# Phối hợp event loop với nhóm xử lý mà không chặn luồng selector

## 1. Mục tiêu: luồng Selector phục vụ I/O, worker xử lý nghiệp vụ

Khi xây dựng TCP server với Java NIO, một luồng **event loop** có thể theo dõi nhiều `SocketChannel` bằng `Selector`. Lỗi kiến trúc phổ biến là nhận một sự kiện `OP_READ` rồi **xử lý nghiệp vụ lâu ngay trong luồng selector**: truy vấn database blocking, gọi HTTP API đồng bộ, chạy công việc CPU nặng, đợi `Future.get()` hoặc chờ lock. Trong thời gian đó, event loop không kịp xử lý các kết nối khác, dù socket của chúng đã sẵn sàng.

Giải pháp là **tách trách nhiệm**:

- **Event loop (I/O thread):** `select()`, nhận kết nối, đọc những byte đang sẵn sàng, ghi những byte có thể gửi ngay, cập nhật trạng thái `SelectionKey`, quản lý kết nối và tạo ranh giới message.
- **Nhóm worker (thread pool):** xử lý phần nghiệp vụ đủ tốn thời gian để không nên làm trên event loop, chẳng hạn chuyển đổi dữ liệu phức tạp, tính toán, hoặc công việc I/O đồng bộ chưa có API bất đồng bộ phù hợp.
- **Hàng đợi completion + `selector.wakeup()`:** worker chuyển kết quả về cho event loop; **event loop** dùng kết quả để cập nhật buffer phản hồi, `interestOps` và đóng/mở lại việc đọc.

Điểm quan trọng: **không chặn luồng selector** không có nghĩa mọi tác vụ ở worker đều được thực hiện tức thì. Chúng có thể chờ hàng đợi, timeout, thất bại hoặc bị hủy. Vì vậy thiết kế còn cần **giới hạn số tác vụ in-flight**, cơ chế quá tải, lưu trạng thái từng kết nối và chính sách shutdown.

```text
                          TCP clients
                    A       B       C
                    |       |       |
                    v       v       v
              +--------------------------+
              | Event loop / Selector    |
              | OP_ACCEPT, OP_READ       |
              | decode/validate frame    |
              | enqueue work             |
              +------------+-------------+
                           |
                           v  bounded work queue (production)
              +--------------------------+
              | Worker pool              |
              | W1         W2      W3    |
              | business processing      |
              +------------+-------------+
                           |
                  completion/result
                           v
              +--------------------------+
              | Thread-safe completions  |
              +------------+-------------+
                           |
                    selector.wakeup()
                           |
                           v
              +--------------------------+
              | Event loop               |
              | apply result to Conn     |
              | interestOps(OP_WRITE)    |
              | partial channel.write()  |
              +--------------------------+
                           |
                       TCP response
```

Bài tập trọng tâm là **Selector**, nên các ví dụ bên dưới dùng **Java 17+ NIO SocketChannel**. Chương trình chạy hoàn chỉnh có một request trên mỗi connection để dễ theo dõi, sau đó phân tích cách mở rộng sang nhiều request và production.

## 2. Vì sao gọi worker mà vẫn có thể chặn event loop?

Những đoạn code sau **không phải chương trình độc lập**; chúng minh họa lỗi thường gặp trong nhánh xử lý `OP_READ`:

```java
// SAI: làm việc lâu ngay trên I/O thread.
String result = databaseCallBlocking(request);
sendResponse(channel, result);

// VẪN SAI: đẩy đi nhưng lập tức đợi đồng bộ trên I/O thread.
Future<String> future = workerPool.submit(
        () -> databaseCallBlocking(request));
String result2 = future.get(); // chặn event loop tới khi worker xong
```

Trong hai trường hợp, nếu tác vụ tốn 500 ms, selector không kịp xử lý hàng loạt key khác trong 500 ms ấy. Việc thêm nhiều worker không cứu được trường hợp thứ hai vì **thread event loop vẫn bị khóa ở `get()`**.

Sơ đồ đúng là:

```text
Event loop:
  READ frame hoàn chỉnh
  -> chuyển request sang pool (không chờ kết quả)
  -> tạm dừng đọc trên connection đó (nếu yêu cầu xử lý tuần tự)
  -> tiếp tục select các connection khác

Worker:
  xử lý request
  -> đặt kết quả vào ConcurrentLinkedQueue
  -> gọi selector.wakeup()
  -> kết thúc, không gọi channel.write trong demo

Event loop khi thức dậy:
  -> lấy kết quả ra khỏi queue
  -> kiểm tra connection/key còn hợp lệ
  -> đặt response ByteBuffer
  -> đăng ký OP_WRITE
  -> thử ghi; nếu ghi dở thì giữ OP_WRITE cho lần sau
```

Một lỗi tinh vi khác là viết callback chạy trên worker nhưng callback đó vẫn **sở hữu logic I/O, mutate attachment và `SelectionKey.interestOps()`** mà không đồng bộ. Thay vì chia sẻ mutable state phức tạp, ví dụ dùng cách đơn giản: **chỉ event loop sửa trạng thái kết nối**, worker chỉ trả về kết quả bất biến.

