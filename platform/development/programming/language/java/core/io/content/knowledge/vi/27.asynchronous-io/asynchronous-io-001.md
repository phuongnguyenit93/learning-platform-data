# Phân biệt asynchronous I/O với non-blocking I/O trong Java

## 1. Mục tiêu và bối cảnh

Khi thiết kế chương trình I/O hiệu quả, hai thuật ngữ **asynchronous I/O** (*I/O bất đồng bộ*) và **non-blocking I/O** (*I/O không chặn*) thường bị dùng thay cho nhau. Chúng có liên quan nhưng **không đồng nghĩa**.

- **Non-blocking** mô tả hành vi của **lời gọi I/O cụ thể**: khi chưa thể đọc/ghi ngay, thao tác có thể trả về tức thời với tín hiệu “chưa tiến triển”, thay vì chặn thread chờ tài nguyên sẵn sàng. Trong Java NIO, ví dụ là `SocketChannel` hoặc `Pipe.SourceChannel` được cấu hình `configureBlocking(false)`.
- **Asynchronous I/O** mô tả mô hình **khởi phát thao tác rồi nhận thông báo/kết quả khi hoàn tất**: phương thức nộp yêu cầu I/O có thể trả về trước khi thao tác hoàn tất; kết quả đến qua `Future` hoặc `CompletionHandler`. Trong Java NIO.2, ví dụ là `AsynchronousFileChannel` và `AsynchronousSocketChannel`.

Hai mô hình khác nhau ở **thời điểm chương trình biết I/O sẵn sàng** và **thời điểm biết I/O đã hoàn tất**. Cả hai có thể giúp tránh dành một thread chỉ để chờ từng kết nối, nhưng hành vi thực tế và cách tổ chức code khác nhau.

Sau bài, bạn có thể:

1. Phân biệt blocking, non-blocking, synchronous, asynchronous theo **hợp đồng API**.
2. Hiểu `Selector` cùng `SelectionKey.OP_READ/OP_WRITE` trong non-blocking I/O là cơ chế **readiness**, còn `Future/CompletionHandler` trong asynchronous I/O là cơ chế **completion**.
3. Viết ví dụ Java 17+ minh họa non-blocking `Pipe.SourceChannel` và asynchronous `AsynchronousFileChannel`.
4. Hiểu vì sao `Future.get()` có thể chặn, vì sao một callback không bảo đảm toàn bộ ứng dụng không dùng thread chặn I/O, và vì sao readiness chưa chứng minh đã đọc đủ message.
5. Chọn mô hình phù hợp cho server socket, đọc/ghi file, tác vụ batch và thư viện có giao diện blocking.

## 2. Bốn khái niệm thường bị trộn lẫn

**Blocking** là khi thread gọi bị giữ lại cho tới khi điều kiện thao tác xảy ra (hoặc lỗi/timeout/hủy). Ví dụ, `InputStream.read()` thông thường có thể chờ dữ liệu.

**Non-blocking** là khi một lời gọi I/O trả về mà không chờ tài nguyên sẵn sàng. Nếu chưa thể đọc/ghi ở thời điểm đó, kết quả có thể là `0`; ứng dụng phải biết **khi nào thử lại**, thường nhờ `Selector`.

**Synchronous** là khi bên gọi nhận trực tiếp kết quả của thao tác đang thực hiện trước khi tiếp tục phần xử lý cần kết quả đó. Ví dụ `FileChannel.read(buffer)` trả số byte đã đọc khi lời gọi hoàn tất.

**Asynchronous** là khi bên gọi nộp công việc và kết quả được cung cấp qua cơ chế hoàn tất sau đó. Ví dụ `AsynchronousFileChannel.read(buffer, position)` trả `Future<Integer>`, hoặc phiên bản có `CompletionHandler`.

Bốn từ không tạo thành hai cặp đối nghĩa tuyệt đối. Một ứng dụng có thể chạy **I/O blocking trên worker thread** để giao diện gọi ở tầng trên có vẻ bất đồng bộ; thao tác trong worker vẫn là blocking. Một API async trên Java cũng có thể được triển khai bằng cơ chế đồng bộ bên dưới cộng thread pool; hợp đồng async nói về **cách bên gọi giao tiếp với kết quả**, không bảo đảm kernel không bao giờ block bất kỳ thread nào.

| Khía cạnh | Non-blocking I/O | Asynchronous I/O |
| --- | --- | --- |
| Câu hỏi chính | “Có thể đọc/ghi **ngay bây giờ** không?” | “Thao tác tôi đã yêu cầu **hoàn tất** chưa?” |
| Tín hiệu | Readiness của channel; `read/write` có thể trả `0` | Completion: số byte/kết quả hoặc lỗi qua `Future`/handler |
| API Java tiêu biểu | `SocketChannel.configureBlocking(false)`, `Selector` | `AsynchronousSocketChannel`, `AsynchronousFileChannel` |
| Chủ thể tiếp tục thao tác | Ứng dụng gọi `read()/write()` khi được báo ready | Provider thực hiện yêu cầu; ứng dụng nhận kết quả completion |
| Cần event loop? | Thường có selector loop khi nhiều channel | Có thể callback/Future; không bắt buộc một `Selector` |
| Kết quả đọc | Lời gọi `read(ByteBuffer)` trực tiếp trả `int` | `Future<Integer>` hoặc `completed(Integer, attachment)` |
| Dữ liệu chưa đủ | Giữ trạng thái và thử đọc tiếp sau readiness | Nộp thao tác đọc mới sau khi thao tác trước hoàn tất |
| Cách tránh chặn caller | Không gọi thao tác I/O blocking trên event loop | Không gọi `Future.get()` ngay trên event loop |

