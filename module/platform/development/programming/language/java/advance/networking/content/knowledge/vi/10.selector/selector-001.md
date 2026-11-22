# Selector giải quyết bài toán theo dõi nhiều kết nối như thế nào?

Khi xây dựng một TCP server, vấn đề không chỉ là nhận được một kết nối. Server còn phải chờ dữ liệu từ rất nhiều client đang mở socket, có thể chỉ gửi vài byte mỗi phút. Nếu dùng I/O blocking theo cách đơn giản, một luồng đang gọi `read()` trên client A sẽ phải chờ A có dữ liệu; trong thời gian ấy, cùng luồng không xử lý ngay client B, C. Cách thường dùng là tạo một thread cho mỗi kết nối, nhưng nếu có rất nhiều kết nối nhàn rỗi, hệ thống vẫn cần quản lý số lượng lớn thread.

**`java.nio.channels.Selector`** của Java NIO giải quyết phần **theo dõi sự sẵn sàng I/O** bằng **I/O multiplexing**: một hoặc vài event-loop thread có thể đăng ký nhiều channel ở chế độ non-blocking, rồi chờ hệ điều hành thông báo **channel nào đang sẵn sàng accept/connect/read/write**. Chỉ các channel có sự kiện đáng xử lý mới được đưa ra vòng xử lý.

Bài này trình bày từ bài toán blocking, kiến trúc selector, `SelectionKey` và interest/ready sets, đến một chương trình Java 17+ có **ba TCP client hoạt động đồng thời nhưng một server event loop**. Mục tiêu là hiểu cơ chế, các giới hạn và cách dùng đúng trong ứng dụng mạng thật.

## 1. Vì sao theo dõi nhiều kết nối bằng I/O blocking gặp khó?

Giả sử server cần giữ kết nối TCP với 10.000 client. Phần lớn đang online nhưng chưa gửi dữ liệu. Với cách **mỗi kết nối một thread**, mỗi thread có thể đứng chờ:

~~~java
// Ý tưởng blocking: đây chỉ là snippet, không phải server hoàn chỉnh.
Socket client = serverSocket.accept();
InputStream in = client.getInputStream();
int value = in.read(); // Chặn cho đến khi có dữ liệu, EOF hoặc lỗi.
~~~

Nếu dùng một thread duy nhất để xử lý tuần tự, khi client đầu tiên chưa gửi gì thì các client khác có thể bị bỏ chờ. Nếu tạo thread riêng cho mọi client, có thể tăng mức song song, nhưng mỗi thread cần stack, metadata, scheduler bookkeeping và chi phí chuyển ngữ cảnh. Quy mô tối đa còn tùy CPU/RAM/OS và mô hình thread của Java.

Đặt cạnh nhau:

~~~text
A. Blocking + mỗi client một platform thread

Client A ──> Thread A ───── read() ─── [đang chờ]
Client B ──> Thread B ───── read() ─── [đang chờ]
Client C ──> Thread C ───── read() ─── [đang chờ]
...
Client N ──> Thread N ───── read() ─── [đang chờ]


B. Non-blocking + Selector

Client A ── SocketChannel A ─┐
Client B ── SocketChannel B ─┤
Client C ── SocketChannel C ─┼─> Selector ─> event loop
...                         │                 |
Client N ── SocketChannel N ─┘                 +─ xử lý kênh ready
                                              +─ quay lại select()
~~~

Selector **không** làm một kết nối TCP biến mất, không tự nhận/ghi byte và không “chạy từng client song song” trong một thread. Nó giúp thread **không phải đứng chờ riêng trên từng socket nhàn rỗi**. Khi có readiness, ứng dụng vẫn phải gọi `accept()`, `read()`, `write()` tương ứng.

**Điểm cân bằng:** Đối với một vài kết nối, code blocking có thể đơn giản và đủ tốt. Với hàng nghìn kết nối chủ yếu nhàn rỗi, event-driven NIO có thể giảm nhu cầu thread và overhead. Trong Java mới hơn còn có virtual threads để viết code blocking theo mô hình dễ đọc hơn; lựa chọn công nghệ phải dựa trên tải và yêu cầu cụ thể, không giả định Selector luôn nhanh hơn.

## 2. Selector là bộ chọn “sẵn sàng I/O”, không phải bộ thực thi I/O

Một `Selector` theo dõi các `SelectableChannel` đã đăng ký:

1. Tạo `Selector`, ví dụ `Selector.open()`.
2. Tạo các channel có thể select như `ServerSocketChannel` và `SocketChannel`; cấu hình **non-blocking** bằng `configureBlocking(false)`.
3. Đăng ký channel với Selector bằng `register(selector, interestOps)`. Phương thức trả về một `SelectionKey`.
4. Gọi `selector.select()` hoặc `selector.select(timeout)`. Lúc này thread có thể **ngủ trong một thao tác chờ chung**, thay vì kiểm tra từng socket bằng vòng lặp bận.
5. Khi có sự kiện phù hợp, đọc `selector.selectedKeys()` và xử lý từng key. **Xóa key khỏi selected set sau khi lấy ra xử lý**.
6. Thay `interestOps(...)` khi trạng thái kết nối thay đổi (ví dụ đang có dữ liệu chờ gửi) rồi quay về `select()`.

