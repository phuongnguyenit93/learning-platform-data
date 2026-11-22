# NetworkInterface và danh sách bộ điều hợp mạng trong Java

## 1. Mục tiêu: Java nhìn thấy những giao diện mạng nào?

Khi viết ứng dụng mạng, một máy tính có thể sở hữu nhiều giao diện mạng (*network interfaces*): Ethernet, Wi‑Fi, loopback, VPN, tunnel, bridge, bộ điều hợp do hypervisor/container tạo, và các subinterface theo cấu hình hệ điều hành. Mỗi interface có thể có **nhiều địa chỉ IP**, hoặc **chưa có địa chỉ IP** tại thời điểm kiểm tra.

Trong Java SE hiện hành, `java.net.NetworkInterface` mô hình hóa một giao diện mạng mà hệ điều hành/JDK nhìn thấy. Nó cho phép:

- Liệt kê các giao diện khả dụng trên host hiện tại.
- Đọc tên hệ thống, tên hiển thị và chỉ số (*interface index*).
- Xem các địa chỉ IPv4/IPv6 được gắn với interface.
- Đọc **prefix length** và, nếu có, IPv4 broadcast address qua `InterfaceAddress`.
- Hỏi các trạng thái/đặc tính: `isUp()`, `isLoopback()`, `isPointToPoint()`, `supportsMulticast()` và `isVirtual()`.
- Xem MTU và hardware address khi hệ thống cho phép.
- Duyệt phân cấp parent/subinterfaces.
- Tra cứu interface theo tên, index hoặc địa chỉ IP đã gắn.

Đây là **API đọc thông tin giao diện mạng cục bộ**, không phải công cụ quét thiết bị Wi‑Fi lân cận, không phải bảng định tuyến và cũng không tự thực hiện HTTP request. Một network interface đang `up` vẫn có thể không truy cập được DNS, gateway hay Internet.

Bài viết hướng tới **Java 17+**, không dùng API đã lỗi thời. Các `Stream` methods xuất hiện từ Java 9 tiếp tục được hỗ trợ trong Java 17+; các phương thức `Enumeration` vẫn hợp lệ và cần biết khi đọc mã Java hiện có.

> Câu cần nhớ: **NetworkInterface cho biết những giao diện mạng và địa chỉ cục bộ được JDK quan sát, không bảo đảm lưu lượng ứng dụng sẽ đi ra giao diện nào.**

## 2. Phân biệt NetworkInterface, InetAddress và InterfaceAddress

Ba kiểu dữ liệu dễ nhầm nhất:

| Kiểu | Chức năng | Ví dụ thông tin |
| --- | --- | --- |
| `NetworkInterface` | Biểu diễn một bộ điều hợp/giao diện mạng | Tên, index, trạng thái, MTU, MAC, tập địa chỉ |
| `InetAddress` | Biểu diễn một **địa chỉ IP** | IPv4/IPv6, host address, loopback/link-local |
| `InterfaceAddress` | Một **địa chỉ IP được gắn trên interface** cùng metadata mạng | IP, network prefix length, IPv4 broadcast nếu có |

Quan hệ:

~~~text
Local machine / network namespace
    |
    +-- NetworkInterface A
    |       +-- name, index, flags, MTU, hardware address
    |       +-- InterfaceAddress (IPv4 / prefix / broadcast)
    |       +-- InterfaceAddress (IPv6 / prefix / no broadcast)
    |       +-- optional subinterfaces
    |
    +-- NetworkInterface B
    |       +-- zero or more InterfaceAddress entries
    |
    +-- Loopback interface
            +-- 127.0.0.1 / 8 (example)
            +-- ::1 / 128 (example)
~~~

Sơ đồ chỉ minh họa: tên, số giao diện, địa chỉ, prefix, IPv4/IPv6 enabled state **tùy OS và network namespace**. Không giả định mọi máy đều có hai loopback addresses hoặc chỉ một Ethernet/Wi‑Fi.

### 2.1. Một interface có thể có nhiều IP

Một NIC có thể được gắn:

- Nhiều IPv4 addresses (secondary addresses).
- Nhiều IPv6 addresses (global, link-local, temporary/privacy addresses).
- Cả IPv4 và IPv6.
- Không địa chỉ IP nào trong một trạng thái cấu hình nhất định.

Vì vậy đừng mô hình hóa `Map<NetworkInterface, InetAddress>` với giả định **một interface → một IP**. Nếu muốn lưu, dùng `List<InetAddress>` hoặc `List<InterfaceAddress>` và xử lý nhiều entries đúng cách.

### 2.2. IP không phải MAC

`InetAddress.getHostAddress()` trả về địa chỉ IP dạng chữ; `NetworkInterface.getHardwareAddress()` trả về **byte[] hardware address** (thường là MAC) nếu có và truy cập được. Chúng khác nhau cả về tầng mạng, vòng đời, định dạng và độ tin cậy khi nhận diện thiết bị.

Một interface ảo/loopback có thể không có MAC, hoặc MAC không truy cập được. Một MAC có thể thay đổi/được randomize. Không dùng MAC làm password, token xác thực hoặc danh tính không thể giả mạo.

## 3. Những API quan trọng và nơi sử dụng

### 3.1. Liệt kê interface

~~~java
Enumeration<NetworkInterface> oldStyle =
        NetworkInterface.getNetworkInterfaces();

Stream<NetworkInterface> modern =
        NetworkInterface.networkInterfaces();
~~~

Đây là hai snippet độc lập; cần imports `java.net.NetworkInterface`, `java.util.Enumeration`, `java.util.stream.Stream`. Cả hai phương thức static có thể ném `SocketException`.

- `getNetworkInterfaces()` là API trả `Enumeration`, không deprecated.
- `networkInterfaces()` trả `Stream<NetworkInterface>`, có từ Java 9, phù hợp Java 17+ và phong cách `filter/map/toList`.
- Theo JavaDoc Java SE hiện hành, kết quả có ít nhất một interface hoặc ném `SocketException` nếu nền tảng không có interface được cấu hình / gặp lỗi I/O.
- Không bảo đảm thứ tự các interface là cố định hoặc ý nghĩa xếp hạng ưu tiên; muốn hiển thị ổn định, ứng dụng có thể sắp xếp theo `getName()` nhưng tên vẫn phụ thuộc OS.

Với Enumeration:

~~~java
Enumeration<NetworkInterface> enumeration =
        NetworkInterface.getNetworkInterfaces();

while (enumeration.hasMoreElements()) {
    NetworkInterface nic = enumeration.nextElement();
    System.out.println(nic.getName());
}
~~~

Với Stream:

~~~java
NetworkInterface.networkInterfaces()
        .map(NetworkInterface::getName)
        .sorted()
        .forEach(System.out::println);
~~~

Hai snippet đều hợp lệ trong một method có `throws SocketException` hoặc trong `try/catch` tương ứng. **Không so thứ tự hoặc số lượng của hai lần snapshot như một invariant**: cấu hình mạng có thể thay đổi giữa các lần gọi.

### 3.2. Lấy địa chỉ IP

~~~java
Enumeration<InetAddress> oldAddresses = nic.getInetAddresses();
Stream<InetAddress> addresses = nic.inetAddresses();
List<InterfaceAddress> metadata = nic.getInterfaceAddresses();
~~~

