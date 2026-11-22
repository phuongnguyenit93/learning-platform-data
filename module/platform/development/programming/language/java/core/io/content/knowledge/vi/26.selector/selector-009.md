# Chỉ đăng ký OP_WRITE khi còn dữ liệu cần gửi trong Java NIO Selector

## 1. Vì sao OP_WRITE thường gây vòng lặp tốn CPU?

Trong Java NIO, `SelectionKey.OP_WRITE` yêu cầu `Selector` theo dõi xem `SocketChannel` có khả năng nhận thêm byte từ ứng dụng hay không. Với socket TCP đã kết nối, bộ đệm gửi của hệ điều hành thường còn chỗ, nên channel có thể được báo **writable** hầu như liên tục.

Nếu mọi socket đều đăng ký `OP_WRITE` từ khi kết nối và giữ nguyên cờ đó cả lúc không có dữ liệu gửi, một thread Selector có thể chạy vòng lặp rất nhanh:

~~~text
Outbound queue rỗng
        |
interestOps = OP_READ | OP_WRITE
        |
select() trả về vì socket writable
        |
isWritable() là true nhưng không có byte nào cần gửi
        |
quay lại select() → lại writable → xử lý trống → lặp mãi
~~~ 

Đây là **write-readiness spin**: vòng lặp sự kiện liên tục thức dậy nhưng không có công việc hữu ích, làm CPU tăng, tiêu tốn năng lượng và giảm khả năng xử lý những connection thực sự có công việc.

**Nguyên tắc:** chỉ thêm `OP_WRITE` vào `interestOps` khi kết nối còn byte chờ gửi; xóa nó khi hàng đợi outbound đã trống. `OP_READ` thường được giữ riêng nếu kết nối vẫn cần nhận dữ liệu.

## 2. Interest, readiness và write thực tế là ba chuyện khác nhau

| Thành phần | Câu hỏi được trả lời |
| --- | --- |
| `key.interestOps()` | Ứng dụng **muốn theo dõi** những hoạt động nào? |
| `key.readyOps()` hoặc `key.isWritable()` | Selector **đã phát hiện** socket có thể tiến hành ghi ở lượt chọn này? |
| `channel.write(buffer)` | Lần gọi này **thực sự chuyển được bao nhiêu byte** từ buffer? |

Một key có `OP_WRITE` trong interest set không có nghĩa byte đã được gửi. `key.isWritable()` không bảo đảm một lần `write` sẽ chuyển hết buffer. Với non-blocking channel, `write` có thể trả 0 hoặc một số byte nhỏ hơn `buffer.remaining()` trước khi gọi.

Thông tin writable chỉ liên quan đến khả năng ghi ở đầu gửi. Nó **không chứng minh** peer đã nhận, đã xử lý hoặc đã lưu bền dữ liệu; muốn biết điều đó cần giao thức phản hồi hoặc ACK ở tầng ứng dụng.

~~~text
Có byte chờ gửi → Thêm OP_WRITE → Selector báo writable
                                      |
                                      v
                                write(buffer)
                                      |
                      +---------------+---------------+
                      |                               |
                 Còn dữ liệu?                    Đã hết dữ liệu?
                      |                               |
                   Giữ OP_WRITE                   Bỏ OP_WRITE
                   Giữ position                   Giữ OP_READ
                   Chờ lượt sau                   Tránh CPU spin
~~~

## 3. Bật và tắt đúng bit OP_WRITE

Sau khi TCP đã kết nối, không có dữ liệu outbound:

~~~java
key.interestOps(SelectionKey.OP_READ);
~~~

Khi dữ liệu mới xuất hiện, thêm `OP_WRITE` mà **không làm mất** các cờ cũ:

~~~java
key.interestOps(key.interestOps() | SelectionKey.OP_WRITE);
~~~

Khi queue trống, chỉ xóa bit `OP_WRITE`:

~~~java
key.interestOps(key.interestOps() & ~SelectionKey.OP_WRITE);
~~~

Đây là các đoạn minh họa nằm trong event loop, với `key` hợp lệ và các import `java.nio.channels.*` thích hợp; chúng chưa là chương trình độc lập.

