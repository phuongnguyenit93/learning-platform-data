# Đánh giá rủi ro của queue không giới hạn trong Java Executor Framework

> **Luận điểm:** Một executor có worker hữu hạn nhưng chấp nhận gần như mọi task vào queue không giới hạn **không tự mở rộng năng lực xử lý**. Khi tốc độ nhận việc lớn hơn tốc độ hoàn thành, backlog tăng, task giữ thêm bộ nhớ, thời gian chờ tăng, request có thể hết deadline và cuối cùng JVM có thể gặp `OutOfMemoryError`. Queue lớn cũng che giấu quá tải vì `submit()` vẫn có thể trả về nhanh. Cần đánh giá **capacity, throughput, memory, latency, rejection, cancellation và shutdown** như một hệ thống.

Bài thuộc nhóm **Executor Framework** của **Java concurrency nói chung**. Các ví dụ dùng Java SE 17+ (`ThreadPoolExecutor`, `Executors`, `BlockingQueue`, `Future`); không dùng Spring.

## 1. Queue không giới hạn là gì?

Một queue được gọi là *unbounded* khi ứng dụng không đặt một dung lượng hữu hạn đủ nhỏ để kiểm soát workload. Chẳng hạn `new LinkedBlockingQueue<>()` có capacity mặc định `Integer.MAX_VALUE`: về kỹ thuật nó có giới hạn số phần tử, nhưng heap thường cạn trước khi đạt giới hạn này. Vì vậy **unbounded không có nghĩa JVM có tài nguyên vô hạn**.

Mô hình cơ bản:

~~~text
Producer threads
       |
       | execute(task) / submit(task)
       v
[ Waiting task queue ] ---> worker-1 ---> complete
                         -> worker-2 ---> complete
                         -> worker-N ---> complete

Nếu task đến > task hoàn thành trong một khoảng dài:
     queue tăng -> chờ lâu -> heap retention -> GC/timeout tăng
~~~

`execute` hoặc `submit` thành công có nghĩa task **đã được executor chấp nhận theo hợp đồng**, không phải đã bắt đầu, đã xử lý thành công hay đã trả kết quả đúng deadline. Một số task còn có thể nằm trong queue cho đến khi pool shutdown, bị hủy, hoặc task trước đó kết thúc.

### Unbounded queue không phải unbounded thread pool

| Thiết kế | Hành vi chính | Rủi ro khi quá tải |
| --- | --- | --- |
| `Executors.newFixedThreadPool(n)` | Cố định số worker, unbounded work queue | Backlog và heap tăng, latency kéo dài |
| `Executors.newSingleThreadExecutor()` | Một worker, unbounded queue, xử lý tuần tự | Head-of-line blocking, chờ rất lâu |
| `Executors.newCachedThreadPool()` | Sử dụng `SynchronousQueue` để handoff; có thể tạo nhiều worker | Bùng nổ số thread và tài nguyên native/CPU |
| `ThreadPoolExecutor` với `ArrayBlockingQueue(cap)` | Queue hữu hạn, worker min/max | Cần xử lý reject/backpressure rõ ràng |
| `ScheduledThreadPoolExecutor` | Hàng đợi nhiệm vụ theo lịch/delay và contract riêng | Retention của scheduled/cancelled tasks, backlog theo thời gian |
| `ForkJoinPool` | Work-stealing và cơ chế riêng | Không áp đặt quy tắc mở worker của `ThreadPoolExecutor` cho nó |

Không nên nhìn thấy từ “Executor” rồi mặc định mọi implementation dùng cùng một kiểu queue.

## 2. Factory method nào dễ dẫn đến backlog?

~~~java
// Snippet API, không phải một chương trình độc lập.
ExecutorService fixed = Executors.newFixedThreadPool(8);
ExecutorService single = Executors.newSingleThreadExecutor();
~~~

`newFixedThreadPool(8)` cung cấp tối đa 8 worker tái sử dụng và **shared unbounded queue** cho task chờ. `newSingleThreadExecutor` có một worker và unbounded queue. Chúng tiện lợi cho ví dụ nhỏ hoặc một số workload được giới hạn đầu vào, nhưng **không cung cấp backpressure tự động** trước khi heap chạm giới hạn.

Một cấu hình dễ gây hiểu lầm:

~~~java
// Snippet mô tả cấu hình ThreadPoolExecutor.
ThreadPoolExecutor pool = new ThreadPoolExecutor(
        4, 16, 60L, TimeUnit.SECONDS,
        new LinkedBlockingQueue<>()
);
~~~

Lập trình viên đặt `maximumPoolSize=16` rồi kỳ vọng khi tải tăng, pool tạo tới 16 worker. Trên thực tế, chiến lược `ThreadPoolExecutor` thường:

1. Khi worker count chưa đạt `corePoolSize`, cố gắng tạo core worker cho task.
2. Sau khi đạt core, ưu tiên `workQueue.offer(task)` nếu queue nhận được.
3. Chỉ khi không thể queue task mới mới xem xét tạo non-core worker tới `maximumPoolSize`.
4. Nếu vẫn không thể nhận, áp dụng `RejectedExecutionHandler`.

Với `LinkedBlockingQueue<>()` có capacity cực lớn, bước 2 thường thành công, nên worker thường chỉ ở gần **core=4**, còn task mới nối dài queue. Không nên gọi `maximumPoolSize` là hoàn toàn vô tác dụng trong mọi ngữ cảnh; nó chỉ **hiếm được kích hoạt vì lựa chọn queue**.

### Capacity là một phần của thuật toán pool

~~~text
new task
    |
    v
workerCount < corePoolSize ?
    | yes -> tạo core worker nếu có thể
    | no
    v
Executor còn RUNNING và queue.offer(task) được?
    | yes -> queue chờ worker
    | no
    v
Thử tạo worker thêm tới maximumPoolSize
    | success -> chạy task
    | failure -> rejection policy
~~~

Đây là mô hình ra quyết định tổng quát; implementation còn kiểm tra lại trạng thái executor sau enqueue để xử lý race với shutdown. Dù vậy nó đủ để lý giải **vì sao một unbounded queue làm `maximumPoolSize` khó phát huy tác dụng**.

## 3. Rủi ro 1 — tốc độ đến vượt tốc độ xử lý

Đặt:

- `λ`: số task được gửi/được chấp nhận trung bình mỗi giây.
- `μ`: số task pool hoàn thành trung bình mỗi giây ở tải đang xét.
- `Q`: số task đang chờ.

Nếu `λ > μ` trong thời gian dài, backlog sẽ tăng theo phần chênh lệch, trừ khi có cancellation, deduplication, rate limit hoặc thay đổi workload. Nếu `λ < μ` sau một burst, pool có thể drain queue, nhưng task vẫn đã phải đợi trước đó.

Ví dụ: 1.000 task đến mỗi giây, pool xử lý được 800 task mỗi giây. Backlog tăng khoảng **200 task/giây** khi điều kiện này được duy trì. Sau mười phút có thể tồn đọng khoảng **120.000 task**, trước khi tính retry và các thay đổi tải.

Đây chỉ là phép tính minh họa, không phải công thức dự báo cứng cho workload có burst, varying task duration, GC pauses và downstream saturation. Nhưng nó phản ánh giới hạn căn bản: queue **lưu công việc chứ không tự xử lý thêm công việc**.

### Vì sao overload có thể không xuất hiện ở chỉ số tiếp nhận?

Khi queue nhận task nhanh, `execute()` không block. Một API handler có thể trả về “đã nhận” trong vài micro-giây trong khi task thực sự phải chờ lâu trước khi worker bắt đầu.

Hãy đo riêng:

| Metric | Câu hỏi |
| --- | --- |
| Accepted/sec | Có bao nhiêu task đã nhận? |
| Completed/sec | Có bao nhiêu task thực sự hoàn tất? |
| Rejected/sec | Có bao nhiêu task bị từ chối? |
| Queue length / slope | Backlog đang giảm sau burst hay tăng đều? |
| Queue waiting time | Task đợi bao lâu từ submit đến start? |
| Task execution time | Khi đã bắt đầu, task mất bao lâu? |
| Failure/cancel/timeout | Task có còn giá trị hay đã thất bại? |

Chỉ nhìn **accepted** hoặc “submit không throw” là không đủ để đánh giá sức khỏe executor.

## 4. Rủi ro 2 — task giữ lại bộ nhớ và gây GC pressure

Queue chứa `Runnable` hoặc `FutureTask`; một task có thể giữ reference tới:

- Payload request, `byte[]`, JSON tree, buffer và object được parse.
- Lambda capture `this`, context, collection hoặc thông tin nghiệp vụ.
- `Callable` và cấu trúc kết quả/exception của `Future`.
- Object graph lớn vốn chỉ nên sống ngắn nếu task xử lý ngay.
- Dữ liệu của request đã timeout ở caller nhưng task còn tồn tại trong queue.

Nếu executor còn sống, nó giữ queue; queue giữ task; task giữ các object reachable theo đường reference đó. Garbage collector **không thể thu hồi** object vẫn reachable chỉ vì phía client không còn chờ kết quả.

Hệ quả:

1. Used heap tăng theo backlog, đặc biệt retained heap của captured objects.
2. Tần suất GC hoặc pause có thể tăng, làm giảm công suất xử lý thực tế.
3. Công suất giảm lại khiến backlog tăng thêm — một vòng phản hồi xấu.
4. JVM có thể gặp `OutOfMemoryError: Java heap space` trước khi queue đạt capacity lý thuyết.
5. Outage có thể đến muộn: queue đã tích dữ liệu từ lâu nhưng chỉ biểu hiện ở đợt tải tiếp theo.

