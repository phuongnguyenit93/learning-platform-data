# Kiểm thử IPv4, IPv6 và cấu hình dual stack trong Java 15+

## 1. Mục tiêu và phạm vi

Một dịch vụ Java có thể chạy trên máy chỉ có IPv4, chỉ có IPv6 hoặc **dual stack** (có cả hai họ địa chỉ). Tuy nhiên, việc hệ điều hành có IPv6 không tự đảm bảo một socket Java đã mở sẽ chấp nhận cả client IPv4 lẫn IPv6. **Protocol family** của socket, địa chỉ được `bind`, cấu hình JVM, thiết lập hệ điều hành, namespace/container và firewall đều có thể tác động đến kết quả.

Bài học này đi từ API chuẩn `java.net.StandardProtocolFamily` đến cách kiểm thử thực tế:

1. Phân biệt `INET` (IPv4) và `INET6` (IPv6) khi tạo network channel.
2. Phân biệt **địa chỉ IP, protocol family của socket, địa chỉ bind và chính sách dual stack**.
3. Dùng `Inet4Address`, `Inet6Address`, `DatagramChannel`, `Selector` để thử UDP loopback của từng họ.
4. Kiểm chứng một IPv6 channel bind **wildcard `::`** có nhận datagram **IPv4** đến `127.0.0.1` hay không.
5. Thử các thuộc tính JVM `java.net.preferIPv4Stack`, `java.net.preferIPv6Addresses` ở **thời điểm khởi động**.
6. Thiết kế test matrix cho TCP, UDP, IPv4-only, IPv6-only, dual-stack, container/CI và điều kiện không có IPv6.
7. Không biến một kết quả loopback thành kết luận về mọi OS hoặc khả năng kết nối mạng công cộng.

Đây là kiến thức mạng Java **vẫn áp dụng với Java 15 và các JDK hiện hành**. Mã hoàn chỉnh được biên dịch bằng `javac --release 17` để chạy ổn định trên Java 17 trở lên, không dùng API preview hoặc các hằng mới chỉ xuất hiện sau Java 17.

## 2. Các thuật ngữ không nên đánh đồng

| Khái niệm | Ý nghĩa | Ví dụ và bẫy |
|---|---|---|
| **IPv4 address** | Địa chỉ giao thức Internet 32 bit | `127.0.0.1` là IPv4 loopback |
| **IPv6 address** | Địa chỉ Internet 128 bit | `::1` là IPv6 loopback, không cùng một địa chỉ với `127.0.0.1` |
| **`InetAddress`** | Abstraction Java đại diện một địa chỉ IP | Có hai subclass `Inet4Address` và `Inet6Address` |
| **`ProtocolFamily`** | Họ giao thức yêu cầu cho socket/channel | `StandardProtocolFamily.INET` hoặc `INET6` |
| **Bind** | Gắn một socket với local address/port | Bind `127.0.0.1` khác bind `::1` và khác wildcard |
| **Wildcard address** | Lắng nghe trên các local address phù hợp của họ mạng | `0.0.0.0` là wildcard IPv4; `::` là wildcard IPv6 |
| **Dual stack host** | Máy chạy được cả IPv4 và IPv6 | Không có nghĩa mọi socket `INET6` tự động nhận IPv4 |
| **Dual stack socket** | Socket IPv6 có thể giao tiếp với cả peer IPv6 và IPv4 nếu stack hỗ trợ | Có thể dùng địa chỉ IPv4-mapped nội bộ; phụ thuộc cấu hình OS/JVM |
| **Dual listener** | Hai socket/listener tách biệt cho IPv4 và IPv6 | Thường dễ kiểm soát quyền bind và policy trên nhiều OS |
| **DNS A/AAAA** | A trỏ tới IPv4; AAAA trỏ tới IPv6 | Thứ tự resolution không chứng minh dịch vụ lắng nghe cả hai |
| **Loopback test** | Client/server chạy cùng máy hoặc cùng network namespace | Không chứng minh đường đi giữa các máy, firewall, LB hay NAT |

**Ba mệnh đề độc lập:**

- `new InetSocketAddress(InetAddress.getByName("::1"), port)` có thể tạo một đối tượng địa chỉ IPv6 ngay cả khi network stack của tiến trình **không hỗ trợ IPv6**.
- `DatagramChannel.open(StandardProtocolFamily.INET6)` yêu cầu một channel họ IPv6 nhưng **chưa chọn local bind address** và chưa chứng minh sẽ chấp nhận IPv4.
- Một socket đã bind `::` có thể **dual stack** hoặc **IPv6-only** tùy hệ thống; phải thử kết nối/nhận datagram từ IPv4 thật.

## 3. `StandardProtocolFamily.INET` và `INET6`

Enum `java.net.StandardProtocolFamily` được hỗ trợ từ Java 7, trước Java 15, và vẫn được dùng trong các JDK hiện hành:

```java
import java.net.StandardProtocolFamily;
import java.nio.channels.DatagramChannel;

try (DatagramChannel udp4 = DatagramChannel.open(StandardProtocolFamily.INET);
     DatagramChannel udp6 = DatagramChannel.open(StandardProtocolFamily.INET6)) {
    // udp4 yêu cầu IPv4; udp6 yêu cầu IPv6.
}
```

Đoạn trên là một **đoạn code minh họa**; nó có thể ném lỗi nếu IPv6 không được hỗ trợ, không có bước bind/send/receive và không phải chương trình kiểm thử đầy đủ.

- **`INET`** yêu cầu socket Internet Protocol Version 4. Một `DatagramChannel` được mở với `INET` **không thể dùng để gửi tới một `Inet6Address` thực**. Ở OpenJDK thử nghiệm, gửi tới `::1` qua `INET` ném `UnsupportedAddressTypeException`.
- **`INET6`** yêu cầu socket Internet Protocol Version 6. Khi OS hỗ trợ dual stack, một socket IPv6 có thể xử lý thêm datagram/connection IPv4 theo cơ chế IPv4-mapped ở tầng native. **Không mặc định** IPv6 socket luôn IPv6-only.
- **`DatagramChannel.open()`** không truyền family là lựa chọn mặc định của JDK; hiệu quả có thể phụ thuộc JVM flags và khả năng nền tảng. Muốn kiểm thử có chủ đích, hãy ghi rõ `INET` hoặc `INET6`.
- Tương tự, với TCP có `ServerSocketChannel.open(StandardProtocolFamily.INET)`, `ServerSocketChannel.open(StandardProtocolFamily.INET6)` và `SocketChannel.open(family)`.

