# StandardProtocolFamily.INET và INET6: chọn họ giao thức IPv4/IPv6 trong Java 15+

## 1. Mục tiêu và phạm vi

Khi lập trình mạng, câu hỏi **“socket này dùng IPv4 hay IPv6?”** khác với câu hỏi **“socket này dùng TCP hay UDP?”**. TCP và UDP là các giao thức vận chuyển, còn IPv4/IPv6 là những họ giao thức IP quyết định kiểu địa chỉ và cách hệ điều hành tạo socket nền.

Java biểu diễn họ giao thức bằng interface `java.net.ProtocolFamily` và các hằng trong enum **`java.net.StandardProtocolFamily`**:

~~~java
StandardProtocolFamily.INET  // Internet Protocol version 4 (IPv4)
StandardProtocolFamily.INET6 // Internet Protocol version 6 (IPv6)
~~~

Những hằng này dùng để chọn họ IP khi tạo các **NIO network channel**. Chủ đề thuộc nhóm **Protocol family** của **Java 15**, bởi Java 15 bổ sung những overload chọn `ProtocolFamily` cho `SocketChannel` và `ServerSocketChannel`, giúp code TCP chủ động chọn IPv4/IPv6. `DatagramChannel.open(ProtocolFamily)` đã tồn tại từ Java 7; không nên nói Java 15 mới phát minh `StandardProtocolFamily` hoặc IPv6 trong Java.

Các API này vẫn được hỗ trợ trên JDK hiện đại. Bài học giải thích khái niệm, cách dùng với **UDP/TCP**, DNS và dual-stack, các trường hợp lỗi, rồi cung cấp ví dụ Java 17+ đã biên dịch/chạy thử trên IPv4 và IPv6 loopback.

**Kết luận nhanh:** `INET` chọn socket họ **IPv4**; `INET6` chọn socket họ **IPv6**. Nhưng **`INET6` không tự hứa “IPv6-only”** trên mọi hệ điều hành: khả năng dual-stack và phạm vi chấp nhận địa chỉ IPv4 còn phụ thuộc nền tảng, cấu hình mạng và cách bind.

## 2. ProtocolFamily, địa chỉ IP, và transport protocol

### 2.1. ProtocolFamily là hợp đồng chọn họ socket

`ProtocolFamily` là một interface có phương thức `name()`, còn `StandardProtocolFamily` là enum chứa các họ chuẩn do Java hỗ trợ. Hai hằng dùng trong bài là:

| Hằng | Họ IP | Ví dụ địa chỉ loopback | Độ dài địa chỉ | Lớp địa chỉ tương ứng |
| --- | --- | --- | --- | --- |
| `StandardProtocolFamily.INET` | IPv4 | `127.0.0.1` | 32 bit | `Inet4Address` |
| `StandardProtocolFamily.INET6` | IPv6 | `::1` | 128 bit | `Inet6Address` |

`InetAddress` là kiểu cha biểu diễn địa chỉ; hai subtype `Inet4Address` và `Inet6Address` phân biệt hai phiên bản IP. `InetSocketAddress` kết hợp **địa chỉ IP và số cổng** để sử dụng trong `bind`/`connect`/`send`.

Ví dụ nhận diện literal IP không cần DNS hostname:

~~~java
InetAddress ipv4 = InetAddress.getByName("127.0.0.1");
InetAddress ipv6 = InetAddress.getByName("::1");

System.out.println(ipv4 instanceof Inet4Address); // true
System.out.println(ipv6 instanceof Inet6Address); // true
~~~

Đoạn trên chỉ phân tích địa chỉ literal thành đối tượng địa chỉ; **việc lấy được một `Inet6Address` không chứng minh máy có thể mở/bind IPv6 socket**. Khả năng sử dụng socket phụ thuộc hệ điều hành và cấu hình JVM.

### 2.2. INET và INET6 không có nghĩa là TCP và UDP

| Thao tác | Transport | Chọn IPv4 | Chọn IPv6 |
| --- | --- | --- | --- |
| `DatagramChannel.open(family)` | UDP datagrams | `DatagramChannel.open(INET)` | `DatagramChannel.open(INET6)` |
| `SocketChannel.open(family)` | TCP client | `SocketChannel.open(INET)` | `SocketChannel.open(INET6)` |
| `ServerSocketChannel.open(family)` | TCP server | `ServerSocketChannel.open(INET)` | `ServerSocketChannel.open(INET6)` |

