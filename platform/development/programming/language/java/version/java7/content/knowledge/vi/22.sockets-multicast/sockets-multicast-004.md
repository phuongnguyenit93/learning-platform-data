# DatagramChannel trong Java: Chọn họ giao thức khi mở kênh UDP

## 1. Bài toán và mục tiêu học tập

`DatagramChannel` là kênh giao tiếp theo datagram của Java NIO.2, có từ Java 7 và **vẫn còn được sử dụng trong Java 17+**. Khi tạo một kênh UDP, bạn có thể để hệ thống chọn họ giao thức hoặc **chỉ định rõ IPv4 hay IPv6 ngay lúc mở**. Sự lựa chọn đặc biệt quan trọng nếu ứng dụng tham gia **IP multicast**, bởi loại socket của kênh phải tương ứng với loại địa chỉ multicast group mà kênh muốn tham gia.

Có hai lời gọi dễ bị nhầm:

```java
DatagramChannel defaultChannel = DatagramChannel.open();

DatagramChannel ipv4Channel =
        DatagramChannel.open(StandardProtocolFamily.INET);

DatagramChannel ipv6Channel =
        DatagramChannel.open(StandardProtocolFamily.INET6);
```

Đây là ba **đoạn minh họa** cần đặt trong phương thức xử lý `IOException` và đóng từng channel khi không còn sử dụng. Chúng **không tương đương** về mặt cam kết của Java API.

**Ý chính:**

- `DatagramChannel.open()`: họ giao thức của socket **không được đặc tả**; phụ thuộc nền tảng/cấu hình. Không dựa vào nó để bảo đảm IPv4 hay IPv6.
- `DatagramChannel.open(StandardProtocolFamily.INET)`: yêu cầu socket thuộc họ **IPv4**.
- `DatagramChannel.open(StandardProtocolFamily.INET6)`: yêu cầu socket thuộc họ **IPv6**; có thể không được nền tảng hỗ trợ.
- Đối với **multicast**, hãy chọn `INET` khi group là `Inet4Address`, chọn `INET6` khi group là `Inet6Address`.
- `StandardProtocolFamily.UNIX` có trong Java hiện đại nhưng **không dùng được cho `DatagramChannel`** theo Java SE 17; Unix-domain sockets được sử dụng trong các kênh socket khác, không biến UDP thành Unix datagrams.
- Sau khi đã mở, bạn không dùng `setOption(...)` để “chuyển” socket từ IPv4 thành IPv6. `IP_MULTICAST_IF` chọn **network interface**, không chọn **protocol family**.
- Loại giao thức đúng vẫn **không bảo đảm** multicast hoạt động: cần cấu hình network interface, bind phù hợp, membership, route, firewall và khả năng của hệ điều hành.

Bài học tập trung vào **“Chọn họ giao thức khi mở DatagramChannel”** thuộc chủ đề cha **“Socket và multicast”**. Nội dung cập nhật cho Java 17+, không dựa vào các thực hành lỗi thời.

## 2. ProtocolFamily, StandardProtocolFamily và loại địa chỉ

### 2.1. `ProtocolFamily` là gì?

`java.net.ProtocolFamily` là interface đại diện cho **một họ giao thức truyền thông**. Các giá trị chuẩn do enum `java.net.StandardProtocolFamily` cung cấp.

| `StandardProtocolFamily` | Ý nghĩa | Kết hợp thông thường |
| --- | --- | --- |
| `INET` | Họ Internet Protocol phiên bản 4 (IPv4) | `Inet4Address`, group IPv4, `127.0.0.1` |
| `INET6` | Họ Internet Protocol phiên bản 6 (IPv6) | `Inet6Address`, group IPv6, `::1` |
| `UNIX` | Unix-domain local IPC (được thêm vào Java 16) | Một số socket channels; **không hỗ trợ trong `DatagramChannel`** |

Hãy phân biệt `ProtocolFamily` với:
- **Giao thức vận chuyển**: `DatagramChannel` làm việc với datagrams/UDP, không phải TCP.
- **Loại địa chỉ**: `Inet4Address` và `Inet6Address` biểu diễn IPv4/IPv6.
- **Network interface**: card/adapter hoặc interface logic của hệ điều hành, dùng để chọn nơi gửi/nhận multicast.
- **Multicast group**: một địa chỉ IP multicast mà các socket có thể xin tham gia.

Hai đối tượng `INET` và `INET6` không phải port numbers; một địa chỉ multicast có cả family lẫn IP address. Port là một phần khác của `InetSocketAddress`.

### 2.2. Khác nhau giữa `Inet4Address` và `Inet6Address`

```java
InetAddress ipv4 = InetAddress.getByName("127.0.0.1");
InetAddress ipv6 = InetAddress.getByName("::1");

System.out.println(ipv4 instanceof Inet4Address); // true
System.out.println(ipv6 instanceof Inet6Address); // true
```

Đây là **minh họa** có import `java.net.*`; các literal ở đây là địa chỉ số, không phải hostname cần DNS. Nếu hệ thống dùng hostname, resolution có thể trả **IPv4 hoặc IPv6** tùy DNS và cấu hình. Vì vậy không “đoán family” từ một hostname hay từ `address.toString().contains(":")`.

Cách an toàn để phân loại là kiểm tra kiểu `InetAddress` đã được resolve:

```java
static StandardProtocolFamily familyOf(InetAddress address) {
    if (address instanceof Inet4Address) {
        return StandardProtocolFamily.INET;
    }
    if (address instanceof Inet6Address) {
        return StandardProtocolFamily.INET6;
    }
    throw new IllegalArgumentException("Unknown IP address type");
}
```

Đây là method minh họa có thể đưa vào class import `java.net.*`.

