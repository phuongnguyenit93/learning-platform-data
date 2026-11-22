# Tham gia nhóm bằng MulticastChannel trong Java NIO.2

> **Mục tiêu:** Hiểu đúng cách dùng `MulticastChannel.join(...)` để đăng ký nhận UDP multicast, lựa chọn `NetworkInterface`, tạo `DatagramChannel` theo IPv4/IPv6, cấu hình socket trước khi bind, theo dõi và rời nhóm bằng `MembershipKey`, lọc nguồn với source-specific membership hoặc `block/unblock` khi nền tảng hỗ trợ, và gửi/nhận thử trong phạm vi máy cục bộ. Đây là API từ Java 7 **vẫn còn áp dụng trong Java 17+**, không phải kỹ thuật đã legacy. Chín chương trình Java 17 độc lập bên dưới đã được biên dịch và chạy. Những kết quả phụ thuộc hệ điều hành/mạng sẽ được ghi rõ thay vì hứa hẹn kết quả cố định ở mọi môi trường.

## 1. Multicast là gì và vì sao có “join group”?

UDP thông thường gửi một datagram từ nguồn đến một địa chỉ đích đơn lẻ (unicast) hoặc có thể broadcast theo phạm vi mạng. **IP multicast** cho phép một sender gửi datagrams tới **địa chỉ nhóm**. Hệ điều hành/mạng phân phối các datagram tới các hosts/interfaces đã đăng ký tham gia nhóm đó, theo khả năng triển khai multicast.

```text
             UDP sender
                 |
                 | Datagram tới 239.255.42.99:5000
                 v
          IP multicast group
            /      |       \
           /       |        \
   Host A:5000  Host B:5000  Host C:5000
   join on NIC1 join on NIC2  chưa join
   có thể nhận  có thể nhận  không tự động nhận như thành viên
```

**Nhóm multicast không phải kết nối TCP.** Không có session connect/accept, không tự bảo đảm gửi thành công, đúng thứ tự, không lặp, và không bắt buộc mọi thành viên đều nhận được mỗi packet. UDP có thể mất gói, bị firewall/router/container chặn, bị host OS bỏ hoặc vượt receive buffer.

### 1.1. Bốn khái niệm riêng

| Khái niệm | Ví dụ | Vai trò |
| --- | --- | --- |
| **Địa chỉ nhóm** | `239.255.42.99` | IP multicast destination chung |
| **Cổng UDP** | `5000` | Port nơi receiver bind và sender gửi tới |
| **NetworkInterface** | Card mạng Ethernet, Wi-Fi hay loopback | Interface host dùng để tham gia nhóm |
| **MembershipKey** | Kết quả `channel.join(group, nic)` | Token quản lý đúng membership trên đúng channel/group/interface |

Khi thay một trong các yếu tố này, hành vi nhận có thể khác. Hai processes cùng join **group** nhưng bind các **port** khác nhau không tự nhận cùng một UDP datagram. Hai interfaces khác nhau có thể thuộc các segment/vùng mạng riêng. Một sender không nhất thiết cần join group để **gửi**, trong khi một receiver thường phải join đúng group trên đúng interface để nhận multicast.

### 1.2. Địa chỉ IPv4 và IPv6 multicast

- IPv4 multicast thuộc `224.0.0.0/4`. Các ví dụ dùng `239.255.42.x`, một phần không gian administratively scoped; chúng phục vụ lab, **không phải quyền độc chiếm** của một ứng dụng.
- IPv6 multicast dùng địa chỉ bắt đầu bằng `ff00::/8`, với các scope/hạn chế riêng; ví dụ `ff02::1` là nhóm IPv6 multicast link-local.
- Dùng `InetAddress.isMulticastAddress()` để xác minh **tính multicast của địa chỉ**, không phải để xác minh network provider sẽ cho join.
- `NetworkInterface` phải tương thích với address family và môi trường chạy. IPv6 link-local có yêu cầu scope/interface cần được cấu hình đúng.

Tránh tự suy rằng một IPv4 multicast group sẽ join được trên `DatagramChannel.open(INET6)`; Javadoc khuyên chọn `ProtocolFamily` phù hợp loại địa chỉ.

## 2. `MulticastChannel` là interface, không phải class để gọi open()

`java.nio.channels.MulticastChannel` là **interface** kế thừa `NetworkChannel`. Implementation NIO.2 thông dụng được Java cung cấp là `DatagramChannel`.

```java
DatagramChannel channel =
        DatagramChannel.open(StandardProtocolFamily.INET);
MulticastChannel membershipApi = channel;
```

Đây là snippet, cần import `java.nio.channels.DatagramChannel`, `MulticastChannel` và `java.net.StandardProtocolFamily`, và một method xử lý IOException. `DatagramChannel` được dùng khi cần cả `send/receive`; `MulticastChannel` là abstraction có `join` và chức năng quản lý socket.

### 2.1. Hai overload join

```java
MembershipKey anySource = channel.join(group, networkInterface);

MembershipKey oneSource =
        channel.join(group, networkInterface, sourceAddress);
```

Đây là snippet, **không gọi cả hai dòng cho cùng group/interface trên cùng channel**: chúng minh họa **hai chế độ thay thế**. Nếu đã có any-source membership, việc tạo source-specific membership trên cùng group/interface sẽ ném `IllegalStateException` và ngược lại.

- `join(group,ni)`: **Any-Source Multicast (ASM)** — nhận datagrams từ các nguồn gửi đến nhóm (subject to OS/network delivery).
- `join(group,ni,source)`: **Source-Specific Multicast (SSM)** — chỉ đăng ký nhận datagrams có địa chỉ nguồn phù hợp. Cần OS hỗ trợ source filtering; có thể ném `UnsupportedOperationException`.

`join` trả `MembershipKey` để quản lý group membership. **Không** gán ý nghĩa của token đó là một socket mới hoặc một datagram: channel vẫn là channel cũ, key chỉ quản lý trạng thái tham gia.

### 2.2. Có nhiều groups hoặc interfaces được không?

Có. Theo Javadoc, một channel có thể join nhiều groups và cùng group trên nhiều interfaces. Tuy nhiên implementation có thể giới hạn số memberships. Khi ứng dụng có nhiều interfaces, nên lưu token và mô tả rõ mỗi {channel,group,interface,source} được sở hữu bởi thành phần nào.

## 3. Chuẩn bị NetworkInterface phù hợp

Một tên interface hard-code như `eth0`, `wlan0` hoặc `en0` không portable giữa Windows, Linux, macOS, container hay CI. Có thể:
1. Nhận tên interface từ cấu hình deployment;
2. `NetworkInterface.getByName(configuredName)`, kiểm tra khác null;
3. Kiểm tra `isUp()`, `supportsMulticast()` và có địa chỉ cùng IP family;
4. Nếu nhiều NIC: chọn đúng NIC thuộc segment muốn nhận, tránh “lấy NIC đầu tiên” trong ứng dụng thực;
5. Nếu không có NIC phù hợp hoặc OS ngăn join: fail rõ, không lén join NIC khác rồi nhận dữ liệu sai mạng.

### 3.1. Chương trình 1 — phân biệt multicast address, IPv4 và IPv6

Lưu `MulticastAddressKindsDemo.java`:

