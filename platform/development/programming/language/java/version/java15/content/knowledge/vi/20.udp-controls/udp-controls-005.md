# Multicast bằng DatagramChannel và NetworkInterface trong Java 15+

## 1. Mục tiêu

**IP multicast** cho phép một bên gửi **một UDP datagram tới địa chỉ nhóm** để những socket đã **tham gia nhóm multicast** trên các network interface phù hợp có thể nhận được datagram đó. Đây không phải TCP, không phải UDP broadcast, và cũng không có lời hứa mọi thành viên sẽ nhận một bản tin.

Trong Java 15+ có thể sử dụng API Java NIO **`java.nio.channels.DatagramChannel`** kết hợp với **`java.net.NetworkInterface`**, **`MulticastChannel.join(...)`** và **`MembershipKey`**. Những API này có từ Java 7, vẫn được hỗ trợ ở Java hiện đại, và cho phép quản lý multicast bằng `ByteBuffer`, non-blocking I/O và `Selector`.

Bài này trả lời các câu hỏi trọng tâm:

1. **Group**, **interface**, **local UDP port** và **source IP** khác nhau thế nào?
2. Vì sao nên mở `DatagramChannel.open(StandardProtocolFamily.INET)` cho nhóm IPv4 hoặc `INET6` cho nhóm IPv6?
3. Thiết lập `SO_REUSEADDR`, bind **wildcard** rồi gọi `join(group, networkInterface)` theo thứ tự nào?
4. `IP_MULTICAST_IF`, `IP_MULTICAST_TTL` và `IP_MULTICAST_LOOP` có nhiệm vụ gì?
5. Dùng `MembershipKey` để kiểm tra membership, `drop`, `block`/`unblock` hoặc source-specific join ra sao?
6. Gửi bằng `send(ByteBuffer, SocketAddress)` và nhận bằng `receive(ByteBuffer)`; quản lý buffer, timeout và lỗi đúng cách.
7. Vì sao multicast cần chính sách **interface/routing/firewall**, và không được coi membership là bằng chứng đã nhận được packet hay đã xác thực sender?

**Giới hạn:** chỉ trình bày API và kiến thức **còn áp dụng hiện nay**, theo Java 15+ và JDK hiện đại. Ví dụ được biên dịch với `--release 15` nhưng nên chạy bằng một JDK được nhà cung cấp duy trì.

## 2. Kiến trúc IP multicast: một sender, nhiều receiver

Với UDP unicast, một packet gửi tới **một địa chỉ IP đích**. Với IP multicast, đích là **group address**; nhiều ứng dụng/socket trên một hay nhiều máy có thể tham gia nhóm để nhận datagram khi hệ điều hành và mạng chuyển phát được.

```text
                             UDP datagram
                             group 239.255.42.99:5000
       Sender  ─────────────────────┬──────────────────────┐
                                    │                      │
                          Multicast-aware network         │
                                    │                      │
                          Receiver A                 Receiver B
                          join(group, nicA)          join(group, nicB)
                          bind(*:5000)               bind(*:5000)
```

Sơ đồ chỉ minh họa ý tưởng: **không phải một packet chắc chắn được sao chép tới mọi socket**. Điều kiện thực tế gồm cấu hình network interfaces, multicast routing/switches, OS, IGMP/MLD, firewall, TTL/hop limit, network policies và membership còn hiệu lực.

### Các thành phần có ý nghĩa riêng

| Thành phần | Trong Java | Vai trò |
| --- | --- | --- |
| **Multicast group IP** | `InetAddress group` | Địa chỉ **nhóm nhận**; không phải IP của riêng một máy |
| **UDP port** | `InetSocketAddress(port)` | Cổng mà receiver **bind** để nhận các datagram gửi tới nhóm/cổng ấy |
| **Local interface** | `NetworkInterface ni` | Giao diện mạng mà máy này **tham gia nhóm**; ví dụ card Ethernet/Wi-Fi hoặc adapter khác |
| **Membership** | `MembershipKey` | Token thể hiện membership cụ thể của **channel + group + interface**, có thể thêm source IP |
| **Sender IP** | `SocketAddress` của `receive` | Endpoint nguồn của từng datagram; **không tự là danh tính đáng tin** |
| **Outgoing interface** | `IP_MULTICAST_IF` | Network interface dùng **gửi** multicast; không đồng nghĩa thao tác join để **nhận** |

Một ứng dụng vừa có thể gửi vừa có thể nhận. **Sender không nhất thiết phải join nhóm để gửi.** Receiver cần có membership còn hiệu lực trên interface phù hợp, và socket phải bind đúng cổng nhận.

### Multicast khác broadcast thế nào?

- **Unicast:** đích là một endpoint cụ thể; ví dụ `192.0.2.10:5000`.
- **IPv4 broadcast:** gửi tới địa chỉ broadcast của mạng/subnet khi mạng cho phép; không dựa trên `MembershipKey` của một multicast group.
- **Multicast:** gửi tới **group IP**, các receiver chọn tham gia nhóm; mạng có thể dùng IGMP/MLD để biết đường phân phối.

Không sử dụng `SO_BROADCAST` thay `join(...)`. `SO_BROADCAST` không phải điều kiện để gửi datagram multicast.

## 3. Địa chỉ nhóm: IPv4, IPv6 và phạm vi

### 3.1. IPv4 multicast

IPv4 multicast dùng không gian **224.0.0.0/4**. Không phải địa chỉ nào trong dải này cũng nên tùy ý sử dụng: có nhóm dành cho giao thức hệ thống, các phạm vi/địa chỉ đã được cấp phát và những yêu cầu vận hành riêng.

Trong bài học dùng địa chỉ minh họa **`239.255.42.99`**, thuộc không gian **administratively scoped IPv4 multicast (239.0.0.0/8)**. Đây là địa chỉ để **thử nghiệm trong mạng do bạn kiểm soát**, không phải một group toàn cầu được bảo đảm không xung đột. Trong sản phẩm thực, tổ chức nên **quản lý group address và port**, tránh trùng với ứng dụng khác.

