# Phân biệt sẵn sàng I/O của Selector với hoàn tất I/O bất đồng bộ

## 1. Mục tiêu và trực giác cốt lõi

Trong Java networking, hai cụm từ **I/O readiness** (sẵn sàng I/O) và **I/O completion** (hoàn tất I/O) thường cùng được gọi ngắn là “non-blocking” hoặc “bất đồng bộ”. Chúng giải quyết cùng vấn đề tránh giữ một thread bị chặn lâu trên mỗi kết nối, nhưng thông báo **hai loại sự kiện khác nhau**:

- **`Selector` — readiness:** thông báo một channel **có vẻ đã sẵn sàng** cho một loại thao tác (đọc, ghi, accept, connect). Sau thông báo, **chương trình vẫn phải tự gọi** `SocketChannel.read(...)`, `write(...)` hoặc `ServerSocketChannel.accept()` và kiểm tra kết quả thực tế.
- **`AsynchronousSocketChannel` — completion:** chương trình **khởi phát một thao tác** `read(...)`, `write(...)` hoặc `connect(...)`, rồi nhận **kết quả của chính thao tác ấy** qua `CompletionHandler` hoặc `Future` khi thao tác hoàn tất (thành công, EOF hoặc thất bại).

**Chốt ý:** *readiness = “bây giờ có thể thử I/O”; completion = “operation I/O được yêu cầu đã có kết quả”.* Cả hai đều **không tự ghép byte thành một thông điệp ứng dụng hoàn chỉnh**.

Bài này tập trung vào TCP/NIO Java 17+, `Selector`, `SelectionKey`, `SocketChannel`, `AsynchronousSocketChannel` và `ByteBuffer`. Các ví dụ chạy trên TCP loopback để không cần server Internet.

## 2. Cơ chế readiness: Selector, channel không chặn và SelectionKey

`java.nio.channels.Selector` quản lý nhiều `SelectableChannel` (ví dụ `ServerSocketChannel`, `SocketChannel`). Channel phải được chuyển sang non-blocking trước khi đăng ký:

~~~java
channel.configureBlocking(false);
SelectionKey key = channel.register(selector, SelectionKey.OP_READ);
~~~

*Đây là đoạn minh họa trong chương trình đã khởi tạo `channel`/`selector`; chưa phải chương trình chạy độc lập.*

Một `SelectionKey` có **interest set** (`interestOps()`) là các thao tác muốn theo dõi, và **ready set** (`readyOps()`) là các thao tác được phát hiện sẵn sàng. Các bit chính:

| Bit | Channel thường dùng | Thông báo gì? | Phải làm gì tiếp? |
| --- | --- | --- | --- |
| `OP_ACCEPT` | `ServerSocketChannel` | Có thể có kết nối đang đợi | Gọi `accept()` và xử lý kết quả (`null` có thể xảy ra ở non-blocking) |
| `OP_CONNECT` | `SocketChannel` | Connect không chặn có khả năng kết thúc hoặc có lỗi | Gọi `finishConnect()`, không tự đánh dấu đã kết nối |
| `OP_READ` | `SocketChannel` | Có thể đọc được, hoặc có EOF/lỗi | Gọi `read(ByteBuffer)`, kiểm tra `n > 0`/`0`/`-1` |
| `OP_WRITE` | `SocketChannel` | Có khả năng ghi, hoặc có trạng thái/lỗi liên quan | Gọi `write(ByteBuffer)`, kiểm tra số byte thực ghi |

`selector.select()` hoặc `selector.select(timeout)` hỏi hệ điều hành về readiness, cập nhật selected-key set và có thể chặn khi đợi. **Selector không tự copy bất kỳ byte nào vào ByteBuffer.** Để lấy payload, chính ứng dụng phải gọi `read`.

Độ tin cậy của ready set cũng có giới hạn: tài liệu `SelectionKey` xem nó là **gợi ý**, không cam kết thao tác sẽ chuyển được dữ liệu. Dữ liệu có thể bị đọc bởi luồng khác hoặc trạng thái channel đổi giữa lúc `select` và `read`.

### selectedKeys không phải keys

