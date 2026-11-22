# 9.5 Phân biệt tranh chấp monitor với việc chờ I/O hoặc chờ kết quả Future

Khi một dịch vụ Java chậm hoặc có vẻ “treo”, hàng chục request threads có thể cùng đứng im trong thread dump. Nhưng **đứng im không phải một nguyên nhân duy nhất**: có luồng đang **chờ lấy Java object monitor**, có luồng đang **đợi socket/disk/database**, và có luồng đang **chờ một kết quả `Future` hoặc `CompletableFuture`**. Ba loại chờ này có cách khắc phục khác nhau. Thay đổi kích thước thread pool để chữa một monitor bị giữ quá lâu có thể chỉ làm số thread bị chặn tăng; tăng timeout để chữa starvation trong executor đôi khi làm vấn đề nặng hơn.

Bài học tập trung vào **đọc bằng chứng từ JVM Java 17+**, đặc biệt `Thread.State`, stack frames, monitor/lock owner, dấu hiệu native I/O, `Future.get()`/`CompletableFuture.join()` và chuỗi phụ thuộc task. Mục tiêu là xây dựng một **quy trình phân loại**, không gán nhãn “deadlock” cho mọi thread `WAITING` và không kết luận “CPU đang nóng” chỉ vì trạng thái `RUNNABLE`.

**Sau bài này bạn cần làm được:**

- Xác định `BLOCKED (on object monitor)` có liên quan tới `synchronized`, tìm object monitor và thread đang nắm nó.
- Phân biệt `Object.wait()`, `LockSupport.park()` và `ReentrantLock` với tranh chấp Java monitor cổ điển.
- Nhận ra chờ I/O qua stack ở `Socket`, `InputStream.read`, `Selector.select`, `FileChannel` hoặc client thư viện; hiểu Java `RUNNABLE` không đồng nghĩa thread đang chiếm CPU.
- Nhận ra chờ kết quả bất đồng bộ qua `FutureTask.get`, `CompletableFuture.join/get`, `ForkJoinPool.managedBlock` và các frame `LockSupport.park`.
- Tìm ra **thread-pool starvation** và vòng phụ thuộc logic mà các deadlock detectors của JVM có thể không báo.
- Kết hợp nhiều thread dumps với lock ownership, pool metrics, downstream latency, JFR và các mốc UTC của **cùng JVM instance**.
- Đề xuất biện pháp khắc phục phù hợp cho từng trường hợp mà không tự tạo thêm tải hay lộ dữ liệu nhạy cảm.

## 1. Cùng triệu chứng “treo”, ba nhóm nguyên nhân

Sơ đồ đặt câu hỏi đầu tiên:

```text
                  Request không tiến triển
                           │
                   Chụp thread dump
                           │
                 Thread đang ở đâu?
       ┌───────────────────┼───────────────────┐
       ▼                   ▼                   ▼
  Java monitor         I/O boundary       Future / async wait
  BLOCKED?             socket/file?        get() / join()?
       │                   │                   │
  Lock identity         Remote endpoint     Future completion
  Lock owner            Timeout/deadline    Executor / producer
  Holder stack          Pool connection     Dependency graph
       │                   │                   │
  Critical section      Downstream/I/O       Queue starvation,
  và thời gian giữ      latency/limit        deadlock logic/timeout
       └───────────────────┼───────────────────┘
                           ▼
               Đối chiếu nhiều snapshots,
                metrics, logs, JFR/traces
```

Cả ba có thể xảy ra đồng thời. Ví dụ **thread A giữ monitor, rồi chờ `Future.get()`**, trong khi task hoàn tất Future cần chính monitor đó: trong dump A có thể là `WAITING (parking)` tại `FutureTask.get`, còn B là `BLOCKED` chờ monitor. Nếu chỉ nhìn trạng thái của A hoặc B riêng lẻ, bạn sẽ bỏ qua vòng phụ thuộc.

Một nguyên tắc quan trọng: **Java `Thread.State` chỉ là trạng thái của JVM tại thời điểm lấy mẫu**, không phải chuẩn đoán cuối cùng về resource gây chậm. Stack frames cho biết thread đang ở đường xử lý nào; lock-owner information, metrics và chuỗi chờ giúp hiểu *vì sao*.

## 2. Sáu trạng thái Java và câu hỏi chẩn đoán

Java 17 có sáu `Thread.State`:

| State | Ý nghĩa ở Java VM | Gợi ý điều tra |
| --- | --- | --- |
| `NEW` | `Thread` object chưa `start()` | Không phải một live worker đang xử lý request |
| `RUNNABLE` | Thread đang chạy/khả dụng cho thực thi theo VM | Có thể tính toán CPU hoặc đang chờ OS I/O; phải đọc stack |
| `BLOCKED` | Chờ lấy lại Java object monitor để vào `synchronized` hoặc tái vào sau `wait` | Tìm `- waiting to lock` và lock owner |
| `WAITING` | Đợi không có timeout cho hành động của thread khác | `Object.wait()`, `LockSupport.park()`, `Thread.join()`; đọc caller |
| `TIMED_WAITING` | Đợi có timeout/độ dài hữu hạn | `sleep`, timed `wait/join`, `parkNanos`, nhiều timed waits |
| `TERMINATED` | Thread đã kết thúc | Thường không nằm trong live thread dump của JVM |

**Đừng ánh xạ một-một sang Linux states `R/S/D`.** Một Java thread `RUNNABLE` có thể nằm trong native socket read và OS thread đang sleeping. Ngược lại, Java `WAITING` có thể là pool idle hoàn toàn bình thường. <u>State + top frames + caller frames + lock data + thời gian mới là bằng chứng.</u>

### 2.1. Một ma trận nhận diện nhanh

| Dấu hiệu trong dump | Khả năng ban đầu | Bằng chứng còn thiếu |
| --- | --- | --- |
| `BLOCKED (on object monitor)`, `- waiting to lock <id>` | Monitor contention | Thread nào đang `- locked <id>`, giữ bao lâu? |
| `WAITING (on object monitor)` tại `Object.wait` | Đợi notify/điều kiện | Ai notify? Predicate/condition đã thay đổi chưa? |
| `WAITING (parking)` tại `AbstractQueuedSynchronizer` | Lock/condition/semaphore/future/pool queue | Caller thực là `lock`, `await` hay `getTask`? |
| `RUNNABLE` với `SocketDispatcher.read0` / `SocketInputStream.socketRead0` | Chờ network read hoặc native work | Endpoint, deadline, byte count, OS socket state |
| `RUNNABLE` với `EPoll.wait` / `Selector.select` | Event loop chờ I/O readiness | Event-loop progress, backlog, select timeout |
| `WAITING` tại `FutureTask.awaitDone` / `CompletableFuture.waitingGet` | Chờ result bất đồng bộ | Producer/task nằm ở executor nào, có chạy không? |
| `TIMED_WAITING` tại timed `Future.get` | Có chờ tối đa timeout | Timeout còn lại, deadline toàn request, producer progress |
| Nhiều request threads cùng `join`, pool active=max và queue tăng | Executor starvation/async bottleneck | Dependency graph: task hoàn tất nằm ở chính pool bị chiếm không? |

Các frame cụ thể có thể đổi theo JDK, thư viện I/O và runtime implementation. Không viết parser khẳng định mọi JDK 17 bắt buộc in đúng tên `SocketDispatcher.read0` hoặc `CompletableFuture.waitingGet`.

## 3. Monitor contention: dấu vết của `synchronized`

### 3.1. Object monitor là gì?

Mỗi Java object có thể được dùng làm monitor cho `synchronized (obj)` hoặc một method `synchronized`. Tại một thời điểm, chỉ một thread sở hữu monitor đó để thực thi critical section; thread khác muốn vào phải chờ. Trong Java thread dump, **thread đang chờ để vào monitor** thường có state:

```text
java.lang.Thread.State: BLOCKED (on object monitor)
    at com.example.InventoryCache.lookup(InventoryCache.java:91)
    - waiting to lock <0x0000000700a01000> (a java.lang.Object)
    at com.example.OrderService.reserve(OrderService.java:54)
```

Đây là **mẫu HotSpot tổng hợp**. Trường `<0x...>` là identity của object monitor trong dump phù hợp, **không phải thread ID**, cũng không phải địa chỉ native `nid`. Tên file/line và cách in có thể khác giữa bản JDK.

