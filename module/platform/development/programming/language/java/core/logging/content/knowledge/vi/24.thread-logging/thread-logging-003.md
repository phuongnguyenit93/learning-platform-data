# Log trong thread pool (Java 17+)

## 1. Vì sao log trong thread pool dễ gây nhầm lẫn?

`Thread pool` là tập các thread được tái sử dụng để chạy nhiều tác vụ (task). Với `ExecutorService`, thread gọi `submit()` hoặc `execute()` chỉ **gửi công việc**; tác vụ thực tế có thể chạy trên một worker khác, tại thời điểm khác. Khi số task lớn hơn số worker, các task còn phải chờ trong hàng đợi.

Ba hệ quả quan trọng đối với logging:

- **Log xen kẽ:** log của hai task có thể xuất hiện đan xen; thứ tự giữa các task không nhất thiết giống thứ tự gửi việc.
- **Worker được tái sử dụng:** cùng tên thread (ví dụ `log-worker-1`) có thể xử lý lần lượt nhiều request hoặc job khác nhau. Không thể dùng riêng tên thread để suy ra request nào tạo log.
- **Context gắn với thread có thể bị sót:** `ThreadLocal`, MDC hoặc thông tin truy vết khác không tự động đi theo task từ thread gửi việc sang worker. Nếu quên dọn, context của task cũ có thể xuất hiện trong log task mới.

Ví dụ một pool có hai worker xử lý ba job A, B, C: A và B có thể chạy cùng lúc; C chờ worker rảnh rồi chạy trên chính thread vừa xử lý A hoặc B. Log `start(A)`, `start(B)`, `end(A)`, `start(C)` là một khả năng, nhưng không phải thứ tự được bảo đảm.

**Nguyên tắc:** mỗi dòng log quan trọng phải cho biết *sự kiện gì*, *thuộc task/request nào*, *xảy ra ở worker nào* và *thành công hay lỗi*. Không suy luận ngữ cảnh chỉ từ thứ tự dòng log hoặc tên thread.

## 2. Những trường nên ghi và vị trí ghi

Một bản ghi tác vụ thường hữu ích với các trường sau:

| Trường | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `event` | Tên sự kiện: `task_submitted`, `task_started`, `task_succeeded`, `task_failed` | Dùng tên ổn định để tìm kiếm và lập cảnh báo |
| `taskId` / `jobId` | Định danh riêng của một lần chạy task | Không dùng tên thread thay thế |
| `requestId` / `traceId` | Ghép log với yêu cầu hoặc trace ở nhiều thành phần | Phải truyền qua ranh giới async hoặc thiết lập lại ở worker |
| `worker` | `Thread.currentThread().getName()` | Hữu ích khi điều tra lịch chạy, không phải định danh nghiệp vụ |
| `elapsedMs` / `queueWaitMs` | Thời gian xử lý và thời gian đợi trong hàng đợi | Đo khoảng thời gian bằng `System.nanoTime()` |
| `outcome` và exception | Kết quả và stack trace khi thất bại | Log exception tại một ranh giới xử lý đã chọn, tránh log trùng |

Nên có log ở thời điểm **gửi task**, **bắt đầu chạy**, **kết thúc** và **thất bại** khi các sự kiện đó có giá trị vận hành. `task_submitted` được ghi ở thread gửi việc; `task_started` được ghi trong worker. Nếu muốn đo độ trễ hàng đợi, ghi lại `submittedAtNanos` khi submit rồi tính hiệu số ở đầu task. Thời điểm trên đồng hồ hệ thống phù hợp để đối chiếu log; `nanoTime()` phù hợp để đo duration.

Với hệ thống hỗ trợ structured logging, ưu tiên trường JSON hoặc key/value ổn định. Ví dụ phần thông điệp:

~~~text
event=task_started taskId=job-42 requestId=req-7 worker=log-worker-2
event=task_succeeded taskId=job-42 elapsedMs=18 worker=log-worker-2
~~~

Hai dòng trên chỉ minh họa định dạng trường, không hàm ý chúng phải đứng cạnh nhau hoặc luôn nằm trên cùng một thread ở mọi bước xử lý.

## 3. Ví dụ Java 17 hoàn chỉnh: định danh worker, liên kết job và bắt lỗi

Ví dụ này chỉ dùng thư viện chuẩn Java. Nó tạo pool hai thread, đặt tên worker, chạy ba job và cố ý làm `job-B` thất bại để thấy khác biệt giữa log của worker với log của thread lấy kết quả.

