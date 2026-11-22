# Executor, ExecutorService và ThreadPoolExecutor trong Java Concurrency

> **Phạm vi:** Executor Framework của Java SE, giải thích ba cấp abstraction `Executor`, `ExecutorService` và `ThreadPoolExecutor`; cách giao task, lấy kết quả, quản lý vòng đời và cấu hình thread pool, kiểm soát queue/rejection, quan hệ Java Memory Model và những tình huống dễ gây deadlock. Bài tập trung vào **Java concurrency nói chung**, không sử dụng cơ chế dành riêng cho Spring.

## 1. Tại sao Java có Executor Framework?

Cách cơ bản để thực thi một công việc đồng thời là tạo thread:

```java
Thread thread = new Thread(() -> doWork());
thread.start();
thread.join();
```

Đây là **đoạn code minh họa trong một method**: `doWork()` phải được khai báo và method cần khai báo/xử lý `InterruptedException` từ `join()`.

Đối với vài tác vụ, cách này đơn giản. Nhưng khi ứng dụng liên tục nhận hàng nghìn tác vụ, việc tạo một platform thread cho mỗi tác vụ có thể làm tăng overhead, số lượng stack/thread của OS, contention và khó kiểm soát shutdown. Nếu nhiều tác vụ cần dùng một số lượng worker hữu hạn, application còn cần:

- **Nơi nhận task** thay vì trực tiếp quản lý từng thread.
- **Chính sách thực thi:** chạy ngay trong caller, tạo worker, đưa vào queue, giới hạn concurrency.
- **Kết quả/ngoại lệ:** nhận được giá trị của `Callable` và biết task thành công hay thất bại.
- **Quản lý vòng đời:** ngừng nhận task mới, đợi task cũ hoàn tất, hủy khi cần.
- **Backpressure/rejection:** nếu worker và queue đều bận thì xử lý task mới thế nào?
- **Quan sát/tuning:** queue length, active threads, completed tasks, latency và failures.

Executor Framework **tách “cái gì cần làm” khỏi “task được chạy ở đâu và bằng cách nào”**. Thay vì `new Thread` khắp ứng dụng, caller mô tả công việc thành `Runnable` hoặc `Callable<T>` rồi giao cho một executor.

**Bảo đảm quan trọng:** một executor **không nhất thiết chạy task trên thread mới**. `Executor` chỉ quy định một giao diện thực thi. Implementation có thể chạy đồng bộ trong caller, trên một worker dùng lại, trên pool, hoặc bằng chiến lược khác. Đừng mặc định gọi `execute()` đồng nghĩa bắt đầu thread mới.

## 2. Ba cấp API cần phân biệt

```text
Executor
   |
   +-- execute(Runnable)
   |
   +-- ExecutorService extends Executor
          |
          +-- submit(...), invokeAll(...), invokeAny(...)
          +-- shutdown(), shutdownNow(), awaitTermination(...)
          +-- Future<T> cho kết quả/hủy
          |
          +-- ThreadPoolExecutor implements ExecutorService
                 |
                 +-- corePoolSize, maximumPoolSize, keepAliveTime
                 +-- BlockingQueue<Runnable>, ThreadFactory
                 +-- RejectedExecutionHandler, metrics/hook
```

### 2.1. `Executor`: “hãy thực thi Runnable này”

`Executor` là functional interface với một phương thức:

```java
void execute(Runnable command);
```

Đây là **chữ ký API minh họa**, không phải method cần tự cài cho mọi ứng dụng. Một executor thực tế quyết định task chạy khi nào/ở đâu.

Ví dụ **direct executor** không tạo worker:

```java
import java.util.concurrent.Executor;

Executor direct = Runnable::run;
direct.execute(() -> System.out.println("Executed by caller"));
```

Đây là đoạn code đặt trong method (có import). `Runnable::run` gọi `run()` trực tiếp ở thread gọi `execute()`, nên **không có bất đồng bộ**. Ví dụ cho thấy không nên suy từ tên `Executor` rằng nó luôn có thread pool.

`Executor.execute()` nhận `Runnable` và không trả `Future`. Nếu muốn nhận một kết quả/ngoại lệ dưới dạng đối tượng có thể đợi, dùng `ExecutorService.submit()` hoặc tự kết hợp một cơ chế completion.

### 2.2. `ExecutorService`: giao task, lấy kết quả, quản lý lifecycle

`ExecutorService` **mở rộng** `Executor`, thêm những phương thức cốt lõi:

- `submit(Runnable)` trả `Future<?>`; với task hoàn tất bình thường, `get()` trả `null`.
- `submit(Callable<T>)` trả `Future<T>`; `get()` trả kết quả kiểu T hoặc ném `ExecutionException` nếu task thất bại.
- `submit(Runnable, T result)` trả Future với giá trị result khi runnable hoàn tất thành công.
- `invokeAll(Collection<? extends Callable<T>>)` nhận nhiều task và trả danh sách Future theo thứ tự **đầu vào**, không phải theo thứ tự task hoàn thành.
- `invokeAny(...)` trả một kết quả thành công từ tập task, không cam kết task nào thắng; các task còn lại có thể bị hủy theo contract.
- `shutdown()` ngừng nhận task mới và tiếp tục xử lý những task đã giao.
- `shutdownNow()` cố gắng dừng task đang chạy và trả danh sách task đã được xếp hàng nhưng chưa khởi chạy.
- `awaitTermination(timeout, unit)` đợi pool đi tới trạng thái terminated hoặc hết thời hạn/interrupt.
- `isShutdown()` và `isTerminated()` giúp quan sát lifecycle.

`ExecutorService` là một **interface**. Không thể kết luận core threads, queue hay rejection policy của mọi instance chỉ từ kiểu `ExecutorService`: cách thực thi thực tế phụ thuộc implementation.

### 2.3. `ThreadPoolExecutor`: implementation có cấu hình cụ thể

`ThreadPoolExecutor` là một class trong `java.util.concurrent` cho phép điều khiển:

1. Số worker lõi: `corePoolSize`.
2. Số worker tối đa: `maximumPoolSize`.
3. Thời gian worker vượt core được giữ khi idle: `keepAliveTime`.
4. Queue chứa task chưa chạy: `BlockingQueue<Runnable>`.
5. Cách tạo worker: `ThreadFactory`.
6. Cách xử lý task không thể nhận: `RejectedExecutionHandler`.

Constructor đại diện:

```java
ThreadPoolExecutor pool = new ThreadPoolExecutor(
    2, 4,
    30L, TimeUnit.SECONDS,
    new ArrayBlockingQueue<>(100),
    Executors.defaultThreadFactory(),
    new ThreadPoolExecutor.AbortPolicy()
);
```

Đây là đoạn code đặt trong method; cần import `ThreadPoolExecutor`, `TimeUnit`, `ArrayBlockingQueue` và `Executors`. Khi không còn dùng pool, phải thực hiện lifecycle shutdown; trong ví dụ này chưa có code đó vì chỉ minh họa constructor.

