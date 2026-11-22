# Java 7 — Socket và multicast: MembershipKey, giao diện mạng và nguồn gửi

## 1. Bức tranh tổng thể

Khi một máy gửi UDP multicast, nó gửi datagram tới **địa chỉ nhóm IP multicast và cổng UDP** thay vì mở kết nối riêng cho từng người nhận. Máy muốn nhận phải có socket gắn với cổng tương ứng, đăng ký nhận nhóm trên **giao diện mạng phù hợp**, và mạng/OS phải chuyển datagram tới socket đó.

Với Java NIO.2, `DatagramChannel` triển khai `MulticastChannel`. Phương thức `join(...)` trả một `MembershipKey`. Khóa này không chứa nội dung gói tin mà mô tả **membership của một channel đối với group, network interface và tùy chọn nguồn gửi**.

Bài học tập trung vào ba thành phần:

- **MembershipKey:** metadata, trạng thái `isValid()`, `drop()`, thay đổi membership và `block/unblock`.
- **NetworkInterface:** chọn đúng interface nhận multicast; phân biệt nó với interface gửi qua `IP_MULTICAST_IF`.
- **Nguồn gửi:** phân biệt *Any-Source Multicast* (ASM) và *Source-Specific Multicast* (SSM); nguồn được cấu hình trong `sourceAddress()` không phải người gửi datagram mới nhất.

Các API đã xuất hiện trong Java 7 và **vẫn áp dụng trong Java 17+**. Ví dụ dùng JDK 17 API, không dùng cách làm lỗi thời.

### 1.1. Sơ đồ IP, port và membership

```text
Sender A 192.0.2.10:41000 -------\
                                  \
                                   >---- 239.255.42.99:5000
                                  /          IP group + UDP port
Sender B 198.51.100.20:42000 ---/                    |
                                                      v
                  Receiver máy tính có NetworkInterface N
                       |
                       +-- DatagramChannel.bind(0.0.0.0:5000)
                       |
                       +-- join(239.255.42.99, N)
                       |       -> key ASM, nhận từ nguồn hợp lệ bất kỳ
                       |
                       +-- hoặc join(239.255.42.99, N, senderA)
                               -> key SSM, chỉ nguồn IP A
```

`192.0.2.0/24` và `198.51.100.0/24` là các dải **ví dụ tài liệu**, không đại diện sender thật trong mạng. Không kỳ vọng nhận packet từ các địa chỉ này.

| Thành phần | Ý nghĩa |
| --- | --- |
| Group multicast | Địa chỉ IP đích được chia sẻ bởi các receivers |
| UDP port | Cổng đích của datagram; thuộc socket bind/send, **không phải** trường trong MembershipKey |
| NetworkInterface | NIC cụ thể mà receiver dùng để join nhóm |
| Source IP | IP người gửi; có thể dùng để lọc ở membership |
| Source UDP port | Port của datagram gửi đến, **không** là một phần của source-specific membership API |
| MembershipKey | Token mô tả và quản lý một membership của channel |

**UDP không bảo đảm nhận đủ, đúng thứ tự, không trùng hoặc có xác nhận thành công.** Membership chỉ giúp OS đăng ký group và lọc nguồn, không thay giao thức ứng dụng.

## 2. API cần biết

| API | Công dụng |
| --- | --- |
| `DatagramChannel.open(StandardProtocolFamily.INET)` | Tạo UDP channel tương ứng IPv4 |
| `DatagramChannel.open(StandardProtocolFamily.INET6)` | Tạo UDP channel tương ứng IPv6 khi hỗ trợ |
| `DatagramChannel.bind(...)` | Gắn socket với local UDP port |
| `MulticastChannel.join(group, interf)` | ASM membership trên network interface |
| `MulticastChannel.join(group, interf, source)` | SSM membership theo IP nguồn |
| `MembershipKey.group()` | Trả group multicast |
| `MembershipKey.networkInterface()` | Trả giao diện mạng đã join |
| `MembershipKey.channel()` | Trả MulticastChannel đã tạo membership |
| `MembershipKey.sourceAddress()` | IP nguồn của SSM, hoặc null cho ASM |
| `MembershipKey.isValid()` | Membership key hiện chưa bị drop/close |
| `MembershipKey.drop()` | Rời membership cụ thể |
| `MembershipKey.block(source)` | Chặn một nguồn trên key ASM nếu OS hỗ trợ |
| `MembershipKey.unblock(source)` | Bỏ chặn nguồn trước đó |
| `NetworkInterface.isUp()` | NIC đang hoạt động theo OS |
| `NetworkInterface.supportsMulticast()` | NIC có khả năng multicast theo OS |
| `StandardSocketOptions.SO_REUSEADDR` | Hỗ trợ nhiều sockets bind cổng theo platform |
| `StandardSocketOptions.IP_MULTICAST_IF` | Chọn NIC cho **multicast outbound** |
| `StandardSocketOptions.IP_MULTICAST_TTL` | Giới hạn IP multicast hop count |
| `StandardSocketOptions.IP_MULTICAST_LOOP` | Cấu hình multicast local loopback |

`DatagramChannel` cũng là `SelectableChannel`: có thể `configureBlocking(false)` và dùng `Selector`. Nhưng `MembershipKey` không phải asynchronous `CompletionHandler`; nó chỉ quản lý membership của một **UDP channel**.

## 3. Địa chỉ nhóm và loại IP phải hợp lệ

Dải IPv4 multicast là **224.0.0.0/4**. Nhiều địa chỉ trong dải có công dụng đặc biệt; ứng dụng thật phải chọn group theo quy hoạch mạng. Trong bài dùng nhóm ví dụ:

```java
InetAddress group = InetAddress.getByName("239.255.42.99");
if (!group.isMulticastAddress()) {
    throw new IllegalArgumentException("Expected multicast address");
}
```

Đây là snippet trong phương thức, import `java.net.InetAddress` và xử lý ngoại lệ liên quan. Nhóm ở khoảng **239.255.0.0/16**, là phạm vi multicast do quản trị viên phân bổ trong mạng, không phải địa chỉ Internet toàn cầu được cấp riêng cho ứng dụng này.

Nếu group IPv4, nên dùng channel `StandardProtocolFamily.INET`. Nếu group IPv6 (thuộc `ff00::/8`), dùng `INET6` và interface/scope phù hợp. Javadoc `MulticastChannel` không bảo đảm channel tạo cho một IP family có thể nhận group thuộc IP family khác.

### 3.1. Nguồn SSM là unicast cùng family

`source` của `join(group,interface,source)` phải là **unicast IP cùng address family** với group. Với IPv4 group, dùng IPv4 unicast source. Với IPv6, dùng IPv6 unicast source phù hợp, không dùng IPv4 hoặc địa chỉ multicast khác làm source.

Ví dụ `InetAddress.getByName("192.0.2.10")` chỉ phục vụ tài liệu. Production dùng IP nguồn thật của sender được phép.

## 4. NetworkInterface: chọn đúng giao diện

Một máy có thể có Ethernet, Wi-Fi, VPN, loopback, card ảo của container hoặc nhiều NIC vật lý. Multicast đăng ký theo **giao diện**, không tự động áp dụng cho toàn bộ máy.

Những phép kiểm tra hữu ích:

```java
boolean up = nic.isUp();
boolean multicastCapable = nic.supportsMulticast();
boolean loopback = nic.isLoopback();
int index = nic.getIndex();
String name = nic.getName();
```

Đây là snippet trong phương thức, `nic` đã được lấy từ `NetworkInterface`, các phép kiểm tra có thể ném `SocketException`.

### 4.1. Không hardcode tên eth0 hoặc wlan0

`NetworkInterface.getByName("eth0")` có thể trả null trên Windows, macOS, container hoặc máy Linux không đặt tên NIC như vậy. Chọn giao diện bằng cấu hình ứng dụng, địa chỉ IP local đã biết, hoặc duyệt interfaces rồi kiểm tra:

1. `isUp() == true`.
2. `supportsMulticast() == true`.
3. Có địa chỉ IP cùng family với group.
4. Có đường mạng phù hợp giữa sender và receiver.
5. Không thuộc NIC ảo/VPN sai segment.

Không mặc định dùng NIC đầu tiên trong danh sách trên production: thứ tự liệt kê không phải một chính sách routing.

### 4.2. Duyệt IPv4 interfaces

```java
Enumeration<NetworkInterface> interfaces =
        NetworkInterface.getNetworkInterfaces();

if (interfaces != null) {
    for (NetworkInterface nic : Collections.list(interfaces)) {
        if (nic.isUp() && nic.supportsMulticast()) {
            boolean hasIPv4 = Collections.list(nic.getInetAddresses())
                    .stream().anyMatch(a -> a instanceof Inet4Address);
            if (hasIPv4) {
                System.out.println(nic.getName());
            }
        }
    }
}
```

Đây là snippet trong phương thức, cần imports `NetworkInterface`, `Inet4Address`, `Enumeration`, `Collections`, xử lý `SocketException`. Việc in tên NIC chỉ có tác dụng khám phá; quyết định NIC cuối cùng phải dựa vào cấu hình/hạ tầng thực.

### 4.3. supportsMulticast không phải network health check

Ngay cả khi OS báo NIC hỗ trợ multicast, packet vẫn có thể không đến vì:

- Switch/router không chuyển multicast hoặc IGMP snooping/router không phù hợp.
- Firewall, VPN, Kubernetes, VM hoặc cloud network policy chặn.
- Người gửi chọn sai outgoing interface hoặc IP source thực tế khác.
- Không cùng group **và** UDP port.
- TTL/hop count nhỏ, địa chỉ nhóm có scope hạn chế.
- IPv4/IPv6 family không khớp.
- Source filtering không được OS/network hỗ trợ.
- UDP packet bị mất hoặc buffer nhận không đủ.

Vì vậy dùng `supportsMulticast()` để kiểm tra **capability local**, không tuyên bố kết nối mạng chắc hoạt động.

## 5. ASM — nhận từ mọi nguồn: join(group, interface)

Lời gọi:

```java
MembershipKey membership = channel.join(group, nic);
```

tạo/tra **any-source membership**, tức nhận các datagrams gửi đến group trên interface đã join, không giới hạn một địa chỉ IP nguồn trong API join.

Các getter khi join thành công:

```java
boolean valid = membership.isValid();
InetAddress joinedGroup = membership.group();
NetworkInterface joinedNic = membership.networkInterface();
MulticastChannel owner = membership.channel();
InetAddress source = membership.sourceAddress(); // null với ASM.
```

Đây là snippet trong phương thức, `channel` là DatagramChannel mở, `group/nic` hợp lệ, có imports tương ứng.

### 5.1. ASM không có nghĩa là nhận qua mọi NIC

Nếu host có Wi-Fi và Ethernet, `join(group,wifi)` không tự động đăng ký cùng group trên Ethernet. Channel có thể join nhiều groups trên nhiều interfaces theo giới hạn OS/provider, mỗi membership gắn đúng interface.

