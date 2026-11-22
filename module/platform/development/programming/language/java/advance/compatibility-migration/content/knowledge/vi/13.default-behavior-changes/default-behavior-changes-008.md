# Thay đổi triển khai I/O, mạng và cách xử lý tình huống biên

Khi nâng cấp Java, mã nguồn vẫn có thể biên dịch, method signature vẫn giữ nguyên và các unit test chạy bình thường, nhưng ứng dụng lại gặp lỗi trong những tình huống ít xảy ra: socket đóng khi một thread đang đọc, DNS trả về địa chỉ khác thứ tự, UDP packet bị cắt, một lần `read()` không nhận đủ dữ liệu, HTTP client dùng lại kết nối đã hết hạn, hoặc file có ký tự tiếng Việt được đọc bằng charset khác trước. Những hiện tượng này dễ bị gán chung là “lỗi Java mới”, trong khi nguyên nhân có thể nằm ở JVM, thư viện mạng, hệ điều hành, cấu hình DNS/TLS, giao thức của ứng dụng hoặc giả định sai về API từ lâu.

Trong Java Advance Compatibility Migration, phần **hành vi mặc định** cần quan tâm không chỉ đến API bị xóa hay kiểu bytecode. Một số JDK thay đổi **implementation phía sau API công khai**, trong khi contract vẫn được giữ; một số release đổi **mặc định của môi trường** như charset; một số bổ sung cơ chế I/O mới mà ứng dụng chỉ sử dụng khi chủ động áp dụng. Các sai khác thường lộ ra ở tình huống biên: timeout, đóng tài nguyên đồng thời, gián đoạn thread, partial read/write, network failure, malformed input và race condition.

Bài học này giải thích những lớp thay đổi đó, cách phân biệt điều gì là hợp đồng Java API và điều gì chỉ là hành vi quan sát được của một implementation, cách xây dựng test tái hiện và quy trình xác minh khi di chuyển giữa các JDK.

## 1. Phân biệt contract API với implementation thực thi

### 1.1. Giữ nguyên public API không đồng nghĩa mọi chi tiết quan sát đều bất biến

Ví dụ, API quen thuộc:

```java
Socket socket = new Socket();
socket.connect(new InetSocketAddress("example.org", 443), 3_000);
socket.setSoTimeout(5_000);
InputStream input = socket.getInputStream();
```

Có thể tiếp tục tồn tại qua nhiều phiên bản JDK. Nhưng chi tiết nội bộ như cấu trúc native socket, synchronization, cách quản lý thread khi chờ I/O, thứ tự thông báo lỗi, cơ chế close hoặc khả năng hợp tác với virtual threads có thể được thay đổi.

Cần phân biệt:

- **Hợp đồng API:** điều được Javadoc/JLS/JVMS cam kết, ví dụ ý nghĩa của `read()`, timeout, close và exception.
- **Chi tiết implementation:** cách JDK dùng native library, selector, file descriptor, thread parking hay data structure.
- **Hành vi hệ điều hành:** TCP stack, giới hạn file descriptor, DNS resolver, buffer size, IPv4/IPv6 và error code.
- **Hành vi thư viện bên thứ ba:** HTTP client pool, JDBC driver, framework reactor, serializer hoặc observability agent.
- **Hợp đồng giao thức của ứng dụng:** cách đóng khung message, retry, idempotency, encoding và error handling.

Một hành vi từng xuất hiện trên JDK cũ nhưng không được API cam kết không nên được xem là yêu cầu tương thích mặc định. Nếu ứng dụng thực sự phụ thuộc vào hành vi đó, cần ghi nó thành assumption có test, rồi sửa code hoặc lập phương án thích nghi.

### 1.2. Phân loại thay đổi khi điều tra migration

| Loại thay đổi | Ví dụ | Cách kiểm chứng |
|---|---|---|
| Thay đổi internal implementation | Socket/DatagramSocket được viết lại | Test close, concurrent I/O, timeout và lỗi mạng |
| Thay đổi default | Default charset thành UTF-8 từ JDK 18 | Test đọc/ghi file và payload |
| API/cơ chế mới, không tự bật | Unix-domain socket channels, virtual threads | Chỉ test nhánh có sử dụng |
| Thay đổi dữ liệu nền tảng | Certificate store, timezone, Unicode | Kiểm tra theo vendor và JDK update |
| Thay đổi OS/container | DNS, IPv6, ulimit, network namespace | So sánh trong môi trường tương đương |
| Thay đổi dependency | HTTP client, TLS provider, framework, agent | Khóa và đối chiếu dependency graph |

Không quy mọi kết quả khác nhau cho JDK nếu môi trường test cũng đổi OS, base image, CA bundle, proxy hoặc phiên bản dependency.

## 2. Những mốc JDK liên quan trực tiếp

Các mốc sau giúp định vị phạm vi, không có nghĩa mọi ứng dụng đều bị tác động:

| Mốc | Thay đổi | Ý nghĩa khi migration |
|---|---|---|
| JDK 11 | `java.net.http.HttpClient` trở thành API chuẩn (JEP 321) | Có HTTP client mới để chủ động dùng; không tự thay thế mọi `HttpURLConnection` |
| JDK 13 | Reimplement Legacy Socket API (JEP 353) | Đổi implementation của `Socket` và `ServerSocket` bên dưới public API |
| JDK 15 | Reimplement Legacy DatagramSocket API (JEP 373) | Đổi implementation của `DatagramSocket` và `MulticastSocket` |
| JDK 16 | Unix-Domain Socket Channels (JEP 380) | Thêm khả năng sử dụng Unix-domain socket trong NIO channels trên hệ hỗ trợ |
| JDK 18 | UTF-8 by Default (JEP 400) | Các API dựa trên default charset có thể đọc/ghi khác trước |
| JDK 18 | Internet-Address Resolution SPI (JEP 418) | Thêm SPI để thay thế cách phân giải hostname; không có nghĩa DNS mặc định đổi với mọi app |
| JDK 21 | Virtual Threads (JEP 444) | Cho phép chủ động dùng thread nhẹ với blocking I/O; cần xem xét pinning và giới hạn tài nguyên |

Đặc biệt, nếu migration là **JDK 17 → 21**, phần viết lại Socket API và DatagramSocket API đã có trong JDK 17. Chúng vẫn đáng biết khi điều tra lỗi lịch sử hoặc khác biệt giữa môi trường build, nhưng không nên mô tả chúng như tính năng chỉ mới xuất hiện ở JDK 21. Ngược lại, JEP 400 từ JDK 18 là thay đổi mặc định nằm trên tuyến 17 → 21.

Những thay đổi về CA, thuật toán TLS bị vô hiệu hóa, dữ liệu timezone và các bản vá bảo mật còn phụ thuộc **JDK update cụ thể**. Vì vậy, khi thu thập bằng chứng cần ghi cả vendor và build number, không chỉ ghi “Java 17” hay “Java 21”.

## 3. Reimplementation của Socket API: JEP 353

### 3.1. “Legacy Socket API” chỉ điều gì?

Các lớp lâu đời của Java networking gồm `java.net.Socket`, `ServerSocket` và các stream đọc/ghi từ socket. JEP 353 cung cấp implementation mới cho các API socket cũ từ JDK 13, với mục tiêu bảo trì dễ hơn và hỗ trợ các hướng phát triển I/O của JDK.

