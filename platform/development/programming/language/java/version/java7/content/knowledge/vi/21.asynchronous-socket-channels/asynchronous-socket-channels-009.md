# Tổ chức dừng máy chủ và thu hồi tài nguyên với kênh mạng bất đồng bộ trong Java

## 1. Vì sao cần thiết kế shutdown đúng cách?

Một máy chủ dùng `AsynchronousServerSocketChannel` nhận kết nối bằng `accept()`; mỗi kết nối đã accept là một `AsynchronousSocketChannel` riêng. Những `read()`/`write()` còn đang pending có thể hoàn tất sau một khoảng thời gian, còn `CompletionHandler` có thể chạy trên các threads của `AsynchronousChannelGroup`.

Nếu ứng dụng chỉ gọi `System.exit(...)` hoặc đóng mọi socket ngay khi nhận yêu cầu dừng, nó có thể làm mất response chưa gửi hết, khiến buffer/I/O pending bị bỏ quên hoặc để thread pool và các session còn sót lại. Ngược lại, nếu cứ chờ mọi client chủ động đóng kết nối, một client idle có thể giữ máy chủ sống vô hạn.

Vì vậy bài học **“Tổ chức dừng máy chủ và thu hồi tài nguyên”** thuộc nhóm **“Kênh mạng bất đồng bộ”** tập trung vào một quy trình có thể kiểm chứng:

~~~text
RUNNING: đang nhận và xử lý kết nối
     |
     | nhận yêu cầu stop
     v
STOPPING_ACCEPT: không nhận kết nối mới, close listener
     |
     v
DRAINING: ngừng nhận request mới, chờ công việc đã nhận
     |
     +-- hoàn tất trong deadline --> đóng sessions bình thường
     |
     +-- quá deadline -----------> force-close các sessions còn lại
     |
     v
SHUTTING_DOWN_GROUP: shutdown group mình sở hữu
     |
     v
TERMINATED: awaitTermination, báo kết quả, thu hồi tài nguyên
~~~

Đây là **state machine gợi ý ở tầng ứng dụng**, không phải những trạng thái có sẵn trong một enum của Java. Mục tiêu là **graceful shutdown** (ưu tiên hoàn tất công việc đang chạy) nhưng có **deadline và forced fallback** khi cần.

**Phiên bản:** `AsynchronousServerSocketChannel`, `AsynchronousSocketChannel`, `AsynchronousChannelGroup`, `Future` và `CompletionHandler` là API Java NIO.2 có từ Java 7 và **vẫn được hỗ trợ trên Java 17, Java 21 và JDK hiện đại**. Ví dụ thực hành chạy trên **JDK 21**. Theo Special Note, bài chỉ dùng API/quy tắc hiện hành, không sử dụng kiến thức lỗi thời hoặc legacy.

Sau bài học, bạn phải biết:

- Phân biệt **đóng listener** với **đóng những socket đã accept**.
- Phân biệt `group.shutdown()`, `group.shutdownNow()` và `group.awaitTermination(...)`.
- Hiểu `AsynchronousCloseException` khi đóng channel có operation pending.
- Ngăn race giữa `accept` callback và stop flag.
- Quản lý session registry, buffer ownership, in-flight request và callback.
- Dừng cả nhóm channels/thread pool **đúng ownership**, không vô tình dừng group được service khác dùng.
- Xử lý timeout/cancel/force-close mà không khẳng định dữ liệu đã rollback.
- Chạy được một ví dụ có kết nối loopback, pending accept, graceful drain, EOF và group termination.

## 2. Các loại tài nguyên cần thu hồi

| Tài nguyên | Ví dụ | Ai chịu trách nhiệm cleanup? |
| --- | --- | --- |
| Listener | `AsynchronousServerSocketChannel` | Server; `close()` ngừng nhận kết nối |
| Accepted peer | `AsynchronousSocketChannel` trả từ `accept()` | Session manager; phải đóng **riêng** |
| Client socket | `AsynchronousSocketChannel` do client tạo | Client hoặc component sở hữu |
| Operation pending | `Future` của `accept/read/write` hoặc handler | Request owner: ghi nhận completion, lỗi, hủy |
| I/O buffer | `ByteBuffer` dùng trong async read/write | Operation owner; không tái dùng khi I/O chưa giải quyết |
| Channel group riêng | `AsynchronousChannelGroup` | Component tạo group; shutdown và await termination |
| Pool thuộc group | Pool tạo bởi `withFixedThreadPool` hoặc truyền vào group | **Group** quản lý shutdown pool lúc termination |
| Executor xử lý nghiệp vụ | Executor độc lập, database worker, timer | Service tạo/sở hữu, có lifecycle riêng |
| Registry và queue | Map sessions, outbound queue | Server/session; drain và clear theo chính sách |
| Protocol resources | File, transaction, lock, stream, TLS state | Request/session component sở hữu |

**Ownership là nguyên tắc cốt lõi.** Một listener không sở hữu toàn bộ group mặc định của JVM. Đóng listener không tự đóng accepted peers. Và dừng `AsynchronousChannelGroup` không tự giải phóng mọi executor nghiệp vụ/DB pool ngoài group.

### 2.1. Default group khác group tạo riêng

Khi gọi:

~~~java
AsynchronousServerSocketChannel listener =
        AsynchronousServerSocketChannel.open();
~~~

listener gắn với default asynchronous channel group của JVM. Default group có thể được nhiều components dùng; **không cố shutdown nó để dừng riêng một server**. Chỉ đóng các kênh mà service sở hữu.

Khi bạn tạo tường minh:

~~~java
AsynchronousChannelGroup group =
        AsynchronousChannelGroup.withFixedThreadPool(
                4, task -> new Thread(task, "my-server-io"));

