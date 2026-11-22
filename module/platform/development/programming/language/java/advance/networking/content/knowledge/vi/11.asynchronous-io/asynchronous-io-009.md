# Đóng channel, xử lý callback thất bại và kết thúc nhóm có thứ tự trong Java Asynchronous I/O

## Mục tiêu

Trong Java NIO.2, một thao tác I/O có thể đã **được khởi tạo nhưng chưa hoàn thành** khi ứng dụng bắt đầu dừng dịch vụ. Nếu đóng `AsynchronousSocketChannel` quá sớm, thao tác `read`/`write` còn chờ có thể đi vào `CompletionHandler.failed(...)`. Nếu gọi `AsynchronousChannelGroup.shutdown()` rồi tưởng tất cả socket đã tự đóng, ứng dụng có thể chờ mãi ở `awaitTermination(...)`. Nếu callback thất bại lại tự khởi động `accept` hoặc `read` mới trong khi server đang dừng, chương trình dễ sinh lỗi lặp, rò rỉ tài nguyên hoặc không kết thúc được.

Bài này giải thích đầy đủ ba vấn đề gắn liền nhau:

1. **Đóng từng channel**: phân biệt ngừng nhận kết nối mới, cho tác vụ hiện tại hoàn tất, half-close một chiều, `close()` cưỡng bức thao tác còn chờ và callback phản ánh thất bại.
2. **Xử lý callback thất bại**: phân loại lỗi dự kiến do shutdown và lỗi thực tế cần báo; không bỏ quên cleanup, không để callback tự tái đăng ký công việc khi đã dừng, không dùng lại `ByteBuffer` khi operation chưa kết thúc.
3. **Kết thúc một `AsynchronousChannelGroup` đúng thứ tự**: ngừng admission → drain in-flight work trong deadline → đóng các channel → `shutdown()` → `awaitTermination()` → chỉ khi cần mới `shutdownNow()`; ghi nhận cả đường thành công lẫn đường thất bại.

Ví dụ sử dụng **Java 17+**, TCP loopback và các API `java.nio.channels`. Ba chương trình độc lập minh họa đúng hành vi: callback bị thất bại do đóng channel; group shutdown không tự đóng channel; và dừng listener trước, hoàn tất trao đổi rồi mới dừng group.

## 1. Bức tranh tổng quan: channel, operation, callback và group

Các lớp chủ đạo:

- `AsynchronousServerSocketChannel`: listener TCP bất đồng bộ; `accept()` hoàn tất khi có một kết nối hoặc thất bại.
- `AsynchronousSocketChannel`: socket TCP bất đồng bộ; `connect`, `read`, `write` có thể hoàn tất ở thời điểm khác với lúc gọi.
- `CompletionHandler<V,A>`: nhận một trong hai kết quả **`completed(V result, A attachment)`** hoặc **`failed(Throwable exc, A attachment)`** cho một thao tác.
- `Future<V>`: cách khác để theo dõi kết quả, đợi bằng `get()`, xử lý `ExecutionException`, `CancellationException`, `TimeoutException` hoặc yêu cầu `cancel(...)`.
- `AsynchronousChannelGroup`: nhóm quản lý tài nguyên và cơ chế dispatch completion cho các asynchronous channel liên kết với nó; nhóm có thread pool phục vụ completion handlers và một số công việc liên quan đến I/O.

```text
Lifecycle của một dịch vụ TCP NIO.2

                     AsynchronousChannelGroup
                      ┌──────────────────────┐
                      │ completion dispatch  │
                      │ group threads        │
                      └─────────────▲────────┘
                                    │ completed(...) / failed(...)
                                    │
  Listener: AsynchronousServerSocketChannel
       accept() ───────► pending operation
                             │
          accepted client ───┘
                  │
                  ▼
  Connection: AsynchronousSocketChannel
      read(ByteBuffer, attachment, handler)
                   │
             pending / completed / failed
                   │
             business handler
                   │
      write(ByteBuffer, attachment, handler)
                   │
             pending / completed / failed

  Khi dừng:
  STOP_ACCEPTING → DRAIN_IN_FLIGHT → CLOSE_CHANNELS
                 → GROUP_SHUTDOWN → AWAIT_TERMINATION
                 → FORCED_CLOSE nếu quá deadline
```

**Một channel có thể có nhiều operation trong vòng đời nhưng không có nghĩa mọi operation được phép song song.** `AsynchronousSocketChannel` cho phép tối đa **một read outstanding** và **một write outstanding** đồng thời trên cùng channel. Gọi thêm read khi read trước chưa hoàn tất có thể ném `ReadPendingException`; tương tự `WritePendingException`. `AsynchronousServerSocketChannel` chỉ cho phép một `accept` outstanding tại một thời điểm; gọi thêm sẽ gây `AcceptPendingException`.

Các channel được phép dùng từ nhiều thread, **nhưng ByteBuffer bản thân không thread-safe**. Không được sửa `position`/`limit`, giải phóng hoặc tái sử dụng buffer của thao tác đang pending chỉ vì phương thức `read/write` đã trả về. Với callback, phần xử lý buffer thông thường bắt đầu **khi operation đã hoàn tất**.

### Khác biệt với Selector

`Selector` trong NIO kiểu readiness yêu cầu event loop xem `OP_READ/OP_WRITE` rồi tự gọi I/O không chặn. Trong NIO.2, bạn **khởi tạo một operation bất đồng bộ** và nhận callback/Future khi operation hoàn tất hoặc thất bại. `AsynchronousChannelGroup` không phải một `Selector` được public cho ứng dụng tùy ý lấy `selectedKeys()`; việc đóng nhóm cũng không đơn giản là đóng một Selector.

## 2. Hai cách nhận kết quả: Future và CompletionHandler

### 2.1. Future: đơn giản cho thí nghiệm có giới hạn

```java
// Đoạn minh họa, biến channel và buffer phải được tạo từ bên ngoài.
Future<Integer> pending = channel.read(buffer);
int count = pending.get(3, java.util.concurrent.TimeUnit.SECONDS);
```

Đây là **đoạn minh họa**, chưa phải chương trình độc lập. `get(timeout)` đợi tối đa một khoảng thời gian cho kết quả. Nếu quá hạn, `TimeoutException` chỉ báo **thread đợi** chưa có kết quả; nó **không tự hủy** thao tác I/O và không chứng minh peer đã ngắt kết nối.

Nếu operation hoàn tất thất bại, `Future.get()` ném `ExecutionException`, và nguyên nhân I/O nằm ở `getCause()`. Nếu chính Future đã được cancel, `get()` ném `CancellationException`. Nếu thread đợi bị ngắt, `get()` có thể ném `InterruptedException`; đây là tình trạng chờ của thread, không được mặc định xem là I/O đã hủy.

**Lưu ý:** gọi `get()` ngay trên mỗi operation khiến thread gọi phải đợi, nên giảm lợi ích của mô hình callback trong server lớn. Tuy vậy Future phù hợp để viết **thí nghiệm deterministic** và giải thích vòng đời, như ví dụ ở cuối bài.

### 2.2. CompletionHandler: kết thúc operation được thông báo

```java
// Đoạn minh họa: channel và buffer đã sẵn sàng, callback quản lý cleanup.
channel.read(buffer, requestId, new CompletionHandler<Integer, String>() {
    @Override
    public void completed(Integer bytesRead, String id) {
        // bytesRead > 0: tiêu thụ bytes mới đọc.
        // bytesRead == -1: EOF; xử lý kết thúc chiều đọc.
    }

    @Override
    public void failed(Throwable error, String id) {
        // Ghi lỗi theo id, hoàn tất trạng thái thất bại, cleanup.
    }
});
```

