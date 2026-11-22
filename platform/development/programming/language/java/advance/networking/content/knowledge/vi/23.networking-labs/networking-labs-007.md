# Thử multicast với card mạng được chọn rõ và dọn membership

## 1. Mục tiêu thực nghiệm

Trong Java Networking, **IP multicast** cho phép một sender gửi **một UDP datagram đến địa chỉ nhóm** (multicast group), còn các receiver đã **tham gia nhóm trên một network interface phù hợp** có thể nhận dữ liệu đó. Máy có nhiều card mạng — Wi-Fi, Ethernet, VPN, Docker/VM adapters, loopback — không nên phó mặc giao diện gửi/nhận cho lựa chọn ngầm định của hệ điều hành nếu bạn cần kết quả thí nghiệm lặp lại được.

Bài học thuộc nhóm **Thực nghiệm mạng** và tập trung vào hai nguyên tắc:
1. **Chỉ định card mạng rõ ràng:** người dùng chọn interface theo **tên** hoặc policy đã xác minh; receiver `join(group, networkInterface)`, sender đặt `IP_MULTICAST_IF` đúng interface ấy. **Không** lấy interface đầu tiên mà API liệt kê rồi coi nó đúng.
2. **Dọn membership:** sau khi đã join, giữ `MembershipKey` và gọi `drop()` trong `finally`; sau đó đóng `DatagramChannel` bằng `try-with-resources`. Với API `MulticastSocket`, ghép `joinGroup(..., netIf)` với `leaveGroup(..., netIf)`; đóng socket riêng.

Bạn sẽ học:
- Sự khác nhau giữa unicast, broadcast và multicast; group IP không phải địa chỉ một máy chủ.
- Ý nghĩa nhóm IPv4 `239.255.42.42`, UDP port, IPv4/IPv6 protocol family, TTL và multicast loopback.
- Cách liệt kê `NetworkInterface` và đánh giá `isUp()`, `supportsMulticast()`, địa chỉ IPv4.
- Cách dùng `DatagramChannel.open(StandardProtocolFamily.INET)`, `join(group, nic)`, `IP_MULTICAST_IF` và `Selector` để nhận có thời gian chờ.
- Chính xác lifecycle của `MembershipKey.isValid()`, `drop()` và `channel.close()`.
- Ví dụ `MulticastSocket` cũ còn dùng được ở Java 17 và API `joinGroup(SocketAddress, NetworkInterface)` hiện phù hợp.
- Các lỗi do chọn nhầm card, network policy/firewall/VPN, vòng đời resource, receiver buffer, timeout và scope.
- Bốn chương trình kiểm thử **Java 17+**, trong đó ba chương trình multicast đã được biên dịch và chạy trên giao diện loopback được chỉ định rõ.

**Lưu ý phạm vi:** Multicast chủ yếu dựa trên **UDP**, không có đảm bảo truyền thành công, thứ tự đến hoặc chống trùng lặp. Tham gia một multicast group không làm dữ liệu trở nên bảo mật hay đáng tin. Đừng gửi mật khẩu, token hoặc thông tin cá nhân qua group test.

## 2. Multicast hoạt động như thế nào?

Mô hình khái niệm:

```text
                  group: 239.255.42.42
                  UDP destination port: 54321
                           │
Sender ── send packet ─────┘
    │
    ├── outgoing interface: NIC_A
    │
    ▼
OS / network multicast delivery
    ├─ Receiver 1: join(group, NIC_A), bind UDP :54321 ─► có thể nhận
    ├─ Receiver 2: join(group, NIC_B), bind UDP :54321 ─► tùy topology
    └─ Receiver 3: không join group                ─► thường không nhận
```

Multicast address đại diện một **nhóm người nhận**. Sender không cần có danh sách IP từng receiver. Nhưng **UDP datagram được gửi đến cả group IP và port đích**; một receiver chỉ join group mà bind nhầm port vẫn không nhận được payload ứng dụng.

So sánh:

| Kiểu | Destination | Ý nghĩa |
| --- | --- | --- |
| Unicast | IP của một host | Gửi tới một đích mạng cụ thể |
| Broadcast IPv4 | Broadcast address của mạng | Phát trong miền broadcast phù hợp; không phải IP multicast |
| Multicast | Địa chỉ IP thuộc dải multicast | Các receivers quan tâm có thể tham gia group |
| Anycast | Nhiều nơi dùng cùng địa chỉ/định tuyến chọn đích | Không đồng nghĩa multicast |

IP multicast không tự tạo **message broker** hoặc cơ chế delivery acknowledgement. UDP payload có thể bị mất, bị trùng hoặc đến không đúng thứ tự; ứng dụng cần thiết kế protocol khi yêu cầu reliability.

## 3. Nhóm IP, UDP port và network interface là ba phần độc lập

Một thí nghiệm thực hiện đầy đủ cần cấu hình:

```text
Protocol family: IPv4 / INET
Group address:   239.255.42.42
UDP port:        54321 hoặc port 0 cấp động cho thử nghiệm một process
Interface:       tên do người chạy cung cấp, ví dụ loopback_0 trên máy test
TTL:             0 khi chỉ muốn thử local host
Loopback:        enabled để sender cùng host có thể thử nhận
```

**Group address** xác định nhóm, **port** xác định endpoint UDP ứng dụng đang nghe, còn **NetworkInterface** xác định địa bàn mạng mà socket tham gia group hoặc phát multicast.

Một host có thể có:
- Card Ethernet vật lý.
- Wi-Fi.
- VPN adapter.
- Virtual switch cho container/VM.
- Loopback.
- IPv6-only interface hoặc interface không có IPv4.

Nếu dùng `NetworkInterface.getNetworkInterfaces()` rồi tự lấy phần tử đầu tiên, thứ tự liệt kê có thể thay đổi, và phần tử đầu có thể là **interface ảo không thể nhận multicast**. Bài này buộc chương trình nhận **tên interface từ command line**, kiểm tra điều kiện, và báo lỗi rõ khi tên không hợp lệ.

## 4. Vì sao chọn card mạng ngầm định gây lỗi khó debug?

Khi không đặt `IP_MULTICAST_IF`, outgoing interface có thể được hệ điều hành chọn theo routing policy. Khi `MulticastSocket.joinGroup` nhận `netIf=null`, tài liệu Java 17 nói hành vi có thể không xác định nếu không có default interface được đặt, hoặc lời gọi có thể thất bại.

Những tình huống:
1. Laptop có Wi-Fi và Ethernet, sender phát qua Ethernet nhưng receiver join trên Wi-Fi.
2. VPN cài route ưu tiên, multicast bị gửi vào adapter không hỗ trợ.
3. Docker/VM adapter xuất hiện trước card thật khi liệt kê.
4. Receiver bind đúng UDP port nhưng join group trên interface không có đường nhận packet.
5. Sender và receiver chạy cùng máy nhưng OS không bật multicast loopback trên interface đã chọn.
6. Laptop thay mạng, tên/index card hoặc routing thay đổi sau restart.
7. Firewall chặn inbound UDP dù `supportsMulticast() == true`.

**Giải pháp:** người dùng xác định interface theo nhu cầu, kiểm tra `isUp`, `supportsMulticast`, address family, rồi dùng **chính object `NetworkInterface` đó** khi join và khi chọn interface gửi.

## 5. API NetworkInterface quan trọng

`java.net.NetworkInterface` đại diện một network interface của máy.

| API | Dùng để làm gì |
| --- | --- |
| `NetworkInterface.getNetworkInterfaces()` | Liệt kê các interface mà Java nhìn thấy |
| `NetworkInterface.getByName(String)` | Chọn interface theo **tên hệ thống** |
| `getName()` | Lấy tên ổn định trong phạm vi runtime hiện hành (không bảo đảm giữa mọi OS) |
| `getDisplayName()` | Nhãn mô tả thân thiện; không nên dùng để so sánh identity |
| `isUp()` | Interface đang được bật theo OS |
| `supportsMulticast()` | OS cho biết interface có capability multicast |
| `isLoopback()` | Interface loopback |
| `isPointToPoint()` | Interface point-to-point |
| `getInetAddresses()` | Liệt kê các địa chỉ IP của interface |
| `getIndex()` | Chỉ số interface của hệ điều hành, có thể thay đổi |
| `NetworkInterface.getByInetAddress(ip)` | Tìm interface có một địa chỉ được chỉ định |