AsynchronousServerSocketChannel listener =
        AsynchronousServerSocketChannel.open(group);
~~~

Đây là đoạn **minh họa**; production cần quản lý `close` listener và `shutdown/awaitTermination` group trong `finally`/lifecycle, kể cả khi bind hoặc start thất bại. Vì service tạo và sở hữu group riêng, nó có thể dừng group **sau khi các channels của mình đã đóng**. Group quản lý pool của chính nó.

## 3. Giai đoạn A — ngừng nhận kết nối mới

Thông thường server có một `accept` outstanding:

~~~java
Future<AsynchronousSocketChannel> pending = listener.accept();
~~~

Hoặc callback:

~~~java
listener.accept(attachment,
        new CompletionHandler<AsynchronousSocketChannel, Context>() {
            @Override
            public void completed(AsynchronousSocketChannel peer,
                                  Context context) {
                // Nhận một connected peer; quyết định đăng ký session.
            }

            @Override
            public void failed(Throwable error, Context context) {
                // Báo lỗi; khi stopping, đóng listener có thể là lỗi dự kiến.
            }
        });
~~~

Đây là những **mẫu chữ ký**, `Context`/`attachment` là kiểu và biến do ứng dụng tạo; không phải chương trình độc lập. Server channel chỉ cho phép **một accept pending** tại một thời điểm. Gọi accept lần thứ hai trước khi lượt trước hoàn tất có thể ném `AcceptPendingException`.

Khi nhận tín hiệu dừng:

1. Đặt `stopping=true` trong lifecycle state dùng chung.
2. Ngừng việc phát accept mới (không re-arm).
3. Gọi `listener.close()` để ngừng nhận kết nối.
4. Xử lý kết quả `accept` đang pending: có thể thất bại khi bị đóng, **hoặc đã thành công trước khi stop thắng race**.
5. Với peer đã accept thành công, hoặc đăng ký vào session registry để drain, hoặc đóng ngay nếu policy không chấp nhận mới.

### 3.1. Close listener khi accept còn pending

Theo Javadoc `AsynchronousChannel`, đóng channel khi một operation còn pending làm operation đó thất bại với `AsynchronousCloseException`. Với `Future`, lỗi nằm trong `ExecutionException.getCause()`; với `CompletionHandler`, callback nhận nó ở `failed(...)`.

~~~java
Future<AsynchronousSocketChannel> waiting = listener.accept();
listener.close();

try {
    AsynchronousSocketChannel unexpected = waiting.get();
    unexpected.close(); // Có thể accept thắng race: không bỏ quên peer.
} catch (ExecutionException ex) {
    if (ex.getCause() instanceof AsynchronousCloseException) {
        // Expected nếu shutdown chủ động đóng listener.
    } else {
        throw ex;
    }
}
~~~

Đây là **mẫu minh họa**; `listener` đã bind và không có `accept` khác pending. Trên server thực, `accept()` có thể đã hoàn tất với peer **trước** khi close, nên đừng khẳng định close “luôn” dẫn đến failure. Quan trọng là **xử lý cả nhánh thành công để không rò rỉ accepted socket**.

### 3.2. Vì sao stopping flag phải được đồng bộ?

Giả sử thread shutdown đặt `stopping`, còn callback accept đang chạy song song:

~~~text
Callback: hoàn tất accept một peer
Shutdown: stopping=true
Callback: kiểm tra stopping hoặc đăng ký peer
Shutdown: duyệt session registry và close
~~~

Nếu callback thêm peer vào registry **sau khi** shutdown đã quét registry mà không có đồng bộ, peer đó có thể bị bỏ sót và tồn tại ngoài vòng đời server. `AtomicBoolean stopping` có thể thông báo trạng thái, nhưng chỉ Boolean đơn lẻ không tự tạo một handoff nguyên tử giữa stop và registry insertion.

Một số chiến lược đúng: dùng lock bảo vệ lifecycle+registry, dùng single-threaded event loop xử lý start/accept/stop tuần tự, hoặc thiết kế registration theo generation/recheck. Quy tắc bất biến phải là **peer vừa accept chắc chắn được đăng ký để quản lý hoặc được đóng**.

## 4. Giai đoạn B — drain session và ngăn request mới trên kết nối cũ

Đóng listener **không chặn** một client đã connected tiếp tục gửi request trên socket giữ lâu (keep-alive). Server cần quy tắc tầng giao thức:

- Không nhận request nghiệp vụ mới sau khi đã vào `QUIESCING`, hoặc trả thông báo từ chối/phục vụ chuyển vùng theo protocol.
- Hoàn tất các requests đã **được chấp nhận** trước stop, trong giới hạn deadline.
- Chờ các response/outbound buffers đang gửi đủ hoặc xử lý failure rõ ràng.
- Với streaming dài hạn, thông báo kết thúc stream hay drain theo chính sách.
- Đóng connection bình thường sau khi đã hoàn tất phiên.
- Nếu client idle không chịu đóng, kết thúc khi đến deadline.

**Không chờ vô hạn chỉ vì muốn “graceful”.** Một stop operation tốt phải trả kết quả trong giới hạn vận hành có thể dự đoán, và ghi nhận số request buộc phải force-close.

### 4.1. TCP là byte stream

Một `write` hoàn tất với `count=100` chỉ cho biết thao tác I/O đã ghi 100 bytes theo API, **không chứng minh client đã đọc/xử lý response**. TCP không có ranh giới thông điệp logic mặc định; client có thể đọc dữ liệu qua nhiều lần read.

