# 8.8. Phân biệt thread đang đợi công việc bình thường với thread đang chặn xử lý

Một thread dump Java có thể chứa hàng chục hoặc hàng trăm thread ở `WAITING` hay `TIMED_WAITING` mà ứng dụng vẫn hoạt động tốt. Worker của executor thường **chờ công việc mới**; scheduler chờ đúng thời điểm chạy; consumer chờ queue có dữ liệu. Nhưng một request đã nhận có thể đang **chờ kết quả không bao giờ đến**, chiếm hết worker hoặc tài nguyên khiến các request khác không tiến triển. Hai trường hợp đôi khi cùng hiển thị `WAITING (parking)`.

Bài học thuộc **8. Thread dump** này giúp trả lời: **thread đang đợi việc theo đúng thiết kế, hay đang giữ/cản một công việc đáng lẽ phải hoàn thành?** Câu trả lời phải kết hợp **vai trò thread, đầy đủ call stack, điều kiện để thức dậy, owner/producer, queue và số liệu tiến độ qua nhiều thời điểm**, không suy từ một dòng trạng thái.

Sau bài học, bạn sẽ nhận diện idle stack như `ThreadPoolExecutor.getTask`, hiểu các wait trong handler như `Future.get()`, phân biệt monitor contention với starvation, dùng `jcmd` và `ThreadMXBean` có kiểm soát, và chạy ví dụ Java 17 có một worker WAITING bình thường cùng một worker BLOCKED thực sự cản tiến độ.

## 1. Trạng thái thread và tác động nghiệp vụ là hai trục khác nhau

Trong Java 17, `Thread.State` có sáu giá trị: `NEW`, `RUNNABLE`, `BLOCKED`, `WAITING`, `TIMED_WAITING`, `TERMINATED`. Bốn trạng thái thường cần phân tích khi điều tra service không tiến triển:

| Java state | Ý nghĩa của JVM | Ví dụ | Không thể kết luận chỉ từ state |
| --- | --- | --- | --- |
| **RUNNABLE** | Thread đang có thể thực thi trong JVM; có thể đợi tài nguyên OS | Java code, native socket read, loop | Không chắc đang sử dụng CPU hoặc xử lý hữu ích |
| **BLOCKED** | Chờ lấy/reenter một **intrinsic monitor** | Thread khác giữ `synchronized(lock)` | Không tự động là deadlock |
| **WAITING** | Chờ hành động của thread/event khác, không có timeout ở lời gọi hiện tại | `Object.wait()`, `Thread.join()`, `LockSupport.park()` | Không có nghĩa chờ “mãi” hay chắc chắn lỗi |
| **TIMED_WAITING** | Chờ với khoảng thời gian giới hạn | `Thread.sleep`, timed wait/join/park | Không đảm bảo request hoàn thành trước SLO |

`NEW` là chưa start, `TERMINATED` là đã kết thúc; thread dump của những threads đang sống có thể không có những thread này. Java state không phải bản sao OS thread state.

**Quan trọng:** `Thread.State.BLOCKED` cụ thể là đang chờ intrinsic monitor. Một thread chờ `ReentrantLock`, `Semaphore`, `Future`, connection pool hoặc native I/O **không nhất thiết** mang state BLOCKED. Khi nói “thread đang chặn xử lý”, đó là **kết luận ở tầng hệ thống**, không phải nhãn của enum.

Ba câu hỏi bắt buộc:

1. **Thread đang làm vai trò gì?** Worker rảnh, request handler, scheduled job, consumer, event-loop hay background helper?
2. **Nó đang chờ điều kiện nào?** Task queue, future completion, monitor, latch, permit, timeout, network event?
3. **Chỗ chờ đó có làm chậm công việc có thật không?** Có request quá hạn, backlog tăng, completed tasks dừng hoặc dependency không được chạy không?

Một worker idle `WAITING` 10 phút vẫn có thể khỏe mạnh nếu không có task. Một request `WAITING` 30 giây có thể là sự cố nghiêm trọng khi SLO chỉ 2 giây.

## 2. Hai vị trí WAITING có ý nghĩa khác nhau

Mô hình vòng đời một executor worker:

~~~text
Worker được tạo
      |
      v
