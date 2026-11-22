# Ưu tiên IPv4, IPv6 và ảnh hưởng đến chọn địa chỉ

## 1. Mục tiêu của bài học

Khi một chương trình Java kết nối tới hostname như **api.example.com**, máy có thể biết **nhiều địa chỉ IP** cho tên đó: một hoặc nhiều **IPv4** từ bản ghi DNS **A**, cùng một hoặc nhiều **IPv6** từ bản ghi **AAAA**. Chương trình cần quyết định địa chỉ nào được thử trước, loại socket có hỗ trợ họ địa chỉ đó hay không và mạng thật có route tới đó không.

Java cung cấp hai system properties thường gây nhầm lẫn:

- **java.net.preferIPv4Stack**: quyết định việc ưu tiên sử dụng **IPv4-only socket stack** thay cho socket hỗ trợ IPv6/dual-stack.
- **java.net.preferIPv6Addresses**: thay đổi **ưu tiên thứ tự địa chỉ trả về** khi hostname có cả IPv4 và IPv6; có thể chọn **true**, **false** hoặc **system**.

**Hai properties không đồng nghĩa nhau**. Cái thứ nhất tác động tới **khả năng của socket stack**; cái thứ hai chủ yếu tác động tới **thứ tự/ưu tiên kết quả phân giải tên**. Chúng **không cấu hình DNS server**, **không cấp phát địa chỉ cho network interface**, **không sửa firewall** và **không bảo đảm rằng địa chỉ được ưu tiên có thể kết nối thành công**.

### Ba tầng cần phân biệt

~~~text
1. PHÂN GIẢI TÊN
   api.example.com
      |
      +-- A     192.0.2.20       (IPv4)
      +-- AAAA  2001:db8::20     (IPv6)
      |
      v
   InetAddress.getAllByName(host)
   -> danh sách địa chỉ theo chính sách Java / resolver

2. CHỌN ĐÍCH VÀ LOẠI SOCKET
   ứng dụng/API chọn một InetAddress để thử
      |
      +-- Inet4Address
      +-- Inet6Address
      |
   java.net.preferIPv4Stack có thể hạn chế IPv6 socket

3. KẾT NỐI THỰC TẾ
   Socket.connect / HTTP client / TLS client
      |
      +-- OS route, source address, interface, DNS cache
      +-- TCP/UDP, firewall, proxy, server listener
      +-- retry/fallback hoặc racing nếu client hỗ trợ
      |
   Socket.getInetAddress() / getLocalAddress()
   mới cho thấy địa chỉ của kết nối cụ thể
~~~

**Một hostname có AAAA record không đồng nghĩa máy kết nối được IPv6.** Một hệ thống có socket IPv6 cũng không bảo đảm server đang listen trên IPv6. Ngược lại, việc Java ưu tiên IPv4 trước **không có nghĩa IPv6 bị tắt**.

Bài này hướng dẫn cách đọc API Java 17, chọn flags đúng mục tiêu, quan sát kết quả trên thực tế, xử lý dual-stack an toàn và chạy một chương trình Java 17 có cả IPv4/IPv6 loopback.

## 2. Cơ sở: IPv4, IPv6, hostname và địa chỉ

### 2.1. IPv4 và IPv6 là hai address families

| Đặc điểm | IPv4 | IPv6 |
| --- | --- | --- |
| Độ rộng địa chỉ | 32 bit | 128 bit |
| Ví dụ tài liệu | **192.0.2.20** | **2001:db8::20** |
| Loopback | **127.0.0.1** | **::1** |
| Wildcard bind thường thấy | **0.0.0.0** | **::** |
| Java address type | **Inet4Address** | **Inet6Address** |
| DNS record điển hình | **A** | **AAAA** |
| API chung | **InetAddress** | **InetAddress** |

Các địa chỉ **192.0.2.0/24** và **2001:db8::/32** dùng làm ví dụ theo tài liệu chuẩn, không phải lời hứa chúng là server Internet thực sự hoạt động.

Java cung cấp abstraction chung:

~~~java
InetAddress a = InetAddress.getByName("127.0.0.1");
InetAddress b = InetAddress.getByName("::1");

System.out.println(a instanceof Inet4Address); // true
System.out.println(b instanceof Inet6Address); // true
~~~

Hai lệnh này kiểm tra **literal IP**. Chúng không cần hỏi DNS để xác định họ địa chỉ. Đặc biệt, **parse được một literal IPv6 không chứng minh socket IPv6 có thể kết nối**: trong phần test, ngay cả khi JVM được chạy với IPv4-only stack, Java vẫn nhận biết kiểu của chuỗi ::1.

### 2.2. Hostname có thể mang nhiều địa chỉ

Ví dụ hostname **service.example.test** được cấu hình trong name service:

~~~text
service.example.test.  A     192.0.2.20
service.example.test.  AAAA  2001:db8::20
~~~

Kết quả phân giải trong Java:

~~~java
InetAddress[] candidates =
        InetAddress.getAllByName("service.example.test");
for (InetAddress ip : candidates) {
    System.out.println(ip.getHostAddress() + " " +
            ip.getClass().getSimpleName());
}
~~~

Snippet trên cần **service.example.test tồn tại trong môi trường DNS/hosts test thực tế**; đây là tên minh họa, không dùng để yêu cầu một kết quả Internet cố định.

**Đừng đánh đồng danh sách trả về với dữ liệu DNS thô.** InetAddress có thể dùng name service của hệ điều hành, hosts file, cache, name services khác, và các xử lý như DNS64/NAT64 trong môi trường nhất định. Do đó dùng **InetAddress.getAllByName()** để quan sát **những gì Java nhìn thấy**, còn công cụ DNS chỉ giúp kiểm tra nguồn bản ghi.

### 2.3. IPv4-mapped IPv6 và dual-stack

Trên nhiều hệ điều hành, một socket IPv6 có thể giao tiếp với đích IPv4 bằng cơ chế **IPv4-mapped IPv6 addresses** hoặc hỗ trợ dual-stack. Đây là chi tiết của native socket/OS policy; không nên suy ra rằng **mọi** socket bind địa chỉ **::** đều nhận cả IPv4 trong mọi hệ điều hành.

Nếu hệ điều hành đặt **IPV6_V6ONLY** cho một listening IPv6 socket, nó không nhận IPv4 trên cùng socket. Java và OS có thể khác nhau giữa vendor/version/platform. Vì vậy cần **thử kết nối thật** từ IPv4 và IPv6 tới cổng server, không chỉ xem một bind thành công.

## 3. java.net.preferIPv4Stack: chọn stack IPv4-only

Theo **Networking Properties** của Java SE 17:

- Mặc định **java.net.preferIPv4Stack=false**.
- Nếu OS có IPv6, native socket theo mặc định có thể sử dụng IPv6 và trên nhiều hệ thống cho phép ứng dụng liên lạc với cả IPv4 và IPv6.
- Khi đặt **java.net.preferIPv4Stack=true**, JVM ưu tiên **IPv4-only sockets**; ứng dụng không thể liên lạc tới peer chỉ có IPv6 bằng con đường socket IPv6 thông thường.

### Bật bằng JVM startup option

~~~bash
java "-Djava.net.preferIPv4Stack=true" -cp . IpFamilyPreferenceDemo
~~~

**Đây là JVM system property**, không phải environment variable tên preferIPv4Stack. Dùng **-D** khi khởi động tiến trình, **trước tên class**. Dạng đặt dấu ngoặc kép quanh toàn bộ argument -D cũng phù hợp khi chạy trong Windows PowerShell.