Tầng protocol phải có **framing** (độ dài cố định, length-prefix, delimiter) và ACK/idempotency khi nghiệp vụ cần. Nếu server đã commit DB nhưng response bị cắt bởi shutdown, client không biết kết quả và có thể retry. Không tự coi `write` thành công là transaction đã được phía bên kia xác nhận.

### 4.2. Một read và một write pending

Với `AsynchronousSocketChannel`, có thể có một read pending và một write pending trên cùng socket; nhưng **không được có hai read outstanding**, hoặc hai write outstanding. Có thể gặp `ReadPendingException` và `WritePendingException` nếu vi phạm. Vì vậy mỗi session thường có inbound buffer và **outbound queue có giới hạn**, submit lượt write tiếp **sau completion** của lượt trước.

ByteBuffer có mutable state: không chỉnh `position/limit`, `flip()`, `clear()` hoặc sửa bytes của một buffer khi I/O vẫn pending. Sau cancel/close, Javadoc cảnh báo underlying I/O và trạng thái buffer có thể không rõ ràng. Nếu không thể biết chắc, discard buffer theo policy thay vì gửi lại bừa bãi.

### 4.3. Half-close khác full close

~~~java
peer.shutdownOutput();
~~~

Lời gọi này ngừng hướng **gửi** của peer; client sau khi nhận hết bytes còn lại có thể đọc được `-1` (EOF). Hướng nhận của peer vẫn có thể hoạt động nếu chưa shutdown. Đây là *half-close*, khác `peer.close()`.

Chỉ dùng half-close khi đúng giao thức. Với keep-alive, TLS hoặc multiplexed streams, cần thủ tục đóng do protocol định nghĩa; không coi TCP EOF là ACK hoặc thông báo “đã xử lý giao dịch”.

## 5. Giai đoạn C — đóng channels và giải quyết pending operations

Một `AsynchronousSocketChannel.close()` sẽ đóng kết nối tương ứng; các asynchronous operations chưa hoàn tất trên channel đó thất bại với `AsynchronousCloseException`. Những operations mới khởi tạo sau close không thể chạy bình thường; xử lý `ClosedChannelException` hoặc lỗi provider tương ứng.

| Trường hợp | Trong đường shutdown | Điều phải làm |
| --- | --- | --- |
| `AsynchronousCloseException` | Thường là kết quả có chủ đích khi close kênh đang I/O | Báo kết thúc theo state, không log thành lỗi RUNNING vô điều kiện |
| `ClosedChannelException` | Operation mới sau close | Chặn submit mới, sửa bug lifecycle nếu bất ngờ |
| `AcceptPendingException` | Hai accept đồng thời | Chỉ re-arm khi lượt trước hoàn tất |
| `ReadPendingException` / `WritePendingException` | Hai thao tác cùng chiều pending | Per-connection state machine và queue |
| `ExecutionException` | Future hoàn tất lỗi | Xem cause thay vì nuốt exception |
| `InterruptedException` | Thread đang đợi bị interrupt | Restore interrupt hoặc propagate, sau đó cleanup |
| `TimeoutException` | `Future.get(timeout)` hết giờ | I/O có thể vẫn pending; có chính sách force-close |
| `CancellationException` | Future bị cancel | Không suy ra bytes chưa được truyền |
| `IOException` | Network/provider error | Hoàn tất outcome của request và đóng/cleanup |

**Giải quyết callback** rất quan trọng: nếu khi close pending read/write chuyển sang `failed`, handler phải báo lỗi cho promise/request và gỡ session khi thích hợp. Đừng chỉ log rồi để caller chờ vô hạn một `CompletableFuture` chưa được hoàn tất.

### 5.1. `Future.cancel(true)` không phải rollback

Javadoc `AsynchronousChannel` nói cancellation có thể không hủy được underlying I/O. `cancel(true)` có thể đóng channel theo implementation, khiến các operations khác thất bại; buffer đang dùng có thể đã được thay đổi một phần.

Trong shutdown, tránh chiến lược “cancel mọi Future, sau đó dùng lại buffer và gửi lại tất cả”. Với giao thức quan trọng, dùng request IDs, deduplication, trạng thái transaction và client retries theo chính sách để tránh side effects lặp.

### 5.2. Close idempotent và ownership accepted sockets

Một session phải có `close` idempotent về **state của ứng dụng** (không phát duplicate callback/outcome), và luôn gỡ khỏi registry kể cả khi I/O fail. Bản thân việc gọi `close` lặp trên channel đã đóng không tạo ra phiên I/O mới, nhưng cleanup code vẫn phải xử lý `IOException` có thể xảy ra.

Accepted peer **không tự đóng khi listener đóng**. Đảm bảo listener owner và session owner không trùng lẫn hoặc bỏ trống quyền sở hữu.

## 6. Giai đoạn D — `AsynchronousChannelGroup.shutdown()`, `shutdownNow()` và `awaitTermination()`

`AsynchronousChannelGroup` có thread pool để xử lý asynchronous I/O completions và dispatch `CompletionHandler`. Java SE 21 phân biệt rõ:

| API | Ý nghĩa |
| --- | --- |
| `group.shutdown()` | Bắt đầu orderly shutdown; không cho tạo channel **mới** gắn group |
| `group.isShutdown()` | Group đã được đánh dấu shutdown hay chưa |
| `group.isTerminated()` | Group đã giải phóng channels/handlers/resources và associated pool đã terminated |
| `group.awaitTermination(timeout,unit)` | Đợi termination tối đa một khoảng thời gian; trả true/false |
| `group.shutdownNow()` | Force-close mọi open channels thuộc group; **không** cố interrupt callback threads đang thực thi |
| `withFixedThreadPool(n, factory)` | Group với fixed number of pool threads |
| `withThreadPool(executor)` | Group dùng executor được cung cấp; group quản lý shutdown pool sau termination |
| `withCachedThreadPool(executor, initialSize)` | Group dùng pool có thể tạo thêm threads theo nhu cầu |

