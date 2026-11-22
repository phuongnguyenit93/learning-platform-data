# Quyền sử dụng ByteBuffer trong thời gian thao tác chưa hoàn tất

*Module Java Advance – networking; ngữ cảnh: I/O bất đồng bộ với `AsynchronousSocketChannel`.*

## 1. Quy tắc quan trọng nhất

Khi ứng dụng gọi `AsynchronousSocketChannel.read(dst)` hoặc `AsynchronousSocketChannel.write(src)`, thao tác I/O **có thể vẫn đang chạy sau khi phương thức Java trả về**. Các API này không hoạt động như `SocketChannel.read/write` đồng bộ: chúng bắt đầu một operation và trả về `Future<Integer>`, hoặc nhận một `CompletionHandler` để thông báo kết quả về sau.

**Từ lúc submit một operation đến lúc nó hoàn tất, ByteBuffer được bàn giao cho I/O: không truy cập, không sửa, không `flip`, `clear`, `compact`, không tái dùng, không trả về pool và không thay đổi backing storage của nó.** Chỉ xử lý buffer sau khi xác nhận completion thành công, hoặc làm cleanup thận trọng khi operation thất bại.

Đây là quy tắc được nêu rõ trong `AsynchronousByteChannel` Javadoc: ByteBuffer không an toàn khi nhiều thread cùng truy cập và cần tránh truy cập buffer từ lúc read/write được khởi tạo đến khi operation hoàn tất.

~~~text
APP ĐANG SỞ HỮU BUFFER
   |
   +-- Chuẩn bị payload hoặc vùng trống, position / limit đúng
   |
   +-- Submit async read(dst) hoặc write(src)
   v
I/O PENDING  (buffer thuộc quyền operation)
   |
   +-- CẤM app/các alias chạm vào buffer
   |
   +-- SUCCESS: Future.get() / CompletionHandler.completed()
   |       |
   |       +-- kiểm tra số byte thực chuyển
   |       +-- xử lý partial read/write
   |       +-- parse / tiếp tục I/O / release khi thật sự xong
   |
   +-- FAILED / TIMEOUT / CANCELLED
           |
           +-- xử lý theo hợp đồng API, không mặc định state an toàn
~~~

Tốc độ operation không thể dự đoán: có thể hoàn tất trước dòng code kế tiếp, cũng có thể kéo dài rất lâu. Việc nhìn thấy một `Future` **không phải** bằng chứng completion.

## 2. ByteBuffer chứa cả dữ liệu lẫn trạng thái cursor

`ByteBuffer` là bộ nhớ byte cùng các mốc:

| API | Ý nghĩa |
|---|---|
| `capacity()` | Dung lượng tối đa của buffer; cố định đối với object |
| `position()` | Chỉ số byte kế tiếp cho thao tác tương đối |
| `limit()` | Giới hạn **loại trừ** không được vượt |
| `remaining()` | `limit - position`: số byte trong cửa sổ còn lại |
| `hasRemaining()` | Có ít nhất một byte trong cửa sổ hay không |
| `flip()` | Đặt limit bằng position cũ, position về 0 để đọc dữ liệu vừa điền |
| `compact()` | Chuyển byte chưa tiêu thụ về đầu, position bằng số byte giữ lại |
| `clear()` | Đặt position 0 và limit capacity; **không tẩy nội dung** |

~~~text
0 <= position <= limit <= capacity
remaining() = limit() - position()
~~~

Với **read bất đồng bộ**, buffer là **destination**: I/O sẽ ghi vào vùng `position..limit` và tăng position theo số byte nhận. Với **write bất đồng bộ**, buffer là **source**: I/O sẽ lấy byte từ vùng `position..limit` và tăng position theo số byte đã được channel chấp nhận.

Ví dụ source ban đầu có `HELLO`, `position=0`, `limit=5`. Nếu write hoàn tất sau khi chuyển 2 byte thì `position=2`, `remaining=3`. Lúc này ứng dụng **được quyền** gửi phần còn lại bằng một operation mới; trước khi operation cũ hoàn tất thì **không được nhìn hoặc thay đổi cursor**.

