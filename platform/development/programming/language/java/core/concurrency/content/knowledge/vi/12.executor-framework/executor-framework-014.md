# Phân biệt user task concurrency với thread pool concurrency

Trong Java, **số yêu cầu người dùng còn đang xử lý** (*user task/request concurrency*) và **số tác vụ đang được worker trong một thread pool thực thi** (*thread pool concurrency*) là hai đại lượng **khác nhau**. Một hệ thống có thể có 200 yêu cầu người dùng in-flight nhưng một `ExecutorService` chỉ có 8 worker threads. Ngược lại, một yêu cầu có thể tách thành 20 subtasks rồi submit vào một executor, khiến số task lớn hơn số requests.

Sai lầm “100 concurrent users thì cần pool 100 threads” có thể dẫn tới quá nhiều threads, queue tích tụ, áp lực CPU/memory, tăng latency hoặc nghẽn ở database. Hiểu đúng cần phân biệt **business requests**, **submitted/accepted tasks**, **queued tasks**, **executing tasks**, **worker threads** và **CPU parallelism**. Các khái niệm này liên quan nhưng **không thể thay thế**.

Bài sử dụng Java concurrency nói chung với Java 17+, không phụ thuộc framework hay thành phần concurrency riêng của Spring.

## 1. Định nghĩa user task concurrency

“User task concurrency” không phải tên một thuộc tính chính thức trong `ExecutorService` API. Ở đây nó biểu diễn **số công việc theo nghĩa nghiệp vụ đang tồn tại cùng lúc**, do chương trình quyết định cách đếm.

Một **request/workflow** có thể được tính là in-flight từ khi được chấp nhận tới khi đã phản hồi hoặc hoàn tất công việc cuối cùng, tùy contract. Trong khoảng đó request có thể:

- Đang chạy CPU code.
- Đang đợi queue có worker trống.
- Đang chờ I/O, database, network hoặc một asynchronous result.
- Đang chia ra nhiều tác vụ con rồi chờ tập hợp kết quả.
- Đã timeout ở caller nhưng background job vẫn chạy, nếu ứng dụng chưa hủy được job.
- Trả response sớm và giao việc nền riêng: request đã xong nhưng job nền vẫn in-flight.

**User đang online** không phải **request đang hoạt động**. Một user có thể gửi nhiều requests song song hoặc không gửi request nào. Nhiều users cũng có thể dùng chung một batch job. Nếu hệ thống cần theo dõi “user concurrency”, phải nói rõ **đếm sessions, requests, workflows hay background jobs**.

### Ranh giới in-flight cần nhất quán

Ví dụ một request bắt đầu lúc nhận input, kết thúc khi đã trả response:

```text
Request received
    -> validate
    -> submit task A
    -> queue wait
    -> task A runs
    -> wait result
    -> response sent
Request completed
```

Nếu business workflow tiếp tục sau response, cần metric **background jobs in-flight** riêng. Nếu request tạo subtasks song song, không cộng số subtasks vào số users rồi gọi tất cả là “concurrent users”.

## 2. Định nghĩa thread pool concurrency

`ThreadPoolExecutor` quản lý một tập workers, thực thi `Runnable` hoặc `Callable` đã được chấp nhận. Tại một thời điểm, các tasks có thể:

1. **Accepted**: executor đã nhận, chưa chắc được chạy ngay.
2. **Queued**: đang đợi trong `BlockingQueue<Runnable>` của pool.
3. **Executing**: worker đang chạy `run()`/`call()`.
4. **Completed/failed/cancelled**: trạng thái lifecycle theo contract cụ thể.

Đây là **nhãn để lý giải**, không phải một enum task-state của JDK. Một task cancelled có thể chưa bao giờ bắt đầu; cancellation của `Future` cũng có thể được ghi nhận trước khi worker đã ra khỏi `finally`. Vì vậy phải xác định **thời điểm hoàn thành** rõ ràng khi đo.

Trong fixed pool có 4 platform workers, **tối đa 4 task bodies** thường được thực thi cùng lúc **bởi chính những worker ấy**. Nhưng số task accepted có thể là 1.000 vì 996 tasks đang đợi trong queue. Nếu một worker đang chờ API từ xa, nó vẫn **bị chiếm bởi task** và chưa thể chạy task khác, dù CPU có thể nhàn.

**Cẩn trọng:** `CallerRunsPolicy` hoặc code tự tạo thread ngoài pool có thể khiến task body được thực thi **ngoài worker pool**. Do đó phải phân biệt “tối đa số task bodies trên pool workers” với “tổng số task bodies cùng chạy trên mọi threads trong ứng dụng”.