### 6.1. `shutdown()` không tự đóng các sessions

Khi group orderly shutdown, những channels **đã có** vẫn có thể tiếp tục xử lý request/response. Group chỉ terminated khi:

1. Mọi asynchronous channels bound vào group đã đóng.
2. Các completion handlers đang chạy đã kết thúc.
3. Những tài nguyên khác của group được giải phóng.
4. Associated pool đã terminated.

Gọi `group.shutdown()` rồi mong `awaitTermination` trả true trong khi một listener hoặc một peer còn mở là sai. Bạn phải đóng các channels do server sở hữu. Ví dụ hoàn chỉnh bên dưới chứng minh **group.isShutdown()==true trong khi peer.isOpen()==true và TCP I/O vẫn thành công**.

### 6.2. `shutdownNow()` là forced close channels, không phải “giết mọi handler”

Theo Javadoc, `group.shutdownNow()` có hiệu lực force-close tất cả open channels trong group. Nhưng nó **không tìm cách interrupt** threads đang thực thi `CompletionHandler`. Vì vậy một handler xử lý đồng bộ quá lâu hoặc bị deadlock vẫn có thể cản trở termination.

Đừng chặn lâu bằng `Future.get()` hoặc `awaitTermination()` bên trong chính pool callback; để thread coordinator riêng điều phối shutdown.

### 6.3. Không tự ý shutdown external executor của group

Nếu code tạo:

~~~java
ExecutorService executor = Executors.newFixedThreadPool(4);
AsynchronousChannelGroup group =
        AsynchronousChannelGroup.withThreadPool(executor);
~~~

Đây là đoạn minh họa, không phải full program. Javadoc chỉ rõ executor này **nên chỉ dành riêng cho group**; việc tự gọi `executor.shutdown()` hoặc `shutdownNow()` trong khi group còn dùng cho kết quả **không được đặc tả**. Group sẽ orderly shutdown executor khi group terminated. Nếu service khác cũng dùng executor đó, ownership đã sai từ đầu.

Không dừng default JVM group để dừng một listener; không dừng một group chia sẻ khi vẫn có service khác cần group đó.

### 6.4. Trình tự dùng group do server sở hữu

~~~java
// Minh họa, các biến và session registry được định nghĩa ở ngoài.
listener.close();
// Ngừng nhận jobs mới; drain và đóng mọi accepted sockets.
group.shutdown();

boolean terminated = group.awaitTermination(5, TimeUnit.SECONDS);
if (!terminated) {
    group.shutdownNow();
    terminated = group.awaitTermination(5, TimeUnit.SECONDS);
}
// Báo outcome; không tự giả định true sau timeout.
~~~

Không copy mù thời gian 5 giây vào mọi production server: deadline phải dựa theo yêu cầu vận hành, số sessions và giao thức. Khi `awaitTermination` trả false, server **chưa được chứng minh đã dừng hẳn**.

### 6.5. Group đã shutdown nhưng listener còn mở?

Javadoc `AsynchronousServerSocketChannel` mô tả nếu group đã shutdown mà một accept hoàn tất với kết nối mới, kết nối đó bị đóng và operation có thể thất bại với `IOException` có cause `ShutdownChannelGroupException`. Điều này củng cố thứ tự **dừng và đóng listener trước, không để listener tiếp tục accept trong group đã shutdown**.

## 7. Chương trình Java 21 chạy được: graceful shutdown trên loopback

Bài kiểm thử này tạo server và client **trong cùng một JVM**, dùng loopback address và port `0` (OS tự gán port), không gọi Internet.

Nó thực hiện đúng thứ tự:

1. Tạo **một `AsynchronousChannelGroup` riêng** với `withFixedThreadPool(4,...)`.
2. Mở listener và client trong group; server khởi tạo một `accept`, client connect tới nó.
3. Lấy accepted peer.
4. Bắt đầu accept thứ hai, **không tạo client thứ hai**, rồi `listener.close()`.
5. Xác minh Future của accept đang pending thất bại do `AsynchronousCloseException`.
6. Gọi `group.shutdown()`, xác nhận peer vẫn mở.
7. Chuyển request `ping` và response `ok` trong **group đã isShutdown**.
8. Peer `shutdownOutput()`, client đọc `-1` EOF.
9. Đóng peer/client/listener, đợi `group.awaitTermination` và xác nhận true.
10. Trong `finally`, nếu group chưa terminated, dùng `shutdownNow()` để tránh leak và chờ có thời hạn.

Chương trình dùng hai helper đọc đủ N bytes/ghi đến khi hết `ByteBuffer` để **không giả định một TCP read/write sẽ xử lý trọn một logical message**. Timeout 5 giây trong demo chỉ dùng cho bài test có giới hạn thời gian, không phải SLA của ứng dụng.

Tạo file `src/main/java/demo/GracefulAsyncShutdownExample.java`:

~~~java
package demo;

