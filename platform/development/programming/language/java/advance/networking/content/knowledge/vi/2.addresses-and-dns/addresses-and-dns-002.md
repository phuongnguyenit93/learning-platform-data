# Địa chỉ loopback, wildcard, riêng, link-local và multicast trong Java

## 1. Mục tiêu và bức tranh tổng quan

Một địa chỉ IP không chỉ là “nơi đặt máy chủ”: một số địa chỉ chỉ dùng bên trong chính máy, một số dùng trong mạng nội bộ, một số dùng để lắng nghe trên các giao diện, và một số đại diện cho *nhóm* máy. Phân biệt đúng các loại này quyết định việc ứng dụng Java có kết nối được hay không, có vô tình mở cổng ra mạng hay không và vì sao gói tin không vượt qua router.

Sau bài này, bạn cần:
- Nhận diện **loopback**, **wildcard/unspecified**, **private/ULA**, **link-local** và **multicast** ở cả IPv4 và IPv6.
- Phân biệt **địa chỉ đích kết nối** với **địa chỉ dùng khi bind/lắng nghe**, cũng như phạm vi định tuyến và khả năng truy cập thực tế.
- Dùng `java.net.InetAddress` để phân loại, `ServerSocket` để kiểm soát giao diện lắng nghe, `NetworkInterface` và `MulticastSocket` khi làm việc với giao diện và nhóm multicast.
- Chẩn đoán các lỗi phổ biến do `localhost`, NAT, container, IPv6 scope ID, firewall và interface lựa chọn sai.

### Bảng định hướng

| Loại | IPv4 thường gặp | IPv6 thường gặp | Ý nghĩa chính |
| --- | --- | --- | --- |
| Loopback | `127.0.0.0/8` (thường là `127.0.0.1`) | `::1/128` | Giao tiếp với **chính máy hiện tại** |
| Wildcard/unspecified | `0.0.0.0/32` | `::/128` | **Không chỉ một IP cụ thể**; thường làm địa chỉ bind của server |
| Private / Unique Local | `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` | `fc00::/7` (thực tế ULA cấp cục bộ chủ yếu `fd00::/8`) | Giao tiếp trong mạng riêng hoặc phạm vi quản trị được cấu hình |
| Link-local unicast | `169.254.0.0/16` | `fe80::/10` | Giao tiếp **trên cùng một liên kết**, router thường không chuyển tiếp |
| Multicast | `224.0.0.0/4` | `ff00::/8` | Địa chỉ **nhóm nhận** gói tin, không đại diện cho một host duy nhất |

`/8`, `/12`, `/16`… là độ dài tiền tố CIDR, không phải số cổng. Ví dụ `172.16.0.0/12` bao phủ `172.16.0.0` đến `172.31.255.255`, **không** bao phủ mọi `172.x.x.x`. Một host có thể đồng thời sở hữu địa chỉ loopback, IP private, IPv6 link-local và IP public trên các interface khác nhau; wildcard và multicast lại có vai trò khác địa chỉ unicast gán cho host.

## 2. Loopback: đường đi chỉ nằm trong một máy

- IPv4 dành **cả `127.0.0.0/8`** cho loopback, mặc dù `127.0.0.1` phổ biến nhất. IPv6 sử dụng **`::1`**.
- Gói gửi đến loopback được xử lý cục bộ, không đi ra card mạng để đến máy khác. Vì vậy `localhost` trên máy A là **máy A**, còn `localhost` trên máy B là **máy B**.
- `localhost` là **tên host**, có thể được phân giải thành `127.0.0.1`, `::1` hoặc cả hai; thứ tự và địa chỉ được chọn tùy hosts/DNS, hệ điều hành và cấu hình JVM. Nếu server chỉ bind IPv4 mà client thử IPv6 trước, bạn có thể gặp lỗi kết nối dù hai phía đều dùng chữ “localhost”.
- Java cung cấp `InetAddress.getLoopbackAddress()` và `InetAddress.isLoopbackAddress()`; không nên giả định `getLoopbackAddress()` luôn trả IPv4.

**Tình huống:** chạy API thử nghiệm và chỉ muốn chương trình trên cùng máy gọi được: bind vào `127.0.0.1` (hoặc `::1` nếu cần IPv6). Dùng loopback làm endpoint **không** giúp điện thoại trong cùng Wi-Fi truy cập API đó.

