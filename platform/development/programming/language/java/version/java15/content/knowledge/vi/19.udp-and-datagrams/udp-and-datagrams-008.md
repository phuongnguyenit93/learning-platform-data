# setOption, getOption và supportedOptions với UDP/Datagram trong Java 15+

## 1. Bài toán: cấu hình đúng một UDP socket

UDP truyền các **datagram** độc lập, không tạo luồng byte đáng tin cậy như TCP. Trong Java, hai API thường dùng là:

- `java.net.DatagramSocket`: gửi/nhận `DatagramPacket`, phù hợp code I/O trực tiếp.
- `java.nio.channels.DatagramChannel`: kênh datagram NIO, có thể dùng với `Selector`, `ByteBuffer` và mô hình non-blocking.

Khi triển khai UDP service, ứng dụng thường muốn thay đổi kích thước bộ đệm nhận/gửi, bật nhận/gửi broadcast, cho phép dùng lại địa chỉ, chỉ định giao diện multicast hoặc đặt TTL. Các lựa chọn này gọi là **socket options**.

Ba phương thức trọng tâm là:

~~~java
Set<SocketOption<?>> options = socket.supportedOptions();
socket.setOption(StandardSocketOptions.SO_RCVBUF, 16 * 1024);
int actual = socket.getOption(StandardSocketOptions.SO_RCVBUF);
~~~

Đây là đoạn minh họa (giả sử `socket` là `DatagramSocket` hoặc `DatagramChannel` hợp lệ, có các import cần thiết). Luồng tư duy đúng:

~~~text
Lấy socket/channel
       │
       ▼
supportedOptions()     Socket/OS/provider có nhận option này không?
       │
       ▼
setOption(option, v)   Yêu cầu thay đổi thiết lập
       │
       ▼
getOption(option)      Đọc giá trị thực tế hiện có
       │
       ▼
bind/send/receive      Vận hành UDP và theo dõi hành vi
~~~

**Điểm phân biệt:** `setOption` **yêu cầu** hệ thống cấu hình; đối với những lựa chọn như kích thước buffer, OS có thể điều chỉnh khác giá trị yêu cầu. `getOption` giúp đọc lại giá trị được thiết lập hoặc được trả về, **không** chứng minh rằng chất lượng mạng, lưu lượng hay QoS được bảo đảm.

### Liên quan đến Java 15

Các phương thức `DatagramSocket.setOption`, `getOption` và `supportedOptions` **đã có từ Java 9**; chúng không phải API vừa xuất hiện lần đầu trong Java 15. Java 15 có nâng cấp triển khai DatagramSocket ở mức JDK (JEP 373), nhưng cách dùng socket options ở đây là **API chuẩn đang được hỗ trợ đến Java hiện hành**.

Tránh sử dụng helper cũ `jdk.net.Sockets.setOption/getOption/supportedOptions`: các phương thức helper này đã bị **deprecated từ Java 16**. Code hiện đại nên gọi trực tiếp `DatagramSocket` hoặc `DatagramChannel`.

## 2. Hiểu kiểu dữ liệu của `SocketOption<T>`

`java.net.SocketOption<T>` là mô tả một lựa chọn socket có **kiểu giá trị `T`**. Ví dụ:

~~~java
SocketOption<Integer> receiveBuffer = StandardSocketOptions.SO_RCVBUF;
SocketOption<Boolean> reuseAddress = StandardSocketOptions.SO_REUSEADDR;

String optionName = receiveBuffer.name();    // "SO_RCVBUF"
Class<Integer> type = receiveBuffer.type();  // Integer.class
~~~

`SocketOption<T>` không phải chính giá trị cấu hình. Nó là **khóa được định kiểu** để gọi `setOption/getOption`:

~~~java
socket.setOption(StandardSocketOptions.SO_RCVBUF, 8192); // Integer
int size = socket.getOption(StandardSocketOptions.SO_RCVBUF);

socket.setOption(StandardSocketOptions.SO_REUSEADDR, true); // Boolean
boolean enabled = socket.getOption(StandardSocketOptions.SO_REUSEADDR);
~~~

Java dùng generics để ràng buộc kiểu tại thời điểm biên dịch: `SO_RCVBUF` nhận `Integer`, không nhận `Boolean`. Tuy nhiên **kiểu đúng chưa bảo đảm giá trị hợp lệ**: chẳng hạn kích thước buffer âm hoặc phạm vi TTL sai có thể bị từ chối.

**Không** tự tạo một `SocketOption` mới chỉ bằng cách đặt tên `"SO_RCVBUF"` rồi mong JVM đối xử như hằng chuẩn. Hãy dùng hằng `StandardSocketOptions` chính thức và các option mở rộng chỉ khi có provider/đặc tả tương ứng.

## 3. `supportedOptions()`: kiểm tra trước khi cấu hình

`supportedOptions()` trả về một `Set<SocketOption<?>>` chứa các option mà socket hoặc channel **hỗ trợ** trong môi trường đang chạy:

~~~java
import java.net.DatagramSocket;
import java.net.SocketOption;
import java.net.StandardSocketOptions;
import java.util.Set;