import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousChannelGroup;
import java.nio.channels.AsynchronousCloseException;
import java.nio.channels.AsynchronousServerSocketChannel;
import java.nio.channels.AsynchronousSocketChannel;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class GracefulAsyncShutdownExample {
    private GracefulAsyncShutdownExample() {}

    static int writeAll(AsynchronousSocketChannel channel, String message)
            throws Exception {
        ByteBuffer buffer = ByteBuffer.wrap(
                message.getBytes(StandardCharsets.UTF_8));
        int total = 0;
        while (buffer.hasRemaining()) {
            int n = channel.write(buffer).get(5, TimeUnit.SECONDS);
            if (n <= 0) {
                throw new IOException("Write made no progress");
            }
            total += n;
        }
        return total;
    }

    static String readExactly(AsynchronousSocketChannel channel, int bytes)
            throws Exception {
        ByteBuffer buffer = ByteBuffer.allocate(bytes);
        while (buffer.hasRemaining()) {
            int n = channel.read(buffer).get(5, TimeUnit.SECONDS);
            if (n == -1) {
                throw new IOException("EOF before message complete");
            }
            if (n == 0) {
                throw new IOException("Read made no progress");
            }
        }
        buffer.flip();
        return StandardCharsets.UTF_8.decode(buffer).toString();
    }

    public static void main(String[] args) throws Exception {
        AsynchronousChannelGroup group =
                AsynchronousChannelGroup.withFixedThreadPool(
                        4, task -> new Thread(task, "graceful-demo-io"));
        try {
            AsynchronousServerSocketChannel listener =
                    AsynchronousServerSocketChannel.open(group);
            try {
                listener.bind(new InetSocketAddress(
                        InetAddress.getLoopbackAddress(), 0));
                try (AsynchronousSocketChannel client =
                        AsynchronousSocketChannel.open(group)) {
                    Future<AsynchronousSocketChannel> accepted = listener.accept();
                    client.connect(listener.getLocalAddress())
                            .get(5, TimeUnit.SECONDS);

                    try (AsynchronousSocketChannel peer =
                            accepted.get(5, TimeUnit.SECONDS)) {
                        System.out.println("client-connected=true");
                        System.out.println("accepted-peer-open=" + peer.isOpen());

                        Future<AsynchronousSocketChannel> waiting = listener.accept();
                        listener.close(); // Stop accepting; keep peers alive.

                        try {
                            AsynchronousSocketChannel unexpected =
                                    waiting.get(5, TimeUnit.SECONDS);
                            unexpected.close();
                            throw new AssertionError("Unexpected connection");
                        } catch (ExecutionException error) {
                            if (!(error.getCause() instanceof AsynchronousCloseException)) {
                                throw error;
                            }
                            System.out.println("pending-accept-closed=true");
                        }
                        System.out.println("listener-open=" + listener.isOpen());

                        group.shutdown(); // Does not close existing peers.
                        System.out.println("group-is-shutdown=" + group.isShutdown());
                        System.out.println("peer-still-open=" + peer.isOpen());

                        System.out.println("client-written=" + writeAll(client, "ping"));
                        System.out.println("peer-received=" + readExactly(peer, 4));

                        System.out.println("peer-written=" + writeAll(peer, "ok"));
                        System.out.println("client-received=" + readExactly(client, 2));

                        peer.shutdownOutput();
                        System.out.println("client-eof=" + client.read(
                                ByteBuffer.allocate(1)).get(5, TimeUnit.SECONDS));
                    }
                }
            } finally {
                listener.close(); // Idempotent, even after normal stop.
            }

            boolean terminated = group.awaitTermination(5, TimeUnit.SECONDS);
            System.out.println("group-terminated=" + terminated);
            if (!terminated) {
                throw new IOException("Group did not terminate in time");
            }
        } finally {
            if (!group.isTerminated()) {
                group.shutdownNow();
                group.awaitTermination(5, TimeUnit.SECONDS);
            }
        }
    }
}
~~~

**Biên dịch và chạy với JDK 21** từ thư mục chứa `src/`:

~~~sh
javac --release 21 -encoding UTF-8 -Xlint:all -d out src/main/java/demo/GracefulAsyncShutdownExample.java
java -cp out demo.GracefulAsyncShutdownExample
~~~

**Stdout chính xác đã quan sát trên Windows loopback:**

~~~text
client-connected=true
accepted-peer-open=true
pending-accept-closed=true
listener-open=false
group-is-shutdown=true
peer-still-open=true
client-written=4
peer-received=ping
peer-written=2
client-received=ok
client-eof=-1
group-terminated=true
~~~

### 7.1. Phân tích từng mốc

**`client-connected=true`:** `client.connect(...).get(...)` hoàn tất thành công. Kênh client đã kết nối; không gửi dữ liệu trước khi connect xong.

**`accepted-peer-open=true`:** `server.accept()` hoàn tất và trả peer riêng, đang mở.

**`pending-accept-closed=true`:** chương trình không tạo client thứ hai nên accept pending bị `listener.close()` kết thúc; Future.get ném `ExecutionException` có cause `AsynchronousCloseException`. Nếu có client khác race vào lúc này, accepted socket có thể thành công; chương trình production phải có nhánh cleanup cho trường hợp đó.

**`listener-open=false`:** listener đã đóng; nó không còn nhận connections mới. Peer đã accept **không** tự bị đóng.

**`group-is-shutdown=true`:** lời gọi `group.shutdown()` đánh dấu group orderly shutdown. Nó không giết handler threads hoặc đóng những peer đã gắn group.

**`peer-still-open=true`:** peer vẫn mở sau group.shutdown, cho thấy cần quản lý vòng đời sockets riêng.

**`client-written=4`, `peer-received=ping`:** gửi/đọc bốn bytes của `ping` trên connection đang tồn tại sau khi group.shutdown; helpers xử lý partial I/O.

**`peer-written=2`, `client-received=ok`:** chiều ngược lại vẫn hoạt động. Đóng listener không làm hỏng stream của peer cũ.

**`client-eof=-1`:** sau khi peer gọi `shutdownOutput()` và dữ liệu đã được tiêu thụ, client read thêm thấy EOF. Đây là half-close TCP, không phải sự bảo đảm ứng dụng đã ACK giao dịch.

