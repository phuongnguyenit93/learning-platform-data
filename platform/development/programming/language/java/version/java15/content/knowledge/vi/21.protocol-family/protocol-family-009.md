# Giữ tương thích hệ điều hành bằng kiểm tra khả năng thực tế trong Java 15+: Protocol family và UDP

## 1. Mục tiêu

Khi viết ứng dụng mạng với Java NIO, một lựa chọn tưởng chừng đơn giản như **`StandardProtocolFamily.INET` hay `INET6`** có thể cho kết quả khác nhau trên Windows, Linux, macOS, máy ảo, container, VPN và các môi trường cloud. Ngay cả hai máy dùng **cùng JDK** cũng có thể khác nhau vì IPv6 bị tắt, interface không có địa chỉ phù hợp, firewall chặn lưu lượng, chính sách kernel hoặc socket option không được hỗ trợ.

Cách xây dựng chương trình **portable** không phải là viết bảng luật “nếu OS là Windows thì…, nếu Linux thì…”. Cách bền vững hơn là **kiểm tra khả năng thật ở đúng cấp độ cần dùng**, xử lý kết quả trong runtime, và có chiến lược fallback **không làm thay đổi ý nghĩa của giao thức**.

Trong ngữ cảnh **Protocol family** của Java 15+, bài học giúp bạn:

1. Phân biệt **platform, protocol family, address family, socket options, network interface** và **kết nối thực sự có truyền dữ liệu**.
2. Mở `DatagramChannel` với `StandardProtocolFamily.INET` (IPv4) hoặc `INET6` (IPv6) thay vì đoán mặc định.
3. Nhận ra `DatagramChannel.open()` **không chỉ rõ family** nên tùy platform/cấu hình; multicast nên chọn family theo địa chỉ group.
4. Dùng `NetworkChannel.supportedOptions()` để **khảo sát tùy chọn**, rồi kiểm tra `setOption(...)`/`getOption(...)` thay vì mặc định mọi option đều hoạt động.
5. Thử **bind và send/receive loopback thực tế** để biết IPv4/IPv6 đang vận hành được trong môi trường hiện tại.
6. Kiểm tra `NetworkInterface` và thử `MembershipKey` theo cơ chế tự nguyện khi ứng dụng cần multicast.
7. Phân loại **không hỗ trợ**, **có hỗ trợ nhưng lỗi cấu hình**, **không nhận được packet**, và **lỗi lập trình**; biết khi nào fallback hợp lý, khi nào phải thất bại rõ ràng.
8. Viết kiểm thử và quan sát production có thể chẩn đoán, không phụ thuộc tên OS hoặc tên adapter cố định.

Bài chỉ sử dụng các API Java SE **chính thức vẫn tồn tại trong Java hiện đại**. Đoạn code biên dịch được với `--release 15`, nhưng môi trường triển khai mới nên dùng JDK/JVM đang được hỗ trợ. Không dùng `sun.*`, API nội bộ, `SecurityManager` đã lỗi thời hoặc lời khuyên giả định một platform cụ thể sẽ mãi giữ nguyên hành vi.

## 2. “Có hỗ trợ” phải được chia thành nhiều tầng

Một sai lầm phổ biến là thấy `open(INET6)` trả về channel và kết luận “IPv6 hoàn toàn hoạt động”. Trên thực tế có ít nhất **năm tầng**:

| Tầng | Điều cần biết | Cách quan sát | Điều **chưa thể** kết luận |
| --- | --- | --- | --- |
| **JDK API** | Class và method có tồn tại? | `DatagramChannel.open(ProtocolFamily)`, `StandardProtocolFamily.INET6` | OS đã bật IPv6? |
| **Socket family** | OS/JVM mở được socket family này? | Thử `DatagramChannel.open(INET6)` | Bind được mọi địa chỉ hoặc có route? |
| **Local bind** | Có thể gắn socket vào địa chỉ/cổng local? | Thử `bind(new InetSocketAddress(loopback, 0))` | Packet sẽ tới được peer khác? |
| **Option/interface** | Tùy chọn và interface sử dụng được? | `supportedOptions()`, `setOption`, `isUp`, `supportsMulticast`, `join` | Toàn bộ mạng đã forward multicast? |
| **End-to-end behavior** | Datagram được gửi và nhận với đúng yêu cầu? | Loopback test, integration test giữa hai nodes, auth/protocol check | Lần sau luôn thành công; UDP vẫn có packet loss |

**Capability discovery chỉ có ý nghĩa tại nơi sẽ dùng nó.** Ví dụ: `NetworkInterface.supportsMulticast()` thông báo interface được OS báo hỗ trợ multicast, nhưng **không** chứng minh switch sẽ forward group, firewall cho qua hay một host khác đã nhận được gói.

Tương tự, việc `setOption(SO_REUSEPORT, true)` không ném lỗi **không** chứng minh mọi socket cùng port sẽ nhận bản tin theo cách ứng dụng muốn trên mọi OS. Cần thử **đúng hành vi** mà ứng dụng dựa vào.

### Nhớ ngắn gọn

- **Có API** ≠ **có socket hỗ trợ**.
- **Mở socket được** ≠ **bind được địa chỉ cần thiết**.
- **Bind được** ≠ **gửi/nhận được packet**.
- **Option có trong danh sách** ≠ **set thành công với giá trị đó**.
- **Option set thành công** ≠ **hành vi network đã được đảm bảo**.
- **Multicast join thành công** ≠ **các receiver thực sự nhận được datagram**.

## 3. Protocol family: `INET`, `INET6` và mặc định

`java.net.StandardProtocolFamily` cung cấp các tên family cần dùng trong bài:

| Family | Mục đích | Dùng với địa chỉ | Cách mở UDP channel |
| --- | --- | --- | --- |
| `INET` | Internet Protocol IPv4 | `Inet4Address` | `DatagramChannel.open(StandardProtocolFamily.INET)` |
| `INET6` | Internet Protocol IPv6 | `Inet6Address` | `DatagramChannel.open(StandardProtocolFamily.INET6)` |

Ví dụ:

```java
try (DatagramChannel ipv4 =
        DatagramChannel.open(StandardProtocolFamily.INET)) {
    // Các thao tác UDP IPv4.
}

try (DatagramChannel ipv6 =
        DatagramChannel.open(StandardProtocolFamily.INET6)) {
    // Các thao tác UDP IPv6.
}
```

Đây là đoạn minh họa nằm trong một method có `throws IOException`, cần import `java.net.StandardProtocolFamily` và `java.nio.channels.DatagramChannel`. Hai lệnh phải được xử lý **độc lập** nếu chương trình cần xác định trường hợp một family khả dụng còn family kia không.

### 3.1. `DatagramChannel.open()` không truyền family

