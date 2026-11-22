# Đọc hợp đồng API mạng theo phiên bản JDK và phân biệt hành vi phụ thuộc nền tảng

Khi làm việc với Java Networking, tên một phương thức giống nhau trên hai máy **không có nghĩa mọi kết quả đều giống nhau**. Hợp đồng API quy định điều có thể dựa vào; phần triển khai của JDK, hệ điều hành, cấu hình mạng và môi trường chạy quyết định nhiều chi tiết quan sát được. Bài này hướng dẫn đọc tài liệu đúng phiên bản JDK, nhận diện câu chữ mang tính cam kết, và chuyển những điểm chưa được bảo đảm thành mã phòng vệ cùng phép kiểm thử phù hợp.

## 1. Ba lớp cần tách riêng khi đọc một hành vi mạng

| Lớp | Cần tìm ở đâu | Được kết luận điều gì? |
| --- | --- | --- |
| **API contract / specification** | Javadoc của đúng phiên bản Java SE/JDK: mô tả lớp, phương thức, tham số, giá trị trả về, ngoại lệ và ghi chú | Những điều API cam kết, giới hạn đầu vào, điều kiện lỗi, trạng thái sau lời gọi |
| **JDK implementation** | Implementation Note/Requirements, release notes, JEP, tài liệu của nhà phân phối JDK và các tùy chọn runtime | Cơ chế triển khai, tối ưu hóa và thay đổi theo JDK/vendor/build; chỉ xem là bảo đảm khi hợp đồng thực sự nói vậy |
| **Platform + environment** | Hệ điều hành, TCP/IP stack, DNS/hosts, firewall, container, IPv4/IPv6, quyền tiến trình, proxy và thiết bị mạng | Các địa chỉ, giao diện, cổng, thời gian, quyền, lựa chọn giao thức và lỗi thực tế trên máy đang chạy |

Ví dụ, `new ServerSocket(0)` có hợp đồng yêu cầu hệ thống chọn một cổng cục bộ. **Số cổng cụ thể** khác nhau giữa các lần chạy; không thể suy ra từ Javadoc. Tương tự, `InetAddress.getLoopbackAddress()` trả về địa chỉ loopback, nhưng không nên ràng buộc bài kiểm thử vào chuỗi đúng bằng `127.0.0.1`: hệ thống có thể chọn dạng IPv6.

Cần phân biệt thêm ba mức câu chữ:

- **“Returns”, “throws”, “must” và điều kiện nêu rõ**: cơ sở cho assertion về hợp đồng.
- **“May”, “typically”, “best effort”, “implementation-specific”, “platform-dependent”**: cho biết điều có thể thay đổi; không biến ví dụ thường gặp thành cam kết tuyệt đối.
- **“API Note”**: lời hướng dẫn cách dùng; **“Implementation Requirements”**: yêu cầu dành cho phần triển khai; **“Implementation Note”**: chi tiết về cách triển khai. Khi có khác biệt, đọc từng mục theo đúng vai trò của nó.

Không suy diễn từ một lần chạy thành đặc tả. Một kết quả là *bằng chứng của môi trường đó*, không đương nhiên là lời hứa cho mọi môi trường.

## 2. Chọn đúng phiên bản tài liệu trước khi kết luận

Trước hết xác định **JDK dùng để biên dịch**, **JDK thực sự chạy chương trình**, và **mốc Java tối thiểu mà sản phẩm hỗ trợ**. Ba giá trị có thể khác nhau, đặc biệt trong IDE, CI, Docker và production.

~~~bash
java -version
javac -version
java -XshowSettings:properties -version
~~~

Trên hệ thống dùng nhiều JDK, kiểm tra đường dẫn executable thực tế và cấu hình runtime của IDE/container. Trong Java, `Runtime.version().feature()` cho biết phiên bản tính năng của runtime; `System.getProperty("java.vendor")` và `System.getProperty("os.name")` hỗ trợ ghi nhận môi trường. Chúng không thay thế cho việc xác định bản cập nhật bảo mật/build cụ thể.

Ví dụ các tài liệu được **đóng phiên bản**:

| API/tài liệu | JDK 17 | JDK 21 |
| --- | --- | --- |
| `java.net.InetAddress` | [Javadoc 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InetAddress.html) | [Javadoc 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/InetAddress.html) |
| `java.net.ServerSocket` | [Javadoc 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html) | [Javadoc 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/ServerSocket.html) |
| `java.net.Socket` | [Javadoc 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html) | [Javadoc 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/Socket.html) |
| `java.nio.channels.SocketChannel` | [Javadoc 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html) | [Javadoc 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SocketChannel.html) |