**`group-terminated=true`:** khi mọi channel đều đã đóng, group dừng và trả true trước deadline test. Associated thread pool của group cũng kết thúc theo contract.

### 7.2. Tại sao nhóm được shutdown trước khi gửi request?

Chương trình **cố ý làm như vậy để kiểm tra một tính chất quan trọng**: `group.shutdown()` không đóng những accepted peers. Trong production, thứ tự thường là **stop listener → drain requests → close peers → shutdown group**. Nhưng vẫn có thể đánh dấu group shutdown sớm nếu các existing channels không cần mở peer mới và lifecycle đã được kiểm soát. Đừng chuyển thứ tự thử nghiệm này thành lời khuyên luôn shutdown group trước mọi việc nếu server còn có protocol tạo channels mới.

### 7.3. Ý nghĩa của `finally` và try-with-resources

- Listener có `try/finally` vì cần `close()` **sớm** để dừng accept, trước khi method kết thúc.
- Client và accepted peer có try-with-resources để tự đóng khi block kết thúc.
- Group là resource được kết thúc qua `shutdown/awaitTermination`; nó không cần và không cung cấp quy trình try-with-resources giống channel trong ví dụ.
- Trong lỗi bất ngờ, `finally` của group gọi `shutdownNow()` để force-close các channels còn sống, rồi chờ có thời hạn. Không tự coi forced close là response đã được client nhận.

Code đã được kiểm tra với `javac --release 21 -Xlint:all` để tránh cả warning khi gọi `close()` tường minh trên một resource đang đặt trực tiếp trong try-with-resources.

## 8. Thiết kế cho máy chủ có nhiều sessions

Bài test chỉ có một accepted peer. Server production cần một **session registry** và một lifecycle coordinator; không thể chỉ có một biến `peer`.

Một state machine điển hình:

~~~text
RUNNING
  accept callback -> register peer -> start session
  read callback   -> parse frame -> submit bounded job
  write callback  -> update outbound queue

QUIESCING
  stopping=true
  close listener
  accept callback: newly accepted peer must be registered or closed
  reject new business requests on old sessions

DRAINING
  existing in-flight requests finish
  outbound responses flush under deadline
  sessions close and leave registry

FORCING
  deadline exceeded
  force-close remaining peers and cancel/settle promises
  group.shutdownNow() if group is exclusively owned

TERMINATED
  group.awaitTermination completed or explicit failure recorded
  no unowned sessions, no pending business tasks silently orphaned
~~~

### 8.1. Session lifecycle ownership

Một session có thể giữ:

- `AsynchronousSocketChannel`.
- Inbound/outbound buffer và frame parser.
- Bounded outbound queue.
- Thông tin request IDs, in-flight counters và promises.
- Deadline/timeout và cờ `closing`.
- Connection close once và callback cleanup.
- Một phương thức `beginDrain()` và một `close()` idempotent ở tầng ứng dụng.

**Không giữ session registry chỉ bằng weak references** và mong garbage collector đóng socket kịp trước shutdown. Đã nhận peer thì phải có strong ownership, cleanup rõ ràng và xác minh kết quả.

### 8.2. Race với callback accept

Ví dụ listener nhận peer mới đúng lúc stop:

~~~text
Thread A: accept completed(peer)
Thread B: stopping=true; snapshot(registry)
Thread B: close all peers in snapshot
Thread A: registry.add(peer) -> nếu không đồng bộ, peer bị bỏ sót
~~~

Giải pháp là đồng bộ điểm **quyết định chấp nhận peer** cùng với snapshot/đổi state shutdown, hoặc serial hóa xử lý lifecycle. `AtomicBoolean stopping` hữu ích nhưng **không đủ một mình** để đảm bảo không bỏ sót accepted peer nếu registration không được đồng bộ.

### 8.3. Callback phải không bị block lâu

Completion handlers được thực thi trong pool của group; nếu một callback gọi `awaitTermination` hoặc đợi Future khác trên cùng pool vô hạn, group có thể không thể hoàn tất những callback cần thiết. Hãy xử lý ngắn: ghi nhận bytes/result/error, tiếp tục một bước I/O hợp lệ, hoặc offload công việc nặng sang executor nghiệp vụ riêng có backpressure.

Không submit I/O mới khi session đã ở trạng thái closing, trừ hoạt động kết thúc protocol được cho phép. Không lập lại `listener.accept(...)` sau stopping/close.

### 8.4. Xử lý kết quả nghiệp vụ chưa xác định

Ví dụ server đã commit một giao dịch nhưng chưa gửi xong response khi shutdown cưỡng bức. Client không biết request đã thành công hay chưa. **Không thể suy ra kết quả nghiệp vụ** từ `AsynchronousCloseException` hoặc `Future.cancel(true)`.

Nếu nghiệp vụ quan trọng, dùng request ID, idempotency/deduplication, transaction record, kiểm tra trạng thái và ACK ở tầng ứng dụng. Graceful shutdown giảm xác suất mất response nhưng không thay thế recovery sau crash/mất điện.

## 9. Timeout, interrupted shutdown và forced fallback

Một shutdown coordinator nên dùng **một deadline tổng**, ví dụ tính bằng `System.nanoTime()` cho các khoảng thời gian, thay vì gọi nhiều lần `awaitTermination(30s)` khiến tổng thời gian chờ vượt dự kiến.

Khi `awaitTermination(timeout,unit)`:

- Trả `true`: group đã terminated.
- Trả `false`: hết thời gian chờ, **không phải** group đã terminated.
- Ném `InterruptedException`: thread điều phối bị interrupt; cần restore flag hoặc propagate và vẫn có cleanup an toàn.