**Đừng đặt trong main rồi nghĩ có thể đổi ngay socket stack**:

~~~java
// Không đáng tin để đổi chính sách sau khi JVM đã khởi tạo networking.
System.setProperty("java.net.preferIPv4Stack", "true");
~~~

Javadoc Java 17 nêu hai properties IPv4/IPv6 được **đọc một lần khi JVM khởi động**. Nếu cần so sánh, hãy tạo **những process Java riêng** với flags khác nhau. Không chạy một process rồi đổi System.setProperty và xem các lần gọi InetAddress là những phép thử độc lập.

### IPv4-only làm được và không làm được gì?

| Tình huống | Ảnh hưởng có thể kỳ vọng |
| --- | --- |
| Ứng dụng chỉ kết nối **IPv4-only server** | Có thể hoạt động bình thường |
| Hostname có cả A và AAAA | Kết quả Java có thể chỉ cung cấp địa chỉ IPv4 với stack bị ép IPv4; xác minh trên JDK thực tế |
| Đích chỉ có AAAA và IPv6 | Không có đường kết nối IPv6 bằng stack IPv4-only bình thường |
| Máy OS vẫn hỗ trợ IPv6 | Property không tắt IPv6 cho toàn OS hay mọi chương trình khác |
| Java parse literal **::1** | Vẫn có thể tạo Inet6Address object; **không bảo đảm có thể mở socket IPv6** |
| IPv4 bị firewall chặn, IPv6 tốt | IPv4-only có thể làm tình hình **tệ hơn** |

**Không nên bật preferIPv4Stack=true một cách mặc định chỉ vì một lỗi IPv6 chưa được chẩn đoán**. Nó có thể che một vấn đề routing ngắn hạn nhưng phá kết nối tới IPv6-only endpoints, nhất là trên hạ tầng cloud/network đã chuyển đổi dần sang IPv6.

## 4. java.net.preferIPv6Addresses: thứ tự địa chỉ

Property này được JDK 17 dùng để điều chỉnh thứ tự địa chỉ khi một hostname có **cả IPv4 và IPv6** và hệ điều hành hỗ trợ IPv6.

| Giá trị | Ý nghĩa | Ghi nhớ |
| --- | --- | --- |
| **false** (mặc định) | Ưu tiên IPv4 trước IPv6 khi cả hai có mặt | Lựa chọn tương thích ngược của Java |
| **true** | Ưu tiên IPv6 trước IPv4 nếu có khả năng | **Không phải** ép IPv6-only; IPv4 vẫn có thể được sử dụng |
| **system** | Giữ thứ tự địa chỉ do **system-wide resolver/OS** trả | Không có một thứ tự cố định giống nhau trên mọi OS |
| Không set | Tương đương default policy false khi không có cấu hình khác | Kiểm tra actual JVM flags nếu deploy |

Khởi động các tiến trình thử nghiệm riêng:

~~~bash
# Mặc định: thường ưu tiên IPv4.
java -cp . IpFamilyPreferenceDemo

# Đưa IPv6 lên trước nếu cả hai family khả dụng.
java "-Djava.net.preferIPv6Addresses=true" -cp . IpFamilyPreferenceDemo

# Giữ thứ tự do resolver hệ điều hành cung cấp.
java "-Djava.net.preferIPv6Addresses=system" -cp . IpFamilyPreferenceDemo
~~~

### Tại sao mặc định Java 17 ưu tiên IPv4?

Javadoc giải thích yếu tố **backward compatibility**. Nhiều ứng dụng cũ kỳ vọng **InetAddress.getHostAddress()** là địa chỉ dạng **a.b.c.d** và chỉ có hệ thống mạng IPv4. Việc ưu tiên IPv4 khi cả hai có mặt làm giảm những bất ngờ khi chạy các ứng dụng đó.

Tuy nhiên, một chương trình hiện đại **không nên tự giả định InetAddress là Inet4Address**. Đừng viết các hàm parse IP bằng cách split dấu chấm hay cast:

~~~java
// BAD: địa chỉ có thể là Inet6Address.
Inet4Address ipv4 = (Inet4Address)
        InetAddress.getByName("some-host");

// BETTER: phân nhánh theo family.
InetAddress ip = InetAddress.getByName("some-host");
if (ip instanceof Inet4Address) {
    // Logic IPv4 khi thật sự cần.
} else if (ip instanceof Inet6Address) {
    // Logic IPv6 khi thật sự cần.
}
~~~

Khi ứng dụng không cần thao tác IP-specific, nên dùng **InetAddress** chung và để API mạng xử lý hai family.

### Nếu đặt cả hai cờ?

~~~bash
java "-Djava.net.preferIPv4Stack=true" "-Djava.net.preferIPv6Addresses=true" -cp . IpFamilyPreferenceDemo
~~~

Hai cờ này **không tạo một IPv6 socket hoạt động**. Đặt preferIPv6Addresses=true chỉ yêu cầu ưu tiên IPv6 ở tầng address ordering; preferIPv4Stack=true lại lựa chọn **IPv4-only socket stack**. Khi có xung đột mục đích, **khả năng socket là giới hạn thực**: chương trình không thể đạt IPv6-only endpoint chỉ bằng cách ưu tiên địa chỉ IPv6 trước.

Trong môi trường test Java sử dụng ở bài này, cặp flags trên khiến **localhost** được trả về chỉ với IPv4. Đó là kết quả kiểm thử có thật ở runtime cụ thể; cần đo lại trên bản JDK/vendor/OS triển khai thực tế thay vì suy diễn từ một lần chạy.

### Thứ tự hệ thống là gì?

Ở mode **system**, Java giữ thứ tự kết quả từ resolver hệ điều hành. Resolver OS có thể áp dụng **chính sách source/destination selection** dựa trên IPv6 availability, prefix policy, scope và network configuration (tham chiếu RFC 6724).

**system không có nghĩa luôn IPv6 trước**. Trên laptop dual-stack, thứ tự có thể IPv6 trước; trong container, Windows policy, VPN hoặc máy chỉ hỗ trợ IPv4, kết quả có thể khác. Vì vậy output mẫu của chương trình cần ghi rõ máy/JVM đang dùng.

## 5. InetAddress.getByName và getAllByName ảnh hưởng thế nào?

### 5.1. Phân giải hostname qua các API

~~~java
InetAddress first = InetAddress.getByName("localhost");

InetAddress[] all = InetAddress.getAllByName("localhost");
for (InetAddress a : all) {
    System.out.println(a.getHostAddress());
}
~~~

**getByName(...)** trả về một InetAddress cho hostname; khi nhiều địa chỉ có thể dùng, chính sách sắp xếp của resolver/JVM ảnh hưởng tới địa chỉ được chọn. **getAllByName(...)** trả mảng các địa chỉ được resolver cung cấp cho hostname, đã chịu tác động của chính sách Java/system.

Không dùng **getByName()** để chứng minh một remote service thật sự reachable. Phân giải tên chỉ là bước đầu; TCP handshake còn có thể thất bại vì server không listen, firewall, routing hoặc tình trạng mạng.

### 5.2. Có A và AAAA nhưng không thể dùng cả hai?

Ví dụ:

~~~text
service.example.com
    A    -> 192.0.2.20
    AAAA -> 2001:db8::20

