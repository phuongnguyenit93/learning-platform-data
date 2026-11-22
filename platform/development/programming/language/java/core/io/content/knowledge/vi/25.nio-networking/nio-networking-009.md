# Phạm vi I/O mạng và các kiến thức giao thức cần học riêng trong Java NIO

**Java NIO mạng** cung cấp cách lập trình *đọc, ghi, kết nối, chấp nhận kết nối và nhận biết trạng thái sẵn sàng của socket* thông qua các channel và buffer. Những công cụ như `SocketChannel`, `ServerSocketChannel`, `DatagramChannel`, `ByteBuffer`, `Selector` và `SelectionKey` giúp xây dựng tầng vận chuyển dữ liệu, đặc biệt khi muốn một số ít thread xử lý nhiều kết nối.

Tuy nhiên, **gửi/nhận được byte không đồng nghĩa đã xây dựng được một giao thức ứng dụng hoàn chỉnh**. Phía trên tầng I/O còn có cách định ranh giới thông điệp, mã hóa, xác thực, bảo mật TLS, timeout, retry, quản lý phiên, kiểm soát lưu lượng, khôi phục kết nối và các quy tắc nghiệp vụ. Phía dưới Java NIO, các cơ chế TCP/IP, UDP, DNS, kernel networking, firewall và hạ tầng mạng cũng có hợp đồng riêng.

Mục tiêu bài học là **xác định ranh giới kiến thức**: điều gì thuộc API Java NIO mạng cần nắm trong module Java Core I/O, điều gì chỉ cần biết như điều kiện để dùng API đúng, và những chủ đề giao thức nào phải học thành bài chuyên sâu riêng khi xây dựng hệ thống thực tế.

## 1. Phân lớp để tránh nhầm I/O với giao thức

Một ứng dụng gửi yêu cầu qua mạng thường đi qua các tầng:

```text
Quy tắc nghiệp vụ: gọi dịch vụ, phản hồi, lỗi, idempotency, authorization
                            |
Giao thức ứng dụng: HTTP/gRPC/WebSocket hoặc framing tự định nghĩa
                            |
Bảo mật phiên truyền (nếu sử dụng): TLS / mTLS
                            |
Tầng vận chuyển: TCP stream hoặc UDP datagram
                            |
Java I/O API: SocketChannel, DatagramChannel, Selector, ByteBuffer
                            |
Hệ điều hành: socket, network stack, network interface, firewall
                            |
Network / thiết bị / peer ở xa
```

Đây là **sơ đồ tư duy** để phân định trách nhiệm; TLS thực tế thường được áp dụng trên transport thích hợp và các giao thức như QUIC có kiến trúc riêng (tích hợp bảo mật, truyền qua UDP), nên không lấy sơ đồ làm mô hình tuyệt đối cho mọi giao thức.

Với Java NIO:

- **API cung cấp** cách mở/kết nối socket, nhận kết nối mới, đọc/ghi bytes, nhận/gửi datagram, thay đổi blocking mode, đăng ký interest và lấy các sự kiện readiness.
- **API không tự định nghĩa** một gói bytes nghĩa là request gì, có bao nhiêu bytes trong một thông điệp ứng dụng, dùng JSON hay Protobuf, có được phép thực hiện thao tác hay không, hay cần retry thế nào.
- **API cũng không thay OS thực hiện TCP/IP**. Java gọi tới networking stack; việc packet bị chia nhỏ, gửi lại, định tuyến hoặc bị drop là chuyện của transport/OS/network. Chương trình phải hiểu những hệ quả quan sát được qua API.

Điểm dễ nhầm là từ “packet”: ở UDP, mỗi lệnh `send` hướng đến **một datagram**; ở TCP, mỗi `write` chỉ đưa thêm bytes vào **một byte stream**, không tạo ra một “message TCP” có thể nhận nguyên khối từ `read` tương ứng.

## 2. Những kiến thức nằm trong phạm vi Java NIO mạng

### 2.1. Họ channel và trách nhiệm

| API | Dùng để làm gì? | Không tự cung cấp |
| --- | --- | --- |
| `ServerSocketChannel` | Bind vào địa chỉ, lắng nghe TCP và `accept` kết nối mới thành `SocketChannel`. | HTTP server, routing, xác thực, protocol framing. |
| `SocketChannel` | Kết nối TCP, `read`/`write` bytes qua `ByteBuffer`, `shutdownInput/Output`, chọn blocking hoặc non-blocking. | Ranh giới thông điệp, retry an toàn, mã hóa TLS mặc định. |
| `DatagramChannel` | `bind`, `connect` (tùy trường hợp), `send`/`receive` datagram UDP với `ByteBuffer`. | Bảo đảm delivery, ordering, chống duplicate, application ACK. |
| `ByteBuffer` | Quản lý vùng byte có `position`, `limit`, `capacity`, `flip`, `compact`. | Charset nếu không gắn decoder, protocol parser, thread-safety tự động. |
| `Selector` | Đợi các channel đã đăng ký có các sự kiện sẵn sàng phù hợp. | Xử lý request, tự thực hiện read/write, timer nghiệp vụ, fairness tự động. |
| `SelectionKey` | Mang `interestOps`, `readyOps`, attachment và trạng thái đăng ký. | Một bảo đảm “sẽ đọc/ghi hết payload” mỗi lần readiness xuất hiện. |
| `SocketOption` và `StandardSocketOptions` | Điều chỉnh một số socket options, theo loại channel và OS. | Tự tối ưu network, bỏ qua giới hạn kernel hoặc tạo SLA. |

