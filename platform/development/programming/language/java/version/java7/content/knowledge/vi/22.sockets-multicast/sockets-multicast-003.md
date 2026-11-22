# Java 7 — Socket và multicast: Các tùy chọn chuẩn và khác biệt theo nền tảng

## 1. Mục tiêu và phạm vi

Java NIO.2 mở rộng API mạng ở Java 7, đồng thời giới thiệu `java.net.StandardSocketOptions` để thiết lập các **socket options chuẩn** với kiểu dữ liệu rõ ràng. Những API này vẫn được dùng trên Java 17+ cho TCP, UDP, datagram multicast và các network channels liên quan.

Một chương trình có thể gọi `setOption` thành công trên một hệ điều hành nhưng thất bại hoặc có kết quả khác trên hệ điều hành khác. **Tên “standard” không có nghĩa mọi option đều hoạt động trên mọi loại socket, mọi phiên bản Java hay mọi nền tảng.**

Bài này giải thích:

1. Khái niệm `SocketOption<T>`, `StandardSocketOptions`, `NetworkChannel`, `supportedOptions()`, `getOption()` và `setOption()`.
2. Option áp dụng cho TCP client, TCP server, UDP, multicast và asynchronous socket; không nhầm loại channel.
3. `TCP_NODELAY`, `SO_KEEPALIVE`, `SO_SNDBUF`, `SO_RCVBUF`, `SO_LINGER`, `SO_REUSEADDR`.
4. `SO_REUSEPORT` được bổ sung **Java 9**, không bảo đảm platform hỗ trợ.
5. `SO_BROADCAST`, `IP_TOS` và các tùy chọn multicast `IP_MULTICAST_IF`, `IP_MULTICAST_TTL`, `IP_MULTICAST_LOOP`.
6. Khác biệt IPv4/IPv6, network interface, wildcard bind, multicast group membership, source filtering.
7. Những chỗ Java API gọi là **hint**, **system-dependent**, **implementation-specific** hoặc **unsupported**.
8. Vì sao `DatagramChannel` nhận UDP datagrams với ranh giới thông điệp, khác TCP byte stream.
9. Cách kiểm tra capability tại runtime và xử lý `UnsupportedOperationException`, `IllegalArgumentException`, `IOException`.
10. Phương pháp kiểm thử an toàn trên loopback/localhost, không phụ thuộc Internet và không giả định cùng cấu hình trên Windows/Linux/macOS, VPN, container hoặc cloud.
11. Bài thực hành, checklist production, ma trận QA và liên kết tài liệu chính thức.

**Đề bài:** “Các tùy chọn chuẩn và khác biệt theo nền tảng”, trong chủ đề “Socket và multicast”. Các chương trình hoàn chỉnh biên dịch với `javac --release 17`. Những nội dung cũ không còn phù hợp không được khuyến nghị; `SO_REUSEPORT` được ghi rõ là Java 9+ thay vì gán nhầm cho Java 7.

## 2. Mô hình lựa chọn socket option

### 2.1. `SocketOption<T>` là một khóa có kiểu

`java.net.SocketOption<T>` biểu diễn tên option và kiểu giá trị tương ứng. Ví dụ:

| SocketOption | Kiểu Java | Ví dụ |
| --- | --- | --- |
| `StandardSocketOptions.TCP_NODELAY` | `Boolean` | `true` |
| `StandardSocketOptions.SO_KEEPALIVE` | `Boolean` | `true` |
| `StandardSocketOptions.SO_SNDBUF` | `Integer` | `16_384` |
| `StandardSocketOptions.SO_RCVBUF` | `Integer` | `16_384` |
| `StandardSocketOptions.SO_REUSEADDR` | `Boolean` | `true` |
| `StandardSocketOptions.SO_REUSEPORT` | `Boolean` | `true` khi hỗ trợ |
| `StandardSocketOptions.IP_MULTICAST_IF` | `NetworkInterface` | NIC đã chọn |
| `StandardSocketOptions.IP_MULTICAST_TTL` | `Integer` | `1` |
| `StandardSocketOptions.IP_MULTICAST_LOOP` | `Boolean` | `true` |

`setOption` có generic type parameter: option kiểu `SocketOption<Integer>` đòi giá trị Integer, option kiểu `SocketOption<NetworkInterface>` đòi một NetworkInterface.

### 2.2. `NetworkChannel` công bố khả năng thực tế

`java.nio.channels.NetworkChannel` định nghĩa:

```java
Set<SocketOption<?>> options = channel.supportedOptions();
T current = channel.getOption(option);
channel.setOption(option, value);
```

Đây là **mảnh minh họa generic**, cần biến `channel` loại network channel, biến `option` kiểu `SocketOption<T>` và imports phù hợp. Không phải class chạy độc lập.

- `supportedOptions()` liệt kê options được instance channel/provider hỗ trợ.
- `setOption(option,value)` yêu cầu thiết lập option.
- `getOption(option)` đọc giá trị provider hiện báo cáo.
- `getOption` không đồng nghĩa network/driver sẽ thực thi đúng mọi yêu cầu ở packet level.
- Một số options hỗ trợ trên loại channel này nhưng không hỗ trợ trên loại channel khác.
- Một số options có thể chỉ có tác dụng khi đặt **trước bind/connect**.

### 2.3. Quy tắc tối thiểu để an toàn

```java
if (channel.supportedOptions().contains(
        StandardSocketOptions.SO_REUSEPORT)) {
    channel.setOption(StandardSocketOptions.SO_REUSEPORT, true);
}
```

Đây là mảnh minh họa Java 9+, dùng trong Java 17 hợp lệ. `supportedOptions` giúp tránh gọi option không hỗ trợ; **không hứa** việc bind chung port sẽ thành công vì chính sách hệ điều hành và quyền vẫn quyết định.

Không dùng `option.name()` rồi tự ánh xạ String sang giá trị, đặc biệt khi generic type đã có sẵn và phần option vendor-specific có thể thay đổi.

## 3. Phân biệt các network channels

| API | Mục đích | Những option tiêu biểu | Điều không được giả định |
| --- | --- | --- | --- |
| `SocketChannel` | TCP stream client/accepted socket | `TCP_NODELAY`, `SO_KEEPALIVE`, `SO_SNDBUF`, `SO_RCVBUF`, `SO_REUSEADDR`, `SO_LINGER` | Multicast options không áp dụng cho TCP |
| `ServerSocketChannel` | TCP listener | `SO_RCVBUF`, `SO_REUSEADDR` | `TCP_NODELAY` không có nghĩa trên listener theo option list chuẩn |
| `AsynchronousSocketChannel` | TCP bất đồng bộ | `TCP_NODELAY`, `SO_KEEPALIVE`, `SO_SNDBUF`, `SO_RCVBUF`, `SO_REUSEADDR` | Không mặc định hỗ trợ `SO_LINGER` |
| `AsynchronousServerSocketChannel` | TCP listener bất đồng bộ | `SO_RCVBUF`, `SO_REUSEADDR` | Không phải UDP/multicast channel |
| `DatagramChannel` | UDP datagram, IPv4/IPv6, multicast | `SO_BROADCAST`, `IP_TOS`, `IP_MULTICAST_IF`, `IP_MULTICAST_TTL`, `IP_MULTICAST_LOOP`, buffers/reuse | Không hỗ trợ `TCP_NODELAY` |
| `MulticastChannel` | Interface cho việc join/leave groups | Triển khai bởi `DatagramChannel` | Không có lớp MulticastChannel.open riêng |

Một số Java channel khác (ví dụ Unix-domain SocketChannel trên hệ điều hành hỗ trợ) có **tập options khác**. Không gộp tất cả vào một danh sách rồi gọi vô điều kiện.

### 3.1. Java 7 và Java hiện đại

- `StandardSocketOptions` và `MulticastChannel`: **Since Java 7**.
- `DatagramChannel`, `SocketChannel` có từ trước, tiếp tục được mở rộng với NIO.2 option APIs.
- `AsynchronousSocketChannel`, `AsynchronousServerSocketChannel`: **Java 7**.
- `StandardSocketOptions.SO_REUSEPORT`: **Java 9**; Java 7 gốc không có hằng số này.
- Các demo biên dịch `--release 17` để dùng tất cả phần hiện hành, không tự nhận tương thích `--release 7`.

## 4. Chương trình A — Tự kiểm tra option được hỗ trợ

Lưu **`OptionCatalogDemo.java`**:

```java
import java.net.*;
import java.nio.channels.*;
import java.util.*;

public final class OptionCatalogDemo {
    public static void main(String[] args) throws Exception {
        try (SocketChannel tcp = SocketChannel.open();
             ServerSocketChannel server = ServerSocketChannel.open();
             DatagramChannel udp =
                     DatagramChannel.open(StandardProtocolFamily.INET);
             AsynchronousSocketChannel async =
                     AsynchronousSocketChannel.open();
             AsynchronousServerSocketChannel asyncServer =
                     AsynchronousServerSocketChannel.open()) {

            System.out.println("tcpNoDelay=" +
                    tcp.supportedOptions().contains(
                            StandardSocketOptions.TCP_NODELAY));
            System.out.println("tcpKeepAlive=" +
                    tcp.supportedOptions().contains(
                            StandardSocketOptions.SO_KEEPALIVE));
            System.out.println("serverReuseAddr=" +
                    server.supportedOptions().contains(
                            StandardSocketOptions.SO_REUSEADDR));
            System.out.println("udpBroadcast=" +
                    udp.supportedOptions().contains(
                            StandardSocketOptions.SO_BROADCAST));
            System.out.println("udpMulticastIf=" +
                    udp.supportedOptions().contains(
                            StandardSocketOptions.IP_MULTICAST_IF));
            System.out.println("udpMulticastTtl=" +
                    udp.supportedOptions().contains(
                            StandardSocketOptions.IP_MULTICAST_TTL));
            System.out.println("tcpMulticastIf=" +
                    tcp.supportedOptions().contains(
                            StandardSocketOptions.IP_MULTICAST_IF));
            System.out.println("udpTcpNoDelay=" +
                    udp.supportedOptions().contains(
                            StandardSocketOptions.TCP_NODELAY));
            System.out.println("asyncNoDelay=" +
                    async.supportedOptions().contains(
                            StandardSocketOptions.TCP_NODELAY));
            System.out.println("asyncLinger=" +
                    async.supportedOptions().contains(
                            StandardSocketOptions.SO_LINGER));
            System.out.println("asyncServerReuse=" +
                    asyncServer.supportedOptions().contains(
                            StandardSocketOptions.SO_REUSEADDR));
            System.out.println("reusePortOnUdp=" +
                    udp.supportedOptions().contains(
                            StandardSocketOptions.SO_REUSEPORT));
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 OptionCatalogDemo.java
java OptionCatalogDemo
```

