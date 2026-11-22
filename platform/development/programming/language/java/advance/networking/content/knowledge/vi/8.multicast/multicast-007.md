# DatagramChannel, MembershipKey và lọc nguồn khi nền tảng hỗ trợ

## Mục tiêu

**IP multicast** cho phép một bên gửi UDP datagram tới một địa chỉ **nhóm**; các máy/ứng dụng tham gia nhóm trên giao diện mạng phù hợp có thể nhận bản sao datagram. Trong Java NIO, `DatagramChannel` là kênh gửi/nhận UDP; `MembershipKey` đại diện quyền tham gia một nhóm multicast và cho phép rời nhóm hoặc điều chỉnh lọc nguồn **khi hệ điều hành/nền tảng hỗ trợ**.

Sau bài này, bạn có thể:

- Mở `DatagramChannel` theo họ địa chỉ `INET`/`INET6`, bind UDP port, chọn `NetworkInterface`, rồi `join` multicast group.
- Hiểu các thông tin trong `MembershipKey`: `group()`, `networkInterface()`, `sourceAddress()`, `isValid()` và `drop()`.
- Phân biệt nhận **mọi nguồn** (*Any-Source Multicast*, ASM), nhận từ **nguồn chỉ định** qua `join(group, interface, source)`, và **chặn một nguồn** qua `MembershipKey.block(source)`.
- Xử lý `UnsupportedOperationException` khi multicast/source filtering không được hỗ trợ; biết tại sao `supportsMulticast()` chưa đủ để chứng minh khả năng **lọc theo nguồn**.
- Viết chương trình Java 17+ nhận multicast datagram có timeout bằng `Selector`, và một chương trình gửi để thử nghiệm trên mạng hỗ trợ multicast.
- Chẩn đoán lỗi chọn interface, family không khớp, firewall, IGMP/MLD, source IP sai và việc nhận datagram không được bảo đảm.

**Phạm vi bài:** IPv4/IPv6 IP multicast trên UDP thông qua Java NIO. Đây là cơ chế truyền dữ liệu nhóm, **không phải TCP**, không có bảo đảm nhận đủ, nhận đúng thứ tự hay chỉ một bản sao; lọc nguồn theo địa chỉ IP không thay thế xác thực và phân quyền ứng dụng.

## 1. Multicast, UDP datagram và việc tham gia nhóm

Một UDP endpoint thông thường gửi datagram đến một địa chỉ đích cụ thể. Với multicast, địa chỉ đích là **group address**, ví dụ IPv4 `239.192.0.42` (một địa chỉ dùng làm ví dụ trong không gian administratively scoped `239.0.0.0/8`). Nhiều receiver cùng `join` group này trên các interface phù hợp.

~~~text
                     UDP → 239.192.0.42:50001
sender (192.0.2.10) -------------------------------► mạng hỗ trợ multicast
                                                          │
                                     ┌────────────────────┴─────────────┐
                                     ▼                                  ▼
                           host A: receiver 1                  host B: receiver 2
                           join group on eth0                  join group on en0
                           bind UDP port 50001                 bind UDP port 50001
~~~

*Địa chỉ `192.0.2.10` trong sơ đồ là địa chỉ dành cho tài liệu, không phải sender hoạt động được; tên interface cũng chỉ mang tính ví dụ.*

Một thông điệp được gửi dưới dạng **một datagram UDP**. `DatagramChannel.receive(ByteBuffer)` lấy **một datagram** và trả `SocketAddress` nguồn; không ghép các datagram thành byte stream như TCP. Ứng dụng vẫn phải tự giải thích payload và quy định liệu có cần sequence number, kiểm tra trùng, retry hoặc thứ tự ở lớp ứng dụng.

Có ba địa chỉ/khái niệm khác nhau:

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| **Group IP** | Địa chỉ multicast mà receiver tham gia | `239.192.0.42` |
| **UDP port** | Cổng receiver bind để nhận datagram của ứng dụng | `50001` |
| **Source IP** | IP unicast thực tế mà datagram được gửi từ đó, dùng cho lọc nguồn | IP gắn với đường egress của sender |

`join(group, interface)` đăng ký **group và interface**, không tự bind socket vào UDP port cụ thể. Để nhận packet cho ứng dụng, channel còn cần bind cổng. Bộ lọc nguồn kiểm tra **địa chỉ IP nguồn**, không phải **source UDP port** hay nội dung payload.

Không chọn nhóm `224.0.0.x` tùy tiện để thử ứng dụng: một số địa chỉ multicast có phạm vi/ý nghĩa được dành riêng cho giao thức điều khiển. Chọn nhóm thử nghiệm phù hợp chính sách mạng, xác nhận với quản trị mạng, và đừng mặc định multicast được route qua Internet.

## 2. `DatagramChannel` khác `DatagramSocket` ra sao?

`DatagramChannel` thuộc `java.nio.channels`, triển khai `MulticastChannel` và `SelectableChannel`:

