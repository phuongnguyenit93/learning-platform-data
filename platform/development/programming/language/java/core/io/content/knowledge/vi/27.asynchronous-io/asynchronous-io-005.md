# AsynchronousChannelGroup và nhóm luồng thực thi trong Java NIO.2

**`AsynchronousChannelGroup`** là cơ chế gom các **asynchronous socket channels** trong Java NIO.2 để dùng chung tài nguyên xử lý I/O và một **nhóm luồng thực thi (thread pool)**. Nhóm quản lý những công việc cần thiết để phát hiện, hoàn tất và chuyển kết quả của thao tác bất đồng bộ đến `CompletionHandler`. Nhờ đó, chương trình có thể khởi tạo thao tác I/O rồi tiếp tục làm việc khác, thay vì bắt buộc giữ một thread chờ mỗi kết nối.

Tuy nhiên, ba khái niệm sau **không đồng nghĩa**:

- *Asynchronous I/O*: thao tác được khởi tạo, kết quả đến về sau qua `Future` hoặc `CompletionHandler`.
- *Thread pool*: nơi các tác vụ phục vụ xử lý I/O và callback được thực thi; **không nhất thiết mỗi kết nối có riêng một thread**.
- *Non-blocking Selector*: mô hình `Selector`/`SocketChannel` khác, nơi ứng dụng chủ động đọc/ghi các channel dựa trên sự kiện sẵn sàng.

Hiểu đúng `AsynchronousChannelGroup` giúp quản lý tài nguyên server, tránh làm nghẽn nhóm luồng khi callback chạy công việc nặng, tránh đóng group khi còn request đang hoạt động, và không nhầm nó với `ExecutorService` của `AsynchronousFileChannel`.

## 1. Vai trò chính của AsynchronousChannelGroup

`AsynchronousChannelGroup` thuộc package `java.nio.channels` (Java 7 trở lên). Đây là lớp trừu tượng đại diện cho **một nhóm các asynchronous channels cùng chia sẻ cơ chế xử lý**. Một group có associated thread pool để:

1. Phục vụ xử lý những sự kiện/tác vụ cần thiết cho các I/O bất đồng bộ trên những channel gắn với group.
2. Dispatch kết quả hoàn thành hoặc thất bại tới `CompletionHandler`.
3. Quản lý vòng đời các tài nguyên I/O, channel và thread pool của group.

**Group không phải một kết nối, không truyền byte, không tự định nghĩa giao thức và không phải một thread riêng.** Mỗi `AsynchronousSocketChannel`/`AsynchronousServerSocketChannel` vẫn đại diện cho endpoint cụ thể và có trạng thái riêng; group là hạ tầng phục vụ nhiều endpoint.

### Hình dung quan hệ

```text
                          AsynchronousChannelGroup
                        +--------------------------+
                        | Thread pool / I/O tasks  |
                        | completion dispatch      |
                        +-------------+------------+
                                      |
            +-------------------------+-------------------------+
            |                         |                         |
   AsynchronousServerSocketChannel   AsynchronousSocketChannel  AsynchronousSocketChannel
          accept(...)                 read/write/connect       read/write/connect
            |                         |                         |
            +------------+------------+------------+------------+
                         |
                 Future / CompletionHandler
                         |
              Kết quả, lỗi, xử lý nghiệp vụ
```

Sơ đồ mô tả **quan hệ logic**, không cam kết OS luôn dùng một thread cố định để xử lý một thao tác cụ thể. Implementation có thể sử dụng cơ chế native asynchronous I/O hoặc mô phỏng bằng các tác vụ nền; Java đưa ra hợp đồng API về completion, không hứa một kiểu kernel I/O đồng nhất trên mọi OS.

## 2. Những channel nào thực sự gắn với group?

| Loại channel | Có thể gắn `AsynchronousChannelGroup`? | Cách liên kết |
| --- | --- | --- |
| `AsynchronousSocketChannel` | **Có** | `AsynchronousSocketChannel.open(group)` hoặc `open()` dùng default group. |
| `AsynchronousServerSocketChannel` | **Có** | `AsynchronousServerSocketChannel.open(group)` hoặc `open()` dùng default group. |
| Socket nhận từ server async | **Có, qua group của server** | `server.accept(...)` trả channel đã kết nối, sử dụng hạ tầng group của server. |
| `AsynchronousFileChannel` | **Không dùng trực tiếp AsynchronousChannelGroup làm tham số** | `open(Path, Set<OpenOption>, ExecutorService, ...)` chỉ định executor; hoặc overload dùng default thread pool. |
| `SocketChannel` / `ServerSocketChannel` đồng bộ | **Không** | Dùng blocking I/O hoặc `Selector`; không phải asynchronous channel group. |
| `FileChannel` | **Không** | Thao tác file channel đồng bộ thông thường, không có liên kết group. |

Đây là khác biệt cần ghi nhớ khi thấy cùng tiền tố `Asynchronous*`. `AsynchronousFileChannel` là asynchronous API nhưng **không có** overload `open(group)`; nó liên kết với `ExecutorService`, không có phương thức `group()`. Java có thể dùng cùng cấu hình default thread pool trong implementation, nhưng không biến file channel thành thành viên trực tiếp của một `AsynchronousChannelGroup` cụ thể do bạn tạo.

Ví dụ gắn hai socket channels với một nhóm:

```java
AsynchronousChannelGroup group =
    AsynchronousChannelGroup.withFixedThreadPool(4,
        runnable -> new Thread(runnable, "nio-aio"));

AsynchronousServerSocketChannel server =
    AsynchronousServerSocketChannel.open(group);
AsynchronousSocketChannel client =
    AsynchronousSocketChannel.open(group);
```

