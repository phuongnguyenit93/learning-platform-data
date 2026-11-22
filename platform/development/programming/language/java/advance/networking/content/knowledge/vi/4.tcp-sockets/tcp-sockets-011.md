# Kiểm tra `supportedOptions` và khác biệt giữa JDK, hệ điều hành khi làm việc với TCP Socket

Một chương trình Java có thể biên dịch tốt trên JDK 17 nhưng không bật được một socket option khi chạy trên Windows, Linux hoặc một JDK build khác. Ngay cả khi `setOption(...)` thành công, kích thước buffer hay hành vi TCP đo được có thể khác giá trị yêu cầu. Để xây ứng dụng TCP đáng tin cậy, cần phân biệt **tên option tồn tại trong API**, **loại socket có hỗ trợ**, **việc cấu hình được chấp nhận** và **hiệu quả thực tế do kernel quyết định**.

Bài học này tập trung vào `java.net.Socket`, `java.net.ServerSocket` và NIO `SocketChannel`, `ServerSocketChannel` trên Java 17+, lấy `supportedOptions()` làm điểm xuất phát và so sánh ảnh hưởng của phiên bản JDK, nhà phân phối JDK, hệ điều hành, protocol family và trạng thái socket.

## 1. Bốn tầng kiểm tra khác nhau

~~~text
1. API Java có khai báo SocketOption<T>?
               |
               v
2. socketInstance.supportedOptions().contains(option)?
               |
               v
3. setOption(option, value) thành công?
               |
               v
4. getOption(option) trả gì, TCP/OS vận hành ra sao?
~~~

| Tầng | Câu hỏi đúng | Ví dụ |
| --- | --- | --- |
| **Có trong API** | Hằng `StandardSocketOptions.SO_REUSEPORT` có sẵn từ JDK nào? | Có từ Java 9, nhưng hiện diện trong API không có nghĩa OS nào cũng hỗ trợ |
| **Hỗ trợ bởi đối tượng** | `channel.supportedOptions().contains(SO_REUSEPORT)` có đúng trên channel này? | Có thể `true` ở một tổ hợp JDK/OS và `false` ở tổ hợp khác |
| **Cấu hình được chấp nhận** | `setOption(SO_REUSEPORT, true)` có ném ngoại lệ không? Đặt ở đúng thời điểm chưa? | Một số option phải đặt **trước bind** mới có ý nghĩa |
| **Giá trị/hiệu quả thực tế** | `getOption` trả gì? OS xử lý bind, ACK, TCP buffer, keep-alive ra sao? | `SO_RCVBUF` có thể bị kernel điều chỉnh; `SO_REUSEADDR` không bảo đảm luôn bind lại được cổng |

Do đó, mẫu kiểm tra đúng thường là:

~~~java
// Đoạn minh họa bên trong một phương thức có channel kiểu SocketChannel.
if (channel.supportedOptions()
        .contains(StandardSocketOptions.TCP_NODELAY)) {
    channel.setOption(StandardSocketOptions.TCP_NODELAY, true);
    Boolean effective =
            channel.getOption(StandardSocketOptions.TCP_NODELAY);
}
~~~

Ở đây phải `import java.net.StandardSocketOptions;`; `setOption/getOption` có thể ném `IOException`. Đoạn code chỉ minh họa thứ tự thao tác, chương trình độc lập và xử lý lỗi đầy đủ nằm ở phần sau. **Có mặt trong `supportedOptions` không đồng nghĩa lệnh `setOption` không bao giờ thất bại.**

## 2. `supportedOptions()` dùng trên loại socket nào?

### 2.1. Classic Socket API: `java.net`

Từ Java 9, ba loại đối tượng chính có API instance sau:

~~~java
Set<SocketOption<?>> clientOptions = socket.supportedOptions();
Set<SocketOption<?>> serverOptions = serverSocket.supportedOptions();
~~~

- `Socket` là đầu mối kết nối TCP bên client hoặc socket đã được `accept`.
- `ServerSocket` là socket lắng nghe, **không** phải luồng dữ liệu TCP đã kết nối. Nó thường hỗ trợ những option liên quan bind/listen/receive buffer, không nhất thiết hỗ trợ `TCP_NODELAY`.
- `SocketOption<T>` mô tả tên option và kiểu giá trị (`name()`, `type()`). Giá trị `T` ví dụ `Boolean` cho `TCP_NODELAY` và `Integer` cho `SO_RCVBUF`.
- `Socket.supportedOptions()` và `ServerSocket.supportedOptions()` trả một `Set<SocketOption<?>>`; tập này có thể chứa option mở rộng của implementation và có thể rỗng nếu không tạo được `SocketImpl`. API vẫn cho phép lấy tập hỗ trợ **sau khi socket đã đóng**, nhưng điều đó không làm `getOption/setOption` trên socket đóng hoạt động trở lại.

Không tự tạo `new SocketOption<...>()` chỉ để trùng tên rồi so sánh chuỗi. Khi kiểm tra option chuẩn, dùng chính hằng `StandardSocketOptions.TCP_NODELAY` / `SO_RCVBUF`; option mở rộng dùng hằng của module tương ứng.