`DatagramChannel.open()` yêu cầu provider tạo channel bằng **protocol family do platform/cấu hình quyết định**; Javadoc nói rõ family thực tế không được đặc tả cố định. Không sử dụng kết quả của `open()` để khẳng định “JVM mặc định luôn dùng IPv6” hoặc “IPv4 sẽ luôn dùng được”.

Với ứng dụng chủ động chọn IPv4/IPv6, **nên truyền family tường minh**. Với **multicast**, Javadoc đặc biệt khuyến nghị family của channel phải tương ứng với address family của group tham gia; ví dụ group `239.255.42.99` thuộc IPv4 nên mở `INET`.

### 3.2. `INET6` không được bảo đảm trên mọi môi trường

`DatagramChannel.open(StandardProtocolFamily.INET6)` có thể ném `UnsupportedOperationException` khi IPv6 không có/không được bật. `IOException` có thể xuất hiện do lỗi tạo socket. Ngay cả khi mở thành công, bind tới một địa chỉ cụ thể vẫn có thể thất bại vì địa chỉ đó không được hệ điều hành cấu hình hoặc policy không cho.

**Đừng kiểm tra bằng cách chỉ xem chuỗi `os.name`.** Một máy Linux có thể tắt IPv6 trong namespace của container; một Windows host có thể bật IPv6 nhưng ứng dụng chạy với networking policy hạn chế; một VM có thể có IPv6 loopback nhưng không có IPv6 route ra ngoài. Tên OS không xác định được trạng thái ấy.

### 3.3. Dual stack IPv4/IPv6 không phải hợp đồng portable

Trên một số hệ thống, một socket IPv6 có thể chấp nhận một số lưu lượng IPv4 qua cơ chế **dual stack/IPv4-mapped IPv6 addresses**, nhưng điều này phụ thuộc native stack, JDK configuration và socket behavior. **Không** mặc định rằng channel `INET6` sẽ nhận/gửi IPv4 ở mọi OS.

Nếu dịch vụ cần cả hai protocol families, có thể:

- Khảo sát **cả `INET` lẫn `INET6`** và chọn family dựa trên địa chỉ đích được cấu hình/resolve.
- Dùng hai sockets/channels riêng khi kiến trúc, OS và port binding policy cho phép.
- Phân loại rõ mục tiêu có thể “IPv4-only fallback” hay bắt buộc IPv6.
- Test chính xác cách bind wildcard/loopback/remote và behavior port reuse trong môi trường vận hành.

Không dùng hành vi dual stack tình cờ làm điều kiện duy nhất cho khả năng tương tác dài hạn.

## 4. Đừng đánh giá IPv6 bằng hostname `localhost` một cách mơ hồ

`InetAddress.getByName("localhost")` có thể trả về `127.0.0.1` hoặc `::1` tùy host resolution, cấu hình IPv4/IPv6 và thứ tự địa chỉ được ưu tiên. Nếu bạn muốn **kiểm thử cụ thể** từng family, hãy chọn địa chỉ bằng cấu trúc rõ ràng:

```java
InetAddress v4Loopback =
        InetAddress.getByAddress(new byte[] {127, 0, 0, 1});

byte[] rawV6 = new byte[16];
rawV6[15] = 1;
InetAddress v6Loopback = InetAddress.getByAddress(rawV6);
```

Đây là đoạn minh họa trong một method có `throws UnknownHostException` hoặc `throws Exception`. Tạo `InetAddress` **không** chứng minh OS có thể bind/gửi vào địa chỉ ấy. Phải thử socket thật.

### 4.1. `InetAddress.getLoopbackAddress()` tiện nhưng không thay thế test family

API `InetAddress.getLoopbackAddress()` lấy loopback thích hợp cho hệ thống, phù hợp khi **không cần lựa chọn rõ IPv4/IPv6**. Nhưng bài này cần so sánh từng family độc lập, nên dùng explicit `127.0.0.1` và `::1`.

### 4.2. Cấu hình JVM liên quan IPv4/IPv6

Một số JVM networking properties còn hiện hành:

- **`java.net.preferIPv4Stack`:** khi bật ở startup, chọn IPv4-only stack trong những trường hợp áp dụng; không được kỳ vọng vẫn truy cập IPv6-only host qua stack này.
- **`java.net.preferIPv6Addresses`:** thay thứ tự ưu tiên địa chỉ khi hostname có cả A và AAAA records (giá trị thường dùng là `true`, `false` hoặc `system` trên JDK hiện đại). Đây là **policy lựa chọn địa chỉ của resolver**, không phải thao tác tự mở tuyến IPv6 trong OS.
- Các property này được **đọc khi JVM khởi động** theo tài liệu networking properties. Dùng `-D...` ở lệnh `java` khi cần; đừng trông chờ `System.setProperty` trong lúc chương trình đang chạy sẽ làm thay đổi mọi socket đã tạo.

Ví dụ để **chạy một phép thử riêng**:

```bash
java -Djava.net.preferIPv4Stack=true UdpFamilyProbe
```

Lệnh này chủ động thay cấu hình JVM cho một lần chạy, không phải khuyến nghị luôn bật IPv4-only. Nếu ứng dụng buộc hỗ trợ IPv6, đừng sử dụng property trên như cách “chữa” một lỗi tạm thời rồi bỏ qua yêu cầu giao thức.

## 5. `supportedOptions()`: khảo sát option trước khi dùng

`java.nio.channels.NetworkChannel.supportedOptions()` trả về tập `Set<SocketOption<?>>` được channel khai báo hỗ trợ. `DatagramChannel` triển khai `NetworkChannel` nên dùng được API này.

Ví dụ với `SO_REUSEPORT`:

```java
try (DatagramChannel channel =
        DatagramChannel.open(StandardProtocolFamily.INET)) {
    boolean listed = channel.supportedOptions()
            .contains(StandardSocketOptions.SO_REUSEPORT);

    if (listed) {
        channel.setOption(StandardSocketOptions.SO_REUSEPORT, true);
    }
}
```

Đây là đoạn minh họa, cần import `java.net.StandardProtocolFamily`, `java.net.StandardSocketOptions`, `java.nio.channels.DatagramChannel` và xử lý exception từ `setOption`.

**Cực kỳ quan trọng:** `supportedOptions()` chỉ là một **capability hint** ở cấp channel/provider. Ngay cả khi listed, một giá trị cụ thể vẫn có thể bị từ chối do quyền, trạng thái socket, OS policy hoặc option đó không được triển khai như ứng dụng kỳ vọng. Vì vậy:

1. Kiểm tra `supportedOptions().contains(option)`.
2. Thử `setOption(option, value)` **trong đúng thứ tự/trạng thái**; một số option cần thiết lập **trước `bind`**.
3. Khi cần, đọc `getOption(option)` để xem giá trị được báo lại.
4. Chạy integration test cho **hành vi** phụ thuộc option (ví dụ nhiều listeners cùng bind một port) thay vì chỉ dừng ở bước 1–3.
5. Nếu option là **tùy chọn tăng hiệu suất**, có thể disable chức năng ấy khi không hỗ trợ. Nếu option là **điều kiện bắt buộc để đúng giao thức**, phải fail rõ ràng hoặc chọn một thiết kế tương đương đã kiểm thử.