`supportsMulticast()` là **capability check**, không phải đảm bảo datagram sẽ đến. Network ACL, multicast forwarding, Wi-Fi AP isolation, IGMP snooping, VPN và firewall vẫn có thể ngăn traffic.

### Ví dụ kiểm tra interface rõ ràng (mảnh code)

```java
NetworkInterface nic = NetworkInterface.getByName(requestedName);
if (nic == null || !nic.isUp() || !nic.supportsMulticast()) {
    throw new IllegalArgumentException("Interface unavailable for multicast");
}
boolean hasIPv4 = Collections.list(nic.getInetAddresses()).stream()
        .anyMatch(address -> address instanceof Inet4Address);
if (!hasIPv4) {
    throw new IllegalArgumentException("IPv4 interface required");
}
```

Mảnh code cần imports `java.net.*`, `java.util.Collections` và biến `String requestedName`. Với bài thử IPv6 phải kiểm tra `Inet6Address` và dùng `StandardProtocolFamily.INET6`; không dùng IPv4 group trên IPv6-only adapter rồi cho rằng lỗi thuộc firewall.

## 6. Chương trình Java 17 số 1: liệt kê card mạng để chọn

Trước khi chạy receiver, cần biết **tên interface thực tế** của máy. Mã sau liệt kê đúng những thuộc tính cần cho thí nghiệm, **không tự chọn** card nào.

Lưu file **`InterfaceProbe282.java`**:

```java
import java.net.*;
import java.util.*;

public class InterfaceProbe282 {
    public static void main(String[] args) throws Exception {
        for (NetworkInterface nic :
                Collections.list(NetworkInterface.getNetworkInterfaces())) {
            boolean v4 = Collections.list(nic.getInetAddresses()).stream()
                    .anyMatch(a -> a instanceof Inet4Address);
            System.out.printf(
                    "name=%s up=%s multicast=%s loopback=%s ipv4=%s%n",
                    nic.getName(),
                    nic.isUp(),
                    nic.supportsMulticast(),
                    nic.isLoopback(),
                    v4);
        }
    }
}
```

Lệnh biên dịch/chạy:

```bash
javac InterfaceProbe282.java
java InterfaceProbe282
```

**Output phụ thuộc máy** — đây là **trích một số dòng** từ lần kiểm thử trên Windows/JDK hỗ trợ Java 17 API, không phải output cố định cho mọi máy:

```text
name=ethernet_32769 up=true multicast=true loopback=false ipv4=true
name=ethernet_32774 up=true multicast=true loopback=false ipv4=true
name=loopback_0 up=true multicast=true loopback=true ipv4=true
```

Máy khác có thể liệt kê `lo`, `eth0`, `en0` hoặc tên khác; không copy `loopback_0` một cách máy móc. Chỉ dùng đúng **tên mà chương trình trên máy của bạn in ra**.

Với bài thử **cùng process/cùng host**, ưu tiên một **loopback interface thực sự có hỗ trợ IPv4 multicast**. Nếu loopback OS không hỗ trợ, **không tự đổi** sang card thật rồi phát traffic lên LAN mà không hiểu môi trường; chọn card phù hợp có chủ đích và đọc lưu ý network ở mục 23.

## 7. Chọn nhóm địa chỉ phù hợp cho bài thử

Địa chỉ `239.255.42.42` thuộc dải **239.255.0.0/16 — IPv4 Local Scope** theo RFC 2365. Ta chọn nó để không đụng các multicast groups phục vụ control protocols chuyên dụng.

Tuy nhiên:
- Một **administratively scoped group address** không có nghĩa “chỉ chạy trong process” hoặc “chỉ chạy localhost” trong mọi mạng.
- **TTL = 0** là cấu hình quan trọng trong bài thử trên cùng máy: multicast datagram **không được truyền lên network**, dù có thể được phát lại nội bộ cho receiver local.
- Nếu muốn thử giữa hai máy trong cùng mạng, TTL thường cần lớn hơn 0, đồng thời network switch/router/firewall phải cho phép multicast; hãy làm trong mạng thí nghiệm được phép.
- Tránh dùng `224.0.0.0/24` tùy tiện vì dải này có nhiều địa chỉ multicast điều khiển link-local.
- IPv4 multicast được chứa trong `224.0.0.0/4`. Không dùng địa chỉ unicast `127.0.0.1` như một multicast group.

Nhóm demo:
- `239.255.42.42` cho thí nghiệm gửi/nhận chính.
- `239.255.42.43` cho bài test hai membership độc lập.
- `239.255.42.44` cho API `MulticastSocket`.

Nếu địa chỉ/port này đã được một ứng dụng khác trên máy dùng, chọn group/port thí nghiệm khác thuộc phạm vi do bạn kiểm soát.

## 8. Java NIO multicast: DatagramChannel và MembershipKey

Java NIO hỗ trợ multicast qua `DatagramChannel` vì nó thực thi `MulticastChannel`.

Một receiver cần:
1. Mở channel với đúng address family, ví dụ `DatagramChannel.open(StandardProtocolFamily.INET)` cho IPv4.
2. Nếu dùng port chung giữa receivers, đặt `SO_REUSEADDR` trước `bind` (tính portable phụ thuộc OS).
3. Bind UDP socket lên **local listening port**, có thể dùng port `0` cho OS cấp trong test.
4. Gọi `MembershipKey key = receiver.join(group, nic)`.
5. Đọc datagrams; có thể dùng blocking receive, hoặc `Selector` với channel nonblocking.
6. Trong `finally`, gọi `key.drop()` để rời group.
7. Đóng channel sau khi kết thúc xử lý.

```java
try (DatagramChannel receiver =
        DatagramChannel.open(StandardProtocolFamily.INET)) {
    receiver.setOption(StandardSocketOptions.SO_REUSEADDR, true);
    receiver.bind(new InetSocketAddress(54321));

    MembershipKey membership = receiver.join(group, nic);
    try {
        // Đọc UDP datagrams...
    } finally {
        membership.drop(); // rời group dù đọc lỗi / bị hủy
    }
} // receiver.close() được gọi tại đây
```

Đây là **mảnh code**, cần `InetAddress group`, `NetworkInterface nic` và imports. Trong production, xử lý khả năng bind/join thất bại, selector/cancellation, và chọn port hợp lệ. **`MembershipKey` không implement `AutoCloseable`**, vì vậy không thể dùng `try (MembershipKey key = ...)` như một input stream; phải quản lý `drop()` rõ ràng.

## 9. Interface nhận khác interface gửi

Hai thao tác rất dễ nhầm:

```java
MembershipKey membership = receiver.join(group, nic);

sender.setOption(StandardSocketOptions.IP_MULTICAST_IF, nic);
```

- `receiver.join(group, nic)`: tham gia **group trên interface nic để nhận** multicast datagrams.
- `sender.setOption(IP_MULTICAST_IF, nic)`: chọn **interface phát outbound** multicast datagrams trên sender.
- `receiver.setOption(IP_MULTICAST_IF, nic)` **không thay thế** `receiver.join(group, nic)`. IP_MULTICAST_IF chủ yếu quyết định multicast **outgoing interface**, không phải tự đăng ký lắng nghe group.
- Chỉ `sender.send(buffer, groupSocketAddress)` không có nghĩa channel trở thành member của group; sender không cần join nếu chỉ phát.

Trong một test cùng host, hãy dùng **cùng NetworkInterface object** cho cả hai thao tác, tránh gửi vào card này nhưng join trên card khác. Khi test giữa hai máy, mỗi máy phải chọn **interface của chính máy ấy**; tên/index card không cần giống nhau, nhưng các card phải cùng một multicast-reachable domain.

## 10. IP_MULTICAST_IF, TTL và LOOP

`java.net.StandardSocketOptions` định nghĩa các tùy chọn:

| Option | Kiểu | Ý nghĩa |
| --- | --- | --- |
| `IP_MULTICAST_IF` | `NetworkInterface` | Chọn interface cho multicast **outbound** |
| `IP_MULTICAST_TTL` | `Integer` 0..255 | TTL/hop-limit của multicast datagram |
| `IP_MULTICAST_LOOP` | `Boolean` | Cho phép loopback các datagrams multicast trong phạm vi host, theo semantics OS |
| `SO_REUSEADDR` | `Boolean` | Cho phép dạng reuse address theo OS, thường đặt trước bind |
| `SO_RCVBUF` | `Integer` | Gợi ý kích thước receive buffer, không bảo đảm số datagrams giữ được |