Từ Java 9, `Socket`, `ServerSocket` và `DatagramSocket` đều có `getOption`, `setOption`, `supportedOptions`. Utility cũ `jdk.net.Sockets` đã **deprecated từ JDK 16**; với Java 17+ nên gọi phương thức trực tiếp trên đối tượng socket. Khi duy trì mã Java 8 cần kiểm tra API của JDK 8 riêng, không gọi nhầm những phương thức instance được thêm từ Java 9.

### 2.2. NIO Channels: `java.nio.channels`

`NetworkChannel` khai báo ba phương thức:

~~~java
Set<SocketOption<?>> supportedOptions();
<T> T getOption(SocketOption<T> name) throws IOException;
<T> NetworkChannel setOption(SocketOption<T> name, T value)
        throws IOException;
~~~

Đây là chữ ký **minh họa từ interface**; chương trình Java của người học không viết lại chúng. Các channel TCP cụ thể `SocketChannel` và `ServerSocketChannel` có thể chuyên biệt hóa kiểu trả về cho `setOption`, và còn các phương thức open, bind, connect, accept riêng.

- `SocketChannel.open()` tạo một channel TCP/IP phía kết nối, ban đầu chưa kết nối tới peer; có thể hỏi `supportedOptions()` ngay.
- `ServerSocketChannel.open()` tạo một channel lắng nghe, ban đầu chưa bind; hỏi hỗ trợ và cấu hình một số option trước bind.
- `SocketChannel.open(StandardProtocolFamily.UNIX)` (trên JDK hỗ trợ) tạo **Unix-domain socket**, không phải TCP/IP socket thông thường; tập options và ngữ nghĩa khác. Không lấy tập options của UNIX family để kết luận hỗ trợ TCP trên IP.
- Các `SelectorProvider`/`SocketImpl` được tùy biến có thể đưa ra tập option khác so với implementation mặc định của JDK.

Javadoc quy định `NetworkChannel.supportedOptions()` tiếp tục trả về tập option dù channel đã đóng. Ngược lại, `getOption/setOption` trên channel đóng có thể ném `ClosedChannelException`. **Supported** ở đây là *capability được công bố* cho loại đối tượng/triển khai đang chạy, không phải trạng thái kết nối, chất lượng mạng hay sự đồng ý của server từ xa.

### 2.3. Không nhầm option TCP với các cơ chế khác

- `StandardSocketOptions` là tập các option dạng `SocketOption<T>`; không phải danh sách mọi chức năng socket trong Java.
- `Socket.setSoTimeout(milliseconds)` điều khiển thời gian chờ **đọc blocking**, còn `Socket.connect(address, timeout)` điều khiển thời gian chờ kết nối. Chúng không xuất hiện như `StandardSocketOptions.SO_TIMEOUT`; `supportedOptions` không thay thế việc đọc API timeout.
- `ServerSocket.setSoTimeout` liên quan `accept`, không phải TCP keep-alive.
- `SO_KEEPALIVE` là cơ chế thăm dò TCP idle ở tầng OS, không tương đương application heartbeat hoặc health check của dịch vụ.
- `IP_MULTICAST_IF`, `IP_MULTICAST_TTL` và `SO_BROADCAST` phục vụ datagram/multicast, không phải các lựa chọn mặc định cần áp dụng cho TCP socket.
- `SSLSocket` còn có API riêng cho TLS (protocol/cipher/handshake). `supportedOptions` của socket không thể dùng thay `getSupportedProtocols()` hay kiểm tra TLS đã thương lượng.

## 3. Các option TCP thường gặp và độ phụ thuộc hệ thống

| Option | Kiểu `T` | Thường liên quan | Điều được phép kỳ vọng / cần lưu ý |
| --- | --- | --- | --- |
| `TCP_NODELAY` | `Boolean` | TCP client/connected socket | Bật để tắt thuật toán Nagle; không bảo đảm mỗi lần `write` đến peer tức thì |
| `SO_KEEPALIVE` | `Boolean` | TCP client/connected socket | Bật cơ chế TCP keep-alive của OS; thời gian/thử lại và hiệu quả phụ thuộc OS |
| `SO_SNDBUF` | `Integer` | TCP socket gửi dữ liệu | Kích thước buffer gửi là **gợi ý**; OS có thể điều chỉnh, đọc lại bằng `getOption` |
| `SO_RCVBUF` | `Integer` | TCP socket nhận, và một số listening socket | Kích thước buffer nhận là **gợi ý**; giá trị thực tế/giới hạn tùy OS |
| `SO_REUSEADDR` | `Boolean` | Bind socket/listening socket | Ngữ nghĩa phụ thuộc loại socket/OS; đặt **trước bind**; không cam kết bind trùng cổng thành công |
| `SO_REUSEPORT` | `Boolean` | Một số listening TCP socket | Hỗ trợ và ngữ nghĩa tùy loại socket/OS, có thể cho nhiều listener bind cùng address:port; luôn probe trước |
| `SO_LINGER` | `Integer` (giây) | Connected TCP socket | Điều khiển xử lý `close` khi còn dữ liệu gửi; dành cho blocking socket, không dùng bừa trên non-blocking channel |
| `IP_TOS` | `Integer` | Một số IP sockets | Giá trị ToS/traffic class là gợi ý; hạ tầng mạng có thể bỏ qua hoặc thay đổi |

