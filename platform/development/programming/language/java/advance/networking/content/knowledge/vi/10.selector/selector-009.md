# Giới hạn hàng đợi ghi và điều tiết bên đọc khi bên nhận chậm với Java NIO Selector

Trong một TCP server sử dụng `Selector`, khả năng đọc dữ liệu nhanh không có nghĩa khả năng gửi dữ liệu cho peer cũng nhanh tương ứng. Khi peer nhận chậm, `SocketChannel.write(ByteBuffer)` ở chế độ non-blocking có thể chỉ ghi một phần dữ liệu hoặc trả về `0`. Nếu ứng dụng tiếp tục đọc, xử lý rồi bổ sung dữ liệu vào danh sách chờ ghi **không giới hạn**, mỗi kết nối chậm có thể giữ ngày càng nhiều byte trong heap/direct memory và cuối cùng làm cạn bộ nhớ toàn server.

Bài này giải thích cách xây **backpressure** trong event loop NIO: đặt **hard cap** cho hàng đợi outbound, theo dõi số byte chưa ghi, bật `OP_WRITE` chỉ khi còn dữ liệu chờ, tạm bỏ `OP_READ` khi hàng đợi cao và bật lại khi nó giảm. Đích cuối cùng là giữ **đúng dữ liệu, đúng thứ tự, sử dụng bộ nhớ có giới hạn và tránh vòng lặp CPU bận**, chứ không đơn giản gọi `write()` càng nhiều lần càng tốt.

Ví dụ dùng **Java 17+**, `SocketChannel` non-blocking, `SelectionKey` và `Selector`. Hai chương trình hoàn chỉnh ở phần sau minh họa (1) watermark với bộ đệm mô phỏng và (2) một kết nối echo TCP thật trên loopback được điều tiết bằng event loop.

## 1. Dòng dữ liệu và lý do phải có backpressure

Một server echo hoặc một proxy TCP có thể hình dung như sau:

~~~text
TCP peer/nguồn gửi
       │
       ▼
kernel receive buffer ── OP_READ ──► read(ByteBuffer)
                                        │
                                        ▼
                              xử lý / tạo response
                                        │
                                        ▼
                             outbound queue [ByteBuffer...]
                                        │
                          OP_WRITE, write() từng phần
                                        ▼
                               kernel send buffer
                                        │
                                        ▼
                                TCP peer nhận chậm
~~~

Nếu tốc độ sinh dữ liệu lớn hơn tốc độ `write` thực sự nhận dữ liệu vào kernel send buffer, backlog tăng. Gọi:

- `λ` (bytes/s): tốc độ ứng dụng tạo dữ liệu outbound.
- `μ` (bytes/s): tốc độ mà `SocketChannel.write` nhận từ hàng đợi ứng dụng.
- `Q` (bytes): số byte outbound chưa được `write` tiêu thụ.

Trong giai đoạn `λ > μ`, hàng đợi xấp xỉ tăng theo `(λ−μ) × thời gian` cho đến khi có điều tiết hoặc giới hạn. Ví dụ giả định `λ = 5 MiB/s`, `μ = 1 MiB/s`, backlog có thể tăng khoảng `4 MiB/s`. Sau một phút, riêng một client chậm có thể tạo khoảng 240 MiB dữ liệu chờ ở tầng ứng dụng nếu không có giới hạn. Đây chỉ là phép tính tải minh họa, không phải dự báo chính xác về TCP/OS.

**Điểm rất quan trọng:** `SocketChannel.write(...)` trả về số byte đã được truyền **từ ByteBuffer sang channel/OS**, không phải số byte remote application đã đọc. TCP, kernel send buffer, receiver window và mạng còn tiếp tục xử lý. Vì vậy `Q=0` không đồng nghĩa peer đã nhận hết; nó chỉ có nghĩa **hàng đợi ghi của ứng dụng** hiện đã được giải phóng.

Cần phân biệt ba lớp bộ đệm:

| Lớp | Ai quản lý? | Có thể điều tiết bằng gì? |
| --- | --- | --- |
| Buffer dữ liệu đã đọc và trạng thái parser | Ứng dụng | Giới hạn kích thước frame, input buffer, số request đang xử lý |
| Outbound queue gồm `ByteBuffer` chưa ghi | Ứng dụng | Byte cap, high/low watermark, chính sách full queue, `OP_READ` |
| TCP send/receive buffer | Kernel/OS | TCP flow control, socket options như `SO_SNDBUF` (hint), cấu hình OS |

`SO_SNDBUF` không phải thay thế cho giới hạn outbound queue trong heap. Cũng không thể “khóa cứng memory” chỉ bằng tắt `OP_READ` nếu đã có nhiều task/response được tạo trước đó.

## 2. Cơ sở API: non-blocking write, ready set và interest set

### 2.1. `SocketChannel.write(ByteBuffer)` có thể ghi một phần

Giả sử buffer chứa 1.000 byte còn lại:

~~~java
int written = channel.write(buffer);
~~~

Có thể nhận `written=1000`, một số nhỏ hơn hoặc `0`. `ByteBuffer.position()` tăng đúng bằng số byte được viết, và `remaining()` phản ánh phần chưa gửi. **Không `clear()` hoặc `flip()` lại buffer này** sau partial write; làm vậy sẽ phá nội dung và có thể gửi trùng hoặc mất byte.

Ví dụ cơ chế:

~~~text
ByteBuffer: [ A B C D E F G H ]  position=0, limit=8
write() => 3
ByteBuffer: [ A B C | D E F G H ]  position=3, limit=8
write() => 0
ByteBuffer: [ A B C | D E F G H ]  position=3, limit=8
Sau OP_WRITE, write() => 5
ByteBuffer: [ A B C D E F G H | ] position=8, limit=8
~~~

Khi `remaining()==0`, mới được loại buffer đầu hàng đợi. Với NIO, **partial write là hành vi bình thường**, không phải lỗi. Lặp gọi `write` liên tục khi nó trả `0` là busy-spin; cần dừng và nhờ `Selector` báo khả năng ghi trong lượt sau.

### 2.2. `SelectionKey.OP_WRITE` chỉ là đăng ký quan tâm readiness

Sau khi channel non-blocking đã đăng ký với `Selector`:

~~~java
SelectionKey key =
        channel.register(selector, SelectionKey.OP_READ);
~~~

Một `SelectionKey` có:

- **Interest set**: các bit thao tác ứng dụng muốn `Selector` theo dõi, đọc bằng `interestOps()`.
- **Ready set**: các thao tác hệ điều hành/selector đánh dấu đã sẵn sàng trong lượt `select`, đọc bằng `readyOps()` hoặc `isReadable()/isWritable()`.
- **Attachment**: gắn object trạng thái kết nối, ví dụ outbound queue.

Hai thao tác thông dụng trên Java 17 (có từ Java 11):

~~~java
key.interestOpsOr(SelectionKey.OP_WRITE);    // thêm OP_WRITE
key.interestOpsAnd(~SelectionKey.OP_WRITE);  // bỏ OP_WRITE

key.interestOpsAnd(~SelectionKey.OP_READ);   // tạm ngừng đọc
key.interestOpsOr(SelectionKey.OP_READ);     // cho đọc trở lại
~~~

