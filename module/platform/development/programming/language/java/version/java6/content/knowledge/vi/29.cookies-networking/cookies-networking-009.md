# Cookie và mạng: Kiểm thử nhiều card mạng, thiếu địa chỉ và nền tảng không hỗ trợ

## Mục tiêu học tập

Một ứng dụng Java không nên giả định máy chạy luôn có đúng một card mạng, một địa chỉ IPv4, một MAC address hoặc một đường kết nối Internet sẵn sàng. Cùng một hệ thống có thể có **Ethernet, Wi-Fi, VPN, tunnel, loopback, virtual adapters và nhiều IPv4/IPv6 addresses**. Card có thể UP nhưng chưa nhận IP, chỉ có địa chỉ link-local, bị vô hiệu hóa, bị rút khỏi máy, hoặc hệ điều hành/container không cho phép lấy đầy đủ thông tin.

Java hiện hành cung cấp **`java.net.NetworkInterface`**, `InetAddress`, `Inet4Address`, `Inet6Address` và `InterfaceAddress` để truy vấn những thông tin này. Nhưng cần nhớ: **khám phá card mạng không tương đương xác minh kết nối tới một dịch vụ từ xa**, và **địa chỉ IP mà ứng dụng nhìn thấy chưa chắc là source IP OS dùng cho mọi destination**.

Bài này tập trung đúng ba nhóm tình huống trong đề bài: **nhiều card mạng**, **thiếu địa chỉ** và **nền tảng không hỗ trợ/không cung cấp được thông tin**. Sau bài, bạn có thể:

1. Duyệt interfaces qua **`NetworkInterface.networkInterfaces()`** (Stream, Java 9+) hoặc `getNetworkInterfaces()` (Enumeration).
2. Phân biệt interface UP/DOWN, loopback, virtual subinterface, point-to-point, multicast và **zero/multiple assigned IP addresses**.
3. Xử lý `getHardwareAddress()` có thể **null** và `getInterfaceAddresses().getBroadcast()` có thể **null**.
4. Không chọn interface đầu tiên của danh sách khi có nhiều candidates; thiết kế **explicit preferred-name policy** hoặc trả **AMBIGUOUS**.
5. Phân biệt **NO_INTERFACES**, **NO_ELIGIBLE_IPV4**, **INTERFACE_NOT_FOUND**, **DISCOVERY_ERROR** và **UNSUPPORTED**.
6. Hiểu IPv4 link-local `169.254/16`, IPv6 link-local `fe80::/10`, IPv6 scope ID, và trường hợp **IPv6-only**.
7. Xử lý `SocketException`/`SecurityException` mà không tự kết luận unsupported hoặc âm thầm chọn loopback.
8. Tách **OS discovery** và **pure selection logic** bằng một interface có thể tiêm để unit test không cần phần cứng thật.
9. Chạy chương trình **Java 17+ độc lập** có 16 trường hợp cố định cùng tùy chọn kiểm tra NIC thật qua `--live`.
10. Thiết kế unit/integration/CI tests trên Windows, macOS, Linux, VM, container, VPN và những môi trường headless.
11. Phân biệt inventory với OS routing, bind, connect, DNS và TLS; hiểu race khi trạng thái NIC đổi sau khi khám phá.
12. Quản lý logging và bảo mật thiết bị: không công khai IP/MAC hoặc fallback sai khi bắt buộc dùng mạng nội bộ.

**Tính hiện hành:** Ví dụ dùng `NetworkInterface.networkInterfaces()` (Java 9+), `record` và `Stream.toList()` (có trong Java 17). Đã biên dịch/chạy thành công trên **OpenJDK 24.0.2 bằng `javac --release 17`**, kiểm thử 16 dòng kết quả xác định và một live probe. Không dùng API không còn áp dụng hoặc thủ thuật cố định vào một hệ điều hành.

---

## 1. Hiểu đúng ba tầng: interface, IP và route

~~~text
               Máy Java đa kết nối
                        │
           ┌────────────┼───────────────┐
           │            │               │
        Ethernet       Wi-Fi           VPN
         [eth0]       [wlan0]         [tun0]
           │            │               │
        IPv4 A         IPv4 B       IPv4/IPv6 C
           │            │               │
           └────────────┴───────────────┘
                        │
             OS routing + policies
                        │
                Destination server
~~~

- **Interface:** một bộ điều hợp mạng theo mô hình OS/JVM; có thể là vật lý hoặc ảo.
- **Address:** một IPv4/IPv6 gắn với interface; một interface có thể có **0, 1 hoặc nhiều IP**.
- **Route:** quyết định của hệ điều hành về đường đi cho một destination. Không có `NetworkInterface.getDefaultInternetInterface()` bảo đảm đúng cho mọi đích.

Ví dụ `eth0` và `wlan0` đều UP, đều có IPv4. OS có thể chọn Wi-Fi cho Internet, VPN cho mạng nội bộ, hoặc Ethernet cho một destination khác. Chỉ đọc danh sách card và `isUp()` không suy được đường đi cuối cùng.

### 1.1. Các kết luận được phép và không được phép

| Quan sát | Có thể kết luận | Không thể kết luận |
| --- | --- | --- |
| Interface tồn tại | JVM quan sát được adapter trong snapshot | Internet đang hoạt động |
| `isUp()==true` | OS báo interface đang up | Có default route, DNS, kết nối TCP/TLS |
| `inetAddresses().isEmpty()` | Chưa có IP trong snapshot | Máy không có network vĩnh viễn |
| Chỉ có IPv6 | Không có IPv4 trong snapshot | Máy hoàn toàn không thể kết nối |
| `getHardwareAddress()==null` | MAC không có hoặc không truy cập được | Adapter không tồn tại |
| Nhiều IPv4 | Có nhiều local candidates | Phần tử đầu tiên là tốt nhất |
| Có IPv6 `fe80::...` | Có địa chỉ link-local IPv6 | Có thể dùng trên Internet công cộng |
| SocketException khi liệt kê | Khám phá đã lỗi | Chắc chắn nền tảng không hỗ trợ |
| `isVirtual()==true` | Virtual subinterface theo API | Mọi loại mạng ảo đều không dùng được |
| `getIndex()==7` | OS báo index hiện tại là 7 | Index 7 là identity vĩnh viễn |

---

## 2. Các API `NetworkInterface` còn được hỗ trợ

### 2.1. Duyệt danh sách interfaces

~~~java
import java.net.NetworkInterface;
import java.net.SocketException;

// Mảnh minh họa trong phương thức có thể xử lý SocketException.
for (NetworkInterface nic : NetworkInterface.networkInterfaces().toList()) {
    System.out.println(nic.getName());
}
~~~