### 5.2. ASM join lặp có lấy key mới không?

Nếu channel đã giữ ASM membership còn hợp lệ của **cùng group và NIC**, `join(group,nic)` trả **cùng MembershipKey đang có**:

```java
MembershipKey first = channel.join(group, nic);
MembershipKey again = channel.join(group, nic);
System.out.println(first == again); // true nếu membership còn valid.
```

Đây không phải “mỗi lần join thêm một subscriber độc lập”. Nếu hai component mượn cùng key và một bên gọi `drop()`, membership của bên kia cũng bị gỡ. App có nhiều consumers phải quản lý leases/owner ở tầng riêng.

### 5.3. ASM có lọc source được không?

Có thể dùng `MembershipKey.block(source)`/`unblock(source)`, **nếu OS hỗ trợ source filtering**. SourceAddress của ASM key vẫn null; block không biến key thành SSM.

## 6. SSM — chỉ một nguồn: join(group, interface, source)

Lời gọi:

```java
MembershipKey fromA = channel.join(group, nic, sourceA);
```

đại diện việc nhận từ IP nguồn `sourceA` gửi tới group trên NIC. Khi thành công, `fromA.sourceAddress().equals(sourceA)` là true.

Khác ASM:

| Kiểu | Lệnh join | Ý nghĩa |
| --- | --- | --- |
| Any-source multicast (ASM) | `join(group,nic)` | Nhận từ các nguồn gửi đến group phù hợp |
| Source-specific multicast (SSM) | `join(group,nic,sourceA)` | Nhận từ IP nguồn cụ thể A |

Với SSM, bạn có thể gọi join thêm cho nguồn B khác (cùng group/interface) để nhận từ A **hoặc** B, mỗi nguồn có key riêng. Join trùng cùng group/interface/source khi key còn hiệu lực trả lại key đã có.

### 6.1. Khả năng lọc nguồn là optional

`join(group,nic,source)` có thể ném `UnsupportedOperationException` nếu OS không hỗ trợ multicast source filtering. Không suy rằng mọi máy hỗ trợ ASM đều hỗ trợ SSM. Một số môi trường cần IGMPv3/MLDv2 và cấu hình hạ tầng tương ứng.

### 6.2. ASM và SSM không trộn cùng group/interface/channel

Nếu đã ASM:

```java
MembershipKey all = channel.join(group, nic);
channel.join(group, nic, sourceA); // IllegalStateException khi ASM còn active.
```

Nếu đã SSM, join ASM cho cùng group/interface trên channel cũng gây `IllegalStateException`. Muốn chuyển chế độ, cần drop memberships cũ có điều phối, rồi join lại. Không để hai modules tự thay đổi memberships dùng chung.

### 6.3. Source là IP, không phải port hoặc danh tính

`sourceAddress()` mô tả IP nguồn **được cấu hình** cho SSM. Nó không chứa port người gửi; không chứa mật khẩu, danh tính hay chữ ký; không phải địa chỉ của datagram nhận gần nhất. Muốn biết source IP **và port thực tế** của packet, hãy kiểm tra `SocketAddress` mà `DatagramChannel.receive(buffer)` trả về.

## 7. block và unblock: từ chối một nguồn trên ASM

Với ASM key, có thể chặn một source:

```java
MembershipKey all = channel.join(group, nic);
try {
    all.block(sourceA);
    // Kết thúc giai đoạn không muốn nhận từ A.
    all.unblock(sourceA);
} catch (UnsupportedOperationException unsupported) {
    // Không có OS-level source filter ở môi trường này.
}
```

Đây là snippet trong phương thức, xử lý `IOException` từ `block`/join. Kết quả lọc có thể bị ảnh hưởng bởi datagrams **đã vào socket receive buffer trước khi block**; không cam kết xóa những packet đó.

### 7.1. Chặn A khác với chỉ nhận A

- ASM + `block(A)`: nhận từ các nguồn **trừ A**.
- SSM + `join(...,A)`: nhận **chỉ từ A**.

Đảo hai ý nghĩa sẽ gây lỗi lớn trong ứng dụng có allow-list.

### 7.2. Cảnh báo ngoại lệ

- `block(source)` trên SSM key: `IllegalStateException`.
- `block(source)` trên key invalid: `IllegalStateException`.
- `block(source)` với IP nguồn không phải unicast hoặc không cùng family: `IllegalArgumentException`.
- `block(source)` nếu OS không hỗ trợ lọc nguồn: `UnsupportedOperationException`.
- `block(source)` khi source đã blocked: không thay đổi thêm.
- `unblock(source)` khi source chưa từng blocked hoặc key invalid: `IllegalStateException`.

Không có API public liệt kê toàn bộ nguồn đã block trong MembershipKey. Nếu ứng dụng thay đổi policy động, tự quản lý blocked set và đồng bộ các transitions.

### 7.3. block không phải bộ lọc bảo mật tuyệt đối

Filtering ở cấp IP không tự xác thực sender. IP source có thể thay đổi do NAT/routing, một số mạng cho phép spoofing, và datagram có thể đã được đệm. Nếu message có độ nhạy cảm cao, kiểm tra identity và integrity ở tầng protocol/application.

## 8. MembershipKey: vòng đời valid, drop, channel close, rejoin

```text
join() thành công ──► MembershipKey VALID
                            |
               +------------+------------+
               |                         |
           key.drop()            channel.close()
               |                         |
               +------------+------------+
                            |
                    MembershipKey INVALID
                            |
                Không thể hồi sinh key cũ
                            |
           channel còn mở? Có thể join lại
                     và nhận key mới
```