```java
import java.net.InetAddress;
import java.net.Inet4Address;
import java.net.Inet6Address;

public class MulticastAddressKindsDemo {
    public static void main(String[] args) throws Exception {
        InetAddress v4 = InetAddress.getByName("239.255.42.99");
        InetAddress host = InetAddress.getByName("192.0.2.11");
        InetAddress v6 = InetAddress.getByName("ff02::1");
        System.out.println("v4Group=" + v4.isMulticastAddress());
        System.out.println("v4Type=" + (v4 instanceof Inet4Address));
        System.out.println("unicastGroup=" + host.isMulticastAddress());
        System.out.println("v6Group=" + v6.isMulticastAddress());
        System.out.println("v6Type=" + (v6 instanceof Inet6Address));
    }
}
```

Biên dịch và chạy với JDK 17:

```bash
javac -encoding UTF-8 --release 17 MulticastAddressKindsDemo.java
java MulticastAddressKindsDemo
```

Stdout đã chạy:

```text
v4Group=true
v4Type=true
unicastGroup=false
v6Group=true
v6Type=true
```

`192.0.2.11` là địa chỉ unicast tài liệu TEST-NET, không phải group. `isMulticastAddress()` chỉ kiểm tra lớp địa chỉ, chưa xác nhận group có route hoặc interface hỗ trợ.

### 3.2. Chương trình 2 — tìm IPv4-capable multicast interface

Lưu `MulticastInterfaceSelectionDemo.java`:

```java
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.NetworkInterface;
import java.util.Enumeration;

public class MulticastInterfaceSelectionDemo {
    static boolean hasV4(NetworkInterface ni) {
        Enumeration<InetAddress> addresses = ni.getInetAddresses();
        while (addresses.hasMoreElements()) {
            if (addresses.nextElement() instanceof Inet4Address) return true;
        }
        return false;
    }
    static NetworkInterface choose() throws Exception {
        Enumeration<NetworkInterface> all = NetworkInterface.getNetworkInterfaces();
        if (all == null) return null;
        while (all.hasMoreElements()) {
            NetworkInterface ni = all.nextElement();
            if (ni.isUp() && ni.supportsMulticast() && hasV4(ni)) return ni;
        }
        return null;
    }
    public static void main(String[] args) throws Exception {
        NetworkInterface ni = choose();
        System.out.println("ipv4MulticastInterfaceFound=" + (ni != null));
        if (ni != null) {
            System.out.println("isUp=" + ni.isUp());
            System.out.println("supportsMulticast=" + ni.supportsMulticast());
            System.out.println("hasIPv4=" + hasV4(ni));
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 MulticastInterfaceSelectionDemo.java
java MulticastInterfaceSelectionDemo
```

Stdout **thực tế trên máy kiểm thử**:

```text
ipv4MulticastInterfaceFound=true
isUp=true
supportsMulticast=true
hasIPv4=true
```

**Kết quả phụ thuộc môi trường:** trên runtime không có NIC multicast hoạt động, dòng đầu có thể là `ipv4MulticastInterfaceFound=false` và không có ba dòng kế tiếp. Đây không phải lỗi biên dịch Java. `supportsMulticast()` là dấu hiệu capability của interface, **không bảo đảm firewall, router, cloud hay container cho phép nhận gói**.

Trong production, nên ưu tiên tên NIC từ cấu hình được kiểm tra, thay vì tùy ý chọn interface đầu tiên khi host có VPN, Ethernet, Wi-Fi và loopback cùng tồn tại.

## 4. Cấu hình DatagramChannel trước khi join

Một receiver IPv4 thông dụng:

```java
NetworkInterface ni = ...;  // NIC đã kiểm tra và phù hợp
InetAddress group = InetAddress.getByName("239.255.42.99");
int port = 5000;

try (DatagramChannel receiver =
        DatagramChannel.open(StandardProtocolFamily.INET)) {
    receiver.setOption(StandardSocketOptions.SO_REUSEADDR, true);
    receiver.bind(new InetSocketAddress(port)); // wildcard address
    MembershipKey key = receiver.join(group, ni);

    try {
        // receive bằng DatagramChannel; đóng khi hoàn tất.
    } finally {
        key.drop();
    }
}
```

Đây là **snippet**, không phải class chạy riêng. Cần imports từ `java.net` và `java.nio.channels`, cùng method xử lý IOException. `ni` phải được chọn theo deployment, không để `null`.

### 4.1. Vì sao phải chỉ định `INET` hoặc `INET6`?

`DatagramChannel.open(StandardProtocolFamily.INET)` tạo socket theo IPv4; `INET6` theo IPv6 khi được hỗ trợ. Javadoc khuyên dùng protocol family **cùng kiểu** địa chỉ group vì behavior khi mix IPv4/IPv6 phụ thuộc platform. Không dựa vào dual-stack implicit mà bỏ kiểm tra.

### 4.2. Vì sao bind wildcard?

`new InetSocketAddress(port)` dùng wildcard address. Theo MulticastChannel Javadoc, receiver nên bind wildcard; nếu bind tới địa chỉ host cụ thể thì việc nhận multicast **phụ thuộc implementation**. Đừng vô tình bind vào IP unicast cụ thể rồi cho rằng mọi group datagrams phải đến.

Port `0` là ephemeral port thường hợp cho **bài kiểm thử**, còn ứng dụng group receiver cần cấu hình **port đã thống nhất với sender**. Join group tự nó **không chọn port cho sender**.

### 4.3. `SO_REUSEADDR` phải đặt trước `bind`

`setOption(StandardSocketOptions.SO_REUSEADDR,true)` trước bind cho phép nhiều thành viên/processes cùng bind địa chỉ/cổng theo semantics OS. Javadoc nói nên bật trước bind để nhiều thành viên có thể dùng cùng địa chỉ. Từng OS vẫn có quyền, quy tắc reuse và khả năng multicast delivery riêng; đừng xem option này là cam kết tất cả processes đều nhận cùng một datagram.

### 4.4. `join` không thay thế `bind` hoặc `receive`

`join(group,ni)` đăng ký membership ở tầng mạng. Nó **không tự nhận gói vào ByteBuffer** và không trả thread listener. `DatagramChannel.receive(ByteBuffer)` mới đọc datagrams từ socket. Không có cơ chế “join thành công = đã nhận packet”.

## 5. MembershipKey: kết quả quan trọng của join

Khi join thành công:

```java
MembershipKey key = channel.join(group, ni);

boolean active = key.isValid();
InetAddress joinedGroup = key.group();
NetworkInterface joinedInterface = key.networkInterface();
InetAddress chosenSource = key.sourceAddress();
MulticastChannel owner = key.channel();
```

Đây là snippet với channel/group/ni đã có. `MembershipKey` chứa:
- `isValid()`: membership còn hợp lệ không.
- `group()`: địa chỉ group.
- `networkInterface()`: NIC được chỉ định.
- `channel()`: channel sở hữu membership.
- `sourceAddress()`: `null` cho any-source; địa chỉ nguồn cho source-specific.
- `drop()`: rời membership, key mất hiệu lực.
- `block(source)` / `unblock(source)`: lọc/khôi phục nguồn trên any-source membership khi OS hỗ trợ.

Key **không phải `AutoCloseable`**, không dùng `try (MembershipKey key = ...)`. Đặt `key.drop()` trong finally; đồng thời đóng channel bằng try-with-resources sẽ tự drop tất cả memberships còn lại của channel.

### 5.1. Một membership không nhất thiết biến mất cùng datagram đang buffered

Javadoc `MembershipKey.drop()` nêu rằng sau khi drop, vẫn có thể nhận những datagrams **đã nằm trong socket receive buffer**. Vì vậy đừng xem `drop()` là cách xóa sạch dữ liệu mạng đang chờ hoặc đảm bảo không còn packet cũ. Nếu cần trạng thái giao thức mới, xử lý buffer, epoch/session IDs và khả năng packet trễ.