```java
InetAddress group = InetAddress.getByName("239.255.42.99");
if (!group.isMulticastAddress()) {
    throw new IllegalArgumentException("Not a multicast address");
}
```

Đây là mảnh mã minh họa trong một method có `throws Exception` hoặc xử lý `UnknownHostException`.

### 3.2. IPv6 multicast

IPv6 multicast dùng địa chỉ bắt đầu bằng **`ff00::/8`**. Phạm vi multicast IPv6 được mã hóa trong địa chỉ (ví dụ các phạm vi link-local/site-local tương ứng); địa chỉ link-local đòi **scope/interface phù hợp**. Với nhóm IPv6, nên mở channel bằng `StandardProtocolFamily.INET6` và chọn `NetworkInterface` có IPv6 address tương ứng.

**Không** sử dụng channel IPv4 rồi giả định có thể join mọi group IPv6. Javadoc yêu cầu dùng đúng **protocol family** tương ứng group; khả năng trộn IPv4/IPv6 trên một socket là **phụ thuộc OS/JDK**, không portable.

### 3.3. Multicast không tự đi qua Internet hoặc router

- Không phải mọi switch/router/VPN/cloud network đều hỗ trợ IP multicast.
- **TTL/hop limit** giới hạn số hop; giá trị nhỏ thường giữ lưu lượng ở mạng cục bộ, không phải cơ chế an ninh.
- Những nhóm thuộc phạm vi local/administrative cần chính sách mạng phù hợp.
- NAT phổ thông và nhiều cloud VPC không tự định tuyến IP multicast giữa các vùng hoặc qua Internet.
- `NetworkInterface.supportsMulticast() == true` chỉ cho biết **interface được báo có khả năng multicast**; nó không bảo đảm group packets đã được router chuyển tới nơi nhận.

**Kiểm tra API join thành công và kiểm tra thực sự nhận datagram là hai phép thử khác nhau.**

## 4. NetworkInterface: chọn chính xác cổng đi/vào của máy

`java.net.NetworkInterface` mô tả một giao diện mạng **vật lý hoặc ảo**. Máy có thể có Ethernet, Wi-Fi, VPN, bridge, adapter của container/VM và loopback; mỗi interface có tên/id, tập địa chỉ IP và trạng thái riêng.

Những API quan trọng:

| API | Ý nghĩa |
| --- | --- |
| `NetworkInterface.getNetworkInterfaces()` | Liệt kê interfaces hiện tại |
| `NetworkInterface.getByName(String)` | Chọn một interface theo **tên trong hệ điều hành** |
| `NetworkInterface.getByInetAddress(InetAddress)` | Tìm interface có IP local nhất định |
| `getName()` / `getDisplayName()` | Tên kỹ thuật / tên hiển thị |
| `isUp()` | OS báo interface đang hoạt động |
| `supportsMulticast()` | OS báo có hỗ trợ multicast |
| `isLoopback()` | Có phải loopback interface không |
| `getInetAddresses()` | Liệt kê các địa chỉ IPv4/IPv6 trên interface |
| `getIndex()` | Index interface, hữu ích với IPv6 scoped addresses |

Ví dụ liệt kê các interface đang up và có multicast:

```java
for (NetworkInterface ni :
        java.util.Collections.list(NetworkInterface.getNetworkInterfaces())) {
    if (ni.isUp() && ni.supportsMulticast()) {
        System.out.println(ni.getName());
    }
}
```

Đây là đoạn minh họa cần import `java.net.NetworkInterface` và đặt trong method có `throws Exception`. Output tên interface **phụ thuộc hệ điều hành**, vì vậy không hard-code `eth0`, `en0` hay tên Windows trong hướng dẫn chung.

**Chọn interface theo môi trường triển khai**, không chỉ lấy phần tử đầu tiên từ enumeration: interface đầu tiên có thể là VPN, loopback, virtual bridge hoặc không có IPv4/IPv6 address phù hợp.

Trong ví dụ runnable bên dưới có mode `list` liệt kê interfaces đang up, hỗ trợ multicast **và có ít nhất một địa chỉ IPv4**. Sau đó chính người thực hành truyền tên interface đã chọn vào mode `join`, `receive` hoặc `send`.

**Network config có thể thay đổi khi JVM đang chạy.** Nếu interface bị tắt, đổi IP hoặc thay cấu hình VPN, ứng dụng cần kiểm tra/lấy lại thông tin interface và có kế hoạch tái tham gia nhóm; không giữ mặc định membership cũ luôn hoạt động.

## 5. Chuỗi thao tác chuẩn để nhận IPv4 multicast

Javadoc `MulticastChannel` khuyến nghị một cấu hình có tính portable hơn:

1. Mở channel với `DatagramChannel.open(StandardProtocolFamily.INET)` cho group IPv4.
2. Gọi `setOption(StandardSocketOptions.SO_REUSEADDR, true)` **trước khi bind** nếu có nhiều receiver cùng dùng một group/port.
3. `bind(new InetSocketAddress(port))` tới **wildcard address** (mọi địa chỉ local phù hợp), **không** nhất thiết bind vào group IP hoặc một IP local cụ thể.
4. Chọn `NetworkInterface ni` có hỗ trợ multicast.
5. Gọi `MembershipKey key = channel.join(group, ni)` để đăng ký nhận datagram gửi tới group trên interface ấy.
6. Dùng `channel.receive(ByteBuffer)` để nhận; giải mã đúng số bytes thực tế đã đọc.
7. Trong `finally`, `key.drop()` hoặc đóng channel để thoát nhóm.

Mẫu code:

```java
try (DatagramChannel channel =
         DatagramChannel.open(StandardProtocolFamily.INET)) {
    channel.setOption(StandardSocketOptions.SO_REUSEADDR, true);
    channel.bind(new InetSocketAddress(5000)); // Wildcard: port 5000

    MembershipKey key = channel.join(group, ni);
    try {
        ByteBuffer buffer = ByteBuffer.allocate(2048);
        SocketAddress sender = channel.receive(buffer);
        buffer.flip();
        // Xử lý đúng buffer.remaining() bytes và kiểm tra sender/payload.
    } finally {
        key.drop();
    }
}
```