~~~text
register channels (non-blocking)
            |
            v
       [ Selector ]
            |
            v
      select() waits ───────────┐
            |                  |
   readiness observed           |
            |                  |
            v                  |
       selectedKeys             |
            |                  |
  ACCEPT / CONNECT / READ / WRITE
            |                  |
   thực hiện I/O, cập nhật key  |
            |                  |
            └──────────────────┘
~~~

**Readiness khác completion:** `isReadable()` thông báo channel **có thể** đọc mà không phải chờ dài (hoặc đã đến EOF/lỗi), chứ không chứa sẵn payload của client. Lời gọi `SocketChannel.read(buffer)` vẫn phải thực hiện và **có thể trả 0**, `-1` hoặc số byte dương. Tương tự, `isWritable()` không hứa rằng toàn bộ dữ liệu sẽ được ghi trong một lần.

NIO Selector là mô hình **readiness-based**, khác với một API completion-based trả callback/future sau khi I/O thực sự hoàn tất. Không nên nhầm `Selector` với `ExecutorService`: selector theo dõi I/O, còn executor chạy công việc được giao.

## 3. Các lớp cần biết

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| `Selector` | Theo dõi tập kênh đăng ký và đợi readiness | `Selector.open()`, `select()`, `selectedKeys()` |
| `ServerSocketChannel` | Kênh TCP phía server, nhận kết nối mới | `bind(...)`, `accept()`, `OP_ACCEPT` |
| `SocketChannel` | Kênh TCP của một kết nối | `read(buffer)`, `write(buffer)`, `OP_READ` |
| `SelectionKey` | Token liên kết một channel với một selector và tập thao tác quan tâm | `interestOps(...)`, `isReadable()`, `attach(...)` |
| `ByteBuffer` | Đệm byte có `position`, `limit`, `capacity` | `put`, `flip()`, `compact()`, `clear()` |
| `NetworkChannel` / `SelectableChannel` | Giao diện kênh có thể cấu hình và/hoặc đăng ký | `configureBlocking(false)`, `validOps()` |

**Không phải mọi channel đều có thể đăng ký với Selector.** Ví dụ `FileChannel` không phải `SelectableChannel`; đọc file thông thường có mô hình I/O riêng. Với UDP, `DatagramChannel` có thể dùng Selector để nhận/gửi datagram, nhưng bài toán theo dõi **nhiều kết nối TCP** chủ yếu dùng `ServerSocketChannel` và `SocketChannel`.

Từng channel chỉ được đăng ký với các operation mà `validOps()` cho phép; dùng sai operation có thể ném `IllegalArgumentException`. `ServerSocketChannel` chỉ hỗ trợ `OP_ACCEPT`, còn `SocketChannel` hỗ trợ `OP_CONNECT`, `OP_READ`, `OP_WRITE`. Trước khi register, channel phải ở **non-blocking mode**, nếu không có thể ném `IllegalBlockingModeException`.

## 4. OP_ACCEPT, OP_CONNECT, OP_READ, OP_WRITE

| Operation | Channel thường dùng | Khi nào quan tâm? | Hành động sau readiness |
| --- | --- | --- | --- |
| `SelectionKey.OP_ACCEPT` | `ServerSocketChannel` | Server đang lắng nghe kết nối mới | Gọi `accept()`; cấu hình socket mới non-blocking và register |
| `SelectionKey.OP_CONNECT` | `SocketChannel` | Client bắt đầu kết nối non-blocking nhưng chưa hoàn thành | Gọi `finishConnect()`; nếu thành công chuyển sang OP_READ/OP_WRITE phù hợp |
| `SelectionKey.OP_READ` | `SocketChannel` | Muốn biết khi nào đọc có thể tiến triển hoặc có EOF/lỗi | Gọi `read(buffer)`; xử lý số byte trả về |
| `SelectionKey.OP_WRITE` | `SocketChannel` | **Có dữ liệu đang chờ ghi** sau lần ghi chưa hết | Gọi `write(buffer)`; theo dõi `buffer.hasRemaining()` |

**Bảng trên mô tả thao tác quan tâm, không khẳng định selector “đã làm” các thao tác đó.** Ví dụ một kênh được báo `OP_ACCEPT` vẫn cần `accept()`; vì kênh non-blocking nên `accept()` có thể trả `null` nếu không còn kết nối đang chờ.

### Tại sao không luôn đăng ký OP_WRITE?

Ở TCP, socket thường **sẵn sàng ghi** khi kernel send buffer còn chỗ. Nếu luôn giữ `OP_WRITE` trong interest set ngay cả khi **không có dữ liệu cần gửi**, `select()` có thể trả về liên tục, khiến CPU bận (busy loop).

Phương án thường dùng:

~~~text
Mới kết nối:
    interestOps = OP_READ

Đã đọc request, có ByteBuffer phản hồi cần gửi:
    interestOps = OP_WRITE  (hoặc OP_READ | OP_WRITE
                            nếu có hàng đợi và backpressure phù hợp)

Khi ghi hết buffer:
    interestOps = OP_READ   (bỏ OP_WRITE)
~~~

Trong demo dưới đây, để giới hạn bộ nhớ đơn giản, ta **tạm ngừng quan tâm OP_READ** khi đang có dữ liệu echo chưa gửi xong. Mỗi kết nối chỉ giữ **một ByteBuffer pending**. Đây là một dạng backpressure cơ bản; server production có thể cần queue có giới hạn, fairness và protocol framing.