### 5.2. Join lặp cùng group/interface

Nếu channel đã tham gia group trên interface với **any-source membership**, gọi lại `join(group,ni)` sẽ trả **membership key đang có** thay vì mặc nhiên tạo duplicate membership. Sau `drop()`, key cũ vĩnh viễn invalid; join lại có thể tạo **key mới**.

### 5.3. Chương trình 3 — join/drop/rejoin/close

Lưu `MulticastJoinDropDemo.java`:

```java
import java.net.*;
import java.nio.channels.*;
import java.util.Enumeration;
import java.io.IOException;

public class MulticastJoinDropDemo {
    static NetworkInterface choose() throws Exception {
        Enumeration<NetworkInterface> interfaces = NetworkInterface.getNetworkInterfaces();
        if (interfaces == null) return null;
        while (interfaces.hasMoreElements()) {
            NetworkInterface nic = interfaces.nextElement();
            if (!nic.isUp() || !nic.supportsMulticast()) continue;
            Enumeration<InetAddress> addresses = nic.getInetAddresses();
            while (addresses.hasMoreElements()) {
                if (addresses.nextElement() instanceof Inet4Address) return nic;
            }
        }
        return null;
    }
    public static void main(String[] args) throws Exception {
        NetworkInterface nic = choose();
        if (nic == null) {
            System.out.println("membership=SKIPPED_NO_MULTICAST_INTERFACE");
            return;
        }
        InetAddress group = InetAddress.getByName("239.255.42.99");
        try (DatagramChannel channel = DatagramChannel.open(StandardProtocolFamily.INET)) {
            channel.setOption(StandardSocketOptions.SO_REUSEADDR, true);
            channel.bind(new InetSocketAddress(0)); // wildcard IPv4, ephemeral port
            try {
                MembershipKey key = channel.join(group, nic);
                System.out.println("membership=JOINED");
                System.out.println("validAfterJoin=" + key.isValid());
                System.out.println("anySource=" + (key.sourceAddress() == null));
                System.out.println("groupMatches=" + key.group().equals(group));
                System.out.println("interfaceMatches=" + key.networkInterface().equals(nic));
                System.out.println("channelMatches=" + (key.channel() == channel));
                MembershipKey repeat = channel.join(group, nic);
                System.out.println("sameKeyForRepeat=" + (repeat == key));
                key.drop();
                System.out.println("validAfterDrop=" + key.isValid());
                key.drop(); // dropping an invalid membership is a no-op
                MembershipKey rejoined = channel.join(group, nic);
                System.out.println("validAfterRejoin=" + rejoined.isValid());
                channel.close();
                System.out.println("validAfterClose=" + rejoined.isValid());
            } catch (IOException | UnsupportedOperationException | SecurityException e) {
                System.out.println("membership=SKIPPED_PLATFORM_OR_NETWORK");
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 MulticastJoinDropDemo.java
java MulticastJoinDropDemo
```

Stdout **đã chạy trên JDK 17 có NIC hỗ trợ multicast**:

```text
membership=JOINED
validAfterJoin=true
anySource=true
groupMatches=true
interfaceMatches=true
channelMatches=true
sameKeyForRepeat=true
validAfterDrop=false
validAfterRejoin=true
validAfterClose=false
```

**Giải thích lần lượt:**
1. `join` thành công và key đang valid.
2. `sourceAddress()==null` cho biết **any-source membership**.
3. `group()`, `networkInterface()` và `channel()` liên hệ key với đúng group/NIC/channel.
4. Join lặp trả cùng key khi membership vẫn active.
5. `drop` làm key invalid; gọi `drop` thêm lần nữa không làm hỏng state.
6. Join lại được key valid mới.
7. `channel.close` tự làm membership cuối invalid.

**Nếu môi trường không có NIC multicast**, chương trình chỉ in `membership=SKIPPED_NO_MULTICAST_INTERFACE`. Nếu OS/firewall/container không cho phép join, nhánh catch in `membership=SKIPPED_PLATFORM_OR_NETWORK`. **Không gọi SKIPPED là PASS cho hành vi join**; cần một môi trường tích hợp hỗ trợ multicast để test đường thành công.

## 6. Khi đóng DatagramChannel thì MembershipKey thế nào?

`MulticastChannel.close()` đóng socket và tự drop memberships đang hoạt động. Theo hợp đồng Java, khi close trả về thì mọi MembershipKeys gắn với channel trở nên invalid. Điều này khác với việc chỉ `key.drop()`:
- `key.drop()` rời **một membership**; channel vẫn có thể mở để gửi/nhận khác.
- `channel.close()` dừng **toàn bộ channel**; mọi membership keys của nó không còn valid.

### 6.1. Chương trình 4 — close tự invalid key

Lưu `MulticastKeyCloseDemo.java`:

```java
import java.net.*;
import java.nio.channels.*;
import java.util.Enumeration;
import java.io.IOException;

public class MulticastKeyCloseDemo {
    static NetworkInterface choose() throws Exception {
        Enumeration<NetworkInterface> all = NetworkInterface.getNetworkInterfaces();
        if (all == null) return null;
        while (all.hasMoreElements()) {
            NetworkInterface ni = all.nextElement();
            if (!ni.isUp() || !ni.supportsMulticast()) continue;
            Enumeration<InetAddress> addrs = ni.getInetAddresses();
            while (addrs.hasMoreElements())
                if (addrs.nextElement() instanceof Inet4Address) return ni;
        }
        return null;
    }
    public static void main(String[] args) throws Exception {
        NetworkInterface nic = choose();
        if (nic == null) {
            System.out.println("closeKey=SKIPPED_NO_INTERFACE");
            return;
        }
        try (DatagramChannel dc = DatagramChannel.open(StandardProtocolFamily.INET)) {
            dc.setOption(StandardSocketOptions.SO_REUSEADDR, true);
            dc.bind(new InetSocketAddress(0));
            try {
                MembershipKey key =
                        dc.join(InetAddress.getByName("239.255.42.101"), nic);
                System.out.println("keyValidBeforeClose=" + key.isValid());
                dc.close();
                System.out.println("keyValidAfterClose=" + key.isValid());
            } catch (IOException | UnsupportedOperationException | SecurityException e) {
                System.out.println("closeKey=SKIPPED_PLATFORM_OR_NETWORK");
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 MulticastKeyCloseDemo.java
java MulticastKeyCloseDemo
```

Stdout đã kiểm chứng:

```text
keyValidBeforeClose=true
keyValidAfterClose=false
```

Khi channel được đóng, key mất hiệu lực ngay cả khi không gọi `key.drop()` tường minh. Với một channel được chia sẻ nhiều groups, đóng channel sẽ tác động **mọi membership trên nó**, nên phải xác định resource ownership trước khi close.

## 7. Validate group và source trước join

Javadoc `MulticastChannel` phân biệt:
- `IllegalArgumentException` nếu `group` không phải multicast hoặc sai address family so với channel.
- Với source-specific join, source phải là **unicast** và cùng address type với group.
- `IllegalStateException` nếu trộn any-source và source-specific memberships trên cùng group/interface trong một channel.
- `UnsupportedOperationException` khi platform không hỗ trợ IP multicast/source filtering.
- `ClosedChannelException` nếu join trên channel đã đóng.
- `IOException` khi native join thất bại.
- `SecurityException` có thể xảy ra dưới cơ chế kiểm soát truy cập đặc thù của runtime.