### 2.3. Không chọn family chỉ dựa vào chuỗi IP

Ví dụ một hostname như `service.internal` có thể:
- Có bản ghi `A` (IPv4).
- Có bản ghi `AAAA` (IPv6).
- Có cả hai loại và thứ tự do hệ thống chọn.
- Thay đổi IP theo môi trường hoặc thời gian.

Nếu ứng dụng thực sự cần tương thích một family duy nhất, hãy **resolve, phân loại địa chỉ và mở channel phù hợp**. Với multicast, địa chỉ group thường là địa chỉ IP cụ thể, không nên dùng tên mơ hồ mà không kiểm chứng kết quả resolve.

## 3. Hai overload `DatagramChannel.open`: mặc định hay chọn rõ family?

### 3.1. `DatagramChannel.open()`

```java
try (DatagramChannel channel = DatagramChannel.open()) {
    // Họ giao thức của socket phụ thuộc nền tảng/cấu hình.
}
```

Oracle Java SE 17 nêu rõ `ProtocolFamily` của socket được mở bởi overload không tham số **platform-dependent and unspecified**. Vì vậy:

- Không khẳng định đây luôn là IPv4.
- Không khẳng định đây luôn là IPv6.
- Không suy từ việc chạy thành công trên laptop này rằng máy khác nhận multicast IPv4/IPv6 giống hệt.
- Các system properties liên quan đến IPv4/IPv6 stack có thể ảnh hưởng cách provider lựa chọn hoặc hỗ trợ họ giao thức.

Overload không tham số vẫn **hữu ích cho một số bài toán unicast thông thường** khi không cần ràng buộc family. Nhưng Java API khuyến nghị dùng overload có `ProtocolFamily` cho **IP multicasting**.

### 3.2. `DatagramChannel.open(ProtocolFamily family)`

```java
try (DatagramChannel ipv4 =
        DatagramChannel.open(StandardProtocolFamily.INET)) {
    // Socket được yêu cầu thuộc họ IPv4.
}

try (DatagramChannel ipv6 =
        DatagramChannel.open(StandardProtocolFamily.INET6)) {
    // Socket được yêu cầu thuộc họ IPv6.
}
```

Kênh mới tạo ở trạng thái **open nhưng chưa connected**. Đây không phải việc gọi `bind`, `connect` hoặc `join` tự động; các bước đó thuộc lifecycle tiếp theo.

Nếu provider/platform không hỗ trợ family yêu cầu—ví dụ IPv6 chưa được bật—`open(family)` có thể ném `UnsupportedOperationException`. Cũng có thể gặp `IOException` do I/O lỗi. Không silently đổi sang family khác khi nghiệp vụ cần multicast đúng loại địa chỉ.

### 3.3. Bảng lựa chọn

| Nhu cầu | Lời gọi nên cân nhắc | Lý do |
| --- | --- | --- |
| UDP unicast IPv4 xác định | `open(INET)` | Không phụ thuộc default family |
| UDP unicast IPv6 xác định | `open(INET6)` | Kênh dùng IPv6 khi được hỗ trợ |
| Nhận group multicast IPv4 | **`open(INET)`** | Khớp `Inet4Address` của group |
| Nhận group multicast IPv6 | **`open(INET6)`** | Khớp `Inet6Address` của group |
| Unicast đơn giản, family không phải ràng buộc | `open()` có thể phù hợp | Chấp nhận provider chọn family |
| Unix-domain datagram bằng `DatagramChannel` | **Không hỗ trợ** | JDK 17 ghi rõ Unix domain sockets không hỗ trợ ở overload này |

**Mục tiêu của việc chọn rõ family là tính đúng và tính portable theo contract**, không phải bằng chứng throughput sẽ cao hơn `open()`.

## 4. Multicast: chọn family theo chính địa chỉ group

### 4.1. Quy tắc khớp loại địa chỉ

Với IP multicast:

```text
Group là Inet4Address (ví dụ 239.255.0.1)
     ↓
DatagramChannel.open(StandardProtocolFamily.INET)

Group là Inet6Address (ví dụ ff02::1)
     ↓
DatagramChannel.open(StandardProtocolFamily.INET6)
```

Lý do: tài liệu `MulticastChannel` nói **không bảo đảm** một kênh thuộc family này có thể join/receive group thuộc family khác. Đặc biệt việc dùng IPv6 socket để nhận một group IPv4 là **implementation-specific**.

Do đó không lấy “IPv6 là giao thức mới hơn” làm lý do luôn mở `INET6` rồi join tất cả group IPv4. Mọi giải pháp dựa trên dual-stack và IPv4-mapped addresses phải được kiểm chứng riêng theo OS/provider; **không phải hợp đồng portable cho multicast**.

### 4.2. Helper kiểm tra group trước khi chọn family

```java
static StandardProtocolFamily familyForGroup(
        InetAddress group) {

    if (!group.isMulticastAddress()) {
        throw new IllegalArgumentException(
                "Not a multicast address");
    }

    if (group instanceof Inet4Address) {
        return StandardProtocolFamily.INET;
    }

    if (group instanceof Inet6Address) {
        return StandardProtocolFamily.INET6;
    }

    throw new IllegalArgumentException(
            "Unsupported address type");
}
```

Phương thức trên:
1. Xác nhận `group` là **multicast address**.
2. Kiểm tra family bằng kiểu địa chỉ của Java.
3. Trả `INET` hoặc `INET6`.
4. Fail-fast nếu input không đúng thay vì mở nhầm socket.

Method này chỉ **chọn family**, **không tự join group** và **không kiểm tra network interface có thực sự nhận được multicast hay không**. Nếu đầu vào `null`, chương trình thực tế cần policy riêng (ví dụ `Objects.requireNonNull`) thay vì để `NullPointerException` phát sinh ngẫu nhiên.

