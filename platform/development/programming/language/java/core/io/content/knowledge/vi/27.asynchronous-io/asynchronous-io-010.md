# Lựa chọn blocking, selector hoặc API bất đồng bộ theo bài toán

## 1. Bài toán chọn mô hình I/O

Java cho phép triển khai cùng một thao tác đọc/ghi theo nhiều cách. Với một TCP client gửi `PING` và chờ `PONG`, ta có thể:

- Gọi `SocketChannel.read()`/`write()` trong **blocking mode**: luồng có thể đợi tại lời gọi.
- Dùng `SocketChannel.configureBlocking(false)` kết hợp **`Selector`**: luồng event loop đợi tín hiệu *readiness*, rồi chủ động gọi read/write.
- Dùng **`AsynchronousSocketChannel`**: khởi tạo thao tác, lấy kết quả qua `Future` hoặc `CompletionHandler` (*completion*), không nhất thiết để luồng gọi đợi.

Điểm khác nhau không nằm ở “API nào hiện đại hơn”, mà là **ai giữ trạng thái I/O trong khi chưa hoàn thành** và **luồng nào chịu chi phí chờ**.

~~~text
Blocking:
  thread -> connect -> write -> read[đợi] -> xử lý -> đóng

Selector / readiness:
  event loop -> select -> channel sẵn sàng -> thử read/write
             -> còn byte chưa xử lý? lưu state -> select lần sau

Asynchronous / completion:
  caller -> phát hành read/write -> tiếp tục việc khác
                                      |
                     Future hoặc CompletionHandler báo kết quả
~~~

**Chọn theo workload thực tế**: số kết nối đang mở, tỉ lệ chờ/CPU, throughput, tail latency, độ phức tạp cho phép, yêu cầu timeout/cancel và giới hạn RAM/file descriptor. Blocking, selector và async đều có thể đúng trong những hoàn cảnh khác nhau.

## 2. Ba khái niệm phải phân biệt

### 2.1. Blocking: lời gọi có thể chờ

~~~java
try (SocketChannel socket = SocketChannel.open(remote)) {
    ByteBuffer dst = ByteBuffer.allocate(1024);
    int n = socket.read(dst);
    // Luồng gọi có thể đợi ở read().
}
~~~

Đây là **mảnh minh họa**, cần `SocketChannel`, `ByteBuffer` và một `remote` hợp lệ; phải khai báo hoặc xử lý `IOException`. `SocketChannel.open(remote)` dùng kết nối TCP blocking theo mặc định.

Mã blocking có luồng điều khiển tuyến tính, dễ theo dõi bằng debugger và dễ quản lý tài nguyên bằng `try-with-resources`. Khi ứng dụng có nhiều platform threads bị chặn lâu trên mạng, chi phí stack, scheduler và giới hạn tài nguyên có thể quan trọng.

Blocking **không bảo đảm một lần `read` trả đủ buffer**. Channel có thể nhận được ít byte hơn ứng dụng cần; `write` cũng có thể tiêu thụ chưa hết `remaining()`. Cần vòng lặp theo giao thức ở mọi mô hình.

### 2.2. Selector: readiness, không phải completion

~~~java
socket.configureBlocking(false);
SelectionKey key = socket.register(selector, SelectionKey.OP_READ);
selector.select();
~~~

Đây là **mảnh minh họa**: `socket` phải được khởi tạo, `selector` đã mở. `SelectionKey.OP_READ` nghĩa là chương trình quan tâm đến lúc socket **có thể thử đọc**.

Khi `key.isReadable()`, ứng dụng gọi `socket.read(buffer)`. Lệnh có thể trả:

- `n > 0`: đã nhận `n` byte;
- `n == 0`: chưa byte nào được chuyển trong lần này;
- `n == -1`: cuối luồng (EOF) ở hướng đọc.

Readiness không có nghĩa toàn bộ thông điệp TCP đã đến. Bởi vì một event loop có thể quản lý nhiều socket, nó thường phải giữ input buffer, parser state và output queue **riêng cho từng kết nối**.

### 2.3. AsynchronousChannel: completion của một thao tác

~~~java
try (AsynchronousSocketChannel socket =
        AsynchronousSocketChannel.open()) {
    Future<Void> future = socket.connect(remote);
    future.get(); // Caller vẫn BLOCK nếu đợi tại get().
}
~~~

Đây là **mảnh minh họa**; cần `AsynchronousSocketChannel`, `Future`, một `remote` hợp lệ và xử lý checked exceptions.

API async có hai lối:

- **`Future`**: thao tác khởi động và Future dùng để hỏi/đợi kết quả. Gọi `get()` ngay sau mỗi lệnh có thể biến caller thành luồng chờ như mã tuần tự.
- **`CompletionHandler`**: chuyển callback cho API và nhận `completed` hoặc `failed` khi thao tác hoàn tất. Phải quản lý lifetime của dữ liệu, error flow và callback thread.