Danh sách trên có chủ ý nói **“thường liên quan”**, không phải mọi option đều được bảo đảm trên mọi loại socket. Đọc `Socket`/`ServerSocket` hoặc `SocketChannel`/`ServerSocketChannel` Javadoc và **hỏi chính đối tượng thực tế** để có danh sách dùng được.

### 3.1. Buffer: `setOption(SO_RCVBUF, 16384)` không hứa kích thước chính xác

Với `SO_RCVBUF`, giá trị muốn cấu hình là một *hint* cho networking implementation. OS có thể áp min/max, điều chỉnh nội bộ hoặc cấp một kích thước được đọc lại khác con số yêu cầu; tương tự cho `SO_SNDBUF`. Một test kiểu:

~~~java
channel.setOption(StandardSocketOptions.SO_RCVBUF, 16 * 1024);
int effective = channel.getOption(StandardSocketOptions.SO_RCVBUF);
~~~

chỉ hợp lý khi channel hỗ trợ option, còn mở và giá trị yêu cầu hợp lệ. **Đừng assert `effective == 16384` như một yêu cầu di động**. Nếu ứng dụng đòi buffer tối thiểu theo thiết kế, kiểm tra giá trị được báo lại và đặt chính sách fallback/fail có thông báo rõ, đồng thời đo hiệu năng trên TCP traffic thật.

### 3.2. `SO_REUSEADDR` khác `SO_REUSEPORT`

`SO_REUSEADDR` có semantics liên quan tái sử dụng địa chỉ/cổng trong một số trạng thái TCP; hệ điều hành có thể xử lý `TIME_WAIT` và chính sách bind khác nhau. `SO_REUSEPORT` (có trong `StandardSocketOptions` từ Java 9) nhằm hỗ trợ tái sử dụng port ở các triển khai hỗ trợ; với TCP nó *thường* cho phép nhiều listening socket ở cùng địa chỉ và cổng. Hai option **không phải hai tên thay thế cho cùng một hành vi**.

Quy trình cho listener cần `SO_REUSEPORT`:

1. Mở listening socket/channel.
2. Hỏi `supportedOptions().contains(StandardSocketOptions.SO_REUSEPORT)`.
3. Nếu hỗ trợ, đặt `setOption(SO_REUSEPORT, true)` **trước khi bind**; vẫn bắt lỗi có thể xảy ra.
4. Bind vào địa chỉ/cổng được phép, sau đó kiểm thử cơ chế chia kết nối trên **OS/JDK đích**. Không suy ra từ một lần `setOption` thành công rằng kernel đang phân phối incoming connections như yêu cầu.

Không tự thử bind chồng trên cổng production. Với bài kiểm thử, dùng địa chỉ loopback/cổng được kiểm soát và dọn tài nguyên sau khi chạy.

### 3.3. Keep-alive và các tham số mở rộng

`SO_KEEPALIVE=true` yêu cầu OS dùng TCP keep-alive khi kết nối nhàn rỗi. Đây không phải timeout của một lệnh `read`, không giám sát logic của ứng dụng, và không luôn phát hiện peer lỗi trong thời gian mà developer tưởng tượng.

Module JDK-specific `jdk.net` có `ExtendedSocketOptions.TCP_KEEPIDLE`, `TCP_KEEPINTERVAL` và `TCP_KEEPCOUNT` (xuất hiện từ JDK 11) để mô tả các tham số thời gian/đếm probe theo **giây hoặc số lần**. Những option này có thể **không khả dụng trên một OS hoặc loại socket**, và giá trị chấp nhận được phụ thuộc kernel. Chỉ khi capability probe trả true mới có lý do thử get/set; một số option mở rộng còn là read-only, ví dụ `SO_INCOMING_NAPI_ID`. Không coi “có hằng trong class” là quyền gọi `setOption`.

`ExtendedSocketOptions.TCP_QUICKACK` (JDK 10+) cũng phụ thuộc OS; theo Javadoc đây **không phải công tắc vĩnh viễn**, vì xử lý TCP tiếp theo có thể lại thay đổi trạng thái delayed ACK. Bởi vậy, từ giá trị đọc lại ngay sau set không thể khẳng định tất cả các ACK sau này đều theo một chính sách cố định.

### 3.4. `SO_LINGER` và trạng thái channel

`SO_LINGER` có giá trị âm để tắt linger; giá trị không âm là khoảng thời gian tính bằng giây cho việc xử lý `close` khi còn dữ liệu chờ. Javadoc lưu ý nó dành cho **blocking socket**; khi bật trên non-blocking socket, hành vi `close` không được định nghĩa. Không thử đặt linger “để nhanh hơn” mà bỏ qua điều kiện chặn, protocol của ứng dụng và tác động đến dữ liệu chưa gửi.

## 4. Vì sao JDK và OS khác nhau?

### 4.1. Phiên bản API không đồng nhất với hỗ trợ runtime

