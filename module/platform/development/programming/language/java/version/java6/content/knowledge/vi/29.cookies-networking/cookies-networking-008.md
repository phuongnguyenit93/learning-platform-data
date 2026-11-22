# MTU, địa chỉ phần cứng và trạng thái giao diện mạng trong Java

## 1. Mục tiêu của bài học

Khi debug một ứng dụng Java không gửi được gói tin, không tham gia được multicast, hoặc gặp lỗi trên VPN/Wi-Fi/Ethernet, bước đầu tiên thường là tìm hiểu **giao diện mạng (network interface)** mà hệ điều hành cung cấp. Java có API chuẩn **`java.net.NetworkInterface`** để khám phá các giao diện mạng cục bộ, kiểm tra trạng thái, MTU, phần cứng và địa chỉ IP được gán.

Bài **“MTU, địa chỉ phần cứng và trạng thái giao diện”** thuộc nhóm **Cookie và mạng**, tập trung vào khả năng chẩn đoán mạng ở tầng máy chủ/client chứ không phải HTTP cookie. Những phương thức quan trọng đều đang có trong **Java SE 26**, package `java.net` của module `java.base`.

Bạn sẽ biết:
1. **MTU (Maximum Transmission Unit)** là gì, đọc bằng `NetworkInterface.getMTU()` và hiểu đúng phạm vi của nó.
2. **Hardware address** thường là MAC: đọc bằng `getHardwareAddress()`, xử lý `null` và độ dài byte thay đổi.
3. **Trạng thái giao diện**: `isUp()`, `isLoopback()`, `isPointToPoint()`, `supportsMulticast()` và `isVirtual()`.
4. Tìm giao diện với `networkInterfaces()`, `getByName()`, `getByIndex()`, `getByInetAddress()` và đọc IPv4/IPv6 addresses/prefix.
5. Phân biệt link interface UP với việc **thực sự kết nối được tới một dịch vụ/Internet**.
6. Phân biệt interface MTU với **path MTU**, tránh coi một con số local là đảm bảo payload TCP/UDP đi được tới đích.
7. Hiểu vì sao MAC và interface index/name **không phải device ID vĩnh viễn**, không nên dùng làm khóa bảo mật hay fingerprint người dùng.
8. Tránh nhầm `isVirtual()` với khái niệm “máy ảo” hay “mọi adapter do phần mềm tạo”.
9. Xử lý `SocketException`, thay đổi cấu hình động, missing data và privacy khi ghi diagnostics.
10. Chạy ví dụ **Java 17+** có **36/36 assertions PASS** trên OpenJDK 24, kết hợp kiểm thử synthetic MTU/MAC và quan sát interfaces thật mà **không in tên, IP, MAC của máy**.

**Phạm vi hiện hành:** Sử dụng `NetworkInterface`, `InterfaceAddress`, `InetAddress` và `HexFormat` (Java 17), không hướng dẫn các API nội bộ/lỗi thời. Mã nguồn được biên dịch bằng `javac --release 17` và đã chạy trên OpenJDK 24. Kết quả mạng thật là dữ liệu OS thay đổi theo máy; bài **không** mặc định mọi laptop đều có Ethernet MTU 1500 hay một MAC sáu byte.

## 2. Mô hình: giao diện mạng trong Java là gì?

`NetworkInterface` là một abstraction của Java cho **network adapter / interface** được hệ điều hành nhìn thấy. Nó có thể đại diện cho card mạng vật lý, loopback, một logical interface, một tunnel hoặc một adapter do phần mềm cấu hình. Một object này có thể có **0, 1 hoặc nhiều IP addresses**, có thể có hoặc không có hardware address.

```text
Java application
     |
     v
java.net.NetworkInterface  [local OS view]
     |
     +-- getName(), getDisplayName(), getIndex()
     +-- getMTU()
     +-- getHardwareAddress() -> byte[] hoặc null
     +-- isUp()
     +-- isLoopback()
     +-- isPointToPoint()
     +-- supportsMulticast()
     +-- isVirtual(), getParent(), subInterfaces()
     +-- inetAddresses() -> IPv4/IPv6 addresses
     +-- getInterfaceAddresses() -> address + prefix + broadcast
     |
     v
Operating system network configuration
     |
     +-- Ethernet / Wi-Fi
     +-- Loopback
     +-- VPN / tunnel / virtual network adapter
     +-- VLAN subinterface (nếu OS biểu diễn như vậy)
```

**Quan trọng:** `NetworkInterface` mô tả *giao diện của host*, không phải một object đại diện cho Internet connection, TCP socket hay một route đến mọi đích. Một host có thể có nhiều interfaces và route quyết định interface nào được dùng để liên lạc với một địa chỉ cụ thể.

### 2.1. Ba lớp cần tách biệt

| Thông tin | Ví dụ | API/thành phần |
| --- | --- | --- |
| **Interface** | Wi-Fi, Ethernet, loopback, tunnel | `NetworkInterface` |
| **IP address/route** | IPv4/IPv6 đã gán, prefix, bảng định tuyến | `InetAddress` / `InterfaceAddress` và OS routing |
| **End-to-end connectivity** | Có kết nối được đến đúng host:port/protocol không | Socket/HTTP client với timeout và policy |

- Một interface UP chưa chắc có gateway.
- Một interface có IP không chắc phân giải DNS được.
- Địa chỉ IP tồn tại trên interface không chắc app được firewall cho phép sử dụng.
- Kết nối tới localhost thành công không chứng minh Internet hoạt động.
- MTU của interface không phải MTU của toàn bộ đường đi tới server.

### 2.2. Object có thể phản ánh snapshot

Javadoc `NetworkInterface` trên Java SE 26 nhấn mạnh **cấu hình mạng thay đổi trong thời gian JVM chạy**. Một số thuộc tính trong object nhận được phản ánh cấu hình **tại thời điểm object được tạo**, đặc biệt danh sách addresses và tên. Việc interface chuyển Wi-Fi/VPN, đổi IP, disable/enable, container attach/detach có thể khiến snapshot cũ không còn chính xác.

Khi cần view mới, hãy **enumerate hoặc lookup lại** từ OS; không coi object cũ, tên hay index là định danh ổn định vĩnh viễn.

## 3. Tổng quan API `java.net.NetworkInterface`

| API | Kết quả | Cần xử lý |
| --- | --- | --- |
| `NetworkInterface.networkInterfaces()` | `Stream<NetworkInterface>` | Có thể ném `SocketException`; Java 9+ |
| `NetworkInterface.getNetworkInterfaces()` | `Enumeration<NetworkInterface>` | API vẫn hợp lệ, hữu ích khi tương tác code cũ |
| `getByName(String)` | Interface theo tên OS | `null` nếu không tìm thấy |
| `getByIndex(int)` | Interface theo index OS | `null` nếu không tìm thấy; negative index không hợp lệ |
| `getByInetAddress(InetAddress)` | Interface sở hữu IP đã gán | Có thể `null` |
| `getName()` | Tên hệ điều hành, ví dụ tùy nền tảng | Không dùng tên cố định như `eth0` trên mọi máy |
| `getDisplayName()` | Tên dễ đọc nếu có | Có thể `null` |
| `getIndex()` | Index do OS định nghĩa | `-1` nếu không biết; thay đổi được |
| `getMTU()` | MTU do giao diện báo | `SocketException`; không mặc định 1500 |
| `getHardwareAddress()` | `byte[]` địa chỉ hardware, thường MAC | `null` nếu không có/không truy cập được |
| `isUp()` | Giao diện đang up/running ở góc nhìn OS | Không chứng minh có Internet |
| `isLoopback()` | Đây có phải loopback interface không | Độc lập với `isUp` |
| `isPointToPoint()` | Giao diện point-to-point? | Không suy tuyến Internet |
| `supportsMulticast()` | Interface có hỗ trợ multicast? | Không đảm bảo có thể join/tới group |
| `isVirtual()` | Có phải **subinterface** theo model của JDK? | Không phải mọi adapter “ảo” |
| `getParent()` | Parent interface hoặc `null` | Không có parent chưa chứng minh vật lý |
| `subInterfaces()` | Stream subinterfaces (Java 9+) | Có thể rỗng |
| `inetAddresses()` | Stream IP addresses được gán (Java 9+) | Có thể rỗng |
| `getInterfaceAddresses()` | Danh sách `InterfaceAddress` | Có thể rỗng |

