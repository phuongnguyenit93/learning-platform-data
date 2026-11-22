# Chế độ blocking và non-blocking trong Java NIO mạng

## 1. Blocking và non-blocking trả lời câu hỏi gì?

Trong lập trình mạng, thao tác như chờ kết nối, chấp nhận kết nối, nhận byte hay gửi byte có thể cần thời gian do phụ thuộc vào hệ điều hành, trạng thái socket, peer và tốc độ mạng.

**Blocking** và **non-blocking** mô tả cách một lời gọi I/O ứng xử khi điều kiện để thực hiện thao tác chưa sẵn sàng:

- **Blocking I/O**: lời gọi có thể giữ luồng đang gọi ở trạng thái chờ cho đến khi thao tác có thể tiến triển, kết thúc, gặp EOF hoặc lỗi. Đây **không có nghĩa** lúc nào cũng chờ, hoặc một lời gọi luôn truyền đủ mọi byte.
- **Non-blocking I/O**: lời gọi không chờ vô hạn chỉ để đợi điều kiện I/O trở nên sẵn sàng; nó có thể trả về ngay mà **chưa chuyển byte nào**. Ứng dụng phải quyết định khi nào thử lại, thường phối hợp `Selector` để nhận thông báo mức độ sẵn sàng (*readiness*).

Ví dụ server gọi `ServerSocketChannel.accept()` khi chưa có client:

| Chế độ của server channel | Điều có thể xảy ra |
| --- | --- |
| Blocking (mặc định) | `accept()` chờ tới khi có kết nối hoặc một tình huống kết thúc/lỗi |
| Non-blocking | `accept()` trả về ngay **`null`** nếu hiện chưa có kết nối chờ được chấp nhận |

Khác với `accept()`, một số lệnh `read()` non-blocking dùng **`0`** để báo chưa nhận byte. Không được đánh đồng `null`, `0` và `-1` — mỗi API có hợp đồng riêng.

Java NIO cung cấp cả hai mô hình để phù hợp với số lượng kết nối, mô hình thực thi, khả năng mở rộng và tính đơn giản của ứng dụng.

## 2. Các lớp liên quan trong NIO mạng

| Kiểu Java | Vai trò | Liên hệ blocking/non-blocking |
| --- | --- | --- |
| `ServerSocketChannel` | Lắng nghe và chấp nhận kết nối TCP | `accept()` blocking hoặc non-blocking |
| `SocketChannel` | Kết nối TCP; đọc/ghi qua `ByteBuffer` | `connect()`, `finishConnect()`, `read()`, `write()` |
| `DatagramChannel` | Gửi/nhận datagram, thường dùng UDP | `receive()` có thể trả `null` nếu non-blocking chưa có datagram |
| `SelectableChannel` | Interface chung cho các channel có thể đăng ký selector | `configureBlocking(boolean)` và `isBlocking()` |
| `Selector` | Theo dõi các channel đã đăng ký và các sự kiện readiness | `select()`, `select(timeout)`, `selectNow()` |
| `SelectionKey` | Đại diện một lần đăng ký channel với selector | `OP_ACCEPT`, `OP_CONNECT`, `OP_READ`, `OP_WRITE` |

**`FileChannel` không phải `SelectableChannel`** và không thể chuyển thành non-blocking kiểu socket bằng `configureBlocking(false)` hoặc đăng ký vào `Selector`. Đây là điểm khác biệt giữa **Java NIO dùng buffer/channel** nói chung với **I/O mạng không chặn dùng selector**.

Một channel mới thuộc nhóm `SelectableChannel` được tạo ở **blocking mode** theo hợp đồng API, trừ khi mã của bạn chủ động chuyển sang non-blocking.

## 3. Chuyển chế độ qua `configureBlocking`

`SelectableChannel` có:

```java
SelectableChannel configureBlocking(boolean block) throws IOException;
boolean isBlocking();
```

- `configureBlocking(true)`: yêu cầu chế độ blocking.
- `configureBlocking(false)`: yêu cầu chế độ non-blocking.
- `isBlocking()`: kiểm tra chế độ hiện tại (đối với channel đang mở).

Ví dụ:

```java
ServerSocketChannel server = ServerSocketChannel.open();
System.out.println(server.isBlocking()); // true
server.configureBlocking(false);
System.out.println(server.isBlocking()); // false
```

Đây là đoạn mã minh họa và cần quản lý đóng channel. `configureBlocking` là **cấu hình của đối tượng channel**, không phải thay đổi toàn bộ JVM hay tất cả socket cùng một lúc.

