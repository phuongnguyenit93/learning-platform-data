# ScheduledExecutorService cho công việc trì hoãn trong Java

## 1. Mục tiêu bài học

Sau bài này, bạn có thể:

- Giải thích **ScheduledExecutorService** trong Executor Framework và phân biệt **hẹn chạy sau một khoảng trì hoãn** với **chạy định kỳ**.
- Dùng đúng hai overload **schedule(Runnable, delay, unit)** và **schedule(Callable<V>, delay, unit)**; biết vai trò của **ScheduledFuture** đối với kết quả, lỗi, timeout và cancellation.
- Phân biệt **thời điểm task đủ điều kiện chạy** với **thời điểm task thực sự bắt đầu**. Hiểu scheduler của JDK không cam kết độ chính xác thời gian thực (*hard real-time*).
- Chọn **Executors.newSingleThreadScheduledExecutor()**, **Executors.newScheduledThreadPool(n)** hoặc **ScheduledThreadPoolExecutor** với cấu hình phù hợp.
- Xử lý an toàn **shutdown()**, **shutdownNow()**, **Future.cancel()**, **InterruptedException**, task ném exception và tài nguyên liên quan.
- Nhận biết các rủi ro: đặt lịch quá nhiều task, một worker bị block, lịch theo giờ thực/đổi múi giờ, task bị chạy lặp qua retry/restart, và sự phụ thuộc giữa các task trong cùng executor.
- Đọc hiểu sự khác biệt giữa **scheduleAtFixedRate()** và **scheduleWithFixedDelay()** để không nhầm lịch một lần với lịch định kỳ.
- Chạy các ví dụ Java 17+ có đầu ra có thể kiểm chứng mà không dựa vào suy đoán độ dài sleep hay thứ tự scheduling ngẫu nhiên.

Phạm vi bài là **Java concurrency nói chung**, thuộc nhóm **Future & Scheduling**. Bài không bàn API, annotation hoặc cơ chế scheduling riêng của Spring.

## 2. Từ ExecutorService đến ScheduledExecutorService

**ExecutorService** tách việc gửi task khỏi việc tạo/quản lý thread. **ScheduledExecutorService** mở rộng ExecutorService và bổ sung khả năng yêu cầu task trở nên **đủ điều kiện thực thi sau một độ trễ tương đối**, hoặc được thực thi theo lịch lặp.

~~~java
// Đoạn minh họa cú pháp trong một phương thức Java.
ScheduledExecutorService scheduler =
        Executors.newSingleThreadScheduledExecutor();

try {
    ScheduledFuture<Integer> result =
            scheduler.schedule(() -> 6 * 7, 200, TimeUnit.MILLISECONDS);
    System.out.println(result.get());
} finally {
    scheduler.shutdown();
}
~~~

Cần import các lớp trong java.util.concurrent và khai báo/xử lý checked exceptions của **Future.get()**. Đoạn trên chưa phải một chương trình main độc lập; ví dụ chạy đầy đủ ở phần 5.

Các thành phần:

| Thành phần | Vai trò |
| --- | --- |
| **Runnable** | Task không trả giá trị qua run(); overload schedule(Runnable, ...) vẫn trả Future để theo dõi |
| **Callable<V>** | Task trả V hoặc ném exception |
| **ScheduledExecutorService** | Interface hỗ trợ schedule và periodic execution |
| **ScheduledThreadPoolExecutor** | Triển khai dựa trên pool thread, quản lý queue của các task bị trì hoãn |
| **ScheduledFuture<V>** | Future kết hợp khả năng hỏi khoảng trì hoãn còn lại qua Delayed |
| **TimeUnit** | Đơn vị cho các tham số delay, period, timeout |
| **ExecutorService lifecycle** | shutdown, shutdownNow, awaitTermination, hủy task và dọn tài nguyên |

**Một task đã được schedule chưa chắc đang chạy.** Nó có thể chờ tới hạn, chờ worker rảnh, hoặc đã bị cancel. **ScheduledFuture** giúp quan sát một tác vụ cụ thể nhưng không phải một kho lưu lịch bền vững qua restart JVM.

### Sơ đồ thời gian

~~~text
Thread gửi task           Scheduler                         Worker
---------------           ---------                         ------
schedule(task, 200 ms)
       |                       |
       +---- đăng ký ----------> task nằm trong queue chờ tới hạn
                                |
              200 ms tương đối  +--- task ĐỦ ĐIỀU KIỆN chạy
                                |                |
                                +--- worker rảnh? +----> task.run()
                                |                |
                                |            nếu bận, tiếp tục chờ
       <---- ScheduledFuture ---+
~~~

Lưu ý **“200 ms” không phải lời hứa task chạy chính xác ở mốc 200 ms**. Khi tới hạn, worker còn phụ thuộc scheduler, CPU, tác vụ trước đó và tài nguyên hệ thống.

## 3. Hai overload schedule cho một lần thực thi

### 3.1. Runnable: không có giá trị kết quả

~~~java
// Minh họa; scheduler là ScheduledExecutorService đã tạo.
ScheduledFuture<?> future = scheduler.schedule(
        () -> System.out.println("done"),
        1, TimeUnit.SECONDS
);
~~~

Task in “done” sau khi đủ điều kiện chạy và worker có thể phục vụ. Khi task **hoàn thành bình thường**, **future.get()** trả **null**. Nếu Runnable ném exception, Future.get() ném **ExecutionException** chứa cause. Nếu Future bị cancel, get() ném **CancellationException**.

### 3.2. Callable<V>: có kết quả

~~~java
ScheduledFuture<Integer> future = scheduler.schedule(
        () -> 21 * 2,
        1, TimeUnit.SECONDS
);
int answer = future.get(); // 42 khi task hoàn tất thành công.
~~~

Đoạn trên là minh họa trong phương thức có biến scheduler và checked-exception handling. **get()** đợi tác vụ hoàn thành, không phải đợi chính xác một giây rồi tự trả. Nếu executor quá tải, tổng thời gian từ schedule tới get() hoàn tất có thể **dài hơn delay**.

### 3.3. Delay tính từ thời điểm đăng ký

Các tham số **delay** và **unit** là **thời gian tương đối**, không phải timestamp lịch theo ngày/tháng/giờ. Ví dụ:

~~~java
scheduler.schedule(task, 500, TimeUnit.MILLISECONDS);
scheduler.schedule(task, 2, TimeUnit.SECONDS);
scheduler.schedule(task, 0, TimeUnit.MILLISECONDS);
~~~