**Đừng dùng số entry nhân một kích thước lambda giả định** để kết luận memory an toàn. Một lambda nhỏ có thể giữ cả một object graph lớn. Dùng heap profiler/dump và dữ liệu task thật để ước lượng retained bytes trên mỗi queued task.

`LinkedBlockingQueue` default capacity `Integer.MAX_VALUE` là giới hạn **số phần tử**, không phải memory limit cho ứng dụng.

## 5. Rủi ro 3 — độ trễ end-to-end tăng

Một task có thời gian thực thi 10 ms nhưng chờ trong queue 5 s sẽ có latency nhiều giây. Nói gần đúng:

~~~text
Total time = queue waiting time + running time + scheduling/other overhead
~~~

Nếu task phải hoàn tất trong 300 ms, một queue chứa hàng nghìn task có thể đã làm SLA **không khả thi trước khi task được bắt đầu**.

Theo Little's Law ở steady state dưới các giả thiết phù hợp: `L = λ × W`, trong đó `L` là số công việc trung bình trong hệ thống, `λ` là throughput/arrival rate tương thích và `W` là thời gian trung bình nằm trong hệ thống. Khi xét riêng queue thì phải dùng **queue length** và **queue waiting time** tương ứng, không trộn với số task active. Khi backlog đang tăng mãi, hệ thống chưa ở steady state nên không thể suy ra kết quả dài hạn đơn giản từ công thức đó.

### Head-of-line blocking

Trong FIFO queue, một task chậm hoặc blocking chiếm worker có thể làm các task phía sau chờ rất lâu:

~~~text
worker-1: blocking remote call ...
worker-2: blocking remote call ...
queue:    [fast1, fast2, fast3, ...]
~~~

Thêm dung lượng queue không làm hai worker bớt block. Cần tìm nguyên nhân giảm service rate: I/O không có timeout, locks, downstream DB/API quá tải, pool dùng chung cho task quá khác nhau, hoặc dependency cycle.

### Thread-pool starvation deadlock

Một task trong single-thread executor submit thêm một task **vào chính pool** rồi chờ `Future.get()` có thể tự kẹt: worker duy nhất bị chiếm bởi task ngoài, task trong queue không có worker để chạy.

~~~java
// Phản ví dụ minh họa; đừng chạy trực tiếp vì có thể kẹt.
ExecutorService pool = Executors.newSingleThreadExecutor();

pool.submit(() -> {
    Future<Integer> nested = pool.submit(() -> 42);
    return nested.get(); // Worker đợi task mà pool chưa thể chạy.
});
~~~

Đây là dependency deadlock, không phải riêng queue không giới hạn. Nhưng queue cho phép nhận thêm task mà không thể tiến triển, che giấu tình trạng nghẽn.

## 6. Ví dụ 1 — queue tăng dù maximumPoolSize lớn

Ví dụ được **điều phối bằng latch**, không tạo hàng triệu object để cố tình OOM. Một worker phải chờ; 5 task tiếp theo được enqueue; dù maximumPoolSize là 4, executor vẫn chỉ có một worker vì queue nhận task.

Tạo `UnboundedQueueDemo.java`, Java 17+:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class UnboundedQueueDemo {
    public static void main(String[] args) throws InterruptedException {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 4, 60L, TimeUnit.SECONDS,
                new LinkedBlockingQueue<>());

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            pool.execute(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });
            started.await();

            for (int i = 0; i < 5; i++) {
                pool.execute(() -> {});
            }

            System.out.println("max = " + pool.getMaximumPoolSize());
            System.out.println("workers = " + pool.getPoolSize());
            System.out.println("queued = " + pool.getQueue().size());
        } finally {
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
        System.out.println("completed = " + pool.getCompletedTaskCount());
    }
}
~~~

Chạy:

~~~bash
javac UnboundedQueueDemo.java
java UnboundedQueueDemo
~~~

Stdout khi thực hiện bình thường:

~~~text
max = 4
workers = 1
queued = 5
completed = 6
~~~

`started.await()` xác nhận worker đang chạy và kẹt tại `release.await()`. Năm task tiếp theo được queue nhận; pool không tăng worker trên core vì queue còn chỗ. `release.countDown()` cho worker hoàn tất rồi chạy tất cả task đã nhận; `awaitTermination()` đợi trước khi in completed count.

Không phải cứ tăng `maximumPoolSize` là giải quyết được backlog khi dùng queue không giới hạn.

## 7. Queue hữu hạn và các điều kiện admission

Một phương án phổ biến là dùng `ArrayBlockingQueue` hoặc `LinkedBlockingQueue` với capacity được đặt rõ:

~~~java
// Snippet cấu hình; không phải chương trình độc lập.
ThreadPoolExecutor pool = new ThreadPoolExecutor(
        2, 4,
        30L, TimeUnit.SECONDS,
        new ArrayBlockingQueue<>(100),
        new ThreadPoolExecutor.AbortPolicy()
);
~~~

