# InterfaceAddress, broadcast và độ dài tiền tố trong Java 17+

## 1. Tổng quan: một giao diện mạng có thể có nhiều địa chỉ

Hệ điều hành có thể cấu hình các địa chỉ IPv4/IPv6 cho Ethernet, Wi-Fi, loopback, VPN, tunnel, interface ảo và container. Trong Java, **`java.net.NetworkInterface`** đại diện cho một giao diện mạng, còn **`java.net.InterfaceAddress`** đại diện cho **một địa chỉ IP đã gắn trên giao diện đó** cùng thông tin subnet.

Bài này tập trung vào ba thuộc tính quan trọng:
- **`InterfaceAddress.getAddress()`:** địa chỉ IP của assignment dưới dạng `InetAddress`.
- **`InterfaceAddress.getNetworkPrefixLength()`:** số bit đầu địa chỉ xác định network prefix (cách viết CIDR `/24`, `/64`…).
- **`InterfaceAddress.getBroadcast()`:** địa chỉ broadcast IPv4 do nền tảng báo cáo, **nếu tồn tại**; IPv6 không có broadcast.

Ví dụ **cấu hình giả định**, không phải kết quả bắt buộc trên máy bạn:

```text
Interface: ethernet0
  IPv4:             192.168.10.42/24
  mask:             255.255.255.0
  network:          192.168.10.0
  IPv4 broadcast:   192.168.10.255 (khi link hỗ trợ broadcast)

  IPv6:             2001:db8:abcd:12::42/64
  IPv6 broadcast:   không có, getBroadcast() == null

Interface: lo
  IPv4:             127.0.0.1/... (theo OS)
  IPv6:             ::1/128 hoặc cấu hình tương ứng
```

**Đối tượng học tập:** cách đọc cấu hình mạng đúng, tính CIDR có kiểm tra, phân biệt broadcast với địa chỉ cuối của mạng, hiểu ngoại lệ IPv4 point-to-point `/31`, IPv4 host `/32`, IPv6 link-local scope và tránh giả định sai trong môi trường Docker/VPN/cloud.

**Special Note:** chỉ sử dụng kiến thức hiện còn đúng với JDK hiện đại. `InterfaceAddress` đã có từ Java 6 nhưng vẫn là API trong `java.base` của Java 17/21/25, không phải class đã bị loại bỏ. Chương trình hoàn chỉnh dùng ngôn ngữ/API tương thích Java 17, được biên dịch bằng `javac --release 17`.

## 2. Phân biệt NetworkInterface, InterfaceAddress và InetAddress

| API | Đại diện | Phương thức hữu ích |
| --- | --- | --- |
| `NetworkInterface` | Card/interface mạng do OS/JDK nhìn thấy. | `getName()`, `getDisplayName()`, `getIndex()`, `getInterfaceAddresses()`, `isUp()`, `isLoopback()`, `isPointToPoint()`, `supportsMulticast()`. |
| `InterfaceAddress` | Một IP assignment trên một interface, có prefix và broadcast metadata. | `getAddress()`, `getNetworkPrefixLength()`, `getBroadcast()`. |
| `InetAddress` | Một địa chỉ IP; bản thân nó không giữ netmask của NIC. | `getHostAddress()`, `getAddress()`, `isLinkLocalAddress()`. |
| `Inet4Address` | IPv4, 4 bytes (32 bit). | Kiểm tra `instanceof`, đọc raw bytes. |
| `Inet6Address` | IPv6, 16 bytes (128 bit), có thể có zone. | `getScopeId()`, `getScopedInterface()`, `isLinkLocalAddress()`. |

Một interface có thể có **0, 1 hoặc nhiều** `InterfaceAddress`. Một IP chỉ có dạng `InetAddress` không cho biết OS đang dùng `/24` hay `/27` tại giao diện nào. Muốn biết netmask/prefix của địa chỉ **được cấu hình trên máy**, phải đọc dữ liệu của `InterfaceAddress` thay vì tự suy từ IP hoặc DNS.

### 2.1. Lấy danh sách address assignments

```java
Enumeration<NetworkInterface> interfaces =
        NetworkInterface.getNetworkInterfaces();

if (interfaces != null) {
    while (interfaces.hasMoreElements()) {
        NetworkInterface nic = interfaces.nextElement();
        for (InterfaceAddress item : nic.getInterfaceAddresses()) {
            InetAddress ip = item.getAddress();
            short prefix = item.getNetworkPrefixLength();
            InetAddress broadcast = item.getBroadcast();
            // Phân biệt IPv4/IPv6, kiểm tra null/range rồi mới dùng.
        }
    }
}
```

**Đây là snippet, không phải file biên dịch độc lập.** Các imports cần dùng: `java.net.*` và `java.util.Enumeration`. `NetworkInterface.getNetworkInterfaces()` có thể ném `SocketException`, và có thể trả `null` nếu không tìm thấy interfaces theo contract. `getInterfaceAddresses()` có thể trả danh sách rỗng.

Không dùng `list.get(0)` khi chưa kiểm tra rỗng, không lấy adapter đầu tiên làm mạng Internet, và không dừng ngay sau địa chỉ IPv4 đầu tiên: có thể còn IPv6 và các địa chỉ tạm/VPN khác.

### 2.2. getInetAddresses() khác gì?

`NetworkInterface.getInetAddresses()` và `inetAddresses()` trả các `InetAddress`, phù hợp khi chỉ muốn liệt kê IP. Chúng **không trả trực tiếp prefix/broadcast**. Nếu cần phần mạng:

```java
for (InterfaceAddress item : nic.getInterfaceAddresses()) {
    InetAddress ip = item.getAddress();
    System.out.println(ip.getHostAddress()
            + "/" + item.getNetworkPrefixLength());
}
```

**Snippet:** biến `nic` phải được khai báo và imports cần có. Khi ứng dụng muốn hiểu **tập địa chỉ thực sự cấu hình trên NIC**, `getInterfaceAddresses()` là API phù hợp hơn chỉ resolve tên host qua `InetAddress.getAllByName(...)`.

### 2.3. Không new InterfaceAddress bằng constructor công khai