Lấy task từ work queue
      |
      +-- Chưa có task: chờ trong take()/poll()
      |    Đây thường là idle bình thường
      |
      +-- Đã có task: chạy handler
           |
           +-- Xử lý xong, tăng completed count
           |
           +-- Chờ Future/lock/DB/IO bên trong task
                Nếu vượt deadline hoặc không có producer,
                worker có thể cản tiến độ
~~~

| Câu hỏi | Idle worker | Worker có khả năng cản xử lý |
| --- | --- | --- |
| Đã nhận task chưa? | Chưa, đang chờ lấy task mới | Có, đang ở trong handler hoặc transaction |
| Top call path | `ThreadPoolExecutor.getTask` → `BlockingQueue.take` | `OrderService.process` → `Future.get/join` |
| Queue của đúng executor | Không có backlog, hoặc đã được xử lý | Queue tăng/oldest task age tăng |
| Completion counter | Tăng khi có công việc | Đứng yên dù có công việc sẵn |
| Điều kiện đánh thức | Có task mới hoặc timer tới hạn | Producer, lock owner, RPC, signal hoặc permit |
| Tác động | SLO/throughput vẫn tốt | Timeouts, inflight requests, p99 tăng |

Đọc trạng thái mà **không đọc các frame phía dưới** là sai lầm phổ biến: `LockSupport.park()` chỉ mô tả cách thread đợi, không cho biết nó đợi **công việc mới** hay **kết quả để hoàn tất công việc hiện tại**.

## 3. Những pattern chờ công việc bình thường

### 3.1. `ThreadPoolExecutor.getTask` trên queue rỗng

Với fixed executor của Java 17, worker thường chờ trong queue lấy task mới. Stack HotSpot **minh họa**, có thể khác theo version:

~~~text
"order-pool-3" #48 ...
   java.lang.Thread.State: WAITING (parking)
        at jdk.internal.misc.Unsafe.park(Native Method)
        at java.util.concurrent.locks.LockSupport.park(LockSupport.java:...)
        at java.util.concurrent.locks.AbstractQueuedSynchronizer$ConditionObject.await(...)
        at java.util.concurrent.LinkedBlockingQueue.take(LinkedBlockingQueue.java:...)
        at java.util.concurrent.ThreadPoolExecutor.getTask(ThreadPoolExecutor.java:...)
        at java.util.concurrent.ThreadPoolExecutor.runWorker(ThreadPoolExecutor.java:...)
~~~

Diễn giải: worker nằm ở `getTask`, **chưa có task tiếp theo**. Khi queue đúng của pool này rỗng, completed tasks ổn định theo nhu cầu và request latency bình thường, đây là idle khỏe mạnh.

Không cứng nhắc yêu cầu state phải WAITING: với `ThreadPoolExecutor` dùng `SynchronousQueue`, `ArrayBlockingQueue`, core-thread timeout hoặc `poll(timeout)`, worker có thể ở `TIMED_WAITING`/frame khác nhưng vẫn là idle.

**Đặc biệt:** một queue rỗng chỉ chứng minh queue đó rỗng. Công việc có thể bị giữ ở producer, ở upstream queue, bị rejected hoặc gửi nhầm executor. Vì vậy vẫn cần kiểm tra flow end-to-end.

### 3.2. Scheduler đợi tới thời điểm chạy

`ScheduledThreadPoolExecutor` dùng delayed work queue để chờ deadline. Một worker có thể ở `TIMED_WAITING` trong `LockSupport.parkNanos` hoặc `DelayedWorkQueue.take`, cũng có thể WAITING khi chưa có task.

~~~text
"scheduler-1" ...
   java.lang.Thread.State: TIMED_WAITING (parking)
        at jdk.internal.misc.Unsafe.park(Native Method)
        at java.util.concurrent.locks.LockSupport.parkNanos(...)
        at java.util.concurrent.ScheduledThreadPoolExecutor$DelayedWorkQueue.take(...)
        at java.util.concurrent.ThreadPoolExecutor.getTask(...)
~~~

Đây là pattern định hướng, không phải stdout cố định. Nếu bây giờ 09:59 và job kế tiếp lúc 10:00, scheduler chờ là hợp lệ. Nếu 10:05 job chưa chạy, mới điều tra backlog, worker đang thực thi job quá lâu, exception, shutdown, rejection hoặc clock.

