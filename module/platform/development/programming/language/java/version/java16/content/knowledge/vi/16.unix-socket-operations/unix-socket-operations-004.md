# Thiết kế timeout ở tầng ứng dụng cho kết nối không phản hồi

**Module:** `JAVA_VERSION_JAVA16`  
**Chương:** Vận hành socket  
**Áp dụng:** Java 16 trở lên; ví dụ dùng Unix-domain `SocketChannel`, `Selector` và API thời gian chuẩn.

Unix-domain socket giao tiếp qua filesystem trên cùng máy, nhưng một kết nối đã mở vẫn có thể không phản hồi: server bận, request không được xử lý, client chờ response sai định dạng hoặc một phía ngừng đọc/ghi. Nếu ứng dụng dùng I/O blocking mà không có giới hạn thời gian, thread có thể chờ vô hạn và giữ tài nguyên.

Unix-domain socket trong Java dùng các API NIO như `SocketChannel`, `ServerSocketChannel` và `Selector`. Không nên thiết kế timeout dựa trên giả định rằng socket này có đầy đủ các tùy chọn timeout của TCP `Socket`. Cách kiểm soát rõ ràng là đặt deadline ở tầng ứng dụng, dùng non-blocking channel và chờ readiness qua `Selector`.

Một thiết kế timeout tốt cần phân biệt:

- **Connect timeout:** thời gian tối đa để hoàn tất kết nối.
- **Write timeout:** thời gian tối đa để gửi đủ request.
- **Read timeout:** thời gian tối đa để nhận dữ liệu cần thiết.
- **Request deadline:** tổng thời gian cho cả kết nối, gửi request và nhận response.
- **Idle timeout:** thời gian một connection không có hoạt động hợp lệ trước khi server đóng nó.

Các giới hạn này có thể dùng chung một deadline tổng hoặc có ngân sách riêng tùy giao thức. Với request/response đơn giản, deadline tổng thường dễ hiểu và tránh việc mỗi giai đoạn được phép kéo dài vô hạn.

## 1. Vì sao kết nối cục bộ vẫn cần timeout?

Unix-domain socket tránh một số chi phí và vấn đề của mạng IP, nhưng không bảo đảm peer luôn phản hồi:

- Server đã accept connection nhưng thread xử lý bị treo hoặc chờ dependency khác.
- Server nhận request nhưng không gửi response.
- Client gửi request lớn trong khi server không đọc, khiến buffer ghi đầy.
- Client đọc chậm hoặc ngừng đọc, khiến server không thể gửi hết dữ liệu.
- Một phía vẫn sống nhưng không còn xử lý giao thức đúng cách.
- Connection được mở nhưng ứng dụng không có giới hạn cho thời gian chờ từng frame.

Nếu không đặt timeout, mỗi connection không phản hồi có thể giữ một thread, buffer, channel và trạng thái request trong thời gian dài. Nhiều connection như vậy có thể làm cạn thread pool hoặc tài nguyên của service.

Timeout không làm peer hoạt động trở lại. Nó đặt giới hạn cho thời gian ứng dụng sẵn sàng chờ, sau đó giải phóng tài nguyên và trả lỗi phù hợp.

## 2. Phân biệt timeout kết nối và timeout request

Không gộp mọi loại timeout thành một con số mà không xác định nó đo giai đoạn nào:

| Loại timeout | Bắt đầu tính khi nào? | Kết thúc khi nào? |
| --- | --- | --- |
| Connect timeout | Bắt đầu mở/kết nối tới pathname | Connection hoàn tất hoặc thất bại |
| Write timeout | Bắt đầu gửi request | Toàn bộ request được ghi vào channel |
| Read timeout | Bắt đầu chờ response/frame | Đủ dữ liệu cần thiết đã được đọc |
| Request deadline | Bắt đầu xử lý một request | Request hoàn tất hoặc deadline hết |
| Idle timeout | Từ lần hoạt động hợp lệ gần nhất | Có hoạt động mới hoặc connection bị đóng |

