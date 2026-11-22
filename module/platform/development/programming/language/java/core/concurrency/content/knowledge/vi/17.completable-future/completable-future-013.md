# Chọn custom executor để quản lý tải và tránh tắc nghẽn trong CompletableFuture

## 1. Tại sao CompletableFuture cần executor được kiểm soát?

`CompletableFuture<T>` mô tả một phép tính bất đồng bộ và các bước xử lý phụ thuộc. Các API như `supplyAsync`, `thenApplyAsync`, `thenComposeAsync`, `thenAcceptAsync` và `thenRunAsync` có thể gửi callback sang một **Executor**. Nhưng bất đồng bộ không làm CPU, thread, kết nối database hay băng thông mạng tăng vô hạn. Nếu nhiều request đến nhanh hơn khả năng xử lý, công việc sẽ **xếp hàng, bị từ chối, hoặc tiêu thụ thêm tài nguyên**.

**Custom executor** là một executor được ứng dụng tạo và cấu hình theo workload thay vì dùng mặc định cho mọi callback. Mục tiêu:

- **Cô lập tải:** task blocking I/O không làm cạn worker dành cho tính toán CPU.
- **Giới hạn tài nguyên:** số worker và lượng công việc chờ phải nằm trong ngân sách hợp lý.
- **Phát hiện quá tải:** khi worker và queue đầy, có chính sách admission/rejection rõ ràng.
- **Tránh phụ thuộc gây tắc nghẽn:** task không giữ worker rồi `join()` công việc chỉ có thể chạy trên cùng worker ấy.
- **Quản lý vòng đời:** ai sở hữu executor, khi nào dừng nhận task, khi nào mọi dependent stage thực sự hoàn tất.

Nội dung chỉ bàn về Java Concurrency chuẩn, không phụ thuộc framework.

## 2. Executor nào thực thi CompletableFuture?

| API | Chính sách thực thi |
|---|---|
| `CompletableFuture.supplyAsync(supplier)` | Gửi theo default async execution facility |
| `CompletableFuture.runAsync(runnable)` | Tương tự với Runnable không trả giá trị |
| `future.thenApply(fn)` | **Non-Async**; callback có thể chạy trên thread hoàn tất stage nguồn hoặc thread khác gọi completion |
| `future.thenApplyAsync(fn)` | Dùng default async executor |
| `future.thenApplyAsync(fn, executor)` | Gửi callback sang executor được chỉ định |
| `future.thenComposeAsync(fn, executor)` | Gửi hàm trả một CompletionStage mới qua executor chỉ định |
| `future.thenAcceptAsync(action, executor)` | Thực thi Consumer qua executor chỉ định |
| `future.thenRunAsync(action, executor)` | Thực thi Runnable qua executor chỉ định |

Với `CompletableFuture` chuẩn, async method không cung cấp executor thường dùng **`ForkJoinPool.commonPool()`**, miễn common pool hỗ trợ parallelism ít nhất hai; nếu không, implementation có thể dùng thread riêng cho các async task. Các subclass có thể tùy chỉnh `defaultExecutor()`, nên không coi một tên pool là bảo đảm xuyên mọi môi trường.

**Common pool là tài nguyên dùng chung trong JVM.** Nếu một thành phần đưa nhiều callback blocking vào đó, các công việc từ phần khác cũng có thể bị ảnh hưởng. Fork/Join work stealing hữu ích cho tính toán chia nhỏ, nhưng không giúp một HTTP/database call đang chờ hoàn tất sớm hơn.

**Non-Async không có nghĩa luôn chạy trong thread gọi đăng ký callback.** Nếu source đã xong, callback có thể thực thi ngay khi đăng ký; nếu source hoàn tất sau, thread hoàn tất source có thể thực thi callback. Một `thenApply` chứa blocking I/O vì thế có thể vô tình giữ worker vừa hoàn thành tác vụ trước.

## 3. Khi nào nên dùng custom executor?

Dùng executor riêng nếu muốn:

1. **Cô lập CPU và blocking I/O**, hoặc tách batch/background task khỏi luồng có SLO nghiêm ngặt.
2. **Đặt bounded queue** và hành vi khi saturated thay vì giữ backlog trong bộ nhớ không giới hạn.
3. **Áp chính sách từ chối** và báo overload chính xác.
4. **Đặt tên worker và quan sát** `activeCount`, queue depth, latency, rejection.
5. **Quản lý lifecycle** theo thành phần và có khả năng shutdown có trật tự.

Đừng tạo executor riêng cho từng Future/request. Mỗi executor tốn tài nguyên và cần shutdown. Thông thường nên **tái sử dụng một số executor theo loại workload và ownership**, không nhân pool vô hạn để che vấn đề tải.

Cũng đừng áp `thenApplyAsync` máy móc cho mọi phép biến đổi vài microsecond: chuyển queue có overhead. Với callback rất ngắn, không blocking, non-Async có thể hợp lý nếu chấp nhận chính sách thread thực thi của nó.

## 4. ThreadPoolExecutor: các thông số quyết định tải

Cấu hình cốt lõi:

~~~java
// MÃ MINH HỌA, các biến phải được định nghĩa trước.
ThreadPoolExecutor pool = new ThreadPoolExecutor(
        corePoolSize,
        maximumPoolSize,
        keepAliveTime,
        TimeUnit.SECONDS,
        workQueue,
        threadFactory,
        rejectedExecutionHandler
);
~~~

| Tham số | Vai trò |
|---|---|
| `corePoolSize` | Số worker lõi mục tiêu |
| `maximumPoolSize` | Giới hạn worker tối đa |
| `keepAliveTime` | Thời gian nhàn rỗi trước khi worker vượt core có thể rút lui |
| `BlockingQueue<Runnable> workQueue` | Lưu task chưa được worker xử lý |
| `ThreadFactory` | Đặt tên/config thread để chẩn đoán |
| `RejectedExecutionHandler` | Phản ứng khi pool saturated hoặc đã shutdown |

Quy tắc tiếp nhận task phổ biến của `ThreadPoolExecutor`:

1. Nếu số worker đang dưới core, pool có thể tạo worker mới.
2. Khi đã có core worker, pool thường ưu tiên **xếp task vào queue**.
3. Nếu queue không nhận được task, pool có thể tăng worker tới maximum.
4. Nếu không thể tạo worker hoặc queue thêm, task bị **reject** theo handler.

Điều này giải thích một bẫy quan trọng: **`maximumPoolSize` có thể hầu như không phát huy tác dụng nếu queue unbounded**. Queue luôn nhận task chờ, nên pool không cần mở rộng ngoài core theo con đường saturated queue.

~~~text
core=2, max=6, queue capacity=10

Ít hơn 2 worker -> có thể thêm worker
Từ 2 worker, queue còn chỗ -> đưa task vào queue
Queue đầy, còn dưới 6 worker -> có thể mở rộng
Queue đầy, đạt 6 worker -> rejection policy
~~~

`Executors.newFixedThreadPool(n)` theo implementation JDK chuẩn dùng `LinkedBlockingQueue` với capacity rất lớn (`Integer.MAX_VALUE`). Tuy cố định số worker n, **không cố định lượng task đang chờ theo một ngân sách vận hành hữu ích**. Nếu tốc độ vào lớn hơn tốc độ xử lý lâu dài, backlog và heap/GC/queue wait vẫn tăng.

## 5. Chọn bounded queue và xử lý quá tải

Một mô hình có giới hạn rõ:

`running ≤ maximumPoolSize`

`queued ≤ queueCapacity`

Nhưng **tổng tải chưa xong** còn có task ở pool khác, retry, timer, request đang đợi permit hoặc future phụ thuộc chưa được schedule. Cần tính toàn tuyến, không chỉ nhìn một queue.

| Rejection policy | Hành vi khi saturated | Rủi ro |
|---|---|---|
| `AbortPolicy` | Ném `RejectedExecutionException` | Caller/boundary phải xử lý lỗi quá tải |
| `CallerRunsPolicy` | Thực thi task bị từ chối trên **thread gọi execute** nếu pool chưa shutdown | Có thể block caller, event-loop, request thread |
| `DiscardPolicy` | Bỏ task bị từ chối | Có thể khiến Future không bao giờ được hoàn tất |
| `DiscardOldestPolicy` | Bỏ task đầu queue rồi thử gửi lại | Mất việc hoặc sai ý nghĩa thứ tự |

