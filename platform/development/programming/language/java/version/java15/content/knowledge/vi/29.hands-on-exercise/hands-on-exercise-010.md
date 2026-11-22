# Thử channel IPv4, IPv6 trên các môi trường hỗ trợ (Java NIO)

Java có thể giao tiếp bằng TCP và UDP qua **IPv4** hoặc **IPv6** bằng các channel trong `java.nio.channels`. Từ **Java 15**, `SocketChannel.open(ProtocolFamily)` và `ServerSocketChannel.open(ProtocolFamily)` cho phép chọn rõ họ giao thức. `DatagramChannel.open(ProtocolFamily)` đã có từ Java 7 và tiếp tục được hỗ trợ. Các API này vẫn hữu ích trên JDK hiện đại; bài thực hành dùng **Java 17+**, không yêu cầu tiếp tục triển khai ứng dụng mới trên Java 15.

Mục tiêu là kiểm tra thực sự các kết nối **TCP** và gói **UDP** trên IPv4/IPv6, ghi nhận môi trường có hỗ trợ hay không, và cấu hình test/CI sao cho một lỗi lập trình không bị ngụy trang thành “máy không có IPv6”.

> **Nguyên tắc:** Một hệ thống hỗ trợ IPv4 không nhất thiết hỗ trợ IPv6. IPv6 loopback (`::1`) hoạt động cũng **chưa** chứng minh máy có kết nối IPv6 ra Internet. Khả năng của JVM, hệ điều hành, network namespace/container, firewall và cấu hình mạng phải được kiểm tra ở đúng môi trường chạy.

## 1. Phân biệt các API và họ địa chỉ

| API | Vận chuyển | Cách chọn họ IP | Ghi chú |
| --- | --- | --- | --- |
| `ServerSocketChannel.open(StandardProtocolFamily.INET)` | TCP server | IPv4 | Overload `open(ProtocolFamily)` có từ Java 15 |
| `ServerSocketChannel.open(StandardProtocolFamily.INET6)` | TCP server | IPv6 | Có thể ném `UnsupportedOperationException` nếu IPv6 không được hỗ trợ |
| `SocketChannel.open(StandardProtocolFamily.INET)` | TCP client | IPv4 | Mở channel chưa kết nối, sau đó `connect(...)` |
| `SocketChannel.open(StandardProtocolFamily.INET6)` | TCP client | IPv6 | Họ socket được chọn rõ ràng; vẫn phải kết nối đến địa chỉ phù hợp |
| `DatagramChannel.open(StandardProtocolFamily.INET)` | UDP | IPv4 | Hỗ trợ chọn `ProtocolFamily` từ Java 7 |
| `DatagramChannel.open(StandardProtocolFamily.INET6)` | UDP | IPv6 | Có thể thất bại khi nền tảng không có IPv6 |
| `SocketChannel.open()`, `ServerSocketChannel.open()`, `DatagramChannel.open()` | TCP/UDP | Mặc định của provider/nền tảng | Không nên dựa vào overload không tham số để kết luận đã thử đúng cả hai họ |

`StandardProtocolFamily.INET` nghĩa là họ địa chỉ IPv4, còn `StandardProtocolFamily.INET6` nghĩa là họ địa chỉ IPv6. Đây là **đặc tả họ protocol của socket**, không phải tên host. Việc JVM hỗ trợ một họ không có nghĩa mọi địa chỉ thuộc họ đó đều có thể bind hoặc route.

### Những địa chỉ phù hợp để kiểm thử tại máy

| Mục đích | IPv4 | IPv6 |
| --- | --- | --- |
| Loopback, chỉ trong máy hoặc namespace hiện tại | `127.0.0.1` (thuộc dải `127.0.0.0/8`) | `::1` |
| Wildcard khi server lắng nghe nhiều interface | `0.0.0.0` | `::` |
| Kết nối đến một server thực | Địa chỉ IPv4 hoặc bản ghi DNS A | Địa chỉ IPv6 hoặc bản ghi DNS AAAA |

