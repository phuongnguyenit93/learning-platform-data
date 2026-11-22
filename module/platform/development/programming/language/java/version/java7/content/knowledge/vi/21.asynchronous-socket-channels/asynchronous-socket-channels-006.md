# Thời hạn chờ, hủy và đóng kênh mạng bất đồng bộ trong Java NIO.2

> **Phạm vi:** Cách quản lý deadline, timeout, `Future.cancel`, đóng `AsynchronousSocketChannel`/`AsynchronousServerSocketChannel` và vòng đời `AsynchronousChannelGroup`. Đây là kiến thức Java 7 NIO.2 **vẫn còn áp dụng trong Java 17+**, không phải API lỗi thời. Ví dụ được viết cho JDK 17 (không phụ thuộc tiện ích Java 11), biên dịch bằng `javac --release 17`, dùng loopback để không cần Internet. Nội dung phân biệt những gì Javadoc bảo đảm với kết quả do provider/thread scheduling quyết định.

## 1. Phân biệt ba kiểu timeout và việc hủy thực sự

```text
Caller thread                     AsynchronousSocketChannel / provider
   |                                         |
   | channel.read(buffer)                    |
   |---------------------------------------->|
   |<------------- Future<Integer> ----------|
   |                                         | I/O vẫn pending
   | future.get(100, MILLISECONDS)            |
   |<------------- TimeoutException ---------| read chưa hẳn dừng
   |                                         |
   | future.cancel(false) hoặc channel.close()| <-- hành động riêng
```

Java có nhiều khái niệm thường bị nhầm:

| Hoạt động | API | Khi hết hạn/tác động |
| --- | --- | --- |
| **Đợi kết quả Future** | `future.get(timeout, TimeUnit)` | Ném `TimeoutException` nếu chưa có kết quả. **Không tự cancel underlying I/O** |
| **Timeout của chính thao tác read/write** | `channel.read/write(buffer, timeout, unit, attachment, handler)` | Timed I/O báo `InterruptedByTimeoutException` cho `CompletionHandler.failed` |
| **Deadline của yêu cầu ứng dụng** | Ngân sách từ `System.nanoTime()` | Ứng dụng tính remaining cho từng bước, quyết định stop/cleanup |
| **Cancellation** | `future.cancel(false/true)` | Future bị cancel nếu chấp nhận; underlying I/O có dừng hay không **phụ thuộc implementation** |
| **Đóng resource** | `channel.close()` | Chấm dứt channel; outstanding I/O thất bại với `AsynchronousCloseException` |
| **Shutdown group** | `group.shutdown()`, `shutdownNow()` | Đóng group có thứ tự hoặc cưỡng bức; không giống timeout một Future |

**Kết luận quan trọng:** một `Future.get(timeout)` hết giờ chỉ làm thread gọi **ngừng đợi**, không chứng minh rằng read/connect/accept đã dừng. Nếu caller không còn cần kết quả, phải có policy rõ về Future, buffer, owned channel và late completion.

### 1.1. Hai cách nhận kết quả trong NIO.2

```java
Future<Integer> pendingRead = channel.read(buffer);
int received = pendingRead.get(2, TimeUnit.SECONDS);
```

Đây là **snippet**, yêu cầu `channel` đã connected và `buffer` do caller chuẩn bị; method phải xử lý checked exceptions. Timeout đặt trên `get` là timeout **của người đợi**.

```java
channel.read(buffer, 500, TimeUnit.MILLISECONDS, null,
    new CompletionHandler<Integer, Void>() {
        @Override
        public void completed(Integer count, Void ignored) {
            // Nhận bytes; -1 nghĩa là EOF.
        }

        @Override
        public void failed(Throwable cause, Void ignored) {
            // Timeout I/O: InterruptedByTimeoutException.
        }
    });
```

Đây là **snippet**, sử dụng timed read **trực tiếp**. Trong Java 17, các timed overload của `AsynchronousSocketChannel.read/write` dùng CompletionHandler; không có overload `read(ByteBuffer,long,TimeUnit)` trả Future như một số người lầm tưởng.

### 1.2. Timeout <= 0 của timed read/write

Các overload timed read/write quy định giá trị timeout **nhỏ hơn hoặc bằng 0** nghĩa là operation **không bị timeout theo tham số đó**. Vì thế nếu deadline tổng đã về 0, đừng truyền 0 rồi tưởng read/write sẽ lập tức thất bại: ứng dụng cần **dừng khởi tạo I/O**, đánh dấu request hết hạn và cleanup.

## 2. Những đối tượng cần quản lý

- `AsynchronousSocketChannel`: kết nối stream (thường là TCP); mở/kết nối/đọc/ghi bất đồng bộ; có `shutdownInput`, `shutdownOutput`, `close`.
- `AsynchronousServerSocketChannel`: listener, `bind` và `accept` bất đồng bộ.
- `AsynchronousChannel`: hợp đồng chung về `Future`, `CompletionHandler`, cancellation và close.
- `AsynchronousChannelGroup`: chia sẻ I/O resources/thread pool và dispatch CompletionHandlers cho các kênh thuộc group.
- `Future<V>`: biểu diễn kết quả pending, thành công, thất bại hoặc cancelled.
- `ByteBuffer`: dữ liệu read/write; không chỉnh sửa đồng thời trước khi I/O kết thúc, không giả định vẫn an toàn sau timeout/cancel.
- `TimeUnit`: giới hạn thời gian có đơn vị rõ, tránh nhầm milliseconds với nanoseconds.

### 2.1. Giới hạn outstanding operations

Một `AsynchronousSocketChannel` có thể vừa đọc vừa ghi nhưng tối đa **một read outstanding** và **một write outstanding**. Nếu read trước chưa kết thúc, read mới có thể ném `ReadPendingException`; write mới gặp `WritePendingException`. Listener chỉ có **một accept outstanding**, accept mới khi cái cũ pending có thể ném `AcceptPendingException`.

Cả ba hiện tượng đều thường là hậu quả của việc caller `get(timeout)` xong rồi tưởng operation cũ đã dừng.

## 3. Timeout Future không hủy `accept`

Giả sử server chờ kết nối:

```java
Future<AsynchronousSocketChannel> accepting = server.accept();
try {
    accepting.get(100, TimeUnit.MILLISECONDS);
} catch (TimeoutException expected) {
    // Chỉ hết thời gian chờ của caller, accept có thể vẫn pending.
}
```