## 3. Các API và cơ chế phải nắm rõ

| API/khái niệm | Vai trò thực tế |
| --- | --- |
| `Selector.open()` | Tạo đối tượng theo dõi những channel đã đăng ký |
| `ServerSocketChannel.configureBlocking(false)` | Cho listener hoạt động non-blocking, dùng được với selector |
| `SocketChannel.configureBlocking(false)` | Cho kết nối con hoạt động non-blocking trước khi register |
| `channel.register(selector, OP_READ, attachment)` | Đăng ký interest set và gắn trạng thái kết nối |
| `selector.select()` | Chờ các sự kiện sẵn sàng hoặc tín hiệu wakeup/interrupt/close |
| `selector.selectedKeys()` | Tập các key được báo ready; phải xử lý và gỡ mỗi key khỏi tập sau khi xử lý |
| `SelectionKey.isAcceptable()/isReadable()/isWritable()` | Truy vấn các readiness operation của key đã chọn |
| `key.interestOps(...)` | Điều chỉnh loại sự kiện cần nhận từ lần select tiếp theo; thao tác theo state machine |
| `selector.wakeup()` | Đánh thức một select đang chặn hoặc làm lần select tiếp theo trở về sớm |
| `ExecutorService.execute(...)` | Gửi công việc cho pool; **không đợi kết quả** |
| `ConcurrentLinkedQueue<Runnable>` | Ví dụ hàng đợi thread-safe để worker bàn giao bước xử lý completion cho event loop |

**Readiness không đồng nghĩa I/O sẽ hoàn thành toàn bộ**: `OP_READ` không cam kết sẽ có một request đầy đủ trong một lần `read()`; `OP_WRITE` không có nghĩa một `write()` gửi hết buffer. Socket trong non-blocking mode có thể `read()`/`write()` trả `0`. Cần theo dõi `ByteBuffer.position()`, `limit()`, `remaining()` và trạng thái framing.

**`Selector.wakeup()` không mang theo một kết quả nghiệp vụ.** Nó chỉ tác động đến việc chờ của selector. Kết quả được đưa qua **queue** trước; event loop lấy queue và áp dụng lên connection. Phải bảo đảm thứ tự: **đặt completion vào queue trước, rồi wakeup**.

## 4. Trạng thái per-connection và ownership

Đừng dùng biến global chung cho payload của mọi client. Mỗi `SelectionKey` nên có **attachment** chứa trạng thái riêng, ví dụ:

```java
static final class Connection {
    final ByteArrayOutputStream request = new ByteArrayOutputStream();
    ByteBuffer response;
}
```

Đây là cấu trúc đơn giản của chương trình chạy bên dưới: request gom byte ASCII tới newline; response chứa các byte `OK:...` chưa gửi hết. Trong server thực tế, attachment thường có nhiều trạng thái hơn:

| Nhóm | Ví dụ dữ liệu cần giữ |
| --- | --- |
| Framing | `ByteBuffer header`, độ dài body dự kiến, buffer nhận chưa decode, parser state |
| In-flight | Request ID, số job đang chạy, deadline, trạng thái huỷ |
| Outbound | Queue response, `ByteBuffer` còn `remaining()`, số byte pending |
| Lifecycle | `OPEN`, `PROCESSING`, `WRITE_PENDING`, `CLOSING` |
| An toàn tài nguyên | Giới hạn kích thước frame, số request, lượng byte gửi chờ, token phiên bản/generation |

**Nguyên tắc ownership:** worker không được đọc hoặc mutate trực tiếp một `ByteBuffer`/attachment mà event loop vẫn đang chỉnh sửa, trừ khi có hợp đồng đồng bộ rõ ràng. Cách dễ kiểm chứng là chuyển sang worker một **request bất biến** (ví dụ `String` hoặc bản sao `byte[]` đã hoàn tất), rồi để event loop nhận một **response bất biến**. Worker chỉ cần capture `SelectionKey` để tạo closure completion; nó **không truy vấn hoặc mutate key trên worker**.

Nếu worker giữ một mảng byte trong khi selector tiếp tục `clear()` và đọc gói mới vào cùng mảng, kết quả nghiệp vụ có thể dùng dữ liệu đã bị ghi đè. Muốn tránh copy, phải quản lý ownership/lifetime của buffer rõ ràng; với bài học cơ sở, chụp dữ liệu request đã giải mã thành đối tượng bất biến an toàn hơn.

## 5. Luồng chính của chương trình demo

Protocol tối thiểu:

- Client kết nối TCP tới server qua loopback.
- **Một connection xử lý đúng một request**: client gửi một dòng **ASCII printable** `hello\n`. Giới hạn phần nội dung 64 byte, không có newline trong payload.
- Selector nhận kết nối và dữ liệu non-blocking. Khi thấy byte `\n`, nó đánh dấu request hoàn chỉnh, **tắt `OP_READ` cho connection này bằng `interestOps(0)`**, sau đó gửi request sang pool.
- Worker xử lý yêu cầu: `hello` → `HELLO`, tạo phản hồi `OK:HELLO\n`. Worker đưa một callback vào completion queue và gọi `selector.wakeup()`. Nó **không gọi `channel.write()`**.
- Event loop nhận completion, nếu key còn hợp lệ thì đặt `ByteBuffer` phản hồi và chuyển interest set sang `OP_WRITE`.
- `OP_WRITE` ghi từng phần theo `remaining()`. Khi gửi xong, server đóng kết nối (đúng hợp đồng một request). Client nhận một dòng response.
- Main thread đặt cờ dừng, wakeup event loop và chờ thread kết thúc, rồi shutdown pool.

```text
Client                           Selector thread               Worker thread
  |                                    |                              |
  |-- "hello\n" --------------------->| OP_READ                      |
  |                                    | read+framing                 |
  |                                    | key.interestOps(0)           |
  |                                    | workers.execute(request) --->|
  |                                    |                              | process
  |                                    | tiếp tục select các key khác |
  |                                    |                              | completions.add(result)
  |                                    |<------------ wakeup() -------|
  |                                    | apply result, OP_WRITE       |
  |<-- "OK:HELLO\n" -------------------| partial write if needed      |
  |                                    | close when all bytes written |
```

**Tại sao không chờ `Future.get()` ở selector?** Nếu selector đợi worker, các kết nối khác phải chịu cùng thời gian chờ. Hoàn tất qua callback/queue cho phép selector tiếp tục xử lý những key khác ngay khi đã submit job.

## 6. Ví dụ Java 17+ độc lập và chạy được

**Tên tệp:** `SelectorWorkerDemo.java`.

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.ByteBuffer;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.util.Iterator;
import java.util.Locale;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

public final class SelectorWorkerDemo {
    private static final int MAX_REQUEST = 64;

    static final class Connection {
        final ByteArrayOutputStream request = new ByteArrayOutputStream();
        ByteBuffer response;
    }

    static void close(SelectionKey key) {
        key.cancel();
        try {
            key.channel().close();
        } catch (IOException ignored) {
            // Already closing.
        }
    }

    static void accept(ServerSocketChannel listener, Selector selector)
            throws IOException {
        SocketChannel client = listener.accept();
        if (client == null) {
            return;
        }
        client.configureBlocking(false);
        client.register(selector, SelectionKey.OP_READ, new Connection());
    }

    static void read(SelectionKey key, ExecutorService workers,
            ConcurrentLinkedQueue<Runnable> completions, Selector selector)
            throws IOException {
        SocketChannel channel = (SocketChannel) key.channel();
        Connection state = (Connection) key.attachment();
        ByteBuffer buffer = ByteBuffer.allocate(256);
        int n = channel.read(buffer);
        if (n < 0) {
            close(key);
            return;
        }
        if (n == 0) {
            return;
        }
        buffer.flip();
        while (buffer.hasRemaining()) {
            int b = Byte.toUnsignedInt(buffer.get());
            if (b == '\n') {
                final String request = state.request.toString(
                        StandardCharsets.US_ASCII);
                key.interestOps(0); // Stop read notifications while processing.
                workers.execute(() -> {
                    // Slow/CPU-heavy business work would run here instead.
                    byte[] reply = ("OK:" + request.toUpperCase(Locale.ROOT)
                            + "\n").getBytes(StandardCharsets.US_ASCII);
                    completions.add(() -> {
                        if (key.isValid()) {
                            Connection current = (Connection) key.attachment();
                            current.response = ByteBuffer.wrap(reply);
                            key.interestOps(SelectionKey.OP_WRITE);
                        }
                    });
                    selector.wakeup();
                });
                return; // Protocol allows one request per connection.
            }
            if (b < 32 || b > 126 || state.request.size() >= MAX_REQUEST) {
                close(key);
                return;
            }
            state.request.write(b);
        }
    }

    static void write(SelectionKey key) throws IOException {
        SocketChannel channel = (SocketChannel) key.channel();
        Connection state = (Connection) key.attachment();
        channel.write(state.response);
        if (!state.response.hasRemaining()) {
            close(key); // One response per connection.
        }
    }

