# AsynchronousChannelGroup, bộ thực thi và vòng đời nhóm trong Java NIO.2

## 1. Tại sao cần AsynchronousChannelGroup?

Khi sử dụng Java NIO.2, một lời gọi như `AsynchronousSocketChannel.read(buffer, attachment, handler)` **khởi tạo** hoạt động I/O, rồi kết quả được báo lại trong `CompletionHandler`. Câu hỏi phát sinh là: **thread nào sẽ nhận sự kiện và chạy callback, các kênh chia sẻ tài nguyên nào, ai dọn thread pool và khi nào hệ thống thực sự đã dừng?**

`java.nio.channels.AsynchronousChannelGroup` trả lời những câu hỏi đó ở cấp **nhóm kênh I/O bất đồng bộ**. Một group sở hữu/điều phối bộ tài nguyên triển khai và một **thread pool liên kết** để xử lý sự kiện hoàn tất, dispatch `CompletionHandler` và các công việc cần thiết cho asynchronous I/O. Các kênh được bind vào group tại thời điểm mở kênh; nhiều kênh có thể dùng chung group thay vì mỗi kết nối tự tạo một pool riêng.

**Bốn điều phải phân biệt:**

1. **Channel** (`AsynchronousServerSocketChannel`, `AsynchronousSocketChannel`): endpoint cụ thể và trạng thái kết nối/read/write của nó.
2. **Channel group** (`AsynchronousChannelGroup`): nhóm quản lý chia sẻ cơ chế completion và vòng đời thread pool.
3. **ExecutorService**: nơi thực thi tác vụ nội bộ và completion handlers của group; không mặc định là “thread riêng cho từng socket”.
4. **Ứng dụng/connection handler**: quyết định khi nào nhận ngừng nhận kết nối, cho request hoàn tất, đóng channel và yêu cầu group shutdown.

`shutdown()` của group **không có nghĩa** “đóng toàn bộ channel ngay bây giờ”. Nó **đánh dấu ngừng nhận kênh mới** và đợi các kênh/handler hoàn tất theo hợp đồng. `shutdownNow()` **mạnh hơn**: chủ động đóng những channel còn mở trong group, nhưng **không dừng cưỡng bức một completion handler đang chạy**. `awaitTermination()` mới là điểm chờ group đã kết thúc.

Bài này thuộc **Java Advance - networking → I/O bất đồng bộ**. Các ví dụ dùng Java 17+ và TCP loopback, không cần framework, database hoặc Internet; có mã đầy đủ cho cả shutdown bình thường và force shutdown.

## 2. Mục tiêu học tập

Sau bài này bạn có thể:

- Mô tả `AsynchronousChannelGroup` làm gì, kênh nào thuộc group và vì sao completion handler được chạy trên group thread.
- Tạo group qua `withFixedThreadPool`, `withCachedThreadPool` và `withThreadPool`; phân biệt kích thước cố định với executor tạo thread khi cần.
- Mở listener/client bằng overload `open(group)`; hiểu accepted channel kế thừa group của listener, còn `open()` không tham số sử dụng default group.
- Dùng `Future<T>` và `CompletionHandler<V,A>`; biết `get()` vẫn blocking thread gọi và callback không nên làm việc nặng.
- Phân biệt `shutdown()`, `shutdownNow()`, `isShutdown()`, `isTerminated()` và `awaitTermination(timeout, unit)`.
- Hiểu group **sở hữu lifecycle** của executor liên kết, không tự gọi `executor.shutdown()` từ bên ngoài khi group còn sử dụng pool.
- Ngăn race giữa accept đang chờ, I/O đang chạy, callback và shutdown, không rò channel/pool.
- Chạy hai chương trình Java để quan sát chính xác trạng thái group và executor.
- Thiết kế timeout, giới hạn tải và quan sát production mà không coi “async” là vô hạn hoặc không tốn thread.

## 3. Kiến trúc: nhiều channels cùng một group

~~~text
                 Application / server lifecycle
                              |
                     creates / owns
                              v
           +---------------------------------------+
           |    AsynchronousChannelGroup           |
           |  - event completion coordination      |
           |  - associated ExecutorService         |
           |  - pooled completion-handler threads  |
           +-----------+-------------+-------------+
                       |             |
             open(group)             open(group)
                       |             |
               +-------v------+   +--v----------------+
               | Async server |   | Async client     |
               | listen/accept|   | connect/read/write|
               +-------+------+   +-------------------+
                       |
                accept succeeds
                       |
                +------v----------------+
                | accepted async socket |
                | bound to SAME group   |
                | read/write callbacks  |
                +-----------------------+

Completion events -> group pool threads -> user CompletionHandler
Application coordinates channel close -> group.shutdown -> awaitTermination
~~~

Nhìn theo cấp tài nguyên:

| Tài nguyên | Ai tạo | Được dùng làm gì | Ai đóng/dừng |
| --- | --- | --- | --- |
| `AsynchronousChannelGroup` tùy chỉnh | Ứng dụng hoặc lifecycle manager | Chia sẻ executor và completion mechanics | Owner gọi `shutdown()`/`shutdownNow()`, `awaitTermination()` |
| `AsynchronousServerSocketChannel` | `open(group)` | Bind/accept TCP connections | Server owner đóng khi ngừng nhận client |
| `AsynchronousSocketChannel` client | `open(group)` | Kết nối và trao đổi stream byte | Client/connection owner đóng khi hoàn tất |
| `AsynchronousSocketChannel` accepted | Kết quả từ `listener.accept()` | Trao đổi byte với một client | Connection handler đóng; cùng group với listener |
| `ExecutorService` do group dùng | Có thể do ứng dụng cung cấp khi tạo group | I/O completion / chạy handler | **Group sở hữu**; shutdown group sẽ dẫn đến shutdown executor |
| `CompletionHandler` | Ứng dụng cung cấp | Xử lý `completed`/`failed` | Không phải `Closeable`; cần đảm bảo code hoàn tất nhanh/đúng |
| `ByteBuffer` | Ứng dụng | Mang byte của operation đang chạy | Tránh sửa/đọc trước khi operation hoàn tất |

**Điểm then chốt:** cùng một group **không** có nghĩa tất cả các socket dùng chung input stream, UDP port, TCP connection hoặc message queue nghiệp vụ. Mỗi channel giữ trạng thái kết nối riêng. Group chia sẻ **nền tảng điều phối completion và executor**.

### Không trộn với một số abstraction gần tên

- `Selector` dùng với `SelectableChannel` cho readiness-based **non-blocking I/O** và event loop do ứng dụng điều hành; nó **không phải** `AsynchronousChannelGroup`.
- `AsynchronousFileChannel` dùng `open(path, options, executor, attrs...)`, nhận **ExecutorService** có thể chỉ định trực tiếp; **không bind vào `AsynchronousChannelGroup`** như network asynchronous socket channel.
- `CompletableFuture` có executor mặc định/khả năng chỉ định executor riêng; nếu gọi `thenApplyAsync` mà không cung cấp executor, tác vụ không tự bảo đảm chạy trong thread pool của channel group.
- Thread pool nghiệp vụ dành cho parsing/DB/CPU có thể **tách** khỏi group executor để tránh callback I/O bị nghẽn.

## 4. Tạo group: ba factory và ý nghĩa của pool

`AsynchronousChannelGroup` không được tạo qua constructor public. Ba cách phổ biến:

### 4.1. `withFixedThreadPool(int nThreads, ThreadFactory factory)`

~~~java
ThreadFactory threads = task -> {
    Thread thread = new Thread(task, "aio-handler");
    return thread;
};
AsynchronousChannelGroup group =
        AsynchronousChannelGroup.withFixedThreadPool(2, threads);