**Ưu tiên địa chỉ loopback dạng số** cho bài test này. `localhost` có thể được phân giải thành IPv4, IPv6 hoặc cả hai theo file hosts, DNS resolver và chính sách JVM, khiến kết quả không còn thể hiện rõ họ IP đang được thử. Trong thử nghiệm cơ bản, tránh dùng wildcard vì nó có thể mở cổng trên nhiều interface ngoài ý định.

`Inet4Address` đại diện IPv4, `Inet6Address` đại diện IPv6; các tên literal `127.0.0.1` và `::1` không phụ thuộc mạng Internet. Khi dùng địa chỉ IPv6 ở URL, cần đặt dấu ngoặc vuông như `http://[::1]:8080`; nhưng đối với `new InetSocketAddress("::1", port)` hoặc `InetAddress.getByName("::1")`, **không** thêm ngoặc vuông theo cú pháp URL.

## 2. Thế nào là một ca test có ý nghĩa?

Một test IPv4/IPv6 tốt không dừng ở việc tạo đối tượng channel:

1. **Mở đúng loại channel:** gọi `open(INET)` hoặc `open(INET6)`, không để ngầm định họ địa chỉ.
2. **Bind đúng địa chỉ:** TCP server hoặc UDP receiver bind vào `127.0.0.1` hay `::1` trên **port 0**, để hệ điều hành cấp cổng trống.
3. **Lấy cổng thật:** đọc `getLocalAddress()` sau `bind`; không hard-code cổng, tránh tranh chấp giữa các lần chạy CI.
4. **Truyền dữ liệu thật:** TCP client `connect` và `write`, server `accept` và `read`; UDP sender `send`, receiver `receive`.
5. **Assert payload:** so sánh các byte/ký tự nhận được với dữ liệu gửi, chẳng hạn chuỗi ASCII `ping`.
6. **Phân biệt kết quả:** IPv4 phải chạy nếu môi trường yêu cầu; IPv6 chỉ được `SKIP` khi bài test được khai báo **tùy chọn** và bước kiểm tra năng lực cho thấy môi trường chưa sẵn sàng. Nếu hợp đồng sản phẩm yêu cầu IPv6, không được `SKIP`.

**TCP là luồng byte**: một lần `write` không bảo đảm bên kia nhận đủ dữ liệu trong một lần `read`; phải có vòng lặp và quy tắc framing phù hợp. **UDP là datagram**: mỗi lần `send` gửi một thông điệp; không bảo đảm giao hàng, đúng thứ tự hoặc không trùng lặp. Trên loopback, UDP thường đến nơi rất nhanh nhưng test vẫn cần thời hạn chờ hữu hạn.

## 3. Chương trình Java 17+ kiểm tra TCP và UDP trên hai họ IP

Tạo một file **`ChannelFamilyLab.java`**, với chương trình đầy đủ bên dưới. Chương trình chỉ thử loopback của máy đang chạy, không cần Internet hay server bên ngoài. Nó có hai chế độ:

- **Mặc định:** IPv4 phải PASS; IPv6 chạy nếu máy có thể mở và bind TCP/UDP trên `::1`, nếu chưa có thì ghi `SKIPPED`.
- **`--require-ipv6`:** IPv6 là yêu cầu bắt buộc. Không có IPv6 loopback hoặc kiểm thử IPv6 thất bại sẽ làm chương trình kết thúc bằng lỗi, thích hợp cho CI cam kết IPv6.

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.StandardProtocolFamily;
import java.nio.ByteBuffer;
import java.nio.channels.DatagramChannel;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;

public final class ChannelFamilyLab {
    private ChannelFamilyLab() {
    }