### 7.1. Chương trình 5 — từ chối group unicast và source multicast

Lưu `MulticastInvalidGroupDemo.java`:

```java
import java.net.*;
import java.nio.channels.*;
import java.util.Enumeration;

public class MulticastInvalidGroupDemo {
    public static void main(String[] args) throws Exception {
        Enumeration<NetworkInterface> all = NetworkInterface.getNetworkInterfaces();
        if (all == null || !all.hasMoreElements()) {
            System.out.println("interface=UNAVAILABLE");
            return;
        }
        NetworkInterface nic = all.nextElement();
        try (DatagramChannel channel = DatagramChannel.open(StandardProtocolFamily.INET)) {
            try {
                channel.join(InetAddress.getByName("192.0.2.11"), nic);
                throw new AssertionError("unicast should not be accepted");
            } catch (IllegalArgumentException expected) {
                System.out.println("unicastJoin=IllegalArgumentException");
            }
            try {
                channel.join(InetAddress.getByName("239.255.42.99"), nic,
                        InetAddress.getByName("239.255.42.100"));
                throw new AssertionError("source must be unicast");
            } catch (IllegalArgumentException expected) {
                System.out.println("multicastSource=IllegalArgumentException");
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 MulticastInvalidGroupDemo.java
java MulticastInvalidGroupDemo
```

Stdout đã kiểm chứng:

```text
unicastJoin=IllegalArgumentException
multicastSource=IllegalArgumentException
```

Chương trình cố ý dùng một địa chỉ TEST-NET unicast làm group, rồi thử dùng chính một địa chỉ multicast làm **source filter**; cả hai đều không hợp lệ. Đây là **kiểm tra tham số API**, không phải thử gửi traffic trên mạng. Nếu runtime hoàn toàn không có NetworkInterface để kiểm tra, chương trình báo `interface=UNAVAILABLE` thay vì đoán một NIC.

## 8. Source-Specific Multicast: chỉ đăng ký nguồn nhất định

Với `join(group,ni,source)`, membership nhận datagrams từ địa chỉ `source` cụ thể gửi tới `group` (nếu OS/underlying network hỗ trợ). Đây là cơ chế **lọc địa chỉ nguồn**, không phải xác thực người gửi và không bảo đảm mạng chống spoofing.

Điều kiện:
- `group.isMulticastAddress()==true`.
- `source` là **unicast**, không phải group/broadcast;
- source và group cùng address family (IPv4/IPv4 hoặc IPv6/IPv6);
- channel protocol family phù hợp;
- interface hỗ trợ multicast;
- nền tảng hỗ trợ source filtering cho join variant;
- không đang có any-source membership cho cùng group/interface trên channel.

Một channel có thể có nhiều source-specific memberships cho các source khác nhau cùng group/interface. Javadoc gọi memberships này là **cumulative**, và mỗi returned key quản lý nguồn đã đăng ký tương ứng.

### 8.1. Chương trình 6 — tạo source-specific membership

Lưu `MulticastSourceFilterDemo.java`:

```java
import java.net.*;
import java.nio.channels.*;
import java.util.Enumeration;
import java.io.IOException;

public class MulticastSourceFilterDemo {
    static NetworkInterface choose() throws Exception {
        Enumeration<NetworkInterface> all = NetworkInterface.getNetworkInterfaces();
        if (all == null) return null;
        while (all.hasMoreElements()) {
            NetworkInterface ni = all.nextElement();
            if (!ni.isUp() || !ni.supportsMulticast()) continue;
            Enumeration<InetAddress> addrs = ni.getInetAddresses();
            while (addrs.hasMoreElements())
                if (addrs.nextElement() instanceof Inet4Address) return ni;
        }
        return null;
    }
    public static void main(String[] args) throws Exception {
        NetworkInterface nic = choose();
        if (nic == null) {
            System.out.println("sourceFilter=SKIPPED_NO_INTERFACE");
            return;
        }
        InetAddress group = InetAddress.getByName("239.255.42.102");
        InetAddress source = InetAddress.getByName("192.0.2.1"); // TEST-NET unicast
        try (DatagramChannel channel = DatagramChannel.open(StandardProtocolFamily.INET)) {
            channel.setOption(StandardSocketOptions.SO_REUSEADDR, true);
            channel.bind(new InetSocketAddress(0));
            try {
                MembershipKey key = channel.join(group, nic, source);
                System.out.println("sourceFilter=JOINED");
                System.out.println("sourceMatches=" + source.equals(key.sourceAddress()));
                System.out.println("valid=" + key.isValid());
                key.drop();
                System.out.println("validAfterDrop=" + key.isValid());
            } catch (IOException | UnsupportedOperationException | SecurityException e) {
                System.out.println("sourceFilter=SKIPPED_PLATFORM_OR_NETWORK");
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 MulticastSourceFilterDemo.java
java MulticastSourceFilterDemo
```

Stdout đã chạy trên môi trường kiểm thử:

```text
sourceFilter=JOINED
sourceMatches=true
valid=true
validAfterDrop=false
```

**Giới hạn của bài test:** `192.0.2.1` là địa chỉ TEST-NET chỉ dùng làm giá trị bộ lọc. Test này **không** tạo sender có địa chỉ đó và **không** chứng minh datagrams từ địa chỉ đó được phân phối thật. Nó kiểm tra API join/token state. Ở máy thiếu source filtering, in `sourceFilter=SKIPPED_PLATFORM_OR_NETWORK`. Không đưa một source thật vào production mà chưa xác định topology và trust.

## 9. `block(source)` / `unblock(source)` trên any-source membership

Nếu ứng dụng đã join any-source bằng `join(group,ni)` và OS hỗ trợ **source filtering**, key có thể:
- `key.block(source)`: yêu cầu không nhận datagrams từ source đó.
- `key.unblock(source)`: gỡ filter đã block, cho phép nhận lại.
- `key.isValid()` vẫn true khi chỉ block/unblock; chỉ `drop/close` làm invalid.

`block` và `unblock` **không dành cho source-specific key**, vì với source-specific membership nguồn đã cố định. `block` trên invalid key hoặc source-specific key có thể ném `IllegalStateException`. `unblock` khi nguồn chưa bị block cũng ném IllegalStateException theo contract.

Quan trọng: Javadoc cho phép vẫn nhận datagrams đã **buffered trước khi block**. Vậy block không phải một biện pháp security zero-leak, và lọc theo IP không thay authentication/integrity verification.

### 9.1. Chương trình 7 — block rồi unblock

Lưu `MulticastBlockUnblockDemo.java`:

```java
import java.net.*;
import java.nio.channels.*;
import java.util.Enumeration;
import java.io.IOException;

public class MulticastBlockUnblockDemo {
    static NetworkInterface choose() throws Exception {
        Enumeration<NetworkInterface> all = NetworkInterface.getNetworkInterfaces();
        if (all == null) return null;
        while (all.hasMoreElements()) {
            NetworkInterface ni = all.nextElement();
            if (!ni.isUp() || !ni.supportsMulticast()) continue;
            Enumeration<InetAddress> a = ni.getInetAddresses();
            while (a.hasMoreElements())
                if (a.nextElement() instanceof Inet4Address) return ni;
        }
        return null;
    }
    public static void main(String[] args) throws Exception {
        NetworkInterface nic = choose();
        if (nic == null) {
            System.out.println("block=SKIPPED_NO_INTERFACE");
            return;
        }
        InetAddress group = InetAddress.getByName("239.255.42.104");
        InetAddress source = InetAddress.getByName("192.0.2.1");
        try (DatagramChannel channel = DatagramChannel.open(StandardProtocolFamily.INET)) {
            channel.setOption(StandardSocketOptions.SO_REUSEADDR, true);
            channel.bind(new InetSocketAddress(0));
            try {
                MembershipKey key = channel.join(group, nic);
                try {
                    MembershipKey blocked = key.block(source);
                    System.out.println("blockSupported=true");
                    System.out.println("blockSameKey=" + (key == blocked));
                    MembershipKey restored = key.unblock(source);
                    System.out.println("unblockSameKey=" + (key == restored));
                } catch (UnsupportedOperationException capabilityMissing) {
                    System.out.println("blockSupported=false");
                } finally {
                    key.drop();
                }
            } catch (IOException | UnsupportedOperationException | SecurityException e) {
                System.out.println("block=SKIPPED_PLATFORM_OR_NETWORK");
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 MulticastBlockUnblockDemo.java
java MulticastBlockUnblockDemo
```

Stdout đã kiểm chứng:

```text
blockSupported=true
blockSameKey=true
unblockSameKey=true
```

`block`/`unblock` trả chính membership key. Nếu OS không hỗ trợ source filtering cho key ASM, nhánh tương ứng có thể in `blockSupported=false`. Nếu join thất bại, in `block=SKIPPED_PLATFORM_OR_NETWORK`. Đừng coi việc **có method** là chứng cứ mọi interface thật đều hỗ trợ. Các lệnh trên không kiểm thử data plane delivery từ IP đã block.

## 10. Trộn Any-Source và Source-Specific trên cùng membership

Chế độ any-source và source-specific **không thể cùng tồn tại** trên cùng channel/group/interface theo hợp đồng. Muốn chuyển chế độ:
1. Lưu key của membership cũ;
2. `key.drop()` để rời group/filter;
3. Kiểm tra `!key.isValid()`;
4. `join` lại bằng overload phù hợp;
5. Đảm bảo không có các nguồn khác vẫn còn membership không tương thích.

### 10.1. Chương trình 8 — IllegalStateException do conflict

Lưu `MulticastConflictingMembershipDemo.java`:

```java
import java.net.*;
import java.nio.channels.*;
import java.util.Enumeration;
import java.io.IOException;

public class MulticastConflictingMembershipDemo {
    static NetworkInterface choose() throws Exception {
        Enumeration<NetworkInterface> all = NetworkInterface.getNetworkInterfaces();
        if (all == null) return null;
        while (all.hasMoreElements()) {
            NetworkInterface ni = all.nextElement();
            if (!ni.isUp() || !ni.supportsMulticast()) continue;
            Enumeration<InetAddress> a = ni.getInetAddresses();
            while (a.hasMoreElements())
                if (a.nextElement() instanceof Inet4Address) return ni;
        }
        return null;
    }
    public static void main(String[] args) throws Exception {
        NetworkInterface nic = choose();
        if (nic == null) {
            System.out.println("conflict=SKIPPED_NO_INTERFACE");
            return;
        }
        InetAddress group = InetAddress.getByName("239.255.42.105");
        InetAddress source = InetAddress.getByName("192.0.2.1");
        try (DatagramChannel channel = DatagramChannel.open(StandardProtocolFamily.INET)) {
            channel.setOption(StandardSocketOptions.SO_REUSEADDR, true);
            channel.bind(new InetSocketAddress(0));
            try {
                MembershipKey allSources = channel.join(group, nic);
                try {
                    channel.join(group, nic, source);
                    throw new AssertionError("ASM and SSM should not mix for same group/NI");
                } catch (IllegalStateException expected) {
                    System.out.println("mixedMembership=IllegalStateException");
                } finally {
                    allSources.drop();
                }
            } catch (IOException | UnsupportedOperationException | SecurityException e) {
                System.out.println("conflict=SKIPPED_PLATFORM_OR_NETWORK");
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 MulticastConflictingMembershipDemo.java
java MulticastConflictingMembershipDemo
```

Stdout đã kiểm chứng:

```text
mixedMembership=IllegalStateException
```

Kết quả là **lỗi trạng thái membership có chủ đích**, không phải lỗi IP packet hoặc thiếu dữ liệu trong socket. Nếu một chương trình cần lọc theo source trên một group đã join any-source, đừng tiếp tục join nguồn khác ở chế độ SSM mà chưa drop membership ASM.

## 11. Gửi/nhận UDP multicast không đồng nhất với việc join

Một receiver cần:
1. Mở `DatagramChannel` đúng address family;
2. Set `SO_REUSEADDR` trước `bind` nếu có nhiều listeners/đúng policy;
3. Bind **wildcard** tới cổng dự kiến nhận;
4. Join group với đúng `NetworkInterface`, giữ `MembershipKey`;
5. Sử dụng `receive(ByteBuffer)` (blocking hoặc nonblocking) để lấy datagram và nguồn gửi;
6. Xử lý payload, giới hạn kích thước, validate sender/protocol;
7. Drop membership/close channel khi dừng.

Sender cần:
1. Mở DatagramChannel đúng protocol family;
2. Chọn **outgoing** interface qua `IP_MULTICAST_IF`;
3. Cân nhắc `IP_MULTICAST_TTL` và `IP_MULTICAST_LOOP`;
4. `send(buffer, new InetSocketAddress(group, port))`;
5. Kiểm tra bytes đã gửi/trạng thái lỗi;
6. Không cần join group chỉ để gửi.

### 11.1. Ba socket options dễ nhầm

| Option | Kiểu | Vai trò | Lưu ý |
| --- | --- | --- | --- |
| `SO_REUSEADDR` | Boolean | Cho nhiều sockets bind cùng địa chỉ/port theo OS policy | Bật **trước bind** |
| `IP_MULTICAST_IF` | NetworkInterface | Interface **gửi multicast** | Không tự thay tham số `join(group,ni)` của receiver |
| `IP_MULTICAST_TTL` | Integer 0..255 | IPv4 TTL / IPv6 hop-limit theo provider | `0` thường ngăn gửi ra mạng nhưng có thể nhận local; **không phải security boundary** |
| `IP_MULTICAST_LOOP` | Boolean | Cho phép loopback multicast trên hệ thống hỗ trợ | Semantics chi tiết phụ thuộc OS |

Đừng nhầm `IP_MULTICAST_IF` với “join trên mọi NIC”; nó chủ yếu cấu hình đường đi của **datagrams gửi ra**. Trong code receiver, đúng `NetworkInterface` phải được truyền vào `join`.

### 11.2. Gửi một datagram không bảo đảm receiver nhận

`DatagramChannel.send` có thể trả số bytes được gửi tới hạ tầng local, nhưng **không xác nhận một hay nhiều receivers đã nhận/đọc**. UDP không có ACK/ordering/retransmission mặc định. Mạng multicast thực tế phụ thuộc switch multicast snooping, router/IGMP hoặc IPv6 MLD, firewall, routing, container capabilities và NIC. Thiết kế protocol cần sequence numbers, replay policy, idempotency hoặc ACK ở tầng ứng dụng khi cần độ tin cậy.

### 11.3. Chương trình 9 — join + gửi và nhận trong loopback

Đây là bài lab cố gắng giới hạn phạm vi **chỉ trong máy cục bộ** bằng cách chọn IPv4 loopback interface `127.0.0.1` và `IP_MULTICAST_TTL=0`. Chương trình có thời hạn chờ ngắn, nhận nonblocking và có nhánh SKIPPED khi OS không cho multicast loopback.

