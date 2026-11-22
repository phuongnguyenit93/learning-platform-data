# 8.4. Phân biệt RUNNABLE, BLOCKED, WAITING và TIMED_WAITING

Khi điều tra một service Java chậm, treo hoặc không trả lời, bạn thường xem thread dump và thấy các nhãn `RUNNABLE`, `BLOCKED`, `WAITING`, `TIMED_WAITING`. **Cùng một nhãn có thể là trạng thái vận hành hoàn toàn bình thường hoặc là triệu chứng của sự cố**, tùy thread đang làm gì, nó đang đợi ai/tài nguyên gì, trạng thái có kéo dài không và công việc nghiệp vụ có tiến triển không.

Bài học thuộc **8. Thread dump**. Mục tiêu là đọc đúng ý nghĩa của bốn trạng thái `java.lang.Thread.State`, liên hệ với stack frames, monitor/lock, API đồng bộ và dấu hiệu trong một hoặc nhiều thread dumps, rồi điều tra có bằng chứng thay vì suy đoán “WAITING là treo” hay “RUNNABLE chắc chắn tốn CPU”.

## 1. Bốn trạng thái và câu hỏi chẩn đoán cốt lõi

Trong Java 17, `Thread.State` là trạng thái do **JVM mô tả**, **không phải** ánh xạ trực tiếp sang trạng thái thread của hệ điều hành. Một thread chỉ có **một** trong sáu giá trị enum tại một thời điểm: `NEW`, `RUNNABLE`, `BLOCKED`, `WAITING`, `TIMED_WAITING`, `TERMINATED`. Bốn trạng thái thường phân tích ở thread dump là:

| Java state | Ý nghĩa ngắn gọn | API/tình huống thường gặp | Câu hỏi cần hỏi |
| --- | --- | --- | --- |
| **RUNNABLE** | Có thể thực thi trong JVM; **có thể đang chờ tài nguyên OS** | Đang chạy Java code, loop, JNI/native I/O, socket read ở một số stack | Có tiêu thụ CPU thực không? Frame có đổi không? Có I/O hoặc native wait không? |
| **BLOCKED** | Đang chờ được vào/reenter **intrinsic monitor** | Chờ `synchronized` block/method, chờ lấy lại monitor sau `Object.wait` | Monitor nào đang bị giữ? Thread owner nào giữ? Có contention/lock ordering không? |
| **WAITING** | Đợi vô thời hạn cho thread/event khác thực hiện hành động | `Object.wait()`, `Thread.join()`, `LockSupport.park()`; `Condition.await()` thường dùng park | Đang đợi tín hiệu nào? Có producer/unpark/notify/complete tương ứng không? |
| **TIMED_WAITING** | Đợi với thời hạn đã chỉ định | `Thread.sleep(...)`, timed `Object.wait`/`join`, `LockSupport.parkNanos`/`parkUntil`, timed condition wait | Đợi gì và timeout bao lâu? Đây là sleep/backoff/poll hợp lệ hay đợi lặp bất thường? |

**Quy tắc ghi nhớ:**
- `BLOCKED` trong `Thread.State` cụ thể là **đợi monitor lock**, không có nghĩa chung chung “bị block bởi mạng, DB hay mutex bất kỳ”.
- `WAITING`/`TIMED_WAITING` mô tả **cơ chế chờ**, chưa kết luận thread có vấn đề.
- `RUNNABLE` không đồng nghĩa thread **đang chiếm CPU core**. Java docs cho phép RUNNABLE trong khi thread đang đợi tài nguyên hệ điều hành như bộ xử lý.
- Một thread ở `BLOCKED`, `WAITING` hoặc `TIMED_WAITING` có thể vẫn **đang làm đúng việc** theo thiết kế. Để nói “treo” cần bằng chứng tiến độ/duration/timeline.

### Hai trạng thái còn lại

- `NEW`: `new Thread(...)` đã tạo nhưng **chưa gọi `start()`**.
- `TERMINATED`: thread đã kết thúc `run()`, không còn chạy.

Không phải mọi `Thread` đang `NEW`/`TERMINATED` đều xuất hiện trong một **thread dump của các thread đang sống**. Hai trạng thái này có trong enum/API nhưng dump thực tế thường tập trung vào thread còn tồn tại ở thời điểm lấy mẫu.

## 2. RUNNABLE: “có thể chạy” chứ không chắc “đang chạy CPU”

### 2.1. Cơ chế

Trong Java SE 17, một thread ở `RUNNABLE` đang thực thi trong JVM theo mô hình Java, nhưng **có thể chờ một tài nguyên từ OS**. Hệ điều hành mới quyết định thread thật sự **running**, **ready/on-run-queue** hay đang chờ một thao tác native. Vì vậy không được nhìn một snapshot `RUNNABLE` rồi kết luận ứng dụng bị CPU-bound.

Ví dụ stack **minh họa** cho tác vụ CPU:

~~~text
"price-worker-1" #42 ... nid=0x2a10 runnable ...
   java.lang.Thread.State: RUNNABLE
        at com.example.PriceCalculator.recalculate(PriceCalculator.java:118)
        at com.example.PriceJob.run(PriceJob.java:53)
~~~

Nếu qua nhiều dumps cách nhau vài giây, thread vẫn ở cùng vòng lặp, CPU time tăng mạnh, p99 request tăng và throughput giảm, đó là **dấu hiệu** cần điều tra hot loop hoặc thuật toán không hiệu quả. Nhưng **một lần dump có frame giống nhau** chưa chứng minh infinite loop.

Ví dụ RUNNABLE có thể không chiếm nhiều CPU:

~~~text
"network-reader" #51 ... nid=0x2a19 runnable ...
   java.lang.Thread.State: RUNNABLE
        at sun.nio.ch.SocketDispatcher.read0(Native Method)
        at sun.nio.ch.SocketDispatcher.read(SocketDispatcher.java:...)
        at sun.nio.ch.NioSocketImpl.implRead(NioSocketImpl.java:...)
~~~

Đây là dạng minh họa, frame có thể thay đổi theo JDK/version/network stack. Lời gọi native/OS I/O có thể chờ dữ liệu trong khi Java state là RUNNABLE. **Không khẳng định mọi socket read đều RUNNABLE**; đối chiếu `top -H`/`pidstat -t`/Java Flight Recorder (JFR) hoặc thread CPU time khi cần.

### 2.2. Phân biệt CPU-bound với native wait

Quy trình gợi ý:
1. Xác định **thread name + Java thread ID + native ID (`nid`)** từ header dump, và PID JVM.
2. Lấy **nhiều snapshots** lúc vấn đề đang xảy ra, cách nhau khoảng thời gian có ích; lưu timestamp.
3. Tìm frames ở **đầu stack**, phần gọi nghiệp vụ và thay đổi giữa các snapshots.
4. Đo CPU **theo thread** bằng công cụ OS phù hợp, ánh xạ native TID với `nid` khi runtime hỗ trợ; trong Linux `nid` thường biểu diễn dạng hex.
5. Nếu CPU time tăng cùng frame loop, ưu tiên điều tra CPU-bound. Nếu CPU thấp, kiểm tra OS wait, I/O, lock/latch, native call, polling và hạ tầng.

**Lưu ý:** “nhiều RUNNABLE” không đủ để giải thích CPU 100%, vì tên trạng thái JVM không trực tiếp phản ánh CPU usage. Đừng dùng số lượng RUNNABLE làm metric CPU thay thế.

## 3. BLOCKED: chờ vào monitor của `synchronized`

### 3.1. Monitor trong Java là gì?

Mỗi object Java có thể là **intrinsic monitor** dùng bởi `synchronized (lock)` hoặc synchronized instance method. Tại một thời điểm chỉ một thread được **giữ monitor** đó. Một thread khác thử vào cùng monitor trong khi có người giữ sẽ ở Java state `BLOCKED` cho đến khi có quyền vào.

~~~java
final Object monitor = new Object();

// Thread A:
synchronized (monitor) {
    // Đang giữ monitor.
    work();
}

// Thread B:
synchronized (monitor) {
    // Nếu A chưa thoát, B phải chờ monitor: BLOCKED.
    otherWork();
}
~~~

Đây là **đoạn minh họa**, giả định `work()`/`otherWork()` và hai threads đã tồn tại; không phải file Java độc lập.

Nếu B bị chặn, một dump HotSpot có thể chứa thông tin dạng:

~~~text
"order-worker-2" #67 ... waiting for monitor entry ...
   java.lang.Thread.State: BLOCKED (on object monitor)
        at com.example.OrderRepository.update(OrderRepository.java:84)
        - waiting to lock <0x00000000ABCDEF00> (a java.lang.Object)
        at com.example.OrderService.process(OrderService.java:41)
~~~

Các địa chỉ, class, line và header là **giá trị minh họa**, không phải stdout có thể tái lập. Cần tìm **thread giữ monitor**; trong output có thể có một frame tương ứng:

~~~text
"order-worker-1" #66 ... 
   java.lang.Thread.State: TIMED_WAITING (sleeping)
        at java.lang.Thread.sleep(Native Method)
        at com.example.OrderRepository.update(OrderRepository.java:79)
        - locked <0x00000000ABCDEF00> (a java.lang.Object)
~~~

Mặc dù owner đang `TIMED_WAITING` vì sleep, nó **vẫn giữ monitor**; B chờ ở `BLOCKED`. Điều này cho thấy không thể chẩn đoán chỉ bằng trạng thái của từng thread mà bỏ qua **quan hệ lock owner**.

### 3.2. BLOCKED khác `ReentrantLock.lock()`

Một thread chờ **`java.util.concurrent.locks.ReentrantLock`** thường được triển khai bằng **`LockSupport.park()`**, nên trong dump thường là `WAITING (parking)` hoặc `TIMED_WAITING` với timeout. Nó **không nhất thiết** ở `BLOCKED` mặc dù xét theo nghĩa tiếng Việt là “bị chặn bởi một khóa”.

Cần xem:
- Frame `java.util.concurrent.locks.AbstractQueuedSynchronizer.acquire/park...` hoặc `LockSupport.park`.
- Các dòng `parking to wait for <...>` hoặc thông tin ownable synchronizers, tùy công cụ và tùy chọn `-l`.
- `ThreadInfo.getLockOwnerId()/getLockOwnerName()` hoặc `ThreadMXBean.dumpAllThreads(true,true)` nếu runtime hỗ trợ thu thập lock info.

**Đừng đánh đồng:** `BLOCKED` (enum JVM) ↔ blocked I/O ↔ waiting for a database connection ↔ waiting on `ReentrantLock`. Hãy đọc **loại primitive** và **frame thực tế**.

### 3.3. BLOCKED kéo dài có ý nghĩa gì?

- Một vài milliseconds `BLOCKED` khi nhiều threads vào critical section ngắn là bình thường.
- Nhiều thread `BLOCKED` trên **cùng object monitor** trong nhiều snapshots, owner giữ lock lâu: có thể là **contention bottleneck**.
- Hai hoặc nhiều thread giữ những monitor khác nhau và chờ chéo nhau, không tiến triển: có thể là **deadlock**.
- Một owner đang sleep/I/O/call DB **trong synchronized**, làm những thread khác chờ dài: thường là thiết kế critical section quá rộng.