### 3.3. ForkJoin workers và background consumers

- `ForkJoinPool` workers có thể park khi không có task, nhưng implementation method names thay đổi theo JDK. Xem active/running, queued submissions/tasks và work-stealing statistics.
- Consumer trong `BlockingQueue.take` khi queue không có event là bình thường. Nếu producer không phát event, **lỗi có thể ở upstream**.
- Network selector/acceptor có thể chờ I/O readiness. Với native I/O, Java state đôi khi là `RUNNABLE`, không phải WAITING.
- Metrics writer, cleaner, background poller, health timer có thể sleep hoặc wait theo lịch; cần đối chiếu job deadline.

Ví dụ consumer logic (đoạn **minh họa**, chưa có imports và catch `InterruptedException`):

~~~java
while (!Thread.currentThread().isInterrupted()) {
    Event event = queue.take();
    handle(event);
}
~~~

Khi queue rỗng, thay `take()` bằng busy-loop chỉ khiến CPU tăng mà không có dữ liệu mới. Nếu service thiếu event, truy producer, transport, retry, routing và message broker.

## 4. Những kiểu chờ có thể thực sự cản tiến độ

### 4.1. Request handler chờ một `Future`

Đoạn logic **minh họa không độc lập**:

~~~java
CompletableFuture<Result> result =
        CompletableFuture.supplyAsync(this::fetchResult, executor);
return result.join();
~~~

Nếu task producer có capacity và hoàn thành nhanh, wait có thể đúng theo kiến trúc. Nếu producer không thể chạy, hoặc request chờ quá deadline, handler đã giữ một slot để chờ mà không tiến triển.

Thread dump minh họa:

~~~text
"http-worker-7" ...
   java.lang.Thread.State: WAITING (parking)
        at jdk.internal.misc.Unsafe.park(Native Method)
        at java.util.concurrent.locks.LockSupport.park(...)
        at java.util.concurrent.CompletableFuture$Signaller.block(...)
        at java.util.concurrent.CompletableFuture.join(...)
        at com.example.CheckoutController.checkout(CheckoutController.java:...)
~~~

Tìm producer của future: task được submit đến pool nào, pool có worker trống không, callback exception hay cancellation có được propagate, downstream call có deadline không? Một lần dump `WAITING` chưa đủ kết luận lỗi; cần event timeline, request age và completion metrics.

### 4.2. Monitor contention, owner đang đợi nhưng vẫn giữ lock

Hai threads có thể hiển thị:

~~~text
"request-8" ...
   java.lang.Thread.State: BLOCKED (on object monitor)
        at com.example.Repository.update(Repository.java:91)
        - waiting to lock <0x00000000AAAABBBB> (a java.lang.Object)

"request-3" ...
   java.lang.Thread.State: TIMED_WAITING (sleeping)
        at java.lang.Thread.sleep(Native Method)
        at com.example.Repository.update(Repository.java:80)
        - locked <0x00000000AAAABBBB> (a java.lang.Object)
~~~

Địa chỉ, lớp, số dòng và header chỉ là **giá trị minh họa**. Thread owner ở TIMED_WAITING nhưng đang giữ monitor; request-8 BLOCKED nên không thể xử lý.

Hãy tìm monitor ID giống nhau ở `waiting to lock` và `locked`, stack của owner, thời gian giữ lock, số waiters và progress qua nhiều dumps. Đây là **contention**; nếu owner có thể release, chưa phải deadlock. Deadlock đòi quan hệ chờ vòng hoặc một dependency không thể thỏa.

### 4.3. Chờ `ReentrantLock` hoặc connection pool có thể là WAITING

Thread chờ `ReentrantLock.lock()` thường park trong `AbstractQueuedSynchronizer`, nên có thể ở `WAITING`. `Semaphore.acquire`, `Condition.await`, `CountDownLatch.await`, lấy DB connection hoặc chờ HTTP connection cũng có thể dùng park/wait.

Không được chỉ lọc `BLOCKED` để tìm bottleneck. Xem frame **ứng dụng** dưới `LockSupport.park`, resource owner và metrics của pool: active, idle, pending acquire, timeout, queue age. Một worker WAITING do `LinkedBlockingQueue.take` khác hoàn toàn WAITING do `DataSource.getConnection` khi pool cạn.

