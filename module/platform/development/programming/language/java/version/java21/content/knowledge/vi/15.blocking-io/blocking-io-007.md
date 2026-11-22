# Truyền cancellation qua lời gọi I/O có hỗ trợ interruption

Trong Java, yêu cầu hủy một tác vụ thường được truyền qua cơ chế interrupt. Khi task đang chờ một thao tác I/O có hỗ trợ interruption, interrupt có thể đánh thức thread đang chờ để task kết thúc và giải phóng tài nguyên. Tuy nhiên, không phải mọi API I/O đều phản hồi `Thread.interrupt()` theo cùng một cách.

Với các channel triển khai `InterruptibleChannel`, nếu thread bị interrupt khi đang block trong thao tác I/O, channel sẽ bị đóng, trạng thái interrupt được giữ và thao tác ném `ClosedByInterruptException`. Java 21 còn có hành vi riêng cho socket I/O chạy trên virtual thread. Cần phân biệt các trường hợp này với `InputStream`/`Reader` thông thường, thao tác đóng channel từ thread khác và việc hủy `Future`.

## 1. Cancellation và interruption là hai khái niệm liên quan

Cancellation là quyết định ở tầng ứng dụng rằng một công việc không cần tiếp tục. Interruption là tín hiệu hợp tác của Java để yêu cầu thread dừng chờ hoặc kiểm tra xem nó có nên kết thúc hay không.

Một luồng hủy điển hình có thể diễn ra như sau:

```text
Người gọi yêu cầu hủy
        |
        v
Future.cancel(true) hoặc shutdownNow()
        |
        v
Worker nhận interrupt
        |
        v
Thao tác I/O có hỗ trợ interruption được đánh thức
        |
        v
Task dọn dẹp tài nguyên và kết thúc
```

Interrupt không phải lệnh cưỡng bức kết thúc thread. Task phải chạy qua một điểm có thể nhận interrupt, kiểm tra trạng thái interrupt hoặc xử lý exception do thao tác blocking phát sinh. Nếu task đang gọi API không hỗ trợ interruption, tín hiệu có thể không làm lời gọi đó kết thúc ngay.

## 2. Cách hoạt động của interrupt status

Mỗi thread có trạng thái interrupt. Có thể gửi yêu cầu interrupt cho thread khác bằng `interrupt()` và kiểm tra trạng thái bằng `isInterrupted()`:

```java
Thread worker = Thread.ofPlatform().start(() -> {
    while (!Thread.currentThread().isInterrupted()) {
        doSmallUnitOfWork();
    }

    releaseResources();
});

worker.interrupt();
```

`isInterrupted()` chỉ đọc trạng thái và không xóa nó. Ngược lại, `Thread.interrupted()` là phương thức static kiểm tra trạng thái của thread hiện tại rồi xóa trạng thái interrupt:

```java
if (Thread.interrupted()) {
    // Đã nhận interrupt; trạng thái hiện tại đã bị xóa.
}
```

Không gọi `Thread.interrupted()` chỉ để kiểm tra một cách tùy tiện. Việc xóa trạng thái có thể khiến tầng gọi phía trên không còn nhận biết yêu cầu hủy.

Các phương thức blocking như `Thread.sleep`, `Object.wait`, `Thread.join` và nhiều phương thức của `BlockingQueue` phản hồi interrupt bằng cách ném `InterruptedException`. Khi exception này được truyền lên tầng gọi, tầng đó có thể quyết định kết thúc tác vụ. Nếu không thể truyền exception ra ngoài, hãy khôi phục trạng thái interrupt:

```java
try {
    queue.take();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
}
```

Đối với các thao tác I/O của `InterruptibleChannel`, tín hiệu interrupt được biểu diễn bằng một exception I/O khác; không nên chờ `InterruptedException` từ `read()` hoặc `write()` của channel.

## 3. I/O trên InterruptibleChannel

`java.nio.channels.InterruptibleChannel` là hợp đồng cho các channel có thể bị đóng do interruption. Các channel như `SocketChannel`, `FileChannel` và `DatagramChannel` triển khai hợp đồng này.

Theo hợp đồng của `InterruptibleChannel`, nếu một thread bị interrupt khi đang block trong thao tác I/O trên channel:

1. Channel bị đóng.
2. Trạng thái interrupt của thread được đặt.
3. Thao tác I/O kết thúc bằng `ClosedByInterruptException`.