`InterfaceAddress` không có public constructor cho ứng dụng tự tạo assignment giả. Với test logic CIDR, hãy truyền một `InetAddress` và `int prefix` vào hàm độc lập; với test thông tin OS, lấy `InterfaceAddress` thật từ `NetworkInterface`. Đừng dùng internal reflection hoặc truy cập class JDK không được công bố để tự lắp đối tượng.

## 3. Chi tiết ba phương thức của InterfaceAddress

### 3.1. getAddress()

```java
InetAddress configuredIp = item.getAddress();
```

Kết quả thuộc IPv4 hoặc IPv6:
- `configuredIp instanceof Inet4Address`: IPv4, 32 bit.
- `configuredIp instanceof Inet6Address`: IPv6, 128 bit.
- `getHostAddress()` trả dạng số, không cần reverse DNS. `getHostName()` **có thể cần DNS**, nên không dùng để tính subnet hay ghi inventory nhanh.
- `InetAddress.getAddress()` trả raw network-order bytes, rất phù hợp cho phép toán bit.
- IPv6 link-local có thể có `%zone` trong `getHostAddress()`.

**Không** coi địa chỉ IP được gắn trên interface là địa chỉ public egress mà người ngoài thấy: NAT, VPN, proxy, route và container có thể thay đổi đường đi của kết nối.

### 3.2. getNetworkPrefixLength()

```java
short prefixLength = item.getNetworkPrefixLength();
```

Prefix là **số bit 1 liên tiếp từ trái** trong subnet mask, không phải số byte hay số host. Dải toán học:
- IPv4: `0 ≤ prefix ≤ 32`.
- IPv6: `0 ≤ prefix ≤ 128`.

Đọc `short` rồi chuyển sang `int` và kiểm tra theo address family trước khi shift/mask. Prefix `/24` có nghĩa 24 bits mạng + 8 bits host trong IPv4. Prefix `/64` có nghĩa 64 bits mạng + 64 bits còn lại trong IPv6. **Không** có quy tắc “mọi IPv4 đều /24” hoặc “mọi IPv6 đều /64”.

### 3.3. getBroadcast()

```java
InetAddress reportedBroadcast = item.getBroadcast();
if (reportedBroadcast == null) {
    System.out.println("broadcast=none");
} else {
    System.out.println("broadcast="
            + reportedBroadcast.getHostAddress());
}
```

**Snippet:** biến `item` có sẵn trong vòng lặp `getInterfaceAddresses()`.

Theo Java SE 17/25 Javadoc:
- **IPv6 không có broadcast address**, nên `getBroadcast()` của một assignment IPv6 trả `null`.
- **Một số IPv4 interfaces** cũng không hỗ trợ broadcast; `getBroadcast()` có thể trả null, chẳng hạn trên point-to-point/tunnel/loopback tùy OS.
- Giá trị không null là **metadata nền tảng trả về**, không là phép thử bảo đảm có thể gửi gói UDP tới mọi host.
- Một OS có thể báo broadcast metadata cho loopback hoặc adapter ảo dù việc sử dụng không giống Ethernet; không assert tất cả loopback nhất định phải null.

**Không tự thay thế `null` bằng `255.255.255.255` hoặc bằng địa chỉ cuối CIDR rồi tự gửi packet.** Muốn broadcast IPv4 thực sự cần link/protocol cho phép, quyền socket, firewall/router policy và mục đích hợp lệ.

### 3.4. equals, hashCode và toString

`InterfaceAddress.equals()` so sánh **address, prefix length và broadcast**. Hai assignments cùng `192.168.10.42` nhưng một cái `/24` và một cái `/27` không có cùng cấu hình. `hashCode()` theo contract của equals. `toString()` hữu ích khi debug, nhưng đừng parse output đó làm API ổn định, bảng DB hay định dạng truyền mạng. Lưu từng field riêng, ghi thời điểm đo và interface identity khi cần.

## 4. Tính subnet IPv4 từ CIDR

Ví dụ: `192.168.10.42/24`.

```text
IP:      192.168.10.42
Binary:  11000000 10101000 00001010 00101010
Mask:    11111111 11111111 11111111 00000000
Network: 11000000 10101000 00001010 00000000
Last:    11000000 10101000 00001010 11111111

Mask:           255.255.255.0
Network:        192.168.10.0
Last address:   192.168.10.255
```

Hai công thức:
- **Network bytes** = `IP bytes AND mask bytes`.
- **Last IPv4 address** = `network bytes OR (NOT mask bytes)`, giữ trong 4 bytes IPv4.

Trong một subnet IPv4 có broadcast như mạng Ethernet thông thường, địa chỉ cuối có thể chính là **directed broadcast address**. Nhưng đây là **hệ quả của loại link và policy**, không phải định nghĩa luôn đúng của `getBroadcast()`.

### 4.1. Bảng mask thường gặp

| CIDR | Netmask IPv4 | Ghi chú |
| --- | --- | --- |
| `/0` | `0.0.0.0` | Tập địa chỉ toán học lớn nhất, không là một LAN broadcast tới Internet. |
| `/8` | `255.0.0.0` | 8 network bits. |
| `/16` | `255.255.0.0` | 16 network bits. |
| `/20` | `255.255.240.0` | Subnet cắt giữa octet thứ ba. |
| `/24` | `255.255.255.0` | 8 host bits. |
| `/30` | `255.255.255.252` | 4 địa chỉ toán học. |
| `/31` | `255.255.255.254` | Hai địa chỉ, đặc biệt trên point-to-point. |
| `/32` | `255.255.255.255` | Một địa chỉ host-specific. |

Ví dụ `172.28.33.14/20` có:
- Mask `255.255.240.0`.
- Network `172.28.32.0`.
- Last IPv4 address `172.28.47.255`.

Vì `/20` cắt **giữa octet**, không dùng cách thay cả octet thành `0`/`255` một cách tùy tiện. Nên xử lý bitwise trên `byte[]` như chương trình đầy đủ.

### 4.2. Java byte là signed nhưng vẫn làm bitwise được

`InetAddress.getAddress()` cho ra `byte[4]` hoặc `byte[16]`. Java byte lưu -128..127, nhưng các bit vẫn được bảo toàn. Khi tạo mask:

```java
int highBits = 5;
byte maskByte = (byte) (0xff << (8 - highBits));
// 11111000 theo bit, tương đương unsigned 248.
```