- `selector.keys()`: các key đã đăng ký, kể cả lúc chưa ready.
- `selector.selectedKeys()`: các key vừa được selector báo ready hoặc còn nằm trong selected-key set.
- Trong vòng lặp xử lý `selectedKeys()`, thường dùng `Iterator.remove()` **sau khi lấy key**, nếu không dễ xử lý lại sự kiện cũ.
- Trước khi xử lý key có thể đã bị đóng/hủy, kiểm tra `key.isValid()`.

**Đừng đăng ký `OP_WRITE` thường trực.** Socket thường writable suốt phần lớn thời gian; event loop có thể thức liên tục và tiêu tốn CPU. Chỉ bật `OP_WRITE` khi thật sự còn dữ liệu trong output queue; tắt bit ấy khi ghi xong.

## 3. Một sự kiện ready chưa có nghĩa đã hoàn tất read

Hãy xem các bước:

~~~text
1. socket.configureBlocking(false)
2. socket.register(selector, OP_READ)
3. selector.select()         -> trả về readable key
4. key.isReadable() == true  -> READINESS, chưa đọc dữ liệu
5. int n = socket.read(dst)  -> chính chương trình gọi I/O
6. n > 0 / n == 0 / n == -1  -> kết quả I/O thật sự
7. xử lý byte hoặc đợi lượt ready khác nếu chưa đủ message
~~~

`SocketChannel.read(ByteBuffer)` có thể trả:

- `n > 0`: đã ghi `n` byte vào buffer. Số byte này **không nhất thiết đủ** một message hoặc header đang cần.
- `n == 0`: lần đọc hiện tại không chuyển byte; có thể do buffer hết `remaining()` hoặc trạng thái readiness thay đổi. Đừng coi đây là EOF.
- `n == -1`: cuối luồng (EOF), tức peer đóng đầu ghi/connection theo trạng thái thích hợp; không tiếp tục chờ phần còn lại của frame dở.
- Ngoại lệ: lỗi I/O cần bắt và đóng/khôi phục connection theo chính sách.

`OP_READ` có thể được báo khi **EOF hoặc lỗi đang chờ**, không chỉ khi có byte payload. `OP_CONNECT` tương tự có thể báo dù kết quả connect là thất bại. Cần dùng `finishConnect()` để biết chắc.

`selector.select(timeout)` chỉ là **thời hạn một lượt đợi readiness**, không phải thời hạn hoàn tất operation hay thời gian tối đa của cả request. Một lần `select` có thể trả 0 do timeout, `wakeup()` hoặc điều kiện hợp lệ khác; cần quản deadline tổng theo thời gian đơn điệu và trạng thái kết nối, không suy ra “không có key = mọi I/O đều thất bại”.

## 4. Cơ chế completion: phát lệnh I/O trước, nhận kết quả sau

`AsynchronousSocketChannel` và `AsynchronousServerSocketChannel` là họ API asynchronous channel. `AsynchronousSocketChannel.read(...)` thực sự **khởi phát** một thao tác đọc trên channel, còn `CompletionHandler` thông báo kết quả sau khi operation này hoàn tất:

~~~java
channel.read(buffer, null, new CompletionHandler<Integer, Void>() {
    @Override
    public void completed(Integer count, Void attachment) {
        // Operation read đã kết thúc: count byte đã chuyển, 0 hoặc -1 (EOF).
    }
    @Override
    public void failed(Throwable error, Void attachment) {
        // Operation read thất bại: xử lý lỗi của chính thao tác này.
    }
});
~~~

*Đoạn minh họa, chưa phải chương trình độc lập vì biến `channel`/`buffer` và imports do ứng dụng cung cấp.*

Chúng ta cũng có biến thể **Future**:

~~~java
Future<Integer> operation = channel.read(buffer);
// Chưa thể dùng buffer như thể read đã xong.
int n = operation.get(); // Có thể chặn thread hiện tại khi chờ.
~~~

*Đây là đoạn minh họa. Ở ví dụ chạy đầy đủ, `connect(...)` trả `Future<Void>` và `read(...)` dùng `CompletionHandler`.*

Những điều cần hiểu:

1. Lời gọi `read(buffer, ..., handler)` **khởi phát** operation; việc nó trả về không chứng minh operation xong.
2. Callback `completed(n, ...)` nghĩa là **một operation read đã kết thúc**, không phải “đủ cả message nghiệp vụ”. Nếu buffer còn `remaining()`, cần khởi phát **read mới**.
3. Callback `failed(Throwable, ...)` nghĩa là operation thất bại, cần xử lý/đóng/hủy phù hợp; không cho phép parser xử lý một buffer dở như message hợp lệ.
4. `Future.get()` có thể **chặn**. Nếu gọi `get` ngay sau mỗi lần khởi phát và không làm việc gì khác, chương trình có thể trở thành mô hình chờ tuần tự dù dùng asynchronous API.
5. **Không có đảm bảo callback luôn chạy trên thread mới** hoặc luôn chạy muộn hơn lời gọi khởi phát; việc dispatch phụ thuộc runtime và asynchronous channel group. Callback nên ngắn, thread-safe, không block tác vụ nặng.
6. Sử dụng asynchronous channel **không đồng nghĩa** triển khai trên mọi hệ điều hành phải dùng cơ chế completion thuần ở mức kernel; quan trọng là ngữ nghĩa API và hệ quả cho code ứng dụng.

## 5. So sánh hai timeline

### Readiness / reactor-style

~~~text
Application                     Selector / OS                  SocketChannel
    |                                  |                            |
    |-- register(OP_READ) ------------>|                            |
    |-- select() --------------------->| đợi khả năng đọc          |
    |<------------- readable key ------|                            |
    |-- key.isReadable() = true                                     |
    |-- read(ByteBuffer) ------------------------------------------>|
    |<-------------------------------------- n / 0 / -1 -------------|
    |-- parse số byte thực, giữ frame state, đợi ready tiếp          |
~~~

### Completion-driven / async API

~~~text
Application                       Asynchronous channel / runtime
    |                                      |
    |-- read(buffer, handler) ------------>| khởi phát read
    |<-- return sau khi khởi phát ---------| có thể chưa xong
    |               làm việc khác ...
    |<-- completed(n) hoặc failed(err) ----| operation đã có kết quả
    |-- xử lý n byte hoặc phát read mới nếu frame còn thiếu
~~~

Sơ đồ mô tả **quan hệ logic**, không quy định thread nào thực thi callback hay thứ tự tuyệt đối khi operation hoàn tất rất nhanh.

### Một bảng đối chiếu

| Khía cạnh | Selector + non-blocking SocketChannel | AsynchronousSocketChannel |
| --- | --- | --- |
| Loại thông báo | Sẵn sàng thử I/O | Kết quả của I/O đã khởi phát |
| Ai thực sự thực hiện lời gọi đọc/ghi? | Ứng dụng trong event loop | Ứng dụng khởi phát operation; runtime xử lý rồi báo kết quả |
| API | `Selector`, `SelectionKey`, `SocketChannel` | `AsynchronousSocketChannel`, `Future`, `CompletionHandler` |
| Cấu hình | `configureBlocking(false)` trước đăng ký | Dùng API asynchronous, không `register(Selector)` như `SocketChannel` |
| Nơi biết kết quả byte | `read()/write()` ở call site | `completed(Integer n)` hoặc `Future.get()` |
| Xử lý message chưa đủ | Giữ parser state, đợi readiness khác | Phát operation tiếp theo từ completion |
| Độ phức tạp | State machine theo key/event loop | State và thứ tự callback/Future |
| EOF | `read() == -1` | Completion read trả `-1` |
| Timeout | Đợi ready hoặc application deadline | Operation timeout / Future wait timeout / application deadline |
| Thread | Thường một/vài event loop | Nhóm thread completion/provider tùy triển khai |
| Dữ liệu | TCP byte stream, không có message boundary | TCP byte stream, không có message boundary |

## 6. Ví dụ Java 17+: Selector chỉ báo ready, không tự đọc dữ liệu

Chương trình tạo TCP server/client trên loopback trong cùng JVM. `SocketChannel` nhận được chuyển sang non-blocking và đăng ký `OP_READ`. Bên gửi ghi `"PING"`. Sau một readable event, **ứng dụng gọi `receiver.read(incoming)`** và chỉ khi buffer đủ 4 byte mới giải mã/in.

Tạo file `SelectorReadinessDemo.java`:

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