Trong thí nghiệm:
 
```java
sender.setOption(StandardSocketOptions.IP_MULTICAST_IF, nic);
sender.setOption(StandardSocketOptions.IP_MULTICAST_TTL, 0);
sender.setOption(StandardSocketOptions.IP_MULTICAST_LOOP, true);
```

**TTL = 0**: với IPv4, datagram không truyền trên network nhưng **có thể** được delivery nội bộ. Trong bài kiểm thử đã chạy, datagram xuất hiện ở receiver loopback. Không coi TTL 0 là bảo đảm delivery trên mọi platform; `IP_MULTICAST_LOOP` có semantics phụ thuộc OS và có thể ảnh hưởng socket gửi hoặc nhận tùy implementation.

**TTL = 1**: thường phù hợp cho mạng cục bộ khi đã được phép và router không forwarding quá một hop; **không** tương đương “chỉ ở localhost”. Không tăng TTL để “chữa” lỗi loopback khi bạn chưa muốn gửi traffic ra LAN.

## 11. Multicast receiver bind port và SO_REUSEADDR

Các receivers muốn nhận **cùng group:port** thường phải bind local UDP port đó:
 
```java
receiver.setOption(StandardSocketOptions.SO_REUSEADDR, true);
receiver.bind(new InetSocketAddress(54321));
MembershipKey key = receiver.join(group, nic);
```

**Mảnh code**. Nếu nhiều receiver processes cùng bind port:
- Thường cần `SO_REUSEADDR` và quy tắc của OS.
- Một số hệ thống có `SO_REUSEPORT`, nhưng **không phải mọi OS/DatagramChannel đều hỗ trợ**.
- Dù reuse thành công, delivery behavior giữa nhiều sockets có thể khác theo OS, group membership và firewall.
- Không suy rằng “đã join group” sẽ tự mở đúng UDP port; `join` không thay `bind`.

Trong chương trình đầy đủ, receiver bind port `0` để OS chọn port rảnh rồi sender lấy:

```java
int port = ((InetSocketAddress) receiver.getLocalAddress()).getPort();
```

Cách đó lý tưởng cho **một process có cả sender và receiver**. Hai process độc lập **phải thỏa thuận trước cùng group và port**, không thể mỗi process tự bind port 0 rồi mặc nhiên nhận cùng luồng dữ liệu.

## 12. Chương trình Java 17 số 2: chọn NIC rõ và nhận multicast loopback

Đây là ví dụ trọng tâm. Chương trình:
- **Bắt buộc nhận đúng một đối số**: tên interface do người chạy chỉ định, không tự chọn card mặc định.
- Kiểm tra card tồn tại, `isUp()`, `supportsMulticast()`, có IPv4.
- Dùng `DatagramChannel.open(StandardProtocolFamily.INET)` cho IPv4.
- Receiver bind port ngẫu nhiên, nhận group `239.255.42.42` qua `join(group,nic)`.
- Sender chọn `IP_MULTICAST_IF=nic`, đặt TTL `0` và loopback `true`.
- Gửi `hello-group` **11 bytes** qua UDP multicast.
- Receiver nonblocking dùng `Selector.select(2000)` để không chờ vô hạn.
- `membership.drop()` trong `finally`; cả sender/receiver và selector đều đóng qua `try-with-resources`.

Lưu file **`ExplicitInterfaceMulticastDemo.java`**:

```java
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.NetworkInterface;
import java.net.SocketAddress;
import java.net.StandardProtocolFamily;
import java.net.StandardSocketOptions;
import java.nio.ByteBuffer;
import java.nio.channels.DatagramChannel;
import java.nio.channels.MembershipKey;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.charset.StandardCharsets;
import java.util.Collections;

public class ExplicitInterfaceMulticastDemo {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: java ExplicitInterfaceMulticastDemo <interface-name>");
        }
        NetworkInterface nic = NetworkInterface.getByName(args[0]);
        if (nic == null || !nic.isUp() || !nic.supportsMulticast()) {
            throw new IllegalArgumentException(
                    "Interface absent/down/no multicast support");
        }
        if (Collections.list(nic.getInetAddresses()).stream()
                .noneMatch(a -> a instanceof Inet4Address)) {
            throw new IllegalArgumentException(
                    "Interface has no IPv4 address");
        }

        InetAddress group = InetAddress.getByName("239.255.42.42");
        System.out.println("selected-interface=" + nic.getName());

        try (DatagramChannel receiver =
                     DatagramChannel.open(StandardProtocolFamily.INET);
             DatagramChannel sender =
                     DatagramChannel.open(StandardProtocolFamily.INET)) {

            receiver.setOption(StandardSocketOptions.SO_REUSEADDR, true);
            receiver.bind(new InetSocketAddress(0));
            receiver.setOption(StandardSocketOptions.IP_MULTICAST_LOOP, true);
            receiver.configureBlocking(false);

            sender.setOption(StandardSocketOptions.IP_MULTICAST_IF, nic);
            sender.setOption(StandardSocketOptions.IP_MULTICAST_TTL, 0);
            sender.setOption(StandardSocketOptions.IP_MULTICAST_LOOP, true);

            MembershipKey membership = receiver.join(group, nic);
            try {
                System.out.println(
                        "membership-valid-before=" + membership.isValid());

                int port = ((InetSocketAddress)
                        receiver.getLocalAddress()).getPort();
                byte[] bytes = "hello-group".getBytes(StandardCharsets.UTF_8);
                int sent = sender.send(ByteBuffer.wrap(bytes),
                        new InetSocketAddress(group, port));
                System.out.println("sent-bytes=" + sent);

                try (Selector selector = Selector.open()) {
                    receiver.register(selector, SelectionKey.OP_READ);
                    int ready = selector.select(2000);
                    ByteBuffer buffer = ByteBuffer.allocate(256);
                    SocketAddress from = ready > 0 ?
                            receiver.receive(buffer) : null;

                    if (from == null) {
                        System.out.println("received=false");
                    } else {
                        buffer.flip();
                        String body =
                                StandardCharsets.UTF_8.decode(buffer).toString();
                        System.out.println("received=" + body);
                    }
                }
            } finally {
                membership.drop();
                System.out.println(
                        "membership-valid-after=" + membership.isValid());
            }
        }
    }
}
```

Biên dịch bằng Java 17:

```bash
javac ExplicitInterfaceMulticastDemo.java
```

Xem tên interface bằng ví dụ ở mục 6, sau đó **chỉ định tên thật**. Trên môi trường đã kiểm thử, loopback có tên `loopback_0`:

```bash
java ExplicitInterfaceMulticastDemo loopback_0
```

**Stdout đã kiểm chứng khi chạy với card `loopback_0` trên môi trường JDK 17:**

```text
selected-interface=loopback_0
membership-valid-before=true
sent-bytes=11
received=hello-group
membership-valid-after=false
```

Đừng mặc định máy Linux/macOS của bạn có `loopback_0`. Ví dụ `lo` chỉ đúng nếu inspector trên máy đó thực sự liệt kê `lo` với multicast và IPv4; không chọn card theo phỏng đoán.

**Điều kiện kết quả:** Packet có thể không trở về trên một số OS, container, VPN hoặc policy firewall dù code compile thành công. Chương trình khi không nhận trong 2 giây in `received=false`, vẫn gọi `drop()`. Khi gặp trường hợp đó, làm theo checklist ở mục 23; không đổi sang một interface phát ra LAN mà không kiểm soát.

## 13. Giải thích code gửi/nhận từng bước