Ví dụ một request có deadline 2 giây. Nếu connect mất 300 ms, write mất 200 ms, thời gian còn lại để đọc response chỉ còn khoảng 1,5 giây. Cách này giới hạn tổng thời gian end-to-end.

Nếu dùng timeout 2 giây riêng cho connect, write và read, tổng thời gian thực tế có thể gần 6 giây. Đây có thể là chủ đích, nhưng cần ghi rõ trong hợp đồng của ứng dụng.

## 3. Dùng non-blocking SocketChannel và Selector

`SocketChannel` có thể hoạt động ở chế độ blocking hoặc non-blocking. Trong chế độ non-blocking, thao tác `connect`, `read` và `write` có thể hoàn tất một phần hoặc chưa sẵn sàng; `Selector` giúp chờ các sự kiện `OP_CONNECT`, `OP_READ` và `OP_WRITE`.

Với Unix-domain socket từ Java 16:

```java
SocketChannel channel =
    SocketChannel.open(StandardProtocolFamily.UNIX);
channel.configureBlocking(false);

Selector selector = Selector.open();
SelectionKey key = channel.register(selector, 0);

boolean connected = channel.connect(
    UnixDomainSocketAddress.of("/run/myapp/service.sock")
);

if (!connected) {
    key.interestOps(SelectionKey.OP_CONNECT);
    // Chờ OP_CONNECT trong giới hạn deadline.
    // Sau đó gọi channel.finishConnect().
}
```

`Selector` có thể theo dõi readiness của Unix-domain `SocketChannel`. Khi một thao tác non-blocking trả về `0`, điều đó thường có nghĩa là hiện chưa có tiến triển; ứng dụng chờ readiness tương ứng rồi thử lại.

Không dùng `Thread.sleep()` trong vòng lặp để thăm dò channel. Cách đó vừa gây trễ không cần thiết vừa tiêu thụ CPU. Dùng selector với thời gian chờ còn lại của deadline.

## 4. Dùng đồng hồ monotonic để tính deadline

Đo thời gian chờ bằng `System.nanoTime()`, không dùng `System.currentTimeMillis()`. Đồng hồ wall-clock có thể thay đổi do đồng bộ thời gian hoặc điều chỉnh hệ thống; `nanoTime()` được thiết kế để đo khoảng thời gian trôi qua.

Tính thời gian còn lại:

```java
long startedAt = System.nanoTime();
long timeoutNanos = Duration.ofSeconds(2).toNanos();

long elapsed = System.nanoTime() - startedAt;
long remainingNanos = timeoutNanos - elapsed;

if (remainingNanos <= 0) {
    throw new SocketTimeoutException("Request deadline exceeded");
}
```

Khi truyền thời gian chờ cho `Selector.select(long)`, cần chú ý đơn vị là millisecond. Nếu đổi từ nanosecond sang millisecond bằng phép làm tròn xuống, một khoảng còn lại nhỏ hơn 1 ms sẽ thành `0`; `select(0)` có nghĩa chờ vô hạn. Vì vậy hãy dùng ít nhất 1 ms sau khi đã xác nhận deadline chưa hết, rồi kiểm tra deadline lại sau khi selector trả về.

## 5. Ví dụ hoàn chỉnh: connect, write và read trong một deadline

Ví dụ sau dùng giao thức minh họa có request `PING\n` và response cố định 5 byte `PONG\n`. Trong giao thức thực tế, hãy dùng framing rõ ràng như length-prefix hoặc delimiter và giới hạn kích thước frame.