## 3. Wildcard/unspecified: lắng nghe trên các địa chỉ phù hợp

`0.0.0.0` (IPv4) và `::` (IPv6) là địa chỉ **unspecified**, còn gọi **any-local/wildcard** trong ngữ cảnh socket. Chúng không chỉ một thiết bị ngoài mạng.

- **Server bind `0.0.0.0:8080`:** yêu cầu hệ điều hành lắng nghe trên các địa chỉ IPv4 cục bộ thích hợp ở cổng 8080, gồm cả loopback và các interface mạng nếu được hỗ trợ. Server bind `127.0.0.1:8080` chỉ lắng nghe trên loopback IPv4.
- **Server bind `[::]:8080`:** lắng nghe theo IPv6; việc có nhận cả IPv4 qua dual-stack hay không phụ thuộc hệ điều hành, tùy chọn socket và cấu hình JVM. Không mặc định rằng `::` tương đương chính xác với `0.0.0.0` trên mọi máy.
- **Client connect:** phải dùng địa chỉ đích cụ thể có thể tới được (ví dụ `127.0.0.1` khi cùng máy hoặc `192.168.1.20` khi ở LAN). **Không dùng `0.0.0.0` hay `::` làm địa chỉ máy chủ mà client phải truy cập.**
- `ServerSocket(8080)` hoặc bind với địa chỉ null thường có ý nghĩa “any-local”; muốn xác định phạm vi truy cập thì truyền IP bind rõ ràng.

**Hệ quả bảo mật:** bind wildcard mở khả năng kết nối qua các interface phù hợp. Điều đó **không đảm bảo** có thể truy cập từ Internet: firewall, NAT, routing, quy tắc container, cloud security group và dịch vụ proxy còn ảnh hưởng. Nhưng với giao diện quản trị hoặc debug, nên chọn loopback thay vì wildcard nếu chỉ cần truy cập cục bộ.

## 4. Private IPv4 và Unique Local IPv6: phạm vi mạng riêng

### IPv4 theo RFC 1918

Ba khối private được dành cho mạng nội bộ:

| CIDR | Khoảng địa chỉ | Ví dụ |
| --- | --- | --- |
| `10.0.0.0/8` | `10.0.0.0` – `10.255.255.255` | `10.20.1.5` |
| `172.16.0.0/12` | `172.16.0.0` – `172.31.255.255` | `172.20.3.9` |
| `192.168.0.0/16` | `192.168.0.0` – `192.168.255.255` | `192.168.1.20` |

Private IP **có thể được router chuyển tiếp trong LAN/VPN/mạng doanh nghiệp**. Chúng không được định tuyến toàn cục trên Internet; truy cập Internet thường thông qua NAT hoặc một cơ chế gateway/proxy khác. Private **không đồng nghĩa an toàn**: hệ thống trong cùng LAN/VPN vẫn có thể truy cập nhau nếu luật mạng cho phép.

**Hai trường hợp dễ nhầm:**
- `100.64.0.0/10` là **Shared Address Space** (thường dùng cho CGNAT, RFC 6598), **không** thuộc ba khối RFC 1918.
- `192.0.2.0/24`, `198.51.100.0/24` và `203.0.113.0/24` là các khối dùng để viết tài liệu, **không** phải private IP để tự cấp cho mạng thực.

### IPv6 ULA

IPv6 dùng **Unique Local Address (ULA)** `fc00::/7` (RFC 4193) cho kết nối trong phạm vi quản trị; ULA thông thường do mạng tự cấp thuộc `fd00::/8`. ULA có thể được route qua nhiều subnet nội bộ và không được kỳ vọng đi qua Internet toàn cục. Ví dụ: `fd12:3456:789a::10`.

**Bẫy Java quan trọng:** `InetAddress.isSiteLocalAddress()` nhận diện ba dải RFC 1918 ở IPv4; trên IPv6, nó theo **site-local kiểu cũ `fec0::/10`** (đã bị loại bỏ theo RFC 3879), **không phải** bộ kiểm tra ULA `fc00::/7`. Vì thế `InetAddress.getByName("fd12:3456::1").isSiteLocalAddress()` trả `false` trên các JDK thông dụng. Nếu ứng dụng cần phân biệt ULA, hãy kiểm tra tiền tố IPv6 riêng (ví dụ Java ở mục 7).

