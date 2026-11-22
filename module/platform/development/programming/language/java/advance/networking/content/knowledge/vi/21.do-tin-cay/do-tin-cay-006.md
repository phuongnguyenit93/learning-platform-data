# Bên nhận chậm, hàng đợi ghi và điều tiết tốc độ ở tầng ứng dụng — Java Networking (Java 17+)

## 1. Bài toán: vì sao một bên nhận chậm có thể làm bên gửi quá tải?

Một server realtime có thể tạo 200 sự kiện mỗi giây, trong khi một thiết bị di động chỉ đọc hoặc xử lý được 50 sự kiện mỗi giây. Nếu server tiếp tục đưa dữ liệu vào **hàng đợi ghi không giới hạn**, thời gian chờ tăng, heap có thể đầy, GC trở nên nặng, và cuối cùng ứng dụng có thể hết bộ nhớ. Tình huống này xảy ra dù TCP connection vẫn chưa báo lỗi.

Bên nhận chậm có thể do mạng nghẽn, thiết bị yếu, ứng dụng không đọc socket, browser ở nền, proxy giảm tốc, hoặc consumer phải chờ database. Hệ quả là khác nhau theo từng lớp, nhưng câu hỏi về độ tin cậy giống nhau: **bên gửi phải làm gì khi tạo dữ liệu nhanh hơn tốc độ bên nhận có thể hấp thụ lâu dài?**

~~~text
Producer (rất nhanh)                         Slow receiver
         |                                         |
         v                                         |
  app outbound queue                               |
      [m1,m2,m3,m4,...]                              |
         |                                         |
         v                                         |
    writer thread / NIO                             |
         |                                         |
         v                                         |
     kernel TCP send buffer -----------> network --+--> kernel receive buffer
         ^                                                 |
         |                                                 v
         +-- window/backpressure ----------- app read()/process()
~~~

TCP có **flow control**: bên nhận quảng bá receive window, nên kernel bên gửi không thể cứ đẩy bytes vượt khả năng nhận của peer. Nhưng TCP **không tự giới hạn queue của ứng dụng**, không biết producer tạo object mới ra sao, và không kiểm soát được các pending `Future`, HTTP/WebSocket outbound buffers hoặc retry tasks.

**Nguyên tắc:** cần kết hợp **hàng đợi hữu hạn**, **chính sách overload**, **điều tiết tốc độ**, **giới hạn thời gian** và, khi nghiệp vụ cần, **application acknowledgment (ACK)**. Không có một cấu hình TCP nào thay thế mọi thành phần trên.

Bài thuộc module **Java Advance - networking**, mục cha **Độ tin cậy**, đề bài **“Bên nhận chậm, hàng đợi ghi và điều tiết tốc độ ở tầng ứng dụng”**. Hai ví dụ đầy đủ được kiểm chứng bằng `javac --release 17`: một queue TCP thật trên loopback, một token bucket với đồng hồ mô phỏng.

## 2. Sau bài học, bạn sẽ hiểu

- Phân biệt **slow consumer**, **backpressure**, **bounded queue**, **load shedding**, **flow control**, **token bucket**, **pacing** và **fairness**.
- Biết rõ các trạng thái **enqueue thành công**, **socket write hoàn tất**, **TCP ACK**, **receiver đã parse message** và **business đã commit** không tương đương.
- Biết lý do `Socket.setSoTimeout(...)` giới hạn blocking **read**, không tự đặt write deadline.
- Chọn chính sách khi queue đầy: reject, timed wait, drop, coalesce, disconnect, pause producer hoặc durable spill.
- Hiểu vì sao giới hạn **số message** thôi chưa đủ, phải có giới hạn **bytes trong queue + in-flight**.
- Duy trì **một writer owner cho mỗi connection** để giữ framing và tránh xen bytes của các producers.
- Biết TCP là byte stream, phải có **message framing và validation độ dài**.
- Điều tiết tốc độ bằng **token bucket** theo encoded bytes; phân biệt burst capacity và refill rate.
- Xử lý `SocketChannel.write(ByteBuffer)` trả **0** hoặc ghi một phần; dùng `SelectionKey.OP_WRITE` có điều kiện.
- Nhận ra khi nào `Flow.Subscription.request(n)` hoặc `WebSocket.request(n)` có ý nghĩa và khi nào không thể thay socket-write backpressure.
- Thiết kế deadline, idempotency, retry, queue TTL, fair scheduling, observability và reconnect.

## 3. Bốn mốc quan trọng: đã xếp hàng ≠ đã gửi ≠ đã nhận ≠ đã xử lý

~~~text
1. Producer queue.offer(message) -> true
       |
       v
2. Writer lấy message, encode, write lên socket
       |
       v
3. Kernel/transport/receiver đọc bytes rồi parse frame
       |
       v
4. Receiver xử lý nghiệp vụ, lưu trạng thái, trả app ACK (nếu có)
~~~

| Tín hiệu | Thực tế xác nhận được | Không thể kết luận |
| --- | --- | --- |
| `queue.offer(msg) == true` | Message đã vào **queue của sender** | Không chứng minh đã gửi |
| Writer lấy item khỏi queue | Item được một worker nhận xử lý | Không chứng minh socket đã ghi |
| `OutputStream.write(bytes)` trả về | Local write operation hoàn tất theo hợp đồng API | Không chứng minh receiver application đã đọc |
| `SocketChannel.write(buf)` trả `n > 0` | `n` bytes đã được channel nhận để ghi | Không có nghĩa toàn bộ buffer đã ghi |
| TCP ACK của peer stack | Transport peer thừa nhận bytes theo TCP semantics | Không phải business ACK |
| `WebSocket.sendText(...)` future thành công | WebSocket send operation đã hoàn tất | Receiver business worker chưa chắc đã chạy |
| App reply `ACK(messageId)` | Hành động mà protocol định nghĩa là ACK đã xảy ra | Không bảo đảm database commit nếu ACK chỉ nghĩa “received” |
| Committed ACK từ transaction service | Commit theo contract của hệ thống nhận | Không mặc nhiên bảo đảm exactly-once khi retry/reconnect |

Một app có thể cần các mốc khác nhau: notification lossy chỉ cần cố gắng gửi; chat cần replay message sau reconnect; thanh toán cần idempotency key và xác nhận transaction commit. **TCP bảo vệ thứ tự bytes trong kết nối, không cung cấp durable exactly-once business delivery.**

### 3.1. Receiver chậm sẽ tác động thế nào tới TCP?

Receiver không gọi `read()` đủ nhanh → kernel receive buffer của receiver gần đầy → receiver advertise TCP window nhỏ/0 → sender kernel giảm tốc độ chuyển bytes → sender kernel buffer bắt đầu đầy → **blocking `OutputStream.write()` có thể chờ lâu**, hoặc **nonblocking `SocketChannel.write()` có thể trả 0**.