Đây là thay đổi **bên dưới API công khai**, không phải yêu cầu viết lại mọi lời gọi `Socket` thành `SocketChannel`. Ứng dụng dùng `Socket`/`ServerSocket` thường không cần sửa code chỉ vì JEP 353; nhưng các trường hợp race, đóng socket và tương tác với native/JVM nội bộ cần regression test.

### 3.2. Những tình huống có thể làm lộ phụ thuộc implementation

Một ứng dụng có thể vô tình phụ thuộc:

- Thứ tự thread đang `read()` hoặc `accept()` được đánh thức khi thread khác gọi `close()`.
- Loại exception và message cụ thể khi đóng kết nối đồng thời với I/O.
- Timing của `connect()`/`accept()`/`read()` tại ranh giới timeout.
- Cách giải phóng file descriptor hoặc xử lý một thao tác block kéo dài.
- Đồng bộ trên đối tượng socket hoặc giả định nhiều thread gọi cùng method luôn được tuần tự hóa theo một thứ tự cố định.
- Hành vi không được Javadoc cam kết của một socket implementation tùy chỉnh.

Không nên khẳng định mọi trường hợp trên **chắc chắn đã đổi** trong một JDK cụ thể. Đó là các điểm cần test vì chúng thường phụ thuộc timing và implementation. Nếu có regression, xác định JDK/build, OS, stack trace và đường gọi chính xác trước khi kết luận nguyên nhân.

### 3.3. Ví dụ timeout rõ ràng

```java
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.Socket;

public final class SimpleTcpClient {
    public static void main(String[] args) throws IOException {
        try (Socket socket = new Socket()) {
            socket.connect(
                new InetSocketAddress("example.org", 443),
                3_000
            );

            socket.setSoTimeout(5_000);

            // Đọc/ghi theo giao thức đã định nghĩa.
            // Không giả định một lần read() trả đủ message.
        }
    }
}
```

Có **ít nhất hai thời gian chờ khác nhau**:

- Timeout truyền vào `Socket.connect(endpoint, timeout)` giới hạn giai đoạn thiết lập kết nối theo contract của API.
- `setSoTimeout(...)` giới hạn thời gian chờ của một thao tác `read()` blocking trên socket input stream; nó không phải thời hạn tổng cho toàn bộ request/response.

Một ứng dụng còn có thể cần **deadline nghiệp vụ** bao phủ DNS, connect, ghi request, đọc response và retry. Không thể thay deadline tổng bằng việc đặt read timeout.

### 3.4. Đóng socket và thread đang block

Một thread có thể block trong `read()`; thread khác yêu cầu dừng và đóng socket. Khi đó thao tác đọc sẽ phải thoát theo cơ chế và exception phù hợp. Nhưng code không nên phụ thuộc vào **chuỗi exception message** hoặc thứ tự chính xác giữa close và dữ liệu đến sát thời điểm close.

Một mô hình quản lý vòng đời tốt:

1. Có owner rõ ràng chịu trách nhiệm đóng socket.
2. Shutdown đánh dấu trạng thái dừng và đóng tài nguyên.
3. Worker I/O ghi nhận exception khi shutdown như một trường hợp riêng, không luôn là lỗi production.
4. Không đóng/đọc cùng socket từ nhiều nơi mà không có contract concurrency.
5. Test cleanup trong cả close bình thường, remote reset, timeout, cancellation và process shutdown.

Trạng thái `socket.isConnected()` mô tả lịch sử kết nối thành công; nó không phải phép “ping” chứng minh peer hiện còn sống. Ngay cả khi socket đã đóng, `isConnected()` có thể vẫn là `true`. Cần dựa vào hợp đồng I/O, `isClosed()` và xử lý lỗi thực tế.

## 4. DatagramSocket và MulticastSocket: JEP 373

### 4.1. Thay đổi implementation, không đổi bản chất UDP

JEP 373 từ JDK 15 viết lại implementation các API datagram truyền thống gồm `DatagramSocket`/`MulticastSocket`. Dù implementation mới, giao thức UDP vẫn giữ bản chất:

- Datagram có ranh giới message, khác TCP byte stream.
- Không bảo đảm giao hàng, thứ tự hoặc chỉ có một bản.
- Packet có thể bị mất, trùng, đến muộn hoặc bị cắt tại buffer nhận.
- Kích thước datagram và fragmentation chịu giới hạn từ network stack.
- Multicast phụ thuộc interface, routing, switch/network policy và OS.

Do đó, việc một ứng dụng lâu nay “chưa mất UDP packet” không có nghĩa UDP có reliability. Khi migration, cần kiểm tra cơ chế retry, sequence number hoặc acknowledgment ở tầng ứng dụng nếu nghiệp vụ yêu cầu.

### 4.2. Buffer nhận ngắn có thể làm mất phần đuôi datagram

```java
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;

public final class UdpReceiver {
    public static void main(String[] args) throws Exception {
        byte[] buffer = new byte[2048];

        try (DatagramSocket socket = new DatagramSocket(9999)) {
            socket.setSoTimeout(2_000);

            DatagramPacket packet =
                new DatagramPacket(buffer, buffer.length);

            try {
                socket.receive(packet);

                String message = new String(
                    packet.getData(),
                    packet.getOffset(),
                    packet.getLength(),
                    StandardCharsets.UTF_8
                );

                System.out.println(message);
            } catch (SocketTimeoutException timeout) {
                System.out.println("No datagram in time window");
            }
        }
    }
}
```

Đừng dùng `buffer.length` làm số byte đã nhận; dùng `packet.getLength()`. Nếu datagram lớn hơn khả năng chứa của packet/buffer, phần dữ liệu vượt quá có thể bị bỏ. Ứng dụng không thể phục hồi phần đó bằng một lần `receive()` tiếp theo như với TCP.

Khi tái sử dụng `DatagramPacket`, cần chú ý độ dài packet do thao tác nhận trước để lại; đặt lại chiều dài tối đa phù hợp trước lần nhận mới nếu muốn dùng lại đầy đủ buffer:

```java
packet.setLength(buffer.length);
socket.receive(packet);
```

Đây là một tình huống biên thực tế: packet đầu ngắn, packet thứ hai dài hơn, nhưng chương trình không reset packet length và vô tình nhận thiếu dữ liệu.

### 4.3. Multicast phụ thuộc môi trường

Với `MulticastSocket`, kiểm tra network interface được chọn, địa chỉ multicast, TTL/hop limit, firewall, container network mode, IPv4/IPv6 support và việc join/leave group. Không giả định localhost sẽ mô phỏng đầy đủ multicast trên production.

Khi JDK đổi implementation, các giả định không công bố về thời điểm join/leave, socket options và multicast interface có thể bị lộ. Test phải dùng môi trường gần với network topology thật.

## 5. TCP là luồng byte: partial read/write không phải regression

Một trong những lỗi mạng bị nhầm là “thay đổi hành vi Java” phổ biến nhất là giả định TCP giữ ranh giới message.

### 5.1. Một `write()` không tương ứng một `read()`

Giả sử phía gửi thực hiện:

```java
output.write(firstMessage);
output.write(secondMessage);
```

Phía nhận có thể đọc:

- Một phần `firstMessage`.
- Nhiều phần liên tiếp của cùng message.
- Toàn bộ hai message trong một lần đọc.
- Số byte phụ thuộc buffer, scheduling và network.

TCP cung cấp dòng byte có thứ tự, không phải message framing. Một lần `InputStream.read(buffer)` có thể trả ít hơn số byte mà ứng dụng mong đợi dù peer chưa đóng kết nối.

### 5.2. Dùng framing rõ ràng

Một cách phổ biến là **length-prefix framing**: gửi độ dài rồi gửi đúng số byte.

```java
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.nio.charset.StandardCharsets;

public final class MessageFrame {
    private static final int MAX_BYTES = 1024 * 1024;

    public static void writeMessage(
            DataOutputStream out,
            String value) throws IOException {
        byte[] payload = value.getBytes(StandardCharsets.UTF_8);

        if (payload.length > MAX_BYTES) {
            throw new IOException("Message too large");
        }

        out.writeInt(payload.length);
        out.write(payload);
        out.flush();
    }

    public static String readMessage(
            DataInputStream in) throws IOException {
        int length = in.readInt();

        if (length < 0 || length > MAX_BYTES) {
            throw new IOException("Invalid frame length: " + length);
        }

        byte[] payload = new byte[length];
        in.readFully(payload);

        return new String(payload, StandardCharsets.UTF_8);
    }
}
```

`DataInputStream.readFully(...)` đọc đủ số byte yêu cầu hoặc ném `EOFException` nếu stream kết thúc sớm. Đừng bỏ giới hạn `MAX_BYTES`: một peer lỗi hoặc không tin cậy có thể khai báo độ dài rất lớn và gây sử dụng bộ nhớ quá mức.

Ví dụ tập trung vào framing; trong hệ thống thực tế cần thêm authentication, checksum/integrity nếu giao thức yêu cầu, deadline, retry/idempotency và bảo vệ tài nguyên.

### 5.3. EOF, timeout và lỗi I/O là ba trạng thái khác nhau

Với stream:

- `read() == -1` thường biểu thị EOF: peer đã kết thúc luồng đọc theo ngữ nghĩa stream.
- `SocketTimeoutException` cho biết thao tác đọc vượt thời gian chờ được cấu hình.
- Các `IOException` khác có thể biểu thị connection reset, socket closed hoặc lỗi OS.

Không nên coi timeout là EOF, hoặc coi EOF là bằng chứng rằng response hợp lệ. Nếu giao thức yêu cầu 100 byte mà nhận 40 byte rồi EOF, đây là message bị cắt cần xử lý theo protocol contract.

Nếu thiết kế ứng dụng đọc đến EOF để xác định kết thúc response, kết nối sẽ khó tái sử dụng vì EOF thường đồng nghĩa kết thúc một chiều stream. Với persistent connection, cần framing theo độ dài, delimiter đã escape hoặc giao thức hỗ trợ rõ ràng.

### 5.4. `available()` không phải số byte của toàn bộ message

`InputStream.available()` là ước lượng số byte có thể đọc ngay mà không block theo hợp đồng API của implementation; nó không phải tổng số byte còn lại trong message hay trong network.

Code như sau không đáng tin cậy:

```java
if (input.available() == 0) {
    // Sai nếu kết luận remote đã gửi xong.
}
```

Có thể chưa có byte trong buffer hiện tại nhưng remote vẫn đang gửi. Hãy đọc theo framing và deadline, không dựa vào `available()` để đo độ dài message.

## 6. NIO channels: zero-byte read và trạng thái buffer

NIO cung cấp `SocketChannel`, `ServerSocketChannel`, `Selector` và `ByteBuffer`. Ở chế độ non-blocking, thao tác đọc có thể trả **0** nếu hiện chưa có dữ liệu dù kết nối vẫn mở. Đây là hành vi hợp đồng, không phải EOF.

```java
int n = channel.read(buffer);

if (n == -1) {
    // Peer đã kết thúc stream: xử lý EOF.
} else if (n == 0) {
    // Chưa có byte; với non-blocking channel phải đợi readiness.
} else {
    // Có n byte mới được đưa vào buffer.
}
```

Ở chế độ non-blocking, code không nên lặp bận `while (read(...) == 0)` liên tục, vì có thể đốt CPU. Sử dụng `Selector`, cơ chế readiness hoặc abstraction thích hợp.

### 6.1. `ByteBuffer` có vị trí và giới hạn

Quy trình đọc/giải mã thường là:

```java
ByteBuffer buffer = ByteBuffer.allocate(4096);

int count = channel.read(buffer);

if (count > 0) {
    buffer.flip();

    while (buffer.hasRemaining()) {
        byte b = buffer.get();
        // Chuyển byte vào bộ giải mã/frame parser.
    }

    buffer.compact();
}
```

Trong ví dụ đơn giản, parser tiêu thụ toàn bộ byte. Với protocol frame có thể chưa nhận đủ, cần giữ byte chưa tiêu thụ bằng `compact()` và tiếp tục đọc ở lần sau.

Các lỗi migration thường xuất hiện khi thay thư viện NIO hoặc event loop nhưng parser ngầm giả định một lần đọc luôn cho đủ header. Cần test với frame bị chia tại mọi vị trí, đặc biệt ở giữa header, UTF-8 multibyte sequence và payload.

### 6.2. Partial write cũng cần xử lý

Với channel:

```java
while (buffer.hasRemaining()) {
    int written = channel.write(buffer);

    if (written == 0) {
        // Với non-blocking mode: đợi sự kiện writable thay vì busy-spin.
        break;
    }
}
```

Đây chỉ là phần minh họa: nếu ngừng tại `written == 0`, ứng dụng phải lưu lại `buffer` chưa gửi hết và đăng ký readiness để ghi tiếp. Không được bỏ byte còn lại.

Với blocking channel, có thể tiếp tục ghi đến khi `buffer.hasRemaining()` trở thành false, nhưng vẫn phải xử lý lỗi close, timeout cấp ứng dụng và remote disconnect. Không giả định “một lần write là đã gửi hết mọi thứ tới peer và peer đã xử lý thành công”.

## 7. DNS, địa chỉ IP và việc chọn endpoint

### 7.1. DNS không phải một hằng số

Khi ứng dụng gọi:

```java
InetAddress[] addresses =
    InetAddress.getAllByName("service.example.org");
```

kết quả có thể phụ thuộc DNS server, search domain, network namespace, TTL/cache, IPv4/IPv6, VPN, DNS split-horizon, container resolver và chính sách của OS/JDK. Kết quả có thể trả nhiều địa chỉ hoặc thứ tự khác nhau.

Đừng giả định:

- Hostname luôn phân giải thành đúng một IP.
- Địa chỉ đầu tiên luôn là IPv4.
- IP không thay đổi trong suốt vòng đời ứng dụng.
- Cùng hostname ở laptop, CI, container và production trả cùng IP.
- TTL của DNS record sẽ tự động được mọi lớp cache tôn trọng theo cùng quy tắc.

### 7.2. Caching và negative caching