    public static void main(String[] args) throws Exception {
        boolean requireIPv6 =
                args.length == 1 && "--require-ipv6".equals(args[0]);

        if (args.length > 1 || (args.length == 1 && !requireIPv6)) {
            throw new IllegalArgumentException(
                    "Usage: java ChannelFamilyLab [--require-ipv6]");
        }

        exercise(StandardProtocolFamily.INET, "127.0.0.1");

        if (!canBindIPv6Loopback()) {
            if (requireIPv6) {
                throw new IllegalStateException(
                        "IPv6 loopback is required but unavailable");
            }
            System.out.println("INET6: SKIPPED (IPv6 loopback unavailable)");
        } else {
            // Capability đã PASS. Lỗi trong test bên dưới phải làm job FAIL.
            exercise(StandardProtocolFamily.INET6, "::1");
        }
    }

    static boolean canBindIPv6Loopback() {
        try (ServerSocketChannel tcp =
                     ServerSocketChannel.open(StandardProtocolFamily.INET6);
             DatagramChannel udp =
                     DatagramChannel.open(StandardProtocolFamily.INET6)) {

            InetAddress local = InetAddress.getByName("::1");
            tcp.bind(new InetSocketAddress(local, 0));
            udp.bind(new InetSocketAddress(local, 0));
            return true;

        } catch (UnsupportedOperationException | IOException unavailable) {
            // Đây chỉ là capability gate cho mode IPv6 tùy chọn.
            System.err.println("IPv6 bind check: "
                    + unavailable.getClass().getSimpleName());
            return false;
        }
    }

    static void exercise(StandardProtocolFamily family, String address)
            throws IOException {
        InetAddress loopback = InetAddress.getByName(address);

        testTcp(family, loopback);
        testUdp(family, loopback);

        System.out.println(family + ": TCP=PASS, UDP=PASS");
    }

    static void testTcp(StandardProtocolFamily family, InetAddress loopback)
            throws IOException {
        try (ServerSocketChannel server =
                     ServerSocketChannel.open(family)) {
            // Bind đúng loopback và lấy port trống từ hệ điều hành.
            server.bind(new InetSocketAddress(loopback, 0));

            try (SocketChannel client = SocketChannel.open(family)) {
                client.connect(server.getLocalAddress());

                try (SocketChannel accepted = server.accept()) {
                    ByteBuffer outgoing =
                            StandardCharsets.US_ASCII.encode("ping");
                    while (outgoing.hasRemaining()) {
                        client.write(outgoing);
                    }

                    ByteBuffer incoming = ByteBuffer.allocate(4);
                    while (incoming.hasRemaining()) {
                        if (accepted.read(incoming) < 0) {
                            throw new EOFException("TCP stream ended early");
                        }
                    }

                    incoming.flip();
                    String result = StandardCharsets.US_ASCII
                            .decode(incoming).toString();

                    if (!"ping".equals(result)) {
                        throw new IOException("Unexpected TCP payload");
                    }
                }
            }
        }
    }

    static void testUdp(StandardProtocolFamily family, InetAddress loopback)
            throws IOException {
        try (DatagramChannel receiver = DatagramChannel.open(family);
             DatagramChannel sender = DatagramChannel.open(family);
             Selector selector = Selector.open()) {

            receiver.bind(new InetSocketAddress(loopback, 0));
            receiver.configureBlocking(false);
            receiver.register(selector, SelectionKey.OP_READ);

            ByteBuffer outgoing =
                    StandardCharsets.US_ASCII.encode("ping");
            int sent = sender.send(outgoing, receiver.getLocalAddress());
            if (sent != 4) {
                throw new IOException("Could not send 4 UDP bytes");
            }

            // Chờ tối đa 5 giây, tránh một bài test treo vô hạn.
            if (selector.select(5_000) == 0) {
                throw new IOException("UDP receive timed out");
            }

            ByteBuffer incoming = ByteBuffer.allocate(16);
            if (receiver.receive(incoming) == null) {
                throw new IOException("UDP packet not available");
            }

            incoming.flip();
            String result = StandardCharsets.US_ASCII
                    .decode(incoming).toString();
            if (!"ping".equals(result)) {
                throw new IOException("Unexpected UDP payload");
            }
        }
    }
}
~~~