Không nhầm **`INET6`** là tên **một chế độ dual stack chắc chắn**, cũng không nhầm `INET` với một tùy chọn bật IPv6. Nếu ứng dụng thật cần bảo đảm chỉ chấp nhận IPv6, việc dùng `INET6` **chưa đủ** khi IPv4-mapped connections có thể được nhận.

### Kiểm tra option `IPV6_V6ONLY`

Hệ điều hành có thể có socket option native **`IPV6_V6ONLY`** để quyết định một IPv6 socket có nhận IPv4-mapped traffic hay không. Tuy nhiên, ở **Java SE 26**, `java.net.StandardSocketOptions` **không có hằng `IPV6_V6ONLY` chuẩn, portable**. Không viết:

```java
// KHÔNG COMPILE với StandardSocketOptions của Java SE chuẩn:
channel.setOption(StandardSocketOptions.IPV6_V6ONLY, true);
```

Đây là **anti-example**. Nếu một framework hoặc JNI/native extension cho phép thiết lập option riêng của OS, đó là API khác với tính di động khác. Để không phụ thuộc tính năng native, có thể vận hành **hai listener riêng** (IPv4/IPv6) và quản lý collision/port rõ ràng, hoặc triển khai một probe xác nhận tính dual stack thực tế ở môi trường đích.

## 4. Chọn địa chỉ kiểm thử: literal thay vì `localhost`

Với loopback, dùng hai địa chỉ chính xác:

```text
IPv4 loopback: 127.0.0.1
IPv6 loopback: ::1
IPv4 wildcard: 0.0.0.0
IPv6 wildcard: ::
```

**`127.0.0.1` và `::1` không hoán đổi cho nhau.** Chúng đều là loopback nhưng thuộc hai không gian địa chỉ khác nhau; một socket bind chỉ `::1` không đương nhiên nhận datagram gửi tới `127.0.0.1`.

Để tạo **đúng object Java** mà không phụ thuộc DNS hay cấu hình hosts file:

```java
// Đoạn minh họa trong method có throws UnknownHostException.
InetAddress ipv4 = InetAddress.getByAddress(new byte[] {127, 0, 0, 1});
byte[] rawIpv6 = new byte[16];
rawIpv6[15] = 1;   // ::1
InetAddress ipv6 = InetAddress.getByAddress(rawIpv6);
```

Những thao tác trên tạo `Inet4Address` và `Inet6Address` tương ứng, nhưng **không phải phép đo khả năng mạng**. Một JVM chạy với `-Djava.net.preferIPv4Stack=true` vẫn có thể parse/tạo IPv6 address object, trong khi mở hoặc bind một socket `INET6` không khả dụng.

Các biểu thức `InetAddress.getByName("127.0.0.1")` và `InetAddress.getByName("::1")` cũng là IP literals, không phải DNS hostname cần lookup; tuy nhiên dùng `getByAddress` giúp ví dụ không phụ thuộc trình phân giải địa chỉ nào.

**Đừng dùng `InetAddress.getLoopbackAddress()` để quyết định phép thử IPv6.** API này trả một loopback address phù hợp theo cấu hình runtime; nó không được hứa sẽ luôn là `::1`. Khi kiểm thử hai protocol family, hãy chọn từng địa chỉ thật rõ ràng.

## 5. Bind: địa chỉ cụ thể và wildcard có ý nghĩa khác nhau

### 5.1. Bind theo địa chỉ cụ thể

Ví dụ:

```java
DatagramChannel channel = DatagramChannel.open(StandardProtocolFamily.INET6);
channel.bind(new InetSocketAddress(InetAddress.getByName("::1"), 0));
```

Đây chỉ là đoạn minh họa, phải đóng channel với `try-with-resources` trong thực tế. `0` yêu cầu OS chọn một local port còn trống. Bind `::1` chỉ nhận traffic gửi tới IPv6 loopback. Không đánh đồng thao tác này với lắng nghe trên tất cả interface IPv6 của máy.

### 5.2. Bind wildcard

```java
byte[] allZeroes = new byte[16]; // ::
InetAddress ipv6Any = InetAddress.getByAddress(allZeroes);
DatagramChannel channel = DatagramChannel.open(StandardProtocolFamily.INET6);
channel.bind(new InetSocketAddress(ipv6Any, 0));
```

Đoạn này minh họa **IPv6 wildcard**; sau khi bind cần nhận gói và đóng channel đúng vòng đời. Trên OS có dual-stack socket, đây là trường hợp có thể nhận thêm gói IPv4 qua một IPv6 socket. Trên hệ thống IPv6-only socket, gói IPv4 sẽ không tới được channel này.

**Vấn đề bảo mật:** `::` và `0.0.0.0` là wildcard, có thể expose dịch vụ qua nhiều network interface hơn mong đợi. Dùng wildcard chỉ khi policy thực sự muốn nghe mọi interface phù hợp, kiểm tra firewall/ACL và bind trong container namespace đích. Để thử tính dual stack mà không lộ dữ liệu ra mạng, dùng payload giả trên **loopback và port OS cấp tự động**, không dùng dịch vụ production.

### 5.3. Dual stack host không bảo đảm dual stack listener

Một host có IPv4 và IPv6 có thể:

- Cho phép IPv4/IPv6 trên **hai socket riêng**.
- Cho phép `INET6` socket bind wildcard nhận **cả IPv4 lẫn IPv6**.
- Cấu hình socket IPv6 **v6-only** nên không nhận được IPv4, dù IPv4 socket riêng vẫn hoạt động.
- Vô hiệu hóa IPv6 cho JVM bằng `java.net.preferIPv4Stack=true`, dù OS có IPv6.
- Có network policy/firewall/container isolation chặn một họ mạng mà địa chỉ vẫn tồn tại.

Chỉ khi **thử được cả hai đường kết nối thực** mới khẳng định deployment đáp ứng yêu cầu dual stack của chính mình.

## 6. Thuộc tính JVM điều khiển IPv4/IPv6

Java có hai system properties hiện hành, được tài liệu Java SE 26 mô tả. Chúng **được xét tại lúc JVM khởi động**, vì vậy nên truyền bằng `-D` trước tên main class.

