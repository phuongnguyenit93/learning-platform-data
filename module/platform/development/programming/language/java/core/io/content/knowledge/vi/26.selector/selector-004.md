# Selector: OP_ACCEPT, OP_CONNECT, OP_READ và OP_WRITE trong Java NIO

## 1. Bốn cờ biểu diễn điều gì?

Trong Java NIO, `java.nio.channels.Selector` giúp một thread theo dõi trạng thái **sẵn sàng thực hiện I/O** của nhiều `SelectableChannel`. Thay vì liên tục gọi `read()` hoặc `write()` trên từng kết nối và tự đoán kết nối nào có thể tiến triển, chương trình đăng ký các sự kiện quan tâm qua `SelectionKey`.

Bốn hằng số được định nghĩa trong `java.nio.channels.SelectionKey`:

| Operation | Giá trị bit | Channel điển hình | Ý nghĩa |
| --- | ---: | --- | --- |
| `OP_ACCEPT` | 16 | `ServerSocketChannel` | Có kết nối đến đang sẵn sàng để `accept()` |
| `OP_CONNECT` | 8 | `SocketChannel` | Kết nối TCP bất đồng bộ đang sẵn sàng để kiểm tra/hoàn tất bằng `finishConnect()` |
| `OP_READ` | 1 | `SocketChannel`, `DatagramChannel`, `Pipe.SourceChannel` | Thao tác đọc có thể tiến triển hoặc phát hiện EOF/lỗi |
| `OP_WRITE` | 4 | `SocketChannel`, `DatagramChannel`, `Pipe.SinkChannel` | Thao tác ghi có thể tiến triển, thường vì có chỗ trong bộ đệm đầu ra |

Các hằng số là **bit flag**, vì vậy có thể kết hợp bằng phép OR bit `|`:

~~~java
int interests = SelectionKey.OP_READ | SelectionKey.OP_WRITE;
~~~

Biểu thức trên yêu cầu theo dõi **cả đọc và ghi**; nó không thực hiện bất kỳ I/O nào. Một thao tác `OP_ACCEPT` không có nghĩa một client đã được trả về; bạn vẫn cần gọi `ServerSocketChannel.accept()`. `OP_CONNECT` không có nghĩa mọi bước kết nối đã hoàn thành; bạn vẫn cần `SocketChannel.finishConnect()` nếu `connect()` trước đó còn pending.

**Quy tắc cốt lõi:** Selector báo **readiness** (khả năng tiến triển), không báo rằng ứng dụng đã đọc, ghi, chấp nhận hay hoàn tất kết nối thay cho bạn.

## 2. Ba tập thao tác: validOps, interestOps và readyOps

Một `SelectionKey` kết nối **một channel** với **một selector**. Muốn hiểu tại sao một cờ được báo hay không, cần tách ba khái niệm:

1. `channel.validOps()`: tập cờ **channel hỗ trợ về mặt loại**. Ví dụ `ServerSocketChannel` hỗ trợ `OP_ACCEPT`; `SocketChannel` hỗ trợ `OP_CONNECT`, `OP_READ` và `OP_WRITE`.
2. `key.interestOps()`: tập cờ **ứng dụng hiện muốn selector giám sát**. Có thể thay đổi bằng `key.interestOps(mask)` khi key còn hợp lệ.
3. `key.readyOps()`: tập cờ mà selector **đã xác định là sẵn sàng** trên key đã được chọn trong lượt selection. Có thể kiểm tra bằng `isAcceptable()`, `isConnectable()`, `isReadable()` và `isWritable()`.

~~~text
channel.validOps()
    │ tập thao tác mà loại channel hỗ trợ
    ▼
key.interestOps()
    │ ứng dụng chọn bit cần theo dõi
    ▼
selector.select()
    │ phát hiện readiness thực tế
    ▼
key.readyOps() / key.isReadable() / ...
    │
    ▼
Ứng dụng tự gọi accept / finishConnect / read / write
~~~