try (DatagramSocket udp = new DatagramSocket(null)) {
    Set<SocketOption<?>> available = udp.supportedOptions();
    if (available.contains(StandardSocketOptions.SO_RCVBUF)) {
        udp.setOption(StandardSocketOptions.SO_RCVBUF, 16 * 1024);
    }
}
~~~

Ví dụ này chạy độc lập khi đặt bên trong một phương thức có `throws Exception` hoặc xử lý lỗi tương ứng. Socket được tạo **chưa bind** bằng `new DatagramSocket(null)`, thuận tiện cho các option cần thiết lập trước khi gắn cổng.

**Lưu ý:**

1. Danh sách option thực sự có thể phụ thuộc **loại socket, hệ điều hành, provider và cấu hình**. Không hardcode danh sách option rồi giả định giống trên mọi máy.
2. Một option xuất hiện trong `StandardSocketOptions` **không đồng nghĩa** mọi loại socket hỗ trợ nó.
3. Một hệ thống có thể hỗ trợ thêm những option mở rộng riêng của provider; chúng không nhất thiết di động.
4. Với `DatagramSocket` và `NetworkChannel`, đặc tả cho phép gọi `supportedOptions()` **sau khi socket/channel đã đóng**, và phương thức vẫn trả tập option được hỗ trợ; điều này khác với việc tiếp tục `setOption/getOption`.
5. `supportedOptions()` kiểm tra **capability**, không cam kết gọi `setOption` với mọi giá trị đều thành công hoặc môi trường mạng sẽ thực hiện đúng kỳ vọng.
6. Không nên ghi log thông tin hệ điều hành/socket option quá chi tiết vào luồng request ở production nếu không có mục đích chẩn đoán; có thể log tại lúc khởi tạo và chỉ số vận hành phù hợp.

### 3.1. Khi nào bắt buộc dùng kiểm tra này?

Nên kiểm tra trước với những option **phụ thuộc nền tảng** như `SO_REUSEPORT`. Nếu thiếu, ứng dụng cần lựa chọn chế độ không dùng tính năng đó hoặc báo lỗi cấu hình có kiểm soát, thay vì crash bất ngờ trong đường xử lý request.

Với các option chuẩn được mô tả cho một UDP socket IP thông thường, kiểm tra vẫn hữu ích khi cần chạy nhiều JDK/vendor/OS và khi cài đặt provider riêng.

## 4. `setOption` và `getOption`: hợp đồng và xử lý lỗi

Trên `DatagramSocket`, hai phương thức có dạng khái niệm:

~~~java
<T> DatagramSocket setOption(SocketOption<T> name, T value) throws IOException;
<T> T getOption(SocketOption<T> name) throws IOException;
~~~

`setOption` trả về **chính `DatagramSocket`** để có thể chain lời gọi (khi cách cấu hình phù hợp). `getOption` trả giá trị có kiểu tương ứng với option, chẳng hạn `Integer` hoặc `Boolean`.

Trên `DatagramChannel`, `setOption` trả **chính channel**; `getOption` đến từ interface `NetworkChannel`. Ví dụ:

~~~java
try (DatagramChannel channel = DatagramChannel.open()) {
    channel.setOption(StandardSocketOptions.SO_BROADCAST, true);
    boolean enabled = channel.getOption(StandardSocketOptions.SO_BROADCAST);
}
~~~

Đây là đoạn minh họa cần import `java.nio.channels.DatagramChannel` và `java.net.StandardSocketOptions`.

### 4.1. Ngoại lệ cần phân biệt

| Tình huống | Loại lỗi thường được đặc tả |
| --- | --- |
| Option không được socket/channel hỗ trợ | `UnsupportedOperationException` |
| Giá trị option sai phạm vi hoặc không hợp lệ | `IllegalArgumentException` |
| `name == null` | `NullPointerException` đối với `DatagramSocket` |
| Socket đã đóng hoặc có lỗi I/O | `IOException` trên `DatagramSocket` |
| Channel đã đóng | `ClosedChannelException` (là một `IOException`) |
| Lỗi I/O khác trên channel | `IOException` |

Ví dụ xử lý rõ ràng:

~~~java
try {
    udp.setOption(StandardSocketOptions.SO_RCVBUF, 32 * 1024);
    int actual = udp.getOption(StandardSocketOptions.SO_RCVBUF);
    System.out.println("Receive buffer hiện tại = " + actual);
} catch (UnsupportedOperationException unsupported) {
    // Môi trường không hỗ trợ option này.
} catch (IllegalArgumentException badValue) {
    // Giá trị cấu hình không hợp lệ.
} catch (IOException ioError) {
    // Socket đóng hoặc hệ điều hành báo lỗi I/O.
}
~~~

Đây chỉ là **đoạn mã minh họa** trong phương thức có biến `udp` và các import tương ứng. Không âm thầm bỏ qua các lỗi không thể phục hồi trong production: ghi log/số liệu phù hợp và đưa ra quyết định fail/điều chỉnh cấu hình theo mức quan trọng của option.

