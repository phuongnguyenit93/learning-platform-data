# Kiểm thử mạng có hỗ trợ multicast trong Java: từ kiểm tra giao diện tới xác nhận gói UDP

## 1. Mục tiêu học tập và định nghĩa “mạng có hỗ trợ multicast”

Trong module **Socket và multicast** của Java 7, câu hỏi “**Kiểm thử mạng có hỗ trợ multicast**” không thể trả lời bằng một `boolean` duy nhất. `NetworkInterface.supportsMulticast()` là kiểm tra năng lực được hệ điều hành báo cáo cho một interface; nó **không chứng minh** gói UDP multicast sẽ đi qua firewall, switch, router, VPN hoặc container và đến được máy nhận.

Java NIO.2 hỗ trợ `DatagramChannel` và `MulticastChannel` từ Java 7. Đây vẫn là các API áp dụng trong **Java 17+**. Bài học sử dụng chúng để triển khai quy trình thử có kiểm soát:

1. **L0 – kiểm tra cú pháp và địa chỉ:** nhóm thử là IPv4/IPv6 multicast hợp lệ; chọn đúng family của kênh.
2. **L1 – kiểm tra giao diện:** network interface tồn tại, đang hoạt động, có địa chỉ đúng family, `supportsMulticast()`.
3. **L2 – kiểm thử UDP unicast nội bộ:** xác minh socket cơ bản, `DatagramChannel`, `Selector` và firewall loopback—**chưa có bằng chứng về multicast**.
4. **L3 – kiểm thử multicast trên cùng host:** bind, `join` group trên interface được chọn, gửi datagram và nhận lại qua multicast loopback—chứng minh đường đi cục bộ nếu thành công, **chưa chứng minh LAN/routing**.
5. **L4 – kiểm thử hai host:** cho receiver trên máy A tham gia group, sender trên máy B gửi; xác nhận đúng payload/token qua đường mạng đích. Chỉ cấp độ này mới thực sự kiểm tra thành công trên tuyến mạng giữa hai máy.
6. **L5 – kiểm thử triển khai:** lặp lại với nhiều NIC, VLAN, subnet, container, VPN, IPv6 nếu hệ thống có dùng, đồng thời đo loss, jitter, timeout và hành vi khi một thành phần mạng thay đổi.

**Không đánh đồng các kết quả:** “interface hỗ trợ multicast” khác “join thành công”, “send trả số byte” khác “receiver đã nhận”, và “cùng host nhận được” khác “hai máy khác nhau nhận được”.

Bài có chương trình **Java 17+ độc lập đã biên dịch/chạy** với các mode: `--self-test`, `--interfaces`, `--probe-local`, `--receive`, `--send`. Mặc định chỉ chạy kiểm thử unicast loopback **không phát multicast ra mạng**. Các mode thực sự gửi multicast phải được người vận hành chủ động gọi trên mạng được phép kiểm thử.

## 2. Multicast khác unicast và broadcast ở đâu?

### 2.1. Unicast

UDP unicast gửi datagram từ một socket tới **một địa chỉ IP và port đích**. Ví dụ `127.0.0.1:12345` là loopback unicast. Thành công ở đây cho thấy UDP nội bộ hoạt động trong môi trường thử; không nói gì về IGMP, multicast subscription hoặc switch forwarding.

### 2.2. IP multicast

Với multicast, sender gửi tới **một địa chỉ group** (ví dụ IPv4 `239.255.42.99`). Các hosts có socket tham gia group trên interface thích hợp có thể nhận datagram nếu hệ điều hành và mạng chuyển gói tương ứng. Receiver thường dùng:

```java
try (DatagramChannel ch =
        DatagramChannel.open(StandardProtocolFamily.INET)) {
    ch.setOption(StandardSocketOptions.SO_REUSEADDR, true);
    ch.bind(new InetSocketAddress(port));
    MembershipKey key = ch.join(group, networkInterface);
    try {
        // Nhận datagram; kiểm tra payload và thời hạn chờ.
    } finally {
        key.drop();
    }
}
```

Đây là **snippet minh họa** bên trong phương thức có các biến `port`, `group`, `networkInterface` đã được chọn đúng. `join` không tạo một kết nối TCP; membership chỉ là đăng ký nhận group trên interface.

### 2.3. Broadcast khác multicast

IPv4 broadcast gửi tới địa chỉ broadcast được cho phép trên một vùng mạng; nó không dùng membership `MulticastChannel.join(...)`. `SO_BROADCAST` và `SO_REUSEADDR` không phải “bật multicast”. Bài này thử **IP multicast**, không dùng broadcast như đường thay thế khi group fail.

### 2.4. Multicast không đảm bảo tin cậy

UDP multicast không tự bảo đảm nhận gói, thứ tự, không trùng, retry hay xác thực. Một `join` thành công vẫn có thể không nhận được do gói không được gửi, bị chặn hoặc mất. Vì vậy thiết kế test cần **nonce/token riêng, deadline, kiểm tra nội dung**, và đánh giá failure chính xác.

## 3. Kiểm tra interface với `NetworkInterface`

### 3.1. Các API nên xem

```java
NetworkInterface ni = NetworkInterface.getByName("eth0");
if (ni != null) {
    boolean up = ni.isUp();
    boolean multicastFlag = ni.supportsMulticast();
    boolean loopback = ni.isLoopback();
    boolean virtual = ni.isVirtual();
}
```

Đây là **mã minh họa**; `eth0` chỉ là ví dụ tên interface của một số hệ Linux. Windows, macOS, containers hay VPN có cách đặt tên khác; phải dùng tên xuất hiện trong hệ thống thực.

| Phép kiểm tra | Thông tin thu được | Không thể suy ra |
| --- | --- | --- |
| `getNetworkInterfaces()` | Những NIC/virtual interfaces Java nhìn thấy | NIC nào đi tới group |
| `NetworkInterface.getByName(name)` | Interface cụ thể tồn tại | Interface đang usable |
| `isUp()` | Trạng thái hệ điều hành báo interface đang up | Có route ra đúng subnet |
| `supportsMulticast()` | Khả năng multicast theo thông tin OS | UDP multicast sẽ đi xuyên firewall/switch |
| `isLoopback()` | Interface loopback local | Test thành công trên LAN |
| `isVirtual()` | Interface logic/virtual | Có/chưa có route multicast |
| `getInetAddresses()` | Các địa chỉ được gán cho interface | Group hiện được NIC/router chuyển tới |

### 3.2. Chọn interface tương ứng với họ địa chỉ

Nếu group IPv4, chương trình cần chọn một interface có **`Inet4Address`** thích hợp. Nếu group IPv6, cần interface có địa chỉ IPv6 và cấu hình scope thích hợp; không thể thay bằng việc chọn một NIC “multicast=true” nhưng không có địa chỉ family đích.