**`NetworkInterface.networkInterfaces()`** là Java Stream API có từ Java 9; **`getNetworkInterfaces()`** vẫn hỗ trợ Enumeration. Trong Java SE 26, `networkInterfaces()` có thể **ném SocketException** nếu OS I/O lỗi hoặc nền tảng không có ít nhất một configured network interface. Không mặc định chắc chắn có `eth0`, không tự ép trả `List.of()` để che lỗi.

~~~java
// Mảnh minh họa cùng ý tưởng, dạng Enumeration:
java.util.Enumeration<NetworkInterface> entries =
        NetworkInterface.getNetworkInterfaces();
while (entries.hasMoreElements()) {
    NetworkInterface nic = entries.nextElement();
    // Xử lý interface.
}
~~~

**Cả hai dạng đều hiện hành**; chọn kiểu phù hợp với codebase. Đừng dựa vào thứ tự enumeration như một ranking priority.

### 2.2. Thuộc tính và lỗi có thể xảy ra

| API | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `getName()` | Tên interface do OS cung cấp | Không portable/không ổn định |
| `getDisplayName()` | Tên hiển thị | Có thể null |
| `getIndex()` | OS index | -1 nếu unknown, có thể thay đổi |
| `isUp()` | OS báo UP | Có thể SocketException |
| `isLoopback()` | Có phải loopback interface | Có thể SocketException |
| `isVirtual()` | Virtual subinterface theo API | Không đại diện tất cả VPN/NIC ảo |
| `isPointToPoint()` | Interface point-to-point | Có thể SocketException |
| `supportsMulticast()` | Có hỗ trợ multicast | Không chứng minh join thành công |
| `getMTU()` | MTU của interface | Không phải path MTU đến mọi remote |
| `getHardwareAddress()` | Hardware/MAC address | Có thể null hoặc SocketException |
| `inetAddresses()` | Stream các `InetAddress` được gán | Có thể rỗng |
| `getInterfaceAddresses()` | IP cùng prefix và broadcast | List có thể rỗng, broadcast null |
| `getParent()/subInterfaces()` | Quan hệ interface con | Phụ thuộc hệ điều hành |

Mọi property có thể phản ánh **snapshot tại thời điểm lấy**. Java SE 26 nhấn mạnh interface configuration có thể thay đổi sau khi object được tạo. Với DHCP renew, VPN connect/disconnect hoặc hotplug, **phải khám phá lại** khi cần trạng thái mới.

### 2.3. Lookup theo name/index/IP

~~~java
// Mảnh minh họa; name/index ở đây chỉ dùng khi chúng có thật.
NetworkInterface byName = NetworkInterface.getByName("eth0");
NetworkInterface byIndex = NetworkInterface.getByIndex(2);
NetworkInterface byIp = NetworkInterface.getByInetAddress(
        java.net.InetAddress.getByAddress(new byte[]{127, 0, 0, 1}));
~~~

- `getByName()` trả **null** nếu không tìm thấy; `"eth0"` không tồn tại trên mọi OS.
- `getByIndex()` trả null nếu index không tồn tại; **index âm ném IllegalArgumentException**.
- `getByInetAddress()` trả null khi không tìm thấy IP; nếu nhiều interfaces có cùng address, **không được bảo đảm trả interface nào**.
- Không dùng name/index/MAC làm identity thiết bị xuyên suốt các lần khởi động mà không revalidate.

### 2.4. `getInterfaceAddresses()` chứa prefix, broadcast

~~~java
// Mảnh minh họa: nic đã tồn tại trong phương thức.
for (java.net.InterfaceAddress info : nic.getInterfaceAddresses()) {
    java.net.InetAddress ip = info.getAddress();
    short prefix = info.getNetworkPrefixLength();
    java.net.InetAddress broadcast = info.getBroadcast();
    if (broadcast != null) {
        // Chỉ một số IPv4 networks có broadcast.
    }
}
~~~

**IPv6 không có broadcast address**; ngay cả IPv4 trên point-to-point interfaces cũng có thể trả broadcast null. Prefix/broadcast không thay thế OS routing table hoặc “default gateway”.

---

## 3. Xử lý máy nhiều card mạng và nhiều địa chỉ

### 3.1. Vì sao `findFirst()` dễ sai?

~~~java
// PHẢN VÍ DỤ: không phải chính sách chọn "primary" interface.
NetworkInterface chosen = NetworkInterface.networkInterfaces()
        .findFirst()
        .orElseThrow();
~~~

Enumeration order có thể đổi theo máy, OS, container network namespace, VPN, phiên bản JVM, hotplug. Phần tử đầu tiên thậm chí có thể là **loopback**, interface DOWN hoặc không có IP. Việc `isUp()==true` cũng **không tự chứng minh Internet connectivity**.

### 3.2. Chính sách lựa chọn đúng phụ thuộc mục đích

- **Diagnostic inventory:** nên trả **tất cả** interfaces/addresses với trạng thái, không chọn một card.
- **Ứng dụng phải dùng VPN:** yêu cầu explicit interface/policy, **fail closed** khi không xác minh được VPN.
- **Tự tìm một IPv4 local duy nhất:** có thể chọn nếu **sau filtering chỉ còn một candidate**.
- **Ứng dụng TCP/HTTP bình thường:** nhiều khi không cần tự chọn NIC; để **OS routing** chọn local address theo destination.
- **Multicast:** lựa chọn interface còn cần multicast capability, group scope và socket behavior.
- **Listener bind:** cấu hình loopback/wildcard/specific local address theo security exposure, không chọn theo MAC đầu tiên.

Nếu sau filtering có **hai** interfaces phù hợp, trả **AMBIGUOUS** thay vì lấy tùy ý. Kể cả một interface có hai IPv4 addresses cũng có thể tạo hai candidates.

### 3.3. `isVirtual` không phải cờ loại trừ tuyệt đối

Virtual subinterface có thể là đường mạng đúng với ứng dụng. Một số VPN/VM adapters lại không được OS/JDK đánh dấu đúng theo ý nghĩa “virtual” mà application nghĩ. Vì vậy **không tự bỏ tất cả `isVirtual()==true`** nếu chưa có policy riêng.

### 3.4. Không dựa vào MAC để xếp hạng

MAC có thể null vì interface không có hardware address, vì quyền truy cập hoặc đặc điểm tunnel. Một card không có MAC vẫn có thể có IP và là candidate hợp lệ. MAC cũng có thể bị randomize/spoof, không phải identity thiết bị tuyệt đối.

---

## 4. Thiếu địa chỉ IPv4 và IPv6-only