`networkInterfaces()` là dạng hiện đại dùng `Stream`, hợp lệ trong source target Java 17. `getNetworkInterfaces()` dạng `Enumeration` **vẫn được hỗ trợ**; không gọi nó là API bị loại bỏ. Trong demo, cả hai được gọi để xác nhận có thể enumerate interfaces.

## 4. Liệt kê giao diện mạng theo cách hiện hành

### 4.1. Dùng Stream (Java 9+)

```java
import java.net.NetworkInterface;
import java.net.SocketException;
import java.util.List;

static List<NetworkInterface> listInterfaces()
        throws SocketException {
    return NetworkInterface.networkInterfaces().toList();
}
```

Snippet này cần đặt trong class Java. `Stream.toList()` dùng được từ Java 16, nên chạy với `--release 17`. Đừng giả định số lượng interfaces luôn là 1. Linux containers, Windows adapters và cloud hosts thường có cấu hình rất khác nhau.

Tài liệu Javadoc nói `networkInterfaces()` trả ít nhất một interface nếu môi trường có cấu hình phù hợp, có thể chỉ là loopback. Nếu platform không có interface nào hoặc I/O failure, có thể ném `SocketException`.

### 4.2. Dùng Enumeration khi tương tác API cũ

```java
List<NetworkInterface> interfaces =
        java.util.Collections.list(
                NetworkInterface.getNetworkInterfaces());
```

Cách này vẫn hợp lệ, không cần ép chuyển hết source cũ chỉ vì thích Stream. Với code mới trên Java 17+, Stream thường dễ kết hợp `filter`/`map`/`toList` hơn.

### 4.3. Chỉ liệt kê giao diện đang UP

```java
for (NetworkInterface nic
        : NetworkInterface.networkInterfaces().toList()) {
    try {
        if (nic.isUp()) {
            // Process this interface, but do not assume Internet works.
        }
    } catch (SocketException transientFailure) {
        // The interface may have changed/disappeared.
    }
}
```

Không dùng `nic.isUp()` trực tiếp trong `Stream.filter` nếu không quản lý checked `SocketException`. Bắt lỗi đúng chỗ và cân nhắc retry một lượt scan mới. Không tự đổi một exception thành `false` rồi lặng lẽ kết luận “giao diện DOWN” khi thực chất là “không đo được”.

### 4.4. Lookup khi đã biết interface hoặc địa chỉ IP

```java
NetworkInterface byName =
        NetworkInterface.getByName("my-interface-name");

NetworkInterface byIndex =
        NetworkInterface.getByIndex(1);

NetworkInterface byAddress =
        NetworkInterface.getByInetAddress(
                java.net.InetAddress.getLoopbackAddress());
```

Đây là snippets; các phương thức có thể ném `SocketException`, và kết quả có thể `null`. Tên `my-interface-name` và index `1` **không phải tên/index đảm bảo tồn tại** trên máy bạn. Khi có interface object, `getName()` và `getIndex()` có thể làm key để lookup lại trong vòng đời ngắn, nhưng **không** làm ID vĩnh viễn.

`getByIndex(-1)` có thể ném `IllegalArgumentException` theo API; kiểm tra index trước khi dùng.

## 5. MTU: giới hạn kích thước truyền trên giao diện

**MTU** viết tắt của **Maximum Transmission Unit**. Với Ethernet, MTU điển hình đề cập đến **kích thước tối đa của IP packet/frame payload ở tầng liên kết**, thường 1.500 bytes với cấu hình Ethernet phổ biến. Các công nghệ khác, tunnel, VPN, PPPoE và loopback có thể có giá trị khác. “MTU = 1500” **không phải hằng số của Java**.

API:

```java
int mtu = networkInterface.getMTU();
```

`NetworkInterface.getMTU()` trả MTU do interface cung cấp và có thể ném `SocketException`. Đối tượng `NetworkInterface` không cung cấp method `setMTU(int)` để sửa giá trị này. Thay đổi MTU là việc cấu hình OS/driver/network policy, thường cần quyền quản trị.

### 5.1. MTU không phải kích thước dữ liệu ứng dụng

```text
Application writes bytes
         |
         v
TCP/UDP segments or datagrams
         |
         +-- Transport header (TCP/UDP)
         |
         v
IP packets
         +-- IP header (IPv4/IPv6)
         |
         v
Network interface / link layer
         +-- interface MTU governs packet size on this link
         |
         v
Router / VPN / tunnels / other links
         +-- Path MTU may be LOWER than local interface MTU
```

Ví dụ **chỉ để minh họa phép trừ** khi MTU là 1500, IPv4 header **không có options** 20 bytes, TCP header **không có options** 20 bytes:

```text
1500 - 20 - 20 = 1460 bytes
```

1460 là **payload theo cấu hình header tối thiểu của ví dụ**, không phải lời hứa rằng mọi TCP socket có MSS = 1460 hoặc một lần `OutputStream.write()` tương ứng đúng một TCP packet. TCP là byte stream; segmentation, MSS negotiation, options, encapsulation, IPv6 và path MTU đều ảnh hưởng.

Nếu có thêm overhead giả định 60 bytes do encapsulation/tunnel trong bài toán minh họa:

```text
1500 - 20 - 20 - 60 = 1400 bytes
```

Không cộng/trừ overhead thực tế một cách tùy tiện. Định dạng tunnel, vị trí MTU được đo và headers trên đường đi phải được xác minh trước khi dùng để chọn kích thước packet.

### 5.2. Interface MTU khác Path MTU

| Thuộc tính | Interface MTU | Path MTU |
| --- | --- | --- |
| Phạm vi | Một interface tại host | Tập các liên kết trên tuyến đến **đích cụ thể** |
| Java API | `NetworkInterface.getMTU()` | Không được trả trực tiếp bởi method này |
| Có thể thay đổi vì | Cấu hình adapter/driver/VPN | Route, tunnel, link khác, chính sách mạng |
| Ý nghĩa | Giới hạn local link đang báo | Giới hạn hiệu quả theo tuyến tại thời điểm đo |

**Không lấy `getMTU()` rồi dùng nó như path MTU cho một TCP/UDP destination bất kỳ**. Với UDP lớn, vấn đề fragmentation, PMTU discovery và ICMP filtering có thể khiến gói tin thất bại. Với TCP, stack hệ điều hành xử lý segmentation theo chính sách của nó; application không tự cần chia mọi message theo đúng MTU để TCP hoạt động.

### 5.3. MTU của loopback / VPN / Wi-Fi

- **Loopback** không đi qua card Ethernet vật lý; MTU có thể khá lớn và hoàn toàn khác 1500.
- **VPN/tunnel** thường có encapsulation overhead; MTU hiệu quả có thể thấp hơn underlying link.
- **Wi-Fi** vẫn thường mang IP packet dưới các quy tắc link riêng; đừng đồng nhất MTU với 802.11 PHY frame size.
- **Jumbo frames** có thể nâng MTU trên các đường Ethernet được cấu hình đồng bộ, nhưng không áp tự động toàn Internet.
- Một host có nhiều interfaces, mỗi interface có MTU riêng và route cụ thể chọn interface.

### 5.4. Cần làm gì khi MTU không khả dụng?

Oracle Javadoc `getMTU()` quy định trả `int` và có thể ném `SocketException`, **không định nghĩa một sentinel `-1` portable cho mọi nền tảng**. Vì vậy:
- Nếu gọi thất bại, ghi trạng thái **ERROR/UNKNOWN**, không coi là MTU = 1500.
- Nếu implementation trả giá trị **không dương**, không dùng nó làm giới hạn packet hợp lệ; báo “không khả dụng/không dùng được” ở tầng application.
- Một API helper có thể hiển thị số thực dương và fallback cho các trường hợp không dương; đó là **defensive application policy**, không phải contract rằng JDK luôn trả `-1` khi thiếu dữ liệu.