### 4.2. “Được hỗ trợ” không đồng nghĩa “giá trị đặt được chính xác”

~~~java
udp.setOption(StandardSocketOptions.SO_RCVBUF, 64 * 1024);
int actual = udp.getOption(StandardSocketOptions.SO_RCVBUF);
~~~

**Không giả định `actual == 65536`.** Buffer là một gợi ý cho hệ điều hành; kernel có thể thay đổi, nhân đôi hoặc giới hạn kích thước. Lưu ý tương tự với `SO_SNDBUF`. Khi tối ưu UDP, cần đo throughput/drop/latency thực tế chứ không đánh giá dựa riêng vào con số `getOption`.

## 5. Những `StandardSocketOptions` thường liên quan UDP

| Option | Kiểu Java | Ý nghĩa khi dùng với UDP | Cảnh báo |
| --- | --- | --- | --- |
| `SO_RCVBUF` | `Integer` | Gợi ý độ lớn bộ đệm nhận ở tầng socket/OS | Có thể được hệ điều hành chỉnh lại; **không** phải dung lượng mảng `DatagramPacket` |
| `SO_SNDBUF` | `Integer` | Gợi ý độ lớn bộ đệm gửi ở tầng socket/OS | Giá trị thực và giới hạn datagram phụ thuộc nền tảng |
| `SO_REUSEADDR` | `Boolean` | Cho phép tái sử dụng local socket address trong những trường hợp OS hỗ trợ | Thiết lập **trước bind**; không bảo đảm cho phép hai socket nhận unicast cùng cổng |
| `SO_BROADCAST` | `Boolean` | Cho phép gửi IPv4 broadcast datagram | Có thể bị OS/quyền/mạng hạn chế; **không phải multicast** |
| `IP_TOS` | `Integer` | Cấu hình Type of Service/traffic class trong IP header | Không bảo đảm DSCP/QoS hay mức ưu tiên đường truyền |
| `SO_REUSEPORT` | `Boolean` | Dùng chung local port theo cơ chế platform cho phép | **Tùy hệ điều hành/JDK**, phải kiểm tra `supportedOptions()` |
| `IP_MULTICAST_IF` | `NetworkInterface` | Chọn interface gửi multicast | Chỉ cấu hình khi thực sự dùng multicast và interface hợp lệ |
| `IP_MULTICAST_TTL` | `Integer` | Đặt TTL/hop limit cho multicast (phạm vi 0–255) | Không điều khiển TTL của mọi loại datagram |
| `IP_MULTICAST_LOOP` | `Boolean` | Bật/tắt loopback của datagram multicast | Tác dụng tùy nền tảng, không thay cho `joinGroup` |

**Lưu ý phạm vi:** danh sách phía trên là các option có liên quan UDP theo đặc tả Java SE và một số lựa chọn phụ thuộc nền tảng. Một instance cụ thể có hỗ trợ hay không phải hỏi `supportedOptions()` của nó. Không phải mọi hệ thống hỗ trợ `SO_REUSEPORT` hoặc tác động như nhau.

### 5.1. Những option thuộc TCP, không dùng cho UDP

`StandardSocketOptions.TCP_NODELAY` là lựa chọn điều khiển Nagle của **TCP**; `SO_KEEPALIVE` và `SO_LINGER` thường liên quan các socket hướng kết nối/stream. Chúng không phải cách tối ưu một `DatagramSocket`.

~~~java
boolean tcpNoDelaySupported =
        udp.supportedOptions().contains(StandardSocketOptions.TCP_NODELAY);
// Với DatagramSocket UDP thông thường: false.
~~~

Với UDP thông thường, gọi `udp.getOption(StandardSocketOptions.TCP_NODELAY)` sẽ dẫn tới `UnsupportedOperationException`. Đừng bắt lỗi đó rồi coi Java không hỗ trợ tính năng TCP; vấn đề đơn giản là **đang dùng sai loại socket**.

### 5.2. `SO_TIMEOUT` không phải `StandardSocketOptions`

Đây là nhầm lẫn thường gặp:

~~~java
udp.setSoTimeout(2000);    // timeout cho blocking receive: 2000 ms
int ms = udp.getSoTimeout(); // 2000
~~~

`DatagramSocket.setSoTimeout/getSoTimeout` là các phương thức riêng của `DatagramSocket`; **không có** hằng `StandardSocketOptions.SO_TIMEOUT` để truyền cho `setOption`.

Nếu `receive(DatagramPacket)` không nhận được datagram trong thời gian cấu hình, nó có thể ném `SocketTimeoutException`. Timeout **không** tự gửi lại gói UDP, không xác nhận bên kia còn sống và không biến UDP thành giao thức đáng tin.

Với `DatagramChannel` ở chế độ non-blocking, xử lý đợi/timeout theo mô hình `Selector` hoặc logic ứng dụng tương ứng, không đơn giản thay bằng `getOption(SO_TIMEOUT)`.

## 6. Thời điểm đặt option: đặc biệt là `SO_REUSEADDR`