### 5.1. Những option có ý nghĩa với UDP

| Socket option | Ý nghĩa | Kiểm tra cần làm |
| --- | --- | --- |
| `SO_RCVBUF` | Kích thước buffer nhận theo gợi ý cho OS | `getOption` sau `setOption`, kiểm tra packet loss dưới tải |
| `SO_SNDBUF` | Buffer gửi theo gợi ý | Kiểm tra giá trị OS trả và hiệu năng thực tế |
| `SO_REUSEADDR` | Cho phép một số hình thức tái sử dụng địa chỉ/port | Đặt **trước bind** khi multicast có nhiều receiver; OS semantics có thể khác |
| `SO_REUSEPORT` | Tính năng tái sử dụng port có thể không được hỗ trợ | Có tên chuẩn không đồng nghĩa platform hỗ trợ; kiểm tra danh sách, set và thử bind thực tế |
| `SO_BROADCAST` | Cho phép gửi UDP broadcast khi network hỗ trợ | Chỉ cần cho broadcast, **không thay `join` của multicast** |
| `IP_TOS` | Traffic class/Type of Service ở IP layer | Có thể bị OS/router làm tròn hoặc thay đổi; không coi đây là quality-of-service guarantee |
| `IP_MULTICAST_IF` | Interface **gửi** multicast | Chọn đúng NIC; receiver join phải thực hiện riêng |
| `IP_MULTICAST_TTL` | Time-to-live/hop limit cho multicast | Đặt phạm vi hợp lý; không phải security boundary |
| `IP_MULTICAST_LOOP` | Yêu cầu local multicast loopback | Tác dụng phụ thuộc platform; không bảo đảm self-delivery |

Không sử dụng `SO_REUSEPORT` mặc định chỉ vì tên option hiện diện trong `StandardSocketOptions`. Trong môi trường kiểm thử minh họa JDK 24/Windows, `supportedOptions()` của một IPv4 `DatagramChannel` **không liệt kê `SO_REUSEPORT`**, nên ví dụ bỏ qua thao tác set. Trên một số Linux, option có thể được khai báo/cho set, nhưng cách phân phối datagrams giữa listeners vẫn cần thử.

### 5.2. Ngoại lệ phải hiểu đúng

- `UnsupportedOperationException`: family/option không được hỗ trợ, thường là tín hiệu để thử phương án tương thích **nếu yêu cầu cho phép**.
- `IllegalArgumentException`: giá trị option hoặc địa chỉ không phù hợp; thường phản ánh **đầu vào sai** chứ không phải cứ fallback âm thầm.
- `IOException`: OS hoặc networking layer báo lỗi; có thể là permission, resource, bind conflict hay route; cần log metadata và phân loại trước khi chọn giải pháp.
- `ClosedChannelException`: code thao tác với channel đã đóng; cần sửa lifecycle, không phải đổi IP family để “chữa”.
- `SecurityException`: quyền hoặc policy môi trường từ chối thao tác; không giải quyết bằng cách bỏ hết kiểm soát truy cập.

**Cẩn thận:** không phải mọi lỗi có từ `setOption` đều nói rằng cả family không dùng được. Ví dụ một performance option không hỗ trợ không nhất thiết khiến chức năng UDP cơ bản thất bại.

## 6. Kiểm tra hành vi bằng loopback chứ không chỉ bằng API discovery

Khi một dịch vụ bắt buộc IPv6, **thành công khi open** chưa đủ. Một phép thử thực tế có thể thực hiện như sau:

```text
open(channel, family)
    |
bind(receiver, loopbackAddressOfFamily, port=0)
    |
open(sender, family)
    |
send("probe", receiver.localAddress)
    |
receive() với deadline / Selector
    |
decode đúng số byte
    |
PASS nếu nhận đúng "probe"; ngược lại report không dùng được
```

Trong phép thử này:

- `port=0` cho phép OS tự chọn cổng tạm, tránh hard-code một port có thể đang bị chiếm.
- Dùng địa chỉ `127.0.0.1` hoặc `::1` để không phụ thuộc DNS hay server bên ngoài.
- Dùng `Selector.select(timeout)` để không bị treo vô hạn nếu packet không về.
- Kết quả “không nhận được” là **tín hiệu môi trường**, không tự suy ra IPv6 hoàn toàn không tồn tại: có thể do policy, timeout, packet loss, race hoặc lỗi xử lý buffer.
- Loopback thành công **không chứng minh** kết nối remote Internet, multicast routing hay firewall giữa hai máy hoạt động. Cần integration test riêng cho luồng thực tế.

Một TCP connection test đến server đang chạy có ý nghĩa khác; ở đây chúng ta kiểm tra **UDP datagram**, không phải TCP handshake.

## 7. Chương trình đầy đủ Java 15+: probe IPv4/IPv6, option và multicast

Chương trình `UdpFamilyProbe.java` có ba chức năng:

- **Mặc định:** thử `INET` và `INET6` bằng **open → bind loopback → send → receive**; in kết quả có căn cứ vào chạy thật.
- **Mặc định:** khảo sát `SO_REUSEPORT` và chỉ thử set khi channel nói có hỗ trợ.
- **Tùy chọn với một argument:** lấy `NetworkInterface` từ tên do người chạy cung cấp, kiểm tra `isUp`/`supportsMulticast`/IPv4 address, thử join/drop một nhóm multicast IPv4 **không gửi datagram**.

Không có hard-coded tên OS hoặc network interface. Một số kết quả **phụ thuộc platform**, vì chính đó là điều bài đang đo.

### 7.1. File `UdpFamilyProbe.java`