## 6. Hardware address / MAC address

`getHardwareAddress()` trả một mảng bytes đại diện cho địa chỉ phần cứng, **thường là MAC**:

```java
byte[] hardware = networkInterface.getHardwareAddress();
```

Theo Javadoc Java SE 26:
- Kết quả có thể là `null` khi interface không có hardware address hoặc thông tin không truy cập được.
- Có thể ném `SocketException` nếu xảy ra I/O error.
- Không hứa mảng luôn dài 6 bytes.
- Không đảm bảo mọi interface giống Ethernet hoặc có một địa chỉ MAC mà ứng dụng được phép đọc.

### 6.1. Không dùng MAC làm ID người dùng hay khóa bảo mật

Một hardware address:
- Có thể bị OS/driver **thay đổi**, thiết bị có thể dùng randomized/local-administered address.
- Có thể không tồn tại trên loopback/tunnel.
- Có thể giống nhau giữa các môi trường clone nếu bị cấu hình sai.
- Có thể thay đổi giữa network profiles, adapters hoặc phiên kết nối.
- Có thể nhạy cảm về privacy khi gắn với một thiết bị/người dùng.

Vì vậy **không dùng MAC như một secret**, **không dùng làm authentication token**, không khóa license chỉ bằng MAC, không lưu vào analytics như stable user tracking identifier khi không có căn cứ và sự đồng ý thích hợp.

Nếu một ứng dụng cần ID instance, hãy dùng ID được ứng dụng tạo và quản trị. Nếu cần device attestation, phải dùng cơ chế platform-specific có trust/crypto, không dựa vào 6 bytes từ `getHardwareAddress()`.

### 6.2. Format bytes đúng với `HexFormat` (Java 17+)

```java
static String formatMac(byte[] bytes) {
    if (bytes == null) return "(unavailable)";
    if (bytes.length == 0) return "(empty)";
    return java.util.HexFormat.ofDelimiter(":")
            .withUpperCase()
            .formatHex(bytes);
}
```

Đây là method Java độc lập nếu đặt trong class, dùng `HexFormat` hiện hành từ Java 17. Không nhầm signed `byte` với giá trị âm trong Java; `HexFormat` diễn giải đúng octets khi format.

Ví dụ **dùng dữ liệu giả lập**:

```text
byte[] {0x00, 0x1A, 0x2B, (byte)0x80, (byte)0xFF, 0x01}
      -> 00:1A:2B:80:FF:01
```

Ví dụ khác 8 bytes:

```text
02:00:00:00:00:00:00:10
```

Không giả định “nếu không có 6 bytes thì lỗi”. Địa chỉ tầng liên kết khác có thể có độ dài khác.

### 6.3. Tại sao demo không in MAC thật?

Tên interface, IP address và MAC có thể là dữ liệu nhạy cảm trong logs/chẩn đoán. Chương trình của bài thực sự gọi `getHardwareAddress()` nhưng chỉ thống kê **có/không có địa chỉ** và độ dài bytes, không in nội dung. Tests format MAC dùng mảng synthetic đã khai báo trong source, nên stdout giữ ổn định và không thu thập fingerprint host.

Trong production monitoring, nếu cần MAC để chẩn đoán, chỉ log theo scope/quyền truy cập phù hợp, redact hoặc hash với context/key theo chính sách và có retention period. Hash một MAC không tự biến nó thành dữ liệu không thể liên kết tới thiết bị.

## 7. Trạng thái giao diện: `isUp()` không đồng nghĩa Online

### 7.1. `isUp()`

```java
boolean up = networkInterface.isUp();
```

Trả `true` nếu interface **up and running** ở góc nhìn OS. Có thể ném `SocketException`. Nhưng `true` **không chứng minh**:
- Tồn tại đường đi đến Internet.
- DNS lookup thành công.
- Router/gateway reachable.
- HTTP service đích trả được response.
- Port không bị firewall chặn.
- Session TLS/tokens còn hợp lệ.

**Quan sát local** và **khả năng kết nối end-to-end** là hai bài toán khác nhau.

### 7.2. `isLoopback()`

Loopback là giao diện mạng trao đổi dữ liệu bên trong cùng host, thường đi với địa chỉ như `127.0.0.1` hoặc `::1`. Nó có thể ở trạng thái UP nhưng **không** chứng minh kết nối Internet.

```java
if (nic.isUp() && !nic.isLoopback()) {
    // A candidate local interface, NOT proof of Internet access.
}
```

### 7.3. `isPointToPoint()`

Một interface point-to-point biểu diễn liên kết giữa hai đầu, có thể gặp ở PPP hoặc một số tunnel. Boolean này phản ánh đặc tính interface, **không** bảo đảm VPN tunnel đã authenticate với gateway hay có route hợp lệ đến một đích cụ thể.

### 7.4. `supportsMulticast()`

Đây là khả năng hỗ trợ multicast của interface. `true` không tự:
- Join một multicast group.
- Mở firewall hoặc IGMP/MLD policy.
- Chọn interface nào được dùng để gửi.
- Đảm bảo đường mạng có multicast forwarding.

Với UDP multicast có thể cần chọn interface bằng `StandardSocketOptions.IP_MULTICAST_IF` hoặc API phù hợp, đăng ký membership và kiểm tra network/router policy.

### 7.5. `isVirtual()` và subinterface

Javadoc định nghĩa `isVirtual()` trong nghĩa **virtual interface / subinterface** — interface được biểu diễn là con của interface khác, có thể được cấu hình các IP/MTU riêng.

**Không suy luận:**
- `isVirtual()==false` ⇒ chắc chắn là card vật lý.
- `isVirtual()==true` ⇒ đang chạy trong máy ảo.
- Có adapter VPN/TAP/VM ⇒ chắc chắn Java sẽ báo `isVirtual()==true`.

Nền tảng OS có thể biểu diễn các adapter phần mềm như interfaces cấp cao độc lập, không được JDK xem là subinterface. Dùng `getParent()` và `subInterfaces()` để xem quan hệ parent/child khi hệ thống hỗ trợ, không biến flag thành taxonomy đầy đủ của mọi adapter.

### 7.6. Phân loại đơn giản cho diagnostics

```java
static String classify(boolean up, boolean loopback,
                       boolean pointToPoint) {
    if (!up) return "DOWN";
    if (loopback) return "LOOPBACK";
    if (pointToPoint) return "POINT_TO_POINT";
    return "UP_LOCAL_INTERFACE";
}
```

Đây là logic **phân loại đơn giản của application**; không phải enum có sẵn trong JDK. `"UP_LOCAL_INTERFACE"` chỉ nghĩa interface không loopback và OS báo UP, **không** nghĩa Internet online. Thứ tự check đặt DOWN lên đầu làm cho một interface DOWN nhưng cũng là loopback được phân loại DOWN trước.

## 8. IP, prefix và broadcast: `InterfaceAddress`

Một interface có thể gán nhiều địa chỉ IPv4/IPv6 hoặc chưa có địa chỉ nào. Java cung cấp:

```java
networkInterface.inetAddresses()
        .forEach(address -> {
            // address is an InetAddress.
        });

for (InterfaceAddress assigned
        : networkInterface.getInterfaceAddresses()) {
    InetAddress address = assigned.getAddress();
    short prefix = assigned.getNetworkPrefixLength();
    InetAddress broadcast = assigned.getBroadcast();
}
```

`InterfaceAddress` chứa:
- `getAddress()`: IP address được gán.
- `getNetworkPrefixLength()`: độ dài network prefix (`short`), ví dụ IPv4 `/24` hoặc IPv6 `/64` theo cấu hình.
- `getBroadcast()`: IPv4 broadcast nếu có, thường **`null` cho IPv6** và interface không hỗ trợ broadcast.