Có ràng buộc quan trọng: **một channel được đăng ký với bất kỳ selector nào không thể chuyển về blocking mode ngay khi nó còn ở trạng thái đăng ký**. Cố `configureBlocking(true)` trong tình huống đó ném `IllegalBlockingModeException`. Khi `SelectionKey.cancel()`, việc hủy đăng ký có thể chỉ được xử lý trong chu kỳ lựa chọn tiếp theo; không nên hủy key rồi lập tức giả định có thể chuyển sang blocking mà không đồng bộ vòng đời.

Ngoài ra, **muốn đăng ký `Selector`, channel phải đang ở non-blocking mode**. Đăng ký khi còn blocking sẽ ném `IllegalBlockingModeException`. Không có nghĩa mọi non-blocking channel bắt buộc phải đăng ký selector: có thể thăm dò bằng lời gọi trực tiếp, nhưng thăm dò lặp vô điều kiện dễ tạo busy loop.

## 4. Hành vi của `accept`, `connect`, `read` và `write`

### 4.1. `ServerSocketChannel.accept()`

- Blocking: có thể chờ một kết nối mới.
- Non-blocking: trả về `SocketChannel` khi có kết nối chờ; nếu chưa có, trả về **`null`**.

Hệ quả: luôn kiểm tra kết quả `accept()` trước khi gọi phương thức của accepted channel.

### 4.2. `SocketChannel.connect(remote)`

- Blocking: thường chỉ trả về sau khi thiết lập kết nối hoàn tất hoặc phát sinh lỗi; `connect` trả `true` nếu đã kết nối thành công.
- Non-blocking: có thể trả về **`false`** vì quá trình kết nối chưa hoàn tất. Khi channel có tín hiệu `OP_CONNECT`, gọi `finishConnect()` để hoàn thành bắt tay; nếu `finishConnect()` vẫn trả false, tiếp tục chờ phù hợp.
- `OP_CONNECT` báo trạng thái sẵn sàng hoàn tất, **không bảo đảm** việc kết nối sẽ thành công: lỗi kết nối có thể xuất hiện qua `finishConnect()`.

Không đọc/ghi ứng dụng như thể socket chắc chắn đã kết nối chỉ vì `connect()` non-blocking trả false. Phải xử lý trạng thái kết nối đang chờ.

### 4.3. `SocketChannel.read(dst)`

Giả sử `dst` có chỗ trống, không chỉ đọc, và socket đã kết nối:

| Kết quả | Ý nghĩa |
| --- | --- |
| `n > 0` | Đã nhận `n` byte; `dst.position()` tăng `n` |
| `n == 0` | Chưa nhận byte nào trong lời gọi hiện tại; thường gặp với non-blocking khi chưa sẵn sàng |
| `n == -1` | Đầu bên kia đã kết thúc chiều gửi hoặc tới EOF |

**`0` không phải EOF**. Cũng không được giả định `read` luôn nhận đủ `dst.remaining()`. TCP là **byte stream** chứ không bảo toàn ranh giới thông điệp: một gói logic có thể đến trong nhiều lần `read`, và một lần `read` có thể chứa dữ liệu của nhiều thông điệp ứng dụng.

Nếu buffer đã đầy (`dst.remaining() == 0`), trước hết phải xử lý dữ liệu rồi `clear()` hoặc `compact()` theo chu kỳ hiện tại, thay vì diễn giải việc không nhận thêm dữ liệu thành “đầu bên kia đã đóng”.

### 4.4. `SocketChannel.write(src)`

- Trả về số byte thực tế đã gửi từ vùng `[src.position(), src.limit())`.
- Có thể chỉ ghi **một phần** dữ liệu, ngay cả khi blocking mode; mã đúng vẫn phải xử lý lượng còn lại theo hợp đồng.
- Ở non-blocking mode, có thể trả `0` nếu hiện chưa thể ghi thêm.
- `write` không dùng `-1` để báo EOF; tình trạng kết nối bị đóng/lỗi sẽ cần xử lý qua ngoại lệ và trạng thái channel.

Một lời gọi `write()` thành công có nghĩa dữ liệu đã được chấp nhận vào đường truyền theo hợp đồng I/O, **không bảo đảm ứng dụng phía peer đã đọc hoặc xử lý dữ liệu**.

## 5. Blocking không đồng nghĩa đồng bộ hóa toàn bộ chương trình

Hình dung một luồng phục vụ một client bằng các bước:

```text
accept() --chờ kết nối--> read() --chờ byte--> xử lý
                                      |
                                      v
                                  write()
```

Nếu các lời gọi I/O blocking, **luồng thực hiện lời gọi** có thể chờ. Các luồng khác trong cùng JVM vẫn có thể chạy. Vì vậy “blocking I/O” không đồng nghĩa “toàn bộ ứng dụng bị đứng”, và “non-blocking I/O” cũng không tự đồng nghĩa “xử lý song song”.