Đó là **đoạn minh họa trong phương thức** có `SelectionKey key` hợp lệ. `interestOpsOr/And` thực hiện phép cập nhật bit tương ứng; nếu dùng `key.interestOps(newOps)`, phải giữ các bit còn cần thiết (`OP_CONNECT`, `OP_READ`, `OP_WRITE`) thay vì ghi đè bừa bãi. Không thêm `OP_ACCEPT` lên `SocketChannel`; bit này dành cho `ServerSocketChannel`.

**Quy tắc quan trọng:** chỉ bật `OP_WRITE` khi outbound queue **không rỗng**, và tắt ngay khi queue rỗng. TCP socket thường được đánh dấu có thể ghi trong phần lớn thời gian. Nếu luôn đăng ký `OP_WRITE` dù không có dữ liệu, `select` có thể trả về liên tục và làm một CPU core chạy sát 100% mà ứng dụng chẳng gửi gì.

`OP_READ` có thể sẵn sàng khi có dữ liệu, EOF, shutdown phía peer hoặc lỗi chờ xử lý. `OP_WRITE` cũng có thể báo readiness do sự kiện đóng/lỗi. Readiness không bảo đảm lời gọi `read/write` sẽ chuyển được byte; vẫn phải xử lý `0`, `-1` và `IOException`.

### 2.3. Vòng lặp `Selector` phải xử lý key có kỷ luật

Một event loop điển hình:

~~~java
selector.select(timeoutMillis);

Iterator<SelectionKey> it =
        selector.selectedKeys().iterator();
while (it.hasNext()) {
    SelectionKey key = it.next();
    it.remove();  // loại khỏi selected set sau khi lấy ra
    if (!key.isValid()) {
        continue;
    }

    if (key.isReadable()) {
        onRead(key);
    }
    if (key.isValid() && key.isWritable()) {
        onWrite(key);
    }
}
~~~

Đây là **pseudocode đặt trong event loop**, `onRead/onWrite` phải được định nghĩa. Sau `onRead`, key có thể bị cancel/close do EOF hoặc lỗi; vì vậy phải kiểm tra lại `isValid()` trước khi xét `isWritable()`. Khi `select` trả về 0 vì timeout/wakeup, xử lý timers hoặc công việc chờ khác; không suy ra là socket có lỗi.

Nếu đã đăng ký `OP_CONNECT` cho non-blocking connect, cần gọi `finishConnect()` thành công trước khi chuyển sang logic đọc/ghi. Ví dụ chương trình độc lập phía dưới dùng `ServerSocketChannel.accept()`, nên accepted channel đã kết nối và không cần nhánh `OP_CONNECT`.

## 3. Bounded outbound queue: giới hạn **byte**, không chỉ số phần tử

Một cấu trúc per-connection đơn giản:

~~~java
final Deque<ByteBuffer> outbound = new ArrayDeque<>();
long pendingBytes = 0;
~~~

Khi thêm một buffer đã đặt đúng `position/limit`:

~~~java
int bytesToAdd = data.remaining();
if (bytesToAdd > MAX_PENDING - pendingBytes) {
    // Không enqueue: áp dụng policy full queue.
} else {
    outbound.addLast(data);
    pendingBytes += bytesToAdd;
}
~~~

Phần này là **pseudocode**: `data` phải có ownership rõ ràng và `MAX_PENDING` là hạn mức của connection. Phép so sánh `bytesToAdd > MAX_PENDING - pendingBytes` tránh phép cộng có thể tràn số trong kiểu `int/long` nếu đầu vào không đáng tin.

Khi viết được `n` byte:

~~~java
int n = channel.write(outbound.peekFirst());
pendingBytes -= n;

if (!outbound.peekFirst().hasRemaining()) {
    outbound.removeFirst();
}
~~~

Chỉ giảm `pendingBytes` theo **số byte thực sự được `write` chấp nhận**, không giảm theo `ByteBuffer.capacity()`, độ dài dữ liệu ban đầu, số message hay `limit()`. Khi hàng đợi còn buffer đầu đã ghi một phần, `remaining()` của nó biểu diễn số byte chính xác phải gửi tiếp.

### 3.1. Những bất biến cần kiểm thử

Trong mỗi kết nối, khi được quản lý bởi một event-loop thread:

1. `0 <= pendingBytes <= MAX_PENDING`.
2. `pendingBytes == sum(buffer.remaining())` của các buffer đang nằm trong outbound queue.
3. ByteBuffer ở đầu queue luôn chứa **phần dữ liệu chưa ghi**; không `clear`/`flip` bừa bãi.
4. Queue không rỗng thì có thể cần `OP_WRITE` (nếu socket đã kết nối và còn mở).
5. Queue rỗng thì phải bỏ `OP_WRITE`.
6. Khi read bị tạm dừng bởi backpressure, **vẫn phải giữ `OP_WRITE`** để backlog được tiêu thụ, tránh deadlock.
7. Khi read được mở lại, không được quên những điều kiện tạm dừng khác (shutdown, parser chưa sẵn sàng, global memory pressure, application-level admission).

Giới hạn theo *số buffer* không thay thế giới hạn theo *byte*: 10 buffer có thể chứa 10 KiB hoặc 10 GiB tùy cách cấp phát. Ngược lại, nếu cho rất nhiều buffer rỗng hoặc cực nhỏ, object overhead vẫn đáng kể; production nên giới hạn thêm **số entry, frame size, các task đang chờ và tổng memory toàn server**.

Với bộ nhớ dùng chung, còn cần:
- `MAX_PENDING_PER_CONNECTION` cho từng client.
- `MAX_PENDING_GLOBAL` hoặc ngân sách theo tenant cho toàn event loop.
- Chống một peer giữ toàn bộ direct-memory/heap hoặc số lượng socket.
- Thống kê dung lượng bộ đệm *ngoài queue*: parser buffers, backlog của executor, response đang tính, TLS buffers nếu có.

## 4. High watermark, low watermark và hard cap

Một chính sách minh họa:

~~~text
             outbound pendingBytes
  0 ─────── LOW ───────── HIGH ───────── MAX
           4 KiB          8 KiB         12 KiB
              ▲             ▲              ▲
              │             │              └─ Giới hạn cứng: không cấp thêm
              │             └──────────────── Tạm tắt OP_READ
              └────────────────────────────── Mở lại OP_READ khi đã đủ giảm
~~~

Nên chọn:
- **HIGH**: khi `pendingBytes >= HIGH`, ngừng lấy thêm dữ liệu từ nguồn có thể gây ra output.
- **LOW**: khi đã tạm dừng và `pendingBytes <= LOW`, mở đọc lại.
- **MAX**: nếu một phép enqueue sẽ vượt giới hạn, **không cho vượt**. Thực hiện reject, backpressure lên producer, đóng connection hoặc chính sách khác do protocol quyết định.

Điều kiện `0 <= LOW < HIGH <= MAX` và mỗi lần đọc/nhận frame phải tính trước khả năng thêm vào queue. Nếu đọc một chunk tối đa 16 KiB khi queue chỉ còn chỗ 4 KiB, việc “tắt OP_READ sau khi đọc” đã quá muộn. Có thể:
- Chỉ cấp `ByteBuffer` read với capacity ≤ `MAX - pendingBytes`.
- Đặt `HIGH` đủ thấp hơn `MAX` một khoảng tương đương chunk/frame tối đa.
- Đối với xử lý có thể **nở dữ liệu** (ví dụ decode và encode tạo response lớn hơn request), phải **dự trữ đầu ra theo kích thước xấu nhất** hoặc sử dụng queue/admission control trước khi đọc/xử lý.