Đây là **đoạn minh họa**, chưa có `bind`/`connect` và chưa giải phóng resource; ứng dụng thật phải đóng cả hai channel rồi shutdown group. Không thể dùng `SocketChannel.open(group)` vì đó là loại channel khác.

## 3. Group được tạo thế nào?

Ba factory method chính:

| Phương thức | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `withFixedThreadPool(int nThreads, ThreadFactory factory)` | Tạo group với số luồng xử lý tối đa `nThreads` cho các nhiệm vụ của group. | `nThreads` phải dương. Thread factory quyết định tên/daemon/priority; đừng đặt quá thấp nếu callback có việc nặng. |
| `withCachedThreadPool(ExecutorService executor, int initialSize)` | Dùng executor có thể tạo thêm thread khi cần; `initialSize` là **gợi ý** cho implementation. | Executor nên tạo thread khi cần, có thể tái sử dụng thread. Giá trị gợi ý không phải cam kết số luồng đang chạy. |
| `withThreadPool(ExecutorService executor)` | Dùng executor do ứng dụng cung cấp cho công việc phục vụ group. | Executor nên hỗ trợ **direct handoff hoặc hàng đợi không giới hạn**; thread gọi `execute` không nên thực thi task trực tiếp. Implementation có thể có ràng buộc bổ sung. |

Cả ba factory có thể ném `IOException` khi provider gặp lỗi tạo group. `withFixedThreadPool` còn ném `IllegalArgumentException` nếu số luồng không hợp lệ.

### Cách dùng fixed group

```java
// Đoạn minh họa: imports phù hợp, gọi trong method throws IOException.
ThreadFactory factory = task -> {
    Thread thread = new Thread(task, "async-io-worker");
    thread.setDaemon(false);
    return thread;
};
AsynchronousChannelGroup group =
        AsynchronousChannelGroup.withFixedThreadPool(4, factory);
```

`ThreadFactory` cho phép gắn tên hữu ích khi theo dõi thread dump. Dùng daemon hay non-daemon phải đi cùng chính sách shutdown rõ ràng; **không dựa vào JVM tự kết thúc để nhả tài nguyên**. Số 4 là số minh họa, không phải công thức chuẩn cho production; cần đo tải và xem callback chiếm thời gian bao lâu.

**Lưu ý sở hữu executor:** Với `withThreadPool` hoặc `withCachedThreadPool`, executor **được dành riêng** cho group. Javadoc nói việc tự `executor.shutdown()` từ nơi khác khi group vẫn hoạt động dẫn đến hành vi **không xác định**; khi group terminate, nó thực hiện orderly shutdown executor. Không nên chia cùng executor với HTTP handler, business scheduler hoặc nhiều group mà không khảo sát hợp đồng. Nếu dùng executor tự tạo, hãy để group quản lý vòng đời của nó.

## 4. Default group và cấu hình trong JVM

Khi không truyền group:

```java
AsynchronousSocketChannel client = AsynchronousSocketChannel.open();
AsynchronousServerSocketChannel server = AsynchronousServerSocketChannel.open();
```

Các channel này gắn với **default asynchronous channel group** cấp JVM. Java tự tạo default group; theo Java SE 21, thread pool của nó tạo thread khi cần. Nếu không cấu hình thread factory cho default group, pooled threads của default group là **daemon threads**.

Hai system properties được Java định nghĩa cho default group:

- `java.nio.channels.DefaultThreadPool.threadFactory`: tên đầy đủ của class `ThreadFactory` cụ thể có thể được nạp và khởi tạo.
- `java.nio.channels.DefaultThreadPool.initialSize`: giá trị nguyên làm tham số `initialSize`, như trong `withCachedThreadPool`; không phải số thread cố định.

Các property này là cấu hình JVM, không phải lệnh đặt số thread cho mọi group do người dùng tạo. Khi phát triển ứng dụng thư viện và chia sẻ default group, khó kiểm soát tác động của callback từ các thành phần khác; khi cần resource isolation cho một subsystem, group riêng có thể hợp lý.

Dùng default group giúp code nhỏ gọn nhưng **không có nghĩa** toàn bộ lifecycle của hệ thống được quản lý giúp: chương trình vẫn phải đóng socket channels và kiểm soát các tác vụ còn chờ. Nếu luồng giữ JVM chạy chỉ là daemon thread, JVM có thể kết thúc khi không còn non-daemon thread; không nên xem sự tồn tại của callback chờ xử lý là một cơ chế giữ process sống.

## 5. CompletionHandler được chạy trên thread nào?

Với channel gắn với `AsynchronousChannelGroup`, Javadoc bảo đảm **completion handler được gọi bởi một trong các pooled threads của group**. Điều này cung cấp danh tính thực thi có thể dự đoán ở mức group, không phải cam kết callback luôn chạy trên “thread A” hay theo thứ tự các request.

Đối với một operation hoàn thành ngay, nếu thread đã khởi tạo operation **đang chính là pooled thread của group**, implementation có thể gọi handler **trực tiếp trên initiating thread đó**, thay vì đi qua hàng đợi. Có thể có giới hạn số lần callback lồng nhau để tránh tràn stack.

Ví dụ:

```java
socket.read(buffer, requestId,
    new CompletionHandler<Integer, String>() {
        @Override
        public void completed(Integer n, String id) {
            // Callback xử lý kết quả; có thể chạy trên thread của group.
        }

        @Override
        public void failed(Throwable error, String id) {
            // Callback được gọi khi operation hoàn tất do lỗi.
        }
    });
```