| Mốc Java | Điều liên quan |
| --- | --- |
| **Java 7** | `NetworkChannel` và `StandardSocketOptions` phục vụ NIO channel |
| **Java 9** | `Socket/ServerSocket/DatagramSocket` có phương thức instance `supportedOptions()`, `setOption`, `getOption`; `SO_REUSEPORT` được chuẩn hóa thành hằng |
| **JDK 10** | Có `jdk.net.ExtendedSocketOptions.TCP_QUICKACK` trong JDK-specific API |
| **JDK 11** | Có các extended TCP keep-alive tuning options `TCP_KEEPIDLE`, `TCP_KEEPINTERVAL`, `TCP_KEEPCOUNT` |
| **JDK 16** | Utility cũ `jdk.net.Sockets` bị deprecated, ưu tiên API instance từ Java 9 |
| **JDK 17, 21 trở lên** | Cùng tên option có thể có mặt trong tài liệu nhưng tập `supportedOptions` thực tế vẫn tùy OS, build, loại socket và provider |

Đặc biệt, Java chạy với `javac --release 17` chỉ được kiểm tra về khả năng biên dịch theo API/bytecode tương ứng; **không mô phỏng** syscall, giới hạn buffer, socket option kernel hoặc tập extended options của runtime thực. Một bản JDK 21 chạy trên máy Windows và bản JDK 21 chạy trên Linux cũng không cần có tập option y hệt. Đừng tự nhận một bảng `supportedOptions` in từ máy cá nhân là “chuẩn Java 17” cho mọi máy.

### 4.2. Hệ điều hành, cấu hình kernel và quyền

- **Kernel TCP stack** quyết định option nào có backing implementation, giới hạn buffer/keep-alive ra sao và ngữ nghĩa cụ thể của reuse port.
- **Phiên bản hệ điều hành** có thể thay đổi option được expose ngay cả khi cùng JDK feature version.
- **Vendor/build/patch của JDK** có thể thay đổi implementation, networking provider hoặc cách ánh xạ option sang OS.
- **Container, policy sandbox hoặc quyền tiến trình** có thể giới hạn thao tác tạo socket, thay option hay bind; `supportedOptions` không đảm bảo phép toán cuối cùng được OS cho phép.
- **Protocol family** (IPv4/IPv6, TCP/IP so với Unix-domain) thay đổi tập option có ý nghĩa. Việc `SocketChannel.open(StandardProtocolFamily.UNIX)` tồn tại trong JDK không chứng minh môi trường hiện tại hỗ trợ Unix-domain sockets.
- **State/lifecycle** quan trọng: một số option nên được đặt trước `bind`/`connect`, một số chỉ có ý nghĩa sau khi TCP connection có dữ liệu, và mọi `getOption/setOption` trên channel đã đóng có thể thất bại.

Nên ghi **java.runtime.version**, **java.vendor**, **os.name**, **os.version**, **os.arch**, protocol family và socket type khi so sánh hai máy. Thêm cấu hình container/kern​​el nếu khác biệt thực tế ở runtime; chỉ những yếu tố liên quan mới cần đưa vào log sản phẩm.

### 4.3. Đọc hợp đồng ở đúng phiên bản JDK

Khi chuyển từ JDK 17 sang 21, không chỉ so tên hằng: đọc phần `Socket options` trong Javadoc của đúng `Socket`, `ServerSocket`, `SocketChannel`, `ServerSocketChannel`; sau đó đọc `StandardSocketOptions` và `jdk.net.ExtendedSocketOptions` theo đúng JDK đang triển khai.

Ba nguồn khác nhau cần đối chiếu:

1. **Spec** nêu lựa chọn chuẩn và kiểu giá trị (như `SO_RCVBUF` là `Integer`).
2. **Javadoc của đúng socket/channel** nêu các option chuẩn mà loại socket hỗ trợ, cùng khả năng có thêm option tùy implementation.
3. **Kết quả `supportedOptions` ở runtime** xác nhận capability của đối tượng đang mở trong môi trường thực. Cần tiếp tục `set/get` để biết giá trị được chấp nhận và đọc lại.

Ví dụ, tài liệu `jdk.net.ExtendedSocketOptions` trên JDK 21 có những mục mà tài liệu JDK 17 không có. Nhưng ngay cả một trường mới xuất hiện trong Javadoc của JDK cũng không có nghĩa mọi OS đang hỗ trợ option đó. Những API JDK-specific cũng không phải cam kết tương thích với mọi Java SE implementation.

## 5. Chương trình Java 17+: liệt kê chính xác option trên máy đang chạy

Tạo file **`TcpOptionInventory.java`**:

~~~java
import java.net.ServerSocket;
import java.net.Socket;
import java.net.SocketOption;
import java.net.StandardSocketOptions;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.util.Comparator;
import java.util.Set;

public final class TcpOptionInventory {
    private static void printOptions(
            String label, Set<SocketOption<?>> options) {
        System.out.println(label + ":");
        options.stream()
                .sorted(Comparator.comparing(SocketOption::name))
                .forEach(option -> System.out.println(
                        "  " + option.name()
                        + " (" + option.type().getSimpleName() + ")"));
    }