Đây là **mảnh minh họa**, giả định có biến `group` và `ni`, các import `java.net.*`, `java.nio.*`, `java.nio.channels.*`. `receive` ở chế độ blocking có thể **đợi vô hạn** nếu chưa có packet, nên ví dụ hoàn chỉnh dùng `Selector`/timeout thay vì blocking vô hạn.

### 5.1. Vì sao bind wildcard?

Multicast group address là một **đích logic của packets**, không phải địa chỉ unicast của card mạng. Khi bind socket vào một **specific unicast address** thay vì wildcard, Javadoc cảnh báo việc nhận multicast có thể **phụ thuộc OS**. Bind wildcard + đúng UDP port thường là cách có tính portable tốt hơn.

`new InetSocketAddress(port)` biểu diễn wildcard local bind cho cổng `port`. Nếu cần nhiều receiver processes trên cùng host và cùng group/port, thiết lập `SO_REUSEADDR` **trước** bind. Một số OS còn có `SO_REUSEPORT` nhưng **không được bảo đảm** được hỗ trợ ở mọi nền tảng; không mặc định dùng nó hoặc phụ thuộc việc load balancing giống nhau giữa OS.

### 5.2. join có thật sự “tạo nhóm” không?

`channel.join(group, ni)` **không tạo** một multicast group toàn cầu hay yêu cầu tất cả routers định tuyến ngay lập tức. Nó yêu cầu OS đăng ký membership tại **interface** đã chọn. Nhiều receiver trên nhiều host có thể cùng đăng ký group này; một channel cũng có thể join **nhiều group** hoặc **cùng group trên nhiều interfaces**, nếu OS/JVM có khả năng.

**Join thành công ≠ chắc chắn nhận được datagram.** Network route, multicast snooping, firewall, loopback behavior và việc sender dùng đúng outgoing interface/TTL vẫn quyết định hiệu quả thực tế.

## 6. MembershipKey: vòng đời join, drop và metadata

`MulticastChannel.join(group, ni)` trả về một **`java.nio.channels.MembershipKey`**:

```java
MembershipKey key = channel.join(group, ni);

System.out.println(key.isValid());          // true ngay khi join
System.out.println(key.group().equals(group));
System.out.println(key.networkInterface().equals(ni));
System.out.println(key.sourceAddress());     // null với any-source join

key.drop();
System.out.println(key.isValid());          // false sau khi drop
```

Đây là đoạn minh họa giả định các biến đã chuẩn bị. `MembershipKey` có các API:

| API | Ý nghĩa |
| --- | --- |
| `isValid()` | Membership hiện còn hiệu lực không |
| `drop()` | Thoát membership; key trở thành invalid |
| `channel()` | Channel mà membership được tạo trên |
| `group()` | Địa chỉ multicast group |
| `networkInterface()` | Interface của membership |
| `sourceAddress()` | `null` cho **any-source membership**; địa chỉ unicast nếu source-specific |
| `block(source)` / `unblock(source)` | Lọc source IP cho **any-source** key, khi OS hỗ trợ |

**`key.drop()` không đóng `DatagramChannel`.** Bạn có thể tiếp tục dùng channel cho datagrams khác hoặc join lại group. Khi channel đóng, các memberships liên quan cũng bị drop; keys trở nên invalid.

**Drop không xóa chắc chắn packet đã xếp hàng.** Javadoc nêu sau khi drop có thể vẫn đọc được datagrams còn nằm trong receive buffer. Nếu ứng dụng cần ranh giới phiên, dùng message ID/sequence và xác thực dữ liệu, không chỉ kiểm tra `isValid()`.

### 6.1. Gọi `join(group, ni)` nhiều lần

Với **cùng group và cùng interface** và đã có **any-source membership**, gọi `join(group, ni)` lần nữa trên **cùng channel** thường trả lại `MembershipKey` đại diện cho membership ấy. Đừng suy nghĩ mỗi lần gọi tạo một “subscriber độc lập” trên cùng channel.

Nếu channel đã có **source-specific memberships** cho group/interface đó, việc xin thêm **any-source membership** có thể ném `IllegalStateException`. Chiều ngược lại cũng vậy. Điều này bảo vệ tính nhất quán của bộ lọc.

Nếu một ứng dụng cần những chính sách lọc khác nhau, hãy tổ chức channel/membership rõ ràng; tránh trộn any-source và source-specific trên cùng (group, interface) của cùng channel.

## 7. Network options khi gửi multicast

Đối với **sender**, ba option quan trọng:

| Option | Kiểu | Vai trò |
| --- | --- | --- |
| `StandardSocketOptions.IP_MULTICAST_IF` | `NetworkInterface` | Chọn **outgoing interface** dùng gửi multicast |
| `StandardSocketOptions.IP_MULTICAST_TTL` | `Integer` | Số hop/IP TTL cho multicast; với IPv4 thường giá trị nhỏ để giới hạn phạm vi |
| `StandardSocketOptions.IP_MULTICAST_LOOP` | `Boolean` | Có cho phép multicast datagram vòng về các receiver local không; **ngữ nghĩa chính xác phụ thuộc hệ điều hành** |

Cấu hình sender IPv4:

```java
try (DatagramChannel sender =
         DatagramChannel.open(StandardProtocolFamily.INET)) {
    sender.setOption(StandardSocketOptions.IP_MULTICAST_IF, ni);
    sender.setOption(StandardSocketOptions.IP_MULTICAST_TTL, 1);
    sender.setOption(StandardSocketOptions.IP_MULTICAST_LOOP, true);

    ByteBuffer data = StandardCharsets.UTF_8.encode("hello-multicast");
    int sent = sender.send(
        data, new InetSocketAddress(group, 5000));
}
```

Đây là đoạn minh họa; cần import `java.net.*`, `java.nio.*`, `java.nio.channels.*` và `java.nio.charset.StandardCharsets`, cùng biến `group`/`ni`. **Không cần join để gửi.**

