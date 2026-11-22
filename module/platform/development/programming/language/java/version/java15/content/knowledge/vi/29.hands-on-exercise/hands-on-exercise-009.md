# Xây dựng UDP echo service có timeout và quản lý tài nguyên trong Java

**Ngữ cảnh:** Java 15 → Thực hành. Bài dùng API mạng `java.net.DatagramSocket` và `DatagramPacket` hiện vẫn được hỗ trợ, viết mã theo **Java 17+**, chỉ áp dụng các kiến thức và cách xử lý còn phù hợp với hệ thống hiện nay.

## 1. Mục tiêu và kết quả thực hành

Xây dựng một **UDP echo service**: client gửi một datagram đến server; server đọc đúng số byte nhận được rồi gửi lại nguyên payload đến đúng địa chỉ IP và cổng nguồn. Ngoài chức năng echo, chương trình cần:

1. **Timeout server:** `receive()` chỉ chờ tối đa 300 ms mỗi lượt để kiểm tra yêu cầu dừng; nếu timeout vì rỗi, **server tiếp tục phục vụ**, không tự thoát.
2. **Timeout client:** giới hạn thời gian chờ phản hồi **cho mỗi lần thử**; nếu không thấy phản hồi tương ứng thì thử lại tối đa số lần cấu hình, sau đó báo `SocketTimeoutException`.
3. **Quản lý tài nguyên:** `DatagramSocket` được đóng qua `try-with-resources`/`AutoCloseable`; khi được yêu cầu dừng, `close()` đánh thức luồng đang chờ nhận datagram.
4. **Giới hạn dữ liệu và mã hóa:** sử dụng UTF-8, kiểm tra kích thước theo **byte**, giữ đúng `getLength()`/`getOffset()`, tránh xử lý phần đệm không thuộc gói tin.
5. **Kiểm thử:** có chương trình smoke test riêng chạy echo Unicode, timeout hai phía, datagram quá lớn và dừng server sạch.

Mẫu chạy trên **`127.0.0.1` (loopback IPv4)** để thuận tiện thử nghiệm. Mở dịch vụ ra mạng thực tế đòi hỏi cấu hình địa chỉ bind, firewall, giới hạn tải và bảo vệ giao thức phù hợp.

## 2. Hiểu đúng UDP và “echo”

UDP truyền các **datagram độc lập**. Nó **không cam kết** datagram đến đích, chỉ đến một lần, đến đúng thứ tự, hoặc đến trước một deadline. Gọi `DatagramSocket.send(...)` thành công có nghĩa datagram đã được chấp nhận để gửi ở phía cục bộ, **không chứng minh** bên kia đã nhận hay xử lý.

Khác TCP, UDP **không cung cấp luồng byte có kết nối tin cậy**. `DatagramSocket.connect(host, port)` trong Java chỉ gắn endpoint mặc định/lọc địa chỉ đối tác cho socket, **không thực hiện TCP-style handshake** và không làm UDP có khả năng bảo đảm giao hàng.

Luồng xử lý trong ví dụ:

```text
Client [cổng UDP tạm do OS chọn]             Server [127.0.0.1:7070]
    |                                                  |
    |---- datagram: "<requestId>|xin chào UDP" ------->|
    |                                                  | receive → kiểm tra byte count
    |<--- echo lại nguyên datagram --------------------|
    |                                                  |
    | so khớp toàn bộ byte requestId + message         |
    | trả về "xin chào UDP" nếu khớp                     |
```

Client thêm `UUID` vào payload để phân biệt phản hồi của lời gọi hiện tại với phản hồi cũ/không khớp. Server là **echo trong suốt**, không cần hiểu cấu trúc payload; nó chỉ gửi lại đúng byte đã nhận. UUID **không phải** cơ chế xác thực nguồn và không ngăn kẻ tấn công giả mạo datagram.

Các thông số được chọn cho bài học:

| Tham số | Giá trị mẫu | Lý do |
| --- | --- | --- |
| Địa chỉ bind | `127.0.0.1` | Chỉ truy cập trên máy đang chạy; tránh lộ demo ra mạng. |
| Cổng mặc định | `7070` | Dễ chạy thủ công, có thể đổi qua tham số dòng lệnh. |
| Payload tối đa | **1.024 byte** | Giới hạn bộ nhớ/gói tin; gồm cả UUID, dấu `|` và nội dung UTF-8. |
| Buffer nhận server | **1.025 byte** | Nếu datagram dài hơn 1.024 byte, nhận được 1.025 byte và **loại bỏ**, tránh echo một gói bị cắt ở ngưỡng cho phép. |
| Poll timeout server | **300 ms** | Cho phép vòng lặp kiểm tra cờ dừng mà không bị chặn vô hạn. |
| Timeout client mặc định | **800 ms/lần thử**, tối đa **2 lần** | Demo xử lý mất phản hồi; tổng thời gian chờ nhận vào khoảng 1,6 s, cộng chi phí khác. |

**Vì sao cần giới hạn byte?** UTF-8 dùng số byte thay đổi cho từng ký tự. `"á".getBytes(UTF_8)` dài 2 byte, không phải 1. `String.length()` cũng không phản ánh kích thước UDP payload. Datagram quá lớn có nguy cơ bị phân mảnh ở tầng IP, giảm độ tin cậy; giới hạn 1.024 byte ở đây là **giới hạn ứng dụng cho demo**, không phải kích thước UDP tối đa cố định cho mọi mạng.

## 3. Những API Java phải nắm

| API | Vai trò | Lưu ý |
| --- | --- | --- |
| `new DatagramSocket(new InetSocketAddress(host, port))` | Bind server tại địa chỉ/cổng cụ thể. | Nếu cổng đã được dùng, có thể gặp `BindException`. Cổng `0` để OS tự chọn cổng rảnh, phù hợp smoke test. |
| `new DatagramSocket()` | Tạo client socket trên cổng tạm. | Socket cần đóng khi kết thúc. |
| `DatagramPacket` | Chứa buffer, `length`, địa chỉ và cổng. | Dùng `getLength()` thay cho `buffer.length` khi đọc datagram. |
| `socket.receive(packet)` | Chờ datagram đến. | Có thể block; nếu buffer nhỏ hơn datagram, dữ liệu bị cắt. |
| `socket.setSoTimeout(ms)` | Giới hạn **một lần chờ nhận**, tính bằng millisecond. | Khi hết hạn, ném `SocketTimeoutException` nhưng **socket vẫn dùng được**. Giá trị `0` nghĩa là chờ vô hạn. |
| `socket.send(packet)` | Gửi datagram. | Không tự retry, không xác nhận phía nhận. |
| `socket.connect(host, port)` | Ràng buộc endpoint UDP của client. | **Không** có handshake hay xác thực. |
| `socket.close()` | Giải phóng socket. | Luồng đang block ở `receive` sẽ thức dậy qua `SocketException`. |
| `try-with-resources` | Đảm bảo gọi `close()` khi rời phạm vi. | Dùng cả khi thành công lẫn khi xảy ra ngoại lệ. |
| `System.nanoTime()` | Tính deadline trôi qua tương đối. | Phù hợp timeout hơn `currentTimeMillis()`, vốn chịu thay đổi đồng hồ hệ thống. |

Không nên dùng `DatagramSocket.setSoTimeout` như một **send timeout**: nó áp dụng cho thao tác `receive`. Không coi `SocketTimeoutException` trên server là lỗi nghiêm trọng phải đóng toàn bộ socket; trong vòng lặp server đây chỉ là dấu hiệu **chưa có gói tin** trong 300 ms.

## 4. Server: `UdpEchoServer.java`

Tạo một tệp **`UdpEchoServer.java`** với mã đầy đủ sau:

```java
import java.io.IOException;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.SocketException;
import java.net.SocketTimeoutException;

public final class UdpEchoServer implements AutoCloseable {
    public static final int MAX_BYTES = 1024;
    private static final int RECEIVE_POLL_MS = 300;

    private final DatagramSocket socket;
    private volatile boolean running = true;

    public UdpEchoServer(InetAddress bindAddress, int port) throws SocketException {
        socket = new DatagramSocket(new InetSocketAddress(bindAddress, port));
        socket.setSoTimeout(RECEIVE_POLL_MS);
    }

    public int port() {
        return socket.getLocalPort();
    }

    public void serve() throws IOException {
        while (running) {
            byte[] buffer = new byte[MAX_BYTES + 1];
            DatagramPacket request = new DatagramPacket(buffer, buffer.length);
            try {
                socket.receive(request);
            } catch (SocketTimeoutException idle) {
                continue;
            } catch (SocketException closed) {
                if (!running) {
                    break;
                }
                throw closed;
            }

            if (request.getLength() > MAX_BYTES) {
                continue;
            }
            DatagramPacket reply = new DatagramPacket(
                    request.getData(), request.getOffset(), request.getLength(),
                    request.getAddress(), request.getPort());
            try {
                socket.send(reply);
            } catch (SocketException closed) {
                if (!running) {
                    break;
                }
                throw closed;
            }
        }
    }

    @Override
    public void close() {
        running = false;
        socket.close();
    }

    public static void main(String[] args) throws Exception {
        int port = args.length == 0 ? 7070 : Integer.parseInt(args[0]);
        InetAddress loopback = InetAddress.getByName("127.0.0.1");
        try (UdpEchoServer server = new UdpEchoServer(loopback, port)) {
            Runtime.getRuntime().addShutdownHook(
                    new Thread(server::close, "udp-echo-shutdown"));
            System.out.println("UDP echo listening on 127.0.0.1:" + server.port());
            server.serve();
        }
    }
}
```

**Giải thích dòng chảy:**

1. Constructor bind socket vào IP/cổng và đặt `SO_TIMEOUT=300`. Khi chạy riêng, server dùng `127.0.0.1:7070` hoặc cổng được nhập; khi test, truyền `0` để hệ điều hành cấp cổng tạm và lấy qua `port()`.
2. `serve()` đọc datagram trong vòng lặp. Mỗi lượt tạo **buffer mới** và `DatagramPacket` mới, nên `length` của gói trước không ảnh hưởng gói kế tiếp. Nếu tái sử dụng packet, phải đặt lại độ dài vùng đệm phù hợp trước lần nhận mới.
3. Gặp `SocketTimeoutException` khi rỗi, vòng lặp `continue` rồi kiểm tra lại `running`. Timeout **không tự đóng** socket.
4. Giới hạn `MAX_BYTES+1` cho phép phát hiện gói vượt ngưỡng ứng dụng; server bỏ gói đó, không echo một bản cắt ngắn. Các datagram lớn hơn buffer có thể bị cắt khi nhận, nên không suy đoán kích thước ban đầu chính xác.
5. Khi nhận payload hợp lệ, dựng packet trả lời từ **chính các byte nhận được**, đúng `request.getOffset()`, `request.getLength()`, `request.getAddress()` và `request.getPort()`. Cổng phải là cổng **nguồn của client**, không phải cổng cố định `7070`.
6. `close()` đặt `running=false` (cờ `volatile` được thấy giữa các thread) rồi đóng socket. Vì `close()` làm `receive()` ném `SocketException`, server chỉ thoát vòng lặp khi chính nó đang được yêu cầu dừng; lỗi socket khác vẫn được báo cho caller.
7. `main` sử dụng `try-with-resources` và shutdown hook để hỗ trợ dừng bằng Ctrl+C trong môi trường dòng lệnh. Trong ứng dụng nhúng, lifecycle manager cần gọi `close()` khi dừng service. `close()` có thể gọi lặp mà không cần mở socket mới.

**Quản lý tài nguyên đúng:** chỉ một `DatagramSocket` tồn tại trong suốt vòng đời server. Không mở một socket mới cho từng datagram, không để ngoại lệ từ `send`/`receive` làm rò tài nguyên, không nuốt lỗi socket thật như một “timeout bình thường”.

## 5. Client: `UdpEchoClient.java`

Tạo tệp **`UdpEchoClient.java`**:

```java
import java.io.IOException;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

public final class UdpEchoClient {
    public static String exchange(
            InetAddress host, int port, String message, int timeoutMs, int attempts)
            throws IOException {
        if (message == null || timeoutMs <= 0 || attempts <= 0) {
            throw new IllegalArgumentException("Invalid request or timeout settings");
        }

        String requestId = UUID.randomUUID().toString();
        byte[] sent = (requestId + "|" + message).getBytes(StandardCharsets.UTF_8);
        if (sent.length > UdpEchoServer.MAX_BYTES) {
            throw new IllegalArgumentException("UDP payload exceeds demo limit");
        }

        try (DatagramSocket socket = new DatagramSocket()) {
            socket.connect(host, port);
            DatagramPacket request = new DatagramPacket(sent, sent.length, host, port);

            for (int attempt = 1; attempt <= attempts; attempt++) {
                socket.send(request);
                long deadline = System.nanoTime()
                        + TimeUnit.MILLISECONDS.toNanos(timeoutMs);

                while (true) {
                    long remainingNs = deadline - System.nanoTime();
                    if (remainingNs <= 0) {
                        break;
                    }
                    int waitMs = (int) Math.max(1,
                            TimeUnit.NANOSECONDS.toMillis(remainingNs));
                    socket.setSoTimeout(waitMs);
                    byte[] buffer = new byte[UdpEchoServer.MAX_BYTES + 1];
                    DatagramPacket response = new DatagramPacket(buffer, buffer.length);
                    try {
                        socket.receive(response);
                    } catch (SocketTimeoutException timeout) {
                        break;
                    }
                    byte[] received = Arrays.copyOfRange(
                            response.getData(),
                            response.getOffset(),
                            response.getOffset() + response.getLength());
                    if (Arrays.equals(sent, received)) {
                        return message;
                    }
                    // An unmatched or stale response does not extend the deadline.
                }
            }
            throw new SocketTimeoutException(
                    "No matching UDP echo after " + attempts + " attempt(s)");
        }
    }

    public static void main(String[] args) throws Exception {
        int port = args.length == 0 ? 7070 : Integer.parseInt(args[0]);
        String message = args.length < 2
                ? "xin chào UDP"
                : String.join(" ", Arrays.copyOfRange(args, 1, args.length));
        String echoed = exchange(
                InetAddress.getByName("127.0.0.1"), port,
                message, 800, 2);
        System.out.println("Echo: " + echoed);
    }
}
```

**Các điểm thiết kế đáng chú ý:**

- `UUID.randomUUID() + "|" + message` tạo payload có request ID riêng cho **mỗi lời gọi**. Trong cùng một lời gọi, các lần gửi lại dùng **cùng request ID**, vì đó là retry của cùng yêu cầu. Đây là giao thức echo rất đơn giản, có thể gửi lại an toàn vì không tạo tác dụng phụ ở server.
- `getBytes(StandardCharsets.UTF_8)` chuyển dữ liệu thành byte trước khi kiểm tra kích thước; 1.024 byte bao gồm cả request ID, dấu phân cách và nội dung. Nếu vượt ngưỡng, ném `IllegalArgumentException` **trước khi tạo socket/gửi**.
- `socket.connect(host, port)` giới hạn endpoint nhận phản hồi theo API UDP; đây **không phải** xác thực người gửi và không biến UDP thành kết nối tin cậy. Phản hồi còn được so sánh **từng byte** với request đang chờ bằng `Arrays.equals`.
- Mỗi lần thử có deadline riêng dựa trên `System.nanoTime()`. Nếu nhận một datagram cũ hoặc không khớp, client bỏ qua nhưng **không gia hạn deadline**. Chỉ dùng `setSoTimeout(800)` lặp lại sau mọi phản hồi sai có thể khiến client chờ quá lâu.
- Hết deadline của một attempt thì gửi lại tối đa số lần cho phép. Sau attempt cuối, client ném `SocketTimeoutException`; caller quyết định thông báo, ghi log hoặc xử lý nghiệp vụ. **Không retry vô hạn.**
- Socket nằm trong `try-with-resources`, nên khi trả về thành công, timeout hoặc xảy ra `IOException` vẫn được đóng. `setSoTimeout` không tự làm việc này.
- Một UDP endpoint không tồn tại có thể dẫn đến `PortUnreachableException` trên một số hệ điều hành/JDK khi socket đã `connect` và nhận ICMP unreachable; **không bảo đảm** lỗi này luôn xuất hiện. Không viết test phụ thuộc vào việc luôn nhận `SocketTimeoutException` nếu không có server ở cổng ấy.