Đây là đoạn minh họa; cần import `java.nio.channels.CompletionHandler` và đầy đủ bối cảnh biến. `A` là kiểu attachment, giúp gắn `requestId`, `connectionState` hoặc đối tượng trạng thái vào operation. `V` là kiểu kết quả: `Integer` cho read/write, `Void` cho connect, `AsynchronousSocketChannel` cho accept.

Phương thức callback nên **hoàn thành nhanh**. Theo Javadoc, completion handler được chạy trên thread thuộc group; trong một số điều kiện operation hoàn tất ngay và thread gọi đã là group thread, handler **có thể được gọi trực tiếp trên thread đó**. Đừng giả định mỗi callback tạo một thread mới hoặc callback có thể block vô hạn mà không ảnh hưởng những operation khác.

### 2.3. Kết quả hoàn tất không phải kết quả nghiệp vụ

- `write.completed(n)` chứng minh một phần `n` byte đã được operation chấp nhận để ghi; **không** chứng minh peer đã đọc message hoặc transaction đã commit.
- `read.completed(-1)` là **EOF bình thường của chiều đọc** sau dữ liệu còn lại, không phải cùng loại với `failed(IOException)`.
- `read.completed(0)` có thể xuất hiện ở một số điều kiện; đừng coi là message rỗng hoặc tiến độ chắc chắn.
- `connect.completed(null)` xác nhận TCP connect operation hoàn tất, **không** bảo đảm server xử lý request.
- `accept.completed(channel)` chỉ xác nhận một connection đã được nhận, không bảo đảm phiên giao tiếp tiếp theo hoàn tất.

Một ứng dụng muốn xác nhận nghiệp vụ phải định nghĩa request/response/ack ở đúng tầng protocol, không coi callback I/O là business acknowledgment.

## 3. Đóng từng channel: điều gì xảy ra với operation còn pending?

`AsynchronousChannel` kế thừa `Channel` và `AutoCloseable`. Với `AsynchronousSocketChannel` và `AsynchronousServerSocketChannel`:

- `close()` đóng **channel cục bộ**. Nếu có operation bất đồng bộ còn outstanding, theo hợp đồng `AsynchronousChannel`, operation đó **hoàn tất thất bại với `AsynchronousCloseException`**.
- Sau khi channel đã đóng, việc cố khởi tạo I/O mới sẽ gặp kết quả lỗi với nguyên nhân `ClosedChannelException`, theo phương thức và cách trả lỗi của API cụ thể.
- `close()` không cam kết rằng mọi **callback đã chạy xong** ngay khi nó trở về; cần tracking/latch/Future hoặc `awaitTermination` ở cấp group để đợi các callback đã khởi tạo.
- `isOpen() == false` chỉ phản ánh channel đã đóng; nó **không** chứng minh application cleanup, metrics, response hay callback đã hoàn tất.
- Try-with-resources giúp đóng channel khi ra khỏi scope, nhưng không tự biến tất cả operation còn pending thành “xử lý thành công”.

### 3.1. Ba trường hợp cạnh tranh rất quan trọng

```text
Trường hợp A — operation đang pending:
  read() ----------- pending ------------ [close()]
                           \______________ failed(AsynchronousCloseException)

Trường hợp B — operation hoàn tất trước close:
  read() ---- completed(bytes) ---- [close()]
  => không được gán lại operation đã hoàn tất thành lỗi do close

Trường hợp C — khởi tạo sau close:
  [close()] ---- read()
  => không có I/O mới hợp lệ; có thể bị báo ClosedChannelException
```

Khi `close()` đua với việc operation vừa hoàn tất, bạn phải xử lý **kết quả thực sự được quan sát**, không đoán mọi callback đến sau khi bắt đầu shutdown đều là thất bại. Một response có thể đã được gửi phần nào trước khi lỗi xảy ra; vì vậy không thể tự động replay side effect nếu protocol không có idempotency.

### 3.2. Half-close không phải close toàn bộ channel

Trên `AsynchronousSocketChannel` đã kết nối:

- `shutdownOutput()` kết thúc **chiều ghi**: sau đó ghi tiếp bị từ chối; chiều đọc vẫn có thể dùng để nhận response.
- `shutdownInput()` kết thúc **chiều đọc cục bộ**; đọc sau đó thường cho EOF theo API, nhưng tác động lên read đang outstanding là **phụ thuộc hệ thống**.
- `close()` đóng channel, tác động lên cả các operation pending.
- Khi có write còn pending, Javadoc nêu tác động của `shutdownOutput()` lên outstanding write **không được xác định**. Muốn graceful completion, hãy đợi write hoàn tất rồi mới half-close hoặc close theo hợp đồng ứng dụng.

Ví dụ thiết kế request–response dựa EOF: gửi đủ request, chờ write completions, `shutdownOutput()`, tiếp tục read response. Không được dùng `close()` sau write đầu tiên nếu còn cần đọc hồi đáp.

### 3.3. Lỗi do tự đóng là bình thường, nhưng không được im lặng mọi lỗi

Nếu vận hành cố ý đóng listener khi dừng dịch vụ, một pending `accept` có thể đi vào callback `failed(...)` do `AsynchronousCloseException`. Đó có thể là **kết thúc dự kiến** trong trạng thái STOPPING, không cần gửi cảnh báo như một sự cố hạ tầng.

Nhưng `AsynchronousCloseException` ở lúc **đang RUNNING** có thể gợi ý một thread khác đóng nhầm socket, một timeout/cancellation hoặc bug lifecycle. Vì vậy nên log kèm **trạng thái shutdown, connection ID, operation, request ID và nguyên nhân**, không chỉ lọc theo class exception.

## 4. `failed(Throwable,A)` phải hoàn thành quy trình thất bại

Đừng viết callback rỗng:

```java
// SAI: mất nguyên nhân và để task còn treo trong hệ thống.
@Override
public void failed(Throwable exc, ConnectionState state) {
}
```

Đây là ví dụ **anti-pattern**, không phải code chạy độc lập. Khi một operation thất bại, còn ít nhất bốn việc cần xem xét: **đánh dấu trạng thái**, **thông báo người chờ**, **giải phóng tài nguyên**, **phân loại log/metric**.

### 4.1. Phân loại lỗi theo ngữ cảnh

| Dạng quan sát | Ý nghĩa thường gặp | Hành vi phù hợp |
|---|---|---|
| `AsynchronousCloseException` khi có cờ STOPPING | Operation đang chờ bị đóng cùng channel | Có thể coi là shutdown dự kiến, nhưng vẫn hoàn tất task và cleanup |
| `AsynchronousCloseException` khi RUNNING | Channel bị đóng trong lúc operation chờ | Điều tra lifecycle/race; không giả định bình thường |
| `ClosedChannelException` | Dùng channel đã đóng hoặc completion báo đóng | Không tái sử dụng channel, kiểm tra state và ai đóng |
| `InterruptedByTimeoutException` | Timeout ở overload `read/write` có timeout của async API | Đóng hoặc bỏ channel khỏi pool theo chính sách; buffer/I/O state có thể không xác định |
| `ReadPendingException` / `WritePendingException` | Khởi tạo hai read hoặc hai write cùng lúc trên một socket | Bug quản lý in-flight operation; serialize theo chiều |
| `AcceptPendingException` | Hai accept outstanding trên cùng listener | Chỉ re-arm accept khi accept trước đã kết thúc |
| `ShutdownChannelGroupException` | Cố tạo channel trong group đã shutdown hoặc không thể dispatch callback vì group đã terminated | Không nhận thêm việc; kiểm tra thứ tự shutdown và ownership |
| `IOException` khác, ví dụ remote reset | Lỗi I/O thực tế, peer có thể đã ngắt | Hoàn tất request thất bại; xử lý retry theo protocol |
| Exception do **code trong callback** tự ném | Lỗi xử lý ứng dụng trong callback | Bắt và log ở biên callback, complete task và cleanup |

