# Executor kiểm soát được cho CompletableFuture trong Java 8

## 1. Vì sao cần chỉ định Executor cho CompletableFuture?

CompletableFuture giúp nối các bước xử lý bất đồng bộ thành một pipeline. Nhưng một pipeline đúng về dữ liệu chưa chắc đã đúng về **nơi chạy công việc**, **giới hạn tài nguyên** và **vòng đời thread**.

Ví dụ:

~~~java
CompletableFuture.supplyAsync(() -> loadOrder())
    .thenApplyAsync(order -> calculateTotal(order))
    .thenAcceptAsync(total -> publishResult(total));
~~~

Code trên không chỉ định executor. Các phương thức async không nhận tham số Executor sẽ dùng cơ chế thực thi bất đồng bộ mặc định của CompletableFuture. Với các static method như supplyAsync và runAsync, đó là ForkJoinPool.commonPool(). Common pool là tài nguyên dùng chung trong JVM. Điều này tiện cho tác vụ ngắn, nhưng không phải lúc nào cũng phù hợp với hệ thống có nhiều tác vụ I/O blocking, yêu cầu cách ly tải, giới hạn queue hoặc cần shutdown theo lifecycle của ứng dụng.

Java 8 cho phép truyền executor trực tiếp vào các overload async:

~~~java
ExecutorService databaseExecutor = ...;

CompletableFuture.supplyAsync(
    () -> loadOrder(),
    databaseExecutor
);
~~~

Các continuation async cũng có overload nhận executor:

~~~java
CompletableFuture.supplyAsync(this::loadOrder, databaseExecutor)
    .thenApplyAsync(this::calculateTotal, calculationExecutor)
    .thenAcceptAsync(this::publishResult, notificationExecutor);
~~~

Nhờ vậy, từng bước có thể được điều phối trên nhóm thread phù hợp với loại công việc. Ứng dụng cũng có thể chủ động giới hạn số worker, dung lượng queue, tên thread, chính sách từ chối tác vụ và thời điểm đóng executor.

Bài Knowledge **“Executor kiểm soát được cho CompletableFuture”** thuộc nhóm **Kiểm thử và tối ưu**, module **Java 8**. Bài trình bày cách chọn executor cho từng stage, khác biệt giữa continuation đồng bộ và async, common pool, cách tạo pool có giới hạn, queue và rejection, tách workload I/O/CPU, xử lý lỗi, shutdown, kiểm thử thread thực thi và những lỗi vận hành thường gặp. Ví dụ sử dụng API có từ Java 8 và vẫn còn được hỗ trợ trên JDK hiện đại.

**Mục tiêu:** biết chính xác stage nào chạy ở đâu, không để tác vụ blocking chiếm tài nguyên chung ngoài ý muốn, có giới hạn tải rõ ràng và đóng executor đúng lifecycle.

## 2. Executor là gì và nó quyết định điều gì?

java.util.concurrent.Executor là abstraction nhận một Runnable và quyết định cách thực thi tác vụ. Nó tách **việc gửi công việc** khỏi **cơ chế chạy công việc**.

~~~java
Executor executor = ...;
executor.execute(() -> doWork());
~~~

Executor có thể chạy task bằng thread trong pool, tạo thread mới, xếp vào queue, hoặc trong trường hợp đơn giản chạy ngay trên thread gọi execute(). Vì vậy, interface Executor **không tự bảo đảm rằng task luôn chạy ở thread khác**. Một executor trực tiếp như:

~~~java
Executor direct = Runnable::run;
~~~

sẽ thực thi task ngay trong thread gọi. Nếu yêu cầu cách ly thread, cần chọn implementation thực sự điều phối sang worker thread, ví dụ ThreadPoolExecutor.

### Executor và ExecutorService

| Kiểu | Trách nhiệm |
| --- | --- |
| Executor | Nhận và thực thi Runnable qua execute() |
| ExecutorService | Mở rộng Executor với submit, shutdown, awaitTermination và quản lý lifecycle |
| ThreadPoolExecutor | ExecutorService dạng thread pool, cấu hình worker, queue và rejection |
| ForkJoinPool | Pool phục vụ fork/join và parallel tasks; common pool được CompletableFuture dùng mặc định |

Một CompletableFuture có thể nhận bất kỳ implementation nào của Executor. Trong ứng dụng, ExecutorService thường phù hợp hơn vì thành phần sở hữu pool cần đóng nó khi shutdown.

**CompletableFuture không sở hữu executor được truyền vào.** Khi future hoàn tất, nó không tự gọi shutdown() cho pool. Thành phần tạo pool chịu trách nhiệm lifecycle của pool đó.

## 3. Ba cách gắn công việc vào CompletionStage

Cần phân biệt ba kiểu continuation.

### 3.1. Phương thức không có hậu tố Async

~~~java
CompletableFuture<String> result =
    source.thenApply(value -> transform(value));
~~~

thenApply không yêu cầu executor mới. Tác vụ có thể được thực hiện bởi thread hoàn tất stage trước đó hoặc thread khác gọi phương thức completion. Nếu stage đã hoàn tất trước khi gắn continuation, continuation cũng có thể chạy ngay trên thread đang gắn nó.

Vì vậy, không nên giả định thenApply luôn chạy trên worker pool, request thread hay main thread. Vị trí thực thi phụ thuộc cách và thời điểm stage hoàn tất.

### 3.2. Phương thức Async không chỉ định Executor

~~~java
CompletableFuture<String> result =
    source.thenApplyAsync(value -> transform(value));
~~~

Phương thức yêu cầu thực thi bất đồng bộ qua default asynchronous execution facility của stage. Với CompletableFuture thông thường, cơ chế mặc định là common pool (với fallback được mô tả trong Javadoc khi common pool không hỗ trợ parallelism cần thiết).

Cách này tiện khi không cần kiểm soát pool riêng. Tuy nhiên, các công việc không cùng loại vẫn có thể cạnh tranh trên common pool.

### 3.3. Phương thức Async có Executor

~~~java
CompletableFuture<String> result =
    source.thenApplyAsync(
        value -> transform(value),
        calculationExecutor
    );
~~~

Đây là cách điều khiển rõ ràng nhất: executor được truyền vào là nơi stage async gửi task để thực thi. Các overload tương ứng có trong Java 8 gồm:

| Giai đoạn | Không chỉ định Executor | Có Executor |
| --- | --- | --- |
| Tạo giá trị bất đồng bộ | supplyAsync(supplier) | supplyAsync(supplier, executor) |
| Chạy tác vụ bất đồng bộ | runAsync(runnable) | runAsync(runnable, executor) |
| Biến đổi kết quả | thenApplyAsync(fn) | thenApplyAsync(fn, executor) |
| Tiêu thụ kết quả | thenAcceptAsync(action) | thenAcceptAsync(action, executor) |
| Kết hợp hai kết quả | thenCombineAsync(other, fn) | thenCombineAsync(other, fn, executor) |
| Nối stage | thenComposeAsync(fn) | thenComposeAsync(fn, executor) |
| Xử lý kết quả/lỗi | handleAsync(fn) | handleAsync(fn, executor) |
| Phản ứng khi hoàn tất | whenCompleteAsync(fn) | whenCompleteAsync(fn, executor) |

**Chỉ định executor cho một stage không tự động gắn executor đó vào mọi stage tiếp theo.** Muốn kiểm soát thread của từng continuation async, truyền executor tương ứng vào từng overload async cần điều phối.

## 4. Common pool: tiện lợi nhưng không phải pool của riêng ứng dụng

Hai lời gọi sau dùng common pool khi không truyền executor:

~~~java
CompletableFuture<User> user =
    CompletableFuture.supplyAsync(() -> repository.loadUser(id));

CompletableFuture<Void> audit =
    CompletableFuture.runAsync(() -> auditService.write(event));
~~~

Các async continuation không có tham số executor cũng dùng default asynchronous facility. Với CompletableFuture thông thường, đây là common pool.

Common pool hữu ích cho các tác vụ ngắn, độc lập và không block lâu. Nhưng cần cân nhắc khi pipeline có:

- truy vấn database hoặc gọi HTTP đồng bộ có thể chờ lâu;
- đọc/ghi file blocking;
- gọi dịch vụ bên ngoài có latency khó dự đoán;
- xử lý một lượng tác vụ lớn có thời gian chạy không đồng đều;
- yêu cầu cách ly một workload khỏi workload khác;
- yêu cầu queue, thread name, rejection hoặc shutdown riêng.

Nếu một worker trong pool dùng chung bị chặn lâu, năng lực thực thi của những task khác có thể giảm. Tách tác vụ I/O blocking sang executor riêng giúp giới hạn ảnh hưởng và cấu hình concurrency theo năng lực dịch vụ bên ngoài.

**Không cần thay common pool trong mọi trường hợp.** Nếu tác vụ nhỏ, không blocking và không có yêu cầu vận hành riêng, dùng default executor có thể hoàn toàn hợp lý. Chỉ tạo pool riêng khi có lý do về workload, isolation, capacity hoặc lifecycle.

## 5. Không nhầm thenApply với thenApplyAsync

Ví dụ:

~~~java
CompletableFuture<Integer> source =
    new CompletableFuture<Integer>();

CompletableFuture<String> inline =
    source.thenApply(value ->
        Thread.currentThread().getName());

CompletableFuture<String> async =
    source.thenApplyAsync(value ->
        Thread.currentThread().getName(), executor);

source.complete(42);
~~~

Nếu continuation thenApply được gắn trước khi source hoàn tất, nó có thể chạy ngay trong thread gọi source.complete(42). Continuation thenApplyAsync được gửi qua executor đã chỉ định.

Điều này ảnh hưởng đến:

- latency của thread hoàn tất stage trước;
- thread nào giữ lock hoặc đang xử lý request;
- thread context, ThreadLocal và tracing;
- việc callback có thể block luồng hoàn tất hay không.

**Đừng đổi mọi thenApply thành thenApplyAsync một cách máy móc.** Continuation đồng bộ rất hữu ích cho phép biến đổi nhỏ, nhanh, không blocking. Dùng async khi muốn chuyển workload sang executor hoặc cần cách ly công việc nặng/blocking.

## 6. Ví dụ 1 — điều khiển executor cho từng stage

Tệp **ExplicitExecutorDemo.java** dùng một ThreadPoolExecutor có một worker, queue giới hạn và tên thread riêng. Cả supplyAsync lẫn thenApplyAsync đều nhận cùng executor.

~~~java
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

public class ExplicitExecutorDemo {
    static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    static ThreadFactory namedFactory(final String prefix) {
        final AtomicInteger ids = new AtomicInteger();
        return task -> new Thread(
            task, prefix + "-" + ids.incrementAndGet());
    }