| Thuộc tính | Giá trị điển hình | Tác dụng thực tế |
|---|---|---|
| `java.net.preferIPv4Stack` | `false` (mặc định) | Khi IPv6 hỗ trợ, cho phép Java dùng native IPv6 sockets có khả năng dual stack theo nền tảng |
| `java.net.preferIPv4Stack=true` | `true` | Yêu cầu dùng socket IPv4-only; ứng dụng không giao tiếp được với IPv6-only hosts |
| `java.net.preferIPv6Addresses` | `false` (mặc định) | Khi hostname có cả A/AAAA, mặc định **ưu tiên địa chỉ IPv4** để tương thích |
| `java.net.preferIPv6Addresses=true` | `true` | Khi có cả IPv4/IPv6, ưu tiên **địa chỉ IPv6** khi giải quyết hostname |
| `java.net.preferIPv6Addresses=system` | `system` | Tôn trọng thứ tự địa chỉ do resolver/nền tảng trả về |

**Hai properties không cùng trách nhiệm:**

- `preferIPv4Stack` là **lựa chọn stack/socket**, có thể khiến `INET6` không được hỗ trợ.
- `preferIPv6Addresses` là **lựa chọn thứ tự địa chỉ khi resolve hostname**; không tự bật IPv6 trên OS, không cấu hình `IPV6_V6ONLY`, không biến một listener bind `127.0.0.1` thành IPv6 listener.
- `preferIPv6Addresses=system` chỉ liên quan resolver order, **không bảo đảm** kết nối thành công với mọi địa chỉ.
- `System.setProperty(...)` sau khi các lớp mạng đã được khởi tạo **không phải** cách đáng tin để đổi hành vi của hai thuộc tính này; chạy **JVM mới** cho mỗi cấu hình cần test.

Ví dụ trên Bash:

```bash
java -Djava.net.preferIPv4Stack=true -cp . ProtocolFamilyProbe
java -Djava.net.preferIPv6Addresses=true -cp . ProtocolFamilyProbe
java -Djava.net.preferIPv6Addresses=system -cp . ProtocolFamilyProbe
```

Trên **Windows PowerShell**, nên quote toàn bộ argument `-D...` để tránh parser xử lý sai dấu chấm và dấu bằng:

```powershell
java '-Djava.net.preferIPv4Stack=true' -cp . ProtocolFamilyProbe
java '-Djava.net.preferIPv6Addresses=true' -cp . ProtocolFamilyProbe
java '-Djava.net.preferIPv6Addresses=system' -cp . ProtocolFamilyProbe
```

Các command chỉ hoạt động sau khi đã biên dịch `ProtocolFamilyProbe.java` ở phần 9; đây là các lần chạy **cùng một chương trình dưới các JVM riêng biệt**. Nếu bạn dùng launcher/systemd/container/orchestration, truyền properties **vào tiến trình Java thực sự** chứ không sửa một process khác.

## 7. Lập test matrix có giá trị hơn một thử nghiệm đơn lẻ

Nên phân chia kiểm thử thành ít nhất bốn phép thử độc lập:

| Test ID | Server/listener | Client/sender | Điều cần chứng minh | Diễn giải đúng |
|---|---|---|---|---|
| **T1 / IPv4** | `INET` bind `127.0.0.1:0` | `INET` gửi tới đúng IPv4 port | Datagram IPv4 đi-về trên loopback | Kiểm tra đường IPv4 local hoạt động |
| **T2 / IPv6** | `INET6` bind `[::1]:0` | `INET6` gửi tới IPv6 loopback | Datagram IPv6 đi-về | Kiểm tra đường IPv6 loopback thực sự hoạt động |
| **T3 / family mismatch** | `INET` channel | Cố gửi tới `[::1]` | IPv4-only channel không gửi được tới IPv6 peer | Không dựa vào giả thuyết “family tự chuyển” |
| **T4 / dual stack** | `INET6` bind `[::]:0` | `INET` gửi tới `127.0.0.1:port` | IPv6 wildcard socket nhận gói IPv4 hay không | Kết quả phụ thuộc OS/JVM, không suy đoán trước |

**Hai kiểu kết quả khác nhau cần giữ riêng:**

- **PASS**: payload thực sự đến, nội dung và address được kiểm tra.
- **NO_PACKET / UNAVAILABLE_OR_ERROR**: không chứng minh một cấu hình duy nhất. Có thể do OS IPv6-only, IPv6 tắt, firewall, provider, container, timeout, hoặc môi trường test chặn sockets.

Vì UDP không thiết lập kết nối và không có ACK transport, **gửi thành công không đồng nghĩa bên nhận đã nhận**. Probe phải đợi I/O readiness rồi đọc, so byte payload, không chỉ gọi `sender.send()` rồi in PASS.

## 8. Cách kiểm thử bằng NIO mà không gây treo thread

`DatagramChannel` hỗ trợ `configureBlocking(false)` và đăng ký `SelectionKey.OP_READ` với `Selector`. Để một smoke test không kẹt mãi khi IPv6 bị chặn hoặc gói không đến, dùng `selector.select(timeoutMillis)` có hạn.

Sơ đồ thí nghiệm:

```text
DatagramChannel receiver (INET hoặc INET6)
    |
    +-- bind(loopbackAddress, port=0) -> OS chọn cổng
    +-- configureBlocking(false)
    +-- register(selector, OP_READ)
    |
DatagramChannel sender cùng family
    +-- send(PAYLOAD, receiverLocalAddress)
    |
selector.select(1200)
    |
    +-- 0 key ready     -> NO_PACKET (không suy luận nguyên nhân)
    +-- có read ready  -> receiver.receive(ByteBuffer)
                            |
                            +-- so bytes đầy đủ -> PASS
                            +-- khác bytes      -> WRONG_PAYLOAD
```

**Giới hạn của smoke test:** không thể bảo đảm các datagram UDP ngoài ý muốn tuyệt đối không đến một ephemeral loopback port, nhưng rủi ro trong một thư mục thử nghiệm cục bộ là thấp; chương trình dùng payload và cổng tự chọn, không dựa vào host mạng công cộng. Khi cần test CI nghiêm ngặt, hãy cô lập network namespace và kiểm soát tiến trình phát datagram.

### Tại sao `SelectionKey.OP_READ` không phải việc nhận dữ liệu?