Tuy nhiên với payload nhỏ, kernel buffers còn rộng, nên write có thể trả về ngay dù receiver đang chậm. Không dùng một lệnh write thành công làm bằng chứng receiver đủ nhanh. **Độ trễ sẽ xuất hiện sau khi các lớp buffering cạn chỗ**.

### 3.2. Hàng đợi ứng dụng không thuộc quyền kernel

~~~text
Producer nhanh
    |
    +--> LinkedBlockingQueue không capacity
    |        |
    |        +--> Writer block khi TCP không nhận thêm bytes
    |        |
    |        +--> Heap giữ hàng triệu Message objects
    |
    +--> ExecutorService có task queue không giới hạn
    |
    +--> CompletableFuture callbacks giữ payload cho tới khi send xong
~~~

Một ứng dụng có thể OOM vì producer hoạt động quá nhanh **trước khi TCP báo lỗi**. Nếu nhiều clients cùng chậm, tổng tài nguyên có thể tăng theo số clients × queue cap.

## 4. Số học đơn giản: hàng đợi đầy nhanh thế nào?

Giả sử:

~~~text
Tốc độ tạo: 200 messages/s
Kích thước mỗi message đã mã hóa: 2 KiB
Tốc độ xử lý của receiver: 50 messages/s

Tạo ra   = 200 × 2 KiB = 400 KiB/s
Tiêu thụ =  50 × 2 KiB = 100 KiB/s
Chênh lệch = 300 KiB/s

Giới hạn queue = 3,000 KiB
Thời gian từ trống tới đầy ≈ 3,000 / 300 = 10 giây
~~~

Đây là **xấp xỉ** khi arrival/drain rates ổn định, không tính kernel buffers và object overhead. Nó chứng minh việc chỉ tăng queue cap không giải quyết bản chất: nếu tốc độ vào lâu dài **lớn hơn** tốc độ ra, backlog vẫn tăng.

Ký hiệu `λ` là tốc độ đến, `μ` là tốc độ gửi/tiêu thụ bền vững. Khi `λ > μ` đủ lâu, backlog tăng. Queue cap hữu hạn làm overload **hiện ra thành một quyết định** thay vì biến thành tăng heap vô hạn.

**Oldest message age** cũng quan trọng: queue còn nhiều chỗ nhưng một update vị trí mất 30 giây mới gửi thì message đó có thể đã vô nghĩa. Kết hợp **queue byte cap** với **deadline/TTL**.

## 5. Kiến trúc an toàn: producer → bounded queue → single writer

~~~text
Producer #1 -----+
Producer #2 -----+----> admission gate ----> bounded FIFO ----> one writer
Producer #3 -----+       | rate / byte cap                       |
                         |                                   encode frame
                         +-- rejected/throttled                 |
                                                              TCP/NIO
                                                                |
                                                        peer read/parse
~~~

**Một writer owner cho một byte stream** giúp:

1. Giữ thứ tự các frames đã được xếp theo FIFO.
2. Tránh hai threads ghi xen phần đầu/cuối của các messages vào cùng stream.
3. Có một nơi duy nhất quản lý current frame/`ByteBuffer.position`, write errors và timeout.
4. Giảm nguy cơ race giữa close, retry, cancellation và byte-budget release.
5. Dễ đo queue drain rate, blocked write time và số bytes in-flight.

**Không đồng nghĩa cần một OS thread cho từng connection** nếu có hàng nghìn clients: có thể dùng NIO `Selector`/event loop, hoặc async networking framework, miễn ownership/ordering rõ.

### 5.1. Các lựa chọn khi hàng đợi đầy

| Chính sách | Mục đích | Cạm bẫy |
| --- | --- | --- |
| Reject mới ngay | Fail fast, caller biết không được nhận | Caller cần backoff/retry contract |
| `offer(msg, timeout, unit)` | Chờ chỗ trống có giới hạn | Không block event loop |
| `put(msg)` | Chờ vô hạn cho pipeline backpressure nội bộ | Dễ deadlock/thread starvation |
| Drop newest | Giảm tải cho telemetry lossy | Không phù hợp payment/audit |
| Drop oldest | Ưu tiên trạng thái mới nhất | Mất lịch sử; không dùng cho logs cần đầy đủ |
| Coalesce theo key | Gộp updates, chỉ giữ latest state | Không hợp với increment/transaction events |
| Disconnect slow peer | Cô lập client gây backlog | Reconnect cần backoff và resync |
| Pause producer | Truyền backpressure ngược upstream | Source phải hỗ trợ demand control |
| Durable broker/disk queue | Giữ dữ liệu phục vụ replay | Quota, retention, latency và vận hành |

Một message về vị trí con trỏ chuột có thể drop/coalesce; event `createOrder` không được âm thầm drop. **Policy là một phần hợp đồng nghiệp vụ, không chỉ tuning throughput**.

### 5.2. `ArrayBlockingQueue` trong Java

~~~java
ArrayBlockingQueue<byte[]> queue = new ArrayBlockingQueue<>(100);

boolean accepted = queue.offer(encodedMessage);
if (!accepted) {
    // Phản hồi overload/throttle/drop theo contract đã công bố.
}
~~~

Đây là **mảnh code** cần biến `encodedMessage` và import `java.util.concurrent.ArrayBlockingQueue`.

- `offer(e)` **không chờ**, trả false khi queue đầy.
- `put(e)` **chờ** đến khi có chỗ hoặc bị interrupt.
- `offer(e, timeout, unit)` chờ có hạn; trả false khi hết thời gian.
- `take()` chờ tới khi queue có item; worker có thể block, event loop thì không nên.
- `remainingCapacity()` và `size()` chỉ là **snapshot**, có race nếu dùng `if size<cap then offer`; phải dựa kết quả offer.
- FIFO cho các items **đã enqueue**, không tự đảm bảo order theo business timestamps giữa concurrent producers.
- Byte arrays hoặc ByteBuffers đưa vào queue cần quyền sở hữu rõ ràng: producer **không được sửa payload** trước khi writer hoàn tất.

## 6. Demo Java #1: queue TCP hữu hạn, từ chối khi đầy

### 6.1. Tình huống có thể kiểm chứng

Dựng một TCP server chỉ trên `127.0.0.1`, một sender dùng `ArrayBlockingQueue<Message>(2)` và **một writer thread**. Writer lấy message đầu rồi **chờ một `CountDownLatch`**. Lúc đó producer thêm messages #2, #3, #4.

- #1 vào queue rồi đã được writer lấy ra: accepted.
- #2 và #3 lấp đủ hai slots: accepted.
- #4 bị từ chối: `queue.offer(...) == false`.
- Khi mở latch, writer gửi ba frames theo thứ tự.
- Receiver đọc **4-byte length prefix**, kiểm tra max length, đọc đủ payload và hiển thị IDs `[1, 2, 3]`.

**Lưu ý khoa học:** latch mô phỏng writer path chậm có kiểm soát, giúp test deterministic. Nó **không chứng minh TCP receive window đã đóng**. Trong thực tế, khi receiver đọc chậm lâu, TCP send buffers làm writer chậm theo cơ chế tương tự, nhưng một loopback test gửi vài bytes sẽ không dễ quan sát hiện tượng đó.

