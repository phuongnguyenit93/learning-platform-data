# Quan hệ giữa họ giao thức với địa chỉ bind, connect (UDP, Java 15+)

## 1. Ba câu hỏi khác nhau: socket thuộc họ nào, nghe ở đâu, trao đổi với ai?

Khi tạo UDP channel trong Java, ta cần tách **ba quyết định**:

1. **Protocol family** (*họ giao thức*): channel làm việc với kiểu địa chỉ IP nào, ví dụ IPv4 hay IPv6?
2. **bind(local)**: socket chiếm **địa chỉ IP cục bộ và cổng cục bộ** nào để nhận/gửi datagram?
3. **connect(remote)**: socket UDP chỉ trao đổi datagram với **địa chỉ IP và cổng của peer** nào?

Ba khái niệm này liên quan nhưng **không thay thế nhau**.

~~~text
DatagramChannel.open(StandardProtocolFamily.INET)
           |                 |
           |                 +-- socket thuoc ho IPv4
           v
bind(127.0.0.1:portA)            <-- endpoint CUC BO
           |
connect(127.0.0.1:portB)         <-- endpoint REMOTE
           |
write(...) / read(...)           <-- peer da duoc chon
           |
disconnect()
           |
send(buffer, remote) / receive(buffer)  <-- khong con peer co dinh
~~~

Nếu một chương trình chọn `INET` nhưng tìm cách bind vào một địa chỉ IPv6 không phù hợp, thao tác sẽ không trở thành IPv6 chỉ vì đã gọi `bind`. Tương tự, `connect` tới một peer không làm thay đổi họ giao thức đã dùng để tạo channel.

**Ý chính:** họ giao thức quyết định **khả năng biểu diễn/giao tiếp của socket**, `bind` quyết định **đầu cục bộ**, còn `connect` quyết định **đầu xa**. Ứng dụng cần chọn chúng tương thích với nhau và với cấu hình mạng thật.

API trong bài đã được Java hỗ trợ từ trước Java 15 và **vẫn hiện hành** trong các JDK mới. Java 15 không phải phiên bản đầu tiên có `DatagramChannel`.

## 2. ProtocolFamily và StandardProtocolFamily

Trong Java:

~~~java
import java.net.ProtocolFamily;
import java.net.StandardProtocolFamily;
import java.nio.channels.DatagramChannel;
~~~

`ProtocolFamily` là interface mô tả họ giao thức; `StandardProtocolFamily` là enum chứa các họ tiêu chuẩn.

Với UDP trên Internet, hai giá trị quan trọng là:

| Hằng | Ý nghĩa | Ví dụ địa chỉ |
| --- | --- | --- |
| `StandardProtocolFamily.INET` | Họ **IPv4**. | `127.0.0.1`, `192.0.2.10`, `0.0.0.0`. |
| `StandardProtocolFamily.INET6` | Họ **IPv6**. | `::1`, `2001:db8::10`, `::`. |

Tạo UDP channel một cách tường minh:

~~~java
try (DatagramChannel ipv4 =
             DatagramChannel.open(StandardProtocolFamily.INET);
     DatagramChannel ipv6 =
             DatagramChannel.open(StandardProtocolFamily.INET6)) {
    // Thiet lap bind/connect phu hop.
}
~~~

Đoạn này là **minh họa API**, không phải ví dụ portability: `INET6` có thể **không được hỗ trợ** trên một số nền tảng/cấu hình, khiến `open(INET6)` ném `UnsupportedOperationException`. Trong dự án thật, hãy kiểm tra và có nhánh xử lý thích hợp.

### 2.1. `DatagramChannel.open()` khác `open(family)` thế nào?

Hai lựa chọn:

~~~java
DatagramChannel defaultChannel = DatagramChannel.open();
DatagramChannel ipv4Channel =
        DatagramChannel.open(StandardProtocolFamily.INET);
~~~

- `open()` **không cam kết rõ** họ giao thức; họ thực tế do nền tảng và cấu hình JVM quyết định. Đừng tự kết luận `open()` luôn là IPv4 hoặc luôn dual-stack.
- `open(INET)` **yêu cầu họ IPv4**.
- `open(INET6)` **yêu cầu họ IPv6** nếu nền tảng hỗ trợ.

Chọn explicit family khi chương trình có **yêu cầu giao thức rõ ràng**, chẳng hạn cần chắc chắn chạy với IPv4 hoặc cần join nhóm multicast có loại địa chỉ xác định.

Đặc biệt với **IP multicast**, tài liệu `DatagramChannel.open(ProtocolFamily)` khuyến nghị họ giao thức tương ứng với **địa chỉ nhóm multicast** dự định join. Không chọn `INET` rồi kỳ vọng join một nhóm IPv6 chỉ vì đã chọn network interface phù hợp.

### 2.2. Họ giao thức khác kiểu thao tác truyền

`INET` và `INET6` không có nghĩa blocking hoặc non-blocking:

~~~java
DatagramChannel channel =
        DatagramChannel.open(StandardProtocolFamily.INET);

System.out.println(channel.isBlocking()); // true
channel.configureBlocking(false);
System.out.println(channel.isBlocking()); // false
~~~

Một UDP channel mới mặc định ở **blocking mode**, bất kể họ địa chỉ. `configureBlocking(false)` là quyết định I/O **độc lập** với `bind`, `connect` và IP family.

Hai thao tác `receive/send` có thể dùng cả khi channel **chưa connected**. Hai thao tác `read/write` của `DatagramChannel` cần channel **connected**, vì chúng không nhận tham số địa chỉ đích và không trả địa chỉ nguồn.