Khi queue đầy và pool chưa đạt max, executor có thể tạo worker bổ sung. Khi queue không nhận được và không thể mở worker thêm, **task bị reject** theo `RejectedExecutionHandler`.

**Capacity=100 chỉ là ví dụ**, không phải con số chuẩn. Dung lượng cần phụ thuộc kích thước retained task, heap budget, throughput, waiting-time SLO, burst size và số worker/downstream concurrency limit. Một queue cực nhỏ có thể reject quá sớm dưới burst hợp lệ; một queue quá lớn có thể hấp thụ request đã hết giá trị.

Lưu ý capacity nói về **task chờ**, không phải tất cả task đang chạy. Tổng concurrency/in-flight bao gồm task active, task queued và có thể những task ở các tầng pipeline khác.

## 8. Ví dụ 2 — bounded queue hiện rõ overload qua rejection

Tạo `BoundedQueueDemo.java`, Java 17+:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class BoundedQueueDemo {
    public static void main(String[] args) throws InterruptedException {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(2),
                new ThreadPoolExecutor.AbortPolicy());

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            pool.execute(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });

            started.await();
            pool.execute(() -> {});
            pool.execute(() -> {});

            boolean rejected = false;
            try {
                pool.execute(() -> {});
            } catch (RejectedExecutionException expected) {
                rejected = true;
            }

            System.out.println("queued = " + pool.getQueue().size());
            System.out.println("rejected = " + rejected);
        } finally {
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
        System.out.println("completed = " + pool.getCompletedTaskCount());
    }
}
~~~

Chạy:

~~~bash
javac BoundedQueueDemo.java
java BoundedQueueDemo
~~~

Stdout bình thường:

~~~text
queued = 2
rejected = true
completed = 3
~~~

Một worker đang block, hai task nằm trong queue dung lượng 2; task thứ tư không còn chỗ và không thể tạo thêm worker vì max=1. `AbortPolicy` ném exception thay vì nhận backlog không giới hạn. Sau khi nhả latch, ba task được chấp nhận hoàn tất.

**Bounded queue không tạo thêm năng lực xử lý**, nhưng cho phép ứng dụng **phát hiện quá tải có kiểm soát**. Cần thiết kế caller xử lý `RejectedExecutionException`: từ chối, retry có backoff, thông báo client, ghi dead-letter khi cần, hoặc làm việc tại tầng phù hợp.

## 9. Chính sách rejection và tradeoff

`ThreadPoolExecutor` có các `RejectedExecutionHandler` built-in:

| Policy | Hành vi khi pool không nhận task | Cần cảnh giác |
| --- | --- | --- |
| `AbortPolicy` | Ném `RejectedExecutionException` | Caller cần xử lý, thích hợp để không mất việc âm thầm |
| `CallerRunsPolicy` | Nếu pool **chưa shutdown**, chạy task trên thread gọi `execute` | Có backpressure, nhưng tăng latency của caller và thay đổi execution context |
| `DiscardPolicy` | Bỏ task im lặng | Có thể mất việc không biết, chỉ hợp khi nghiệp vụ cho phép |
| `DiscardOldestPolicy` | Cố bỏ task ở đầu queue rồi submit lại | Mất work cũ, không phù hợp nếu thứ tự/ưu tiên quan trọng |

**Chi tiết quan trọng:** `CallerRunsPolicy` **bỏ task** khi executor đã shutdown. Vì vậy nó không bảo đảm “task nào cũng sẽ được thực hiện”. Nó chỉ là một chiến lược tạo feedback khi pool còn nhận task.

`DiscardOldestPolicy` không có nghĩa bỏ task “kém ưu tiên nhất” trong mọi queue. Với priority queue, phần tử đầu queue có ý nghĩa tùy comparator; với FIFO, đó thường là phần tử chờ lâu nhất.

### CallerRunsPolicy có thể không hợp trong request thread

Nếu task chậm vài giây, chính request/event-loop thread có thể phải thực thi và block theo. Context như thread-local, transaction, security principal hoặc lock đang giữ có thể khác worker. Chỉ dùng policy này khi **chạy inline** là hành vi hợp lệ và được chấp nhận về latency.

## 10. Ví dụ 3 — CallerRunsPolicy thực sự chạy trên submitter