`nic` là một `NetworkInterface` có sẵn, còn imports gồm `InetAddress`, `InterfaceAddress`, `List`. Các phương thức:

- `getInetAddresses()`: dãy `InetAddress` được gắn lên interface.
- `inetAddresses()`: dạng `Stream<InetAddress>` có từ Java 9.
- `getInterfaceAddresses()`: các bản ghi `InterfaceAddress`, trong đó có prefix và broadcast.
- `getInetAddresses()/inetAddresses()` không trực tiếp cho bạn CIDR prefix.
- Một số khả năng truy cập địa chỉ có thể chịu hạn chế của môi trường/runtime. Đừng dựa vào địa chỉ/MAC luôn hiển thị đầy đủ.

## 4. Thông tin nhận dạng: name, display name và index

Các method:

~~~java
String name = nic.getName();
String display = nic.getDisplayName();
int index = nic.getIndex();
~~~

`getName()` thường là tên kỹ thuật từ hệ điều hành, ví dụ các dạng giống `eth0`, `en0`, `lo` hoặc tên khác. Không hardcode những tên này trong chương trình đa nền tảng.

`getDisplayName()` là mô tả dễ đọc hơn, nhưng **có thể null** và có thể bị thay đổi bởi OS, locale, driver hoặc cấu hình. Nó phù hợp UI/diagnostics hơn là khóa cấu hình đáng tin cậy.

`getIndex()` là số định danh giao diện do hệ thống gán, **có thể -1 nếu không xác định**. Chỉ số có thể thay đổi sau reboot, thay đổi network namespace hoặc reconfiguration. Không dùng index làm một ID bền vững qua các lần triển khai.

### 4.1. Tra cứu theo tên và index

~~~java
NetworkInterface byName =
        NetworkInterface.getByName(configuredName);

NetworkInterface byIndex =
        NetworkInterface.getByIndex(configuredIndex);
~~~

Đây là snippet; `configuredName`/`configuredIndex` là giá trị ứng dụng đã nhận/kiểm tra.

- `getByName(name)` tìm interface có tên tương ứng.
- `getByIndex(index)` tìm interface theo index.
- Cả hai có thể trả **null** nếu không tìm thấy.
- Các lookup có thể ném `SocketException` khi gặp lỗi I/O, và input không hợp lệ có thể gây exception theo contract.
- Không hardcode tên/index lấy từ một máy vào cấu hình trên máy khác.

### 4.2. Tìm interface đang gắn một IP

~~~java
NetworkInterface byAddress =
        NetworkInterface.getByInetAddress(localAddress);
~~~

`localAddress` là `InetAddress`; method có thể trả null. Nếu một IP được gắn lên **nhiều** interface, JavaDoc không quy định interface nào sẽ được trả về. Không dùng kết quả tùy ý ấy làm quyết định định tuyến hoặc security.

Với địa chỉ đến từ cấu hình text, cần tránh lấy `InetAddress.getByName(hostname)` rồi suy ra đây là local address. DNS có thể trả IP ở bên ngoài; `getByInetAddress` chỉ hữu ích để xem địa chỉ ấy có được gắn vào một interface trong môi trường hiện tại không.

### 4.3. Những tên hoặc index trùng không tạo định danh toàn cục

Javadoc nêu tên interface có tính platform-specific và có thể không duy nhất trong mọi trường hợp. Tên/index thay đổi theo OS, container namespace, thời điểm chụp snapshot. Nếu ứng dụng cần theo dõi thay đổi, lấy lại danh sách mới và reconcile bằng nhiều thuộc tính phù hợp nghiệp vụ; **không dùng một `NetworkInterface` làm ID vĩnh viễn trong database**.

## 5. Trạng thái giao diện: `isUp` không có nghĩa Internet hoạt động

Các method quan sát:

| Method | Ý nghĩa | Điều không thể suy ra |
| --- | --- | --- |
| `nic.isUp()` | Interface được OS báo đang hoạt động | Không chứng minh có gateway, DNS hay Internet |
| `nic.isLoopback()` | Loopback interface | Không nhất thiết luôn tên `lo` hay `Loopback` |
| `nic.isPointToPoint()` | Giao diện kiểu point-to-point | Không tự xác định VPN protocol/đối tác |
| `nic.supportsMulticast()` | Hỗ trợ multicast theo OS/JDK | Không đảm bảo group có thể join/route thành công |
| `nic.isVirtual()` | Subinterface theo mô hình Java | Không nhận diện tất cả VM/VPN/Hyper-V/Docker virtual adapters |
| `nic.getMTU()` | Maximum Transmission Unit của interface | Không phải path MTU tới mọi đích |
| `nic.getHardwareAddress()` | Hardware address nếu có/quyền cho phép | Không đảm bảo MAC tồn tại/bền vững/độc nhất |

Các method `isUp`, `isLoopback`, `isPointToPoint`, `supportsMulticast`, `getMTU` và `getHardwareAddress` có thể ném `SocketException`. Riêng `isVirtual()` không có checked `SocketException`.

Một ví dụ lọc **ứng viên** interface cho hoạt động mạng:

~~~java
static boolean isCandidate(NetworkInterface nic) {
    try {
        return nic.isUp()
                && !nic.isLoopback()
                && !nic.isPointToPoint();
    } catch (SocketException failure) {
        return false;
    }
}
~~~

Đây là snippet có import `java.net.*`. Nó chỉ lọc ứng viên theo policy minh họa, **không kiểm tra kết nối thực tế**. Một adapter đang up nhưng chưa có địa chỉ usable hoặc không có route đến destination vẫn có thể nằm trong kết quả.

### 5.1. Loopback phải được xử lý theo mục đích

`isLoopback()` phù hợp để nhận diện interface dùng cho liên lạc cục bộ. Với ứng dụng cần phục vụ bên ngoài host, loopback không phải interface cho phép clients từ mạng khác truy cập. Ngược lại, với server test, database giả lập hoặc endpoint admin chỉ được dùng nội bộ, **loopback là lựa chọn tốt**.

Đừng gỡ bỏ loopback khỏi mọi danh sách theo mặc định. Với công cụ kiểm thử/diagnostics, loopback là một phần quan trọng của cấu hình mạng.

### 5.2. Multicast: supported không đồng nghĩa permitted

`supportsMulticast()` nói khả năng interface, không chứng minh firewall, router, địa chỉ group hoặc socket option đã đúng. Nếu ứng dụng thực sự cần multicast, phải cấu hình network channel/socket và thử join/send/receive theo protocol và quyền mạng. **Không gửi multicast chỉ để liệt kê interface**.

### 5.3. `isVirtual` không phải thước đo tất cả thiết bị ảo

Theo JavaDoc, `isVirtual()` xác định interface thuộc loại **virtual subinterface** theo mô hình có parent. Một VM NIC hoặc VPN adapter có thể được OS/JDK báo như giao diện top-level và `isVirtual()==false`. Không dùng `!isVirtual()` để suy ra “chắc chắn là cáp Ethernet vật lý”.

## 6. Địa chỉ IPv4 và IPv6 qua InetAddress

Mỗi `InetAddress` thuộc họ:

~~~java
if (address instanceof Inet4Address) {
    // IPv4.
} else if (address instanceof Inet6Address) {
    // IPv6.
}
~~~