Điều có thể kết luận: tại snapshot, thread chưa lấy được một monitor để tiếp tục. Điều **chưa** thể kết luận: monitor sẽ bị giữ mãi mãi, đây là deadlock hay chỉ contention thoáng qua vài micro giây. Cần tìm thread sở hữu monitor đó.

### 3.2. Tìm chủ sở hữu cùng lock

Cùng dump có thể có thread khác:

```text
"cache-refresh" #52 ...
   java.lang.Thread.State: TIMED_WAITING (sleeping)
    at java.base/java.lang.Thread.sleep(Native Method)
    at com.example.InventoryCache.refresh(InventoryCache.java:120)
    - locked <0x0000000700a01000> (a java.lang.Object)
```

Nếu identity `<0x0000000700a01000>` trùng, thread `cache-refresh` có thể đang giữ monitor mà `OrderService.reserve` chờ. Điểm rất dễ sai: **`Thread.sleep` không nhả monitor** đang giữ. Vì vậy thread đang ngủ vẫn có thể chặn nhiều request threads.

Đường điều tra hợp lý:

1. Xác nhận object monitor identity giống nhau **trong cùng dump**.
2. Đọc owner stack để tìm critical section của `synchronized`.
3. Đọc source quanh frame owner: có sleep, synchronous network call, database query, giữ lock trong loop hay giữ lock trước khi `Future.get`?
4. Lấy thêm snapshot khi triệu chứng còn xuất hiện, có giới hạn tác động.
5. Đối chiếu blocked time/blocked count, request latency và lock contention events.
6. Sửa **thời gian nắm lock hoặc cấu trúc ownership**, không chỉ tăng số thread đang đợi.

Monitor identity có thể khác qua đời process hoặc giữa hai dump; không dùng nó như khóa toàn cục của cluster. Java lock owner/monitor frames còn phụ thuộc mức độ chi tiết của thread dump và tối ưu hóa JVM.

### 3.3. `BLOCKED` không phải mọi loại tranh chấp khóa

`ReentrantLock.lock()` thường dựa trên `AbstractQueuedSynchronizer` và `LockSupport.park`. Thread chờ `ReentrantLock` có thể là **WAITING (parking)**, không phải `BLOCKED`. `Condition.await`, `Semaphore.acquire`, `CountDownLatch.await`, `FutureTask.get` cũng có thể hiện WAITING hoặc TIMED_WAITING. Vì vậy:

- `BLOCKED` là dấu hiệu khá cụ thể của **Java monitor enter**.
- **Không có `BLOCKED`** không loại trừ contention ở `java.util.concurrent`.
- `WAITING (parking)` tự nó **không** khẳng định loại cơ chế chờ; phải đọc frames bên dưới `Unsafe.park`/`LockSupport.park`.
- Một thread có state WAITING vẫn có thể **đang giữ monitor hoặc lock khác**, gây chặn thread khác.

### 3.4. `Object.wait` là trường hợp khác với chờ vào monitor

`Object.wait()` chỉ được gọi khi thread sở hữu monitor của object đó. Khi vào wait, thread **nhả monitor trên object được wait**, chờ notify/notifyAll, interrupt hoặc điều kiện được đánh thức; sau đó cần reacquire monitor trước khi trở lại Java code bên trong critical section. Nó **không tự nhả mọi monitor khác** mà thread đang nắm.

Một mẫu:

```text
"producer" ...
   java.lang.Thread.State: WAITING (on object monitor)
    at java.base/java.lang.Object.wait(Native Method)
    at com.example.Queue.take(Queue.java:67)
    - waiting on <0x0000000700a02000> (a java.lang.Object)
```

Đây không phải bằng chứng thread đang **BLOCKED để vào** monitor. Nó đang chờ **điều kiện/notify**. Nếu được notify nhưng chưa reacquire lock, thread có thể chuyển sang BLOCKED. Phân tích phải tách “chờ được thông báo” và “chờ được vào monitor”.

**Thực hành an toàn với wait/notify:** kiểm tra predicate trong vòng `while`, không dùng `if`, vì spurious wakeups có thể xảy ra; tránh notify sai object hoặc bỏ lỡ điều kiện khi thiết kế concurrency. Khi thật sự cần concurrency primitives bậc cao, thường ưu tiên `BlockingQueue`/`Condition`/`CompletableFuture` đúng ngữ nghĩa hơn tự xây một protocol `wait/notify` phức tạp.

## 4. Monitor contention có thể biến thành starvation thế nào?

Một code path có dạng:

```java
// Snippet minh họa trong method, không phải chương trình độc lập.
synchronized (cacheLock) {
    refreshFromRemoteService(); // I/O có thể mất vài giây.
    updateSharedCache();
}
```

Tất cả request threads cần `cacheLock` phải xếp hàng trong khi owner **đang đợi I/O**. Trong dump cùng lúc:

- Owner có thể `RUNNABLE` ở socket native read.
- Nhiều request workers khác là `BLOCKED` chờ một monitor ID.
- CPU của JVM có thể thấp; p99 vẫn cao.
- Nguyên nhân **trực tiếp** của waiter là monitor contention; nguyên nhân **kéo dài thời gian nắm monitor** lại là I/O chậm.

Không nên phân loại toàn incident là “monitor” *hoặc* “network” khi thực tế là **cả hai tạo thành chuỗi nguyên nhân**. Cách sửa thường gồm chuyển I/O ra ngoài critical section hoặc dùng snapshot/immutable state, cùng timeout/circuit breaker và thiết kế đồng bộ thích hợp.

## 5. I/O wait: state `RUNNABLE` có thể gây hiểu lầm

### 5.1. Blocking socket read

Một mẫu HotSpot/JDK 17 phổ biến khi request gọi một dependency:

```text
"http-worker-17" #70 ...
   java.lang.Thread.State: RUNNABLE
    at java.base/sun.nio.ch.SocketDispatcher.read0(Native Method)
    at java.base/sun.nio.ch.SocketDispatcher.read(SocketDispatcher.java:...)
    at java.base/sun.nio.ch.NioSocketImpl.tryRead(NioSocketImpl.java:...)
    at java.base/java.net.Socket$SocketInputStream.read(Socket.java:...)
    at com.example.http.Client.fetch(Client.java:84)
    at com.example.web.OrderController.submit(OrderController.java:37)
```

Đây là **ví dụ theo kiểu stack**: số dòng/frames thay đổi theo JDK, driver HTTP/TLS, thư viện và cơ chế socket. Trên một implementation khác có thể thấy `SocketInputStream.socketRead0` hoặc frame NIO/Netty khác.

**`RUNNABLE` không khẳng định CPU cao.** Java VM có thể phân loại thread đang trong native I/O method là RUNNABLE trong khi OS cho nó ngủ đợi dữ liệu. Cần xem OS thread CPU time/TID, socket state, network timeout, latency phụ thuộc, bytes received và số connections để biết có thật sự bận CPU hay không.

### 5.2. Selector/event loop chờ I/O

Một worker reactor/Netty/Java NIO có thể hiển thị:

```text
java.lang.Thread.State: RUNNABLE
    at java.base/sun.nio.ch.EPoll.wait(Native Method)
    at java.base/sun.nio.ch.EPollSelectorImpl.doSelect(EPollSelectorImpl.java:...)
    at java.base/java.nio.channels.Selector.select(Selector.java:...)
```

Đây có thể là **event loop idle đúng thiết kế**, không phải “loop vô hạn ngốn CPU”. Cần kiểm tra:

- epoll/select có đang thực sự chặn đợi sự kiện không?
- CPU time của native TID có tăng mạnh hay gần như không tăng?
- Event loop backlog, queue size, completed tasks và thời gian dispatch?
- Có busy-spin (select liên tục trả tức thời), callback tốn CPU hoặc handler I/O giữ event loop quá lâu không?
- Latency được đo từ client có thể do downstream hoặc queue trước event loop?

Một framework bất đồng bộ cũng có thể chuyển I/O wait sang **task/callback hoặc future**: thread event-loop lúc đó đang chờ readiness còn request thread khác chờ result. Không gán một state cố định cho “I/O wait” trên mọi thư viện.

### 5.3. File/disk I/O và native calls