Các lớp kể trên thuộc `java.nio`, `java.nio.channels` và `java.net`. Hãy phân biệt chúng với `FileChannel`: channel cho file có seek, offset và mapping; channel cho socket có network endpoint và có thể đăng ký `Selector` khi là `SelectableChannel`.

### 2.2. Chu kỳ dùng SocketChannel/ServerSocketChannel

Với một kết nối TCP ở chế độ blocking:

1. Server tạo `ServerSocketChannel.open()` rồi `bind(localAddress)`.
2. Server gọi `accept()` để nhận kết nối từ client.
3. Client tạo `SocketChannel.open()` rồi `connect(remoteAddress)`.
4. Hai bên dùng `read(ByteBuffer)` / `write(ByteBuffer)` để trao đổi **byte stream**.
5. Hai bên xác định protocol framing, đóng nửa kết nối khi thích hợp (`shutdownOutput()`) hoặc đóng hẳn channel (`close()`).

Trong chế độ non-blocking, `connect(...)` có thể trả `false` (kết nối chưa hoàn tất); cần kiểm tra `finishConnect()` khi nhận sự kiện phù hợp. `accept()` có thể trả `null` nếu chưa có kết nối mới; `read/write` có thể trả `0` khi chưa thể tiến triển.

**Kiểu channel và blocking mode quyết định hành vi**, không chỉ tên `read`/`write`. Tránh dùng một vòng `while (read() == 0)` chạy liên tục khiến CPU tăng cao; với non-blocking I/O, dùng readiness, queue và backpressure theo kiến trúc đã chọn.

### 2.3. Selector và event loop chỉ giải quyết bài toán readiness

Một event loop đơn giản thường:

```text
configureBlocking(false)
register(selector, OP_ACCEPT / OP_CONNECT / OP_READ ...)
              |
selector.select() đợi kênh sẵn sàng
              |
duyệt selectedKeys và xử lý từng loại sự kiện
              |
read/write bytes, cập nhật per-connection state
              |
đổi interestOps phù hợp; quay lại select
```

Đây là **sơ đồ quy trình**, không phải Java source độc lập. Trong code thật cần:

- Bỏ key đã xử lý khỏi tập `selectedKeys()`, thông thường qua iterator.remove().
- Khi `OP_ACCEPT`: gọi `accept`, xử lý kết quả `null` nếu thích hợp, cấu hình client channel non-blocking và đăng ký `OP_READ`.
- Khi `OP_CONNECT`: gọi `finishConnect`, xử lý lỗi và thay interest ops.
- Khi `OP_READ`: đọc vào buffer thích hợp, phân tích từng phần dữ liệu, xử lý `-1` là phía remote đã kết thúc chiều gửi.
- Khi `OP_WRITE`: ghi tiếp các buffer còn lại; **chỉ quan tâm `OP_WRITE` khi có dữ liệu cần đẩy** để tránh event loop thức liên tục vì socket thường xuyên writable.
- Lưu trạng thái parser và buffer cho **từng connection**, theo dõi queue outbound và áp dụng giới hạn bộ nhớ.
- Xử lý `IOException` theo từng kết nối, thay vì khiến một kết nối lỗi làm sập cả server.

`Selector` cho biết kênh *có thể* thực hiện một thao tác mà không block ở thời điểm kiểm tra; nó không định nghĩa số byte chắc chắn chuyển được, và không làm toàn bộ logic của một request trở thành bất đồng bộ. Nếu handler chạy truy vấn DB chậm hoặc CPU nặng ngay trên event-loop thread, nó vẫn có thể trì hoãn các connection khác.

## 3. TCP là byte stream, không phải chuỗi message

Đây là kiến thức transport **bắt buộc ở mức nền tảng** để dùng `SocketChannel` đúng. TCP đem lại một **byte stream có thứ tự**, với cơ chế truyền tin cậy theo mô hình TCP khi kết nối còn hoạt động. Nhưng không có ranh giới giữa các lần `write` của ứng dụng:

```text
Client gọi:
  write("HELLO")
  write("WORLD")

Server có thể read được:
  "HELLOWORLD"
hoặc:
  "HE" + "LLOW" + "ORLD"
hoặc nhiều cách chia chunk khác nhau
```

Đây là minh họa các cách phân đoạn *quan sát qua read*; không phải lời hứa hệ điều hành phải chọn một cách cụ thể. Mỗi `read` được quyền trả ít bytes hơn phần còn trống trong buffer. Khi stream kết thúc có thể trả `-1`; việc một phía đóng kết nối đột ngột có thể gây exception và không thể suy ra toàn bộ dữ liệu chưa xử lý đã được peer application chấp nhận.