Tạo `CallerRunsDemo.java`, Java 17+:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class CallerRunsDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread submitter = Thread.currentThread();
        AtomicBoolean ranInCaller = new AtomicBoolean();

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.CallerRunsPolicy());

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            pool.execute(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });
            started.await();

            pool.execute(() -> {}); // Slot queue đã được chiếm.
            pool.execute(() -> ranInCaller.set(
                    Thread.currentThread() == submitter));

            System.out.println("caller ran = " + ranInCaller.get());
            System.out.println("queued = " + pool.getQueue().size());
        } finally {
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Chạy:

~~~bash
javac CallerRunsDemo.java
java CallerRunsDemo
~~~

Stdout bình thường:

~~~text
caller ran = true
queued = 1
~~~

Vì worker đang bận và queue capacity 1 đã đầy, task thứ ba được chạy **đồng bộ trong main thread**. `execute` chỉ trả về sau khi task này xong, nên submitter chịu feedback. Kết quả được kiểm tra bằng **Thread identity**, không đoán tên thread hoặc lịch OS.

Khi chọn policy, hãy định nghĩa rõ liệu client có quyền chờ lâu hơn, callback có thể chạy ở caller, và exception từ task có được truyền về caller hay không.

## 11. Rủi ro deadline, timeout và cancellation

Một request chờ `future.get(timeout, unit)` rồi gặp `TimeoutException` không có nghĩa task đã bị hủy. Task có thể:

- Vẫn nằm trong queue trong khi client đã bỏ cuộc.
- Được worker bắt đầu sau deadline, tiêu tốn tài nguyên cho kết quả không còn ai nhận.
- Đã chạy và tạo side effect, nhưng caller retry và tạo một task thứ hai.
- Chưa xử lý cancellation và tiếp tục sau `Future.cancel(true)` nếu nó không hợp tác với interruption.

Muốn quản lý deadline đúng phải có quy tắc: ai sở hữu Future, ai gọi cancel, lúc bắt đầu task có kiểm tra deadline không, task đang thực hiện side effect có idempotency không, và trạng thái thành công/thất bại được ghi nhận ở đâu.

**Timeout việc chờ không phải timeout việc thực thi.** `Future.get(100, MILLISECONDS)` dừng đợi sau thời gian đó, không tự ngắt worker hay xóa queue entry.

### Cancelled Future có thể vẫn nằm trong work queue

Task được gửi bằng `submit` thường có wrapper `FutureTask`. `Future.cancel()` thay đổi trạng thái Future; nó không nhất thiết xóa wrapper khỏi queue ngay. `ThreadPoolExecutor.purge()` được cung cấp để loại các cancelled Future tasks còn trong work queue, nhưng có chi phí và không thay thế bounded admission.

Đối với `ScheduledThreadPoolExecutor` có phương thức `setRemoveOnCancelPolicy(true)` riêng; không nhầm method đó là API của `ThreadPoolExecutor` thường.

## 12. Ví dụ 4 — cancellation khác removal khỏi queue

Tạo `CancelledQueueDemo.java`, Java 17+:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class CancelledQueueDemo {
    public static void main(String[] args) throws InterruptedException {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(2));

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            pool.execute(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });
            started.await();

            Future<?> pending = pool.submit(() -> {});
            boolean cancelled = pending.cancel(false);

            System.out.println("cancelled = " + cancelled);
            System.out.println("queue before purge = "
                    + pool.getQueue().size());

            pool.purge();
            System.out.println("queue after purge = "
                    + pool.getQueue().size());
        } finally {
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Chạy:

~~~bash
javac CancelledQueueDemo.java
java CancelledQueueDemo
~~~

Stdout bình thường:

~~~text
cancelled = true
queue before purge = 1
queue after purge = 0
~~~

Worker đang bị giữ, nên Future chưa thể bắt đầu; cancel đánh dấu Future đã hủy nhưng wrapper còn trong queue. `purge` loại bỏ nó. Đừng suy rộng hành vi implementation này cho mọi executor tùy chỉnh; hãy xem contract và instrumentation của executor đang sử dụng.

## 13. Admission control và backpressure ngoài queue bound

Bounded queue vẫn có thể nhận nhiều task hơn mức SLA cho phép. Những phương án bổ sung:

- **Rate limiting** ở producer/API layer: tránh gửi quá tốc độ xử lý bền vững.
- **Semaphore cho in-flight budget**: giới hạn tổng số task đã nhận gồm running và queued, không chỉ queue length.
- **Rejection rõ ràng**: trả tín hiệu overload và retry-after/backoff khi nghiệp vụ cho phép.
- **Caller-runs** nếu chạy inline là hợp lệ.
- **Tách pool theo workload**: CPU-bound, blocking I/O, priority cao/thấp có thể dùng tài nguyên riêng.
- **Coalescing/deduplication**: bỏ bớt thông báo trạng thái cũ không còn giá trị, theo quy tắc nghiệp vụ.
- **Deadline-aware task**: task bị expired khi bắt đầu có thể trả kết quả hủy thay vì thực hiện side effect vô ích.
- **Durable queue ngoài JVM** khi phải chịu tải vượt bộ nhớ và cần persistence, kèm quota/retention/broker backpressure; không phải cách “làm vô hạn công suất”.

### Cẩn trọng khi tự dùng Semaphore

Một pattern ngây thơ lấy permit trước `submit` rồi release trong `finally` của worker có thể **rò permit** nếu task bị cancel **trước khi thực thi**: phần `finally` của worker không bao giờ chạy. Khi submit bị reject, permit cũng cần trả; khi handler chạy task ngay trên caller, phải tránh **trả hai lần** khi exception vượt qua call stack. Một solution đúng cần một ownership/release-once protocol cho mọi trạng thái, không phải chỉ thêm `Semaphore` tùy tiện.

Nếu nhu cầu đơn giản là giới hạn queue, `ArrayBlockingQueue` với rejection rõ có thể ít lỗi hơn.

## 14. Chọn capacity từ memory budget và latency budget

Không có capacity mặc định đúng cho mọi hệ thống. Hãy xét hai giới hạn chính:

**Giới hạn bộ nhớ:** giả sử mỗi queued task giữ trung bình R byte retained heap theo đo đạc và ngân sách heap dành cho queue là M byte; capacity lý thuyết không được vượt tỷ lệ M/R, và cần headroom cho GC, task có payload lớn bất thường, worker và các hệ thống khác.

**Giới hạn độ trễ:** tốc độ hoàn thành ổn định khoảng C task/s, thời gian cho phép chờ queue khoảng W giây; một queue quá nhiều phần tử so với C×W sẽ khiến task phía cuối khó đạt deadline. Đây chỉ là ước lượng sơ bộ cho FIFO và workload tương đối đồng nhất, không phải cam kết cứng khi task duration thay đổi.

Nếu hai giới hạn cho các con số khác nhau, **giới hạn chặt hơn** là gợi ý để bắt đầu thử nghiệm. Không đặt queue capacity chỉ bằng “số lớn mà JVM cho phép”.

| Câu hỏi | Vì sao cần |
| --- | --- |
| Peak arrival rate và burst dài bao lâu? | Xác định lượng backlog thật sự cần hấp thụ |
| Completion rate khi downstream chậm? | Đo năng lực trong tình huống xấu |
| Retained heap của mỗi queued task? | Ngăn OOM trước khi capacity đạt ngưỡng |
| P95/p99 queue wait target? | Bảo vệ SLA chứ không chỉ heap |
| Timeout/cancel rate? | Tránh giữ task đã không còn giá trị |
| Rejection có chấp nhận được? | Quyết định fail-fast hay durable buffer |
| Task có idempotent không? | Tránh retry storm/double side effect |
| Shutdown deadline bao nhiêu? | Queue rất dài làm drain lâu |

## 15. Shutdown với queue lớn

`ExecutorService.shutdown()` ngừng nhận task mới và cho task đã được nhận tiếp tục theo hợp đồng, bao gồm những task còn chờ. Với queue khổng lồ, graceful shutdown có thể mất rất lâu.

`shutdownNow()` là yêu cầu hủy best-effort: cố interrupt task đang chạy và trả danh sách task chưa bắt đầu. Nó **không** đảm bảo thread running dừng tức thì và không tự bền vững hóa các task còn chờ. Chủ sở hữu phải có policy ghi nhận/requeue/cancel phù hợp.

`awaitTermination(timeout, unit)` chỉ đợi trạng thái terminated, không tự sửa backlog hoặc hủy task. Nếu task đang kẹt ở I/O không phản hồi interrupt, executor có thể không kết thúc trong timeout.

~~~java
// Snippet shutdown điều phối, cần xử lý InterruptedException ở caller.
pool.shutdown();
if (!pool.awaitTermination(30, TimeUnit.SECONDS)) {
    java.util.List<Runnable> neverStarted = pool.shutdownNow();
    // Theo nghiệp vụ: ghi nhận, hủy hoặc chuyển những task chưa chạy.
    if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
        // Còn task không phản hồi interrupt: alert/escalation.
    }
}
~~~