**Đừng hiểu `maximumPoolSize = 4` nghĩa là cứ có 4 task thì pool tạo 4 threads.** Sự tương tác giữa `corePoolSize` và loại queue quyết định lúc nào pool tạo worker mới.

## 3. `Runnable`, `Callable` và `Future`

### Runnable: không có giá trị trả về được khai báo

```java
Runnable task = () -> processEvent();
executor.execute(task);
```

Đây là minh họa với `processEvent()`/`executor` do caller cung cấp. `Runnable.run()` có chữ ký `void run()` và không khai báo checked exception. Nếu task thất bại, đường truyền exception phụ thuộc cách giao task và implementation, không mặc định có `Future.get()` để truy xuất.

### Callable: trả kết quả và có thể ném Exception

```java
Callable<Integer> task = () -> 21 * 2;
Future<Integer> result = service.submit(task);
Integer value = result.get();
```

Đây là đoạn code trong method có `service` là `ExecutorService`, cần import `java.util.concurrent.Callable` và `Future`; method phải xử lý/khai báo `InterruptedException`/`ExecutionException`.

`Callable<V>.call()` trả V và khai báo `throws Exception`. `ExecutorService.submit` đóng gói việc hoàn tất vào `Future`.

### `Future.get()` không phải thao tác “thăm dò không chờ”

- `get()` có thể **block** tới khi task hoàn tất.
- `get(timeout, unit)` có thể ném `TimeoutException`; **timeout ở `get` không tự hủy task**.
- Nếu task ném exception, `get()` ném `ExecutionException`, với `getCause()` chứa nguyên nhân.
- Nếu Future đã bị cancel, `get()` ném `CancellationException`.
- Nếu thread gọi `get` bị interrupt trong khi chờ, `get` ném `InterruptedException`.
- `isDone()` true khi task hoàn tất **bình thường, thất bại hoặc bị hủy**; không phải bằng chứng thành công.
- `isCancelled()` cho biết trạng thái hủy; `cancel(true)` yêu cầu interrupt nếu task đang chạy, **không cam kết code bỏ qua interrupt sẽ ngừng ngay**.

**Điểm quan trọng:** nếu chỉ gọi `submit` mà không quan sát Future hoặc kênh báo lỗi khác, exception trong task có thể trở thành lỗi “im lặng” ở tầng gọi. Với task quan trọng, phải kiểm tra/ghi nhận failure theo một giao thức rõ.

## 4. Ví dụ Java 17 chạy được: cả ba cấp API

Chương trình minh họa ba hành vi tách biệt và **không phụ thuộc vào may rủi của scheduler**:

1. `Executor` chạy task trực tiếp, xác nhận đã gọi Runnable.
2. `ExecutorService` nhận `Callable` và trả 42 qua `Future.get()`.
3. `ThreadPoolExecutor` có **một worker và queue capacity = 1**. Ta dùng latch để giữ worker trong task thứ nhất, xếp task thứ hai vào queue rồi nộp task thứ ba; với `AbortPolicy` task thứ ba **bị từ chối**. Sau đó thả latch, đọc hai kết quả, shutdown và đợi pool terminated.

Tạo file **`ExecutorFrameworkDemo.java`**:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class ExecutorFrameworkDemo {
    public static void main(String[] args) throws Exception {
        AtomicBoolean ran = new AtomicBoolean(false);
        Executor direct = Runnable::run;
        direct.execute(() -> ran.set(true));
        System.out.println("executorRan=" + ran.get());

        ExecutorService service = Executors.newSingleThreadExecutor();
        try {
            Future<Integer> answer = service.submit(() -> 6 * 7);
            System.out.println("submitResult=" + answer.get());
        } finally {
            service.shutdown();
        }

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.AbortPolicy());
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<String> first = pool.submit(() -> {
                started.countDown();
                release.await();
                return "first";
            });
            started.await();
            Future<String> second = pool.submit(() -> "second");

            boolean rejected = false;
            try {
                pool.execute(() -> { });
            } catch (RejectedExecutionException expected) {
                rejected = true;
            }
            System.out.println("rejectedWhenSaturated=" + rejected);

            release.countDown();
            System.out.println("taskResults=" + first.get() + "," + second.get());
        } finally {
            release.countDown();
            pool.shutdown();
        }
        System.out.println("poolTerminated="
                + pool.awaitTermination(5, TimeUnit.SECONDS));
    }
}
```

Biên dịch và chạy với JDK 17 hoặc mới hơn:

```bash
javac --release 17 ExecutorFrameworkDemo.java
java ExecutorFrameworkDemo
```

**Stdout đã kiểm chứng:**

```text
executorRan=true
submitResult=42
rejectedWhenSaturated=true
taskResults=first,second
poolTerminated=true
```

### Phân tích từng dòng

**`executorRan=true`:** `Runnable::run` chạy trực tiếp nên giá trị AtomicBoolean đã đổi trước khi `execute()` trở về. Không có một platform thread mới nào được tạo chỉ vì gọi `Executor.execute()` trong trường hợp này.

**`submitResult=42`:** `Executors.newSingleThreadExecutor()` cung cấp `ExecutorService` với một worker thực thi các task tuần tự. `submit(Callable<Integer>)` trả Future; `get()` chờ phép tính hoàn thành và lấy kết quả.

**`rejectedWhenSaturated=true`:**

- `ThreadPoolExecutor(1,1,..., new ArrayBlockingQueue<>(1), AbortPolicy)` chỉ có tối đa **một active worker**.
- Task thứ nhất được worker chạy và báo `started.countDown()` rồi **chờ `release.await()`**, nên worker không rảnh.
- `started.await()` ở main xác nhận task thứ nhất đang ở checkpoint trước khi nộp task tiếp theo.
- Task thứ hai không thể nhận thêm worker (max = 1), vì vậy được enqueue vào **slot duy nhất**.
- Task thứ ba đến khi worker đã bận và queue đầy. `AbortPolicy` ném `RejectedExecutionException`, code catch và in true.

**`taskResults=first,second`:** sau `release.countDown()`, worker tiếp tục task thứ nhất, rồi chạy task thứ hai từ queue. Đọc `Future.get()` bảo đảm cả hai hoàn thành; biểu thức kết quả được kết hợp theo thứ tự main gọi get, không phải vì scheduler hứa thứ tự gọi `submit` luôn phản ánh thứ tự completion của các thread trong mọi loại pool.

**`poolTerminated=true`:** sau khi đã lấy hai Future và gọi `pool.shutdown()`, `awaitTermination` thành công trong lần chạy kiểm chứng. `awaitTermination` có timeout 5 giây nên trong môi trường bị kẹt bất thường nó có thể trả false; chương trình in đúng trạng thái được quan sát, không suy từ timeout rằng mọi thread chắc chắn đã dừng.

### Giới hạn mẫu thực hành

- Latch chỉ kiểm soát **lịch thử nghiệm**, không phải mô hình xử lý công việc production.
- Code dùng `shutdown()` sau các task hoàn tất; production nên có cancellation/timeout hoặc shutdown policy khi Future không bao giờ kết thúc.
- Lệnh `release.countDown()` trong `finally` tránh để worker tiếp tục kẹt ở latch nếu main gặp exception giữa chừng.
- Các class executor chuẩn Java SE không tự mang lại transaction cho database, external API hoặc file system.
- Với task thất bại trong `submit`, có thể lấy nguyên nhân từ `ExecutionException.getCause()`. `Future.get` là ranh giới completion/visibility, không phải bảo đảm “mọi side effect bên ngoài JVM đã commit”.

## 5. ThreadPoolExecutor xử lý task mới như thế nào?

Với một `ThreadPoolExecutor` đang ở trạng thái chạy và cấu hình thông thường, nguyên lý admission chính:

1. Nếu số worker đang có **nhỏ hơn `corePoolSize`**, ưu tiên tạo worker để chạy task mới.
2. Nếu đã đạt core, thử **đưa task vào work queue**.
3. Nếu queue không nhận được task (thường vì đã đầy), thử **tạo thêm worker** nếu tổng số worker còn dưới `maximumPoolSize`.
4. Nếu không thể enqueue hoặc tạo thêm worker, executor **reject** task theo `RejectedExecutionHandler`.

```text
                  execute(task)
                       |
             workerCount < core?
              /               \
            yes               no
             |                 |
        tạo worker       offer vào workQueue
                              /      \
                        thành công    thất bại
                            |            |
                         xếp hàng   workerCount < max?
                                      /       \
                                     yes      no
                                      |        |
                                  tạo worker  REJECT