Một số option cần có hiệu lực **trước khi socket được bind**:

~~~java
DatagramSocket receiver = new DatagramSocket(null); // chưa bind
try (receiver) {
    receiver.setOption(StandardSocketOptions.SO_REUSEADDR, true);
    receiver.setOption(StandardSocketOptions.SO_RCVBUF, 32 * 1024);
    receiver.bind(new InetSocketAddress(9000));
}
~~~

Đây là **đoạn mã minh họa**; cổng 9000 có thể đã được ứng dụng khác sử dụng, nên trong bài thực hành chạy tự động ta sẽ dùng **cổng 0** để OS chọn cổng còn rảnh.

Tại sao không dùng `new DatagramSocket(9000)` rồi mới gọi `setOption(SO_REUSEADDR, true)`? Vì constructor với cổng sẽ **bind ngay**; đặc tả không bảo đảm thay đổi `SO_REUSEADDR` sau khi bind có tác dụng như bạn kỳ vọng. Tương tự, một số nền tảng hạn chế thay buffer sau bind.

### 6.1. `SO_REUSEADDR` không phải `SO_REUSEPORT`

- `SO_REUSEADDR` cho phép tái sử dụng địa chỉ trong một số trường hợp, đặc biệt quan trọng với multicast trên một số OS.
- `SO_REUSEPORT` có cơ chế liên quan **nhiều socket bind cùng port** với ngữ nghĩa OS-specific và có thể liên quan phân phối datagram.
- Ngay cả khi nhận `true` sau `setOption`, **không được suy luận các gói unicast sẽ được nhân bản cho mọi socket**. Cách kernel phân phối và xử lý phụ thuộc nền tảng.

Trước khi thiết kế multi-worker UDP dùng chung port, hãy kiểm tra `supportedOptions()` và thử nghiệm thực tế trên **cùng OS/container/JDK** dự kiến vận hành.

### 6.2. Multicast cần cấu hình thêm bên ngoài `setOption`

Để nhận multicast, ngoài `SO_REUSEADDR`/`IP_MULTICAST_IF` có thể cần chọn đúng interface, **tham gia group** và mở firewall. `DatagramSocket.joinGroup(...)` hoặc `DatagramChannel.join(...)` là API tham gia nhóm; chỉ bật `IP_MULTICAST_LOOP` không tự động cho phép nhận một nhóm multicast bất kỳ.

Với ứng dụng multicast phức tạp hoặc source-specific multicast, `DatagramChannel` cung cấp các API `MulticastChannel` phù hợp hơn. **Không thử gửi đến mạng multicast công cộng như một phần test cơ bản**; ví dụ trong mục 9 chỉ gửi giữa hai socket trên loopback.

## 7. `DatagramSocket` và `DatagramChannel` dùng cùng kiểu option, khác API vận hành

Cả hai đều có `setOption`, `getOption`, `supportedOptions` và đều làm việc với `SocketOption<T>`. Tuy nhiên không nên suy đoán rằng hai tập option luôn bằng nhau.

| Khía cạnh | `DatagramSocket` | `DatagramChannel` |
| --- | --- | --- |
| Gửi/nhận | `send(DatagramPacket)`, `receive(DatagramPacket)` | `send(ByteBuffer, SocketAddress)`, `receive(ByteBuffer)` |
| Option | Method trực tiếp trên `DatagramSocket` | Method của `NetworkChannel` / `DatagramChannel` |
| Binding | `bind(SocketAddress)` | `bind(SocketAddress)` |
| Timeout nhận | `setSoTimeout(int)` | `Selector`/logic I/O và timeout theo thiết kế NIO |
| NIO non-blocking | Không phải API channel chính | `configureBlocking(false)`, đăng ký `Selector` |
| Multicast | `joinGroup`/`leaveGroup` và multicast options | `MulticastChannel.join` và các API membership |
| Thu hồi tài nguyên | `try-with-resources`/`close` | `try-with-resources`/`close` |

### 7.1. Ví dụ cấu hình một `DatagramChannel`

~~~java
import java.net.StandardProtocolFamily;
import java.net.StandardSocketOptions;
import java.nio.channels.DatagramChannel;
import java.util.Set;
import java.net.SocketOption;

try (DatagramChannel channel = DatagramChannel.open(StandardProtocolFamily.INET)) {
    Set<SocketOption<?>> available = channel.supportedOptions();

    if (available.contains(StandardSocketOptions.SO_BROADCAST)) {
        channel.setOption(StandardSocketOptions.SO_BROADCAST, true);
        boolean enabled =
                channel.getOption(StandardSocketOptions.SO_BROADCAST);
    }

    if (available.contains(StandardSocketOptions.SO_RCVBUF)) {
        channel.setOption(StandardSocketOptions.SO_RCVBUF, 16 * 1024);
        int actual = channel.getOption(StandardSocketOptions.SO_RCVBUF);
    }
}
~~~

Đây là **đoạn mã minh họa**, cần đặt trong phương thức xử lý `IOException`. `StandardProtocolFamily.INET` chọn family IPv4 cho channel trong ví dụ; không có lý do dùng broadcast option nếu ứng dụng chỉ xử lý unicast loopback.

