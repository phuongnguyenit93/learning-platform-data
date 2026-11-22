# Phát hiện callback bị treo và khóa chết khi tạm dừng tài nguyên

Trong ứng dụng Java dùng CRaC (Coordinated Restore at Checkpoint), các resource như connection pool, HTTP client, scheduler, message consumer và worker thread thường cần được chuẩn bị trước khi JVM tạo checkpoint. CRaC gọi các callback `beforeCheckpoint` để ứng dụng đưa những resource này về trạng thái an toàn; sau khi process được khôi phục, callback `afterRestore` giúp tạo lại hoặc kích hoạt resource.

Một callback bị treo có thể khiến toàn bộ yêu cầu checkpoint không hoàn tất. Một deadlock trong lúc dừng worker có thể làm callback chờ vô hạn, trong khi worker lại chờ lock mà callback đang giữ. Trường hợp nguy hiểm là ứng dụng chỉ ghi một log “checkpoint started”, không có log hoàn tất, và process vẫn tồn tại nhưng không thể tiếp tục phục vụ hoặc checkpoint.

Để chẩn đoán đúng, cần phân biệt **callback chậm**, **callback chờ tài nguyên**, **thread pool không drain**, **lock contention** và **deadlock thực sự**. Cách xử lý hiệu quả là ghi log theo từng callback, đặt deadline hữu hạn, tránh giữ lock khi chờ task kết thúc, lấy thread dump khi có dấu hiệu treo và kiểm tra trạng thái lock bằng `ThreadMXBean`.

## 1. Vòng đời callback và nơi có thể bị treo

Một resource CRaC triển khai interface `org.crac.Resource` có hai callback chính:

- `beforeCheckpoint(Context<? extends Resource> context)`: chuẩn bị resource trước khi JVM được checkpoint.
- `afterRestore(Context<? extends Resource> context)`: khôi phục hoặc tạo lại resource sau khi JVM được restore.

