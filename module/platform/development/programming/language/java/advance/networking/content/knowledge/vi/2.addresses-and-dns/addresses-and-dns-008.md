# NetworkInterface, nhiều card mạng và phạm vi của địa chỉ IPv6

## 1. Vì sao phải quan tâm đến nhiều giao diện mạng?

Một máy chạy Java có thể đồng thời kết nối Wi-Fi, Ethernet, VPN, mạng container và loopback. Mỗi giao diện có thể không có địa chỉ IP, có một địa chỉ hoặc có nhiều địa chỉ cùng lúc. IPv4 và IPv6 có thể cùng tồn tại trên một giao diện. Vì vậy **một host không tương đương một card mạng hay một địa chỉ IP**.

Ví dụ minh họa:

| Giao diện | Địa chỉ có thể được gán | Vai trò |
| --- | --- | --- |
| Wi-Fi | 192.168.1.20/24, fe80::a1%wlan0, 2001:db8:1::20 | Mạng Wi-Fi và IPv6 |
| Ethernet | 10.10.0.20/24, fe80::b2%eth0 | Mạng LAN khác |
| VPN | 10.8.0.5/24 | Mạng riêng |
| Loopback | 127.0.0.1, ::1 | Kết nối nội bộ trên cùng máy |

Tên giao diện tùy hệ điều hành; **2001:db8::/32** là dải địa chỉ dành cho tài liệu, không phải ví dụ địa chỉ Internet có thể truy cập. Một giao diện có thể mang nhiều địa chỉ IPv6, kể cả link-local, ULA, global và địa chỉ tạm thời cho quyền riêng tư.

Khi tiến trình Java mở kết nối, ba việc khác nhau cùng ảnh hưởng kết quả: **địa chỉ đích**, **giao diện/địa chỉ được gán cục bộ**, và **đường định tuyến mà hệ điều hành chọn**. Với một số địa chỉ IPv6 có phạm vi giới hạn, đặc biệt link-local, ứng dụng còn phải xác định **liên kết (link) cụ thể** chứa đích.

## 2. NetworkInterface là gì?

Lớp **java.net.NetworkInterface** biểu diễn giao diện mạng được hệ điều hành công bố cho JVM. Đây là cách quan sát tên, chỉ số, địa chỉ IP được gán và các thuộc tính của giao diện; **NetworkInterface không phải một socket** và không tự thiết lập kết nối.

~~~text
Máy đa giao diện
├── Wi-Fi
│   ├── 192.168.1.20/24
│   ├── fe80::a1%wlan0
│   └── một hay nhiều IPv6 global
├── Ethernet
│   ├── 10.10.0.20/24
│   └── fe80::b2%eth0
├── VPN / tunnel
│   └── địa chỉ được mạng riêng cấp
└── loopback
    ├── 127.0.0.1
    └── ::1
~~~

Đối tượng NetworkInterface có thể ứng với Ethernet vật lý, Wi-Fi, loopback, tunnel hoặc một giao diện do phần mềm cung cấp. **isVirtual()** trong hợp đồng Java phản ánh **subinterface**, không phải bộ phát hiện mọi loại VPN hay adapter ảo trong hệ điều hành.

### Những phương thức quan trọng của NetworkInterface