Đây là snippet. Sau `get` timeout, nếu server còn phục vụ, nên **tiếp tục quản lý cùng Future**; đừng mở thêm `accept()` khi accept cũ đang outstanding. Nếu ứng dụng muốn dừng listener, code sở hữu listener có thể `server.close()`, khi đó pending accept thất bại với `AsynchronousCloseException`.

### 3.1. Chương trình 1: timeout waiter, accept vẫn hoàn tất sau đó

Lưu thành `FutureWaitDeadlineDemo.java`:

```java
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.channels.AsynchronousServerSocketChannel;
import java.nio.channels.AsynchronousSocketChannel;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class FutureWaitDeadlineDemo {
    public static void main(String[] args) throws Exception {
        try (AsynchronousServerSocketChannel server =
                 AsynchronousServerSocketChannel.open().bind(
                         new InetSocketAddress(InetAddress.getLoopbackAddress(), 0))) {
            Future<AsynchronousSocketChannel> accepting = server.accept();
            boolean timedOut = false;
            try {
                accepting.get(100, TimeUnit.MILLISECONDS);
            } catch (TimeoutException expected) {
                timedOut = true;
            }
            System.out.println("waitTimedOut=" + timedOut);
            System.out.println("acceptStillPending=" + !accepting.isDone());

            try (AsynchronousSocketChannel client = AsynchronousSocketChannel.open()) {
                client.connect(server.getLocalAddress()).get(2, TimeUnit.SECONDS);
                try (AsynchronousSocketChannel accepted =
                         accepting.get(2, TimeUnit.SECONDS)) {
                    System.out.println("acceptedLater=" + accepted.isOpen());
                }
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 FutureWaitDeadlineDemo.java
java FutureWaitDeadlineDemo
```

Stdout đã kiểm chứng trên JDK 17:

```text
waitTimedOut=true
acceptStillPending=true
acceptedLater=true
```

Server bind loopback và port 0 để OS cấp port trống. Trong 100 ms đầu không có client, nên `get` timeout nhưng `accepting` vẫn pending. Khi client kết nối sau đó, **Future cũ** trả accepted socket thành công. Ví dụ không gọi một `accept` thứ hai; kênh accepted và client đều đóng qua try-with-resources.

**Không suy rộng kết quả timing 100% cho mọi CI**: trên máy cực tải hoặc chính sách cấm loopback, scheduling/test environment có thể ảnh hưởng; chương trình minh họa contract, không đo latencies tuyệt đối.

## 4. Timed I/O có thể để lại trạng thái không nhất quán

Timeout thực của `AsynchronousSocketChannel.read/write` có một hậu quả quan trọng mà `Future.get(timeout)` không có: Javadoc nêu nếu implementation không bảo đảm bytes chưa được read/written thì channel có thể ở **implementation-specific error state**, khiến read hoặc write cùng chiều tiếp theo báo một runtime exception không xác định.

Khi timed read/write timeout, trạng thái `ByteBuffer` hoặc danh sách buffers được sử dụng **không được định nghĩa**. Không đọc `buffer.position()` để khẳng định chính xác bao nhiêu bytes đã qua đường mạng, không gọi `buffer.clear()` rồi tưởng đã phục hồi I/O và không tái sử dụng buffer đó tùy tiện khi channel còn mở.

### 4.1. Chương trình 2: `InterruptedByTimeoutException` qua CompletionHandler

Lưu thành `TimedReadHandlerDemo.java`:

```java
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousServerSocketChannel;
import java.nio.channels.AsynchronousSocketChannel;
import java.nio.channels.CompletionHandler;
import java.nio.channels.InterruptedByTimeoutException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class TimedReadHandlerDemo {
    public static void main(String[] args) throws Exception {
        try (AsynchronousServerSocketChannel server =
                 AsynchronousServerSocketChannel.open().bind(
                         new InetSocketAddress(InetAddress.getLoopbackAddress(), 0));
             AsynchronousSocketChannel client = AsynchronousSocketChannel.open()) {
            Future<AsynchronousSocketChannel> accepting = server.accept();
            client.connect(server.getLocalAddress()).get(2, TimeUnit.SECONDS);
            try (AsynchronousSocketChannel peer = accepting.get(2, TimeUnit.SECONDS)) {
                CountDownLatch finished = new CountDownLatch(1);
                AtomicReference<Throwable> error = new AtomicReference<>();
                ByteBuffer destination = ByteBuffer.allocate(16);
                client.read(destination, 150, TimeUnit.MILLISECONDS, null,
                        new CompletionHandler<Integer, Void>() {
                            @Override
                            public void completed(Integer count, Void ignored) {
                                error.set(new AssertionError("unexpected read: " + count));
                                finished.countDown();
                            }

                            @Override
                            public void failed(Throwable cause, Void ignored) {
                                error.set(cause);
                                finished.countDown();
                            }
                        });
                if (!finished.await(3, TimeUnit.SECONDS)) {
                    throw new AssertionError("handler deadline exceeded");
                }
                Throwable cause = error.get();
                if (!(cause instanceof InterruptedByTimeoutException)) {
                    throw new AssertionError("unexpected result", cause);
                }
                System.out.println("ioTimeout=InterruptedByTimeoutException");
                // Do not inspect/reuse destination after an I/O timeout.
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 TimedReadHandlerDemo.java
java TimedReadHandlerDemo
```

Stdout đã kiểm chứng:

```text
ioTimeout=InterruptedByTimeoutException
```

Peer kết nối nhưng không gửi bytes và không đóng trong lúc read chờ. Timed read hết 150 ms và callback `failed` nhận `InterruptedByTimeoutException`. `CountDownLatch.await(3s)` chỉ giới hạn thời gian **chương trình test chờ callback**, không tạo ra exception I/O. Ví dụ không dùng lại buffer sau timeout.

### 4.2. Retry sau timed write đòi hỏi thiết kế giao thức

Một write timed out **không đồng nghĩa** bên kia chưa nhận bytes. Gửi lại cùng request có side effect (như tạo đơn hàng/ghi tiền) có thể gây trùng. Nên dùng request IDs, idempotency keys, protocol ACK và có cơ chế reconciliation, thay vì retry ngay một ByteBuffer cũ.

## 5. `Future.cancel(false)` và `cancel(true)`

`Future.cancel` quản lý trạng thái Future: nếu cancel thành công, những thread đang `get` nhận `CancellationException`. Nhưng underlying I/O **có hủy được hay không phụ thuộc provider/implementation**, vì có thể bytes đã đi vào/ra socket.