Ví dụ:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class ExampleResource implements Resource {

    public ExampleResource() {
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        // Tạm dừng và đóng resource.
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {
        // Tạo lại hoặc kết nối lại resource.
    }
}
~~~

Callback được thực hiện trong luồng xử lý checkpoint/restore. Nếu callback chờ vô hạn, tiến trình không thể hoàn tất giai đoạn lifecycle tương ứng. Chỉ việc JVM vẫn có PID không chứng minh checkpoint đang tiến triển.

### 1.1. Những vị trí thường bị kẹt trong beforeCheckpoint

Các thao tác sau có thể gây chờ lâu hoặc deadlock:

- Chờ `ExecutorService.awaitTermination()` trong khi task cần lock mà callback đang giữ.
- Gọi `Future.get()` hoặc `CompletableFuture.join()` để chờ công việc được lập lịch trên chính executor vừa bị shutdown.
- Gọi `lock()` hoặc vào `synchronized` trong khi thread khác giữ lock và đang chờ callback.
- Chờ active task count về 0 nhưng task bị block trên database, socket hoặc message broker.
- Đóng connection pool trong khi worker vẫn giữ connection hoặc transaction.
- Chờ HTTP request/handshake không có connect timeout hoặc read timeout.
- Gọi callback của resource khác theo thứ tự ngược với dependency.
- Dùng latch/condition nhưng quên signal trong nhánh exception hoặc cancellation.

### 1.2. Những vị trí thường bị kẹt trong afterRestore

Sau restore, callback có thể bị treo khi:

- Chờ database hoặc service bên ngoài mà không có timeout.
- Chờ secret/config provider phản hồi.
- Tạo lại executor nhưng worker startup chờ một lock đang bị thread khác giữ.
- Chờ một `Future` chỉ được hoàn thành bởi scheduler chưa được resume.
- Khởi động HTTP server trong khi port đã bị process khác chiếm.
- Mở resource theo thứ tự sai khiến dependency chưa hoạt động.
- Chờ readiness hoặc startup state được cập nhật bởi một thread không còn chạy.

Không phải callback nào chạy lâu cũng là deadlock. Ví dụ, database đang khởi động có thể khiến reconnect mất thời gian nhưng vẫn có tiến triển. Chẩn đoán cần quan sát stack trace và sự thay đổi trạng thái qua nhiều lần lấy thread dump.

## 2. Nhận biết callback bị treo qua log và thời lượng

Mỗi callback nên ghi ít nhất ba mốc:

1. Bắt đầu callback.
2. Bắt đầu và kết thúc từng bước quan trọng bên trong callback.
3. Kết thúc callback cùng thời lượng.

Ghi thêm resource name, phase, thread name và checkpoint/restore operation ID nếu hệ thống có correlation ID.

Ví dụ:

~~~text
2026-11-13T07:10:00.010Z INFO  CRaC phase=beforeCheckpoint resource=job-gate event=start thread=main
2026-11-13T07:10:00.012Z INFO  CRaC phase=beforeCheckpoint resource=job-gate step=stop-admission
2026-11-13T07:10:00.015Z INFO  CRaC phase=beforeCheckpoint resource=job-gate step=await-active-tasks active=3
2026-11-13T07:10:20.015Z ERROR CRaC phase=beforeCheckpoint resource=job-gate event=timeout active=1 elapsedMs=20000
~~~

Nếu log chỉ có `event=start` mà không có `event=complete`, cần xác định callback đang chờ ở bước nào. Log theo từng bước giúp thu hẹp phạm vi trước khi lấy thread dump.

### 2.1. Đo thời lượng bằng System.nanoTime()

Dùng monotonic clock để đo elapsed time trong process:

~~~java
long started = System.nanoTime();

try {
    resource.pause();
} finally {
    long elapsedNanos = System.nanoTime() - started;
    logger.info(
            "CRaC callback resource={} elapsedMs={}",
            resourceName,
            elapsedNanos / 1_000_000);
}
~~~

`System.nanoTime()` phù hợp để đo thời lượng vì phép đo không bị sai lệch bởi việc chỉnh giờ hệ thống. Không dùng `System.currentTimeMillis()` để kiểm tra timeout trong callback.

Lưu ý: khối `finally` chỉ chạy khi lời gọi trả về hoặc ném exception. Nếu callback bị kẹt vô hạn, log hoàn tất trong `finally` sẽ không xuất hiện. Vì vậy, cần có log bắt đầu, log theo từng bước và một watchdog bên ngoài hoặc công cụ giám sát thread.

### 2.2. Đặt deadline cho toàn bộ callback

Không chỉ đặt timeout riêng cho từng bước mà quên giới hạn tổng thời gian. Ví dụ callback có ba bước, mỗi bước timeout 20 giây thì tổng thời gian có thể lên tới 60 giây. Hãy truyền một deadline hoặc remaining budget xuyên suốt các bước để bảo đảm tổng thời gian nằm trong giới hạn vận hành.

Với timeout dùng `nanoTime`, có thể kiểm tra elapsed theo phép trừ:

~~~java
long started = System.nanoTime();
long budgetNanos = TimeUnit.SECONDS.toNanos(20);

// Trước mỗi bước có khả năng chờ:
long elapsed = System.nanoTime() - started;
long remaining = budgetNanos - elapsed;

if (remaining <= 0) {
    throw new TimeoutException("Checkpoint preparation deadline exceeded");
}
~~~

Không cộng timeout vào `started` rồi so sánh `nanoTime()` với giá trị đã cộng. Dùng hiệu số giúp tránh lỗi overflow khi tính deadline.

## 3. Deadlock khi callback giữ lock và chờ worker

Đây là một lỗi phổ biến khi dừng executor.

Giả sử callback dùng một monitor để bảo vệ trạng thái scheduler:

~~~java
public synchronized void beforeCheckpoint(
        Context<? extends Resource> context) throws Exception {

    executor.shutdown();
    executor.awaitTermination(30, TimeUnit.SECONDS);
}
~~~

Một worker đang chạy có thể cần cùng monitor để cập nhật trạng thái khi kết thúc:

~~~java
public synchronized void onTaskFinished() {
    activeTasks--;
    notifyAll();
}
~~~

Tình huống xảy ra:

~~~text
Thread callback                          Worker thread
---------------                          -------------
Giữ monitor
executor.shutdown()
awaitTermination()
  │
  │ chờ worker kết thúc
  │                                        Hoàn tất nghiệp vụ
  │                                        Gọi onTaskFinished()
  │                                        Chờ monitor
  └────────────────────────────────────────┘
                 DEADLOCK
~~~

Callback giữ monitor trong khi chờ executor kết thúc. Worker cần monitor để hoàn tất và trả thread về pool. Cả hai chờ nhau nên không có tiến triển.

### 3.1. Nguyên tắc sửa

- Chỉ giữ lock trong thời gian cập nhật trạng thái ngắn.
- Đặt cờ ngừng nhận task mới bên trong lock.
- Nhả lock trước khi chờ active task drain.
- Worker phải có đường thoát luôn giảm active count trong `finally`.
- Chờ có timeout; không dùng `awaitTermination()` vô hạn.
- Không đóng dependency mà worker còn cần trước khi worker kết thúc.

Không gọi `awaitTermination`, `Future.get`, `join` hoặc thao tác I/O lâu trong một khối `synchronized` hay khi đang giữ lock lifecycle.

## 4. Dùng admission gate và condition để drain task an toàn

Một gate giúp ngăn task mới đi vào nghiệp vụ và đếm task đang chạy. `Condition.awaitNanos()` tự nhả lock khi chờ, nhờ đó worker có thể lấy lock để giảm active count.

Ví dụ:

~~~java
package com.example.lifecycle;

import java.time.Duration;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public final class JobGate {

    private final ReentrantLock lock = new ReentrantLock();
    private final Condition drained = lock.newCondition();

    private boolean accepting = true;
    private int activeTasks;

    public boolean enter() {
        lock.lock();
        try {
            if (!accepting) {
                return false;
            }

            activeTasks++;
            return true;
        } finally {
            lock.unlock();
        }
    }

    public void exit() {
        lock.lock();
        try {
            if (activeTasks <= 0) {
                throw new IllegalStateException(
                        "No active task to exit");
            }

            activeTasks--;

            if (activeTasks == 0) {
                drained.signalAll();
            }
        } finally {
            lock.unlock();
        }
    }

    public void pauseAndAwait(Duration timeout)
            throws InterruptedException, TimeoutException {

        long budgetNanos = timeout.toNanos();

        if (budgetNanos <= 0) {
            throw new IllegalArgumentException(
                    "timeout must be positive");
        }

        long started = System.nanoTime();

        lock.lockInterruptibly();
        try {
            accepting = false;

            while (activeTasks > 0) {
                long elapsed = System.nanoTime() - started;
                long remaining = budgetNanos - elapsed;

                if (remaining <= 0) {
                    accepting = true;
                    drained.signalAll();

                    throw new TimeoutException(
                            "Active jobs did not drain before checkpoint");
                }

                drained.awaitNanos(remaining);
            }
        } catch (InterruptedException interrupted) {
            accepting = true;
            drained.signalAll();
            Thread.currentThread().interrupt();
            throw interrupted;
        } finally {
            lock.unlock();
        }
    }

    public void resume() {
        lock.lock();
        try {
            accepting = true;
            drained.signalAll();
        } finally {
            lock.unlock();
        }
    }

    public int activeTasks() {
        lock.lock();
        try {
            return activeTasks;
        } finally {
            lock.unlock();
        }
    }
}
~~~

`pauseAndAwait()` đặt `accepting=false` trước khi chờ. Vì `enter()` kiểm tra cờ và tăng active count trong cùng lock, không có task mới lọt vào giữa hai thao tác đó. Khi `awaitNanos()` chờ, lock được nhả để worker gọi `exit()`.

Nếu hết thời gian, gate được mở lại trước khi ném `TimeoutException`. Điều này quan trọng khi checkpoint bị từ chối và ứng dụng tiếp tục chạy bình thường. Trong ứng dụng thực tế, có thể cần một trạng thái riêng `PAUSING`, `PAUSED`, `RESUMING` để điều phối nhiều thành phần phức tạp hơn.

### 4.1. Bọc task bằng try/finally

Mọi task được gate chấp nhận phải gọi `exit()` đúng một lần:

~~~java
public void runScheduledJob() {
    if (!jobGate.enter()) {
        return;
    }

    try {
        reconciliationService.run();
    } finally {
        jobGate.exit();
    }
}
~~~

Không gọi `exit()` ở nhánh mà `enter()` trả false. Không gọi `enter()` nhiều lần cho cùng một task nếu chỉ có một `exit()`. Nếu task được chia thành các child task, mỗi child task cần được quản lý riêng hoặc parent phải chờ child hoàn tất trước khi exit.

## 5. Tách dừng scheduler khỏi chờ task hoàn tất

Dừng phát lịch và drain task là hai việc riêng. Một quy trình thường dùng:

1. Đóng admission gate.
2. Hủy hoặc pause các lịch tương lai để không tiếp tục enqueue.
3. Gọi shutdown có trật tự cho executor.
4. Chờ task active kết thúc trong deadline.
5. Nếu còn task, ghi thread dump và báo lỗi checkpoint.
6. Chỉ đóng database/client mà task cần sau khi task đã kết thúc.

Ví dụ với `ExecutorService`:

~~~java
executor.shutdown();

if (!executor.awaitTermination(20, TimeUnit.SECONDS)) {
    List<Runnable> queued = executor.shutdownNow();

    logger.warn(
            "Executor did not terminate; queuedTasks={}",
            queued.size());

    if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
        throw new TimeoutException(
                "Background executor is still running");
    }
}
~~~