“Async” không có nghĩa không sử dụng luồng: implementation có thể dùng thread pool, completion port hoặc cơ chế nền tảng khác. Nó cũng không đồng nghĩa zero-copy, tự có transaction hoặc tự giải quyết partial I/O.

## 3. Bảng so sánh tổng quan

| Tiêu chí | Blocking I/O | Selector non-blocking | Asynchronous API |
| --- | --- | --- | --- |
| Ngữ nghĩa | Caller có thể đợi cho tới khi thao tác tiến triển/hoàn tất theo hợp đồng. | Selector báo channel ready, caller tự thử read/write. | Future/callback báo thao tác cụ thể đã hoàn tất/thất bại. |
| Mã nguồn | Tuyến tính, ít state machine. | Event loop và state cho mỗi connection. | Continuation, callback/Future và state in-flight. |
| Concurrency | Thường dùng nhiều platform threads hoặc pool. | Một event loop có thể theo dõi nhiều selectable channels. | Provider/pool xử lý nhiều operations; số thread phụ thuộc implementation. |
| Khả năng xử lý file | `Files`/`FileChannel` rất thuận tiện. | `FileChannel` không thể đăng ký Selector như socket. | `AsynchronousFileChannel` hỗ trợ positional file I/O. |
| Partial read/write | Có. | Có. | Có, cả khi một Future/completion đã trả kết quả. |
| Timeout | Cấu hình và deadline theo API/protocol. | Phải giữ deadline trong event loop; `select(timeout)` chỉ là thời gian chờ readiness. | `Future.get(timeout)`/handler và chính sách cancel/close. |
| Backpressure | Giới hạn worker/queue, chờ write. | Quản lý `OP_READ`/`OP_WRITE` và per-connection queues. | Giới hạn số operation in-flight và lifetime buffer. |
| Chi phí triển khai | Thường thấp nhất. | Phải tự giải quyết state, fairness, readiness và cleanup. | Phải xử lý callback, ownership, cancellation và thứ tự completion. |
| Phù hợp | I/O đơn giản, ít/vừa kết nối, công cụ batch. | Nhiều socket đồng thời, đa số idle, event-driven services. | Pipeline dựa trên completion, file offset và callbacks/Future. |

Không diễn giải bảng này như kết quả benchmark. Hiệu năng đo được còn phụ thuộc hệ điều hành, cấu hình provider, payload, server behavior, GC, TLS, số kết nối và thời gian xử lý ứng dụng.

## 4. Khi nào blocking là lựa chọn hợp lý?

Blocking phù hợp khi:

1. Giao tiếp chỉ vài kết nối hoặc số kết nối đang chờ nằm trong khả năng thread pool hiện tại.
2. Logic request/response cần mã tuyến tính, dễ đọc và dễ xử lý ngoại lệ.
3. Ứng dụng CLI, batch, dịch vụ nhỏ, đọc/ghi tệp cục bộ có khối lượng vừa phải.
4. Thư viện phụ trợ chủ yếu blocking; chưa có yêu cầu số lượng kết nối đồng thời cực lớn.
5. Cách hiện tại đạt throughput/latency, chưa có profiling chứng minh thread waiting là nút thắt.

### 4.1. Gửi và nhận đầy đủ với blocking SocketChannel

~~~java
static void writeFully(SocketChannel channel, ByteBuffer source)
        throws IOException {
    while (source.hasRemaining()) {
        int n = channel.write(source);
        if (n == 0) {
            throw new IOException("Blocking write không tiến triển");
        }
    }
}

static void readFully(SocketChannel channel, ByteBuffer target)
        throws IOException {
    while (target.hasRemaining()) {
        int n = channel.read(target);
        if (n == -1) {
            throw new EOFException("EOF trước khi đủ dữ liệu");
        }
        if (n == 0) {
            throw new IOException("Blocking read không tiến triển");
        }
    }
}
~~~

Hai phương thức trên là **mảnh mã cần đặt trong một lớp**, với import `IOException`, `EOFException`, `ByteBuffer` và `SocketChannel`. Chúng có chủ đích dành cho *blocking channel* với buffer có chỗ và kỳ vọng tiến triển. Đừng dùng nguyên xi cho socket non-blocking: giá trị `0` khi ấy có thể hoàn toàn bình thường.

`readFully` chỉ nên dùng nếu giao thức thực sự đòi hỏi **đúng một số byte**. Đọc một tệp đến EOF hoặc đọc văn bản phân cách dấu xuống dòng có quy trình khác.

### 4.2. Virtual threads có thay đổi quyết định không?