Blocking thường phù hợp với:
- Ứng dụng đơn giản, ít kết nối đồng thời.
- Luồng riêng cho từng kết nối khi tài nguyên và chiến lược thực thi cho phép.
- Mã nghiệp vụ cần luồng điều khiển tuyến tính, dễ đọc và dễ gỡ lỗi.

Những đánh đổi thường gặp:
- Nếu số kết nối lớn và nhiều client không gửi dữ liệu trong thời gian dài, thiết kế một thread nền tảng cho mỗi client có thể tốn tài nguyên.
- Cần kiểm soát timeout, hủy tác vụ, backpressure và đóng socket.
- Một thao tác có thể chờ lâu nếu không có tiến độ và không thiết kế cách kết thúc.

**Non-blocking** giúp một số lượng nhỏ luồng điều phối nhiều kết nối, nhưng chuyển sự phức tạp sang quản lý trạng thái của từng kết nối, selector, buffer và các tình huống read/write một phần. Không mặc định chuyển sang non-blocking là tăng tốc tất cả trường hợp.

## 6. Ví dụ Java 17+ chạy độc lập: TCP blocking

Ví dụ này chạy một server và một client trên loopback trong cùng JVM. Server dùng `ServerSocketChannel.accept()` ở blocking mode, client gửi đúng bốn byte ASCII `PING`; server đọc đủ bốn byte rồi kết thúc. Để không phụ thuộc thứ tự log giữa hai luồng, **chỉ luồng chính in kết quả sau khi tác vụ server hoàn tất**.

**Tệp `BlockingTcpDemo.java`:**

```java
import java.io.EOFException;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class BlockingTcpDemo {
    public static void main(String[] args) throws Exception {
        try (ServerSocketChannel server = ServerSocketChannel.open()) {
            server.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 0));

            ExecutorService pool = Executors.newSingleThreadExecutor();
            try {
                Future<String> response = pool.submit(() -> {
                    try (SocketChannel accepted = server.accept()) {
                        ByteBuffer bytes = ByteBuffer.allocate(4);
                        while (bytes.hasRemaining()) {
                            int n = accepted.read(bytes);
                            if (n == -1) {
                                throw new EOFException("Client closed early");
                            }
                        }

                        bytes.flip();
                        return StandardCharsets.US_ASCII
                                .decode(bytes).toString();
                    }
                });

                try (SocketChannel client = SocketChannel.open()) {
                    client.connect(server.getLocalAddress());
                    ByteBuffer outgoing = ByteBuffer.wrap(
                            "PING".getBytes(StandardCharsets.US_ASCII));

                    while (outgoing.hasRemaining()) {
                        client.write(outgoing);
                    }
                }

                String received = response.get(5, TimeUnit.SECONDS);
                System.out.println("Blocking server: "
                        + server.isBlocking());
                System.out.println("Noi dung nhan: " + received);
            } finally {
                server.close();
                pool.shutdownNow();
            }
        }
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac BlockingTcpDemo.java
java BlockingTcpDemo
```

**Stdout khi kết nối loopback và I/O thành công:**

```text
Blocking server: true
Noi dung nhan: PING
```

**Giải thích:**

1. `bind(..., 0)` để hệ điều hành cấp một cổng TCP trống; không cần cố định số cổng và không in số cổng vì nó thay đổi theo từng lần chạy.
2. Server giữ chế độ blocking mặc định. Tác vụ trong pool chờ ở `accept()` cho đến khi client kết nối.
3. Client dùng `SocketChannel.open()` và `connect(...)` ở blocking mode mặc định, sau đó ghi đủ bốn byte với vòng lặp `hasRemaining()`.
4. Server tiếp tục gọi `read(bytes)` cho đến khi nhận đủ bốn byte hoặc gặp EOF. Không giả định một `read` đủ bốn byte.
5. `Future.get` giúp luồng chính chỉ in kết quả sau khi server đọc xong. Timeout 5 giây là giới hạn chờ của `get`, không phải timeout tự động cho từng thao tác socket; demo được thiết kế cho môi trường loopback hoạt động bình thường.

Nếu muốn xây server thực tế, cần cơ chế dừng, timeout, giới hạn kết nối, quản lý luồng và bảo vệ tài nguyên. Ví dụ chỉ chứng minh hành vi blocking và cách đọc TCP đầy đủ một thông điệp có độ dài đã biết.

## 7. Non-blocking: thử I/O khi có thể tiến triển

Đối với `ServerSocketChannel` hay `SocketChannel`:

```java
channel.configureBlocking(false);
```

Khi chuyển sang non-blocking, mã phải chuẩn bị xử lý:
- `accept() == null` nếu chưa có kết nối chờ.
- `connect() == false` nếu đang kết nối.
- `read() == 0` khi chưa nhận được byte.
- `write() == 0` khi chưa chuyển được byte.
- `read() == -1` khi gặp EOF (khác hoàn toàn với 0).