**Stdout đã kiểm thử trên JDK 24/Windows, biên dịch `--release 17`:**

```text
tcpNoDelay=true
tcpKeepAlive=true
serverReuseAddr=true
udpBroadcast=true
udpMulticastIf=true
udpMulticastTtl=true
tcpMulticastIf=false
udpTcpNoDelay=false
asyncNoDelay=true
asyncLinger=false
asyncServerReuse=true
reusePortOnUdp=false
```

### 4.1. Ý nghĩa của bảng kết quả

- `tcpNoDelay=true` vì `TCP_NODELAY` áp dụng cho TCP.
- `udpTcpNoDelay=false` vì UDP không dùng Nagle của TCP.
- `tcpMulticastIf=false` vì một TCP SocketChannel không dùng IP multicast membership của UDP.
- `asyncNoDelay=true` nhưng `asyncLinger=false` trên runtime này: **không giả định mọi option TCP đồng loạt áp dụng cho asynchronous socket**.
- `reusePortOnUdp=false` là **khả năng của runtime/OS kiểm thử**, không phải API thiếu `SO_REUSEPORT`. Hằng số có mặt trong Java 17 nhưng channel không hỗ trợ.
- Để portable, chương trình sản phẩm cần đọc `supportedOptions` của **channel thực tế** thay vì so cứng output máy thử.

### 4.2. Vì sao không in số lượng options như một contract?

JDK có thể cung cấp các options vendor-specific hoặc capabilities khác. `supportedOptions()` có thể thay đổi khi chuyển JDK, hệ điều hành, loại socket hoặc protocol family. Test nên kiểm thuộc tính quan trọng, không assert số option cố định.

## 5. TCP_NODELAY: kiểm soát Nagle, không phải “tăng tốc mọi kết nối”

`StandardSocketOptions.TCP_NODELAY` thuộc TCP stream sockets. Khi bật `true`, nó vô hiệu hóa cơ chế Nagle dùng để gộp các TCP segments nhỏ nhằm giảm overhead.

Điều nên hiểu:

- Có thể hữu ích với workload gửi message nhỏ mà Nagle tác động đến latency.
- Không bảo đảm request latency chắc chắn giảm trong mọi hệ thống.
- Có thể tăng số packet/overhead khi gửi nhiều mẩu bytes nhỏ.
- Không thay thế protocol framing, batching hợp lý, TCP tuning hoặc application performance measurement.
- Không áp dụng cho UDP `DatagramChannel`.
- Default `false` theo Java 17 API; việc tắt lại sau khi đã bật có thể có behavior phụ thuộc hệ thống trong một số implementation.

**Khuyến nghị:** Thử nghiệm dưới workload thực và kiểm `supportedOptions()`. Không bật một cách mù quáng chỉ vì tên chứa “NODELAY”.

## 6. SO_KEEPALIVE: probe idle connection, không phải application heartbeat

`StandardSocketOptions.SO_KEEPALIVE` là Boolean dành cho TCP, cho phép OS dùng keepalive mechanism khi connection idle.

- Default thường là `false` theo API.
- Chu kỳ và hành vi probe là **system-dependent**; có thể rất dài.
- Không xác nhận một request đã được server xử lý.
- Không thay thế timeout nghiệp vụ, message ACK, heartbeat tầng ứng dụng hoặc reconnect logic.
- Không bảo đảm phát hiện mất mạng ngay lập tức khi peer ngủ, NAT thay đổi hoặc firewall cắt kết nối.

Nếu dịch vụ cần phát hiện dead peer trong vài giây, cần thiết kế heartbeat, timeout và recovery ở application layer; đừng nghĩ `SO_KEEPALIVE=true` đồng nghĩa “ping mỗi giây”.

## 7. SO_SNDBUF và SO_RCVBUF: hints, không phải giá trị buộc OS dùng nguyên xi

`SO_SNDBUF` và `SO_RCVBUF` nhận `Integer` là kích thước bộ đệm gửi/nhận cấp OS.

Ví dụ:

```java
socket.setOption(StandardSocketOptions.SO_SNDBUF, 16_384);
int actual = socket.getOption(StandardSocketOptions.SO_SNDBUF);
```

Đây là **mảnh minh họa**; cần `socket` là network channel hỗ trợ option. Trong Java docs:

- Kích thước thiết lập là **hint**.
- OS có thể điều chỉnh theo minimum, maximum, scaling và system policy.
- `getOption` báo size quan sát được; **không khẳng định equal requested value**.
- Default và dải hợp lệ có thể khác giữa Windows/Linux/macOS.
- Thay đổi sau bind có thể không được hỗ trợ/không có tác dụng theo cách ứng dụng mong.
- Với UDP, buffers có thể tác động khả năng nhận bursts và giới hạn thực tế datagram size, không thay thế MTU/fragmentation/packet-loss handling.
- Với TCP, receive buffer có thể liên quan TCP receive window, không có nghĩa application gọi `read` một lần sẽ nhận đúng lượng buffer đó.

### 7.1. Không coi SO_RCVBUF là một application message buffer

Một server TCP nhận dữ liệu qua `ByteBuffer.allocate(4096)` có thể nhận 10, 100 hoặc 4096 bytes ở từng read, không phụ thuộc bạn đã đặt `SO_RCVBUF` thành 64 KiB. TCP là byte stream; framing phải do application xử lý.

UDP thì khác: một `receive` tiêu thụ **một datagram**. Nếu ByteBuffer nhỏ hơn datagram, bytes thừa của datagram ấy có thể bị **bỏ**, không tự chuyển sang lần receive sau.

## 8. SO_LINGER: tránh dùng tùy tiện

`StandardSocketOptions.SO_LINGER` nhận số nguyên giây:

- Giá trị âm: disable linger.
- Giá trị từ 0 trở lên: yêu cầu linger-on-close theo semantics của OS.
- Maximum linger interval phụ thuộc platform; implementation có thể giới hạn.
- Option này **dành cho sockets chạy blocking mode**. Java docs nói hành vi close khi bật linger trên non-blocking socket không được định nghĩa.
- Không coi `SO_LINGER=0` là cách chung “đảm bảo đã gửi hết” — nó có thể có hậu quả về reset/loss của dữ liệu chưa gửi.
- `AsynchronousSocketChannel` không liệt kê `SO_LINGER` trong tập standard options của nó trên Java 17.

Trong phần demo TCP ở dưới, code đặt `SO_LINGER=-1` để **giữ trạng thái disabled**, không bật policy close rủi ro khi chưa có business requirement.

## 9. Chương trình B — Thiết lập các TCP options

Lưu **`TcpOptionDemo.java`**:

```java
import java.net.*;
import java.nio.channels.*;

public final class TcpOptionDemo {
    public static void main(String[] args) throws Exception {
        try (SocketChannel tcp = SocketChannel.open()) {
            tcp.setOption(StandardSocketOptions.TCP_NODELAY, true);
            tcp.setOption(StandardSocketOptions.SO_KEEPALIVE, true);
            tcp.setOption(StandardSocketOptions.SO_SNDBUF, 16384);
            tcp.setOption(StandardSocketOptions.SO_RCVBUF, 16384);
            tcp.setOption(StandardSocketOptions.SO_REUSEADDR, true);
            tcp.setOption(StandardSocketOptions.SO_LINGER, -1);

            System.out.println("noDelay=" +
                    tcp.getOption(StandardSocketOptions.TCP_NODELAY));
            System.out.println("keepAlive=" +
                    tcp.getOption(StandardSocketOptions.SO_KEEPALIVE));
            System.out.println("reuseAddress=" +
                    tcp.getOption(StandardSocketOptions.SO_REUSEADDR));
            System.out.println("sendBufferPositive=" +
                    (tcp.getOption(StandardSocketOptions.SO_SNDBUF) > 0));
            System.out.println("receiveBufferPositive=" +
                    (tcp.getOption(StandardSocketOptions.SO_RCVBUF) > 0));
            System.out.println("lingerDisabled=" +
                    (tcp.getOption(StandardSocketOptions.SO_LINGER) < 0));
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 TcpOptionDemo.java
java TcpOptionDemo
```

**Stdout đã kiểm chứng trên JDK/Windows:**

```text
noDelay=true
keepAlive=true
reuseAddress=true
sendBufferPositive=true
receiveBufferPositive=true
lingerDisabled=true
```

### 9.1. Vì sao in “buffer positive” thay vì đúng 16384?

Mặc dù request 16384, Java docs quy định đây là hint và actual socket buffers có thể khác. Test portable không assert equality. Trong ứng dụng thật, bạn có thể log actual buffer size để phân tích môi trường, nhưng không dùng số literal của một OS làm contract của toàn hệ thống.

### 9.2. Vì sao không connect?

Ví dụ muốn cô lập việc thiết lập/đọc options, không cần Internet hoặc server. `SocketChannel.open` tạo channel; một số options có thể đặt trước connect. Khi cần kết nối thật, gọi `connect` rồi xử lý I/O và close theo protocol.

## 10. SO_REUSEADDR: kiểm soát bind, phụ thuộc kiểu socket và hệ điều hành

`StandardSocketOptions.SO_REUSEADDR` có thể dùng với TCP listeners và UDP sockets, nhưng **ngữ nghĩa không giống nhau hoàn toàn**:

- Với TCP, thường liên quan khả năng bind lại địa chỉ/port khi connection trước còn trạng thái `TIME_WAIT`.
- Với UDP, thường dùng để cho phép nhiều sockets/programs bind cùng địa chỉ phục vụ multicast receive.
- Default là **system-dependent**.
- Nên đặt **trước bind/connect** nếu muốn có hiệu lực; docs nói thay đổi sau bind không có tác dụng đối với option này.
- Không được xem đây là cách bỏ qua mọi conflict hoặc quyền port.
- Không bảo đảm mỗi OS cho phép nhiều TCP listeners cùng bind y hệt endpoint khi bật `SO_REUSEADDR`.

### 10.1. SO_REUSEADDR không giống SO_REUSEPORT

| Khía cạnh | `SO_REUSEADDR` | `SO_REUSEPORT` |
| --- | --- | --- |
| Có từ | StandardSocketOptions Java 7 | **Java 9** |
| Kiểu | Boolean | Boolean |
| Công dụng thường gặp | Bind reuse/TIME_WAIT, UDP multicast membership | Một số OS chia sẻ cùng IP:port giữa listeners/sockets |
| Semantics | OS- và socket-type-dependent | OS- và socket-type-dependent |
| Có thể bật sau bind cho tác dụng mong muốn? | Không | Không |
| Mọi DatagramChannel đều hỗ trợ? | Option chuẩn có cho UDP/IP | **Không**, phải kiểm `supportedOptions` |
| Có thay thế an ninh/quyền truy cập port? | Không | Không |

**SO_REUSEPORT có hằng số không đồng nghĩa `supportedOptions().contains(SO_REUSEPORT)==true`.** Ví dụ máy kiểm thử Windows có hằng số này trên Java 17 nhưng `DatagramChannel` báo **false**.

## 11. Chương trình C — Cấu hình TCP listener trước bind

Lưu **`ServerOptionsDemo.java`**:

```java
import java.net.*;
import java.nio.channels.*;

public final class ServerOptionsDemo {
    public static void main(String[] args) throws Exception {
        try (ServerSocketChannel server = ServerSocketChannel.open()) {
            server.setOption(StandardSocketOptions.SO_REUSEADDR, true);
            server.setOption(StandardSocketOptions.SO_RCVBUF, 16384);
            server.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 0));

            System.out.println("reuseAddress=" +
                    server.getOption(StandardSocketOptions.SO_REUSEADDR));
            System.out.println("recvBufferPositive=" +
                    (server.getOption(StandardSocketOptions.SO_RCVBUF) > 0));
            System.out.println("bound=" +
                    (server.getLocalAddress() != null));
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 ServerOptionsDemo.java
java ServerOptionsDemo
```

**Stdout đã kiểm chứng:**

```text
reuseAddress=true
recvBufferPositive=true
bound=true
```

### 11.1. Vì sao dùng loopback và port 0?

`InetAddress.getLoopbackAddress()` giới hạn listener tới máy local trong demo. Port 0 yêu cầu OS cấp một port phù hợp, tránh cố ý chiếm port dịch vụ khác.

### 11.2. Dùng SO_REUSEADDR không có nghĩa test phải bind được hai servers

Khả năng đồng thời bind cùng endpoint là OS-dependent. Đừng biến test QA portable thành yêu cầu cả hai TCP listeners bắt buộc bind thành công chỉ vì `SO_REUSEADDR` được bật.

## 12. SO_BROADCAST và IP_TOS: tùy chọn datagram, không phải multicast membership

### 12.1. SO_BROADCAST

`SO_BROADCAST` dành cho việc gửi **IPv4 broadcast datagrams**, không phải điều kiện join một IP multicast group. Giá trị ban đầu là false theo StandardSocketOptions.

- Chỉ bật khi ứng dụng cần broadcast và network policy cho phép.
- Nhiều OS hoặc môi trường sandbox có thể từ chối broadcast/đòi quyền đặc biệt.
- Broadcast có ý nghĩa khác multicast: broadcast hướng đến phạm vi mạng IPv4, multicast hướng đến group address và memberships.
- Không gửi broadcast ra LAN thật chỉ để kiểm tra option có tồn tại; kiểm thử an toàn nên dùng local options/controlled network.

### 12.2. IP_TOS

`IP_TOS` là Integer thể hiện ToS octet/traffic class hint trong IPv4 IP header.

- Đây là **hint**: implementation/network có thể bỏ qua một số giá trị.
- Không có bảo đảm thiết lập `IP_TOS=16` làm traffic được ưu tiên trên mọi router/switch.
- Hành vi với TCP stream hoặc IPv6 socket không được định nghĩa chung theo tài liệu Java 17.
- Kiểm tra dải giá trị/option support, không đánh đồng option này với Quality of Service SLA.

## 13. Ba tùy chọn multicast quan trọng

### 13.1. IP_MULTICAST_IF — outgoing interface

`StandardSocketOptions.IP_MULTICAST_IF` có kiểu `SocketOption<NetworkInterface>`. Nó chọn **network interface để gửi multicast datagrams**, không tự động đăng ký receive membership.

```java
datagram.setOption(StandardSocketOptions.IP_MULTICAST_IF, netIf);
```

Đây là mảnh minh họa; `datagram` là DatagramChannel cho IP socket, `netIf` phải là NetworkInterface hợp lệ của máy.

Giá trị mặc định có thể là `null`, nghĩa là OS tự chọn outgoing interface theo routing. Với máy nhiều NIC, Wi‑Fi/Ethernet/VPN, mặc định khác nhau; nên chọn interface cụ thể khi protocol yêu cầu.

### 13.2. IP_MULTICAST_TTL — TTL IPv4 / hop limit IPv6

`IP_MULTICAST_TTL` nhận Integer trong khoảng **0..255**:

- IPv4: TTL của multicast packets gửi ra.
- IPv6: hop limit của multicast packets.
- TTL 0: gói không phát lên mạng, có thể được chuyển local tùy implementation.
- Default thường là 1, nhưng không hardcode khi chưa query.
- Giá trị càng lớn cho phép phạm vi hops rộng hơn theo TTL, **không buộc router/firewall chuyển multicast**.
- Thay đổi/query trước bind có thể system-dependent; ví dụ nên set trên channel phù hợp và kiểm kết quả.
- Với socket IPv6 gửi tới IPv4 group, việc TTL option ảnh hưởng IPv4 như thế nào tùy hệ thống.

### 13.3. IP_MULTICAST_LOOP — multicast loopback

`IP_MULTICAST_LOOP` nhận Boolean:

- `true` bật loopback của multicast datagrams theo semantics của OS.
- Default thường true.
- **Exact semantics là system-dependent**, kể cả loopback áp dụng ở chiều gửi hay chiều nhận, và xử lý IPv6/IPv4.
- Không dùng option này làm security control; nó không xác thực người tham gia group.
- Việc đọc lại true không chứng minh một receiver local chắc chắn nhận gói nếu NIC, bind, group, OS/firewall hoặc network policy không phù hợp.

## 14. Chương trình D — UDP/multicast option values

Lưu **`DatagramOptionsDemo.java`**:

```java
import java.net.*;
import java.nio.channels.*;

public final class DatagramOptionsDemo {
    public static void main(String[] args) throws Exception {
        try (DatagramChannel udp =
                     DatagramChannel.open(StandardProtocolFamily.INET)) {
            udp.setOption(StandardSocketOptions.SO_REUSEADDR, true);
            udp.setOption(StandardSocketOptions.SO_BROADCAST, true);
            udp.setOption(StandardSocketOptions.IP_MULTICAST_TTL, 1);
            udp.setOption(StandardSocketOptions.IP_MULTICAST_LOOP, true);
            udp.setOption(StandardSocketOptions.IP_TOS, 16);
            udp.setOption(StandardSocketOptions.SO_RCVBUF, 16384);
            udp.bind(new InetSocketAddress(0));

            System.out.println("reuseAddress=" +
                    udp.getOption(StandardSocketOptions.SO_REUSEADDR));
            System.out.println("broadcast=" +
                    udp.getOption(StandardSocketOptions.SO_BROADCAST));
            System.out.println("multicastTtl=" +
                    udp.getOption(StandardSocketOptions.IP_MULTICAST_TTL));
            System.out.println("multicastLoop=" +
                    udp.getOption(StandardSocketOptions.IP_MULTICAST_LOOP));
            int tos = udp.getOption(StandardSocketOptions.IP_TOS);
            System.out.println("tosWithinRange=" +
                    (tos >= 0 && tos <= 255));
            System.out.println("receiveBufferPositive=" +
                    (udp.getOption(StandardSocketOptions.SO_RCVBUF) > 0));
            System.out.println("boundPortPositive=" +
                    (((InetSocketAddress) udp.getLocalAddress())
                            .getPort() > 0));
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 DatagramOptionsDemo.java
java DatagramOptionsDemo
```

**Stdout đã kiểm chứng với IPv4 UDP channel trên JDK/Windows:**

```text
reuseAddress=true
broadcast=true
multicastTtl=1
multicastLoop=true
tosWithinRange=true
receiveBufferPositive=true
boundPortPositive=true
```

### 14.1. Điều gì là request, điều gì là guarantee?

`setOption(IP_TOS,16)` là request/hint; test chỉ yêu cầu `getOption` trong dải 0..255, không bắt buộc returned value luôn đúng 16.

`multicastTtl=1` và `multicastLoop=true` là **giá trị được provider báo lại trên máy thử**. Điều đó không chứng minh một datagram thực sự vượt qua firewall/router hoặc loop back được. Demo này **không gửi multicast ra LAN**.

### 14.2. Tại sao phải xác định ProtocolFamily?

`DatagramChannel.open(StandardProtocolFamily.INET)` tạo UDP IPv4 channel. Nếu định dùng IPv6 multicast group, cần chọn `INET6` khi runtime hỗ trợ. Không trông chờ một IPv6 socket tự nhận IPv4 multicast group giống nhau giữa OSes.

## 15. Giá trị option không hợp lệ và option không được hỗ trợ