Các frame như `FileInputStream.readBytes`, `FileChannelImpl.read`, filesystem provider, database driver hoặc JNI native method có thể cho biết thread ở đường I/O. Một Linux thread có thể ở `D` uninterruptible sleep, nhưng Java state vẫn không nhất thiết hiện thành tên `IO_WAITING` — Java `Thread.State` **không có enum này**.

Để điều tra, đối chiếu:

- I/O latency/IOPS/thông tin disk queue;
- connection pool wait vs socket read vs TLS handshake;
- SQL/query latency từ database metrics, tracing, pool active/pending;
- OS thread state, `/proc` hoặc tools read-only khi có quyền;
- network latency/retransmissions, DNS, timeouts/deadlines;
- JVM heap/GC/safepoint nếu thời gian bất thường trùng pause.

**Đừng kết luận backend chậm** chỉ vì thấy frame JDBC: nó có thể đang chờ connection pool, transaction lock, network read, driver synchronization hoặc application-level backpressure. Đọc đủ caller frames và dependency metrics.

### 5.4. Timeout của I/O không giống timeout của Future

`Socket.setSoTimeout(...)` giới hạn blocking read trên socket theo ngữ nghĩa của API, không phải deadline tổng của một business transaction. `HttpClient`, JDBC driver, pool acquisition và RPC framework có nhiều loại timeout riêng: connection, handshake, read, request/call, queue/pool acquisition.

Một request có thể có ba chặng:

```text
Chờ pool connection (500 ms)
→ connect (300 ms)
→ read response (3 s)
→ retry (2 lần)
→ tổng latency vượt SLA
```

Một thread dump chỉ thấy đúng **chặng hiện tại**. Bài toán chẩn đoán cần tính tổng deadline, retry budget và chuỗi dependencies, không chỉ cấu hình socket timeout của một call.

### 5.5. Bằng chứng phân biệt I/O wait với CPU hotspot

| Điều quan sát | Nghi I/O wait | Nghi CPU-heavy |
| --- | --- | --- |
| Java state | Có thể RUNNABLE/native hoặc WAITING tùy framework | Thường RUNNABLE ở application method |
| Stack | `Socket.read`, `FileChannel.read`, `Selector.select`, driver call | Java loops, transforms, serialization, crypto, matching |
| CPU time cùng OS TID qua 2 mẫu | Tăng ít khi thực sự đang blocked | Tăng nhanh tương ứng khoảng đo |
| Dependency latency | Có thể tăng | Có thể bình thường |
| JFR | SocketRead/FileRead duration hoặc thread park có ý nghĩa | Execution samples tập trung vào code |
| Biện pháp đầu tiên | Xác minh endpoint, timeout, queue, I/O latency | Profiling CPU và tối ưu đường tính |

Có thể cùng có CPU work và I/O trong một request. Một lần đọc `Thread.State` không đủ cho định lượng.

## 6. Future wait: chờ kết quả của một công việc khác

### 6.1. `Future.get()` chờ điều gì?

`Future<V>` đại diện kết quả tính toán bất đồng bộ. Với `Future.get()` không timeout, caller **chờ khi cần cho tới khi task hoàn tất**, sau đó nhận result hoặc exception/cancellation tương ứng. `get(timeout,unit)` chờ tối đa khoảng thời gian chỉ định rồi có thể ném `TimeoutException`.

Một ví dụ API (snippet trong method):

```java
Future<String> result = executor.submit(() -> remoteLookup());

try {
    String value = result.get(2, TimeUnit.SECONDS);
    use(value);
} catch (TimeoutException ex) {
    // Xử lý deadline/timeout ở tầng ứng dụng.
}
```

`executor`, `remoteLookup`, `use` giả định đã tồn tại; đây **không phải chương trình biên dịch độc lập**. `get` còn có thể ném `InterruptedException` và `ExecutionException`; ví dụ lược bớt xử lý chúng để nhấn mạnh timeout. Nếu dùng code thực, phải xử lý ba trường hợp chính xác, khôi phục interrupt status khi phù hợp và giải quyết cancellation theo policy.

### 6.2. Stack thường gặp khi chờ `FutureTask.get`

Một mẫu HotSpot:

```text
"request-worker-8" #87 ...
    java.lang.Thread.State: WAITING (parking)
     at java.base/jdk.internal.misc.Unsafe.park(Native Method)
     at java.base/java.util.concurrent.locks.LockSupport.park(LockSupport.java:...)
     at java.base/java.util.concurrent.FutureTask.awaitDone(FutureTask.java:...)
     at java.base/java.util.concurrent.FutureTask.get(FutureTask.java:...)
     at com.example.OrderService.create(OrderService.java:109)
```

Phân tích từ dưới lên về **nguyên nhân chờ**: business method `OrderService.create` gọi `FutureTask.get`, nội bộ FutureTask dùng `awaitDone`/`park` để đợi task hoàn tất. Thread có thể là WAITING mặc dù **không hề tranh chấp Java object monitor**.

Trong log/metrics cần tìm:

- Future được sinh ra ở đâu, ai submit?
- Executor nào chạy producer?
- Task đang ở trạng thái pending/running/completed/failed/cancelled?
- Queue executor, active threads, completed task count, rejected tasks?
- Task chạy có đang chờ I/O/monitor/another Future?
- Caller có đang giữ lock trước khi `get` hay không?

Không có tên “producerThread” mặc định nằm trong Future object. Thread dump của consumer cho biết **điểm chờ**, không đảm bảo chỉ ra thread producer nếu chưa theo trace/task ID hoặc scheduler metadata.

### 6.3. CompletableFuture `join`/`get`

`CompletableFuture<T>` triển khai `Future<T>` và `CompletionStage<T>`. Các frame có thể gồm `CompletableFuture.waitingGet`, `CompletableFuture$Signaller.block`, `ForkJoinPool.managedBlock` và `LockSupport.park`. Tên và chi tiết stack khác theo JVM, vậy phải tìm **chuỗi gọi `join` hoặc `get` ở caller frames**.

Khác nhau đáng nhớ:

| API | Timeout | Exception chính | Dấu hiệu chờ |
| --- | --- | --- | --- |
| `Future.get()` | Không | `InterruptedException`, `ExecutionException`, `CancellationException` | Thường WAITING nếu chưa done |
| `Future.get(t, unit)` | Có | Thêm `TimeoutException` | Có thể TIMED_WAITING |
| `CompletableFuture.join()` | Không | `CompletionException` (unchecked) khi exceptional, `CancellationException` | Thường WAITING/parking nếu chưa done |
| `CompletableFuture.get()` | Không | `InterruptedException`, `ExecutionException` | Có thể WAITING |
| `CompletableFuture.orTimeout(t,unit)` | Thay đổi trạng thái tương lai khi hết hạn | Future hoàn tất exceptionally với `TimeoutException` | **Không tự đảm bảo** công việc nền được hủy |
| `CompletableFuture.completeOnTimeout(value,t,unit)` | Cấp fallback value khi timeout | Phụ thuộc completion/cancellation cạnh tranh | Không tự chứng minh work đã dừng |

`Future.isDone() == true` có nghĩa computation đã **hoàn tất theo trạng thái của Future**, có thể thành công, thất bại hoặc cancelled; **không** đồng nghĩa thành công. `join()` không khai báo `InterruptedException`, vì vậy không xử lý interrupt giống hệt `get()`; hiểu chính sách interrupt/cancellation cụ thể của API và executor.

### 6.4. `WAITING` không chứng minh Future chưa bao giờ hoàn tất

Thread dump là ảnh chụp tại một thời điểm. Future có thể hoàn tất ngay sau đó; consumer có thể chưa được scheduler chạy tiếp. Ngay cả khi đã timeout ở tầng HTTP client, một task đã submit vẫn có thể tiếp tục chạy nếu cancellation không được triển khai đúng.

Nếu nhiều request threads cùng chờ `get`, trước khi kết luận “Future không chạy”, kiểm tra pool size/queue, submit failures, callback executor, deadlock cycle, native I/O của producer và timing.

## 7. Thread-pool starvation: không có monitor deadlock vẫn treo

### 7.1. Một worker tự chờ task chưa được chạy

Giả sử executor có **một worker**. Task A đang chạy trong worker, submit task B vào **cùng executor**, rồi gọi `B.get()`. B nằm trong queue nhưng không thể chạy vì worker duy nhất đang bị A chiếm và A chờ B. Đây là **thread-pool starvation** hoặc vòng phụ thuộc do scheduling, không cần hai monitor chờ nhau.