`ClosedByInterruptException` là một subclass của `AsynchronousCloseException`. Nó cho biết channel bị đóng do chính thread đang thực hiện I/O nhận interrupt.

Ví dụ đọc từ `SocketChannel` ở chế độ blocking:

```java
import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.ClosedByInterruptException;
import java.nio.channels.SocketChannel;

static void readFromServer() throws IOException {
    try (SocketChannel channel = SocketChannel.open()) {
        channel.connect(new InetSocketAddress("localhost", 9000));

        ByteBuffer buffer = ByteBuffer.allocate(4096);
        while (channel.read(buffer) != -1) {
            buffer.flip();
            consume(buffer);
            buffer.clear();
        }
    } catch (ClosedByInterruptException e) {
        // Channel đã bị đóng và interrupt status đã được đặt.
        // Truyền tiếp để tầng gọi nhận biết thao tác I/O bị hủy.
        throw e;
    }
}

static void consume(ByteBuffer buffer) {
    // Xử lý dữ liệu đã đọc.
}
```

Khi `channel.read(buffer)` đang block và thread bị interrupt, channel bị đóng. Khối `try-with-resources` vẫn đảm bảo đóng tài nguyên khi thoát khỏi phương thức; việc đóng thêm một lần trên channel đã đóng là an toàn.

### Phân biệt các exception khi channel kết thúc

| Tình huống | Kết quả thường gặp |
|---|---|
| Thread đang block trong channel I/O nhận interrupt | `ClosedByInterruptException`; interrupt status được đặt và channel đóng |
| Một thread khác đóng channel trong khi thread hiện tại đang block I/O | `AsynchronousCloseException` |
| Gọi thao tác trên channel đã đóng trước đó | Thường là `ClosedChannelException` |
| Đọc từ channel và đầu vào đã kết thúc bình thường | Phương thức đọc có thể trả `-1`, tùy loại channel |

Không gộp mọi trường hợp thành `InterruptedException`. Với channel, `ClosedByInterruptException` là tín hiệu quan trọng để nhận diện việc I/O bị ngắt do interrupt.

## 4. Truyền cancellation từ Future tới I/O

Khi task được submit vào executor, `Future.cancel(true)` yêu cầu hủy task. Nếu task đang chạy, tham số `true` cho phép executor gửi interrupt tới thread thực thi task. Nếu task đang block trên `InterruptibleChannel`, interrupt có thể khiến channel đóng và I/O ném `ClosedByInterruptException`.

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.SocketChannel;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