`Selector` báo **khả năng đọc**, nhưng app vẫn phải gọi `DatagramChannel.receive(ByteBuffer)` và so payload thực. `receive()` trên non-blocking channel có thể trả `null` nếu chưa có datagram ở thời điểm gọi; không được diễn giải `null` là EOF như TCP stream. Test chỉ đánh dấu PASS nếu `origin != null` **và** toàn bộ payload khớp.

### Chọn `port=0` và scope

Bind port 0 làm OS chọn cổng tự do. Không dùng port cứng như 8080 cho phép thử này; port cứng dễ xung đột với service khác và không chứng minh thêm điều gì về protocol family. Test `::` wildcard vẫn cần cân nhắc bề mặt bind, nhưng dữ liệu gửi đi chỉ tới `127.0.0.1`.

## 9. Chương trình Java 17+ hoàn chỉnh: IPv4, IPv6 và dual UDP

Ví dụ sau **không phụ thuộc dịch vụ ngoài hoặc DNS** và dùng NIO `DatagramChannel`. Code có thể chạy trên IPv4-only runtime: khi `INET6` không được hỗ trợ, nó ghi **UNAVAILABLE_OR_ERROR_...** thay vì mặc định coi IPv6 đã hoạt động.

Tạo tệp **`ProtocolFamilyProbe.java`** (UTF-8):

```java
import java.io.IOException;
import java.net.Inet4Address;
import java.net.Inet6Address;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ProtocolFamily;
import java.net.SocketAddress;
import java.net.StandardProtocolFamily;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.nio.channels.DatagramChannel;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.util.Arrays;

public final class ProtocolFamilyProbe {
    private static final byte[] PAYLOAD =
            "family-probe".getBytes(StandardCharsets.UTF_8);

    private static InetAddress ipv4Loopback() throws IOException {
        return InetAddress.getByAddress(new byte[] {127, 0, 0, 1});
    }

    private static InetAddress ipv6Loopback() throws IOException {
        byte[] address = new byte[16];
        address[15] = 1;
        return InetAddress.getByAddress(address);
    }

    private static InetAddress ipv6Any() throws IOException {
        return InetAddress.getByAddress(new byte[16]);
    }

    private static String udpRoundTrip(ProtocolFamily family, InetAddress address) {
        try (DatagramChannel receiver = DatagramChannel.open(family);
             DatagramChannel sender = DatagramChannel.open(family);
             Selector selector = Selector.open()) {
            receiver.bind(new InetSocketAddress(address, 0));
            receiver.configureBlocking(false);
            receiver.register(selector, SelectionKey.OP_READ);
            sender.bind(new InetSocketAddress(address, 0));

            int sent = sender.send(ByteBuffer.wrap(PAYLOAD), receiver.getLocalAddress());
            if (sent != PAYLOAD.length) {
                return "SEND_INCOMPLETE";
            }
            if (selector.select(1200) == 0) {
                return "NO_PACKET";
            }
            ByteBuffer buffer = ByteBuffer.allocate(64);
            SocketAddress origin = receiver.receive(buffer);
            buffer.flip();
            byte[] actual = new byte[buffer.remaining()];
            buffer.get(actual);
            return origin != null && Arrays.equals(actual, PAYLOAD)
                    ? "PASS" : "WRONG_PAYLOAD";
        } catch (IOException | UnsupportedOperationException error) {
            return "UNAVAILABLE_OR_ERROR_" + error.getClass().getSimpleName();
        }
    }

    private static String udpDualStack() {
        try (DatagramChannel receiver =
                    DatagramChannel.open(StandardProtocolFamily.INET6);
             DatagramChannel sender =
                    DatagramChannel.open(StandardProtocolFamily.INET);
             Selector selector = Selector.open()) {
            receiver.bind(new InetSocketAddress(ipv6Any(), 0));
            receiver.configureBlocking(false);
            receiver.register(selector, SelectionKey.OP_READ);
            sender.bind(new InetSocketAddress(ipv4Loopback(), 0));

            int port = ((InetSocketAddress) receiver.getLocalAddress()).getPort();
            int sent = sender.send(ByteBuffer.wrap(PAYLOAD),
                    new InetSocketAddress(ipv4Loopback(), port));
            if (sent != PAYLOAD.length) {
                return "SEND_INCOMPLETE";
            }
            if (selector.select(1200) == 0) {
                return "NO_PACKET";
            }
            ByteBuffer buffer = ByteBuffer.allocate(64);
            SocketAddress origin = receiver.receive(buffer);
            buffer.flip();
            byte[] actual = new byte[buffer.remaining()];
            buffer.get(actual);
            return origin != null && Arrays.equals(actual, PAYLOAD)
                    ? "ACCEPTS_IPV4" : "WRONG_PAYLOAD";
        } catch (IOException | UnsupportedOperationException error) {
            return "UNAVAILABLE_OR_ERROR_" + error.getClass().getSimpleName();
        }
    }

    private static String ipv4ChannelToIpv6() {
        try (DatagramChannel channel =
                    DatagramChannel.open(StandardProtocolFamily.INET)) {
            channel.bind(new InetSocketAddress(ipv4Loopback(), 0));
            channel.send(ByteBuffer.wrap(PAYLOAD),
                    new InetSocketAddress(ipv6Loopback(), 9));
            return "UNEXPECTED_SEND";
        } catch (IOException | UnsupportedOperationException
                 | java.nio.channels.UnsupportedAddressTypeException error) {
            return "REJECTED_" + error.getClass().getSimpleName();
        }
    }

    public static void main(String[] args) throws IOException {
        System.out.println("literal4=" + (ipv4Loopback() instanceof Inet4Address));
        System.out.println("literal6=" + (ipv6Loopback() instanceof Inet6Address));
        System.out.println("udp4=" + udpRoundTrip(StandardProtocolFamily.INET,
                ipv4Loopback()));
        System.out.println("udp6=" + udpRoundTrip(StandardProtocolFamily.INET6,
                ipv6Loopback()));
        System.out.println("inetToIpv6=" + ipv4ChannelToIpv6());
        System.out.println("dualUdp=" + udpDualStack());
        System.out.println("preferIPv4Stack="
                + System.getProperty("java.net.preferIPv4Stack", "<unset>"));
        System.out.println("preferIPv6Addresses="
                + System.getProperty("java.net.preferIPv6Addresses", "<unset>"));
    }
}
```

### 9.1. Biên dịch và chạy

