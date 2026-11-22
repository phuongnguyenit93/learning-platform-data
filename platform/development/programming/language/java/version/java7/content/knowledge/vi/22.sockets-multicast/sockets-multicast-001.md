# NetworkChannel và cấu hình SocketOption — Java NIO hiện hành

## 1. Vì sao cần NetworkChannel?

Khi xây ứng dụng TCP/UDP, bạn phải chọn địa chỉ và cổng local, đặt kích thước bộ đệm socket, bật hoặc tắt TCP keepalive, quyết định có sử dụng TCP_NODELAY hay cấu hình giao diện multicast. Những thuộc tính này khác nhau giữa **listener TCP**, **kết nối TCP** và **socket UDP**.

Java NIO định nghĩa interface `java.nio.channels.NetworkChannel` cho những thao tác chung:

- `bind(SocketAddress)`: gắn socket với một địa chỉ local.
- `getLocalAddress()`: lấy địa chỉ local đang bound.
- `setOption(SocketOption<T>, T)`: đặt cấu hình socket.
- `getOption(SocketOption<T>)`: đọc cấu hình socket.
- `supportedOptions()`: hỏi **channel cụ thể** hỗ trợ option nào.
- `close()` và `isOpen()`: từ superinterface `Channel`.

Ví dụ minh họa trong một phương thức có xử lý `IOException`:

~~~java
try (DatagramChannel udp =
             DatagramChannel.open(StandardProtocolFamily.INET)) {
    NetworkChannel channel = udp;

    channel.setOption(StandardSocketOptions.SO_REUSEADDR, true);
    channel.setOption(StandardSocketOptions.SO_RCVBUF, 16384);

    channel.bind(new InetSocketAddress(
            InetAddress.getLoopbackAddress(), 0));

    int actualBufferSize =
            channel.getOption(StandardSocketOptions.SO_RCVBUF);
}
~~~

Cần import `java.net.*` và `java.nio.channels.*`. Mã sử dụng **IPv4 UDP trên loopback**, không gửi datagram ra Internet. Đây là đoạn trong phương thức, **không** phải class chạy độc lập.

**Quan trọng:** `NetworkChannel` **không định nghĩa `read`, `write`, `send`, `receive` hoặc `accept`**. Các thao tác truyền dữ liệu thuộc class triển khai. Giao diện này thống nhất **cấu hình socket**, không làm mất sự khác biệt TCP/UDP.

### Mục tiêu học tập

1. Hiểu quan hệ NetworkChannel, SocketOption và các loại socket channels.
2. Dùng `bind` và `getLocalAddress`, phân biệt loopback với wildcard.
3. Hiểu `SocketOption<T>` cung cấp type safety lúc biên dịch.
4. Biết các `StandardSocketOptions` thông dụng và kiểu giá trị tương ứng.
5. Không đặt `TCP_NODELAY` lên server listener, hoặc đặt multicast option lên TCP connection.
6. Kiểm tra `supportedOptions()` để viết chương trình portable hơn.
7. Hiểu `SO_RCVBUF/SO_SNDBUF` là gợi ý và giá trị đọc lại có thể khác request.
8. Cấu hình `SO_REUSEADDR`, `SO_REUSEPORT` và biết giới hạn hệ điều hành.
9. Cấu hình `IP_MULTICAST_IF`, `IP_MULTICAST_TTL`, `IP_MULTICAST_LOOP`.
10. Phân biệt multicast với UDP broadcast.
11. Bắt lỗi option không hỗ trợ, giá trị không hợp lệ và channel đã đóng.
12. Kiểm thử với `ServerSocketChannel`, `SocketChannel`, `DatagramChannel` và các asynchronous channels.
13. Không dùng API deprecated/legacy thay cho cách hiện hành.

**Phiên bản:** `NetworkChannel` và `SocketOption<T>` có từ **Java 7** và vẫn được hỗ trợ. Bài ưu tiên **Java 17+**, tài liệu hiện hành được đối chiếu với **Oracle Java SE 26**. Mười chương trình Java đầy đủ trong bài đã được biên dịch bằng `javac -encoding UTF-8 --release 17` và chạy trên JDK 17; một ví dụ lỗi generic được javac cố ý từ chối.

## 2. Các class triển khai NetworkChannel

~~~text
Channel
  └── NetworkChannel
       ├── ServerSocketChannel             (TCP listener)
       ├── SocketChannel                   (TCP connection)
       ├── AsynchronousServerSocketChannel (asynchronous listener)
       ├── AsynchronousSocketChannel       (asynchronous connection)
       └── MulticastChannel
            └── DatagramChannel           (UDP)
~~~

Sơ đồ chỉ thể hiện những quan hệ liên quan tới chủ đề, không phải toàn bộ Java inheritance tree.

| Loại kênh | Chức năng mạng | Option đáng quan tâm |
| --- | --- | --- |
| `ServerSocketChannel` | TCP listener nhận kết nối | `SO_RCVBUF`, `SO_REUSEADDR` |
| `SocketChannel` | TCP client/accepted connection | `SO_RCVBUF`, `SO_SNDBUF`, `SO_KEEPALIVE`, `TCP_NODELAY`, `SO_REUSEADDR`, `SO_LINGER` |
| `AsynchronousServerSocketChannel` | TCP listener bất đồng bộ | `SO_RCVBUF`, `SO_REUSEADDR` |
| `AsynchronousSocketChannel` | TCP connection bất đồng bộ | `SO_RCVBUF`, `SO_SNDBUF`, `SO_KEEPALIVE`, `TCP_NODELAY`, `SO_REUSEADDR` |
| `DatagramChannel` | UDP/unicast/broadcast/multicast | `SO_RCVBUF`, `SO_SNDBUF`, `SO_REUSEADDR`, `SO_BROADCAST`, `IP_TOS`, `IP_MULTICAST_*` |

Danh sách nêu **các options chuẩn trên IP sockets theo Javadoc**. Những option mở rộng hoặc `SO_REUSEPORT` có thể xuất hiện **tùy hệ điều hành/provider**. Đừng hardcode số option và đừng giả định UNIX-domain sockets có cùng những tùy chọn IPv4/IPv6.

`MulticastChannel extends NetworkChannel`; `DatagramChannel implements MulticastChannel`. Multicast là cơ chế nhóm **IP datagram**, không phải chế độ bổ sung cho TCP listener.

Nguồn: [NetworkChannel Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/NetworkChannel.html), [DatagramChannel](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/DatagramChannel.html), [MulticastChannel](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/MulticastChannel.html).

## 3. SocketOption<T> là gì?

`java.net.SocketOption<T>` đại diện cho một option có **tên** và **kiểu dữ liệu**:

~~~java
SocketOption<Boolean> reuse =
        StandardSocketOptions.SO_REUSEADDR;

SocketOption<Integer> receiveBytes =
        StandardSocketOptions.SO_RCVBUF;

SocketOption<NetworkInterface> outgoingIf =
        StandardSocketOptions.IP_MULTICAST_IF;
~~~

Đây là đoạn minh họa trong phương thức đã import `java.net.*`.