public class SelectorReadinessDemo {
    public static void main(String[] args) throws IOException {
        try (ServerSocketChannel listener = ServerSocketChannel.open()) {
            listener.bind(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0));
            try (SocketChannel sender = SocketChannel.open(listener.getLocalAddress());
                 SocketChannel receiver = listener.accept();
                 Selector selector = Selector.open()) {
                receiver.configureBlocking(false);
                receiver.register(selector, SelectionKey.OP_READ);

                ByteBuffer outgoing = StandardCharsets.US_ASCII.encode("PING");
                while (outgoing.hasRemaining()) {
                    sender.write(outgoing);
                }

                ByteBuffer incoming = ByteBuffer.allocate(4);
                boolean sawReadableKey = false;
                long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
                while (incoming.hasRemaining() && System.nanoTime() < deadline) {
                    selector.select(1_000);
                    Iterator<SelectionKey> it = selector.selectedKeys().iterator();
                    while (it.hasNext()) {
                        SelectionKey key = it.next();
                        it.remove();
                        if (key.isValid() && key.isReadable()) {
                            sawReadableKey = true;
                            int n = receiver.read(incoming);
                            if (n < 0) {
                                throw new EOFException("peer closed before four bytes");
                            }
                        }
                    }
                }

                if (incoming.hasRemaining()) {
                    throw new IOException("incomplete payload");
                }
                incoming.flip();
                System.out.println("readiness observed: " + sawReadableKey);
                System.out.println("buffered bytes: " + incoming.remaining());
                System.out.println("payload: "
                        + StandardCharsets.US_ASCII.decode(incoming));
            }
        }
    }
}
~~~

Lệnh chạy:

~~~bash
javac SelectorReadinessDemo.java
java SelectorReadinessDemo
~~~

Kết quả trên loopback:

~~~text
readiness observed: true
buffered bytes: 4
payload: PING
~~~

Giải thích chi tiết:

- `ServerSocketChannel` chặn ở `accept()` chỉ để tạo **fixture kết nối trong cùng chương trình**. Phần đang minh họa Selector là `receiver` có `configureBlocking(false)` và `register(OP_READ)`.
- `selector.select(1_000)` chỉ cập nhật selected-key set. Byte thực được đưa vào `incoming` trong dòng `receiver.read(incoming)`, **không phải** trong `select`.
- `Iterator.remove()` lấy key ra khỏi selected-key set khi đã xử lý.
- Vì TCP có thể chia dữ liệu, chương trình lặp qua nhiều sự kiện read nếu `incoming` chưa đủ 4 byte.
- Nếu `read == -1` trước khi đủ 4 byte, đó là EOF trước payload trọn vẹn. Nếu trễ quá deadline 5 giây, demo báo lỗi thay vì đợi vô hạn.
- `incoming.flip()` chuyển buffer từ ghi vào sang đọc ra để `US_ASCII.decode` chỉ thấy 4 byte vừa nhận.

Ví dụ cố ý dùng độ dài cố định 4 byte để có stdout dễ đối chiếu, **không** thay thế bộ giải mã frame dùng header length của hệ thống thật.

## 7. Ví dụ Java 17+: AsynchronousSocketChannel báo completion

Ở ví dụ này, phía client dùng `AsynchronousSocketChannel`. Nó khởi phát `connect(...)` và nhận `Future<Void>`, sau đó khởi phát `read(...)` với `CompletionHandler`. Server phía peer gửi `"PONG"`. Handler được gọi khi read operation có kết quả, và nếu buffer còn trống thì **đăng ký một read mới**. `CountDownLatch` chỉ giúp chương trình demo đợi đủ payload để in stdout.

