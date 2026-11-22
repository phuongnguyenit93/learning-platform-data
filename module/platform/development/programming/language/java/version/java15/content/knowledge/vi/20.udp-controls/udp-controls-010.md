# Kiểm thử cổng đang dùng, quyền truy cập và địa chỉ không hợp lệ với UDP trong Java 15+

## 1. Mục tiêu: biết **vì sao** một UDP socket không thể bind hoặc gửi

Khi viết UDP server bằng `DatagramSocket` hoặc `DatagramChannel`, không phải lỗi nào cũng là “cổng đang bị chiếm”. Có ít nhất ba nhóm vấn đề cần tách bạch:

1. **Cổng hoặc địa chỉ local đã được sử dụng**: một socket khác đang giữ cùng tổ hợp địa chỉ/cổng và các tùy chọn reuse không cho phép thêm socket.
2. **Quyền truy cập hoặc chính sách vận hành**: hệ điều hành, container, firewall, sandbox, chính sách mạng hay cấu hình tài khoản không cho phép một thao tác. Những nguyên nhân này không có chung một cách phát sinh lỗi trên mọi hệ thống.
3. **Địa chỉ/cổng không hợp lệ**: cổng nằm ngoài phạm vi; địa chỉ đích chưa được phân giải; địa chỉ local không gắn với interface của host; hoặc không phù hợp address family.

Bài học trình bày **cách tạo test có thể lặp lại**, đọc đúng ngoại lệ, kiểm tra trạng thái socket và phân biệt kết quả Java API với những hạn chế OS/network. Ví dụ hoàn chỉnh chỉ trao đổi datagram trên **loopback của máy chạy**, không kết nối tới mạng công cộng.

**Phạm vi phiên bản:** các API chuẩn `java.net.DatagramSocket`, `java.nio.channels.DatagramChannel`, `InetSocketAddress` và ngoại lệ liên quan sử dụng được từ Java 15 và còn được hỗ trợ trong Java hiện hành. Java 15 có JEP 373 thay đổi triển khai UDP trong JDK; **không** có nghĩa mọi loại ngoại lệ hoặc quyền sử dụng cổng là tính năng mới chỉ tồn tại từ Java 15.

## 2. Nhận diện thao tác nào thất bại: `bind`, `send` hay `receive`

Trước hết phải phân biệt:

~~~text
DatagramSocket mới (chưa bind)
      │
      ▼
bind(localAddress, localPort)   ← chọn địa chỉ/cổng TRÊN MÁY NÀY
      │
      ▼
send(packet, remoteAddress)    ← gửi đến IP/cổng ĐÍCH
      │
      ▼
receive(packet)                ← chờ datagram đến trên socket đã bind
~~~

- **`bind`** gắn socket vào địa chỉ/cổng **local**. Bind có thể thất bại nếu cổng đã được giữ, địa chỉ không thuộc máy hoặc quyền OS không cho phép.
- **`send`** dùng địa chỉ/cổng **remote**. Gửi không thành công không tự chứng minh cổng local đang bận; có thể do địa chỉ đích chưa phân giải, gói quá lớn, lỗi route, policy hoặc lỗi I/O.
- **`receive`** chờ dữ liệu. Không có gói trong khoảng timeout, firewall chặn gói, hoặc ứng dụng phía kia không gửi là tình huống khác với bind lỗi.

Đặc biệt, UDP **không** tự xác nhận phía nhận đã nhận gói: `send(...)` trả thành công **không** có nghĩa remote port có process đang lắng nghe hoặc firewall đã cho phép gói tới đích.

### 2.1. “Cổng 0” là hợp lệ khi bind

~~~java
InetAddress local = InetAddress.getLoopbackAddress();

try (DatagramSocket socket = new DatagramSocket(null)) {
    socket.bind(new InetSocketAddress(local, 0));
    System.out.println(socket.getLocalPort() > 0); // true khi bind thành công
}
~~~

Đây là đoạn mã minh họa trong ngữ cảnh đã import `java.net.*` hoặc các lớp tương ứng; `new DatagramSocket(null)` tạo socket **chưa bind** và `new InetSocketAddress(local, 0)` yêu cầu OS chọn cổng ephemeral. **Đừng coi số 0 ở đây là cổng 0 sẽ được gửi tới remote**. Sau bind, `getLocalPort()` trả cổng thật (thường là số dương).

Dùng cổng 0 làm bài test giúp tránh xung đột với service khác, đồng thời không đòi quyền để lấy một cổng cố định.

### 2.2. “Địa chỉ 0.0.0.0” khác “127.0.0.1”

- `0.0.0.0` là **wildcard IPv4** khi bind: thường biểu thị tất cả interface IPv4 của host. Nó không phải địa chỉ remote tùy ý để kết nối.
- `127.0.0.1` là **IPv4 loopback**. `InetAddress.getLoopbackAddress()` cho địa chỉ loopback khả dụng trong môi trường JVM.
- Bind vào một IP **không được gán cho interface local** có thể bị OS từ chối ngay cả khi cổng chưa ai dùng.
- Một socket bind wildcard có thể xung đột với socket bind vào một IP cụ thể trên cùng cổng. Kết quả còn phụ thuộc IPv4/IPv6, dual-stack và các option reuse.

Vì vậy, báo “port in use” nên gắn với **address family + local IP + port + reuse policy**, không chỉ một con số port.

## 3. Kiểm thử cổng đang dùng mà không cần đoán PID

### 3.1. Cách thử có kiểm soát với hai socket

Quy trình thực hành:

1. Tạo socket A chưa bind bằng `new DatagramSocket(null)`.
2. Đặt `SO_REUSEADDR=false` trên A **trước bind** để tránh chủ ý chia sẻ cổng.
3. Bind A vào loopback và **port 0** để OS cấp cổng còn trống.
4. Giữ A **chưa đóng**, lấy cổng thật bằng `getLocalPort()`.
5. Tạo socket B cũng đặt `SO_REUSEADDR=false`; thử bind B vào **cùng loopback + cổng** với A.
6. Ghi nhận `SocketException`, thường là `BindException`, từ B nếu OS từ chối bind trùng.