**`failed` nhận `Throwable` chứ không chỉ `IOException`.** Đừng tùy tiện nuốt mọi `Throwable`; đồng thời cần đảm bảo cleanup thực hiện được trong nhánh lỗi. Với lỗi nghiêm trọng kiểu `Error`, cần chính sách vận hành và phát hiện, không giả định hệ thống an toàn để tiếp tục phục vụ.

### 4.2. Mô hình state cho một connection

```text
NEW → CONNECTING → ACTIVE → DRAINING → CLOSED
           │         │        │
           └─────────┴────────┴────► FAILED → CLOSED

Mỗi request:
PENDING → COMPLETED
       └→ FAILED / CANCELLED / TIMED_OUT

Một operation kết thúc theo một đường terminal, nhưng
connection có thể sở hữu nhiều operations / callbacks khác nhau.
```

Khi implement bằng nhiều thread, dùng synchronization, lock hoặc `AtomicBoolean.compareAndSet` để đảm bảo thao tác như “thông báo client, bỏ khỏi registry, trừ active count” chỉ xảy ra **một lần về mặt logic**. Điều đó không thay thế việc nhận kết quả từng operation; nó tránh đường timeout và callback cùng kết thúc một request hai lần.

### 4.3. Mẫu callback cleanup an toàn về ý tưởng

```java
// Pseudocode Java: ConnectionContext, finishFailure và closeQuietly
// là các thành phần ứng dụng cần định nghĩa; KHÔNG phải chương trình độc lập.
@Override
public void failed(Throwable exc, ConnectionContext ctx) {
    try {
        if (!ctx.stopping.get()) {
            ctx.logger.error("I/O failed id=" + ctx.id, exc);
        } else {
            ctx.logger.debug("I/O stopped id=" + ctx.id, exc);
        }
        ctx.finishFailure(exc); // idempotent: thông báo pending request 1 lần.
    } finally {
        ctx.closeQuietly();
    }
}
```

Tách phần **ghi nhận/hoàn tất tác vụ** khỏi **đóng channel**, vì `close` có thể kích hoạt các callback thất bại khác. Callback không nên giữ lock rồi chờ một callback khác trên cùng thread pool; đó là một đường deadlock quen thuộc.

### 4.4. Đừng tái arm khi đang shutdown

Một accept loop bất đồng bộ có thể có mẫu:

```java
// Pseudocode: rearmAccept() và onAccepted() là hàm ứng dụng.
public void completed(AsynchronousSocketChannel peer, State state) {
    if (state.stopping.get()) {
        closeQuietly(peer);
        return;
    }
    rearmAccept(); // Chỉ khi listener còn mở và app vẫn nhận việc mới.
    onAccepted(peer);
}

public void failed(Throwable error, State state) {
    if (state.stopping.get()) {
        state.acceptStopped.countDown();
        return;
    }
    logUnexpectedAcceptFailure(error);
    // Chỉ retry/re-arm theo chính sách có backoff, tránh vòng lặp vô hạn.
}
```

Đoạn này **không độc lập**. Ý chính: khi server đã yêu cầu stop, không gọi `listener.accept(...)` mãi từ callback `failed`. Nếu đã accept thành công đúng lúc shutdown nhưng app không nhận việc mới, phải **đóng ngay accepted channel** để tránh leak; không được coi `completed` luôn đồng nghĩa “phục vụ tiếp”.

## 5. Sự thật về timeout và cancellation

Hai dạng timeout thường bị trộn:

**Timeout của người chờ Future:** `future.get(2, SECONDS)` ném `TimeoutException` khi caller chờ quá thời hạn. Operation bất đồng bộ có thể vẫn chạy. Nếu app muốn chấm dứt, cần chính sách riêng cho cancel/close và chờ cleanup; không tự dùng lại buffer.

**Timeout của chính I/O:** overload `AsynchronousSocketChannel.read/write(..., long timeout, TimeUnit unit, ..., handler)` có thể hoàn tất thất bại bằng `InterruptedByTimeoutException`. Tài liệu JDK cảnh báo sau timeout, nếu hệ thống không bảo đảm byte chưa được nhận/ghi, channel hoặc chiều I/O có thể vào **trạng thái lỗi tùy implementation**, và trạng thái `ByteBuffer` liên quan **không xác định**. Với thao tác có side effect quan trọng, đóng connection và dùng protocol idempotency/response để xác định trạng thái thay vì tiếp tục ghi như chưa có gì xảy ra.

**`Future.cancel(boolean)`:** yêu cầu hủy Future. Có thể khiến `Future.get()` ném `CancellationException`, nhưng việc ngừng I/O bên dưới phụ thuộc implementation; `cancel(true)` có thể dẫn đến đóng channel. Javadoc còn khuyến cáo cẩn trọng với buffer của operation bị cancel khi channel vẫn mở.

Không được tuyên bố:

- “`Future.get(timeout)` quá hạn thì read đã tự hủy”.
- “`cancel(false)` bảo đảm không byte nào từng được đọc/ghi”.
- “`cancel(true)` chỉ interrupt callback thread và giữ socket chắc chắn an toàn”.
- “`ByteBuffer.position` vẫn đáng tin sau mọi timeout/cancellation”.

Khi khách hàng gửi một thao tác không idempotent, timeout ở tầng Java chỉ cho biết **chưa nhận được kết quả tin cậy**, không chắc server chưa xử lý. Retry cần request ID và cơ chế dedup/idempotency phù hợp, không dựa vào cách đóng channel.

## 6. `AsynchronousChannelGroup`: shutdown khác close channel

Một `AsynchronousChannelGroup` gom các channel và thread pool dispatch callbacks. Nhóm được tạo tường minh, chẳng hạn:

```java
// Ví dụ minh họa: nơi quản lý lifecycle của dịch vụ.
AsynchronousChannelGroup group =
        AsynchronousChannelGroup.withFixedThreadPool(4, Thread::new);
AsynchronousServerSocketChannel listener =
        AsynchronousServerSocketChannel.open(group);
AsynchronousSocketChannel client =
        AsynchronousSocketChannel.open(group);
```

Đây là đoạn mã minh họa cần `import java.nio.channels.*` và cleanup đầy đủ. Group có thể được tạo qua `withFixedThreadPool`, `withCachedThreadPool` hoặc `withThreadPool`. Các channel `open(group)` gắn với group được chỉ định; channel mở không truyền group thường dùng group mặc định của JVM.

### 6.1. Bảng so sánh quan trọng

| API | Có tác dụng gì? | Không bảo đảm điều gì? |
|---|---|---|
| `group.shutdown()` | Đánh dấu group đang shutdown; từ chối tạo channel mới gắn vào group; khởi đầu orderly shutdown | **Không tự đóng tất cả channel đang mở**, không tự ép operation còn pending hoàn tất |
| `group.isShutdown()` | Biết group đã được đánh dấu shutdown | Không đồng nghĩa tài nguyên đã giải phóng |
| `group.isTerminated()` | Kiểm tra group đã terminated, thread pool đi kèm cũng terminated | Không phải trạng thái mỗi business request, không thay `Future`/state tracking |
| `group.awaitTermination(t,u)` | Đợi group thực sự terminated hoặc hết thời hạn/chịu interrupt | **Không chủ động đóng socket**; có thể trả false vì channel còn mở |
| `group.shutdownNow()` | Yêu cầu forceful shutdown, đóng **mọi channel đang mở trong group** | **Không** đảm bảo callback đang chạy bị interrupt/cắt ngang; cần chờ termination |
| `channel.close()` | Đóng riêng channel; operation outstanding thất bại theo hợp đồng | Không dừng group nếu còn channel/callback khác |