### Lưu ý rất quan trọng

- `IP_MULTICAST_IF` tác động đến **hướng đi**. Nó không thay thế `join(group, ni)`, thao tác cần để **nhận**.
- `IP_MULTICAST_TTL = 1` giới hạn gói thường trong subnet/link gần (trên IPv6 là hop limit tương ứng); **không phải bảo mật** hay cam kết packet không thể bị quan sát.
- `IP_MULTICAST_LOOP = true` cho phép khả năng loopback, nhưng Javadoc nói tác dụng cụ thể của option **system dependent**. Có thể join thành công mà không nhận được datagram tự gửi trên máy hiện tại.
- Giá trị `send(...)` trả về là **số byte được đưa ra** từ ByteBuffer để gửi. Nó không phải số receiver, số packet tới được bên kia hay ACK.
- Gửi một datagram không bảo đảm có receiver đang join, không bảo đảm switch/router forward, và không bảo đảm app nhận/parse thành công.

**Trong kiểm thử thực tế**, một host Windows có thể `join` thành công trên interface loopback nhưng `send` tới multicast group qua interface đó báo `Network is unreachable`. Đây là vấn đề định tuyến/OS, không chứng tỏ phương thức `join` của Java sai. Chọn interface mạng thật phù hợp, kiểm tra route/firewall và thử lại trên môi trường multicast được bật.

## 8. Chương trình Java 15+ chạy được: liệt kê, join/drop, receive và send

Chương trình dùng **một file** và **bốn mode** để không phụ thuộc vào tên interface cố định:

- `list`: in các interface up, hỗ trợ multicast và có IPv4.
- `join <ifname>`: mở channel, bind, join group rồi drop; **stdout cố định** nếu join thành công.
- `receive <ifname> <port>`: join group trên cổng được chọn, đợi packet tối đa 5 giây qua `Selector`.
- `send <ifname> <port> <text>`: gửi **một** UDP multicast datagram tới group/port.

### 8.1. File `MulticastNioDemo.java`

```java
import java.net.*;
import java.nio.*;
import java.nio.channels.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

public final class MulticastNioDemo {
    private static final String GROUP = "239.255.42.99";

    private static NetworkInterface requireInterface(String name) throws Exception {
        NetworkInterface ni = NetworkInterface.getByName(name);
        if (ni == null || !ni.isUp() || !ni.supportsMulticast()) {
            throw new IllegalArgumentException(
                    "Interface missing, down, or without multicast: " + name);
        }
        boolean ipv4 = Collections.list(ni.getInetAddresses()).stream()
                .anyMatch(a -> a instanceof Inet4Address);
        if (!ipv4) {
            throw new IllegalArgumentException(
                    "Interface has no IPv4 address: " + name);
        }
        return ni;
    }

    private static void listInterfaces() throws Exception {
        for (NetworkInterface ni : Collections.list(
                NetworkInterface.getNetworkInterfaces())) {
            if (ni.isUp() && ni.supportsMulticast()
                    && Collections.list(ni.getInetAddresses()).stream()
                    .anyMatch(a -> a instanceof Inet4Address)) {
                System.out.println(ni.getName());
            }
        }
    }

    private static void runMembership(NetworkInterface ni) throws Exception {
        InetAddress group = InetAddress.getByName(GROUP);
        try (DatagramChannel channel =
                DatagramChannel.open(StandardProtocolFamily.INET)) {
            channel.setOption(StandardSocketOptions.SO_REUSEADDR, true);
            channel.bind(new InetSocketAddress(0)); // Wildcard; port tam.
            channel.setOption(StandardSocketOptions.IP_MULTICAST_IF, ni);
            channel.setOption(StandardSocketOptions.IP_MULTICAST_TTL, 1);
            channel.setOption(StandardSocketOptions.IP_MULTICAST_LOOP, true);
            MembershipKey key = channel.join(group, ni);
            try {
                System.out.println("groupMatches=" + key.group().equals(group));
                System.out.println("interfaceMatches="
                        + key.networkInterface().equals(ni));
                System.out.println("sourceSpecific="
                        + (key.sourceAddress() != null));
                System.out.println("joined=" + key.isValid());
            } finally {
                key.drop();
                System.out.println("afterDrop=" + key.isValid());
            }
        }
    }

    private static void receive(NetworkInterface ni, int port) throws Exception {
        InetAddress group = InetAddress.getByName(GROUP);
        try (DatagramChannel channel =
                DatagramChannel.open(StandardProtocolFamily.INET)) {
            channel.setOption(StandardSocketOptions.SO_REUSEADDR, true);
            channel.bind(new InetSocketAddress(port)); // Wildcard + port.
            channel.setOption(StandardSocketOptions.IP_MULTICAST_IF, ni);

            MembershipKey key = channel.join(group, ni);
            try {
                channel.configureBlocking(false);
                try (Selector selector = Selector.open()) {
                    channel.register(selector, SelectionKey.OP_READ);
                    System.out.println("listening=" + GROUP + ":" + port);
                    if (selector.select(5000) == 0) {
                        System.out.println("noDatagramWithin5s");
                    } else {
                        ByteBuffer buffer = ByteBuffer.allocate(2048);
                        SocketAddress sender = channel.receive(buffer);
                        if (sender != null) {
                            buffer.flip();
                            System.out.println("message="
                                    + StandardCharsets.UTF_8.decode(buffer));
                            System.out.println("sourceKnown="
                                    + (sender != null));
                        }
                    }
                }
            } finally {
                key.drop();
            }
        }
    }

    private static void send(NetworkInterface ni, int port, String message)
            throws Exception {
        try (DatagramChannel channel =
                DatagramChannel.open(StandardProtocolFamily.INET)) {
            channel.setOption(StandardSocketOptions.IP_MULTICAST_IF, ni);
            channel.setOption(StandardSocketOptions.IP_MULTICAST_TTL, 1);
            channel.setOption(StandardSocketOptions.IP_MULTICAST_LOOP, true);

            ByteBuffer buffer = StandardCharsets.UTF_8.encode(message);
            int sent = channel.send(buffer,
                    new InetSocketAddress(
                            InetAddress.getByName(GROUP), port));
            System.out.println("sentBytes=" + sent);
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 1 && "list".equals(args[0])) {
            listInterfaces();
            return;
        }
        if (args.length < 2) {
            System.out.println(
                "Usage: list | join <ifname> | receive <ifname> <port> "
                + "| send <ifname> <port> <text>");
            return;
        }
        NetworkInterface ni = requireInterface(args[1]);
        switch (args[0]) {
            case "join":
                if (args.length != 2) {
                    throw new IllegalArgumentException("join <ifname>");
                }
                runMembership(ni);
                break;
            case "receive":
                if (args.length != 3) {
                    throw new IllegalArgumentException(
                            "receive <ifname> <port>");
                }
                receive(ni, Integer.parseInt(args[2]));
                break;
            case "send":
                if (args.length != 4) {
                    throw new IllegalArgumentException(
                            "send <ifname> <port> <text>");
                }
                send(ni, Integer.parseInt(args[2]), args[3]);
                break;
            default:
                throw new IllegalArgumentException("Unknown mode");
        }
    }
}
```