Đoạn này minh họa shutdown có giới hạn. `shutdownNow()` chỉ yêu cầu interrupt các task đang chạy và trả về các task chưa bắt đầu; nó không bảo đảm thread đã dừng. Task cần tôn trọng interrupt và mọi I/O cần có timeout.

Nếu task bắt buộc phải được hoàn tất trước checkpoint, không được coi `shutdownNow()` là bằng chứng drain thành công. Nếu task không thể dừng an toàn, hãy từ chối checkpoint và để ứng dụng tiếp tục hoạt động hoặc xử lý theo recovery policy.

### 5.1. Tránh chờ Future được chạy trên executor đã dừng

Một lỗi khác:

~~~java
executor.shutdown();
future.get();
~~~

Nếu `future` đại diện cho task chưa chạy hoặc completion callback được lên lịch trên chính executor vừa shutdown, `get()` có thể chờ mãi.

Trước khi chờ future, xác nhận task đã được submit và có đường thực thi còn hoạt động. Dùng timeout cho `get(timeout, unit)`. Nếu task bị cancel, xử lý `CancellationException`; nếu chờ bị interrupt, giữ lại trạng thái interrupt và thoát callback theo policy.

## 6. Đặt timeout cho lock và I/O

Một callback có thể bị treo vì lock hoặc I/O không có giới hạn. Hãy biến mọi thao tác có khả năng chờ thành thao tác có deadline.

### 6.1. Dùng tryLock thay cho lock vô hạn khi phù hợp