## 3. Phân biệt concurrency và parallelism

| Khái niệm | Câu hỏi | Điều không nên suy ra |
| --- | --- | --- |
| **Concurrent business requests** | Có bao nhiêu workflow người dùng chưa kết thúc? | Không bằng số Java threads |
| **Outstanding executor tasks** | Có bao nhiêu task đã accepted nhưng chưa hoàn tất? | Không bằng số active workers |
| **Queued tasks** | Bao nhiêu task chưa có worker? | Không phải CPU work đang chạy |
| **Active pool workers** | Worker nào đang thực thi task body? | Không bảo đảm worker đang sử dụng CPU |
| **CPU parallelism** | Bao nhiêu phép tính đang thực sự diễn ra trên các cores? | Không bằng tổng threads hay futures |
| **Asynchrony** | Caller có thể tiếp tục mà chưa đợi kết quả? | Không có nghĩa supplier bên trong không blocking |

Một task có thể đang **executing** nhưng `Thread.sleep`, `Future.get`, `CountDownLatch.await` hoặc chờ I/O. Worker bị giữ nhưng không làm CPU computation. Một `CompletableFuture.supplyAsync` trả Future ngay cho caller, nhưng supplier có thể thực thi synchronous blocking I/O trên worker.

## 4. Bốn con số điển hình trong một pool

Giả sử người gọi submit 6 tasks vào `ThreadPoolExecutor` có đúng 2 workers và queue đủ 4 slots. Hai tasks chạy/chờ trên workers; 4 tasks xếp hàng:

```text
                  Executor (pool of 2)
                       |
submit 6 tasks --------+
                       |
                 +-----+------+
                 |            |
              Worker 1     Worker 2
               Task A       Task B
                 |            |
                 +-----+------+
                       |
             queue: [C, D, E, F]

Accepted tasks  = 6
Executing tasks = 2
Queued tasks    = 4
Workers in pool = 2
```

Nếu **mỗi task đến từ một request riêng**, có thể có 6 requests in-flight. Nếu **một request nộp cả 6 tasks**, chỉ có 1 request, 6 executor tasks và 2 executing workers.

Một phép tính kế toán theo định nghĩa tự thiết kế:

```text
outstanding accepted tasks = accepted tasks - actually completed tasks
roughly: outstanding ≈ queued + executing
```

Trong production, các metric thường là snapshot khác thời điểm, còn cancellation, rejection, task stealing, transfer và caller-runs làm cách đếm thay đổi. Vì vậy đây là **mô hình lý giải**, không phải invariant luôn áp dụng chính xác cho mọi executor getter.

## 5. Java 17: đo 6 accepted, 2 executing, 4 queued

Thay vì dùng `Thread.sleep(100)` để đoán “hai tasks đang chạy”, chương trình dưới dùng `CountDownLatch` chặn hai workers tại checkpoint xác định. Main chụp số liệu **trước** khi mở cổng.

Tạo tệp **`TaskVsPoolConcurrencyDemo.java`**:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class TaskVsPoolConcurrencyDemo {
    public static void main(String[] args) throws Exception {
        CountDownLatch twoStarted = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);
        AtomicInteger executing = new AtomicInteger();
        AtomicInteger completed = new AtomicInteger();

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                2, 2, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(4));

        int accepted = 6;
        try {
            for (int i = 0; i < accepted; i++) {
                pool.execute(() -> {
                    executing.incrementAndGet();
                    twoStarted.countDown();
                    try {
                        release.await();
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                    } finally {
                        executing.decrementAndGet();
                        completed.incrementAndGet();
                    }
                });
            }

            if (!twoStarted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Workers not ready");
            }

            System.out.println("accepted=" + accepted);
            System.out.println("executing=" + executing.get());
            System.out.println("queued=" + pool.getQueue().size());
            System.out.println(
                    "inFlight=" + (accepted - completed.get()));
        } finally {
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
                throw new IllegalStateException("Pool did not stop");
            }
        }
        System.out.println("completed=" + completed.get());
    }
}
```

Biên dịch/chạy JDK 17+:

```bash
javac TaskVsPoolConcurrencyDemo.java
java TaskVsPoolConcurrencyDemo
```

Stdout **khi chương trình hoàn thành bình thường trước timeout**:

```text
accepted=6
executing=2
queued=4
inFlight=6
completed=6
```

**Vì sao có thể dự đoán kết quả?** Hai task đầu làm `executing++`, báo `twoStarted`, rồi chờ `release`. Vì cả hai workers đang chờ latch, bốn task còn lại **không thể được lấy từ queue** trước khi main in số liệu. Main sau đó mở `release` trong `finally`, gọi `shutdown` rồi `awaitTermination`. Chỉ sau khi tất cả sáu tasks hoàn thành, nó in `completed=6`.

Lưu ý rằng `executing=2` ở đây là “hai task bodies đã bắt đầu và chưa kết thúc”; thực tế cả hai đang **WAITING** trên latch, không dùng CPU để xử lý business logic. Các getter giám sát như `getActiveCount()` và `getQueue().size()` có thể là snapshot đổi ngay trong production, nhưng test này cố ý giữ state ổn định để giải thích khái niệm.

Đây là thí nghiệm điều phối, **không phải benchmark throughput**.

## 6. Fan-out: một request có thể sinh nhiều executor tasks

Ví dụ ba requests cùng cần hai tác vụ con:

```text
User request A --> subtask A1 + subtask A2
User request B --> subtask B1 + subtask B2
User request C --> subtask C1 + subtask C2