## 5. SelectionKey: interest set, ready set, selected set, attachment

Mỗi lần đăng ký channel với Selector sẽ tạo một `SelectionKey` để theo dõi quan hệ đó. Key có vài ý nghĩa thường bị nhầm:

**Interest set** là tập operation ứng dụng **muốn được thông báo**, đặt bằng:

~~~java
key.interestOps(SelectionKey.OP_READ);
key.interestOps(SelectionKey.OP_READ | SelectionKey.OP_WRITE);
~~~

**Ready set** là tập operation selector **phát hiện sẵn sàng** trong lần lựa chọn, có thể đọc bằng `readyOps()` hoặc các helper `isAcceptable()`, `isConnectable()`, `isReadable()`, `isWritable()`. Một key có thể có nhiều ready flags nếu interest set chứa nhiều operation.

**Selected-key set** là `selector.selectedKeys()`. Bộ này chứa các key đã được selector chọn; nó **không phải** danh sách tự động rỗng sau mỗi lượt. Vòng lặp đúng nên chủ động gọi `iterator.remove()`:

~~~java
Iterator<SelectionKey> it = selector.selectedKeys().iterator();
while (it.hasNext()) {
    SelectionKey key = it.next();
    it.remove();                 // Rất quan trọng.
    if (!key.isValid()) {
        continue;
    }
    // Xử lý các readiness flags.
}
~~~

Đây là snippet trong event loop, cần import `Iterator` và `SelectionKey`. Nếu quên `remove()`, cùng một key có thể tiếp tục nằm trong selected set qua các lượt và gây xử lý lại hoặc hành vi khó đoán. Không gọi `add(key)` trực tiếp vào selected set: set này do selector quản lý.

**Attachment** là dữ liệu **riêng của một kết nối**, gắn vào key:

~~~java
key.attach(connectionState);
Object state = key.attachment();
~~~

Ví dụ `connectionState` có thể lưu receive buffer, output queue, parser state, request ID, last activity time, số byte chưa gửi. Đừng giữ một `ByteBuffer` dùng chung cho mọi client rồi sửa qua lại, vì dữ liệu của các kết nối có thể bị trộn hoặc bị ghi đè.

**Vòng đời:** `key.cancel()` đánh dấu hủy đăng ký; thường nên đóng channel khi kết nối hoàn tất hoặc lỗi. Key có thể bị invalid khi channel bị đóng. Do readiness và trạng thái có thể đổi giữa `select()` và handler, hãy kiểm tra `key.isValid()` trước khi thao tác; có thể cần xử lý `CancelledKeyException` trong code có thay đổi key ở nhiều nơi.

## 6. Ví dụ Java 17+: một Selector theo dõi ba kết nối TCP

Để thấy lợi ích mà không cần mở hai terminal hay chọn trước một port cố định, ví dụ này thực hiện tất cả trong **một chương trình**:

- Một `ServerSocketChannel` bind `127.0.0.1:0`. Port 0 nghĩa là hệ điều hành tự chọn port trống.
- Server đăng ký `OP_ACCEPT` với **một Selector** và chạy **event loop trong main thread**.
- Ba client được tạo đồng thời bởi `ExecutorService` chỉ để sinh tải kiểm thử. Chúng **không phải** ba server worker thread.
- Mỗi client gửi một chuỗi ngắn và chờ server echo lại. Server chấp nhận nhiều kết nối, đọc từng phần byte, giữ buffer chờ gửi trên key và chuyển giữa `OP_READ` / `OP_WRITE`.
- Khi cả ba client đã nhận echo, đóng kết nối và server thấy EOF của cả ba, event loop dừng. Chương trình in kết quả theo thứ tự Future, vì thứ tự readiness trên mạng không có bảo đảm.

Tạo **`SelectorManyClientsDemo.java`**:

~~~java
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.ByteBuffer;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Iterator;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class SelectorManyClientsDemo {
    // Client chỉ dùng để tạo tải thử; phần server là NIO event loop.
    private static String client(int port, int id) throws IOException {
        String text = "client-" + id;
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);

        try (Socket socket = new Socket("127.0.0.1", port)) {
            socket.setSoTimeout(3000);
            socket.getOutputStream().write(bytes);

            // Client biết trước số byte echo nên dùng readNBytes.
            byte[] echo = socket.getInputStream().readNBytes(bytes.length);
            if (!Arrays.equals(bytes, echo)) {
                throw new IOException("Unexpected echo");
            }
            return new String(echo, StandardCharsets.UTF_8);
        }
    }

    private static void close(SelectionKey key) {
        key.cancel();
        try {
            key.channel().close();
        } catch (IOException ignored) {
            // Chỉ dọn tài nguyên trong demo.
        }
    }

    private static int handle(
            SelectionKey key, Selector selector) throws IOException {

        if (key.isAcceptable()) {
            ServerSocketChannel server = (ServerSocketChannel) key.channel();
            SocketChannel accepted;

            // Non-blocking accept: null nghĩa là không còn kết nối chờ.
            while ((accepted = server.accept()) != null) {
                accepted.configureBlocking(false);
                accepted.register(selector, SelectionKey.OP_READ);
            }
            return 0;
        }

        SocketChannel socket = (SocketChannel) key.channel();

        if (key.isReadable()) {
            ByteBuffer incoming = ByteBuffer.allocate(1024);
            int n = socket.read(incoming);

            if (n == -1) {
                close(key);         // Client đóng input (EOF).
                return 1;
            }
            if (n > 0) {
                incoming.flip();    // Chuẩn bị đọc byte từ buffer.
                key.attach(incoming);
                key.interestOps(SelectionKey.OP_WRITE);
            }
        } else if (key.isWritable()) {
            ByteBuffer pending = (ByteBuffer) key.attachment();
            socket.write(pending);  // Có thể ghi một phần, hoặc 0 byte.

            if (!pending.hasRemaining()) {
                key.attach(null);
                key.interestOps(SelectionKey.OP_READ);
            }
        }

        return 0;
    }

    public static void main(String[] args) throws Exception {
        ExecutorService clients = Executors.newFixedThreadPool(3);

        try (Selector selector = Selector.open();
             ServerSocketChannel server = ServerSocketChannel.open()) {

            server.configureBlocking(false);
            server.bind(new InetSocketAddress("127.0.0.1", 0));
            server.register(selector, SelectionKey.OP_ACCEPT);

            int port = ((InetSocketAddress)
                    server.getLocalAddress()).getPort();

            List<Future<String>> replies = new ArrayList<>();
            for (int id = 1; id <= 3; id++) {
                int clientId = id;
                replies.add(clients.submit(
                        () -> client(port, clientId)));
            }

            int closedClients = 0;
            long deadline = System.nanoTime()
                    + TimeUnit.SECONDS.toNanos(10);

            while (closedClients < 3
                    && System.nanoTime() < deadline) {

                selector.select(100);
                Iterator<SelectionKey> it =
                        selector.selectedKeys().iterator();

                while (it.hasNext()) {
                    SelectionKey key = it.next();
                    it.remove();

                    if (!key.isValid()) {
                        continue;
                    }

                    if (key.isAcceptable()) {
                        closedClients += handle(key, selector);
                    } else {
                        try {
                            closedClients += handle(key, selector);
                        } catch (IOException e) {
                            close(key);
                            throw e;
                        }
                    }
                }
            }

            if (closedClients != 3) {
                throw new IOException("Timed out");
            }

            // Future được duyệt theo thứ tự submit, dù sự kiện I/O xen kẽ.
            for (Future<String> future : replies) {
                System.out.println("Echo: " + future.get());
            }
        } finally {
            clients.shutdownNow();
        }
    }
}
~~~

Chạy trên JDK 17+:

~~~bash
javac -encoding UTF-8 SelectorManyClientsDemo.java
java SelectorManyClientsDemo
~~~

**Kết quả trên máy có TCP loopback hoạt động bình thường:**

~~~text
Echo: client-1
Echo: client-2
Echo: client-3
~~~

Đây là chương trình chạy có thời hạn, **không phải dịch vụ production**. Nếu môi trường cấm kết nối TCP loopback, quá tải hoặc timeout, nó có thể ném exception thay vì in ba dòng. Ví dụ dùng `127.0.0.1` để không phải giải quyết DNS và dùng port 0 để tránh xung đột cổng cứng.

### Điều gì thực sự diễn ra khi chạy?

1. `server.register(selector, OP_ACCEPT)` không accept ngay; nó chỉ đăng ký để hỏi “khi nào có client chờ accept?”.
2. Ba client được tạo đồng thời, mỗi client connect đến port do hệ điều hành cấp và gửi các byte của `client-n`.
3. `selector.select(100)` chờ tối đa 100ms cho readiness. Chỉ những key sẵn sàng cần được xử lý, không có một server thread riêng cho từng connection.
4. Khi key **acceptable**, `server.accept()` trả về một `SocketChannel`. Server cấu hình channel mới ở non-blocking mode và đăng ký `OP_READ`. Vòng `while (accept() != null)` giúp lấy hết các kết nối đang chờ trong lượt đó.
5. Khi một client key **readable**, `socket.read(incoming)` trả số byte mới có; `-1` nghĩa là EOF. Nếu có byte, code gọi `flip()` rồi gắn buffer làm attachment của **chính key đó**.
6. Server đổi interest thành `OP_WRITE` để gửi lại byte. Trong giai đoạn đang echo, nó không tiếp tục đọc cùng client, nên không có queue vô hạn.
7. Ở sự kiện **writable**, `socket.write(pending)` có thể chỉ ghi một phần. Nếu buffer chưa hết thì giữ `OP_WRITE`; nếu hết thì `attach(null)` và chuyển về `OP_READ`.
8. Client đọc số byte mình đã gửi, so sánh chính xác rồi đóng socket; server cuối cùng đọc EOF trên cả ba connection và kết thúc.
9. Main thread duyệt danh sách `Future` theo thứ tự đăng ký để in output cố định. **Thứ tự accept/read/write thực tế có thể khác.**

Điểm quan trọng nhất: **một server event loop đã phục vụ ba TCP connection bằng readiness**, còn thread pool chỉ đại diện cho ba client giả lập. Với N lớn, cùng cơ chế có thể theo dõi nhiều socket hơn mà không phải cấp một platform thread riêng cho mỗi kết nối.

