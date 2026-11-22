# Work queue, worker pool và task dispatch trong Java Concurrency

## 1. Bài toán cần giải quyết

Giả sử một ứng dụng nhận yêu cầu xử lý báo cáo, gửi email hoặc tính toán dữ liệu. Yêu cầu có thể đến nhanh hơn tốc độ xử lý. Nếu mỗi yêu cầu tạo một `Thread` platform mới, ứng dụng dễ tốn bộ nhớ, tăng chi phí chuyển ngữ cảnh và mất kiểm soát khi lưu lượng tăng đột biến. Nếu xử lý trực tiếp trên luồng nhận yêu cầu, thời gian phản hồi và khả năng nhận thêm việc lại bị ảnh hưởng.

Một thiết kế phổ biến tách ba trách nhiệm:

1. **Work queue (hàng đợi công việc):** lưu các tác vụ đang chờ, có thể có giới hạn dung lượng.
2. **Worker pool (nhóm worker):** tập các thread nhận và thực hiện tác vụ; số worker giới hạn lượng công việc đang được xử lý cùng lúc.
3. **Task dispatch (điều phối tác vụ):** quyết định tác vụ nào được nhận, đưa vào queue hay giao ngay cho worker, cách xử lý khi quá tải, theo dõi lỗi và vòng đời.

~~~text
Producer(s) -- submit task --> [ Work queue ] -- take --> Worker 1
                                         |-------> Worker 2
                                         |-------> Worker N
                         | full |
                         v
              wait / reject / caller runs / shed load
~~~

**Task** là đơn vị việc cần làm, thường biểu diễn bằng `Runnable` (không có giá trị trả về) hoặc `Callable<T>` (trả `T` và có thể ném checked exception). **Worker** là thread thực thi task. **Queue** là chỗ chứa task *chưa bắt đầu chạy*. Với Java, API trung tâm nằm trong `java.util.concurrent`: `BlockingQueue`, `Executor`, `ExecutorService` và `ThreadPoolExecutor`.

Mô hình này không bảo đảm mọi task chạy đúng thứ tự đưa vào queue. Một queue FIFO bảo đảm **thứ tự lấy ra** ở đầu queue (trong điều kiện sử dụng thích hợp), nhưng nhiều worker có thể hoàn tất task ở những thời điểm khác nhau.

## 2. Cách work queue phối hợp với worker

### 2.1. Producer–consumer và nguyên tắc blocking

Trong mô hình producer–consumer:

- **Producer** tạo task rồi đưa vào queue.
- **Consumer/worker** gọi `take()` để chờ và lấy task; khi queue trống, thread đợi thay vì liên tục kiểm tra.
- Khi queue có giới hạn và đầy, producer có thể chờ chỗ trống (`put`), chờ có timeout (`offer` có timeout) hoặc xử lý thất bại ngay (`offer` không timeout).
- Worker thực hiện task ngoài thao tác lấy queue. Nhiều producer và consumer có thể sử dụng `BlockingQueue` đồng thời mà không cần tự thêm `synchronized` quanh mỗi `put`/`take`.

Các lựa chọn cơ bản của `BlockingQueue<E>`:

| Hành động | Ném ngoại lệ nếu không làm ngay | Trả trạng thái ngay | Chờ vô hạn | Chờ có timeout |
| --- | --- | --- | --- | --- |
| Thêm item | `add(e)` | `offer(e)` → `boolean` | `put(e)` | `offer(e, timeout, unit)` |
| Lấy và xóa | `remove()` | `poll()` → item hoặc `null` | `take()` | `poll(timeout, unit)` |
| Chỉ xem đầu queue | `element()` | `peek()` | Không có | Không có |

Ví dụ `queue.put(task)` có thể khiến **producer** bị chặn khi queue đầy; đây là một hình thức **backpressure** đơn giản. Đừng gọi `put` trên luồng không được phép chờ lâu (ví dụ luồng giữ khóa quan trọng) nếu có nguy cơ gây nghẽn dây chuyền. `BlockingQueue` không nhận phần tử `null`; `poll()` trả `null` để biểu diễn không có item.

Các thao tác trên blocking queue cũng hỗ trợ tính hiển thị bộ nhớ: những hành động diễn ra **trước khi** một thread đưa item vào queue *happen-before* những hành động diễn ra **sau khi** thread khác lấy/chạm đến item đó qua queue. Đây là một phần của hợp đồng concurrency, không phải sự tình cờ do CPU cache.

### 2.2. Chọn loại queue