**Snippet độc lập**. Khi chuyển byte thành giá trị octet để in số, dùng `Byte.toUnsignedInt(b)` hoặc `b & 0xff`. Không dùng `String.startsWith("192.168.10")` để xét cùng subnet: `192.168.100.3` sẽ match sai, và một `/23` có thể trải qua nhiều octet values.

### 4.3. CIDR /0: đừng gây tràn khi shift

Với IPv4 `/0`:
- Mask `0.0.0.0`.
- Network `0.0.0.0`.
- Last IPv4 address (toán học) `255.255.255.255`.

**Đừng viết `1 << (32 - prefix)` bằng int để đếm số địa chỉ**, vì `1 << 32` trong Java bị giới hạn shift distance và cho kết quả không mong muốn. Dùng `long`/`BigInteger` nếu thật sự cần đếm, và nhớ số địa chỉ toán học **không đồng nghĩa số host có thể sử dụng**.

## 5. Ngoại lệ /31 và /32 rất quan trọng

### 5.1. IPv4 /31 point-to-point theo RFC 3021

`192.0.2.10/31` có hai địa chỉ:
- First numerical address: `192.0.2.10`.
- Last numerical address: `192.0.2.11`.

Trên **point-to-point links**, RFC 3021 cho phép **cả hai địa chỉ trở thành host endpoints**. Không dùng địa chỉ `.11` làm directed broadcast của link. Đây là lý do công thức “usable hosts = 2^(32-prefix) - 2” **không áp dụng vô điều kiện cho /31**.

Chương trình mẫu in `p31First` và `p31Second`, cố ý **không** gọi `p31Broadcast`. Prefix math chỉ cho biết hai đầu mút số; link semantics quyết định công dụng chúng.

`192.0.2.0/24` là dải IPv4 dành cho tài liệu (RFC 5737), phù hợp ví dụ code và **không cần gửi network packet**.

### 5.2. IPv4 /32 host-specific

`192.0.2.10/32`:
- Mask toàn bộ 32 bits là 1.
- Network bằng chính `192.0.2.10`.
- Last numerical address bằng chính `192.0.2.10`.
- Không có dedicated directed broadcast riêng trong dải chỉ một địa chỉ.

Nếu API báo null broadcast, đừng tự áp dụng last address làm broadcast fallback. `/32` thường dùng cho host routes/địa chỉ riêng lẻ, không phải mạng nhiều hosts thông thường.

### 5.3. Broadcast IPv4 có nhiều ngữ cảnh

- **Directed broadcast**: toàn bộ host bits là 1 trong một broadcast-capable subnet, ví dụ `192.168.10.255` cho `192.168.10.0/24`.
- **Limited broadcast**: `255.255.255.255`, một địa chỉ IPv4 riêng, không phải kết quả của `getBroadcast()` cho mọi NIC.
- **No broadcast link**: point-to-point, một số tunnels, interfaces đặc thù; `getBroadcast()` có thể null.

Broadcast packets có thể bị network devices/firewalls ngăn để tránh khuếch đại traffic. `DatagramSocket.setBroadcast(true)` hoặc `SO_BROADCAST` chỉ cho phép socket sử dụng capability tương ứng khi OS/network cho phép; **không** đảm bảo packet được router chuyển hoặc host khác nhận.

## 6. IPv6 không có broadcast: prefix, multicast và scope

### 6.1. CIDR IPv6

`2001:db8:abcd:12::1/64` và `2001:db8:abcd:12::beef/64` cùng **64 network bits**. `2001:db8:abcd:13::1` khác mạng `/64`. `2001:db8::/32` là địa chỉ IPv6 dành cho ví dụ (RFC 3849), không phải địa chỉ Internet mà code cần truy cập.

Với IPv6:
- `Inet6Address` có 16 bytes (128 bit).
- `getNetworkPrefixLength()` cho biết prefix thực được OS cấu hình.
- **`getBroadcast()` luôn trả null** theo `InterfaceAddress` JavaDoc.
- `/64` phổ biến nhưng không bắt buộc. `/128` biểu diễn host-specific IPv6 address; các prefix khác cũng tồn tại.

IPv6 sử dụng multicast thay vì broadcast trong những giao thức cần liên lạc nhiều đích. Không coi `ff02::1` là một “broadcast” để đưa vào `getBroadcast()`; đó là một **multicast group**, với scope và socket/API khác.

### 6.2. Link-local IPv6 và zone ID

IPv6 link-local như `fe80::1234` có thể xuất hiện trên nhiều interfaces nên cần zone/scope:

```text
fe80::1234%eth0
fe80::1234%7
```

Đây là các chuỗi minh họa; tên/số zone khác nhau theo OS. `Inet6Address.getScopeId()` trả numeric scope nếu có; `getScopedInterface()` trả interface được gắn khi có; `getHostAddress()` có thể kèm `%zone`.

**Cảnh báo với phép tính prefix:** code mẫu tạo network bằng `InetAddress.getByAddress(maskedBytes)`. Nó hữu ích để **so sánh bit-prefix**, nhưng bản network address mới có thể **không mang zone/scope của địa chỉ IPv6 ban đầu**. Không dùng kết quả này như endpoint link-local đã scoped để mở socket.

### 6.3. Multicast không đồng nghĩa broadcast

- IPv6 multicast dùng không gian `ff00::/8`.
- `NetworkInterface.supportsMulticast()` là một capability riêng, không kiểm tra IPv4 broadcast.
- IPv6 multicast cần group membership, scope/zone và quyền socket/network.
- Một interface có IPv6 address chưa chắc cho phép mọi multicast traffic.

Bài này chỉ **đọc interface metadata và tính prefix**, không gửi UDP broadcast hay multicast. Khi viết discovery thực, cần chọn giao thức/scope và policy riêng, không phát gói tin lên mạng chỉ để thử công thức.

## 7. Dữ liệu live là snapshot phụ thuộc OS