| API Java 17 | Cung cấp | Điều cần nhớ |
| --- | --- | --- |
| **getNetworkInterfaces()** | Enumeration giao diện trên máy | Có thể ném SocketException |
| **networkInterfaces()** | Stream giao diện; hỗ trợ từ Java 9 | Dễ dùng trong Stream API |
| **getByName(String)** | Tìm theo tên kỹ thuật | Trả null nếu không tìm thấy |
| **getByIndex(int)** | Tìm theo chỉ số interface | Chỉ số cục bộ, có thể thay đổi |
| **getByInetAddress(InetAddress)** | Tìm interface có địa chỉ IP được gán | Nếu nhiều interface cùng có IP, kết quả không xác định được giao diện nào |
| **getName(), getDisplayName(), getIndex()** | Tên, mô tả, chỉ số | Display name có thể null; index có thể -1 |
| **getInetAddresses(), inetAddresses()** | Các InetAddress trên interface | Có thể chứa cả IPv4 và IPv6 |
| **getInterfaceAddresses()** | Các InterfaceAddress với prefix | Phù hợp xem địa chỉ và mạng con |
| **isUp(), isLoopback(), isPointToPoint()** | Đặc tính giao diện | isUp không chứng minh Internet đang hoạt động |
| **supportsMulticast()** | Giao diện báo có multicast | Không bảo đảm mọi gói multicast đều qua được mạng |
| **getMTU(), getHardwareAddress()** | MTU và địa chỉ phần cứng nếu có | Hardware address có thể null |
| **getParent(), getSubInterfaces()** | Quan hệ subinterface | Không bao quát mọi kiểu adapter ảo |

**InterfaceAddress.getAddress()** cho địa chỉ InetAddress; **getNetworkPrefixLength()** cho số bit prefix; **getBroadcast()** có thể có với IPv4 và trả null cho IPv6. Nếu chỉ cần IP nhưng không cần prefix, có thể dùng **getInetAddresses()**.

**InetAddress.getLocalHost()** chỉ phân giải địa chỉ tương ứng cấu hình hostname cục bộ, nên không thay thế việc liệt kê mọi NIC và IP được gán bằng NetworkInterface. Cả tên interface và danh sách địa chỉ đều có thể đổi khi bật/tắt VPN, DHCP cấp lại địa chỉ hoặc mạng thay đổi.

## 3. Khác biệt giữa IP, network prefix, scope và zone

Cần tách bốn khái niệm thường bị gộp vào nhau:

1. **IP address:** giá trị 32 bit (IPv4) hoặc 128 bit (IPv6) như 192.168.1.20 hay fe80::a1.
2. **Network prefix length:** ví dụ /24 trong 192.168.1.20/24 hoặc /64 của một địa chỉ IPv6 trên interface; cho biết phần prefix mạng theo cấu hình.
3. **IPv6 address scope:** loại phạm vi tô-pô nơi địa chỉ có ý nghĩa: loopback, link-local, global, multicast với các scope khác nhau...
4. **Scope zone / zone identifier:** liên kết hoặc vùng cụ thể mà địa chỉ không-global thuộc về; có thể được chọn bằng hậu tố phần trăm như **fe80::a1%eth0**.

~~~text
fe80::a1%eth0
└─ IP 128 bit ─┘ └─ zone id cục bộ ─┘

fe80::a1/64 trên giao diện eth0
         └─ độ dài prefix do hệ điều hành báo

fe80::/10
       └─ dải địa chỉ IPv6 link-local theo chuẩn
~~~

Một interface thông thường có thể sử dụng prefix **/64** cho địa chỉ link-local, còn **fe80::/10** biểu thị dải địa chỉ thuộc **loại link-local**. Hai con số này không có cùng chức năng. Hậu tố **%eth0** không phải một phần của 128 bit IPv6 và cũng không phải tên miền.

## 4. Những phạm vi địa chỉ IPv6 thường gặp

| IPv6 | Loại/phạm vi | Ý nghĩa |
| --- | --- | --- |
| **::/128** | Unspecified | Chưa có địa chỉ; có thể dùng biểu diễn wildcard khi bind, không dùng như địa chỉ đích bình thường |
| **::1/128** | Loopback | Chỉ chính host; tương tự 127.0.0.1 |
| **fe80::/10** | Unicast link-local | Có ý nghĩa trên một link, không được định tuyến thông thường sang link khác |
| **fc00::/7** | Unique Local Address (ULA) | Dùng cho mạng giới hạn/quản trị riêng, có thể định tuyến nội bộ nhưng không kỳ vọng định tuyến trên Internet toàn cầu |
| **2000::/3** | Không gian thường dùng cho global unicast | Có thể định tuyến toàn cầu khi được cấp phát/cấu hình; không phải mọi địa chỉ trong dải đều hoạt động ngoài Internet |
| **ff00::/8** | Multicast | Địa chỉ nhóm; scope được mã hóa trong địa chỉ |
| **fec0::/10** | Site-local unicast kiểu cũ | Đã bị loại bỏ khỏi chuẩn sử dụng, tránh dùng cho hệ thống mới |