~~~

Đây là **mảnh code trong method có `throws IOException`**; import `java.nio.channels.AsynchronousChannelGroup` và `java.util.concurrent.ThreadFactory`. `nThreads` phải lớn hơn 0. Đặt tên thread giúp chẩn đoán; ở code production nên đặt tên duy nhất theo chỉ số, đồng thời cân nhắc uncaught-exception handler, thread priority và daemon policy.

- Group dùng **fixed pool** với số pooled threads do cấu hình; không phải mỗi client một thread.
- Hai thread cho một demo có thể đủ xử lý vài network operations, **không** đồng nghĩa group chỉ được mở hai socket.
- Thread group có thể thực hiện callback và công việc hỗ trợ I/O, vì vậy callback chờ database vô thời hạn có thể làm nghẽn completions.
- Kích thước cần đo dựa trên tốc độ completion, thời gian handler, tải, provider/OS và CPU; không áp dụng công thức “số kết nối = số thread”.

### 4.2. `withCachedThreadPool(ExecutorService executor, int initialSize)`

~~~java
ExecutorService pool = Executors.newCachedThreadPool();
AsynchronousChannelGroup group =
        AsynchronousChannelGroup.withCachedThreadPool(pool, 0);
~~~

Mảnh code cần imports `java.util.concurrent.*`, `java.nio.channels.*` và xử lý `IOException`. Với cách này:

- Executor **nên** có khả năng tạo thêm thread khi cần (ví dụ cached thread pool) để đáp ứng tác vụ hoàn tất.
- `initialSize` là **gợi ý** ban đầu cho implementation, **không** có nghĩa tối đa 0 thread, không phải cấu hình hard limit, không phải số socket.
- Giá trị không âm hoặc âm mang ý nghĩa mặc định riêng của implementation theo API. Nếu muốn dễ hiểu, dùng `0` cho nhóm nhận đầu vào từ executor.
- Executor được đưa vào **chuyên dụng cho group**. Khi group kết thúc, executor sẽ được shutdown. **Đừng dùng lại executor đó cho nghiệp vụ độc lập.**

Số thread tăng linh hoạt có thể giúp chống tắc callback trong một số tình huống, nhưng tiêu thụ thread/memory nhiều hơn. Không nên coi cached executor là nguồn tài nguyên vô hạn an toàn; vẫn cần giới hạn client và tác vụ.

### 4.3. `withThreadPool(ExecutorService executor)`

~~~java
ExecutorService pool = Executors.newCachedThreadPool();
AsynchronousChannelGroup group =
        AsynchronousChannelGroup.withThreadPool(pool);
~~~

Khác `withCachedThreadPool(executor, initialSize)` ở hợp đồng chọn cách khai báo, và `initialSize` truyền cho provider được đặt 0 trong factory này. Với `withThreadPool`, JDK lưu ý executor cần **hỗ trợ direct handoff hoặc unbounded queue** và **không được chạy task ngay trên thread gọi `execute`**; provider có thể yêu cầu thêm điều kiện.

**Tránh `CallerRunsPolicy`** trên executor của group: một pool chạy callback ngay trong thread enqueue I/O có thể phá giả định về thread và gây deadlock. Executor có queue chặn/giới hạn kém thiết kế hoặc tự shutdown sẽ gây vấn đề khó chẩn đoán.

### Bảng lựa chọn factory

| Factory | Đầu vào | Trọng tâm | Rủi ro/cần chú ý |
| --- | --- | --- | --- |
| `withFixedThreadPool(n,factory)` | Số thread và ThreadFactory | Pool cố định, dễ quan sát | Callback blocking làm nghẽn công việc khác |
| `withCachedThreadPool(executor,initialSize)` | Executor tăng thread khi cần + hint | Co giãn theo yêu cầu implementation | Tăng thread, executor phải dành riêng cho group |
| `withThreadPool(executor)` | ExecutorService đủ điều kiện | Có sẵn executor quản lý theo policy mong muốn | Phải theo contract executor; tránh CallerRuns/queue không phù hợp |
| `open()` của async channel không truyền group | Không truyền group | Dùng **default group** của JVM | Ownership và tuning khác custom group |

Không có một factory “tốt nhất cho mọi hệ thống”. Khi muốn lifecycle độc lập, thread naming và cô lập loại workload, custom group thường hữu ích. Còn demo ngắn có thể dùng default group nếu không cần tự shutdown riêng.

## 5. Group mặc định so với group do ứng dụng sở hữu

~~~java
AsynchronousSocketChannel a = AsynchronousSocketChannel.open();
AsynchronousSocketChannel b = AsynchronousSocketChannel.open(group);
AsynchronousServerSocketChannel server =
        AsynchronousServerSocketChannel.open(group);
~~~

Đây là **mảnh code**, `group` phải đã được tạo; cần xử lý `IOException` và đóng các channel. Ngữ nghĩa:

- `open()` hoặc `open(null)` đặt channel vào **system-wide default group**.
- `open(group)` đặt channel vào **group cụ thể** được truyền vào; đó là lựa chọn để quản lý riêng thread pool và lifecycle.
- `AsynchronousServerSocketChannel.accept()` trả một `AsynchronousSocketChannel` **thuộc cùng group với listener**.
- Không thể “chuyển group” của một channel đang sống bằng một setter; group được chọn khi tạo channel.
- Nếu group đã shutdown, xây channel mới bound vào group sẽ ném `ShutdownChannelGroupException`.
- Group sử dụng `AsynchronousChannelProvider` tương ứng để tạo channel; nhóm và channel phải tương thích provider. Java API không cho phép gắn group của provider khác bằng thủ thuật ép kiểu.

Group mặc định được JVM duy trì, có executor tạo thread khi cần và cấu hình thông qua system properties:

- `java.nio.channels.DefaultThreadPool.threadFactory`: tên class `ThreadFactory` để JVM khởi tạo qua system class loader.
- `java.nio.channels.DefaultThreadPool.initialSize`: cấu hình initial size hint cho default group.

Nếu không cấu hình factory, tài liệu JDK mô tả các pooled threads của default group là **daemon threads**. Nhưng không nên suy rằng daemon thread bảo đảm mọi tài nguyên I/O được đóng sạch vào lúc JVM exit; cần thực hiện cleanup đúng. Khởi tạo default group do runtime quản lý không thay thế khả năng kiểm soát lifecycle của một custom group ở service.

**Không tự ý đặt system properties chỉ để sửa một handler chậm.** Trước hết tách hoạt động blocking/CPU-heavy khỏi callback, giới hạn tài nguyên và đo tải thực tế.

## 6. CompletionHandler và Future: ai thực thi, ai chờ?

Một asynchronous operation thường có hai phong cách.

### 6.1. Future-based

~~~java
Future<AsynchronousSocketChannel> pending = listener.accept();
AsynchronousSocketChannel accepted = pending.get(5, TimeUnit.SECONDS);
~~~

Đây là mảnh code trong method `throws Exception`. `accept()` **khởi tạo** chờ kết nối bất đồng bộ; nhưng `Future.get(...)` **block thread đang gọi** đến khi có kết quả, timeout hoặc lỗi. Nếu gọi `get()` trong một callback đang chiếm group thread, bạn có thể tự tạo deadlock khi pool nhỏ và operation cần chính những group threads đó để hoàn tất.

Dùng `Future` phù hợp cho demo và orchestration một số bước đơn giản; trong server nhiều client, completion handlers hoặc pipeline không-blocking thường phù hợp hơn.

### 6.2. Callback-based