**Không lặng lẽ bỏ qua rejection**. Nếu công việc được nhận nhưng không bao giờ chạy, caller đang `join()` có thể chờ mãi. Với pipeline yêu cầu có kết quả rõ ràng, `AbortPolicy` và một boundary xử lý overload thường dễ kiểm chứng hơn chính sách discard.

**CallerRunsPolicy** có thể tạo feedback backpressure: bên gửi phải tự thực thi callback nên không gửi tiếp nhanh như trước. Tuy nhiên khi saturated, callback `thenApplyAsync` có thể **không chạy trên worker của executor**, mà chạy trên thread thực hiện lệnh submit; phải cân nhắc nếu thread này cần phản hồi nhanh.

Khi executor **đã shutdown**, `CallerRunsPolicy` bỏ task thay vì chạy trên caller. Vì thế đây không phải cơ chế đảm bảo mọi dependent Future đều được resolve.

## 6. Phân loại CPU-bound và blocking I/O

**CPU-bound**: callback dành phần lớn thời gian tính toán. Số worker có lợi thường gần CPU hiệu dụng sau khi cân nhắc quota/container, SMT và các pool khác. Tăng worker cao hơn CPU không tự làm tăng throughput; có thể tăng context switch và cache contention.

**Blocking I/O**: callback dành nhiều thời gian đợi HTTP/database/file API đồng bộ. Có thể cần nhiều worker hơn CPU để không để tất cả worker cùng bị chặn. Nhưng trần concurrency của downstream, số connection và memory vẫn áp dụng.

Heuristic tham khảo:

`N_threads ≈ N_CPU × targetCPUUtilization × (1 + waitTime / computeTime)`.

**Chỉ dùng để có điểm đo ban đầu**, không phải công thức đúng mọi hệ thống. Khi downstream cho phép 20 connection, 200 I/O worker không thể làm 200 connection cùng hoạt động an toàn vượt quota đó.

Một pipeline có thể chia:

~~~text
Incoming requests
       |
admission / bounded queue
       |
I/O executor: blocking dependency, timeout
       |
CPU executor: parse/transform/tính toán
       |
result / completion callback
~~~

Việc tách pool **chưa tự tạo backpressure**: producer vẫn có thể submit vô hạn, hoặc các stage ở pool sau có thể bị reject. Phải thiết kế đầy đủ overload ở mỗi boundary.

## 7. Ví dụ Java 17: định tuyến I/O và CPU tới hai executor

Ví dụ dùng hai pool mỗi pool một worker, queue capacity 2 và thread name riêng. Không có I/O thật; dữ liệu giả lập nhằm kiểm chứng API và thread routing.

Lưu file **CustomExecutorRoutingDemo.java**:

~~~java
import java.util.Locale;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class CustomExecutorRoutingDemo {
    private static ThreadPoolExecutor pool(String threadName) {
        return new ThreadPoolExecutor(
                1, 1, 0, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(2),
                task -> new Thread(task, threadName),
                new ThreadPoolExecutor.AbortPolicy());
    }

    public static void main(String[] args) {
        ThreadPoolExecutor io = pool("io-worker");
        ThreadPoolExecutor cpu = pool("cpu-worker");
        AtomicReference<String> ioThread = new AtomicReference<>();
        AtomicReference<String> cpuThread = new AtomicReference<>();

        try {
            CompletableFuture<String> pipeline =
                    CompletableFuture.supplyAsync(() -> {
                        ioThread.set(Thread.currentThread().getName());
                        return "  java  ";
                    }, io).thenApplyAsync(value -> {
                        cpuThread.set(Thread.currentThread().getName());
                        return value.trim().toUpperCase(Locale.ROOT);
                    }, cpu);

            System.out.println("result=" + pipeline.join());
            System.out.println("io thread=" + ioThread.get());
            System.out.println("cpu thread=" + cpuThread.get());
        } finally {
            io.shutdown();
            cpu.shutdown();
        }
    }
}
~~~