### 4.3. Một số dải địa chỉ

- IPv4 multicast thuộc dải `224.0.0.0/4`.
- IPv6 multicast dùng tiền tố `ff00::/8`; byte thấp trong phần flags/scope có ý nghĩa về phạm vi.
- `127.0.0.1` và `::1` là **loopback unicast**, không phải multicast groups.
- Đừng chọn group số tùy ý cho production mà chưa xác minh vùng địa chỉ được phép, scope/assignment và thiết kế mạng.
- `InetAddress.isMulticastAddress()` kiểm tra loại địa chỉ; **không cấp quyền** dùng địa chỉ đó trên mạng.

Trong ví dụ runnable, chúng ta chỉ **phân loại** hai địa chỉ multicast tượng trưng; không gửi multicast ra hệ thống mạng của người dùng.

## 5. Chọn family là bước đầu, không phải toàn bộ cấu hình multicast

### 5.1. NetworkInterface dùng để chọn tuyến nhận/gửi

`DatagramChannel.join(InetAddress group, NetworkInterface interf)` cần một `NetworkInterface` thực sự phù hợp. Việc chọn family không tự tìm interface mong muốn trong máy đa card mạng (Wi-Fi, Ethernet, VPN, container, virtual adapters).

Ví dụ:

```java
NetworkInterface ni =
        NetworkInterface.getByInetAddress(localAddress);

if (ni == null || !ni.isUp() || !ni.supportsMulticast()) {
    throw new IOException("No suitable multicast interface");
}
```

Đây là **mã minh họa**; `localAddress` cần được xác định bởi người quản trị/cấu hình hoặc lựa chọn giao diện hợp lệ. Không đảm bảo interface “đầu tiên trong danh sách” sẽ tương ứng mạng có group.

`supportsMulticast()` báo đặc tính của interface; nó **không chứng minh** router, firewall hoặc thiết bị phía bên kia sẽ chuyển gói tới socket.

### 5.2. Bind wildcard khi nhận multicast

Tài liệu `MulticastChannel` khuyến nghị bind socket với **wildcard address**, vì khả năng nhận multicast khi bind một IP cụ thể phụ thuộc implementation.

```java
channel.bind(new InetSocketAddress(port));
```

Đây là cách bind đến wildcard trên port đã chọn, không tự cấu hình `group`; `join` thực hiện phần membership. Với IPv6 link-local multicast cần chú ý scope và interface phù hợp.

### 5.3. `SO_REUSEADDR` trước khi bind

Nếu nhiều tiến trình/thành viên cần bind cùng địa chỉ/port, `MulticastChannel` khuyến nghị:

```java
channel.setOption(
        StandardSocketOptions.SO_REUSEADDR, true);
channel.bind(new InetSocketAddress(port));
```

**Đặt option trước bind.** Tuy nhiên, `SO_REUSEADDR` không đảm bảo trên mọi OS sẽ cho mọi tổ hợp chương trình dùng chung cổng; semantics và security có thể phụ thuộc nền tảng. `SO_REUSEPORT` (nếu có) là option khác, không phải mặc định cần sử dụng để “chữa” family mismatch.

### 5.4. `IP_MULTICAST_IF` chọn outgoing interface, không chọn IPv4/IPv6

```java
channel.setOption(
        StandardSocketOptions.IP_MULTICAST_IF, ni);
```

Option này chọn network interface dùng cho **multicast datagrams gửi đi**. Nó **không thay đổi họ giao thức** của socket. Đừng hiểu `IP_MULTICAST_IF=eth0` là kênh tự chuyển từ `INET6` sang `INET`.

Mặt khác `join(group, ni)` chỉ rõ interface cần tham gia group **để nhận**. Hai lựa chọn liên quan nhưng không thay thế nhau.

### 5.5. TTL, loopback và phạm vi multicast

```java
channel.setOption(
        StandardSocketOptions.IP_MULTICAST_TTL, 1);

channel.setOption(
        StandardSocketOptions.IP_MULTICAST_LOOP, true);
```

`IP_MULTICAST_TTL` liên quan hop limit của multicast; ý nghĩa và phạm vi thực tế phụ thuộc family/platform. `IP_MULTICAST_LOOP` điều khiển việc loopback multicast theo contract. Đây không phải các phép “bật multicast toàn mạng” hay cam kết gói tin vượt router.

Đừng dùng tăng TTL để thay cho thiết kế scope, routing và policy. Đối với IPv6 link-local multicast, interface/scope của địa chỉ đích cũng là yếu tố quan trọng.

## 6. Tham gia và rời một nhóm multicast

Sau khi chọn family và interface:

```java
try (DatagramChannel channel =
        DatagramChannel.open(familyForGroup(group))) {

    channel.setOption(
            StandardSocketOptions.SO_REUSEADDR, true);

    channel.bind(new InetSocketAddress(port));

    MembershipKey membership = channel.join(group, networkInterface);

    try {
        // Dùng receive(...) hoặc Selector để nhận datagrams.
        // Handler thật phải kiểm tra kích thước và format gói.
    } finally {
        membership.drop();
    }
}
```

Đây là **skeleton minh họa**, các biến `group`, `port` và `networkInterface` phải được chọn/cấp bởi ứng dụng. Đoạn này chỉ minh họa cấu hình và vòng đời membership, không phải một service nhận gói đầy đủ.