- `DatagramChannel.open(StandardProtocolFamily.INET)` tạo kênh UDP thuộc họ IPv4; `INET6` dành cho IPv6 nếu nền tảng hỗ trợ. Với multicast, nên chọn family **phù hợp đúng group IP**. `open()` không chỉ định family, nên không thuận lợi cho code multicast cần tính tương thích rõ ràng.
- `setOption(StandardSocketOptions.SO_REUSEADDR, true)` **trước khi bind** hỗ trợ nhiều listener multicast bind cùng cổng khi nền tảng cho phép; kết quả cụ thể vẫn do OS quyết định.
- `bind(new InetSocketAddress(port))` bind tới wildcard address với cổng đó; tài liệu Java khuyến nghị wildcard binding cho multicast. Bind vào một IP unicast cụ thể có thể làm nhận multicast phụ thuộc triển khai.
- `join(group, networkInterface)` tạo membership trên interface được chỉ rõ; `DatagramChannel.receive(ByteBuffer)` đọc datagram và đưa byte vào buffer.
- `configureBlocking(false)` cho phép đăng ký với `Selector`, thay vì block vô hạn ở `receive`. Nếu không dùng selector, kênh mặc định ở blocking mode.
- `setOption(StandardSocketOptions.IP_MULTICAST_IF, nic)` chọn **interface cho multicast gửi ra**; nó **không thay thế** đối số interface của `join` khi receiver đăng ký group.
- `setOption(StandardSocketOptions.IP_MULTICAST_TTL, 1)` đặt giới hạn hop cho multicast gửi ra, hay dùng để thử nghiệm mạng cục bộ. Nó không biến datagram thành reliable delivery.

`DatagramSocket` cũng có API UDP nhưng `DatagramChannel` phù hợp khi cần NIO `ByteBuffer`, `Selector` và `MembershipKey`. Không nhất thiết phải `connect()` để `send` hoặc `receive`; việc `DatagramChannel.connect(remote)` là ràng buộc UDP peer ở tầng kênh, **không phải TCP handshake**, và có thể hạn chế datagram từ nguồn khác. Với receiver multicast nhiều nguồn, ví dụ bên dưới dùng kênh **unconnected**.

## 3. `MembershipKey` quản lý việc tham gia nhóm

Có hai overload `join` quan trọng:

~~~java
MembershipKey allSources = channel.join(group, nic);

MembershipKey selectedSource = channel.join(group, nic, source);
~~~

Đây là đoạn minh họa dùng biến `channel`, `group`, `nic`, `source` đã được chuẩn bị; không phải chương trình độc lập.

| API | Ý nghĩa | Membership |
|---|---|---|
| `channel.join(group, nic)` | Nhận datagram tới group trên interface từ **mọi nguồn** có thể nhận | ASM / không chỉ định nguồn |
| `channel.join(group, nic, source)` | Chỉ nhận datagram gửi tới group từ **một IP nguồn unicast cụ thể** | Source-specific membership |
| `key.sourceAddress()` | `null` nếu membership không chỉ định nguồn; trả IP đã chọn nếu source-specific | Kiểm tra loại membership |
| `key.isValid()` | Membership vẫn còn hiệu lực theo đối tượng key hay không | Kiểm tra trạng thái |
| `key.drop()` | Rời membership; làm key không còn valid | Dọn tài nguyên |
| `key.block(source)` | Trên **ASM key**, chặn một IP nguồn nếu nền tảng hỗ trợ | Lọc nguồn kiểu exclude |
| `key.unblock(source)` | Gỡ nguồn đã block trên ASM key | Khôi phục nhận nguồn |

**Vòng đời:** key hợp lệ sau khi `join` thành công; `drop()` hoặc đóng `DatagramChannel` sẽ làm key vô hiệu. `isValid()` từ đó trả `false`. `drop()` trên key đã vô hiệu không gây thêm hiệu ứng. Tuy nhiên datagram vốn đã nằm trong socket receive buffer **vẫn có thể xuất hiện ngay sau khi drop/block**; đừng biến membership thành giả định “không còn một packet nào lập tức”.

**Membership là cặp/nhóm trạng thái của channel với group/interface và có thể thêm source.** Cùng channel:
- Gọi `join(group, nic)` hai lần với ASM membership đang tồn tại thường nhận lại key đại diện membership ấy.
- Có thể thêm nhiều **source-specific memberships** cho cùng group/interface để nhận từ nhiều source được phép; chúng có tác dụng cộng dồn.
- Không thể trộn **ASM membership** và **source-specific membership** cho **cùng group/interface trên cùng channel** theo cách tùy ý: các lệnh `join` tương ứng có thể ném `IllegalStateException`. Hãy chọn một chiến lược rõ ràng ngay từ đầu.

`MembershipKey.block(source)` **không dùng cho source-specific key**; gọi như vậy sẽ ném `IllegalStateException`. `unblock(source)` chỉ hợp lệ nếu source đó đã được block trước, và key vẫn valid.

## 4. Hai mô hình lọc nguồn: include và exclude

Giả sử group `239.192.0.42` có ba sender IP unicast `192.0.2.10`, `192.0.2.11` và `192.0.2.12` (địa chỉ tài liệu, chỉ để minh họa).

**ASM (Any-Source Multicast):**