    public static void main(String[] args) throws Exception {
        ThreadPoolExecutor executor = new ThreadPoolExecutor(
            1, 1, 0L, TimeUnit.MILLISECONDS,
            new ArrayBlockingQueue<Runnable>(8),
            namedFactory("cf-worker"),
            new ThreadPoolExecutor.AbortPolicy());

        try {
            String trace = CompletableFuture
                .supplyAsync(
                    () -> Thread.currentThread().getName(),
                    executor)
                .thenApplyAsync(
                    source -> source + "|"
                        + Thread.currentThread().getName(),
                    executor)
                .join();

            String[] threads = trace.split("\\\\|");
            check(threads.length == 2, "two stages");
            check(threads[0].startsWith("cf-worker-"),
                "supplier executor");
            check(threads[1].startsWith("cf-worker-"),
                "continuation executor");

            System.out.println("supplierThread=" + threads[0]);
            System.out.println("continuationThread=" + threads[1]);
            System.out.println("explicitExecutorUsed=true");
            System.out.println("PASS");
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(2, TimeUnit.SECONDS)) {
                executor.shutdownNow();
                if (!executor.awaitTermination(2, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                        "executor did not terminate");
                }
            }
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 8 -encoding UTF-8 ExplicitExecutorDemo.java
java ExplicitExecutorDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
supplierThread=cf-worker-1
continuationThread=cf-worker-1
explicitExecutorUsed=true
PASS
~~~

Vì pool chỉ có một worker, hai stage chạy trên thread cf-worker-1. Tên thread xác nhận task được executor chỉ định thực thi; nó cũng giúp quan sát pool trong log và thread dump.

## 7. Ví dụ 2 — thấy rõ thread của thenApply và thenApplyAsync

Tệp **ContinuationThreadDemo.java** hoàn tất source future từ một thread có tên completion-thread. Continuation không async chạy trên thread hoàn tất source; continuation async chạy trên executor riêng.

~~~java
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

public class ContinuationThreadDemo {
    static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    static ThreadFactory namedFactory(final String prefix) {
        final AtomicInteger ids = new AtomicInteger();
        return task -> new Thread(
            task, prefix + "-" + ids.incrementAndGet());
    }

    public static void main(String[] args) throws Exception {
        ExecutorService executor =
            Executors.newSingleThreadExecutor(
                namedFactory("async-stage"));

        CompletableFuture<Integer> source =
            new CompletableFuture<Integer>();

        CompletableFuture<String> nonAsync =
            source.thenApply(
                value -> Thread.currentThread().getName());

        CompletableFuture<String> async =
            source.thenApplyAsync(
                value -> Thread.currentThread().getName(),
                executor);

        Thread completer = new Thread(
            () -> source.complete(42),
            "completion-thread");

        try {
            completer.start();
            completer.join();

            String inlineThread = nonAsync.join();
            String asyncThread = async.join();

            check("completion-thread".equals(inlineThread),
                "non-async continuation");
            check(asyncThread.startsWith("async-stage-"),
                "async continuation executor");

            System.out.println("thenApplyThread=" + inlineThread);
            System.out.println("thenApplyAsyncThread=" + asyncThread);
            System.out.println("differentExecutionContexts=true");
            System.out.println("PASS");
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(2, TimeUnit.SECONDS)) {
                executor.shutdownNow();
                if (!executor.awaitTermination(2, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                        "executor did not terminate");
                }
            }
        }
    }
}
~~~

~~~bash
javac --release 8 -encoding UTF-8 ContinuationThreadDemo.java
java ContinuationThreadDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
thenApplyThread=completion-thread
thenApplyAsyncThread=async-stage-1
differentExecutionContexts=true
PASS
~~~

Đây là lý do không nên đặt một callback nặng hoặc blocking vào thenApply nếu thread hoàn tất source cần phản hồi nhanh. Khi muốn chuyển việc đó sang pool, dùng overload async và truyền executor cụ thể.

## 8. Thiết kế ThreadPoolExecutor có giới hạn

ThreadPoolExecutor cho phép kiểm soát các tham số:

~~~java
ThreadPoolExecutor executor = new ThreadPoolExecutor(
    corePoolSize,
    maximumPoolSize,
    keepAliveTime,
    TimeUnit.SECONDS,
    new ArrayBlockingQueue<Runnable>(queueCapacity),
    threadFactory,
    new ThreadPoolExecutor.AbortPolicy()
);
~~~

| Tham số | Ý nghĩa |
| --- | --- |
| corePoolSize | Số worker cốt lõi pool duy trì theo chính sách |
| maximumPoolSize | Số worker tối đa |
| keepAliveTime | Thời gian worker vượt core được giữ khi idle |
| workQueue | Queue giữ task chờ worker |
| threadFactory | Tạo worker thread, đặt tên hoặc cấu hình cần thiết |
| RejectedExecutionHandler | Xử lý task không thể nhận vì pool shutdown hoặc đã đầy |

### Thứ tự nhận task

Với cấu hình ThreadPoolExecutor thông thường, quá trình nhận task diễn ra theo thứ tự:

1. Nếu số worker đang chạy nhỏ hơn core size, pool ưu tiên tạo worker mới.
2. Khi đã đạt core size, pool ưu tiên đưa task vào queue.
3. Nếu queue không nhận thêm được task, pool mới tăng worker lên tới maximum size.
4. Nếu queue đầy và đã đạt maximum size, task bị từ chối theo rejection handler.

Điều này giải thích một điểm dễ nhầm: **maximumPoolSize không nhất thiết được sử dụng ngay khi core worker bận**. Nếu queue vẫn nhận task, pool ưu tiên queue trước.

### Vì sao nên dùng queue có giới hạn?

Queue không giới hạn có thể tích lũy lượng task chờ rất lớn khi tốc độ gửi task vượt tốc độ xử lý. Điều này làm tăng bộ nhớ, độ trễ và thời gian chờ; cấu hình maximumPoolSize cũng thường không giúp tăng worker vượt core khi queue luôn nhận task.

Queue giới hạn như ArrayBlockingQueue đặt ra một capacity rõ. Khi tải vượt capacity, executor phải từ chối hoặc áp dụng một chính sách backpressure đã chọn. Kích thước queue nên dựa trên latency cho phép, tốc độ đến, thời gian xử lý và bộ nhớ; không chọn một con số tùy ý rồi coi đó là tối ưu.

## 9. Rejection policy và backpressure

Khi executor đã shutdown hoặc đã đạt giới hạn worker/queue, RejectedExecutionHandler quyết định cách xử lý task mới.

| Policy | Hành vi | Khi cân nhắc |
| --- | --- | --- |
| AbortPolicy | Ném RejectedExecutionException | Mặc định phù hợp khi cần biết task không được nhận |
| CallerRunsPolicy | Thread gọi execute chạy task nếu pool chưa shutdown | Có thể tạo feedback/backpressure bằng cách làm chậm caller |
| DiscardPolicy | Bỏ task im lặng | Chỉ phù hợp khi việc mất task đã được chấp nhận rõ |
| DiscardOldestPolicy | Bỏ task cũ nhất trong queue rồi thử nhận task mới | Hiếm khi phù hợp; cần hiểu hậu quả với task bị bỏ |

Với pipeline CompletableFuture, không nên chọn policy loại bỏ task một cách im lặng nếu phần còn lại của hệ thống đang chờ future hoàn tất. Nếu task bị discard mà future không được hoàn tất, bên chờ có thể chờ mãi. Chính sách từ chối cần được kiểm thử, ghi nhận và thiết kế theo contract của ứng dụng.

CallerRunsPolicy có thể làm task chạy ngay trên thread gửi task. Khi task được gửi từ thread đang hoàn tất một stage, callback có thể chạy inline trên thread đó, kéo dài thời gian hoàn tất. Đây là backpressure có chủ đích nhưng phải tính đến thread context và latency.

**Không tăng maximumPoolSize vô hạn để tránh rejection.** Thread không miễn phí; tạo quá nhiều worker có thể gây context switching, tranh chấp CPU, áp lực bộ nhớ và làm quá tải database/dịch vụ downstream.

## 10. Ví dụ 3 — queue đầy thì AbortPolicy từ chối task

Tệp **BoundedQueueRejectionDemo.java** cấu hình một worker và queue chỉ chứa được một task. Task đầu tiên bị giữ bằng latch, task thứ hai nằm trong queue, task thứ ba bị từ chối.

~~~java
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

public class BoundedQueueRejectionDemo {
    static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    static ThreadFactory namedFactory() {
        final AtomicInteger ids = new AtomicInteger();
        return task -> new Thread(
            task, "bounded-worker-" + ids.incrementAndGet());
    }