Javadoc quy định một group orderly-terminated khi **tất cả channel gắn với group đã đóng**, **các completion handler đang hoạt động đã chạy xong** và tài nguyên của group đã được giải phóng. `shutdown()` đánh dấu trạng thái, còn `awaitTermination` chỉ chờ; sự kiện “đóng hết channel” không tự phát sinh chỉ vì đã gọi shutdown.

### 6.2. `shutdownNow()` là phương án cuối, không phải graceful default

`shutdownNow()` thực hiện hành vi shutdown cộng với việc đóng tất cả channel còn mở trong group như gọi `close` cho chúng. Operation pending có thể đi vào `failed(AsynchronousCloseException)`. Hàm này **không cố dừng/interrupt completion handler đang thực thi**; group vẫn chỉ được xem terminated sau khi các handler tích cực kết thúc và tài nguyên được giải phóng.

Nếu callback chứa I/O blocking bên ngoài, vòng lặp vô tận hoặc tự chờ completion cần cùng group thread, `shutdownNow()` không phải một chiếc “kill switch” bảo đảm chấm dứt lập tức. Callback phải thiết kế **ngắn, không block vô hạn, phản ứng với cờ dừng** và có công cụ giám sát.

### 6.3. Đừng shutdown nhầm group dùng chung

- Channel tạo không truyền group dùng **default asynchronous channel group** của JVM; dịch vụ không nên xem đó là nhóm riêng độc quyền nếu nhiều module cùng dùng.
- Nếu truyền một `ExecutorService` vào `withThreadPool(...)` hoặc `withCachedThreadPool(...)`, group **quản lý vòng đời executor** này. Tài liệu nhấn mạnh executor đó nên dành riêng cho group; tự shutdown executor từ một thành phần khác có thể dẫn đến hành vi không xác định.
- Nếu một service quản lý nhiều nhóm độc lập, phải biết **channel nào thuộc group nào** và ai chịu trách nhiệm kết thúc. Đóng group của service A không nên bất ngờ làm service B mất callback.

## 7. Thứ tự graceful shutdown đúng

Hãy định nghĩa bốn trạng thái rõ ràng:

```text
RUNNING
  │ nhận yêu cầu dừng
  ▼
STOPPING_ADMISSION
  - đánh dấu stopping=true; ngăn accept/submit công việc mới
  - đóng listener; pending accept có thể failed (expected)
  │
  ▼
DRAINING
  - đợi các request đã nhận, queued writes và callbacks hoàn tất
  - không tạo request mới; có bounded deadline
  │
  ├── drain thành công ──────────────────────┐
  │                                         │
  └── quá deadline → đánh dấu aborted ──────┤
                                            ▼
CLOSING_CHANNELS
  - đóng accepted/client channels còn thuộc service
  - hoàn tất request pending bằng lỗi nếu cần
  │
  ▼
GROUP_SHUTDOWN
  - group.shutdown()
  - group.awaitTermination(timeout, ...)
  │
  ├── terminated -> STOPPED
  │
  └── chưa terminated -> group.shutdownNow()
                         -> awaitTermination lần cuối
                         -> log/alert nếu vẫn chưa xong
```

Điều kiện **drained** không nên chỉ là “đã gửi xong một phần bytes” hoặc “đang không thấy callback mới”. Trong server, cần theo dõi ít nhất **active connections**, **in-flight request count**, **pending outbound buffers/writes**, **business tasks đang chạy** và **callback completion**.

Trình tự khuyến nghị:

1. **Chặn admission trước.** Set cờ lifecycle, ngăn đăng ký accept mới và stop nhận message nghiệp vụ mới. Đóng `AsynchronousServerSocketChannel` để hủy pending accept; callback `failed` phải biết đây là shutdown dự kiến.
2. **Xử lý connection vừa được accept lúc đua với stop.** Nếu `accept.completed(peer)` chạy sau cờ STOPPING, đóng `peer` và không phục vụ request mới.
3. **Drain in-flight work có deadline.** Cho phép các connection đang thực hiện request hợp lệ hoàn tất và gửi response, bao gồm xử lý partial writes. Khi tất cả request/response hoàn tất, mới cho các channel đóng bình thường.
4. **Dọn accepted channels.** Với session hoàn tất, đóng channel. Với session quá hạn, mark failed/cancelled, đóng channel và giải phóng registry/buffers khi operation đã hoàn tất/thất bại.
5. **Kết thúc group.** `group.shutdown()`, rồi `group.awaitTermination(...)` từ **thread điều phối shutdown ở bên ngoài callback pool**.
6. **Escalate nếu cần.** Nếu quá thời hạn, `group.shutdownNow()`, chờ thêm có giới hạn và ghi cảnh báo nếu không terminated. Không hứa forced shutdown vẫn gửi đủ response.

### Thứ tự khác có hợp lệ không?

Có thể gọi `group.shutdown()` **sau khi đã ngừng admission nhưng khi còn channel mở**, vì shutdown không tự đóng chúng. Tuy nhiên cần chắc chắn callback còn chạy **không cần tạo thêm channel trong group**, và pending accept không đưa một accepted channel mới vào group đã shutdown. Để dễ review, bài này đề xuất **dừng accept → drain → đóng socket → shutdown group**.

**Không được chờ termination ngay khi còn nhiều channel mở mà chưa có ai chịu trách nhiệm đóng**, vì group có thể không đạt điều kiện kết thúc.

### Đừng gọi `awaitTermination` trong chính callback của group

Nếu callback đang chạy trên group thread gọi `group.awaitTermination(...)` và đợi group terminated, chính callback đó là **một handler còn đang active**. Nó có thể tự giữ điều kiện termination chưa thỏa hoặc gây thiếu thread cho những callback khác. Hãy dùng một **shutdown coordinator thread** riêng để chờ và tổng hợp kết quả.

## 8. Java 17+: đóng channel khi pending read, quan sát `failed`

Chương trình độc lập này tạo TCP listener và một client trên loopback, accept ra một server-side channel. Nó **khởi tạo một read đang chờ** nhưng **không gửi byte nào**, rồi đóng server-side channel. Callback phải hoàn tất đường thất bại. `CountDownLatch` khiến main đợi callback thay vì kết luận khi `close` vừa trả về.

**Tệp `AsyncCloseCallbackDemo.java`:**

```java
import java.net.*;
import java.nio.*;
import java.nio.channels.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class AsyncCloseCallbackDemo {
    public static void main(String[] args) throws Exception {
        AsynchronousChannelGroup group =
                AsynchronousChannelGroup.withFixedThreadPool(2, Thread::new);
        try {
            try (AsynchronousServerSocketChannel listener =
                         AsynchronousServerSocketChannel.open(group).bind(
                                 new InetSocketAddress(InetAddress.getLoopbackAddress(), 0));
                 AsynchronousSocketChannel client =
                         AsynchronousSocketChannel.open(group)) {
                Future<AsynchronousSocketChannel> pending = listener.accept();
                client.connect(listener.getLocalAddress()).get(3, TimeUnit.SECONDS);
                try (AsynchronousSocketChannel peer =
                             pending.get(3, TimeUnit.SECONDS)) {
                    CountDownLatch callbackDone = new CountDownLatch(1);
                    AtomicReference<Throwable> failure = new AtomicReference<>();
                    AtomicBoolean successfulRead = new AtomicBoolean();

                    peer.read(ByteBuffer.allocate(32), "request-1",
                            new CompletionHandler<Integer, String>() {
                                @Override public void completed(Integer count, String tag) {
                                    successfulRead.set(true);
                                    callbackDone.countDown();
                                }
                                @Override public void failed(Throwable error, String tag) {
                                    failure.set(error);
                                    callbackDone.countDown();
                                }
                            });

                    peer.close();
                    if (!callbackDone.await(3, TimeUnit.SECONDS)) {
                        throw new IllegalStateException("Callback did not finish");
                    }
                    if (successfulRead.get()
                            || !(failure.get() instanceof AsynchronousCloseException)) {
                        throw new IllegalStateException("Unexpected callback result: "
                                + failure.get());
                    }
                    System.out.println("Pending read failed: AsynchronousCloseException");
                    System.out.println("Channel open: " + peer.isOpen());
                }
            }
        } finally {
            group.shutdown();
            if (!group.awaitTermination(3, TimeUnit.SECONDS)) {
                group.shutdownNow();
                if (!group.awaitTermination(3, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Group did not terminate");
                }
            }
        }
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 -encoding UTF-8 AsyncCloseCallbackDemo.java
java AsyncCloseCallbackDemo
```