JVM default: IPv4 có thể đứng đầu
JVM preferIPv6Addresses=true: IPv6 có thể đứng đầu
JVM preferIPv6Addresses=system: theo thứ tự OS trả
JVM preferIPv4Stack=true: khả năng dùng IPv6 bị hạn chế
~~~

Nếu server chỉ **listen ở 192.0.2.20:443**, việc ưu tiên IPv6 tới 2001:db8::20 có thể gây timeout hoặc connection refused trước khi một client thử IPv4. Ngược lại, nếu IPv4 route lỗi nhưng IPv6 hoạt động, preferIPv6Addresses=true có thể cải thiện kết quả **cho client chọn/thử theo thứ tự đó**.

Đừng nói “cứ có A và AAAA thì Java luôn thử cả hai” hoặc “đặt true thì Java luôn chọn IPv6”. **Chính API/client implementation mới quyết định cách thử nhiều candidates**.

### 5.3. DNS cache làm các lần test trông giống nhau

**InetAddress** cache cả kết quả phân giải thành công và thất bại. Vì vậy:

- Thay đổi A/AAAA record không nhất thiết được một JVM đang chạy nhìn thấy ngay.
- TTL của Java name-service cache có thể chịu ảnh hưởng từ security properties như **networkaddress.cache.ttl** và **networkaddress.cache.negative.ttl**, các quy tắc của phiên bản JDK và provider.
- DNS TTL trên authoritative server và cache TTL trong JVM/OS có thể không giống nhau.
- Thử với một **JVM mới** có thể hữu ích khi thay đổi flags IPv4/IPv6 vốn là startup-only.

**networkaddress.cache.ttl là security property**, không nên mặc định rằng truyền **-Dnetworkaddress.cache.ttl=0** luôn là cách cấu hình đúng. Xem Javadoc và file **JAVA_HOME/conf/security/java.security** của runtime; quản trị cache theo chính sách hệ thống. Không tắt cache vô điều kiện, vì có thể tăng tải DNS và tạo lỗi mới.

## 6. Thứ tự địa chỉ không đồng nghĩa đường mạng được chọn

Một luồng kết nối phải xét ít nhất bốn quyết định:

~~~text
Hostname
   |
   v
Name service / hosts / DNS A,AAAA
   |
   v
Address ordering (Java property + OS)
   |
   v
Client API chọn địa chỉ để thử
   |
   v
OS chọn source address + route cho destination
   |
   v
Connect success/failure (firewall, listener, NAT, proxy...)
~~~

Cần phân biệt:

1. **Destination family selection**: client thử IPv4 hay IPv6 của server.
2. **Source address selection**: OS chọn địa chỉ nguồn của interface phù hợp với route/đích.
3. **Socket family/capability**: IPv4-only, IPv6-only, dual-stack.
4. **Connection strategy**: thử một địa chỉ, thử lần lượt, hay racing một vài địa chỉ theo thời gian.

System property chỉ tác động **một phần** của pipeline. RFC 6724 mô tả chính sách chọn source/destination cho IPv6 và IPv4-mapped addresses. RFC 8305 mô tả **Happy Eyeballs v2**: cách sắp xếp và thử xen kẽ địa chỉ để giảm độ trễ khi một family không hoạt động.

**Không thể suy ra rằng mọi API Java 17 tự triển khai Happy Eyeballs chỉ từ hai system properties**. Với **Socket** do bạn chủ động tạo, để có fallback có thể phải quản lý danh sách candidates và retries; với một HTTP client/framework, việc retry/racing là chi tiết phiên bản và implementation, cần quan sát.

### Fallback nối tiếp khi tự quản lý Socket (snippet)

~~~java
// Snippet minh họa: không có network access trong bài demo
// nếu không dùng host được phép kiểm thử. 
static Socket connectSequential(String host, int port)
        throws IOException {
    IOException last = null;
    for (InetAddress addr : InetAddress.getAllByName(host)) {
        Socket socket = new Socket();
        try {
            socket.connect(
                    new InetSocketAddress(addr, port), 1500);
            return socket;
        } catch (IOException failure) {
            socket.close();
            last = failure;
        }
    }
    throw last != null ? last :
            new UnknownHostException("No usable address");
}
~~~

**Giải thích:** đoạn code tự thử tuần tự các địa chỉ trả về; không có racing song song kiểu Happy Eyeballs. Nếu mỗi địa chỉ timeout 1,5 giây và hostname có nhiều địa chỉ không reachable, tổng chờ có thể lớn. Trong production, cần **overall deadline**, giới hạn attempts, cancellation, telemetry, retry policy, và xử lý DNS/service discovery phù hợp.

**Với HTTPS/TLS**, việc chọn đích IP **không cho phép bỏ hostname verification**. Certificate server phải đại diện cho **DNS hostname gốc của URL**, dù TCP đang nối tới một IP cụ thể. Đừng kết nối thẳng IP rồi chấp nhận mọi chứng chỉ chỉ để “né DNS”.

### IPv6 preferred nhưng service thực tế dùng IPv4

Các lý do phổ biến:

- DNS chỉ cung cấp A record hoặc name service trả IPv4.
- IPv6 tắt trong container/netns/OS hoặc JVM bị **preferIPv4Stack=true**.
- Proxy xử lý hostname và chọn đích theo policy của **proxy**, không phải thứ tự getAllByName trong app.
- IPv6 firewall, route hoặc listener không hoạt động, client fallback sang IPv4.
- HTTP client tái sử dụng connection cũ đã thiết lập bằng IPv4.
- DNS cache/hosts file lưu kết quả khác với record vừa chỉnh.
- Client dùng **literal IPv4** hoặc đã cấu hình InetSocketAddress cụ thể nên không có bước chọn giữa A/AAAA.

Vì vậy debug phải ghi **actual socket remote address** hoặc proxy route, chứ không chỉ giá trị System.getProperty.

## 7. Bind địa chỉ server: localhost, wildcard và dual-stack

### 7.1. Bind loopback IPv4 khác loopback IPv6

~~~java
ServerSocket ipv4Listener = new ServerSocket(
        8080, 50, InetAddress.getByName("127.0.0.1"));
~~~

Cổng chỉ mở trên IPv4 loopback **127.0.0.1**; đừng mong client kết nối **[::1]:8080** sẽ tự chuyển sang IPv4.

Tương tự:

~~~java
ServerSocket ipv6Listener = new ServerSocket(
        8080, 50, InetAddress.getByName("::1"));
~~~

Listener này chỉ bind IPv6 loopback trong tình huống thông thường, với điều kiện OS và JVM hỗ trợ socket IPv6. Nếu JVM đang **preferIPv4Stack=true**, đừng giả định lệnh bind IPv6 sẽ thành công. Hai snippet minh họa này không nên chạy cùng cổng 8080 trong một môi trường đã có service; chương trình hoàn chỉnh dùng **port 0** để tránh xung đột.

### 7.2. Wildcard binds và IPv6-only policy

| Bind address | Nghĩa cơ bản | Điều còn phải kiểm tra |
| --- | --- | --- |
| **127.0.0.1** | IPv4 loopback | Chỉ client cùng máy dùng IPv4 loopback |
| **::1** | IPv6 loopback | Chỉ client cùng máy dùng IPv6 loopback |
| **0.0.0.0** | Mọi interface IPv4 thuộc namespace | Firewall/ACL/port có cho kết nối không |
| **::** | Mọi interface IPv6 thuộc namespace | OS IPV6_V6ONLY/dual-stack có nhận IPv4 nữa không |
| **Một IPv4/IPv6 interface cụ thể** | Chỉ interface/address được bind | Port, route, DNS và quyền OS |