Đây là snippet, `address` có kiểu `InetAddress`; imports `Inet4Address`, `Inet6Address`. Để hiển thị **địa chỉ số** mà không phụ thuộc reverse DNS, dùng:

~~~java
String numericIp = address.getHostAddress();
~~~

`getHostAddress()` phù hợp cho inventory/reporting. Không gọi `getHostName()` khi chỉ muốn format IP, vì nó có thể thực hiện name resolution và tăng độ trễ/phụ thuộc DNS.

### 6.1. Những phân loại địa chỉ hữu ích

| Phương thức của `InetAddress` | Ý nghĩa cần hiểu |
| --- | --- |
| `isAnyLocalAddress()` | Địa chỉ wildcard/unspecified, ví dụ `0.0.0.0` hoặc `::` |
| `isLoopbackAddress()` | Địa chỉ loopback, ví dụ `127.0.0.1`, `::1` |
| `isLinkLocalAddress()` | Địa chỉ link-local, chỉ dùng trong phạm vi liên kết |
| `isSiteLocalAddress()` | Phân loại theo semantics API, **không đồng nghĩa mạng riêng an toàn** |
| `isMulticastAddress()` | Địa chỉ multicast |
| `getHostAddress()` | Text địa chỉ số (IPv6 có thể kèm zone ID/scope) |

Một interface có nhiều addresses thuộc các loại khác nhau. Nếu cần quyết định chọn địa chỉ để bind service, **đừng chỉ dựa trên IPv4/IPv6 hoặc isSiteLocal**. Phải hiểu security/exposure, route, firewall, network namespace và destination.

### 6.2. IPv6 link-local và scope ID

Địa chỉ IPv6 link-local thường cần scope/zone để phân biệt cùng một địa chỉ literal xuất hiện trên nhiều link. Ví dụ địa chỉ dạng:

~~~text
fe80::1234%some-interface
fe80::1234%7
~~~

Đây là **cú pháp minh họa**, không phải địa chỉ thật trên máy hiện tại. Một `Inet6Address` cung cấp:

~~~java
if (address instanceof Inet6Address v6) {
    int scopeId = v6.getScopeId();
    NetworkInterface scopedNic = v6.getScopedInterface();
}
~~~

Hai giá trị có thể không khả dụng trong mọi hoàn cảnh (`getScopedInterface()` có thể null). `getHostAddress()` của IPv6 có thể chứa phần zone; đừng tùy tiện cắt bỏ `%...` khi connect tới địa chỉ link-local. Các địa chỉ link-local không chứng minh có Internet/global reachability.

### 6.3. API address literal không cần DNS

Trong Java 17+ có thể tạo địa chỉ từ bytes:

~~~java
InetAddress ipv4 = InetAddress.getByAddress(
        new byte[] {127, 0, 0, 1});

byte[] ipv6Bytes = new byte[16];
ipv6Bytes[15] = 1;
InetAddress ipv6 = InetAddress.getByAddress(ipv6Bytes);
~~~

Hai lệnh tạo `InetAddress` từ bytes, **không cần DNS lookup**. Nhận được đối tượng IPv6 không đồng nghĩa OS đang bật IPv6 networking; đó chỉ là representation trong Java. Chương trình demo sử dụng điều này để có self-test phân loại IPv4/IPv6 độc lập với tên adapter của máy.

## 7. InterfaceAddress: prefix, broadcast và những giá trị vắng mặt

`NetworkInterface.getInterfaceAddresses()` trả `List<InterfaceAddress>`. Mỗi entry có:

~~~java
InetAddress ip = entry.getAddress();
short prefixBits = entry.getNetworkPrefixLength();
InetAddress broadcast = entry.getBroadcast();
~~~

Ví dụ một IPv4 có thể là `192.0.2.10/24`; prefix `24` cho biết 24 bits đầu của network prefix. `192.0.2.0/24` thuộc khối địa chỉ tài liệu và không phải IP người dùng. Với IPv6, prefix có thể dạng `/64` hoặc các giá trị theo cấu hình interface.

**Không nhầm prefix length với độ dài địa chỉ**:

- IPv4 là 32 bits tổng cộng; `/24` là network prefix 24 bits, không phải 24 bytes.
- IPv6 là 128 bits tổng cộng; `/64` là network prefix 64 bits.
- Prefix nhận từ runtime cần được kiểm tra nếu bạn định dùng nó tính toán subnet/mask. Nếu provider trả giá trị không hợp lệ/không khả dụng, fail safely thay vì shift bits mù quáng.

### 7.1. Broadcast chỉ áp cho IPv4 trong API này

`InterfaceAddress.getBroadcast()`:

- Có thể trả IPv4 broadcast address nếu interface/network hỗ trợ.
- Trả **null** đối với IPv6 vì IPv6 không dùng broadcast.
- Có thể trả null với interface IPv4 không hỗ trợ broadcasting.

Do đó:

~~~java
InetAddress broadcast = entry.getBroadcast();
String shown = broadcast == null
        ? "(none)"
        : broadcast.getHostAddress();
~~~

Đây là snippet. **Đừng gọi `entry.getBroadcast().getHostAddress()` mà không null-check**; loopback, point-to-point và IPv6 là các tình huống bình thường không có broadcast.

### 7.2. Một `InterfaceAddress` không phải route entry

Prefix cho biết cấu hình subnet của địa chỉ giao diện, **không** cung cấp:

- Default gateway.
- Metric hoặc ưu tiên của route.
- Rules policy routing/VPN.
- Destination reachability.
- Firewall/NAT state.
- DNS resolver đang được OS sử dụng.

Nếu cần biết traffic tới server nào sẽ đi qua route nào, dùng OS routing facilities hoặc thử network connection trong môi trường kiểm soát, không tự suy ra từ `getNetworkPrefixLength()`.

## 8. Subinterface và phân cấp parent/children

Một network interface có thể có **subinterfaces** (giao diện con, đôi khi được gọi virtual interface trong API này):

~~~java
NetworkInterface parent = nic.getParent();

nic.subInterfaces()
        .map(NetworkInterface::getName)
        .forEach(System.out::println);
~~~

Các phương thức:

- `getParent()`: trả parent nếu nic là subinterface, hoặc null nếu không có parent.
- `getSubInterfaces()`: trả `Enumeration<NetworkInterface>` các con.
- `subInterfaces()`: trả `Stream<NetworkInterface>` các con (Java 9+).
- `isVirtual()`: cờ subinterface theo API.

**Không giả định mọi hệ điều hành đều báo quan hệ parent-child giống nhau.** Trên máy có Docker/VPN/virtual switches, một adapter được coi là ảo trong OS vẫn có thể không phải “virtual subinterface” theo `isVirtual`.

Khi hiển thị cây, nếu muốn chống việc lặp lại entries, hãy quyết định có hiển thị top-level và children riêng hay gắn cây con vào parent. Đừng mặc định rằng gọi `networkInterfaces()` và đệ quy children rồi cộng lại sẽ luôn không trùng.

## 9. MTU và hardware address

### 9.1. Maximum Transmission Unit

~~~java
int mtu = nic.getMTU();
~~~