~~~java
if (!resourceLock.tryLock(5, TimeUnit.SECONDS)) {
    throw new TimeoutException(
            "Could not acquire resource lock before checkpoint");
}

try {
    prepareResource();
} finally {
    resourceLock.unlock();
}
~~~

`tryLock` có timeout giúp callback báo lỗi rõ ràng khi resource đang bị thread khác giữ quá lâu. Khi không lấy được lock, cần biết owner thread nào đang giữ nó và tại sao; đừng lặp retry vô hạn trong callback.

### 6.2. Timeout cho network và database

Đóng client hoặc chờ server phản hồi có thể bị treo nếu socket timeout không được cấu hình.

Cần kiểm tra các loại timeout tương ứng:

- Connection timeout.
- Socket/read timeout.
- Request/response timeout.
- Database query timeout.
- Transaction timeout.
- Pool acquisition timeout.
- Broker acknowledgement/close timeout.

Không chỉ đặt timeout ở HTTP client mà bỏ quên timeout ở DNS, TLS handshake, database driver hoặc broker client. Tên thuộc tính và semantics phụ thuộc thư viện cụ thể.

### 6.3. Không thực hiện việc có thể trì hoãn trong beforeCheckpoint

`beforeCheckpoint` nên tập trung vào việc đưa resource về trạng thái có thể checkpoint:

- Ngừng nhận việc mới.
- Drain task đang chạy.
- Commit/rollback transaction.
- Đóng connection/socket.
- Dừng thread hoặc timer cần tạo lại.

Những việc như tải cache lớn, gọi API khởi tạo lại, refresh secret hoặc mở connection mới thường nên thực hiện trong `afterRestore`. Việc chuyển đúng thao tác sang đúng phase làm giảm thời gian checkpoint và hạn chế lock contention.

## 7. Thứ tự callback và deadlock do dependency

CRaC quản lý callback theo thứ tự đăng ký resource trong cùng context: `beforeCheckpoint` được gọi theo thứ tự ngược, còn `afterRestore` theo thứ tự đăng ký. Có thể dùng đặc điểm này để sắp xếp dependency.

Giả sử worker phụ thuộc database pool:

- Database phải được tạo trước worker sau restore.
- Worker phải được dừng trước database trước checkpoint.

Có thể đăng ký database trước, worker sau:

~~~text
Đăng ký:
1. DatabaseResource
2. WorkerResource

beforeCheckpoint (ngược thứ tự):
1. WorkerResource dừng và drain
2. DatabaseResource đóng pool

afterRestore (theo thứ tự đăng ký):
1. DatabaseResource tạo pool mới
2. WorkerResource resume
~~~

Nếu callback của WorkerResource gọi trực tiếp `databaseResource.close()` trong khi DatabaseResource cũng có callback riêng, có thể đóng hai lần hoặc tạo thứ tự không rõ ràng. Mỗi resource nên có một lifecycle owner; coordinator chỉ điều phối dependency và trạng thái admission.

Trong context lồng nhau hoặc framework tự đăng ký resource, cần xác nhận thứ tự thực tế của phiên bản CRaC đang dùng. Không suy ra thứ tự toàn cục từ hai resource nằm ở context khác nhau.

## 8. Log callback có cấu trúc và đo thời lượng

Một wrapper nhỏ giúp mọi callback có cùng format log:

~~~java
package com.example.lifecycle;

import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;

public final class CallbackTiming {

    private CallbackTiming() {
    }

    public static void run(
            Logger logger,
            String phase,
            String resource,
            CheckedAction action) throws Exception {

        long started = System.nanoTime();

        logger.info(
                "CRaC callback start phase={} resource={} thread={}",
                phase,
                resource,
                Thread.currentThread().getName());

        try {
            action.run();
        } catch (Exception failure) {
            long elapsed = System.nanoTime() - started;

            logger.error(
                    "CRaC callback failed phase={} resource={} elapsedMs={}",
                    phase,
                    resource,
                    TimeUnit.NANOSECONDS.toMillis(elapsed),
                    failure);

            throw failure;
        }

        long elapsed = System.nanoTime() - started;

        logger.info(
                "CRaC callback complete phase={} resource={} elapsedMs={}",
                phase,
                resource,
                TimeUnit.NANOSECONDS.toMillis(elapsed));
    }

    @FunctionalInterface
    public interface CheckedAction {
        void run() throws Exception;
    }
}
~~~

Sử dụng:

~~~java
@Override
public void beforeCheckpoint(
        Context<? extends Resource> context) throws Exception {

    CallbackTiming.run(
            logger,
            "beforeCheckpoint",
            "job-gate",
            () -> jobGate.pauseAndAwait(Duration.ofSeconds(20)));
}
~~~

Nếu callback bị treo, log `start` vẫn xuất hiện nhưng `complete` không xuất hiện. Có thể bổ sung log cho từng bước con, số active task, lock acquisition duration và thời gian chờ dependency.

Không log secret, connection string hoặc payload nghiệp vụ trong callback diagnostics.

## 9. Phát hiện deadlock bằng ThreadMXBean

Java cung cấp `ThreadMXBean` để quan sát thread và phát hiện một số dạng deadlock.

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;