    public static void main(String[] args) throws Exception {
        ThreadPoolExecutor executor = new ThreadPoolExecutor(
            1, 1, 0L, TimeUnit.MILLISECONDS,
            new ArrayBlockingQueue<Runnable>(1),
            namedFactory(),
            new ThreadPoolExecutor.AbortPolicy());

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        boolean rejected = false;
        boolean firstStarted = false;
        int queued;

        try {
            executor.execute(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            });

            firstStarted = started.await(2, TimeUnit.SECONDS);
            check(firstStarted, "first task started");

            executor.execute(() -> { });
            queued = executor.getQueue().size();

            try {
                executor.execute(() -> { });
            } catch (RejectedExecutionException expected) {
                rejected = true;
            }

            check(queued == 1, "one queued task");
            check(rejected, "third task rejected");

            System.out.println("firstTaskStarted=" + firstStarted);
            System.out.println("queuedTasks=" + queued);
            System.out.println("thirdTaskRejected=" + rejected);
            System.out.println("PASS");
        } finally {
            release.countDown();
            executor.shutdown();
            if (!executor.awaitTermination(2, TimeUnit.SECONDS)) {
                executor.shutdownNow();
                if (!executor.awaitTermination(2, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                        "executor did not terminate");
                }
            }
        }
    }
}
~~~

~~~bash
javac --release 8 -encoding UTF-8 BoundedQueueRejectionDemo.java
java BoundedQueueRejectionDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
firstTaskStarted=true
queuedTasks=1
thirdTaskRejected=true
PASS
~~~

Bài test chứng minh capacity có hiệu lực: một task đang chạy, một task đang chờ, task tiếp theo bị từ chối. Latch bảo đảm tình huống bão hòa được tạo có kiểm soát, không phụ thuộc timing bằng Thread.sleep().

### Rejection khi gọi CompletableFuture

Các phương thức async cần gửi task vào executor. Nếu executor không nhận task, ứng dụng phải xử lý tình huống đó như một phần của vận hành pipeline. Không giả định queue luôn còn chỗ hoặc pool luôn đang chạy. Dùng AbortPolicy giúp tình trạng từ chối không bị che giấu; viết test cho đúng overload và runtime đang dùng nếu logic ứng dụng phụ thuộc cách rejection được phản ánh qua future.

## 11. Tách executor theo loại workload

Một mô hình phổ biến là dùng pool riêng cho tác vụ I/O blocking và tác vụ CPU-bound:

~~~java
CompletableFuture.supplyAsync(
    () -> repository.loadOrder(id),
    ioExecutor
).thenApplyAsync(
    order -> calculateTotals(order),
    cpuExecutor
).thenAcceptAsync(
    result -> notifyClient(result),
    notificationExecutor
);
~~~

Lý do:

- I/O có thể chờ socket, database hoặc dịch vụ bên ngoài; worker có thể bị giữ trong thời gian chờ.
- CPU transformation tiêu thụ CPU và cần được điều phối để không bị tác vụ blocking chiếm hết worker.
- Notification có thể có throughput, rate limit hoặc latency riêng.
- Tách pool tạo giới hạn và quan sát riêng cho từng loại tải.

Không nhất thiết phải có một pool cho mỗi stage. Quá nhiều pool làm tăng phức tạp, worker và queue. Tạo pool theo **ranh giới workload có ý nghĩa**, chẳng hạn database I/O, CPU transform và callback outbound.

### Sizing pool

Không có một công thức thread count đúng cho mọi ứng dụng:

- CPU-bound thường bắt đầu thử quanh số processor khả dụng, sau đó đo throughput/latency.
- I/O-bound có thể cần nhiều thread hơn số core vì worker dành thời gian chờ, nhưng phải tôn trọng connection limit, rate limit và khả năng của downstream.
- Queue cần cân bằng giữa burst absorption và thời gian chờ tối đa.
- Nếu task có latency dài hoặc không kiểm soát, cần timeout, concurrency limit và rejection policy.

Theo dõi các chỉ số như active thread count, pool size, queue size, task count, completed count, rejection count và latency. Dùng số liệu production/test tải để điều chỉnh thay vì dựa trên một con số mẫu.

## 12. Ví dụ 4 — I/O và CPU chạy trên hai executor khác nhau

Tệp **WorkloadExecutorsDemo.java** dùng pool tên io-worker để tạo dữ liệu và pool cpu-worker để biến đổi dữ liệu. Cả hai stage đều truyền executor rõ ràng.

~~~java
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.Locale;

public class WorkloadExecutorsDemo {
    static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    static ThreadFactory namedFactory(final String prefix) {
        final AtomicInteger ids = new AtomicInteger();
        return task -> new Thread(
            task, prefix + "-" + ids.incrementAndGet());
    }

    static ThreadPoolExecutor pool(String prefix) {
        return new ThreadPoolExecutor(
            1, 1, 0L, TimeUnit.MILLISECONDS,
            new ArrayBlockingQueue<Runnable>(8),
            namedFactory(prefix),
            new ThreadPoolExecutor.AbortPolicy());
    }

    static void stop(ExecutorService executor)
            throws InterruptedException {
        executor.shutdown();
        if (!executor.awaitTermination(2, TimeUnit.SECONDS)) {
            executor.shutdownNow();
            if (!executor.awaitTermination(2, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                    "executor did not terminate");
            }
        }
    }

    public static void main(String[] args) throws Exception {
        ThreadPoolExecutor ioExecutor = pool("io-worker");
        ThreadPoolExecutor cpuExecutor = pool("cpu-worker");

        try {
            String trace = CompletableFuture
                .supplyAsync(
                    () -> Thread.currentThread().getName()
                        + "|payload",
                    ioExecutor)
                .thenApplyAsync(input ->
                    input.substring(0, input.indexOf('|')) + "|"
                    + Thread.currentThread().getName() + "|"
                    + input.substring(input.indexOf('|') + 1)
                        .toUpperCase(Locale.ROOT),
                    cpuExecutor)
                .join();

            String[] parts = trace.split("\\\\|");
            check(parts.length == 3, "trace shape");
            check(parts[0].startsWith("io-worker-"), "I/O stage");
            check(parts[1].startsWith("cpu-worker-"), "CPU stage");
            check("PAYLOAD".equals(parts[2]), "transformed result");

            System.out.println("ioThread=" + parts[0]);
            System.out.println("cpuThread=" + parts[1]);
            System.out.println("result=" + parts[2]);
            System.out.println("separateExecutors=true");
            System.out.println("PASS");
        } finally {
            stop(ioExecutor);
            stop(cpuExecutor);
        }
    }
}
~~~

~~~bash
javac --release 8 -encoding UTF-8 WorkloadExecutorsDemo.java
java WorkloadExecutorsDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
ioThread=io-worker-1
cpuThread=cpu-worker-1
result=PAYLOAD
separateExecutors=true
PASS
~~~

Ví dụ không truy cập database thật; tên thread cho thấy stage đầu và stage sau được gửi tới hai executor khác nhau. Trong ứng dụng, thay phần tạo chuỗi bằng I/O thật và phần uppercase bằng phép tính CPU thực tế.