~~~java
InetAddress loopback = InetAddress.getLoopbackAddress();

try (DatagramSocket first = new DatagramSocket(null);
     DatagramSocket second = new DatagramSocket(null)) {
    first.setReuseAddress(false);
    second.setReuseAddress(false);

    first.bind(new InetSocketAddress(loopback, 0));
    int occupiedPort = first.getLocalPort();

    try {
        second.bind(new InetSocketAddress(loopback, occupiedPort));
        System.out.println("Host cho phép bind thứ hai theo chính sách hiện tại");
    } catch (SocketException expected) {
        System.out.println("Bind thứ hai bị từ chối: " +
                expected.getClass().getSimpleName());
    }
}
~~~

Đoạn trên là mã minh họa (cần `import java.net.*;` và đặt trong phương thức có `throws Exception`). Trên JDK 24 và môi trường thử của bài, socket B bị từ chối. **Không bắt buộc phải hiện cùng chuỗi thông báo trên Windows/Linux/macOS**. `BindException` là lớp con của `SocketException`, còn thông điệp lỗi do OS/JDK có thể khác.

**Không chạy hai tiến trình sử dụng một cổng cố định tùy ý rồi nhận kết quả làm test hoàn toàn quyết định**: cổng có thể đã được sử dụng từ trước, và cấu hình reuse/interface khác nhau có thể thay đổi kết luận. Chiến lược A bind port 0, B thử đúng cổng của A làm bài test sạch hơn.

### 3.2. Cũng có lỗi “bind lại cùng một socket”

~~~java
try (DatagramSocket udp = new DatagramSocket(null)) {
    udp.bind(new InetSocketAddress(
            InetAddress.getLoopbackAddress(), 0));

    // udp.bind(...) lần thứ hai sẽ gây SocketException.
}
~~~

Đây là **lỗi trạng thái**: socket này đã bind rồi. Không nên giải thích thành “một process lạ đang chiếm cổng”. Trạng thái `udp.isBound()` giúp phân biệt.

### 3.3. Với `DatagramChannel`: `AlreadyBoundException` có ý nghĩa riêng

~~~java
try (DatagramChannel channel = DatagramChannel.open()) {
    channel.bind(new InetSocketAddress(
            InetAddress.getLoopbackAddress(), 0));
    channel.bind(new InetSocketAddress(
            InetAddress.getLoopbackAddress(), 0)); // AlreadyBoundException
}
~~~

Đây là mã minh họa có các import tương ứng. `AlreadyBoundException` thuộc `java.nio.channels` và là **unchecked exception** khi bind lại **chính channel đã bind**. Nếu một **channel khác** bị OS từ chối vì cổng đang bị socket khác giữ, thường là lỗi I/O như `BindException`. Hai tình huống nên được ghi nhận khác nhau.

## 4. Các ngoại lệ cần biết và cách diễn giải

| Lỗi Java | Thao tác có thể gặp | Điều có thể suy ra | Không nên vội kết luận |
| --- | --- | --- | --- |
| `BindException` | `DatagramSocket.bind`, `DatagramChannel.bind` | OS không thực hiện được bind địa chỉ/cổng | Không phải lúc nào cũng chỉ do “cổng bận”; có thể liên quan địa chỉ không hợp lệ/khác |
| `SocketException` | Datagram socket mở/bind/send/receive | Lỗi socket hoặc bind; bao gồm một số lỗi OS | Không đủ để kết luận chính xác permission hay port conflict |
| `AlreadyBoundException` | Bind lần nữa trên cùng `DatagramChannel` | Chính channel này đã bind | Không nhất thiết có tiến trình khác giữ cổng |
| `IllegalArgumentException` | Tạo `InetSocketAddress` với port ngoài `0..65535` | Input port không hợp lệ | Không phải lỗi mạng hay thiếu quyền |
| `UnknownHostException` | Phân giải hostname hoặc tạo `InetAddress` từ bytes sai độ dài | Không lấy được `InetAddress` hợp lệ | Không đồng nghĩa OS từ chối bind một IP local hợp lệ |
| `UnresolvedAddressException` | Một số API NIO như `DatagramChannel.send/connect` | `InetSocketAddress` cho đích chưa phân giải | Không phải bằng chứng remote port đóng |
| `UnsupportedAddressTypeException` | Một số thao tác NIO với `SocketAddress`/family không hỗ trợ | Sai kiểu địa chỉ cho channel | Không phải lỗi thiếu quyền truy cập cổng |
| `ClosedChannelException` | Dùng channel sau đóng | Channel đã đóng | Không liên quan việc cổng có process khác hay không |
| `SocketTimeoutException` | `DatagramSocket.receive` khi bật timeout | Không nhận datagram kịp thời | Không chứng minh thiếu quyền bind hay port remote đóng |
| `PortUnreachableException` | Một số thao tác trên UDP đã “connected” | Có thể nhận thông báo ICMP destination/port unreachable | Java **không bảo đảm** hệ điều hành sẽ báo lỗi này |

**Chú ý:** API `DatagramSocket.bind(SocketAddress)` công khai `SocketException` (và `IllegalArgumentException` cho loại SocketAddress không phù hợp); `DatagramChannel.bind` có hợp đồng về `AlreadyBoundException`, `ClosedChannelException` và `IOException`. Chọn `catch` theo đúng API đang gọi, không bê nguyên nhánh exception của NIO sang DatagramSocket.

Không xây logic nghiệp vụ bằng cách so sánh nguyên văn `exception.getMessage()` với chuỗi tiếng Anh `"Address already in use"`: thông báo thay đổi theo OS, locale, implementation và kiểu lỗi. Log exception type, địa chỉ/cổng đang thử, action `bind/send/receive`, phiên bản/cấu hình runtime và những thông tin không nhạy cảm để chẩn đoán.

## 5. Địa chỉ và cổng không hợp lệ: tạo test hoàn toàn xác định

### 5.1. Cổng hợp lệ là `0..65535` trong `InetSocketAddress`

~~~java
InetAddress loopback = InetAddress.getLoopbackAddress();