Các trạng thái thường gặp:
- Ethernet/Wi-Fi có IPv4, IPv6 hoặc cả hai.
- Loopback có `127.0.0.1`, `::1`; prefix/metadata tùy nền tảng.
- VPN/tunnel/bridge và virtual adapters có thể xuất hiện hoặc biến mất.
- Một interface có thể hiện diện nhưng chưa được gán IP.
- IPv6 privacy address có thể thay đổi.
- Docker/container chạy trong network namespace khác host.
- Cấu hình IP/prefix có thể đổi ngay sau khi `getInterfaceAddresses()` trả về.

`NetworkInterface.getName()`, `getDisplayName()` và `getIndex()` không phải định danh bất biến giữa OS/restart. **Đừng hard-code tên `eth0`, `en0` hoặc cổng Ethernet đầu tiên**. Khi dùng `isUp()`/`isLoopback()`/`isPointToPoint()`, nhớ chúng có thể ném `SocketException` và không chứng minh có kết nối tới Internet.

**Không dùng địa chỉ đầu tiên có broadcast làm default route.** `InterfaceAddress` không trả gateway, DNS server, route metrics, egress IP hoặc quyền đi qua VPN. OS routing/source-address selection quyết định socket đi đâu; cần socket/routing APIs thích hợp và test kết nối thực.

### 7.1. OS broadcast value vs calculated last IP

`getBroadcast()` mô tả giá trị OS trả về. `ipv4Last(address,prefix)` của chương trình dưới đây chỉ tính toán **địa chỉ IPv4 cuối** theo mask. Hai giá trị có thể trùng trong Ethernet `/24` thường gặp nhưng **không phải luôn tương đương về ý nghĩa**. Trong chế độ `--live`, code in actual `getBroadcast()` và không thay bằng `ipv4Last` khi null.

### 7.2. Không coi cùng subnet là được tin cậy

Hai địa chỉ cùng network prefix theo bit:
- Không có nghĩa chúng giao tiếp được: firewall, VLAN, router và network policies vẫn tác động.
- Không có nghĩa client được xác thực. IP có thể bị NAT/proxy, cấu hình sai hoặc có nguy cơ giả mạo trong một số kịch bản.
- Không có nghĩa source IP người ngoài nhìn thấy nằm trên NIC này.

Trong hệ thống bảo mật, dùng **identity, token, mTLS hoặc chính sách xác thực/ủy quyền rõ ràng**; subnet math chỉ là một phần của network policy, không là quyết định tin cậy độc lập.

## 8. Chương trình Java 17+: InterfaceAddressGuide.java

Chương trình hoàn chỉnh dưới đây dùng hai chế độ:
- **Không tham số:** phép tính CIDR trên IP literals, có `AssertionError` khi kết quả sai; stdout **19 dòng xác định**.
- **`--live`:** duyệt cấu hình giao diện mạng OS thực, in `InterfaceAddress` family, prefix, reported broadcast (hoặc null), computed network và IPv6 scope ID khi có. Kết quả **không cố định** và có thể chứa IP nội bộ.

Mã được biên dịch bằng `javac --release 17` trên JDK 24 để chứng minh tương thích Java 17; không cần dependency bên thứ ba hoặc permission gửi network traffic.

### 8.1. Toàn bộ mã nguồn

Lưu file tên **`InterfaceAddressGuide.java`** với UTF-8:

```java
import java.net.Inet4Address;
import java.net.Inet6Address;
import java.net.InetAddress;
import java.net.InterfaceAddress;
import java.net.NetworkInterface;
import java.net.SocketException;
import java.util.Enumeration;

public final class InterfaceAddressGuide {

    private static InetAddress ip(String literal) throws Exception {
        return InetAddress.getByName(literal);
    }

    private static int width(InetAddress address) {
        if (address instanceof Inet4Address) return 32;
        if (address instanceof Inet6Address) return 128;
        throw new IllegalArgumentException("Unknown IP family");
    }

    private static byte[] mask(InetAddress address, int prefix) {
        int bits = width(address);
        if (prefix < 0 || prefix > bits) {
            throw new IllegalArgumentException(
                    "prefix must be between 0 and " + bits);
        }
        byte[] mask = new byte[bits / 8];
        for (int i = 0; i < mask.length; i++) {
            int oneBits = Math.max(0, Math.min(8, prefix - i * 8));
            mask[i] = (byte) (oneBits == 0 ? 0
                    : (0xff << (8 - oneBits)));
        }
        return mask;
    }

    private static InetAddress network(InetAddress address, int prefix)
            throws Exception {
        byte[] addressBytes = address.getAddress();
        byte[] maskBytes = mask(address, prefix);
        for (int i = 0; i < addressBytes.length; i++) {
            addressBytes[i] &= maskBytes[i];
        }
        return InetAddress.getByAddress(addressBytes);
    }

    private static InetAddress ipv4Mask(Inet4Address address, int prefix)
            throws Exception {
        return InetAddress.getByAddress(mask(address, prefix));
    }

    // Last numerical IPv4 address; NOT always a usable broadcast destination.
    private static InetAddress ipv4Last(Inet4Address address, int prefix)
            throws Exception {
        byte[] start = network(address, prefix).getAddress();
        byte[] maskBytes = mask(address, prefix);
        for (int i = 0; i < start.length; i++) {
            start[i] |= (byte) ~maskBytes[i];
        }
        return InetAddress.getByAddress(start);
    }

    private static boolean sameSubnet(InetAddress a, InetAddress b, int prefix)
            throws Exception {
        if (width(a) != width(b)) return false;
        return network(a, prefix).equals(network(b, prefix));
    }

    private static void check(boolean ok, String description) {
        if (!ok) throw new AssertionError(description);
    }

    private static void demo() throws Exception {
        Inet4Address address =
                (Inet4Address) ip("192.168.10.42");
        int prefix = 24;

        String netmask = ipv4Mask(address, prefix).getHostAddress();
        String subnet = network(address, prefix).getHostAddress();
        String last = ipv4Last(address, prefix).getHostAddress();

        check(netmask.equals("255.255.255.0"), "mask /24");
        check(subnet.equals("192.168.10.0"), "network /24");
        check(last.equals("192.168.10.255"), "last /24");

        System.out.println("address=" + address.getHostAddress());
        System.out.println("prefix=" + prefix);
        System.out.println("netmask=" + netmask);
        System.out.println("network=" + subnet);
        System.out.println("lastAddress=" + last);
        System.out.println("sameIPv4Subnet="
                + sameSubnet(address, ip("192.168.10.200"), 24));
        System.out.println("differentIPv4Subnet="
                + sameSubnet(address, ip("192.168.11.1"), 24));

        Inet4Address pointToPoint = (Inet4Address) ip("192.0.2.10");
        System.out.println("p31First="
                + network(pointToPoint, 31).getHostAddress());
        System.out.println("p31Second="
                + ipv4Last(pointToPoint, 31).getHostAddress());
        System.out.println("p32Only="
                + network(pointToPoint, 32).getHostAddress());
        System.out.println("p0Mask="
                + ipv4Mask(pointToPoint, 0).getHostAddress());
        System.out.println("p0Network="
                + network(pointToPoint, 0).getHostAddress());

        InetAddress ipv6 = ip("2001:db8:abcd:12::1");
        check(ipv6 instanceof Inet6Address, "IPv6 literal");
        System.out.println("sameIPv6Prefix64="
                + sameSubnet(ipv6, ip("2001:db8:abcd:12::beef"), 64));
        System.out.println("differentIPv6Prefix64="
                + sameSubnet(ipv6, ip("2001:db8:abcd:13::1"), 64));
        System.out.println("ipv6NetworkIsV6="
                + (network(ipv6, 64) instanceof Inet6Address));
        System.out.println("ipv6Host128="
                + sameSubnet(ipv6, ip("2001:db8:abcd:12::1"), 128));
        System.out.println("ipv6DifferentHost128="
                + sameSubnet(ipv6, ip("2001:db8:abcd:12::2"), 128));

        boolean bad4 = false;
        boolean bad6 = false;
        try { network(address, 33); }
        catch (IllegalArgumentException expected) { bad4 = true; }
        try { network(ipv6, 129); }
        catch (IllegalArgumentException expected) { bad6 = true; }
        check(bad4 && bad6, "invalid prefix rejection");
        System.out.println("invalidIPv4PrefixRejected=" + bad4);
        System.out.println("invalidIPv6PrefixRejected=" + bad6);
    }

    private static void live() throws Exception {
        Enumeration<NetworkInterface> entries =
                NetworkInterface.getNetworkInterfaces();
        if (entries == null) {
            System.out.println("No visible interfaces");
            return;
        }
        while (entries.hasMoreElements()) {
            NetworkInterface nic = entries.nextElement();
            System.out.println("interface=" + nic.getName()
                    + " index=" + nic.getIndex()
                    + " display=" + nic.getDisplayName());

            for (InterfaceAddress item : nic.getInterfaceAddresses()) {
                InetAddress ip = item.getAddress();
                if (ip == null) continue;
                int prefix = item.getNetworkPrefixLength();
                InetAddress actualBroadcast = item.getBroadcast();
                String family = (ip instanceof Inet4Address)
                        ? "IPv4" : "IPv6";

                System.out.println("  family=" + family
                        + " ip=" + ip.getHostAddress()
                        + " prefix=/" + prefix
                        + " broadcast="
                        + (actualBroadcast == null
                            ? "none" : actualBroadcast.getHostAddress()));

                if (prefix >= 0 && prefix <= width(ip)) {
                    System.out.println("  network="
                            + network(ip, prefix).getHostAddress());
                } else {
                    System.out.println("  network=unknown");
                }
                if (ip instanceof Inet6Address v6 && v6.isLinkLocalAddress()) {
                    System.out.println("  ipv6ScopeId=" + v6.getScopeId());
                }
            }
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 0) {
            demo();
        } else if (args.length == 1 && "--live".equals(args[0])) {
            live();
        } else {
            throw new IllegalArgumentException(
                    "Usage: java InterfaceAddressGuide [--live]");
        }
    }
}
```

### 8.2. Biên dịch và chạy

```bash
javac --release 17 -encoding UTF-8 InterfaceAddressGuide.java
java InterfaceAddressGuide
java InterfaceAddressGuide --live
```

Không cần Maven, Gradle, network permissions đặc biệt hay thư viện ngoài JDK. `InetAddress.getByName` trong demo chỉ nhận **numeric IP literals cố định**, không cần truy cập DNS bên ngoài. Tham số `--live` chỉ **đọc metadata network interfaces**, không mở TCP connection và không gửi broadcast packets.

**Thứ tự địa chỉ/interfaces, display names và scope IDs thay đổi theo OS**, do đó đừng assert giá trị cụ thể của `--live`. Cách tốt hơn là assertion theo invariant: IPv6 broadcast null, prefix nằm trong family range nếu được OS báo hợp lệ, interfaces trống được chấp nhận, và string address không được coi là trust token.

### 8.3. Stdout đã kiểm chứng của chế độ mặc định

Chương trình đã **biên dịch thành công với `--release 17` và chạy trên OpenJDK 24**. Kết quả cố định gồm **19 dòng**:

```text
address=192.168.10.42
prefix=24
netmask=255.255.255.0
network=192.168.10.0
lastAddress=192.168.10.255
sameIPv4Subnet=true
differentIPv4Subnet=false
p31First=192.0.2.10
p31Second=192.0.2.11
p32Only=192.0.2.10
p0Mask=0.0.0.0
p0Network=0.0.0.0
sameIPv6Prefix64=true
differentIPv6Prefix64=false
ipv6NetworkIsV6=true
ipv6Host128=true
ipv6DifferentHost128=false
invalidIPv4PrefixRejected=true
invalidIPv6PrefixRejected=true
```

Giải thích:
- `netmask/network/lastAddress`: mask/network/địa chỉ cuối /24 được tính đúng.
- `sameIPv4Subnet` và `differentIPv4Subnet`: kiểm tra membership theo prefix bits thay vì chuỗi.
- `p31First/Second`: hai địa chỉ /31 theo toán học; **không dán nhãn địa chỉ cuối là broadcast**.
- `p32Only`: /32 là một địa chỉ.
- `p0Mask` và `p0Network`: /0 được tính không lỗi bit shift.
- `sameIPv6Prefix64`/`differentIPv6Prefix64`: so sánh 64 bits đầu IPv6.
- `ipv6Host128`/`ipv6DifferentHost128`: /128 xét đúng một host.
- Invalid prefixes `33` cho IPv4 và `129` cho IPv6 bị từ chối bằng `IllegalArgumentException`.

