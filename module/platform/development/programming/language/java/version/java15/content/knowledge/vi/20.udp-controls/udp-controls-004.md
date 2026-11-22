# Đóng hoặc hủy tác vụ UDP đang chờ I/O theo đúng hợp đồng API (Java 15+)

## 1. Tại sao “hủy tác vụ” không đồng nghĩa “ngắt lời gọi receive”?

UDP là giao thức truyền datagram **không thiết lập luồng kết nối kiểu TCP**. Một chương trình Java có thể gửi datagram, rồi chờ nhận datagram bằng `DatagramSocket.receive(DatagramPacket)` hoặc `DatagramChannel.receive(ByteBuffer)`. Nếu không có gói đến, luồng nhận có thể chờ rất lâu hoặc vô thời hạn.

Khi ứng dụng cần dừng service, hủy một request, đổi cấu hình hoặc tắt listener, dễ xuất hiện các cách làm thiếu chính xác:

```java
// Minh họa CÁCH KHÔNG ĐỦ CHẮC CHẮN trong một ứng dụng có sẵn các biến.
future.cancel(true);          // Chưa chắc giải phóng được mọi loại UDP receive.
running = false;              // Chỉ đổi cờ; không tự đánh thức syscall đang chờ.
receiverThread.interrupt();   // Hành vi phụ thuộc API/socket/channel và kiểu thread.
```

Các biến trên chỉ minh họa, **không phải chương trình độc lập**. Một tác vụ được đánh dấu “cancelled” trong `Future` vẫn có thể còn mã đang chạy, hoặc một thread còn bị kẹt trong lời gọi I/O. Để dừng đúng, phải đọc **hợp đồng của đúng API đang sử dụng**.

Bài học tập trung vào bốn cơ chế hiện hành:

1. **`DatagramSocket.close()`:** đóng tài nguyên socket; luồng đang bị chặn trong `DatagramSocket.receive()` được đánh thức bằng `SocketException`.
2. **`DatagramSocket.setSoTimeout(milliseconds)`:** đặt thời gian chờ tối đa cho **mỗi lời gọi receive**; hết hạn ném `SocketTimeoutException`, **socket vẫn dùng được**.
3. **`DatagramChannel` và interrupt/close:** một `InterruptibleChannel`; interrupt luồng đang chặn có thể **đóng channel** và ném `ClosedByInterruptException`; thread khác đóng channel có thể làm receive ném `AsynchronousCloseException`.
4. **`Selector.wakeup()`:** đánh thức vòng chọn NIO mà **không tự đóng** `Selector` hay `DatagramChannel`; thích hợp để thông báo thay đổi trạng thái cho event loop.

Đây là các hợp đồng khác nhau về **tài nguyên còn mở hay đã đóng**, **loại ngoại lệ** và **khả năng tái sử dụng**. Không nên gộp mọi thao tác thành một hàm `cancel()` rồi đoán hậu quả giống nhau.

## 2. Phân biệt tác vụ, thread, socket, channel và selector

Một ứng dụng UDP có nhiều lớp đối tượng:

```text
Ứng dụng nhận lệnh stop/cancel
          |
          +--> Cờ running / lifecycle state
          |
          +--> Future / ExecutorService / Thread
          |           |
          |           +--> mã công việc đang chạy
          |                       |
          |                       +--> DatagramSocket.receive(packet)
          |                       |             hoặc
          |                       +--> DatagramChannel.receive(buffer)
          |
          +--> socket/channel là tài nguyên I/O
          |
          +--> Selector.select(...) (nếu dùng NIO non-blocking)
```

Cần xác định **đang muốn hủy thứ gì**:

- **Hủy nhu cầu xử lý**: một client không còn muốn kết quả; đánh dấu future cancelled có thể đủ về mặt logic, nhưng chưa chắc dừng được I/O phía sau.
- **Dừng một lần chờ**: muốn thread thoát khỏi `receive` hay `select`. Phải có cơ chế được API hứa hẹn đánh thức.
- **Đóng vĩnh viễn listener UDP**: thường cần thay đổi cờ chạy, rồi **close** socket/channel; sau đó chờ thread thực sự kết thúc.
- **Giữ socket để tiếp tục xử lý**: không nên close một socket dùng chung chỉ vì một request hết hạn; dùng **timeout, non-blocking selector, hoặc quản lý request timeout riêng**.

**UDP không có dấu hiệu EOF như đọc TCP stream.** Đừng mong `receive()` trả `-1` khi “đối tác đóng kết nối”: UDP không có luồng byte có EOF. Nếu ứng dụng cần thông điệp shutdown trên UDP, đó là **giao thức ứng dụng** tự định nghĩa; việc đặt `running=false` cũng không tự tạo datagram để làm lời gọi đang chờ trở về.

## 3. Ma trận hợp đồng API hiện hành

| API và thao tác | Khi đang chờ I/O | Có đóng tài nguyên không? | Khi nào dùng? |
|---|---|---|---|
| `DatagramSocket.close()` | `receive(packet)` đang block được đánh thức và ném `SocketException` | **Có**, socket đóng | Shutdown listener/socket thuộc quyền sở hữu của tác vụ |
| `DatagramSocket.setSoTimeout(t)` với `t > 0` | `receive` ném `SocketTimeoutException` nếu hết t mà không nhận gói | **Không**; socket vẫn hợp lệ | Poll trạng thái, deadline ngắn theo từng lần receive |
| `DatagramSocket.setSoTimeout(0)` | Không có timeout do `SO_TIMEOUT` | Không | Chỉ dùng khi có cơ chế stop khác đáng tin |
| `DatagramChannel.close()` từ thread khác | I/O channel đang block nhận `AsynchronousCloseException` theo hợp đồng `InterruptibleChannel` | **Có**, channel đóng | Shutdown channel hoặc thay thế listener |
| `Thread.interrupt()` trên thread đang block trong `DatagramChannel.receive` | `ClosedByInterruptException`, interrupt flag được đặt | **Có**, channel đóng | Kiến trúc dùng interruptible NIO blocking channel |
| `Selector.wakeup()` | `select()` hiện tại, hoặc lần select kế tiếp, được phép trở về ngay | **Không** | Event loop nhận thay đổi cấu hình/stop flag mà còn muốn chủ động đóng tài nguyên |
| `Selector.close()` | Làm selector ngừng hoạt động; các thao tác chọn hiện tại được đánh thức | **Có**, selector đóng; channel đã đăng ký không tự được đóng theo cùng ý nghĩa | Hủy selector và giải phóng đăng ký |
| `Future.cancel(true)` | **Cố gắng** interrupt nếu task đang chạy và implementation biết thread; không đảm bảo mọi receive kết thúc | **Không mặc định** | Thể hiện yêu cầu cancel ở tầng task, kết hợp cơ chế đóng I/O thích hợp |