Ba dòng trên minh họa các lần đăng ký với Runnable task đã khai báo. **Delay bằng 0 hoặc âm** cho một lần schedule được hiểu là yêu cầu thực thi **ngay khi có thể**; đó không phải lời hứa thực thi đồng bộ ngay trên thread gửi. Scheduler vẫn có thể enqueue.

**Không nhầm với periodic APIs:** **period** của scheduleAtFixedRate và **delay giữa các lần chạy** của scheduleWithFixedDelay phải **dương**; giá trị 0 hoặc âm cho các tham số ấy gây IllegalArgumentException. **initialDelay** của periodic scheduling có thể bằng 0.

## 4. ScheduledFuture, getDelay và quan sát trạng thái

**ScheduledFuture<V>** đồng thời là **Future<V>** và **Delayed**.

Các API đáng chú ý:

| API | Ý nghĩa |
| --- | --- |
| **get()** | Chờ kết thúc và lấy kết quả, có thể ném InterruptedException/ExecutionException/CancellationException |
| **get(timeout, unit)** | Chờ tối đa thời lượng được chỉ định; có thể ném TimeoutException |
| **cancel(false)** | Cố hủy; không yêu cầu ngắt task đang chạy |
| **cancel(true)** | Cố hủy; có thể yêu cầu interrupt thread đang thực thi |
| **isCancelled()** | Future đã bị hủy theo hợp đồng hay chưa |
| **isDone()** | Future đã hoàn tất, kể cả lỗi hoặc hủy, không nhất thiết thành công |
| **getDelay(unit)** | Thời gian ước lượng tới khi task đủ điều kiện thực thi |
| **compareTo(Delayed)** | Thứ tự các task bị trì hoãn trong hợp đồng Delayed |

**getDelay() không phải đồng hồ đếm ngược chính xác tới lúc task bắt đầu.** Khi task đã đến hạn nhưng worker đang bận, **getDelay() có thể bằng 0 hoặc âm** trong khi task vẫn chưa chạy. Sau khi Future hoàn tất, giá trị delay cũng không phải báo cáo thời lượng đã thực thi hay latency.

**get(timeout)** giới hạn thời gian **caller đợi Future**, không thay đổi delay đã đăng ký và **không tự cancel task** khi timeout. Một caller có thể bỏ chờ nhưng worker vẫn chạy sau đó.

### Ba trạng thái cần tách riêng

~~~text
Đã nhận lịch -> chưa đủ hạn -> đủ hạn, đang chờ worker -> đang chạy
                                                           |
                           +----------- hoàn tất ----------+
                           |               |
                           v               v
                        thành công      exception

Hủy có thể xảy ra trước khi bắt đầu hoặc trong lúc task đang chạy.
~~~

**Future.isDone() = true** có thể do thành công, thất bại hoặc hủy. **isCancelled() = true** không chứng minh mọi side effect đã được đảo ngược; cancellation là trạng thái Future và yêu cầu hợp tác với task.

## 5. Ví dụ 1: chạy Callable một lần sau độ trễ

Tệp **DelayedCallableDemo.java**:

~~~java
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;