## 7. Giải thích bộ đệm, partial I/O và ranh giới thông điệp

**TCP là byte stream, không có ranh giới message** theo từng lần `write()`. Client gửi `"client-1"` một lần không bảo đảm server nhận đủ tám byte trong một lần `read()`. Ví dụ đã xử lý điều này bằng cách echo **mỗi chunk nhận được** và để client ghép đủ số byte đã biết trước bằng `readNBytes(bytes.length)`.

Một `SocketChannel.read(ByteBuffer)` non-blocking trả:
- **`n > 0`:** đã đọc được `n` byte. Dữ liệu nằm trong buffer từ vị trí trước khi đọc tới vị trí mới.
- **`n == 0`:** chưa có byte để đọc ngay; không quay vòng vô hạn trong handler.
- **`n == -1`:** đầu vào của stream đã ở EOF (ví dụ peer đã đóng hoặc shutdown output); xử lý lifecycle/half-close theo giao thức.

Tương tự `SocketChannel.write(buffer)` có thể ghi 0, một phần hoặc hết số byte còn lại. Vì thế đoạn sau là **sai logic** nếu xem như đã gửi toàn bộ:

~~~java
socket.write(buffer);           // Có thể chưa gửi hết.
key.interestOps(SelectionKey.OP_READ); // Sai nếu buffer.hasRemaining().
~~~

Cách đúng trong ví dụ:

~~~java
socket.write(buffer);
if (buffer.hasRemaining()) {
    key.interestOps(SelectionKey.OP_WRITE);
} else {
    key.interestOps(SelectionKey.OP_READ);
}
~~~

Đây là các snippet minh họa, giả định `socket`, `key` và `buffer` đã được cấu hình.

### ByteBuffer có position, limit, capacity

`ByteBuffer` không chỉ là mảng byte. Có ba trạng thái:
- **capacity:** tổng dung lượng.
- **position:** vị trí thao tác tiếp theo.
- **limit:** giới hạn vùng có thể đọc/ghi.

Vòng đời điển hình:

~~~text
buffer = ByteBuffer.allocate(8)

Khi nhận từ socket:
    [a b c . . . . .]
         ^ position = 3
    limit = 8

flip(): chuyển sang chế độ đọc
    [a b c . . . . .]
     ^ position = 0
           ^ limit = 3

write(buffer): gửi đến khi position == limit
    [a b c . . . . .]
           ^ position = 3
           ^ limit = 3

clear(): position = 0, limit = capacity
    (không xóa vật lý từng byte cũ)
~~~

Trong một parser nhận message dạng có length header hoặc delimiter, có thể cần giữ byte cuối chưa đủ thành một frame bằng `compact()`, sau đó đọc tiếp. Không ép mỗi lần `read` phải là một message độc lập. Nếu giải mã Unicode UTF-8 khi chưa đủ byte, một code point có thể bị cắt giữa các lần đọc; hãy giữ state của decoder hoặc đợi frame hoàn chỉnh.

Mẫu framing thường gặp:
- **Length-prefix:** đọc đủ header (ví dụ 4 byte độ dài), validate kích thước, rồi đọc đủ payload.
- **Delimiter:** đọc tới ký tự phân cách, ví dụ newline, nhưng giới hạn chiều dài để tránh client gửi mãi không có delimiter.
- **Protocol có sẵn:** HTTP/WebSocket/RPC có grammar riêng; không dùng phép “mỗi read = một request”.

## 8. Vì sao phải giữ trạng thái riêng cho từng kết nối?

Trong blocking code, nhiều trạng thái nằm trong stack của thread client. Trong NIO event loop, handler của client A chỉ chạy một lúc rồi trở về selector; lần sau có thể xử lý client B rồi quay lại A. Do đó trạng thái phải được **lưu bền giữa các lần readiness**.

Một state production có thể gồm:

~~~java
// Kiểu minh họa, không phải chương trình độc lập.
final class ConnectionState {
    final ByteBuffer input = ByteBuffer.allocate(8192);
    final java.util.ArrayDeque<ByteBuffer> outputQueue =
            new java.util.ArrayDeque<>();

    long lastActivityNanos;
    boolean outputShutdownRequested;
}
~~~

Có thể đăng ký state ngay khi accept:

~~~java
client.register(selector, SelectionKey.OP_READ, new ConnectionState());
~~~

Đây là snippet; constructor cần `selector` đã mở và `client.configureBlocking(false)` trước đó. Handler lấy lại bằng `(ConnectionState) key.attachment()`.

Trong demo, attachment đơn giản là một `ByteBuffer` pending duy nhất:
- `null`: đang quan tâm read, chưa có dữ liệu echo chờ gửi.
- `ByteBuffer` không rỗng: đang quan tâm write, cần giữ position giữa những lần ghi.
- Khi buffer đã gửi hết: `attach(null)` để giải phóng tham chiếu rồi quay lại read.

**Bộ nhớ phải có giới hạn.** Nếu người dùng gửi dữ liệu nhanh hơn tốc độ network ghi trả, việc thêm mọi dữ liệu vào output queue không giới hạn có thể gây out-of-memory. Cách thường dùng là high/low-water marks để tạm bỏ `OP_READ` khi pending bytes vượt ngưỡng, rồi bật lại khi đã drain. Trong demo, mỗi connection chỉ giữ một buffer 1024 byte pending, nên code dễ nhìn và tự tạo backpressure, nhưng throughput có thể thấp vì ngừng đọc trong lúc trả lời.