Không phải cứ có `OP_READ` trong `interestOps` là `isReadable()` lập tức trả `true`. Nó chỉ đăng ký ý định quan sát. Ngược lại, `readyOps` không nên được suy luận như tình trạng I/O bất biến: trạng thái mạng có thể thay đổi ngay sau khi selector đánh dấu ready.

### validOps phải khớp channel

| Loại channel | validOps về mặt loại |
| --- | --- |
| `ServerSocketChannel` | `OP_ACCEPT` |
| `SocketChannel` | `OP_CONNECT \| OP_READ \| OP_WRITE` |
| `DatagramChannel` | `OP_READ \| OP_WRITE` |
| `Pipe.SourceChannel` | `OP_READ` |
| `Pipe.SinkChannel` | `OP_WRITE` |

Không đăng ký `OP_ACCEPT` cho `SocketChannel`, cũng không đăng ký `OP_CONNECT` cho `ServerSocketChannel`. Nếu `interestOps` chứa bit không nằm trong `validOps()`, `register(selector, ops)` hay `interestOps(ops)` có thể ném `IllegalArgumentException`.

Có thể kiểm tra:

~~~java
boolean canAccept =
        (serverChannel.validOps() & SelectionKey.OP_ACCEPT) != 0;
~~~

Đây là mảnh code minh họa có biến `serverChannel` đã mở và import `SelectionKey`, không phải chương trình độc lập.

## 3. Điều kiện trước khi đăng ký với Selector

Một `SelectableChannel` phải được đặt **non-blocking mode** trước khi đăng ký selector. Quy trình nền tảng:

~~~java
Selector selector = Selector.open();
ServerSocketChannel server = ServerSocketChannel.open();
server.configureBlocking(false);
server.bind(new InetSocketAddress("127.0.0.1", 0));
SelectionKey serverKey =
        server.register(selector, SelectionKey.OP_ACCEPT);
~~~

Đây là đoạn minh họa trong phương thức có xử lý `IOException` và đóng tài nguyên bằng `try-with-resources`; các import cần dùng thuộc `java.nio.channels` và `java.net`. Cổng `0` yêu cầu hệ điều hành chọn cổng còn trống.

`register(selector, ops)` trả một `SelectionKey`; `key.channel()` là channel đã đăng ký và `key.selector()` là selector tương ứng. Một channel chỉ có **một key trên mỗi selector**, nhưng có thể đăng ký với nhiều selector nếu đáp ứng điều kiện API. Nếu đã đăng ký trên selector đó, đăng ký lại có thể cập nhật interest set và attachment của key hiện có.

Hãy phân biệt:

- **Blocking mode:** lời gọi I/O có thể đợi dữ liệu/khả năng hoàn thành. Không được đăng ký một channel đang blocking với selector; cố làm vậy ném `IllegalBlockingModeException`.
- **Non-blocking mode:** `accept()` có thể trả `null`, `read()` hoặc `write()` có thể trả `0`; chương trình nên xử lý thông qua readiness thay vì bận chờ vô hạn.
- **Selector:** không thực hiện I/O thay ứng dụng, mà cung cấp tập key đã được chọn để ứng dụng điều phối.

Một chương trình vẫn có thể dùng non-blocking channel không có selector; selector có ý nghĩa khi cần quản lý nhiều channel và tránh thao tác hỏi liên tục từng kết nối.

## 4. OP_ACCEPT: nhận kết nối mới

`OP_ACCEPT` dùng với `ServerSocketChannel` đang mở và đã bind tới địa chỉ lắng nghe. Khi key có `isAcceptable() == true`, hãy gọi `accept()`:

~~~java
if (key.isAcceptable()) {
    ServerSocketChannel server =
            (ServerSocketChannel) key.channel();

    SocketChannel client = server.accept();
    if (client != null) {
        client.configureBlocking(false);
        client.register(selector, SelectionKey.OP_READ);
    }
}
~~~

Đây là đoạn nằm **bên trong vòng xử lý selected keys**, giả sử `selector` và `key` đã hợp lệ.

Giải thích:

1. `server` tiếp nhận kết nối; bản thân nó chỉ hỗ trợ `OP_ACCEPT`.
2. `accept()` trả một `SocketChannel` **mới** cho kết nối vừa được chấp nhận, khác với `ServerSocketChannel` đang lắng nghe.
3. Với channel non-blocking, ngay cả sau một thông báo readiness, `accept()` vẫn có thể trả `null` nếu không còn kết nối có thể nhận tại thời điểm gọi.
4. `SocketChannel` vừa nhận phải được cấu hình non-blocking **trước khi register**.
5. Nếu server có thể nhận liên tiếp nhiều kết nối, có thể xử lý nhiều `accept()` trong một lượt với giới hạn hợp lý để không bỏ đói các key khác.

Sau khi accept, dữ liệu của kết nối mới được đọc qua `SocketChannel` và `OP_READ`; không đọc trực tiếp từ `ServerSocketChannel` bằng `OP_READ`.

## 5. OP_CONNECT: hoàn tất kết nối TCP non-blocking

`OP_CONNECT` áp dụng cho **SocketChannel đang thực hiện kết nối chưa hoàn tất**. Quy trình phía client:

~~~java
SocketChannel client = SocketChannel.open();
client.configureBlocking(false);

boolean connected = client.connect(remoteAddress);
if (connected) {
    client.register(selector, SelectionKey.OP_READ);
} else {
    client.register(selector, SelectionKey.OP_CONNECT);
}
~~~

Đây là đoạn minh họa; `remoteAddress` là địa chỉ đích đã xác định, `selector` là Selector đang mở.

Điểm then chốt: `connect(...)` **có thể trả `true` ngay** nếu kết nối hoàn tất tức thì. Khi đó **không cần chờ `OP_CONNECT`**, và có thể đăng ký thẳng `OP_READ`/`OP_WRITE` theo nhu cầu.

Nếu `connect(...)` trả `false`, kết nối còn pending. Khi selector báo `isConnectable()`:

~~~java
if (key.isConnectable()) {
    SocketChannel client = (SocketChannel) key.channel();
    if (client.finishConnect()) {
        key.interestOps(SelectionKey.OP_READ);
    }
}
~~~

`finishConnect()` có thể hoàn tất kết nối, trả `true`, hoặc trả `false` nếu vẫn còn pending trong chế độ non-blocking. Nó cũng có thể ném `IOException` khi kết nối thất bại (ví dụ đích từ chối). Không coi `OP_CONNECT` là bảo đảm kết nối đã thành công.

Sau khi kết nối xong, **thay `OP_CONNECT` bằng những cờ của trạng thái giao thức tiếp theo**. Thường là `OP_READ` nếu cần nhận dữ liệu, hoặc `OP_WRITE` khi có payload cần gửi. Để mãi `OP_CONNECT` trong interest set sau khi đã connected có thể dẫn đến xử lý sự kiện không phù hợp.

## 6. OP_READ: sẵn sàng đọc không đồng nghĩa có đủ một bản tin

`OP_READ` thường xuất hiện khi socket có dữ liệu, đầu bên kia đóng một chiều kết nối hoặc có điều kiện I/O cần ứng dụng xử lý.

~~~java
if (key.isReadable()) {
    SocketChannel channel = (SocketChannel) key.channel();
    ByteBuffer dst = ByteBuffer.allocate(4096);
    int n = channel.read(dst);

    if (n > 0) {
        dst.flip();
        // Tiêu thụ đúng n byte vừa nhận.
    } else if (n == -1) {
        // Peer đã gửi EOF cho chiều đọc này.
        key.cancel();
        channel.close();
    } else {
        // n == 0: chưa có tiến triển; thử lại ở lượt phù hợp.
    }
}
~~~

Đây là mã minh họa, có thể cần thêm cơ chế giữ lại buffer giữa các lần đọc trong ứng dụng thực tế.

Phải phân biệt:

- `n > 0`: có đúng `n` byte mới được đưa vào buffer; buffer `position` đã tăng, nên `flip()` trước khi tiêu thụ.
- `n == 0`: lời gọi chưa chuyển được byte; không được giả định kết nối đã đóng.
- `n == -1`: EOF của channel đọc. Cần quyết định đóng toàn bộ kết nối hay hỗ trợ half-close theo giao thức.
- **Một lần `read` không bảo đảm đủ một HTTP request, một JSON message hay một record ứng dụng.** TCP là luồng byte, không giữ ranh giới bản tin.

Với protocol có header và payload, thường giữ `ByteBuffer` ở attachment của `SelectionKey` hoặc một object connection state. Phân tích các record hoàn chỉnh, sau đó `compact()` để giữ byte còn thiếu và tiếp tục nhận vào lượt kế tiếp. Tránh cấp phát buffer mới rồi vứt dữ liệu chưa phân tích mỗi lần có `OP_READ`.

Readiness chỉ báo cơ hội tiến triển; vì dữ liệu có thể bị một bên khác tiêu thụ hoặc trạng thái thay đổi, lời gọi `read` vẫn cần xử lý giá trị trả về thực tế.

## 7. OP_WRITE: chỉ theo dõi khi thực sự có dữ liệu muốn gửi

`OP_WRITE` báo channel **có khả năng ghi**. Đối với socket TCP thông thường, điều kiện này rất hay đúng do send buffer của hệ điều hành có chỗ. Nếu luôn đăng ký `OP_WRITE` dù không có gì cần gửi, selector có thể liên tục báo writable, khiến vòng lặp tốn CPU.

**Chính sách thường dùng:**

1. Mặc định theo dõi `OP_READ` cho một kết nối đã thiết lập.
2. Khi có dữ liệu cần gửi, đưa dữ liệu vào queue/buffer và thêm `OP_WRITE` vào `interestOps`.
3. Khi selector báo writable, gọi `write` và xử lý số byte ghi thực tế.
4. Nếu còn payload chưa gửi, giữ `OP_WRITE` để tiếp tục ở lượt sau.
5. Khi queue đã rỗng, **bỏ bit `OP_WRITE`** khỏi interest set.

Mảnh code minh họa:

~~~java
if (key.isWritable()) {
    SocketChannel channel = (SocketChannel) key.channel();
    ByteBuffer pending = (ByteBuffer) key.attachment();

    if (pending != null) {
        channel.write(pending);
        if (!pending.hasRemaining()) {
            key.attach(null);
            key.interestOps(key.interestOps() & ~SelectionKey.OP_WRITE);
        }
    }
}
~~~

Đây là mảnh ví dụ giả định attachment chỉ lưu một buffer chờ gửi; trong chương trình thực tế, attachment thường là đối tượng chứa cả inbound buffer, outbound queue và trạng thái giao thức.

`write(ByteBuffer)` **không bảo đảm tiêu thụ hết** payload một lần. Nếu trả `0` hoặc còn `pending.hasRemaining()`, chưa được loại buffer. Chỉ hủy `OP_WRITE` khi dữ liệu đã được gửi hết vào channel (hoặc giao thức chủ động hủy việc gửi).

Để thêm bit ghi mà giữ lại bit đọc:

~~~java
key.interestOps(key.interestOps() | SelectionKey.OP_WRITE);
~~~

Để bỏ bit ghi:

~~~java
key.interestOps(key.interestOps() & ~SelectionKey.OP_WRITE);
~~~

Dấu `|` thêm bit, `& ~` xóa bit có chọn lọc. Không dùng `key.interestOps(OP_WRITE)` nếu vẫn cần theo dõi `OP_READ`: lời gọi setter này thay thế toàn bộ interest set.

## 8. Chu trình xử lý selectedKeys

Một vòng lặp Selector tối thiểu có dạng:

~~~java
while (running) {
    selector.select();

    Iterator<SelectionKey> it = selector.selectedKeys().iterator();
    while (it.hasNext()) {
        SelectionKey key = it.next();
        it.remove();

        if (!key.isValid()) {
            continue;
        }

        if (key.isAcceptable()) {
            // accept() và đăng ký socket được chấp nhận.
        }
        if (key.isConnectable()) {
            // finishConnect(), đổi interest set khi kết nối hoàn tất.
        }
        if (key.isReadable()) {
            // read(), xử lý n > 0, n == 0, n == -1.
        }
        if (key.isWritable()) {
            // write(), tiếp tục dữ liệu dở, bỏ OP_WRITE khi hết.
        }
    }
}
~~~

Đây là **skeleton minh họa**, chưa có khai báo `running`, `selector` hay xử lý ngoại lệ/đóng channel. Trong hệ thống sản xuất cần các điều kiện dừng và quản lý tài nguyên thích hợp.

Những điểm quan trọng:

- `selector.select()` có thể chặn tới khi có key sẵn sàng, có `wakeup()`, bị interrupt hoặc có điều kiện khác theo API. `select(timeout)` cho phép giới hạn thời gian đợi; phải xử lý cả trường hợp trả 0.
- `selectedKeys()` là tập key đã chọn và **không tự được dọn** chỉ vì đã duyệt qua. Dùng `it.remove()` sau khi lấy key.
- `key.isValid()` kiểm tra key còn hợp lệ. Khi hủy key qua `cancel()` hoặc đóng channel, key sẽ không còn dùng được cho các phép kiểm tra readiness.
- `isReadable()` và `isWritable()` có thể cùng đúng trên **một key SocketChannel**, nên code có thể xử lý nhiều điều kiện trong cùng lượt; nếu một nhánh đóng/cancel channel, phải tránh các nhánh sau sử dụng key không còn hợp lệ.
- Trong code chạy thực tế, nên định tuyến theo **loại channel/trạng thái kết nối** và kiểm tra tính hợp lệ sau hành động có thể đóng channel.
- `interestOps` là tập đang theo dõi, trong khi `readyOps` là kết quả select; việc thay interest set không có nghĩa bit ready cũ tự biến thành một lần I/O đã xảy ra.

Một số hệ thống dùng một thread Selector và các worker khác tạo dữ liệu chờ gửi. Khi worker khác thay đổi state, có thể cần `selector.wakeup()` để thread đang đợi select nhận biết thay đổi kịp thời. Tuy vậy, `wakeup()` không thay thế cơ chế đồng bộ của queue hoặc trạng thái chia sẻ giữa các thread.

## 9. Ví dụ Java 17+ chạy độc lập: TCP loopback sử dụng cả bốn cờ

Ví dụ dưới đây tạo một server và một client trong cùng tiến trình, qua địa chỉ loopback và cổng ngẫu nhiên do OS cấp. Chương trình dùng Selector để:

- `OP_ACCEPT`: server chấp nhận socket mới;
- `OP_CONNECT`: client theo dõi hoàn tất kết nối **nếu connect còn pending**;
- `OP_WRITE`: client gửi chuỗi ASCII `PING`, sau đó bỏ interest ghi;
- `OP_READ`: socket phía server đọc đủ bốn byte.

Ví dụ chỉ in kết quả cuối cùng để stdout không phụ thuộc thứ tự các key được selector trả về. `OP_CONNECT` có thể không phát sinh trong lần chạy cụ thể nếu `connect()` hoàn tất ngay; code xử lý đúng cả hai khả năng.

Lưu thành `SelectorOperationsDemo.java`:

~~~java
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

public class SelectorOperationsDemo {
    public static void main(String[] args) throws IOException {
        try (Selector selector = Selector.open();
             ServerSocketChannel server = ServerSocketChannel.open();
             SocketChannel client = SocketChannel.open()) {

            server.configureBlocking(false);
            server.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 0));
            server.register(selector, SelectionKey.OP_ACCEPT);

            client.configureBlocking(false);
            boolean connectedNow = client.connect(server.getLocalAddress());
            client.register(selector, connectedNow
                    ? SelectionKey.OP_WRITE
                    : SelectionKey.OP_CONNECT);