### 4.1. Interface có thể không có địa chỉ

Một interface UP nhưng chưa có DHCP lease, chưa được cấu hình hoặc tunnel mới tạo có thể có `inetAddresses()` rỗng.

~~~java
// Mảnh minh họa.
boolean hasAnyIp = nic.inetAddresses().findAny().isPresent();
if (!hasAnyIp) {
    // Không có địa chỉ IP trong snapshot.
}
~~~

Không dùng `.findFirst().get()` trên collection có thể rỗng. Không lấy `0.0.0.0` như một “địa chỉ máy thật”; đó là **wildcard/unspecified** trong các ngữ cảnh socket.

### 4.2. IPv6-only vẫn có thể có mạng

~~~java
// Mảnh minh họa phân loại địa chỉ.
if (ip instanceof java.net.Inet4Address) {
    // IPv4.
} else if (ip instanceof java.net.Inet6Address) {
    // IPv6, có thể cần scope ID khi link-local.
}
~~~

Nếu policy yêu cầu **IPv4**, một NIC chỉ có IPv6 nên cho **NO_ELIGIBLE_IPV4**, không được nói “máy không có network”. Với dịch vụ hỗ trợ IPv6, có thể thiết kế selector IPv6 riêng theo domain/multicast/link-local/global scope phù hợp.

### 4.3. IPv4 link-local `169.254/16`

`InetAddress.isLinkLocalAddress()` cho biết địa chỉ link-local như 169.254.x.x. Địa chỉ này dùng trong phạm vi local link, **không phải lựa chọn mặc định để quảng bá dịch vụ có thể truy cập từ Internet**. Tuy nhiên, với thiết bị trong cùng một local link, ứng dụng có thể chủ động cần link-local; không có một filter universal cho mọi trường hợp.

### 4.4. IPv6 link-local và scope ID

IPv6 `fe80::/10` dùng cho link-local, có thể cần zone/scope ID để phân biệt interface:

~~~text
fe80::1%7       (numeric scope 7)
fe80::1%eth0    (interface name scope)
~~~

Java hỗ trợ `Inet6Address.getScopeId()` và `getScopedInterface()`. Ví dụ trong bài tạo synthetic `fe80::1%7` bằng bytes; **scope 7 không cần tồn tại trong OS để tạo object**, và không phải một destination dùng được nếu không có interface tương ứng.

~~~java
// Mảnh minh họa không mở kết nối.
byte[] raw = new byte[16];
raw[0] = (byte) 0xfe;
raw[1] = (byte) 0x80;
raw[15] = 1;
java.net.Inet6Address sample =
        java.net.Inet6Address.getByAddress(null, raw, 7);
System.out.println(sample.isLinkLocalAddress()); // true
System.out.println(sample.getScopeId());         // 7
~~~

---

## 5. Nền tảng không hỗ trợ, lỗi quyền và SocketException

### 5.1. Không biết nguyên nhân chỉ từ một exception

Theo Java SE 26, `NetworkInterface.networkInterfaces()` có thể ném `SocketException` do **I/O error hoặc nền tảng không có ít nhất một configured interface**. Những nguyên nhân thực tế có thể gồm network namespace hạn chế, OS lỗi tạm thời, thiếu interface, hotplug, native API lỗi hoặc permission problems.

**Chỉ từ `SocketException` không thể kết luận chắc “OS không hỗ trợ tính năng này”**. Nên dùng một trạng thái chung như **DISCOVERY_ERROR**, giữ exception cause trong logs có kiểm soát và retry chỉ khi hợp lý.

~~~java
// Mảnh minh họa boundary.
try {
    var observed = NetworkInterface.networkInterfaces().toList();
} catch (SocketException failure) {
    // Fail closed hoặc báo unavailable; giữ cause để diagnostic.
}
~~~

### 5.2. `UnsupportedOperationException` chỉ có nghĩa trong abstraction của bạn

Một optional platform-specific adapter do application tự xây có thể chủ động `throw new UnsupportedOperationException("not supported")`; khi đó status **UNSUPPORTED** có ngữ nghĩa rõ trong contract của adapter. **Đừng giả định NetworkInterface API chuẩn sẽ luôn ném exception này khi môi trường không hỗ trợ**. Với standard discovery, SocketException vẫn là case cần xử lý.

### 5.3. Phân biệt no interfaces và discovery failed

~~~text
NO_INTERFACES:
    Fake source trả List.of() hoặc custom provider báo rỗng.

NO_ELIGIBLE_IPV4:
    Có inventory nhưng không có IPv4 thỏa mãn policy.

DISCOVERY_ERROR:
    OS/protected operation ném SocketException/SecurityException.

UNSUPPORTED:
    Một adapter tùy chọn cụ thể chủ động báo feature không hỗ trợ.
~~~

Trong API JDK, khi không có một configured interface, việc khám phá **có thể báo SocketException chứ không cần trả empty list**. Trạng thái `NO_INTERFACES` trong unit test là một simulated edge case của abstraction, không phải khẳng định runtime nào cũng làm vậy.

### 5.4. Không biến lỗi thành loopback fallback

Một application bắt buộc đi qua corporate VPN sẽ **rò data** nếu thất bại khi tìm VPN rồi âm thầm chuyển sang Wi-Fi công cộng. Các tác vụ nhạy cảm phải **fail closed**, không thay một địa chỉ thiếu bằng 127.0.0.1 hoặc một NIC ngẫu nhiên.

### 5.5. Retry có giới hạn

Nếu card đang nhận DHCP lease hoặc VPN reconnect, có thể retry với bounded backoff. Sau mỗi lần retry cần **lấy NetworkInterface snapshot mới**, không dùng object cũ vô hạn. Có tổng timeout và cancellation; không ngủ vô hạn trong HTTP request thread.

---

## 6. Cấu trúc code dễ kiểm thử

`NetworkInterface` là **final class**, không thuận tiện mock trực tiếp. Thay vào đó, chuyển dữ liệu OS sang DTO nội bộ **Adapter**, rồi unit test selection trên fake snapshots.

~~~text
Production                    Unit tests
NetworkInterface              List<Adapter> giả
       │                           │
       ▼                           ▼
    readSystem()             () -> fakeList
       │                           │
       └──────────┬────────────────┘
                  ▼
           AdapterSource
                  ▼
       choose(adapters, preferredName)
           pure selection
                  ▼
    SELECTED / AMBIGUOUS / NO_ELIGIBLE_IPV4 /
    INTERFACE_NOT_FOUND / DISCOVERY_ERROR / UNSUPPORTED
~~~