## 3. Quyền sở hữu theo từng giai đoạn

| Giai đoạn | Ai được phép thao tác buffer? | Quyết định hợp lệ |
|---|---|---|
| Mới tạo hoặc lấy từ pool | App | Điền dữ liệu, set position/limit |
| Chuẩn bị write/read | App | `flip` source write, tạo destination writable |
| Sau `read(dst)`, Future chưa hoàn tất | Operation read | App không truy cập destination/backing array |
| Sau `write(src)`, Future chưa hoàn tất | Operation write | App không truy cập source/backing array |
| `Future.get()` trở về thành công | App nhận lại quyền | Kiểm tra result, position và remaining |
| Trong `CompletionHandler.completed(...)` | Callback được giao quyền | Parse, tiếp tục I/O hoặc chuyển quyền qua queue |
| `Future.get(timeout)` ném `TimeoutException` | I/O có thể vẫn đang sở hữu | Không `clear`/reuse |
| Async operation báo timeout/cancel/error | Cần chính sách cleanup | Không mặc định buffer ở state thành công |
| Buffer đã trả vào pool | Pool hoặc consumer tiếp theo | Producer cũ không dùng nữa |

“Owner” ở đây là **quy tắc concurrency của ứng dụng**, không phải chức năng `ByteBuffer.lock()`. Java có thể cho phép caller gọi `clear` khi I/O pending, nhưng kết quả là **race/undefined application behavior**. Không có cách hợp lệ để suy ra “I/O chắc đã xong” chỉ bằng `Thread.sleep(...)`.

## 4. Các hành động không an toàn khi I/O pending

### 4.1. Đổi position hoặc ghi đè payload của write

~~~java
// Trích đoạn SAI; channel đã connected.
ByteBuffer src = StandardCharsets.UTF_8.encode("HELLO");
Future<Integer> pendingWrite = channel.write(src);
src.clear();                                  // SAI
src.put("WORLD".getBytes(StandardCharsets.UTF_8)); // SAI
~~~

Trong lúc đó I/O có thể vẫn đang lấy byte và cập nhật `position`. Nếu application đổi `limit`, `position` hoặc byte data, server bên kia có thể nhận payload trộn hoặc nội dung sai. Hành vi race phụ thuộc timing/implementation nên không thể viết test kỳ vọng lúc nào cũng tái hiện cùng lỗi.

### 4.2. Đọc/parse destination trước khi read hoàn tất

~~~java
// Trích đoạn SAI.
ByteBuffer dst = ByteBuffer.allocate(1024);
Future<Integer> pendingRead = channel.read(dst);
dst.flip();                          // SAI
String text = StandardCharsets.UTF_8.decode(dst).toString(); // SAI
~~~

Dữ liệu có thể chưa tới, mới tới một phần hoặc bị I/O cập nhật sau khi code trên đã parse. `read` trả Future không đồng nghĩa `dst` chứa message hoàn chỉnh.

### 4.3. Thao tác qua alias vẫn nguy hiểm

~~~java
byte[] bytes = new byte[256];
ByteBuffer view = ByteBuffer.wrap(bytes);
Future<Integer> pendingRead = channel.read(view);

bytes[0] = 42;                        // SAI: sửa backing array.
ByteBuffer duplicate = view.duplicate();
duplicate.put(0, (byte) 99);          // SAI: duplicate chia sẻ memory.
~~~

`duplicate()`, `slice()` và `asReadOnlyBuffer()` tạo view có position/limit riêng **nhưng chia sẻ vùng byte**. Read-only view không biến backing array thành immutable snapshot. Với direct buffer cũng cần quản lý ownership vùng nhớ tương tự.

**Quyền sử dụng buffer phải bao trùm mọi alias** có thể truy cập dữ liệu hoặc cursor liên quan. Nếu producer cần tiếp tục sửa mảng gốc, copy payload sang **buffer riêng** trước khi submit I/O.

## 5. Cách an toàn với Future

`AsynchronousSocketChannel.read(ByteBuffer)` và `write(ByteBuffer)` trả `Future<Integer>`:

~~~java
// Trích đoạn: src đã có payload và channel connected.
Future<Integer> pending = channel.write(src);
// Tuyệt đối không dùng src cho tới khi get() thành công.
int n = pending.get();
if (n < 0) {
    throw new IOException("Unexpected write result");
}
if (src.hasRemaining()) {
    // Khởi động write tiếp theo cho phần byte còn lại.
}
~~~

Khi `get()` **trả về thành công**, operation đã hoàn tất và application được phép xử lý ByteBuffer theo số byte thực chuyển. `Future` cũng có memory-consistency guarantee: các hành động của computation bất đồng bộ xảy ra trước những hành động theo sau việc lấy kết quả bằng `Future.get()`.

Với **read**:

~~~java
// Trích đoạn: protocol quy định chính xác 100 byte.
ByteBuffer dst = ByteBuffer.allocate(100);
while (dst.hasRemaining()) {
    Future<Integer> pending = channel.read(dst);
    int count = pending.get();   // Chỉ truy cập dst sau successful get().
    if (count == -1) {
        throw new EOFException("Incomplete frame");
    }
}
dst.flip();                     // Đã nhận đủ 100 byte, có thể parse.
~~~

Đoạn trên chưa phải server độc lập; channel, import và xử lý timeout cần được bổ sung. Vòng lặp phù hợp vì **mỗi read được chờ hoàn tất trước khi submit read tiếp**. Nếu protocol không biết trước length, cần framing riêng (header độ dài, delimiter, EOF-delimited theo quy tắc).

Không đồng nhất **“one read operation completed”** với **“đã có toàn bộ request”**: read có thể trả 1, 37 hoặc 100 byte tùy trạng thái TCP và giới hạn buffer.

## 6. Future.get(timeout) chỉ giới hạn thời gian chờ Future

~~~java
// Trích đoạn SAI:
Future<Integer> pending = channel.read(dst);
try {
    pending.get(1, TimeUnit.SECONDS);
} catch (TimeoutException ex) {
    dst.clear();                 // SAI, I/O có thể vẫn đang chạy.
    bufferPool.offer(dst);      // SAI, pool có thể phát lại memory.
}
~~~

`TimeoutException` của `Future.get(timeout, unit)` có nghĩa **caller đã chờ kết quả quá thời hạn**; nó **không dừng operation** và không chứng minh I/O đã hoàn tất. Buffer vẫn thuộc về operation nếu còn pending.

Ứng dụng phải thiết kế policy: tiếp tục theo dõi completion, hoặc đóng channel theo cách kiểm soát; không tự recycle buffer chỉ vì hết giờ chờ. `Future.get()` cũng có thể báo `InterruptedException`, `ExecutionException` hoặc `CancellationException`: cần phân loại, không giả định dữ liệu chắc chắn chưa truyền.

| Tình huống | Điều đã biết | Điều không được giả định |
|---|---|---|
| `future.get()` trả `n` thành công | Operation này đã hoàn tất | Đã gửi/nhận trọn message |
| `future.get(2, SECONDS)` trả `n` | Operation hoàn tất trước hạn chờ | Peer đã xử lý payload |
| `future.get(2, SECONDS)` ném `TimeoutException` | Việc chờ đã hết giờ | I/O đã dừng hoặc buffer có thể reuse |
| `future.isDone() == true` | Future ở trạng thái finished/cancelled | Chắc chắn thành công và buffer giống state trước đó |
| `future.cancel(...)` thành công | Yêu cầu hủy được ghi nhận | Byte chắc chắn chưa qua channel hoặc buffer đã phục hồi |

## 7. Timeout của chính read/write bất đồng bộ

`AsynchronousSocketChannel` có overload nhận timeout **của operation**:

~~~java
// Trích đoạn: Context/context do application khai báo.
channel.read(dst, 2, TimeUnit.SECONDS, context,
        new CompletionHandler<Integer, Context>() {
    @Override
    public void completed(Integer count, Context state) {
        // Operation hoàn tất thành công, kiểm tra số byte.
    }

    @Override
    public void failed(Throwable error, Context state) {
        // Nếu InterruptedByTimeoutException: đặc biệt thận trọng.
    }
});
~~~