new InetSocketAddress(loopback, 0);      // Hợp lệ để bind, auto port
new InetSocketAddress(loopback, 65535);  // Hợp lệ về mặt phạm vi

try {
    new InetSocketAddress(loopback, 65536);
} catch (IllegalArgumentException expected) {
    System.out.println("outside range");
}
~~~

Đoạn này **không thử bind cổng 65535**; chỉ kiểm tra việc tạo địa chỉ. Cổng 1..65535 hợp lệ về mặt kiểu **không** đồng nghĩa ứng dụng có quyền bind cổng đó hoặc port chưa ai dùng.

Cổng âm, chẳng hạn `-1`, cũng bị constructor từ chối bằng `IllegalArgumentException`. Nên validate cấu hình đầu vào trước khi tạo socket và báo lỗi cấu hình rõ ràng thay vì thử nhiều lần bind một cổng không thể hợp lệ.

### 5.2. Một `InetSocketAddress` có thể “unresolved”

~~~java
InetSocketAddress target =
        InetSocketAddress.createUnresolved("never-resolved.invalid", 9999);

System.out.println(target.isUnresolved()); // true
~~~

`createUnresolved(...)` **cố ý không phân giải DNS**. Vì vậy `isUnresolved()` trả `true` độc lập với kết quả mạng. Nó phù hợp để tạo test cho tình huống **chưa có địa chỉ IP**, thay vì cố gọi hostname thật rồi trông đợi DNS thất bại trong mọi môi trường.

Với `DatagramChannel.send(ByteBuffer, SocketAddress)`, đưa một `InetSocketAddress` chưa phân giải vào sẽ phát sinh `UnresolvedAddressException`:

~~~java
try (DatagramChannel channel = DatagramChannel.open()) {
    InetSocketAddress unresolved =
            InetSocketAddress.createUnresolved("never-resolved.invalid", 9999);
    try {
        channel.send(ByteBuffer.wrap(new byte[]{1}), unresolved);
    } catch (UnresolvedAddressException expected) {
        System.out.println("Đích chưa phân giải");
    }
}
~~~

Đây là **test API**, không gửi gói ra Internet: địa chỉ đã được tạo ở trạng thái unresolved. Mã sử dụng `ByteBuffer` và `DatagramChannel`/`UnresolvedAddressException` từ NIO.

**Đừng dùng `String` hostname chưa phân giải như bằng chứng port đang bận**: đây là lỗi đầu vào địa chỉ đích, không phải `BindException` của cổng local.

### 5.3. Độ dài bytes IP sai

~~~java
try {
    InetAddress.getByAddress(new byte[]{127, 0, 0});
} catch (UnknownHostException expected) {
    System.out.println("byte IP không hợp lệ");
}
~~~

Ba byte không tạo được địa chỉ IPv4 4 byte hoặc IPv6 16 byte. `UnknownHostException` ở đây phát sinh **không phải do DNS**. Đây là bài test đơn vị ổn định cho điều kiện dữ liệu địa chỉ không hợp lệ ở mức API.

Lưu ý: chuỗi văn bản sai dạng IP, hostname không tồn tại và một địa chỉ local không được gán cho interface là **ba tình huống khác nhau**. Chúng không nhất thiết phát sinh cùng exception.

### 5.4. Địa chỉ local không thuộc host

Giả sử một máy chỉ có loopback, nhưng app cố:

~~~java
// Chỉ minh họa; KHÔNG chạy như một kiểm thử xác định trên mọi host.
InetAddress requested = InetAddress.getByName("203.0.113.77");
try (DatagramSocket socket = new DatagramSocket(null)) {
    socket.bind(new InetSocketAddress(requested, 12345));
}
~~~

`203.0.113.0/24` là không gian địa chỉ dùng cho tài liệu (TEST-NET-3). Trên máy bình thường không có địa chỉ này, bind thường bị từ chối bằng `SocketException`/`BindException` do OS. **Đây vẫn là điều kiện phụ thuộc cấu hình host**: một host có thể có route/địa chỉ/bind-nonlocal policy đặc biệt, nên không ghi stdout cố định cho tình huống này.

Trong production, cần so sánh **local bind IP** với địa chỉ thực sự được cấu hình trên interface qua các API `NetworkInterface` hoặc cấu hình triển khai đáng tin, và lưu ý rằng một số môi trường hỗ trợ bind address phi local có chủ đích. Việc **bind** một địa chỉ không tự động kiểm tra khả năng nhận gói từ mạng ngoài.

### 5.5. IPv4, IPv6 và address family

`127.0.0.1` là IPv4 loopback; `::1` là IPv6 loopback. Nếu mở `DatagramChannel.open(StandardProtocolFamily.INET)` cho IPv4 nhưng cấu hình địa chỉ IPv6, hoặc dùng loại `SocketAddress` không phù hợp, thao tác có thể thất bại. Cách chính xác và portable:

- Xác định rõ giao thức IPv4/IPv6 cần dùng.
- Đối với NIO, chọn `StandardProtocolFamily.INET` hoặc `INET6` theo hợp đồng.
- Kiểm tra địa chỉ local/remote đúng family và khả dụng trong container/host.
- Thử trên JDK/OS thực tế, không coi hành vi dual-stack của mọi máy là giống nhau.

Đừng suy luận từ một IPv6 literal hợp lệ rằng interface và kernel đã bật IPv6 hoặc nó có thể bind trên mọi node triển khai.

## 6. Quyền truy cập khi bind UDP: test thế nào cho đáng tin?

**Thiếu quyền** là chủ đề khác với **cổng đang dùng** hoặc **địa chỉ sai**. Quyền bind phụ thuộc:

- Hệ điều hành và cấu hình kernel.
- User/UID, container user và capability.
- Sandbox, MAC policy như AppArmor/SELinux, network namespace.
- Chính sách firewall hoặc security group (chủ yếu ảnh hưởng luồng gói, **không nhất thiết chặn bind**).
- Việc một process khác đang giữ cổng, cũng có thể cho ra thông báo hệ điều hành dễ bị nhầm với lỗi quyền.