## 5. Link-local: chỉ có ý nghĩa trên liên kết trực tiếp

**IPv4:** `169.254.0.0/16` thường xuất hiện khi thiết bị tự cấu hình địa chỉ link-local (ví dụ không nhận DHCP). Nó phục vụ giao tiếp trên cùng liên kết, **không được router IPv4 chuyển tiếp** đến mạng khác. `169.254.x.x` khác hoàn toàn private RFC 1918 `192.168.x.x`.

**IPv6:** `fe80::/10` là link-local unicast và rất phổ biến trên các interface đã bật IPv6, kể cả khi interface còn có địa chỉ global hay ULA. Neighbor Discovery sử dụng link-local và multicast cục bộ. Router thông thường **không chuyển tiếp** gói có địa chỉ đích hoặc nguồn link-local ra liên kết khác.

IPv6 có thể có cùng một địa chỉ dạng `fe80::...` trên **nhiều interface** hoặc địa chỉ đích chỉ có nghĩa trong một interface cụ thể. Vì thế cần **scope/zone ID**, ví dụ:

```text
fe80::1234%eth0       # tên interface trên một hệ thống có interface eth0
fe80::1234%12         # ví dụ scope ID dạng số trên máy khác
```

Tên `eth0` và số `12` chỉ là ví dụ; hãy dùng interface/scope ID **thực tế** của máy. Trong Java, `Inet6Address` có `getScopeId()` và `getScopedInterface()`; `NetworkInterface` giúp xem các interface và IP của máy. Nếu dùng `InetAddress.getByName("fe80::1234%eth0")` mà interface không tồn tại, việc phân giải có thể thất bại. Chỉ kiểm tra `isLinkLocalAddress()` là **chưa đủ** để bảo đảm có đường đến peer.

**So sánh phạm vi:** loopback = một máy; link-local = một liên kết; private/ULA = một hoặc nhiều mạng nội bộ có routing thích hợp; global/public = có khả năng định tuyến toàn cục nếu chính sách cho phép.

## 6. Multicast: một địa chỉ dành cho nhóm người nhận

Multicast cho phép một sender gửi datagram đến **địa chỉ nhóm**; những host đã tham gia nhóm trên interface phù hợp có thể nhận bản sao. Nó khác:
- **Unicast:** một đích logic cho một gói.
- **Broadcast IPv4:** phát đến mọi host trong miền broadcast liên quan.
- **Multicast:** đích là **nhóm đã đăng ký**, không mặc định mọi máy trong LAN đều nhận.

**Phạm vi địa chỉ:**
- IPv4 multicast: `224.0.0.0/4` (224.0.0.0 đến 239.255.255.255). `224.0.0.0/24` dành cho các mục đích điều khiển mạng trên cùng liên kết, không dùng tùy tiện làm nhóm ứng dụng. `239.0.0.0/8` là dải multicast có phạm vi quản trị, thường thích hợp hơn cho ứng dụng nội bộ khi đã quy hoạch nhóm.
- IPv6 multicast: `ff00::/8`; phần scope trong địa chỉ thể hiện phạm vi, ví dụ `ff02::1` là nhóm *all-nodes* phạm vi link-local, **không** phải nhóm tùy ý dành cho ứng dụng.
- Thiết bị/router quản lý nhóm qua cơ chế như IGMP (IPv4) và MLD (IPv6); multicast qua subnet phụ thuộc hỗ trợ và cấu hình của mạng, không tự hoạt động xuyên Internet/NAT.
- Java chủ yếu dùng UDP với `MulticastSocket` hoặc NIO `DatagramChannel`. Không dùng địa chỉ multicast làm đích TCP `Socket`/`ServerSocket` để “phát một kết nối tới nhiều máy”.
- UDP multicast không bảo đảm người nhận đều nhận đủ gói, không bảo đảm thứ tự hay loại bỏ trùng lặp. Nếu cần độ tin cậy, ứng dụng phải bổ sung giao thức phù hợp.

Hai khái niệm dễ nhầm: **loopback IP** (`127.0.0.1`, `::1`) là gửi tới chính host; **multicast loopback** là cấu hình hệ điều hành có trả gói multicast do chính host gửi về những socket local đã tham gia nhóm hay không. Đây là hai cơ chế khác nhau.