Không được biến bài toán overload thành “shutdown nhanh bằng cách bỏ hết backlog” nếu work phải được xử lý chính xác. Phải thiết kế rõ acceptable loss và retry/durability.

## 16. Observability: metric nào cần theo dõi?

`ThreadPoolExecutor` cung cấp các getter như:

- `getQueue().size()`: số task đang chờ trong queue **tại thời điểm đo**.
- `getActiveCount()`: số thread đang tích cực thực thi task, là **ước lượng** cho monitoring.
- `getPoolSize()`, `getLargestPoolSize()`: worker hiện tại và cực đại đã từng có.
- `getTaskCount()`, `getCompletedTaskCount()`: số task tổng và đã hoàn tất, giá trị dùng monitoring.
- `getRejectedExecutionHandler()`: policy đang cấu hình, nhưng muốn thống kê số reject thường cần tự instrument.
- **Queue waiting time**: thời gian từ enqueue/accept đến task bắt đầu; rất quan trọng cho SLA.
- **Execution time**: thời gian task chạy; tránh nhầm với queue wait.
- **Heap/GC**, downstream response time, timeouts, cancellations và retry.

Các getter snapshot/ước lượng **không phải primitive đồng bộ**: check `getQueue().size() < capacity` rồi `execute()` không đảm bảo còn chỗ, vì thread khác có thể submit trong khoảng trống. Dùng chính queue bounded/rejection hoặc một admission protocol.