## 13. ThreadFactory: đặt tên và cấu hình worker

ThreadFactory quyết định cách pool tạo thread. Đặt tên có ích khi đọc thread dump, log và metrics:

~~~java
AtomicInteger ids = new AtomicInteger();

ThreadFactory factory = task ->
    new Thread(task, "orders-io-" + ids.incrementAndGet());
~~~

Nên đặt tên phản ánh workload hoặc thành phần sở hữu pool, ví dụ orders-db-1 cho database I/O, image-cpu-1 cho xử lý ảnh CPU và notification-1 cho gửi thông báo.

Có thể cấu hình uncaught exception handler, daemon status hoặc priority khi có lý do rõ ràng. Tránh thay đổi priority tùy tiện. Thread daemon cho phép JVM kết thúc dù worker còn sống; điều đó có thể làm task chưa hoàn tất bị dừng khi process thoát. Với executor do ứng dụng quản lý, nên shutdown có trật tự thay vì dựa vào daemon thread.

Tên thread không thay thế tracing context. ThreadLocal không tự được sao chép qua mọi stage async. Nếu cần request ID, security context hoặc tracing span, hãy truyền context tường minh hoặc dùng cơ chế context propagation được framework hỗ trợ.

## 14. Vòng đời executor: tạo một lần, tái sử dụng và đóng đúng lúc

Một executor thuộc về **lifecycle của thành phần tạo ra nó**, chẳng hạn service, application context hoặc một subsystem. Không tạo một pool mới cho mỗi request hoặc mỗi CompletableFuture; điều đó làm tăng thread, queue và chi phí khởi động, đồng thời khó shutdown.

Mô hình lifecycle:

~~~text
Application/service start
       |
       v
Tạo executor và cấu hình pool
       |
       v
Nhận các task / CompletableFuture pipeline
       |
       v
Ngừng nhận công việc mới
       |
       v
executor.shutdown()
       |
       v
awaitTermination(timeout)
       |
       +---- hoàn tất -> service shutdown
       |
       +---- timeout -> shutdownNow() theo policy
~~~

shutdown() ngừng nhận task mới nhưng cho phép task đã nhận tiếp tục chạy. Nó **không đợi** các task hoàn tất. Dùng awaitTermination() để chờ trong thời hạn xác định.

shutdownNow() cố gắng dừng task đang chạy, ngừng xử lý task đang chờ và trả về danh sách task chưa bắt đầu. Đây là nỗ lực best-effort; task phải hợp tác với interruption mới dừng đúng cách.

### Helper shutdown hai pha

~~~java
static void shutdownAndAwaitTermination(
        ExecutorService executor) {
    executor.shutdown();
    try {
        if (!executor.awaitTermination(30, TimeUnit.SECONDS)) {
            executor.shutdownNow();
            if (!executor.awaitTermination(30, TimeUnit.SECONDS)) {
                System.err.println("Executor did not terminate");
            }
        }
    } catch (InterruptedException ex) {
        executor.shutdownNow();
        Thread.currentThread().interrupt();
    }
}
~~~

Thời hạn 30 giây chỉ là ví dụ; chọn timeout theo SLA và cách ứng dụng shutdown. Nếu thread bị interrupt, gọi shutdownNow theo policy và khôi phục interrupt flag bằng Thread.currentThread().interrupt().

**Không gọi shutdown executor dùng chung sau mỗi future.** Nếu nhiều service cùng sử dụng một pool, phải có owner/lifecycle coordinator rõ ràng để tránh một component đóng pool khi component khác vẫn cần gửi task.

## 15. Ví dụ 5 — shutdown vẫn cho task đã nhận hoàn tất

Tệp **ExecutorShutdownDemo.java** gửi một task vào executor, gọi shutdown ngay sau khi task được nhận, rồi xác nhận task hoàn tất và pool kết thúc. Task mới sau shutdown bị từ chối.

~~~java
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

public class ExecutorShutdownDemo {
    static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    static ThreadFactory namedFactory() {
        final AtomicInteger ids = new AtomicInteger();
        return task -> new Thread(
            task, "shutdown-worker-" + ids.incrementAndGet());
    }

    public static void main(String[] args) throws Exception {
        ThreadPoolExecutor executor = new ThreadPoolExecutor(
            1, 1, 0L, TimeUnit.MILLISECONDS,
            new ArrayBlockingQueue<Runnable>(4),
            namedFactory(),
            new ThreadPoolExecutor.AbortPolicy());

        try {
            CompletableFuture<String> accepted =
                CompletableFuture.supplyAsync(
                    () -> "completed@"
                        + Thread.currentThread().getName(),
                    executor);

            executor.shutdown();

            String result = accepted.join();
            boolean terminated =
                executor.awaitTermination(2, TimeUnit.SECONDS);

            boolean rejectedAfterShutdown = false;
            try {
                executor.execute(() -> { });
            } catch (RejectedExecutionException expected) {
                rejectedAfterShutdown = true;
            }

            check(result.startsWith("completed@shutdown-worker-"),
                "accepted task completed");
            check(terminated, "executor terminated");
            check(rejectedAfterShutdown,
                "new task rejected after shutdown");

            System.out.println("acceptedTask=" + result);
            System.out.println("terminated=" + terminated);
            System.out.println("newTaskRejectedAfterShutdown="
                + rejectedAfterShutdown);
            System.out.println("PASS");
        } finally {
            if (!executor.isShutdown()) executor.shutdown();
            if (!executor.awaitTermination(2, TimeUnit.SECONDS)) {
                executor.shutdownNow();
                if (!executor.awaitTermination(2, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                        "executor did not terminate");
                }
            }
        }
    }
}
~~~

~~~bash
javac --release 8 -encoding UTF-8 ExecutorShutdownDemo.java
java ExecutorShutdownDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
acceptedTask=completed@shutdown-worker-1
terminated=true
newTaskRejectedAfterShutdown=true
PASS
~~~

Task đã được nhận trước shutdown vẫn chạy. Sau shutdown, executor không nhận task mới. Trong ứng dụng thật, phải dừng luồng tạo task mới trước khi đóng executor để tránh rejection trong thời gian shutdown.

## 16. Xử lý lỗi trong pipeline và executor

Nếu một stage hoàn tất exceptionally, các continuation yêu cầu kết quả bình thường như thenApply sẽ không chạy. Lỗi được truyền tiếp trong pipeline cho tới khi có stage xử lý.

Các API quan trọng:

| API | Khi nào chạy | Mục đích |
| --- | --- | --- |
| exceptionally(fn) | Khi stage trước lỗi | Chuyển lỗi thành kết quả fallback |
| handle(fn) | Thành công hoặc thất bại | Biến đổi dựa trên value/error |
| whenComplete(action) | Thành công hoặc thất bại | Quan sát kết quả/lỗi, thường dùng side effect |
| handleAsync(fn, executor) | Thành công hoặc thất bại, qua executor | Recovery/transform có kiểm soát thread |
| whenCompleteAsync(action, executor) | Thành công hoặc thất bại, qua executor | Callback quan sát trên pool chỉ định |

Ví dụ recovery:

~~~java
CompletableFuture<String> result =
    CompletableFuture.supplyAsync(
        () -> remoteService.fetch(),
        ioExecutor
    ).handleAsync((value, error) -> {
        if (error != null) {
            return "fallback";
        }
        return value;
    }, recoveryExecutor);
~~~

Cần phân biệt lỗi của tác vụ với lỗi gửi task vào executor. Pool có thể từ chối task vì đã shutdown hoặc bão hòa. Chính sách rejection phải rõ ràng và được quan sát; không coi việc queue đầy là một tình huống không thể xảy ra.

Khi debug, unwrap CompletionException hoặc ExecutionException nếu cần tìm cause gốc. Không bỏ qua exception rồi trả fallback chung mà không ghi nhận, nếu điều đó làm mất khả năng phát hiện lỗi vận hành.

## 17. Ví dụ 6 — recovery stage chạy trên executor chỉ định

Tệp **CompletableFutureRecoveryDemo.java** tạo lỗi trong supplier, dùng thenApplyAsync (sẽ không chạy do stage trước lỗi) và handleAsync để khôi phục kết quả trên executor riêng.

~~~java
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

public class CompletableFutureRecoveryDemo {
    static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    static ThreadFactory namedFactory() {
        final AtomicInteger ids = new AtomicInteger();
        return task -> new Thread(
            task, "recovery-worker-" + ids.incrementAndGet());
    }

    public static void main(String[] args) throws Exception {
        ExecutorService executor =
            Executors.newSingleThreadExecutor(namedFactory());

        try {
            String result = CompletableFuture
                .supplyAsync(() -> {
                    throw new IllegalStateException(
                        "service unavailable");
                }, executor)
                .thenApplyAsync(
                    value -> "value=" + value,
                    executor)
                .handleAsync((value, error) -> {
                    if (error == null) return value;

                    Throwable cause = error;
                    while (cause instanceof CompletionException
                            && cause.getCause() != null) {
                        cause = cause.getCause();
                    }
                    return "recovered:" + cause.getMessage();
                }, executor)
                .join();

            check("recovered:service unavailable".equals(result),
                "exception recovery");

            System.out.println("result=" + result);
            System.out.println("recoveredOnExplicitExecutor=true");
            System.out.println("PASS");
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(2, TimeUnit.SECONDS)) {
                executor.shutdownNow();
                if (!executor.awaitTermination(2, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                        "executor did not terminate");
                }
            }
        }
    }
}
~~~

~~~bash
javac --release 8 -encoding UTF-8 CompletableFutureRecoveryDemo.java
java CompletableFutureRecoveryDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
result=recovered:service unavailable
recoveredOnExplicitExecutor=true
PASS
~~~

handleAsync nhận cả kết quả và lỗi. Nếu có lỗi, ví dụ unwrap CompletionException rồi trả fallback. Trong production, recovery cần quyết định rõ lỗi nào retry được, lỗi nào phải propagate, và fallback nào có ý nghĩa nghiệp vụ.

## 18. join/get và nguy cơ tự làm nghẽn pool

join() và get() là thao tác chờ kết quả. Dùng chúng ở ranh giới đồng bộ như main/test hoặc adapter bắt buộc trả kết quả đồng bộ có thể hợp lý. Nhưng nếu worker của pool đang chạy một stage rồi lại chờ một future khác cũng cần cùng pool nhỏ để chạy, hệ thống có thể tự nghẽn.

Ví dụ ý tưởng cần tránh:

~~~java
// Anti-pattern khi chạy bên trong worker của pool nhỏ.
CompletableFuture.supplyAsync(() -> {
    return anotherFuture.join();
}, sameSmallExecutor);
~~~

Nếu tất cả worker đều block chờ task xếp trong queue của chính pool, không còn worker nào rảnh để chạy task cần thiết. Đây là một dạng thread starvation/deadlock do thiết kế phụ thuộc.

Ưu tiên nối pipeline bằng thenCompose, thenCombine và các continuation phù hợp thay vì chặn worker để chờ một stage khác. Nếu phải chờ đồng bộ, xác định rõ pool nào chạy task được chờ và pool nào đang block.

## 19. Cancellation và timeout không tự giải quyết vòng đời task

CompletableFuture.cancel(...) hoàn tất future theo trạng thái cancellation/exceptional completion. Vì CompletableFuture không trực tiếp sở hữu computation như một FutureTask thông thường, không nên giả định việc cancel luôn interrupt thread đang thực thi supplier.

Tác vụ blocking cần timeout riêng ở API I/O (ví dụ timeout của client/database), hoặc cơ chế cancellation token/interruption mà chính task kiểm tra. Đừng giữ worker vô hạn trong một call không có timeout.

Trong Java 8, CompletableFuture chưa có các tiện ích timeout được bổ sung ở những phiên bản Java sau; nếu code phải chạy Java 8, thiết kế timeout bằng API và scheduler tương thích Java 8. Không sao chép API chỉ có từ JDK mới vào module Java 8.

## 20. ThreadLocal và context propagation qua executor

Một request thường có context như correlation ID, trace ID, tenant ID hoặc security context. ThreadLocal gắn dữ liệu với thread hiện tại; khi CompletableFuture chuyển sang worker khác, dữ liệu đó không tự được chuyển sang.

Không nên giả định:

~~~java
requestContext.set(context);
CompletableFuture.supplyAsync(this::work, executor);
~~~

sẽ làm requestContext.get() bên trong worker trả cùng context.

Các hướng xử lý phù hợp:

- truyền context thành tham số rõ ràng vào từng stage;
- tạo immutable context object và capture nó trước khi submit;
- dùng executor wrapper/context propagation library được framework hỗ trợ;
- khôi phục và xóa context trong finally nếu dùng ThreadLocal wrapper.

Đặc biệt, pool tái sử dụng worker. Nếu set ThreadLocal nhưng không xóa đúng lúc, request sau có thể đọc dữ liệu của request trước. Không dùng ThreadLocal để truyền security data một cách ngầm định mà không có quy trình cleanup.

## 21. Quan sát và kiểm thử executor

Đặt tên thread giúp đọc log, nhưng vận hành pool cần thêm chỉ số:

| Chỉ số | Câu hỏi cần trả lời |
| --- | --- |
| Pool size | Hiện có bao nhiêu worker? |
| Active count | Có bao nhiêu worker đang bận? |
| Queue size | Có bao nhiêu task đang chờ? |
| Completed task count | Pool đã hoàn thành bao nhiêu task? |
| Task count | Tổng số task đã được lên lịch xấp xỉ bao nhiêu? |
| Rejection count | Có bao nhiêu task không được nhận? |
| Task latency | Task chờ queue bao lâu và chạy bao lâu? |
| Error rate | Bao nhiêu task hoàn tất exceptionally? |

ThreadPoolExecutor cung cấp một số metric gần đúng như getActiveCount(), getPoolSize(), getQueue().size(), getTaskCount() và getCompletedTaskCount(). Đây là số liệu quan sát, không phải phép đo transaction chính xác tuyệt đối. Có thể bọc executor hoặc instrument task để đo queue wait và execution time.

### Kiểm thử thread thực thi

Một test đơn giản có thể trả tên thread từ mỗi stage, như ví dụ 1–4. Với logic phức tạp hơn:

- dùng latch/barrier để đồng bộ test, tránh sleep;
- kiểm tra stage được gửi đúng executor;
- kiểm tra queue capacity và rejection;
- kiểm tra shutdown không nhận task mới nhưng hoàn tất task đã nhận;
- kiểm tra exception được propagate/recover;
- kiểm tra không còn worker sau khi test đóng pool;
- không assert thứ tự thread nếu pool có nhiều worker và thứ tự không phải hợp đồng.

Test không nên dùng Thread.sleep() để hy vọng một task đã chạy. Dùng CountDownLatch, CyclicBarrier hoặc hoàn tất future để chờ điều kiện cụ thể.

## 22. Những lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Gọi supplyAsync không executor cho tác vụ blocking dài | Chiếm common pool dùng chung | Tạo executor riêng theo workload |
| Chỉ gắn executor ở stage đầu | Continuation async sau đó vẫn dùng default facility nếu không truyền executor | Truyền executor ở từng stage async cần kiểm soát |
| Nghĩ thenApply luôn chạy trên pool | Có thể chạy trên thread hoàn tất source | Dùng thenApplyAsync(fn, executor) khi cần chuyển thread |
| Nghĩ mọi Executor đều bất đồng bộ | Direct executor có thể chạy trong caller | Chọn executor có worker thread thực sự |
| Dùng unbounded queue | Task backlog và memory có thể tăng không giới hạn | Bounded queue và rejection policy |
| Nghĩ maximumPoolSize tăng ngay khi core bận | Pool ưu tiên queue trước | Hiểu thứ tự core → queue → max → reject |
| Dùng DiscardPolicy cho pipeline cần kết quả | Future có thể không hoàn tất nếu task bị bỏ | Dùng rejection rõ ràng và xử lý lỗi |
| Dùng CallerRuns mà không xem thread gọi | Callback có thể chạy inline và tăng latency | Đánh giá backpressure/thread context |
| Tạo pool cho mỗi request | Tạo quá nhiều worker, khó shutdown | Pool được sở hữu bởi service/application |
| CompletableFuture hoàn tất thì pool tự đóng | Worker có thể sống mãi | Owner gọi shutdown/awaitTermination |
| Gọi shutdown sau mỗi future | Request khác mất khả năng submit task | Đóng pool theo lifecycle owner |
| Block bằng join bên trong pool nhỏ | Starvation hoặc deadlock | Nối stage không blocking |
| Dùng chung pool cho I/O và CPU không cân nhắc | Workload có thể ảnh hưởng lẫn nhau | Tách pool khi isolation có lợi |
| Không timeout tác vụ I/O | Worker bị giữ vô hạn | Timeout ở client/downstream và cancellation hợp tác |
| Dựa vào ThreadLocal qua async stage | Context mất hoặc rò giữa request | Truyền context/propagate và cleanup |
| Không xử lý RejectedExecutionException | Mất task hoặc lỗi submit không được quan sát | Thiết kế và test saturation/shutdown |
| Chỉ xem pool size | Không biết backlog/latency | Theo dõi active, queue, rejection và task latency |
| Dùng sleep trong test concurrency | Test flaky | Latch/barrier/future completion |

## 23. Ma trận quyết định executor

| Tình huống | Cách chọn |
| --- | --- |
| Tác vụ ngắn, không blocking, không cần isolation | Có thể dùng default common pool |
| Tác vụ database/JDBC blocking | Executor riêng với concurrency giới hạn theo connection pool |
| HTTP client blocking | Pool riêng và timeout/rate limit theo downstream |
| CPU transformation nặng | Pool CPU có số worker được đo theo tài nguyên |
| Gửi notification | Pool riêng nếu cần giới hạn tốc độ và cô lập |
| Stage đồng bộ nhỏ | thenApply/thenAccept nếu chấp nhận thread hoàn tất thực thi |
| Stage nặng cần tách thread | thenApplyAsync(fn, executor) |
| Task queue có thể tăng đột biến | Bounded queue và policy rejection rõ |
| Ứng dụng shutdown | Dừng submit, shutdown, await, escalation theo policy |

## 24. Bài tập thực hành có đáp án

### Bài 1 — executor mặc định

**Đề:** CompletableFuture.supplyAsync(() -> load()) dùng executor nào?

**Đáp án:** Static overload không nhận executor dùng ForkJoinPool.commonPool() theo JavaDoc.

### Bài 2 — chỉ định executor

**Đề:** Muốn chạy supplier trên pool riêng, dùng overload nào?

**Đáp án:** CompletableFuture.supplyAsync(supplier, executor).

### Bài 3 — continuation

**Đề:** thenApply(fn) có đảm bảo chạy ở thread khác không?

**Đáp án:** Không. Nó có thể chạy trên thread hoàn tất stage trước hoặc thread gọi completion. Dùng thenApplyAsync(fn, executor) khi cần điều phối qua executor.

### Bài 4 — stage tiếp theo

**Đề:** Đã truyền executor cho supplyAsync. thenApplyAsync(fn) sau đó có tự kế thừa executor không?

**Đáp án:** Không nên giả định. Overload không executor dùng default async facility; truyền executor vào từng stage cần kiểm soát.

### Bài 5 — Executor trực tiếp

**Đề:** Một implementation Executor gọi command.run() trong execute() có thể khiến async stage chạy trên caller không?

**Đáp án:** Có. Executor interface không bắt buộc thực thi bất đồng bộ; implementation quyết định execution policy.

### Bài 6 — bounded queue

**Đề:** Một ThreadPoolExecutor có một worker và queue capacity một. Worker đang bận, task thứ hai xếp queue. Task thứ ba làm gì với AbortPolicy?