### 4.4. RUNNABLE vẫn có thể chặn vì native I/O

Một thread ở native socket/file/DNS/TLS wait có thể hiển thị `RUNNABLE`, tùy JDK/OS. Nếu thread đó là event-loop, một blocking call có thể ngăn nhiều requests được xử lý.

Đối chiếu per-thread CPU:
- RUNNABLE + CPU tăng liên tục + Java loop không progress → nghi CPU-bound.
- RUNNABLE + CPU thấp + socket native read + remote latency cao → nghi chờ I/O.
- WAITING ở Future.get + producer queue có backlog → nghi dependency/capacity.

`Thread.State` không trực tiếp đo CPU usage hoặc tác động SLO.

### 4.5. Latch và condition không có ai đánh thức

Khi thấy `Object.wait`, `Condition.await`, `LockSupport.park`, `Thread.join` hoặc `CountDownLatch.await`, hỏi:
1. Điều kiện thoát wait là gì?
2. Thread/producer nào phải gọi `notify/signal/unpark/countDown/complete`?
3. Producer có còn chạy/được schedule không?
4. Có exception/cancellation làm mất signal không?
5. Có timeout, fallback và rollback đúng contract không?

`Object.wait()` **nhả monitor của object được gọi wait** khi chờ và phải reacquire để tiếp tục. `Thread.sleep()` và `CountDownLatch.await()` **không tự nhả monitor ngoại vi đang giữ**. Thread WAITING vẫn có thể là chủ của lock làm thread khác BLOCKED.

## 5. Thread-pool starvation: tất cả đều WAITING nhưng không phải idle

Một trường hợp rất đáng nhận diện:

~~~text
Single-thread executor có Worker-1
    |
    Worker-1 nhận OuterTask
    |
    OuterTask submit InnerTask vào cùng executor
    |
    OuterTask gọi Future.get() chờ InnerTask
    |
    InnerTask nằm trong queue
    |
    Worker-1 không rảnh để chạy InnerTask
    |
    Công việc không thể hoàn thành nếu không hủy/đổi thiết kế
~~~

Ví dụ **chỉ để đọc** (không độc lập, có nguy cơ chờ vô hạn, không chạy trên service thật):

~~~java
// executor là Executors.newSingleThreadExecutor().
Future<String> outer = executor.submit(() -> {
    Future<String> inner = executor.submit(() -> "done");
    return inner.get();
});
~~~

Trong dump, worker có thể `WAITING` tại `FutureTask.get`, pool active=1, queue=1, completed không tăng. Không có Java monitor `BLOCKED`, deadlock detector có thể trả `null` vì nó không phát hiện mọi dependency trên future/executor.

**Đây là starvation**: task tồn tại, nhưng worker duy nhất đã chiếm chỗ để đợi chính task nằm trong queue. Sửa bằng async continuation/composition, tránh nested blocking, phân tách tài nguyên hợp lý hoặc thiết kế timeout/cancellation; tăng pool size tùy tiện chỉ che một cấu hình và không giải quyết chu trình phụ thuộc tổng quát.

`ThreadMXBean.findDeadlockedThreads()` tìm vòng chờ trên object monitors/ownable synchronizers (khi được hỗ trợ), không bảo đảm tìm mọi Future starvation, remote wait hay business deadlock.

## 6. Thu và phân tích thread dump từng bước

### 6.1. Chọn đúng JVM/PID

Với JDK 17 HotSpot, ví dụ:

~~~bash
jcmd -l
jcmd 12345 help Thread.print
jcmd 12345 Thread.print -l
~~~

`12345` là PID **minh họa**, phải thay bằng PID đã xác minh của service và đúng PID namespace. `-l` của `Thread.print` lấy thêm thông tin `java.util.concurrent` locks nếu được hỗ trợ; nó khác `jcmd -l` liệt kê JVM. Có thể dùng `jstack 12345` ở JDK/OS hỗ trợ.

Thread dump có chi phí phụ thuộc số threads, nên thu vài snapshots có timestamp **khi đang có triệu chứng**, không liên tục không giới hạn. Nếu không attach được, kiểm tra quyền user/group, JVM đã thoát, container namespace và cấu hình attach.