Chương trình này dùng các API Java SE đã có ở Java 15: `DatagramChannel`, `MembershipKey`, `NetworkInterface`, `Selector`, `StandardSocketOptions`, `StandardProtocolFamily` và `ByteBuffer`. Nó không sử dụng API preview, thư viện ngoài hay class nội bộ `sun.*`.

### 8.2. Biên dịch

Tại thư mục chứa file, dùng một JDK còn hỗ trợ môi trường của bạn và có `javac` chấp nhận `--release 15`:

```bash
javac --release 15 -encoding UTF-8 MulticastNioDemo.java
```

### 8.3. Liệt kê interface và kiểm thử membership

```bash
java MulticastNioDemo list
```

Output phụ thuộc hệ điều hành; ví dụ `eth0` trên Linux hoặc tên do Java/Windows đặt. Chọn **tên thật trong output** có thể tham gia IPv4 multicast. Không copy nguyên `eth0` vào mọi máy.

Thay `<ifname>` ở các lệnh sau bằng tên thật — ví dụ trên một máy có tên interface `eth0`:

```bash
java MulticastNioDemo join eth0
```

**Stdout chính xác nếu interface và OS cho phép join thành công:**

```text
groupMatches=true
interfaceMatches=true
sourceSpecific=false
joined=true
afterDrop=false
```

Năm dòng này đã được kiểm chứng bằng chạy Java 15-compatible code trên **OpenJDK 24** với một interface thực sự cho phép join. Với máy không có interface hỗ trợ multicast, hoặc OS/firewall chặn membership, chương trình có thể ném exception và **không** in đủ các dòng trên; đó là giới hạn môi trường, không được gọi là PASS giả.

Giải thích:

- `groupMatches=true`: `MembershipKey.group()` là địa chỉ `239.255.42.99` đã join.
- `interfaceMatches=true`: membership gắn với đúng `NetworkInterface` do người thực hành chọn.
- `sourceSpecific=false`: `join(group, ni)` nhận từ **mọi source hợp lệ trong group**, nên `sourceAddress() == null`.
- `joined=true`: key còn valid ngay sau khi join.
- `afterDrop=false`: `drop()` làm key invalid; chương trình đóng channel khi ra khỏi `try-with-resources`.

**Tại sao cổng bind là 0?** `0` nhờ OS cấp một cổng tạm; mode `join` chỉ kiểm tra lifecycle membership và không cần nhận packet. Đây là lý do output không phụ thuộc số port tạm.

### 8.4. Thử gửi/nhận từ hai terminal

Chọn một cổng thử nghiệm chưa có dịch vụ nào dùng, ví dụ `48994`. Dùng **cùng multicast group, UDP port và interface có khả năng định tuyến multicast**.

**Terminal A — mở receiver trước:**

```bash
java MulticastNioDemo receive eth0 48994
```

Khi thành công bind/join, chương trình in:

```text
listening=239.255.42.99:48994
```

Nó chờ tối đa khoảng 5 giây để một packet đến (vì mode `receive` gọi `Selector.select(5000)`).

**Terminal B — gửi nhanh trước khi 5 giây hết:**

```bash
java MulticastNioDemo send eth0 48994 hello-multicast
```

Nếu sender gửi 15 byte thành công, terminal B sẽ in:

```text
sentBytes=15
```

**Nếu multicast được chuyển phát và receiver nhận kịp**, terminal A có thể in thêm:

```text
message=hello-multicast
sourceKnown=true
```

**Nếu không có datagram sẵn sàng trong 5 giây**, terminal A sẽ in:

```text
noDatagramWithin5s
```

**Lưu ý cần thiết:** output gửi/nhận **phụ thuộc mạng**, không có một stdout chung được bảo đảm trên mọi máy. Trong môi trường kiểm thử Windows được sử dụng để xác minh biên dịch/membership, `join` thành công nhưng multicast loopback không chuyển datagram về receiver; trên loopback interface, thử gửi còn có thể nhận lỗi `Network is unreachable`. Vì vậy đây là **bài thực hành mạng**, không phải một unit test được phép giả định nhận packet chắc chắn.

Nếu bạn muốn test nhận mạng đáng tin hơn, dùng hai máy trong **một LAN đã bật multicast** hoặc môi trường mạng thử nghiệm được quản trị phù hợp, kiểm tra TTL, firewall, IGMP snooping và interface routing.

### 8.5. Tại sao dùng Selector thay vì receive blocking?