~~~java
MembershipKey key = channel.join(group, nic);
~~~

Mục đích là đăng ký nhận từ mọi nguồn gửi tới group/interface theo cơ chế multicast mạng, nhưng datagram vẫn có thể bị mất do UDP, cấu hình mạng, firewall, queue hoặc interface sai.

**Include / source-specific membership:**

~~~java
MembershipKey key = channel.join(group, nic, allowedSource);
~~~

Đây là yêu cầu nhận **chỉ từ địa chỉ `allowedSource`** trên group/interface đã chọn. Source phải là **unicast IP**, cùng họ IPv4/IPv6 với group. Java có thể ném `UnsupportedOperationException` nếu hệ điều hành/network stack không hỗ trợ **source filtering**. Việc platform hỗ trợ join ASM **không suy ra** source-specific join được.

**Exclude / chặn một nguồn trên ASM key:**

~~~java
MembershipKey key = channel.join(group, nic);
key.block(blockedSource);
// ... Khi cần cho phép lại:
key.unblock(blockedSource);
~~~

`block`/`unblock` là khả năng tùy nền tảng. `block` có thể ném `UnsupportedOperationException`; `unblock` có thể ném `IllegalStateException` nếu nguồn chưa block hoặc key đã vô hiệu. Việc chặn không bảo đảm loại bỏ ngay các datagram cũ đã xếp hàng.

**Sự khác nhau:** source-specific join **đăng ký tập được phép** (*include*), còn ASM + `block` bắt đầu từ **mọi nguồn** rồi loại trừ một hoặc nhiều IP (*exclude*). Hai chế độ có semantics khác nhau; đừng thay include bằng exclude nếu cần chỉ một nguồn, và đừng tưởng `block` hoạt động trên SSM key.

### IGMP/MLD và tính phụ thuộc nền tảng

IPv4 multicast thường liên quan **IGMP**; lọc nguồn theo IPv4 liên quan khả năng IGMPv3 của OS và mạng. IPv6 dùng **MLD**, source filtering tương ứng với MLDv2. Không phải mọi OS, interface, NIC, switch, router, VM/container hay mạng Wi-Fi đều hỗ trợ đầy đủ các khả năng này.

`NetworkInterface.supportsMulticast()` là một bước kiểm tra hữu ích, nhưng **không phải phép kiểm tra chắc chắn source filtering**. Chỉ có thể biết yêu cầu tham gia/lọc hoạt động tại điểm gọi `join(..., source)`/`block(source)` và qua kiểm thử dữ liệu trên chính nền tảng, có tính đến sự thay đổi cấu hình mạng. API khai báo `UnsupportedOperationException`; cũng có thể gặp `IOException` vì lỗi mạng/OS.

## 5. Ví dụ Java 17+ nhận UDP multicast với tùy chọn lọc nguồn

Chương trình **`MulticastReceiveDemo.java`** nhận ba hoặc năm tham số:

~~~text
java MulticastReceiveDemo <group> <port> <interface>
java MulticastReceiveDemo <group> <port> <interface> include <source-ip>
java MulticastReceiveDemo <group> <port> <interface> exclude <source-ip>
~~~

- Ba tham số: join ASM, nhận từ nguồn bất kỳ.
- `include source-ip`: source-specific `join(group, nic, source)`, khi hệ thống hỗ trợ.
- `exclude source-ip`: ASM `join(group, nic)` rồi `MembershipKey.block(source)`, khi hệ thống hỗ trợ.

Chương trình giới hạn chờ bằng `Selector.select(5_000)`, rồi xử lý tối đa **một datagram** và kết thúc. Điều này giúp demo không đợi vô hạn. Cần cung cấp **tên network interface thật** do Java nhìn thấy, và group IP/port hợp lệ.

~~~java
import java.net.*;
import java.nio.*;
import java.nio.channels.*;
import java.nio.charset.StandardCharsets;

public class MulticastReceiveDemo {
    private static final int MAX_BYTES = 2048;

    static void usage() {
        System.out.println(
            "Usage: java MulticastReceiveDemo <group> <port> <interface>"
            + " [include|exclude <source-ip>]");
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 3 && args.length != 5) {
            usage();
            return;
        }

        String mode = args.length == 3 ? "all" : args[3];
        if (!mode.equals("all") && !mode.equals("include")
                && !mode.equals("exclude")
                || args.length == 5 && mode.equals("all")) {
            usage();
            return;
        }

        InetAddress group = InetAddress.getByName(args[0]);
        int port = Integer.parseInt(args[1]);
        if (!group.isMulticastAddress()
                || port < 1 || port > 65535) {
            throw new IllegalArgumentException("Invalid group or port");
        }

        NetworkInterface nic = NetworkInterface.getByName(args[2]);
        if (nic == null || !nic.isUp() || !nic.supportsMulticast()) {
            throw new IllegalArgumentException(
                "Interface unavailable or multicast unsupported");
        }

        InetAddress source = args.length == 5
            ? InetAddress.getByName(args[4]) : null;
        if (source != null && (source.isAnyLocalAddress()
                || source.isMulticastAddress()
                || (source instanceof Inet4Address)
                    != (group instanceof Inet4Address))) {
            throw new IllegalArgumentException(
                "Source must be a unicast address of the same IP family");
        }