Mẫu này giúp CI pass kể cả khi không có Wi-Fi hoặc không được phép kết nối mạng; không cần tạo/remove NIC thật. Integration test tùy chọn mới gọi NetworkInterface OS.

**Một `record Adapter` chỉ là snapshot:** nó không tự đại diện một DNS resolver, OS route, MAC identity bền vững, socket connection hoặc mạng hiện còn sống. Sử dụng `List.copyOf` để khóa danh sách địa chỉ theo record và giúp unit test ổn định.

---

## 7. Chương trình Java 17+ đầy đủ: 16 tình huống và live probe

Lưu code dưới đây thành **`NetworkInterfaceEdgeCasesDemo.java`**. Không cần Maven, Gradle hay external dependency. Chương trình không mở network connection tới các IP giả; các dải **192.0.2.0/24** và **198.51.100.0/24** dành cho tài liệu theo RFC 5737.

### 7.1. Source: `NetworkInterfaceEdgeCasesDemo.java`

~~~java
import java.net.Inet4Address;
import java.net.Inet6Address;
import java.net.InetAddress;
import java.net.NetworkInterface;
import java.net.SocketException;
import java.net.UnknownHostException;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public final class NetworkInterfaceEdgeCasesDemo {
    enum Status {
        SELECTED, AMBIGUOUS, NO_INTERFACES, NO_ELIGIBLE_IPV4,
        INTERFACE_NOT_FOUND, DISCOVERY_ERROR, UNSUPPORTED
    }

    record Adapter(String name, int index, boolean up, boolean loopback,
                   boolean virtual, boolean macAvailable,
                   List<InetAddress> addresses) {
        Adapter {
            addresses = List.copyOf(addresses);
        }
    }

    record Decision(Status status, String detail) {
        @Override public String toString() {
            return status + (detail.isEmpty() ? "" : ":" + detail);
        }
    }

    @FunctionalInterface
    interface AdapterSource {
        List<Adapter> load() throws SocketException;
    }

    static InetAddress ipv4(int a, int b, int c, int d)
            throws UnknownHostException {
        return InetAddress.getByAddress(
                new byte[] {(byte) a, (byte) b, (byte) c, (byte) d});
    }

    static Inet6Address ipv6LinkLocal(int scope) throws UnknownHostException {
        byte[] raw = new byte[16];
        raw[0] = (byte) 0xfe;
        raw[1] = (byte) 0x80;
        raw[15] = 1;
        return Inet6Address.getByAddress(null, raw, scope);
    }

    static boolean eligibleIpv4(InetAddress ip) {
        return ip instanceof Inet4Address
                && !ip.isAnyLocalAddress()
                && !ip.isLoopbackAddress()
                && !ip.isLinkLocalAddress()
                && !ip.isMulticastAddress();
    }

    static Decision choose(List<Adapter> all, String requestedName) {
        if (all == null || all.isEmpty())
            return new Decision(Status.NO_INTERFACES, "");

        List<Adapter> relevant = all;
        if (requestedName != null && !requestedName.isBlank()) {
            relevant = all.stream()
                    .filter(a -> requestedName.equals(a.name()))
                    .toList();
            if (relevant.isEmpty())
                return new Decision(Status.INTERFACE_NOT_FOUND, "");
        }

        record Match(String name, Inet4Address address) {}
        List<Match> matches = new ArrayList<>();
        for (Adapter adapter : relevant) {
            if (!adapter.up() || adapter.loopback()) continue;
            // isVirtual is NOT a reliable proxy for "bad" network access.
            for (InetAddress ip : adapter.addresses()) {
                if (eligibleIpv4(ip)) {
                    matches.add(new Match(adapter.name(), (Inet4Address) ip));
                }
            }
        }
        if (matches.isEmpty())
            return new Decision(Status.NO_ELIGIBLE_IPV4, "");
        if (matches.size() != 1)
            return new Decision(Status.AMBIGUOUS, "");

        Match one = matches.get(0);
        return new Decision(Status.SELECTED,
                one.name() + "@" + one.address().getHostAddress());
    }

    static Decision safelyChoose(AdapterSource source, String requestedName) {
        try {
            return choose(source.load(), requestedName);
        } catch (UnsupportedOperationException unsupported) {
            return new Decision(Status.UNSUPPORTED, "");
        } catch (SocketException | SecurityException unavailable) {
            // SocketException also covers no configured NIC on some platforms.
            // It does not prove one specific cause.
            return new Decision(Status.DISCOVERY_ERROR, "");
        }
    }

    static List<Adapter> readSystem() throws SocketException {
        List<Adapter> result = new ArrayList<>();
        for (NetworkInterface networkInterface :
                NetworkInterface.networkInterfaces().toList()) {
            try {
                result.add(new Adapter(
                        networkInterface.getName(),
                        networkInterface.getIndex(),
                        networkInterface.isUp(),
                        networkInterface.isLoopback(),
                        networkInterface.isVirtual(),
                        networkInterface.getHardwareAddress() != null,
                        networkInterface.inetAddresses().toList()));
            } catch (SocketException | SecurityException failure) {
                SocketException wrapped = new SocketException(
                        "Cannot inspect all network adapters");
                wrapped.initCause(failure);
                throw wrapped; // Fail closed: no partial silent selection.
            }
        }
        return List.copyOf(result);
    }

    static Adapter fake(String name, boolean up, boolean loopback,
                        boolean virtual, boolean macAvailable,
                        InetAddress... addresses) {
        return new Adapter(name, 1, up, loopback, virtual, macAvailable,
                List.of(addresses));
    }

    public static void main(String[] args) throws Exception {
        Adapter cable = fake("eth0", true, false, false, false,
                ipv4(192, 0, 2, 10));
        Adapter wifi = fake("wlan0", true, false, false, true,
                ipv4(192, 0, 2, 20));
        List<Adapter> two = List.of(cable, wifi);
        System.out.println("twoInterfaces=" + choose(two, null));
        System.out.println("preferWifi=" + choose(two, "wlan0"));
        System.out.println("preferMissing=" + choose(two, "not-here"));
        System.out.println("emptyInventory=" + choose(List.of(), null));
        System.out.println("noAddresses=" + choose(
                List.of(fake("eth0", true, false, false, false)), null));
        System.out.println("ipv6Only=" + choose(List.of(
                fake("eth0", true, false, false, false, ipv6LinkLocal(7))), null));
        System.out.println("downOnly=" + choose(List.of(
                fake("eth0", false, false, false, true,
                        ipv4(192, 0, 2, 10))), null));
        System.out.println("loopbackOnly=" + choose(List.of(
                fake("lo", true, true, false, false,
                        ipv4(127, 0, 0, 1))), null));
        System.out.println("ipv4LinkLocal=" + choose(List.of(
                fake("eth0", true, false, false, false,
                        ipv4(169, 254, 1, 2))), null));
        System.out.println("noMacStillSelectable=" +
                choose(List.of(cable), null));
        System.out.println("virtualAllowedByPolicy=" + choose(List.of(
                fake("vlan1", true, false, true, false,
                        ipv4(198, 51, 100, 9))), null));
        System.out.println("unsupportedProvider=" + safelyChoose(
                () -> { throw new UnsupportedOperationException("unsupported"); },
                null));
        System.out.println("socketError=" + safelyChoose(
                () -> { throw new SocketException("no interface"); }, null));
        System.out.println("securityError=" + safelyChoose(
                () -> { throw new SecurityException("not permitted"); }, null));
        Inet6Address scoped = ipv6LinkLocal(7);
        System.out.println("linkLocalIpv6=" + scoped.isLinkLocalAddress());
        System.out.println("ipv6ScopeId=" + scoped.getScopeId());

        // Optional real inventory smoke test. No MAC/IP details are printed.
        if (args.length > 0 && "--live".equals(args[0])) {
            String preferred = args.length > 1 ? args[1] : null;
            Decision live = safelyChoose(
                    NetworkInterfaceEdgeCasesDemo::readSystem, preferred);
            System.out.println("liveStatus=" + live.status());
        }
    }
}
~~~

