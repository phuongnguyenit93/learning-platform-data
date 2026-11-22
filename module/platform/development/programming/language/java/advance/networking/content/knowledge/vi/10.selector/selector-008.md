# Chỉ đăng ký OP_WRITE khi còn dữ liệu chờ gửi để tránh vòng lặp tốn CPU (Java NIO Selector)

**Quy tắc cốt lõi:** với `SocketChannel` ở chế độ **non-blocking**, chỉ bật `SelectionKey.OP_WRITE` khi ứng dụng thực sự có **byte chưa gửi hết** trên kết nối đó; khi hàng đợi outbound đã rỗng, phải **gỡ OP_WRITE khỏi interest set ngay**. Nếu giữ OP_WRITE thường trực, `Selector.select()` có thể thức dậy liên tục vì socket hầu như luôn *writable* khi send buffer còn chỗ, dù ứng dụng **không có dữ liệu nào cần ghi**. Event loop khi đó tiêu tốn CPU để xử lý các sự kiện vô ích.

Đây là một lỗi hiệu năng điển hình trong chủ đề **Selector** của **Java Advance - networking**. Bài học trình bày bản chất write-readiness, cách bật/tắt đúng bằng bitmask mà không làm mất `OP_READ`, xử lý partial writes và queue, điều phối từ thread khác, backpressure, kiểm thử và hai chương trình Java 17+ có thể biên dịch/chạy độc lập.

## 1. Vì sao OP_WRITE khác với “có dữ liệu mới cần gửi”?

`SelectionKey.OP_WRITE` nói rằng channel **có khả năng ghi thêm byte vào tầng gửi của hệ điều hành mà không phải chờ lâu**. Nó không phải sự kiện “ứng dụng vừa tạo response” và cũng không phải tín hiệu “peer đã nhận dữ liệu”.

Khi TCP send buffer còn dung lượng, trạng thái có thể writable suốt nhiều vòng `select`. Với phần lớn kết nối đang khỏe, đây là trạng thái **rất phổ biến**, đặc biệt khi không gửi gì. Ngược lại, `OP_READ` thường chỉ đáng chú ý khi có byte nhận/EOF/sự kiện I/O để xử lý. Vì vậy viết một vòng event loop quan tâm thường trực cả `OP_READ | OP_WRITE` sẽ làm sự kiện ghi xuất hiện ngay cả lúc queue gửi trống.

```text
Không có outbound data, nhưng key vẫn đăng ký OP_WRITE:

selector.select()  -> writable -> pendingQueue.isEmpty() -> không gửi
selector.select()  -> writable -> pendingQueue.isEmpty() -> không gửi
selector.select()  -> writable -> pendingQueue.isEmpty() -> không gửi
... lặp với tốc độ cao dù không có công việc ứng dụng ...

Khi tắt OP_WRITE ở trạng thái idle:
selector.select()  -> chờ OP_READ / OP_ACCEPT / timer / wakeup
                                    |
                               Có response mới
                                    v
                     enqueue(response) + bật OP_WRITE
                                    |
                         writable -> ghi từng phần
                                    |
                         hết pending -> tắt OP_WRITE
                                    |
                              tiếp tục chờ
```

**Readiness ≠ message completion, cũng ≠ acknowledgement.** Channel writable có thể ghi `0` trong một tình huống đua/trạng thái thay đổi, có thể ghi được một phần buffer, hoặc có thể phát sinh `IOException`. Việc ghi thành công vào TCP cũng chưa khẳng định đối tác đã giải mã hay xử lý response.

## 2. Interest set, ready set và selected-key set là ba thứ khác nhau

Một `SelectionKey` đại diện cho sự đăng ký giữa một selectable channel và `Selector`. Ba khái niệm thường bị nhầm:

| Thành phần | API | Vai trò |
| --- | --- | --- |
| **Interest set** | `key.interestOps()` | Các loại I/O mà ứng dụng **muốn được thông báo** ở những lượt chọn tiếp theo |
| **Ready set** | `key.readyOps()`, `key.isWritable()`, `key.isReadable()` | Những thao tác được selector đánh dấu có khả năng tiến triển từ kết quả chọn |
| **Selected-key set** | `selector.selectedKeys()` | Tập key mà ứng dụng phải duyệt và **loại khỏi set sau khi xử lý** |

Một event loop nhận biết rằng có byte cần gửi **bằng dữ liệu trong outbound queue**, không phải bằng `key.isWritable()`. Khi queue có data, nó đăng ký interest OP_WRITE và đợi readiness. Khi queue hết, nó gỡ interest. **Đừng dùng `readyOps()` làm nơi lưu trạng thái nghiệp vụ**: đó là kết quả readiness, không phải “đang có response chờ”.

Java NIO `Selector` chủ yếu biểu diễn **readiness**, không phải completion API kiểu “hệ điều hành sẽ gửi xong message và gọi callback”. Khi `select` trả một key writable, code vẫn phải gọi `channel.write(ByteBuffer)` và kiểm tra `remaining()`.

Một điểm thiết yếu khác: khi duyệt `selector.selectedKeys()`, dùng iterator và `iterator.remove()`. Nếu bỏ key ở lại set selected, các lần select sau có thể không thêm key ấy như bạn chờ đợi và hành vi theo dõi trở nên khó hiểu. Việc remove selected key **không** hủy registration và không gỡ interest OP_WRITE: hai thao tác hoàn toàn khác nhau.

## 3. Lỗi sai thường gặp: luôn bật OP_WRITE từ khi accept

Đây là **đoạn mã minh họa sai**, không phải chương trình chạy độc lập:

```java
SocketChannel client = server.accept();
client.configureBlocking(false);

// SAI: quan tâm ghi ngay cả khi chưa có dữ liệu cần gửi.
client.register(selector,
        SelectionKey.OP_READ | SelectionKey.OP_WRITE);

// Trong event loop:
if (key.isWritable()) {
    if (outboundQueue.isEmpty()) {
        // Chẳng có dữ liệu; vòng select kế tiếp vẫn thường thức dậy.
        return;
    }
    // ...
}
```