**Lưu ý về thời điểm:** nếu thao tác `receive()` chưa bắt đầu khi một thread khác đóng socket/channel, lời gọi kế tiếp có thể gặp ngoại lệ loại **“đã đóng”** thay vì loại **“đóng bất đồng bộ trong khi đang chờ”**. Không nên viết logic yêu cầu **chính xác một subclass exception** ở mọi interleaving. Bài test có thể kiểm tra điều kiện cuối cùng: worker đã thoát và resource đóng.

## 4. `DatagramSocket.close()`: cơ chế rõ ràng để kết thúc receive

Với `DatagramSocket`:

```java
// Minh họa trong ứng dụng có socket được worker sở hữu.
socket.close();
```

Theo Javadoc hiện hành, khi `close()` được gọi, thread đang block trong `DatagramSocket.receive(DatagramPacket)` trên socket đó sẽ nhận **`SocketException`**. Sau close, socket không thể được “mở lại” bằng `bind()` hay gọi `receive()` như cũ: muốn tiếp tục nghe UDP phải **tạo socket mới**, gán port/bind theo chính sách của hệ điều hành và ứng dụng.

### 4.1. Đừng coi lỗi do shutdown là lỗi hệ thống

Một vòng nghe thường có `volatile boolean running` hoặc `AtomicBoolean running`. Khi shutdown:

1. Đặt trạng thái `running=false`.
2. Gọi `socket.close()` để đánh thức thao tác `receive` hiện tại.
3. Trong nhánh bắt `SocketException`, kiểm tra **shutdown đã được yêu cầu** (và/hoặc `socket.isClosed()`) để phân biệt **dừng chủ động** với lỗi I/O ngoài ý muốn.
4. Thoát vòng và chờ worker kết thúc bằng `join` hoặc `ExecutorService.awaitTermination`.

Ví dụ mẫu ở mức cấu trúc:

```java
// Minh họa, nằm trong lớp có các trường running và socket đã được tạo.
while (running.get()) {
    try {
        DatagramPacket packet = new DatagramPacket(new byte[2048], 2048);
        socket.receive(packet);
        if (!running.get()) {
            break; // Có thể đã nhận gói đúng lúc stop được yêu cầu.
        }
        processPacket(packet);
    } catch (SocketException ex) {
        if (!running.get() && socket.isClosed()) {
            break; // Nhánh shutdown chủ động, không cần báo lỗi ồn ào.
        }
        throw ex; // Lỗi không mong đợi cần được báo hoặc xử lý đúng chính sách.
    }
}
```

Đoạn này **không độc lập** vì `running`, `socket` và `processPacket` do ứng dụng định nghĩa. Một `try/finally` bên ngoài phải đóng socket khi worker sở hữu nó. Không xử lý mọi `SocketException` như “đang shutdown”: nếu socket vẫn mở, lỗi có thể đến từ cấu hình, network hoặc provider khác.

### 4.2. Ai có quyền đóng socket?

Nếu **một listener** chia sẻ socket giữa nhiều request, đóng socket vì một request đã timeout sẽ làm gián đoạn **tất cả** các tác vụ dùng socket. Cần đặt rõ **owner/lifecycle**:

- Socket thuộc listener/server → chỉ service shutdown hoặc quản lý listener được phép đóng.
- Một request tạo socket UDP riêng → request hủy có thể close socket của chính mình khi hợp đồng cho phép.
- Nhiều request dùng cùng một socket → hủy request ở **tầng định tuyến kết quả**, không đóng tài nguyên chia sẻ.
- Executor và socket thuộc các owner khác nhau → cần một cơ chế shutdown phối hợp; `shutdownNow()` của executor không đương nhiên close socket.

**Không có bảo đảm rằng có thể cancel riêng một `receive` trên socket dùng chung mà không tác động tới receive khác**. Nếu cần nhiều deadline/request trên cùng socket, kiến trúc event loop và bảng pending requests thường phù hợp hơn việc mở một thread block riêng cho từng request.

## 5. `SO_TIMEOUT`: hết thời gian chờ khác đóng tài nguyên

`DatagramSocket.setSoTimeout(int timeout)` đặt thời gian chờ tối đa cho **một lần** gọi `receive()`:

```java
// Đoạn minh họa trong method có socket:
socket.setSoTimeout(200); // milliseconds, phải set trước khi vào receive().
try {
    socket.receive(packet);
} catch (SocketTimeoutException ex) {
    // Không có gói trước hạn; socket vẫn hợp lệ.
}
```

Các điểm đáng nhớ:

- **`timeout > 0`**: nếu không có datagram trước khi hết hạn, `receive` ném `SocketTimeoutException`.
- **`timeout == 0`**: vô hạn theo `SO_TIMEOUT`; không phải “chờ 0 ms”.
- **`timeout < 0`**: `IllegalArgumentException`.
- Cần set **trước khi** bắt đầu blocking operation; không dựa vào việc một thread khác đổi timeout giữa lúc đang receive.
- Sau `SocketTimeoutException`, socket **vẫn được phép sử dụng**. Có thể lặp `receive()` nếu service còn chạy, hoặc đóng nó khi lifecycle kết thúc.
- Timeout là trên **lời gọi nhận**, không đảm bảo deadline tổng thể của **nhiều lần retry**. Nếu một request có deadline chung, ứng dụng cần tính ngân sách thời gian còn lại và stop điều kiện lặp.

Ví dụ vòng poll (mã minh họa):

```java
socket.setSoTimeout(250);
while (running.get()) {
    try {
        socket.receive(packet);
        if (running.get()) {
            processPacket(packet);
        }
    } catch (SocketTimeoutException ignored) {
        // Chỉ kiểm tra lại running/deadline.
    }
}
```