Tại thư mục chứa file, chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac --release 17 ChannelFamilyLab.java
java ChannelFamilyLab
~~~

Khi máy **hỗ trợ đầy đủ cả IPv4 và IPv6 loopback**, stdout chính xác là:

~~~text
INET: TCP=PASS, UDP=PASS
INET6: TCP=PASS, UDP=PASS
~~~

Nếu môi trường **không thể bind IPv6 loopback** nhưng IPv4 hoạt động, stdout là:

~~~text
INET: TCP=PASS, UDP=PASS
INET6: SKIPPED (IPv6 loopback unavailable)
~~~

Lúc đó stderr còn có dòng chẩn đoán bắt đầu bằng `IPv6 bind check:`, tiếp theo là tên kiểu ngoại lệ thực tế; **không dự đoán chính xác thông báo ngoại lệ** vì phụ thuộc hệ điều hành/JDK. Nếu IPv4 thất bại, chương trình kết thúc bằng lỗi và **không** báo PASS. Nếu bước kiểm tra IPv6 đã đạt nhưng truyền TCP/UDP thất bại, chương trình cũng kết thúc bằng lỗi — không tự chuyển lỗi đó thành SKIP.

Để buộc job test xác nhận IPv6:

~~~bash
java ChannelFamilyLab --require-ipv6
~~~

Nếu môi trường chỉ hỗ trợ IPv4, lệnh sẽ ném `IllegalStateException` sau khi chạy IPv4. Trong CI, đây là **FAIL có chủ đích** vì khả năng IPv6 là yêu cầu bắt buộc. Cần phân biệt điều đó với một job IPv6 tùy chọn trên runner không hỗ trợ IPv6.

### Tại sao code viết theo cách này?

- `new InetSocketAddress(loopback, 0)` yêu cầu bind trên địa chỉ loopback cụ thể, port 0 cấp phát động. Lấy lại cổng thực từ `server.getLocalAddress()` hoặc `receiver.getLocalAddress()`.
- TCP client sử dụng `SocketChannel.open(family)` và server dùng `ServerSocketChannel.open(family)`, vì vậy bài test thực sự đi qua overload chọn `ProtocolFamily` được bổ sung trong Java 15.
- `accept()` nhận kết nối TCP sau `connect()`. Chương trình dùng các channel TCP mặc định ở chế độ blocking; đây là ví dụ tuần tự trên loopback, **chưa** phải server nhiều kết nối.
- Vòng `while(outgoing.hasRemaining())` xử lý `write` không đủ byte trong một lần. Vòng đọc TCP dừng khi đã lấy đủ bốn byte hoặc ném `EOFException` nếu peer đóng sớm.
- UDP dùng `DatagramChannel.open(family)` cho cả bên gửi và nhận. `Selector.select(5000)` giới hạn thời gian chờ gói; `configureBlocking(false)` là bắt buộc trước khi đăng ký channel với `Selector`.
- `try-with-resources` đóng channel và selector cả khi test thất bại, giúp cổng được giải phóng để chạy lại.
- Hàm `canBindIPv6Loopback()` chỉ kiểm tra **khả năng mở và bind ở thời điểm đó**; kết quả `true` không bảo đảm mọi lần truyền sau đó sẽ thành công, vì thế `exercise(INET6, "::1")` vẫn phải chạy. Khi chạy CI bắt buộc, cả việc bind không được cũng phải làm job FAIL.