### 6.2. Đọc cả header, state và call chain

~~~text
"pool-4-thread-1" #59 ... tid=0x00007f... nid=0x1a2b waiting on condition
   java.lang.Thread.State: WAITING (parking)
        at jdk.internal.misc.Unsafe.park(Native Method)
        at java.util.concurrent.locks.LockSupport.park(...)
        at java.util.concurrent.locks.AbstractQueuedSynchronizer$ConditionObject.await(...)
        at java.util.concurrent.LinkedBlockingQueue.take(...)
        at java.util.concurrent.ThreadPoolExecutor.getTask(...)
        at java.util.concurrent.ThreadPoolExecutor.runWorker(...)
~~~

- Thread name giúp biết executor nhưng không phải request ID.
- `#59` trong một số HotSpot headers là Java thread ID.
- `tid=0x...` thường là VM thread pointer/ID nội bộ, không tự đồng nhất Linux TID.
- `nid=0x...` là native ID trong HotSpot, thường hex, cần đúng OS/PID namespace để đối chiếu CPU.
- Dòng `java.lang.Thread.State` là enum snapshot; chữ “waiting” ở header chưa chắc trùng enum.
- Top frames mô tả cơ chế park/monitor, còn **frames phía dưới** cho biết đang lấy task mới hay chờ bên trong handler.

Đọc stack từ dưới lên tìm caller nghiệp vụ và từ trên xuống tìm primitive. Không kết luận chỉ vì xuất hiện `Unsafe.park`.

### 6.3. Xem owner và quan hệ chờ

Trong dump có thể có các annotations:

~~~text
- waiting to lock <0x0000000011112222> (a java.lang.Object)
- locked <0x0000000011112222> (a java.lang.Object)
- parking to wait for <0x0000000033334444> (...)
~~~

Đối với `synchronized`, tìm owner đang `locked` cùng monitor. Với `ReentrantLock`/ownable synchronizers, xem lock information khi tool/runtime cung cấp. `parking to wait for` có thể chỉ chờ queue trống; phải xem các frames bên dưới. Không phải mọi dump đều có cùng định dạng/annotations.

### 6.4. So nhiều snapshots và tiến độ

Tại thời điểm T0 (giả định):

~~~text
worker-A WAITING at Future.get
worker-B WAITING at queue.take
queue_depth=4; completed_tasks=1000
~~~

Năm giây sau:

~~~text
worker-A WAITING at same Future.get
worker-B WAITING at queue.take
queue_depth=27; completed_tasks=1000
~~~

Điều này gợi ý một luồng **không tiến triển**, nhưng chưa thể quy worker-B là nguyên nhân nếu queue_depth thuộc executor khác. Cần xem task producer, oldest age, request deadlines và stack owner. Một snapshot không phải video; cùng stack qua nhiều mốc + backlog/timeouts mới giúp đánh giá chỗ chờ có tác động.

## 7. Số liệu đối chiếu quan trọng

| Nguồn | Metrics | Mục đích |
| --- | --- | --- |
| Executor | `getPoolSize()`, `getActiveCount()` | Biết pool và worker xử lý task (số ước lượng) |
| Executor | `getQueue().size()`, oldest task age | Có backlog đang chờ xử lý? |
| Executor | `getCompletedTaskCount()`, task rejected count | Task có hoàn thành; có bị reject? |
| Service | inflight requests, throughput, timeout, p95/p99 | Tác động thực tế tới người dùng |
| Dependency | DB pool active/idle/pending, HTTP latency, remote errors | Wait vì resource/downstream? |
| JVM/OS | thread CPU, GC pauses, RSS, FD count | CPU loop, I/O wait hay runtime pressure |
| Logs/traces | requestId, traceId, event start/end, duration | Điểm nào trong workflow không tiến triển |

Các API về pool thường trả **ước lượng ở thời điểm gọi**. `Executors.newSingleThreadExecutor()` trả wrapper `ExecutorService`, không đảm bảo expose tất cả `ThreadPoolExecutor` getter trực tiếp; instrument executor/framework phù hợp.

### `ThreadMXBean` bổ trợ, không thay tiến độ nghiệp vụ

`ManagementFactory.getThreadMXBean()` cung cấp `ThreadInfo`, stack và thông tin synchronization khi JVM hỗ trợ. Đoạn sau là **minh họa**, cần imports bao quanh:

~~~java
ThreadMXBean bean = ManagementFactory.getThreadMXBean();
ThreadInfo[] infos = bean.dumpAllThreads(true, true);
for (ThreadInfo info : infos) {
    System.out.printf(
            "name=%s id=%d state=%s lock=%s owner=%s%n",
            info.getThreadName(),
            info.getThreadId(),
            info.getThreadState(),
            info.getLockName(),
            info.getLockOwnerName());
}
~~~

Kiểm tra `isObjectMonitorUsageSupported()` và `isSynchronizerUsageSupported()` trước khi yêu cầu thông tin tương ứng; thu dump có chi phí. `getBlockedTime()`/`getWaitedTime()` cần thread contention monitoring được bật/hỗ trợ, thường mặc định tắt và có thể trả `-1`. Đừng bật `setThreadContentionMonitoringEnabled(true)` tùy tiện trong production vì overhead. Per-thread CPU time cũng có support/enablement riêng.

## 8. Thực hành Java 17+: WAITING đúng và BLOCKED cản tiến độ

Chương trình dùng JDK 17+ và không cần thư viện ngoài. Nó tạo hai tình huống:
1. `idle-queue-worker` trong `newSingleThreadExecutor`: chạy xong task rỗng rồi **WAITING** để lấy task mới từ queue. Không có backlog, đây là idle khỏe mạnh.
2. `lock-owner` giữ một monitor; `blocked-worker` đã được giao việc nhưng chờ monitor nên **BLOCKED**. Chỉ khi owner nhả monitor thì work mới hoàn tất.

Main thread chờ cho đến khi từng state thực sự được quan sát rồi mới in, nên giảm lỗi race khi lấy snapshot quá sớm. Chỉ main in stdout để không xen kẽ.

Tạo tệp **IdleVsBlockedDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public final class IdleVsBlockedDemo {
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
        AtomicReference<Thread> idleWorker = new AtomicReference<>();
        ExecutorService idlePool =
                Executors.newSingleThreadExecutor(task -> {
                    Thread t = new Thread(task, "idle-queue-worker");
                    idleWorker.set(t);
                    return t;
                });

        Object monitor = new Object();
        CountDownLatch ownerHolding = new CountDownLatch(1);
        CountDownLatch releaseOwner = new CountDownLatch(1);
        CountDownLatch workCompleted = new CountDownLatch(1);

        Thread owner = new Thread(() -> {
            synchronized (monitor) {
                ownerHolding.countDown();
                try {
                    releaseOwner.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            }
        }, "lock-owner");

        Thread blockedWorker = new Thread(() -> {
            synchronized (monitor) {
                workCompleted.countDown();
            }
        }, "blocked-worker");

        try {
            idlePool.submit(() -> { }).get(5, TimeUnit.SECONDS);

            owner.start();
            if (!ownerHolding.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Owner did not lock");
            }
            blockedWorker.start();

            Thread.State idle = awaitState(
                    idleWorker.get(), Thread.State.WAITING);
            Thread.State blocked = awaitState(
                    blockedWorker, Thread.State.BLOCKED);

            System.out.println("idle_worker=" + idle);
            System.out.println("blocked_worker=" + blocked);
            System.out.println(
                    "completed_before_release="
                    + (workCompleted.getCount() == 0));

            releaseOwner.countDown();
            if (!workCompleted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Work did not complete");
            }
            System.out.println(
                    "completed_after_release="
                    + (workCompleted.getCount() == 0));
        } finally {
            releaseOwner.countDown();
            owner.interrupt();
            blockedWorker.interrupt();
            idlePool.shutdownNow();
            owner.join(2_000L);
            blockedWorker.join(2_000L);
            idlePool.awaitTermination(2, TimeUnit.SECONDS);
        }
    }
}
~~~

Biên dịch và chạy trong thư mục chứa file:

~~~bash
javac IdleVsBlockedDemo.java
java IdleVsBlockedDemo
~~~

**Stdout chính xác trong môi trường scheduling bình thường:**

~~~text
idle_worker=WAITING
blocked_worker=BLOCKED
completed_before_release=false
completed_after_release=true
~~~