Các bước trong ví dụ:
1. `NetworkInterface.getByName(args[0])` trả card **đúng tên do người chạy cung cấp**. Nếu không có sẽ là `null`, không fallback.
2. `nic.isUp()` xác định card đang bật; `supportsMulticast()` xác định capability; kiểm tra `Inet4Address` tránh dùng card IPv6-only cho một group IPv4.
3. `DatagramChannel.open(StandardProtocolFamily.INET)` tạo socket Datagram IPv4; khác với `INET6` dành cho IPv6.
4. Receiver đặt `SO_REUSEADDR` **trước `bind`** rồi bind ephemeral UDP port. `SO_REUSEADDR` không bắt buộc để test một receiver, nhưng tạo nền tảng giải thích multiple listeners.
5. Receiver bật loopback, chuyển sang **nonblocking** để dùng `Selector`.
6. Sender đặt `IP_MULTICAST_IF` rõ ràng; không giao quyền chọn outgoing interface cho routing default.
7. Sender đặt `TTL=0` để chỉ thử delivery nội bộ trên host, không phát packet qua mạng ngoài.
8. Receiver `join(group,nic)` nhận token `MembershipKey` đại diện đúng group/interface membership.
9. Sender gửi ByteBuffer có 11 bytes. `DatagramChannel.send` trả số bytes đã gửi vào datagram, **không phải số receiver đã nhận**.
10. Selector chờ readiness tối đa khoảng 2000 milliseconds; `receive(buffer)` điền datagram, trả `SocketAddress` nguồn hoặc `null` nếu chưa có packet.
11. `buffer.flip()` chuyển từ chế độ ghi bytes sang chế độ đọc bytes, rồi decode UTF-8.
12. `finally` gọi `membership.drop()`; sau đó try-with-resources đóng channels.

**Lưu ý:** `received=hello-group` kiểm tra data path **trong cấu hình thí nghiệm**, còn `membership-valid-after=false` kiểm tra lifecycle token. Hai dòng này là **hai kiểm tra khác nhau**, không suy rằng mọi packet queued trước `drop()` đã biến mất ngay lập tức.

## 14. Datagram boundaries và ByteBuffer

UDP multicast nhận **datagram**, không phải một TCP byte stream:
- Một lời gọi `send(ByteBuffer, target)` gửi một datagram nếu thành công.
- Receiver nhận tối đa lượng bytes mà `ByteBuffer` còn chỗ.
- Nếu buffer quá nhỏ, datagram có thể bị **cắt/truncate** theo semantics channel/platform; phần dư **không trở thành một datagram thứ hai**.
- Nếu dùng ByteBuffer có `position`/`limit` không đúng, decode có thể rỗng, thiếu hoặc chứa bytes cũ.

Chu trình đúng:

```java
ByteBuffer buffer = ByteBuffer.allocate(2048);
SocketAddress source = receiver.receive(buffer);
if (source != null) {
    buffer.flip();
    byte[] payload = new byte[buffer.remaining()];
    buffer.get(payload);
    processDatagram(source, payload);
}
```

Đây là **mảnh code**, cần `receiver` đã cấu hình, `processDatagram` do ứng dụng định nghĩa. Nếu vòng lặp nhận nhiều packets, phải `buffer.clear()` trước packet tiếp theo. Không tái sử dụng ByteBuffer mà quên `clear`.

**Giao thức ứng dụng** cần giới hạn kích thước datagram, magic/version, session ID, sequence number và payload schema nếu yêu cầu. Đừng nhận multicast untrusted rồi `deserialize` Java object một cách tùy tiện; tránh Java native deserialization với dữ liệu từ mạng.

## 15. Nhận có timeout: Selector thay cho blocking receive vô hạn

`DatagramChannel` khi mới mở mặc định ở **blocking mode**. `receive(buffer)` khi chưa có packet có thể chờ vô hạn. Với bài thực nghiệm/CI, không nên để test bị treo.

Một cách có kiểm soát:
1. `receiver.configureBlocking(false)`.
2. `Selector.open()`.
3. `receiver.register(selector, SelectionKey.OP_READ)`.
4. `selector.select(2000)` đợi readiness tối đa khoảng 2 giây.
5. Nếu không có dữ liệu, kết thúc thí nghiệm và cleanup.

```java
receiver.configureBlocking(false);
try (Selector selector = Selector.open()) {
    receiver.register(selector, SelectionKey.OP_READ);
    if (selector.select(2000) > 0) {
        ByteBuffer buffer = ByteBuffer.allocate(2048);
        SocketAddress from = receiver.receive(buffer);
        if (from != null) {
            buffer.flip();
            // xử lý bytes
        }
    }
}
```

Đây là mảnh code. `select(...)` có thể trả `0` do timeout hoặc wakeup/spurious reasons. Nếu xây event loop dài hạn, cần:
- Lặp cho đến deadline bằng `System.nanoTime()`.
- Duyệt và remove selected keys sau xử lý.
- Xử lý `ClosedChannelException` khi cancel/close.
- Đặt giới hạn packets mỗi vòng tránh một group flood làm starvation tasks khác.

**Không** trộn tùy tiện `DatagramSocket.setSoTimeout(...)` với `DatagramChannel.receive` NIO rồi giả định timeout được áp giống nhau. Ví dụ NIO dùng `Selector`; ví dụ `MulticastSocket` dùng `setSoTimeout` và blocking receive ở mục 20.

## 16. MembershipKey lifecycle: thứ cần dọn thật sự

`java.nio.channels.MembershipKey` biểu diễn membership của một multicast group trên interface tương ứng.

```text
receiver.join(group, nic)
      │
      ▼
MembershipKey valid = true
      │
      ├─ receiver có thể nhận datagrams group trên NIC đã join
      │
      ├─ membership.drop()
      │       └─ key.isValid() = false
      │
      └─ receiver.close()
              └─ mọi membership keys thuộc channel đều invalid
```

Theo Java 17 API:
- Key **valid ngay khi tạo**.
- Key còn valid cho đến khi gọi **`drop()`** hoặc **channel bị đóng**.
- `isValid()` trả trạng thái token membership, không phải “đã nhận được packet” hay “network chắc chắn hoạt động”.
- `drop()` rời group; nếu key đã invalid thì gọi lại **không có tác dụng** (idempotent ở trạng thái invalid).
- Sau `drop()`, channel có thể **join lại** group và nhận một **key mới**.
- Key invalid **không thể trở lại valid**.
- `drop()` **không đóng channel**; channel có thể tiếp tục hoạt động, nhận unicast hoặc groups khác.

### Một bẫy tinh vi: datagram đã buffer

Ngay sau `drop()`, đôi khi vẫn có thể nhận một datagram đã nằm trong socket receive buffer **trước khi rời nhóm**. Java 17 `MembershipKey.drop` có nêu rõ tình huống này. Vì vậy không viết test khẳng định “gọi drop xong thì receive chắc chắn trả null ngay lập tức”.

Bài test chuẩn hơn:
- `key.isValid() == false` sau `drop()`.
- Giữ một group khác vẫn valid nếu chỉ drop group đầu.
- Đóng channel khiến mọi membership keys của channel invalid.
- Không dùng số packets nhận ngay sau drop làm điều kiện duy nhất để xác nhận cleanup.

## 17. Cleanup đúng ngay cả khi sender/receiver lỗi

Mẫu:

```java
try (DatagramChannel receiver = DatagramChannel.open(
        StandardProtocolFamily.INET)) {
    receiver.bind(new InetSocketAddress(54321));
    MembershipKey key = receiver.join(group, nic);
    try {
        receiveAndProcess(receiver);
    } finally {
        key.drop();
    }
}
```

Đây là **mảnh code**, `group`, `nic`, `receiveAndProcess` cần định nghĩa.

Sự bảo vệ:
1. Nếu `receiver.join(...)` ném `IOException` hay `UnsupportedOperationException` **trước khi có key**, try-with-resources vẫn **đóng receiver**; không gọi `drop` trên biến chưa được gán.
2. Nếu `receiveAndProcess` ném exception, `finally` **drop membership**.
3. Sau đó outer try-with-resources vẫn **đóng receiver**, bảo đảm không giữ UDP socket.
4. Nếu dùng `Selector` và sender channel, chúng cũng nên nằm trong try-with-resources riêng.
5. Nếu toàn chương trình dùng một group và không cần giám sát trạng thái membership, chỉ đóng channel cũng sẽ invalidate key; **drop tường minh** vẫn rất hữu ích để thể hiện rõ ý định rời group **trước khi đóng socket**.

Đừng coi `drop()` là thay cho `DatagramChannel.close()`. Rời group không giải phóng tất cả file descriptors/UDP socket buffers mà channel đang giữ.

## 18. Thử hai group trong cùng channel rồi drop riêng từng membership

Một `DatagramChannel` có thể tham gia **nhiều nhóm** và nhận về nhiều `MembershipKey`. Nếu chỉ drop key của group A, key group B vẫn có thể valid.