Java có cơ chế cache kết quả phân giải địa chỉ. Các security properties như:

```properties
networkaddress.cache.ttl=30
networkaddress.cache.negative.ttl=5
```

điều khiển chính sách cache trong phạm vi hỗ trợ của implementation. Đây là **security properties**, không nên mặc định chúng hoạt động như mọi `-D` system property. Cần cấu hình theo cơ chế được JDK/vendor hỗ trợ và xác minh trong runtime thực tế.

Tránh chọn một TTL tùy ý chỉ để sửa lỗi tạm. TTL ngắn có thể tăng số lần DNS lookup; TTL dài có thể giữ IP đã thay đổi trong quá trình failover. Xác định yêu cầu discovery và failure recovery của hệ thống.

### 7.3. IPv4/IPv6 và localhost

Một service bind vào `127.0.0.1` không đồng nghĩa nó lắng nghe `::1`. Nếu hostname `localhost` phân giải ra IPv6 trước, client có thể cố kết nối vào endpoint khác với điều developer mong đợi.

Khi test, nên chỉ rõ địa chỉ hoặc bind phù hợp:

```java
InetSocketAddress endpointV4 =
    new InetSocketAddress("127.0.0.1", 8080);

// Nếu môi trường hỗ trợ IPv6:
InetSocketAddress endpointV6 =
    new InetSocketAddress("::1", 8080);
```

Việc bind vào wildcard address, chọn interface mặc định và dual-stack behavior còn phụ thuộc OS/JDK. Nếu ứng dụng cần hỗ trợ cả hai, test trên cả IPv4-only, IPv6-only hoặc dual-stack theo phạm vi sản phẩm.

JDK có các thuộc tính cấu hình liên quan lựa chọn địa chỉ như `java.net.preferIPv4Stack` và `java.net.preferIPv6Addresses`. Không nên dùng chúng như workaround toàn cục khi chưa xác định endpoint, DNS và ràng buộc môi trường.

### 7.4. JEP 418 không có nghĩa DNS mặc định chắc chắn đổi

JEP 418 (JDK 18) thêm **Internet-Address Resolution SPI**, cho phép các implementation tùy chỉnh cung cấp dịch vụ phân giải hostname. Đây là extension point; việc JDK cung cấp SPI không tự chứng minh rằng mọi ứng dụng từ JDK 17 lên 21 nhận kết quả DNS khác.

Nếu ứng dụng hoặc agent sử dụng resolver tùy chỉnh, cần kiểm tra provider được chọn, fallback, lỗi lookup, cache và tương tác với HTTP/database client. Nếu không có resolver tùy chỉnh, điều tra DNS theo dữ liệu và cấu hình thực tế thay vì quy kết trực tiếp cho JEP 418.

## 8. HTTP client: redirect, timeout, pool và protocol

### 8.1. Không nên đồng nhất mọi HTTP client trong Java

Các cơ chế HTTP phổ biến gồm:

- `HttpURLConnection` từ các API lâu đời.
- `java.net.http.HttpClient` là API chuẩn từ JDK 11.
- Apache HttpClient, OkHttp, Netty và client trong framework.
- SDK riêng của cloud/database/service provider.

Chúng có thể khác nhau về redirect, connection pooling, HTTP/2, proxy, DNS, TLS, timeout, retry và xử lý streaming. Nâng JDK không tự thay thế một client bên thứ ba bằng `java.net.http.HttpClient`.

Nếu migration đồng thời thay HTTP library, hãy ghi đó là thay đổi độc lập để xác định regression chính xác.

### 8.2. Ví dụ Java HttpClient với timeout rõ ràng

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public final class HttpExample {
    public static void main(String[] args) throws Exception {
        HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(3))
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();

        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create("https://example.org/api/status"))
            .timeout(Duration.ofSeconds(8))
            .GET()
            .build();

        HttpResponse<byte[]> response =
            client.send(request, HttpResponse.BodyHandlers.ofByteArray());

        int status = response.statusCode();

        if (status < 200 || status >= 300) {
            throw new IllegalStateException(
                "Unexpected HTTP status: " + status
            );
        }

        // Diễn giải bytes theo Content-Type và hợp đồng API.
        System.out.println("bytes=" + response.body().length);
    }
}
```

Đây là ví dụ minh họa. `connectTimeout` và request timeout có phạm vi khác nhau; deadline nghiệp vụ có thể còn bao gồm nhiều request, retry hoặc bước xử lý ngoài HTTP client.

HTTP status 4xx/5xx thường là HTTP response hợp lệ ở tầng transport, không tự biến thành Java exception cho mọi client. Cần phân loại transport exception, timeout và application error từ status/body.

### 8.3. Redirect có thể thay đổi semantics bảo mật

Khi cho phép redirect, phải xác định:

- Redirect sang host khác có được phép không.
- Credential, cookie hoặc authorization header có được gửi lại hay bị loại bỏ theo client policy.
- Redirect từ HTTPS sang HTTP có bị ngăn không.
- Redirect giữa POST/GET hoặc method/body semantics ra sao.
- Có giới hạn số lần redirect để tránh loop không.

Không bật redirect tự động chỉ để che endpoint configuration sai hoặc SSL error. Hành vi redirect cụ thể phải dựa vào client version và test với server mô phỏng.

### 8.4. Connection reuse và stale connection

HTTP keep-alive/pooling giảm chi phí bắt tay TCP/TLS, nhưng server hoặc proxy có thể đóng kết nối nhàn rỗi. Một lần gửi sau đó có thể gặp lỗi do client cố dùng connection đã bị đóng.

Thay vì kết luận runtime mới “không ổn định”, kiểm tra:

- Pool idle timeout và max lifetime.
- Proxy/load balancer idle timeout.
- Keep-alive và server close behavior.
- Retry policy cho request idempotent.
- HTTP/1.1 vs HTTP/2 được thương lượng thật sự.
- Streaming response body có được consume/close đúng không.

Có thể có thay đổi hiệu năng khi cập nhật JDK, nhưng không nên dùng một kết quả throughput duy nhất để suy ra protocol contract thay đổi.

## 9. TLS, certificate và chính sách bảo mật

### 9.1. SSL handshake là một bước tích hợp độc lập

Một chương trình kết nối được TCP không có nghĩa TLS handshake thành công. TLS còn cần protocol/cipher phù hợp, certificate chain, truststore, hostname verification, SNI và đôi khi client certificate.

Khi nâng JDK, các security defaults có thể thay đổi qua bản update: thuật toán yếu bị vô hiệu hóa, truststore thay đổi, provider được cập nhật hoặc cách thương lượng TLS khác. Những thay đổi này có thể làm lộ server cũ chỉ hỗ trợ cipher/protocol không còn được chấp nhận.

Các lỗi điển hình:

- `SSLHandshakeException` khi handshake thất bại.
- `PKIX path building failed` khi không xác minh được trust chain.
- Hostname mismatch khi chứng thư không khớp endpoint.
- `protocol_version` hoặc `handshake_failure` từ server/proxy.

### 9.2. Không sửa bằng cách vô hiệu hóa kiểm tra bảo mật

Không nên:

- Tắt certificate validation.
- Dùng trust-all TrustManager.
- Bỏ hostname verification.
- Hạ TLS protocol hoặc bật thuật toán yếu trên toàn JVM chỉ để kết nối được.

Giải pháp đúng là kiểm tra chain, tên miền, server TLS policy, proxy, truststore và policy của JDK, rồi cập nhật server/chứng thư/config theo yêu cầu bảo mật.

Để điều tra trên môi trường được phép, JVM có tùy chọn debug TLS như:

```bash
java -Djavax.net.debug=ssl,handshake -jar application.jar
```

Log có thể chứa certificate, host và metadata mạng nội bộ. Chỉ thu thập log trong phạm vi cần thiết và lọc dữ liệu nhạy cảm trước khi chia sẻ.

### 9.3. Phân biệt JDK major với JDK update

Khi so sánh JDK 17 và 21, hãy ghi vendor, patch level, base image, truststore và TLS provider. Một vấn đề có thể do cập nhật CA hoặc policy trong JDK update cùng dòng, không nhất thiết do chuyển major version.

## 10. I/O với file và encoding: JEP 400

### 10.1. UTF-8 trở thành default charset từ JDK 18

Trước JDK 18, nhiều API Java dùng default charset phụ thuộc OS/locale. Từ JDK 18, JEP 400 chuẩn hóa UTF-8 làm default charset cho các API dựa vào mặc định này, trừ các cơ chế tương thích hoặc ngoại lệ theo tài liệu API.

Do đó, khi nâng **JDK 17 → 21**, đoạn code:

```java
String text = new String(bytes);
byte[] output = text.getBytes();
```

có thể đọc/ghi khác trước nếu runtime cũ dùng encoding không phải UTF-8. Tương tự với các overload không chỉ định charset của `FileReader`, `FileWriter`, `InputStreamReader`, `OutputStreamWriter` và một số thư viện I/O.

### 10.2. Chỉ định encoding ở biên dữ liệu

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("data", "customers.csv");

String content =
    Files.readString(path, StandardCharsets.UTF_8);

Files.writeString(path, content, StandardCharsets.UTF_8);
```