Đoạn này là **minh họa API**, giả định `socket` đã kết nối, `buffer` hợp lệ và `requestId` được khai báo. `Integer n` là số byte đọc được (`-1` có thể biểu thị EOF), không phải số message ứng dụng. `attachment` mang theo ngữ cảnh do caller cung cấp; nó không được JDK tự sinh ra.

### Thread thực thi callback và thread thực thi business logic

Nên coi callback chạy trên resource pool **cần được trả lại nhanh**:

- **Phù hợp:** kiểm tra kết quả, cập nhật trạng thái buffer, hoàn tất `CompletableFuture`, đặt một công việc vào queue khác, đăng ký lần đọc kế tiếp khi cần.
- **Không phù hợp khi mất nhiều thời gian:** chạy truy vấn DB blocking, gọi HTTP blocking, parse payload khổng lồ, sleep, chờ người dùng, `Future.get()` của công việc cũng cần chính pool đó.
- **Nguy cơ:** một pool chỉ có 2 threads, cả hai callback chặn trong lúc chờ task khác của group → tiến độ xử lý I/O/callback khác có thể bị trì hoãn nặng hoặc deadlock do starvation.

Một kiến trúc tốt tách **I/O completion dispatch** và **business executor**:

```text
AsynchronousChannelGroup threads
     |
     | đọc/ghi hoàn tất
     v
CompletionHandler (rất ngắn)
     |
     | kiểm tra + enqueue
     v
Business Executor / bounded queue
     |
     | validate, parse, truy vấn DB, business rule
     v
Kết quả trả về → khởi tạo async write
```

Tuy vậy, business executor cũng cần giới hạn queue và backpressure. Không chuyển việc nặng khỏi group bằng cách tạo số task vô hạn gây hết heap. Khi tính toán network protocol, phải giữ thứ tự message/response theo quy tắc ứng dụng, không mặc định thread pool thực thi theo thứ tự submit.

## 6. Future và CompletionHandler: hai cách nhận kết quả

Cùng là asynchronous socket I/O nhưng kiểu lấy kết quả ảnh hưởng khả năng mở rộng:

| Cách dùng | Mô hình | Điểm cần chú ý |
| --- | --- | --- |
| `Future<V>` | Gọi `connect` / `accept` / `read` / `write` nhận Future; caller có thể làm việc khác rồi `get` để lấy kết quả. | `Future.get()` **chặn thread gọi** nếu chưa xong. Không dùng trong callback của chính pool nếu phụ thuộc task khác của pool. |
| `CompletionHandler<V,A>` | Truyền handler/attachment; JDK gọi `completed` hoặc `failed` khi thao tác hoàn tất. | Không block chờ kết quả trong callback; cần quản lý state, lỗi, buffer, concurrency và lifecycle. |

`Future` **không đồng nghĩa non-blocking từ đầu đến cuối** nếu bạn gọi `get()` ngay lập tức. Đó vẫn là API khởi tạo bất đồng bộ, nhưng luồng gọi `get` sẽ chờ. Trong demo ngắn, `get(timeout, unit)` dễ giúp kiểm chứng kết quả; trong server có nhiều connection, completion callback hoặc event-driven abstraction thường phù hợp hơn.

Một thao tác có thể hoàn tất lỗi. Với `Future`, exception từ I/O thường được bọc trong `ExecutionException` khi `get`. Với callback, `failed(Throwable, attachment)` là nhánh xử lý lỗi. **Không nuốt cả hai** rồi giả định dữ liệu đã truyền đủ.

## 7. Ví dụ Java 17+ chạy được: group, Future và callback

Ví dụ mở TCP loopback server và client **cùng gắn vào một group có 2 threads**. Client ghi `PING` bằng asynchronous write/Future; server đọc đến khi đủ 4 byte qua `CompletionHandler`. Program chờ hoàn thành có timeout để không treo vô hạn trong demo.

Lưu thành file `AsyncGroupDemo.java`:

```java
import java.io.EOFException;
import java.io.IOException;
import java.net.*;
import java.nio.*;
import java.nio.channels.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.*;

public class AsyncGroupDemo {
    public static void main(String[] args) throws Exception {
        AsynchronousChannelGroup group =
                AsynchronousChannelGroup.withFixedThreadPool(2,
                    task -> new Thread(task, "aio-worker"));
        try {
            InetAddress loopback = InetAddress.getLoopbackAddress();
            try (AsynchronousServerSocketChannel server =
                         AsynchronousServerSocketChannel.open(group)
                             .bind(new InetSocketAddress(loopback, 0));
                 AsynchronousSocketChannel client =
                         AsynchronousSocketChannel.open(group)) {
                Future<AsynchronousSocketChannel> accepted = server.accept();
                client.connect(server.getLocalAddress()).get(5, TimeUnit.SECONDS);
                try (AsynchronousSocketChannel peer =
                             accepted.get(5, TimeUnit.SECONDS)) {
                    ByteBuffer outbound = ByteBuffer.wrap(
                            "PING".getBytes(StandardCharsets.US_ASCII));
                    int totalSent = 0;
                    while (outbound.hasRemaining()) {
                        int n = client.write(outbound).get(5, TimeUnit.SECONDS);
                        if (n <= 0) throw new IOException("Write made no progress");
                        totalSent += n;
                    }
                    ByteBuffer inbound = ByteBuffer.allocate(4);
                    CompletableFuture<Integer> done = new CompletableFuture<>();
                    CompletionHandler<Integer, Void> handler = new CompletionHandler<>() {
                        @Override public void completed(Integer n, Void attachment) {
                            if (n < 0) {
                                done.completeExceptionally(
                                        new EOFException("Truncated message"));
                            } else if (inbound.hasRemaining()) {
                                peer.read(inbound, null, this);
                            } else {
                                done.complete(inbound.position());
                            }
                        }
                        @Override public void failed(Throwable error, Void attachment) {
                            done.completeExceptionally(error);
                        }
                    };
                    peer.read(inbound, null, handler);
                    int totalRead = done.get(5, TimeUnit.SECONDS);
                    inbound.flip();
                    System.out.println("sent=" + totalSent);
                    System.out.println("received=" + totalRead);
                    System.out.println("body=" +
                            StandardCharsets.US_ASCII.decode(inbound));
                }
            }
        } finally {
            group.shutdown();
            if (!group.awaitTermination(5, TimeUnit.SECONDS)) {
                group.shutdownNow();
                group.awaitTermination(5, TimeUnit.SECONDS);
            }
        }
    }
}
```