## 9. OP_CONNECT: theo dõi kết nối outbound non-blocking

Server ở ví dụ chỉ dùng `OP_ACCEPT`, `OP_READ`, `OP_WRITE`. Đối với ứng dụng **chủ động kết nối** bằng `SocketChannel` non-blocking, cần thêm `OP_CONNECT`.

Ý tưởng (snippet, không phải chương trình hoàn chỉnh):

~~~java
SocketChannel client = SocketChannel.open();
client.configureBlocking(false);

boolean connected =
        client.connect(new InetSocketAddress("127.0.0.1", 9090));

if (connected) {
    client.register(selector, SelectionKey.OP_READ);
} else {
    client.register(selector, SelectionKey.OP_CONNECT);
}

// Trong event loop, sau khi nhận key connectable:
if (key.isConnectable()) {
    SocketChannel channel = (SocketChannel) key.channel();
    if (channel.finishConnect()) {
        key.interestOps(SelectionKey.OP_READ);
    }
}
~~~

Các biến `selector` và `key` trong snippet phải nằm trong event loop đang quản lý channel tương ứng. `connect(...)` có thể trả `true` nếu kết nối hoàn tất ngay, hoặc `false` nếu đang chờ. Khi `OP_CONNECT` sẵn sàng, **vẫn phải gọi `finishConnect()`**; không chuyển qua đọc/ghi như thể kết nối đã hoàn thành mà không xác minh.

Nếu kết nối thất bại, `finishConnect()` hoặc thao tác liên quan có thể ném `IOException`; xử lý và đóng key/channel. Tùy implementation có thể có lỗi chờ kết nối. Một `ServerSocketChannel` không có `OP_CONNECT`; nó được dùng để accept.

## 10. Các cách select, wakeup và tránh vòng lặp CPU

| API | Cách chờ | Khi phù hợp |
| --- | --- | --- |
| `selector.select()` | Chờ cho đến khi có readiness, wakeup hoặc interrupt theo semantics API | Event loop thường xuyên chờ I/O |
| `selector.select(timeoutMillis)` | Chờ tối đa số mili giây dương trước khi trả về | Có timer / deadline / housekeeping |
| `selector.selectNow()` | Trả về ngay, kể cả không có kênh ready | Poll chủ động trong vòng lập kế hoạch đã thiết kế |
| `selector.wakeup()` | Yêu cầu thao tác select đang/sắp chờ trở về | Một thread khác cần event loop cập nhật đăng ký/nhiệm vụ |

**Lưu ý:** Trong `select(long timeout)`, **timeout = 0 có ngữ nghĩa chờ không giới hạn như `select()`**, không phải “đợi 0ms rồi trả về”. Muốn không block, dùng `selectNow()`. `select(100)` trong demo là timeout 100ms, giúp chương trình kiểm tra deadline mỗi lượt; code server lâu dài thường dùng `select()` với cơ chế wakeup/timer chính xác.

Một event loop mẫu cho production (pseudo code):

~~~text
while running:
    applyPendingRegistrationsAndTasks()
    selector.select(nextTimerDeadline)
    for each key in selectedKeys:
        remove key from selected set
        if valid:
            handleReadyOperations(key)
    runExpiredTimersAndHousekeeping()
~~~

**Vấn đề cross-thread:** Nếu thread phụ tạo hoặc thay interestOps của channel trong lúc event loop đang `select()`, cần quy ước ownership và đồng bộ phù hợp. Mẫu an toàn thường là thread phụ đẩy yêu cầu vào một queue, gọi `selector.wakeup()`, rồi event-loop thread lấy queue và thực hiện `register()/interestOps()`. Không tùy tiện để nhiều thread cùng chỉnh cấu trúc và attachment mà không có synchronization.

**Busy spin:** Nếu `selectNow()` được gọi lặp vô hạn khi chưa có dữ liệu, hoặc `OP_WRITE` luôn được quan tâm dù output queue trống, CPU có thể tăng cao. Hãy ưu tiên block chờ readiness khi nhàn rỗi và chỉ bật OP_WRITE khi thật sự có byte chờ gửi.

## 11. Một Selector có bao nhiêu thread, và nó có thật sự xử lý song song?

Một Selector có thể được dùng bởi một event-loop thread, hoặc kết hợp nhiều selector và event-loop thread. **Multiplexing không đồng nghĩa parallel execution**. Trong một loop đơn:
- Chỉ **một callback/handler** chạy tại một thời điểm trên event-loop thread.
- Nhiều socket khác nhau được phục vụ **xen kẽ** khi sẵn sàng.
- Công việc CPU tốn thời gian, truy vấn database blocking, I/O file blocking, tra cứu DNS đồng bộ hoặc `Thread.sleep(...)` trong handler sẽ chặn **toàn bộ event loop**.

Một thiết kế phục vụ nhiều client thường tách:

~~~text
                          acceptor selector (tùy thiết kế)
                                   |
                        1..N selector event loops
                                   |
                    read/parse nhanh, ghi non-blocking
                                   |
                   queue bounded / worker executor
                                   |
                      business logic hoặc storage
                                   |
                    queue kết quả về event loop
                                   |
                           wakeup(), OP_WRITE