```bash
javac --release 17 -encoding UTF-8 ProtocolFamilyProbe.java
java -cp . ProtocolFamilyProbe
```

Chạy một JVM khác chỉ dùng IPv4 stack:

```bash
java -Djava.net.preferIPv4Stack=true -cp . ProtocolFamilyProbe
```

Trên Windows PowerShell, dùng dấu nháy cho argument `'-Djava.net.preferIPv4Stack=true'` như phần 6.

### 9.2. Stdout **đã quan sát** trên Windows / OpenJDK Zulu 24.0.2

Đây là **đầu ra chính xác của một lần chạy kiểm chứng trên môi trường dual-stack đã thử**, không phải stdout được đảm bảo bất biến trên mọi JDK/OS:

```text
literal4=true
literal6=true
udp4=PASS
udp6=PASS
inetToIpv6=REJECTED_UnsupportedAddressTypeException
dualUdp=ACCEPTS_IPV4
preferIPv4Stack=<unset>
preferIPv6Addresses=<unset>
```

**Không hard-code các kỳ vọng `udp6=PASS` hoặc `dualUdp=ACCEPTS_IPV4` trong CI chạy trên hệ thống chưa xác định**. Nếu IPv6 tắt, `udp6` có thể báo lỗi/không khả dụng. Nếu IPv6 socket có chính sách `IPV6_V6ONLY`, `dualUdp` có thể báo `NO_PACKET`. Nếu firewall/namespace chặn gói, kết quả cũng có thể khác. Ký tự `<unset>` chỉ nói rằng **JVM không được truyền property tương ứng**, không nói JVM đang chạy không có chính sách mặc định.

### 9.3. Đọc từng kết quả mà không kết luận quá mức

- **`literal4=true`, `literal6=true`**: mã đã tạo được object đúng lớp `Inet4Address` và `Inet6Address` từ literal raw bytes. Nó không chứng minh khả năng bind hay giao tiếp mạng.
- **`udp4=PASS`**: cặp IPv4 `INET` trên loopback gửi/nhận và so bytes đúng.
- **`udp6=PASS`**: cặp IPv6 `INET6` trên `::1` gửi/nhận đúng trong môi trường thử.
- **`inetToIpv6=REJECTED_UnsupportedAddressTypeException`**: `INET` IPv4-only channel không thể gửi tới IPv6 peer trong JDK thử nghiệm.
- **`dualUdp=ACCEPTS_IPV4`**: channel `INET6` bind wildcard nhận được datagram do một channel `INET` gửi đến `127.0.0.1`. Đây là bằng chứng **dual stack loopback UDP trong môi trường đang chạy**.
- **`preferIPv4Stack=<unset>`**: property không được truyền tường minh; trên JDK đang thử, IPv6 vẫn dùng được.
- **`preferIPv6Addresses=<unset>`**: không thay đổi chính sách resolver từ default; đây không phải bằng chứng về một hostname có A/AAAA nào.

Đặc biệt, chữ `ACCEPTS_IPV4` **không chứng minh** listener nhận được IPv4 từ host ngoài máy, đi qua load balancer, NAT hoặc firewall; test chỉ gửi vào **loopback**. Cũng không chứng minh TCP listener của cùng ứng dụng đang dual stack, vì TCP/UDP có socket/options/port riêng.

### 9.4. Kết quả tham khảo khi bật IPv4-only stack

Trong một JVM riêng với:

```text
-Djava.net.preferIPv4Stack=true
```

`Inet6Address` từ literal có thể vẫn được tạo, nhưng việc mở `DatagramChannel.open(INET6)` có thể ném `UnsupportedOperationException`. Một phép thử ngắn trên Windows/OpenJDK 24 xác nhận `v6Literal=true` trong khi `INET6` channel **không khả dụng**. Khi chạy chương trình chính, các dòng `udp6`/`dualUdp` có thể là:

```text
udp6=UNAVAILABLE_OR_ERROR_UnsupportedOperationException
dualUdp=UNAVAILABLE_OR_ERROR_UnsupportedOperationException
preferIPv4Stack=true
```

Đó là **mẫu đầu ra có điều kiện**, không phải một transcript đầy đủ được hứa hẹn cho mọi OS/JDK. Điều quan trọng cần test là **IPv4-only stack thực sự ngăn truy cập IPv6**, không phải chỉ kiểm tra giá trị `System.getProperty`.

## 10. Vì sao IPv4-mapped IPv6 không nên dùng làm chứng cứ trực tiếp?

Ở hệ điều hành hỗ trợ dual stack, IPv6 socket có thể biểu diễn một IPv4 peer nội bộ như **IPv4-mapped IPv6** `::ffff:127.0.0.1`. Tuy nhiên Java `InetAddress`/`Inet6Address` **không trả một đối tượng mapped như một `Inet6Address` riêng theo cách đó**: Javadoc Java SE 26 cho biết mapped literal được chuyển thành IPv4 `Inet4Address` khi đi vào API.

Ví dụ:

```java
InetAddress mappedInput = InetAddress.getByName("::ffff:127.0.0.1");
// Java có thể trả Inet4Address do chuẩn hóa mapped literal.
```

Không lấy `mappedInput instanceof Inet6Address` làm test rằng OS có dual stack hay không. Java API chuẩn hóa biểu diễn của một địa chỉ, còn **socket binding policy** là một vấn đề khác.

**Test đúng:** mở `INET6`, bind `::`, cho sender `INET` thực sự gửi vào địa chỉ IPv4 cùng port, rồi nhận/so gói như phần 9. Nếu chỉ parse string `::ffff:...`, chưa có network packet nào được chuyển và chưa có gì chứng minh đường truyền dual stack.

## 11. TCP cần test riêng với `ServerSocketChannel`

Mặc dù ví dụ hoàn chỉnh dùng **UDP** để kiểm tra protocol family, một server **TCP** cũng có vấn đề tương tự:

```java
// Minh họa trong method có imports java.net.* / java.nio.channels.*:
try (ServerSocketChannel server =
             ServerSocketChannel.open(StandardProtocolFamily.INET6)) {
    server.bind(new InetSocketAddress(InetAddress.getByName("::"), 0));
    // Muốn chứng minh TCP dual stack phải thử connect từ cả
    // SocketChannel.open(INET) -> 127.0.0.1:serverPort
    // SocketChannel.open(INET6) -> [::1]:serverPort
    // rồi kiểm tra accept() có nhận cả hai.
}
```