| Interest set trước | Tác động | Interest set sau |
| --- | --- | --- |
| `OP_READ` | Thêm `OP_WRITE` | `OP_READ | OP_WRITE` |
| `OP_READ | OP_WRITE` | Thêm `OP_WRITE` lần nữa | Không đổi |
| `OP_READ | OP_WRITE` | Xóa `OP_WRITE` | `OP_READ` |
| `OP_READ` | Xóa `OP_WRITE` | Không đổi |

**Sai lầm:** viết `key.interestOps(SelectionKey.OP_WRITE)` khi vẫn muốn đọc. Lời gọi đó **thay thế toàn bộ mask**, xóa `OP_READ`. Nếu chỉ thêm cờ, dùng phép OR bit; nếu chỉ bỏ cờ, dùng phép AND với bit đảo.

Java 17 cũng có `SelectionKey.interestOpsOr(mask)` và `interestOpsAnd(mask)` để cập nhật bit nguyên tử. Tuy nhiên, tính nguyên tử của mask không tự bảo vệ hàng đợi dữ liệu: trong ứng dụng nhiều thread vẫn cần quy tắc ownership, đồng bộ hoặc bàn giao tác vụ.

## 4. ByteBuffer phải giữ nguyên phần chưa ghi xong

Thao tác `channel.write(source)` tiêu thụ byte từ `source.position()` đến trước `source.limit()`, làm tăng position theo số byte thực sự được chuyển.

Giả sử buffer chứa 10 byte. Một lần `write` chuyển 4 byte:

~~~text
Trước: position=0, limit=10, remaining=10
write() trả 4
Sau:   position=4, limit=10, remaining=6
~~~

Sáu byte cuối **vẫn chưa được chuyển khỏi ByteBuffer**. Ứng dụng phải giữ buffer đó và tiếp tục viết khi có readiness lần tới. Không được gọi `clear()`, `rewind()` hay `flip()` tùy tiện giữa hai lần gửi vì có thể làm gửi trùng hoặc đánh mất byte.

Ví dụ một connection có outbound queue:

~~~text
head                                                     tail
  |                                                        |
[Buffer A: còn 6 byte] → [Buffer B: còn 12 byte] → [Buffer C]
                           Outbound vẫn chưa rỗng
                           nên cần OP_WRITE
~~~

Dùng queue giữ các ByteBuffer đã sẵn sàng **đọc** để gửi. `ByteBuffer.wrap(byte[])` và `StandardCharsets.UTF_8.encode(text)` trả buffer có trạng thái phù hợp cho việc gửi; với `ByteBuffer.allocate(...)` rồi `put(...)`, phải `flip()` sau khi put.

Mảnh code cơ bản cho sự kiện writable:

~~~java
while (!outbound.isEmpty()) {
    ByteBuffer head = outbound.peek();
    int n = channel.write(head);

    if (head.hasRemaining()) {
        // Đã ghi một phần hoặc n == 0; giữ head để gửi tiếp.
        break;
    }

    outbound.remove();
}

if (outbound.isEmpty()) {
    key.interestOps(key.interestOps() & ~SelectionKey.OP_WRITE);
}
~~~

Đây là đoạn minh họa trong phương thức xử lý một `SocketChannel` với một `Queue<ByteBuffer> outbound` và `SelectionKey key`; nó không phải chương trình chạy độc lập.

Việc kiểm tra `head.hasRemaining()` là quan trọng nhất. Khi buffer đầu tiên đã hết, loại khỏi queue và thử gửi buffer kế tiếp. Khi socket chưa thể tiến triển, không được quay vòng gọi `write` vô hạn: rời hàm, giữ `OP_WRITE` và chờ lượt readiness sau.

## 5. Một connection có các trạng thái nào?

~~~text
                    Connected
                        |
                        v
                 Queue trống
                 interest=OP_READ
                        |
                  enqueue(payload)
                        |
                        v
                  Queue có byte
            interest=OP_READ | OP_WRITE
                        |
                 Selector writable
                        |
                  write(head)
                        |
             +----------+----------+
             |                     |
        Head còn byte        Head đã gửi hết
             |                     |
         Chờ lần sau          Bỏ head khỏi queue
             |                     |
         Giữ OP_WRITE        Còn head khác?
                                   |
                              +----+----+
                              |         |
                             Có        Không
                              |         |
                         Giữ OP_WRITE   Bỏ OP_WRITE
                                        Giữ OP_READ