### 6.1. Port “đặc quyền” là quy tắc của OS, không phải của JCA

Trên nhiều cấu hình Unix/Linux, bind cổng thấp (truyền thống là **dưới 1024**) yêu cầu quyền/capability thích hợp, chẳng hạn `CAP_NET_BIND_SERVICE` trên Linux. Nhưng đây **không phải định luật chung của Java**:

- Linux có thể cấu hình ngưỡng cổng không đặc quyền bằng `net.ipv4.ip_unprivileged_port_start`.
- Container có thể được cấp capability đặc biệt hoặc chạy trong network namespace khác.
- Windows và các OS khác có quy tắc quyền/cổng khác nhau.
- Một cổng thấp có thể thất bại do **đang được sử dụng**, không phải do thiếu quyền.

Do đó, **không viết test bắt buộc rằng bind cổng 80 phải thất bại trên mọi máy**. Để kiểm tra quyền, phải tạo **môi trường có kiểm soát** (user không đặc quyền, OS policy đã biết, cổng xác định chưa bị chiếm, địa chỉ local hợp lệ), rồi so sánh kết quả trước/sau thay đổi policy hoặc chạy bằng account được cấp phép.

### 6.2. Test permission có kiểm soát

Quy trình gợi ý trong một container/VM thử nghiệm:

1. Chọn port và IP **local** được phép dùng cho test; xác nhận không có process khác dùng port đó. Không thử trên service production đang chạy.
2. Ghi nhận user/UID, quyền/capability, network namespace và policy bind hiện tại.
3. Chạy cùng một chương trình probe với **user hoặc policy không được phép**, ghi lại kết quả `bind` và lỗi OS.
4. Chạy lại với một policy **được cấp quyền có chủ đích** trong môi trường thử.
5. Xác minh lý do là **policy permission** qua log/errno/cấu hình OS, không chỉ từ chuỗi `SocketException.getMessage()`.
6. Sau test, dừng tiến trình, đóng socket và hoàn nguyên thay đổi quyền/capability.

**Quan trọng:** đừng “chữa” lỗi thiếu quyền bằng cách chạy cả ứng dụng với quyền admin/root nếu kiến trúc không yêu cầu. Nên dùng cấu hình cổng không đặc quyền, proxy/reverse proxy, cơ chế cấp capability tối thiểu hoặc chính sách triển khai phù hợp. Với UDP, reverse proxy TCP/HTTP thông thường không tự nhiên chuyển tiếp UDP; cần lớp giao thức/UDP proxy phù hợp.

### 6.3. Security Manager không phải cách test quyền UDP hiện đại

Một số tài liệu Java cũ mô tả `java.lang.SecurityManager` và `SocketPermission` để cho phép hoặc cấm network operation trong JVM. **Không nên dùng cách này cho bài học hiện đại**: JDK 24 đã **vô hiệu hóa vĩnh viễn Security Manager** (JEP 486), sau quá trình deprecation từ các bản trước. Cách gọi `System.setSecurityManager(...)` **không còn là giải pháp quản trị quyền UDP cho Java hiện hành**.

Thay vào đó, kiểm thử bằng **OS/container network policy**, user/capabilities, firewall và cấu hình ứng dụng. Khi cần quyền ở tầng nghiệp vụ (client được gửi packet nào, dùng endpoint nào), hãy tự triển khai authentication/authorization ở đúng giao thức, **không** coi thành công của `bind` là chứng cứ client đã được phép.

### 6.4. Firewall và inbound UDP khác lỗi bind

Một UDP server có thể:

~~~text
bind=SUCCESS
send=SUCCESS
receive=TIMEOUT
~~~

Nguyên nhân có thể là không có ai gửi, firewall chặn inbound, NAT/routing, packet bị mất, ứng dụng gửi nhầm IP/family/port, hoặc lỗi protocol. **Không** suy ra `bind` không đủ quyền nếu thực tế bind đã thành công.

Ngược lại, việc bind vào `0.0.0.0` thành công không bảo đảm host được phép nhận lưu lượng từ bên ngoài. Cần kiểm tra ở tầng network: listener địa chỉ nào, policy inbound, container port mapping, route, source/destination, packet counters và thử gửi có kiểm soát từ máy phù hợp.

`PortUnreachableException` đối với datagram đã connected không được JVM bảo đảm luôn phát sinh khi đích không có listener. Vì vậy **không dùng sự vắng mặt của exception này** làm bằng chứng remote port có dịch vụ.

## 7. Mã probe quyền và cổng: không gán nguyên nhân từ một exception

Một probe ngắn (có trong chương trình ở mục 9) nhận **một cổng từ dòng lệnh**, rồi thử bind **loopback**:

~~~java
static void probeLoopbackPort(String userPort) {
    try {
        int port = Integer.parseInt(userPort);
        try (DatagramSocket probe = new DatagramSocket(null)) {
            probe.setReuseAddress(false);
            probe.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), port));
            System.out.println("manualProbe=BOUND");
        }
    } catch (IllegalArgumentException invalidInput) {
        System.out.println("manualProbe=INVALID_PORT");
    } catch (SocketException socketFailure) {
        System.out.println("manualProbe=SOCKET_ERROR");
    }
}
~~~

Đây là **một method hoàn chỉnh nhưng cần đặt trong class**, với `import java.net.*;`.

- `manualProbe=BOUND`: có thể bind local socket theo cấu hình hiện tại. **Không** chứng minh gói từ bên ngoài đến được host.
- `manualProbe=INVALID_PORT`: input không parse thành số hợp lệ hoặc nằm ngoài phạm vi `0..65535`.
- `manualProbe=SOCKET_ERROR`: socket bị OS/JDK từ chối vì một lỗi socket. **Không đủ dữ kiện** để kết luận port busy, permission denied hay local address sai; cần đối chiếu exception/log OS và điều kiện test.

Probe chỉ bind vào **loopback**. Với trường hợp permission theo một interface cụ thể, phải có test riêng với IP/interface **đã được xác nhận** và policy tương ứng.