```java
static boolean hasIpv4(NetworkInterface ni) {
    Enumeration<InetAddress> addresses = ni.getInetAddresses();
    while (addresses.hasMoreElements()) {
        if (addresses.nextElement() instanceof Inet4Address) {
            return true;
        }
    }
    return false;
}
```

Đây là method có thể dùng trong class import `java.net.*`, `java.util.Enumeration`. Kết quả `true` là một **điều kiện hữu ích**, không chứng minh interface đã join group hoặc có thể nhận traffic từ máy khác.

### 3.3. Chọn NIC đúng với đường đi thực

Trong máy có Ethernet, Wi-Fi, VPN, vEthernet, Docker bridge, loopback, không chọn bừa interface đầu tiên thỏa `supportsMulticast()`. Người vận hành nên biết:

- Sender nằm trên mạng nào?
- Máy receiver có NIC nào nối tới mạng đó?
- Các máy cùng Layer 2, khác VLAN hay khác subnet?
- Có VPN/container bridge/NAT chen giữa?
- Router có cho multicast forwarding trên tuyến đó không?
- Group IPv4/IPv6 và phạm vi được phép là gì?

`NetworkInterface` không biết toàn bộ topology vật lý/ảo; nó không thể trả lời thay cho phép thử đường truyền thật.

## 4. Địa chỉ multicast và họ giao thức

### 4.1. IPv4

Dải IPv4 multicast là `224.0.0.0/4`. Bài thực hành chọn `239.255.42.99`, một địa chỉ trong không gian multicast quản trị (`239/8`), dùng làm ví dụ **trong lab được phép thử**. Không coi đó là group được phân bổ độc quyền; trong mạng thật nên dùng group được quản trị mạng phê duyệt, tránh trùng group của dịch vụ đang chạy.

```java
InetAddress group = InetAddress.getByAddress(
        new byte[]{(byte) 239, (byte) 255, 42, 99});

if (!(group instanceof Inet4Address)
        || !group.isMulticastAddress()) {
    throw new IllegalArgumentException("Not an IPv4 group");
}
```

Đây là snippet có thể đưa vào phương thức `throws IOException`. Tạo `InetAddress` từ bytes tránh việc DNS/hostname vô tình resolve sang họ khác.

### 4.2. IPv6

IPv6 multicast thuộc `ff00::/8`; địa chỉ và scope mang các thông tin về phạm vi. Bài demo chạy thực tế là **IPv4** vì hầu hết môi trường học có thể chạy nó độc lập với IPv6 availability. Nếu ứng dụng cần IPv6, mở:

```java
DatagramChannel dc =
        DatagramChannel.open(StandardProtocolFamily.INET6);
```

Đây là snippet phải đóng `dc`. Chọn group `Inet6Address` và network interface có IPv6, lưu ý scoped addresses/link-local và MLD. Không sử dụng cùng group IPv4 với kênh IPv6 rồi kỳ vọng multicast cross-family hoạt động portable.

### 4.3. Tại sao không dùng `DatagramChannel.open()` mặc định cho bài test?

Overload không tham số của `DatagramChannel.open()` có **protocol family phụ thuộc nền tảng và không được đặc tả**. Kiểm thử cần reproducibility nên dùng `DatagramChannel.open(StandardProtocolFamily.INET)` khi group là IPv4. Đây là quyết định về **tính đúng**, không phải thủ thuật tăng tốc.

## 5. Cấu hình nhận multicast đúng thứ tự

### 5.1. Tạo socket và bind wildcard

```java
DatagramChannel receiver =
        DatagramChannel.open(StandardProtocolFamily.INET);

receiver.setOption(StandardSocketOptions.SO_REUSEADDR, true);
receiver.bind(new InetSocketAddress(port));
```

Đây là đoạn minh họa, `receiver` phải được đóng. `new InetSocketAddress(port)` bind với **wildcard address**, thường được khuyến nghị để nhận multicast; việc bind một địa chỉ IP cụ thể rồi nhận multicast phụ thuộc provider.

`SO_REUSEADDR` được đặt **trước `bind`** để hỗ trợ nhiều membership listeners cùng port trên các OS cho phép. Tuy nhiên không hứa mọi hệ điều hành hoặc cấu hình bảo mật đều cho phép nhiều tiến trình dùng chung port.

### 5.2. Tham gia group trên interface đúng

```java
MembershipKey membership = receiver.join(group, ni);
try {
    // Dùng receive/Selector để thu datagram.
} finally {
    membership.drop();
}
```

`join(group, ni)` trả `MembershipKey`, và `drop()` rời group; đóng channel cũng làm các memberships tương ứng mất hiệu lực. Một `join` thành công nói rằng **provider đã chấp nhận yêu cầu membership** tại thời điểm đó, không phải xác minh packet delivery xuyên mạng.

### 5.3. Cấu hình sender

```java
try (DatagramChannel sender =
        DatagramChannel.open(StandardProtocolFamily.INET)) {
    sender.setOption(StandardSocketOptions.IP_MULTICAST_IF, ni);
    sender.setOption(StandardSocketOptions.IP_MULTICAST_TTL, 1);
    sender.setOption(StandardSocketOptions.IP_MULTICAST_LOOP, true);

    sender.send(
            ByteBuffer.wrap(payload.getBytes(StandardCharsets.US_ASCII)),
            new InetSocketAddress(group, port));
}
```

Đây là snippet minh họa với `ni`, `group`, `payload` và `port` hợp lệ. `IP_MULTICAST_IF` chọn interface để **gửi** multicast; nó không tự join group và không đổi protocol family. `IP_MULTICAST_TTL=1` giới hạn số hop (không phải cam kết gói tin chắc chắn ở lại local host). `IP_MULTICAST_LOOP=true` yêu cầu cho phép loopback multicast, nhưng **semantics chi tiết phụ thuộc OS/provider**, nên test trên cùng host có thể không phản ánh LAN.

### 5.4. Không bật tính năng network không cần thiết trong test

Không sử dụng TTL rất lớn hay group/cổng của hệ thống production khi đang học. Không gửi hàng nghìn packets để ép kết quả. Một test có một payload nhỏ và deadline vài giây đủ chứng minh một chiều dữ liệu trong lab.

## 6. Ba cấp độ phép thử cần tách rời

### 6.1. Kiểm tra capability: không có network traffic

Gọi `NetworkInterface.getNetworkInterfaces()`, `isUp()`, `supportsMulticast()`, `isLoopback()`, và kiểm tra IPv4/IPv6 addresses. Từ đó lọc **ứng viên** để test.

Nếu `supportsMulticast()==false`, interface đó không đáp ứng điều kiện multicast theo OS ở thời điểm kiểm tra. Nếu `true`, vẫn cần kiểm tra join/receive.

### 6.2. UDP loopback unicast baseline