Sai không nằm ở `if (outboundQueue.isEmpty())` — kiểm tra ấy cần thiết để phòng vệ. Sai nằm ở việc **interest OP_WRITE vẫn bật** sau khi xác định không còn byte chờ gửi. Nếu loop cứ `selector.select()` rồi liên tục nhận writable event trong trạng thái idle, CPU có thể tăng rất mạnh, số lượt select/s cao, latency các socket khác tăng vì event loop bận xử lý key không làm việc.

Một phiên bản khác cũng sai:

```java
// Sai: không có outbound data nhưng vẫn tiếp tục đăng ký OP_WRITE.
if (key.isWritable()) {
    ByteBuffer buffer = outboundQueue.peek();
    if (buffer != null) {
        channel.write(buffer);
    }
    // Không cập nhật interestOps khi queue đã rỗng!
}
```

Thậm chí khi có vài byte chờ gửi ban đầu, sau khi `ByteBuffer` đã được ghi hết mà quên xóa OP_WRITE, vòng lặp CPU vẫn tiếp diễn **sau khi mọi response đã gửi xong**. Đây thường là lỗi chỉ xuất hiện sau một request đầu tiên nên dễ bị bỏ qua.

## 4. Quy tắc bật/tắt interest bằng phép bitmask

Giả sử `SelectionKey key` còn hợp lệ và việc sửa registration được thực hiện trong **owner event-loop thread**. Những phép toán chuẩn:

```java
// Ban đầu chỉ đọc, chưa có outbound bytes.
key.interestOps(SelectionKey.OP_READ);

// Khi enqueue byte mới (và queue trước đó rỗng):
key.interestOps(key.interestOps() | SelectionKey.OP_WRITE);

// Khi toàn bộ queue đã được ghi hết:
key.interestOps(key.interestOps() & ~SelectionKey.OP_WRITE);

// Kiểm tra interest hiện tại, không nhầm với readyOps:
boolean wantsWrite =
        (key.interestOps() & SelectionKey.OP_WRITE) != 0;
```

Đây là **snippet minh họa**, không có class/biến `key` đầy đủ nên không chạy độc lập. Cần nhớ:

- Dùng **`| OP_WRITE`** để bật một bit mà giữ các bit khác như `OP_READ` và `OP_CONNECT` nếu chúng còn hợp lệ.
- Dùng **`& ~OP_WRITE`** để tắt duy nhất bit write, không làm tắt các interest khác.
- **Đừng dùng `key.interestOps(SelectionKey.OP_WRITE)` tùy tiện** khi chỉ muốn *thêm* write: nó thay toàn bộ interest set và có thể vô tình tắt OP_READ.
- **Đừng dùng `key.interestOps(0)` để ngừng ghi** nếu vẫn muốn tiếp tục đọc; 0 nghĩa là không quan tâm bất kỳ readiness operation nào cho key đó.
- Một key chỉ nhận các operation mà channel hỗ trợ. Với `SocketChannel` đã kết nối, OP_READ/OP_WRITE thường là hai interest chính; `ServerSocketChannel` dùng OP_ACCEPT.
- `interestOps` có thể ném `CancelledKeyException` nếu key đã bị cancel. Vòng đời, hủy connection và worker completion phải kiểm tra trạng thái trước khi bật lại.

Thay đổi interest set ảnh hưởng đến **các lượt chọn**, không tự gọi `channel.write` và không tự “flush” một ByteBuffer. Logic thực tế phải xử lý cả đầu ra mới được enqueue **lẫn** dữ liệu chưa ghi hết từ lần trước.

## 5. Vòng đời outbound: từ idle tới drain rồi trở lại idle

Đối với **mỗi kết nối**, có thể mô hình hóa một queue `Deque<ByteBuffer>` của những frame đã sẵn sàng truyền:

```text
IDLE
  outbound = []
  interest = OP_READ               (OP_WRITE OFF)
       |
       | app tạo response đã frame hoàn chỉnh
       v
ENQUEUE
  outbound = [frame1, frame2, ...]
  interest |= OP_WRITE             (OP_WRITE ON)
       |
       | Selector báo writable
       v
WRITE
  write(head ByteBuffer)
  nếu head.hasRemaining(): giữ position, đợi event kế
  nếu head hết byte: remove head, thử frame kế
       |
       +---- outbound != [] -------> giữ OP_WRITE ON
       |
       +---- outbound == [] -------> interest &= ~OP_WRITE
                                        |
                                        v
                                       IDLE
```

Có thể bật OP_WRITE mỗi khi enqueue, nhưng để giảm các syscall/hàm set interest không cần thiết, thường chỉ bật khi queue chuyển từ **rỗng → không rỗng**. Dù sao, nếu queue đang còn byte sau lần write cuối, OP_WRITE **phải vẫn bật** để có cơ hội hoàn tất.

Với ứng dụng đa producer, việc cập nhật queue và interest set phải có owner/synchronization rõ ràng. Một cách an toàn là mọi thay đổi output queue của socket, `key.interestOps` và `channel.write` đều do **một event-loop thread** thực hiện. Worker tạo response gửi command qua mailbox, event loop nhận và enqueue frame.

## 6. Vì sao phải giữ ByteBuffer qua các lần write?

Ở non-blocking mode, `SocketChannel.write(ByteBuffer)` có thể:

- Ghi toàn bộ byte còn lại, tăng `position` đến `limit`.
- Ghi **một phần**, tăng `position` tương ứng.
- Trả **0** vì hiện tại không ghi thêm được.
- Ném `IOException` khi có lỗi/connection đóng.

Không thể bỏ phần buffer chưa gửi chỉ vì một `write` đã trả về bình thường:

```java
// Đoạn minh họa, channel và queue đã tồn tại.
ByteBuffer current = outbound.peekFirst();

int n = channel.write(current);

if (current.hasRemaining()) {
    // Chưa xong frame; giữ buffer cùng position, giữ OP_WRITE bật.
    return;
}

outbound.removeFirst(); // Chỉ bỏ khi current hết byte.
if (outbound.isEmpty()) {
    key.interestOps(key.interestOps() & ~SelectionKey.OP_WRITE);
}
```

**Đừng gọi `flip()` lại** lên buffer sau khi `write` một phần. `flip()` thay `limit` theo `position` hiện tại và có thể làm hỏng ranh giới phần chưa gửi. `position` đã chứa thông tin offset tiếp theo. Cũng đừng tạo mới `ByteBuffer.wrap(allBytes)` từ đầu mỗi lần writable event — bạn có thể gửi trùng những byte đã gửi.