Theo tài liệu Java 17:

- Nếu read/write vượt timeout của chính operation, nó hoàn tất thất bại với `InterruptedByTimeoutException`.
- Channel hoặc connection underlying có thể bị đặt vào **implementation-specific error state** khi implementation không bảo đảm được những byte đã/chưa đi qua.
- **Trạng thái của ByteBuffer (hoặc dãy ByteBuffer) có thể không xác định sau I/O timeout.** Javadoc khuyến cáo discard buffer hoặc cẩn trọng nghiêm ngặt, không truy cập trong lúc channel còn mở.

Đây là khác biệt lớn với `TimeoutException` của `Future.get(timeout)`: một bên chỉ hết **thời gian chờ kết quả**, còn một bên là **operation được báo timeout và buffer state có thể undefined**.

Trong service không có recovery protocol được thiết kế riêng, cách thận trọng là **đóng connection, không recycle buffer bất thường và tạo buffer/connection mới**. Không lấy `dst.position()` sau timeout để suy ra chính xác số byte đã truyền.

## 8. Future.cancel không phải rollback

Hủy `Future` không cung cấp ACK rằng byte chắc chắn chưa được gửi/nhận; không tự undo tác động của transport hoặc khôi phục cursor. Do đó sai khi:

~~~java
// Trích đoạn SAI:
Future<Integer> operation = channel.write(src);
operation.cancel(true);
src.clear();
pool.offer(src);                  // Nguy cơ use-after-release.
~~~

Sau cancel, cần xử lý lifecycle của channel và operation theo contract. Với I/O kết thúc bất thường, một phần dữ liệu có thể đã đi qua; retry nghiệp vụ có thể gây trùng nếu ứng dụng không dùng request ID và idempotency. Không biến `isCancelled` hoặc `isDone` thành xác nhận “buffer sạch và không còn operation nào chạm nó” trong mọi tình huống.

## 9. CompletionHandler: callback sở hữu buffer sau success

Overload dùng handler:

~~~java
// Trích đoạn: ch đã connected.
ByteBuffer inbound = ByteBuffer.allocate(4096);
ch.read(inbound, inbound,
        new CompletionHandler<Integer, ByteBuffer>() {
    @Override
    public void completed(Integer count, ByteBuffer buffer) {
        if (count == -1) {
            // EOF; kiểm tra frame dở dang, cleanup.
            return;
        }
        buffer.flip();
        // Parse những byte thực nhận và giữ partial frame.
        buffer.compact();
        // Có thể submit read tiếp khi trạng thái hợp lệ.
    }

    @Override
    public void failed(Throwable error, ByteBuffer buffer) {
        // Phân loại error; không clear/release tùy tiện.
    }
});
~~~

Đây **không phải chương trình độc lập**. Attachment truyền vào `read` là object được trả lại ở tham số callback. Dùng attachment giúp operation mang theo parser/buffer/session state riêng mà không cần biến global mutable.

`completed(count, attachment)` nghĩa operation đã báo kết thúc **thành công**; callback có thể xử lý ByteBuffer sau đó nếu không có consumer khác cạnh tranh. `failed(error, attachment)` phải có đường cleanup riêng, nhất là timeout operation.

Callback có thể được gọi rất nhanh và có thể chạy trên thread thuộc channel group. **Chuẩn bị state trước khi submit**; không giả định callback luôn bắt đầu sau khi dòng submit của caller đã trả về. Nếu callback chuyển buffer sang thread worker khác, phải dùng queue/latch/executor và chuyển lease; không được vừa cho worker đọc data vừa `clear` rồi đọc tiếp bằng cùng buffer.

## 10. Java 17+ runnable: chứng minh quy tắc ownership

Chương trình này chạy bằng loopback trong một JVM, không cần Internet và không dùng cổng cố định. Server và client dùng `AsynchronousSocketChannel`. Nó chứng minh:

1. Bắt đầu một pending read rồi gửi yêu cầu read thứ hai, nhận `ReadPendingException` do một read còn outstanding.
2. Client gửi chuỗi `HELLO` qua các Future write tuần tự; server đọc đủ năm byte qua một hoặc nhiều Future read. Các buffer chỉ được truy cập sau successful `get`.
3. Server khởi tạo read dùng `CompletionHandler` trên **buffer mới**; client gửi ký tự `!`. Callback xử lý rồi báo cho main bằng `CountDownLatch`.

Tệp **`AsyncBufferOwnershipDemo.java`**:

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousServerSocketChannel;
import java.nio.channels.AsynchronousSocketChannel;
import java.nio.channels.CompletionHandler;
import java.nio.channels.ReadPendingException;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class AsyncBufferOwnershipDemo {
    private static final int WAIT_SECONDS = 5;

    private static void sendAll(
            AsynchronousSocketChannel channel, ByteBuffer data)
            throws Exception {
        while (data.hasRemaining()) {
            Future<Integer> pendingWrite = channel.write(data);
            // 'data' belongs to the outstanding operation until get() succeeds.
            int count = pendingWrite.get(WAIT_SECONDS, TimeUnit.SECONDS);
            if (count < 0) {
                throw new EOFException("Write ended unexpectedly");
            }
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();
        try (AsynchronousServerSocketChannel server =
                     AsynchronousServerSocketChannel.open()) {
            server.bind(new InetSocketAddress(loopback, 0));
            Future<AsynchronousSocketChannel> pendingAccept = server.accept();

            try (AsynchronousSocketChannel client =
                         AsynchronousSocketChannel.open()) {
                client.connect(server.getLocalAddress())
                        .get(WAIT_SECONDS, TimeUnit.SECONDS);

                try (AsynchronousSocketChannel peer = pendingAccept
                        .get(WAIT_SECONDS, TimeUnit.SECONDS)) {
                    ByteBuffer inbound = ByteBuffer.allocate(5);
                    Future<Integer> pendingRead = peer.read(inbound);
                    System.out.println("readSubmitted=true");

                    try {
                        peer.read(ByteBuffer.allocate(1));
                        System.out.println("unexpectedSecondRead");
                    } catch (ReadPendingException expected) {
                        System.out.println("secondReadRejected=true");
                    }

                    ByteBuffer outbound =
                            StandardCharsets.US_ASCII.encode("HELLO");
                    sendAll(client, outbound);
                    System.out.println("writeRemaining=" +
                            outbound.remaining());

                    int firstCount = pendingRead.get(
                            WAIT_SECONDS, TimeUnit.SECONDS);
                    if (firstCount < 0) {
                        throw new EOFException("Unexpected EOF");
                    }
                    while (inbound.hasRemaining()) {
                        int count = peer.read(inbound)
                                .get(WAIT_SECONDS, TimeUnit.SECONDS);
                        if (count < 0) {
                            throw new EOFException("Truncated message");
                        }
                    }
                    inbound.flip();
                    System.out.println("received=" +
                            StandardCharsets.US_ASCII.decode(inbound));

                    CountDownLatch completed = new CountDownLatch(1);
                    AtomicReference<String> outcome = new AtomicReference<>();
                    AtomicReference<Throwable> error = new AtomicReference<>();
                    ByteBuffer callbackBuffer = ByteBuffer.allocate(1);

                    peer.read(callbackBuffer, null,
                            new CompletionHandler<Integer, Void>() {
                        @Override
                        public void completed(Integer count, Void ignored) {
                            try {
                                if (count != 1) {
                                    throw new IOException(
                                            "Expected one byte, got " + count);
                                }
                                callbackBuffer.flip();
                                outcome.set(Character.toString(
                                        (char) (callbackBuffer.get() & 0xff)));
                            } catch (Throwable failure) {
                                error.set(failure);
                            } finally {
                                completed.countDown();
                            }
                        }

                        @Override
                        public void failed(Throwable failure, Void ignored) {
                            error.set(failure);
                            completed.countDown();
                        }
                    });

                    sendAll(client,
                            StandardCharsets.US_ASCII.encode("!"));
                    if (!completed.await(WAIT_SECONDS, TimeUnit.SECONDS)) {
                        throw new IOException("Completion handler deadline");
                    }
                    if (error.get() != null) {
                        throw new IOException("Callback failure", error.get());
                    }
                    System.out.println("callback=" + outcome.get());
                }
            }
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 AsyncBufferOwnershipDemo.java
java AsyncBufferOwnershipDemo
~~~

**Stdout đã xác minh trên OpenJDK 24 bằng biên dịch `--release 17`:**

~~~text
readSubmitted=true
secondReadRejected=true
writeRemaining=0
received=HELLO
callback=!
~~~

Ý nghĩa:

- `readSubmitted=true`: chỉ báo đã khởi tạo read, **không phải** đã nhận xong data.
- `secondReadRejected=true`: read thứ hai bị từ chối khi read trước còn pending; không cần/chẳng được chạm buffer cũ để kiểm chứng.
- `writeRemaining=0`: client đã **chờ mọi Future write hoàn tất** và chuyển hết byte theo API; không có nghĩa peer đã xử lý nghiệp vụ.
- `received=HELLO`: server đợi successful completion của từng read để lấy đủ năm byte rồi mới `flip`.
- `callback=!`: handler đã xử lý buffer sau success completion; `CountDownLatch` làm main chỉ đọc kết quả sau callback.

Demo không in số byte của từng read, bởi TCP có thể chia thành nhiều đoạn ở các thời điểm khác nhau. Nó có giới hạn chờ để không treo mãi; khi timeout, demo thoát/đóng channel, **không tái sử dụng buffer khi I/O có thể outstanding**.

## 11. Concurrent read/write: đúng channel chưa chắc đúng buffer

`AsynchronousSocketChannel` an toàn khi gọi từ nhiều thread, nhưng quy định **tối đa một read và một write outstanding trên cùng channel**.

| Tình huống | Đánh giá |
|---|---|
| Một pending read vào `input` và một pending write từ `output` độc lập | Hợp lệ theo full-duplex channel |
| Hai pending read trên cùng channel | `ReadPendingException` |
| Hai pending write trên cùng channel | `WritePendingException` |
| Một read và write dùng **cùng ByteBuffer** | Không an toàn |
| Read vào buffer, write từ `buffer.duplicate()` cùng memory | Không an toàn nếu vùng dữ liệu bị cạnh tranh |
| Hai channel đồng thời ghi vào cùng destination buffer | Không an toàn |
| Source write là read-only view, nhưng producer sửa backing array | Không an toàn |

Vì vậy nên có **inbound buffer** và **outbound queue/buffer** độc lập. Với nhiều outbound messages, chỉ submit một write; khi complete, tiếp tục phần remaining rồi mới chuyển sang message khác. Đừng đưa `OP_WRITE` readiness của Selector vào logic này như thể nó là completion của `AsynchronousSocketChannel`.

## 12. Partial read/write và scatter/gather

Async read hoặc write có thể chuyển **ít byte hơn `remaining()`** lúc bắt đầu operation; trạng thái byte hợp lệ phải được kiểm tra **sau completion**. `read` trả `-1` khi EOF. Nếu `remaining() == 0` ngay lúc khởi tạo I/O, operation có thể hoàn tất ngay với kết quả `0`.

Với protocol có length-prefix, callback read chỉ có thể báo một phần header/body. Parser cần giữ trạng thái qua nhiều operation, không `clear` buffer khi còn frame dở dang. Với write, tiếp tục gửi source còn remaining trong operation mới; một callback trả số dương không tự động nói toàn bộ response đã gửi.

`AsynchronousSocketChannel` còn có overload **scattering read/gathering write** sử dụng `ByteBuffer[]`. Tất cả buffer thuộc dãy được submit đều nằm trong **cùng một lease operation** cho đến completion; không được thay đổi riêng header hoặc body khi operation chưa kết thúc.

~~~java
// Trích đoạn giao diện: header/body/state là object do app chuẩn bị.
ByteBuffer[] parts = {header, body};
channel.write(parts, 0, parts.length,
        0, TimeUnit.MILLISECONDS, state,
        new CompletionHandler<Long, State>() {
    @Override
    public void completed(Long count, State context) {
        // Xử lý remaining của từng buffer sau success completion.
    }

    @Override
    public void failed(Throwable error, State context) {
        // Error cleanup theo policy.
    }
});
~~~

Đoạn này **không phải chương trình độc lập**: `State`/`state` cần được định nghĩa. Nếu dùng buffer pool, cả `header` và `body` phải được giữ cho operation; không trả một trong hai về pool chỉ vì một buffer đã hết byte trước khi callback chạy.

## 13. Buffer pool: không có use-after-release

Pooling tiết kiệm allocation nhưng rất dễ tái sử dụng buffer quá sớm:

~~~text
FREE_IN_POOL
   → LEASED_TO_CONNECTION
   → PREPARED
   → IO_PENDING
   → COMPLETED_SUCCESS
   → PARSE / SEND_REMAINDER / CONSUMER
   → NO_MORE_IO_OR_CONSUMER
   → FREE_IN_POOL

FAILED / TIMEOUT / CANCELLED → cleanup, discard/quarantine khi cần.
~~~

Một quy trình tốt:

1. **Acquire** buffer cho đúng connection/message, biết ai đang sở hữu.
2. **Prepare** content và cursor, kiểm tra max payload.
3. **Submit**, đánh dấu in-flight và chuyển quyền cho operation.
4. **Complete**, kiểm tra count/remaining; tiếp tục I/O nếu cần.
5. **Release** về pool **chỉ** khi không còn I/O pending và consumer khác đã hoàn tất.
6. Với timeout/error, tách ra đường cleanup; không `clear` chỉ để “giải phóng cho nhanh”.
7. Tránh double-release bằng state machine hoặc lease token, và đặt giới hạn tổng buffer memory.

`ByteBuffer.allocateDirect()` không miễn trừ quy tắc ownership; direct memory cũng có thể bị ghi đè trong khi I/O native đang dùng nó. `slice`/`duplicate` không tạo buffer độc lập để pool có thể phát lại cho request khác.

## 14. Đồng bộ kết quả giữa callback và thread khác

Có ba vấn đề tách biệt: channel thread-safety, buffer ownership và **publication của kết quả**.

- `Future.get()` thành công tạo quan hệ happens-before từ computation bất đồng bộ tới thread nhận kết quả.
- `CountDownLatch.countDown()` và `await()` thành công cung cấp điểm đồng bộ để main nhìn thấy kết quả callback.
- `BlockingQueue` hoặc concurrent collection có thể dùng để chuyển message hoàn chỉnh sang worker với memory-visibility phù hợp.

Nếu callback muốn gửi buffer sang worker để parse mà không copy data, cần **chuyển lease độc quyền**; callback phải chờ worker release trước khi clear/submit read tiếp dùng cùng memory. Nếu muốn callback tiếp tục read ngay, thường **copy message byte** sang đối tượng độc lập cho worker, rồi callback mới reuse input buffer đã được xử lý xong.

Không dùng vòng lặp bận `while (buffer.position() < N)` hoặc `Thread.sleep` để quyết định buffer đã an toàn: không có hợp đồng memory synchronization và dễ sai theo timing.

## 15. Lỗi phổ biến

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Message gửi ra bị trộn nội dung | Ghi đè source khi async write pending | Không mutate đến completion, dùng outbound queue |
| Parser thấy dữ liệu cũ/trống | `flip` destination trước async read completion | Đợi Future/handler và kiểm tra count |
| `ReadPendingException` | Submit read khi read trước còn outstanding | Bắt đầu read mới chỉ sau completion |
| `WritePendingException` | Hai write overlap | Một write outstanding, gửi phần dư tuần tự |
| `TimeoutException` của `get` rồi buffer bị trả pool | Lẫn timeout chờ với timeout I/O | Vẫn giữ lease hoặc đóng channel có policy |
| `InterruptedByTimeoutException` | Async operation timeout | Buffer state có thể không xác định, discard/cleanup |
| `BufferUnderflowException` | Parser đọc nhiều hơn byte đã nhận | Framing, kiểm tra `remaining` sau completion |
| `BufferOverflowException` | Buffer quá nhỏ hoặc sai limit | Kích thước/giới hạn frame có kiểm soát |
| Duplicate view bị “tự đổi data” | Alias chia sẻ backing array | Copy hoặc quản lý tất cả alias |
| Memory leak / pool depletion | Callback lỗi không hoàn trả tài nguyên | Có cleanup riêng, thống kê in-flight leases |
| Duplicate transaction sau retry | Timeout bị hiểu là chắc chắn chưa gửi | Message ID, idempotency ở tầng nghiệp vụ |

## 16. Checklist code review

Trước `read/write`: buffer có đúng owner, size/position/limit và backing storage không? Có writer/reader khác đang thao tác memory hay không? Trên cùng channel có operation cùng chiều đang outstanding không? Callback hoặc Future có giữ được context, error policy và deadline không?

Sau completion thành công: kiểm tra count (bao gồm `-1` cho read), còn remaining hay không, frame đã đủ chưa. Nếu còn byte thì tiếp tục operation mới sau completion; chỉ release khi không có consumer hay operation khác tham chiếu.

Khi thất bại: phân biệt `TimeoutException` của Future wait, `InterruptedByTimeoutException` của actual operation, failure do network và cancel. Không đoán số byte đã/chưa đi qua và không tái dùng memory chỉ vì một timer hết hạn.

## 17. Tự kiểm tra

**1. `write(src)` đã trả Future thì `src.clear()` được chưa?** Chưa. Future không đồng nghĩa completion.

**2. `Future.get()` trả 3, source ban đầu 10 byte. Có phải 10 byte đã gửi?** Không. Chỉ ba byte được báo trong operation này; cần gửi phần remaining.

**3. `Future.get(1, SECONDS)` ném timeout. Có được recycle buffer?** Không; I/O có thể vẫn pending.

**4. Timeout của chính async operation xảy ra. Có tin `dst.position` là số byte đã nhận không?** Không. Theo Javadoc, trạng thái buffer sau timeout có thể undefined.

**5. Hai read cùng lúc trên cùng AsynchronousSocketChannel được không?** Không; `ReadPendingException`.

**6. Một read và một write cùng lúc trên cùng channel được không?** Có, dùng buffer độc lập.

**7. `ByteBuffer.duplicate()` có copy backing array?** Không.

**8. Handler `completed` có thể `flip(dst)` ngay không?** Có khi operation đã báo thành công và buffer thuộc handler, không có consumer cạnh tranh.

**9. Async read trả 24 byte, protocol cần 100 byte. Đủ message chưa?** Chưa; tiếp tục read sau completion và giữ trạng thái parser.

**10. Read-only view có tự bảo đảm payload bất biến không?** Không; alias/backing array còn có thể bị sửa.

**11. Callback đưa buffer cho worker xử lý; callback được clear rồi read tiếp vào buffer đó chưa?** Chưa, trừ khi worker đã release hoặc dùng bản copy độc lập.

## 18. Tài liệu chính thức

- [Java SE 17 – AsynchronousByteChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousByteChannel.html): quyền sử dụng ByteBuffer và completion.
- [Java SE 17 – AsynchronousSocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousSocketChannel.html): concurrent read/write, timeout và trạng thái buffer.
- [Java SE 17 – AsynchronousServerSocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousServerSocketChannel.html): accept bất đồng bộ.
- [Java SE 17 – CompletionHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/CompletionHandler.html): callback success/failure.
- [Java SE 17 – Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): get, cancel, happens-before.
- [Java SE 17 – CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): countDown/await synchronization.
- [Java SE 17 – ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): remaining, flip, slice và duplicate.

**Kết luận:** Trong thời gian asynchronous I/O chưa hoàn tất, ByteBuffer được **operation mượn độc quyền**. Chỉ xử lý lại nó sau successful completion và vẫn phải xét partial read/write. Timeout của `Future.get` không dừng I/O, còn timeout của chính async read/write có thể khiến trạng thái ByteBuffer không xác định. Không tái sử dụng buffer, backing array hoặc các view dùng chung bộ nhớ trước khi ownership trở về application.
