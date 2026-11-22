# Nhận kết quả qua Future hoặc CompletionHandler trong I/O bất đồng bộ Java

Với Java NIO.2, ứng dụng có thể **khởi tạo một thao tác I/O trước khi thao tác hoàn thành**, rồi nhận kết quả sau đó bằng hai phong cách chính: **`Future<V>`** hoặc **`CompletionHandler<V,A>`**. Cả hai được hỗ trợ bởi các kênh bất đồng bộ như `AsynchronousSocketChannel`, `AsynchronousServerSocketChannel` và `AsynchronousFileChannel`, nhưng khác nhau lớn ở cách điều khiển chương trình:

- **`Future<V>`:** phương thức trả ngay một đối tượng đại diện cho kết quả tương lai. Người gọi có thể tiếp tục làm việc khác, rồi gọi `get()` khi thực sự cần kết quả. **`get()` có thể chặn chính luồng gọi**.
- **`CompletionHandler<V,A>`:** người gọi truyền callback ngay khi khởi tạo I/O. Khi hoàn thành, hệ thống gọi `completed(result, attachment)` hoặc `failed(error, attachment)`. Phong cách này thuận lợi cho chuỗi tác vụ bất đồng bộ mà không cần một luồng đứng chờ mỗi kết quả.

Trong bài học, ví dụ chính dùng **TCP loopback** với `AsynchronousServerSocketChannel` và `AsynchronousSocketChannel`, vì module đang học networking. Phần cuối cũng chỉ ra cách áp dụng cùng mô hình với `AsynchronousFileChannel`. Tất cả code chạy độc lập được viết cho **Java 17 trở lên**.

## 1. “Bất đồng bộ” không có nghĩa `get()` không bao giờ chặn

Một thao tác bất đồng bộ thường tách thành ba giai đoạn:

~~~text
T0 — GỌI HÀM: khởi tạo read / write / connect / accept
         |
         +--- Future<V> được trả về
         |       ứng dụng xử lý việc khác
         |       ...
         |       get() chờ nếu chưa hoàn tất
         |
         +--- HOẶC đăng ký CompletionHandler
                 ứng dụng trả quyền điều khiển
                 ...
                 completed(value, attachment)
                    hoặc failed(cause, attachment)

T1 — I/O thực sự hoàn thành hoặc thất bại
T2 — Ứng dụng tiêu thụ kết quả / xử lý lỗi / dọn tài nguyên
~~~

Điểm khác biệt không nằm ở việc “một cách dùng async, một cách dùng sync”: cả hai **khởi tạo** I/O bất đồng bộ. Nhưng nếu ngay sau `channel.read(buffer)` bạn gọi `future.get()` trên cùng luồng, bạn đã **đợi đồng bộ** kết quả tại vị trí đó. Việc đợi có thể hợp lý trong chương trình nhỏ, nhưng khi xây server phục vụ nhiều client, cần tránh để mọi luồng bị chiếm chỉ vì `get()`.

Kênh Java NIO.2 có thể sử dụng các thread của `AsynchronousChannelGroup` và cơ chế I/O đặc thù của hệ điều hành; không nên suy luận rằng mọi runtime đều triển khai bằng cùng một cơ chế kernel. **“Bất đồng bộ” là hợp đồng API**, không phải lời hứa rằng thao tác chẳng dùng thread, chẳng block ở bất kỳ mức nào, hoặc luôn nhanh hơn I/O blocking.

## 2. API nào trả Future, API nào nhận CompletionHandler?

Với TCP asynchronous channels trong Java 17:

| Thao tác | Dạng Future | Dạng callback |
| --- | --- | --- |
| Server nhận kết nối | `Future<AsynchronousSocketChannel> accept()` | `accept(A attachment, CompletionHandler<AsynchronousSocketChannel, ? super A>)` |
| Client kết nối TCP | `Future<Void> connect(SocketAddress remote)` | `connect(SocketAddress, A, CompletionHandler<Void, ? super A>)` |
| Đọc bytes | `Future<Integer> read(ByteBuffer dst)` | `read(ByteBuffer dst, A, CompletionHandler<Integer, ? super A>)` |
| Ghi bytes | `Future<Integer> write(ByteBuffer src)` | `write(ByteBuffer src, A, CompletionHandler<Integer, ? super A>)` |

`AsynchronousSocketChannel` nhận và ghi **stream byte của TCP**, không tự phân định một `read()` tương ứng một request, một response hay một `write()`. Kết quả đọc/ghi thường là **số byte của lần hoàn thành đó**, có thể nhỏ hơn số byte bạn mong muốn.

Với `AsynchronousFileChannel`, hai phong cách cũng tồn tại, nhưng API nhận thêm vị trí trong tệp:

~~~java
// Các chữ ký rút gọn (minh họa, không phải class chạy độc lập):
Future<Integer> result = file.read(dst, filePosition);

file.read(dst, filePosition, attachment,
          new CompletionHandler<Integer, AttachmentType>() {
              @Override
              public void completed(Integer count, AttachmentType state) {
                  // Hoàn thành đọc.
              }
              @Override
              public void failed(Throwable cause, AttachmentType state) {
                  // Đọc lỗi.
              }
          });
~~~

Tại `AsynchronousFileChannel`, vị trí file là **tham số tường minh**; khác với TCP socket là stream tuần tự, không có file offset. Phần này chỉ minh họa API; bạn phải mở file channel và định nghĩa `AttachmentType` trước khi biên dịch.

## 3. Nhận kết quả bằng `Future<V>`

Ví dụ:

~~~java
// Fragment bên trong một method có AsynchronousSocketChannel channel:
ByteBuffer buffer = ByteBuffer.allocate(1024);
Future<Integer> pendingRead = channel.read(buffer);

// Có thể thực hiện việc không phụ thuộc vào pendingRead ở đây.
int bytes = pendingRead.get(); // Chặn nếu read chưa hoàn tất.
buffer.flip();
~~~