Hỏi “thread nào giữ lock, nó đang làm gì trong lock, bao lâu và có tiến triển không?” trước khi thay code.

## 4. WAITING: chờ vô thời hạn, không có nghĩa “đợi mãi”

`WAITING` là trạng thái thread đang chờ một hành động không có timeout chỉ định tại lời gọi chờ.

### 4.1. Các nguyên nhân quen thuộc

- `Object.wait()`: thread phải giữ monitor lúc gọi, sau đó **nhả monitor đó** và đợi `notify`/`notifyAll` hoặc interrupt/spurious wakeup; muốn tiếp tục khỏi `wait`, thread phải **giành lại monitor**, có thể chuyển sang `BLOCKED` nếu monitor vẫn bị giữ.
- `Thread.join()` không timeout: chờ thread khác hoàn thành.
- `LockSupport.park()`: chờ permit/unpark/interrupt hoặc có thể return spuriously.
- `Condition.await()` thường dùng cơ chế park; một thread có thể thấy `WAITING` khi chờ condition.
- Worker threads trong `ExecutorService` có thể `WAITING` khi queue không có task; đây thường là **idle pool** khỏe mạnh.
- `CompletableFuture.join()` hoặc các synchronization utilities có thể dùng parking/waiting; kiểm tra stack và timeout semantics của API cụ thể.

Ví dụ minh họa:

~~~text
"worker-pool-3" #88 ...
   java.lang.Thread.State: WAITING (parking)
        at jdk.internal.misc.Unsafe.park(Native Method)
        at java.util.concurrent.locks.LockSupport.park(LockSupport.java:...)
        at java.util.concurrent.locks.AbstractQueuedSynchronizer$ConditionNode.block(...)
        at java.util.concurrent.ThreadPoolExecutor.getTask(ThreadPoolExecutor.java:...)
~~~

**Không chép cứng các internal frame**: AQS/ThreadPoolExecutor implementation thay đổi theo JDK và collector; output trên chỉ gợi ý. Worker `WAITING` trong `getTask` có thể là chuyện bình thường khi không có việc.

### 4.2. `Object.wait` khác `Thread.sleep`

Hai API thường bị nhầm:
- `Object.wait()` **nhả monitor của object gọi wait**, đang chờ notification, rồi phải re-acquire trước khi tiếp tục. Có thể thấy `WAITING (on object monitor)` hoặc chuyển `BLOCKED` khi reentry.
- `Thread.sleep(milliseconds)` **không nhả các monitor đang giữ** và đặt thread vào `TIMED_WAITING` khi sleep với thời lượng dương.

Đoạn minh họa:

~~~java
synchronized (monitor) {
    monitor.wait();   // Thả monitor này trong lúc đợi.
}

synchronized (monitor) {
    Thread.sleep(1000); // Vẫn giữ monitor trong lúc ngủ.
}
~~~

Các lời gọi trên giả định `monitor` đã khai báo và method bao quanh có `throws InterruptedException` hoặc catch. **Không chạy mẫu `wait()` đầu tiên một mình** nếu không có thread nào có thể notify/unpark: có thể đợi vô hạn. Khi dùng wait cho condition thật, phải đặt trong `while (!condition) monitor.wait()` để xử lý **spurious wakeups** và re-check state.

### 4.3. Khi nào WAITING đáng nghi?

- Pool có rất nhiều `WAITING` nhưng queue trống, request latency bình thường: thường không phải vấn đề.
- Request đang chờ `CompletableFuture.join()` hoặc `CountDownLatch.await()`, nhưng producer không chạy/không bao giờ signal: có thể là **liveness issue**.
- Thread chờ một condition mà code không gọi `signal`/`notify` đúng nhánh: nghi **lost notification/protocol bug**, cần hiểu logic đồng bộ.
- Một thread chờ một `Future.get()` trong khi executor còn một worker duy nhất và task được chờ lại nằm trong cùng executor: có thể là **thread pool starvation deadlock**, dù thread state là WAITING và tool không nhất thiết báo Java monitor deadlock.

Một WAITING kéo dài chưa chứng minh deadlock: cần xác định **event nào sẽ đánh thức**, chủ thể nào phải tạo event và nó có thể làm việc đó không.

## 5. TIMED_WAITING: có timeout, không có nghĩa đã hết hạn

`TIMED_WAITING` là đợi trong thời hạn được chỉ định:

| API | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `Thread.sleep` | `Thread.sleep(500)` | Ngủ với thời gian yêu cầu 500 ms |
| `Object.wait(timeout)` | `lock.wait(500)` trong `synchronized` | Nhả monitor, chờ notification tối đa khoảng thời gian, rồi re-acquire |
| `Thread.join(timeout)` | `other.join(1000)` | Chờ thread kia kết thúc, có giới hạn |
| `LockSupport.parkNanos` | `LockSupport.parkNanos(1_000_000)` | Park tối đa khoảng 1 ms |
| `LockSupport.parkUntil` | Park đến deadline | Chờ tới mốc thời gian đã chỉ định |
| `Condition.await(time, unit)` | Timed condition wait | Chờ signal hoặc tới hạn theo API |

Dấu hiệu dump minh họa:

~~~text
"retry-scheduler" #91 ...
   java.lang.Thread.State: TIMED_WAITING (sleeping)
        at java.lang.Thread.sleep(Native Method)
        at com.example.RetryLoop.backoff(RetryLoop.java:57)
~~~

Hoặc:

~~~text
"polling-worker" #92 ...
   java.lang.Thread.State: TIMED_WAITING (parking)
        at jdk.internal.misc.Unsafe.park(Native Method)
        at java.util.concurrent.locks.LockSupport.parkNanos(LockSupport.java:...)
        at java.util.concurrent.DelayQueue.take(DelayQueue.java:...)
~~~

Các frames là **minh họa**, có thể khác runtime.

**Hiểu đúng:** timeout chỉ là **giới hạn được yêu cầu** theo contract API và lịch JVM/OS; nó không đảm bảo thread được CPU chạy đúng ngay khi hết deadline. Lời gọi có thể trở về sớm do interrupt, notify/unpark (với API hỗ trợ) hoặc spurious wakeup. Với `sleep`, hành vi trả về sớm bởi interrupt được báo qua `InterruptedException`; không tùy tiện cho rằng mọi API có cùng hành vi.

### `TIMED_WAITING` bình thường và bất thường

- Một scheduler đang ngủ giữa các đợt quét, retry có backoff, socket/client chờ có timeout: có thể bình thường.
- Hàng nghìn thread cùng `sleep` trong khối `synchronized`: nghi ảnh hưởng lock contention cho các thread khác.
- Nhiều request threads ở timed `Future.get`/`Condition.await`, p99 cao: có thể downstream chậm hoặc thread pool saturated.
- Một thread lặp lại chu kỳ sleep ngắn rồi retry vô hạn: có thể là **retry storm**, cần xem event logs/metrics.
- **Không** dựa vào TIMED_WAITING để kết luận “sắp tự hồi phục”, nhất là khi timeout được đặt quá dài hoặc loop sau timeout lại đợi tiếp.

## 6. Đọc nhãn trong thread dump đúng ngữ cảnh

### 6.1. Thu thập snapshot bằng công cụ thích hợp

Với JVM đang chạy trên host/namespace phù hợp và quyền attach:

~~~bash
jcmd -l
jcmd 12345 help Thread.print
jcmd 12345 Thread.print -l
~~~

`12345` là PID **minh họa**; phải xác minh PID của JVM thực. `-l` ở `Thread.print` yêu cầu thêm thông tin về `java.util.concurrent` locks, có thể hỗ trợ tìm owner/waiter. `jcmd -l` là switch **liệt kê JVM**, không cùng nghĩa với `Thread.print -l`.

Một số môi trường dùng:

~~~bash
jstack 12345
~~~

Tùy JDK/OS/version, output và mức độ hỗ trợ có thể khác nhau; nếu JVM không attach được, kiểm tra process owner, container PID namespace, JVM đã thoát hay attach bị tắt. Thu thập thread dump có chi phí phụ thuộc số threads; không chạy nhiều lần liên tục ở production khi chưa đánh giá tác động.

**Đừng dùng `jcmd 0 Thread.print`** để điều tra một PID cụ thể: target `0` có thể gửi command tới **nhiều JVM** nhìn thấy, tạo tải không cần thiết.

### 6.2. Đọc header và state line

Ví dụ HotSpot **minh họa**:

~~~text
"request-worker-7" #53 daemon prio=5 os_prio=0 cpu=4.21ms elapsed=22.14s
   tid=0x00007f1234010000 nid=0x2a91 waiting for monitor entry
   java.lang.Thread.State: BLOCKED (on object monitor)
        at com.example.OrderService.update(OrderService.java:88)
        - waiting to lock <0x00000000deadbeef> (a java.lang.Object)
        at com.example.OrderController.handle(OrderController.java:42)
~~~

Các giá trị, class/line, thứ tự fields và cả các trường có xuất hiện hay không đều **phụ thuộc bản JDK, công cụ, OS**.

| Thông tin | Ý nghĩa | Sai lầm cần tránh |
| --- | --- | --- |
| `"request-worker-7"` | Thread name, hữu ích để biết loại executor | Tên có thể trùng, có thể đổi, thread pool tái sử dụng; không là request ID |
| `#53` | Ở nhiều HotSpot dumps là số/Java thread ID được in | Không đồng nhất với OS TID; kiểm tra định dạng |
| `tid=0x...` | Trong một số HotSpot headers là địa chỉ/định danh cấu trúc VM thread | Không tự đổi hex này rồi coi là Linux TID hoặc `Thread.getId()` |
| `nid=0x2a91` | Native thread ID trong header HotSpot | Thường dạng hex; khi đối chiếu OS cần đúng PID namespace |
| `java.lang.Thread.State` | Enum state Java ở thời điểm snapshot | Không phải tình trạng OS/CPU tức thì |
| Frame `at Class.method(File.java:line)` | Vị trí gọi (trên cùng thường gần điểm đang thực thi/chờ) | Không kết luận nguyên nhân gốc từ một frame đơn lẻ |
| `- waiting to lock` | Monitor đang chờ | Tìm thread owner và cùng object monitor ID |
| `- locked` | Monitor đang giữ ở frame tương ứng | Không tự suy rằng việc giữ monitor là lỗi |
| `- parking to wait for` | Đối tượng synchronizer hoặc blocker liên quan park | Cần ngữ nghĩa API, có thể là queue idle |

Header từ công cụ/phiên bản khác có thể dùng câu chữ “runnable”, “waiting on condition”, “waiting for monitor entry” ở **phần header**, còn dòng `java.lang.Thread.State: ...` là enum cần đọc trước. Không lấy một từ “waiting” ở header làm bằng chứng thread ở `WAITING` nếu dòng state thật là `TIMED_WAITING` hoặc `BLOCKED`.

### 6.3. Cách lần một thread trong nhiều dumps