### 4.1. Vì sao cần hai ngưỡng thay vì một?

Nếu một ngưỡng duy nhất bằng 8 KiB, sau mỗi write vài byte, server lại mở `OP_READ`, đọc ngay thêm chút ít, rồi tắt. Hiện tượng bật/tắt liên tục (*thrashing*) làm tăng biến động readiness và overhead.

Với **hysteresis**:
- `pending = 8 KiB` → pause `OP_READ`.
- `pending = 7 KiB` → **vẫn pause**.
- `pending = 4 KiB` → resume `OP_READ`.
- Sau resume, đọc thêm đến HIGH rồi mới pause lần tiếp.

Sơ đồ trạng thái:

~~~text
  READING ─── pending >= HIGH ───► PAUSED_READ
     ▲                                │
     └────── pending <= LOW ──────────┘
                      và còn được phép đọc theo policy
~~~

Đây là ngưỡng **hàng đợi ứng dụng** chứ không phải ngưỡng `SO_SNDBUF` của kernel. Không có một cặp LOW/HIGH tối ưu tuyệt đối; phải chọn theo số lượng kết nối, traffic, kích thước frame, memory limit và latency budget. Chọn HWM quá cao làm tăng memory/latency; quá thấp có thể giảm throughput hoặc tạo quá nhiều readiness transitions.

### 4.2. Trường hợp queue đầy

Nếu một response không thể enqueue đầy đủ, **không được** thêm “phần đầu thôi” rồi âm thầm bỏ phần cuối của một protocol TCP cần toàn vẹn. Tùy hợp đồng ứng dụng:

| Chính sách | Khi nào hợp lý | Rủi ro cần xử lý |
| --- | --- | --- |
| Dừng producer / defer xử lý | Pipeline có thể tạm dừng, chấp nhận backpressure | Cần đường đánh thức producer khi queue xuống LOW; tránh deadlock |
| Trả lỗi và đóng socket có kiểm soát | Protocol không chấp nhận thiếu dữ liệu; peer quá chậm | Xác định dữ liệu nào đã gửi, xử lý idempotency và logging |
| Reject request mới | Server có admission control và response lỗi có thể gửi an toàn | Lỗi cũng là outbound bytes, cần có hạn mức riêng |
| Drop/coalesce sự kiện mới hoặc cũ | Chỉ với **stream sự kiện cho phép mất/coalesce** | Không dùng với byte stream TCP chung hoặc response bắt buộc toàn vẹn |
| Spill ra disk | Hệ thống batch/log có hợp đồng lưu trữ và quota | I/O, disk quota, ordering, crash recovery và bảo mật |

Backpressure đúng nghĩa là **đưa tín hiệu quá tải về producer**; chỉ giới hạn queue nhưng vẫn đọc và tạo response vô hạn vào một executor khác thì chỉ chuyển điểm rò bộ nhớ sang hàng đợi khác.

## 5. Thuật toán cơ bản: `OP_READ` tạo dữ liệu, `OP_WRITE` tiêu thụ dữ liệu

### 5.1. Xử lý readable event

Một callback nên:
1. Kiểm tra session có thể nhận thêm dữ liệu hay không.
2. Tính dung lượng còn lại và giới hạn `ByteBuffer` cho read.
3. `read()` một lượng hữu hạn; nhận `-1` thì xử lý EOF, `0` thì dừng.
4. Chỉ sau khi đã có byte, tạo output buffer với ownership đúng và enqueue.
5. Bật `OP_WRITE` nếu queue vừa có dữ liệu.
6. Pause `OP_READ` khi `pendingBytes >= HIGH`.

Pseudocode:

~~~java
void onReadable(SelectionKey key, State s) throws IOException {
    int available = MAX_PENDING - s.pendingBytes;
    if (available <= 0) {
        key.interestOpsAnd(~SelectionKey.OP_READ);
        return;
    }

    ByteBuffer input = ByteBuffer.allocate(
            Math.min(READ_CHUNK, available));
    int n = s.channel.read(input);

    if (n == -1) {
        s.inputEof = true;
        key.interestOpsAnd(~SelectionKey.OP_READ);
        // Nếu queue còn dữ liệu, tiếp tục flush trước khi close.
        return;
    }
    if (n == 0) return;

    input.flip();
    s.outbound.addLast(input);   // echo: input chính là output
    s.pendingBytes += n;
    key.interestOpsOr(SelectionKey.OP_WRITE);

    if (s.pendingBytes >= HIGH) {
        key.interestOpsAnd(~SelectionKey.OP_READ);
    }
}
~~~

Đoạn trên là **pseudocode phụ thuộc `State` và constants**; ví dụ compile độc lập ở phần 8. Với echo, số byte output đúng bằng input. Với HTTP, transcoding, encryption hoặc xử lý nghiệp vụ, **dữ liệu đầu ra không nhất thiết có kích thước bằng dữ liệu đầu vào**, nên không thể dùng công thức capacity như echo nếu chưa giới hạn độ lớn response.

### 5.2. Xử lý writable event

Khi `key.isWritable()`:

~~~java
void onWritable(SelectionKey key, State s) throws IOException {
    int budget = WRITE_BUDGET_PER_EVENT;
    while (!s.outbound.isEmpty() && budget > 0) {
        ByteBuffer head = s.outbound.peekFirst();
        int n = s.channel.write(head);
        s.pendingBytes -= n;
        budget -= n;

        if (!head.hasRemaining()) {
            s.outbound.removeFirst();
        }
        if (n == 0) break;
    }

    if (s.outbound.isEmpty()) {
        key.interestOpsAnd(~SelectionKey.OP_WRITE);
    }

    if (!s.inputEof && s.pendingBytes <= LOW
            && s.readWasPaused) {
        key.interestOpsOr(SelectionKey.OP_READ);
        s.readWasPaused = false;
    }
}
~~~

Đây là **pseudocode** cho luồng ý tưởng, không phải class chạy độc lập. Có một chi tiết khi áp dụng `WRITE_BUDGET_PER_EVENT`: `SocketChannel.write(head)` có thể chuyển **nhiều hơn budget còn lại** nếu `head.remaining()` lớn, nên production phải dùng cách giới hạn `ByteBuffer.limit` tạm thời hoặc write một phần buffer đúng budget, như chương trình `SelectorBackpressureLoopback` phía dưới. Nếu bỏ yêu cầu strict fairness budget, có thể viết toàn bộ `head.remaining()` nhưng nên giới hạn số phép gọi/bytes xử lý để không chiếm toàn bộ event loop.

Không bao giờ đặt `pendingBytes -= head.capacity()` sau partial write. Việc đó làm số liệu âm hoặc kích hoạt resume sai. Nếu `write` trả `0`, giữ nguyên `position`, **giữ `OP_WRITE`** và quay lại selector.

### 5.3. Không được dừng consumer khi queue high

Một lỗi logic nguy hiểm:

~~~java
if (pendingBytes >= HIGH) {
    key.interestOps(0);  // SAI: tắt cả READ lẫn WRITE
}
~~~

Như vậy queue có thể không bao giờ giảm, vì không còn đăng ký `OP_WRITE` để drain. Đúng là **chỉ bỏ `OP_READ`** khi producer cần tạm dừng; `OP_WRITE` phải tiếp tục được theo dõi khi còn pending data.

Ngược lại, khi queue đã hết, bỏ `OP_WRITE`. Đừng bỏ `OP_READ` mãi mãi khi queue giảm xuống LOW; nếu không, connection có thể ngừng hoạt động dù peer vẫn gửi dữ liệu.

## 6. Chương trình Java 17+ thứ nhất: mô phỏng watermark và partial consumption

Chương trình sau **không mở socket**. Nó mô phỏng outbound queue bằng `Deque<ByteBuffer>`, kiểm tra admission trước enqueue và tiêu thụ một số byte nhất định mỗi lượt. Phần hay của ví dụ là stdout **hoàn toàn xác định**, giúp xác nhận tính đúng của watermark logic mà không phụ thuộc tốc độ OS/network.

Tạo **`QueueWatermarksDemo.java`**:

~~~java
import java.nio.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

public class QueueWatermarksDemo {
    private static final int HIGH = 8;
    private static final int LOW = 3;
    private static final int MAX = 12;
    private final Deque<ByteBuffer> queue = new ArrayDeque<>();
    private int pending;
    private boolean readPaused;

    public boolean enqueue(String text) {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        if (bytes.length > MAX - pending) return false;
        queue.addLast(ByteBuffer.wrap(bytes));
        pending += bytes.length;
        if (pending >= HIGH) readPaused = true;
        return true;
    }

    public void drain(int budget) {
        while (budget > 0 && !queue.isEmpty()) {
            ByteBuffer head = queue.peekFirst();
            int moved = Math.min(budget, head.remaining());
            head.position(head.position() + moved);
            pending -= moved;
            budget -= moved;
            if (!head.hasRemaining()) queue.removeFirst();
        }
        if (pending <= LOW) readPaused = false;
    }

    private void print(String label) {
        System.out.println(label + ": pending=" + pending +
                ", readPaused=" + readPaused);
    }

    public static void main(String[] args) {
        QueueWatermarksDemo q = new QueueWatermarksDemo();
        System.out.println("A accepted: " + q.enqueue("ABCDE"));
        q.print("after A");
        System.out.println("B accepted: " + q.enqueue("1234"));
        q.print("after B");
        System.out.println("C accepted: " + q.enqueue("xxxxx"));
        q.drain(3);
        q.print("after drain 3");
        q.drain(3);
        q.print("after drain 6");
        q.drain(3);
        q.print("after drain 9");
    }
}
~~~

Chạy:

~~~bash
javac --release 17 QueueWatermarksDemo.java
java QueueWatermarksDemo
~~~

Stdout chính xác:

~~~text
A accepted: true
after A: pending=5, readPaused=false
B accepted: true
after B: pending=9, readPaused=true
C accepted: false
after drain 3: pending=6, readPaused=true
after drain 6: pending=3, readPaused=false
after drain 9: pending=0, readPaused=false
~~~

Cách đọc:
- Thông điệp A có 5 byte, chưa vượt HIGH=8 nên vẫn được đọc.
- B có 4 byte, `pending=9 >= HIGH` nên ứng dụng quyết định pause read.
- C có 5 byte, nếu enqueue sẽ thành 14 > MAX=12 nên bị **từ chối nguyên vẹn**, không làm queue vượt cap.
- Sau drain 3 byte, pending còn 6, vẫn pause vì chưa xuống LOW=3.
- Sau drain thêm 3 byte, pending bằng 3, chuyển về unpaused.
- Tổng 9 byte đã được tiêu thụ; hàng đợi trống, pending=0.

`drain` này **chỉ mô phỏng tiến độ của ByteBuffer**, không gọi `SocketChannel.write`. Trong server thật, pending phải giảm theo **giá trị trả về từ `write`**, và cơ chế pause phải thay đổi `SelectionKey`. Không dùng phương thức `drain` mô phỏng để “gửi” dữ liệu TCP thật.

## 7. Event loop đầy đủ: những bất biến phải giữ khi không blocking

Trước khi xem ví dụ network chạy được, cần hiểu thiết kế trạng thái:

~~~text
ConnectionState
  channel            SocketChannel non-blocking
  outbound           Deque<ByteBuffer>
  pendingBytes       tổng các remaining() của outbound
  inputEof           đã thấy read() == -1?
  pauseCount         số lần tạm bỏ OP_READ
  resumeCount        số lần mở lại OP_READ
  peakBytes          đỉnh pendingBytes quan sát
~~~

Các thao tác bắt buộc:

- **Accept:** `ServerSocketChannel.accept` có thể trả `null` trên non-blocking listener; configure accepted channel non-blocking rồi register `OP_READ` với attachment riêng.
- **Read:** mỗi sự kiện chỉ xử lý hữu hạn bytes; if `read==-1` thì không đọc tiếp, nhưng giữ outbound đến khi flush xong.
- **Write:** giữ `ByteBuffer.position` sau partial write, không loại buffer khi vẫn còn `remaining`; đừng bỏ `OP_WRITE` khi queue chưa rỗng.
- **Pause:** khi backlog high, chỉ bỏ `OP_READ`, vẫn để `OP_WRITE`.
- **Resume:** chỉ khi backlog ≤ LOW và connection còn được đọc; không bật `OP_READ` sau EOF.
- **Close:** nếu peer đã half-close input và output đã flush xong, đóng channel. Nếu connection còn cần gửi response vào lúc client đã shutdown output, cho phép gửi nốt trước khi close.
- **Cleanup:** `SelectionKey.cancel()`, đóng channel và xử lý các selected keys đã vô hiệu trong event loop.

**TCP là byte stream, không bảo toàn message boundary.** Ví dụ tiếp theo chỉ echo byte nên không cần parser. Với giao thức frame-based như length-prefix, phải giữ buffer parser giữa nhiều lần `read` và **kiểm tra frame size trước khi cấp phát output**. Tắt `OP_READ` không được xóa dở dang một frame đã bắt đầu đọc.

## 8. Chương trình Java 17+ thứ hai: Selector echo TCP có bounded queue thật

Ví dụ này chạy **cả server và client trên loopback trong cùng một JVM**, không cần công cụ ngoài. Client gửi 4.096 byte `'x'` rồi shutdown chiều gửi, sau đó đọc echo. Server dùng `ServerSocketChannel` + `Selector` + `SocketChannel` non-blocking và per-connection outbound queue.

Để **thấy được pause/resume trong một bài test ngắn mà không lệ thuộc kernel tình cờ nghẽn**, chương trình **cố ý giới hạn lượng byte được xử lý trong mỗi writable event ở 128 byte**. Đây là **throttle mô phỏng một consumer chậm ở tầng ứng dụng**, không chứng minh OS send buffer đang đầy. Trên hệ thống thật, `write` có thể trả `0` hoặc partial write do TCP backpressure; logic giữ queue và interestOps vẫn đúng như nhau.

Tạo **`SelectorBackpressureLoopback.java`**:

~~~java
import java.io.*;
import java.net.*;
import java.nio.*;
import java.nio.channels.*;
import java.util.*;
import java.util.concurrent.*;

public class SelectorBackpressureLoopback {
    private static final int READ_CHUNK = 512;
    private static final int HIGH = 1024;
    private static final int LOW = 512;
    private static final int MAX_PENDING = 2048;
    private static final int WRITE_BUDGET = 128;

    private static final class Session {
        final SocketChannel channel;
        final Deque<ByteBuffer> outbound = new ArrayDeque<>();
        int pendingBytes;
        int peakBytes;
        int paused;
        int resumed;
        boolean eof;
        Session(SocketChannel channel) { this.channel = channel; }
    }

    private static void onRead(SelectionKey key) throws IOException {
        Session s = (Session) key.attachment();
        int free = MAX_PENDING - s.pendingBytes;
        if (free <= 0) {
            key.interestOpsAnd(~SelectionKey.OP_READ);
            return;
        }
        ByteBuffer buffer =
                ByteBuffer.allocate(Math.min(READ_CHUNK, free));
        int read = s.channel.read(buffer);
        if (read == -1) {
            s.eof = true;
            key.interestOpsAnd(~SelectionKey.OP_READ);
            if (s.outbound.isEmpty()) {
                key.cancel();
                s.channel.close();
            }
            return;
        }
        if (read == 0) return;
        buffer.flip();
        s.outbound.addLast(buffer);
        s.pendingBytes += read;
        s.peakBytes = Math.max(s.peakBytes, s.pendingBytes);
        key.interestOpsOr(SelectionKey.OP_WRITE);
        if (s.pendingBytes >= HIGH) {
            key.interestOpsAnd(~SelectionKey.OP_READ);
            s.paused++;
        }
    }