Tạo file `AsyncCompletionDemo.java`:

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousSocketChannel;
import java.nio.channels.CompletionHandler;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class AsyncCompletionDemo {
    public static void main(String[] args) throws Exception {
        try (ServerSocketChannel listener = ServerSocketChannel.open()) {
            listener.bind(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0));
            try (AsynchronousSocketChannel client = AsynchronousSocketChannel.open()) {
                Future<Void> connecting = client.connect(listener.getLocalAddress());
                try (SocketChannel peer = listener.accept()) {
                    connecting.get(5, TimeUnit.SECONDS);

                    ByteBuffer incoming = ByteBuffer.allocate(4);
                    CountDownLatch done = new CountDownLatch(1);
                    AtomicReference<Throwable> failure = new AtomicReference<>();

                    CompletionHandler<Integer, Void> handler =
                            new CompletionHandler<Integer, Void>() {
                        @Override
                        public void completed(Integer n, Void attachment) {
                            if (n < 0) {
                                failure.set(new EOFException("incomplete payload"));
                                done.countDown();
                            } else if (incoming.hasRemaining()) {
                                client.read(incoming, null, this);
                            } else {
                                done.countDown();
                            }
                        }

                        @Override
                        public void failed(Throwable error, Void attachment) {
                            failure.set(error);
                            done.countDown();
                        }
                    };

                    client.read(incoming, null, handler);

                    ByteBuffer outgoing = StandardCharsets.US_ASCII.encode("PONG");
                    while (outgoing.hasRemaining()) {
                        peer.write(outgoing);
                    }

                    if (!done.await(5, TimeUnit.SECONDS)) {
                        throw new IOException("read completion timeout");
                    }
                    if (failure.get() != null) {
                        throw new IOException("read failed", failure.get());
                    }

                    incoming.flip();
                    System.out.println("completion observed: true");
                    System.out.println("buffered bytes: " + incoming.remaining());
                    System.out.println("payload: "
                            + StandardCharsets.US_ASCII.decode(incoming));
                }
            }
        }
    }
}
~~~

Lệnh chạy:

~~~bash
javac AsyncCompletionDemo.java
java AsyncCompletionDemo
~~~

Kết quả trên loopback:

~~~text
completion observed: true
buffered bytes: 4
payload: PONG
~~~

Giải thích:

1. `client.connect(listener.getLocalAddress())` **khởi phát connect** và trả `Future<Void>`. `connecting.get(5, SECONDS)` đợi việc connect hoàn tất; `get` có thể chặn thread hiện tại. Trong demo, việc đợi được dùng để đảm bảo kết nối đã sẵn sàng trước khi đặt read.
2. `client.read(incoming, null, handler)` **khởi phát read**; không có `selector.select()` hoặc key readable.
3. `completed(Integer n, ...)` là kết quả **của lần read vừa khởi phát**. `n == -1` báo EOF. Nếu `incoming.hasRemaining()` còn true, chưa đủ 4 byte; handler khởi phát một read tiếp theo **sau khi read trước hoàn tất**.
4. `failed(Throwable, ...)` báo lỗi I/O. `AtomicReference` lưu lỗi để thread đang chờ biết và không giải mã dữ liệu chưa đủ.
5. `done.await(...)` chặn thread main chỉ để demo biết khi nào đã nhận đủ 4 byte, không phải thành phần bắt buộc khi triển khai callback server.
6. Chỉ sau khi latch báo hoàn tất, chương trình mới `incoming.flip()` và decode `PONG`.
7. Một read callback có thể nhận ít byte hơn độ dài message. **Operation hoàn tất ≠ message hoàn tất** — đây là chi tiết quan trọng nhất khi thiết kế parser trên async channel.

Các ví dụ chạy trên loopback và có giả định môi trường mạng hoạt động bình thường. Ứng dụng thật cần xử lý partial reads, EOF, giới hạn payload, timeout, shutdown và backpressure trên nhiều client.

## 8. OP_ACCEPT, OP_CONNECT, OP_READ, OP_WRITE: ánh xạ sang async

| Hoạt động | Selector (readiness) | Asynchronous channel (completion) |
| --- | --- | --- |
| Nhận client mới | Đợi `OP_ACCEPT`, gọi `ServerSocketChannel.accept()` | Khởi phát `AsynchronousServerSocketChannel.accept(...)`, nhận channel đã accept qua handler/Future |
| Kết nối client | `SocketChannel.connect`, nếu pending thì đợi `OP_CONNECT` rồi `finishConnect()` | `AsynchronousSocketChannel.connect(...)` và đợi Future/handler báo kết quả |
| Đọc payload | Đợi `OP_READ`, tự gọi `SocketChannel.read(dst)` | Khởi phát `AsynchronousSocketChannel.read(dst, ...)` và nhận `completed(n)`/`failed` |
| Ghi payload | Tự `SocketChannel.write(src)`; nếu còn byte, bật `OP_WRITE` | Khởi phát `AsynchronousSocketChannel.write(src, ...)`, hoàn tất operation rồi gửi tiếp phần còn |
| EOF | `read(dst) == -1` | Read completion trả `-1` |
| Lỗi | Ngoại lệ khi read/write/finishConnect | `CompletionHandler.failed(Throwable)` hoặc Future exception |