**Không in raw exception message theo yêu cầu kiểm thử cố định**: kết quả `getMessage()` khác nhau giữa nền tảng. Với log vận hành thật, có thể ghi thông điệp đã được lọc thông tin nhạy cảm cùng tên exception và địa chỉ/cổng.

## 8. Hai cách đọc trạng thái socket để chẩn đoán

### 8.1. Ở Java: `isBound`, `getLocalAddress` và `getLocalPort`

~~~java
try (DatagramSocket socket = new DatagramSocket(null)) {
    System.out.println(socket.isBound());    // false

    socket.bind(new InetSocketAddress(
            InetAddress.getLoopbackAddress(), 0));

    System.out.println(socket.isBound());    // true
    System.out.println(socket.getLocalPort() > 0); // true
}
~~~

`isBound()` là thông tin **từng socket**, không phải danh sách tiến trình đang giữ các port trên máy. `getLocalPort()` trả cổng thật sau bind, nhưng sau khi socket đã đóng có thể trả `-1`. Đừng xây health check dựa vào những giá trị sau `close()` mà không hiểu hợp đồng API.

### 8.2. Ở NIO: `DatagramChannel.getLocalAddress()`

~~~java
try (DatagramChannel channel = DatagramChannel.open()) {
    System.out.println(channel.getLocalAddress() == null); // true trước bind
    channel.bind(new InetSocketAddress(
            InetAddress.getLoopbackAddress(), 0));
    System.out.println(channel.getLocalAddress() != null); // true
}
~~~

Đây là trạng thái của channel tương ứng. Với `NetworkChannel.bind(null)`, hệ thống có thể tự gán địa chỉ/cổng. Nếu gọi `bind` **hai lần** trên cùng channel, `AlreadyBoundException` là trường hợp riêng, không phải lỗi DNS hay firewall.

### 8.3. Ở hệ điều hành: tra cổng đang được dùng

Các lệnh chẩn đoán dưới đây **chỉ đọc trạng thái**; dùng trong môi trường bạn được phép quản trị. Đối chiếu theo **cùng network namespace/host/container** với chương trình Java.

**Windows PowerShell:**

~~~powershell
Get-NetUDPEndpoint -LocalPort 12345
~~~

Hoặc:

~~~powershell
netstat -ano -p udp
~~~

**Linux:**

~~~bash
ss -lunp
~~~

Một số lệnh có thể cần quyền phù hợp để hiển thị đầy đủ PID/process. **Không tìm thấy một port trong output** không chắc chắn nghĩa là nó “luôn trống”: process có thể vừa bind/close, chạy trong namespace khác, hoặc output không đủ quyền truy cập. Tránh kill process chỉ vì tên cổng trùng; kiểm tra process/owner theo quy trình vận hành.

Đặc biệt, UDP không có trạng thái `LISTEN`/`ESTABLISHED` giống TCP. Công cụ có thể hiển thị dạng `UNCONN` hoặc cột khác; **đừng áp logic TCP port-scan nguyên xi sang UDP**.

## 9. Chương trình Java 15+/17+ hoàn chỉnh, test offline

Chương trình **`UdpBindDiagnosticsDemo.java`** thực hiện tất cả kiểm thử ổn định sau:

- Từ chối cổng `65536` và `-1` bằng `IllegalArgumentException`.
- Từ chối mảng IP ba byte bằng `UnknownHostException`.
- Tạo `InetSocketAddress` chưa phân giải bằng `createUnresolved`, kiểm tra NIO `UnresolvedAddressException`.
- Giữ một UDP socket trên loopback với **port ephemeral**, thử bind lại cùng socket và thử socket thứ hai bind vào cùng cổng khi reuse bị tắt.
- Gửi/nhận một datagram UTF-8 **trên loopback**, đặt timeout để test không chờ vô hạn.
- Bind lại cùng `DatagramChannel` để kiểm tra `AlreadyBoundException`.
- Có một probe CLI **tùy chọn** nhận cổng nhằm kiểm tra thủ công trong môi trường có kiểm soát.

**Không** thử ép lỗi permission trong lần chạy mặc định: quyền OS không thể được mô phỏng một cách di động bằng Java standard API hiện hành. Những bài test permission phải chạy trong một môi trường được cấu hình riêng theo mục 6.

~~~java
import java.net.*;
import java.nio.ByteBuffer;
import java.nio.channels.AlreadyBoundException;
import java.nio.channels.DatagramChannel;
import java.nio.channels.UnresolvedAddressException;
import java.nio.charset.StandardCharsets;

public class UdpBindDiagnosticsDemo {
    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();

        boolean highPortRejected = false;
        try {
            new InetSocketAddress(loopback, 65_536);
        } catch (IllegalArgumentException expected) {
            highPortRejected = true;
        }
        boolean negativePortRejected = false;
        try {
            new InetSocketAddress(loopback, -1);
        } catch (IllegalArgumentException expected) {
            negativePortRejected = true;
        }
        boolean badAddressBytesRejected = false;
        try {
            InetAddress.getByAddress(new byte[]{127, 0, 0});
        } catch (UnknownHostException expected) {
            badAddressBytesRejected = true;
        }
        System.out.println("highPortRejected=" + highPortRejected);
        System.out.println("negativePortRejected=" + negativePortRejected);
        System.out.println("badAddressBytesRejected=" + badAddressBytesRejected);

        InetSocketAddress unresolved =
                InetSocketAddress.createUnresolved("never-resolved.invalid", 9999);
        boolean unresolvedFlag = unresolved.isUnresolved();
        boolean channelUnresolvedRejected = false;
        try (DatagramChannel channel = DatagramChannel.open()) {
            try {
                channel.send(ByteBuffer.wrap(new byte[]{1}), unresolved);
            } catch (UnresolvedAddressException expected) {
                channelUnresolvedRejected = true;
            }
        }
        System.out.println("unresolvedFlag=" + unresolvedFlag);
        System.out.println("channelUnresolvedRejected=" + channelUnresolvedRejected);