| Lệnh | Kết quả nên hiểu | Rủi ro không được bỏ qua |
| --- | --- | --- |
| `cancel(false)` | Yêu cầu hủy, không yêu cầu ngắt theo tham số | Future cancelled không chứng minh I/O vật lý đã dừng |
| `cancel(true)` | Có thể cho phép provider **đóng channel** để chấm dứt I/O | Có thể làm pending operations khác thất bại với AsynchronousCloseException |
| `future.isCancelled()` | Future đã nhận cancellation | Không đủ chứng minh buffer/stream không bị thay đổi |
| `future.isDone()` | Future ở một trạng thái hoàn tất, kể cả cancelled | Không phải phép đo kernel I/O đã rollback |

Sau khi cancel read/write, tài liệu khuyến nghị bỏ buffers hoặc bảo đảm không truy cập chúng khi channel còn mở nếu provider chưa bảo đảm trạng thái. Chính sách dễ kiểm toán là đóng **owned channel** khi request không còn dùng được.

### 5.1. Chương trình 3: Future cancelled và get báo `CancellationException`

Lưu thành `CancelReadFutureDemo.java`:

```java
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousServerSocketChannel;
import java.nio.channels.AsynchronousSocketChannel;
import java.util.concurrent.CancellationException;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class CancelReadFutureDemo {
    public static void main(String[] args) throws Exception {
        try (AsynchronousServerSocketChannel server =
                 AsynchronousServerSocketChannel.open().bind(
                         new InetSocketAddress(InetAddress.getLoopbackAddress(), 0));
             AsynchronousSocketChannel client = AsynchronousSocketChannel.open()) {
            Future<AsynchronousSocketChannel> accepting = server.accept();
            client.connect(server.getLocalAddress()).get(2, TimeUnit.SECONDS);
            try (AsynchronousSocketChannel peer = accepting.get(2, TimeUnit.SECONDS)) {
                ByteBuffer buffer = ByteBuffer.allocate(8);
                Future<Integer> waiting = client.read(buffer);
                boolean cancelled = waiting.cancel(false);
                System.out.println("cancelAccepted=" + cancelled);
                System.out.println("futureCancelled=" + waiting.isCancelled());
                try {
                    waiting.get();
                    throw new AssertionError("expected cancellation");
                } catch (CancellationException expected) {
                    System.out.println("get=CancellationException");
                }
                // Closing, not cancel(false), is the final resource cleanup.
                // Never rely on buffer contents after cancellation.
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 CancelReadFutureDemo.java
java CancelReadFutureDemo
```

Stdout đã kiểm chứng:

```text
cancelAccepted=true
futureCancelled=true
get=CancellationException
```

Peer vẫn mở nhưng không gửi data, vì thế read đang pending trước cancel. `cancel(false)` trong thử nghiệm báo true và Future chuyển cancelled. Không có bước tiếp tục read hoặc inspect buffer; try-with-resources đóng connection. Thử nghiệm **không** khẳng định I/O nền đã dừng chính xác lúc `cancel` được gọi.

## 6. Đóng channel làm pending I/O thất bại

`AsynchronousChannel.close()` có contract: outstanding operations thất bại với `AsynchronousCloseException`. Sau khi đóng, I/O mới thất bại với `ClosedChannelException`. Với Future của operation thất bại, `get` ném `ExecutionException` chứa cause.

Cần phân biệt:
- `CancellationException` khi Future đã cancelled;
- `ExecutionException` với `AsynchronousCloseException` khi kênh đóng trong lúc I/O pending;
- Completion thành công nếu I/O kết thúc **trước** khi close thắng race;
- `ClosedChannelException` khi khởi tạo I/O lúc channel đã đóng.

### 6.1. Chương trình 4: đóng socket có pending read

Lưu thành `ClosePendingReadDemo.java`:

```java
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousCloseException;
import java.nio.channels.AsynchronousServerSocketChannel;
import java.nio.channels.AsynchronousSocketChannel;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ClosePendingReadDemo {
    public static void main(String[] args) throws Exception {
        try (AsynchronousServerSocketChannel server =
                 AsynchronousServerSocketChannel.open().bind(
                         new InetSocketAddress(InetAddress.getLoopbackAddress(), 0));
             AsynchronousSocketChannel client = AsynchronousSocketChannel.open()) {
            Future<AsynchronousSocketChannel> accepting = server.accept();
            client.connect(server.getLocalAddress()).get(2, TimeUnit.SECONDS);
            try (AsynchronousSocketChannel peer = accepting.get(2, TimeUnit.SECONDS)) {
                Future<Integer> pendingRead = client.read(ByteBuffer.allocate(16));
                client.close();
                try {
                    pendingRead.get(2, TimeUnit.SECONDS);
                    throw new AssertionError("read should fail when channel closed");
                } catch (ExecutionException expected) {
                    if (!(expected.getCause() instanceof AsynchronousCloseException)) {
                        throw new AssertionError("unexpected cause", expected);
                    }
                    System.out.println("pendingRead=AsynchronousCloseException");
                }
                System.out.println("clientOpen=" + client.isOpen());
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 ClosePendingReadDemo.java
java ClosePendingReadDemo
```

Stdout đã chạy:

```text
pendingRead=AsynchronousCloseException
clientOpen=false
```

Read đang chờ bytes, `client.close()` làm nó thất bại; `Future.get` bọc AsynchronousCloseException trong ExecutionException. Channel được đóng hai lần qua lệnh close và try-with-resources mà không mở lại. Không xem việc close thành công là bằng chứng remote peer đã xử lý mọi message.

## 7. Đóng listener có `accept` đang pending

`AsynchronousServerSocketChannel.accept()` trả `Future<AsynchronousSocketChannel>` hoặc dùng CompletionHandler, **không có** timed accept overload nhận `timeout` như read/write ở Java 17. Vì vậy `acceptFuture.get(timeout)` chỉ giới hạn waiter. Để kết thúc một listener thuộc quyền sở hữu ứng dụng, đóng `server.close()`.

### 7.1. Chương trình 5: pending accept bị channel close

Lưu thành `ServerAcceptCloseDemo.java`:

```java
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.channels.AsynchronousCloseException;
import java.nio.channels.AsynchronousServerSocketChannel;
import java.nio.channels.AsynchronousSocketChannel;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ServerAcceptCloseDemo {
    public static void main(String[] args) throws Exception {
        try (AsynchronousServerSocketChannel server =
                 AsynchronousServerSocketChannel.open().bind(
                         new InetSocketAddress(InetAddress.getLoopbackAddress(), 0))) {
            Future<AsynchronousSocketChannel> accepting = server.accept();
            server.close();
            try {
                accepting.get(2, TimeUnit.SECONDS);
                throw new AssertionError("accept should fail on close");
            } catch (ExecutionException expected) {
                if (!(expected.getCause() instanceof AsynchronousCloseException)) {
                    throw new AssertionError("unexpected cause", expected);
                }
                System.out.println("pendingAccept=AsynchronousCloseException");
            }
            System.out.println("serverOpen=" + server.isOpen());
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 ServerAcceptCloseDemo.java
java ServerAcceptCloseDemo
```

Stdout đã kiểm chứng:

```text
pendingAccept=AsynchronousCloseException
serverOpen=false
```

Server không có kết nối client khi close, nên outstanding accept thất bại. Trong service thật, một lỗi close chủ đích khi shutdown cần phân biệt với lỗi network bất thường.

## 8. Không có hai outstanding reads/writes/accepts

Sau `Future.get(timeout)`, operation có thể còn pending. Một read mới trên cùng channel khi read cũ chưa xong ném `ReadPendingException`; write mới có thể `WritePendingException`. Listener chỉ nhận một pending accept, còn accept thứ hai có thể `AcceptPendingException`.

### 8.1. Chương trình 6: hai reads trùng nhau

Lưu thành `ReadPendingDemo.java`:

```java
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousCloseException;
import java.nio.channels.AsynchronousServerSocketChannel;
import java.nio.channels.AsynchronousSocketChannel;
import java.nio.channels.ReadPendingException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ReadPendingDemo {
    public static void main(String[] args) throws Exception {
        try (AsynchronousServerSocketChannel server =
                 AsynchronousServerSocketChannel.open().bind(
                         new InetSocketAddress(InetAddress.getLoopbackAddress(), 0));
             AsynchronousSocketChannel client = AsynchronousSocketChannel.open()) {
            Future<AsynchronousSocketChannel> accepting = server.accept();
            client.connect(server.getLocalAddress()).get(2, TimeUnit.SECONDS);
            try (AsynchronousSocketChannel peer = accepting.get(2, TimeUnit.SECONDS)) {
                Future<Integer> first = client.read(ByteBuffer.allocate(8));
                try {
                    client.read(ByteBuffer.allocate(8));
                    throw new AssertionError("second read should not start");
                } catch (ReadPendingException expected) {
                    System.out.println("secondRead=ReadPendingException");
                }
                client.close();
                try {
                    first.get(2, TimeUnit.SECONDS);
                    throw new AssertionError("read must fail on close");
                } catch (ExecutionException expected) {
                    if (!(expected.getCause() instanceof AsynchronousCloseException)) {
                        throw new AssertionError("unexpected cause", expected);
                    }
                    System.out.println("firstRead=AsynchronousCloseException");
                }
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 ReadPendingDemo.java
java ReadPendingDemo
```

Stdout đã chạy:

```text
secondRead=ReadPendingException
firstRead=AsynchronousCloseException
```

**Thiết kế thực tế:** một read loop đảm nhiệm chiều đọc của mỗi TCP connection, parse frame rồi phân phối dữ liệu cho logical requests. Một write queue xử lý từng write, kể cả partial writes. Cho phép một read và một write cùng outstanding nhưng không cho hai reads hoặc hai writes cạnh tranh cùng chiều.

## 9. `InterruptedException` ở waiter không tương đương hủy kênh

Thread chờ `Future.get()` bị `interrupt()` có thể ném `InterruptedException`. Đây là chuyện của **thread đợi**, không phải kết luận underlying I/O đã bị cancel. Khi catch mà không propagate exception, thường cần gọi `Thread.currentThread().interrupt()` để giữ tín hiệu.

### 9.1. Chương trình 7: waiter bị interrupt, accept vẫn chờ

Lưu thành `InterruptedWaitDemo.java`:

```java
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.channels.AsynchronousServerSocketChannel;
import java.nio.channels.AsynchronousSocketChannel;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class InterruptedWaitDemo {
    public static void main(String[] args) throws Exception {
        try (AsynchronousServerSocketChannel server =
                 AsynchronousServerSocketChannel.open().bind(
                         new InetSocketAddress(InetAddress.getLoopbackAddress(), 0))) {
            Future<AsynchronousSocketChannel> pending = server.accept();
            AtomicBoolean wasInterrupted = new AtomicBoolean(false);
            CountDownLatch waiting = new CountDownLatch(1);
            Thread waiter = new Thread(() -> {
                waiting.countDown();
                try {
                    pending.get();
                } catch (InterruptedException expected) {
                    wasInterrupted.set(true);
                    Thread.currentThread().interrupt();
                } catch (Exception other) {
                    throw new AssertionError(other);
                }
            }, "future-waiter");
            waiter.start();
            if (!waiting.await(1, TimeUnit.SECONDS)) {
                throw new AssertionError("waiter did not start");
            }
            waiter.interrupt();
            waiter.join(2000);
            if (waiter.isAlive()) throw new AssertionError("waiter did not stop");
            System.out.println("waitInterrupted=" + wasInterrupted.get());
            System.out.println("acceptStillPending=" + !pending.isDone());

            try (AsynchronousSocketChannel client = AsynchronousSocketChannel.open()) {
                client.connect(server.getLocalAddress()).get(2, TimeUnit.SECONDS);
                try (AsynchronousSocketChannel accepted =
                             pending.get(2, TimeUnit.SECONDS)) {
                    System.out.println("acceptedAfterInterrupt=" + accepted.isOpen());
                }
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 InterruptedWaitDemo.java
java InterruptedWaitDemo
```

Stdout đã kiểm chứng:

```text
waitInterrupted=true
acceptStillPending=true
acceptedAfterInterrupt=true
```

Waiter bị interrupt và khôi phục cờ interrupt của chính nó; không ai gọi cancel hoặc close listener. Future accept vẫn pending và sau đó nhận được kết nối từ client. Không sử dụng interrupt của caller làm biện pháp duy nhất để cleanup socket do mình sở hữu.

## 10. `AsynchronousChannelGroup`: shutdown không giống close channel