Stdout **đã kiểm chứng khi chạy trên JDK có hỗ trợ Java 17+**:

```text
Pending read failed: AsynchronousCloseException
Channel open: false
```

**Đọc kết quả đúng cách:**

1. `listener.accept()` trả `Future`; client connect, rồi chương trình lấy accepted peer.
2. `peer.read(..., callback)` bắt đầu một operation đang chờ byte. Client không ghi nên read chưa có dữ liệu để hoàn tất.
3. `peer.close()` kết thúc channel lúc read outstanding. Theo API `AsynchronousChannel`, operation thất bại bằng `AsynchronousCloseException`. Callback `failed` lưu nguyên nhân, thả latch.
4. `callbackDone.await(...)` đợi callback đi vào nhánh terminal. Nếu callback không hoàn tất đúng deadline, chương trình ném lỗi thay vì in dữ liệu giả.
5. Chỉ **sau** khi callback đã hoàn tất, chương trình mới đóng hết các channel còn lại, gọi `group.shutdown()` và chờ termination.
6. `AtomicReference`/`AtomicBoolean` được dùng làm nơi chuyển kết quả giữa callback thread và main. Việc main chờ latch cung cấp điểm đồng bộ rõ ràng.

Đây là **thí nghiệm có chủ ý tạo lỗi**. Production không nên thường xuyên đóng socket trước khi response hoàn tất rồi coi đó là graceful shutdown.

## 9. Java 17+: `group.shutdown()` không tự đóng channel còn mở

Thí nghiệm tiếp theo tạo group và một `AsynchronousSocketChannel` chưa connect. Nó đánh dấu shutdown khi channel vẫn mở, kiểm tra group chưa terminated, rồi đóng channel và chờ group thật sự kết thúc. Chưa connect không quan trọng cho việc kiểm tra **vòng đời group**.

**Tệp `AsyncGroupLifecycleDemo.java`:**

```java
import java.nio.channels.*;
import java.util.concurrent.*;

public class AsyncGroupLifecycleDemo {
    public static void main(String[] args) throws Exception {
        AsynchronousChannelGroup group =
                AsynchronousChannelGroup.withFixedThreadPool(2, Thread::new);
        AsynchronousSocketChannel channel = AsynchronousSocketChannel.open(group);
        try {
            group.shutdown();
            System.out.println("Group shutdown: " + group.isShutdown());
            System.out.println("Channel still open: " + channel.isOpen());
            System.out.println("Group terminated yet: " + group.isTerminated());

            boolean rejected = false;
            try (AsynchronousSocketChannel ignored =
                         AsynchronousSocketChannel.open(group)) {
                // Không đi đến đây khi group đã shutdown.
            } catch (ShutdownChannelGroupException expected) {
                rejected = true;
            }
            System.out.println("New channel rejected: " + rejected);
        } finally {
            channel.close();
            if (!group.isShutdown()) group.shutdown();
            if (!group.awaitTermination(3, TimeUnit.SECONDS)) {
                group.shutdownNow();
                if (!group.awaitTermination(3, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Group did not terminate");
                }
            }
        }
        System.out.println("Group terminated after close: "
                + group.isTerminated());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 AsyncGroupLifecycleDemo.java
java AsyncGroupLifecycleDemo
```

Stdout **đã kiểm chứng**:

```text
Group shutdown: true
Channel still open: true
Group terminated yet: false
New channel rejected: true
Group terminated after close: true
```

Ý nghĩa từng dòng:

- `group.shutdown()` bật trạng thái shutdown; group **không tự close channel** đang tồn tại.
- Khi channel còn mở, group chưa thỏa điều kiện terminated, nên `isTerminated()==false`.
- `AsynchronousSocketChannel.open(group)` mới bị từ chối với `ShutdownChannelGroupException`. Điều đó không có nghĩa channel cũ bị đóng.
- Sau `channel.close()` và chờ `awaitTermination` thành công, group mới kết thúc.
- Nếu chờ vượt hạn, ví dụ dùng `shutdownNow()` để giải phóng các channel còn sót; nhưng trong test thành công nhánh này không cần thiết.

Cần phân biệt **`group.isShutdown()`** (“đã nhận lệnh bắt đầu dừng”) với **`group.isTerminated()`** (“đã giải phóng đủ điều kiện”). Chỉ có trạng thái đầu tiên chưa đủ để báo service STOPPED.

## 10. Java 17+: dừng listener, xử lý xong response, đóng channel rồi mới kết thúc group

Đây là ví dụ **graceful theo thứ tự** được cô đọng để chạy trong một process: một listener async, một client async và một connection đã accept trên loopback.

1. Client connect; listener lấy accepted channel.
2. **Đóng listener** ngay sau accept, nghĩa là dừng nhận connection mới.
3. Hai bên trao đổi một message ngắn: `PING\n` và `PONG\n`. Ví dụ dùng `Future.get(timeout)` để dễ kiểm chứng thứ tự, không giả làm một server callback non-blocking hoàn chỉnh.
4. Các phương thức `sendAll` và `readExactly` có vòng lặp để xử lý **partial write/read**, không giả định một call sẽ gửi/nhận đủ 5 byte.
5. Đóng hai socket đang giao tiếp rồi `group.shutdown()` và `awaitTermination`.

**Tệp `AsyncOrderlyDrainDemo.java`:**

```java
import java.io.EOFException;
import java.net.*;
import java.nio.*;
import java.nio.channels.*;
import java.nio.charset.*;
import java.util.concurrent.*;

public class AsyncOrderlyDrainDemo {
    private static void sendAll(AsynchronousSocketChannel channel, String text)
            throws Exception {
        ByteBuffer buffer = StandardCharsets.UTF_8.encode(text);
        while (buffer.hasRemaining()) {
            channel.write(buffer).get(3, TimeUnit.SECONDS);
        }
    }

    private static String readExactly(AsynchronousSocketChannel channel, int n)
            throws Exception {
        ByteBuffer buffer = ByteBuffer.allocate(n);
        while (buffer.hasRemaining()) {
            int read = channel.read(buffer).get(3, TimeUnit.SECONDS);
            if (read == -1) throw new EOFException("Incomplete message");
        }
        buffer.flip();
        return StandardCharsets.UTF_8.decode(buffer).toString();
    }

    public static void main(String[] args) throws Exception {
        AsynchronousChannelGroup group =
                AsynchronousChannelGroup.withFixedThreadPool(2, Thread::new);
        try {
            try (AsynchronousServerSocketChannel listener =
                         AsynchronousServerSocketChannel.open(group).bind(
                                 new InetSocketAddress(InetAddress.getLoopbackAddress(), 0));
                 AsynchronousSocketChannel client =
                         AsynchronousSocketChannel.open(group)) {
                Future<AsynchronousSocketChannel> pending = listener.accept();
                client.connect(listener.getLocalAddress()).get(3, TimeUnit.SECONDS);
                try (AsynchronousSocketChannel serverPeer =
                             pending.get(3, TimeUnit.SECONDS)) {
                    listener.close();
                    System.out.println("Admission stopped: " + !listener.isOpen());

                    sendAll(client, "PING\n");
                    String request = readExactly(serverPeer, 5);
                    sendAll(serverPeer, "PONG\n");
                    String reply = readExactly(client, 5);
                    System.out.println("Server received: " + request.strip());
                    System.out.println("Client received: " + reply.strip());
                }
            }
        } finally {
            group.shutdown();
            if (!group.awaitTermination(3, TimeUnit.SECONDS)) {
                group.shutdownNow();
                if (!group.awaitTermination(3, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Group did not terminate");
                }
            }
        }
        System.out.println("Group terminated: " + group.isTerminated());
    }
}
```