Vòng này có **độ trễ dừng tối đa theo timeout nhận** nếu không có tín hiệu khác, nhưng thời gian lập lịch không phải bảo đảm realtime tuyệt đối. Với shutdown yêu cầu nhanh và chắc chắn, **đặt running=false rồi close socket** thường đơn giản hơn chờ timer hết hạn.

**Đừng làm:** `catch (SocketTimeoutException e) { socket = new DatagramSocket(...); }` trong mọi lần timeout. Timeout bình thường không có nghĩa socket đã hỏng; tạo socket liên tục làm tiêu tốn tài nguyên và có thể thay đổi port.

## 6. `DatagramChannel` và interrupt: tính chất của `InterruptibleChannel`

`DatagramChannel` triển khai `InterruptibleChannel`. Theo Javadoc:

- Nếu **một thread khác gọi `channel.close()`** trong khi thread nhận đang chờ I/O, thread đang chờ nhận **`AsynchronousCloseException`**.
- Nếu **thread bị gọi `interrupt()`** trong lúc chờ I/O trên channel, channel bị **đóng**, thread đang chờ nhận **`ClosedByInterruptException`**, và interrupt status được đặt.
- Nếu **interrupt flag đã được đặt** trước khi một thread bắt đầu một blocking operation trên interruptible channel, nó có thể bị đóng và ném `ClosedByInterruptException` ngay.

Ví dụ nguyên tắc:

```java
// Đoạn minh họa, chưa đủ lớp/biến để chạy độc lập.
DatagramChannel channel = DatagramChannel.open();
channel.bind(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0));

Thread worker = new Thread(() -> {
    try {
        channel.receive(ByteBuffer.allocate(2048)); // Blocking theo mặc định.
    } catch (ClosedByInterruptException ex) {
        // Task đã bị interrupt; channel cũng đóng.
    } catch (AsynchronousCloseException ex) {
        // Thread khác đã close channel đang chờ I/O.
    } catch (IOException ex) {
        // Lỗi I/O khác.
    }
});
worker.start();
// Nếu yêu cầu stop thì worker.interrupt() hoặc channel.close() theo thiết kế.
```

Đoạn trên cần imports `java.net.*`, `java.nio.*`, `java.nio.channels.*`, `java.io.*` và quản lý thread/lifecycle; đây chỉ là **ví dụ API**, chương trình hoàn chỉnh ở phần 10.

### 6.1. Interrupt trên channel thường là một hành động đóng tài nguyên

Không nên hiểu `worker.interrupt()` ở đây là “tạm dừng receive nhưng vẫn dùng channel cho lần tới”. Với `DatagramChannel`, **interrupt dẫn đến đóng channel** theo hợp đồng `InterruptibleChannel`. Sau đó muốn nghe tiếp cần tạo channel mới.

Điều này quan trọng đối với retry logic: nếu `ClosedByInterruptException` xuất hiện, việc `continue` rồi `channel.receive` lại trên **cùng channel** thường dẫn tới `ClosedChannelException`, không phải khả năng phục hồi.

### 6.2. `ClosedChannelException` và race khi close

Lịch thực thi giữa các thread là bất định. Nếu channel **đã đóng trước khi receive bắt đầu**, lời gọi có thể ném `ClosedChannelException`. Nếu thread khác đóng **trong lúc receive đang block**, ngoại lệ phù hợp là `AsynchronousCloseException`, vốn là một subtype của `ClosedChannelException`.

Trong nhánh xử lý, nếu cần phân biệt, hãy catch **ngoại lệ chuyên biệt trước**:

```java
try {
    channel.receive(buffer);
} catch (ClosedByInterruptException ex) {
    // Thread hiện tại bị interrupt khi thao tác.
} catch (AsynchronousCloseException ex) {
    // Thread khác close giữa khi đang chờ.
} catch (ClosedChannelException ex) {
    // Channel đã đóng ở thời điểm gọi hoặc trường hợp còn lại.
}
```

Các biến `channel`, `buffer` là giả định của mã minh họa. **Không catch `ClosedChannelException` trước rồi mới catch `AsynchronousCloseException`** vì nhánh sau sẽ không tới được.

### 6.3. Đừng xóa interrupt flag vô tình

`Thread.currentThread().isInterrupted()` **chỉ đọc** cờ interrupt. `Thread.interrupted()` (static) **đọc và xóa** cờ của thread hiện tại. Trong code hệ thống, không dùng `Thread.interrupted()` chỉ để log trạng thái rồi vô tình mất tín hiệu hủy.

Nếu gặp `InterruptedException` từ `CountDownLatch.await()`, `Thread.sleep()`, `Future.get()` hoặc `Thread.join()`, nên dừng/propagate hoặc **khôi phục cờ bằng `Thread.currentThread().interrupt()`** nếu không thể propagate, rồi thực hiện cleanup. Với `ClosedByInterruptException` do channel, cờ interrupt đã được đặt theo hợp đồng; tránh mã xử lý vô tình clear nó.

## 7. `DatagramSocket.receive` có hỗ trợ interrupt trực tiếp không?

**Không có một quy tắc duy nhất cho mọi trường hợp.** Theo Javadoc Java hiện hành, `DatagramSocket.receive(DatagramPacket)` có hành vi interruptible trong những trường hợp xác định:

1. **Socket gắn với `DatagramChannel`:** interrupt thread đang receive sẽ đóng channel bên dưới và ném **`ClosedByInterruptException`**; cờ interrupt được đặt.
2. **Socket dùng system-default socket implementation, thread nhận là virtual thread (Java 21+):** interrupt virtual thread sẽ làm nó thức dậy, đóng socket và ném **`SocketException`**; cờ interrupt được đặt.

Ngược lại, với một **`DatagramSocket` thường** chạy trên **platform thread** mà không có channel đi kèm, **không được dựa vào `Thread.interrupt()` như cơ chế bảo đảm đánh thức `receive()`**. Muốn stop chắc chắn, gọi `socket.close()`, hoặc set `SO_TIMEOUT` để có các mốc kiểm tra cancellation.