Một cách sai thường gặp:

```java
while (channel.read(buffer) == 0) {
    // Không làm gì.
}
```

Vòng lặp này có thể liên tục chiếm CPU khi chưa có dữ liệu. Cũng không có cơ sở bảo đảm một lần đọc sau đó sẽ nhận đủ cả thông điệp.

**Thực hành tốt:** Đăng ký channel non-blocking với `Selector` và xử lý khi có sự kiện `OP_ACCEPT`/`OP_CONNECT`/`OP_READ`/`OP_WRITE` phù hợp. Khi một lệnh non-blocking không tiến triển, hãy trả quyền điều khiển cho event loop, giữ trạng thái chưa hoàn tất và đợi thông báo tiếp theo.

## 8. `Selector`: chờ readiness cho nhiều channel

`Selector` là cơ chế multiplexing các channel selectable:

```text
Socket A (non-blocking) ---\
Socket B (non-blocking) ----> Selector ---> một event loop
ServerSocketChannel -------/
                            |
                            +-- accept khi sẵn sàng
                            +-- finishConnect khi kết nối sẵn sàng
                            +-- read khi sẵn sàng đọc
                            +-- write khi sẵn sàng ghi
```

Quy trình tổng quát:

1. Mở `Selector`.
2. Chuyển mỗi channel cần theo dõi sang `configureBlocking(false)`.
3. Đăng ký qua `channel.register(selector, interestOps)` để nhận `SelectionKey`.
4. Gọi `selector.select()` hoặc `select(timeout)` để chờ ít nhất một channel phù hợp có readiness, hoặc trở về theo timeout/wakeup.
5. Duyệt `selector.selectedKeys()`, xử lý các key còn hợp lệ, và **xóa key khỏi tập selectedKeys sau khi xử lý**.
6. Thay đổi `interestOps` theo trạng thái thực, tiếp tục vòng event loop đến khi ứng dụng có điều kiện dừng.

**Readiness không có nghĩa chắc chắn chuyển được một lượng byte định trước.** Giữa sự kiện selector và thao tác I/O, điều kiện có thể thay đổi. Non-blocking `read`/`write` vẫn có thể trả 0 và buộc ứng dụng giữ trạng thái để chờ lần sau.

Các bit sự kiện thông dụng:

| Bit | Thường dùng với | Khi nào quan tâm |
| --- | --- | --- |
| `SelectionKey.OP_ACCEPT` | `ServerSocketChannel` | Có kết nối chờ được chấp nhận |
| `SelectionKey.OP_CONNECT` | `SocketChannel` đang connect non-blocking | Có thể gọi `finishConnect()` |
| `SelectionKey.OP_READ` | `SocketChannel` đã kết nối | Có thể đọc byte, xử lý EOF/lỗi hoặc nhận dữ liệu |
| `SelectionKey.OP_WRITE` | `SocketChannel` có dữ liệu chờ gửi | Có thể thử ghi phần còn lại |

Không phải bit nào cũng hợp lệ cho mọi channel. `ServerSocketChannel.validOps()` hỗ trợ `OP_ACCEPT`; `SocketChannel` hỗ trợ các thao tác kết nối/đọc/ghi. Đăng ký bit không hợp lệ ném `IllegalArgumentException`.

**Đừng để `OP_WRITE` bật mãi chỉ vì socket đang mở.** Socket thường có thể ghi gần như liên tục khi buffer mạng còn chỗ, dẫn tới selector thức dậy lặp đi lặp lại và tiêu tốn CPU. Chỉ quan tâm `OP_WRITE` khi có dữ liệu **đã chuẩn bị nhưng chưa gửi hết**, và bỏ interest này khi không còn byte chờ gửi.

## 9. Ví dụ Java 17+ chạy độc lập: non-blocking accept/read với Selector

Chương trình sau mở server trên loopback ở chế độ non-blocking, đăng ký `OP_ACCEPT`, sau đó dùng một client **blocking** để gửi chuỗi ASCII `HELLO`. Event loop của server dùng `Selector` nhận kết nối và đọc cho đến khi đủ năm byte. Việc client được dùng blocking không làm server trở thành blocking: **chế độ được cấu hình riêng theo channel**.

Ví dụ chỉ in kết quả khi đã nhận đủ dữ liệu, nên không phụ thuộc sự kiện SELECT xảy ra một hay nhiều lần. Thời gian đợi được giới hạn để demo không chờ mãi trong môi trường mạng gặp sự cố.

**Tệp `NonBlockingSelectorDemo.java`:**