### 7.2. Biên dịch và chạy

~~~bash
javac -encoding UTF-8 --release 17 NetworkInterfaceEdgeCasesDemo.java
java NetworkInterfaceEdgeCasesDemo
~~~

Để thử inventory mạng **thật** (không in IP/MAC):

~~~bash
java NetworkInterfaceEdgeCasesDemo --live
~~~

Để thử lựa chọn theo tên NIC do operator chỉ định (thay tên bằng name thật trên máy):

~~~bash
java NetworkInterfaceEdgeCasesDemo --live eth0
~~~

Kết quả của `--live` thay đổi theo OS, JDK, quyền, card mạng, VPN và runtime network namespace. Không yêu cầu máy Windows/macOS phải có `eth0`. Live test chỉ là **smoke test**, không phải một unit test có status cố định.

### 7.3. Stdout đã kiểm chứng (16 dòng)

~~~text
twoInterfaces=AMBIGUOUS
preferWifi=SELECTED:wlan0@192.0.2.20
preferMissing=INTERFACE_NOT_FOUND
emptyInventory=NO_INTERFACES
noAddresses=NO_ELIGIBLE_IPV4
ipv6Only=NO_ELIGIBLE_IPV4
downOnly=NO_ELIGIBLE_IPV4
loopbackOnly=NO_ELIGIBLE_IPV4
ipv4LinkLocal=NO_ELIGIBLE_IPV4
noMacStillSelectable=SELECTED:eth0@192.0.2.10
virtualAllowedByPolicy=SELECTED:vlan1@198.51.100.9
unsupportedProvider=UNSUPPORTED
socketError=DISCOVERY_ERROR
securityError=DISCOVERY_ERROR
linkLocalIpv6=true
ipv6ScopeId=7
~~~

**Thực tế kiểm thử:** Đã dùng `javac --release 17` với OpenJDK 24.0.2, chạy và so sánh **chính xác cả 16 dòng** trên. Chạy thêm `--live` cũng thành công; dòng `liveStatus` cuối được kiểm tra là một giá trị thuộc enum hợp lệ, **không bị hardcode**.

Ví dụ một giá trị live có thể thấy, không phải kết quả mọi máy:

~~~text
liveStatus=AMBIGUOUS
~~~

Địa chỉ mẫu là từ documentation IP ranges; code không mở kết nối tới chúng, chỉ khởi tạo đối tượng `InetAddress` qua bytes.

### 7.4. Diễn giải từng case

| Output | Ý nghĩa |
| --- | --- |
| `twoInterfaces=AMBIGUOUS` | Ethernet và Wi-Fi fake đều có IPv4 phù hợp; không chọn bừa |
| `preferWifi=SELECTED...` | Explicit name chọn Wi-Fi; còn đúng một IPv4 |
| `preferMissing=INTERFACE_NOT_FOUND` | Name cấu hình không tồn tại |
| `emptyInventory=NO_INTERFACES` | Fake source rỗng, không crash |
| `noAddresses=NO_ELIGIBLE_IPV4` | NIC tồn tại nhưng chưa có IP |
| `ipv6Only=NO_ELIGIBLE_IPV4` | NIC có IPv6 nhưng selector này chỉ nhận IPv4 |
| `downOnly=NO_ELIGIBLE_IPV4` | NIC có IP nhưng OS báo DOWN |
| `loopbackOnly=NO_ELIGIBLE_IPV4` | IPv4 127.0.0.1 không phù hợp rule |
| `ipv4LinkLocal=NO_ELIGIBLE_IPV4` | IPv4 169.254.x.x bị loại bởi policy ví dụ |
| `noMacStillSelectable=SELECTED...` | MAC optional, không phải điều kiện chọn |
| `virtualAllowedByPolicy=SELECTED...` | Virtual subinterface không bị tự loại |
| `unsupportedProvider=UNSUPPORTED` | Fake provider chủ động báo unsupported |
| `socketError=DISCOVERY_ERROR` | SocketException không chứng minh riêng platform unsupported |
| `securityError=DISCOVERY_ERROR` | Không được phép truy cập thông tin |
| `linkLocalIpv6=true` | Synthetic fe80 là IPv6 link-local |
| `ipv6ScopeId=7` | Synthetic scope ID 7, không cần có card 7 thật |

**Chú ý trạng thái NO_INTERFACES:** Trong code fake source trả List rỗng. Standard `NetworkInterface.networkInterfaces()` trong JDK có thể ném SocketException khi không có configured interfaces. Vì vậy đừng viết integration test bắt buộc cả hai phải hành xử giống nhau.

### 7.5. Một số giới hạn code mẫu

- Selector chỉ dành cho **local IPv4 inventory** theo rules chủ động; không phải chọn OS route.
- `macAvailable` là metadata quan sát, không phải điều kiện.
- `isVirtual` không tự là một lý do loại interface.
- Không tự kiểm tra DNS, route, Internet hay remote service.
- Không có IPv6 global selector; `ipv6Only` được xử lý bằng status.
- Một NIC có nhiều IPv4 cũng sẽ AMBIGUOUS.
- Không đảm bảo source snapshot vẫn mới khi ứng dụng dùng để bind/connect.
- Các `Adapter` dùng `List.copyOf`, không có device identity bền vững.
- `readSystem()` fail closed nếu một NIC không đọc được các trường mà nó cần; một diagnostic-only app có thể lựa chọn trả partial data với warnings thay vì từ chối hoàn toàn.
- Main không in raw IP/MAC của thiết bị thật; chỉ giả IP synthetic được công khai.
- `Status.UNSUPPORTED` là hợp đồng của fake/optional provider; không phải exception được hứa bởi mọi OS.