Lệnh:

```bash
javac --release 17 -encoding UTF-8 AsyncOrderlyDrainDemo.java
java AsyncOrderlyDrainDemo
```

Stdout **đã kiểm chứng**:

```text
Admission stopped: true
Server received: PING
Client received: PONG
Group terminated: true
```

**Vì sao ví dụ này có giá trị?** `listener.close()` chỉ dừng admission của listener, **không tự đóng accepted peer**. Vì vậy serverPeer vẫn đọc PING, gửi PONG; client nhận phản hồi hoàn chỉnh; cuối cùng cả socket client và accepted server đóng trước khi group shutdown.

**Giới hạn được nêu rõ:** `Future.get()` làm thread main đợi từng bước, nên ví dụ chưa có throughput của hệ thống async production. Trong server phục vụ nhiều client, bạn dùng completion handlers hoặc state machine để không block thread đợi từng request; theo dõi các session đang active và deadline drain riêng. Đầu vào dài đúng 5 byte được chọn để phép thử deterministic, không phải framing chung cho mọi protocol. Với protocol thật, dùng length-prefix/delimiter, giới hạn kích thước và xác nhận nghiệp vụ nếu cần.

## 11. Thiết kế callback/server production: không để close và fail tạo rò rỉ

Ba ví dụ trên minh họa đúng contract của API, còn hệ thống phục vụ nhiều connection phải quản lý trạng thái phức tạp hơn.

### 11.1. Track **connection** và **operation** riêng

Một `activeConnections` set không đủ nếu đã bắt đầu callback cleanup mà chưa chạy xong hoặc có business task tách sang worker thread. Mỗi request có thể cần:

```text
ConnectionContext
  channel
  state = OPEN | DRAINING | CLOSING | CLOSED
  activeRead / activeWrite
  inputParser
  outboundQueue<ByteBuffer>
  outstandingRequestIds
  stopRequested
  lastActivity
  closeOnce / terminalOnce

ServiceContext
  listener
  asynchronousChannelGroup
  accepting = true|false
  activeConnections
  activeRequests
  pendingCallbacks
  pendingBusinessTasks
  drainDeadline
```

Đây là **sơ đồ dữ liệu minh họa**, không phải Java class được khai báo đầy đủ. Các counters có thể đưa vào `Phaser`, `CountDownLatch`, `CompletableFuture.allOf` hoặc cơ chế concurrency khác, nhưng phải thiết kế không bị lỡ sự kiện khi task hoàn tất rất nhanh hoặc khi task mới xuất hiện trong lúc shutdown.

### 11.2. Đếm in-flight phải nhất quán

Một mẫu logic hợp lý:

```text
Khi nhận request hợp lệ và được phép xử lý:
    increment activeRequests trước khi dispatch task.

Khi request kết thúc thành công, thất bại hoặc bị hủy:
    transition PENDING → TERMINAL bằng atomic compare-and-set.
    nếu là lần transition terminal đầu tiên:
        decrement activeRequests đúng một lần.
        thông báo Future/callback phía application.

Khi stopping:
    không tăng activeRequests cho request mới.
    chờ activeRequests == 0 AND pendingWrites == 0,
    sau đó đóng connections.
```

Nếu `failed` và timeout handler đều gọi `activeRequests.decrementAndGet()` mà không có state transition guard, counter có thể xuống âm và shutdown coordinator kết luận sai. Ngược lại, nếu callback ném exception trước khi decrement, group có thể không chấm dứt về mặt nghiệp vụ dù socket đã đóng.

### 11.3. Re-arm accept theo trạng thái

`AsynchronousServerSocketChannel.accept()` cho phép một accept outstanding. Callback `completed` chỉ nên re-arm **sau khi một accept hoàn tất** và dịch vụ vẫn RUNNING. Nếu ngừng dịch vụ:

- Set `accepting=false` trước.
- Đóng listener, làm pending accept thất bại nếu có.
- Trong `failed`, nếu `accepting=false` và failure phù hợp với close, ghi debug và **không re-arm**.
- Nếu accept hoàn tất ngay lúc stop, đóng accepted peer và không tạo session mới.
- Nếu accept lỗi bất thường khi RUNNING, áp dụng chính sách retry/backoff hoặc stop với cảnh báo; **không** gọi accept lại vô hạn liên tục.

Một race thường gặp: thread A set STOPPING, thread B đã đọc cờ RUNNING rồi re-arm accept vừa lúc listener bị đóng. Phải bắt ngoại lệ tại điểm khởi tạo/re-arm và bảo đảm không bỏ sót cleanup; một cờ `AtomicBoolean` đơn độc không biến toàn bộ chuỗi check→accept thành giao dịch nguyên tử.

### 11.4. Re-arm read/write và buffer ownership

Sau `read.completed(n)`:

- Nếu `n > 0`, chuyển buffer sang read mode theo `flip()` rồi parser tiêu thụ; giữ bytes thừa chưa tạo thành message.
- Nếu `n == -1`, xử lý EOF, kết thúc request đang chờ hoặc nửa đóng kết nối theo protocol.
- Khi STOPPING, có thể hoàn tất request đang xử lý nhưng **không nhận request nghiệp vụ mới** từ stream nữa.
- Nếu muốn đọc tiếp, chỉ khởi tạo **một read mới** khi read trước đã completed và channel chưa đóng/còn được phép xử lý. Tránh `ReadPendingException`.

Sau `write.completed(n)`:

- Nếu outbound buffer còn `hasRemaining()`, khởi tạo **write tiếp theo**.
- Nếu buffer hết, lấy buffer tiếp trong hàng đợi.
- Nếu queue hết, đánh dấu response đã được ghi xong ở tầng channel; nếu connection đang DRAINING thì có thể close theo protocol.
- Nếu `failed`, báo request không nhận được xác nhận đáng tin cậy, và đóng/cleanup theo chính sách. **Không tự nhận gửi được toàn bộ response chỉ vì `write.completed` một lần.**

Đừng gán `ByteBuffer` về một pool tái sử dụng trước khi read/write đã kết thúc hoặc thất bại và quyền sở hữu buffer đã rõ ràng. Callback có thể chạy muộn sau khi shutdown request bắt đầu.

### 11.5. Callback không nên block lẫn nhau

Completion-handler thread pool thường giới hạn. Nếu callback A đợi `CountDownLatch` mà callback B (phải chạy cùng pool) cần countDown, có thể gây deadlock hoặc starve. Chuyển công việc nặng như DB query, encode payload lớn, blocking HTTP call sang executor riêng có lifecycle do ứng dụng quản lý; callback nhanh chóng ghi trạng thái, enqueue công việc/response và trả quyền cho I/O dispatcher.

Tuy nhiên phải quản lý **shutdown thứ tự giữa executor nghiệp vụ và async group**: không tắt worker pool trước khi các callback cần worker hoàn tất, và không tắt channel group trước khi đã dừng admission và xác định số request trong flight.

## 12. Sai lầm thường gặp khi kết thúc nhóm