**Không có API nào hứa luôn đọc đủ một record ứng dụng chỉ trong một lần gọi.** Kết quả byte thực tế, EOF, kích thước buffer, framing và lifecycle vẫn phải được kiểm tra.

## 3. Readiness và completion: sơ đồ trình tự

### 3.1. Non-blocking với `Selector`: readiness trước, thực hiện I/O sau

```text
Thread/event loop             Selector              Socket/Pipe
      |                           |                      |
      | register(OP_READ)         |                      |
      |-------------------------->|                      |
      | select()                  |                      |
      |-------------------------->|                      |
      |      (đợi readiness)      |                      |
      |<------ readable key ------|<--- dữ liệu đến -----|
      | read(buffer)              |                      |
      |------------------------------------------------->|
      |<------------------ int n (n>0, 0 hoặc -1) --------|
      | xử lý n byte; giữ phần record chưa đủ              |
```

`Selector.select()` **có thể chặn thread selector** khi chờ sự kiện; còn bản thân thao tác `read()/write()` của **non-blocking channel** không đợi tài nguyên sẵn sàng theo cách của blocking mode. Vì vậy nói “non-blocking nghĩa là chẳng thread nào bao giờ chờ” cũng sai.

Nếu chương trình không muốn chặn ở `select()`, có `selectNow()` để kiểm tra readiness mà không đợi. Tuy nhiên gọi `selectNow()` liên tục trong vòng lặp bận có thể tiêu hao CPU.

### 3.2. Asynchronous: nộp yêu cầu trước, nhận completion sau

```text
Thread ứng dụng          AsynchronousFileChannel / provider
      |                                 |
      | read(dst, offset)               |
      |-------------------------------->|
      |<---------- Future --------------|
      | tiếp tục công việc khác          |
      |                                 | thực hiện I/O
      |             (khi hoàn tất)      |
      |<----------- completion ---------|
      | get() hoặc completed()/failed()  |
      | xử lý số byte thực sự đọc         |
```

Với overload trả `Future`, `future.get()` sẽ **chờ** nếu kết quả chưa sẵn sàng; gọi nó ngay sau `read` biến luồng xử lý ở caller thành “submit rồi đợi”, dù API I/O vẫn là asynchronous.

Với overload `CompletionHandler`, provider gọi `completed(result, attachment)` hoặc `failed(error, attachment)` khi thao tác hoàn tất. Callback là điểm nhận completion; code callback nên ngắn gọn và không chạy tác vụ CPU nặng chặn thread xử lý completion trong thời gian dài.

### 3.3. Reactor và Proactor là cách gọi mô hình, không phải kiểu Java bắt buộc

**Reactor** là cách tổ chức ứng dụng quanh event readiness (selector) rồi handler tự thực hiện `read/write`. **Proactor** là cách mô tả mô hình nhận completion sau khi hệ thống thực hiện I/O được yêu cầu. Hai thuật ngữ hữu ích để thảo luận kiến trúc, nhưng không nên suy ra một-to-một với mọi chi tiết triển khai JDK/OS hoặc coi tên API là bằng chứng về cơ chế kernel.

## 4. Non-blocking I/O trong Java NIO hoạt động thế nào?

Những kênh như `SocketChannel`, `ServerSocketChannel`, `DatagramChannel` và hai đầu của `Pipe` là `SelectableChannel`. Muốn đăng ký channel với selector:

```java
channel.configureBlocking(false);
SelectionKey key = channel.register(
        selector, SelectionKey.OP_READ);
```

Đây là snippet **không độc lập**, giả định `channel` thuộc `SelectableChannel` phù hợp và `selector` đang mở; cần import cùng xử lý ngoại lệ.

Nếu đăng ký khi channel còn blocking mode, `register` ném `IllegalBlockingModeException`. Nếu dùng operation không được `channel.validOps()` hỗ trợ (ví dụ đăng ký `OP_WRITE` cho `Pipe.SourceChannel`), có thể ném `IllegalArgumentException`.

Các trạng thái điển hình:

- `ReadableByteChannel.read(ByteBuffer)` khi đọc được dữ liệu: trả số byte `n > 0`.
- Đối với non-blocking channel, nếu chưa có byte nào sẵn sàng: **có thể trả `0`**.
- Nếu input đã đến EOF: trả `-1`; điều này **không phải** chỉ là chưa có dữ liệu.
- `WritableByteChannel.write(ByteBuffer)` có thể ghi ít hơn số byte còn trong buffer hoặc trả `0`. Byte chưa ghi vẫn phải được giữ lại để retry khi được báo writable.

`SelectionKey.isReadable()` không bảo đảm `read` sẽ trả đủ byte cho toàn bộ message. Readiness có thể thay đổi giữa thời điểm selector chọn key và thời điểm xử lý I/O, nhất là khi nhiều thread cùng sử dụng channel.

### Một số quy tắc của selector event loop