**Lưu ý ứng dụng thực tế:** Retry có thể gửi trùng yêu cầu. Với thao tác **không idempotent** như thanh toán hoặc ghi dữ liệu, phải có cơ chế định danh request và deduplication ở server, không sao chép retry logic của echo service mà không thiết kế ngữ nghĩa nghiệp vụ.

## 6. Biên dịch và chạy với hai terminal

Yêu cầu JDK 17+ (ví dụ JDK 17, 21, 25) và môi trường dòng lệnh có `javac`/`java`. Đặt ba tệp `.java` của bài trong cùng thư mục, không dùng `package`.

Tại thư mục đó, biên dịch:

```bash
javac --release 17 -encoding UTF-8 UdpEchoServer.java UdpEchoClient.java UdpEchoSmokeTest.java
```

**Terminal A — chạy server:**

```bash
java UdpEchoServer 7070
```

Khi bind thành công, server in:

```text
UDP echo listening on 127.0.0.1:7070
```

Terminal A tiếp tục giữ tiến trình server và chờ datagram; không có dòng log khi không có request. Để dừng, dùng Ctrl+C.

**Terminal B — gửi echo request:**

```bash
java UdpEchoClient 7070 "xin chào UDP"
```

Nếu server đang chạy và phản hồi đến đúng hạn, client in chính xác:

```text
Echo: xin chào UDP
```

Có thể thay cổng `7070` bằng cổng khác ở **cả hai lệnh**; ví dụ `java UdpEchoServer 7071` và `java UdpEchoClient 7071 "hello"`. Không cần mở port trên firewall cho thử nghiệm loopback. Nếu có firewall/chính sách máy cục bộ đặc biệt, kết quả vẫn tùy môi trường.

**Điều gì xảy ra khi không có phản hồi?** Client sẽ thử tối đa 2 lần, mỗi lần chờ tối đa 800 ms, sau đó ném `SocketTimeoutException` với thông báo do ví dụ tạo. Một số hệ điều hành có thể trả lỗi unreachable sớm hơn. Để kiểm chứng timeout **ổn định** trong test tự động, dùng socket “im lặng” đã bind cổng nhưng không gửi trả lời như phần dưới.

## 7. Kiểm thử tự động: `UdpEchoSmokeTest.java`

Tạo tệp **`UdpEchoSmokeTest.java`**:

```java
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.SocketTimeoutException;
import java.util.concurrent.atomic.AtomicReference;

public final class UdpEchoSmokeTest {
    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getByName("127.0.0.1");
        try (UdpEchoServer server = new UdpEchoServer(loopback, 0)) {
            AtomicReference<Throwable> serverFailure = new AtomicReference<>();
            Thread worker = new Thread(() -> {
                try {
                    server.serve();
                } catch (Throwable error) {
                    serverFailure.set(error);
                }
            }, "udp-test-server");
            worker.start();

            try {
                String first = UdpEchoClient.exchange(
                        loopback, server.port(), "xin chào UDP", 800, 2);
                if (!first.equals("xin chào UDP")) {
                    throw new AssertionError("Echo content mismatch");
                }
                System.out.println("Echo UTF-8: PASS");

                Thread.sleep(700);
                String second = UdpEchoClient.exchange(
                        loopback, server.port(), "after idle", 800, 2);
                if (!second.equals("after idle")) {
                    throw new AssertionError("Server stopped after idle timeout");
                }
                System.out.println("Server after idle timeout: PASS");

                try (DatagramSocket silent = new DatagramSocket(
                        new InetSocketAddress(loopback, 0))) {
                    try {
                        UdpEchoClient.exchange(loopback, silent.getLocalPort(),
                                "no response", 150, 1);
                        throw new AssertionError("Expected a client timeout");
                    } catch (SocketTimeoutException expected) {
                        System.out.println("Client timeout: PASS");
                    }
                }

                try {
                    UdpEchoClient.exchange(loopback, server.port(),
                            "á".repeat(1024), 200, 1);
                    throw new AssertionError("Oversized UTF-8 payload was accepted");
                } catch (IllegalArgumentException expected) {
                    System.out.println("UTF-8 byte limit: PASS");
                }
            } finally {
                server.close();
                worker.join(2_000);
            }

            if (worker.isAlive()) {
                throw new AssertionError("Server thread failed to stop");
            }
            if (serverFailure.get() != null) {
                throw new AssertionError("Server thread failed", serverFailure.get());
            }
            System.out.println("Clean shutdown: PASS");
        }
    }
}
```