## 3. Địa chỉ thực sự truyền cho bind và connect là gì?

`DatagramChannel.bind` và `DatagramChannel.connect` nhận `java.net.SocketAddress`. Với UDP/IP, kiểu quen thuộc là `java.net.InetSocketAddress` gồm:

- `InetAddress`: địa chỉ IP.
- `int port`: cổng TCP/UDP, với UDP là cổng của socket UDP.

Ví dụ hai kiểu địa chỉ:

~~~java
import java.net.InetAddress;
import java.net.InetSocketAddress;

InetAddress ipv4 = InetAddress.getByName("127.0.0.1");
InetAddress ipv6 = InetAddress.getByName("::1");

InetSocketAddress local4 = new InetSocketAddress(ipv4, 0);
InetSocketAddress peer6 = new InetSocketAddress(ipv6, 9000);
~~~

**`127.0.0.1` là loopback IPv4**, còn **`::1` là loopback IPv6**. Chúng đều mang ý nghĩa “máy của chính mình” nhưng là **địa chỉ của hai họ khác nhau**. Không được coi chúng là hai cách viết có thể hoán đổi trong mọi socket.

Với `InetSocketAddress`:

~~~java
InetSocketAddress endpoint = ...;
InetAddress address = endpoint.getAddress();
int port = endpoint.getPort();
~~~

Đoạn trên là minh họa với biến `endpoint` đã tồn tại, không phải chương trình độc lập. Đối tượng có thể **unresolved** nếu tạo từ hostname chưa phân giải; khi đó `getAddress()` có thể là `null` và NIO `connect` có thể ném `UnresolvedAddressException`. Khi muốn kiểm soát họ IP, hãy phân giải và chọn một địa chỉ cụ thể theo policy, không dựa vào tên hostname chung chung.

### 3.1. Vì sao `localhost` dễ gây nhầm?

`InetAddress.getByName("localhost")` có thể trả IPv4 hoặc IPv6 tùy máy, DNS/hosts file và cấu hình JVM. Nếu mở channel `INET` rồi bind/connect với một địa chỉ được phân giải thành `::1`, sự kết hợp có thể không được hỗ trợ.

Đối với ví dụ học tập, nên dùng literal để tránh suy đoán:

~~~java
InetAddress loopback4 = InetAddress.getByName("127.0.0.1");
InetAddress loopback6 = InetAddress.getByName("::1");
~~~

Trong dịch vụ production, thường cần chiến lược lựa chọn endpoint từ DNS A/AAAA, có xử lý kết nối thất bại và giám sát. Không ép mọi hostname về địa chỉ đầu tiên khi ứng dụng cần IPv4 hoặc IPv6 cụ thể.

### 3.2. `Inet4Address` và `Inet6Address`

Sau khi phân giải, có thể kiểm tra kiểu:

~~~java
boolean v4 = loopback4 instanceof java.net.Inet4Address;
boolean v6 = loopback6 instanceof java.net.Inet6Address;
~~~

Cách này giúp kiểm tra địa chỉ dự kiến, nhưng không thay cho việc thử `bind/connect` trong môi trường thật. Một địa chỉ thuộc họ đúng vẫn có thể **không được cấu hình trên máy** hoặc **không thể định tuyến** tới peer.

Đối với IPv6 link-local (`fe80::/10`), **scope ID hoặc network interface** thường cần thiết để xác định một địa chỉ trong môi trường nhiều interface. Ví dụ ký hiệu địa chỉ có zone `fe80::...%eth0` là khái niệm scope-dependent; tên interface thực tế tùy máy. Không hard-code tên interface trên production hoặc bỏ qua scope khi kết nối IPv6 link-local.

## 4. `bind(local)` xác định endpoint cục bộ

`DatagramChannel.bind(SocketAddress local)` gắn channel với **địa chỉ/cổng ở máy đang chạy**.

~~~java
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.StandardProtocolFamily;
import java.nio.channels.DatagramChannel;

InetAddress loopback4 = InetAddress.getByName("127.0.0.1");

try (DatagramChannel server =
             DatagramChannel.open(StandardProtocolFamily.INET)) {
    server.bind(new InetSocketAddress(loopback4, 9000));
    System.out.println(server.getLocalAddress());
}
~~~

Nếu socket bind được `127.0.0.1:9000`, nó nghe datagram đến địa chỉ loopback IPv4 ở cổng 9000. Máy khác **không thể dùng loopback của chính máy đó** để truy cập server này. Bind một địa chỉ loopback phù hợp cho test, còn dịch vụ muốn nhận từ mạng bên ngoài thường bind tới địa chỉ interface cụ thể hoặc wildcard theo policy firewall và topology.

**Quan trọng:** `bind(local)` không chọn peer. Server UDP có thể nhận datagram từ nhiều nguồn nếu chưa `connect`.

### 4.1. Cổng `0` nghĩa là gì?

~~~java
server.bind(new InetSocketAddress(loopback4, 0));
~~~

`port=0` yêu cầu OS chọn **ephemeral local port** đang khả dụng. Sau khi bind, đọc cổng thực tế qua:

~~~java
InetSocketAddress actual =
        (InetSocketAddress) server.getLocalAddress();
int actualPort = actual.getPort();
~~~

Đây là lựa chọn hợp lý cho test tự chạy trên một máy, vì không phụ thuộc cổng cố định có thể đang bận.