Lệnh biên dịch và chạy:

```bash
javac --release 17 AsyncGroupDemo.java
java AsyncGroupDemo
```

Kết quả đã kiểm chứng trong môi trường cho phép TCP loopback:

```text
sent=4
received=4
body=PING
```

**Giải thích đầy đủ:**

1. `withFixedThreadPool(2, ...)` tạo group gắn hạ tầng hoàn tất I/O với hai pooled threads; `ThreadFactory` đặt tên. **Tên thread không được in** vì thứ tự chạy callback không phải hợp đồng bảo đảm.
2. `AsynchronousServerSocketChannel.open(group)` và `AsynchronousSocketChannel.open(group)` dùng cùng group. `bind(..., 0)` yêu cầu OS chọn một port tự do.
3. `server.accept()` trả `Future<AsynchronousSocketChannel>`. Client `connect(...).get(5, ...)` chờ kết nối được thiết lập, rồi Future accept trả channel phía server. `get` chặn **main thread**, không biến I/O thành blocking API của channel.
4. Client viết buffer `PING`. Vòng `write` xử lý khả năng ghi **ít byte** mỗi lần; sau khi Future hoàn tất, mới được truy cập/ghi tiếp buffer.
5. Server `read` đăng ký callback. Khi hoàn tất một lần đọc, handler kiểm tra EOF rồi **khởi tạo lần đọc tiếp theo** nếu buffer chưa đủ 4 byte. Vì TCP là stream, không giả định một lần read tương ứng một message.
6. `CompletableFuture done` ở đây chỉ là cầu nối để **main thread** đợi cả khối demo hoàn tất; bản thân completion handler không gọi `get`. Sau khi `done.get` trả về, buffer đã được viết xong; `flip` chuẩn bị để decode.
7. `try-with-resources` đóng server/client/accepted channel. Cuối cùng `group.shutdown()` và `awaitTermination` đợi group kết thúc, dùng `shutdownNow` khi vượt thời hạn mẫu.

Code đơn giản hóa nội dung mạng thành 4 ASCII byte và một kết nối. Dịch vụ thật cần framing, giới hạn kích thước, queue ghi, backpressure, timeout toàn request, xử lý lỗi callback và shutdown phối hợp. Nếu môi trường hạn chế tạo socket, chương trình có thể ném exception; không phải bằng chứng API group không hoạt động.

### Hạn chế của ví dụ cần hiểu

- Một `AsynchronousSocketChannel` cho phép nhiều thread sử dụng, nhưng **tối đa một read đang chờ và một write đang chờ** trên cùng channel. Khởi tạo read thứ hai trước khi read cũ hoàn tất sẽ ném `ReadPendingException`; tương tự `WritePendingException` cho write. Code đặt lần read kế tiếp sau callback nên tránh overlap.
- `read` có thể trả `-1` nếu peer đóng chiều ghi; handler coi đó là dữ liệu dở nếu chưa đủ 4 bytes. Ở production phải có quy tắc parser riêng cho EOF hợp lệ.
- `CompletableFuture` làm tầng phối hợp trong ví dụ, không thay group; hai loại executor/thread vẫn có trách nhiệm khác nhau.
- `awaitTermination(5,...)` là thời gian demo. Hệ thống thật cần grace period, cancellation policy và quan sát request còn đang hoạt động.

## 8. Ràng buộc về số operation đang chờ và buffer

Async không cho phép sử dụng bừa các buffer ở nhiều thread.

### Một read và một write pending trên một async socket

`AsynchronousSocketChannel` có thể đồng thời có **một read và một write** đang chờ. Nhưng hai lần read đang chờ đồng thời hoặc hai lần write đang chờ đồng thời trên cùng socket sẽ bị từ chối qua exception tương ứng. Điều này đòi hỏi per-connection state:

```text
READ_IDLE --start read--> READ_PENDING --completed/failed--> READ_IDLE
WRITE_IDLE --start write--> WRITE_PENDING --completed/failed--> WRITE_IDLE
```

Nếu có nhiều message cần gửi, xếp chúng trong outbound queue, chỉ tạo lần write tiếp theo sau khi operation trước hoàn tất; dữ liệu gửi dở phải tiếp tục từ `ByteBuffer.position` hiện tại. Khi có hàng chờ lớn, dùng backpressure hoặc giới hạn queue, không tạo vô hạn Future rồi hy vọng group tự giữ thứ tự.