**Không coi `getBroadcast()==null` là lỗi.** IPv6 không có khái niệm broadcast như IPv4; multicast là cơ chế khác.

### 8.1. IPv4 và IPv6 cần được tôn trọng

`InetAddress` có các subtype `Inet4Address` và `Inet6Address`. `getAddress()` trả:
- 4 bytes cho IPv4.
- 16 bytes cho IPv6.

Việc chỉ lọc `Inet4Address` có thể bỏ qua kết nối IPv6 hợp lệ. Ngược lại, một địa chỉ IPv6 link-local có thể cần **scope ID/network interface** khi dùng trên socket; địa chỉ `fe80::...` không tự có ý nghĩa tuyến liên kết nếu thiếu scope.

Chỉ dùng prefix từ OS theo interface, không mặc định `/24` cho mọi IPv4 hoặc `/64` cho mọi IPv6. Một interface có thể có nhiều prefixes và addresses.

### 8.2. `InetAddress.getLocalHost()` không phải cách liệt kê NICs

`InetAddress.getLocalHost()` giải quyết tên host của máy (có thể dựa vào local name resolution). Nó có thể chọn một IP đại diện, **không có nghĩa liệt kê tất cả** interfaces/addresses. Để khảo sát network configuration, dùng `NetworkInterface.networkInterfaces()` và `inetAddresses()`.

### 8.3. Interface address khác remote IP

`getInterfaceAddresses()` phản ánh những IP **được gán cho local interface**. Nó không trả danh sách remote peers hoặc dải mạng mà bạn có quyền truy cập, cũng không tự trả route table. Khi cần biết route đến một đích, phải dùng OS routing hoặc một connection/probe cụ thể; `NetworkInterface` không phải API truy vấn full routing table.

## 9. Tên, index và vòng đời giao diện

`NetworkInterface.getName()` trả tên gắn với OS. `getDisplayName()` có thể `null`. `getIndex()` trả index system-specific, hoặc `-1` nếu unknown, và có thể thay đổi giữa machines/boot/network reconfiguration.

Một pattern chẩn đoán:

```java
NetworkInterface nic =
        NetworkInterface.getByName(configuredName);
if (nic == null) {
    throw new IllegalStateException(
            "Configured interface not found");
}
```

**Dữ liệu `configuredName` phải đến từ cấu hình đáng tin và kiểm tra trên máy triển khai**, không hardcode một tên Linux vào mọi Windows/macOS. Nếu interface biến mất giữa lookup và gọi `getMTU()`, hãy coi đó là transient system error và retry có giới hạn.

### 9.1. Có nên lưu object NetworkInterface lâu dài không?

Không nên coi object là **cache bất biến** của toàn bộ cấu hình. Nếu ứng dụng có service khám phá mạng chạy lâu:
1. Lưu ý định/ràng buộc từ cấu hình ứng dụng (interface name/role hoặc selected address).
2. Trước phép đo mới, lấy snapshot mới qua `networkInterfaces()` hoặc lookup.
3. So sánh các trường dựa trên ý nghĩa nghiệp vụ; không dựa vào index làm durable ID.
4. Dự phòng thay đổi IP/route/MTU.
5. Nếu refresh thất bại, báo trạng thái **UNKNOWN/ERROR**, không biến thành một số mặc định sai.
6. Thiết lập retry/backoff và tần suất scan vừa đủ, tránh polling quá mức.

Javadoc cũng lưu ý `equals` của hai object có thể thay đổi ý nghĩa khi địa chỉ được gán thay đổi; đừng xây một identity cache vĩnh viễn chỉ dựa trên equality của snapshot.

## 10. Thiết kế chẩn đoán an toàn

Một công cụ diagnostics tốt nên tách:

```text
1. Discovery            -> what interfaces exist now?
2. Local state          -> isUp/isLoopback/isP2P/multicast
3. Configuration        -> MTU, IPs, prefixes, hardware availability
4. Path/application     -> authorized connectivity probe to target
5. Decision             -> health with error/unknown distinctions
```

Ví dụ record nội bộ:

```java
record InterfaceObservation(
        String interfaceKey,
        boolean up,
        boolean loopback,
        boolean multicastCapable,
        int mtu,
        boolean hardwareAddressPresent) {}
```

Đây là **snippet minh họa**; không phải mọi trường trong record đều nên export công khai. Đối với monitoring gửi về hệ thống tập trung, hạn chế output gồm mã tình trạng và số liệu được phép, không đưa raw MAC/IP nếu không có lý do cụ thể.

### 10.1. Không trộn status với reachability

Giả sử `isUp()==true`, `getMTU()==1500` và `supportsMulticast()==true`:
- Bạn chỉ biết OS báo interface đang chạy với cấu hình đó.
- Bạn **chưa biết** DNS, route, gateway, remote service, TLS hoặc API token có hoạt động không.
- Để kiểm tra mục tiêu thực, thử một request **được phép** đến endpoint đã biết với timeout và yêu cầu protocol phù hợp.
- Không dùng `InetAddress.isReachable()` làm bài kiểm chứng tuyệt đối: ICMP/firewall/privileges có thể khiến phép thử sai âm hoặc không đồng nghĩa một TCP service thực tế reachable.

### 10.2. Dùng probes có trách nhiệm

Với health checks:
- Chỉ probe server/port được tổ chức cho phép.
- Timeout ngắn và có rate limit.
- Không scan tùy ý địa chỉ mạng nội bộ hoặc public Internet vì interface UP.
- Nếu là service cần kiểm tra HTTP, tốt nhất probe chính endpoint health đã định nghĩa.
- Ghi log kết quả an toàn, không kèm credentials.
- Phân biệt network unreachable, connection refused, TLS error, DNS failure và application 5xx.

## 11. Bài thực hành có chạy thật: `NetworkInterfaceFactsDemo.java`

Chương trình dưới đây chỉ dùng **Java 17+ standard library** và thực hiện **36 assertions**. Nó minh họa:

1. `HexFormat` đúng với 6-byte, 8-byte hardware addresses và octets >= 128.
2. Xử lý `null`/mảng rỗng từ hardware address.
3. Display MTU dương và fallback cho giá trị không dương **do ứng dụng tự đặt**, không coi `-1` là API sentinel bắt buộc.
4. Tính toán minh họa header budget cho MTU 1500 và tunnel overhead.
5. Phân loại DOWN, LOOPBACK, POINT_TO_POINT, UP_LOCAL_INTERFACE bằng synthetic booleans.
6. Phân biệt IPv4 4-byte, IPv6 16-byte, loopback và multicast IP.
7. `NetworkInterface.networkInterfaces()` và `getNetworkInterfaces()` đều truy xuất được giao diện thật.
8. Lookup interface theo tên và xử lý tên không tồn tại.
9. Đọc `isUp`, `isLoopback`, `isPointToPoint`, `supportsMulticast`, `isVirtual`, MTU, hardware bytes, IP addresses, `InterfaceAddress`, subinterfaces và parent.
10. Bắt `SocketException` theo từng interface khi cấu hình OS thay đổi trong lúc đo.
11. Không tiết lộ MAC/IP/name thật trong stdout.
12. Xác nhận các counters và field lengths trong observation không âm, trừ giá trị `-1` đại diện cho missing hardware address **do helper tự định nghĩa**.

**Không cần Internet**. `InetAddress.getByAddress` tạo các IP synthetic từ raw bytes, không gọi DNS. `NetworkInterface.getByInetAddress(InetAddress.getLoopbackAddress())` là local OS lookup, không mở socket ra mạng.

Chú ý: Live OS/network environment có thể thay đổi giữa hai scans. Các assertions chọn để tránh phụ thuộc một hostname, IP, MAC hay MTU cụ thể. Trên một hệ thống thay đổi interfaces liên tục, lookup có thể bị race hoặc `SocketException`; đó là lỗi môi trường cần xử lý, không phải lý do đặt cứng giá trị mong muốn.