Mở hai `DatagramChannel.open(INET)`, bind receiver trên `127.0.0.1` với port `0` (OS cấp port tạm), gửi `PING` qua unicast, dùng `Selector` có timeout và đọc lại.

Kết quả `PING` chứng minh network stack UDP trên local host và code xử lý `DatagramChannel/ByteBuffer/Selector` hoạt động. Nó **không gửi multicast**, không chứng minh `join` hay hạ tầng multicast.

### 6.3. Multicast trên cùng máy

Sau khi người vận hành chỉ định một interface ứng viên:

1. Mở receiver IPv4.
2. `SO_REUSEADDR` rồi bind wildcard vào port.
3. `join(239.255.42.99, chosenInterface)`.
4. Mở sender, đặt `IP_MULTICAST_IF=chosenInterface`, `IP_MULTICAST_LOOP=true` và `TTL=1`.
5. Gửi một datagram có token ngẫu nhiên vào group/port của receiver.
6. Đợi qua `Selector` với deadline 4 giây.
7. Chỉ báo PASS khi receiver nhận đúng **token** đó.
8. Gọi `MembershipKey.drop` và đóng cả hai channels.

PASS ở đây xác minh **đường đi multicast cục bộ thông qua interface/test stack**. Nó không chứng minh switch hoặc router chuyển packet tới máy khác.

### 6.4. Multicast giữa hai host

Chạy receiver và sender trên **hai máy khác nhau** trong mạng lab được phép dùng. Receiver báo `joined=true` và `ready=true`, sender gửi datagram có một token đã thỏa thuận. Receiver chỉ báo PASS khi nhận token đúng trước timeout.

Nếu FAIL, cần chẩn đoán:
- Đúng interface/network path chưa?
- Có firewall ingress/egress cho UDP port không?
- IGMP membership và switch snooping có hoạt động không?
- Có router multicast giữa VLAN/subnets không?
- Group/TTL/port có phù hợp không?
- VPN, NAT, Docker bridge, cloud VPC có hỗ trợ multicast không?

**Đặc biệt:** send trả số byte **không đủ** để khẳng định receiver nhận được. Phải nhìn kết quả ở **receiver**.

## 7. Tại sao có thể `join` được mà không nhận gói?

| Tình huống | Biểu hiện | Điều nên kiểm tra |
| --- | --- | --- |
| Sai interface nhận | `join` thành công nhưng không thấy packet từ sender | NIC/subnet/route, tên interface |
| Group sai | Không có packet phù hợp | Địa chỉ group và family |
| Sender gửi cổng khác | Receiver chỉ chờ sai UDP port | Port của sender/receiver |
| Firewall endpoint | Máy A nhận, máy B không nhận | Inbound UDP policy, endpoint security |
| Switch có IGMP snooping | Traffic không đến một số switch ports | IGMP membership reports/querier/snooping config |
| Router không forward multicast | Cùng VLAN pass, khác VLAN fail | Multicast routing/PIM và TTL/scope |
| Container/cloud | Host pass, container fail | Bridge, overlay, namespace, VPC support |
| VPN | Local LAN pass, VPN fail | VPN multicast routing/tunneling policy |
| Interface up nhưng không có IPv4 | `INET` group không được nhận đúng | `getInetAddresses` và cấu hình IP |
| Loopback multicast bị OS chặn | Same-host test fail | `IP_MULTICAST_LOOP`, OS semantics |
| Gói được gửi trước khi join | Receiver bỏ lỡ | Receiver phải join trước sender send |
| Datagram buffer nhỏ | Payload cắt mất token | Buffer size và protocol bounds |
| Test có nhiều group listeners | Nhận datagram người khác | Token ngẫu nhiên và kiểm tra payload |
| Mạng quá tải | Mất gói ngẫu nhiên | Thử lặp có kiểm soát, loss metrics |
| Source-specific filtering | Chỉ chấp nhận sender cụ thể | Kiểm tra `MembershipKey`/SSM config |

Lỗi “không nhận được” là một **triệu chứng**, không tự xác định “NIC không hỗ trợ multicast”. Cần tách các tầng nói trên.

## 8. Chương trình Java 17+ hoàn chỉnh có kiểm thử

Chương trình `MulticastNetworkTest.java` có năm mode:

| Mode | Ý nghĩa | Có gửi multicast? |
| --- | --- | --- |
| `--self-test` | Group classification + UDP loopback unicast deterministic | **Không** |
| `--interfaces` | In trạng thái interface/up/multicastFlag/loopback/IPv4 | **Không** |
| `--probe-local IFACE` | Join một group trên interface, gửi token và nhận lại ngay trên host | **Có – chỉ chạy khi chủ động chọn** |
| `--receive IFACE PORT TOKEN` | Join multicast và đợi token từ sender trong 12 giây | Không gửi |
| `--send IFACE PORT TOKEN` | Gửi một gói multicast TTL=1 tới group/port | **Có – chỉ chạy khi chủ động chọn** |

Chương trình dùng:
- `DatagramChannel` + `StandardProtocolFamily.INET` (IPv4);
- `NetworkInterface.isUp(), supportsMulticast(), getInetAddresses()`;
- `MembershipKey` và `drop()` trong `AutoCloseable`;
- `SO_REUSEADDR` trước wildcard bind;
- `IP_MULTICAST_IF`, `IP_MULTICAST_LOOP` và `IP_MULTICAST_TTL`;
- `Selector` với timeout, `ByteBuffer`, token exact-match;
- `try-with-resources` để tránh rò network channels.

**Lưu ý:** Trong môi trường bị giới hạn bởi sandbox/firewall, `--probe-local` hoặc `--receive` có thể timeout dù interface có `supportsMulticast=true`. Đây là bằng chứng chưa quan sát thấy gói theo cấu hình thử, không phải kết luận tuyệt đối về khả năng của toàn mạng. Mode `--self-test` chỉ là kiểm tra nền tảng, không đánh tráo thành kiểm thử multicast.

Tạo file **`MulticastNetworkTest.java`**:

```java
import java.io.IOException;
import java.net.*;
import java.nio.ByteBuffer;
import java.nio.channels.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.TimeUnit;

public final class MulticastNetworkTest {
    static InetAddress group() throws IOException {
        return InetAddress.getByAddress(
                new byte[]{(byte) 239, (byte) 255, 42, 99});
    }

    static void require(boolean ok, String message) {
        if (!ok) throw new IllegalStateException(message);
    }

    static boolean hasIpv4(NetworkInterface ni) {
        Enumeration<InetAddress> addresses = ni.getInetAddresses();
        while (addresses.hasMoreElements()) {
            if (addresses.nextElement() instanceof Inet4Address) {
                return true;
            }
        }
        return false;
    }

    static NetworkInterface eligibleInterface(String name)
            throws IOException {
        NetworkInterface ni = NetworkInterface.getByName(name);
        if (ni == null) throw new IllegalArgumentException(
                "Network interface not found: " + name);
        if (!ni.isUp() || !ni.supportsMulticast() || !hasIpv4(ni)) {
            throw new IllegalArgumentException(
                    "Interface must be up, multicast-capable and IPv4");
        }
        return ni;
    }

    static int checkedPort(String raw) {
        int port = Integer.parseInt(raw);
        if (port < 1024 || port > 65535) {
            throw new IllegalArgumentException(
                    "Use a UDP port from 1024 to 65535");
        }
        return port;
    }

    static String checkedToken(String token) {
        if (!token.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException(
                    "Token must have 1-64 ASCII letters, digits, _ or -");
        }
        return "MCTEST:" + token;
    }

    record Listener(DatagramChannel channel, MembershipKey membership)
            implements AutoCloseable {
        @Override
        public void close() throws IOException {
            try {
                membership.drop();
            } finally {
                channel.close();
            }
        }
    }

    static Listener listen(NetworkInterface ni, int port)
            throws IOException {
        DatagramChannel channel =
                DatagramChannel.open(StandardProtocolFamily.INET);
        try {
            channel.setOption(StandardSocketOptions.SO_REUSEADDR, true);
            channel.bind(new InetSocketAddress(port));
            channel.setOption(StandardSocketOptions.IP_MULTICAST_LOOP, true);
            MembershipKey key = channel.join(group(), ni);
            return new Listener(channel, key);
        } catch (IOException | RuntimeException ex) {
            channel.close();
            throw ex;
        }
    }

    static int send(NetworkInterface ni, int port, String payload)
            throws IOException {
        try (DatagramChannel sender =
                DatagramChannel.open(StandardProtocolFamily.INET)) {
            sender.setOption(StandardSocketOptions.IP_MULTICAST_IF, ni);
            sender.setOption(StandardSocketOptions.IP_MULTICAST_LOOP, true);
            sender.setOption(StandardSocketOptions.IP_MULTICAST_TTL, 1);
            ByteBuffer data = ByteBuffer.wrap(
                    payload.getBytes(StandardCharsets.US_ASCII));
            int n = sender.send(
                    data, new InetSocketAddress(group(), port));
            require(n == payload.length(), "Incomplete datagram send");
            return n;
        }
    }

    static boolean receiveExpected(
            DatagramChannel channel, String expected, long timeoutMs)
            throws IOException {
        channel.configureBlocking(false);
        try (Selector selector = Selector.open()) {
            channel.register(selector, SelectionKey.OP_READ);
            ByteBuffer data = ByteBuffer.allocate(1024);
            long deadline = System.nanoTime()
                    + TimeUnit.MILLISECONDS.toNanos(timeoutMs);
            while (true) {
                long left = deadline - System.nanoTime();
                if (left <= 0) return false;
                long wait = Math.max(1,
                        Math.min(250, TimeUnit.NANOSECONDS.toMillis(left)));
                selector.select(wait);
                selector.selectedKeys().clear();

                SocketAddress sender;
                while ((sender = channel.receive(data)) != null) {
                    data.flip();
                    String text = StandardCharsets.US_ASCII
                            .decode(data).toString();
                    if (expected.equals(text)) return true;
                    data.clear();
                }
            }
        }
    }

    static void selfTest() throws IOException {
        InetAddress group = group();
        require(group.isMulticastAddress(), "Invalid test group");
        require(group instanceof Inet4Address, "Group is not IPv4");
        InetAddress loopback = InetAddress.getByName("127.0.0.1");
        String received = null;
        try (DatagramChannel listener =
                    DatagramChannel.open(StandardProtocolFamily.INET);
             DatagramChannel sender =
                    DatagramChannel.open(StandardProtocolFamily.INET)) {
            listener.bind(new InetSocketAddress(loopback, 0));
            String expected = "PING";
            int n = sender.send(
                    ByteBuffer.wrap(expected.getBytes(
                            StandardCharsets.US_ASCII)),
                    listener.getLocalAddress());
            require(n == 4, "Unicast send failed");
            listener.configureBlocking(false);
            try (Selector selector = Selector.open()) {
                listener.register(selector, SelectionKey.OP_READ);
                if (selector.select(2000) == 0) {
                    throw new IOException("Unicast UDP loopback timed out");
                }
                ByteBuffer data = ByteBuffer.allocate(32);
                SocketAddress origin = listener.receive(data);
                require(origin != null, "No UDP datagram");
                data.flip();
                received = StandardCharsets.US_ASCII
                        .decode(data).toString();
            }
        }
        require("PING".equals(received), "Wrong UDP payload");
        System.out.println("selftest.groupIsMulticast=true");
        System.out.println("selftest.groupIsIPv4=true");
        System.out.println("selftest.unicastPayload=PING");
        System.out.println("selftest.multicastTrafficSent=false");
        System.out.println("checks=PASS");
    }

    static void listInterfaces() throws IOException {
        Enumeration<NetworkInterface> interfaces =
                NetworkInterface.getNetworkInterfaces();
        System.out.println(
                "name | up | multicastFlag | loopback | ipv4");
        if (interfaces == null) return;
        while (interfaces.hasMoreElements()) {
            NetworkInterface ni = interfaces.nextElement();
            System.out.printf(
                    "%s | %s | %s | %s | %s%n",
                    ni.getName(), ni.isUp(), ni.supportsMulticast(),
                    ni.isLoopback(), hasIpv4(ni));
        }
    }

    static void probeLocal(String iface) throws IOException {
        NetworkInterface ni = eligibleInterface(iface);
        String token = checkedToken(
                UUID.randomUUID().toString().substring(0, 8));
        boolean matched;
        int sent;
        try (Listener listener = listen(ni, 0)) {
            int port = ((InetSocketAddress)
                    listener.channel().getLocalAddress()).getPort();
            sent = send(ni, port, token);
            matched = receiveExpected(listener.channel(), token, 4000);
        }
        System.out.println("probe.sentBytes=" + sent);
        System.out.println("probe.receivedMatching=" + matched);
        require(matched, "Local multicast delivery not observed");
        System.out.println("probe.result=PASS_LOCAL_ONLY");
    }

    static void receive(String iface, int port, String token)
            throws IOException {
        NetworkInterface ni = eligibleInterface(iface);
        boolean matched;
        try (Listener listener = listen(ni, port)) {
            System.out.println("receiver.joined=true");
            System.out.println("receiver.ready=true");
            matched = receiveExpected(listener.channel(), token, 12000);
        }
        System.out.println("receiver.receivedMatching=" + matched);
        require(matched, "No matching multicast message before timeout");
        System.out.println("receiver.result=PASS");
    }

    static void sendToGroup(String iface, int port, String token)
            throws IOException {
        NetworkInterface ni = eligibleInterface(iface);
        int bytes = send(ni, port, token);
        System.out.println("sender.sentBytes=" + bytes);
        System.out.println("sender.deliveryUnconfirmed=true");
    }

    static void usage() {
        System.out.println("Usage:");
        System.out.println("  java MulticastNetworkTest --self-test");
        System.out.println("  java MulticastNetworkTest --interfaces");
        System.out.println("  java MulticastNetworkTest --probe-local IFACE");
        System.out.println("  java MulticastNetworkTest --receive IFACE PORT TOKEN");
        System.out.println("  java MulticastNetworkTest --send IFACE PORT TOKEN");
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 0
                || (args.length == 1 && args[0].equals("--self-test"))) {
            selfTest();
        } else if (args.length == 1
                && args[0].equals("--interfaces")) {
            listInterfaces();
        } else if (args.length == 2
                && args[0].equals("--probe-local")) {
            probeLocal(args[1]);
        } else if (args.length == 4
                && args[0].equals("--receive")) {
            receive(args[1], checkedPort(args[2]),
                    checkedToken(args[3]));
        } else if (args.length == 4
                && args[0].equals("--send")) {
            sendToGroup(args[1], checkedPort(args[2]),
                    checkedToken(args[3]));
        } else {
            usage();
            throw new IllegalArgumentException("Invalid arguments");
        }
    }
}
```