```

Sơ đồ giản lược này giải thích chiến lược phổ biến; bên trong class còn có kiểm tra trạng thái pool và xử lý race khi shutdown. **Task có thể bị reject khi pool đang shutdown**, ngay cả khi queue chưa đầy.

### Ví dụ `core=2`, `max=4`, queue capacity 3

- Task 1 và 2 có thể tạo hai core workers.
- Khi hai core workers đang bận, task 3–5 có thể nằm trong queue.
- Task 6–7 đến khi queue đầy có thể kích hoạt worker thứ 3 và thứ 4.
- Task 8 đến khi 4 worker đều bận và queue vẫn đầy → rejection theo policy.

Đây là một **kịch bản minh họa khi các task đầu chưa kết thúc**. Nếu task hoàn tất nhanh, thread pool có thể tái sử dụng worker và queue không thực sự đầy; đừng coi số thứ tự task như lịch cố định của mọi execution.

### Những cấu hình làm `maximumPoolSize` ít tác dụng

Nếu work queue là `LinkedBlockingQueue` **gần như không giới hạn**, task có thể liên tục được enqueue sau khi đạt core, nên pool thường **không tăng worker vượt core** chỉ vì queue còn rất nhiều task. Lúc đó `maximumPoolSize` có thể không phát huy chức năng mở rộng như người cấu hình tưởng.

Nếu dùng `SynchronousQueue`, nó không lưu item nội bộ: producer giao task trực tiếp cho worker nhận. Khi không có worker rảnh và số worker chưa đạt max, pool có thể tăng worker mạnh hơn; cấu hình max quá lớn có nguy cơ tạo rất nhiều threads dưới burst.

**Chọn queue có chủ đích**, vì nó ảnh hưởng không chỉ memory/backpressure mà còn ảnh hưởng trực tiếp đến cách thread pool tăng số worker.

## 6. Các tham số chính và đánh đổi

| Tham số | Ý nghĩa | Lỗi hiểu nhầm hay gặp |
|---|---|---|
| `corePoolSize` | Số worker mục tiêu được duy trì theo chính sách; worker có thể được tạo khi task đến, không nhất thiết được tạo hết từ constructor | “Core threads luôn được prestart ngay” |
| `maximumPoolSize` | Trần số worker trong executor (tùy điều kiện queue và lifecycle) | “Pool sẽ luôn tăng tới max khi task đến nhiều” |
| `keepAliveTime` | Idle timeout với worker vượt core theo mặc định | “Tất cả core threads tự dừng sau keepAlive” |
| `workQueue` | Lưu task đang chờ worker | “Queue thread-safe nghĩa là backlog không thể tăng vô hạn” |
| `ThreadFactory` | Cách tạo thread: tên, daemon flag, ưu tiên, `UncaughtExceptionHandler`, v.v. | “Đặt daemon=true là một shutdown strategy đúng” |
| `RejectedExecutionHandler` | Chính sách khi task không thể được nhận | “Reject luôn ném exception” |
| `allowCoreThreadTimeOut(true)` | Cho phép core workers cũng timeout khi idle nếu điều kiện API được đáp ứng | “Có thể bật với keepAlive=0 một cách mặc nhiên” |

### Số worker và loại workload

**CPU-bound:** nếu task chủ yếu tính toán và không block, số platform workers gần số CPU thực sự khả dụng thường là một điểm bắt đầu để đo lường. Tăng quá nhiều workers tạo context switching, cache contention và giảm throughput.

**I/O-bound:** task đợi network/disk có thể có lợi khi số concurrent tasks lớn hơn số CPU. Nhưng cần kiểm tra giới hạn downstream: connection pool, API rate limit, file descriptors, bộ nhớ và latency. Số worker lớn không giải quyết được tài nguyên bên ngoài bị quá tải.

**Hỗn hợp:** tách các nhóm workload có đặc tính khác nhau hoặc dùng deadline/capacity riêng. Ví dụ task đọc file rất lâu không nên ngăn các tác vụ cập nhật UI/health-check quan trọng được cấp worker.

Đây là hướng dẫn **điểm bắt đầu để đo**, không phải công thức cố định; workload cần benchmark, profiling và thử nghiệm quá tải với SLA thực.

### `prestartCoreThread(s)`

`ThreadPoolExecutor` có `prestartCoreThread()` và `prestartAllCoreThreads()` để tạo worker lõi trước khi task được nhận, khi cần giảm cold-start latency. Không bắt buộc dùng; tạo nhiều threads rảnh sớm cũng tốn tài nguyên.

### `allowCoreThreadTimeOut`

Nếu muốn core workers cũng được thu hồi khi idle, `allowCoreThreadTimeOut(true)` cho phép cơ chế đó với cấu hình keep-alive hợp lệ. Khi task mới đến, worker có thể được tạo lại. Điều này đánh đổi tài nguyên lúc nhàn rỗi với thời gian khởi tạo lại worker.

## 7. Work queue và backpressure

`ThreadPoolExecutor` thường dùng một `BlockingQueue<Runnable>` để chứa task chưa được cấp worker. Đây là **queue task của executor**, không nhất thiết cùng một queue dữ liệu mà business logic tự dùng để chuyển message.

Một số lựa chọn:

- `ArrayBlockingQueue<>(capacity)`: capacity rõ, FIFO, tránh backlog vô hạn trong queue của pool.
- `LinkedBlockingQueue<>(capacity)`: bounded linked queue nếu truyền capacity cụ thể.
- `new LinkedBlockingQueue<>()`: mặc định capacity rất lớn (`Integer.MAX_VALUE`), **không phải giới hạn bộ nhớ thực dụng**.
- `SynchronousQueue<>()`: handoff trực tiếp, không giữ backlog trong queue, khiến admission phụ thuộc worker sẵn sàng hoặc việc tạo worker mới.
- `PriorityBlockingQueue`: thứ tự priority thay vì FIFO và không có hard bound capacity như `ArrayBlockingQueue`; không mặc định thích hợp để giới hạn tài nguyên.

**Capacity của work queue không đồng nghĩa tổng công việc trong hệ thống.** Tổng số task được executor nhận có thể gồm các task đang chạy và các task đang nằm trong queue. Ngoài ra còn có task đang ở upstream queues, HTTP buffers, message brokers hoặc sources khác.

### Chọn backpressure một cách rõ ràng

Nếu tất cả worker đang bận và work queue đầy, executor phải quyết định **không thể nhận thêm task**. Policy mặc định của `ThreadPoolExecutor` khi dùng `AbortPolicy` là ném `RejectedExecutionException`.

Caller nên xử lý rejection theo contract:

- Trả “quá tải” cho upstream.
- Retry với giới hạn, backoff và idempotency.
- Chuyển công việc sang tầng lưu trữ bền vững nếu không được phép mất.
- Giảm tốc upstream/rate limit.
- Dùng caller-runs có cân nhắc để truyền áp lực ngược vào thread gửi task.

**Không được im lặng bỏ qua rejection** nếu tác vụ là đơn hàng, thanh toán hoặc event bắt buộc xử lý. Mất task vì “đầy queue” là hành vi nghiệp vụ cần được khai báo và giám sát.

## 8. Rejection policies của ThreadPoolExecutor

| Handler | Hành vi tổng quát | Khi dùng phải lưu ý |
|---|---|---|
| `AbortPolicy` | Ném `RejectedExecutionException` | Caller phải catch/propagate/report |
| `CallerRunsPolicy` | Chạy task trong **thread gọi execute** nếu pool chưa shutdown | Làm caller chậm (backpressure), phá giả định “task luôn chạy ở worker”; khi pool shutdown thì task bị bỏ |
| `DiscardPolicy` | Im lặng bỏ task | Có thể mất dữ liệu; không phù hợp việc bắt buộc hoàn tất |
| `DiscardOldestPolicy` | Bỏ task ở đầu queue rồi thử submit lại task mới khi còn chạy | Có thể loại công việc quan trọng, tương tác không mong muốn với queue priority và concurrency |

### `CallerRunsPolicy` không phải lúc nào cũng là lựa chọn vô hại

Nếu task thực thi I/O nặng và caller là request thread, caller-runs khiến request latency tăng đột biến. Nếu task thực thi mã dựa trên identity/ThreadLocal của worker, việc task chạy trong caller có thể gây lỗi ngữ nghĩa. Với `submit()`, task thường được bọc thành một `FutureTask`: caller-runs có thể thực hiện ngay trong caller, làm lời gọi `submit` tốn thời gian trước khi trả Future.

**Đặc biệt:** khi executor đã shutdown, `CallerRunsPolicy` **không chạy** task được reject mà có thể bỏ qua. Vì thế nếu cần bảo đảm “task luôn được thực thi hoặc trả lỗi”, phải thiết kế rejection contract riêng, không mặc định caller-runs là an toàn tuyệt đối.

### `DiscardOldestPolicy` và FIFO queue

“Oldest” ở đây là task ở đầu queue theo hành vi `poll()` của queue, **không nhất thiết là task có timestamp nghiệp vụ cũ nhất**. Với priority queue, “head” còn có thể là task ưu tiên cao nhất—discarding nó có thể trái kỳ vọng.

Cả hai discard handlers có thể gây mất việc. Chỉ dùng khi product contract thực sự cho phép bỏ task và có metrics để phát hiện.

### Custom handler

`RejectedExecutionHandler.rejectedExecution(Runnable r, ThreadPoolExecutor executor)` cho phép đưa ra chính sách riêng. Một handler production có thể báo metric và ném exception có nội dung rõ, nhưng phải tránh **block vô hạn hoặc deadlock** trong cùng executor đang quá tải. Handler chạy trên đường gửi task và phải được audit về concurrency.

## 9. `execute` và `submit`: exception đi đâu?

Đây là một trong các khác biệt vận hành hay bị bỏ qua.

```java
// Minh họa trong method, executor là ThreadPoolExecutor:
executor.execute(() -> {
    throw new IllegalStateException("failed in execute");
});