Hợp đồng:

1. Key hợp lệ khi được tạo.
2. `drop()` rời đúng membership mà key biểu diễn.
3. `drop()` **không** đóng toàn bộ DatagramChannel.
4. `drop()` lặp khi key đã invalid là no-op.
5. `DatagramChannel.close()` drop memberships, invalidates keys.
6. Invalid key **không thể valid trở lại**, kể cả sau rejoin.
7. Nếu channel còn mở, có thể rejoin để nhận key mới; phụ thuộc OS cho phép.
8. Các getter `group()/channel()/networkInterface()/sourceAddress()` vẫn trả metadata ban đầu ngay khi key invalid.
9. Datagrams đã được đệm có thể vẫn tới app sau drop.
10. `isValid()==true` xác nhận **trạng thái membership**, không xác nhận kết nối multicast end-to-end.

### 8.1. Vòng đời giữa nhiều components

Nếu cùng key được mượn bởi component A và B, A drop có thể làm B ngừng nhận group. Nên có một `MulticastSubscriptionManager` giữ ownership; consumer đăng ký/hủy lease, chỉ manager quyết định drop khi không còn consumers. Java không tự cấp reference count cho mỗi lần join lặp.

### 8.2. Concurrency với isValid và drop

Một thread thấy `isValid()==true` rồi thread khác `drop()` ngay sau đó: phép kiểm tra không khóa không bảo đảm membership tồn tại cho thao tác tiếp theo. Dùng lock/serial executor/state machine nếu nhiều threads điều phối join/drop/block/unblock/close.

## 9. Ví dụ Java 17+ hoàn chỉnh: kiểm tra vòng đời MembershipKey

Chương trình dưới đây chọn NIC multicast IPv4 đang hoạt động. Nó **không nhận packet**, chỉ test join, getter, drop, rejoin và close để không phụ thuộc máy khác gửi traffic.

**Tệp: `MembershipLifecycleDemo.java`**

```java
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.NetworkInterface;
import java.net.SocketException;
import java.net.InetSocketAddress;
import java.net.StandardProtocolFamily;
import java.net.StandardSocketOptions;
import java.nio.channels.DatagramChannel;
import java.nio.channels.MembershipKey;
import java.util.Collections;
import java.util.Enumeration;

public class MembershipLifecycleDemo {
    static boolean hasIPv4(NetworkInterface nic) {
        return Collections.list(nic.getInetAddresses()).stream()
                .anyMatch(a -> a instanceof Inet4Address);
    }
    static NetworkInterface findInterface() throws SocketException {
        Enumeration<NetworkInterface> items = NetworkInterface.getNetworkInterfaces();
        if (items == null) return null;
        NetworkInterface fallback = null;
        for (NetworkInterface nic : Collections.list(items)) {
            if (nic.isUp() && nic.supportsMulticast() && hasIPv4(nic)) {
                if (!nic.isLoopback()) return nic;
                if (fallback == null) fallback = nic;
            }
        }
        return fallback;
    }

    public static void main(String[] args) throws Exception {
        NetworkInterface nic = findInterface();
        if (nic == null) {
            System.out.println("SKIPPED: no active multicast-capable IPv4 interface");
            return;
        }
        InetAddress group = InetAddress.getByName("239.255.42.99");
        MembershipKey original;
        try (DatagramChannel channel = DatagramChannel.open(StandardProtocolFamily.INET)) {
            channel.setOption(StandardSocketOptions.SO_REUSEADDR, true);
            channel.bind(new InetSocketAddress(0));

            original = channel.join(group, nic);
            System.out.println("group is multicast = " + group.isMulticastAddress());
            System.out.println("membership valid = " + original.isValid());
            System.out.println("group matches = " + original.group().equals(group));
            System.out.println("interface matches = " + original.networkInterface().equals(nic));
            System.out.println("any-source key = " + (original.sourceAddress() == null));
            System.out.println("channel matches = " + (original.channel() == channel));
            System.out.println("repeated join same key = " + (channel.join(group, nic) == original));

            original.drop();
            System.out.println("valid after drop = " + original.isValid());
            original.drop(); // Idempotent after drop.
            MembershipKey replacement = channel.join(group, nic);
            System.out.println("rejoin yields fresh key = " +
                    (replacement != original && replacement.isValid()));
            System.out.println("old key remains invalid = " + !original.isValid());
            original = replacement;
        }
        System.out.println("valid after channel close = " + original.isValid());
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 MembershipLifecycleDemo.java
java MembershipLifecycleDemo
```

**Stdout đã kiểm thử bằng JDK 24 trên Windows có NIC multicast IPv4:**

```text
group is multicast = true
membership valid = true
group matches = true
interface matches = true
any-source key = true
channel matches = true
repeated join same key = true
valid after drop = false
rejoin yields fresh key = true
old key remains invalid = true
valid after channel close = false
```

Nếu **không tìm được NIC**, chương trình in:

```text
SKIPPED: no active multicast-capable IPv4 interface
```

Nếu có NIC phù hợp trên giấy tờ nhưng OS/network từ chối join, chương trình báo ngoại lệ. Không nên lặng lẽ in PASS khi thực tế join không thành công.

**Điểm học tập:** cùng key được trả khi join ASM trùng còn hiệu lực; drop invalidates; rejoin tạo key mới, không hồi sinh key cũ; close channel làm key cuối invalid. Port 0 chỉ là cổng tạm vì demo không nhận packet từ mạng.