### 8.1. Biên dịch và chạy chế độ an toàn mặc định

```bash
javac -encoding UTF-8 MulticastNetworkTest.java
java MulticastNetworkTest --self-test
```

**Stdout chính xác đã kiểm chứng thực tế bằng JDK 17+:**

```text
selftest.groupIsMulticast=true
selftest.groupIsIPv4=true
selftest.unicastPayload=PING
selftest.multicastTrafficSent=false
checks=PASS
```

`selftest.multicastTrafficSent=false` là một **chỉ báo quan trọng về độ trung thực của kiểm thử**: chưa gửi multicast. Chỉ có thể kết luận code/UDP loopback local hoạt động và group bytes đã được phân loại đúng.

### 8.2. Liệt kê giao diện mạng

```bash
java MulticastNetworkTest --interfaces
```

Kết quả có dòng tiêu đề:

```text
name | up | multicastFlag | loopback | ipv4
```

Các dòng tiếp theo **phụ thuộc máy thật**. Ví dụ minh họa (không phải stdout cố định):

```text
eth0 | true | true | false | true
lo | true | false | true | true
```

Không phải hệ nào có interface tên `eth0` hoặc `lo`; xem chính xác những tên được lệnh trả về. Một interface báo `multicastFlag=true` chỉ là **ứng viên để thử**, không tự kết luận đường mạng giữa hai hosts hoạt động.

### 8.3. Kiểm thử multicast trên một host theo NIC đã chọn

Chỉ chạy khi được phép phát một datagram multicast trên interface trong môi trường test. Chọn `IFACE` từ kết quả `--interfaces`:

```bash
java MulticastNetworkTest --probe-local "eth0"
```

Ví dụ khi thành công, output chính có dạng:

```text
probe.sentBytes=15
probe.receivedMatching=true
probe.result=PASS_LOCAL_ONLY
```

Đây chỉ là **minh họa dạng output**, không phải kết quả đã được kiểm chứng trên mọi NIC/OS. Độ dài token trong chương trình là 7 byte `MCTEST:` cộng 8 ký tự token random, vì vậy `sentBytes=15` trong mode này.

Nếu không nhận được packet trong 4 giây, chương trình ném lỗi `Local multicast delivery not observed`. Điều đó nói rằng **trong cấu hình thử này** không quan sát được local multicast loopback, không đủ bằng chứng để kết luận card mạng “không hỗ trợ multicast” ở mọi trường hợp.

### 8.4. Kiểm thử multicast giữa hai host

Chuẩn bị **hai máy trên mạng được phép thử**, tên interface có thể khác nhau. Đảm bảo receiver lắng nghe đúng group `239.255.42.99`, UDP port cùng nhau, và không có dịch vụ khác sử dụng port. Ví dụ chọn port `49876` và token `test2026`:

Trên **máy nhận A** (chạy trước):

```bash
java MulticastNetworkTest --receive "eth0" 49876 test2026
```

Chờ thấy:

```text
receiver.joined=true
receiver.ready=true
```

Sau đó chạy **ngay** trên máy gửi B trước deadline 12 giây:

```bash
java MulticastNetworkTest --send "eth0" 49876 test2026
```

Sender có thể in:

```text
sender.sentBytes=15
sender.deliveryUnconfirmed=true
```

Đây là **output minh họa** cho token `MCTEST:test2026`. `deliveryUnconfirmed=true` cố ý nhắc rằng **send thành công không chứng minh delivery**.

Nếu thực sự có multicast delivery giữa hai host trong thời hạn chờ, receiver báo:

```text
receiver.receivedMatching=true
receiver.result=PASS
```

Đây là **output kỳ vọng nếu mạng đủ điều kiện**, không phải stdout mặc định đã chạy thử trong môi trường này. Nếu timeout, receiver in `receiver.receivedMatching=false` rồi báo lỗi. Không che giấu timeout hoặc biến nó thành PASS.

Với Windows hoặc macOS, thay `eth0` bằng đúng **tên interface Java trả từ `--interfaces`**, đặt trong dấu nháy nếu tên chứa khoảng trắng.

### 8.5. Tại sao receiver phải chạy trước sender?

UDP multicast không lưu gói để một thành viên join sau được nhận lại. Nếu sender phát trước khi receiver join, receiver có thể bỏ lỡ gói. Bài kiểm thử chỉ chờ tối đa 12 giây; hãy mở receiver trước, quan sát `ready=true` rồi phát ngay từ sender.

### 8.6. Khi nào `--receive` PASS vẫn chưa đủ?

Một lần nhận đúng datagram chỉ xác nhận **một đường đi tại một thời điểm**. Muốn vận hành dịch vụ multicast dài hạn, cần kiểm thử lặp:
- Loss rate và jitter trong điều kiện tải hợp lý.
- Đổi Wi-Fi/Ethernet hoặc mất/khôi phục NIC.
- Router reboot và IGMP membership refresh.
- Nhiều receivers, nhiều nguồn và source filtering.
- Khác VLAN/subnet nếu có thiết kế multicast routing.
- IPv6 multicast riêng nếu triển khai thực sự dùng IPv6.
- Các chính sách firewall và mạng cloud/container.

Không tăng tốc bắn traffic lên mạng production để “thử cho chắc”; phải dùng lab hoặc kế hoạch thử nghiệm được cấp phép.

## 9. Diễn giải kết quả theo từng tầng