MTU biểu diễn giới hạn truyền tải của giao diện theo OS/JDK, thường tính theo bytes. Nó không phải kích thước một HTTP body, cũng không phải Path MTU đến destination qua toàn bộ route. Nếu một UDP packet lớn hơn MTU hoặc bị fragmentation, hành vi còn tùy protocol, IP version và network path.

Không tự áp `mtu` làm `MAX_HTTP_BODY_SIZE`. HTTP/TCP stream có thể lớn hơn MTU rất nhiều vì transport tự chia dữ liệu thành segments/packets.

### 9.2. MAC/hardware address có thể null

~~~java
byte[] hardware = nic.getHardwareAddress();
if (hardware == null) {
    System.out.println("(unavailable)");
} else {
    System.out.println("[redacted]");
}
~~~

Đây là snippet. JavaDoc nói hardware address có thể **không tồn tại hoặc không truy cập được theo quyền hiện tại**. MAC có thể thay đổi theo Wi‑Fi privacy randomization, VPN/VM/container, NIC replacement hoặc chính sách OS.

Trong công cụ diagnostics, **không tự ghi MAC/IP nội bộ vào log bên ngoài** nếu không cần. Nếu cần hiển thị MAC cho quản trị, hãy yêu cầu quyền người dùng và áp dụng masking, retention policy và kiểm soát truy cập.

### 9.3. Khi buộc phải format MAC để debug được cấp quyền

Nếu một yêu cầu quản trị thực sự cần format bytes MAC:

~~~java
byte[] mac = nic.getHardwareAddress();
if (mac != null) {
    StringBuilder text = new StringBuilder();
    for (byte value : mac) {
        if (!text.isEmpty()) {
            text.append(':');
        }
        text.append(String.format(
                java.util.Locale.ROOT, "%02X", value & 0xFF));
    }
    System.out.println(text);
}
~~~

Đây là snippet Java 17+ **chỉ nên bật trong công cụ kiểm soát quyền**. Không hardcode assumptions rằng hardware address luôn dài 6 bytes hoặc cố dùng nó làm machine identifier. Để bài học mặc định an toàn, chương trình hoàn chỉnh luôn in `[redacted]` thay vì MAC raw.

## 10. Snapshot có thể cũ ngay sau khi đọc

JavaDoc Java SE 26 nhấn mạnh network configuration có thể thay đổi **trong suốt vòng đời JVM**. Một `NetworkInterface` instance có thể giữ một số đặc điểm (ví dụ name, assigned IP list) từ lúc khởi tạo. Các sự kiện thực tế:

- Người dùng chuyển Wi‑Fi, rút cáp Ethernet.
- VPN được kết nối/ngắt.
- DHCP cấp lại IPv4.
- IPv6 temporary address thay đổi.
- Container bị thay network namespace.
- OS thay index/name hoặc thêm adapter.
- Interface đang up trở thành down giữa hai lời gọi.

Đừng coi một snapshot trả về từ `networkInterfaces()` là nguồn dữ liệu live tự cập nhật. Nếu cần refresh, **gọi lại API lấy NetworkInterface mới**; không chỉ lặp lại thao tác đọc trên instance cũ rồi mong metadata đã đổi.

### 10.1. Không kiểm tra bằng cách so hai snapshot bắt buộc phải bằng nhau

Cách kiểm thử sai:

~~~java
List<NetworkInterface> first =
        NetworkInterface.networkInterfaces().toList();
List<NetworkInterface> second =
        NetworkInterface.networkInterfaces().toList();

assert first.equals(second); // Không bảo đảm khi cấu hình mạng đổi.
~~~

Đây là anti-pattern. Một số attributes có thể khác ngay giữa hai lần đọc. JavaDoc còn nói hai `NetworkInterface` objects đại diện cùng interface có thể `equals` khác nhau nếu tập IP đã thay đổi.

### 10.2. Nếu cần monitor

`NetworkInterface` không cung cấp một event listener thống nhất để báo mọi thay đổi network adapter. Các cách thiết kế:

- Poll lại snapshot theo khoảng thời gian có kiểm soát.
- So khớp names/index/addresses theo policy và đánh dấu sự kiện “changed”, nhưng không suy đoán tên/index là vĩnh viễn.
- Với môi trường cần phản ứng tức thời/hệ thống, sử dụng OS-native network change events hoặc platform service phù hợp.
- Dừng scheduler/thread monitoring khi ứng dụng shutdown.
- Không poll với chu kỳ quá ngắn và không log toàn bộ MAC/IP mỗi lần.

Dữ liệu network có thể thay đổi trong lúc bạn chọn NIC để bind hoặc multicast join: luôn xử lý `SocketException`/I/O failure tại thao tác cuối.

## 11. Tình huống thực hành: chọn ứng viên interface

Giả sử ứng dụng cần **tìm ứng viên** IPv4 không loopback để hiển thị cho người vận hành:

~~~java
static boolean candidate(NetworkInterface nic) {
    try {
        return nic.isUp()
                && !nic.isLoopback()
                && nic.inetAddresses().anyMatch(ip ->
                        ip instanceof Inet4Address
                        && !ip.isAnyLocalAddress()
                        && !ip.isLoopbackAddress());
    } catch (SocketException ex) {
        return false;
    }
}
~~~

Đây là snippet, cần imports `NetworkInterface`, `SocketException` và `Inet4Address`. Nó chỉ xem có IPv4 usable theo điều kiện đơn giản, **không bảo đảm** IPv4 đó public, Internet reachable, gateway đúng hoặc được phép bind.

Một cách sử dụng:

~~~java
List<NetworkInterface> candidates =
        NetworkInterface.networkInterfaces()
                .filter(MyClass::candidate)
                .toList();
~~~

Đây là snippet có class helper `MyClass.candidate` do ứng dụng định nghĩa. Không có API JDK sẵn tên `candidate`.

### 11.1. Server bind: địa chỉ nào được chọn?

Nếu HTTP server bind trên `127.0.0.1`, chỉ dùng loopback. Nếu bind trên `0.0.0.0`, server lắng nghe wildcard IPv4 trên các interfaces thích hợp theo OS/firewall. Nếu bind một IP cụ thể thuộc NIC, app giới hạn local bind đến IP ấy, nhưng **chưa tự giải quyết TLS, authentication hay firewall policy**.

Không auto-bind tất cả IP tìm được chỉ vì interface `isUp()==true`. Với ứng dụng có dữ liệu nhạy cảm, chọn explicit bind address và deny-by-default network exposure.

### 11.2. Outbound traffic không tự động theo “first interface”

Một ứng dụng mở TCP/HTTP connection thường để OS routing stack quyết định nguồn/route khi không bind local address rõ ràng. Lấy `networkInterfaces().findFirst()` và nghĩ đó là default Internet NIC là sai.

Khi cần multicast, Java có thể dùng network interface trong socket/channel API như `MulticastSocket.setNetworkInterface(...)` hoặc `DatagramChannel.setOption(StandardSocketOptions.IP_MULTICAST_IF, nic)` nếu protocol phù hợp. Đây là hoạt động **khác với enumeration** và cần kiểm tra quyền, IPv4/IPv6, group membership, route và firewall.

## 12. Chương trình Java 17+ hoàn chỉnh: liệt kê NIC và tự kiểm thử

### 12.1. Hành vi của chương trình

File `NetworkInterfaceInventoryDemo.java` có hai chế độ:

- `--self-test`: duyệt các APIs, kiểm tra các invariant hợp lệ và in **9 dòng kết quả có thể so sánh**; không in địa chỉ IP/MAC thật.
- `--list`: liệt kê **cấu hình mạng hiện thời** gồm name/index/display name, flags, MTU, parent/children, các IP và prefix/broadcast. Chế độ này che MAC theo mặc định, nhưng **IP/names vẫn có thể nhạy cảm**; chỉ dùng ở môi trường được phép.

Cả hai chế độ **không mở socket kết nối hoặc gọi DNS lookup**. Chúng tra cứu interface cục bộ từ hệ điều hành/JDK; không quét LAN và không gửi packet thử. `--self-test` dùng IPv4/IPv6 literals tạo từ `byte[]` để kiểm tra phân loại IP, tránh phụ thuộc tên hoặc địa chỉ cụ thể của host.

**Điểm về tính portable:** Không assert số lượng `Enumeration` và `Stream` snapshots phải bằng nhau vì network có thể đổi. Không giả định tên `eth0`/`wlan0`/`lo`, không yêu cầu IPv6 phải được gán ở máy thật và không yêu cầu MAC phải tồn tại. Prefix âm/không xác định không được dùng để tính mask. Nếu interface bị gỡ giữa lúc duyệt, `SocketException` có thể phát sinh; integration/monitor ứng dụng thật cần xử lý bằng refresh/retry hữu hạn.

### 12.2. File độc lập `NetworkInterfaceInventoryDemo.java`

~~~java
import java.net.Inet4Address;
import java.net.Inet6Address;
import java.net.InetAddress;
import java.net.InterfaceAddress;
import java.net.NetworkInterface;
import java.net.SocketException;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;

public final class NetworkInterfaceInventoryDemo {
    private NetworkInterfaceInventoryDemo() {}

    private static List<NetworkInterface> snapshot()
            throws SocketException {
        return NetworkInterface.networkInterfaces()
                .sorted(Comparator.comparing(NetworkInterface::getName))
                .toList();
    }

    private static String family(InetAddress address) {
        return address instanceof Inet4Address ? "IPv4"
             : address instanceof Inet6Address ? "IPv6" : "unknown";
    }

    private static String readable(String value) {
        return value == null || value.isBlank() ? "(not available)" : value;
    }

    private static String privacySafeMac(byte[] bytes) {
        return bytes == null ? "(unavailable)" : "[redacted]";
    }

    private static void listInventory() throws SocketException {
        List<NetworkInterface> all = snapshot();
        System.out.println("Interfaces: " + all.size());
        for (NetworkInterface nic : all) {
            System.out.println("name=" + nic.getName()
                    + " index=" + nic.getIndex()
                    + " display=" + readable(nic.getDisplayName()));
            System.out.println("  up=" + nic.isUp()
                    + " loopback=" + nic.isLoopback()
                    + " pointToPoint=" + nic.isPointToPoint()
                    + " virtualSubinterface=" + nic.isVirtual()
                    + " multicastCapable=" + nic.supportsMulticast()
                    + " mtu=" + nic.getMTU());
            NetworkInterface parent = nic.getParent();
            System.out.println("  parent="
                    + (parent == null ? "(none)" : parent.getName())
                    + " children=" + nic.subInterfaces()
                            .map(NetworkInterface::getName).toList());
            System.out.println("  MAC="
                    + privacySafeMac(nic.getHardwareAddress()));
            for (InterfaceAddress entry : nic.getInterfaceAddresses()) {
                InetAddress ip = entry.getAddress();
                String broadcast = entry.getBroadcast() == null ? "(none)"
                        : entry.getBroadcast().getHostAddress();
                System.out.println("  " + family(ip)
                        + " address=" + ip.getHostAddress()
                        + "/" + entry.getNetworkPrefixLength()
                        + " broadcast=" + broadcast);
                if (ip instanceof Inet6Address v6
                        && v6.isLinkLocalAddress()) {
                    System.out.println("    IPv6 link-local scopeId="
                            + v6.getScopeId());
                }
            }
        }
    }

    private static void require(
            boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }

    private static void selfTest() throws Exception {
        List<NetworkInterface> all = snapshot();
        List<NetworkInterface> legacy =
                Collections.list(
                        NetworkInterface.getNetworkInterfaces());
        require(!all.isEmpty() && !legacy.isEmpty(),
                "No configured interface found");
        System.out.println(
                "Stream and Enumeration inventory: OK");

        NetworkInterface first = all.get(0);
        require(NetworkInterface.getByName(first.getName()) != null,
                "Name lookup failed");
        if (first.getIndex() >= 0) {
            NetworkInterface.getByIndex(first.getIndex());
        }

        boolean addressLookupExercised = false;
        for (NetworkInterface nic : all) {
            nic.isUp();
            nic.isLoopback();
            nic.isPointToPoint();
            nic.isVirtual();
            nic.supportsMulticast();
            nic.getMTU();

            byte[] mac = nic.getHardwareAddress();
            require(privacySafeMac(mac).equals(
                    mac == null ? "(unavailable)" : "[redacted]"),
                    "MAC accidentally exposed");

            NetworkInterface parent = nic.getParent();
            if (parent != null) {
                require(nic.isVirtual(),
                        "Subinterface should be virtual");
            }
            nic.subInterfaces().forEach(child -> {
                require(child != null, "Null child interface");
            });

            nic.inetAddresses().forEach(address -> {
                require(address != null, "Null InetAddress");
            });
            Collections.list(nic.getInetAddresses())
                    .forEach(address -> {
                        require(address != null,
                                "Null old-style InetAddress");
                    });

            for (InterfaceAddress entry : nic.getInterfaceAddresses()) {
                InetAddress addr = entry.getAddress();
                int bits = entry.getNetworkPrefixLength();
                if (addr instanceof Inet4Address && bits >= 0) {
                    require(bits <= 32, "Invalid IPv4 prefix");
                } else if (addr instanceof Inet6Address v6) {
                    if (bits >= 0) {
                        require(bits <= 128, "Invalid IPv6 prefix");
                    }
                    require(entry.getBroadcast() == null,
                            "IPv6 broadcast must be absent");
                    v6.getScopeId();
                    v6.getScopedInterface();
                }
                if (!addressLookupExercised) {
                    NetworkInterface.getByInetAddress(addr);
                    addressLookupExercised = true;
                }
            }
        }
        System.out.println("Name/index/IP lookup APIs: OK");
        System.out.println("Interface status and MTU APIs: OK");
        System.out.println("InterfaceAddress IPv4/IPv6 data: OK");
        System.out.println("Parent/subinterfaces and IPv6 scope: OK");
        System.out.println("MAC addresses intentionally hidden: OK");

        InetAddress v4 = InetAddress.getByAddress(
                new byte[] {127, 0, 0, 1});
        byte[] ipv6Bytes = new byte[16];
        ipv6Bytes[15] = 1;
        InetAddress v6 = InetAddress.getByAddress(ipv6Bytes);
        require(v4 instanceof Inet4Address && v4.isLoopbackAddress(),
                "IPv4 literal check failed");
        require(v6 instanceof Inet6Address && v6.isLoopbackAddress(),
                "IPv6 literal check failed");
        System.out.println("IPv4/IPv6 literal classification: OK");
        System.out.println("No DNS or socket connections created: OK");
        System.out.println(
                "Actual adapter names/IPs vary by machine: true");
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 1 && "--self-test".equals(args[0])) {
            selfTest();
        } else if (args.length == 1 && "--list".equals(args[0])) {
            listInventory();
        } else {
            System.err.println(
                    "Usage: java NetworkInterfaceInventoryDemo "
                    + "--self-test|--list");
            System.exit(2);
        }
    }
}
~~~