        boolean sameSocketSecondBindRejected = false;
        boolean usedPortRejected = false;
        boolean udpLoopback = false;
        boolean receiverBound = false;
        try (DatagramSocket receiver = new DatagramSocket(null);
             DatagramSocket competitor = new DatagramSocket(null);
             DatagramSocket sender = new DatagramSocket(null)) {
            receiver.setReuseAddress(false);
            competitor.setReuseAddress(false);
            receiver.bind(new InetSocketAddress(loopback, 0));
            receiverBound = receiver.isBound() && receiver.getLocalPort() > 0;
            InetSocketAddress occupied =
                    new InetSocketAddress(loopback, receiver.getLocalPort());

            try {
                receiver.bind(new InetSocketAddress(loopback, 0));
            } catch (SocketException expected) {
                sameSocketSecondBindRejected = true;
            }
            try {
                competitor.bind(occupied);
            } catch (SocketException expected) {
                usedPortRejected = true;
            }
            sender.bind(new InetSocketAddress(loopback, 0));
            receiver.setSoTimeout(2000);
            byte[] outgoing = "UDP an toàn 🌱".getBytes(StandardCharsets.UTF_8);
            sender.send(new DatagramPacket(outgoing, outgoing.length, occupied));
            byte[] buffer = new byte[128];
            DatagramPacket incoming = new DatagramPacket(buffer, buffer.length);
            receiver.receive(incoming);
            udpLoopback = "UDP an toàn 🌱".equals(
                    new String(incoming.getData(), incoming.getOffset(),
                            incoming.getLength(), StandardCharsets.UTF_8));
        }
        System.out.println("receiverBound=" + receiverBound);
        System.out.println("sameSocketSecondBindRejected=" +
                sameSocketSecondBindRejected);
        System.out.println("usedPortRejected=" + usedPortRejected);
        System.out.println("udpLoopback=" + udpLoopback);

        boolean channelSecondBindRejected = false;
        try (DatagramChannel channel = DatagramChannel.open()) {
            channel.bind(new InetSocketAddress(loopback, 0));
            try {
                channel.bind(new InetSocketAddress(loopback, 0));
            } catch (AlreadyBoundException expected) {
                channelSecondBindRejected = true;
            }
        }
        System.out.println("channelSecondBindRejected=" +
                channelSecondBindRejected);
        System.out.println("checks=" +
                (highPortRejected && negativePortRejected
                 && badAddressBytesRejected && unresolvedFlag
                 && channelUnresolvedRejected && receiverBound
                 && sameSocketSecondBindRejected && usedPortRejected
                 && udpLoopback && channelSecondBindRejected));

        // Optional manual probe: java UdpBindDiagnosticsDemo 0
        if (args.length == 1) {
            probeLoopbackPort(args[0]);
        }
    }

    static void probeLoopbackPort(String userPort) {
        try {
            int port = Integer.parseInt(userPort);
            try (DatagramSocket probe = new DatagramSocket(null)) {
                probe.setReuseAddress(false);
                probe.bind(new InetSocketAddress(
                        InetAddress.getLoopbackAddress(), port));
                System.out.println("manualProbe=BOUND");
            }
        } catch (IllegalArgumentException invalidInput) {
            System.out.println("manualProbe=INVALID_PORT");
        } catch (SocketException socketFailure) {
            System.out.println("manualProbe=SOCKET_ERROR");
        }
    }
}
~~~

### 9.1. Biên dịch và chạy

Lưu mã trong **`UdpBindDiagnosticsDemo.java`** với encoding UTF-8:

~~~bash
javac --release 17 -encoding UTF-8 UdpBindDiagnosticsDemo.java
java UdpBindDiagnosticsDemo
~~~

Đã kiểm chứng cả `javac --release 15` và `javac --release 17`, thực thi trên JDK 24. **Stdout chính xác của lần chạy mặc định trên môi trường thử:**

~~~text
highPortRejected=true
negativePortRejected=true
badAddressBytesRejected=true
unresolvedFlag=true
channelUnresolvedRejected=true
receiverBound=true
sameSocketSecondBindRejected=true
usedPortRejected=true
udpLoopback=true
channelSecondBindRejected=true
checks=true
~~~

**Giải thích từng kết quả:**

- `highPortRejected/negativePortRejected=true`: giới hạn hợp lệ của constructor `InetSocketAddress` được kiểm tra trước khi có bất kỳ bind.
- `badAddressBytesRejected=true`: byte IP không đúng độ dài bị từ chối ở API address; không phụ thuộc DNS.
- `unresolvedFlag=true`: `createUnresolved` cố ý tạo địa chỉ chưa phân giải.
- `channelUnresolvedRejected=true`: `DatagramChannel.send` từ chối target unresolved, không gửi gói ra mạng ngoài.
- `receiverBound=true`: socket A đã có local port do OS cấp và còn đang mở.
- `sameSocketSecondBindRejected=true`: không được bind lại **cùng một `DatagramSocket`**.
- `usedPortRejected=true`: socket B bị từ chối khi thử chiếm loopback + cổng của A, với reuse tắt trên **OS/JDK được thử**. Trên cấu hình OS đặc biệt, hành vi chia sẻ cổng có thể khác; phải đọc kết quả thực tế.
- `udpLoopback=true`: gói UTF-8 được gửi/nhận trong cùng máy; nếu không nhận trong 2 giây, `receive` ném `SocketTimeoutException` thay vì treo vô hạn.
- `channelSecondBindRejected=true`: cùng `DatagramChannel` bind hai lần tạo `AlreadyBoundException`.
- `checks=true`: tất cả điều kiện xác nhận trong chương trình thành công **trong lần kiểm chứng đã nêu**.

### 9.2. Probe cổng thủ công

Chạy với đối số `0` (bind một cổng auto):

~~~bash
java UdpBindDiagnosticsDemo 0
~~~

Ngoài 11 dòng mặc định, chương trình in thêm:

~~~text
manualProbe=BOUND
~~~

Chạy với port không hợp lệ:

~~~bash
java UdpBindDiagnosticsDemo 70000
~~~

Ngoài 11 dòng mặc định, chương trình in thêm:

~~~text
manualProbe=INVALID_PORT
~~~