        StandardProtocolFamily family =
            group instanceof Inet4Address
                ? StandardProtocolFamily.INET
                : StandardProtocolFamily.INET6;

        try (DatagramChannel channel = DatagramChannel.open(family)) {
            channel.setOption(StandardSocketOptions.SO_REUSEADDR, true);
            channel.bind(new InetSocketAddress(port));

            MembershipKey membership;
            try {
                if (mode.equals("include")) {
                    membership = channel.join(group, nic, source);
                } else {
                    membership = channel.join(group, nic);
                    if (mode.equals("exclude")) {
                        membership.block(source);
                    }
                }
            } catch (UnsupportedOperationException ex) {
                System.err.println(
                    "Multicast/source filtering unsupported: " + ex);
                return;
            }

            try {
                System.out.println("Joined " + group.getHostAddress()
                    + " on " + nic.getName()
                    + " with mode=" + mode);

                channel.configureBlocking(false);
                try (Selector selector = Selector.open()) {
                    channel.register(selector, SelectionKey.OP_READ);
                    int ready = selector.select(5_000);
                    if (ready == 0) {
                        System.out.println("No datagram ready");
                        return;
                    }
                    selector.selectedKeys().clear();

                    ByteBuffer buffer = ByteBuffer.allocate(MAX_BYTES);
                    SocketAddress sender = channel.receive(buffer);
                    if (sender == null) {
                        System.out.println("No datagram ready");
                        return;
                    }

                    buffer.flip();
                    String message = StandardCharsets.UTF_8
                        .decode(buffer).toString();
                    System.out.println("From " + sender + ": " + message);
                }
            } finally {
                membership.drop();
            }
        }
    }
}
~~~

### Tại sao code được viết như vậy?

1. `group.isMulticastAddress()` kiểm tra địa chỉ nhóm; `port` nằm trong 1..65535. Đối số `source` phải là địa chỉ unicast **cùng IP family**. Để phép thử có thể tái lập, hãy truyền **địa chỉ IP literal** thay vì hostname phụ thuộc DNS.
2. `NetworkInterface.getByName(name)` tìm interface theo **system name**. `nic.isUp()` và `nic.supportsMulticast()` loại sớm những interface rõ ràng không phù hợp; chúng không kiểm tra khả năng filtering.
3. `DatagramChannel.open(family)` tránh phụ thuộc family mặc định. `SO_REUSEADDR` được đặt trước bind wildcard port.
4. Ba nhánh `all/include/exclude` tạo các membership khác nhau. Khi `UnsupportedOperationException` xảy ra, demo **báo rõ và dừng**, không âm thầm đổi sang “nhận mọi nguồn”.
5. `membership.drop()` trong `finally` rời group ngay cả khi timeout hoặc xử lý dữ liệu thất bại; khối `try (channel)` đóng kênh trong mọi đường thoát. Nếu `block` thất bại trước khi vào khối `finally` thì khối `try (channel)` vẫn đóng channel và hủy membership.
6. `configureBlocking(false)` + `Selector` tránh `receive` chờ mãi; khi selector không báo readiness, chương trình in `No datagram ready`. Ngay cả sau readiness, `receive` có thể trả `null` trong nonblocking mode; luôn kiểm tra.
7. `ByteBuffer.flip()` chuẩn bị đọc những byte đã nhận. `receive` trả `SocketAddress` nguồn bao gồm IP và UDP port, nên có thể quan sát **IP nguồn thực tế** để cấu hình include/exclude.
8. Payload được coi là UTF-8 **chỉ cho demo văn bản**. Một datagram có thể là binary; buffer cố định 2048 byte có thể làm datagram lớn bị cắt. Hệ thống thật cần quy ước kích thước tối đa, kiểm tra lỗi encoding và định dạng payload.

Dữ liệu multicast **không đảm bảo đến trước deadline**. Không nhận được packet trong năm giây không có nghĩa group rỗng, filtering sai hay API không hoạt động; có thể không có người gửi, firewall chặn, interface sai hoặc cơ chế multicast mạng chưa sẵn sàng.

## 6. Chương trình gửi UDP multicast để thử nghiệm

File **`MulticastSendDemo.java`** sau gửi **một datagram** tới group/port, chọn interface egress và TTL 1 để hạn chế phạm vi thử nghiệm:

~~~java
import java.net.*;
import java.nio.channels.DatagramChannel;
import java.nio.charset.StandardCharsets;