Quy trình đọc một phương thức: (1) kiểm tra tên class, module, chữ ký và `Since`; (2) đọc mô tả ở *Method Detail*, không chỉ *Method Summary*; (3) ghi nhận `Parameters`, `Returns`, `Throws`; (4) đọc kỹ *API Note*, *Implementation Requirements/Note*, trạng thái deprecated và liên kết liên quan; (5) so sánh chính các mục đó giữa **hai JDK mục tiêu**, rồi xem release notes nếu xuất hiện khác biệt. `Since: 16` chỉ khẳng định API được giới thiệu từ Java 16, **không** cam kết mọi hệ điều hành và mọi cấu hình đều hỗ trợ tính năng đó.

Khi biên dịch trên JDK mới hơn để chạy trên Java 17, dùng `javac --release 17` để kiểm tra khả năng dùng API Java 17 và tạo bytecode tương ứng. Cờ này **không mô phỏng** DNS, TCP stack, quyền, thuật toán TLS hay khác biệt OS ở runtime; vẫn cần chạy test trên JDK và nền tảng mục tiêu.

## 3. Những ví dụ điển hình: đâu là hợp đồng, đâu là biến số?

### 3.1. Phân giải tên miền: `InetAddress`

`InetAddress.getAllByName(host)` dựa vào cơ chế phân giải tên mà runtime và hệ thống cung cấp. Số lượng, thứ tự và loại địa chỉ IPv4/IPv6 có thể thay đổi theo DNS, file hosts, VPN, chính sách địa chỉ và cấu hình JDK. Một hostname có thể có nhiều địa chỉ; không chọn phần tử đầu tiên với giả định rằng đó luôn là IPv4 hay máy chủ “chính”. Nếu phân giải thất bại, xử lý `UnknownHostException` theo ngữ cảnh, không biến thất bại tạm thời thành kết luận vĩnh viễn.

`InetAddress.isReachable(timeout)` là phép thử **best effort**. Tài liệu nêu rằng ICMP có thể bị chặn bởi quyền hoặc firewall và triển khai có thể thử cơ chế khác, ví dụ TCP Echo port 7. Vì vậy `false` **không chứng minh** dịch vụ HTTPS hoặc cổng ứng dụng của host bị hỏng; `true` cũng không chứng minh API ứng dụng đang khỏe. Muốn đánh giá một dịch vụ, thực hiện health check ở đúng protocol/endpoint với timeout riêng.

Cache DNS là một lớp độc lập. `networkaddress.cache.ttl` và `networkaddress.cache.negative.ttl` là **Java security properties**, không phải các system property thông thường có thể mặc nhiên cấu hình bằng `-Dnetworkaddress.cache.ttl=...`. Chính sách mặc định/khả năng tái phân giải phải đối chiếu tài liệu của JDK đang chạy; việc đổi cấu hình cũng không đồng nghĩa xóa các kết quả đã cache. Xem [Networking Properties, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/doc-files/net-properties.html).

### 3.2. Bind cổng, backlog và timeout: `ServerSocket` / `Socket`

`new ServerSocket(0, backlog, bindAddress)` yêu cầu bind địa chỉ chỉ định và xin hệ thống cấp cổng động; đọc cổng được cấp bằng `getLocalPort()`. Số `0` **không phải** cổng TCP thực tế để client kết nối. Với `bindAddress = null`, server có thể nhận kết nối trên các địa chỉ cục bộ thích hợp của hệ thống; khi chỉ làm thí nghiệm nội bộ, nên bind vào `InetAddress.getLoopbackAddress()`.

`backlog` là **độ dài hàng đợi được yêu cầu**, không phải phép bảo đảm “nhận chính xác N kết nối đồng thời”. Javadoc cho phép hệ điều hành/triển khai áp giới hạn hoặc bỏ qua tham số; backlog cũng không đồng nghĩa số request ứng dụng có thể xử lý. Không biến `backlog = 8` thành assertion rằng kết nối thứ chín chắc chắn bị từ chối.