### 6.2. Tệp `BoundedOutboundQueueDemo.java`

~~~java
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class BoundedOutboundQueueDemo {
    record Message(int id, String content) {}

    public static void main(String[] args) throws Exception {
        ExecutorService readerWorker = Executors.newSingleThreadExecutor();
        ExecutorService writerWorker = Executors.newSingleThreadExecutor();

        try (ServerSocket server = new ServerSocket(
                0, 1, InetAddress.getByName("127.0.0.1"))) {
            server.setSoTimeout(5000);

            Future<List<Integer>> received = readerWorker.submit(() -> {
                try (Socket peer = server.accept()) {
                    peer.setSoTimeout(5000);
                    DataInputStream input =
                            new DataInputStream(peer.getInputStream());
                    List<Integer> ids = new ArrayList<>();
                    for (int i = 0; i < 3; i++) {
                        int length = input.readInt();
                        if (length < 1 || length > 128) {
                            throw new IOException("Invalid frame length");
                        }
                        byte[] data = input.readNBytes(length);
                        if (data.length != length) throw new EOFException();
                        String frame = new String(data, StandardCharsets.UTF_8);
                        ids.add(Integer.parseInt(
                                frame.substring(0, frame.indexOf('|'))));
                    }
                    return ids;
                }
            });

            try (Socket sender = new Socket(
                    InetAddress.getByName("127.0.0.1"),
                    server.getLocalPort())) {
                sender.setTcpNoDelay(true);
                ArrayBlockingQueue<Message> queue = new ArrayBlockingQueue<>(2);
                CountDownLatch firstSelected = new CountDownLatch(1);
                CountDownLatch releaseWriter = new CountDownLatch(1);

                Future<Integer> writing = writerWorker.submit(() -> {
                    DataOutputStream output =
                            new DataOutputStream(sender.getOutputStream());
                    int sent = 0;
                    for (int i = 0; i < 3; i++) {
                        Message message = queue.take();
                        if (i == 0) {
                            firstSelected.countDown();
                            if (!releaseWriter.await(5, TimeUnit.SECONDS)) {
                                throw new IOException("Writer gate expired");
                            }
                        }
                        byte[] payload = (message.id() + "|" + message.content())
                                .getBytes(StandardCharsets.UTF_8);
                        output.writeInt(payload.length);
                        output.write(payload);
                        output.flush();
                        sent++;
                    }
                    return sent;
                });

                System.out.println("Offer #1: " +
                        queue.offer(new Message(1, "alpha")));
                if (!firstSelected.await(5, TimeUnit.SECONDS)) {
                    throw new IOException("Writer did not start");
                }
                System.out.println("Offer #2: " +
                        queue.offer(new Message(2, "beta")));
                System.out.println("Offer #3: " +
                        queue.offer(new Message(3, "gamma")));
                System.out.println("Offer #4 with full queue: " +
                        queue.offer(new Message(4, "delta")));

                releaseWriter.countDown();
                System.out.println("Writer completed: " +
                        writing.get(5, TimeUnit.SECONDS));
                System.out.println("Receiver ids: " +
                        received.get(5, TimeUnit.SECONDS));
            }
        } finally {
            readerWorker.shutdownNow();
            writerWorker.shutdownNow();
        }
    }
}
~~~

Lệnh biên dịch/chạy với API mục tiêu Java 17:

~~~bash
javac --release 17 -encoding UTF-8 BoundedOutboundQueueDemo.java
java BoundedOutboundQueueDemo
~~~

**Stdout đã kiểm chứng trên JDK 24 với `javac --release 17`:**

~~~text
Offer #1: true
Offer #2: true
Offer #3: true
Offer #4 with full queue: false
Writer completed: 3
Receiver ids: [1, 2, 3]
~~~

### 6.3. Giải thích sâu chương trình

- `ServerSocket(0, 1, loopback)` chọn cổng trống, không mở listener Internet; test không cần server ngoài.
- `firstSelected.await` đảm bảo writer đã lấy #1 khỏi queue trước khi producer thêm #2/#3.
- `releaseWriter` giữ writer lại, nên queue capacity 2 chắc chắn đầy; #4 bị reject.
- Mỗi frame gồm `DataOutputStream.writeInt(payload.length)` rồi đúng bytes. Receiver `readInt` + `readNBytes(length)`, không giả định mỗi TCP read có đúng một message.
- `Writer completed: 3` xác nhận writer task đã thực hiện ba sends theo API; không tự kết luận chúng đã được database bên nhận commit.
- `Receiver ids` chứng minh **receiver local thật sự parse** ba frames, nhưng chưa có application ACK/transaction.
- `Future.get(5, TimeUnit.SECONDS)` là deadline của bài test; không block vô hạn.
- `try-with-resources` dọn Socket/ServerSocket; `shutdownNow()` kết thúc executor demo.

**Đây là test fixture, không phải production socket server:** chỉ nhận ba frames ngắn đã biết, parser dựa `'|'`, không có TLS, auth, global quota, message TTL, durable queue, retry hoặc shutdown protocol đầy đủ. Không thay nội dung message bằng dữ liệu mạng không tin cậy rồi tin rằng parser này an toàn.

## 7. Queue item cap chưa đủ: phải có byte budget

`ArrayBlockingQueue<>(100)` chỉ giới hạn **100 items**. Nếu mỗi item có thể chứa 10 MiB, chỉ riêng payload đã có thể tới khoảng 1 GiB. Phải tính ít nhất:

~~~text
queued payload bytes        : các frames còn trong app queue
in-flight payload bytes     : current frame đã dequeue nhưng write chưa xong
other user-space buffers    : HTTP/WebSocket library, serialization, retry...
TOTAL app outstanding       = tổng các lớp trên theo policy
~~~

**Đừng giải phóng byte reservation ngay khi dequeue** nếu writer vẫn giữ payload và đang bị chặn. Nếu có 10.000 clients và mỗi client được phép backlog 1 MiB, payload queued tối đa lý thuyết đã khoảng **10 GiB**, chưa kể overhead. Cần **per-client budget + per-tenant budget + global cap**.

### 7.1. Mẫu quản lý ngân sách bytes

Đây là **mảnh code độc lập về ý tưởng**, chưa tích hợp thành socket server; bảo vệ reservation bằng `synchronized` và tránh phép cộng tràn qua phép so sánh trừ:

~~~java
final class ByteBudget {
    private final long maxBytes;
    private long reservedBytes;

    ByteBudget(long maxBytes) {
        if (maxBytes <= 0) throw new IllegalArgumentException();
        this.maxBytes = maxBytes;
    }

    synchronized boolean reserve(long bytes) {
        if (bytes < 0 || bytes > maxBytes) return false;
        if (reservedBytes > maxBytes - bytes) return false;
        reservedBytes += bytes;
        return true;
    }