```java
import java.io.EOFException;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.util.Iterator;
import java.util.concurrent.TimeUnit;

public class NonBlockingSelectorDemo {
    public static void main(String[] args) throws IOException {
        try (Selector selector = Selector.open();
             ServerSocketChannel server = ServerSocketChannel.open()) {

            server.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 0));
            server.configureBlocking(false);
            server.register(selector, SelectionKey.OP_ACCEPT);

            try (SocketChannel client = SocketChannel.open()) {
                client.connect(server.getLocalAddress());
                ByteBuffer message = ByteBuffer.wrap(
                        "HELLO".getBytes(StandardCharsets.US_ASCII));

                while (message.hasRemaining()) {
                    client.write(message);
                }

                String received = null;
                long deadline = System.nanoTime()
                        + TimeUnit.SECONDS.toNanos(5);

                while (received == null) {
                    long remainingNanos = deadline - System.nanoTime();
                    if (remainingNanos <= 0) {
                        throw new IOException("Selector timeout");
                    }

                    long timeoutMillis = Math.max(1L,
                            TimeUnit.NANOSECONDS.toMillis(remainingNanos));
                    selector.select(timeoutMillis);

                    Iterator<SelectionKey> keys =
                            selector.selectedKeys().iterator();

                    while (keys.hasNext()) {
                        SelectionKey key = keys.next();
                        keys.remove();

                        if (!key.isValid()) {
                            continue;
                        }

                        if (key.isAcceptable()) {
                            SocketChannel peer = server.accept();
                            if (peer != null) {
                                peer.configureBlocking(false);
                                peer.register(selector, SelectionKey.OP_READ,
                                        ByteBuffer.allocate(5));
                            }
                        } else if (key.isReadable()) {
                            SocketChannel peer =
                                    (SocketChannel) key.channel();
                            ByteBuffer buffer =
                                    (ByteBuffer) key.attachment();

                            int n = peer.read(buffer);
                            if (n == -1) {
                                throw new EOFException("Peer closed early");
                            }

                            if (!buffer.hasRemaining()) {
                                buffer.flip();
                                received = StandardCharsets.US_ASCII
                                        .decode(buffer).toString();
                                key.cancel();
                                peer.close();
                            }
                        }
                    }
                }

                System.out.println("Server non-blocking: "
                        + !server.isBlocking());
                System.out.println("Noi dung nhan: " + received);
            }
        }
    }
}
```

Biên dịch, chạy:

```bash
javac NonBlockingSelectorDemo.java
java NonBlockingSelectorDemo
```

**Stdout khi loopback và I/O thành công:**

```text
Server non-blocking: true
Noi dung nhan: HELLO
```

**Cần hiểu rõ:**

1. `server.configureBlocking(false)` bắt buộc trước `server.register(selector, OP_ACCEPT)`.
2. Selector chờ sẵn sàng chấp nhận, sau đó `server.accept()` trả channel mới hoặc có thể trả null; chương trình kiểm tra null.
3. Channel mới cũng được chuyển non-blocking trước khi đăng ký `OP_READ`.
4. `read(buffer)` có thể đọc một phần. Vì buffer có capacity 5, event loop giữ buffer làm attachment và tiếp tục đến khi đủ năm byte.
5. `selector.selectedKeys()` là tập các key đã được chọn; code dùng `Iterator.remove()` để tránh xử lý lặp key cũ không đúng cách.
6. Demo không dùng `OP_WRITE` vì client gửi dữ liệu bằng blocking mode. Server production xử lý chiều gửi non-blocking cần quản lý hàng đợi buffer và bật/tắt `OP_WRITE` theo lượng dữ liệu chưa gửi.
7. Đoạn demo giả định thông điệp đúng năm byte. Ứng dụng thực cần **framing** (ví dụ tiền tố độ dài, delimiter hoặc protocol parser), giới hạn kích thước thông điệp, bộ nhớ và số kết nối để tránh đọc dở hoặc xử lý sai dữ liệu.

## 10. Vòng đời kết nối non-blocking và `OP_CONNECT`

Client non-blocking có thêm giai đoạn *kết nối chưa hoàn tất*:

```text
SocketChannel.open()
      |
      v
configureBlocking(false)
      |
      v
connect(address)
      |
      +--- true ---> connected; đăng ký OP_READ khi cần
      |
      +--- false --> đăng ký OP_CONNECT
                         |
                         v
                  selector báo connectable
                         |
                         v
                    finishConnect()
                         |
                         +--- true --> connected
                         |
                         +--- false --> tiếp tục đợi
```

Khung mã minh họa:

```java
SocketChannel socket = SocketChannel.open();
socket.configureBlocking(false);
boolean connected = socket.connect(remoteAddress);

if (connected) {
    socket.register(selector, SelectionKey.OP_READ);
} else {
    socket.register(selector, SelectionKey.OP_CONNECT);
}

// Trong event loop, chỉ khi key.isConnectable():
// if (socket.finishConnect()) {
//     key.interestOps(SelectionKey.OP_READ);
// }
```