## 10. Ví dụ Java 17+ hoàn chỉnh: ASM block và SSM source

Chương trình thứ hai thử hai cách lọc nguồn trên **hai channels khác nhau**, tránh xung đột ASM/SSM trên cùng group/interface/channel.

**Tệp: `SourceFilterDemo.java`**

```java
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.NetworkInterface;
import java.net.InetSocketAddress;
import java.net.StandardProtocolFamily;
import java.net.StandardSocketOptions;
import java.nio.channels.DatagramChannel;
import java.nio.channels.MembershipKey;
import java.util.Collections;

public class SourceFilterDemo {
    static NetworkInterface choose() throws Exception {
        var all = NetworkInterface.getNetworkInterfaces();
        if (all == null) return null;
        NetworkInterface fallback = null;
        for (NetworkInterface nic : Collections.list(all)) {
            if (!nic.isUp() || !nic.supportsMulticast()) continue;
            if (Collections.list(nic.getInetAddresses()).stream()
                    .noneMatch(a -> a instanceof Inet4Address)) continue;
            if (!nic.isLoopback()) return nic;
            fallback = nic;
        }
        return fallback;
    }
    public static void main(String[] args) throws Exception {
        NetworkInterface nic = choose();
        if (nic == null) {
            System.out.println("SKIPPED: no multicast IPv4 interface");
            return;
        }
        InetAddress group = InetAddress.getByName("239.255.42.100");
        InetAddress allowedSource = InetAddress.getByName("192.0.2.10");

        try (DatagramChannel receiver =
                DatagramChannel.open(StandardProtocolFamily.INET)) {
            receiver.setOption(StandardSocketOptions.SO_REUSEADDR, true);
            receiver.bind(new InetSocketAddress(0));
            MembershipKey allSources = receiver.join(group, nic);
            try {
                allSources.block(allowedSource);
                System.out.println("ASM block result = " +
                        (allSources.sourceAddress() == null && allSources.isValid()));
                allSources.unblock(allowedSource);
                System.out.println("ASM unblocked = true");
            } catch (UnsupportedOperationException unsupported) {
                System.out.println("ASM source filtering unsupported");
            } finally {
                allSources.drop();
            }
        }

        try (DatagramChannel receiver =
                DatagramChannel.open(StandardProtocolFamily.INET)) {
            receiver.setOption(StandardSocketOptions.SO_REUSEADDR, true);
            receiver.bind(new InetSocketAddress(0));
            try {
                MembershipKey onlySource = receiver.join(group, nic, allowedSource);
                System.out.println("SSM source matches = " +
                        allowedSource.equals(onlySource.sourceAddress()));
                System.out.println("SSM key valid = " + onlySource.isValid());
                try {
                    onlySource.block(allowedSource);
                    System.out.println("unexpected block success");
                } catch (IllegalStateException expected) {
                    System.out.println("SSM block rejected = true");
                }
                onlySource.drop();
            } catch (UnsupportedOperationException unsupported) {
                System.out.println("SSM source filtering unsupported");
            }
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 SourceFilterDemo.java
java SourceFilterDemo
```

**Stdout đã kiểm thử trên Windows/JDK 24 có source filtering:**

```text
ASM block result = true
ASM unblocked = true
SSM source matches = true
SSM key valid = true
SSM block rejected = true
```

Nếu OS không hỗ trợ source filtering, các nhánh liên quan có thể in `ASM source filtering unsupported` và/hoặc `SSM source filtering unsupported`. Nếu máy không có NIC thích hợp sẽ in `SKIPPED: no multicast IPv4 interface`.

Địa chỉ `192.0.2.10` chỉ dùng làm source IP **mẫu** cho bộ lọc; chương trình không gửi gói tin từ IP đó. Nếu xảy ra `IOException` khi join do mạng/hệ điều hành, lỗi được truyền lên, không giả vờ coi đó là `UnsupportedOperationException`.

## 11. Giao diện nhận và giao diện gửi là hai cấu hình khác nhau

Receiver:

```java
MembershipKey key = receiver.join(group, receiverNic);
```

Sender:

```java
sender.setOption(StandardSocketOptions.IP_MULTICAST_IF, senderNic);
```

`join` dùng NIC để **đăng ký nhóm nhận**; `IP_MULTICAST_IF` trên **sender DatagramChannel** chọn NIC cho datagrams multicast **outbound**. Hai thao tác không thay thế nhau.

### 11.1. Gửi multicast qua DatagramChannel

```java
try (DatagramChannel sender =
        DatagramChannel.open(StandardProtocolFamily.INET)) {
    sender.setOption(StandardSocketOptions.IP_MULTICAST_IF, senderNic);
    sender.setOption(StandardSocketOptions.IP_MULTICAST_TTL, 1);
    sender.setOption(StandardSocketOptions.IP_MULTICAST_LOOP, true);
    ByteBuffer bytes = ByteBuffer.wrap(
            "hello".getBytes(StandardCharsets.UTF_8));
    sender.send(bytes, new InetSocketAddress(group, 5000));
}
```

Đây là **snippet trong phương thức**, yêu cầu `senderNic` là NetworkInterface phù hợp IPv4, `group` là địa chỉ multicast IPv4, imports `DatagramChannel`, `StandardProtocolFamily`, `StandardSocketOptions`, `ByteBuffer`, `StandardCharsets`, `InetSocketAddress`, xử lý `IOException`.