Thí nghiệm thứ ba:
- `group1 = 239.255.42.42`.
- `group2 = 239.255.42.43`.
- Cả hai join cùng `NetworkInterface nic` trên một receiver.
- Drop `group1`, đọc `isValid()` của cả hai.
- Kết thúc try-with-resources, channel đóng; key group2 trở nên invalid **dù không gọi `drop` riêng**.

**Điều này minh họa sự khác biệt giữa “rời một nhóm” và “đóng mọi membership của channel”.** Không cần gửi multicast traffic; chỉ yêu cầu NIC/OS hỗ trợ join.

## 19. Chương trình Java 17 số 3: dọn đúng từng MembershipKey

Lưu file **`MembershipCleanupDemo.java`**:

```java
import java.net.*;
import java.nio.channels.*;
import java.util.*;

public class MembershipCleanupDemo {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Specify interface name");
        }

        NetworkInterface nic = NetworkInterface.getByName(args[0]);
        if (nic == null || !nic.isUp() || !nic.supportsMulticast()
                || Collections.list(nic.getInetAddresses()).stream()
                .noneMatch(ip -> ip instanceof Inet4Address)) {
            throw new IllegalArgumentException(
                    "Unusable multicast interface");
        }

        MembershipKey second;
        try (DatagramChannel receiver =
                DatagramChannel.open(StandardProtocolFamily.INET)) {
            receiver.setOption(StandardSocketOptions.SO_REUSEADDR, true);
            receiver.bind(new InetSocketAddress(0));

            MembershipKey first = receiver.join(
                    InetAddress.getByName("239.255.42.42"), nic);
            second = receiver.join(
                    InetAddress.getByName("239.255.42.43"), nic);

            System.out.println("first-before=" + first.isValid());
            System.out.println("second-before=" + second.isValid());

            first.drop();
            System.out.println("first-after-drop=" + first.isValid());
            System.out.println("second-still-valid=" + second.isValid());
        }

        System.out.println(
                "second-after-channel-close=" + second.isValid());
    }
}
```

Biên dịch và chạy sau khi đã tìm đúng tên interface:

```bash
javac MembershipCleanupDemo.java
java MembershipCleanupDemo loopback_0
```

**Stdout đã kiểm chứng trên máy test có interface `loopback_0`:**

```text
first-before=true
second-before=true
first-after-drop=false
second-still-valid=true
second-after-channel-close=false
```

Các điều đã được kiểm chứng:
- Sau hai `join`, cả hai keys `true`.
- `first.drop()` làm key đầu `false`.
- Key thứ hai vẫn `true` vì **drop group A không làm drop group B**.
- Khi `receiver.close()` được try-with-resources gọi, group B key chuyển `false`.

**Lưu ý scope test:** chương trình chứng minh lifecycle membership, **không** chứng minh delivery trên group2, không kiểm thử IGMP/router forwarding và không cần traffic ngoài máy.

### Nếu group2 join thất bại thì sao?

Trong code ngắn này, nếu `second = receiver.join(...)` ném exception, `first` vẫn còn valid cho tới khi outer try-with-resources **đóng receiver**. Theo contract, channel close làm key invalid, nên không rò membership. Trong hệ thống quản lý nhiều groups động, vẫn nên ghi nhận từng successful key vào collection và drop chúng trong cleanup để có kiểm soát lifecycle tường minh hơn.

## 20. API MulticastSocket cũ: joinGroup/leaveGroup với interface cụ thể

Ngoài NIO, Java có `java.net.MulticastSocket`. Java 17 vẫn hỗ trợ:
- `joinGroup(SocketAddress mcastaddr, NetworkInterface netIf)`.
- `leaveGroup(SocketAddress mcastaddr, NetworkInterface netIf)`.
- `setNetworkInterface(NetworkInterface)` cho outgoing multicast interface.
- `setTimeToLive(int)` cho TTL 0..255.
- `setSoTimeout(int)` cho blocking `receive` (có thể ném `SocketTimeoutException`).
- `close()` để đóng socket.

Trong Java 17, các phiên bản cũ `joinGroup(InetAddress)` và `leaveGroup(InetAddress)` đã được **deprecated**; nên dùng overload nhận `SocketAddress` và `NetworkInterface`, tránh selection ngầm định.

Một khác biệt với NIO:
- `DatagramChannel.join(group,nic)` trả về `MembershipKey` có thể `drop()`.
- `MulticastSocket.joinGroup(socketAddress,nic)` là lời gọi đăng ký; muốn rời nhóm thì gọi **`leaveGroup(socketAddress,nic)`** với đúng group/interface.

**Port trong `SocketAddress` của lời gọi `joinGroup` theo Java 17 được bỏ qua** vì lịch sử API, nhưng socket **vẫn phải bind đúng UDP listening port** để nhận datagrams. Trong ví dụ, `new InetSocketAddress(group, 0)` dùng làm identity nhóm khi join/leave; sender vẫn gửi đến `receiver.getLocalPort()` thật.

## 21. Chương trình Java 17 số 4: MulticastSocket và leaveGroup

Lưu file **`ClassicMulticastSocketDemo.java`**:

```java
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.Collections;

public class ClassicMulticastSocketDemo {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Interface name required");
        }
        NetworkInterface nic = NetworkInterface.getByName(args[0]);
        if (nic == null || !nic.isUp() || !nic.supportsMulticast() ||
                Collections.list(nic.getInetAddresses()).stream()
                .noneMatch(a -> a instanceof Inet4Address)) {
            throw new IllegalArgumentException(
                    "Interface unsuitable for IPv4 multicast");
        }

        InetAddress group = InetAddress.getByName("239.255.42.44");
        try (MulticastSocket receiver = new MulticastSocket(null);
             MulticastSocket sender = new MulticastSocket()) {
            receiver.setReuseAddress(true);
            receiver.bind(new InetSocketAddress(0));
            receiver.setSoTimeout(1500);

            SocketAddress membership = new InetSocketAddress(group, 0);
            receiver.joinGroup(membership, nic);
            try {
                sender.setNetworkInterface(nic);
                sender.setTimeToLive(0);

                byte[] bytes = "classic".getBytes(
                        StandardCharsets.UTF_8);
                sender.send(new DatagramPacket(
                        bytes, bytes.length,
                        group, receiver.getLocalPort()));

                byte[] buffer = new byte[100];
                DatagramPacket received = new DatagramPacket(
                        buffer, buffer.length);
                receiver.receive(received);

                System.out.println(
                        "selected-interface=" + nic.getName());
                System.out.println("received=" + new String(
                        received.getData(), received.getOffset(),
                        received.getLength(), StandardCharsets.UTF_8));
            } finally {
                receiver.leaveGroup(membership, nic);
                System.out.println("leave-group-called=true");
            }
        }
    }
}
```

Biên dịch:

```bash
javac ClassicMulticastSocketDemo.java
```

Chạy với interface thực trên máy test:

```bash
java ClassicMulticastSocketDemo loopback_0
```

**Stdout đã kiểm chứng trên interface `loopback_0`:**

```text
selected-interface=loopback_0
received=classic
leave-group-called=true
```

- `receiver.joinGroup(membership,nic)` chỉ rõ interface để **nhận** group.
- `sender.setNetworkInterface(nic)` chỉ rõ interface để **gửi**.
- `sender.setTimeToLive(0)` yêu cầu phát local.
- `receiver.setSoTimeout(1500)` tránh blocking receive vô hạn; nếu không có packet, sẽ ném `SocketTimeoutException`. **`finally` vẫn leave group**, rồi try-with-resources đóng sockets.
- `leave-group-called=true` xác nhận lời gọi `leaveGroup` đã **trả về thành công** trong test. Nó không chứng minh router/OS đã dọn mọi forwarding state trên mạng.

Khi so với `DatagramChannel`, API cổ điển phù hợp code truyền thống, còn NIO phù hợp ứng dụng có `Selector`, nonblocking I/O và nhu cầu quản lý nhiều channel.

## 22. So sánh hai API khi cần dọn membership