Trong sản phẩm thực tế, bổ sung timeout cho **toàn bộ** chu trình TCP (`connect`, `accept` và `read`), chẳng hạn dùng nonblocking channel + `Selector` với deadline hoặc giới hạn thời gian ở test runner. Ví dụ ở trên có timeout cho bước đợi UDP nhưng phần TCP blocking còn có thể chờ nếu môi trường gặp sự cố. Đừng dùng nguyên sample làm server production.

## 4. Kiểm tra môi trường có hỗ trợ IPv6 hay không

Ba mức kiểm tra khác nhau, không thể thay thế nhau:

| Mức | Cách kiểm tra | Chứng minh được gì? |
| --- | --- | --- |
| **API/JDK** | Gọi `ServerSocketChannel.open(INET6)`, `SocketChannel.open(INET6)` | JVM/provider có chấp nhận họ socket IPv6 tại thời điểm đó hay không |
| **Bind trong máy** | Bind TCP/UDP vào `::1` bằng port 0 | IPv6 loopback hoạt động trong **network namespace** hiện tại |
| **Kết nối đến mạng khác** | Connect tới endpoint IPv6 thật và truyền dữ liệu | Có đường truyền, routing, firewall/DNS phù hợp với endpoint được thử |

Một container có thể bật TCP/UDP IPv4, nhưng namespace của nó không có IPv6 loopback hoặc không có route IPv6 ra ngoài. Máy host hỗ trợ IPv6 không có nghĩa **container** cũng hỗ trợ. Tương tự, trạng thái network interface có IPv6 chưa chứng minh port của dịch vụ reachable. Kết quả đáng tin nhất cho một tính năng là **thực sự truyền dữ liệu trên channel tương ứng**.

Nếu cần xem cấu hình hệ điều hành, tùy nền tảng:

~~~bash
# Linux: kiểm tra địa chỉ IPv4/IPv6 trên các interface
ip -4 address
ip -6 address

# macOS: xem interface loopback
ifconfig lo0
~~~

Trong **PowerShell trên Windows**:

~~~powershell
Get-NetIPAddress -AddressFamily IPv4
Get-NetIPAddress -AddressFamily IPv6
~~~

Các lệnh chẩn đoán chỉ cung cấp **bằng chứng cấu hình**; không chứng minh được thành công của `SocketChannel.connect`/`DatagramChannel.receive`. Trên môi trường hạn chế, lệnh có thể không được cài hoặc không có quyền hiển thị đầy đủ. Bài test Java vẫn là nguồn xác nhận hành vi của chính ứng dụng.

Để kiểm tra dịch vụ từ máy khác, cần dùng địa chỉ **IPv4/IPv6 thực** của interface, cấu hình bind phù hợp với mục tiêu, firewall và routing. Không thể truy cập `127.0.0.1` hoặc `::1` của một server từ máy khác; các địa chỉ này luôn quay lại chính máy/namespace của phía gửi.

## 5. Dual-stack và các system properties của Java

Một nhầm lẫn phổ biến là: **chọn `INET6` không tự động chứng minh socket chỉ nhận IPv6**. Trên một số hệ điều hành, socket IPv6 còn có thể xử lý kết nối IPv4 thông qua địa chỉ IPv4-mapped IPv6 và chính sách dual-stack của hệ thống. Cách bind và socket options của nền tảng quyết định hành vi cụ thể. Bài test trên `::1` xác nhận đường đi IPv6 thật, nhưng nếu dự án cần **IPv6-only listener**, phải kiểm tra riêng cấu hình socket và hành vi kết nối từ IPv4.

Hai thuộc tính JVM thường gặp:

| Thuộc tính | Ý nghĩa thực tế |
| --- | --- |
| `-Djava.net.preferIPv4Stack=true` | Yêu cầu JVM ưu tiên sử dụng **IPv4-only sockets**; khi đặt giá trị này, **không** thể mặc nhiên kỳ vọng socket IPv6 hoạt động |
| `-Djava.net.preferIPv6Addresses=true` | Thay đổi **thứ tự ưu tiên địa chỉ** khi một hostname có cả A và AAAA; không tự tạo IPv6 route hoặc buộc một server luôn nhận IPv6 |
| `-Djava.net.preferIPv6Addresses=system` | Dùng thứ tự mà hệ điều hành/resolver trả về khi khả dụng; hữu ích khi cần tôn trọng thứ tự hệ thống |