| Sai lầm | Vì sao sai | Cách sửa |
|---|---|---|
| Gọi `group.shutdown()` và bỏ qua các socket đang mở | Group có thể không terminated | Stop admission, drain rồi close từng channel; sau đó await |
| Gọi `shutdownNow()` ngay khi nhận SIGTERM | Cắt ngang response còn pending, callback failed hàng loạt | Có grace period/deadline trước khi force |
| Gọi `awaitTermination` từ chính completion handler | Handler đang active có thể tự ngăn group terminated | Dùng coordinator thread bên ngoài pool |
| Re-arm `accept` trong `failed` khi listener đã đóng | Exception/retry loop, spam log, tốn CPU | Check STOPPING; không re-arm |
| Bỏ trống `failed` | Request treo, leak state/counter | Log đúng ngữ cảnh, complete request, cleanup |
| Coi mọi `AsynchronousCloseException` là lỗi nghiêm trọng | Shutdown chủ động có thể tạo lỗi này | Phân loại theo trạng thái lifecycle |
| Coi mọi `AsynchronousCloseException` là “bình thường” | Có thể che bug đóng socket ở RUNNING | Chỉ giảm log khi đóng có chủ đích |
| Trừ active count trong cả timeout và callback | Counter sai; double-completion | Atomic terminal state/compareAndSet |
| Dùng lại buffer sau `cancel(true)` | Trạng thái buffer/I/O có thể không xác định | Chờ cleanup/đóng channel; không tái sử dụng vội |
| Gọi `Future.get(timeout)` rồi cho rằng I/O đã hủy | Timeout chỉ ảnh hưởng việc chờ Future | Hủy/đóng theo chính sách và ghi outcome chưa rõ |
| Tắt executor của group trực tiếp | Javadoc không đảm bảo hành vi nếu shutdown pool độc lập | Để group sở hữu executor của nó |
| Quên accepted socket được gắn cùng group với listener | Group còn channel nên không terminate | Track accepted channel, close hết |
| Coi `isOpen()==false` là mọi callback đã chạy xong | Callback có thể hoàn thành sau close | Đồng bộ callback terminal và group termination |
| Không có deadline drain | Peer chậm, callback treo làm shutdown vô hạn | Grace timeout, force fallback, metrics và cảnh báo |
| Không xử lý `InterruptedException` khi await | Có thể mất tín hiệu interrupt/thread tiếp tục sai | Lập policy cleanup, restore interrupt flag ở coordinator |
| Không phân biệt EOF `-1` và callback failure | Kết thúc chiều đọc bình thường bị gắn nhãn lỗi | Xử lý `completed(-1)` theo protocol |

### Thread interruption phải có chủ đích

`awaitTermination` có thể ném `InterruptedException`. Nếu shutdown coordinator bị interrupt, ứng dụng cần thực hiện chính sách cleanup bắt buộc (có thể force close), rồi **khôi phục interruption** bằng `Thread.currentThread().interrupt()` khi thích hợp. Đừng nuốt interrupt rồi chờ vô hạn bằng một vòng retry không kiểm soát.

Ví dụ pseudocode:

```text
try:
    group.shutdown()
    if not group.awaitTermination(grace):
        group.shutdownNow()
        if not group.awaitTermination(forceGrace):
            alert("group still not terminated")
catch InterruptedException:
    request forced cleanup if required by policy
    restore interrupt flag before returning
```

Đây là pseudocode, không phải cú pháp Java chạy trực tiếp; code thật cũng phải xử lý `IOException` từ `shutdownNow()`.

## 13. Kiểm chứng shutdown bằng log và phép thử có kiểm soát

Một hệ thống không nên chỉ log “shutdown initiated”. Ghi nhận trạng thái cuối cùng và những khoản chưa hoàn tất.

### Các mốc nên đo

```text
timestamp | serviceId | lifecycleState | activeConnections
          | activeRequests | pendingWrites | pendingCallbacks
          | groupShutdown | groupTerminated | remainingDeadline
          | reason | errorClass | requestId
```

Để điều tra một lỗi callback, log `operation=ACCEPT/CONNECT/READ/WRITE`, `channelId`, `cause`, `stopping flag` và `requestId`. Không đưa payload nhạy cảm hoặc thông tin xác thực vào log.

### Ma trận kiểm chứng

| Thử nghiệm | Bằng chứng mong muốn | Kết luận hợp lệ |
|---|---|---|
| Close socket khi pending read | Callback `failed(AsynchronousCloseException)` | Channel close tác động lên outstanding operation |
| Close listener khi pending accept | Accept callback `failed` theo chính sách shutdown | Listener ngừng admission; không re-arm |
| `group.shutdown` khi còn channel mở | `isShutdown=true`, `isTerminated=false` | Shutdown không tự đóng mọi channel |
| Close mọi channel, callback kết thúc | `awaitTermination=true` | Group đã kết thúc trong deadline |
| Gửi request và drain trước close | Response đầy đủ rồi group terminated | Trình tự graceful được thử thành công với workload demo |
| Request đang pending lâu hơn grace | Force close, callback thất bại, request thành FAILED | Có xử lý escalation khi hết thời gian |
| Callback cố re-arm sau STOPPING | Không tạo accept/read mới | Lifecycle guard hoạt động |
| Race timeout và callback completed | Pending request chỉ một terminal outcome | Không double-complete hoặc trừ count hai lần |
| Outbound write partial | Gửi hết buffer trước khi close | Không mất bytes do bỏ phần chưa ghi |
| Handler ném exception ở business logic | Task vẫn được đánh terminal/cleanup | Không leak active counters |

Cần phân biệt **test API** với **test guarantee nghiệp vụ**. Ví dụ một lần `write` hoàn tất và peer nhận `PONG` ở loopback xác nhận đường thử đó. Với mạng thực, lỗi mất kết nối sau commit có thể khiến client chưa biết request đã chạy hay chưa; giải pháp cần correlation ID/idempotency, không thể suy ra chỉ từ callback.

## 14. Thiết kế một hàm shutdown coordinator

Một ứng dụng production nên có một đối tượng quản lý lifecycle rõ ràng, thay vì nhiều callback tự quyết định đóng group. Hình thức thuật toán:

```text
shutdown(graceDeadline):
  if RUNNING -> STOPPING_ADMISSION bằng atomic transition:
      accepting = false
      close(listener)                  // callback accept bị đánh dấu expected
  else:
      return hoặc đợi shutdownFuture hiện có

  stop accepting new application requests
  wait until activeRequests==0 and pendingWrites==0
       OR graceDeadline reached

  for each open connection:
      if completed:
          close normally
      else:
          complete outstanding application request as failed/unknown
          close connection (may trigger failed callbacks)

  wait for terminal callbacks/cleanup (bounded)
  group.shutdown()

  if not group.awaitTermination(groupGrace):
      group.shutdownNow()
      if not group.awaitTermination(forceGrace):
          record critical incident; do not claim fully stopped

  signal shutdownFuture completion, report metrics
```

Đây **không phải Java code copy chạy**, vì còn thiếu registry, atomic state machine, quota và chính sách nghiệp vụ. Những ranh giới cần thiết để một implementation đúng:

- **Admission stop phải xảy ra một lần** và được thông báo tới các callback đang chạy.
- **Completion của request phải idempotent**: timeout, close và operation failure không được hoàn tất cùng request hai lần.
- **Drain có deadline thực tế**, và không để một client chậm khóa toàn hệ thống.
- **Close xảy ra sau xử lý đủ outbound bytes khi có thể**, nhưng vẫn có force path cho request quá hạn.
- **Shutdown group sau khi ownership các channel đã rõ**; không chờ vô hạn ở main thread hay callback pool.
- **Thành công cuối** chỉ được báo khi `isTerminated()` đúng hoặc `awaitTermination` trả true. Nếu quá hạn, ghi rõ điều gì chưa hoàn tất.
- **Không bỏ mất business outcome**: nếu write/response thất bại nhưng side effect có thể đã xảy ra, trạng thái phải phản ánh “chưa biết”, cần truy vấn hoặc dedup/idempotency.