Lưu `MulticastLoopbackDemo.java`:

```java
import java.net.*;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.nio.channels.*;
import java.util.concurrent.TimeUnit;
import java.io.IOException;

public class MulticastLoopbackDemo {
    public static void main(String[] args) throws Exception {
        NetworkInterface loopback =
                NetworkInterface.getByInetAddress(InetAddress.getByName("127.0.0.1"));
        if (loopback == null || !loopback.isUp() || !loopback.supportsMulticast()) {
            System.out.println("loopbackTest=SKIPPED_INTERFACE_UNSUPPORTED");
            return;
        }
        InetAddress group = InetAddress.getByName("239.255.42.103");
        try (DatagramChannel receiver = DatagramChannel.open(StandardProtocolFamily.INET);
             DatagramChannel sender = DatagramChannel.open(StandardProtocolFamily.INET)) {
            receiver.setOption(StandardSocketOptions.SO_REUSEADDR, true);
            receiver.bind(new InetSocketAddress(0));
            sender.bind(new InetSocketAddress(0));
            sender.setOption(StandardSocketOptions.IP_MULTICAST_IF, loopback);
            sender.setOption(StandardSocketOptions.IP_MULTICAST_LOOP, true);
            sender.setOption(StandardSocketOptions.IP_MULTICAST_TTL, 0);
            try {
                MembershipKey key = receiver.join(group, loopback);
                receiver.configureBlocking(false);
                int port = ((InetSocketAddress) receiver.getLocalAddress()).getPort();
                ByteBuffer send = ByteBuffer.wrap("ping".getBytes(StandardCharsets.UTF_8));
                int sent = sender.send(send, new InetSocketAddress(group, port));
                boolean received = false;
                long deadline = System.nanoTime() + TimeUnit.MILLISECONDS.toNanos(1500);
                ByteBuffer dst = ByteBuffer.allocate(64);
                while (System.nanoTime() < deadline) {
                    dst.clear();
                    SocketAddress from = receiver.receive(dst);
                    if (from != null) {
                        dst.flip();
                        received = "ping".equals(StandardCharsets.UTF_8.decode(dst).toString());
                        if (received) break;
                    }
                    Thread.sleep(10);
                }
                System.out.println("join=SUCCESS");
                System.out.println("sentBytes=" + sent);
                System.out.println("delivery=" + (received ? "RECEIVED" : "NOT_OBSERVED"));
                key.drop();
            } catch (IOException | UnsupportedOperationException | SecurityException e) {
                System.out.println("loopbackTest=SKIPPED_PLATFORM_OR_NETWORK");
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 MulticastLoopbackDemo.java
java MulticastLoopbackDemo
```

Stdout **thực tế tại môi trường test**:

```text
join=SUCCESS
sentBytes=4
delivery=RECEIVED
```

**Tính phụ thuộc môi trường:** nếu loopback interface không hỗ trợ multicast, máy có thể in `loopbackTest=SKIPPED_INTERFACE_UNSUPPORTED`; nếu thao tác socket bị chặn, in `loopbackTest=SKIPPED_PLATFORM_OR_NETWORK`; nếu join/send thành công nhưng gói không đến trong thời hạn test, in `delivery=NOT_OBSERVED`. Không suy rằng một lần thử loopback thành công bảo đảm multicast hoạt động qua các hosts/subnets trên mạng production.

**Vì sao `IP_MULTICAST_TTL=0`?** Đây là lab chỉ muốn gửi local; TTL=0 không phát ra network theo ý nghĩa IP multicast thông dụng, nhưng hành vi loopback có thể khác giữa OS. Nó **không phải ranh giới bảo mật**. Không dùng lab này để chứng minh bảo mật mạng hoặc đo packet delivery SLA. Trong mạng thật, chọn TTL/hop limit theo topology và network policy.

### 11.4. Blocking và nonblocking receive

`DatagramChannel` mặc định có thể block khi `receive` trong blocking mode. Trong demo, `receiver.configureBlocking(false)` cho phép `receive` trả null nếu chưa có datagram, và vòng lặp dùng `System.nanoTime` để có deadline. Ứng dụng thực nên dùng `Selector`/event loop hoặc mô hình quản lý I/O có deadline thay vì polling `Thread.sleep(10)` liên tục. Đừng viết receive blocking vô hạn nếu cần shutdown sạch.

## 12. MulticastChannel và MembershipKey trong code production

Một receiver thực tế có thể gồm các bước sau:

```text
Config group + port + interface name
     |
     v
Validate group address/family + interface isUp/supportsMulticast
     |
     v
DatagramChannel.open(INET/INET6)
     |
     v
SO_REUSEADDR=true (trước bind) -> bind(wildcard, port)
     |
     v
join(group, NetworkInterface) -> MembershipKey
     |
     v
receive loop / Selector + protocol validation
     |
     v
stop signal -> key.drop() -> channel.close()
```

### 12.1. Vòng đời nên rõ owner

- Component **tạo** channel là owner mặc định của channel và cleanup.
- `MembershipKey` nên được giữ trong một field/context sống đủ lâu, không tạo rồi bỏ tham chiếu nếu cần chủ động `drop`.
- Drop membership không tự đóng DatagramChannel; có thể channel vẫn join các nhóm khác.
- Close DatagramChannel làm **tất cả** keys gắn với nó invalid.
- Khi reconfigure group/interface, drop key cũ trước khi join lại theo chế độ khác; không tái sử dụng key invalid.
- Không đóng channel được chia sẻ với module khác khi chỉ muốn bỏ một group.
- Exception từ `join` cần được phân loại và không coi là thành công.
- Khi khởi tạo dở: try-with-resources đảm bảo socket được đóng, tránh rò rỉ port/file descriptor.

### 12.2. Không “join” ngay sau mỗi lần nhận packet

Group membership thường sống cùng listener/service. Không cần gọi `join` lại cho từng datagram, và join lặp có thể cùng key. Application phải duy trì membership cho đến khi cấu hình thay đổi hoặc receiver dừng.

### 12.3. Nhiều groups trên một channel

Có thể join nhóm A và B trên cùng DatagramChannel, nhưng các datagrams vẫn tới **cùng receive socket/port**; application muốn biết gói thuộc logical group nào cần dựa trên metadata/transport design và protocol framing, không mặc định `receive` trả group destination như một field trong mọi implementation. Tham số `receive` trả **địa chỉ sender** (`SocketAddress`), không phải tự trả MembershipKey tương ứng.

### 12.4. Multi-homed hosts và IPv6

Một server có Ethernet, Wi-Fi, VPN, Docker bridge và loopback có thể có nhiều interfaces báo multicast-capable. Chọn interface theo mạng nghiệp vụ, không theo thứ tự enumeration. Với IPv6 multicast scope-aware, cần kiểm tra interface zone và address scope; không hard-code `ff02::1` rồi giả định mọi NIC đều cùng link.

## 13. Những điều MulticastChannel KHÔNG hứa