Các thuộc tính trên được đọc **khi JVM khởi động**. Cần truyền bằng option `-D` trước tên class và chạy **tiến trình JVM mới** nếu muốn so sánh; việc đổi `System.setProperty` trong lúc chương trình đã chạy không phải phép thử đáng tin cho hai thuộc tính này.

Ví dụ, chỉ dùng để quan sát trên môi trường thử nghiệm:

~~~bash
java -Djava.net.preferIPv4Stack=true ChannelFamilyLab
java -Djava.net.preferIPv6Addresses=true ChannelFamilyLab
~~~

Lệnh thứ nhất có thể khiến phần IPv6 bị đánh dấu không khả dụng; lệnh thứ hai **không làm thay đổi địa chỉ literal** `127.0.0.1` hoặc `::1` trong chương trình, vì ở đây không có việc chọn giữa A và AAAA của hostname. Điều này thể hiện lý do nên dùng literal + `StandardProtocolFamily` trong bài kiểm tra họ IP.

**Không viết kiểm thử IPv6 chỉ bằng `InetAddress.getByName("localhost")`**: cách làm đó có thể trả địa chỉ IPv4 và vẫn khiến test pass. Nếu cần test khả năng phân giải dual-stack DNS, hãy viết một bài test DNS riêng, có kỳ vọng theo resolver và network topology của môi trường.

## 6. Kiểm thử với JUnit và chiến lược CI

Đặt `ChannelFamilyLab.java` của ví dụ vào `src/main/java` (hoặc package riêng phù hợp với dự án). Đoạn dưới là **class kiểm thử JUnit Jupiter**, không phải chương trình có `main`. Khi cả hai file ở cùng package, phương thức `exercise` và `canBindIPv6Loopback` có thể giữ quyền package-private như ví dụ.

**File `src/test/java/ChannelFamilyLabTest.java`:**

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.net.StandardProtocolFamily;
import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.Test;

class ChannelFamilyLabTest {
    @Test
    void ipv4LoopbackTcpAndUdp() throws Exception {
        ChannelFamilyLab.exercise(
                StandardProtocolFamily.INET, "127.0.0.1");
    }

    @Test
    void ipv6LoopbackWhenEnvironmentSupportsIt() throws Exception {
        Assumptions.assumeTrue(
                ChannelFamilyLab.canBindIPv6Loopback(),
                "IPv6 loopback is unavailable on this runner");

        ChannelFamilyLab.exercise(
                StandardProtocolFamily.INET6, "::1");
    }

    @Test
    void ipv6MustWorkOnDedicatedIpv6Runner() throws Exception {
        // Chỉ bật test này trong job được cấu hình bắt buộc IPv6;
        // bỏ @Test trên môi trường chạy matrix tùy chọn.
        assertTrue(ChannelFamilyLab.canBindIPv6Loopback(),
                "Runner is required to support IPv6 loopback");
        ChannelFamilyLab.exercise(
                StandardProtocolFamily.INET6, "::1");
    }
}
~~~

**Lưu ý khi đưa vào dự án:** ba test ở trên minh họa **hai chính sách khác nhau**. Test `ipv6MustWorkOnDedicatedIpv6Runner` **không nên bật đồng thời trong mọi runner tùy chọn**; chỉ đặt nó trong bộ test/profile/job bắt buộc IPv6 (hoặc dùng biến môi trường để bật phù hợp). Nếu để tất cả test chạy ở runner chỉ có IPv4, test cuối sẽ FAIL đúng như thiết kế. Không biến một cam kết IPv6 thành `assumeTrue` trên tất cả job, vì sẽ làm CI xanh dù yêu cầu không đạt.