Một điểm kỹ thuật quan trọng:

```java
DatagramSocket socket = new DatagramSocket(); // Socket thông thường.
boolean associatedChannel = socket.getChannel() != null;
```

Trường hợp trên thường cho `getChannel() == null`. Một socket chỉ có channel gắn với nó nếu socket được tạo thông qua `DatagramChannel.open()` rồi lấy `channel.socket()`. Hợp đồng interruptible của trường hợp này khác với socket thường.

**Virtual threads có từ Java 21**, không phải một phần tính năng của Java 15. Bài học dùng Java 17 làm baseline và chỉ nhắc virtual threads như một khác biệt **hiện hành** khi nâng cấp runtime. Không đưa `Thread.ofVirtual()` vào chương trình `--release 17`.

## 8. `Selector.wakeup()`: hủy chờ, không hủy tài nguyên

Nếu bạn dùng NIO `DatagramChannel` ở **non-blocking mode** và đăng ký với `Selector`, vòng nhận thường nằm ở `selector.select()`, không block trong `channel.receive()`.

```java
// Minh họa trong method với channel/selector đã tạo.
channel.configureBlocking(false);
channel.register(selector, SelectionKey.OP_READ);
int ready = selector.select(10_000); // Có thể trở về sớm khi wakeup.
```

Khi một thread khác đổi trạng thái:

```java
running.set(false);
selector.wakeup();
```

Theo Javadoc, `wakeup()` làm **lần select đang chờ**, hoặc **lần select kế tiếp nếu chưa có select đang chờ**, trở về ngay. **Nó không đóng selector hoặc channel.** Đây là lựa chọn khi muốn:

- Tắt event loop và để chính loop cleanup trong `finally`.
- Thay đổi danh sách channel được quan sát.
- Cập nhật danh sách request/deadline rồi yêu cầu loop tính lại.
- Hủy chờ mà vẫn giữ socket/channel mở để tái sử dụng theo chính sách owner.

Các điểm dễ nhầm:

- `Selector.wakeup()` **không sinh datagram** và không làm `DatagramChannel.receive()` đang block thoát nếu bạn không hề dùng selector.
- `selector.select(timeout)` có thể trả **`0`** khi bị wakeup mà không có key ready; cũng có thể trả số khác `0` nếu đồng thời có I/O ready. **Không dùng `return == 0` để khẳng định shutdown**. Hãy đọc cờ `running`.
- Một lần wakeup không phải phép “lưu vô hạn các tín hiệu” để ứng dụng đếm sự kiện. Nếu chưa select, lần select kế tiếp sẽ trở về ngay; sau đó select khác có thể lại block nếu không có wakeup mới.
- Thay đổi interestOps hoặc hủy key từ thread khác cần tính đến **đồng bộ và wakeup** để loop nhìn thấy thay đổi kịp thời.
- `Selector.close()` khác `wakeup()`: close hủy selector và registration, còn channel đã đăng ký cần được quản lý/đóng riêng theo owner.

### Event loop mẫu dùng timeout và wakeup (minh họa)

```java
while (running.get()) {
    selector.select(5_000); // Chờ readiness hoặc wakeup.
    if (!running.get()) {
        break;
    }
    for (SelectionKey key : selector.selectedKeys()) {
        if (key.isValid() && key.isReadable()) {
            DatagramChannel channel = (DatagramChannel) key.channel();
            ByteBuffer dst = ByteBuffer.allocate(2048);
            SocketAddress source = channel.receive(dst); // Non-blocking: có thể null.
            if (source != null) {
                dst.flip();
                processDatagram(source, dst);
            }
        }
    }
    selector.selectedKeys().clear();
}
```

Đây **không phải một class độc lập**; `running`, `selector`, `processDatagram` phải được định nghĩa. Hệ thống production cần xử lý `IOException`, concurrent changes và selected-key set theo một cách đồng bộ thích hợp, tránh giữ payload Buffer của request quá lâu. Lưu ý `DatagramChannel.receive()` ở **non-blocking mode** trả `null` nếu chưa có datagram ngay lập tức; đó không phải EOF.

## 9. `Future.cancel(true)`, `ExecutorService.shutdownNow()` và `CompletableFuture`

Đây là chỗ rất dễ hiểu sai khi tích hợp UDP I/O với tác vụ bất đồng bộ.

### 9.1. `Future.cancel(true)` là yêu cầu hủy, không phải lệnh đóng socket

`Future.cancel(true)` thử hủy task; nếu task đang chạy, implementation có thể **interrupt thread** để nó tự dừng. `Future.isCancelled() == true` nói về **trạng thái Future**, không phải bằng chứng rằng syscall UDP đang chờ đã kết thúc. `Future.get()` trên Future bị cancel ném `CancellationException`; đó cũng không chứng minh tài nguyên đã đóng.

Đặc biệt:

- Task dùng `DatagramChannel.receive`: interrupt thread đang block có thể đóng channel theo hợp đồng API.
- Task dùng `DatagramSocket.receive` trên platform thread/socket thường: interrupt **không đủ làm hợp đồng stop**.
- Task có thể bỏ qua interrupt hoặc giữ tài nguyên ở nơi khác.
- Task đã hoàn tất trước `cancel`: hủy có thể không có tác dụng.

Nếu một task **sở hữu** socket riêng, shutdown an toàn thường gồm **cờ dừng + close socket + cancel/request interruption khi phù hợp + chờ worker thật sự kết thúc**. Nếu nhiều task chia sẻ socket, không đóng nó vì cancel một task; phải hủy logic request/registration trong event loop.

### 9.2. `shutdownNow()` cũng không tự đóng mọi socket

`ExecutorService.shutdownNow()` cố gắng dừng các task đang chạy, thông thường qua `interrupt`, và trả về những task chưa bắt đầu. Nó **không bảo đảm** task đang block trong I/O tùy ý sẽ chấm dứt. Sau lệnh shutdown, phải phối hợp **đóng resource của owner** hoặc wakeup selector và kiểm tra `awaitTermination`.

Một quy trình shutdown ở cấp service:

```text
acceptingNewWork=false
running=false
→ ngừng đăng ký request mới
→ nếu owner: close UDP socket/channel; nếu selector event loop: wakeup()
→ yêu cầu executor shutdown
→ awaitTermination/join với thời hạn hợp lý
→ ghi nhận lỗi timeout, phát tín hiệu vận hành
→ cleanup tài nguyên và không dùng lại socket/channel đã đóng
```

Không chỉ gọi `shutdownNow()` rồi bỏ reference tới socket và tự cho rằng thread I/O đã biến mất.

### 9.3. `CompletableFuture.cancel(true)` còn khác

Trong Java hiện hành, `CompletableFuture.cancel(boolean)` **không sử dụng interrupt để điều khiển tác vụ**, tham số `mayInterruptIfRunning` không có tác dụng ngắt theo hợp đồng class này. Nếu bọc một UDP receive trong `CompletableFuture.supplyAsync(...)`, gọi `cancel(true)` có thể làm kết quả Future chuyển sang cancelled mà blocking I/O bên dưới vẫn đang chạy.

Vì vậy, một API trả `CompletableFuture` nên có **cơ chế cancellation do chính service quản lý**: loại request khỏi pending map, hủy scheduler, close socket riêng nếu owner hoặc wakeup event loop để áp dụng trạng thái, thay vì phụ thuộc vào cờ hủy của Future.

## 10. Chương trình Java 17+ hoàn chỉnh: bốn cơ chế, stdout ổn định

Ví dụ dưới đây kiểm tra bốn trường hợp trên **địa chỉ loopback** và các **cổng UDP tự chọn** (port 0). Không truy cập mạng bên ngoài, không cần server khác, không dùng API preview. Chạy với Java 17 trở lên; các hợp đồng API cốt lõi đã có ở Java 15 và vẫn được hỗ trợ.

Chương trình:

1. Đặt `SO_TIMEOUT`, nhận `SocketTimeoutException` mà socket vẫn mở.
2. Đặt thread vào `DatagramSocket.receive()`, gọi `close()` từ main, kiểm tra thread kết thúc.
3. Đặt thread vào `DatagramChannel.receive()` (blocking mặc định), gọi `interrupt()`, kiểm tra `ClosedByInterruptException`, channel đóng và cờ interrupt.
4. Đăng ký non-blocking `DatagramChannel` với `Selector`; gọi `wakeup()`, kiểm tra `select` trở về mà channel vẫn mở.

### 10.1. Mã nguồn: `UdpCancellationDemo.java`

```java
import java.io.IOException;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.SocketException;
import java.net.SocketTimeoutException;
import java.nio.ByteBuffer;
import java.nio.channels.ClosedByInterruptException;
import java.nio.channels.DatagramChannel;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

public class UdpCancellationDemo {
    private static InetSocketAddress local() {
        return new InetSocketAddress(InetAddress.getLoopbackAddress(), 0);
    }

    private static void timeoutKeepsSocket() throws Exception {
        try (DatagramSocket socket = new DatagramSocket(local())) {
            socket.setSoTimeout(120);
            String result;
            try {
                socket.receive(new DatagramPacket(new byte[32], 32));
                result = "unexpected-datagram";
            } catch (SocketTimeoutException expected) {
                result = "SocketTimeoutException";
            }
            System.out.println("timeoutResult=" + result);
            System.out.println("timeoutKeepsSocketOpen=" + !socket.isClosed());
        }
    }

    private static void closeUnblocksSocket() throws Exception {
        DatagramSocket socket = new DatagramSocket(local());
        CountDownLatch entering = new CountDownLatch(1);
        AtomicReference<String> result = new AtomicReference<>("not-finished");
        Thread receiver = new Thread(() -> {
            entering.countDown();
            try {
                socket.receive(new DatagramPacket(new byte[32], 32));
                result.set("unexpected-datagram");
            } catch (SocketException expected) {
                result.set(socket.isClosed() ? "SocketException" : "socket-error");
            } catch (IOException error) {
                result.set("other-io-error");
            }
        }, "socket-receiver");
        receiver.start();
        try {
            if (!entering.await(2, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Receiver did not start");
            }
        } finally {
            socket.close();
        }
        receiver.join(2_000);
        if (receiver.isAlive()) {
            receiver.interrupt();
            throw new IllegalStateException("Receiver did not terminate");
        }
        System.out.println("socketCloseResult=" + result.get());
        System.out.println("socketClosed=" + socket.isClosed());
    }

    private static void interruptClosesChannel() throws Exception {
        try (DatagramChannel channel = DatagramChannel.open()) {
            channel.bind(local());
            CountDownLatch entering = new CountDownLatch(1);
            AtomicReference<String> result = new AtomicReference<>("not-finished");
            AtomicBoolean interruptFlag = new AtomicBoolean();
            Thread receiver = new Thread(() -> {
                entering.countDown();
                try {
                    channel.receive(ByteBuffer.allocate(32));
                    result.set("unexpected-datagram");
                } catch (ClosedByInterruptException expected) {
                    result.set("ClosedByInterruptException");
                } catch (IOException error) {
                    result.set("other-io-error");
                } finally {
                    interruptFlag.set(Thread.currentThread().isInterrupted());
                }
            }, "channel-receiver");
            receiver.start();
            if (!entering.await(2, TimeUnit.SECONDS)) {
                channel.close();
                throw new IllegalStateException("Channel receiver did not start");
            }
            receiver.interrupt();
            receiver.join(2_000);
            if (receiver.isAlive()) {
                channel.close();
                throw new IllegalStateException("Channel receiver did not terminate");
            }
            System.out.println("channelInterruptResult=" + result.get());
            System.out.println("channelClosed=" + !channel.isOpen());
            System.out.println("channelInterruptFlag=" + interruptFlag.get());
        }
    }

    private static void wakeupDoesNotCloseChannel() throws Exception {
        try (DatagramChannel channel = DatagramChannel.open();
                Selector selector = Selector.open()) {
            channel.bind(local());
            channel.configureBlocking(false);
            channel.register(selector, SelectionKey.OP_READ);
            CountDownLatch entering = new CountDownLatch(1);
            AtomicReference<String> result = new AtomicReference<>("not-finished");
            Thread selectWorker = new Thread(() -> {
                entering.countDown();
                try {
                    selector.select(10_000);
                    result.set("returned");
                } catch (IOException error) {
                    result.set("io-error");
                }
            }, "selector-worker");
            selectWorker.start();
            if (!entering.await(2, TimeUnit.SECONDS)) {
                selector.wakeup();
                throw new IllegalStateException("Selector worker did not start");
            }
            selector.wakeup();
            selectWorker.join(2_000);
            if (selectWorker.isAlive()) {
                selector.wakeup();
                throw new IllegalStateException("Selector worker did not terminate");
            }
            System.out.println("selectorWakeupResult=" + result.get());
            System.out.println("selectorChannelOpen=" + channel.isOpen());
        }
    }

    public static void main(String[] args) throws Exception {
        timeoutKeepsSocket();
        closeUnblocksSocket();
        interruptClosesChannel();
        wakeupDoesNotCloseChannel();
    }
}
```