### Buffer không nên được sửa khi operation còn pending

Ví dụ **sai**:

```java
ByteBuffer buffer = ByteBuffer.wrap(payload);
socket.write(buffer); // async write chưa chắc đã hoàn tất
buffer.clear();        // SAI: làm đổi trạng thái buffer khi I/O còn pending
```

Đây chỉ là snippet minh họa, `payload` và `socket` giả định đã có. Theo hợp đồng, sau khi khởi tạo operation bất đồng bộ, không truy cập/biến đổi buffer liên quan cho tới khi operation hoàn tất. Nếu socket API timeout và implementation không bảo đảm đã xử lý bao nhiêu byte, trạng thái buffer sau timeout có thể **không được xác định**; phải áp dụng chính sách hủy/đóng và không tùy tiện retry trên buffer đó.

Đối với protocol có frame dài, giữ buffer đúng ownership qua các lần callback; không đưa cùng buffer cho hai pending operations. **Group thread pool không tự làm ByteBuffer thread-safe.**

## 9. AsynchronousFileChannel sử dụng ExecutorService, không dùng group trực tiếp

`AsynchronousFileChannel` cũng hỗ trợ `Future` và `CompletionHandler`, nhưng không có **current file position**; mỗi `read/write` nhận offset tường minh. Nó cho phép **nhiều read/write operations outstanding** trên cùng file channel, nhưng thứ tự thao tác hoặc callback **không được bảo đảm** theo thứ tự khởi tạo. Buffer dùng cho I/O pending không được chia sẻ bất cẩn.

Factory đặc trưng:

```java
AsynchronousFileChannel.open(
    path,
    Set.of(StandardOpenOption.READ, StandardOpenOption.WRITE),
    executor);
```

Đoạn trên chỉ minh họa; `path` và `executor` đã có. `executor` là một `ExecutorService` phục vụ thao tác/dispatch của file channel này. **Không truyền `AsynchronousChannelGroup` vào overload** vì Java không định nghĩa signature đó. Overload `AsynchronousFileChannel.open(path, options...)` dùng thread pool mặc định theo môi trường.

### Ví dụ Java 17+: file async với executor riêng

Lưu thành `AsyncFilePoolDemo.java`:

```java
import java.nio.*;
import java.nio.channels.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;

public class AsyncFilePoolDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("async-file-", ".dat");
        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            try (AsynchronousFileChannel channel = AsynchronousFileChannel.open(
                    file, Set.of(StandardOpenOption.READ, StandardOpenOption.WRITE),
                    executor)) {
                ByteBuffer payload = ByteBuffer.wrap(
                        "DATA".getBytes(StandardCharsets.US_ASCII));
                int written = channel.write(payload, 0).get(5, TimeUnit.SECONDS);
                ByteBuffer target = ByteBuffer.allocate(4);
                int read = channel.read(target, 0).get(5, TimeUnit.SECONDS);
                target.flip();
                System.out.println("file-written=" + written);
                System.out.println("file-read=" + read);
                System.out.println("file-data=" +
                        StandardCharsets.US_ASCII.decode(target));
            }
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
            Files.deleteIfExists(file);
        }
    }
}
```

```bash
javac --release 17 AsyncFilePoolDemo.java
java AsyncFilePoolDemo
```

Kết quả đã kiểm chứng trên local filesystem:

```text
file-written=4
file-read=4
file-data=DATA
```

Ở đây sử dụng `ExecutorService` trực tiếp chứ **không tạo `AsynchronousChannelGroup`**. Cả hai Future được `get` xác nhận hoàn tất trước khi dùng lại buffer hoặc đọc kết quả. Nội dung file nhỏ 4 byte khiến output ổn định trong môi trường thử nghiệm, nhưng **API vẫn cho phép read/write ngắn**; khi triển khai với file lớn, cần lặp theo số byte thực xử lý và duy trì offset chính xác.

Khác với việc group **sở hữu executor** được truyền vào `withThreadPool`, executor ở ví dụ file được ứng dụng tạo và ứng dụng chủ động shutdown **sau khi channel được đóng**. Không trộn lẫn lifecycle giữa các API. Với file lớn, điều phối nhiều operation cùng offset có thể làm hỏng record logic nếu không có giao thức tránh overlap, dù mỗi lời gọi riêng hợp lệ.

## 10. Vòng đời AsynchronousChannelGroup: shutdown, shutdownNow, termination

`AsynchronousChannelGroup` **không triển khai AutoCloseable**; không dùng `try (AsynchronousChannelGroup group = ...)` như với socket channel. Quản lý group qua bốn trạng thái/phương thức:

| API | Ý nghĩa chính | Không nên suy diễn |
| --- | --- | --- |
| `isShutdown()` | Group đã được đánh dấu shutdown chưa. | Không có nghĩa tất cả channel đã đóng. |
| `shutdown()` | Khởi tạo **orderly shutdown**: ngăn tạo channel mới gắn vào group. | **Không** tự đóng các channel đang mở, không tự hủy callback đang chạy. |
| `shutdownNow()` | Khởi tạo shutdown và gọi đóng tất cả channel đang mở trong group. | Không cố ngắt/interrrupt các callback đang thực thi; tác vụ có thể thất bại do channel bị đóng. |
| `awaitTermination(timeout, unit)` | Chờ group hoàn tất hoặc hết thời hạn. | Không phải phương thức bắt đầu shutdown; thời gian chờ có thể hết mà group chưa terminate. |
| `isTerminated()` | Xác nhận group đã terminate. | Không phải tín hiệu “mọi request đã commit” nếu ứng dụng không tự quản lý state. |

