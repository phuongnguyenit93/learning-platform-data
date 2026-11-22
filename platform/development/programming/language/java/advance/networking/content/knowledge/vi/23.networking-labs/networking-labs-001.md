# Khảo sát DNS, nhiều địa chỉ và card mạng trên môi trường đang chạy với Java 17+

Khi một ứng dụng Java kết nối thành công trên laptop nhưng thất bại trong container, VPN, máy chủ dual-stack hoặc máy có nhiều card mạng, nguyên nhân có thể nằm ở **name resolution**, **thứ tự địa chỉ IPv4/IPv6**, **cấu hình giao diện mạng**, **địa chỉ nguồn mà hệ điều hành chọn**, hoặc **phạm vi IPv6**. Việc chỉ in `InetAddress.getLocalHost()` rồi kết luận “máy này có một IP và một card mạng” thường gây hiểu nhầm.

Bài thực nghiệm này hướng dẫn **quan sát môi trường đang chạy** bằng Java 17+ và đối chiếu với công cụ hệ điều hành, tập trung vào bốn câu hỏi:

1. Một hostname hiện được Java phân giải thành **bao nhiêu IP, thuộc những address families nào, theo thứ tự nào**?
2. Máy/JVM nhìn thấy **những `NetworkInterface` nào**, mỗi giao diện có những `InterfaceAddress`, prefix, MTU và flags gì?
3. **Bind một socket vào loopback hoặc IP cụ thể** khác gì với chỉ resolve tên, và làm sao xác nhận endpoint thực sự của socket?
4. Kết quả nào là sự thật quan sát tại thời điểm đo, còn kết quả nào **không được suy ra** từ DNS, flags, route hoặc một phép ping đơn lẻ?

Mọi chương trình mặc định chỉ khảo sát **`localhost`, interfaces hiện có và loopback**; **không truy cập Internet**, không dò cổng của máy khác. Khi truyền hostname của môi trường thực, chỉ đo trên dịch vụ/hạ tầng được phép và cân nhắc log địa chỉ IP, hostname, interface name hoặc MAC có thể chứa thông tin nhạy cảm. Bài không yêu cầu quyền administrator hay thay cấu hình mạng.

## 1. Phân biệt năm khái niệm trước khi chạy thí nghiệm