**Không dùng wildcard bind cho server bài tập khi không cần**, vì có thể vô tình mở dịch vụ tới LAN/Internet. Demo dùng loopback để đảm bảo traffic chỉ ở máy thử nghiệm.

### 7.3. IPv6 link-local cần scope zone

Địa chỉ IPv6 dạng **fe80::...** là **link-local** và thường cần một **scope_id/zone identifier** để chỉ interface, ví dụ dấu **%** sau địa chỉ và tên interface hợp lệ (cụ thể phụ thuộc OS). Java **Inet6Address** hỗ trợ scoped addresses, có thể kiểm tra NetworkInterface.getName() và Inet6Address.getScopedInterface().

Không đơn giản đổi một link-local literal thành địa chỉ public để dùng trên Internet. Với **URI có IPv6 literal**, cần đặt trong dấu ngoặc vuông, ví dụ **http://[::1]:8080/health**. Việc escape dấu phần trăm trong IPv6 zone ID của URL có quy tắc riêng, không tự ghép chuỗi mà nên dùng URI builder/parser phù hợp.

## 8. Chương trình Java 17 hoàn chỉnh: quan sát flags, thứ tự địa chỉ và loopback

**IpFamilyPreferenceDemo.java** không dùng DNS Internet hay host ngoài. Nó:

1. In hai JVM properties tại **startup**.
2. Phân loại literal **127.0.0.1** thành Inet4Address và **::1** thành Inet6Address.
3. Dùng **InetAddress.getAllByName("localhost")** để in **thứ tự địa chỉ thực tế** mà Java nhìn thấy; in getByName("localhost") để so sánh một lựa chọn.
4. Tạo **ServerSocket bind chính xác 127.0.0.1** trên port ngẫu nhiên và **Socket.connect** tới đó; assert cả hai đầu được kết nối.
5. Nếu không bị ép IPv4-only, thử một vòng tương tự trên **::1**; có thể ghi **UNAVAILABLE** khi OS/container không có IPv6 loopback usable.
6. Nếu chạy với **preferIPv4Stack=true**, ghi **NOT_TESTED** cho IPv6 TCP vì JVM được cấu hình IPv4-only; vẫn in literal type IPv6 để minh họa **parse khác khả năng connect**.
7. Đóng tất cả sockets qua try-with-resources, không mở listener public và không gửi thông tin ra Internet.

### Tệp IpFamilyPreferenceDemo.java

~~~java
import java.net.*;
import java.util.*;
import java.io.IOException;

public class IpFamilyPreferenceDemo {
    static String family(InetAddress address) {
        if (address instanceof Inet4Address) return "IPv4";
        if (address instanceof Inet6Address) return "IPv6";
        return "unknown";
    }

    static void require(boolean okay, String detail) {
        if (!okay) throw new AssertionError(detail);
    }

    static void connectToLoopback(InetAddress address)
            throws IOException {
        try (ServerSocket listener =
                    new ServerSocket(0, 1, address);
             Socket client = new Socket()) {
            client.connect(
                    new InetSocketAddress(
                            address, listener.getLocalPort()),
                    2000);
            try (Socket accepted = listener.accept()) {
                require(accepted.isConnected(),
                        "Accepted socket not connected");
                require(client.isConnected(),
                        "Client socket not connected");
                require(family(client.getInetAddress())
                                .equals(family(address)),
                        "Connected to wrong address family");
                require(family(accepted.getLocalAddress())
                                .equals(family(address)),
                        "Listener bound to wrong address family");
            }
        }
    }

    public static void main(String[] args) throws Exception {
        String stack = System.getProperty(
                "java.net.preferIPv4Stack", "(unset)");
        String addresses = System.getProperty(
                "java.net.preferIPv6Addresses", "(unset)");

        System.out.println("preferIPv4Stack=" + stack);
        System.out.println("preferIPv6Addresses=" + addresses);

        InetAddress ipv4 = InetAddress.getByName("127.0.0.1");
        InetAddress ipv6 = InetAddress.getByName("::1");

        require(ipv4 instanceof Inet4Address,
                "IPv4 literal parsed incorrectly");
        require(ipv6 instanceof Inet6Address,
                "IPv6 literal parsed incorrectly");

        System.out.println(
                "IPv4 literal type: " + family(ipv4));
        System.out.println(
                "IPv6 literal type: " + family(ipv6));

        InetAddress[] options =
                InetAddress.getAllByName("localhost");
        require(options.length > 0,
                "localhost not resolved");

        StringJoiner sequence = new StringJoiner(",");
        boolean seenIpv4 = false;
        boolean seenIpv6 = false;

        for (InetAddress address : options) {
            sequence.add(family(address));
            seenIpv4 |= address instanceof Inet4Address;
            seenIpv6 |= address instanceof Inet6Address;
        }

        System.out.println("localhost order: " + sequence);
        System.out.println("localhost has IPv4: " + seenIpv4);
        System.out.println("localhost has IPv6: " + seenIpv6);
        System.out.println("getByName(localhost): " +
                family(InetAddress.getByName("localhost")));

        connectToLoopback(ipv4);
        System.out.println(
                "Explicit IPv4 loopback TCP: PASS");

        if ("true".equalsIgnoreCase(stack)) {
            System.out.println(
                    "Explicit IPv6 loopback TCP: NOT_TESTED " +
                    "(IPv4 stack requested)");
        } else {
            try {
                connectToLoopback(ipv6);
                System.out.println(
                        "Explicit IPv6 loopback TCP: PASS");
            } catch (IOException |
                     UnsupportedOperationException ex) {
                System.out.println(
                        "Explicit IPv6 loopback TCP: UNAVAILABLE");
            }
        }

        System.out.println(
                "Network test used only local loopback");
    }
}
~~~

### Biên dịch

Sử dụng **JDK 17 trở lên**:

~~~bash
javac --release 17 -encoding UTF-8 IpFamilyPreferenceDemo.java
~~~

### Chạy bốn JVM riêng

~~~bash
# 1. Mặc định (không truyền property).
java -cp . IpFamilyPreferenceDemo

# 2. Yêu cầu ưu tiên IPv6 trong kết quả phân giải.
java "-Djava.net.preferIPv6Addresses=true" -cp . IpFamilyPreferenceDemo

# 3. Theo thứ tự resolver của OS.
java "-Djava.net.preferIPv6Addresses=system" -cp . IpFamilyPreferenceDemo

# 4. Ép IPv4-only stack; cùng lúc thử yêu cầu ưu tiên IPv6.
java "-Djava.net.preferIPv4Stack=true" "-Djava.net.preferIPv6Addresses=true" -cp . IpFamilyPreferenceDemo
~~~

**Tại sao tạo bốn tiến trình mới?** Vì hai properties được JDK đọc một lần khi khởi động; dùng nhiều lệnh java bảo đảm không dựa vào System.setProperty thay đổi giữa chừng.

### Đầu ra kiểm thử thực tế trên máy thử nghiệm

Chương trình được biên dịch bằng **javac --release 17** và chạy thành công với **OpenJDK 24.0.2 trên Windows có IPv4 + IPv6 loopback**. Phần dưới ghi đúng các dòng quan sát được; **không phải mẫu stdout bất biến** của mọi OS.

**Lần 1 — Không truyền cờ:**