~~~

Đây là một **state machine do ứng dụng quản lý**, không phải cơ chế tự động của Selector. Nó phải xử lý cả hai trường hợp `write` tiến triển một phần và `write` trả 0.

Không nên tạo một `SelectionKey` mới mỗi lần có payload. Một channel đã đăng ký trên một selector thường giữ key tương ứng và chỉ thay interest set. Nếu key bị cancel/đóng thì cần kết thúc vòng đời kết nối hoặc tái đăng ký theo điều kiện API.

## 6. Ví dụ Java 17+ chạy độc lập: bật/tắt OP_WRITE khi gửi PING và PONG

Chương trình dùng loopback TCP, một `Selector` và một thread. Client gửi `PING`, server trả `PONG`. Chỉ khi có dữ liệu outbound mới bật `OP_WRITE`, và tắt sau khi gửi xong.

Server dùng `OP_ACCEPT`. Client dùng `OP_CONNECT` nếu `connect()` chưa hoàn tất; nếu kết nối hoàn tất ngay thì chuyển thẳng sang `OP_WRITE`. Các output chỉ được in khi từng chặng đã hoàn thành, nên không phụ thuộc thứ tự các selected key.

Lưu thành `WriteInterestDemo.java`:

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

public class WriteInterestDemo {
    public static void main(String[] args) throws IOException {
        try (Selector selector = Selector.open();
             ServerSocketChannel listener = ServerSocketChannel.open();
             SocketChannel client = SocketChannel.open()) {

            listener.configureBlocking(false);
            listener.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 0));
            listener.register(selector, SelectionKey.OP_ACCEPT);

            client.configureBlocking(false);
            boolean connected = client.connect(listener.getLocalAddress());
            client.register(selector, connected
                    ? SelectionKey.OP_WRITE
                    : SelectionKey.OP_CONNECT);

            ByteBuffer request = ByteBuffer.wrap(
                    "PING".getBytes(StandardCharsets.US_ASCII));
            ByteBuffer serverInput = ByteBuffer.allocate(4);
            ByteBuffer response = ByteBuffer.wrap(
                    "PONG".getBytes(StandardCharsets.US_ASCII));
            ByteBuffer clientInput = ByteBuffer.allocate(4);

            SocketChannel peer = null;
            long deadline = System.nanoTime()
                    + TimeUnit.SECONDS.toNanos(10);

            try {
                while (clientInput.hasRemaining()
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
                            SocketChannel accepted = listener.accept();
                            if (accepted != null) {
                                accepted.configureBlocking(false);
                                accepted.register(
                                        selector, SelectionKey.OP_READ);
                                peer = accepted;
                                key.interestOps(0);
                            }
                        } else if (key.isConnectable()) {
                            if (client.finishConnect()) {
                                key.interestOps(SelectionKey.OP_WRITE);
                            }
                        } else if (key.isWritable()) {
                            if (key.channel() == client) {
                                client.write(request);
                                if (!request.hasRemaining()) {
                                    key.interestOps(SelectionKey.OP_READ);
                                    System.out.println(
                                            "client OP_WRITE removed=true");
                                }
                            } else {
                                SocketChannel serverSide =
                                        (SocketChannel) key.channel();
                                serverSide.write(response);
                                if (!response.hasRemaining()) {
                                    key.interestOps(0);
                                    System.out.println(
                                            "server OP_WRITE removed=true");
                                }
                            }
                        } else if (key.isReadable()) {
                            SocketChannel reading =
                                    (SocketChannel) key.channel();

                            if (reading == client) {
                                int n = client.read(clientInput);
                                if (n < 0) {
                                    throw new EOFException(
                                            "Server closed before PONG");
                                }
                            } else {
                                int n = reading.read(serverInput);
                                if (n < 0) {
                                    throw new EOFException(
                                            "Client closed before PING");
                                }
                                if (!serverInput.hasRemaining()) {
                                    serverInput.flip();
                                    String message =
                                            StandardCharsets.US_ASCII
                                                    .decode(serverInput)
                                                    .toString();
                                    System.out.println(
                                            "server received=" + message);
                                    key.interestOps(SelectionKey.OP_WRITE);
                                }
                            }
                        }
                    }
                }

                if (clientInput.hasRemaining()) {
                    throw new IOException("Timed out waiting for PONG");
                }

                clientInput.flip();
                System.out.println("client received="
                        + StandardCharsets.US_ASCII.decode(clientInput));
            } finally {
                if (peer != null) {
                    peer.close();
                }
            }
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac WriteInterestDemo.java
java WriteInterestDemo
~~~