---

## 8. Production: refresh snapshot, lỗi từng interface và lựa chọn an toàn

### 8.1. Cấu hình mạng thay đổi trong đời JVM

~~~text
T0: app thấy VPN UP, local IP A
T1: người dùng ngắt VPN
T2: DHCP/vpn reconnect tạo IP B
T3: app vẫn giữ snapshot IP A
T4: bind/connect IP A thất bại
~~~

`NetworkInterface` được thiết kế như snapshot. Khi cần thông tin mới, lookup lại qua `getByName`, `getByIndex` hoặc full enumeration. **Không cache vô thời hạn** và kỳ vọng các properties tự cập nhật khi OS đổi route/IP.

Đồng thời, dù app vừa lookup snapshot mới, vẫn có race trước khi bind. Khi tạo socket hoặc kết nối remote, phải xử lý `BindException`, `ConnectException`, `NoRouteToHostException`, `SocketTimeoutException` và những I/O errors khác đúng context.

### 8.2. Interface-level error: fail closed hay partial?

Nếu `getHardwareAddress()` trên một adapter ném SocketException, nhưng ứng dụng chỉ cần danh sách IPv4 để hiển thị trong UI, nó có thể ghi **MAC unavailable** và tiếp tục với IP (sau khi đã xử lý các lỗi chính đáng khác).

Ngược lại, nếu application buộc inventory **đầy đủ và nhất quán** để ra security decision, việc tiếp tục một tập dữ liệu thiếu sót có thể nguy hiểm. `readSystem()` trong demo chọn **fail closed**, chuyển về DISCOVERY_ERROR. Đây là **lựa chọn policy**; không phải NetworkInterface bắt buộc mọi ứng dụng phải ngừng khi một getter lỗi.

### 8.3. Không che exception bằng một danh sách rỗng

~~~java
// PHẢN VÍ DỤ: không làm như vậy nếu caller cần biết nguyên nhân.
List<NetworkInterface> readInterfaces() {
    try {
        return NetworkInterface.networkInterfaces().toList();
    } catch (SocketException ignored) {
        return List.of(); // Che việc discovery bị lỗi.
    }
}
~~~

Nếu cần API trả result thay vì ném exception, thiết kế **sealed result type/enum status với error metadata**, không trộn "thật sự không có NIC" với "không truy cập được" hoặc "provider không hỗ trợ".

### 8.4. Không catch toàn bộ RuntimeException

Một `NullPointerException`, `ClassCastException` hoặc lỗi programming khác không nhất thiết là “platform unsupported”. Chỉ bắt **những exception mà abstraction của bạn thực sự định nghĩa**. Demo bắt UnsupportedOperationException từ optional source và SocketException/SecurityException từ discovery boundary, không bắt mọi RuntimeException.

### 8.5. Logging và quyền riêng tư

Interface names, IPs, MAC addresses, VPN identifiers và network topology có thể là thông tin nội bộ/thiết bị nhạy cảm. Trong public APIs và CI logs, ưu tiên ghi:

~~~text
event=network_discovery_failed
status=DISCOVERY_ERROR
requestedInterface=<redacted>
correlationId=<redacted>
~~~

Đây là mẫu log minh họa, không phải stdout demo. Chỉ ghi danh tính NIC/IP/MAC khi thực sự cần và đã có policy bảo mật/retention. Không dùng “bật admin/root cho toàn app” chỉ để lấy MAC nếu use case chỉ cần IP.

---

## 9. Mạng nhiều interface và yêu cầu kết nối thực

### 9.1. `NetworkInterface` không thay thế kiểm thử kết nối

Một interface UP, có IPv4 không đảm bảo:

- Có default route.
- DNS phân giải hostname đích.
- Firewall cho phép TCP/UDP.
- Destination server chạy.
- TLS certificate/hostname hợp lệ.
- Không bị captive portal/proxy.
- VPN split-tunnel có route tới subnet đích.

Khi cần đánh giá service connectivity, sử dụng một **đích kiểm thử đã được phép**, timeout và đúng giao thức (TCP/TLS/HTTP). Tránh dùng `InetAddress.isReachable()` như bằng chứng đủ rằng HTTP service hoạt động; nó có thể phụ thuộc ICMP, firewall và quyền OS.

### 9.2. Bind listening address khác chọn interface để egress

~~~java
// Mảnh minh họa server loopback trong Java 17+.
try (java.net.ServerSocket server =
        new java.net.ServerSocket(
                0, 50, java.net.InetAddress.getLoopbackAddress())) {
    int port = server.getLocalPort();
    // Chỉ listener local, không cho máy ngoài trực tiếp kết nối.
}
~~~

Khi bind `0.0.0.0` hoặc `::`, chương trình có thể nghe trên nhiều local interfaces theo OS policy. Điều này **tăng exposure**, cần network/firewall/TLS/auth. Không suy rằng wildcard là một “primary NIC”.

### 9.3. Routing phụ thuộc destination

Một máy có thể:

~~~text
Destination corporate.internal → VPN
Destination public.example     → Ethernet/Wi-Fi
Destination metadata.local     → bị network policy chặn
~~~

OS routing và source address selection mới quyết định interface cho destination. Nếu app tự chọn NIC từ inventory để thực hiện request tới URL do người dùng cung cấp, vẫn cần **destination allowlist, SSRF protection, HTTPS/hostname verification**, không chỉ chọn đúng card.

### 9.4. Không mặc định fallback sang mạng công cộng

Với application phải dùng VPN, nếu VPN không tồn tại hoặc không có IP, **đừng tự fallback sang Ethernet/Wi-Fi**. Cách xử lý hợp lý là từ chối operation, báo trạng thái rõ cho operator và thử lại khi chính sách cho phép.

---

## 10. Ma trận kiểm thử đa nền tảng

### 10.1. Unit tests offline