- `IP_MULTICAST_IF`: interface phát multicast.
- `IP_MULTICAST_TTL`: hop limit; ví dụ đặt 1 để hạn chế phạm vi truyền.
- `IP_MULTICAST_LOOP`: cấu hình loopback multicast, phụ thuộc khả năng và thiết lập platform.
- `new InetSocketAddress(group,5000)`: **IP nhóm + cổng UDP đích**, khác với sourceAddress của MembershipKey.

Gọi `send` thành công không có nghĩa mọi receivers đã nhận data. Không coi UDP send là application acknowledgment.

### 11.2. Nguồn gửi thực có thể không như bạn đoán

Source IP và source UDP port của packet outbound phụ thuộc NIC, bind và routing của OS. `MembershipKey.sourceAddress()` không cấu hình IP nguồn của một sender; nó là filter của receiver trong chế độ SSM.

Khi nhận một packet, `DatagramChannel.receive(buffer)` trả `SocketAddress` của **nguồn thật** của packet đó. Thường là `InetSocketAddress` cho socket IP, từ đó lấy `getAddress()` và `getPort()`. Đừng dùng metadata key để suy ra địa chỉ/cổng người gửi thực tế.

## 12. Port, wildcard bind và SO_REUSEADDR

Để nhận datagram gửi đến `239.255.42.99:5000`, receiver thường phải:

1. Mở DatagramChannel đúng protocol family.
2. Bật `SO_REUSEADDR` **trước bind** nếu cần nhiều sockets cùng cổng.
3. Bind đến **wildcard** và UDP port 5000.
4. Join group trên NIC phù hợp.
5. Gọi `receive(buffer)` và xử lý datagrams (có timeout/cơ chế cancellation).

```java
try (DatagramChannel receiver =
        DatagramChannel.open(StandardProtocolFamily.INET)) {
    receiver.setOption(StandardSocketOptions.SO_REUSEADDR, true);
    receiver.bind(new InetSocketAddress(5000));
    MembershipKey key = receiver.join(group, nic);
    try {
        ByteBuffer buffer = ByteBuffer.allocate(2048);
        SocketAddress actualSender = receiver.receive(buffer);
        buffer.flip();
        // Kiểm tra actualSender và parse buffer theo protocol.
    } finally {
        key.drop();
    }
}
```

Đây là **snippet trong phương thức**, không phải ví dụ integration có stdout cố định. Khi không có sender, `receive` trong blocking mode **có thể chờ vô hạn**. Production cần Selector/nonblocking mode hoặc chính sách dừng đọc. `new InetSocketAddress(5000)` bind wildcard port; nếu bind một địa chỉ local cụ thể, việc nhận multicast có thể **implementation-specific**, theo Javadoc MulticastChannel.

### 12.1. Nonblocking receive

Với `receiver.configureBlocking(false)`, `receive(buffer)` có thể trả `null` khi chưa có packet. Nó không đồng nghĩa EOF; không busy-spin. Dùng `Selector`/readiness hoặc một cơ chế chờ phù hợp.

### 12.2. Vì sao key không có port?

Membership được mô tả bằng group/interface/source; UDP port được thiết lập ở socket/destination address. Nếu nhiều nhóm được join trên cùng socket/cổng, `receive` chỉ cho biết nguồn của datagram; không thể tự suy destination group từ một key khi socket có nhiều memberships. Khi cần phân biệt, tách channels/ports, dùng metadata trong payload hoặc khả năng riêng được provider hỗ trợ.

## 13. IPv4, IPv6, IGMP, MLD và giới hạn OS

Với IPv4 multicast, OS/network có thể dùng IGMP để quản lý membership; với IPv6 là MLD. Source filtering thường cần hỗ trợ tương ứng ở OS/provider và mạng. Java cung cấp API nhưng không bảo đảm toàn bộ switches, routers, firewalls, hypervisors hoặc cloud fabric đều cho multicast đi qua.

Với IPv6:

- Chọn `StandardProtocolFamily.INET6` và group IPv6 multicast.
- Chọn NetworkInterface có IPv6 address/scope phù hợp.
- Source-specific lọc địa chỉ IPv6 **unicast**.
- Với link-local multicast cần chú ý interface index/scope; cùng chuỗi địa chỉ nhưng trên interface khác có thể khác ngữ cảnh.
- Đừng tự chuyển IPv4 address sang IPv6 rồi giả định source filtering hoạt động như nhau.

**Không dùng khả năng join thành công làm bằng chứng packet sẽ được nhận.** Để kiểm thử delivery, cần sender thực, đúng group/port, interface và TTL, quan sát receive, xác nhận payload và sequence number nếu cần.

## 14. Lỗi và exceptions

| Tình huống | Exception/hành vi |
| --- | --- |
| Group không phải IP multicast | `IllegalArgumentException` |
| Group không thuộc family channel | `IllegalArgumentException` hoặc lỗi capability tương ứng |
| SSM source không unicast/cùng family | `IllegalArgumentException` |
| Source filtering không hỗ trợ | `UnsupportedOperationException` |
| Multicast không được platform hỗ trợ | `UnsupportedOperationException` |
| Join với channel đã đóng | `ClosedChannelException` |
| ASM và SSM trộn cùng group/interface/channel | `IllegalStateException` |
| block trên SSM key hoặc key invalid | `IllegalStateException` |
| unblock source chưa block hoặc key invalid | `IllegalStateException` |
| block source sai kiểu địa chỉ | `IllegalArgumentException` |
| Join/drop do I/O hoặc OS gặp lỗi | `IOException` đối với join/block có checked I/O |
| Drop key đã invalid | Không có hiệu ứng |
| Interface theo tên không tồn tại | `NetworkInterface.getByName(...)` có thể trả null |
| NIC không hoạt động/không multicast | Không nên cố join nếu capability check không đạt |
| Receive nonblocking chưa có datagram | `receive(...) == null` |
| Không có packet tới đúng group/port | Blocking receive có thể chờ; cần deadline |