Group gom channels để chia sẻ thread pool và completion callbacks. Một group ứng dụng tự tạo có thể dùng `withFixedThreadPool`, `withCachedThreadPool` hoặc `withThreadPool`; channels được bind qua `AsynchronousSocketChannel.open(group)`/`AsynchronousServerSocketChannel.open(group)`.

Kênh `open()` không chỉ định group thì gắn với **default group** do JVM quản lý; không tự shutdown default group vì một request.

### 10.1. Orderly shutdown: `group.shutdown()`

`shutdown()` đánh dấu group không nhận thêm channels. Khi group đã shutdown, cố tạo channel mới bound vào group có thể ném `ShutdownChannelGroupException`. Nhưng channels **đã mở** không bị tự động đóng; group chỉ terminated khi channels đóng, active completion handlers xong và resources giải phóng.

### 10.2. Forceful shutdown: `group.shutdownNow()`

`shutdownNow()` đóng các channels đang mở trong group. Outstanding I/O trên chúng bị ảnh hưởng bởi close. Nhưng Javadoc nêu nó **không cố interrupt các completion handlers đã đang chạy**. Cần `awaitTermination` để chờ group thực sự kết thúc.

### 10.3. `group.awaitTermination`

`awaitTermination(t,unit)` trả true nếu terminated, false nếu hết t trước khi terminated; có thể bị `InterruptedException`. Nó chỉ **chờ**, không tự đổi từ orderly sang forceful shutdown.

## 11. Chương trình 8: orderly shutdown và đóng listener sau đó

Lưu thành `ChannelGroupLifecycleDemo.java`:

```java
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.channels.AsynchronousChannelGroup;
import java.nio.channels.AsynchronousServerSocketChannel;
import java.nio.channels.ShutdownChannelGroupException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class ChannelGroupLifecycleDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger id = new AtomicInteger();
        AsynchronousChannelGroup group = AsynchronousChannelGroup.withFixedThreadPool(
                2, job -> new Thread(job, "io-group-" + id.incrementAndGet()));
        try {
            try (AsynchronousServerSocketChannel listener =
                     AsynchronousServerSocketChannel.open(group).bind(
                             new InetSocketAddress(InetAddress.getLoopbackAddress(), 0))) {
                group.shutdown();
                System.out.println("shutdown=" + group.isShutdown());
                System.out.println("listenerStillOpen=" + listener.isOpen());
                System.out.println("terminatedWhileOpen=" +
                        group.awaitTermination(100, TimeUnit.MILLISECONDS));
                try {
                    AsynchronousServerSocketChannel.open(group).close();
                    throw new AssertionError("new channel should be rejected");
                } catch (ShutdownChannelGroupException expected) {
                    System.out.println("newChannel=ShutdownChannelGroupException");
                }
            }
            System.out.println("terminatedAfterClose=" +
                    group.awaitTermination(3, TimeUnit.SECONDS));
        } finally {
            group.shutdownNow();
            group.awaitTermination(3, TimeUnit.SECONDS);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 ChannelGroupLifecycleDemo.java
java ChannelGroupLifecycleDemo
```

Stdout đã kiểm chứng:

```text
shutdown=true
listenerStillOpen=true
terminatedWhileOpen=false
newChannel=ShutdownChannelGroupException
terminatedAfterClose=true
```

Group đánh dấu shutdown nhưng listener vẫn mở, nên awaitTermination tạm thời false. Sau try-with-resources đóng listener, group mới có thể terminate. `finally` bảo đảm tiếp tục dọn group khi lỗi.

### 11.1. Ownership của executor/thread pool

Nếu ứng dụng tạo group bằng `withThreadPool(ExecutorService)` hoặc `withCachedThreadPool`, executor nên dùng **riêng cho group** theo contract. Javadoc cảnh báo code khác shutdown executor khi group còn hoạt động có thể gây behavior không xác định. Completion handlers nên ngắn để pool không bị starvation và group có thể terminate.

## 12. Chương trình 9: forceful shutdown đóng pending accept

Lưu thành `ChannelGroupForceShutdownDemo.java`:

```java
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.channels.AsynchronousChannelGroup;
import java.nio.channels.AsynchronousCloseException;
import java.nio.channels.AsynchronousServerSocketChannel;
import java.nio.channels.AsynchronousSocketChannel;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ChannelGroupForceShutdownDemo {
    public static void main(String[] args) throws Exception {
        AsynchronousChannelGroup group = AsynchronousChannelGroup.withFixedThreadPool(
                2, runnable -> new Thread(runnable, "group-force-worker"));
        try {
            AsynchronousServerSocketChannel server =
                    AsynchronousServerSocketChannel.open(group).bind(
                            new InetSocketAddress(InetAddress.getLoopbackAddress(), 0));
            try (server) {
                Future<AsynchronousSocketChannel> future = server.accept();
                group.shutdownNow();
                try {
                    future.get(3, TimeUnit.SECONDS);
                    throw new AssertionError("accept should fail on group shutdownNow");
                } catch (ExecutionException expected) {
                    if (!(expected.getCause() instanceof AsynchronousCloseException)) {
                        throw new AssertionError("unexpected cause", expected);
                    }
                    System.out.println("accept=AsynchronousCloseException");
                }
                System.out.println("channelOpen=" + server.isOpen());
            }
            System.out.println("terminated=" +
                    group.awaitTermination(3, TimeUnit.SECONDS));
        } finally {
            group.shutdownNow();
            group.awaitTermination(3, TimeUnit.SECONDS);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 ChannelGroupForceShutdownDemo.java
java ChannelGroupForceShutdownDemo
```

Stdout đã chạy:

```text
accept=AsynchronousCloseException
channelOpen=false
terminated=true
```

`shutdownNow` đóng listener bound vào group, khiến accept outstanding thất bại. Completion handlers đang chạy ở group khác/tác vụ khác có thể làm termination chậm hơn; vì vậy không được khẳng định `shutdownNow` luôn lập tức trả trạng thái terminated.

## 13. `shutdownInput`/`shutdownOutput` là half-close, không phải close

TCP kết nối stream có hai chiều. `shutdownOutput()` báo rằng phía local không gửi thêm bytes, peer có thể đọc hết dữ liệu đã nhận rồi thấy EOF. Kênh local có thể **vẫn mở** để đọc chiều ngược. `shutdownInput()` dừng chiều đọc local. `close()` khác: đóng toàn bộ channel.

### 13.1. TCP là byte stream, không có ranh giới messages

