# Java 7 — Kênh tệp bất đồng bộ: Phân biệt I/O chặn, không chặn và bất đồng bộ

## 1. Mục tiêu và vấn đề thực tế

Trong Java hiện đại, một lời gọi đọc file, đọc socket hoặc chờ dữ liệu có thể được tổ chức theo ba mô hình: **blocking I/O**, **non-blocking I/O** và **asynchronous I/O**. Ba tên gọi có liên quan nhưng không thể dùng thay nhau.

- **Blocking (chặn):** thread gọi một phương thức có thể phải **đợi** tới khi phương thức đọc/ghi trả kết quả hoặc lỗi.
- **Non-blocking (không chặn):** lời gọi đọc/ghi trên channel đã được cấu hình đúng **không đợi dữ liệu sẵn sàng**; nếu chưa đọc/ghi được gì, nó có thể trả **0**, để ứng dụng quay lại khi có readiness.
- **Asynchronous (bất đồng bộ):** ứng dụng **khởi tạo một yêu cầu I/O** rồi nhận **kết quả hoàn thành** về sau, thường qua `Future` hoặc `CompletionHandler`.

Đề bài thuộc chủ đề **Kênh tệp bất đồng bộ** (*Asynchronous File Channels*) trong NIO.2. Tập trung vào sự khác biệt giữa `FileChannel`, non-blocking `SelectableChannel` + `Selector`, và `AsynchronousFileChannel`. Các khái niệm còn áp dụng trên **Java 17+**; không dựa vào cơ chế lỗi thời.

Khi học xong, bạn cần phân biệt được: lời gọi nào giữ thread chờ, API nào chỉ báo sẵn sàng (*readiness*) và API nào báo hoàn thành (*completion*); tại sao `Future.get()` vẫn chặn; lý do `FileChannel` không có `configureBlocking(false)`; vì sao `AsynchronousFileChannel` có thể dùng thread pool; và cách quản lý `ByteBuffer`, timeout, callback, số byte đọc/ghi thực tế.

## 2. Blocking và asynchronous không phải hai đầu của một thang duy nhất

Có **hai câu hỏi** cần đặt ra:

1. **Thread gọi hàm phải chờ không?** Đây là trục *blocking/non-blocking*.
2. **Khi nào và bằng cách nào nhận kết quả hoàn tất?** Đây là trục *synchronous/asynchronous completion*.

Một API bất đồng bộ như `AsynchronousFileChannel.read(...)` cho Future; lời gọi khởi tạo không cần đợi xong file read. Nhưng nếu lập tức gọi `future.get()`, thread caller lại **đang chờ kết quả**. Ngược lại, một `SocketChannel.read(buffer)` với `configureBlocking(false)` có thể trả ngay 0 byte; đó là **kết quả đồng bộ cho chính lần gọi read đó**, không phải callback cho một request đang chạy trong nền.

| Mô hình | Lời gọi read/write | Cách caller nhận kết quả | Ví dụ Java |
| --- | --- | --- | --- |
| Blocking synchronous | Có thể giữ thread đợi I/O | Trả số byte/dữ liệu khi lời gọi kết thúc | `Files.readString`, `FileChannel.read` |
| Non-blocking synchronous | Không chờ dữ liệu xuất hiện, có thể trả 0 hoặc partial | Nhận số byte của từng lần gọi, tự kiểm tra readiness và gọi lại | `SocketChannel.configureBlocking(false)`, `Pipe.SourceChannel` |
| Asynchronous completion | Gửi yêu cầu và nhận một handle/callback | Nhận kết quả về sau qua Future/CompletionHandler | `AsynchronousFileChannel.read/write` |

**Không suy rằng mọi async I/O đều được triển khai trực tiếp bằng tính năng kernel-native không chiếm worker threads.** Java SE 17 quy định `AsynchronousFileChannel` liên kết với một thread pool; kỹ thuật I/O bên dưới tùy provider.

## 3. Ba luồng thời gian: giữ thread, hỏi readiness, nhận completion

### 3.1. Blocking: lời gọi đợi tại chỗ

```text
Thread:
    gọi read() ────────── đợi I/O ──────────► nhận n byte
        │                                        │
        └───────── không đi tiếp ────────────────┘
```

Ví dụ:

```java
try (FileChannel channel =
        FileChannel.open(path, StandardOpenOption.READ)) {
    ByteBuffer dst = ByteBuffer.allocate(4096);
    int count = channel.read(dst);
    // Dòng này chỉ thực thi sau khi read đã trả kết quả.
}
```

Đây là **snippet trong phương thức**, với `Path path`, imports `FileChannel`, `StandardOpenOption`, `ByteBuffer` và xử lý `IOException`. `read` là synchronous file I/O. Không khẳng định nó sẽ luôn chậm: dữ liệu có thể đã nằm trong cache OS.

### 3.2. Non-blocking: chưa sẵn sàng thì trả 0

```text
Thread:
    read() -> 0 byte ──► làm việc khác / chờ readiness
                               │
                               ▼
                         read() -> n byte
```

Với `SelectableChannel` cấu hình non-blocking, thao tác `read` không đợi dữ liệu xuất hiện. Điều này phù hợp khi ứng dụng phải quản lý nhiều socket/pipe channels cùng lúc. Nó đòi hỏi lưu giữ trạng thái còn thiếu, partial I/O và tránh vòng lặp nóng liên tục đọc 0 byte.

### 3.3. Asynchronous: yêu cầu hoàn thành ở thời điểm khác

```text
Thread caller:
    channel.read(buffer, offset) ──► Future/đăng ký callback
           │
           ├──────── caller tiếp tục công việc khác
           │
           └──────── provider xử lý I/O ──► completion
                                             │
                                             ├─ Future có kết quả
                                             └─ handler.completed(...)
```

Điểm khác biệt cốt lõi: **Selector báo có thể thực hiện I/O; AsynchronousFileChannel báo thao tác I/O đã kết thúc**. Readiness không thay read, còn completion không đảm bảo kết quả được xử lý ở chính thread khởi tạo.

