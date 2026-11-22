# thenApplyAsync() và ý nghĩa của Executor trong CompletableFuture

> **Ý chính:** `CompletableFuture.thenApplyAsync(fn)` tạo **một dependent stage** áp dụng hàm chuyển đổi khi stage trước **hoàn thành bình thường**; hàm được lên lịch qua **default asynchronous execution facility**, thường là `ForkJoinPool.commonPool()` trong Java 17. `thenApplyAsync(fn, executor)` dùng **Executor được chỉ định** để chạy hàm chuyển đổi. Ngược lại, `thenApply(fn)` không yêu cầu một async scheduling boundary: callback có thể thực thi trong thread hoàn tất stage trước hoặc thread gọi đăng ký khi stage đã hoàn tất. Từ `Async` mô tả **cách điều phối callback**, không cam kết callback là non-blocking, chạy song song, nhanh hơn hoặc không thể bị từ chối.

Bài thuộc nhóm **CompletableFuture** của **Java concurrency nói chung**, dùng Java SE 17+, không bàn đến Spring. Nội dung tập trung vào ý nghĩa của executor ở mỗi stage, timing, thread context, lỗi/rejection, phụ thuộc dữ liệu, lựa chọn pool, cancellation và vận hành.

## 1. Bối cảnh: CompletableFuture là một chuỗi các giai đoạn

`CompletableFuture<T>` là một abstraction cho một kết quả có thể đến sau, đồng thời là `CompletionStage<T>`. Một pipeline có thể gồm nhiều giai đoạn:

~~~text
Source stage
 CompletableFuture<Integer>
           |
           | when completed normally
           v
 thenApplyAsync(Integer -> String, Executor)
           |
           v
 CompletableFuture<String>
           |
           | when completed normally
           v
 thenApply(String -> Integer)
           |
           v
 CompletableFuture<Integer>
~~~

Mỗi lời gọi tạo một **stage mới**. Nó không sửa kiểu kết quả của stage gốc, không biến một callback đã thất bại thành thành công và không tự tạo thêm CPU. Điều kiện để callback `thenApplyAsync` được gọi là stage đầu vào đã **completed normally**; nếu stage đầu vào exceptional/cancelled, callback chuyển đổi thông thường **không chạy**, và stage phụ thuộc sẽ kết thúc exceptional theo chuỗi.

Một ví dụ tối giản:

~~~java
// Snippet API: dùng trong method có import CompletableFuture.
CompletableFuture<Integer> source =
        CompletableFuture.completedFuture(21);

CompletableFuture<String> result =
        source.thenApplyAsync(n -> "value=" + (n * 2));
~~~

`result` có kiểu `CompletableFuture<String>`; `source` vẫn là `CompletableFuture<Integer>`. Dù `source` đã hoàn tất, `thenApplyAsync` không phải synonym của `thenApply`: callback có thể được submit sang executor thay vì thực hiện ngay ở caller.

### Ba câu hỏi phải tách bạch

1. **Khi nào callback đủ điều kiện chạy?** Khi source stage hoàn tất bình thường.
2. **Callback chạy ở đâu?** Phụ thuộc dạng non-async/async và executor.
3. **Callback thực sự chạy xong khi nào?** Phụ thuộc queueing, số worker, workload, lỗi và cancellation; không có hard deadline tự động.

Nói “sau `thenApplyAsync` thì program tiếp tục ngay” cũng thiếu chính xác: phương thức *thường* trả nhanh sau khi đăng ký/submit dependent stage, nhưng executor/custom rejection/callback trực tiếp và các thao tác nối chuỗi có thể gây exception hoặc overhead. Muốn biết **giá trị đã được tính xong**, phải quan sát/chờ Future tương ứng.

## 2. So sánh thenApply, thenApplyAsync và thenApplyAsync với executor

| Method | Khi nào callback được gọi? | Nơi callback có thể thực thi | Cần chú ý |
| --- | --- | --- | --- |
| `thenApply(fn)` | Sau khi stage trước completed normally | Thread hoàn tất stage trước, hoặc thread tham gia completion/registration theo timing | Không cam kết có thread riêng, không có async scheduling boundary |
| `thenApplyAsync(fn)` | Sau khi stage trước completed normally | Default asynchronous execution facility, thường `commonPool()` | Các call sites có thể tranh common pool; ngoại lệ parallelism thấp |
| `thenApplyAsync(fn, executor)` | Sau khi stage trước completed normally | Theo `executor.execute(...)` được chỉ định | Có thể queue, reject, chậm vì bận; cần lifecycle ownership |

**Cả ba** đều thực hiện **mapping `T -> U`** và trả `CompletableFuture<U>`; không trả trực tiếp `U`. Sự khác nhau chủ yếu ở **quy tắc thực thi callback**, không phải toán học của hàm biến đổi.

### Thế nào là “không có executor” trong API?

Không phải callback chạy trong khoảng không. Khi gọi `thenApplyAsync(fn)`, implementation lựa chọn một **default asynchronous execution facility**. Trong JDK 17, default thường là `ForkJoinPool.commonPool()`; Javadoc `CompletableFuture` có ngoại lệ: nếu common pool không hỗ trợ **parallelism ít nhất 2**, một Thread mới có thể được tạo cho từng async task.

Vì vậy câu “`thenApplyAsync` luôn dùng chung một worker cụ thể” là **sai**. Không viết test bắt buộc tên thread phải có tiền tố `ForkJoinPool.commonPool-worker` hoặc đòi chỉ số worker cố định.

### Async không nghĩa là callback được thực hiện ngay

Đăng ký async action trước khi source hoàn tất:

~~~text
Thread A: source.thenApplyAsync(fn, executor) --> returned dependent stage
                    |
                    | source chưa completed
                    v
         callback chưa được phép chạy
                    |
Thread B: source.complete(value)
                    |
                    v
       executor được yêu cầu chạy fn
                    |
                queue/wait
                    |
             worker chạy fn
                    |
             dependent completed
~~~

Stage đã đăng ký có thể chờ **source** rồi chờ **executor**, nghĩa là có **hai loại thời gian đợi** cần đo riêng khi một pipeline chậm.

## 3. Ví dụ 1 — thấy rõ thread hoàn tất source và executor của callback

Dùng hai single-thread executors có tên thread rõ ràng. Source ban đầu **chưa completed**, callbacks được đăng ký trước. Một worker `source-worker` gọi `complete(21)`; `thenApply` chạy đồng bộ trên completion path, `thenApplyAsync(..., stageExecutor)` được submit sang `stage-worker`.