```java
import java.io.IOException;
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.NetworkInterface;
import java.net.StandardProtocolFamily;
import java.net.StandardSocketOptions;
import java.nio.ByteBuffer;
import java.nio.channels.DatagramChannel;
import java.nio.channels.MembershipKey;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.charset.StandardCharsets;
import java.util.Collections;

public class UdpFamilyProbe {
    static void probe(StandardProtocolFamily family, InetAddress loopback) {
        String label = family.name();
        try (DatagramChannel receiver = DatagramChannel.open(family);
             DatagramChannel sender = DatagramChannel.open(family);
             Selector selector = Selector.open()) {

            receiver.bind(new InetSocketAddress(loopback, 0));
            receiver.configureBlocking(false);
            receiver.register(selector, SelectionKey.OP_READ);

            ByteBuffer output = StandardCharsets.UTF_8.encode("probe");
            int sent = sender.send(output, receiver.getLocalAddress());

            ByteBuffer input = ByteBuffer.allocate(32);
            String result = "NO_DATAGRAM";
            if (selector.select(1500) > 0 &&
                    receiver.receive(input) != null) {
                input.flip();
                result = "probe".equals(
                        StandardCharsets.UTF_8.decode(input).toString())
                        ? "OK" : "WRONG_PAYLOAD";
            }
            System.out.println(label + ".openBind=OK");
            System.out.println(label + ".sentBytes=" + sent);
            System.out.println(label + ".loopbackReceive=" + result);
        } catch (UnsupportedOperationException | IOException | SecurityException ex) {
            System.out.println(label + ".probe=UNAVAILABLE:"
                    + ex.getClass().getSimpleName());
        }
    }

    static void optionProbe() {
        try (DatagramChannel channel = DatagramChannel.open(
                StandardProtocolFamily.INET)) {
            boolean advertised = channel.supportedOptions()
                    .contains(StandardSocketOptions.SO_REUSEPORT);
            System.out.println("reusePortAdvertised=" + advertised);
            if (!advertised) {
                System.out.println("reusePortSet=SKIPPED");
                return;
            }
            try {
                channel.setOption(StandardSocketOptions.SO_REUSEPORT, true);
                System.out.println("reusePortSet="
                        + channel.getOption(StandardSocketOptions.SO_REUSEPORT));
            } catch (UnsupportedOperationException | IOException
                     | IllegalArgumentException e) {
                System.out.println("reusePortSet=FAILED:"
                        + e.getClass().getSimpleName());
            }
        } catch (UnsupportedOperationException | IOException
                 | SecurityException ex) {
            System.out.println("reusePortProbe=UNAVAILABLE:"
                    + ex.getClass().getSimpleName());
        }
    }

    static void multicastProbe(String interfaceName) throws Exception {
        NetworkInterface ni = NetworkInterface.getByName(interfaceName);
        if (ni == null || !ni.isUp() || !ni.supportsMulticast()) {
            System.out.println("multicast=INTERFACE_UNAVAILABLE");
            return;
        }
        boolean hasIPv4 = Collections.list(ni.getInetAddresses()).stream()
                .anyMatch(a -> a instanceof Inet4Address);
        if (!hasIPv4) {
            System.out.println("multicast=NO_IPV4_ADDRESS");
            return;
        }
        InetAddress group = InetAddress.getByName("239.255.42.99");
        try (DatagramChannel channel = DatagramChannel.open(
                StandardProtocolFamily.INET)) {
            channel.setOption(StandardSocketOptions.SO_REUSEADDR, true);
            channel.bind(new InetSocketAddress(0));
            MembershipKey key = channel.join(group, ni);
            try {
                System.out.println("multicastJoin=" + key.isValid());
            } finally {
                key.drop();
                System.out.println("multicastDropped=" + !key.isValid());
            }
        } catch (UnsupportedOperationException | IOException
                 | IllegalArgumentException ex) {
            System.out.println("multicast=UNAVAILABLE:"
                    + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) throws Exception {
        probe(StandardProtocolFamily.INET, InetAddress.getByAddress(
                new byte[] {127, 0, 0, 1}));

        byte[] v6 = new byte[16];
        v6[15] = 1;
        probe(StandardProtocolFamily.INET6, InetAddress.getByAddress(v6));

        optionProbe();

        if (args.length == 1) {
            multicastProbe(args[0]); // Local interface name from OS.
        }
    }
}
```

**Lưu ý:** nếu interface biến mất hoặc truy xuất `NetworkInterface.isUp()` ném `SocketException`, method `multicastProbe` trong ví dụ có thể báo exception tới `main`. Trong ứng dụng production, cần bắt/log lỗi khảo sát interface theo từng chức năng và quyết định có thể bỏ qua multicast hay không; **đừng nuốt lỗi rồi kết luận multicast được hỗ trợ**.

### 7.2. Lệnh biên dịch và chạy

Tạo file đúng tên `UdpFamilyProbe.java`. Dùng một JDK hiện đại hỗ trợ target 15, ví dụ JDK 21 hoặc mới hơn:

```bash
javac --release 15 -encoding UTF-8 UdpFamilyProbe.java
java UdpFamilyProbe
```

Chương trình đã được **biên dịch thành công với `--release 15`** và chạy trên **OpenJDK 24** trong môi trường kiểm thử.

**Ví dụ stdout thực tế trên một máy Windows/JDK 24 được kiểm thử:**

```text
INET.openBind=OK
INET.sentBytes=5
INET.loopbackReceive=OK
INET6.openBind=OK
INET6.sentBytes=5
INET6.loopbackReceive=OK
reusePortAdvertised=false
reusePortSet=SKIPPED
```

**Đây là output ghi nhận trên một môi trường, không phải output được bảo đảm trên mọi máy.** Nếu IPv6 bị tắt, có thể xuất hiện `INET6.probe=UNAVAILABLE:UnsupportedOperationException` hoặc một loại lỗi I/O khác. Nếu socket mở/bind được nhưng datagram không về trong 1.5 giây, chương trình có thể in `INET6.loopbackReceive=NO_DATAGRAM`. Trên hệ điều hành khác, `reusePortAdvertised=true` và `reusePortSet=true` cũng có thể xuất hiện.

**Tại sao lại ghi `sentBytes=5`?** `"probe"` là năm ký tự ASCII, mã hóa UTF-8 thành đúng năm byte. `sender.send(...)` trả về số byte được gửi từ `ByteBuffer`. Tuy nhiên, thành công của send **không tự bảo đảm** receiver đã nhận; chỉ dòng `loopbackReceive=OK` mới là bằng chứng **chương trình thực sự đã đọc đúng payload** trong lần thử ấy.

### 7.3. Probe multicast khi thật sự cần

Chương trình **không tự chọn interface để join nhóm** vì interface trên máy không thể đoán từ tên OS.

Bạn có thể xem các interface đang có bằng công cụ OS hoặc một đoạn Java riêng, ví dụ:

```java
for (NetworkInterface ni :
        Collections.list(NetworkInterface.getNetworkInterfaces())) {
    if (ni.isUp() && ni.supportsMulticast()) {
        System.out.println(ni.getName());
    }
}
```

Đoạn này chỉ là **mảnh minh họa** trong một method có `throws Exception`, với import `java.net.NetworkInterface`, `java.util.Collections`. Chọn một interface thực sự có **IPv4 address** trên mạng mà bạn quản lý. Không hard-code `eth0` hoặc tên adapter Windows vào ứng dụng chung.

Với tên interface tìm được:

```bash
java UdpFamilyProbe <interface-name>
```

`<interface-name>` ở đây là **placeholder của lệnh terminal**, cần thay bằng tên thật, không gõ các dấu `<` và `>`.

Khi môi trường cho phép join IPv4 group, chương trình in thêm:

```text
multicastJoin=true
multicastDropped=true
```