Đoạn này **không phải chương trình độc lập**; cần khai báo `remoteAddress`, `selector`, xử lý `IOException`, sự kiện đọc/ghi và đóng tài nguyên. `finishConnect()` có thể ném ngoại lệ khi kết nối thất bại; không dùng `isConnectable()` như bảo đảm kết nối thành công. Nếu còn dữ liệu outbound đang chờ sau khi connect hoàn tất, có thể quan tâm thêm `OP_WRITE`.

## 11. Partial write và backpressure trong non-blocking

Với socket non-blocking, hàng đợi gửi ở kernel hoặc peer có thể không nhận thêm byte ngay. Một lệnh:

```java
int sent = socket.write(outgoing);
```

có thể trả từ 0 tới số byte đang còn trong `outgoing`. Chỉ phần đã gửi làm `outgoing.position()` tăng. Nếu `sent==0` hoặc vẫn còn `outgoing.hasRemaining()`, phải **giữ lại phần dữ liệu chưa gửi** để gửi tiếp khi `OP_WRITE` báo sẵn sàng.

Một mô hình quản lý:

```text
Ứng dụng tạo response -> ByteBuffer ở read mode
                           |
                           v
                      socket.write()
                           |
                    +------+------+
                    |             |
                Đã gửi hết    Còn remaining
                    |             |
                  bỏ OP_WRITE   bật OP_WRITE
                                  |
                                  v
                              sự kiện writable
                                  |
                                  v
                            thử write lần nữa
```

Không dùng vòng `while (outgoing.hasRemaining()) { socket.write(outgoing); }` không điều kiện trên event-loop non-blocking nếu `write()` có thể luôn trả 0: nó gây **busy spin**, chặn các kết nối khác. Thay vào đó, khi chưa gửi hết, giữ lại buffer và quay về selector.

**Backpressure** là cơ chế phản hồi khi nơi tiêu thụ dữ liệu chậm hơn nơi tạo dữ liệu. Event loop cần giới hạn lượng dữ liệu pending trên mỗi kết nối (ví dụ giới hạn byte trong queue), quyết định tạm ngừng đọc, từ chối thêm request hoặc ngắt kết nối theo chính sách. Non-blocking không loại bỏ áp lực bộ nhớ; nó khiến việc quản lý áp lực này trở thành trách nhiệm rõ ràng của ứng dụng.

## 12. `ByteBuffer.flip`, `clear` và `compact` trong network I/O

Cả hai chế độ đều dùng `ByteBuffer`; chuyển blocking mode không tự thay đổi quy tắc buffer.

| Bước | Buffer state |
| --- | --- |
| Chuẩn bị nhận byte | `clear()` → `position=0`, `limit=capacity` |
| Gọi `channel.read(buffer)` | `position` tăng theo byte nhận thực tế |
| Chuẩn bị giải mã/xử lý | `flip()` → `limit=oldPosition`, `position=0` |
| Giải mã/tiêu thụ | `position` tăng theo số byte đã xử lý |
| Đã xử lý hết | `clear()` để nhận lần tiếp theo |
| Chưa xử lý hết | `compact()` giữ phần dư trước khi nhận thêm |

**`clear()` không xóa byte khỏi vùng nhớ**. Nó chỉ thiết lập lại position và limit. Nếu parser còn một phần thông điệp chưa đủ byte, `compact()` đưa phần chưa xử lý về đầu buffer, giúp nhận thêm dữ liệu ở vùng trống phía sau.

Đối với UTF-8 hoặc các protocol có record bị chia qua nhiều lần nhận, mỗi `read` không nhất thiết tương ứng một chuỗi/hàng. Cần parser theo giao thức và decoder có khả năng xử lý dữ liệu đến từng phần. Ví dụ non-blocking ở trên dùng ASCII với độ dài cố định nhằm cô lập chủ đề blocking mode, không áp dụng nguyên xi để xử lý text tùy ý.

## 13. So sánh blocking và non-blocking

| Tiêu chí | Blocking | Non-blocking |
| --- | --- | --- |
| Khi I/O chưa sẵn sàng | Luồng gọi có thể chờ | Lời gọi có thể trở về không tiến độ |
| Điều khiển luồng | Tuyến tính, dễ đọc | Event-driven/state machine thường phức tạp hơn |
| Công cụ NIO phổ biến | `SocketChannel`, `ServerSocketChannel` blocking | `configureBlocking(false)` + `Selector` |
| Xử lý kết quả `read` | Vẫn phải kiểm tra số byte, EOF | Phải kiểm tra số byte, `0`, EOF |
| Xử lý `write` | Vẫn phải kiểm tra partial write | Phải giữ pending bytes và chờ readiness |
| Chi phí nhiều kết nối chờ | Mô hình nhiều luồng có thể tốn tài nguyên | Một event loop có thể quản lý nhiều socket |
| Thử thách thiết kế | Thread, timeout, hủy, giới hạn tài nguyên | Key, trạng thái kết nối, buffer, backpressure, lỗi |
| Hiệu năng | Có thể tốt cho ứng dụng đơn giản | Có thể tốt cho lượng lớn socket chủ yếu chờ |
| Bản chất | Một cách thực hiện I/O | Một cách thực hiện I/O, không tự đồng nghĩa bất đồng bộ |