```java
import java.io.EOFException;
import java.io.IOException;
import java.net.StandardProtocolFamily;
import java.net.SocketTimeoutException;
import java.net.UnixDomainSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Iterator;
import java.util.concurrent.TimeUnit;

public final class UnixSocketClient {
    private static final int MAX_RESPONSE_BYTES = 1_048_576;

    private UnixSocketClient() {}

    public static byte[] exchange(
            Path socketPath,
            byte[] request,
            int responseLength,
            Duration timeout
    ) throws IOException {
        if (responseLength <= 0 || responseLength > MAX_RESPONSE_BYTES) {
            throw new IllegalArgumentException("responseLength is outside the allowed range");
        }
        if (timeout.isZero() || timeout.isNegative()) {
            throw new IllegalArgumentException("timeout must be positive");
        }

        final long timeoutNanos;
        try {
            timeoutNanos = timeout.toNanos();
        } catch (ArithmeticException tooLarge) {
            throw new IllegalArgumentException("timeout is too large", tooLarge);
        }

        long startedAt = System.nanoTime();

        try (SocketChannel channel =
                 SocketChannel.open(StandardProtocolFamily.UNIX);
             Selector selector = Selector.open()) {

            channel.configureBlocking(false);
            SelectionKey key = channel.register(selector, 0);

            boolean connected = channel.connect(
                UnixDomainSocketAddress.of(socketPath)
            );

            if (!connected) {
                while (true) {
                    checkDeadline(startedAt, timeoutNanos, "connect");
                    if (channel.finishConnect()) {
                        break;
                    }
                    awaitReady(
                        selector, key, SelectionKey.OP_CONNECT,
                        startedAt, timeoutNanos, "connect"
                    );
                }
            }

            writeFully(
                channel, selector, key, ByteBuffer.wrap(request),
                startedAt, timeoutNanos
            );

            ByteBuffer response = ByteBuffer.allocate(responseLength);
            readFully(
                channel, selector, key, response,
                startedAt, timeoutNanos
            );

            checkDeadline(startedAt, timeoutNanos, "request");
            return response.array();
        }
    }

    private static void writeFully(
            SocketChannel channel,
            Selector selector,
            SelectionKey key,
            ByteBuffer data,
            long startedAt,
            long timeoutNanos
    ) throws IOException {
        while (data.hasRemaining()) {
            checkDeadline(startedAt, timeoutNanos, "write");
            int written = channel.write(data);
            if (written == 0) {
                awaitReady(
                    selector, key, SelectionKey.OP_WRITE,
                    startedAt, timeoutNanos, "write"
                );
            }
        }
    }

    private static void readFully(
            SocketChannel channel,
            Selector selector,
            SelectionKey key,
            ByteBuffer data,
            long startedAt,
            long timeoutNanos
    ) throws IOException {
        while (data.hasRemaining()) {
            checkDeadline(startedAt, timeoutNanos, "read");
            int read = channel.read(data);
            if (read < 0) {
                throw new EOFException("Peer closed before response was complete");
            }
            if (read == 0) {
                awaitReady(
                    selector, key, SelectionKey.OP_READ,
                    startedAt, timeoutNanos, "read"
                );
            }
        }
    }

    private static void awaitReady(
            Selector selector,
            SelectionKey key,
            int operation,
            long startedAt,
            long timeoutNanos,
            String phase
    ) throws IOException {
        key.interestOps(operation);

        while (true) {
            long remaining = remainingNanos(startedAt, timeoutNanos, phase);

            long waitMillis = Math.max(
                1L, TimeUnit.NANOSECONDS.toMillis(remaining)
            );
            selector.select(waitMillis);

            Iterator<SelectionKey> iterator =
                selector.selectedKeys().iterator();
            while (iterator.hasNext()) {
                SelectionKey selected = iterator.next();
                iterator.remove();

                if (selected == key
                        && selected.isValid()
                        && (selected.readyOps() & operation) != 0) {
                    return;
                }
            }
        }
    }

    private static void checkDeadline(
            long startedAt,
            long timeoutNanos,
            String phase
    ) throws SocketTimeoutException {
        remainingNanos(startedAt, timeoutNanos, phase);
    }

    private static long remainingNanos(
            long startedAt,
            long timeoutNanos,
            String phase
    ) throws SocketTimeoutException {
        long remaining = timeoutNanos - (System.nanoTime() - startedAt);
        if (remaining <= 0) {
            throw new SocketTimeoutException(
                "Unix socket " + phase + " deadline exceeded"
            );
        }
        return remaining;
    }

    public static void main(String[] args) throws IOException {
        byte[] response = exchange(
            Path.of("/run/myapp/service.sock"),
            "PING\n".getBytes(StandardCharsets.UTF_8),
            5,
            Duration.ofSeconds(2)
        );

        System.out.println(
            new String(response, StandardCharsets.UTF_8)
        );
    }
}
```