`Socket.setSoTimeout(2000)` đặt timeout cho thao tác **đọc blocking** qua input stream sau khi option có hiệu lực; nó **không** tự động giới hạn thời gian `connect` và không phải deadline cho toàn bộ request. `Socket.connect(endpoint, timeout)` có timeout riêng cho bước kết nối; timeout `0` được hiểu là chờ vô hạn theo API tương ứng. Nếu read hết thời gian, `SocketTimeoutException` được ném và socket vẫn còn hợp lệ theo hợp đồng, nhưng ứng dụng vẫn phải tự quyết định có nên dùng lại kết nối đó theo giao thức của mình hay không. Thời gian quan sát bằng đồng hồ có thể vượt mốc danh nghĩa do scheduling và chi phí hệ thống; không dùng phép đo mili-giây tuyệt đối như một API guarantee.

### 3.3. Socket options: hỗ trợ tính năng khác với hiệu lực thực tế

`StandardSocketOptions` liệt kê các lựa chọn chuẩn, nhưng sự tồn tại của hằng số **không** có nghĩa mọi loại socket và mọi nền tảng đều nhận option đó. Với `SocketChannel` / `NetworkChannel`, hỏi `supportedOptions()` trước khi gọi `setOption(...)`; hợp đồng có thể ném `UnsupportedOperationException` nếu không hỗ trợ, `IllegalArgumentException` nếu giá trị không hợp lệ, hoặc `IOException` vì lỗi hệ thống. Một số option như kích thước buffer chịu giới hạn/điều chỉnh của kernel; kiểm tra lại qua `getOption(...)` khi cần quan sát giá trị hiệu lực.

Không dùng mặc định của một máy để suy ra mặc định chung: `SO_REUSEADDR`, `SO_RCVBUF`, `SO_SNDBUF`, `TCP_NODELAY`, hành vi multicast/broadcast và các tùy chọn mở rộng có phạm vi áp dụng khác nhau giữa TCP, UDP, Unix-domain socket, hệ điều hành và phiên bản JDK. Phải đọc phần **Socket options** của đúng loại channel và đúng phiên bản.

### 3.4. Giao diện mạng, địa chỉ và thay đổi cấu hình

`NetworkInterface.getNetworkInterfaces()` / `networkInterfaces()` phản ánh cấu hình mạng của máy tại thời điểm truy xuất. Tên như `eth0`, `en0`, chỉ số interface, số lượng NIC và địa chỉ gắn vào NIC đều là dữ liệu môi trường; mạng container, VPN hoặc hot-plug có thể làm thay đổi chúng ngay trong quá trình chạy. Tài liệu JDK mới còn nhấn mạnh đối tượng interface có thể là **snapshot**, cần lấy lại khi muốn có góc nhìn mới. Đừng coi chỉ số hoặc thứ tự interface là ID bền vững.

`InetAddress.getLoopbackAddress().isLoopbackAddress()` là loại invariant hợp lý để kiểm chứng; `getLoopbackAddress().getHostAddress().equals("127.0.0.1")` lại khóa cứng biểu diễn địa chỉ, nên kém di động hơn.

### 3.5. HTTP client, proxy và TLS

`HttpClient.version()` trong `java.net.http` trả về **phiên bản HTTP được ưu tiên** trong cấu hình client, không bảo đảm mọi phản hồi đều dùng HTTP/2. Proxy, server và điều kiện thương lượng có thể khiến request thực tế dùng HTTP/1.1; nếu cần biết kết quả, xem `HttpResponse.version()` của phản hồi. Tương tự, cấu hình proxy, trust store, chứng chỉ và giao thức TLS được hỗ trợ có thể thay đổi giữa runtime và môi trường; phân biệt cấu hình *mong muốn* với trạng thái *đã thương lượng*.

Lưu ý: `java.net.http.HttpClient` là API được chuẩn hóa từ Java 11; nhưng không được suy ra từ “API có mặt” rằng tất cả nhà cung cấp, proxy hoặc phiên bản protocol sẽ có cùng kết quả kết nối.

## 4. Đọc thay đổi theo phiên bản JDK bằng tình huống cụ thể

| Mốc tham khảo | Tính năng/điểm đọc | Kết luận đúng |
| --- | --- | --- |
| **JDK 11** | `java.net.http.HttpClient` chuẩn trong module `java.net.http` | Cần cả module/API thích hợp và khả năng thương lượng HTTP thực tế |
| **JDK 16** | `UnixDomainSocketAddress` và Unix-domain socket channels | Có API từ 16; runtime vẫn phụ thuộc OS, phiên bản OS, loại filesystem và quyền |
| **JDK 18** | SPI `java.net.spi.InetAddressResolverProvider` (JEP 418) | Có thể cắm resolver thay cho đường mặc định; mã tham chiếu trực tiếp SPI này không tương thích API Java 17 |
| **JDK 21** | Virtual threads và mô tả interrupt đối với `Socket` mặc định | Khi virtual thread bị interrupt trong những socket operation được Javadoc nêu, thao tác có thể đóng socket và ném ngoại lệ; không áp quy tắc ấy cho mọi phiên bản hoặc mọi custom implementation |