**Đừng gửi datagram tới port 0 của peer.** Port 0 có ý nghĩa lựa chọn **cổng local trước bind**, không phải cổng dịch vụ thật mà client phải liên lạc. Sau bind, dùng port thực tế được hệ điều hành cấp.

### 4.2. Wildcard address: “mọi local interface phù hợp”

Đối với IPv4:

~~~java
try (DatagramChannel channel =
             DatagramChannel.open(StandardProtocolFamily.INET)) {
    channel.bind(new InetSocketAddress(0));
    InetSocketAddress actual =
            (InetSocketAddress) channel.getLocalAddress();
    System.out.println(actual.getAddress().isAnyLocalAddress());
}
~~~

`new InetSocketAddress(0)` biểu diễn wildcard local với port 0; trên IPv4 thường tương ứng `0.0.0.0`, còn IPv6 wildcard là `::` khi dùng họ IPv6 phù hợp.

**Wildcard không có nghĩa IP peer là 0.0.0.0.** Nó chỉ có nghĩa local socket lắng nghe trên những local addresses mà nền tảng/cấu hình cho phép, trong phạm vi protocol family tương ứng.

Về bảo mật: bind wildcard có thể làm dịch vụ **hiển thị trên nhiều interface hơn** so với bind loopback. Không suy ra firewall sẽ bảo vệ đúng; cần kiểm tra rules, interface và network namespace/container.

### 4.3. `bind(null)` và automatic binding

~~~java
channel.bind(null);
~~~

Theo hợp đồng `DatagramChannel.bind`, `null` có nghĩa **địa chỉ local được hệ thống tự gán**. Ngoài ra, nếu channel chưa bind mà gọi `connect` hoặc `send/receive` thích hợp, hệ thống có thể **tự bind** nó như gọi `bind(null)`.

Điều đó hữu ích cho UDP client không cần chỉ định cổng local:

~~~java
try (DatagramChannel client =
             DatagramChannel.open(StandardProtocolFamily.INET)) {
    client.connect(new InetSocketAddress("127.0.0.1", 9000));
    System.out.println(client.getLocalAddress() != null);
}
~~~

Đây là ví dụ minh họa không cần server đang lắng nghe để hoàn tất UDP `connect`, tuy nhiên vẫn cần OS/network cho phép socket liên quan. `connect` không đợi peer trả lời bằng handshake kiểu TCP.

### 4.4. Bind sai họ địa chỉ hoặc local IP không tồn tại

Một channel IPv4 mở bằng `INET` phải được sử dụng với **endpoint IPv4 phù hợp**. Bind địa chỉ IPv6 như `::1` vào channel chỉ có IPv4 không phải cách hợp lệ để “nâng cấp” channel. Provider có thể báo lỗi địa chỉ không hỗ trợ hoặc `IOException`.

Một địa chỉ thuộc họ đúng **vẫn chưa đủ**: bind một IP không được gán cho máy/interface thường dẫn tới lỗi hệ điều hành như `BindException`; bind port đã bị chiếm cũng có thể thất bại tùy tùy chọn socket và hệ điều hành.

**Sau khi bind thành công, channel vẫn bound đến khi đóng.** Gọi `bind` lần nữa trên cùng channel đã bound có thể ném `AlreadyBoundException`. `disconnect` **không phải** cách unbind socket để bind lại ở địa chỉ/cổng mới.

## 5. `connect(remote)` trên UDP: gắn peer, không làm TCP handshake

`DatagramChannel.connect(SocketAddress remote)` thiết lập **peer mặc định** cho UDP channel:

~~~java
channel.connect(new InetSocketAddress("127.0.0.1", 9000));
~~~

Khác TCP:

- Không có ba bước bắt tay TCP.
- Không bảo đảm remote host/port thật sự có service hoặc sẵn sàng nhận.
- Không tạo giao thức bảo đảm delivery, ordering hoặc retransmission.
- Không tự mã hóa hay xác thực remote.
- Việc gửi/nhận vẫn là **datagram UDP**.

Sau `connect` thành công, channel chỉ nhận datagram từ **remote peer đã chọn** và gửi tới peer đó. Datagram đã tồn trong receive buffer trước `connect` có thể bị bỏ. `getRemoteAddress()` trả peer và `isConnected()` trả `true`.

### 5.1. `connect` không tự đổi protocol family

Ví dụ:

~~~java
DatagramChannel channel =
        DatagramChannel.open(StandardProtocolFamily.INET);
~~~

Channel được tạo cho IPv4. Nếu gọi `connect` với địa chỉ IPv6 không phù hợp, thao tác đó không đổi channel thành IPv6; phải chọn family phù hợp từ lúc mở, hoặc dùng cơ chế dual-stack mà nền tảng hỗ trợ đúng cách.

Khi dùng `INET6`, **một số hệ thống có cơ chế dual-stack/IPv4-mapped addresses**, nhưng **không có lời hứa di động rằng mọi IPv6 socket đều giao tiếp được với mọi IPv4 peer**. Phụ thuộc OS, JVM config, provider và network environment. Nếu ứng dụng cần hoạt động trên cả hai họ, nên kiểm thử thực tế hoặc mở **hai channel riêng** cho IPv4/IPv6.

**Không dựa vào `DatagramChannel.open()` không tham số để mặc định luôn dual-stack**: chính JavaDoc nói family trong trường hợp này có thể khác theo nền tảng/cấu hình.

### 5.2. `read/write` chỉ dùng khi connected

Khi chưa `connect`:

~~~java
channel.send(buffer, target); // Chi ro dia chi dich.
channel.receive(buffer);      // Tra dia chi nguon khi nhan.
~~~