public final class DeadlockDetector {

    private DeadlockDetector() {
    }

    public static void dumpDeadlockedThreads() {
        ThreadMXBean bean =
                ManagementFactory.getThreadMXBean();

        long[] ids = bean.findDeadlockedThreads();

        if (ids == null || ids.length == 0) {
            System.out.println("No monitor/ownable-synchronizer deadlock detected");
            return;
        }

        ThreadInfo[] infos =
                bean.getThreadInfo(ids, true, true);

        for (ThreadInfo info : infos) {
            if (info != null) {
                System.err.println(info);
            }
        }
    }
}
~~~

`findDeadlockedThreads()` tìm deadlock liên quan đến monitor và ownable synchronizer mà JVM có thể quan sát. Kết quả `null` không chứng minh ứng dụng không bị treo.

Nó không phát hiện mọi dạng chờ logic, ví dụ:

- Thread chờ một `CountDownLatch` mà không có thread nào gọi `countDown()`.
- `Future.get()` chờ một task không còn được schedule.
- Callback chờ một service bên ngoài không phản hồi.
- Hai thành phần chờ nhau qua message hoặc trạng thái trong database.
- Thread chờ socket read không có timeout.

Vì vậy, kết hợp ThreadMXBean với thread dump, log callback và trạng thái executor.

### 9.1. Theo dõi số thread và trạng thái

Có thể ghi các thông tin sau từ `ThreadMXBean`:

~~~java
ThreadMXBean bean =
        ManagementFactory.getThreadMXBean();

logger.info(
        "threadCount={} peakThreadCount={} daemonThreadCount={}",
        bean.getThreadCount(),
        bean.getPeakThreadCount(),
        bean.getDaemonThreadCount());
~~~

Nếu có thể lấy `ThreadInfo` cho tất cả thread, ghi các thread có tên prefix như `crac-`, `scheduler-`, `worker-` và `http-`. Tên thread có quy ước giúp nhận diện pool đang bị kẹt.

Không gọi dump toàn bộ stack trace liên tục trong mỗi lần probe. Chỉ thu thập khi callback vượt ngưỡng hoặc khi có cảnh báo.

## 10. Lấy thread dump khi checkpoint không tiến triển

Khi log cho thấy callback bắt đầu nhưng không hoàn tất, lấy nhiều thread dump cách nhau vài giây để so sánh.

### 10.1. Dùng jcmd

Trên Linux, nếu attach API còn hoạt động và có quyền phù hợp:

~~~bash
jcmd <PID> Thread.print -l
~~~

Tùy JDK, có thể dùng:

~~~bash
jstack -l <PID>
~~~

`-l` yêu cầu in thông tin lock bổ sung, gồm monitor và ownable synchronizer. Cần chạy bằng user có quyền attach vào JVM và đúng PID namespace.

Nếu checkpoint command đang chờ callback, có thể thử lấy thread dump từ một terminal khác. Tuy nhiên, attach có thể không khả dụng trong một số trạng thái JVM, container hoặc security profile.

### 10.2. Dùng SIGQUIT trên Linux

Nếu attach không hoạt động nhưng process vẫn nhận signal:

~~~bash
kill -3 <PID>
~~~

Trên HotSpot, SIGQUIT thường yêu cầu JVM in thread dump vào stdout/stderr của process. Đảm bảo log container được thu thập để không mất output.

Không gửi SIGKILL để “thử giải phóng” callback. SIGKILL chấm dứt process ngay và không cho callback cleanup hoặc rollback.

### 10.3. Lấy dump nhiều lần

Một thread dump đơn lẻ có thể cho thấy thread đang `WAITING` hoặc `TIMED_WAITING`, nhưng chưa đủ để kết luận deadlock. Lấy hai hoặc ba dump cách nhau vài giây:

- Nếu stack và lock owner không thay đổi, thread có thể đang kẹt.
- Nếu thread chuyển sang bước tiếp theo, callback vẫn đang tiến triển.
- Nếu cùng một thread liên tục chờ cùng monitor và owner thread cũng không tiến triển, kiểm tra lock cycle.
- Nếu thread chờ socket read, xem timeout và trạng thái network/service.
- Nếu thread chờ `awaitTermination`, kiểm tra worker thread và executor queue.

Một lệnh Linux hữu ích để quan sát thread ở mức OS:

~~~bash
ps -L -p <PID> -o pid,tid,stat,pcpu,comm,wchan:32
~~~

`wchan` có thể giúp nhận diện nơi thread đang ngủ trong kernel, nhưng không thay thế Java stack trace. Thread có CPU thấp không đồng nghĩa deadlock; nó có thể đang chờ I/O hợp lệ.

### 10.4. Dùng timeout cho lệnh checkpoint

Có thể giới hạn thời gian chờ của client gọi checkpoint:

~~~bash
timeout --signal=TERM 60s jcmd <PID> JDK.checkpoint
~~~

Lệnh `timeout` giới hạn thời gian chạy của tiến trình `jcmd` client. Nó **không bảo đảm hủy callback hoặc rollback thao tác checkpoint bên trong JVM** khi client bị dừng. Nếu lệnh hết hạn, hãy kiểm tra trạng thái process và thu thread dump trước khi quyết định hành động tiếp theo.