- `join(group, networkInterface)` trả `MembershipKey` đại diện cho tư cách thành viên.
- `membership.drop()` rời group cho membership ấy.
- Đóng channel cũng làm các memberships của channel bị hủy và keys trở nên invalid.
- Một channel có thể tham gia nhiều groups và cùng group trên nhiều interfaces theo khả năng của provider.
- `join(group, iface, source)` hỗ trợ **source-specific multicast** khi platform có source filtering; có thể ném `UnsupportedOperationException` nếu không hỗ trợ.
- Với source filtering, source address phải phù hợp family/group và policy; **không dùng source-specific join làm “bộ lọc an ninh” duy nhất**.

Lưu ý `DatagramChannel` là selectable channel nên có thể dùng blocking hoặc nonblocking và `Selector`. Điều này không làm UDP trở thành reliable stream: datagrams vẫn có thể mất, trùng, thay thứ tự, hoặc bị loại ở tầng mạng.

## 7. IPv4 và IPv6 không nên được trộn dựa vào may mắn dual-stack

Một hệ điều hành có thể hỗ trợ dual-stack IPv4/IPv6 và cho một số thao tác unicast xuyên family, nhưng Java API **không hứa** mọi tổ hợp.

Một vài cách cấu hình dễ gây hiểu nhầm:

- `-Djava.net.preferIPv4Stack=true` là system property ảnh hưởng khả năng IPv4 stack theo runtime/platform; không phải một lệnh chuyển family tùy ý giữa chừng.
- `-Djava.net.preferIPv6Addresses=true` có thể ảnh hưởng cách chọn địa chỉ từ hostname; không có nghĩa mọi socket đều tự tham gia được nhóm IPv6.
- Một kênh `INET6` có thể gặp triển khai IPv4-mapped addresses, nhưng việc nhận group **IPv4 multicast bằng IPv6 socket** không được bảo đảm.
- Máy có địa chỉ IPv6 không chắc interface đó hỗ trợ IPv6 multicast theo route/phạm vi đích mong muốn.
- Trên một số môi trường, `INET6` không được bật; `open(INET6)` có thể ném `UnsupportedOperationException`.

**Mẫu quyết định:** bắt đầu từ group (đã resolve ra `InetAddress`), kiểm tra `isMulticastAddress`, chọn `StandardProtocolFamily` cùng loại, sau đó chọn interface, bind/join, và đo đạc/kiểm thử trên hệ điều hành thực.

## 8. Unicast, connected UDP và lựa chọn family

### 8.1. Gửi/nhận không cần connect

`DatagramChannel` mới mở chưa connected nhưng có thể dùng:

```java
sender.send(
        ByteBuffer.wrap(
                "hi".getBytes(StandardCharsets.UTF_8)),
        destination);

SocketAddress from = receiver.receive(buffer);
```

Đây là **snippet minh họa**; `sender`/`receiver` là channels đã mở, `destination` là `SocketAddress` đúng family và `buffer` có đủ dung lượng. `send` nhận địa chỉ đích, `receive` trả địa chỉ nguồn khi có datagram.

### 8.2. `connect` UDP không phải handshake TCP

`DatagramChannel.connect(peer)` giới hạn remote peer mà channel trao đổi theo semantics của UDP connected socket. Nó **không tạo một kết nối tin cậy như TCP** và không xác nhận peer sẽ nhận được dữ liệu. Sau connect, các phương thức `read`/`write` không nhận địa chỉ socket có thể được dùng; trước connect, chúng không phù hợp với cùng vai trò này.

### 8.3. Sai family thường bị phát hiện ở bind/connect/send

Ví dụ kênh mở bằng `INET` nhưng ứng dụng cố bind/gửi bằng địa chỉ IPv6 có thể dẫn tới lỗi kiểu địa chỉ không hỗ trợ như `UnsupportedAddressTypeException` hoặc `IOException`, tùy thao tác/provider. **Đừng bắt mọi exception và mặc nhiên fallback sang một family khác** nếu đang tham gia multicast cụ thể—đó có thể che lỗi cấu hình.

### 8.4. Nonblocking UDP và Selector

`DatagramChannel.configureBlocking(false)` cho phép đăng ký `SelectionKey.OP_READ` trên `Selector`. `receive(buffer)` có thể trả `null` khi không có datagram trong chế độ nonblocking. `Selector.select(timeout)` giúp tránh chờ vô hạn trong bài kiểm thử.

Chọn family xảy ra **khi mở channel**, không phụ thuộc việc sau này chọn blocking hay nonblocking.

## 9. Chương trình Java 17+ độc lập đã kiểm thử

Chương trình sau thực hiện đúng nội dung bài học mà **không phụ thuộc nhận multicast thực từ router**:

1. Tạo hai địa chỉ multicast dạng bytes: một `Inet4Address` (239.255.0.1) và một `Inet6Address` (ff02::1).
2. Dùng `familyForGroup` để chọn `INET`/`INET6`.
3. Xác nhận một địa chỉ unicast `127.0.0.1` bị từ chối nếu đưa vào helper dành cho multicast group.
4. Mở **hai UDP channels IPv4** bằng `DatagramChannel.open(INET)`.
5. Bind receiver trên `127.0.0.1` với **port 0** để OS tự cấp cổng tạm.
6. Đặt receiver nonblocking, dùng `Selector` đợi tối đa 3 giây cho datagram.
7. Dùng sender gửi chuỗi `PING` tới địa chỉ receiver, nhận lại nội dung để xác minh.
8. Kiểm tra local address thuộc `Inet4Address`.
9. Kiểm tra JDK 17 từ chối `DatagramChannel.open(UNIX)` bằng `UnsupportedOperationException`.
10. Assert tất cả điều kiện rồi in `checks=PASS`.