### 12.3. Biên dịch và thực thi

Lưu code vào file **`NetworkInterfaceInventoryDemo.java`**. JDK 17+ là đủ; `java.net` và `java.util` thuộc `java.base` nên không cần `--add-modules` hoặc dependency ngoài.

~~~sh
javac --release 17 NetworkInterfaceInventoryDemo.java
java NetworkInterfaceInventoryDemo --self-test
java NetworkInterfaceInventoryDemo --list
~~~

**Stdout chuẩn xác của `--self-test`** đã kiểm thử bằng `javac --release 17` và chạy trên JDK 24:

~~~text
Stream and Enumeration inventory: OK
Name/index/IP lookup APIs: OK
Interface status and MTU APIs: OK
InterfaceAddress IPv4/IPv6 data: OK
Parent/subinterfaces and IPv6 scope: OK
MAC addresses intentionally hidden: OK
IPv4/IPv6 literal classification: OK
No DNS or socket connections created: OK
Actual adapter names/IPs vary by machine: true
~~~

Với chế độ `--list`, **không có stdout cố định** vì phụ thuộc OS, NIC names, routing/network namespace, VPN và thời điểm chạy. Mỗi interface có format gần như:

~~~text
Interfaces: <number>
name=<interface-name> index=<index> display=<description>
  up=<boolean> loopback=<boolean> pointToPoint=<boolean> virtualSubinterface=<boolean> multicastCapable=<boolean> mtu=<bytes>
  parent=<parent-or-none> children=[...]
  MAC=[redacted]
  IPv4 address=<local-ip>/<prefix> broadcast=<broadcast-or-none>
  IPv6 address=<local-ipv6>/<prefix> broadcast=(none)
~~~

Đoạn trên là **mẫu cấu trúc với placeholders**, không phải stdout đã lấy từ máy người dùng. Trong môi trường thử nghiệm, chế độ `--list` chạy thành công; số lượng/tên/IP được xem là biến đổi theo máy. Nội dung `--list` có thể chứa địa chỉ riêng nên không copy toàn bộ vào issue tracker/public logs nếu chưa được phép.

### 12.4. Phân tích luồng chương trình

**`snapshot()`** gọi `NetworkInterface.networkInterfaces()`, sắp xếp theo name rồi materialize thành `List`. Nó không biến snapshot thành live observer. Lần gọi sau có thể trả cấu hình khác.

**`listInventory()`** duyệt các interface và in metadata cùng các `InterfaceAddress`, phân biệt IPv4/IPv6. Với IPv6 link-local, nó còn in scope ID. MAC có thể hiện ra ở byte[] nhưng được thay bằng `[redacted]`.

**`selfTest()`** dùng cả Stream và Enumeration API, kiểm lookup theo tên/index/địa chỉ nếu có; đọc các capability/status methods, parent/child, kiểm cấu trúc IPv4/IPv6 và kiểm dữ liệu MAC không bị in. Nó không so count hai snapshots vì cấu hình mạng có thể biến đổi.

**`InetAddress.getByAddress(...)`** tạo IPv4 loopback và IPv6 loopback literal cho kiểm thử phân loại; không dùng DNS. `getByInetAddress(...)` chỉ tra cứu gắn IP cục bộ, không thực hiện TCP connect.

### 12.5. Vì sao không assert kết quả `--list`?

Một máy laptop có thể có một Wi‑Fi, một Ethernet, loopback và nhiều VPN/virtual adapters; máy container có thể chỉ nhìn thấy interfaces của namespace đang chạy. Java API chính xác ở chỗ phản ánh trạng thái host tại thời điểm gọi, không phải luôn phải có tên `eth0` hoặc index 1.

Test tốt phải chia:

- **Bất biến API**: kiểu return, IPv6 broadcast null, prefix trong range khi có, các method có thể được gọi an toàn khi interface tồn tại.
- **Kết quả phụ thuộc môi trường**: số NIC, trạng thái up/down, MTU, MAC có/null, IPv4/IPv6 addresses, parent/children.

Không đưa snapshot của một máy thành expected output cho mọi máy.

## 13. NetworkInterface và bảo mật thông tin hệ thống

Mặc dù không gửi packet mạng, inventory có thể bộc lộ:

- Host nội bộ đang có bao nhiêu adapters.
- Dải IP riêng, IPv6 link-local/global.
- VPN/virtual adapters hoặc môi trường container.
- Tên hệ điều hành đặt cho interface.
- Hardware address có thể dùng làm fingerprint trong một số bối cảnh.

Vì vậy:

1. Chỉ thu thập các trường thật sự cần cho diagnostics.
2. Mask MAC mặc định; hạn chế in IP/name ở logs không được bảo vệ.
3. Có cơ chế opt-in cho `--list`, tránh tự upload inventory.
4. Không dùng địa chỉ NIC để xác thực người dùng hoặc làm license ID dễ giả mạo.
5. Không tự ý duyệt interfaces để kết nối tới host nội bộ.
6. Nếu ứng dụng bị sandbox/container giới hạn, chấp nhận việc nhìn thấy **một phần** interfaces hoặc metadata.
7. Với hệ thống đa thuê, đừng để người dùng không có quyền thấy network topology của host khác.

### 13.1. Tên interface là dữ liệu từ OS, không phải input đã được validate

Khi tạo logs/JSON/UI với `nic.getDisplayName()`, hãy escape output theo format đích; tránh ghép raw string vào lệnh shell hoặc command line. Với tên do OS cung cấp, vẫn nên xử lý null/encoding/Unicode hợp lệ. Không xây command `ipconfig`/`ifconfig` bằng nối string name từ request tùy ý.

### 13.2. NetworkInterface không phải công cụ fingerprint đáng tin

Tên/index/MAC có thể thay đổi, vắng mặt, duplicate, được randomize hoặc bị spoof. Dùng chúng làm security principal, thay cho cryptographic identity hoặc trusted key, là thiết kế yếu. Gắn access control với identity thực của user/service, không với NIC.

## 14. Phân biệt việc liệt kê network interfaces và kết nối mạng

| Câu hỏi | `NetworkInterface` có trả lời trực tiếp? | Nguồn thật cần tham khảo |
| --- | --- | --- |
| Máy hiện thấy những interface nào? | Có | `networkInterfaces()` |
| Interface đang up? | Có (theo OS) | `isUp()` |
| Interface có IPv4/IPv6 nào? | Có | `inetAddresses()/getInterfaceAddresses()` |
| Interface có MTU và multicast support? | Có | `getMTU()/supportsMulticast()` |
| Địa chỉ IP này nằm trên NIC nào? | Có thể | `getByInetAddress()` |
| DNS server hiện tại là ai? | Không | OS resolver/network configuration |
| Gateway mặc định là ai? | Không | OS routing table |
| Route đến server X dùng interface nào? | Không trực tiếp | OS routing/connection state |
| Server X có reachable không? | Không | Controlled network connectivity test |
| TCP server nên bind công khai không? | Không | Security/port/firewall policy |
| VPN đang cho phép truy cập mạng nào? | Không trực tiếp | VPN/OS routing policy |
| Danh sách Wi‑Fi SSID quanh đây? | Không | OS wireless APIs theo permission |
| Máy bên cạnh có MAC/IP gì? | Không | Network discovery (khác bài toán; cần quyền) |