public class MulticastSendDemo {
    public static void main(String[] args) throws Exception {
        if (args.length != 4) {
            System.out.println(
                "Usage: java MulticastSendDemo <group> <port> <interface> <text>");
            return;
        }

        InetAddress group = InetAddress.getByName(args[0]);
        int port = Integer.parseInt(args[1]);
        NetworkInterface nic = NetworkInterface.getByName(args[2]);
        if (!group.isMulticastAddress()
                || port < 1 || port > 65535 || nic == null
                || !nic.isUp() || !nic.supportsMulticast()) {
            throw new IllegalArgumentException("Invalid multicast config");
        }

        StandardProtocolFamily family =
            group instanceof Inet4Address
                ? StandardProtocolFamily.INET
                : StandardProtocolFamily.INET6;

        try (DatagramChannel channel = DatagramChannel.open(family)) {
            channel.setOption(StandardSocketOptions.IP_MULTICAST_IF, nic);
            channel.setOption(StandardSocketOptions.IP_MULTICAST_TTL, 1);
            int sent = channel.send(StandardCharsets.UTF_8.encode(args[3]),
                new InetSocketAddress(group, port));
            System.out.println("Sent bytes: " + sent);
        }
    }
}
~~~

Sender không cần join group nếu chỉ gửi; `IP_MULTICAST_IF` chỉ định interface đi ra. `IP_MULTICAST_TTL=1` là cấu hình multicast hop limit trên kênh; nó không đảm bảo packet được nhận, và cấu hình multicast loopback/firewall của OS vẫn ảnh hưởng tới thử nghiệm trên cùng một máy.

**Biên dịch hai file:**

~~~bash
javac -encoding UTF-8 MulticastReceiveDemo.java MulticastSendDemo.java
~~~

**Trường hợp không truyền tham số** là kiểm tra cú pháp/chạy được mà không phụ thuộc mạng:

~~~bash
java MulticastReceiveDemo
~~~

Stdout chính xác:

~~~text
Usage: java MulticastReceiveDemo <group> <port> <interface> [include|exclude <source-ip>]
~~~

Tương tự, `java MulticastSendDemo` in chính xác:

~~~text
Usage: java MulticastSendDemo <group> <port> <interface> <text>
~~~

Hai chương trình Java đã được thử biên dịch trong JShell, và các nhánh usage cho đầu ra như trên. **Không có stdout cố định cho phần nhận packet thực**: IP nguồn, source port, hỗ trợ multicast và thời điểm packet đến phụ thuộc mạng.

### Chạy thử khi mạng hỗ trợ multicast

Trước hết xác định **tên interface thực** mà JVM nhìn thấy, chẳng hạn `eth0`, `en0` hay một tên khác. Có thể dùng JShell (Java 17+):

~~~java
import java.net.NetworkInterface;
NetworkInterface.networkInterfaces().forEach(
    n -> System.out.println(n.getName() + " | " + n.getDisplayName()));
~~~

Đoạn trên dành cho JShell, không phải source file `main` độc lập. Chọn interface **đang up, hỗ trợ multicast** và phù hợp đường gửi/nhận, không chọn ngẫu nhiên loopback/Wi-Fi.

Trên **terminal A** (thay `<if-name>` bằng system name thật):

~~~bash
java MulticastReceiveDemo 239.192.0.42 50001 <if-name>
~~~

Trên **terminal B**, chạy ngay sau khi receiver join nhóm:

~~~bash
java MulticastSendDemo 239.192.0.42 50001 <if-name> hello
~~~

Nếu sender gửi đủ 5 byte UTF-8 và OS chấp nhận gửi, stdout sender:

~~~text
Sent bytes: 5
~~~

Nếu datagram thực sự đến đúng receiver trong khoảng thời gian chờ, receiver có dạng output minh họa:

~~~text
Joined 239.192.0.42 on eth0 with mode=all
From /192.0.2.10:54321: hello
~~~

Hai dòng trên là **ví dụ định dạng**, không phải cam kết đầu ra. Tên interface, IP nguồn và source port sẽ khác; `192.0.2.10` là địa chỉ tài liệu. Nếu không có packet, receiver có thể in `No datagram ready` rồi dừng. Đôi khi cần thử trên hai host trong cùng mạng hỗ trợ multicast thay vì một host mà loopback multicast bị chặn.

**Để kiểm tra include/exclude:** chạy mode `all` trước, ghi nhận **IP nguồn** thực tế từ `From /IP:port`. Sau đó mới truyền IP ấy vào lệnh thử:

~~~bash
java MulticastReceiveDemo 239.192.0.42 50001 <if-name> include <source-ip>
java MulticastReceiveDemo 239.192.0.42 50001 <if-name> exclude <source-ip>
~~~

Các lệnh là hai **lần chạy riêng**, không chạy hai mode cho cùng group/interface trên cùng channel. Nếu nền tảng không hỗ trợ source filtering, chương trình báo `Multicast/source filtering unsupported`. Nếu mode `include` nhận từ đúng IP đã chọn, packet có thể được thấy; mode `exclude` yêu cầu chặn IP ấy. Kiểm thử mạng thực cần nhiều packet và quan sát qua nhiều lần vì UDP có thể mất packet hoặc còn dữ liệu xếp hàng.

## 7. Lọc nguồn ở kernel và lọc tại ứng dụng khác nhau

Nếu hệ thống không hỗ trợ `join(group, nic, source)` hay `block(source)`, **đừng tự động coi việc đổi sang ASM là cùng tính chất**. Có hai lựa chọn phải tường minh:

- **Fail closed:** khi ứng dụng yêu cầu chỉ nhận từ nguồn đã cho, từ chối khởi động/nhận dữ liệu nếu platform không thể thiết lập bộ lọc nguồn. Đây là cách ví dụ receiver áp dụng với `UnsupportedOperationException`.
- **Application-level filtering:** nếu sản phẩm cho phép fallback và mục tiêu chỉ là chọn dữ liệu để xử lý, có thể join ASM rồi nhận datagram, kiểm tra IP nguồn từ `SocketAddress` và **bỏ qua packet không khớp**. Cách này vẫn cho phép các packet bị loại **đi qua mạng và vào socket buffer**; không tạo membership nguồn cụ thể ở OS/network.

Đoạn xử lý ứng dụng minh họa, đặt **sau lời gọi `receive` trả về một `SocketAddress` khác null**:

~~~java
if (sender instanceof InetSocketAddress remote
        && remote.getAddress().equals(allowedSource)) {
    // Chỉ xử lý payload ứng dụng từ địa chỉ được chọn.
} else {
    // Bỏ qua datagram này tại lớp ứng dụng.
}
~~~

Đoạn trên **không phải chương trình độc lập** và không chứng minh datagram đáng tin. Lọc theo IP nguồn là điều kiện nhận dữ liệu, **không phải cơ chế xác thực mật mã**: UDP source IP có thể bị giả mạo trong một số điều kiện mạng. Thông điệp nhạy cảm cần cơ chế xác thực/kiểm tra toàn vẹn, giới hạn độ dài và format phù hợp.

Nên phân biệt:
- **Network/kernel source filter:** yêu cầu OS/network chỉ phân phối những nguồn phù hợp; có thể giảm công việc ứng dụng và lưu lượng được đưa vào socket, tùy triển khai.
- **Application filter:** luôn tiêu thụ packet rồi quyết định có xử lý payload hay không; phù hợp fallback có chủ đích nhưng không tương đương về hiệu năng/khả năng phân phối.

Không thay đổi giữa hai cách **âm thầm** trong sản phẩm cần tính chính xác hoặc bảo vệ dữ liệu; ghi rõ mode hoạt động và kiểm thử.

## 8. Gỡ lọc, rời group và quản lý tài nguyên

Ví dụ với ASM membership:

~~~java
MembershipKey key = channel.join(group, nic);
try {
    key.block(unwantedSource);   // Nếu OS hỗ trợ.
    // Xử lý các datagram phù hợp.
    key.unblock(unwantedSource); // Chỉ nếu đã block thành công.
} finally {
    key.drop();
}
~~~

Đây là **snippet minh họa**, giả định `channel`, `group`, `nic` và `unwantedSource` đã khởi tạo và bên gọi xử lý `IOException`/`UnsupportedOperationException`. Nếu `block` thất bại, `unblock` không được gọi; `drop` trong `finally` vẫn giúp rời membership. Trong chương trình receiver đầy đủ, key được drop khi dừng và channel được đóng bằng try-with-resources.

Các điểm cần nhớ:

- `drop()` chỉ rời **membership tương ứng**. Một channel có thể tham gia nhiều group/interface, hoặc nhiều source-specific memberships; cần giữ các key và dọn đủ từng membership khi kết thúc.
- `key.sourceAddress() == null` là key ASM; source-specific key trả source IP. Không dựa vào `sourceAddress()` để suy ra packet được xác thực.
- `key.isValid()` thể hiện membership chưa bị drop/channel chưa đóng; nó không bảo đảm switch/router đang thực sự chuyển tiếp packet.
- Sau `drop` hoặc `block`, datagram cũ có thể đã nằm trong queue của socket; phải tiếp tục kiểm tra điều kiện nghiệp vụ trước khi tin tưởng payload.
- `unblock` chỉ hợp lệ cho nguồn đã `block` thành công, trên key còn hiệu lực; không gọi nó từ code xử lý key source-specific.

Với listener sống lâu, nên có lifecycle: init channel, bind, join, nhận datagram với buffer bounded, xử lý lỗi/cancellation, drop membership và đóng channel. Kênh có thể đóng khi thread khác hủy; xử lý `ClosedChannelException` hoặc `AsynchronousCloseException` theo chính sách dừng, thay vì retry vô hạn.

## 9. Vấn đề mạng và giới hạn platform thường gặp