Với readiness, `OP_CONNECT` chỉ gợi ý có thể gọi `finishConnect()`; nó không cam kết connect thành công. `OP_ACCEPT` cũng không tự đặt client channel vào `SelectionKey`. Với asynchronous server, mỗi `accept(...)` là **một operation**. Nếu server cần nhận nhiều client, sau khi accept hoàn tất nó phải khởi phát accept tiếp theo theo thiết kế.

## 9. ByteBuffer, partial read/write và quyền sở hữu

Dù dùng readiness hay completion, phải hiểu `ByteBuffer`:

| Thuộc tính/phương thức | Ý nghĩa |
| --- | --- |
| `capacity()` | Sức chứa cố định |
| `position()` | Vị trí byte kế tiếp |
| `limit()` | Ranh giới thao tác |
| `remaining()`/`hasRemaining()` | Số byte hoặc việc còn byte chưa xử lý |
| `flip()` | Chuyển dữ liệu vừa ghi vào buffer thành vùng có thể đọc ra |
| `clear()` | Reset position/limit, **không xóa nội dung mảng** |
| `compact()` | Dồn byte chưa đọc để tiếp tục tích lũy một frame còn thiếu |

Một lần `write(ByteBuffer)` có thể ghi ít hơn số byte còn lại: cần giữ buffer đến khi hết `remaining()`. Một lần `read(ByteBuffer)` có thể nhận ít hơn message: cần parser state thay vì mặc định một callback = một frame.

Trong asynchronous API, **không đọc/sửa `ByteBuffer` từ thread khác khi operation vẫn pending**. Buffer không thread-safe; position/limit có thể được runtime thay đổi trong quá trình I/O. Nếu trước khi read trước hoàn tất mà lại đăng ký read mới trên cùng `AsynchronousSocketChannel`, có thể ném `ReadPendingException`; tương tự `WritePendingException` khi ghi trùng pending operation. Nên cho mỗi connection có một read pending tối đa theo API, rồi phát read tiếp trong completion.

**Không nên xử lý CPU-heavy hoặc blocking database call ngay trong Selector event loop hay thread callback async.** Hãy dùng executor có giới hạn, chuyển ownership message/session rõ ràng và điều phối backpressure để không tạo hàng đợi byte vô hạn.

## 10. Cả hai mô hình đều phải tự nhận biết ranh giới thông điệp TCP

TCP không chuyển từng “message” nguyên vẹn theo mỗi lần `read`. Ví dụ ứng dụng định dạng frame bằng header length 4 byte big-endian:

~~~text
[4 byte length][length byte payload]
00 00 00 05 48 45 4C 4C 4F
  header 5        "HELLO"
~~~

Trong cả hai thiết kế:

1. Tích lũy đủ **4 byte header** (qua nhiều read nếu cần).
2. `flip()` header, đọc `int length`.
3. Kiểm tra `length >= 0 && length <= MAX_PAYLOAD_BYTES` **trước khi cấp phát body**; từ chối length độc hại.
4. Đọc đủ `length` byte body; nếu gặp EOF/timeout khi còn thiếu thì không trả message dở cho nghiệp vụ.
5. Chỉ xử lý payload đã hoàn chỉnh; giữ state cho message kế tiếp.

Điểm khác biệt nằm ở **cách đợi và tiếp tục**:

- Selector: đợi `OP_READ`, **gọi `read`**, nếu chưa đủ thì giữ buffer/parser state và đợi readiness tiếp.
- Async: khởi phát `read`, **đợi callback/Future completion**, nếu chưa đủ thì khởi phát read **mới** và giữ buffer/parser state.

Với ghi dữ liệu cũng tương tự: selector giữ output queue và chỉ bật `OP_WRITE` khi còn byte; async giữ buffer đến completion và đặt write kế tiếp nếu vẫn còn `remaining()`.

## 11. Timeout, cancel và vòng đời kết nối