### 11.1. File mã nguồn `NetworkInterfaceFactsDemo.java`

Lưu nguyên vẹn file Java sau:

```java
import java.net.InetAddress;
import java.net.InterfaceAddress;
import java.net.NetworkInterface;
import java.net.SocketException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HexFormat;
import java.util.List;
import java.util.Objects;

public final class NetworkInterfaceFactsDemo {
    private static int passed;

    static void check(String name, boolean condition) {
        if (!condition) throw new AssertionError("FAIL " + name);
        System.out.println("PASS " + name);
        passed++;
    }

    static String formatHardwareAddress(byte[] bytes) {
        if (bytes == null) return "(unavailable)";
        if (bytes.length == 0) return "(empty)";
        return HexFormat.ofDelimiter(":")
                .withUpperCase().formatHex(bytes);
    }

    static String mtuLabel(int mtu) {
        return mtu > 0 ? mtu + " bytes"
                : "(unavailable or nonpositive: " + mtu + ")";
    }

    static String classify(boolean up, boolean loopback,
                           boolean pointToPoint) {
        if (!up) return "DOWN";
        if (loopback) return "LOOPBACK";
        if (pointToPoint) return "POINT_TO_POINT";
        return "UP_LOCAL_INTERFACE";
    }

    record Observation(
            boolean up,
            boolean loopback,
            boolean pointToPoint,
            boolean multicastCapable,
            boolean virtualSubinterface,
            int mtu,
            int hardwareAddressBytes,
            int boundAddressCount,
            int interfaceAddressCount,
            int subinterfaceCount,
            boolean hasParent) {
    }

    static Observation observe(NetworkInterface network)
            throws SocketException {
        // Read a fresh object for each scan. Dynamic OS state may change.
        boolean up = network.isUp();
        boolean loopback = network.isLoopback();
        boolean p2p = network.isPointToPoint();
        boolean multicast = network.supportsMulticast();
        int mtu = network.getMTU();
        byte[] hardware = network.getHardwareAddress();
        int length = hardware == null ? -1 : hardware.length;
        int addresses = (int) network.inetAddresses().count();
        List<InterfaceAddress> interfaceAddresses =
                network.getInterfaceAddresses();

        for (InterfaceAddress item : interfaceAddresses) {
            Objects.requireNonNull(item.getAddress());
            // An IPv6 address need not have an IPv4 broadcast address.
            item.getBroadcast(); // May be null.
            item.getNetworkPrefixLength(); // A short, not a subnet mask.
        }

        return new Observation(up, loopback, p2p, multicast,
                network.isVirtual(), mtu, length, addresses,
                interfaceAddresses.size(),
                (int) network.subInterfaces().count(),
                network.getParent() != null);
    }

    public static void main(String[] args) throws Exception {
        byte[] sample = {
                (byte) 0x00, (byte) 0x1A, (byte) 0x2B,
                (byte) 0x80, (byte) 0xFF, (byte) 0x01
        };
        byte[] extended = {
                (byte) 0x02, (byte) 0x00, (byte) 0x00,
                (byte) 0x00, (byte) 0x00, (byte) 0x00,
                (byte) 0x00, (byte) 0x10
        };

        check("null-hardware-address-supported",
                formatHardwareAddress(null).equals("(unavailable)"));
        check("empty-hardware-address-supported",
                formatHardwareAddress(new byte[0]).equals("(empty)"));
        check("synthetic-six-byte-mac-format",
                formatHardwareAddress(sample)
                        .equals("00:1A:2B:80:FF:01"));
        check("synthetic-high-byte-unsigned",
                formatHardwareAddress(new byte[] {
                        (byte) 0x80, (byte) 0xFF
                }).equals("80:FF"));
        check("synthetic-eight-byte-address",
                formatHardwareAddress(extended)
                        .equals("02:00:00:00:00:00:00:10"));
        check("hex-format-roundtrip",
                java.util.Arrays.equals(
                        HexFormat.ofDelimiter(":")
                                .parseHex(formatHardwareAddress(sample)),
                        sample));
        check("mtu-positive-display",
                mtuLabel(1500).equals("1500 bytes"));
        check("mtu-zero-fallback",
                mtuLabel(0).contains("nonpositive"));
        check("mtu-negative-fallback",
                mtuLabel(-1).contains("-1"));
        check("illustrative-ipv4-tcp-payload-budget",
                1500 - 20 - 20 == 1460);
        check("illustrative-tunnel-overhead-reduces-budget",
                1500 - 20 - 20 - 60 == 1400);
        check("classify-down-first",
                classify(false, true, false).equals("DOWN"));
        check("classify-up-loopback",
                classify(true, true, false).equals("LOOPBACK"));
        check("classify-up-point-to-point",
                classify(true, false, true)
                        .equals("POINT_TO_POINT"));
        check("classify-up-nonloopback",
                classify(true, false, false)
                        .equals("UP_LOCAL_INTERFACE"));

        InetAddress ipv4 = InetAddress.getByAddress(
                new byte[] { (byte) 192, (byte) 0, (byte) 2, (byte) 4 });
        InetAddress ipv6 = InetAddress.getByAddress(new byte[16]);
        InetAddress loop4 = InetAddress.getByAddress(
                new byte[] { 127, 0, 0, 1 });
        InetAddress multicast = InetAddress.getByAddress(
                new byte[] {
                        (byte) 239, (byte) 1, (byte) 2, (byte) 3
                });
        check("ipv4-four-address-bytes",
                ipv4.getAddress().length == 4);
        check("ipv6-sixteen-address-bytes",
                ipv6.getAddress().length == 16);
        check("loopback-address-property",
                loop4.isLoopbackAddress());
        check("multicast-address-property",
                multicast.isMulticastAddress());

        check("networkinterface-in-java-base",
                NetworkInterface.class.getModule()
                        .getName().equals("java.base"));
        List<NetworkInterface> found =
                NetworkInterface.networkInterfaces().toList();
        check("live-network-interfaces-found",
                !found.isEmpty());
        List<NetworkInterface> enumerated = Collections.list(
                NetworkInterface.getNetworkInterfaces());
        check("enumeration-api-finds-interfaces",
                !enumerated.isEmpty());
        check("stream-and-enumeration-have-names",
                found.stream().allMatch(n -> n.getName() != null)
                && enumerated.stream().allMatch(n -> n.getName() != null));
        NetworkInterface first = found.get(0);
        check("interface-name-available",
                first.getName() != null
                        && !first.getName().isBlank());
        NetworkInterface refreshed =
                NetworkInterface.getByName(first.getName());
        check("lookup-existing-interface-by-name",
                refreshed != null);
        check("lookup-nonexistent-interface",
                NetworkInterface.getByName(
                        "__not_a_real_interface_123456__") == null);

        // Never print names, IPs, or MACs from the user's computer.
        int inspected = 0;
        int upCount = 0;
        int knownMtuCount = 0;
        int unknownHardwareCount = 0;
        List<Observation> observations = new ArrayList<>();
        for (NetworkInterface network : found) {
            try {
                Observation o = observe(network);
                observations.add(o);
                inspected++;
                if (o.up()) upCount++;
                if (o.mtu() > 0) knownMtuCount++;
                if (o.hardwareAddressBytes() < 0)
                    unknownHardwareCount++;
                // Do not expose actual values in stdout or logs:
                // network.getHardwareAddress(), inetAddresses(), etc.
                mtuLabel(o.mtu());
                classify(o.up(), o.loopback(), o.pointToPoint());
            } catch (SocketException transientChange) {
                // An interface can disappear/change while being observed.
                // A monitoring service can retry the next fresh scan.
            }
        }
        check("at-least-one-interface-observed",
                inspected > 0);
        check("observation-count-consistent",
                observations.size() == inspected);
        check("up-count-is-bounded",
                upCount >= 0 && upCount <= inspected);
        check("known-mtu-count-is-bounded",
                knownMtuCount >= 0 && knownMtuCount <= inspected);
        check("nullable-hardware-count-is-bounded",
                unknownHardwareCount >= 0
                        && unknownHardwareCount <= inspected);
        check("address-counts-nonnegative",
                observations.stream().allMatch(
                        o -> o.boundAddressCount() >= 0
                                && o.interfaceAddressCount() >= 0));
        check("subinterface-counts-nonnegative",
                observations.stream().allMatch(
                        o -> o.subinterfaceCount() >= 0));
        check("hardware-byte-length-represented",
                observations.stream().allMatch(
                        o -> o.hardwareAddressBytes() >= -1));

        NetworkInterface byLoopback =
                NetworkInterface.getByInetAddress(
                        InetAddress.getLoopbackAddress());
        check("lookup-loopback-address-is-optional",
                byLoopback == null || byLoopback.getName() != null);
        check("lookup-name-consistent",
                refreshed.getName().equals(first.getName()));
        System.out.println("passed=" + passed);
    }
}
```