    static void loop(Selector selector, ServerSocketChannel listener,
            ExecutorService workers,
            ConcurrentLinkedQueue<Runnable> completions,
            AtomicBoolean running) throws IOException {
        while (running.get()) {
            Runnable completed;
            while ((completed = completions.poll()) != null) {
                completed.run(); // Run selector-key updates only in this thread.
            }
            selector.select();
            while ((completed = completions.poll()) != null) {
                completed.run();
            }
            Iterator<SelectionKey> it = selector.selectedKeys().iterator();
            while (it.hasNext()) {
                SelectionKey key = it.next();
                it.remove();
                if (!key.isValid()) {
                    continue;
                }
                try {
                    if (key.isAcceptable()) {
                        accept(listener, selector);
                    } else {
                        if (key.isReadable()) {
                            read(key, workers, completions, selector);
                        }
                        if (key.isValid() && key.isWritable()) {
                            write(key);
                        }
                    }
                } catch (IOException | RuntimeException ex) {
                    close(key);
                }
            }
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress local = InetAddress.getLoopbackAddress();
        try (Selector selector = Selector.open();
             ServerSocketChannel listener = ServerSocketChannel.open()) {
            listener.configureBlocking(false);
            listener.bind(new InetSocketAddress(local, 0));
            listener.register(selector, SelectionKey.OP_ACCEPT);

            ExecutorService workers = Executors.newFixedThreadPool(2);
            ConcurrentLinkedQueue<Runnable> completions =
                    new ConcurrentLinkedQueue<>();
            AtomicBoolean running = new AtomicBoolean(true);
            AtomicReference<Throwable> error = new AtomicReference<>();
            Thread eventLoop = new Thread(() -> {
                try {
                    loop(selector, listener, workers, completions, running);
                } catch (Throwable ex) {
                    error.set(ex);
                }
            }, "selector-loop");
            eventLoop.start();
            try (Socket client = new Socket(local,
                    ((InetSocketAddress) listener.getLocalAddress()).getPort())) {
                client.setSoTimeout(5000);
                BufferedWriter out = new BufferedWriter(
                        new OutputStreamWriter(client.getOutputStream(),
                                StandardCharsets.US_ASCII));
                BufferedReader in = new BufferedReader(
                        new InputStreamReader(client.getInputStream(),
                                StandardCharsets.US_ASCII));
                out.write("hello\n");
                out.flush();
                System.out.println("client sent: hello");
                String response = in.readLine();
                if (!"OK:HELLO".equals(response)) {
                    throw new IOException("Unexpected response: " + response);
                }
                System.out.println("client received: " + response);
            } finally {
                running.set(false);
                selector.wakeup();
                eventLoop.join(5000);
                workers.shutdownNow();
                if (eventLoop.isAlive()) {
                    throw new IllegalStateException("Loop did not stop");
                }
            }
            if (error.get() != null) {
                throw new IllegalStateException("Selector loop failed", error.get());
            }
            System.out.println("selector loop stopped");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 SelectorWorkerDemo.java
java SelectorWorkerDemo
```

Stdout trong lần chạy thành công:

```text
client sent: hello
client received: OK:HELLO
selector loop stopped
```

**Đọc đúng ví dụ:** việc client nhận `OK:HELLO` chứng minh frame phản hồi đã được truyền qua TCP cho client, chứ không phải chỉ việc pool chạy xong. Code test không in thread name nên không thấy thời gian chạy song song qua stdout; cấu trúc `workers.execute(...)` không đợi và việc completion được xử lý trên event loop là bằng chứng ở **logic code** cho tính tách rời. Có thể quan sát thêm qua debugger, thread dump hoặc mở rộng thử nghiệm với hai client.

**Giới hạn chủ đích của demo:** một dòng ASCII/một connection; những byte sau newline trong cùng lượt read không được xem là request thứ hai; server đóng sau phản hồi. Vì vậy ví dụ **không triển khai HTTP, keep-alive, pipeline, hỗ trợ Unicode hay nhiều frame liên tiếp**, và nó không có cơ chế thời hạn toàn cục trên server. `ByteBuffer.allocate(256)` được tạo cho mỗi read-ready event để đơn giản hóa; sản phẩm thực tế thường giữ/reuse receive buffer per connection, nhưng vẫn phải quản lý ownership cẩn thận.

`Executors.newFixedThreadPool(2)` trong ví dụ có **hàng đợi tác vụ không giới hạn dung lượng cấu hình**; nó chỉ phù hợp minh họa, **không nên bê nguyên vào hệ thống chịu tải không tin cậy**. Mục 9 sẽ thay bằng bounded queue.

## 7. Tại sao `interestOps(0)` chỉ áp dụng cho connection đang xử lý?

Giả sử hai client A và B kết nối đồng thời:

```text
A: READ request A -> submit worker A -> keyA.interestOps(0)
B: keyB vẫn OP_READ -> selector vẫn nhận input B
A: worker A hoàn tất -> completion A -> keyA.interestOps(OP_WRITE)
B: không bị khoá theo kết nối A
```

Chỉ **keyA** tạm dừng nhận thông báo đọc; những key khác vẫn phục vụ bình thường. Cách này phù hợp khi yêu cầu **mỗi connection chỉ có một request đang xử lý**, ví dụ protocol tuần tự. Nếu còn byte trong receive buffer của hệ điều hành, chúng có thể tiếp tục tích tụ: tắt `OP_READ` không xóa dữ liệu, nhưng giới hạn các lần xử lý tại ứng dụng. Với một request/connection như demo, sau khi gửi response server đóng socket.

**Không lạm dụng `interestOps(0)` khi protocol cần full-duplex** (ví dụ server push) hoặc nhiều request in-flight trên cùng một connection: khi đó phải điều khiển đọc/ghi theo quy tắc pipeline, hạn mức và thứ tự riêng, thay vì tắt đọc vô điều kiện. Có thể giữ `OP_READ | OP_WRITE` khi vừa có khả năng đọc vừa có byte chờ gửi, nhưng phải bảo đảm phần đọc không vượt ngân sách xử lý cho connection.

**Bẫy quan trọng:** `key.interestOps(SelectionKey.OP_WRITE)` trong callback **thay thế toàn bộ interest set**. Với protocol nhiều request, điều này có thể vô tình mất `OP_READ`. Khi cần vừa đọc vừa ghi, hãy dùng phép bit OR phù hợp theo state machine và đóng/mở mỗi bit có chủ đích. Trong demo, thay thế là **đúng** vì một connection chỉ có một request, đang chờ ghi phản hồi rồi đóng.

## 8. Worker báo hoàn tất bằng queue + `selector.wakeup()`

Cấu trúc then chốt trong demo:

```java
// Worker thread: chỉ tạo kết quả, không mutate connection/key.
byte[] reply = ("OK:" + request.toUpperCase(Locale.ROOT) + "\n")
        .getBytes(StandardCharsets.US_ASCII);
completions.add(() -> {
    // Closure này CHỈ chạy trên event loop thread.
    if (key.isValid()) {
        Connection state = (Connection) key.attachment();
        state.response = ByteBuffer.wrap(reply);
        key.interestOps(SelectionKey.OP_WRITE);
    }
});
selector.wakeup();
```

*Đây là một mảnh mã từ hàm xử lý và worker trong chương trình chạy; các biến `request`, `completions`, `key`, `selector` phải có trong scope.*

Lý do có đủ hai bước:

1. **Queue** là kênh truyền dữ liệu/command từ worker sang event loop. `ConcurrentLinkedQueue` cho phép nhiều worker thêm completion an toàn.
2. **Wakeup** bảo đảm event loop đang ở `selector.select()` không phải đợi tới khi có thêm network readiness mới kiểm tra completion queue.

Nếu worker **chỉ wakeup mà không enqueue**, event loop không biết phản hồi nào phải ghi. Nếu worker **chỉ enqueue mà không wakeup**, event loop có thể bị kẹt trong `select()` khi không có sự kiện network mới, khiến response trễ vô hạn. Vòng lặp mẫu rút queue **trước và sau** `select()` để xử lý những callback đến sát thời điểm wakeup.

`Selector.wakeup()` được thiết kế để gọi từ thread khác; nó không có nghĩa worker được phép gọi `selectedKeys().clear()` hoặc sửa attachment tùy tiện. Khi một connection bị client đóng trong lúc worker đang xử lý, completion có thể đến muộn. Demo kiểm tra `key.isValid()` và bỏ kết quả nếu key đã bị hủy; bản production còn cần bảo vệ **generation/request ID** để response của yêu cầu cũ không bị gắn nhầm vào trạng thái mới.

## 9. Bounded worker pool và backpressure

Một event loop đọc rất nhanh nhưng worker xử lý chậm có thể **đẩy số lượng job lên vô hạn**. Ví dụ có 10.000 client cùng gửi request; dù chỉ hai worker xử lý, `Executors.newFixedThreadPool(2)` có thể tích tụ nhiều job trong queue. Mỗi job giữ reference tới request, response và key; RAM, độ trễ và thời gian shutdown có thể tăng liên tục.

Trong hệ thống thực, hãy cân nhắc **bounded `ThreadPoolExecutor`**:

```java
// Mảnh cấu hình cho production prototype (cần import các lớp).
ThreadPoolExecutor workers = new ThreadPoolExecutor(
        2, 2,
        0L, TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(128),
        new ThreadPoolExecutor.AbortPolicy());
```

*Đoạn độc lập về ý nghĩa cấu hình, nhưng phải đặt trong lớp có import `java.util.concurrent.ThreadPoolExecutor`, `ArrayBlockingQueue` và `TimeUnit`; cần quản lý vòng đời shutdown.* Khi cả hai worker bận và queue đầy, `execute(...)` có thể ném `RejectedExecutionException`. Event loop **không được vô tư xử lý nghiệp vụ ngay tại chỗ để "cứu" việc từ chối**; làm như vậy sẽ chặn selector trong chính tình huống tải cao.

Một số hướng xử lý khi queue đầy:

- Gửi phản hồi `BUSY`/`429`/`503` theo **giao thức ứng dụng** nếu connection và protocol cho phép, rồi đóng hoặc chờ lượt sau.
- Tạm ngừng `OP_READ` trên một số connection theo ngân sách, nhưng phải có cơ chế **bật đọc lại** khi áp lực giảm. Nếu tắt mà không có đường resume, connection bị kẹt.
- Giới hạn số connection, số job in-flight per connection, tổng pending response bytes và timeout; từ chối thêm request mới khi vượt ngân sách.
- Chỉ dùng `CallerRunsPolicy` khi cố ý chấp nhận caller chạy job. **Không phù hợp mặc định** nếu caller là selector thread: nó sẽ chạy business task đồng bộ và phá vỡ yêu cầu không chặn event loop.

Mỗi loại workload cần cân đối pool: CPU-bound thường bị giới hạn bởi số core; blocking I/O có thể cần nhiều worker hơn nhưng nên dùng client/database API bất đồng bộ khi phù hợp. Không chọn thread count chỉ bằng cách tăng thật lớn: context switching, connection pool/DB limit và contention có thể trở thành nút cổ chai.

**Backpressure là điều khiển tốc độ sinh công việc để không vượt tốc độ tiêu thụ.** Bounded queue cộng cơ chế từ chối/tạm đọc có thể giữ bộ nhớ ổn định; chỉ tăng worker count hoặc tăng `SO_RCVBUF` không giải quyết được logic quá tải lâu dài.

## 10. Xử lý partial read và partial write trên event loop

`SocketChannel` ở non-blocking mode có thể chỉ đọc/ghi được một phần:

```text
OP_READ:
  read() > 0 : thêm byte vào per-connection decoder
  read() == 0: không có byte mới; chờ readiness khác
  read() == -1: EOF; xử lý request chưa hoàn chỉnh rồi đóng

OP_WRITE:
  write(buffer) > 0: buffer.position tăng
  write(buffer) == 0: socket chưa nhận thêm byte; chờ OP_WRITE
  buffer.hasRemaining() == false: response đã được ghi hết vào channel
```

Trong demo, `write(...)` chỉ gọi một lần cho mỗi ready event. Nếu `response.hasRemaining()` vẫn là `true`, `interestOps(OP_WRITE)` được giữ nguyên, nên vòng lặp nhận lần writable tiếp theo và gửi phần còn lại. **Không `rewind()`/`clear()` buffer phản hồi giữa các lần write còn dang dở** vì sẽ gửi trùng dữ liệu hoặc làm mất byte.

Với parser input, demo tích byte tới `\n`, giới hạn 64 byte và từ chối byte không phải ASCII printable. Với frame nhị phân production, nên dùng một state machine:

```text
READ_FIXED_HEADER
    -> đủ length header, validate 0 <= L <= MAX
READ_BODY
    -> tích đủ L byte, có thể qua nhiều read events
SUBMIT_WORK
    -> tạm dừng/giới hạn OP_READ
WAIT_WORKER
    -> completion queue + wakeup
WRITE_RESPONSE
    -> giữ buffer position qua nhiều OP_WRITE events
READY_FOR_NEXT_FRAME or CLOSE
```

**TCP không giữ ranh giới write:** nhiều lời gọi `write()` của client có thể được gom vào một `read()`; một frame có thể đến qua nhiều `read()`. Không coi một sự kiện ready là một message. Nếu client gửi hai frame trong cùng một socket và protocol cho phép, parser cần giữ byte dư sau frame thứ nhất để xử lý frame thứ hai. Demo chủ động **không** triển khai trường hợp này.

## 11. Đảm bảo thứ tự phản hồi và tránh race condition

Khi một connection cho phép nhiều request đồng thời, completion có thể về **khác thứ tự gửi**. Ví dụ:

```text
Request #10 -> worker A xử lý 400 ms
Request #11 -> worker B xử lý  30 ms
Completion #11 có thể tới trước #10
```

Có ba hướng chọn theo giao thức:

1. **Tuần tự per connection:** chỉ một request in-flight; tắt OP_READ đến khi phản hồi xong. Dễ giữ thứ tự, nhưng có head-of-line blocking **trong phạm vi connection đó**.
2. **Cho phép response đảo thứ tự:** mỗi request/response có `requestId`, client ghép response theo ID. Cần đồng bộ gửi frame và định tuyến kết quả.
3. **Xử lý song song nhưng trả theo thứ tự:** giữ buffer kết quả theo sequence ID, chỉ ghi ra những response đã đủ các kết quả trước đó. Có thể tốn bộ nhớ và chịu head-of-line blocking ở chiều trả.

Không cho nhiều worker tự gọi `channel.write()` trên cùng socket mà không có writer queue/serialize. Hai tác vụ có thể xen byte header/body, làm hỏng framing. Sở hữu write state ở event loop giúp giữ một luồng serialize theo connection.

Mỗi job cần chính sách **hủy và hết hạn**: nếu client ngắt kết nối, worker có thể vẫn đang thực hiện một nhiệm vụ vô ích. Callback phải kiểm tra key còn hợp lệ; nếu là thao tác có side effect, việc hủy phía client không đồng nghĩa backend chưa commit. Với transaction quan trọng cần idempotency key, deadline và lưu trạng thái xử lý phù hợp.

## 12. Xử lý exception, kết nối đóng và shutdown

Trong ví dụ, lỗi `IOException` hoặc `RuntimeException` khi xử lý một ready key dẫn đến hủy key và đóng channel. Đây là cách minh họa gọn: connection gặp lỗi không làm toàn bộ event loop chết. **Production** cần thêm xử lý có chủ đích:

- **Worker exception:** bọc phần xử lý trong `try/catch`, biến thành result thành công/thất bại hoặc phản hồi lỗi. Nếu worker ném exception trước khi enqueue completion, key có thể giữ mãi `interestOps(0)`, khiến client bị treo. Phải luôn có đường hoàn tất, báo lỗi hoặc đóng.
- **Queue reject:** bắt `RejectedExecutionException` tại nơi submit. Trả lỗi/từ chối hợp lệ hoặc đóng connection; không chạy tác vụ dài trên selector thread.
- **Channel close trong lúc job chạy:** kết quả hoàn thành muộn phải bị bỏ, không đăng ký lại `OP_WRITE` trên key đã hủy; giải phóng buffer và tham chiếu khi không còn cần.
- **Worker xử lý quá lâu:** timeout/deadline theo request, hủy/cancel khi hợp lệ. `Future.cancel(true)` chỉ yêu cầu ngắt thread; code business và thư viện cần tôn trọng interruption. Không coi cancel là bằng chứng side effect chưa xảy ra.
- **Selector crash:** một ngoại lệ ngoài handler per-key có thể làm event loop dừng hoàn toàn. Ghi nhận lỗi, thông báo giám sát, cleanup toàn bộ kết nối và áp dụng restart policy.
- **Shutdown tuần tự:** ngừng nhận kết nối mới, ngừng tạo job mới, chờ hoặc hủy job theo deadline, xử lý/hủy response pending, wakeup selector, đóng channel/selector rồi shutdown pool. Tránh còn worker callback mutate key sau khi selector đã đóng.
- **Không chặn shutdown vô hạn:** `join()`/`awaitTermination()` ở **main/manager thread** có thể hợp lệ, nhưng không được đưa việc đợi này vào event loop đang phải xử lý I/O.

Code demo dùng `AtomicBoolean running` để yêu cầu dừng, `selector.wakeup()` để thoát khỏi `select()` và `eventLoop.join(5000)` ở **main thread**. `workers.shutdownNow()` dừng pool nhanh phục vụ demo; production nên thiết kế graceful shutdown phù hợp với các job có ảnh hưởng nghiệp vụ.

Một rủi ro khác: callback có thể tự ném exception. Vì closure chạy trên event loop, exception không bắt riêng có thể phá hỏng vòng lặp chính. Hãy giới hạn việc callback làm và có error handling riêng khi triển khai hệ thống lớn.

## 13. Tính công bằng (fairness), latency và observability

Khi hàng nghìn channel ready, event loop phải phân phối thời gian hợp lý:

- Không để một connection độc quyền CPU bằng vòng xử lý vô hạn. Có thể đặt **budget tối đa byte/frame per iteration** và tiếp tục ở vòng kế tiếp.
- Không decode/gzip/parse JSON quá nặng ngay trên event loop; giữ bước parsing cần thiết để xác định frame và hợp lệ cơ bản, còn công việc nặng đưa sang worker.
- Giới hạn kích thước response và số pending outbound byte; nếu client đọc chậm, hàng đợi ghi có thể phình. OP_WRITE chỉ bật khi thực sự có dữ liệu cần gửi.
- Tránh để lỗi của một client ảnh hưởng các connection khác. Không ghi log đồng bộ khối lượng lớn trên selector thread nếu hệ thống logging có thể block.
- Với tác vụ I/O đồng bộ trong worker, nhớ rằng event loop vẫn nonblocking nhưng **worker pool** có thể bị nghẽn; đo queue length và waiting time, không chỉ đo selector loop.

Các chỉ số hữu ích:

| Metric | Giải thích |
| --- | --- |
| `selector loop iteration latency` | Thời gian mỗi vòng select và xử lý ready keys |
| `ready keys processed / iteration` | Số kết nối/sự kiện đã phục vụ |
| `worker queue depth` | Số task đang xếp hàng, dấu hiệu backlog |
| `worker queue wait time` | Thời gian từ submit tới lúc bắt đầu xử lý |
| `worker execution latency` | Thời gian xử lý thực tế |
| `in-flight requests` | Số request chưa hoàn tất ở từng connection/toàn server |
| `pending write bytes` | Tổng số byte response đang chờ `OP_WRITE` |
| `timeouts/rejections/failed completions` | Dấu hiệu quá tải hoặc lỗi luồng trả kết quả |

Nên log `connectionId`, `requestId`, trạng thái đọc/worker/ghi và mốc thời gian; **không log payload nhạy cảm**. Nếu thấy selector loop latency tăng khi pool đầy, kiểm tra có vô tình áp dụng `CallerRunsPolicy`, gọi `Future.get()`, khóa đồng bộ hoặc làm parse nặng trên event loop hay không.

## 14. Các sai lầm phổ biến

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Gọi JDBC/HTTP blocking ngay trong `isReadable()` | Selector bỏ lỡ phục vụ các connection khác | Giao cho worker hoặc dùng async API |
| Submit rồi gọi `Future.get()` ngay | Event loop vẫn block | Completion queue/callback, không đợi trên I/O thread |
| Worker tự mutate attachment/`interestOps` không có ownership | Race và state khó kiểm chứng | Worker gửi completion, event loop áp dụng |
| Enqueue completion nhưng quên `selector.wakeup()` | `select()` có thể chờ vô hạn khi không còn I/O event | Enqueue trước, wakeup sau |
| Wakeup nhưng không có queue/result | Selector không biết phải ghi phản hồi nào | Truyền command/result qua hàng đợi thread-safe |
| Bật `OP_WRITE` liên tục khi không có output | Selector báo writable liên tục, CPU spin | Chỉ bật khi có response pending |
| Gọi `write()` một lần rồi quên `remaining()` | Mất phần response chưa gửi | Giữ `ByteBuffer` và ghi tiếp ở OP_WRITE |
| `read()==0` mà coi là đóng kết nối | Đóng nhầm nonblocking channel | Phân biệt 0, -1 và exception |
| Tắt `OP_READ` và không có đường bật lại | Connection bị "đóng băng" | State machine có resume hoặc write/close |
| Để worker queue không giới hạn dưới tải cao | Tăng RAM và latency | Bounded pool, reject/backpressure |
| Dùng `CallerRunsPolicy` mặc định trên selector | Business task chạy trên selector lúc quá tải | Không chạy tác vụ dài ở caller |
| Worker exception không trả completion | Key chờ vĩnh viễn | Error completion + deadline/cleanup |
| Gửi nhiều frame song song bằng nhiều writer trên một channel | Byte nhiều frame có thể xen lẫn | Một writer/response queue per connection |
| Không validate frame size | Cấp phát quá lớn, DoS | Giới hạn kích thước và thời gian |
| Worker response đến sau khi channel đóng | Stale result hoặc truy cập key không hợp lệ | Check key validity, request generation |
| Một client tạo quá nhiều request in-flight | Worker pool và outbound queue nghẽn | Per-client quota, flow control |

## 15. Bài tập kiểm tra hiểu biết

**Bài 1.** Trong callback `OP_READ`, server submit một job kéo dài 2 giây rồi gọi `future.get()`. Nếu có 2.000 connection khác đang ready, chúng bị ảnh hưởng thế nào? Đổi kiến trúc như thế nào?

**Bài 2.** Worker đã tạo response và đặt vào `ConcurrentLinkedQueue` nhưng quên `selector.wakeup()`. Nếu không có network event mới, client có thể gặp gì?

**Bài 3.** Response dài 10.000 byte; `SocketChannel.write(buffer)` lần đầu chỉ ghi 3.000 byte. Event loop nên làm gì với `buffer.position()` và `OP_WRITE`?

**Bài 4.** Vì sao `interestOps(SelectionKey.OP_WRITE)` có thể đúng khi mỗi connection chỉ có một request, nhưng nguy hiểm khi protocol cho phép tiếp tục đọc request khác?

**Bài 5.** Worker pool có hai thread và queue sức chứa 100; tất cả đều bận. Nếu hệ thống dùng `CallerRunsPolicy` và `workers.execute()` được gọi trực tiếp từ selector thread, điều gì xảy ra khi queue đầy?

**Bài 6.** Client ngắt kết nối trước khi job hoàn tất; worker trả response. Tại sao không được vô điều kiện `key.interestOps(OP_WRITE)`? Ngoài `key.isValid()`, hệ thống nhiều request cần nhận diện thêm thông tin gì?

**Bài 7.** Khi server hỗ trợ hai request A/B song song trên cùng socket và worker B xong trước A, client làm sao biết response nào tương ứng yêu cầu nào? Trường hợp protocol đòi trả theo thứ tự thì server phải quản lý gì?

**Đáp án gợi ý:**

1. Event loop bị block 2 giây, làm các kết nối ready khác trễ. Submit không chờ; worker gửi completion và wakeup selector.
2. Event loop có thể vẫn kẹt trong `select()`; response không được bật `OP_WRITE` kịp thời. Wakeup sau enqueue.
3. Giữ nguyên `position` đã tăng 3.000 byte, giữ interest `OP_WRITE`, tiếp tục ghi `remaining()==7.000` byte khi writable; không rewind.
4. Gán trực tiếp thay toàn bộ interest set, làm mất `OP_READ` nếu cần đọc tiếp. Cần điều khiển bitmask theo state.
5. Policy chạy job trên **caller**, tức selector thread, khiến event loop thực hiện business task đồng bộ và gây head-of-line blocking.
6. Connection/key có thể đã đóng; stale callback phải bị bỏ. Với nhiều request/connection cần request ID/generation, cancellation và lifecycle.
7. Gắn `requestId` vào response; nếu trả theo thứ tự, giữ reorder buffer theo sequence và chỉ phát khi các request trước đã hoàn tất.

## Tài liệu tham khảo chính thức

- [Java SE 17 — Selector](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html): `select()`, `wakeup()` và `selectedKeys()`.
- [Java SE 17 — SelectionKey](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectionKey.html): `interestOps`, ready operations, validity và attachment.
- [Java SE 17 — SocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html): `configureBlocking(false)`, partial read/write.
- [Java SE 17 — ServerSocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ServerSocketChannel.html): non-blocking accept.
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): submit/execute, lifecycle.
- [Java SE 17 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html): bounded queue, reject policies và pool sizing.
- [Java SE 17 — ConcurrentLinkedQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentLinkedQueue.html): queue thread-safe cho completion.
- [Java SE 17 — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): `flip`, `remaining` và partial I/O.