Nếu message là length-prefix, hãy queue **cả frame** (header + body) với ordering rõ. Việc nhiều producer tự ý ghi trực tiếp cùng một `SocketChannel` sẽ khiến các phần của nhiều frame xen nhau. Với server selector, mô hình một writer owner/connection giúp tránh lỗi ấy.

## 7. Mẫu xử lý write event: có giới hạn công việc mỗi lượt

**Pseudo-code minh họa**, các class `Connection` và hàm `closeConnection` là của ứng dụng, không phải mã chạy độc lập:

```java
void onWritable(SelectionKey key) throws IOException {
    SocketChannel channel = (SocketChannel) key.channel();
    Connection state = (Connection) key.attachment();

    int budget = 64 * 1024; // Ví dụ: tối đa 64 KiB/lần xử lý.
    while (!state.outbound.isEmpty() && budget > 0) {
        ByteBuffer head = state.outbound.peekFirst();

        // Giới hạn số byte của lần write này.
        int oldLimit = head.limit();
        head.limit(Math.min(oldLimit, head.position() + budget));
        int n;
        try {
            n = channel.write(head);
        } finally {
            head.limit(oldLimit);
        }
        budget -= n;

        if (head.hasRemaining()) {
            break; // Partial/zero write, hoặc hết budget.
        }
        state.outbound.removeFirst();
    }

    if (state.outbound.isEmpty()) {
        key.interestOps(key.interestOps() & ~SelectionKey.OP_WRITE);
    }
}
```

Mục đích của **write budget** là tránh một client có output rất nhiều monopolize event loop, làm các client khác tăng độ trễ. Mẫu trên khôi phục `limit` sau write, vì `ByteBuffer` được giữ trong queue lâu dài. Nếu `budget` hết, giữ OP_WRITE vì còn data; event loop sẽ tiếp tục trong lượt phù hợp tiếp theo.

**Lưu ý thiết kế:** `SelectionKey` và `ByteBuffer` phải do owner event loop quản lý; không để worker đồng thời sửa `position/limit`. `write` trả 0 vẫn nên dừng vòng xử lý key và quay lại `select`, không lặp nóng trên cùng key. Một số hệ thống bổ sung giới hạn số frame/lượt để đảm bảo công bằng.

Nếu chỉ xử lý một response nhỏ mỗi client, không nhất thiết cần budget phức tạp; vẫn phải giữ invariant quan trọng nhất: **không còn pending outbound ⇒ OP_WRITE OFF**.

## 8. Ví dụ Java 17+ số 1: quan sát readiness khi queue trống

Tệp **`SelectorWriteInterest.java`** chạy trên IPv4 loopback. `ServerSocketChannel` chấp nhận một client; accepted `SocketChannel` chuyển sang non-blocking rồi đăng ký với `Selector`. Chương trình **cố ý** bật OP_WRITE khi chưa có payload trong ba lượt chọn để thấy writable readiness có thể xuất hiện. Sau đó, nó tắt OP_WRITE lúc idle, enqueue chữ `PONG`, bật OP_WRITE để gửi rồi tắt lại khi queue rỗng.

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
import java.util.ArrayDeque;
import java.util.Iterator;