Business requests = 3
Submitted subtasks = 6
Fixed pool workers = 2
```

Tùy scheduler và thời gian thực thi, chỉ một phần subtasks được worker xử lý ở cùng thời điểm. Nếu requests tạo 10 subtasks mỗi lần và có 500 requests đang in-flight, workload có thể tạo tới 5.000 subtasks outstanding, **không có nghĩa pool có 5.000 threads**.

### Java 17: CompletableFuture fan-out, fan-in

Tạo `FanOutExample.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class FanOutExample {
    public static void main(String[] args) throws Exception {
        int requests = 3;
        int subtasksPerRequest = 2;
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            List<CompletableFuture<Integer>> futures =
                    new ArrayList<>();

            for (int r = 0; r < requests; r++) {
                for (int part = 0; part < subtasksPerRequest; part++) {
                    futures.add(CompletableFuture.supplyAsync(
                            () -> 1, pool));
                }
            }

            CompletableFuture.allOf(
                    futures.toArray(new CompletableFuture<?>[0])
            ).join();

            int sum = futures.stream()
                    .mapToInt(CompletableFuture::join)
                    .sum();

            System.out.println("requests=" + requests);
            System.out.println("subtasks=" + futures.size());
            System.out.println("sum=" + sum);
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
                throw new IllegalStateException("Pool did not stop");
            }
        }
    }
}
```

Chạy:

```bash
javac FanOutExample.java
java FanOutExample
```

Stdout:

```text
requests=3
subtasks=6
sum=6
```

Mỗi subtask trả một `int` bằng 1, và main tổng hợp sau khi `allOf` hoàn thành. `join()` ở đây nằm ở **main**, không ở worker của chính pool đó; các workers vẫn rảnh để chạy các subtasks còn lại. `requests=3` là **số request mô phỏng**, không phải chỉ số đo từ server thật hay khẳng định cả ba cùng chiếm worker.

**Điểm cần nhớ:** `CompletableFuture` mang tính composition/asynchrony, không mặc định supplier không blocking. Nếu supplier gọi HTTP đồng bộ hay `Thread.sleep`, nó vẫn chiếm một worker trong khoảng chờ.

## 7. Cấu hình `ThreadPoolExecutor` quyết định task chạy hay queue

Constructor phổ biến:

```java
new ThreadPoolExecutor(
    corePoolSize,
    maximumPoolSize,
    keepAliveTime,
    TimeUnit.MILLISECONDS,
    workQueue,
    rejectionHandler
);
```

Đây là snippet chưa khai báo biến/nhập số liệu. Với `ThreadPoolExecutor` thông thường:

1. Nếu số worker ít hơn `corePoolSize`, pool có thể tạo worker để chạy task mới.
2. Khi đã có đủ core workers, pool thử **đưa task vào queue**.
3. Nếu queue không nhận thêm và số workers chưa đạt `maximumPoolSize`, pool có thể tạo thêm worker.
4. Nếu cả worker/queue đều không thể nhận, rejection handler được gọi.

Điều này rất quan trọng: **maximumPoolSize không phải số threads chắc chắn sẽ được tạo ngay**. Với **unbounded queue**, sau khi core workers đã có, pool thường xếp hàng, không cần mở rộng tới maximum.

### Factory methods thường gặp

| API | Mô hình | Nguy cơ/giới hạn |
| --- | --- | --- |
| `Executors.newFixedThreadPool(n)` | n platform workers, các task dư thường chờ trong unbounded queue | Queue có thể phình và gây long latency/memory pressure |
| `Executors.newSingleThreadExecutor()` | Chạy tasks tuần tự | Một task chậm làm tất cả đợi |
| `Executors.newCachedThreadPool()` | Tạo thêm workers khi demand tăng, có tái sử dụng | Số threads có thể tăng mạnh nếu không giới hạn admission |
| `Executors.newScheduledThreadPool(n)` | Chạy delayed/periodic tasks | Nhiều scheduled items không đồng nghĩa nhiều workers |
| `ThreadPoolExecutor` custom | Chọn core/max, bounded queue, rejection | Phải quản lý saturation/backpressure rõ |
| `newVirtualThreadPerTaskExecutor()` (Java 21+) | Một virtual thread cho mỗi task | Không có trên Java 17; tài nguyên downstream vẫn hữu hạn |

**Không nên chọn factory chỉ từ tên API**. Cần biết số lượng tasks, thời gian CPU/blocking, mức burst, queue semantics và giới hạn nghiệp vụ.

## 8. Vì sao tăng `maximumPoolSize` có thể không cải thiện latency?

Ví dụ `corePoolSize=4`, `maximumPoolSize=32`, queue capacity rất lớn. Khi có bốn workers, task tiếp theo thường **được queue**. Chỉ khi queue đầy mới có thể kích hoạt tạo workers tới maximum. Vì vậy tăng maximum nhưng để queue không bao giờ đầy có thể không tăng concurrency thực tế.

Ngược lại, cấu hình pool với queue rất nhỏ có thể tạo thêm workers nhanh hơn tới maximum nhưng **tăng tải đồng thời vào downstream**. Nếu DB chỉ cho 10 connections, tạo 100 workers I/O cũng không làm DB xử lý 100 query cùng lúc; các workers còn có thể xếp hàng chờ connection, tốn memory/context switching.

**Pool sizing không phải bài toán một tham số.** Phải xét:

- CPU cores và thời gian compute.
- Thời gian chờ I/O/lock.
- Queue waiting latency.
- Tốc độ submit và burst.
- Connection pool, network, DB rate limit.
- Memory/stack và chi phí quản lý threads.
- Timeout, cancellation, SLA.
- Chính sách khi full: reject, caller-runs, load shedding.

## 9. Khi queue đầy: rejection và backpressure

Một fixed pool hữu hạn không thể nhận vô hạn tasks mà không trả giá. **Backpressure** buộc producer giảm tốc độ, trì hoãn hoặc từ chối công việc khi downstream không đủ khả năng phục vụ.

Một số chiến lược:

- **`AbortPolicy`**: ném `RejectedExecutionException` khi saturation, caller tự xử lý.
- **`CallerRunsPolicy`**: khi phù hợp, task chạy trên thread **đang gọi submit/execute** thay vì pool worker, làm caller chậm lại.
- **`DiscardPolicy`**: bỏ task; nguy hiểm nếu job bắt buộc hoàn tất hoặc có dữ liệu quan trọng.
- **`DiscardOldestPolicy`**: loại task đang chờ lâu nhất rồi thử nhận task mới, có thể phá fairness hoặc mất dữ liệu.
- **Semaphore admission**: giới hạn số requests/jobs in-flight **trước** khi submit vào pool.
- **Bounded queue**: bảo vệ heap khỏi backlog vô hạn và tạo điểm áp dụng policy rõ ràng.

**Quan trọng với CallerRuns:** pool có thể chỉ có 4 workers, nhưng caller **cũng đang chạy một task body**, nên toàn ứng dụng có thể có hơn 4 tasks đang thực thi. Điều này không làm pool tự có worker thứ năm. Nếu caller là event-loop thread không được block, policy này có thể làm hỏng latency toàn hệ thống. Khi executor shutdown, CallerRunsPolicy không có lời hứa luôn thực thi task.

## 10. Java 17: một worker, một queue slot, một task bị từ chối

Tạo **`PoolSaturationExample.java`**:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class PoolSaturationExample {
    public static void main(String[] args) throws Exception {
        CountDownLatch firstStarted = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicInteger completed = new AtomicInteger();

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.AbortPolicy());

        Runnable task = () -> {
            firstStarted.countDown();
            try {
                release.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally {
                completed.incrementAndGet();
            }
        };

        int accepted = 0;
        int rejected = 0;
        try {
            pool.execute(task);
            accepted++;

            if (!firstStarted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker not started");
            }

            pool.execute(task);
            accepted++;

            try {
                pool.execute(task);
                accepted++;
            } catch (RejectedExecutionException expected) {
                rejected++;
            }

            System.out.println("accepted=" + accepted);
            System.out.println("queued=" + pool.getQueue().size());
            System.out.println("rejected=" + rejected);
        } finally {
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
                throw new IllegalStateException("Pool did not stop");
            }
        }
        System.out.println("completed=" + completed.get());
    }
}
```