Future<?> future = executor.submit(() -> {
    throw new IllegalStateException("failed in submit");
});
```

Đây là **đoạn minh họa** với imports phù hợp. Trong `submit`, executor bọc task qua `FutureTask` và lưu kết quả/exception vào Future; việc đọc `future.get()` ném `ExecutionException` mang cause `IllegalStateException`.

Với `execute`, unchecked exception có thể thoát khỏi method `run()` của worker và được xử lý theo cơ chế uncaught exception của thread/implementation; không có Future trả về cho caller để truy vấn nguyên nhân. Không được suy rằng chỉ nhìn `System.err` là một chiến lược error monitoring đầy đủ.

`ThreadPoolExecutor.afterExecute(Runnable r, Throwable t)` có thể được override để thu thập thông tin task completion, nhưng lưu ý: **khi task do `submit` bọc bằng `FutureTask`, exception thường nằm trong Future, và tham số `t` của hook có thể là null**. Nếu cần lấy failure, phải kiểm tra Future một cách cẩn thận (và tránh block vô hạn trong hook).

**Khuyến nghị vận hành:** dùng một cơ chế rõ ràng để **ghi nhận task thất bại**, bao gồm cả business exceptions và infrastructure exceptions, thay vì chỉ dựa vào logs mặc định của worker.

## 10. Vòng đời ExecutorService và shutdown an toàn

### Các trạng thái logic

Một executor có thể:

1. **Running:** nhận task mới.
2. **Shutdown:** không nhận task mới, nhưng có thể tiếp tục các task đã nhận.
3. **Terminated:** không còn task đang thực thi; executor đã kết thúc.
4. **Stop attempt:** `shutdownNow()` cố interrupt task đang chạy, không bảo đảm mọi task dừng tức thì.

`shutdown()` không đợi. `awaitTermination()` **chỉ đợi** và trả boolean; nó không tự gọi `shutdown()`. Nếu không gọi shutdown, một pool còn worker có thể làm JVM tiếp tục chạy (đặc biệt khi threads không phải daemon). Do đó resource ownership và lifecycle phải rõ ràng.

### Mẫu graceful shutdown

```java
static void stopGracefully(ExecutorService service)
        throws InterruptedException {
    service.shutdown(); // không nhận task mới
    try {
        if (!service.awaitTermination(10, TimeUnit.SECONDS)) {
            service.shutdownNow(); // yêu cầu interrupt task đang chạy
            if (!service.awaitTermination(10, TimeUnit.SECONDS)) {
                System.err.println("Executor did not terminate");
            }
        }
    } catch (InterruptedException e) {
        service.shutdownNow();
        Thread.currentThread().interrupt();
        throw e;
    }
}
```

Đây là **static method minh họa** đặt trong class có import `ExecutorService`, `TimeUnit`; ngưỡng 10 giây chỉ là ví dụ, cần chọn theo workload/SLA. Khi cần propagate `InterruptedException`, khôi phục interrupt flag trước khi rethrow có thể phù hợp với contract caller; nếu dừng theo phương án khác thì chính sách đó phải được định nghĩa rõ.

`shutdownNow()` thường sử dụng `Thread.interrupt()` như một tín hiệu. Nếu task bỏ qua interrupt, đang block ở thao tác không interruptible, hoặc giữ vòng lặp vô hạn, nó vẫn có thể tiếp tục. Không được tin rằng một lần shutdownNow là “kill task” tuyệt đối.

### Cancellation trong task

Task hợp tác với interrupt:

```java
Runnable task = () -> {
    try {
        while (!Thread.currentThread().isInterrupted()) {
            performOneUnitOfWork();
        }
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
    } finally {
        cleanupOwnedResources();
    }
};
```

Đây là **mã minh họa**: `performOneUnitOfWork()` có thể ném `InterruptedException`, `cleanupOwnedResources()` phải được định nghĩa. Task không nên catch `InterruptedException` rồi tiếp tục mãi và làm shutdown bị treo. Với `Future.cancel(true)`, người gọi yêu cầu interrupt; việc task dừng nhanh tới đâu còn tùy code và nơi đang block.

**Lưu ý:** `Future.get(timeout)` có timeout chỉ cho **caller đang đợi**; nó **không tự gọi `cancel(true)`**. Nếu muốn hủy sau deadline, caller phải thiết kế thao tác hủy và xử lý kết quả.

## 11. Deadlock thường gặp khi task đợi task khác cùng pool

Một executor có thể deadlock mà không có hai lock lồng nhau. Ví dụ một worker đang chạy task A, A submit task B vào **cùng single-thread executor**, rồi A gọi `Future.get()` để chờ B.

```java
// Minh họa sai: chạy đoạn này với pool chỉ có một worker.
ExecutorService pool = Executors.newSingleThreadExecutor();
pool.submit(() -> {
    Future<Integer> other = pool.submit(() -> 42);
    return other.get(); // A chờ B; B chưa có worker để chạy.
});
```

Đoạn code minh họa cần imports `java.util.concurrent`, và nếu được chạy nguyên vẹn sẽ có nguy cơ **treo**; không dùng nó làm chương trình thực hành chạy. Task A giữ worker duy nhất rồi đợi B; B đang xếp hàng và cần worker đó, tạo **thread starvation deadlock**.

Tăng pool size đôi khi tránh tình huống cụ thể nhưng không phải lời giải đủ nếu graph phụ thuộc có thể sâu hơn hoặc mọi worker cùng block. Giải pháp đúng có thể là:

- Không chờ Future của task phụ thuộc trên **cùng executor có số worker hữu hạn**.
- Tổ chức computation thành một task lớn hơn khi không cần concurrency.
- Dùng completion orchestration phù hợp, hoặc pool tách biệt với capacity được thiết kế.
- Hạn chế blocking call bên trong worker khi chúng cần chính pool đó để tiến triển.
- Đặt timeout/cancellation cho các điểm chờ và theo dõi active/queued tasks.

Một mẫu khác: N worker trong pool đồng loạt gọi `BlockingQueue.put` trên queue đang đầy, nhưng task consumer cần được chạy trên **chính pool đã hết worker**. Worker không nhả chỗ, consumer không được cấp CPU/worker → treo. Khi thiết kế pipeline, phải xét cả executor work queue lẫn business data queue.

## 12. Tác vụ dài hạn và một pool chung

Nếu trộn task rất ngắn với tác vụ block network nhiều phút trong một pool nhỏ, short tasks có thể bị starvation hoặc latency cao dù chúng chỉ cần ít CPU.

### Cách tách workload

- **CPU executor:** số worker vừa phải theo CPU khả dụng, tránh blocking I/O kéo dài.
- **I/O executor:** concurrency/queue có giới hạn phù hợp với connection pool và downstream capacity.
- **Scheduled executor:** nhiệm vụ delay/periodic dùng `ScheduledExecutorService`/`ScheduledThreadPoolExecutor` thay vì tự `Thread.sleep()` trong worker thường.
- **Single-thread owner:** các command cần thực thi tuần tự vì invariant có thể dùng `newSingleThreadExecutor()`, nhưng backlog và shutdown vẫn phải được kiểm soát.

Không phải lúc nào cũng cần nhiều pool; chia quá nhiều pools gây phức tạp lifecycle và dùng tài nguyên kém. Hãy tách khi SLA, loại chờ, khả năng scale hoặc owner của state thật sự khác nhau.

### `Executors` factory methods và rủi ro mặc định

| Factory | Hành vi nổi bật | Cần cảnh giác |
|---|---|---|
| `newSingleThreadExecutor()` | Một worker xử lý task tuần tự; worker được thay khi thất bại theo contract | Queue có thể phát triển lớn; không phải bounded admission |
| `newFixedThreadPool(n)` | Số worker cố định n, tái sử dụng | Work queue mặc định **không có hard bound nhỏ**, có thể backlog |
| `newCachedThreadPool()` | Tái sử dụng worker rảnh và tạo thêm theo nhu cầu | Có thể tạo rất nhiều platform threads dưới burst, phải cân nhắc giới hạn |
| `newScheduledThreadPool(n)` | Delay và periodic tasks | Chính sách queue/timer khác; task periodic lỗi có thể ngừng các lần chạy kế tiếp |
| `newWorkStealingPool()` | Dựa trên `ForkJoinPool`, work-stealing | Không bảo đảm thứ tự thực thi; không tương đương pool FIFO truyền thống |
| `newSingleThreadScheduledExecutor()` | Một worker cho lịch chạy tuần tự | Task dài làm những lần chạy sau bị trễ |

**Quan trọng:** `newFixedThreadPool(n)` chỉ giới hạn worker count, **không giới hạn số task chờ thực tế** theo một capacity nhỏ. Khi producer nhanh hơn consumer, work queue có thể tích tụ rất nhiều task và ăn RAM. Nếu cần bounded queue + rejection policy cụ thể, dùng `ThreadPoolExecutor` với constructor rõ ràng.

## 13. ThreadFactory và quan sát thread

`ThreadFactory` quyết định cách tạo worker mới. Có thể dùng để:

- Đặt tên thread dễ chẩn đoán như `image-worker-1`, `image-worker-2`.
- Đặt `UncaughtExceptionHandler` cho các lỗi uncaught (không thay thế đọc exception trong Future).
- Quyết định daemon/thread priority theo policy có kiểm chứng.
- Tạo worker thuộc context/class loader/thread group phù hợp với môi trường.

Ví dụ Java 17:

```java
AtomicInteger sequence = new AtomicInteger();
ThreadFactory factory = runnable -> {
    Thread t = new Thread(runnable,
            "image-worker-" + sequence.incrementAndGet());
    t.setDaemon(false);
    return t;
};
```

Đây là đoạn code đặt trong method với imports `java.util.concurrent.ThreadFactory` và `java.util.concurrent.atomic.AtomicInteger`.

**Không chọn daemon=true chỉ để JVM tự tắt** nếu có công việc quan trọng chưa hoàn tất. Daemon threads có thể bị dừng khi JVM kết thúc mà không bảo đảm flush dữ liệu/commit state. Resource owner vẫn phải shutdown và đợi completion theo contract.

ThreadFactory có thể từ chối tạo thread (ví dụ trả null theo một số tình huống); class pool xử lý việc tạo worker theo hành vi API. Với production, custom factory cần được kiểm thử khi hệ thống thiếu tài nguyên hoặc cấu hình không hợp lệ.

## 14. Memory visibility và Java Memory Model

Executor Framework không chỉ là hàng đợi task; các API concurrency của Java có quy tắc memory consistency để dữ liệu được công bố an toàn giữa threads.

Các quan hệ thường gặp:

1. Hành động trong thread trước khi **submit** một `Runnable/Callable` cho `ExecutorService` *happen-before* các hành động bên trong task đó.
2. Hành động bên trong task *happen-before* những hành động của thread khác **sau khi `Future.get()` lấy kết quả thành công** theo contract của API.
3. Với `Executor.execute`, tài liệu API mô tả memory consistency cho các hành động trước khi submit `Runnable` và bắt đầu thực thi nó.
4. Những quan hệ từ `Thread.start`, `join`, volatile, locks và queues vẫn áp dụng nếu chương trình có thêm cơ chế phối hợp.

Ví dụ:

```java
// Minh họa trong một method, có sẵn ExecutorService service:
int[] data = {10, 20};
Future<Integer> task = service.submit(() -> data[0] + data[1]);
System.out.println(task.get()); // 30 nếu không có mutation cạnh tranh
```

Đây là code minh họa, method cần khai báo/xử lý checked exceptions. Nếu main tạo `data` trước submit và **không sửa nó đồng thời**, worker có thể thấy dữ liệu đã chuẩn bị theo memory consistency contract; sau `get()` main nhận kết quả đúng.

**Nhưng:** submission không khiến mọi mutation sau submit tự an toàn. Nếu main đổi `data[0]` trong lúc worker đọc, vẫn phải có synchronization/ownership riêng. Task return không tự làm các object mutable mà nó trả về trở thành immutable.

### Future.get và visibility không sửa atomicity của work

Nếu hai task cùng làm `counter++` trên một `int` thường thiếu synchronization, main đợi cả hai bằng `Future.get()` **không cứu lost update**. `get()` chỉ là ranh giới completion/visibility giữa task và caller; cập nhật giữa hai workers đã có thể race trước đó.

Sửa bằng:

- `AtomicInteger.incrementAndGet()` cho counter độc lập.
- `synchronized`/`Lock` cho invariant đa bước.
- Task-local accumulators rồi merge sau `Future.get()`.
- Immutable message/ownership transfer khi muốn tránh shared mutable state.

## 15. Metrics: quan sát pool theo đúng semantics

`ThreadPoolExecutor` có API quan sát như:

```java
int core = pool.getCorePoolSize();
int max = pool.getMaximumPoolSize();
int current = pool.getPoolSize();
int active = pool.getActiveCount();
int queued = pool.getQueue().size();
long completed = pool.getCompletedTaskCount();
```

Đây là **đoạn minh họa trong method** với `pool` là `ThreadPoolExecutor`.

Các số liệu được dùng để theo dõi:

- **Active count:** số worker đang thực thi task vào thời điểm quan sát (một số count có tính ước lượng).
- **Pool size:** tổng số worker hiện có.
- **Queue depth:** số task còn chờ, không bao gồm task đang thực thi.
- **Completed tasks:** số task đã hoàn thành ở mức executor, **không có nghĩa business operation thành công**.
- **Rejection count:** thường cần tự theo dõi trong rejection handler vì không có “rejected task counter” tiêu chuẩn đầy đủ trên mọi executor.
- **Task wait time:** thời gian từ submit đến start (nếu instrument), khác execution time.
- **Task execution time, queue age và latency end-to-end:** giúp biết bottleneck nằm ở cấp nhận task, worker hay downstream.

Một số getter dùng snapshot/ước lượng, có thể thay đổi ngay sau khi đọc. **Không dùng `getQueue().size()` rồi quyết định chắc chắn task tiếp theo sẽ được nhận**, vì concurrent submissions/completions có thể thay đổi queue. Đừng gọi `getQueue().clear()` như một cách “điều tiết bình thường”: tác động đến các task đã được chấp nhận và có thể làm Future không bao giờ hoàn thành như caller kỳ vọng.

### Thread dump và JFR

Khi nghi pool đang nghẽn:

```bash
jcmd <PID> Thread.print -l
```

Thay `<PID>` bằng process ID thật. Xem worker đang chạy, chờ queue, blocked trên monitor hay đang đợi network/DB. `WAITING (parking)` của idle worker có thể là **bình thường**, không đồng nghĩa deadlock.

Với workload đủ dài, JFR giúp xem sự kiện thread park, contention và hot spots tùy JVM/recording settings. Quan sát thread state chỉ là một snapshot; phải kết hợp queue depth, task latency, retry/rejection và các SLA nghiệp vụ.

## 16. Những quyết định quan trọng trước khi tuning pool

Khi chuẩn bị một executor cho production, nên trả lời rõ:

1. **Task là gì?** CPU-bound, I/O-bound, long-running, periodic hay có external side effect?
2. **Tải đến như thế nào?** Trung bình, burst, peak concurrency và khả năng giảm tốc upstream?
3. **SLO latency/throughput nào phải giữ?** Thời gian chờ queue có bao gồm trong deadline không?
4. **Giới hạn bộ nhớ?** Một queued task giữ bao nhiêu reference/payload; capacity cần bao nhiêu?
5. **Downstream có capacity nào?** DB connections, HTTP pool, API quota, disk throughput?
6. **Task được phép reject/drop không?** Nếu không, cần cơ chế bền vững/retry/idempotency?
7. **Quy tắc hủy ra sao?** Deadline, interrupt, retry và rollback/compensation?
8. **Exception được quan sát ở đâu?** Future, CompletionService, logging/metrics, error channel?
9. **Ai sở hữu executor?** Ai được shutdown và lúc nào? Không để một service bất kỳ tắt pool dùng chung.
10. **Có phụ thuộc task-task?** Một task có gọi `Future.get` của task khác cùng pool không?
11. **Có mutable state chia sẻ?** Task submission không thay synchronization của chính state.
12. **Có metrics và bài test quá tải không?** Chỉ test với hai task nhẹ không cho biết behavior khi queue full.

Tuning có ý nghĩa khi đã xác định chính xác acceptance semantics và lifecycle. Tăng thread count để giảm queue depth có thể làm downstream quá tải và tăng lỗi; giảm threads để tiết kiệm CPU có thể gây starvation cho tác vụ phụ thuộc lẫn nhau.

## 17. Khi nào cần CompletionService, ScheduledExecutorService hoặc ForkJoinPool?

Ba loại API này liên quan Executor Framework, nhưng **không thay đổi ý nghĩa của ba cấp chính**:

### `ExecutorCompletionService<V>`

Nếu submit nhiều `Callable` và muốn lấy kết quả **theo thứ tự hoàn tất**, `ExecutorCompletionService` bọc một `Executor`/`ExecutorService`, cung cấp completion queue của Future. Điều này khác việc gọi `future1.get()` rồi `future2.get()` theo thứ tự đầu vào: một Future chậm ở đầu có thể làm caller đợi dù Future khác đã hoàn thành.

### `ScheduledExecutorService`

Dùng để chạy task sau delay hoặc định kỳ:

- `schedule`: chạy một lần sau delay.
- `scheduleAtFixedRate`: lịch dựa trên khoảng bắt đầu định kỳ.
- `scheduleWithFixedDelay`: chờ một khoảng sau khi lần chạy trước kết thúc.

Các periodic executions có thể bị trễ khi worker bận; không có bảo đảm đúng mốc thời gian thực tuyệt đối. Exception từ một lần periodic execution có thể khiến các lần chạy tiếp theo bị ngừng theo contract, cần giám sát Future/result.

### `ForkJoinPool`

Phù hợp với tác vụ chia nhỏ và work-stealing, đặc biệt khi bài toán có cấu trúc fork/join. Nó có queue/scheduling semantics riêng; không được suy rằng nó đảm bảo FIFO như một fixed thread pool dùng `LinkedBlockingQueue`. Blocking I/O kéo dài trong worker của fork/join có thể cần thiết kế và cơ chế quản lý blocking đặc biệt.

Bài này tập trung vào `Executor`, `ExecutorService` và `ThreadPoolExecutor`; các API trên là lựa chọn bổ trợ khi yêu cầu phù hợp.

## 18. Java 21+ virtual threads và sự khác biệt cần biết

Từ Java 21, virtual threads cho phép tạo nhiều thread Java nhẹ hơn platform threads trong nhiều workload blocking I/O. API `Executors.newVirtualThreadPerTaskExecutor()` tạo **một virtual thread mới cho mỗi task**, không phải một fixed pool của virtual threads theo `corePoolSize/maximumPoolSize`.

- Java 17 **chưa hỗ trợ ổn định virtual threads** như Java 21; ví dụ chính của bài dùng platform threads và chạy trên JDK 17.
- Không lấy tư duy “giới hạn platform thread pool” áp dụng máy móc cho virtual-thread-per-task executor. Muốn giới hạn số concurrent DB requests hoặc API calls, dùng Semaphore/rate limit/connection pool phù hợp.
- Virtual threads **không** loại bỏ data races, shared mutable state, timeout hay backpressure.
- Với các tác vụ CPU-bound, tạo thêm vô số virtual threads không giúp vượt số CPU vật lý; vẫn phải đo workload.

Phân biệt API theo **phiên bản JDK** trước khi sao chép code: `newVirtualThreadPerTaskExecutor()` không biên dịch với `--release 17`.

## 19. Lỗi phổ biến và cách sửa

1. **“Executor.execute luôn tạo thread mới.”** Sai: implementation có thể chạy đồng bộ trong caller như direct executor.
2. **“Executor và ExecutorService giống hệt nhau.”** Sai: `ExecutorService` có `submit`, `Future`, lifecycle/coordination APIs.
3. **“newFixedThreadPool(n) tự giới hạn mọi backlog ở n.”** Sai: n là số worker, queue có thể tăng rất lớn.
4. **“maximumPoolSize là số worker luôn tạo khi có nhiều task.”** Sai: pool thường ưu tiên queue sau khi đạt core; queue unbounded làm max ít được dùng.
5. **“shutdown chờ mọi task kết thúc.”** Sai: shutdown ngừng nhận task mới; đợi bằng Future/awaitTermination.
6. **“shutdownNow kill mọi task ngay lập tức.”** Sai: thường chỉ yêu cầu interrupt; task phải hợp tác.
7. **“Future.isDone nghĩa là task thành công.”** Sai: task có thể lỗi hoặc bị hủy.
8. **“future.get(timeout) tự động cancel nếu timeout.”** Sai: timeout của get không hủy task.
9. **“submit exception sẽ tự in stack trace như execute.”** Không thể dựa vào điều đó; task failure được giữ trong Future.
10. **“CallerRunsPolicy luôn ném lỗi khi từ chối.”** Sai: nó thường chạy trong caller nếu pool chưa shutdown; khi đã shutdown có thể bỏ task.
11. **“DiscardPolicy vẫn xử lý task theo cách khác.”** Sai: nó bỏ task; chỉ dùng khi được phép mất việc.
12. **“Đặt workQueue unbounded sẽ không hết bộ nhớ.”** Sai: backlog có thể tăng tới OOM dưới tải quá mức.
13. **“Các task đều độc lập vì chạy trong pool.”** Sai: shared mutable fields vẫn có thể race.
14. **“Future.get sau hai task sửa cùng counter bảo đảm đúng tổng.”** Sai: get hoàn tất/visibility, không sửa lost update giữa workers.
15. **“Thread pool một worker không thể deadlock.”** Sai: task đang chạy có thể đợi task khác chỉ có thể được chạy bởi worker duy nhất đó.
16. **“getQueue().size() == 0 nghĩa là mọi task hoàn thành.”** Sai: task có thể đang chạy.
17. **“Pool activeCount cao nghĩa là CPU luôn quá tải.”** Sai: workers có thể block I/O; cần CPU/stack/latency.
18. **“Đặt daemon=true đủ thay thế shutdown.”** Sai: công việc quan trọng có thể mất khi JVM thoát.
19. **“Tăng max threads luôn tăng throughput.”** Sai: downstream bottleneck, context switching và GC có thể xấu hơn.
20. **“ThreadFactory thay thế error handling.”** Sai: failures trong `submit` thường được lưu trong Future.
21. **“Mỗi method có thể tự shutdown executor được inject/shared.”** Sai về ownership: caller sở hữu lifecycle phải được định nghĩa để không làm hỏng users khác.
22. **“Có thread pool thì task tự có timeout.”** Không: deadline phải được thiết kế ở Future, I/O operations, cancellation và queue admission.

## 20. Câu hỏi ôn tập và đáp án

**Câu 1.** `Executor` có bắt buộc chạy task trên thread khác không?  
**Đáp án:** Không. Nó chỉ định giao diện `execute(Runnable)`; implementation có thể chạy trực tiếp trong caller.

**Câu 2.** Tại sao cần `ExecutorService` thay vì `Executor` nếu muốn nhận kết quả phép tính?  
**Đáp án:** `ExecutorService.submit(Callable<T>)` trả `Future<T>`, có thể `get()` để chờ kết quả và bắt exception/hủy.

**Câu 3.** `ExecutorService.shutdown()` có chờ task đang chạy xong không?  
**Đáp án:** Không. Nó ngừng nhận task mới; muốn đợi phải dùng Future/`awaitTermination`.

**Câu 4.** Pool core=2, max=8, queue rất lớn: tại sao có thể chỉ dùng 2 workers dù còn nhiều task?  
**Đáp án:** Khi đạt core, ThreadPoolExecutor ưu tiên enqueue trước khi tăng workers; queue lớn còn nhận task thì thường không cần tạo worker vượt core.

**Câu 5.** Pool core=max=1, queue capacity=1. Worker đang bận, queue chứa một task, task thứ ba đến: điều gì xảy ra với AbortPolicy?  
**Đáp án:** Task mới bị reject bằng `RejectedExecutionException`. Đây là tình huống trong ví dụ chính.

**Câu 6.** `CallerRunsPolicy` giúp backpressure thế nào?  
**Đáp án:** Khi pool còn hoạt động nhưng bão hòa, task có thể chạy ngay trong thread gọi `execute`, làm caller chậm và giảm tốc submit. Cần lưu ý thread-affinity/context và behavior khi shutdown.

**Câu 7.** `submit` task ném `IllegalStateException`, caller thấy gì ở `future.get()`?  
**Đáp án:** `ExecutionException` với cause là exception của task (trừ khi có cancellation/interrupt khác theo contract).

**Câu 8.** `Future.get(100, MILLISECONDS)` ném `TimeoutException` có chắc task đã ngừng không?  
**Đáp án:** Không. Timeout chỉ kết thúc lời gọi đợi; task có thể vẫn đang chạy.

**Câu 9.** Một task trong single-thread pool submit task thứ hai cùng pool rồi gọi `get`, tại sao nguy hiểm?  
**Đáp án:** Task đầu giữ worker duy nhất và đợi task hai; task hai đang queue, không được chạy nên có thể deadlock.

**Câu 10.** Có thể gọi `Future.get` sau hai task làm `counter++` không synchronization rồi suy tổng sẽ chính xác?  
**Đáp án:** Không. Future.get bảo đảm completion/visibility ở phía caller nhưng không làm phép cập nhật counter giữa workers atomic.

**Câu 11.** `getQueue().size() == 0` chứng minh executor đã xử lý xong tất cả task chưa?  
**Đáp án:** Không; các task đang chạy không nằm trong queue. Dùng Future, termination status và application-level completion.

**Câu 12.** Tại sao không nên dùng `newCachedThreadPool()` không kiểm soát cho nguồn có burst lớn?  
**Đáp án:** Nó có thể tạo nhiều platform threads khi không có worker nhàn rỗi; cần admission/rate limit theo tài nguyên.

**Câu 13.** Khi task có lỗi business, `getCompletedTaskCount()` có phân biệt thành công không?  
**Đáp án:** Không nên coi nó là success counter. Nó chỉ đo hoàn tất ở mức executor; cần business result/error metrics riêng.

**Câu 14.** Khi nhiều tasks độc lập CPU-bound, tăng workers gấp 10 lần số CPU có chắc nhanh hơn không?  
**Đáp án:** Không. Overhead scheduling, cache contention và resource bottleneck có thể giảm hiệu năng; đo thực tế với workload đại diện.

**Câu 15.** Để có bounded task backlog mà task bị reject rõ ràng khi quá tải, nên cấu hình gì?  
**Đáp án:** Một `ThreadPoolExecutor` với giới hạn core/max, work queue có capacity cụ thể và handler như `AbortPolicy`, đồng thời caller xử lý rejection.

## 21. Checklist áp dụng vào code thật

Trước khi đưa một executor vào ứng dụng, xác nhận:

- **Ownership:** component nào tạo pool, ai có quyền submit và ai phải shutdown?
- **Semantics:** task có cần thứ tự, kết quả, deadline, retry hoặc idempotency không?
- **Worker limits:** core/max có hợp lý với CPU và downstream resource không?
- **Queue capacity:** có hard bound thực dụng cho burst và ngân sách bộ nhớ không?
- **Rejection:** task bị reject sẽ báo lỗi, retry, lưu bền hay bỏ theo contract?
- **Completion:** caller có nhận exceptions từ `Future` hoặc kênh lỗi rõ ràng không?
- **Cancellation:** interrupt có được tôn trọng, I/O có timeout và task có cleanup không?
- **Deadlock:** task có chờ task khác trong cùng pool? Producer/consumer có bị kẹt do thiếu worker?
- **Visibility:** dữ liệu được chuẩn bị trước submit đúng, mutable state chia sẻ trong task có synchronization?
- **Monitoring:** queue age, active workers, completed/failures, rejections, latency và CPU có được thu thập?
- **Shutdown:** test khi service kết thúc với task đang chờ/đang chạy và khi nhận interrupt?
- **Version:** class/API mình dùng có sẵn trong JDK triển khai không (đặc biệt các APIs mới từ Java 21+)?

Khi câu trả lời chưa rõ, cấu hình đơn giản nhưng **có bound và báo lỗi rõ** thường dễ điều hành hơn một pool rất lớn không có rejection/timeout.

## 22. Tài liệu tham khảo chính thức

- [Java SE 17 — Executor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executor.html): `execute` và memory-consistency properties.
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): `submit`, `invokeAll`, `invokeAny`, lifecycle.
- [Java SE 17 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html): cấu hình worker, queue, handler, hooks và metrics.
- [Java SE 17 — Executors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executors.html): các factory methods.
- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): `get`, `cancel`, exceptions và memory consistency.
- [Java SE 17 — Callable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Callable.html): hàm trả kết quả.
- [Java SE 17 — BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html): queue, blocking, capacity và publication.
- [Java SE 17 — RejectedExecutionHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RejectedExecutionHandler.html): rejection contract.
- [Java Language Specification `17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): Java Memory Model và happens-before.

**Tổng kết:** `Executor` là hợp đồng “chạy Runnable”; `ExecutorService` thêm kết quả `Future` và lifecycle; `ThreadPoolExecutor` hiện thực pool với **worker limits + work queue + rejection policy**. Để ứng dụng đúng, không chỉ chọn số threads: cần kiểm soát **backlog, loại workload, lỗi, hủy, shutdown, shared state và quan hệ memory visibility**. Một thread pool tốt không phải pool lớn nhất, mà là pool có hành vi rõ ràng khi tải bình thường lẫn khi quá tải.