## 4. I/O chặn và FileChannel

`java.nio.channels.FileChannel` là channel file **đồng bộ** được sử dụng phổ biến trong ứng dụng Java. Nó hỗ trợ:

- `read(ByteBuffer)` và `write(ByteBuffer)`.
- `read(ByteBuffer, long position)` và `write(ByteBuffer, long position)`.
- `position()`, `size()`, `truncate()`, `force()`.
- `transferTo/transferFrom`, mapping và file locking.

Một positional read như:

```java
int count = fileChannel.read(buffer, 8192L);
```

vẫn **synchronous**, dù có offset 8192. Caller nhận kết quả của chính lời gọi đó. Nó không trả Future và không chấp nhận CompletionHandler.

### 4.1. FileChannel không phải SelectableChannel

`FileChannel` kế thừa `SeekableByteChannel`, **không** phải `SelectableChannel`. Vì vậy không có `configureBlocking(false)` và không đăng ký với `Selector` như `SocketChannel`. Không cố biến regular file thành non-blocking bằng một lời gọi trên `FileChannel`.

**Tác động trong thiết kế:** muốn đọc file theo completion-style, dùng `AsynchronousFileChannel`; muốn multiplex readiness trên các channel có thể chọn, dùng `SocketChannel`, `Pipe.SourceChannel` hoặc những kiểu `SelectableChannel` phù hợp.

### 4.2. FileChannel có phù hợp code mới không?

**Có.** Synchronous I/O không phải công nghệ lỗi thời. Khi chương trình chỉ đọc một số ít file, flow trực tiếp dễ hiểu và hiệu suất đáp ứng yêu cầu, `FileChannel` hoặc `Files.readString` hoàn toàn hợp lý. Đừng đổi code sang callback chỉ vì tưởng async luôn nhanh hơn.

## 5. I/O không chặn và SelectableChannel

Các kiểu `SelectableChannel` thường dùng trên Java 17+:

| Channel | Mục đích |
| --- | --- |
| `SocketChannel` | Kết nối TCP, đọc/ghi dữ liệu |
| `ServerSocketChannel` | Chấp nhận TCP connections |
| `DatagramChannel` | Nhận/gửi datagrams |
| `Pipe.SourceChannel` | Đọc dữ liệu từ một pipe |
| `Pipe.SinkChannel` | Ghi dữ liệu vào pipe |

Một channel mới tạo thường ở blocking mode. Chuyển sang non-blocking:

```java
source.configureBlocking(false);
System.out.println(source.isBlocking()); // false
```

Đây là snippet trong phương thức có `Pipe.SourceChannel source` hợp lệ, xử lý `IOException`.

### 5.1. Trả 0 không có nghĩa EOF

```java
ByteBuffer dst = ByteBuffer.allocate(1024);
int n = source.read(dst);

if (n == 0) {
    // Chưa có byte được chuyển, không coi là kết thúc stream.
} else if (n < 0) {
    // EOF.
} else {
    // Có n byte vừa được chuyển.
}
```

Đây là snippet với `source` đã cấu hình non-blocking. Trong những read APIs như Pipe/SocketChannel, **0** thường là không có byte sẵn sàng, còn **-1** báo EOF. Nhầm 0 với -1 làm mất dữ liệu trên các kết nối còn hoạt động.

### 5.2. Partial write và pending output

```java
int written = socket.write(buffer);
if (buffer.hasRemaining()) {
    // Giữ phần bytes chưa ghi; đợi OP_WRITE khi có điều kiện.
}
```

Đây là snippet có `SocketChannel socket` non-blocking và `ByteBuffer buffer` ở chế độ đọc. Một lần write có thể chuyển 0 hoặc một phần bytes; không được bỏ phần còn lại. Tầng application phải quản lý queue, offset và connection state.

### 5.3. Non-blocking không đồng nghĩa không bao giờ có thread chờ

Một ứng dụng non-blocking thực tế thường dùng `Selector.select()` để **đợi readiness một cách hiệu quả**, thay vì bận rộn thử đọc 0 byte. `Selector.select()` có thể chặn thread; chỉ việc **I/O operation trên channel nonblocking** không phải đợi dữ liệu. Hai tầng này khác nhau.

## 6. Selector: quan sát readiness, không tự thực hiện read

`Selector` cho phép một thread điều phối nhiều `SelectableChannel`:

1. `Selector.open()`.
2. `channel.configureBlocking(false)`.
3. `channel.register(selector, SelectionKey.OP_READ)`.
4. `selector.select()` hoặc `select(timeout)`.
5. Duyệt `selectedKeys()`.
6. Gọi `read/write/accept/connect` đúng loại channel.
7. Quản lý `SelectionKey`, buffer state và đóng resources.

`SelectionKey.isReadable()` nghĩa là channel **được phát hiện có readiness cho READ**. Nó không hứa một record hoàn chỉnh, số byte cố định hoặc đảm bảo read luôn chuyển toàn bộ buffer. Kết quả readiness có thể stale do thao tác khác hoặc thay đổi đồng thời.

### 6.1. Chỉ chờ OP_WRITE khi có dữ liệu

Một lỗi hiệu năng là đăng ký `OP_WRITE` suốt thời gian sống của socket, kể cả khi không cần gửi. Nhiều socket thường ready để ghi, khiến selector loop bị đánh thức liên tục. Chỉ quan tâm OP_WRITE khi có pending output, rồi loại khỏi interest set sau khi đã gửi hết.

### 6.2. Readiness của Selector không phải completion callback

`Selector.select(2000)` đợi **tối đa 2000 mili giây** để phát hiện readiness, trong khi `AsynchronousFileChannel.read(...)` thực hiện yêu cầu đọc và báo completion. Timeout của Selector **không phải timeout cho một yêu cầu file read**; đây là các khái niệm khác nhau.

## 7. AsynchronousFileChannel và completion-based I/O

`AsynchronousFileChannel` là API NIO.2 hiện hành để làm việc bất đồng bộ với file. Một channel có thể được mở bằng:

```java
AsynchronousFileChannel async =
        AsynchronousFileChannel.open(path, StandardOpenOption.READ);
```

Đây là snippet có `Path path`, imports liên quan và xử lý `IOException`. Khi dùng thực tế phải đóng channel bằng try-with-resources.

Những điểm quan trọng:

- Không có **shared current file position**; mọi read/write cung cấp `long position`.
- Có thể có nhiều operation pending.
- Hai operation submit theo thứ tự A rồi B **không chắc hoàn thành theo thứ tự A rồi B**.
- Không dùng cùng `ByteBuffer` cho nhiều operation đang pending cùng lúc.
- Channel gắn với **thread pool** để thực thi/dispatch completion.
- `AsynchronousFileChannel` không phải `SelectableChannel`; không dùng `Selector.register` hoặc `configureBlocking(false)` trên nó.

### 7.1. Overload trả Future

```java
try (AsynchronousFileChannel ch =
        AsynchronousFileChannel.open(path, StandardOpenOption.READ)) {
    ByteBuffer dst = ByteBuffer.allocate(4096);
    Future<Integer> pending = ch.read(dst, 0L);

    // Có thể thực hiện việc khác trong khi I/O pending.
    int n = pending.get(); // Có thể block.
    dst.flip();
    System.out.println("Read bytes: " + n);
}
```

Đây là snippet trong phương thức, cần xử lý `IOException`, `InterruptedException` và `ExecutionException`.

`Future.get()` có thể đợi đến khi file read hoàn tất: API read là **async**, nhưng **call site gọi get lập tức** đã dùng nó theo cách chặn. Do đó không gọi `get()` dài trên UI thread hay event loop.

### 7.2. Overload nhận CompletionHandler

```java
ByteBuffer dst = ByteBuffer.allocate(4096);
ch.read(dst, 0L, "request-01",
        new CompletionHandler<Integer, String>() {
    @Override
    public void completed(Integer count, String requestId) {
        dst.flip();
        System.out.println(requestId + ": " + count);
    }
    @Override
    public void failed(Throwable error, String requestId) {
        System.err.println(requestId + " failed: " + error);
    }
});
```

Đây là snippet trong phương thức với biến `AsynchronousFileChannel ch` hợp lệ; không phải class đầy đủ. Handler được gọi **khi completion**, không có guarantee chạy trên thread khởi tạo. Theo Java SE 17, callback chạy trên một thread của pool gắn với channel, và có trường hợp completed ngay khi thread khởi tạo là thread của pool thì callback có thể được gọi trực tiếp.

### 7.3. Future và CompletionHandler không có kết quả đồng nhất “ngay lập tức”

- Future chứa **trạng thái của một thao tác đang được theo dõi**; `isDone()` cho biết hoàn thành/hủy, không chứng minh success.
- `get()` có thể block; nếu lỗi sẽ có `ExecutionException`.
- CompletionHandler nhận kết quả qua `completed(result, attachment)` hoặc lỗi qua `failed(exc, attachment)`.
- Attachment giúp gắn ID/offset/metadata của request với callback.
- Không giả định callback A chạy trước callback B chỉ vì A submit trước.

### 7.4. AsynchronousFileChannel có phải native kernel AIO trên mọi OS không?

**Không có bảo đảm như vậy.** Javadoc mô tả thread pool liên quan đến async channel, còn hoạt động thực thi I/O bên trong là implementation-specific. Có thể provider dùng workers thực hiện file I/O; không suy ra “không tiêu tốn thread” hoặc “async luôn tối ưu hơn blocking” từ tên class.

## 8. Ví dụ hoàn chỉnh: ba mô hình trong một chương trình

Chương trình dưới đây không cần máy chủ mạng; nó dùng **file tạm** cho synchronous/async file I/O và **Pipe** cho nonblocking I/O. Kết quả dễ kiểm chứng với ASCII.