~~~text
preferIPv4Stack=(unset)
preferIPv6Addresses=(unset)
IPv4 literal type: IPv4
IPv6 literal type: IPv6
localhost order: IPv4,IPv6
localhost has IPv4: true
localhost has IPv6: true
getByName(localhost): IPv4
Explicit IPv4 loopback TCP: PASS
Explicit IPv6 loopback TCP: PASS
Network test used only local loopback
~~~

**Lần 2 — preferIPv6Addresses=true:**

~~~text
preferIPv4Stack=(unset)
preferIPv6Addresses=true
IPv4 literal type: IPv4
IPv6 literal type: IPv6
localhost order: IPv6,IPv4
localhost has IPv4: true
localhost has IPv6: true
getByName(localhost): IPv6
Explicit IPv4 loopback TCP: PASS
Explicit IPv6 loopback TCP: PASS
Network test used only local loopback
~~~

**Lần 3 — preferIPv6Addresses=system:**

~~~text
preferIPv4Stack=(unset)
preferIPv6Addresses=system
IPv4 literal type: IPv4
IPv6 literal type: IPv6
localhost order: IPv6,IPv4
localhost has IPv4: true
localhost has IPv6: true
getByName(localhost): IPv6
Explicit IPv4 loopback TCP: PASS
Explicit IPv6 loopback TCP: PASS
Network test used only local loopback
~~~

**Lần 4 — preferIPv4Stack=true cùng preferIPv6Addresses=true:**

~~~text
preferIPv4Stack=true
preferIPv6Addresses=true
IPv4 literal type: IPv4
IPv6 literal type: IPv6
localhost order: IPv4
localhost has IPv4: true
localhost has IPv6: false
getByName(localhost): IPv4
Explicit IPv4 loopback TCP: PASS
Explicit IPv6 loopback TCP: NOT_TESTED (IPv4 stack requested)
Network test used only local loopback
~~~

### Cách hiểu đúng bốn lần chạy

- Ở lần 1, JVM test ưu tiên **IPv4** cho localhost khi không truyền flags. Socket IPv6 **vẫn hoạt động**, nên **IPv4-first không đồng nghĩa IPv6-disabled**.
- Ở lần 2, localhost có IPv6 đứng đầu và getByName lấy địa chỉ IPv6; cả hai literal loopback vẫn connect được khi chỉ định rõ đích.
- Ở lần 3, resolver của OS trong môi trường thử nghiệm trả **IPv6 trước**. Máy khác có thể trả IPv4 trước hoặc chỉ một family; không sao chép thứ tự này thành quy tắc cố định cho **system**.
- Ở lần 4, dù preferIPv6Addresses=true, JVM được yêu cầu **IPv4-only socket stack**. Test thấy localhost chỉ có IPv4 trong kết quả phân giải, nhưng **InetAddress.getByName("::1") vẫn tạo Inet6Address object**. Chương trình cố ý không kết nối IPv6 khi property đặt IPv4 stack.
- Trong cả bốn lần chạy, **IPv4 explicit TCP** thành công vì test bind listener IPv4 loopback. Điều đó **không chứng minh** máy đi được IPv4 Internet hoặc bất kỳ server ngoài nào.

**Output phụ thuộc môi trường:** trong container chỉ có IPv4, **localhost has IPv6** có thể false, **IPv6 loopback TCP** có thể UNAVAILABLE; với hosts file hoặc resolver khác, thứ tự/khả năng localhost thay đổi. Mục đích test là **quan sát, giải thích và assert các điều kiện thực sự**, không ép môi trường phải có một cấu hình mạng cố định.

### Vì sao demo dùng cả InetAddress và Socket?

**InetAddress** cho thấy lookup/order và family của candidate. **Socket.connect** xác minh khả năng tạo kết nối TCP cụ thể. Cả hai cần thiết: nếu chỉ in InetAddress.getAllByName thì chưa biết server listen hay route đi tới đâu; nếu chỉ connect tới IPv4 literal thì chưa kiểm tra chính sách hostname preferences.

## 9. Ưu tiên địa chỉ có tác động đến HttpClient, TLS và proxy thế nào?

### 9.1. HTTP client với hostname có hai family

Một URL như **https://api.example.com/v1** vẫn dùng **hostname api.example.com**. HTTP client có thể resolve tên, chọn đích IPv4/IPv6, mở TCP, thực hiện TLS handshake rồi gửi HTTP request. Tuy nhiên việc client triển khai **thử địa chỉ nào, thứ tự fallback, connection pooling và retry** phụ thuộc vào API/implementation và phiên bản JDK.

**Không tuyên bố mọi HttpClient trong Java17 áp dụng cùng chiến thuật Happy Eyeballs**; muốn biết thực tế phải quan sát connection, thời gian timeout và logs của đúng runtime.

Nếu dùng **java.net.http.HttpClient**, URLConnection hay Socket, cần kiểm tra khả năng hiện hành của từng stack. Chỉ thay system properties không phải một kế hoạch migration IPv6 hoàn chỉnh.

### 9.2. HTTPS certificate vẫn xác minh hostname

Nếu DNS của **api.example.com** trỏ tới **192.0.2.20** và **2001:db8::20**, việc kết nối TCP tới một trong hai IP **không đổi tên origin**. Với HTTPS, phải xác minh certificate có SAN phù hợp **api.example.com** và đường trust hợp lệ.

Không đổi URL từ hostname sang IPv4 literal hoặc IPv6 literal chỉ để tránh lỗi DNS rồi **tắt hostname verification**. Nếu URL thật sự dùng **https://[2001:db8::20]/**, certificate cần **iPAddress SAN** phù hợp IP đích, không mặc định lấy dNSName SAN khác. Với IPv6 trong URI, nhớ **dấu ngoặc vuông** quanh host literal.

### 9.3. Proxy có thể thay đổi nơi DNS diễn ra

Khi đi qua **HTTP/SOCKS proxy**, Java client có thể thực hiện TCP connection tới địa chỉ **proxy**, còn proxy thực hiện bước chọn đích origin. Vì thế property ưu tiên của **JVM client** có thể chủ yếu ảnh hưởng **địa chỉ của proxy**, không quyết định trực tiếp IPv4/IPv6 tới origin.

Ví dụ HTTP CONNECT có thể yêu cầu proxy tạo tunnel tới **api.example.com:443**; việc proxy resolve hostname, chọn A/AAAA và route là **chính sách của proxy**. Không đọc getAllByName("api.example.com") trong client rồi khẳng định proxy đang dùng candidate đầu tiên.

**Dùng đúng proxy bắt buộc của tổ chức**, không tắt proxy để “sửa IPv6”. Khi chẩn đoán, phân biệt client→proxy và proxy→origin.

### 9.4. Connection pooling và kết quả cũ

Một HTTP client có thể **tái sử dụng TCP/TLS connection** đã tạo trước khi thay đổi DNS record. Trong trường hợp đó, request mới **không cần chọn địa chỉ lại**. Nếu đổi JVM flags, phải **khởi động tiến trình mới**; khi đổi DNS hoặc tuyến mạng, cần xem caching/pooling/lifecycle trước khi kết luận thay đổi không có hiệu quả.

### 9.5. Dual-stack không bảo đảm hiệu năng IPv6 vượt IPv4

IPv6 route có thể tốt hoặc xấu tùy mạng. Một giá trị preferIPv6Addresses=true có thể làm request nhanh hơn trong mạng IPv6 tốt, hoặc chậm hơn trong mạng có IPv6 thông báo nhưng blackhole packet. **Không dùng throughput/latency một lần** để suy ra tất cả IPv6 nhanh hơn IPv4 hoặc ngược lại.

