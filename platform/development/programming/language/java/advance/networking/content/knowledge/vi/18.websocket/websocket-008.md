# WebSocket: chuỗi gửi đúng thứ tự và giới hạn thao tác đang chờ trong Java 17+

Một kết nối WebSocket cho phép ứng dụng Java gửi/nhận nhiều thông điệp mà không phải mở lại HTTP request cho mỗi lần giao tiếp. Tuy nhiên, **một lời gọi `sendText(...)` không phải là lệnh ghi đồng bộ đã hoàn tất**, và **nhiều producer threads đồng thời gọi `sendText(...)` không tự tạo một hàng đợi an toàn, có giới hạn**. Nếu client gửi nhanh hơn khả năng chuyển dữ liệu qua mạng, backlog có thể tích tụ trong ứng dụng; nếu gọi gửi text/binary khi thao tác text/binary trước chưa xong, API `java.net.http.WebSocket` của JDK 17 có thể trả `CompletableFuture` hoàn thành lỗi `IllegalStateException`.

Bài này tập trung vào hai yêu cầu của một outbound WebSocket client đáng tin cậy:

1. **Đúng thứ tự:** thống nhất **thứ tự nghiệp vụ**, chỉ bắt đầu thao tác gửi text/binary tiếp theo sau khi thao tác trước hoàn thành thành công; tránh gửi đồng thời vô tình, tráo thứ tự, trộn các fragment của message.
2. **Có giới hạn:** kiểm soát số message, số byte **đang chờ và đang gửi**, thời gian chờ cùng chính sách xử lý đầy queue. Không tạo chuỗi `CompletableFuture` vô hạn hay gom nhiều `ByteBuffer` không giới hạn.

Hai ví dụ Java 17+ độc lập phía dưới kiểm chứng các nguyên tắc này. Ví dụ thứ nhất **không dùng mạng**, cho phép điều khiển thời điểm send-completion bằng mock và quan sát chính xác queue cap. Ví dụ thứ hai tạo một **WebSocket server kiểm thử tối giản trên loopback**, dùng Java `HttpClient` thực hiện HTTP Upgrade, chuỗi ba `sendText` rồi kiểm tra các message server nhận theo đúng thứ tự.

## 1. Ba lớp phải phân biệt: logic message, send operation, transport

~~~text
Producer A / B / C (nhiều threads)
             │
             ▼
      ỨNG DỤNG ấn định thứ tự
      - message #1, #2, #3
      - admission / bounded queue
             │
             ▼
       serial send dispatcher
       - tối đa một text/binary send pending
       - gọi sendText/sendBinary
       - đợi CompletableFuture hoàn tất
             │
             ▼
     java.net.http.WebSocket (client)
       - WebSocket framing / masking
       - state và pending-send policy
             │
             ▼
       TLS/TCP/OS/network
             │
             ▼
        Remote peer / application
~~~

Một **WebSocket message** là đơn vị logic với loại **text** hoặc **binary**. Một message có thể được truyền qua **một hoặc nhiều frames**. API Java có tham số `last` để phân biệt fragment cuối với fragment chưa kết thúc. Một **send operation** là một lời gọi `sendText`, `sendBinary`, `sendPing`, `sendPong` hoặc `sendClose` và `CompletableFuture` trả về.

Theo [JDK 17 WebSocket Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.html), một operation đã được khởi tạo nhưng `CompletableFuture` của nó chưa hoàn thành được xem là **pending**. Khi future hoàn thành bình thường, **operation được xem là gửi thành công**; khi hoàn thành ngoại lệ, operation thất bại.

**Không suy ra remote application đã xử lý message chỉ từ việc send future thành công.** TCP/WebSocket send-completion không thay thế **acknowledgment ở tầng nghiệp vụ**. Nếu cần biết server đã cập nhật đơn hàng/ghi event/commit transaction, phải định nghĩa ACK message có correlation ID hoặc protocol response riêng và timeout/idempotency phù hợp.

| Sự kiện | Điều được chứng minh | Điều chưa được chứng minh |
| --- | --- | --- |
| `sendText("A", true)` trả future | Đã khởi tạo hoặc từ chối operation theo contract | Không nói future đã thành công |
| Future `sendText` hoàn thành bình thường | Operation gửi theo JDK hoàn tất thành công | Không chứng minh peer đã xử lý nghiệp vụ |
| Server WebSocket listener nhận message A | Message đã đến WebSocket server endpoint đó | Không chứng minh transaction phía server đã commit |
| Server gửi application ACK cho message ID A | Phụ thuộc semantics ACK được thiết kế | Không mặc nhiên bảo đảm exactly-once sau retry |
| Client đóng WebSocket output bằng Close frame | Đã khởi tạo/hoàn tất close-send theo future | Không bảo đảm ứng dụng phía peer đã xử lý mọi side effect |

## 2. Những ràng buộc send cụ thể trong Java 17

### 2.1. `sendText` và `sendBinary` không nên overlap

API:

~~~java
CompletableFuture<WebSocket> a =
        webSocket.sendText("first", true);

CompletableFuture<WebSocket> b =
        webSocket.sendText("second", true);
~~~

Đây là **mã minh họa nguy cơ**, không phải pattern nên dùng. Nếu `a` còn pending khi gọi `sendText` thứ hai, theo Javadoc `b` **có thể hoàn thành ngoại lệ `IllegalStateException`** do có thao tác text hoặc binary send đang pending. Exception nằm trong **returned future**, không nhất thiết bị ném đồng bộ ngay tại dòng `sendText`.

Với `sendBinary(ByteBuffer, boolean)` cũng tương tự: nếu có text/binary send operation pending, future có thể hoàn thành `IllegalStateException`. Một lỗi I/O hoặc output side đã đóng thường biểu hiện `IOException` trong future.

**Quy tắc ứng dụng:** không dựa vào tốc độ loopback khiến future đầu tiên tình cờ hoàn thành ngay. Nếu muốn thứ tự A→B, chỉ **khởi tạo send B sau khi future send A đã complete normally**.

### 2.2. Chaining bằng `thenCompose`

~~~java
CompletableFuture<WebSocket> chain =
        CompletableFuture.completedFuture(webSocket);

chain = chain
        .thenCompose(ws -> ws.sendText("first", true))
        .thenCompose(ws -> ws.sendText("second", true))
        .thenCompose(ws -> ws.sendText("third", true));
~~~

Đây là **đoạn Java minh họa trong phương thức**; cần `webSocket` kiểu `WebSocket`, import `java.net.http.WebSocket` và `java.util.concurrent.CompletableFuture`.

- `thenCompose` không bắt đầu send thứ hai cho tới khi stage thứ nhất thành công.
- Chuỗi giữ thứ tự **các operation được enqueue trong chính chuỗi đó**.
- Nếu operation đầu thất bại, các bước `thenCompose` tiếp theo **không được gọi**; stage cuối cũng hoàn thành ngoại lệ.
- `thenApply` phù hợp để biến đổi giá trị sau send; `thenCompose` dùng để **nối một future bất đồng bộ mới**, tránh `CompletableFuture<CompletableFuture<...>>`.
- `thenRun` có thể dùng cho bước đồng bộ, nhưng không thay `thenCompose` khi callback trả về send future.
- Không chặn event loop/callback bằng `join()` hoặc `get()` cho từng message; chỉ chờ trên thread test hoặc consumer được phép block.

Một chuỗi future theo thứ tự **không tự bounded**. Nếu có một triệu call `thenCompose` được thêm trong lúc send đầu chưa xong, chương trình có thể giữ một triệu message/payload và future nodes ở heap. Phải có **admission control** trước khi thêm stage.

### 2.3. Ping/Pong có chính sách pending riêng

Theo JDK 17:

- `sendText` / `sendBinary` xem **pending text hoặc binary send** là xung đột.
- `sendPing` / `sendPong` xem **pending ping hoặc pong send** là xung đột với nhóm control tương ứng.
- Ping/Pong payload tối đa **125 bytes**; `sendPing(ByteBuffer)` và `sendPong(ByteBuffer)` có thể hoàn thành ngoại lệ `IllegalArgumentException` nếu vượt giới hạn.
- WebSocket implementation tự gửi Pong đáp lại Ping theo contract; ứng dụng thường **không cần tự gửi Pong thủ công**.
- `sendClose` có semantics riêng, đồng thời ảnh hưởng trạng thái output; **không** đặt Close vào giữa data messages vẫn cần gửi.

Vì text/binary và ping/pong có các nhóm pending điều kiện khác nhau, đừng suy ra API tự tạo một **global FIFO order cho mọi loại send**. Nếu ứng dụng yêu cầu thứ tự chặt cho một nhóm data/control commands, đặt chúng trong **dispatcher có policy rõ ràng**, nhưng không hứa wire-level interleaving control frame luôn giống thứ tự application queue.

## 3. Thứ tự đến từ đâu khi có nhiều producer threads?

Ví dụ chat, telemetry hoặc game state:

~~~text
Producer A: enqueue seq=101 (JOIN)
Producer B: enqueue seq=102 (MOVE)
Producer C: enqueue seq=103 (LEAVE)
               │
               ▼
        One outbound owner
        queue [101, 102, 103]
               │
               ▼
         serial send chain
~~~

Nếu cả ba threads độc lập gọi `webSocket.sendText` trực tiếp, mỗi thread có thể thắng race khác nhau. **Thread scheduling không bảo đảm thứ tự nghiệp vụ**, kể cả nếu người dùng bấm “JOIN” trước “MOVE” ở UI. Nếu order thật sự quan trọng, application phải:

1. **Ấn định thứ tự tại một điểm tuyến tính** (single actor/event loop, hoặc lock khi tiếp nhận) rồi gán sequence ID nếu cần.
2. Chỉ có **một owner** quyết định enqueue và gọi send; producer threads không gửi trực tiếp.
3. Dùng FIFO queue hoặc một `tail` future chain để giữ order từ lúc **admission**.
4. Dừng/giới hạn producer khi queue đầy thay vì tạo future nodes vô hạn.
5. Có điều khoản xử lý lỗi, timeout và shutdown để không để các message còn chờ mãi.

**Thứ tự tiếp nhận dưới `synchronized` = thứ tự thread nào lấy lock trước**, không phải nhất thiết thứ tự thời gian sự kiện xảy ra trong thế giới thực. Với nhiều producers cần global business order, gán sequence ở upstream/transaction log, hoặc dùng single-owner event stream/actor với source-order contract rõ ràng. Không dùng `System.currentTimeMillis()` làm total order chắc chắn vì các event có thể cùng timestamp và đồng hồ có thể dịch chuyển.

### 3.1. Bounded queue phải giới hạn cả active và waiting

Một thiết kế thông dụng:

~~~text
MAX_MESSAGES = 3
MAX_BYTES    = 6

T0: request A (1 byte) -> accepted -> send A in flight
T1: request BB (2 bytes) -> accepted, waits
T2: request CCC (3 bytes) -> accepted, waits
    reserved = 1 + 2 + 3 = 6 bytes
    pendingMessages = 3

T3: request D (1 byte) -> REJECTED:
    pendingMessages đã chạm MAX_MESSAGES=3

T4: send A hoàn thành -> release A, bắt đầu BB
T5: send BB hoàn thành -> release BB, bắt đầu CCC
T6: send CCC hoàn thành -> release CCC
    reserved=0, pendingMessages=0
~~~

Cần đếm **message đang gửi (in-flight)** trong quota, không chỉ queue đang đợi. Nếu có 1 active + 100 waiting mà cap kiểm tra 100 waiting thì trạng thái tài nguyên thật lớn hơn cap dự kiến.

Nếu gửi text, byte cap nên dựa trên kích thước **UTF-8 encoded payload**, không phải `String.length()`: `"é"` có một UTF-16 code unit nhưng hai byte UTF-8; một emoji thường có hai UTF-16 code units và bốn byte UTF-8. Phải tính cả overhead của `String`/future/queue nodes, binary buffers, WebSocket framing và client implementation khi lập memory budget thực tế. **MAX_BYTES tính payload là một ranh giới hữu ích, không phải cam kết tổng heap/direct memory chính xác bằng MAX_BYTES.**

### 3.2. High-water/low-water + hard cap

Có thể kết hợp:

- `LOW_WATER`: khi pending bytes giảm tới hoặc dưới mức này, resume nguồn dữ liệu đã pause.
- `HIGH_WATER`: khi pending bytes tăng tới mức này, pause producer hoặc ngừng poll upstream.
- `MAX_PENDING_BYTES`: hard cap không được vượt, bất kể high watermark.
- `MAX_PENDING_MESSAGES`: bảo vệ object overhead khi có rất nhiều message nhỏ.

~~~text
0 ─── LOW (256 KiB) ─── HIGH (768 KiB) ─── MAX (1 MiB)
        ▲                    ▲                ▲
   resume producer       pause producer   reject/defer
       (nếu đủ chỗ)                        trước enqueue
~~~

**Không** đợi enqueue xong mới kiểm tra MAX. Với message 2 MiB và cap 1 MiB, phải reject một message đó ngay, không phân mảnh thành hai triệu entries hoặc cắt mất phần cuối trừ khi protocol nghiệp vụ cho phép.

## 4. Chính sách khi queue đầy: fail-fast, defer, coalesce hay disconnect?

Không có chính sách duy nhất cho mọi loại WebSocket traffic.

| Chính sách | Phù hợp | Cảnh báo |
| --- | --- | --- |
| **Reject new message** | RPC/control commands bắt buộc đúng; caller có retry policy | Caller phải nhận lỗi rõ, không âm thầm bỏ |
| **Pause producer** | Stream từ file/DB/upstream có hỗ trợ backpressure | Tránh giữ thêm bytes ở queue khác; phải resume ở LOW |
| **Drop/coalesce snapshots** | UI presence, tốc độ cập nhật trạng thái được phép mất | Phải định nghĩa message replaceable, **không áp dụng cho mọi nghiệp vụ** |
| **Disconnect slow peer** | Quota bị vi phạm kéo dài, client không tiêu thụ | Close/abort có thể làm mất các message chưa được ACK |
| **Spool to disk** | Hàng đợi có durability semantics và quota nghiêm | Disk I/O, checksum, ordering, crash recovery, PII |
| **Fail entire session** | Một send failure làm trạng thái phiên không còn đáng tin | Fail pending futures, cleanup, reconnect và reconcile |

Nếu message đại diện thanh toán, đặt hàng, thay đổi quyền hoặc command có side effect, **không drop hoặc reorder tùy tiện**. Nếu chỉ là snapshot nhiệt độ mới nhất, có thể thay thế snapshot cũ trước khi gửi nếu protocol cho phép. Mọi lựa chọn cần thể hiện trong **delivery semantics**: at-most-once, at-least-once, dedupe, ACK, replay hoặc idempotency.

**Không dùng retry không giới hạn** cho `sendText` khi future thất bại. Peer có thể đã nhận một phần/đầy đủ trước khi disconnect; lặp command không có idempotency token có thể tạo side effect trùng.

## 5. Ví dụ Java 17+ số 1: hàng đợi gửi có giới hạn và chuỗi future đúng thứ tự

Ví dụ này chủ động **không mở network**. Một `ManualTransport` đóng vai transport có `CompletableFuture` hoàn thành khi bài test chủ động gọi `finishOne()`. Nó giúp thấy rõ **khi operation A còn pending thì B/C chưa bắt đầu**, dù cả ba đã được chấp nhận trong queue. Cả số message và tổng byte đang reserved đều có giới hạn.