| Option | Kiểu T | Ý nghĩa |
| --- | --- | --- |
| `SO_REUSEADDR` | `Boolean` | Tái sử dụng địa chỉ theo OS |
| `SO_REUSEPORT` | `Boolean` | Tái sử dụng port nếu được hỗ trợ |
| `SO_RCVBUF` | `Integer` | Kích thước yêu cầu của receive buffer tính byte |
| `SO_SNDBUF` | `Integer` | Kích thước yêu cầu của send buffer tính byte |
| `SO_KEEPALIVE` | `Boolean` | Cho phép TCP keepalive probes |
| `TCP_NODELAY` | `Boolean` | Tắt Nagle khi true |
| `SO_LINGER` | `Integer` | Linger trên TCP socket khi close, tùy channel |
| `SO_BROADCAST` | `Boolean` | Cho phép UDP broadcast |
| `IP_TOS` | `Integer` | IP traffic class/Type of Service |
| `IP_MULTICAST_IF` | `NetworkInterface` | Interface dùng để gửi multicast |
| `IP_MULTICAST_TTL` | `Integer` | TTL/hop limit 0..255 |
| `IP_MULTICAST_LOOP` | `Boolean` | Local loopback multicast |

Một option tồn tại trong `StandardSocketOptions` **không** có nghĩa channel nào cũng nhận nó. Việc một giá trị có **đúng kiểu generic** cũng **không** có nghĩa nằm trong khoảng hợp lệ.

### 3.1. Ví dụ 1 — Kiểm tra tên và kiểu option

Tạo `OptionMetadataDemo.java`:

~~~java
import java.net.*;