### 11.2. Biên dịch và chạy

Trong thư mục chứa `NetworkInterfaceFactsDemo.java`:

```bash
javac --release 17 -encoding UTF-8 NetworkInterfaceFactsDemo.java
java NetworkInterfaceFactsDemo
```

Không cần thêm module đặc biệt: `NetworkInterface`, `InetAddress`, `InterfaceAddress`, `SocketException`, `HexFormat` và Java collections nằm trong **`java.base`**. `HexFormat` là API hiện hành từ Java 17.

Nếu dùng project named module, Java SE module `java.base` được đọc tự động, **không cần viết `requires java.base`** trong `module-info.java`. Các thư viện HTTP frameworks khác không liên quan đến bài này.

### 11.3. Stdout chính xác đã xác minh trên OpenJDK 24

```text
PASS null-hardware-address-supported
PASS empty-hardware-address-supported
PASS synthetic-six-byte-mac-format
PASS synthetic-high-byte-unsigned
PASS synthetic-eight-byte-address
PASS hex-format-roundtrip
PASS mtu-positive-display
PASS mtu-zero-fallback
PASS mtu-negative-fallback
PASS illustrative-ipv4-tcp-payload-budget
PASS illustrative-tunnel-overhead-reduces-budget
PASS classify-down-first
PASS classify-up-loopback
PASS classify-up-point-to-point
PASS classify-up-nonloopback
PASS ipv4-four-address-bytes
PASS ipv6-sixteen-address-bytes
PASS loopback-address-property
PASS multicast-address-property
PASS networkinterface-in-java-base
PASS live-network-interfaces-found
PASS enumeration-api-finds-interfaces
PASS stream-and-enumeration-have-names
PASS interface-name-available
PASS lookup-existing-interface-by-name
PASS lookup-nonexistent-interface
PASS at-least-one-interface-observed
PASS observation-count-consistent
PASS up-count-is-bounded
PASS known-mtu-count-is-bounded
PASS nullable-hardware-count-is-bounded
PASS address-counts-nonnegative
PASS subinterface-counts-nonnegative
PASS hardware-byte-length-represented
PASS lookup-loopback-address-is-optional
PASS lookup-name-consistent
passed=36
```

**QA thực tế:** `javac --release 17` trên JDK 24: PASS. `java NetworkInterfaceFactsDemo` trên OpenJDK 24: **36/36 assertions PASS**. Mã chỉ in tên checks, không in tên interfaces/IP/MAC thật và không thực hiện remote network connection.

### 11.4. Tại sao các phép kiểm thử này hữu ích?

| Nhóm | Assertion tiêu biểu | Tập trung |
| --- | --- | --- |
| Hardware null/empty | `null-hardware-address-supported` | Không crash khi MAC không có |
| Định dạng MAC | `synthetic-six-byte-mac-format` | Viết hex octets đúng |
| Signed byte | `synthetic-high-byte-unsigned` | 0x80/0xFF không bị in thành số âm |
| Non-six-byte address | `synthetic-eight-byte-address` | Không hardcode MAC length = 6 |
| MTU | `mtu-positive-display` | Display giá trị local MTU |
| Fallback | `mtu-zero-fallback`, `mtu-negative-fallback` | Defensive app handling, không bịa sentinel API |
| Header budget | `illustrative-ipv4-tcp-payload-budget` | Hiểu MTU != application payload |
| Link state | `classify-up-loopback` và `classify-up-nonloopback` | UP không có nghĩa public Internet |
| IP families | `ipv4-four-address-bytes`, `ipv6-sixteen-address-bytes` | Không áp quy tắc IPv4 cho mọi IP |
| Enumeration | `live-network-interfaces-found` | Đọc OS interfaces thật |
| Lookup | `lookup-nonexistent-interface` | Xử lý absence bình thường |
| OS observation | `at-least-one-interface-observed` | Gọi status/hardware/MTU trên interface thật |
| Snapshot statistics | `observation-count-consistent` | Không phát tán raw identifiers |
| Counters | `up-count-is-bounded` | Biết data result nằm trong tập đã quan sát |
| Optional lookup | `lookup-loopback-address-is-optional` | Không assume một kiểu loopback luôn map được |
| Cache awareness | `lookup-name-consistent` | Lookup mới sau khi biết name |

Các test synthetic là **unit tests của helpers**; tests interface thật là **integration check phụ thuộc OS**. Không gọi những số liệu runtime tại thời điểm chạy là “mặc định của Java”. Một container hoặc host không có interface hoạt động có thể ném `SocketException`; ghi diagnostics và xử lý theo thiết kế production.

## 12. Dùng NetworkInterface trong thực tế

### 12.1. Chọn interface cho multicast

`NetworkInterface` đặc biệt hữu ích khi ứng dụng cần tham gia một multicast group trên đúng interface. `supportsMulticast()` giúp loại bỏ những interface chắc chắn không hỗ trợ; nhưng vẫn phải chỉ định socket option/interface và xử lý network policy.

Ví dụ minh họa với NIO:

```java
DatagramChannel channel = DatagramChannel.open();
try {
    channel.setOption(
            StandardSocketOptions.IP_MULTICAST_IF, selectedNic);
    // Join an allowed multicast group / send datagram here.
} finally {
    channel.close();
}
```

Đây là **snippet**, cần `DatagramChannel`, `StandardSocketOptions` và `selectedNic` đã được chọn an toàn; lệnh có thể ném IOException/UnsupportedOperationException tùy môi trường và channel configuration. Phải mở channel với protocol family phù hợp, bind/join đúng group và kiểm tra OS/firewall. **Không** tự suy multicast luôn đến được đích vì flag true.

### 12.2. Gắn listener HTTP/TCP vào địa chỉ local

Nhiều ứng dụng server cần bind vào một IP cục bộ. `NetworkInterface.inetAddresses()` giúp liệt kê các candidates đã gán, nhưng nên kết hợp:
- Config rõ địa chỉ bind và security boundary.
- IPv4/IPv6 family handling.
- Xác minh địa chỉ vẫn tồn tại ngay trước bind.
- Timeout, interface changes và địa chỉ bị rút.
- Firewall, TLS và authentication policies riêng.

Một server bind vào `0.0.0.0` thường nghe **mọi IPv4 interfaces**, không có nghĩa “tự chọn interface tốt nhất”; điều này có thể expose dịch vụ ngoài ý muốn. Với local development, bind loopback một cách tường minh.

### 12.3. Diagnostics trên VPN/tunnel

Một dịch vụ có thể phát hiện:
- Interface UP nhưng VPN route chưa được cấu hình.
- Local MTU thấp hơn dự kiến ở tunnel.
- Một số interface không có hardware address.
- Địa chỉ IPv6 đã thay đổi mà snapshot vẫn cũ.

Nhưng chỉ với `NetworkInterface` bạn **không xác định được toàn bộ path route hoặc peer status**. Cần thêm OS routing telemetry, authorized connection probe, application logs và VPN client state theo chính sách.

### 12.4. Giám sát MTU thay đổi