Từ **Java 21**, virtual threads là một lựa chọn quan trọng cho lượng lớn tác vụ *blocking-style*. Với Java 17, virtual threads chưa có ở dạng tính năng chuẩn, nên mã ví dụ trong bài chỉ dùng những API thuộc Java 17.

Virtual threads không thay thế nhu cầu giới hạn số socket, downstream database connections, memory buffers hay deadline. Nếu dự án được phép nâng lên Java 21+, hãy đưa virtual threads vào phương án so sánh bên cạnh selector và async.

## 5. Khi nào chọn Selector?

Chọn `Selector` khi:

- Có hàng nghìn kết nối TCP mở đồng thời, phần lớn ở trạng thái chờ dữ liệu.
- Muốn **một hoặc vài I/O event-loop threads** quản lý nhiều socket.
- Mỗi lượt xử lý event ngắn, có khả năng thiết kế parser theo state machine.
- Muốn kiểm soát readiness, outbound queues, fairness và backpressure ở cấp kết nối.
- Hệ thống đã theo kiến trúc non-blocking hoặc đang dùng framework dựa trên selector.

Mẫu khung event loop:

~~~java
while (running) {
    selector.select();
    Iterator<SelectionKey> iterator =
            selector.selectedKeys().iterator();

    while (iterator.hasNext()) {
        SelectionKey key = iterator.next();
        iterator.remove(); // Bắt buộc để không giữ selected key cũ.

        if (!key.isValid()) {
            continue;
        }
        if (key.isAcceptable()) {
            // ServerSocketChannel.accept(): có thể trả null.
        } else if (key.isConnectable()) {
            // SocketChannel.finishConnect(): kết thúc pending connect.
        } else if (key.isReadable()) {
            // SocketChannel.read(): >0, 0 hoặc -1.
        } else if (key.isWritable()) {
            // SocketChannel.write(): có thể ghi một phần hoặc 0.
        }
    }
}
~~~

Đây là **pseudocode event loop**, chưa chứa khai báo `running`, `selector`, per-connection state, try/catch và cleanup.

Nguyên tắc quan trọng:

- Chỉ channel ở **non-blocking mode** mới đăng ký với Selector. `SocketChannel` từ `ServerSocketChannel.accept()` ban đầu là blocking; phải `configureBlocking(false)` trước khi đăng ký.
- Một selector chỉ báo *ready*. `read/write` vẫn có thể chuyển ít dữ liệu. Trạng thái position/limit của mỗi `ByteBuffer` phải được giữ giữa nhiều lượt.
- `SelectionKey.attachment()` có thể gắn input parser, output queue và connection metadata.
- `OP_WRITE` không nên bật liên tục khi không có byte chờ gửi; điều đó có thể làm event loop bị đánh thức dày đặc.
- Đừng chạy xử lý CPU-heavy, truy vấn database blocking hoặc sleep trong event loop; một callback chậm sẽ trì hoãn mọi socket trên cùng luồng.
- `selector.close()` không tương đương đóng mọi peer socket; ứng dụng phải đóng những channel mình sở hữu.

Đặc biệt, **`FileChannel` không phải `SelectableChannel`**. Không sử dụng Selector để “làm FileChannel bất đồng bộ”; hãy dùng file API thích hợp.

## 6. Khi nào chọn AsynchronousChannel?

Các lớp tiêu biểu của Java NIO.2:

| API | Chức năng |
| --- | --- |
| `AsynchronousSocketChannel` | TCP connect/read/write bất đồng bộ. |
| `AsynchronousServerSocketChannel` | Bind và accept TCP bất đồng bộ. |
| `AsynchronousFileChannel` | Đọc/ghi vùng tệp tại offset xác định bằng Future/callback. |
| `CompletionHandler<V, A>` | Callback `completed(result, attachment)` hoặc `failed(error, attachment)`. |
| `AsynchronousChannelGroup` | Nhóm channel và tài nguyên thực thi liên quan. |

Đây là lựa chọn hữu ích khi ứng dụng đã dựa trên **completion pipeline**, muốn caller phát hành operation và làm việc khác, hoặc muốn file I/O có callback/Future tại offset riêng.

### 6.1. Future không khiến mã chờ biến mất

~~~java
try (AsynchronousSocketChannel client =
        AsynchronousSocketChannel.open()) {

    client.connect(remote).get(5, TimeUnit.SECONDS);

    ByteBuffer data = ByteBuffer.allocate(256);
    Future<Integer> operation = client.read(data);
    int n = operation.get(5, TimeUnit.SECONDS);
}
~~~

Mảnh minh họa cần `remote` hợp lệ và import `AsynchronousSocketChannel`, `ByteBuffer`, `Future`, `TimeUnit`. **`get(...)` vẫn block caller trong lúc đợi**; phương thức `read` bên dưới được phát hành bất đồng bộ.