```bash
javac PoolSaturationExample.java
java PoolSaturationExample
```

Stdout khi chương trình hoàn tất bình thường:

```text
accepted=2
queued=1
rejected=1
completed=2
```

Giải thích: một worker chạy task đầu rồi chờ `release`; task thứ hai nằm trong queue capacity 1. Task thứ ba không còn chỗ nên `AbortPolicy` ném exception. Main chỉ đo queue khi latch chưa mở; sau đó cho hai accepted tasks hoàn tất và đợi executor terminate.

Không có `Thread.sleep` để hy vọng tạo ra saturation; thứ tự được bảo đảm bởi latch. Đây là **thí nghiệm API**, không chứng minh hiệu năng pool trong tải thực.

## 11. User concurrency vượt pool concurrency không nhất thiết là lỗi

Có thể chấp nhận hàng trăm requests outstanding khi:

- Một phần lớn requests chờ kết quả async mà không giữ platform worker.
- Có queue bounded và hạn SLA rõ.
- Downstream đủ sức xử lý ở tốc độ đến trung bình.
- Backpressure/rejection được thiết kế để tránh backlog vô hạn.
- Mỗi request giới hạn fan-out và total in-flight tasks.

Ngược lại, **ít concurrent requests vẫn có thể gây overload** nếu mỗi request tạo hàng trăm subtasks, I/O chậm, retry không giới hạn hoặc tasks giữ nhiều memory. Chỉ đếm số requests không đủ; cần đếm workloads được sinh ra và tài nguyên chúng đang chờ.