Đây là ba **API khác nhau**. Tạo `DatagramChannel.open(INET6)` vẫn là **UDP qua IPv6**, không phải TCP. Tạo `SocketChannel.open(INET)` vẫn là **TCP qua IPv4**, không phải UDP.

`StandardProtocolFamily` còn có `UNIX` trên các Java hiện đại hỗ trợ Unix-domain sockets, nhưng đó là **họ khác**, không phải IPv4/IPv6; `DatagramChannel` không hỗ trợ Unix-domain sockets qua `open(UNIX)` theo API chính thức. Bài này tập trung chỉ vào `INET` và `INET6`.

## 3. Mốc phiên bản Java: kiến thức nào còn áp dụng?

- **Java 7:** `DatagramChannel.open(ProtocolFamily)` đã được cung cấp để chủ động chọn họ giao thức cho datagram channel; `StandardProtocolFamily.INET` và `INET6` cũng có từ giai đoạn này.
- **Java 15:** `SocketChannel.open(ProtocolFamily)` và `ServerSocketChannel.open(ProtocolFamily)` được bổ sung, cho phép chọn họ giao thức rõ ràng khi tạo TCP channel. Đây là phần trực tiếp đáng chú ý trong một module Java 15.
- **Java 15 / JEP 373:** phần triển khai bên trong `DatagramSocket`/`MulticastSocket` được thay đổi để đơn giản hóa bảo trì, nhưng **không thay đổi ý nghĩa cơ bản** của `INET`/`INET6` và cũng không yêu cầu di trú toàn bộ ứng dụng sang NIO.
- **Java 17 và các bản hiện hành:** các phương thức trên vẫn tồn tại. Ví dụ chạy độc lập bên dưới dùng `javac --release 17` để bảo đảm cú pháp/API tương thích Java 17+.

Không thay các API tiêu chuẩn này bằng thư viện lỗi thời hay API socket nội bộ của JDK. `ProtocolFamily`, `StandardProtocolFamily` và các overload `open(family)` là lựa chọn chính thức khi yêu cầu **chọn họ IP một cách tường minh**.

## 4. Chọn family khi mở UDP DatagramChannel

### 4.1. UDP/IPv4

~~~java
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.StandardProtocolFamily;
import java.nio.channels.DatagramChannel;

try (DatagramChannel receiver =
        DatagramChannel.open(StandardProtocolFamily.INET)) {
    InetAddress v4 = InetAddress.getByName("127.0.0.1");
    receiver.bind(new InetSocketAddress(v4, 0));
    // Có thể gọi receive(ByteBuffer) để đọc datagram.
}
~~~

Đây là một đoạn minh họa **không có `main`**. Chọn `INET` yêu cầu channel thuộc họ IPv4. `bind(new InetSocketAddress(v4, 0))` bind trên **IPv4 loopback** với cổng động (port `0` để hệ điều hành tự cấp). Dùng `receiver.getLocalAddress()` để xem địa chỉ/cổng thực tế sau khi bind.

### 4.2. UDP/IPv6

~~~java
InetAddress v6 = InetAddress.getByName("::1");
try (DatagramChannel receiver =
        DatagramChannel.open(StandardProtocolFamily.INET6)) {
    receiver.bind(new InetSocketAddress(v6, 0));
    // Có thể nhận datagram trên IPv6 loopback.
}
~~~

Đoạn minh họa này giả sử đã import `InetAddress`, `InetSocketAddress`, `StandardProtocolFamily` và `DatagramChannel` như trên. `::1` là **IPv6 loopback**, không phải địa chỉ Internet công cộng.

Tạo `INET6` có thể bị từ chối khi nền tảng không hỗ trợ IPv6; `DatagramChannel.open(INET6)` có thể ném `UnsupportedOperationException`. Nếu family tạo được nhưng bind/connect/send vẫn lỗi do mạng hoặc quyền của hệ điều hành, có thể nhận `IOException` hoặc subtype phù hợp.

### 4.3. DatagramChannel.open() không chỉ rõ family

~~~java
DatagramChannel defaultChannel = DatagramChannel.open();
~~~