## 7. Ví dụ Java 17+: phân loại địa chỉ chính xác

Lưu mã sau vào `AddressKinds.java`. Ví dụ dùng **IP literal**, nên không cần truy vấn DNS cho các mẫu này.

```java
import java.net.Inet6Address;
import java.net.InetAddress;

public class AddressKinds {
    private static boolean isIpv6Ula(InetAddress address) {
        if (!(address instanceof Inet6Address)) {
            return false;
        }
        byte[] bytes = address.getAddress();
        return (bytes[0] & 0xFE) == 0xFC; // fc00::/7
    }

    private static String kind(InetAddress address) {
        if (address.isAnyLocalAddress()) return "wildcard";
        if (address.isLoopbackAddress()) return "loopback";
        if (address.isLinkLocalAddress()) return "link-local";
        if (address.isMulticastAddress()) return "multicast";
        if (isIpv6Ula(address)) return "IPv6 ULA";
        if (address.isSiteLocalAddress()) return "site-local API";
        return "other";
    }

    public static void main(String[] args) throws Exception {
        String[] samples = {
            "127.0.0.1", "0.0.0.0", "10.2.3.4",
            "172.31.255.254", "169.254.7.9", "239.1.2.3",
            "::1", "::", "fd12:3456::1", "fec0::1",
            "fe80::1", "ff02::1"
        };

        for (String literal : samples) {
            InetAddress address = InetAddress.getByName(literal);
            System.out.println(literal + " -> " + kind(address));
        }
    }
}
```

Biên dịch và chạy:

```bash
javac AddressKinds.java
java AddressKinds
```

Stdout:

```text
127.0.0.1 -> loopback
0.0.0.0 -> wildcard
10.2.3.4 -> site-local API
172.31.255.254 -> site-local API
169.254.7.9 -> link-local
239.1.2.3 -> multicast
::1 -> loopback
:: -> wildcard
fd12:3456::1 -> IPv6 ULA
fec0::1 -> site-local API
fe80::1 -> link-local
ff02::1 -> multicast
```

**Phân tích:** `isAnyLocalAddress()` kiểm tra wildcard; `isLoopbackAddress()` kiểm tra loopback; `isLinkLocalAddress()` kiểm tra link-local; `isMulticastAddress()` kiểm tra multicast. `isSiteLocalAddress()` có tên dễ hiểu nhầm nên được ghi rõ “API”; bộ kiểm tra ULA thực hiện riêng bằng bitmask: byte IPv6 đầu tiên có 7 bit cao bằng `1111110`, tức `fc` hoặc `fd`. Kết quả là **phân loại phạm vi địa chỉ**, không phải phép thử kết nối, quyền truy cập hay trạng thái online.

Không dùng `InetAddress.isReachable()` để suy ra địa chỉ “public/private” hay bảo đảm dịch vụ TCP đang chạy: việc kiểm tra reachability phụ thuộc quyền ICMP, firewall, mạng và cơ chế thử kết nối của hệ điều hành.

## 8. Ví dụ Java 17+: bind loopback và wildcard

Lưu mã sau vào `BindScopeDemo.java`:

```java
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;

public class BindScopeDemo {
    private static void bindAndPrint(String bindIp) throws Exception {
        try (ServerSocket server = new ServerSocket()) {
            server.bind(new InetSocketAddress(
                    InetAddress.getByName(bindIp), 0)); // port 0: OS chọn cổng trống
            System.out.println(bindIp + " -> "
                    + server.getInetAddress().getHostAddress()
                    + ", ephemeral=" + (server.getLocalPort() > 0));
        }
    }

    public static void main(String[] args) throws Exception {
        bindAndPrint("127.0.0.1");
        bindAndPrint("0.0.0.0");
    }
}
```

```bash
javac BindScopeDemo.java
java BindScopeDemo
```

Stdout trên môi trường IPv4 thông dụng có thể bind cả hai địa chỉ:

```text
127.0.0.1 -> 127.0.0.1, ephemeral=true
0.0.0.0 -> 0.0.0.0, ephemeral=true
```