Các API như `Files.readString(Path)` vốn được định nghĩa dùng UTF-8 trong Java 11 trở đi; không phải mọi API đều dựa vào default charset. `Properties.load(InputStream)` có hợp đồng encoding riêng (ISO-8859-1 trong định dạng properties cổ điển). Vì vậy phải xem Javadoc của chính overload, không sửa bằng suy đoán.

Nếu file legacy thật sự ở encoding khác, cần chỉ định đúng charset tại chỗ đọc:

```java
Charset legacyCharset = Charset.forName("windows-1258");

try (BufferedReader reader =
         Files.newBufferedReader(path, legacyCharset)) {
    // Đọc dữ liệu legacy theo hợp đồng đã được xác minh.
}
```

Tên charset là ví dụ, phải xác minh encoding của file thực tế. Không chuyển mặc định cả JVM chỉ để phục vụ một file cũ.

### 10.3. Encoding của network payload là hợp đồng giao thức

TCP/UDP truyền bytes, không truyền sẵn “Java String”. Mỗi protocol phải xác định cách encode/decode. Với HTTP, kiểm tra `Content-Type` và đặc tả payload; với JSON, tuân thủ quy tắc encoding của chuẩn và API giao tiếp.

Nếu code dùng `new String(bytes)` trên dữ liệu từ socket, việc đổi default charset có thể làm payload sai dù TCP hoàn toàn ổn định. Đây là ví dụ điển hình của lỗi “mạng” mà nguyên nhân thật sự nằm ở encoding.

### 10.4. Unicode có thể bị cắt giữa hai lần read

Với UTF-8, một ký tự có thể chiếm nhiều byte. Nếu parser giải mã mỗi chunk độc lập, việc chia buffer giữa các byte trong cùng ký tự có thể gây ký tự thay thế hoặc lỗi decoding.

Khi nhận stream, nên dùng `InputStreamReader` hoặc một `CharsetDecoder` duy trì trạng thái qua nhiều chunk, không gọi `new String(chunk, UTF_8)` tùy tiện cho từng phần khi chưa biết ranh giới ký tự.

## 11. File system behavior và tình huống biên

### 11.1. Tính tương thích không chỉ phụ thuộc JDK

File path, permission, symlink, case sensitivity, atomic rename và file locking còn phụ thuộc file system/OS. Nếu migration đồng thời chuyển từ Windows sang Linux hoặc từ máy ảo sang container, có thể xuất hiện lỗi dù JDK API không đổi.

Ví dụ:

- `report.csv` và `Report.csv` có thể là hai file khác nhau trên một file system, nhưng không trên file system khác.
- Path separator là `\` hay `/` tùy nền tảng; tránh nối chuỗi thủ công.
- File permission và owner/group khác nhau giữa container và host.
- Symlink có thể khiến thao tác đọc/ghi trỏ sang tài nguyên ngoài dự kiến.
- File lock semantics khác nhau theo file system, OS và process.
- Atomic move không được hỗ trợ trên mọi provider hoặc giữa hai file stores.

### 11.2. Sử dụng Path và Files theo contract

```java
Path base = Path.of("data", "export");
Path file = base.resolve("report.csv");

Files.createDirectories(base);
Files.writeString(file, "id,name\n1,An\n", StandardCharsets.UTF_8);
```

`Path.resolve` giảm lỗi ghép separator. Tuy nhiên, nó không tự bảo vệ trước path traversal nếu một thành phần của path đến từ input không tin cậy. Cần normalize/validate và kiểm tra containment theo chính sách bảo mật, đồng thời xem xét symlink/race.

### 11.3. Atomic move có thể không khả dụng

Khi muốn ghi file theo kiểu publish-as-one-step, có thể tạo file tạm rồi chuyển sang đích:

```java
Path temp = Files.createTempFile(target.getParent(), ".new-", ".tmp");