| Queue | Đặc điểm | Dùng khi nào | Rủi ro/cần lưu ý |
| --- | --- | --- | --- |
| `ArrayBlockingQueue<>(capacity)` | FIFO, dung lượng cố định | Muốn giới hạn số task chờ và dự đoán bộ nhớ | Producer có thể chờ hoặc bị từ chối khi đầy |
| `LinkedBlockingQueue<>(capacity)` | FIFO, dung lượng cấu hình | Muốn queue có giới hạn nhưng không yêu cầu mảng cố định | Nếu **không truyền capacity**, giới hạn là `Integer.MAX_VALUE`, thực tế có thể phình bộ nhớ |
| `SynchronousQueue<>` | Không lưu item; truyền trực tiếp cho worker đang nhận | Handoff trực tiếp, tránh tích tụ queue | Nếu không có consumer sẵn sàng, `offer` thất bại ngay; với pool có thể làm tăng thread hoặc gây reject |
| `PriorityBlockingQueue<>` | Ưu tiên theo comparator/natural ordering, về cơ bản không bounded | Cần xử lý theo độ ưu tiên | Không duy trì FIFO cho task cùng độ ưu tiên nếu không tự bổ sung sequence; dễ starvation; không tự backpressure |
| `DelayQueue<>` | Chỉ lấy item khi delay đã hết, không bounded | Tác vụ cần trì hoãn theo thời gian | Không phải scheduler tổng quát của pool; phần tử phải implement `Delayed` |

Dùng một queue có giới hạn thường an toàn hơn cho hệ thống có lưu lượng biến động. Tuy vậy, **queue capacity không phải throughput**: tăng chiều dài queue chỉ cho nhiều task chờ hơn, không làm worker xử lý nhanh hơn.

## 3. Ví dụ chạy được: tự xây work queue với hai worker

Ví dụ này minh họa producer đẩy công việc vào `ArrayBlockingQueue`; hai worker lặp `take()` cho đến khi nhận tín hiệu kết thúc. Sau khi tất cả task được đưa vào queue, producer gửi **một poison pill cho mỗi worker** để chúng thoát vòng lặp.

Lưu thành **`WorkQueueDemo.java`** (JDK 17+):

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CopyOnWriteArrayList;

public class WorkQueueDemo {
    private static final int STOP = -1;

    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<Integer> queue = new ArrayBlockingQueue<>(2);
        List<Integer> processed = new CopyOnWriteArrayList<>();