| Case | Input giả | Kết quả |
| --- | --- | --- |
| Nhiều card UP | eth0+wlan0 có IPv4 | AMBIGUOUS |
| Preferred name hợp lệ | wlan0 | SELECTED |
| Preferred name thiếu | not-here | INTERFACE_NOT_FOUND |
| List rỗng | `List.of()` | NO_INTERFACES |
| Card chưa có IP | addresses empty | NO_ELIGIBLE_IPV4 |
| Chỉ IPv6 | fe80::1%7 | NO_ELIGIBLE_IPV4 theo policy |
| Card DOWN | IP có nhưng up=false | NO_ELIGIBLE_IPV4 |
| Chỉ loopback | 127.0.0.1 | NO_ELIGIBLE_IPV4 |
| IPv4 link-local | 169.254.1.2 | NO_ELIGIBLE_IPV4 |
| MAC=null | IP hợp lệ | SELECTED |
| Virtual subinterface | IP hợp lệ | SELECTED |
| Provider không hỗ trợ | throws UnsupportedOperationException | UNSUPPORTED |
| Không thể đọc OS | throws SocketException | DISCOVERY_ERROR |
| Quyền không đủ | throws SecurityException | DISCOVERY_ERROR |
| IPv6 link-local | synthetic fe80 | true |
| IPv6 scope | synthetic scope7 | 7 |

**Những test này không cần NIC thật.** Trong CI, nên chạy chúng như unit tests thường xuyên.

### 10.2. Integration tests có điều kiện

Với `--live` không assert máy có `eth0`, IPv4/IPv6 cụ thể, MAC khác null, hoặc tổng số interfaces cố định. Chỉ assert:

- Chương trình không crash.
- Nếu discovery thành công, status tuân theo enum đã định nghĩa.
- Nếu bị hạn chế truy cập, trả DISCOVERY_ERROR thay vì NPE.
- Không log raw IP/MAC trong môi trường không được phép.
- Có thể chọn interface được cấu hình nếu test fixture bảo đảm nó tồn tại.

Nếu cần test một NIC DOWN hay chỉ IPv6 trên OS thật, dùng **VM/container/network namespace thử nghiệm được cấu hình trước**, tránh sửa network production.

### 10.3. Các platform khác nhau

- **Linux:** tên có thể `eth0`, `ens...`, `enp...`, `lo`, `veth...`, `tun...`. Container có network namespace riêng.
- **Windows:** adapter names/index phụ thuộc cấu hình, Wi-Fi/Hyper-V/VPN có thể xuất hiện hoặc vắng mặt.
- **macOS:** `en0`, `en1`, `lo0`, `utun...`, bridges và scoped IPv6; không assume `en0` luôn là Wi-Fi.
- **Headless CI:** có thể chỉ loopback hoặc không có network được phép. Unit tests vẫn phải chạy.

### 10.4. Không dùng DNS trong unit test địa chỉ

~~~java
// PHẢN VÍ DỤ: phụ thuộc DNS và network.
java.net.InetAddress ip = java.net.InetAddress.getByName("example.com");
~~~

Để tạo fake `InetAddress`, dùng bytes:

~~~java
// Mảnh minh họa: 192.0.2.10 là IP dành cho tài liệu.
java.net.InetAddress fake =
        java.net.InetAddress.getByAddress(
                new byte[]{(byte) 192, 0, 2, 10});
~~~

Nhờ đó unit test không phụ thuộc DNS cache, hosts file, IPv4/IPv6 preference hoặc availability của remote network.

### 10.5. Trường hợp cần kiểm thử thêm

- Một NIC UP có **hai IPv4**, selector trả AMBIGUOUS ngay cả khi preferredName khớp.
- Same name nhưng nhiều Adapter records; không giả định name unique toàn bộ sources.
- Invalid name/index; index -1 không truyền vào getByIndex.
- IPv4 multicast address không được chọn làm local unicast.
- `InetAddress.isAnyLocalAddress` true với 0.0.0.0.
- IPv6 global vs unique-local vs link-local.
- IPv6 link-local scope không được chỉ định.
- `getHardwareAddress()==null` mà interface vẫn hoạt động.
- `getInterfaceAddresses()` trả empty hoặc broadcast null.
- `isUp` thay đổi giữa hai lần đọc.
- SocketException ở một thuộc tính của một NIC.
- Preferred interface biến mất sau discovery trước bind.
- User config bắt buộc VPN nhưng NIC không có, fail closed.
- Nhiều requests/threads cùng query NIC, không busy polling.
- Network namespaces/permissions khác nhau trong CI và production.
- Live case thiếu quyền và status đúng thay vì bật root.
- Listener bind loopback vs wildcard có exposure đúng.

---

## 11. Anti-pattern và cách khắc phục

| Anti-pattern | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chọn `findFirst()` từ networkInterfaces | Lấy sai NIC | Explicit policy/AMBIGUOUS |
| Hardcode eth0/en0 | Không portable | Config name/lookup runtime |
| Chỉ chấp nhận một IP mỗi NIC | Bỏ sót multi-address | Duyệt toàn bộ |
| Không có IPv4 = không có mạng | Sai với IPv6-only | Trả NO_ELIGIBLE_IPV4 |
| Interface UP = Internet sẵn | Không xét routing/DNS | Destination connectivity test |
| MAC null = lỗi | Thiếu MAC có thể hợp lệ | Treat as optional |
| isVirtual true = luôn xấu | VPN/tunnel có thể cần | Policy theo use case |
| SocketException = unsupported | Không đủ evidence | DISCOVERY_ERROR + cause |
| getByName null rồi dereference | NullPointerException | Check null |
| getByIndex(-1) | IllegalArgumentException | Validate index |
| Dùng broadcast trên IPv6 | Broadcast null | Null-check |
| Dùng IPv6 fe80 mà không có scope | Mơ hồ interface | Validate scope |
| Lưu NIC object mãi | Snapshot stale | Refresh |
| Retry network vô hạn | Hang/excess logs | Bounded backoff |
| Catch RuntimeException rồi nuốt | Che programming bug | Catch precise exceptions |
| Discovery failure → fallback public Wi-Fi | Có thể leak qua wrong route | Fail closed |
| Unit test phụ thuộc NIC thật | CI flaky | Fake AdapterSource |
| Test gọi DNS Internet | Không deterministic | InetAddress.getByAddress |
| In raw MAC/IP ở public logs | Lộ network topology | Redaction/status-only |
| Chọn NIC thay vì hỏi OS route | Không đúng đích | Route/connection policy riêng |
| Không test bind sau selection | Race khi NIC biến mất | Handle BindException/SocketException |

---

## 12. Bài tập tự luyện