~~~

Không nhất thiết ứng dụng nào cũng cần sơ đồ phức tạp này. Với handler rất nhanh, một event loop có thể đủ; với việc xử lý CPU/DB lâu, có thể chuyển phần chậm sang executor, **kèm giới hạn hàng đợi và backpressure**. Nhiều framework event-driven hiện đại xây trên mô hình tương tự, nhưng lựa chọn thread model và cách phân phối channel giữa các selector khác nhau.

Chi phí vận hành không biến mất: vẫn cần file descriptors/socket resources, buffer, state per client, timer, cleanup, bảo mật và giới hạn kết nối. “10.000 kết nối” cũng **không tự động** đồng nghĩa “10.000 request/giây”.

## 12. Readiness không bảo đảm thao tác thành công ngay

Selector thường dùng hạ tầng polling/event notification của hệ điều hành (tùy platform/provider) để phát hiện readiness. Readiness chỉ là **gợi ý hiện tại**, có thể đổi trước khi ứng dụng thao tác.

Những trường hợp phải xử lý:
1. `OP_READ` được báo nhưng `read` trả **0 byte** trong non-blocking mode.
2. `OP_READ` được báo vì peer đóng output, nên `read` trả **-1 EOF**; đây không phải packet dữ liệu.
3. `OP_WRITE` được báo, nhưng `write` chỉ nhận một phần hoặc **0 byte** nếu send buffer không còn chỗ tại thời điểm gọi.
4. `OP_ACCEPT` được báo, nhưng một lần `accept()` sau đó có thể trả `null` vì không còn pending connection.
5. Một `SelectionKey` có thể bị hủy giữa lúc chọn và xử lý; kiểm tra validity, phân biệt channel close với key cancel.
6. `select()` có thể trả về **0**, ví dụ do wakeup, interrupt hoặc timeout; không coi đó là một client lỗi.

Chính vì vậy code event-driven cần branch đầy đủ theo return value và lưu trạng thái. Nếu một thao tác ghi dở, phần chưa ghi nằm trong `ByteBuffer`; nếu một khung protocol chưa đọc đủ, parser phải giữ byte/state cho lần sau.

## 13. Vòng đời kết nối và dọn tài nguyên

Với TCP và Selector, khởi tạo và đóng là trách nhiệm của ứng dụng:

- Khi accept được client, cấu hình non-blocking trước khi register, có thể gắn connection state, timeout policy, request limits.
- Khi gặp EOF `read() == -1`, decide đóng channel ngay hay xử lý **half-close** theo giao thức nếu còn output pending; demo đóng ngay vì client đã nhận echo.
- Khi có `IOException` riêng trên một client, thường chỉ hủy key/đóng channel client đó và tiếp tục phục vụ client khác; đừng để một client hỏng làm sập toàn bộ server.
- Khi shutdown server, ngừng accept, hủy registration, đóng mọi client channel và server channel; sau đó đóng selector. **Đóng Selector không tự động thay việc đóng tất cả registered channels**.
- Việc hủy key có thể được xử lý khi selector chạy vòng select tiếp theo; code phải tránh sử dụng key không còn valid.
- Đặt idle timeout/heartbeat, giới hạn connection và pending bytes nếu server giữ rất nhiều kết nối nhàn rỗi.

Demo cố ý chạy có deadline và dừng sau khi đọc EOF ba client. Nó không phải server production chạy mãi và không chứa toàn bộ logic shutdown/cancel tasks khi gặp lỗi bất thường. Thiết kế production nên dọn các channel đã accept ngay cả khi event loop thoát vì exception.

## 14. Selector có phù hợp mọi bài toán không?

| Tình huống | Có nên cân nhắc Selector? | Lý do |
| --- | --- | --- |
| Rất nhiều socket TCP giữ kết nối nhưng thường nhàn rỗi | Có | Một event loop có thể chờ readiness của nhiều channel |
| Chat server, gateway, proxy cần read/write non-blocking | Có | Phù hợp event-driven với per-connection state |
| Client đơn giản vài kết nối, I/O blocking đọc được rõ ràng | Có thể không cần | API blocking dễ lập trình hơn, overhead thấp ở quy mô nhỏ |
| Công việc xử lý mỗi request nặng CPU, gọi DB blocking | Chỉ dùng Selector cho I/O | Phải offload việc chậm hoặc chọn kiến trúc khác |
| Cần xử lý file channel bằng Selector | Không trực tiếp | `FileChannel` không phải `SelectableChannel` |
| Dùng Java 21+ với virtual threads | Cân nhắc so sánh | Virtual threads giúp thread-per-request dễ viết hơn nhưng không thay mọi chính sách backpressure |
| Muốn tự động đảm bảo protocol framing, retransmit hay authentication | Không đủ | Selector chỉ là cơ chế readiness, không phải protocol framework |

Các thư viện NIO như Netty, Grizzly hoặc server framework thường đóng gói rất nhiều chi tiết về buffer, framing, lifecycle, timeouts và backpressure. Cần hiểu Selector để phân tích behavior và debug; không nhất thiết phải viết tay event loop cho một sản phẩm production.