### Framing là phần của protocol ứng dụng

Muốn tách message, hai bên phải thống nhất một quy tắc, ví dụ:

| Kiểu framing | Nguyên lý | Lỗi và giới hạn cần xét |
| --- | --- | --- |
| **Length-prefix** | Header chứa độ dài; tiếp theo là đúng số byte payload. | Thống nhất byte order, kích thước header, giới hạn tối đa, xử lý EOF giữa frame. |
| **Delimiter** | Ký tự/chuỗi đặc biệt kết thúc frame, ví dụ `\n`. | Escaping, delimiter bên trong nội dung, giới hạn chiều dài dòng, encoding. |
| **Fixed-length** | Mỗi record có cùng số byte. | Cấu trúc cứng, padding, phiên bản dữ liệu. |
| **Self-describing format** | Parser của định dạng tự tìm ranh giới theo luật giao thức. | Parser có thể phải giữ state qua nhiều lần read, cần giới hạn độ phức tạp. |

**Không lấy `ByteBuffer.position()` hoặc số byte của một lần `SocketChannel.read` làm số lượng message.** Một lần read có thể chứa nửa header, một message hoàn chỉnh cộng một phần message tiếp, hoặc nhiều message liền nhau. Parser phải dùng trạng thái tích lũy qua nhiều lần đọc. Với non-blocking code, buffer có thể còn dữ liệu chưa parse và phải được `compact()` hoặc quản lý bằng queue/ring buffer cho lần đọc tiếp.

### Ví dụ Java 17+: một frame TCP có header độ dài

Ví dụ dùng blocking `SocketChannel` qua địa chỉ loopback để tập trung vào **ranh giới message**; không cần thiết lập máy chủ mạng bên ngoài. Một frame gồm 4 byte số nguyên big-endian là độ dài UTF-8, tiếp theo là số byte payload tương ứng. Đây là giao thức ví dụ tự đặt ra để học, **không phải HTTP hoặc một chuẩn sản xuất**.

Tạo file `TcpFramingDemo.java`:

```java
import java.io.EOFException;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.*;

public class TcpFramingDemo {
    static void readFully(SocketChannel socket, ByteBuffer dst) throws IOException {
        while (dst.hasRemaining()) {
            int n = socket.read(dst);
            if (n < 0) throw new EOFException("Truncated TCP frame");
            if (n == 0) throw new IOException("Blocking read made no progress");
        }
    }

    static void writeFully(SocketChannel socket, ByteBuffer src) throws IOException {
        while (src.hasRemaining()) {
            int n = socket.write(src);
            if (n == 0) throw new IOException("Blocking write made no progress");
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();
        try (ServerSocketChannel server = ServerSocketChannel.open()) {
            server.bind(new InetSocketAddress(loopback, 0));
            ExecutorService pool = Executors.newSingleThreadExecutor();
            try {
                Future<String> received = pool.submit(() -> {
                    try (SocketChannel peer = server.accept()) {
                        ByteBuffer header = ByteBuffer.allocate(Integer.BYTES);
                        readFully(peer, header);
                        header.flip();
                        int size = header.getInt();
                        if (size < 0 || size > 1024)
                            throw new IOException("Invalid frame size");
                        ByteBuffer body = ByteBuffer.allocate(size);
                        readFully(peer, body);
                        body.flip();
                        return StandardCharsets.UTF_8.decode(body).toString();
                    }
                });

                try (SocketChannel client = SocketChannel.open()) {
                    client.connect(server.getLocalAddress());
                    byte[] message = "Xin chào".getBytes(StandardCharsets.UTF_8);
                    ByteBuffer packet = ByteBuffer.allocate(Integer.BYTES + message.length);
                    packet.putInt(message.length).put(message).flip();
                    writeFully(client, packet);
                    client.shutdownOutput();
                }
                System.out.println("tcp-message=" + received.get(5, TimeUnit.SECONDS));
            } finally {
                pool.shutdownNow();
            }
        }
    }
}
```

Biên dịch/chạy Java 17+ ở môi trường cho phép tạo TCP loopback socket:

```bash
javac --release 17 TcpFramingDemo.java
java TcpFramingDemo
```

Output đã kiểm chứng:

```text
tcp-message=Xin chào
```

Giải thích:

1. `server.bind(..., 0)` yêu cầu OS chọn một cổng tạm, rồi client dùng địa chỉ trả về từ `server.getLocalAddress()`.
2. Server chạy tác vụ nhận kết nối riêng, đọc **đủ 4 byte** header rồi phân tích length với `getInt()`. `ByteBuffer` mặc định dùng big-endian, nên hai phía phù hợp nhau.
3. Kiểm tra `0 <= size <= 1024` trước khi cấp phát payload: chỉ đọc 4 byte từ network chưa đủ để tin bên gửi sẽ không khai báo dung lượng quá lớn.
4. Server tiếp tục `readFully` tới khi đủ payload hoặc ném `EOFException` khi peer đóng giữa frame. Client dùng `writeFully`, không giả định một `write` gửi đủ.
5. `UTF_8.decode` giải mã **toàn bộ payload được frame**. Nếu hai bên dùng charset khác nhau hoặc payload hỏng thì cần quy tắc báo lỗi decoder/validation của giao thức.
6. `Future.get(5, TimeUnit.SECONDS)` giới hạn thời gian đợi kết quả trong chương trình demo, không phải một hệ thống quản lý timeout cho toàn bộ hoạt động kết nối sản xuất.