### Đơn vị đo phải rõ

“Active=100” là **100 requests** hay **100 executor tasks**, **100 threads**, **100 DB connections**, **100 subscriptions**? Cùng số 100 nhưng thiết kế capacity hoàn toàn khác.

## 12. CPU-bound và I/O-bound

**CPU-bound:** task hầu hết dùng CPU. Thêm quá nhiều workers hơn số core có ích có thể tăng context switches và cache misses, làm throughput giảm. Một pool compute nên được sizing dựa trên core và mức contention, rồi benchmark thực tế.

**I/O-bound:** task chủ yếu chờ network/database/file. Có thể sử dụng nhiều workers hơn số cores vì threads waiting không dùng CPU liên tục. Tuy nhiên giới hạn connection pool, bandwidth và remote API vẫn quyết định concurrency hữu ích. Thêm workers không sửa được downstream đã quá tải.

**Mixed workload:** parsing CPU và gọi I/O dài trong cùng pool có thể gây interference. Nếu cần, tách các stages hoặc executor theo workload, nhưng tổng thread/process và queue vẫn phải được quản lý; không tạo nhiều pool lớn tùy ý.

**Không đồng nhất `Thread.State.RUNNABLE` với “đang dùng CPU”.** Thread có thể runnable mà chưa được scheduler chọn; các trạng thái Java và OS cũng không giống hệt nhau. Dùng profiler/JFR để phân biệt CPU, lock contention và blocking I/O.

## 13. Nested submission: thread-starvation deadlock

Một lỗi đặc biệt khó phát hiện là task A đang chiếm worker của pool, submit task B **vào cùng pool**, rồi chặn bằng `Future.get()` để đợi B. Nếu tất cả workers đều làm như vậy, không còn ai chạy B.

**Snippet sai — không chạy nếu không có timeout:**

```java
ExecutorService pool = Executors.newSingleThreadExecutor();

Future<Integer> outer = pool.submit(() -> {
    Future<Integer> inner = pool.submit(() -> 42);
    return inner.get(); // Worker duy nhất chờ task ở queue!
});

System.out.println(outer.get()); // Có thể đợi mãi.
```

Đây là snippet (cần imports `ExecutorService`, `Executors`, `Future`). Pool một worker chạy outer; inner đã queue nhưng worker đang chờ inner, nên inner không thể chạy. Đây là **thread-starvation deadlock**, không nhất thiết có vòng sở hữu intrinsic monitor.

Cách tránh:

- Nếu công việc nhỏ, gọi trực tiếp logic con thay vì submit và blocking wait.
- Với fan-out, tạo subtasks rồi **join ở coordinator không chiếm worker của chính pool**.
- Dùng asynchronous composition `thenCompose`/`allOf` đúng cách thay cho blocking `get` trong pool worker.
- Nếu sử dụng executor riêng cho phụ thuộc, cần tính toán capacity/lifecycle rõ ràng, không đơn giản nhân đôi pool.
- Thêm timeout và cancellation, nhưng timeout chỉ giúp thoát một tình huống chờ, không tự giải quyết sai cấu trúc.