Điểm quan trọng: **hai địa chỉ multicast chỉ được phân loại, không có lệnh `join` hoặc gửi multicast**. Vì vậy ví dụ kiểm thử được family selection mà không cần chọn NIC hoặc router thật. UDP loopback thường hoạt động trên máy lập trình, nhưng có thể bị hạn chế bởi sandbox/firewall/provider; nếu môi trường cấm loopback datagram thì chương trình sẽ báo lỗi I/O chứ không giả vờ thành công.

Lưu tệp **`DatagramProtocolFamilyDemo.java`**:

```java
import java.io.IOException;
import java.net.*;
import java.nio.ByteBuffer;
import java.nio.channels.*;
import java.nio.charset.StandardCharsets;

public final class DatagramProtocolFamilyDemo {
    static StandardProtocolFamily familyForGroup(InetAddress group) {
        if (!group.isMulticastAddress()) {
            throw new IllegalArgumentException("Not a multicast address");
        }
        if (group instanceof Inet4Address) {
            return StandardProtocolFamily.INET;
        }
        if (group instanceof Inet6Address) {
            return StandardProtocolFamily.INET6;
        }
        throw new IllegalArgumentException("Unsupported address type");
    }

    static void check(boolean condition, String label) {
        if (!condition) throw new AssertionError(label);
    }

    public static void main(String[] args) throws IOException {
        InetAddress group4 = InetAddress.getByAddress(
                new byte[] {(byte) 239, (byte) 255, 0, 1});

        byte[] ipv6 = new byte[16];
        ipv6[0] = (byte) 0xff;
        ipv6[1] = 0x02;
        ipv6[15] = 0x01;
        InetAddress group6 = InetAddress.getByAddress(ipv6);

        StandardProtocolFamily selected4 = familyForGroup(group4);
        StandardProtocolFamily selected6 = familyForGroup(group6);

        boolean rejected = false;
        try {
            familyForGroup(InetAddress.getByName("127.0.0.1"));
        } catch (IllegalArgumentException expected) {
            rejected = true;
        }

        System.out.println("group4.family=" + selected4);
        System.out.println("group6.family=" + selected6);
        System.out.println("nonMulticast.rejected=" + rejected);

        InetAddress loopback4 = InetAddress.getByName("127.0.0.1");

        String received;
        int sent;
        boolean localIPv4;

        try (DatagramChannel receiver =
                    DatagramChannel.open(StandardProtocolFamily.INET);
             DatagramChannel sender =
                    DatagramChannel.open(StandardProtocolFamily.INET);
             Selector selector = Selector.open()) {

            receiver.bind(new InetSocketAddress(loopback4, 0));

            localIPv4 =
                    ((InetSocketAddress) receiver.getLocalAddress())
                    .getAddress() instanceof Inet4Address;

            receiver.configureBlocking(false);
            receiver.register(selector, SelectionKey.OP_READ);

            ByteBuffer outbound = ByteBuffer.wrap(
                    "PING".getBytes(StandardCharsets.US_ASCII));

            sent = sender.send(outbound, receiver.getLocalAddress());

            if (selector.select(3000) == 0) {
                throw new IOException("No UDP datagram within deadline");
            }

            ByteBuffer inbound = ByteBuffer.allocate(64);
            SocketAddress actualSender = receiver.receive(inbound);

            if (actualSender == null) {
                throw new IOException(
                        "No datagram after readiness event");
            }

            inbound.flip();
            received = StandardCharsets.US_ASCII
                    .decode(inbound).toString();
        }

        System.out.println("unicast.bytesSent=" + sent);
        System.out.println("unicast.received=" + received);
        System.out.println("unicast.localIPv4=" + localIPv4);

        boolean unixUnsupported = false;

        try (DatagramChannel unused =
                DatagramChannel.open(StandardProtocolFamily.UNIX)) {
            // Java SE 17 DatagramChannel does not support UNIX sockets.
        } catch (UnsupportedOperationException expected) {
            unixUnsupported = true;
        }

        System.out.println(
                "unix.datagramUnsupported=" + unixUnsupported);

        check(selected4 == StandardProtocolFamily.INET
                && selected6 == StandardProtocolFamily.INET6
                && rejected
                && sent == 4
                && localIPv4
                && received.equals("PING")
                && unixUnsupported,
                "DatagramChannel family selection");

        System.out.println("checks=PASS");
    }
}
```

Chạy với JDK 17+:

```bash
javac -encoding UTF-8 DatagramProtocolFamilyDemo.java
java DatagramProtocolFamilyDemo
```

**Stdout chính xác trong lần chạy thử đã kiểm chứng bằng `javac`/`java`:**

```text
group4.family=INET
group6.family=INET6
nonMulticast.rejected=true
unicast.bytesSent=4
unicast.received=PING
unicast.localIPv4=true
unix.datagramUnsupported=true
checks=PASS
```

### 9.1. Vì sao có `group6.family=INET6` dù ví dụ không mở IPv6 socket?

Bởi method `familyForGroup` dựa vào **kiểu địa chỉ `Inet6Address`**, không phụ thuộc việc máy hiện tại có thể bind/join IPv6 multicast hay không. Đây chỉ là quyết định lựa chọn family cần có khi ứng dụng chuẩn bị thực hiện bước mạng.

**Đừng diễn giải dòng đó thành “hệ thống đã nhận multicast IPv6 thành công”.** Để kiểm chứng nhận thực tế, phải mở `DatagramChannel.open(INET6)`, chọn interface IPv6 phù hợp, bind, join, nhận datagram và xác minh packet.

### 9.2. Tại sao bài dùng IPv4 loopback để kiểm tra gửi/nhận?

UDP loopback không cần multicast router, interface tùy chọn hoặc network traffic ra ngoài host. Nó kiểm tra:
- `DatagramChannel.open(INET)` có thể tạo channel IPv4 khi OS hỗ trợ.
- `bind` nhận địa chỉ local IPv4 và port tạm.
- `send`/`receive` truyền đúng payload.
- Nonblocking receiver và `Selector` phối hợp với timeout.