| Khía cạnh | `DatagramChannel` | `MulticastSocket` |
| --- | --- | --- |
| Join IPv4 group trên NIC | `join(group, nic)` | `joinGroup(new InetSocketAddress(group,0), nic)` |
| Token membership riêng | `MembershipKey` | Không trả token tương đương |
| Rời group tường minh | `key.drop()` | `leaveGroup(groupSocketAddress,nic)` |
| Đóng UDP resource | `channel.close()` | `socket.close()` |
| Chọn outgoing NIC | `setOption(IP_MULTICAST_IF,nic)` | `setNetworkInterface(nic)` |
| TTL | `setOption(IP_MULTICAST_TTL,0)` | `setTimeToLive(0)` |
| Loopback | `IP_MULTICAST_LOOP` | `setOption(IP_MULTICAST_LOOP,...)`; tránh deprecated `setLoopbackMode` |
| Blocking receive timeout | Dùng nonblocking + `Selector` nếu cần bounded wait | `setSoTimeout` + blocking `receive` |
| Data buffer | `ByteBuffer` | `DatagramPacket` chứa `byte[]` |
| Socket lifecycle | Try-with-resources | Try-with-resources |

**Không trộn** `DatagramChannel.join` và `MulticastSocket.leaveGroup` cho cùng membership. Đó là hai API quản lý membership theo socket khác nhau. Nếu source code dùng NIO, giữ key và drop key; nếu dùng MulticastSocket, lưu group + NIC và gọi leaveGroup tương ứng.

## 23. Nếu không nhận được multicast: checklist kiểm tra

Một test chạy nhưng in `received=false` hoặc ném `SocketTimeoutException` chưa chắc do bug Java. Thử theo thứ tự:

1. **Tên NIC:** `getByName` có trả đúng interface do bạn định dùng? Tên thuộc máy đang chạy, không phải tên từ máy khác.
2. **Trạng thái:** `isUp`, `supportsMulticast` và interface có IPv4? Nếu không, dừng với lỗi giải thích, **không tự fallback**.
3. **Group IP:** có thực sự là multicast? `group.isMulticastAddress()` nên `true`.
4. **Family:** IPv4 group dùng `StandardProtocolFamily.INET`, không vô tình chọn IPv6-only channel/NIC.
5. **Port:** Receiver bind UDP port gì? Sender gửi đến đúng port đó?
6. **Join:** `join(group,nic)` thực sự hoàn tất và key valid trước khi sender gửi? Nếu fail, xem exception.
7. **Outgoing NIC:** Sender đã đặt `IP_MULTICAST_IF=nic` chưa, hay OS chọn một card khác?
8. **Loopback:** Local test đã bật loopback và OS/NIC có hỗ trợ local multicast delivery chưa?
9. **TTL:** `0` là local-only; dùng giữa hai máy thì cần scope/hop policy khác, nhưng chỉ tăng khi đã được phép thử LAN.
10. **Firewall:** Host firewall có chặn UDP inbound/multicast không?
11. **Switch/AP:** IGMP snooping, Wi-Fi client isolation, multicast-to-unicast conversion có ảnh hưởng không?
12. **VPN/VM:** Route/interface ảo làm traffic đi sai miền hay chặn multicast?
13. **Container:** Network namespace có interface và multicast capability không? Loopback container khác loopback của host.
14. **Socket reuse:** Có process khác đã bind port? `SO_REUSEADDR` có được đặt trước bind và được OS hỗ trợ như mong muốn?
15. **Buffer:** ByteBuffer có đủ `remaining()`, đã `flip`/`clear` đúng chưa?
16. **Timing:** Receiver đã join **trước** khi sender gửi chưa? UDP không giữ packet cho người tham gia sau.
17. **Deadline:** Timeout 1500/2000 ms có quá ngắn trên CI chậm? Tăng có giới hạn, không bỏ timeout vô hạn.
18. **Protocol data:** Datagram gửi có payload hợp lệ? Ghi logs chiều dài/sequence ID an toàn, không log secrets.
19. **Địa chỉ nguồn:** Sender có source IP phù hợp interface? NIC/router có multicast egress/ingress policy?
20. **Membership cleanup:** Nếu test trước giữ socket/group, tiến trình cũ còn chạy có gây nhiễu không? Dừng nó đúng lifecycle.

**Không suy từ `supportsMulticast()==true` rằng firewall, router hoặc AP bắt buộc phải chuyển group tới mọi máy.** API chỉ nói capability của local interface, không kiểm tra toàn bộ mạng.

## 24. Khi nào nên chạy giữa hai máy thay vì loopback?

Local loopback test xác minh:
- Java APIs mở được channel/socket.
- NIC được chỉ định hợp lệ.
- `join`/`leaveGroup`/`drop` có lifecycle đúng.
- IP multicast loopback trên host hoạt động.
- Codec/ByteBuffer/DatagramPacket xử lý được payload.

Local test **không** xác minh:
- Network switch có IGMP snooping đúng.
- Router multicast forwarding được cấu hình.
- Firewall của máy khác mở UDP port.
- Phạm vi TTL/routing giữa VLANs.
- Group membership report đến router đúng thời điểm.
- Wi-Fi AP không cô lập clients.

Muốn thử hai máy trong mạng do bạn quản trị:
1. Chọn group `239.255.x.x` và port đã thống nhất, không đụng production traffic.
2. Trên mỗi máy, liệt kê NIC, chọn tên **riêng của máy**.
3. Receiver bind cùng UDP port và join group trên NIC kết nối đúng LAN.
4. Sender đặt outgoing NIC rõ, TTL phù hợp mạng cho phép (ví dụ 1 trong cùng LAN, tùy topology).
5. Gửi gói test nhỏ, có sequence ID, không chứa secrets.
6. Kiểm tra firewall, route và metrics ở cả hai máy.
7. Cleanup memberships/sockets sau test.

Ví dụ đầy đủ ở trên **cố tình dùng TTL=0**, nên chỉ kiểm tra cùng host. **Không nâng TTL thành 1 trong demo để “sửa” output** trừ khi bạn chủ động chuyển sang thí nghiệm network ngoài host.

## 25. Source-specific multicast và filter: phạm vi nâng cao

`MulticastChannel.join(group,nic)` là **Any-Source Multicast (ASM)** về mặt membership: có thể nhận packets tới group từ nhiều sources trong giới hạn mạng.

Java NIO cũng có overload:

```java
MembershipKey sourceSpecific =
        receiver.join(group, nic, sourceAddress);
```

Đây là **mảnh code**, `receiver`, `group`, `nic`, `sourceAddress` cần được chuẩn bị. Nó hướng tới **source-specific membership**, yêu cầu source address phù hợp family, là unicast, và **OS phải hỗ trợ source filtering**. Nếu không, API có thể ném `UnsupportedOperationException`.

Với non-source-specific key, `block(source)`/`unblock(source)` có thể lọc các sources nếu OS hỗ trợ. Không nên đưa source filtering vào bài thử đầu tiên:
- Làm tăng phụ thuộc OS/switch/router và source address binding.
- Dễ nhầm drop cả group với block một source.
- Không tạo cơ chế authentication: địa chỉ IP source vẫn không tương đương danh tính ứng dụng tin cậy.
- Semantics các packets **đã buffer trước filter** cần xử lý riêng.

Dù key là ASM hay source-specific, **`drop()` vẫn là thao tác rời membership**; đóng channel cũng invalidates keys.

## 26. IPv4 và IPv6 multicast khác nhau ở scope và interface

Ví dụ chính dùng IPv4:
- `StandardProtocolFamily.INET`.
- Group `239.255.42.42`.
- Card có `Inet4Address`.
- IPv4 TTL.

Nếu dùng IPv6:
- Chọn `StandardProtocolFamily.INET6`.
- Dùng group IPv6 multicast, ví dụ các dạng `ff02::...` cho **link-local scope** khi thích hợp và đúng group assignment.
- Card phải có IPv6 address, nhiều địa chỉ link-local IPv6 có **scope ID/interface**.
- `IP_MULTICAST_TTL` biểu diễn IPv6 **hop limit**, semantics gửi tới IPv4-mapped destination có thể phụ thuộc implementation.
- IPv6 multicast membership và network policy có thể khác IPv4; đừng chỉ thay string group rồi giữ nguyên mọi giả định.

**Không** viết chương trình chỉ kiểm tra `Inet4Address` rồi truyền vào group IPv6; không test IPv6 trên card không có địa chỉ IPv6. Với bài học một giao thức, giải quyết IPv4 đầy đủ trước, sau đó viết thí nghiệm IPv6 riêng với scope/network capabilities đã xác nhận.