Ở đây:

1. `read(buffer)` **khởi tạo thao tác đọc** và trả `Future<Integer>`.
2. `pendingRead.isDone()` cho biết thao tác **đã kết thúc** ở một trạng thái nào đó, không có nghĩa chắc chắn thành công. Nó có thể thành công, thất bại hoặc bị hủy.
3. `pendingRead.get()` chờ kết quả nếu cần. Với lần đọc hoàn tất thành công, giá trị `Integer` biểu thị số byte đã đọc; giá trị `-1` là EOF phía đầu ra của TCP peer.
4. Chỉ sau khi hoàn tất mới được dùng/di chuyển buffer như thể I/O đó đã xong. `flip()` giúp chuyển vùng nhận sang vùng đọc.

**Chú ý:** với `ByteBuffer` có `remaining() == 0`, lời gọi đọc có thể hoàn tất ngay với `0`. Không lấy `0` làm bằng chứng mất kết nối. Khi `remaining() > 0`, đọc TCP thông thường có thể chỉ trả về một phần dữ liệu mong muốn; phải dùng framing hoặc lặp tới đủ bytes / delimiter / EOF.

### Dùng `get(timeout, unit)` đúng cách

~~~java
// Fragment cho một Future<Integer> đã khởi tạo.
try {
    Integer n = pendingRead.get(3, TimeUnit.SECONDS);
    // n là số byte hoặc -1; tiếp tục xử lý theo protocol.
} catch (TimeoutException timeout) {
    // CHỈ timeout chờ Future trên luồng hiện tại.
    // Không mặc nhiên hủy I/O đang pending.
    channel.close(); // Ví dụ chính sách hủy bằng đóng channel.
}
~~~

`get(3, SECONDS)` giới hạn **thời gian chờ của lời gọi get**. Nếu ném `TimeoutException`, thao tác I/O có thể **vẫn đang tiếp tục**; timeout của `Future.get` không tự gửi tín hiệu stop tới OS và không tự biến kết quả thành thất bại.

Nếu ứng dụng không còn muốn giữ thao tác, có thể dùng `Future.cancel(...)` theo hợp đồng cụ thể của kênh; nhưng đối với asynchronous socket, cancellation có thể ảnh hưởng tới trạng thái kênh và những byte đã/đang được truyền. Đừng tự khẳng định `cancel(true)` luôn ngắt tức thời mà không có side effect. **Đóng kênh/giải phóng tài nguyên có kiểm soát** và không tái sử dụng buffer đang có kết quả không chắc chắn là chính sách đơn giản hơn ở nhiều trường hợp bỏ phiên.

### Các ngoại lệ quan trọng của Future

| Tình huống | Biểu hiện | Cách hiểu |
| --- | --- | --- |
| I/O hoàn thành thành công | `get()` trả `V` | Kiểm tra giá trị kết quả; số byte có thể nhỏ hơn payload |
| I/O thất bại | `ExecutionException` | Nguyên nhân thật trong `getCause()`, thường là `IOException` hoặc lỗi channel |
| Thread đang chờ bị interrupt | `InterruptedException` | Khôi phục cờ interrupt nếu xử lý ở tầng phù hợp; tổ chức cleanup |
| `get(timeout)` quá hạn | `TimeoutException` | Timeout chờ; I/O không tự hủy |
| Future đã bị hủy | `CancellationException` | Không có kết quả thành công thông thường |

Ví dụ xử lý lỗi:

~~~java
// Fragment minh họa; cần imports java.util.concurrent.*.
try {
    int n = readFuture.get(5, TimeUnit.SECONDS);
    if (n == -1) {
        // TCP peer kết thúc chiều gửi.
    } else {
        // n byte đã ghi vào ByteBuffer.
    }
} catch (ExecutionException ex) {
    Throwable cause = ex.getCause();
    // Log cause kèm client/request context, không chỉ log wrapper.
    throw new IOException("Asynchronous read failed", cause);
} catch (TimeoutException ex) {
    // Quyết định đóng connection / bỏ response / retry theo nghiệp vụ.
    throw new IOException("Read did not finish in time", ex);
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new IOException("Waiting thread interrupted", ex);
}
~~~

Đây là **fragment**, giả định đã có `readFuture` và import `IOException`. Trong hệ thống thực tế, ngoài việc ném lại lỗi còn cần quản lý vòng đời kênh, hủy/cancel khi thích hợp và không sử dụng một operation đã timeout để tạo race.

## 4. Nhận kết quả bằng `CompletionHandler<V,A>`

Định nghĩa của Java NIO.2:

~~~java
public interface CompletionHandler<V, A> {
    void completed(V result, A attachment);
    void failed(Throwable exc, A attachment);
}
~~~

Trong đó:

- `V` là **kiểu kết quả I/O**: ví dụ `Integer` cho read/write, `Void` cho connect, hoặc `AsynchronousSocketChannel` cho accept.
- `A` là **kiểu attachment**, tức đối tượng ngữ cảnh **do chính bạn truyền lúc gọi I/O**, không phải giá trị do Java tự tìm trong buffer.
- `completed(...)` được gọi khi thao tác hoàn thành thành công; đối với đọc TCP, callback `completed(-1, ...)` là một lần hoàn thành thành công **về mặt API** nhưng cho biết EOF, không phải `failed(...)`.
- `failed(Throwable, attachment)` được gọi khi thao tác I/O thất bại. Đây là nơi nhận trực tiếp nguyên nhân lỗi, không cần mở lớp bọc `ExecutionException` như khi gọi Future.
- Callback nên hoàn thành nhanh, tránh chạy CPU/DB blocking lâu hoặc gọi `Future.get()` chặn vô thời hạn ngay trong callback, vì có thể làm giảm số thread của asynchronous channel group có thể dispatch callback khác.

Ví dụ một thao tác đọc:

~~~java
// Fragment bên trong method, socket đã kết nối.
ByteBuffer buffer = ByteBuffer.allocate(1024);