Khi Future hoàn tất, `n` là **số byte thực nhận**, không phải bằng `data.capacity()` mặc định. `n == -1` báo EOF; `n == 0` không đồng nghĩa một thông điệp đã hoàn chỉnh.

### 6.2. CompletionHandler thực sự tổ chức flow theo callback

~~~java
ByteBuffer input = ByteBuffer.allocate(1024);

channel.read(input, input,
        new CompletionHandler<Integer, ByteBuffer>() {
    @Override
    public void completed(Integer n, ByteBuffer buffer) {
        if (n == -1) {
            closeConnection();
            return;
        }
        if (n > 0) {
            buffer.flip();
            processAvailableBytes(buffer);
            buffer.compact();
        }
        // Nếu cần tiếp tục, phát hành lần read kế tiếp.
    }

    @Override
    public void failed(Throwable error, ByteBuffer buffer) {
        reportFailure(error);
        closeConnection();
    }
});
~~~

Đây là **pseudocode tích hợp**, không phải Java độc lập; `channel`, `closeConnection`, `processAvailableBytes`, `reportFailure` phải được ứng dụng định nghĩa.

Trạng thái input/output và buffer phải sống ít nhất đến lúc completion kết thúc. Không để luồng khác thay đổi position/limit của buffer đang được operation sử dụng. Handler thường được gọi thông qua cơ chế thực thi của provider/channel group; tránh thực hiện xử lý CPU hoặc blocking kéo dài trong handler.

### 6.3. File I/O bất đồng bộ

~~~java
try (AsynchronousFileChannel file =
        AsynchronousFileChannel.open(path, StandardOpenOption.READ)) {

    ByteBuffer target = ByteBuffer.allocate(4096);
    Future<Integer> op = file.read(target, 0L);
    int n = op.get();
}
~~~

Đây là mảnh minh họa, cần `path` hợp lệ và các import tương ứng. `AsynchronousFileChannel.read(dst, position)` nhận một **vị trí tệp rõ ràng** cho từng operation. Điều này khác với việc dùng một file-position chung trên `FileChannel`; các operation hoàn tất có thể không theo thứ tự phát hành. Không coi việc callback đến trước là bằng chứng byte offset nhỏ hơn đã ghi hoàn tất trước.

Implementation của asynchronous file I/O có thể dùng thread pool; không mặc định là kernel-native async hoặc nhanh hơn mọi `FileChannel` blocking.

## 7. Cây quyết định theo workload

~~~text
Bắt đầu
   |
   +-- I/O chủ yếu là đọc/ghi file?
   |     |
   |     +-- Tuần tự và đơn giản -> Files / FileChannel blocking
   |     |
   |     +-- Nhiều offset độc lập / cần completion?
   |             -> AsynchronousFileChannel
   |
   +-- I/O là nhiều socket TCP?
         |
         +-- Ít/vừa, logic tuần tự, dễ bảo trì?
         |       -> Blocking SocketChannel
         |
         +-- Nhiều socket idle, cần readiness event loop?
         |       -> Non-blocking SocketChannel + Selector
         |
         +-- Hệ thống xử lý theo callback/completion?
                 -> AsynchronousSocketChannel
~~~

Một thiết kế có thể **phối hợp** các hướng: selector quản lý network, worker pool xử lý CPU, AsynchronousFileChannel cho file offset, và API blocking cho thao tác nhỏ ngoài event loop. Không cần biến mọi lời gọi trong một ứng dụng thành cùng một kiểu API.

Bảng tình huống:

| Tình huống | Lựa chọn khởi đầu | Lý do |
| --- | --- | --- |
| Chương trình CLI tạo báo cáo từ tệp nhỏ | Blocking `Files` hoặc `FileChannel` | Chi phí trạng thái async lớn hơn lợi ích. |
| Một client gọi một vài TCP service | Blocking `SocketChannel` | Request-response rõ ràng, dễ debug. |
| Gateway có rất nhiều kết nối idle | Selector hoặc framework event-driven có kiểm chứng | Nhiều socket được theo dõi bởi ít I/O threads. |
| Ứng dụng callback-first trên mạng | `AsynchronousSocketChannel` | Flow theo completion, không cần caller chờ. |
| Xử lý nhiều vùng tệp tại các offset | `AsynchronousFileChannel` hoặc worker pool | Có thể overlap tác vụ nhưng phải xét ordering. |
| Server làm nén/mã hóa CPU nặng | Worker executor riêng | Selector không tự song song hóa CPU. |
| I/O blocking kiểu tuyến tính nhưng concurrency lớn trên Java 21+ | Virtual threads là một ứng viên | Vẫn cần giới hạn sockets và downstream resources. |
| Tệp cần snapshot nhất quán khi writer khác cập nhật | Versioning, transaction, snapshot | Đổi API I/O không tự tạo consistency. |