Nếu cần alert khi cấu hình MTU đổi:
1. Tạo snapshot interfaces định kỳ với tần suất phù hợp.
2. Lưu identifier tạm thời dựa trên cấu hình role/interface name, không coi index vĩnh viễn.
3. Chỉ so sánh MTU giữa các snapshots mà bạn tin là cùng interface/role.
4. Phân biệt interface biến mất với MTU đổi.
5. Không biến `SocketException` thành MTU = 0 rồi alert sai.
6. Bổ sung authorized path connectivity checks nếu muốn đánh giá ảnh hưởng dịch vụ.

**Không thay MTU tự động** chỉ dựa trên một phép đo hoặc phép trừ minh họa; thay đổi OS network configuration là hành động có tác động toàn máy.

## 13. Xử lý exception và dữ liệu thiếu

Các methods sau có thể ném `SocketException`:
- `NetworkInterface.networkInterfaces()`.
- `NetworkInterface.getNetworkInterfaces()`.
- `NetworkInterface.getByName()`, `getByIndex()`, `getByInetAddress()`.
- `getMTU()`, `getHardwareAddress()`.
- `isUp()`, `isLoopback()`, `isPointToPoint()`, `supportsMulticast()`.

Một helper có thể trả kết quả kiểu:

```java
record Result<T>(T value, Exception error) {
    static <T> Result<T> ok(T value) {
        return new Result<>(value, null);
    }
    static <T> Result<T> fail(Exception cause) {
        return new Result<>(null, cause);
    }
}
```

Đây là **snippet kiểu dữ liệu** minh họa cho service diagnostics; trong code production, có thể dùng `Optional` cùng error category hoặc typed result riêng.

Cần phân biệt:
- **DOWN:** `isUp()` trả false.
- **UNKNOWN:** không đo được vì `SocketException` hoặc thiếu quyền/trường dữ liệu.
- **UNAVAILABLE:** `getHardwareAddress() == null` hoặc `getByName(...) == null`.
- **UP:** OS trả true.
- **CONNECTIVITY_ERROR:** probe end-to-end đã thất bại theo protocol/timeout cụ thể.

Không gọi mọi trạng thái là “offline”. Nhiều số liệu trên OS thay đổi đồng thời; một lần đọc `isUp()`, lần kế đọc `getMTU()` không phải một atomic snapshot của tất cả field động.

### 13.1. Vì sao không nên bắt mọi Exception rồi trả giá trị giả?

Sai:

```java
try {
    return nic.getMTU();
} catch (Exception any) {
    return 1500; // Giả định nguy hiểm.
}
```

Đúng hơn:

```java
try {
    int mtu = nic.getMTU();
    return mtu > 0 ? mtu : -1; // Sentinel app tự định nghĩa.
} catch (SocketException failure) {
    // Record a diagnostic with category and safe error info.
    return -1; // Sentinel app, KHÔNG phải API contract.
}
```

Đây là hai **snippets trong method có kiểu trả về `int`** và biến `nic`. Trong ứng dụng lớn, một typed Result tốt hơn magic number. Dùng một giá trị mặc định hợp lý cho thuật toán chỉ khi business explicitly quyết định cách fallback, không biến giá trị giả thành “MTU thật của NIC”.

## 14. Bảo mật và quyền riêng tư khi dùng NetworkInterface

### 14.1. Không dùng local networking metadata làm authentication

MAC, local IP, interface name, MTU và index là dữ liệu cấu hình mạng, **không phải chứng cứ mật mã**. Những thông tin đó có thể bị cấu hình lại, che giấu bởi VM/container/VPN hoặc được mô phỏng. Không dùng chúng để thay thế xác thực tài khoản, mTLS, certificates hoặc signed device identity.

### 14.2. Logging và telemetry có thể tiết lộ network topology

Những thông tin như:
- MAC thật;
- IP địa chỉ cục bộ, đặc biệt RFC1918/private networks;
- interface names/displays (có thể chứa tên tổ chức hoặc profile VPN);
- broadcast/subnet prefixes;
- tên/tần suất adapters;

có thể cung cấp thông tin topology nội bộ. Nếu gửi diagnostics lên cloud:
- Chỉ log field cần thiết.
- Redact/hash theo chính sách có kiểm soát.
- Không gắn raw MAC vào analytics events vô thời hạn.
- Có access control/retention và data minimization.
- Không hiển thị toàn bộ interfaces của server qua public health endpoint.

### 14.3. Không dùng NetworkInterface để quét mạng

Một interface có prefix `/24` không có nghĩa ứng dụng được phép thử kết nối mọi IP trong subnet. Health checks chỉ nên nhắm những endpoints do hệ thống xác định và được phép, không biến thành port scanner của các mạng lân cận.

## 15. Những lỗi phổ biến

**1. Coi `isUp()==true` là “có Internet”.**  
UP chỉ là trạng thái local OS; cần probe endpoint thật.

**2. Coi `getMTU()==1500` trên một interface là path MTU tới mọi đích.**  
VPN/tunnel/router/path links có thể khác.

**3. Sử dụng MTU như application payload size.**  
Quên IP/TCP/UDP headers và các options/encapsulation.

**4. Kỳ vọng MTU luôn 1500.**  
Loopback, VPN, PPPoE, jumbo frames và OS profiles có thể khác.

**5. Cho rằng `getMTU()` có sentinel -1 chuẩn của mọi platform.**  
Javadoc không hứa điều đó; xử lý SocketException và nonpositive defensively.

**6. Cố gọi `networkInterface.setMTU(1500)`.**  
Java NetworkInterface không có public setter như thế; MTU là OS config.

**7. Không kiểm tra `getHardwareAddress()==null`.**  
Có thể crash ở loopback/tunnel hoặc môi trường hạn chế.

**8. Luôn bắt hardware address phải dài 6 bytes.**  
Hardware address có thể khác kích thước, hoặc rỗng/không có.

**9. In Java signed bytes trực tiếp thành số âm.**  
Format với `HexFormat` hoặc convert unsigned byte rõ ràng.

**10. Dùng MAC như unique device ID/bí mật.**  
Có thể randomized/spoofed, thay đổi và nhạy cảm.

**11. Coi `isVirtual()==false` là adapter vật lý.**  
JDK virtual flag chỉ phản ánh mô hình subinterface được OS báo.

**12. Coi `supportsMulticast()==true` là multicast đi được qua router/firewall.**  
Nó là capability, không phải connectivity test.

**13. Coi `isLoopback()==true` là mạng ngoài hoạt động.**  
Loopback chỉ giao tiếp trong host.

**14. Coi `isPointToPoint()==true` là VPN/tunnel đã đăng nhập thành công.**  
Nó không xác minh remote peer.

**15. Hardcode tên `eth0` vào ứng dụng cross-platform.**  
Tên interface do OS định nghĩa, Windows/macOS/Linux khác nhau.

**16. Hardcode index rồi lưu như stable key trong database.**  
Index có thể thay đổi, `getIndex()` có thể -1.

**17. Không kiểm tra `getByName`/`getByInetAddress` trả null.**  
Không tìm thấy là kết quả hợp lệ.

**18. Bỏ IPv6 vì chỉ lấy `Inet4Address`.**  
Mất network configurations hợp lệ; chú ý scope ID.

**19. Coi `InterfaceAddress.getBroadcast()==null` là lỗi.**  
IPv6 không có broadcast, loopback/P2P cũng có thể không có.

**20. Tự dựng subnet mask từ prefix nhưng không kiểm tra IPv4/IPv6.**  
Prefix length mang semantics theo address family.

**21. Coi `InetAddress.getLocalHost()` là danh sách mọi NIC IP.**  
Không. Enumerate NetworkInterface.

**22. Cache NetworkInterface snapshot vô thời hạn.**  
Cấu hình thay đổi khi Wi-Fi/VPN/containers thay đổi.

**23. Không bắt `SocketException` khi đọc trạng thái.**  
Interface có thể biến mất hoặc bị thay đổi ngay giữa lúc đọc.