Stdout mong đợi khi môi trường cho phép kết nối loopback và hoàn thành I/O:

~~~text
client OP_WRITE removed=true
server received=PING
server OP_WRITE removed=true
client received=PONG
~~~

Phân tích:

1. Client đăng ký `OP_CONNECT` khi connection còn pending; nếu hoàn tất ngay thì đăng ký `OP_WRITE` vì đã có sẵn `PING`.
2. Client ghi buffer `PING`. Nếu viết được ít hơn 4 byte, buffer còn `remaining()` và `OP_WRITE` vẫn bật. Khi gửi đủ, chuyển về `OP_READ`.
3. Socket bên server theo dõi `OP_READ`, tích lũy đúng 4 byte. Khi đã có `PING`, nó đổi interest set sang `OP_WRITE` vì chuẩn bị gửi `PONG`.
4. Server ghi hết `PONG` và bỏ `OP_WRITE` bằng cách đặt interest về 0, vì ví dụ chỉ xử lý một request/response.
5. Client đọc đủ 4 byte `PONG`, kết thúc vòng lặp và in kết quả.
6. Các selected key được loại khỏi tập bằng `Iterator.remove()`; channel và selector được đóng khi kết thúc.

**Điều kiện:** môi trường phải cho phép mở socket TCP loopback và hoạt động trong thời hạn 10 giây. Ví dụ này chỉ minh họa một message cố định mỗi chiều, chưa xử lý queue nhiều message, TLS, giao thức framing hoặc hàng nghìn connection. Nếu môi trường không cho phép networking, sẽ có ngoại lệ thay vì stdout trên.

## 7. Trong server thật: outbound queue và connection state

Với nhiều message, nên gắn state riêng cho mỗi `SelectionKey` bằng `key.attach(state)`. Một dạng thường dùng:

~~~java
final class ConnectionState {
    final java.util.ArrayDeque<ByteBuffer> outbound =
            new java.util.ArrayDeque<>();
    final ByteBuffer inbound = ByteBuffer.allocate(8192);
    long queuedBytes;
}
~~~

Đây là một class minh họa trong dự án lớn hơn; cần import `java.nio.ByteBuffer`.

Ở **thread Selector** khi có message mới:

~~~java
void enqueue(SelectionKey key, ByteBuffer data) {
    ConnectionState state = (ConnectionState) key.attachment();
    if (!data.hasRemaining()) {
        return;
    }

    state.queuedBytes += data.remaining();
    state.outbound.addLast(data);
    key.interestOps(key.interestOps() | SelectionKey.OP_WRITE);
}
~~~

Ở **thread Selector** khi key writable:

~~~java
void onWritable(SelectionKey key) throws IOException {
    SocketChannel ch = (SocketChannel) key.channel();
    ConnectionState state = (ConnectionState) key.attachment();

    while (!state.outbound.isEmpty()) {
        ByteBuffer head = state.outbound.peekFirst();
        int n = ch.write(head);
        state.queuedBytes -= n;

        if (head.hasRemaining()) {
            break;
        }
        state.outbound.removeFirst();
    }

    if (state.outbound.isEmpty()) {
        key.interestOps(
                key.interestOps() & ~SelectionKey.OP_WRITE);
    }
}
~~~

Đây là các **mảnh phương thức minh họa**, chưa có `main` hoặc cơ chế bảo vệ full lifecycle. Chúng giả định key hợp lệ và state chỉ do thread Selector thay đổi.