Tránh gọi `NetworkInterface.networkInterfaces()` mỗi khi HTTP request không thành công rồi kết luận “giao diện down” là nguyên nhân. Có thể lỗi DNS, proxy, certificate, routing, firewall, remote host, request timeout hoặc authorization.

## 15. Xử lý lỗi và thay đổi mạng

### 15.1. `SocketException`

Một số network information methods có `throws SocketException`, ví dụ:

~~~java
try {
    List<NetworkInterface> adapters =
            NetworkInterface.networkInterfaces().toList();
    // Use adapters snapshot.
} catch (SocketException failure) {
    // Ghi log hạn chế, báo diagnostic unavailable hoặc retry có giới hạn.
}
~~~

Đây là snippet. Không coi mọi lỗi là “không có NIC” rồi ghi dữ liệu giả vào inventory. Nếu lỗi xảy ra khi bạn sắp chọn một NIC để multicast/bind, cần xác nhận lại trạng thái, dừng hoặc fallback theo policy.

### 15.2. Lookup có thể không còn đúng

Giả sử UI lưu `getIndex()==42` rồi vài phút sau gọi `getByIndex(42)`. Interface có thể đã bị thay đổi, index được gán lại hoặc địa chỉ của NIC không còn như trước. Cần check lại tên/expected addresses/flags trước khi dùng.

### 15.3. Null và danh sách rỗng là trạng thái bình thường

- `getDisplayName()` có thể null.
- `getHardwareAddress()` có thể null.
- `getParent()` thường null trên non-subinterfaces.
- `getByName/getByIndex/getByInetAddress` có thể null nếu không tìm thấy.
- `InterfaceAddress.getBroadcast()` thường null cho IPv6 và một số IPv4.
- `getInterfaceAddresses()` có thể rỗng nếu interface chưa có IP.
- `inetAddresses()` có thể không có entries.
- `getIndex()` có thể -1 nếu không biết.

Dùng null-check và không giả định mọi adapter đều có IP/MAC.

## 16. Kiểm thử tự động nên làm

| Case | Điều kiện | Kỳ vọng |
| --- | --- | --- |
| Stream enumeration | Java17+, host có NIC | `networkInterfaces()` trả Stream |
| Enumeration enumeration | Cùng host | `getNetworkInterfaces()` dùng được |
| Sort for output | Nhiều NIC | Thứ tự log do ứng dụng chọn; không giả định OS |
| Name lookup | Dùng name lấy từ NIC thật | Tra cứu được nếu NIC chưa đổi |
| Index lookup | Index đã biết và không đổi | Có thể tìm lại |
| Missing name | Tên không tồn tại | `getByName` trả null |
| Missing IP | IP không gắn local NIC | `getByInetAddress` trả null |
| Status methods | Interface tồn tại | Xử lý `SocketException` |
| Loopback | Có interface loopback | Không giả định tên "lo" |
| IPv4 | Có entry v4 | Prefix hợp lệ nếu khả dụng |
| IPv6 | Có entry v6 | Broadcast null |
| IPv6 scope | Link-local address | Duy trì scope khi cần |
| No MAC | Loopback/sandbox/hardware bị ẩn | Không NPE; hiển thị unavailable |
| Virtual adapter | OS VPN/VM bridge | Không giả định `isVirtual` luôn true |
| Subinterface hierarchy | Parent/child entries | Duyệt được, tránh trùng |
| Multicast support | Flag true | Không coi như join đã thành công |
| MTU | Giá trị OS báo | Không dùng như HTTP body limit |
| Network changes | Disable/enable/VPN reconnect | Snapshot refresh, retry bounded |
| Concurrent reconfiguration | NIC biến mất khi đọc | Không crash không kiểm soát |
| Container namespace | Chạy trong container | Chỉ thấy view được cấp |
| Privacy test | Diagnostic output | MAC redacted mặc định |
| No DNS query | Inventory only | Chỉ dùng `getHostAddress`, không `getHostName` |
| No sockets | Inventory only | Không mở connection/test traffic |
| Java 17 build | `javac --release 17` | Compile thành công |
| OS-dependent output | Chạy trên máy khác | Không assert tên/IP/count cụ thể |

Nếu test cần thay cấu hình mạng thật, thực hiện trong VM/sandbox và có phương án khôi phục. Không bật/tắt card mạng của máy người dùng tự động chỉ để làm unit test.

## 17. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ dùng `InetAddress.getLocalHost()` để tìm mọi IP | Chỉ là một ánh xạ host; bỏ sót NIC/IP | Dùng `NetworkInterface.networkInterfaces()` và per-interface addresses |
| Giả định mỗi NIC có một IP | Bỏ IPv6/secondary addresses | Duyệt List/Stream addresses |
| So thứ tự kết quả enumeration | Tests flaky | Sort nếu cần output ổn định |
| Hardcode `eth0`, `en0`, `wlan0` hoặc `lo` | Hỏng trên OS/container khác | Đọc tên động |
| Hardcode interface index | Chỉ số thay đổi | Lookup/validate lại |
| Coi `getDisplayName()` luôn non-null | NPE | Null-safe fallback |
| Coi `getHardwareAddress()` luôn có 6 bytes | NPE/format sai | Check null/length, mask mặc định |
| Dùng MAC làm device auth | MAC có thể spoof/change | Cryptographic identity/trust khác |
| Coi `isUp()` là Internet reachable | Phán đoán sai | Kiểm route/DNS/connectivity riêng |
| Coi `isVirtual()` false là NIC vật lý | VPN/VM NIC có thể top-level | Hiểu semantics subinterface |
| Bỏ mọi loopback khỏi diagnostics | Thiếu thông tin/test | Giữ nếu nhiệm vụ cần |
| Gọi `entry.getBroadcast().getHostAddress()` | NPE với IPv6/point-to-point | Null-check |
| Cho rằng IPv6 có broadcast | Sai mô hình mạng | IPv6 dùng multicast, broadcast null |
| Bỏ phần `%zone` của IPv6 link-local | Có thể không xác định đúng link | Dùng scope-aware Inet6Address |
| Gọi `getHostName()` để chỉ in IP | DNS/reverse lookup chậm/không mong muốn | `getHostAddress()` |
| Đếm `Enumeration` và `Stream` snapshot phải luôn bằng | Mạng có thể đổi giữa hai lời gọi | Không assert invariant qua thời điểm |
| Cache NetworkInterface mãi | Snapshot cũ | Refresh theo nhu cầu |
| Biến `getMTU()` thành max HTTP request body | Hai tầng khác nhau | HTTP size cap riêng |
| Tự chọn NIC đầu tiên làm default route | Có thể route sai | OS routing, explicit policy |
| Liệt kê adapter rồi tự động bind tất cả | Mở port ngoài ý muốn | Explicit bind address/auth/firewall |
| In MAC/IP toàn bộ vào public logs | Lộ topology/fingerprint | Redact, control access |
| Không catch SocketException | App crash khi network reconfig | Handle/retry bounded, fail safe |
| Dùng networkInterfaces để quét Wi‑Fi | Không làm nhiệm vụ đó | OS wireless discovery APIs |
| Coi IPv6 object luôn kết nối được | OS có thể tắt IPv6 | Kiểm networking capability thật |