Có thể cấu hình CI theo hai nhóm:

1. **Job tương thích phổ thông:** chạy test IPv4 bắt buộc và IPv6 tùy chọn với điều kiện môi trường. Ghi rõ số test đã chạy, số test bị **skipped**, tên OS/JDK và nguyên nhân.
2. **Job IPv6 bắt buộc:** runner/container/network namespace được cấp IPv6 loopback; chạy `java ChannelFamilyLab --require-ipv6` hoặc test assert khả năng IPv6 rồi kiểm tra TCP/UDP. Nếu không bind được hoặc không truyền dữ liệu được thì job FAIL.

Nếu sản phẩm cần **IPv6 ngoài máy**, bắt buộc bổ sung job kiểm thử với endpoint IPv6 reachable qua mạng test thật. Loopback test chỉ xác nhận network stack trong máy. Với sản phẩm hỗ trợ nhiều JDK, chọn đúng JDK mục tiêu cho test runner; Java 15 là mốc xuất hiện API `open(ProtocolFamily)` cho TCP, còn môi trường triển khai mới nên dùng JDK được nhà phân phối bảo trì.

### Khi nào dùng `Assumptions.assumeTrue`?

Trong JUnit, assumption thất bại nghĩa là **test bị bỏ qua/aborted**, không phải test đã chứng minh mạng IPv6 hoạt động. Điều này chỉ đúng khi IPv6 là năng lực *tùy chọn* và CI tổng hợp được số ca skip. Nếu feature yêu cầu IPv6, dùng assertion và để build FAIL. Test framework và build tool phải được cấu hình cho JDK được chọn; không nhầm “0 test bị lỗi” với “toàn bộ test đã chạy”.

## 7. Các lỗi thường gặp và cách sửa

| Biểu hiện | Diễn giải | Hành động kiểm tra |
| --- | --- | --- |
| `UnsupportedOperationException` từ `open(INET6)` | Provider/nền tảng không hỗ trợ họ socket yêu cầu | Kiểm tra IPv6 trên OS, container và startup properties; chỉ SKIP nếu IPv6 tùy chọn |
| `BindException` hoặc `SocketException` khi bind `::1` | IPv6 loopback chưa sẵn sàng, địa chỉ không gắn cho namespace, hoặc lỗi ràng buộc socket | Xác minh địa chỉ/interface và network namespace; giữ thông tin kiểu lỗi |
| `ConnectException: Connection refused` | Không có server lắng nghe đúng địa chỉ/cổng hoặc kết nối bị từ chối | Kiểm tra bind, port cấp phát, địa chỉ đích và thời điểm server sẵn sàng |
| TCP `read` trả về `-1` trước khi đủ dữ liệu | Peer đã đóng stream | Kiểm tra logic giao thức, partial I/O và trình tự đóng socket |
| UDP `receive` không có gói trước timeout | Gói chưa đến hoặc bị bỏ, sai destination, cấu hình mạng/filter | Kiểm tra `send`, port thực tế, firewall, timeout; không tự coi là “IPv6 unsupported” |
| Code dùng `localhost` rồi báo “IPv6 đã PASS” | Resolver đã trả về IPv4 | Dùng `::1` và `INET6` để test trực tiếp; tách test DNS |
| Chương trình nghe `::` nhưng vẫn có client IPv4 kết nối | Dual-stack platform-dependent | Kiểm tra chính sách IPv6-only và thực sự thử cả hai họ |
| JVM mới chạy được nhưng CI khác thất bại | Không cùng JDK/OS/namespace, Docker IPv6, DNS và properties | Ghi nhận runtime JDK, OS, địa chỉ bind, phiên bản container, mạng test |
| Test treo | TCP blocking `accept/read` hoặc network không phản hồi | Dùng nonblocking + `Selector`, timeout và deadline khi chạy production/CI |
| Port “đang được sử dụng” | Hard-code port giữa test chạy song song | Bind port `0` rồi đọc cổng thực; đóng channel bằng try-with-resources |
| Nhầm UDP với TCP | UDP không bảo đảm giao hàng hoặc thứ tự | Viết giao thức retry/ACK khi cần; test thông điệp, không đọc như luồng TCP |