Tạo file **`WebSocketBoundedQueueDemo.java`**:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;

public final class WebSocketBoundedQueueDemo {
    interface AsyncTextTransport {
        CompletableFuture<Void> send(String message);
    }

    static final class BoundedOrderedSender {
        private final AsyncTextTransport transport;
        private final int maxMessages;
        private final int maxBytes;
        private int pendingMessages;
        private int pendingBytes;
        private boolean accepting = true;
        private CompletableFuture<Void> tail =
                CompletableFuture.completedFuture(null);

        BoundedOrderedSender(AsyncTextTransport transport,
                             int maxMessages, int maxBytes) {
            if (maxMessages < 1 || maxBytes < 1) {
                throw new IllegalArgumentException(
                        "positive limits required");
            }
            this.transport = Objects.requireNonNull(transport);
            this.maxMessages = maxMessages;
            this.maxBytes = maxBytes;
        }

        synchronized CompletableFuture<Void> offer(String message) {
            Objects.requireNonNull(message);
            int bytes =
                    message.getBytes(StandardCharsets.UTF_8).length;

            if (!accepting) {
                return CompletableFuture.failedFuture(
                        new IllegalStateException("sender stopped"));
            }
            if (pendingMessages >= maxMessages
                    || bytes > maxBytes - pendingBytes) {
                return CompletableFuture.failedFuture(
                        new RejectedExecutionException("send queue full"));
            }

            pendingMessages++;
            pendingBytes += bytes;

            CompletableFuture<Void> internal =
                    tail.thenCompose(ignored ->
                            transport.send(message));
            tail = internal;

            CompletableFuture<Void> forCaller =
                    new CompletableFuture<>();
            internal.whenComplete((ok, failure) -> {
                synchronized (BoundedOrderedSender.this) {
                    pendingMessages--;
                    pendingBytes -= bytes;
                    if (failure != null) accepting = false;
                }
                if (failure == null) {
                    forCaller.complete(null);
                } else {
                    forCaller.completeExceptionally(failure);
                }
            });
            return forCaller;
        }

        synchronized int pendingMessages() {
            return pendingMessages;
        }

        synchronized int pendingBytes() {
            return pendingBytes;
        }
    }

    static final class ManualTransport
            implements AsyncTextTransport {
        final List<String> started = new ArrayList<>();
        final Deque<CompletableFuture<Void>> acknowledgments =
                new ArrayDeque<>();

        @Override
        public CompletableFuture<Void> send(String message) {
            started.add(message);
            CompletableFuture<Void> ack = new CompletableFuture<>();
            acknowledgments.addLast(ack);
            return ack;
        }

        void finishOne() {
            acknowledgments.removeFirst().complete(null);
        }
    }

    public static void main(String[] args) {
        ManualTransport transport = new ManualTransport();
        BoundedOrderedSender queue =
                new BoundedOrderedSender(transport, 3, 6);

        CompletableFuture<Void> first = queue.offer("A");
        CompletableFuture<Void> second = queue.offer("BB");
        CompletableFuture<Void> third = queue.offer("CCC");
        CompletableFuture<Void> rejected = queue.offer("D");

        System.out.println("started: " + transport.started);
        System.out.println("pending: " + queue.pendingMessages()
                + " messages, " + queue.pendingBytes() + " bytes");
        System.out.println("fourth rejected: "
                + rejected.isCompletedExceptionally());

        transport.finishOne();
        System.out.println("after first ack: " + transport.started);

        transport.finishOne();
        System.out.println("after second ack: " + transport.started);

        transport.finishOne();
        System.out.println("all accepted completed: "
                + (first.isDone() && second.isDone()
                        && third.isDone()));
        System.out.println("pending after drain: "
                + queue.pendingMessages() + "/"
                + queue.pendingBytes());
    }
}
~~~

Chạy bằng JDK 17+:

~~~bash
javac --release 17 WebSocketBoundedQueueDemo.java
java WebSocketBoundedQueueDemo
~~~

Stdout **đúng, ổn định, đã kiểm chứng bằng JDK cục bộ**:

~~~text
started: [A]
pending: 3 messages, 6 bytes
fourth rejected: true
after first ack: [A, BB]
after second ack: [A, BB, CCC]
all accepted completed: true
pending after drain: 0/0
~~~

Ở `ManualTransport`, từ “ack” trong tên và stdout là **tín hiệu mock do test chủ động gọi `complete(null)`**, **không phải application ACK của WebSocket peer thật**. Điều này chỉ kiểm chứng thứ tự khởi tạo send và accounting của queue, không kiểm chứng transport network hay server delivery.

### 5.1. Tại sao mẫu này giữ thứ tự?

- `offer` được đồng bộ bằng `synchronized`, nên cùng lúc chỉ một thread thực hiện admission và nối thêm stage.
- `tail.thenCompose(...)` làm cho chỉ khi operation trước **thành công** thì lời gọi transport tiếp theo mới bắt đầu.
- Ba message được chấp nhận theo **thứ tự lời gọi `offer` đạt được lock**.
- `pendingMessages` và `pendingBytes` tăng **trước khi** tạo send stage và chỉ giảm khi future internal hoàn tất.
- Một message quá quota nhận `CompletableFuture.failedFuture(RejectedExecutionException)` **ngay từ admission**; không được enqueue rồi âm thầm drop.
- `forCaller` tách biệt với future chain nội bộ: nếu caller tự cancel future quan sát của mình thì nó **không trực tiếp hủy internal ordering chain**.
- Nếu một send fail, chuỗi `tail` trở nên exceptional; những send đã nhận phía sau không được khởi tạo, cũng hoàn thành lỗi; `accepting=false` ngừng nhận message mới.

**Giới hạn mẫu demo:** `thenCompose` có thể chạy callback ngay trên thread hoàn thành future; `transport.send(...)` nên là lời gọi **nhanh, bất đồng bộ và không block**. Trong production nên đưa ownership và dispatch tới event loop/actor chuyên trách nếu nhiều producers/callbacks; cần state machine cho shutdown/timeout và metrics. Demo không hỗ trợ thay đổi thứ tự, ưu tiên ping/pong hoặc coalesce snapshots. Việc đếm UTF-8 dùng allocation tạm `getBytes(...)`; nếu payload rất lớn, phải giới hạn kích thước đầu vào **trước** khi tạo các bản copy.

### 5.2. Áp dụng transport thực cho `WebSocket`

`BoundedOrderedSender` dùng interface nhỏ `AsyncTextTransport` để có thể test không mạng. Sau khi tạo `WebSocket ws` thật, adapter tương ứng:

~~~java
// Đoạn minh họa trong một phương thức có WebSocket ws.
WebSocketBoundedQueueDemo.BoundedOrderedSender out =
        new WebSocketBoundedQueueDemo.BoundedOrderedSender(
                text -> ws.sendText(text, true)
                          .thenApply(ignored -> (Void) null),
                64, 256 * 1024);

CompletableFuture<Void> accepted = out.offer("hello");
accepted.whenComplete((ignored, failure) -> {
    if (failure != null) {
        // report/reconcile; không giả định peer chưa nhận message
    }
});
~~~

Đoạn này **không phải chương trình độc lập**; cần class demo và `ws` đã được thiết lập. Mỗi `text` là một **logical message trọn vẹn**, do đó dùng `sendText(text, true)`. Nếu muốn gửi một logical message qua nhiều fragments, cần một dispatcher có notion “message transaction” riêng (phần 7), không để fragments của hai messages khác nhau xen kẽ.

**Cần cải tiến khi dùng production:** Có chính sách khi queue đầy (defer/reject/close), global cap across sockets, timeout, bẫy `IOException`, close handshake, khôi phục sau reconnect. 64 messages/256 KiB trong adapter là **giá trị minh họa**, không phải mức tối ưu universal.