### 10.2. Biên dịch và chạy

Lưu tệp UTF-8 `UdpCancellationDemo.java` ở một thư mục riêng. Trên macOS/Linux hoặc PowerShell, từ thư mục chứa tệp:

```bash
javac --release 17 -encoding UTF-8 UdpCancellationDemo.java
java -cp . UdpCancellationDemo
```

**Stdout đúng khi chương trình chạy như dự kiến trong môi trường loopback không có datagram ngoài ý muốn:**

```text
timeoutResult=SocketTimeoutException
timeoutKeepsSocketOpen=true
socketCloseResult=SocketException
socketClosed=true
channelInterruptResult=ClosedByInterruptException
channelClosed=true
channelInterruptFlag=true
selectorWakeupResult=returned
selectorChannelOpen=true
```

### 10.3. Đọc kết quả theo hợp đồng

- `timeoutResult=SocketTimeoutException`: lần `receive` hết thời gian chờ. `timeoutKeepsSocketOpen=true` xác nhận **timeout không đóng socket**.
- `socketCloseResult=SocketException`: main gọi `DatagramSocket.close()`; reader đang hoặc sắp vào receive không thể tiếp tục chờ trên socket đã đóng. `socketClosed=true` xác nhận trạng thái cuối cùng.
- `channelInterruptResult=ClosedByInterruptException`: worker bị interrupt ở hoạt động NIO interruptible. `channelClosed=true` và `channelInterruptFlag=true` phản ánh **hợp đồng đóng channel và set interrupt flag**.
- `selectorWakeupResult=returned`: vòng `select` rời khỏi lời gọi dù timeout là `10_000` ms. `selectorChannelOpen=true`: `wakeup()` chỉ đánh thức, không đóng channel.

**Tính tái lập:** chương trình không gửi datagram; nó bind loopback port 0 do OS tự chọn, không phụ thuộc địa chỉ máy hay cổng cố định. `CountDownLatch` giúp điều phối thread nhưng đếm trước thao tác blocking, nên về lý thuyết scheduler có thể cho phép main close/interrupt/wakeup ngay **trước** lời gọi chờ. Các kết quả cuối vẫn phù hợp với hợp đồng:

- Socket đã đóng → receive không thể chờ và ném `SocketException`.
- Thread bị interrupt trước blocking channel receive → interruptible channel đóng, ném `ClosedByInterruptException`.
- `Selector.wakeup()` gọi trước select vẫn làm **lần select kế tiếp** trở về ngay.

Một datagram ngẫu nhiên gửi đúng ephemeral port của chương trình hoặc sự cố môi trường cực hiếm có thể làm nhánh timeout nhận gói; không coi stdout là một bảo đảm realtime hay một phép kiểm định mọi hệ điều hành. Chương trình đã được biên dịch và chạy trên JDK hiện hành với `--release 17` và đầu ra mẫu khớp từng dòng.

### 10.4. Vì sao ví dụ sử dụng `join` có thời hạn?

Nếu worker có lỗi logic và không thoát, một test không nên **kẹt mãi** ở `join()`. Các lời gọi `join(2_000)` chỉ là **giới hạn đợi ở chương trình test**; nó không có quyền buộc thread chết. Nếu sau hạn worker còn sống, ví dụ ném `IllegalStateException` để phát hiện thất bại thay vì in `PASS` giả.

Trong code production, cần một lộ trình cleanup/giám sát khi `awaitTermination` hoặc `join` quá hạn. Không dùng `Thread.stop()` để cưỡng chế hủy I/O; API này đã bị loại khỏi lựa chọn lập trình an toàn từ lâu. Không dùng busy waiting với `while(worker.isAlive()) { }` vì tốn CPU và không tăng bảo đảm dừng.

## 11. Thiết kế cancellation theo quyền sở hữu tài nguyên

Giả sử một hệ thống có hai loại tác vụ:

**Trường hợp A: một UDP listener thuộc service**

```text
Service.start()
  └── tạo DatagramSocket / DatagramChannel
        └── một receiver hoặc selector event loop
              └── xử lý nhiều request
Service.stop()
  ├── running=false
  ├── socket.close() / channel.close() / selector.wakeup()
  ├── join hoặc awaitTermination
  └── dọn registrations và tài nguyên của service
```

Ở đây service sở hữu socket, nên shutdown toàn service có quyền close. Một request riêng lẻ timeout **không** được đóng socket chung. Event loop dùng `Selector.wakeup()` khi cần xử lý trạng thái mới hoặc đóng resources một cách tập trung trong loop.

**Trường hợp B: mỗi request có socket riêng**

```text
RequestTask
  ├── tạo DatagramSocket riêng
  ├── gửi/nhận tới peer theo yêu cầu
  └── finally: close socket

Request cancelled
  ├── request.cancelled=true
  ├── close socket của chính request
  └── chờ worker kết thúc theo hợp đồng task
```

Trong trường hợp này, close không ảnh hưởng các request khác, nhưng tạo nhiều socket/port và thread có chi phí. Cần cân nhắc mức tải, port exhaustion, timeout, nguồn datagram không tin cậy và yêu cầu throughput.

### 11.1. Hủy request trên socket chung

Khi các request dùng chung một UDP listener, mô hình nên là:

1. Mỗi request có một ID/khóa đối sánh và **deadline**.
2. Listener nhận datagram từ socket chung, đối chiếu với request còn active.
3. Khi request bị cancel, xóa pending entry và hoàn thành kết quả ở trạng thái cancelled; **không đóng socket**.
4. Datagrams đến trễ cho request đã hủy được xử lý theo chính sách (bỏ qua, audit tối thiểu hoặc báo sự kiện), không vô tình hoàn thành request khác.
5. Khi **toàn service** shutdown, wakeup/close socket và chờ listener dừng.

Trên UDP, một datagram có thể **mất, trễ, đảo thứ tự hoặc lặp lại**. Cancellation ở client **không thể thu hồi datagram đã được gửi qua mạng** hoặc bắt peer ngừng xử lý. Nếu cần hủy công việc phía peer, giao thức ứng dụng cần **thông điệp cancel riêng, mã yêu cầu và xác thực**, và vẫn phải chấp nhận race giữa cancel và phản hồi.

## 12. Timeout và deadline khi nhiều lần receive

Một lỗi phổ biến là đặt `socket.setSoTimeout(1_000)` rồi retry 10 lần và gọi đó là “timeout 1 giây”. Đó chỉ là **timeout mỗi lượt nhận**, còn tổng thời gian có thể gần 10 giây hoặc lâu hơn nếu có xử lý giữa các lần.

Nếu request có **deadline tổng**:

- Đặt một thời điểm kết thúc bằng đồng hồ monotonic, ví dụ `System.nanoTime()` (không dùng wall-clock để đo độ trễ).
- Trước mỗi receive, tính **thời gian còn lại**.
- Nếu còn lại hết, dừng request và báo timeout.
- Nếu dùng `DatagramSocket`, chọn `SO_TIMEOUT` dương hợp lý cho mỗi lượt; không nhầm `0` là “không chờ”.
- Nếu dùng selector, `select(timeout)` có thể trở về sớm vì wakeup/I/O; cần tính lại deadline sau mỗi vòng.

Ví dụ công thức ở cấp độ ý tưởng:

```java
// Minh họa, không phải phương thức hoàn chỉnh.
long deadlineNanos = System.nanoTime() + TimeUnit.SECONDS.toNanos(3);
long remainingNanos = deadlineNanos - System.nanoTime();
if (remainingNanos <= 0) {
    // Deadline tổng đã hết.
}
```

**Không lấy `System.currentTimeMillis()` cho một đo lường yêu cầu monotonic** vì đồng hồ hệ thống có thể điều chỉnh. `System.nanoTime()` dành cho đo chênh lệch thời gian trong cùng JVM, không phải timestamp trao đổi giữa máy.

Nếu timeout tính theo millisecond trong `setSoTimeout` nhưng `remainingNanos` còn ít hơn 1 ms, đừng làm tròn xuống `0` rồi vô tình thành **infinite timeout**; phải xử lý nhánh hết hạn hoặc làm tròn lên dương theo chính sách.

## 13. Xử lý ngoại lệ và giám sát không gây nhiễu

Khi shutdown đúng, một số ngoại lệ là **tín hiệu điều khiển được mong đợi**, không nhất thiết là lỗi nghiêm trọng.

| Tình huống | Ngoại lệ/kết quả thường gặp | Cách xử lý |
|---|---|---|
| `SO_TIMEOUT` hết hạn | `SocketTimeoutException` | Kiểm tra running/deadline; socket còn hợp lệ |
| `DatagramSocket.close()` khi receive chờ | `SocketException` | Nếu stop đã được yêu cầu và socket đóng → exit bình thường |
| `DatagramChannel` bị interrupt | `ClosedByInterruptException` | Dừng, giữ tín hiệu interrupt, không retry trên channel đóng |
| `DatagramChannel` bị close từ thread khác khi đang chờ | `AsynchronousCloseException` | Kiểm tra lifecycle; nếu shutdown → kết thúc bình thường |
| I/O trên channel đã đóng | `ClosedChannelException` | Phân biệt race shutdown với bug tái sử dụng resource |
| `Selector.wakeup()` | `select` trở về, có thể không có key ready | Kiểm tra running và queue thay đổi, không coi `0` là lỗi |
| Channel non-blocking không có datagram | `DatagramChannel.receive` trả `null` | Chờ readiness/đổi vòng, không diễn giải là peer EOF |
| `Future.get()` khi Future đã cancel | `CancellationException` | Chỉ biết kết quả Future bị hủy; kiểm tra resource/task termination riêng |
| UDP không nhận được phản hồi | Timeout ở cấp ứng dụng nếu có deadline | Không kết luận peer đã chết chỉ từ một timeout hoặc một packet loss |

Không log stack trace ồn ào ở mức ERROR cho mỗi `SocketException` do **shutdown chủ động**. Ngược lại, đừng bắt mọi `IOException` rồi coi là “đã cancel”: lỗi địa chỉ, quyền, cổng hoặc network vẫn cần được chẩn đoán và giám sát.

Nếu shutdown quá hạn, cung cấp sự kiện vận hành rõ ràng: thread chưa thoát, socket/channel state, timeout cấu hình, số pending requests; tránh đổ nguyên payload UDP nhạy cảm vào log chỉ để debug.

## 14. Những sai lầm thường gặp