**Cần tránh:** bắt mọi `IOException` trong test IPv6 rồi in `SKIP`. Ví dụ, khi bước capability đã xác nhận bind `::1` thành công, một lỗi `IOException` trong truyền dữ liệu có thể phản ánh bug code, route, port, firewall hoặc timeout. Phải báo FAIL để điều tra. Chỉ gate/skip ở nơi có chính sách IPv6 tùy chọn và có bằng chứng môi trường chưa sẵn sàng.

## 8. Checklist thực hành

- [ ] Chọn **JDK 17+** (có hai API TCP `open(ProtocolFamily)` từ Java 15), xác nhận `java --version` và `javac --version`.
- [ ] Dùng `StandardProtocolFamily.INET` với `127.0.0.1`; dùng `INET6` với `::1`, không suy luận từ `localhost`.
- [ ] Bind **port 0**, lấy đúng port thực từ channel; đóng tài nguyên bằng `try-with-resources`.
- [ ] Test **TCP** tạo kết nối và truyền đủ byte; test **UDP** gửi/nhận gói thực sự trong thời gian chờ hữu hạn.
- [ ] Giữ nguyên tính chất **TCP stream / UDP datagram**; thêm framing và deadline toàn bộ thao tác khi xây dựng ứng dụng thật.
- [ ] Tách **supported**, **unsupported/skipped** và **functional failure**; chỉ skip IPv6 khi không phải yêu cầu bắt buộc.
- [ ] Nếu CI quảng bá hỗ trợ IPv6, cấu hình job **--require-ipv6** hoặc assertion bắt buộc để job FAIL khi môi trường không đạt.
- [ ] Kiểm thử riêng dual-stack, DNS/AAAA, IPv6 global address và firewall/routing khi tính năng sản phẩm thực sự cần những khả năng đó.
- [ ] Không áp dụng các thủ thuật nội bộ hoặc API cũ không còn được hỗ trợ. Ưu tiên Java NIO channel và system properties có tài liệu chính thức, đồng thời xác nhận trên môi trường đích.

Tự kiểm tra `INET` và `INET6` bằng các channel cùng địa chỉ loopback xác định giúp tách **lỗi chọn họ địa chỉ** khỏi lỗi DNS và kết nối Internet. Với môi trường hỗ trợ IPv6, cả TCP lẫn UDP phải thực sự truyền thành công; với môi trường không hỗ trợ, báo rõ quyết định SKIP hoặc FAIL theo hợp đồng sản phẩm.

## Tài liệu chính thức

- [Java SE 25 – `ServerSocketChannel.open(ProtocolFamily)`, since Java 15](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/ServerSocketChannel.html)
- [Java SE 25 – `SocketChannel.open(ProtocolFamily)`, since Java 15](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/SocketChannel.html)
- [Java SE 25 – `DatagramChannel.open(ProtocolFamily)`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/DatagramChannel.html)
- [Java SE 25 – `StandardProtocolFamily.INET` và `INET6`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/StandardProtocolFamily.html)
- [Java SE 25 – Networking Properties, `preferIPv4Stack` và `preferIPv6Addresses`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/doc-files/net-properties.html)
- [Java SE 25 – `Selector`/`SelectionKey` và I/O không blocking](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/Selector.html)
- [JEP 373 – Reimplement Legacy DatagramSocket API (Java 15), bối cảnh hiện đại của networking stack](https://openjdk.org/jeps/373)