## 6. Một chuỗi gửi thành công không đồng nghĩa ACK nghiệp vụ

Có hai trục mà nhiều ứng dụng nhầm:

~~~text
Transport/send operation:
  sendText() ── future complete ──> bước gửi của JDK thành công

Application workflow:
  publish(commandId=42) ──> server receive ──> server process
                                    │                │
                                    └─ ACK/RESULT ◄──┘
~~~

Khi thiết kế ACK:
- Mỗi message có `messageId` ổn định qua retry.
- Client giữ mapping `messageId → pending result` ở **một bảng có giới hạn**, timeout.
- Server xác định ACK nghĩa là **đã nhận**, **đã ghi durable** hay **đã xử lý xong**. Các mức khác nhau không được gọi chung “delivered”.
- Có idempotency/deduplication phía server cho commands có side effects.
- Nếu ACK không đến, không mặc định message chưa từng được xử lý; retry chỉ theo protocol phù hợp.

Nếu WebSocket bị đóng ngay sau khi send future hoàn tất, remote application có thể chưa xử lý hoặc ACK chưa đến. `sendClose` sau data-send chain là **thứ tự đúng của thao tác local**, nhưng không thay cho application delivery confirmation.

## 7. Fragmentation: `last=false` chưa hoàn tất message

JDK17 `WebSocket.sendText(CharSequence data, boolean last)` và `sendBinary(ByteBuffer data, boolean last)` hỗ trợ gửi **một logical message** thành nhiều phần:

~~~java
webSocket.sendText("Hello, ", false)
         .thenCompose(ws -> ws.sendText("world!", true))
         .thenCompose(ws -> ws.sendText("next message", true));
~~~

Đoạn này là **minh họa**; với `last=false`, phần text đầu tiên **chưa kết thúc message**. Phần thứ hai `last=true` mới đóng logical message “Hello, world!”. Phần thứ ba bắt đầu message mới. Chaining tránh vừa có pending send, vừa giảm nguy cơ interleave fragments.

**Không làm thế này:**

~~~java
webSocket.sendText("part A", false)
         .thenCompose(ws -> ws.sendBinary(
                 ByteBuffer.wrap(new byte[]{1}), true)); // SAI
~~~

Nếu text message trước chưa kết thúc, gọi sendBinary không phải chuyển sang logical message binary mới hợp lệ; JDK17 future có thể hoàn thành `IllegalStateException` vì **previous textual data does not complete the message**. Ngược lại, không chuyển sang text giữa binary fragments chưa hoàn tất.

Một lưu ý tinh tế: dù các future đã complete lần lượt, nếu gửi `sendText("part A", false)` rồi xen một `sendText("unrelated", true)` từ producer khác, `"unrelated"` có thể được diễn giải như **continuation** của cùng logical text message, không phải message độc lập. Cần lock/actor để đảm bảo **mọi fragments của một message được gửi như một transaction logic**, rồi mới tới message tiếp theo.

### 7.1. Quyền sở hữu `ByteBuffer`

Javadoc `sendBinary(ByteBuffer, last)` nói không được **truy cập data buffer** cho tới khi future của operation hoàn tất. Sau completion bình thường, buffer không còn `remaining()`. Vì thế:

~~~java
ByteBuffer data = ByteBuffer.wrap(
        new byte[]{10, 20, 30});
CompletableFuture<WebSocket> f =
        webSocket.sendBinary(data, true);

// Không sửa data.position()/limit(), không ghi đè byte[]
// hoặc tái sử dụng buffer trước khi f hoàn tất.
~~~

Đây là **minh họa**. Lỗi phổ biến là đưa **cùng một `ByteBuffer` hoặc underlying byte[]** vào nhiều asynchronous sends rồi gọi `clear()`/`flip()` ngay. Kết quả có thể là dữ liệu trùng/mất/sai hoặc vi phạm buffer ownership. Trong queue, dùng buffer độc lập hoặc copy data khi ownership không thể chuyển giao; đặt memory cap cho chính các copy đó.

Với `sendText(CharSequence, last)`, **không sửa CharSequence** trước khi send future hoàn tất. `String` bất biến thích hợp; `StringBuilder`/`StringBuffer` mutable có thể dẫn tới data race khi bị thay đổi giữa lúc send. Dùng `toString()` tạo snapshot bất biến trước admission nếu producer còn giữ mutable source.

### 7.2. UTF-8 và lỗi UTF-16

Text WebSocket là **UTF-8** trên wire. JDK17 implementation note cho biết malformed UTF-16 sequence trong `sendText` có thể khiến future thất bại với `IOException`. Không dựa vào `String.length()` để cấp phát memory theo số byte; validate hoặc encode đúng khi cần byte quota. Với binary, count `ByteBuffer.remaining()` trước admission, không dùng `capacity()`.

Fragmented text còn có thể chia ở boundary không trùng code point/chunk; tránh tự giả định một fragment là một text message hoàn chỉnh phía receiver. `WebSocket.Listener.onText(WebSocket, CharSequence, boolean last)` có thể được gọi nhiều lần cho một message; chính `last` quyết định khi nào logical message hoàn tất.

## 8. Ví dụ Java 17+ số 2: WebSocket thật trên loopback, kiểm tra thứ tự message

Ví dụ này kiểm chứng API `HttpClient.newWebSocketBuilder()` và `sendText` thực tế mà **không cần server ngoài Internet**. Chương trình tạo một **mock WebSocket server cực nhỏ** bằng `ServerSocket`:

1. Nhận yêu cầu HTTP Upgrade (RFC 6455) trên loopback.
2. Tính `Sec-WebSocket-Accept` từ `Sec-WebSocket-Key` rồi trả `HTTP/1.1 101 Switching Protocols`.
3. Đọc đúng ba **masked client text frames**, giải mask và ghi nhận payload.
4. Nhận Close frame rồi trả Close frame.
5. Client gửi ba message bằng **`thenCompose` chain**, chờ hoàn thành, rồi gửi Close.

**Mock server chỉ là test harness**: cố ý hỗ trợ frames có `FIN=1`, payload ≤125 bytes và text opcode; không hỗ trợ fragmentation, extended payload lengths, extensions, TLS, ping/pong scheduling, quotas hay multi-client concurrency. **Không triển khai nó thành server production**.

Tạo file **`WebSocketOrderLoopbackDemo.java`**:

~~~java
import java.io.*;
import java.net.*;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;

public final class WebSocketOrderLoopbackDemo {
    private static String readHandshake(InputStream in)
            throws IOException {
        ByteArrayOutputStream buf = new ByteArrayOutputStream();
        int prev3 = -1, prev2 = -1, prev1 = -1, ch;

        while ((ch = in.read()) != -1) {
            buf.write(ch);
            if (buf.size() > 16384) {
                throw new IOException("Handshake too large");
            }
            if (prev3 == '\r' && prev2 == '\n'
                    && prev1 == '\r' && ch == '\n') {
                return buf.toString(
                        StandardCharsets.ISO_8859_1);
            }
            prev3 = prev2;
            prev2 = prev1;
            prev1 = ch;
        }
        throw new EOFException("Incomplete HTTP upgrade");
    }