**Giải thích từng dòng:**
- Task rỗng đã xong; worker của fixed one-thread executor đợi task tiếp theo. `WAITING` tại queue `take()` là bình thường.
- `ownerHolding` bảo đảm owner đã vào `synchronized` trước khi blocked worker chạy. Worker chờ monitor, do đó `BLOCKED`.
- Trước `releaseOwner.countDown()`, `workCompleted` vẫn là 1; kết quả là `false`.
- Sau release, owner thoát monitor; blocked worker vào critical section và countDown; kết quả thành `true`.
- `finally` release, interrupt và shutdown để tránh để lại worker kẹt.

**Điểm then chốt:** `lock-owner` ở `WAITING` trong `CountDownLatch.await()` nhưng **vẫn giữ monitor ngoại vi**, vì latch await không nhả monitor. Đọc state của owner riêng lẻ không cho biết tác động đến waiter; phải đọc owner/waiter lock annotations.

**Giới hạn:** `Thread.getState()` là snapshot, có thể đổi ngay sau khi đọc. Poll deadline 10 giây giảm race nhưng trong môi trường quá tải hoặc không thể tạo threads, `awaitState` có thể throw `IllegalStateException`; bốn dòng trên là output kỳ vọng trong môi trường Java 17 bình thường.

Để thử `jcmd` khi demo đang chờ, có thể thêm một câu `Thread.sleep(10_000L);` **ngay sau khi in `completed_before_release` và trước `releaseOwner.countDown()`**, rồi chạy từ terminal khác:

~~~bash
jcmd -l
jcmd 12345 Thread.print -l
~~~

Thay `12345` bằng PID thực, không giữ monitor/sleep kiểu demo trong production.

## 9. Ma trận tình huống thực tế

| Tình huống | Dấu hiệu | Nhận định |
| --- | --- | --- |
| Pool 20 workers `WAITING` ở `getTask`, queue 0, throughput bình thường | Không có việc đang đợi trong queue đó | Idle hợp lệ, không cần đánh thức |
| Handler `WAITING` tại `CompletableFuture.join`, request quá SLO, task producer chưa chạy | Queue producer tăng, completions đứng | Nghi Future dependency/executor starvation |
| Thread `RUNNABLE` ở native socket read, CPU delta thấp, remote p99 cao | Network call chậm | Nghi I/O wait, không suy CPU loop |
| Owner `TIMED_WAITING` đang `sleep` nhưng `locked <0xABCD>`, nhiều waiters `BLOCKED` cùng monitor | Lock được giữ lâu | Monitor contention, tìm cách giảm critical section |
| Consumer `WAITING` ở `queue.take`, queue 0 nhưng upstream errors tăng | Producer không phát event | Consumer chờ hợp lệ, lỗi ở upstream |
| Pool A rảnh, Pool B có 300 queued tasks và worker chờ Future | Hai executors khác nhau | Phải phân tích đúng pool, không cộng nhầm |
| Single-thread executor active=1, queue=1, worker `WAITING` tại Future.get | Outer đợi Inner trong cùng pool | Starvation/dependency cycle |
| Scheduler `TIMED_WAITING` trước deadline | Task chưa tới giờ | Bình thường; nếu deadline qua lâu thì điều tra |

Các số trong bảng chỉ là giả định minh họa; phải đối chiếu workload, JDK, timestamp và metrics thực tế.

## 10. Những lỗi suy luận phổ biến