Khi so hai dumps:
1. Đối chiếu **PID JVM + process start time**, tránh so lẫn tiến trình mới sau restart.
2. Dùng thread name và **Java thread ID/native ID** (khi công cụ cung cấp) để theo đúng thread; không dùng name một mình vì pools tái sử dụng tên.
3. So state, top frames, monitor ID, owner và call chain ở nhiều thời điểm.
4. So application timestamps, requestId/traceId, queue size, duration, CPU/GC/I/O metrics và throughput.
5. Đặt câu hỏi “có tiến triển hay không?”, thay vì chỉ “vẫn ở trạng thái giống nhau?”.

Không nên công bố toàn bộ dumps công khai: stack frames, class/path, log metadata và một số tham số có thể tiết lộ thông tin nội bộ.

## 7. Bốn trạng thái dưới góc nhìn chẩn đoán: ma trận nhanh

| Quan sát | Có thể bình thường khi | Cần điều tra sâu khi | Bằng chứng bổ sung |
| --- | --- | --- | --- |
| Nhiều `RUNNABLE` | Đang xử lý tải hoặc native I/O | CPU/thread CPU cao, cùng loop liên tục, request không tiến triển | OS per-thread CPU, JFR, nhiều thread dumps |
| Nhiều `BLOCKED` | Tranh monitor ngắn hạn | Cùng lock trong nhiều dumps, owner giữ lock lâu, p99 tăng | Monitor ID, owner stack, `-l`, contention |
| Nhiều `WAITING` | Executor idle, queue rỗng, background service chờ sự kiện | Request chờ future/latch không được signal, thread starvation | Pending tasks, queue, producer/consumer, trace |
| Nhiều `TIMED_WAITING` | Sleep/backoff/scheduled polling, timeout có kiểm soát | Retry storm, chờ chồng chéo, sleep khi giữ lock, deadline quá dài | Timeout config, event timeline, lock ownership |

**Không có “mức độ nguy hiểm” cố định theo enum.** Một thread RUNNABLE trong vòng lặp CPU vô hạn nguy hiểm hơn hàng trăm WAITING idle. Một BLOCKED 2 ms bình thường hơn một WAITING vô thời hạn trên future mà không còn producer nào.

## 8. Java 17+ chạy độc lập: tạo bốn trạng thái có kiểm soát

Chương trình sau tạo các Java platform threads với **bốn cơ chế độc lập**:

- `demo-runnable`: chạy vòng lặp ngắn với `Thread.onSpinWait()` đến khi main phát tín hiệu dừng.
- `demo-blocked`: chờ monitor đang được giữ bởi `demo-lock-owner`.
- `demo-waiting`: gọi `LockSupport.park()` không timeout đến khi main `unpark`.
- `demo-timed`: gọi `Thread.sleep(60_000L)`, main sẽ interrupt khi kết thúc.

Main thread dùng hàm `awaitState` để kiểm tra **state thực tế** trước khi in, tránh một race phổ biến là `Thread.start()` xong lập tức hỏi `getState()` khi thread chưa vào đúng đoạn code. Nếu môi trường quá tải khiến state không đạt trong 10 giây, demo ném lỗi minh bạch thay vì in sai; `finally` vẫn giải phóng worker threads.

Tạo file **ThreadStatesDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.locks.LockSupport;

public final class ThreadStatesDemo {
    private static Thread.State awaitState(
            Thread thread, Thread.State expected)
            throws InterruptedException {

        long deadline = System.nanoTime()
                + TimeUnit.SECONDS.toNanos(10);

        while (System.nanoTime() < deadline) {
            if (thread.getState() == expected) {
                return expected;
            }
            Thread.sleep(5L);
        }

        throw new IllegalStateException(
                "State not reached: " + thread.getName()
                + " actual=" + thread.getState());
    }