    private static String acceptKey(String header)
            throws Exception {
        String key = null;
        for (String line : header.split("\r\n")) {
            if (line.regionMatches(true, 0,
                    "Sec-WebSocket-Key:", 0,
                    "Sec-WebSocket-Key:".length())) {
                key = line.substring(
                        "Sec-WebSocket-Key:".length()).trim();
                break;
            }
        }
        if (key == null) {
            throw new IOException("Missing WebSocket key");
        }
        byte[] digest = MessageDigest.getInstance("SHA-1")
                .digest((key
                        + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11")
                        .getBytes(StandardCharsets.US_ASCII));
        return Base64.getEncoder().encodeToString(digest);
    }

    private record Frame(int opcode, byte[] data) { }

    private static int requiredByte(InputStream in)
            throws IOException {
        int b = in.read();
        if (b == -1) throw new EOFException("Truncated frame");
        return b;
    }

    private static Frame readFrame(InputStream in)
            throws IOException {
        int first = requiredByte(in);
        int second = requiredByte(in);
        if ((first & 0x80) == 0
                || (second & 0x80) == 0) {
            throw new IOException(
                    "Expected final masked client frame");
        }
        int length = second & 0x7F;
        if (length >= 126) {
            throw new IOException(
                    "Demo supports payload <= 125 bytes");
        }

        byte[] mask = in.readNBytes(4);
        byte[] body = in.readNBytes(length);
        if (mask.length != 4 || body.length != length) {
            throw new EOFException("Truncated frame payload");
        }
        for (int i = 0; i < body.length; i++) {
            body[i] ^= mask[i % 4];
        }
        return new Frame(first & 0x0F, body);
    }

    public static void main(String[] args)
            throws Exception {
        InetAddress loopback =
                InetAddress.getLoopbackAddress();
        try (ServerSocket listener =
                new ServerSocket(0, 1, loopback)) {
            listener.setSoTimeout(5000);

            FutureTask<List<String>> server = new FutureTask<>(() -> {
                try (Socket peer = listener.accept()) {
                    peer.setSoTimeout(5000);
                    InputStream in = peer.getInputStream();
                    OutputStream out = peer.getOutputStream();

                    String key = acceptKey(readHandshake(in));
                    String response =
                            "HTTP/1.1 101 Switching Protocols\r\n"
                            + "Upgrade: websocket\r\n"
                            + "Connection: Upgrade\r\n"
                            + "Sec-WebSocket-Accept: "
                            + key + "\r\n\r\n";
                    out.write(response.getBytes(
                            StandardCharsets.ISO_8859_1));
                    out.flush();

                    List<String> values = new ArrayList<>();
                    for (int i = 0; i < 3; i++) {
                        Frame frame = readFrame(in);
                        if (frame.opcode() != 1) {
                            throw new IOException(
                                    "Expected text frame");
                        }
                        values.add(new String(
                                frame.data(),
                                StandardCharsets.UTF_8));
                    }

                    Frame close = readFrame(in);
                    if (close.opcode() != 8) {
                        throw new IOException(
                                "Expected close frame");
                    }
                    out.write(new byte[]{
                            (byte) 0x88, 2, 3, (byte) 0xE8
                    });
                    out.flush();
                    return values;
                }
            });

            Thread serverThread = new Thread(
                    server, "websocket-test-server");
            serverThread.setDaemon(true);
            serverThread.start();

            URI uri = new URI(
                    "ws", null, loopback.getHostAddress(),
                    listener.getLocalPort(), "/test", null, null);

            WebSocket socket = HttpClient.newHttpClient()
                    .newWebSocketBuilder()
                    .connectTimeout(Duration.ofSeconds(5))
                    .buildAsync(uri, new WebSocket.Listener() {
                        @Override
                        public void onOpen(WebSocket ws) {
                            ws.request(1);
                        }
                    }).get(5, TimeUnit.SECONDS);

            CompletableFuture<WebSocket> chain =
                    CompletableFuture.completedFuture(socket);
            chain = chain
                    .thenCompose(ws -> ws.sendText("one", true))
                    .thenCompose(ws -> ws.sendText("two", true))
                    .thenCompose(ws -> ws.sendText("three", true));
            chain.get(5, TimeUnit.SECONDS);

            socket.sendClose(
                    WebSocket.NORMAL_CLOSURE, "")
                    .get(5, TimeUnit.SECONDS);

            List<String> received = server.get(
                    5, TimeUnit.SECONDS);
            System.out.println("server messages: " + received);
            System.out.println("in order: " +
                    received.equals(List.of(
                            "one", "two", "three")));
        }
    }
}
~~~

Chạy bằng JDK 17+:

~~~bash
javac --release 17 WebSocketOrderLoopbackDemo.java
java WebSocketOrderLoopbackDemo
~~~

Stdout **đã kiểm chứng trên máy có loopback khả dụng**:

~~~text
server messages: [one, two, three]
in order: true
~~~

**Những gì được chứng minh và chưa được chứng minh:**

- Chứng minh thật: JDK WebSocket client đã Upgrade, gửi text frames qua TCP; mock server giải masked frames và thu được ba logical message đúng thứ tự.
- Chứng minh thứ tự: client chỉ gọi send 2 sau future send 1 hoàn tất, send 3 sau send 2.
- Không chứng minh: production server nào cũng chấp nhận handshake như mock, network có exactly-once delivery, message đã được xử lý nghiệp vụ hoặc queue có giới hạn trong example này. Ví dụ 1 giải quyết riêng queue cap.
- Test server chỉ hỗ trợ payload nhỏ vì đọc trực tiếp frames tối giản; **không** đưa parser này lên Internet.
- Client gửi Close frame **sau** data-send chain. Mock trả Close để kết thúc protocol handshake; production cần idle timeout/abort fallback nếu peer không phản hồi Close.
- Các futures `get(5, TimeUnit.SECONDS)` chỉ xuất hiện trong **chương trình kiểm thử** để tránh treo, không phải khuyến nghị block trên callback/event loop.

Tùy sandbox, bind loopback có thể bị chặn. Mock không làm TLS, vì địa chỉ `ws://loopback`; production dùng `wss://` khi cần confidentiality và verify TLS server identity.

## 9. Close/abort: dừng nhận message mới trước khi đóng output

Một WebSocket có **input side** và **output side** độc lập. `sendClose(int,String)` khởi tạo **orderly close** phía output; không nhất thiết ngay lập tức đóng input side. `abort()` đóng cả hai phía đột ngột. Theo JDK17 WebSocket Javadoc, gọi `sendClose` thành công có nghĩa Close message đã được gửi ở local send operation, **không thay application ACK**.

**Graceful close đúng thứ tự:**

~~~java
// Đoạn minh họa: "tail" là future của cuối hàng đợi data.
CompletableFuture<Void> closing =
        tail.thenCompose(ignored ->
                webSocket.sendClose(
                        WebSocket.NORMAL_CLOSURE, "")
                        .thenApply(ws -> (Void) null));
~~~

Phải ngừng admission **trước** khi lên lịch close; nếu không producer khác có thể thêm data **sau** stage close và bị fail/lost. Nếu send trước bị lỗi, `thenCompose` skip close; có thể phải `abort()` và xử lý cleanup theo failure policy. Nếu close được gửi nhưng peer không trả Close trong thời hạn, hãy có timeout rồi `abort` để tránh giữ connection vô hạn.

Các điều kiện cần thống nhất:

1. State `OPEN`: còn nhận message mới.
2. State `DRAINING`: từ chối/defer message mới, tiếp tục gửi backlog đã được chấp nhận.
3. State `CLOSING`: đã khởi tạo Close, không gửi thêm application data.
4. State `CLOSED/FAILED`: giải phóng pending queue, subscriptions, timers; callers nhận lỗi rõ.
5. `abort()`: dùng khi lỗi nghiêm trọng, deadline, protocol violation hoặc graceful close không hoàn tất theo policy.

**Close có thể đua với producer** nếu mỗi thread gọi WebSocket API độc lập. Đây là lý do cần một owner/dispatcher, không chỉ một biến `boolean closed` không đồng bộ.

### 9.1. `WebSocket.Listener.onClose` và `onError`

- `onClose(ws,status,reason)` báo phía **input** nhận Close. Nó không có nghĩa mọi application messages đã được server xử lý.
- `onError(ws,error)` báo lỗi nhận, ứng dụng cần shutdown/reconcile state. Javadoc không bảo đảm mọi lỗi send đều luôn tạo một `onError` tương ứng; **quan sát send future và listener**.
- Khi nhận Close, listener cần xử lý theo protocol, có thể trả lời Close nếu chưa gửi; không tự giả định lời gọi này trùng với hoàn thành send future.
- Với `onOpen`, ứng dụng cần gọi `ws.request(n)` nếu muốn nhận callbacks, vì counter receive ban đầu là **0**.

Không nhầm `request(n)` là cách giải phóng send queue: nó chỉ cho phép WebSocket listener được gọi thêm **n lần receive callbacks**, không phải n messages chắc chắn, càng không phải outbound `sendText` credit.

## 10. Receive backpressure khác send backpressure

~~~text
OUTBOUND (đề bài này)
app producers -> queue -> sendText/sendBinary futures -> network

INBOUND
network -> WebSocket.Listener callbacks -> app consumer
               ^
               |
       ws.request(n) controls number of receive callbacks
~~~

JDK17 `WebSocket.request(long n)` tăng internal counter cho **số lần gọi listener receive methods** như `onText/onBinary/onPing/onPong/onClose`. Một logical text message có thể đến trong **nhiều `onText` callbacks** với `last=false`, nên `request(1)` **không** đồng nghĩa xin một logical message hoàn chỉnh.

Ví dụ listener:

~~~java
WebSocket.Listener listener = new WebSocket.Listener() {
    @Override
    public void onOpen(WebSocket ws) {
        ws.request(1);
    }

    @Override
    public CompletionStage<?> onText(
            WebSocket ws, CharSequence chars, boolean last) {
        // Consumer xử lý từng phần theo ownership/size limit.
        handleFragment(chars, last);
        ws.request(1);
        return CompletableFuture.completedFuture(null);
    }
};
~~~

Đây là **mã minh họa**, `handleFragment` do ứng dụng định nghĩa và phải xử lý nhanh/đúng logic. Nếu xử lý bất đồng bộ và cần backpressure, nên chỉ request callback tiếp theo khi downstream có capacity; không mặc định `request(Long.MAX_VALUE)` nếu app không chịu nổi memory. Đừng xem receive counter như hard cap cho outbound.

**Vấn đề quan trọng:** việc không gọi `request` sẽ tạm ngưng các receive callbacks, nhưng peer/OS/network buffers vẫn có thể có dữ liệu in flight. Nó không thay inbound memory global cap hoặc protocol-level flow control/timeout.

## 11. Tránh deadlock khi gửi từ listener callback

Một anti-pattern:

~~~java
@Override
public CompletionStage<?> onText(
        WebSocket ws, CharSequence data, boolean last) {
    ws.sendText("reply", true).join(); // CÓ THỂ BLOCK callback thread
    ws.request(1);
    return CompletableFuture.completedFuture(null);
}
~~~

Blocking trong listener callback có thể:
- trì hoãn callback tiếp theo;
- gây starvation trên executor của client;
- tạo chu kỳ phụ thuộc với code đang chờ receive callback;
- làm mất khả năng xử lý timeout/Close/Ping kịp thời.

Cách an toàn hơn: **enqueue response vào bounded outbound dispatcher**, return một `CompletionStage` mô tả công việc receive nếu cần, và quản lý request(n) dựa trên capacity của downstream. Nếu listener gọi `sendText` trực tiếp từ nhiều callbacks/threads, nó có thể race với producer khác đang send; dùng **một owner** cho toàn output side.

### 11.1. Callback order ≠ business order từ nhiều nguồn

Javadoc bảo đảm listener receive methods được gọi thread-safe theo lifecycle; điều đó không biến mọi application tasks sinh từ callbacks thành một thứ tự send tuyệt đối khi chúng tiếp tục trên nhiều executors. Ví dụ nhận A, B theo thứ tự nhưng xử lý A trong task chậm hơn B: nếu cả hai gọi `sendText` khi hoàn tất, B có thể được gửi trước A. Muốn giữ A→B, gán sequence/message ID và **reorder tại outbound admission** hoặc xử lý tuần tự theo contract nghiệp vụ.

## 12. Quy tắc xử lý send failure và cancelled futures

Một send failure có thể xuất hiện ở nhiều thời điểm:
- Future lỗi `IllegalStateException` do có pending text/binary send hoặc loại message trước chưa hoàn tất.
- Future lỗi `IOException` do output đã đóng, disconnect hoặc I/O error.
- Future lỗi do malformed UTF-16 text (implementation note).
- Lỗi quota: chính application trả `RejectedExecutionException` ở admission.
- Timeout ứng dụng: operation pending quá lâu; không có ACK/tiến triển theo SLA.

**Cần phân biệt lỗi quota và lỗi network:**

| Tình huống | Caller nên thấy gì | Cách xử lý |
| --- | --- | --- |
| Queue full, chưa khởi tạo WebSocket send | Application rejection có mã rõ | Defer/retry khi capacity, hoặc fail theo policy |
| Text/binary send conflict do gọi đồng thời | `IllegalStateException` trong send future | Sửa serializer/chain, không retry ồ ạt |
| Message bị reject do output side đã đóng | `IOException` trong send future hoặc trạng thái đóng | Không enqueue thêm, reconcile/reconnect |
| Send operation thất bại sau khi đã khởi tạo | Exceptional completion (thường I/O) | Stop queue, fail pending, xác minh status nghiệp vụ trước retry |
| Caller không cần kết quả của future đã trả | Có thể cancel future quan sát | **Không** suy send operation đã được hủy/reversed |
| Peer chậm khiến future pending rất lâu | Queue cap bảo vệ bytes, nhưng latency tăng | Timeout, abort/close, telemetry và upstream backpressure |

**Đừng xử lý lỗi bằng `tail.exceptionally(e -> null)` rồi tự động tiếp tục mọi message** mà chưa biết WebSocket vẫn usable. Việc nuốt lỗi có thể khiến một message thất bại nhưng các message sau gửi tiếp, làm mất tính nhất quán nghiệp vụ. Nếu cần retry, hãy xác định có thể replay an toàn, có message ID/idempotency và connection state đã khỏe.

### 12.1. Cancellation và lifetime của underlying send

Mẫu `BoundedOrderedSender` cố ý trả **future riêng `forCaller`**. Người gọi cancel future đó chỉ thay đổi việc **nhận kết quả** ở caller; **không hứa hủy send operation đã khởi tạo** hoặc giải phóng queue slot ngay. Operation chính vẫn giữ quota tới khi internal future complete. Điều này bảo vệ thứ tự nếu caller hủy một task downstream.

Production cần API riêng để:
- Hủy **message chưa bắt đầu send** (nếu protocol cho phép).
- Không lấy message đã bắt đầu send ra khỏi hàng đợi một cách mù quáng.
- Đóng/abort session khi deadline chung hết.
- Giải phóng/từ chối pending messages đúng cách sau fail/close.
- Không leak timer, future callback hoặc ByteBuffer sau reconnect.

Cancel một `CompletableFuture` không phải mô hình transaction rollback và không thể đảo ngược message có thể đã đi qua network.

## 13. Quản lý queue và concurrency trên nhiều WebSocket connections

Một server/client có N sessions không thể chỉ dùng per-socket cap rồi cho N tăng vô hạn. Ví dụ 100.000 sockets × 1 MiB pending cap cho **100 GiB** potential payload trước khi tính overhead. Vì vậy cần:

- **Per-connection cap:** bytes, messages, age của item già nhất.
- **Global cap:** tổng pending across all WebSockets, theo process/tenant.
- **Quota cho producer:** outstanding commands, publish rate, số subscriber.
- **Bounded executor/task queue:** nếu user-code có deferred work; đừng chỉ bounded WebSocket queue nhưng unbounded upstream executor queue.
- **Metrics:** offered, accepted, rejected, in-flight bytes, queue bytes, send latency, errors, close reasons và queue age.
- **Fair scheduling:** tránh một connection/message lớn độc chiếm CPU hoặc memory.
- **Load shedding:** fail/reject slow clients, coalesce event types được phép và graceful close/abort khi quá hạn.

Nếu user interface gửi 60 vị trí con trỏ/giây, nhiều updates có thể coalesce theo latest-only semantics. Nhưng với audit log, chat sequence có thứ tự hoặc financial commands, phải lưu/gửi đầy đủ theo delivery contract, không tự giảm rate bằng drop.

### 13.1. Giới hạn bytes phải phản ánh ownership

Với text bất biến, `message.getBytes(UTF_8).length` là kích thước encoded payload ước lượng; WebSocket framing thêm overhead, JShell/JDK có thể tạo thêm internal copies. Với binary, giữ `ByteBuffer.remaining()` và không sửa buffer trước send future hoàn tất. Nếu buffer chỉ chứa view trỏ tới một mảng lớn, queue cap tính `remaining()` có thể nhỏ hơn **memory backing array** vẫn còn bị giữ. Global memory budget cần tính object retention/pooled direct buffers.

Với messages đã bị queue reject, caller cần **giải phóng hoặc không giữ reference** tới payload nếu không có kế hoạch retry. Nếu logic retry đặt payload vào một `ScheduledExecutorService` unbounded, bạn lại chuyển chỗ memory leak từ WebSocket queue sang scheduler queue.

### 13.2. Đo queue age, không chỉ queue size

Queue chỉ có 2 messages nhưng mỗi message chờ 15 phút là một kết nối có vấn đề. Theo dõi:
- `pending_message_count`.
- `pending_payload_bytes`.
- `oldest_pending_age_ms`.
- `send_completion_latency_ms` (khi bắt đầu operation đến send future complete).
- `queue_wait_latency_ms` (admission đến bắt đầu send).
- `send_failures_total` tách quota vs transport.
- `close_drain_duration_ms` và deadline exceeded count.
- `application_ack_latency_ms` **nếu** protocol có application ACK.

Không nhập nhằng `send_completion_latency` với end-to-end business processing latency.

## 14. Khi nào nên dùng một queue actor thay cho chuỗi future?

**Future chain + admission lock** như ví dụ 1 rất hữu ích để hiểu và xử lý hàng đợi nhỏ. Khi production có:
- nhiều loại messages (text/binary/ping/pong/close),
- cắt fragment lớn,
- priority rules và per-user quotas,
- cancellation của item chưa gửi,
- reconnect/replay,
- nhiều producer threads,
- high-water/low-water notifications,
- timeout và fair scheduling,

mô hình **single-thread actor/event-loop owner** thường rõ hơn:

~~~text
many producers
     │
     ▼
bounded mailbox of commands
     │
     ▼
one owner event loop
     │
     ├── dequeue one logical message
     ├── send sequential frames / fragments
     ├── await CompletableFuture completion
     ├── account/release quota
     ├── process error / deadline / close
     └── wake next command only when allowed
~~~

Không dùng một `Executors.newSingleThreadExecutor()` với unbounded task queue rồi nghĩ “chỉ một thread thì memory bounded”. Executor đơn luồng nhưng queue jobs không giới hạn vẫn tạo overload. Cần bounded mailbox với admission cap, và chỉ tối đa một send job active. Đừng thực hiện `join()` trong owner thread nếu future completion đòi owner chạy callback; sẽ deadlock.

### 14.1. Đưa Close vào chính owner

Một outbound actor có thể nhận command:
- `SendText(message)`,
- `SendBinary(bytes)`,
- `SendPing(payload)`,
- `DrainAndClose(reason)`,
- `Abort(cause)`.

Xử lý `DrainAndClose` phải:
1. Chuyển state sang `DRAINING`, ngừng nhận data messages mới.
2. Đợi các data messages đã accepted hoàn thành send futures.
3. Gửi Close frame đúng status/reason.
4. Đợi peer Close hoặc deadline; gọi `abort()` khi vượt deadline.
5. Hoàn thành/fail pending public futures, giải phóng memory và timer.

Không đẩy Close vào một queue chung **sau đó vẫn cho producers enqueue tiếp**. Một ngữ cảnh có nhiều priorities còn phải đảm bảo control messages không bị starve, đồng thời không reorder critical data messages.

## 15. Cách kiểm thử thứ tự gửi và hard cap

### 15.1. Deterministic unit test với manual send futures

Ví dụ 1 là unit test thuận tiện vì:
- Gửi `A` bắt đầu ngay; `BB` và `CCC` chưa được gọi lên transport.
- Thao tác thứ tư bị reject khi cap chạm.
- Chỉ khi test hoàn thành future `A`, `BB` mới bắt đầu.
- Chỉ khi `BB` hoàn tất, `CCC` mới bắt đầu.
- Sau ba completion, reserved=0 và không có pending messages.

Có thể mở rộng test:
- Giả lập failure khi `BB` đang gửi; `CCC` phải fail/skip, không gọi transport.
- Gửi một message đơn lẻ vượt byte cap, đảm bảo reject **trước** khởi tạo send.
- Nhiều producers cùng `offer`, kiểm tra IDs được accepted theo lock admission order.
- Mỗi lần complete, đối chiếu `pendingBytes>=0` và `pendingMessages>=0`.
- Test `forCaller.cancel(true)`: internal operation vẫn giữ resource đến khi thật sự complete.
- Test shutdown khi còn pending messages: không accept thêm, drain hoặc abort theo policy.
- Test producer slow/resume khi queue đạt HIGH rồi xuống LOW.

### 15.2. Integration test với server thật

Ví dụ 2 xác minh thứ tự trên network loopback, nhưng production cần kiểm tra:
- TLS `wss://`, certificate/hostname/trust policy.
- Server thực hỗ trợ large/fragmented messages, Ping/Pong/Close.
- Peer cố ý đọc chậm: queue và timeout có còn bounded không?
- Concurrent producers: thứ tự được giữ **theo sequence business** hay chỉ thứ tự admission?
- Disconnect sau một message đã sent nhưng trước application ACK.
- Reconnect rồi replay idempotently, không duplicate side effects.
- Hành vi khi `sendClose` được gọi trong lúc data backlog còn.
- Metrics/inflight counts không rò qua exception/cancel.
- Bounded global memory với nhiều kết nối và nhiều message sizes.

Đừng khẳng định WebSocket có exactly-once chỉ vì TCP có byte stream có thứ tự. TCP order là tính chất transport khi kết nối hoạt động; application reconnect/retry cần trạng thái riêng.

## 16. Các lỗi phổ biến và hậu quả

| Sai lầm | Vì sao nguy hiểm | Cách đúng |
| --- | --- | --- |
| Nhiều threads đồng thời `sendText` | `IllegalStateException` vì pending text/binary; business order không chắc | One sender owner, serialize bằng `thenCompose` hoặc queue actor |
| Dùng `thenApply` để trả future của send tiếp | Tạo nested future; dễ đánh dấu xong quá sớm | Dùng `thenCompose` |
| Gọi `join()` trên listener thread | Block/stall/deadlock callback | Async chain, bounded dispatcher |
| Xây một chuỗi triệu futures không có admission | Giữ payload/future nodes vô hạn | Hard caps trước khi enqueue |
| Chỉ cap số messages | Một message có thể nhiều MB | Cap bytes + entries + max message size |
| Chỉ cap queue waiting, bỏ qua active send | Thực dùng lớn hơn quota | Count **in-flight + waiting** |
| Dùng `String.length()` làm bytes | UTF-16 code units không bằng UTF-8 bytes | Đếm UTF-8 payload bytes, thêm overhead budget |
| Thay đổi `StringBuilder` trước future xong | Vi phạm mutable CharSequence ownership | Snapshot `String` |
| `ByteBuffer.clear()` khi future còn pending | Mất/sai payload, position/limit race | Không truy cập buffer cho tới future complete |
| Xen logical messages giữa `last=false` fragments | Có thể trộn message semantics | Gửi fragments atomically theo logical message |
| Gọi `sendBinary` khi text message chưa hoàn tất | API có thể fail `IllegalStateException` | Kết thúc đúng message type trước |
| Dùng `sendPing` payload >125 bytes | Javadoc cho `IllegalArgumentException` | Giới hạn control payload |
| Coi `request(1)` là outbound credit | Đó là receive callback demand | Đặt outbound queue cap riêng |
| Coi send future success là server ACK | Không chứng minh business effect | Message IDs + explicit ACK protocol |
| Fail send nhưng tự động tiếp tục chain | Có thể mất order/consistency | Stop/fail pending, reconcile state |
| Retry mọi message sau reconnect | Duplicate side effects | Idempotency, dedupe, sequence/ACK |
| Gọi `sendClose` trong lúc producers tiếp tục enqueue | Data có thể bị gửi sau close hoặc fail | State DRAINING, stop admission, drain then close |
| Đợi Close của peer vô hạn | Connection/resources mắc kẹt | Close deadline rồi `abort` |
| Dùng unbounded executor queue trước bounded WS queue | Chỉ dời điểm quá tải | Backpressure upstream + bounded all queues |

## 17. Bài tập tự kiểm tra

**Câu 1.** A và B cùng gọi `sendText` khi future A còn pending. Điều gì có thể xảy ra?  
**Đáp án:** Future B có thể complete exceptionally `IllegalStateException`. Nên đợi A complete normally trước khi khởi tạo B.

**Câu 2.** Vì sao `thenCompose` phù hợp hơn `thenApply` cho send futures?  
**Đáp án:** `thenCompose` flatten future trả bởi lời gọi send, bảo đảm stage tiếp theo bắt đầu sau khi operation trước hoàn tất.

**Câu 3.** Ba producers cùng gọi `offer` dưới `synchronized`, thứ tự admission có chắc phản ánh thứ tự event nghiệp vụ phát sinh không?  
**Đáp án:** Không. Chỉ là thứ tự lấy lock; cần sequence ID/single source để thể hiện business order.

**Câu 4.** `pendingMessages==0` có nghĩa server đã xử lý mọi message không?  
**Đáp án:** Không. Chỉ nghĩa local send operations đang theo dõi đã hoàn tất; cần application ACK riêng.

**Câu 5.** MAX_MESSAGES=3, đã có 1 send active và 2 waiting. Có được accept thêm message dù Deque waiting.size()==2 không?  
**Đáp án:** Không nếu cap đếm **cả active + waiting**, tổng đã bằng 3.

**Câu 6.** `String.length()` có đủ để cap byte payload UTF-8 không?  
**Đáp án:** Không. Unicode có độ dài byte khác UTF-16; nên count encoded bytes/actual buffer bytes.

**Câu 7.** `sendText("abc",false)` rồi `sendText("def",true)` tạo mấy logical messages?  
**Đáp án:** Một text message “abcdef” gồm fragments, không phải hai messages.

**Câu 8.** Có được sửa `ByteBuffer` trong khi `sendBinary` future còn pending?  
**Đáp án:** Không; Javadoc yêu cầu không truy cập buffer cho tới khi future complete.

**Câu 9.** Ping payload 126 bytes có hợp lệ?  
**Đáp án:** Không. Ping/Pong payload tối đa 125 bytes theo RFC/Javadoc.

**Câu 10.** `WebSocket.request(1)` xin thêm một outbound send slot?  
**Đáp án:** Không. Nó cho phép thêm một receive callback invocation.

**Câu 11.** Khi queue đầy, có nên drop một chat message đã accepted nhưng chưa gửi không?  
**Đáp án:** Không mặc định. Phải áp protocol/delivery policy; thường reject/defer message mới hoặc fail session, không drop bất ngờ.

**Câu 12.** Future send A thất bại, chain `A.thenCompose(sendB)` có gọi sendB không?  
**Đáp án:** Không. Stage B bị skip; chain hoàn thành lỗi nếu không có recovery handler cố ý.

**Câu 13.** Caller cancel future quan sát được từ queue có nghĩa network send đã hủy không?  
**Đáp án:** Không nhất thiết. Nếu queue tách internal future và caller future, operation vẫn tiếp tục để giữ order và accounting.

**Câu 14.** Gửi Close rồi vẫn enqueue một message mới có hợp lệ?  
**Đáp án:** Không. Khi bắt đầu orderly close cần ngừng admission, drain đã accepted trước Close và không gửi thêm application data sau Close.

**Câu 15.** Đã thấy server mock nhận A→B→C có bảo đảm message “exactly once” qua reconnect?  
**Đáp án:** Không. Loopback test chứng minh đúng thứ tự một kết nối; reconnect/retry cần idempotency và ACK/correlation.

## 18. Checklist triển khai production

1. Tạo **một owner cho output side** WebSocket; producers gọi queue, không gọi `sendText` trực tiếp từ nhiều threads.
2. Nếu cần **business order**, gán sequence ID tại upstream và xác định thứ tự admission/reorder đúng.
3. Serialize text/binary sends bằng `thenCompose`/actor, chỉ bắt đầu operation mới sau send future trước thành công.
4. Dùng queue admission **có giới hạn messages, payload bytes (active+waiting), age và global budget**.
5. Khi quota đầy, reject/defer/coalesce/close theo message semantics; không tự drop critical messages.
6. Không block listener/event loop bằng `get()`/`join()`; có bounded workers và async callbacks.
7. Với text, snapshot mutable `CharSequence`; với binary, giữ `ByteBuffer` bất biến/độc quyền tới future completion.
8. Với fragments, gửi đủ các phần của **một logical message** theo thứ tự tới `last=true` trước message khác.
9. Xử lý lỗi future và listener; không swallow `IllegalStateException`/`IOException` rồi tiếp tục pipeline như chưa lỗi.
10. Phân biệt Ping/Pong pending policy và payload ≤125 bytes; không xem `request(n)` là outbound credit.
11. Đóng đúng lifecycle: stop admission → drain → sendClose → chờ peer Close có deadline → abort khi cần.
12. Không suy send future complete là remote application ACK; thiết kế protocol message ID, ACK, idempotency khi cần.
13. Test slow receiver, reconnect, partial/fragments, multi-producer races, quota overflow và fail trước ACK.
14. Theo dõi pending bytes/messages, oldest age, send latency, quota rejections, send failures, close timeouts.
15. Dùng `wss://` và TLS hostname verification cho mạng ngoài/nhạy cảm; WebSocket API không tự bổ sung authorization/business validation.

## Tài liệu chính thức

- [Java SE 17 — WebSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.html): `sendText`, `sendBinary`, `sendPing`, `sendPong`, `sendClose`, pending send operations, future-completion và `request(n)`.
- [Java SE 17 — WebSocket.Listener](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.Listener.html): `onOpen`, `onText`, `onBinary`, `onClose`, `onError` và receive callback lifecycle.
- [Java SE 17 — WebSocket.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.Builder.html): `buildAsync`, handshake, connect timeout và subprotocols.
- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `thenCompose`, `whenComplete`, `failedFuture`, `handle` và completion semantics.
- [Java SE 17 — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): `position`, `limit`, `remaining` và buffer ownership.
- [RFC 6455 — The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455): handshake, frame masking, fragmentation, control frames và close handshake.

**Nguyên tắc cốt lõi:** Giữ **thứ tự bằng một outbound owner và send-future chain**, giới hạn **cả data đang gửi lẫn đang chờ** bằng hard cap, và phân biệt **local send success** với **remote application ACK**. Không dùng sự may mắn của scheduling/loopback để thay thế đúng thứ tự hoặc backpressure.