### Dấu hiệu overload rõ ràng

- Queue size tăng liên tục qua nhiều khoảng đo, không drain sau burst.
- Completed/sec thấp hơn accepted/sec kéo dài.
- Active workers đạt mức worker hữu ích nhưng queue vẫn tăng.
- P99 queue wait tăng, nhiều task bắt đầu sau client deadline.
- Heap sau GC tăng cùng queue.
- Retry rate, timeout rate và lượng task bị cancel cùng tăng.
- Executor shutdown mất nhiều thời gian vì backlog.

Nếu queue luôn bằng 0 nhưng request vẫn chậm, hãy tìm bottleneck khác: task đang chạy, downstream, `SynchronousQueue`, thread count, lock contention hoặc CPU, thay vì quy mọi lỗi về unbounded queue.

## 17. Kiểm thử load và rủi ro thực tế

Không cần cố tình đẩy JVM tới `OutOfMemoryError` để chứng minh nguy cơ. Dùng latch như các ví dụ trên, queue capacity nhỏ, deadline và metric rõ ràng. Với load test riêng, cần kiểm tra:

1. **Steady state:** accepted/completed cân bằng và queue ổn định?
2. **Burst:** queue có drain trong thời gian cho phép sau khi burst qua?
3. **Overload kéo dài:** rejection/backpressure kích hoạt đúng?
4. **Task chậm:** worker bị block thì queue wait thay đổi ra sao?
5. **Timeout/cancel:** task đã hết giá trị có còn chạy hay giữ memory?
6. **Failure:** task ném exception có được ghi nhận, retry đúng và idempotent không?
7. **Shutdown:** queue còn backlog, `shutdown`/`shutdownNow` hoạt động theo policy?
8. **Caller-runs:** submitter có bị block lâu hay chạy task dưới context không phù hợp?
9. **Memory:** heap sau GC và retained task graph có phù hợp budget?
10. **Tail latency:** p95/p99 của queue wait và end-to-end vẫn nằm trong yêu cầu?

Dùng JMH cho microbenchmark phù hợp, nhưng để đánh giá queue overload phải có **load test nhiều producer, task durations đại diện, giới hạn downstream và cancellation/shutdown scenarios**. Một vòng `System.nanoTime()` chạy trong main không phản ánh áp lực thực.

### Một lưu ý riêng về `submit`

Khi `submit(Callable/Runnable)`, exception của task thường được lưu trong `Future`; nếu bỏ qua Future mà không có kênh quan sát lỗi, task có thể **thất bại âm thầm đối với logic nghiệp vụ**. `execute(Runnable)` có xử lý exception khác. Vì vậy monitor “submit thành công” không chứng minh task đã chạy đúng, nhất là khi queue quá lớn.

## 18. Quy trình quyết định khi nhận thấy queue không giới hạn

**Bước 1 — Xác định loại executor thật.** `newFixedThreadPool`, `newSingleThreadExecutor` hay custom `ThreadPoolExecutor`? Work queue loại gì, capacity bao nhiêu, core/max và rejection handler gì?

**Bước 2 — Đo arrival vs completion.** Task gửi vào và hoàn thành trên cùng cửa sổ thời gian; backlog tăng có bền vững không?

**Bước 3 — Đánh giá memory retention.** Task giữ object graph lớn nào, cancelled Future có nằm trong queue, memory budget cho queue còn bao nhiêu?

**Bước 4 — Đánh giá deadline.** Task chờ tới lúc chạy còn có giá trị hay chỉ làm việc vô ích? Có nên reject/cancel/expire sớm?

**Bước 5 — Chọn capacity.** Dựa vào cả memory và latency; không mặc định dùng `Integer.MAX_VALUE`.

**Bước 6 — Chọn overload policy.** Abort, caller-runs nếu đúng semantics, rate limiting, semaphore admission có release-once, hoặc durable queue với quota. Ghi nhận reject và tác động lên client.

**Bước 7 — Kiểm tra số worker/downstream.** CPU-bound khác blocking I/O; tăng worker không tự tăng DB capacity hoặc external API rate limits.

**Bước 8 — Kiểm tra failure và shutdown.** Phải thu lỗi từ `Future`, có cancellation policy và giới hạn thời gian drain; không mất task không chủ đích.

**Bước 9 — Benchmark/load test.** So sánh p95/p99 wait, completed/sec, heap, GC, reject, timeouts và correctness trên tải đại diện.