Khi forced shutdown, log số active peers, requests chưa hoàn tất, thời gian chờ đã qua và lỗi close. Sau `shutdownNow()`, callback đang chạy có thể vẫn chưa xong; cần đợi lại có giới hạn rồi báo nếu termination chưa đạt được.

**Không coi `System.exit(0)` là một bước cleanup đáng tin để chạy khi pool vẫn còn việc.** Process kill hoặc mất điện có thể bỏ qua toàn bộ graceful shutdown; persistence/recovery phải được thiết kế riêng.

### 9.1. JVM shutdown hook có đủ không?

`Runtime.addShutdownHook(Thread)` có thể yêu cầu app stop khi JVM shutdown thông thường, nhưng nó không chạy trong mọi tình huống (ví dụ process bị kill cưỡng bức hoặc hệ thống mất điện). Hook nên **báo stop rồi chờ có hạn**, tránh block vô tận, không tự giả định logger/network/DB vẫn luôn sẵn sàng. Đừng viết toàn bộ shutdown logic chồng chéo trong nhiều hooks không có ordering rõ ràng.

### 9.2. Khi nào dùng `shutdownInput()` / `shutdownOutput()`?

Half-close chỉ nên được dùng khi đã gửi/nhận đúng theo giao thức. Nếu server gửi “đã dừng” trên một TCP connection, đừng `shutdownOutput()` **trước** khi outbound queue đã flush thành công; nếu không response bị cắt. Ngược lại, không giữ connection mãi nếu client không đọc và deadline đã hết.

## 10. Những lỗi shutdown dễ gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ gọi `group.shutdown()` | Existing channels vẫn mở, awaitTermination có thể timeout | Đóng listener/sessions riêng |
| Gọi `shutdownNow()` ngay từ đầu | Cắt I/O trước khi response hoàn tất | Drain trước, force khi cần |
| Close listener rồi coi mọi peer đã đóng | Rò rỉ accepted sockets | Session registry và close |
| Không ngừng re-arm accept | Tiếp tục nhận kết nối khi stop | stopping flag + listener.close |
| Bỏ qua nhánh accept thành công gần shutdown | Socket mới không ai sở hữu | Cleanup/registry trong mọi nhánh |
| Chờ drain vô hạn | Deploy treo do client idle | Global deadline |
| Gọi group shutdown trên group của service khác | Ảnh hưởng những channels khác | Sở hữu group rõ |
| Tự shutdown pool truyền cho group khi đang hoạt động | Hành vi không được API bảo đảm | Cho group quản lý pool termination |
| Coi `isShutdown()` là `isTerminated()` | Báo đã dừng dù tài nguyên còn | `awaitTermination()` và status |
| Block trong completion callback | Nghẽn pool, shutdown không kết thúc | Coordinator riêng, handler nhanh |
| Nuốt `failed(...)` | Request promise bị treo | Propagate outcome/cleanup |
| Reuse ByteBuffer sau cancel/timeouts | Race/bytes không chắc chắn | Discard hay chỉ tái sử dụng khi an toàn |
| Coi socket close là response đã nhận | Thiếu application ACK | Dùng protocol/transaction |
| Hai accepts outstanding | `AcceptPendingException` | Một accept một lúc |
| Hai writes pending trên một peer | `WritePendingException` | Outbound queue |
| Không xử lý `InterruptedException` | Khó dừng thread coordinator | Restore/propagate và cleanup |
| Không có path khi `awaitTermination` trả false | Leaking group/threads | Force fallback, báo đúng |
| Chỉ chạy unit test với `Thread.sleep` | Không quyết định | Chờ futures/conditions cụ thể |
| Nghĩ graceful shutdown luôn chạy khi process chết | Không đúng | Persistence/recovery riêng |

## 11. Bài tập có đáp án

**Câu 1.** Đóng listener có đóng mọi `AsynchronousSocketChannel` đã accept xong không?

**Đáp án:** Không. Accepted peers là các channels riêng, cần session manager sở hữu và close riêng.

**Câu 2.** Khi `accept()` đang pending và listener bị đóng, Future có thể cho kết quả gì?

**Đáp án:** Nếu chưa accept thành công, operation thất bại với `AsynchronousCloseException` (qua `ExecutionException.getCause()`). Nếu accept đã hoàn tất trước close, Future có thể trả peer; phải đóng hoặc đăng ký peer đó.

**Câu 3.** `group.shutdown()` có đóng tất cả channels không?

**Đáp án:** Không. Nó ngăn tạo channels mới gắn group; những channels đã có vẫn có thể hoạt động.

**Câu 4.** `group.shutdownNow()` có interrupt handler đang chạy không?

**Đáp án:** Không. API đóng channels; không cố interrupt threads đang thực thi CompletionHandler.

**Câu 5.** Khi nào group thực sự terminated?

**Đáp án:** Khi các channels gắn group đóng, handlers đang chạy xong và tài nguyên/pool được giải phóng; kiểm tra bằng `awaitTermination`/`isTerminated`.

**Câu 6.** Một client idle giữ connection không có request, server có nên chờ vô hạn để graceful không?

**Đáp án:** Không. Định nghĩa shutdown deadline, khi quá hạn close connection theo policy.

**Câu 7.** Nếu `group.awaitTermination(5,SECONDS)` trả false, được báo “mọi thread đã dừng” không?

**Đáp án:** Không. Group chưa terminated trong thời gian chờ; cần fallback và báo trạng thái thực.

**Câu 8.** Vì sao nhóm trong demo shutdown nhưng vẫn ghi/đọc được `ping`/`ok`?

**Đáp án:** Existing channels vẫn có thể I/O sau orderly `shutdown()`; shutdown group không đồng nghĩa close sockets.