channel.read(buffer, "request-42",
        new CompletionHandler<Integer, String>() {
            @Override
            public void completed(Integer count, String requestId) {
                if (count < 0) {
                    // EOF, cleanup tùy giao thức.
                    return;
                }
                buffer.flip();
                // Parse dữ liệu liên quan tới requestId.
                // Nếu thiếu dữ liệu, tổ chức read kế tiếp sau khi
                // thao tác hiện tại đã hoàn tất.
            }

            @Override
            public void failed(Throwable exc, String requestId) {
                // Log exception và context requestId, cleanup.
            }
        });
~~~

`"request-42"` là attachment kiểu `String`. Có thể thay bằng object chứa ID, buffer, deadline, trạng thái parser hoặc request state. Tránh nhét quá nhiều mutable global state không đồng bộ vào callback. Một attachment khác không làm hai thao tác đọc chồng nhau trên **cùng một channel** trở nên hợp lệ.

### Callback làm thay đổi cách viết chuỗi tác vụ

Từ mẫu chờ tuần tự:

~~~text
Future read -> get -> parse -> Future write -> get
     (thread chờ)              (thread chờ)
~~~

sang mẫu kích hoạt bước tiếp sau khi bước trước hoàn tất:

~~~text
initiate read()
       |
       +--- completed(readBytes)
       |        |
       |        +--- parse; nếu đủ request thì initiate write()
       |                                    |
       |                                    +--- completed(writeBytes)
       |                                    +--- failed(writeError)
       |
       +--- failed(readError)
~~~

Trong trường hợp response cần ghi nhiều lần do partial write, `completed(writeCount)` kiểm tra `ByteBuffer.hasRemaining()` trước khi đăng ký lượt ghi tiếp theo. Không tự coi **một** callback ghi thành công là toàn bộ response đã được ghi hết.

## 5. Ví dụ Java 17+: cả Future lẫn CompletionHandler trên TCP loopback

Ví dụ đầy đủ tạo TCP listener ở loopback với cổng `0` để OS chọn cổng trống. Nó chạy **hai phiên tách biệt**:

- **Future path:** client kết nối tới listener, gửi `PING`; server nhận đủ bốn byte bằng các lời gọi `read(...).get(...)` và in kết quả.
- **Handler path:** client đăng ký callback đọc, server đăng ký callback ghi rồi hai handler tiếp tục tới khi buffer đủ; thread chính chỉ dùng `CountDownLatch` để kết thúc **bài thử** một cách có thứ tự, không lấy `Future.get()` làm cách nhận kết quả đọc/ghi trong path này.