Đo **lookup duration, first connection attempt, actual remote IP, TLS handshake, fallback delay và response time** theo từng family, so sánh trên cùng mạng/host/deadline.

## 10. Quy trình chẩn đoán một lỗi IPv4/IPv6 trong Java

### Bước 1 — Chốt JVM và flags thực sự được khởi động

Ghi lại:

- **java -version**, JDK vendor và runtime.
- **java.net.preferIPv4Stack** có set hay không, giá trị tại startup.
- **java.net.preferIPv6Addresses** false/true/system.
- Container, namespace, OS, VPN/proxy và network policy.
- DNS hostname và port mà ứng dụng thật đang dùng.

**Đừng chỉ tìm trong source code:** flags có thể được truyền từ JVM launcher, service manager, container JAVA_TOOL_OPTIONS hoặc deployment configuration. Ghi lại giá trị có hiệu lực ở tiến trình thực tế.

### Bước 2 — Phân biệt lỗi DNS và lỗi kết nối

| Lỗi hoặc quan sát | Phân tích tiếp |
| --- | --- |
| **UnknownHostException** | Name service/hosts/DNS/cache không trả usable address |
| **InetAddress.getAllByName chỉ có IPv4** | Kiểm tra A/AAAA, IPv4Stack flag, resolver/hosts/OS |
| **getAllByName có IPv6 trước** | Chỉ nói thứ tự candidate, chưa nói socket kết nối |
| **ConnectException: Connection refused** | Có route nhưng endpoint không listen/đang từ chối |
| **SocketTimeoutException trong connect** | Đường mạng, firewall, blackhole, timeout, sai địa chỉ |
| **NoRouteToHostException** | Route hoặc policy OS không cho tới đích |
| **BindException khi bind IPv6** | Socket/OS/port/address không sẵn sàng hoặc cấu hình v6only |
| **SSLHandshakeException sau khi TCP connect** | TLS certificate/hostname/protocol, không đồng nhất với lỗi chọn IP |
| **HTTP 502/504 khi qua proxy** | Phải kiểm tra proxy→origin, không chỉ Java client→proxy |

Một DNS lookup thành công **không bảo đảm TCP connection thành công**; TCP connection thành công cũng **không bảo đảm TLS identity verification đúng**. Phân loại theo lớp để tránh chuyển sang IPv4-only chỉ vì bất kỳ lỗi HTTP/HTTPS nào.

### Bước 3 — Xem Java nhận những địa chỉ gì

Chạy **IpFamilyPreferenceDemo** trên máy hoặc container thực. Nó in **localhost** vì an toàn/offline; khi cần chẩn đoán host thật, một tool tương tự có thể gọi **InetAddress.getAllByName(target)** với hostname được phép và ghi family/order, nhưng **không log dữ liệu nhạy cảm**.

Nếu dùng nslookup, dig, Resolve-DnsName hoặc getent, lưu ý: các lệnh đó có thể dùng **resolver path khác với Java**, hoặc hiển thị bản ghi raw khác thứ tự JVM đã áp dụng. So sánh A/AAAA, local hosts, VPN DNS và Java lookup side by side.

### Bước 4 — Kiểm tra listener và network route

Một service có thể chỉ bind **0.0.0.0** hoặc **127.0.0.1**, trong khi client ưu tiên **::1**. Kiểm tra thực tế port và family được bind; nếu muốn dual-stack, thử hai kết nối riêng đến cả IPv4 và IPv6.

Ở tầng OS có thể kiểm tra route, interface, firewall, policy table, NAT64/DNS64 và IPv6 link-local scope. Đừng chỉ nhìn interface có địa chỉ IPv6 rồi tuyên bố ứng dụng có Internet IPv6.

### Bước 5 — Đo client fallback và proxy

- Ghi remote address/port thật từ Socket hoặc telemetry của HTTP client.
- Nếu qua proxy, xác định Java kết nối proxy bằng IPv4 hay IPv6; kiểm tra proxy chọn origin ra sao.
- Đo connect timeout và tổng deadline. Nếu client thử nhiều IP tuần tự, delay có thể cộng dồn.
- Quan sát connection reuse và cache, thử JVM mới sau thay đổi flags.

### Bước 6 — Sửa đúng nguyên nhân

| Nguyên nhân | Hướng sửa | Không nên |
| --- | --- | --- |
| IPv6 route đứt | Sửa route/firewall/interface, kiểm thử dual-stack | Tắt IPv6 toàn JVM vĩnh viễn không phân tích |
| Hostname AAAA trỏ sai server | Sửa DNS AAAA/traffic routing và TTL | Chỉ ép preferIPv4Stack để che lỗi |
| App cũ chỉ nhận IPv4 literal | Sửa code hỗ trợ Inet6Address | Cast Inet4Address sau getByName |
| Client có fallback chậm | Có deadline, thử candidates hợp lý, client hỗ trợ chiến lược rõ | Treo mỗi IP vô thời hạn |
| Server chỉ listen IPv4 | Bind/listen IPv6 khi service cần, kiểm tra v6only | Nghĩ preferIPv6Addresses sẽ sửa server listener |
| Proxy IPv6 không hỗ trợ | Sửa proxy route/policy | Bỏ proxy bắt buộc |
| TLS certificate SAN sai | Sửa certificate/trust/hostname | Tắt hostname verification |
| Cache DNS lỗi thời | Kiểm tra resolver/cache TTL, restart có quản trị | Tắt cache DNS cho mọi request |
| IPv6-only cluster | Cho phép socket IPv6 và dịch vụ phù hợp | Ép preferIPv4Stack=true |

## 11. Lỗi thường gặp

### Sai 1 — Nhầm ưu tiên với bắt buộc

**preferIPv6Addresses=true** nghĩa là ưu tiên IPv6 **khi có cả hai**; không phải phép kiểm tra bắt buộc địa chỉ đích IPv6 hoặc lệnh vô hiệu IPv4. Nếu cần một kết nối cụ thể tới IPv6, hãy chọn **Inet6Address** hoặc hostname/route được thiết kế phù hợp, rồi xác minh socket thực tế.

### Sai 2 — Nhầm IPv4Stack với IPv4-first

**preferIPv4Stack=true** tác động đến kiểu socket/khả năng IPv6; **preferIPv6Addresses=false** chủ yếu tác động đến thứ tự địa chỉ. Một ứng dụng có **IPv4-first nhưng IPv6 vẫn hoạt động** là hoàn toàn bình thường.

### Sai 3 — Đổi property giữa chừng

System.setProperty(...) trong main không phải cách đáng tin cho hai flags **startup-only**. Mỗi lần đo cấu hình khác nhau hãy chạy **một tiến trình Java mới** với -D đặt trước class name.

### Sai 4 — In địa chỉ đầu tiên rồi khẳng định network đã dùng nó

**getAllByName** cho candidates, không phải log wire traffic. HTTP client có thể chọn địa chỉ khác, thử fallback, reuse connection hoặc đi proxy. Kiểm tra remote/local address của socket thật hoặc telemetry.

### Sai 5 — Coi IPv6 localhost và IPv4 localhost như một

**127.0.0.1 != ::1**. Một listener chỉ bind 127.0.0.1 không chắc chấp nhận ::1. Để test dual-stack, thử mỗi family tường minh và không phụ thuộc vào thứ tự localhost của một OS.