try {
    Files.writeString(temp, output, StandardCharsets.UTF_8);
    Files.move(temp, target, StandardCopyOption.ATOMIC_MOVE);
} catch (AtomicMoveNotSupportedException ex) {
    // Quyết định có chấp nhận fallback không theo yêu cầu nhất quán.
    throw ex;
} finally {
    Files.deleteIfExists(temp);
}
```

Đoạn code là mẫu minh họa; phải có `target`, `output` và các import tương ứng trong ngữ cảnh thực tế. Nếu đích đã tồn tại, semantics thay thế khi atomic move có thể phụ thuộc provider. Không nên tự động fallback sang non-atomic move nếu hệ thống yêu cầu đảm bảo không bao giờ nhìn thấy file chưa hoàn chỉnh.

Trong production, còn cần đánh giá fsync/durability, permission, ownership và crash consistency. Atomic rename không đồng nghĩa dữ liệu đã được lưu bền vững lên thiết bị trong mọi trường hợp.

### 11.4. TOCTOU: kiểm tra rồi dùng có thể bị race

Code:

```java
if (Files.exists(path)) {
    byte[] bytes = Files.readAllBytes(path);
}
```

không bảo đảm file vẫn tồn tại khi thực hiện `readAllBytes`. Giữa check và use, process khác có thể xóa, thay thế hoặc đổi quyền file.

Hãy xử lý exception ở chính thao tác, dùng API atomic khi có và tránh biến một lần `exists()` thành cam kết về trạng thái tương lai.

## 12. Đóng, hủy và ngắt các thao tác I/O

### 12.1. Blocking I/O có vòng đời riêng

Một thread gọi `read()` có thể đang chờ dữ liệu. Ứng dụng muốn shutdown cần cơ chế ngắt chờ hoặc đóng tài nguyên có chủ đích. Ý nghĩa của `Thread.interrupt()` phụ thuộc loại channel/stream, cách I/O được triển khai và thread đang sử dụng; không nên giả định interrupt luôn tương đương `Socket.close()`.

Các lỗi/thông báo có thể gặp gồm:

- `SocketTimeoutException`.
- `SocketException` do kết nối bị đóng/reset.
- `ClosedChannelException`.
- `ClosedByInterruptException`.
- `AsynchronousCloseException`.
- `EOFException` hoặc `read() == -1` khi thiếu dữ liệu/kết thúc luồng.

Không xử lý mọi exception bằng một catch rộng rồi retry vô hạn. Phân loại shutdown có chủ đích, timeout, lỗi protocol và lỗi mạng để quyết định chính sách tiếp theo.

### 12.2. Try-with-resources là ranh giới ownership

```java
try (Socket socket = new Socket()) {
    socket.connect(endpoint, 3_000);
    socket.setSoTimeout(5_000);
    // Giao tiếp I/O.
}
```

Try-with-resources giúp đóng socket khi ra khỏi scope, kể cả khi exception xuất hiện. Nhưng nếu một socket đang được chia sẻ giữa nhiều task, scope phải phản ánh đúng ownership; đóng quá sớm có thể làm task khác thất bại.

### 12.3. Không retry mọi I/O failure như nhau

Giả sử client gửi request chuyển tiền, sau đó mất kết nối trước khi nhận response. Client không biết chắc server đã xử lý hay chưa. Retry không kiểm soát có thể gây xử lý trùng.

Với request có side effect, cần idempotency key, transaction status lookup hoặc protocol acknowledgment đáng tin cậy. Đây là khác biệt quan trọng giữa:

- **Transport failure:** không nhận được kết quả.
- **Business failure:** server trả lỗi nghiệp vụ.
- **Unknown outcome:** có thể server đã xử lý nhưng response bị mất.

Một thay đổi timing khi nâng JDK có thể làm lộ nhiều unknown-outcome case hơn; vấn đề cần được giải quyết ở hợp đồng nghiệp vụ, không chỉ bằng tăng timeout.

## 13. Virtual threads và blocking I/O trên JDK 21

### 13.1. Không có nghĩa ứng dụng tự chuyển sang virtual threads

JEP 444 hoàn thiện virtual threads trong JDK 21. Chỉ nâng runtime lên Java 21 không tự đổi mọi `Thread` thành virtual thread. Ứng dụng phải chủ động sử dụng API hoặc framework configuration phù hợp.

Ví dụ:

```java
try (ExecutorService executor =
         Executors.newVirtualThreadPerTaskExecutor()) {
    Future<String> result = executor.submit(() -> readFromService());
    System.out.println(result.get());
}
```

Đoạn code cần các import phù hợp và một method `readFromService()` do ứng dụng cung cấp. Mục đích là minh họa mô hình mỗi task một virtual thread.

### 13.2. I/O-bound workload có thể hưởng lợi

Virtual threads giúp dùng mô hình code blocking dễ đọc trong hệ thống có nhiều tác vụ đồng thời chờ I/O. Nhưng chúng không tự làm CPU xử lý nhanh hơn, không tăng số connection database hoặc remote capacity và không thay thế backpressure.

Nếu trước đây một thread pool nhỏ vô tình giới hạn số request đồng thời, chuyển sang virtual threads có thể làm số request tới database/API tăng mạnh. Cần giới hạn tài nguyên thật bằng connection pool, semaphore, concurrency budget hoặc rate limit.

### 13.3. Pinning trên JDK 21

Trên JDK 21, virtual thread có thể bị **pin** vào carrier thread khi thực hiện blocking operation trong một số tình huống, đặc biệt khi giữ monitor `synchronized` hoặc trong native/foreign function call. Điều này có thể ảnh hưởng scalability nếu nhiều virtual thread bị pin trong thời gian dài.

Khi thử virtual threads trên JDK 21:

- Tìm vùng `synchronized` giữ lock trong lúc gọi network I/O dài.
- Kiểm tra thư viện native/JNI hoặc driver I/O có đặc điểm riêng.
- Dùng Java Flight Recorder và sự kiện như `jdk.VirtualThreadPinned` để điều tra khi phù hợp.
- Đo latency, throughput, carrier/platform thread count và connection utilization.
- Không mặc định rằng mọi framework/driver đã tối ưu cho virtual threads chỉ vì chạy được trên JDK 21.

Một số cơ chế pinning thay đổi ở các JDK về sau; hãy đánh giá theo đúng phiên bản runtime sản phẩm đang dùng thay vì suy từ hành vi của JDK khác.

## 14. Bảng tình huống biên cần đặc biệt kiểm thử

| Tình huống | Giả định sai phổ biến | Hành vi/kiểm tra cần có |
|---|---|---|
| TCP read trả ít byte | “Một lần đọc là một message” | Framing, loop/readFully, timeout |
| TCP read trả -1 | “Request chắc đã hoàn tất” | Kiểm tra đủ frame và protocol |
| NIO read trả 0 | “Đã EOF” | Với non-blocking mode: đợi readiness |
| NIO write chưa hết buffer | “write gửi xong tất cả” | Giữ bytes còn lại và tiếp tục khi writable |
| UDP packet lớn hơn buffer | “Nhận nốt ở lần receive sau” | Kiểm soát packet size, phát hiện/giảm truncation |
| DatagramPacket tái sử dụng | “Packet length luôn bằng capacity gốc” | Reset length trước lần receive mới |
| Socket read timeout | “Hết thời hạn toàn bộ request” | Có deadline tổng riêng |
| DNS trả nhiều IP | “Chọn một IP cố định là đủ” | Chính sách address selection/failover |
| Localhost hỗ trợ cả IPv4/IPv6 | “Bind 127.0.0.1 cũng nhận ::1” | Test hai address family |
| TLS handshake lỗi | “Tắt certificate validation là xong” | Sửa certificate, truststore, protocol |
| HTTP 503 | “Mọi HTTP error đều ném IOException” | Kiểm tra status code và body |
| Remote đóng pooled connection | “Mọi reuse luôn thành công” | Pool lifecycle, retry có kiểm soát |
| File đổi encoding | “new String(bytes) luôn giống trước” | Chỉ định charset và contract |
| UTF-8 bị chia chunk | “Mỗi chunk tự decode độc lập được” | Stateful decoding |
| File exists rồi biến mất | “exists bảo đảm read thành công” | Xử lý race tại thao tác |
| Atomic move không hỗ trợ | “Mọi file system đều atomic rename” | Handle AtomicMoveNotSupportedException |
| Shutdown khi thread đang read | “Exception nào cũng là lỗi production” | Phân biệt expected cancellation và failure |
| Timeout sau write | “Server chưa xử lý” | Idempotency/unknown outcome |
| Virtual thread concurrency tăng | “I/O backend cũng tăng capacity” | Resource limit, backpressure |

Danh sách là đầu vào test design. Không phải mọi ứng dụng đều cần tất cả trường hợp; chọn theo giao thức, dependency, OS và yêu cầu vận hành thực tế.

## 15. Thiết kế test tái hiện lỗi I/O và mạng

### 15.1. Baseline phải cố định

Trước khi thay JDK, ghi:

- JDK vendor, major/minor/update/build.
- OS, kernel, architecture, container image.
- JVM flags và security properties.
- DNS, proxy, firewall, certificate/truststore.
- Version thư viện HTTP, Netty, database driver và framework.
- Network topology: localhost, nội bộ, Internet, load balancer, service mesh.
- Connection pool, executor, thread model, timeout và retry.
- Payload đại diện và các lỗi hiện có ở baseline.

Nếu so sánh hai JDK trên môi trường khác nhau, phải công bố rõ những biến số không kiểm soát. Cần tránh kết luận về nguyên nhân chỉ từ một phép thử.

### 15.2. Test với server có thể điều khiển

Một test server hoặc network fault proxy cho phép tạo các kịch bản:

1. Chấp nhận TCP connection nhưng không gửi dữ liệu.
2. Gửi header rồi chờ trước khi gửi body.
3. Gửi frame theo từng byte.
4. Đóng connection giữa message.
5. Reset connection bất ngờ.
6. Trả HTTP redirect loop hoặc 429/503.
7. Trả chunked response hoặc body bị cắt.
8. TLS handshake với certificate hết hạn/không khớp.
9. DNS lookup thất bại hoặc endpoint unreachable.
10. UDP packet thiếu, trùng, đảo thứ tự hoặc vượt buffer.

Mỗi test nên có timeout cứng để tránh treo pipeline. Sử dụng port được cấp động nếu framework hỗ trợ, thay vì cố định port dễ xung đột giữa các build song song.

### 15.3. Test theo ma trận runtime và môi trường

| Chiều kiểm chứng | Trường hợp tối thiểu | Trường hợp mở rộng khi cần |
|---|---|---|
| JDK | Baseline và JDK mục tiêu | Nhiều patch/vendor |
| OS | OS production | Windows/Linux/macOS liên quan |
| Network | localhost và staging thật | IPv4-only, IPv6-only, dual-stack |
| DNS | Host có một/multiple A/AAAA | Failover, cache expiry, negative lookup |
| HTTP | 2xx, 4xx, 5xx, timeout | Redirect, HTTP/2, proxy, stale pool |
| TLS | Trust chain hợp lệ | Cert hết hạn, hostname mismatch, mTLS |
| Payload | ASCII và UTF-8 có dấu | File legacy, Unicode boundary, malformed bytes |
| Stream | Full frame và partial frame | EOF giữa header/body, slow client |
| Concurrency | Tải thường | Concurrent close, shutdown, saturation |
| File I/O | File thường | Permission, symlink, lock, atomic move unsupported |

Không cần nhân tất cả chiều thành ma trận khổng lồ. Dùng risk-based selection: chọn tổ hợp đại diện rủi ro của ứng dụng và các thay đổi JDK/OS thực sự đang diễn ra.

### 15.4. Đo metric thay vì chỉ quan sát pass/fail

Theo dõi:

- DNS resolution latency và số lỗi lookup.
- TCP connect time, read timeout, reset, EOF.
- HTTP status distribution và retry count.
- TLS handshake success/failure.
- Connection pool active/idle/waiting.
- Thread count, virtual-thread event/pinning khi áp dụng.
- Request latency p50/p95/p99 và throughput.
- File I/O error, queue backlog, payload decode error.
- Resource leak: socket/file descriptor, heap, direct buffer và thread.

JFR, ứng dụng tracing/metrics và log có cấu trúc có thể hỗ trợ điều tra. Nhưng không bật log byte payload hoặc TLS debug dài hạn nếu có nguy cơ lộ secret hay gây overhead quá lớn.

## 16. Quy trình điều tra khi hành vi khác giữa hai JDK

### Bước 1: Mô tả chính xác khác biệt

Thay vì “Java 21 lỗi mạng”, ghi: “Trên JDK 17, endpoint A trả sau 300 ms; trên JDK 21, 2% request bị `SocketTimeoutException` ở read stage khi qua proxy B”.

Cần có stack trace, thời điểm, tần suất, JDK build, loại client và môi trường.

### Bước 2: Xác định tầng bị lỗi

Phân loại:

- DNS lookup.
- TCP connect/accept.
- TLS handshake.
- HTTP protocol/client pool.
- Application framing/serialization.
- Database/network driver.
- File read/write/charset.
- Shutdown/cancellation.
- OS/container/network infrastructure.

Không bắt đầu bằng tăng timeout hoặc thay JDK flag khi chưa xác định tầng lỗi.

### Bước 3: Kiểm tra contract API

Hỏi liệu code có phụ thuộc giả định sai về partial read, zero read, socket state, DNS order, EOF, timeout hoặc encoding. Nhiều bug không xuất hiện trên JDK cũ chỉ vì timing thuận lợi.

### Bước 4: So sánh các biến số

Chạy cùng artifact, cùng dependency và cùng cấu hình trên hai JDK nếu có thể. Sau đó đổi từng biến: JDK update, HTTP client version, OS/container image, TLS provider hoặc JVM flags. Giữ bằng chứng để tránh nhầm correlation với causation.

### Bước 5: Tạo regression test tối thiểu

Mô phỏng tình huống biên bằng test server/proxy hoặc file fixture. Chọn điều kiện lặp lại đủ tin cậy để test không phụ thuộc vào timing ngẫu nhiên quá nhiều.

### Bước 6: Sửa ở đúng tầng

Ví dụ:

- Partial read: sửa framing parser.
- Charset: chỉ định encoding.
- DNS stale cache: điều chỉnh discovery/caching có căn cứ.
- TLS: sửa certificate/policy.
- Timeout: xác định deadline và retry.
- Runtime pool: điều chỉnh lifecycle, không sửa JVM socket toàn cục trước.
- Concurrent close: rõ ownership/cancellation contract.

### Bước 7: Kiểm tra lại trên artifact cuối

Chạy test với JAR/WAR/container và JDK thật của production, có proxy/TLS/DNS tương tự. Chỉ chạy unit test trực tiếp từ IDE là chưa đủ.

## 17. Ví dụ xuyên suốt: một lần đọc TCP không nhận đủ header

Giả sử service cũ có giao thức riêng. Bốn byte đầu là độ dài message, theo sau là payload. Code cũ:

```java
byte[] header = new byte[4];
int count = input.read(header);