Khi đã `connect`:

~~~java
channel.write(buffer); // Gui den peer da ket noi.
channel.read(buffer);  // Nhan tu peer da ket noi.
~~~

Với `DatagramChannel`:

- `send(src, target)` chỉ định đích mỗi lần gửi.
- `receive(dst)` trả `SocketAddress` nguồn của datagram (hoặc `null` ở non-blocking khi chưa có datagram).
- `write(src)` dùng remote mặc định của channel và trả số byte gửi.
- `read(dst)` đọc datagram từ peer mặc định và trả số byte nhận.

Nếu gọi `read/write` trên channel **chưa connected**, có thể gặp `NotYetConnectedException`. Nếu channel đã connected tới peer A mà cố `send` tới peer B, có thể ném `AlreadyConnectedException`. Đừng chuyển đổi giữa các API này mà không kiểm tra trạng thái.

**Kết nối UDP không mở ra một “dòng byte TCP”**: `read/write` vẫn hoạt động trên datagram; buffer nhỏ có thể làm phần dư datagram bị cắt. Số byte từ `write` không phải ACK của peer.

### 5.3. `connect` tự bind nếu channel chưa bound

Trên một UDP client mới tạo:

~~~java
try (DatagramChannel c =
             DatagramChannel.open(StandardProtocolFamily.INET)) {
    System.out.println(c.getLocalAddress() == null); // true

    c.connect(new InetSocketAddress("127.0.0.1", 9000));

    System.out.println(c.getLocalAddress() != null); // true
    System.out.println(c.getRemoteAddress() != null); // true
}
~~~

Nói cách khác, **local endpoint** và **remote endpoint** là hai thông tin khác nhau. `connect` khi cần có thể giúp hệ thống tự chọn local port/địa chỉ cho client. Nó không “bind vào địa chỉ remote”: local và remote luôn là hai đầu khác nhau.

`getLocalAddress()` có thể phản ánh địa chỉ nguồn được OS chọn sau `connect` nếu ban đầu bind wildcard. Không nên cố định assumptions rằng nó **luôn** tiếp tục in `0.0.0.0` hoặc `::` sau connect trên mọi hệ thống.

### 5.4. `disconnect` bỏ peer nhưng không bỏ bind

`DatagramChannel.disconnect()` xóa trạng thái connected:

~~~java
channel.disconnect();
System.out.println(channel.isConnected()); // false
System.out.println(channel.getRemoteAddress()); // null
~~~

Sau `disconnect` thành công:

- Channel vẫn mở, vẫn bound ở local endpoint (không tự unbind).
- Có thể dùng `send(dst, target)` và `receive(dst)` cho datagram từ các peer thích hợp.
- `read/write` không còn phù hợp nếu chưa `connect` lại.
- Muốn đổi local binding phải tạo channel/socket mới theo thiết kế, không gọi `bind` lần hai trên channel vẫn bound.

Nếu `disconnect` ném `IOException`, JavaDoc lưu ý trạng thái socket có thể **không xác định**, nên **đóng channel** thay vì cố tiếp tục sử dụng và giả định đã an toàn.

## 6. Quan hệ family ↔ bind ↔ connect: bảng quyết định

| Cấu hình channel | Địa chỉ `bind` | Địa chỉ `connect` | Nhận định |
| --- | --- | --- | --- |
| `open(INET)` | `127.0.0.1:port` | `127.0.0.1:peerPort` | **Hợp lý** để thử UDP IPv4 loopback trên cùng máy. |
| `open(INET)` | IPv4 wildcard `0.0.0.0:port` | IPv4 peer | **Hợp lý** nếu cần một local IPv4 socket phục vụ nhiều interface phù hợp. |
| `open(INET6)` | `[::1]:port` | `[::1]:peerPort` | **Hợp lý khi IPv6 khả dụng**. |
| `open(INET)` | `[::1]:port` | IPv6 peer | **Không tương thích với socket chỉ IPv4**; không thể đổi family bằng bind/connect. |
| `open(INET6)` | `[::]:port` | IPv4 peer | **Phụ thuộc dual-stack/OS/JVM**; không mặc định khả dụng. |
| `open()` | Không chỉ định | Peer bất kỳ | Family của socket **không được Java bảo đảm cố định**; cần kiểm thử/chọn family rõ nếu quan trọng. |
| `open(INET)` | Không bind trước | IPv4 peer | `connect` có thể **tự bind** local port/địa chỉ. |
| `open(INET6)` | IPv6 link-local | IPv6 link-local cùng mạng | Cần **scope/interface/route** phù hợp; chỉ đúng kiểu địa chỉ chưa đủ. |

Bảng minh họa quan hệ **về mặt thiết kế**, không bảo đảm packet đến hoặc các lệnh thành công trong mọi môi trường. Firewall, IP routing, port usage, interface và provider vẫn ảnh hưởng.

### 6.1. Địa chỉ wildcard không phải địa chỉ remote

`0.0.0.0` và `::` biểu diễn **địa chỉ local unspecified/wildcard** khi bind. Chúng không phải đích ứng dụng nên dùng để connect tới dịch vụ thực.

Cần phân biệt:

~~~text
Server bind: 0.0.0.0:9000
Client connect: 192.0.2.10:9000    (IP cu the cua may server)
~~~

Server có thể bind wildcard để nghe trên nhiều local interface; **client vẫn phải chọn một remote IP có thể định tuyến tới server**.

### 6.2. IPv6 link-local và zone ID