Cổng thực tế do OS cấp là số dương và có thể khác mỗi lần chạy; chương trình chỉ in điều kiện kiểm tra để giữ output ổn định. Bind loopback giới hạn truy cập trực tiếp qua IPv4 loopback; bind wildcard cho phép server nghe các IP IPv4 phù hợp. Nếu muốn máy khác ở LAN gọi được, client phải dùng **IP LAN thực tế của máy chạy server**, chẳng hạn `192.168.1.20:<port>`, và cổng đó phải được firewall/routing cho phép. Không dùng `0.0.0.0:<port>` như “địa chỉ truy cập” trong tài liệu client.

Ví dụ dùng cổng `0` để tránh đụng cổng đang mở; khi deploy thật, cấu hình cổng cụ thể và cân nhắc bind IPv4/IPv6 riêng theo yêu cầu. Trên môi trường chỉ hỗ trợ IPv6 hoặc nơi chính sách mạng chặn bind, chương trình có thể ném `IOException`; đó là điều kiện môi trường, không làm thay đổi ý nghĩa của các loại địa chỉ.

## 9. Ví dụ Java 17+: tham gia và gửi gói multicast nội bộ

Ví dụ dưới đây minh họa rõ ba việc khác nhau: **group** là `239.255.0.1`, **cổng UDP** là `50001` và **interface** lấy từ tên mà người chạy cung cấp. Không phụ thuộc tên card mạng cố định trong mã.

Lưu vào `MulticastDemo.java`:

```java
import java.net.DatagramPacket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.MulticastSocket;
import java.net.NetworkInterface;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;

public class MulticastDemo {
    private static final String GROUP = "239.255.0.1";
    private static final int PORT = 50001;

    public static void main(String[] args) throws Exception {
        if (args.length != 2
                || (!"send".equals(args[0]) && !"receive".equals(args[0]))) {
            System.out.println(
                    "Usage: java MulticastDemo send|receive <network-interface>");
            return;
        }

        NetworkInterface nic = NetworkInterface.getByName(args[1]);
        if (nic == null || !nic.isUp() || !nic.supportsMulticast()) {
            throw new IllegalArgumentException(
                    "Interface unavailable or multicast unsupported: " + args[1]);
        }

        InetAddress group = InetAddress.getByName(GROUP);
        if ("receive".equals(args[0])) {
            InetSocketAddress membership = new InetSocketAddress(group, 0);
            try (MulticastSocket socket = new MulticastSocket(PORT)) {
                socket.joinGroup(membership, nic);
                try {
                    socket.setSoTimeout(5000);
                    byte[] buffer = new byte[2048];
                    DatagramPacket packet =
                            new DatagramPacket(buffer, buffer.length);
                    socket.receive(packet);
                    String message = new String(
                            packet.getData(), packet.getOffset(),
                            packet.getLength(), StandardCharsets.UTF_8);
                    System.out.println(message);
                } catch (SocketTimeoutException e) {
                    System.out.println("Timed out");
                } finally {
                    socket.leaveGroup(membership, nic);
                }
            }
        } else {
            try (MulticastSocket socket = new MulticastSocket()) {
                socket.setNetworkInterface(nic);
                socket.setTimeToLive(1);
                byte[] data = "hello multicast"
                        .getBytes(StandardCharsets.UTF_8);
                socket.send(new DatagramPacket(data, data.length,
                        new InetSocketAddress(group, PORT)));
                System.out.println("Sent");
            }
        }
    }
}
```

Thử trên mạng **có hỗ trợ multicast**, với tên interface thực tế của máy (ví dụ `eth0` trên một số Linux; trên Windows xem tên từ `NetworkInterface`, không đoán tên):

```bash
javac MulticastDemo.java
# Terminal 1: mở trước
java MulticastDemo receive eth0
# Terminal 2: chạy ngay sau khi bên nhận đã join nhóm
java MulticastDemo send eth0
```

Nếu sender gửi thành công, stdout sender là `Sent`; nếu receiver nhận đúng datagram thì stdout receiver là `hello multicast`. Nếu không có gói hợp lệ trong 5 giây, receiver in `Timed out`. Việc nhận gói còn phụ thuộc interface, IGMP, Wi-Fi/AP isolation, firewall, multicast loopback và trạng thái mạng; ví dụ này **không cam kết** hai terminal luôn liên lạc được trong mọi VM/container/Wi-Fi. `setTimeToLive(1)` giới hạn TTL gói IPv4 multicast ở mức một hop, không thay thế chính sách multicast của router.