1. **Không hứa reliable delivery:** UDP multicast có packet loss, duplicate, reorder, congestion.
2. **Không hứa routing:** IGMP/MLD/multicast routing phụ thuộc hạ tầng; Internet công cộng thường không forward multicast tùy ý.
3. **Không hứa bảo mật:** IP multicast không mã hóa, không tự authenticate, membership filter theo IP không phải chứng thực.
4. **Không hứa cùng group là cùng port:** Port bind phải khớp nơi sender gửi.
5. **Không hứa same-port reuse ở mọi OS:** `SO_REUSEADDR` có khác biệt platform.
6. **Không hứa bind vào unicast IP vẫn nhận group:** nên bind wildcard.
7. **Không hứa cross-family join:** dùng INET cho IPv4, INET6 cho IPv6.
8. **Không hứa IP_MULTICAST_LOOP/TTL giống hệt trên mọi OS:** kiểm thử tại target environment.
9. **Không hứa drop xóa hết receive buffer:** datagrams cũ có thể còn.
10. **Không hứa block/unblock luôn hỗ trợ:** source filtering optional.
11. **Không hứa join thành công là sender có traffic:** phải có sender hợp lệ, route và event loop.
12. **Không hứa datagram lớn an toàn:** MTU/fragmentation, truncated buffer, payload quotas.
13. **Không hứa NetworkInterface.supportsMulticast là bằng chứng firewall cho phép:** chỉ là capability signal.
14. **Không hứa người gửi không bị giả mạo IP:** bảo vệ integrity/replay ở tầng ứng dụng.
15. **Không hứa close rời group ngay trên mọi router:** OS/IGMP/MLD có thời gian phản ánh trạng thái mạng riêng.

### 13.1. Đừng tin địa chỉ nguồn để xác thực

`MembershipKey.sourceAddress` và `block/unblock` lọc theo IP source, nhưng chúng không chứng minh người gửi là đối tác hợp lệ. Một mạng multicast nhạy cảm cần segmentation, ACL phù hợp, kiểm tra message format, authentication/signature/MAC khi áp dụng, replay detection, rate limits và quản lý secrets ngoài payload logs.

### 13.2. Đừng coi TTL như access control

`IP_MULTICAST_TTL` giới hạn scope truyền đi theo hops, không bảo vệ nội dung bằng cryptography. Một máy cùng segment vẫn có thể nghe multicast nếu môi trường cho phép. Muốn bảo mật phải thiết kế ở network/application layer.

### 13.3. Không gửi packet tùy ý ra production chỉ để “test join”

Thử ở loopback hoặc test VLAN riêng trước. Dùng group/port đã thống nhất, không sử dụng dải multicast mang ý nghĩa control-plane hay route protocol của hệ thống. Fixture ở đây dùng `239.255.42.x` cho lab và TTL=0, tránh yêu cầu router hoặc host khác.

## 14. Xử lý lỗi thường gặp

| Exception / dấu hiệu | Lý do thường gặp | Cách xử lý |
| --- | --- | --- |
| `IllegalArgumentException` | group không multicast; source không unicast; sai address family | Validate tham số trước join |
| `IllegalStateException` | Trộn ASM/SSM cho cùng group/interface; block invalid key | Drop đúng membership hoặc đổi mode |
| `UnsupportedOperationException` | OS/provider thiếu multicast/source filtering | Phát hiện capability, có fallback hoặc fail |
| `ClosedChannelException` | Join trên DatagramChannel đã đóng | Tạo channel mới theo ownership |
| `IOException` | Native join/bind hoặc network lỗi | Kiểm tra NIC, quyền, firewall, OS logs |
| `SecurityException` | Chính sách bảo mật runtime/môi trường chặn network | Không tự bypass |
| `BindException` | Port đã dùng hoặc reuse không được phép | Chọn port/reuse policy phù hợp |
| `NullPointerException` | Truyền group/interface null khi API yêu cầu | Validate config |
| `NetworkInterface` null | Tên interface không tồn tại | Báo lỗi cấu hình, không chọn ngẫu nhiên |
| `supportsMulticast()==false` | NIC không có capability multicast | Dùng NIC phù hợp hoặc báo unsupported |
| `receive` null ở nonblocking mode | Chưa có packet vào socket | Dùng Selector/deadline, không coi null là lỗi |
| `receive` block mãi | Chưa có packet và blocking mode | Nonblocking/event loop/shutdown control |
| `key.isValid()==false` | Đã drop hoặc channel closed | Không reuse key, join mới nếu cần |
| Packet không đến | Sai group/port/NIC, TTL/loop, firewall/router hoặc loss | Diagnostics theo các tầng |
| Packet đến nhưng dữ liệu thiếu | ByteBuffer quá nhỏ/truncation hoặc fragmentation loss | Bound size, protocol framing, kiểm tra packet lengths |

### 14.1. Chẩn đoán theo thứ tự

Khi receiver “đã join nhưng không nhận”:
1. In group address, protocol family, port, **interface name**, socket bind address.
2. `InetAddress.isMulticastAddress()` và NIC `isUp()/supportsMulticast()`.
3. Receiver bind wildcard và `SO_REUSEADDR` trước bind?
4. Sender gửi đúng group **và đúng UDP port**?
5. `IP_MULTICAST_IF` của sender trỏ đúng interface/network?
6. `IP_MULTICAST_TTL`, scope và loopback hợp lý?
7. OS/container/firewall/router/IGMP/MLD có cho phép packet không?
8. Receiver đang blocking, nonblocking, hay mất gói vì buffer nhỏ?
9. `MembershipKey.isValid()` còn true?
10. Nếu SSM, source address có trùng IP của datagram sender thật không?
11. App có block nguồn bằng `MembershipKey.block` hay filter ở tầng application?
12. Nếu mọi thông số đúng, thử trên test VLAN hoặc loopback được kiểm soát và ghi nhận environment-specific limitations.

## 15. Checklist code review

1. Dùng `DatagramChannel` triển khai `MulticastChannel` đúng API?
2. Có chọn `StandardProtocolFamily.INET` hay `INET6` phù hợp?
3. Có validate `group.isMulticastAddress()`?
4. Có cấu hình group/port/NIC từ deployment thay vì hard-code production?
5. NIC có `isUp()`, `supportsMulticast()` và family thích hợp?
6. Có tránh lấy NIC đầu tiên trên multi-homed server nếu không đúng network?
7. Có bật `SO_REUSEADDR` trước bind khi nhiều receiver share port?
8. Receiver có bind wildcard thay vì một unicast IP cụ thể?
9. Port receiver có trùng nơi sender gửi?
10. Có gọi `channel.join(group, ni)` ở đúng interface?
11. Có lưu `MembershipKey` và kiểm tra `isValid()`?
12. Khi không còn cần group, có `drop()` hoặc close đúng owner?
13. Có hiểu `drop` không nhất thiết xóa socket receive buffer?
14. Có hiểu `close` invalid tất cả keys của channel?
15. Có tránh join lại sau mỗi packet?
16. Có tránh trộn ASM và SSM cho cùng group/interface?
17. Source-specific address có unicast và cùng address family?
18. Có xử lý `UnsupportedOperationException` nếu source filtering thiếu?
19. Có hiểu block/unblock không phải security barrier?
20. Sender có dùng `IP_MULTICAST_IF` đúng interface?
21. TTL/hop-limit có đúng scope và không dùng làm ACL?
22. `IP_MULTICAST_LOOP` có được kiểm thử theo OS?
23. Có sử dụng `DatagramChannel.receive` đúng blocking/nonblocking mode?
24. Có deadline/Selector để không treo vô hạn?
25. Có giới hạn payload, xử lý datagram loss/duplicate/reorder?
26. Có protocol-level authentication, replay protection nếu dữ liệu nhạy cảm?
27. Có phân loại lỗi IllegalArgument/IllegalState/IO/Unsupported/Closed?
28. Có dọn DatagramChannel và MembershipKey trong mọi nhánh lỗi?
29. Có test trên target OS/container/NIC đúng topology?
30. Có chỉ dùng Java APIs còn hiện hành, không dựa vào legacy multicast calls chưa rõ interface?