Hai lệnh trên cũng đã được kiểm chứng trên JDK 24. Nếu dùng cổng cố định (ví dụ `12345`) thì kết quả **phụ thuộc môi trường**: có thể `BOUND` hoặc `SOCKET_ERROR`. **Không** đưa một giá trị chờ cố định vào unit test cho trường hợp port cụ thể nếu chưa kiểm soát điều kiện OS.

Để kiểm thử **thiếu quyền**, chạy probe trong **container/VM thử nghiệm** với port/policy đã có kế hoạch như mục 6, ghi riêng kết quả OS và account. Không thử chiếm port của ứng dụng đang phục vụ người dùng.

## 10. Một số tình huống rất dễ chẩn đoán sai

### 10.1. Đã bind nhưng không nhận gói

~~~text
isBound() == true
getLocalPort() > 0
receive() → SocketTimeoutException
~~~

Có thể đơn giản không có datagram đến, packet bị chặn, gửi nhầm địa chỉ/cổng hoặc ứng dụng không gọi send. Không chỉ vì timeout mà kết luận cổng đang bị process khác dùng.

**Cách xác minh:** gửi một datagram có kiểm soát từ process khác trên **cùng máy** tới đúng loopback + port, kiểm tra source/destination, packet length, timeout và kết quả decode.

### 10.2. Send thành công nhưng server không chạy

UDP không thiết lập connection và không đòi ACK ở tầng giao thức. Một sender có thể gọi `send` thành công dù bên nhận không có ứng dụng lắng nghe. Nếu ứng dụng cần chứng minh dịch vụ hoạt động, phải thiết kế **application-level response/health probe**, xử lý timeout và correlation ID, không dựa vào kết quả `send`.

### 10.3. Port cao vẫn báo thiếu quyền

Quyền có thể đến từ container sandbox, SELinux/AppArmor, chính sách endpoint, OS hoặc cấu hình runtime; **không chỉ low ports**. Đồng thời hãy kiểm tra process nào đang giữ cổng và IP bind. Đừng đoán mọi lỗi cổng cao đều là `BindException` do port busy.

### 10.4. Bind vào IP của host khác

`bind(localAddress, port)` yêu cầu **địa chỉ local**, không phải địa chỉ remote peer. Địa chỉ peer chỉ xuất hiện khi `send`/`connect` theo đúng API. Dùng IP của server đích trong `bind` là lỗi thiết kế thường tạo “Cannot assign requested address”.

### 10.5. Quên `close` và xung đột port ở lần test sau

Nếu test mở socket rồi không đóng, test kế tiếp có thể bị lỗi cổng thật sự đang được giữ. Sử dụng `try-with-resources`, không để socket nằm trong static field toàn cục không quản lý vòng đời và tránh giữ socket lâu ngoài thời gian kiểm thử. Bài demo dùng `try-with-resources` cho mọi socket/channel.

### 10.6. `SO_REUSEADDR`/`SO_REUSEPORT` làm kết quả “cổng bận” thay đổi

Những tùy chọn này có ngữ nghĩa phụ thuộc OS, cách bind và tình huống. `SO_REUSEADDR` và `SO_REUSEPORT` **không đồng nghĩa** với “mọi UDP socket đều có thể bind cùng port và đều nhận cùng gói”. Nếu test cần sự độc quyền, cấu hình reuse có chủ đích **trước khi bind**, và kiểm tra quy tắc thực tế của nền tảng.

### 10.7. Lấy thông báo lỗi làm API ổn định

Không match cố định những câu như `"Permission denied"` hoặc `"Address already in use"` để đưa ra một kết luận chắc chắn. Chúng là chi tiết OS/provider. Nên xây **loại lỗi ứng dụng** như `INVALID_CONFIGURATION`, `BIND_FAILED`, `ADDRESS_UNRESOLVED`, `TIMEOUT` sau khi có đủ điều kiện kiểm chứng; log ngoại lệ gốc để phục vụ điều tra.

### 10.8. Xem bài test qua loopback là đã kiểm tra quyền production

Loopback giúp kiểm tra code và các trạng thái socket mà không có yếu tố network ngoài. Nó **không** mô phỏng inbound firewall, container port mapping, cloud security group, broadcast/multicast hay quyền bind trên NIC vật lý. Phải bổ sung integration test theo topography thật khi triển khai.

## 11. Ma trận kiểm thử đề xuất

| Ca kiểm thử | Thiết lập | Kết quả mong đợi/cách đọc |
| --- | --- | --- |
| Bind cổng ephemeral hợp lệ | `DatagramSocket(null)` rồi bind loopback:0 | `isBound=true`; `getLocalPort()>0` |
| Bind lại cùng DatagramSocket | Socket đã bind | `SocketException` |
| Bind lại cùng DatagramChannel | Channel đã bind | `AlreadyBoundException` |
| Cổng đang được socket A giữ | Giữ A; B bind cùng loopback + port; reuse tắt | Thường `SocketException`/`BindException`, phụ thuộc OS |
| Port 65536 hoặc -1 | Tạo `InetSocketAddress` | `IllegalArgumentException` |
| Bytes IPv4 sai độ dài | `InetAddress.getByAddress` với 3 byte | `UnknownHostException` |
| Target chưa phân giải | `createUnresolved` + NIO `send` | `UnresolvedAddressException` |
| Local IP không gán cho host | Chạy trong sandbox với cấu hình đã kiểm soát | OS có thể từ chối bind; không cố định tên exception |
| Thiếu quyền bind | Dùng user/policy OS bị hạn chế trong VM/container | Ghi nhận lỗi OS, xác định bằng policy; không giả lập bằng Security Manager |
| Cổng được cho phép | Cùng config dưới account/policy hợp lệ và cổng trống | Bind thành công; không chứng minh UDP từ mạng ngoài đến được |
| Firewall chặn inbound | Bind hợp lệ, kiểm tra từ nguồn ngoài được kiểm soát | Có thể timeout/mất gói dù bind thành công |
| Bind IPv4/IPv6 không phù hợp | Chọn address family sai có chủ đích | Phản ứng phụ thuộc JDK/OS; ghi rõ type và cấu hình |
| UDP loopback roundtrip | Sender/receiver cùng host, đúng cổng | Nhận đúng byte, đúng packet length |
| Socket đóng | Gọi send/bind sau close | Lỗi socket/IO theo API; không phải port conflict |