    public static void main(String[] args) throws Exception {
        System.out.println("Runtime: "
                + System.getProperty("java.runtime.version"));
        System.out.println("Vendor: "
                + System.getProperty("java.vendor"));
        System.out.println("OS: "
                + System.getProperty("os.name"));
        System.out.println("Architecture: "
                + System.getProperty("os.arch"));

        try (Socket client = new Socket();
             ServerSocket listener = new ServerSocket();
             SocketChannel clientChannel = SocketChannel.open();
             ServerSocketChannel listenerChannel =
                     ServerSocketChannel.open()) {

            printOptions("Socket", client.supportedOptions());
            printOptions("ServerSocket", listener.supportedOptions());
            printOptions("SocketChannel",
                    clientChannel.supportedOptions());
            printOptions("ServerSocketChannel",
                    listenerChannel.supportedOptions());

            System.out.println("Socket TCP_NODELAY: "
                    + client.supportedOptions()
                            .contains(StandardSocketOptions.TCP_NODELAY));
            System.out.println("ServerSocket TCP_NODELAY: "
                    + listener.supportedOptions()
                            .contains(StandardSocketOptions.TCP_NODELAY));
            System.out.println("Listener SO_REUSEPORT: "
                    + listenerChannel.supportedOptions()
                            .contains(StandardSocketOptions.SO_REUSEPORT));
        }
    }
}
~~~

~~~bash
javac --release 17 TcpOptionInventory.java
java TcpOptionInventory
~~~

**Không có một stdout cố định duy nhất:** các dòng `Runtime`, `Vendor`, `OS`, tên/kiểu option và kết quả `contains` phải được **in từ chính máy chạy**. Chương trình sắp xếp theo `option.name()` chỉ để dễ so sánh giữa các môi trường, vì `Set` không cam kết thứ tự. Khi chạy trên một hệ thống cụ thể, `SO_RCVBUF (Integer)`, `TCP_NODELAY (Boolean)` hoặc các extended option có thể xuất hiện trong phần phù hợp với socket/provider đang chạy.

Ví dụ này **không kết nối mạng tới host ngoài** và không bind cổng; nó chỉ tạo đối tượng/socket descriptor rồi thu thập capability. Việc mở socket/channel vẫn có thể ném `IOException` do hạn chế sandbox hoặc tài nguyên OS; điều đó cần ghi thành kết quả môi trường. `try-with-resources` đóng toàn bộ đối tượng ngay cả khi có lỗi.

Để so sánh JDK 17 và JDK 21, chạy cùng source với `--release 17` trên **hai runtime thật**, lưu riêng stdout, và chỉ coi sự khác biệt được tìm thấy là bằng chứng về **cặp môi trường đó**. Kết luận tổng quát cần thêm tài liệu và thử nghiệm trên nền tảng sản phẩm hỗ trợ.

## 6. Chương trình Java 17+: kiểm tra, đặt option, đọc lại và xử lý lỗi

Tạo file **`TcpOptionReadback.java`**:

~~~java
import java.io.IOException;
import java.net.SocketOption;
import java.net.StandardSocketOptions;
import java.nio.channels.SocketChannel;