Đoạn này **không phải chương trình hoàn chỉnh**: chưa có accept loop, client, timeout và dọn selected keys. Tránh `accept()` blocking vô hạn trong test; dùng **non-blocking `ServerSocketChannel` + `Selector.OP_ACCEPT`**, hoặc đặt giới hạn ở phía client/thread để có kết quả rõ ràng.

**Một TCP dual-stack smoke test tối thiểu** cần kiểm tra:

1. Server `INET6` bind wildcard `::` trên **port tự chọn**.
2. Client **IPv6** thử kết nối tới `::1:port`; server phải accept được.
3. Client **IPv4** độc lập thử kết nối tới `127.0.0.1:port`; server phải accept được.
4. Khi server không nhận IPv4, phân loại lỗi **refused / timeout / unavailable**, không khẳng định ngay là do chỉ có `IPV6_V6ONLY`.
5. Với ứng dụng thật, test cả ingress qua load balancer/proxy, SSL/TLS nếu có và địa chỉ mạng ngoài loopback.

Nếu muốn kết quả hoàn toàn portable và policy chặt chẽ, có thể khởi động **hai listener riêng** cho IPv4/IPv6 với cổng/bind được quản lý. Cần lưu ý OS có thể coi một IPv6 wildcard listener dual-stack là chiếm luôn IPv4 port tương ứng; điều đó có thể khiến listener IPv4 thứ hai **bind thất bại**. Đừng chỉ bật `SO_REUSEADDR` và cho rằng vấn đề được giải quyết an toàn, nhất là khi có nhiều process có thể bắt cùng port.

## 12. DNS, `localhost` và quy tắc resolver

Một hostname có thể có cả DNS record **A** và **AAAA**:

```text
example.internal. A     192.0.2.10
example.internal. AAAA  2001:db8::10
```

Đây là **địa chỉ ví dụ dùng trong tài liệu**, không phải endpoint đang chạy. Trên môi trường thật, `InetAddress.getAllByName(hostname)` trả những địa chỉ mà resolver thấy theo cấu hình OS và JVM. Nếu bạn chỉ gọi `InetAddress.getByName(hostname)` rồi kết nối với kết quả đầu tiên, ứng dụng có thể **bỏ qua một họ còn hoạt động** do resolver order.

Một phép thử hữu ích:

```java
// Minh họa khi hostname là String đã được cấu hình.
for (InetAddress address : InetAddress.getAllByName(hostname)) {
    System.out.println(address.getClass().getSimpleName()
            + " " + address.getHostAddress());
}
```

Lệnh trên cho biết **thứ tự resolution quan sát được**, nhưng vẫn phải thực sự thử TCP connect/UDP receive để chứng minh đường mạng. Đừng cố định snapshot `getAllByName("localhost")` thành expected output trên mọi OS vì hosts file, DNS config, JVM flags và policy resolver có thể khác nhau.

### Dual stack cho client không phải tự nhiên “fallback” trong mọi API

Nếu client nhận nhiều địa chỉ A/AAAA, cần một chính sách **thử địa chỉ tiếp theo khi lỗi**, quản lý deadline chung và tránh replay/side effect ngoài ý muốn. Một số thư viện client có chiến lược kết nối riêng; đừng mặc định mọi `SocketChannel.connect` hay `DatagramChannel.send` tự thử tất cả A/AAAA. Ở tầng TCP, các triển khai hiện đại có thể dùng chiến lược kiểu **Happy Eyeballs** theo thư viện/giao thức, nhưng phải kiểm tra chính thư viện đang sử dụng.

Với UDP, gửi thành công còn **không hứa peer tồn tại hoặc đã nhận gói**, nên fallback giữa địa chỉ cũng cần deadline và logic ứng dụng (ACK/application response nếu giao thức yêu cầu).

## 13. IPv6 scope, URL và firewall: những lỗi cấu hình hay bỏ qua

### 13.1. IPv6 link-local cần scope

Một địa chỉ IPv6 link-local thường có dạng `fe80::...` và chỉ hợp lệ trong một phạm vi interface. Nhiều môi trường cần **scope ID hoặc network interface** (ví dụ `%eth0`) để xác định đúng link. Một địa chỉ link-local không scope có thể không route được hoặc bind/connect đến interface ngoài mong đợi.

Java có các API `Inet6Address` lưu scope ID/interface; nên lấy network interface từ cấu hình đúng, không chèn tên interface của máy phát triển vào production. Trong phần test loopback `::1`, **không cần scope**.

### 13.2. IPv6 literal trong URI cần dấu ngoặc vuông

Khi dùng URL/URI:

```text
http://127.0.0.1:8080/
http://[::1]:8080/
```

Dấu `[` và `]` cần thiết vì IPv6 address chứa dấu `:`, cùng ký tự phân tách cổng trong URI. Trong Java `new InetSocketAddress(InetAddress, port)`, bạn không cần tự thêm ngoặc vì address và port là hai đối số riêng.

### 13.3. Đường mạng ngoài loopback

Cần test thêm theo deployment:

- Firewall host, security groups, Kubernetes NetworkPolicy, load balancer listener và inbound rules cho **từng họ**.
- Container/network namespace có IPv6 thực sự hay không; chỉ thấy máy chủ host có IPv6 không đủ.
- IPv4 NAT và IPv6 routing/neighbor discovery; cấu hình egress/ingress có thể khác.
- Proxy/LB có listener dual stack nhưng backend chỉ IPv4 (hoặc ngược lại).
- TLS/certificate hostname nếu dùng TCP/TLS; kết nối tới IP literal có thể khác xác minh danh tính theo hostname.
- Địa chỉ public, private hoặc link-local; test loopback không chứng minh route giữa các subnet.

**Không thử nghiệm bind `::` trong production mà chưa kiểm tra ACL**: nó có thể mở cổng trên interface IPv6 trước đây không được phục vụ.

## 14. Cấu hình JVM và hệ điều hành: cách chạy một test matrix

Thực hiện phép thử trên **cùng một host hoặc môi trường container đích**, thay đổi **một yếu tố mỗi lần**.