## 11. Đọc thread dump để xác định loại lỗi

Một số dấu hiệu thường gặp:

| Dấu hiệu trong dump | Ý nghĩa có thể | Cần kiểm tra |
|---|---|---|
| `BLOCKED` và `waiting to lock` | Thread đang chờ monitor | Thread nào sở hữu monitor, lock ordering |
| `Found one Java-level deadlock` | JVM phát hiện chu trình monitor/ownable synchronizer | Stack và lock owner của các thread trong chu trình |
| `WAITING` tại `CountDownLatch.await` | Đang chờ tín hiệu | Ai phải gọi `countDown`, nhánh exception có bỏ quên signal không |
| `TIMED_WAITING` tại `awaitTermination` | Callback chờ executor | Worker còn active không, có chờ lock mà callback giữ không |
| `FutureTask.get` hoặc `CompletableFuture.join` | Chờ kết quả async | Task có được thực thi không, executor có bị shutdown không |
| `SocketDispatcher.read` hoặc socket read | Chờ I/O | Read timeout, remote service, DNS/TLS |
| `Object.wait` | Chờ monitor/condition | Điều kiện thoát và thread phát signal |
| `LockSupport.park` | Thread đang park | Lock, condition, future hoặc synchronizer đang chờ |

Một callback có thể bị treo mà không có deadlock cycle. Ví dụ, một thread duy nhất chờ một API bên ngoài vô hạn. Trong trường hợp đó, `findDeadlockedThreads()` có thể trả `null`; thread dump vẫn chỉ ra stack đang chờ I/O.

## 12. Xử lý callback timeout và rollback trạng thái

Nếu `beforeCheckpoint` không thể dừng resource trong thời gian cho phép, callback nên báo lỗi để checkpoint không tiếp tục trong trạng thái không an toàn. Nhưng trước khi ném exception, ứng dụng cần xem trạng thái nào đã được thay đổi và có thể rollback được không.

Ví dụ:

- Admission gate đã đóng nhưng worker chưa drain.
- Scheduler đã pause nhưng executor chưa shutdown.
- Một pool đã đóng nhưng các pool khác chưa đóng.
- Readiness đã chuyển sang `REFUSING_TRAFFIC`.
- Một listener đã ngừng nhận request.

Nếu checkpoint bị từ chối và process tiếp tục chạy, các thành phần đã pause cần được resume hoặc khôi phục theo policy. Không để ứng dụng tiếp tục chạy nhưng gate vẫn đóng hoặc readiness vẫn false vô thời hạn.

Mẫu xử lý:

~~~java
@Override
public void beforeCheckpoint(
        Context<? extends Resource> context) throws Exception {

    readiness.refusingTraffic();
    jobGate.pauseAdmission();

    try {
        jobGate.awaitDrained(Duration.ofSeconds(20));
        scheduler.pause();
        closeResourcesForCheckpoint();

    } catch (Exception failure) {
        scheduler.resumeIfPaused();
        jobGate.resume();
        readiness.acceptingTraffic();

        throw failure;
    }
}
~~~

Đây là skeleton. Trong ứng dụng thực tế, không phải resource nào cũng có thể reopen an toàn sau khi đóng. Cần theo dõi chính xác các bước đã hoàn tất và rollback theo thứ tự ngược. Nếu resource đã đóng không thể phục hồi, có thể phải fail process hoặc chuyển sang recovery path có kiểm soát thay vì công bố readiness.

### 12.1. afterRestore thất bại

Nếu `afterRestore` không thể kết nối lại dependency:

- Giữ readiness ở `REFUSING_TRAFFIC`.
- Không resume worker phụ thuộc resource chưa sẵn sàng.
- Ghi log phase, resource và exception.
- Retry có giới hạn nếu lỗi có thể tạm thời.
- Dùng startup/liveness policy phù hợp với khả năng tự phục hồi.
- Chỉ đánh dấu Ready sau khi tất cả dependency bắt buộc hoạt động.

Không nuốt exception rồi để process có vẻ đã restore thành công. Nếu recovery không thể tiếp tục, để orchestration xử lý theo policy đã thiết kế, chẳng hạn restart hoặc cold start bằng artifact hợp lệ.

## 13. Tránh deadlock giữa nhiều Resource callback

Khi có nhiều resource, deadlock có thể xuất hiện vì thứ tự lock không nhất quán.

Ví dụ:

~~~text
Resource A callback:
  giữ lock A
  gọi B.close()
  chờ lock B

Resource B worker:
  giữ lock B
  gọi A.update()
  chờ lock A
~~~

Đây là lock-order inversion. Hai thành phần có thứ tự lấy lock khác nhau.

Các biện pháp:

- Thiết kế một thứ tự lock toàn cục và tuân thủ ở mọi đường code.
- Tránh callback của resource này gọi trực tiếp lifecycle method của resource khác.
- Dùng coordinator quản lý thứ tự dependency.
- Không giữ lock khi gọi code bên ngoài hoặc chờ executor.
- Tách state transition khỏi thao tác đóng/mở resource.
- Nếu có thể, dùng `tryLock` với timeout và log owner/phase.
- Tránh callback đồng thời đóng cùng một resource.