Với factory không tham số, **family của socket nền là lựa chọn phụ thuộc nền tảng/cấu hình**, không nên coi mặc định là IPv4 hoặc IPv6-only. Trong ứng dụng cần kiểm soát chắc chắn **họ socket** hoặc dùng IP multicast, dùng `open(family)` và kiểm tra môi trường chạy.

Các thao tác `receive(ByteBuffer)` và `send(ByteBuffer, SocketAddress)` làm việc với **datagram**, không phải một stream TCP. Một `receive` có thể nhận ít bytes hơn datagram gốc nếu buffer không đủ; phần vượt quá bị **loại bỏ**, không được đọc tiếp ở lần sau. Phân biệt điều này với TCP `read(ByteBuffer)` có thể đọc từng phần từ một stream.

## 5. Chọn family khi mở TCP SocketChannel và ServerSocketChannel

### 5.1. TCP server và client chỉ dùng IPv4

~~~java
InetAddress v4 = InetAddress.getByName("127.0.0.1");

try (ServerSocketChannel server =
             ServerSocketChannel.open(StandardProtocolFamily.INET);
     SocketChannel client =
             SocketChannel.open(StandardProtocolFamily.INET)) {
    server.bind(new InetSocketAddress(v4, 0));
    client.connect(server.getLocalAddress());

    try (SocketChannel accepted = server.accept()) {
        // accepted là kết nối TCP từ client.
        // Có thể dùng read(ByteBuffer), write(ByteBuffer).
    }
}
~~~

Đây là đoạn minh họa cần các `import` tương ứng. Vì các channel mới mặc định **blocking**, `connect` và `accept` chờ theo ngữ nghĩa blocking. `accept` trả về `SocketChannel` phía server; nên đóng bằng `try-with-resources`. Cần có cơ chế timeout/non-blocking hoặc điều phối thread phù hợp nếu ứng dụng không được phép chờ vô hạn.

### 5.2. TCP chỉ định IPv6

~~~java
InetAddress v6 = InetAddress.getByName("::1");

try (ServerSocketChannel server =
             ServerSocketChannel.open(StandardProtocolFamily.INET6);
     SocketChannel client =
             SocketChannel.open(StandardProtocolFamily.INET6)) {
    server.bind(new InetSocketAddress(v6, 0));
    client.connect(server.getLocalAddress());
    try (SocketChannel accepted = server.accept()) {
        // Kết nối TCP chạy qua IPv6 loopback.
    }
}
~~~

Khác với constructor `SocketChannel.open(remoteAddress)`, overload `open(family)` **chưa tự kết nối**; cần gọi `connect(remote)`. Với `ServerSocketChannel.open(family)`, cần `bind(...)` trước khi `accept()`.

Cả hai overload `open(ProtocolFamily)` của TCP channel là **API từ Java 15**, không phải extension không chính thức. Việc chọn family không làm các socket tự hỗ trợ TLS hoặc tự xác thực peer; bảo mật và giao thức ứng dụng vẫn phải được thiết kế riêng.

## 6. INET6 có đồng nghĩa IPv6-only không?

**Không thể kết luận chỉ từ tên `INET6`.** Nó chọn **họ socket IPv6**, nhưng các hệ điều hành và JDK có thể cấu hình **dual-stack** để IPv6 socket cũng tiếp nhận hoặc gửi qua địa chỉ IPv4-mapped trong điều kiện thích hợp.

Các trường hợp thường gặp:

1. **INET/IPv4:** socket thuộc họ IPv4; không thể bind trực tiếp vào địa chỉ `::1` kiểu `Inet6Address`.
2. **INET6/IPv6:** hỗ trợ địa chỉ IPv6 như `::1` khi IPv6 khả dụng.
3. **INET6 dual-stack:** trên một số cấu hình, một IPv6 socket có thể giao tiếp với peer IPv4; điều này **không được bảo đảm chỉ bởi enum `INET6`**.
4. **INET6 chỉ IPv6:** có thể do cấu hình hệ điều hành, đặc tính nền tảng hoặc cách bind; không nên suy diễn từ kết quả trên một máy sang mọi máy.