Nhiều option liên quan multicast cũng thường được `DatagramChannel` hỗ trợ, ví dụ `IP_MULTICAST_TTL` và `IP_MULTICAST_IF`. Nhưng các giá trị như `NetworkInterface` **không di động** giữa host; không hardcode tên card mạng `en0` hoặc `eth0` cho mọi nơi.

## 8. Thực hành an toàn: xử lý UDP và option ở lớp nào?

Với UDP server thực tế, có thể phân tách:

~~~text
Config (cổng, interface, buffer, reuse policy, timeout)
        │
        ▼
Khởi tạo DatagramSocket/DatagramChannel
        │
        ▼
Kiểm tra supportedOptions + setOption + getOption
        │
        ▼
Bind địa chỉ/cổng, khởi chạy vòng nhận
        │
        ▼
Nhận DatagramPacket/ByteBuffer, kiểm tra length/source
        │
        ▼
Decode/validate payload, xử lý nghiệp vụ
        │
        ▼
Gửi trả datagram nếu protocol yêu cầu
        │
        ▼
Close/metrics/log
~~~

**Nên làm trong production:**

1. Cấu hình option **một lần lúc khởi tạo** khi có thể, đặc biệt các option cần đặt trước bind.
2. Chỉ đòi hỏi các option thật sự cần thiết. Nếu option không hỗ trợ, chọn nhánh fallback đã được thiết kế hoặc fail-fast lúc khởi động.
3. Đọc lại `SO_RCVBUF`/`SO_SNDBUF`, tránh suy đoán giá trị thực bằng số yêu cầu.
4. Giữ `DatagramPacket.getLength()` và offset đúng khi giải mã payload; không coi toàn bộ byte array là message đã nhận.
5. Đặt ngưỡng kích thước datagram và buffer đủ lớn cho protocol. Buffer của kernel và `DatagramPacket` là hai cấp riêng; nhận vào mảng quá nhỏ có thể làm mất phần dữ liệu còn lại của datagram.
6. Quản lý thời hạn của request ở tầng ứng dụng. UDP vẫn có thể bị **mất gói, trùng gói, đảo thứ tự**; socket options không giải quyết tính tin cậy, retry, ACK hoặc chống replay.
7. Giới hạn nguồn tin cậy, tốc độ lưu lượng và tài nguyên xử lý để tránh UDP amplification/DoS, đặc biệt nếu server trả lời dữ liệu lớn cho địa chỉ nguồn có thể bị giả mạo.
8. Đóng socket/channel theo vòng đời. Không tiếp tục cấu hình/get option sau close chỉ vì `supportedOptions()` còn hoạt động.

**Đặt option không thay thế quan sát:** nếu gặp packet loss, phải kiểm tra lưu lượng, tốc độ xử lý, kernel receive-drop counters (nếu có), CPU, độ lớn datagram, giới hạn mạng và chính sách retry. Tăng buffer là một **công cụ** có giới hạn chứ không phải sửa được mọi nguyên nhân.

## 9. Chương trình Java 15+/17+ hoàn chỉnh, chạy offline bằng loopback

Chương trình sau minh họa trực tiếp cả **ba phương thức** trên `DatagramSocket`, thử option không phải UDP, kiểm tra `supportedOptions` sau close, cấu hình một `DatagramChannel` và thực hiện **một datagram UDP nội bộ** giữa hai socket cùng máy.

Để output ổn định, chương trình **không in** số cổng tự chọn hay giá trị buffer OS điều chỉnh; chỉ in các điều kiện boolean. Cài đặt trên JDK/OS khác có thể có tập option khác, nên `checks=true` là kết quả **kiểm chứng trên môi trường thử** chứ không phải lời hứa mọi hệ điều hành đều cho cùng output.

Lưu file **`DatagramOptionsDemo.java`** bằng encoding UTF-8:

~~~java
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.nio.channels.DatagramChannel;
import java.util.Set;