    synchronized void release(long bytes) {
        if (bytes < 0 || bytes > reservedBytes) {
            throw new IllegalStateException("Invalid release");
        }
        reservedBytes -= bytes;
    }

    synchronized long outstandingBytes() {
        return reservedBytes;
    }
}
~~~

Tích hợp admission với hai giới hạn item và bytes:

~~~java
int cost = encoded.length + Integer.BYTES; // payload + length prefix
if (!budget.reserve(cost)) {
    // Reject: byte budget đã đầy.
} else if (!queue.offer(encoded)) {
    budget.release(cost); // Rollback nếu item queue đầy.
} else {
    // Writer owns reservation until no longer retaining payload.
}
~~~

Đây là mảnh code có các biến `encoded`, `budget` và `queue` đã khai báo phù hợp. Production cần bảo vệ **đóng queue, admission và rollback** bằng một lifecycle owner/atomic state để tránh races với cancel/close. Phải release đúng một lần cả trong success, failure và cancellation. Nếu một message đơn lẻ vượt byte cap, **reject ngay**, không xếp một tác vụ không bao giờ có chỗ trống.

### 7.2. High/low watermark và TTL

Dùng hai ngưỡng để tạo **hysteresis**:

~~~text
0% ---------- 20% ---------------- 80% ------------ 100%
              ^                     ^
           RESUME upstream       PAUSE upstream
                                                    HARD CAP
~~~

Nếu chỉ bật/tắt quanh 80%, producer có thể dao động pause/resume liên tục. Ngoài byte cap, nên có **oldest message age limit**. Với dashboard chỉ cần latest state, một item tồn 10 giây có thể hết giá trị dù queue chưa đầy; coalesce/drop stale với contract rõ.

## 8. Điều tiết tốc độ: token bucket và giới hạn burst

**Queue limit** trả lời “tối đa bao nhiêu backlog được tồn tại đồng thời?”. **Rate limit** trả lời “mỗi khoảng thời gian tối đa bao nhiêu bytes/cost units được cho phép?”. Chúng giải quyết hai câu hỏi khác nhau.

Token bucket có:

- **Capacity B**: tối đa tokens tồn tại; quyết định burst tối đa.
- **Refill rate R**: số tokens bổ sung mỗi giây; quyết định tốc độ dài hạn.
- **Cost c**: tokens mỗi message phải tiêu, ví dụ encoded bytes.
- **Monotonic time**: trong production dùng `System.nanoTime()` để đo elapsed time, không dùng wall clock làm deadline.

~~~text
capacity = 9 tokens; refill = 6 tokens/giây

t=0:
  A cost4 -> true; còn 5
  B cost4 -> true; còn 1
  C cost2 -> false; vẫn còn 1

t=0.5s: +3 token -> 4
  D cost3 -> true; còn 1

t=0.75s: +1.5 token -> 2.5
  E cost3 -> false

t=1.0s: +1.5 token -> 4
  F cost4 -> true; còn 0
  G cost1 -> false
~~~

Nếu rate unit là bytes, nên tính **`payload.getBytes(UTF_8).length` + framing** khi cần. `String.length()` đếm UTF-16 code units, không phải bytes truyền. Dù tính đúng tokens, app-level limiter không hứa tốc độ vật lý TCP chính xác ở mọi mili-giây vì kernel buffering, TLS/HTTP framing và OS scheduling.

### 8.1. Đặt limiter ở đâu?

| Vị trí | Lợi ích | Rủi ro nếu chỉ dùng một lớp |
| --- | --- | --- |
| Trước enqueue | Producer nhận tín hiệu sớm, ít backlog | Không ngăn slow write vô hạn nếu vẫn cho token định kỳ |
| Trước socket write | Pacing tốc độ output | Queue có thể vẫn đầy nếu producer quá nhanh |
| Tại consumer/app subscription | Giảm demand khi xử lý chậm | Phải đảm bảo publisher thực sự tôn trọng demand |
| Per-user/per-tenant | Ngăn một actor chiếm throughput | Cần global budget thêm |
| Global output limiter | Bảo vệ băng thông service | Phải chia fairness, không làm một client khóa toàn hệ thống |

Trong pipeline thực tế nên có **admission gate + bounded queue + rate/pacing + expiry + failure policy**. Thiếu token không có nghĩa phải đợi vô hạn; nếu message hết TTL trong lúc chờ, reject/drop theo contract.

## 9. Demo Java #2: token bucket deterministic theo bytes

Chương trình sau **không truy cập mạng** vì nhiệm vụ của nó là kiểm chứng thuật toán ra quyết định. Nó dùng đồng hồ `nowNanos` mô phỏng và `synchronized allow` để khi dùng chung bucket không có race giữa refill và consume.

### 9.1. Tệp `TokenBucketRateLimitDemo.java`

~~~java
public class TokenBucketRateLimitDemo {
    static final class TokenBucket {
        private final double capacityBytes;
        private final double rateBytesPerSecond;
        private double availableBytes;
        private long lastRefillNanos;

        TokenBucket(double capacityBytes, double rateBytesPerSecond,
                    long startingNanos) {
            if (capacityBytes <= 0 || rateBytesPerSecond <= 0) {
                throw new IllegalArgumentException("Positive limits required");
            }
            this.capacityBytes = capacityBytes;
            this.rateBytesPerSecond = rateBytesPerSecond;
            this.availableBytes = capacityBytes;
            this.lastRefillNanos = startingNanos;
        }

        synchronized boolean allow(int costBytes, long nowNanos) {
            if (costBytes < 0 || nowNanos < lastRefillNanos) {
                throw new IllegalArgumentException("Invalid cost or clock");
            }
            long elapsed = nowNanos - lastRefillNanos;
            availableBytes = Math.min(capacityBytes,
                    availableBytes + elapsed / 1_000_000_000.0
                            * rateBytesPerSecond);
            lastRefillNanos = nowNanos;
            if (costBytes > capacityBytes ||
                    availableBytes + 1e-12 < costBytes) {
                return false;
            }
            availableBytes -= costBytes;
            return true;
        }
    }

    public static void main(String[] args) {
        TokenBucket bucket = new TokenBucket(9.0, 6.0, 0);
        System.out.println("t=0 A(4): " + bucket.allow(4, 0));
        System.out.println("t=0 B(4): " + bucket.allow(4, 0));
        System.out.println("t=0 C(2): " + bucket.allow(2, 0));
        System.out.println("t=500ms D(3): " +
                bucket.allow(3, 500_000_000L));
        System.out.println("t=750ms E(3): " +
                bucket.allow(3, 750_000_000L));
        System.out.println("t=1000ms F(4): " +
                bucket.allow(4, 1_000_000_000L));
        System.out.println("t=1000ms G(1): " +
                bucket.allow(1, 1_000_000_000L));
    }
}
~~~

Lệnh:

~~~bash
javac --release 17 -encoding UTF-8 TokenBucketRateLimitDemo.java
java TokenBucketRateLimitDemo
~~~