try (ExecutorService executor = Executors.newFixedThreadPool(2)) {
    Future<?> readTask = executor.submit(() -> {
        try (SocketChannel channel = SocketChannel.open(
                new InetSocketAddress("localhost", 9000))) {
            ByteBuffer buffer = ByteBuffer.allocate(4096);
            while (channel.read(buffer) != -1) {
                buffer.clear();
            }
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    });

    // Khi nghiệp vụ không cần kết quả đọc nữa:
    readTask.cancel(true);
}
```

`cancel(true)` là yêu cầu hủy, không phải bảo đảm task đã dừng ngay khi phương thức trả về. `Future` chuyển sang trạng thái cancelled; thread đang chạy nhận interrupt và phải có cơ hội thoát khỏi thao tác blocking cũng như hoàn tất cleanup. Nếu task dùng API I/O không hỗ trợ interruption, nó có thể tiếp tục chạy.

Nếu cần quan sát lỗi nghiệp vụ của task chưa bị hủy, giữ `Future` và gọi `get()`. Khi `cancel(true)` thành công, lời gọi `get()` ném `CancellationException`; nó không trả về `ClosedByInterruptException` của worker. Exception ở worker là nguyên nhân ở tầng I/O, còn `CancellationException` là trạng thái ở API `Future`.

`ExecutorService.shutdownNow()` cũng yêu cầu interrupt các task đang chạy. Ngược lại, `shutdown()` và `ExecutorService.close()` thực hiện shutdown có trật tự, cho task đã submit tiếp tục hoàn tất; không dùng chúng với kỳ vọng interrupt ngay các lời gọi I/O đang block.

## 5. Đóng channel từ thread sở hữu để hủy I/O

Không phải lúc nào thread đang chờ I/O cũng là nơi nhận được interrupt. Một cách hủy khác là thread quản lý tài nguyên đóng channel. Nếu một thread đang block trên channel và thread khác gọi `close()`, thao tác đang chờ sẽ được đánh thức và thường kết thúc bằng `AsynchronousCloseException`.

Mẫu này hữu ích khi một thành phần sở hữu channel và cần hủy hoạt động của worker:

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousCloseException;
import java.nio.channels.ClosedByInterruptException;
import java.nio.channels.SocketChannel;

final class ChannelReader implements Runnable {
    private final SocketChannel channel;

    ChannelReader(SocketChannel channel) {
        this.channel = channel;
    }

    @Override
    public void run() {
        ByteBuffer buffer = ByteBuffer.allocate(4096);
        try {
            while (channel.read(buffer) != -1) {
                buffer.clear();
            }
        } catch (ClosedByInterruptException e) {
            // Interrupt status đã được đặt; channel bị đóng do interrupt.
            handleCancellation(e);
        } catch (AsynchronousCloseException e) {
            // Một thread khác đã đóng channel trong khi worker đang chờ.
            handleCancellation(e);
        } catch (IOException e) {
            handleReadFailure(e);
        }
    }

    void cancel() throws IOException {
        channel.close();
    }

    private void handleReadFailure(IOException error) {
        // Ghi nhận hoặc chuyển lỗi lên tầng gọi.
    }

    private void handleCancellation(IOException reason) {
        // Dọn dẹp hoặc ghi nhận cancellation theo chính sách ứng dụng.
    }
}
```

Khi `cancel()` đóng channel, worker đang đọc có thể nhận `AsynchronousCloseException`. Nếu worker bị interrupt, nó có thể nhận `ClosedByInterruptException`. Cả hai trường hợp đều cần được xem xét trong logic cleanup và logging; không nên ghi nhận chúng như lỗi kết nối thông thường nếu đó là kết quả của một yêu cầu hủy có chủ đích.

Đóng channel là hành động ảnh hưởng tới tất cả người dùng channel đó. Nếu nhiều task chia sẻ cùng một channel, hủy một task bằng cách đóng channel có thể làm các task khác thất bại. Cách thiết kế dễ kiểm soát nhất là để task sở hữu channel riêng hoặc có một thành phần quản lý vòng đời channel rõ ràng.

## 6. Socket API và khác biệt giữa platform thread với virtual thread

Không phải API socket nào cũng có cùng hành vi interruption trên mọi loại thread. Java 21 có hỗ trợ riêng cho blocking socket I/O chạy trên virtual thread.

| API và môi trường | Hành vi khi thread bị interrupt lúc đang block |
|---|---|
| `SocketChannel`/`FileChannel` triển khai `InterruptibleChannel` | Channel đóng; thao tác I/O ném `ClosedByInterruptException`; interrupt status được đặt |
| `Selector.select()` | Trả về ngay và giữ interrupt status; không đồng nghĩa mọi channel đã đăng ký bị đóng |
| Blocking I/O của `Socket`, `ServerSocket`, `DatagramSocket` trên virtual thread trong Java 21 | Virtual thread được đánh thức; socket tương ứng bị đóng và thao tác kết thúc bằng `SocketException` |
| Blocking I/O trên các API `InputStream`/`Reader` tổng quát | Không có bảo đảm chung rằng `Thread.interrupt()` sẽ hủy lời gọi I/O |

JEP 444 bổ sung khả năng interrupt các thao tác blocking trên socket khi được gọi từ virtual thread, gồm `Socket.connect`, đọc từ `Socket.getInputStream()`, ghi vào `Socket.getOutputStream()`, `ServerSocket.accept()` và `DatagramSocket.receive()`. Nếu virtual thread bị interrupt trong lúc chờ một trong các thao tác này, thread được đánh thức bằng `SocketException` và socket tương ứng bị đóng. Hành vi này giúp cancellation hoạt động tự nhiên hơn trong mã blocking viết theo kiểu tuần tự.

Không suy rộng hành vi của virtual thread sang platform thread. Với blocking I/O của `java.net.Socket` trên platform thread, hãy dùng `Socket.close()` từ thành phần sở hữu hoặc timeout phù hợp để đánh thức lời gọi đang chờ; không giả định `Thread.interrupt()` đơn thuần sẽ hủy được mọi lời gọi.

Ví dụ với virtual thread:

```java
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.Socket;

Thread client = Thread.ofVirtual().start(() -> {
    try (Socket socket = new Socket()) {
        socket.connect(new InetSocketAddress("localhost", 9000));
        int value = socket.getInputStream().read();
        System.out.println(value);
    } catch (IOException e) {
        // Có thể là SocketException do virtual thread bị interrupt.
        handleSocketFailure(e);
    }
});

// Khi không cần client tiếp tục đọc:
client.interrupt();
```

Nếu cần phân biệt cancellation với lỗi mạng, tầng ứng dụng nên theo dõi trạng thái yêu cầu hủy và phân loại exception dựa trên ngữ cảnh đó. Không nên xem mọi `SocketException` là cancellation, vì lỗi kết nối hoặc lỗi socket khác cũng có thể tạo ra exception này.

## 7. Selector và thao tác I/O non-blocking

Với `SelectableChannel` ở chế độ non-blocking, thao tác đọc/ghi thường trả về ngay thay vì chờ dữ liệu. Một thread có thể đợi sự kiện bằng `Selector.select()`.

Nếu thread đang block trong `select()` nhận interrupt, `select()` trả về ngay và trạng thái interrupt được đặt. Cơ chế này tương tự việc gọi `wakeup()` để đánh thức selector, nhưng không có nghĩa các channel đã đăng ký bị đóng:

```java
import java.nio.channels.Selector;

try (Selector selector = Selector.open()) {
    while (!Thread.currentThread().isInterrupted()) {
        int ready = selector.select();

        if (Thread.currentThread().isInterrupted()) {
            break;
        }

        if (ready == 0) {
            continue;
        }

        processSelectedKeys(selector);
    }
}
```

Ứng dụng dùng selector cần kiểm tra interrupt status sau khi `select()` trả về và kết thúc vòng lặp theo chính sách cancellation. Nếu muốn đóng các channel đã đăng ký, cần thực hiện cleanup riêng. Với ứng dụng cần deadline hoặc timeout, có thể dùng `select(timeout)` và kiểm tra lại trạng thái công việc sau mỗi lần thức dậy.

## 8. Khi API I/O không hỗ trợ interruption

Các API I/O truyền thống như `InputStream.read()` hoặc `Reader.read()` không đưa ra một bảo đảm chung rằng interrupt sẽ đánh thức thread đang chờ. Hành vi thực tế phụ thuộc implementation và loại tài nguyên. Với socket I/O trên platform thread, đóng socket từ thread quản lý là cách hủy được hỗ trợ; với một số nguồn dữ liệu khác, cần dùng timeout hoặc API có cơ chế hủy riêng.

Các hướng xử lý thường dùng:

- **Đóng tài nguyên từ thread sở hữu:** đóng `Socket`, channel hoặc stream để giải phóng thread đang chờ, theo hợp đồng của API cụ thể.
- **Đặt timeout:** dùng timeout kết nối/đọc mà API hỗ trợ để lời gọi có thể kết thúc trong thời gian giới hạn.
- **Dùng NIO interruptible channel:** chọn `SocketChannel`, `FileChannel` hoặc channel phù hợp khi muốn dùng interrupt như một tín hiệu hủy.
- **Dùng API asynchronous có cancellation riêng:** theo dõi `Future` hoặc handle trả về từ API đó và gọi phương thức hủy/đóng được tài liệu hóa.
- **Chia nhỏ công việc:** nếu API cho phép đọc theo từng phần, kiểm tra trạng thái interrupt giữa các lần đọc; cách này không giải phóng được một lần đọc đang block nếu bản thân lời gọi không hỗ trợ hủy.

Không bọc một API không interruptible trong `Future` rồi cho rằng `cancel(true)` sẽ tự giải phóng I/O. `Future.cancel(true)` chỉ gửi tín hiệu interrupt; API đang block vẫn phải hỗ trợ hoặc phải được đóng bằng một cơ chế khác.

Ví dụ, với `Socket` chạy trên platform thread, có thể đặt timeout cho kết nối và thao tác đọc:

```java
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.Socket;

try (Socket socket = new Socket()) {
    socket.connect(new InetSocketAddress("localhost", 9000), 5_000);
    socket.setSoTimeout(5_000);
    int value = socket.getInputStream().read();
}
```

`connect(..., timeout)` giới hạn thời gian thiết lập kết nối; `setSoTimeout` giới hạn thời gian chờ cho thao tác đọc từ socket. Khi hết thời gian, thao tác đọc ném `SocketTimeoutException`. Timeout giúp lời gọi tự kết thúc trong thời gian hữu hạn, nhưng không giống interrupt và không tự biểu diễn một yêu cầu cancellation của nghiệp vụ.

## 9. Nguyên tắc xử lý exception và cleanup

Khi truyền cancellation qua nhiều tầng, cần giữ nguyên ý nghĩa của tín hiệu hủy:

1. Không bắt `InterruptedException` rồi bỏ qua. Nếu không thể truyền tiếp, khôi phục trạng thái interrupt bằng `Thread.currentThread().interrupt()`.
2. Với `ClosedByInterruptException`, hợp đồng channel đã đặt interrupt status. Hãy truyền tiếp hoặc chuyển thành trạng thái cancellation của ứng dụng mà không xóa cờ interrupt.
3. Phân biệt `AsynchronousCloseException` do một thread khác đóng tài nguyên với `ClosedByInterruptException` do thread đang I/O bị interrupt.
4. Đặt việc đóng channel/socket trong thành phần sở hữu vòng đời tài nguyên. Không để nhiều task cùng đóng một tài nguyên mà không có quy tắc rõ ràng.
5. Đảm bảo `finally` hoặc try-with-resources giải phóng buffer, channel, socket và tài nguyên liên quan khi task kết thúc bất thường.
6. Không tìm cách cưỡng bức kết thúc thread. Cancellation an toàn cần dựa vào interrupt, đóng tài nguyên theo đúng hợp đồng hoặc cơ chế hủy riêng của API.

Ví dụ giữ đúng interrupt status khi chuyển exception sang tầng ứng dụng:

```java
static void readData(SocketChannel channel) throws IOException {
    try {
        ByteBuffer buffer = ByteBuffer.allocate(1024);
        while (channel.read(buffer) >= 0) {
            buffer.clear();
        }
    } catch (ClosedByInterruptException e) {
        // Interrupt status đã được đặt theo hợp đồng InterruptibleChannel.
        throw e;
    }
}
```

Không cần gọi `Thread.currentThread().interrupt()` lần nữa trong catch này vì channel đã đặt trạng thái interrupt. Nếu tầng xử lý khác chủ động xóa trạng thái bằng `Thread.interrupted()`, tầng đó phải có lý do rõ ràng và tự chịu trách nhiệm truyền tiếp thông tin cancellation.

## 10. Checklist truyền cancellation qua I/O

- [ ] Đã xác định API I/O cụ thể có hỗ trợ interruption hay không.
- [ ] Với `InterruptibleChannel`, đã xử lý `ClosedByInterruptException` và hiểu rằng channel bị đóng.
- [ ] Đã phân biệt interrupt với việc một thread khác gọi `close()`.
- [ ] Đã hiểu `Future.cancel(true)` chỉ gửi yêu cầu interrupt, không bảo đảm task dừng ngay.
- [ ] Không dùng `shutdown()` hoặc `ExecutorService.close()` với kỳ vọng interrupt task đang chạy.
- [ ] Với socket I/O, đã xét riêng platform thread và virtual thread theo Java 21.
- [ ] Với selector, kiểm tra interrupt status sau khi `select()` trả về và cleanup channel riêng.
- [ ] Với API không hỗ trợ interruption, đã có timeout hoặc cơ chế đóng/hủy riêng.
- [ ] Không nuốt `InterruptedException` hoặc xóa interrupt status ngoài ý muốn.
- [ ] Tài nguyên có chủ sở hữu rõ ràng và luôn được đóng khi cancellation xảy ra.

## Tài liệu tham khảo

- [InterruptibleChannel — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/InterruptibleChannel.html): hợp đồng đóng channel và `ClosedByInterruptException` khi thread đang block nhận interrupt.
- [ClosedByInterruptException — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/ClosedByInterruptException.html): exception báo channel bị đóng do interruption.
- [AsynchronousCloseException — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/AsynchronousCloseException.html): exception khi channel bị đóng trong lúc thread khác đang block I/O.
- [Selector — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/Selector.html): hành vi `select()` khi thread bị interrupt hoặc selector được wakeup.
- [Socket — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/Socket.html): blocking socket I/O, timeout và hành vi đóng socket.
- [JEP 444: Virtual Threads](https://openjdk.org/jeps/444): hỗ trợ interrupt cho blocking socket I/O trên virtual thread trong Java 21.
- [Future — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html): hợp đồng `cancel(boolean)` và trạng thái cancellation của task.