Một địa chỉ IPv6 link-local như `fe80::...` chỉ có ý nghĩa trong phạm vi link. Trên máy có nhiều network interface, thiếu scope có thể khiến OS không biết đi qua interface nào. Java cung cấp `Inet6Address` với scope ID hoặc interface theo API phù hợp.

Khi debug, ghi lại **địa chỉ, port và scope** mà ứng dụng thực sự sử dụng, nhưng tránh phụ thuộc tên interface ví dụ trong tài liệu hoặc môi trường người khác.

### 6.3. Tên miền với nhiều A/AAAA records

Tên miền có thể phân giải cả địa chỉ IPv4 và IPv6. Hệ thống phải có chính sách:

1. Chọn thứ tự thử IP addresses phù hợp.
2. Mở channel có family tương ứng khi cần.
3. Bind local IP thích hợp với family đó.
4. Thử remote cụ thể và xử lý lỗi.
5. Không chuyển đổi từ `Inet4Address` sang `Inet6Address` chỉ bằng cách cast.

Đừng dùng kiểu `InetAddress.getByName(host)` rồi mặc định host luôn trả cùng họ giữa các máy/JDK.

## 7. Chương trình Java đầy đủ: INET, bind, connect, disconnect, INET6

Ví dụ sử dụng **loopback** để kiểm tra mà không cần server bên ngoài. Nó:

1. Mở **hai UDP channels IPv4 bằng `INET`**.
2. Bind cả hai vào `127.0.0.1` với cổng **0** để OS cấp ephemeral port.
3. Kết nối peer hai chiều, dùng `write/read` cho datagram.
4. `disconnect` receiver rồi nhận datagram bằng `receive`, kiểm tra địa chỉ nguồn.
5. Tạo channel IPv4 **wildcard**, kiểm tra cổng tự chọn.
6. Thử tạo channel **INET6** và bind vào `::1`, nhưng báo `unavailable` nếu môi trường không hỗ trợ.

### 7.1. File `UdpProtocolFamilyDemo.java`

~~~java
import java.io.IOException;
import java.net.Inet4Address;
import java.net.Inet6Address;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.SocketAddress;
import java.net.StandardProtocolFamily;
import java.nio.ByteBuffer;
import java.nio.channels.DatagramChannel;
import java.nio.channels.UnsupportedAddressTypeException;
import java.nio.charset.StandardCharsets;

public class UdpProtocolFamilyDemo {
    private static void ipv4Demo() throws IOException {
        InetAddress loopback = InetAddress.getByName("127.0.0.1");

        try (DatagramChannel receiver =
                     DatagramChannel.open(StandardProtocolFamily.INET);
             DatagramChannel sender =
                     DatagramChannel.open(StandardProtocolFamily.INET)) {
            receiver.bind(new InetSocketAddress(loopback, 0));
            sender.bind(new InetSocketAddress(loopback, 0));

            InetSocketAddress local =
                    (InetSocketAddress) receiver.getLocalAddress();
            InetSocketAddress peer =
                    (InetSocketAddress) sender.getLocalAddress();

            System.out.println("ipv4Bound=" +
                    (local.getAddress() instanceof Inet4Address));
            System.out.println("beforeConnect=" + receiver.isConnected());

            receiver.connect(peer);
            sender.connect(local);

            System.out.println("afterConnect=" + receiver.isConnected());
            System.out.println("remoteMatchesPeer=" +
                    receiver.getRemoteAddress().equals(peer));

            sender.write(ByteBuffer.wrap(
                    "hello".getBytes(StandardCharsets.UTF_8)));
            ByteBuffer buffer = ByteBuffer.allocate(128);
            int bytesRead = receiver.read(buffer);
            buffer.flip();
            System.out.println("connectedBytes=" + bytesRead);
            System.out.println("connectedPayload=" +
                    StandardCharsets.UTF_8.decode(buffer));

            receiver.disconnect();
            System.out.println("afterDisconnect=" + receiver.isConnected());

            sender.write(ByteBuffer.wrap(
                    "again".getBytes(StandardCharsets.UTF_8)));
            buffer.clear();
            SocketAddress source = receiver.receive(buffer);
            buffer.flip();
            System.out.println("sourceMatchesPeer=" + peer.equals(source));
            System.out.println("unconnectedPayload=" +
                    StandardCharsets.UTF_8.decode(buffer));
        }
    }

    private static void wildcardDemo() throws IOException {
        try (DatagramChannel channel =
                     DatagramChannel.open(StandardProtocolFamily.INET)) {
            channel.bind(new InetSocketAddress(0));
            InetSocketAddress local =
                    (InetSocketAddress) channel.getLocalAddress();
            System.out.println("wildcardBound=" +
                    local.getAddress().isAnyLocalAddress());
            System.out.println("ephemeralPort=" + (local.getPort() > 0));
        }
    }

    private static void ipv6Demo() {
        try (DatagramChannel channel =
                     DatagramChannel.open(StandardProtocolFamily.INET6)) {
            InetAddress loopback6 = InetAddress.getByName("::1");
            channel.bind(new InetSocketAddress(loopback6, 0));
            InetSocketAddress local =
                    (InetSocketAddress) channel.getLocalAddress();
            System.out.println("ipv6Bound=" +
                    (local.getAddress() instanceof Inet6Address));
        } catch (IOException | UnsupportedOperationException |
                 UnsupportedAddressTypeException unavailable) {
            System.out.println("ipv6Bound=unavailable");
        }
    }

    public static void main(String[] args) throws IOException {
        ipv4Demo();
        wildcardDemo();
        ipv6Demo();
    }
}
~~~