Chọn mô hình theo yêu cầu cụ thể. Nếu số kết nối ít và công việc chủ yếu tuần tự, blocking có thể dễ bảo trì. Nếu phải quản lý hàng nghìn kết nối chủ yếu đợi sự kiện, non-blocking kết hợp selector có thể phù hợp hơn. Cần **benchmark trong môi trường thực** thay vì khẳng định một chế độ luôn nhanh hơn.

## 14. Non-blocking khác asynchronous ở điểm nào?

Hai thuật ngữ thường bị dùng lẫn:

- **Non-blocking channel**: một lần gọi I/O có thể trở về ngay nếu chưa tiến triển. Ứng dụng thường tiếp tục bằng `Selector`, readiness và thao tác I/O **chủ động ở lần sau**.
- **Asynchronous channel**: API như `AsynchronousSocketChannel` dùng callback hoặc `Future` để biểu diễn một thao tác bất đồng bộ đang diễn ra hoặc đã hoàn tất. Cơ chế hoàn thành thuộc hợp đồng API asynchronous, không phải chính thao tác `SocketChannel.read` non-blocking.

Một event loop non-blocking có thể lập trình theo phong cách “asynchronous” ở cấp ứng dụng, nhưng không có nghĩa `SocketChannel.configureBlocking(false)` biến đối tượng thành `AsynchronousSocketChannel`. Hai loại có API và mô hình hoàn thành khác nhau.

Ngoài ra, `CompletableFuture` hoặc luồng riêng chạy một lời gọi blocking không tự chuyển **socket** sang non-blocking mode; chỉ cách tổ chức tác vụ ở tầng ứng dụng thay đổi.

## 15. Thời gian chờ, đóng kết nối và xử lý lỗi

Ứng dụng cần chính sách rõ cho:
- **Kết nối không hoàn tất**: timeout cho connect; xử lý `finishConnect` thất bại.
- **Peer im lặng**: timeout ở tầng giao thức/ứng dụng; non-blocking + selector timeout giúp event loop đánh giá deadline.
- **Đọc được `-1`**: peer kết thúc chiều gửi; hủy interest và đóng hoặc xử lý half-close theo giao thức.
- **Ghi chưa hết**: giữ buffer pending, không giải phóng/`clear` sớm.
- **Channel bị đóng khi đang được dùng**: bắt và xử lý `IOException`/`ClosedChannelException` hoặc lỗi cụ thể.
- **Selector key hủy**: kiểm tra `key.isValid()`; `interestOps` hoặc readiness trên key không hợp lệ có thể gây `CancelledKeyException`.
- **Đóng tài nguyên**: dùng `try-with-resources` khi ownership rõ, và quản lý vòng đời channel đã được gắn với selector.

`selector.select(timeout)` không đồng nghĩa timeout cho từng socket. Đây là khoảng chờ readiness của **lần lựa chọn**, còn timeout nghiệp vụ cần theo dõi deadline của từng kết nối và kiểm tra sau mỗi lần thức dậy.

Không giả định mỗi lần `select()` trả về đều có I/O hữu ích: selector có thể thức dậy do `wakeup()`, đóng, ngắt hoặc do các điều kiện khác; kiểm tra số key sẵn sàng và trạng thái channel trước khi xử lý.

**Bảo mật:** Khi xử lý dữ liệu từ mạng, giới hạn kích thước request, thời gian giữ kết nối, lượng buffer pending và số kết nối. Không cấp phát buffer vô hạn theo thông tin chiều dài do client gửi mà chưa kiểm tra.