public class DatagramOptionsDemo {
    public static void main(String[] args) throws Exception {
        DatagramSocket receiver = new DatagramSocket(null);
        Set<SocketOption<?>> snapshot = receiver.supportedOptions();
        boolean supportsReceive = snapshot.contains(StandardSocketOptions.SO_RCVBUF);
        boolean supportsReuse = snapshot.contains(StandardSocketOptions.SO_REUSEADDR);
        boolean supportsTcp = snapshot.contains(StandardSocketOptions.TCP_NODELAY);
        boolean sameObject;
        boolean reuseOn;
        boolean bufferPositive;
        boolean bound;
        boolean udpRoundTrip;
        boolean tcpRejected = false;

        try (receiver; DatagramSocket sender = new DatagramSocket()) {
            System.out.println("supportsReceiveBuffer=" + supportsReceive);
            System.out.println("supportsReuseAddress=" + supportsReuse);
            System.out.println("supportsTcpNoDelay=" + supportsTcp);

            DatagramSocket returned = receiver.setOption(
                    StandardSocketOptions.SO_REUSEADDR, true);
            sameObject = returned == receiver;
            reuseOn = receiver.getOption(StandardSocketOptions.SO_REUSEADDR);
            System.out.println("setOptionReturnsSame=" + sameObject);
            System.out.println("reuseAddressEnabled=" + reuseOn);

            receiver.setOption(StandardSocketOptions.SO_RCVBUF, 16 * 1024);
            bufferPositive = receiver.getOption(StandardSocketOptions.SO_RCVBUF) > 0;
            System.out.println("actualReceiveBufferPositive=" + bufferPositive);

            receiver.bind(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0));
            receiver.setSoTimeout(2000);
            bound = receiver.getLocalPort() > 0;
            System.out.println("boundToEphemeralPort=" + bound);
            System.out.println("timeoutMillis=" + receiver.getSoTimeout());

            byte[] bytes = "Ping UDP 🌱".getBytes(StandardCharsets.UTF_8);
            DatagramPacket outgoing = new DatagramPacket(
                    bytes, bytes.length, receiver.getLocalSocketAddress());
            sender.send(outgoing);

            byte[] buffer = new byte[128];
            DatagramPacket incoming = new DatagramPacket(buffer, buffer.length);
            receiver.receive(incoming);
            String received = new String(incoming.getData(), incoming.getOffset(),
                    incoming.getLength(), StandardCharsets.UTF_8);
            udpRoundTrip = "Ping UDP 🌱".equals(received);
            System.out.println("udpRoundTrip=" + udpRoundTrip);

            try {
                receiver.getOption(StandardSocketOptions.TCP_NODELAY);
            } catch (UnsupportedOperationException expected) {
                tcpRejected = true;
            }
            System.out.println("tcpOptionRejected=" + tcpRejected);
        }

        boolean afterClose = receiver.supportedOptions().equals(snapshot);
        System.out.println("supportedAfterClose=" + afterClose);

        boolean channelSupportsReceive;
        boolean channelSupportsMulticastTtl;
        boolean channelBroadcastOn;
        boolean channelBufferPositive;
        try (DatagramChannel channel = DatagramChannel.open(StandardProtocolFamily.INET)) {
            Set<SocketOption<?>> channelOptions = channel.supportedOptions();
            channelSupportsReceive = channelOptions.contains(StandardSocketOptions.SO_RCVBUF);
            channelSupportsMulticastTtl =
                    channelOptions.contains(StandardSocketOptions.IP_MULTICAST_TTL);
            System.out.println("channelSupportsReceiveBuffer=" + channelSupportsReceive);
            System.out.println("channelSupportsMulticastTtl=" + channelSupportsMulticastTtl);

            channel.setOption(StandardSocketOptions.SO_BROADCAST, true);
            channelBroadcastOn = channel.getOption(StandardSocketOptions.SO_BROADCAST);
            System.out.println("channelBroadcastEnabled=" + channelBroadcastOn);

            channel.setOption(StandardSocketOptions.SO_RCVBUF, 16 * 1024);
            channelBufferPositive = channel.getOption(StandardSocketOptions.SO_RCVBUF) > 0;
            System.out.println("channelActualBufferPositive=" + channelBufferPositive);
        }

        System.out.println("checks=" + (
                supportsReceive && supportsReuse && !supportsTcp
                && sameObject && reuseOn && bufferPositive && bound && udpRoundTrip
                && tcpRejected && afterClose
                && channelSupportsReceive && channelSupportsMulticastTtl
                && channelBroadcastOn && channelBufferPositive));
    }
}
~~~

### 9.1. Biên dịch và chạy

~~~bash
javac --release 17 -encoding UTF-8 DatagramOptionsDemo.java
java DatagramOptionsDemo
~~~

Mã cũng biên dịch được ở ngữ nghĩa Java 15 bằng lệnh `javac --release 15 -encoding UTF-8 DatagramOptionsDemo.java`. Trong lần kiểm chứng, đã biên dịch với **`--release 15` và `--release 17`**, rồi chạy bằng **JDK 24**. Stdout chính xác:

~~~text
supportsReceiveBuffer=true
supportsReuseAddress=true
supportsTcpNoDelay=false
setOptionReturnsSame=true
reuseAddressEnabled=true
actualReceiveBufferPositive=true
boundToEphemeralPort=true
timeoutMillis=2000
udpRoundTrip=true
tcpOptionRejected=true
supportedAfterClose=true
channelSupportsReceiveBuffer=true
channelSupportsMulticastTtl=true
channelBroadcastEnabled=true
channelActualBufferPositive=true
checks=true
~~~

### 9.2. Giải thích các dòng quan trọng