Đặc biệt: **ULA không phải link-local**. Ví dụ một mạng công ty có các địa chỉ **fd12:3456::/48** có thể thiết lập routing giữa nhiều subnet. Ngược lại, một đích **fe80::1** chỉ có ý nghĩa trên link tương ứng, ngay cả khi hai máy cùng thuộc công ty.

IPv6 multicast dùng phạm vi riêng. **ff01::1** là ví dụ nhóm all-nodes ở interface-local; **ff02::1** là all-nodes link-local; **ff05::2** là nhóm router ở site-local multicast. Scope multicast có thể là interface-local, link-local, site-local, organization-local hoặc global tùy mã và quy định. **Site-local multicast vẫn tồn tại trong chuẩn**; thứ bị loại bỏ là **site-local unicast fec0::/10**, không phải tất cả khái niệm site-local.

Các phép thử Java như **isLoopbackAddress()**, **isAnyLocalAddress()**, **isLinkLocalAddress()**, **isMulticastAddress()**, **isMCLinkLocal()**, **isMCSiteLocal()**, **isMCGlobal()** giúp nhận diện từng nhóm. Không dùng **isSiteLocalAddress()** làm phép kiểm tra tổng quát cho ULA: site-local unicast lịch sử và ULA theo RFC 4193 là các khái niệm khác nhau.

## 5. Khi nào phải thêm phần trăm và tên giao diện?

Một máy có thể nối **hai link độc lập**, mỗi link chứa một thiết bị mang cùng 128 bit địa chỉ **fe80::1**:

~~~text
                    Máy Java
               ┌────────────────┐
 Link A:        │ eth0      eth1 │         Link B:
 peer fe80::1 <-┤                ├-> peer fe80::1
               └────────────────┘

 fe80::1%eth0 -> đích trên link A
 fe80::1%eth1 -> đích trên link B
~~~

Nếu chỉ truyền **fe80::1**, không đủ thông tin để phân biệt hai scope zone. Các biểu diễn có thể dùng:

- **fe80::1%eth0** và **fe80::1%eth1**: zone qua tên interface trên máy đang gửi.
- **fe80::1%7**: zone bằng chỉ số cục bộ, nếu hệ thống hiểu số 7 tương ứng zone cần chọn.

Tên interface phải lấy từ **NetworkInterface.getName()** trên máy chạy. **Zone identifier có ý nghĩa cục bộ**, nên không sao chép **%7** từ máy gửi A rồi mặc định %7 trên máy B có cùng ý nghĩa. Giá trị **NetworkInterface.getIndex()** là chỉ số giao diện do hệ điều hành cấp; không coi nó là mã quốc tế hay một scope ID giống nhau trên mọi nền tảng.

Các API liên quan:

- **Inet6Address.getScopeId()**: trả numeric scope ID đã gắn với đối tượng địa chỉ, hoặc **0** nếu không có.
- **Inet6Address.getScopedInterface()**: trả NetworkInterface khi đối tượng được tạo với scoped interface, hoặc **null** nếu không có.
- **Inet6Address.getHostAddress()**: có thể hiển thị thêm **%scope** nếu đối tượng mang scope ID.
- **Inet6Address.getByAddress(String, byte[], NetworkInterface)**: tạo đối tượng IPv6 gắn scope của giao diện cụ thể.