`joinGroup(SocketAddress, NetworkInterface)` chỉ định interface rõ ràng. Các overload cũ `joinGroup(InetAddress)` và `setInterface(InetAddress)` đã deprecated; Java 17+ nên dùng API nhận `NetworkInterface`. Nhớ `leaveGroup`/`close` để giải phóng tài nguyên.

## 10. Địa chỉ nào thực sự gán cho máy? Đừng đoán qua DNS

`InetAddress.getLocalHost()` phụ thuộc hostname và cấu hình phân giải tên, nên **không bảo đảm** trả IP LAN bạn muốn, càng không bảo đảm trả IP public nhìn từ Internet. `localhost` không đại diện cho mọi interface. Một host có thể có Wi-Fi, Ethernet, VPN, Docker bridge, loopback và nhiều địa chỉ IPv6.

Để xem những địa chỉ hệ điều hành báo cho Java, dùng `NetworkInterface`:

```java
import java.net.InetAddress;
import java.net.NetworkInterface;
import java.util.Collections;

public class ListInterfaces {
    public static void main(String[] args) throws Exception {
        for (NetworkInterface nic :
                Collections.list(NetworkInterface.getNetworkInterfaces())) {
            System.out.println(nic.getName());
            for (InetAddress ip :
                    Collections.list(nic.getInetAddresses())) {
                System.out.println("  " + ip.getHostAddress());
            }
        }
    }
}
```

```bash
javac ListInterfaces.java
java ListInterfaces
```

Danh sách/output phụ thuộc hệ điều hành và cấu hình mạng. Dù tìm được một IP tại interface, vẫn cần kiểm tra route, firewall, DNS, NAT, khả năng lắng nghe trên family IPv4/IPv6 và cổng dịch vụ. Nếu ứng dụng chạy trong container, địa chỉ của container không nhất thiết là địa chỉ mà client ngoài host phải dùng; hãy kiểm tra port publishing và mạng container.

## 11. Chọn địa chỉ theo tình huống

| Nhu cầu | Lựa chọn phù hợp | Điều cần kiểm tra |
| --- | --- | --- |
| Test HTTP server chỉ trên máy lập trình | Bind `127.0.0.1` / `::1` | Client dùng cùng family; `localhost` có thể resolve khác |
| Cho thiết bị khác trong LAN truy cập server | Bind IP LAN cụ thể hoặc wildcard có chủ đích | IP LAN thực tế, port, firewall, subnet/route |
| Kết nối dịch vụ qua mạng private/VPN | IP RFC 1918 hoặc IPv6 ULA được mạng cấp | Route, VPN, DNS nội bộ, ACL |
| Kết nối IPv6 peer cùng liên kết | IPv6 `fe80::...%interface` | Scope ID đúng và cùng link |
| Mạng IPv4 tự nhận địa chỉ `169.254` | Kiểm tra DHCP/link-local | Chỉ cùng link; không coi là LAN routed |
| Gửi thông điệp UDP đến nhóm nội bộ | Nhóm multicast được quản trị trong `239/8`, join đúng NIC | Multicast support, membership, scope, TTL, firewall |
| Triển khai API public | IP/interface nhận traffic + network policy/proxy | Bind wildcard không tự tạo IP public hay mở NAT |

## 12. Những lỗi và ngộ nhận thường gặp