## 19. Các hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
| --- | --- |
| “Queue không giới hạn là vô hạn tài nguyên.” | Heap hữu hạn; `LinkedBlockingQueue` cũng có bound `Integer.MAX_VALUE` theo số phần tử |
| “Chỉ cần tăng `maximumPoolSize`.” | Unbounded queue thường nhận task trước khi tạo worker vượt core |
| “`submit` trả nhanh là task chạy nhanh.” | Có thể vẫn đang chờ rất lâu |
| “Không có reject nghĩa là hệ thống khỏe.” | Queue có thể đang tích backlog nguy hiểm |
| “Task nhỏ nên memory footprint nhỏ.” | Closure và `FutureTask` có thể giữ object graph lớn |
| “Timeout ở `Future.get` tự hủy task.” | Timeout của caller không phải cancellation |
| “`cancel` tức khắc xóa task khỏi queue.” | Có executor cần dequeue hoặc `purge` |
| “Bounded queue tự xử lý overload.” | Nó làm overload lộ rõ, caller vẫn phải có policy |
| “`CallerRunsPolicy` luôn thực hiện task.” | Sau shutdown nó có thể bỏ task; trước shutdown có thể block caller |
| “Queue size bằng 0 nghĩa là mọi task xong.” | Task running không nằm trong queue |
| “`shutdown()` xóa backlog.” | Thường drain những task đã nhận |
| “`shutdownNow()` chắc chắn terminate ngay.” | Best effort interruption, có task không hợp tác |
| “Một benchmark ngắn đủ chứng minh tối ưu.” | Kết quả phụ thuộc contention, GC, payload, scheduling và downstream |

## 20. Câu hỏi tự kiểm tra

**Câu 1.** `ThreadPoolExecutor` có core=2, max=20 và `new LinkedBlockingQueue<>()`. Nếu core worker bận, task mới có chắc làm pool tăng lên 20 worker không?  
**Đáp án:** Không. Queue rất lớn thường nhận task, nên executor không cần tạo worker vượt core.

**Câu 2.** Vì sao queue chưa đạt `Integer.MAX_VALUE` vẫn có thể gặp OOM?  
**Đáp án:** Số task và captured object graph có thể tiêu thụ hết heap từ sớm.

**Câu 3.** `Future.get(100, MILLISECONDS)` timeout thì task đã dừng chưa?  
**Đáp án:** Chưa chắc. Deadline chờ của caller tách biệt với execution/cancellation.

**Câu 4.** Một worker đang block, bounded queue capacity 2 có 2 task chờ, maxPoolSize=1. Task tiếp theo với `AbortPolicy` ra sao?  
**Đáp án:** Bị reject bằng `RejectedExecutionException`.

**Câu 5.** `CallerRunsPolicy` có bảo đảm task sẽ chạy ngay cả khi executor đã shutdown không?  
**Đáp án:** Không. Policy bỏ task khi shutdown; khi chưa shutdown và overload, task có thể chạy inline ở caller.

**Câu 6.** Nếu `getQueue().size() == 0` có thể kết luận executor không có việc không?  
**Đáp án:** Không. Worker vẫn có thể đang chạy task.

**Câu 7.** Vì sao `shutdown()` mất rất lâu khi queue unbounded lớn?  
**Đáp án:** Nó không tự bỏ task đã nhận; executor phải hoàn tất backlog trước khi terminated, trừ khi thay policy/cancel.

**Câu 8.** `cancel(false)` đối với Future đang queued có nhất thiết xóa wrapper ngay không?  
**Đáp án:** Không. `ThreadPoolExecutor.purge()` có thể được dùng để loại cancelled Future còn ở queue.

**Câu 9.** Đo mỗi accepted/sec có đủ để phát hiện overload không?  
**Đáp án:** Không. Cần completed/sec, queue slope, wait latency, heap/GC, timeout, failure/rejection.

**Câu 10.** Tiêu chí chọn queue capacity là “lớn nhất JVM chịu được” phải không?  
**Đáp án:** Không. Cần dựa vào budget heap, queue waiting-time deadline, workload burst và policy quá tải.

## Tài liệu chính thức Java SE

- [`ThreadPoolExecutor` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html): core/max/queue strategy, rejection, `purge`, monitoring.
- [`Executors` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executors.html): `newFixedThreadPool`, `newSingleThreadExecutor`, `newCachedThreadPool`.
- [`LinkedBlockingQueue` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/LinkedBlockingQueue.html): default capacity và queue behavior.
- [`ArrayBlockingQueue` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html): bounded FIFO queue.
- [`RejectedExecutionHandler` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RejectedExecutionHandler.html): xử lý task không được nhận.
- [`Future` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): timeout, cancellation và completion.
- [`ExecutorService` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): shutdown, termination, task lifecycle.
- [`Semaphore` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Semaphore.html): admission/resource permits.

**Ghi nhớ:** Queue không giới hạn **trì hoãn thời điểm phải đối mặt với overload**, không làm executor có throughput vô hạn. Thiết kế an toàn cần **bounded admission, memory và latency budget, rejection/backpressure policy, deadline/cancellation, đo backlog và shutdown semantics**.