**`CompletableFuture.supplyAsync(..., samePool).join()` trong worker vẫn có thể gây starvation.** Tên method có chữ Async không khiến `join` thành non-blocking.

## 14. CompletableFuture không có nghĩa non-blocking

`CompletableFuture.supplyAsync(supplier, executor)` làm caller nhận future mà không đợi supplier xong. Nhưng supplier có thể:

- Tính toán CPU nặng.
- Gọi `Thread.sleep`.
- Gọi JDBC hoặc HTTP client đồng bộ.
- Chờ mutex hoặc `Future.get` khác.

Nếu supplier blocking, nó vẫn chiếm executor worker. Khi dùng `thenApply`, `thenApplyAsync`, `thenCompose` và `thenComposeAsync`, cần biết **executor nào chạy stage tiếp theo** và stage nào có thể block. Nếu không chỉ định executor cho một số async method, JDK có thể dùng common pool; vì thế theo dõi resource thực tế không thể chỉ nhìn một pool do ứng dụng tạo.

**Request concurrency** có thể tiếp tục tồn tại trong thời gian future chưa hoàn tất dù caller thread đã trả về. Do đó đếm requests theo lifecycle business và đếm executor tasks theo lifecycle task, không dùng số futures như số users.

## 15. Giới hạn business concurrency riêng với pool

Giả sử business yêu cầu tối đa 100 user requests đang hoạt động và pool chỉ có 12 workers. Có thể dùng **`Semaphore` admission** ở ranh giới request để không nhận nhiều hơn 100, còn pool 12 workers xử lý từng stage.

Snippet synchronous:

```java
if (!requestPermits.tryAcquire()) {
    rejectBusy();
    return;
}

try {
    handleWholeRequest();
} finally {
    requestPermits.release();
}
```

Ở đây `requestPermits` là `Semaphore` và các methods là logic ứng dụng. Nếu `tryAcquire` thất bại, **không release**. Nếu request thực thi qua **asynchronous stages**, phải giữ permit tới **khi workflow cuối cùng hoàn thành**, không release ngay sau `submit` hoặc ngay khi callback khởi động trả về.

Một limiter cho business work **không thay** giới hạn connections tới DB. Có thể cần:

1. Max user requests in-flight.
2. Max outstanding tasks / bounded executor queue.
3. Max concurrent downstream I/O calls.
4. Per-user/tenant quota để tránh một nguồn chiếm toàn bộ tài nguyên.

Đây là bốn lớp admission khác nhau, không phải bốn cách đặt cùng một biến `threadPoolSize`.

## 16. Đo đúng metrics cho requests và executor

| Metric | Tầng | Lưu ý |
| --- | --- | --- |
| `activeRequests` | Business | Đếm từ accept tới response/workflow completion |
| `inFlightJobs` | Business/background | Đếm jobs vẫn chạy sau response nếu có |
| `taskSubmitRate` | Executor | Tasks/s nộp vào pool |
| `acceptedTasks` | Executor | Đã nhận, không chắc đã chạy |
| `rejectedTasks` | Executor | Bị policy từ chối, cần handling |
| `queuedTasks` | Queue | Snapshot backlog chờ worker |
| `activeWorkers` | Executor | Worker đang thực thi task body |
| `poolSize` | Executor | Số workers hiện pool quản lý |
| `largestPoolSize` | Executor | Mức pool size cao nhất đã quan sát |
| `completedTaskCount` | Executor | Số task hoàn thành theo metric pool |
| `queueWaitMs` | Latency | Submit → task body start |
| `taskRunMs` | Latency | Task start → task body complete |
| `requestLatencyMs` | End-to-end | Yêu cầu bắt đầu → phản hồi |
| `blockedTime` | Runtime | I/O/lock/condition wait |
| `CPU load` | Host | CPU có phải nghẽn không |
| `downstreamInFlight` | Resource | Connections/API calls đang sử dụng |

`ThreadPoolExecutor.getActiveCount()`, `getCompletedTaskCount()`, `getTaskCount()` là các số liệu giám sát **ước lượng**, không một transaction snapshot nhất quán. Không ghép chúng trong một phép kiểm soát invariant nghiêm ngặt. Với request accounting, instrument **start/end** theo business ownership và xử lý cả rejection, exception, timeout, cancellation.

### Little's Law hỗ trợ capacity thinking, không cho ra số threads

Trong tải ổn định tương đối:

```text
Average in-flight requests ≈ completion rate × average request duration

Ví dụ:
100 requests/second × 0.2 seconds = 20 requests in-flight (average)
```