**Stdout đã kiểm chứng bằng OpenJDK 24 sau khi compile `--release 17`:**

~~~text
t=0 A(4): true
t=0 B(4): true
t=0 C(2): false
t=500ms D(3): true
t=750ms E(3): false
t=1000ms F(4): true
t=1000ms G(1): false
~~~

### 9.2. Cách đọc kết quả và giới hạn

- Sau A/B, bucket chỉ còn 1 token; C cost2 bị từ chối.
- Sau 500 ms có thêm 3 tokens; D cost3 chấp nhận.
- Sau 250 ms tiếp theo chỉ thêm 1.5 tokens, nên E cost3 vẫn bị từ chối.
- Sau thêm 250 ms nữa, bucket có đủ 4 tokens; F chấp nhận và G bị từ chối.
- `allow(...) == true` chỉ là **cho phép** một công việc đi tiếp, không có nghĩa socket gửi hay receiver đã ACK.
- Nếu `costBytes > capacityBytes`, message sẽ không vừa bucket; nên reject hay dùng đường streaming riêng có quota.

Trong production, dùng `System.nanoTime()` làm nguồn elapsed time, cân nhắc fixed-point math để tránh sai số double ở high throughput, và giới hạn concurrency/token contention. Đây là demo thuật toán deterministic, không phải benchmark băng thông. **Rate limiter không thay byte cap**, vì receiver có thể ngừng đọc hẳn dù tokens vẫn tiếp tục refill.

## 10. Phối hợp limiter, byte budget, queue, writer và ACK

~~~text
Business producer
   |
   v
Serialize + validate max frame size + deadline
   |
   v
Token bucket / demand controller
   |
   v
Reserve byte budget (queued + in-flight)
   |
   v
Bounded queue.offer(frame)
   +------ fail ------> rollback budget, reject/throttle
   |
   v
Single writer → TCP/NIO → receiver parser
   |
   v
Local send completed → release user buffer reservation
   |
   v
Optional application ACK with messageId
   |
   v
Mark received/accepted/committed per explicit protocol
~~~

Một thứ tự hợp lý:

1. **Encode immutable payload** để biết kích thước, chống payload thay đổi sau admission.
2. **Validate max frame size** và TTL trước khi giữ tài nguyên.
3. Kiểm tra rate limit/demand theo contract.
4. Reserve queue+in-flight byte budget và xác minh connection còn active.
5. Thử `queue.offer`. Nếu thất bại, rollback reservation; không đánh dấu message “đã gửi”.
6. Writer lấy frame, ghi **đến khi hết bytes**, giữ buffer position và tính lỗi.
7. Giải phóng user-space byte reservation đúng một lần khi không còn giữ payload; **không** tự coi đây là business ACK.
8. Nếu cần xác nhận nghiệp vụ, dùng message ID và ACK riêng, với giới hạn số **unacked outstanding**.
9. Nếu mất kết nối, phân loại queued/in-flight/unknown outcome theo contract; không retry side-effect mù.

**Lưu ý về token refund:** nếu token dùng để rate-limit **attempts**, việc queue full không nhất thiết được hoàn token; nếu token chỉ tính **accepted messages**, bạn có thể thiết kế reserve/rollback atomically. Đây là quyết định semantics, phải ghi rõ để tránh “mất token” hoặc đếm sai.

### 10.1. Các hàng đợi ẩn cần kiểm soát

Ngoài `ArrayBlockingQueue` bạn tạo, còn có thể có:

- Executor task queue của `ExecutorService`.
- Callbacks và CompletableFuture chains giữ payload.
- Outbound buffers của HTTP/WebSocket library.
- Retry queue, dead-letter queue, disk staging.
- Per-tenant fanout buffers hoặc actor mailboxes.
- Logging/metrics async pipelines.

**Chỉ giới hạn main queue chưa đủ** nếu các hàng đợi khác không có cap hoặc timeout. Tính tổng outstanding bytes theo các nơi mà application có quyền kiểm soát.

## 11. Blocking TCP: các timeout dễ nhầm

### 11.1. `SO_TIMEOUT` áp dụng đọc, không phải ghi

Với classic `Socket`:

~~~java
socket.setSoTimeout(5000); // timeout cho blocking input read
socket.getOutputStream().write(payload); // KHÔNG được bảo đảm write timeout 5s
~~~

Đây là mảnh code có `socket` và `payload` đã được khởi tạo. Java `Socket.setSoTimeout` quy định timeout cho `read()` trên `InputStream` của socket. Nó **không tự đặt deadline** cho `OutputStream.write()`. Nếu receiver ngừng đọc, blocking write có thể kẹt lâu.

Để xử lý write deadline, cân nhắc **SocketChannel nonblocking + Selector** hoặc network framework có send/cancel/timeout tương ứng; có thể close connection khi không còn progress. Không coi việc gọi `Thread.interrupt()` bất kỳ là lời hứa an toàn rằng classic Socket OutputStream write luôn bị ngắt ngay trên mọi JDK/OS.

### 11.2. `SO_SNDBUF` và `TCP_NODELAY` không chữa backlog

- `Socket.setSendBufferSize`/`SO_SNDBUF` là gợi ý kích thước kernel send buffer, có thể chịu chính sách OS; không phải app byte budget.
- Tăng send buffer có thể **trì hoãn** lúc write bị block, nhưng cũng che slow consumer lâu hơn.
- `setTcpNoDelay(true)` có thể giảm tác động Nagle với một số message nhỏ; nó **không làm receiver xử lý nhanh hơn**.
- `Socket.isConnected()` không phải liveness/throughput test của receiver ở hiện tại.
- TCP ACK không phải app-level ACK; đừng thay protocol idempotency bằng socket options.

### 11.3. Framing bắt buộc vì TCP là byte stream

Hai lần `OutputStream.write` không bảo đảm bên nhận có đúng hai lần `InputStream.read` với kích thước giống nhau. Một frame có thể bị tách thành nhiều reads hoặc nhiều frames gộp vào một read.

Ví dụ length-prefix:

~~~text
4-byte big-endian length | N bytes payload
+-----------------------+--------------------------+
| uint32 payload length | payload N bytes          |
+-----------------------+--------------------------+
~~~

Receiver phải đọc đủ prefix, **validate 0 ≤ length ≤ MAX_FRAME_BYTES trước khi allocate**, rồi đọc **đúng N bytes** và kiểm tra EOF. Demo #1 dùng `DataOutputStream.writeInt`, `DataInputStream.readInt`, `readNBytes` và max frame 128 bytes.

Không dùng `InputStream.available()` để xác định đầy đủ message; nó chỉ cho biết bytes có thể đọc ngay không block theo stream contract.

## 12. NIO SocketChannel: partial writes, write(0) và OP_WRITE

Nonblocking `SocketChannel.write(ByteBuffer)` có thể trả số dương **nhỏ hơn** số bytes còn lại hoặc **0** khi kernel socket buffer không còn đủ chỗ. Khi ghi, `ByteBuffer.position` được tăng đúng theo bytes đã ghi.