### Sai 6 — Lầm rằng parse IPv6 literal nghĩa là đã bật IPv6

InetAddress.getByName("::1") có thể tạo Inet6Address object ngay cả khi socket IPv6 bị cấm hoặc OS không có IPv6 route. Chỉ **connect thực** mới đánh giá khả năng giao tiếp.

### Sai 7 — Sửa sự cố HTTPS bằng cách nối thẳng IP rồi tắt TLS verification

DNS address family và TLS peer identity là hai lớp riêng. Một địa chỉ IP có thể đi được nhưng certificate không hợp lệ cho origin DNS. Phải giữ xác minh hostname và truststore.

### Sai 8 — Tin cấu hình dual-stack ở server khi chưa test

**:: wildcard bind** có thể phụ thuộc IPV6_V6ONLY. Xác nhận listener cho cả IPv4 và IPv6 bằng hai kết nối độc lập; đừng suy ra chỉ từ dòng cấu hình.

### Sai 9 — Hardcode một family trong code library

Một module mạng dùng chung không nên luôn tạo **Inet4Address**, trừ khi business contract thật sự bắt buộc. Dùng InetAddress, URI và family-neutral API nơi có thể, log/troubleshoot tình huống family-specific khi cần.

### Sai 10 — Dùng IPv4 preference để làm security policy

Một service kiểm tra “chỉ chặn 127.0.0.1” có thể bỏ qua **::1**, IPv4-mapped IPv6, ULA, link-local và cách biểu diễn địa chỉ khác. **Cả IPv4 và IPv6 đều phải được đánh giá** trong allowlist/denylist và SSRF defenses.

## 12. Bảo mật IPv4/IPv6 trong dịch vụ mạng

### 12.1. Không dùng IP version để thay access control

IPv4/IPv6 là cách gắn địa chỉ và truyền gói, **không xác thực người dùng**. Một dịch vụ nội bộ bind **0.0.0.0** hoặc **::** có thể trở nên truy cập được ngoài dự kiến nếu firewall cho phép. Ưu tiên IPv4 hay IPv6 không thay ACL, authentication và TLS.

### 12.2. SSRF có thể lợi dụng cách viết IP khác nhau

Một server nhận URL từ người dùng có thể bị SSRF nếu chỉ blacklist **127.0.0.1** nhưng cho qua **[::1]**, IPv4-mapped addresses, link-local, private ranges, hostname rebinding hoặc IPv6 ULA. Vì vậy kiểm tra URL/destination cần:

1. Parse URI và scheme theo parser chuẩn.
2. Resolve **tất cả candidates** mà application thực sự có thể dùng, không chỉ địa chỉ đầu.
3. Xác định allowed IP ranges cho **cả IPv4 và IPv6**, kể cả mapped/translation scenarios.
4. Áp lại policy sau **redirect** và khi cần sau DNS resolution mới.
5. Kết hợp egress firewall/network policy để giảm tác động nếu logic app sai.
6. Không tắt hostname verification khi dùng HTTPS qua một IP được chọn.

**Thay system preference không phải biện pháp phòng chống SSRF**; attacker có thể khai thác nhiều representations, proxy hoặc DNS changes nếu policy không đầy đủ.

### 12.3. Observability không được lộ dữ liệu

Khi log địa chỉ từ Socket, tránh ghi auth tokens, full URLs có mật khẩu, cookie và session ID. IP addresses cũng có thể là dữ liệu nhạy cảm tùy bối cảnh; giữ đúng thời hạn log và truy cập phù hợp.

### 12.4. Địa chỉ nguồn có thể thay đổi

OS có thể chọn IPv6 source address khác nhau theo interface, scope và privacy address policy. Việc source IP đổi không mặc nhiên chỉ ra user khác, cũng không nên dùng source IP làm phương pháp xác thực duy nhất.

## 13. Checklist triển khai và bài tập

### Checklist khi thay đổi IPv4/IPv6 preference

- Xác nhận **JDK vendor/version** và system properties tại **startup**.
- Phân biệt **preferIPv4Stack** (socket capability) với **preferIPv6Addresses** (address preference).
- Xem A/AAAA, hosts file và **InetAddress.getAllByName** trong đúng môi trường.
- Thử IPv4 và IPv6 listener bằng địa chỉ literal nếu được phép.
- Quan sát remote IP thực, source address, connect duration, error reason.
- Xét OS route, firewall, container namespace, VPN, proxy, NAT64/DNS64.
- Kiểm tra fallback/Happy Eyeballs theo chính client API và phiên bản.
- Kiểm tra DNS cache, TTL và connection reuse trước khi kết luận.
- Giữ TLS certificate/hostname verification và security policy.
- Thử cả môi trường IPv4-only, IPv6-only và dual-stack nếu ứng dụng cần.
- Có timeout, overall deadline và khả năng rollback khi thay đổi JVM flags.
- Không coi một bài test trên localhost là xác nhận Internet route/availability.

### Bài tập A — Thay đổi thứ tự localhost

Chạy demo không cờ, true và system; ghi các mảng địa chỉ. Giải thích vì sao **system** có thể không giống true ở máy khác. Không hardcode expected order trên mọi hệ thống.

### Bài tập B — IPv4Stack và IPv6 loopback

Chạy preferIPv4Stack=true kết hợp preferIPv6Addresses=true. Tại sao literal IPv6 vẫn được parse trong khi kết nối IPv6 không được thử? Phân biệt **address object** với **native socket capability**.

### Bài tập C — Server bind một family

Tạo TCP ServerSocket chỉ bind **127.0.0.1** và thử kết nối bằng **::1** với timeout ngắn. So sánh với listener chỉ bind **::1**. Không dùng một cổng cố định đang được hệ thống khác sử dụng.

### Bài tập D — Hostname có nhiều IP

Trong một môi trường test có DNS/hosts bạn quản lý, đặt A và AAAA cho cùng hostname. Dùng **getAllByName** để ghi thứ tự theo từng JVM startup mode. Xác minh đích nào thật sự reachable và client có fallback hay không.

### Bài tập E — DNS cache

Chỉnh bản ghi trong môi trường cô lập, đo **InetAddress** trong JVM cũ và JVM mới. Xác định role của resolver OS và Java cache policy. Không đổi DNS ngoài quyền quản trị.

### Bài tập F — Proxy versus direct

Đặt một HTTP proxy test được ủy quyền và phân biệt **remote IP của Java→proxy** với **remote IP của proxy→origin**. Vì sao getAllByName(origin) trong Java không nhất thiết là danh sách địa chỉ proxy đã dùng?

### Bài tập G — HTTPS với hostname và literal

Kiểm thử một endpoint HTTPS nội bộ có certificate hợp lệ cho hostname. Sau khi đổi IPv4/IPv6 preference, vẫn phải xác minh hostname. Nếu truy cập bằng IP literal, certificate cần SAN phù hợp; không được dùng trust-all.

### Bài tập H — Dual-stack và nguồn kết nối

Ghi **socket.getInetAddress()** cùng **socket.getLocalAddress()**. Giải thích remote family khác với lựa chọn source IP/interface. Dùng loopback trước khi thử host thật.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** java.net.preferIPv4Stack và java.net.preferIPv6Addresses khác nhau ở đâu?  
**Trả lời:** Cờ thứ nhất lựa chọn IPv4-only socket stack; cờ thứ hai ảnh hưởng thứ tự ưu tiên IPv4/IPv6 khi phân giải hostname có cả hai.