**Ownership của ByteBuffer:** sau khi enqueue, producer không nên sửa backing array/position của payload cho đến khi consumer đã xử lý hoặc sao chép xong. Nếu không, có thể phát sinh race và gửi dữ liệu sai.

Nếu queue đã rỗng, không cần chờ thêm event writable. Khi dữ liệu mới lại đến, bật bit một lần nữa. `OP_READ` vẫn được giữ nếu ứng dụng còn muốn nhận request.

## 8. Backpressure và giới hạn lượng dữ liệu chờ

Tắt `OP_WRITE` giúp tránh CPU spin **khi không có gì để gửi**, nhưng không giải quyết vấn đề **producer tạo dữ liệu nhanh hơn socket tiêu thụ**. Nếu ứng dụng tạo 10 MiB/s nhưng đường truyền chỉ tiêu thụ 1 MiB/s, queue tăng khoảng 9 MiB mỗi giây; đây là ví dụ minh họa, không phải số đo cho mọi hệ thống.

Để tránh cạn bộ nhớ, nên:

- Giới hạn số byte và số message trong queue theo mỗi connection và trên toàn hệ thống.
- Dùng **high-water mark** để dừng hoặc giảm nguồn tạo thêm dữ liệu khi tồn đọng quá cao.
- Dùng **low-water mark** để tiếp tục nhận/đẩy dữ liệu khi backlog giảm.
- Nếu cần, tạm bỏ `OP_READ` để không nhận quá nhiều yêu cầu rồi lại phải tạo thêm response, nhưng chỉ khi giao thức cho phép.
- Giới hạn lượng byte xử lý trong một vòng event loop để một connection có outbound lớn không làm đói những connection khác.
- Có chính sách timeout, từ chối yêu cầu hoặc ngắt kết nối quá chậm nếu queue không thể phục hồi.

Một queue đã được drain hết qua `write` cũng không có nghĩa remote ứng dụng đã xử lý dữ liệu. Cần ACK/response riêng nếu giao thức đòi hỏi xác nhận.

## 9. Khi thread khác tạo outbound data

Trong ứng dụng thực tế, worker thread có thể tạo xong response trong khi selector thread đang ngủ ở `select()`. Đừng để worker tùy tiện sửa `ArrayDeque` của connection, vì `ArrayDeque` không thread-safe.

Mô hình dễ quản lý:

1. Worker tạo payload và thêm **tác vụ enqueue** vào một command queue thread-safe.
2. Worker gọi `selector.wakeup()` để thread đang ở `select()` xử lý tác vụ sớm.
3. Thread Selector lấy tác vụ, đưa payload vào outbound queue của connection, thêm `OP_WRITE` khi cần.
4. Sau khi ghi hết dữ liệu, chính thread Selector bỏ `OP_WRITE`.

~~~text
Worker thread                       Selector thread
     |                                      |
     | tạo response                         | select()
     |                                      |
     +-- commandQueue.add(task) ----------->|
     +-- selector.wakeup() ----------------> | thức dậy
                                            |
                                            +-- xử lý task
                                            +-- outbound.add(payload)
                                            +-- thêm OP_WRITE
                                            +-- chờ writable và write
~~~

`wakeup()` **không** tự gửi byte, không tự thay `interestOps` và cũng không làm queue bất kỳ trở thành thread-safe. Khi task đến trễ sau lúc key đã cancel hoặc connection đóng, phải có chính sách bỏ task hoặc xử lý lỗi an toàn.

`SelectionKey.interestOpsOr(...)` và `interestOpsAnd(...)` có thể hỗ trợ cập nhật bit nguyên tử, nhưng không thay thế đồng bộ dữ liệu queue. Một thread duy nhất sở hữu interest set/queue giúp tránh sai sót khi có nhiều nguồn tạo response.

## 10. Những lỗi phổ biến

### Giữ OP_WRITE kể cả khi không có payload

~~~java
socket.register(selector,
        SelectionKey.OP_READ | SelectionKey.OP_WRITE);
~~~