if (count != 4) {
    throw new IOException("Invalid header");
}
```

Trên môi trường trước đây, tình cờ đa số lần `read(header)` nhận đủ bốn byte. Sau khi đổi JDK hoặc network proxy, header đến thành hai phần; `read()` trả 2 và code xem là lỗi.

Đây không phải bằng chứng JDK vi phạm TCP. Hợp đồng của stream không yêu cầu một lần read phải lấp đầy buffer. Code đúng phải đọc cho đến khi đủ header hoặc gặp EOF/error:

```java
DataInputStream in = new DataInputStream(input);

byte[] header = new byte[4];
in.readFully(header);
```

Sau đó decode length theo endian/protocol đã định, giới hạn payload và dùng `readFully` hoặc stateful parser để đọc body.

Test regression nên cố ý gửi từng byte của header qua những lần write riêng, chèn khoảng nghỉ hoặc network fault injection. Chỉ test payload thông thường là chưa đủ để xác nhận parser chịu được TCP fragmentation.

## 18. Ví dụ xuyên suốt: endpoint HTTPS sau nâng JDK

Một ứng dụng dùng Java HTTP client gọi service B. Khi đổi từ JDK 17 sang 21, một số request thất bại `SSLHandshakeException`.

Quy trình xử lý:

1. Xác định host/port, SNI, proxy và JDK vendor/build.
2. Phân biệt DNS/connect thành công với lỗi trong TLS handshake.
3. Thu thập TLS error có lọc, certificate chain và protocol/cipher negotiation.
4. Kiểm tra truststore/container CA và hostname verification.
5. Kiểm tra có sự thay đổi JDK update hoặc proxy/load balancer đồng thời hay không.
6. Thử kết nối với server cấu hình TLS đúng trong staging.
7. Không tắt certificate validation, không bật cipher yếu toàn hệ thống.
8. Chạy test request thật, mTLS nếu cần và retry/timeout behavior sau khi sửa.

Nếu kết quả là server chỉ hỗ trợ một thuật toán yếu không còn được policy cho phép, giải pháp chính là cập nhật cấu hình TLS của server. Một workaround cục bộ trên client phải được đánh giá bảo mật và giới hạn phạm vi, không trở thành mặc định mới không kiểm soát.

## 19. Ví dụ xuyên suốt: file CSV legacy sau JEP 400

Một batch job trên Windows JDK 17 sử dụng:

```java
String data = Files.readString(path);
```

Trường hợp này cần đọc **đúng contract của method**: `Files.readString(Path)` đã dùng UTF-8 từ JDK 11, nên không thể chỉ vì JEP 400 mà kết luận nó đổi encoding. Nếu batch thực sự dùng `new FileReader(path.toFile())` hoặc `new String(bytes)` không chỉ định charset, những API đó mới là ứng viên bị ảnh hưởng bởi default charset.

Quy trình:

1. Xác định overload thực tế.
2. Kiểm tra encoding nguồn file theo byte hoặc hợp đồng cung cấp.
3. Tạo fixture có tiếng Việt, dấu câu, ký tự ngoài ASCII.
4. Chỉ định charset tại ranh giới đọc.
5. Test dữ liệu đọc vào và dữ liệu ghi ra.
6. Kiểm tra rollback nếu bản cũ và bản mới cùng xử lý chung file trong giai đoạn chuyển tiếp.

Cách phân biệt dựa trên Javadoc giúp tránh sửa những API vốn đã dùng UTF-8 bất kể JVM default charset.

## 20. Phát hành, giám sát và rollback

Các vấn đề I/O thường nhạy tải, độ trễ và network topology nên không phải lúc nào cũng bộc lộ ở test cục bộ. Cần có phát hành từng bước:

1. **Baseline:** lưu metric lỗi socket, HTTP/TLS, DNS, latency, throughput và resource usage.
2. **Staging:** chạy workload đại diện với JDK/container mục tiêu.
3. **Canary:** cho một phần nhỏ lưu lượng, so sánh error rate và p95/p99.
4. **Thang mở rộng:** tăng traffic có điều kiện khi metric nằm trong ngưỡng.
5. **Dừng/rollback:** có trigger rõ ràng cho timeout, TLS failure, connection reset, queue backlog hoặc data corruption.
6. **Theo dõi sau rollout:** kiểm tra batch job, scheduled task và các nhánh ít được gọi.

Rollback không nhất thiết chỉ là đổi JDK flag. Cần giữ image/artifact cũ, JVM flags và dependency đi kèm. Nếu format file, protocol hoặc dữ liệu đã thay đổi, phải xác định compatibility giữa phiên bản cũ và mới. Với lỗi gửi request có unknown outcome, tránh retry/rollback làm tác vụ side effect chạy hai lần.

## 21. Hồ sơ bàn giao và checklist

Hồ sơ migration nên chứa:

- **Environment record:** JDK vendor/update, OS/container, kernel, DNS, proxy, TLS và relevant JVM flags.
- **I/O inventory:** socket, datagram, NIO, HTTP clients, file I/O, parser và encoding.
- **Behavior assumptions:** framing, EOF, timeout, shutdown, DNS ordering, retries, charset và resource ownership.
- **Dependency matrix:** HTTP/network framework, driver, TLS provider, logging/tracing agent và version đã kiểm thử.
- **Verification evidence:** unit, integration, fault injection, TLS/HTTP contract và performance tests.
- **Release evidence:** artifact checksum, image, metric baseline, canary status và rollback plan.

### Checklist trước khi chốt migration

- [ ] Đã phân biệt thay đổi public API, internal implementation, JDK default và môi trường OS.
- [ ] Đã ghi rõ mốc JEP 353, JEP 373, JEP 400 và các tính năng mới thật sự được sử dụng.
- [ ] Đã kiểm tra TCP framing, partial read và partial write.
- [ ] Đã phân biệt EOF, timeout, reset và cancellation.
- [ ] Đã xử lý `SocketChannel.read() == 0` trong non-blocking mode.
- [ ] Đã kiểm tra UDP truncation, `DatagramPacket` reuse và multicast nếu có.
- [ ] Đã xác minh DNS caching, IPv4/IPv6, localhost và failover.
- [ ] Đã xác định timeout connect/read/request/deadline và retry semantics.
- [ ] Đã kiểm tra HTTP status, redirect, pooling, stale connection và TLS.
- [ ] Đã rà soát các API I/O dựa vào default charset và dữ liệu legacy.
- [ ] Đã thử payload Unicode bị chia thành nhiều chunk và malformed input.
- [ ] Đã kiểm tra file permission, symlink, atomic move và race khi dùng file.
- [ ] Đã kiểm tra cleanup tài nguyên, concurrent close và graceful shutdown.
- [ ] Nếu dùng virtual threads, đã giới hạn tài nguyên và kiểm tra pinning trên đúng JDK.
- [ ] Đã test failure injection và các tình huống biên trên artifact cuối.
- [ ] Đã so sánh metric với baseline trong môi trường tương đương.
- [ ] Đã chuẩn bị ngưỡng dừng, rollback và phương án xử lý unknown outcome.

Thay đổi implementation I/O và mạng không có nghĩa Java phá vỡ hợp đồng của các API đã công bố. Nhưng migration có thể làm những giả định chưa từng được kiểm chứng về timing, message framing, DNS, charset, timeout, close và resource lifecycle trở nên rõ ràng. Cách tiếp cận đúng là **bám vào contract, phân tách tầng lỗi, tạo test cho tình huống biên và đo hành vi trên runtime/artifact thật**. Khi đó nhóm có thể phát hiện và sửa đúng nguyên nhân thay vì dựa vào workaround phụ thuộc một JDK hoặc môi trường duy nhất.