**Bind vào `::1` và bind vào wildcard IPv6 `::` là hai thao tác khác nhau.** `::1` chỉ là loopback IPv6; wildcard dùng cho các giao diện được phép theo cấu hình mạng và có các hệ quả dual-stack khác nhau. Tương tự, `127.0.0.1` và `0.0.0.0` khác nhau: loopback và wildcard không thể dùng thay nhau khi suy luận phạm vi lắng nghe.

Nếu ứng dụng có yêu cầu bảo mật **bắt buộc chỉ chấp nhận IPv6**, cần kiểm tra chính sách bind/firewall/OS và xác minh thực tế rằng kết nối IPv4 không lọt qua; đừng giả định chỉ cần `open(INET6)` là đã đạt yêu cầu. Các socket option có thể phụ thuộc provider/nền tảng; **không giả định Java `StandardSocketOptions` cung cấp một công tắc `IPV6_V6ONLY` di động trên mọi JDK**.

## 7. Ví dụ chạy độc lập: UDP và TCP trên cả hai họ IP

Ví dụ thực hành:

- Xác nhận hai địa chỉ literal tạo đúng `Inet4Address` và `Inet6Address`.
- Kiểm thử UDP `DatagramChannel.open(INET)` trên `127.0.0.1` và TCP `ServerSocketChannel`/`SocketChannel` với `INET`.
- Cố tình bind địa chỉ IPv6 vào `DatagramChannel.open(INET)` để xác minh trường hợp **mismatch family**.
- Nếu IPv6 có thể mở/bind, thử cả UDP và TCP với `INET6` trên `::1`.
- Nếu IPv6 không khả dụng, in **`SKIP(...)`** cho hai phép IPv6 thay vì tuyên bố chương trình hỏng hoặc khẳng định đã kiểm thử IPv6 thành công.

Tạo file **`ProtocolFamilyDemo.java`** (lưu bằng UTF-8):

~~~java
import java.io.IOException;
import java.net.Inet4Address;
import java.net.Inet6Address;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.SocketAddress;
import java.net.StandardProtocolFamily;
import java.nio.ByteBuffer;
import java.nio.channels.DatagramChannel;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.channels.UnsupportedAddressTypeException;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.TimeUnit;

public class ProtocolFamilyDemo {
    private static int passed;

    private static void check(String label, boolean ok) {
        if (!ok) throw new AssertionError(label);
        passed++;
        System.out.println(label + "=PASS");
    }

    private static boolean udpEcho(
            StandardProtocolFamily family, InetAddress loopback) throws Exception {
        try (DatagramChannel receiver = DatagramChannel.open(family);
             DatagramChannel sender = DatagramChannel.open(family)) {
            receiver.bind(new InetSocketAddress(loopback, 0));
            sender.bind(new InetSocketAddress(loopback, 0));
            receiver.configureBlocking(false);

            byte[] message = "Hi".getBytes(StandardCharsets.UTF_8);
            int sent = sender.send(ByteBuffer.wrap(message), receiver.getLocalAddress());
            ByteBuffer dst = ByteBuffer.allocate(32);
            SocketAddress source = null;
            long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(3);
            while (source == null && System.nanoTime() < deadline) {
                source = receiver.receive(dst);
                if (source == null) Thread.sleep(5);
            }
            dst.flip();
            return source instanceof InetSocketAddress
                    && sent == message.length
                    && "Hi".equals(StandardCharsets.UTF_8.decode(dst).toString());
        }
    }