**Đây là phép kiểm thử unicast**, không phải test join multicast. Sự tách biệt làm kết quả đáng tin hơn và tránh khiến người học nghĩ multicast được bảo đảm trên mọi máy.

### 9.3. Vì sao `UNIX` bị từ chối?

`StandardProtocolFamily.UNIX` tồn tại ở Java 17, nhưng `DatagramChannel.open(ProtocolFamily)` có ghi chú **Unix domain sockets are not supported**. Kết quả `unix.datagramUnsupported=true` trong lần chạy là bằng chứng trực tiếp trên JDK đã thử, phù hợp contract. Nếu cần Unix-domain stream sockets, dùng các API hỗ trợ thích hợp như `SocketChannel`/`ServerSocketChannel` trên nền tảng tương ứng, không cố dùng `DatagramChannel`.

### 9.4. Tại sao test không dùng `DatagramChannel.open()`?

Vì overload mặc định có **family unspecified**; test sẽ không có kỳ vọng portable “channel mặc định là IPv4”. Đây chính là lý do bài học nhấn mạnh family phải được chọn **tường minh** khi protocol group là yêu cầu bắt buộc.

## 10. Cấu hình multicast thực tế: đoạn minh họa bổ sung

Giả sử ứng dụng đã có:
- `InetAddress group` là địa chỉ multicast đã xác minh.
- `NetworkInterface iface` là interface cụ thể do cấu hình hệ thống lựa chọn, đang up và hỗ trợ multicast.
- `int port` là UDP port hợp lệ mà ứng dụng muốn nghe.

Một method minh họa cấu hình nhận một datagram có thể viết như sau:

```java
static boolean receiveMulticastOnce(
        InetAddress group,
        NetworkInterface iface,
        int port) throws IOException {

    if (group == null || !group.isMulticastAddress()) {
        throw new IllegalArgumentException("Invalid multicast group");
    }
    if (iface == null || !iface.isUp()
            || !iface.supportsMulticast()) {
        throw new IllegalArgumentException("Invalid interface");
    }

    StandardProtocolFamily family =
            group instanceof Inet4Address
                    ? StandardProtocolFamily.INET
                    : StandardProtocolFamily.INET6;

    try (DatagramChannel dc = DatagramChannel.open(family);
         Selector selector = Selector.open()) {

        dc.setOption(StandardSocketOptions.SO_REUSEADDR, true);
        dc.bind(new InetSocketAddress(port));

        MembershipKey key = dc.join(group, iface);
        try {
            dc.configureBlocking(false);
            dc.register(selector, SelectionKey.OP_READ);

            if (selector.select(1000) == 0) {
                return false; // Không có gói trong thời hạn.
            }

            ByteBuffer buffer = ByteBuffer.allocate(2048);
            SocketAddress sender = dc.receive(buffer);
            return sender != null;
        } finally {
            key.drop();
        }
    }
}
```

**Đây là phương thức minh họa, không được gọi trong `main` của bài kiểm thử.** Để biên dịch trong một class riêng, import `java.io.IOException`, `java.net.*`, `java.nio.ByteBuffer` và `java.nio.channels.*`. Trước khi dùng thật phải chọn group/interface/port cụ thể, thiết kế kích thước datagram, xác minh người gửi và parse payload.

Giới hạn cần nắm:
- `selector.select(1000)` chỉ chờ tối đa một giây; trả `false` không chứng minh group/configuration sai, có thể đơn giản **chưa có gói gửi tới**.
- Nếu datagram lớn hơn buffer 2048 byte, dữ liệu có thể bị cắt; phải chọn giới hạn phù hợp và định nghĩa protocol framing.
- NIC hỗ trợ multicast không bảo đảm router/firewall/hypervisor truyền gói.
- IPv6 link-local group có ràng buộc scope/interface; gửi ra network khác không chỉ dựa vào TTL.
- Cần policy bảo mật và xác thực nội dung, vì UDP/multicast không tự mã hóa hay xác thực người gửi.
- Source-specific multicast, nhiều interfaces và cấu hình production có thể cần logic thêm.

### 10.1. Quy trình chọn interface

Không hard-code tên interface từ máy tác giả rồi áp cho mọi môi trường. `NetworkInterface.getByName(...)` phụ thuộc OS và tên interface thực tế. Có thể để người vận hành cấu hình interface hoặc dùng `NetworkInterface.getByInetAddress(...)` nếu đã xác định đúng local IP mong muốn.

Sau khi chọn, kiểm tra `isUp()` và `supportsMulticast()`; với IPv6 cần kiểm tra địa chỉ/scope hỗ trợ thực tế. Nếu có nhiều interfaces, test từng cấu hình trong môi trường cho phép và log lựa chọn, không “chọn interface đầu tiên cho mọi request”.