**getScopedInterface() == null** không chứng minh địa chỉ global; **getScopeId() == 0** chỉ cho biết đối tượng không mang numeric scope ID. Muốn biết địa chỉ là link-local hay không, kiểm tra bản thân địa chỉ bằng **isLinkLocalAddress()**.

Khác với các địa chỉ global unicast, **link-local** và multicast có phạm vi giới hạn cần gắn ngữ cảnh zone khi giao tiếp để không nhầm link. Số scope ID chỉ có ý nghĩa tại node được sử dụng; nó **không đi kèm gói IPv6 như một phần của 128 bit đích**.

## 6. Chương trình Java 17+ liệt kê tất cả giao diện

Ví dụ dưới đây chạy độc lập, không truy cập server. Nó liệt kê giao diện do JVM quan sát và thông tin quan trọng của mỗi IP, kể cả IPv6 scope ID. Không hard-code tên giao diện.

**Tệp InterfaceInventory.java**

~~~java
import java.net.Inet6Address;
import java.net.InetAddress;
import java.net.InterfaceAddress;
import java.net.NetworkInterface;
import java.net.SocketException;
import java.util.Enumeration;

public class InterfaceInventory {
    public static void main(String[] args) throws SocketException {
        Enumeration<NetworkInterface> all =
                NetworkInterface.getNetworkInterfaces();

        int count = 0;
        while (all.hasMoreElements()) {
            NetworkInterface nic = all.nextElement();
            count++;
            System.out.printf(
                    "%s | index=%d | up=%b | loopback=%b | subinterface=%b%n",
                    nic.getName(), nic.getIndex(), nic.isUp(),
                    nic.isLoopback(), nic.isVirtual()
            );

            for (InterfaceAddress item : nic.getInterfaceAddresses()) {
                InetAddress ip = item.getAddress();
                String family = ip instanceof Inet6Address ? "IPv6" : "IPv4";
                System.out.printf(
                        "  %s %s/%d", family, ip.getHostAddress(),
                        (int) item.getNetworkPrefixLength()
                );

                if (ip instanceof Inet6Address ipv6) {
                    System.out.printf(
                            " linkLocal=%b scopeId=%d",
                            ipv6.isLinkLocalAddress(), ipv6.getScopeId()
                    );
                    NetworkInterface scoped = ipv6.getScopedInterface();
                    if (scoped != null) {
                        System.out.print(" scopedIf=" + scoped.getName());
                    }
                } else {
                    InetAddress broadcast = item.getBroadcast();
                    if (broadcast != null) {
                        System.out.print(
                                " broadcast=" + broadcast.getHostAddress()
                        );
                    }
                }
                System.out.println();
            }
        }
        System.out.println("Interfaces found: " + count);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 InterfaceInventory.java
java InterfaceInventory
~~~

**Stdout minh họa, không cố định**: tên, IP, số lượng, thứ tự, chỉ số, trạng thái đều khác theo máy:

~~~text
eth0 | index=2 | up=true | loopback=false | subinterface=false
  IPv4 192.168.1.20/24 broadcast=192.168.1.255
  IPv6 fe80:0:0:0:0:0:0:a1%eth0/64 linkLocal=true scopeId=2 scopedIf=eth0
lo | index=1 | up=true | loopback=true | subinterface=false
  IPv4 127.0.0.1/8
  IPv6 0:0:0:0:0:0:0:1/128 linkLocal=false scopeId=0
Interfaces found: 2
~~~

Quan sát cần rút ra:

- Mỗi dòng bắt đầu bằng tên giao diện; một interface có thể có **0, 1 hoặc nhiều địa chỉ**.
- **up=true** không bảo đảm kết nối Internet hoặc server khác truy cập được. Cần xem routing, firewall, DNS và trạng thái dịch vụ đích.
- **scopeId** gắn với đối tượng Inet6Address; **/64** là prefix length trên interface, hai thông tin khác nhau.
- Java có thể in IPv6 theo dạng nhiều nhóm số hexa thay vì dạng nén, nên đừng so sánh địa chỉ bằng chuỗi được format tùy ý.
- **getHardwareAddress()** có thể null; **getDisplayName()** có thể null. Không mặc định mọi adapter là vật lý hay có MAC.
- Giao diện có thể biến mất hoặc thay IP trong lúc ứng dụng chạy. Các API truy cập network interface có thể ném **SocketException**.

## 7. Ví dụ Java 17+ nhận biết IPv6 scope với stdout chính xác

Ví dụ này chỉ phân tích literal IPv6. Nó chạy độc lập và không cần truy cập mạng từ bên ngoài.

**Tệp Ipv6ScopeBasics.java**

~~~java
import java.net.Inet6Address;
import java.net.InetAddress;

public class Ipv6ScopeBasics {
    public static void main(String[] args) throws Exception {
        InetAddress link = InetAddress.getByName("fe80::1234");
        InetAddress loop = InetAddress.getByName("::1");
        InetAddress docs = InetAddress.getByName("2001:db8::1");

        System.out.println("IPv6: " + (link instanceof Inet6Address));
        System.out.println("Link-local: " + link.isLinkLocalAddress());
        System.out.println("Loopback: " + loop.isLoopbackAddress());
        System.out.println(
                "Docs address link-local: " + docs.isLinkLocalAddress()
        );
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 Ipv6ScopeBasics.java
java Ipv6ScopeBasics
~~~

**Stdout chính xác**:

~~~text
IPv6: true
Link-local: true
Loopback: true
Docs address link-local: false
~~~

Lý do: fe80::1234 là link-local; ::1 là loopback; 2001:db8::1 là địa chỉ ví dụ thuộc dải documentation và không phải link-local. Kết quả phân loại không nói địa chỉ nằm trên NIC nào và không chứng minh có thể kết nối.

## 8. Tạo một địa chỉ link-local có scoped interface trong Java

Nếu cần chọn link cho đích IPv6 link-local, tạo **Inet6Address** với **NetworkInterface** thực tế. Overload **Inet6Address.getByAddress(null, rawBytes, nic)** lấy scope ID thích hợp từ giao diện. Nếu NIC không có numeric scope ID cho loại địa chỉ ấy, Java có thể ném **UnknownHostException**.

Chương trình sau nhận tên NIC từ tham số và chỉ dựng địa chỉ minh họa fe80::1234; **nó không cố gắng kết nối đến một peer chưa được xác nhận**.

**Tệp ScopedAddressDemo.java**

~~~java
import java.net.Inet6Address;
import java.net.InetAddress;
import java.net.NetworkInterface;
import java.net.UnknownHostException;

public class ScopedAddressDemo {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.out.println(
                    "Usage: java ScopedAddressDemo <interface-name>"
            );
            return;
        }

        NetworkInterface nic = NetworkInterface.getByName(args[0]);
        if (nic == null) {
            System.out.println("Interface not found: " + args[0]);
            return;
        }

        byte[] raw = InetAddress.getByName("fe80::1234").getAddress();

        try {
            Inet6Address scoped = Inet6Address.getByAddress(
                    null, raw, nic
            );
            System.out.println("Address: " + scoped.getHostAddress());
            System.out.println("Scope ID: " + scoped.getScopeId());
            NetworkInterface selected = scoped.getScopedInterface();
            System.out.println(
                    "Scoped interface: " +
                    (selected == null ? "none" : selected.getName())
            );
        } catch (UnknownHostException ex) {
            System.out.println(
                    "No suitable IPv6 link-local scope on " + nic.getName()
            );
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ScopedAddressDemo.java
java ScopedAddressDemo
~~~

**Stdout chính xác của lần chạy không truyền tên NIC:**

~~~text
Usage: java ScopedAddressDemo <interface-name>
~~~

Nếu đã biết tên NIC thật qua chương trình InterfaceInventory thì chạy, ví dụ:

~~~bash
java ScopedAddressDemo eth0
~~~

Kết quả khi có tham số **không cố định**: eth0 có thể không tồn tại, interface có thể chưa được cấu hình IPv6 link-local, hoặc scope ID là số khác. Nếu thành công, getHostAddress() phản ánh địa chỉ đã được gắn scope. Muốn dùng địa chỉ đó kết nối tới peer thật, peer phải thực sự có địa chỉ trên **cùng link**, server phải listen ở đúng port và routing/firewall phải cho phép.

**Chú ý:** overload **Inet6Address.getByAddress(host, bytes, intScope)** chỉ gán số scope và **không tự kiểm tra** số đó ứng với interface thật hay không. Dùng tham chiếu **NetworkInterface** thường giúp thể hiện ý định rõ ràng hơn khi ứng dụng đã chọn đúng NIC.

## 9. Liên hệ nhiều NIC với việc bind socket và chọn route

### Server: bind địa chỉ nào?

Server có thể bind vào **một địa chỉ IP cục bộ** hoặc **wildcard**:

- **127.0.0.1** hoặc **::1**: loopback; không dùng để nhận trực tiếp kết nối từ máy khác.
- **IP được gán trên Ethernet/Wi-Fi**: có thể nhận kết nối đến địa chỉ ấy nếu hệ điều hành, route và firewall phù hợp.
- **0.0.0.0** hoặc **::** khi dùng làm địa chỉ bind: đại diện wildcard của họ địa chỉ tương ứng; cách hoạt động dual-stack IPv4/IPv6 phụ thuộc nền tảng và cấu hình socket.

API liên quan: **ServerSocket.bind(SocketAddress)**, **ServerSocket(int, int, InetAddress)** và **InetSocketAddress**. Không hiểu nhầm việc bind wildcard thành bảo đảm “đã mở dịch vụ ra Internet”: NAT, firewall, route, container và cloud vẫn quyết định khả năng truy cập.

### Client: chọn địa chỉ nguồn khác với chọn tuyến đường

Thông thường hệ điều hành chọn nguồn/route dựa trên đích và chính sách. Ứng dụng TCP có thể dùng **Socket.bind(...)** để ràng buộc local IP trước khi kết nối, nhưng điều đó **không nhất thiết cưỡng ép tất cả lưu lượng ra card vật lý mong muốn** trong mọi cấu hình routing.

~~~java
// Minh họa API, không phải chương trình Java độc lập.
// localIp là IP thật được gán trên máy; remoteIp là địa chỉ đích thật.
Socket socket = new Socket();
socket.bind(new InetSocketAddress(localIp, 0));
socket.connect(new InetSocketAddress(remoteIp, 443), 3000);
~~~

Ở đây local port **0** yêu cầu hệ điều hành chọn cổng nguồn phù hợp; **3000** là connect timeout tính theo mili-giây. Khi đích là IPv6 link-local, đối tượng remoteIp còn cần ngữ cảnh zone đúng để không nhầm interface.

### Multicast

Các ứng dụng gửi/join multicast có thể cần chọn **NetworkInterface** cho lưu lượng multicast, thay vì để mặc định. **supportsMulticast()** hữu ích để kiểm tra khả năng cơ bản. Một địa chỉ multicast có scope link-local chỉ có ý nghĩa trên link được chỉ định.

## 10. NetworkInterface, InetAddress và DNS không làm cùng một việc

- **DNS** giúp phân giải một tên thành những địa chỉ ứng viên: bản ghi **A** cho IPv4, **AAAA** cho IPv6. **InetAddress.getAllByName(host)** có thể trả nhiều địa chỉ theo cấu hình resolver.
- **NetworkInterface** mô tả giao diện **cục bộ** và những IP gắn với giao diện.
- **Routing table/chính sách hệ điều hành** quyết định nơi các gói đi qua và IP nguồn phù hợp, không được biểu diễn đầy đủ bởi một danh sách NetworkInterface.

Ví dụ, nếu DNS trả địa chỉ 203.0.113.10 (dải tài liệu) thì từ việc máy có Wi-Fi và VPN đang up chưa thể kết luận lưu lượng sẽ đi qua interface nào. Cần nhìn route tới địa chỉ đích. Địa chỉ IPv6 global cũng có thể thay đổi theo môi trường mạng, còn scope ID là cục bộ; tránh lưu cứng IP/interface index trong cấu hình dùng lại ở máy khác.

## 11. Tình huống lỗi và cách chẩn đoán

| Tình huống | Nguyên nhân/hướng kiểm tra |
| --- | --- |
| Kết nối fe80::1 thất bại trên máy có hai NIC | Chưa chỉ đúng zone/interface hoặc peer không ở cùng link |
| Sao chép phần %5 từ máy A sang máy B | Scope ID chỉ có nghĩa cục bộ; %5 trên B có thể là interface khác |
| Liệt kê thấy IPv6 nhưng connect lỗi | Thiếu route, interface down, firewall, peer không listen, IPv6 stack hoặc zone sai |
| Bind server trên ::1 rồi dùng client từ máy khác | ::1 chỉ là loopback trên chính server |
| Thấy ULA fd... và tưởng router không được chuyển tiếp | ULA có thể được định tuyến trong mạng riêng, khác fe80::/10 |
| isUp() trả true nên coi mạng đã hoạt động đầy đủ | isUp không kiểm tra DNS, Internet hoặc dịch vụ |
| getScopedInterface() trả null nên kết luận IPv6 global | Null là thông tin về cách tạo đối tượng, không xác định toàn bộ loại địa chỉ |
| Chỉ xem InetAddress.getLocalHost() để chọn NIC | Một hostname không cung cấp toàn bộ inventory IP trên máy |

Một quy trình chẩn đoán thực tế:

1. Xác định đích là **DNS name hay IPv4/IPv6 literal**, và đích có port/giao thức gì.
2. Nếu là hostname, kiểm tra kết quả **A/AAAA**, phân biệt lỗi phân giải với lỗi kết nối.
3. Chạy **InterfaceInventory** để lấy tên/interface index và địa chỉ thực tế. Kiểm tra NIC mong muốn có IPv6 hợp lệ.
4. Nếu là **fe80::/10** hoặc multicast scope giới hạn, kiểm tra **%zone** được chọn trên máy client.
5. Xem **routing table** và firewall bằng công cụ của hệ điều hành; NetworkInterface một mình không đủ xác định đường đi.
6. Kiểm tra server đã bind địa chỉ/port phù hợp; kiểm tra timeout, log socket và trạng thái giao diện thay đổi trong lúc chạy.
7. Với log thực tế, cân nhắc tránh công bố địa chỉ nội bộ và thông tin thiết bị không cần thiết.

## 12. Hiểu nhầm quan trọng

**Một máy chỉ có một IP.** Sai: một interface có thể sở hữu nhiều IP; một máy có thể có hàng chục interface do phần mềm hoặc phần cứng tạo ra.

**isVirtual() cho biết tất cả card ảo/VPN.** Sai: ý nghĩa API cụ thể là subinterface; nhiều adapter ảo của hệ điều hành không nhất thiết được gắn nhãn này.

**Prefix /64 bằng scope ID hoặc interface index.** Sai: prefix length thể hiện mạng con, scope ID xác định zone trong ngữ cảnh địa chỉ scoped, interface index là định danh giao diện cục bộ.

**IPv6 link-local luôn duy nhất trên cả Internet.** Sai: cùng một địa chỉ fe80::1 có thể xuất hiện trên nhiều link. Cần thêm zone khi địa chỉ đơn lẻ gây nhập nhằng.

**So sánh Inet6Address bằng equals() là đủ để phân biệt hai link.** Không đúng nếu ứng dụng cần phân biệt zone: hợp đồng equals() của Inet6Address so sánh byte địa chỉ IP, không tự coi hai zone là hai byte địa chỉ khác nhau. Cần đưa zone/interface vào khóa so sánh phù hợp với bài toán.

**Dùng isSiteLocalAddress() để nhận diện mọi địa chỉ mạng riêng IPv6.** Không đúng: khái niệm site-local unicast cũ đã bị loại bỏ; ULA có dải fc00::/7 và quy tắc riêng.

**Có scope link-local nên truyền dữ liệu tự an toàn.** Sai: phạm vi giới hạn không thay thế mã hóa, xác thực, kiểm soát quyền và firewall.

**Một lần liệt kê NetworkInterface là đủ dùng mãi.** Sai: trạng thái, IP và interface index có thể đổi khi mạng thay đổi. Ứng dụng sống lâu cần cập nhật thông tin khi cần.

## 13. Câu hỏi tự kiểm tra

**1. Laptop có Wi-Fi và Ethernet; peer ở mỗi link dùng cùng fe80::1. Làm gì để chọn đúng?**  
Cần xác định **zone/interface cục bộ**, ví dụ hậu tố %wlan0 hay %eth0 nếu đó là tên thực của NIC trên máy đang gửi.

**2. Nếu InterfaceAddress báo fe80::1234/64, số 64 có phải scope ID?**  
Không. Đây là prefix length; scope ID là ngữ cảnh zone của địa chỉ scoped IPv6.

**3. Địa chỉ fd12:3456::1 có thể được route qua hai subnet nội bộ không?**  
Có thể. Đây là ULA nếu thuộc dải fc00::/7, không bị ràng buộc một link như fe80::/10.

**4. DNS trả nhiều AAAA. NetworkInterface có cho biết cái nào sẽ được client chọn không?**  
Không. DNS cung cấp ứng viên địa chỉ đích, interface inventory cung cấp IP cục bộ; quyết định kết nối/định tuyến còn phụ thuộc hệ điều hành và chính sách ứng dụng.

**5. Khi getScopeId() == 0, có thể kết luận địa chỉ chắc chắn là global không?**  
Không. Có thể đơn giản đối tượng Inet6Address chưa có numeric scope ID; muốn phân loại địa chỉ phải kiểm tra bản thân bit địa chỉ.

**6. Vì sao không chuyển giá trị %7 trong link-local literal từ host A sang host B?**  
Vì scope/zone ID chỉ mang nghĩa cục bộ trên từng host, không phải định danh link thống nhất giữa các máy.

## Tóm tắt

**NetworkInterface** giúp Java biết máy đang có những giao diện gì, trạng thái ra sao, được gán IPv4/IPv6 nào; **InterfaceAddress** bổ sung prefix length. **Inet6Address** mô tả IPv6 và thông tin scope/zone khi cần. Trong hệ thống đa NIC, cần phân biệt **địa chỉ cục bộ**, **kết quả DNS**, **lựa chọn routing** và **phạm vi IPv6**. Đặc biệt, **địa chỉ link-local có thể trùng trên các link khác nhau**, nên hậu tố **%zone** hoặc scoped Inet6Address giúp chọn đúng link trên máy hiện tại.

### Tham khảo

- [Java SE 17 — NetworkInterface](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/NetworkInterface.html)
- [Java SE 17 — InterfaceAddress](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InterfaceAddress.html)
- [Java SE 17 — Inet6Address](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Inet6Address.html)
- [Java SE 17 — InetAddress](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InetAddress.html)
- [RFC 4007 — IPv6 Scoped Address Architecture](https://www.rfc-editor.org/rfc/rfc4007)
- [RFC 4291 — IPv6 Addressing Architecture](https://www.rfc-editor.org/rfc/rfc4291)
- [RFC 4193 — Unique Local IPv6 Unicast Addresses](https://www.rfc-editor.org/rfc/rfc4193)
- [RFC 3879 — Deprecating Site Local Addresses](https://www.rfc-editor.org/rfc/rfc3879)