1. Gọi `configureBlocking(false)` **trước** khi đăng ký.
2. Chỉ đăng ký các bit có trong `validOps()`.
3. Sau `selector.select()`, duyệt `selectedKeys()` và **remove mỗi key đã xử lý khỏi tập selected**. `remove` khác với `key.cancel()`; cancel hủy registration.
4. Kiểm tra `key.isValid()` trước các thao tác trên key có thể đã bị hủy.
5. Với socket, chỉ giữ `OP_WRITE` khi có dữ liệu cần gửi; socket thường writable phần lớn thời gian, đăng ký mãi dễ khiến event loop bận.
6. Nếu thread khác bổ sung công việc trong lúc selector đang đợi, dùng queue và `selector.wakeup()` đúng cách.
7. Đừng xem kết quả `select(timeout) == 0` là EOF; đó là trạng thái chọn, không phải kết quả đọc channel.

## 5. Ví dụ Java 17+ hoàn chỉnh: non-blocking `Pipe` với `Selector`

Để tránh phụ thuộc vào cổng mạng, ví dụ dùng `Pipe` trong cùng process. `Pipe.SourceChannel` được đặt non-blocking và đăng ký `OP_READ`; phía sink ghi thông điệp ASCII `HELLO`. Chương trình gom đủ 5 byte dù mỗi lần `read` có thể nhận một phần.

Lưu tên **`NonBlockingSelectorDemo.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.Pipe;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.charset.StandardCharsets;
import java.util.Iterator;

public class NonBlockingSelectorDemo {
    public static void main(String[] args) throws IOException {
        Pipe pipe = Pipe.open();

        try (Pipe.SourceChannel source = pipe.source();
             Pipe.SinkChannel sink = pipe.sink();
             Selector selector = Selector.open()) {

            source.configureBlocking(false);
            source.register(selector, SelectionKey.OP_READ);

            byte[] expected = "HELLO".getBytes(StandardCharsets.US_ASCII);
            ByteBuffer outbound = ByteBuffer.wrap(expected);

            // Sink vẫn blocking; lượng byte rất nhỏ.
            while (outbound.hasRemaining()) {
                sink.write(outbound);
            }

            ByteArrayOutputStream received = new ByteArrayOutputStream();
            ByteBuffer inbound = ByteBuffer.allocate(8);

            while (received.size() < expected.length) {
                int keys = selector.select(2000);
                if (keys == 0) {
                    throw new IOException("Timeout while waiting for read");
                }

                Iterator<SelectionKey> it =
                        selector.selectedKeys().iterator();

                while (it.hasNext()) {
                    SelectionKey key = it.next();
                    it.remove();

                    if (!key.isValid() || !key.isReadable()) {
                        continue;
                    }

                    inbound.clear();
                    int n = source.read(inbound);
                    if (n == -1) {
                        throw new IOException("Unexpected EOF");
                    }
                    if (n > 0) {
                        inbound.flip();
                        while (inbound.hasRemaining()) {
                            received.write(inbound.get());
                        }
                    }
                }
            }

            System.out.println("bytes=" + received.size());
            System.out.println("text="
                    + received.toString(StandardCharsets.US_ASCII));
        }
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac NonBlockingSelectorDemo.java
java NonBlockingSelectorDemo
```

Stdout khi pipe/selector hoạt động bình thường:

```text
bytes=5
text=HELLO
```

**Điểm quan trọng:**

- `source.configureBlocking(false)` ảnh hưởng lệnh đọc của **source channel**; sink vẫn blocking. Không phải cứ có `Selector` là tất cả channel trong chương trình trở thành non-blocking.
- `selector.select(2000)` có thể **chặn event-loop thread tối đa 2 giây** để chờ readiness. Đây là hành vi dự kiến của selector.
- Khi có `OP_READ`, chương trình **tự gọi** `source.read(inbound)`. Nếu chưa có byte tại chính thời điểm đọc, non-blocking source có thể trả 0.
- Chỉ đưa các byte thực đọc vào `received`. `ByteBuffer.flip()` giới hạn vùng vừa nhận; `clear()` chuẩn bị vòng đọc mới.
- `try-with-resources` đóng hai đầu pipe và selector.
- Ví dụ có hạn timeout để tránh chờ vô hạn; với hệ thống quá tải, `IOException` timeout có thể xuất hiện thay vì stdout thành công.

Đây là ví dụ của **readiness**, không có `Future<Integer>` hay callback completion nào thực hiện thay việc `read` cho ứng dụng.

## 6. Asynchronous I/O trong Java NIO.2

Các API đáng chú ý:

| API | Cách nhận kết quả | Dùng cho |
| --- | --- | --- |
| `AsynchronousFileChannel.read(dst, position)` | `Future<Integer>` | Đọc file theo offset |
| `AsynchronousFileChannel.read(dst, position, attachment, handler)` | `CompletionHandler` | Đọc file theo offset, nhận callback |
| `AsynchronousFileChannel.write(src, position)` | `Future<Integer>` | Ghi file theo offset |
| `AsynchronousFileChannel.write(src, position, attachment, handler)` | `CompletionHandler` | Ghi file và nhận callback |
| `AsynchronousSocketChannel.connect(remote)` | `Future<Void>` hoặc handler | Kết nối TCP |
| `AsynchronousSocketChannel.read(dst)` | `Future<Integer>` hoặc handler | Đọc socket |
| `AsynchronousSocketChannel.write(src)` | `Future<Integer>` hoặc handler | Ghi socket |

`AsynchronousFileChannel` sử dụng **offset rõ ràng**, không phải con trỏ `position()` chia sẻ theo kiểu `FileChannel`. Điều này thuận lợi cho thao tác ở nhiều vị trí nhưng khiến bạn phải quản lý offset chính xác, tránh vùng ghi chồng nhau không được phối hợp.