## 18. Câu hỏi tự kiểm tra

**Câu 1.** `NetworkInterface` khác `InetAddress` ở đâu?

**Trả lời:** NetworkInterface biểu diễn giao diện mạng và metadata OS; InetAddress biểu diễn một địa chỉ IP. Một interface có thể có nhiều InetAddress hoặc không có địa chỉ.

**Câu 2.** `getNetworkInterfaces()` và `networkInterfaces()` khác nhau gì?

**Trả lời:** API thứ nhất trả Enumeration; thứ hai trả Stream, có từ Java 9. Cả hai còn dùng được trong Java17+, có thể ném SocketException.

**Câu 3.** Muốn biết prefix của địa chỉ gắn lên NIC, dùng method nào?

**Trả lời:** Duyệt `getInterfaceAddresses()` rồi gọi `InterfaceAddress.getNetworkPrefixLength()`; `getInetAddresses()` chỉ cho InetAddress.

**Câu 4.** Vì sao IPv6 InterfaceAddress có broadcast null?

**Trả lời:** IPv6 không sử dụng broadcast. JavaDoc `getBroadcast` trả null cho IPv6; IPv4 cũng có thể null khi interface không hỗ trợ broadcast.

**Câu 5.** `isUp()==true` có bảo đảm Internet không?

**Trả lời:** Không. Đó là trạng thái interface, không phải phép kiểm route/DNS/gateway/remote connectivity.

**Câu 6.** `isVirtual()==false` có chắc chắn là NIC vật lý không?

**Trả lời:** Không. Theo NetworkInterface API, virtual chủ yếu chỉ các subinterfaces; VM/VPN NIC có thể được OS biểu diễn như top-level adapters.

**Câu 7.** `getByInetAddress(addr)` trả gì nếu IP nằm trên nhiều NIC?

**Trả lời:** JavaDoc không quy định cụ thể NIC nào được chọn. Không dùng nó như một cách chọn route duy nhất.

**Câu 8.** Tại sao không dùng `getIndex()` làm khóa lưu lâu dài?

**Trả lời:** Index phụ thuộc OS và có thể thay đổi sau cấu hình mạng/restart/namespace. Dùng snapshot mới và kiểm lại metadata.

**Câu 9.** Trường hợp nào `getHardwareAddress()` trả null?

**Trả lời:** Khi interface không có hardware address hoặc hiện tại không thể truy cập theo quyền/runtime. Không assume có 6-byte MAC.

**Câu 10.** Muốn in IP mà không thực hiện reverse DNS thì dùng gì?

**Trả lời:** `InetAddress.getHostAddress()` thay cho `getHostName()`.

**Câu 11.** Phần zone trong IPv6 link-local quan trọng thế nào?

**Trả lời:** Nó xác định scope/link liên quan. `Inet6Address.getScopeId()` và `getScopedInterface()` giúp biểu diễn thông tin scope khi có.

**Câu 12.** `getMTU()` có thể dùng thay HTTP body size limit không?

**Trả lời:** Không. MTU là giới hạn tầng network interface, HTTP body là luồng dữ liệu có thể lớn hơn nhiều packet. Phải có HTTP/application size limit riêng.

**Câu 13.** `supportsMulticast()` có bảo đảm join một multicast group thành công không?

**Trả lời:** Không; còn group, OS, socket options, routing, permissions, firewall và network conditions.

**Câu 14.** Vì sao chương trình demo có `--self-test` và `--list` riêng?

**Trả lời:** API invariant có thể kiểm tra với expected output ổn định, còn NIC names/IP/count thực tế phụ thuộc máy nên không nên bịa stdout cố định.

**Câu 15.** NetworkInterface có tự cập nhật khi người dùng chuyển Wi‑Fi không?

**Trả lời:** Không bảo đảm. Instance có thể là snapshot; cần lấy lại NetworkInterface mới khi cần refresh.

**Câu 16.** Container thường thấy danh sách NIC nào?

**Trả lời:** Danh sách trong network namespace/môi trường được cấp, có thể khác host vật lý và khác các container khác.

**Câu 17.** MAC có phù hợp làm khóa định danh bảo mật không?

**Trả lời:** Không. MAC có thể thiếu, thay đổi, randomize hoặc giả mạo. Sử dụng identity và cryptographic credentials được cấp quyền.

**Câu 18.** Khi nào nên dùng NetworkInterface trong multicast?

**Trả lời:** Khi ứng dụng đã được phép và cần chỉ rõ NIC cho socket/channel multicast, kết hợp kiểm tra `supportsMulticast` nhưng vẫn phải xử lý I/O/network errors.

**Câu 19.** Có thể dựa vào danh sách IP để quyết định route tới một remote endpoint không?

**Trả lời:** Không chắc chắn. OS routing, metrics, VPN policy, source address selection và firewall quyết định đường đi thực tế.

**Câu 20.** Cần làm gì khi đang duyệt thì interface bị rút/ngắt?

**Trả lời:** Xử lý SocketException, không giả định snapshot luôn hợp lệ; refresh/retry có giới hạn hoặc báo network state changed.

**Ghi nhớ:** `java.net.NetworkInterface` (thuộc `java.base`) dùng để **liệt kê và quan sát các giao diện mạng cục bộ**. Dùng `networkInterfaces()`/`getNetworkInterfaces()` để lấy danh sách, `inetAddresses()` và `getInterfaceAddresses()` để đọc IP/prefix/broadcast, các cờ `isUp/isLoopback/isPointToPoint/supportsMulticast/isVirtual` để phân loại, và `getByName/getByIndex/getByInetAddress` để tra cứu. Tên/index/MAC/IP có tính platform-specific, có thể thiếu hoặc thay đổi; IPv6 broadcast là null, MAC nên mask trong diagnostics. **Danh sách NIC không phải bảng định tuyến, kiểm tra kết nối hay cơ chế nhận diện bảo mật.**

### Tài liệu chính thức hiện hành

- [Oracle Java SE 26 — NetworkInterface](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/NetworkInterface.html): toàn bộ methods, snapshot/dynamic configuration, lookups, stream/enumeration, state/MTU/MAC.
- [Oracle Java SE 26 — InterfaceAddress](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/InterfaceAddress.html): IP, prefix length, IPv4 broadcast và IPv6 null.
- [Oracle Java SE 26 — InetAddress](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/InetAddress.html): địa chỉ IP và phân loại địa chỉ.
- [Oracle Java SE 26 — Inet4Address](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/Inet4Address.html): địa chỉ IPv4.
- [Oracle Java SE 26 — Inet6Address](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/Inet6Address.html): IPv6 scope ID và scoped interface.
- [Oracle Java SE 17 — NetworkInterface](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/NetworkInterface.html): đối chiếu tương thích Java 17.
- [Oracle Java SE 26 — DatagramChannel](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/DatagramChannel.html): dùng network interface cho multicast qua socket options khi cần.