| Kết quả quan sát | Được phép kết luận | Không được phép kết luận |
| --- | --- | --- |
| `supportsMulticast=true` | OS báo NIC có capability multicast | Group packet đến nơi |
| `--self-test` PASS | UDP loopback unicast trên host hoạt động | Network hỗ trợ multicast |
| `join` trả `MembershipKey` | Membership request được provider chấp nhận | Có packet từ sender |
| `send` trả đúng số bytes | Sender đã chấp nhận datagram local | Remote receiver nhận |
| `--probe-local` PASS | Multicast local delivery qua cấu hình test | Cross-host multicast hoạt động |
| Receiver host B nhận đúng token | Một chiều multicast A→B thành công trong lần thử | Không có packet loss dài hạn |
| Test cùng VLAN PASS, khác VLAN FAIL | Có thể có vấn đề multicast routing/scope | Chắc chắn do code Java sai |
| Timeout khi chờ | Không thấy đúng token trong deadline | “Thiết bị hoàn toàn không hỗ trợ multicast” |
| `MembershipKey.isValid=true` | Membership key còn valid tại JVM/channel | Switch/router thực sự forwarding |
| Join source-specific fail | Platform/config chưa hỗ trợ kiểu membership đó | Mọi multicast đều không hoạt động |

**Nguyên tắc:** luận điểm phải có bằng chứng tương ứng. Không đánh giá network capability bằng một `println(true)` duy nhất.

## 10. Bảo mật và an toàn khi kiểm thử

### 10.1. Chỉ gửi multicast có chủ đích

Chương trình mặc định `--self-test` không phát multicast ra NIC. Hai mode `--probe-local` và `--send` **có** gửi một datagram tới group được cấu hình. Chỉ dùng chúng trên mạng được phép; TTL=1 làm giới hạn số hop, không đồng nghĩa “không ra ngoài máy”.

Group `239.255.42.99` không phải group bí mật hay được cấp riêng cho ứng dụng; lựa chọn nhóm sản xuất cần theo điều phối địa chỉ của tổ chức.

### 10.2. Không tin payload từ network

Một UDP datagram có thể đến từ nguồn không tin cậy. Chương trình kiểm thử:
- Dùng token ASCII đã biết hoặc token ngẫu nhiên.
- So khớp **toàn bộ payload** bằng `String.equals`.
- Giới hạn receive buffer 1024 byte.
- Có deadline không block vô hạn.
- Đóng network resources khi kết thúc.

Trong sản phẩm, token chỉ dùng để **phân biệt gói thử**, không thay thế authentication hay encryption. Nếu dữ liệu nhạy cảm, phải dùng cơ chế bảo mật phù hợp với threat model; IP multicast không tự cung cấp bảo mật nội dung.

### 10.3. Không tự động “sửa” firewall hay route

Nếu test FAIL, nên báo nguyên nhân nghi ngờ và hướng kiểm tra. Không tự thay đổi firewall rules, route tables, NIC settings hay nâng quyền hệ thống nếu chưa được người vận hành cho phép.

### 10.4. Giới hạn thời gian và tài nguyên

- `--probe-local` chờ tối đa 4 giây.
- `--receive` chờ tối đa 12 giây.
- `--self-test` đợi UDP loopback tối đa 2 giây.
- `--send` chỉ gửi một datagram nhỏ.

Các mốc trên phù hợp bài demo nhỏ, không phải cấu hình bắt buộc cho production. `Selector` và `ByteBuffer` giúp tránh vòng chờ vô hạn; `try-with-resources` và `MembershipKey.drop` tránh giữ membership sau test.

## 11. Quy trình chẩn đoán khi multicast không tới

Để khoanh vùng nguyên nhân, dùng thứ tự:

1. **Kiểm tra family**: địa chỉ group `Inet4Address` thì mở `DatagramChannel.open(INET)`; group IPv6 thì `INET6`. Không dựa vào `DatagramChannel.open()` mặc định vì family không được đặc tả.
2. **Kiểm tra NIC**: `isUp`, `supportsMulticast`, IPv4/IPv6, route tới sender/receiver, VLAN.
3. **Kiểm tra socket configuration**: `SO_REUSEADDR` trước bind, receiver bind wildcard, same port/group, proper `join` và `MembershipKey` valid.
4. **Kiểm tra outgoing interface**: `IP_MULTICAST_IF` là NIC thật dùng để phát. Không chọn nhầm VPN/loopback.
5. **Kiểm tra phạm vi**: `IP_MULTICAST_TTL=1` không đi qua nhiều router; nếu cần cross-subnet, phải có multicast-routing được thiết kế và cho phép. Không chỉ tăng TTL để bỏ qua policy.
6. **Kiểm tra firewall**: host firewall/endpoint security cho phép UDP port/group cần thiết; có thể khác nhau giữa ingress/egress.
7. **Kiểm tra switch**: IGMP snooping và querier cho IPv4 multicast. Nếu thiếu querier hoặc membership reports không được xử lý, switch có thể không chuyển group traffic tới port mong muốn.
8. **Kiểm tra router**: multicast routing (ví dụ PIM khi được vận hành) khác với unicast routing, NAT/VPN/cloud không nhất thiết hỗ trợ group.
9. **Kiểm tra payload**: token đúng, byte encoding, port đúng, buffer đủ; gói đã tới nhưng parse sai khác với gói không tới.
10. **Quan sát tại hai đầu**: receiver log readiness/membership và received count; sender log send count. Nếu có quyền, dùng network capture được tổ chức cho phép để xem IGMP/UDP, chú ý bảo mật dữ liệu.
11. **So sánh tầng**: nếu unicast PASS, join PASS, local multicast PASS nhưng cross-host FAIL, ưu tiên điều tra network path chứ không đổ lỗi ngay cho `ByteBuffer`.
12. **Đánh giá kết luận**: một lần fail không nhất thiết là không hỗ trợ; thử lại có kiểm soát sau khi cấu hình được xác minh.

### 11.1. IGMP và MLD

Đối với IPv4 multicast, hệ thống thường dùng IGMP để thể hiện membership tới mạng; với IPv6 multicast, cơ chế tương ứng là MLD. Java `join` yêu cầu hệ thống tham gia nhóm nhưng không tự cấu hình switch/router/querier trên hạ tầng.

Một số mạng triển khai IGMP snooping để chuyển multicast hiệu quả. Khi các thiết bị bị cấu hình sai, gói có thể bị drop, flood hoặc không tới đúng port. Không dùng `supportsMulticast()` như bằng chứng switch snooping đã đúng.

### 11.2. Wi-Fi, VPN, VM, cloud và containers

- Access point có thể hạn chế multicast/broadcast, tối ưu power-save hoặc chuyển thành unicast theo thiết kế.
- VPN có thể chỉ forward unicast.
- VM virtual NIC và NAT networking có thể có flag hỗ trợ nhưng path multicast bị giới hạn.
- Container bridge và overlay network có thể không truyền multicast group theo cách mạng vật lý đang truyền.
- Cloud VPC thường có giới hạn về multicast tùy nhà cung cấp và sản phẩm; cần kiểm tra tài liệu môi trường đang dùng.
- Nhiều NIC cùng up không đồng nghĩa outbound multicast đi ra NIC bạn mong muốn; đặt `IP_MULTICAST_IF`.