~~~java
SocketChannel channel = SocketChannel.open();
channel.configureBlocking(false);
// ... connect/finishConnect và đăng ký Selector trước khi write ...

ByteBuffer frame = ...; // immutable/owned bởi single writer.
int n = channel.write(frame);
if (n == 0 && frame.hasRemaining()) {
    // Chưa thể ghi thêm: đợi OP_WRITE thay vì quay vòng CPU.
}
~~~

Đây là **mảnh code** chưa đầy đủ connection/selector lifecycle, không phải chương trình độc lập; cần import `java.nio.ByteBuffer` và `java.nio.channels.SocketChannel`. Không gọi `frame.clear()` hay xóa frame sau một write khi `hasRemaining()` vẫn true.

### 12.1. Bật `OP_WRITE` khi có bytes chờ

~~~text
Outbound queue rỗng và current frame đã xong:
    tắt OP_WRITE (tránh selector wakeup liên tục).

Producer enqueue frame:
    thông báo owner selector, wakeup nếu cần;
    bật OP_WRITE hoặc thử write ở owner thread.

Selector key.isWritable():
    ghi current ByteBuffer theo số bytes có thể ghi;
    nếu frame còn remaining, giữ position và đợi lại;
    nếu frame hết, lấy frame tiếp theo;
    nếu không còn frame, TẮT OP_WRITE.

write() trả 0:
    không spin while(true), quay lại Selector.select().
~~~

Nhiều sockets luôn **writable** khi OS send buffer có chỗ. Nếu giữ `OP_WRITE` bật dù không có pending data, selector có thể wakeups liên tục, đốt CPU (**busy-spin**).

Mảnh code interest bits:

~~~java
int flags = key.interestOps();
key.interestOps(flags | SelectionKey.OP_WRITE); // Khi có pending bytes.

// ... sau khi drain hết ...
key.interestOps(key.interestOps() & ~SelectionKey.OP_WRITE);
~~~

Đây là **mảnh code** chạy trong đúng selector owner thread, với `SelectionKey key` hợp lệ. Nếu producer ở thread khác, dùng queue thread-safe, `selector.wakeup()` và phối hợp interestOps/state an toàn. Một server đầy đủ phải xử lý `OP_ACCEPT`, `OP_CONNECT`, `OP_READ`, cancellation, EOF và errors. Không dùng `write==0` làm dấu hiệu receiver đã chết; đó là backpressure nhất thời.

## 13. Reactive Flow, WebSocket và HTTP không cùng cấp backpressure

`Flow.Subscription.request(n)` trong Java Reactive Streams là **demand về số items** từ subscriber tới publisher. Nó không trực tiếp đặt TCP receive window; một item có thể chứa payload lớn, nên vẫn cần byte budget.

Với `java.net.http.WebSocket.Listener`, `WebSocket.request(n)` cấp demand cho **receive callbacks**. Nó không trực tiếp giới hạn **outbound** app queue khi gọi `sendText`. Một `sendText(...)` future hoàn tất không chứng minh remote business consumer đã commit event.

~~~java
@Override
public CompletionStage<?> onText(
        WebSocket webSocket, CharSequence data, boolean last) {
    // Xử lý/cấp thêm demand phù hợp năng lực consumer.
    webSocket.request(1);
    return CompletableFuture.completedFuture(null);
}
~~~

Đây là **mảnh method trong WebSocket.Listener**, imports `CompletionStage` và `CompletableFuture`; WebSocket text message có thể fragment, `last` mới cho biết message boundary. Không request vô hạn khi downstream chưa có capacity.

HTTP/2 có **stream-level flow control** bên cạnh TCP flow control, nhưng một tầng app vẫn cần admission/queue limits. Kể cả có reactive demand, nếu source bị xử lý trong một thread khác và vẫn tạo dữ liệu bất chấp demand, bạn lại xây được hàng đợi vô hạn.

## 14. ACK, retry và idempotency khi kết nối bị mất

~~~text
Sender                         Receiver
  |-- event ID=44 ------------->|
  |                              | đã commit business operation
  |<--- ACK ID=44 --------------X| ACK bị mất khi network đứt
  |
  | timeout; outcome tại sender là UNKNOWN
  | retry ID=44 nếu receiver không dedupe → có thể tạo dữ liệu trùng.
~~~

Phân biệt các mức xác nhận:

- **QUEUED**: message đang chờ ở sender.
- **WRITTEN**: send operation hoàn tất theo API.
- **RECEIVED**: peer parser đã nhận đủ message (nếu có protocol ACK).
- **ACCEPTED**: server đã nhận trách nhiệm xử lý.
- **COMMITTED**: transaction/durable log đã lưu thành công theo contract.

Nếu xử lý payment/order, **không retry mù** sau write timeout hoặc connection close; request có thể đã được xử lý rồi response bị mất. Sử dụng message ID, idempotency key, deduplication, bounded retry và cơ chế kiểm tra trạng thái. Với telemetry lossy, có thể dùng snapshot latest-state thay vì replay mọi message cũ.

### 14.1. Deadline theo phase

| Deadline | Đo sự chậm nào |
| --- | --- |
| Enqueue deadline | Producer có được queue chấp nhận đúng hạn không |
| Queue TTL | Message có hết giá trị trước khi gửi không |
| Write deadline | User-space sender có tiến triển hay bị block |
| Heartbeat timeout | Peer/network có dấu hiệu không phản hồi không |
| App ACK deadline | Business protocol có xác nhận message đúng hạn không |
| End-to-end deadline | Caller đã nhận kết quả nghiệp vụ trong SLO chưa |

Dùng `System.nanoTime()`/elapsed time cho deadline, không lấy `currentTimeMillis()` làm đồng hồ đơn điệu. Chậm ở một phase không tự chứng minh chậm ở các phase khác.

## 15. Chọn policy theo loại dữ liệu

| Loại dữ liệu | Khi receiver chậm |
| --- | --- |
| Sensor position / UI presence | Coalesce latest-value theo key; drop dữ liệu cũ đúng contract |
| Chat có lịch sử | Durable store/replay, queue live hữu hạn, resync sau reconnect |
| Payment / order | Không silently drop; idempotency + committed ACK |
| Telemetry lossy | Bounded queue, sampling/drop counters, ưu tiên giữ service sống |
| Video/live frames | Ưu tiên frame mới, drop expired frames |
| File transfer | Streaming/credit window/checksum, hạn chế concurrent sessions |
| API gateway | Admission control, queue ngắn có deadline, HTTP 429/503 tùy chính sách |
| WebSocket broadcaster | **Per-client** byte budget; slow-client disconnect/resync |
| Audit/event sourcing | Durable broker/retention quota, kiểm soát consumer lag |

Không để **một client chậm** block global broadcaster. Nhưng không làm rơi audit/payment events như thể chúng chỉ là các UI state updates.

### 15.1. Fairness và giới hạn toàn hệ