**Phạm vi bài:** code chủ yếu minh họa primitive NIO và framing. Chưa xử lý giao thức có nhiều frame liên tiếp, backpressure trên non-blocking socket, TLS, xác thực, replay, quota, kiểm soát request hoặc recovery. Khi xây dựng dịch vụ thật, cần tách parser/protocol state khỏi transport và ràng buộc kích thước/tài nguyên cho mỗi kết nối.

## 4. UDP có ranh giới datagram nhưng không có bảo đảm như TCP

`DatagramChannel` nhận và gửi **datagram** bằng `send(ByteBuffer, SocketAddress)` / `receive(ByteBuffer)`. Khác TCP byte stream:

- Mỗi datagram có ranh giới thông điệp ở tầng transport; một lần nhận thành công trả thông tin sender của một datagram.
- Datagram có thể **bị mất, đến không đúng thứ tự, trùng lặp** hoặc quá lớn so với mạng, tùy điều kiện. Không suy ra gửi thành công ở client thì remote app đã xử lý.
- Khi buffer nhận nhỏ hơn datagram, **phần vượt quá có thể bị loại bỏ**; không có “đọc tiếp nửa còn lại” như TCP stream. Vì vậy cần định nghĩa maximum payload và kích thước receive buffer đúng.
- `connect` trên `DatagramChannel` xác định peer mặc định/lọc giao tiếp theo peer, nhưng không thực hiện TCP handshake và **không** biến UDP thành transport tin cậy.
- UDP không có stream EOF tương tự TCP; cơ chế timeout, thông báo mất kết nối hoặc kết thúc phiên thuộc thiết kế ứng dụng/protocol.

Muốn xây giao thức tin cậy trên UDP, phải học thêm sequence number, ACK, retransmission, duplicate suppression, ordering, congestion/flow control và cách xác định peer/phiên. Đây là phần **giao thức chuyên sâu**, vượt quá việc học API `DatagramChannel` đơn thuần. Một số công nghệ như QUIC đã triển khai các cơ chế riêng, không nên tự xây lại nếu không có nhu cầu kỹ thuật cụ thể.

### Ví dụ Java 17+: gửi và nhận một UDP datagram qua loopback

Tạo file `UdpDatagramDemo.java`:

```java
import java.net.*;
import java.nio.*;
import java.nio.channels.*;
import java.nio.charset.StandardCharsets;

public class UdpDatagramDemo {
    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();
        try (DatagramChannel receiver = DatagramChannel.open();
             DatagramChannel sender = DatagramChannel.open()) {
            receiver.bind(new InetSocketAddress(loopback, 0));
            sender.bind(new InetSocketAddress(loopback, 0));
            byte[] text = "PING".getBytes(StandardCharsets.UTF_8);
            int sent = sender.send(ByteBuffer.wrap(text), receiver.getLocalAddress());
            ByteBuffer buffer = ByteBuffer.allocate(64);
            SocketAddress from = receiver.receive(buffer);
            buffer.flip();
            String received = StandardCharsets.UTF_8.decode(buffer).toString();
            System.out.println("udp-sent-bytes=" + sent);
            System.out.println("udp-received=" + received);
            System.out.println("udp-has-sender=" + (from != null));
        }
    }
}
```

```bash
javac --release 17 UdpDatagramDemo.java
java UdpDatagramDemo
```

Kết quả đã kiểm chứng khi loopback cho phép UDP và datagram đến nơi:

```text
udp-sent-bytes=4
udp-received=PING
udp-has-sender=true
```

`sender.send` gửi 4 byte từ buffer. `receiver.receive` lấy một datagram và địa chỉ người gửi; `flip()` chuẩn bị vùng byte vừa nhận cho decoder. Demo dùng datagram nhỏ, cùng host nên dễ quan sát. **Một lần chạy thành công không chứng minh UDP giao hàng tin cậy trên mạng thực.** Trong môi trường chặn socket hoặc drop datagram, blocking `receive` có thể đợi; ứng dụng thật nên quy định deadline, xử lý lỗi và đóng channel khi hủy tác vụ.

## 5. Kiến thức TCP/IP cần biết nhưng phải học riêng khi đào sâu

Java NIO **phơi bày** hệ quả của tầng vận chuyển qua I/O result và option; kiến thức sâu về TCP/IP thuộc chủ đề giao thức hoặc mạng máy tính.