Hai dòng này đã được kiểm thử trên một interface multicast-capable của môi trường OpenJDK 24. Chúng xác nhận **`MembershipKey` được tạo, valid trước `drop` và invalid sau `drop`**. Chúng **không** chứng minh một sender ở host khác sẽ chuyển phát đến đây. Nếu interface không phù hợp, output có thể là `multicast=INTERFACE_UNAVAILABLE`, `multicast=NO_IPV4_ADDRESS` hoặc `multicast=UNAVAILABLE:...`.

**`MulticastChannel.join(...)` chỉ nên được chạy khi multicast thực sự là nhu cầu của ứng dụng.** Không cần join một nhóm bất kỳ trong mọi lần app khởi động chỉ để “kiểm tra xem có mạng không”. Đối với production, thực hiện capability check phù hợp với địa chỉ group/interface, và quản lý membership trong lifecycle rõ ràng.

### 7.4. Từng phần của ví dụ cho ta biết gì?

| Kết quả | Điều đã kiểm tra thật | Điều vẫn cần kiểm tra riêng |
| --- | --- | --- |
| `INET.openBind=OK` | Tạo được IPv4 DatagramChannel và bind loopback local | Kết nối tới remote IPv4 không? |
| `INET6.openBind=OK` | Tạo được IPv6 DatagramChannel và bind loopback `::1` | Có IPv6 route ra mạng ngoài hay không? |
| `*.sentBytes=5` | Socket đã chấp nhận thao tác gửi năm byte | Packet có được nhận không? |
| `*.loopbackReceive=OK` | Receiver nhận và giải mã đúng một datagram loopback | Firewall/routing tới peer khác? |
| `reusePortAdvertised=true/false` | Danh sách options khai báo hỗ trợ `SO_REUSEPORT` | OS có phân phối giữa nhiều sockets theo yêu cầu không? |
| `reusePortSet=true` | Giá trị option được set/read lại thành true | Nhiều socket có bind chung port và nhận như thiết kế không? |
| `multicastJoin=true` | Thao tác join group trên interface thành công | Router/IGMP/firewall chuyển phát group không? |
| `multicastDropped=true` | MembershipKey invalid sau drop | Packet đã vào receive queue trước drop có còn không? |

## 8. Thiết kế fallback đúng: chỉ đổi phương án nếu giao thức cho phép

Một chiến lược thường gặp là ưu tiên IPv6, nếu không khả dụng thì dùng IPv4. Nhưng nó chỉ đúng khi **ứng dụng thực sự hỗ trợ IPv4 fallback**.

### 8.1. Trường hợp có thể fallback

Giả sử dịch vụ nội bộ được cấu hình cho **cả IPv4 và IPv6**, server có endpoints theo cả hai family, và giao thức ứng dụng không thay đổi ý nghĩa khi chuyển IP family:

```text
Nếu có endpoint IPv6 được phép:
    thử family INET6 và hoạt động I/O thật
    nếu thành công -> sử dụng IPv6

Nếu endpoint IPv6 không tồn tại/không dùng được:
    thử endpoint IPv4 được phép với family INET
    nếu thành công -> sử dụng IPv4

Nếu không có phương án nào hoạt động:
    báo lỗi rõ, không giả vờ "connected"
```

Đây là pseudocode kiến trúc. **Không** dùng một lỗi UDP send để tự suy ra có thể thay server identity hoặc bỏ yêu cầu xác thực; fallback phải giữ đúng chính sách trust, key, certificate/credentials, endpoint và protocol version của ứng dụng.

### 8.2. Trường hợp **không được** fallback

- API/giao thức **bắt buộc IPv6**, chẳng hạn remote endpoint chỉ có AAAA record; chuyển sang IPv4 làm không có đúng peer.
- Ứng dụng sử dụng **IPv6 multicast group** và cần membership/SSM theo IPv6; không được âm thầm đổi sang một group IPv4 không tương ứng.
- Chính sách mạng bắt buộc interface/segment cụ thể; fallback sang NIC khác có thể làm lộ dữ liệu hoặc đi sai route.
- Tính năng quan trọng phụ thuộc `SO_REUSEPORT` hoặc multicast source filtering; tự tắt mà không có thiết kế khác có thể gây sai phân phối hoặc mất kiểm soát.
- Chứng thực/authorization gắn với endpoint và protocol metadata; không dùng bất kỳ endpoint có cùng hostname để bỏ qua bước kiểm tra bảo mật.

**Nguyên tắc:** *Optional performance optimization* có thể tắt khi unsupported. *Required protocol/security invariant* phải được thỏa hoặc fail rõ.

## 9. Đừng coi `os.name` và phiên bản JDK là bảng khả năng mạng

Một anti-pattern:

```java
String os = System.getProperty("os.name");
if (os.contains("Linux")) {
    // Assume SO_REUSEPORT and IPv6 multicast always work.
} else {
    // Disable everything else.
}
```

Đây là **phản ví dụ**; có thể biên dịch khi đặt trong method nhưng **sai về nguyên tắc suy luận**.

Tại sao?

- Linux containers có namespace network và sysctls riêng, có thể tắt IPv6, không cấp quyền join multicast hoặc không có route.
- Windows có nhiều loại adapter/VPN/virtual switches; IPv6 có thể bật nhưng outbound multicast vẫn không đi được.
- macOS có thể có `SO_REUSEPORT` nhưng cách distribute UDP datagrams giữa sockets khác Linux.
- Cloud mạng có thể chặn multicast dù `NetworkInterface.supportsMulticast()` trả `true`.
- OS firewall, SELinux, endpoint security và quyền process có thể thay đổi thành công/thất bại theo deployment.
- JDK provider, option set, DNS policy và network properties khác nhau dù OS build giống nhau.
- Một OS update, cấu hình VPN hoặc container restart có thể thay đổi khả năng thực tế **mà không đổi chuỗi `os.name`**.

**Dùng `os.name`/version để quan sát, không để tự thay thế runtime feature probing.**

## 10. NetworkInterface: khả năng của NIC chưa bằng khả năng của network

Các method hữu ích trong `java.net.NetworkInterface`:

| Method | Trả lời câu hỏi | Giới hạn |
| --- | --- | --- |
| `getNetworkInterfaces()` | Host/container đang nhìn thấy interfaces nào? | Có thể trả interface ảo hoặc cấu hình hạn chế |
| `getByName(name)` | Interface được chọn có còn tồn tại? | Tên có thể thay đổi sau reboot/deploy |
| `isUp()` | Interface đang up theo OS? | Không đảm bảo route/multicast delivery |
| `supportsMulticast()` | OS báo interface hỗ trợ multicast? | Không bảo đảm switch/router/cloud cho qua |
| `isLoopback()` | Interface là loopback? | Không giống một NIC truyền ra LAN |
| `getInetAddresses()` | Interface đang có IPv4/IPv6 addresses nào? | Địa chỉ tồn tại không chứng minh peer reachable |
| `getIndex()` | Index interface, cần chú ý với IPv6 scope | Index cũng có thể thay đổi |
| `getInterfaceAddresses()` | Địa chỉ và prefix/broadcast metadata | Không thay chính sách mạng thực tế |