    private static void onWrite(SelectionKey key) throws IOException {
        Session s = (Session) key.attachment();
        int budget = WRITE_BUDGET;
        while (budget > 0 && !s.outbound.isEmpty()) {
            ByteBuffer head = s.outbound.peekFirst();
            int originalLimit = head.limit();
            head.limit(head.position()
                    + Math.min(head.remaining(), budget));
            int written;
            try {
                written = s.channel.write(head);
            } finally {
                head.limit(originalLimit);
            }
            s.pendingBytes -= written;
            budget -= written;
            if (!head.hasRemaining()) s.outbound.removeFirst();
            if (written == 0) break;
        }
        if (s.outbound.isEmpty()) {
            key.interestOpsAnd(~SelectionKey.OP_WRITE);
        }
        if (!s.eof && s.pendingBytes <= LOW
                && (key.interestOps() & SelectionKey.OP_READ) == 0) {
            key.interestOpsOr(SelectionKey.OP_READ);
            s.resumed++;
        }
        if (s.eof && s.outbound.isEmpty()) {
            key.cancel();
            s.channel.close();
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();
        byte[] payload = new byte[4096];
        Arrays.fill(payload, (byte) 'x');
        try (Selector selector = Selector.open();
             ServerSocketChannel listener = ServerSocketChannel.open()) {
            listener.bind(new InetSocketAddress(loopback, 0));
            listener.configureBlocking(false);
            listener.register(selector, SelectionKey.OP_ACCEPT);
            int port =
                    ((InetSocketAddress) listener.getLocalAddress())
                            .getPort();

            FutureTask<byte[]> clientJob = new FutureTask<>(() -> {
                try (Socket client = new Socket(loopback, port)) {
                    client.setSoTimeout(5000);
                    client.getOutputStream().write(payload);
                    client.shutdownOutput();
                    return client.getInputStream()
                            .readNBytes(payload.length);
                }
            });
            new Thread(clientJob, "loopback-client").start();

            Session session = null;
            long deadline = System.nanoTime()
                    + TimeUnit.SECONDS.toNanos(10);
            while (System.nanoTime() < deadline
                    && (session == null || session.channel.isOpen())) {
                selector.select(100);
                Iterator<SelectionKey> it =
                        selector.selectedKeys().iterator();
                while (it.hasNext()) {
                    SelectionKey key = it.next();
                    it.remove();
                    if (!key.isValid()) continue;
                    if (key.isAcceptable()) {
                        SocketChannel accepted = listener.accept();
                        if (accepted != null) {
                            accepted.configureBlocking(false);
                            session = new Session(accepted);
                            accepted.register(
                                    selector, SelectionKey.OP_READ, session);
                        }
                    } else {
                        if (key.isReadable()) onRead(key);
                        if (key.isValid() && key.isWritable()) onWrite(key);
                    }
                }
            }
            if (session == null || session.channel.isOpen()) {
                throw new IOException("Server did not finish");
            }
            byte[] echoed = clientJob.get(5, TimeUnit.SECONDS);
            System.out.println("echo matches: " +
                    Arrays.equals(payload, echoed));
            System.out.println("queue within cap: " +
                    (session.peakBytes <= MAX_PENDING));
            System.out.println("read paused: " + (session.paused > 0));
            System.out.println("read resumed: " + (session.resumed > 0));
        }
    }
}
~~~

Biên dịch/chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 SelectorBackpressureLoopback.java
java SelectorBackpressureLoopback
~~~

**Khi hệ điều hành cho phép tạo và trao đổi TCP qua loopback trong thời hạn thử nghiệm**, stdout đã kiểm chứng là:

~~~text
echo matches: true
queue within cap: true
read paused: true
read resumed: true
~~~

Giải thích chi tiết:

1. `MAX_PENDING=2048` và `READ_CHUNK=512`. Trước mỗi lần read, code tính `free = MAX_PENDING-pendingBytes`, nên một lần đọc không thể làm queue vượt hard cap.
2. Read đầu vào tạo `ByteBuffer` riêng, `flip()` rồi đưa vào queue. ByteBuffer được “sở hữu” bởi outbound queue cho đến khi ghi xong; không ghi đè vùng dữ liệu mà chưa tiêu thụ.
3. `onRead` bật `OP_WRITE` vì có output mới. Khi pending đạt `HIGH=1024`, nó **bỏ `OP_READ`**.
4. `onWrite` xử lý tối đa 128 byte mỗi writable event. Muốn giữ budget đúng, nó đặt **`limit` tạm thời** của `ByteBuffer` rồi khôi phục `limit` trong `finally`, không làm mất `position` sau partial write.
5. `pendingBytes` giảm bằng đúng `written`, không phải `head.capacity()`. Buffer nào có `remaining()==0` mới được dequeue.
6. Khi queue rỗng, bỏ `OP_WRITE` tránh CPU spin. Khi pending giảm đến `LOW=512` và chưa EOF, bật `OP_READ` trở lại.
7. Client gọi `shutdownOutput()` để báo đã gửi hết request nhưng vẫn đọc echo. Server nhận `read==-1` rồi **không close trước khi flush outbound**; sau flush mới đóng channel.
8. Test đối chiếu **toàn bộ 4.096 byte**: byte count không đủ để phát hiện sai thứ tự, vì vậy `Arrays.equals` bảo đảm đúng nội dung và thứ tự.
9. `peakBytes<=MAX_PENDING` xác nhận giới hạn per-connection trong lần chạy; `paused/resumed>0` chứng minh demo thực sự đi qua hai nhánh backpressure.

Đây là **demo giới hạn một kết nối**. Để dùng cho server production phải thêm: quản lý nhiều accepted channels, bắt và đóng riêng connection khi `IOException`, limit tổng toàn server, parser/frame policy, executor handoff, metrics, timeout/idle deadline, xử lý shutdown có thể xảy ra khi đang blocked ở `select`. Không được đưa nguyên một self-test loopback vào production rồi tưởng đã có server multi-client đầy đủ.

## 9. Hai vai trò khác nhau của `OP_READ` trong echo server và TCP proxy

### 9.1. Echo server một channel

Trong echo server, cùng một `SocketChannel` nhận dữ liệu và ghi echo cho **chính peer**. Khi outbound queue tới HIGH, tắt `OP_READ` trên **key của channel đó**. Như vậy ứng dụng ngừng tiêu thụ dữ liệu mới của peer, trong khi `OP_WRITE` vẫn drain backlog.

~~~text
client ──► server SocketChannel (READ) ──► echo queue ──► same channel (WRITE) ──► client
                        ▲                     │
                        └── pause/resume ◄────┘
~~~

### 9.2. Proxy hai channel

Proxy có **upstream socket A** và **downstream socket B**, thường có các queue riêng cho mỗi chiều. Nếu **B không ghi được**, hàng đợi outbound của B tăng; cái cần pause là **`OP_READ` của A**, vì chính dữ liệu đọc từ A tạo bytes cho B.

~~~text
A (source) ── OP_READ ──► queue pending-for-B ── OP_WRITE ──► B (slow receiver)
     ▲                                │
     └────── pause A when HIGH ───────┘
     └────── resume A when LOW ◄──────┘
~~~

Không chỉ tắt `OP_READ` trên B rồi cho A tiếp tục nạp vào `queue B`. Làm vậy là backpressure sai chiều, backlog vẫn lớn dần. Với proxy hai chiều, mỗi hướng có quan hệ độc lập:

| Queue đang tăng | Producer cần tạm dừng | Consumer vẫn phải hoạt động |
| --- | --- | --- |
| A → B outbound queue của B | `OP_READ` của A | `OP_WRITE` của B |
| B → A outbound queue của A | `OP_READ` của B | `OP_WRITE` của A |

Cẩn thận với quan hệ phụ thuộc và **half-close** giữa hai socket: khi A đã EOF chiều đọc, proxy vẫn phải flush dữ liệu A→B; sau đó có thể gọi `shutdownOutput` của B theo protocol để truyền EOF mà không tự đóng chiều ngược B→A còn hoạt động. Không đóng cả hai socket ngay khi một đầu đọc được `-1` nếu response chiều ngược vẫn cần thiết.

### 9.3. Ứng dụng không phải proxy

Trong HTTP/RPC server, producer có thể là task worker hoàn thành response, chứ không trực tiếp là `OP_READ`. Khi client nhận chậm, cần backpressure lên **bộ phát response** (future, stream, callback, upstream request) và không chỉ tắt read. Nếu protocol multiplexing cho phép nhiều request độc lập trên cùng connection, logic pause phải xét toàn bộ tài nguyên liên quan và quyền kiểm soát từng stream; có thể phải dùng cơ chế flow control của protocol thay vì khóa toàn socket.

## 10. Event-loop fairness: đừng để một client nuốt hết thời gian

Hạn chế memory là một việc; tránh starvation còn đòi **giới hạn công việc trên mỗi selected key**:

- `MAX_READ_BYTES_PER_EVENT`: mỗi lượt đọc tối đa N byte hoặc M chunk. Nếu vẫn còn dữ liệu, quay lại selector để phục vụ connection khác.
- `MAX_WRITE_BYTES_PER_EVENT`: tối đa K byte ghi mỗi lượt. Demo dùng 128 byte để test, nhưng production điều chỉnh theo throughput/latency thật.
- `MAX_FRAMES_PER_EVENT` hoặc time budget cho parser, tránh xử lý hàng triệu frame nhỏ của một connection.
- Không thực hiện database call, file I/O blocking hay thao tác CPU rất nặng ngay trên selector thread.
- Tránh busy-spin `while (channel.write(buffer)==0)` hoặc `while (channel.read(buf)==0)`.
- Theo dõi selector event loop lag, số key ready, thời gian xử lý mỗi key và các client bị pause quá lâu.

Nếu không giới hạn write per event, một connection luôn có backlog có thể độc chiếm event loop, làm các kết nối khác bị chậm dù queue của chúng nhỏ. Nếu budget quá thấp, throughput giảm đáng kể và số lần `select` tăng. Đây là trade-off thực nghiệm, nên đo workload thật.

## 11. Giao tiếp với worker thread: ownership và `selector.wakeup()`

Ví dụ loopback chỉ sửa queue và interestOps trên **một selector thread**, nên không có race giữa producer/consumer. Trong hệ thống thật, response có thể được tạo ở worker thread. Đừng để nhiều thread cùng sửa `ArrayDeque<ByteBuffer>`, `pendingBytes` và `SelectionKey.interestOps(...)` không theo protocol đồng bộ.

Mẫu quản lý tốt:

~~~text
worker thread
    │
    ├── tạo response hoặc thông báo "response ready"
    ├── gửi task vào concurrent controlQueue của event-loop
    └── selector.wakeup()
                        │
                        ▼
                selector event-loop thread
                        │
                        ├── lấy control task
                        ├── kiểm tra admission và memory cap
                        ├── enqueue ByteBuffer có ownership riêng
                        ├── bật OP_WRITE nếu cần
                        └── điều chỉnh OP_READ theo watermark
~~~

`selector.wakeup()` đánh thức một thao tác `select` đang chờ (hoặc khiến thao tác `select` kế tiếp trả sớm theo contract). Nó **không tự thêm một ByteBuffer vào outbound queue**, cũng không tự bật `OP_WRITE`. Một mẫu cụ thể trong worker:

~~~java
controlQueue.add(() -> enqueueResponseOnEventLoop(key, response));
selector.wakeup();
~~~

Đoạn này là **pseudocode**, `controlQueue` là thread-safe queue và `enqueueResponseOnEventLoop` chỉ thực thi trên event-loop thread. Phải cấp quyền sở hữu đối với `response` trước khi worker chuyển sang xử lý việc khác; ví dụ copy byte[] hoặc buffer immutable. Event loop phải chạy các control tasks khi được đánh thức, không chỉ khi có selected keys.

Sửa `interestOps` khi một thread khác đang `select` sẽ được phản ánh ở lần selection tiếp theo theo Javadoc; do đó tránh “đã bật OP_WRITE mà không có wakeup” khiến event loop đang ngủ đến timeout lâu. Nếu có nhiều luồng cùng thay đổi bit, dùng `interestOpsOr/And` để cập nhật bit nguyên tử **nhưng vẫn cần đồng bộ trạng thái queue và vòng đời key**.

## 12. Chọn chính sách khi peer chậm không hồi phục

Backpressure giúp server giữ tài nguyên có giới hạn, nhưng **không thể bảo đảm một client đọc cực chậm sẽ hoàn thành request đúng hạn**. Production cần thêm deadline và chính sách xử lý:

1. **Bounded write queue**: từ chối enqueue nếu vượt per-client/global hard cap.
2. **Write-progress deadline**: nếu không ghi thêm byte trong một thời gian quá dài khi queue vẫn có dữ liệu, đóng kết nối theo hợp đồng.
3. **Maximum paused duration**: nếu `OP_READ` bị pause quá lâu, ghi cảnh báo hoặc cắt kết nối sau grace period.
4. **Response timeout/stream deadline**: tránh một request giữ tài nguyên vô hạn.
5. **Per-client fairness/quotas**: bảo vệ người dùng khác khỏi một peer chậm.
6. **Clean disconnect**: cancel key, close channel, giải phóng queue/buffers và hủy các task producer đang chờ. Không enqueue vào session đã đóng.

Không có giá trị timeout duy nhất phù hợp cho mọi dịch vụ. Chọn dựa vào SLA, kích thước response, môi trường WAN/LAN, throughput tối thiểu chấp nhận, và khả năng tiếp tục/resume của protocol. Đóng socket khi đã gửi một phần response có thể khiến client nhận **partial payload**; protocol cần framing/checksum hoặc error semantics để nhận biết.

### 12.1. Không drop tùy ý các byte TCP

TCP bảo đảm luồng byte theo thứ tự khi kết nối còn hoạt động, nhưng ứng dụng **không** được lặng lẽ bỏ byte khỏi outbound queue để giữ memory. Nếu server tự cắt payload giữa chừng, remote application thấy protocol bị hỏng hoặc dữ liệu không đủ. Drop chỉ phù hợp khi application protocol **thiết kế trước** ý nghĩa “message này có thể bị bỏ”, ví dụ các snapshot cập nhật trạng thái mới nhất có thể thay thế snapshot cũ.

Nếu không thể enqueue một response nguyên vẹn và không thể pause producer, có thể cần fail request/connection. Chọn quy tắc rõ ràng thay vì để `OutOfMemoryError` quyết định.

### 12.2. Thận trọng với TLS và HTTP

Với `SSLEngine`, queue có thể là **encrypted application records** và các buffer plain/network riêng biệt. `wrap/unwrap` có thể tạo output nhiều hơn input và yêu cầu tiếp tục handshake kể cả khi app payload bị pause. Không áp dụng trực tiếp công thức “đọc N byte tạo N byte outbound” của echo sang TLS. Cần tính toàn bộ memory và trạng thái handshake; tránh deadlock nếu khóa read quá sớm mà `SSLEngine` còn cần nhận TLS record.

HTTP/2 hoặc các protocol multiplexed có flow control ở cấp stream/connection. Có thể cần phối hợp các cửa sổ flow control này, không chỉ đặt `OP_READ`/`OP_WRITE` trên TCP channel. Mục tiêu cuối cùng vẫn là liên kết tốc độ **producer → queue → consumer** với ranh giới tài nguyên.

## 13. Quan sát và kiểm thử backpressure

### 13.1. Các metric nên đo

| Metric | Ý nghĩa |
| --- | --- |
| `outbound_pending_bytes` per-connection | Số byte còn trong queue để write |
| `outbound_pending_bytes_global` | Tổng byte queue trên server/tenant |
| `queue_peak_bytes` | Đỉnh backlog, dùng so cap và memory budget |
| `read_paused_connections` | Số kết nối bị bỏ `OP_READ` bởi backpressure |
| `read_pause_duration_ms` | Thời gian read bị pause, giúp phát hiện peer chậm |
| `nonblocking_write_zero_count` | Số lần `write` trả `0` khi queue còn dữ liệu |
| `write_progress_bytes/s` | Tốc độ OS/channel nhận dữ liệu từ app |
| `selector_loop_delay_ms` | Độ trễ vòng lặp, giúp phát hiện CPU-bound handler |
| `queue_overflow_rejections` | Số response/request bị từ chối do hard cap |
| `connection_closes_slow_peer` | Số kết nối bị cắt do peer quá chậm |

Đừng chỉ đo queue length dưới dạng số phần tử. Đừng coi `write_progress_bytes/s` là tốc độ remote đã xử lý nghiệp vụ. Ghi dimension hữu ích (protocol, endpoint, trạng thái) mà không tạo metric cardinality vô hạn bằng IP/port của từng peer.

### 13.2. Test case bắt buộc

| Tình huống | Kỳ vọng |
| --- | --- |
| Peer đọc nhanh, queue rỗng | Không đăng ký `OP_WRITE` khi không có dữ liệu |
| `write` chỉ nhận một phần | Buffer head giữ phần còn lại, thứ tự data nguyên vẹn |
| `write` trả `0` | Không busy-spin; giữ `OP_WRITE` và dữ liệu |
| Pending chạm HIGH | Chỉ bỏ `OP_READ` của producer tương ứng |
| Pending giảm nhưng vẫn > LOW | Chưa bật read lại |
| Pending <= LOW | Bật lại `OP_READ` nếu session cho phép và chưa EOF |
| Pending sẽ vượt MAX | Reject/defer **trước** cấp phát/enqueue; không vượt cap |
| Peer gửi EOF khi còn outbound | Flush đúng phần đã tạo rồi mới close/half-close theo protocol |
| Channel/key bị close/cancel | Không tiếp tục enqueue/interestOps; dọn queue và task |
| Một client rất chậm, nhiều client nhanh | Slow client không làm memory vô hạn hoặc starvation |
| Có nhiều producer threads | Dữ liệu không bị ghi đè; queue ownership và wakeup đúng |
| Parser nhận frame quá lớn | Không cấp phát frame vô hạn dù `OP_READ` throttling đã được bật |

### 13.3. Tạo slow receiver test mà không phụ thuộc may rủi

Một thử nghiệm mạng thật có thể:
- Cho client **đọc chậm có chủ đích** (sleep giữa các read) với một payload đủ lớn.
- Đặt `SO_RCVBUF` phía receiver nhỏ để hỗ trợ tái hiện, nhưng đây chỉ là hint và kết quả tùy OS.
- Phát nhiều response có kích thước lớn và theo dõi `pendingBytes`, pause time và write-zero count.
- Thiết lập deadline để test không treo vô hạn; dùng loopback cho kiểm thử chức năng, môi trường mạng được kiểm soát cho benchmark.
- Kiểm tra bất biến tổng số byte và hash nội dung, không chỉ “server vẫn sống”.
- Chạy trên các JDK/OS mà sản phẩm hỗ trợ; kernel buffering và scheduler khiến thời điểm xuất hiện partial write/`0` không cố định.

Ví dụ `SelectorBackpressureLoopback` cố ý dùng write budget 128 byte cho **mỗi event**, nên có thể kiểm tra các nhánh pause/resume một cách lặp lại **mà không cần chờ OS tự nghẽn**. Đây là test logic throttling; integration test thực tế vẫn cần peer đọc chậm và socket buffer thật.

## 14. Những lỗi thường gặp

**Lỗi 1: bật `OP_WRITE` từ đầu cho mọi kết nối.** Khi socket thường xuyên writable, event loop có thể chạy CPU liên tục. Chỉ bật khi có data chờ; tắt lúc queue rỗng.

**Lỗi 2: gọi `while(buffer.hasRemaining()) channel.write(buffer)` không kiểm tra `0`.** Nếu OS không nhận thêm byte, vòng lặp trở thành busy-spin. Dừng khi `write==0`, đợi readiness tương ứng.

**Lỗi 3: xóa buffer khỏi queue sau một lần `write`.** Non-blocking write có thể partial; giữ buffer đến khi `remaining()==0`.

**Lỗi 4: tắt tất cả interest bits khi queue đầy.** Tắt cả `OP_WRITE` làm queue không được drain và connection có thể deadlock.

**Lỗi 5: chỉ giới hạn số message.** Một message có thể cực lớn. Phải giới hạn byte queue, frame length và số task đang chờ.

**Lỗi 6: high watermark đồng thời là hard cap mà không tính kích thước chunk.** Nếu pending sát cap, đọc một chunk lớn mới check thì đã vượt cap. Tính free bytes **trước read/enqueue**.

**Lỗi 7: mở `OP_READ` lại ngay khi pending vừa giảm một byte.** Gây bật/tắt liên tục; dùng LOW thấp hơn HIGH.

**Lỗi 8: tắt read của sai socket trong TCP proxy.** Khi B chậm, phải pause nguồn A đang tạo outbound của B, không chỉ pause B.

**Lỗi 9: nhầm `SO_SNDBUF` với memory budget ứng dụng.** OS buffer là một lớp riêng; `SocketChannel.write` có thể chấp nhận vào kernel nhưng remote chưa xử lý.

**Lỗi 10: một worker thread tự thay queue và interestOps khi selector thread đang xử lý.** Có thể race, mất wakeup hoặc double enqueue. Dùng một owner event loop và thread-safe command queue.

**Lỗi 11: thấy `read==-1` là close ngay dù queue còn response.** Mất phần dữ liệu đã tạo; cần drain trước, nếu protocol yêu cầu.

**Lỗi 12: không loại key đã xử lý khỏi `selectedKeys()` hoặc không xét `isValid()`.** Có thể xử lý lặp/sai trạng thái sau close, làm event loop lỗi.

## 15. Bài tập tự kiểm tra

**Câu 1.** Một `SocketChannel` non-blocking có 1.000 byte trong `ByteBuffer`; `write` trả 300. Có thể dequeue ngay không?  
**Đáp án:** Không. Còn 700 byte `remaining()`; giữ buffer, tiếp tục khi writable.

**Câu 2.** Tại sao `OP_WRITE` được bật liên tục khi queue rỗng làm CPU cao?  
**Đáp án:** Socket có thể luôn báo writable, khiến `select` trả về liên tục dù không có data để gửi.

**Câu 3.** Hàng đợi hiện có 900 byte; HIGH=1.024, MAX=1.280. Có được đọc thêm chunk 512 byte rồi mới kiểm tra?  
**Đáp án:** Không. Chunk vượt phần trống 380 byte của MAX. Cần giới hạn read ≤380 byte hoặc defer.

**Câu 4.** HIGH=8 KiB, LOW=4 KiB, pending từ 10 xuống 7 KiB. Có resume `OP_READ` chưa?  
**Đáp án:** Chưa, vì đang paused và pending vẫn > LOW.

**Câu 5.** B nhận chậm trong một proxy A→B. `OP_READ` nào cần pause?  
**Đáp án:** `OP_READ` trên A, nguồn của dữ liệu đi vào queue chờ ghi cho B; vẫn giữ `OP_WRITE` của B.

**Câu 6.** `channel.write(buffer)` trả `0`. Có phải remote đã đóng hoặc gửi lỗi?  
**Đáp án:** Không nhất thiết. OS có thể chưa nhận thêm byte; giữ data và chờ writable. Trạng thái đóng/lỗi phải được kiểm tra qua API và ngoại lệ thích hợp.

**Câu 7.** `pendingBytes==0` có chứng minh remote nhận hết response không?  
**Đáp án:** Không. Chỉ chứng minh application queue rỗng vì các byte đã được chuyển tới channel/OS.

**Câu 8.** Một client gửi EOF trong khi server còn queue. Nên close ngay không?  
**Đáp án:** Không mặc định. Với protocol cần trả hết response, dừng read, giữ write, flush outbound và sau đó mới đóng/half-close theo thiết kế.

**Câu 9.** Giới hạn queue 1 MiB trên mỗi client có đủ bảo vệ server 100.000 client không?  
**Đáp án:** Chưa. Tổng tiềm năng là ~100 GiB chưa kể object overhead/input/task buffers; cần global budget và connection admission.

**Câu 10.** Worker task vừa tạo response nhưng selector đang `select` blocking. Có phải gọi `selector.wakeup()` là đủ để enqueue?  
**Đáp án:** Không. Cần chuyển response/command qua thread-safe queue, wakeup selector, rồi event-loop owner thực sự enqueue và bật `OP_WRITE`.

## 16. Checklist production

1. Xác định **producer** của mỗi outbound queue và consumer tương ứng; trong proxy đừng pause nhầm đầu.
2. Đặt per-connection **MAX_PENDING**, global budget và giới hạn input/frame/task.
3. Theo dõi `pendingBytes = Σ outbound.remaining()`; cập nhật bằng bytes thực `write`.
4. Dùng `LOW < HIGH <= MAX`; pause nguồn tại HIGH và chỉ resume tại LOW.
5. Đảm bảo read-chunk/frame size không làm queue vượt MAX **trước khi enqueue**.
6. `OP_WRITE` chỉ bật khi queue có dữ liệu; bỏ ngay khi queue rỗng.
7. Handle `write==0`, partial write, `read==0`, `read==-1` và `IOException`; không busy-spin.
8. Giữ đúng position/limit của ByteBuffer, ownership khi chuyển qua worker thread và thứ tự byte stream.
9. Có per-event byte/time budget để tránh một connection độc chiếm event loop.
10. Thiết kế overload policy, slow-peer timeout, EOF/half-close và cleanup rõ ràng.
11. Đo peak queue, pause duration, blocked writes, memory global và loop lag.
12. Kiểm thử có peer đọc chậm, nhiều client, lỗi/hủy key và các JVM/OS mục tiêu.

## Tài liệu chính thức

- [Java SE 17 — `SocketChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html): `read`/`write` trong non-blocking mode, partial/zero-byte I/O, EOF, kết nối và half-close.
- [Java SE 17 — `SelectionKey`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectionKey.html): `OP_READ`, `OP_WRITE`, interest/ready sets, `interestOpsAnd` và `interestOpsOr`, key validity.
- [Java SE 17 — `Selector`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html): `select`, `selectedKeys`, cancellation, `wakeup` và quy tắc concurrency.
- [Java SE 17 — `ServerSocketChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ServerSocketChannel.html): non-blocking `accept` và registration.
- [Java SE 17 — `ByteBuffer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): `position`, `limit`, `remaining`, `flip` và ownership data.
- [Java SE 17 — `StandardSocketOptions`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/StandardSocketOptions.html): `SO_SNDBUF` và giới hạn socket buffer ở OS.

**Nguyên tắc xuyên suốt:** **giới hạn queue bằng số byte, không vứt dữ liệu còn pending; chỉ đăng ký `OP_WRITE` khi cần; pause đúng nguồn bằng `OP_READ` tại HIGH và resume tại LOW; với peer quá chậm, phải có overload policy và deadline rõ ràng.**