**Đừng khẳng định tất cả công nghệ trên luôn chặn multicast.** Đây là các lớp cần kiểm tra, phụ thuộc kiến trúc cụ thể.

## 12. Kiểm thử âm tính và ma trận QA

### 12.1. Unit tests không dùng mạng

Một số trường hợp có thể kiểm thử độc lập hệ điều hành:
- Địa chỉ `239.255.42.99` được phân loại IPv4 multicast.
- `127.0.0.1` không phải multicast.
- `checkedPort("0")` bị từ chối theo policy CLI (mode two-host chỉ nhận 1024–65535).
- `checkedPort("49876")` được chấp nhận.
- `checkedToken("test2026")` trả `MCTEST:test2026`.
- Token có dấu cách/ký tự điều khiển bị từ chối.
- Chọn đúng `INET` cho group IPv4.
- Bài học không gửi multicast tự động khi chưa chọn mode chủ động.

Các unit tests này **không cần** giả định LAN có hỗ trợ multicast.

### 12.2. Integration tests theo tầng

| Test | Điều kiện | Điều cần assert |
| --- | --- | --- |
| UDP loopback unicast | Host cho phép UDP loopback | Nhận đúng `PING` |
| Interface enumeration | Java có quyền đọc interfaces | In đúng các flags hiện có, không hard-code tên |
| Join thử trên NIC | NIC up, IPv4, multicastFlag | Membership được chấp nhận hoặc lỗi rõ |
| Local multicast | NIC có loopback multicast theo OS | Nhận đúng token hoặc timeout rõ |
| Hai hosts cùng subnet | NIC/UDP/firewall/group đúng | Receiver nhận đúng token |
| Khác subnet/VLAN | Router multicast được cấu hình | Receiver nhận đúng token nếu route cho phép |
| Port đang được dùng | Đối tượng cạnh tranh port | Đo đúng failure, không overwrite |
| Group không hợp lệ | `InetAddress` unicast | Fail trước `join` |
| Interface không tồn tại | `--probe-local` với tên sai | `IllegalArgumentException` rõ |
| Interface chỉ có IPv6 | Demo IPv4 | Reject theo policy, không chọn family sai |
| Receiver chạy quá muộn | Sender phát trước membership | Timeout có thể xảy ra, không báo PASS |
| Không có sender | Receiver chờ quá deadline | In `receivedMatching=false` và fail |
| Tác vụ bị interrupt/close | Channel/Selector dừng | Resource được cleanup |
| Nhiều packet lạ | Traffic chung group | Chỉ token đúng mới được chấp nhận |

### 12.3. Không có stdout cố định cho live network

Tránh đưa ra lời khẳng định như “trên mọi máy `--interfaces` sẽ có `eth0 true true`”. Interface names, IPs, trạng thái route, firewall và tốc độ mạng thay đổi. Chỉ stdout `--self-test` đã được chạy xác minh ở môi trường kiểm thử. Các dòng `--probe-local`/`--receive` là **kỳ vọng có điều kiện** khi đường multicast thực sự hoạt động.

### 12.4. CI và test automation

Trong CI thông thường, không nên bắt mọi build phải chạy multicast giữa hai máy thật vì cloud runner có thể không có multicast routing. Có thể tách:

- **Unit tests:** xác minh address/family/port/token validation; không network.
- **Local unicast smoke test:** chỉ khi runner cho phép UDP loopback.
- **Multicast integration test:** chỉ trên runner/lab có NIC và mạng được xác nhận hỗ trợ; cấu hình rõ group, port và interface.
- **Pre-deployment test:** kiểm tra trực tiếp topology production-like được phép và lưu evidence nhận ở hai phía.

Không cho test thất bại âm thầm chỉ vì cấu hình thiếu; dùng trạng thái **SKIPPED_UNSUPPORTED_ENVIRONMENT** hoặc thông báo khả năng không đủ, khác với test **FAILED_DELIVERY** đã chạy trên môi trường phù hợp. Trong code CLI demo, thiếu interface/timeout sẽ ném lỗi rõ; hệ CI cần tự phân loại log đó.

## 13. Vấn đề thường bị hiểu nhầm

| Nhận định sai | Thực tế đúng |
| --- | --- |
| “`supportsMulticast()==true` là mạng đang chạy multicast tốt” | Đó chỉ là cờ capability theo OS |
| “Gửi UDP thành công tức bên kia đã nhận” | `DatagramChannel.send` chỉ xác nhận phía gửi |
| “UDP loopback unicast PASS chứng minh multicast” | Unicast không kiểm tra `join`/IGMP |
| “Local multicast PASS đủ để production” | Chưa kiểm tra switch/router/firewall giữa hosts |
| “Không có packet trong 4 giây thì NIC chắc chắn không hỗ trợ” | Có nhiều nguyên nhân: sender, route, loopback, deadline |
| “Một kênh IPv6 tự nhận IPv4 group” | Cross-family multicast không portable |
| “`IP_MULTICAST_IF` chọn family socket” | Nó chọn interface gửi multicast, family chọn khi mở kênh |
| “`SO_REUSEADDR` bật multicast” | Chỉ liên quan address/port reuse |
| “`join` giống `connect` TCP” | Membership không cung cấp reliable connection |
| “TTL=1 nghĩa gói không rời host” | TTL=1 có thể tới cùng subnet; không phải host-only |
| “Token là xác thực bảo mật” | Token chỉ phân biệt gói thử, có thể bị bắt chước |
| “Receiver bound một IP cụ thể luôn nhận group” | Java MulticastChannel khuyến nghị wildcard bind |
| “Một lần `receive` lấy được bao nhiêu byte tùy ý” | Datagram có ranh giới và có thể bị truncate nếu buffer nhỏ |
| “Đóng channel không cần drop MembershipKey” | Đóng channel sẽ vô hiệu membership, nhưng `drop` làm ý định vòng đời rõ |
| “Có `isUp=true` thì firewall chắc chắn cho UDP qua” | Host/network policy vẫn có thể chặn |

## 14. Câu hỏi ôn tập

**Câu 1.** `NetworkInterface.supportsMulticast()` kiểm tra điều gì?  
**Đáp án:** Khả năng multicast do OS báo về interface. Không chứng minh packet delivery.

**Câu 2.** Tại sao phải có `--self-test` trước khi thử multicast?  
**Đáp án:** Để loại bỏ lỗi cơ bản của UDP loopback/`DatagramChannel`/`Selector` mà không gửi multicast ra mạng.