## 16. Những lỗi phổ biến

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Nghĩ non-blocking `read()==0` là EOF | Kết thúc kết nối sớm | Chỉ `-1` là EOF trong hợp đồng đọc |
| Nghĩ blocking `read` luôn lấp đầy buffer | Parser nhận thiếu byte | Theo dõi số byte đã đọc, dùng framing |
| Nghĩ `write` luôn gửi hết dữ liệu | Mất phần response chưa gửi | Giữ `ByteBuffer` và tiếp tục từ position hiện tại |
| Quên `configureBlocking(false)` trước `register` | `IllegalBlockingModeException` | Cấu hình non-blocking trước khi đăng ký |
| Cố `configureBlocking(true)` khi vẫn đăng ký selector | `IllegalBlockingModeException` | Hoàn thành hủy đăng ký trước khi chuyển mode |
| Gọi `accept()` non-blocking rồi không kiểm tra null | `NullPointerException` | Kiểm tra kết quả trước khi dùng |
| Gọi `read/write` trước khi `finishConnect` xong | Sai trạng thái kết nối | Xử lý `OP_CONNECT` và `finishConnect` |
| Lặp liên tục khi `read/write == 0` | Busy spin, CPU cao | Trả quyền điều khiển cho Selector/event loop |
| Giữ `OP_WRITE` liên tục khi không có dữ liệu chờ | Vòng sự kiện thức dậy nhiều | Chỉ bật `OP_WRITE` khi pending write |
| Không xóa key khỏi `selectedKeys()` | Xử lý lặp sự kiện cũ | Duyệt qua iterator và `remove()` |
| Coi một lần `read` là một TCP message | Sai framing | Thiết kế protocol parser rõ ràng |
| Nghĩ `FileChannel` có thể đăng ký selector mạng | Không đúng kiểu API | Dùng `SelectableChannel` phù hợp |
| Đóng buffer/peer sai vòng đời | Mất dữ liệu hoặc lỗi I/O | Thiết kế ownership, shutdown và backpressure |

## 17. Bài tập kiểm tra

**Câu 1.** Một `SocketChannel` non-blocking có `dst.remaining() == 128` và gọi `read(dst)` trả về `0`. Có thể kết luận peer đã đóng kết nối chưa?

**Không.** `0` chỉ cho biết lần gọi hiện tại không nhận byte; chờ `OP_READ` hoặc cơ chế đợi phù hợp. Nếu `read` trả về `-1` mới là EOF.

**Câu 2.** `write(src)` trả về 3 khi ban đầu `src.remaining()==10`. Còn bao nhiêu byte cần xử lý, và cần làm gì?

**Còn 7 byte.** `src.position` tăng 3; không `clear` sớm. Nếu dùng non-blocking và chưa thể gửi tiếp, giữ buffer, quan tâm `OP_WRITE` và thử ghi phần dư khi sẵn sàng.

**Câu 3.** `ServerSocketChannel` đã được đăng ký với `Selector`. Có thể gọi `server.configureBlocking(true)` ngay không?

**Không.** Nếu còn đăng ký selector, chuyển về blocking ném `IllegalBlockingModeException`; cần quản lý hủy đăng ký, xử lý canceled keys và vòng đời selector đúng cách.

**Câu 4.** Non-blocking `SocketChannel.connect(remote)` trả về `false`. Có phải thất bại kết nối?

**Không.** Nó có thể chỉ nghĩa là kết nối đang được thực hiện. Đăng ký `OP_CONNECT`, gọi `finishConnect()` khi sẵn sàng và xử lý lỗi nếu có.

**Câu 5.** Vì sao một server non-blocking có thể phục vụ nhiều kết nối trên một event loop, nhưng vẫn có thể phản hồi chậm?

**Vì event loop vẫn là mã chạy trên CPU.** Nếu handler làm việc chặn lâu, xử lý quá nặng, hoặc bận quay vòng khi không có I/O, các kết nối khác sẽ bị chậm. Phải tránh tác vụ blocking trên event loop hoặc đưa tác vụ nặng sang nơi thực thi riêng có kiểm soát.

## 18. Ghi nhớ

1. **Blocking**: thao tác I/O có thể giữ luồng chờ. **Non-blocking**: thao tác có thể trả ngay với kết quả chưa tiến triển.
2. **`configureBlocking(false)`** áp dụng trên `SelectableChannel`; NIO socket mới thường bắt đầu ở blocking mode.
3. **`accept()==null`**, **`read()==0`**, **`read()==-1`**, **`connect()==false`** là những trạng thái **khác nhau** phải xử lý đúng hợp đồng.
4. **`Selector`** giúp theo dõi readiness `OP_ACCEPT`, `OP_CONNECT`, `OP_READ`, `OP_WRITE` mà không busy-spin.
5. **Partial read/write và `ByteBuffer.position/limit`** là trách nhiệm của ứng dụng ở cả hai chế độ; với non-blocking cần lưu trạng thái còn lại và quản lý backpressure.
6. Blocking, non-blocking và asynchronous là những khái niệm liên quan nhưng **không đồng nghĩa**. Chọn kiến trúc dựa trên nhu cầu, độ phức tạp và tải thực tế.

**Tài liệu chuẩn:** Java SE 17 API — `java.nio.channels.SelectableChannel`, `ServerSocketChannel`, `SocketChannel`, `Selector`, `SelectionKey`, `java.nio.ByteBuffer`. Đặc biệt tham khảo Javadoc về `configureBlocking`, `register` và các kết quả trả về của `accept/read/write/connect/finishConnect`.