**Phân loại mức kiểm thử:**

- **Unit test ổn định**: port ngoài phạm vi, invalid address bytes, tạo unresolved address, bind lần hai cùng đối tượng.
- **Integration test cục bộ**: hai socket cạnh tranh port, UDP loopback, SO_REUSEADDR.
- **Environment/security test**: low port/permission, container capabilities, firewall, non-local bind, dual-stack, IPv6.

Tránh biến mọi test OS-dependent thành “phải `true` trên bất kỳ runner CI nào”. CI trên Linux, Windows, container hoặc phiên bản kernel khác nhau có thể cho trạng thái khác; nên kiểm tra **đúng hợp đồng và capability** trên môi trường tương ứng.

## 12. Quy trình xử lý sự cố UDP theo thứ tự

Khi một service Java báo không thể mở UDP listener:

1. **Ghi nhận operation** thất bại (`new DatagramSocket`, `bind`, `send` hay `receive`), stack trace và exception type.
2. **Kiểm tra cấu hình**: port có trong `0..65535` không, local IP có đúng là IP của host và đúng family không, có nhầm remote IP vào local bind không.
3. **Kiểm tra trạng thái chương trình**: socket/channel đã bind/đóng chưa, có code bind lần thứ hai hay không.
4. **Kiểm tra port occupancy trong đúng network namespace** bằng công cụ OS và đối chiếu process; xem wildcard vs loopback và cấu hình reuse.
5. **Kiểm tra quyền**: account, capability, policy OS/container; không suy ra quyền từ số port đơn thuần hoặc message lỗi.
6. **Tái hiện bằng loopback với port 0** để chứng minh code cơ bản hoạt động độc lập với cổng production.
7. Nếu bind được nhưng không nhận gói, **chuyển sang lớp mạng**: firewall, network policy, source/dest, packet loss, IPv4/IPv6, routing và packet length.
8. Nếu là DNS/unresolved, kiểm tra cách phân giải hostname trước `send/connect`, không coi đó là lỗi bind local.
9. **Không tự động thử port mới trong production** để che đi một vấn đề quyền/cấu hình; service phải dùng đúng port hợp đồng.
10. **Đóng tài nguyên** sau mỗi test và thu hồi những thay đổi OS/policy đã cấp để thử nghiệm.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Có phải `BindException` luôn nghĩa “một process khác đang dùng port”?  
**Không.** Nó báo lỗi bind ở OS/JDK; nguyên nhân có thể là địa chỉ/cổng và những ràng buộc hệ thống. Phải đối chiếu địa chỉ local, trạng thái và dữ liệu OS.

**Câu 2.** Vì sao test cổng đang bận dùng `new DatagramSocket(null)` và cổng 0?  
Vì nó tạo socket chưa bind để cấu hình reuse trước, sau đó OS cấp port thật đang trống; socket thứ hai thử **chính cổng đã được A giữ**.

**Câu 3.** `DatagramChannel.bind` hai lần có ngoại lệ gì?  
**`AlreadyBoundException`** khi bind lại chính channel đang bind. Đây không phải ngoại lệ kết nối TCP hay hostname.

**Câu 4.** Port `-1` hoặc `65536` có phải permission denied không?  
**Không.** Chúng không hợp lệ về phạm vi và `InetSocketAddress` ném `IllegalArgumentException` ngay khi tạo.

**Câu 5.** Vì sao không tạo test “bind port 80 phải lỗi” để chứng minh quyền hạn?  
Quyền cổng thấp **phụ thuộc OS/user/capabilities/kernel configuration**, thậm chí cổng 80 có thể đang bị process khác dùng; không thể gán một kết quả cho mọi máy.

**Câu 6.** Có thể dùng `System.setSecurityManager` để mô phỏng mạng bị chặn trên Java hiện hành không?  
**Không nên.** Từ JDK 24 Security Manager đã bị vô hiệu hóa vĩnh viễn; dùng OS/container policy và môi trường thử được kiểm soát.

**Câu 7.** `DatagramSocket.send` thành công có chứng minh remote service đã nhận gói?  
**Không.** UDP không có ACK ở transport; nếu cần thì xác minh ở giao thức ứng dụng.

**Câu 8.** Vì sao `InetSocketAddress.createUnresolved(...)` hữu ích cho unit test?  
Vì nó tạo **đích chưa phân giải một cách xác định**, không phụ thuộc DNS có đang hoạt động hay không.

## 14. Tài liệu chính thức còn hiệu lực

- Oracle Java SE 25, **`DatagramSocket`**, `bind`, `isBound`, `getLocalPort`, `setReuseAddress` và các ngoại lệ: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/DatagramSocket.html
- Oracle Java SE 25, **`DatagramChannel`**, `bind/send/receive`, `AlreadyBoundException` và `UnresolvedAddressException`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/DatagramChannel.html
- Oracle Java SE 25, **`InetSocketAddress`**, cổng `0..65535`, `createUnresolved` và `isUnresolved`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/InetSocketAddress.html
- Oracle Java SE 25, **`InetAddress`**, `getByAddress(byte[])` và `getLoopbackAddress()`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/InetAddress.html
- Oracle Java SE 25, **`BindException` / `SocketException`**: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/BindException.html
- Oracle Java SE 25, **`AlreadyBoundException`**: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/AlreadyBoundException.html
- OpenJDK, **JEP 373 — Reimplement the Legacy DatagramSocket API** (Java 15): https://openjdk.org/jeps/373
- OpenJDK, **JEP 486 — Permanently Disable the Security Manager** (JDK 24): https://openjdk.org/jeps/486
- Oracle Java SE 24, **The Security Manager Is Permanently Disabled**: https://docs.oracle.com/en/java/javase/24/security/security-manager-is-permanently-disabled.html