            ByteBuffer outbound = ByteBuffer.wrap(
                    "PING".getBytes(StandardCharsets.US_ASCII));
            ByteBuffer inbound = ByteBuffer.allocate(4);
            SocketChannel accepted = null;
            boolean acceptedConnection = false;

            try {
                long deadline = System.nanoTime()
                        + TimeUnit.SECONDS.toNanos(10);

                while (inbound.hasRemaining()
                        && System.nanoTime() < deadline) {

                    selector.select(250);
                    Iterator<SelectionKey> it =
                            selector.selectedKeys().iterator();

                    while (it.hasNext()) {
                        SelectionKey key = it.next();
                        it.remove();

                        if (!key.isValid()) {
                            continue;
                        }

                        if (key.isAcceptable()) {
                            ServerSocketChannel listener =
                                    (ServerSocketChannel) key.channel();
                            SocketChannel peer = listener.accept();

                            if (peer != null) {
                                peer.configureBlocking(false);
                                peer.register(selector, SelectionKey.OP_READ);
                                accepted = peer;
                                acceptedConnection = true;
                                key.interestOps(0);
                            }
                        } else if (key.isConnectable()) {
                            SocketChannel connecting =
                                    (SocketChannel) key.channel();
                            if (connecting.finishConnect()) {
                                key.interestOps(SelectionKey.OP_WRITE);
                            }
                        } else if (key.isWritable()) {
                            SocketChannel sender =
                                    (SocketChannel) key.channel();
                            sender.write(outbound);

                            if (!outbound.hasRemaining()) {
                                key.interestOps(0);
                            }
                        } else if (key.isReadable()) {
                            SocketChannel receiver =
                                    (SocketChannel) key.channel();
                            int n = receiver.read(inbound);

                            if (n == -1) {
                                throw new EOFException(
                                        "Connection ended before PING");
                            }
                        }
                    }
                }

                if (inbound.hasRemaining()) {
                    throw new IOException("Timed out waiting for PING");
                }

                inbound.flip();
                System.out.println("accepted=" + acceptedConnection);
                System.out.println("connected=" + client.isConnected());
                System.out.println("message="
                        + StandardCharsets.US_ASCII.decode(inbound));
            } finally {
                if (accepted != null) {
                    accepted.close();
                }
            }
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac SelectorOperationsDemo.java
java SelectorOperationsDemo
~~~

Stdout mong đợi khi môi trường cho phép TCP loopback và kết nối/đọc ghi hoàn thành bình thường:

~~~text
accepted=true
connected=true
message=PING
~~~

Lý giải từng giai đoạn:

1. `server` mở ở non-blocking mode, bind loopback, đăng ký `OP_ACCEPT`.
2. `client.connect(...)` có thể trả `true` hoặc `false`. Nếu `true`, client đã nối thành công và đăng ký `OP_WRITE` ngay; nếu `false`, client đăng ký `OP_CONNECT`, sau đó `finishConnect()` chuyển sang `OP_WRITE`.
3. Selector báo `OP_ACCEPT` khi server có kết nối sẵn sàng. `accept()` trả socket `peer` (có thể `null` trong một thời điểm); code đăng ký socket này với `OP_READ`.
4. Khi client có thể ghi, `OP_WRITE` khiến code gửi dần buffer `PING`. Nếu chưa gửi hết, giữ `OP_WRITE`; khi gửi hết, `interestOps(0)` để tránh vòng lặp writable liên tục.
5. `OP_READ` của socket phía server khiến code đọc vào `inbound`. Nếu mới nhận một phần thì buffer vẫn có `remaining()`, vòng lặp tiếp tục chờ.
6. Khi đủ bốn byte, vòng lặp kết thúc và in `PING`. Hai biến boolean mô tả kết nối cuối cùng, không phụ thuộc việc `OP_CONNECT` có xuất hiện hay không.
7. `selectedKeys` được loại từng key bằng `Iterator.remove()`; các socket, server và Selector được đóng khi hoàn tất.

**Phạm vi ví dụ:** cần một môi trường cho phép tạo socket loopback. Timeout 10 giây giúp thất bại rõ ràng khi môi trường bị chặn hoặc quá chậm; khi đó chương trình ném `IOException` thay vì in đủ ba dòng. Đây là mẫu học tập, chưa triển khai các yêu cầu production như hàng đợi dữ liệu nhiều bản tin, backpressure tổng quát, quản lý timeout per-connection và giới hạn tài nguyên.

## 10. Khi dùng interestOps nên đổi như thế nào?

Một lifecycle kết nối TCP thường có dạng:

~~~text
Phía server: ServerSocketChannel
    OP_ACCEPT
       |
       | accept() thành công
       v
SocketChannel được chấp nhận
    OP_READ  <-------------+
       |                   |
       | có dữ liệu cần gửi|
       v                   |
  OP_READ | OP_WRITE       |
       |                   |
       | gửi hết           |
       +-------------------+

Phía client: SocketChannel
    connect(...)
       |
       +-- trả true --------------> OP_READ / OP_WRITE
       |
       +-- trả false --> OP_CONNECT
                           |
                           | finishConnect() thành công
                           v
                      OP_READ / OP_WRITE
~~~

Sơ đồ trình bày trạng thái **interest set** mà chương trình điều chỉnh. Đây không phải bộ máy tự động của Selector; logic ứng dụng chịu trách nhiệm chuyển trạng thái.

Bảng quyết định:

| Tình huống | Interest set hợp lý |
| --- | --- |
| Server chờ kết nối mới | `OP_ACCEPT` |
| Client non-blocking còn pending connect | `OP_CONNECT` |
| Đã kết nối, chờ request/response tới | `OP_READ` |
| Đã kết nối, có dữ liệu outbound còn chờ | `OP_READ \| OP_WRITE` (hoặc OP_WRITE khi chủ động tạm dừng đọc) |
| Đã gửi hết payload | Bỏ `OP_WRITE`; thường giữ `OP_READ` |
| Kết nối đóng hoặc không còn cần theo dõi | `cancel()` key rồi đóng channel nếu đã kết thúc vòng đời |

Không nên luôn đăng ký `OP_READ | OP_WRITE` cho mọi socket khi hoàn toàn không có outbound data. Vì writable thường sẵn sàng, chương trình có thể liên tục xử lý event ghi giả, làm tăng CPU usage đáng kể.

## 11. Các lỗi thường gặp

### Nhầm operation với hành động đã hoàn tất

`isAcceptable()` không tự tạo client; `isConnectable()` không tự hoàn thành kết nối; `isReadable()` không tự đổ byte vào buffer; `isWritable()` không tự chuyển payload. **Cần gọi đúng API I/O** và kiểm tra kết quả.

### Đăng ký operation không hợp lệ

`ServerSocketChannel` không hỗ trợ `OP_READ` hoặc `OP_CONNECT`. `SocketChannel` không hỗ trợ `OP_ACCEPT`. Dùng `validOps()` để phân biệt và tránh `IllegalArgumentException`.

### Quên configureBlocking(false)

Đăng ký channel đang blocking với Selector gây `IllegalBlockingModeException`. Cấu hình non-blocking trước khi `register`.

### Bỏ qua nhánh kết nối hoàn tất ngay

`SocketChannel.connect(address)` có thể trả `true`. Nếu chương trình luôn chờ `OP_CONNECT` sau đó, có thể không tiến triển đúng. Khi trả true, chuyển ngay sang interest set cần thiết của kết nối đã thành lập.

### Không gọi finishConnect

Với connect non-blocking đang pending, phải `finishConnect()` để hoàn tất hoặc nhận thông báo lỗi. Bỏ qua bước này rồi đọc/ghi ngay có thể dẫn tới `NotYetConnectedException`.

### Đăng ký OP_WRITE liên tục

Đây là lỗi hiệu năng kinh điển. Vì socket thường writable, selector có thể liên tục đánh thức thread. Chỉ thêm `OP_WRITE` khi có dữ liệu cần gửi, xóa ngay khi dữ liệu được gửi hết.

### Không xử lý I/O một phần

Một sự kiện `OP_READ` có thể chỉ đọc được vài byte của bản tin; một `OP_WRITE` có thể chỉ gửi được một phần buffer. Với TCP không có ranh giới message tự nhiên, phải giữ state giữa các lượt và xây cơ chế framing.

### Không remove key khỏi selectedKeys

Nếu dùng `selector.selectedKeys()` mà không `iterator.remove()`, key vẫn còn trong tập đã chọn và có thể gây xử lý lặp không mong muốn. Selected set thuộc trách nhiệm quản lý của vòng lặp event.

### Bỏ qua key invalid và thay đổi trạng thái trong vòng lặp

Sau khi một nhánh đóng channel hoặc `cancel()`, các lời gọi kiểm tra readiness sau đó có thể ném `CancelledKeyException`. Kiểm tra `isValid()` và tránh dùng lại key đã hủy.

### Đụng cùng Selector từ nhiều thread mà không phối hợp

Nếu thread khác thêm dữ liệu vào queue hoặc đổi interest set, cần thiết kế thread safety cho queue/state và cân nhắc `selector.wakeup()` để vòng select biết có công việc mới. `wakeup()` không tự đồng bộ mọi biến và không tạo ra một bản tin mạng.

## 12. Câu hỏi tự kiểm tra

1. `ServerSocketChannel` cần theo dõi cờ nào để nhận kết nối? **`OP_ACCEPT`**. Kết nối mới được lấy bằng **`accept()`**.
2. Client gọi `connect(...)` và nhận `false`. Nên quan tâm sự kiện nào? **`OP_CONNECT`**, sau đó gọi `finishConnect()`.
3. Client gọi `connect(...)` và nhận `true`. Có bắt buộc chờ `OP_CONNECT` không? **Không**; kết nối đã hoàn thành ngay, hãy theo dõi read/write theo nhu cầu.
4. Sau `OP_READ`, `read(buffer)` trả `0` nghĩa là EOF? **Không**. EOF là **`-1`**; 0 có nghĩa chưa đọc được byte trong lần gọi.
5. Vì sao không nên để `OP_WRITE` luôn được đăng ký? Vì socket rất hay writable, dễ tạo vòng lặp tốn CPU khi không có payload.
6. `key.interestOps(OP_WRITE)` có giữ lại `OP_READ` đã đăng ký không? **Không**; setter thay cả mask. Dùng `key.interestOps(key.interestOps() | OP_WRITE)` để thêm mà giữ bit cũ.
7. `validOps` và `readyOps` khác nhau thế nào? **validOps** là các thao tác loại channel có thể hỗ trợ; **readyOps** là những thao tác được selector báo ready ở lượt selection.
8. Vì sao cần `it.remove()` trong vòng duyệt `selectedKeys()`? Vì tập selected key không tự dọn sau khi ứng dụng xử lý.
9. `OP_CONNECT` có áp dụng cho socket phía server vừa `accept` không? Thông thường **không cần**; socket nhận qua `accept()` đã có kết nối và thường được đăng ký `OP_READ`.
10. Trong event loop, nhận `OP_WRITE` và `channel.write(buffer)` mới ghi được một phần. Xử lý sao? **Giữ buffer còn byte, giữ `OP_WRITE`, thử tiếp khi có readiness**.

**Ghi nhớ:** `OP_ACCEPT` báo cơ hội nhận kết nối, `OP_CONNECT` báo cơ hội hoàn tất kết nối pending, `OP_READ` báo cơ hội đọc/nhận EOF, `OP_WRITE` báo cơ hội ghi. Chúng là **bit của interest/ready state**, không phải thao tác I/O. Mẫu NIO hiệu quả là đăng ký đúng `validOps`, xử lý `readyOps` dựa trên kết quả gọi channel, bảo toàn dữ liệu chưa hoàn tất, và **chỉ giữ `OP_WRITE` khi có outbound data**.