| Sai lầm | Vì sao không chính xác | Cách sửa |
|---|---|---|
| `future.cancel(true)` chắc chắn dừng UDP receive trên mọi socket | Future không bảo đảm syscall stop; interrupt tùy loại I/O | Dùng close/timeout/channel interruption theo API và ownership |
| Đổi `running=false` rồi chờ worker tự thức | Flag không đánh thức blocking receive | Close socket hoặc wakeup selector, hoặc dùng `SO_TIMEOUT` |
| Catch `SocketTimeoutException` rồi đóng socket ngay | Timeout không làm socket hỏng | Quyết định theo lifecycle/deadline, không theo timeout một lần |
| Dùng `setSoTimeout(0)` để poll ngay | 0 nghĩa là vô hạn | Dùng giá trị dương hoặc non-blocking channel |
| Interrupt blocking `DatagramChannel` rồi retry cùng channel | Interrupt đóng channel | Tạo channel mới nếu cần tiếp tục |
| Dùng `Selector.wakeup()` để hủy blocking `DatagramSocket.receive` | Selector và socket receive là hai vị trí block khác nhau | Wakeup cho select; close socket cho receive |
| Đóng socket chung khi một request cancel | Ảnh hưởng mọi request đang dùng socket | Cancel pending request, giữ listener |
| Dùng `while (true)` bắt `SocketException` rồi retry vô hạn | Socket đã đóng; vòng lặp tạo log flood/spin | Khi stop thì break; lỗi thật thì báo/khôi phục đúng cách |
| Cho rằng UDP có EOF khi peer đóng | UDP không phải stream | Dùng timeout và ứng dụng-level protocol |
| `DatagramSocket` platform thread luôn interruptible | Chỉ một số trường hợp Javadoc cam kết | Dùng close, hoặc triển khai NIO channel/virtual-thread-aware |
| Quên `join`/`awaitTermination` | Task có thể còn chạy sau khi Future cancelled | Chờ/kiểm tra điều kiện termination thực |
| `Selector.select(0)` là non-blocking | 0 nghĩa là chờ vô hạn đối với `select(long)` | Dùng `selectNow()` nếu muốn không block |
| Lấy `return == 0` của selector để kết luận stop | Wakeup/timeout có thể trả 0; readiness có thể có | Kiểm tra cờ lifecycle và pending changes |
| Cố “khôi phục” socket đã close bằng `bind()` | Một socket/channel đóng không mở lại được | Tạo đối tượng mới, quản lý port và backoff |
| Lưu packet dùng lại mà không reset length | DatagramPacket có thể giữ length lần nhận trước | Reset length hoặc tạo packet phù hợp trước mỗi lượt |

## 15. Kiểm thử cancellation đúng hợp đồng

Đừng viết một test chỉ kiểm tra `future.isCancelled()`; nó không chứng minh lời gọi đang chờ đã thoát. Tối thiểu cần:

1. **Timeout:** tạo socket trên loopback port tự chọn, set `SO_TIMEOUT>0`, không gửi gói, bắt `SocketTimeoutException`, xác nhận `!socket.isClosed()`.
2. **Close UDP socket:** thread chờ receive; từ thread khác close; kiểm tra worker đã kết thúc và socket `isClosed()`.
3. **Interrupt NIO channel:** thread đang/chuẩn bị receive; interrupt; kiểm tra `ClosedByInterruptException` trong đường test phù hợp và `!channel.isOpen()`.
4. **Close NIO channel:** thread khác đóng khi đang thực sự block, kiểm tra `AsynchronousCloseException` hoặc nhánh đã đóng nếu race xảy ra trước khi block. Trong test đồng thời, không hard-code exception subtype khi lịch thực thi chưa được đồng bộ chắc chắn.
5. **Selector wakeup:** `select` trở về khi `wakeup`; `channel.isOpen()` vẫn `true` trước cleanup.
6. **Owner và cancellation:** cancel một request không làm listener chung đóng; stop listener toàn cục giải phóng tất cả tài nguyên nó sở hữu.
7. **Deadline tổng:** nhiều receive/retry không kéo dài quá policy do tính lại thời gian còn lại.
8. **Kiểm tra tài nguyên:** thread thực sự kết thúc, socket không leak, pending map/selection key được dọn và không tạo spin/log flood.
9. **Lỗi/ngoại lệ:** shutdown chủ động không phát cảnh báo giả; lỗi bất thường không bị nuốt.
10. **Khả năng chạy thực tế:** test cả JDK/runtime/OS của dịch vụ; với virtual thread Java 21+ cần test hợp đồng interrupt tương ứng của `DatagramSocket`.

Đặt giới hạn `join`/latch/awaitTermination trong test để phát hiện hang. Dùng **loopback và ephemeral port**, tránh địa chỉ hoặc port cố định có thể bận. Không dùng `Thread.sleep(100)` như một bằng chứng rằng receiver đã bước vào syscall; hãy dùng điều phối có kiểm tra, và chấp nhận sự khác biệt hợp lệ do race/OS nếu không thể quan sát chính xác thời điểm vào blocking method.

## 16. Kết luận

**Đóng hoặc hủy một tác vụ UDP phải tuân hợp đồng của đối tượng đang bị chặn:**

- **`DatagramSocket.receive`:** `socket.close()` là cơ chế dừng rõ ràng, `SO_TIMEOUT` là cơ chế giới hạn chờ mà vẫn giữ socket. Không coi interrupt platform thread/socket thường là bảo đảm.
- **`DatagramChannel.receive`:** close từ thread khác và interrupt đều có hợp đồng rõ về việc đánh thức, nhưng **interrupt còn đóng channel**.
- **`Selector.select`:** `wakeup()` đánh thức chờ mà giữ tài nguyên mở; event loop tự quyết định có đóng channel/selector hay không.
- **`Future.cancel`, `CompletableFuture.cancel`, `ExecutorService.shutdownNow`:** quản lý trạng thái task và/hoặc yêu cầu interrupt; không thay thế quản lý vòng đời UDP socket/channel.

Thiết kế bền vững nhất là làm rõ **ai sở hữu tài nguyên**, **request cancel hay service shutdown**, **deadline bao lâu**, **mã nào chịu trách nhiệm close/wakeup**, rồi xác nhận **thread/task thật sự dừng** bằng `join`, `awaitTermination` và kiểm tra trạng thái, thay vì chỉ nhìn một cờ Future.

### Tài liệu chính thức đang áp dụng

- [Oracle Java SE 26 — `DatagramSocket`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/DatagramSocket.html): `receive`, `setSoTimeout`, `close`, các điều kiện interruptible.
- [Oracle Java SE 26 — `DatagramChannel`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/DatagramChannel.html): `receive`, non-blocking và close/interrupt exceptions.
- [Oracle Java SE 26 — `InterruptibleChannel`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/InterruptibleChannel.html): `AsynchronousCloseException`, `ClosedByInterruptException`, interrupt flag.
- [Oracle Java SE 26 — `Selector`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/Selector.html): `select`, `selectNow`, `wakeup`, concurrency.
- [Oracle Java SE 26 — `Future`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/Future.html), [`CompletableFuture`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CompletableFuture.html), [`ExecutorService`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ExecutorService.html): hợp đồng hủy và dừng task.