~~~java
ByteBuffer buffer = ByteBuffer.allocate(1024);
client.read(buffer, null, new CompletionHandler<Integer, Void>() {
    @Override
    public void completed(Integer count, Void attachment) {
        // Phân biệt count=-1 (EOF), count=0, count>0.
        // Chỉ đọc buffer sau khi operation đã hoàn tất.
    }

    @Override
    public void failed(Throwable error, Void attachment) {
        // Xử lý lỗi, ghi log và đóng đúng channel.
    }
});
~~~

Đây là **mảnh code**, `client` đã kết nối và imports `java.nio.ByteBuffer`, `CompletionHandler`. Khi thao tác hoàn tất, callback thường được dispatch qua thread thuộc pool của group.

**JDK bảo đảm:** completion handler của operation trên channel thuộc group được gọi bởi **một pooled thread trong group**. Nếu operation hoàn tất ngay và code gọi từ group thread, implementation **có thể** chạy callback trực tiếp trên thread đó (inline), trừ một số operation có ràng buộc riêng như `accept`. Vì vậy:

- **Đừng dựa vào tên/thứ tự thread cụ thể** cho correctness; chỉ dựa vào hợp đồng pooled-thread.
- **Đừng block lâu trong callback** để đợi `Future.get()` của công việc khác trong cùng group, gọi DB lâu hoặc chờ lock của thread đang cần completion.
- Một callback có thể được kích hoạt rất nhanh, thậm chí inline trong hoàn cảnh cho phép. Cẩn thận đệ quy re-arm `read`/`write`, giới hạn stack và xử lý progress.
- Buffer truyền cho một asynchronous operation **không an toàn khi đồng thời sửa/đọc từ thread khác** trước khi operation hoàn tất; dùng ownership trên mỗi request.
- `completed`/`failed` của `CompletionHandler` không phải nơi sửa trực tiếp trạng thái shared mà không có synchronization. Sử dụng data structures thread-safe hoặc message passing.

### 6.3. Một lúc có thể có bao nhiêu operation?

| Channel | Giới hạn cốt lõi | Exception nếu vi phạm |
| --- | --- | --- |
| `AsynchronousServerSocketChannel` | Tối đa **một accept outstanding** trên một channel | `AcceptPendingException` |
| `AsynchronousSocketChannel` | Tối đa **một read outstanding** | `ReadPendingException` |
| `AsynchronousSocketChannel` | Tối đa **một write outstanding** | `WritePendingException` |
| `AsynchronousSocketChannel` | Có thể có một read **và** một write đồng thời | Không đồng nghĩa nhiều read cùng lúc |
| `ByteBuffer` dùng cho I/O | Một owner cho đến callback/`Future` hoàn tất | Race dữ liệu nếu reuse trước thời điểm |

Các giới hạn là **theo từng channel**, không phải một read cho cả group. Một group có thể quản lý nhiều channel song song. Nếu dùng custom pipeline, quản lý per-connection state và backpressure trước khi gọi operation mới.

### 6.4. Lỗi I/O không đồng nghĩa callback luôn chạy trên thread main

Các lỗi khi khởi tạo operation (ví dụ `AcceptPendingException` hoặc `ShutdownChannelGroupException` trong một số trạng thái) có thể được ném **ngay tại lời gọi**, không phải lúc callback. Lỗi xảy ra trong asynchronous operation thường được chuyển qua `failed(Throwable, attachment)` hoặc `Future.get()` với cause. Do đó phải có xử lý cả hai đường lỗi.

Không giữ lock trên main thread rồi chờ callback cần lock đó: ứng dụng có thể tạo deadlock dù I/O do hệ điều hành xử lý bất đồng bộ.

## 7. Vòng đời: những trạng thái phải phân biệt

~~~text
CREATED / RUNNING
   |
   | group.shutdown()
   v
SHUTDOWN (orderly)
   - từ chối kênh mới bound vào group
   - không tự đóng những kênh đang mở
   - handler đang chạy không bị interrupt
   |
   | tất cả group channels đóng
   | + các completion handlers đang chạy kết thúc
   | + tài nguyên group được giải phóng
   v
TERMINATED
   - isShutdown() == true
   - isTerminated() == true
   - executor liên kết đã terminated

Hoặc từ trạng thái đang chạy / shutdown:
   |
   | group.shutdownNow()
   v
FORCE SHUTDOWN REQUESTED
   - group đóng tất cả group channels còn mở
   - không cưỡng bức interrupt handler đang chạy
   |
   | handler đang chạy xong + release tài nguyên
   v
TERMINATED
~~~

### 7.1. `shutdown()`: ngừng có trật tự

`group.shutdown()` đánh dấu group đang shutdown. Sau đó:

- `AsynchronousSocketChannel.open(group)` hoặc `AsynchronousServerSocketChannel.open(group)` sẽ ném `ShutdownChannelGroupException`.
- **Các channel hiện có không tự bị đóng** chỉ vì gọi `shutdown()`. Ứng dụng vẫn chịu trách nhiệm đóng listener và các connected channels theo contract.
- Group chỉ terminated khi **mọi asynchronous channels của group được đóng**, **các completion handlers đang thực thi hoàn tất**, và **tài nguyên group đã giải phóng**.
- Group không cố stop/interrupt thread đang chạy callback.
- `isShutdown()` có thể là true trong khi `isTerminated()` là false rất lâu, thậm chí vô hạn nếu ứng dụng không đóng channel còn mở.

**Điểm dễ sai:** gọi `shutdown()` nhưng vẫn giữ `AsynchronousServerSocketChannel` đang mở với một `accept` chưa dứt; group có thể không terminated. Shutdown đúng phải điều phối listener và accepted channels chứ không chỉ đặt flag group.

### 7.2. `shutdownNow()`: đóng các group channels

`group.shutdownNow()` thực hiện shutdown và **gọi `close()` cho những channel đang mở thuộc group**. Nhờ vậy nó thường giúp giải phóng những pending asynchronous operations trên các channel, nhưng:

- Method có thể ném `IOException`.
- **Không** cưỡng bức dừng hoặc interrupt một completion handler đã vào code người dùng và đang block mãi.
- Không tự đóng database connections/files/queues **không thuộc group**.
- Phải chờ group terminate; trạng thái `isTerminated()` không được giả định chuyển sang true ngay sau khi gọi.
- Đang có callback cần ghi response, force close có thể làm hỏng giao dịch; dùng khi đã quá thời hạn drain hoặc cần hủy ngay.

### 7.3. `awaitTermination(long timeout, TimeUnit unit)`

~~~java
group.shutdown();
boolean terminated = group.awaitTermination(5, TimeUnit.SECONDS);
if (!terminated) {
    group.shutdownNow();
    terminated = group.awaitTermination(5, TimeUnit.SECONDS);
}
~~~

Đây là mảnh code nằm trong method `throws IOException, InterruptedException` hoặc xử lý hai ngoại lệ tương ứng. Trước `shutdown()`, ứng dụng cần **ngừng nhận thêm client và đóng/cho đóng group channels** để việc chờ có thể thành công. Nếu timeout hết mà `terminated` vẫn false, phải báo/điều tra handler bị kẹt; không được ghi log “đã dừng sạch” một cách sai lệch.

Hợp đồng `awaitTermination`: trả true nếu group đã terminated; false nếu hết thời gian chờ. Nếu thread đang chờ bị interrupt, method ném `InterruptedException`. Ứng dụng bắt exception thường cần khôi phục interrupt flag (`Thread.currentThread().interrupt()`), phối hợp cleanup và báo trạng thái phù hợp.

### 7.4. `isShutdown()` và `isTerminated()`