public class SelectorWriteInterest {
    private static void readFully(SocketChannel channel, ByteBuffer dst)
            throws IOException {
        while (dst.hasRemaining()) {
            if (channel.read(dst) == -1) {
                throw new EOFException("Incomplete reply");
            }
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback =
                InetAddress.getByAddress(new byte[] {127, 0, 0, 1});

        try (ServerSocketChannel listener = ServerSocketChannel.open();
             Selector selector = Selector.open()) {
            listener.bind(new InetSocketAddress(loopback, 0));
            int port = ((InetSocketAddress) listener.getLocalAddress())
                    .getPort();

            try (SocketChannel client = SocketChannel.open(
                         new InetSocketAddress(loopback, port));
                 SocketChannel peer = listener.accept()) {
                peer.configureBlocking(false);
                SelectionKey key = peer.register(
                        selector, SelectionKey.OP_WRITE);

                // Deliberately WRONG state: interested in OP_WRITE with
                // no application data queued.
                int idleWritable = 0;
                for (int i = 0; i < 3; i++) {
                    selector.select(1_000);
                    Iterator<SelectionKey> it =
                            selector.selectedKeys().iterator();
                    while (it.hasNext()) {
                        SelectionKey ready = it.next();
                        it.remove();
                        if (ready.isWritable()) {
                            idleWritable++;
                        }
                    }
                }

                System.out.println("Writable while idle observed: "
                        + (idleWritable > 0));

                // Correct idle state: retain OP_READ, disable OP_WRITE.
                key.interestOps(SelectionKey.OP_READ);
                System.out.println("OP_WRITE off while idle: "
                        + ((key.interestOps() & SelectionKey.OP_WRITE) == 0));

                ArrayDeque<ByteBuffer> outbound = new ArrayDeque<>();
                outbound.add(ByteBuffer.wrap(
                        "PONG".getBytes(StandardCharsets.UTF_8)));
                key.interestOps(key.interestOps() | SelectionKey.OP_WRITE);

                for (int attempt = 0;
                     attempt < 20 && !outbound.isEmpty();
                     attempt++) {
                    selector.select(1_000);
                    Iterator<SelectionKey> it =
                            selector.selectedKeys().iterator();
                    while (it.hasNext()) {
                        SelectionKey ready = it.next();
                        it.remove();
                        if (!ready.isWritable()) {
                            continue;
                        }
                        while (!outbound.isEmpty()) {
                            ByteBuffer head = outbound.peek();
                            peer.write(head);
                            if (head.hasRemaining()) {
                                break;
                            }
                            outbound.remove();
                        }
                    }
                }
                if (!outbound.isEmpty()) {
                    throw new IOException("Write did not finish");
                }

                key.interestOps(
                        key.interestOps() & ~SelectionKey.OP_WRITE);
                ByteBuffer answer = ByteBuffer.allocate(4);
                readFully(client, answer);
                answer.flip();
                System.out.println("Queue empty: " + outbound.isEmpty());
                System.out.println("OP_WRITE after drain: "
                        + ((key.interestOps() & SelectionKey.OP_WRITE) != 0));
                System.out.println("Client got: "
                        + StandardCharsets.UTF_8.decode(answer));
            }
        }
    }
}
```

Biên dịch/chạy trên JDK 17+:

```sh
javac -encoding UTF-8 SelectorWriteInterest.java
java SelectorWriteInterest
```

Stdout khi đường loopback bình thường và socket có chỗ gửi:

```text
Writable while idle observed: true
OP_WRITE off while idle: true
Queue empty: true
OP_WRITE after drain: false
Client got: PONG
```

Giải thích:

1. **`listener.accept()` ở blocking mode** chỉ dùng để dựng một socket loopback trong demo; `peer.configureBlocking(false)` bắt buộc trước khi `register(selector, OP_WRITE)`.
2. Ba lượt `select(1000)` đầu chứng minh **có thể** nhận writable readiness nhiều lần ngay cả khi không có outbound data. Đây là quan sát thông thường của socket khỏe trên loopback, không phải lời hứa rằng *mọi* đường mạng luôn writable.
3. Tắt OP_WRITE khi chưa có data nhưng giữ OP_READ. Queue sau đó chứa một `ByteBuffer.wrap("PONG")`, nên bật lại bit write.
4. Trong write callback, `write` tiêu thụ các byte từ `position` đến `limit`; phần còn lại được giữ nguyên trong queue. Chỉ sau khi `queue.isEmpty()` mới thực hiện `interestOps & ~OP_WRITE`.
5. Client nhận chính xác bốn byte `PONG` qua blocking `readFully`. Ghi xong chỉ nói rằng dữ liệu đã được chấp nhận theo channel; demo không suy ra bất kỳ business ACK nào.

Ví dụ này là bài **quan sát trạng thái selector**, không phải TCP server production, và nó cố ý có một giai đoạn cấu hình sai để minh họa. Một event loop chuẩn sẽ không đăng ký OP_WRITE khi queue rỗng ngay từ đầu.

## 9. Ví dụ Java 17+ số 2: server Selector trả response theo frame

Tệp **`SelectorFramedEcho.java`** là một server loopback đơn giản, xử lý một request có header 4-byte length-prefix và gửi lại `ACK:...`. Điểm đáng học: socket accepted đăng ký **OP_READ trước**, hàm đọc ghép đủ frame rồi đưa response đã mã hóa vào outbound queue **và bật OP_WRITE**; khi write hoàn tất, queue hết, handler **gỡ OP_WRITE**. Không có vòng while bận đợi `write` trả khác 0.

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
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.ArrayDeque;
import java.util.Iterator;

public class SelectorFramedEcho {
    private static final int MAX_FRAME = 2048;

    private static final class Connection {
        final ByteBuffer header = ByteBuffer.allocate(4);
        ByteBuffer body;
        final ArrayDeque<ByteBuffer> outbound = new ArrayDeque<>();
        String request;
        boolean requestComplete;
    }

    private static void onRead(SelectionKey key) throws IOException {
        SocketChannel channel = (SocketChannel) key.channel();
        Connection state = (Connection) key.attachment();

        while (true) {
            ByteBuffer target =
                    state.body == null ? state.header : state.body;
            int bytes = channel.read(target);
            if (bytes == -1) {
                throw new EOFException("Peer closed during request");
            }
            if (bytes == 0) {
                return;
            }
            if (target.hasRemaining()) {
                continue;
            }

            if (state.body == null) {
                state.header.flip();
                int length = state.header.getInt();
                if (length <= 0 || length > MAX_FRAME) {
                    throw new IOException("Invalid frame length");
                }
                state.body = ByteBuffer.allocate(length);
            } else {
                state.body.flip();
                state.request = StandardCharsets.UTF_8.newDecoder()
                        .onMalformedInput(CodingErrorAction.REPORT)
                        .onUnmappableCharacter(CodingErrorAction.REPORT)
                        .decode(state.body).toString();

                byte[] payload = ("ACK:" + state.request)
                        .getBytes(StandardCharsets.UTF_8);
                ByteBuffer reply = ByteBuffer.allocate(4 + payload.length);
                reply.putInt(payload.length);
                reply.put(payload);
                reply.flip();

                state.outbound.addLast(reply);
                state.requestComplete = true;
                // Pause reads for this one-request demo and enable writes.
                key.interestOps(
                        (key.interestOps() & ~SelectionKey.OP_READ)
                                | SelectionKey.OP_WRITE);
                return;
            }
        }
    }

    private static void onWrite(SelectionKey key) throws IOException {
        SocketChannel channel = (SocketChannel) key.channel();
        Connection state = (Connection) key.attachment();

        while (!state.outbound.isEmpty()) {
            ByteBuffer head = state.outbound.peekFirst();
            channel.write(head);
            if (head.hasRemaining()) {
                // Partial/zero write: keep OP_WRITE until next readiness.
                return;
            }
            state.outbound.removeFirst();
        }

        // No pending bytes. Keeping OP_WRITE would cause a hot loop.
        key.interestOps(key.interestOps() & ~SelectionKey.OP_WRITE);
    }

    private static void readFully(SocketChannel channel, ByteBuffer target)
            throws IOException {
        while (target.hasRemaining()) {
            if (channel.read(target) == -1) {
                throw new EOFException("Incomplete response");
            }
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback =
                InetAddress.getByAddress(new byte[] {127, 0, 0, 1});
        String expected = "Xin chao \u20AC";

        try (Selector selector = Selector.open();
             ServerSocketChannel server = ServerSocketChannel.open()) {
            server.bind(new InetSocketAddress(loopback, 0));
            server.configureBlocking(false);
            server.register(selector, SelectionKey.OP_ACCEPT);
            int port = ((InetSocketAddress) server.getLocalAddress())
                    .getPort();

            try (SocketChannel client = SocketChannel.open(
                         new InetSocketAddress(loopback, port))) {
                byte[] data = expected.getBytes(StandardCharsets.UTF_8);
                ByteBuffer outgoing = ByteBuffer.allocate(4 + data.length);
                outgoing.putInt(data.length).put(data).flip();
                while (outgoing.hasRemaining()) {
                    client.write(outgoing); // Client is blocking.
                }

                SocketChannel accepted = null;
                SelectionKey peerKey = null;
                Connection state = null;

                try {
                    for (int i = 0;
                         i < 20 && (state == null
                                 || !state.requestComplete
                                 || !state.outbound.isEmpty());
                         i++) {
                        if (selector.select(2_000) == 0) {
                            throw new IOException("Selector timeout");
                        }

                        Iterator<SelectionKey> it =
                                selector.selectedKeys().iterator();
                        while (it.hasNext()) {
                            SelectionKey key = it.next();
                            it.remove();
                            if (key.isAcceptable()) {
                                accepted = server.accept();
                                if (accepted != null) {
                                    accepted.configureBlocking(false);
                                    state = new Connection();
                                    peerKey = accepted.register(
                                            selector, SelectionKey.OP_READ,
                                            state);
                                }
                            } else {
                                if (key.isReadable()) {
                                    onRead(key);
                                }
                                if (key.isValid() && key.isWritable()) {
                                    onWrite(key);
                                }
                            }
                        }
                    }

                    if (state == null || !state.requestComplete
                            || !state.outbound.isEmpty()) {
                        throw new IOException("Incomplete event loop");
                    }

                    ByteBuffer length = ByteBuffer.allocate(4);
                    readFully(client, length);
                    length.flip();
                    int n = length.getInt();
                    if (n < 0 || n > MAX_FRAME) {
                        throw new IOException("Invalid response length");
                    }

                    ByteBuffer body = ByteBuffer.allocate(n);
                    readFully(client, body);
                    body.flip();
                    String response = StandardCharsets.UTF_8
                            .newDecoder()
                            .onMalformedInput(CodingErrorAction.REPORT)
                            .decode(body).toString();

                    System.out.println("Request matches: "
                            + expected.equals(state.request));
                    System.out.println("Response matches: "
                            + ("ACK:" + expected).equals(response));
                    System.out.println("Queued frames: "
                            + state.outbound.size());
                    System.out.println("OP_WRITE after flush: "
                            + ((peerKey.interestOps()
                                    & SelectionKey.OP_WRITE) != 0));
                } finally {
                    if (accepted != null) {
                        accepted.close();
                    }
                }
            }
        }
    }
}
```

Chạy:

```sh
javac -encoding UTF-8 SelectorFramedEcho.java
java SelectorFramedEcho
```

Stdout xác định trên một lần chạy thành công:

```text
Request matches: true
Response matches: true
Queued frames: 0
OP_WRITE after flush: false
```

Đọc kỹ những chi tiết sau:

- `server.configureBlocking(false)` là điều kiện để đăng ký OP_ACCEPT. Socket được `server.accept()` trả về **vẫn bắt đầu ở blocking mode**; ví dụ gọi `accepted.configureBlocking(false)` trước khi đăng ký OP_READ.
- `Connection` là **attachment riêng** của từng accepted key: giữ buffer header/body, queue outbound, trạng thái request. Nó **không** dùng queue toàn server trộn byte của các client.
- `onRead` tiếp tục khi một lần đọc chưa đủ header/body; khi đọc ra `0`, nó dừng và chờ event kế tiếp, không spin. Nếu EOF xảy ra giữa frame thì ném `EOFException`.
- Khi đủ payload, ứng dụng build một response frame gồm 4 byte length big-endian và body UTF-8. **Không gửi khi chưa có dữ liệu**; interest trở thành OP_WRITE chỉ sau khi enqueue.
- `onWrite` xử lý **partial/zero writes**, giữ lại `ByteBuffer.position`. Khi không còn frame trong `outbound`, nó tắt OP_WRITE.
- Demo chỉ xử lý **một request**; sau khi parse frame, nó tạm tắt OP_READ để thể hiện rõ state transition. Server production có thể bật OP_READ lại khi sẵn sàng nhận frame kế, tùy backpressure và quota.

Không biến ví dụ ngắn thành hệ thống production bằng cách bỏ qua timeout, authentication, maximum concurrent clients, queue capacity và xử lý disconnect. Kịch bản đã giới hạn một client, một frame và loopback để có kết quả kiểm chứng chắc chắn.

## 10. Lưu ý về selectedKeys và thay đổi interest trong lúc xử lý

Một vòng event loop cơ bản:

```java
// Pseudo-code: handler methods và selector đã tồn tại.
while (running) {
    selector.select();

    Iterator<SelectionKey> iterator =
            selector.selectedKeys().iterator();
    while (iterator.hasNext()) {
        SelectionKey key = iterator.next();
        iterator.remove();

        if (!key.isValid()) {
            continue; // Đã cancel/close.
        }
        try {
            if (key.isAcceptable()) onAccept(key);
            if (key.isValid() && key.isReadable()) onRead(key);
            if (key.isValid() && key.isWritable()) onWrite(key);
        } catch (IOException e) {
            closeConnection(key);
        }
    }
}
```

Mẫu trên là **khung minh họa, không chạy độc lập**: `running`, `onAccept`, `onRead`, `onWrite` và `closeConnection` là các thành phần ứng dụng. Điểm chính:

- **Loại key khỏi selected-key set** bằng iterator trước/sau khi xử lý. Nếu quên, behavior của những vòng chọn tiếp theo khó theo dõi; không dùng `selectedKeys().clear()` bừa bãi nếu chưa xử lý mọi key.
- Một key có thể báo nhiều readiness bits. Kiểm tra `key.isValid()` sau những bước có thể đóng/cancel channel trước khi xử lý bước sau.
- `interestOps` thay đổi trong callback sẽ tác động đến lựa chọn readiness tiếp theo. `isWritable()` đang đọc ready set đã được selector trả về, **không** có nghĩa cứ bật interestOps ngay lập tức là handler đang chạy phải gọi onWrite.
- Tránh kích hoạt OP_WRITE rồi **gọi write lặp liên tục trong cùng lượt** khi kernel đã báo 0. Hãy quay về selector để nhận readiness mới.
- Không xử lý vô hạn lượng dữ liệu cho một client trong một ready callback; dùng budget/quota nếu cần fairness.

## 11. Khi worker thread tạo response: dùng mailbox và selector.wakeup()

Đây là tình huống rất phổ biến: một thread pool tính toán response sau khi đã nhận request, trong khi selector thread đang `select()` để chờ I/O. **Worker không nên đồng thời sửa `ByteBuffer.position`, queue và state của accepted key**. Thiết kế rõ ownership:

```text
Worker thread:
  compute response -> immutable byte[]/frame
          |
          v
Thread-safe mailbox (ConcurrentLinkedQueue<Runnable>)
          |
          | selector.wakeup()
          v
Selector owner thread:
  drain mailbox:
    if key valid:
      outbound.add(frame)
      interestOps |= OP_WRITE
  selector.select()
          |
          v
  writable event -> write queue -> drain -> interestOps &= ~OP_WRITE
```

Ví dụ **snippet minh họa** về giao việc (không phải chương trình chạy độc lập):

```java
// mailbox: ConcurrentLinkedQueue<Runnable>
// selector, key, connection: những đối tượng do event-loop thread sở hữu.
// payload được copy/đóng băng trước khi đưa vào mailbox.
byte[] ownedCopy = java.util.Arrays.copyOf(
        responseBytes, responseBytes.length);

mailbox.add(() -> {
    if (!key.isValid()) return; // Connection có thể đã đóng.
    connection.outbound.addLast(ByteBuffer.wrap(ownedCopy));
    key.interestOps(key.interestOps() | SelectionKey.OP_WRITE);
});
selector.wakeup();
```

**`wakeup()` không phải lệnh gửi byte**. Nó khiến một lượt `select()` đang chờ (hoặc lượt chọn tiếp theo, theo hợp đồng API) quay về để owner thread có cơ hội chạy mailbox và thay đổi interest. Tạo tác vụ rồi gọi `selector.wakeup()` giúp tránh để response nằm trong queue mà selector vẫn đợi vô hạn chỉ vì chưa có I/O readiness mới.

Thiết kế vòng lặp phải **drain mailbox ở điểm xác định**, ví dụ trước mỗi lần `select` hoặc ngay sau khi `select` trả về. Nếu có task đến đúng thời điểm chuyển vào select, cơ chế wakeup giúp tránh mất tiến triển. Không coi selector thread-safe cho mọi mutation chỉ vì mailbox thread-safe: một owner nên quyết định trạng thái socket, và dữ liệu trao đổi phải có công bố an toàn.

Đừng để callback của một thread khác gọi `socketChannel.write` đồng thời với owner writer. Một connection cần một writer chịu trách nhiệm ordering của **từng frame**.

## 12. Không có queue vô hạn: backpressure cho từng connection

Tắt OP_WRITE khi idle giải quyết **busy-loop**, nhưng không giải quyết việc worker tạo response **nhanh hơn tốc độ client nhận**. Nếu queue outbound tăng vô hạn:

- Mỗi response/frame giữ byte array/ByteBuffer trong heap.
- Client đọc chậm khiến write trả 0, OP_WRITE vẫn bật (đúng) nhưng queue có thể tăng.
- Khi nhiều client cùng chậm, tổng bộ nhớ và GC có thể tăng đến mức dịch vụ suy yếu.

Đặt **giới hạn byte chờ gửi** thay vì chỉ giới hạn số frame. Một queue 100 frame có thể chứa 100 byte hoặc 100 MiB nếu kích thước frame không bị giới hạn.

```text
Ví dụ chính sách:
- perConnectionPendingBytes <= 1 MiB
- globalPendingBytes <= ngân sách đã thiết kế
- frameBytes <= giới hạn giao thức
- highWatermark: tạm ngừng OP_READ / giảm nguồn tạo response
- lowWatermark: mở lại OP_READ khi outbound giảm
- quá hạn/chậm quá lâu: đóng peer hoặc báo lỗi theo hợp đồng ứng dụng
```

Các mốc trên là **ví dụ chính sách**, không phải con số chuẩn. Cần cân nhắc traffic, SLA, số connection, memory, kích thước TLS/compression buffers và khả năng xử lý của peer. Giảm OP_READ có thể chặn tốc độ tạo request, nhưng không tự giải quyết những producer độc lập như notification hoặc push; chúng vẫn phải chịu quota.

**Không tắt OP_WRITE khi queue vẫn còn byte** chỉ để tiết kiệm CPU: việc tắt ở sai thời điểm có thể làm pending data **không bao giờ được gửi tiếp** nếu không có tác nhân nào khác bật lại. Khi backlog tồn tại mà kernel chưa ghi được, hãy giữ OP_WRITE và để selector chờ readiness.

## 13. Read/write cùng lúc trên một key: giữ đúng mặt nạ sự kiện

Một ứng dụng TCP vừa đọc request vừa gửi push có thể giữ OP_READ và chỉ bật thêm OP_WRITE khi có pending:

```text
Nhàn rỗi:               OP_READ
Có outbound:            OP_READ | OP_WRITE
Kernel write tạm hết:   OP_READ | OP_WRITE  (còn pending)
Gửi xong outbound:      OP_READ
Đầu đọc bị backpressure: OP_WRITE            (nếu còn pending)
Chờ không đọc/ghi:      0                   (chỉ nếu chủ động quản lý)
```

Nếu dùng `key.interestOps(OP_WRITE)` khi enqueue mà quên OR với mặt nạ hiện tại, hệ thống có thể **vô tình tắt OP_READ** và ngừng xử lý request mới. Ngược lại, nếu luôn ghi `interestOps(OP_READ | OP_WRITE)` sau mỗi event, bạn bật lại OP_WRITE ngay cả khi queue rỗng, gây busy-loop.

Một state machine cần quyết định **từng bit theo điều kiện**: OP_READ theo chính sách đọc/inbound backpressure; OP_WRITE theo byte pending; OP_CONNECT chỉ khi connect còn đang diễn ra; OP_ACCEPT cho listener. Đừng đặt ý nghĩa “đang bận xử lý request” lên một bit readiness không liên quan.

Một số thiết kế muốn **không đọc** thêm khi output queue đạt high watermark. Khi giảm dưới low watermark, cần bật OP_READ trở lại bằng đúng bitmask và kiểm tra key còn hợp lệ. Cách làm đó khác hoàn toàn việc bật OP_WRITE thường trực.

## 14. Đường gửi: độ dài frame, mã hóa, ownership và không interleave

Trước khi enqueue, tạo **một representation nhất quán** của response:

```java
// Snippet: tạo frame với header 4-byte big-endian.
byte[] payload = message.getBytes(StandardCharsets.UTF_8);
ByteBuffer frame = ByteBuffer.allocate(4 + payload.length);
frame.putInt(payload.length); // 4-byte prefix, big-endian mặc định.
frame.put(payload);
frame.flip();                 // Ready to be consumed by write().
outbound.addLast(frame);     // Từ đây event loop sở hữu frame.
```

Nếu message chứa UTF-8 đa byte, `payload.length` là số byte **đúng** cần gửi. Không dùng `String.length()` thay độ dài khi protocol định nghĩa byte length. Phải kiểm tra `payload.length`, số frame và tổng pending bytes trước khi cấp phát/enqueue.

Sau `flip`, **không gọi `flip` lần thứ hai** khi `write` đã ghi một phần; ByteBuffer còn giữ `position` chính xác. Không dùng chung một ByteBuffer mutable giữa hai connection nếu cả hai đang thay `position`, kể cả khi cùng một underlying byte[] bất biến.

Với nhiều producer, queue response theo một order rõ (theo request ID, theo enqueue order đã đồng bộ, theo ưu tiên), và đảm bảo **một writer** phát ra trọn frame theo thứ tự đã chọn. TCP giữ thứ tự byte trên một connection nhưng không biết header, payload hay ranh giới message ở ứng dụng.

## 15. Xử lý đóng, hủy và lỗi để không còn OP_WRITE ma

Khi một connection bị đóng hoặc hủy:

1. Hủy/cancel `SelectionKey` và đóng `SocketChannel` theo luồng xử lý cleanup được định nghĩa. Key đã cancel sẽ không nhận readiness hợp lệ như trước.
2. Giải phóng outbound buffers và giảm đúng counter pending bytes; không giữ tham chiếu vào queue trong task/attachment cũ.
3. Worker completion đến **sau** khi socket đã đóng phải thấy `key.isValid()==false` hoặc connection generation/token không còn đúng, rồi **không được enqueue** vào state cũ.
4. Khi `write` ném `IOException`, không loop retry vô hạn trên cùng buffer. Phải quyết định đóng connection, báo lỗi nghiệp vụ hoặc cơ chế retry ở tầng ứng dụng theo protocol.
5. Khi `write` trả `0` và queue còn byte, đó **không phải lỗi**; chờ readiness phù hợp. Nếu key không được kích hoạt lại mãi do peer chậm, áp dụng deadline, rate limit và peer-close policy.
6. Nếu cần **graceful shutdown**, không đóng ngay socket đang có pending response mà chưa quyết định policy flush/deadline. Nhưng cũng không được chờ vô hạn cho peer không đọc.

Đôi khi OP_WRITE liên tục ready nhưng code vẫn không thể giảm queue vì mỗi lần enqueue nhiều hơn ghi. Lúc đó vấn đề là **backpressure/throughput**, không chỉ busy-loop: quan sát bytes queued, rate producer/consumer, channel write returns và độ sâu outbound để tìm nguyên nhân.

## 16. Kiểm thử lỗi CPU và tính đúng đắn của việc tắt OP_WRITE

Không nên chỉ assert “một response đã trả đúng”. Cần ít nhất những ca:

| Ca kiểm thử | Kỳ vọng |
| --- | --- |
| Socket không có outbound byte | Interest **không** có OP_WRITE; `select` không thức dậy vô ích vì write |
| Enqueue frame đầu tiên | OP_WRITE được bật; selector có thể tiến triển để gửi |
| Ghi một phần / ghi 0 | ByteBuffer giữ phần chưa gửi; OP_WRITE vẫn bật vì còn pending |
| Ghi xong toàn bộ queue | OP_WRITE được gỡ ngay; OP_READ còn nguyên nếu vẫn muốn đọc |
| Nhiều response lần lượt | Bật/tắt lặp lại đúng qua nhiều chu kỳ; không resend byte |
| Producer từ worker khác trong khi selector chờ | Mailbox + `wakeup` đánh thức event loop, response được gửi |
| Client đọc chậm | Queue có trần; overload/backpressure và deadline hoạt động |
| Cancel key khi worker đang tính response | Không gửi vào connection đã đóng; không sinh `CancelledKeyException` không được xử lý |
| Có hai client, một client có backlog lớn | Giới hạn write budget để client kia vẫn có cơ hội tiến triển |

**Đo lường hữu ích**: số `select` mỗi giây, số selected keys, tỉ lệ writable events nhưng `queue.isEmpty()`, CPU của event-loop thread, queue length/bytes, throughput bytes written, số write trả 0, p95/p99 latency. Nếu idle có hàng trăm nghìn lượt select/s và phần lớn là OP_WRITE không có dữ liệu, đó là dấu hiệu rất rõ về cấu hình interest sai.

Kiểm tra hiệu năng phải đối chiếu với số kết nối, kích thước buffer, tải, TLS, CPU profiler và môi trường mạng. Không có một tỷ lệ CPU cố định mà từ đó có thể kết luận mọi trường hợp đều do OP_WRITE.

## 17. Sai lầm thường gặp và cách sửa

1. **Đăng ký mọi socket `OP_READ | OP_WRITE` ngay khi accept.** Khi chưa có pending, OP_WRITE vẫn thường ready. Khởi tạo OP_READ rồi chỉ OR OP_WRITE khi cần.
2. **Kiểm tra `queue.isEmpty()` nhưng không gỡ OP_WRITE.** Event loop tiếp tục nhận ready event. Gỡ bit write sau khi queue drained.
3. **`interestOps(OP_WRITE)` thay vì `interestOps(interestOps() | OP_WRITE)`.** Vô tình bỏ OP_READ. Sửa bằng bitmask.
4. **Tắt OP_WRITE sau mọi write event, kể cả partial write.** Phần byte còn lại có thể bị treo. Chỉ tắt khi queue trống.
5. **Loop liên tục `while(write(buffer)==0)`.** CPU spin khi kernel chưa còn chỗ. Trở về `select` và giữ buffer.
6. **Tạo ByteBuffer mới từ đầu mỗi lần gửi tiếp.** Gửi trùng prefix/body. Giữ `position` gốc của buffer chưa gửi hết.
7. **Quên `iterator.remove()` cho selected-key set.** Hành vi selected readiness và vòng lặp khó đoán. Xử lý rồi remove mọi key.
8. **Gửi hai frame song song vào cùng channel từ nhiều thread.** Các byte header/body có thể xen nhau. Dùng một writer/connection.
9. **Worker chỉ enqueue mà không `wakeup()`.** Selector có thể ngủ trong khi đã có response; chuyển việc qua mailbox và wakeup.
10. **Worker trực tiếp sửa queue/key cùng lúc owner selector xử lý.** Race về trạng thái/ByteBuffer/interest. Sử dụng ownership nhất quán.
11. **Giữ OP_WRITE khi queue không có data để “phòng khi sau này gửi”.** Sự kiện writable không phải notification về data mới. Data mới phải tự kích hoạt interest/wakeup.
12. **Cho output queue tăng vô hạn vì client chậm.** Hết RAM/GC nặng; đặt giới hạn bytes, high/low watermarks và overload policy.
13. **Đóng connection ngay sau enqueue mà chưa flush.** Response có thể không được gửi theo hợp đồng. Quy định shutdown/drain riêng.
14. **Nhầm writable với peer đã nhận hoặc đã commit.** TCP writable chỉ thể hiện khả năng ghi thêm ở phía gửi; cần ACK ứng dụng khi nghiệp vụ yêu cầu.
15. **Dùng `selector.selectNow()` liên tục để “tránh chặn”.** Khi không có event, đó cũng có thể tạo busy loop. Hãy dùng `select` blocking + wakeup/timer phù hợp.
16. **Bật OP_WRITE lại mỗi vòng chọn dù queue rỗng.** Tự tái tạo lỗi sau khi vừa sửa. Coi trạng thái queue là nguồn quyết định interest.

## 18. Tình huống suy luận nhanh

**Hỏi:** Một server có 10.000 kết nối idle, mỗi key đăng ký `OP_READ | OP_WRITE`. Tại sao CPU vẫn cao dù không có request?

**Đáp:** Nhiều socket có send buffer trống nên writable. `Selector.select` có thể liên tục báo OP_WRITE, event loop xử lý hàng nghìn key không có outbound byte. Chỉ đăng ký OP_READ khi idle; bật OP_WRITE khi enqueue mới.

**Hỏi:** Sau khi `channel.write(head)` trả 0, có nên tắt OP_WRITE không?

**Đáp:** **Không** nếu `head.hasRemaining()`. Queue còn pending nên giữ OP_WRITE và quay lại selector. Có thể tắt nếu đã xóa/hủy toàn bộ pending theo một policy lỗi rõ ràng.

**Hỏi:** Vừa gửi xong một buffer, queue còn hai buffer nữa. Có thể tắt OP_WRITE để CPU giảm không?

**Đáp:** Không, vì vẫn có pending outbound. Tiếp tục ghi trong budget hoặc giữ OP_WRITE để nhận writable readiness tiếp theo.

**Hỏi:** Event loop đang `selector.select()` chờ OP_READ, worker mới tạo response; sao response chưa được gửi?

**Đáp:** Nếu worker chỉ thêm vào queue ngoài mà không thông báo event loop, selector có thể tiếp tục chờ. Dùng thread-safe mailbox, owner bật OP_WRITE và `selector.wakeup()` để tiến triển.

**Hỏi:** Gỡ OP_WRITE thì OP_READ có mất không?

**Đáp:** Không nếu dùng `key.interestOps(key.interestOps() & ~SelectionKey.OP_WRITE)`. Nó chỉ xóa bit write.

**Hỏi:** Nếu `selectedKeys` còn chứa writable key cũ, chỉ tắt interest đã đủ để nó biến khỏi selected set chưa?

**Đáp:** Không. Interest set và selected-key set khác nhau. Handler vẫn cần remove key khỏi selected-key set sau khi xử lý.

## 19. Checklist triển khai và kết luận

Khi review một TCP selector server, kiểm tra theo trình tự:

1. **Accepted `SocketChannel` đã `configureBlocking(false)` chưa?** Channel blocking không được đăng ký với selector.
2. **Khi mới accept và chưa có outbound, interest có chỉ OP_READ không?** Tránh mặc định bật OP_WRITE.
3. **Ai sở hữu outbound queue?** Một owner event loop/connection, không mutate ByteBuffer từ nhiều thread.
4. **Khi thêm response đầu tiên, có bật OP_WRITE và wakeup đúng lúc không?** Worker thread đi qua mailbox.
5. **Khi write chưa hết, có giữ ByteBuffer và OP_WRITE không?** Partial/zero write không được spin hay bỏ byte.
6. **Khi queue rỗng, có xóa OP_WRITE ngay bằng `& ~OP_WRITE` không?** Giữ các interest khác hợp lệ.
7. **Có remove selected keys sau xử lý không?** Không nhầm readiness set với interest set.
8. **Có bounded pending bytes và backpressure cho slow client không?** Không để queue phình vô hạn.
9. **Có tránh starve các connection khác bằng write budget không?** Một peer với backlog lớn không được độc chiếm event loop.
10. **Có xử lý close, cancel, timeout và worker completion đến muộn không?** Không bật interest trên key không hợp lệ.
11. **Có test idle CPU, slow reader, partial write và các chu kỳ enqueue→drain không?** Đó là tình huống phát hiện lỗi OP_WRITE hiệu quả nhất.

**Kết luận:** `OP_WRITE` là **tín hiệu socket có thể ghi**, không phải **tín hiệu ứng dụng đang có thứ phải gửi**. Ứng dụng tự quản lý data pending; **bật OP_WRITE khi queue chuyển sang có dữ liệu, giữ nó nếu còn byte, và tắt ngay sau khi drain**. Quy tắc nhỏ này thường quyết định một selector event loop idle thực sự ngủ chờ hay chạy nóng ở CPU cao.

### API chuẩn để đối chiếu

- [Java SE 17 — `SelectionKey`, `OP_WRITE`, `interestOps()` và `readyOps()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectionKey.html)
- [Java SE 17 — `Selector`, `select()`, `selectedKeys()` và `wakeup()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html)
- [Java SE 17 — `SocketChannel` và `write(ByteBuffer)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html)
- [Java SE 17 — `ByteBuffer` và vị trí `position/limit`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html)
- [Java SE 17 — `ServerSocketChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ServerSocketChannel.html).