`NetworkChannel.setOption` có hai nhóm lỗi khác nhau:

1. Option **không thuộc tập supported** của channel → `UnsupportedOperationException`.
2. Option có hỗ trợ nhưng giá trị không hợp lệ (ví dụ TTL âm/256) → `IllegalArgumentException`.

Các trường hợp đặc biệt có thể còn `IOException`/`SocketException` khi OS không thiết lập được, hoặc `ClosedChannelException` nếu channel đã đóng. Không catch chung mọi lỗi rồi giả lập thành công.

### 15.1. Hằng số tồn tại không chứng minh provider hỗ trợ

`StandardSocketOptions.TCP_NODELAY` là hằng số Java hợp lệ, nhưng đưa vào `DatagramChannel.setOption` sẽ không có ý nghĩa: đó là UDP, không sử dụng TCP Nagle.

`StandardSocketOptions.IP_MULTICAST_TTL` chỉ hợp lệ cho datagram-oriented IP sockets; không nên cố set lên TCP socket.

### 15.2. Kiểu dữ liệu cũng phải đúng

`SocketOption<T>` giúp compiler kiểm tra value type. Ví dụ `IP_MULTICAST_TTL` cần Integer, không dùng Boolean; `IP_MULTICAST_IF` cần NetworkInterface, không dùng String tên interface. Nếu có input text, hãy parse/validate trước khi setOption.

## 16. Chương trình E — Xác minh lỗi option

Lưu **`OptionValidationDemo.java`**:

```java
import java.net.*;
import java.nio.channels.*;

public final class OptionValidationDemo {
    public static void main(String[] args) throws Exception {
        try (DatagramChannel udp =
                     DatagramChannel.open(StandardProtocolFamily.INET)) {
            boolean badTtl = false, badBigTtl = false;
            boolean badBuffer = false, unsupported = false;

            try {
                udp.setOption(StandardSocketOptions.IP_MULTICAST_TTL, -1);
            } catch (IllegalArgumentException e) {
                badTtl = true;
            }
            try {
                udp.setOption(StandardSocketOptions.IP_MULTICAST_TTL, 256);
            } catch (IllegalArgumentException e) {
                badBigTtl = true;
            }
            try {
                udp.setOption(StandardSocketOptions.SO_SNDBUF, -1);
            } catch (IllegalArgumentException e) {
                badBuffer = true;
            }
            try {
                udp.setOption(StandardSocketOptions.TCP_NODELAY, true);
            } catch (UnsupportedOperationException e) {
                unsupported = true;
            }

            System.out.println("negativeTtlRejected=" + badTtl);
            System.out.println("ttl256Rejected=" + badBigTtl);
            System.out.println("negativeSendBufferRejected=" + badBuffer);
            System.out.println("tcpNoDelayOnUdpRejected=" + unsupported);
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 OptionValidationDemo.java
java OptionValidationDemo
```

**Stdout đã kiểm chứng:**

```text
negativeTtlRejected=true
ttl256Rejected=true
negativeSendBufferRejected=true
tcpNoDelayOnUdpRejected=true
```

Điểm chính: giá trị TTL phải trong khoảng 0..255. Với invalid send buffer size âm, provider từ chối. `TCP_NODELAY` không được UDP channel hỗ trợ. **Tránh phụ thuộc exact exception message**; test dựa trên loại exception.

## 17. UDP datagram không giống TCP byte stream

**Một nhầm lẫn lớn:** UDP `DatagramChannel` và TCP `SocketChannel` đều dùng `ByteBuffer`, nhưng chúng có semantics khác nhau.

### 17.1. TCP có dòng byte liên tục

Nếu sender TCP write 5 byte, receiver dùng buffer 3 byte, phần còn lại của dòng byte **vẫn còn để đọc tiếp**. Phải dùng framing để xác định boundaries của application message.

### 17.2. UDP có ranh giới datagram

`DatagramChannel.receive(dst)` nhận **một datagram**. Nếu datagram có 5 byte nhưng `dst` chỉ còn 3 chỗ, phần thừa của datagram **bị bỏ** theo API. Một lần receive tiếp theo không tự nhận hai byte còn thừa của datagram trước.

```text
Datagram #1 = H E L L O, receiver buffer 3
receive #1  = H E L      phần L O còn lại của datagram bị bỏ

Datagram #2 = Z
receive #2  = Z          không phải L O
```

**SO_RCVBUF lớn không sửa được lỗi destination ByteBuffer quá nhỏ.** Receive buffer của OS và `ByteBuffer.remaining` của application là hai giới hạn khác nhau.

## 18. Chương trình F — Thấy rõ UDP bị cắt datagram

Lưu **`UdpDatagramBoundaryDemo.java`**:

```java
import java.net.*;
import java.nio.*;
import java.nio.channels.*;
import java.nio.charset.StandardCharsets;

public final class UdpDatagramBoundaryDemo {
    static String receiveUntil(DatagramChannel ch, ByteBuffer b)
            throws Exception {
        long deadline = System.nanoTime() + 2_000_000_000L;
        while (System.nanoTime() < deadline) {
            b.clear();
            SocketAddress remote = ch.receive(b);
            if (remote != null) {
                b.flip();
                byte[] part = new byte[b.remaining()];
                b.get(part);
                return new String(
                        part, StandardCharsets.US_ASCII);
            }
            Thread.sleep(2);
        }
        throw new IllegalStateException("No datagram");
    }

    public static void main(String[] args) throws Exception {
        try (DatagramChannel receiver =
                     DatagramChannel.open(StandardProtocolFamily.INET);
             DatagramChannel sender =
                     DatagramChannel.open(StandardProtocolFamily.INET)) {

            receiver.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 0));
            receiver.configureBlocking(false);
            SocketAddress address = receiver.getLocalAddress();

            int count = sender.send(ByteBuffer.wrap(
                    "HELLO".getBytes(StandardCharsets.US_ASCII)),
                    address);
            String first = receiveUntil(receiver,
                    ByteBuffer.allocate(3));

            int next = sender.send(ByteBuffer.wrap(
                    "Z".getBytes(StandardCharsets.US_ASCII)),
                    address);
            String second = receiveUntil(receiver,
                    ByteBuffer.allocate(8));

            System.out.println("sendFirst=" + count);
            System.out.println("firstReceived=" + first);
            System.out.println("sendSecond=" + next);
            System.out.println("secondReceived=" + second);
            System.out.println("firstDatagramTruncated=" +
                    first.equals("HEL"));
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 UdpDatagramBoundaryDemo.java
java UdpDatagramBoundaryDemo
```

**Stdout đã kiểm chứng trên loopback:**

```text
sendFirst=5
firstReceived=HEL
sendSecond=1
secondReceived=Z
firstDatagramTruncated=true
```

### 18.1. Vì sao đây là minh họa khác “partial TCP write”?

UDP sender gửi **một datagram** `HELLO` gồm 5 byte. Receiver dùng buffer3 chỉ nhìn thấy `HEL`; hai byte `LO` bị bỏ theo receive semantics. Datagram tiếp theo `Z` vẫn độc lập.

Với TCP, partial reads là chuyện bình thường và bytes chưa nhận vẫn trong stream; với UDP, một datagram bị truncation **không thể ghép lại bằng lời gọi receive tiếp** nếu đã bị bỏ.

### 18.2. Vì sao code dùng non-blocking receive và deadline?

Ví dụ không nên block vô hạn nếu môi trường chặn UDP loopback. `configureBlocking(false)` khiến `receive` có thể trả `null` khi chưa có datagram; `receiveUntil` poll tới deadline ngắn rồi báo lỗi. Thread.sleep ở đây chỉ phục vụ chương trình test, không là thiết kế server hiệu năng cao.

### 18.3. Mốc đúng là length theo byte

Khi UDP body là UTF-8, ứng dụng phải tránh cắt giữa ký tự; nhưng kể cả với ASCII `HELLO`, truncation vẫn làm mất dữ liệu. Kiểm số byte/MTU/payload limit theo protocol. Đừng nghĩ `SO_RCVBUF` tăng thì có thể truyền datagram lớn tùy ý.

## 19. Multicast: địa chỉ group khác interface cục bộ

IP multicast gửi **một datagram tới địa chỉ group**, cho những hosts tham gia group theo khả năng mạng.

`MulticastChannel.join(group, netIf)` có hai thông tin:

- `group`: địa chỉ multicast ví dụ `239.255.10.17` (IPv4).
- `netIf`: `NetworkInterface` cụ thể ở máy local để join/receive.

`IP_MULTICAST_IF` cũng nhận `NetworkInterface`, nhưng chủ yếu chọn **outgoing interface** khi gửi multicast. **Set outgoing interface không tự join group.**

### 19.1. Cách chọn network interface

Dùng `NetworkInterface.getNetworkInterfaces()` rồi kiểm:

- `isUp()` — interface đang hoạt động.
- `supportsMulticast()` — interface được platform báo có khả năng multicast.
- `isLoopback()` — có phải loopback hay không.
- `getInterfaceAddresses()` có IPv4/IPv6 address phù hợp với group không.
- Giới hạn theo yêu cầu sản phẩm (Wi‑Fi/Ethernet/VPN/container) thay vì chọn NIC đầu tiên tùy ý.

Trên một số máy/vùng cloud, không có interface phù hợp. **Không được tạo giả tên giao diện như “eth0” hoặc “en0” rồi tin mọi máy đều có.**

### 19.2. IPv4 và IPv6 protocol family

`DatagramChannel.open(StandardProtocolFamily.INET)` tạo IPv4 channel; `INET6` tạo IPv6 channel khi runtime hỗ trợ.

Java `MulticastChannel` quy định không có bảo đảm một channel IPv6 có thể join/receive một nhóm IPv4, hoặc ngược lại. Chọn protocol family khớp group address. Trên môi trường bị hạn chế IPv6, open `INET6` có thể thất bại.

### 19.3. Bind wildcard trước join

Tài liệu Java 17 khuyến cáo:

1. Mở `DatagramChannel` với `ProtocolFamily` phù hợp.
2. Đặt `SO_REUSEADDR=true` **trước bind** để nhiều group members có thể bind cùng địa chỉ/port khi được OS cho phép.
3. Bind tới **wildcard address** và port mong muốn (ví dụ `new InetSocketAddress(port)`).
4. Chọn `IP_MULTICAST_IF` nếu cần outgoing multicast.
5. Gọi `join(group, netIf)` rồi giữ `MembershipKey`.
6. Khi không dùng nữa, `key.drop()` và đóng channel.

**Nếu bind đến một địa chỉ cụ thể thay vì wildcard, khả năng nhận multicast có thể implementation-specific.** Đừng thay thiết kế multicast thành bind đến `127.0.0.1` rồi kết luận group không hoạt động.

## 20. MembershipKey và vòng đời group

`MulticastChannel.join(group,netIf)` trả `MembershipKey`:

- `key.isValid()` kiểm membership key còn hiệu lực.
- `key.drop()` rời group.
- Đóng channel cũng làm memberships bị hủy theo lifecycle.
- Một channel có thể join nhiều groups nếu provider/OS hỗ trợ.
- Join lại cùng group và interface theo API có thể trả key liên quan thay vì tạo trùng vô hạn.
- `join(group,interface,source)` hỗ trợ source-specific multicast khi underlying platform có khả năng source filtering; có thể ném `UnsupportedOperationException` nếu không hỗ trợ.
- `MembershipKey.block(source)`/`unblock(source)` cũng phụ thuộc khả năng source filtering; không coi mọi mạng có IGMPv3/MLDv2.

### 20.1. Membership không phải security boundary

Bất cứ participant phù hợp với cấu hình mạng có thể gửi datagram đến group. Multicast UDP không tự cung cấp TLS, authentication hoặc reliable delivery. Với dữ liệu nhạy cảm, cần protocol kiểm chứng sender, integrity, encryption hoặc một cơ chế truyền phù hợp hơn.

### 20.2. Không dùng IP_MULTICAST_LOOP làm cách kiểm quyền

`IP_MULTICAST_LOOP` chỉ liên quan khả năng loopback multicast packets, với semantics OS-dependent. Nó không xác thực user, không chặn sender lạ và không thay thế network ACL/firewall.

## 21. Chương trình G — Join một IPv4 multicast group có điều kiện

Lưu **`MulticastInterfaceDemo.java`**:

```java
import java.net.*;
import java.nio.channels.*;
import java.util.*;

public final class MulticastInterfaceDemo {
    public static void main(String[] args) throws Exception {
        Enumeration<NetworkInterface> interfaces =
                NetworkInterface.getNetworkInterfaces();
        NetworkInterface candidate = null;

        while (interfaces != null && interfaces.hasMoreElements()) {
            NetworkInterface ni = interfaces.nextElement();
            if (!ni.isUp() ||
                !ni.supportsMulticast() ||
                ni.isLoopback()) continue;

            for (InterfaceAddress address : ni.getInterfaceAddresses()) {
                if (address.getAddress() instanceof Inet4Address) {
                    candidate = ni;
                    break;
                }
            }
            if (candidate != null) break;
        }

        boolean found = candidate != null;
        System.out.println("candidateFound=" + found);

        if (!found) {
            System.out.println("joinAttempted=false");
            System.out.println("joinSucceeded=not-applicable");
            return;
        }

        try (DatagramChannel dc =
                     DatagramChannel.open(StandardProtocolFamily.INET)) {
            dc.setOption(StandardSocketOptions.SO_REUSEADDR, true);
            dc.bind(new InetSocketAddress(0));
            dc.setOption(StandardSocketOptions.IP_MULTICAST_IF, candidate);
            dc.setOption(StandardSocketOptions.IP_MULTICAST_TTL, 1);

            InetAddress group =
                    InetAddress.getByName("239.255.10.17");
            boolean succeeded = false;

            try {
                MembershipKey key = dc.join(group, candidate);
                succeeded = key.isValid();
                key.drop();
            } catch (java.io.IOException |
                     UnsupportedOperationException e) {
                succeeded = false;
            }

            System.out.println("joinAttempted=true");
            System.out.println("joinSucceeded=" + succeeded);
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 MulticastInterfaceDemo.java
java MulticastInterfaceDemo
```

**Stdout đã quan sát trên máy kiểm thử:**

```text
candidateFound=true
joinAttempted=true
joinSucceeded=true
```

**Không hardcode bộ stdout này cho mọi máy.** Trên CI/container không có interface IPv4 đủ điều kiện, chương trình có thể in:

```text
candidateFound=false
joinAttempted=false
joinSucceeded=not-applicable
```

Nếu có interface nhưng OS/network policy không cho join, `joinSucceeded` có thể false. Chương trình chỉ thử membership rồi drop; nó **không phát multicast gói tin ra mạng**. Đây là cách thử capability có giới hạn hơn so với tự gửi broadcast/multicast tùy tiện lên mạng công ty.

### 21.1. Vì sao không chỉ cần `supportsMulticast()==true`?

Đó là flag thông báo của platform, không đảm bảo firewall, router, Wi‑Fi AP, VLAN, Docker bridge hoặc VPN sẽ vận chuyển multicast từ host khác. Cần integration test trên đúng network path của sản phẩm.

## 22. SO_REUSEPORT: bảo đảm giá trị tên hằng số, không bảo đảm OS hỗ trợ

`SO_REUSEPORT` được thêm từ **Java 9**. Đây là Boolean option cho phép một số nền tảng chia sẻ cùng địa chỉ và port giữa nhiều sockets.

- TCP: thường liên quan nhiều listening sockets trên cùng address/port.
- UDP: thường cho nhiều sockets bind cùng địa chỉ/port.
- Cách phân phối các incoming packets/connections phụ thuộc OS/kernel.
- Các yêu cầu về cùng user/process, privileges, bind address, option timing hoặc load-balancing behavior có thể khác nhau.
- Java không hứa cùng semantics trên Linux, macOS, Windows và custom providers.
- Trên máy thử `DatagramChannel.supportedOptions().contains(SO_REUSEPORT)==false`; đó là lý do **không gọi setOption một cách vô điều kiện**.

### 22.1. Khi không hỗ trợ thì làm gì?

- Nếu `SO_REUSEPORT` chỉ là tối ưu: bỏ qua optimization có thông báo/metrics.
- Nếu cùng port sharing là yêu cầu bắt buộc: fail configuration một cách rõ ràng, hoặc đổi kiến trúc thành một listener/dispatcher.
- Không dùng `SO_REUSEADDR` như một phép thay thế hoàn toàn vì hai option có semantics khác.
- Đừng thử bind cùng port ngẫu nhiên trên production để “kiểm tra”; hãy thiết kế explicit capability checks và test môi trường riêng.

## 23. Chương trình H — OptionalReusePortDemo.java

```java
import java.net.*;
import java.nio.channels.*;

public final class OptionalReusePortDemo {
    public static void main(String[] args) throws Exception {
        try (DatagramChannel udp =
                     DatagramChannel.open(StandardProtocolFamily.INET)) {
            boolean supported = udp.supportedOptions().contains(
                    StandardSocketOptions.SO_REUSEPORT);
            boolean enabled = false;

            if (supported) {
                udp.setOption(StandardSocketOptions.SO_REUSEPORT, true);
                enabled = Boolean.TRUE.equals(
                        udp.getOption(StandardSocketOptions.SO_REUSEPORT));
            }

            udp.bind(new InetSocketAddress(0));

            System.out.println("supported=" + supported);
            System.out.println("enabledWhenSupported=" +
                    (!supported || enabled));
            System.out.println("bound=" +
                    (udp.getLocalAddress() != null));
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 OptionalReusePortDemo.java
java OptionalReusePortDemo
```

**Stdout đã kiểm chứng trên Windows/JDK test:**

```text
supported=false
enabledWhenSupported=true
bound=true
```

### 23.1. Giải thích biểu thức `!supported || enabled`

Đây là một kiểm tra rằng: “Nếu OS/channel công bố support, thử set/get option đã thành công; nếu không support, code **đã bỏ qua** một cách có chủ ý.” Vì vậy `enabledWhenSupported=true` khi `supported=false` **không có nghĩa SO_REUSEPORT đã được bật**.

Ứng dụng thật nên log riêng:

- `supported`,
- `enabled` nếu có support,
- tình trạng bind/use-case,
- backend config cần fallback hay fail-fast.

### 23.2. Không đoán từ tên hệ điều hành

Hãy kiểm capability trên channel thực tế. Hệ điều hành và JDK version là một phần bối cảnh chẩn đoán, nhưng native policy/driver/runtime/container mới quyết định behavior.

## 24. AsynchronousSocketChannel: option nào thực sự có?

`AsynchronousSocketChannel` (Java 7+) là TCP asynchronous stream channel, không phải multicast/UDP channel.

Danh sách standard options được Java 17 docs mô tả gồm:

- `SO_SNDBUF`, `SO_RCVBUF`,
- `SO_KEEPALIVE`,
- `SO_REUSEADDR`,
- `TCP_NODELAY`.

Có thể có options implementation-specific khác, nhưng **`SO_LINGER` và `IP_MULTICAST_IF` không nằm trong danh sách chuẩn được hứa** cho AsynchronousSocketChannel. Với ứng dụng, luôn kiểm `supportedOptions()` trước khi phụ thuộc optional capabilities.

### 24.1. Options trước hay sau connect?

Một số socket options có thể set trước connect; các options khác chỉ có ý nghĩa khi connection ở trạng thái thích hợp. Hướng an toàn:

- Những option ảnh hưởng bind/reuse: set trước bind/connect.
- Những option như `TCP_NODELAY`/`SO_KEEPALIVE`: kiểm support, đặt theo yêu cầu.
- Đừng quên `connect`/I/O vẫn có thể thất bại dù setOption thành công.
- Không dùng `setOption` làm phép thử “peer reachable”.

## 25. Chương trình I — AsyncSocketOptionDemo.java

Lưu **`AsyncSocketOptionDemo.java`**:

```java
import java.net.*;
import java.nio.channels.*;

public final class AsyncSocketOptionDemo {
    public static void main(String[] args) throws Exception {
        try (AsynchronousSocketChannel client =
                     AsynchronousSocketChannel.open()) {
            client.setOption(StandardSocketOptions.SO_KEEPALIVE, true);
            client.setOption(StandardSocketOptions.TCP_NODELAY, true);

            System.out.println("keepAlive=" +
                    client.getOption(StandardSocketOptions.SO_KEEPALIVE));
            System.out.println("noDelay=" +
                    client.getOption(StandardSocketOptions.TCP_NODELAY));
            System.out.println("supportsLinger=" +
                    client.supportedOptions().contains(
                            StandardSocketOptions.SO_LINGER));
            System.out.println("supportsMulticast=" +
                    client.supportedOptions().contains(
                            StandardSocketOptions.IP_MULTICAST_IF));
            System.out.println("connected=" +
                    (client.getRemoteAddress() != null));
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 AsyncSocketOptionDemo.java
java AsyncSocketOptionDemo
```

**Stdout đã kiểm chứng:**

```text
keepAlive=true
noDelay=true
supportsLinger=false
supportsMulticast=false
connected=false
```

`connected=false` là điều mong đợi: mở channel và đặt socket options **không tự connect** tới remote host. `supportsLinger=false` là đặc trưng runtime kiểm thử/phù hợp tập options standard của asynchronous socket; không lấy toàn bộ options của `SocketChannel` để áp dụng thẳng cho `AsynchronousSocketChannel`.

## 26. IPv4 và IPv6 không thể gộp thành một cấu hình vô điều kiện

### 26.1. ProtocolFamily cần khớp group address

Với IPv4 group, ưu tiên:

```java
DatagramChannel ch =
        DatagramChannel.open(StandardProtocolFamily.INET);
```

Với IPv6 group, ưu tiên:

```java
DatagramChannel ch =
        DatagramChannel.open(StandardProtocolFamily.INET6);
```

Đây là mảnh minh họa, mỗi channel phải được đóng. Một runtime có thể không hỗ trợ `INET6`. Việc IPv6 channel join IPv4 multicast group là implementation-specific.

### 26.2. Outgoing interface và NIC scope

IPv6 multicast thường nhạy với **interface/scope**: cùng một group address nhưng trên interface khác có thể không tương ứng cùng phạm vi nhận. Chọn `NetworkInterface` đúng và kiểm OS/network topology.

### 26.3. TTL IPv6 thật ra là hop limit

API đặt tên chung `IP_MULTICAST_TTL`, nhưng với IPv6 nó dùng hop limit. Không lấy khái niệm TTL/hop count làm cam kết multicast luôn đi tới mọi router trong phạm vi số hops; policy/firewall/network equipment vẫn có thể chặn.

## 27. Chương trình J — FamilyCapabilitiesDemo.java

```java
import java.net.*;
import java.nio.channels.*;

public final class FamilyCapabilitiesDemo {
    public static void main(String[] args) throws Exception {
        try (DatagramChannel ipv4 =
                     DatagramChannel.open(StandardProtocolFamily.INET)) {
            System.out.println("ipv4Opened=" + ipv4.isOpen());
            System.out.println("ipv4Multicast=" +
                    ipv4.supportedOptions().contains(
                            StandardSocketOptions.IP_MULTICAST_IF));
        }

        boolean ipv6 = false;
        boolean ipv6Multicast = false;
        try (DatagramChannel ch =
                     DatagramChannel.open(StandardProtocolFamily.INET6)) {
            ipv6 = ch.isOpen();
            ipv6Multicast = ch.supportedOptions().contains(
                    StandardSocketOptions.IP_MULTICAST_IF);
        } catch (UnsupportedOperationException |
                 java.io.IOException e) {
            // IPv6 không dùng được trong môi trường hiện tại.
        }

        System.out.println("ipv6Available=" + ipv6);
        System.out.println("ipv6MulticastWhenAvailable=" +
                (!ipv6 || ipv6Multicast));
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 FamilyCapabilitiesDemo.java
java FamilyCapabilitiesDemo
```

**Stdout đã quan sát trên JDK/Windows QA:**

```text
ipv4Opened=true
ipv4Multicast=true
ipv6Available=true
ipv6MulticastWhenAvailable=true
```

Trên runtime không có IPv6, `ipv6Available` có thể false. `ipv6MulticastWhenAvailable=true` trong trường hợp IPv6 không khả dụng chỉ có nghĩa logic đã **skip kiểm tra capability phụ thuộc IPv6**. Nó không chứng minh máy có multicast IPv6.

### 27.1. IPv6 available chưa đủ để gửi/nhận multicast

Mở thành công `INET6` channel không chứng minh mạng có route multicast IPv6, interface support, group join permissions hoặc multicast traversal qua router. Cần integration test có kiểm soát trên hạ tầng mục tiêu.

## 28. SO_REUSEADDR và multicast: thứ tự cấu hình chuẩn

Khi muốn nhiều receivers cùng đăng ký một multicast group trên cùng port:

```java
try (DatagramChannel dc =
             DatagramChannel.open(StandardProtocolFamily.INET)) {
    dc.setOption(StandardSocketOptions.SO_REUSEADDR, true);
    dc.bind(new InetSocketAddress(5000));  // wildcard + port.
    dc.setOption(StandardSocketOptions.IP_MULTICAST_IF, netIf);

    InetAddress group = InetAddress.getByName("239.255.10.17");
    MembershipKey key = dc.join(group, netIf);
    try {
        // Đọc UDP datagrams theo protocol có giới hạn.
    } finally {
        key.drop();
    }
}
```

**Đây là mảnh minh họa**, `netIf` phải là NetworkInterface hợp lệ có hỗ trợ IPv4 multicast; port5000 có thể đang được dùng; không triển khai receive loop để tránh block và xung đột test. Với bài runnable trên máy thực, dùng `MulticastInterfaceDemo` ở trên.

### 28.1. Vì sao wildcard bind quan trọng?

Java `MulticastChannel` mô tả binding tới một địa chỉ specific có thể cho kết quả multicast receive **implementation-specific**. Nên dùng wildcard khi muốn receive datagrams gửi tới group, rồi kiểm membership/interface/port.

### 28.2. Đặt option sau bind có thể không có tác dụng

Java docs nói thay `SO_REUSEADDR` và `SO_REUSEPORT` sau bind không làm thay đổi effect của chúng đối với bind. Vì vậy, set trước bind. Đừng “fix” lỗi bind bằng cách set option sau khi bind thất bại rồi nghĩ thao tác trước được retry tự động.

### 28.3. Source-specific multicast là optional

`dc.join(group,netIf,source)` phụ thuộc IGMPv3/MLDv2, OS và protocol family. Nếu platform không hỗ trợ source filtering, API có thể ném `UnsupportedOperationException`. Thiết kế phải có fallback rõ hoặc báo thiếu khả năng thay vì coi việc filter đã được áp dụng.

## 29. Các khác biệt theo nền tảng cần kiểm tra từng lớp

| Lớp khác biệt | Ví dụ | Phương pháp kiểm |
| --- | --- | --- |
| OS socket API | Linux/Windows/macOS bind/reuse khác | Integration tests trên OS deploy |
| JDK/runtime | Provider trả tập options khác | `supportedOptions()`, Java version |
| Java target | `SO_REUSEPORT` có từ Java 9 | `javac --release 17` / source compatibility |
| Protocol family | IPv4 vs IPv6 | `StandardProtocolFamily.INET/INET6` |
| Network interfaces | Wi‑Fi/Ethernet/VPN/NIC ảo | `NetworkInterface` enumeration |
| Container/network namespace | Host NIC không hiện trong container | Kiểm interface bên trong runtime |
| Cloud platform | Multicast/broadcast có thể không được định tuyến | Hỏi network policy, test mạng thật |
| Firewall/ACL | Group/UDP traffic bị chặn | Firewall rules, metrics, captures |
| Application socket type | TCP/UDP/listener/async | Chỉ set supported options |
| Buffer sizing | OS điều chỉnh/clamp kích thước | `getOption` rồi đo throughput |
| Multicast scope | TTL/hop-limit, IGMP/MLD | Test group routing và membership |
| Source-specific multicast | OS thiếu filter support | Catch UnsupportedOperation, test capability |
| Permissions | Không cho broadcast/bind privileged port | Catch exceptions, deploy policy |
| QoS | IP_TOS ignored/rewritten | Network measurements, không tự hứa SLA |
| Receive loopback | `IP_MULTICAST_LOOP` system-dependent | Test trên exact NIC + OS |

### 29.1. Không hardcode tên interface

Tên `eth0`, `en0`, `Wi-Fi`, `Ethernet` không phải chuẩn xuyên nền tảng. Chọn theo thuộc tính và config. Nếu tên interface là input từ người vận hành, dùng `NetworkInterface.getByName(...)` và kiểm null/`isUp()/supportsMulticast()` trước khi set.

### 29.2. Không hardcode SO_REUSEPORT support từ OS name

Có những khác biệt giữa kernel, system policy, JDK builds và socket type. Test runtime `supportedOptions` đáng tin hơn suy đoán chỉ từ tên “Linux” hoặc “Windows”.

### 29.3. Không trộn multicast/broadcast với discovery đảm bảo

Multicast discovery có thể bị VLAN isolation, Wi‑Fi AP, container bridging và firewall chặn dù local join thành công. Nếu sản phẩm cần discovery đáng tin qua Internet hoặc cloud, cân nhắc registry/discovery service phù hợp thay vì coi multicast là universal connectivity.

## 30. Khi option không hỗ trợ: fallback hay fail-fast?

Đặt policy theo tầm quan trọng của option:

**Option chỉ tối ưu hiệu năng** như `TCP_NODELAY` hoặc `SO_SNDBUF`:
- Nếu không hỗ trợ và app vẫn đúng chức năng, có thể dùng default và ghi log/metrics.
- Nếu hiệu năng là SLA bắt buộc, test performance và fail configuration có chủ đích.