## 15. Các lỗi phổ biến

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Register khi channel còn blocking | Có thể ném `IllegalBlockingModeException` | `configureBlocking(false)` trước |
| Register sai operation với loại channel | `IllegalArgumentException` / không đúng chức năng | Kiểm tra `validOps()` |
| Không gọi `iterator.remove()` với selected key | Key đã xử lý có thể nằm lại trong selected set | Remove ngay trong vòng lặp |
| Dùng `if(isReadable())` rồi luôn giải mã một message hoàn chỉnh | TCP có thể trả một phần, ghép nhiều message | Thiết kế framing và parser state |
| Giả định một lần `write` gửi hết | Còn dữ liệu trong buffer bị bỏ quên | Kiểm tra `hasRemaining()`, giữ OP_WRITE khi cần |
| Luôn đăng ký OP_WRITE khi queue trống | Busy spin và CPU tăng | Chỉ bật OP_WRITE khi có pending bytes |
| Không có state per client | Dữ liệu của các kết nối bị trộn/ghi đè | Attachment hoặc map state theo key |
| Queue output không giới hạn | OOM khi client chậm đọc | Backpressure/high-water marks, giới hạn bộ nhớ |
| Handler chạy SQL/blocking I/O lâu | Chặn toàn event loop | Tách tác vụ blocking/CPU sang worker pool |
| `read() == 0` bị coi là EOF | Đóng nhầm client | EOF chỉ khi trả `-1` |
| Không xử lý `read() == -1` | Socket chết còn nằm trong selector | Hủy key/đóng hoặc xử lý half-close |
| Quên `finishConnect()` sau OP_CONNECT | Socket chưa hoàn tất connect mà bị đọc/ghi | Hoàn tất rồi đổi interest set |
| Gọi `select(0)` để không block | Thực tế có thể chờ vô hạn | Dùng `selectNow()` |
| Thay interestOps từ thread khác mà không wakeup/đồng bộ | Event loop có thể không nhận thay đổi kịp hoặc bị race | Queue task cho loop + `selector.wakeup()` |
| Chỉ đóng Selector khi server dừng | Channel đã đăng ký có thể vẫn mở | Đóng các channel và selector theo lifecycle |

## 16. Tự kiểm tra kiến thức

**1.** Một thread gọi `selector.select()` để chờ 5.000 `SocketChannel`. Điều này có nghĩa 5.000 client được xử lý song song không?  
**Đáp án:** Không. Nó theo dõi readiness của nhiều channel; event-loop thread xử lý lần lượt những channel ready, có thể xen kẽ các kết nối.

**2.** Khác nhau giữa **interest set** và **ready set** của `SelectionKey`?  
**Đáp án:** Interest là operation ứng dụng muốn quan tâm, còn ready là operation selector phát hiện sẵn sàng ở lượt lựa chọn hiện tại.

**3.** Tại sao selected key phải được `iterator.remove()`?  
**Đáp án:** Selected set không tự xóa toàn bộ key đã xử lý sau một vòng lặp; loại bỏ giúp tránh xử lý lại không chủ định.

**4.** Vì sao không bật `OP_WRITE` suốt thời gian socket tồn tại?  
**Đáp án:** Socket thường writable khi kernel buffer còn chỗ, nên có thể khiến selector liên tục đánh thức event loop mặc dù ứng dụng không có dữ liệu để gửi.

**5.** `read(buffer) == 0` và `== -1` khác nhau như thế nào?  
**Đáp án:** 0 là chưa đọc được byte ngay lúc đó, -1 là EOF của input stream.

**6.** Client gửi 100 byte bằng một lệnh `write()` thì server có chắc sẽ nhận đủ 100 byte trong một lệnh `read()` không?  
**Đáp án:** Không. TCP là byte stream; phải tích lũy theo framing hoặc độ dài đã biết.

**7.** Vì sao demo dùng `key.attach(ByteBuffer)`?  
**Đáp án:** Để giữ phần dữ liệu trả lời chưa gửi hết của **từng kết nối**, không mất `ByteBuffer.position` giữa các lần được báo writable.

**8.** Đăng ký `OP_CONNECT` cho `ServerSocketChannel` đúng không?  
**Đáp án:** Không. `ServerSocketChannel` chỉ hỗ trợ `OP_ACCEPT`. `SocketChannel` outbound non-blocking mới dùng `OP_CONNECT`.

**9.** Làm sao tránh một client chậm đọc khiến server dùng quá nhiều RAM?  
**Đáp án:** Giới hạn pending output/buffers và tạm giảm hoặc tắt read interest khi vượt ngưỡng; bật lại khi đã drain.

**10.** Tại sao selector thread không nên gọi truy vấn database blocking?  
**Đáp án:** Vì trong thời gian DB chờ, cả event loop không thể xử lý những socket khác, làm độ trễ tăng dù readiness đã có.

## Tham khảo Java API và NIO chính thức

- [Java SE 17 — `java.nio.channels` package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/package-summary.html): mô hình multiplexed, non-blocking I/O.
- [Java SE 17 — Selector](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html): `select`, selected-key set và `wakeup`.
- [Java SE 17 — SelectionKey](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectionKey.html): interest set/ready set, OP_* và attachment.
- [Java SE 17 — SocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html), [ServerSocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ServerSocketChannel.html): read/write/accept và non-blocking behavior.
- [Java SE 17 — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): position, limit, flip, compact và buffer lifecycle.