public class DelayedCallableDemo {
    public static void main(String[] args) throws Exception {
        ScheduledExecutorService scheduler =
                Executors.newSingleThreadScheduledExecutor();

        try {
            ScheduledFuture<Integer> future = scheduler.schedule(
                    () -> 21 * 2,
                    20, TimeUnit.MILLISECONDS
            );

            System.out.println("value = " + future.get());
            System.out.println("done = " + future.isDone());
            System.out.println("cancelled = " + future.isCancelled());
        } finally {
            scheduler.shutdownNow();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 DelayedCallableDemo.java
java DelayedCallableDemo
~~~

Stdout khi môi trường không gửi interrupt và task hoàn tất bình thường:

~~~text
value = 42
done = true
cancelled = false
~~~

**Lập luận:**

1. Scheduler nhận Callable, đặt trigger tương đối sau 20 ms.
2. **future.get()** chờ đến khi task đã thực thi và trả 42, dù worker có thể bắt đầu sau hạn.
3. Khi get() trả thành công, Future đã **done** và không bị cancel.
4. finally yêu cầu shutdown để worker không giữ chương trình chạy sau khi không còn cần scheduler.

Đừng in một con số “elapsed = 20 ms” như output bắt buộc: runtime, độ phân giải đồng hồ và tải hệ thống có thể làm thời gian đo thực tế khác nhau.

### Runnable có Future trả null khi hoàn tất

Tệp **DelayedRunnableDemo.java**:

~~~java
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class DelayedRunnableDemo {
    public static void main(String[] args) throws Exception {
        ScheduledExecutorService scheduler =
                Executors.newSingleThreadScheduledExecutor();
        AtomicBoolean executed = new AtomicBoolean();

        try {
            ScheduledFuture<?> future = scheduler.schedule(
                    () -> executed.set(true),
                    10, TimeUnit.MILLISECONDS
            );

            Object value = future.get();

            System.out.println("runnable result = " + value);
            System.out.println("executed = " + executed.get());
        } finally {
            scheduler.shutdownNow();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 DelayedRunnableDemo.java
java DelayedRunnableDemo
~~~

Stdout:

~~~text
runnable result = null
executed = true
~~~

Task Runnable không có kết quả trả về của run(), nhưng **ScheduledFuture** vẫn cho phép chờ **thời điểm hoàn tất** hoặc nhận lỗi. AtomicBoolean là công cụ quan sát trạng thái minh họa; ngữ nghĩa completion của Future đã đủ để main biết code trước khi run() kết thúc đã xảy ra.

## 6. Chọn scheduler: một worker hay nhiều worker?

Hai factory phổ biến:

~~~java
ScheduledExecutorService one =
        Executors.newSingleThreadScheduledExecutor();

ScheduledExecutorService many =
        Executors.newScheduledThreadPool(4);
~~~

Đoạn minh họa dùng các import từ java.util.concurrent; trong chương trình thật phải shutdown cả hai executor đúng vòng đời.

| Tiêu chí | Single-thread scheduled | Scheduled thread pool N worker |
| --- | --- | --- |
| Số task chạy đồng thời | Tối đa 1 | Tối đa N |
| Khi task đến hạn nhưng worker bận | Chờ task đang chạy kết thúc | Có thể chạy trên worker khác còn rảnh |
| Hai task cùng đủ hạn | Thực thi tuần tự | Có thể thực thi song song |
| Chia sẻ mutable state | Dễ xây một owner nếu tất cả truy cập đều đi qua executor | Cần atomic/lock/confinement phù hợp |
| Blocking task kéo dài | Chặn toàn bộ tác vụ sau | Dùng hết N worker có thể chặn tác vụ sau |
| Queue delayed tasks | Có thể tích lũy rất lớn | Vẫn có thể tích lũy rất lớn |
| Thứ tự task thực sự hoàn tất | Tuần tự trong một worker | Không hứa theo thứ tự submit |

**newSingleThreadScheduledExecutor()** bảo đảm không có hơn một task chạy cùng thời điểm; không nên giả định **cùng một Thread object tồn tại vĩnh viễn**. Nếu worker kết thúc bất thường, executor có thể tạo worker thay thế. ThreadLocal gắn với thread, không gắn với scheduler.

**newScheduledThreadPool(n)** dùng **n core workers** theo nhu cầu. Với **ScheduledThreadPoolExecutor**, queue của các task trì hoãn là **DelayedWorkQueue không có capacity hữu ích để áp dụng backpressure**. Khi tất cả n worker bận, task đến hạn vẫn chờ. Việc đặt maximumPoolSize lớn hơn core **không tạo cơ chế scale tương tự bounded ThreadPoolExecutor**, vì hàng đợi delayed thực dụng không giới hạn.

### Không coi “scheduled” là “giới hạn số job”

Nếu mỗi giây producer đăng ký nhiều task với delay dài, scheduler có thể giữ rất nhiều object task trong queue. Cần **admission control**, giới hạn số lịch, hủy lịch không còn cần thiết, và xem xét **setRemoveOnCancelPolicy(true)** khi dùng ScheduledThreadPoolExecutor để tránh giữ task đã cancel trong queue quá lâu.

## 7. Khi task đến hạn nhưng scheduler chưa có worker

Ví dụ, scheduler chỉ có 1 worker:

~~~text
Thời điểm 0:
  Task A đang chạy và block trên I/O.

Thời điểm 100 ms:
  Task B đủ hạn để chạy.

Thời điểm 500 ms:
  Task A hoàn tất, worker mới nhận B.

Kết quả:
  B được schedule sau 100 ms nhưng có thể thực sự bắt đầu gần 500 ms.
~~~

Đây là sơ đồ minh họa, không phải giới hạn thời gian được JDK bảo đảm.

Các nguyên nhân delay sau hạn:

- Tất cả worker đang thực thi task khác, đặc biệt là blocking I/O dài.
- CPU scheduler/JVM đang bận, stop-the-world GC hoặc mức tải cao.
- Task trước đó giữ khóa hoặc đợi tài nguyên mà task mới cũng cần.
- Queue có quá nhiều task cùng đến hạn.
- Shutdown/cancellation/exception thay đổi trạng thái lifecycle của scheduler.
- Nhiều instance ứng dụng có lịch độc lập cùng tranh chấp tài nguyên chung.

**ScheduledExecutorService là công cụ hẹn thời điểm sớm nhất có thể chạy, không phải scheduler hard real-time.** Nếu nghiệp vụ cần deadline chặt, phải thiết kế theo dõi latency, timeout và xử lý quá hạn riêng.

### Bẫy: một task đợi task khác trên cùng scheduler một worker

Nếu task A chạy trên single scheduler, từ A lại gọi schedule(task B, 0, ...) rồi **B.get()**, A chiếm worker và chờ B. B chưa được chạy vì worker duy nhất đang bận A: **thread-starvation deadlock**.

Không viết luồng phụ thuộc như vậy. Cân nhắc composition bất đồng bộ hoặc mô hình worker khác nếu bài toán cần, và kiểm tra dependency graph trước khi dùng Future.get() trong task.

## 8. Ví dụ 2: hủy task đang nằm trong queue trước khi thực thi

**cancel(false)** phù hợp khi muốn ngăn task chưa bắt đầu, không yêu cầu interrupt task đang chạy. Để ví dụ không phụ thuộc vào việc “kịp cancel trước 100 ms”, ta **cố ý giữ worker duy nhất** bằng một latch, rồi đặt task thứ hai vào queue và cancel ngay khi nó chắc chắn chưa có worker.

Tệp **CancelDelayedTaskDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class CancelDelayedTaskDemo {
    public static void main(String[] args) throws Exception {
        ScheduledExecutorService scheduler =
                Executors.newSingleThreadScheduledExecutor();

        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicBoolean ran = new AtomicBoolean();

        try {
            Future<?> blocker = scheduler.submit(() -> {
                entered.countDown();
                try {
                    release.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            });

            entered.await(); // Worker duy nhất đang bị giữ.

            ScheduledFuture<?> delayed = scheduler.schedule(
                    () -> ran.set(true),
                    0, TimeUnit.MILLISECONDS
            );

            boolean cancelled = delayed.cancel(false);

            release.countDown();
            blocker.get();

            scheduler.shutdown();
            scheduler.awaitTermination(5, TimeUnit.SECONDS);

            System.out.println("cancel accepted = " + cancelled);
            System.out.println("task ran = " + ran.get());
            System.out.println("cancelled = " + delayed.isCancelled());
        } finally {
            release.countDown();
            scheduler.shutdownNow();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 CancelDelayedTaskDemo.java
java CancelDelayedTaskDemo
~~~

Stdout:

~~~text
cancel accepted = true
task ran = false
cancelled = true
~~~

**Vì sao kết quả được xác định?**

1. entered.await() xác nhận **blocker đã bắt đầu** và đang giữ worker duy nhất.
2. Task delayed có delay=0 nhưng không thể chạy vì worker còn chờ latch.
3. Main gọi cancel(false) khi delayed còn pending, nên hủy thành công.
4. Khi release mở, blocker kết thúc và worker không thực thi task đã hủy.
5. Future bị hủy có isCancelled() true; **delayed.get() nếu gọi sẽ ném CancellationException**.

Cẩn thận trong production: cancel(false) có thể trả false khi task đã hoàn tất hoặc bị hủy trước đó; trả true không có nghĩa side effect từ mọi task khác sẽ bị rollback. Khi task đã bắt đầu, **cancel(false) không yêu cầu interrupt**, và task đang thực thi có thể vẫn tiếp tục chạy.

## 9. cancel(true), interrupt và cleanup

**ScheduledFuture.cancel(true)** cố hủy Future và **có thể interrupt thread đang chạy** nếu task đã bắt đầu. Nó không cưỡng chế dừng code Java theo cách an toàn. Việc dừng phụ thuộc vào task có kiểm tra trạng thái interrupt, dùng blocking API interruptible và dọn tài nguyên hay không.

Mẫu task hợp tác:

~~~java
// Minh họa thân một Runnable, không phải file độc lập.
Runnable job = () -> {
    try {
        while (!Thread.currentThread().isInterrupted()) {
            // Xử lý từng lô ngắn, không giữ lock xuyên thời gian dài.
            processBatch();
        }
    } finally {
        releaseOwnedResources();
    }
};
~~~

Ở đây **processBatch()** và **releaseOwnedResources()** là các phương thức giả định. Nếu processBatch thực hiện blocking API ném InterruptedException, cần xử lý bằng cách propagate hoặc restore interrupt flag rồi thoát theo giao thức.

**Một điểm rất quan trọng:** cancel(true) có thể chuyển Future sang canceled **trước khi code task thực sự kết thúc**. Vì vậy không suy ra “Future canceled” đồng nghĩa side effect đã chấm dứt hoặc resource đã được cleanup. Muốn đợi cleanup, cần giao thức completion riêng nếu việc ấy quan trọng.

Nếu đang giữ Semaphore permit, ReentrantLock hoặc file handle, task phải dùng **try/finally** để giải phóng đúng quyền sở hữu. Không để cleanup phụ thuộc vào task luôn chạy hết đến dòng cuối.

## 10. Ví dụ 3: Future.get(timeout) không hủy task

Ta tạo task **đã bắt đầu nhưng đang đợi một latch chưa mở**, rồi gọi get với timeout. Vì latch chưa được mở, Future chắc chắn **chưa hoàn tất** ở thời điểm chờ; sau timeout, main mở latch và đợi lấy giá trị cuối.

Tệp **ScheduledFutureTimeoutDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class ScheduledFutureTimeoutDemo {
    public static void main(String[] args) throws Exception {
        ScheduledExecutorService scheduler =
                Executors.newSingleThreadScheduledExecutor();

        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            ScheduledFuture<Integer> future = scheduler.schedule(() -> {
                entered.countDown();
                release.await();
                return 42;
            }, 0, TimeUnit.MILLISECONDS);

            entered.await();

            boolean timedOut = false;
            try {
                future.get(10, TimeUnit.MILLISECONDS);
            } catch (TimeoutException ex) {
                timedOut = true;
            }

            release.countDown();
            int value = future.get();

            System.out.println("wait timed out = " + timedOut);
            System.out.println("final value = " + value);
            System.out.println("cancelled = " + future.isCancelled());
        } finally {
            release.countDown();
            scheduler.shutdownNow();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ScheduledFutureTimeoutDemo.java
java ScheduledFutureTimeoutDemo
~~~

Stdout:

~~~text
wait timed out = true
final value = 42
cancelled = false
~~~

**Phân tích:**

- Khi main gọi get(10ms), worker đã vào Callable và vẫn phải chờ **release**.
- Vì main **chưa mở release**, Future chưa thể hoàn tất bình thường; get hết timeout và ném TimeoutException.
- Timeout chỉ làm **caller ngừng chờ**, không gọi cancel().
- Main mở release, task trả 42 và Future.get() lần sau nhận kết quả.
- isCancelled() false vì Future chưa từng bị cancel.

Đừng biến 10 ms thành phép đo tốc độ scheduler: ta chỉ dùng nó để minh họa một **đường timeout có thể kiểm chứng**, không suy ra task luôn bắt đầu/hoàn tất trong 10 ms.

## 11. Exception trong scheduled task

Nếu Callable hoặc Runnable ném unchecked exception, **ScheduledFuture.get()** của task chạy một lần ném **ExecutionException**, và **getCause()** cung cấp nguyên nhân. Exception không tự động chạy lại task.

Tệp **ScheduledFailureDemo.java**:

~~~java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;

public class ScheduledFailureDemo {
    public static void main(String[] args) throws Exception {
        ScheduledExecutorService scheduler =
                Executors.newSingleThreadScheduledExecutor();

        try {
            ScheduledFuture<Integer> future = scheduler.schedule(
                    () -> {
                        throw new IllegalStateException("invalid state");
                    },
                    0, TimeUnit.MILLISECONDS
            );

            try {
                future.get();
            } catch (ExecutionException ex) {
                System.out.println(
                    "cause = " + ex.getCause().getClass().getSimpleName()
                );
            }

            System.out.println("done = " + future.isDone());
            System.out.println("cancelled = " + future.isCancelled());
        } finally {
            scheduler.shutdownNow();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ScheduledFailureDemo.java
java ScheduledFailureDemo
~~~

Stdout:

~~~text
cause = IllegalStateException
done = true
cancelled = false
~~~

**Khác biệt với rejection:** nếu scheduler đã shutdown hoặc từ chối đăng ký, **schedule()** có thể ném **RejectedExecutionException ngay tại thread gửi**, không trả Future hợp lệ. Nếu đã nhận lịch rồi task ném exception khi chạy, lỗi được quan sát bằng Future.get().

**Đừng bỏ qua Future** của tác vụ quan trọng. Một exception trong tác vụ đã được schedule có thể không xuất hiện như exception ở thread đã gửi task; phải có kênh quan sát lỗi, metrics và chính sách retry phù hợp.

## 12. Lịch một lần và lịch định kỳ khác nhau thế nào?

ScheduledExecutorService còn có hai phương thức chạy lặp:

~~~java
// Minh họa:
scheduler.scheduleAtFixedRate(
        task, 0, 100, TimeUnit.MILLISECONDS
);

scheduler.scheduleWithFixedDelay(
        task, 0, 100, TimeUnit.MILLISECONDS
);
~~~

Các đoạn này minh họa tham số; task là Runnable đã khai báo. Dù tên phương thức đều có schedule, **ý nghĩa lịch lặp khác với schedule() một lần**.

### scheduleAtFixedRate: nhắm tới các mốc theo chu kỳ

Với initialDelay=0, period=100ms, các mốc dự kiến lần lượt là khoảng:

~~~text
t0, t0 + 100ms, t0 + 200ms, t0 + 300ms, ...
~~~

Nếu lần chạy trước mất thời gian dài, lần chạy sau có thể bắt đầu **muộn**. Theo hợp đồng ScheduledThreadPoolExecutor, các lần chạy liên tiếp **của cùng một periodic task không chồng lấn**, dù executor có nhiều worker. Nếu task chạy lâu hơn period, các lần sau có thể nối tiếp nhau mà không có khoảng trống dự kiến.

### scheduleWithFixedDelay: đợi sau khi lần chạy trước kết thúc

Với delay=100ms:

~~~text
Run 1 kết thúc
    |
    +-- chờ 100ms --> Run 2 bắt đầu
                           |
                      Run 2 kết thúc
                           |
                           +-- chờ 100ms --> Run 3 ...
~~~

Fixed-delay thường dễ hiểu cho polling có điều kiện hoặc task chỉ nên bắt đầu lại sau khi lần trước xong một khoảng. Nó không cố bám vào các mốc cố định từ thời điểm ban đầu.

### Bảng so sánh

| Ý định | API | Đặc điểm |
| --- | --- | --- |
| Chạy đúng **một lần** sau khoảng trì hoãn | **schedule(task, delay, unit)** | Future hoàn tất khi task hoàn tất/lỗi/hủy |
| Chạy lặp theo nhịp kể từ mốc ban đầu | **scheduleAtFixedRate** | Mốc lý tưởng theo period; có thể trễ, không overlap cùng một periodic task |
| Chạy lặp sau khoảng nghỉ từ kết thúc lần trước | **scheduleWithFixedDelay** | Khoảng nghỉ giữa hai lần chạy |
| Đợi đúng **một giờ lịch địa phương** mỗi ngày | Cần tính lại thời điểm theo ngày/zone | Không mặc nhiên dùng period=24h vì DST/đổi giờ |
| Công việc cần bền vững qua JVM restart | Cần persistence và giao thức khác | ScheduledExecutorService chỉ giữ lịch trong process |

**Task định kỳ ném exception** sẽ làm các lần chạy tiếp theo **bị suppress** theo hợp đồng, thay vì tự retry mãi. Future của task periodic **không hoàn tất bình thường** chỉ vì đã chạy một lượt: nó đại diện cho cả chuỗi lặp; chỉ trở thành done khi bị hủy hoặc kết thúc bất thường. Không gọi periodicFuture.get() vô thời hạn rồi kỳ vọng nó trả sau tick đầu.

## 13. Ví dụ 4: hủy lịch chạy định kỳ sau ba lần

Tệp **PeriodicStopDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class PeriodicStopDemo {
    public static void main(String[] args) throws Exception {
        ScheduledExecutorService scheduler =
                Executors.newSingleThreadScheduledExecutor();

        AtomicInteger runs = new AtomicInteger();
        CountDownLatch threeRuns = new CountDownLatch(3);

        try {
            ScheduledFuture<?> periodic =
                    scheduler.scheduleWithFixedDelay(
                            () -> {
                                runs.incrementAndGet();
                                threeRuns.countDown();
                            },
                            0, 10, TimeUnit.MILLISECONDS
                    );

            threeRuns.await();
            boolean stopped = periodic.cancel(false);

            System.out.println("at least three = " + (runs.get() >= 3));
            System.out.println("cancelled = " + stopped);
            System.out.println("future cancelled = "
                    + periodic.isCancelled());
        } finally {
            scheduler.shutdownNow();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 PeriodicStopDemo.java
java PeriodicStopDemo
~~~

Stdout:

~~~text
at least three = true
cancelled = true
future cancelled = true
~~~

threeRuns.await() bảo đảm main **không hủy trước khi đạt ba lượt**; trong lúc main chuẩn bị cancel, một lượt kế tiếp *có thể* đã chạy, nên **không in runs == 3 như một hằng số**. Đây là nguyên tắc quan trọng để kiểm thử concurrency: phát biểu **bất biến bảo đảm**, không khẳng định lịch xen kẽ tình cờ.

**Periodic future** không tự kết thúc bình thường. cancel(false) hủy các lần chạy tiếp theo; khi hủy thành công, isCancelled() true. Việc hủy không có nghĩa những side effect của ba lượt trước được hoàn tác.

## 14. Shutdown của scheduler có hai chính sách đặc biệt

**ScheduledThreadPoolExecutor** là triển khai nền tảng của các factory scheduler trong JDK. Khi dùng trực tiếp, nó cung cấp chính sách kiểm soát các task đã được đăng ký trước khi shutdown.

| Chính sách | Giá trị mặc định | Ý nghĩa |
| --- | --- | --- |
| **getExecuteExistingDelayedTasksAfterShutdownPolicy()** | **true** | Task **one-shot đã hẹn trước shutdown** vẫn có thể chạy sau khi shutdown khi đủ hạn |
| **getContinueExistingPeriodicTasksAfterShutdownPolicy()** | **false** | Các lượt chạy periodic tương lai không tiếp tục sau shutdown |
| **getRemoveOnCancelPolicy()** | **false** | Task đã cancel không nhất thiết được gỡ ngay khỏi queue chờ |

Các setter tương ứng:

~~~java
// Minh họa với ScheduledThreadPoolExecutor scheduler đã tạo:
scheduler.setExecuteExistingDelayedTasksAfterShutdownPolicy(false);
scheduler.setContinueExistingPeriodicTasksAfterShutdownPolicy(false);
scheduler.setRemoveOnCancelPolicy(true);
~~~

**Không nhầm shutdown với cancel tất cả lịch đã có.** Với mặc định **execute-existing-delayed=true**, nếu bạn schedule một task chạy sau 1 ngày rồi gọi shutdown(), executor có thể giữ tài nguyên chờ task đó tới hạn thay vì terminated ngay.

### shutdown() khác shutdownNow()

- **shutdown()** ngừng nhận lịch mới. Task đã đăng ký sẽ được xử lý theo các policy ở trên; phương thức **không tự block chờ hoàn tất**.
- **shutdownNow()** cố ngắt task đang chạy và trả về các task chưa bắt đầu; không bảo đảm task đang thực thi dừng ngay.
- **awaitTermination(timeout, unit)** chờ executor kết thúc; trả boolean. Nếu false, không được mặc định coi cleanup đã xong.
- Task có thể bị **RejectedExecutionException** khi gọi schedule sau shutdown.
- Nếu cấu hình periodic-continue=true, periodic task có thể tiếp tục và giữ executor không terminated cho đến khi cancel/shutdownNow hoặc thay đổi policy.

### Ví dụ 5: one-shot delayed task vẫn chạy sau shutdown mặc định

Tệp **ScheduledShutdownDemo.java**:

~~~java
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class ScheduledShutdownDemo {
    public static void main(String[] args) throws Exception {
        ScheduledThreadPoolExecutor scheduler =
                new ScheduledThreadPoolExecutor(1);

        try {
            ScheduledFuture<Integer> future = scheduler.schedule(
                    () -> 42,
                    20, TimeUnit.MILLISECONDS
            );

            scheduler.shutdown(); // Mặc định vẫn cho delayed one-shot chạy.
            System.out.println("value after shutdown = " + future.get());
            scheduler.awaitTermination(5, TimeUnit.SECONDS);
        } finally {
            scheduler.shutdownNow();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ScheduledShutdownDemo.java
java ScheduledShutdownDemo
~~~

Stdout:

~~~text
value after shutdown = 42
~~~

Task được **đăng ký trước shutdown()** và chính sách mặc định cho phép one-shot task tiếp tục chạy sau khi executor ngừng nhận task mới. Vì vậy future.get() vẫn trả 42. Khoảng 20ms là độ trễ tối thiểu để đủ điều kiện, không phải SLA của thực thi.

Nếu đổi thành **setExecuteExistingDelayedTasksAfterShutdownPolicy(false)** trước khi shutdown, những task one-shot chưa đến hạn sẽ bị cancel theo policy thay vì được để lại tới lúc chạy. **Phải quyết định rõ mong muốn của ứng dụng:** khi dừng hệ thống, các lịch cũ nên chạy cho xong, bị hủy, hay được lưu lại ở nơi bền vững để phục hồi?

## 15. Task đã cancel có thể còn trong queue

Đối với **ScheduledThreadPoolExecutor**, task bị cancel **không nhất thiết được loại khỏi queue ngay lập tức** theo mặc định. Một task hẹn trong nhiều giờ, bị cancel sau vài giây, có thể còn được lưu trong delayed queue đến khi tới hạn; số lượng lớn có thể gây giữ bộ nhớ không cần thiết.

Khi tự tạo ScheduledThreadPoolExecutor, có thể cấu hình:

~~~java
// Mã minh họa:
ScheduledThreadPoolExecutor scheduler =
        new ScheduledThreadPoolExecutor(2);
scheduler.setRemoveOnCancelPolicy(true);
~~~

Chính sách này giúp những task bị cancel được gỡ khỏi queue ngay khi hủy theo hợp đồng của executor, giảm retention và thuận tiện quản trị số lượng lịch. Nó **không khiến task đã bắt đầu bị cưỡng chế dừng** và không thay thế việc thiết kế quản lý số lượng lịch.

**Không sử dụng queue.size() làm bộ điều khiển nhận việc theo kiểu check rồi schedule**: giữa lúc kiểm tra và gửi lịch, nhiều thread khác có thể đăng ký; số liệu có thể thay đổi ngay. Nếu phải giới hạn “đang có tối đa K lịch được nhận”, dùng admission control có primitive nguyên tử/permit và hoàn trả permit trên **mọi trạng thái cuối** theo một giao thức được chứng minh.

### Khi nào dùng ScheduledThreadPoolExecutor trực tiếp?

Khi cần các setter policy, thread factory, rejection handler hoặc cấu hình/chẩn đoán cụ thể. Đối với one-shot delay đơn giản, factory **Executors.newSingleThreadScheduledExecutor()** hoặc **newScheduledThreadPool(n)** đủ rõ ràng. Tránh ép kiểu executor trả về từ factory sang ScheduledThreadPoolExecutor: wrapper có thể che triển khai cụ thể; API type của factory không hứa một cast như vậy hợp lệ.

## 16. Hẹn lịch theo thời điểm trên đồng hồ thực

**schedule(delay, unit)** nhận **độ trễ tương đối**. Nếu nghiệp vụ nói “chạy lúc 09:00 theo múi giờ cụ thể”, bạn cần tính khoảng cách giữa **thời điểm hiện tại** và **thời điểm mục tiêu**.

Ví dụ minh họa trong một chương trình Java đã khai báo scheduler:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.TimeUnit;

// target là một Instant đã được xác định:
long delayMillis = Math.max(
        0L,
        Duration.between(Instant.now(), target).toMillis()
);
scheduler.schedule(task, delayMillis, TimeUnit.MILLISECONDS);
~~~

Đây là **mảnh code minh họa**, không phải file Java có main(): cần khai báo **target**, **task**, **scheduler** và áp dụng đúng import trong class.

### Những yếu tố dễ bỏ sót

- **Instant** là một thời điểm tuyệt đối; **LocalDateTime** không mang múi giờ nên tự nó không xác định duy nhất một instant toàn cầu.
- Nếu người dùng muốn “09:00 theo Asia/Ho_Chi_Minh”, phải dùng **ZoneId** tương ứng và tính **ZonedDateTime** thích hợp.
- Sau khi đã tính độ trễ, scheduler đang giữ **relative delay**. Nếu đồng hồ hệ thống bị chỉnh về trước/sau, scheduler không tự hiểu lại ý nghĩa lịch theo giờ treo trên tường.
- Nếu lịch lặp “09:00 mỗi ngày” phải tính **ngày kế tiếp với zone**, không đơn giản lặp period=24 HOURS trong mọi múi giờ có DST.
- Nếu target đã ở quá khứ, **Math.max(0, ...)** ở trên khiến task được gửi để chạy sớm nhất có thể, nhưng có thể nghiệp vụ muốn **từ chối lịch quá hạn**; phải quyết định theo hợp đồng.
- Duration lớn hoặc conversion có thể overflow; đối với lịch rất xa hoặc phức tạp, cần validate khoảng thời gian và cơ chế persistent scheduler thích hợp.
- Thay đổi timezone/calendar rule và daylight-saving có thể làm giờ địa phương trùng lặp hoặc không tồn tại ở một số vùng. Hãy định nghĩa rõ ứng xử khi gặp các trường hợp này.

### “Delay 24 giờ” khác “cùng giờ ngày mai”

Tại một khu vực có đổi giờ mùa hè, khoảng cách giữa cùng một giờ địa phương ở hai ngày liên tiếp có thể **23 giờ hoặc 25 giờ**. Dùng TimeUnit.DAYS chỉ biểu diễn khoảng tương đối theo đơn vị thời gian; nó không hiểu lịch địa phương.

Đối với lịch theo calendar, cần xây task hẹn lần tới từ **ZonedDateTime**; khi đã chạy xong mới tính mục tiêu tiếp theo, đồng thời xử lý downtime/restart. Đây là nghiệp vụ khác với một ScheduledFuture hẹn chạy một lần.

## 17. Lập lịch trì hoãn không tương đương lưu công việc bền vững

**ScheduledExecutorService giữ lịch trong bộ nhớ JVM**. Nếu process crash, server restart, JVM bị kill, hay hệ thống đổi deployment, các lịch chưa chạy thường **không được khôi phục tự động**.

Nếu một workflow bắt buộc bảo đảm:

- Không mất lịch dù process chết.
- Nhiều JVM không xử lý trùng cùng một lịch.
- Có trạng thái retry và backoff bền vững.
- Task được thực hiện ít nhất một lần hoặc được xác nhận rõ.
- Cần audit, replay, giới hạn số lần thử hoặc dead-letter policy.

...thì phải thiết kế **persistent job store/queue**, idempotency và coordination ở nơi các process cùng truy cập. Một Java executor trong JVM không tự bảo đảm exactly-once execution toàn hệ thống.

### Hẹn gửi thông báo hoặc thanh toán

Ví dụ chương trình schedule task gửi email sau 10 phút. Nếu user hủy trước hạn, gọi future.cancel(false) có thể ngăn task pending. Nhưng nếu email đã bắt đầu gửi, cancel có thể không rút lại email. Nếu JVM restart, future cũ cũng không sống lại.

Với **thao tác tài chính hoặc side effect không thể đảo ngược**, cần lưu trạng thái, idempotency key, xử lý duplicate và giao thức xác nhận; không dựa vào ScheduledFuture như source of truth.

## 18. Timeout, deadline và quyền hủy

**ScheduledExecutorService** quản lý lúc task đủ điều kiện chạy, còn **Future.get(timeout)** quản lý thời gian caller chờ.

| Tình huống | Công cụ | Ý nghĩa |
| --- | --- | --- |
| Muốn task bắt đầu không sớm hơn 5 giây sau đăng ký | schedule(task, 5, SECONDS) | Delay trước khi task đủ điều kiện |
| Caller chỉ có 1 giây chờ kết quả | future.get(1, SECONDS) | Caller có thể timeout, task vẫn chạy |
| Không muốn task pending chạy nữa | future.cancel(false) | Cố hủy task, không yêu cầu interrupt worker |
| Muốn yêu cầu ngắt task đang chạy | future.cancel(true) | Yêu cầu hủy/interrupt hợp tác, không rollback |
| Toàn bộ thao tác có deadline | Tính remaining time cho từng bước | Không cộng nguyên timeout lặp lại cho từng bước |
| Muốn biết scheduler dừng thật chưa | awaitTermination(timeout, unit) | Quan sát lifecycle sau shutdown |

Khi có nhiều lần chờ trong một deadline chung, tính **thời gian còn lại** từ đồng hồ đơn điệu **System.nanoTime()** (với tính toán an toàn với overflow), thay vì cấp lại toàn bộ budget cho mỗi API.

**Không dùng Thread.sleep(delay) thay cho schedule** nếu mục tiêu là “đăng ký việc để worker thực thi sau này” và caller cần làm việc khác: sleep chặn chính thread gọi, không cung cấp ScheduledFuture/cancel/queue semantics tương đương.

## 19. Các lỗi thiết kế thường gặp

| Sai lầm | Vấn đề | Cách sửa |
| --- | --- | --- |
| Nghĩ schedule(delay=100ms) cam kết đúng 100ms sẽ chạy | Task còn phụ thuộc worker và OS scheduler | Diễn đạt là “đủ điều kiện sau delay”; đo lateness |
| Chặn worker duy nhất bằng I/O dài | Các task đến hạn phía sau bị trễ | Không block worker lâu, chọn pool và phân tách workload |
| Dùng schedule() thay timer bền vững qua restart | Lịch bị mất khi JVM chết | Persistent job store nếu cần durability |
| Dùng scheduleAtFixedRate cho công việc chỉ muốn một lần | Task bị lặp không mong muốn | Dùng schedule() |
| Dùng periodic future.get() để đợi tick đầu | get có thể không hoàn tất bình thường | Dùng CountDownLatch/Condition hoặc tín hiệu riêng |
| Tin shutdown() lập tức hủy mọi delayed task | Mặc định one-shot delayed vẫn được chạy | Cấu hình policy theo lifecycle |
| Hủy nhiều lịch rất xa nhưng bỏ mặc queue | Giữ task canceled lâu | setRemoveOnCancelPolicy(true), giới hạn lịch |
| Cancel(true) rồi cho rằng đã rollback I/O | Future hủy không đảo ngược side effect | Hủy hợp tác và idempotency |
| Quên xem ExecutionException của Future | Không nhận biết task đã lỗi | Thu Future và xử lý cause |
| Timeout get() rồi coi task đã dừng | Task vẫn có thể đang chạy | Chỉ cancel theo policy, theo dõi completion thực tế |
| Dùng clock wall-time để đo khoảng chờ | Đồng hồ có thể được điều chỉnh | Dùng nanoTime cho elapsed/deadline |
| Dùng fixed-rate 24h để biểu diễn mỗi ngày 09:00 ở zone có DST | Giờ địa phương có thể dịch | Tính ZonedDateTime của từng ngày |
| Chỉ dùng một worker rồi chờ task con trong chính scheduler đó | Thread-starvation deadlock | Không block đợi task cần cùng worker |
| Đăng ký vô hạn delayed tasks | Queue/memory tăng không kiểm soát | Admission control, giới hạn và telemetry |
| Tự cast factory scheduler sang ScheduledThreadPoolExecutor | Wrapper có thể không có kiểu đó | Tạo ScheduledThreadPoolExecutor trực tiếp nếu cần policy |
| Đặt ThreadLocal làm trạng thái lịch dài hạn | Worker có thể bị thay và context task tái sử dụng | Lưu state với lifecycle rõ, cleanup ThreadLocal |
| Thấy Future done rồi coi nghiệp vụ thành công | Done gồm lỗi/cancellation | Kiểm tra get()/isCancelled() và status business |

## 20. Kiểm thử lịch trì hoãn mà không phụ thuộc timing ngẫu nhiên

Tạo test đúng cho scheduling có hai phần: **hợp đồng thời gian** và **hợp đồng trạng thái**.

**Nên kiểm tra:**

1. **Callable one-shot** trả đúng kết quả qua Future.get().
2. **Runnable one-shot** hoàn tất, Future.get() trả null.
3. **Cancel trước khi task bắt đầu**: giữ worker bằng latch, đặt task vào queue, cancel(false), xác nhận task không chạy.
4. **Timeout của caller**: giữ Callable trên latch rồi dùng Future.get(timeout), xác nhận task vẫn có thể hoàn tất sau khi caller mở latch.
5. **Task ném exception**: Future.get() ném ExecutionException với cause mong đợi.
6. **Periodic scheduling**: dùng CountDownLatch đếm một số tick rồi cancel; không assert một số tick chính xác sau khi main có thể bị scheduler trễ.
7. **Shutdown policies**: schedule trước shutdown, xác minh task delayed chạy/hủy theo policy cấu hình.
8. **Overload**: cố tình giữ tất cả workers bận rồi xem delayed task chỉ chạy khi worker rảnh; kiểm tra memory/backlog nếu gửi nhiều lịch.
9. **Lịch theo calendar**: kiểm tra đổi ngày, múi giờ và trường hợp DST nếu hệ thống cần.
10. **Completion/side effects**: phân biệt “task đã chạy”, “đã retry”, “external operation commit” và “Future canceled”.

**Không nên kiểm tra bằng giả định:** “Thread.sleep(100) xong thì task đã chạy”. Điều đó có thể đúng trên máy này nhưng sai khi hệ thống quá tải. Ưu tiên latch, Future, thông báo trạng thái và invariant. Nếu cần đo thời gian, dùng ngưỡng phù hợp với môi trường và không biến con số timer chính xác thành yêu cầu mà API không hứa.

## 21. Checklist đưa vào ứng dụng

**Thiết kế:**

- [ ] Công việc chạy **một lần** hay **định kỳ**? Đã chọn đúng API?
- [ ] Delay tương đối hay lịch theo giờ địa phương? Đã xác định zone?
- [ ] Có cần kết quả, exception, cancel hoặc deadline? Đã giữ ScheduledFuture?
- [ ] Có yêu cầu lịch sống qua restart/multi-JVM không? Nếu có, có persistent coordinator?
- [ ] Task có thể được thực thi lại không? Có idempotency với external side effect?

**Tải và tài nguyên:**

- [ ] Số worker có phù hợp với CPU-bound/blocking I/O và độ trễ kỳ vọng?
- [ ] Có task dài chiếm worker làm các task sau quá hạn?
- [ ] Số lượng delayed tasks có được giới hạn hoặc đo queue growth?
- [ ] Có xử lý canceled-task retention qua removeOnCancelPolicy khi cần?
- [ ] Có metric scheduled, started, completed, failed, cancelled, overdue, queue size?

**Vòng đời:**

- [ ] Đã quyết định existing delayed tasks có chạy sau shutdown hay bị cancel?
- [ ] Đã quyết định periodic tasks có tiếp tục sau shutdown không?
- [ ] Có shutdown/awaitTermination và fallback phù hợp?
- [ ] Xử lý RejectedExecutionException nếu producer gửi sau shutdown?
- [ ] Nếu caller timeout hoặc Future cancel, task có cleanup hợp tác?
- [ ] Không giữ lock hoặc chiếm worker để đợi task khác phụ thuộc cùng executor?

## 22. Câu hỏi tự kiểm tra

**1. schedule(task, 500, MILLISECONDS) có bảo đảm task bắt đầu chính xác sau 500 ms không?**  
Không. Task **đủ điều kiện** sau delay, còn thời điểm thực sự chạy phụ thuộc worker/scheduler.

**2. ScheduledFuture.getDelay() bằng -100 ms có chắc task đã chạy xong không?**  
Không. Task có thể đã quá hạn nhưng worker chưa rảnh.

**3. Với schedule(Runnable, ...), get() trả giá trị gì khi thành công?**  
**null**, vì Runnable không trả V qua call().

**4. Future.get(timeout) ném TimeoutException có tự hủy lịch không?**  
Không. Caller chỉ ngừng chờ, task có thể vẫn tiếp tục.

**5. cancel(false) và cancel(true) khác nhau ở điểm nào?**  
cancel(false) không yêu cầu interrupt task đang chạy; cancel(true) có thể yêu cầu interrupt, nhưng không ép rollback side effect.

**6. Một periodic task có thể tự chạy hai lần chồng lên nhau trong ScheduledThreadPoolExecutor với bốn worker không?**  
Các lượt **của cùng periodic task** không chồng lấn theo hợp đồng; những periodic task khác nhau có thể chạy đồng thời.

**7. Vì sao periodicFuture.get() có thể chờ mãi?**  
Vì Future đại diện cho cả chuỗi lặp, không hoàn tất bình thường sau một tick. Nó cần bị hủy hoặc kết thúc bất thường để đạt trạng thái cuối.

**8. shutdown() có hủy task one-shot đã được hẹn từ trước nhưng chưa đến hạn theo mặc định không?**  
Không. ScheduledThreadPoolExecutor mặc định cho phép existing delayed one-shot task thực thi sau shutdown.

**9. Dùng scheduleAtFixedRate với period=24 HOURS có hẹn đúng 09:00 giờ địa phương mỗi ngày ở mọi timezone không?**  
Không. Lịch theo giờ địa phương có thể thay đổi offset do DST; phải tính lại thời điểm calendar tương ứng.

**10. Single-thread scheduled executor có thể deadlock khi nào?**  
Khi task đang chạy chiếm worker duy nhất rồi đợi Future của task khác đang chờ trong chính executor đó.

**11. Có thể dựa vào setRemoveOnCancelPolicy(true) để chắc chắn task đã chạy không?**  
Không. Nó chỉ nói về việc gỡ task đã **bị hủy** khỏi queue khi cancel, không chứng minh đã chạy.

**12. ScheduledExecutorService có bảo đảm lịch còn sau restart JVM không?**  
Không. Lịch nằm trong bộ nhớ process; cần persistence/coordination riêng khi nghiệp vụ yêu cầu.

## 23. Tổng kết

**ScheduledExecutorService** là công cụ của JDK giúp **đăng ký công việc chạy sau một độ trễ tương đối** và theo dõi nó bằng **ScheduledFuture**. Phương thức **schedule()** phục vụ tác vụ **một lần**; periodic methods giải quyết một mục tiêu khác là chạy lặp theo **fixed rate** hoặc **fixed delay**.

Điều quan trọng nhất là phân biệt:

- **Đủ hạn chạy** không đồng nghĩa **đã bắt đầu chạy**.
- **Future.get(timeout) hết hạn** không đồng nghĩa **task bị hủy**.
- **Future.cancel()** không đồng nghĩa **mọi side effect đã được hoàn tác**.
- **shutdown()** không nhất thiết **hủy mọi lịch đã đăng ký**.
- **Một scheduler trong JVM** không tương đương **dịch vụ lập lịch bền vững, chính xác giờ lịch và không trùng giữa nhiều process**.

Hãy chọn số worker phù hợp, kiểm soát lượng lịch pending, giữ và quan sát Future, hiểu cancellation/shutdown policies, thiết kế lịch giờ thực với múi giờ rõ ràng và kiểm thử bằng **invariant cùng blocking primitives** thay vì kỳ vọng sleep chính xác.