    public static void main(String[] args) throws Exception {
        Object monitor = new Object();
        AtomicBoolean keepRunning = new AtomicBoolean(true);
        AtomicBoolean keepWaiting = new AtomicBoolean(true);
        CountDownLatch ownerLocked = new CountDownLatch(1);
        CountDownLatch releaseOwner = new CountDownLatch(1);

        Thread runnable = new Thread(() -> {
            while (keepRunning.get()) {
                Thread.onSpinWait();
            }
        }, "demo-runnable");

        Thread owner = new Thread(() -> {
            synchronized (monitor) {
                ownerLocked.countDown();
                try {
                    releaseOwner.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            }
        }, "demo-lock-owner");

        Thread blocked = new Thread(() -> {
            synchronized (monitor) {
                // Enters only after demo-lock-owner releases monitor.
            }
        }, "demo-blocked");

        Thread waiting = new Thread(() -> {
            while (keepWaiting.get()) {
                LockSupport.park();
            }
        }, "demo-waiting");

        Thread timed = new Thread(() -> {
            try {
                Thread.sleep(60_000L);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }, "demo-timed");

        runnable.start();
        owner.start();

        try {
            ownerLocked.await(); // Owner now holds monitor.
            blocked.start();
            waiting.start();
            timed.start();

            System.out.println("runnable="
                    + awaitState(runnable, Thread.State.RUNNABLE));
            System.out.println("blocked="
                    + awaitState(blocked, Thread.State.BLOCKED));
            System.out.println("waiting="
                    + awaitState(waiting, Thread.State.WAITING));
            System.out.println("timedWaiting="
                    + awaitState(timed, Thread.State.TIMED_WAITING));
        } finally {
            keepRunning.set(false);
            keepWaiting.set(false);
            releaseOwner.countDown();
            LockSupport.unpark(waiting);
            timed.interrupt();

            runnable.join(2_000L);
            blocked.join(2_000L);
            waiting.join(2_000L);
            timed.join(2_000L);
            owner.join(2_000L);
        }
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 hoặc mới hơn**:

~~~bash
javac ThreadStatesDemo.java
java ThreadStatesDemo
~~~

**Stdout chính xác trong điều kiện scheduling bình thường:**

~~~text
runnable=RUNNABLE
blocked=BLOCKED
waiting=WAITING
timedWaiting=TIMED_WAITING
~~~

**Vì sao mỗi dòng đúng:**
1. `demo-runnable` đang vòng lặp và chưa nhận stop; JVM báo RUNNABLE. Đây là vòng spin để **minh họa**, có thể tiêu thụ CPU; không dùng trong business code.
2. `demo-lock-owner` đã vào `synchronized` và đang giữ monitor. `demo-blocked` chờ lấy cùng monitor nên BLOCKED.
3. `demo-waiting` đang park không timeout nên WAITING (kể cả khi park có thể return spuriously, vòng lặp đưa thread vào park lại).
4. `demo-timed` đang sleep dương thời gian nên TIMED_WAITING; main interrupt để không phải chờ 60 giây.
5. `finally` tắt loop, release monitor, unpark worker và interrupt sleeper để chương trình kết thúc.

**Hạn chế và QA:**
- `Thread.getState()` chỉ là **snapshot**, có thể đổi ngay sau khi trả về. Poll chờ một state làm demo đáng tin hơn, nhưng không “đóng băng” mọi thread.
- Trong môi trường CPU starvation rất nặng hoặc không cho khởi tạo threads, state có thể không đạt deadline; khi đó chương trình báo `IllegalStateException` và output sẽ khác. Bốn dòng trên là kết quả dự kiến khi chạy trong môi trường Java 17 bình thường.
- Demo giữ monitor trong lúc owner `await()`, đó là **cố tình tạo contention để học**, không phải mẫu code tối ưu.
- Spin loop chủ ý làm tải CPU trong thời gian ngắn. Không chạy stress test vô hạn hoặc trên production để “bắt” RUNNABLE.
- Java 17 dùng platform threads; nếu bạn chạy JVM đời mới với virtual threads, cần xem format và APIs hỗ trợ tương ứng, không áp đặt mọi chi tiết header HotSpot JDK 17 cho bản mới.

### 8.1. Xem thread dump khi demo đang chạy

Demo trên thường hoàn tất nhanh nên **khó đủ thời gian** để bạn kịp chạy `jcmd` ở terminal khác. Có hai cách:
- **Cách không sửa chương trình:** chạy demo nhiều lần để quan sát qua `getState()`; xem output của bốn dòng kiểm chứng.
- **Cách chỉnh cho môi trường thử nghiệm:** thêm một dòng `Thread.sleep(10_000L);` **ở main sau bốn dòng print và trước `finally`** để giữ các worker ở trạng thái đã thiết lập trong 10 giây, rồi tại terminal khác chạy `jcmd -l` và `jcmd <PID> Thread.print -l`. Khi sleep ở main, main là `TIMED_WAITING`, nhưng worker states vẫn có thể thay đổi giữa snapshot; nên xác nhận cụ thể.

Nếu muốn lệnh không chứa `<PID>` theo literal, thay thế đúng số PID thực:
~~~bash
jcmd 12345 Thread.print -l
~~~

Không để thread demo giữ monitor vô hạn; `finally` giải phóng trong mọi đường đi hợp lệ.

### 8.2. Liên hệ với Java management APIs

Trong code Java, bạn có thể lấy `Thread.State` qua `thread.getState()` hoặc quan sát bên ngoài bằng `ThreadMXBean`:

~~~java
ThreadMXBean bean = ManagementFactory.getThreadMXBean();
ThreadInfo[] infos = bean.dumpAllThreads(true, true);

for (ThreadInfo info : infos) {
    System.out.printf(
            "%s javaId=%d state=%s lockOwner=%s%n",
            info.getThreadName(),
            info.getThreadId(),
            info.getThreadState(),
            info.getLockOwnerName()
    );
}
~~~

Đây là **đoạn minh họa** cần imports `java.lang.management.ManagementFactory`, `ThreadMXBean` và `ThreadInfo`, không phải chương trình độc lập. `dumpAllThreads(true,true)` có chi phí và khả năng thu lock info tùy runtime; không lặp ở tần suất rất cao khi service đang căng.

`ThreadInfo` có thể cho `getLockName()`, `getLockOwnerId()`, `getLockOwnerName()`, `getStackTrace()`, `getLockedMonitors()` và `getLockedSynchronizers()` tùy thông tin thu được. Nếu owner là `null` hoặc `-1`, không có nghĩa toàn bộ hệ thống không có dependency; chỉ nói bean/dump hiện không có owner phù hợp được nhận diện.

## 9. Những pattern dễ gây kết luận sai

### 9.1. “Nhiều thread WAITING = ứng dụng bị deadlock”

Một `ThreadPoolExecutor` có thể có hàng chục workers ở `WAITING` để đợi `BlockingQueue.take()`. Nếu requests vẫn được xử lý và queue không tồn đọng, đây là trạng thái **idle**. Ngược lại, chỉ một request thread WAITING trên `Future.get()` mà không còn worker sản xuất kết quả có thể làm một giao dịch đứng.

**Cần kiểm tra:** tên thread, call stack, queue length, active threads, pending tasks, business logs và tiến độ theo correlation ID.

### 9.2. “BLOCKED nghĩa là JVM deadlock”

`BLOCKED` chỉ là chờ monitor; contended monitor trong thời gian ngắn là bình thường. Deadlock cần **vòng chờ**: A giữ monitor X đợi Y; B giữ Y đợi X, và không ai tiến triển. Một thread owner giữ lock lâu do I/O cũng làm nhiều BLOCKED nhưng không nhất thiết là cycle/deadlock.

**Cần kiểm tra:** owner stack, monitor identity, lock order, nhiều dumps, `ThreadMXBean.findDeadlockedThreads()` hoặc công cụ deadlock detection phù hợp. Không lầm contention với deadlock.

### 9.3. “RUNNABLE = đang chiếm CPU 100%”

Một RUNNABLE có thể ở native socket read/OS wait. Muốn kết luận CPU hotspot cần **per-thread CPU measurement** cộng stack sampling. Chỉ xem state line không đủ.

### 9.4. “TIMED_WAITING tức là sắp thoát”

Một thread có thể `sleep(60_000)`; sau timeout lại sleep tiếp. Nó có thể đang giữ một monitor hoặc đang chờ dependency với deadline rất dài. Không đủ bằng chứng để gọi là bình thường chỉ từ timed state.

### 9.5. “Thread có cùng tên là cùng request”

Thread pools dùng tên như `http-nio-8080-exec-7` cho **nhiều requests tuần tự**; một request có thể đi qua nhiều workers và services. Khi cần nối timeline, dùng **correlation/trace ID**, timestamp và PID/start time; thread name chỉ là thông tin thực thi.

### 9.6. “Có tên lock trong dump là đã biết nguyên nhân”

`- waiting to lock <0x...>` xác định monitor/đối tượng đang đợi trong snapshot, nhưng **nguyên nhân** có thể là owner đi làm I/O, critical section lớn, thread starvation hoặc lock order. Cần tìm owner và code path, không chỉ địa chỉ hex.

### 9.7. “Một snapshot đủ để xác nhận treo”

Thread dump là **ảnh chụp thời điểm**. Một WAITING kéo dài 50 ms có thể bình thường; một RUNNABLE cùng frame trong 10 dumps cộng CPU cao mới gợi ý loop. Cần so **thời gian, tiến độ và resources**, không đọc một hình như video.

## 10. Phân biệt lock contention, starvation, deadlock và I/O wait

| Tình huống | Dấu hiệu có thể thấy | Bước điều tra tiếp |
| --- | --- | --- |
| **Intrinsic monitor contention** | Nhiều BLOCKED cùng `waiting to lock`; owner giữ monitor | Tìm owner, giảm critical section, tránh I/O khi giữ monitor |
| **Java monitor deadlock** | Vòng owner/waiter giữa nhiều monitors; không tiến triển | Dùng deadlock detection và lock graph; sửa lock order |
| **Ownable synchronizer contention** | WAITING parking ở AQS/ReentrantLock | Dùng `Thread.print -l`, owner info, timing |
| **Thread pool starvation** | Request WAITING ở Future/join; không còn worker chạy queued task | Xem pool active/queue, dependency giữa task, tránh nested blocking |
| **Native I/O wait** | RUNNABLE hoặc state khác tùy stack/JVM; frame native socket/file | OS/JFR I/O events, timeout, downstream latency |
| **Backoff/polling** | TIMED_WAITING trong sleep/parkNanos | Xem retries, cadence, rate và tổng thời gian |
| **CPU hot loop** | RUNNABLE liên tục + OS thread CPU tăng | Profiler/JFR, CPU time, stack changes |
| **Healthy idle pool** | WAITING trong queue take/getTask và queue rỗng | Xác nhận throughput/metrics và job queue |

Các tình huống có thể **đồng thời tồn tại**: pool starvation gây request WAITING, trong khi worker gốc bị BLOCKED vào monitor do một thread khác RUNNABLE đang giữ lock. Phân tích **chuỗi phụ thuộc** sẽ giúp tìm nút nghẽn đầu tiên.

## 11. Quy trình chẩn đoán production theo từng bước

**Bước 1 — Xác định mục tiêu và triệu chứng.** Ghi service, môi trường, version, host/container, PID JVM, thời điểm bắt đầu, symptom (CPU cao, latency, no progress, timeout), các chỉ số throughput/queue/GC. Không chạy nhiều lệnh chẩn đoán trên sai PID.

**Bước 2 — Thu vài thread dumps có timestamp.** Lấy đủ để so sự thay đổi nhưng không quá dày làm tăng overhead hoặc lấp file. `Thread.print` Impact Medium, phụ thuộc số lượng threads. Nếu JVM không attach, dùng cơ chế quản trị được hỗ trợ và ghi rõ hạn chế.

**Bước 3 — Gom theo stack pattern và state.** Đừng chỉ đếm `RUNNABLE/BLOCKED/WAITING`; nhóm theo top frames và business operation. Phân biệt framework worker idle với request-processing threads.

**Bước 4 — Lập quan hệ waiting/owner.** Với BLOCKED đọc `waiting to lock`; tìm `locked` ở thread khác hoặc `lockOwnerName/Id`. Với WAITING đọc `Object.wait`, `Condition.await`, `LockSupport.park`, `Future.get`, `join` hoặc queue. Với TIMED_WAITING xem timeout/backoff. Với RUNNABLE xem CPU/I/O.

**Bước 5 — Đối chiếu tiến độ.** Một lock owner có hoàn tất công việc không? Queue có được rút không? Trace có tiến triển không? CPU time nào tăng? Memory/GC có tạo pause dài? Nếu nhiều snapshots cùng pattern, có thể cần JFR/profiler và service metrics.

**Bước 6 — Ưu tiên nguyên nhân theo bằng chứng.** Ví dụ “12 request threads BLOCKED cùng monitor X, owner giữ X trong một call DB kéo dài” là giả thuyết mạnh hơn “nhiều BLOCKED nên JVM hỏng”. Nếu owner chỉ chờ 1 ms, kiểm tra nguyên nhân khác.

**Bước 7 — Thử sửa trong môi trường kiểm chứng.** Thu hẹp synchronized section, tách blocking call, fix lock ordering, điều chỉnh pool/queue, deadline/backpressure, tránh nested wait. Đo lại p95/p99, throughput, CPU, số blocked threads và kết quả nghiệp vụ.

**Bước 8 — Giữ chứng cứ an toàn.** Lưu snapshots có timestamp, PID/start time, JDK version, lệnh thu thập, selected stacks và metrics; redact thông tin nhạy cảm. Không gửi dump nguyên bản lên nguồn công khai.

## 12. Bài tập đọc và giải thích trạng thái

### Bài tập A — Hai threads trên cùng monitor

~~~text
A: TIMED_WAITING at Thread.sleep
   - locked <0xABCD>
B: BLOCKED
   - waiting to lock <0xABCD>
~~~

**Giải thích:** A giữ monitor trong lúc ngủ, B đợi. Điều cần xem là tại sao A sleep trong critical section và nó kéo dài bao lâu. B `BLOCKED` không tự chứng minh deadlock vì A có thể thức dậy và nhả monitor.

### Bài tập B — Pool workers chờ task

~~~text
worker-1 WAITING at LinkedBlockingQueue.take
worker-2 WAITING at LinkedBlockingQueue.take
queue_size=0
processed_requests increasing
~~~

**Giải thích:** có thể là pool idle bình thường. Không bắt đầu tối ưu synchronization khi chưa thấy vấn đề.

### Bài tập C — Nhiều request threads chờ Future

~~~text
request-1 WAITING at CompletableFuture.join
request-2 WAITING at CompletableFuture.join
async-worker-1 WAITING at CompletableFuture.join
task_queue_size=128
active_workers=1
~~~

**Giải thích:** nghi starvation hoặc chuỗi task phụ thuộc nhau. Cần biết task mà `async-worker-1` đang chờ có nằm trong chính queue không; thông số trên chưa đủ khẳng định deadlock.

### Bài tập D — RUNNABLE trong native read

~~~text
network-worker RUNNABLE at SocketDispatcher.read0(Native Method)
cpu_delta_ms approximately 0 over sample interval
downstream p99 high
~~~

**Giải thích:** CPU không tăng, native I/O có thể đang đợi data; ưu tiên phân tích network/downstream timeout thay vì “CPU loop”. Trạng thái native phụ thuộc implementation, nên kết hợp OS/JFR.

### Bài tập E — Scheduler timed waiting

~~~text
retry-timer TIMED_WAITING at Thread.sleep
retry_count increasing quickly
error_rate high
~~~

**Giải thích:** một TIMED_WAITING riêng lẻ không phải lỗi, nhưng tổng thể có thể là retry storm; xem cấu hình backoff, jitter, max attempts và circuit breaker.

## 13. Checklist cuối bài

Khi nhìn thấy một thread dump, hỏi theo thứ tự:

1. **Đúng JVM chưa?** PID, process start, Java vendor/version, container namespace và thời điểm.
2. **Tên và ID nào?** Thread name, Java thread ID, native `nid` nếu có; không trộn với `tid=0x...` hay request ID.
3. **State thật là gì?** Đọc dòng `java.lang.Thread.State`, không chỉ chữ “waiting” ở header.
4. **RUNNABLE có dùng CPU không?** So per-thread CPU, sampling và native/Java frames.
5. **BLOCKED đợi intrinsic monitor nào?** `waiting to lock`, owner là ai, owner đang làm gì?
6. **WAITING đợi điều kiện nào?** Future, queue, park, join hay Object.wait? Có thread/event nào đánh thức?
7. **TIMED_WAITING có timeout/backoff hợp lý không?** Có đang giữ monitor? Có retry lặp và deadline quá dài?
8. **Các snapshots có tiến triển không?** So state/frames/lock ownership với logs và metrics.
9. **Có thể là contention, starvation, deadlock, I/O wait, CPU loop hay idle hợp lệ?** Đừng chẩn đoán theo enum một mình.
10. **Hành động sửa có bằng chứng không?** Tránh thay đổi thread pool/GC/timeout ngẫu nhiên mà không kiểm chứng.

**Ghi nhớ ngắn:** **RUNNABLE** là có thể thực thi trong JVM (không nhất thiết đang ăn CPU); **BLOCKED** là đợi monitor của `synchronized`; **WAITING** là đợi không có timeout; **TIMED_WAITING** là đợi có giới hạn thời gian. Muốn kết luận thread bị treo hay hệ thống nghẽn, phải đọc **stack frames, lock owner, tín hiệu đánh thức, timeline và resource metrics**, tốt nhất qua nhiều dumps.

### Tài liệu tham khảo

- Oracle Java SE 17, `Thread.State`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.State.html
- Oracle Java SE 17, `ThreadInfo`: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadInfo.html
- Oracle Java SE 17, `ThreadMXBean`: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html
- Oracle JDK 17, `jcmd` và `Thread.print`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
- Oracle JDK 17, *Troubleshoot Process Hangs and Loops*: https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshoot-process-hangs-and-loops.html

Các mẫu dump có ghi “minh họa” không phải stdout từ một PID nhất định. Hãy luôn ưu tiên bản dump thực tế của JVM cần điều tra, cùng với timestamps, phiên bản Java và bằng chứng vận hành.