### 10.1. Kiểm tra đúng IP family

Nếu join IPv4 group, interface nên có **IPv4 address** phù hợp. Nếu join IPv6 multicast group, phải kiểm tra **IPv6 address/scope** tương ứng. Điều kiện `isUp() && supportsMulticast()` **chưa đủ** để suy ra cả hai family được dùng.

Java cung cấp `Inet4Address` và `Inet6Address` để kiểm tra address family:

```java
boolean hasIPv4 = Collections.list(ni.getInetAddresses()).stream()
        .anyMatch(address -> address instanceof Inet4Address);
```

Đoạn này giả định `ni` tồn tại và các import `java.net.Inet4Address`, `java.util.Collections` có sẵn. Không đánh giá family bằng cách tìm dấu `:` hoặc `.` trong `getHostAddress()` vì textual formatting, scope suffix và dạng địa chỉ hỗn hợp dễ khiến code sai.

### 10.2. Chọn source IP và interface khi gửi multicast

`StandardSocketOptions.IP_MULTICAST_IF` chỉ định **outgoing interface**. Nó không tham gia nhóm để nhận; receiver cần `join(group, ni)` và local bind port. Đặt `IP_MULTICAST_TTL` và `IP_MULTICAST_LOOP` theo nhu cầu, nhưng không dùng những option ấy thay cho routing/security.

Nếu hệ thống có nhiều NIC, sender gửi qua A còn receiver join qua B, packet có thể không đến dù cả hai `supportsMulticast()`. Hãy log interface, group, port, family, TTL và quan sát packet delivery trên mạng được phép để chẩn đoán.

### 10.3. Kiểm tra thực tế nhưng không tạo traffic mạng tùy ý

Capability check cho multicast có thể được phân tầng:

1. Xác nhận group IP là multicast và family trùng với channel.
2. Xác nhận NIC up/multicast và address family phù hợp.
3. Mở/bind/`join` group trên một interface đã được phép dùng.
4. **Chỉ khi thực sự cần kiểm chứng delivery**, gửi **test datagram được định danh** đến group/port trong mạng thử nghiệm do bạn quản lý; giới hạn TTL và payload.
5. Nhận và kiểm tra source/sequence/protocol data, không dựa vào `send()` success.

Đừng scan hoặc join hàng loạt groups trên mạng production chỉ để thu thập danh sách khả năng. Chọn phép thử có chi phí và tác động thấp nhất vẫn đủ trả lời câu hỏi kỹ thuật.

## 11. Khác biệt giữa advertised option và effect thật

Một ví dụ điển hình là **`SO_REUSEPORT`**. Không chỉ hỏi “Option có được khai báo không?” mà cần ba mức:

### Mức 1 — liệt kê

```java
boolean advertised = channel.supportedOptions()
        .contains(StandardSocketOptions.SO_REUSEPORT);
```

Kết quả `true` chỉ cho biết implementation báo có option đó. Kết quả `false` nói rằng **trên channel hiện tại** không nên thử `setOption` như một tính năng bình thường.

### Mức 2 — thử set/get

```java
if (advertised) {
    channel.setOption(StandardSocketOptions.SO_REUSEPORT, true);
    boolean enabled = channel.getOption(StandardSocketOptions.SO_REUSEPORT);
}
```

Đoạn minh họa chưa có xử lý exception; production phải xử lý `IOException` và `UnsupportedOperationException`. Chọn thời điểm thiết lập trước `bind` nếu behavior reuse cần ở bước bind. Không coi `enabled=true` là bảo đảm hai listeners thực sự có thể bind cùng địa chỉ/cổng.

### Mức 3 — thử đúng use case

Nếu tính năng thật cần **nhiều UDP receivers cùng local port**:

- Tạo hai sockets/channels trong môi trường test có cùng family, bind address và port.
- Thiết lập options cần thiết trước `bind`; xác nhận **cả hai bind thành công**.
- Gửi nhiều datagrams thử nghiệm từ nguồn đủ đa dạng để quan sát cách OS phân phối.
- Không đưa một số lượng packet cụ thể thành tiêu chí portable nếu OS có chính sách hashing/load distribution khác nhau.
- Nếu hệ thống bắt buộc nhận **một bản copy trên mỗi listener**, đừng đánh đồng `SO_REUSEPORT` với multicast group subscription; đó có thể là mô hình phân phối khác.
- Kiểm tra lại sau OS/JDK/provider upgrades.

**Những hành vi tầng OS không có trong hợp đồng Java thì không nên biến thành assumption bắt buộc của business logic.**

## 12. Phân loại lỗi và fallback có kiểm soát

| Triệu chứng | Nơi gặp | Ý nghĩa có thể | Quyết định |
| --- | --- | --- | --- |
| `UnsupportedOperationException` với `open(INET6)` | Tạo channel | Family không được hỗ trợ/bật | Fallback IPv4 **nếu protocol cho phép**, nếu không fail rõ |
| `IOException` với `open` hoặc `bind` | Socket/OS resource | Policy, địa chỉ không có, port conflict, hết tài nguyên | Chẩn đoán cụ thể; không mặc định “IPv6 unsupported” |
| `BindException` | Local bind | Port/address đã dùng hoặc permission | Thử ephemeral port khi test, sửa cấu hình prod |
| `UnsupportedAddressTypeException` | Bind/connect/send | Dùng loại `SocketAddress` không hợp lệ | Sửa kiểu/family, không giấu lỗi |
| `UnsupportedOperationException` với `setOption` | Tùy chọn | Option không được channel hỗ trợ | Bỏ qua **chỉ nếu optional**, nếu required thì fail |
| `IllegalArgumentException` với `setOption` | Tùy chọn | Giá trị sai hoặc ngoại lệ cụ thể của implementation | Sửa config/value, không “fallback mọi thứ” |
| `ClosedChannelException` | I/O trên channel | Code đã đóng channel | Sửa lifecycle, không phải lỗi family |
| `SocketException` khi đọc interface | `NetworkInterface` | Interface bị gỡ, OS policy, vấn đề mạng | Reload cấu hình/interface, retry có giới hạn |
| `Selector.select(timeout) == 0` | Probe/receive | Chưa có packet ready | Ghi nhận `NO_DATAGRAM`, kiểm tra test/routing/firewall |
| `send(...) == payload length` | UDP sender | Kernel chấp nhận bytes để gửi | **Chưa** chứng minh receiver nhận |
| `Network is unreachable` | Send tới network/multicast | Route/interface/network policy không cho | Chọn interface/route phù hợp, không chỉ đổi family |
| `NoRouteToHostException` | I/O network | Không có đường tới đích/route bị từ chối | Kiểm tra route/firewall, provider, địa chỉ |
| `MembershipKey.isValid() == true` | Multicast join | Membership được tạo | Vẫn phải kiểm tra delivery ở tầng mạng |
| `SecurityException` | Cấu hình/policy | Access bị từ chối | Phân quyền đúng, không tắt các biện pháp bảo vệ |
| `UnknownHostException` | DNS resolution | Không phân giải được hostname hoặc cấu hình name service lỗi | Kiểm tra DNS, policy và endpoints; không tự đổi protocol |