## 16. Câu hỏi tự kiểm tra có đáp án

**1.** `MulticastChannel` là class tự tạo bằng `open`?  
**Đáp án:** Không, nó là interface; `DatagramChannel` là implementation thông dụng.

**2.** Sender cần join group trước khi gửi multicast?  
**Đáp án:** Không bắt buộc, sender có thể `send` tới group/port.

**3.** Receiver join group có tự nhận vào ByteBuffer?  
**Đáp án:** Không; vẫn cần `receive`/I/O event loop.

**4.** `join(group,ni)` trả gì?  
**Đáp án:** `MembershipKey` any-source membership.

**5.** `MembershipKey.sourceAddress()==null` nghĩa gì?  
**Đáp án:** Any-source membership, không giới hạn một nguồn cố định.

**6.** `key.drop()` làm gì?  
**Đáp án:** Rời membership; key invalid, channel có thể vẫn mở.

**7.** `channel.close()` ảnh hưởng keys ra sao?  
**Đáp án:** Mọi membership keys của channel invalid.

**8.** Join cùng group/interface lần hai khi key còn active tạo key khác?  
**Đáp án:** Với any-source membership hiện có, trả lại key đại diện membership đó.

**9.** `SO_REUSEADDR` nên set khi nào?  
**Đáp án:** Trước `bind` nếu cần cùng port cho nhiều listeners.

**10.** Receiver nên bind vào đâu?  
**Đáp án:** Wildcard address với port nhận.

**11.** `IP_MULTICAST_IF` tác động phía nào?  
**Đáp án:** Chọn interface gửi multicast, không thay `join(group,ni)`.

**12.** `IP_MULTICAST_TTL=0` có làm message private?  
**Đáp án:** Không; đó là cơ chế scope/hop, không phải security.

**13.** `join(group,ni,source)` cần source kiểu gì?  
**Đáp án:** Địa chỉ unicast cùng family với group và OS hỗ trợ filtering.

**14.** Có thể vừa join ASM vừa SSM trên cùng group/ni/channel?  
**Đáp án:** Không, có thể `IllegalStateException`.

**15.** `key.block(source)` có luôn khả dụng?  
**Đáp án:** Không; phụ thuộc OS source filtering.

**16.** Sau `drop` có thể nhận packet cũ?  
**Đáp án:** Có thể nếu datagram đã nằm trong receive buffer.

**17.** `supportsMulticast()==true` có chứng minh routing/firewall đúng?  
**Đáp án:** Không.

**18.** Cần gì để chạy IPv6 multicast?  
**Đáp án:** INET6 channel, IPv6 multicast group đúng scope, NIC phù hợp và OS/network support.

**19.** UDP multicast có bảo đảm mỗi packet được giao đúng một lần?  
**Đáp án:** Không, có thể mất/lặp/sai thứ tự.

**20.** `receive(ByteBuffer)` trả địa chỉ gì?  
**Đáp án:** Địa chỉ nguồn sender, không tự trả MembershipKey/group mà packet thuộc về.

## 17. Bài tập thực hành

### A. Xác minh multicast address

Chạy `MulticastAddressKindsDemo`, thay IPv4 group bằng một unicast khác và dự đoán `isMulticastAddress()`.

### B. Liệt kê NIC phù hợp

Chạy `MulticastInterfaceSelectionDemo` trên host và container; so sánh `supportsMulticast` và các loại địa chỉ IPv4/IPv6. Không hard-code NIC đầu tiên cho production.

### C. Chu trình join/drop/rejoin

Chạy `MulticastJoinDropDemo`, ghi lại key validity, sameKeyForRepeat và effect của close. Khi SKIPPED, ghi điều kiện môi trường chưa đáp ứng.

### D. Channel close invalid key

Chạy `MulticastKeyCloseDemo`. Giải thích tại sao không cần `key.drop()` khi channel đã close và vì sao close có thể ảnh hưởng nhiều groups.

### E. Tham số không hợp lệ

Chạy `MulticastInvalidGroupDemo` và giải thích hai trường hợp IllegalArgumentException.

### F. SSM và source filtering

Chạy `MulticastSourceFilterDemo` với source TEST-NET; phân biệt API acceptance và data-plane delivery. Thiết kế test sender có IP nguồn thực chỉ trong test VLAN.

### G. block/unblock

Chạy `MulticastBlockUnblockDemo`, so sánh branch supported và unsupported; giải thích vì sao block không đảm bảo loại bỏ datagrams đã buffered.

### H. Trộn ASM/SSM

Chạy `MulticastConflictingMembershipDemo`, sau đó đổi thứ tự: SSM trước rồi thử ASM. Dự đoán lỗi IllegalStateException và xử lý bằng drop đúng key.

### I. Loopback test

Chạy `MulticastLoopbackDemo`, quan sát RECEIVED/NOT_OBSERVED/SKIPPED; không ép mọi OS phải có cùng output. Giải thích vai trò của TTL=0 và loopback NIC.

### J. Hai receivers cùng port

Trong test environment riêng, tạo hai DatagramChannels, bật `SO_REUSEADDR` trước bind cùng port rồi join cùng group. Kiểm tra packet được phân phối thế nào trên OS đó; không kết luận mọi hệ thống giống nhau.

### K. Nonblocking receive + Selector

Thay polling sleep của demo bằng `Selector`, giữ deadline và cleanup để JVM không treo khi không có packet.

### L. Multicast protocol layer

Thiết kế message format có version, senderId, sequenceNumber, bounded payload và authentication tag; xử lý datagram duplicate/loss/reorder, không tin IP source là identity.

## 18. Tài liệu chính thức

- [Java SE 17 — MulticastChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/MulticastChannel.html): `join`, platform dependencies, protocol family, wildcard bind và `SO_REUSEADDR`.
- [Java SE 17 — DatagramChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/DatagramChannel.html): `open`, `bind`, `send`, `receive`, multicast socket options.
- [Java SE 17 — MembershipKey](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/MembershipKey.html): group, sourceAddress, interface, channel, isValid, drop, block, unblock.
- [Java SE 17 — NetworkInterface](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/NetworkInterface.html): `getByName`, `getNetworkInterfaces`, `isUp`, `supportsMulticast`, địa chỉ.
- [Java SE 17 — StandardSocketOptions](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/StandardSocketOptions.html): `SO_REUSEADDR`, `IP_MULTICAST_IF`, `IP_MULTICAST_TTL`, `IP_MULTICAST_LOOP`.
- [Java SE 17 — StandardProtocolFamily](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/StandardProtocolFamily.html): `INET` và `INET6`.
- [Java SE 17 — InetAddress](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InetAddress.html): `isMulticastAddress`.
- [Java SE 17 — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): buffer position/limit trong `send/receive`.

**Ghi nhớ:** `MulticastChannel` là API **tham gia nhóm**, `DatagramChannel` là kênh UDP thực thi gửi/nhận, `NetworkInterface` xác định nơi join, `MembershipKey` quản lý membership và `drop` để rời nhóm. Dùng đúng address family, đặt `SO_REUSEADDR` trước bind wildcard, cấu hình `IP_MULTICAST_IF` khi gửi, phân biệt ASM với SSM, xử lý khả năng thiếu source filtering và luôn đóng resources theo ownership. Multicast có tính **best effort**, phụ thuộc môi trường mạng và không cung cấp authentication/delivery guarantee tự động.