### 7.2. Biên dịch và chạy

Lưu đúng tên file, chạy từ thư mục chứa file bằng JDK hỗ trợ các API Java 15:

~~~bash
javac --release 15 -encoding UTF-8 UdpProtocolFamilyDemo.java
java UdpProtocolFamilyDemo
~~~

`--release 15` yêu cầu compiler kiểm tra API/ngôn ngữ trong phạm vi Java 15, kể cả khi người học đang sử dụng JDK mới hơn.

**Đầu ra đã kiểm tra thực tế trên JDK 24:**

~~~text
ipv4Bound=true
beforeConnect=false
afterConnect=true
remoteMatchesPeer=true
connectedBytes=5
connectedPayload=hello
afterDisconnect=false
sourceMatchesPeer=true
unconnectedPayload=again
wildcardBound=true
ephemeralPort=true
ipv6Bound=true
~~~

**Giải thích:**

- `ipv4Bound=true`: channel mở bằng `INET` và bind thành công vào IPv4 loopback.
- `beforeConnect=false`: channel UDP mới **không connected** mặc định, dù đã bind.
- `afterConnect=true`: `connect(peer)` thiết lập remote peer cho channel.
- `remoteMatchesPeer=true`: `getRemoteAddress()` trùng endpoint của sender.
- `connectedBytes=5`, `connectedPayload=hello`: `write/read` hoạt động khi cả hai channel đã connected tới nhau.
- `afterDisconnect=false`: receiver bỏ remote peer, **không bị đóng hay unbind**.
- `sourceMatchesPeer=true` và `unconnectedPayload=again`: sau disconnect, receiver dùng `receive(buffer)` và biết nguồn của datagram.
- `wildcardBound=true`: channel IPv4 bind với địa chỉ local wildcard.
- `ephemeralPort=true`: OS đã cấp cổng local > 0 khi bind port 0.
- `ipv6Bound=true`: máy kiểm thử có thể tạo `INET6` channel và bind vào IPv6 loopback.

Dòng cuối **có thể là `ipv6Bound=unavailable`** nếu máy không bật/sử dụng được IPv6. Khả năng hoạt động của IPv6 không được suy ra chỉ từ việc Java có enum `INET6`.

**Caveat quan trọng:** UDP không bảo đảm datagram đến, nên trong một môi trường loopback bất thường, `read/receive` ở blocking mode có thể chờ khi datagram mất hoặc bị chặn. Mẫu trên cho kết quả đã ghi trong môi trường kiểm thử; hệ thống thật cần deadline/timeout (ví dụ channel không chặn kết hợp `Selector`), xử lý lỗi và cơ chế ứng dụng phù hợp.

## 8. `bind` và `connect` không tự làm UDP trở thành TCP

Sử dụng `connect` trên UDP giúp giảm việc truyền địa chỉ đích khi gửi nhiều datagram tới một peer và có thể giảm một số kiểm tra mỗi lần gửi/nhận. Tuy nhiên:

- Không có **TCP handshake**, stream, retransmission hay bảo đảm thứ tự.
- `write` chỉ báo **số byte đã gửi xuống tầng hệ thống**, không bảo đảm peer nhận.
- `read` nhận datagram từ peer đã chọn; không ghép nhiều datagram thành TCP stream.
- Packet từ peer khác thường bị lọc khi channel connected; không coi đây là chứng thực mật mã.
- Một endpoint có thể có cùng IP nhưng port khác: `connect` ràng buộc theo **IP và port** phù hợp.
- Nếu remote không phản hồi, `connect` có thể vẫn thành công. Các lỗi đích không truy cập được có thể xuất hiện **sau này** khi gửi/nhận, và không có bảo đảm OS luôn phát hiện.

Không dùng `isConnected()==true` như tín hiệu “dịch vụ bên kia đang hoạt động”. Trạng thái đó chỉ nói **channel đã chọn một peer**, không xác minh remote có tồn tại, còn sống hay đáng tin.

### 8.1. Bảo mật: địa chỉ không phải danh tính

UDP source IP/port có thể bị giả mạo trong những topology nhất định. `DatagramChannel.connect` lọc nhận theo peer, nhưng **không xác minh danh tính bằng mật mã** và không ngăn mọi kiểu giả mạo nguồn.

Nếu datagram mang lệnh nhạy cảm, hãy dùng cơ chế bảo mật phù hợp: xác thực thông điệp, encryption/integrity khi cần, nonce/replay protection và phân quyền. Không dựa riêng vào `connect` hay bind local loopback để tuyên bố ứng dụng đã an toàn trong mọi bối cảnh triển khai.

## 9. Những lỗi và ngoại lệ thường gặp