Đây là tương quan **số requests trong hệ thống**, không phải khuyến nghị tạo 20 worker threads. Request có thể chờ I/O, tạo subtasks, hoặc không giữ worker trong phần lớn thời gian. Công thức cũng không mô tả chính xác một snapshot khi burst/queue đang tăng không ổn định.

## 17. Timeout, cancellation và task lifecycle

Khi request timeout sau 2 giây, thread đang gọi remote API có thể tiếp tục chạy lâu nếu API không có timeout/cancellation phù hợp. Khi đó:

- Request metric có thể xem request kết thúc.
- Background task vẫn giữ worker và connection.
- Queue có thể tăng mặc dù caller đã từ bỏ kết quả.
- `future.cancel(true)` là **yêu cầu hủy**, không phải cam kết worker dừng ngay.
- Future cancelled có thể được báo trước khi worker ra khỏi `finally` và hoàn tất resource cleanup.

Do đó cần truyền deadline qua các stages, dùng I/O API có timeout, viết cooperative cancellation, finally/try-with-resources và **quan sát task termination** thật. Không dùng `Thread.stop()` để ép dừng; nó có thể phá invariant và gây resource corruption.

Trong metrics, phân biệt **request completed**, **task cancelled**, **worker stopped** và **resource closed** khi điều đó ảnh hưởng correctness.

## 18. Virtual threads thay đổi loại thread, không xóa demand

Từ Java 21 có `Executors.newVirtualThreadPerTaskExecutor()`: thường tạo virtual thread cho mỗi task, **không phải fixed-size platform worker pool**. Nó giúp mô hình nhiều blocking tasks dễ scale hơn trong nhiều trường hợp, nhưng:

- Mỗi request vẫn có thể tạo nhiều virtual tasks.
- Nhiều virtual threads không bằng cùng số OS/carrier threads hoặc cores.
- CPU, heap, file descriptors, DB connections, remote API quotas vẫn hữu hạn.
- Vẫn cần admission limiter/backpressure cho downstream.
- Shared mutable state vẫn phải tuân theo Java Memory Model.
- Không suy ra mọi blocking call đều có chi phí bằng 0; runtime/version JDK khác nhau có thể có hành vi scheduling/pinning riêng.

API virtual threads không có trên Java 17; toàn bộ ví dụ executable trước đó tương thích JDK 17+.

## 19. Tối ưu và kiểm thử tải

Không tăng pool size chỉ vì thấy nhiều requests. Một quy trình có căn cứ:

1. **Định nghĩa** user/request in-flight bắt đầu và kết thúc ở đâu.
2. **Vẽ fan-out**: mỗi request tạo bao nhiêu tasks, có retry/nested waits không.
3. **Phân loại workload**: CPU, I/O, mixed, lock contention.
4. **Đo** arrival rate, request latency, task queue wait, task runtime, rejection.
5. **Quan sát** poolSize, activeCount, queued tasks, completedTaskCount, CPU, heap.
6. **Quan sát downstream**: DB connection pool, API quota, network throughput.
7. **Chọn queue bounded/admission** và rõ cách reject/busy/timeout.
8. **Điều chỉnh** core/max phù hợp hành vi queue và deadline; đừng quên maximum không luôn có tác dụng với unbounded queue.
9. **Load test** nhiều mức concurrent requests, xem p50/p95/p99, queue growth, throughput, starvation/fairness.
10. **Thử shutdown/cancellation**: tasks queued, tasks running và tasks không phản hồi interrupt.
11. **Review nested blocking** để tránh pool starvation.
12. **Kiểm tra memory/resource limits** khi fan-out tăng hoặc chuyển sang virtual threads.

Không nên đặt mục tiêu pool `activeCount` luôn bằng maximum. Pool rảnh khi tải thấp là bình thường. Mục tiêu thực là **latency, correctness, throughput, khả năng phục hồi và giới hạn tài nguyên**.

## 20. Các ngộ nhận phổ biến