## 11. Các lỗi và tình huống nền tảng thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `open(INET6)` ném `UnsupportedOperationException` | Họ IPv6 không được nền tảng/provider hỗ trợ | Báo rõ cấu hình/feature unavailable; không tự join IPv6 qua INET |
| `open()` hoạt động trên máy A nhưng nhận multicast lỗi trên máy B | Default family unspecified | Dùng `open(INET/INET6)` theo group |
| IPv6 channel không nhận group IPv4 | Cross-family multicast không portable | Chọn `INET` cho IPv4 group |
| `join` ném lỗi vì địa chỉ không phải multicast | Group sai | Kiểm tra `isMulticastAddress()` |
| Không có datagram dù join thành công | NIC, firewall, route, sender, TTL, scope | Kiểm tra interface, bind wildcard, membership và mạng |
| Bind lỗi vì port đang dùng | Trùng bind hoặc quyền hạn | Kiểm tra port; `SO_REUSEADDR` trước bind khi phù hợp |
| `SO_REUSEADDR` không cho phép dùng chung trên OS cụ thể | OS semantics | Test khả năng trên môi trường thật |
| Chọn `IP_MULTICAST_IF` nhưng vẫn sai family | Option chỉ chọn outgoing interface | Chọn family trong `open` trước |
| `receive` nonblocking trả `null` | Không có gói ngay lúc gọi | Dùng `Selector` và xử lý timeout |
| Bị cắt datagram | Buffer quá nhỏ | Giới hạn payload và buffer hợp lý |
| `connect` thành công nhưng peer không phản hồi | UDP không có handshake/reliability | Đặt timeout và retry protocol-level nếu cần |
| Lỗi khi gửi IPv6 từ `INET` socket | Address-family mismatch | Mở channel `INET6` nếu yêu cầu đúng |
| `open(UNIX)` bị từ chối | Không hỗ trợ Unix-domain datagrams trong API này | Dùng loại channel khác nếu cần Unix local IPC |
| Group IPv6 link-local không tới | Scope/interface sai | Cấu hình interface và scoped address phù hợp |
| Group nhận duplicate/missing datagram | UDP/multicast best effort | Thiết kế sequence/idempotency ở tầng ứng dụng |
| `SecurityException` hoặc bind không được phép | Policy hoặc quyền OS/container | Chạy theo quyền và cấu hình hợp lệ |
| Channel không được đóng | Rò socket/file descriptor | Dùng `try-with-resources` |
| Dùng `read/write` trước khi connected | Sai phương thức cho unconnected UDP | Dùng `send/receive` hoặc `connect` nếu cần |

**Không có một exception duy nhất cho mọi failure mạng.** Những lỗi có thể xuất hiện khi mở, bind, set options, join, send hoặc receive; cần xử lý đúng giai đoạn và không che lỗi bằng cách lén chuyển family.

## 12. Tính đúng và bảo mật ở tầng ứng dụng

Chọn đúng family không giải quyết mọi vấn đề của UDP:

1. **Mất gói:** UDP/multicast không hứa giao hàng.
2. **Gói trùng và sai thứ tự:** nếu ứng dụng cần tính thứ tự, hãy thêm sequence number và logic xử lý.
3. **Dữ liệu không tin cậy:** kiểm tra kích thước, format, version và tính hợp lệ trước khi parse.
4. **Quyền gửi/nhận:** `MembershipKey` không phải authentication; một nhóm multicast không tự mã hóa traffic.
5. **Giới hạn tài nguyên:** cấp buffer phù hợp; không tạo vô hạn datagrams/process queues.
6. **Địa chỉ IP và DNS:** với hostname từ input, không giả định nó luôn resolve ra một family duy nhất.
7. **IPv6 scope:** link-local addresses/multicast có thể yêu cầu interface hoặc zone identifier.
8. **Phạm vi lan truyền:** TTL/hop limit và multicast routing policy không được thay bằng việc đơn thuần gửi datagram.
9. **Trạng thái channel:** đóng membership/channel đúng lúc, đừng dùng `MembershipKey` đã invalid.
10. **Quan sát lỗi:** log group type, selected family, local bind address, network interface, port và lỗi—không cần ghi lộ payload nhạy cảm.

Trong production, nên có integration tests chạy trên chính nền tảng mạng được triển khai. Một unit test chọn `INET/INET6` đúng mới xác nhận phần **decision logic**, chưa xác nhận cấu hình multicast end-to-end.

## 13. Checklist trước khi triển khai

- [ ] Xác định đang cần unicast IPv4, unicast IPv6, multicast IPv4 hay multicast IPv6.
- [ ] Dùng `Inet4Address`/`Inet6Address`, không phân loại IP bằng string contains.
- [ ] Với multicast group, kiểm tra `group.isMulticastAddress()`.
- [ ] Mở `DatagramChannel.open(INET)` cho group IPv4.
- [ ] Mở `DatagramChannel.open(INET6)` cho group IPv6.
- [ ] Không dựa vào family mặc định của `DatagramChannel.open()` khi multicast.
- [ ] Không dùng `StandardProtocolFamily.UNIX` với `DatagramChannel` trong Java 17.
- [ ] Xử lý provider/platform không hỗ trợ `INET6`.
- [ ] Chọn đúng `NetworkInterface`; kiểm tra `isUp`/`supportsMulticast` và scope.
- [ ] Bind wildcard khi nhận multicast nếu muốn hành vi portable.
- [ ] Cấu hình `SO_REUSEADDR` trước bind khi cần nhiều members cùng port.
- [ ] Phân biệt `IP_MULTICAST_IF` (outgoing interface) với protocol family.
- [ ] Dùng `join`/`MembershipKey.drop` theo vòng đời, đóng channel bằng `try-with-resources`.
- [ ] Với source-specific multicast, xác minh platform hỗ trợ source filtering.
- [ ] Không mong `connect` biến UDP thành TCP.
- [ ] Nonblocking receive xử lý `null`; dùng `Selector`/timeout phù hợp.
- [ ] Xác minh kích thước datagram, chống truncation và parse dữ liệu không tin cậy.
- [ ] Không coi `join` thành công là gói chắc chắn tới từ router.
- [ ] Thử trên Windows/Linux/container và interface thật theo yêu cầu.
- [ ] Có logs/metrics đủ để phân biệt lỗi family, NIC, port, firewall và route.
- [ ] Không dùng giá trị TTL/loopback tùy tiện để “ép” gửi sang vùng mạng khác.

## 14. Câu hỏi ôn tập