| Hiện tượng | Khả năng nguyên nhân | Cách kiểm tra |
|---|---|---|
| `IllegalArgumentException` ở `join` | Group không multicast, source không unicast, IPv4/IPv6 family lệch | Kiểm tra literal IP, `isMulticastAddress()`, `instanceof Inet4Address` |
| `UnsupportedOperationException` ở `open(INET6)` | IPv6 socket family không được hỗ trợ | Xác nhận IPv6 của OS/JVM |
| `UnsupportedOperationException` ở `join(group, nic)` | Nền tảng không hỗ trợ multicast hoặc socket không phù hợp | Thử interface/family đúng, xem capability OS |
| `UnsupportedOperationException` ở source-specific `join` hoặc `block` | OS/network stack không hỗ trợ source filtering | Ghi lỗi rõ ràng, chọn fail closed hoặc fallback có chủ đích |
| `IllegalStateException` khi gọi các loại `join` xen kẽ | Cùng group/interface đã có membership ASM hoặc SSM mâu thuẫn trên channel | Dùng chiến lược nhất quán; drop membership cũ trước khi đổi |
| `IllegalStateException` ở `unblock` | Chưa block nguồn hoặc key invalid | Theo dõi state và dùng `isValid()` nếu cần |
| `IOException` khi bind | Cổng đã dùng/chính sách port reuse khác nhau hoặc lỗi OS | Đặt `SO_REUSEADDR` trước bind; kiểm tra cổng và OS |
| Join thành công nhưng không thấy datagram | Sender chưa gửi, interface sai, firewall, VLAN, switch IGMP snooping, router TTL hoặc multicast bị chặn | Xác minh group/port/route/nic, thử sender và receiver cùng subnet |
| ASM nhận nhưng include không nhận | Sai IP nguồn, source filter không hỗ trợ, địa chỉ sender egress khác dự đoán | Đọc `SocketAddress` nguồn ở mode all rồi thử lại |
| UDP payload bị cắt/giải mã sai | Receive `ByteBuffer` nhỏ hơn datagram, binary không phải UTF-8 hoặc network lỗi | Giới hạn payload theo protocol, dùng buffer đủ lớn và kiểm tra định dạng |
| Sender gửi thành công, receiver không nhận | UDP không có delivery acknowledgment; multicast forwarding không được bảo đảm | Thêm application ack/sequence number nếu use case cần reliability |

**Chú ý độ lớn datagram:** với `DatagramChannel.receive(ByteBuffer)`, mỗi lần nhận tương ứng một datagram; khi datagram lớn hơn dung lượng còn lại của buffer, phần vượt có thể bị loại bỏ. Vì thế buffer 2048 trong demo chỉ thích hợp cho các payload nhỏ, đã biết giới hạn. Không được xem phần bị cắt là một “mảnh TCP” để ghép vào lần `receive` sau. Datagram bị truncate sẽ mất phần dư trong lần nhận đó.

**Chú ý multicast loopback:** bật/tắt `IP_MULTICAST_LOOP`, firewall và chính sách hệ điều hành có thể ảnh hưởng việc một sender trên cùng host có được receiver thấy hay không. Dùng một cặp host trên mạng thử nghiệm được phép multicast khi kiểm tra thực tế. Không suy ra “UDP gửi thành công” tức “mọi receiver đều nhận”.

**IPv6:** group IPv6 có scope và các quy tắc interface rõ ràng hơn; chọn `StandardProtocolFamily.INET6` cho group `Inet6Address`. Không giả định một kênh IPv6 có thể join group IPv4; điều đó phụ thuộc OS. Nguồn được lọc phải cùng IP family với group và có địa chỉ/route thích hợp.

## 10. Hiệu năng, tính đúng đắn và bảo mật

**Selector và CPU work:** demo nhận một datagram rồi decode text. Nếu trở thành multicast service nhiều packet/giây, tránh làm CPU nặng trực tiếp trong event loop; đặt queue có giới hạn, một worker đọc dữ liệu, worker riêng xử lý payload và áp backpressure/drop policy có số liệu. `DatagramChannel` có thể receive liên tiếp nhiều datagram, nhưng vòng lặp phải tôn trọng nonblocking mode và giới hạn thời gian mỗi lần xử lý.

**Không có flow control như TCP:** UDP multicast có thể mất hoặc đến lệch thứ tự, trùng gói hoặc bị lọc bởi mạng. Với dữ liệu cần đảm bảo, giao thức ứng dụng cần sequence number, định danh sender, phát hiện thiếu và phương án lấy lại dữ liệu; nhiều use case multicast chấp nhận best effort thay vì xây lại TCP.

**Không xem filter là firewall hoặc authentication:** lọc theo source IP giảm phạm vi nhận, không chống giả mạo, replay hay payload độc hại. Khi dữ liệu có thể không đáng tin, kiểm tra kích thước, định dạng, version/sequence và xác thực ở lớp ứng dụng. Nếu ứng dụng thực sự yêu cầu chỉ những sender được phê duyệt, cần kiểm soát bảo mật mạng và kiểm tra tính toàn vẹn thông điệp phù hợp.

**Quy mô và quota:** nhóm multicast trên NIC/socket có giới hạn của OS; thêm nhiều group/source memberships có chi phí; nhiều datagram tốc độ cao có thể khiến socket receive queue đầy. Đo `packets_received`, `decode_failures`, `application_drops`, độ trễ xử lý, lỗi join/filter và chênh lệch sequence thay vì chỉ đo tổng bytes.