Lưu vào tệp **`ThreadPoolLoggingDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Level;
import java.util.logging.Logger;

public class ThreadPoolLoggingDemo {
    private static final Logger LOG =
            Logger.getLogger(ThreadPoolLoggingDemo.class.getName());

    record Job(String id, boolean shouldFail) {}

    public static void main(String[] args) throws InterruptedException {
        AtomicInteger nextWorker = new AtomicInteger();
        ThreadFactory factory = task -> new Thread(
                task, "log-worker-" + nextWorker.incrementAndGet()
        );
        ExecutorService pool = Executors.newFixedThreadPool(2, factory);

        List<Job> jobs = List.of(
                new Job("job-A", false),
                new Job("job-B", true),
                new Job("job-C", false)
        );
        List<Future<String>> results = new ArrayList<>();

        try {
            for (Job job : jobs) {
                results.add(pool.submit(() -> process(job)));
            }

            for (int i = 0; i < results.size(); i++) {
                Job job = jobs.get(i);
                try {
                    results.get(i).get();
                } catch (ExecutionException error) {
                    LOG.log(Level.SEVERE,
                            "event=job_failed jobId=" + job.id(),
                            error.getCause());
                }
            }
        } finally {
            pool.shutdown();
            try {
                if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                    pool.shutdownNow();
                }
            } catch (InterruptedException error) {
                pool.shutdownNow();
                Thread.currentThread().interrupt();
                throw error;
            }
        }
    }

    private static String process(Job job) {
        long started = System.nanoTime();
        String worker = Thread.currentThread().getName();

        LOG.info(() -> "event=job_started jobId=" + job.id()
                + " worker=" + worker);

        if (job.shouldFail()) {
            throw new IllegalStateException("simulated failure");
        }

        long elapsedMs =
                TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - started);
        LOG.info(() -> "event=job_succeeded jobId=" + job.id()
                + " worker=" + worker + " elapsedMs=" + elapsedMs);
        return "ok";
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac ThreadPoolLoggingDemo.java
java ThreadPoolLoggingDemo
~~~

Các thông điệp có thể thấy (đây là **trích ý nghĩa của log**, không phải stdout chính xác):

~~~text
event=job_started jobId=job-A worker=log-worker-1
event=job_started jobId=job-B worker=log-worker-2
event=job_succeeded jobId=job-A worker=log-worker-1 elapsedMs=...
event=job_started jobId=job-C worker=log-worker-1
event=job_failed jobId=job-B
java.lang.IllegalStateException: simulated failure
~~~

`java.util.logging` với cấu hình console mặc định thường ghi vào **stderr**, kèm thời gian, tên logger/method và thông tin stack trace; ví dụ không yêu cầu một stdout cố định. Thứ tự chạy, worker được chọn và `elapsedMs` thay đổi theo lịch thực thi. Đừng viết kiểm thử đòi hỏi đúng thứ tự mẫu trên.

Giải thích cơ chế:

1. `ThreadFactory` đặt tên worker dễ đọc. Pool tái sử dụng thread; số job lớn hơn số worker không làm xuất hiện một worker mới cho từng job.
2. `job.id()` được truyền tường minh vào lambda của từng lần `submit()`. Vì vậy mọi log có thể gắn với đúng job dù thread đổi hoặc được tái sử dụng.
3. `process()` ghi `job_started` và `job_succeeded` ngay tại worker. Khi `job-B` ném `IllegalStateException`, không có `job_succeeded` cho job đó.
4. `submit(Callable)` giữ lỗi bên trong `Future`. `Future.get()` ném `ExecutionException` và `getCause()` là lỗi gốc. Trong ví dụ, chỉ thread gọi `get()` ghi `job_failed` kèm stack trace, tránh log cùng lỗi hai lần.
5. `shutdown()` ngừng nhận task mới nhưng cho task đã gửi chạy tiếp; `awaitTermination()` chờ có giới hạn; `shutdownNow()` cố gắng ngắt các task còn chạy/chờ, không bảo đảm chúng lập tức dừng. Khi bị interrupt, code yêu cầu dừng pool, đặt lại cờ interrupt rồi chuyển ngoại lệ lên caller.

Trong ứng dụng thật, hãy thống nhất **nơi chịu trách nhiệm log lỗi**: ở ranh giới worker nếu task tự xử lý thất bại, hoặc ở nơi thu kết quả `Future` nếu caller chịu trách nhiệm. Nếu cả hai cùng log stack trace, cùng một lỗi sẽ bị đếm đôi.

## 4. `execute()`, `submit()` và tác vụ bất đồng bộ: ngoại lệ hiện ra ở đâu?

| Cách chạy | Khi task ném lỗi không được bắt | Cách quan sát đáng tin |
| --- | --- | --- |
| `Executor.execute(Runnable)` | Ngoại lệ unchecked có thể thoát khỏi `run()`; worker có thể kết thúc và cơ chế uncaught exception xử lý | Bọc task bằng `try/catch` tại boundary thích hợp hoặc cấu hình xử lý uncaught exception |
| `ExecutorService.submit(Runnable/Callable)` | Lỗi được giữ trong `Future`, thường không đi vào `UncaughtExceptionHandler` | Gọi `Future.get()` và xử lý `ExecutionException.getCause()`; hoặc gắn xử lý ở cấp task |
| `CompletableFuture.supplyAsync(...)` | Completion trở thành exceptional | Dùng `whenComplete`/`handle`/`exceptionally`; `join()` có thể ném `CompletionException` |

Không nên chỉ dựa vào `Thread.setUncaughtExceptionHandler(...)` để bắt mọi lỗi của pool. Đặc biệt, `submit()` thường bọc task bằng `FutureTask` nên lỗi không thoát ra theo con đường uncaught handler. Với `ThreadPoolExecutor.afterExecute(Runnable, Throwable)`, tham số `Throwable` cũng có thể là `null` cho task được gửi bằng `submit()` dù `Future` đã thất bại; muốn kiểm tra phải hiểu cách lấy kết quả từ `Future` đã hoàn tất.

Đừng bỏ qua `Future` nếu kết quả và lỗi là quan trọng. Nếu ứng dụng chủ đích gửi task kiểu fire-and-forget, hãy có boundary xử lý lỗi rõ ràng trong chính task hoặc cơ chế quan sát tập trung. Đặt tên, mã lỗi, mức log và chính sách retry thống nhất để lỗi không biến mất trong hàng đợi.

## 5. MDC và ThreadLocal: vấn đề lớn nhất khi worker được tái sử dụng

`MDC` (Mapped Diagnostic Context) là nơi logging framework lưu các trường ngữ cảnh như `traceId` hay `tenantId`, thường dựa trên dữ liệu gắn với **thread hiện tại**. Khi thread nhận request gửi task vào pool, worker là thread khác: MDC của caller **không tự động được mang sang worker**. Sau khi xử lý xong, nếu worker không xóa context thì task kế tiếp trên cùng worker có nguy cơ nhận nhầm `traceId` của task trước.

Ví dụ lỗi logic:

~~~text
request A -> worker-1: MDC traceId=A; hoàn thành nhưng quên clear
request B -> worker-1: không thiết lập traceId; log của B vẫn hiện A
~~~

Với `ThreadLocal<String>` thuần Java, thiết lập giá trị bên trong task và luôn dọn ở `finally`:

~~~java
private static final ThreadLocal<String> TRACE_ID = new ThreadLocal<>();

static Runnable taskWithTrace(String traceId, Runnable task) {
    return () -> {
        try {
            TRACE_ID.set(traceId);
            task.run();
        } finally {
            TRACE_ID.remove();
        }
    };
}
~~~

Đây là **đoạn helper đặt trong một lớp Java**, không phải chương trình độc lập. Nó truyền `traceId` bằng tham số rõ ràng và không để context của task vừa chạy tồn tại sau khi task kết thúc. Nếu code có ngữ cảnh lồng nhau thật sự trên cùng thread, cần chiến lược lưu/khôi phục giá trị trước đó thay vì luôn xóa; đối với boundary của các task độc lập trên thread pool, xóa sau mỗi task thường là lựa chọn dễ kiểm chứng.

Với **SLF4J MDC** và backend logging hỗ trợ MDC, có thể chụp bản sao context **ở thread gửi task** rồi thiết lập/xóa nó trong worker:

~~~java
import java.util.Map;
import org.slf4j.MDC;

// Helper trong lớp có sẵn executor và logger; cần SLF4J + backend tương thích.
static Runnable propagateMdc(Runnable task) {
    Map<String, String> captured = MDC.getCopyOfContextMap();
    return () -> {
        try {
            MDC.clear();
            if (captured != null) {
                MDC.setContextMap(captured);
            }
            task.run();
        } finally {
            MDC.clear();
        }
    };
}

// Gọi ở thread tạo công việc, lúc MDC còn chứa requestId/traceId:
// executor.submit(propagateMdc(() -> logger.info("processing")));
~~~

`propagateMdc(...)` phải được gọi lúc **submit**, không phải sau khi request đã kết thúc; mỗi task cần snapshot riêng. Helper trên thiết kế cho *boundary của các task độc lập* trong pool. Nếu gọi lồng trực tiếp cùng thread khi có MDC bên ngoài cần giữ, hãy lưu và khôi phục context cũ trong `finally`. Chỉ chụp context thôi chưa đủ: cấu hình pattern hoặc encoder của logging backend còn phải xuất trường MDC (ví dụ `%X{traceId}` với Logback) thì chúng mới hiện trong log.

`InheritableThreadLocal` không giải quyết việc truyền ngữ cảnh theo từng task trong pool: worker thường được tạo trước và tái sử dụng, nên giá trị kế thừa tại lúc tạo thread không phản ánh request mới. Đừng đặt thông tin request trong biến `static` dùng chung. Với executor do framework quản lý, có thể dùng task decorator/context propagation phù hợp, nhưng vẫn phải xác minh thời điểm capture, cleanup và đường đi của task.

## 6. Giữ context qua nhiều bước async

Khi một task lại gửi task khác sang executor hoặc dùng `CompletableFuture`, mỗi lần chuyển sang worker mới là một **ranh giới truyền context**. Nếu bỏ tham số executor trong `CompletableFuture.supplyAsync(...)`, Java dùng `ForkJoinPool.commonPool()` mặc định; task có thể chạy ở những thread không thuộc pool bạn đặt tên và cấu hình.

~~~java
CompletableFuture<Result> future =
        CompletableFuture.supplyAsync(() -> loadData(requestId), executor);
~~~

Đây là đoạn minh họa: `Result`, `loadData`, `requestId` và `executor` phải được định nghĩa trong ứng dụng. Truyền `requestId` như tham số là cách rõ ràng; nếu thư viện logging cần MDC, tạo wrapper tương ứng cho `Supplier` trước khi đưa vào `supplyAsync`. Không giả định callback `whenComplete` luôn chạy trên cùng thread hoặc giữ MDC của giai đoạn trước. Dùng log có `taskId`/`requestId` tại từng boundary quan trọng để truy vết mạch công việc.

Khi cần trace xuyên HTTP, messaging và task queue, `traceId` và `spanId` từ hệ thống tracing giúp liên kết nhiều đoạn thực thi; logging context cần được tích hợp với cơ chế tracing thực sự thay vì tự đoán quan hệ qua tên thread.

## 7. Log đúng sự kiện, đúng mức và đúng chi phí

- **`INFO`:** sự kiện vận hành quan trọng như job hoàn thành, batch được nhận, retry đã quyết định; tránh ghi INFO cho mọi vòng lặp của task tần suất cao.
- **`DEBUG`/`TRACE`:** chi tiết từng bước, cấu hình, thời gian nội bộ phục vụ điều tra, bật theo nhu cầu. Với logging có tham số/lazy message, giảm chi phí dựng chuỗi khi mức log bị tắt.
- **`WARN`:** bất thường có thể phục hồi, chẳng hạn retry hoặc độ trễ hàng đợi vượt ngưỡng.
- **`ERROR`/`SEVERE`:** task cuối cùng thất bại hay hành động không hoàn tất; đính kèm exception để giữ stack trace và cause.

Đừng log mọi lần retry thành một lỗi cuối cùng nếu hệ thống còn khả năng phục hồi; chọn chính sách đếm và mức cảnh báo hợp lý. Ngược lại, không biến lỗi bất ngờ thành một dòng `"failed"` thiếu stack trace.

Logging cũng có chi phí: formatter, đồng bộ I/O, ghi file và ship log có thể làm chậm worker, khiến hàng đợi dài hơn. Async appender có thể tách I/O ra khỏi thread xử lý nhưng có hàng đợi, chính sách quá tải và rủi ro mất log khi tiến trình dừng đột ngột; nó **không** đồng nghĩa với `ExecutorService` chạy công việc nghiệp vụ. Khi đo hiệu năng, quan sát cả `activeThreads`, kích thước hàng đợi, thời gian chờ, tỷ lệ lỗi, dropped logs và độ trễ xử lý; không mặc định tăng số thread là giải pháp.

## 8. Những tình huống cần đặc biệt chú ý

1. **Task bị từ chối:** khi executor đang shutdown hoặc pool/hàng đợi đã quá tải theo chính sách, thao tác submit có thể ném `RejectedExecutionException` **ngay tại thread gửi việc**. Ghi rõ `taskId`, trạng thái pool và chính sách xử lý; đừng chờ log `task_started` vốn sẽ không có.
2. **Task bị hủy hoặc interrupt:** `Future.cancel(true)` chỉ *yêu cầu* interrupt nếu đang chạy. Code cần xử lý interrupt đúng cách; tránh log hủy có chủ ý như lỗi hệ thống nghiêm trọng. `Future.get()` có thể ném `CancellationException`.
3. **Pool nhiều tenant/request:** luôn dọn MDC/ThreadLocal; hạn chế chứa dữ liệu cá nhân, token, mật khẩu, nội dung request nhạy cảm. Khi nhận ID không tin cậy từ bên ngoài, chuẩn hóa và giới hạn độ dài để tránh log injection hoặc log quá lớn.
4. **Log đảo thứ tự:** timestamps từ nhiều thread có thể rất gần nhau; log shipper/async appender có thể đệm, làm thứ tự quan sát khác thứ tự xử lý. Phân tích theo `traceId`, `taskId` và mốc sự kiện thay vì dựa vào vị trí dòng.
5. **Ngoại lệ bị nuốt:** `submit()` không đảm bảo lỗi tự hiện thành stack trace; phải lấy `Future` hoặc xử lý ở boundary.
6. **Ghi trùng stack trace:** log ở worker rồi log lại nguyên lỗi ở caller làm tăng nhiễu và sai số đếm sự cố. Chỉ thêm log tại cả hai nơi khi chúng thể hiện *hai sự kiện khác nhau* với thông tin bổ sung rõ ràng.
7. **Vòng đời pool:** mỗi request không nên tự tạo một pool rồi bỏ quên; quản lý executor theo vòng đời ứng dụng, shutdown có kiểm soát và quan sát task còn đang chạy.

## 9. Cách kiểm chứng bằng kiểm thử

Để phát hiện lỗi thực sự, kiểm tra hành vi thay vì so khớp thứ tự log không xác định:

- Tạo pool **một thread**, chạy tuần tự hai task có `traceId=A` rồi `traceId=B`. Thu log qua handler/appender của test và xác nhận log của B không chứa A; chạy thêm task không có context để kiểm tra đã dọn sạch.
- Chạy task ném lỗi qua `submit()`. Xác nhận `Future.get()` trả `ExecutionException`, giữ được cause và hệ thống ghi đúng một sự kiện thất bại theo chính sách.
- Chạy nhiều task trên pool nhỏ, kiểm tra mỗi bản ghi có đúng `taskId` dù thread lặp lại và log xen kẽ. Không assert một thứ tự tùy thuộc scheduler.
- Kiểm tra đường xử lý `RejectedExecutionException`, interrupt/cancel và shutdown ở nơi ứng dụng thực sự có các tình huống này.
- Nếu dùng MDC, kiểm tra cả **dữ liệu trong MDC** và **cấu hình encoder/pattern**; MDC được thiết lập đúng nhưng formatter không xuất trường sẽ làm log thiếu traceId.

Một cách đọc log hữu ích khi có sự cố là lọc theo `taskId`/`traceId`, dựng lại các mốc `submitted → started → succeeded/failed`, xem worker và khoảng chờ, rồi đối chiếu stack trace cùng trạng thái executor. Cách này vẫn có ý nghĩa khi một worker xử lý nhiều task và log của nhiều task xen kẽ.

## 10. Kết luận thực hành

Với thread pool, hãy **truyền định danh task tường minh**, đặt tên worker để chẩn đoán, xử lý lỗi đúng theo API gửi việc, và xem MDC/ThreadLocal là dữ liệu cần thiết lập **và dọn trong mỗi lần chạy task**. Log đủ trường để truy vết và đo thời gian, nhưng kiểm soát chi phí, thông tin nhạy cảm và việc ghi trùng. Khi làm đúng, log vẫn cho thấy rõ một job đã đi qua hệ thống thế nào dù nó phải chờ hàng đợi, đổi thread hoặc thất bại.