- `supportsReceiveBuffer=true`, `supportsReuseAddress=true`: hai option UDP tiêu chuẩn có trong tập được môi trường thử hỗ trợ.
- `supportsTcpNoDelay=false`: option chỉ phù hợp TCP không thuộc tập option của UDP socket.
- `setOptionReturnsSame=true`: `DatagramSocket.setOption` trả chính socket đã cấu hình.
- `reuseAddressEnabled=true`: bật `SO_REUSEADDR` và đọc lại trước khi `bind`. **Điều này không chứng minh hai socket có thể chiếm chung cổng trên mọi OS.**
- `actualReceiveBufferPositive=true`: getter trả buffer dương; **chương trình không đòi nó bằng đúng 16 KiB** vì kernel có thể chọn giá trị khác.
- `boundToEphemeralPort=true`: bind cổng 0 thành cổng thật do hệ điều hành cấp phát; chương trình không cố định cổng nên tránh xung đột cổng khi học.
- `timeoutMillis=2000`: timeout được điều chỉnh bằng `setSoTimeout`, không qua `setOption`.
- `udpRoundTrip=true`: nhận chính chuỗi UTF-8 được gửi trên loopback. `DatagramPacket.getLength()` quyết định độ dài payload được giải mã.
- `tcpOptionRejected=true`: `getOption(TCP_NODELAY)` thất bại với `UnsupportedOperationException`, khác lỗi I/O hay giá trị sai.
- `supportedAfterClose=true`: sau khi đóng socket, vẫn có thể hỏi tập option đã hỗ trợ; **không** suy ra socket có thể tiếp tục gửi/nhận.
- `channelSupportsMulticastTtl=true`: channel của môi trường thử hỗ trợ một multicast option; chương trình **không** gửi/join multicast thực tế.
- `channelBroadcastEnabled=true`: channel cho phép bật `SO_BROADCAST`; đây không phải bằng chứng có packet broadcast đi qua firewall.
- `checks=true`: các kiểm tra cơ bản, UDP loopback và cấu hình channel đều đạt.

### 9.3. Đừng copy đúng output môi trường thử vào logic sản phẩm

Đầu ra `checks=true` ở đây là kết quả **một cấu hình JDK/OS**. Trên hệ thống chỉ hỗ trợ subset option, quyền broadcast bị hạn chế hoặc loopback bị cấu hình bất thường, có thể gặp kết quả khác hay exception. Ứng dụng sản xuất nên **có fallback/fail-fast rõ ràng**, không phụ thuộc cứng vào số lượng hoặc thứ tự các phần tử của `supportedOptions()`.

## 10. Một số mẫu ngắn thường dùng

### 10.1. Ưu tiên `SO_REUSEADDR` trước bind

~~~java
try (DatagramSocket udp = new DatagramSocket(null)) {
    if (udp.supportedOptions().contains(StandardSocketOptions.SO_REUSEADDR)) {
        udp.setOption(StandardSocketOptions.SO_REUSEADDR, true);
    }
    udp.bind(new InetSocketAddress(0));
    // Sử dụng udp...
}
~~~

Đây là đoạn minh họa trong một method xử lý `IOException`/`SocketException`. Với unicast client đơn giản, **không nhất thiết bật `SO_REUSEADDR`**; chỉ bật theo yêu cầu bind/multicast/thử nghiệm đã xác minh.

### 10.2. `SO_REUSEPORT` nếu thật sự được hỗ trợ

~~~java
try (DatagramSocket udp = new DatagramSocket(null)) {
    if (udp.supportedOptions().contains(StandardSocketOptions.SO_REUSEPORT)) {
        udp.setOption(StandardSocketOptions.SO_REUSEPORT, true);
    } else {
        // Chọn kiến trúc không cần SO_REUSEPORT.
    }
    udp.bind(new InetSocketAddress(0));
}
~~~

Chỉ bật trước `bind` là cần thiết khi app đang thiết kế cách phối hợp nhiều worker nhận cùng cổng. Trong code production, việc hỗ trợ option chưa đủ để quyết định phân phối gói: cần kiểm thử trên **OS và chế độ container cụ thể**.

### 10.3. Bật `SO_BROADCAST` để gửi IPv4 broadcast

~~~java
if (udp.supportedOptions().contains(StandardSocketOptions.SO_BROADCAST)) {
    udp.setOption(StandardSocketOptions.SO_BROADCAST, true);
}
~~~

Đoạn này **chỉ cấu hình quyền gửi broadcast**, không gửi datagram và không tìm subnet broadcast address. Đừng dùng broadcast để thay thế multicast hoặc cơ chế service discovery có xác thực; mạng có thể chặn broadcast.

### 10.4. Cấu hình multicast TTL

~~~java
if (channel.supportedOptions().contains(StandardSocketOptions.IP_MULTICAST_TTL)) {
    channel.setOption(StandardSocketOptions.IP_MULTICAST_TTL, 1);
    int ttl = channel.getOption(StandardSocketOptions.IP_MULTICAST_TTL);
}
~~~

Đây là đoạn minh họa trong method có biến `channel` là `DatagramChannel` đã tạo. TTL=1 là ví dụ thường dùng để giới hạn multicast trong mạng cục bộ; không bảo đảm mọi router/giao diện sẽ xử lý giống nhau và **không** tự động tham gia multicast group.

## 11. Checklist triển khai và xử lý lỗi