Một write 2 bytes không bắt một read tương ứng trả đúng 2 bytes; một read có thể nhận 1 byte, 2 bytes hoặc nhiều hơn tùy networking/provider. Với giao thức thực cần framing/length-prefix hoặc đọc đến EOF theo hợp đồng protocol.

### 13.2. Chương trình 10: half-close sau khi gửi "OK"

Lưu thành `HalfCloseDemo.java`:

```java
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.nio.channels.AsynchronousServerSocketChannel;
import java.nio.channels.AsynchronousSocketChannel;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class HalfCloseDemo {
    public static void main(String[] args) throws Exception {
        try (AsynchronousServerSocketChannel server =
                 AsynchronousServerSocketChannel.open().bind(
                         new InetSocketAddress(InetAddress.getLoopbackAddress(), 0));
             AsynchronousSocketChannel client = AsynchronousSocketChannel.open()) {
            Future<AsynchronousSocketChannel> accepting = server.accept();
            client.connect(server.getLocalAddress()).get(2, TimeUnit.SECONDS);
            try (AsynchronousSocketChannel peer = accepting.get(2, TimeUnit.SECONDS)) {
                ByteBuffer message = ByteBuffer.wrap("OK".getBytes(StandardCharsets.UTF_8));
                while (message.hasRemaining()) {
                    int written = client.write(message).get(2, TimeUnit.SECONDS);
                    if (written <= 0) throw new AssertionError("no progress");
                }
                client.shutdownOutput();
                ByteBuffer received = ByteBuffer.allocate(8);
                int n = peer.read(received).get(2, TimeUnit.SECONDS);
                int eof = peer.read(received).get(2, TimeUnit.SECONDS);
                received.flip();
                System.out.println("payload=" +
                        StandardCharsets.UTF_8.decode(received));
                System.out.println("firstRead=" + n);
                System.out.println("eofAfterShutdownOutput=" + eof);
                System.out.println("channelStillOpen=" + client.isOpen());
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 HalfCloseDemo.java
java HalfCloseDemo
```

Stdout **đã quan sát** trên JDK 17 tại máy thử:

```text
payload=OK
firstRead=2
eofAfterShutdownOutput=-1
channelStillOpen=true
```

**Không coi firstRead=2 là hợp đồng TCP.** Đó là kết quả trên loopback trong thử nghiệm; trong mạng thật read có thể chỉ nhận một phần. Sửa thành vòng read cho đến khi đủ frame/EOF trong sản phẩm. `client.isOpen=true` sau half-close chỉ cho thấy channel vẫn mở cho chiều khác, không cho phép write thêm sau `shutdownOutput()`.

## 14. `connect` không có timed overload tương tự read/write

`AsynchronousSocketChannel.connect(SocketAddress)` trả `Future<Void>` hoặc nhận CompletionHandler, không có overload `connect(remote, 500, MILLISECONDS)` trực tiếp trên Java 17. Muốn giới hạn chờ connect có thể dùng Future.get:

```java
try (AsynchronousSocketChannel client = AsynchronousSocketChannel.open()) {
    Future<Void> connecting = client.connect(remote);
    connecting.get(connectTimeout, TimeUnit.MILLISECONDS);
    // Chỉ read/write sau khi connect thành công.
} catch (TimeoutException expected) {
    // Future wait timed out; connect may still be pending.
    // try-with-resources closes this owned client.
}
```

Đây là **snippet** với `SocketAddress remote` và `long connectTimeout` đã khai báo, method xử lý IOException, InterruptedException, ExecutionException. Không suy connect timeout đồng nghĩa remote chắc chắn không nhận connection attempt; close owned client nếu không dùng nữa.

Connect TCP thành công chưa có nghĩa handshake TLS hoặc yêu cầu nghiệp vụ đã hoàn thành. Cần deadline cho toàn bộ session/request.

## 15. Deadline tổng dùng `System.nanoTime()`

Để tránh nhiều operation kéo dài quá SLA, hãy lấy mốc thời gian monotonic một lần:

```java
long started = System.nanoTime();
long budgetNanos = TimeUnit.SECONDS.toNanos(2);

// Sau mỗi bước:
long remaining = budgetNanos - (System.nanoTime() - started);
if (remaining <= 0) {
    throw new TimeoutException("overall deadline exceeded");
}
future.get(remaining, TimeUnit.NANOSECONDS);
```

Đây là snippet trong method có xử lý checked exceptions và `Future<?> future` đã khai báo. Không dùng wall-clock `System.currentTimeMillis` để đo elapsed: giờ hệ thống có thể điều chỉnh. Với duration cực lớn cần xử lý overflow; còn budget ngắn vài giây dùng hiệu nanoTime là cách tiếp cận hiện hành.

**Điểm quan trọng:** ngay cả khi Future.get ở đây ném TimeoutException, underlying I/O **chưa tự hủy**. Trên deadline tổng, owner phải chọn close channel, quản lý future/callback và bảo toàn trạng thái request.

### 15.1. Timeout và retry có thể nhân tổng thời gian

Nếu một client cho connect 2 giây, write 2 giây, read 2 giây rồi retry ba lần, tổng có thể rất lớn so với SLA. Deadline tổng phải giảm sau mỗi bước và mỗi retry, có giới hạn attempts/backoff, không reset ngân sách sau lỗi.

### 15.2. Nếu read/write trả một phần

TCP không bảo toàn message boundaries. Một `write` có thể trả count nhỏ hơn số bytes buffer còn lại; dùng `buffer.hasRemaining()` để tiếp tục **sau khi operation cũ hoàn thành**. Một `read` có thể nhận một phần payload; cần parse framing và kiểm tra size. Mỗi bước sử dụng remaining deadline; `read=-1` mới biểu thị EOF, không phải `read=0`.

## 16. CompletionHandler và các cuộc đua

`CompletionHandler.completed`/`failed` có thể được chạy bởi thread trong `AsynchronousChannelGroup`. Không block callback quá lâu bằng `Future.get` vô hạn, Thread.sleep hoặc lock nặng; việc này có thể gây starvation/deadlock và làm group shutdown chậm.

**Timeout race:** timer ở tầng app vừa tuyên bố request TIMED_OUT, I/O callback lại vừa nhận success. Có thể dùng một `AtomicBoolean.compareAndSet(false,true)` để chỉ có **một** bên công bố kết quả. Dù callback thua, nó vẫn có trách nhiệm cleanup socket/accepted channel do nó tạo ra.