**24. Nuốt SocketException rồi đặt `isUp=false`.**  
Biến lỗi đo thành “DOWN”, dẫn tới alert sai.

**25. Coi một lần quét NetworkInterface là transactional snapshot của OS.**  
Fields có thể thay đổi giữa các method calls.

**26. Cho rằng interface có IP là có default route.**  
Routing là lớp riêng; `NetworkInterface` không trả toàn bộ route table.

**27. Cho rằng MAC/IPv4/private subnet nên xuất hiện trong public health endpoint.**  
Rò rỉ topology và thông tin thiết bị không cần thiết.

**28. Dùng `NetworkInterface.equals` làm identity key vĩnh viễn.**  
Danh sách IP thay đổi có thể làm equality behavior khác.

**29. Không xét loopback hoặc only-loopback môi trường CI.**  
Containers/CI có thể không có interface ngoài. Test phải OS-neutral.

**30. Không phân biệt unit tests trên synthetic data và integration tests với OS.**  
Không thể kỳ vọng mọi máy có cùng MAC/IP/MTU.

## 16. Checklist áp dụng

- [ ] Chỉ dùng API public `java.net.NetworkInterface` hiện hành.
- [ ] Dùng `networkInterfaces()`/`inetAddresses()` khi chạy Java 17+.
- [ ] Chọn tên/interface qua cấu hình theo OS, tránh hardcode platform-specific.
- [ ] Xử lý kết quả `getByName/getByIndex/getByInetAddress` có thể null.
- [ ] Biết `getIndex()` có thể thay đổi và -1 nếu unknown.
- [ ] Xử lý `getMTU()` có thể ném `SocketException`.
- [ ] Không coi MTU local là path MTU hoặc application message size.
- [ ] Không giả định MTU=1500 và MAC=6 bytes.
- [ ] Xử lý hardware address null/empty, dùng `HexFormat` khi cần format.
- [ ] Không dùng MAC làm khóa bảo mật, stable user ID hoặc license fingerprint.
- [ ] Phân biệt `isUp` với end-to-end connectivity.
- [ ] Biết loopback, point-to-point, multicast và virtual subinterface là các thuộc tính khác nhau.
- [ ] Không coi `isVirtual` là “máy ảo”.
- [ ] Đọc `InterfaceAddress.getNetworkPrefixLength` và broadcast null đúng IPv4/IPv6.
- [ ] Không log raw IP/MAC/interface names tùy tiện.
- [ ] Refresh snapshots khi mạng thay đổi.
- [ ] Phân loại DOWN/UNKNOWN/ERROR riêng.
- [ ] Khi cần connectivity, probe endpoint được phép với timeout.
- [ ] Nếu dùng multicast, cấu hình multicast socket/interface đúng OS/network policy.
- [ ] Kiểm thử trên Windows/Linux/macOS/container đúng môi trường target.
- [ ] Đảm bảo monitoring/diagnostics không trở thành network scanner trái phép.

## 17. Câu hỏi ôn tập

**1. Lớp Java đại diện interface mạng là gì?**  
`java.net.NetworkInterface`.

**2. Nó nằm trong module nào?**  
`java.base`.

**3. Lấy Stream các interfaces thế nào?**  
`NetworkInterface.networkInterfaces()` từ Java 9+.

**4. Khi nào `getByName` trả null?**  
Khi không tồn tại interface có tên được hỏi.

**5. `getMTU()` trả gì?**  
MTU của local interface, không phải path MTU.

**6. MTU có phải số bytes tối đa cho một `SocketOutputStream.write` không?**  
Không. TCP là byte stream, IP/transport headers và segmentation là lớp riêng.

**7. Khi getMTU ném SocketException, có nên giả định MTU=1500 không?**  
Không. Ghi unknown/error hoặc fallback có chính sách rõ.

**8. `getHardwareAddress()` có thể trả gì ngoài một MAC 6 bytes?**  
Có thể `null` hoặc byte array kích thước khác.

**9. Có thể dùng MAC làm device-secret ổn định không?**  
Không. Nó không phải chứng cứ mật mã và có thể đổi/spoof.

**10. Vì sao ví dụ format MAC bằng HexFormat?**  
Để format unsigned octets đúng, hỗ trợ mảng length bất kỳ trên Java 17+.

**11. `isUp()==true` nghĩa Internet online?**  
Không. Chỉ là trạng thái OS của local interface.

**12. `isLoopback()` cho biết gì?**  
Đây là loopback interface phục vụ giao tiếp nội bộ host.

**13. `supportsMulticast()==true` chứng minh sẽ nhận group traffic không?**  
Không. Còn multicast socket, membership, interface, network policy.

**14. `isVirtual()==false` chắc chắn là NIC vật lý?**  
Không. Flag dùng cho subinterface theo mô hình JDK/OS.

**15. `getParent()` null nghĩa luôn là card vật lý?**  
Không. Có thể không phải subinterface nhưng vẫn là adapter software.

**16. `InterfaceAddress.getBroadcast()` với IPv6 là gì?**  
`null` theo tài liệu.

**17. `getNetworkPrefixLength()` là subnet-mask dotted IPv4 luôn không?**  
Không. Nó là prefix length `short` áp dụng cho IPv4/IPv6.

**18. `InetAddress.getLocalHost()` có liệt kê mọi IP của host không?**  
Không.

**19. Tại sao cần refresh interface object?**  
OS cấu hình mạng thay đổi động; snapshot cũ có thể stale.

**20. Có thể sửa MTU từ NetworkInterface.setMTU(...) không?**  
Không có public method đó; dùng OS/network management ngoài API này.

**21. Nên làm gì nếu muốn biết một HTTP service thực sự truy cập được?**  
Probe đúng endpoint đã được phép với timeout, TLS/authorization và HTTP semantics phù hợp.

**22. Tại sao không in MAC/IP thật trong demo?**  
Bảo vệ privacy; synthetic tests kiểm tra định dạng mà không lộ cấu hình máy.

**23. 36/36 PASS có chứng minh mọi hệ điều hành có interface MTU và MAC giống nhau?**  
Không. Chỉ xác minh bộ helpers và OS integration tại môi trường đã chạy.

## 18. Tài liệu chính thức còn áp dụng

- [Oracle Java SE 26 — `NetworkInterface`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/NetworkInterface.html): methods, null hardware address, MTU, status, Stream API, snapshot freshness, index và OS variation.
- [Oracle Java SE 26 — `InterfaceAddress`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/InterfaceAddress.html): IP address, network prefix length, IPv4 broadcast và nullable broadcast cho IPv6.
- [Oracle Java SE 26 — `InetAddress`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/InetAddress.html): IPv4/IPv6, loopback, link-local, multicast and address semantics.
- [Oracle Java SE 26 — `Inet4Address`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/Inet4Address.html): IPv4 addresses.
- [Oracle Java SE 26 — `Inet6Address`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/Inet6Address.html): IPv6 addresses và scope identifiers.
- [Oracle Java SE 26 — `SocketException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/SocketException.html): socket/network operation errors.
- [Oracle Java SE 26 — `HexFormat`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/HexFormat.html): hex byte formatting/parsing, colon delimiter, uppercase.
- [Oracle Java SE 26 — `StandardSocketOptions`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/StandardSocketOptions.html): `IP_MULTICAST_IF` khi cấu hình multicast.
- [Oracle Java SE 26 — `DatagramChannel`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/DatagramChannel.html): UDP channel/multicast operations.

**Ghi nhớ:** `NetworkInterface` giúp Java quan sát **cấu hình mạng cục bộ**, không phải kiểm tra Internet tổng quát. `getMTU()` phản ánh **MTU của interface**, `getHardwareAddress()` có thể không có và **không phải device identity tin cậy**, còn `isUp()` chỉ phản ánh link/interface status ở góc nhìn OS. Hãy dùng các APIs hiện hành cùng null/error handling, snapshot refresh và privacy-aware diagnostics; khi cần biết kết nối đến đích có hoạt động, phải đo bằng một phép thử end-to-end riêng, được phép và có timeout.