**Đáp án:** Bị từ chối bằng RejectedExecutionException.

### Bài 7 — core và maximum

**Đề:** Khi core worker đã bận nhưng queue còn chỗ, pool có lập tức tạo worker tới maximum không?

**Đáp án:** Không. ThreadPoolExecutor ưu tiên queue trước; chỉ tăng worker vượt core khi queue không nhận task.

### Bài 8 — CallerRunsPolicy

**Đề:** Pool bão hòa, CallerRunsPolicy có thể làm stage chạy ở thread nào?

**Đáp án:** Thread gọi execute() có thể chạy task, nếu pool chưa shutdown. Đây là backpressure nhưng có thể ảnh hưởng latency/thread context.

### Bài 9 — shutdown

**Đề:** shutdown() có đợi task hoàn tất không?

**Đáp án:** Không. Nó ngừng nhận task mới và cho task đã nhận tiếp tục. Dùng awaitTermination() để chờ.

### Bài 10 — shutdownNow

**Đề:** shutdownNow() có bảo đảm task đang chạy dừng ngay lập tức không?

**Đáp án:** Không. Nó cố interrupt task và ngừng task đang chờ; task phải hợp tác với interruption.

### Bài 11 — pool ownership

**Đề:** Một CompletableFuture dùng executor của service. Khi future hoàn tất, ai đóng executor?

**Đáp án:** Thành phần sở hữu executor theo lifecycle service/application; CompletableFuture không tự shutdown pool.

### Bài 12 — common pool và I/O

**Đề:** Một stage gọi API blocking lâu. Có nên mặc định gửi vào common pool không?

**Đáp án:** Cần cân nhắc. Executor riêng giúp cách ly tác vụ blocking và giới hạn concurrency theo dịch vụ downstream.

### Bài 13 — queue không giới hạn

**Đề:** Queue unbounded có thể gây vấn đề gì?

**Đáp án:** Backlog và bộ nhớ có thể tăng lớn; maximumPoolSize thường không tăng worker vượt core khi queue luôn nhận task.

### Bài 14 — exception

**Đề:** Muốn recovery stage chạy trên executor riêng, dùng API nào?

**Đáp án:** handleAsync(fn, executor) hoặc exceptionally/cách xử lý phù hợp; Java 8 có handleAsync nhận executor.

### Bài 15 — ThreadLocal

**Đề:** ThreadLocal của request có tự được chuyển sang worker trong CompletableFuture không?

**Đáp án:** Không. Truyền context tường minh hoặc dùng cơ chế propagation và cleanup phù hợp.

### Bài 16 — test concurrency

**Đề:** Vì sao dùng Thread.sleep() để test queue đầy không đáng tin?

**Đáp án:** Timing phụ thuộc máy và scheduler. Dùng latch để xác nhận worker đang bận trước khi lấp queue và kiểm rejection.

## 25. Câu hỏi tự đánh giá

**1.** Executor nằm trong package nào? — java.util.concurrent.

**2.** Executor có phương thức cốt lõi nào? — execute(Runnable).

**3.** Executor có bắt buộc chạy task ở thread khác không? — Không.

**4.** CompletableFuture supplyAsync không executor dùng gì? — Common pool.

**5.** Overload có executor là gì? — supplyAsync(supplier, executor).

**6.** thenApply và thenApplyAsync khác gì? — thenApply không yêu cầu executor async; thenApplyAsync dùng default facility hoặc executor được truyền.

**7.** Executor của stage đầu có tự áp dụng cho tất cả stage sau không? — Không.

**8.** ThreadPoolExecutor có những tham số giới hạn chính nào? — core, maximum, queue, keepAlive, ThreadFactory và rejection handler.

**9.** Vì sao queue nên có giới hạn? — Kiểm soát backlog, latency và memory.

**10.** AbortPolicy làm gì? — Ném RejectedExecutionException.

**11.** CallerRunsPolicy có thể tạo hiệu ứng gì? — Backpressure bằng cách cho caller chạy task.

**12.** DiscardPolicy có rủi ro gì với CompletableFuture? — Task có thể bị bỏ im lặng khiến future chờ hoàn tất mãi.

**13.** Vì sao tách I/O và CPU executor? — Cách ly workload có đặc tính blocking và tài nguyên khác nhau.

**14.** shutdown có chờ task hoàn tất không? — Không.

**15.** Cách chờ pool kết thúc? — awaitTermination.

**16.** CompletableFuture có tự đóng executor truyền vào không? — Không.

**17.** Vì sao không join bên trong worker pool nhỏ? — Có thể làm cạn worker và gây starvation/deadlock.

**18.** ThreadLocal có tự truyền qua stage async không? — Không.

**19.** Dùng gì để test task bắt đầu trước khi lấp queue? — CountDownLatch hoặc primitive đồng bộ phù hợp.

**20.** Cần quan sát metric nào ngoài pool size? — Active count, queue size, rejection, task count, completed count và latency.

## Tài liệu chính thức

- [Java SE 8 — CompletableFuture](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/CompletableFuture.html) — supplyAsync, runAsync, các continuation async và overload nhận Executor.
- [Java SE 26 — CompletableFuture](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CompletableFuture.html) — default asynchronous facility, common pool và API hiện hành.
- [Java SE 8 — Executor](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/Executor.html) — execution policy và hợp đồng execute.
- [Java SE 8 — ExecutorService](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/ExecutorService.html) — submit, shutdown, awaitTermination và lifecycle.
- [Java SE 8 — ThreadPoolExecutor](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/ThreadPoolExecutor.html) — core/max, queue, ThreadFactory và rejection policies.
- [Java SE 26 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html) — queue strategy, saturation, rejection và shutdown.
- [Java SE 8 — RejectedExecutionHandler](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/RejectedExecutionHandler.html) — xử lý task không thể nhận.
- [Java SE 8 — ThreadFactory](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/ThreadFactory.html) — tạo worker thread.
- [Java SE 8 — CompletionStage](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/CompletionStage.html) — semantics của continuation và exceptional completion.

**Ghi nhớ:** CompletableFuture mô tả luồng kết quả; Executor quyết định task được điều phối ra sao. Dùng overload async có executor khi cần kiểm soát thread của stage. thenApply có thể chạy trên thread hoàn tất stage trước, còn overload async không chỉ định executor dùng default facility. Pool riêng cần queue có giới hạn, rejection policy phù hợp và owner chịu trách nhiệm shutdown. Tách I/O blocking khỏi CPU work khi cần isolation; nối stage thay vì block worker bằng join; kiểm thử queue, thread và lifecycle bằng latch/future thay vì timing tùy ý.