**Câu 3.** `--self-test` PASS có đủ kết luận mạng hỗ trợ multicast không?  
**Đáp án:** Không. Mode đó chỉ gửi unicast trên `127.0.0.1`.

**Câu 4.** Cần gì để join IPv4 multicast group?  
**Đáp án:** Một `DatagramChannel` họ `INET`, địa chỉ group `Inet4Address` hợp lệ, `NetworkInterface` thích hợp và `join(group, ni)`.

**Câu 5.** Vì sao bind wildcard khi nhận multicast?  
**Đáp án:** Việc nhận multicast với socket bind tới một IP cụ thể là phụ thuộc implementation; wildcard được khuyến nghị.

**Câu 6.** `IP_MULTICAST_IF` làm gì?  
**Đáp án:** Chọn interface cho multicast outgoing datagrams, không thay đổi family socket.

**Câu 7.** `IP_MULTICAST_LOOP=true` có đảm bảo trên mọi OS sẽ nhận gói gửi bởi chính host không?  
**Đáp án:** Không. Semantics loopback option phụ thuộc hệ thống và chính sách mạng.

**Câu 8.** Tại sao phải đợi receiver báo `ready=true` rồi mới chạy sender?  
**Đáp án:** UDP không replay datagrams đã phát trước khi receiver tham gia group.

**Câu 9.** Tại sao `send` in `deliveryUnconfirmed=true`?  
**Đáp án:** Vì trả số byte gửi không phải acknowledgement từ receiver.

**Câu 10.** Cần gì để kết luận có delivery giữa hai hosts?  
**Đáp án:** Receiver trên host khác nhận đúng payload/token trong cùng group/port, với NIC và tuyến mạng được xác minh.

**Câu 11.** Nếu local multicast PASS nhưng cross-host FAIL, nên kiểm tra gì trước?  
**Đáp án:** Interface, firewall, IGMP snooping, VLAN/router multicast, TTL và container/VPN path.

**Câu 12.** Vì sao không coi `MembershipKey.isValid()` là bằng chứng packet đến?  
**Đáp án:** Nó phản ánh trạng thái membership ở channel, không chứng minh một gói đã đi qua toàn bộ network path.

**Câu 13.** Chương trình mẫu có hỗ trợ thực thi IPv6 multicast không?  
**Đáp án:** Code thử thực tế chọn IPv4/`INET` để dễ kiểm soát; IPv6 cần triển khai một phép thử riêng với `INET6`, `Inet6Address`, NIC/scope và MLD phù hợp.

**Câu 14.** Vì sao không dùng nhóm/port của hệ thống production để học?  
**Đáp án:** Có thể gây trùng traffic, ảnh hưởng dịch vụ hoặc phát gói ngoài phạm vi được phép.

**Câu 15.** Nếu receiver timeout, test ghi PASS hay FAIL?  
**Đáp án:** Không có bằng chứng delivery, nên phải báo timeout/failure cho cấu hình đã thử, không thể báo PASS.

## 15. Checklist triển khai trước khi kết luận network multicast hoạt động

- [ ] Group IPv4/IPv6 thuộc dải multicast phù hợp và được phép dùng.
- [ ] Kênh mở bằng `StandardProtocolFamily.INET` hoặc `INET6` tương ứng.
- [ ] Network interface thực sự tồn tại, up và có địa chỉ cùng family.
- [ ] `supportsMulticast` được đọc nhưng không bị lạm dụng thành kết luận.
- [ ] Chọn interface chính xác thay vì interface đầu tiên.
- [ ] Receiver dùng `SO_REUSEADDR` trước wildcard bind nếu cần.
- [ ] Đã gọi `join(group, ni)` và quản lý `MembershipKey`.
- [ ] Sender dùng `IP_MULTICAST_IF` đúng interface và scope.
- [ ] `IP_MULTICAST_TTL` không vượt phạm vi kiểm thử được phép.
- [ ] Test local unicast và multicast riêng biệt.
- [ ] Mặc định không phát multicast ngoài khi chưa chỉ định.
- [ ] Dùng token duy nhất, verify payload exact, deadline, giới hạn buffer.
- [ ] Ghi nhận sender result **và** receiver result.
- [ ] Test hai hosts nếu muốn kiểm chứng đường truyền hai máy.
- [ ] Với khác VLAN/subnet, xác minh router multicast, IGMP/MLD, TTL.
- [ ] Xác minh firewall, Wi-Fi, VPN, container, cloud policy tùy triển khai.
- [ ] Không coi một packet test PASS chứng minh độ tin cậy lâu dài.
- [ ] Có logging/metrics/tình huống timeout và yêu cầu bảo mật.
- [ ] Tắt test, drop membership và close channels sau khi hoàn tất.
- [ ] Phân loại unsupported environment khác với failed delivery.
- [ ] Không thay đổi cấu hình mạng trái phép để làm cho test PASS.

## 16. Kết luận và tài liệu chính thức còn hiệu lực

“**Kiểm thử mạng có hỗ trợ multicast**” phải được hiểu thành **chuỗi kiểm tra tăng dần về bằng chứng**. Java `NetworkInterface.supportsMulticast()` chỉ hỗ trợ bước phát hiện capability. `DatagramChannel.open(INET/INET6)`, `join` và `MembershipKey` xác lập membership. `send` phát datagram. Chỉ khi một **receiver nhận đúng token từ sender** mới có bằng chứng delivery cho mạng, interface, group, port và thời điểm đã kiểm thử.

Bài sử dụng Java NIO.2 còn áp dụng trong Java 17+, không dựa vào những phương thức socket đã lỗi thời. Với các phép thử mạng, cần nêu rõ môi trường: self-test nội bộ, local multicast hay kiểm thử giữa hai hosts, để không biến một PASS cục bộ thành tuyên bố quá mức.

### Tài liệu Oracle Java SE 17

- [`NetworkInterface`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/NetworkInterface.html): `getNetworkInterfaces`, `getByName`, `isUp`, `supportsMulticast`, địa chỉ giao diện.
- [`MulticastChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/MulticastChannel.html): `join`, wildcard bind, `SO_REUSEADDR`, source filtering, khả năng phụ thuộc hệ thống.
- [`DatagramChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/DatagramChannel.html): open family, bind, send/receive, nonblocking channels.
- [`StandardProtocolFamily`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/StandardProtocolFamily.html): `INET`, `INET6`, `UNIX`.
- [`StandardSocketOptions`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/StandardSocketOptions.html): `SO_REUSEADDR`, `IP_MULTICAST_IF`, `IP_MULTICAST_LOOP`, `IP_MULTICAST_TTL`.
- [`MembershipKey`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/MembershipKey.html): membership validity và `drop`.
- [`Selector`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html): readiness-based nonblocking I/O và deadline.
- [`InetAddress`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InetAddress.html): địa chỉ IP và `isMulticastAddress`.