| Ngộ nhận | Điều thực tế |
| --- | --- |
| “100 concurrent users cần 100 threads” | User sessions ≠ active requests ≠ worker tasks |
| “Pool 10 threads chỉ nhận được 10 tasks” | Có thể còn nhiều tasks trong queue |
| “`submit` xong nghĩa task đã chạy” | Accepted task có thể queued |
| “Active worker = đang dùng CPU” | Task có thể chờ I/O, lock, latch |
| “Một request luôn tương ứng một task” | Fan-out và retries sinh nhiều subtasks |
| “Nhiều workers luôn tăng throughput” | CPU/downstream có thể bão hòa, thêm threads gây overhead |
| “Tăng `maximumPoolSize` chắc chắn thêm workers” | Pool có thể queue sau khi đạt core |
| “Unbounded queue không reject nên an toàn” | Queue/memory/latency có thể tăng không giới hạn |
| “Async future luôn non-blocking” | Supplier có thể block, `join()` block caller |
| “Nested `Future.get` trong same pool luôn ổn” | Dễ thread-starvation deadlock |
| “CallerRuns không thay đổi execution concurrency” | Task chạy trên caller ngoài pool workers |
| “`isCancelled()` chứng minh worker đã dừng” | Worker có thể vẫn cleanup hoặc block |
| “Virtual threads bỏ giới hạn hệ thống” | Downstream/CPU/memory vẫn hữu hạn |
| “Queue depth snapshot là accounting chính xác tuyệt đối” | Metrics có race và snapshot độc lập |
| “Một user nhiều requests sẽ tự được chia công bằng” | Có thể cần per-user quota/fair queue |

## 21. Câu hỏi tự kiểm tra

**1. Có 500 requests in-flight và pool 8 workers, có mâu thuẫn không?** Không. Requests có thể chờ queue hoặc I/O, một request có thể sinh nhiều tasks.

**2. Một request submit 20 subtasks, có phải 20 users?** Không. Đây là một request tạo 20 executor tasks.

**3. `newFixedThreadPool(4)` nhận 100 tasks thì có 100 tasks chạy body đồng thời trong pool không?** Không. Thường nhiều nhất bốn tasks trên pool workers, các tasks khác đợi queue.

**4. Worker đang ở `CountDownLatch.await` có tính đang executing không?** Nó vẫn chiếm vị trí worker, dù không sử dụng CPU để tính toán.

**5. Tăng `maximumPoolSize` mà queue không đầy có tạo thêm workers ngay không?** Thường không. Sau core, pool ưu tiên queue.

**6. Tại sao `CompletableFuture.supplyAsync` không có nghĩa non-blocking toàn bộ?** Code supplier vẫn có thể gọi blocking API trên executor thread.

**7. Vì sao nested `Future.get` trong pool một worker có thể treo?** Worker chờ subtask ở queue của chính pool, nhưng không có worker rảnh để chạy subtask.

**8. CallerRunsPolicy tạo ra task body ngoài pool worker được không?** Có, trên thread gọi `execute` khi policy áp dụng.

**9. Little's Law ra 20 requests in-flight có buộc pool 20 threads không?** Không. Nó đo requests trung bình trong hệ thống, không phải worker count.

**10. Khi user response timeout, task chạy nền có thể vẫn chiếm worker không?** Có, nếu cancellation không khiến task thực sự dừng.

**11. Virtual-thread-per-task tự giới hạn số DB queries song song không?** Không. Cần giới hạn connection/rate/quota riêng.

**12. Đo chỉ `activeCount` có đủ sizing pool không?** Không. Cần queue waits, request latency, CPU, downstream, fan-out, rejection và demand theo thời gian.

## 22. Checklist cuối cùng

- **Đã xác định user task concurrency là requests, sessions hay jobs chưa?**
- Có đếm request in-flight riêng khỏi executor tasks outstanding không?
- Biết một request tạo bao nhiêu subtasks, futures và retries không?
- Đã phân biệt accepted, queued, executing, completed, rejected chưa?
- Pool đang dùng queue **bounded hay unbounded**? Core/max/rejection hoạt động thế nào?
- Worker đang CPU-bound hay chủ yếu bị blocking?
- Có nested submission tới same pool rồi blocking `get/join` không?
- Có admission limiter cho workflow và limiter cho downstream riêng không?
- Có deadline, cancellation và finally cleanup thực tế không?
- Metrics có ghi đơn vị requests/tasks/threads/cores và đo theo time series không?
- Khi chuyển sang virtual threads, vẫn quản lý resource budgets chứ?
- Load test đã kiểm tra p95/p99, memory, queue growth, rejection và shutdown chưa?

**Kết luận:** **User task concurrency** thể hiện số lượng công việc người dùng đang có nhu cầu xử lý; **thread pool concurrency** thể hiện số task bodies được các workers trong một executor thực thi tại một thời điểm; **CPU parallelism** là mức thực sự chạy trên hardware. Ba đại lượng có quan hệ nhưng không bằng nhau. Muốn hệ thống ổn định, phải đếm đúng business requests và subtasks, hiểu queue/rejection, giới hạn in-flight demand, tránh worker starvation và tuning theo bottleneck thực tế thay vì suy ra số thread từ số users.