- **“WAITING nghĩa là ứng dụng treo.”** Worker chờ task mới thường khỏe mạnh.
- **“RUNNABLE nghĩa là CPU cao.”** Native I/O và OS wait có thể hiện RUNNABLE; đo CPU time.
- **“BLOCKED gồm mọi kiểu chờ.”** Java `BLOCKED` chỉ về intrinsic monitor.
- **“Owner đang WAITING thì không giữ lock.”** Nó có thể await một latch bên trong `synchronized`.
- **“Deadlock detector trả null nghĩa là không có starvation.”** Future/queue/external RPC dependencies nằm ngoài nhiều phép kiểm.
- **“Nhiều WAITING thì phải tăng worker pool.”** Khi traffic thấp, đây có thể là capacity dư; tăng threads còn tốn memory/context switches.
- **“Queue rỗng nghĩa mọi công việc đã hoàn thành.”** Producer có thể chưa dispatch hoặc task bị giữ ở queue khác.
- **“Queue lớn chứng minh mọi WAITING đều bất thường.”** Phải xác định queue của đúng executor.
- **“Một snapshot đủ chứng minh không tiến triển.”** Cần timeline và completion/latency.
- **“Thấy `park` thì sửa `LockSupport`.”** Park chỉ là primitive; bug có thể nằm trong handler, future hoặc producer.
- **“Tăng timeout là giải quyết.”** Timeout dài có thể giữ slot lâu hơn; cần cancellation và thiết kế lại dependency.
- **“Thread name là request ID.”** Pool tái sử dụng thread; dùng correlation/trace ID.
- **“Mọi `TIMED_WAITING` đều vô hại.”** Sleep khi giữ lock hoặc retry storm có thể ảnh hưởng nhiều threads.
- **“Chỉ cần gọi notifyAll để đánh thức.”** Nếu protocol/condition sai, notify không sửa được nguyên nhân.
- **“Không thấy completion log là task chưa chạy.”** Log có thể bị sampled/drop; kiểm tra business state và metrics.

## 11. Playbook chẩn đoán production

1. **Chốt triệu chứng:** service, pod, PID/start time, Java version, thời gian, SLO, request timeout, throughput và error rate.
2. **Lấy vài thread dumps có timestamp** đúng lúc sự cố; không spam `jcmd` trên JVM quá tải.
3. **Phân loại thread theo vai trò:** handler, executor worker, scheduler, selector, consumer, DB pool, JVM helpers.
4. **Đọc call chain đầy đủ:** `getTask/take` chờ task hay `Future.get/join/await` trong handler? Có `waiting to lock`, `locked` hoặc native read không?
5. **Xác định quan hệ phụ thuộc:** task cần kết quả của ai, owner giữ resource gì, producer có khả năng chạy không?
6. **Đo tiến độ:** queue depth/age, active/completed/rejected tasks, inflight, p99, connection pool, GC, thread CPU, dependencies.
7. **So nhiều mốc thời gian:** trạng thái có thay đổi, tasks có hoàn tất, oldest pending age có tăng, trace events có tiếp tục?
8. **Phân biệt loại vấn đề:** healthy idle, contention, starvation, true deadlock, I/O wait, hot CPU loop hay producer outage.
9. **Sửa đúng nguyên nhân:** không block event loop, tránh nested Future trên bounded executor, thu hẹp monitor critical section, xử lý downstream timeout/cancellation, kiểm soát pool/retry.
10. **Đo lại SLO/tiến độ**, không lấy số thread WAITING giảm làm tiêu chí duy nhất.
11. **Lưu chứng cứ an toàn:** dumps có class, path, nội dung nội bộ; che thông tin nhạy cảm và giới hạn quyền truy cập.

**Checklist nhanh trước khi kết luận một thread đang chặn xử lý:** Thread đã nhận task hay chờ task mới? Nó đợi resource nào và ai đánh thức? Có task backlog tại đúng executor không? Có producer/completer còn chạy không? Request đã vượt deadline chưa? Qua nhiều snapshots có tiến độ không? Owner đang giữ monitor/connection/permit nào? CPU/JFR/metrics có hỗ trợ giả thuyết không?

**Ghi nhớ:** `WAITING` ở `ThreadPoolExecutor.getTask` thường là **worker rảnh sẵn sàng nhận việc**, còn `WAITING` ở `Future.get` bên trong handler là **công việc đã nhận đang đợi một kết quả khác**. Chỉ khi xem **full stack, đúng queue/resource, người tạo tín hiệu và tiến độ nghiệp vụ** mới phân biệt được đợi bình thường với chặn xử lý.

### Tài liệu tham khảo

- Oracle Java 17, `Thread.State`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.State.html
- Oracle Java 17, `ThreadPoolExecutor`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
- Oracle Java 17, `ThreadMXBean`: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html
- Oracle Java 17, `ThreadInfo`: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadInfo.html
- Oracle JDK 17, `jcmd` (`Thread.print`): https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html

Các stack snippets và số liệu được ghi là minh họa; method nội bộ, state và thread dump format có thể thay đổi theo JVM/vendor/OS. Khi điều tra, ưu tiên output và timeline thực tế.