1. **“Bind `0.0.0.0` thì client kết nối tới `0.0.0.0`.”** Sai: đó là địa chỉ bind; client phải kết nối đến một IP/hostname đích hợp lệ.
2. **“`127.0.0.1` là địa chỉ của máy chủ ở mọi nơi.”** Sai: loopback luôn trỏ về **máy đang chạy client**.
3. **“Tất cả `172.x.x.x` đều private.”** Sai: chỉ `172.16.0.0/12` là RFC 1918. `100.64.0.0/10` là shared CGNAT, không phải RFC 1918.
4. **“Private hoặc ULA có nghĩa là không thể bị truy cập.”** Sai: chúng vẫn truy cập được trong phạm vi có routing và quyền mạng; NAT cũng không thay thế xác thực hay firewall.
5. **“`isSiteLocalAddress()` xác nhận mọi địa chỉ IPv6 nội bộ.”** Sai: IPv6 ULA `fc00::/7` cần kiểm tra riêng; IPv6 `fec0::/10` site-local cũ đã bị deprecated.
6. **“`fe80::1234` đủ để tới máy cùng LAN.”** Chưa chắc: với nhiều interface, cần scope ID hoặc lựa chọn interface đúng; router không chuyển tiếp link-local sang mạng khác.
7. **“`ff02::1` hoặc `224.0.0.1` là nhóm ứng dụng có thể dùng tùy ý.”** Sai: đây là nhóm dành cho chức năng mạng đã quy định; chọn dải và group đúng chính sách, tránh nhóm hệ thống.
8. **“`isMulticastAddress()` true nghĩa là sẽ nhận gói.”** Sai: còn phải join group trên NIC phù hợp và mạng phải hỗ trợ chuyển datagram.
9. **“Gọi `InetAddress.getByName("localhost")` luôn trả `127.0.0.1`.”** Sai: IPv6 `::1` có thể được chọn. Nếu cần chắc chắn family, dùng IP literal hoặc chủ động xử lý các bản ghi A/AAAA.
10. **“Bind wildcard là chắc chắn public.”** Sai: socket lắng nghe và khả năng bên ngoài kết nối là hai vấn đề; kiểm tra firewall, NAT, port forwarding, reverse proxy và cloud network policy.

### Quy trình kiểm tra khi client không kết nối được

1. Xác định **client đang chạy ở máy/container nào**; `localhost` trên client trỏ về máy đó.
2. Kiểm tra server bind vào **IP family, IP cụ thể và port** nào. So sánh `127.0.0.1` với `0.0.0.0`, `::1` với `::`.
3. Xác định IP và interface thực tế bằng công cụ hệ điều hành hoặc `NetworkInterface`; so sánh route giữa client và server.
4. Nếu dùng IPv6 link-local, xác minh **cùng link** và **scope ID**; nếu multicast, kiểm tra **group + NIC + TTL + membership**.
5. Kiểm tra firewall/ACL/NAT/port publishing. Thử kết nối TCP đến **địa chỉ đích cụ thể** trước khi đổ lỗi cho DNS hoặc mã Java.

## 13. Câu hỏi tự kiểm tra

1. Hai laptop A và B cùng Wi-Fi. Server A chỉ bind `127.0.0.1:9000`. B kết nối `127.0.0.1:9000` có tới A không? **Không**: đó là loopback của B; A cần lắng nghe trên IP LAN hoặc wildcard có chủ đích, B dùng IP LAN của A.
2. Vì sao `172.20.5.1` là private nhưng `172.40.5.1` không thuộc RFC 1918? **Vì** `172.16.0.0/12` chỉ bao phủ `172.16` đến `172.31`.
3. Vì sao `fd12:3456::1` có thể là ULA nhưng `isSiteLocalAddress()` trả `false`? **Vì** Java không dùng predicate này để nhận diện RFC 4193; cần kiểm tra `fc00::/7` riêng.
4. Hai máy trên hai subnet khác nhau muốn gửi tới `fe80::1234`. Chỉ thêm `%interface` có đủ không? **Không**: scope ID giúp chọn interface trên cùng link, không biến link-local thành địa chỉ được route qua router.
5. Một multicast receiver gọi `joinGroup` thành công nhưng không nhận gì. Có thể do đâu? **Sai NIC**, không có sender cùng group/port, TTL/scope không phù hợp, firewall hoặc thiết bị mạng chặn multicast; UDP cũng không bảo đảm delivery.

## 14. Tài liệu đối chiếu

- Java SE 21 `InetAddress` API: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/InetAddress.html
- Java SE 21 `MulticastSocket` API: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/MulticastSocket.html
- IANA IPv4 Special-Purpose Address Space: https://www.iana.org/assignments/iana-ipv4-special-registry/
- IANA IPv4 Multicast Address Space: https://www.iana.org/assignments/multicast-addresses/
- RFC 1918 (private IPv4): https://www.rfc-editor.org/rfc/rfc1918
- RFC 3927 (IPv4 link-local): https://www.rfc-editor.org/rfc/rfc3927
- RFC 4193 (IPv6 ULA): https://www.rfc-editor.org/rfc/rfc4193
- RFC 4291 (IPv6 address architecture): https://www.rfc-editor.org/rfc/rfc4291
- RFC 3879 (deprecated IPv6 site-local): https://www.rfc-editor.org/rfc/rfc3879