~~~text
Hostname / URI host (ví dụ service.example.test)
                   |
                   | Name resolution (hosts, OS resolver, DNS/cache...)
                   v
       [candidate IP #1, candidate IP #2, ...]
                   |
                   | Chọn địa chỉ đích và thử kết nối
                   v
         Remote IP address + port
                   |
                   | OS routing / address selection / policy
                   v
         Local source IP + local ephemeral port
                   |
                   | Network interface / routing table / network namespace
                   v
               Đường truyền
~~~

**Không đồng nhất**:

- **Hostname:** tên do ứng dụng hoặc URL cung cấp. Một tên có thể map tới 0, 1 hoặc nhiều IP; có thể đổi theo thời gian.
- **`InetAddress`:** một IP address object (IPv4 hoặc IPv6); không chứa TCP/UDP port. Một mảng `InetAddress[]` là các ứng viên, **không** phải danh sách TCP connections đã thành công.
- **`InetSocketAddress`:** một endpoint gồm IP/hostname + **port**, có thể ở trạng thái **unresolved**.
- **`NetworkInterface`:** một giao diện mà JVM nhìn thấy ở hệ thống hiện tại; một interface có thể không có IP, có một IP hoặc nhiều IP thuộc nhiều families.
- **Routing/source-address selection:** quyết định giao diện/địa chỉ nguồn cho **đích cụ thể**; không suy chắc chỉ từ việc `NetworkInterface.isUp()` là true.

Một card Wi-Fi có thể mang địa chỉ IPv4 private, một hoặc nhiều IPv6 global/link-local và IPv6 temporary/privacy addresses. Đồng thời máy có Ethernet, loopback, VPN, VPN split tunnel, VLAN, Docker/veth, Hyper-V/VMware adapters hoặc interfaces chỉ hiện trong network namespace của container.

**DNS A/AAAA không có nghĩa giao diện địa phương nào đang dùng.** `A` cung cấp địa chỉ IPv4 ứng viên; `AAAA` cung cấp địa chỉ IPv6 ứng viên. Kết quả từ Java resolver có thể còn đến từ `hosts`, cache hoặc cơ chế name service khác, không nhất thiết có một truy vấn DNS mới.

## 2. Bảng API Java 17 nên nhớ

| API | Trả gì? | Dùng cho mục đích |
| --- | --- | --- |
| `InetAddress.getAllByName(host)` | `InetAddress[]` từ name service | Khảo sát **nhiều candidate addresses** |
| `InetAddress.getByName(host)` | **Một** `InetAddress` | Tra một địa chỉ, không đủ để khảo sát dual-stack |
| `InetAddress.getLoopbackAddress()` | IPv4 127.0.0.1 hoặc IPv6 ::1 tùy môi trường | Thí nghiệm an toàn trong máy |
| `InetAddress.getLocalHost()` | IP sau khi resolve **tên của local host** | Chẩn đoán tên máy; **không** liệt kê mọi interface |
| `InetAddress.getByAddress(rawBytes)` | IPv4/IPv6 object từ bytes hợp lệ | Tạo IP object **không cần reverse lookup** |
| `InetAddress.getHostAddress()` | Chuỗi địa chỉ IP dạng literal | Hiển thị IP, không cần reverse DNS |
| `InetAddress.getCanonicalHostName()` | Tên canonical tốt nhất có thể | Có thể phát sinh reverse/name lookup, có thể chậm |
| `InetSocketAddress.createUnresolved(host,port)` | Endpoint hostname + port, **chưa DNS** | Lưu target hoặc cho một số proxy tự resolve |
| `NetworkInterface.getNetworkInterfaces()` | Enumeration các interfaces | Khảo sát thiết bị mà JVM thấy |
| `NetworkInterface.getByName(name)` | Interface theo name hoặc null | Chọn giao diện cụ thể sau khi liệt kê |
| `NetworkInterface.getByInetAddress(ip)` | Interface có **IP local** đó hoặc null | Tìm interface sở hữu một địa chỉ local |
| `NetworkInterface.getInterfaceAddresses()` | List `InterfaceAddress` | IP/prefix/broadcast của một interface |
| `NetworkInterface.getInetAddresses()` | Enumeration `InetAddress` | IPs của giao diện, **không gồm prefix** |
| `NetworkInterface.isUp/isLoopback/isVirtual` | Thuộc tính interface | Chẩn đoán trạng thái/loại |
| `NetworkInterface.supportsMulticast()` | Khả năng multicast được báo cáo | Không chứng minh multicast packets chắc chắn tới |
| `NetworkInterface.getMTU()` | Maximum Transmission Unit được báo cáo | Dữ liệu tham khảo về network path |
| `Inet6Address.getScopeId()` | Numeric scope identifier | Quan trọng với IPv6 scoped/link-local |
| `Socket.getLocalAddress/getLocalPort` | Endpoint **nguồn đã chọn** sau connect/bind | Quan sát socket thật |
| `Socket.getInetAddress/getPort` | Endpoint **đích đã connect** | Phân biệt route thực với DNS candidates |

Các APIs có thể ném `SocketException`, `UnknownHostException` hoặc `SecurityException` tùy môi trường. Việc một interface hoặc address không hiện ở JVM **không chứng minh OS không có nó**, vì container/network namespace, access controls và trạng thái mạng có thể làm danh sách khác nhau. Một snapshot cũng không bảo đảm giữ nguyên khi VPN/Wi-Fi chuyển trạng thái.

## 3. Đọc kết quả DNS cho đúng: một tên không đồng nghĩa một IP

### 3.1. Tại sao `getAllByName` quan trọng hơn `getByName`?

~~~java
InetAddress[] candidates =
        InetAddress.getAllByName("localhost");

for (InetAddress address : candidates) {
    System.out.println(address.getHostAddress());
}
~~~

Đây là **đoạn minh họa**, có import `java.net.InetAddress` và xử lý `UnknownHostException`. Trên một hệ thống, `localhost` có thể map tới cả `127.0.0.1` và `::1`; trên hệ khác chỉ trả một family. Với hostname dịch vụ, resolver có thể trả nhiều A/AAAA, một số IP thay đổi theo DNS round-robin hoặc load balancing.

`InetAddress.getByName(host)` trả **một address**. Nó không chứng minh “host chỉ có đúng IP đó”. Nếu cần quan sát mọi ứng viên ở thời điểm đo, dùng `getAllByName`. Tuy nhiên **“all” ở đây nghĩa là tất cả address entries mà configured name service trả về trong lần tra cứu**, không bảo đảm bạn đã tìm được mọi backend trong một service discovery system.

**Đặc biệt:** `InetAddress.getByName(null)` hoặc hostname rỗng theo Java 17 có semantics trả loopback. Không dùng giá trị rỗng để kiểm tra “DNS không có host”; validate input trước, tránh lỡ kết nối localhost.

### 3.2. Vì sao thứ tự A/AAAA không ổn định hoặc thay đổi giữa máy?

Những yếu tố có thể ảnh hưởng:

- OS resolver policy, `hosts`, local DNS proxy, VPN DNS, split-horizon/internal DNS.
- DNS server trả nhiều A/AAAA với thứ tự và TTL khác nhau.
- Java name-resolution cache: JVM có thể phục vụ kết quả cũ trong TTL; negative lookup cũng có cache.
- Khả năng IPv4/IPv6 của OS/network namespace, dual-stack configuration.
- `java.net.preferIPv4Stack` và `java.net.preferIPv6Addresses` được đọc lúc JVM khởi động.
- Container image với `/etc/hosts`/resolver configuration riêng và network namespace riêng.

Cùng một hostname ở laptop và container **có thể đúng khi trả các danh sách khác nhau**, vì hai môi trường dùng cấu hình/namespace/resolver khác. Nếu một lần `getAllByName` trả `[IPv4, IPv6]` và lần khác trả `[IPv6, IPv4]`, không mặc định đó là lỗi DNS. Cần đối chiếu policy và thời điểm đo.

### 3.3. Câu hỏi kiểm thử gợi ý

Khi khảo sát một tên được phép, ghi:

| Trường đo | Ví dụ cách ghi |
| --- | --- |
| Environment | Máy vật lý/VM/container, JDK vendor/version |
| Input host | Domain hoặc hostname test được duyệt |
| Time of query | Timestamp UTC hoặc local có timezone |
| Candidate count | Độ dài `getAllByName(host)` |
| Family and position | `[0] IPv4`, `[1] IPv6`, ... |
| Literal IP | `getHostAddress()`, chỉ lưu nội bộ khi nhạy cảm |
| JVM preference flags | `java.net.preferIPv4Stack` và `java.net.preferIPv6Addresses` |
| DNS cache settings | `networkaddress.cache.ttl`, negative TTL, actual implementation defaults |
| DNS resolver evidence | Hosts/resolv.conf/OS DNS settings hoặc tool DNS |
| Connect outcome | Kết quả mỗi IP/port **trên dịch vụ được phép**, có timeout |
| Local source address | `Socket.getLocalAddress()` của **kết nối đã thành công** |

Không lấy thời gian chạy `getAllByName` làm “network RTT DNS chính xác”: có thể là cache hit hoặc hosts lookup không gửi packet, JIT/scheduling/GC còn tạo nhiễu.

## 4. Ví dụ Java 17+ #1: khảo sát nhiều địa chỉ bằng `InetAddress`

Ví dụ này dùng `localhost` mặc định để hoạt động offline. Nếu truyền một hostname khác, JVM sẽ thực hiện name resolution theo cấu hình thật của môi trường — **chỉ truyền domain được phép thử nghiệm**.

Tạo file **`DnsLookupSurveyDemo.java`**:

~~~java
import java.net.*;
import java.util.*;

public final class DnsLookupSurveyDemo {
    public static void main(String[] args)
            throws Exception {
        if (args.length > 1) {
            throw new IllegalArgumentException(
                    "Usage: java DnsLookupSurveyDemo [host]");
        }
        String host =
                args.length == 0 ? "localhost" : args[0];
        if (host.isBlank()) {
            throw new IllegalArgumentException(
                    "Host must not be blank");
        }

        long started = System.nanoTime();
        InetAddress[] all =
                InetAddress.getAllByName(host);
        long elapsedNanos = System.nanoTime() - started;

        System.out.println("queried host: " + host);
        System.out.println(
                "addresses returned: " + all.length);

        for (int i = 0; i < all.length; i++) {
            InetAddress address = all[i];
            String family =
                    address instanceof Inet4Address
                    ? "IPv4" : "IPv6";

            System.out.println(
                    "candidate[" + i + "] " + family
                    + " literal=" + address.getHostAddress()
                    + " loopback=" + address.isLoopbackAddress()
                    + " linkLocal=" + address.isLinkLocalAddress());

            if (address instanceof Inet6Address v6) {
                System.out.println(
                        "  v6 scopeId=" + v6.getScopeId()
                        + " scopedInterface=" +
                        (v6.getScopedInterface() == null
                                ? "(none)"
                                : v6.getScopedInterface().getName()));
            }
        }

        System.out.println(
                "lookup nanos nonnegative: " +
                (elapsedNanos >= 0));
        System.out.println(
                "has at least one candidate: " +
                (all.length > 0));

        InetAddress first = InetAddress.getByName(host);
        System.out.println(
                "getByName family: " +
                (first instanceof Inet4Address
                        ? "IPv4" : "IPv6"));

        InetAddress localLoopback =
                InetAddress.getLoopbackAddress();
        System.out.println(
                "system loopback recognized: " +
                localLoopback.isLoopbackAddress());

        InetAddress synthetic4 =
                InetAddress.getByAddress(
                        new byte[]{127, 0, 0, 1});
        byte[] synthetic6bytes = new byte[16];
        synthetic6bytes[15] = 1;
        InetAddress synthetic6 =
                InetAddress.getByAddress(synthetic6bytes);

        System.out.println(
                "synthetic v4 bytes: " +
                synthetic4.getAddress().length);
        System.out.println(
                "synthetic v6 bytes: " +
                synthetic6.getAddress().length);

        InetSocketAddress unresolved =
                InetSocketAddress.createUnresolved(
                        "service.example.invalid", 8443);
        System.out.println(
                "unresolved without DNS: " +
                unresolved.isUnresolved());
        System.out.println(
                "unresolved hostname: " +
                unresolved.getHostString());
    }
}
~~~

Chạy:

~~~bash
javac --release 17 DnsLookupSurveyDemo.java
java DnsLookupSurveyDemo
java DnsLookupSurveyDemo localhost
~~~

Có thể thêm hostname thuộc hệ thống của bạn:

~~~bash
java DnsLookupSurveyDemo my-authorized-service.internal
~~~

**Lưu ý:** lệnh cuối là minh họa tên mạng nội bộ, chỉ chạy khi service/hostname đó tồn tại và bạn được phép kiểm tra. Không cần DNS công cộng trong bài test mặc định.

Một **ví dụ output đã quan sát trên một máy JDK cục bộ**:

~~~text
queried host: localhost
addresses returned: 2
candidate[0] IPv4 literal=127.0.0.1 loopback=true linkLocal=false
candidate[1] IPv6 literal=0:0:0:0:0:0:0:1 loopback=true linkLocal=false
  v6 scopeId=0 scopedInterface=(none)
lookup nanos nonnegative: true
has at least one candidate: true
getByName family: IPv4
system loopback recognized: true
synthetic v4 bytes: 4
synthetic v6 bytes: 16
unresolved without DNS: true
unresolved hostname: service.example.invalid
~~~

**Đây không phải stdout được bảo đảm trên mọi hệ điều hành**: số lượng, thứ tự, family và literal text của `localhost` phụ thuộc cấu hình. Những dòng `synthetic v4 bytes: 4`, `synthetic v6 bytes: 16` và `unresolved without DNS: true` mang tính xác định cho logic trong ví dụ. Chương trình không kết nối tới `service.example.invalid` vì `createUnresolved` chỉ tạo endpoint object.

### 4.1. Vì sao không gọi `getCanonicalHostName()` trong vòng lặp mặc định?

`getHostAddress()` cho chuỗi literal. `getHostName()` có thể trả tên đã biết khi object xuất phát từ hostname, còn `getCanonicalHostName()` có thể thực hiện reverse name lookup. Reverse lookup có thể:
- chậm, timeout hoặc bị chặn bởi DNS/security policy;
- trả lại IP literal khi không tìm được tên;
- cho tên không khớp với forward DNS hiện tại;
- khiến test tưởng đang đo cùng một lần forward lookup dù đã thực hiện thêm work.

Nếu muốn khảo sát **reverse DNS**, hãy mở một thí nghiệm riêng, log latency riêng, dùng tên/địa chỉ được phép và **không dùng PTR record như chứng cứ xác thực identity**. TLS hostname verification hoặc service identity cần cơ chế riêng.

### 4.2. Đọc các flags trên `InetAddress`

| Method | Diễn giải đúng |
| --- | --- |
| `isAnyLocalAddress()` | Địa chỉ wildcard/unspecified, không phải một remote destination có thể kết nối bình thường |
| `isLoopbackAddress()` | IPv4 loopback hoặc IPv6 ::1, lưu lượng quay về local stack |
| `isLinkLocalAddress()` | Địa chỉ có scope trong link; IPv6 link-local thường cần scope/interface khi gửi |
| `isSiteLocalAddress()` | Phân loại theo API, **không phải phân loại bảo mật đầy đủ của private IP toàn Internet** |
| `isMulticastAddress()` | Destination thuộc multicast range; không chứng minh NIC đã join hoặc mạng hỗ trợ |
| `getAddress().length` | 4 cho IPv4, 16 cho IPv6 (sau normalizing của API) |
| `getHostAddress()` | Literal text, với IPv6 scoped có thể gồm zone identifier |

Những flags này giúp mô tả địa chỉ, **không kiểm tra được DNS integrity, routing, firewall hay reachability**. Ví dụ `127.0.0.1` là loopback nhưng service port 9000 có thể chưa listen; kết nối vẫn `Connection refused`.

## 5. `InetSocketAddress`: hostname có thể chưa được phân giải

Cần phân biệt ba đối tượng:

~~~java
InetSocketAddress literal = new InetSocketAddress(
        InetAddress.getLoopbackAddress(), 8080);

InetSocketAddress resolved = new InetSocketAddress(
        "localhost", 8080);

InetSocketAddress unresolved =
        InetSocketAddress.createUnresolved(
                "service.example.invalid", 8080);
~~~

Đoạn này là **mã minh họa trong phương thức Java** có import `java.net.*`. Ý nghĩa:

- `new InetSocketAddress(InetAddress, port)`: caller đã có IP object, không cần resolve lại host string.
- `new InetSocketAddress(String, port)`: **cố gắng resolve hostname ngay khi tạo object**; nếu thất bại nó có thể vẫn tạo object `isUnresolved()==true`, thay vì luôn ném `UnknownHostException`.
- `createUnresolved(String, port)`: chủ động **không resolve** lúc tạo; `getHostString()` có thể trả hostname không tạo reverse DNS; `getAddress()` trả `null` khi unresolved.

Một unresolved endpoint hữu ích khi transport/proxy **được thiết kế** để tự resolve hostname (ví dụ SOCKS5 hỗ trợ chuyển hostname). Nhưng **không phải mọi `Socket.connect`/`SocketChannel.connect` đều nhận unresolved endpoint khi kết nối trực tiếp**; một API có thể ném `UnknownHostException` hoặc `UnresolvedAddressException`. Không dùng `createUnresolved` như cách “bảo đảm luôn connect được dù DNS lỗi”.

### 5.1. Phân biệt DNS name và socket port

DNS A/AAAA chỉ nói về IP candidates. `service.example.test:443` có:
- host = `service.example.test`;
- port = `443`;
- resolved candidates = IPs do resolver trả;
- transport = TCP hoặc UDP tùy API/protocol;
- TLS identity = hostname/authority của dịch vụ, **không phải chuỗi IP tự động xác thực**.

Thử connect tới một candidate mà bỏ URL hostname có thể phá SNI, certificate hostname verification, virtual-host routing và policy proxy. Nếu cần chọn IP cụ thể vì troubleshooting, giữ nguyên **logical hostname** trong HTTP Host/authority và TLS SNI/endpoint identification theo thư viện và chính sách — không tắt xác thực TLS để ép một IP hoạt động.

## 6. Cấu hình IPv4/IPv6 của JVM: không chỉ do DNS

Oracle Java 17 liệt kê:

| Property | Giá trị thường mặc định | Ảnh hưởng |
| --- | --- | --- |
| `java.net.preferIPv4Stack` | `false` | Khi true, dùng IPv4-only socket stack và không trao đổi với IPv6-only peers |
| `java.net.preferIPv6Addresses` | `false` | Với host dual-stack, mặc định Java thiên về IPv4 để tương thích ngược |
| `java.net.preferIPv6Addresses=system` | Chọn tường minh | Giữ thứ tự địa chỉ do OS trả theo property semantics |
| `networkaddress.cache.ttl` | Phụ thuộc security settings/implementation | Cache kết quả resolve **thành công** theo seconds |
| `networkaddress.cache.negative.ttl` | Mặc định thường 10 giây | Cache resolve **thất bại** theo seconds |

Hai `java.net.prefer...` là **JVM startup properties**: được kiểm tra **một lần khi VM khởi động** theo Java 17 docs. Hãy chạy **các process Java riêng** để so sánh:

~~~bash
java DnsLookupSurveyDemo localhost
java -Djava.net.preferIPv6Addresses=true DnsLookupSurveyDemo localhost
java -Djava.net.preferIPv6Addresses=system DnsLookupSurveyDemo localhost
java -Djava.net.preferIPv4Stack=true DnsLookupSurveyDemo localhost
~~~

**Đừng kỳ vọng kết quả chắc chắn khác ở cả bốn lần.** Nếu OS hoặc hostname không có IPv6 candidate, property không thể tạo một AAAA record mới. Nếu IPv6 bị disable, `-Djava.net.preferIPv6Addresses=true` không chữa được. Nếu Linux/container có resolver/hosts policy riêng, thứ tự cũng có thể giống nhau.

Với Windows PowerShell, các lệnh Java trên có thể chạy một dòng; nếu shell diễn giải đặc biệt một tham số `-D...`, đặt tham số trong dấu nháy khi cần. Không sửa system-wide networking properties của dịch vụ production để chạy thí nghiệm.

### 6.1. DNS cache TTL là security property, không phải system property thông thường

Tài liệu Java 17 phân biệt:

- `networkaddress.cache.ttl`: TTL kết quả thành công.
- `networkaddress.cache.negative.ttl`: TTL `UnknownHostException`/lookup thất bại.

Đây là **security properties**. Đặt `-Dnetworkaddress.cache.ttl=0` hoặc `System.setProperty("networkaddress.cache.ttl","0")` **không phải cách đúng được Java 17 tài liệu cam kết**. Có thể cấu hình qua security configuration (`java.security`) hoặc application startup security policy theo JDK; cần biết JDK version và quyền vận hành. `Security.getProperty(...)` đọc configured security property; giá trị `null`/trống không cho phép khẳng định cache “tắt”.

Với TTL:
- `-1` (âm) thường nghĩa cache vô hạn theo policy.
- `0`: không cache.
- Giá trị dương: số giây lưu cache entry, **không phải TTL DNS authoritative record nhất thiết giống hệt**.
- Cache positive/negative có thể khác nhau.
- Các cơ chế OS resolver cache, DNS stub, VPN DNS và server cache vẫn tồn tại **ngoài cache JVM**.

Đừng đo “DNS TTL” bằng cách gọi cùng hostname 1.000 lần trong một JVM: kết quả có thể chỉ lấy từ cache hoặc `hosts`, không có request DNS nào được gửi.

### 6.2. Thí nghiệm cache có kiểm soát

Để hiểu cache mà không thay DNS thật:
1. Dùng một test DNS zone/server được cho phép với record có TTL nhỏ và logging.
2. Chạy các JVM process riêng với cấu hình security-property được kiểm soát từ startup.
3. Ghi timestamp, hostname, `getAllByName` results và DNS server query logs; không chỉ đo latency.
4. Đổi record theo quy trình test; đợi cache positive/negative hết hạn.
5. So sánh JVM cache vs OS resolver cache; xem có requests tới DNS server thực hay không.
6. Dừng và khôi phục cấu hình sau test. Không thay toàn bộ DNS production chỉ để minh họa.

Với Java 17, mặc định `networkaddress.cache.ttl` khi không có SecurityManager là implementation-specific theo Javadoc, **không nên ghi một giá trị cố định cho mọi JDK vendors/builds**.

## 7. `NetworkInterface`: card mạng không nhất thiết là card vật lý

`NetworkInterface` đại diện cho interface có tên/index và các IP gán vào nó. Một máy có thể liệt kê:
- Loopback, thường gọi `lo` (Linux/macOS) hoặc interface khác ở Windows.
- Ethernet/Wi-Fi.
- VPN/TUN/TAP.
- Interfaces của Docker/Kubernetes/WSL/Hyper-V.
- VLAN/subinterfaces.
- Interfaces đã down hoặc không có IP.

Vì vậy:
- `getName()` là tên do platform/JDK cung cấp, không nên hard-code `eth0`.
- `getDisplayName()` có thể thân thiện với người dùng nhưng có thể null/khác tên.
- `getIndex()` là index trong OS hiện tại; không phải định danh bền vững qua reboot/container.
- `isUp()==true` chỉ báo interface up/running, **không chứng minh Internet connectivity**.
- `isLoopback()==true` mô tả interface loopback; không có nghĩa mọi traffic qua nó đều an toàn theo business policy.
- `isVirtual()==true` có nghĩa virtual/subinterface theo API, **không đảm bảo tất cả VPN/VM adapters đều trả true**. Một adapter ảo ở hypervisor vẫn có thể có `isVirtual()==false` trong Java.
- `isPointToPoint()==true` mô tả kiểu link, không phải “TCP connected”.
- `supportsMulticast()==true` là capability được báo cáo, không chứng minh IGMP/MLD/firewall/routing hoạt động.
- `getMTU()` là MTU của interface, **không phải Path MTU** chắc chắn tới remote destination.
- `getHardwareAddress()` có thể null vì interface không có MAC hoặc quyền bị hạn chế; MAC cũng có thể thay đổi/randomized. **Không in raw MAC trong log mặc định**.

### 7.1. `getInetAddresses` khác `getInterfaceAddresses`

~~~java
for (InterfaceAddress assigned :
        nic.getInterfaceAddresses()) {
    InetAddress ip = assigned.getAddress();
    short prefix = assigned.getNetworkPrefixLength();
    InetAddress broadcast = assigned.getBroadcast();
}
~~~

Đây là **đoạn minh họa** với `NetworkInterface nic` có sẵn. `getInetAddresses()` chỉ liệt kê IP objects. `getInterfaceAddresses()` thêm:
- `getNetworkPrefixLength()`: số bit prefix, ví dụ IPv4 `/24`; Java trả `short`.
- `getBroadcast()`: với IPv4 có thể có broadcast address, nhưng **có thể null** nếu không có/không áp dụng; với IPv6 trả null vì IPv6 **không có broadcast** theo cùng semantics.

Ví dụ địa chỉ IPv4 `192.0.2.15/24` biểu diễn địa chỉ nằm trong prefix `192.0.2.0/24` ở một tình huống thông thường. Địa chỉ ở đây thuộc dải documentation (không phải IP của máy người học). **Không suy chắc gateway/route chỉ từ prefix**: cần routing table và neighbor/next-hop information.

IPv6 interface address có thể là `2001:db8::1234/64` (địa chỉ documentation) hoặc `fe80::.../64` (link-local), thêm scope identifier. `getBroadcast()==null` là bình thường với IPv6.

## 8. Ví dụ Java 17+ #2: khảo sát interfaces, IP assignments, prefix và MTU

Chương trình mặc định **ẩn IP literal và broadcast** để tránh chia sẻ vô tình thông tin hạ tầng trong màn hình/CI logs. Nó vẫn hiển thị interface name/index, flags, prefix, IPv4/IPv6 và scope; bạn có thể bật `--show-addresses` khi **được phép** và chạy trong môi trường nội bộ. Chương trình **không in MAC address**.

Tạo file **`NetworkInterfaceSurveyDemo.java`**:

~~~java
import java.net.*;
import java.util.*;

public final class NetworkInterfaceSurveyDemo {
    private static String addressFamily(
            InetAddress address) {
        return address instanceof Inet4Address
                ? "IPv4" : "IPv6";
    }

    public static void main(String[] args)
            throws Exception {
        if (args.length > 1 ||
                (args.length == 1 &&
                 !"--show-addresses".equals(args[0]))) {
            throw new IllegalArgumentException(
                    "Usage: java NetworkInterfaceSurveyDemo " +
                    "[--show-addresses]");
        }

        boolean showAddresses = args.length == 1;
        Enumeration<NetworkInterface> enumeration =
                NetworkInterface.getNetworkInterfaces();

        List<NetworkInterface> interfaces =
                enumeration == null
                ? new ArrayList<>()
                : Collections.list(enumeration);

        interfaces.sort(Comparator.comparing(
                NetworkInterface::getName,
                Comparator.nullsLast(String::compareTo)));

        System.out.println(
                "network interfaces found: " +
                interfaces.size());
        System.out.println(
                "address details enabled: " +
                showAddresses);

        int ipv4 = 0;
        int ipv6 = 0;

        for (NetworkInterface nic : interfaces) {
            try {
                System.out.println(
                        "interface name=" + nic.getName()
                        + " index=" + nic.getIndex()
                        + " up=" + nic.isUp()
                        + " loopback=" + nic.isLoopback()
                        + " virtual=" + nic.isVirtual()
                        + " p2p=" + nic.isPointToPoint()
                        + " multicast=" +
                            nic.supportsMulticast()
                        + " mtu=" + nic.getMTU());

                for (InterfaceAddress assignment :
                        nic.getInterfaceAddresses()) {
                    InetAddress address =
                            assignment.getAddress();
                    if (address == null) continue;

                    if (address instanceof Inet4Address) {
                        ipv4++;
                    } else {
                        ipv6++;
                    }

                    String literal = showAddresses
                            ? address.getHostAddress()
                            : "[hidden]";
                    InetAddress broadcast =
                            assignment.getBroadcast();

                    System.out.println(
                            "  " + addressFamily(address)
                            + " address=" + literal
                            + " prefix=" +
                                assignment.getNetworkPrefixLength()
                            + " broadcast=" +
                            (broadcast == null
                                    ? "(none)"
                                    : showAddresses
                                        ? broadcast.getHostAddress()
                                        : "[hidden]"));

                    if (address instanceof Inet6Address v6) {
                        System.out.println(
                                "    scopeId=" + v6.getScopeId()
                                + " scopedInterface=" +
                                (v6.getScopedInterface() == null
                                    ? "(none)"
                                    : v6.getScopedInterface()
                                            .getName()));
                    }
                }
            } catch (SocketException issue) {
                System.out.println(
                        "interface unavailable: " +
                        nic.getName()
                        + " type=" +
                        issue.getClass().getSimpleName());
            }
        }

        System.out.println(
                "IPv4 assignments: " + ipv4);
        System.out.println(
                "IPv6 assignments: " + ipv6);
        System.out.println(
                "MAC bytes intentionally not printed");
    }
}
~~~

~~~bash
javac --release 17 NetworkInterfaceSurveyDemo.java
java NetworkInterfaceSurveyDemo
~~~

Chỉ khi có quyền xem/log IP địa phương:

~~~bash
java NetworkInterfaceSurveyDemo --show-addresses
~~~

**Output là dữ liệu sống, không có stdout cố định cho mọi máy.** Một JDK chạy trên workstation có thể thấy vài interfaces, nhưng máy có VPN/virtual adapters có thể thấy hàng chục, container chỉ thấy một subset. Phần cuối sẽ có hai dòng thống kê số IPv4/IPv6 assignments và dòng `MAC bytes intentionally not printed`. Ví dụ đã chạy trên một môi trường thử với **74 interface entries**, nhưng **không lấy con số đó làm expected result**.

### 8.1. Cách đọc output từ từng interface

Giả sử nhìn thấy một dòng dạng:

~~~text
interface name=eth0 index=2 up=true loopback=false virtual=false p2p=false multicast=true mtu=1500
  IPv4 address=[hidden] prefix=24 broadcast=[hidden]
  IPv6 address=[hidden] prefix=64 broadcast=(none)
    scopeId=2 scopedInterface=eth0
~~~

Đây là **output minh họa format** (không phải dữ liệu máy đang sử dụng). Diễn giải:
- `up=true`: OS báo interface đang up, không chứng minh có route đến Internet.
- `loopback=false`: không phải loopback interface.
- `virtual=false`: Java không phân loại nó là virtual subinterface; không khẳng định hardware vật lý.
- `p2p=false`: không báo kiểu point-to-point.
- `multicast=true`: báo hỗ trợ multicast; muốn join group vẫn phải chọn đúng network interface/address family và xác minh OS/network.
- `mtu=1500`: MTU local, không nói path MTU tới peer là 1500.
- IPv4 `prefix=24`: số bit network prefix, không phải subnet gateway.
- IPv6 `broadcast=(none)`: đúng vì IPv6 không dùng broadcast kiểu IPv4.
- `scopeId=2`: numeric scope của IPv6; giá trị phụ thuộc OS/interface, không bền vững.

Interface không có `InterfaceAddress` trong output **không nhất thiết bị lỗi**: nó có thể đang down, chỉ có link-level state, không được gán IP hoặc JVM không được phép xem addresses.

### 8.2. Kiểm tra MAC và quyền truy cập

Có thể gọi `nic.getHardwareAddress()` khi thật sự cần inventory/debug NIC; method có thể trả byte array hoặc null. Nhưng **MAC không phải định danh bí mật bất biến**, có thể randomize, alias, thay qua VM/VPN, và có thể bị security policy hạn chế. Nếu log trong production, mask/hash có kiểm soát và có retention policy; đừng in thẳng để “chứng minh card mạng”.

## 9. IPv6 scopes: vì sao link-local phải gắn đúng interface?

IPv4 và IPv6 đều là IP, nhưng IPv6 có vấn đề **scope** rõ rệt:

- `::1` là IPv6 loopback.
- `fe80::/10` thuộc nhóm IPv6 link-local, thường dùng trên một đường link; để kết nối tới link-local peer, hệ điều hành cần biết **interface/link cụ thể**.
- `2001:db8::/32` là prefix tài liệu, không phải đích thực để kiểm thử Internet.
- Một host có thể có nhiều IPv6 addresses cho cùng một NIC, bao gồm temporary/privacy addresses.

Hai interfaces khác nhau có thể dùng cùng một địa chỉ link-local dạng giống nhau. Do đó một IPv6 endpoint có thể cần **zone identifier**:

~~~text
fe80::1234%eth0
fe80::1234%7
~~~

Các chuỗi trên là **dạng minh họa**; `eth0` hay scope index `7` chỉ là ví dụ, không phải interface thật trong môi trường hiện tại. Trên Windows, tên zone/index có thể khác. `Inet6Address.getScopeId()` và `getScopedInterface()` cung cấp scope information của object nếu có.

### 9.1. Không xóa scope khi lưu IPv6 địa chỉ

Nếu lấy `Inet6Address.getHostAddress()` của scoped link-local address, output có thể chứa `%scope`. Không dùng logic `split("%")[0]` rồi mất interface context khi cần kết nối. Không xem IPv6 link-local như global address có thể route qua nhiều hops. Khi tạo `InetSocketAddress`, giữ đúng scoped Inet6Address/zone identifier khi cần.

**IPv6 URL syntax khác literal socket syntax**: trong URI, literal IPv6 phải được bao trong `[ ]`, và escaped zone identifier có quy tắc đặc biệt theo URI standard. Không nối thô `"http://" + ipv6.getHostAddress() + ":8080"` vì dấu `:` trong IPv6 gây ambiguity. Ưu tiên `URI` builder/validated syntax đúng spec hoặc logical hostname.

### 9.2. Không tự suy loại private/global chỉ bằng `isSiteLocalAddress`

IPv6 site-local addressing cũ đã bị deprecate trong các chuẩn địa chỉ, còn ULA `fc00::/7` có semantics riêng. `InetAddress.isSiteLocalAddress()` không thay thế ACL/route policy hoặc IP classifier đầy đủ. Với security-sensitive code (SSRF, allowlist), xét cụ thể IPv4/IPv6, link-local, loopback, unspecified, multicast, ULA/private ranges, mapped addresses, DNS rebinding và proxy rules.

## 10. Loopback, wildcard và địa chỉ nguồn: thí nghiệm xác nhận bằng socket thật

Có ba trường hợp dễ nhầm:

| Local bind | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Loopback cụ thể | Chỉ bind vào loopback của family đó | `127.0.0.1:port` hoặc `[::1]:port` |
| Local interface address cụ thể | Bind vào một địa chỉ IP gán cho interface | Ví dụ IPv4 của máy hoặc scoped IPv6 |
| Wildcard/any-local | Lắng nghe trên các địa chỉ local phù hợp stack/config | `0.0.0.0:port` hoặc `[::]:port` |

**Không đặt một server nhạy cảm bind wildcard chỉ để debug**: wildcard có thể vô tình mở dịch vụ cho các NIC/VPN/container networks, tùy firewall/stack. Với demo chỉ dùng loopback.

### 10.1. `getLocalHost` không phải interface list

`InetAddress.getLocalHost()` lấy hostname của máy rồi resolve tên đó. Nếu file `hosts` mapping hostname tới loopback, bạn sẽ thấy loopback; nếu host map tới một IP LAN, sẽ thấy IP đó; nếu hostname resolution lỗi, có thể ném `UnknownHostException`. **Nó không liệt kê mọi NIC/IP** và không chứng minh địa chỉ outbound của một socket.

Để biết **socket đã kết nối dùng local source IP nào**, đọc `Socket.getLocalAddress()` và `Socket.getLocalPort()` sau khi connect. Để biết đường đi đến remote, quan sát routing table/network namespace và thực tế kết nối, không chỉ chọn một địa chỉ trên NIC list.

### 10.2. Ví dụ Java 17+ #3: server bind loopback, client connect và quan sát

Ví dụ khởi động `ServerSocket` trên `InetAddress.getLoopbackAddress()` với ephemeral port `0`, dùng một thread server accept, client gửi `PING` và nhận `PONG`. Không có DNS ngoài hoặc remote Internet. Proxy được tắt rõ với `new Socket(Proxy.NO_PROXY)` để tránh accidental system proxy settings trong bài test.

Tạo file **`LoopbackBindProbeDemo.java`**:

~~~java
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.*;

public final class LoopbackBindProbeDemo {
    public static void main(String[] args)
            throws Exception {
        InetAddress loopback =
                InetAddress.getLoopbackAddress();
        NetworkInterface localNic =
                NetworkInterface.getByInetAddress(loopback);

        System.out.println(
                "bind address is loopback: " +
                loopback.isLoopbackAddress());
        System.out.println(
                "matching interface found: " +
                (localNic != null));

        try (ServerSocket server =
                new ServerSocket(0, 1, loopback)) {
            server.setSoTimeout(3000);

            FutureTask<String> accepted =
                    new FutureTask<>(() -> {
                try (Socket peer = server.accept()) {
                    peer.setSoTimeout(3000);
                    BufferedReader reader =
                            new BufferedReader(
                                new InputStreamReader(
                                    peer.getInputStream(),
                                    StandardCharsets.US_ASCII));
                    String received = reader.readLine();
                    peer.getOutputStream().write(
                            "PONG\n".getBytes(
                                    StandardCharsets.US_ASCII));
                    return received;
                }
            });

            Thread worker =
                    new Thread(accepted, "loopback-accept");
            worker.setDaemon(true);
            worker.start();

            try (Socket client =
                    new Socket(Proxy.NO_PROXY)) {
                client.connect(new InetSocketAddress(
                        loopback, server.getLocalPort()),
                        3000);
                client.setSoTimeout(3000);
                client.getOutputStream().write(
                        "PING\n".getBytes(
                                StandardCharsets.US_ASCII));

                String reply = new BufferedReader(
                        new InputStreamReader(
                                client.getInputStream(),
                                StandardCharsets.US_ASCII))
                        .readLine();
                System.out.println(
                        "client remote is loopback: " +
                        client.getInetAddress().isLoopbackAddress());
                System.out.println(
                        "client reply: " + reply);
            }

            System.out.println(
                    "server saw: " +
                    accepted.get(3, TimeUnit.SECONDS));
        }
    }
}
~~~

~~~bash
javac --release 17 LoopbackBindProbeDemo.java
java LoopbackBindProbeDemo
~~~

**Stdout đã quan sát trên JDK cục bộ**:

~~~text
bind address is loopback: true
matching interface found: true
client remote is loopback: true
client reply: PONG
server saw: PING
~~~

Trên một runtime hạn chế, `matching interface found` có thể là false hoặc bind/accept bị cấm; các môi trường sandbox không cho sockets sẽ ném exception. Kết quả ví dụ **không chứng minh NIC Ethernet/Wi-Fi đang hoạt động**: cả hai đầu ở loopback của máy.

### 10.3. Vì sao ví dụ dùng `new ServerSocket(0,1,loopback)`?

- `0`: OS tự chọn ephemeral listening port, tránh hardcode port có thể đã được dùng.
- `1`: backlog hint nhỏ cho demo, OS có thể điều chỉnh theo implementation; không phải concurrency limit chuẩn production.
- `loopback`: chọn local bind IP cụ thể, **không lắng nghe trên tất cả NICs**.
- `setSoTimeout(3000)`: bounded accept/read wait, không giữ test treo vô hạn.
- `new Socket(Proxy.NO_PROXY)`: yêu cầu direct socket, không route SOCKS mặc định của JVM.
- `getInetAddress()` của client là remote IP đã connect, còn `getLocalAddress()` (nếu thêm log) là source IP đã được chọn.
- `FutureTask.get(3,TimeUnit.SECONDS)` đợi server test trả kết quả, không phải lời khuyên tạo một thread riêng cho mọi request của server production.

### 10.4. Mở rộng: so sánh local source address với remote destination

Sau khi `Socket.connect(...)` thành công trong thí nghiệm được phép:

~~~java
System.out.println("local = " +
        client.getLocalAddress().getHostAddress()
        + ":" + client.getLocalPort());

System.out.println("remote = " +
        client.getInetAddress().getHostAddress()
        + ":" + client.getPort());
~~~

Đây là **đoạn minh họa trong khối có `Socket client` đã connected**. Với một máy có VPN/Wi-Fi/Ethernet, source IP có thể đổi theo remote IP/route; không được khẳng định một lần connect tới loopback chỉ ra source IP sẽ dùng khi đi tới Internet.

Không kết nối tới IP lạ để “kiểm tra mạng sống hay chết”. Nếu thực nghiệm remote, dùng endpoint test được phê duyệt, cổng được cho phép, kết nối một lần có timeout và không quét subnet/port range.

## 11. Một hostname trả nhiều IP: chọn địa chỉ nào để thử kết nối?

Một bản ghi DNS trả nhiều IP thường nhằm redundancy/traffic distribution/dual-stack. Nhưng:

- **Nhiều IP không có nghĩa một connection sử dụng tất cả IP.** Mỗi TCP connection có một remote endpoint IP:port (trừ những cơ chế transport đặc biệt ngoài phạm vi).
- `InetAddress.getByName(host)` chọn một candidate, không tự kiểm tra mọi IP còn lại.
- Nếu IP đầu không có route hoặc không listen port, một TCP connect có thể fail ngay hoặc timeout. Chương trình có thể cần fallback theo policy.
- Thứ tự addresses chỉ là **input** cho connection strategy; không phải phép đo độ trễ hoặc health của candidates.
- Một HTTP client cấp cao có thể thực hiện chiến lược route/proxy/connection pooling riêng; không suy nó luôn theo thứ tự bạn in từ `getAllByName`.

### 11.1. Mẫu fallback TCP cho môi trường test có kiểm soát

~~~java
// Mã minh họa: chỉ dùng host/port được phép, lỗi cần log/aggregate.
// Các imports java.net.* và java.io.IOException.
InetAddress[] candidates =
        InetAddress.getAllByName(host);
IOException last = null;
Socket connected = null;

for (InetAddress address : candidates) {
    Socket attempt = new Socket(Proxy.NO_PROXY);
    try {
        attempt.connect(
                new InetSocketAddress(address, port), 1000);
        connected = attempt;
        break;
    } catch (IOException failed) {
        last = failed;
        attempt.close();
    }
}
if (connected == null) {
    throw last != null
            ? last : new IOException("No candidate addresses");
}
// Ownership của connected phải được close bởi caller.
~~~

Đây là **đoạn minh họa không độc lập**: `host`, `port` là input đã validate, caller giữ và đóng `connected` khi xong. **Không** áp dụng ngây thơ cho POST có side effects: việc reconnect/fallback và gửi lại request khác với thử TCP connect trước khi gửi payload. Nếu đã gửi một phần application data, retry cần idempotency/deduplication.

Một chiến lược kết nối tốt có thể thử nhiều addresses có giới hạn thời gian, với trì hoãn có kiểm soát giữa IPv4/IPv6 candidates (Happy Eyeballs, RFC 8305) để không phải đợi một family timeout dài. Nhưng **không mở hàng trăm parallel sockets**, không tạo port scan, không vượt network policy. Java 17 `Socket.connect` làm một kết nối tới một endpoint tại một thời điểm; muốn Happy Eyeballs thực sự cần một strategy/HTTP client có hỗ trợ và kiểm thử cụ thể, không suy `getAllByName` tự làm điều đó.

### 11.2. Nhiều A/AAAA có thể có các trạng thái khác nhau

Một hostname dual-stack có thể:
- IPv4 connect thành công, IPv6 thất bại vì thiếu IPv6 route.
- IPv6 connect thành công, IPv4 thất bại do firewall.
- Cả hai TCP connect thành công nhưng HTTPS fail với certificate/virtual host khác.
- DNS resolve thành công nhưng port đóng ở tất cả addresses.
- Một IP thuộc internal network, một IP thuộc public network do split DNS hoặc cấu hình lỗi.

Cần ghi **failure per address family và per candidate**, không chỉ lỗi tổng `ConnectException` và kết luận “DNS hỏng”. Một `UnknownHostException` xảy ra **trước khi có danh sách IP**, còn `NoRouteToHostException`/`ConnectException`/timeout thường thuộc giai đoạn kết nối/routing (tùy platform).

## 12. Khi DNS hoạt động nhưng network request vẫn thất bại

Các lớp chẩn đoán:

| Giai đoạn | Evidence | Lỗi có thể thấy |
| --- | --- | --- |
| Validate hostname | Input nonblank, IDN policy, URI scheme | Invalid host/URI, sai tên |
| Resolve name | `getAllByName(host)` trả IPs | `UnknownHostException` hoặc stale/negative cache |
| Chọn IP family | IPv4/IPv6 candidates, JVM properties | Ưu tiên family không có route |
| Chọn route/source | OS routing table và actual local endpoint | Wrong VPN split route, source address mismatch |
| TCP connect | `Socket.connect(..., timeout)` hoặc HTTP client connection | Refused, timeout, no route |
| Proxy | ProxySelector/HTTP CONNECT/SOCKS policies | Đường đi khác direct, 407, proxy auth |
| TLS | SNI, certificate, endpoint verification | SSLHandshakeException/hostname mismatch |
| HTTP | Status, headers, response body | 4xx, 5xx, 429, redirect |
| Application | Protocol response/message semantics | Auth/session/business failure |

**`DNS success != TCP success != TLS success != HTTP 200 != business success`**. Đừng đổi hostname thành một resolved IP literal để “sửa DNS” rồi tắt certificate hostname verification; đó là thay đổi trust boundary.

### 12.1. `InetAddress.isReachable` không phải ping chắc chắn

`InetAddress.isReachable(timeout)`/overload với `NetworkInterface` có thể sử dụng ICMP echo khi OS và quyền cho phép, hoặc phương thức khác như TCP echo theo implementation. Nhiều firewall chặn probe nhưng vẫn cho phép TCP/443. Vì vậy:

- `isReachable()==false` **không chứng minh host/service down**.
- `isReachable()==true` **không chứng minh HTTP endpoint port 443 chạy**.
- Không dùng `isReachable` làm health check thay cho **ứng dụng protocol** được phép.
- Nếu dùng overload `isReachable(interface, ttl, timeout)`, phải hiểu `ttl` là hop limit/network TTL, **không** phải DNS cache TTL.
- Không biến exercise thành ping sweep/port scanner; giữ thí nghiệm ở loopback hoặc endpoint được cho phép.

## 13. Đối chiếu Java với công cụ OS và DNS

Khi có quyền kiểm tra môi trường, đối chiếu những nguồn khác nhau. **Không phải lệnh nào cũng có sẵn trên mọi OS/distro**, nên dùng công cụ phù hợp, không giả định mọi command đều trả kết quả tương đương với JVM.

| OS | DNS/hostname | Interfaces/addresses | Routes |
| --- | --- | --- | --- |
| Windows | `Resolve-DnsName host` (PowerShell), `nslookup host`, `ipconfig /all` | `Get-NetIPConfiguration`, `Get-NetIPAddress`, `Get-NetAdapter` | `Get-NetRoute`, `route print` |
| Linux | `getent ahosts host`, `resolvectl query host`, `dig A/AAAA` nếu cài | `ip address show`, `ip link show` | `ip route`, `ip -6 route`, `ip route get <IP>` |
| macOS | `dscacheutil -q host -a name host`, `scutil --dns`, `dig` nếu có | `ifconfig`, `networksetup -listallhardwareports` | `netstat -rn`, `route -n get <IP>` |

Các lệnh bên dưới minh họa cho host **localhost**, không dùng `ping`/probe Internet:

~~~powershell
# Windows PowerShell nếu có các cmdlets:
Resolve-DnsName localhost
Get-NetIPConfiguration
Get-NetIPAddress
Get-NetRoute
~~~

~~~bash
# Linux (tùy bản phân phối):
getent ahosts localhost
ip address show
ip route
ip -6 route
~~~

~~~bash
# macOS:
dscacheutil -q host -a name localhost
ifconfig
scutil --dns
netstat -rn
~~~

**Không so sánh 1:1 mà không đọc ý nghĩa command**:
- `dig` truy vấn DNS theo kiểu riêng; nó có thể **bỏ qua `/etc/hosts`/NSS policy** mà Java và `getent` dùng.
- `nslookup` có thể đi thẳng tới resolver theo cách riêng, không phản ánh toàn bộ OS/JVM cache.
- `ip address` và `ifconfig` liệt kê interfaces mà OS nhìn thấy **trong namespace hiện tại**, không phải danh sách DNS records.
- `route print`/`ip route get` cho chính sách route dựa vào destination và source, không phải kết quả của DNS.
- Trên container, shell chạy **bên trong container** và shell chạy **trên host** có thể thấy những NIC/route khác nhau; ghi rõ nơi chạy.

### 13.1. Checklist ghi evidence có thể so sánh được

Ghi bốn bộ số liệu cùng một thời điểm tương đối:
1. Java `InetAddress.getAllByName(host)`: candidate IPs/families.
2. OS resolver (`getent`, `Resolve-DnsName` hay tương đương): output.
3. Java `NetworkInterfaceSurveyDemo`: interfaces/flags/prefix.
4. OS route tới **một IP candidate cụ thể**, nếu có quyền.

Sau đó chỉ cần đưa ra **giả thuyết có kiểm chứng**: “Java đang ưu tiên IPv6 nhưng container không có IPv6 default route”, hay “loopback listener chỉ bind ::1 nhưng client đang thử 127.0.0.1”. Không khẳng định nguyên nhân chỉ vì hai output khác nhau.

## 14. DNS cache và thời gian chạy: cách tránh benchmark sai

Một thí nghiệm naive:

~~~java
for (int i = 0; i < 1000; i++) {
    InetAddress.getAllByName("localhost");
}
~~~

Đây là **đoạn minh họa**, không đánh giá hiệu năng DNS. Với cache JVM/OS và mapping loopback, vòng lặp hầu như không tương đương 1.000 DNS network queries.

Khi phân tích latency:
- Tách **cold lookup** vs **warm lookup**, và ghi điều kiện thí nghiệm.
- Xác minh có thật network DNS query ở resolver logs.
- Không sửa security cache policy của một JVM production đang phục vụ traffic.
- Dùng `System.nanoTime()` cho elapsed measurement, không suy precision/overhead chính xác từ một lần chạy.
- Một `getCanonicalHostName()` sẽ thêm reverse lookup, đo riêng.
- Một TCP connect đo **DNS + route + handshake** tùy cách gọi; nếu muốn tách, resolve trước rồi connect cụ thể mỗi IP với bounded timeout.
- Trên Windows, có thể có DNS client cache bên ngoài JVM; trên Linux có `systemd-resolved`/`nscd`/container resolver tùy cấu hình.
- Kết quả TTL/stale/negative caching thay đổi theo JVM security properties và name service.

**Không set `networkaddress.cache.ttl=0` toàn hệ thống chỉ để “mọi lần gọi đều đo được DNS”.** Cần môi trường lab riêng và hiểu tác động request load.

## 15. NetworkInterface với multicast, IPv6, VPN: dấu hiệu nào đáng tin?

Các trường hợp cần nhìn sâu hơn:

**Multicast:** `ni.supportsMulticast()` là flag capability. Một multicast receiver cần chọn địa chỉ group phù hợp IPv4/IPv6, `NetworkInterface` đúng và join membership bằng API tương ứng. Multicast có thể bị chặn ở Wi-Fi, VPN, router, IGMP/MLD, firewalls hoặc namespace dù flag true. Không suy “supportsMulticast=true” = group traffic đến chắc chắn.

**IPv6 link-local:** `scopeId`/zone rất quan trọng khi một hostname hoặc destination resolve ra `fe80::...`. Với nhiều NIC, cùng link-local network không nhất thiết có route xuyên interface; phải chọn scope đúng và không tự gỡ `%zone` khỏi address.

**VPN:** Windows/macOS/Linux có thể hiển thị tunnel NIC và route. Khi VPN bật, route tới host private có thể chuyển sang interface khác, DNS server thay đổi hoặc split DNS trả A/AAAA khác. Điều này không đồng nghĩa Java “random”; hãy ghi route/resolve trước và sau khi bật VPN trong môi trường được phép.

**Containers/Kubernetes:** Một pod thường thấy `lo` và một hoặc vài `eth0`/interfaces **trong namespace**, không thấy mọi NIC vật lý trên host. `InetAddress.getLocalHost()` có thể trả Pod IP hoặc loopback tùy `/etc/hosts` và hostname policy; không mặc định nó là IP public của node. Service DNS, headless services, search domains và NAT có thể làm một hostname cho nhiều IP hoặc một virtual service IP; API Java trả những gì configured resolver cung cấp tại thời điểm hỏi.

**Multiple NICs:** Đừng hard-code `NetworkInterface.getByName("eth0")` nếu app chạy đa nền tảng. Có thể chọn interface theo cấu hình tường minh, địa chỉ local của socket, index hoặc policy, nhưng index và address có thể thay đổi khi interface restart. Nếu cần bind vào NIC cụ thể, phải kiểm thử cả khi NIC mất/đổi tên và khi IPv6 scope khác nhau.

## 16. Chẩn đoán các lỗi thực tế

| Triệu chứng | Giả thuyết thường gặp | Điều cần đo |
| --- | --- | --- |
| `localhost` trả IPv6 trước, server chỉ nghe IPv4 | Family/bind mismatch | `getAllByName` order và `ServerSocket.getInetAddress()` |
| `UnknownHostException` trong container nhưng host OS resolve | DNS search domains/hosts/resolv.conf khác | Resolver config **trong container**, nameserver logs |
| Java thấy một IP, OS thấy nhiều | Cache, resolver/API khác, DNS preference, snapshot timing | TTL, OS lookup tool, Java preferences |
| `getLocalHost()` trả loopback dù máy có IP LAN | Hostname mapping tới loopback | Local hosts file và `NetworkInterface` IP list |
| `NetworkInterface.getByName("eth0")==null` | Interface name khác hoặc namespace khác | Liệt kê actual interface names |
| `isUp()==true` nhưng không truy cập Internet | Không có route, firewall, proxy, DNS, origin fail | Route tới remote IP, TCP connect endpoint |
| IPv6 `fe80::...` connect fail | Thiếu hoặc sai scope/interface | `Inet6Address.getScopeId/getScopedInterface` |
| `getInterfaceAddresses()` thiếu prefix ở một NIC | Interface không có địa chỉ/permissions/OS reporting | OS interface config, JVM privileges |
| `supportsMulticast()==true` nhưng không nhận | Network multicast filtering/join group/IGMP | Membership, firewall, NIC, scope |
| `getHardwareAddress()==null` | Không có MAC hoặc thiếu privilege | NIC type/OS policy, đừng coi null là lỗi bắt buộc |
| Socket bind vào `0.0.0.0` bị expose ngoài ý muốn | Wildcard bind + firewall policy | `getLocalSocketAddress`, listening sockets, security rules |
| Server bind ::1 nhưng client dùng 127.0.0.1 | Chọn khác address family | Bind family vs candidate |
| `isReachable=false` dù HTTPS hoạt động | Probe ICMP/TCP echo bị chặn | Thử **đúng protocol/port** được phép |
| Tăng DNS TTL nhưng vẫn thấy IP cũ | JVM/OS/proxy caches hoặc config khởi động sai | Security properties, process restart, resolver logs |
| Thấy IP source khác mong đợi | Routing/NAT/VPN/split tunnel | `Socket.getLocalAddress()`, OS route, NAT |
| Kết nối TCP được nhưng HTTPS fail | SNI/cert/truststore hoặc HTTP authority mismatch | TLS handshake/certificate, không tắt verification |
| Một địa chỉ A thành công, địa chỉ AAAA timeout | IPv6 route/firewall không hoạt động | Per-family connect timeout, route table |
| NIC inventory thay đổi giữa hai lần | VPN, DHCP, hotplug, namespace/permissions | Snapshot timestamp và interface state |

Đừng “fix” tất cả bằng `java.net.preferIPv4Stack=true`. Điều đó có thể giúp một nhóm sự cố dual-stack cụ thể, nhưng đồng thời **loại khả năng kết nối IPv6-only services**. Cần root-cause, policy và kiểm thử ở OS/JDK thật.

## 17. Thực hành phân tích từng bước trên máy đang chạy

### Bước 1 — Ghi môi trường

~~~bash
java -version
~~~

Ghi JDK vendor, major version và OS/runtime image. Nếu là container, ghi tên namespace/pod/environment theo policy, không đổ secrets/env vars vào log.

### Bước 2 — Chụp kết quả hostname

~~~bash
java DnsLookupSurveyDemo localhost
~~~

Điền vào biên bản nội bộ: candidate count, thứ tự IPv4/IPv6, loopback flags. Nếu được phép thử service nội bộ, đổi sang hostname được phê duyệt. Không truy vấn tên ngẫu nhiên hoặc quét DNS.

### Bước 3 — Liệt kê NIC không lộ IP

~~~bash
java NetworkInterfaceSurveyDemo
~~~

Ghi số interfaces, số IPv4/IPv6 assignments, interfaces đang up, loopback, multicast capability và MTU. Nếu thực sự cần literal IP cho troubleshooting, chạy `--show-addresses` trong terminal/log nội bộ đã được bảo vệ.

### Bước 4 — Xác minh một kết nối loopback

~~~bash
java LoopbackBindProbeDemo
~~~

Xác minh chương trình thấy `PONG` và server thấy `PING`. Nếu không chạy, cần phân biệt sandbox socket restrictions, OS firewall local, family mismatch, port policy với lỗi DNS (bài test không cần DNS ngoài).

### Bước 5 — So sánh OS/JVM

Chạy một lệnh OS resolver và một lệnh interface inventory phù hợp. Không xem `dig`, `getent` và Java luôn có một output duy nhất; ghi rõ khác biệt.

### Bước 6 — Thay đổi JVM properties trong process test mới

~~~bash
java -Djava.net.preferIPv6Addresses=true DnsLookupSurveyDemo localhost
java -Djava.net.preferIPv4Stack=true DnsLookupSurveyDemo localhost
~~~

Không chạy flags này như thay thế mặc định production khi chưa chứng minh ảnh hưởng. So sánh số/loại/thứ tự candidates; giải thích vì sao result có thể không đổi.

### Bước 7 — Rút kết luận dựa trên evidence

Viết một đoạn ngắn:
- **Quan sát:** điều gì xuất hiện ở Java/OS.
- **Giả thuyết:** DNS preference, route, scope hay binding?
- **Thử nghiệm kiểm chứng:** một thay đổi trong môi trường test (đúng IP family, bind address, route check).
- **Kết quả:** đo lại có cải thiện không?
- **Giới hạn:** điều gì chưa được xác minh (TLS, HTTP, routing, external reachability)?

Đây là một **bài điều tra reproducible**, không phải “chạy vài lệnh rồi kết luận DNS lỗi”.

## 18. Những lỗi người học rất dễ gặp

| Sai lầm | Hậu quả | Cách hiểu đúng |
| --- | --- | --- |
| `getByName(host)` trả một IP → nghĩ host có một IP | Bỏ lỡ A/AAAA candidates | `getAllByName` |
| `getAllByName` trả IPv6 → nghĩ IPv6 connection chắc chắn thành công | Không biết route/firewall/listener | Thử connect được phép với timeout |
| `getLocalHost()` là “IP mạng hiện tại” | Có thể là loopback/hostname mapping | List interfaces và inspect connected socket |
| `getHostName/getCanonicalHostName` gọi trong hot loop | Reverse DNS/blocking overhead | Dùng `getHostAddress` khi chỉ cần literal |
| `createUnresolved` rồi cho rằng Socket sẽ tự resolve | Một số direct APIs không hỗ trợ unresolved | Chọn resolver/transport đúng |
| Dùng interface index/name cố định | Mất khi OS/VPN/container đổi | Khảo sát runtime, cấu hình tường minh |
| `isUp=true` được hiểu là Internet alive | False assurance | Route + application-level test |
| `isVirtual=false` được hiểu là card vật lý | VPN/VM có thể hiển thị khác | Không suy hardware từ boolean |
| `supportsMulticast=true` được hiểu là join/traffic thành công | Network có thể chặn | Kiểm tra membership/routing/firewall |
| In MAC/local IP/tên nội bộ lên public issue | Lộ metadata hạ tầng | Redact mặc định, log có quyền |
| Bind wildcard để “khỏi lỗi” | Có thể mở server cho mọi interface | Bind loopback/allowed IP rõ ràng |
| Quên IPv6 zone `%scope` | Link-local connect fail/nhầm NIC | Giữ đúng scoped address |
| Coi TTL JVM là DNS authoritative TTL | Chẩn đoán cache sai | Kiểm tra security properties + OS resolver cache |
| Dùng `-Dnetworkaddress.cache.ttl=0` rồi tuyên bố đã tắt cache | Sai loại property | Dùng security policy/JDK docs đúng |
| Lấy `isReachable=false` làm host down | ICMP/filtering khác TCP/HTTPS | Probe đúng service được phép |
| Kết nối thẳng IP và tắt TLS hostname verification | Mất security identity | Giữ logical hostname/SNI/verify |
| So sánh OS host với container như một môi trường | Namespace/DNS/route khác | Chạy tools trong **cùng namespace** |
| Thu IP đầu tiên rồi retry vô hạn | Không có bounded timeout/fallback | Address candidates + retry policy phù hợp |
| Quên đóng Socket/ServerSocket | Resource leak | `try-with-resources` |

## 19. Câu hỏi tự kiểm tra

**Câu 1.** `getByName` trả `127.0.0.1`. Điều này có chứng minh `localhost` không có IPv6 không?  
**Đáp án:** Không. Dùng `getAllByName` để quan sát tất cả candidates theo configured resolver.

**Câu 2.** Một hostname có hai A và một AAAA. Java có bắt buộc trả tất cả ba theo đúng thứ tự DNS packet không?  
**Đáp án:** Không. Java/OS resolver có thể cache, sort/filter/prefer family theo config.

**Câu 3.** `InetAddress.getLocalHost()` có liệt kê mọi IP trên Wi-Fi, Ethernet và VPN không?  
**Đáp án:** Không. Nó resolve tên local host thành một `InetAddress`.

**Câu 4.** Một interface `isUp()==true` có chứng minh default route tới Internet hoạt động không?  
**Đáp án:** Không; cần kiểm tra route/firewall và phép thử protocol được phép.

**Câu 5.** `isVirtual()==false` có phải chắc chắn NIC vật lý?  
**Đáp án:** Không. Java flag nói về virtual subinterface; VM/VPN adapters có thể không cùng phân loại.

**Câu 6.** `getInetAddresses()` và `getInterfaceAddresses()` khác gì?  
**Đáp án:** Cái đầu chỉ có IPs; cái sau thêm network prefix/broadcast metadata.

**Câu 7.** `getBroadcast()` có trả một broadcast IPv6 không?  
**Đáp án:** Không, IPv6 không có broadcast theo kiểu IPv4; Java trả null.

**Câu 8.** Địa chỉ `fe80::...` cần gì khi có nhiều NIC?  
**Đáp án:** Cần correct IPv6 scope/zone/interface khi kết nối link-local.

**Câu 9.** `InetSocketAddress.createUnresolved` có gửi DNS query không?  
**Đáp án:** Không tại thời điểm tạo; transport/consumer sau đó quyết định xử lý hostname.

**Câu 10.** `InetAddress.getByAddress(byte[4])` có yêu cầu DNS reverse lookup không?  
**Đáp án:** Không. Nó tạo object từ raw IP bytes có độ dài hợp lệ.

**Câu 11.** `networkaddress.cache.ttl` có thể cấu hình bằng `-D` như một normal system property và chắc chắn có hiệu lực không?  
**Đáp án:** Không. Oracle Java17 mô tả nó là security property.

**Câu 12.** `java.net.preferIPv6Addresses=true` có tự tạo IPv6 route nếu OS không hỗ trợ không?  
**Đáp án:** Không. Nó ảnh hưởng lựa chọn/ưu tiên address candidates trong điều kiện phù hợp, không thay OS networking.

**Câu 13.** Thời gian `getAllByName("localhost")` bằng 1ms có nghĩa mạng DNS round-trip là 1ms không?  
**Đáp án:** Không. Có thể là hosts/JVM/OS cache và có scheduling overhead.

**Câu 14.** `isReachable(false)` có chứng minh HTTP server port 443 down?  
**Đáp án:** Không. Probe và application protocol khác nhau.

**Câu 15.** Socket client kết nối tới `127.0.0.1`, `getLocalAddress()` cho biết gì?  
**Đáp án:** Local source address của **kết nối đó**, không chứng minh source IP khi đi tới một remote site.

**Câu 16.** Máy có 5 interfaces nhưng `NetworkInterfaceSurveyDemo` chạy trong container chỉ thấy 2. Có chắc code sai không?  
**Đáp án:** Không. Container network namespace/permissions có thể khác host.

**Câu 17.** Vì sao không bind sensitive server vào `0.0.0.0` cho tiện test?  
**Đáp án:** Có thể expose listener trên nhiều NIC, khác loopback-only và tăng attack surface.

**Câu 18.** Sau khi `getAllByName` trả IPv4+IPv6, cần thêm gì để biết dịch vụ thực hoạt động?  
**Đáp án:** Bounded connect tới endpoint được phép, route/source evidence, TLS/HTTP/application response tùy protocol.

**Câu 19.** `supportsMulticast()==true` có bảo đảm multicast packet đến?  
**Đáp án:** Không; còn membership, OS, route, IGMP/MLD, firewall và network policy.

**Câu 20.** `getCanonicalHostName` có phải một bằng chứng an toàn để xác thực server?  
**Đáp án:** Không. Reverse name resolution là best effort, không thay TLS/credential identity verification.

## 20. Checklist triển khai sau thí nghiệm

1. Khi báo lỗi DNS, ghi **đúng JVM vendor/version, hostname, namespace và time** trước khi phân tích.
2. Dùng `InetAddress.getAllByName` cho **multi-address khảo sát**, không dùng một `getByName` để suy host chỉ có một IP.
3. Ghi **thứ tự address families** và startup properties `java.net.preferIPv4Stack`/`java.net.preferIPv6Addresses`.
4. Phân biệt **Java positive/negative DNS cache** với OS resolver/DNS authoritative TTL; cấu hình cache như security property.
5. Khảo sát `NetworkInterface` và `InterfaceAddress` để biết NIC flags, IP assignments, prefix, MTU, scoped IPv6.
6. Không xem `isUp`, `supportsMulticast` hoặc `isReachable` là health check cuối cùng.
7. Với link-local IPv6, giữ **scope/zone identifier** và chọn đúng NIC.
8. Với server, bind **địa chỉ cụ thể theo policy**; hạn chế wildcard khi không cần expose.
9. Với client, dùng **bounded connect timeouts**, xét mọi candidate addresses, fallback/racing có giới hạn nếu cần.
10. Giữ TLS SNI, origin hostname và endpoint certificate verification ngay cả khi thử một candidate IP cụ thể.
11. Đối chiếu Java và công cụ OS trong **cùng máy/container/network namespace**; không so khác môi trường rồi quy trách nhiệm cho Java.
12. Không đưa hostnames/IP/MAC nội bộ lên public logs; dùng redaction/safe retention, bật `--show-addresses` chỉ khi cần.
13. Coi mỗi run là **snapshot**, không cache interface index/address vô hạn trong service có VPN/DHCP/hotplug.
14. Kiểm tra lỗi bằng evidence theo tầng: **DNS → address family → route/source → TCP → TLS → application**.
15. Không mở rộng bài khảo sát thành scanning/brute-force; thử loopback hoặc endpoints được phép.
16. Mô tả rõ khi nào stdout phụ thuộc OS/resolver và **không bịa một danh sách NIC/IP “chuẩn” cho mọi người học**.

## Nguồn chính thức

- [Java SE 17 — InetAddress](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InetAddress.html): `getAllByName`, `getByName`, `getLocalHost`, raw address, reverse lookup, caching, reachability methods.
- [Java SE 17 — Inet4Address](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Inet4Address.html): IPv4 address class, special address categories.
- [Java SE 17 — Inet6Address](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Inet6Address.html): IPv6 text format, scope IDs và scoped interfaces.
- [Java SE 17 — InetSocketAddress](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InetSocketAddress.html): `createUnresolved`, resolved vs unresolved socket endpoints.
- [Java SE 17 — NetworkInterface](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/NetworkInterface.html): NIC enumeration, flags, MTU, IP bindings và subinterfaces.
- [Java SE 17 — InterfaceAddress](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InterfaceAddress.html): IP assignment, network prefix và broadcast.
- [Java SE 17 — Socket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html) và [ServerSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html): bind/connect, source/remote IP, timeouts và socket lifecycle.
- [Oracle Java SE 17 — Networking Properties](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/doc-files/net-properties.html): `java.net.preferIPv4Stack`, `java.net.preferIPv6Addresses` và DNS security cache policies.
- [RFC 8305 — Happy Eyeballs Version 2](https://www.rfc-editor.org/rfc/rfc8305.html): ứng dụng dual-stack có thể bố trí connection attempts để tránh trì hoãn do family unreachable.
- [RFC 5952 — IPv6 Text Representation](https://www.rfc-editor.org/rfc/rfc5952.html): khuyến nghị biểu diễn địa chỉ IPv6 dạng text.

**Kết luận:** Một tên có thể ánh xạ tới **nhiều IP**, một máy có thể có **nhiều interfaces với nhiều địa chỉ**, còn **source IP/route của một TCP connection** chỉ có ý nghĩa khi bạn quan sát đúng kết nối tới đích cụ thể. Khảo sát Java DNS và network interfaces theo **từng lớp, từng snapshot**, kiểm tra IPv4/IPv6, cache và IPv6 scope, rồi đối chiếu OS/network evidence trước khi kết luận sự cố mạng.