Chạy sau khi biên dịch:

```bash
java UdpEchoSmokeTest
```

Đầu ra từ chính bộ kiểm thử khi các điều kiện được đáp ứng:

```text
Echo UTF-8: PASS
Server after idle timeout: PASS
Client timeout: PASS
UTF-8 byte limit: PASS
Clean shutdown: PASS
```

**Bộ kiểm thử xác minh điều gì?**

1. **Echo UTF-8:** client gửi chuỗi `xin chào UDP` có ký tự tiếng Việt. Test chỉ PASS khi nhận được phản hồi tương ứng chính xác.
2. **Server sau idle timeout:** `Thread.sleep(700)` dài hơn hai chu kỳ poll `300 ms`. Sau thời gian rỗi, cùng server vẫn trả lời `after idle`, chứng minh timeout nhận **không làm hỏng hoặc đóng service**.
3. **Client timeout:** test tạo một `DatagramSocket` trên cổng tạm và **không đọc/gửi trả lời**. Client gửi đến cổng có socket đang bind nhưng không có phản hồi, chờ 150 ms/lần với 1 attempt; `SocketTimeoutException` là kết quả mong đợi.
4. **Giới hạn byte UTF-8:** `"á".repeat(1024)` có nhiều byte hơn 1.024; client phải ném `IllegalArgumentException` trước khi gửi.
5. **Clean shutdown:** `server.close()` đánh thức server thread; `join(2_000)` yêu cầu thread dừng trong giới hạn; `AtomicReference<Throwable>` chuyển lỗi ở thread server về test main để **không có false PASS**.

Test dùng `port=0` để OS tự cấp cổng trống, giúp tránh xung đột cổng `7070` và cho phép chạy đồng thời với server thủ công. `SocketTimeoutException` do client xử lý như case âm đã kiểm soát; lỗi bind, xử lý datagram hoặc tắt server **không** được coi là PASS.

**Tính chất của smoke test:** thử nghiệm giao tiếp thật giữa hai UDP socket **trên cùng máy**. Đây là kiểm thử tích hợp tối thiểu, không chứng minh truyền thông qua NAT/firewall, sức chịu tải, bảo mật hay tính tin cậy trên mạng có mất gói. Chạy thêm thử nghiệm trên môi trường triển khai nếu service cần nhận từ máy khác.

## 8. Xử lý timeout, retry và vòng đời tài nguyên

### Phân biệt timeout phía server và client

| Khía cạnh | Server | Client |
| --- | --- | --- |
| Chờ `receive` | 300 ms rồi kiểm tra lại cờ dừng. | Chờ đến deadline còn lại của mỗi attempt. |
| Khi `SocketTimeoutException` | Bình thường khi rỗi; tiếp tục vòng lặp. | Kết thúc thời gian chờ của attempt, có thể retry. |
| Khi kết thúc | `close()` đặt cờ dừng và đóng socket. | Trả kết quả hoặc ném lỗi, `try-with-resources` đóng socket. |
| Có tự retry không? | Không; chỉ echo datagram thực sự nhận. | Có giới hạn 2 attempt trong CLI demo. |
| Có cam kết delivery không? | Không. | Không; timeout nghĩa là **chưa có phản hồi phù hợp**, không khẳng định server chắc chắn chưa nhận request. |

### Vì sao dùng deadline bằng `System.nanoTime()`?