Theo Javadoc, khi `shutdown` đã được gọi:

- Tạo thêm channel gắn vào group sẽ ném `ShutdownChannelGroupException`.
- **Group chỉ terminate khi** toàn bộ asynchronous channels thuộc group đã đóng, các completion handlers đang thực thi đã chạy xong, và tài nguyên group được giải phóng.
- `shutdown` **không** cố ngừng hoặc interrupt thread đang chạy callback.
- `shutdownNow` sẽ đóng các channel đang mở, nhưng **cũng không** ngắt callback đang thực thi; vì thế không lấy đây làm một hard kill/timeout bảo đảm.

### Trình tự shutdown an toàn

```text
Đánh dấu server không nhận request mới
       |
Dừng đăng ký thao tác mới / đóng server accept endpoint
       |
Chờ hoặc hủy theo chính sách các request đang hoạt động
       |
Đóng các client sockets / server socket thuộc group
       |
group.shutdown()
       |
group.awaitTermination(gracefulTimeout, unit)
       |
Nếu chưa dừng: group.shutdownNow(); theo dõi kết quả/timeout
       |
Chỉ báo kết thúc khi state nghiệp vụ và resources đã được xử lý
```

`shutdownNow` có thể ném `IOException` nếu đóng channel gặp lỗi. `awaitTermination` có thể ném `InterruptedException`; phải giữ đúng chính sách interruption, không bỏ qua rồi tuyên bố đã terminate. Những callback được gọi khi channel đang đóng có thể nhận failure; cần bảo đảm completion signal và cleanup được thực hiện cả ở nhánh lỗi.

**Deadlock shutdown thường gặp:** callback đợi một `CountDownLatch` sẽ chỉ được giải phóng bởi task khác cũng cần group thread, hoặc thread điều phối đóng group rồi chờ một callback chưa bao giờ được phép chạy. Hạn chế việc chờ blocking trên group threads và có cơ chế cancellation/outstanding-work tracking từ thiết kế.

### Group ownership

Một hệ thống có nhiều module có thể cùng dùng một group để giảm overhead, nhưng nếu module A gọi `shutdownNow` trong khi module B vẫn giữ socket thuộc group, module B cũng bị ảnh hưởng. Chỉ **chủ sở hữu group** được phép shutdown; thư viện nhận group từ caller chỉ nên đóng các channel do chính nó sở hữu, trừ khi giao kèo API nói khác.

Nếu muốn cô lập fault/latency giữa các subsystems, dùng group riêng cho từng loại I/O hoặc hạn chế việc nặng trong callbacks. Nhưng tạo group mới cho **mỗi kết nối** sẽ gây thêm thread/tài nguyên và làm mất lợi ích chia sẻ — thường không phù hợp.

## 11. Đặt kích thước pool sao cho phù hợp

**Không có công thức Java API bảo đảm số thread tối ưu.** Khi chọn fixed vs cached, cần phân tích:

- Số concurrent connections và số operations pending; chúng **không** tương đương số threads cần giữ.
- Cách JDK/provider xử lý I/O events và dispatch, số lượng callback hoàn thành mỗi giây.
- Callback chạy trong bao lâu và có blocking không.
- Có business thread pool riêng không? Queue có bounded/backpressure không?
- Network throughput, độ trễ yêu cầu, số CPU core, GC, socket memory và áp lực tài nguyên khác.
- OS, JDK version/provider, số lượng file descriptors và behavior under load.

### Fixed thread pool

Ưu điểm: dễ đặt giới hạn số worker phục vụ group, dễ đo saturation, tạo rõ thread factory. Nhược điểm: nếu callbacks lâu hoặc blocking, toàn nhóm có thể thiếu worker. Tăng `nThreads` không sửa logic deadlock hoặc thiếu backpressure; tăng vô hạn còn tạo overhead.

### Cached thread pool

Ưu điểm: có thể tạo thêm threads khi cần, phù hợp với profile workload/provider nhất định. Nhược điểm: cần giới hạn tải ở tầng ứng dụng vì tăng threads/queue có thể tiêu thụ nhiều memory và làm latency biến động. `initialSize` là hint, **không** phải cam kết tạo đúng số thread ban đầu.

### Custom ExecutorService

Ưu điểm: kiểm soát ThreadFactory, instrumentation, policy cấu hình. Nhược điểm: phải tuân thủ các ràng buộc `withThreadPool`. Javadoc yêu cầu hỗ trợ **direct handoff hoặc hàng đợi không giới hạn**, và thread gọi `execute` không chạy task trực tiếp. Vì vậy **không** tự ý dùng executor với bounded queue + `CallerRunsPolicy` cho `withThreadPool`; khi quá tải, `CallerRunsPolicy` có thể khiến thread dispatch/initiating call bị kéo vào chạy công việc một cách không phù hợp với hợp đồng. Dùng bounded business queue riêng cho backpressure, không phá giả định dispatch của group.

**Quan sát hữu ích:** số socket đang mở, active/pending callbacks, thời gian callback, độ dài outbound queues, số timeout/exception, thời gian graceful shutdown, thread dumps và tỷ lệ CPU. Đo throughput và tail latency trên đúng JDK/OS triển khai.

## 12. Phân biệt AsynchronousChannelGroup và Selector / CompletableFuture / virtual threads