**Buffer ownership:** không dùng cùng ByteBuffer cho hai I/O outstanding; sau cancel/timed timeout không tái sử dụng tùy tiện. Cần một read owner và một write owner cho mỗi session; chỉ phát read mới khi callback read cũ hoàn tất và trạng thái cho phép.

### 16.1. State machine minh họa

```text
NEW -> CONNECTING -> OPEN -> HALF_CLOSED -> CLOSING -> CLOSED
           |          |             |
           | failed   | timed-out   | complete
           v          v             v
         CLOSING    CLOSING       CLOSING
```

Đây là model tầng ứng dụng, không phải enum có sẵn trong API Java. Các race có thể xảy ra giữa completion, timeout, cancel và close; code phải bảo đảm single outcome, dọn resources và không vô tình đóng shared listener.

## 17. Bảng lỗi quan trọng

| Exception/trạng thái | Ở đâu | Cách hiểu đúng |
| --- | --- | --- |
| `TimeoutException` | `Future.get(timeout,unit)` | Caller ngừng chờ; I/O có thể còn pending |
| `InterruptedByTimeoutException` | Timed read/write callback failure | I/O timeout; buffer/channel có thể bất định |
| `CancellationException` | `Future.get` sau cancel thành công | Future cancelled, không bảo đảm rollback |
| `InterruptedException` | Thread chờ Future/group bị interrupt | Waiter bị ngắt, I/O không tự cancel |
| `ExecutionException` | Future completion lỗi | Xem `getCause()` |
| `AsynchronousCloseException` | Channel close khi I/O pending | Outstanding operation thất bại |
| `ClosedChannelException` | I/O sau channel close | Channel đã đóng |
| `ReadPendingException` | Read thứ hai đang có read outstanding | Chỉ một read cùng lúc |
| `WritePendingException` | Write thứ hai đang có write outstanding | Chỉ một write cùng lúc |
| `AcceptPendingException` | Accept thứ hai trên listener | Chỉ một accept cùng lúc |
| `NotYetConnectedException` | Read/write trước connect | Connect chưa xong |
| `ConnectionPendingException` | Connect khi connect đang pending | Không connect trùng |
| `ShutdownChannelGroupException` | Mở channel trên group đã shutdown | Group không nhận channel mới |

Ví dụ phân loại `ExecutionException`:

```java
try {
    pending.get(1, TimeUnit.SECONDS);
} catch (ExecutionException failure) {
    Throwable cause = failure.getCause();
    if (cause instanceof AsynchronousCloseException) {
        // Operation may have failed because the channel was closed.
    } else {
        // Handle a different I/O failure.
    }
}
```

Đây là snippet với `Future<?> pending` và imports phù hợp, caller xử lý các checked exceptions khác. **Không** coi mọi ExecutionException đều là timeout/close.

### 17.1. `SO_TIMEOUT` không phải cấu hình deadline chung cho NIO.2 async sockets

`AsynchronousSocketChannel` định nghĩa timed read/write overload riêng, không có socket option `SO_TIMEOUT` kiểu blocking Socket để áp tự động cho mọi I/O. Dùng timed operations, Future wait deadline và deadline tổng đúng tầng.

## 18. Quy trình shutdown service

Nếu ứng dụng sở hữu listener, accepted channels và một custom group:
1. Chuyển trạng thái server sang STOPPING, ngừng nhận công việc mới.
2. Đóng listener để ngừng accept và đánh dấu các accept outstanding.
3. Có thể cho các kết nối đang làm việc một grace period theo deadline tổng.
4. Hết grace: đóng các owned sockets còn mở.
5. Gọi `group.shutdown()` để orderly shutdown, rồi bounded `awaitTermination`.
6. Nếu group chưa terminated khi hết hạn, gọi `group.shutdownNow()` và lại bounded await.
7. Đừng tự shutdown executor mà group đang sử dụng theo một lifecycle khác.
8. Log shutdown errors, callback jobs còn đang thực thi và mọi resources chưa giải phóng; không tuyên bố force-stop đã interrupt handlers.
9. Không tự đóng default group JVM hoặc group dùng chung khi method không sở hữu.

### 18.1. Ownership của kênh và group

Method nhận một `AsynchronousSocketChannel` từ caller **không mặc nhiên** được close channel khi một request ngắn timeout. Contract phải nói rõ ai có quyền close và có multiplex nhiều requests không. Với socket riêng chỉ dành cho một request, try-with-resources và close on deadline thường hợp lý hơn.

## 19. Các hiểu nhầm phổ biến

| Nhầm lẫn | Vì sao sai | Cách đúng |
| --- | --- | --- |
| `get(timeout)` là timeout I/O | Chỉ hạn chế waiter | Timed read/write hoặc close owned channel |
| Timeout get tự cancel `accept` | Accept vẫn pending | Giữ Future hoặc close listener |
| Future cancelled là bytes rollback | Underlying I/O không bảo đảm hủy | Protocol ACK/idempotency |
| `cancel(true)` không ảnh hưởng channel | Có thể close channel | Tính tới các I/O khác |
| Timed read timeout là buffer còn nguyên | Buffer state không xác định | Discard/close, không retry mù |
| Interrupt waiter tự đóng socket | Không tự cancel underlying I/O | Ownership cleanup |
| Hai reads trên một socket được phép | ReadPendingException | Một read loop |
| Group.shutdown đóng mọi channel | Không | Close channels, await |
| shutdownNow interrupt mọi callback | Không bảo đảm | Không block callback, bounded await |
| `shutdownOutput` giống `close` | Half-close một chiều | Chọn theo protocol |
| TCP write là message boundary | TCP là stream | Framing và read loop |
| SO_TIMEOUT là giải pháp cho async | Không phải API đúng | Timed overload/deadline |
| Mỗi retry có timeout mới | Tổng vượt SLA | Remaining budget từ một mốc |
| Close là peer ACK | Không có nghĩa peer đã xử lý | Application ACK/idempotency |

## 20. Checklist code review