Tạo `ThenApplyVsAsync.java` (Java 17+):

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class ThenApplyVsAsync {
    public static void main(String[] args) throws Exception {
        ExecutorService sourceExecutor =
                Executors.newSingleThreadExecutor(
                        r -> new Thread(r, "source-worker"));
        ExecutorService stageExecutor =
                Executors.newSingleThreadExecutor(
                        r -> new Thread(r, "stage-worker"));

        try {
            CompletableFuture<Integer> source =
                    new CompletableFuture<>();

            CompletableFuture<String> inline =
                    source.thenApply(v ->
                            Thread.currentThread().getName() + ":" + v);

            CompletableFuture<String> async =
                    source.thenApplyAsync(v ->
                            Thread.currentThread().getName() + ":" + v,
                            stageExecutor);

            sourceExecutor.execute(() -> source.complete(21));

            System.out.println("thenApply = " + inline.join());
            System.out.println("thenApplyAsync = " + async.join());
        } finally {
            sourceExecutor.shutdown();
            stageExecutor.shutdown();

            if (!sourceExecutor.awaitTermination(10, TimeUnit.SECONDS)) {
                sourceExecutor.shutdownNow();
            }
            if (!stageExecutor.awaitTermination(10, TimeUnit.SECONDS)) {
                stageExecutor.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac ThenApplyVsAsync.java
java ThenApplyVsAsync
~~~

Stdout bình thường với JDK 17:

~~~text
thenApply = source-worker:21
thenApplyAsync = stage-worker:21
~~~

Đây là một **thí nghiệm có kiểm soát**: chỉ `source-worker` complete source; `thenApply` được đăng ký khi source chưa complete, nên non-async continuation chạy trên completion path. Executor của async continuation có một worker tên `stage-worker`, nên kết quả xác định, bất kể thread nào được CPU trước.

**Không suy rộng:** `thenApply` **luôn** chạy trên source worker trong mọi chương trình. Nếu source đã completed **trước** khi gọi `thenApply`, callback có thể được chạy **ngay trên thread đăng ký**; các completion interactions khác cũng ảnh hưởng nơi chạy. `thenApplyAsync(fn, executor)` mới là cách chọn execution facility minh bạch cho callback.

## 4. Source đã completed trước khi đăng ký: khác biệt vẫn tồn tại

Một stage có thể đã completed trước khi dependent method được gọi. Ví dụ `CompletableFuture.completedFuture(5)` là stage đã có giá trị.

- `thenApply(fn)` có thể tính mapping ngay khi đăng ký; trong implementation JDK 17 thông thường callback chạy ở thread gọi phương thức.
- `thenApplyAsync(fn, executor)` vẫn lên lịch callback thông qua executor, thay vì bắt caller thực thi mapping trực tiếp.
- Không nên dùng `isDone()` ngay sau khi tạo async stage để khẳng định callback đã hoặc chưa xong: worker có thể đã chạy trước khi main kiểm tra. Muốn xác minh completion, dùng `join()`/`get()` hoặc một signal riêng.
- Đừng đo khoảng thời gian giữa lời gọi và `join()` một lần rồi kết luận async luôn nhanh hơn.

### Ví dụ 2 — completed source, callback chạy ở caller hay worker riêng

Tạo `CompletedStageExecutor.java` (Java 17+):

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class CompletedStageExecutor {
    public static void main(String[] args) throws InterruptedException {
        Thread caller = Thread.currentThread();
        ExecutorService executor = Executors.newSingleThreadExecutor();

        try {
            CompletableFuture<Integer> done =
                    CompletableFuture.completedFuture(5);

            CompletableFuture<Boolean> plain = done.thenApply(
                    value -> Thread.currentThread() == caller);

            CompletableFuture<Boolean> async = done.thenApplyAsync(
                    value -> Thread.currentThread() != caller, executor);

            System.out.println("plain on caller = " + plain.join());
            System.out.println("async on executor worker = " + async.join());
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Chạy:

~~~bash
javac CompletedStageExecutor.java
java CompletedStageExecutor
~~~

Stdout trên JDK 17 thông thường:

~~~text
plain on caller = true
async on executor worker = true
~~~

Đây là cách thể hiện **không phụ thuộc tên OS thread**. Lời gọi non-async trên một `completedFuture` đã hoàn thành trước khi đăng ký có thể thực hiện ngay trên caller; lời gọi async sử dụng thread từ `ExecutorService` riêng. Đừng biến kết quả của ví dụ thành hợp đồng tất cả `thenApply` chạy ở caller — khi source còn pending thì thread hoàn tất có thể chạy mapping.

## 5. Executor không phải dữ liệu: nó là chính sách thực thi

Interface `Executor` chỉ có hợp đồng nền tảng:

~~~java
public interface Executor {
    void execute(Runnable command);
}
~~~

Một `Executor` nhận command để thực thi theo cơ chế của nó. Có các lựa chọn rất khác nhau:

- Executor chạy mỗi command ngay trong caller (direct executor).
- Executor dùng một worker thread, thực thi tuần tự.
- Executor dùng nhiều worker và queue.
- Executor giới hạn queue, có thể ném `RejectedExecutionException` khi quá tải.
- Executor ưu tiên/sắp lịch theo chính sách riêng; có thể delay hoặc sắp thứ tự.
- Một executor đã shutdown không còn chấp nhận task mới.

**Executor không tự cam kết task chạy trên thread khác**. Ví dụ:

~~~java
// Snippet: direct Executor hợp lệ, chạy command đồng bộ ở caller.
Executor direct = Runnable::run;
CompletableFuture<Integer> f =
        CompletableFuture.completedFuture(1)
                .thenApplyAsync(x -> x + 1, direct);
~~~

Dù method có hậu tố `Async`, direct executor gọi `Runnable.run()` ngay, nên mapping có thể chạy đồng bộ trong thread gọi method. Vì vậy “Async = chắc chắn non-blocking/đổi thread” là một hiểu nhầm nghiêm trọng.

### Chọn `Executor` hay `ExecutorService`?

`Executor` đủ để truyền một chính sách thực thi vào `thenApplyAsync`. `ExecutorService` mở rộng thêm `submit`, `shutdown`, `awaitTermination`, v.v. Trong thực tế, nhiều executor ta truyền là `ExecutorService`, nhưng signature của `thenApplyAsync` nhận **`Executor`**. Nếu code sở hữu một `ExecutorService`, code đó chịu trách nhiệm đóng và dọn tài nguyên. Không tự gọi `shutdown` một executor dùng chung do framework/library/module khác quản lý.

## 6. Ví dụ 3 — direct Executor không tạo async thread mới

Tạo `DirectExecutorDemo.java` (Java 17+):

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;

public class DirectExecutorDemo {
    public static void main(String[] args) {
        Thread caller = Thread.currentThread();
        Executor direct = Runnable::run;

        CompletableFuture<Boolean> stage =
                CompletableFuture.completedFuture(7)
                        .thenApplyAsync(value ->
                                Thread.currentThread() == caller,
                                direct);

        System.out.println("mapped value = " + stage.join());
        System.out.println("stage done = " + stage.isDone());
    }
}
~~~

Chạy:

~~~bash
javac DirectExecutorDemo.java
java DirectExecutorDemo
~~~

Stdout:

~~~text
mapped value = true
stage done = true
~~~

Một direct executor đáp ứng API, nhưng **không tạo ranh giới thread**. Nó có thể phù hợp cho test hoặc những trường hợp muốn chạy inline; trong production, hãy đọc hợp đồng của executor thực tế trước khi kết luận “Async” cô lập latency khỏi caller.

Lưu ý với callback có recursion hoặc nested completions: direct executor có thể đẩy nhiều công việc vào chính call stack hoặc completion path, làm thay đổi latency/reentrancy; không nên dùng như cách mặc định để tránh mọi overhead của thread pool.

## 7. Ý nghĩa của thenApplyAsync trong một chuỗi stage

Mỗi lần gọi `thenApplyAsync(fn, executor)` tạo một dependent stage và yêu cầu **executor tương ứng cho chính callback ấy**. Nó **không đặt một thuộc tính “executor hiện tại” vĩnh viễn** cho tất cả stages phía sau.

Ví dụ:

~~~java
// Snippet API, các biến/source được tạo nơi khác.
CompletableFuture<String> result =
        source
            .thenApplyAsync(this::parse, cpuExecutor)
            .thenApplyAsync(this::render, renderExecutor)
            .thenApply(this::format);
~~~

- `parse` được điều phối qua `cpuExecutor`.
- `render` được điều phối qua `renderExecutor`.
- `format` không có async executor được chỉ định; nó có thể chạy trên completion path của stage `render`.
- Nếu stage sau gọi `thenApplyAsync(this::more)` không có executor, nó trở lại **default asynchronous facility** của implementation, không mặc nhiên “thừa hưởng” `renderExecutor`.

**Điểm cần nhớ:** Executor là một **tham số của từng async dependent method**, không phải context tự động lan qua pipeline.

### Ví dụ 4 — pipeline luân chuyển qua hai executor riêng

Tạo `ExecutorHandoffChain.java` (Java 17+):

~~~java
import java.util.Queue;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class ExecutorHandoffChain {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService poolA = Executors.newSingleThreadExecutor(
                r -> new Thread(r, "pool-A"));
        ExecutorService poolB = Executors.newSingleThreadExecutor(
                r -> new Thread(r, "pool-B"));
        Queue<String> contexts = new ConcurrentLinkedQueue<>();

        try {
            CompletableFuture<Integer> result =
                    CompletableFuture.supplyAsync(() -> {
                        contexts.offer(Thread.currentThread().getName());
                        return 20;
                    }, poolA)
                    .thenApplyAsync(value -> {
                        contexts.offer(Thread.currentThread().getName());
                        return value + 1;
                    }, poolB)
                    .thenApplyAsync(value -> {
                        contexts.offer(Thread.currentThread().getName());
                        return value * 2;
                    }, poolA);

            System.out.println("result = " + result.join());
            System.out.println("contexts = " + contexts);
        } finally {
            poolA.shutdown();
            poolB.shutdown();
            if (!poolA.awaitTermination(10, TimeUnit.SECONDS)) {
                poolA.shutdownNow();
            }
            if (!poolB.awaitTermination(10, TimeUnit.SECONDS)) {
                poolB.shutdownNow();
            }
        }
    }
}
~~~

Chạy:

~~~bash
javac ExecutorHandoffChain.java
java ExecutorHandoffChain
~~~

Stdout:

~~~text
result = 42
contexts = [pool-A, pool-B, pool-A]
~~~

Stage 2 phụ thuộc stage 1, stage 3 phụ thuộc stage 2, nên ba lần ghi context xảy ra theo thứ tự logic dù thread có thể đổi. `ConcurrentLinkedQueue` đảm bảo việc thêm từ các threads được quản lý an toàn; `join` trên final stage đợi hoàn tất toàn pipeline trước khi main in.

Một pool riêng cô lập **executor queue và worker threads**, nhưng CPU, heap, GC và downstream services trong JVM vẫn được chia sẻ. Không coi mỗi bước chuyển executor là “một máy chủ mới” hay bảo đảm hard deadline.

## 8. Default Executor và ForkJoinPool.commonPool()

Trong Java 17, `CompletableFuture` có một default asynchronous execution facility. Với các async methods không chỉ định executor, JDK thường dùng `ForkJoinPool.commonPool()` — pool toàn cục trong cùng JVM.

Những thành phần khác có thể cùng dùng common pool:

- `CompletableFuture.runAsync` / `supplyAsync` không truyền executor.
- Nhiều `thenApplyAsync`, `thenAcceptAsync`, `thenComposeAsync` không truyền executor.
- Những thuật toán `ForkJoinTask` submit vào `ForkJoinPool.commonPool()`.
- Parallel streams trong implementation JDK thông dụng.

Không cam kết tất cả luôn dùng common pool trong mọi config/implementation. Đặc biệt khi common pool không hỗ trợ parallelism tối thiểu 2, `CompletableFuture` có thể dùng thread-per-task fallback.

### Noisy neighbor

~~~text
Module A: 100 tác vụ CPU nặng ──────┐
                                     +── commonPool workers
Module B: 1 thenApplyAsync ngắn ────┘
                                     |
                                  contention
                                     |
                          callback B có thể chờ lâu
~~~

Một callback chỉ tốn 2 ms CPU có thể có **end-to-end latency** hàng trăm ms nếu phải đợi được schedule khi pool chung bận. Queueing/scheduling, CPU saturation, GC và downstream block cần được đo riêng; không kết luận từ một log hay một lần benchmark.

**Khi nào để mặc định?** Với computation nhẹ, CPU-oriented, không có yêu cầu isolation và đã đo trên tải thực, common pool có thể là lựa chọn gọn. Khi workload latency-sensitive, blocking hoặc tốn nhiều tài nguyên, cân nhắc executor riêng.

## 9. Không nên đưa blocking I/O dài vào commonPool một cách vô thức

Một sai lầm:

~~~java
// Snippet — blockingRemoteCall() là hàm nghiệp vụ chưa khai báo.
CompletableFuture<String> pipeline =
        source.thenApplyAsync(value -> blockingRemoteCall(value));
~~~

Hậu tố `Async` ở đây **không biến blocking I/O thành non-blocking**. Worker Fork/Join vẫn có thể chờ network/database/file trong hàng giây; nhiều callbacks đồng thời có thể làm pool chung thiếu worker cho phần tính toán khác.

Lựa chọn an toàn hơn khi có blocking:

~~~java
// Snippet — ioPool là ExecutorService đã tạo/quản lý ở component.
CompletableFuture<String> pipeline =
        source.thenApplyAsync(value -> blockingRemoteCall(value), ioPool);
~~~

Nhưng chỉ truyền `ioPool` là chưa đủ. Pool cần sizing dựa trên **giới hạn downstream và memory**, timeout I/O, bounded admission hoặc rejection policy nếu producer có thể nhanh hơn consumer, quan sát queue wait, và shutdown khi component không còn dùng. `Executors.newFixedThreadPool(n)` dùng unbounded queue theo contract nên không phải template production về backpressure.

### CPU-bound khác I/O-bound

- **CPU-bound:** Chọn concurrency có tính đến cores/quota và độ lớn leaf work; quá nhiều threads có thể tăng context switching.
- **I/O-bound:** Có thể cần nhiều concurrent tasks hơn CPU cores, nhưng vẫn bị giới hạn bởi connections, remote rate limits và memory. Áp dụng timeouts.
- **Mixed workload:** Cân nhắc tách executor cho CPU transformations và blocking I/O callbacks nếu cần bảo vệ p99 latency.
- **Rất nhiều pipeline nhỏ:** Tạo một executor mới cho mỗi request thường làm tăng overhead; dùng pool theo lifecycle component, tái sử dụng.

Đặt tên các executor theo **tính chất workload** hoặc yêu cầu isolation giúp cấu hình và monitoring dễ giải thích hơn là “pool1”, “pool2” trong ứng dụng thật.

## 10. Executor bị reject: thenApplyAsync không phải bảo đảm sẽ chạy

Một `Executor` có thể từ chối command khi pool đã shutdown hoặc khi queue/worker capacity hết. `ThreadPoolExecutor` thường biểu diễn bằng `RejectedExecutionException` tùy `RejectedExecutionHandler`.

Khi thiết kế pipeline:

- Không mặc định mọi callback đăng ký bằng `thenApplyAsync` đều được nhận.
- Với executor tùy chỉnh, `execute(Runnable)` có thể ném exception; sự từ chối có thể **xuất hiện ngay lúc đăng ký** hoặc **trên đường kích hoạt dependent stage**, tùy timing/implementation.
- Cần xử lý đường lỗi đúng, không đợi vô hạn một Future mà bạn không hề kiểm soát hoàn tất.
- `AbortPolicy` làm overload hiện rõ; `DiscardPolicy`/`CallerRunsPolicy` có semantics khác và có thể làm task bị bỏ hoặc chạy trên caller.
- Đừng sử dụng `CallerRunsPolicy` mà không đánh giá callback có an toàn khi chạy trong request/event-loop thread hoặc khi executor shutdown hay không.

### Ví dụ 5 — một Executor cố tình từ chối callback

Tạo `RejectedExecutorDemo.java` (Java 17+):

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.Executor;
import java.util.concurrent.RejectedExecutionException;

public class RejectedExecutorDemo {
    public static void main(String[] args) {
        Executor rejecting = command -> {
            throw new RejectedExecutionException("not accepting");
        };

        boolean rejectionObserved = false;
        try {
            CompletableFuture<Integer> next =
                    CompletableFuture.completedFuture(10)
                            .thenApplyAsync(x -> x * 2, rejecting);
            next.join();
        } catch (RejectedExecutionException ex) {
            rejectionObserved = true;
        } catch (CompletionException ex) {
            rejectionObserved =
                    ex.getCause() instanceof RejectedExecutionException;
        }

        System.out.println("rejection observed = " + rejectionObserved);
    }
}
~~~

Chạy:

~~~bash
javac RejectedExecutorDemo.java
java RejectedExecutorDemo
~~~

Stdout trong Java SE 17:

~~~text
rejection observed = true
~~~

Executor tùy chỉnh **luôn ném** `RejectedExecutionException` khi nhận command. Code chấp nhận hai cách biểu hiện thường gặp đối với đường điều phối bất đồng bộ: rejection đi trực tiếp qua lời gọi đăng ký, hoặc được ghi vào dependent completion rồi bọc trong `CompletionException` khi `join()`. Nó không bao giờ in một giá trị mapped vì executor không thực thi command.

**Quan trọng:** Đừng coi catch hai đường lỗi này là giải pháp overload đầy đủ: caller phải quyết định return lỗi, retry với backoff, drop có chủ đích, hoặc chuyển sang hệ thống bền vững theo yêu cầu nghiệp vụ.

## 11. Callback thất bại và exception propagation

Ví dụ source hoàn thành với `10`, callback `thenApplyAsync` ném `IllegalStateException`. Dependent stage kết thúc **exceptionally**; source vẫn có thể completed normally.

- `dependent.isCompletedExceptionally()` là true.
- `dependent.isDone()` là true, nhưng **không** có nghĩa thành công.
- `dependent.join()` ném unchecked `CompletionException` với cause tương ứng (trừ một số trường hợp đặc biệt như cancellation).
- `dependent.get()` ném checked `ExecutionException`; nguyên nhân qua `getCause()`.
- `exceptionally(fn)` có thể chuyển lỗi thành fallback value cho stage tiếp theo.
- Nếu `thenApplyAsync` được gắn vào source **đã failed/cancelled**, callback mapping **không được chạy**; stage phụ thuộc truyền trạng thái thất bại tương ứng.

### Ví dụ 6 — lỗi trong callback và fallback

Tạo `AsyncMappingFailure.java` (Java 17+):

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class AsyncMappingFailure {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            CompletableFuture<Integer> mapped =
                    CompletableFuture.completedFuture(10)
                    .thenApplyAsync(value -> {
                        throw new IllegalStateException("mapping failed");
                    }, pool);

            CompletableFuture<Integer> recovered =
                    mapped.exceptionally(error -> -1);

            System.out.println("fallback = " + recovered.join());
            System.out.println("mapped exceptional = "
                    + mapped.isCompletedExceptionally());

            try {
                mapped.join();
            } catch (CompletionException ex) {
                System.out.println("cause = "
                        + ex.getCause().getClass().getSimpleName());
            }
        } finally {
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
javac AsyncMappingFailure.java
java AsyncMappingFailure
~~~

Stdout:

~~~text
fallback = -1
mapped exceptional = true
cause = IllegalStateException
~~~

`exceptionally` không “sửa” stage `mapped` cũ; nó tạo **một stage phục hồi mới**. `mapped` vẫn exceptional. Cách hiểu này giúp tránh nhầm về hệ thống errors: biến nào đại diện kết quả gốc, biến nào đại diện fallback?

### Nếu source đã exceptional?

~~~java
// Snippet, không phải chương trình độc lập.
CompletableFuture<Integer> source =
        CompletableFuture.failedFuture(new IllegalArgumentException("bad"));

CompletableFuture<Integer> mapped =
        source.thenApplyAsync(x -> x * 2, executor);
// Mapper không được gọi vì source không hoàn thành bình thường.
// mapped hoàn tất exceptional theo chuỗi, không có giá trị mapped.
~~~

Muốn xử lý lỗi, cân nhắc `exceptionally`, `handle`/`handleAsync` hoặc `whenComplete`/`whenCompleteAsync` tùy việc **khôi phục giá trị**, **quan sát side effect** hay **chuyển đổi cả kết quả lẫn lỗi**. Không nhầm `thenApplyAsync` là một error handler.

## 12. thenApplyAsync khác thenComposeAsync: mapping hay flatten?

`thenApplyAsync(fn, executor)` áp dụng một function trả **giá trị U**. Nếu function trả `CompletableFuture<U>`, kết quả sẽ là một Future **lồng trong Future**:

~~~text
CompletableFuture<T>
  .thenApplyAsync(T -> CompletableFuture<U>, executor)
        |
        v
CompletableFuture<CompletableFuture<U>>
~~~

`thenComposeAsync(fn, executor)` dùng function trả `CompletionStage<U>` và **flatten/compose** để kết quả là `CompletableFuture<U>`:

~~~text
CompletableFuture<T>
  .thenComposeAsync(T -> CompletionStage<U>, executor)
        |
        v
CompletableFuture<U>
~~~

Sự khác biệt này **không** liên quan việc “async stage nào có nhiều threads hơn”; nó là sự khác nhau giữa **mapping** và **monadic flattening/dependency composition**.

### Khi nào dùng cái nào?

| Function | Phương thức thích hợp |
| --- | --- |
| `T -> U`, tính ra giá trị thường | `thenApply` / `thenApplyAsync` |
| `T -> CompletionStage<U>`, gọi dịch vụ async khác | `thenCompose` / `thenComposeAsync` |
| Hai Futures độc lập, cần gộp cả hai | `thenCombine` / `thenCombineAsync` |
| Chỉ làm side effect với giá trị, trả `Void` | `thenAccept` / `thenAcceptAsync` |
| Chỉ làm tác vụ sau completion, không cần input | `thenRun` / `thenRunAsync` |

### Ví dụ 7 — thenComposeAsync không block worker để đợi future con

Tạo `ComposeVsApply.java` (Java 17+):

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class ComposeVsApply {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            CompletableFuture<Integer> source =
                    CompletableFuture.completedFuture(3);

            CompletableFuture<CompletableFuture<Integer>> nested =
                    source.thenApplyAsync(x ->
                            CompletableFuture.completedFuture(x * 2), pool);

            CompletableFuture<Integer> flattened =
                    source.thenComposeAsync(x ->
                            CompletableFuture.supplyAsync(() -> x * 2, pool),
                            pool);

            System.out.println("nested result = "
                    + nested.join().join());
            System.out.println("flattened result = "
                    + flattened.join());
        } finally {
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
javac ComposeVsApply.java
java ComposeVsApply
~~~

Stdout:

~~~text
nested result = 6
flattened result = 6
~~~

`thenApplyAsync` ở ví dụ đầu trả về **một Future bên trong một Future**, nên main cần `join().join()`. `thenComposeAsync` nhận một asynchronous computation và trả Future phẳng. Dù sử dụng **single-thread pool**, không xảy ra starvation ở ví dụ này vì callback compose **trả Future con rồi kết thúc**, không block worker bằng `join()` bên trong chính callback ấy.

**Đừng viết thay thế**:

~~~java
// Snippet anti-pattern: blocking wait trong worker của single-thread pool.
source.thenApplyAsync(x ->
        CompletableFuture.supplyAsync(() -> x * 2, pool).join(),
        pool);
~~~

Ở cấu hình single-thread, callback bên ngoài chiếm worker rồi block đợi task con đã submit **vào chính pool ấy**; task con không có worker rảnh để chạy. Đây có thể là **thread-pool starvation deadlock**. `thenComposeAsync` biểu diễn dependency mà không chặn worker để đợi Future con theo cách ấy.

## 13. thenApplyAsync và Java Memory Model

Chuyển từ stage trước sang stage sau không phải một thao tác đọc/ghi biến thường tùy tiện. `CompletableFuture` và `Future` cung cấp cơ chế completion và synchronization để dependent callback nhận đúng giá trị hoàn tất, kể cả khi nó chạy trên thread khác.

Với một pipeline đơn giản:

~~~java
CompletableFuture<String> stage =
        CompletableFuture.supplyAsync(() -> "ready", executorA)
                .thenApplyAsync(value -> value + "!", executorB);
~~~

Callback sau được chạy khi stage trước completed normally; nó nhận String immutable do stage trước trả về. Không cần `volatile` cho **tham số `value`** chỉ để truyền chính giá trị Future ấy. Bảo đảm synchronization của completion/execution giúp kết quả được chuyển giao an toàn.

Tuy nhiên:

- Nếu callback giữ reference tới một **mutable object** mà các threads khác còn tiếp tục sửa, CompletableFuture không biến mọi mutation khác thành atomic.
- `sharedCounter++` trong hai callbacks đồng thời vẫn có thể lost update; dùng `AtomicInteger`, lock hoặc mô hình immutable reduce khi cần.
- Việc source completed không tự đảm bảo transaction bên ngoài (DB/network) đã commit nếu thao tác ngoài JVM chưa được đồng bộ/ack.
- Việc callback ở executor khác không tự làm thread-local values của source thread được truyền qua.
- Nếu callback mở một task **fire-and-forget** khác rồi return, completion của callback **không** có nghĩa task con đã hoàn tất.

### Giao quyền sở hữu object mutable

Một thiết kế an toàn hơn là:

1. Tạo một immutable DTO/snapshot trước khi complete stage.
2. Đưa DTO/snapshot làm result của Future.
3. Mỗi callback chỉ đọc snapshot hoặc tạo giá trị mới.
4. Nếu callback cần sửa shared mutable state, dùng synchronization đúng.
5. Không tiếp tục mutate object sau khi “publish” rồi nghĩ Future đã khóa toàn bộ object graph.

Đây là Java concurrency nói chung; không phụ thuộc cơ chế quản lý transaction hay request scope của framework nào.

## 14. ThreadLocal và execution context có thể thay đổi

`ThreadLocal` lưu state theo **thread**, không tự truyền context từ thread gọi đăng ký `thenApplyAsync` sang worker khác. Do đó:

~~~java
// Snippet cảnh báo, không phải chương trình độc lập.
ThreadLocal<String> correlationId = new ThreadLocal<>();
correlationId.set("request-7");

future.thenApplyAsync(value -> {
    // Không được mặc định correlationId.get() == "request-7".
    return transform(value);
}, executor);
~~~

Nếu thread này là shared worker, bạn cũng không nên dựa vào một ThreadLocal từ request trước còn sót. Nếu chủ động set context trên worker, phải restore/clear trong `finally` hoặc một adapter an toàn đã được kiểm chứng.

Có thể truyền **context bất biến** như một phần của object đầu vào thay vì dùng biến ẩn theo thread:

~~~java
// Snippet API, khai báo record/context/method theo ứng dụng.
record Input(String correlationId, int value) {}

CompletableFuture<Input> inputStage =
        CompletableFuture.completedFuture(new Input("request-7", 21));

CompletableFuture<String> result =
        inputStage.thenApplyAsync(input ->
                input.correlationId() + ":" + (input.value() * 2),
                executor);
~~~

Đây không phải chương trình standalone vì biến `executor` là executor đã cấu hình ở nơi khác. Ý chính: context là **dữ liệu tường minh**, không phụ thuộc scheduler chọn worker nào.

## 15. Timeout: thời gian caller chờ khác thời gian callback thực thi

Nếu caller làm:

~~~java
// Snippet API trong method có thể throw TimeoutException/Exception.
String value = future.get(100, TimeUnit.MILLISECONDS);
~~~

Thì `get(timeout)` giới hạn **thời gian chờ của caller**; nó **không tự cancel** callback `thenApplyAsync` đang chờ executor hoặc đang chạy. Callback có thể hoàn tất sau khi caller timeout.

Trong Java 17 còn có `CompletableFuture.orTimeout(timeout, unit)` để hoàn tất Future **exceptionally với `TimeoutException`** nếu chưa completed, và `completeOnTimeout(value, timeout, unit)` để cung cấp một value fallback. Chúng ảnh hưởng **trạng thái completion** của CompletableFuture theo hợp đồng; **không** có nghĩa worker đang thực thi hàm ứng dụng sẽ bị interrupt hay side effects được rollback.

### Ví dụ 8 — timeout khi callback đang chờ latch, sau đó vẫn hoàn tất

Tạo `AsyncWaitTimeout.java` (Java 17+):

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class AsyncWaitTimeout {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            CompletableFuture<Integer> mapped =
                    CompletableFuture.completedFuture(7)
                    .thenApplyAsync(value -> {
                        started.countDown();
                        try {
                            release.await();
                            return value + 1;
                        } catch (InterruptedException e) {
                            Thread.currentThread().interrupt();
                            throw new IllegalStateException(e);
                        }
                    }, pool);

            started.await();
            try {
                mapped.get(50, TimeUnit.MILLISECONDS);
            } catch (TimeoutException expected) {
                System.out.println("wait timed out = true");
            }

            System.out.println("cancelled = " + mapped.isCancelled());
            System.out.println("done before release = " + mapped.isDone());

            release.countDown();
            System.out.println("result = " + mapped.join());
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
javac AsyncWaitTimeout.java
java AsyncWaitTimeout
~~~

Stdout trên đường chạy bình thường:

~~~text
wait timed out = true
cancelled = false
done before release = false
result = 8
~~~

`started.await()` xác nhận callback đã vào body; nó không thể return trước khi `release` mở. Vì vậy `get(50ms)` chắc chắn timeout ở caller. Sau timeout, stage vẫn pending; mở latch cho callback trả `8` bình thường. Không phụ thuộc vào một `Thread.sleep` bất định để tạo delay.

**Production tip:** Với I/O, dùng deadline ở **API I/O** (connect/read/request timeout) và thiết kế cancellation cooperative; đừng mặc định caller timeout có nghĩa connection đã được đóng an toàn.

## 16. Cancellation của CompletableFuture không ép interrupt callback

`CompletableFuture.cancel(boolean mayInterruptIfRunning)` ảnh hưởng **trạng thái CompletableFuture**. Theo tài liệu implementation `CompletableFuture`, `mayInterruptIfRunning` **không có hiệu lực điều khiển computation** như người đọc có thể kỳ vọng ở một số `FutureTask`.

Điều này quan trọng đối với `thenApplyAsync`:

- Một stage bị cancel có thể khiến `isDone()`/`isCancelled()` true và `join()` ném `CancellationException`.
- Callback đang thực thi ở worker riêng **không được bảo đảm bị interrupt/dừng ngay** chỉ vì dependent stage bị cancel.
- Nếu callback đã gửi side effect tới DB/API, cancellation không rollback.
- Cancel một dependent stage **không tự hủy** source stage độc lập; ngược lại, failure/cancellation propagation qua dependent pipeline theo rules của CompletionStage cần được hiểu rõ.
- `exceptionally`/`handle`/`whenComplete` không tự là cơ chế dừng worker.

Nếu phải dừng công việc đang chạy, hãy dùng **stop token**, deadline, timeout của library, kiểm tra cancellation hợp tác và signal **body actually stopped** riêng khi cần dọn resources.

### Không dựa vào `isDone()` sau cancel làm điều kiện đóng tài nguyên

Một stage đã completed exceptionally/cancelled có thể không còn cung cấp kết quả bình thường trong khi computation thực sự vẫn làm cleanup hoặc vẫn chạy. Không đóng một socket/object do callback còn đang sử dụng chỉ từ trạng thái Future nếu không có giao thức ownership phù hợp.

Với nhiều dependent stages chia sẻ cùng source, cancellation của một nhánh còn đòi hỏi xem nhánh khác có cần kết quả source không; đừng hủy computation chung chỉ vì một caller bỏ đợi.

## 17. Lỗi đường ống và nơi đặt recovery stage

Một pipeline điển hình:

~~~text
supplyAsync(fetch, ioPool)
      |
      v
thenApplyAsync(parse, cpuPool)
      |
      v
thenApplyAsync(validate, cpuPool)
      |
      +---------- completed normally ---> thenAcceptAsync(persist, ioPool)
      |
      +---------- exceptional ----------> exceptionally(recover/log)
~~~

Nếu `parse` lỗi, `validate` không được chạy và `persist` sẽ không chạy theo nhánh thenAccept thông thường. Điều này rất quan trọng để không vô tình ghi dữ liệu chưa được validate.

Những lựa chọn error handling:

| API | Khi nào được gọi? | Trả kiểu gì? |
| --- | --- | --- |
| `exceptionally(fn)` | Khi stage trước exceptional | Một giá trị fallback cho cùng kiểu kết quả |
| `handle(fn)` | Dù success/failure | Chuyển `(value, throwable) -> U` |
| `handleAsync(fn, executor)` | Dù success/failure | Tương tự, nhưng mapping qua executor |
| `whenComplete(action)` | Dù success/failure | Quan sát side effect, giữ nguyên kiểu result |
| `whenCompleteAsync(action, executor)` | Dù success/failure | Tương tự, action qua executor |
| `exceptionallyAsync(fn, executor)` | Khi exceptional | Recovery mapping async, có trong Java 17 |

Đừng trả null từ recovery một cách vô thức rồi để stage sau gọi phương thức trên null. Định nghĩa rõ **fallback** có hợp lệ về business semantics không; đôi khi tốt nhất là propagate failure và trả lỗi cho caller.

Khi có executor riêng cho error handling, nhớ rằng **ngay cả callback ghi log/khôi phục** cũng có thể bị queue hoặc reject nếu executor không sẵn sàng; không xây một error-reporting path chỉ dựa vào pool đang bị hỏng/đầy.

## 18. Một callback nặng có thể làm nghẽn completion path nếu dùng thenApply

Đây là một lý do thực tế để chọn `thenApplyAsync`: nếu `thenApply` chạy trên thread đang hoàn tất source, một callback CPU nặng hoặc blocking có thể giữ thread ấy lâu hơn mong đợi. Nếu source hoàn tất trong thread nhạy latency (I/O event loop, request dispatcher, thread phát kết quả cho nhiều dependents), inline computation có thể làm chậm các hoạt động khác.

~~~text
thenApply:
  source completed by thread X
           |
       callback nặng chạy inline trên completion path
           |
        X bận, chưa phục vụ việc khác

thenApplyAsync(..., executor):
  source completed by thread X
           |
       submit dependent callback tới executor
           |
        X có thể rời completion path sớm hơn
           |
        callback chờ/running tại executor
~~~

Đây là **khả năng**, không phải cam kết thread X sẽ luôn hoàn toàn không làm việc khác sau submit. Việc chuyển task cũng có overhead và có thể bị reject; executor direct/caller-runs có thể chạy callback inline. Với mapping cực nhỏ, chi phí scheduling thêm có thể lớn hơn công việc mapping.

### Quy tắc lựa chọn khởi đầu

- `thenApply`: hàm **rất ngắn, thuần, không blocking**, chấp nhận chạy trong completion/caller path.
- `thenApplyAsync(fn)`: muốn async boundary, task CPU-oriented, không cần resource isolation đặc biệt; đã đánh giá common pool.
- `thenApplyAsync(fn, executor)`: cần rõ workload isolation/lifecycle/threads/queue policy, hoặc callback blocking nên có pool I/O riêng.
- `thenComposeAsync`: mapper trả về async operation; cần compose thay vì block trên Future con.

Chọn sau khi đo; đừng tự động thêm `Async` vào mọi stage. Thực thi một chuỗi hàng trăm callbacks nhỏ qua executor có thể tạo scheduler overhead không cần thiết.

## 19. Thread pool starvation nếu callback block đợi task ở chính pool

Giả sử dùng `Executors.newSingleThreadExecutor()`, một callback `thenApplyAsync` chạy trong worker duy nhất, bên trong lại submit task khác vào **cùng pool** rồi gọi `join()` để đợi. Task con nằm trong queue nhưng worker duy nhất đã bị callback cha giữ. Đó có thể là **thread-pool starvation deadlock**.

~~~java
// Snippet nguy hiểm: KHÔNG chạy trực tiếp như một chương trình.
source.thenApplyAsync(value ->
        CompletableFuture.supplyAsync(
                () -> slowTransform(value), sameSingleThreadPool).join(),
        sameSingleThreadPool);
~~~

Để tránh:

1. Dùng `thenCompose`/`thenComposeAsync` để **compose** Future con thay vì block callback cha.
2. Tránh dependency cycle khi task A chờ B, B phải được chạy bởi resource A đang chiếm.
3. Đặt timeout cho waits khi có ý nghĩa (không thay thế correctness).
4. Tách workloads có dependency đặc biệt hoặc dùng đủ resource với protocol phù hợp.
5. Không hold lock trong callback rồi đợi task khác cần chính lock đó.

Đừng cho rằng chỉ vì default executor là ForkJoinPool có work-stealing nên mọi blocking Future wait đều an toàn. Work stealing không giải quyết dependency cycles và tài nguyên downstream hữu hạn.

## 20. Thay đổi executor có thể làm thay đổi độ ưu tiên và trật tự kết thúc

Trong một pipeline `A -> B -> C`, các stages có **quan hệ phụ thuộc**: B không thể chạy mapper trước khi A completed normally; C không thể chạy mapper trước khi B completed normally. Nhưng nếu **hai nhánh độc lập** cùng phụ thuộc source:

~~~text
             source
              /  \
             /    \
    thenApplyAsync A   thenApplyAsync B
       executorA          executorB
             \            /
              \          /
               thenCombine
~~~

Không có bảo đảm A kết thúc trước B hay ngược lại. Chọn executor khác nhau ảnh hưởng waiting time, CPU, queue policy và thread-local context; **không** áp đặt thứ tự giữa hai nhánh độc lập.

Nếu cần gộp, sử dụng `thenCombine`/`thenCombineAsync` hoặc `allOf` rồi đọc kết quả, không ghép bằng side effects trên một `ArrayList` shared không khóa.

### Fan-out và resource budgeting

Một source có thể kích hoạt nhiều dependents async cùng lúc. Nếu 1.000 source stages đều complete, mỗi cái fan-out 10 callbacks, lượng task chờ có thể tăng rất nhanh. Không dùng sự tồn tại của Executor như một chứng minh backlog được giới hạn.

Một số biện pháp:

- Giảm fan-out/batch input khi phù hợp.
- Rate limit/admission limit ở producer.
- Executor có queue hữu hạn và overload policy rõ.
- Giữ memory footprint của captured closures nhỏ.
- Hủy/hết hạn các công việc không còn giá trị theo protocol.
- Theo dõi queue length, queue wait, rejection, active workers, completion counts.
- Dùng thời gian thực thi đại diện khi sizing, không chỉ microbenchmark callback rỗng.

## 21. Tác động của shutdown và dependency đang chờ executor

Khi một component sở hữu `ExecutorService` và dùng nó trong pipeline, thứ tự shutdown rất quan trọng:

- **Ngừng nhận pipeline mới** trước khi dừng executor, nếu không các source stage hoàn tất muộn có thể cố submit callback mới vào executor đã shutdown.
- Nếu chỉ đăng ký callback nhưng source chưa completed, callback **chưa được submit vào executor**; shutdown sớm có thể khiến dependent stage không thực thi bình thường.
- `executor.shutdown()` không chờ mọi pipeline đã hoàn tất trước khi trả về; nó chỉ bắt đầu graceful shutdown theo hợp đồng executor.
- Giữ handles của **final pipeline stages** và chờ `get/join` hoặc `allOf` với deadline phù hợp trước khi shutdown executor nếu muốn drain.
- `shutdownNow()` là best effort interrupt và trả các tasks chưa bắt đầu; không tự rollback task/CompletableFuture side effects.
- Với shared common pool, không nên tự gọi shutdown như thể pool thuộc về một module.
- Khi có executor rejection, đừng để monitoring ghi “pipeline completed” nếu dependent stage thực tế đã lỗi.

### Mẫu nguyên tắc shutdown

~~~java
// Snippet kiến trúc, chưa độc lập.
stopSubmittingNewPipelines();
awaitOwnedPipelineFuturesWithDeadline();
ownedExecutor.shutdown();
if (!ownedExecutor.awaitTermination(10, TimeUnit.SECONDS)) {
    ownedExecutor.shutdownNow();
}
~~~

`awaitOwnedPipelineFuturesWithDeadline` phải thu cả successful/exceptional/cancelled outcomes theo nhu cầu, không chỉ call `join` rồi bỏ qua exception. Nếu có lỗi, hãy quyết định retry/compensate/log trước khi rời component. Với cancellation, body còn chạy có thể phải hoàn tất cleanup riêng.

## 22. Quan sát executor và callback ở production

Khi một stage `thenApplyAsync` chậm, hãy chia thời gian thành:

~~~text
T0: stage trước hoàn tất
    |
    | callback đủ điều kiện; submit tới executor
    v
T1: executor nhận/queue callback
    |
    | QUEUE WAIT TIME
    v
T2: worker bắt đầu mapper
    |
    | EXECUTION TIME
    v
T3: mapper return hoặc throw
    |
    | dependent completion / downstream notification
    v
T4: stage sau bắt đầu/nhận kết quả
~~~

Một callback body chạy 2 ms nhưng queue wait 200 ms sẽ làm latency phụ thuộc stage đó tăng đáng kể. Chỉ log thời gian trong body sẽ bỏ qua phần chờ.

Những metric hữu ích:

| Metric | Vì sao cần |
| --- | --- |
| Parent stage completion time | Phân biệt chậm ở source và chậm ở dependent |
| Submit-to-start (queue wait) | Phát hiện executor saturation |
| Callback execution time p50/p95/p99 | Phát hiện blocking/CPU/GC contention |
| Pool active/queued/completed counts | Xem năng lực xử lý và backlog |
| Rejected tasks | Phát hiện overload hoặc shutdown race |
| Timeout/cancel/exceptional completions | Đánh giá tỷ lệ kết quả không hợp lệ |
| Heap/GC/allocations | Captured closures/queued tasks có thể giữ object graph |
| Thread dumps | Phát hiện worker block ở lock, Future.join, I/O |
| Downstream connections/rate limits | Tăng worker không phải lúc nào cũng tăng throughput |

Các getter của `ThreadPoolExecutor` là snapshot/ước lượng và không thể thay admission protocol. `queue.size() < limit` rồi submit không atomic vì thread khác có thể submit giữa hai thao tác.

Đối với common pool, những metric như `getQueuedTaskCount`, `getQueuedSubmissionCount`, `getActiveThreadCount` và `getStealCount` là estimates phục vụ chẩn đoán; không dùng một snapshot làm bằng chứng stage của module đã xong.

## 23. Một số nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “`thenApplyAsync` luôn tạo thread mới.” | Thường dùng một executor/pool; có thể tái sử dụng worker, và direct Executor có thể chạy inline |
| “`thenApplyAsync` chắc chắn chạy song song với stage trước.” | Mapper phụ thuộc source, chỉ đủ điều kiện khi source đã completed normally |
| “`thenApply` luôn chạy ở thread gọi đăng ký.” | Có thể chạy trong thread hoàn tất stage trước, hoặc caller khi stage đã completed |
| “`thenApplyAsync(fn)` mặc nhiên dùng pool riêng của pipeline.” | Mặc định thường dùng `commonPool()`, trừ fallback/implementation khác |
| “Truyền executor cho stage đầu là toàn chuỗi thừa hưởng.” | Mỗi async dependent method cần xét executor riêng |
| “Có executor là không thể reject.” | Executor có thể shutdown hoặc bounded queue đầy |
| “`Async` nghĩa callback non-blocking I/O.” | Callback có thể blocking; Async chủ yếu nói về cách scheduling |
| “`join` luôn trả giá trị ngay.” | Nó có thể block tới khi stage hoàn tất; lỗi thường ném `CompletionException` |
| “`thenApplyAsync` xử lý exception của source.” | Mapper không được gọi nếu source exceptional; dùng recovery APIs |
| “Một source thất bại nhưng mapper vẫn tính một giá trị bình thường.” | Dependent stage thường propagate exceptional completion |
| “`CompletableFuture.cancel(true)` luôn interrupt worker.” | Tham số interrupt không có hiệu lực với implementation CompletableFuture |
| “Caller `get(timeout)` timeout sẽ cancel pipeline.” | Timeout của caller không tự hủy computation |
| “Mọi dependent stage có thứ tự hoàn thành theo thứ tự đăng ký.” | Nhánh độc lập có thể chạy theo thứ tự khác nhau |
| “`thenApplyAsync` phù hợp khi function trả Future.” | `thenComposeAsync` giúp flatten async dependency |
| “Pool riêng đồng nghĩa có thêm CPU.” | CPU, heap, GC và downstream vẫn là tài nguyên chung |
| “Có common pool nên không thể deadlock.” | Blocking waits, dependency cycles và lock contention vẫn có thể kẹt |
| “ThreadLocal tự truyền sang worker.” | Không có propagation tự động của ordinary ThreadLocal |
| “shutdown executor khi vừa đăng ký callback là đủ.” | Source có thể chưa completed; callback chưa submit và có thể bị reject sau shutdown |
| “thenApplyAsync nhỏ lúc nào cũng nhanh hơn thenApply.” | Scheduling overhead/queue wait có thể lớn hơn phép mapping |
| “isDone true nghĩa là mọi side effects đã được rollback/cleanup.” | Exceptional/cancel completion và cleanup thực sự là những trạng thái khác nhau |

## 24. Tự kiểm tra

**Câu 1.** `CompletableFuture.completedFuture(10).thenApply(x -> x+1)` có tạo một stage khác không?  
**Đáp án:** Có, nó trả `CompletableFuture<Integer>` mới với giá trị `11`; source cũ vẫn giữ `10`.

**Câu 2.** `thenApplyAsync(fn)` mặc định chạy ở đâu trong Java 17?  
**Đáp án:** Thường qua `ForkJoinPool.commonPool()`; có fallback khi common pool không hỗ trợ parallelism ít nhất 2.

**Câu 3.** `thenApplyAsync(fn, executor)` chắc chắn đổi thread so với caller không?  
**Đáp án:** Không phải hợp đồng bắt buộc cho mọi Executor; direct Executor có thể gọi `run` inline.

**Câu 4.** Khi source CompletableFuture chưa completed, gọi `thenApplyAsync` có khiến mapper chạy ngay không?  
**Đáp án:** Không. Mapper chờ source completed normally rồi mới được kích hoạt.

**Câu 5.** Source completed exceptionally. Callback `thenApplyAsync` có chạy để “sửa lỗi” không?  
**Đáp án:** Không; cần dùng `exceptionally`, `handle` hoặc recovery API tương ứng.

**Câu 6.** `thenApply` trên source đã completed có thể chạy ở thread nào?  
**Đáp án:** Nó có thể chạy ngay trên caller/registration thread; trong tình huống source hoàn tất sau khi đăng ký, thường chạy trên completion path.

**Câu 7.** Muốn tách CPU transform và blocking database call thì nên làm gì?  
**Đáp án:** Cân nhắc executors riêng, một pool CPU và một pool I/O với timeouts, capacity và overload policy; truyền executor tường minh tới từng async stage cần isolation.

**Câu 8.** Một stage đầu dùng `poolA`, stage sau gọi `thenApplyAsync(fn)` không có executor. Nó chắc vẫn chạy ở `poolA`?  
**Đáp án:** Không. Stage sau dùng default async facility của CompletableFuture, thường common pool.

**Câu 9.** `thenApplyAsync(x -> CompletableFuture.supplyAsync(...), pool)` trả kiểu gì?  
**Đáp án:** Thường là `CompletableFuture<CompletableFuture<U>>`; dùng `thenComposeAsync` nếu muốn flatten thành `CompletableFuture<U>`.

**Câu 10.** Worker single-thread pool gọi `supplyAsync(..., samePool).join()` trong mapper đang chạy. Có rủi ro gì?  
**Đáp án:** Thread-pool starvation deadlock vì task con chờ worker đang bị mapper cha chiếm.

**Câu 11.** Mapper ném `IllegalStateException`. `join` trên dependent stage trả gì?  
**Đáp án:** Thường ném `CompletionException` với cause là `IllegalStateException`.

**Câu 12.** Executor bị shutdown, `thenApplyAsync(fn, executor)` vẫn chắc chạy callback?  
**Đáp án:** Không. Việc submit có thể bị reject; phải xử lý failure/shutdown race.

**Câu 13.** Caller `get(50, MILLISECONDS)` bị timeout; callback có tự bị cancel không?  
**Đáp án:** Không. Timeout của waiting thread không tự cancel CompletableFuture.

**Câu 14.** `future.cancel(true)` có chắc ngắt Supplier/mapper đang chạy không?  
**Đáp án:** Không. CompletableFuture cancellation thay đổi completion state, không ép interrupt code đang thực thi.

**Câu 15.** Tại sao không dùng ordinary ThreadLocal để truyền request ID qua `thenApplyAsync`?  
**Đáp án:** Callback có thể chạy trên worker khác; ordinary ThreadLocal không tự truyền giá trị từ caller.

**Câu 16.** Khi nào `thenApply` thường phù hợp hơn `thenApplyAsync`?  
**Đáp án:** Khi mapper ngắn, thuần, không blocking, và có thể chạy an toàn trên completion path mà không cần thêm scheduling overhead.

## Tài liệu tham khảo Java SE 17

- [`CompletableFuture` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `thenApply/thenApplyAsync`, default async facility, explicit executors, cancellation, error handling.
- [`CompletionStage` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html): stages phụ thuộc, `thenComposeAsync`, `thenCombine` và execution rules.
- [`Executor` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executor.html): hợp đồng `execute(Runnable)`.
- [`ExecutorService` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): quản lý worker pool và shutdown.
- [`ThreadPoolExecutor` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html): queueing, rejection, lifecycle và monitoring.
- [`ForkJoinPool` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): common pool, work-stealing, shared-resource considerations.
- [`Future` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): `get(timeout)`, completion và cancellation.
- [`RejectedExecutionException` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RejectedExecutionException.html): khi executor từ chối task.
- [`ThreadLocal` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html): per-thread context.
- [Java Language Specification `17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): synchronization, memory visibility và happens-before.

**Ghi nhớ:** `thenApplyAsync` tách **điều kiện phụ thuộc** khỏi **nơi thực thi mapping**. Dùng `thenApply` cho transform ngắn có thể chạy inline; dùng `thenApplyAsync(fn)` nếu chấp nhận default async facility; dùng `thenApplyAsync(fn, executor)` khi cần chọn rõ **worker resource, queue/rejection policy và lifecycle**. Mọi lựa chọn vẫn phải xem deadline, error propagation, backpressure, thread context và việc có block downstream hay không.