**Câu 2.** Mặc định Java 17 ưu tiên IPv4 hay IPv6 addresses?  
**Trả lời:** Theo Networking Properties Java17, **preferIPv6Addresses=false**, nên ưu tiên IPv4 khi cả hai có mặt nhằm tương thích ngược.

**Câu 3.** preferIPv6Addresses=true có tắt IPv4 không?  
**Trả lời:** Không. Nó ưu tiên IPv6 nhưng IPv4 vẫn có thể được chọn/sử dụng, tùy candidates và client behavior.

**Câu 4.** preferIPv4Stack=true có thể làm IPv6-only host unreachable?  
**Trả lời:** Có. IPv4-only socket stack không thể kết nối với peer chỉ có IPv6 bằng socket IPv6 thông thường.

**Câu 5.** Giá trị system dùng để làm gì?  
**Trả lời:** Giữ thứ tự địa chỉ từ system-wide resolver/OS, không bắt buộc một family cụ thể đứng đầu.

**Câu 6.** Có thể thay giá trị flags bằng System.setProperty sau khi JVM chạy rồi đo lại không?  
**Trả lời:** Không đáng tin; hai cờ được kiểm tra một lần khi startup. Chạy JVM mới với -D.

**Câu 7.** InetAddress.getAllByName trả về kết nối TCP đang hoạt động?  
**Trả lời:** Không; nó trả candidates từ name service. Khả năng connect phải được thử bằng Socket hoặc client phù hợp.

**Câu 8.** Vì sao getByName có thể trả IPv6 đầu tiên nhưng HTTP vẫn dùng IPv4?  
**Trả lời:** Client có thể fallback, dùng proxy, reuse connection cũ hoặc có chiến lược kết nối riêng.

**Câu 9.** Một máy có AAAA DNS record có nghĩa IPv6 Internet hoạt động?  
**Trả lời:** Không. Cần OS interface, route, firewall và server listener tương ứng.

**Câu 10.** Loopback IPv4 và IPv6 có giống nhau?  
**Trả lời:** Không. 127.0.0.1 và ::1 là hai địa chỉ/AF khác nhau.

**Câu 11.** Bind :: trên server có chắc nhận IPv4 không?  
**Trả lời:** Không chắc. Còn tùy dual-stack/IPV6_V6ONLY policy của OS và implementation.

**Câu 12.** Tại sao ::1 vẫn parse thành Inet6Address khi đặt preferIPv4Stack=true trong ví dụ?  
**Trả lời:** Phân tích cú pháp IP literal và khả năng native socket IPv6 là hai việc khác nhau.

**Câu 13.** DNS cache ảnh hưởng như thế nào?  
**Trả lời:** InetAddress có cache positive/negative, nên record thay đổi chưa chắc được JVM cũ nhìn thấy ngay.

**Câu 14.** Có nên dùng -Dnetworkaddress.cache.ttl=0 làm cách chuẩn để vô hiệu cache?  
**Trả lời:** Không mặc định như vậy; đó là security property, phải cấu hình theo tài liệu JDK/security policy và đánh giá hệ quả.

**Câu 15.** Tại sao chọn IPv6 trước có thể tăng latency trong mạng bị blackhole IPv6?  
**Trả lời:** Client có thể chờ timeout một IPv6 address trước khi thử IPv4, tùy cách kết nối; cần deadline/fallback phù hợp.

**Câu 16.** Happy Eyeballs có tự được bảo đảm chỉ nhờ preferIPv6Addresses=true?  
**Trả lời:** Không. Cờ chỉ đổi preference, còn Happy Eyeballs là connection strategy riêng.

**Câu 17.** Khi dùng proxy, ai chọn A/AAAA cho origin?  
**Trả lời:** Có thể là proxy, tùy kiểu proxy/tunnel; Java client có thể chỉ trực tiếp kết nối tới proxy.

**Câu 18.** Khi dùng HTTPS, có được tắt hostname verification để kết nối qua IPv6 literal?  
**Trả lời:** Không. Phải xác minh certificate cho DNS origin hoặc IP SAN phù hợp theo URL thực tế.

**Câu 19.** Vì sao chỉ blacklist 127.0.0.1 không đủ chống SSRF?  
**Trả lời:** Còn ::1, mapped IPv6, ULA, link-local, private IPv4 ranges, redirects và DNS rebinding.

**Câu 20.** Cách kiểm tra family được chọn khi Socket.connect thành công?  
**Trả lời:** Xem Socket.getInetAddress() cho remote, getLocalAddress() cho local và đối chiếu thực tế.

**Câu 21.** Chạy demo thành công trên localhost có chứng minh route tới Internet dual-stack?  
**Trả lời:** Không. Nó chỉ xác minh mạng loopback/cấu hình hiện tại trên máy thử.

**Câu 22.** Vì sao nên so sánh cả getAllByName và socket remote address?  
**Trả lời:** Một cái cho danh sách candidate, một cái cho đích của kết nối thực đã được thiết lập.

## Kết luận

Ưu tiên IPv4/IPv6 trong Java là sự phối hợp của **name resolution, address ordering, socket stack, OS routing và client connection strategy**. Trên Java17, **java.net.preferIPv4Stack=true** làm JVM ưu tiên IPv4-only sockets; **java.net.preferIPv6Addresses=false/true/system** thay đổi thứ tự IPv4/IPv6 khi có cả hai, hoặc giữ thứ tự resolver OS.

Đừng đánh đồng **địa chỉ được ưu tiên** với **địa chỉ chắc chắn kết nối**. Dùng **InetAddress.getAllByName** để xem candidates, **Socket.getInetAddress/getLocalAddress** để xem kết nối cụ thể, và kiểm tra DNS, caching, proxy, firewall, TLS cùng fallback của client. Khi ứng dụng cần dual-stack, ưu tiên thiết kế và quan sát hỗ trợ cả hai family, không ép một cờ để che sự cố hạ tầng.

### Tài liệu tham khảo chính thức

- [Java SE 17 — Networking Properties](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/doc-files/net-properties.html): java.net.preferIPv4Stack, java.net.preferIPv6Addresses và startup-only.
- [Java SE 17 — Java Networking](https://docs.oracle.com/en/java/javase/17/core/java-networking.html): IPv4/IPv6 protocol properties, proxy-related properties.
- [Java SE 17 — InetAddress](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InetAddress.html): getByName, getAllByName, IP literals và name-service caching.
- [Java SE 17 — Inet4Address](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Inet4Address.html): họ IPv4.
- [Java SE 17 — Inet6Address](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Inet6Address.html): IPv6, scope IDs và zone identifiers.
- [Java SE 17 — NetworkInterface](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/NetworkInterface.html): interface addresses và metadata.
- [Java SE 17 — Socket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html): connect timeout và remote/local addresses.
- [Java SE 17 — ServerSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html): bind IP/port và listener.
- [Java SE 17 — InetSocketAddress](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InetSocketAddress.html): địa chỉ endpoint và resolution behavior.
- [RFC 6724 — Default Address Selection for IPv6](https://www.rfc-editor.org/rfc/rfc6724.html): source/destination address selection.
- [RFC 8305 — Happy Eyeballs Version 2](https://www.rfc-editor.org/rfc/rfc8305.html): sắp xếp và thử các candidates để giảm delay.
- [RFC 3986 — URI Syntax](https://www.rfc-editor.org/rfc/rfc3986.html): IPv6 literals trong URI.