public class OptionMetadataDemo {
    public static void main(String[] args) {
        SocketOption<Boolean> flag =
                StandardSocketOptions.SO_REUSEADDR;
        SocketOption<Integer> size =
                StandardSocketOptions.SO_RCVBUF;
        SocketOption<NetworkInterface> iface =
                StandardSocketOptions.IP_MULTICAST_IF;

        System.out.println("flagName=" + flag.name());
        System.out.println("flagType=" + flag.type().getSimpleName());
        System.out.println("sizeName=" + size.name());
        System.out.println("sizeType=" + size.type().getSimpleName());
        System.out.println("ifaceType=" + iface.type().getSimpleName());
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 OptionMetadataDemo.java
java OptionMetadataDemo
~~~

Stdout:

~~~text
flagName=SO_REUSEADDR
flagType=Boolean
sizeName=SO_RCVBUF
sizeType=Integer
ifaceType=NetworkInterface
~~~

`name()` và `type()` mô tả bản thân option; các phương thức này **không** chứa trạng thái của một socket. Trạng thái được đọc bằng `channel.getOption(option)` của **channel cụ thể**.

### 3.2. Compiler ngăn truyền sai kiểu

Mã sau **cố ý không biên dịch**:

~~~java
// Sai cố ý: SO_RCVBUF cần Integer, không phải Boolean.
datagram.setOption(StandardSocketOptions.SO_RCVBUF, true);
~~~

Với `datagram` kiểu `DatagramChannel`, javac Java 17 từ chối lời gọi vì `SocketOption<Integer>` không khớp `Boolean`. Phép thử compiler đã xác nhận điều này.

Cách đúng:

~~~java
datagram.setOption(StandardSocketOptions.SO_RCVBUF, 8192);
datagram.setOption(StandardSocketOptions.SO_REUSEADDR, true);
~~~

Các đoạn này là **mã minh họa trong phương thức**, không phải class chạy độc lập. Kiểu generic bảo vệ bạn khỏi **sai kiểu**, còn phạm vi giá trị, hỗ trợ của OS và trạng thái channel vẫn cần kiểm tra lúc chạy.

## 4. bind và getLocalAddress: local address không phải remote address

`NetworkChannel.bind(SocketAddress)` liên kết socket với một địa chỉ local. `getLocalAddress()` trả địa chỉ mà socket đã bind, hoặc `null` nếu chưa bound.

~~~java
channel.bind(new InetSocketAddress(
        InetAddress.getLoopbackAddress(), 0));
~~~

- `InetAddress.getLoopbackAddress()`: địa chỉ cho **local loopback**.
- Port `0`: nhờ OS chọn một **port rảnh**; phải đọc lại số port qua `getLocalAddress()`.
- `bind(null)` hoặc bind wildcard: có thể tạo socket lắng nghe trên **nhiều network interfaces** tùy loại channel, **không giống** loopback.
- Một channel đã bind mà bind lại thường ném `AlreadyBoundException`.
- Đóng channel thì địa chỉ binding không còn thuộc một listener/socket đang mở.

**Không nhầm bind với connect:** TCP client `SocketChannel.connect(remote)` tạo kết nối tới peer, còn `bind(local)` chọn địa chỉ nguồn local. UDP `DatagramChannel.send(buffer,target)` không nhất thiết phải connect trước.

### 4.1. Đặt option trước/sau bind

`SO_REUSEADDR` thường cần được đặt **trước khi bind**, nhất là trường hợp nhiều multicast receivers cùng port hoặc server restart. Với `SO_RCVBUF`, tài liệu lưu ý việc yêu cầu size lớn hơn (và TCP receive window) có thể phụ thuộc thời điểm trước connect/bind.

Không áp dụng một quy tắc chung "mọi option chỉ được set trước bind" hoặc "mọi option đều có thể đổi sau bind". Hãy đọc Javadoc của **option** và **loại channel**.

## 5. Ví dụ 2 — NetworkChannel cấu hình UDP rồi bind loopback

Tạo `UdpNetworkChannelDemo.java`:

~~~java
import java.net.*;
import java.nio.channels.*;

public class UdpNetworkChannelDemo {
    public static void main(String[] args) throws Exception {
        try (DatagramChannel datagram =
                DatagramChannel.open(StandardProtocolFamily.INET)) {
            NetworkChannel net = datagram;

            System.out.println("beforeBind=" +
                    (net.getLocalAddress() == null));

            System.out.println("supportsReuse=" +
                    net.supportedOptions().contains(
                            StandardSocketOptions.SO_REUSEADDR));

            net.setOption(StandardSocketOptions.SO_REUSEADDR, true);
            net.setOption(StandardSocketOptions.SO_RCVBUF, 16384);

            net.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 0));

            InetSocketAddress local =
                    (InetSocketAddress) net.getLocalAddress();

            System.out.println("boundLoopback=" +
                    local.getAddress().isLoopbackAddress());
            System.out.println("assignedPort=" +
                    (local.getPort() > 0));
            System.out.println("reuseEnabled=" +
                    net.getOption(StandardSocketOptions.SO_REUSEADDR));
            System.out.println("receiveBufferPositive=" +
                    (net.getOption(StandardSocketOptions.SO_RCVBUF) > 0));
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 UdpNetworkChannelDemo.java
java UdpNetworkChannelDemo
~~~

Stdout kiểm chứng trên JDK 17:

~~~text
beforeBind=true
supportsReuse=true
boundLoopback=true
assignedPort=true
reuseEnabled=true
receiveBufferPositive=true
~~~

**Phân tích:**

1. `DatagramChannel.open(INET)` tạo kênh UDP/IPv4 chưa bind.
2. Gán nó cho biến `NetworkChannel net` để cho thấy dùng API chung.
3. Kiểm tra hỗ trợ rồi bật `SO_REUSEADDR` trước bind.
4. Yêu cầu `SO_RCVBUF=16384`; OS có thể chọn kích thước khác.
5. Bind loopback/cổng động, lấy `InetSocketAddress` thực.
6. Đọc lại cờ reuse và kiểm tra receive buffer có giá trị dương.
7. Try-with-resources đóng kênh; không mở dịch vụ public hay gửi datagram ra Internet.

**Điểm cốt lõi:** Lời gọi `setOption` là **cấu hình cho socket**, không phải lệnh gửi gói UDP.

## 6. So sánh options của TCP listener và TCP connection

Một server TCP có hai loại channel:

~~~text
ServerSocketChannel        (listener; bind và accept)
        |
        +-- accept()
                 |
                 v
          SocketChannel   (accepted TCP connection)

SocketChannel client      (TCP connection phía client)
        |
        +-- connect(serverAddress)
~~~

- Trên listener, `SO_REUSEADDR`/`SO_RCVBUF` thường hữu ích.
- Trên mỗi connection, `TCP_NODELAY`/`SO_KEEPALIVE`/`SO_SNDBUF` và các option TCP khác có ý nghĩa riêng.
- Đặt option trên một client SocketChannel **không đồng nghĩa** option cùng giá trị ở accepted SocketChannel phía server.
- `TCP_NODELAY=true` **tắt Nagle algorithm**, không loại bỏ mọi buffering và không làm TCP giữ ranh giới message.
- `SO_KEEPALIVE=true` bật cơ chế probe TCP của OS; **không** phải app heartbeat, TLS hay xác thực.

## 7. Ví dụ 3 — TCP listener, client và accepted connection

Tạo `TcpChannelOptionsDemo.java`:

~~~java
import java.net.*;
import java.nio.channels.*;

public class TcpChannelOptionsDemo {
    public static void main(String[] args) throws Exception {
        try (ServerSocketChannel server = ServerSocketChannel.open();
             SocketChannel client = SocketChannel.open()) {

            NetworkChannel listener = server;
            listener.setOption(StandardSocketOptions.SO_REUSEADDR, true);

            server.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 0));

            client.setOption(StandardSocketOptions.TCP_NODELAY, true);
            client.setOption(StandardSocketOptions.SO_KEEPALIVE, true);
            client.connect(server.getLocalAddress());

            try (SocketChannel accepted = server.accept()) {
                accepted.setOption(StandardSocketOptions.TCP_NODELAY, true);

                System.out.println("serverReuse=" +
                        listener.getOption(
                                StandardSocketOptions.SO_REUSEADDR));
                System.out.println("serverSupportsNodelay=" +
                        listener.supportedOptions().contains(
                                StandardSocketOptions.TCP_NODELAY));
                System.out.println("clientNodelay=" +
                        client.getOption(StandardSocketOptions.TCP_NODELAY));
                System.out.println("clientKeepalive=" +
                        client.getOption(StandardSocketOptions.SO_KEEPALIVE));
                System.out.println("acceptedNodelay=" +
                        accepted.getOption(StandardSocketOptions.TCP_NODELAY));
                System.out.println("clientConnected=" + client.isConnected());
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 TcpChannelOptionsDemo.java
java TcpChannelOptionsDemo
~~~

Stdout:

~~~text
serverReuse=true
serverSupportsNodelay=false
clientNodelay=true
clientKeepalive=true
acceptedNodelay=true
clientConnected=true
~~~

`ServerSocketChannel` lắng nghe chứ không truyền bytes TCP của một phiên, nên `TCP_NODELAY` không nằm trong tập option chuẩn của listener. `SocketChannel` đã kết nối mới là nơi cấu hình TCP_NODELAY. Phần thử đặt option cho accepted channel riêng biệt thể hiện **hai đầu connection có cấu hình riêng**.

**Bảo mật:** Listener chỉ bind loopback, port do OS cấp; socket options không cung cấp TLS. Không triển khai ra Internet nếu chưa có firewall, authentication và protocol framing đúng.

## 8. supportedOptions trước setOption

`NetworkChannel.supportedOptions()` trả một `Set<SocketOption<?>>`. Các option có mặt trong tập này được channel/provider quảng bá hỗ trợ; tuy nhiên giá trị bạn yêu cầu vẫn có thể sai hoặc OS từ chối vì nguyên nhân khác.

Quy trình khuyến nghị:

~~~text
1. Chọn đúng channel và protocol family
2. Kiểm tra supportedOptions().contains(option)
3. Validate giá trị: kiểu, khoảng số, interface, policy
4. Chọn thời điểm set trước/sau bind/connect
5. Gọi setOption(option, value)
6. Gọi getOption(option) để xem giá trị thực
7. Đo hành vi trên OS/runtime đích
~~~

Không giả định `supportedOptions().size()` cố định giữa Windows, Linux, macOS hoặc providers. Đừng biến option chỉ phục vụ performance thành dependency bắt buộc nếu ứng dụng có fallback hợp lý; ngược lại, nếu option là **bắt buộc** cho nghiệp vụ, hãy fail-fast khi không có.

### 8.1. Các ngoại lệ cần xử lý

| Hoàn cảnh | Dạng lỗi |
| --- | --- |
| Channel không hỗ trợ option | `UnsupportedOperationException` |
| Giá trị option ngoài khoảng | `IllegalArgumentException` |
| Channel đã đóng | `ClosedChannelException` |
| Truyền tên option `null` | `NullPointerException` |
| Lỗi OS/socket | `IOException` hoặc subclass |
| Bind lại channel đã bound | `AlreadyBoundException` |
| Bind địa chỉ sai loại | `UnsupportedAddressTypeException` hoặc lỗi theo provider |

Không che những lỗi này bằng `catch(Exception ignored)`. Cần ghi lại nguyên nhân để phân biệt “option thiếu”, “config sai” và “môi trường mạng lỗi”.

## 9. Ví dụ 4 — Option không hỗ trợ, buffer âm và null

Tạo `UnsupportedOptionDemo.java`:

~~~java
import java.net.*;
import java.nio.channels.*;

public class UnsupportedOptionDemo {
    public static void main(String[] args) throws Exception {
        try (ServerSocketChannel server = ServerSocketChannel.open();
             DatagramChannel udp =
                     DatagramChannel.open(StandardProtocolFamily.INET)) {

            boolean serverNoNodelay =
                    !server.supportedOptions().contains(
                            StandardSocketOptions.TCP_NODELAY);

            boolean unsupportedRejected = false;
            try {
                server.setOption(StandardSocketOptions.TCP_NODELAY, true);
            } catch (UnsupportedOperationException e) {
                unsupportedRejected = true;
            }

            boolean invalidBufferRejected = false;
            try {
                udp.setOption(StandardSocketOptions.SO_RCVBUF, -1);
            } catch (IllegalArgumentException e) {
                invalidBufferRejected = true;
            }

            boolean nullOptionRejected = false;
            try {
                udp.getOption(null);
            } catch (NullPointerException e) {
                nullOptionRejected = true;
            }

            System.out.println("serverNoNodelay=" + serverNoNodelay);
            System.out.println("unsupportedRejected=" + unsupportedRejected);
            System.out.println("negativeBufferRejected=" +
                    invalidBufferRejected);
            System.out.println("nullOptionRejected=" +
                    nullOptionRejected);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 UnsupportedOptionDemo.java
java UnsupportedOptionDemo
~~~

Stdout:

~~~text
serverNoNodelay=true
unsupportedRejected=true
negativeBufferRejected=true
nullOptionRejected=true
~~~

Trên provider đã kiểm thử, các lỗi xuất hiện tại thời điểm gọi method. Một option có kiểu `Integer` nhưng giá trị âm vẫn sai; generic type không thay value validation. Trong production, tránh dùng exception như một cách thông thường để khám phá option, thay vào đó kiểm tra `supportedOptions()` trước.

## 10. Ba option multicast cần phân biệt

Với một `DatagramChannel` có protocol family phù hợp:

| Option | Kiểu dữ liệu | Ý nghĩa |
| --- | --- | --- |
| `IP_MULTICAST_IF` | `NetworkInterface` | Network interface dùng **gửi** multicast |
| `IP_MULTICAST_TTL` | `Integer` | TTL/hop limit từ 0 đến 255 |
| `IP_MULTICAST_LOOP` | `Boolean` | Bật/tắt loopback của multicast packets trên máy local |

Còn `SO_BROADCAST` là cho **IPv4 UDP broadcast**, không phải một multicast membership.

### 10.1. TTL là hop limit, không phải giây

Với IPv4 multicast, TTL ảnh hưởng số hop mà datagram có thể đi qua; với IPv6 là hop limit. `IP_MULTICAST_TTL=1` **không phải timeout 1 giây**. TTL=0 không đưa datagram ra mạng nhưng có thể giao local. TTL không thay firewall, authentication hay kiểm soát dữ liệu.

### 10.2. IP_MULTICAST_LOOP mang nghĩa thuận

~~~java
udp.setOption(StandardSocketOptions.IP_MULTICAST_LOOP, true);
~~~

`true` nghĩa là **bật** loopback theo cách định nghĩa của StandardSocketOptions. Đây là một hint cho network stack; không bảo đảm mọi OS/interface luôn giao multicast trở về socket như nhau. Không dùng cách hiểu đảo ngược của phương thức cũ `MulticastSocket.setLoopbackMode(boolean disable)` (**deprecated từ Java 14**) trong code mới.

### 10.3. NetworkInterface cho multicast

Trước khi tham gia nhóm, cần chọn interface thực sự tồn tại, đang UP và hỗ trợ multicast. Với mã minh họa dưới đây, `interfaceName` và `port` là biến cấu hình đã khai báo:

~~~java
NetworkInterface ni = NetworkInterface.getByName(interfaceName);

if (ni == null || !ni.isUp() || !ni.supportsMulticast()) {
    throw new IllegalStateException("Unavailable multicast interface");
}

try (DatagramChannel dc =
             DatagramChannel.open(StandardProtocolFamily.INET)) {
    dc.setOption(StandardSocketOptions.SO_REUSEADDR, true);
    dc.bind(new InetSocketAddress(port));
    dc.setOption(StandardSocketOptions.IP_MULTICAST_IF, ni);
    dc.setOption(StandardSocketOptions.IP_MULTICAST_TTL, 1);
    dc.setOption(StandardSocketOptions.IP_MULTICAST_LOOP, true);

    InetAddress group = InetAddress.getByName("239.255.0.1");
    MembershipKey membership = dc.join(group, ni);
    try {
        // Nhận/giải mã datagram theo giao thức ứng dụng.
    } finally {
        membership.drop();
    }
}
~~~

Đây là **đoạn minh họa không phải class chạy độc lập**; import `java.net.*` và `java.nio.channels.*`, xử lý IOException. Không hardcode tên interface như `eth0` vì các máy có NIC khác nhau.

Theo Javadoc `MulticastChannel`:

- Chọn `StandardProtocolFamily.INET/INET6` tương ứng địa chỉ nhóm.
- Với **multicast receiver**, thường bind vào **wildcard address**, vì bind tới một địa chỉ giao diện cụ thể có thể không nhận multicast trên một số OS.
- Bật `SO_REUSEADDR` **trước bind** nếu nhiều thành viên cùng nhận theo một địa chỉ/port.
- `MembershipKey.drop()` dùng rời nhóm; đóng channel cũng làm membership không hợp lệ.
- Có thể cần routing, firewall và hỗ trợ multicast từ VM/container/VPN/network.
- Đừng suy luận TTL/loopback là công cụ bảo mật; chúng chỉ điều khiển phạm vi/looping.

Để không phụ thuộc một mạng multicast thật, ví dụ Java chạy độc lập tiếp theo **chỉ kiểm tra set/get options**, không join hoặc gửi multicast ra mạng ngoài.

## 11. Ví dụ 5 — Multicast TTL, loopback và broadcast options

Tạo `MulticastOptionsDemo.java`:

~~~java
import java.net.*;
import java.nio.channels.*;

public class MulticastOptionsDemo {
    public static void main(String[] args) throws Exception {
        try (DatagramChannel udp =
                DatagramChannel.open(StandardProtocolFamily.INET)) {

            udp.setOption(StandardSocketOptions.IP_MULTICAST_TTL, 1);
            udp.setOption(StandardSocketOptions.IP_MULTICAST_LOOP, true);
            udp.setOption(StandardSocketOptions.SO_BROADCAST, false);

            System.out.println("supportsMulticastIF=" +
                    udp.supportedOptions().contains(
                            StandardSocketOptions.IP_MULTICAST_IF));
            System.out.println("multicastTTL=" +
                    udp.getOption(StandardSocketOptions.IP_MULTICAST_TTL));
            System.out.println("multicastLoop=" +
                    udp.getOption(StandardSocketOptions.IP_MULTICAST_LOOP));
            System.out.println("broadcastEnabled=" +
                    udp.getOption(StandardSocketOptions.SO_BROADCAST));
            System.out.println("isBound=" +
                    (udp.getLocalAddress() != null));
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 MulticastOptionsDemo.java
java MulticastOptionsDemo
~~~

Stdout:

~~~text
supportsMulticastIF=true
multicastTTL=1
multicastLoop=true
broadcastEnabled=false
isBound=false
~~~

Một `setOption` không tự động tạo multicast membership, không có datagram được gửi/nhận và channel vẫn chưa bind trong fixture. `SO_BROADCAST=false` cũng không đồng nghĩa multicast bị tắt: broadcast và multicast có semantics khác nhau.

## 12. Dùng UDP loopback để kiểm tra socket hoạt động

UDP là **datagram**, không phải TCP byte stream. Một lời gọi `DatagramChannel.send(buffer,target)` đưa một datagram tới địa chỉ đích; `receive(buffer)` trả địa chỉ người gửi hoặc `null` nếu channel ở chế độ nonblocking và chưa có datagram.

UDP không đảm bảo packets được giao, đúng thứ tự hoặc không mất. Receive buffer quá nhỏ có thể làm payload bị cắt. `SO_RCVBUF` có thể hỗ trợ khi có burst traffic nhưng không làm UDP thành reliable transport.

## 13. Ví dụ 6 — Gửi nhận UDP nội bộ với SO_RCVBUF

Tạo `UdpLoopbackDemo.java`:

~~~java
import java.net.*;
import java.nio.*;
import java.nio.channels.*;
import java.nio.charset.*;
import java.util.concurrent.*;

public class UdpLoopbackDemo {
    public static void main(String[] args) throws Exception {
        try (DatagramChannel receive =
                DatagramChannel.open(StandardProtocolFamily.INET);
             DatagramChannel send =
                DatagramChannel.open(StandardProtocolFamily.INET)) {

            receive.setOption(StandardSocketOptions.SO_RCVBUF, 8192);
            receive.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 0));
            send.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 0));

            receive.configureBlocking(false);

            ByteBuffer payload = ByteBuffer.wrap(
                    "UDP".getBytes(StandardCharsets.US_ASCII));
            int written = send.send(payload, receive.getLocalAddress());

            ByteBuffer buf = ByteBuffer.allocate(16);
            SocketAddress source = null;
            long deadline =
                    System.nanoTime() + TimeUnit.SECONDS.toNanos(3);

            while (source == null && System.nanoTime() < deadline) {
                source = receive.receive(buf);
                if (source == null) {
                    Thread.sleep(10);
                }
            }

            if (source == null) {
                throw new AssertionError(
                        "UDP loopback reception timed out");
            }

            buf.flip();
            System.out.println("sentBytes=" + written);
            System.out.println("received=" +
                    StandardCharsets.US_ASCII.decode(buf));
            System.out.println("sourceIsLoopback=" +
                    ((InetSocketAddress) source)
                            .getAddress().isLoopbackAddress());
            System.out.println("receiveBufferPositive=" +
                    (receive.getOption(StandardSocketOptions.SO_RCVBUF) > 0));
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 UdpLoopbackDemo.java
java UdpLoopbackDemo
~~~

Stdout đã kiểm chứng:

~~~text
sentBytes=3
received=UDP
sourceIsLoopback=true
receiveBufferPositive=true
~~~

**Giải thích:**

1. Hai DatagramChannels mở IPv4 và bind loopback/port động.
2. Receiver yêu cầu receive buffer 8192 byte.
3. Receiver chuyển sang chế độ nonblocking.
4. Sender gửi ba byte ASCII `UDP` tới receiver.
5. Vòng polling có deadline 3 giây; nếu chưa có packet, `receive` trả null.
6. Sau khi nhận, `flip()` chuẩn bị ByteBuffer để decode.
7. Source address được kiểm tra là loopback.
8. Không in giá trị SO_RCVBUF cụ thể vì OS có thể điều chỉnh.

Trong code production, nên dùng `Selector`/event loop thay cho sleep-based polling, kiểm soát packet size, loss, rate limits và input validation. Mẫu này chỉ phục vụ integration test cục bộ.

## 14. NetworkChannel áp dụng cho asynchronous TCP

`AsynchronousServerSocketChannel` cũng là một NetworkChannel, nhưng **chỉ đóng vai trò TCP listener**. `AsynchronousSocketChannel` là kết nối TCP và hỗ trợ các option như `TCP_NODELAY` và `SO_KEEPALIVE`.

Các channel bất đồng bộ có thao tác accept/connect/read/write qua `Future` hoặc `CompletionHandler`. Điều đó không thay cách cấu hình options:

~~~java
NetworkChannel listener = asyncServer;
listener.setOption(StandardSocketOptions.SO_REUSEADDR, true);

NetworkChannel client = asyncClient;
client.setOption(StandardSocketOptions.TCP_NODELAY, true);
~~~

Đoạn trên minh họa trong một method với `asyncServer`/`asyncClient` đã được mở. `TCP_NODELAY` vẫn là option của **connection**, không phải listener.

## 15. Ví dụ 7 — SocketOption trên asynchronous channels

Tạo `AsyncOptionsDemo.java`:

~~~java
import java.net.*;
import java.nio.channels.*;
import java.util.concurrent.*;

public class AsyncOptionsDemo {
    public static void main(String[] args) throws Exception {
        try (AsynchronousServerSocketChannel server =
                AsynchronousServerSocketChannel.open();
             AsynchronousSocketChannel client =
                AsynchronousSocketChannel.open()) {

            NetworkChannel listener = server;
            listener.setOption(StandardSocketOptions.SO_REUSEADDR, true);
            server.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 0));

            NetworkChannel connection = client;
            connection.setOption(StandardSocketOptions.TCP_NODELAY, true);
            connection.setOption(StandardSocketOptions.SO_KEEPALIVE, true);

            Future<AsynchronousSocketChannel> pending = server.accept();

            client.connect(server.getLocalAddress())
                    .get(5, TimeUnit.SECONDS);

            try (AsynchronousSocketChannel accepted =
                    pending.get(5, TimeUnit.SECONDS)) {
                System.out.println("serverReuse=" +
                        listener.getOption(
                                StandardSocketOptions.SO_REUSEADDR));
                System.out.println("clientNodelay=" +
                        connection.getOption(
                                StandardSocketOptions.TCP_NODELAY));
                System.out.println("clientKeepalive=" +
                        connection.getOption(
                                StandardSocketOptions.SO_KEEPALIVE));
                System.out.println("acceptedOpen=" + accepted.isOpen());
                System.out.println("serverDoesNotHaveNodelay=" +
                        !server.supportedOptions().contains(
                                StandardSocketOptions.TCP_NODELAY));
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 AsyncOptionsDemo.java
java AsyncOptionsDemo
~~~

Stdout:

~~~text
serverReuse=true
clientNodelay=true
clientKeepalive=true
acceptedOpen=true
serverDoesNotHaveNodelay=true
~~~

Chương trình bind server loopback, client connect, Future accept nhận channel riêng và tự đóng tài nguyên. Những option của client **không tự động đặt** cho accepted-side channel, nếu cần phải cấu hình accepted channel riêng theo chính sách phiên.

## 16. Viết helper generic đúng kiểu

Dùng helper chung khi nhiều lớp cùng cấu hình NetworkChannel:

~~~java
static <T> void setIfSupported(
        NetworkChannel ch, SocketOption<T> option, T value)
        throws IOException {
    if (!ch.supportedOptions().contains(option)) {
        throw new UnsupportedOperationException(
                option.name() + " not supported");
    }
    ch.setOption(option, value);
}
~~~

Đây là method minh họa; import `java.io.IOException`, `java.net.SocketOption`, `java.nio.channels.NetworkChannel`.

`<T>` liên kết type của option với type của value tại compile time. Cách này tốt hơn tạo một `Map<String,Object>` rồi cast mọi value thành Boolean/Integer thủ công mà không kiểm soát.

### 16.1. Ví dụ 8 — Helper setIfSupported chạy thực

Tạo `SocketOptionHelperDemo.java`:

~~~java
import java.net.*;
import java.nio.channels.*;
import java.io.*;

public class SocketOptionHelperDemo {
    static <T> void setIfSupported(
            NetworkChannel ch,
            SocketOption<T> option,
            T value) throws IOException {
        if (!ch.supportedOptions().contains(option)) {
            throw new UnsupportedOperationException(
                    option.name() + " not supported");
        }
        ch.setOption(option, value);
    }

    public static void main(String[] args) throws Exception {
        try (DatagramChannel udp =
                DatagramChannel.open(StandardProtocolFamily.INET)) {

            setIfSupported(
                    udp, StandardSocketOptions.SO_REUSEADDR, true);
            setIfSupported(
                    udp, StandardSocketOptions.SO_RCVBUF, 8192);

            System.out.println("reuse=" +
                    udp.getOption(StandardSocketOptions.SO_REUSEADDR));
            System.out.println("bufferSizePositive=" +
                    (udp.getOption(StandardSocketOptions.SO_RCVBUF) > 0));
            System.out.println("optionCountNonzero=" +
                    !udp.supportedOptions().isEmpty());
            System.out.println("optionTypes=" +
                    StandardSocketOptions.SO_REUSEADDR.type()
                            .getSimpleName() + "/" +
                    StandardSocketOptions.SO_RCVBUF.type()
                            .getSimpleName());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 SocketOptionHelperDemo.java
java SocketOptionHelperDemo
~~~

Stdout:

~~~text
reuse=true
bufferSizePositive=true
optionCountNonzero=true
optionTypes=Boolean/Integer
~~~

Trong production, chọn policy theo mục tiêu: nếu một option cần thiết mà unsupported, fail-fast; nếu là performance hint có thể sử dụng fallback và ghi warning. Dù helper kiểm tra supportedOptions, `setOption` vẫn có thể ném IllegalArgumentException/IOException vì giá trị hoặc môi trường.

## 17. supportedOptions sau close khác với set/get sau close

Javadoc NetworkChannel nói `supportedOptions()` tiếp tục trả tập option **sau khi channel đóng**. Tuy nhiên, `getOption/setOption` lúc đó **không còn tương tác được với socket** và có thể ném `ClosedChannelException`. Việc channel đã đóng không được khắc phục bằng cách set lại SO_REUSEADDR.

### 17.1. Ví dụ 9 — Option trên channel đóng bị từ chối

Tạo `ClosedChannelOptionsDemo.java`:

~~~java
import java.net.*;
import java.nio.channels.*;

public class ClosedChannelOptionsDemo {
    public static void main(String[] args) throws Exception {
        DatagramChannel dc =
                DatagramChannel.open(StandardProtocolFamily.INET);
        dc.close();

        boolean setClosed = false;
        boolean getClosed = false;

        try {
            dc.setOption(StandardSocketOptions.SO_REUSEADDR, true);
        } catch (ClosedChannelException ex) {
            setClosed = true;
        }

        try {
            dc.getOption(StandardSocketOptions.SO_REUSEADDR);
        } catch (ClosedChannelException ex) {
            getClosed = true;
        }

        System.out.println("closed=" + !dc.isOpen());
        System.out.println("setRejected=" + setClosed);
        System.out.println("getRejected=" + getClosed);
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 ClosedChannelOptionsDemo.java
java ClosedChannelOptionsDemo
~~~

Stdout:

~~~text
closed=true
setRejected=true
getRejected=true
~~~

Đây là lỗi **lifecycle**, không phải option không tồn tại. Trong ứng dụng nhiều threads, cần ownership rõ để không có thread đóng channel khi thread khác vẫn đang configure hoặc gửi/nhận.

## 18. Multicast TTL: kiểu đúng chưa chắc giá trị đúng

`IP_MULTICAST_TTL` là `SocketOption<Integer>`, nhưng khoảng hợp lệ **0..255**. Do đó:

~~~java
dc.setOption(StandardSocketOptions.IP_MULTICAST_TTL, 1);
~~~

đúng kiểu và giá trị hợp lệ; còn:

~~~java
dc.setOption(StandardSocketOptions.IP_MULTICAST_TTL, 256);
~~~

có thể **biên dịch** nhưng bị từ chối ở runtime.

### 18.1. Ví dụ 10 — Kiểm tra TTL ngoài khoảng

Tạo `MulticastTtlValidationDemo.java`:

~~~java
import java.net.*;
import java.nio.channels.*;

public class MulticastTtlValidationDemo {
    public static void main(String[] args) throws Exception {
        try (DatagramChannel dc =
                DatagramChannel.open(StandardProtocolFamily.INET)) {

            boolean invalidRejected = false;
            try {
                dc.setOption(StandardSocketOptions.IP_MULTICAST_TTL, 256);
            } catch (IllegalArgumentException e) {
                invalidRejected = true;
            }

            dc.setOption(StandardSocketOptions.IP_MULTICAST_TTL, 1);

            System.out.println("tooLargeTtlRejected=" + invalidRejected);
            System.out.println("validTtl=" +
                    dc.getOption(StandardSocketOptions.IP_MULTICAST_TTL));
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 MulticastTtlValidationDemo.java
java MulticastTtlValidationDemo
~~~

Stdout:

~~~text
tooLargeTtlRejected=true
validTtl=1
~~~

**Bài học:** `SocketOption<T>` kiểm tra **type**, nhưng vẫn phải validate **range**, option support, protocol family và policy môi trường. Đặc biệt với config từ file hoặc API, không chỉ parse Integer rồi đưa trực tiếp vào kernel.

## 19. Các điểm dễ nhầm cần phân biệt

### 19.1. SO_REUSEADDR không đồng nghĩa SO_REUSEPORT

`SO_REUSEADDR` hỗ trợ một số ngữ cảnh tái sử dụng địa chỉ, tùy OS và socket protocol. `SO_REUSEPORT` có từ **Java 9** và việc hỗ trợ phụ thuộc OS/provider. Không bật SO_REUSEPORT một cách vô điều kiện.

Đoạn minh họa kiểm tra khả năng hỗ trợ:

~~~java
if (channel.supportedOptions().contains(
        StandardSocketOptions.SO_REUSEPORT)) {
    channel.setOption(StandardSocketOptions.SO_REUSEPORT, true);
} else {
    // Thiết kế không phụ thuộc SO_REUSEPORT.
}
~~~

Không có output cố định vì OS có thể hỗ trợ hoặc không. Cả hai option **không tự cấp quyền bind cùng port vô điều kiện**, cũng không thay security isolation của ứng dụng.

### 19.2. SO_RCVBUF/SO_SNDBUF là yêu cầu, không phải bảo đảm

Nếu set `SO_RCVBUF=65536`, OS có thể clamp/round, và một số nền tảng dùng giá trị theo cách khác. Dùng `getOption()` để xem giá trị hiệu lực và benchmark khi tối ưu.

Socket buffer size không có nghĩa một lần TCP `read/write` luôn chuyển đủ số byte đó; TCP là stream và partial I/O vẫn có thể xảy ra. Với UDP, buffer quá nhỏ có thể gây rơi/cắt datagram, nhưng buffer lớn không thay thế flow control của ứng dụng.

### 19.3. TCP_NODELAY và SO_KEEPALIVE không phải bảo mật

- `TCP_NODELAY=true` tắt thuật toán Nagle; TCP vẫn có buffering và không giữ ranh giới message.
- `SO_KEEPALIVE=true` bật OS-level TCP probes; interval và chính sách có thể khác máy.
- Cả hai không cung cấp TLS, certificate verification, authentication hoặc application heartbeat.
- Cân nhắc tác động latency/throughput bằng benchmark, không bật tuỳ tiện mọi cờ.

### 19.4. Broadcast khác multicast

`SO_BROADCAST` cho UDP broadcast; multicast dùng nhóm địa chỉ và interface membership. `IP_MULTICAST_LOOP=true` không phải `SO_BROADCAST=true`. Nếu một ứng dụng gửi multicast, đừng chỉ set loop/TTL mà quên chọn địa chỉ group, interface và network policy.

### 19.5. IP_TOS không cam kết chất lượng dịch vụ end-to-end

`IP_TOS` là gợi ý ToS/traffic class cho network stack. Router, OS và mạng trung gian có thể diễn giải khác nhau hoặc bỏ qua. Không dùng IP_TOS làm biện pháp bảo mật hay lời hứa packet luôn được ưu tiên.

### 19.6. Không dùng SO_TIMEOUT như một StandardSocketOption

`SO_TIMEOUT` xuất hiện trong một số API socket blocking và interface implementation-level `SocketOptions`, nhưng **không có** hằng `StandardSocketOptions.SO_TIMEOUT`. Đừng tự tạo option ảo cho NetworkChannel; chọn timeout mechanism phù hợp với `Selector`, asynchronous read/write overload, Future hoặc API socket cụ thể.

## 20. Những cách cũ nên tránh theo Special Note

Ưu tiên **API vẫn được hỗ trợ**:

- `NetworkChannel.setOption/getOption/supportedOptions` trên NIO channels.
- `StandardSocketOptions` thay cho numeric option IDs từ `java.net.SocketOptions` implementation-level.
- Tránh `jdk.net.Sockets` static helpers: class đó **deprecated từ Java 16**, và các socket hiện đại đã có API trực tiếp.
- Tránh `MulticastSocket.setLoopbackMode(boolean disable)` (**deprecated từ Java 14**). Dùng `setOption(StandardSocketOptions.IP_MULTICAST_LOOP,true/false)` để không đảo nhầm semantics.
- Nếu dùng `jdk.net.ExtendedSocketOptions`, chú ý đó là extension phụ thuộc JDK/platform, không giả định có trên mọi runtime.
- Không hardcode tên NIC, kích thước receive buffer hiệu lực, thứ tự supportedOptions hoặc số lượng extension options.
- Không biến một ví dụ loopback thành public listener ngoài ý muốn khi chuyển sang production.

## 21. Lỗi phổ biến và cách xử lý

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Dùng NetworkChannel như class đọc/ghi | Không có API read/write/send trên interface | Dùng SocketChannel/DatagramChannel đúng loại |
| `setOption(SO_RCVBUF,true)` | Lỗi javac do sai type | Integer dương |
| Set `TCP_NODELAY` trên ServerSocketChannel | UnsupportedOperationException | Set trên TCP connection |
| Bỏ qua supportedOptions | Lỗi khi khác OS/provider | Kiểm tra trước, fallback/fail-fast |
| Gửi TTL=256 | IllegalArgumentException | Giới hạn 0..255 |
| Cố set/get trên channel đã đóng | ClosedChannelException | Quản lý lifecycle |
| Set SO_RCVBUF và khẳng định giá trị đúng tuyệt đối | OS có thể điều chỉnh | Get lại và benchmark |
| Dùng SO_REUSEPORT không kiểm tra | UnsupportedOperationException | Check supportedOptions |
| Nhầm true của IP_MULTICAST_LOOP là disable | Bật/tắt sai | true bật local loopback |
| Nhầm multicast TTL với timer | Cấu hình sai | TTL là hop limit |
| Bind wildcard khi chỉ muốn loopback | Có thể mở dịch vụ trên network interfaces | Bind địa chỉ rõ ràng |
| Hardcode interface name | Không portable | NetworkInterface.getByName và validation |
| Gọi receive nonblocking và không kiểm tra null | Logic sai/vòng lặp | Selector/deadline |
| Tin SO_KEEPALIVE là xác thực hoặc TLS | Lỗ hổng thiết kế | TLS, protocol authentication |
| Dùng SO_BROADCAST thay IP multicast config | Sai nhóm gói | Phân biệt broadcast và multicast |
| Không đóng MembershipKey/channel | Leak resources/membership | drop/close trong finally |
| Dựa vào jdk.net.Sockets deprecated | Đường đi cũ | Method trực tiếp trên channel |

## 22. Checklist trước triển khai

1. Có chọn đúng class NetworkChannel theo TCP listener, TCP connection, UDP hoặc asynchronous?
2. Có phân biệt `bind(local)` và `connect(remote)`?
3. Có chọn loopback, wildcard hay interface production đúng ý định?
4. Có bind port `0` cho integration test thay vì hardcode cổng dễ xung đột?
5. Có dùng `SocketOption<T>` đúng kiểu Boolean/Integer/NetworkInterface?
6. Có kiểm tra `supportedOptions()` với option optional hoặc phụ thuộc OS?
7. Có validate TTL 0..255 và buffer size dương?
8. Có đặt SO_REUSEADDR trước bind trong trường hợp cần?
9. Có phân biệt SO_REUSEADDR với SO_REUSEPORT?
10. Có tránh đặt TCP_NODELAY trên listener?
11. Đã cấu hình accepted-side TCP connection riêng nếu cần?
12. Có nhớ SO_RCVBUF/SO_SNDBUF là hint, không phải giá trị chắc chắn?
13. Có kiểm tra getOption/actual effective values?
14. Nếu multicast, có dùng đúng protocol family INET/INET6?
15. Có kiểm tra NIC đang up và supportsMulticast?
16. Có hiểu multicast receiver thường bind wildcard?
17. Có xử lý MembershipKey/drop/close?
18. Có hiểu IP_MULTICAST_LOOP=true là bật loopback?
19. Có phân biệt SO_BROADCAST và IP_MULTICAST_*?
20. Có xử lý UnsupportedOperationException, IllegalArgumentException, IOException?
21. Có xử lý ClosedChannelException và tránh race giữa config/close?
22. Có tránh các API deprecated như jdk.net.Sockets và setLoopbackMode?
23. Có TLS/authentication/firewall/quota khi phục vụ mạng ngoài?
24. Có benchmark thực trước khi coi socket options là tối ưu hiệu năng?
25. Có test trên JDK/OS/provider/network interfaces được triển khai?

## 23. Tự kiểm tra kiến thức

**1.** NetworkChannel có nhiệm vụ chính gì?  
**Đáp án:** Bind địa chỉ local và quản lý socket options.

**2.** `SocketOption<Boolean>` có thể được set bằng một Integer không?  
**Đáp án:** Không, generic type ngăn sai kiểu.

**3.** `SO_RCVBUF` nhận loại giá trị gì?  
**Đáp án:** `Integer` với đơn vị byte, thường phải dương.

**4.** `getOption(SO_RCVBUF)` có chắc đúng bằng giá trị request?  
**Đáp án:** Không, OS có thể điều chỉnh.

**5.** Gọi `NetworkChannel.bind(null)` có tương đương bind loopback không?  
**Đáp án:** Không, có thể bind wildcard address.

**6.** Port 0 trong bind nghĩa gì?  
**Đáp án:** Nhờ OS cấp port rảnh; lấy cổng qua getLocalAddress.

**7.** `TCP_NODELAY` thuộc TCP listener hay connection?  
**Đáp án:** TCP connection, không phải ServerSocketChannel listener.

**8.** `SO_KEEPALIVE` có tự cung cấp authentication không?  
**Đáp án:** Không, đó là TCP probe mechanism.

**9.** Khi nào cần kiểm tra supportedOptions?  
**Đáp án:** Khi đặt option có thể không được hỗ trợ bởi channel/OS/provider.

**10.** `SO_REUSEPORT` có chắc được hỗ trợ vì đang dùng Java 17?  
**Đáp án:** Không; cần xem supportedOptions.

**11.** Multicast TTL=1 có nghĩa một giây không?  
**Đáp án:** Không, đó là TTL/hop limit.

**12.** Multicast TTL=256 có hợp lệ không?  
**Đáp án:** Không, giá trị hợp lệ từ 0 tới 255.

**13.** `IP_MULTICAST_LOOP=true` làm gì?  
**Đáp án:** Bật multicast loopback theo option hiện đại.

**14.** `IP_MULTICAST_IF` có kiểu gì?  
**Đáp án:** `NetworkInterface`.

**15.** Multicast receiver có nên chọn protocol family khớp group?  
**Đáp án:** Có, theo khuyến nghị của MulticastChannel Javadoc.

**16.** `SO_BROADCAST` có nghĩa join một multicast group?  
**Đáp án:** Không.

**17.** getOption trên channel đã đóng có thể ném gì?  
**Đáp án:** `ClosedChannelException`.

**18.** supportedOptions còn dùng được sau close không?  
**Đáp án:** Javadoc NetworkChannel quy định vẫn trả danh sách hỗ trợ.

**19.** Socket options có thay TLS không?  
**Đáp án:** Không.

**20.** Muốn gửi/nhận UDP, gọi read/write trên NetworkChannel interface được không?  
**Đáp án:** Không. Dùng DatagramChannel và các method tương ứng.

**21.** Vì sao một setting đúng kiểu vẫn có thể lỗi lúc chạy?  
**Đáp án:** Giá trị ngoài khoảng, option unsupported hoặc OS/I/O failure.

**22.** Điều nên làm với code mới thay cho MulticastSocket.setLoopbackMode?  
**Đáp án:** Dùng StandardSocketOptions.IP_MULTICAST_LOOP trên API socket/channel hiện đại.

**23.** Vì sao trong ví dụ UDP loopback có deadline khi receive?  
**Đáp án:** Nonblocking receive có thể trả null; deadline tránh chờ vô hạn.

**24.** TCP_NODELAY=true có loại bỏ TCP stream semantics không?  
**Đáp án:** Không; TCP vẫn là byte stream, phải có protocol framing.

**25.** Điểm trọng tâm nhất?  
**Đáp án:** Cấu hình network channel theo **loại socket, option có kiểu, khả năng hỗ trợ thực tế và vòng đời**, không áp dụng một danh sách cờ cho mọi channel.

## 24. Nguồn chính thức

- [Oracle Java SE 26 — NetworkChannel](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/NetworkChannel.html): bind, getLocalAddress, setOption/getOption/supportedOptions và exceptions.
- [Oracle Java SE 26 — SocketOption](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/SocketOption.html): kiểu generic T, name() và type().
- [Oracle Java SE 26 — StandardSocketOptions](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/StandardSocketOptions.html): bộ options chuẩn và các ràng buộc.
- [Oracle Java SE 26 — DatagramChannel](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/DatagramChannel.html): UDP, send/receive, option support, multicast.
- [Oracle Java SE 26 — MulticastChannel](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/MulticastChannel.html): join, NetworkInterface, protocol family và wildcard bind.
- [Oracle Java SE 26 — MembershipKey](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/MembershipKey.html): drop membership.
- [Oracle Java SE 26 — SocketChannel](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/SocketChannel.html): TCP connection options.
- [Oracle Java SE 26 — ServerSocketChannel](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/ServerSocketChannel.html): TCP listener options.
- [Oracle Java SE 26 — AsynchronousSocketChannel](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/AsynchronousSocketChannel.html): asynchronous TCP connection options.
- [Oracle Java SE 26 — AsynchronousServerSocketChannel](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/AsynchronousServerSocketChannel.html): asynchronous listener options.
- [Oracle Java SE 26 — NetworkInterface](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/NetworkInterface.html): multicast support và network interface state.
- [Oracle Java SE 26 — StandardProtocolFamily](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/StandardProtocolFamily.html): INET/INET6.
- [Oracle Java SE 26 — ClosedChannelException](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/ClosedChannelException.html): lỗi channel đã đóng.
- [Oracle Java SE 26 — jdk.net.Sockets](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.net/jdk/net/Sockets.html): deprecated, không dùng làm API chính.
- [Oracle Java SE 26 — MulticastSocket](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/MulticastSocket.html): giải thích vì sao tránh setLoopbackMode deprecated.
- [Oracle Java SE 17 — NetworkChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/NetworkChannel.html): đối chiếu API Java 17 chạy ví dụ.
- [Oracle Java SE 7 — NetworkChannel](https://docs.oracle.com/javase/7/docs/api/java/nio/channels/NetworkChannel.html): xác nhận API đã có từ Java 7.

**Tóm tắt:** `NetworkChannel` là interface cấu hình mạng qua `bind/getLocalAddress/setOption/getOption/supportedOptions`. `SocketOption<T>` cung cấp **type safety**; `StandardSocketOptions` cung cấp các option hiện hành. Mỗi loại TCP/UDP channel có tập hỗ trợ khác nhau; OS có thể điều chỉnh kết quả, nhất là buffer hints. Multicast cần đúng NetworkInterface, protocol family, TTL, loopback và MembershipKey. Các cờ socket **không thay bảo mật, TLS hay kiểm thử mạng thực tế**.