Đây là **test subnet math**, không chứng minh các IP thực tế thuộc cùng physical LAN hoặc có kết nối mạng.

### 8.4. Chế độ live: kết quả phụ thuộc máy

Lệnh:

```bash
java InterfaceAddressGuide --live
```

Dưới đây là **mẫu giả định, không phải stdout đã thực thi cố định**:

```text
interface=ethernet0 index=5 display=Ethernet Adapter
  family=IPv4 ip=192.168.10.42 prefix=/24 broadcast=192.168.10.255
  network=192.168.10.0
  family=IPv6 ip=fe80:0:0:0:1:2:3:4%ethernet0 prefix=/64 broadcast=none
  network=fe80:0:0:0:0:0:0:0
  ipv6ScopeId=5
interface=lo index=1 display=Loopback
  family=IPv6 ip=0:0:0:0:0:0:0:1 prefix=/128 broadcast=none
  network=0:0:0:0:0:0:0:1
```

**Kiểm chứng thực tế:** chế độ `--live` đã chạy trên một môi trường Windows và liệt kê được các interface có và không có IP, IPv4/IPv6, một số IPv4 broadcast metadata và IPv6 link-local với scope ID. Bài không sao chép địa chỉ/tên adapter thật của máy kiểm thử để tránh tiết lộ cấu hình mạng.

Một interface có thể in duy nhất dòng `interface=...` mà không có `family=...`, vì `getInterfaceAddresses()` trả list rỗng. Một loopback IPv4 có thể báo địa chỉ broadcast theo OS dù không nên dùng để gửi ra LAN; không ép giả định loopback luôn null. Với IPv6, `broadcast=none` là kết quả dự kiến.

### 8.5. Vì sao source code tự tính network nhưng lấy broadcast từ OS?

Method `network(ip,prefix)` biểu diễn phép toán chuẩn CIDR, có thể dùng cho test/hiển thị. Nhưng `actualBroadcast = item.getBroadcast()` là dữ liệu **nền tảng thực sự báo**. Khi `actualBroadcast == null`, chương trình không tính một “fallback broadcast” để thay thế, vì không có bảo đảm interface hỗ trợ broadcast.

Khi tính network IPv6 từ raw bytes, kết quả mới có thể mất scope; đừng dùng network address làm đích link-local socket ngay mà không giữ zone/interface.

## 9. Các tình huống sử dụng và giới hạn thực tế

### 9.1. Chẩn đoán interface trên máy chạy Java

Một tool nội bộ có thể hiển thị:
- Danh sách interface name/index/displayName.
- IPv4/IPv6 assignments.
- Prefix lengths và IPv4 broadcast nếu OS báo.
- Có IPv6 link-local zone/scope ID hay không.
- Các interface ảo, VPN, container và loopback hiện diện.

Tuy nhiên, danh sách này **không phải routing table**. Nó không cung cấp default gateway, DNS server, NAT egress IP, route metrics hoặc path tới một remote server. `NetworkInterface.isUp()` cũng không chứng minh có Internet connectivity.

### 9.2. Kiểm tra tính thuộc cùng subnet

Với hai `InetAddress` cùng family và một prefix hợp lệ:

```text
sameSubnet(A, B, prefix)
  = network(A, prefix).equals(network(B, prefix))
```

Đây là phép so sánh **bit-level**:
- `192.168.10.42` và `192.168.10.200` cùng /24.
- `192.168.10.42` và `192.168.11.1` khác /24.
- `2001:db8:abcd:12::1` và `2001:db8:abcd:12::beef` cùng /64.

Không nhầm điều này với “hai hosts thật sự reach được nhau” hoặc “được cấp quyền”. Firewall, VLAN, NAT, route/proxy và authentication là những lớp khác.

### 9.3. Phát UDP broadcast có hợp lý không?

Nếu ứng dụng muốn discovery trên một IPv4 LAN broadcast-capable:
1. Xác định interface/address phù hợp với quyền và network policy.
2. Dùng **`InterfaceAddress.getBroadcast()`**, không tùy tiện tính địa chỉ cuối nếu metadata null.
3. Kiểm tra interface/link và OS `SO_BROADCAST`, rate limit, firewall.
4. Xác minh responses có nguồn/định dạng hợp lệ, không tin mọi UDP reply.
5. Tránh gửi directed broadcast qua router không có sự cho phép; mạng hiện đại thường chặn để giảm amplification.

Không có lý do chạy broadcast packets trong unit test cho prefix math. IPv6 discovery cần multicast theo scope/group riêng; `getBroadcast()` không thể được dùng cho IPv6.

### 9.4. Bảo vệ thông tin mạng

Tên adapter, IP nội bộ, VPN/interface indexes và scope IDs có thể tiết lộ topology. Với endpoint diagnostics:
- Chỉ cấp quyền cho người vận hành được xác thực.
- Không log/sao chép toàn bộ `--live` output vào trang public.
- Redact nếu cần, không dùng MAC/IP làm secret.
- Không cung cấp API để client tùy ý quét mạng hoặc gửi broadcast.
- Khi dùng subnet rules làm một phần firewall/network ACL, kiểm tra proxy/NAT/source address thật và giữ lớp identity/authorization.

### 9.5. Cấu hình động và refresh

DHCP/VPN, IPv6 temporary addresses, cloud/container network namespaces có thể thay đổi danh sách address assignments. Một `InterfaceAddress` là **quan sát tại thời điểm gọi**, không phải bảo đảm vẫn còn trong interface vài giây sau. Với chương trình chạy lâu, refresh theo sự kiện/retry hợp lý và xử lý thay đổi cấu hình. Không cache vô thời hạn rồi dùng để authorize clients hoặc bind sockets.

## 10. Kiểm thử: deterministic và phụ thuộc nền tảng