Chạy với JDK 17+:

~~~bash
javac CustomExecutorRoutingDemo.java
java CustomExecutorRoutingDemo
~~~

Stdout:

~~~text
result=JAVA
io thread=io-worker
cpu thread=cpu-worker
~~~

`supplyAsync(..., io)` chạy trên `io-worker`; `thenApplyAsync(..., cpu)` chạy trên `cpu-worker`. Main chỉ in sau khi `pipeline.join()`, do đó không phụ thuộc thứ tự lịch của hai worker.

**Không sao chép pool size 1 và queue 2 vào production**: đây là giá trị demo. Trong ứng dụng thật cần benchmark và các policy về deadline, rejection, shutdown, timeout I/O, metric.

## 8. Chọn thenApply hay thenApplyAsync?

Nếu `ioFuture.thenApply(parse)` đăng ký callback non-Async, `parse` có thể chạy ngay trong thread hoàn tất ioFuture. Nếu parsing nặng, callback chiếm worker I/O, khiến task I/O tiếp theo phải chờ.

~~~java
// MÃ MINH HỌA: ioFuture là CompletableFuture<String>
// và cpuExecutor là Executor đã được cấu hình.
CompletableFuture<Result> converted =
        ioFuture.thenApplyAsync(value -> parse(value), cpuExecutor);
~~~

Đoạn trên **không phải chương trình độc lập**; `Result`, `parse`, `ioFuture` và `cpuExecutor` là ký hiệu giả định.

Tuy nhiên, **`thenApplyAsync` không có nghĩa “nhanh hơn”**: nó phát sinh thao tác gửi callback vào executor và có thể bị reject khi saturated. Với phép biến đổi cực ngắn, `thenApply` có thể hiệu quả và đơn giản hơn.

Nếu callback trả về một `CompletionStage<U>` khác, nên dùng `thenCompose`/`thenComposeAsync` để ghép phẳng, tránh tạo `CompletableFuture<CompletableFuture<U>>` từ `thenApply`.

## 9. Ví dụ Java 17: executor reject callback khi quá tải

Ta tạo pool **1 worker và queue capacity 1**. Worker đang chờ latch; một task khác đã chiếm slot queue; callback async thứ ba phải bị từ chối.

**Chi tiết quan trọng của CompletableFuture:** trong JDK 17 với `thenApplyAsync` trên source đã hoàn tất và executor dùng `AbortPolicy`, lời gọi đăng ký **trả một dependent stage đã hoàn tất bất thường**. Vì vậy phải kiểm tra **Future trả về**, không chỉ bắt `RejectedExecutionException` bên ngoài lời gọi `thenApplyAsync`.