Nếu chỉ đặt `socket.setSoTimeout(800)` rồi nhận liên tiếp các datagram sai, mỗi lần gọi `receive` lại có thể chờ thêm 800 ms. Một peer nhiều traffic có thể khiến thời gian chờ thực tế vượt ngân sách. Ví dụ này giữ **deadline cố định theo attempt** và tính lại `setSoTimeout(remainingMs)` trước mỗi lần nhận. `nanoTime` được dùng cho khoảng thời gian tương đối; không phụ thuộc việc đồng hồ hệ thống bị chỉnh.

### Khi đóng socket có nên bắt mọi `SocketException` và bỏ qua?

**Không.** Ví dụ server chỉ coi `SocketException` là dừng bình thường khi `running=false` do `close()` yêu cầu. Trong các trường hợp khác, exception được ném ra ngoài để caller thấy lỗi thật. Nếu nuốt mọi lỗi như “server stop” thì mất khả năng phát hiện lỗi mạng, permission hoặc bug.

### Khi nào nên dùng `DatagramChannel`?

`DatagramSocket` phù hợp cho demo/small service với một luồng xử lý và `SO_TIMEOUT`. Khi cần **non-blocking IO**, selector, tích hợp với event loop hoặc throughput nhiều socket, có thể thiết kế trên `java.nio.channels.DatagramChannel`. Cả hai API đều còn được hỗ trợ; bài này chọn `DatagramSocket` vì dễ quan sát timeout và lifecycle.

## 9. Lỗi phổ biến khi làm UDP echo service

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra/sửa |
| --- | --- | --- |
| `BindException: Address already in use` | Cổng server đã bị tiến trình khác chiếm | Đổi cổng cho cả server/client; khi test tự động dùng `port=0`. |
| Client timeout dù server còn chạy | Sai IP/port, firewall, packet loss, server drop oversize, reply không khớp ID | Kiểm tra IP/port, packet size, log số datagram, thử loopback, dùng packet capture khi cần. |
| `PortUnreachableException` | ICMP báo endpoint không thể tới; hành vi tùy OS/JVM | Phân loại như sự cố mạng/endpoint, đừng giả định luôn xảy ra. |
| Echo ra chuỗi có dấu rác hoặc byte 0 | Decode toàn bộ buffer, bỏ qua `getLength()` | Chỉ lấy `offset` và `length` của datagram. |
| Client gửi tin nhắn Unicode quá dài | `String.length()` khác số byte UTF-8 | Tính kích thước sau `getBytes(StandardCharsets.UTF_8)`. |
| Server chỉ nhận packet đầu tiên đúng | Tái sử dụng `DatagramPacket` mà không reset độ dài | Tạo packet mới hoặc reset `setLength(...)` trước `receive`. |
| Server tự thoát khi rỗi | Coi `SocketTimeoutException` là lỗi dừng | Timeout ở server demo chỉ là lần kiểm tra cờ dừng. |
| Server không dừng được vì kẹt `receive` | Không đặt timeout, không gọi `close()` từ lifecycle | Đặt timeout poll hoặc đóng socket để đánh thức thread chờ. |
| Test luôn PASS dù server lỗi | Exception bị nuốt trong thread phụ | Chuyển lỗi về test main; xác minh `join`/thread dừng. |
| Retry sinh tác dụng phụ lặp | UDP có thể giao hàng trùng; retry gửi lại request | Với nghiệp vụ thật cần idempotency key/deduplication. |
| Tưởng `connect` xác thực người gửi | UDP không cung cấp authentication/handshake | Thiết kế xác thực ứng dụng hoặc giao thức bảo vệ phù hợp. |

## 10. Nâng cấp khi đem vào ứng dụng thực

Bài demo cố ý chỉ mở loopback và echo tối đa 1.024 byte. Nếu đưa ra mạng thật, tối thiểu cần xem xét:

- **Địa chỉ bind và phạm vi truy cập:** không thay bằng `0.0.0.0` tùy tiện. Quyết định interface được phép nghe, firewall, access control và logging; UDP echo public có thể bị lạm dụng với IP spoofing.
- **Giới hạn tải:** chống spam/rate limit, theo dõi datagram nhận/gửi/bỏ vì quá cỡ, metric lỗi và timeout; tăng buffer/worker theo đo đạc. UDP echo gửi phản hồi tới địa chỉ nguồn có thể bị giả mạo, vì vậy cần kiểm soát truy cập và mức sử dụng.
- **Giao thức rõ ràng:** mã hóa version, request ID, kiểu message, checksum/xác thực ở tầng ứng dụng nếu cần; không dùng phép ghép chuỗi tạm thời làm format production nếu có yêu cầu mở rộng, ký hoặc bảo mật.
- **Kích thước/MTU:** chọn payload đủ nhỏ theo path MTU, tránh IP fragmentation; giá trị 1.024 byte trong demo là giới hạn chủ đích, **không phải bảo đảm** datagram sẽ không bị phân mảnh trên mọi đường truyền.
- **Độ tin cậy:** UDP có thể mất, trễ, lặp và đảo thứ tự. Retry kèm deadline/backoff, request ID và xử lý duplicate phải phù hợp với hành vi nghiệp vụ. Timeout không chứng minh request chưa được server thực hiện.
- **Bảo mật:** `socket.connect` và UUID **không** chứng minh tính toàn vẹn, danh tính hay bí mật. Khi cần, dùng giao thức bảo mật phù hợp (ví dụ DTLS hoặc cơ chế xác thực tại tầng ứng dụng), kiểm tra cả replay và quyền thực hiện.
- **Vòng đời:** lifecycle manager gọi `close()` khi shutdown; không để luồng nhận tiếp tục hoạt động sau khi service đóng; ghi nhận và xử lý riêng lỗi khởi tạo, timeout và lỗi khi phục vụ.

## 11. Bài tập mở rộng

1. Thay `"xin chào UDP"` bằng thông điệp có emoji, dấu tiếng Việt và chuỗi dài; xác nhận giới hạn theo **byte UTF-8** và echo đầy đủ.
2. Đổi `RECEIVE_POLL_MS` thành 100 ms và đo thời gian thread server dừng; so sánh với việc gọi `close()` để đánh thức `receive` trực tiếp.
3. Đặt `attempts=1` rồi `attempts=3` với “silent socket”, đo deadline của từng lần thử và xác nhận không có vòng retry vô hạn.
4. Sửa test để gửi một datagram dài hơn `MAX_BYTES` **bỏ qua client validator**; quan sát server drop thay vì echo dữ liệu bị cắt.
5. Thêm thống kê số request nhận/echo/bỏ quá cỡ bằng counter an toàn theo mô hình thread được lựa chọn. Viết thêm test rằng chỉ datagram hợp lệ mới làm tăng số echo.
6. Bổ sung test gửi **phản hồi sai ID** trước phản hồi đúng. Client phải bỏ qua gói sai nhưng không gia hạn deadline của attempt.

**Tiêu chí hoàn thành:** Có thể chạy server/client độc lập, hiểu chính xác tác dụng của `SO_TIMEOUT`, chứng minh timeout và retry có giới hạn, giữ đúng ranh giới datagram/UTF-8, xử lý lỗi và dừng socket sạch, và biết đâu là giới hạn bảo mật/độ tin cậy của UDP.

## Nguồn kỹ thuật chính thức

- [Java SE DatagramSocket API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/DatagramSocket.html): `send`, `receive`, `connect`, `setSoTimeout`, `close` và exception.
- [Java SE DatagramPacket API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/DatagramPacket.html): datagram buffer, offset, length, source address/port.
- [Java SE SocketTimeoutException API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/SocketTimeoutException.html): nhận diện timeout trên thao tác socket.
- [RFC 768 — User Datagram Protocol](https://www.rfc-editor.org/rfc/rfc768): UDP không bảo đảm delivery hay chống duplicate.
- [RFC 8085 — UDP Usage Guidelines](https://www.rfc-editor.org/rfc/rfc8085): hướng dẫn về datagram size, timeout, reliability, congestion và triển khai UDP an toàn.

Các API trên vẫn còn được hỗ trợ trong Java SE hiện hành. Khi triển khai thực tế, kiểm tra lại hành vi trên bản JDK, hệ điều hành và đường truyền mục tiêu.