| Kịch bản | Cấu hình | Điều mong đợi cần kiểm tra |
|---|---|---|
| **Baseline** | Không set hai `java.net.prefer...` properties | `INET` hoạt động, `INET6` nếu OS hỗ trợ; dual tùy nền tảng |
| **IPv4-only Java stack** | `-Djava.net.preferIPv4Stack=true` | `INET` vẫn dùng được, IPv6 channel/connection không được phép theo runtime |
| **Ưu tiên resolver IPv6** | `-Djava.net.preferIPv6Addresses=true` | Thứ tự A/AAAA được ưu tiên IPv6 nếu có; không kết luận socket tự dual |
| **Resolver theo hệ thống** | `-Djava.net.preferIPv6Addresses=system` | Tôn trọng thứ tự resolver OS; test thực tế và không hard-code output |
| **IPv6-only socket policy** | Cấu hình OS có tác dụng `IPV6_V6ONLY` | Bind `::` nhận IPv6, không nhận IPv4 trên chính socket đó |
| **Dual socket policy** | OS/JVM cho phép IPv4-mapped trên IPv6 socket | Bind `::` và thử `INET` sender: test `dualUdp=ACCEPTS_IPV4` |
| **Container thiếu IPv6** | Network namespace không có IPv6 | `INET6` có thể thất bại dù host chính có IPv6 |
| **Public ingress** | Firewall/LB/proxy được cấu hình A/AAAA/IPv4/IPv6 | Chứng minh từ client ở từng họ, không chỉ từ chính server |

**Không chỉnh system-wide IPv6 configuration trên máy dùng chung chỉ để chạy một unit test.** Nếu cần thử IPv6-only vs dual-stack policy, dùng môi trường test cô lập được quản lý bởi nhóm vận hành và ghi lại OS/kernel flags. `StandardSocketOptions.IPV6_V6ONLY` **không tồn tại như hằng portable** để bạn toggle ngay trong Java JCA/NIO chuẩn.

### Đọc thông tin network trên OS

- Trên Linux, có thể dùng `ip -4 addr` và `ip -6 addr` để xem địa chỉ; `ss -lnt` / `ss -lnu` để xem socket TCP/UDP đang lắng nghe. Cần quyền/phạm vi namespace phù hợp.
- Trên Windows, dùng `Get-NetIPAddress -AddressFamily IPv4` và `Get-NetIPAddress -AddressFamily IPv6`; kiểm tra listening TCP bằng `Get-NetTCPConnection`, còn UDP có `Get-NetUDPEndpoint`.
- Trên macOS, dùng `ifconfig` và các công cụ quản trị socket/network tương ứng.

Các công cụ này **chỉ cung cấp quan sát cấu hình và socket state**, không thay thế kiểm thử gửi/nhận gói. Khi thử dịch vụ qua mạng, lấy kết quả từ **client IPv4 thật và client IPv6 thật**; luôn giới hạn lưu lượng và quyền thử nghiệm.

## 15. Các lỗi thường gặp và hướng chẩn đoán

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `Inet6Address` tạo được nhưng `INET6` mở thất bại | IPv6 không được hỗ trợ hoặc `preferIPv4Stack=true` | Kiểm tra JVM flags lúc startup và OS, không lấy object parse làm connectivity test |
| `UnsupportedOperationException` khi `DatagramChannel.open(INET6)` | Provider/nền tảng không hỗ trợ family đã yêu cầu | Báo rõ khả năng môi trường; không fallback âm thầm sang IPv4 khi policy yêu cầu IPv6 |
| `UnsupportedAddressTypeException` khi `INET` gửi tới IPv6 | Channel IPv4 không nhận IPv6 address | Dùng `INET6`/địa chỉ tương ứng hoặc listener/client tách biệt |
| `BindException: Address already in use` | Port bị dùng, listener IPv6 dual có thể đã chiếm IPv4 port | Dùng port 0 khi test, thiết kế bind policy và stop listener cũ |
| `BindException` khi bind IPv6 cụ thể | Địa chỉ không thuộc interface/namespace hiện tại hoặc policy chặn | Kiểm tra `ip -6 addr`, IPv6 scope và quyền bind |
| `udp4=PASS`, `udp6=UNAVAILABLE` | IPv6 tắt/chưa cấu hình trong JVM hoặc OS | Xem startup properties, capability và trạng thái network |
| `udp6=PASS` nhưng `dualUdp=NO_PACKET` | Có thể IPv6 socket v6-only hoặc IPv4 bị chặn | Thử IPv4 sender/IPv6 wildcard trên cùng namespace, kiểm tra OS firewall/policy |
| `dualUdp=ACCEPTS_IPV4` nhưng client bên ngoài không kết nối | Loopback không chứng minh ingress ngoài mạng | Kiểm tra LB, firewall, địa chỉ bind, security group và route thực |
| `localhost` lúc chọn IPv4 lúc chọn IPv6 | Hosts/DNS/resolver order và JVM props khác nhau | Dùng IP literals để test từng family, xem `getAllByName` |
| Đổi `System.setProperty("java.net.preferIPv6Addresses", ...)` giữa test không tác dụng | Property được xét ở JVM startup | Khởi động process riêng với `-D`; đừng dựa vào mutation runtime |
| IPv6 URL lỗi parse | Thiếu `[::1]` khi trộn IPv6 literal và port | Dùng `http://[::1]:port/` |
| Gửi UDP thành công nhưng không thấy bên nhận | UDP không hứa datagram đến; timeout/firewall/port mismatch | Dùng receive + payload match, kiểm tra sender/receiver/timeout |
| Test `selector.select(1200)` đôi lúc không nhận dữ liệu | Test chạy trên OS/CI quá tải hoặc bị chặn socket | Kiểm tra môi trường, thử timeout phù hợp, không suy diễn family thiếu |
| IPv6 link-local không đi được | Thiếu scope ID/interface phù hợp | Dùng `Inet6Address` với scope chính xác theo network interface |
| IPv4-mapped literal xuất ra `Inet4Address` | Java chuẩn hóa `::ffff:...` thành IPv4 | Đừng dùng `instanceof Inet6Address` trên mapped literal để kết luận OS mode |
| `SO_REUSEADDR` bật nhưng không bind được hai listeners | Socket port ownership và dual stack phụ thuộc OS | Thiết kế bind/port rõ, kiểm tra startup order và tránh tranh chấp cổng |

Cùng một ngoại lệ có thể có nhiều nguyên nhân; không kết luận “IPv6 hoàn toàn không tồn tại” chỉ vì một phép `bind` thất bại hoặc một test UDP không nhận gói.