- `channel.configureBlocking(false)` đưa channel vào non-blocking mode.
- `channel.register(selector, SelectionKey.OP_READ)` đăng ký chờ dữ liệu có thể đọc.
- `selector.select(5000)` chờ tối đa khoảng 5 giây; không tạo ra packet.
- Nếu select báo có event, `channel.receive(buffer)` lấy một datagram nếu đã có; ở non-blocking mode, `receive` có thể trả `null` nếu chưa có packet ngay thời điểm gọi.
- `buffer.flip()` chuyển từ mode ghi dữ liệu vào buffer sang mode đọc/giải mã, ngăn decode nhầm byte chưa nhận.
- `StandardCharsets.UTF_8.decode(buffer)` giải mã đúng dữ liệu còn trong buffer, không giải mã những byte thừa của capacity.

**Trong ứng dụng sản xuất**, nên dùng **event loop** nhiều lần, kiểm tra mọi selected keys, xử lý spurious wakeups và các packet nối tiếp, kết hợp deadline/interrupt/close. Ví dụ giới hạn một datagram để minh họa API, không phải một multicast server hoàn chỉnh.

### 8.6. Kích thước buffer và xử lý datagram

`ByteBuffer.allocate(2048)` cho tối đa 2048 byte trong ví dụ. Nếu một datagram lớn hơn số byte còn lại, `DatagramChannel.receive` **có thể chép phần đầu và bỏ phần còn lại** theo Javadoc. UDP không chia message dài thành nhiều lần `receive` như TCP stream.

Ứng dụng cần:

1. Quy định **giới hạn kích thước** message tối đa (tốt nhất thấp hơn MTU thực tế để tránh IP fragmentation khi phù hợp).
2. Kiểm tra số byte đọc, version/length field của protocol và charset/encoding.
3. Tránh xử lý payload không xác thực, kích thước quá lớn hoặc vượt quota.
4. Không dựa vào thứ tự packets; tự có message ID, sequence, timeout/retry nếu nghiệp vụ cần.

## 9. Any-source multicast (ASM) và source-specific multicast (SSM)

### 9.1. ASM — nhận từ mọi sender vào nhóm

`join(group, ni)` là **any-source multicast**: receiver chấp nhận các datagram tới group từ những sender thuộc phạm vi mạng có thể đến. `key.sourceAddress()` trả `null`.

Nếu platform hỗ trợ **source filtering**, với membership key **không source-specific**, bạn có thể block/unblock một source IP:

```java
MembershipKey key = channel.join(group, ni);
try {
    key.block(sourceIp);   // Chặn datagram từ IP nguồn chỉ định.
    // ...
    key.unblock(sourceIp); // Chỉ unblock nếu trước đó đã block.
} finally {
    key.drop();
}
```

Đây là **đoạn minh họa**; `sourceIp` phải là **unicast address** cùng họ IPv4/IPv6 với group, các biến cần hợp lệ, và OS phải hỗ trợ filtering. `key.block` có thể ném `UnsupportedOperationException`; `unblock` có thể ném `IllegalStateException` nếu source chưa được block hoặc key đã invalid.

**Block không bảo đảm xóa packet cũ**: datagram từ source vừa bị block vẫn có thể còn trong receive buffer và được nhận. Lọc source ở mức OS không thay thế xác thực payload.

### 9.2. SSM — chỉ nhận từ source đã chọn

Có thể tham gia group với **source IP cụ thể**:

```java
MembershipKey sourceKey =
        channel.join(group, ni, trustedSenderIp);
```

Mảnh mã minh họa dùng `trustedSenderIp` là một **unicast source IP** cùng address family với group. Key này có `sourceAddress()` khác `null`. Cách join phù hợp với **source-specific multicast** khi hệ thống mạng/OS hỗ trợ IGMPv3 (IPv4) hoặc MLDv2 (IPv6) cùng cơ chế nhận nguồn tương ứng.

`join(group, ni, source)` có thể ném `UnsupportedOperationException` nếu OS không hỗ trợ source filtering. Không đơn giản bắt exception rồi chuyển sang ASM mà **không kiểm tra lại yêu cầu bảo mật**: ASM nhận từ nhiều source hơn, làm thay đổi chính sách.

Một channel có thể đăng ký **nhiều source-specific memberships** cho cùng group/interface để nhận từ một tập source IP; các memberships này có tính cộng dồn. Tuy nhiên không được trộn any-source và source-specific cho cùng group/interface trên một channel: Javadoc quy định `IllegalStateException` trong trường hợp xung đột ấy.

### 9.3. Lọc IP nguồn không phải bảo mật end-to-end

Ngay cả SSM vẫn chủ yếu là cơ chế multicast source selection **ở tầng mạng**, không xác nhận nội dung đến từ một danh tính đã được xác thực mật mã. Tùy môi trường, giả mạo source IP và replay vẫn có thể là mối lo.

Nếu payload nhạy cảm, cần **message authentication**, chống replay, authorization và encryption thích hợp cho nhóm, cùng cơ chế **phân phối/thu hồi group keys**. Đừng xem `key.sourceAddress().equals(ip)` là xác thực người gửi.

## 10. Mối liên hệ giữa multicast và `connect()/disconnect()`

`DatagramChannel` có thể được `connect(remotePeer)` để chỉ gửi/nhận datagram của **một remote endpoint**; `read/write` chỉ dùng khi connected. Nhưng **multicast membership không tạo qua connect**.

| Thao tác | Ý nghĩa |
| --- | --- |
| `channel.join(group, ni)` | Tham gia một **multicast group** trên một interface để có thể nhận multicast |
| `channel.connect(remote)` | Ràng buộc socket vào **một remote IP + port**, lọc endpoint và cho dùng `read/write` |
| `channel.disconnect()` | Bỏ gắn kết remote endpoint; không tự drop multicast membership |
| `key.drop()` | Hủy **một multicast membership** trên channel; không đồng nghĩa đóng channel |
| `channel.close()` | Đóng channel; mọi memberships liên quan bị invalidated |

**Không dùng `connect(groupAddress)` để thay thế `join`.** Muốn nhận datagrams gửi tới group thì cần join trên interface, bind đúng port và bảo đảm network multicast có hoạt động.

Với receiver multicast nhiều sender, thường **để channel unconnected** và dùng `receive(ByteBuffer)` để lấy sender address cho từng packet. Sender có thể dùng `send(ByteBuffer, groupSocketAddress)` khi channel không connected.