| Câu hỏi | Cách kiểm tra |
| --- | --- |
| API đang dùng là UDP hay TCP? | `DatagramSocket`/`DatagramChannel`; đừng gọi `TCP_NODELAY` cho UDP |
| Option có thật được hỗ trợ không? | `supportedOptions().contains(option)` |
| Giá trị đúng kiểu chưa? | `SocketOption<T>` và `StandardSocketOptions` |
| Giá trị có trong phạm vi hợp lệ? | Theo Javadoc/OS, bắt `IllegalArgumentException` |
| Option cần đặt trước bind không? | `SO_REUSEADDR`/`SO_REUSEPORT` và các buffer theo chính sách |
| `SO_RCVBUF` có đúng cỡ yêu cầu? | `getOption(SO_RCVBUF)`; chấp nhận kernel chỉnh size |
| Muốn timeout `receive`? | `DatagramSocket.setSoTimeout` thay vì `setOption` |
| Cần nhiều socket cùng port? | Phân biệt `SO_REUSEADDR`/`SO_REUSEPORT`, thử trên OS |
| Muốn multicast? | Chọn interface/TTL, join group và firewall tương ứng |
| Socket đã đóng? | `getOption/setOption` có thể lỗi I/O; `supportedOptions` vẫn trả set |
| Datagram quá lớn hoặc packet bị cắt? | Kiểm tra kích thước payload, `DatagramPacket`, OS buffer |
| UDP mất gói/đảo thứ tự? | Phải giải quyết tại protocol; option không bảo đảm delivery |
| Triển khai nhiều JDK/OS? | Test capability, thông số thực và hành vi trên từng môi trường |

### Bốn lỗi cần nhớ

1. **Coi `setOption` đã bảo đảm đúng giá trị:** dùng `getOption` để đọc lại, đặc biệt với buffer sizes.
2. **Lẫn option TCP và UDP:** `TCP_NODELAY`, `SO_KEEPALIVE` không phải công cụ xử lý vấn đề UDP.
3. **Bật `SO_REUSEADDR` sau khi bind:** chức năng đa socket có thể không có hiệu lực hoặc phụ thuộc OS. Tạo socket unbound khi cần cấu hình trước.
4. **Coi `supportedOptions` là đảm bảo tính năng vận hành:** set option có thể được chấp nhận nhưng OS/network vẫn có hạn chế; cần đo và xử lý tình huống không được hỗ trợ.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** `supportedOptions()` dùng để làm gì?  
**Đáp án:** lấy `Set<SocketOption<?>>` mà **instance socket/channel** hỗ trợ; không phải danh sách tất cả option của Java.

**Câu 2.** `setOption(SO_RCVBUF, 65536)` có nghĩa getter luôn trả 65536 không?  
**Đáp án:** **Không**. OS có thể điều chỉnh kích thước thực; đọc lại qua `getOption`.

**Câu 3.** Vì sao nên gọi `new DatagramSocket(null)` rồi đặt `SO_REUSEADDR`?  
**Đáp án:** socket chưa bind; đặt reuse trước khi bind phù hợp hợp đồng nền tảng.

**Câu 4.** `DatagramSocket.setOption(StandardSocketOptions.SO_TIMEOUT, 2000)` có đúng không?  
**Đáp án:** **Không**. Không có hằng `StandardSocketOptions.SO_TIMEOUT`; dùng `setSoTimeout(2000)`.

**Câu 5.** `getOption(StandardSocketOptions.TCP_NODELAY)` trên UDP sẽ thế nào?  
**Đáp án:** với `DatagramSocket` thông thường, option không hỗ trợ và có thể nhận `UnsupportedOperationException`.

**Câu 6.** Sau khi đóng socket, có được dùng `supportedOptions()` không?  
**Đáp án:** **Có**, theo Javadoc, nhưng điều đó không cho phép tiếp tục `send/receive/setOption/getOption` trên socket đóng.

**Câu 7.** `DatagramChannel` hỗ trợ option multicast có nghĩa tự nhận mọi gói multicast không?  
**Đáp án:** **Không**. Thông thường vẫn cần bind, chọn interface, tham gia group và cấu hình mạng.

## Tài liệu chuẩn còn áp dụng

- **Oracle Java SE 25 — `DatagramSocket`**, danh sách option, `setOption/getOption/supportedOptions` và ngoại lệ (Since 9): https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/DatagramSocket.html
- **Oracle Java SE 25 — `DatagramChannel`**, UDP socket options và cách sử dụng với NIO: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/DatagramChannel.html
- **Oracle Java SE 25 — `NetworkChannel`**, hợp đồng `setOption/getOption/supportedOptions`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/NetworkChannel.html
- **Oracle Java SE 25 — `StandardSocketOptions`**, kiểu và ý nghĩa các hằng UDP/TCP/multicast: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/StandardSocketOptions.html
- **Oracle Java SE 25 — `SocketOption<T>`**, `name()` và `type()`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/SocketOption.html
- **OpenJDK JEP 373 — Reimplement the Legacy DatagramSocket API**, thay đổi triển khai UDP của Java 15: https://openjdk.org/jeps/373