| Lúc quan sát | `isShutdown()` | `isTerminated()` |
| --- | --- | --- |
| Group vừa tạo và còn chạy | false | false |
| Vừa gọi `shutdown()`, còn ít nhất một channel mở | true | false |
| Các channels đã đóng, handlers kết thúc, resources đã release | true | true |
| `shutdownNow()` vừa trả về nhưng handler đang chạy lâu | true | Có thể false |
| Sau `awaitTermination(...) == true` | true | true |

**Không** viết health check theo công thức “`isShutdown()` = true => mọi kết nối đã đóng và thread đã giải phóng”. Chỉ `isTerminated()` xác nhận trạng thái terminated.

## 8. Ví dụ chạy được 1: group, completion handler và shutdown bình thường

Mã Java 17+ bên dưới:

1. Tạo một **custom group** với 2 thread đặt tên theo tiền tố `aio-group-`.
2. Mở **listener và client** với `open(group)`; accepted socket từ listener cũng thuộc group.
3. Dùng `Future` để nhận kết nối, `CompletionHandler` để nhận một thông điệp bốn byte `PING`.
4. Kiểm tra handler được chạy trên một thread thuộc group qua tên do ThreadFactory đặt.
5. Gọi `group.shutdown()` khi các channel vẫn đang mở: group shutdown nhưng **chưa terminated**.
6. Thử mở channel mới trên group và nhận `ShutdownChannelGroupException`.
7. Thoát scopes đóng accepted socket, client và listener; chờ `awaitTermination` xác nhận kết thúc.

Tạo file **`AsyncGroupLifecycleDemo.java`**:

~~~java
import java.io.EOFException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousChannelGroup;
import java.nio.channels.AsynchronousServerSocketChannel;
import java.nio.channels.AsynchronousSocketChannel;
import java.nio.channels.CompletionHandler;
import java.nio.channels.ShutdownChannelGroupException;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.atomic.AtomicInteger;

public class AsyncGroupLifecycleDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger counter = new AtomicInteger();
        ThreadFactory threads = task -> new Thread(
                task, "aio-group-" + counter.incrementAndGet());
        AsynchronousChannelGroup group =
                AsynchronousChannelGroup.withFixedThreadPool(2, threads);
        try {
            try (AsynchronousServerSocketChannel listener =
                         AsynchronousServerSocketChannel.open(group).bind(
                                 new InetSocketAddress(
                                         InetAddress.getLoopbackAddress(), 0));
                 AsynchronousSocketChannel client =
                         AsynchronousSocketChannel.open(group)) {
                Future<AsynchronousSocketChannel> pending = listener.accept();
                client.connect(listener.getLocalAddress())
                        .get(5, TimeUnit.SECONDS);

                try (AsynchronousSocketChannel accepted =
                             pending.get(5, TimeUnit.SECONDS)) {
                    ByteBuffer input = ByteBuffer.allocate(4);
                    CompletableFuture<String> message = new CompletableFuture<>();
                    CompletableFuture<Boolean> correctThread = new CompletableFuture<>();
                    accepted.read(input, null, new CompletionHandler<Integer, Void>() {
                        @Override public void completed(Integer n, Void unused) {
                            try {
                                if (n < 0) throw new EOFException("Missing request");
                                if (input.hasRemaining()) {
                                    accepted.read(input, null, this);
                                } else {
                                    input.flip();
                                    correctThread.complete(Thread.currentThread()
                                            .getName().startsWith("aio-group-"));
                                    message.complete(StandardCharsets.US_ASCII
                                            .decode(input).toString());
                                }
                            } catch (Throwable e) {
                                correctThread.completeExceptionally(e);
                                message.completeExceptionally(e);
                            }
                        }

                        @Override public void failed(Throwable error, Void unused) {
                            correctThread.completeExceptionally(error);
                            message.completeExceptionally(error);
                        }
                    });

                    ByteBuffer payload = StandardCharsets.US_ASCII.encode("PING");
                    while (payload.hasRemaining()) {
                        client.write(payload).get(5, TimeUnit.SECONDS);
                    }
                    System.out.println("Server received: " +
                            message.get(5, TimeUnit.SECONDS));
                    System.out.println("Handler used group thread: " +
                            correctThread.get(5, TimeUnit.SECONDS));

                    group.shutdown();
                    System.out.println("Group shutdown: " + group.isShutdown());
                    System.out.println("Terminated with channels open: " +
                            group.isTerminated());
                    try (AsynchronousSocketChannel ignored =
                                 AsynchronousSocketChannel.open(group)) {
                        System.out.println("New channel rejected: false");
                    } catch (ShutdownChannelGroupException expected) {
                        System.out.println("New channel rejected: true");
                    }
                }
            }
            System.out.println("Terminated after channel close: " +
                    group.awaitTermination(5, TimeUnit.SECONDS));
        } finally {
            if (!group.isTerminated()) {
                group.shutdownNow();
                group.awaitTermination(5, TimeUnit.SECONDS);
            }
        }
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac -encoding UTF-8 AsyncGroupLifecycleDemo.java
java AsyncGroupLifecycleDemo
~~~

**Stdout đã xác minh bằng OpenJDK 24 trên TCP loopback:**

~~~text
Server received: PING
Handler used group thread: true
Group shutdown: true
Terminated with channels open: false
New channel rejected: true
Terminated after channel close: true
~~~

**Diễn giải từng bước:**

- `InetAddress.getLoopbackAddress()` giữ kết nối cục bộ; bind port 0 để OS chọn cổng trống. Không cần server bên ngoài.
- `listener.accept()` trả `Future<AsynchronousSocketChannel>`. `Future.get` trên main đợi accepted channel; operation vốn đã được khởi tạo bất đồng bộ.
- `accepted.read(input, null, handler)` dùng callback. Callback có thể được gọi sau mỗi lần đọc một phần; nếu buffer chưa đầy, nó re-arm read. Với ví dụ 4 byte, xử lý này dễ hiểu.
- `client.write(payload).get` trong vòng lặp xử lý khả năng write một phần; đây là demo, production nên dùng async state machine nếu không muốn main block.
- `correctThread` kiểm tra prefix tên do `ThreadFactory` tạo. Đây là **instrumentation của ví dụ**, không nên dùng thread name làm cơ chế authorization hoặc correctness ở ứng dụng thực.
- `shutdown` đánh dấu group, không đóng channel. Vì listener và client vẫn mở, `isTerminated()` là false.
- `AsynchronousSocketChannel.open(group)` bị từ chối vì group đã shutdown.
- Sau các scopes `try-with-resources` đóng hết listener/client/accepted, group mới có thể terminated và `awaitTermination` trả true.

**Không áp dụng độ dài bốn byte như protocol production**: TCP là byte stream; ứng dụng thực cần framing, giới hạn payload và timeout/cancel, phân biệt EOF/partial read. `ByteBuffer` phải thuộc một operation tại một thời điểm. Code demo cố ý dùng `CompletableFuture` để main đợi callback; các handler không block `get()` của việc khác.

## 9. Ví dụ chạy được 2: shutdownNow đóng channel và dừng pool

Chương trình tiếp theo tạo `ExecutorService` bằng `Executors.newCachedThreadPool()`, giao nó cho `AsynchronousChannelGroup.withThreadPool(pool)` và mở listener trong group. Sau `group.shutdownNow()`, listener phải bị đóng và khi group terminated, executor cũng bị shutdown.

Tạo file **`AsyncGroupForceCloseDemo.java`**:

~~~java
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.channels.AsynchronousChannelGroup;
import java.nio.channels.AsynchronousServerSocketChannel;
import java.util.concurrent.Executors;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.TimeUnit;

public class AsyncGroupForceCloseDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newCachedThreadPool();
        AsynchronousChannelGroup group =
                AsynchronousChannelGroup.withThreadPool(pool);
        try {
            AsynchronousServerSocketChannel listener =
                    AsynchronousServerSocketChannel.open(group);
            try {
                listener.bind(new InetSocketAddress(
                        InetAddress.getLoopbackAddress(), 0));
                System.out.println("Listener open before: " + listener.isOpen());
                group.shutdownNow();
                System.out.println("Listener open after: " + listener.isOpen());
                System.out.println("Group terminated: " +
                        group.awaitTermination(5, TimeUnit.SECONDS));
                System.out.println("Executor shutdown: " + pool.isShutdown());
            } finally {
                listener.close();
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

Lệnh chạy:

~~~bash
javac -encoding UTF-8 AsyncGroupForceCloseDemo.java
java AsyncGroupForceCloseDemo
~~~

**Stdout đã xác minh:**

~~~text
Listener open before: true
Listener open after: false
Group terminated: true
Executor shutdown: true
~~~

Dòng `Listener open after: false` là hệ quả của `shutdownNow()` gọi close trên group channels. Dòng `Executor shutdown: true` thể hiện **group sở hữu vòng đời executor**. Không nên dùng `pool.shutdown()` trước rồi mong group vẫn tiếp tục thực hiện callback bình thường.

Ví dụ này **không có callback lâu**: group có thể terminated nhanh. Trong production có handler đang chờ DB, lock hoặc xử lý CPU lâu, `shutdownNow()` có thể đóng channels nhưng `awaitTermination` vẫn timeout cho đến khi handler hoàn tất.

## 10. Ai sở hữu executor, và vì sao không shutdown nó trực tiếp?

Với `withThreadPool(pool)` hoặc `withCachedThreadPool(pool, initialSize)`, tuy caller tạo `ExecutorService`, **group được giao quyền sở hữu lifecycle** của pool đó. Tài liệu JDK nhấn mạnh:

- Executor nên dành **riêng cho group**.
- Group terminated dẫn đến executor được shutdown có trật tự.
- Shutting down executor theo con đường khác trong lúc group dùng nó dẫn tới **hành vi không xác định (unspecified behavior)**.

Sai về ownership:

~~~java
ExecutorService executor = Executors.newCachedThreadPool();
AsynchronousChannelGroup group =
        AsynchronousChannelGroup.withThreadPool(executor);

executor.shutdown(); // SAI: group vẫn đang hoạt động, callback có thể bị lỗi.
~~~

Đây là **mảnh code**. Không nên trộn resource list kiểu `try (executor; group)`: Java 17 `ExecutorService` chưa phải `AutoCloseable` theo API Java 17 và `AsynchronousChannelGroup` cũng không phải `AutoCloseable`. Do vậy lifecycle cần lời gọi `shutdown/awaitTermination` **chủ động** trong `finally`/shutdown hook hoặc manager.

Thiết kế đúng:

~~~java
AsynchronousChannelGroup group =
        AsynchronousChannelGroup.withFixedThreadPool(4, factory);
try {
    runServer(group);
} finally {
    group.shutdown();     // Đã đóng các group channels trong runServer.
    if (!group.awaitTermination(5, TimeUnit.SECONDS)) {
        group.shutdownNow();
        if (!group.awaitTermination(5, TimeUnit.SECONDS)) {
            reportStuckHandlers();
        }
    }
}
~~~

Đây là **mảnh code phác thảo**, không standalone: `factory`, `runServer`, `reportStuckHandlers` do ứng dụng cung cấp; `shutdownNow()` có thể ném `IOException` và `awaitTermination()` có thể ném `InterruptedException`, vì vậy phương thức cần xử lý hoặc khai báo. `runServer` cần có đường dừng để cleanup bắt đầu; không đặt vòng accept vô hạn mà không cho caller ra tới `finally`.

**Nếu có application executor khác để xử lý nghiệp vụ**, đó là pool **khác** và có owner khác. Đóng theo thứ tự phù hợp: dừng nhận request, drain hoạt động nghiệp vụ, đóng channel, shutdown group, chờ group, rồi shutdown các pool ứng dụng riêng khi chúng không còn được dùng. Đừng dùng chung executor của group cho job scheduling hoặc tác vụ CPU dài chỉ vì thuận tiện.

## 11. Thiết kế shutdown server bất đồng bộ có kiểm soát

Một server thực tế có listener `AsynchronousServerSocketChannel`, nhiều accepted `AsynchronousSocketChannel` và có thể đang chạy nhiều `CompletionHandler`. Shutdown đúng cần state machine.

~~~text
RUNNING:
  listener accept loop đang hoạt động
  accepted channels đang đọc/ghi
  completion handlers có thể tạo operation mới

STOPPING_ACCEPT:
  set stopping=true (thread-safe / volatile / atomic)
  ngừng re-arm accept
  listener.close()
  callback accept failure thấy stopping -> không retry
  không tạo client channels mới trên group

DRAINING:
  chờ các phiên đã nhận kết thúc theo deadline
  mỗi handler đóng accepted channel của nó
  không mở thêm kênh hoặc tạo operation nghiệp vụ mới

GROUP_SHUTDOWN:
  sau khi ngừng mở group channels mới, gọi group.shutdown()
  chờ awaitTermination; còn channel mở sẽ khiến chưa terminated

FORCED_CLOSE (khi deadline hết):
  group.shutdownNow() -> đóng group channels còn mở
  hoàn thành hoặc xử lý handler đang chạy
  chờ awaitTermination thêm với deadline

TERMINATED:
  resource cleanup xong; associated executor đã terminated
  log tình trạng và metrics
~~~

**Có thể bắt đầu `group.shutdown()` trước khi mọi channel đóng**, vì shutdown chỉ cấm mở **channel mới**, không tự đóng channel cũ. Tuy nhiên, cần điều phối accept loop: theo hợp đồng `AsynchronousServerSocketChannel`, nếu group đang shutdown mà một kết nối được accept, operation có thể thất bại với cause `ShutdownChannelGroupException` và accepted socket được đóng. Vì vậy order trong ứng dụng nên giảm race: đặt stop flag và đóng listener/không re-arm accept trước, rồi shutdown group khi dừng nhận mới.

### 11.1. Quy tắc cho accept completion handler

Phác thảo logic (không phải code standalone):

~~~java
listener.accept(null, new CompletionHandler<AsynchronousSocketChannel, Void>() {
    @Override
    public void completed(AsynchronousSocketChannel client, Void ignored) {
        if (stopping.get()) {
            closeQuietly(client);
            return;
        }
        // Re-arm đúng một accept tiếp theo nếu listener còn mở.
        listener.accept(null, this);
        // Chuyển ownership của client cho handler; handler phải close nó.
        handOff(client);
    }

    @Override
    public void failed(Throwable error, Void ignored) {
        if (stopping.get()) {
            // Expected shutdown, không retry vô hạn.
            return;
        }
        reportAcceptFailure(error);
        // Áp dụng backoff/retry policy theo lỗi và trạng thái.
    }
});
~~~

Đoạn minh họa cần `listener`, `stopping` kiểu `AtomicBoolean`, helpers `closeQuietly`, `handOff` và `reportAcceptFailure`; phải xử lý `ClosedChannelException`/`ShutdownChannelGroupException` ném đồng bộ khi re-arm, và chuyển ownership thất bại. Trong code production cần ràng buộc concurrency và transaction của việc giao task. Không copy mảnh trên như một server hoàn chỉnh.

Những quy tắc:

- Một listener chỉ cho phép **một outstanding accept**. Gọi chồng sẽ ném `AcceptPendingException`.
- Re-arm accept sau khi operation trước hoàn thành mới nhận kết nối tiếp; code thường gọi re-arm sớm trong callback để không trì hoãn client mới, nhưng không được tạo race với stop.
- Nếu nhận client khi stop đã bắt đầu, **đóng client vừa accept** ngay, không giao thêm tác vụ.
- Callback `failed` do server chủ động close lúc stop **không nên retry vô hạn** và tạo log lỗi liên tục.
- Theo dõi accepted channels đang active để drain hoặc force-close khi cần.

### 11.2. Quản lý accepted channels và nhiệm vụ phụ

Nếu group có nhiều handler, dùng registry thread-safe cho các accepted channels, ví dụ `ConcurrentHashMap.newKeySet()`. Khi accept:

1. Nhận client và đăng ký vào registry trước khi xử lý.
2. Nếu hệ thống đã stop, không giao nhiệm vụ mới; đóng ngay.
3. Handler hoàn tất hoặc lỗi thì `close()` channel và xóa khỏi registry.
4. Khi hết thời gian drain, close các channel còn trong registry; đồng thời `shutdownNow()` là phương án force-close toàn group.
5. Hạn chế số connection, per-client pending read/write, buffer và tác vụ downstream.

**Race cần tránh:** nếu stop xảy ra giữa thời điểm kiểm tra `stopping` và đăng ký/giao handler, client mới có thể lọt vào sau stop. State/registry phải có phối hợp atomic hoặc quy tắc chấp nhận late arrival rồi đóng ngay. Chỉ một biến boolean mà không có policy retry/close thì chưa đủ.

## 12. Timeout, cancel và lỗi trên async channel

### 12.1. Timeout không được xử lý bằng cách chỉ shutdown group

Các overload `AsynchronousSocketChannel.read/write` cho phép chỉ định timeout. Với `read`:

~~~java
client.read(buffer, 3, TimeUnit.SECONDS, null,
        new CompletionHandler<Integer, Void>() {
    @Override public void completed(Integer n, Void ignored) {
        // Xử lý n >= 0 hoặc -1 EOF.
    }
    @Override public void failed(Throwable error, Void ignored) {
        // Có thể là InterruptedByTimeoutException hoặc lỗi I/O.
    }
});
~~~

Đây là **mảnh code**; `client`/`buffer` đã có. Theo tài liệu JDK, I/O timeout có thể làm trạng thái channel hoặc ByteBuffer trở nên không đáng tin theo implementation nếu không thể xác nhận byte đã chuyển hay chưa. Do đó **không mặc định retry trên cùng ByteBuffer/channel ngay sau timeout**. Thường nên đóng connection và tạo phiên mới theo protocol khi trạng thái frame không chắc chắn.

`Future.get(timeout, unit)` khác timeout của I/O: nó giới hạn **thời gian thread gọi chờ Future**, không tự bảo đảm kernel operation đã bị hủy khi caller hết thời gian. Nếu muốn stop operation, có chiến lược cancel/close channel và quản lý kết quả completion không còn cần thiết.

### 12.2. Exception cần phân loại

| Tình huống | Exception/kết quả điển hình | Ý nghĩa |
| --- | --- | --- |
| Mở channel bound vào group đã shutdown | `ShutdownChannelGroupException` | Không được gắn kênh mới vào group |
| Initiate accept trong khi accept khác pending | `AcceptPendingException` | Phải điều phối một accept outstanding |
| Initiate read khi read khác pending | `ReadPendingException` | Per-connection state machine sai |
| Initiate write khi write khác pending | `WritePendingException` | Gộp/queue write đúng cách |
| Connection không còn / close đang diễn ra | `AsynchronousCloseException`, `ClosedChannelException` hoặc lỗi I/O tương ứng | Phải coi lifecycle/close race là bình thường khi stop |
| Read/Write quá thời hạn | `InterruptedByTimeoutException` | Trạng thái buffer/connection có thể không chắc chắn |
| Future I/O bị lỗi | `ExecutionException` trong `Future.get()` | Dùng `getCause()` để hiểu lỗi gốc |
| Hết hạn chờ Future | `TimeoutException` | Caller ngừng chờ, operation không tự chắc chắn bị hủy |
| Main bị interrupt khi await | `InterruptedException` | Khôi phục interrupt và phối hợp cleanup |
| `shutdownNow()` cleanup bị lỗi | `IOException` | Báo lỗi dừng/tài nguyên chưa chắc đã giải phóng |

Không “nuốt” exception trong `CompletionHandler.failed`: nếu không close/tín hiệu lỗi, một channel có thể vẫn giữ tài nguyên và `awaitTermination()` không bao giờ thành công. Đóng đúng channel owner, hoàn tất `CompletableFuture`/promise nghiệp vụ bằng lỗi, và tránh log payload bí mật.

### 12.3. Cancellation và completion có thể đua nhau

Một operation có thể hoàn tất ngay trước khi caller cancel/close, hoặc fail khi group bị shutdown. Vì vậy:

- Thiết kế mỗi request chỉ **hoàn thành một lần** (atomic state hoặc `CompletableFuture.complete/completeExceptionally`).
- Tránh thao tác tiếp trên ByteBuffer khi operation còn pending.
- Nếu timeout nghiệp vụ, có thể close channel để cắt I/O, sau đó xử lý callback muộn và giải phóng buffers an toàn.
- Chỉ xác nhận channel/group đóng sau khi lifecycle thật sự hoàn tất; đừng dựa vào một callback có thể đến muộn để cập nhật trạng thái đã hủy theo cách làm sống lại request.

## 13. Hiệu năng: async không đồng nghĩa vô hạn thread/connection

Một nhóm có 2 hoặc 4 threads vẫn có thể điều phối rất nhiều channel vì phần I/O được triển khai bất đồng bộ. Nhưng **callback handler** thực thi Java code trên pooled threads nên dễ trở thành bottleneck.

Tình huống:

~~~text
Group fixed pool: 2 threads
  Thread A: handler đọc xong -> gọi DB blocking 10 s
  Thread B: handler đọc xong -> tính toán CPU 10 s

Các completion khác có thể phải chờ.
TCP senders/receivers vẫn có byte trong OS buffer nhưng application latency tăng.
~~~

Biện pháp:

- Giữ completion handlers **ngắn, không block**, chuyển việc CPU/DB sang **application executor** khác, để group threads quay lại dispatch I/O.
- Đặt giới hạn số active connections và số tasks đang pending; không tạo vô hạn `CompletableFuture` hoặc buffer per-request.
- Với một socket, chỉ một read và một write pending; dùng queue per-connection và backpressure.
- Chọn pool cố định hoặc cached dựa trên tải đo thật, không dựa vào tổng số socket đơn thuần.
- Tránh `CallerRunsPolicy`, tự shutdown pool được group sở hữu, callback ném exception bỏ lửng mà không close channel.
- Theo dõi metrics: active channels, pending accepts, pending read/write, completion latency, group thread count, executor queue, time-to-drain, timed-out operations, force closes.
- Khi cần kiểm soát deadline, xem cả callback, network I/O, application pool và downstream resources; riêng `awaitTermination()` không đặt timeout cho mọi hoạt động nghiệp vụ.

Một callback blocking chờ công việc khác trong **cùng fixed-size group** có nguy cơ deadlock; không sửa bằng cách cứ tăng số thread mãi, hãy sửa dependency graph để callback không đợi đồng bộ.

## 14. Default group và các vấn đề vận hành

Nếu viết:

~~~java
try (AsynchronousSocketChannel client = AsynchronousSocketChannel.open()) {
    client.connect(address).get(5, TimeUnit.SECONDS);
}
~~~

Đây là **mảnh code**, `address` phải đã xác định, method `throws Exception`. Nó sử dụng **default group của JVM**. Khi hệ thống có nhiều module/library dùng default group chung:

- Không thể dựa vào custom group để cô lập callback của một module vì module đó không sử dụng `open(customGroup)`.
- Default group thread pool có thể chịu ảnh hưởng bởi các thư viện khác và system properties JVM.
- Không nên cố dùng shutdown của một executor không được gắn với group hoặc thay thread factory khi runtime đang chạy với giả định mọi thứ sẽ đổi ngay.
- Nếu muốn test/metrics/lifecycle độc lập, tạo explicit group và truyền nó vào **tất cả** channel thuộc subsystem.

**Lưu ý thread naming:** handler demo dùng `aio-group-` chỉ để quan sát. Trong môi trường thật, thread có thể được provider tạo thêm cho nhiệm vụ nội bộ theo cách implementation-specific; không có bảo đảm “đúng một Java thread trên mỗi socket” hoặc “một event = một thread mới”.

### 14.1. Không nhầm AsynchronousFileChannel với group network

`AsynchronousFileChannel.open(path, Set<OpenOption>, ExecutorService, FileAttribute...)` chấp nhận pool trực tiếp. Đây **không** là overload `open(AsynchronousChannelGroup)`, nên không tự thuộc group network trong bài này.

Nếu dùng file channel và socket channel cùng ứng dụng, phân biệt ownership của executor file và executor group, đặc biệt khi ngừng server. Đừng dùng `group.shutdownNow()` với kỳ vọng nó đóng mọi `AsynchronousFileChannel` trong JVM.

### 14.2. Không tin rằng tất cả platform cho cùng số threads hoặc timing

NIO.2 dựa trên `AsynchronousChannelProvider` và hệ điều hành. Timing callback, số luồng hỗ trợ và chi tiết I/O completion có thể khác nhau giữa Windows/Linux/macOS. API bảo đảm một số hợp đồng — ví dụ callbacks từ group pooled threads, shutdown states — nhưng không bảo đảm thứ tự mọi event, thời gian response cụ thể hay provider có số native worker cố định.

Vì vậy test nên kiểm tra **điều kiện đồng bộ/hợp đồng**, không sleep 100 ms rồi suy ra resource đã đóng.

## 15. Ma trận test cho group và lifecycle

| Test | Thiết lập | Kỳ vọng |
| --- | --- | --- |
| Tạo custom group | `withFixedThreadPool(2, factory)` | Tạo group thành công; chưa shutdown |
| Channel gắn group | `AsynchronousSocketChannel.open(group)` | Channel thuộc group lựa chọn |
| Accepted channel | `listener.open(group)` rồi `accept()` | Accepted channel gắn group của listener |
| Callback thread | Tạo thread factory có prefix cố định | Callback chạy trên pooled thread theo contract |
| Graceful shutdown | Gọi `group.shutdown()` khi channels vẫn mở | `isShutdown()=true`, `isTerminated()=false` |
| Mở mới sau shutdown | `AsynchronousSocketChannel.open(group)` | `ShutdownChannelGroupException` |
| Chờ khi còn channel mở | `awaitTermination(shortTimeout)` | Có thể trả false |
| Đóng hết channels | Đóng listener/client/accepted và handler xong | `awaitTermination(...)` trở thành true |
| Force shutdown | `group.shutdownNow()` khi listener đang mở | Listener bị close |
| Executor ownership | `withThreadPool(pool)` rồi group terminate | `pool.isShutdown()=true` |
| Handler chậm | Callback block có kiểm soát | `shutdownNow` không cưỡng bức ngắt callback |
| Accept double pending | Gọi 2 accepts trên cùng listener | `AcceptPendingException` |
| Double read pending | Gọi 2 reads trên cùng connected channel | `ReadPendingException` |
| Double write pending | Gọi 2 writes trên cùng connected channel | `WritePendingException` |
| Fault during callback | Handler ném IOException hoặc lỗi runtime | Bắt/propagate/close đúng, không để leak |
| Shutdown race | Stop flag và accept callback chạy đồng thời | Không mở/giao client mới sau stop policy; late accepted closed |
| File channel khác group | Tạo `AsynchronousFileChannel` riêng | Không bị shutdown theo group network |

Đối với test có concurrency, đừng cố assert đúng tên thread hoặc thứ tự callback giữa hai connection. Dùng `CountDownLatch`/`CompletableFuture` để đồng bộ và test với deadline. Một phép thử chỉ pass trên laptop không đảm bảo không có race dưới tải.

## 16. Các lỗi thiết kế phổ biến

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Gọi `group.shutdown()` rồi cho rằng channels đóng | Group không terminate vì channel còn mở | Đóng/cho đóng channel theo ownership |
| Không gọi `awaitTermination()` | Không biết tài nguyên/pool đã giải phóng chưa | Chờ với deadline, kiểm tra boolean |
| Gọi `shutdownNow()` và mặc định callback đang block đã dừng | Callback Java đang chạy không bị interrupt bởi contract này | Thiết kế cancellation và cooperative deadline |
| Shutdown executor được đưa vào group trực tiếp | Provider có thể hành xử không xác định | Để group sở hữu executor lifecycle |
| Dùng chung executor group cho CPU task dài | Completion event nghẽn, latency tăng | App executor riêng, callback ngắn |
| Chọn `CallerRunsPolicy` cho group executor | Có thể chạy handler trên caller, vi phạm giả định API | Dùng executor phù hợp contract |
| Tạo một group/pool cho mỗi client | Rất nhiều threads/tài nguyên, khó shutdown | Một group được chia sẻ theo subsystem |
| Trộn `open()` và `open(group)` không có kế hoạch | Channel nằm trong default group, shutdown custom không ảnh hưởng | Truyền group xuyên suốt subsystem |
| Nhận connection xong nhưng không close | Group chờ channel mãi, leak | Try-with-resources/cleanup trong handler |
| Gọi `accept()` chồng khi accept đang pending | `AcceptPendingException` | Re-arm đúng một lần sau completion |
| Gọi `read()`/`write()` chồng trên cùng hướng | `ReadPendingException` / `WritePendingException` | Per-channel queue/state machine |
| Truy cập ByteBuffer trước khi I/O xong | Race/corrupt dữ liệu | Chỉ dùng buffer sau completion |
| Gọi `Future.get()` trong group callback | Starvation/deadlock khi pool nhỏ | Kết hợp callback, không block thread group |
| Tưởng `Future.get(timeout)` hủy I/O khi hết hạn | Operation có thể vẫn pending | Đóng/cancel channel theo policy |
| Tưởng timeout read không thay đổi buffer | JDK cho phép buffer state không xác định | Không tái sử dụng buffer mù sau timeout |
| `completed()` ném lỗi rồi không báo cho caller | Request treo, channel leak | catch, completeExceptionally, close đúng |
| Log cả lỗi shutdown như lỗi bất thường | Log noise, retry vô hạn | Phân biệt planned stop và failure |
| Chỉ nhìn `isShutdown()` để xác nhận stop thành công | Group có thể chưa terminated | Dùng `isTerminated()`/`awaitTermination` |
| Tăng thread pool mà không giới hạn connection | Queue, file descriptor, buffers vẫn tăng | Backpressure và resource budgets |

## 17. Bài tập có lời giải

### Bài 1 — Shutdown không dừng được

Server gọi `group.shutdown()`, `group.isShutdown()` trả true nhưng `awaitTermination(5, SECONDS)` trả false. Điều này có nhất thiết là bug JDK?

**Đáp án:** Không. Có thể còn listener, client/accepted channels hoặc completion handler đang chạy. `shutdown` không đóng các channel. Phải xác định owner, đóng/cho các channel kết thúc, chờ handlers và release resources, sau đó group mới terminated.

### Bài 2 — Chọn factory

Ứng dụng muốn tạo group có 4 threads xử lý completion, có thể đặt tên để đo latency. Nên dùng factory nào? Số 4 có nghĩa chỉ mở được 4 sockets không?

**Đáp án:** Dùng `AsynchronousChannelGroup.withFixedThreadPool(4, threadFactory)`. Bốn là số pooled threads theo cấu hình, không phải giới hạn socket count; hàng trăm sockets có thể gắn với cùng group nhưng vẫn cần resource/backpressure.

### Bài 3 — Executor bị shutdown ngoài ý muốn

Một library chia sẻ `ExecutorService pool` với ứng dụng nghiệp vụ rồi tạo `group = withThreadPool(pool)`. Khi ứng dụng gọi `pool.shutdown()` giữa chừng, chuyện gì sai?

**Đáp án:** Group dự kiến **sở hữu riêng** executor. Tắt trực tiếp bằng con đường khác khi group còn dùng dẫn đến behavior không được JDK quy định; có thể gián đoạn completion tasks. Cần executor chuyên dụng và gọi `group.shutdown()/awaitTermination()` qua lifecycle manager.

### Bài 4 — Tạo kênh mới sau shutdown

Sau `group.shutdown()`, lệnh `AsynchronousSocketChannel.open(group)` xảy ra chuyện gì?

**Đáp án:** Ném `ShutdownChannelGroupException`. Điều đó không chứng minh các channels cũ đã đóng; nó chỉ chứng minh group không nhận channel mới.

### Bài 5 — Callback blocking

Group fixed pool chỉ có hai threads. Hai `CompletionHandler.completed` đồng thời gọi `Future.get()` đợi một operation khác cũng cần group callbacks để hoàn tất. Có rủi ro gì?

**Đáp án:** Starvation/deadlock. Các handler chiếm hết pooled threads trong khi completion khác cần được xử lý. Không block group callbacks; dùng chaining/non-blocking logic hoặc offload CPU/DB sang executor nghiệp vụ khác.

### Bài 6 — So sánh shutdownNow

Ứng dụng gọi `group.shutdownNow()`. Có chắc `isTerminated()` lập tức true và callback đang chạy bị interrupt?

**Đáp án:** Không. `shutdownNow` đóng những group channels còn mở nhưng không cố dừng/interrupt handlers đang thực thi. Chờ `awaitTermination` và bảo đảm callback hợp tác kết thúc.

### Bài 7 — Nhầm default group

Server dùng `AsynchronousServerSocketChannel.open(group)`, nhưng client dùng `AsynchronousSocketChannel.open()`. Khi `group.shutdownNow()`, client có tự bị đóng vì cùng process JVM không?

**Đáp án:** Không. Client thuộc **default group**, không thuộc custom group của server. Group shutdown chỉ đóng channels của group đó. Client có thể bị ảnh hưởng theo cách bình thường từ việc server connection đóng, nhưng không do group trực tiếp sở hữu nó.

### Bài 8 — One read pending

Một client callback `read` chưa được gọi, handler khác lại gọi `read` trên cùng `AsynchronousSocketChannel`. Exception nào và vì sao?

**Đáp án:** `ReadPendingException`: per-channel chỉ cho phép một read outstanding. Dùng state machine để đợi callback trước rồi mới re-arm read.

### Bài 9 — File channel

`AsynchronousFileChannel.open(path, options, executor)` có tự thuộc custom `AsynchronousChannelGroup` của network không?

**Đáp án:** Không. File channel nhận executor trực tiếp, không bind với group network qua `open(group)`. Quản lý executor/file channel theo owner riêng.

### Bài 10 — Kiểm chứng lifecycle

Tại sao một test có `Thread.sleep(200)` rồi kiểm tra `group.isTerminated()` yếu hơn test dùng `awaitTermination(timeout)`?

**Đáp án:** Sleep đặt giả định về timing CPU/OS và dễ flaky. `awaitTermination` chờ điều kiện trạng thái thực với deadline, trả boolean kiểm chứng được. Test phải đóng channels/handlers theo contract trước khi chờ.

## 18. Checklist code review cho nhóm I/O bất đồng bộ

- [ ] Tôi đã xác định rõ subsystem nào sở hữu custom `AsynchronousChannelGroup`.
- [ ] Tôi chọn `withFixedThreadPool`/`withCachedThreadPool`/`withThreadPool` với lý do thực tế và executor phù hợp.
- [ ] Executor liên kết **dành riêng cho group**, không tự `shutdown` trước group.
- [ ] Listener, client và accepted async channels đều gắn vào **group chủ đích**.
- [ ] Accepted channel được handler sở hữu và close cả happy path lẫn error path.
- [ ] Callback không block dài, không đợi Future khác trong cùng pool bằng `get()`.
- [ ] Không đọc/ghi ByteBuffer khi asynchronous operation vẫn pending.
- [ ] Mỗi channel chỉ có tối đa một accept, một read, một write pending theo API.
- [ ] Có framing, giới hạn payload, deadline và ứng xử với EOF/timeout.
- [ ] Có stop flag/registry thread-safe để giảm race giữa accept và shutdown.
- [ ] Ngừng re-arm accept và đóng listener trước khi kết thúc nhóm.
- [ ] `shutdown()` chỉ đánh dấu ngừng; **đóng channels** mới giúp terminated.
- [ ] Có deadline cho `awaitTermination()`; kiểm tra false và xử lý shutdownNow đúng quyền.
- [ ] Đã xử lý `InterruptedException`/`IOException` khi shutdown, không ghi log thành công giả.
- [ ] Metrics tách group shutdown, group terminated, active channels và blocked handlers.
- [ ] Default group, FileChannel executor và application executor có lifecycle riêng.
- [ ] Có test bao phủ shutdown bình thường, force close, callback error và race.

## 19. Tài liệu chuẩn

- [Java SE 17 — AsynchronousChannelGroup](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousChannelGroup.html): factory methods, threading, default group, shutdown, awaitTermination và executor ownership.
- [Java SE 17 — AsynchronousServerSocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousServerSocketChannel.html): `open(group)`, `accept`, accepted channel cùng group, `AcceptPendingException`.
- [Java SE 17 — AsynchronousSocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousSocketChannel.html): `read/write`, `CompletionHandler`, `Future`, buffer state khi timeout, `ReadPendingException` và `WritePendingException`.
- [Java SE 17 — CompletionHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/CompletionHandler.html): `completed` và `failed`.
- [Java SE 17 — AsynchronousFileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousFileChannel.html): khác với network channel group, quản lý executor truyền vào khi open file.
- [Java SE 17 — ShutdownChannelGroupException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ShutdownChannelGroupException.html): phản ứng khi group không nhận kênh mới.
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): lifecycle executor; phân biệt với group shutdown.
- [Java SE 17 — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): `position`, `limit` và buffer safety.
- [Java SE 17 — java.nio.channels package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/package-summary.html): vị trí của asynchronous I/O trong NIO.2.

**Ghi nhớ:** `AsynchronousChannelGroup` là **cơ chế chia sẻ completion + executor** cho các async socket channels, **không** phải danh sách socket tự động đóng khi gọi `shutdown()`. Hãy tách ownership channel khỏi ownership group, giữ callback ngắn, để group quản lý executor liên kết, ngừng accept/đóng channels trước khi chờ `awaitTermination()`, và chỉ dùng `shutdownNow()` để force-close khi đã xác định hậu quả với các giao dịch còn chạy.