| Trường hợp | Hành vi / exception có thể gặp | Hướng xử lý |
| --- | --- | --- |
| `open(INET6)` trên platform tắt IPv6 | `UnsupportedOperationException` hoặc lỗi môi trường khác | Phát hiện hỗ trợ, fallback có chủ đích sang IPv4 hoặc báo cấu hình không tương thích. |
| Bind IP không được gán cho local interface | `BindException` / `IOException` | Kiểm tra local IP, interface, container namespace và quyền hệ điều hành. |
| Bind port đã được chiếm hoặc bind lần hai | `BindException` / `AlreadyBoundException` | Chọn port khác hoặc tạo channel mới; hiểu socket options. |
| Đưa loại `SocketAddress` provider không hỗ trợ | `UnsupportedAddressTypeException` | Dùng `InetSocketAddress` hợp lệ cho UDP/IP. |
| Remote hostname chưa phân giải | `UnresolvedAddressException` | Phân giải/chọn địa chỉ trước khi connect. |
| Gọi `connect` lần nữa khi đang connected | `AlreadyConnectedException` | `disconnect` nếu muốn chuyển peer, rồi `connect` theo policy; xử lý mọi lỗi. |
| Gọi `read/write` trước khi connect | `NotYetConnectedException` | `connect` trước hoặc dùng `receive/send`. |
| `send` tới peer khác khi đang connected | `AlreadyConnectedException` | Chỉ gửi tới remote đã connect; hoặc disconnect rồi cấu hình lại. |
| Connect tới IP/port không có service | `connect` UDP vẫn có thể thành công | Đừng dùng thành công của `connect` làm health check; kiểm tra response/protocol. |
| Binding IPv4 với IPv6 địa chỉ không phù hợp | Lỗi loại địa chỉ/`IOException` tùy provider | Chọn family và endpoint tương thích, không giả định dual-stack. |
| Gửi tới địa chỉ IPv6 link-local thiếu scope | Lỗi route/interface | Chọn `Inet6Address` có scope hoặc interface thích hợp. |
| Mở `open()` và đoán là IPv6 dual-stack | Hành vi thay đổi giữa môi trường | Mở `INET`/`INET6` rõ ràng, test trên deployment. |

**Không phải mọi lỗi mạng đều xuất hiện đúng khi `connect`.** Có trường hợp send/receive sau đó mới thất bại, hoặc datagram bị mất mà không có exception. Phải có timeout và kiểm tra response tầng ứng dụng.

### 9.1. Không tự giải quyết bằng cách đổi hostname thành “localhost”

Nếu bind IPv4 không thành công vì đã tạo địa chỉ `::1`, đổi host thành `localhost` không bảo đảm fix: hostname có thể lại phân giải IPv6. Thử explicit `127.0.0.1` cho IPv4 loopback hoặc `::1` cho IPv6 loopback rồi mở family tương ứng.

Nếu IP đúng family nhưng không thuộc máy, dù đổi port vẫn có thể không bind được. Nguyên nhân cần kiểm tra là **local interface/namespace**, không phải chỉ cú pháp Java.

## 10. Liên quan đến multicast và dual-stack

### 10.1. Multicast cần đúng họ giao thức

Với multicast, nhóm IPv4 và nhóm IPv6 là hai loại khác nhau. JavaDoc `DatagramChannel.open(ProtocolFamily)` khuyến nghị chọn family trùng với kiểu địa chỉ nhóm muốn join.

Ví dụ chỉ minh họa cấu hình family, không phải chương trình multicast hoàn chỉnh:

~~~java
try (DatagramChannel v4 =
             DatagramChannel.open(StandardProtocolFamily.INET);
     DatagramChannel v6 =
             DatagramChannel.open(StandardProtocolFamily.INET6)) {
    // v4 se duoc cau hinh join IPv4 multicast group.
    // v6 se duoc cau hinh join IPv6 multicast group.
}
~~~

Để thật sự join multicast, cần địa chỉ group hợp lệ, `NetworkInterface` được hỗ trợ, `channel.join(group, networkInterface)`, bind/port, socket options và kiểm tra IGMP/MLD/firewall/routing. Đừng coi chỉ mở family đúng là tự tham gia nhóm.

### 10.2. IPv6 dual-stack phụ thuộc nền tảng

Có những môi trường cho phép socket IPv6 giao tiếp với IPv4 thông qua dual-stack và các biểu diễn liên quan đến IPv4-mapped addresses. Nhưng không nên mặc định:

- Mọi OS bật dual-stack.
- `INET6` luôn chấp nhận IPv4 `InetSocketAddress`.
- Wildcard `::` trên IPv6 luôn bao phủ IPv4.
- Mọi JVM/provider cấu hình IPv6 như nhau.
- `java.net.preferIPv4Stack` và chính sách OS không ảnh hưởng hành vi.

Khi triển khai dịch vụ hỗ trợ cả hai họ, cách dễ dự đoán là **hai sockets/channels** được bind rõ ràng, đồng thời kiểm tra port reuse, OS dual-stack behavior và routing trên đúng hạ tầng. Nếu muốn dùng một dual-stack socket, phải có integration tests xác thực trong môi trường production.

### 10.3. Không nhầm với Unix domain sockets

Các JDK mới có hỗ trợ **Unix domain socket** cho một số API stream sockets, nhưng **`DatagramChannel.open(ProtocolFamily)` không hỗ trợ Unix-domain sockets** theo JavaDoc hiện đại. Đừng suy ra `StandardProtocolFamily.UNIX` ở phiên bản sau có thể thay `INET/INET6` cho UDP datagram channel; bài toán đang xét là **UDP trên IP**.

## 11. Checklist thiết kế trước khi bind/connect

Khi xây một UDP service/client Java:

1. **Bạn cần IPv4, IPv6 hay cả hai?** Chọn `StandardProtocolFamily` rõ ràng khi cần.
2. **Local endpoint nào thực sự tồn tại?** Xác định IP interface hoặc wildcard phù hợp, port cố định hay ephemeral.
3. **Server có phải nhận từ nhiều interface không?** Bind loopback và wildcard khác nhau về khả năng tiếp cận.
4. **Remote peer được chọn từ đâu?** DNS A/AAAA, địa chỉ literal, service discovery; có kiểm tra unresolved và family không?
5. **Có cần `connect` không?** Nếu gửi/nhận với nhiều peer, dùng `send/receive`; nếu một peer cố định, `connect` có thể đơn giản hơn.
6. **Cần blocking hay non-blocking?** Đây là lựa chọn riêng: `configureBlocking(false)` và `Selector` khi cần multiplex.
7. **Thời hạn chờ nhận là gì?** `connect` UDP không chứng minh peer sống; cần deadline/application ACK nếu nghiệp vụ yêu cầu.
8. **IPv6 link-local có scope đúng?** Kiểm tra interface, route và địa chỉ thực.
9. **Đa nền tảng có test dual-stack chưa?** Không dựa vào assumption mặc định của `open()` hay IPv6 wildcard.
10. **Có bảo vệ dữ liệu và xác thực peer không?** UDP `connect` không thay thế authentication, confidentiality hay chống replay.
11. **Tài nguyên có được đóng?** Dùng try-with-resources và xử lý socket/channel errors phù hợp.
12. **Có cần multicast?** Chọn family tương ứng nhóm multicast và network interface thực tế.

## 12. Bài tập tự kiểm tra

**Câu 1.** `DatagramChannel.open()` có chắc tạo IPv4 channel không?

**Đáp án:** Không. Family phụ thuộc nền tảng/cấu hình. Dùng `open(StandardProtocolFamily.INET)` nếu cần IPv4 rõ ràng.

**Câu 2.** `bind(new InetSocketAddress("127.0.0.1", 0))` có ý nghĩa gì?

**Đáp án:** Gắn local socket vào địa chỉ IPv4 loopback và để OS chọn ephemeral port. Đọc port thực tế qua `getLocalAddress()`.

**Câu 3.** Một channel `INET` có thể trở thành IPv6 channel chỉ bằng `connect` với `::1` không?

**Đáp án:** Không. Family được chọn lúc mở, `connect` chỉ chọn peer và không đổi họ giao thức. Phải tạo channel phù hợp.

**Câu 4.** UDP `connect` thành công có chứng minh server đang lắng nghe không?

**Đáp án:** Không. Không có TCP handshake; phải dùng quy tắc response/timeout của protocol để kiểm tra.

**Câu 5.** Tại sao `read/write` yêu cầu connected channel, còn `send/receive` có thể dùng khi unconnected?

**Đáp án:** `read/write` không có tham số địa chỉ, nên cần peer đã chọn. `send` chỉ rõ đích; `receive` trả nguồn từng datagram.

**Câu 6.** `disconnect` có giải phóng local port đã bind không?

**Đáp án:** Không. Nó chỉ bỏ remote peer, còn binding giữ tới khi đóng channel. Không gọi lại `bind` trên channel đã bound.

**Câu 7.** Vì sao `0.0.0.0` hợp lệ trong cấu hình local bind nhưng không phải remote destination lý tưởng?

**Đáp án:** `0.0.0.0` biểu diễn wildcard/unspecified local; client cần remote IP thực tế có thể định tuyến tới server.

**Câu 8.** Nếu domain phân giải được A và AAAA records, nên làm gì?

**Đáp án:** Chọn family phù hợp từng endpoint, kiểm tra địa chỉ được chọn và fallback theo policy. Không giả định `localhost` hay một hostname luôn trả địa chỉ cùng họ trên mọi máy.

## Ghi nhớ

- **`ProtocolFamily` chọn họ IPv4/IPv6; `bind` chọn endpoint local; `connect` chọn peer remote.**
- **`open()` không cam kết family cố định**; dùng `open(INET)` hoặc `open(INET6)` khi cần kiểm soát.
- **`bind(127.0.0.1, port)` và `bind(::1, port)` khác họ địa chỉ**; IPv4/IPv6 không hoán đổi máy móc.
- **Port 0 chọn cổng local tự động**, còn wildcard chọn phạm vi local interface phù hợp.
- **`connect` UDP không có TCP handshake**, nhưng cho phép `read/write` và lọc remote peer; `send/receive` dùng được không cần connected.
- **`connect` có thể tự bind** nếu channel chưa bound; `disconnect` chỉ bỏ peer, không unbind.
- **IPv6, dual-stack, multicast và link-local scope phụ thuộc OS/JVM/network**, phải test deployment thực tế.
- **Chọn blocking/non-blocking độc lập** với IPv4/IPv6; xác thực peer và bảo mật dữ liệu là vấn đề riêng.

### Tài liệu tham khảo còn áp dụng

- [Oracle Java 25 – DatagramChannel](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/DatagramChannel.html): `open`, `bind`, `connect`, `disconnect`, `send/receive`, `read/write`, giới hạn Unix domain socket.
- [Oracle Java 25 – StandardProtocolFamily](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/StandardProtocolFamily.html): `INET` và `INET6`.
- [Oracle Java 25 – InetSocketAddress](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/InetSocketAddress.html): địa chỉ IP, port, wildcard, unresolved endpoints.
- [Oracle Java 25 – Inet4Address](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/Inet4Address.html): IPv4 addresses.
- [Oracle Java 25 – Inet6Address](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/Inet6Address.html): IPv6 addresses, scope IDs và interface.
- [Oracle Java 25 – NetworkChannel](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/NetworkChannel.html): `bind` và `getLocalAddress`.
- [OpenJDK Networking IPv6 User Guide](https://docs.oracle.com/javase/8/docs/technotes/guides/net/ipv6_guide/index.html): tương thích IPv4/IPv6 và cấu hình liên quan.
- [RFC 768 – User Datagram Protocol](https://www.rfc-editor.org/rfc/rfc768): nền tảng datagram UDP.