## 11. Những hiểu lầm phổ biến

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| “`DatagramChannel.join` chọn UDP port.” | `bind` xác lập UDP port; `join` đăng ký group/interface |
| “`DatagramChannel.open()` luôn mở đúng IPv4.” | Family mặc định có thể phụ thuộc platform; multicast nên chỉ định `INET`/`INET6` |
| “Chỉ cần `InetAddress.isMulticastAddress()` là chắc nhận được.” | Còn cần interface, bind, OS, firewall, mạng và sender |
| “`supportsMulticast()` nghĩa là hỗ trợ source-specific filtering.” | Đây là hai khả năng khác nhau; `join(..., source)`/`block` có thể không được hỗ trợ |
| “`join(group, nic, source)` lọc theo source UDP port.” | Nguồn được lọc là **IP unicast**, không phải port |
| “`block(source)` dùng được trên mọi `MembershipKey`.” | Chỉ trên ASM key khi platform hỗ trợ, không dùng trên SSM key |
| “Đã gọi `drop()` thì không còn packet cũ nào trong buffer.” | Packet đã xếp hàng có thể vẫn được nhận |
| “`Selector.select(5000) == 0` chứng tỏ group không có sender.” | Chỉ không có readiness trong lượt chờ; cần kiểm tra nhiều nguyên nhân |
| “`receive()` giống `SocketChannel.read()` của TCP.” | Một lần `receive` đọc một UDP datagram, không phải TCP byte stream |
| “Không có source filtering thì cứ join ASM là tương đương.” | Application filtering sau receive không thay thế kernel/network filtering |
| “IP nguồn nằm trong allowlist là đã xác thực sender.” | UDP IP có thể bị giả mạo; cần authentication nếu use case yêu cầu |

## 12. Bài tập tự kiểm tra

1. Nêu khác biệt giữa `channel.bind(new InetSocketAddress(50001))` và `channel.join(group, nic)`. Vì sao cần cả hai?
2. Tại sao nên gọi `DatagramChannel.open(StandardProtocolFamily.INET)` khi group là IPv4, thay vì mặc định mở kênh bất kỳ?
3. Với ASM membership, `key.sourceAddress()` trả gì? Với source-specific membership trả gì?
4. Hãy mô tả chính xác khi nào dùng `join(group, nic, source)`, `key.block(source)` và `key.unblock(source)`.
5. Nền tảng hỗ trợ join multicast nhưng ném `UnsupportedOperationException` khi source-specific join. Tại sao không nên tự động đổi thành ASM mà không báo?
6. Khi receiver chạy mode `include` nhưng không thấy packet, làm sao xác định **source IP thực tế** của sender?
7. Trong mode `exclude`, nếu `block` thành công rồi ngay lập tức vẫn nhận một packet từ nguồn bị chặn, điều đó có nhất thiết chứng minh API lỗi không?
8. Nếu `ByteBuffer` chỉ còn 100 byte nhưng datagram có 500 byte, tại sao lần `receive` tiếp theo không cho 400 byte còn lại để ghép?
9. Vì sao `MembershipKey.isValid()` không chứng minh mạng đang chuyển tiếp packet?
10. Nếu ứng dụng phải xác thực sender, liệu lọc theo source IP đã đủ chưa? Nêu một cơ chế khác cần xem xét.

**Gợi ý đáp án:** (1) bind cổng vs join group/interface; (2) đảm bảo IP family đúng; (3) `null` vs source IP; (4) include một nguồn vs chặn/gỡ chặn nguồn trên ASM; (5) khác semantics và mức hạn chế mạng; (6) chạy mode all trước rồi xem `SocketAddress`; (7) packet có thể đã nằm trong receive queue; (8) UDP datagram có ranh giới, phần dư bị loại khi buffer không đủ; (9) key chỉ nói trạng thái membership ở API, không bảo đảm delivery; (10) cần authentication/integrity ở lớp ứng dụng khi dữ liệu yêu cầu.

## 13. Ghi nhớ

- **`DatagramChannel`** xử lý UDP datagram; để nhận multicast cần chọn IP family, bind wildcard UDP port, `join(group, interface)` phù hợp.
- **`MembershipKey`** gắn với membership; `drop()`/đóng kênh làm key invalid; `sourceAddress()` cho biết membership có chỉ định nguồn không.
- **Lọc nguồn chỉ khi nền tảng hỗ trợ:** `join(group, nic, source)` để include nguồn; ASM `key.block(source)` và `unblock(source)` để exclude/gỡ chặn. Chuẩn bị xử lý `UnsupportedOperationException`.
- **Không đánh đồng join thành công với nhận được packet**, hoặc filter IP với xác thực sender; UDP/multicast phụ thuộc nhiều lớp hệ thống và mạng.
- **Đo bằng thử nghiệm trên interface/mạng thực**, bảo toàn ranh giới datagram, giới hạn buffer và xác định chính sách fallback rõ ràng.

### Tài liệu tham khảo

- [Oracle Java SE 17 — DatagramChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/DatagramChannel.html)
- [Oracle Java SE 17 — MulticastChannel, join và platform dependencies](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/MulticastChannel.html)
- [Oracle Java SE 17 — MembershipKey, sourceAddress, block, unblock, drop](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/MembershipKey.html)
- [Oracle Java SE 17 — StandardSocketOptions](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/StandardSocketOptions.html)
- [RFC 3376 — Internet Group Management Protocol Version 3](https://www.rfc-editor.org/rfc/rfc3376.html)
- [RFC 3810 — Multicast Listener Discovery Version 2](https://www.rfc-editor.org/rfc/rfc3810.html)