| Công cụ | Thời gian/việc thực sự giới hạn | Không được suy ra |
| --- | --- | --- |
| `selector.select(1000)` | Một lượt chờ readiness | Không phải deadline của toàn message |
| Application deadline dựa trên `System.nanoTime()` | Tổng thời gian tối đa do ứng dụng tự áp | Không tự động hủy mọi I/O nếu code không xử lý |
| `future.get(5, SECONDS)` | Thời gian thread caller **chờ kết quả** | Không có nghĩa operation nền đã bị hủy khi timeout |
| `asyncChannel.read(dst, timeout, unit, attachment, handler)` | Timeout của read operation tương ứng | Không phải thời gian tổng mọi read của một frame |
| `selector.wakeup()` | Đánh thức thread đang `select` | Không phải I/O completion hoặc cancel |

`Future.get(timeout)` có thể ném `TimeoutException` trong khi operation vẫn chạy; cần chiến lược `cancel`/close/connection state riêng. Với timeout của asynchronous read/write, tài liệu JDK lưu ý một số triển khai **không thể bảo đảm** buffer không tiếp tục bị ảnh hưởng sau timeout; không được tái sử dụng buffer/channel theo giả định pending operation luôn đã dừng an toàn.

Khi kết nối bị đóng, các key/callback có thể đã được xếp lịch; kiểm tra trạng thái connection, key validity và handle lỗi `AsynchronousCloseException`/`ClosedChannelException`. Không để callback của một session đã shutdown đụng vào buffer hoặc nghiệp vụ session mới.

## 12. Chọn mô hình theo workload, không theo tên gọi “async”

**Selector** phù hợp khi muốn event loop theo readiness, tự quản state machine của nhiều channel, điều phối `interestOps` và xử lý partial I/O. Mô hình có thể rất hiệu quả nếu mỗi event được xử lý ngắn; nhưng nếu callback xử lý event quá lâu thì các connection khác do cùng loop quản lý sẽ bị trễ.

**AsynchronousSocketChannel** phù hợp khi muốn code được kích hoạt theo **kết quả operation**, phối hợp `CompletionHandler` hoặc `Future`, và chuyển trạng thái sau mỗi completion. Callback có thể chạy trên thread pool của asynchronous channel group hoặc cơ chế runtime khác. Không nên chiếm callback thread bằng công việc chặn lâu.

Không thể kết luận **mô hình nào nhanh hơn trên mọi OS/JDK** chỉ bằng tên gọi. Hãy đo latency, throughput, số connection idle, CPU, GC, allocation, số buffer đang giữ và tính phức tạp bảo trì. Cả hai đều cần giới hạn dữ liệu, số kết nối, output queue, đồng bộ hóa và xử lý EOF.

## 13. Những lỗi dễ mắc nhất

| Khẳng định/lỗi | Sai ở đâu? | Cách sửa |
| --- | --- | --- |
| “`key.isReadable()` nghĩa là bytes đã đến buffer.” | `Selector` không thực hiện `read` | Gọi `SocketChannel.read` và kiểm tra `n` |
| “Có `OP_READ` là chắc chắn có payload.” | EOF/lỗi cũng có thể kích hoạt readiness | Xử lý `-1` và exception |
| “Có `OP_CONNECT` là connect xong.” | Connect có thể còn cần hoàn tất hoặc thất bại | Gọi `finishConnect()` |
| “`OP_ACCEPT` tự mang client channel.” | Chỉ báo readiness | Gọi `accept()` |
| “`read == 0` là peer đóng.” | Zero không phải EOF | EOF là `-1` |
| “`completed(2)` nghĩa là message 5 byte đã đủ.” | Hoàn tất **một read operation** | Phát read mới nếu buffer thiếu |
| “Future là luôn non-blocking, kể cả `get()`.” | `get()` có thể chặn caller | Dùng callback hoặc phối hợp chờ hợp lý |
| “Callback luôn chạy thread được tạo riêng.” | Không có cam kết như vậy | Thread-safe và không block callback |
| “Có thể `clear()` buffer khi async read pending.” | Runtime có thể còn đang dùng buffer | Đợi completion/cancel đúng chính sách |
| “Bắt đầu hai read cùng lúc trên một async socket.” | Có thể ném `ReadPendingException` | Đọc tiếp sau completion |
| “Bật `OP_WRITE` mãi mãi.” | Dễ tạo busy loop | Chỉ bật khi còn output |
| “`select(timeout)` = I/O operation timeout.” | Nó chỉ đợi readiness | Deadline của frame/connection riêng |
| “`get(timeout)` tự hủy pending operation.” | Chỉ giới hạn chờ thread | Cancel/close theo chính sách riêng |
| “Callback xong là TCP message xong.” | TCP là byte stream | Framing và parser state |