Điểm chính của ví dụ:

- Channel được cấu hình non-blocking trước khi đăng ký với selector.
- `connect()` có thể hoàn tất ngay hoặc cần chờ `OP_CONNECT` và gọi `finishConnect()`.
- `writeFully()` xử lý trường hợp chỉ ghi được một phần request.
- `readFully()` xử lý trường hợp response đến thành nhiều lần đọc; `-1` được xem là peer đóng sớm.
- Mọi giai đoạn dùng chung `startedAt` và `timeoutNanos`, nên tổng thời gian không vượt quá ngân sách request (ngoại trừ độ trễ nhỏ do scheduler/OS đánh thức thread).
- Khi hết hạn, `SocketTimeoutException` được ném; try-with-resources đóng channel và selector.

Ví dụ đọc response có độ dài cố định để làm rõ partial read. Giao thức production nên có header độ dài, kiểm tra độ dài không vượt giới hạn trước khi cấp phát buffer, và xử lý nhiều frame trên cùng connection theo trạng thái parser riêng.

## 6. Không dùng một timeout tổng cho mọi loại request

Một deadline tổng phù hợp với request/response có SLA rõ. Nhưng connection sống lâu có thể cần chính sách riêng:

| Kiểu kết nối | Chính sách thường phù hợp |
| --- | --- |
| RPC ngắn | Một deadline end-to-end cho connect, write và read |
| Stream dữ liệu liên tục | Read/write idle timeout và giới hạn thời gian từng frame |
| Client tương tác lâu dài | Idle timeout, heartbeat theo giao thức và deadline cho từng request |
| Upload/download lớn | Deadline hoặc tốc độ tối thiểu theo từng giai đoạn, giới hạn kích thước và backpressure |
| Health check | Deadline ngắn, độc lập với timeout nghiệp vụ thông thường |

Không đặt một timeout cực ngắn cho toàn bộ connection streaming nếu ứng dụng hợp lệ có thể không gửi dữ liệu trong một khoảng dài. Thay vào đó, đo khoảng thời gian từ hoạt động hợp lệ gần nhất và đặt idle timeout phù hợp.

## 7. Timeout phía server: không để client giữ tài nguyên vô hạn

Timeout chỉ ở client bảo vệ client khỏi chờ lâu. Nó không tự giải phóng connection hoặc worker ở server nếu server vẫn đang chờ request.

Server cũng cần chính sách:

- Giới hạn thời gian chờ request đầu tiên sau khi accept.
- Giới hạn thời gian nhận đủ header và body.
- Giới hạn idle time giữa các frame nếu protocol cho phép nhiều request trên một connection.
- Giới hạn thời gian xử lý request và chờ dependency bên ngoài.
- Đóng connection khi client gửi frame quá lớn, sai định dạng hoặc vượt deadline.

Với non-blocking server, có thể đăng ký accepted `SocketChannel` với selector và lưu deadline/last-activity cho từng connection. Mỗi lần selector thức dậy, server xử lý readiness và kiểm tra những deadline đã hết. Không cần tạo một thread riêng chỉ để `sleep()` chờ timeout cho từng connection.

Với blocking server, dùng executor có giới hạn và quản lý channel theo connection. Khi deadline hết, đóng channel để giải phóng thao tác I/O đang chờ; chỉ hủy `Future` mà không đóng channel có thể khiến thao tác I/O vẫn còn chạy.

## 8. Heartbeat và ping không thay thế deadline