## 27. Nhiều receiver, nhiều sender, nhiều group

Trong thực tế, một process có thể muốn:
- Một channel join nhiều groups.
- Nhiều channels join cùng group trên cùng NIC.
- Một sender gửi vào nhiều groups với cùng NIC.
- Nhiều interfaces tham gia cùng group.
- Stop một feature bằng cách drop **một** membership trong khi giữ channel/group khác.

Ví dụ nhóm membership:

```java
List<MembershipKey> memberships = new ArrayList<>();
try (DatagramChannel channel =
        DatagramChannel.open(StandardProtocolFamily.INET)) {
    channel.bind(new InetSocketAddress(54321));
    try {
        memberships.add(channel.join(groupA, nicA));
        memberships.add(channel.join(groupB, nicB));
        // Xử lý datagrams...
    } finally {
        for (MembershipKey key : memberships) {
            if (key != null && key.isValid()) {
                key.drop();
            }
        }
    }
}
```

Đây là **mảnh code**, không chạy độc lập; cần đúng imports, groupA/groupB/nicA/nicB, error handling. Nó minh họa một **collection of membership tokens** được dọn trong `finally`. Với production, mỗi group/interface có lifecycle, quota và access policy riêng; thêm khả năng rollback nếu join thứ hai thất bại.

**Cẩn thận:** Nếu source-specific và ASM membership xung đột trên cùng group/interface, `join` có thể báo `IllegalStateException`; không cứ thêm key vào collection là luôn thành công.

## 28. Các lỗi resource-lifecycle thường gặp

1. **Join xong bỏ mất MembershipKey:** Không thể drop một group cụ thể khi vẫn giữ channel. Giữ key trong cấu trúc ownership rõ.
2. **Chỉ gọi `key.drop()`, không close channel:** Rời group nhưng UDP channel/socket vẫn mở.
3. **Chỉ close channel, không ghi rõ ý định rời group:** OS cleanup vẫn xảy ra, nhưng khó quan sát lifecycle nhóm nếu app giữ socket phục vụ nhiều groups.
4. **Join rồi return trước finally:** Đường return/exception có thể rò membership. Đặt `drop` trong `finally`.
5. **Dùng `try (MembershipKey ...)`:** Không hợp lệ; MembershipKey không phải AutoCloseable.
6. **Drop group A rồi tưởng group B cũng rời:** Mỗi key/group riêng; test mục 19 cho thấy key B vẫn valid.
7. **Test rằng không còn packet ngay sau drop:** Packet đã queued có thể vẫn được đọc. Kiểm tra `isValid()` và lifecycle.
8. **Gọi leaveGroup trên sai interface:** Phải leave đúng group/interface đã join.
9. **Trộn NIO drop với MulticastSocket leave:** Hai API quản lý resource khác nhau.
10. **Không close Selector:** Selector cũng giữ tài nguyên; dùng try-with-resources.
11. **Thread nhận vẫn block khi shutdown:** Dùng nonblocking/Selector deadlines, wakeup/cancel và close hợp tác.
12. **Socket timeout bị hiểu như packet loss tuyệt đối:** No packet trong 2 giây không chứng minh mạng vĩnh viễn không chuyển.
13. **Không giới hạn kích thước/khối lượng datagrams:** Multicast flood có thể làm cạn CPU/heap; giới hạn payload và số packets xử lý mỗi vòng.

## 29. Những lỗi logic và bảo mật khi thử multicast

1. **Tự lấy interface đầu tiên** trong enumeration. Không có bảo đảm đúng card.
2. **Chọn card chỉ vì nó có IPv4.** Cần thêm `isUp`/`supportsMulticast`, policy và route phù hợp.
3. **Gọi IP_MULTICAST_IF ở receiver rồi tưởng đã join.** Nó chọn outgoing NIC, không đăng ký membership.
4. **Sender không đặt IP_MULTICAST_IF.** OS có thể chọn adapter sai, nhất là khi VPN/VM.
5. **Join IPv4 group trên INET6-only channel/NIC.** Sai family.
6. **Cho rằng multicast group là hostname cần DNS resolve.** Trong ví dụ group là numeric IP multicast, không dùng DNS host service discovery.
7. **Nhầm group IP với địa chỉ của receiver.** Sender gửi tới group, không đến một unicast receiver IP.
8. **Receiver bind sai port.** Group đúng không đủ; UDP destination port cũng phải khớp.
9. **Không bật loopback khi test cùng host.** Có thể không nhận gói tự gửi.
10. **TTL>0 khi chỉ muốn test local.** Packet có thể ra network; chọn TTL=0 khi mục tiêu là local-only.
11. **Tin TTL=0 luôn được loop back.** OS vẫn có thể không hỗ trợ; “may be delivered locally”.
12. **Nhầm SO_REUSEADDR với cơ chế fan-out portable.** Nhiều sockets cùng port có behaviors khác OS.
13. **Dùng blocking receive mà không có timeout/cancellation.** CI dễ treo mãi.
14. **Bỏ quên ByteBuffer.flip/clear.** Payload bị đọc sai hoặc datagram sau không có chỗ.
15. **Đọc datagram bằng buffer nhỏ rồi coi phần dư là packet sau.** UDP datagram có thể bị truncate.
16. **Gửi secret/API token qua nhóm test.** Multicast không tự xác thực hay mã hóa.
17. **Tin source IP là danh tính bảo mật.** Có thể giả mạo hoặc không đủ để authorize; cần protocol/app security.
18. **Cho rằng multicast đảm bảo delivery.** UDP không có ACK/retransmit mặc định.
19. **Dùng group chung của production cho test.** Có thể ảnh hưởng hệ thống khác; chọn group/port thí nghiệm.
20. **Chạy lan traffic khi chưa được phép.** Test loopback trước, chỉ dùng NIC/LAN thật khi có thẩm quyền.

## 30. Kiểm thử và cách đọc kết quả một cách khoa học

| Thử nghiệm | Kiểm chứng hợp lệ | Không được suy diễn |
| --- | --- | --- |
| Interface probe in `up=true/multicast=true/ipv4=true` | Local interface có các capability được báo | Network/firewall chắc chắn cho phép delivery |
| Sender có `IP_MULTICAST_IF=nic` | Code đã chọn NIC outgoing | Mọi packet thực sự ra ngoài bằng NIC này trong mọi OS policy |
| `join(group,nic)` trả key valid | Channel có membership token trên group/interface | Có receiver đã nhận một packet |
| Test gửi 11 bytes và nhận `hello-group` | Local multicast data path trong môi trường thử nghiệm hoạt động | LAN/routers/IPv6 multicast chắc chắn hoạt động |
| `key.drop()` rồi `isValid()==false` | Membership token đã invalid | Receive buffer ngay lập tức rỗng |
| Drop group1, group2 vẫn valid | Cleanup riêng theo membership | Group2 chắc chắn có datagrams |
| Close channel, key còn lại invalid | Channel close cleanup memberships | Mọi network router state biến mất tức thì |
| MulticastSocket `leaveGroup` trả về | Application gọi leave thành công | Mạng không còn bất cứ datagram queued nào |
| `Selector.select(2000)==0` | Không thấy readiness trong lần đợi | Network đã hỏng vĩnh viễn |
| `SocketTimeoutException` ở classic receive | Không nhận packet trong configured interval | Sender không gửi hoặc firewall là nguyên nhân duy nhất |

Để test repeatable:
- Bắt đầu receiver **trước** sender.
- Chọn group/nic/port minh bạch.
- Giới hạn thời gian chờ.
- Log **chỉ metadata** group/port/interface, length và status, không log secrets.
- Đo packet loss/truncation khi thử nhiều packets.
- Cleanup mọi key/socket/selector ngay cả khi timeout/exception.
- Nếu cần retry, dùng cùng protocol với sequence ID và xử lý duplicate, không mặc định “gửi lại luôn an toàn”.

## 31. Checklist thí nghiệm từng bước

**Chuẩn bị:**
1. Có JDK 17+, kiểm tra `java -version` và `javac -version`.
2. Chạy `InterfaceProbe282`, xác định card **đúng tên**; không dựa vào tên từ bài viết.
3. Xác nhận card up/multicast/IPv4. Với local test, xem loopback có hỗ trợ không.
4. Chọn group `239.255.42.42` và để TTL=0.
5. Đảm bảo không dùng port/group của ứng dụng khác; trong same-process test dùng port 0.