## 16. Thiết kế service hỗ trợ dual stack bền vững

### 16.1. Chọn một trong hai kiến trúc

**Một IPv6 wildcard listener có khả năng dual stack:**

- Đơn giản về số lượng socket/port.
- Có thể nhận cả IPv4 và IPv6 nếu OS/JVM cho phép.
- Khó kiểm soát chính xác IPv6-only vs IPv4-mapped bằng **standard Java socket options**.
- Phải kiểm chứng bằng test thực tế trên đúng môi trường deploy và theo dõi regression khi đổi OS/container/JDK.

**Hai listeners tách biệt (`INET` và `INET6`):**

- Tách bạch chính sách địa chỉ, ACL, logging và đo đạc theo từng family.
- Không phụ thuộc assumption rằng IPv6 wildcard nhận IPv4.
- Có thể cần cổng riêng hoặc cấu hình IPv6-only ở hệ điều hành để tránh tranh chấp bind cùng port.
- Cần đồng bộ lifecycle, routing, health checks và metrics của hai listeners.

Không có lựa chọn duy nhất cho mọi ứng dụng. Nếu yêu cầu chính sách chính xác và tính di động cao, hãy chọn cách quản lý **hai path** hoặc dùng framework có cam kết rõ và kiểm thử trên các nền tảng mục tiêu.

### 16.2. Đừng rơi vào “IPv6 capable” nhưng IPv4-only ở ứng dụng

Một host có IPv6 interface không bảo đảm app đã:

- Resolve AAAA record đúng.
- Mở socket `INET6` thay vì `INET`.
- Bind địa chỉ `::` hoặc địa chỉ IPv6 cần thiết.
- Chấp nhận client IPv6 qua firewall/LB.
- Xử lý IPv6 URL literal có ngoặc vuông.
- Không hard-code IPv4 address parsing hoặc regex IPv4-only.
- Có cấu hình metrics, logs và ACL hoạt động với IPv6 (bao gồm scoped addresses).

Cần test **end-to-end** từ client thực, không chỉ chạy `InetAddress.getByName("::1")` một lần.

### 16.3. Dùng dữ liệu và ID an toàn trong log

Ghi kết quả probe (`ipv4_pass`, `ipv6_pass`, `dual_udp_accepts_ipv4`, loại lỗi), JDK version, network namespace và cấu hình JVM đã cho phép. Không cần log payload thật, token, private key hay request body. Nếu môi trường test nhiều tenant, tránh in thông tin interface/địa chỉ công khai ngoài phạm vi quyền truy cập cần thiết.

## 17. Checklist kiểm thử trước khi phát hành

- [ ] Kiểm tra IPv4 loopback `INET`: gửi/nhận gói thật và so byte chính xác.
- [ ] Kiểm tra IPv6 loopback `INET6`: không chỉ parse `::1`, phải bind/send/receive hoặc connect.
- [ ] Kiểm tra `INET` không thể dùng IPv6 address như IPv4.
- [ ] Kiểm tra IPv6 wildcard `::` và IPv4 sender trên cùng port để xác nhận dual stack socket nếu ứng dụng cần.
- [ ] Nếu production dùng TCP, thử riêng TCP IPv4/IPv6 connect + accept; UDP probe không thay thế.
- [ ] Truyền `java.net.preferIPv4Stack` và `java.net.preferIPv6Addresses` **tại JVM startup**, không đặt runtime giữa test.
- [ ] Kiểm tra A và AAAA records, resolver order và client fallback strategy nếu dùng hostname.
- [ ] Test từ client **trên mạng bên ngoài**, không chỉ loopback, qua LB/firewall/container.
- [ ] Kiểm tra IPv6-only OS policy và xung đột port khi dùng một hoặc hai listeners.
- [ ] Đảm bảo mọi bind wildcard tuân ACL và không vô tình expose dịch vụ ra ngoài.
- [ ] Test gracefully skipped/unavailable IPv6 trong CI không hỗ trợ; không che giấu lỗi trên môi trường có yêu cầu IPv6 bắt buộc.
- [ ] Dùng socket timeout/selector timeout trong test, port 0, đóng tất cả resources bằng `try-with-resources`.
- [ ] Không suy luận OS dual-stack từ `instanceof Inet6Address` hoặc từ giá trị của một system property đơn lẻ.
- [ ] Ghi lại JDK version, OS/network namespace và cấu hình thay đổi giữa các lần thử khi điều tra regression.

## 18. Tổng kết

**Protocol family là lựa chọn ở lúc tạo socket/channel, không phải chứng chỉ rằng dịch vụ đã đạt dual stack.** `StandardProtocolFamily.INET` dành cho IPv4; `INET6` dành cho IPv6 và trên một số hệ thống cho phép giao tiếp với IPv4 qua native dual-stack socket. **Bind `::1`, bind `::` và bind `127.0.0.1` có ý nghĩa khác nhau**, và việc OS hỗ trợ IPv6 không có nghĩa một listener dùng được cả hai họ.

Thực hành chắc chắn là **kiểm thử bốn tình huống** (IPv4, IPv6, mismatch, dual IPv6 wildcard + IPv4 sender), đổi `-Djava.net.preferIPv4Stack` và `-Djava.net.preferIPv6Addresses` trong **các JVM riêng**, quan sát kết quả thực từ socket và xác minh từ client ngoài môi trường loopback khi triển khai. Không suy diễn quá mức từ DNS order, raw address object hoặc một lần `send()` UDP.

### Tài liệu chính thức vẫn áp dụng

- [Oracle Java SE 26 — `StandardProtocolFamily`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/StandardProtocolFamily.html): `INET` và `INET6`.
- [Oracle Java SE 26 — `DatagramChannel`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/DatagramChannel.html), [`ServerSocketChannel`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/ServerSocketChannel.html), [`Selector`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/Selector.html).
- [Oracle Java SE 26 — Networking Properties](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/doc-files/net-properties.html): `java.net.preferIPv4Stack`, `java.net.preferIPv6Addresses` và hành vi JVM startup.
- [Oracle Java SE 26 — `InetAddress`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/InetAddress.html), [`Inet6Address`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/Inet6Address.html): IPv6 literal/scope, IPv4-mapped normalization.
- [Oracle Java SE 26 — `StandardSocketOptions`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/StandardSocketOptions.html): các socket options chuẩn; không có `IPV6_V6ONLY` portable.