Nếu resource A phụ thuộc B, hãy dùng thứ tự đăng ký CRaC phù hợp thay vì lồng lời gọi close/open thủ công. Đảm bảo chỉ có một owner thực hiện lifecycle của từng resource.

## 14. Quan sát tiến độ callback bằng watchdog

Một watchdog có thể phát hiện callback vượt ngưỡng. Có hai hướng triển khai:

- Watchdog nội bộ ghi nhận thời điểm bắt đầu callback và cảnh báo nếu callback chưa kết thúc.
- Supervisor bên ngoài quan sát log/metric/process và thu thread dump khi quá thời gian.

Với checkpoint thực, watchdog bên ngoài thường hữu ích vì nó không phụ thuộc vào executor đang được ứng dụng chuẩn bị dừng. Tuy nhiên, phải bảo đảm watchdog có quyền truy cập process và log.

Một bản ghi trạng thái có thể gồm:

~~~text
checkpointOperationId=cp-2026-11-13-001
phase=beforeCheckpoint
resource=database-pool
startedAt=2026-11-13T07:10:00Z
elapsedMs=12000
thread=main
status=RUNNING
step=await-pool-drain
activeConnections=2
~~~

Metric gợi ý:

| Metric | Ý nghĩa |
|---|---|
| `crac_callback_duration_seconds` | Thời lượng callback theo phase/resource |
| `crac_callback_in_progress` | Callback đang chạy hay không |
| `crac_callback_timeouts_total` | Số callback vượt deadline |
| `crac_active_workers` | Số worker task đang active |
| `crac_executor_termination_seconds` | Thời gian executor dừng |
| `crac_lock_wait_seconds` | Thời gian chờ lock lifecycle |
| `crac_checkpoint_failures_total` | Số checkpoint thất bại |
| `crac_restore_callback_failures_total` | Số lỗi callback sau restore |

Dùng label có cardinality giới hạn như resource name và phase. Không gắn request ID hoặc checkpoint ID không giới hạn vào metric label; các giá trị đó phù hợp hơn với log hoặc trace.

## 15. Kiểm thử callback chậm và deadlock có kiểm soát

Không đợi tới production mới phát hiện callback treo. Có thể kiểm thử lifecycle bằng resource giả lập và điều khiển đồng bộ.

### 15.1. Test callback timeout

Dùng `CountDownLatch` để mô phỏng worker chưa hoàn tất:

~~~java
CountDownLatch releaseWorker = new CountDownLatch(1);

executor.submit(() -> {
    try {
        releaseWorker.await();
    } catch (InterruptedException interrupted) {
        Thread.currentThread().interrupt();
    }
});

assertThrows(
        TimeoutException.class,
        () -> gate.pauseAndAwait(Duration.ofMillis(100)));
~~~

Sau test, luôn release latch và shutdown executor trong `finally` để test không để lại thread nền.

### 15.2. Test worker hoàn tất bình thường

1. Cho worker vào gate.
2. Gọi pause từ thread khác.
3. Xác nhận task mới bị từ chối.
4. Gọi `exit()` cho worker đang chạy.
5. Xác nhận pause hoàn tất.
6. Xác nhận active count bằng 0.
7. Gọi resume và xác nhận task mới có thể vào.

### 15.3. Test lock inversion

Tạo hai thread thử nghiệm với hai lock và dùng latch để kiểm soát thứ tự lấy lock. Xác nhận detector hoặc thread dump cho thấy chu trình chờ. Test phải có timeout và cleanup để không làm treo test suite.

Không đưa deadlock cố ý vào môi trường production. Mục tiêu là chứng minh cơ chế phát hiện và timeout hoạt động.

### 15.4. Test trên CRaC runtime thật

Unit test chỉ kiểm tra logic gate và lock. Cần thêm integration test với JDK/CRaC engine thật để xác nhận:

- `beforeCheckpoint` thực sự được gọi.
- Exception/timeout trong callback làm checkpoint request thất bại theo runtime semantics.
- Process có thể tiếp tục hoặc rollback sau checkpoint failure.
- `afterRestore` chạy theo đúng thứ tự resource.
- Thread/executor được tạo lại đúng cách.
- Log và thread dump có thể thu thập trong môi trường container.

`simengine` hữu ích để kiểm tra callback flow nhưng không thay thế kiểm thử CRIU checkpoint/restore trên Linux. Chạy integration test với đúng JDK vendor/build, CRIU, kernel, container runtime và security context dự kiến triển khai.

## 16. Runbook khi checkpoint bị treo

Khi lệnh checkpoint không hoàn tất, xử lý theo trình tự sau:

1. Ghi nhận PID, thời điểm bắt đầu, lệnh checkpoint và checkpoint operation ID.
2. Xác định callback cuối cùng có log `start` nhưng chưa có `complete`.
3. Kiểm tra resource và step cuối cùng được ghi nhận.
4. Lấy thread dump bằng `jcmd Thread.print -l`, `jstack -l` hoặc SIGQUIT nếu attach không khả dụng.
5. Lấy thêm một hoặc hai dump sau vài giây để xác định stack có tiến triển không.
6. Kiểm tra lock owner, active worker, executor queue và I/O timeout.
7. Dùng `ThreadMXBean.findDeadlockedThreads()` nếu JVM còn cho phép gọi management API.
8. Nếu callback có deadline, chờ timeout có kiểm soát và để checkpoint request thất bại an toàn.
9. Sau failure, xác nhận gate, scheduler, pool và readiness đã được rollback hoặc resume.
10. Chỉ thử checkpoint lại sau khi nguyên nhân được xác định và trạng thái ứng dụng đã ổn định.

Không xóa thư mục checkpoint đang được engine ghi hoặc restore. Không gửi SIGKILL chỉ vì callback chậm. Nếu process không thể tự phục hồi, thu thập log và dump trước khi quyết định restart theo runbook của ứng dụng.

## 17. Bảng chẩn đoán nhanh

| Triệu chứng | Khả năng cao | Bằng chứng cần lấy | Hướng xử lý |
|---|---|---|---|
| Log callback start nhưng không complete | Callback đang chờ hoặc bị block | Thread dump và log step | Xác định wait point, đặt timeout |
| Callback chờ `awaitTermination` | Worker chưa dừng | Thread dump worker và executor state | Nhả lock, kiểm tra task và interrupt |
| Thread `BLOCKED` trên monitor | Lock contention hoặc deadlock | Lock owner và chuỗi stack | Sửa lock ordering, giảm critical section |
| `findDeadlockedThreads()` trả null nhưng callback treo | Chờ I/O, latch hoặc future | Stack trace và dependency state | Thêm timeout/signal/cancel đúng cách |
| Active task count không giảm | Worker không gọi exit hoặc chưa kết thúc | Log enter/exit, thread dump | Đặt exit trong finally và xử lý cancellation |
| Timeout callback, checkpoint thất bại | Drain không xong trong budget | Active count, task state | Tăng budget có cơ sở hoặc sửa task không dừng |
| Checkpoint fail nhưng ứng dụng không nhận traffic | Gate/readiness chưa rollback | Availability state và resource state | Resume theo thứ tự, không công bố Ready giả |
| afterRestore treo ở reconnect | Dependency hoặc network chưa sẵn sàng | Client logs, timeout, thread dump | Retry có giới hạn, giữ readiness false |
| Nhiều callback đóng cùng resource | Lifecycle owner không rõ | Callback start/end theo resource | Chọn một owner và điều phối thứ tự |
| Chỉ treo trên một node | Khác biệt kernel/runtime/permission | Node fingerprint và CRIU logs | So sánh môi trường và test đúng node |

## 18. Nguyên tắc thiết kế callback không bị treo

Một callback CRaC dễ vận hành cần tuân thủ các nguyên tắc:

1. **Có log bắt đầu và kết thúc:** ghi phase, resource, thread và elapsed time.
2. **Có deadline tổng:** không để callback chờ vô hạn.
3. **Không giữ lock khi chờ:** nhả lock trước `awaitTermination`, `Future.get`, I/O hoặc condition wait.
4. **Drain theo thứ tự:** ngừng admission, dừng phát lịch, drain task rồi mới đóng dependency.
5. **Task có đường thoát:** dùng `finally` để giảm active count và xử lý interrupt.
6. **I/O có timeout:** database, socket, broker và secret provider phải có timeout phù hợp.
7. **Lifecycle owner rõ ràng:** không để hai callback cùng đóng/mở một resource.
8. **Rollback có chủ đích:** nếu checkpoint bị từ chối, khôi phục các thành phần đã pause/đóng khi có thể.
9. **Có công cụ chẩn đoán:** thread dump, ThreadMXBean, executor metrics và callback timing.
10. **Kiểm thử failure path:** test task chậm, lock contention, interrupt, timeout và restore callback thất bại.

Khi callback bị treo, hãy bắt đầu từ callback cuối cùng có log `start`, xác định thread đang chờ gì bằng thread dump, rồi lần theo lock owner hoặc dependency chưa phản hồi. Deadlock cần được sửa ở thứ tự lock và cách phối hợp thread; callback chậm cần deadline và timeout cho thao tác chờ; task không drain cần admission gate và cơ chế kết thúc an toàn. Việc chỉ tăng timeout hoặc restart JVM có thể che triệu chứng nhưng không giải quyết nguyên nhân.

## 19. Tài liệu tham khảo

- [CRaC: Implementing the CRaC API](https://crac.org/use/implement-crac/): đăng ký resource và triển khai callback trước checkpoint/sau restore.
- [Java ThreadMXBean API](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html): theo dõi thread và phát hiện deadlock có thể quan sát.
- [jcmd tool](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): gửi diagnostic command tới JVM đang chạy.
- [jstack tool](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jstack.html): lấy thread stack trace và lock information.
- [ExecutorService API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html): shutdown, awaitTermination và quản lý executor lifecycle.
- [ReentrantLock API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html): lock acquisition có timeout và condition waiting.