Heartbeat có thể giúp phát hiện peer không còn phản hồi trong một protocol kết nối dài hạn. Tuy nhiên, heartbeat phải có deadline riêng:

1. Gửi ping với sequence hoặc correlation ID.
2. Chờ pong tương ứng trong một khoảng thời gian hữu hạn.
3. Bỏ qua hoặc xử lý đúng pong trễ/không khớp.
4. Sau số lần thất bại theo chính sách, đánh dấu peer không khỏe và đóng/reconnect.

Không gửi heartbeat liên tục chỉ vì một response bị chậm; cần tránh tạo tải bổ sung lên server đang quá tải. Với RPC ngắn, request deadline thường đủ và không cần heartbeat riêng.

## 9. Nếu phải giữ blocking I/O, hãy đóng channel khi timeout

Trong hệ thống cũ hoặc API xử lý theo blocking mode, có thể chạy I/O trong executor có giới hạn và chờ kết quả bằng `Future.get(timeout, unit)`. Khi timeout:

- Đóng `SocketChannel` liên quan để buộc thao tác I/O đang chờ kết thúc.
- Hủy task để báo cho executor rằng công việc không còn cần thiết.
- Xử lý `AsynchronousCloseException` hoặc lỗi I/O tương ứng trong worker.
- Không trả channel đã timeout về pool hoặc tái sử dụng nó.

`Future.cancel(true)` hoặc `CompletableFuture.orTimeout()` chỉ điều khiển trạng thái task/future; không nên giả định chúng luôn tự đóng channel hoặc hủy mọi I/O đang chờ. Ứng dụng phải sở hữu channel và chủ động đóng khi deadline hết.

Không tạo một thread không giới hạn cho mỗi connection. Dùng executor có queue và concurrency limit rõ ràng; nếu workload cần nhiều connection đồng thời, non-blocking selector thường phù hợp hơn.

## 10. Phân biệt timeout với EOF, lỗi kết nối và lỗi giao thức

Không gom mọi lỗi thành “timeout”:

| Kết quả | Ý nghĩa | Cách xử lý |
| --- | --- | --- |
| `SocketTimeoutException` | Deadline hết trước khi thao tác hoàn tất | Ghi nhận phase, đóng connection, trả lỗi timeout |
| `EOFException` hoặc `read() == -1` | Peer đóng trước khi đủ response | Xem là response không hoàn chỉnh/protocol failure |
| `ConnectException` | Không thể kết nối tới endpoint | Kiểm tra server, pathname, quyền và trạng thái listener |
| `AccessDeniedException` hoặc lỗi permission | OS từ chối truy cập socket path | Kiểm tra owner/group/mode/ACL |
| Protocol error | Dữ liệu nhận được sai format hoặc vượt giới hạn | Đóng connection hoặc trả lỗi giao thức |
| Cancel/interruption | Caller không còn cần kết quả hoặc task bị dừng | Đóng channel và bảo toàn trạng thái interrupt phù hợp |

Phân loại đúng giúp retry policy không biến lỗi permission hoặc protocol thành vòng lặp reconnect vô ích.

## 11. Retry sau timeout cần có giới hạn

Timeout không chứng minh server chưa xử lý request. Ví dụ server đã thực hiện thanh toán hoặc ghi dữ liệu, nhưng response bị chậm và client hết deadline. Nếu client gửi lại ngay mà không có cơ chế idempotency, thao tác có thể được thực hiện hai lần.

Khi thiết kế retry:

- Chỉ retry các thao tác an toàn hoặc có idempotency key.
- Đặt giới hạn số lần retry và tổng deadline bao gồm cả backoff.
- Dùng exponential backoff có jitter để tránh nhiều client reconnect cùng lúc.
- Không retry lỗi cấu hình, permission hoặc protocol không thể phục hồi bằng reconnect.
- Ghi correlation ID để đối chiếu request đã gửi và kết quả server.