| Kiểm thử | Input | Kỳ vọng |
| --- | --- | --- |
| IPv4 /24 | `192.168.10.42/24` | Mask `255.255.255.0`; network `192.168.10.0`; last `192.168.10.255`. |
| IPv4 /20 | `172.28.33.14/20` | Mask `255.255.240.0`; network `172.28.32.0`; last `172.28.47.255`. |
| IPv4 /31 | `192.0.2.10/31` | Two endpoints `.10`, `.11`; không gán label broadcast cho point-to-point. |
| IPv4 /32 | `192.0.2.10/32` | Network = last = chính IP. |
| IPv4 /0 | `192.0.2.10/0` | Mask/network `0.0.0.0`, không overflow. |
| Invalid IPv4 | `-1` hoặc `33` | Reject. |
| IPv6 /64 | `2001:db8:abcd:12::1` | Cùng prefix với `...:12::beef`, khác `...:13::1`. |
| IPv6 /128 | Hai địa chỉ khác host bits | Không cùng /128. |
| Invalid IPv6 | `-1` hoặc `129` | Reject. |
| IPv6 OS metadata | `InterfaceAddress` từ IPv6 | `getBroadcast() == null`. |
| IPv4 không broadcast | NIC tunnel/point-to-point/OS-specific | Null-safe, không tự gán fallback. |
| Interface không IP | Virtual/filter interface | List rỗng được chấp nhận. |
| IPv6 link-local | `fe80::...%zone` | Scope được báo khi có; không strip zone khi mở socket. |
| Nhiều địa chỉ | NIC IPv4 + IPv6, nhiều IPv6 temporary | Duyệt mọi assignment. |
| OS thay đổi mạng | VPN connect/disconnect, DHCP update | Refresh, không giả định snapshot bất biến. |
| Bảo mật | Chế độ `--live` in IP | Chỉ log/hiển thị trong phạm vi truy cập được phép. |

**Unit tests** nên dùng các IP literals cố định và assertions của phần không tham số. **Integration tests** cho `--live` nên kiểm tra invariants, không assert tên interface, thứ tự, prefix hay địa chỉ thật: môi trường CI trên Windows/Linux/container có thể khác nhau.

### 10.1. Bộ thuộc tính nên kiểm tra bằng property-based testing

Với mọi IPv4 address và prefix p trong 0..32:
- Mask có đúng p bit 1 liên tiếp từ trái.
- `network(ip,p)` có host bits bằng 0.
- `sameSubnet(ip,ip,p)` luôn true.
- Với p=32, network bằng IP.
- Với p=0, network bằng 0.0.0.0.
- `ipv4Last` giữ nguyên network bits và đặt mọi host bits thành 1.

Với IPv6 prefix p trong 0..128:
- Tạo mask trên **16 bytes**, không shift 32-bit integer.
- Network có host bits bằng 0.
- p=128 giữ nguyên địa chỉ; p=0 làm tất cả bits bằng 0.
- Broadcast không tồn tại, không tạo giá trị tương đương bằng cách OR host bits.

### 10.2. Phân lớp testable

Do `InterfaceAddress` không có public constructor, thiết kế dễ test:
- Hàm thuần CIDR nhận `InetAddress` + prefix; test trực tiếp với literals.
- Adapter OS dùng `NetworkInterface.getInterfaceAddresses()` và chuyển các field sang DTO immutable.
- Integration test adapter trong môi trường được kiểm soát.
- UI/diagnostics chỉ hiển thị data đã chuẩn hóa và bảo vệ theo quyền người dùng.

Không cần reflective creation của JDK internals để test.

## 11. Lỗi thường gặp

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Lấy IP qua `InetAddress` rồi nghĩ đã có netmask. | `InetAddress` không mang prefix của NIC. | Đọc `InterfaceAddress`. |
| Mặc định mọi IPv4 là /24. | OS có thể gán /8,/20,/30,/31,/32… | Đọc `getNetworkPrefixLength()`. |
| Mặc định IPv6 là /64. | /128 và các prefix khác tồn tại. | Đọc prefix và validate 0..128. |
| Dùng `getBroadcast().getHostAddress()` luôn. | IPv6 và một số IPv4 trả null. | Null-check và phân biệt family. |
| Xem địa chỉ cuối là broadcast trên mọi prefix. | /31 và /32 có semantics đặc biệt. | Gọi `lastAddress`; broadcast thực theo OS/link. |
| Dùng `255.255.255.255` như fallback. | Không cùng directed broadcast của mọi subnet. | Không tự gửi tới fallback không kiểm soát. |
| Dùng `String.startsWith` kiểm tra cùng subnet. | Sai ở prefix lẻ và chuỗi IPv6. | Bit mask trên raw IP bytes. |
| Dùng `1 << 32` đếm địa chỉ. | Java shift distance và int overflow. | `long`/`BigInteger` nếu cần đếm. |
| Trộn IPv4 và IPv6 trong cùng mask. | Độ rộng 32 vs 128. | Kiểm tra Inet4Address/Inet6Address. |
| Coi `getInterfaceAddresses().get(0)` luôn có. | Interface có thể không được gán IP. | Lặp qua list, hỗ trợ rỗng. |
| Coi interface đầu tiên là default route. | OS route selection độc lập. | Xem route/socket thực tế. |
| Dùng `isUp` như health check Internet. | Interface up không bảo đảm remote reachable. | Kiểm tra đường đi/remote service. |
| Dùng `getHostName()` để in IP số. | Có thể reverse DNS. | `getHostAddress()`. |
| Bỏ IPv6 zone/scope khi kết nối link-local. | Không biết phải đi qua interface nào. | Bảo toàn scope/interface. |
| Coi `supportsMulticast` đồng nghĩa broadcast. | Hai network capabilities khác nhau. | Chọn protocol và API đúng. |
| Hard-code `eth0` trong test. | OS/VM/container thay tên/card. | Test theo invariants. |
| Cache IP/prefix vô thời hạn. | DHCP/VPN/IPv6 privacy có thể đổi. | Refresh theo vòng đời. |
| Dùng cùng subnet làm authn/authz. | Không chứng minh identity. | Authentication và authorization độc lập. |
| Đăng inventory IP vào logs công khai. | Tiết lộ topology/VPN. | Redact và giới hạn quyền truy cập. |

## 12. FAQ

**1. InterfaceAddress có còn dùng được trong Java 17 và Java 25 không?**

Có. `java.net.InterfaceAddress` vẫn được tài liệu chính thức mô tả và dùng với `NetworkInterface`. Không phải deprecated/legacy API bị loại bỏ.

**2. Có public constructor cho InterfaceAddress không?**