Theo hợp đồng:

- Nộp yêu cầu I/O bằng `read/write` không có nghĩa dữ liệu đã đọc/ghi hoàn tất.
- Kết quả thành công thường là **số byte thực sự xử lý**; có thể nhỏ hơn kích thước buffer yêu cầu, nên vẫn cần lặp hoặc nộp yêu cầu tiếp.
- Lỗi cần được xử lý qua `ExecutionException` của `Future.get()` hoặc `CompletionHandler.failed(...)`.
- Trong lúc thao tác bất đồng bộ chưa hoàn tất, **không tự ý thay đổi nội dung hay `position/limit` của buffer đang tham gia thao tác**. Tái sử dụng một buffer cho nhiều thao tác pending có thể khiến nội dung/trạng thái không xác định.
- Với một số asynchronous socket channel, nộp thêm một read/write cùng hướng khi operation trước còn pending có thể gây `ReadPendingException` / `WritePendingException`; thiết kế phải theo dõi trạng thái pending.
- Đóng channel trong lúc operation đang pending cần được xử lý bằng cancellation/exception và chính sách cleanup rõ ràng.

`Future.get()` có thể chặn thread gọi; `Future.isDone()` chỉ báo trạng thái hoàn tất, gọi nó liên tục trong một vòng busy-wait cũng có thể tiêu tốn CPU.

## 7. Ví dụ Java 17+ hoàn chỉnh: asynchronous file read với `Future`

Chương trình tạo một file nhỏ, mở `AsynchronousFileChannel`, gửi yêu cầu đọc trước, nhận `Future<Integer>`, sau đó cố ý gọi `get()` để kiểm tra kết quả cho mục đích học API.

Lưu **`AsyncFutureFileDemo.java`**:

```java
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousFileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.concurrent.Future;

public class AsyncFutureFileDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("nio-async-", ".txt");

        try {
            Files.writeString(file, "HELLO", StandardCharsets.US_ASCII);

            try (AsynchronousFileChannel channel =
                    AsynchronousFileChannel.open(
                            file, StandardOpenOption.READ)) {

                ByteBuffer buffer = ByteBuffer.allocate(8);

                Future<Integer> operation = channel.read(buffer, 0);
                System.out.println("request submitted");

                // Cố tình chờ để minh họa Future; caller có thể block.
                int n = operation.get();

                buffer.flip();
                byte[] bytes = new byte[buffer.remaining()];
                buffer.get(bytes);

                System.out.println("bytes=" + n);
                System.out.println("text="
                        + new String(bytes, StandardCharsets.US_ASCII));
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Lệnh:

```bash
javac AsyncFutureFileDemo.java
java AsyncFutureFileDemo
```

Stdout khi file I/O hoàn tất thành công:

```text
request submitted
bytes=5
text=HELLO
```

Giải thích:

1. `channel.read(buffer, 0)` nộp yêu cầu đọc tối đa 8 byte từ offset 0 và **trả về Future**.
2. In `request submitted` chỉ nói rằng lời gọi submit đã trả về; không chứng minh thao tác đã hoàn tất ngay lúc đó.
3. `operation.get()` có thể chặn cho đến khi thao tác hoàn tất; vì vậy đoạn ví dụ này **không phải event-loop không chặn từ đầu tới cuối**.
4. File chỉ chứa 5 byte, `n == 5` khi thành công. `buffer.flip()` chuyển sang đọc những byte đã được channel đưa vào.
5. `try-with-resources` đóng channel, sau đó file tạm được xóa.

Nếu chỉ muốn minh họa tính đúng đắn với file nhỏ, `Future.get()` thuận tiện. Trong GUI hoặc một event loop xử lý hàng nghìn kết nối, gọi `get()` trực tiếp trên thread quan trọng sẽ làm mất lợi thế mà kiến trúc đang tìm kiếm.

## 8. Ví dụ Java 17+ hoàn chỉnh: asynchronous với `CompletionHandler`

Khi không muốn viết code chờ `Future` ngay sau mỗi lời gọi, dùng overload có `CompletionHandler`. Bài học dùng `CountDownLatch` **chỉ để chương trình demo đợi callback xong trước khi in kết quả và đóng file**. Trong ứng dụng server thật, bạn thường nối tiếp tác vụ bằng callback, event queue hoặc thành phần điều phối thay vì chặn một thread để đợi latch.

Lưu **`AsyncCallbackFileDemo.java`**:

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousFileChannel;
import java.nio.channels.CompletionHandler;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class AsyncCallbackFileDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("nio-callback-", ".txt");

        try {
            Files.writeString(file, "JAVA", StandardCharsets.US_ASCII);

            try (AsynchronousFileChannel channel =
                    AsynchronousFileChannel.open(
                            file, StandardOpenOption.READ)) {

                ByteBuffer dst = ByteBuffer.allocate(8);
                CountDownLatch done = new CountDownLatch(1);
                AtomicInteger readCount = new AtomicInteger(-2);
                AtomicReference<Throwable> error = new AtomicReference<>();

                channel.read(dst, 0L, "file-read",
                        new CompletionHandler<Integer, String>() {
                    @Override
                    public void completed(Integer n, String attachment) {
                        readCount.set(n);
                        done.countDown();
                    }

                    @Override
                    public void failed(Throwable exc, String attachment) {
                        error.set(exc);
                        done.countDown();
                    }
                });

                System.out.println("submitted=file-read");

                if (!done.await(10, TimeUnit.SECONDS)) {
                    throw new IOException("Timeout waiting for callback");
                }
                if (error.get() != null) {
                    throw new IOException("Asynchronous read failed",
                            error.get());
                }

                dst.flip();
                byte[] bytes = new byte[dst.remaining()];
                dst.get(bytes);

                System.out.println("bytes=" + readCount.get());
                System.out.println("text="
                        + new String(bytes, StandardCharsets.US_ASCII));
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

```bash
javac AsyncCallbackFileDemo.java
java AsyncCallbackFileDemo
```

Stdout khi completion thành công:

```text
submitted=file-read
bytes=4
text=JAVA
```

Trong handler, `completed(Integer, String)` nhận số byte thực đọc và attachment `"file-read"` đã nộp, còn `failed(Throwable, String)` nhận lỗi. `CountDownLatch` bảo đảm thread in kết quả chỉ tiếp tục sau khi handler xử lý trạng thái. `AtomicInteger` và `AtomicReference` làm nơi chuyển kết quả đơn giản trong demo; khi triển khai thật, thay bằng state và cơ chế điều phối phù hợp.

**Không dùng callback để chứng minh không có thread nào chờ trong hệ thống.** Provider có thể sử dụng pool bên dưới để thực hiện công việc I/O, và code demo có `await` chặn thread chính. Lợi ích là API cho phép người gọi **không buộc phải chờ ở chính lời gọi `read`** và có một con đường xử lý hoàn tất tách biệt.

Một timeout ở `await` không tự đảm bảo I/O đã bị hủy. Trong chương trình thực tế cần chính sách hủy/đóng và điều phối những completion đến muộn; không tự giải phóng hoặc tái sử dụng buffer khi còn thao tác pending.

## 9. Vì sao “async” không đồng nghĩa “không có blocking ở mọi nơi”?

Có ít nhất ba tầng cần xét:

1. **API phía người gọi:** phương thức trả `Future` hoặc nhận handler, nên caller có thể tiếp tục việc khác thay vì đợi toàn bộ I/O.
2. **Cách provider thực thi:** có thể dựa trên I/O bất đồng bộ của hệ điều hành, hoặc có thể dùng thread pool để thực hiện những lời gọi chặn ở tầng dưới. Hợp đồng Java không hứa một chiến lược triển khai duy nhất cho mọi hệ điều hành/filesystem/JVM.
3. **Cách ứng dụng tiêu thụ kết quả:** gọi `Future.get()` ngay, `CountDownLatch.await()`, hoặc thực hiện code chậm trong callback có thể làm thread tương ứng bị giữ lại.

Ví dụ kiến trúc:

```text
Luồng HTTP/event loop
    |
    | submit async file read
    v