**Option ảnh hưởng correctness mạng**, ví dụ chọn đúng multicast interface hoặc family:
- Nếu không thể join đúng group/interface, báo không hoạt động thay vì giả success.
- Nếu IPv6 group không hỗ trợ, không tự sửa sang IPv4 group mà không có cấu hình/protocol tương ứng.

**Option chỉ có trên một số OS**, ví dụ `SO_REUSEPORT`:
- Nếu bắt buộc cần many-listener architecture, fail-fast và chuyển hướng thiết kế.
- Nếu optional, skip và tiếp tục single listener.

### 30.1. Exception nào có thể gặp?

| Exception | Nguyên nhân thường gặp |
| --- | --- |
| `UnsupportedOperationException` | Option không được channel/provider hỗ trợ |
| `IllegalArgumentException` | Value sai phạm vi (TTL -1/256, size âm...), hoặc type/value không hợp lệ |
| `ClosedChannelException` | Channel đóng trước khi get/set option |
| `IOException`/`SocketException` | OS không thể thực thi yêu cầu |
| `UnsupportedAddressTypeException` | Kết hợp địa chỉ/protocol family không tương thích |
| `IllegalArgumentException` khi join | Group không phải multicast hoặc family không phù hợp |
| `UnsupportedOperationException` khi source-specific join | Platform không hỗ trợ source filtering |
| `SecurityException` | Security policy hạn chế thao tác, nếu môi trường có |
| `UnknownHostException` | Tên group/hostname không resolve khi dùng tên DNS |

**Không catch tất cả rồi tiếp tục như đã set thành công.** Nếu option quan trọng, log category + config và dừng, hoặc có fallback đã kiểm chứng.

## 31. Sự khác biệt giữa “option được chấp nhận” và “mạng làm đúng như kỳ vọng”

Ngay cả khi:

```java
dc.setOption(StandardSocketOptions.IP_MULTICAST_LOOP, true);
System.out.println(dc.getOption(
        StandardSocketOptions.IP_MULTICAST_LOOP)); // true
```

đây vẫn **chưa chứng minh local receiver đã nhận multicast packet**. Còn nhiều điều kiện khác:

- Có interface phù hợp và route/IGMP/MLD hoạt động.
- Group đúng family, scope và port.
- Receiver bound wildcard và membership vẫn valid.
- Firewall/router/AP/VPN không drop.
- Không overflow socket receive buffer.
- Datagram application buffer đủ chỗ.
- OS loopback semantics và provider behavior phù hợp.
- Sender thật sự gửi đúng destination và outgoing interface.

### 31.1. Option đo được vs packet captures

`getOption` là phép đọc cấu hình tầng socket. Để xác minh trên network path, cần end-to-end test, thống kê packets, packet capture ở môi trường được phép, và không gửi data bí mật. Không suy đoán QoS từ một boolean.

### 31.2. Diagnostic logs cần privacy

Có thể log tên option, có supported không, actual buffer size, protocol family, tên interface đã được cho phép và exception category. Không tự log payload, tokens hoặc host credentials; địa chỉ IP cá nhân có thể là dữ liệu cần bảo vệ theo sản phẩm.

## 32. Cách kiểm thử đúng: unit, integration và deploy QA

### 32.1. Unit tests

Kiểm logic:

- Nếu `supportedOptions` thiếu option bắt buộc, trả lỗi cấu hình.
- Nếu thiếu optional option, skip có báo metrics.
- TTL ngoài 0..255 bị từ chối trước khi set.
- Không gửi multicast khi chưa chọn đúng network interface.
- Không dùng `DatagramChannel` cho `TCP_NODELAY`.
- Không ngộ nhận nhận UDP datagram nhỏ khi destination buffer bị truncate.
- Phân biệt IPv4/IPv6 và no candidate NIC.

### 32.2. Loopback tests

- TCP options có thể set/get trên runtime.
- UDP unicast send/receive qua loopback.
- Test datagram boundary/truncation với buffer nhỏ.
- Kiểm option discovery và UnsupportedOperation.
- Không cần gửi multicast thật ra LAN để test phần logic.

### 32.3. Multicast integration tests

- Chọn NIC thực có up/multicast support.
- Set reuse before wildcard bind.
- Set `IP_MULTICAST_IF` cho sender khi cần.
- Join group và giữ MembershipKey.
- Gửi test payload nhỏ, có unique test ID và giới hạn.
- Xác minh receiver đúng group/interface/port.
- Test với loop true/false riêng, không mặc định semantics giống mọi OS.
- Test IPv4/IPv6 riêng với routing đúng.
- Đóng/drop key, không leak resources.

**Không nên làm multicast integration trên production LAN khi không có quyền**, vì group traffic có thể ảnh hưởng thiết bị khác. Dùng môi trường lab hoặc staging và địa chỉ group/ports do đội mạng cấp.

### 32.4. Deploy checks

- Runtime có đúng Java version.
- Container có NIC/hỗ trợ multicast hay không.
- SO_REUSEPORT behavior thực tế.
- Firewall, route, VPN và IGMP snooping.
- Buffer limits/throughput hợp workload.
- Logs quan sát option đã áp dụng và actual values.
- Không phụ thuộc một subclass exception cụ thể của OS.

## 33. Bảng QA của 10 chương trình runnable

| Chương trình | Đối tượng chính | Điều đã xác minh trên JDK24 Windows |
| --- | --- | --- |
| `OptionCatalogDemo` | NetworkChannel.supportedOptions | TCP/UDP/async có tập options khác; UDP SO_REUSEPORT false |
| `TcpOptionDemo` | SocketChannel | TCP_NODELAY/KEEPALIVE/REUSEADDR true; buffers positive |
| `ServerOptionsDemo` | ServerSocketChannel | SO_REUSEADDR trước bind; port loopback được cấp |
| `DatagramOptionsDemo` | DatagramChannel INET | Multicast TTL1, LOOP true, BROADCAST true, IP_TOS trong range |
| `OptionValidationDemo` | Invalid/unsupported options | TTL -1/256, negative SNDBUF, TCP_NODELAY-on-UDP bị từ chối |
| `UdpDatagramBoundaryDemo` | UDP unicast loopback | Datagram HELLO 5 byte bị cắt còn HEL vì buffer3; datagram Z độc lập |
| `OptionalReusePortDemo` | SO_REUSEPORT gating | False trên test Windows; skip thay vì lỗi |
| `AsyncSocketOptionDemo` | AsynchronousSocketChannel | KEEPALIVE/NODELAY true, không support multicast/linger trong test |
| `MulticastInterfaceDemo` | NIC + multicast membership | Interface đủ điều kiện, join/drop thành công trên test machine |
| `FamilyCapabilitiesDemo` | INET vs INET6 | Cả hai mở được trên test machine; không hardcode ở runtime khác |

Các chương trình compile bằng `javac --release 17 -encoding UTF-8`, không cần Internet. Các test có dùng loopback hoặc join local group; không gửi broadcast/multicast tới LAN thật. Những giá trị môi trường như `reusePortOnUdp=false` và `joinSucceeded=true` **chỉ là kết quả trên máy kiểm thử**, không là guarantee của Java API.

### 33.1. Điều không nên assert

- Socket send buffer luôn đúng 16384 chỉ vì setOption(16384).
- Máy luôn có ba network interfaces hoặc một NIC tên `eth0`.
- SO_REUSEPORT luôn supported, kể cả đã có hằng số.
- Tất cả OS nhận multicast loopback khi option true.
- Máy luôn có IPv6 và multicast routing.
- UDP datagram không bao giờ bị mất/duplicate.
- Multicast join thành công đồng nghĩa mọi router sẽ forward.
- Tất cả socket types hỗ trợ cùng tập options.

## 34. Những lỗi thường gặp

1. Dùng `TCP_NODELAY` trên UDP → option không hỗ trợ.
2. Dùng `IP_MULTICAST_TTL` trên TCP → sai kiểu channel.
3. Không kiểm `supportedOptions` rồi gọi `SO_REUSEPORT` mọi nơi.
4. Nhầm `SO_REUSEADDR` và `SO_REUSEPORT` có semantics giống nhau.
5. Đặt reuse options sau `bind` rồi kỳ vọng thay đổi retroactively.
6. Dùng số liệu actual buffer size như request phải được OS giữ nguyên.
7. Coi `SO_KEEPALIVE` là heartbeat tầng ứng dụng với thời hạn ngắn.
8. Bật `TCP_NODELAY` vô điều kiện vì nghĩ luôn nhanh hơn.
9. Bật `SO_LINGER` trên non-blocking socket rồi dựa vào close behavior chưa được định nghĩa.
10. Coi `IP_TOS` tạo guaranteed QoS.
11. Bật `SO_BROADCAST` rồi gửi multicast group, tưởng hai khái niệm giống.
12. Set `IP_MULTICAST_IF` nhưng quên `join(group,interface)` ở receiver.
13. Dùng tên interface `eth0` hardcode cho cả Windows/macOS.
14. Bind multicast receiver vào specific IP, không kiểm wildcard behavior.
15. Mở `INET6` rồi join group IPv4 mà không xem support.
16. Giả định multicast TTL1 luôn tới được mọi host LAN.
17. Giả định `IP_MULTICAST_LOOP=true` tương đương đã nhận local packet.
18. Dùng `SO_RCVBUF` để che giấu destination ByteBuffer quá nhỏ của UDP receive.
19. Thử `DatagramChannel.receive` nhiều lần để lấy bytes bị cắt từ datagram trước.
20. Không giới hạn payload/frame/retries khiến DoS hoặc memory pressure.
21. Không đóng `DatagramChannel`, `SocketChannel` hoặc `MembershipKey`.
22. Coi multicast group là kênh an toàn/được xác thực.
23. Coi default option value là cố định giữa OS.
24. Copy stdout kiểm thử Windows và dùng làm golden test cho mọi machine.
25. Gán `SO_REUSEPORT` cho Java 7: thực tế option này được thêm từ Java 9.
26. Không phân biệt “setOption trả thành công” với “remote đã nhận datagram”.
27. Không kiểm exception khi OS từ chối privileged operations.
28. Dùng một option performance làm lý do bỏ qua đo benchmark/network metrics.