## 11. Chọn interface khi nhiều NIC, VPN hoặc container

Những vấn đề thường gặp:

- Máy có cả Wi-Fi và Ethernet: sender gửi trên interface A trong khi receiver join group trên interface B; dữ liệu có thể không đi tới nhau.
- Docker/VM/VPN làm xuất hiện interface ảo; `supportsMulticast()` có thể `true` nhưng network virtualization không chuyển gói multicast qua boundary.
- Network route hoặc group membership bị firewall/switch/IGMP snooping chặn.
- Máy có cả IPv4 và IPv6: channel family và group family không khớp.
- Interface thay đổi index, IP hoặc trạng thái trong lúc app chạy, khiến membership đã join không còn hiệu quả.
- Local multicast loopback do OS xử lý khác nhau; `IP_MULTICAST_LOOP=true` không bảo đảm self-delivery.

### Quy trình chẩn đoán

1. Dùng mode `list` xem những interfaces có thể chọn.
2. Kiểm tra interface thực tế có IPv4/IPv6 phù hợp, đang `isUp()` và `supportsMulticast()`.
3. Chạy mode `join`. Nếu báo thành công, **chỉ kết luận membership API hoạt động trên interface đó**, không kết luận route hay reception đã hoạt động.
4. Chạy `receive` trước `send` trên cùng group/port/interface; bảo đảm receiver chưa hết timeout.
5. Nếu sender ném `Network is unreachable`, xem route/adapter/outgoing interface; đổi sang interface có đường multicast hợp lệ.
6. Nếu `send` trả bytes nhưng receiver timeout, kiểm tra firewall, IP_MULTICAST_LOOP, IGMP/MLD, switch snooping, TTL/hop limit và nguồn packet có đúng network.
7. Nếu packet đến nhưng nội dung sai, kiểm tra `ByteBuffer` position/limit, charset, length và application protocol, không giải mã cả capacity.
8. Kiểm tra mạng production bằng hệ thống quan sát của OS/router được cho phép, chứ không viết một ứng dụng bắt packet không giới hạn hay tự phát tán multicast vào mạng ngoài phạm vi.

## 12. Các lỗi và nguyên nhân phổ biến

| Hiện tượng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `IllegalArgumentException` tại `join` | `group` không phải multicast address, sai IP family hoặc source IP không phù hợp | Dùng group hợp lệ, mở `INET/INET6` tương ứng, source unicast cùng family |
| `UnsupportedOperationException` | Platform không hỗ trợ multicast/source filtering hoặc protocol family tương ứng | Xác nhận OS/network/provider; với SSM không fallback ASM trái chính sách |
| `IllegalStateException` tại `join` | Trộn any-source và source-specific memberships cho cùng group/interface | Chọn một mode cho mỗi (channel, group, interface) hoặc tách channel |
| `IllegalStateException` tại `block/unblock` | Key invalid, key SSM, hoặc source chưa block khi gọi unblock | Kiểm tra `isValid()`/`sourceAddress()` và trạng thái block |
| `Network is unreachable` hoặc `SocketException` khi send | Network interface/route không đi được tới multicast đích | Chọn đúng interface, route, family; không coi lỗi là do mã decode |
| `BindException: Address already in use` | Port đang được dùng, `SO_REUSEADDR` đặt sau bind hoặc OS policy | Đặt `SO_REUSEADDR` trước bind; kiểm tra port/process |
| `receive` trả `null` | Channel non-blocking mà chưa có datagram ngay | Chờ qua `Selector`/event loop; không dereference null |
| `Selector.select(timeout) == 0` | Chưa có sự kiện đọc trong thời hạn | Kiểm tra sender, multicast delivery, firewall, port và TTL |
| `StandardSocketOptions.IP_MULTICAST_IF` không đúng | Gửi qua NIC khác với NIC receiver/network multicast | Chọn đúng `NetworkInterface` và kiểm tra route |
| `MembershipKey.isValid() == false` | Đã drop/đã close channel | Join lại nếu channel vẫn open, hoặc mở channel mới |
| Sau `drop` vẫn nhận datagram | Gói đã đợi trong receive buffer | Không coi `drop` như thao tác flush; kiểm tra generation/session |
| Datagram bị cắt | `ByteBuffer` không đủ remaining bytes | Thiết kế giới hạn payload và kích thước buffer hợp lý |
| `NotYetConnectedException` khi gọi `read/write` | Channel unconnected | Dùng `send/receive` hoặc connect có chủ đích |
| Receiver chỉ nhận một nguồn rồi “mất” nguồn khác | Channel bị `connect` tới remote peer | Dùng unconnected receiver và `join` đúng group |
| IPv6 không nhận dù IPv4 hoạt động | Sai `INET6`, scope id/interface hoặc policy mạng | Chọn group IPv6, family `INET6` và interface IPv6 phù hợp |
| Chỉ một receiver nhận trong nhiều process | OS socket reuse/multicast delivery phụ thuộc nền tảng | Cấu hình `SO_REUSEADDR` trước bind và kiểm tra triển khai thực tế |
| Receiver có packet “lạ” | Nhóm có nhiều sender hoặc dữ liệu chưa xác thực | Kiểm tra sender, message version, key ID, MAC/signature và replay protection |

## 13. Bảo mật và vận hành multicast đúng cách

**Multicast là cơ chế phân phối ở tầng IP**, không phải channel riêng tư:

- **Không có authentication:** ai có khả năng gửi tới group có thể đưa UDP packets vào hệ thống tùy môi trường.
- **Không có encryption:** thành viên hoặc node quan sát được traffic có thể đọc payload nếu giao thức không mã hóa.
- **Không có replay protection:** packet có thể bị phát lại. App cần nonce/sequence/timestamp policy thích hợp.
- **Không có reliability:** packets có thể mất, lặp, trễ hoặc đảo thứ tự; nếu muốn bảo đảm, thiết kế giao thức tầng ứng dụng.
- **Không có backpressure tự động như TCP:** nếu senders phát quá nhanh, receiver hoặc mạng có thể quá tải.
- **Không có group membership authorization built-in trong Java:** `join` không chứng minh một user đã được cho phép truy cập nội dung.