## 14. Tự kiểm tra và bài tập

**Câu 1.** `key.isReadable() == true`, ngay sau đó `read(dst)` trả 0. Có phải ứng dụng đã nhận một message rỗng?

Không. Readiness chỉ là **gợi ý**, còn `read == 0` nói rằng lời gọi hiện tại chưa chuyển byte. Giữ state và đợi readiness sau (trừ khi giao thức có frame rỗng tường minh).

**Câu 2.** Callback async `completed(2)` được gọi nhưng parser cần 5 byte. Operation đó hoàn tất hay chưa?

**Operation đã hoàn tất** với 2 byte, nhưng **message chưa đủ**. Phải khởi phát read kế tiếp sau callback, không coi 2 byte đã là một frame hợp lệ.

**Câu 3.** `SocketChannel.connect` ở non-blocking trả false, sau đó có `OP_CONNECT`. Tại sao vẫn phải `finishConnect()`?

Readiness chỉ nói kết nối **có khả năng hoàn tất hoặc có lỗi**. `finishConnect()` thực hiện bước hoàn tất và phát hiện thất bại; không được đánh dấu connected chỉ từ key.

**Câu 4.** `Future<Integer> f = async.read(dst); f.get(1, SECONDS)` ném `TimeoutException`. Được phép `clear()` buffer và dùng ngay cho request khác?

Không thể mặc định. Thread đợi Future đã hết giờ, nhưng operation nền có thể vẫn pending. Cần xử lý cancel/close/ownership đúng API trước khi tái sử dụng buffer.

**Câu 5.** Vì sao `OP_WRITE` có thể khiến một event loop tiêu thụ CPU dù không có dữ liệu gửi?

Socket rất thường sẵn sàng ghi, nên readiness cho `OP_WRITE` có thể liên tục xuất hiện. Chỉ bật bit này khi output queue còn byte; tắt khi hết.

**Bài thực hành:** 
- Chạy hai file Java, đánh dấu dòng `selector.select`/`key.isReadable` **vs** dòng `receiver.read`; so với dòng `client.read(..., handler)`/`completed` của ví dụ async.
- Đổi `"PING"` thành `"HELLO"`, tăng buffer lên 5 và giữ nguyên logic đọc đủ; sau đó thử nhận từng phần bằng cách chia sender thành hai lượt ghi.
- Đổi `"PONG"` thành `"HELLO"` trong async demo, tăng buffer lên 5. Xác minh handler xử lý nhiều completion nếu cần.
- Phác thảo parser length-prefix giới hạn `MAX_PAYLOAD_BYTES = 1024` cho cả hai mô hình; chỉ cấp phát payload sau kiểm tra header.
- Với server có hàng nghìn kết nối idle, viết sơ đồ ownership buffer/session, backpressure và shutdown cho mỗi mô hình rồi benchmark trong môi trường thực.

## Tài liệu tham khảo chính thức (Java SE 21)

- [`Selector`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/Selector.html) — selected keys, selection operations và readiness.
- [`SelectionKey`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SelectionKey.html) — `interestOps`, `readyOps`, `OP_ACCEPT`, `OP_CONNECT`, `OP_READ`, `OP_WRITE`.
- [`SocketChannel`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SocketChannel.html) — non-blocking `connect`/`finishConnect`/`read`/`write`.
- [`ServerSocketChannel`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/ServerSocketChannel.html) — blocking/non-blocking accept.
- [`AsynchronousSocketChannel`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/AsynchronousSocketChannel.html) — Future, handler, pending read/write, timeout và buffer safety.
- [`AsynchronousServerSocketChannel`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/AsynchronousServerSocketChannel.html) — asynchronous accept.
- [`CompletionHandler`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/CompletionHandler.html) — `completed`/`failed`.
- [`ByteBuffer`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html) — position, limit, flip, clear, compact.