        Runnable consumer = () -> {
            try {
                while (true) {
                    int jobId = queue.take();
                    if (jobId == STOP) {
                        return;
                    }
                    processed.add(jobId);
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        };

        Thread first = new Thread(consumer, "worker-1");
        Thread second = new Thread(consumer, "worker-2");
        first.start();
        second.start();

        for (int id = 1; id <= 4; id++) {
            queue.put(id);
        }

        // Chỉ gửi STOP sau khi đã gửi xong tất cả job thật.
        queue.put(STOP);
        queue.put(STOP);

        first.join();
        second.join();

        processed.sort(Comparator.naturalOrder());
        System.out.println("Processed: " + processed);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 WorkQueueDemo.java
java WorkQueueDemo
~~~

Kết quả:

~~~text
Processed: [1, 2, 3, 4]
~~~

**Giải thích:**

1. Queue chỉ chứa tối đa hai phần tử *đang chờ*. Khi đầy, `put` sẽ chờ worker lấy bớt item.
2. Hai worker đồng thời lấy job. Vì vậy thứ tự thực thi/hoàn tất có thể khác nhau; chương trình **sort sau khi `join()`** để stdout ổn định.
3. `STOP` được thêm **sau** tất cả job thật, queue là FIFO, mỗi worker nhận một tín hiệu và kết thúc.
4. `join()` buộc main đợi hai worker dừng trước khi in kết quả.
5. `CopyOnWriteArrayList` chỉ được dùng để dễ tạo ví dụ nhỏ; với hệ thống ghi kết quả với tần suất cao, chi phí sao chép mảng mỗi lần thêm rất lớn. Thường dùng bộ tổng hợp phù hợp hoặc `ConcurrentLinkedQueue`.

**Poison pill có giới hạn:** cần một sentinel **không thể trùng dữ liệu thật** (ở đây job hợp lệ chỉ mang ID dương); số sentinel và số consumer phải tương ứng. Nếu producer khác còn tiếp tục gửi task, nếu worker chết bất ngờ hoặc nếu có nhiều nguồn gửi STOP, cần một giao thức đóng queue chắc chắn hơn. `BlockingQueue` **không có `close()` tổng quát**; task pool chuyên dụng thường nên dùng `ExecutorService`.

## 4. `Executor` và `ExecutorService`: giao task thay vì quản lý thread thủ công

Ở mức thấp, ta có thể gọi `new Thread(task).start()`. Với tác vụ đến liên tục, cách này khiến code tự gánh việc tạo, quản lý, hủy và theo dõi từng thread. API `Executor` tách nơi **gửi task** khỏi nơi **chạy task**:

~~~java
Executor executor = ...;
executor.execute(() -> doWork());
~~~

Đây là **mảnh mã minh họa**, giả định `executor` và `doWork()` đã được định nghĩa. `ExecutorService` mở rộng `Executor` với `submit(Callable/Runnable)`, `Future`, `shutdown`, `awaitTermination` và các cơ chế chờ/hủy tác vụ.

| API | Cách dùng | Nhận kết quả hoặc lỗi |
| --- | --- | --- |
| `execute(Runnable)` | Gửi fire-and-forget task, nhưng vẫn cần ghi nhận lỗi | Không trả `Future`; lỗi uncaught tùy worker/executor |
| `submit(Runnable)` | Gửi task và theo dõi trạng thái | `Future<?>`; `get()` trả `null` khi thành công |
| `submit(Callable<T>)` | Gửi task trả kết quả | `Future<T>.get()` lấy kết quả; lỗi của task bọc trong `ExecutionException` |
| `Future.cancel(true)` | Yêu cầu hủy và có thể interrupt worker | Hủy mang tính hợp tác, không bảo đảm task dừng ngay |
| `shutdown()` | Ngừng nhận task mới, xử lý task đã nhận | **Không chờ** tất cả task xong |
| `awaitTermination(...)` | Chờ pool kết thúc sau khi đã shutdown | Trả `true` khi dừng, `false` khi hết timeout |
| `shutdownNow()` | Thử interrupt task đang chạy và trả về task chưa bắt đầu | Best-effort; không bảo đảm worker dừng ngay |

`submit` không đồng nghĩa với “đã xử lý xong” khi phương thức trả về. `execute` và `submit` cũng có thể bị **từ chối ngay khi gửi** nếu executor đã shutdown hoặc bị giới hạn tài nguyên. Với `Future`, nếu **không bao giờ gọi `get()`**, một exception trong task có thể không được quan sát ở caller.

Các factory thường gặp:

~~~java
ExecutorService fixed = Executors.newFixedThreadPool(4);
ExecutorService single = Executors.newSingleThreadExecutor();
ExecutorService cached = Executors.newCachedThreadPool();

// Dùng shutdown() / awaitTermination() khi kết thúc.
// Các dòng trên minh họa việc tạo executor, không phải chương trình hoàn chỉnh.
~~~

- `newFixedThreadPool(4)` có bốn worker tối đa theo thiết kế và dùng queue chờ thực tế **không bounded**; không coi đây là cơ chế backpressure hoàn chỉnh.
- `newSingleThreadExecutor()` giữ một worker xử lý tuần tự; vẫn có queue chờ có thể lớn.
- `newCachedThreadPool()` dùng direct handoff và có thể tạo nhiều platform thread khi tải đến liên tục; cần đánh giá giới hạn tài nguyên.
- Trong Java 21+, `Executors.newVirtualThreadPerTaskExecutor()` **tạo một virtual thread mới cho mỗi task**, không phải một pool gồm số virtual thread cố định. Muốn khống chế concurrency truy cập database, HTTP hoặc tài nguyên khác, cần một giới hạn riêng (ví dụ semaphore) thay vì cho rằng executor tự giới hạn số tác vụ.

Các factory dễ dùng nhưng không phải lúc nào cũng cho kiểm soát queue capacity, thread count và rejection policy như hệ thống cần. Khi các thông số này quan trọng, dùng `ThreadPoolExecutor` trực tiếp.

## 5. `ThreadPoolExecutor`: quy tắc dispatch cần nắm thật chắc

Constructor phổ biến (Java 17+):

~~~java
ThreadPoolExecutor executor = new ThreadPoolExecutor(
        corePoolSize,
        maximumPoolSize,
        keepAliveTime,
        TimeUnit.MILLISECONDS,
        workQueue,
        threadFactory,
        rejectedExecutionHandler);
~~~

Đây là **mảnh mã cấu hình**; các tên biến mang nghĩa tham số, chưa khai báo trong đoạn này.

Các tham số:

- `corePoolSize`: mức worker cốt lõi. Nếu số worker **ít hơn core**, pool ưu tiên tạo worker mới khi nhận task, ngay cả khi queue còn chỗ (mặc định không tạo trước tất cả core worker).
- `maximumPoolSize`: giới hạn tối đa worker đang tồn tại trong pool. Có tác dụng rõ nhất khi queue **không nhận thêm task**.
- `keepAliveTime`: thời gian worker *vượt quá core* có thể rảnh trước khi nghỉ; mặc định core workers không bị timeout trừ khi bật `allowCoreThreadTimeOut(true)`.
- `workQueue`: nơi chờ task khi đã có ít nhất core worker; dung lượng queue tác động trực tiếp đến việc pool có mở thêm worker tới max hay không.
- `threadFactory`: đặt tên, daemon, handler cho platform thread theo yêu cầu.
- `rejectedExecutionHandler`: xử lý task không thể nhận vào pool (bao gồm tình huống shutdown).

Thứ tự quyết định khi gửi một task vào `ThreadPoolExecutor`:

~~~text
Gọi execute(task)
   |
   +-- running workers < corePoolSize ? --> tạo worker mới xử lý task
   |
   +-- nếu không: thử offer(task) vào workQueue
   |       |
   |       +-- nhận được --> task chờ worker lấy
   |
   +-- queue không nhận thêm: workers < maximumPoolSize ?
   |       |
   |       +-- có --> tạo thêm worker chạy task
   |
   +-- không --> rejectedExecutionHandler
~~~

Đây là **luồng quyết định khái niệm**. Implementation có thêm kiểm tra trạng thái run/shutdown và xử lý cạnh tranh giữa thread để tránh nhận task sau khi executor ngừng hoạt động.

**Hệ quả hay bị hiểu sai:** cấu hình `core=2, max=8` với `LinkedBlockingQueue` không có giới hạn thực tế thường chỉ chạy **2 worker** vì queue cứ nhận thêm task; `max=8` không tự làm pool mở rộng. Với `ArrayBlockingQueue<>(100)`, task bắt đầu đi vào queue khi đã có hai core worker; pool chỉ tăng số worker tiếp khi queue không nhận thêm. Với `SynchronousQueue`, không có chỗ lưu task chờ nên executor thử mở thêm worker sớm hơn nếu không handoff được.

### 5.1. Ví dụ có thể tự kiểm chứng: queue đầy và từ chối task

Chương trình sau tạo **1 worker** và queue có **1 vị trí**. Task đầu tiên chờ tín hiệu `CountDownLatch` nên chắc chắn chiếm worker; task thứ hai nằm trong queue; task thứ ba không còn chỗ nhận và bị từ chối theo `AbortPolicy`. Cách dùng latch giúp kết quả độc lập với sự nhanh/chậm của scheduler.

Lưu thành **`PoolRejectionDemo.java`**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class PoolRejectionDemo {
    public static void main(String[] args) throws InterruptedException {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.AbortPolicy());

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        boolean rejected = false;

        try {
            pool.execute(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            });

            started.await();              // task 1 đang giữ worker
            pool.execute(() -> { });      // task 2 đang chờ trong queue

            try {
                pool.execute(() -> { });  // task 3 không còn slot
            } catch (RejectedExecutionException ex) {
                rejected = true;
            }
        } finally {
            release.countDown();
            pool.shutdown();
        }

        boolean stopped = pool.awaitTermination(5, TimeUnit.SECONDS);
        System.out.println("Third rejected: " + rejected);
        System.out.println("Pool stopped: " + stopped);
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 PoolRejectionDemo.java
java PoolRejectionDemo
~~~

Kết quả khi máy chạy bình thường và pool dừng trước timeout:

~~~text
Third rejected: true
Pool stopped: true
~~~

Số worker, queue slot và trình tự latch đã được khống chế. `awaitTermination(5, SECONDS)` có thể trả `false` nếu JVM bị tạm dừng/quá tải lâu hơn timeout; đó là lý do kết quả dòng cuối được mô tả có điều kiện. Phần này cho thấy **task dispatch bị ảnh hưởng bởi trạng thái worker và queue**, không chỉ bởi `maximumPoolSize`.

## 6. Rejection policy chính là quyết định khi quá tải

Khi pool không nhận task, `ThreadPoolExecutor` gọi `RejectedExecutionHandler`. Bốn policy có sẵn:

| Policy | Hành vi | Khi nên cân nhắc |
| --- | --- | --- |
| `AbortPolicy` | Ném `RejectedExecutionException` (mặc định) | Cần trả thông báo quá tải/rate limit và không được mất task thầm lặng |
| `CallerRunsPolicy` | Nếu chưa shutdown, caller **tự chạy task** | Muốn tự giảm tốc producer bằng cách buộc caller thực hiện công việc; chú ý latency và việc chặn caller |
| `DiscardPolicy` | Bỏ qua task, không báo lỗi | Chỉ cho dữ liệu có thể mất, có metrics và chấp nhận mất việc |
| `DiscardOldestPolicy` | Bỏ task đầu queue, thử gửi task hiện tại lại | Chỉ khi chấp nhận đổi ưu tiên/mất task; dễ phá thứ tự và giả định nghiệp vụ |

Với `CallerRunsPolicy`, khi pool **đã shutdown**, task có thể bị **bỏ qua** theo hợp đồng của policy. Vì vậy không được suy diễn rằng policy này luôn đảm bảo tất cả task được xử lý.

**Backpressure thực tế** là kết hợp nhiều lớp: queue bounded, giới hạn producer/request, giới hạn số thao tác đến downstream, timeout, retry có kiểm soát và tín hiệu quá tải rõ ràng. Chỉ đổi `AbortPolicy` sang `CallerRunsPolicy` chưa đủ nếu caller là event loop hoặc đang giữ một khóa quan trọng.

Một ví dụ thiết kế ranh giới nhận task:

~~~java
// Mảnh minh họa: executor, task và rejectedCounter đã tồn tại.
try {
    executor.execute(task);
} catch (RejectedExecutionException rejected) {
    rejectedCounter.incrementAndGet();
    // Báo "quá tải" cho phía gửi hoặc lưu sang cơ chế bền vững.
}
~~~

Đoạn này **không phải chương trình hoàn chỉnh**; task đã reject không thể được coi là “đã nhận”. Nếu queue chỉ nằm trong bộ nhớ, shutdown/crash có thể làm mất task còn chờ. Với yêu cầu không được mất việc, cần một cơ chế durable queue/transaction/ack riêng; `BlockingQueue` không phải message broker bền vững.

## 7. Lấy kết quả: `Callable`, `Future` và completion-order dispatch

`Runnable` thích hợp khi không cần kết quả. `Callable<T>` trả `T` và có thể ném checked exception, nên thường dùng với `ExecutorService.submit`. `Future.get()` đợi kết quả; `ExecutionException` chứa nguyên nhân gốc. Nếu cần xử lý **task nào xong trước thì lấy trước**, `ExecutorCompletionService` cung cấp một completion queue; gọi `take()` để lấy `Future` đã hoàn tất.

Ví dụ độc lập **`CompletionDispatchDemo.java`** (Java 17+):

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.ExecutorCompletionService;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class CompletionDispatchDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            ExecutorCompletionService<Integer> completed =
                    new ExecutorCompletionService<>(pool);

            for (int i = 1; i <= 3; i++) {
                int id = i;
                completed.submit(() -> id * id);
            }

            List<Integer> results = new ArrayList<>();
            for (int i = 0; i < 3; i++) {
                Future<Integer> future = completed.take();
                results.add(future.get());
            }

            Collections.sort(results);
            System.out.println("Results: " + results);
        } finally {
            pool.shutdown();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 CompletionDispatchDemo.java
java CompletionDispatchDemo
~~~

Stdout:

~~~text
Results: [1, 4, 9]
~~~

`completed.take()` trả `Future` theo **thứ tự hoàn thành**, vốn có thể thay đổi giữa các lần chạy. Chỉ sau khi `sort` kết quả in ra mới cố định. `submit` có thể ném `RejectedExecutionException` ngay nếu pool không nhận task; một task đã nhận nhưng ném exception khi chạy sẽ làm `future.get()` ném `ExecutionException`.

Nếu từng task có thời hạn riêng, cân nhắc `future.get(timeout, unit)` và `future.cancel(true)`; nhớ rằng cancel thường dựa trên interrupt và tác vụ phải hợp tác. `shutdown()` trong `finally` không chờ kết thúc như `awaitTermination()`, nhưng ví dụ đã lấy đủ ba kết quả nên tất cả công việc gửi đã xong trước khi rời try.

## 8. Dispatch và thứ tự xử lý: FIFO không đồng nghĩa hoàn thành tuần tự

Một queue FIFO với hai worker có thể tạo dòng thời gian:

~~~text
Thời điểm     Worker A                  Worker B
t0            lấy task 1                lấy task 2
t1            task 1 chờ I/O            task 2 tính xong
t2            vẫn đang chờ              lấy task 3
t3            task 1 xong               task 3 xong
Hoàn tất:     2, 1, 3  (hoặc một thứ tự khác tùy lịch)
~~~

Điều cần phân biệt:

- **Enqueue order:** thứ tự producer đưa task vào queue. Nhiều producer đồng thời tạo thứ tự cạnh tranh, không mặc nhiên theo thời gian từ hệ thống ngoài.
- **Dequeue/start order:** thứ tự worker nhận/bắt đầu task. FIFO queue thường giữ thứ tự lấy item, nhưng worker có thể bị scheduler tạm dừng trước khi chạy tác vụ thật.
- **Completion order:** thứ tự task kết thúc; với nhiều worker, không được suy ra từ FIFO.

Nếu cần thao tác cùng tài khoản/đơn hàng chạy đúng thứ tự, có thể dùng **single-thread executor** cho một nhóm công việc, hoặc **partition theo key** tới các queue/worker tuần tự. Nếu cần giữ thứ tự kết quả nhưng vẫn xử lý song song, đánh số sequence rồi sắp xếp/tập hợp trước khi phát kết quả. Cả hai cách có chi phí chờ; đừng áp dụng đồng bộ toàn cục nếu chỉ một nhóm key cần tuần tự.

**Task priority** cũng cần xem xét: hàng đợi ưu tiên có thể khiến task mức thấp chờ rất lâu (**starvation**). Cần cơ chế aging hoặc các hàng đợi riêng nếu hệ thống buộc phải có công bằng. **Task timeout** phải tính cả **thời gian nằm trong queue** nếu SLA tính từ lúc nhận việc, chứ không chỉ thời gian xử lý sau khi một worker bắt đầu.

## 9. Worker pool phù hợp cho CPU-bound hay I/O-bound?

- **CPU-bound:** công việc chủ yếu tiêu thụ CPU; khởi đầu hợp lý là số worker platform thread quanh số lõi CPU có thể dùng được, rồi đo theo workload và giới hạn container. Quá nhiều worker có thể làm tăng context switching mà không tăng throughput.
- **Blocking I/O-bound:** worker có thời gian đáng kể chờ network/disk/database. Với platform threads, có thể cần nhiều worker hơn số lõi, nhưng tài nguyên khác như connection pool và memory vẫn giới hạn concurrency.
- **Java 21+ virtual threads:** cho phép nhiều task blocking theo lối code đồng bộ mà không cần giữ một platform thread cho mỗi task; `newVirtualThreadPerTaskExecutor()` không tạo **pool giới hạn cố định**. Vẫn cần backpressure hoặc semaphore cho tài nguyên downstream.
- **Mixed workload:** nếu tác vụ CPU nặng chia sẻ cùng pool với tác vụ chờ I/O lâu, công việc ngắn có thể bị đói worker. Có thể dùng các executor/queue riêng theo loại workload và SLA.

Không có con số `poolSize=16` hay `queueCapacity=1000` đúng cho mọi hệ thống. Thiết kế dựa trên **arrival rate**, **service rate**, **thời gian task nằm trong queue**, bộ nhớ mỗi task, giới hạn downstream và mục tiêu độ trễ. Nếu trung bình có 60 task/s đến mà toàn bộ worker chỉ xử lý ổn định 40 task/s, backlog tăng xấp xỉ **20 task/s** khi tình trạng kéo dài. Queue 100 slot sẽ đầy rất nhanh nếu không có cơ chế điều tiết nguồn vào (đây là ước lượng lý tưởng hóa, bỏ qua biến động và trạng thái ban đầu).

### Phân biệt các giới hạn

| Giới hạn | Bảo vệ điều gì? | Thiết lập ở đâu? |
| --- | --- | --- |
| Worker count | Số task đang chạy trên worker pool | `corePoolSize`/`maximumPoolSize` |
| Work queue capacity | Số task đang chờ trong pool | `BlockingQueue` bounded |
| Downstream concurrency | Số kết nối/call đồng thời đến DB hoặc dịch vụ ngoài | `Semaphore`, connection pool, rate limiter |
| Timeout | Thời gian chờ tối đa để lấy/hoàn thành tác vụ | `Future.get(timeout)` hoặc cơ chế timeout riêng |
| Admission/rate limit | Số request đầu vào chấp nhận | Logic điều tiết ở producer/entry point |

Các giới hạn cần khớp nhau. Ví dụ pool có 100 worker nhưng database chỉ có 10 connection thì tăng worker không làm database đáp ứng nhanh hơn; nhiều worker có thể chỉ mắc kẹt chờ connection.

## 10. Lifecycle và shutdown an toàn

**Với custom queue + worker tự quản:** phải định nghĩa rõ khi nào producer ngừng gửi, consumer nào cần tín hiệu kết thúc, cách drain task còn chờ, cách xử lý interrupt và task lỗi. Poison pill phù hợp cho ví dụ có một producer kiểm soát được quá trình kết thúc; hệ thống nhiều producer cần giao thức đóng cẩn thận để không mất task.

**Với `ExecutorService`/`ThreadPoolExecutor`:**

1. Ngừng tiếp nhận task mới ở tầng producer.
2. Gọi `shutdown()`: từ chối task đến sau đó nhưng để task đã được nhận chạy tiếp.
3. Gọi `awaitTermination(timeout, unit)` để chờ có hạn.
4. Nếu quá thời gian và cần dừng, gọi `shutdownNow()`, ghi nhận task còn chờ được trả về và xử lý chúng theo chính sách ứng dụng.
5. Với `InterruptedException`, yêu cầu dừng phù hợp rồi khôi phục cờ interrupt (`Thread.currentThread().interrupt()`).

Mẫu Java 17+ sau là **phương thức độc lập** để đặt trong một lớp Java có các import tương ứng:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.TimeUnit;

public static void stopPool(ExecutorService pool) {
    pool.shutdown();
    try {
        if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
            pool.shutdownNow();
            if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                System.err.println("Pool still running");
            }
        }
    } catch (InterruptedException e) {
        pool.shutdownNow();
        Thread.currentThread().interrupt();
    }
}
~~~

`shutdownNow()` **không** cưỡng bức kill thread: nó cố interrupt tác vụ đang chạy và trả danh sách task chưa bắt đầu; task bỏ qua interrupt có thể không dừng. `isShutdown()` chỉ nói pool đã được yêu cầu dừng; `isTerminated()` mới xác nhận đã chấm dứt toàn bộ công việc sau shutdown.

Một nguồn treo phổ biến là **task trong pool chờ `Future.get()` của task khác cũng đang xếp hàng chờ chính pool đó**, trong khi tất cả worker đều bận chờ. Ví dụ pool một worker: task A submit task B vào cùng pool rồi `get()` chờ B; B không thể chạy vì A đang chiếm worker. Đây là **thread starvation deadlock**. Khắc phục bằng cách thiết kế luồng phụ thuộc, tránh blocking chéo cùng pool, dùng compose bất đồng bộ hoặc tách executor có kiểm soát.

## 11. Theo dõi hiệu năng và vận hành

Đối với `ThreadPoolExecutor`, có thể đọc một số số đo để quan sát:

| API/metric | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `getPoolSize()` | Worker hiện tồn tại | Không phải tổng số task |
| `getActiveCount()` | Ước tính worker đang thực thi task | Là **ước lượng tức thời** |
| `getQueue().size()` | Số task đang chờ hiện tại | Thay đổi liên tục; không dùng như cơ chế đồng bộ |
| `getCompletedTaskCount()` | Ước tính số task đã hoàn tất | Là số tích lũy, không phải throughput tức thời |
| Rejected task count | Số task không được nhận | Cần tự đo qua handler/ngoại lệ, chú ý policy có thể không ném |
| Queue wait time | Từ lúc nhận task đến lúc worker bắt đầu | Phải chủ động đo; quan trọng cho SLA |
| Task execution time | Từ lúc thực thi đến khi kết thúc | Phân tích riêng với queue wait time |
| End-to-end latency | Từ lúc nhận yêu cầu đến khi có kết quả | Tính cả xếp hàng, thực thi và truyền kết quả |

Không nên suy đoán tải chỉ từ queue size tại một thời điểm. Queue có thể rỗng vì worker quá nhiều, vì producer không còn việc hoặc vì chính sách reject đang loại bỏ task. Quan sát cùng **tốc độ nhận, tốc độ hoàn thành, latency percentile, lỗi, timeout, mức CPU, heap và downstream saturation**.

Một số tình huống cần kiểm thử:

- **Burst load:** một khoảng tăng lưu lượng ngắn; kiểm tra queue tăng rồi giảm như dự kiến.
- **Sustained overload:** đầu vào nhanh hơn đầu ra lâu dài; xác nhận reject/throttle có kiểm soát, không tăng bộ nhớ không giới hạn.
- **Slow task:** một số tác vụ bị treo I/O; kiểm tra timeout, cancellation và không làm nghẽn tất cả worker.
- **Task failure:** task ném runtime exception; theo dõi lỗi, không để task không liên quan biến mất.
- **Graceful stop:** ngừng producer, drain/chờ worker và xác minh không còn task được nhận nhưng chưa xử lý.
- **Ordering/duplicates:** khi retry hoặc worker thất bại, kiểm tra idempotency và thứ tự theo business key.

Đối với dữ liệu quan trọng, nên thiết kế **idempotency key**, retry có giới hạn, và ghi nhận trạng thái hoàn thành/đã nhận rõ ràng. `BlockingQueue`/`ThreadPoolExecutor` trong bộ nhớ không cung cấp giao dịch, persistence hay exactly-once delivery.

## 12. Lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| `while (true) { if (!queue.isEmpty()) queue.remove(); }` | Busy-spin, thao tác kiểm tra rồi lấy không atomic | Dùng `take()`/`poll(timeout)` |
| Dùng queue không bounded mà không giám sát | Bộ nhớ tăng khi input vượt khả năng phục vụ | Chọn capacity có tính toán và rejection/backpressure |
| Cấu hình `maxPoolSize` lớn nhưng queue không bounded | Pool thường không tăng quá core | Hiểu quy tắc dispatch trước khi sizing |
| `Future.get()` ngay sau mỗi lần `submit` trong vòng lặp | Vô tình tuần tự hóa công việc | Submit trước rồi thu kết quả hoặc dùng `CompletionService` |
| Không gọi `Future.get()`/không bắt lỗi task | Không phát hiện failure | Thu Future, ghi exception, quyết định retry/compensation |
| Bỏ qua `InterruptedException` | Task không hủy đúng, shutdown treo | Dừng phù hợp và khôi phục interrupt nếu không xử lý hoàn toàn |
| Bỏ qua `RejectedExecutionException` | Task thất lạc im lặng | Xử lý overload ở nơi gửi, ghi metrics |
| Coi `shutdown()` là dừng ngay | Tác vụ vẫn chạy; tài nguyên chưa giải phóng | Dùng `awaitTermination()` rồi xử lý timeout |
| Worker làm I/O lâu trong pool CPU | CPU tasks xếp hàng không cần thiết | Tách workload và tài nguyên |
| Coi FIFO là thứ tự hoàn tất | Sai trạng thái khi task song song | Tạo sequence/partition/điều phối kết quả |
| Dùng poison pill sai số lượng | Consumer treo hoặc task còn tồn | Giao thức đóng rõ ràng, một sentinel trên mỗi worker |
| Coi queue in-memory là hàng đợi bền vững | Mất task sau crash | Dùng cơ chế durable khi yêu cầu reliability |

## 13. Tóm lược quyết định thiết kế

- Muốn producer–consumer đơn giản, kiểm soát trực tiếp dữ liệu trong queue: bắt đầu với **`BlockingQueue` bounded + worker loops**, làm rõ shutdown protocol.
- Muốn phân phát task thông dụng và quản lý vòng đời: dùng **`ExecutorService`**.
- Muốn chọn rõ **core/max/queue capacity/rejection**: dùng **`ThreadPoolExecutor`** và kiểm thử quá tải trước khi triển khai.
- Muốn trả kết quả và quản lý lỗi: dùng **`Callable`/`Future`**, hoặc **`ExecutorCompletionService`** cho completion order.
- Muốn tác vụ blocking I/O với Java 21+: xem xét **virtual threads**, nhưng vẫn giới hạn số thao tác đến tài nguyên khan hiếm.
- Muốn reliability cao: xác định rõ admission, timeout, retry, idempotency, persistence và quan sát; pool/queue một mình không thể bảo đảm hoàn thành khi JVM crash.

### Tài liệu chính thức

- [Java SE 21 — `BlockingQueue`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/BlockingQueue.html) — các chế độ `put/offer/take/poll`, memory consistency và poison pill.
- [Java SE 21 — `ThreadPoolExecutor`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html) — quy tắc core/queue/max, cấu hình và rejection.
- [Java SE 21 — `ExecutorService`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html) — `submit`, `Future` và shutdown.
- [Java SE 21 — `ExecutorCompletionService`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorCompletionService.html) — kết quả theo thứ tự hoàn thành.
- [Java SE 21 — `Executors`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html) — các factory và virtual thread per task.