## 8. Ví dụ Java 17+ chạy được: cùng một PING/PONG bằng ba mô hình

Ví dụ có **một server TCP loopback blocking** phục vụ ba kết nối, mỗi lần nhận đúng `PING` và gửi đúng `PONG`. Cả ba client gọi nối tiếp để stdout có thứ tự cố định:

- Client 1: blocking `SocketChannel`.
- Client 2: non-blocking `SocketChannel` + `Selector`, chuyển `OP_CONNECT → OP_WRITE → OP_READ`.
- Client 3: `AsynchronousSocketChannel` với Future và `get(timeout)`. Vì gọi `get`, luồng main vẫn chờ các completion.

Code không giả định một lần `read/write` chuyển đủ bốn byte và có timeout để tránh vòng đợi vô hạn trong client selector/Future.

Lưu file `IoModelChoiceDemo.java`:

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.SocketAddress;
import java.net.SocketTimeoutException;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousSocketChannel;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.util.Iterator;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class IoModelChoiceDemo {

    private static final byte[] REQUEST =
            "PING".getBytes(StandardCharsets.US_ASCII);

    static void sendBlocking(SocketChannel channel, ByteBuffer src)
            throws IOException {
        while (src.hasRemaining()) {
            if (channel.write(src) == 0) {
                throw new IOException("Blocking write không tiến triển");
            }
        }
    }

    static void receiveBlocking(SocketChannel channel, ByteBuffer dst)
            throws IOException {
        while (dst.hasRemaining()) {
            int n = channel.read(dst);
            if (n == -1) {
                throw new EOFException("EOF trước khi đủ dữ liệu");
            }
            if (n == 0) {
                throw new IOException("Blocking read không tiến triển");
            }
        }
    }

    static String decode(ByteBuffer data) {
        data.flip();
        return StandardCharsets.US_ASCII.decode(data).toString();
    }

    static String blockingClient(SocketAddress address)
            throws IOException {
        try (SocketChannel client = SocketChannel.open(address)) {
            sendBlocking(client, ByteBuffer.wrap(REQUEST));
            ByteBuffer reply = ByteBuffer.allocate(4);
            receiveBlocking(client, reply);
            return decode(reply);
        }
    }

    static String selectorClient(SocketAddress address)
            throws IOException {
        try (Selector selector = Selector.open();
             SocketChannel client = SocketChannel.open()) {

            client.configureBlocking(false);
            boolean connectedNow = client.connect(address);
            client.register(selector, connectedNow
                    ? SelectionKey.OP_WRITE
                    : SelectionKey.OP_CONNECT);

            ByteBuffer outgoing = ByteBuffer.wrap(REQUEST);
            ByteBuffer incoming = ByteBuffer.allocate(4);
            long deadline = System.nanoTime()
                    + TimeUnit.SECONDS.toNanos(5);

            while (incoming.hasRemaining()) {
                long remainingNanos = deadline - System.nanoTime();
                if (remainingNanos <= 0) {
                    throw new SocketTimeoutException("Selector deadline");
                }
                long timeoutMs = Math.max(1,
                        TimeUnit.NANOSECONDS.toMillis(remainingNanos));

                if (selector.select(timeoutMs) == 0) {
                    continue;
                }
                Iterator<SelectionKey> it =
                        selector.selectedKeys().iterator();

                while (it.hasNext()) {
                    SelectionKey key = it.next();
                    it.remove();
                    if (!key.isValid()) {
                        continue;
                    }

                    if (key.isConnectable()) {
                        if (client.finishConnect()) {
                            key.interestOps(SelectionKey.OP_WRITE);
                        }
                    } else if (key.isWritable()) {
                        client.write(outgoing);
                        if (!outgoing.hasRemaining()) {
                            key.interestOps(SelectionKey.OP_READ);
                        }
                    } else if (key.isReadable()) {
                        int n = client.read(incoming);
                        if (n == -1) {
                            throw new EOFException("Selector EOF sớm");
                        }
                    }
                }
            }
            return decode(incoming);
        }
    }

    static String asyncClient(SocketAddress address)
            throws Exception {
        try (AsynchronousSocketChannel client =
                AsynchronousSocketChannel.open()) {

            client.connect(address).get(5, TimeUnit.SECONDS);

            ByteBuffer outgoing = ByteBuffer.wrap(REQUEST);
            while (outgoing.hasRemaining()) {
                int n = client.write(outgoing).get(5, TimeUnit.SECONDS);
                if (n == 0) {
                    throw new IOException("Async write không tiến triển");
                }
            }

            ByteBuffer incoming = ByteBuffer.allocate(4);
            while (incoming.hasRemaining()) {
                int n = client.read(incoming).get(5, TimeUnit.SECONDS);
                if (n == -1) {
                    throw new EOFException("Async EOF sớm");
                }
                if (n == 0) {
                    throw new IOException("Async read không tiến triển");
                }
            }
            return decode(incoming);
        }
    }

    static void serveThree(ServerSocketChannel server)
            throws IOException {
        for (int i = 0; i < 3; i++) {
            try (SocketChannel peer = server.accept()) {
                ByteBuffer request = ByteBuffer.allocate(4);
                receiveBlocking(peer, request);

                if (!"PING".equals(decode(request))) {
                    throw new IOException("Request không hợp lệ");
                }

                ByteBuffer answer = ByteBuffer.wrap(
                        "PONG".getBytes(StandardCharsets.US_ASCII));
                sendBlocking(peer, answer);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        try (ServerSocketChannel server = ServerSocketChannel.open()) {
            server.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 0));

            SocketAddress address = server.getLocalAddress();
            ExecutorService executor =
                    Executors.newSingleThreadExecutor();

            try {
                Future<?> serving = executor.submit(() -> {
                    try {
                        serveThree(server);
                    } catch (IOException e) {
                        throw new RuntimeException(e);
                    }
                });

                String blocking = blockingClient(address);
                String selector = selectorClient(address);
                String async = asyncClient(address);

                serving.get(5, TimeUnit.SECONDS);

                System.out.println("blocking=" + blocking);
                System.out.println("selector=" + selector);
                System.out.println("async=" + async);
            } finally {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Lệnh biên dịch/chạy bằng JDK 17 trở lên:

~~~bash
javac IoModelChoiceDemo.java
java IoModelChoiceDemo
~~~

**Stdout dự kiến** khi môi trường cho phép mở TCP socket trên loopback:

~~~text
blocking=PONG
selector=PONG
async=PONG
~~~

Giải thích:

1. Server bind loopback với port 0 (hệ điều hành tự chọn), rồi một executor thread lần lượt `accept` ba client.
2. `blockingClient` thực hiện `sendBlocking`/`receiveBlocking` trong cùng flow; vẫn lặp đến khi đủ 4 byte.
3. `selectorClient` tự quản lý connection state. Nếu `connect` chưa xong, chờ `OP_CONNECT` và gọi `finishConnect`; tiếp theo gửi PING khi `OP_WRITE`, đọc PONG khi `OP_READ`. Phần chưa xử lý vẫn nằm trong `ByteBuffer`.
4. `asyncClient` phát hành `connect`, `write`, `read` và nhận completion count qua Future. Trong ví dụ caller gọi `get` có timeout, nên vẫn chờ để giữ luồng minh họa đơn giản.
5. Các client lần lượt hoàn tất mới in kết quả. Server luôn phản hồi PONG khi nhận PING, nên ba dòng là cố định.

**Ví dụ không phải benchmark.** Nó chỉ đặt ba phong cách API cạnh nhau trên cùng một protocol. Server chỉ phục vụ ba request nhỏ, không đại diện cho tải hàng nghìn kết nối. Để đánh giá hiệu năng cần workload thật, kiểm tra throughput, P95/P99, CPU, RAM và lỗi timeout.

## 9. Partial I/O và trạng thái buffer: rủi ro chung

Tất cả ba mô hình cần quản lý `ByteBuffer.position()`, `limit()` và `remaining()` đúng:

~~~text
Buffer chứa 8 byte A B C D E F G H, position=0 limit=8
write lần 1 trả 3 -> position=3, remaining=5
write lần 2 trả 2 -> position=5, remaining=3
write lần 3 trả 3 -> position=8, remaining=0
Lúc này mới thực sự hết byte cần gửi.
~~~

- **Blocking:** lặp write đến khi hết, hoặc xử lý lỗi/timeout.
- **Selector:** nếu non-blocking write trả `0`, giữ buffer và đợi `OP_WRITE`; nếu write một phần, không `flip()` hoặc `clear()` nhầm.
- **Async:** sau completion, xem `n` byte thực chuyển; phát hành operation kế tiếp nếu còn dữ liệu. Không sửa buffer khi operation trước đang dùng nó.

Với read, khi đọc một protocol length-prefix, 4 byte header có thể đến qua nhiều lần đọc. Cần parser state machine hoặc tích lũy cho đủ. TCP là luồng byte, **không bảo toàn ranh giới giữa các lần write** của phía gửi.

## 10. Timeout, cancellation và backpressure

### 10.1. Timeout không được suy đoán

Xác định giới hạn **connect**, **đọc một frame**, **ghi phản hồi**, **idle** và **tổng thời gian request**. Ví dụ `selector.select(5_000)` chỉ giới hạn một lần chờ readiness; nó không tự tạo timeout cho toàn bộ request. Cần deadline tích lũy như `System.nanoTime()`.

`Future.get(timeout)` chỉ giới hạn **thời gian chờ của caller**; khi ném `TimeoutException`, không mặc định operation đã bị hủy. Cần đóng socket hoặc yêu cầu cancel có kiểm soát, tránh để callback đến trễ xử lý dữ liệu của request đã bị loại bỏ.

### 10.2. Cancellation và cleanup

Khi client bỏ cuộc, có thể có một I/O operation đã phát hành mà chưa hoàn thành. Cần định nghĩa state như OPEN, CLOSING, CLOSED; đóng tài nguyên và bỏ buffer đang chờ theo chính sách; callback/future lỗi phải được xử lý **idempotent**, không đóng hoặc hoàn tất request nhiều lần.

Một `CompletionHandler` có thể chạy trên thread do implementation quản lý. Nếu callback gọi phương thức blocking lâu, một số completion khác có thể bị trì hoãn. Hãy chuyển tác vụ nặng sang worker pool hoặc pipeline thích hợp.

### 10.3. Backpressure

Giả sử ứng dụng tạo phản hồi nhanh gấp nhiều lần tốc độ client đọc: outbound queue lớn dần và có thể làm cạn RAM.

- Blocking: giới hạn số worker, số request chờ và thời gian gửi; không cho queue tăng vô hạn.
- Selector: chỉ bật `OP_WRITE` khi có byte chờ; có thể tạm ngừng `OP_READ` hoặc đóng socket khi queue vượt ngưỡng.
- Async: đặt hạn mức số operation in-flight và bộ nhớ giữ bởi callback/Future; chưa hoàn thành một write thì không tùy tiện xếp thêm vô hạn các write tương ứng.

Không có API nào tự cung cấp backpressure theo yêu cầu nghiệp vụ nếu ứng dụng không định nghĩa giới hạn.

## 11. Khi nào phối hợp nhiều mô hình?

Một hệ thống có thể sử dụng Selector cho mạng mà vẫn có worker pool thực hiện các công việc blocking hoặc CPU-heavy:

~~~text
Selector thread                        Worker pool
      |                                     |
      +-- read/parse request                |
      +-- submit job ---------------------->|
      |   phục vụ những socket khác         +-- xử lý nghiệp vụ
      |<-------------- kết quả qua queue ---+
      +-- selector.wakeup()
      +-- đẩy response vào output queue
      +-- bật OP_WRITE
~~~

Ở đây queue phải thread-safe. Tốt nhất chỉ event-loop thread sở hữu và cập nhật per-connection buffer/attachment; worker trả kết quả bất biến hoặc message để loop xử lý. `selector.wakeup()` đánh thức select, **không có nghĩa socket tự nhiên đã có readiness**.

Nếu tác vụ là `AsynchronousFileChannel`, có thể nhận Future/callback rồi chuyển kết quả tới event loop. Nhưng không vì trộn mô hình mà bỏ qua ownership, cancellation hay thứ tự ghi.

## 12. Các sai lầm khi lựa chọn API

| Sai lầm | Hệ quả / cách sửa |
| --- | --- |
| Cho rằng asynchronous luôn nhanh hơn blocking | Cần đo workload: scheduling, callback, pool và buffer có chi phí. |
| Dùng Selector cho FileChannel thông thường | `FileChannel` không selectable; dùng `FileChannel` hoặc `AsynchronousFileChannel`. |
| Dùng Future rồi gọi get ngay và tuyên bố caller non-blocking | `get` có thể block; muốn non-blocking caller cần completion/callback phù hợp. |
| Gắn mọi socket vào một event loop rồi làm CPU-heavy trong callback | Một callback lâu cản trở các socket khác; chuyển việc nặng ra pool. |
| Dùng một ByteBuffer cho nhiều async operation đồng thời | Rủi ro tranh chấp position/limit; cần ownership và thời điểm giải phóng rõ ràng. |
| Bỏ qua read/write count vì nghĩ blocking đảm bảo toàn bộ | Vẫn có partial I/O; kiểm tra `remaining()` và EOF. |
| Gọi `clear()` sau một non-blocking write chưa hoàn tất | Mất các byte chưa gửi; giữ buffer chờ OP_WRITE. |
| Giữ OP_WRITE trong interestOps khi output queue rỗng | Loop có thể thức dậy liên tục; chỉ bật khi có dữ liệu. |
| Nghĩ `Future.get(timeout)` chắc chắn đã hủy I/O | Timeout chỉ báo caller hết thời gian chờ; cần cancel/close. |
| Không giới hạn kết nối, hàng đợi hoặc bộ nhớ | Bất kỳ mô hình nào cũng có thể hết tài nguyên. |
| Cho rằng Java 17 có virtual threads chuẩn | Tính năng chính thức bắt đầu ở Java 21. |
| Dùng cùng một lựa chọn cho socket, file, DB, CPU | Các loại tài nguyên có API và chi phí khác nhau; có thể phối hợp. |

## 13. Checklist lựa chọn theo bài toán

Trả lời các câu hỏi sau trước khi triển khai:

1. **Loại tài nguyên?** TCP, UDP, file, database, pipe hay CPU? Selector chỉ áp dụng selectable channels.
2. **Bao nhiêu kết nối đồng thời?** Đừng chỉ đo request mỗi giây mà bỏ qua số socket idle.
3. **Chờ I/O chiếm bao nhiêu thời gian so với xử lý CPU?** Event loop đặc biệt hợp với callback ngắn.
4. **Java phiên bản nào?** Trên Java 17 dùng ba mô hình chuẩn; trên Java 21+ xem thêm virtual threads.
5. **Yêu cầu latency và throughput?** Đo P95/P99, không chỉ trung bình.
6. **Có cần thao tác theo completion callback không?** Nếu không, blocking có thể đủ và dễ hơn.
7. **Có state machine cho framing và partial reads/writes không?** Bất kể API nào đều phải đúng giao thức.
8. **Timeout, cancellation, close được định nghĩa chưa?** Đừng để request hoặc in-flight operation tồn tại vô hạn.
9. **Ai sở hữu buffer và kết nối?** Tránh race khi callback/worker cùng cập nhật.
10. **Có giới hạn output queue và số operation in-flight không?** Đây là nền tảng backpressure.
11. **Đã thử tải với client chậm, EOF, ngắt kết nối và mạng lỗi chưa?** Tải lý tưởng thường che giấu lỗi.
12. **Có thật sự cần đổi kiến trúc?** Nếu cách đơn giản đáp ứng SLO, lợi ích của một mô hình phức tạp cần có số liệu chứng minh.

## 14. Câu hỏi tự kiểm tra

1. **Một CLI đọc tệp nhỏ rồi ghi kết quả, có cần Selector không?** Thông thường không. `Files` hoặc `FileChannel` blocking đơn giản hơn.
2. **Một gateway có rất nhiều TCP socket chờ dữ liệu, mô hình nào đáng cân nhắc?** Selector hoặc async socket, với benchmark và giới hạn tài nguyên.
3. **`Selector.isReadable` báo gì?** Readiness để thử đọc; không hứa một message hoàn chỉnh.
4. **Asynchronous Future mà gọi `get()` thì caller có thể bị chặn không?** Có.
5. **`AsynchronousFileChannel` có thể đăng ký OP_READ với Selector không?** Không; đây là API completion cho file.
6. **Một read completion nhận 2/4 byte header có hoàn tất giao thức chưa?** Chưa, phải nhận tiếp hoặc xử lý EOF/lỗi.
7. **Một non-blocking write trả 0 là lỗi chắc chắn không?** Không; có thể tạm chưa writable.
8. **`OP_WRITE` nên bật khi nào?** Khi có dữ liệu chờ gửi và cần đợi writable; tắt khi hết.
9. **Một loop chỉ có một thread có tự chạy song song các CPU tasks không?** Không.
10. **Timeout của Future.get tự hủy socket operation không?** Không bảo đảm; cần chính sách cancel/close.
11. **Tại sao AsynchronousFileChannel không nhất thiết nhanh hơn FileChannel blocking?** Provider có thể dùng thread pool; tải và overhead quyết định.
12. **Nếu hệ thống cần data consistency, đổi sang async có giải quyết transaction không?** Không; consistency/transaction thuộc giao thức hoặc tầng lưu trữ.

## 15. Tài liệu Java 17 tham khảo

- [SocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html): blocking/non-blocking, connect/read/write.
- [Selector](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html) và [SelectionKey](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectionKey.html): readiness/interest operations.
- [AsynchronousSocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousSocketChannel.html): Future và completion handler cho TCP.
- [AsynchronousFileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousFileChannel.html): file I/O với offset rõ ràng.
- [CompletionHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/CompletionHandler.html): kết quả thành công hoặc thất bại của operation.

**Ghi nhớ:** **Blocking** tối ưu sự đơn giản của flow tuần tự; **Selector** tối ưu khả năng điều phối nhiều selectable channels theo readiness với event loop; **AsynchronousChannel** cho completion qua Future/callback. Chọn theo workload, phiên bản JDK, khả năng quản lý state và SLO; cả ba đều phải giải quyết partial I/O, timeout, cancellation, buffer lifetime và backpressure.