Provider / executor: xử lý I/O
    |
    | kết quả/exception
    v
CompletionHandler hoặc Future
    |
    v
Hệ thống phản hồi / scheduler
```

Mô hình trên có thể giữ luồng HTTP rảnh trong lúc I/O đang tiến hành, nhưng không có nghĩa implementation không dùng thread pool. Muốn biết công nghệ thực tế đang dùng, cần kiểm tra tài liệu runtime, profiling và môi trường hoạt động.

Tương tự, đưa `Files.readAllBytes(path)` vào `ExecutorService.submit(...)` khiến **caller không đợi ngay** khi submit, nhưng worker vẫn thực hiện blocking I/O. Đây là **asynchronous orchestration** ở tầng ứng dụng, khác với bảo đảm của một **non-blocking channel**. Hai cách đều có thể hợp lý nếu mục tiêu và hạn mức thread được quản lý tốt.

## 10. File I/O: vì sao `FileChannel` không dùng `Selector`?

`FileChannel` hỗ trợ `ByteBuffer`, `position`, `size`, `map`, `transferTo` và `force`. Nhưng **`FileChannel` không phải `SelectableChannel`**: nó không có `configureBlocking(false)` hay `register(selector, ops)`.

```java
FileChannel file = FileChannel.open(path, StandardOpenOption.READ);