| Công cụ | Trách nhiệm | Điểm khác |
| --- | --- | --- |
| `AsynchronousChannelGroup` | Resource sharing, I/O completion processing, completion dispatch cho các async socket channels. | Không phải API tự đọc/ghi; nhóm không đại diện một kết nối. |
| `AsynchronousSocketChannel` | Khởi tạo connect/read/write async, nhận `Future` hoặc `CompletionHandler`. | Socket có thể thuộc group do người dùng tạo hoặc default group. |
| `SocketChannel` + `Selector` | Readiness-based non-blocking I/O do event loop chủ động điều phối. | Thao tác đọc/ghi vẫn được **ứng dụng chủ động gọi** sau readiness. |
| `ExecutorService` | Chạy task nói chung; có thể làm resource pool của group hoặc phục vụ file async. | Executor một mình không tạo semantics I/O bất đồng bộ cho network socket. |
| `CompletableFuture` | Compose kết quả bất đồng bộ của tác vụ. | Không tự tạo group; có thể nhận kết quả từ callback. |
| Virtual threads (Java 21+) | Cho phép viết luồng điều khiển kiểu blocking với chi phí thread nhỏ hơn trong nhiều tác vụ I/O. | Đây là mô hình lập trình khác; không đồng nghĩa AsynchronousChannelGroup. |

**Không chọn group chỉ vì muốn “nhiều kết nối”.** Cân nhắc ba kiến trúc phổ biến:

1. Blocking network I/O với nền tảng hiện có, hoặc virtual threads khi dùng JDK hỗ trợ và bài toán phù hợp.
2. Non-blocking `SocketChannel` + `Selector` nếu cần kiểm soát event loop và readiness.
3. `AsynchronousSocketChannel` + `AsynchronousChannelGroup` khi muốn khởi tạo I/O và nhận completion qua callbacks/Future.

Mọi lựa chọn vẫn phải giải quyết framing TCP, short read/write, timeout, TLS, authentication, error handling và backpressure ở tầng thích hợp. Group không xóa trách nhiệm này.

## 13. Những lỗi thường gặp và cách sửa

| Sai lầm | Hậu quả | Thiết kế đúng |
| --- | --- | --- |
| Tạo `AsynchronousChannelGroup` cho mỗi connection. | Tốn thêm thread và tài nguyên; khó shutdown. | Một group dùng chung cho subsystem có ownership rõ ràng. |
| Cho callback gọi `Thread.sleep` hoặc truy vấn DB chậm. | Pool xử lý completion bị nghẽn/starvation, latency tăng. | Callback ngắn, chuyển việc nặng sang executor khác có bounded queue. |
| Trong callback gọi `Future.get()` để chờ tác vụ cũng cần group. | Có thể deadlock hoặc pool starvation. | Compose async, callback tiếp nối hoặc chuyển việc chờ ra nơi khác. |
| Chạy hai read đồng thời trên cùng socket. | `ReadPendingException`. | Mỗi kết nối quản lý trạng thái: tối đa một read đang chờ. |
| Chạy hai write đồng thời trên cùng socket. | `WritePendingException`. | Hàng đợi ghi; write tiếp sau khi lần trước hoàn tất. |
| Thay đổi `ByteBuffer` khi operation chưa xong. | Race dữ liệu/position, kết quả không đáng tin. | Quy tắc buffer ownership; chỉ truy cập sau completion. |
| Nghĩ `read` nhận đủ một frame TCP. | Parser hỏng khi dữ liệu đến theo nhiều chunk. | Tích lũy bytes và framing protocol. |
| Gọi `group.shutdown()` nhưng để socket mở. | `awaitTermination` có thể đợi mãi hoặc timeout. | Đóng mọi channel thuộc group và chờ callbacks xong. |
| `shutdownNow` rồi cho rằng callback chắc chắn đã bị interrupt. | Callback tiếp tục chạy, có thể vẫn dùng tài nguyên nghiệp vụ. | Thiết kế cancellation/cooperative stop, đóng channel và await. |
| Tự gọi `executor.shutdown()` trên executor đang được group sử dụng. | Hành vi không xác định theo Javadoc. | Để group sở hữu và shutdown executor của nó. |
| Dùng `AsynchronousFileChannel.open(path, group)`. | Không có overload đó; lỗi biên dịch. | Dùng `open(path, options, ExecutorService)` cho async file. |
| Đọc một callback xảy ra trên thread nào đó rồi khẳng định mọi callback luôn ở thread ấy. | Phụ thuộc lịch thực thi, dễ sai về concurrency. | Chỉ dựa trên bảo đảm pooled threads của group, không dựa trên thread ID cụ thể. |
| `get(timeout)` hết hạn rồi vẫn coi buffer an toàn để tái sử dụng ngay. | Operation có thể còn chạy; buffer đang được sử dụng. | Xác nhận completion/cancel semantics, đóng channel khi cần, xử lý timeout từng API. |

### Exception đáng nhận biết

- `ShutdownChannelGroupException`: cố tạo channel mới ràng buộc group đã shutdown.
- `ReadPendingException` / `WritePendingException`: operation cùng hướng trước chưa hoàn tất trên asynchronous socket.
- `AcceptPendingException`: cố khởi tạo accept mới trong lúc accept trước vẫn pending trên cùng server channel.
- `ExecutionException`: `Future.get` bọc nguyên nhân I/O thất bại.
- `TimeoutException`: luồng đang đợi Future chưa nhận kết quả trong thời gian yêu cầu; **không đồng nghĩa underlying I/O đã bị hủy**.
- `AsynchronousCloseException` / `ClosedChannelException`: channel bị đóng hoặc không còn hợp lệ cho thao tác.
- `InterruptedByTimeoutException`: quá thời gian trong overload async socket read/write có timeout; Javadoc cảnh báo trạng thái buffer/connection có thể không xác định trong một số trường hợp.