Đây là mảnh minh họa có `socket` và `selector` đang mở. Khi không có outbound data, socket vẫn thường writable, khiến selector thức dậy liên tục. **Sửa:** mặc định chỉ đăng ký `OP_READ` và bật `OP_WRITE` khi queue có byte.

### Xóa OP_WRITE quá sớm

`channel.write(payload)` có thể chuyển 4 trong 10 byte. Nếu lập tức xóa `OP_WRITE` thì 6 byte còn lại có thể chờ mãi không được gửi. **Sửa:** chỉ xóa khi mọi outbound buffer đã hết `remaining()`.

### Ghi một phần rồi reset buffer

Gọi `clear()` hoặc `rewind()` với buffer đang gửi dở sẽ làm position quay về đầu, có thể gửi trùng dữ liệu. Buffer phải được giữ nguyên trạng thái từ lượt writable trước.

### Busy loop khi write trả 0

~~~java
while (buffer.hasRemaining()) {
    channel.write(buffer);
}
~~~

Với non-blocking channel, vòng trên có thể xoay CPU khi không tiến triển. **Sửa:** nếu còn dữ liệu mà chưa ghi được, quay về Selector và chờ readiness.

### Thay cả interest mask và bỏ mất OP_READ

`key.interestOps(SelectionKey.OP_WRITE)` xóa những bit cũ, không chỉ thêm `OP_WRITE`. Dùng phép OR để thêm bit hoặc chỉ thay toàn bộ mask nếu thực sự muốn thay state.

### Không giới hạn outbound queue

Quản lý `OP_WRITE` đúng vẫn có thể hết RAM nếu remote peer quá chậm. Áp dụng watermarks, queue caps và backpressure.

### Thay đổi queue ở nhiều thread không có đồng bộ

`ArrayDeque` không thread-safe. Nên để Selector thread sở hữu queue, còn worker thread dùng command queue thread-safe và `wakeup()`.

### Nhầm writable với delivery ACK

Khi `write` trả số byte đã chuyển, chưa có bảo đảm peer đã xử lý message. Nếu cần xác nhận end-to-end thì xây giao thức ACK.

## 11. Bài tập kiểm tra

1. Channel đã connected, outbound queue rỗng. Nên quan tâm bit nào? **Thường chỉ `OP_READ`**, không giữ `OP_WRITE`.
2. Có thêm một buffer 200 byte vào queue. Cần làm gì? **Bật `OP_WRITE`**.
3. `write` chuyển 70/200 byte. Tiếp theo? **Giữ 130 byte và `OP_WRITE`**, thử tiếp khi được báo ready.
4. Queue có hai buffer; buffer đầu đã hết nhưng buffer thứ hai còn byte. Được bỏ `OP_WRITE` chưa? **Chưa**.
5. Queue rỗng hoàn toàn. Việc cần làm? **Bỏ `OP_WRITE`**, thường giữ `OP_READ`.
6. `key.interestOps(OP_WRITE)` có giữ bit `OP_READ` không? **Không**; setter thay nguyên mask.
7. Tại sao không gọi `write` liên tiếp vô hạn nếu trả `0`? **Vì non-blocking channel chưa tiến triển, cần đợi readiness**.
8. Tại sao phải giữ `ByteBuffer.position()` giữa các lần write? **Để tiếp tục từ byte chưa chuyển, không lặp lại dữ liệu cũ**.
9. Worker tạo response khi selector đang chờ. Phối hợp ra sao? **Đưa task vào queue an toàn, gọi `wakeup()`, để selector thread bật `OP_WRITE`**.
10. Bật/tắt `OP_WRITE` đã đủ chống cạn RAM chưa? **Chưa**; phải giới hạn outbound queue và tạo backpressure.

**Ghi nhớ:** `OP_WRITE` biểu diễn khả năng ghi, không phải tín hiệu "có dữ liệu cần gửi". Chỉ bật bit khi outbound queue có byte; giữ bit khi `write` mới chuyển một phần; khi mọi buffer đã được tiêu thụ, bỏ `OP_WRITE` để tránh CPU spin. Kết hợp với ByteBuffer ownership, đồng bộ giữa thread và backpressure để có event loop vừa chính xác vừa hiệu quả.