Lưu với tên đúng **`AsyncResultsDemo.java`**:

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousServerSocketChannel;
import java.nio.channels.AsynchronousSocketChannel;
import java.nio.channels.CompletionHandler;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class AsyncResultsDemo {
    private static final long LIMIT_SECONDS = 5;

    // Mỗi Future.get() có thời gian chờ tối đa cho lần thao tác đó.
    private static int writeAll(
            AsynchronousSocketChannel channel, ByteBuffer data)
            throws Exception {
        int total = 0;
        while (data.hasRemaining()) {
            int n = channel.write(data)
                    .get(LIMIT_SECONDS, TimeUnit.SECONDS);
            if (n <= 0) {
                throw new IOException("No write progress");
            }
            total += n;
        }
        return total;
    }

    private static int readAll(
            AsynchronousSocketChannel channel, ByteBuffer data)
            throws Exception {
        int total = 0;
        while (data.hasRemaining()) {
            int n = channel.read(data)
                    .get(LIMIT_SECONDS, TimeUnit.SECONDS);
            if (n < 0) {
                throw new EOFException("Peer closed too soon");
            }
            if (n == 0) {
                throw new IOException("No read progress");
            }
            total += n;
        }
        return total;
    }

    private static void futurePath() throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();

        try (AsynchronousServerSocketChannel listener =
                     AsynchronousServerSocketChannel.open()) {
            listener.bind(new InetSocketAddress(loopback, 0));

            Future<AsynchronousSocketChannel> pendingAccept =
                    listener.accept();

            try (AsynchronousSocketChannel client =
                         AsynchronousSocketChannel.open()) {
                Future<Void> connecting =
                        client.connect(listener.getLocalAddress());
                connecting.get(LIMIT_SECONDS, TimeUnit.SECONDS);

                try (AsynchronousSocketChannel serverSide =
                             pendingAccept.get(
                                     LIMIT_SECONDS,
                                     TimeUnit.SECONDS)) {

                    int written = writeAll(
                            client,
                            StandardCharsets.UTF_8.encode("PING"));

                    ByteBuffer inbound = ByteBuffer.allocate(4);
                    int received = readAll(serverSide, inbound);
                    inbound.flip();

                    System.out.println("futureWriteBytes=" + written);
                    System.out.println("futureReadBytes=" + received);
                    System.out.println(
                            "futureText="
                                    + StandardCharsets.UTF_8.decode(
                                            inbound));
                }
            }
        }
    }

    private static void handlerPath() throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();

        try (AsynchronousServerSocketChannel listener =
                     AsynchronousServerSocketChannel.open()) {
            listener.bind(new InetSocketAddress(loopback, 0));

            Future<AsynchronousSocketChannel> pendingAccept =
                    listener.accept();

            try (AsynchronousSocketChannel client =
                         AsynchronousSocketChannel.open()) {
                client.connect(listener.getLocalAddress())
                        .get(LIMIT_SECONDS, TimeUnit.SECONDS);

                try (AsynchronousSocketChannel serverSide =
                             pendingAccept.get(
                                     LIMIT_SECONDS,
                                     TimeUnit.SECONDS)) {

                    ByteBuffer input = ByteBuffer.allocate(4);
                    ByteBuffer output =
                            StandardCharsets.UTF_8.encode("PONG");

                    CountDownLatch finished = new CountDownLatch(2);
                    AtomicReference<Throwable> failure =
                            new AtomicReference<>();
                    AtomicInteger sent = new AtomicInteger();
                    AtomicInteger received = new AtomicInteger();

                    // Handler đọc: attachment chính là buffer.
                    client.read(input, input,
                            new CompletionHandler<Integer, ByteBuffer>() {
                        @Override
                        public void completed(
                                Integer n, ByteBuffer buffer) {
                            if (n < 0) {
                                failed(new EOFException(
                                        "EOF before 4 bytes"), buffer);
                                return;
                            }
                            received.addAndGet(n);

                            if (buffer.hasRemaining()) {
                                client.read(buffer, buffer, this);
                            } else {
                                finished.countDown();
                            }
                        }

                        @Override
                        public void failed(
                                Throwable exc, ByteBuffer buffer) {
                            failure.compareAndSet(null, exc);
                            finished.countDown();
                        }
                    });

                    // Handler ghi: chỉ ghi tiếp sau completion.
                    serverSide.write(output, output,
                            new CompletionHandler<Integer, ByteBuffer>() {
                        @Override
                        public void completed(
                                Integer n, ByteBuffer buffer) {
                            if (n < 0) {
                                failed(new IOException(
                                        "Unexpected write result"),
                                        buffer);
                                return;
                            }
                            sent.addAndGet(n);

                            if (buffer.hasRemaining()) {
                                serverSide.write(buffer, buffer, this);
                            } else {
                                finished.countDown();
                            }
                        }

                        @Override
                        public void failed(
                                Throwable exc, ByteBuffer buffer) {
                            failure.compareAndSet(null, exc);
                            finished.countDown();
                        }
                    });

                    // Chỉ để main chờ demo hoàn thành rồi in
                    // stdout theo thứ tự không phụ thuộc callback timing.
                    if (!finished.await(
                            LIMIT_SECONDS, TimeUnit.SECONDS)) {
                        throw new TimeoutException(
                                "Callback did not finish");
                    }
                    if (failure.get() != null) {
                        throw new IOException(
                                "Callback failed", failure.get());
                    }

                    input.flip();
                    System.out.println(
                            "handlerWriteBytes=" + sent.get());
                    System.out.println(
                            "handlerReadBytes=" + received.get());
                    System.out.println(
                            "handlerText="
                                    + StandardCharsets.UTF_8.decode(
                                            input));
                }
            }
        }
    }

    public static void main(String[] args) throws Exception {
        futurePath();
        handlerPath();
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac AsyncResultsDemo.java
java AsyncResultsDemo
~~~

**Đầu ra mong đợi** trên JDK 17+ khi loopback TCP được phép (logic đã kiểm tra với JDK):

~~~text
futureWriteBytes=4
futureReadBytes=4
futureText=PING
handlerWriteBytes=4
handlerReadBytes=4
handlerText=PONG
~~~

### Giải thích vì sao kết quả đáng tin

1. Listener bind địa chỉ loopback và port `0`; sau đó dùng `getLocalAddress()` cho client kết nối tới đúng cổng vừa mở, không phải đoán cổng.
2. `listener.accept()` trả `Future<AsynchronousSocketChannel>`; `client.connect(...)` trả `Future<Void>`. Trong hai path, ta dùng `get(timeout)` để **thiết lập điều kiện chạy bài thử** và lấy channel server-side.
3. Trong **futurePath**, vòng `writeAll/readAll` xử lý trường hợp một lần I/O hoàn thành chưa dùng hết buffer. Mỗi `get(timeout)` chờ **một thao tác**. Mã đơn giản này cố ý ném ngoại lệ khi `n == 0` với buffer vẫn còn chỗ, thay vì lặp không giới hạn.
4. Trong **handlerPath**, `read(input, input, handler)` và `write(output, output, handler)` dùng `ByteBuffer` làm attachment. Callback được gọi với **cùng object đã truyền**; không cần một biến toàn cục chứa request hiện tại.
5. Nếu `buffer.hasRemaining()`, callback bắt đầu **lượt I/O kế tiếp sau khi lượt trước đã hoàn thành**; như vậy tránh có hai read hoặc hai write outstanding cùng lúc. Có thể có **một read và một write** outstanding đồng thời trên cùng `AsynchronousSocketChannel`.
6. `CountDownLatch(2)` chỉ dùng để chương trình demo biết **cả callback đọc và ghi đều đã kết thúc**, rồi in các số lượng byte theo thứ tự. Một server thực tế sẽ không dùng thread chính đứng chờ mỗi client như vậy.
7. `try-with-resources` đóng client, socket đã được accept và listener. Khi test quá thời gian hoặc có exception, khối đóng tài nguyên vẫn chạy.

**Giới hạn:** mặc dù ví dụ dùng giao thức cố định 4 byte, TCP không giữ ranh giới message: trên mạng thật, phải có length prefix, delimiter hoặc framing rõ ràng. Mỗi callback có thể thấy một phần data. Kết quả loopback 4 byte không chứng minh mọi network đều giao hàng với đúng một read hoặc một write.

**Lưu ý cho production:** các lệnh khởi tạo read/write mới bên trong callback cũng có thể ném runtime exception tức thời nếu kênh đã bị đóng/đang có operation khác/callback group shutdown; cần bắt lỗi này, đảm bảo báo hoàn tất đúng một lần, đóng/thu hồi kết nối và tránh để request đứng chờ mãi. Callback đệ quy phù hợp minh họa một buffer nhỏ; luồng production nên có state machine và chính sách công bằng khi dữ liệu lớn.

## 6. Mẫu callback cho connect và accept, không dùng Future

Trong demo trên, bước khởi tạo được đồng bộ hóa bằng `Future.get()` cho dễ tái lập. Nhưng connect/accept cũng hỗ trợ completion handler trực tiếp.

Ví dụ **fragment server** minh họa callback accept và tiếp tục lắng nghe:

~~~java
// Fragment: listener đã bind và còn mở.
listener.accept(null,
        new CompletionHandler<AsynchronousSocketChannel, Void>() {
    @Override
    public void completed(
            AsynchronousSocketChannel client, Void ignored) {
        // Khởi tạo accept KẾ TIẾP sau khi accept trước hoàn tất.
        listener.accept(null, this);

        // Chuyển socket mới sang xử lý ứng dụng.
        // ownership, timeout, read/write, close cần được định nghĩa.
        handleNewClient(client);
    }

    @Override
    public void failed(Throwable error, Void ignored) {
        // Log; kiểm tra listener còn mở trước khi quyết định accept lại.
    }
});
~~~

`listener.accept(...)` không thể được gọi lần hai khi một `accept` trước đó vẫn đang pending; nếu làm vậy, Java ném `AcceptPendingException`. Trong callback `completed`, thao tác trước đã hoàn tất, nên có thể đăng ký **accept tiếp theo**. Tránh mất listener do exception trong `handleNewClient`; cần cơ chế quản lý lỗi và đóng các socket đã accept.

Ví dụ **fragment client** cho kết nối bất đồng bộ:

~~~java
// Fragment: client là AsynchronousSocketChannel vừa open().
client.connect(remote, "connect-request-42",
        new CompletionHandler<Void, String>() {
    @Override
    public void completed(Void ignored, String requestId) {
        // TCP connect hoàn tất. Lúc này bắt đầu write request.
        startRequest(client, requestId);
    }

    @Override
    public void failed(Throwable error, String requestId) {
        // Log nguyên nhân, báo request thất bại và close client.
    }
});
~~~

Trong `connect()` của TCP, chỉ khi completed mới bắt đầu I/O đã kết nối. Đối với `AsynchronousSocketChannel`, việc gọi read/write khi chưa kết nối có thể ném `NotYetConnectedException`. Hai fragment không phải class chạy độc lập vì các helper `handleNewClient`/`startRequest`, biến `listener/client/remote` và lifecycle do ứng dụng tự định nghĩa.

## 7. Quản lý ByteBuffer khi operation còn pending

Cả Future và CompletionHandler đều yêu cầu chú ý **ownership** của `ByteBuffer`.

### Mẫu đọc đúng

~~~text
buffer mới (position=0, limit=capacity)
   |
initiate async read(buffer)
   |
CHỜ operation hoàn tất (Future.get thành công hoặc completed callback)
   |
kiểm tra byte count; -1 = EOF
   |
buffer.flip()  -> limit=position, position=0
   |
parse đúng vùng remaining()
   |
buffer.clear() -> chuẩn bị tái sử dụng, KHÔNG xóa vật lý dữ liệu
~~~

Nếu đọc với Future thì **không** được gọi `flip()` hoặc chỉnh `position/limit` trong khi I/O vẫn pending. Nếu dùng callback, chỉ đọc/chỉnh buffer sau khi `completed` cho lượt tương ứng, hoặc sau khi xử lý lỗi biết rõ không có thao tác còn thay đổi buffer. Javadoc asynchronous channels nêu rõ các buffer không được truy cập/sửa trong lúc I/O còn sử dụng, vì nội dung/position có thể thay đổi bất đồng bộ.

Khi `write`:

~~~java
ByteBuffer out = StandardCharsets.UTF_8.encode("HELLO");
// encode() đã trả buffer ở trạng thái có byte sẵn để đọc;
// KHÔNG gọi flip() thêm ở đây.
channel.write(out); // Future path: chờ kết quả trước khi tái dùng out.
~~~

Với buffer tự tạo qua `allocate()` rồi `put()`, phải gọi `flip()` **trước** khi write. Với `StandardCharsets.UTF_8.encode(...)`, buffer đã ở tư thế đọc. Một `completed(count)` có thể chỉ ghi được một phần: phần còn lại nằm trong `out.remaining()`, nên muốn gửi hết response cần một lượt write tiếp theo sau completion.

### Dữ liệu lớn và framing

TCP không giữ ranh giới của write. Ví dụ client viết `HELLO` một lần nhưng peer có thể đọc lần đầu 2 byte và lần sau 3 byte, hoặc đọc được nhiều request cùng lúc trong buffer lớn hơn. Một protocol có thể dùng:

- **Length prefix:** gửi header chứa số byte payload; receiver đọc đủ header rồi đủ payload; kiểm tra max length trước khi cấp phát.
- **Delimiter:** xác định ranh giới bằng newline hoặc ký tự đặc biệt; cần giới hạn độ dài để tránh client gửi vô hạn.
- **Fixed length:** giao thức điều khiển định nghĩa đúng 4 byte hoặc N byte, như demo; phải đọc cho đủ N hoặc nhận EOF/lỗi.

Nếu đọc UTF-8, một ký tự có thể được chia giữa nhiều lần read; không nên decode từng mẩu tùy tiện mà không có decoder giữ trạng thái. Với payload nhị phân, xác định byte order, field format, version và length.

## 8. Một read và một write outstanding; không có hai read đồng thời

Theo Javadoc của `AsynchronousSocketChannel`:

- Có thể có **một read pending và một write pending** trên cùng channel cùng lúc.
- Nếu bắt đầu **read thứ hai trước khi read thứ nhất hoàn thành**, Java ném `ReadPendingException`.
- Nếu bắt đầu **write thứ hai trước khi write thứ nhất hoàn thành**, Java ném `WritePendingException`.
- Các operation của nhiều thread cần quản lý chung ownership, thứ tự, buffer và lifecycle. “Thread-safe API” không đồng nghĩa các request nghiệp vụ tự được sắp xếp theo thứ tự mong đợi.

Ví dụ phản ví dụ:

~~~java
// Fragment minh họa: không được dựa vào mẫu này.
Future<Integer> first = channel.read(bufferA);
Future<Integer> second = channel.read(bufferB);
// Nếu first còn pending, second ném ReadPendingException.
~~~

Không thử giải quyết bằng cách chỉ đợi `first.isDone()` rồi đọc tiếp mà bỏ qua race trong code đa luồng; cần thiết kế **hàng đợi thao tác đọc/ghi** hoặc serial executor cho mỗi connection. Callback chuỗi (read tiếp từ `completed` của read trước) là cách trực quan để giữ một operation mỗi chiều.

Với server, `AsynchronousServerSocketChannel` tương tự chỉ cho phép **một accept pending tại thời điểm**. Dùng callback accept để đăng ký lượt tiếp theo rồi giao client vào xử lý, không mở bừa nhiều accept pending trên cùng channel.

## 9. Timeout: Future.get khác timeout I/O thật

Có hai kiểu timeout cần tách rõ:

| Kiểu | API | Khi hết hạn |
| --- | --- | --- |
| **Thời gian thread chờ kết quả** | `future.get(3, SECONDS)` | Ném `TimeoutException` cho thread đang chờ; operation không tự động hủy |
| **Thời hạn của I/O do channel quản lý** | `channel.read(buffer, 3, SECONDS, attachment, handler)` hoặc overload write tương ứng | Thao tác hoàn thành thất bại qua `failed(InterruptedByTimeoutException, ...)` theo hợp đồng API |

Một fragment callback I/O timeout:

~~~java
// Fragment cho AsynchronousSocketChannel đã kết nối.
ByteBuffer input = ByteBuffer.allocate(2048);

channel.read(input, 3, TimeUnit.SECONDS, input,
        new CompletionHandler<Integer, ByteBuffer>() {
    @Override
    public void completed(Integer bytes, ByteBuffer buffer) {
        if (bytes == -1) {
            // EOF.
            return;
        }
        buffer.flip();
        // Xử lý bytes và quyết định read tiếp.
    }

    @Override
    public void failed(Throwable error, ByteBuffer buffer) {
        if (error instanceof InterruptedByTimeoutException) {
            // Channel/buffer có thể ở trạng thái không chắc chắn;
            // tránh tiếp tục sử dụng mù quáng.
        }
        // Đóng/loại bỏ connection theo chính sách ứng dụng.
    }
});
~~~

Với các overload có I/O timeout, Javadoc nói **timeout có thể khiến channel hoặc underlying connection ở trạng thái không nhất quán**. Nếu implementation không thể bảo đảm byte chưa được đọc/ghi, operation tiếp theo của hướng đó có thể ném một runtime exception không định trước. **Trạng thái ByteBuffer của operation timeout là không xác định**; không đọc/flip/reuse nó như thể đã có kết quả thành công.

Đây là điểm cực kỳ quan trọng: `get(timeout)` không tự cancel, còn timeout được đặt **trên operation của channel** có thể thay đổi tình trạng I/O và buffer. Trong cả hai trường hợp, thiết kế sản phẩm cần lifecycle rõ ràng: deadline của request, đóng channel khi bỏ phiên, thông báo lỗi một lần, giải phóng tài nguyên và quyết định retry.

Mọi lời gọi `get(timeout)` chỉ giới hạn **lần đợi đó**. Nếu bạn lặp đọc 1.000 lần, mỗi lần cho 3 giây, tổng request có thể kéo dài hơn 3 giây. Cần **deadline tổng** (ví dụ `System.nanoTime()` cho thời gian còn lại), không reset thời hạn vô hạn mỗi khi đọc được thêm một byte.

## 10. Những khác biệt đáng nhớ giữa Future và CompletionHandler

| Tiêu chí | `Future<V>` | `CompletionHandler<V,A>` |
| --- | --- | --- |
| Nhận kết quả | Người gọi chủ động `get()` | Channel/provider kích hoạt `completed(V,A)` |
| Báo lỗi | `get()` ném `ExecutionException` bao nguyên nhân | `failed(Throwable,A)` nhận nguyên nhân |
| Có chặn thread không? | Khởi tạo async; **`get()` có thể chặn** | Không phải gọi `get()` cho chính operation đó; callback cần tránh tự blocking |
| Context | Biến/closure quanh `Future` | Attachment `A` được truyền xuyên tới callback |
| Chuỗi I/O | Dễ viết vòng tuần tự `get → read → get` | Dễ khởi tạo lượt tiếp trong `completed` |
| Đọc/ghi một phần | Vẫn phải xử lý `ByteBuffer.remaining()` | Vẫn phải xử lý `ByteBuffer.remaining()` |
| Timeout | `get(timeout)` là timeout chờ | Có overload I/O timeout, callback `failed` |
| Điều khiển callback | Chỉ dùng Future không cần callback | Cần thiết kế callback, lỗi, thread group, trạng thái |
| Học và debug | Dễ đọc, stack trace theo luồng đợi | Event-driven, khó hơn khi có nhiều hoạt động đồng thời |
| Mở rộng số connection | Dễ vô tình chiếm nhiều thread do `get` | Dễ giữ số thread chờ thấp hơn nhưng phải quản lý backpressure |

Không có lựa chọn “Future luôn kém hiệu năng” hay “CompletionHandler luôn đúng hơn”. Với một công cụ nhỏ hoặc khi đã có worker pool giới hạn, `Future.get` có thể rất dễ hiểu. Với server nhiều connection, callback thường phù hợp hơn vì không cần một thread chờ từng client. Trong cả hai, thiết kế deadline, framing và giới hạn tài nguyên mới quyết định hệ thống có bền vững hay không.

## 11. Phân biệt CompletionHandler với CompletableFuture

Trong Java có hai khái niệm tên gần nhau:

- `java.nio.channels.CompletionHandler<V,A>` là **interface callback** riêng của API asynchronous channels, có `completed` và `failed`, nhận attachment.
- `java.util.concurrent.CompletableFuture<T>` là một concrete class triển khai `Future<T>` và `CompletionStage<T>`, hỗ trợ chaining như `thenApply/thenCompose/handle/whenComplete`.

JDK 17 **không tự biến tất cả** thao tác NIO.2 nhận `CompletionHandler` thành `CompletableFuture`. Ứng dụng có thể viết adapter: tạo `CompletableFuture<V>`, gọi channel với handler, rồi `complete(value)` hoặc `completeExceptionally(error)`. Phải cân nhắc cancellation, đóng channel và buffer ownership, không tưởng rằng cancel `CompletableFuture` tự động hủy I/O underlying.

Ví dụ **fragment adapter**:

~~~java
// Fragment Java 17+ cho một AsynchronousSocketChannel đã kết nối.
static CompletableFuture<Integer> readAsync(
        AsynchronousSocketChannel channel, ByteBuffer dst) {

    CompletableFuture<Integer> result = new CompletableFuture<>();

    channel.read(dst, null, new CompletionHandler<Integer, Void>() {
        @Override
        public void completed(Integer bytes, Void ignored) {
            result.complete(bytes);
        }

        @Override
        public void failed(Throwable error, Void ignored) {
            result.completeExceptionally(error);
        }
    });
    return result;
}
~~~

Đoạn trên minh họa **kết nối hai API**, không phải mã production hoàn chỉnh: khi khởi tạo `channel.read(...)` ném ngoại lệ tức thời, adapter cần xử lý; khi `CompletableFuture` bị cancel, cần xác định ai chịu trách nhiệm đóng/hủy channel và xử lý buffer còn pending. Vì vậy, việc thêm wrapper không tự giải quyết bài toán quản trị lifecycle.

## 12. Tình huống thực tế và lỗi phổ biến

### 12.1. “Đã dùng AsynchronousSocketChannel, sao server vẫn chậm?”

Có thể vì code gọi `read(...).get()` ngay trong thread phục vụ mỗi kết nối; thread vẫn đứng đợi bytes đến. Cân nhắc tách quản lý I/O thành callback, pipeline, worker thích hợp hoặc dùng mô hình thread phù hợp với quy mô. Quan sát thread dump và số thread chờ trước khi kết luận API bất đồng bộ bị lỗi.

### 12.2. “Callback `completed` chạy, sao response chỉ được gửi một phần?”

`Integer` trong callback ghi là **số byte hoàn tất tại lần đó**, không đảm bảo bằng toàn bộ response. Kiểm tra `buffer.hasRemaining()` và khởi tạo write tiếp sau completion cho tới khi hết data. Nếu peer đóng/reset, kết quả có thể là lỗi. Không sửa buffer trong lúc write còn pending.

### 12.3. “Future.get timeout, có thể reuse ByteBuffer để làm việc khác?”

Không nên khi thao tác cũ vẫn đang pending. Timeout của `get` không hủy I/O; channel còn có thể ghi vào buffer sau khi `get` hết hạn. Phải giải quyết operation cũ hoặc đóng channel/thu hồi vùng nhớ theo chính sách. Với I/O timeout của kênh, tình trạng buffer còn nguy hiểm hơn vì Javadoc nói undefined.

### 12.4. “Callback nhận `-1`; có phải Java gọi failed không?”

Không. `completed(-1, attachment)` biểu thị đọc TCP hoàn tất và thấy EOF. Đó không phải lỗi I/O; điều cần làm là kết thúc/half-close giao thức và giải phóng tài nguyên phù hợp. `failed(Throwable,...)` báo thao tác thất bại.

### 12.5. “Có thể khởi động nhiều đọc bất đồng bộ từ các thread khác nhau không?”

Không nếu trên **cùng AsynchronousSocketChannel** vẫn có read pending; Javadoc sẽ ném `ReadPendingException`. Tương tự `WritePendingException`. Một read và một write có thể cùng pending, nhưng cần bảo vệ thứ tự message và dữ liệu chung.

### 12.6. “CompletionHandler chạy ở thread nào?”

Callback thường được dispatch theo cơ chế của asynchronous channel group/provider. Không được viết code phụ thuộc callback luôn chạy trên thread caller, cũng không được giả định callback chỉ chạy trên một thread duy nhất. Trạng thái chia sẻ cần đồng bộ đúng, ví dụ `AtomicReference`/`ConcurrentHashMap` hoặc thiết kế actor/serial executor. Callback dài và blocking có thể chiếm thread phục vụ completion của group.

### 12.7. “Callback lỗi, nhưng thread chính không thấy exception?”

Nếu exception xảy ra trong callback, nó không tự ném ngược qua stack của thread đã gọi `read(...)` trước đó. Hãy báo lỗi bằng một cơ chế rõ ràng (handler error path, promise, state machine, queue), log ngữ cảnh và thực hiện cleanup. Trong demo, `AtomicReference<Throwable>` và `CountDownLatch` đưa kết quả lỗi về main chỉ để kiểm tra.

### 12.8. “Server accept một lần rồi không nhận client mới?”

Với callback accept, khi một kết nối được accept thành công cần **khởi tạo accept tiếp theo** nếu muốn liên tục phục vụ. Chỉ có một accept outstanding được phép, nên đăng ký lại trong `completed`. Với Future loop, chỉ gọi accept tiếp sau khi nhận kết quả previous accept và chuyển socket đã nhận sang quản lý.

### 12.9. “Đóng kênh có thể hoàn thành callback bằng lỗi?”

Có. Một operation pending có thể kết thúc thất bại khi channel bị đóng, callback `failed` cần xử lý, không biến quá trình shutdown bình thường thành retry vô hạn. Hãy áp dụng một state machine để idempotently close mỗi connection và tránh cập nhật session đã hoàn tất.

## 13. Thiết kế server bất đồng bộ với giới hạn và backpressure

Một server thực tế không chỉ cần nhận kết quả, mà còn cần duy trì an toàn khi có hàng nghìn connection:

1. **Ownership:** mỗi connection sở hữu socket, read buffer, write queue và trạng thái protocol rõ ràng. Không có hai read hoặc hai write outstanding trên một channel.
2. **Framing:** giới hạn kích thước header/body, giải mã theo length prefix/delimiter, bảo vệ trước client gửi dữ liệu cực chậm.
3. **Deadline:** timeout từng I/O và tổng request/session; khi quá hạn phải xác định đóng/hủy, không để Future hoặc callback chờ vô hạn.
4. **Backpressure:** nếu client đọc chậm, giới hạn bytes đang xếp hàng gửi; không cố allocate vô tận rồi `write()` bất đồng bộ không giới hạn.
5. **Threading:** callback ngắn; chuyển CPU/DB/blocking tác vụ dài sang executor khác có giới hạn. Cấu hình `AsynchronousChannelGroup` nếu cần kiểm soát threads và lifecycle.
6. **Failure handling:** xử lý cả lỗi khởi tạo operation đồng bộ, lỗi Future/callback bất đồng bộ, EOF, cancellation và shutdown.
7. **Resource cleanup:** đóng socket/listener, hủy pending phù hợp, giải phóng buffer/pool và hoàn thành request **một lần** ngay cả khi nhiều đường lỗi cạnh tranh.
8. **Observability:** log request ID/peer/operation, pending reads/writes, bytesRead/bytesWritten, latency, timeout và number of live connections; tránh log thông tin nhạy cảm của payload.
9. **Không đồng nhất transport và nghiệp vụ:** số byte write hoàn thành ở TCP local không chứng minh ứng dụng đối tác đã xử lý, cần ACK/response theo giao thức khi yêu cầu.
10. **Test lỗi:** ngoài loopback bình thường cần test đóng peer bất ngờ, chỉ gửi một phần frame, timeout, mạng chậm, callback failure, đồng thời đóng channel, overload và cắt connection giữa chừng.

Nếu đang xử lý hàng nghìn kết nối, callback không tự giảm số socket, file descriptors, buffer memory hoặc CPU cần cho payload. Thành công của mô hình phụ thuộc admission control, queue bounded, deadlines và state machine.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** `Future<Integer> f = channel.read(buf)` đã trả về. Có chắc `buf` đã chứa dữ liệu sẵn đọc không?  
**Đáp án:** Không. I/O có thể chưa hoàn thành; phải đợi Future hoặc kiểm tra kết quả completion theo đúng cách. Không sửa vị trí buffer trong lúc pending.

**Câu 2.** `f.get(2, SECONDS)` ném `TimeoutException`. Thao tác đọc đã bị hủy chưa?  
**Đáp án:** Chưa có bảo đảm. Timeout chỉ áp cho thời gian luồng đợi Future; operation có thể tiếp tục. Cần lifecycle/cancel/close rõ ràng.

**Câu 3.** Với `CompletionHandler<Integer, String>`, `String` có nghĩa gì?  
**Đáp án:** Đây là kiểu attachment: mã request, correlation ID hoặc ngữ cảnh do code truyền khi khởi tạo I/O; không phải nội dung byte tự động được lấy từ socket.

**Câu 4.** Vì sao `completed(-1, attachment)` không được xử lý giống `failed(...)`?  
**Đáp án:** `-1` là EOF của stream TCP, một kết quả đọc thành công về mặt API. `failed` nhận một Throwable do I/O lỗi.

**Câu 5.** Tại sao `completed(writeCount)` cần kiểm tra `src.hasRemaining()`?  
**Đáp án:** TCP write bất đồng bộ có thể hoàn thành một phần dữ liệu. Buffer còn remaining thì phải tiếp tục write sau completion theo giao thức.

**Câu 6.** Có được gọi hai lần `channel.read(...)` liên tiếp mà không đợi lần đầu xong không?  
**Đáp án:** Không. Nếu lần đầu vẫn pending thì lần thứ hai ném `ReadPendingException`. Có thể đồng thời có một read và một write.

**Câu 7.** Sự khác nhau giữa `CompletionHandler` và `CompletableFuture`?  
**Đáp án:** Một bên là callback interface riêng NIO.2 có attachment; một bên là class Future/CompletionStage cho chaining. Có thể bọc handler bằng CompletableFuture, nhưng wrapper không tự xử lý cancel và buffer ownership.

**Câu 8.** Callback I/O timeout được báo bằng gì và vì sao cần cẩn thận với buffer?  
**Đáp án:** Overload timeout của channel có thể gọi `failed(InterruptedByTimeoutException, attachment)`. Javadoc cảnh báo channel/connection có thể không nhất quán và trạng thái buffer operation timeout không xác định.

**Câu 9.** Nếu muốn async accept nhiều client liên tiếp bằng CompletionHandler, khi nào đăng ký accept lần sau?  
**Đáp án:** Khi accept trước hoàn thành, thường ngay trong `completed`. Không để hai accept pending trên cùng listener vì `AcceptPendingException`.

**Câu 10.** Vì sao không gọi xử lý DB lâu ngay trong `completed`?  
**Đáp án:** Callback có thể dùng thread dispatch của group; công việc blocking lâu làm nghẽn callback khác. Chuyển công việc nặng sang executor có giới hạn và thiết kế backpressure.

## Tài liệu chuẩn Java SE 17

- `AsynchronousSocketChannel` — connect/read/write, `Future`, handler, timeouts, read/write pending: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousSocketChannel.html
- `AsynchronousServerSocketChannel` — accept qua Future và handler, `AcceptPendingException`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousServerSocketChannel.html
- `CompletionHandler<V,A>` — `completed` và `failed`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/CompletionHandler.html
- `AsynchronousChannelGroup` — nhóm thread/channel dùng cho I/O async: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousChannelGroup.html
- `AsynchronousFileChannel` — Future/CompletionHandler với vị trí file: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousFileChannel.html
- `ByteBuffer` — position/limit/flip/clear: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html
- `Future` — get, timeout, cancellation và trạng thái: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html
- `CompletableFuture` — API khác `CompletionHandler`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html