Khi dữ liệu có giá trị hoặc nhạy cảm:

1. Chọn phạm vi group và TTL hợp lý, phối hợp với network policy; không coi TTL là security boundary.
2. Giới hạn sender/receiver bằng firewall, ACL mạng và network segmentation phù hợp.
3. Dùng **mã hóa và xác thực thông điệp** theo một giao thức group phù hợp, quản lý group keys và rotation/revocation.
4. Thêm source ID/key ID, sequence, nonce và xác thực integrity trước khi xử lý dữ liệu.
5. Giới hạn message size, số lượng join/receive buffer và tần suất xử lý để tránh DoS.
6. Ghi log metadata thiết yếu nhưng tránh ghi secret hoặc payload nhạy cảm.
7. Không dựa vào `NetworkInterface.getName()` cố định trên các môi trường/VM/VPN; cho phép cấu hình interface và revalidation.

Nếu hệ thống không có multicast routing nhưng cần phát tán sự kiện cho nhiều clients, có thể dùng hệ thống publish/subscribe, message broker hoặc cơ chế unicast fan-out phù hợp. **Không** dùng multicast như mặc định cho mọi ứng dụng vì thấy có thể giảm số lần send.

## 14. Checklist tự kiểm tra

- [ ] Nhóm sử dụng là **multicast IP hợp lệ**, được cấp phát/quản lý cho ứng dụng, không đụng tới nhóm reserved?
- [ ] `DatagramChannel.open(StandardProtocolFamily.INET/INET6)` đúng với IPv4/IPv6 group?
- [ ] Interface được chọn theo **tên/configuration**, `isUp()` và `supportsMulticast()`, có IP family tương ứng?
- [ ] Receiver gọi `setOption(SO_REUSEADDR, true)` **trước** wildcard `bind(port)`?
- [ ] Receiver `join(group, ni)` và giữ `MembershipKey` tới khi cần rời nhóm?
- [ ] Đã phân biệt **IP_MULTICAST_IF = outgoing interface** với `join(..., ni) = incoming group membership`?
- [ ] Đã đặt TTL/hop limit theo phạm vi định tuyến và biết `IP_MULTICAST_LOOP` là OS-dependent?
- [ ] Sender dùng `channel.send(buffer, group:port)`, không giả định cần join để send?
- [ ] Receiver dùng `receive`/Selector đúng blocking mode, xử lý `null` và buffer `flip()`?
- [ ] Datagrams có được kiểm tra length, source, protocol version, session và authentication trước khi dùng?
- [ ] Khi dùng source filtering, OS có hỗ trợ SSM/block/unblock? Có tránh trộn ASM và SSM cho cùng group/interface không?
- [ ] Khi `key.drop()`, đã tính đến queued datagrams và cleanup trong `finally`?
- [ ] Đã thử **membership lifecycle** độc lập với **datagram delivery**, không ép một unit test “phải nhận” trên mọi OS?
- [ ] Khi triển khai, đã kiểm tra switch/router/firewall/IGMP/MLD/VPN/container và có logs/metrics hợp lý?
- [ ] Khi dữ liệu nhạy cảm, đã dùng encryption/authentication và replay protection thích hợp?

## 15. Tài liệu chính thức còn được sử dụng

- **Java SE 15 `java.nio.channels.DatagramChannel`** — `open(INET/INET6)`, `bind`, `send`, `receive` và API NIO: https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/nio/channels/DatagramChannel.html
- **Java SE 25 `DatagramChannel`** — đặc tả API hiện đại: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/DatagramChannel.html
- **Java SE 15 `MulticastChannel`** — `join(group, interface)`, source-specific join và yêu cầu cấu hình: https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/nio/channels/MulticastChannel.html
- **Java SE hiện đại `MulticastChannel`** — multicast nhóm và source filtering: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/MulticastChannel.html
- **Java SE 15 `MembershipKey`** — `isValid`, `drop`, `block`, `unblock`: https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/nio/channels/MembershipKey.html
- **Java SE hiện đại `NetworkInterface`** — tìm interface, `supportsMulticast()`, địa chỉ IP và trạng thái: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/NetworkInterface.html
- **Java SE hiện đại `StandardSocketOptions`** — `SO_REUSEADDR`, `IP_MULTICAST_IF`, `IP_MULTICAST_TTL`, `IP_MULTICAST_LOOP`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/StandardSocketOptions.html
- **RFC 1112 — Host Extensions for IP Multicasting**, mô hình IPv4 multicast: https://www.rfc-editor.org/rfc/rfc1112
- **RFC 2365 — Administratively Scoped IP Multicast**, phạm vi 239.0.0.0/8: https://www.rfc-editor.org/rfc/rfc2365
- **RFC 3376 — IGMPv3**, source filtering IPv4: https://www.rfc-editor.org/rfc/rfc3376
- **RFC 3810 — Multicast Listener Discovery Version 2 (MLDv2)**, IPv6 multicast listener/source filtering: https://www.rfc-editor.org/rfc/rfc3810
- **RFC 8085 — UDP Usage Guidelines**, giới hạn và quy tắc vận hành UDP: https://www.rfc-editor.org/rfc/rfc8085

**Kết luận:** Với Java 15+, mô hình chuẩn để nhận IP multicast là **chọn đúng `NetworkInterface` → mở `DatagramChannel` theo IP family → bật `SO_REUSEADDR` trước wildcard bind → `join(group, ni)` → dùng `receive(ByteBuffer)` → `MembershipKey.drop()` khi xong**. Với sender, thiết lập `IP_MULTICAST_IF` và TTL/hop limit rồi `send` tới group/port. Các API này còn áp dụng trong Java hiện đại, nhưng **routing, delivery và authentication** vẫn là những trách nhiệm riêng của hệ điều hành, mạng và ứng dụng.