**Câu 9.** Khi accept callback đến sau stopping, làm gì với peer?

**Đáp án:** Không bỏ rơi peer; nếu không được chấp nhận mới thì close ngay, hoặc đăng ký có đồng bộ để được drain.

**Câu 10.** `AtomicBoolean stopping` có đảm bảo không race với session registry không?

**Đáp án:** Không một mình. Cần đồng bộ quyết định accept/register với shutdown snapshot hoặc serialize lifecycle.

**Câu 11.** Vì sao không gọi `awaitTermination` trực tiếp bên trong CompletionHandler?

**Đáp án:** Handler giữ một thread pool completion; chờ lâu có thể ngăn các handlers khác chạy và trì hoãn termination.

**Câu 12.** `peer.shutdownOutput()` là close hoàn toàn hay half-close?

**Đáp án:** Half-close hướng gửi. Phía kia có thể đọc EOF sau bytes còn lại; socket chưa nhất thiết đóng hoàn toàn.

**Câu 13.** `Future.cancel(true)` có chắc mọi byte đã gửi được rollback không?

**Đáp án:** Không. I/O có thể đã tác động một phần, cancellation phụ thuộc provider; phải dựa vào protocol/idempotency.

**Câu 14.** Sau khi group terminated, executor riêng truyền qua `withThreadPool` thế nào?

**Đáp án:** Group sở hữu lifecycle và orderly-shutdown executor đó khi terminated. Tự đóng executor sớm khi group còn hoạt động là không được đặc tả.

**Câu 15.** Vì sao một response write thành công không chứng minh client đã xử lý giao dịch?

**Đáp án:** Write chỉ phản ánh I/O outcome; transaction/application ACK cần giao thức riêng.

**Câu 16.** Tại sao cần test pending accept bị đóng?

**Đáp án:** Để đảm bảo server giải quyết một operation còn chờ, không để handler/Future hoặc tài nguyên kẹt sau shutdown.

## 12. Checklist code review

- [ ] Có state RUNNING/QUIESCING/DRAINING/FORCING/TERMINATED, stop idempotent.
- [ ] Đặt stop flag trước khi ngừng accept; close listener đúng ownership.
- [ ] Callback accept có nhánh success/failure và giải quyết race với stopping.
- [ ] Accepted peers được đăng ký hoặc đóng, không có orphan socket.
- [ ] Ngừng business requests mới trên kết nối đang tồn tại.
- [ ] Có deadline, không đợi client idle vô hạn.
- [ ] Hoàn tất in-flight requests/outbound buffers hoặc báo forced failure.
- [ ] Session cleanup gỡ registry cả khi success và error.
- [ ] Không block lâu trong CompletionHandler.
- [ ] Không tạo hai accepts pending; không tạo hai read/write cùng chiều pending.
- [ ] Không chạm ByteBuffer khi I/O đang pending.
- [ ] Phân biệt close listener, close peer, shutdownOutput và group shutdown.
- [ ] Với group sở hữu riêng: shutdown orderly, awaitTermination và force fallback khi cần.
- [ ] Không dừng default group hoặc external executor đang được group sử dụng.
- [ ] Kiểm tra `isTerminated` trước khi báo đã giải phóng group.
- [ ] Xử lý các pending I/O outcomes khi channel close, không nuốt `failed`.
- [ ] Không coi I/O cancellation là rollback; cần idempotency/ACK cho nghiệp vụ.
- [ ] Test loopback, callback race, slow clients, half-close, pending accept, forced stop.
- [ ] Không phụ thuộc `Thread.sleep` để suy ra mọi task đã kết thúc.
- [ ] Dùng đúng Java NIO.2 API còn được hỗ trợ, tránh kiến thức lỗi thời/legacy.

## 13. Tài liệu chính thức

- [Java SE 21 — AsynchronousChannelGroup](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/AsynchronousChannelGroup.html): group/pool ownership, `shutdown`, `shutdownNow` và `awaitTermination`.
- [Java SE 21 — AsynchronousServerSocketChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/AsynchronousServerSocketChannel.html): `bind`, `accept`, pending accepts, close, group shutdown interactions.
- [Java SE 21 — AsynchronousSocketChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/AsynchronousSocketChannel.html): connected channels, `read/write`, `shutdownOutput`, pending limits.
- [Java SE 21 — AsynchronousChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/AsynchronousChannel.html): pending I/O khi close, cancellation và buffer.
- [Java SE 21 — CompletionHandler](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/CompletionHandler.html): `completed`/`failed` callback.
- [Java SE 21 — AsynchronousCloseException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/AsynchronousCloseException.html): I/O bị ảnh hưởng bởi close.
- [Java SE 21 — ShutdownChannelGroupException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/ShutdownChannelGroupException.html): tạo channel khi group đã shutdown.
- [Java SE 21 — ExecutorService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html): lifecycle của executor do ứng dụng sở hữu.
- [Java SE 21 — Future](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html): `get`, `cancel` và các outcomes.
- [Java SE 21 — ByteBuffer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html): `position`, `remaining`, `flip` và buffer state.

**Kết luận:** Shutdown của một asynchronous Java server cần được tổ chức theo thứ tự **ngừng accept → chặn request mới → drain/đóng accepted peers → shutdown nhóm sở hữu → đợi termination → force fallback khi quá hạn**. `listener.close()`, `group.shutdown()` và `group.shutdownNow()` có **hợp đồng khác nhau**, không thể hoán đổi tùy tiện. Có lifecycle state, deadline, registry và xử lý lỗi/callback giúp giảm rò rỉ tài nguyên và tránh tuyên bố sai rằng response đã đến nơi khi ứng dụng dừng.