Với Unix-domain socket, `StandardProtocolFamily.UNIX`/`UnixDomainSocketAddress` dùng địa chỉ trên filesystem thay vì cặp IP:port. Không suy ra có tính di động tuyệt đối chỉ vì code compile: OS hoặc địa điểm tạo socket file có thể không hỗ trợ; đường dẫn, quyền và dọn socket file cũng cần xem xét. [Javadoc UnixDomainSocketAddress 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/UnixDomainSocketAddress.html) ghi `Since: 16`; release notes JDK 16 còn ghi nhận giới hạn hỗ trợ ở một số bản Windows.

Với DNS provider SPI được thêm ở JDK 18, khác biệt không chỉ là tên class mới: đường phân giải có thể được tùy chỉnh bởi ứng dụng/runtime. Khi so sánh JDK 17 và JDK 21, không mặc nhiên cho rằng mọi lời gọi `InetAddress` cùng đi qua một cơ chế resolver. Xem [JDK 18 release notes — JEP 418](https://www.oracle.com/java/technologies/javase/18-relnote-issues.html).

Với virtual threads (JDK 21), hãy đọc **đúng overload** của `Socket.connect`, `getInputStream` và phần ghi chú interrupt của Javadoc 21. Thay đổi semantics của interrupt không thể được phán đoán chỉ từ chữ ký phương thức vốn đã tồn tại ở JDK 17.

## 5. Hai chương trình Java 17+ để kiểm tra hợp đồng và môi trường

### Ví dụ A — chỉ assert điều API thật sự bảo đảm

Tệp `NetContractProbe.java`:

~~~java
import java.io.IOException;
import java.net.InetAddress;
import java.net.ServerSocket;

public class NetContractProbe {
    public static void main(String[] args) throws IOException {
        InetAddress loopback = InetAddress.getLoopbackAddress();
        System.out.println("Loopback: " + loopback.isLoopbackAddress());

        try (ServerSocket server = new ServerSocket(0, 8, loopback)) {
            System.out.println("Bound: " + server.isBound());
            System.out.println("Loopback bind: "
                    + server.getInetAddress().isLoopbackAddress());
            System.out.println("Ephemeral port assigned: "
                    + (server.getLocalPort() > 0));
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 NetContractProbe.java
java NetContractProbe
~~~

Khi môi trường cho phép mở một local server socket, stdout chính xác là:

~~~text
Loopback: true
Bound: true
Loopback bind: true
Ephemeral port assigned: true
~~~

Các assertion dùng **tính chất**, không dùng cổng được cấp hay chuỗi IP cụ thể. Tham số backlog `8` chỉ là yêu cầu gửi cho triển khai; ví dụ không kiểm tra sai rằng hệ điều hành sẽ xếp hàng chính xác 8 kết nối. Nếu máy/sandbox cấm bind socket hoặc tài nguyên cạn, chương trình có thể ném `IOException`; điều đó cho thấy precondition môi trường không thỏa, không làm đảo ngược hợp đồng khi bind thành công. Khối `try-with-resources` giải phóng socket ngay cả khi phát sinh lỗi bên trong.

### Ví dụ B — in sự thật của môi trường, không áp đặt stdout cố định

Tệp `NetEnvironmentProbe.java`:

~~~java
import java.net.InetAddress;
import java.net.StandardSocketOptions;
import java.nio.channels.SocketChannel;

public class NetEnvironmentProbe {
    public static void main(String[] args) throws Exception {
        String host = args.length == 0 ? "localhost" : args[0];

        System.out.println("JDK feature: " + Runtime.version().feature());
        System.out.println("Vendor: " + System.getProperty("java.vendor"));
        System.out.println("OS: " + System.getProperty("os.name"));

        for (InetAddress address : InetAddress.getAllByName(host)) {
            System.out.println(address.getClass().getSimpleName()
                    + ": " + address.getHostAddress());
        }

        try (SocketChannel channel = SocketChannel.open()) {
            boolean supported = channel.supportedOptions()
                    .contains(StandardSocketOptions.TCP_NODELAY);
            System.out.println("TCP_NODELAY supported: " + supported);

            if (supported) {
                channel.setOption(StandardSocketOptions.TCP_NODELAY, true);
                System.out.println("TCP_NODELAY configured: "
                        + channel.getOption(StandardSocketOptions.TCP_NODELAY));
            }
        }
    }
}
~~~

~~~bash
javac --release 17 NetEnvironmentProbe.java
java NetEnvironmentProbe localhost
java -Djava.net.preferIPv4Stack=true NetEnvironmentProbe localhost
java -Djava.net.preferIPv6Addresses=system NetEnvironmentProbe localhost
~~~

Không có “stdout chuẩn” duy nhất cho ví dụ B: major version, vendor, OS, địa chỉ trả về và option được hỗ trợ tùy máy. `localhost` cũng phụ thuộc cấu hình phân giải tên; nếu thất bại, chương trình có thể ném `UnknownHostException`. Các lệnh `-D` thể hiện cách **thử nghiệm** một cấu hình khác, không hứa rằng số địa chỉ hoặc thứ tự địa chỉ chắc chắn sẽ đổi. `java.net.preferIPv4Stack` và `java.net.preferIPv6Addresses` được kiểm tra khi JVM khởi động, nên chạy tiến trình mới khi thay đổi chúng; xem [Networking Properties, Java 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/doc-files/net-properties.html).

Đối với lỗi thực tế, log thêm exception type, địa chỉ đích/port (không ghi credentials), thời điểm, JDK build, proxy và bối cảnh IPv4/IPv6 để có thể tái hiện. Đừng bắt mọi `Exception` rồi in “network unavailable”: `UnknownHostException`, `ConnectException`, `SocketTimeoutException` và `UnsupportedOperationException` biểu đạt các tình huống khác nhau.

## 6. Biến hợp đồng thành kiểm thử có ý nghĩa

| Điều muốn xác nhận | Assertion tốt | Assertion dễ sai |
| --- | --- | --- |
| Loopback | `isLoopbackAddress() == true` | IP string luôn là `127.0.0.1` |
| Bind cổng động thành công | `isBound()` và `getLocalPort() > 0` | Cổng được cấp luôn là một số cố định |
| DNS | Mỗi kết quả là địa chỉ hợp lệ; ứng dụng chịu được nhiều kết quả/lỗi phân giải | `getAllByName("localhost")[0]` luôn là IPv4 |
| Backlog | Server có thể bind và chấp nhận kết nối trong điều kiện test xác định | Hàng đợi luôn chứa chính xác N kết nối |
| Reachability | Kiểm tra endpoint ứng dụng thực tế nếu muốn biết dịch vụ hoạt động | `isReachable(false)` suy ra toàn bộ dịch vụ đã chết |
| Socket option | Kiểm tra `supportedOptions()` và xử lý ngoại lệ/giá trị hiệu lực | Mọi OS hỗ trợ mọi `StandardSocketOptions` |
| HTTP version | Kiểm tra `HttpResponse.version()` sau request | `HttpClient.version() == HTTP_2` bảo đảm response dùng HTTP/2 |

Nên tách **unit test của logic xử lý kết quả** khỏi **integration test trên mạng thật**. Unit test tránh giả định hệ điều hành; integration test ghi môi trường, giữ timeout hữu hạn, dùng endpoint do test kiểm soát và chấp nhận những khác biệt được API cho phép. Khi một tính năng là tùy chọn theo OS/JDK, dùng capability probe rồi chọn đường fallback hoặc đánh dấu trường hợp test không áp dụng; không coi việc thiếu tính năng đó là lỗi kinh doanh nếu sản phẩm không cam kết hỗ trợ.

Một ma trận thử tối thiểu có thể gồm JDK 17 và 21 trên các OS sản phẩm thực tế hỗ trợ, môi trường có/không IPv6, container và máy thường, proxy/DNS cấu hình khác nhau. Chỉ đưa vào ma trận những kết hợp phù hợp phạm vi hỗ trợ của ứng dụng; bản vá JDK và chính sách mạng của CI cần được lưu trong bằng chứng.

## 7. Quy trình chẩn đoán khi hai máy chạy khác nhau

1. **Tái hiện câu hỏi hẹp:** phương thức nào, input nào, dự kiến điều gì, quan sát điều gì? Ghi exception class thay vì chỉ chép thông báo.
2. **Chốt phiên bản:** lưu `java -version`, `javac -version`, vendor/build, OS, target `--release` và API documentation URL cụ thể.
3. **Đọc hết hợp đồng:** đối chiếu `Parameters`, `Returns`, `Throws`, `Since`, API/Implementation Notes; gạch chân các từ “may”, “best effort”, “implementation-specific”.
4. **Phân loại claim:** điều được bảo đảm, điều chỉ là mặc định tùy môi trường, điều đặc trưng cho triển khai; đừng thử sửa một khác biệt được phép bằng cách khóa cứng giá trị.
5. **Đo tại runtime:** IP family, resolver, network interface, proxy, supported socket options, timeout và protocol đã thương lượng; không giả định thứ tự hoặc giá trị ngầm định.
6. **Thiết kế xử lý:** đặt timeout đúng thao tác, bắt lỗi có ý nghĩa, thử địa chỉ thay thế khi chiến lược kết nối yêu cầu, quản lý tài nguyên và chỉ retry có kiểm soát.
7. **Xác minh lại:** kiểm thử những invariant của API trên JDK/OS mục tiêu, đồng thời lưu log về biến số platform để phân biệt lỗi sản phẩm với đặc điểm môi trường.

Một số dấu hiệu điển hình cần dừng và mở đúng Javadoc: “ping Java false nên HTTP phải fail”, “backlog là giới hạn concurrent client”, “bật `SO_REUSEADDR` chắc chắn dùng lại được cổng”, “cứ ưu tiên HTTP/2 thì response sẽ là HTTP/2”, “API có `Since` thì mọi máy phải hỗ trợ”, hoặc “biên dịch `--release 17` thì runtime Java 17 trên Linux và Windows giống nhau”. Mỗi kết luận trên đều đi xa hơn hợp đồng API.

## 8. Câu hỏi tự kiểm tra

**Tình huống 1:** Java 17 trên laptop trả `127.0.0.1`, Java 21 trong container trả `::1` cho loopback. Có nhất thiết là bug? **Không.** Kiểm tra tính loopback và chính sách IPv4/IPv6; chỉ ép IPv4 khi sản phẩm có yêu cầu tương thích cụ thể.

**Tình huống 2:** `isReachable(1000)` trả `false` nhưng GET `/health` của server thành công. Có mâu thuẫn hợp đồng? **Không.** Phép probe mạng best effort khác protocol/port của dịch vụ.

**Tình huống 3:** Trên JDK mới, `javac --release 17` báo không tìm thấy `InetAddressResolverProvider`. Tại sao? **Vì SPI được giới thiệu từ JDK 18**; target API Java 17 không có class đó.

**Tình huống 4:** Cấu hình `backlog = 8` nhưng hệ điều hành xử lý lượng kết nối đang chờ khác dự đoán. Có vi phạm hợp đồng? **Không thể kết luận như vậy**: tài liệu cho phép triển khai giới hạn hoặc bỏ qua backlog được yêu cầu.

**Tình huống 5:** `HttpClient.version()` trả `HTTP_2` nhưng `HttpResponse.version()` là `HTTP_1_1`. Có nhất thiết sai? **Không.** Thuộc tính client chỉ biểu thị phiên bản ưu tiên; kết quả phụ thuộc phía server, proxy và thương lượng.

## Tài liệu gốc nên tra cứu

- [Java SE 17 — InetAddress](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InetAddress.html), [Networking Properties](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/doc-files/net-properties.html): phân giải tên, `isReachable` và DNS cache.
- [Java SE 17 — ServerSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html), [Java SE 21 — Socket](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/Socket.html): bind, backlog, timeout, ngoại lệ, interrupt.
- [Java SE 21 — NetworkChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/NetworkChannel.html), [SocketChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SocketChannel.html): socket options, channel lifecycle và giới hạn hỗ trợ.
- [Java SE 21 — HttpClient](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html), [UnixDomainSocketAddress](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/UnixDomainSocketAddress.html): cấu hình giao thức ưu tiên, khả năng Unix socket.
- [JDK 18 release notes — JEP 418](https://www.oracle.com/java/technologies/javase/18-relnote-issues.html), [Java SE 25 — Networking Properties](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/doc-files/net-properties.html): diễn biến API và cấu hình phụ thuộc phiên bản.

**Nguyên tắc sử dụng:** chọn **đúng tài liệu của runtime/target**, chỉ khẳng định điều mà hợp đồng thực sự bảo đảm, và kiểm tra các chi tiết do OS/JDK/mạng quyết định ngay trong môi trường sẽ triển khai.