**Không bắt mọi `Exception` rồi gọi `DatagramChannel.open(INET)` như “cứu vãn”.** Nếu lỗi gốc là permission hoặc không có route, fallback có thể làm giấu sự cố hoặc vô tình đổi transport/security policy. Phân loại lỗi và ràng buộc fallback theo yêu cầu thực tế.

### Khi runtime thay đổi trong lúc hoạt động

Ngay cả khi bước startup probe PASS, interface vẫn có thể bị disable, DNS có thể đổi, route có thể mất và firewall có thể cập nhật. Vì vậy:

- Luôn xử lý `IOException` ở **mỗi I/O operation**, không coi startup probe là sự bảo đảm mãi mãi.
- Có retry/backoff có giới hạn khi nghiệp vụ cho phép, không loop vô hạn ăn CPU.
- Nếu socket/channel ở trạng thái không xác định sau lỗi I/O nghiêm trọng, đóng và tạo mới thay vì lạm dụng một object hỏng.
- Nếu cần failover, revalidate remote endpoint, credentials và application session.
- Ghi lại lý do thất bại ở mức phù hợp; tránh log dữ liệu nhạy cảm, secrets hoặc payload của người dùng.

## 13. Cách tổ chức kiểm thử portable

Nên tách **ba loại test** để không biến CI thành một bộ kiểm tra phụ thuộc mạng ngoài:

### 13.1. Unit tests không phụ thuộc OS/network thật

Kiểm tra các hàm thuần: lựa chọn family từ `InetAddress`, mapping lỗi → quyết định fallback, validation cấu hình port/group/interface, byte serialization, giới hạn buffer, phân tích output.

Ví dụ quy tắc thuần:

```java
static StandardProtocolFamily familyFor(InetAddress address) {
    if (address instanceof java.net.Inet4Address) {
        return StandardProtocolFamily.INET;
    }
    if (address instanceof java.net.Inet6Address) {
        return StandardProtocolFamily.INET6;
    }
    throw new IllegalArgumentException("Unsupported IP address family");
}
```

Đây là method minh họa cần nằm trong class và import `java.net.InetAddress`/`StandardProtocolFamily`. Nó quyết định family dựa trên **loại địa chỉ**, không dùng hostname text.

### 13.2. Capability/integration tests tại môi trường chạy

Thực hiện những probe như chương trình `UdpFamilyProbe`:

- IPv4 loopback có được mở/bind/gửi/nhận?
- IPv6 loopback có được mở/bind/gửi/nhận?
- `SO_REUSEPORT` có trong `supportedOptions`? Set được không?
- Nếu cần multicast, interface/group được join/drop không?
- Có thể chạy một test giữa hai máy cùng network (nếu phạm vi đã được cấp phép) để kiểm tra routing/firewall?
- Nếu cần NIO nonblocking, `Selector` có báo readiness và ứng dụng xử lý null return không?

Không biến kết quả **một environment** thành sự thật toàn cầu. Chạy test tại những nơi thực sự deploy: dev workstation, CI, staging và production readiness nếu được phép.

### 13.3. Load và failure-injection tests

Cho use case quan trọng:

- Test khi UDP packets bị drop/duplicate/reorder.
- Test khi interface bị disable hoặc route đổi lúc chương trình chạy.
- Test cổng đã bị process khác bind.
- Test IPv6 disabled và IPv4-only environment.
- Test cùng process có nhiều network interfaces/virtual adapters.
- Test option từ chối hoặc không có trong danh sách.
- Test transient I/O failures, deadline và backoff.
- Test fallback **giữ nguyên security/identity policy**.

Sử dụng network simulator/lab có kiểm soát, không tự tác động lên mạng production hoặc khiến health probe gửi lưu lượng multicast lớn ngoài yêu cầu.

## 14. Quan sát và cấu hình khi triển khai

Một log capability có giá trị nên chứa:

| Thuộc tính | Vì sao hữu ích |
| --- | --- |
| JDK runtime/version, OS name/version | Dùng để **đối chiếu**, không quyết định khả năng |
| Protocol family được yêu cầu | Cho biết application intended IPv4 hay IPv6 |
| Family đã được mở/bind thành công | Tách lỗi cấp socket và cấp địa chỉ |
| Local bind address/port (không phải secret) | Chẩn đoán xung đột port và wildcard/loopback |
| Remote endpoint hoặc group/port đã cấu hình | Tìm lỗi route/address family |
| Interface name/index và IP family | Tìm lỗi NIC/VPN/IPv6 scope |
| Socket options được quảng bá và option set result | Xác định thiếu `SO_REUSEPORT`/multicast option |
| Datagram send count và receive count, bytes, timeouts | Quan sát hành vi thật; không chỉ dựa vào `open` |
| Exception **type** và bước I/O xảy ra | Phân loại lỗi và khôi phục |
| Capability mode/fallback đã chọn | Biết ứng dụng đang chạy ở mode nào |

Với ứng dụng nhiều mạng, tốt nhất **giữ configuration tường minh**: enableIPv4, requireIPv6, preferredFamily, bindAddress, interfaceId, multicastGroup, port, TTL, retry deadlines và feature flags cho những option optional.

Không lưu một “capability cache” vĩnh viễn chỉ dựa trên lần startup nếu môi trường có thay đổi interface/route. Cập nhật khi có network change signal phù hợp hoặc khi I/O fail, rồi tạo lại socket/channel theo chính sách.

### Quyết định fail-fast vs degrade gracefully

| Yêu cầu | Nếu probe thất bại | Ví dụ |
| --- | --- | --- |
| **Optional** diagnostic multicast | Log + tắt multicast mode | Ứng dụng vẫn chạy unicast nếu business cho phép |
| **Optional** `SO_REUSEPORT` optimization | Chạy một receiver hoặc chiến lược khác đã test | Không giữ giả định multi-process port reuse |
| **Required** IPv6 endpoint | Fail fast rõ ràng | Không “dịch” IPv6-only thành IPv4 |
| **Required** multicast group receive | Không phát tín hiệu READY nếu chưa join được | Báo lỗi config/interface |
| **Required** end-to-end delivery | Phải có application-level health/ACK nếu giao thức cung cấp | `open` hoặc `send` success không đủ |
| **Security/identity constraint** | Không fallback sang endpoint thiếu xác thực | Giữ đúng TLS/DTLS/credentials và policy |