**Phân biệt lỗi không hỗ trợ với lỗi cấu hình.** `UnsupportedOperationException` báo capability; `IOException` có thể là interface/routing/quyền; `IllegalStateException` thường là lỗi sử dụng key/mode của chương trình. Không catch mọi exception rồi báo “không hỗ trợ multicast”.

## 15. Những rủi ro khi vận hành

### 15.1. Chọn sai NIC

Một máy có nhiều interfaces; chọn NIC đầu tiên dù nó là VPN hoặc adapter ảo có thể làm join thành công nhưng packet không tới. Cho phép cấu hình NIC, log ID, IP family, trạng thái và tên NIC, không log dữ liệu nhạy cảm.

### 15.2. Source filtering không phải xác thực

SSM/block dựa trên IP nguồn, không dựa trên user identity. Khi nguồn được phép bị giả mạo/đổi địa chỉ hoặc một attacker truy cập mạng, vẫn cần message integrity và authentication ở tầng ứng dụng nếu rủi ro đáng kể. SSM không tự mã hóa nội dung.

### 15.3. Datagram đã nằm trong buffer

Gọi `block` hoặc `drop` không có nghĩa các packet cũ đã nằm trong receive buffer sẽ bị xóa. Khi thay policy, app có thể cần kiểm tra sequence/version/source của packet thực nhận và quản lý transition rõ.

### 15.4. Port, TTL, NAT và firewall

Một sender đúng group nhưng sai UDP port sẽ không tới app. TTL thấp, router không forward multicast, NAT/cloud fabric không hỗ trợ hoặc firewall chặn đều làm mất data. `key.isValid()` không giúp chẩn đoán hết các vấn đề này.

### 15.5. Concurrency và ownership

Nhiều threads có thể tranh nhau join/drop và đổi block list. Một key có thể bị drop giữa lúc thread khác thấy valid. App cần một owner/state machine, đồng bộ policy changes và cleanup; tránh “mỗi request tự join rồi drop” nếu cùng channel/group được chia sẻ.

## 16. Checklist review

- [ ] Đã xác minh group là multicast IP và đúng phạm vi quy hoạch?
- [ ] Channel đã mở bằng `INET` hoặc `INET6` phù hợp group?
- [ ] Chọn NetworkInterface theo cấu hình/hạ tầng, không hardcode tên NIC không portable?
- [ ] Interface đang up, supportsMulticast và có IP family tương ứng?
- [ ] Hiểu multicast capability không bảo đảm delivery end-to-end?
- [ ] Receiver đã bind đúng cổng UDP đích, thường là wildcard?
- [ ] Nếu cần SO_REUSEADDR, đã đặt **trước bind**?
- [ ] Phân biệt rõ ASM và SSM?
- [ ] ASM `sourceAddress()==null` được xử lý đúng?
- [ ] SSM source là unicast cùng family với group?
- [ ] Không trộn ASM/SSM trên cùng group/interface/channel?
- [ ] Có xử lý UnsupportedOperationException cho source filtering?
- [ ] Không âm thầm fallback từ SSM sang ASM nếu policy cần fail-closed?
- [ ] block/unblock chỉ trên ASM key và quản lý nguồn đã blocked?
- [ ] Không coi `drop` là đóng toàn channel?
- [ ] Không tái sử dụng invalid key sau drop/close?
- [ ] Khi rejoin, lấy key mới, không kỳ vọng old key valid?
- [ ] Shared subscription có owner/lease trước khi drop?
- [ ] Outbound interface cấu hình riêng bằng IP_MULTICAST_IF?
- [ ] Sender gửi đúng group + UDP port, TTL/loopback tùy môi trường?
- [ ] Khi receive, lấy nguồn thực từ SocketAddress, không đoán bằng MembershipKey?
- [ ] Ứng dụng xử lý UDP loss, duplication và message integrity?
- [ ] Có timeout/Selector cho receiver khi không có packet?
- [ ] Có kiểm tra OS/router/firewall/VPN/cloud multicast support thật?
- [ ] Test không assert tuyệt đối mọi datagram sẽ quay lại trên loopback?
- [ ] Có metrics join/drop failures, nhận packet theo nguồn/interface?
- [ ] Có authentication/validation riêng nếu source IP không đủ an toàn?

## 17. Những hiểu nhầm thường gặp

**1.** “join(group,nic) nghĩa là join mọi NIC.” — Sai; một NIC cụ thể.

**2.** “MembershipKey chứa UDP port.” — Sai; socket bind/destination mới có port.

**3.** “sourceAddress là IP người vừa gửi packet cuối.” — Sai; nó là IP filter được cấu hình cho SSM.

**4.** “sourceAddress null nghĩa là key lỗi.” — Sai; đó là key ASM hợp lệ.

**5.** “supportsMulticast true nghĩa là mạng sẽ chuyển packet.” — Sai; còn router, firewall, TTL, port và sender.

**6.** “IP_MULTICAST_IF thay được join.” — Sai; IP_MULTICAST_IF là outgoing interface.

**7.** “join lần hai cùng group/interface tạo subscriber riêng.” — Sai với ASM cùng channel; trả key hiện có.

**8.** “drop đóng luôn channel.” — Sai; chỉ gỡ membership.