1. Đang sử dụng đúng `AsynchronousSocketChannel`/`AsynchronousServerSocketChannel`?
2. `Future.get` timeout có bị nhầm là cancel I/O?
3. Có code xử lý Future còn pending sau wait timeout?
4. Có gọi accept/read/write thứ hai khi operation cũ chưa hoàn tất?
5. Có dùng deadline tổng cho connect, read, write, frame parsing và retry?
6. Deadline dùng `System.nanoTime` thay vì wall-clock?
7. Timed read/write xử lý `InterruptedByTimeoutException` ở callback?
8. Sau timeout/cancel có tránh reuse ByteBuffer/channel thiếu căn cứ?
9. Có biết `cancel(true)` có thể làm channel đóng?
10. Có phân biệt `CancellationException` và `TimeoutException`?
11. `InterruptedException` của waiter có được propagate/restore flag?
12. I/O failure qua Future có xem `ExecutionException.getCause()`?
13. Resource ownership của socket và listener có rõ?
14. Accepted socket không còn owner sau race có được close?
15. Có serialize writes và xử lý partial progress?
16. Có một read loop và framing phù hợp?
17. Callback có tránh blocking operations kéo dài?
18. Có single-completion guard khi timer và callback đua nhau?
19. Có dùng `shutdown()` đúng (không tự đóng channels)?
20. Có xử lý `shutdownNow` và bounded `awaitTermination`?
21. Có tránh đóng group/executor do người khác sở hữu?
22. Có phân biệt `shutdownOutput` với close?
23. Retry side-effect request có idempotency/ACK?
24. Test dùng loopback và port 0, không phụ thuộc DNS/Internet?
25. Có đóng mọi channel/group để JVM không treo?
26. Có log lỗi phân loại và không lộ thông tin nhạy cảm?

## 21. Câu hỏi tự kiểm tra

**1.** `Future.get(100,MILLISECONDS)` timeout có stop read? — **Không**, chỉ waiter ngừng chờ.

**2.** Timed read báo gì? — `InterruptedByTimeoutException` trong failure callback.

**3.** Timed read/write có Future overload nhận timeout trực tiếp? — **Không**, các overload timed dùng CompletionHandler.

**4.** Buffer sau timed timeout có đáng tin? — Không nhất thiết; state có thể không xác định.

**5.** `cancel(false)` thành công là I/O đã rollback? — **Không**.

**6.** `cancel(true)` có thể làm gì? — Có thể **đóng channel**.

**7.** `Future.get` sau cancel thành công ném gì? — `CancellationException`.

**8.** Channel close khi read pending làm Future lỗi gì? — `ExecutionException` với cause `AsynchronousCloseException`.

**9.** Có thể khởi tạo read mới khi read cũ chưa kết thúc? — Không, `ReadPendingException`.

**10.** Thread chờ `Future.get` bị interrupt có tự cancel Future? — **Không**.

**11.** `group.shutdown()` có tự đóng listener? — **Không**.

**12.** `group.shutdownNow()` có interrupt callback đang chạy? — Không bảo đảm.

**13.** `group.awaitTermination` hết hạn trả gì? — `false`.

**14.** `shutdownOutput()` đóng cả kênh? — Không, half-close chiều gửi.

**15.** Một `write` 2 bytes có buộc một `read` trả 2 bytes? — Không; TCP là byte stream.

**16.** Vì sao cần deadline tổng? — Các timeout lẻ/retries có thể cộng dồn vượt SLA.

**17.** Retry một request đã write timeout cần gì? — Protocol ACK, idempotency/reconciliation.

**18.** Khi nào `InterruptedByTimeoutException` khác `TimeoutException`? — Đầu tiên do **timed I/O**, thứ hai do **caller wait**.

**19.** Vì sao `acceptStillPending` có thể true sau get timeout? — Vì get không cancel accept.

**20.** Vì sao không đóng shared listener trong helper timeout? — Resource không thuộc quyền sở hữu của helper.

## 22. Bài tập thực hành

### A. Timeout chờ Future

Chạy `FutureWaitDeadlineDemo`, giảm 100 ms thành 50 ms. Giải thích vì sao accept vẫn có thể nhận kết nối.

### B. Timed read thật

Chạy `TimedReadHandlerDemo`, tăng timeout lên 300 ms; phân biệt CountDownLatch timeout và `InterruptedByTimeoutException`.

### C. Cancel Future

Chạy `CancelReadFutureDemo`, kiểm tra isCancelled. Trình bày vì sao không khẳng định bytes đã được rollback.

### D. Channel close

Chạy `ClosePendingReadDemo` và `ServerAcceptCloseDemo`. Phân loại `ExecutionException.getCause()`.

### E. Outstanding limit

Chạy `ReadPendingDemo`, thiết kế read loop chỉ gửi read mới khi callback cũ hoàn tất.

### F. Waiter interrupt

Chạy `InterruptedWaitDemo`. Vì sao restore interrupt flag không tự đóng listener?

### G. Group shutdown

Chạy `ChannelGroupLifecycleDemo` và `ChannelGroupForceShutdownDemo`. Đối chiếu shutdown, shutdownNow, awaitTermination.

### H. Half-close

Chạy `HalfCloseDemo` và sửa thành vòng lặp read đến EOF để không phụ thuộc firstRead=2.

### I. Deadline tổng

Thiết kế connect → write → read response với một budget 2 giây, giảm theo `System.nanoTime()` và đóng socket do request sở hữu khi hết hạn.

### J. Callback race

Dùng `AtomicBoolean.compareAndSet(false,true)` để timer và I/O callback không cùng hoàn tất một request hai lần.

## 23. Tài liệu chính thức Java SE 17

- [AsynchronousChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousChannel.html): cancellation và close semantics.
- [AsynchronousSocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousSocketChannel.html): timed read/write, error state, shutdown input/output.
- [AsynchronousServerSocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousServerSocketChannel.html): accept pending.
- [AsynchronousChannelGroup](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousChannelGroup.html): shutdown, shutdownNow, awaitTermination.
- [CompletionHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/CompletionHandler.html): completed/failed.
- [Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): get/cancel/isDone/isCancelled.
- [TimeUnit](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/TimeUnit.html): đơn vị thời gian.
- [InterruptedByTimeoutException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/InterruptedByTimeoutException.html): timeout của I/O.
- [AsynchronousCloseException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousCloseException.html): close khi I/O outstanding.

**Ghi nhớ:** `Future.get(timeout)` chỉ chặn **thời gian chờ của caller**; timed read/write có semantics riêng và nguy cơ buffer/channel state không xác định; `cancel` không bảo đảm kernel I/O dừng ngay; `close` là hành động kết thúc resource theo ownership; `shutdown`/`shutdownNow` của group có phạm vi khác nhau. Kết hợp deadline tổng, một read/write pending mỗi chiều, quản lý CompletionHandlers, đóng tài nguyên đúng owner và retry idempotent để xây ứng dụng mạng bất đồng bộ Java an toàn.