Đừng chuyển tất cả exception thành “thử lại ngay”. Khi mạng bị gián đoạn, chưa chắc peer application đã xử lý bao nhiêu bytes. Với protocol có tác động nghiệp vụ, cần framing và idempotency/acknowledgement riêng.

## 14. Checklist triển khai và tự kiểm tra

### Checklist

1. **Làm rõ loại channel:** async socket hay async file? Chỉ socket channels gắn trực tiếp vào `AsynchronousChannelGroup`.
2. **Chọn group:** default group khi đơn giản; explicit group khi cần giới hạn/cô lập và quản lý lifecycle.
3. **Chọn factory:** fixed, cached hay custom executor theo workload và ràng buộc Javadoc.
4. **Sở hữu pool:** với group tự tạo, group chịu trách nhiệm shutdown pooled executor; không tự shutdown từ module khác.
5. **Giữ callback ngắn:** không chờ khóa/DB/network blocking trong pooled threads nếu có thể tránh.
6. **Buffer ownership:** không tái sử dụng/modify buffer khi I/O pending; quản lý per-connection state.
7. **Giới hạn pending operations:** mỗi async socket chỉ một read và một write đồng thời; quản lý write queue.
8. **Protocol:** TCP stream không có message boundaries; xử lý partial read/write, EOF, kích thước frame.
9. **Timeout/cancel:** đặt deadline đúng cấp request; `Future.get` timeout không tự hủy I/O.
10. **Shutdown đúng thứ tự:** ngừng nhận công việc, hoàn tất/hủy, đóng channels, group.shutdown, awaitTermination, fallback phù hợp.
11. **Load test:** theo dõi callback latency, pending tasks, memory, active sockets, error rate và tail latency.
12. **Platform test:** xác minh behavior trên đúng OS/JDK/network provider, không dự đoán implementation từ tên NIO.

### Câu hỏi tự kiểm tra

**1. `AsynchronousChannelGroup` có được dùng để truyền bytes giữa hai socket không?**

Không. Group chia sẻ hạ tầng xử lý completion; chính `AsynchronousSocketChannel` mới thực hiện `read/write`.

**2. Callback của một channel được gắn group có chạy ngẫu nhiên trên thread không thuộc group không?**

Theo hợp đồng, callback được gọi bởi một pooled thread của group. Nếu operation hoàn tất ngay và caller đang ở pooled thread, có thể được gọi trực tiếp trên chính initiating pooled thread đó.

**3. `group.shutdown()` đã đóng tất cả socket chưa?**

Chưa. Orderly shutdown đánh dấu group shutdown và ngăn tạo channel mới; group chỉ terminate khi các channel trong nhóm đã đóng, callbacks đang thực thi hoàn tất và tài nguyên được giải phóng.

**4. Có thể gọi `group.shutdownNow()` để chắc chắn hủy tức thì mọi callback không?**

Không. Nó đóng các channel mở, nhưng không cố interrupt những thread đang chạy completion handler.

**5. Nếu `Future.get(5, SECONDS)` ném `TimeoutException`, thao tác I/O đã tự hủy chưa?**

Không thể suy ra. Timeout của `Future.get` chỉ là timeout chờ kết quả. Phải dùng cơ chế cancel/close/timeout riêng với semantics của channel.

**6. Vì sao không nên gọi `Future.get()` lâu ngay bên trong `CompletionHandler` của pool cố định?**

Vì callback chiếm một pooled thread. Nếu tất cả pooled threads đều chờ task/callback khác cũng cần cùng pool, ứng dụng có thể starvation hoặc deadlock.

**7. `AsynchronousFileChannel` có thể tạo bằng `AsynchronousChannelGroup.withFixedThreadPool` rồi `open(path, group)` không?**

Không. API file async nhận `ExecutorService` trong overload chuyên biệt, không nhận group.

**8. Tại sao example phải lặp đọc và ghi dù đã dùng API asynchronous?**

Vì một operation chỉ hứa trả số bytes thực đọc/ghi, không hứa hoàn tất trọn message TCP. “Asynchronous” mô tả cách nhận completion, **không** làm stream trở thành message-based.

## Nguồn đọc chính thức

- Oracle Java SE 21 — [`AsynchronousChannelGroup`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/AsynchronousChannelGroup.html): group, thread pool, default group, callback dispatch, shutdown và termination.
- Oracle Java SE 21 — [`AsynchronousSocketChannel`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/AsynchronousSocketChannel.html): Future/CompletionHandler, giới hạn một read và một write pending, timeout.
- Oracle Java SE 21 — [`AsynchronousServerSocketChannel`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/AsynchronousServerSocketChannel.html): accept kết nối, accept pending và group.
- Oracle Java SE 21 — [`AsynchronousFileChannel`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/AsynchronousFileChannel.html): async file I/O với ExecutorService và offset riêng.
- Oracle Java SE 21 — [`CompletionHandler`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/CompletionHandler.html): completion callback, attachment và error branch.

**Tóm lại:** `AsynchronousChannelGroup` là **tầng chia sẻ tài nguyên và thread pool** cho asynchronous socket channels, không phải một protocol handler hay event loop tự động xử lý nghiệp vụ. Thành công của thiết kế phụ thuộc ownership rõ ràng, callback ngắn, quản lý buffer/pending operations, cấp phát số threads có đo đạc và shutdown cả channels lẫn group đúng vòng đời.