```text
SingleThreadExecutor (1 worker)
                │
                ▼
           task A running
                │
          submit task B
                │
                ▼
          futureB.get()
                │
              WAITING
                │
                ▼
     B queued, không có worker rảnh
                │
                └── B chưa thể complete
```

Điều quan trọng: `ThreadMXBean.findDeadlockedThreads()` có thể trả `null` vì không có monitor/ownable-synchronizer cycle mà JVM nhận diện. **`null` không loại trừ starvation hoặc deadlock logic** qua Future, message queue, callback, semaphore và remote services.

### 7.2. Dấu hiệu ở thread dump và executor metrics

- Một hoặc nhiều pool workers ở `FutureTask.get`, `CompletableFuture.join`, `LockSupport.park`.
- `activeCount` gần `maximumPoolSize`; queue size tăng hoặc `completedTaskCount` dừng tăng.
- Tasks có thể được **submit từ chính các workers** vào cùng pool.
- Không có `BLOCKED` hoặc Java monitor deadlock report.
- Request timeout tăng, thread count không nhất thiết tăng.
- CPU có thể thấp vì workers đang chờ, mặc dù queue đầy.

Một queue có nhiều task không đủ chứng minh starvation: có thể workload burst hoặc downstream chậm. Cần thêm dependency edges, worker utilization và queue wait time.

### 7.3. Callback chain/CompletableFuture cũng có thể tạo vòng chờ

Một flow bất đồng bộ có thể vô tình block:

```java
// Snippet khái niệm, không đầy đủ:
CompletableFuture<String> a = loadAsync();
CompletableFuture<String> b = a.thenApply(value -> transform(value));
String result = b.join();  // Block thread hiện tại khi b chưa complete.
```

`loadAsync` và `transform` chưa định nghĩa. Đoạn trên không tự động sai: `join` ở orchestration thread có thể chấp nhận được. Nhưng khi gọi `join` **bên trong thread pool dùng để chạy stages phụ thuộc**, pool nhỏ hoặc bounded queue có thể bị starvation.

Một mô hình ít chặn hơn:

```java
// Snippet trong code đã có async operations:
CompletableFuture<Result> result =
        fetchAsync()
            .thenCompose(data -> enrichAsync(data))
            .thenApply(this::toResult);
```

`fetchAsync`, `enrichAsync`, `toResult` và type `Result` giả định đã có, không phải file độc lập. `thenCompose` thể hiện phụ thuộc bất đồng bộ mà không buộc một worker phải chờ `get` trong một critical section; nhưng **không** tự đảm bảo không có blocking bên trong các callbacks hoặc executor implementation.

### 7.4. Không chữa starvation chỉ bằng tăng pool size

Tăng threads từ 1 lên 2 có thể làm ví dụ A→B chạy được, nhưng cũng có thể chỉ trì hoãn lỗi khi traffic cao: N workers đều submit N tasks rồi cùng đợi. Giải pháp cấu trúc thường gồm:

- không block `Future.get`/`join` trong cùng bounded pool chạy producer;
- thiết kế async composition hoặc tách pool đúng theo tính chất blocking/CPU;
- tránh circular dependency giữa tasks/requests;
- đặt queue bound, rejection policy, deadline, timeout và cancellation có quan sát;
- kiểm tra backpressure, workload và thread-pool sizing dựa trên đo lường;
- giảm thời gian giữ Java monitor khi đợi Future/I/O.

## 8. Bảng quyết định: monitor, I/O hay Future?

| Dấu hiệu | Monitor contention | I/O wait | Future wait |
| --- | --- | --- | --- |
| Java state thường thấy | `BLOCKED` | Có thể `RUNNABLE` trong native read hoặc WAITING theo thư viện | `WAITING`/`TIMED_WAITING` |
| Top frames đặc trưng | `- waiting to lock` khi vào `synchronized` | Socket/file/selector/driver/native read | `FutureTask.get`, `CompletableFuture.join/get` |
| Đối tượng phải tìm | Monitor ID + thread owner | Endpoint/file/connection/timeout | Future producer + executor/dependency |
| Metrics có ích | Blocked count/time, lock owner chains, JFR monitor enter | SocketRead/FileRead durations, pool waits, downstream latency | Active/queue/completed tasks, dependency traces |
| CPU của waiter | Thường thấp khi BLOCKED | Thường thấp trong blocking I/O, nhưng state có thể RUNNABLE | Thường thấp khi parked |
| Deadlock detector có thấy? | Có thể thấy vòng monitors | Thường không | Thường không |
| Biện pháp cấu trúc | Giảm thời gian giữ lock, bỏ I/O/await ra khỏi critical section | Timeout/deadline, pool, downstream, backpressure | Async composition, executor graph, timeout, bounded queues |
| Rủi ro diễn giải | Một BLOCKED có thể chỉ thoáng qua | RUNNABLE không bằng CPU-bound | WAITING không bằng monitor deadlock |

**Một thread có thể ở nhiều nguyên nhân theo chuỗi:** A giữ monitor nhưng chờ Future; producer B đang chờ database; các request C chờ monitor của A. Gốc latency có thể là database chậm *khuếch đại* bởi thiết kế monitor, không phải chỉ “database” hay chỉ “lock”.

## 9. Cách lấy thread dump có kiểm soát trên Java 17

### 9.1. `jcmd Thread.print -l`

Với HotSpot JDK 17, lệnh minh họa (PID `12345` phải là JVM đích đúng và có quyền):

```bash
jcmd -l
jcmd 12345 VM.version
jcmd 12345 help Thread.print
jcmd 12345 Thread.print -l
```

`-l` yêu cầu thông tin khóa `java.util.concurrent` khi JVM hỗ trợ. Theo tài liệu JDK, `Thread.print` có tác động **Medium**, phụ thuộc số lượng thread: tạo quá nhiều dumps trên JVM đang chịu tải có thể ảnh hưởng latency.

Trước khi chụp:

1. Chốt service, node/container ID, PID **đúng namespace**, JVM start time, build revision.
2. Ghi mốc UTC và khoảng thời gian sự cố.
3. Tìm trong metrics đã có trước; chỉ chụp dump khi có mục tiêu.
4. Thu 2–3 snapshots cách nhau khoảng vài giây nếu triệu chứng còn xảy ra **và ngân sách tác động cho phép**.
5. Lưu file chỉ nơi được phép, hạn chế quyền đọc và thời hạn giữ.
6. Không chụp quá dày chỉ để bắt một spike 10 ms; JFR/profiler sampling thường thích hợp hơn.

Ví dụ lưu dump vào một thư mục đã được bảo vệ:

```bash
jcmd 12345 Thread.print -l > thread-20261029T081000Z.txt
```

Lệnh chỉ ghi stdout của công cụ tại nơi chạy terminal; không chắc tạo file trong container target. Tên file minh họa, **không phải dump thực**. Trên container, `jcmd -l` không nhất thiết thấy JVM trong namespace khác.

### 9.2. Đọc nhiều snapshots để phân biệt nguyên nhân

Một mẫu tư duy:

```text
t0: 27 request threads BLOCKED on monitor M
t0: owner "cache-refresh" ở Socket.read

t0+5s: 43 request threads BLOCKED on M
t0+5s: owner vẫn Socket.read, không có progress

t0+10s: 52 request threads BLOCKED on M
t0+10s: owner chuyển sang timeout/retry

Đối chiếu: timeout client, backend latency, p99, monitor contention.
```

Đây là **tình huống giả định**. Nó gợi ý I/O chậm kéo dài thời gian giữ monitor, làm số request bị BLOCKED tăng. Để xác nhận cần đúng cùng JVM/monitor, thread identity, event timestamps và code đang giữ monitor trong I/O path.

Với Future starvation:

```text
t0: 8 pool workers ở FutureTask.get, queue size=300
t0+5s: 8 workers vẫn FutureTask.get, queue size=600
t0+10s: active=8, completedTaskCount gần như không tăng

Phân tích dependency: các task sẽ complete Future đang chờ
nằm trong chính queue đang không có worker rảnh?
```

`Thread.State.WAITING` tự nó không trả lời câu cuối. Cần mã submit/callback, task IDs hoặc tracing executor.

### 9.3. Không đọc một stack frame ngoài ngữ cảnh