Không. Lấy từ `NetworkInterface.getInterfaceAddresses()`; khi chỉ cần tính CIDR, dùng một `InetAddress` và prefix riêng.

**3. Prefix /24 nghĩa là 24 hosts?**

Không. Nó là 24 network bits trong tổng 32 IPv4 bits; còn 8 bits cho phần host. Số host dùng được phụ thuộc link/subnet semantics.

**4. Tại sao /20 không thể tính bằng cách lấy 2 octets đầu và đặt 0?**

Vì 20 bits nghĩa là octet thứ ba có 4 network bits. Ví dụ `172.28.33.14/20` có network `172.28.32.0`.

**5. IPv6 có địa chỉ broadcast không?**

Không; `getBroadcast()` trả null với IPv6. Multicast là khái niệm khác.

**6. getBroadcast() null có phải interface down không?**

Không. Nó có thể là IPv6, point-to-point hoặc IPv4 link không có broadcast. Muốn biết up/down, gọi `NetworkInterface.isUp()` và xử lý `SocketException`.

**7. Có được dùng IPv4 last address làm UDP broadcast không?**

Chỉ nếu network/link/cấu hình thật sự định nghĩa nó là broadcast và chính sách cho phép. Đừng suy từ phép toán, nhất là /31, /32.

**8. Vì sao /31 dùng được cả hai địa chỉ?**

RFC 3021 định nghĩa hai endpoints trên point-to-point links; không có directed broadcast của link đó.

**9. Vì sao /32 không có dedicated broadcast?**

Dải chỉ gồm một địa chỉ; nó thường là host route/assignment đơn, không một mạng broadcast LAN.

**10. IPv6 link-local có `%eth0` hoặc `%5` nghĩa là gì?**

Đó là zone/scope identifier gắn với interface; cần cho một số kết nối link-local để tránh mơ hồ.

**11. getNetworkInterfaces() có thể trả null không?**

Có theo contract nếu không tìm thấy interface. Danh sách `InterfaceAddress` cũng có thể rỗng; code cần xử lý.

**12. Tôi có thể lấy default gateway từ InterfaceAddress không?**

Không. InterfaceAddress chỉ gồm IP assignment/prefix/broadcast; routing table và gateway không được cung cấp qua API này.

**13. Vì sao live output khác nhau giữa Windows/Linux/container?**

Vì OS adapters, VPN, routing/namespace, IPv6 configuration, driver và trạng thái mạng khác nhau. Không hard-code expected names/IP.

**14. Có nên gửi broadcast trong unit test?**

Không cần; test phép toán CIDR bằng IP literals. Broadcast gửi packets thật có thể tác động mạng và bị firewall chặn.

**15. IPv6 /128 có phải luôn loopback?**

Không. `::1/128` là loopback, nhưng một địa chỉ IPv6 khác cũng có thể được cấu hình /128 làm host-specific address.

**16. Có thể dùng phép sameSubnet để cấp quyền cho tất cả local clients không?**

Không. Subnet membership không thay thế xác thực danh tính, nhất là khi có NAT, proxy, spoofing hoặc mạng chia sẻ.

## 13. Checklist thực hành

- [ ] Lấy các IP assignments từ `NetworkInterface.getInterfaceAddresses()`.
- [ ] Duyệt tất cả interfaces và addresses; hỗ trợ null/empty.
- [ ] Dùng `Inet4Address`/`Inet6Address`, không đoán family bằng chuỗi.
- [ ] Đọc prefix thật từ `getNetworkPrefixLength()` và validate 0..32 hoặc 0..128.
- [ ] Với IPv4 mask/network/last, dùng phép toán bit trên raw bytes.
- [ ] Đọc reported broadcast qua `getBroadcast()` và kiểm tra null.
- [ ] Không gán broadcast cho IPv6; hiểu multicast/zone scope riêng.
- [ ] Không gọi last numerical IP là directed broadcast trên /31 hoặc /32.
- [ ] Không coi IP assignment như default gateway, Internet route hay public NAT address.
- [ ] Không chọn interface theo index/tên đầu tiên nếu mục tiêu là outbound traffic.
- [ ] Dự kiến DHCP/VPN/containers/IPv6 temporary address và làm mới snapshot.
- [ ] Không dùng subnet membership để thay authentication/authorization.
- [ ] Không in network inventory lên logs/telemetry công khai.
- [ ] Unit test CIDR bằng literals, integration test với OS bằng invariants.
- [ ] Chạy `javac --release 17` và kiểm tra behavior trên JDK/OS triển khai thật.

## 14. Tài liệu chính thức

- [Java SE 17 — InterfaceAddress](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InterfaceAddress.html): `getAddress`, `getBroadcast`, `getNetworkPrefixLength`, equals/hashCode.
- [Java SE 25 — InterfaceAddress](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/InterfaceAddress.html): xác nhận API và no IPv6 broadcast trên JDK hiện đại.
- [Java SE 17 — NetworkInterface](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/NetworkInterface.html): `getNetworkInterfaces`, `getInterfaceAddresses` và interface flags.
- [Java SE 17 — InetAddress](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InetAddress.html): network-order bytes, host-address text.
- [Java SE 17 — Inet4Address](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Inet4Address.html).
- [Java SE 17 — Inet6Address](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Inet6Address.html): scoped interface/zone ID.
- [Java SE 17 — DatagramSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/DatagramSocket.html): UDP broadcast option nếu ứng dụng thực sự cần.
- [RFC 3021 — Using 31-Bit Prefixes on IPv4 Point-to-Point Links](https://www.rfc-editor.org/rfc/rfc3021): ngoại lệ /31.
- [RFC 4632 — Classless Inter-domain Routing (CIDR)](https://www.rfc-editor.org/rfc/rfc4632): CIDR notation/network prefixes.
- [RFC 4291 — IPv6 Addressing Architecture](https://www.rfc-editor.org/rfc/rfc4291): IPv6 unicast, anycast, multicast.
- [RFC 3849 — IPv6 documentation prefix](https://www.rfc-editor.org/rfc/rfc3849): `2001:db8::/32`.
- [RFC 5737 — IPv4 documentation address blocks](https://www.rfc-editor.org/rfc/rfc5737): `192.0.2.0/24`.