## 15. Lỗi suy nghĩ thường gặp

1. **“JDK hỗ trợ API nên OS chắc chắn hỗ trợ.”** API Java tồn tại nhưng native socket/network có thể unavailable.
2. **“Máy là Linux nên `SO_REUSEPORT` luôn có.”** Containers, kernel, policy và providers khác nhau; kiểm tra `supportedOptions` và behavior thật.
3. **“Có `::1` là có IPv6 Internet.”** IPv6 loopback chỉ chứng minh đường local.
4. **“`open(INET6)` thành công nên IPv4 cũng nhận được.”** Dual-stack phụ thuộc platform; thử riêng hoặc dùng channels riêng.
5. **“`supportsMulticast()` là đủ để nhận multicast.”** Cần đúng group/interface/port/join/routing/firewall và sender.
6. **“`IP_MULTICAST_LOOP=true` chắc chắn tự nhận datagram.”** OS có thể không deliver theo cách trông đợi.
7. **“`SO_REUSEADDR` và `SO_REUSEPORT` tương đương.”** Tên khác, semantics/platform differences khác; phải test đúng use case.
8. **“`getOption` true nghĩa toàn bộ hành vi OK.”** Nó chỉ xác nhận value được báo lại, không chứng minh packet distribution.
9. **“`send` thành công nghĩa peer đã nhận.”** UDP không có ACK ở tầng vận chuyển.
10. **“Gọi `System.setProperty` rồi sockets cũ tự đổi behavior.”** Nhiều Java networking properties được đọc lúc VM startup.
11. **“Cứ `catch(IOException)` rồi fallback IPv4 là an toàn.”** Lỗi có thể là permission, route, resource exhaustion hoặc policy bắt buộc IPv6.
12. **“Test chạy được trên máy mình thì mọi host đều chạy được.”** Feature probe cần chạy ở môi trường deployment thật.
13. **“Dùng tên hostname để xác định family.”** A/AAAA records và DNS policy có thể đổi; quyết định từ `InetAddress` thực tế.
14. **“UDP connect là handshake.”** `DatagramChannel.connect` chỉ gắn một remote peer cục bộ; không có bảo đảm remote tồn tại.
15. **“Capability probe có thể chạy một lần rồi tin mãi.”** Interface/route/firewall có thể thay đổi trong runtime.

## 16. Checklist đưa vào sản phẩm

- [ ] Đã tách **API availability, socket family, bind, option, interface và delivery** thành các kiểm tra riêng chưa?
- [ ] Chọn `INET` hoặc `INET6` dựa vào nhu cầu thực tế và loại IP địa chỉ đích, thay vì `os.name`?
- [ ] Với multicast, channel family trùng group family, NIC hỗ trợ và đã join thật?
- [ ] Đã kiểm tra `supportedOptions()` trước khi dùng những option optional, và xử lý set/get failure?
- [ ] Với `SO_REUSEADDR`, `SO_REUSEPORT` hay một option phụ thuộc bind, đã thiết lập **trước bind** khi yêu cầu?
- [ ] Đã dùng explicit IPv4/IPv6 loopback và ephemeral port để test mà không phụ thuộc Internet?
- [ ] Đã có timeout và không giả định mọi datagram sẽ đến hoặc theo đúng thứ tự?
- [ ] Đã phân biệt `send succeeded`, `receive succeeded` và **application-level validation succeeded**?
- [ ] Đã phân loại `UnsupportedOperationException`, `IOException`, `IllegalArgumentException`, `ClosedChannelException` và các lỗi cấu hình khác đúng ý nghĩa?
- [ ] Fallback IPv4/IPv6 hoặc optional feature có được business/security protocol cho phép?
- [ ] Đã dùng NetworkInterface thực tế của runtime, quan tâm IPv4/IPv6, VPN, NIC ảo và interface down?
- [ ] Đã chạy integration test khi nhiều sockets cùng bind, khi cần multicast delivery và khi có firewall/router policy?
- [ ] Có log/metrics cho family, interface, options, errors, timeouts mà không ghi dữ liệu nhạy cảm?
- [ ] Có chuẩn bị xử lý lỗi/reconnect khi network thay đổi lúc runtime?
- [ ] Runtime triển khai có đang được hỗ trợ và đã test trên đúng JDK/OS/container của production chưa?

## 17. Tài liệu chính thức đang áp dụng

- **Java SE 15 — `DatagramChannel`**: `open()` vs `open(ProtocolFamily)`, IPv4/IPv6, `bind`, `send`, `receive`, socket options và exceptions: https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/nio/channels/DatagramChannel.html
- **Java SE 25 — `DatagramChannel`** (API hiện đại, cùng khái niệm family): https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/DatagramChannel.html
- **Java SE 15 — `NetworkChannel`**: `supportedOptions()`, `getOption` và `setOption`: https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/nio/channels/NetworkChannel.html
- **Java SE 15 — `StandardProtocolFamily`** (`INET`, `INET6`): https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/net/StandardProtocolFamily.html
- **Java SE hiện đại — `StandardSocketOptions`**: `SO_REUSEPORT`, `SO_REUSEADDR` và multicast options: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/StandardSocketOptions.html
- **Java SE 15 — `NetworkInterface`**: trạng thái NIC, địa chỉ IP, multicast capability: https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/net/NetworkInterface.html
- **Java SE 15 — `MulticastChannel`**: join group, source filtering và cấu hình interface: https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/nio/channels/MulticastChannel.html
- **Java SE 25 — Networking Properties**: `java.net.preferIPv4Stack` và `java.net.preferIPv6Addresses` đọc từ lúc JVM startup: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/doc-files/net-properties.html
- **Java SE 15 — `Selector` và `SelectionKey`**: timeout/nonblocking readiness: https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/nio/channels/Selector.html
- **RFC 8085 — UDP Usage Guidelines**: các giới hạn delivery, packet size, flow/congestion và cách sử dụng UDP: https://www.rfc-editor.org/rfc/rfc8085
- **RFC 1112 — IP Multicasting**: nguyên tắc group/network delivery: https://www.rfc-editor.org/rfc/rfc1112

**Kết luận:** Để Java 15+ làm việc ổn định trên nhiều hệ điều hành, hãy **chọn protocol family có chủ đích, kiểm tra socket mở/bind được, khảo sát tùy chọn nhưng không quá tin `supportedOptions()`, thử giao tiếp UDP thực tế trong phạm vi được phép, rồi fallback theo chính sách**. Một ứng dụng mạng portable không phải ứng dụng đoán đúng tên OS — mà là ứng dụng phân biệt được **khả năng có thật**, lỗi môi trường, giới hạn giao thức và quyết định phục hồi an toàn.