**Chạy:**
1. Biên dịch `ExplicitInterfaceMulticastDemo`, chạy với tên card chọn rõ.
2. Kiểm tra `membership-valid-before=true`, `sent-bytes=11` và nếu OS cho phép, `received=hello-group`.
3. Kiểm tra `membership-valid-after=false` dù nhận được hay không.
4. Biên dịch `MembershipCleanupDemo`, xác minh drop group1 không làm invalid group2 và close channel làm invalid group2.
5. Biên dịch `ClassicMulticastSocketDemo`, kiểm tra `leave-group-called=true` ở môi trường loopback hỗ trợ.

**Sau test:**
1. Không còn Java receiver process nào đang chạy nền.
2. Không còn UDP sockets/Selectors do chương trình giữ.
3. Mọi MembershipKey đã drop hoặc channel đã close.
4. Nếu test qua LAN, ngừng sender và cleanup group membership ở các receivers.
5. Không đưa dữ liệu mật vào logs hoặc payload.
6. Nếu chưa nhận packet, dùng checklist mục 23, **không** tăng TTL/hệ thống firewall một cách mù quáng.

## 32. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao bài thực nghiệm buộc truyền tên card qua command line?  
**Đáp án:** Để tránh OS/JVM chọn ngầm một adapter không phù hợp khi có Wi-Fi, Ethernet, VPN hoặc VM; lựa chọn trở nên rõ ràng và có thể debug.

**Câu 2.** `sender.setOption(IP_MULTICAST_IF,nic)` có làm sender join nhóm không?  
**Đáp án:** Không. Nó chọn outgoing multicast interface; `receiver.join(group,nic)` mới tạo membership cho receiver.

**Câu 3.** Vì sao chọn `StandardProtocolFamily.INET`?  
**Đáp án:** Ví dụ dùng IPv4 group `239.255.42.42`; `INET` phù hợp IPv4.

**Câu 4.** `join(group,nic)` trả về đối tượng gì?  
**Đáp án:** `MembershipKey`, token đại diện membership group trên interface đó.

**Câu 5.** Rời một membership bằng API NIO ra sao?  
**Đáp án:** Gọi `key.drop()`, thích hợp trong `finally`.

**Câu 6.** `drop()` có đóng channel không?  
**Đáp án:** Không. Channel còn mở; phải `channel.close()` khi không cần socket nữa.

**Câu 7.** Đóng channel mà chưa drop có invalid key không?  
**Đáp án:** Có. Java 17 contract nói channel close invalidates memberships.

**Câu 8.** Sau khi drop group A, group B có tự invalid không?  
**Đáp án:** Không. Group B key vẫn valid cho đến khi drop riêng hoặc channel đóng.

**Câu 9.** Vì sao đôi khi vẫn nhận packet ngay sau khi drop?  
**Đáp án:** Datagram đã nằm trong socket receive buffer trước khi drop vẫn có thể được đọc.

**Câu 10.** TTL 0 đảm bảo điều gì?  
**Đáp án:** IPv4 multicast datagram không được truyền lên network; **có thể** được giao nội bộ nếu OS hỗ trợ.

**Câu 11.** `IP_MULTICAST_LOOP=true` luôn đảm bảo local receiver nhận không?  
**Đáp án:** Không. Semantics tùy OS và các policy/adapter/receive path khác.

**Câu 12.** Receiver join đúng group nhưng bind UDP port khác sender gửi đến, có được packet không?  
**Đáp án:** Không thể kỳ vọng; destination UDP port phải trùng listening port.

**Câu 13.** Trong MulticastSocket, nên dùng API rời nhóm nào trên Java17?  
**Đáp án:** `leaveGroup(SocketAddress,NetworkInterface)` với group/interface đã join; tránh overload cũ deprecated.

**Câu 14.** Làm sao tránh Java test treo vì chưa nhận multicast?  
**Đáp án:** Với DatagramChannel dùng nonblocking + Selector timeout; với MulticastSocket dùng `setSoTimeout` và cleanup trong finally.

**Câu 15.** `supportsMulticast()==true` đã đủ khẳng định LAN cho phép multicast chưa?  
**Đáp án:** Chưa. OS firewall, switch/AP, VPN, router multicast topology vẫn ảnh hưởng.

**Câu 16.** Multicast có bảo đảm mọi receiver nhận cùng datagram không?  
**Đáp án:** Không. UDP là best-effort; cần application-level reliability nếu muốn delivery guarantee.

**Câu 17.** Vì sao `SO_REUSEADDR` nên đặt trước `bind` khi có nhiều receivers?  
**Đáp án:** Đó là yêu cầu/tập quán của nhiều OS cho reuse UDP port; hiệu lực vẫn phụ thuộc platform.

**Câu 18.** Vì sao test dùng group 239.255.x.x?  
**Đáp án:** Thuộc IPv4 Local Scope theo RFC2365, thích hợp cho phạm vi admin/local test; TTL0 mới giữ demo ở local host.

**Câu 19.** `MembershipKey.isValid` là chỉ số packet delivery?  
**Đáp án:** Không. Nó chỉ kiểm tra token membership còn hiệu lực hay không.

**Câu 20.** Để test multicast giữa hai máy, điều gì phải đổi?  
**Đáp án:** Chọn NIC thật trên từng máy, cùng group và UDP port, TTL/network/firewall policy phù hợp, và có quyền thực hiện thử nghiệm LAN. Demo TTL0 không dùng cho giữa hai máy.

## 33. Tổng kết nguyên tắc thực hành

Khi thử multicast trong Java 17, hãy ghi nhớ vòng đời:

```text
Chọn network interface có chủ đích
     ↓
Kiểm tra up + multicast capability + address family
     ↓
Mở receiver DatagramChannel, bind UDP port
     ↓
MembershipKey = receiver.join(group, selectedInterface)
     ↓
Mở sender và set IP_MULTICAST_IF = selectedInterface
     ↓
Set IP_MULTICAST_TTL = 0 cho local-only test
     ↓
Send UDP datagram, nhận với bounded timeout
     ↓
finally: membership.drop()
     ↓
try-with-resources: close selector + sender + receiver
```

Đây là trình tự mẫu. Trong hệ thống nhiều groups, lưu nhiều MembershipKeys và dọn từng key đúng ownership; đóng channel cuối cùng sẽ invalidates những keys còn lại. Với `MulticastSocket`, chuyển cặp `joinGroup/leaveGroup` tương ứng.

**Kết luận cốt lõi:** **Chọn đúng interface** giúp packet đi/được nhận trên đúng mạng; **giữ và drop membership** giúp ứng dụng rời nhóm có kiểm soát; **close socket/channel** giải phóng resource. Không dùng một thao tác để suy rằng hai thao tác còn lại đã được thực hiện theo đúng ý định nghiệp vụ.

## 34. Tài liệu chính thức và chuẩn liên quan

- Java SE 17 `DatagramChannel` — mở channel theo protocol family, send/receive, các socket options: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/DatagramChannel.html
- Java SE 17 `MulticastChannel` — `join(group,interface)`, source-specific multicast: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/MulticastChannel.html
- Java SE 17 `MembershipKey` — `drop()`, `isValid()`, buffered datagrams sau drop: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/MembershipKey.html
- Java SE 17 `NetworkInterface` — `getByName`, `isUp`, `supportsMulticast`, IP addresses: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/NetworkInterface.html
- Java SE 17 `StandardSocketOptions` — `IP_MULTICAST_IF`, `IP_MULTICAST_TTL`, `IP_MULTICAST_LOOP`, `SO_REUSEADDR`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/StandardSocketOptions.html
- Java SE 17 `MulticastSocket` — `joinGroup`/`leaveGroup` chọn interface, `setNetworkInterface`, `setTimeToLive`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/MulticastSocket.html
- Java SE 17 `Selector` và `SelectionKey` — nonblocking receive và timeout: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html
- Java SE 17 `DatagramPacket` — datagram content buffer/offset/length: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/DatagramPacket.html
- RFC 2365 — Administratively Scoped IPv4 Multicast, `239.255.0.0/16` Local Scope: https://www.rfc-editor.org/rfc/rfc2365