**Câu 1.** `DatagramChannel.open()` mặc định là IPv4 hay IPv6?  
**Đáp án:** Java API **không đặc tả** họ giao thức; nó phụ thuộc nền tảng/cấu hình.

**Câu 2.** Muốn một UDP channel IPv4 tường minh, gọi gì?  
**Đáp án:** `DatagramChannel.open(StandardProtocolFamily.INET)`.

**Câu 3.** Muốn một UDP channel IPv6 tường minh, gọi gì?  
**Đáp án:** `DatagramChannel.open(StandardProtocolFamily.INET6)`; phải xử lý nền tảng không hỗ trợ IPv6.

**Câu 4.** Tại sao nhóm multicast IPv4 nên dùng `INET`?  
**Đáp án:** Tài liệu `MulticastChannel` không bảo đảm một IPv6 socket có thể join/receive IPv4 multicast group.

**Câu 5.** Có được dùng `InetAddress.getByName(hostname)` rồi giả định kết quả luôn là IPv4 không?  
**Đáp án:** Không. Hostname có thể resolve ra IPv4 hoặc IPv6; kiểm tra `instanceof Inet4Address/Inet6Address`.

**Câu 6.** `IP_MULTICAST_IF` có chuyển socket từ IPv4 sang IPv6 không?  
**Đáp án:** Không. Nó chọn outgoing network interface cho multicast; protocol family được chọn tại lúc `open`.

**Câu 7.** Tại sao bind wildcard khi muốn nhận multicast?  
**Đáp án:** Theo `MulticastChannel`, việc nhận multicast khi bind một địa chỉ cụ thể phụ thuộc implementation; wildcard là lựa chọn được khuyến nghị.

**Câu 8.** Khi nào bật `SO_REUSEADDR`?  
**Đáp án:** Trước khi `bind`, nếu cần nhiều thành viên nhận trên cùng port và OS cho phép.

**Câu 9.** `join(group, iface)` trả về gì?  
**Đáp án:** `MembershipKey`, có thể `drop()` để rời membership; đóng channel cũng hủy memberships của nó.

**Câu 10.** Chọn `INET6` có đảm bảo máy nhận được IPv6 multicast không?  
**Đáp án:** Không. Còn phụ thuộc NIC, scope, route, firewall, membership và sender.

**Câu 11.** `StandardProtocolFamily.UNIX` có hoạt động với `DatagramChannel` ở Java 17 không?  
**Đáp án:** Không. Javadoc của `DatagramChannel.open(ProtocolFamily)` nêu Unix domain sockets không được hỗ trợ.

**Câu 12.** `DatagramChannel.connect` là handshake đáng tin như TCP?  
**Đáp án:** Không. UDP connected socket chỉ tạo ràng buộc peer theo API, không bảo đảm giao hàng.

**Câu 13.** Khi `receive` nonblocking trả `null`, có phải channel lỗi?  
**Đáp án:** Không nhất thiết; thường là chưa có datagram sẵn để nhận.

**Câu 14.** Một lần kiểm thử family mapping bằng `InetAddress` có đủ chứng minh multicast hoạt động end-to-end?  
**Đáp án:** Không; còn phải chọn interface, join, gửi datagram và kiểm tra mạng thật.

**Câu 15.** Cần kiểm tra gì trước khi dùng địa chỉ untrusted làm group?  
**Đáp án:** Resolve đúng loại, `isMulticastAddress`, scope/quyền sử dụng, network interface, port và policy nhận dữ liệu.

## 15. Kết luận

Để **chọn họ giao thức khi mở `DatagramChannel`** đúng trong Java:

1. Xác định ứng dụng cần IPv4 hay IPv6 từ **địa chỉ thực tế**.
2. Khi tham gia IP multicast, chọn `StandardProtocolFamily.INET` cho `Inet4Address` và `INET6` cho `Inet6Address`.
3. Không dựa vào `DatagramChannel.open()` để đoán family; default family được đặc tả là phụ thuộc nền tảng.
4. Không dùng `UNIX` với `DatagramChannel` ở Java 17.
5. Sau khi mở đúng family, tiếp tục xử lý interface, wildcard bind, `SO_REUSEADDR`, `join`, membership, route và hạn chế của mạng.
6. Dùng `try-with-resources` và kiểm tra I/O; không suy rằng multicast tự đảm bảo giao hàng.

Đây là những kiến thức **vẫn còn áp dụng cho Java 17+**, đồng thời giữ đúng lịch sử API từ Java 7.

### Tài liệu chính thức còn hiệu lực

- [Oracle Java SE 17 — `DatagramChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/DatagramChannel.html): hai overload `open`, họ giao thức mặc định unspecified, `open(ProtocolFamily)`, send/receive/connect và socket options.
- [Oracle Java SE 17 — `MulticastChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/MulticastChannel.html): lưu ý platform dependencies, chọn family theo group, wildcard binding, `SO_REUSEADDR` và `join`.
- [Oracle Java SE 17 — `StandardProtocolFamily`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/StandardProtocolFamily.html): `INET`, `INET6`, `UNIX`.
- [Oracle Java SE 17 — `StandardSocketOptions`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/StandardSocketOptions.html): `IP_MULTICAST_IF`, `IP_MULTICAST_TTL`, `IP_MULTICAST_LOOP`, `SO_REUSEADDR`.
- [Oracle Java SE 17 — `NetworkInterface`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/NetworkInterface.html): giao diện mạng, địa chỉ và `supportsMulticast`.
- [Oracle Java SE 17 — `MembershipKey`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/MembershipKey.html): quản lý membership và `drop`.
- [Oracle Java SE 17 — `Selector`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html): readiness-based nonblocking I/O.