**Tệp: `IOModelDemo.java`**

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.nio.channels.AsynchronousFileChannel;
import java.nio.channels.CompletionHandler;
import java.nio.channels.FileChannel;
import java.nio.channels.Pipe;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class IOModelDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("io-model-", ".txt");
        try {
            Files.writeString(file, "abcdef", StandardCharsets.UTF_8);

            try (FileChannel channel =
                    FileChannel.open(file, StandardOpenOption.READ)) {
                ByteBuffer buffer = ByteBuffer.allocate(3);
                int count = channel.read(buffer, 0);
                buffer.flip();
                System.out.println("sync bytes = " + count);
                System.out.println("sync data = " +
                        StandardCharsets.UTF_8.decode(buffer));
            }

            Pipe pipe = Pipe.open();
            try (Pipe.SourceChannel source = pipe.source();
                 Pipe.SinkChannel sink = pipe.sink()) {
                source.configureBlocking(false);
                ByteBuffer target = ByteBuffer.allocate(8);
                System.out.println("nonblocking mode = " + !source.isBlocking());
                System.out.println("nonblocking empty = " + source.read(target));
                sink.write(ByteBuffer.wrap(
                        "ping".getBytes(StandardCharsets.UTF_8)));
                int count = source.read(target);
                target.flip();
                System.out.println("nonblocking bytes = " + count);
                System.out.println("nonblocking data = " +
                        StandardCharsets.UTF_8.decode(target));
            }

            try (AsynchronousFileChannel channel =
                    AsynchronousFileChannel.open(file, StandardOpenOption.READ)) {
                ByteBuffer buffer = ByteBuffer.allocate(4);
                Future<Integer> pending = channel.read(buffer, 2);
                int read = pending.get(5, TimeUnit.SECONDS);
                buffer.flip();
                System.out.println("async future bytes = " + read);
                System.out.println("async future data = " +
                        StandardCharsets.UTF_8.decode(buffer));

                ByteBuffer second = ByteBuffer.allocate(2);
                CountDownLatch complete = new CountDownLatch(1);
                AtomicReference<String> callbackData = new AtomicReference<>();
                AtomicReference<Throwable> error = new AtomicReference<>();
                channel.read(second, 0L, null, new CompletionHandler<Integer, Void>() {
                    @Override
                    public void completed(Integer count, Void ignored) {
                        try {
                            second.flip();
                            callbackData.set(StandardCharsets.UTF_8
                                    .decode(second).toString());
                        } catch (Throwable failure) {
                            error.set(failure);
                        } finally {
                            complete.countDown();
                        }
                    }
                    @Override
                    public void failed(Throwable failure, Void ignored) {
                        error.set(failure);
                        complete.countDown();
                    }
                });
                if (!complete.await(5, TimeUnit.SECONDS)) {
                    throw new IOException("Timed out waiting for callback");
                }
                if (error.get() != null) {
                    throw new IOException("Asynchronous read failed", error.get());
                }
                System.out.println("async callback data = " + callbackData.get());
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Lệnh chạy:

```bash
javac --release 17 IOModelDemo.java
java IOModelDemo
```

**Stdout đã kiểm thử trên Windows/JDK 24:**

```text
sync bytes = 3
sync data = abc
nonblocking mode = true
nonblocking empty = 0
nonblocking bytes = 4
nonblocking data = ping
async future bytes = 4
async future data = cdef
async callback data = ab
```

**Phân tích đầu ra:**

- `FileChannel.read(buffer, 0)` là synchronous positional read: nhận 3 byte `abc`.
- `Pipe.SourceChannel` ở nonblocking mode, trước khi writer ghi dữ liệu thì read trả **0**.
- Sau khi sink gửi `ping`, source nhận 4 byte.
- `AsynchronousFileChannel.read(buffer, 2)` đọc từ byte offset 2, có 4 byte `cdef`; `Future.get` lấy kết quả completion.
- Callback đọc 2 byte tại offset 0 thành `ab`. Main dùng `CountDownLatch` để đợi callback **chỉ nhằm tạo stdout xác định cho demo**; trong thiết kế async thực, callback có thể chuyển kết quả tới hàng đợi sự kiện hoặc pipeline khác.

Ví dụ sử dụng `try-with-resources`/`finally` để đóng tài nguyên và xóa file tạm do chính chương trình tạo. Nếu filesystem/provider không hỗ trợ API hoặc bị thiếu quyền, có thể nhận ngoại lệ. Thời gian completion không được bảo đảm trong mọi tình huống; timeout năm giây là giới hạn ví dụ.

## 9. Ví dụ hoàn chỉnh: readiness của Selector

**Tệp: `SelectorReadinessDemo.java`**

```java
import java.nio.ByteBuffer;
import java.nio.channels.Pipe;
import java.nio.channels.Selector;
import java.nio.channels.SelectionKey;

public class SelectorReadinessDemo {
    public static void main(String[] args) throws Exception {
        Pipe pipe = Pipe.open();
        try (Pipe.SourceChannel source = pipe.source();
             Pipe.SinkChannel sink = pipe.sink();
             Selector selector = Selector.open()) {
            source.configureBlocking(false);
            source.register(selector, SelectionKey.OP_READ);
            System.out.println("ready before write = " + selector.selectNow());
            sink.write(ByteBuffer.wrap(new byte[] { 7, 8 }));
            int ready = selector.select(2000);
            System.out.println("ready after write = " + (ready > 0));
            if (ready > 0) {
                for (SelectionKey key : selector.selectedKeys()) {
                    if (key.isValid() && key.isReadable()) {
                        ByteBuffer buffer = ByteBuffer.allocate(8);
                        System.out.println("read after readiness = " +
                                ((Pipe.SourceChannel) key.channel()).read(buffer));
                    }
                }
                selector.selectedKeys().clear();
            }
        }
    }
}
```

Chạy:

```bash
javac --release 17 SelectorReadinessDemo.java
java SelectorReadinessDemo
```

**Stdout thực nghiệm với JDK 24 trên local Pipe:**

```text
ready before write = 0
ready after write = true
read after readiness = 2
```

`selectNow()` đầu tiên không thấy dữ liệu; sau khi sink ghi hai byte, `selector.select(2000)` nhận một readiness indication. **Selector không tự đọc hai byte**; code gọi `source.read(buffer)` mới lấy được chúng.

Kết quả cụ thể có thể phụ thuộc timing/provider, đặc biệt khi có lỗi hoặc channel bị đóng. Đừng lấy một lần thử làm cam kết mọi `select(timeout)` chắc chắn sẽ báo trong đúng thời gian đó. Ý nghĩa quan trọng là **readiness rồi mới gọi read**, không phải **completion của read đã submit**.

## 10. ByteBuffer: kết quả I/O là bytes, không phải String

Cả FileChannel và AsynchronousFileChannel dùng `ByteBuffer`:

- `capacity`: sức chứa buffer.
- `position`: vị trí đang đọc/ghi.
- `limit`: giới hạn được phép đọc/ghi.
- `remaining()`: số byte còn có thể đi qua giữa position và limit.
- `flip()`: chuyển từ nhận dữ liệu vào buffer sang đọc dữ liệu đã nhận.
- `clear()`: reset các vị trí để buffer có thể nhận dữ liệu mới; **không xóa bytes vật lý**, không gọi trong lúc I/O còn pending.

Ví dụ:

```java
ByteBuffer dst = ByteBuffer.allocate(8);
Future<Integer> operation = channel.read(dst, 0L);
int n = operation.get();
if (n > 0) {
    dst.flip();
    String text = StandardCharsets.UTF_8.decode(dst).toString();
}
```

Đây là snippet trong phương thức có `AsynchronousFileChannel channel` đang mở; cần xử lý checked exceptions. Không `flip` trước khi operation hoàn thành. Không giả định kết quả read luôn điền đầy buffer.

### 10.1. Một buffer không dùng chung cho nhiều operation pending

Javadoc `AsynchronousFileChannel` cảnh báo buffers không an toàn cho nhiều concurrent I/O operations. Nếu submit:

```java
channel.read(sameBuffer, 0L);
channel.read(sameBuffer, 4096L);
```

đây là **anti-pattern**: hai operation có thể cùng thay đổi buffer position/data. Sử dụng buffer riêng, hoặc tuần tự hóa operations, rồi chỉ đưa buffer về pool sau khi completion rõ ràng.

### 10.2. Partial read/write và EOF

Một read có thể trả ít byte hơn `remaining()`. Với asynchronous file read, Future/handler trả số byte đọc hoặc **-1** khi offset tại hoặc vượt EOF theo hợp đồng. Với nonblocking selectable read, kết quả **0** khi chưa có byte chuyển được không là EOF. Việc đọc một record đủ 4096 byte có thể phải tiến hành nhiều lần.

Với asynchronous write cũng phải kiểm tra số byte đã ghi; nếu `buffer.hasRemaining()` còn true, cần viết tiếp từ **fileOffset + sốByteĐãGhi**. Không thực hiện hai write dùng cùng source buffer mà chưa đợi completion của thao tác đầu.

### 10.3. Unicode và ranh giới các mẩu byte

Khi đọc file UTF-8 theo chunks, một ký tự tiếng Việt hoặc emoji có thể bị chia qua hai chunks. Không decode mỗi chunk độc lập rồi nối String nếu cắt giữa mã Unicode. Với dữ liệu lớn, dùng `CharsetDecoder` có trạng thái hoặc buffer tích lũy byte hợp lệ trước khi decode.

## 11. Future: lấy kết quả, chờ, timeout và lỗi

Overload:

```java
Future<Integer> pending = channel.read(dst, position);
```

trả handle của operation. Các phương thức:

| Phương thức | Ý nghĩa |
| --- | --- |
| `isDone()` | Đã hoàn thành, lỗi hoặc hủy; không chứng minh thành công |
| `get()` | Đợi cho tới completion; **có thể block** |
| `get(timeout, unit)` | Đợi có giới hạn; có thể ném `TimeoutException` |
| `cancel(mayInterruptIfRunning)` | Yêu cầu hủy Future; không đồng nghĩa mọi I/O cấp OS đã dừng tức thì |
| `isCancelled()` | Future có trạng thái canceled |

Khi `get()` không thành công:

- `ExecutionException`: nguyên nhân thực ở `getCause()`.
- `InterruptedException`: thread chờ bị interrupt; xử lý theo interrupt policy.
- `TimeoutException` (overload timeout): thời gian chờ hết, **không tự động hủy operation**.
- `CancellationException`: Future đã bị hủy.

Không bắt mọi exception rồi mặc định trả 0 byte; sẽ làm lẫn EOF, timeout, lỗi quyền và thiết bị I/O.

### 11.1. Timeout không phải transactional rollback

`future.get(5, SECONDS)` báo timeout có nghĩa **caller chưa nhận completion trong thời gian giới hạn**. I/O vẫn có thể tiếp tục. Nếu cần cancel, đóng resource hoặc retry, phải có quy tắc tránh data duplication/overlapping writes và bảo vệ buffer ownership.

### 11.2. Không gọi get trong event loop

Một pipeline event-driven bị đánh mất lợi ích nếu mỗi callback lại gọi Future.get để đợi file/network. Nếu việc xử lý phải đợi, dùng worker threads hoặc kết hợp callbacks/Futures mà không block thread có trách nhiệm xử lý các sự kiện khác.

## 12. CompletionHandler: callback thực thi ở đâu?

Callback có hai nhánh:

```java
new CompletionHandler<Integer, String>() {
    @Override
    public void completed(Integer bytes, String requestId) {
        // Thao tác hoàn thành; xử lý số byte thực tế.
    }
    @Override
    public void failed(Throwable error, String requestId) {
        // Thao tác thất bại; giải phóng request/báo lỗi.
    }
};
```

Đây là mẫu khai báo **handler object minh họa**, không phải toàn bộ chương trình. Attachment giúp nhận diện request, offset hoặc business context.

Theo Javadoc Java SE 17, handler của AsynchronousFileChannel được chạy bởi thread thuộc **thread pool gắn với channel**. Nó không có guarantee chạy trên caller/UI thread. Nếu operation hoàn tất tức thì và caller đã là một thread thuộc pool, handler có thể được gọi trực tiếp bởi caller.

**Thực hành đúng:** callback phải ngắn gọn, truyền kết quả sang tầng xử lý phù hợp, không truy cập UI không thread-safe, không chặn cả thread pool xử lý completions bằng database/network calls kéo dài, và không bỏ qua `failed(Throwable, A)`.

### 12.1. Thứ tự callback không bảo đảm như thứ tự submit

Hai reads ở offset khác nhau:

```java
channel.read(bufferA, 0L, "A", handler);
channel.read(bufferB, 8192L, "B", handler);
```

được submit A rồi B nhưng **B có thể hoàn thành trước A**. Sắp xếp kết quả theo **offset hoặc sequence number**, không theo thứ tự callback.

### 12.2. Thread-safety của kết quả

Callback có thể chạy trên thread khác. Nếu cập nhật dữ liệu chung, dùng structures/concurrency controls phù hợp như `ConcurrentHashMap`, `AtomicReference`, queue hoặc lock, và thiết kế ownership rõ ràng. Không dùng một `StringBuilder` chia sẻ không đồng bộ giữa nhiều handlers rồi giả định mọi completion tuần tự.

## 13. AsynchronousFileChannel và thread pool

Channel có default pool theo hệ thống hoặc pool do ứng dụng cung cấp.

```java
ExecutorService pool = Executors.newFixedThreadPool(4);
try {
    try (AsynchronousFileChannel channel = AsynchronousFileChannel.open(
            path, Set.of(StandardOpenOption.READ), pool)) {
        ByteBuffer dst = ByteBuffer.allocate(1024);
        Future<Integer> future = channel.read(dst, 0L);
        future.get();
    }
} finally {
    pool.shutdown();
}
```

Đây là snippet trong phương thức Java 17+ với imports `ExecutorService`, `Executors`, `Set`, `StandardOpenOption`, `AsynchronousFileChannel`, `ByteBuffer`, `Future` và xử lý checked exceptions. Channel đóng **trước** khi owner shutdown pool.

**Cảnh báo:** nhiệm vụ mà provider submit tới pool là implementation-specific. Javadoc khuyến nghị executor hỗ trợ hàng đợi unbounded và không chạy task trực tiếp trên caller thread trong `execute()`. Shutdown pool khi channel còn mở dẫn tới hành vi **không được đặc tả**. Dù executor có queue unbounded, ứng dụng vẫn cần **backpressure** để không submit số lượng pending operations/buffers vô hạn.

Pool càng lớn không chắc throughput cao hơn; storage device, OS cache, queue depth, GC, bộ nhớ và scheduling quyết định kết quả.

## 14. Asynchronous file API khác với “chạy blocking task trong CompletableFuture”

Hai đoạn có thể đều trả Future-like result nhưng semantics khác nhau.

**A. API async file của NIO.2:**

```java
Future<Integer> pending = asyncChannel.read(dst, offset);
```

**B. Lập lịch blocking file read sang executor:**

```java
CompletableFuture<String> pending = CompletableFuture.supplyAsync(
        () -> {
            try {
                return Files.readString(path, StandardCharsets.UTF_8);
            } catch (IOException ex) {
                throw new CompletionException(ex);
            }
        }, executor);
```

Đây là snippets trong phương thức. Ở B, người gọi nhận một CompletableFuture bất đồng bộ, nhưng **worker vẫn chạy blocking Files.readString**. Nó không biến `FileChannel` thành nonblocking hoặc đảm bảo có native AIO. Cách B vẫn hữu ích khi cần làm việc ngoài UI/event thread, chỉ phải tính đến số threads bị giữ trong lúc đợi file.

### 14.1. Java 21+ và virtual threads

Virtual threads là tính năng hiện hành từ **Java 21**, không có trong Java 17. Với runtime Java 21+, chúng là lựa chọn để giữ code theo phong cách blocking tuần tự với chi phí scheduling thấp hơn trong nhiều workload. Virtual threads **không biến FileChannel thành SelectableChannel**, không thay đổi ý nghĩa Future/get, và không bảo đảm mọi filesystem call được native nonblocking.

Vì demo nhắm **Java 17+**, không dùng `Thread.ofVirtual()` hoặc API Java 21 trong mã cần biên dịch bằng `--release 17`.

## 15. Vòng đời channel, đóng sớm và hủy operation

Dùng try-with-resources cho `FileChannel`, `AsynchronousFileChannel`, `Pipe.SourceChannel`, `Pipe.SinkChannel` và `Selector`. Với async, cần đặc biệt tránh đóng channel khi request bắt buộc phải hoàn thành vẫn còn pending.

Theo Javadoc `AsynchronousFileChannel`, khi `close()`, các operations outstanding sẽ hoàn tất với lỗi `AsynchronousCloseException`. Không coi `read(...)` đã return là dữ liệu chắc chắn đọc xong. Caller phải đồng bộ vòng đời cho đến khi callback/Future resolved.

Nếu nhiều request dùng chung channel:

- Xác định **owner** chịu trách nhiệm close.
- Borrowers không được tự đóng gây lỗi cho requests khác.
- Giao thức shutdown cần đợi requests hoàn thành hoặc hủy với trạng thái rõ ràng.
- Không tái sử dụng ByteBuffer sau cancel quá sớm.
- Không nhầm `channel.isOpen()` là bảo đảm nó vẫn mở sau khi kiểm tra (thread khác có thể close ngay).

### 15.1. Methods không phải tất cả bất đồng bộ

`AsynchronousFileChannel` cung cấp async read/write/lock variants, nhưng các thao tác như `size()`, `truncate()` và `force(boolean)` không vì tên class mà thành nonblocking Future APIs. Đọc Javadoc từng phương thức; không gán chung một đặc tính timing cho mọi method của class.

### 15.2. File I/O có tính nhất quán và durability riêng

Async không có nghĩa write operations là transaction. Nếu hai writes vào cùng vùng file xảy ra đồng thời, thứ tự kết quả có thể không biết trước. Nếu cần durability, dùng cơ chế force/sync và publish protocol thích hợp; đừng coi callback completed đồng nghĩa toàn bộ giao dịch nghiệp vụ hoặc file đã durable qua mất điện trên mọi hệ thống.

## 16. Error handling theo từng mô hình

| Tình huống | Biểu hiện | Cách xử lý |
| --- | --- | --- |
| Nonblocking source chưa có byte | `read() == 0` | Chờ readiness, không coi EOF |
| EOF ở read API | `read() == -1` | Đóng/xử lý kết thúc hợp đồng input |
| Selector timeout | `select(timeout) == 0` | Không có readiness được báo; không suy toàn hệ thống bất động |
| Future vẫn pending | `isDone() == false` | Không đụng buffer, tiếp tục việc khác hoặc đợi |
| Future I/O lỗi | `ExecutionException` | Xem cause, report/cancel/retry hợp lý |
| Thread chờ bị interrupt | `InterruptedException` | Xử lý interrupt policy, không nuốt lỗi |
| Future chờ quá lâu | `TimeoutException` | Timeout không tự hủy I/O |
| Callback async I/O thất bại | `CompletionHandler.failed` | Hoàn tất request lỗi, cleanup |
| Đóng channel khi pending | `AsynchronousCloseException` | Phân biệt shutdown chủ động với hỏng storage |
| Read với position âm | `IllegalArgumentException` | Validate offset |
| Đọc vào buffer read-only | `IllegalArgumentException`/lỗi API | Dùng buffer writable |
| Channel mở sai options | `NonReadableChannelException` / `NonWritableChannelException` | Mở READ/WRITE chính xác |
| Register channel đang blocking | `IllegalBlockingModeException` | Cấu hình nonblocking trước register |
| Provider không hỗ trợ operation | `UnsupportedOperationException` hoặc IOException | Fallback thiết kế trước, không giả định mọi FileSystem tương đương |

Khi xử lý `InterruptedException` trong worker thread, thường cần khôi phục interrupt flag nếu không chuyển checked exception lên tầng trên:

```java
try {
    int n = future.get();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return;
}
```

Đây là snippet đặt trong phương thức cho phép `return` và có xử lý các checked exceptions khác như `ExecutionException`. Tránh bắt Exception chung rồi trả chuỗi rỗng, vì sẽ che lỗi provider/permission/lifecycle.

## 17. Hiệu năng: nonblocking và async không đồng nghĩa “nhanh hơn”

Khi chọn API, phải biết mình đang tối ưu **latency mỗi request**, **throughput**, **số lượng concurrent operations**, **RAM**, hay **CPU usage**.

**Blocking:** đơn giản, rất phù hợp ít file, request latency thấp/có cache; với nhiều concurrent operations có thể cần nhiều threads hoặc virtual threads (Java 21+).

**Selector nonblocking:** cho phép multiplex nhiều socket/pipe channels trên ít event-loop threads; phù hợp nhiều kết nối idle, nhưng yêu cầu state machine, partial reads/writes và flow control.

**AsynchronousFileChannel:** thích hợp đọc/ghi file theo offsets với completion semantics, nhiều thao tác độc lập; cần giới hạn inflight, executor/buffers và hiểu provider-specific implementation. Không thể đánh giá bằng một bảng “async luôn nhanh hơn”.

### 17.1. Benchmark công bằng

- Cùng số byte thật và loại storage (local SSD, remote share, ZIP provider...).
- Cùng concurrency, buffer size, read chunk size và mức warm-up.
- Không so `Files.readString` cả file với một async read 4 KiB.
- Đo throughput, p95/p99 latency, CPU, GC, số pending buffers và queue length.
- Xét OS page cache — lần đọc thứ hai có thể nhanh hơn không do API.
- Có xử lý I/O errors/timeout như nhau.
- Benchmark trên OS/filesystem mà hệ thống thực sự triển khai.

Dễ mắc sai lầm khi thấy một AsynchronousFileChannel Future hoàn thành nhanh trong demo vài byte rồi suy nó có ưu thế tuyệt đối ở production.

## 18. Tình huống chọn công cụ

| Tình huống | Lựa chọn thường hợp lý | Lý do |
| --- | --- | --- |
| CLI đọc một vài file cấu hình | `Files.readString` | Đơn giản, ít overhead |
| Đọc block file theo offset | `FileChannel` hoặc `AsynchronousFileChannel` | Tùy concurrency và API result mong muốn |
| Nhiều TCP connections idle | `SocketChannel` + `Selector` | Multiplex readiness |
| Đọc nhiều vùng file độc lập | `AsynchronousFileChannel` + Future/handler | Completion theo offset, có thể pending đồng thời |
| Tác vụ file nhỏ cần chạy ngoài UI thread | Worker executor/CompletableFuture | Không làm đứng UI, dù worker dùng blocking I/O |
| Runtime Java 21+ cần code blocking dễ đọc ở nhiều tasks | Virtual threads có thể cân nhắc | Scheduling model khác, benchmark thực tế |
| Cần một transaction file có rollback | Không dựa riêng NIO async | Thiết kế storage/commit/backup protocol riêng |

**Tiêu chí cuối:** tính đúng của chương trình, tải thực, quyền truy cập, provider và yêu cầu latency. Đừng dùng thuật ngữ “async” như một lời hứa vô điều kiện.

## 19. Lỗi phổ biến

1. **“NIO luôn nonblocking.”** Sai; `FileChannel` là synchronous và có thể block.
2. **“AsynchronousFileChannel có configureBlocking(false).”** Sai; nó không phải SelectableChannel.
3. **“FileChannel.read(buffer, offset) là async.”** Sai; positional read vẫn đồng bộ.
4. **“Nonblocking read trả 0 tức là EOF.”** Sai; EOF thường là -1.
5. **“Selector.select() không chặn.”** Sai; bản thân select có thể đợi readiness.
6. **“Selector đã đọc dữ liệu từ socket.”** Sai; caller vẫn phải gọi read/write.
7. **“Một readiness event nghĩa là đủ bytes của một message.”** Sai; cần framing và partial handling.
8. **“Một write nonblocking luôn ghi hết buffer.”** Sai; có thể trả 0/partial.
9. **“Future.get() là không chặn.”** Sai; có thể block.
10. **“Future timeout đồng nghĩa I/O đã dừng.”** Sai; operation có thể vẫn pending.
11. **“CompletionHandler chạy trên thread caller.”** Không đảm bảo; pool xử lý completion.
12. **“Submit A trước B thì callback A đến trước B.”** Không đảm bảo.
13. **“Có thể dùng một ByteBuffer cho hai async reads cùng lúc.”** Sai; race buffer.
14. **“Một async read luôn điền đầy buffer.”** Sai; kiểm tra byte count.
15. **“Đóng async channel không ảnh hưởng pending operations.”** Sai; có thể có AsynchronousCloseException.
16. **“supplyAsync(Files.readString) biến OS file thành nonblocking.”** Sai; worker gọi blocking read.
17. **“Async nghĩa là không cần thread pool.”** Sai; AsynchronousFileChannel gắn với pool.
18. **“Thread pool càng lớn càng nhanh.”** Không chắc, cần benchmark và backpressure.
19. **“OP_WRITE luôn nên được đăng ký.”** Có thể gây busy loop khi socket thường ready.
20. **“Không cần xử lý callback failed.”** Sai; không report lỗi khiến logical requests treo.
21. **“File offsets được chia sẻ như FileChannel.position().”** AsynchronousFileChannel không có current position chung.
22. **“Cancellation chắc chắn rollback file write.”** Sai; không có transaction mặc định.
23. **“Async always native kernel AIO.”** Không có cam kết portable.
24. **“Virtual threads là API Java 17.”** Sai; virtual threads là tính năng từ Java 21.

## 20. Checklist code review

- [ ] Phân biệt rõ blocking vs nonblocking vs async completion trong API đang dùng?
- [ ] Không gọi FileChannel là SelectableChannel?
- [ ] Có tránh `configureBlocking(false)` trên FileChannel?
- [ ] Nonblocking read xử lý 0 riêng với -1?
- [ ] Partial read/write có giữ bytes/offset còn lại?
- [ ] Có dùng Selector hoặc cơ chế readiness phù hợp thay vì busy-spin?
- [ ] Có đặt selectable channel nonblocking trước register?
- [ ] Có tránh interest OP_WRITE thường trực?
- [ ] Có xử lý và xóa selected keys sau mỗi lượt?
- [ ] Future.get có được đặt tránh UI/event-loop thread khi I/O có thể chậm?
- [ ] Đã phân biệt Future timeout và cancellation?
- [ ] Callback failed có report lỗi và hoàn tất request?
- [ ] Có biết callback chạy trên pool, không giả định thread caller?
- [ ] Có buffer ownership riêng khi multiple asynchronous operations pending?
- [ ] Có đợi completion rồi mới flip/clear/reuse ByteBuffer?
- [ ] Offset file có được quản lý qua từng read/write?
- [ ] Callback completion order có được xử lý độc lập submit order?
- [ ] Có giới hạn in-flight requests, RAM và thread pool queue?
- [ ] Có tránh ghi chồng vùng file khi không có coordination?
- [ ] Có close channel/selector/pipe đúng vòng đời?
- [ ] Nếu dùng executor custom, có close channel trước shutdown executor?
- [ ] Có xử lý InterruptedException, ExecutionException, TimeoutException, AsynchronousCloseException?
- [ ] Có xử lý charset/UTF-8 split giữa các chunks?
- [ ] Có benchmark với provider, loại file và tải thực?
- [ ] Có kiểm tra tương thích Java 17 nếu sử dụng API Java 21+ trong runtime khác?

## 21. Câu hỏi tự đánh giá

**1.** I/O chặn là gì? — Lời gọi có thể giữ thread đợi đến lúc thao tác có kết quả.

**2.** I/O không chặn là gì? — Một lời gọi trên channel nonblocking không đợi dữ liệu sẵn sàng; có thể trả 0.

**3.** I/O bất đồng bộ là gì? — Submit thao tác, nhận completion sau qua Future/handler.

**4.** Asynchronous và nonblocking có giống nhau không? — Không; completion khác readiness.

**5.** FileChannel có `configureBlocking(false)` không? — Không.

**6.** SocketChannel có nonblocking mode không? — Có.

**7.** Nonblocking read trả 0 có phải EOF không? — Không.

**8.** Selector thông báo gì? — Readiness của những channel có đăng ký phù hợp.

**9.** Selector có đọc byte giùm ứng dụng không? — Không.

**10.** `Selector.select()` có thể block không? — Có.

**11.** AsynchronousFileChannel đọc file ở vị trí nào? — Offset được truyền trong từng read/write.

**12.** AsynchronousFileChannel có current file position chung không? — Không.

**13.** Future.get có thể block không? — Có.

**14.** Future.get(timeout) timeout có hủy read không? — Không tự động.

**15.** CompletionHandler chạy trên UI thread không? — Không bảo đảm; pool của channel theo hợp đồng.

**16.** Callback completion order có bảo đảm submit order không? — Không.

**17.** Có thể share một ByteBuffer cho hai async reads đang pending không? — Không an toàn.

**18.** Một read có bắt buộc điền đầy buffer không? — Không.

**19.** Vì sao gọi flip sau read? — Để đọc phần bytes vừa đưa vào buffer.

**20.** Khi close async channel, pending requests có thể bị gì? — AsynchronousCloseException.

**21.** supplyAsync(Files.readString) có dùng blocking I/O trong worker không? — Có.

**22.** Async file I/O có bắt buộc sử dụng native kernel AIO không? — Không có cam kết portable như vậy.

**23.** Bài nào phù hợp nhiều TCP sockets idle? — Nonblocking SocketChannel + Selector.

**24.** Bài nào phù hợp đọc block file theo offset có callback? — AsynchronousFileChannel.

**25.** Có phải async luôn nhanh hơn blocking không? — Không; phụ thuộc workload, provider và benchmark.

**26.** Virtual threads có sẵn trong Java 17 không? — Không, từ Java 21.

**27.** Vì sao phải giới hạn pending buffers? — Tránh memory pressure và queue overload.

**28.** Khi nào blocking I/O phù hợp? — Workload đơn giản, concurrency vừa, performance đo được đủ.

## Tài liệu chính thức — Java SE 17

- [AsynchronousFileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousFileChannel.html): positional async read/write, Future, CompletionHandler, pool, close và buffer lifecycle.
- [FileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): synchronous file I/O, positional read/write và file operations.
- [SelectableChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectableChannel.html): blocking/nonblocking mode và Selector registration.
- [Selector](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html): readiness, select/selectNow, selected keys.
- [SelectionKey](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectionKey.html): interest/ready ops và readiness hint.
- [Pipe](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Pipe.html): source/sink channels.
- [CompletionHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/CompletionHandler.html): completed/failed.
- [Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): get, timeout, cancel.
- [ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): position, limit, flip và remaining.
- [java.nio.channels package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/package-summary.html): tổng quan channel I/O trên Java 17.

**Ghi nhớ:** **Blocking** có thể giữ thread đợi; **nonblocking** trả kết quả tạm ngay, có thể là **0 byte** rồi caller dựa vào readiness; **asynchronous** báo **completion** của một yêu cầu đã được khởi tạo. `Selector` không thực hiện read thay cho caller. `AsynchronousFileChannel` dùng Future/CompletionHandler nhưng `Future.get()` vẫn có thể chặn. Phải quản lý buffer, offsets, partial results, pool, timeout và resource lifetime, rồi mới đánh giá hiệu năng trên hệ thống thực tế.