// Hai dòng sau KHÔNG biên dịch:
// file.configureBlocking(false);
// file.register(selector, SelectionKey.OP_READ);
```

Đây là **đoạn minh họa sai có chủ đích**, không phải ví dụ runnable; nó chỉ rõ vì sao không thể dùng `Selector` cho `FileChannel`.

Nếu cần xử lý file mà không buộc thread gọi chờ:

- `AsynchronousFileChannel` cung cấp `Future`/`CompletionHandler`.
- Hoặc chạy file I/O đồng bộ trong worker thread/executor và chuyển kết quả trở lại event loop.
- Nếu mục đích là **nhận thông báo file được sửa**, cân nhắc `WatchService` để quan sát sự kiện thay đổi thư mục; nó không phải selector cho từng byte của file và không thay thế việc đọc file thực tế.

**Không được kết luận** “API mang tên NIO” thì mọi channel đều non-blocking hoặc đều đăng ký selector được. NIO chứa cả giao diện đồng bộ, không chặn theo readiness, và bất đồng bộ theo completion.

## 11. TCP server: chọn mô hình nào?

### 11.1. Non-blocking `SocketChannel` + `Selector`

Server thường có một hoặc vài event-loop thread:

1. Mở `ServerSocketChannel` và gọi `configureBlocking(false)`.
2. `register(selector, OP_ACCEPT)` để quan sát kết nối mới.
3. Khi key acceptable, gọi `accept()`; đối tượng `SocketChannel` mới cũng phải `configureBlocking(false)` rồi đăng ký.
4. Khi readable, gọi `read(ByteBuffer)`, kiểm tra `n > 0 / n == 0 / n == -1`, ghép các chunk thành message.
5. Khi có dữ liệu muốn gửi, thực hiện `write(ByteBuffer)`. Nếu ghi dở, giữ phần còn lại và bật `OP_WRITE`; tắt `OP_WRITE` khi output queue rỗng.
6. Khi key bị cancel hoặc channel đóng, giải phóng tài nguyên đúng vòng đời.

`OP_READ` chỉ thông báo có thể thử đọc. Không coi một key ready là hoàn tất request HTTP hay một frame binary protocol.

### 11.2. `AsynchronousServerSocketChannel` / `AsynchronousSocketChannel`

Các asynchronous socket API dùng `Future` hoặc `CompletionHandler` cho `accept`, `connect`, `read`, `write`. Chương trình không dùng `Selector` trực tiếp để chọn key readiness; nó nhận **completion** của từng thao tác đã nộp.

Ví dụ ý tưởng (snippet):

```java
socket.read(buffer, buffer, new CompletionHandler<Integer, ByteBuffer>() {
    @Override
    public void completed(Integer n, ByteBuffer dst) {
        // n: số byte nhận được, hoặc -1 cho EOF.
        // Sau khi xử lý phần đọc được, nộp tiếp một read nếu cần.
    }

    @Override
    public void failed(Throwable error, ByteBuffer dst) {
        // Ghi nhận lỗi và kết thúc/đóng kết nối theo chính sách.
    }
});
```

Đây là **snippet không độc lập**: `socket` là `AsynchronousSocketChannel` đã kết nối, `buffer` là `ByteBuffer` hợp lệ, cần import và chính sách quản lý vòng đời. Nó minh họa điểm completion, không phải một TCP server hoàn chỉnh.

Cả hai hướng đều cần framing, backpressure, giới hạn bộ nhớ, timeout, cancellation, quan sát lỗi và cleanup. Chọn dựa trên API/framework đã dùng, khả năng vận hành, hiệu năng đo được và độ phức tạp dễ kiểm soát; không có kết luận mọi trường hợp asynchronous luôn nhanh hơn non-blocking.

## 12. Khác biệt quan trọng giữa readiness và completion khi xử lý buffer

| Tình huống | Readiness / non-blocking | Completion / async |
| --- | --- | --- |
| Ai tiến hành `read`? | Handler của ứng dụng gọi `channel.read(buffer)` khi ready | Ứng dụng submit `channel.read(...)`; provider xử lý yêu cầu |
| Lúc nào `position` của buffer thay đổi? | Trong lời gọi `read()` khi có byte | Trong quá trình thao tác async; chỉ nên truy cập/flip khi hoàn tất |
| Không có byte ngay lúc này | `read` có thể trả `0` | Yêu cầu có thể còn pending; kết quả nhận sau |
| Kết thúc input | `read` có thể trả `-1` | Completion mang kết quả `-1` khi EOF |
| Ghi một phần | `write` có thể ghi một phần/0; bật OP_WRITE và retry | Completion mang số byte thực ghi; nộp write tiếp cho phần còn lại |
| Lỗi | Thường ném ngay từ `read/write` | Future thất bại hoặc callback `failed` |
| Buffer có thể tái sử dụng? | Sau lời gọi đồng bộ đã hoàn tất, với trạng thái đúng | Sau **completion** và sau khi ứng dụng tiêu thụ dữ liệu đúng cách |

Một lỗi nghiêm trọng ở async là:

```java
Future<Integer> result = asyncFile.read(buffer, 0);
// Sai nếu I/O còn pending:
buffer.clear();
buffer.put(newData);
```

Đây là **mã sai có chủ đích**, vì buffer đang thuộc thao tác đọc còn pending. Nếu đổi nội dung, position hoặc limit quá sớm, kết quả có thể sai hoặc trạng thái buffer không được xác định. Đợi completion trước khi `flip()`, parse hoặc tái sử dụng buffer.

Ngược lại, trong non-blocking channel, lệnh `read(buffer)` đã trả thì lần gọi ấy hoàn tất; nhưng có thể chỉ mới đọc được một phần message. Chương trình vẫn phải giữ đủ state để nhận những byte còn thiếu trong lần readiness sau.

## 13. Timeout, cancellation và lỗi

### Non-blocking

- `selector.select(timeout)` đợi readiness tối đa trong khoảng chỉ định; kết quả 0 không tự nói channel EOF.
- `selectNow()` không chờ; dùng khi event loop có công việc khác, không lặp busy-wait.
- `selector.wakeup()` làm một lần select đang đợi hoặc lần chọn tiếp theo trở về theo hợp đồng.
- `SelectionKey.cancel()` hủy registration, không tự đóng channel.
- `channel.close()` đóng I/O resource và hủy các registration tương ứng.
- `read()==-1` biểu thị EOF của channel, khác `read()==0` là không có tiến triển trong lần đọc non-blocking.

### Asynchronous

- `Future.get(timeout, unit)` đợi tối đa khoảng được chỉ định và có thể ném `TimeoutException`; timeout **không chứng minh thao tác I/O bên dưới đã bị hủy**.
- `Future.cancel(mayInterruptIfRunning)` yêu cầu hủy theo hợp đồng Future; kết quả/hành vi đối với operation đang chạy phụ thuộc API và trạng thái. Không mặc định tài nguyên được rollback, channel vẫn usable hoặc buffer không còn bị truy cập ngay sau cancel.
- `ExecutionException` đóng gói lỗi nguyên nhân khi đợi `get()`; `InterruptedException` báo thread chờ bị interrupt.
- `CompletionHandler.failed(Throwable, attachment)` nhận lỗi ở dạng callback. Nếu callback tự ném exception, cần hiểu cách provider xử lý log/lỗi; không dùng callback để che giấu thất bại.
- `channel.close()` khi còn operation pending có thể dẫn đến completion thất bại/cancellation theo API; ứng dụng cần quy trình shutdown và bảo vệ buffer/state.

Khi yêu cầu ghi dữ liệu bền vững, cả readiness lẫn completion đều **không tự thay thế `FileChannel.force()`, `FileDescriptor.sync()` hay giao thức commit**. “I/O completed” có nghĩa thao tác I/O trong hợp đồng được hoàn tất, không phải luôn bảo đảm chống mất điện.

## 14. Thread pool, backpressure và giới hạn tài nguyên

Không có mô hình nào miễn phí:

**Với non-blocking selector:**
- Một event loop có thể theo dõi nhiều kết nối, nhưng handler xử lý CPU nặng hoặc gọi I/O blocking trên event loop sẽ làm chậm tất cả kết nối liên quan.
- Việc bỏ qua partial write khiến mất byte; giữ `OP_WRITE` liên tục khi queue trống có thể làm CPU tăng.
- Readiness có thể đến nhanh hơn tốc độ xử lý message, cần giới hạn input buffers, tạm giảm `OP_READ` và thiết kế backpressure.

**Với asynchronous:**
- Dù API trả Future/callback, implementation có thể sử dụng executor; pool quá nhỏ hay hàng đợi không giới hạn đều có thể gây độ trễ.
- Callback không nên thực hiện công việc blocking kéo dài trên thread xử lý completion. Nếu cần, chuyển sang executor riêng với giới hạn công việc.
- Không nộp số lượng vô hạn operation đồng thời trên cùng channel/buffer. Theo dõi in-flight operations, buffer ownership và giới hạn dung lượng.
- Cần cơ chế tín hiệu kết quả về thread điều phối, xử lý ngoại lệ và shutdown có thứ tự.

**Với tác vụ blocking trong worker pool:** event loop có thể tiếp tục làm việc khác, nhưng worker pool vẫn bị giới hạn bởi số thread và tốc độ thiết bị. Mô hình này là một công cụ hữu dụng khi hệ thống có sẵn thư viện blocking và tải vừa phải; nó không biến một `InputStream` thành `SelectableChannel`.

Không có con số tuyệt đối rằng một mô hình luôn nhanh hơn. Đo throughput, latency (đặc biệt p95/p99), số thread, CPU, queue size, số kết nối và thời gian thao tác trên môi trường chạy thật.

## 15. Tình huống lựa chọn trong thực tế

| Yêu cầu | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| Một CLI đọc file nhỏ | `Files.readAllBytes` / `FileChannel` đồng bộ | Code đơn giản, số tác vụ ít |
| HTTP server có nhiều TCP socket và event loop | `SocketChannel` non-blocking + `Selector` hoặc framework tương ứng | Điều phối readiness nhiều channel |
| Muốn đọc/ghi file ở offset mà không buộc caller chờ | `AsynchronousFileChannel` hoặc task trên executor | Có Future/handler hay offload blocking task |
| Ứng dụng xử lý callback completion socket | `AsynchronousSocketChannel` / `AsynchronousServerSocketChannel` | Mô hình callback/Future cho từng operation |
| Dùng thư viện `InputStream` blocking trên UI thread | Chuyển công việc sang worker thread | Giữ UI thread rảnh; I/O ở worker vẫn blocking |
| Theo dõi file log bị cập nhật | `WatchService` kết hợp đọc file thực tế | Sự kiện filesystem khác readiness của socket |
| Nhiều file ghi cần durability | I/O phù hợp + `force/sync` và giao thức dữ liệu | Completion/readiness không phải durability |
| Một request cần nhiều dữ liệu chưa đến đủ | Framing + state/buffer phù hợp với mô hình chọn | Cả hai đều có thể nhận dữ liệu từng phần |

Đừng chuyển toàn bộ code sang async chỉ vì mọi I/O đều có thể chậm. Chọn mô hình dựa trên cách hệ thống xử lý đồng thời, framework đang dùng, yêu cầu về số kết nối, khả năng quản lý state và giới hạn môi trường.

## 16. Lỗi thường gặp

1. **“Async và non-blocking là một.”** Sai: non-blocking trả lời readiness/khả năng thử I/O ngay; async có cơ chế nhận completion sau submit.
2. **“`Selector.select()` không bao giờ block.”** Sai: `select()` có thể chặn thread đợi sự kiện; non-blocking mô tả các lời gọi I/O của channel được cấu hình đúng.
3. **“`isReadable()` nghĩa là đã đọc xong.”** Sai: selector mới chỉ báo readiness, ứng dụng phải gọi `read()` và kiểm tra kết quả.
4. **“AsynchronousFileChannel dùng `Selector`.”** Sai: đây là API completion, không phải `SelectableChannel`.
5. **“`FileChannel` cũng có `configureBlocking(false)`.”** Sai: `FileChannel` không selectable, không có API đó.
6. **“`Future.get()` không block vì Future đến từ async.”** Sai: `get()` có thể đợi cho đến khi operation hoàn tất.
7. **“Callback chứng minh không có OS thread nào bị chặn.”** Sai: implementation có thể dùng thread pool bên dưới.
8. **“Một lần read luôn đủ message.”** Sai trong cả hai mô hình; kết quả có thể ít hơn dự kiến, cần framing.
9. **“Có thể `flip()/clear()` buffer ngay sau submit async.”** Sai khi operation còn pending; phải đợi completion rồi mới tái sử dụng.
10. **“Non-blocking write trả 0 thì cứ retry ngay trong while vô hạn.”** Không tốt: dùng readiness/`OP_WRITE` và backpressure để tránh CPU spin.
11. **“Giữ OP_WRITE mãi để chắc chắn gửi hết.”** Không cần thiết và dễ tạo event liên tục khi socket writable, làm tăng CPU.
12. **“Future timeout là cancel operation.”** Không phải; timeout chỉ giới hạn thời gian chờ của caller.
13. **“Callback hoàn tất là file đã sống sót qua mất điện.”** Không mặc định; durability đòi hỏi hợp đồng đồng bộ storage riêng.
14. **“Tạo task async vô hạn là mở rộng vô hạn.”** Sai: executor, descriptor, buffer và queue đều có giới hạn.
15. **“Read/write trả `0` và `-1` tương đương.”** Sai: 0 là chưa tiến triển trong lời gọi đó, -1 là EOF ở đường đọc.

## 17. Bài tập và câu hỏi tự kiểm tra

1. Giải thích khác nhau giữa “channel đã ready để đọc” và “yêu cầu đọc đã hoàn tất”. Kết quả mỗi trạng thái được nhận qua API Java nào?
2. Vì sao `selector.select()` có thể block nhưng các lần `SocketChannel.read()` trên channel non-blocking không phải chờ dữ liệu sẵn sàng theo blocking mode?
3. Bạn đã đăng ký `OP_READ` cho socket. `isReadable() == true` có đảm bảo `read(buffer)` trả đúng 100 byte đang mong đợi không?
4. Nếu `AsynchronousFileChannel.read(buffer, 0)` trả `Future<Integer>`, điều gì xảy ra nếu gọi `future.get()` ngay trên UI thread?
5. Tại sao có thể có thread pool chạy I/O dưới một API có tên `AsynchronousFileChannel`?
6. Một socket nonblocking chưa thể ghi nên `write(buffer) == 0`. Cần dùng `OP_WRITE` thế nào để retry mà không bận CPU?
7. FileChannel có thể đăng ký với selector không? Nếu muốn đọc file trên một background task, chọn hai phương án nào?
8. Trong `AsyncCallbackFileDemo`, tại sao phải đợi completion trước `dst.flip()` và trước khi đóng channel?
9. Nếu callback trả `completed(20, attachment)` nhưng giao thức yêu cầu 80 byte, chương trình nên làm gì?
10. `Future.get(timeout)` hết thời gian có đồng nghĩa nội dung buffer an toàn để dùng lại ngay không? Cần quản lý lifecycle ra sao?
11. Làm sao phân biệt `read()==0` và `read()==-1` trong nonblocking socket?
12. Thử sửa `NonBlockingSelectorDemo` để sink gửi nhiều phần, quan sát vòng `select`, và giải thích vì sao lượng byte nhận trong mỗi lượt có thể khác.
13. Thử đổi `AsyncFutureFileDemo` sang callback; điều gì khác về cách ứng dụng nhận kết quả và xử lý lỗi?
14. Nếu cần bảo đảm ghi bền vững tới file, asynchronous completion đã là đủ chưa? Vì sao?
15. Bạn chọn kiểu I/O nào cho một server có 50.000 socket và một tác vụ đọc file cấu hình nhỏ không thường xuyên? Giải thích lý do tách công việc file khỏi event loop.

## 18. Tài liệu API Java SE 17

- [`SelectableChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectableChannel.html) — `configureBlocking`, `register` và tính hợp lệ của operation.
- [`Selector`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html) — `select`, `selectedKeys`, `wakeup`.
- [`SelectionKey`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectionKey.html) — `interestOps`, `readyOps` và operation bitmask.
- [`AsynchronousFileChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousFileChannel.html) — file I/O với `Future` và `CompletionHandler`.
- [`AsynchronousSocketChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousSocketChannel.html) — TCP connect/read/write theo completion.
- [`CompletionHandler`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/CompletionHandler.html) — callback thành công/thất bại.

## 19. Ghi nhớ

**Non-blocking I/O** giúp lời gọi I/O không phải chờ dữ liệu/tài nguyên sẵn sàng; ứng dụng dùng `Selector` để được báo **readiness** rồi **tự thử `read()/write()`**. **Asynchronous I/O** cho phép nộp yêu cầu rồi nhận **completion** dưới dạng `Future` hoặc `CompletionHandler`; provider thực hiện yêu cầu I/O theo cơ chế tương ứng.

Hai mô hình vẫn phải giải quyết partial I/O, EOF, buffer ownership, timeout, cancellation, backpressure và tài nguyên. `Future.get()` có thể chặn thread gọi; `Selector.select()` cũng có thể đợi readiness. “Async” không hứa provider không dùng blocking threads, và “non-blocking” không có nghĩa mọi thao tác trong ứng dụng đều không thể chặn. Hãy chọn API theo **tín hiệu cần nhận (ready hay completed)**, loại tài nguyên (file/socket), và cách ứng dụng điều phối công việc.