Mỗi thread entry thường có:

```text
"request-worker-17" #77 ... tid=0x... nid=0x...
  java.lang.Thread.State: WAITING (parking)
      at jdk.internal.misc.Unsafe.park(Native Method)
      at java.util.concurrent.locks.LockSupport.park(...)
      at java.util.concurrent.FutureTask.awaitDone(...)
      at java.util.concurrent.FutureTask.get(...)
      at com.example.PaymentService.process(PaymentService.java:144)
```

`Unsafe.park` ở top **không** có nghĩa “JVM tự treo vì Unsafe”. Điều có ích là chuỗi caller từ `PaymentService.process` tới `FutureTask.get`, vì đó là lý do thread đi vào park. Tìm task producer và đường completion tiếp theo. Tương tự, `Socket.read` cần được nối tới service/client call ở caller frames.

## 10. API `ThreadMXBean`: lock owner, thread info, CPU/blocked time

Java 17 cung cấp `ManagementFactory.getThreadMXBean()` để đọc Java threads có quản lý. API chuẩn này trả Java thread ID/state/stack/locks, **không trả một “I/O_WAITING” enum hoặc native thread ID portable**.

### 10.1. Thu thông tin của một thread

```java
java.lang.management.ThreadMXBean mx =
        java.lang.management.ManagementFactory.getThreadMXBean();

long javaId = Thread.currentThread().getId();
java.lang.management.ThreadInfo info =
        mx.getThreadInfo(javaId, 20);

if (info != null) {
    System.out.println(info.getThreadName());
    System.out.println(info.getThreadState());
    System.out.println(info.getLockOwnerName());
}
```

Đây là snippet đặt trong method. `ThreadInfo.getLockOwnerName()` có thể là `null` nếu không biết owner; không dùng `null` để kết luận “không có phụ thuộc”. `getThreadInfo(id, maxDepth)` lấy tối đa số stack frames yêu cầu. Nếu thread kết thúc giữa các lần đọc, `getThreadInfo` có thể trả `null`.

### 10.2. Kiểm tra monitor và ownable synchronizer support

```java
boolean monitors = mx.isObjectMonitorUsageSupported();
boolean synchronizers = mx.isSynchronizerUsageSupported();

java.lang.management.ThreadInfo[] snapshot =
        mx.dumpAllThreads(monitors, synchronizers);
```

Đoạn này dùng `mx` được khai báo như trên, không phải chương trình độc lập. `dumpAllThreads` có overhead, đặc biệt khi rất nhiều threads. `getLockedMonitors()` và `getLockedSynchronizers()` giúp hiểu ownership nếu VM và chế độ dump có hỗ trợ, nhưng không biến mọi `Future`/I/O dependency thành graph tự động.

Nếu chỉ muốn xem một nhóm thread, sử dụng `getThreadInfo(ids, depth)` và metrics trước khi dump toàn bộ JVM. Tránh xuất hết stack frames lên log ở mức INFO trong production.

### 10.3. `getBlockedTime` và `getWaitedTime`

`ThreadInfo.getBlockedCount()` và `getBlockedTime()` liên quan các lần thread chờ monitor; `getWaitedCount()` và `getWaitedTime()` liên quan cơ chế wait theo định nghĩa của API. **Không** diễn giải các trường này như “thời gian chờ network” hoặc “thời gian chờ Future” được tính riêng.

Thread contention monitoring phải được hỗ trợ và bật để có elapsed blocked/waited time đáng tin:

```java
if (mx.isThreadContentionMonitoringSupported()
        && mx.isThreadContentionMonitoringEnabled()) {
    // Có thể đọc blocked/waited time từ ThreadInfo;
    // vẫn phải hiểu giới hạn và phạm vi của bộ đếm.
}
```

Bật bằng `setThreadContentionMonitoringEnabled(true)` là **thay đổi trạng thái JVM quản lý**, có thể làm tăng overhead. Chỉ làm theo chính sách và cân nhắc tác động; không tự bật trên production chỉ vì thấy `-1`.

### 10.4. Deadlock detection có phạm vi hữu hạn

- `findMonitorDeadlockedThreads()`: phát hiện chu trình chờ **Java object monitors**.
- `findDeadlockedThreads()`: có thể bao gồm ownable synchronizers nếu VM hỗ trợ.
- `null` nghĩa là không tìm được deadlock theo **mô hình những khóa API nhận diện lúc kiểm tra**.

**Nó không phát hiện mọi Future starvation, chờ socket/DB, distributed lock hay vòng phụ thuộc logic qua callbacks.** Một pool có tất cả workers chờ `Future.get()` trong khi producer tasks nằm trong queue có thể treo vô hạn nhưng deadlock API trả `null`.

Đừng “chữa deadlock” bằng force-stop thread. `Thread.stop` không an toàn và đã deprecated lâu; thao tác phá monitor/kill task tùy tiện có thể làm hỏng trạng thái. Hãy xử lý dependency graph và rollback an toàn.

## 11. Chương trình Java 17+ độc lập: monitor BLOCKED và Future WAITING

Chương trình này **cố ý tạo hai kiểu chờ khác nhau**, dùng latch để đồng bộ thời điểm quan sát, sau đó giải phóng tất cả threads. Không cần kết nối mạng hoặc external service. Mục đích là chứng minh: `synchronized` làm contender **BLOCKED**, trong khi chờ một `CompletableFuture.join()` chưa hoàn tất thường làm consumer **WAITING (parking)** trên HotSpot/JDK 17.