Ngoài per-client queue cap, nên có:

- Per-user/tenant quota, vì một user có thể mở nhiều connections.
- Global bytes cap, tính cả queued/in-flight/app futures.
- Max single message/frame size.
- Max oldest age hoặc deadline của từng loại event.
- Per-client rate, global rate và burst giới hạn.
- Fair scheduling, ví dụ round-robin theo budget bytes per connection.
- Bounded retry queue/backoff+jitter khi reconnect.
- Metrics và alert để biết đã reject/drop bao nhiêu.

## 16. Observability và chẩn đoán

| Metric | Diễn giải | Mục đích |
| --- | --- | --- |
| `outbound_queue_items` | Số items đang chờ | Cảnh báo đầy |
| `outbound_queue_bytes` | Bytes queued | Cảnh báo memory |
| `outbound_inflight_bytes` | Bytes writer đang giữ | Tránh cap giả |
| `outbound_oldest_age_ms` | Tuổi item cũ nhất | Phát hiện dữ liệu stale |
| `outbound_offer_rejected_total` | Tổng admission failures | Quan sát load shedding |
| `outbound_drop_total` | Tổng intentional drops | Kiểm soát mất dữ liệu |
| `writer_blocked_ms` | Thời gian chờ write | Transport/receiver congestion |
| `writer_bytes_per_sec` | Throughput write thực tế | So với producer arrival rate |
| `write_zero_returns_total` | Số nonblocking writes trả 0 | Send buffer không sẵn |
| `selector_op_write_wakeups` | Wakeups của OP_WRITE | Phát hiện busy-spin |
| `unacked_messages` | Chưa có app ACK | Unknown outcome risk |
| `application_ack_latency_ms` | Độ trễ business ACK | Receiver consumer/DB chậm |
| `slow_consumer_disconnect_total` | Cắt connection do backlog | Policy sensitivity |

**Không log raw payload, token, password hoặc message IDs vào metric labels high-cardinality**. Tổng hợp theo tenant/region/connection class và thu histograms p95/p99.

### 16.1. Phân biệt các bottleneck

| Quan sát | Khả năng | Hướng kiểm tra |
| --- | --- | --- |
| Queue tăng, write time tăng, TCP send queue cao | Receiver không đọc hoặc network congested | Receiver read rate, advertised window, retransmissions |
| Queue tăng, write time thấp | Producer/encoding/scheduling imbalance | Writer capacity, hidden task queues |
| Queue rỗng nhưng app ACK chậm | Business worker/db chậm | Consumer queue/transaction latency |
| `write() == 0` liên tục và CPU cao | NIO busy-spin | OP_WRITE toggle, Selector readiness |
| Heap tăng nhưng queue size nhỏ | Large payload/in-flight/Futures | Byte budgeting, buffer copies |
| Chỉ một client backlog cao | Per-client slow receiver | Isolate/disconnect/resync |
| Tất cả clients backlog cao | Systemic overload | Global cap, upstream rate, server health |
| Reconnect đồng loạt sau timeout | Thundering herd | Exponential backoff+jitter |

## 17. Lỗi lập trình thường gặp

| Sai lầm | Tại sao sai | Cách sửa |
| --- | --- | --- |
| Queue không giới hạn vì TCP reliable | TCP không giới hạn app heap | Bounded queue, byte cap |
| Chỉ cap số items | Large item có thể chứa hàng MiB | Byte budget và max frame |
| Dequeue xong release budget ngay | In-flight payload vẫn còn | Tính queued + in-flight |
| Gọi `put()` trên event loop | Có thể chặn mọi clients | `offer()` / nonblocking admission |
| Thread mới cho mỗi message | Quá nhiều threads | One writer/ bounded executor |
| Hai threads cùng ghi một TCP stream | Frame bytes bị xen | Serialize writes |
| Giả định một write = một read | TCP không có message boundary | Length-prefixed framing |
| Gửi length không validate | Peer có thể làm allocate huge | Max frame cap trước allocate |
| `setSoTimeout` được tưởng là write timeout | Giới hạn đọc, không phải ghi | Write deadline/cancel |
| Dùng `SO_SNDBUF` lớn để “chữa” | Chỉ trì hoãn pressure | Điều tiết upstream/app |
| Gọi `SocketChannel.write` một lần | Có partial/0 write | Giữ buffer position |
| Giữ `OP_WRITE` bật liên tục | Selector busy-spin | Chỉ bật khi pending |
| Vòng `while(write()==0){}` | Tiêu CPU vô ích | Chờ writable readiness |
| Mutate `ByteBuffer` sau enqueue | Data race/corruption | Immutable/ownership |
| Chỉ rate-limit, queue không bound | Receiver có thể dừng hoàn toàn | Kết hợp token bucket + cap |
| Release byte budget hai lần | Underflow/overadmission | Once-only lifecycle |
| Không release khi cancel/reject | Memory quota leak | finally/rollback |
| Drop order/audit âm thầm | Mất nghiệp vụ | Durable queue/ACK |
| Coi socket write là ACK | Chưa chứng minh receiver parse | App protocol ACK |
| Retry POST vô điều kiện | Trùng side effect | Idempotency |
| Một slow client chặn mọi fanout | Không có isolation | Per-client cap/fairness |
| Reconnect đồng loạt | Overload mới | Backoff + jitter |
| Không đo oldest age | Queue còn chỗ nhưng dữ liệu stale | TTL/SLO |

## 18. Ma trận kiểm thử nên có

| Test | Thiết lập | Kỳ vọng |
| --- | --- | --- |
| Queue capacity 2 | Writer tạm dừng sau dequeue #1 | #2/#3 accepted, #4 rejected |
| Unblock writer | Mở latch | Receiver có IDs [1,2,3] |
| Slow receiver | Test staging không đọc socket lâu | Writer chậm, queue bounded |
| Large frames | Item lớn hơn byte cap | Reject sớm |
| Variable-size items | Một item nhỏ, một item lớn | Byte budget khác item budget |
| In-flight accounting | Writer dequeue nhưng chưa ghi | Reservation chưa được release |
| Producer concurrency | N producers cùng offer | Không double-release/overwrite |
| TCP frame fragmentation | Chia frame qua nhiều reads | Decoder vẫn đúng |
| Invalid length prefix | Length âm hoặc quá lớn | Không allocate vô hạn |
| Token bucket burst | Capacity 9, rate 6/s | A/B true, C false |
| Token refill | Đồng hồ mô phỏng | Đúng stdout demo #2 |
| Clock goes backwards | nowNanos nhỏ hơn trước | Reject/validate |
| NIO write 0 | Buffer socket không sẵn | Không busy-spin |
| Partial write | Một frame cần nhiều writes | Giữ ByteBuffer position |
| No pending bytes | Selector idle | OP_WRITE disabled |
| Cancel in-flight | Đóng connection khi write đang chờ | Mark failed, release once |
| Stale message | TTL đã hết | Drop/reject theo contract |
| ACK loss | Receiver commit nhưng ACK mất | Idempotency, no blind retry |
| One slow among many | Broadcaster nhiều subscribers | Các clients khác vẫn phục vụ |
| Global overload | Mọi clients chậm | Global cap và fair shedding |
| Reconnect storm | N clients timeout cùng lúc | Backoff+jitter giảm spike |