Lưu **BoundedRejectionDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class BoundedRejectionDemo {
    public static void main(String[] args) throws Exception {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.AbortPolicy());

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            pool.execute(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                }
            });
            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker did not start");
            }

            pool.execute(() -> { }); // Lấp queue.
            System.out.println("queue full="
                    + (pool.getQueue().remainingCapacity() == 0));

            CompletableFuture<Integer> stage =
                    CompletableFuture.completedFuture(2)
                    .thenApplyAsync(value -> value * 10, pool);
            System.out.println("stage done=" + stage.isDone());
            try {
                stage.join();
            } catch (CompletionException failure) {
                System.out.println("rejection cause="
                        + failure.getCause().getClass().getSimpleName());
            }
        } finally {
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Lệnh chạy:

~~~bash
javac BoundedRejectionDemo.java
java BoundedRejectionDemo
~~~

Stdout với JDK 17:

~~~text
queue full=true
stage done=true
rejection cause=RejectedExecutionException
~~~

**Diễn giải:** `ThreadPoolExecutor.execute` bị `AbortPolicy` từ chối; ở đường hoàn thành dependent của CompletableFuture, lỗi được ghi lên Future của callback. `stage.isDone()` true **không có nghĩa là thành công**, vì `stage.join()` ném `CompletionException` có cause `RejectedExecutionException`.

Trong những tình huống khác, tác vụ bị reject có thể xuất hiện ở caller của API gửi task hoặc trong thread hoàn tất source. Hệ thống nên thiết kế cả **synchronous rejection** và **exceptional completion của Future**, thay vì tin mọi lời gọi luôn ném ở đúng một chỗ.

## 10. Ví dụ Java 17: CallerRunsPolicy có thể chạy callback trên caller

Đổi policy sang `CallerRunsPolicy`. Khi pool saturated, callback thứ ba được chạy ngay trong thread đang gọi execute, ở đây là main. Việc gọi `thenApplyAsync` không đảm bảo luôn thực thi ở worker của pool nếu rejection policy can thiệp.

Lưu **CallerRunsStageDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class CallerRunsStageDemo {
    public static void main(String[] args) throws Exception {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.CallerRunsPolicy());

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicBoolean ranOnCaller = new AtomicBoolean();
        Thread caller = Thread.currentThread();

        try {
            pool.execute(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                }
            });
            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker did not start");
            }

            pool.execute(() -> { }); // Queue đầy.
            CompletableFuture<Integer> stage =
                    CompletableFuture.completedFuture(2)
                    .thenApplyAsync(value -> {
                        ranOnCaller.set(Thread.currentThread() == caller);
                        return value * 10;
                    }, pool);

            System.out.println("ran on caller=" + ranOnCaller.get());
            System.out.println("result=" + stage.join());
        } finally {
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Chạy:

~~~bash
javac CallerRunsStageDemo.java
java CallerRunsStageDemo
~~~

Stdout:

~~~text
ran on caller=true
result=20
~~~

**Cẩn thận:** nếu thread caller là thread phục vụ request, UI hay event loop, một callback CPU/I/O chậm có thể làm giảm responsiveness của chính thread đó. CallerRunsPolicy có thể là backpressure đơn giản cho producer cho phép chậm lại, không phải lựa chọn mặc định mọi nơi.

## 11. Tắc nghẽn do join trong cùng single-thread executor

Một lỗi nguy hiểm: worker duy nhất chạy task A, sau đó **chờ task B chỉ có thể chạy trên cùng executor**.

~~~java
// MINH HỌA SAI; KHÔNG CHẠY: oneWorker là ExecutorService 1 thread.
CompletableFuture<Integer> outer = CompletableFuture.supplyAsync(() -> {
    CompletableFuture<Integer> inner =
            CompletableFuture.supplyAsync(() -> 42, oneWorker);
    return inner.join(); // Giữ worker duy nhất và chờ inner.
}, oneWorker);
~~~

Khi A giữ worker và gọi `join`, B ở queue không thể được chạy; A lại không thoát nếu B chưa hoàn tất. Đây là **thread starvation deadlock**. Tăng queue capacity không sửa được vì không có worker rảnh để lấy B.

Thay vì chặn trong callback, dùng **composition**:

~~~java
// MINH HỌA ĐÚNG: oneWorker đã khai báo và còn hoạt động.
CompletableFuture<Integer> outer =
        CompletableFuture.supplyAsync(() -> 21, oneWorker)
        .thenCompose(value ->
                CompletableFuture.supplyAsync(
                        () -> value * 2, oneWorker));
~~~

`thenCompose` thiết lập dependency bất đồng bộ mà không cần `join()` ngay trong worker trước. Main hoặc tầng boundary có thể đợi kết quả cuối cùng khi cần.

### Ví dụ Java 17: compose thay vì giữ worker

Lưu **SingleWorkerCompositionDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class SingleWorkerCompositionDemo {
    public static void main(String[] args) {
        ExecutorService oneWorker = Executors.newSingleThreadExecutor();

        try {
            CompletableFuture<Integer> result =
                    CompletableFuture.supplyAsync(() -> 21, oneWorker)
                    .thenCompose(value ->
                            CompletableFuture.supplyAsync(
                                    () -> value * 2, oneWorker));

            System.out.println("result=" + result.join());
            System.out.println("done=" + result.isDone());
        } finally {
            oneWorker.shutdown();
        }
    }
}
~~~

Chạy:

~~~bash
javac SingleWorkerCompositionDemo.java
java SingleWorkerCompositionDemo
~~~

Stdout:

~~~text
result=42
done=true
~~~

**Không có `join()` trong stage callback**; thread worker sau khi tính 21 có thể tiếp tục chạy công việc con đã được tạo. Main chờ ở boundary, không chiếm worker của pool. Điều này tránh được dependency deadlock cụ thể vừa phân tích nhưng không ngăn mọi lock hoặc I/O deadlock khác.

## 12. Các kiểu tắc nghẽn vẫn xảy ra khi có nhiều pool

Tách thành ioPool và cpuPool chưa đủ nếu:

- ioPool workers đồng loạt `join()` task ở cpuPool, trong khi cpuPool workers lại `join()` task cần ioPool;
- task giữ một lock/permit rồi chờ callback cần cùng tài nguyên;
- task A và B lấy khóa theo thứ tự A→B và B→A;
- task đang chạy chặn worker, còn task dùng để phát completion signal đứng sau trong queue;
- CallerRunsPolicy khiến callback chạy trong thread đang giữ lock hoặc phụ trách sự kiện quan trọng.

Giải pháp không phải “cứ thêm thread”, mà là **vẽ dependency graph**, tránh chu trình chờ đồng bộ, dùng `thenCompose`/`thenCombine`/`allOf` đúng ngữ nghĩa, và đặt deadline nếu có blocking bắt buộc.

**Không gọi `get()` hoặc `join()` trong mỗi stage chỉ để “chắc đã xong”.** Các phương thức này có thể block worker và triệt tiêu ý nghĩa của composition. Nếu cần đồng bộ với caller truyền thống, thường chỉ đợi ở boundary phù hợp.

## 13. Quản lý backpressure từ upstream

Custom executor với bounded queue tạo **điểm phát hiện saturated**, nhưng backpressure yêu cầu upstream **thay đổi hành vi**. Các lựa chọn:

- **Fail-fast:** báo không nhận task và trả trạng thái overload rõ ràng.
- **Chờ có hạn:** đợi capacity theo deadline tổng nếu API admission hỗ trợ; không chặn thread quan trọng vô thời hạn.
- **CallerRuns:** làm chậm producer bằng cách thực thi ngay, chỉ khi thread gửi được phép chịu tải.
- **Drop/coalesce có chủ đích:** phù hợp metric hoặc bản cập nhật không quan trọng, **không** tùy tiện bỏ công việc giao dịch.
- **Lưu bền vững:** nếu công việc phải tồn tại sau restart, cần cơ chế lưu durable riêng; queue của ThreadPoolExecutor chỉ nằm trong bộ nhớ.

Đừng retry vô hạn ngay khi executor từ chối: retry storm tăng tải đúng lúc hệ thống đã đầy. Cần retry budget, backoff có jitter khi phù hợp và đảm bảo idempotency cho side effect.

Nếu queue lớn nhưng không có rejection, độ trễ chờ tăng trước khi thấy lỗi. Vì vậy đo cả **queue wait**, **end-to-end latency** và throughput, không chỉ success rate.

## 14. Downstream concurrency và timeout

Giới hạn executor chưa chắc giới hạn hết số outbound request: callback có thể khởi tạo các async I/O call khác rồi thoát ngay, khiến số request đang xử lý downstream cao hơn số worker.

Một `Semaphore` ở boundary của tài nguyên hữu hạn hoặc connection pool có concurrency limit thích hợp sẽ quản lý **số request in-flight** độc lập với số worker/queue. Cần release permit đúng một lần sau khi công việc thực sự hoàn tất, kể cả khi Future exceptional.

**`CompletableFuture.orTimeout` không dừng bảo đảm task nền.** Nó có thể làm Future hoàn tất bằng `TimeoutException` mà công việc blocking vẫn tiếp tục. Tương tự `cancel(true)` của CompletableFuture không dùng boolean đó để ép interrupt worker. Cần áp timeout ở tầng HTTP/database, deadline tổng và cancellation hợp tác khi dependency hỗ trợ.

Trong Java 21+, virtual threads giúp giảm chi phí quản lý nhiều tác vụ blocking trong một số workload, nhưng **không làm CPU, kết nối database hay quota tăng lên**. Dù dùng virtual-thread-per-task executor, vẫn cần giới hạn in-flight/downstream. Các ví dụ ở đây được giữ tương thích JDK 17.

## 15. Cách chọn kích thước pool và queue

Không có công thức đúng cho mọi bài toán. Quy trình thực tế:

1. **Đo workload**: CPU time, thời gian chờ I/O, latency downstream, throughput và số request cùng lúc.
2. **Giới hạn theo downstream**: connection count, API rate/in-flight quota và memory có thể thấp hơn số thread mong muốn.
3. **Chọn CPU pool** quanh CPU hiệu dụng, chạy benchmark với nhiều kích thước.
4. **Chọn blocking I/O pool** dựa trên tỷ lệ chờ/tính và ceiling downstream; không nhân worker vô hạn.
5. **Chọn queue capacity** theo khả năng hấp thụ burst và latency budget, không chỉ theo heap rảnh.
6. **Chọn rejection policy** có quan sát phù hợp nghiệp vụ và một nơi chịu trách nhiệm xử lý lỗi.
7. **Load test khi saturated**, ghi p50/p95/p99 queue wait, end-to-end latency, CPU, GC, rejection và tốc độ phục hồi.
8. **Thử shutdown** trong lúc stage nguồn còn pending và callback async chưa được submit.

Heuristic cho blocking I/O trong vài mô hình:

`threads ≈ CPUs × targetCPUUtilization × (1 + waitTime/computeTime)`.

Đó là điểm bắt đầu cần đo, không phải mặc định sản xuất.

Trong trạng thái ổn định, Little's Law với queue được xác định rõ:

`L = λ × W`

L: số task **đang chờ trung bình**, λ: throughput của queue, W: thời gian chờ queue trung bình. Nó không bảo đảm P99 hoặc tự tính được capacity phù hợp trong giai đoạn overload không ổn định.

### Metric nên theo dõi

| Nhóm | Ví dụ |
|---|---|
| Worker | `getActiveCount()`, `getPoolSize()`, completed task count |
| Queue | queue size, remaining capacity, tuổi task chờ |
| Admission | tỷ lệ reject, timeout, retry, drop |
| Latency | queue wait, callback duration, end-to-end p95/p99 |
| Downstream | số in-flight, connection saturation, I/O timeout |
| Liveness | worker bị block trong `join/get`, lock contention, pending stages |
| Shutdown | số pipeline chưa hoàn tất, executor terminated, escalation count |

`size()`, `remainingCapacity()` hay active count thường là snapshot/xấp xỉ phục vụ monitoring, **không phải phép đặt chỗ nguyên tử**. Không đọc queue còn chỗ rồi giả định submit tiếp chắc chắn thành công.

## 16. Lifecycle và shutdown đúng

Một executor phải có owner rõ ràng. Nếu nhiều thành phần cùng dùng chung một executor, thành phần không sở hữu **không được tự shutdown** vì có thể làm task của bên khác bị từ chối.

Quy trình dừng:

1. **Ngừng admission** của root request/task mới.
2. Theo dõi các pipeline còn sống, kể cả callback `thenApplyAsync` **chưa được schedule** vì stage nguồn còn pending.
3. Hoàn thành/hủy có chủ đích những pipeline cần xử lý, tránh shutdown executor trước khi dependent callbacks được submit.
4. Gọi `shutdown()`: từ chối task mới và cho task đã nhận chạy tiếp theo hợp đồng; shutdown **không chờ**.
5. Gọi `awaitTermination(timeout, unit)` ở thread điều phối bên ngoài worker đang phải thoát.
6. Khi quá hạn, cân nhắc `shutdownNow()`, tiếp tục chờ có hạn, ghi nhận trường hợp chưa dừng. Interruption **không phải kill bắt buộc**.
7. Chỉ đóng connection/client/tài nguyên phụ thuộc khi không còn task đang dùng, hoặc có cleanup policy an toàn.

**Bẫy quan trọng với CompletableFuture:** callback async có thể mới **được đăng ký**, chưa được gửi vào executor. Nếu executor shutdown trong khoảng đó, callback phụ thuộc có thể thất bại khi nguồn hoàn tất sau. Theo dõi **toàn bộ chain** chứ không chỉ Future của source.

Nếu `awaitTermination` ném `InterruptedException`, thông thường truyền tiếp hoặc khôi phục interrupt flag nếu đã bắt để xử lý tại chỗ; không nuốt rồi tiếp tục đợi vô hạn.

## 17. Những lỗi phổ biến

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Cho mọi callback blocking dùng common pool | Tranh worker dùng chung, giảm throughput | Pool riêng cho I/O và giới hạn downstream |
| `thenApply` thực hiện blocking I/O dài | Có thể giữ thread hoàn tất source | Dùng async stage/executor phù hợp |
| `newFixedThreadPool` rồi nghĩ queue bounded | Backlog tăng không kiểm soát | Dùng bounded `ThreadPoolExecutor` |
| Tăng max pool nhưng vẫn dùng queue unbounded | Pool có thể không mở rộng như kỳ vọng | Thiết kế lại queue và sizing |
| Không quan sát Future từ callback async bị reject | Pipeline mất kết quả hoặc lỗi không ai xử lý | Bắt overload ở boundary và xử lý exceptional stage |
| Bắt lỗi chỉ ở `thenApplyAsync` lúc đăng ký | Có trường hợp Future trả về đã exceptional | Giữ Future và xử lý `join/get/whenComplete` |
| Dùng DiscardPolicy với task cần completion | Future có thể chờ mãi | Không silent drop công việc có người đợi |
| Dùng CallerRunsPolicy trên thread nhạy latency | Callback dài block chính caller | Xác định chính sách quá tải theo loại thread |
| Worker duy nhất `join()` task của cùng pool | Thread starvation deadlock | Dùng `thenCompose` hoặc tách dependency |
| Tin TimeoutException nghĩa tác vụ nền đã dừng | Vẫn có thể chiếm resource và tạo side effect | Timeout I/O, cancellation hợp tác |
| Tạo pool mới cho mỗi request | Tốn thread, khó shutdown | Pool được tái sử dụng theo workload |
| Shutdown executor trước khi chain hoàn tất | Dependent async stage có thể bị từ chối | Quản lý ownership và toàn bộ pipeline |
| Dùng queue depth làm phép admission nguyên tử | Race giữa kiểm tra và submit | Để executor xử lý admission/rejection |

## 18. Checklist và kết luận

Trước khi triển khai, trả lời:

1. Callback này CPU-bound, blocking I/O hay thao tác ngắn non-blocking?
2. Có cần `Async` hay có thể dùng non-Async an toàn?
3. Pool nào sở hữu work queue; core/max/queue capacity cụ thể là bao nhiêu?
4. Khi pool đầy, công việc sẽ reject, chờ, caller-runs, drop hay lưu bền vững?
5. Caller có nhận được cả **exception trong Future** và **exception khi submit** không?
6. Có stage nào giữ worker rồi `join/get` task cần chính worker đó không?
7. Có giới hạn downstream in-flight, timeout, deadline và retry budget?
8. Có theo dõi source và dependent stages trước khi shutdown executor không?
9. Đã load test saturation, rejection, callback failure, timeout và shutdown chưa?
10. Có metric queue wait, active worker, rejection và p95/p99 latency để điều chỉnh?

**Kết luận:** chọn custom executor cho `CompletableFuture` là xác định **ranh giới tài nguyên, cơ chế admission, queue và liveness**, không chỉ chọn tên thread. Tách CPU/I/O khi cần, dùng bounded queue và rejection policy có thể quan sát, tránh blocking `join` trong worker phụ thuộc vào chính pool đó, và quản lý trọn đời các dependent stages.

## 19. Tài liệu Java SE

- [CompletableFuture – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [ThreadPoolExecutor – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [ExecutorService – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