public final class TcpOptionReadback {
    private static <T> void tryOption(
            SocketChannel channel,
            SocketOption<T> option,
            T requested) {

        if (!channel.supportedOptions().contains(option)) {
            System.out.println(option.name() + ": UNSUPPORTED");
            return;
        }

        try {
            channel.setOption(option, requested);
            T readback = channel.getOption(option);
            System.out.println(option.name()
                    + ": requested=" + requested
                    + ", readback=" + readback);
        } catch (UnsupportedOperationException
                | IllegalArgumentException
                | SecurityException
                | IOException ex) {
            System.out.println(option.name()
                    + ": ERROR " + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) throws IOException {
        try (SocketChannel channel = SocketChannel.open()) {
            tryOption(channel, StandardSocketOptions.TCP_NODELAY, true);
            tryOption(channel, StandardSocketOptions.SO_RCVBUF,
                    16 * 1024);

            System.out.println("SO_REUSEPORT advertised: "
                    + channel.supportedOptions()
                            .contains(StandardSocketOptions.SO_REUSEPORT));
        }
    }
}
~~~

~~~bash
javac --release 17 TcpOptionReadback.java
java TcpOptionReadback
~~~

Trên runtime hỗ trợ và cho phép cấu hình `TCP_NODELAY`, dòng tương ứng thường là:

~~~text
TCP_NODELAY: requested=true, readback=true
~~~

Những dòng khác cố ý **không áp một stdout duy nhất**: `SO_RCVBUF` có thể khác `16384`; `SO_REUSEPORT` có thể được quảng bá hoặc không; nếu `setOption` thất bại, chương trình in class của ngoại lệ. Đây mới là điều quan trọng cần học từ probe: **tập capability, kết quả set, giá trị readback là ba tín hiệu khác nhau**.

`tryOption` không tự kết luận option mang lại cải thiện hiệu năng. Với option dạng hint như `SO_RCVBUF`, readback chỉ cho biết kích thước báo lại; với `SO_REUSEPORT`, chương trình chỉ truy vấn, **không** bật tính năng. Khi đang thử nghiệm một server thật, cần quyết định option là **bắt buộc** hay **tùy chọn**, sau đó mới chọn log + fallback hoặc fail fast.

Nếu `TCP_NODELAY` thực sự là điều kiện bắt buộc cho mục tiêu của hệ thống, không chỉ in lỗi rồi tiếp tục. Hãy biến kết quả thành exception cấu hình với thông tin môi trường, và kiểm tra thêm giá trị readback. Ngược lại, với tối ưu hóa không bắt buộc, có thể tắt tối ưu hóa đó khi capability bị thiếu mà vẫn giữ đúng chức năng mạng.

## 7. Đọc ngoại lệ đúng: tại sao `contains(option)` vẫn chưa đủ?

| Quan sát | Ý nghĩa hợp lý | Cách xử lý |
| --- | --- | --- |
| `supportedOptions().contains(option) == false` | Socket/channel này không công bố option | Không gọi `setOption`; chọn fallback hoặc thông báo yêu cầu nền tảng |
| `UnsupportedOperationException` | API/implementation không hỗ trợ thao tác option đang yêu cầu | Ghi loại socket, provider, option, runtime; kiểm tra lại API đúng instance |
| `IllegalArgumentException` | Giá trị không hợp lệ cho option | Sửa loại/miền giá trị, không retry mù quáng |
| `ClosedChannelException` hay `IOException` | Channel/socket đã đóng hoặc lỗi I/O/OS | Kiểm tra lifecycle, cấu hình nguồn lực và errno khi có; không gộp thành “option không hỗ trợ” |
| `SecurityException` | Có rào cản quyền nếu runtime áp dụng kiểm soát tương ứng | Xử lý policy/quyền, không âm thầm tắt bảo mật |
| `setOption` thành công, `getOption` khác request | Kernel có thể điều chỉnh hint hoặc giá trị bị clamp | Đọc hợp đồng option, đánh giá giá trị thực cần cho ứng dụng |
| `set/get` cho cùng giá trị nhưng TCP khác kỳ vọng | Mạng/OS/protocol còn nhiều biến số | Test lưu lượng thật; đo latency/throughput bằng workload kiểm soát |

Không phải mọi `SocketOption` trong tập hỗ trợ đều **có thể set**. Ví dụ `jdk.net.ExtendedSocketOptions.SO_INCOMING_NAPI_ID` là read-only theo Javadoc; nếu nó xuất hiện trong `supportedOptions`, vẫn phải dùng `getOption` đúng trạng thái, **không** tự động `setOption`.

Ngoài ra, một số option có thể đọc/đặt ở trạng thái chưa kết nối, nhưng các option khác có nghĩa khi kết nối đã được thiết lập hoặc sau khi có gói tin. Tài liệu API của từng option và runtime phải quyết định thời điểm thử nghiệm.

## 8. Quy trình triển khai an toàn cho TCP client/server

### 8.1. Với client TCP

1. Xác định yêu cầu: ví dụ cần latency thấp thì xem xét `TCP_NODELAY`, cần phát hiện kết nối idle lâu thì đánh giá `SO_KEEPALIVE` và application heartbeat.
2. Tạo `Socket`/`SocketChannel` **đúng triển khai** đang dùng, rồi hỏi `supportedOptions` của chính đối tượng đó.
3. Chỉ gọi `setOption` khi hỗ trợ; dùng giá trị hợp lệ, xử lý lỗi I/O, closed state, optional-vs-required.
4. Đọc lại `getOption` nếu cần quan sát giá trị hiệu lực, đặc biệt buffer sizes.
5. Kết nối với connect timeout phù hợp; đặt thêm read timeout/deadline ở API có hỗ trợ. `SO_KEEPALIVE` không thay thế các timeout này.
6. Test I/O thực tế. `TCP_NODELAY` không có nghĩa một `write` Java chắc chắn tương ứng đúng một TCP packet, và `SO_KEEPALIVE` không xác nhận ứng dụng peer đang xử lý nghiệp vụ.

### 8.2. Với listening TCP server

1. Tạo `ServerSocket` hoặc `ServerSocketChannel`, **chưa bind**.
2. Xác định `SO_REUSEADDR`, `SO_REUSEPORT`, `SO_RCVBUF` nào có ý nghĩa trong môi trường đích.
3. Kiểm tra support, đặt những option về binding **trước `bind`**. Đừng dùng `SO_REUSEPORT` như thay thế tự động cho `SO_REUSEADDR`.
4. Bind bằng một địa chỉ rõ ràng; khi test, ưu tiên loopback và cổng động `0` để tránh ảnh hưởng dịch vụ khác.
5. Sau `accept`, đọc/set các option dành cho **socket kết nối** nếu cần. `TCP_NODELAY` là option của đường dữ liệu, không phải thuộc tính cần áp lên listening `ServerSocket`.
6. Test số kết nối và hành vi hàng đợi dưới tải có kiểm soát. `backlog` cũng là tham số hệ điều hành xử lý; nó không phải một socket option có thể suy ra từ `supportedOptions`.

Ví dụ ý tưởng đúng với `ServerSocketChannel` (đoạn minh họa, cần đặt trong phương thức `throws IOException` và import các class tương ứng):

~~~java
try (ServerSocketChannel server = ServerSocketChannel.open()) {
    if (server.supportedOptions()
            .contains(StandardSocketOptions.SO_REUSEPORT)) {
        server.setOption(StandardSocketOptions.SO_REUSEPORT, true);
    }

    server.bind(new InetSocketAddress(
            InetAddress.getLoopbackAddress(), 0));
}
~~~

Code này **chỉ thể hiện thứ tự** (probe → set trước bind → bind). Nếu `setOption` thất bại, ngoại lệ phải được caller xử lý theo chính sách sản phẩm; nếu thành công, việc nhiều listener chia sẻ port vẫn cần bài test OS-specific. Không nên tự thực hiện thử nghiệm share port trên máy production.

## 9. So sánh hai môi trường bằng một ma trận có bằng chứng

Giả sử một ứng dụng định sử dụng `SO_REUSEPORT` khi chạy local, nhưng trên CI bị `UNSUPPORTED`. Đừng bắt đầu từ việc ép `true` hoặc đổi code thành `SO_REUSEADDR`. Hãy ghi lại các dữ liệu sau:

| Dữ liệu | Máy A | Máy B |
| --- | --- | --- |
| `java -version` và JDK vendor/build | Giá trị lấy từ lệnh thực tế | Giá trị lấy từ lệnh thực tế |
| `os.name`, `os.version`, `os.arch` | Giá trị thực tế | Giá trị thực tế |
| TCP socket type | `ServerSocketChannel` hay `ServerSocket` | Cùng loại được sử dụng |
| IP protocol family | IPv4/IPv6 theo môi trường | IPv4/IPv6 theo môi trường |
| `supportedOptions` đã sort | In bằng inventory probe | In bằng inventory probe |
| `setOption` | Thành công / loại ngoại lệ | Thành công / loại ngoại lệ |
| `getOption` | Giá trị được OS báo lại | Giá trị được OS báo lại |
| Kết quả bind và traffic test | Quan sát thực tế | Quan sát thực tế |

**Chỉ những cột có bằng chứng mới được điền giá trị.** Ma trận này cho phép xác định: option thực sự không có, có nhưng không set được, hoặc set được nhưng hệ điều hành không có semantics ứng dụng dự kiến. Đó là ba lớp lỗi khác nhau và cần hướng xử lý khác nhau.

Khi một option là optional optimization, ghi capability, bỏ qua nếu thiếu và bảo đảm chức năng chính vẫn chạy. Khi option bắt buộc vì kiến trúc (ví dụ hệ thống dựa vào nhiều listener trên cùng port), validate ngay khi khởi động, fail fast có thông báo yêu cầu nền tảng, và test triển khai trên đúng JDK/OS được hỗ trợ.

## 10. Những khẳng định sai thường gặp

**“Có hằng `SO_REUSEPORT` trong Java nghĩa là mọi máy đều bật được.”** Sai. Hằng chuẩn xuất hiện ở API nhưng option có thể thiếu trong `supportedOptions` của một socket cụ thể.

**“`supportedOptions` chứa option thì `setOption` sẽ luôn thành công.”** Sai. Còn type/range, lifecycle, quyền và lỗi I/O. Có option read-only.

**“`setOption(SO_RCVBUF, 16384)` thành công, nên TCP buffer bằng chính xác 16 KiB.”** Sai. Đây là hint và OS có thể điều chỉnh; kiểm tra readback và hiệu năng.

**“`SO_REUSEADDR` bảo đảm hai server cùng listen trên một cổng.”** Sai. Ngữ nghĩa thay đổi theo TCP stack; `SO_REUSEPORT` cũng cần được hỗ trợ và kiểm nghiệm riêng.

**“`SO_KEEPALIVE` thay cho connect/read timeout hoặc health check.”** Sai. Nó là TCP idle probing, không phải deadline nghiệp vụ hay phép thử hoạt động của endpoint.

**“Mọi option có trong `StandardSocketOptions` phù hợp với `ServerSocket`.”** Sai. Listening socket và connected socket có các nhóm hỗ trợ khác nhau; không áp `TCP_NODELAY` lên listening socket nếu API không công bố nó.

**“Đã đóng channel thì `supportedOptions` cũng phải throw.”** Sai. Hợp đồng `NetworkChannel` và socket classic mô tả việc vẫn trả tập options sau close; nhưng `set/get` có thể ném ngoại lệ.

**“Dùng cùng JDK 21 thì kết quả trên mọi OS phải giống nhau.”** Sai. Kernel, provider, quyền và OS version thay đổi capability và hành vi.

## 11. Bài tập tự kiểm tra

**Câu 1.** Vì sao kiểm tra `StandardSocketOptions.SO_REUSEPORT != null` không đủ?  
**Đáp án:** Không chứng minh option được đối tượng socket hỗ trợ. Cần `supportedOptions().contains(SO_REUSEPORT)`, thử cấu hình hợp lệ và xác minh hành vi ở OS đích.

**Câu 2.** `ServerSocket.supportedOptions()` có nhất thiết chứa `TCP_NODELAY` giống `Socket`?  
**Đáp án:** Không. `ServerSocket` dùng để lắng nghe; `TCP_NODELAY` là option xử lý việc gửi các segment trên socket TCP có dữ liệu. Hỏi đúng đối tượng và đọc contract của loại socket.

**Câu 3.** `SO_RCVBUF` yêu cầu 32 KiB nhưng `getOption` báo giá trị khác. Có chắc Java sai?  
**Đáp án:** Không. Giá trị option dạng hint có thể bị kernel điều chỉnh; kiểm tra Javadoc và yêu cầu thực tế của ứng dụng.

**Câu 4.** `supportedOptions()` vẫn trả danh sách sau `close()`; có được gọi tiếp `getOption`?  
**Đáp án:** Không nên. `supportedOptions` mô tả capability, còn `getOption` trên socket/channel đóng có thể ném `IOException`/`ClosedChannelException`.

**Câu 5.** Muốn bật `SO_REUSEPORT` cho listener, nên gọi trước hay sau bind?  
**Đáp án:** Trước `bind`, sau khi xác nhận support; sau đó kiểm tra lỗi và test trên OS/JDK đích.

**Câu 6.** `ExtendedSocketOptions.TCP_QUICKACK` có cho phép bật một lần rồi tin rằng mọi ACK luôn được gửi tức thì?  
**Đáp án:** Không. Theo Javadoc, TCP protocol processing có thể thay đổi trạng thái này sau đó.

**Câu 7.** Cùng chương trình, khi chạy JDK khác vendor trên OS khác lại liệt kê nhiều option hơn. Hướng xử lý?  
**Đáp án:** Ghi runtime/OS/provider, phân biệt option chuẩn và mở rộng, so sánh capability và thử nghiệm trên matrix hỗ trợ. Không khóa cứng số lượng hay thứ tự options vào unit test.

## 12. Checklist trước khi dùng socket option trong sản phẩm

- Đọc **Javadoc đúng JDK và loại socket**. Hãy xác nhận option đó thuộc TCP/IP, listening socket hay channel nào.
- Hỏi `supportedOptions()` ngay trên **đúng object** sẽ được cấu hình.
- Phân biệt **tùy chọn tối ưu hóa** và **điều kiện bắt buộc của kiến trúc**.
- Đặt option tại **thời điểm hợp lệ**, nhất là `SO_REUSEADDR` / `SO_REUSEPORT` trước bind.
- Bắt ngoại lệ riêng cho `UnsupportedOperationException`, `IllegalArgumentException`, `IOException` và quyền nếu có.
- Nếu hợp đồng ghi hint hoặc OS-specific, đọc lại `getOption` và thực hiện kiểm thử hành vi thật.
- Không giả định default, số lượng option, thứ tự `Set`, buffer size, keep-alive timer hay port sharing giống trên mọi OS.
- Tái hiện trên ma trận JDK/OS/provider thật, ghi build cụ thể và hạn chế thay đổi cổng production trong quá trình thử.
- Đóng socket/channel bằng `try-with-resources`; không dùng `supportedOptions` làm bằng chứng tài nguyên vẫn mở.
- Khi có option trong `jdk.net.ExtendedSocketOptions`, xác nhận JDK-specific module và chính sách hỗ trợ; không tự suy ra mọi thuộc tính đều writable.

## Tài liệu chính thức để đối chiếu

- [Java SE 17 — `Socket`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html) và [`ServerSocket`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html): `setOption`, `getOption`, `supportedOptions`, tập chuẩn và hành vi sau close.
- [Java SE 17 — `NetworkChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/NetworkChannel.html), [`SocketChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html), [`ServerSocketChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ServerSocketChannel.html): capability và API NIO.
- [Java SE 17 — `StandardSocketOptions`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/StandardSocketOptions.html): kiểu giá trị và những điều kiện/giới hạn của từng option, đặc biệt buffer, reuse, linger và keep-alive.
- [JDK 17 — `ExtendedSocketOptions`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.net/jdk/net/ExtendedSocketOptions.html), [JDK 21 — `ExtendedSocketOptions`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.net/jdk/net/ExtendedSocketOptions.html): tùy chọn mở rộng và phạm vi platform-specific.
- [JDK 17 — `jdk.net.Sockets`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.net/jdk/net/Sockets.html): utility cũ đã deprecated; migration sang API instance.
- [Java SE 21 — `Socket`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/Socket.html), [`NetworkChannel`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/NetworkChannel.html): đối chiếu cùng contract khi nâng cấp runtime.

**Nguyên tắc nhớ lâu:** `StandardSocketOptions` chỉ cho biết **tên option chuẩn**; `supportedOptions` cho biết **đối tượng hiện tại công bố khả năng nào**; `setOption` và `getOption` cho biết **thao tác cấu hình và readback**; chỉ kiểm thử thực tế mới nói được **TCP hoạt động ra sao trên OS/JDK đích**.