Không dùng mạng công cộng hay server không có quyền để cố tình flood/blackhole dữ liệu. Dùng localhost hoặc staging có giới hạn.

## 19. Câu hỏi ôn tập và đáp án

### 19.1. Vì sao TCP flow control không cứu app queue?

Vì TCP chỉ kiểm soát bytes trong transport, không quản lý số lượng tasks, messages, retry jobs và user-space buffers ứng dụng tạo ra. Cần bounded admission/backpressure.

### 19.2. `ArrayBlockingQueue.offer()` trả false nghĩa gì?

Message **không được enqueue**. Caller phải xử lý reject/drop/pause theo contract, không đánh dấu message đã gửi.

### 19.3. `put()` vào queue đầy trong event loop có gì nguy hiểm?

Có thể block vô hạn và làm một slow client ảnh hưởng tất cả event-loop connections. Dùng nonblocking offer/demand control.

### 19.4. Queue 100 items, mỗi item có thể 5 MiB; payload tối đa?

Khoảng 500 MiB **trước object overhead**, nên item cap không đủ.

### 19.5. Writer đã lấy một payload 20 MiB nhưng chưa ghi xong; giải phóng byte budget ngay?

Không, nếu writer còn giữ payload. Reservation phải cover in-flight memory và release đúng một lần sau ownership thực sự kết thúc.

### 19.6. Token bucket 9 tokens, refill 6/s, A và B mỗi request cost4 tại t=0; C cost2 có pass?

Không: sau A/B còn 1 token; C bị reject. Tại t=0.5s bucket refill 3 token nên có thể nhận một yêu cầu cost3.

### 19.7. Rate limit có thay queue cap không?

Không. Rate limiter giới hạn tốc độ chấp nhận/gửi trung bình, còn receiver có thể không đọc chút nào; vẫn cần queue/backlog bound.

### 19.8. Tại sao `setSoTimeout(2000)` không bảo đảm write fail sau 2s?

Vì `SO_TIMEOUT` cho **blocking InputStream read**, không phải OutputStream write deadline.

### 19.9. `SocketChannel.write(buffer)` trả 0; nên làm gì?

Giữ buffer, chờ `OP_WRITE`, không loop spin. Nếu `OP_WRITE` không có pending frame thì tắt để tránh CPU spike.

### 19.10. Một `OutputStream.write` thành công có chứng minh order đã commit ở server?

Không. Muốn biết commit phải có business ACK/transaction result; còn retry cần idempotency để tránh duplicates.

### 19.11. Một broadcaster có 10.000 clients, mỗi queue cap 1 MiB, chỉ cần 1 GiB RAM?

Không. Queued payload lý thuyết đã tới khoảng **10 GiB**, chưa tính in-flight, kernel buffers, TLS, futures, threads. Cần global cap.

### 19.12. Telemetry latest-state có nên replay tất cả stale messages sau reconnect?

Không nhất thiết; nếu contract chỉ cần trạng thái mới nhất, coalesce và gửi snapshot mới thay vì hàng nghìn updates hết giá trị.

## 20. Checklist code review

- [ ] Có **item cap, byte cap, max frame size, oldest-age/TTL** cho outbound.
- [ ] Cả queued và in-flight payload đều được tính vào memory budget.
- [ ] Có **one writer owner** hoặc single event-loop owner cho mỗi connection.
- [ ] Không block event loop bằng `put()` hoặc `Future.get()` vô hạn.
- [ ] Khi queue đầy, có chính sách reject/drop/coalesce/pause/disconnect rõ ràng.
- [ ] Không silently drop dữ liệu cần durable delivery.
- [ ] Producer không sửa payload/ByteBuffer sau khi enqueue.
- [ ] TCP message framing có bounded decoder.
- [ ] Phân biệt enqueue, local write, peer read, app ACK và committed ACK.
- [ ] Không coi `Socket.setSoTimeout` là write timeout.
- [ ] Với NIO, giữ ByteBuffer position qua partial writes và xử lý write=0.
- [ ] Chỉ bật `OP_WRITE` khi pending bytes, tắt khi queue drain hết.
- [ ] Có rate limiter theo encoded bytes hoặc business cost, có burst cap.
- [ ] Rate limiter **không** thay bounded queue.
- [ ] Có per-client, per-tenant và global memory/rate budgets.
- [ ] Có fair scheduling, không để một slow client chặn broadcaster.
- [ ] Dùng monotonic elapsed time cho deadline/refill.
- [ ] Có bounded retry, backoff+jitter và idempotency khi cần.
- [ ] Có metrics queue bytes/age, write duration, reject/drop và ACK RTT.
- [ ] Có test slow writer/slow receiver, partial writes, cancellation và queue overflow.
- [ ] Không dùng đoạn demo làm production TCP protocol/server khi chưa bổ sung TLS/auth/security.

## 21. Tài liệu chính thức

- [Java SE 17 — ArrayBlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html): bounded FIFO, `offer/put/take`.
- [Java SE 17 — BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html): các chiến lược insert có/không chờ.
- [Java SE 17 — Socket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html): `SO_TIMEOUT`, `SO_SNDBUF`, `TCP_NODELAY`.
- [Java SE 17 — SocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html): partial writes, nonblocking write có thể trả 0.
- [Java SE 17 — SelectionKey](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectionKey.html): `OP_WRITE`, `interestOps`.
- [Java SE 17 — Selector](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html): nonblocking multiplexing và `wakeup`.
- [Java SE 17 — DataOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataOutputStream.html): `writeInt` cho frame length prefix.
- [Java SE 17 — DataInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html): `readInt` và parsing bytes.
- [Java SE 17 — Flow](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Flow.html): reactive backpressure, `request(n)`.
- [Java SE 17 — WebSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.html): send futures, receive demand, close semantics.
- [Java SE 17 — System.nanoTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()): elapsed-time clock.
- [RFC 9293 — TCP](https://www.rfc-editor.org/rfc/rfc9293): reliable byte stream, receiver window và flow control.
- [RFC 9113 — HTTP/2](https://www.rfc-editor.org/rfc/rfc9113): stream-level flow control.

**Tóm kết:** receiver chậm sẽ truyền áp lực ngược lên TCP, nhưng **không tự ngăn app tạo backlog vô hạn**. Độ tin cậy thực tế đòi hỏi một **bounded outbound queue theo items và bytes**, writer/framing có ownership, rate limiter, policy overload minh bạch, deadline, observability và application ACK/idempotency khi nghiệp vụ cần. Đừng nhầm **đã xếp hàng**, **đã ghi lên socket** với **đã được bên nhận xử lý và commit**.