| Khái niệm | Cần hiểu ở mức dùng NIO | Học chuyên sâu riêng khi nào? |
| --- | --- | --- |
| IP, port, endpoint | `InetSocketAddress` chỉ định địa chỉ + cổng; server bind, client connect. | Định tuyến, IPv4/v6, NAT, subnet, load balancer, multi-homing. |
| DNS | Hostname cần phân giải thành địa chỉ; có thể lỗi hoặc thay đổi. | TTL, caching, split-horizon DNS, failover, DNSSEC, service discovery. |
| TCP connection | Có handshake, thứ tự byte, half-close, EOF, reset; `read` không giữ message boundary. | Congestion control, retransmission, window scaling, keepalive tuning, queueing và packet capture. |
| TCP flow control | Writer có thể phải chờ hoặc `write` chuyển ít byte; cần outbound queue/backpressure. | Receive window, congestion window, thuật toán điều khiển nghẽn, bufferbloat. |
| UDP datagram | Có ranh giới gói; có thể mất/trùng/sai thứ tự; buffer nhỏ gây cắt dữ liệu. | MTU, fragmentation, application retransmission, jitter, streaming thời gian thực. |
| Firewall/NAT | Bind/listen không có nghĩa thiết bị ở xa truy cập được; kết nối có thể bị chặn. | Stateful firewall, NAT traversal, reverse proxy, ingress policy. |
| Timeout | Một socket có thể treo rất lâu nếu không quy định thời hạn và xử lý hủy. | Deadline propagation, retry budgets, circuit breaker, failure detectors. |

Ví dụ thấy `SocketChannel.write` trả `0` ở chế độ non-blocking không nhất thiết có nghĩa network đã hỏng; có thể send buffer chưa sẵn sàng. Ngược lại, một write trả số byte dương chỉ chứng minh bytes đã được chuyển theo hợp đồng local API, **không xác nhận remote ứng dụng đã nhận, parse hoặc commit yêu cầu**. Muốn biết remote đã xử lý đúng cần cơ chế acknowledgement **ở giao thức ứng dụng**.

## 6. Giao thức ứng dụng phải định nghĩa rõ ràng, không phát sinh tự động từ Channel

Một giao thức giữa client và server cần trả lời các câu hỏi:

1. **Message bắt đầu/kết thúc ở đâu?** Length-prefix, delimiter, header định dạng hay cấu trúc đã chuẩn hóa?
2. **Dữ liệu là gì?** Text UTF-8, JSON, Protobuf, CBOR hay binary tùy chỉnh? Byte order, charset, null, field bắt buộc?
3. **Phiên bản được tương thích thế nào?** Field cũ/mới, version negotiation, schema validation, giới hạn kích thước?
4. **Request/response ghép cặp bằng gì?** Request id, correlation id, multiplexing, thứ tự phản hồi?
5. **Lỗi trả ra thế nào?** Error code, transient/permanent, malformed input, unknown request, server busy?
6. **Thời hạn là bao lâu?** Timeout kết nối, đọc, xử lý, deadline toàn giao dịch và cancellation?
7. **Retry có an toàn không?** Nếu kết nối đứt sau khi gửi yêu cầu, bên gửi có biết server đã xử lý chưa? Idempotency key và deduplication thuộc giao thức/nghiệp vụ.
8. **Phân quyền ra sao?** Authentication, authorization, mTLS/token, auditing, rate limit và quota.

Một protocol parser tốt phải xử lý **dữ liệu đến từng phần** và input không tin cậy. Đừng cấp phát `ByteBuffer.allocate(untrustedLength)` trước khi kiểm tra giới hạn, đừng tin một lần read đủ header, và đừng xử lý request chưa xác thực bằng cách chạy logic nghiệp vụ với quyền hệ thống.

### So sánh với HTTP

Khi nghiệp vụ chỉ cần gọi REST API, **`java.net.http.HttpClient`** hoặc client framework phù hợp thường là lựa chọn đúng hơn tự dùng `SocketChannel` rồi tự viết parser HTTP. Một HTTP implementation đã mang theo các quy tắc URL, method, header, status, streaming body, phiên bản HTTP, HTTP/2 multiplexing và tích hợp TLS theo cấu hình.

`SocketChannel` chỉ cung cấp **byte transport**, không tự hiểu `GET /... HTTP/1.1`, `Content-Length`, chunked transfer, HTTP/2 frames, cookies hoặc xác thực. `HttpClient` trong module `java.net.http` hỗ trợ HTTP và WebSocket client; một ứng dụng HTTP server có thể dùng framework chuyên dụng. Xây protocol qua raw socket là bài tập hữu ích để hiểu framing, nhưng không nên triển khai giao thức phổ biến từ đầu nếu thư viện chuẩn đã đáp ứng nhu cầu.

## 7. TLS, mTLS và bảo mật nằm ở tầng nào?

`SocketChannel` **không tự mã hóa** bytes. Một kết nối TCP không TLS truyền dữ liệu dưới dạng plaintext ở mức ứng dụng (dù có thể có bảo vệ riêng ở tầng mạng/hạ tầng, điều đó không thay TLS end-to-end theo yêu cầu). Để bảo vệ dữ liệu truyền:

- **TLS** đòi hỏi handshake, xác nhận danh tính peer theo chứng chỉ/hostname, trao đổi khóa, mã hóa và kiểm tra tính toàn vẹn của record.
- **mTLS** cho phép xác thực lẫn nhau bằng chứng chỉ client/server; còn mapping từ danh tính đã xác thực tới quyền truy cập nghiệp vụ là **authorization**, không do TLS tự quyết định.
- Java có `SSLSocket` / `SSLServerSocket` cho mô hình stream và **`SSLEngine`** cho trường hợp muốn điều khiển mã hóa qua buffer, có thể tích hợp với NIO non-blocking. `SSLEngine.wrap/unwrap`, handshake status, delegated tasks, close-notify và trạng thái buffer đòi hỏi một state machine riêng.
- Không truyền dữ liệu nhạy cảm hoặc xác thực qua raw `SocketChannel` rồi mặc định nó an toàn vì ở trong mạng nội bộ.

Phần cần biết trong **Java Core I/O** là ranh giới trách nhiệm và API nào tích hợp. Thiết kế ciphersuite, certificate validation, CA trust, revocation, key rotation, ALPN, TLS handshake state machine và phòng chống tấn công thuộc **bài bảo mật/giao thức chuyên sâu**. Nếu nghiệp vụ chỉ cần HTTPS client, dùng thư viện HTTP/TLS chuẩn với kiểm tra chứng chỉ và hostname được bật; đừng tắt verification để chữa lỗi kết nối trong production.

## 8. Timeout, cancel, backpressure và đóng kết nối

Đây là phần thiết kế I/O cần hiểu ở mức API, còn chính sách cụ thể thường nằm ở hệ thống mạng/application.

**Timeout không có một công tắc dùng cho mọi thao tác NIO:**

- Blocking `SocketChannel.connect` và `read` có hành vi chờ khác với non-blocking connect/read qua `Selector`. Cần xác định deadline ở cấp tác vụ, có thể dùng event loop timer và cancel/close đúng cách.
- `Selector.select(timeout)` giới hạn lần chờ readiness, **không giới hạn tổng thời gian xử lý request**. Cần tự lưu thời điểm bắt đầu/deadline theo connection/request.
- Kết nối thành công không bảo đảm peer còn đáp ứng; TCP keepalive ở OS khác với application heartbeat hoặc read deadline.
- Khi dùng `Future`/asynchronous framework, timeout của việc **đợi kết quả** có thể không tự dừng socket I/O; phải kết nối cơ chế hủy với vòng đời channel.

**Backpressure:** nếu phía nhận chậm hơn phía gửi, outbound buffer có thể tăng không giới hạn. Một server NIO đúng cần giới hạn số bytes pending mỗi connection, tạm ngừng đọc hoặc trả lỗi/làm chậm producer, và bật `OP_WRITE` khi có bytes chưa gửi. Đây là chính sách tài nguyên ứng dụng, không phải công việc tự động của `Selector`.

**Close:** với TCP, `shutdownOutput()` báo kết thúc chiều gửi, trong khi vẫn có thể đọc phản hồi; `close()` đóng channel và có thể khiến I/O đang chờ bị ngắt. Khi peer đọc được `-1`, đó là trạng thái end-of-stream cho chiều đọc; **không có nghĩa message trước đó hợp lệ nếu parser vẫn thiếu byte**. Vùng buffer còn bytes hoặc request chưa ACK cần có chính sách kết thúc rõ ràng. Với UDP không có khái niệm stream EOF/half-close giống TCP.

## 9. Phân biệt lỗi transport, protocol và nghiệp vụ

| Tình huống | Thuộc lớp nào? | Xử lý chính |
| --- | --- | --- |
| `ConnectException` khi không kết nối được | Transport/network | Log địa chỉ/cổng, đánh giá timeout/retry theo deadline; không tự động retry vô hạn. |
| `read` trả `-1` giữa frame TCP | Transport kết hợp framing | Đánh dấu message chưa đủ, từ chối dữ liệu dở và đóng/khôi phục theo protocol. |
| `write` ghi ngắn hoặc trả `0` khi non-blocking | NIO I/O state | Giữ buffer phần còn lại, cập nhật readiness/backpressure. |
| Frame khai báo độ dài vượt quota | Application protocol/parser | Từ chối sớm, giới hạn cấp phát bộ nhớ và đóng kết nối nếu vi phạm giao thức. |
| JSON sai schema, phiên bản không tương thích | Application protocol/schema | Trả protocol error với mã lỗi phù hợp. |
| TLS certificate không tin cậy | Security/identity | Từ chối handshake; kiểm tra truststore/hostname, không bỏ validation. |
| HTTP status 401/403 | HTTP + authorization | Xử lý credential/quyền, không nhầm thành TCP connection failure. |
| Request thanh toán đã được server xử lý nhưng ACK bị mất | Application consistency | Idempotency key, query transaction status; tránh retry mù gây double charge. |
| Datagram UDP mất | UDP/network | Chấp nhận mất nếu là telemetry best-effort hoặc thiết kế reliability riêng. |
| Nhiều request ngốn CPU và làm nghẽn event loop | Application scheduling | Giới hạn công việc, tách xử lý nặng khỏi thread vận hành selector. |