1. Chạy chương trình và giải thích 16 dòng output.
2. Thử `java NetworkInterfaceEdgeCasesDemo --live`; ghi lại status, không công khai MAC/IP.
3. Đổi preferredName từ wlan0 sang not-here, chứng minh INTERFACE_NOT_FOUND.
4. Thêm một IPv4 thứ hai cho eth0: nếu preferredName=eth0, tại sao vẫn AMBIGUOUS?
5. Viết `IPv6Selector` để không bỏ qua trường hợp IPv6-only.
6. Tạo synthetic IPv6 link-local với scope 7; giải thích vì sao scope không chứng minh interface thật có index đó.
7. Cho phép IPv4 link-local trong một use case chỉ phục vụ thiết bị trên cùng link.
8. Thử một NIC DOWN nhưng có IPv4; xác nhận không auto chọn.
9. Thêm adapter loopback và một adapter Ethernet; kiểm tra policy loại loopback.
10. Tạo 3 NIC UP, chỉ một có IPv4; kiểm tra SELECTED.
11. Thử MAC missing trên interface còn IPv4; xác nhận không lỗi.
12. Tạo fake virtual subinterface và giải thích tại sao không loại tuyệt đối.
13. Inject UnsupportedOperationException; xem UNSUPPORTED chỉ thuộc contract fake source.
14. Inject SocketException rồi kiểm tra DISCOVERY_ERROR và không đoán lý do.
15. Inject SecurityException, kiểm tra không lọt sang SELECTED.
16. Đọc InterfaceAddress trên máy thật và xử lý `getBroadcast()==null`.
17. So sánh `getByName/getByIndex/getByInetAddress` với input OS thật, null-check.
18. Tạo một offline test để chứng minh lựa chọn không phụ thuộc order của interfaces.
19. Thiết kế diagnostics có exception cause mà không log IP/MAC.
20. Xây retry với deadline cho DHCP chưa gán IP; refresh mỗi lần.
21. Mô phỏng hot-unplug giữa discovery và bind trong VM thử nghiệm.
22. Tạo unit test với một NIC có 2 địa chỉ IPv4 và 1 IPv6.
23. Kiểm tra sự khác biệt giữa `isVirtual` và một VPN/tun interface thực.
24. Soạn policy bắt buộc VPN: nếu không có/không UP thì fail closed.
25. Đặt một listener loopback với `ServerSocket`, không cần IP cụ thể của Ethernet.
26. Tạo integration fixture chỉ IPv6 trong container namespace.
27. So sánh Mac/Windows/Linux network names/indices ở môi trường test.
28. Viết báo cáo phân biệt inventory thành công và connectivity thành công tới một HTTPS server do test fixture kiểm soát.

---

## 13. Checklist trước production

- [ ] Dùng API NetworkInterface hiện hành, không assume luôn có Ethernet.
- [ ] Phân biệt network inventory, local IP, routing và connectivity.
- [ ] Có policy cho nhiều NIC/multi-IP, không chọn phần tử đầu tiên.
- [ ] Có explicit preferred name khi nghiệp vụ buộc dùng một interface.
- [ ] Không dùng MAC hoặc index như identity duy nhất ổn định.
- [ ] Xử lý UP/DOWN, loopback, virtual, multicast theo use case.
- [ ] Không bắt buộc `getHardwareAddress()` phải khác null.
- [ ] Không gọi `getBroadcast()` trên IPv6 rồi dereference null.
- [ ] Xử lý empty addresses, IPv6-only và link-local có scope.
- [ ] Không nhầm NO_ELIGIBLE_IPV4 với mất hoàn toàn network.
- [ ] Không nhầm SocketException với unsupported chắc chắn.
- [ ] Phân loại được NO_INTERFACES/NO_ELIGIBLE/DISCOVERY_ERROR/UNSUPPORTED.
- [ ] Security-sensitive binding fail closed, không tự fallback sang Wi-Fi.
- [ ] Không nuốt IOException/SecurityException để tạo thành danh sách trống.
- [ ] Refresh snapshot khi DHCP/VPN/hotplug thay đổi.
- [ ] Xử lý lỗi bind/connect dù vừa chọn được NIC.
- [ ] Có bounded retry/backoff và deadline khi mạng chưa sẵn sàng.
- [ ] Unit tests dùng fake AdapterSource, không phụ thuộc phần cứng thật.
- [ ] Test nhiều NIC, thiếu IP, chỉ IPv6, DOWN, loopback, link-local, MAC null.
- [ ] Test provider unsupported, discovery I/O và permission denied.
- [ ] Live smoke test không hardcode NIC/IP/OS-specific status.
- [ ] Dùng documentation-only addresses cho unit tests.
- [ ] Không log raw IP/MAC/network topology trong public logs.
- [ ] Không mở connection ra mạng thật chỉ để test selection logic.
- [ ] Connectivity tests dùng đích được phép, timeouts và TLS đúng.
- [ ] Validation/authorization mạng không được dựa duy nhất vào isUp.

## Kết luận

**Nhiều card mạng, thiếu địa chỉ và nền tảng không cung cấp được network information là các tình huống cần thiết kế có chủ ý.** `NetworkInterface` cung cấp snapshot hiện hành của adapter và IP, nhưng không biết default route phù hợp mọi destination và không bảo đảm kết nối Internet.

Khi một chính sách yêu cầu duy nhất một địa chỉ, hãy **chọn theo cấu hình hoặc trả AMBIGUOUS** nếu nhiều candidates; **NO_ELIGIBLE_IPV4** khi không có IPv4 phù hợp, và **DISCOVERY_ERROR** khi API OS thất bại. MAC null không phải lỗi; IPv6-only không có nghĩa không có mạng; IPv6 link-local cần scope. Đối với VPN hay traffic có ràng buộc bảo mật, **fail closed**, không fallback sai.

Để test tin cậy, **tách OS discovery khỏi pure selection algorithm** bằng một adapter/source có thể tiêm. Chương trình Java 17+ trong bài đã xác minh 16 scenarios offline và một live probe trên OpenJDK 24.0.2; cùng cách tiếp cận này cho phép CI đa nền tảng không phụ thuộc card mạng thật.

**Tài liệu chính thức và tiêu chuẩn hiện hành:**

- [NetworkInterface — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/NetworkInterface.html)
- [NetworkInterface — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/NetworkInterface.html)
- [InterfaceAddress — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/InterfaceAddress.html)
- [InetAddress — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/InetAddress.html)
- [Inet4Address — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/Inet4Address.html)
- [Inet6Address — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/Inet6Address.html)
- [SocketException — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/SocketException.html)
- [ServerSocket — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/ServerSocket.html)
- [RFC 5737 — IPv4 documentation address blocks](https://www.rfc-editor.org/rfc/rfc5737)
- [RFC 3849 — IPv6 documentation prefix](https://www.rfc-editor.org/rfc/rfc3849)
- [RFC 4007 — IPv6 scoped address architecture](https://www.rfc-editor.org/rfc/rfc4007)