Lưu file **`MonitorFutureStatesDemo.java`**:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class MonitorFutureStatesDemo {
    private static void awaitState(Thread thread, Thread.State expected)
            throws InterruptedException {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(3);
        while (thread.getState() != expected) {
            if (System.nanoTime() >= deadline) {
                throw new IllegalStateException(
                    thread.getName() + " did not enter " + expected
                    + "; actual=" + thread.getState());
            }
            Thread.sleep(5);
        }
    }

    public static void main(String[] args) throws Exception {
        Object monitor = new Object();
        CountDownLatch ownerEntered = new CountDownLatch(1);
        CountDownLatch releaseOwner = new CountDownLatch(1);

        Thread owner = new Thread(() -> {
            synchronized (monitor) {
                ownerEntered.countDown();
                try {
                    releaseOwner.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            }
        }, "monitor-holder");

        Thread contender = new Thread(() -> {
            synchronized (monitor) {
                // Chỉ được chạy sau khi owner nhả monitor.
            }
        }, "monitor-contender");

        owner.start();
        if (!ownerEntered.await(3, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Owner did not start");
        }
        contender.start();

        try {
            awaitState(contender, Thread.State.BLOCKED);
            ThreadMXBean mx = ManagementFactory.getThreadMXBean();
            ThreadInfo info = mx.getThreadInfo(contender.getId(), 10);

            System.out.println("monitor.state=" + info.getThreadState());
            System.out.println("monitor.owner="
                    + info.getLockOwnerName());
        } finally {
            releaseOwner.countDown();
            owner.join(3000);
            contender.join(3000);
        }

        CompletableFuture<String> result = new CompletableFuture<>();
        CountDownLatch consumerReady = new CountDownLatch(1);
        AtomicReference<String> observed = new AtomicReference<>();

        Thread consumer = new Thread(() -> {
            consumerReady.countDown();
            observed.set(result.join());
        }, "future-consumer");

        consumer.start();
        if (!consumerReady.await(3, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Consumer did not start");
        }

        try {
            awaitState(consumer, Thread.State.WAITING);
            System.out.println("future.state=" + consumer.getState());
            System.out.println("future.done.before=" + result.isDone());
        } finally {
            result.complete("ok");
            consumer.join(3000);
        }
        System.out.println("future.value=" + observed.get());
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac MonitorFutureStatesDemo.java
java MonitorFutureStatesDemo
```

**Stdout kỳ vọng khi chạy thành công trên HotSpot/OpenJDK 17** (không bị timeout hoặc can thiệp từ debugger):

```text
monitor.state=BLOCKED
monitor.owner=monitor-holder
future.state=WAITING
future.done.before=false
future.value=ok
```

**Giải thích chi tiết:**

1. `owner` lấy monitor trước, đợi `releaseOwner` khi **vẫn đang giữ monitor**. `contender` phải BLOCKED ở `synchronized`.
2. `ThreadMXBean.getThreadInfo` nhìn thấy `BLOCKED` và owner tên `monitor-holder` trong môi trường hỗ trợ monitor ownership.
3. Khi `releaseOwner.countDown()`, owner nhả monitor và contender kết thúc; ví dụ không để thread treo vô hạn.
4. `consumer` gọi `CompletableFuture.join()` trên future chưa complete; HotSpot 17 thường đưa nó tới `WAITING (parking)`, **không phải BLOCKED chờ Java monitor**.
5. `result.complete("ok")` giải phóng consumer; kết quả quan sát là `ok`.
6. Các vòng kiểm tra trạng thái chỉ dành cho demo; chúng có thể timeout trên VM/platform scheduling quá chậm hoặc khác implementation. Không nên biến cách poll `getState()` thành framework production.
7. Nếu chạy bằng JVM khác, `getLockOwnerName()` hoặc trạng thái cụ thể của `join` có thể khác; đó là lý do output được ghi **có điều kiện** theo môi trường hỗ trợ, chứ không hứa bất biến trên mọi VM.

Đây là **chương trình runnable hoàn chỉnh**. Nó thay đổi trạng thái local threads do chính nó tạo ra, không attach JVM bên ngoài. Không thực hiện chương trình demo với một object monitor dùng chung của ứng dụng production.

## 12. Chương trình Java 17+ độc lập: Future starvation có timeout an toàn

Ví dụ này chủ động tạo vòng chờ trong `newSingleThreadExecutor`, nhưng **dùng timeout** để chương trình tự thoát thay vì treo vô hạn. Điểm học tập: worker chỉ có một, task A submit task B lên **chính pool đó**, sau đó A chờ B. B không thể chạy cho tới khi A thoát.

Lưu file **`SingleWorkerFutureStarvationDemo.java`**:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class SingleWorkerFutureStarvationDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService one = Executors.newSingleThreadExecutor();
        try {
            Future<String> outer = one.submit(() -> {
                Future<String> inner = one.submit(() -> "inner-completed");
                try {
                    inner.get(200, TimeUnit.MILLISECONDS);
                    return "unexpected";
                } catch (TimeoutException expected) {
                    return "timeout-waiting-for-queued-inner";
                }
            });

            String result = outer.get(5, TimeUnit.SECONDS);
            System.out.println("outer=" + result);
        } finally {
            one.shutdown();
            if (!one.awaitTermination(5, TimeUnit.SECONDS)) {
                one.shutdownNow();
            }
        }
    }
}
```

Biên dịch/chạy:

```bash
javac SingleWorkerFutureStarvationDemo.java
java SingleWorkerFutureStarvationDemo
```

**Stdout chính xác khi chương trình chạy thành công, không bị ngắt từ bên ngoài:**

```text
outer=timeout-waiting-for-queued-inner
```

Tại sao đây không phải “Java monitor deadlock”?

- `outer` đang chạy trên worker duy nhất; `inner` **đã submit nhưng còn trong executor queue**.
- `outer` gọi `inner.get(200, ...)` rồi đợi 200 ms. Nó có thể ở `TIMED_WAITING`/parking tại snapshot.
- Không có thứ tự nào để `inner` bắt đầu **trước khi outer nhả worker**. Vì vậy timeout là kết quả tất yếu của mô hình một worker, không phải lỗi của `Future.get`.
- Sau timeout, `outer` trả về, worker rảnh và có thể chạy `inner`; `shutdown`/`awaitTermination` hoàn tất.
- Nếu thay `get(200,...)` bằng `get()` không timeout, ví dụ có thể treo vô hạn. **Không làm điều này trong môi trường cần an toàn.**
- `findDeadlockedThreads` có thể không phát hiện vấn đề, vì nguyên nhân nằm ở **executor scheduling/dependency**, không phải cycle của Java monitors.

**Giải pháp:** không block worker chờ task đã enqueue vào chính bounded pool; đưa kết quả theo async composition hoặc dùng kiến trúc executor phụ thuộc phù hợp. Thêm một worker đôi khi giải phóng case nhỏ nhưng không bảo đảm xử lý được workload N tasks cùng chờ N tasks khác.

## 13. Chương trình Java 17+ độc lập: I/O read trên loopback

Ví dụ này tạo một server socket trên **loopback** của máy thực hành, cho thread reader chờ nhận byte rồi client gửi dữ liệu. Nó minh họa: thread có thể đang block trong `InputStream.read`, trong khi Java state được chụp tùy OS/implementation, **không có state I/O_WAITING chuẩn**.

Lưu file **`LoopbackIoWaitDemo.java`**:

```java
import java.io.IOException;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class LoopbackIoWaitDemo {
    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();
        AtomicInteger received = new AtomicInteger(-1);
        AtomicReference<IOException> error = new AtomicReference<>();
        CountDownLatch accepted = new CountDownLatch(1);

        try (ServerSocket listener = new ServerSocket(0, 1, loopback)) {
            Thread reader = new Thread(() -> {
                try (Socket peer = listener.accept()) {
                    peer.setSoTimeout(3000);
                    accepted.countDown();
                    received.set(peer.getInputStream().read());
                } catch (IOException ex) {
                    error.set(ex);
                }
            }, "socket-reader");

            reader.start();

            try (Socket client = new Socket(loopback,
                    listener.getLocalPort())) {
                if (!accepted.await(2, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("No connection accepted");
                }

                // Đọc trạng thái trong lúc peer chưa gửi byte.
                Thread.sleep(50);
                System.out.println("io.reader.state.sample="
                        + reader.getState());

                client.getOutputStream().write(65); // ASCII 'A'
            }

            reader.join(4000);
            if (reader.isAlive()) {
                throw new IllegalStateException("Reader still running");
            }
            if (error.get() != null) {
                throw new IllegalStateException("Reader error", error.get());
            }
            System.out.println("io.received.byte=" + received.get());
        }
    }
}
```

Biên dịch/chạy bằng JDK 17+ trên máy cho phép bind loopback:

```bash
javac LoopbackIoWaitDemo.java
java LoopbackIoWaitDemo
```

**Output minh họa** trên một HotSpot/Linux có blocking socket read:

```text
io.reader.state.sample=RUNNABLE
io.received.byte=65
```

Dòng `io.reader.state.sample=...` là **giá trị sống**, có thể khác vì scheduler/JDK/socket implementation; không cố định `RUNNABLE` trong mọi môi trường. Dòng `io.received.byte=65` được xác định bởi byte client gửi **nếu chạy thành công**. Ví dụ không gọi dịch vụ ngoài và có read timeout để tránh treo vô hạn.

Điểm quan trọng: kể cả khi reader báo `RUNNABLE`, chúng ta **biết** nó đang ở đường I/O chờ byte, vì reader không thể nhận `65` trước khi client gửi. Nếu muốn đối chiếu JVM stack, hãy lấy `ThreadMXBean.getThreadInfo(reader.getId(),20)` trong khoảng trước khi gửi, nhưng nhớ đó là một snapshot không đồng thời với `getState()`.

## 14. JFR và các bằng chứng bổ sung theo nguyên nhân

### 14.1. JFR events cho monitor, parking và I/O

JDK Flight Recorder (JFR) có các event có thể phục vụ điều tra khi recording settings phù hợp, ví dụ:

- `jdk.JavaMonitorEnter`: thread chờ vào Java monitor; duration/threshold giúp tìm contention đáng kể.
- `jdk.JavaMonitorWait`: thread đợi `Object.wait` — **khác** monitor enter contention.
- `jdk.ThreadPark`: thread park; có thể liên quan Future, AQS lock, idle executor hoặc các cơ chế khác.
- `jdk.SocketRead` / `jdk.SocketWrite`: hoạt động I/O socket theo cấu hình/threshold.
- `jdk.FileRead` / `jdk.FileWrite`: I/O file khi event được bật và ngưỡng phù hợp.
- Execution samples, CPU load, GC/safepoints khi ghi phù hợp.

**Không giả định mọi event luôn bật và mọi lần đợi đều được ghi**. JFR có threshold, event settings, sampling và giới hạn dữ liệu; khoảng wait ngắn dưới threshold có thể không hiện. Không gọi một event `ThreadPark` là “Future wait” nếu thiếu stack/caller context.

### 14.2. Xác minh recording hiện có

Ví dụ với HotSpot JDK 17 có `jcmd`, PID minh họa:

```bash
jcmd 12345 JFR.check
jcmd 12345 help JFR.dump
```

Nếu có recording đang chạy và được phép thu, `JFR.dump` có thể lưu snapshot theo quy trình. **Không tự bật recording hoặc tăng event thresholds trên production** nếu chưa cân nhắc impact, disk và dữ liệu nhạy cảm. Khi cần bắt micro-spike, sampling/JFR thường hiệu quả hơn chụp thread dump liên tiếp.

### 14.3. OS/network và executor telemetry

Với I/O:

- latency tới endpoint, error/timeout rates, connection pool pending/active;
- socket states, retransmission, DNS timings, disk latency và queue depth;
- request trace/span IDs để tìm callback/producer liên quan;
- CPU thread time để phân biệt native blocking với busy loop.

Với Future:

- executor core/max threads, activeCount, queue size, completedTaskCount, rejectedCount nếu hệ thống hỗ trợ;
- thời gian task nằm trong queue vs chạy thực, task/parent IDs;
- dependency graph và cancellation/timeout propagation;
- completion metrics của nguồn dữ liệu.

Với monitor:

- lock owner/waiter count, blocked time/count, JFR monitor enter events;
- critical section duration và code có chờ network/Future dưới monitor không;
- nhiều snapshots để xem holder thay đổi hay đứng tại cùng call path.

## 15. Năm tình huống đọc dump và chọn biện pháp

### Case A — 80 request threads `BLOCKED` cùng một monitor

**Dữ liệu giả định:** nhiều `http-worker` có `- waiting to lock <0xABC>`; owner `cache-refresh` có `- locked <0xABC>` và stack tại `Socket.read`.

**Diễn giải:** waiter bị monitor contention; owner giữ monitor trong lúc I/O. Nếu downstream chậm, contention được khuếch đại. Kiểm tra monitor identity trong cùng dump, timeout, JFR lock events và source code để chứng minh quan hệ.

**Hành động:** thu nhỏ critical section, tách remote request khỏi monitor khi thiết kế cho phép, sử dụng immutable/cache snapshot, timeout và backpressure đúng. Không chỉ tăng HTTP worker pool.

### Case B — 150 threads ở `Socket.read`, CPU thấp

**Dữ liệu giả định:** nhiều threads RUNNABLE ở native socket read, pool pending tăng, dependency p99 tăng.

**Diễn giải:** I/O wait có thể chiếm worker threads dù CPU thấp. Kiểm tra connection pool, server response time, socket read timeouts, DNS/TLS/retries. Dùng spans và các JFR `SocketRead` events để xác minh. Chỉ giảm số threads chưa giải quyết dependency đang chậm.

**Hành động:** deadline tổng, per-hop timeout hợp lý, circuit breaker, giới hạn concurrency/retry budget, tăng tài nguyên downstream nếu metrics chứng minh bottleneck.

### Case C — Futures chờ kết quả từ chính bounded executor

**Dữ liệu giả định:** 8/8 workers ở `FutureTask.get`, queue size tăng, completed task count không nhúc nhích. Nguồn code cho thấy 8 workers đã submit child tasks về cùng pool rồi chờ.

**Diễn giải:** dependency starvation. Không cần monitor deadlock; `findDeadlockedThreads()` có thể trả `null`.

**Hành động:** async composition, tách responsibilities/executors theo loại tác vụ và loại bỏ blocking wait trong pool thực thi producers. Đặt timeout/backpressure để tránh treo vô hạn; không chỉ tăng pool size tùy tiện.

### Case D — CompletableFuture join nhưng producer thật đang chờ DB

**Dữ liệu giả định:** request threads WAITING ở `CompletableFuture.join`; producer tasks có stack JDBC/network; database pool active=max và pending tăng.

**Diễn giải:** việc chờ Future là **triệu chứng tại caller**, nhưng nguyên nhân kéo dài completion nằm ở DB/pool hoặc đường I/O. Phải lần theo producer/callback rồi áp dụng deadline/cancellation, connection pool limit và SQL diagnostics.

**Hành động:** cải thiện dependency/pool hoặc tối ưu query, tránh vô hạn retry và propagate deadline. Không gán nhãn “CompletableFuture lỗi” chỉ vì frame `join` xuất hiện.

### Case E — Hai threads chờ nhau gián tiếp

**Dữ liệu giả định:** A giữ monitor M và chờ futureB; B cần lấy M mới complete futureB. A có WAITING ở `FutureTask.get`; B BLOCKED ở `waiting to lock M`.

**Diễn giải:** có **vòng phụ thuộc kết hợp** (monitor + Future) mà monitor-only deadlock detector có thể không nhận diện. Tìm owner A, waiter B, producer của futureB và code path complete.

**Hành động:** bỏ blocking future wait khỏi vùng giữ monitor, tách state update, xác định lock ordering và boundary async; kiểm thử để loại trừ race/cancellation side effects.

## 16. Cách viết một kết luận incident có thể kiểm chứng

Tránh câu quá mức chắc chắn: “JVM treo vì WAITING” hoặc “80 BLOCKED chắc chắn deadlock”. Mẫu tốt hơn:

```text
Quan sát:
  2026-10-29T08:10:00Z, JVM PID=12345, start=...
  37 request threads BLOCKED on monitor M
  owner thread="cache-refresh", frame Socket.read
  downstream p99 tăng từ 120ms lên 4s

Tái quan sát:
  t+5s, 45 request threads BLOCKED on cùng M
  owner vẫn chờ network read, pool queue tăng

Giả thuyết:
  Remote I/O kéo dài khi holder vẫn giữ monitor,
  dẫn tới contention dây chuyền.

Cần xác minh:
  source synchronized block, timeout settings,
  trace cụ thể của downstream call và JFR monitor enter.

Khắc phục được đề xuất:
  loại I/O khỏi critical section khi an toàn,
  bổ sung deadline/backpressure và đo sau thay đổi.
```

Đây là **case mô phỏng**, không phải báo cáo một hệ thống thật. Kết luận “đã xác nhận root cause” chỉ nên viết khi có **evidence nối được owner/waiter/dependency và thời gian**.

### 16.1. Thu thập không làm hỏng bằng chứng

- Không restart JVM trước khi thu tối thiểu các snapshot được phép nếu restart sẽ xóa mất hiện trạng, trừ khi khôi phục dịch vụ khẩn cấp quan trọng hơn.
- Không tự tạo hàng trăm thread dumps vì hành động đo có thể làm tăng latency.
- Không gọi `System.gc()` hoặc full heap dump chỉ để xác nhận một Future chờ.
- Đừng hủy tất cả Futures hoặc `shutdownNow()` executor trên production nếu chưa hiểu idempotency/transaction/interruptibility.
- Giữ tất cả dumps/metrics với cùng timezone UTC, JVM identity, mốc t0/t1, phạm vi container và nguồn tool.
- Thread names, file paths, DB URLs, custom MDC, task labels và stack traces có thể chứa thông tin nhạy cảm: redact trước khi chia sẻ và áp dụng retention/quyền truy cập.

## 17. Các lỗi thường gặp khi phân loại treo và tranh chấp

1. **Đồng nhất WAITING với deadlock.** Thread pool idle là WAITING hợp lệ.
2. **Đồng nhất BLOCKED với mọi loại lock.** ReentrantLock contention có thể là WAITING/parking.
3. **Cho rằng RUNNABLE luôn dùng CPU.** Native I/O wait có thể xuất RUNNABLE.
4. **Chỉ đọc top frame `Unsafe.park`.** Caller `Future.get`/`Condition.await`/`ThreadPoolExecutor.getTask` mới giải thích ngữ nghĩa.
5. **Chỉ đọc một dump và gọi đó là nguyên nhân gốc.** Cần snapshots theo thời gian, metrics và code context.
6. **Không tìm lock owner.** Waiter BLOCKED không nói ai giữ monitor hoặc vì sao.
7. **Đọc `Object.wait` như giữ monitor đang chờ vào.** Thread nhả monitor trên object được wait, nhưng có thể vẫn giữ lock khác.
8. **Cho rằng Thread.sleep nhả monitor.** Nó không nhả monitor.
9. **Cho rằng mọi `LockSupport.park` là Future.** Cũng có thể là pool idle, AQS lock, semaphore, condition.
10. **Thấy `Socket.read` và kết luận database bị lỗi.** Cần biết endpoint, driver/pool, timeout, SQL và tracing.
11. **Thấy `CompletableFuture.join` và kết luận Future implementation lỗi.** Producer/executor thường mới là nơi cần điều tra.
12. **Tin `findDeadlockedThreads() == null` là hết deadlock.** Không phát hiện logic wait cycles qua Future/I/O.
13. **Tăng pool size mà không xử lý nested blocking.** Chỉ làm starvation chậm xuất hiện.
14. **Không tách queue wait và execution time.** Request có thể chờ producer chưa được bắt đầu.
15. **Đặt timeout chỉ một tầng, không có deadline tổng.** Retries và nhiều hop khiến latency vượt SLA.
16. **Coi `cancel(true)` chắc chắn dừng task I/O.** Cancellation chỉ là nỗ lực; công việc có thể không hỗ trợ interrupt.
17. **Cho rằng `orTimeout` tự hủy remote work.** Nó có thể chỉ complete future exceptionally.
18. **Đọc `ThreadInfo.getBlockedTime()=-1` thành “không bị chặn”.** Có thể vì contention monitoring chưa bật.
19. **Bật contention monitoring/JFR cực chi tiết không cân nhắc overhead.** Công cụ đo cũng có tác động.
20. **Không kiểm tra JVM/PID/container namespace.** Có thể phân tích dump khác đời process.
21. **Bỏ qua I/O nằm trong monitor.** Incident có thể có nhiều lớp nguyên nhân phụ thuộc.
22. **Chỉ xem CPU process tổng.** CPU thấp không loại trừ network wait, lock contention hoặc starvation.
23. **Bỏ qua thread giàu CPU trong callback thay vì request thread đang chờ.** Producer có thể bận loop.
24. **Nhầm Java ID/HotSpot tid/nid.** Không dùng native TID thay Java thread ID trong ThreadMXBean.
25. **Không bảo vệ dữ liệu chẩn đoán.** Full stack/task names có thể tiết lộ endpoint và thông tin nội bộ.

## 18. Checklist thực hành

- [ ] Đúng JVM process, PID namespace, start time và UTC timestamp?
- [ ] Triệu chứng là request timeout, CPU cao, queue tăng hay service không phản hồi?
- [ ] Java state thật là BLOCKED, WAITING, TIMED_WAITING hay RUNNABLE?
- [ ] Đã đọc đủ stack callers thay vì chỉ top native/park frame?
- [ ] Nếu BLOCKED: tìm đúng monitor ID và thread giữ monitor trong cùng dump?
- [ ] Nếu Object.wait: phân biệt chờ notification với chờ reacquire lock?
- [ ] Nếu ReentrantLock/AQS: đọc `park` caller và ownable synchronizers?
- [ ] Nếu I/O: xác định socket/file/driver/pool, endpoint, timeout và dependency metrics?
- [ ] Nếu Future: xác định producer, executor, queue, completion và dependency graph?
- [ ] Có kiểm tra nested Future.get/join trong cùng bounded executor không?
- [ ] Có thread nào giữ lock khi gọi remote I/O hoặc Future.get không?
- [ ] Đã phân biệt `Future.isDone()` với thành công?
- [ ] Đã kiểm tra timeouts, cancellation, interrupt handling và deadline tổng?
- [ ] Deadlock detector có phạm vi gì; kết quả null có đủ loại trừ không?
- [ ] Có CPU-time/JFR/OS I/O/GC data để loại trừ giả thuyết khác?
- [ ] Có 2–3 snapshots khi sự cố kéo dài và tác động cho phép?
- [ ] Đã giới hạn số dumps và che dữ liệu nhạy cảm?
- [ ] Báo cáo có tách quan sát, giả thuyết và bằng chứng xác nhận?

## 19. Bài tập tự kiểm tra

**Bài 1 — Monitor hay Future?** Thread A `BLOCKED`, có `waiting to lock <0xAAA>`; thread B `WAITING (parking)`, stack `FutureTask.get`. Có thể nói cả hai cùng chờ monitor không? **Không.** A chờ Java monitor; B chờ kết quả Future. Cần xem B có giữ monitor <0xAAA> hay producer của Future có cần monitor đó không để phát hiện vòng phụ thuộc hỗn hợp.

**Bài 2 — I/O và CPU.** Thread `RUNNABLE` có stack `SocketDispatcher.read0`; CPU time của OS native TID gần như không tăng. Nó đang ngốn CPU? **Chưa có bằng chứng**; có thể native blocking I/O. Cần latency/endpoint/socket counters và nhiều mẫu.

**Bài 3 — Future starvation.** Pool có 1 worker, task A submit B vào cùng pool rồi `B.get()` không timeout. B không chạy được vì A chiếm worker. Đây có phải deadlock monitor mà `findMonitorDeadlockedThreads` chắc chắn tìm ra? **Không.** Đây là dependency starvation, thường không có Java monitor cycle.

**Bài 4 — `Object.wait`.** Thread C gọi `wait()` trên monitor M, có nhả monitor M không? **Có**, trong lúc wait, nhưng có thể vẫn giữ những monitors khác. Khi thức dậy cần reacquire M mới tiếp tục bên trong synchronized.

**Bài 5 — Một snapshot đủ chưa?** 50 request threads ở `CompletableFuture.join`; có thể kết luận Future implementation bị lỗi? **Không**. Kiểm tra producer tasks, executor queue, downstream I/O và cancellation/timeout; lặp snapshot nếu được phép.

**Bài 6 — Timed waits.** Một request timeout từ `Future.get(2,SECONDS)`, nhưng downstream vẫn tiếp tục xử lý 10 giây. Có mâu thuẫn không? **Không**: timeout ở caller không luôn hủy remote computation; cần cancellation/deadline propagation theo API thực.

**Bài 7 — Đường nguyên nhân.** Owner monitor đang chờ JDBC, 100 request threads BLOCKED cùng monitor. Cách sửa phù hợp hơn “tăng request pool” là gì? **Giảm phạm vi giữ monitor**, tránh synchronous I/O trong critical section khi an toàn, kiểm tra database connection pool/timeout và xác minh bằng metrics trước–sau.

## Tài liệu tham khảo

- Oracle Java SE 17, [`Thread.State` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.State.html): semantics BLOCKED, WAITING, TIMED_WAITING, RUNNABLE; Java states khác OS states.
- Oracle Java SE 17, [`ThreadInfo` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadInfo.html): lock owner, monitor, blocked/waited time và stack.
- Oracle Java SE 17, [`ThreadMXBean` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html): dump, lock usage, contention monitoring và deadlock detection.
- Oracle Java SE 17, [`Future` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): `get`, timeout, cancellation, completion state.
- Oracle Java SE 17, [`FutureTask` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/FutureTask.html): FutureTask execution và completion.
- Oracle Java SE 17, [`CompletableFuture` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `join/get`, async stages, completion/cancellation và timeouts.
- Oracle Java SE 17, [`Object.wait` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html): giải phóng monitor đang wait và điều kiện wake-up.
- Oracle Java SE 17, [`LockSupport` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/LockSupport.html): parking và blocker context.
- Oracle Java SE 17, [`jcmd` Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): `Thread.print -l`, cú pháp và mức tác động.
- Oracle Java SE 17, [Java Flight Recorder Runtime Guide](https://docs.oracle.com/en/java/javase/17/jfapi/index.html): sự kiện runtime và bản ghi JFR, khi được bật đúng.
- Oracle Java SE 17, [Prepare Java for Troubleshooting](https://docs.oracle.com/en/java/javase/17/troubleshoot/prepare-java-troubleshooting.html): thu một số thread dumps khi JVM không phản hồi và lưu bằng chứng.

**Kết luận:** trước khi sửa lỗi “treo”, hãy hỏi **thread đang chờ lấy monitor, chờ hoàn tất I/O hay chờ một Future?**. `BLOCKED` kèm `waiting to lock` chỉ vào monitor, `RUNNABLE` ở native read có thể là I/O wait, và `WAITING` ở `FutureTask.get`/`CompletableFuture.join` chỉ vào dependency bất đồng bộ. Lần theo **lock owner hoặc task producer**, kiểm tra liệu chúng có tiếp tục chạy được không, rồi đối chiếu với nhiều snapshots, queue/downstream metrics và JFR để chọn cách sửa đúng tầng.