Nhận diện đúng lớp lỗi giúp tránh một anti-pattern: thấy `IOException` rồi “gửi lại toàn bộ request” một cách tự động. Với request **không idempotent**, lỗi kết nối xảy ra sau khi server đã cập nhật dữ liệu có thể khiến retry thực hiện thêm lần nữa. Độ tin cậy nghiệp vụ cần một protocol/transaction identity mà bản thân I/O API không biết.

## 10. Những phần cần học riêng khi phát triển hệ thống mạng

Các chủ đề dưới đây liên quan sát sao tới NIO nhưng cần chương trình học chuyên sâu riêng vì có bộ quy tắc vượt xa việc đọc/ghi buffer:

| Chủ đề học riêng | Trọng tâm tối thiểu |
| --- | --- |
| **TCP/IP và mạng máy tính** | IP/port, DNS, handshake, connection states, congestion/flow control, routing, NAT/firewall, socket diagnostics, packet capture. |
| **Giao thức ứng dụng** | Framing, request/response, encoding, schema, versioning, parser incremental, multiplexing, heartbeat và error contract. |
| **HTTP/HTTPS và WebSocket** | HTTP methods, headers, body framing, caching, status codes, HTTP/2, WebSocket handshake/frames, reverse proxy. |
| **TLS/mTLS và bảo mật** | Certificate/PKI, truststore, hostname verification, TLS handshake, SSLEngine state, secrets, authentication/authorization. |
| **Resilience trong distributed systems** | Timeout budgets, retry/backoff/jitter, idempotency, duplicate suppression, circuit breaker, partial failure. |
| **Event-loop architecture** | Selector lifecycle, per-connection state, write queue, fairness, task offloading, buffer pooling, leak detection. |
| **UDP / realtime / QUIC** | Datagram loss/reorder, MTU, reliable delivery khi cần, jitter buffers, congestion control, QUIC/HTTP3. |
| **Quan sát và vận hành** | Metrics latency/throughput, connection counts, TLS errors, tracing, packet logging an toàn, load testing. |

Không bắt buộc học toàn bộ chi tiết này trước khi viết NIO network hello-world. Nhưng khi chuyển từ demo sang production, chủ đề nào ảnh hưởng trực tiếp tới hợp đồng dịch vụ phải được chọn và đào sâu có hệ thống.

### Một lộ trình hợp lý

1. Bắt đầu với `ByteBuffer` và hành vi short read/write, EOF, `flip/compact`.
2. Hiểu `SocketChannel` / `ServerSocketChannel` ở **blocking mode**; tự viết một length-prefixed message nhỏ, có giới hạn payload và xử lý EOF dở.
3. Thử `DatagramChannel` để nhận ra ranh giới và failure model khác TCP.
4. Sau khi thông thạo byte transport, chuyển sang `configureBlocking(false)`, `Selector`, `SelectionKey`, trạng thái kết nối và outbound queue/backpressure.
5. Học TLS/HTTP/application protocol riêng khi mục đích thực tế yêu cầu; ưu tiên API/framework chuẩn thay vì tự viết HTTP/TLS.
6. Cuối cùng kiểm tra failure mode, timeout, retry safety, security, load test và khả năng quan sát trên mạng thật.

## 11. Những ngộ nhận thường gặp

**Ngộ nhận 1: “`SocketChannel` là một HTTP client.”**

Sai. Channel chỉ trao đổi bytes với TCP peer. Không có xử lý HTTP method/status/header mặc định. HTTP client là `java.net.http.HttpClient` hoặc framework phù hợp.

**Ngộ nhận 2: “Một lần `write` tương ứng một lần `read`.”**

Sai với TCP. Bytes có thể được gom/chia thành nhiều lần read. Cần framing và parser tích lũy.

**Ngộ nhận 3: “Có Selector thì server tự động xử lý được mọi request bất đồng bộ.”**

Sai. Selector chỉ báo readiness. Handler blocking hoặc CPU nặng vẫn làm nghẽn event loop; state machine, queue và scheduling do ứng dụng quản lý.

**Ngộ nhận 4: “UDP connect thành công có nghĩa peer đã nhận kết nối.”**

Sai. UDP không sử dụng TCP handshake. `DatagramChannel.connect` cấu hình peer liên quan; không chứng minh bên kia tồn tại hoặc datagram được giao.

**Ngộ nhận 5: “Đã gửi đủ bytes tức là giao dịch đã thành công.”**

Sai. Thành công của local I/O không phải ACK của remote ứng dụng. Cần application-level response và chính sách idempotency khi retry.

**Ngộ nhận 6: “Non-blocking read trả 0 là EOF.”**

Sai. `0` nghĩa chưa chuyển byte trong lời gọi hiện tại (có thể do buffer rỗng hoặc trạng thái chưa sẵn sàng); `-1` mới là EOF của stream đối với đọc TCP.

**Ngộ nhận 7: “TCP bảo đảm không mất dữ liệu nghiệp vụ trong mọi trường hợp.”**

Sai. TCP cho mô hình byte stream đáng tin cậy khi kết nối hoạt động; reset, timeout hoặc crash vẫn tạo trạng thái chưa rõ bên kia đã xử lý tới đâu. Cần giao thức xác nhận/khôi phục cấp ứng dụng.