**9.** “Rejoin sẽ hồi sinh key cũ.” — Sai; key cũ invalid vĩnh viễn.

**10.** “Close channel không ảnh hưởng MembershipKey.” — Sai; keys invalid.

**11.** “ASM block(A) tương đương SSM join(A).” — Sai; block loại A, SSM chỉ nhận A.

**12.** “block có thể dùng trên SSM key.” — Sai; IllegalStateException.

**13.** “unblock chưa block chỉ là no-op.” — Sai; IllegalStateException.

**14.** “SSM luôn được hỗ trợ nếu ASM hoạt động.” — Sai; phụ thuộc OS source filtering.

**15.** “Lọc IP nguồn cũng lọc cổng UDP nguồn.” — Sai; API filter chỉ theo địa chỉ IP nguồn.

**16.** “Sau drop không còn packet cũ trong receive buffer.” — Sai; có thể còn.

**17.** “Key valid tức là dữ liệu đang được nhận.” — Sai; không phải network health check.

**18.** “Một IPv6 group dùng INET IPv4 chắc vẫn hoạt động.” — Không có guarantee portable.

**19.** “IP nguồn đủ xác thực sender.” — Sai; cần validation/authentication.

**20.** “UDP multicast đảm bảo packet không mất.” — Sai; UDP là best-effort.

## 18. Câu hỏi tự kiểm tra

**1.** MembershipKey là gì? — Token đại diện một membership multicast của channel.

**2.** group() trả gì? — Địa chỉ nhóm multicast.

**3.** networkInterface() trả gì? — NIC đã tham gia nhóm.

**4.** channel() trả gì? — MulticastChannel tạo key.

**5.** sourceAddress()==null có nghĩa gì? — Any-source membership.

**6.** sourceAddress()!=null có nghĩa gì? — Source-specific membership với IP đó.

**7.** ASM dùng join overload nào? — join(group,interface).

**8.** SSM dùng join overload nào? — join(group,interface,source).

**9.** SSM source phải là địa chỉ nào? — Unicast cùng IP family với group.

**10.** SSM có thể không được OS hỗ trợ không? — Có; UnsupportedOperationException.

**11.** ASM và SSM cho cùng group/interface trên một channel trộn được không? — Không.

**12.** block(source) dành cho key nào? — ASM, nếu OS hỗ trợ.

**13.** block trên SSM key gây gì? — IllegalStateException.

**14.** unblock source chưa block gây gì? — IllegalStateException.

**15.** Repeated ASM join trên cùng channel/group/interface trả gì? — Cùng key đang valid.

**16.** drop() có đóng channel không? — Không.

**17.** drop() hai lần có hồi sinh key không? — Không.

**18.** Rejoin sau drop dùng key nào? — Key mới.

**19.** Close channel làm keys ra sao? — Invalid.

**20.** isValid() cho biết mạng chắc nhận packet không? — Không; chỉ membership lifecycle.

**21.** Vì sao chọn NIC đúng là quan trọng? — Join trên một interface cụ thể, network segments/routes khác nhau.

**22.** Giao diện gửi được chọn bằng option nào? — IP_MULTICAST_IF.

**23.** Receiver cần bind gì? — UDP port đích, thường wildcard address.

**24.** Lệnh send cần những gì? — Payload cùng multicast group IP và UDP port.

**25.** Nguồn thực của packet được lấy từ đâu? — DatagramChannel.receive() trả SocketAddress.

**26.** Dùng INET cho loại group nào? — IPv4.

**27.** Vì sao cần test multicast trên môi trường thực? — Phụ thuộc IGMP/MLD, NIC, OS, router, firewall, VPN.

**28.** Source filter có thay message authentication không? — Không.

## 19. Tài liệu chính thức còn áp dụng

- [Java SE 17 — MembershipKey](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/MembershipKey.html): group/networkInterface/channel/sourceAddress, isValid, drop, block, unblock.
- [Java SE 17 — MulticastChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/MulticastChannel.html): ASM/SSM join và yêu cầu platform.
- [Java SE 17 — DatagramChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/DatagramChannel.html): send, receive, bind, DatagramChannel.open(family).
- [Java SE 17 — NetworkInterface](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/NetworkInterface.html): chọn/kiểm tra NIC.
- [Java SE 17 — StandardSocketOptions](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/StandardSocketOptions.html): SO_REUSEADDR, IP_MULTICAST_IF, IP_MULTICAST_TTL, IP_MULTICAST_LOOP.
- [Java SE 17 — InetAddress](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InetAddress.html): multicast và address family.
- [RFC 2365 — Administratively Scoped IP Multicast](https://www.rfc-editor.org/rfc/rfc2365): phạm vi group multicast quản lý.
- [RFC 4607 — Source-Specific Multicast](https://www.rfc-editor.org/rfc/rfc4607): SSM và nguồn gửi.

**Ghi nhớ:** `MembershipKey` quản lý đúng membership của **group + NetworkInterface + tùy chọn source IP**. ASM trả `sourceAddress()==null`; SSM chỉ nhận nguồn IP đã chỉ định khi OS hỗ trợ. `block/unblock` chỉ áp dụng cho ASM và cũng phụ thuộc source filtering support. `drop` hoặc đóng channel làm key invalid vĩnh viễn; muốn tham gia lại phải `join` để nhận key mới. Giao diện **nhận** được chọn khi join, giao diện **gửi** được chọn qua `IP_MULTICAST_IF`, còn cổng UDP thuộc bind/send, **không** thuộc MembershipKey.