## 35. Bài tập thực hành

**Bài 1.** `SocketOption<NetworkInterface>` có thể nhận tên NIC kiểu String trực tiếp không? **Không**; tìm `NetworkInterface` cụ thể.

**Bài 2.** Vì sao `StandardSocketOptions` không có nghĩa mọi option đều supported? **Vì socket type, provider, OS, protocol family khác nhau.**

**Bài 3.** Tên method kiểm option nào channel hỗ trợ? **supportedOptions()**.

**Bài 4.** `SO_SNDBUF` set 16384 nhưng get 32768, có phải bug Java? **Không nhất thiết**; option là hint và OS điều chỉnh.

**Bài 5.** `TCP_NODELAY=true` tắt cơ chế gì? **Nagle algorithm của TCP**.

**Bài 6.** Vì sao không bật NODELAY cho mọi hệ thống? **Có thể tăng packet overhead; cần benchmark.**

**Bài 7.** `SO_KEEPALIVE=true` có bảo đảm phát hiện peer chết trong 2 giây? **Không**, timing OS-dependent.

**Bài 8.** `SO_LINGER` nên dùng thế nào trên non-blocking channel? **Không dựa vào behavior close chưa được định nghĩa; dùng khi có lý do rõ, ưu tiên blocking-mode semantics.**

**Bài 9.** SO_REUSEADDR có phải load-balancing nhiều TCP listeners giống SO_REUSEPORT? **Không**; semantics khác theo OS.

**Bài 10.** SO_REUSEPORT lần đầu xuất hiện ở phiên bản nào? **Java 9**, không phải Java 7.

**Bài 11.** SO_REUSEPORT bị supportedOptions trả false. Có nên set rồi catch và bỏ qua tất cả không? **Nên kiểm capability trước; optional thì skip, mandatory thì fail config.**

**Bài 12.** Multicast IF là địa chỉ group hay local NIC? **Local NetworkInterface để gửi**, không tự join group.

**Bài 13.** IPv4 multicast TTL có dải hợp lệ nào? **0..255**.

**Bài 14.** TTL=1 có bảo đảm một packet sẽ tới các máy trong cùng LAN không? **Không**; routing/firewall/group membership còn quyết định.

**Bài 15.** IP_MULTICAST_LOOP=true có hứa mọi local receiver đều thấy packet? **Không**, semantics phụ thuộc hệ thống.

**Bài 16.** IPv6 channel join IPv4 multicast group có portable không? **Không**, chọn đúng ProtocolFamily.

**Bài 17.** Multicast receive bind vào wildcard hay địa chỉ specific? **Wildcard được khuyến cáo**, specific address có thể implementation-specific.

**Bài 18.** Khi cần nhiều multicast receivers bind một port, set option nào trước bind? **SO_REUSEADDR=true**, nhưng vẫn xét OS policy.

**Bài 19.** Method nào join group? **DatagramChannel.join(group,netIf)** qua MulticastChannel API.

**Bài 20.** Làm sao rời group? **MembershipKey.drop()** hoặc close channel.

**Bài 21.** Source-specific multicast có chắc supported mọi OS? **Không**, có thể ném UnsupportedOperationException.

**Bài 22.** Có thể nhận nốt bytes LO của UDP datagram HELLO bị cắt ở receive đầu không? **Không**, phần dư datagram bị bỏ.

**Bài 23.** TCP receiver buffer3 có làm mất vĩnh viễn 2 byte còn lại của stream5 không? **Không**, TCP stream còn bytes để đọc tiếp nếu kết nối hoạt động.

**Bài 24.** SO_BROADCAST dùng để join multicast group đúng không? **Không**, broadcast IPv4 khác multicast.

**Bài 25.** IP_TOS=16 có bảo đảm network priority ở router không? **Không**, chỉ là hint.

**Bài 26.** Có nên dựa exception message “Connection refused” để chọn OS-specific logic? **Không**; phân loại exception/cause và connectivity state.

**Bài 27.** Vì sao không hardcode một NIC đầu tiên trong enumeration? **Thứ tự/khả năng/route thay đổi; chọn theo cấu hình và khả năng.**

**Bài 28.** Multicast join local thành công có chắc mạng cloud hỗ trợ group routing không? **Không**.

**Bài 29.** Nếu option tối ưu không hỗ trợ nhưng app vẫn đúng, hành vi nào phù hợp? **Skip có báo/metrics hoặc dùng default.**

**Bài 30.** Nếu một option là điều kiện correctness bắt buộc, nên làm gì? **Fail-fast/explicit fallback được kiểm chứng, không giả success.**

**Bài 31.** Khi test cross-platform, nên assert exact SO_RCVBUF value? **Không**, chỉ assert các invariants thuộc hợp đồng và đo actual separately.**

**Bài 32.** Nêu lý do multicast UDP không tự đảm bảo confidentiality/authentication/reliability. **UDP multicast là datagram group delivery; không có TLS/ACK/app identity mặc định.**

## 36. Checklist trước khi đưa vào dự án

- [ ] Chọn đúng channel: TCP client/server, asynchronous TCP, UDP hay multicast.
- [ ] Dùng `supportedOptions()` trước khi phụ thuộc option.
- [ ] Dùng kiểu `SocketOption<T>` đúng (Boolean, Integer, NetworkInterface).
- [ ] Đặt `SO_REUSEADDR`/`SO_REUSEPORT` trước bind nếu cần.
- [ ] Không mặc định SO_REUSEPORT có dù Java 17 có hằng số.
- [ ] Không gán SO_REUSEPORT cho Java 7; mốc đúng là Java 9.
- [ ] Không tin `SO_SNDBUF`/`SO_RCVBUF` giữ đúng requested sizes.
- [ ] Chỉ bật `TCP_NODELAY` sau khi hiểu trade-offs và benchmark.
- [ ] Không dùng `SO_KEEPALIVE` thay application heartbeat.
- [ ] Không dựa vào `SO_LINGER` trên non-blocking sockets.
- [ ] Với UDP, không dùng TCP-specific options.
- [ ] Với multicast, chọn ProtocolFamily khớp group.
- [ ] Kiểm `NetworkInterface` up, multicast support và IP family.
- [ ] Cân nhắc outgoing `IP_MULTICAST_IF` rõ ràng trên nhiều NIC.
- [ ] Đặt TTL/hop limit đúng phạm vi, không dùng TTL thay security.
- [ ] Không coi LOOP=true là bằng chứng reception.
- [ ] Bind wildcard và bật reuse trước bind cho multicast receiver khi cần.
- [ ] Drop MembershipKey và đóng DatagramChannel.
- [ ] Không mặc định source-filter multicast được hỗ trợ.
- [ ] Không dùng `SO_BROADCAST` thay multicast join.
- [ ] Không coi `IP_TOS` là guaranteed QoS.
- [ ] UDP receive buffer phải đủ chứa một datagram muốn giữ trọn.
- [ ] Không xử lý UDP như TCP stream hoặc TCP như message-oriented UDP.
- [ ] Test IPv4, IPv6, NIC, VPN/container/cloud riêng.
- [ ] Có fallback hoặc fail-fast cho option bắt buộc không hỗ trợ.
- [ ] Giới hạn datagram size, memory, bandwidth và resource exhaustion.
- [ ] Không gửi multicast/broadcast trên production LAN để kiểm thử tùy tiện.
- [ ] Cấu hình authentication/encryption nếu dữ liệu nhạy cảm.
- [ ] Log supported/actual option values và failure categories an toàn.
- [ ] Bảo đảm Java target `--release 17` trong examples và CI.
- [ ] Dùng public Java APIs hiện hành, không phụ thuộc JDK internal classes.

## 37. Tài liệu chính thức Java 17

- [`StandardSocketOptions`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/StandardSocketOptions.html): danh sách options, typed values, system-dependent details, mốc Java 9 của `SO_REUSEPORT`.
- [`SocketOption<T>`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/SocketOption.html): tên và kiểu option.
- [`NetworkChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/NetworkChannel.html): `supportedOptions`, `getOption`, `setOption` và bind.
- [`SocketChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html): stream sockets và standard TCP option list.
- [`ServerSocketChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ServerSocketChannel.html): TCP listener options/bind.
- [`AsynchronousSocketChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousSocketChannel.html): asynchronous TCP option list.
- [`AsynchronousServerSocketChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousServerSocketChannel.html): asynchronous listener option list.
- [`DatagramChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/DatagramChannel.html): UDP datagrams, IPv4/IPv6 family, multicast option list.
- [`MulticastChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/MulticastChannel.html): join/leave groups, wildcard bind, SO_REUSEADDR, family/platform dependencies.
- [`MembershipKey`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/MembershipKey.html): isValid/drop/source filtering.
- [`NetworkInterface`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/NetworkInterface.html): chọn network interface theo năng lực.
- [`StandardProtocolFamily`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/StandardProtocolFamily.html): `INET`, `INET6`.
- [`DatagramSocket`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/DatagramSocket.html): so sánh UDP, multicast và platform dependencies.

**Tổng kết:** Tên option chuẩn tạo nên một API typed chung, **không xóa sự khác biệt của TCP/UDP/multicast, OS, NIC và phiên bản Java**. Trước tiên chọn đúng channel/protocol family, kiểm `supportedOptions()`, set option vào đúng thời điểm (đặc biệt trước bind), đọc actual value nếu cần và test tính năng thật trên môi trường mục tiêu. `SO_REUSEPORT` là Java 9+ và có thể không được hỗ trợ; `SO_SNDBUF`/`SO_RCVBUF` chỉ là hints; `IP_MULTICAST_IF`, `TTL` và `LOOP` không tự tạo group membership hoặc đảm bảo multicast delivery. Với mạng không tin cậy, cần thêm framing, validation, giới hạn tài nguyên và bảo mật ở tầng ứng dụng.