    private static boolean tcpEcho(
            StandardProtocolFamily family, InetAddress loopback) throws Exception {
        try (ServerSocketChannel server = ServerSocketChannel.open(family);
             SocketChannel client = SocketChannel.open(family)) {
            server.bind(new InetSocketAddress(loopback, 0));
            client.connect(server.getLocalAddress());
            try (SocketChannel accepted = server.accept()) {
                ByteBuffer src = ByteBuffer.wrap(new byte[]{79, 75});
                while (src.hasRemaining()) client.write(src);

                ByteBuffer dst = ByteBuffer.allocate(2);
                while (dst.hasRemaining()) {
                    if (accepted.read(dst) < 0) throw new IOException("Early EOF");
                }
                dst.flip();
                return "OK".equals(StandardCharsets.UTF_8.decode(dst).toString());
            }
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress v4 = InetAddress.getByName("127.0.0.1");
        InetAddress v6 = InetAddress.getByName("::1");
        check("ipv4LiteralType", v4 instanceof Inet4Address);
        check("ipv6LiteralType", v6 instanceof Inet6Address);
        check("udpInet", udpEcho(StandardProtocolFamily.INET, v4));
        check("tcpInet", tcpEcho(StandardProtocolFamily.INET, v4));

        try (DatagramChannel onlyV4 =
                     DatagramChannel.open(StandardProtocolFamily.INET)) {
            try {
                onlyV4.bind(new InetSocketAddress(v6, 0));
                throw new AssertionError("INET unexpectedly bound IPv6");
            } catch (UnsupportedAddressTypeException expected) {
                check("inetRejectsIpv6Bind", true);
            }
        }

        try {
            check("udpInet6", udpEcho(StandardProtocolFamily.INET6, v6));
        } catch (UnsupportedOperationException | IOException notAvailable) {
            System.out.println("udpInet6=SKIP(" + notAvailable.getClass().getSimpleName() + ")");
        }
        try {
            check("tcpInet6", tcpEcho(StandardProtocolFamily.INET6, v6));
        } catch (UnsupportedOperationException | IOException notAvailable) {
            System.out.println("tcpInet6=SKIP(" + notAvailable.getClass().getSimpleName() + ")");
        }
        System.out.println("TOTAL_PASS=" + passed);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 ProtocolFamilyDemo.java
java ProtocolFamilyDemo
~~~

**Stdout chính xác trên môi trường kiểm thử có IPv6 hoạt động**, đã biên dịch với `--release 17` và chạy trên JDK 24:

~~~text
ipv4LiteralType=PASS
ipv6LiteralType=PASS
udpInet=PASS
tcpInet=PASS
inetRejectsIpv6Bind=PASS
udpInet6=PASS
tcpInet6=PASS
TOTAL_PASS=7
~~~

Nếu máy không hỗ trợ IPv6, ví dụ có thể in:

~~~text
udpInet6=SKIP(UnsupportedOperationException)
tcpInet6=SKIP(UnsupportedOperationException)
~~~

hoặc in một loại `IOException` tương ứng cho mỗi phép IPv6. Các dòng này là **nhánh thay thế**, không phải stdout bắt buộc trong mọi môi trường. Khi cả hai nhánh IPv6 bị bỏ qua, tổng `TOTAL_PASS` bằng **5** chứ không phải 7. **`SKIP` không được tính là phép thử IPv6 thành công.**

### Các chi tiết kỹ thuật trong chương trình

**UDP:**

- `DatagramChannel.open(family)` tạo hai datagram channel cùng họ IP, bind vào đúng loại loopback.
- `port 0` cấp cổng trống động, nên không cần hard-code port cố định.
- Receiver chuyển sang **non-blocking** bằng `configureBlocking(false)`; khi chưa có gói, `receive(dst)` có thể trả `null`.
- Vòng lặp có **deadline 3 giây** để tránh chờ vô hạn trong thử nghiệm. Sau khi nhận, `ByteBuffer.flip()` chuyển buffer sang chế độ đọc.
- `send(ByteBuffer, SocketAddress)` gửi một datagram. Nếu buffer UDP quá nhỏ, dữ liệu vượt quá bị cắt chứ không tạo một phần stream để `receive` lần sau đọc tiếp.

**TCP:**

- `ServerSocketChannel.open(family)` và `SocketChannel.open(family)` tạo socket server/client thuộc họ đã chọn; `bind` gắn server với loopback/cổng động.
- `connect` rồi `accept` tạo hai đầu TCP. Chương trình gửi hai byte `'O'`/`'K'`.
- `SocketChannel.write`/`read` làm việc với **byte stream**, vì vậy các vòng lặp `while (hasRemaining())` xử lý trường hợp đọc/ghi một phần thay vì giả định một lời gọi luôn đủ.
- Cả server, client và accepted channel đều được đóng bằng `try-with-resources`.

**Thử không tương thích địa chỉ:**

- `DatagramChannel.open(INET)` cố bind `InetSocketAddress(::1, 0)`.
- Trong runtime được kiểm thử, thao tác bị từ chối bằng **`UnsupportedAddressTypeException`**.
- Ở môi trường/provider khác, lỗi liên quan thao tác mạng có thể khác về chi tiết, nhưng **không được thiết kế chương trình trông chờ IPv4 socket bind thành công vào IPv6 loopback**.

**Thử IPv6 tùy khả năng máy:**

- `UnsupportedOperationException` ở `open(INET6)` là dấu hiệu family không được hỗ trợ trên hệ thống.
- `IOException` trong bind/connect/send/receive còn có thể phản ánh chính sách mạng, quyền hoặc trục trặc I/O.
- Chương trình in `SKIP` để minh họa cách không giả định IPv6 luôn khả dụng. Trong CI production, nên **ghi lý do và quy định chính sách rõ**: nếu chức năng IPv6 là bắt buộc, `SKIP` phải được xem là không đạt điều kiện triển khai, không được chấp nhận im lặng.

## 8. DNS, localhost và các system property ảnh hưởng IPv4/IPv6

Khi xử lý một hostname thay vì địa chỉ số, DNS có thể cung cấp bản ghi **A (IPv4)** và **AAAA (IPv6)**. Cấu hình JVM có thể ảnh hưởng thứ tự địa chỉ được ưu tiên:

- **`java.net.preferIPv4Stack`:** mặc định là `false`. Nếu đặt `true` từ khi khởi động JVM, Java ưu tiên dùng socket chỉ IPv4 theo tài liệu Networking Properties; ứng dụng sẽ không giao tiếp được với **IPv6-only** hosts.
- **`java.net.preferIPv6Addresses`:** điều chỉnh ưu tiên/độ giữ thứ tự của địa chỉ khi tên máy có cả IPv4 và IPv6; **không tự biến một `INET` socket thành `INET6`** và không khắc phục việc OS chưa hỗ trợ IPv6.

Ví dụ cú pháp cấu hình từ command line:

~~~bash
java -Djava.net.preferIPv4Stack=true ProtocolFamilyDemo
~~~

Trong **Windows PowerShell**, có thể đặt đối số JVM trong dấu nháy để bảo toàn nguyên chuỗi:

~~~powershell
java '-Djava.net.preferIPv4Stack=true' ProtocolFamilyDemo
~~~

Không xem `java.net.preferIPv4Stack` là công tắc có thể đổi lại sau khi đã mở socket: các thuộc tính mạng loại này được JVM xét khi khởi động. Chạy trên một process mới khi muốn thử các cấu hình khác nhau.

**Đừng dùng `InetAddress.getByName("localhost")` để ngầm khẳng định sẽ nhận `127.0.0.1` hay `::1` trên mọi máy.** Thứ tự và loại địa chỉ có thể do hosts file, resolver, DNS và thuộc tính JVM quyết định. Ví dụ trong bài dùng **literal `"127.0.0.1"` và `"::1"`** để đặt mục tiêu kiểm thử rõ ràng, không phụ thuộc DNS.

Nếu bạn cần kết nối tới một dịch vụ có cả A và AAAA, cách tiếp cận robust là lấy danh sách địa chỉ phù hợp rồi thử các kết nối được phép theo chính sách/timeouts; **không chỉ thử một địa chỉ ngẫu nhiên** và không giả định OS sẽ chuyển giao thức tự động khi socket đã bị khóa family.

## 9. Multicast UDP: family phải phù hợp nhóm địa chỉ

`DatagramChannel.open(family)` đặc biệt hữu ích khi làm **IP multicast**. Javadoc yêu cầu chọn family phù hợp với địa chỉ multicast group mà channel sẽ join.

| Multicast group | Họ multicast IP | Channel dùng |
| --- | --- | --- |
| IPv4 group (thuộc `224.0.0.0/4`) | IPv4 multicast | `DatagramChannel.open(StandardProtocolFamily.INET)` |
| IPv6 group (thuộc `ff00::/8`) | IPv6 multicast | `DatagramChannel.open(StandardProtocolFamily.INET6)` |

Để join multicast thật, còn cần một `NetworkInterface` tương thích và cấu hình membership bằng `MulticastChannel.join(...)`; chỉ mở channel bằng `INET`/`INET6` **chưa tham gia nhóm multicast nào**. Các vấn đề về giao diện mạng, multicast scope, firewall và router vẫn phải được xử lý.

Vì multicast phụ thuộc cấu hình mạng và quyền của host, bài kiểm thử runnable **không** yêu cầu multicast hoạt động. Tính di động của kiểm thử được cải thiện nhờ dùng hai địa chỉ **unicast loopback** để chứng minh riêng việc chọn IPv4/IPv6 family.

## 10. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| `DatagramChannel.open(INET6)` ném `UnsupportedOperationException` | IPv6 không được nền tảng/JVM hỗ trợ hoặc bị vô hiệu hóa | Kiểm tra hỗ trợ IPv6 và cấu hình JVM/OS; nếu IPv6 bắt buộc, không âm thầm fallback sang IPv4. |
| `INET` socket không bind được `::1` | Family IPv4 không tương thích `Inet6Address` | Dùng `INET6` cho IPv6, hoặc địa chỉ IPv4 phù hợp cho `INET`. |
| Tạo `INET6` thành công nhưng kết nối vẫn lỗi | IPv6 route/firewall/peer/listener không phù hợp, dù family có sẵn | Kiểm tra bind thực tế, địa chỉ/port, OS network và exception cụ thể. |
| `INET6` socket nhận được một số kết nối IPv4 | Nền tảng có thể dùng dual-stack/IPv4-mapped | Đừng suy diễn IPv6-only; kiểm tra chính sách bảo mật và thực nghiệm dual-stack. |
| `localhost` được phân giải khác kỳ vọng | Resolver/hosts/JVM ưu tiên IPv4 hoặc IPv6 khác nhau | Dùng địa chỉ literal trong test; với host thật, xử lý danh sách A/AAAA có chủ đích. |
| `getByName("::1")` thành công nhưng `open(INET6)` thất bại | Phân tích literal không chứng minh hỗ trợ IPv6 socket | Tách kiểm tra địa chỉ với kiểm tra mạng thực. |
| `BindException: Address already in use` | Cổng cố định đã bị tiến trình khác bind, hoặc chính sách reuse | Dùng cổng `0` trong test; với server thật, quản lý port/reuse rõ ràng. |
| TCP `SocketChannel.open(INET6)` không kết nối được server IPv4-only | Family/địa chỉ không phù hợp, dual-stack khác nhau giữa OS | Dùng family/địa chỉ khớp peer hoặc thiết kế listener tương thích cho từng family. |
| UDP `receive` trả `null` trong test | `DatagramChannel` đặt non-blocking và chưa có datagram | Dùng `Selector`/vòng chờ có deadline hoặc blocking theo yêu cầu. |
| TCP đọc ít byte hơn đã gửi | TCP là stream và `read` có thể trả một phần | Lặp tới khi đủ bytes theo framing/length của giao thức. |
| UDP nhận thiếu bytes | Buffer quá nhỏ khiến phần dư datagram bị loại bỏ | Chọn kích thước buffer và giới hạn payload của giao thức; không coi UDP như TCP stream. |
| Dùng `Inet6Address` để xác định số cổng | `Inet6Address` chỉ chứa địa chỉ IP, không có port | Sử dụng `InetSocketAddress(ip, port)`. |
| Chọn `INET6` nhưng không join được multicast IPv4 group | Family/group không phù hợp | Chọn `INET` cho IPv4 multicast, `INET6` cho IPv6 multicast. |

### Những giả định không nên đưa vào mã production

- “Nếu `INET6` mở thành công thì socket chỉ nhận IPv6” — **không đủ căn cứ**.
- “`INET` là TCP và `INET6` là UDP” — **sai lớp khái niệm**.
- “Java 15 mới có `DatagramChannel.open(ProtocolFamily)`” — **sai mốc phiên bản**.
- “`DatagramChannel.open()` không tham số luôn dùng IPv4” — **không được API bảo đảm**.
- “Địa chỉ IPv6 là hai IPv4 nối vào nhau” — **không đúng mô hình biểu diễn**.
- “Thử trên loopback chứng minh mọi router/firewall đều hỗ trợ IPv6” — **không đúng phạm vi kiểm thử**.
- “Chỉ đổi `java.net.preferIPv6Addresses` trong code thì socket `INET` chuyển sang IPv6” — **không đúng**.
- “Java `StandardSocketOptions` luôn có option `IPV6_V6ONLY` để bật/tắt dual-stack” — **không có hợp đồng di động như vậy trong bộ StandardSocketOptions được dùng ở ví dụ**.

## 11. Checklist để đưa vào kiểm thử dự án

1. **Xác định mục tiêu:** ứng dụng cần IPv4-only, IPv6-only hay dual-stack? Cần UDP hay TCP?
2. **Chọn family rõ ràng:** dùng `DatagramChannel.open(INET/INET6)` hoặc TCP `SocketChannel`/`ServerSocketChannel.open(family)` khi family có ý nghĩa hợp đồng.
3. **Bind đúng địa chỉ:** `Inet4Address` với IPv4 loopback/wildcard tương ứng; `Inet6Address` với IPv6 loopback/wildcard tương ứng.
4. **Không phụ thuộc resolver trong unit test:** dùng `127.0.0.1` và `::1`; tách bài test DNS/hostname thành nhóm khác.
5. **Có xử lý IPv6 unavailable:** `UnsupportedOperationException`/`IOException` phải được phân loại; phân biệt SKIP cho môi trường tùy chọn với FAIL khi IPv6 bắt buộc.
6. **Kiểm thử ít nhất hai hướng UDP/TCP nếu chương trình dùng cả hai:** đừng lấy thành công UDP để kết luận TCP listener chắc chắn hoạt động.
7. **Kiểm thử mismatch:** thử gia đình địa chỉ không tương thích và kiểm tra chương trình từ chối thay vì im lặng thay đổi family.
8. **Đối chiếu dual-stack thực tế:** với listener `INET6`, cần kiểm chứng riêng khả năng nhận IPv4 theo chính sách, bind và OS.
9. **Quản lý tài nguyên:** luôn đóng channel bằng `try-with-resources`; dùng cổng `0` cho test; timeout/deadline để tránh treo CI.
10. **Xác minh giao thức ứng dụng:** TCP cần framing, UDP cần thiết kế loss/retry nếu cần; việc chọn IP family không tạo tính tin cậy hay bảo mật.
11. **Theo dõi môi trường triển khai:** phiên bản JDK, OS, IPv6 enabled, thuộc tính `java.net.preferIPv4Stack` và `java.net.preferIPv6Addresses`, cấu hình container/firewall.
12. **Giới hạn phạm vi kết luận:** chạy loopback thành công là bằng chứng local, không chứng minh endpoint Internet bên ngoài có DNS/routing/ACL đúng.

## 12. Tài liệu chính thức còn áp dụng

- [Java SE 26 — StandardProtocolFamily](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/StandardProtocolFamily.html): `INET`, `INET6` và các họ giao thức chuẩn.
- [Java SE 26 — ProtocolFamily](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/ProtocolFamily.html): hợp đồng tên của protocol family.
- [Java SE 26 — DatagramChannel](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/DatagramChannel.html): `open(ProtocolFamily)` (từ Java 7), family mặc định, multicast, `receive` và `send`.
- [Java SE 26 — SocketChannel](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/SocketChannel.html): `open(ProtocolFamily)` (từ Java 15), `connect`, `read`, `write`.
- [Java SE 26 — ServerSocketChannel](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/ServerSocketChannel.html): `open(ProtocolFamily)` (từ Java 15), `bind`, `accept`.
- [Java SE 26 — Inet4Address / Inet6Address](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/InetAddress.html): địa chỉ IP và các dạng literal/hostname.
- [Java SE 26 — Networking Properties](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/doc-files/net-properties.html): `java.net.preferIPv4Stack`, `java.net.preferIPv6Addresses`.
- [JEP 373 — Reimplement the Legacy Datagram Socket API](https://openjdk.org/jeps/373): mốc Java 15 với triển khai UDP socket bên trong; không phải thay đổi ý nghĩa của enum family.

**Kết luận:** `StandardProtocolFamily.INET` biểu thị **IPv4**, `INET6` biểu thị **IPv6**. Chúng chọn họ địa chỉ khi tạo **TCP hoặc UDP channel**, còn kiểu transport do `SocketChannel`/`ServerSocketChannel` hay `DatagramChannel` xác định. Kiểm thử đúng family phải bao gồm loại địa chỉ, thao tác bind/connect/send/receive, khả năng IPv6 của môi trường và chính sách dual-stack — không chỉ so sánh tên enum.