### Phạm vi nào là “graceful”?

Graceful **không đồng nghĩa** mọi client buộc phải nhận response thành công. Nó nghĩa là hệ thống:

1. Ngừng tạo công việc mới đúng thời điểm.
2. Cố hoàn thành công việc đã được chấp nhận theo deadline/chính sách.
3. Thông báo rõ kết quả hoặc trạng thái chưa xác định.
4. Giải phóng tài nguyên theo một thứ tự kiểm soát.
5. Có đường kết thúc cưỡng bức và có thể kiểm chứng khi grace period hết.

Nếu một client không đọc dữ liệu, outbound write có thể treo. Khi đó việc hết hạn grace và đóng channel là hành vi có chủ đích, không phải “shutdown thất bại hoàn toàn”; tuy nhiên không được ghi nhận message đã được client xử lý nếu không có acknowledgement.

## 15. Tự kiểm tra

**Câu 1.** `AsynchronousSocketChannel.read(...)` đang pending; thread khác gọi `close()`. Callback có nên coi đó là read trả `-1` không?  
**Đáp án:** Không. Read pending được hoàn tất thất bại theo hợp đồng `AsynchronousChannel`, đi vào `failed` với `AsynchronousCloseException`. `completed(-1)` là EOF của chiều đọc, hai đường khác nhau.

**Câu 2.** `group.shutdown()` đã chạy, nhưng còn một `AsynchronousSocketChannel` mở. `awaitTermination` có bắt buộc trả true ngay không?  
**Đáp án:** Không. Group chỉ terminated khi các channel gắn với nó đã đóng, các completion handlers còn hoạt động đã kết thúc và tài nguyên đã được giải phóng.

**Câu 3.** Vì sao `group.shutdownNow()` không được coi là cách đảm bảo mọi callback đang chạy lập tức dừng?  
**Đáp án:** Nó đóng các channel còn mở, nhưng Javadoc không yêu cầu interrupt các completion handlers đang thực thi. Các handler vẫn phải kết thúc để group terminated.

**Câu 4.** Đóng listener có làm mọi accepted client socket tự đóng theo không?  
**Đáp án:** Không. Những accepted `AsynchronousSocketChannel` đã được tạo là các channel riêng; phải quản lý/đóng chúng theo connection lifecycle.

**Câu 5.** Khi server đang STOPPING, callback accept `failed(AsynchronousCloseException)` chạy. Có nên gọi `accept` lại ngay không?  
**Đáp án:** Không. Lỗi này có thể là hệ quả dự kiến của việc đóng listener; re-arm trái lifecycle có thể gây vòng lỗi. Hoàn tất stop-admission và cleanup.

**Câu 6.** `Future.get(2, SECONDS)` ném `TimeoutException`. Operation chắc chắn đã hủy?  
**Đáp án:** Không. Chỉ thread đợi đã quá thời gian; underlying I/O có thể còn pending. Quyết định cancel/close riêng và không vội tái sử dụng buffer.

**Câu 7.** `read` với async timeout ném `InterruptedByTimeoutException`. Có thể tin `ByteBuffer.position` vẫn phản ánh chính xác bytes chưa đọc không?  
**Đáp án:** Không chắc. JDK cảnh báo trạng thái buffer và chiều I/O có thể không xác định trong một số trường hợp timeout.

**Câu 8.** Vì sao không gọi `group.awaitTermination` từ trong một completion handler của chính group đó?  
**Đáp án:** Handler ấy vẫn đang active, có thể giữ điều kiện terminated chưa thỏa và làm thiếu thread cho các callbacks khác. Dùng coordinator riêng.

**Câu 9.** Một channel có thể có hai read outstanding nhưng không có lỗi vì hai thread khác nhau?  
**Đáp án:** Không. `AsynchronousSocketChannel` chỉ hỗ trợ tối đa một read outstanding; read thứ hai có thể ném `ReadPendingException`. Tương tự write.

**Câu 10.** Nếu `write.completed(512)` nhưng buffer ban đầu có 2.048 byte, đã an toàn close để đảm bảo peer nhận đủ message chưa?  
**Đáp án:** Chưa. Cần tiếp tục gửi phần `ByteBuffer.hasRemaining()` và, nếu nghiệp vụ yêu cầu, nhận xác nhận từ ứng dụng bên kia. Hoàn tất write không tự đảm bảo peer đã xử lý message.

**Câu 11.** `CompletionHandler.failed` và timer timeout đều thấy cùng request chưa hoàn tất. Cách nào tránh trừ active count hai lần?  
**Đáp án:** Dùng state terminal atomic, ví dụ compare-and-set `PENDING → FAILED/TIMED_OUT`, rồi chỉ thread thắng transition mới complete request và decrement counter.

**Câu 12.** Dùng `AsynchronousChannelGroup.withThreadPool(executor)` rồi gọi `executor.shutdownNow()` từ module khác có an toàn không?  
**Đáp án:** Không nên. Executor được thiết kế dành riêng cho group và group sở hữu lifecycle; shutdown executor riêng gây hành vi không được Javadoc bảo đảm.

**Câu 13.** Sau `close()`, `channel.isOpen() == false` có chứng minh mọi callback đã chạy hết và group terminated không?  
**Đáp án:** Không. Cần đồng bộ callback terminal và điều kiện termination riêng.

**Câu 14.** Group bị kẹt không terminated sau khi shutdown; nên kiểm tra gì trước khi kết luận JDK lỗi?  
**Đáp án:** Kiểm tra channel còn mở, pending accept/read/write, callback block, business worker chờ nhau, state counters, executor ownership và lời gọi `awaitTermination` có nằm trong group thread không.

## 16. Tóm tắt vận dụng

- **`close(channel)`** tác động trực tiếp lên outstanding operation; callback `failed(AsynchronousCloseException)` là hậu quả có thể dự kiến của việc đóng khi đang chờ.
- **`failed(Throwable,attachment)`** phải hoàn tất đường lỗi, cleanup, log/metric theo lifecycle; không re-arm việc mới khi STOPPING.
- **`shutdown(group)`** bắt đầu orderly shutdown nhưng **không tự đóng mọi channel**. `isShutdown` và `isTerminated` là hai trạng thái khác nhau.
- **`awaitTermination`** chờ các channel đóng, callback hoàn tất và tài nguyên được giải phóng; không nên gọi từ callback của cùng group.
- **`shutdownNow`** là force path đóng channel, **không** cam kết interrupt handler đang chạy.
- Trình tự dễ review nhất: **stop admission → drain trong deadline → đóng channel → shutdown group → await → force fallback**.
- Future timeout/cancel và callback failure cần được phân biệt; khi I/O chưa biết kết quả, **không tự xem side effect đã thất bại**.
- Viết một shutdown coordinator có atomic state, tracking in-flight, deadline và kiểm chứng group terminated đáng tin cậy hơn việc mỗi callback tự đóng tài nguyên tùy hứng.

### Tài liệu API Java 17

- [`AsynchronousChannel`: close/cancellation và operation outstanding](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousChannel.html)
- [`AsynchronousChannelGroup`: threading, shutdown, shutdownNow và awaitTermination](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousChannelGroup.html)
- [`AsynchronousSocketChannel`: read/write, connect, timeout và half-close](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousSocketChannel.html)
- [`AsynchronousServerSocketChannel`: accept và pending accept](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousServerSocketChannel.html)
- [`CompletionHandler`: completed/failed](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/CompletionHandler.html)
- [`Future`: get, cancel và các kết quả bất đồng bộ](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