**Ngộ nhận 8: “TLS là một option tự có của `SocketChannel`.”**

Sai. Dùng SSL/TLS APIs hoặc framework thích hợp, quản lý handshake, validation và lifecycle. Raw SocketChannel không mã hóa payload tự động.

**Ngộ nhận 9: “Trong loopback chạy đúng thì kết nối qua Internet chắc chắn đúng.”**

Sai. Loopback không mô phỏng đầy đủ packet loss, latency, NAT, firewall, proxies, MTU, congestion, certificates, mạng đứt quãng và pressure của server.

## 12. Checklist trước khi chọn Java NIO cho network service

- **Transport:** chọn TCP hay UDP vì yêu cầu delivery/ordering, không chỉ vì muốn tốc độ.
- **Protocol:** xác định framing, encoding, maximum message size, version, parser state.
- **Blocking model:** cần blocking/virtual thread hoặc non-blocking selector? Chọn theo số kết nối, latency, workload và năng lực vận hành.
- **ByteBuffer:** ownership từng connection, `flip/compact`, partial read/write, charset decode across chunks.
- **Backpressure:** giới hạn inbound/outbound queue, per-client quota, chính sách từ chối khi quá tải.
- **Timeout:** kết nối, read, write progress, processing deadline, cancellation, heartbeat.
- **Security:** TLS/hostname verification, authentication, authorization, chống dữ liệu đầu vào độc hại.
- **Resilience:** retry chỉ khi an toàn, idempotency và duplicate handling, phân biệt lỗi transport/protocol/kinh doanh.
- **Resource lifecycle:** đóng channel/selector, bỏ key, tránh leak socket và buffer direct.
- **Testing:** loopback unit demo, integration qua network thật, kiểm thử payload bị chia chunk, lỗi EOF giữa frame, payload quá lớn, mạng chậm/ngắt và sender nhanh hơn receiver.

### Câu hỏi tự kiểm tra

**1. Hai lần `client.write("A")` và `client.write("B")` có bảo đảm server đọc được lần lượt “A” và “B” trong đúng hai lệnh read?**  
Không. TCP giữ thứ tự bytes nhưng không giữ ranh giới các lời gọi write. Server có thể thấy “AB” trong một read hoặc từng phần.

**2. `Selector` có xử lý HTTP request hay chỉ báo readiness?**  
Chỉ báo readiness của các channel được đăng ký. Parser HTTP, việc định tuyến và nghiệp vụ thuộc tầng khác.

**3. `DatagramChannel.receive` nhận một phần datagram rồi có thể đọc tiếp phần còn lại bằng `receive` lần sau?**  
Không. Nếu buffer nhận không đủ, phần vượt quá của datagram có thể bị loại bỏ; lần receive sau là cho datagram khác.

**4. Chọn `SocketChannel` thì traffic đã được mã hóa tự động chưa?**  
Chưa. Cần TLS stack như `SSLEngine` hoặc API/framework HTTPS/TLS thích hợp.

**5. Một request đã `write` xong rồi socket reset, có nên retry mọi request ngay không?**  
Không. Remote application có thể đã xử lý. Cần xác định idempotency và trạng thái xử lý ở tầng ứng dụng.

**6. Khi nào nên dùng `HttpClient` thay vì raw `SocketChannel`?**  
Khi nghiệp vụ cần HTTP/HTTPS client thông thường; thư viện HTTP xử lý các quy tắc giao thức mà raw channel không tự cung cấp.

**7. Vì sao học Java NIO vẫn cần hiểu cơ bản TCP/UDP?**  
Vì kết quả `read/write` và lựa chọn cơ chế framing, timeout, reliability phụ thuộc loại transport. Nhưng nghiên cứu chi tiết congestion control, DNS, TLS hay HTTP là các mảng kiến thức riêng.

## Tài liệu chính thức

- Java SE 21: [`SocketChannel`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SocketChannel.html), [`ServerSocketChannel`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/ServerSocketChannel.html) — TCP connect, accept, read/write.
- Java SE 21: [`DatagramChannel`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/DatagramChannel.html) — UDP datagram send/receive.
- Java SE 21: [`Selector`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/Selector.html), [`SelectionKey`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SelectionKey.html) — non-blocking readiness.
- Java SE 21: [`ByteBuffer`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html) — buffer state và byte handling.
- Java SE 21: [`SSLEngine`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLEngine.html) — tích hợp TLS với buffers/transport.
- Java SE 21: [`java.net.http`](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/module-summary.html) — HTTP client và WebSocket APIs.

**Điều cần ghi nhớ:** Java NIO mạng giúp xây *đường đi của bytes và cơ chế readiness*, còn giao thức truyền tin quyết định *bytes biểu thị thông điệp nào, xử lý ra sao, an toàn và tin cậy đến mức nào*. Hãy học cả hai lớp nhưng giữ đúng ranh giới trách nhiệm để không vô tình biến một demo socket thành một protocol production thiếu framing, TLS, timeout hoặc quy tắc khôi phục.