Retry không được tạo một deadline mới vô hạn sau mỗi lần timeout. Nếu request có tổng ngân sách 3 giây, mọi lần connect, retry, write và read phải cùng tiêu thụ ngân sách đó.

## 12. Những nhầm lẫn cần tránh

| Nhận định | Đúng hay sai? | Giải thích |
| --- | --- | --- |
| Unix-domain socket cục bộ nên không thể bị treo chờ. | **Sai** | Peer có thể không đọc, không xử lý hoặc không gửi response. |
| Timeout connect cũng giới hạn thời gian đọc response. | **Sai** | Đây là các giai đoạn khác nhau. |
| Một request deadline chung có thể giới hạn toàn bộ exchange. | **Đúng** | Các phase cùng dùng một ngân sách thời gian còn lại. |
| `System.currentTimeMillis()` là đồng hồ tốt nhất để đo timeout. | **Sai** | Dùng `System.nanoTime()` cho khoảng thời gian trôi qua. |
| `Selector.select(0)` là polling không chờ. | **Sai** | Giá trị 0 có nghĩa chờ vô hạn; cần tránh khi làm tròn timeout xuống millisecond. |
| `read()` luôn trả đủ response trong một lần. | **Sai** | Phải xử lý partial read và EOF. |
| `Future.cancel(true)` luôn đóng socket I/O. | **Sai** | Chủ động đóng channel để giải phóng I/O đang chờ. |
| Client timeout đồng nghĩa server chưa thực hiện request. | **Sai** | Server có thể đã xử lý xong nhưng response đến muộn. |
| Heartbeat không cần deadline vì nó chỉ là ping nhỏ. | **Sai** | Phải giới hạn thời gian chờ pong và số lần thất bại. |

## 13. Checklist thiết kế timeout

1. Đã phân biệt connect, write, read, request deadline và idle timeout chưa?
2. Deadline có dùng `System.nanoTime()` thay vì wall-clock không?
3. Các phase có dùng chung một deadline nếu SLA là end-to-end không?
4. `Selector.select()` có nhận timeout dương sau khi kiểm tra deadline không?
5. Code có xử lý partial write, partial read, `read() == -1` và connection close không?
6. Protocol có framing và giới hạn kích thước frame không?
7. Khi timeout, channel và selector có được đóng không?
8. Server có giới hạn thời gian chờ header/body và idle client không?
9. Heartbeat có deadline và chính sách thất bại không?
10. Blocking I/O có executor giới hạn và cơ chế đóng channel khi timeout không?
11. Retry có idempotency, backoff, jitter và tổng deadline không?
12. Log có phân biệt timeout, EOF, permission, connect và protocol error không?

**Ghi nhớ:** Unix-domain socket không tự cung cấp deadline cho nghiệp vụ. Dùng non-blocking `SocketChannel` với `Selector` để chờ connect/read/write theo thời gian còn lại của một deadline monotonic. Xử lý partial I/O, đóng channel khi hết hạn, đặt timeout ở cả client và server, và thiết kế retry có giới hạn cùng idempotency. Timeout là giới hạn thời gian chờ của ứng dụng, không phải bằng chứng rằng peer chưa thực hiện request.

## Tài liệu chính thức

- [JEP 380 — Unix-Domain Socket Channels, Java 16](https://openjdk.org/jeps/380).
- [Java SE 26 API — `SocketChannel`, blocking/non-blocking connect, read và write](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/SocketChannel.html).
- [Java SE 26 API — `Selector.select(long)`, thời gian chờ và selected keys](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/Selector.html#select(long)).
- [Java SE 26 API — `SelectionKey`, `OP_CONNECT`, `OP_READ` và `OP_WRITE`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/SelectionKey.html).
- [Java SE 26 API — `System.nanoTime`, đo elapsed time](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/System.html#nanoTime()).
- [Java SE 26 API — `SocketTimeoutException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/SocketTimeoutException.html).
- [Java SE 26 API — `InterruptibleChannel`, đóng channel khi thread bị interrupt](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/InterruptibleChannel.html).
