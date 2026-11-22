# CallerRunsPolicy chuyển công việc sang luồng gọi và thay đổi độ trễ

Trong ứng dụng Spring, `ThreadPoolTaskExecutor` thường dùng một nhóm worker thread để xử lý công việc nền. Tuy nhiên, khi pool đã bận và hàng đợi đầy, một tác vụ mới có thể bị từ chối. `java.util.concurrent.ThreadPoolExecutor.CallerRunsPolicy` là một chiến lược xử lý tình huống đó: **nếu executor chưa shutdown, thread đang gọi `execute()` sẽ tự thực thi tác vụ bị từ chối**.

Kết quả rất đáng chú ý: lời gọi vốn được kỳ vọng chỉ “gửi việc” có thể trở thành **lời gọi đồng bộ, chờ đến khi công việc kết thúc**. Nếu caller là thread xử lý HTTP request, thời gian phản hồi của chính request đó tăng theo thời gian chạy tác vụ. Nếu caller là thread chuyên sinh việc, tốc độ sinh việc tự giảm lại. Cơ chế sau được gọi là **backpressure bằng caller**, nhưng chỉ phù hợp khi chấp nhận những hệ quả đối với latency, thread context và hợp đồng xử lý task.

Một giới hạn phải ghi nhớ ngay: **nếu executor đã shutdown, `CallerRunsPolicy` bỏ tác vụ và không ném lỗi**. Vì vậy không được xem mọi lần `execute()` trả về bình thường như một bằng chứng tác vụ đã được nhận để xử lý sau này.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích lúc nào `ThreadPoolExecutor` chuyển sang `RejectedExecutionHandler` và khi nào `CallerRunsPolicy` thực thi task trên caller thread.
- Phân biệt **worker thread**, **caller thread**, **queue** và **task đang chạy**; hiểu vì sao `maximumPoolSize` không hạn chế tổng số task có thể đồng thời chạy trên các caller.
- Phân tích tác động lên độ trễ `execute()`, thời gian đáp ứng HTTP, throughput, p95/p99 và chu kỳ sinh việc.
- Cấu hình `CallerRunsPolicy` với Spring `ThreadPoolTaskExecutor` và hiểu tác động khi dùng `@Async`, `Future` hoặc `CompletableFuture`.
- Nhận diện các rủi ro: chạy trong transaction/request context, blocking event-loop, deadlock/reentrancy, lỗi bị đẩy lên caller và task bị bỏ im lặng lúc shutdown.
- Viết kiểm thử Java 17+ không phụ thuộc timing để chứng minh nhiệm vụ bị đẩy sang caller.
- Chọn chính sách overload và cách quan sát phù hợp với yêu cầu nghiệp vụ.

## 2. Vì sao một executor cần chính sách từ chối?

`ThreadPoolExecutor` của Java có ít nhất ba yếu tố liên quan đến sức chứa:

1. `corePoolSize`: mức worker cốt lõi.
2. `maximumPoolSize`: số worker tối đa **thuộc về pool**.
3. `BlockingQueue<Runnable>`: nơi lưu công việc đã nhận nhưng chưa được worker xử lý.

Với cấu hình thông thường, trình tự xử lý `execute(task)` như sau:

1. Nếu số worker còn dưới `corePoolSize`, thử tạo worker để thực hiện task.
2. Nếu đã đạt core, thử thêm task vào queue.
3. Nếu queue không nhận thêm và số worker còn dưới `maximumPoolSize`, thử tạo thêm worker.
4. Nếu cả các phương án đó không thể nhận task, hoặc executor đang shutdown, gọi `RejectedExecutionHandler`.

Đây là mô tả đường quyết định của `ThreadPoolExecutor`, không phải hợp đồng cho mọi loại `Executor`. Trong khi xử lý một lời gọi, worker khác vẫn có thể hoàn thành task hoặc lấy việc khỏi queue, nên tình trạng bão hòa là một điều kiện có thể thay đổi rất nhanh.

Ví dụ `core=2`, `max=4`, queue chứa 3 phần tử: khi hai worker đều bận, ba job mới có thể vào queue; sau đó pool có thể tạo thêm hai worker; nếu bốn worker bận và ba chỗ queue đều đã dùng, một task mới sẽ phải đi vào rejection handler. Không phải cứ `getActiveCount()==max` là chắc chắn từ chối, vì queue có thể vẫn còn sức chứa.

### Hàng đợi cần được giới hạn có chủ đích

`ThreadPoolTaskExecutor` trong Spring có mặc định `corePoolSize=1`, `maxPoolSize=Integer.MAX_VALUE` và `queueCapacity=Integer.MAX_VALUE`. Với queue rất lớn, công việc thường xếp hàng trước khi pool cần mở rộng vượt core; độ trễ có thể ngày càng tăng trong khi chính sách từ chối chưa hề được kích hoạt.

Muốn đánh giá `CallerRunsPolicy` khi quá tải, trước hết phải xác định **capacity hữu hạn**, tốc độ producer, tốc độ consumer, chi phí của task và thời gian đáp ứng tối đa được phép. Không tăng queue tùy tiện chỉ để tránh thấy tín hiệu quá tải.

## 3. Hợp đồng chính xác của CallerRunsPolicy

`CallerRunsPolicy` là lớp lồng trong `ThreadPoolExecutor`, triển khai `RejectedExecutionHandler`. Khi handler được gọi:

| Trạng thái executor | Hành vi |
| --- | --- |
| Executor chưa shutdown và đang từ chối task do bão hòa | Gọi `run()` của tác vụ ngay trong thread đang gọi `execute()` |
| Executor đã shutdown | **Bỏ tác vụ**; không tự chạy và không ném `RejectedExecutionException` |
| Pool còn chỗ và `execute()` nhận task bình thường | Handler không được gọi; task chạy theo cơ chế worker/queue |

Có thể hình dung nhánh xử lý đặc trưng:

~~~java
// Mô hình khái niệm của rejectedExecution(), KHÔNG phải
// lời khuyên tự thay thế mã thư viện JDK.
if (!executor.isShutdown()) {
    runnable.run(); // chạy trong chính thread đã gọi execute()
}
// Khi shutdown: không làm gì.
~~~

Điểm cần nhấn mạnh:

- `CallerRunsPolicy` không tạo một worker thread mới.
- Nó không đặt tác vụ bị từ chối lại vào queue.
- Nó không gửi tác vụ sang một executor khác.
- Nó không hứa luôn thực thi tác vụ: **shutdown là ngoại lệ quan trọng**.
- Khi task chạy trực tiếp, lời gọi `execute()` thường chỉ trả về **sau khi `run()` kết thúc**. Nếu `run()` ném unchecked exception thì exception có thể thoát ra trên caller thread.
- Chính sách này không tự retry task lỗi, không cung cấp lưu trữ bền vững và không cam kết thứ tự thực thi với những task đã có trong queue.

Vì sao lại gọi là **caller-runs**? “Caller” là thread thực sự thực hiện lời gọi `execute()` trong tình huống đó; không nhất thiết là HTTP request thread. Trong batch producer, đó có thể là một producer thread; trong một worker đang tiếp tục gửi việc, đó có thể là worker của pool khác hoặc chính pool hiện tại.

## 4. Backpressure: producer bị buộc làm việc thay cho consumer

Giả sử một producer gọi:

~~~java
executor.execute(job);
createNextJob();
~~~

Khi executor còn sức chứa, `execute(job)` thường trả về tương đối nhanh để producer tiếp tục tạo việc. Khi pool bão hòa và handler là `CallerRunsPolicy`, `job.run()` chạy ngay trên producer thread. Producer **không thể đi tới `createNextJob()` trước khi job hoàn thành**.

Đây là cơ chế phản hồi bằng thời gian: tốc độ gửi việc giảm tự nhiên khi hệ thống thiếu năng lực xử lý. Trong khi producer bận làm job, worker có thể lấy bớt phần tử khỏi queue, tạo chỗ cho những lần submit tiếp theo. JDK gọi đây là một cơ chế feedback control đơn giản.

Nhưng cần phân biệt **giảm tốc producer** với **giới hạn concurrency toàn hệ thống**:

- `maximumPoolSize=4` chỉ giới hạn số worker mà **pool** có thể tạo; nó không cấm nhiều request thread cùng chạy task riêng do CallerRuns.
- Nếu có 30 request thread đồng thời submit vào một pool 4 worker đang bão hòa, một số request thread có thể đồng thời tự chạy các task bị từ chối. **Tổng số task đang thực thi có thể vượt quá bốn**.
- Với task dùng nhiều CPU hoặc kết nối database, cơ chế này có thể chuyển tình trạng quá tải sang web thread pool và dependency bên ngoài. Nó không phải một semaphore kiểm soát tổng số task toàn ứng dụng.

Do đó CallerRuns là một cách tạo áp lực ngược lên **nguồn gửi** chứ không phải bộ giới hạn tài nguyên tuyệt đối. Khi cần concurrency cap chung, cân nhắc bounded admission, semaphore hoặc hàng đợi bền vững có số worker được kiểm soát.

## 5. Ví dụ Java 17+ chứng minh việc chạy trên caller

Ta tạo pool chỉ có **một worker** và queue sức chứa **một task**. Task thứ nhất giữ worker bằng `CountDownLatch`; task thứ hai chiếm chỗ queue. Khi main thread gửi task thứ ba, `CallerRunsPolicy` phải chạy task đó ngay trên main thread.

Ví dụ không dùng `Thread.sleep()` để hy vọng pool bão hòa: các latch xác định chính xác trạng thái. Đồng thời, ví dụ kiểm tra trường hợp executor đã shutdown.

**Tệp `CallerRunsDemo.java`:**

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

public final class CallerRunsDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch workerStarted = new CountDownLatch(1);
        CountDownLatch releaseWorker = new CountDownLatch(1);
        CountDownLatch queuedFinished = new CountDownLatch(1);

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.CallerRunsPolicy());

        try {
            pool.execute(() -> {
                workerStarted.countDown();
                try {
                    releaseWorker.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            });

            if (!workerStarted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker did not start");
            }

            // Worker vẫn chờ releaseWorker nên job này phải nằm trong queue.
            pool.execute(queuedFinished::countDown);

            Thread submittingThread = Thread.currentThread();
            AtomicReference<Thread> executedBy = new AtomicReference<>();
            List<String> order = new ArrayList<>();

            order.add("before");
            pool.execute(() -> {
                executedBy.set(Thread.currentThread());
                order.add("inCaller");
            });
            order.add("after");

            System.out.println("onCaller="
                    + (executedBy.get() == submittingThread));
            System.out.println("order=" + String.join(">", order));

            releaseWorker.countDown();
            if (!queuedFinished.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Queued job did not finish");
            }
            System.out.println("queuedFinished=true");
        } finally {
            releaseWorker.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }

        // Chính sách này im lặng bỏ task sau khi executor đã shutdown.
        ThreadPoolExecutor stopped = new ThreadPoolExecutor(
                1, 1, 0, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.CallerRunsPolicy());

        stopped.shutdown();
        AtomicBoolean ran = new AtomicBoolean(false);
        stopped.execute(() -> ran.set(true));
        Future<Integer> future = stopped.submit(() -> 42);

        System.out.println("shutdownTaskRan=" + ran.get());
        System.out.println("futureDoneAfterDiscard=" + future.isDone());
        future.cancel(false);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac CallerRunsDemo.java
java CallerRunsDemo
~~~

**Stdout của lần chạy thành công:**

~~~text
onCaller=true
order=before>inCaller>after
queuedFinished=true
shutdownTaskRan=false
futureDoneAfterDiscard=false
~~~

Giải thích:

1. `workerStarted.await()` chỉ tiếp tục khi worker thứ nhất đã bắt đầu và đang chờ `releaseWorker`.
2. Task thứ hai chiếm slot duy nhất của queue, vì worker chưa thể lấy task đó.
3. Task thứ ba không thể vào pool/queue, nên `CallerRunsPolicy` chạy nó trên chính `submittingThread`. Vì vậy `onCaller=true`.
4. Chuỗi `before>inCaller>after` chứng minh **`execute()` của task thứ ba chưa trả về trước khi phần thân task chạy xong**.
5. Sau `releaseWorker.countDown()`, worker xử lý task thứ hai và `queuedFinished.await()` chứng minh nó hoàn tất.
6. Với executor khác đã shutdown, `execute()` bỏ task; `shutdownTaskRan=false`. `submit()` vẫn có thể trả một `Future` chưa hoàn thành bởi vì task chứa trong `FutureTask` đã bị bỏ. Ta gọi `cancel(false)` để không để lại một future có thể bị chờ vô hạn.

**Vì sao đoạn này không race ở phần `List<String> order`?** Chỉ main thread chỉnh sửa danh sách trong ba vị trí `before`, `inCaller`, `after`: trong tình huống đang kiểm thử, phần thân task thứ ba cũng chạy trên main thread. Không nên suy luận rằng `ArrayList` an toàn với mọi trường hợp executor; trong bài toán thực tế phải dùng đồng bộ hoặc collection phù hợp nếu task có thể chạy trên worker.

Một điều kiện thiết yếu của bài kiểm thử là **không thả `releaseWorker` trước khi gửi task thứ ba**. Nếu worker có thời gian lấy task thứ hai ra khỏi queue, policy có thể không được kích hoạt và test không còn chứng minh nhánh caller-runs.

## 6. CallerRunsPolicy thay đổi độ trễ như thế nào?

### Độ trễ của lời gọi submit

Gọi `T_submit` là thời gian từ lúc bắt đầu tới lúc `execute(task)` trả về. Khi pool còn chỗ, `T_submit` thường gần với chi phí kiểm tra/đưa việc vào queue hoặc tạo worker; **không bao gồm toàn bộ thời gian chạy task**. Khi `CallerRunsPolicy` kích hoạt, công việc xảy ra trên caller nên:

~~~text
T_submit ≈ T_kiểm_tra_pool + T_task_trực_tiếp
~~~

Đây chỉ là mô hình gần đúng. `T_task_trực_tiếp` còn chứa thời gian CPU, I/O, chờ lock, GC, scheduling và các lệnh gọi phụ thuộc. Nếu task nặng hoặc bị block, `execute()` có thể block rất lâu, kể cả quá deadline của request.

### Tác động tới request HTTP

Giả sử một API mất khoảng 20 ms để validate và chuẩn bị response, sau đó gửi một công việc tạo báo cáo có thời gian xử lý khoảng 400 ms vào executor.

- Khi executor còn chỗ, request có thể trả kết quả về việc **đã tiếp nhận theo hợp đồng hiện tại** mà không chờ báo cáo chạy xong.
- Khi pool bão hòa và caller-runs kích hoạt, request thread có thể làm việc thêm khoảng 400 ms trước khi hoàn tất lời gọi submit. Độ trễ phản hồi có thể từ mức vài chục ms lên hàng trăm ms hoặc cao hơn.
- Nếu task gọi DB hay HTTP bên ngoài, thời gian có thể biến động rất lớn, khiến p95/p99 tăng mạnh dưới tải.

Các số 20 ms và 400 ms chỉ là **ví dụ minh họa cơ chế**, không phải cam kết đo đạc hoặc định luật cộng thời gian. Nếu deadline HTTP đã hết nhưng caller vẫn đang làm việc, server vẫn có thể tiêu tốn tài nguyên sau khi client ngừng chờ.

**Tính chất quan trọng:** cơ chế thường xuất hiện **chỉ ở giai đoạn bão hòa**, nên hệ thống có thể trông rất nhanh trong kiểm thử tải thấp rồi đột ngột có đuôi độ trễ dài trong production. Đừng đo mỗi p50.

### Hai loại latency cần phân biệt

| Chỉ số | Khi pool còn chỗ | Khi CallerRuns kích hoạt |
| --- | --- | --- |
| Thời gian gọi `execute()` | Thường ngắn | Bao gồm thời gian thực thi task trên caller |
| Thời gian đợi trong queue của task bị reject | Task khác có thể phải đợi | Task caller-runs không phải xếp vào queue đó |
| Request response latency | Ít chịu ảnh hưởng trực tiếp từ body task nếu async thật | Có thể tăng theo toàn bộ thời gian task |
| Tốc độ producer gửi việc mới | Có thể nhanh | Chậm lại vì producer thực hiện task |
| Số task chạy bên ngoài worker của pool | Thường bằng 0 | Có thể tăng theo số caller bị điều hướng |
| p95/p99 và khả năng đáp ứng deadline | Phụ thuộc queue và task | Có nguy cơ tăng đột ngột đúng lúc quá tải |

## 7. Ví dụ phân tích tải và backpressure

Giả sử một dịch vụ có `core=2`, `max=4`, queue capacity 8 và mỗi job mất trung bình 250 ms khi giữ một worker. Nếu bốn worker đều bận và hàng đợi đầy, task tiếp theo chuyển sang caller; producer phải tiêu tốn khoảng thời gian tương ứng để xử lý nó.

Trong điều kiện lý tưởng đơn giản, bốn worker mỗi worker xử lý một tác vụ trong 250 ms có thể hoàn tất khoảng 16 job/giây; đây **không phải dự báo production** vì còn contention, I/O, jitter và thay đổi kích thước worker. Nếu upstream liên tục đẩy 80 job/giây, backlog có thể đầy nhanh, khiến nhiều caller cùng làm việc.

Vì vậy có hai hiệu ứng đồng thời:

1. **Phản hồi âm lên tốc độ gửi của từng caller:** request/producer đó không gửi tiếp cho đến khi task nó đang làm xong.
2. **Gia tăng tổng thread tham gia thực thi task:** khi có nhiều caller, nhiều task chạy ngoài worker pool; quá tải có thể lan sang HTTP threads, scheduler hoặc database.

Một producer chạy vòng lặp tuần tự có thể được điều tiết tốt bởi CallerRuns. Một HTTP server có hàng trăm request thread độc lập có thể biến các request thread thành nguồn parallelism bổ sung không mong muốn. Phải đánh giá **topology của caller**, chứ không chỉ cấu hình pool.

Nếu thực sự cần tổng concurrency cố định, hãy dùng giới hạn admission riêng như semaphore/queue bounded, hoặc chuyển sang hàng đợi và worker độc lập với số lượng consumer cố định.

## 8. So sánh CallerRunsPolicy với các chính sách còn lại

`ThreadPoolExecutor` cung cấp một số `RejectedExecutionHandler` chuẩn:

| Chính sách | Khi bão hòa và chưa shutdown | Ảnh hưởng nổi bật |
| --- | --- | --- |
| `AbortPolicy` (mặc định) | Ném `RejectedExecutionException` | Caller biết không được nhận; có thể trả lỗi hoặc fallback |
| `CallerRunsPolicy` | Thực thi task trên caller | Không mất task do bão hòa trong nhánh này, nhưng làm caller chờ |
| `DiscardPolicy` | Bỏ task im lặng | Nhanh nhưng có nguy cơ mất việc mà hệ thống không nhận biết |
| `DiscardOldestPolicy` | Bỏ task đầu queue rồi thử submit lại | Có thể làm mất tác vụ đã queue và phá kỳ vọng thứ tự |

`CallerRunsPolicy` có vẻ tránh được việc bỏ job do **bão hòa** nhưng có hai ngoại lệ cần xét: task có thể lỗi ngay trên caller, và khi **shutdown** policy **bỏ job im lặng**. Vì vậy không thể dùng nó để bảo đảm “mỗi job đều thực thi thành công”.

Với dữ liệu bắt buộc xử lý, `AbortPolicy` và một durable queue/job table thường tạo hợp đồng rõ ràng hơn. Với producer batch tuần tự có thể chấp nhận chạy tác vụ trực tiếp, `CallerRunsPolicy` là công cụ hữu ích và ít phức tạp.

## 9. Cấu hình CallerRunsPolicy trong Spring

`ThreadPoolTaskExecutor` là Spring adapter trên nền `ThreadPoolExecutor`. Có thể cấp `RejectedExecutionHandler` cho executor bằng `setRejectedExecutionHandler(...)`.

**Tệp `ReportExecutorConfig.java`**, dùng trong dự án Spring Framework có `spring-context`:

~~~java
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class ReportExecutorConfig {

    @Bean(name = "reportExecutor")
    public ThreadPoolTaskExecutor reportExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("report-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.CallerRunsPolicy());

        return executor;
    }
}
~~~

Đây là **Spring configuration class**, không phải chương trình `javac` độc lập: nó cần dependencies của Spring và không có `main`. Khi bean do Spring quản lý, container khởi tạo và shutdown executor theo vòng đời ứng dụng. Nếu tự `new ThreadPoolTaskExecutor()` ngoài container, cần gọi `initialize()` trước khi sử dụng và `shutdown()` sau khi xong.

Với cấu hình trên, queue bounded là điều kiện quan trọng để có thể xuất hiện overload theo ý nghĩa mong muốn. Nếu đặt queue capacity cực lớn, `CallerRunsPolicy` có thể hiếm khi kích hoạt trong khi task đang đợi lâu.

### Service gửi việc

**Tệp `ReportDispatchService.java`:**

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.TaskExecutor;
import org.springframework.stereotype.Service;

@Service
public class ReportDispatchService {
    private final TaskExecutor executor;

    public ReportDispatchService(
            @Qualifier("reportExecutor") TaskExecutor executor) {
        this.executor = executor;
    }

    public void dispatch(String reportId) {
        executor.execute(() -> generate(reportId));
    }

    private void generate(String reportId) {
        System.out.println("Generating report " + reportId);
    }
}
~~~

`dispatch` ở đây không hứa luôn trả về nhanh. Khi pool còn capacity, task thường chạy trên worker; khi CallerRuns kích hoạt, **`generate(reportId)` chạy ngay trên thread gọi `dispatch`**, và `dispatch` chỉ trở về sau khi việc này hoàn thành. Khi pool đã shutdown, task có thể bị bỏ mà `dispatch` vẫn trả về bình thường.

Không dùng ví dụ in log trên làm cơ chế lưu/khôi phục job thật. Trong ứng dụng nghiệp vụ, cần job ID, trạng thái lưu bền, idempotency và xử lý lỗi phù hợp nếu việc không được phép mất.

### Dùng chung với @Async

Nếu phương thức được đánh dấu `@Async("reportExecutor")`, Spring gửi lời gọi qua một executor được chọn theo tên. Tuy nhiên, khi handler là `CallerRunsPolicy` và pool bão hòa, **wrapper của công việc bất đồng bộ có thể được chạy đồng bộ trên caller thread**. Do đó:

- Cần xem `@Async` là yêu cầu gửi công việc qua executor, không phải lời cam kết cứng rằng body **luôn** chạy trên thread khác.
- Nếu caller là request thread, request có thể chờ body thực thi, kéo dài response time.
- `@Async` theo proxy mặc định không intercept self-invocation trong cùng bean.
- Với method trả `Future`/`CompletableFuture`, phải xét cả completion/exception; nếu task bị discard lúc shutdown, một future của JDK submit có thể không bao giờ complete nếu không được hủy/timeout.
- `@Async void` có đường xử lý lỗi nội bộ riêng qua `AsyncUncaughtExceptionHandler`; không dùng handler này làm giải pháp chung cho tất cả lỗi tại thời điểm submit.

Trong ứng dụng Spring Boot, chỉ gắn handler vào đúng executor được yêu cầu. Đừng mặc định rằng mọi `@Async` hay mọi xử lý HTTP async đều chọn bean này; khi cần, chỉ định bean bằng qualifier và kiểm tra đường gọi qua proxy.

## 10. Exception của task và lỗi bị từ chối khác nhau

### Khi dùng execute(Runnable)

Nếu pool bão hòa và dùng `AbortPolicy`, handler ném `RejectedExecutionException`; qua `ThreadPoolTaskExecutor` của Spring, lỗi này thường được chuyển thành `TaskRejectedException` ở ranh giới submit. Caller có thể bắt và trả lỗi quá tải.

Nếu pool bão hòa và dùng `CallerRunsPolicy`, handler tự gọi `Runnable.run()` trên caller. Nếu body ném `RuntimeException`, exception đó có thể thoát ra ngay từ `execute()` trên thread gọi.

~~~java
// Mã minh họa trong một phương thức có executor phù hợp.
// Nếu handler chạy Runnable trực tiếp trên caller, exception có
// thể tới chính lời gọi execute() này.
executor.execute(() -> {
    throw new IllegalStateException("Report generation failed");
});
~~~

Vì vậy phải phân biệt:

- **Không nhận được task:** handler phản ứng với bão hòa hoặc shutdown.
- **Task được thực thi nhưng lỗi:** body `run()` ném exception trong môi trường thực thi của nó.

Với `CallerRunsPolicy`, hai tình huống đó có thể trộn vào cùng một call stack, nhưng ý nghĩa nghiệp vụ vẫn khác nhau. Đừng bắt mọi `RuntimeException` rồi kết luận “pool đang đầy”.

### Khi dùng submit(Callable/Runnable) và Future

Trong JDK `ExecutorService.submit` thường đóng gói công việc thành `FutureTask`. Nếu CallerRuns kích hoạt khi pool bão hòa, chính `FutureTask.run()` chạy trên caller: `submit` có thể mất nhiều thời gian mới trả `Future`, và Future thường đã hoàn tất khi công việc đã chạy xong. Lỗi từ `Callable` được ghi trong Future để `get()` thông báo bằng `ExecutionException`; không nhất thiết được ném trực tiếp từ `submit`.

Nhưng khi executor **shutdown**, `CallerRunsPolicy` **bỏ `FutureTask`**, không hủy Future. Bởi vậy `submit()` có thể trả một Future vẫn ở trạng thái pending; nếu người gọi `get()` không timeout, có thể chờ vô hạn.

Cách sử dụng an toàn hơn khi môi trường có thể shutdown:

- Không dựa vào `CallerRunsPolicy` để thông báo chắc chắn về việc nhận job khi shutdown.
- Khi cần hợp đồng “không nhận thì báo lỗi”, ưu tiên `AbortPolicy` hoặc custom handler ném exception rõ ràng.
- Khi có Future, dùng deadline/timeout và cơ chế cancel phù hợp; timeout chỉ giúp người chờ không treo, không tự chứng minh job chưa từng được thực thi.
- Không lập tức retry tác vụ có side effect mà chưa có job ID, idempotency key hay trạng thái xác nhận.

`CompletableFuture.runAsync(task, executor)` cũng cần đánh giá theo executor được truyền vào: nếu handler chạy inline, quá trình tạo/sắp lịch future có thể thực thi body ngay; nếu bỏ task khi shutdown mà không báo lỗi, completion có thể không đến. Đây không phải một API thay thế cho durable queue.

## 11. Thread context thay đổi: vấn đề quan trọng trong Spring

Khi task chạy trong worker thread, nhiều giá trị được gắn với thread gọi **không tự chuyển theo**. Khi chạy bằng `CallerRunsPolicy`, task lại dùng **chính thread gọi**. Sự khác biệt này có thể làm lộ lỗi chỉ xuất hiện lúc quá tải.

### Transaction và tài nguyên gắn với thread

Trong Spring, nhiều transaction context được gắn với thread đang thực thi. Giả sử controller/service đang ở trong một transaction và gọi `execute()`:

- Lúc còn capacity, task trên worker thường không tự nhận transaction của thread gửi.
- Lúc CallerRuns kích hoạt, task có thể chạy **trong thread đang mang transaction hiện tại**. Nó có thể thấy thread-bound state hoặc tham gia thao tác trên tài nguyên gắn thread theo cách khác với worker execution.
- Cùng một đoạn code có thể có hai hành vi khác nhau phụ thuộc tải, điều rất khó kiểm thử và vận hành.

Không nên giả định một tác vụ chạy qua executor luôn độc lập với request/transaction. Với cập nhật dữ liệu nghiệp vụ, cần xác định ranh giới transaction và nơi ghi bền vững rõ ràng. Dùng transactional outbox hoặc cơ chế sau-commit khi phù hợp với yêu cầu consistency.

### SecurityContext, MDC và ThreadLocal

Các giá trị như security principal, trace ID hoặc MDC logging có thể được giữ trong `ThreadLocal`. Worker pool thread có thể cần `TaskDecorator` hoặc cơ chế context propagation phù hợp để nhận đúng thông tin. Nhưng khi CallerRuns xảy ra, task có thể nhìn thấy trực tiếp context của caller.

Điều này dẫn tới hai kiểu vấn đề:

1. Task chạy trên worker thiếu context mà nó cần.
2. Task chạy trên caller bỗng thấy/ghi vào context của request, trong khi thiết kế ban đầu không dự kiến.

Tránh dựa vào implicit ThreadLocal cho logic nghiệp vụ hoặc quyền truy cập. Truyền dữ liệu cần thiết qua tham số, xác định scope của security context, và kiểm thử cả hai đường worker/caller.

### Thread name, blocking và event-loop

`setThreadNamePrefix("report-")` chỉ đặt tên cho **worker của pool**. Khi CallerRuns kích hoạt, log có thể ghi tên như `http-nio-8080-exec-...` hay tên thread khác do hệ thống gọi, không phải `report-...`. Không sử dụng prefix để suy ra chắc chắn một job chưa chạy.

Trong Spring MVC (Servlet), caller có thể là request processing thread: chạy job dài sẽ chiếm một thread phục vụ request. Trong ứng dụng reactive dùng event-loop, việc gọi một executor với CallerRuns từ event-loop để chạy task blocking có thể gây ảnh hưởng nghiêm trọng đến nhiều request. Kể cả với virtual thread, chạy trực tiếp vẫn làm thời gian hoàn tất của caller tăng và cần hiểu tác động lên tài nguyên.

## 12. Reentrancy, khóa và nguy cơ deadlock

CallerRuns làm việc bị từ chối trở thành **một lời gọi hàm lồng trong `execute()`**, vì vậy bất kỳ trạng thái/khóa nào caller đang giữ sẽ tiếp tục tồn tại trong khi body chạy.

Rủi ro có thể gặp:

- Caller đang giữ một lock; task chạy inline rồi đợi một worker khác cần lock đó → deadlock hoặc tắc nghẽn.
- Caller tạo một latch/future rồi dự định release/chờ ở những dòng **sau `execute()`**, nhưng task inline lại đang chờ release từ caller → cùng một thread tự chặn chính mình.
- Task tự submit thêm task vào cùng executor khi bão hòa; những task lồng nhau cũng chạy trên caller, có thể tạo chuỗi gọi đệ quy rất sâu hoặc thay đổi thứ tự side effect.
- Code vốn dựa vào giả định “ngay sau `execute` sẽ chạy cleanup/commit/giải phóng permit” có thể không thực hiện sớm được, vì `execute` đang chạy task nặng.

Ví dụ **mẫu lỗi khái niệm**:

~~~java
CountDownLatch ready = new CountDownLatch(1);
executor.execute(() -> {
    try {
        ready.await();  // nguy hiểm nếu task bị CallerRuns
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
    }
});
ready.countDown();      // không tới được nếu execute đang chờ vô hạn
~~~

Đây là **đoạn minh họa bên trong method**, không phải chương trình độc lập. Trong trạng thái overload, task có thể chạy inline rồi chờ mã `countDown()` sau lời gọi `execute()`, tạo deadlock. Với worker execution, đường này có thể hoạt động, khiến lỗi không xuất hiện trong test tải thấp.

Nếu dùng CallerRuns, thiết kế task **độc lập với caller sau thời điểm submit**, tránh block chờ caller, tránh giữ lock lâu và kiểm soát đệ quy.

## 13. Shutdown là góc khuất có thể làm mất công việc

Theo hợp đồng JDK, `CallerRunsPolicy` chỉ thực thi khi executor **chưa shutdown**. Khi shutdown, handler bỏ task mà không ném exception. Điều này đặc biệt nguy hiểm trong các tình huống:

- Rolling deployment hoặc ApplicationContext đang đóng.
- Request tới ngay sát thời điểm ứng dụng ngừng nhận việc.
- Một producer vẫn gửi việc sau khi executor bị đóng.
- Job bắt buộc được xử lý nhưng chỉ được lưu trong RAM/queue nội bộ.

Ví dụ Java ở trên kiểm tra cả `shutdownTaskRan=false` và `futureDoneAfterDiscard=false`, cho thấy `execute`/`submit` **trả về bình thường không đủ chứng minh công việc đã chạy hay sẽ chạy**.

Với job phải bảo đảm thực thi:

1. Lưu yêu cầu ở nơi bền vững, có mã job và trạng thái.
2. Chỉ trả “đã nhận” theo hợp đồng khi thao tác ghi bền vững thật sự thành công.
3. Để worker lấy việc từ kho đó khi có capacity; có retry giới hạn, backoff, dead-letter/failure state và idempotency.
4. Nếu không thể tiếp nhận yêu cầu, trả phản hồi rõ ràng (ví dụ HTTP 503 hoặc 429 tùy nguyên nhân).
5. Thiết kế drain/shutdown để không làm mất job đã nhận nhưng chưa chạy.

Trong hệ thống nhiều replica, một `ThreadPoolExecutor` chỉ quản lý thread của **một tiến trình JVM**, không thể đại diện cho một hàng đợi bền vững dùng chung.

## 14. Quan sát và đo đạc CallerRuns trong production

Nếu chỉ đo số thread active và số task hoàn thành của pool, có thể **không nhìn thấy những tác vụ chạy trực tiếp trên caller**. Những tác vụ này không phải worker task thông thường nên số đếm nội bộ của pool như `getCompletedTaskCount()` hoặc các hook `beforeExecute/afterExecute` không nhất thiết bao phủ chúng.

Các số đo nên cân nhắc:

| Tín hiệu | Vì sao quan trọng |
| --- | --- |
| Số lần handler đi vào nhánh caller-runs | Biết tần suất thực sự chuyển công việc sang caller |
| Tổng thời gian caller chạy task và phân phối p95/p99 | Xác định chi phí áp lên request/producer |
| Active worker, current pool size, queue size/capacity | Phân biệt đang đầy queue với cấu hình khác |
| Request latency, timeout, số request đang xử lý | Phát hiện overload lan sang HTTP |
| Job wait time, execution duration, job failure | Không nhầm độ trễ queue với độ trễ body |
| Số tác vụ bị bỏ khi shutdown | Phát hiện tình trạng im lặng mất job |
| CPU, GC, database connections, downstream saturation | Đánh giá tổng áp lực tài nguyên khi nhiều caller tự chạy |

Một handler tùy biến có thể đếm và đo thời gian caller-runs, nhưng phải **giữ đúng semantics shutdown** hoặc cố ý thay bằng semantics báo lỗi. Ví dụ dưới đây là **đoạn minh họa trong phần cấu hình executor**, với `callerRunCount` là `LongAdder` đã được khởi tạo và đăng ký làm metric theo thiết kế ứng dụng:

~~~java
executor.setRejectedExecutionHandler((task, pool) -> {
    if (pool.isShutdown()) {
        throw new java.util.concurrent.RejectedExecutionException(
                "Executor is shutting down");
    }
    callerRunCount.increment();
    task.run();
});
~~~

Đoạn này **không phải `CallerRunsPolicy` thuần**: nó thay đổi hợp đồng shutdown bằng cách ném exception để tránh mất việc im lặng. Với Spring `ThreadPoolTaskExecutor`, exception từ rejection handler có thể được chuyển thành `TaskRejectedException` khi caller gọi API của Spring. Nếu muốn đo thời gian, đặt `long start = System.nanoTime()` ngay trước `task.run()` rồi ghi metric trong `finally`. Chỉ thêm logging/metric nhẹ ở handler; I/O nặng trong handler sẽ khiến caller chậm hơn nữa.

### Không kết luận từ số pool worker

Ví dụ `pool.getActiveCount()==4`, `maximumPoolSize==4` không đồng nghĩa chỉ có bốn task đang chạy; năm request thread có thể đang đồng thời thực thi năm caller-runs task khác. Nếu cần thống kê tổng mức song song, instrument ngay ở ranh giới thực thi task và sử dụng các phép đếm thread-safe phù hợp.

## 15. Kiểm thử cần bao phủ đường worker lẫn đường caller

Test chỉ chạy trong điều kiện queue còn rỗng sẽ bỏ sót nhiều vấn đề. Một bộ kịch bản có ích:

| Kịch bản | Điều cần xác minh |
| --- | --- |
| Pool còn capacity | Tác vụ được worker nhận, không chạy inline chỉ vì có `CallerRunsPolicy` |
| Một worker đang chờ latch, queue đã đầy | Task tiếp theo chạy trên chính thread gọi `execute()` |
| Task caller-runs cần thời gian dài | Lời gọi submit chỉ trở về sau khi body hoàn thành; latency của caller tăng |
| Task caller-runs ném unchecked exception với `execute(Runnable)` | Lỗi có thể xuất hiện tại call stack của caller |
| `submit(Callable)` khi bão hòa | Future có thể hoàn tất sau khi body chạy inline; exception được lưu theo semantics Future |
| Executor đã shutdown | Task mới bị bỏ im lặng theo JDK `CallerRunsPolicy`; không coi return bình thường là accepted |
| Nhiều request threads cùng submit | Có thể có nhiều caller-runs đồng thời ngoài giới hạn worker pool |
| Gửi task khi đang giữ lock/transaction | Không phát sinh self-deadlock hoặc side effect khác giữa worker/caller |
| `@Async("reportExecutor")` khi overload | Xác nhận thời gian phản hồi và đúng executor; không giả định luôn chạy thread khác |
| Graceful shutdown/restart | Các job đã nhận theo hợp đồng bền vững không bị mất hoặc bị xử lý trùng thiếu kiểm soát |

Cách dựng pool bão hòa **không dùng `Thread.sleep()`**: giữ worker bằng latch, chờ `workerStarted`, gửi một job lấp queue, sau đó gửi job cần kiểm thử. Dùng timeout chỉ như chốt để test không treo vô hạn nếu lỗi. Test phải giải phóng latch và đóng executor trong `finally` để không làm CI giữ lại worker non-daemon.

Với Spring, nếu tự khởi tạo `ThreadPoolTaskExecutor` trong integration test, phải gọi `initialize()` rồi `shutdown()`. Nếu dùng bean Spring, để container sở hữu lifecycle. Khi test web response, assert đúng status và deadline ở cả tải thường lẫn overload.

## 16. Khi nào nên dùng CallerRunsPolicy?

**Tình huống phù hợp:** một tiến trình batch có **producer tuần tự**, công việc ngắn/giới hạn thời gian, task an toàn khi chạy trên chính producer, không giữ lock phụ thuộc producer, không cần phân tách thread context, và có chiến lược shutdown rõ ràng. CallerRuns có thể giảm tốc độ đưa việc vào queue mà không cần cơ chế phức tạp.

**Tình huống cần cân nhắc kỹ:** request thread trong Spring MVC giao một job nặng. CallerRuns sẽ làm request mất khả năng trả lời nhanh khi bão hòa; người dùng có thể gặp timeout ngay trong lúc API đang chịu tải nhất.

**Tình huống nên tránh:** event-loop dùng cho reactive request gửi task blocking, công việc có side effect phải thực thi đúng một lần, job cần bảo đảm qua restart, logic phụ thuộc transaction context của thread, hoặc tác vụ có thể chờ tín hiệu chỉ caller mới cung cấp.

### Ma trận lựa chọn

| Mục tiêu hệ thống | Lựa chọn thường thích hợp hơn |
| --- | --- |
| Producer batch tuần tự phải tự giảm tốc khi downstream chậm | CallerRuns có thể phù hợp nếu task chạy trên caller an toàn |
| API phải giữ deadline, không được block để làm job dài | Bounded executor + `AbortPolicy` + phản hồi quá tải rõ ràng |
| Bảo đảm job không mất khi shutdown hoặc restart | Durable queue/job table và worker tiêu thụ, với idempotency |
| Giới hạn tổng số task chạy đồng thời kể cả caller | Admission control, semaphore hoặc consumer pool cố định |
| Dữ liệu metrics best-effort có thể bỏ | Chính sách drop có quan sát, nếu đã chấp nhận mất |
| Tác vụ cần transaction/context rõ ràng | Thiết kế ranh giới thực thi và context propagation độc lập với chính sách tải |

Chính sách overload nên là **một phần hợp đồng ứng dụng**, được review cùng yêu cầu latency và durability. Không nên chỉ đổi handler vì benchmark thấy throughput tăng.

## 17. Các lỗi thường gặp

1. **Cho rằng đặt `CallerRunsPolicy` vẫn luôn bất đồng bộ.** Nhánh quá tải gọi `run()` trực tiếp trên thread gửi.
2. **Cho rằng không ném exception tức task chắc chắn được nhận.** Khi shutdown, chính sách này bỏ task mà có thể không báo lỗi.
3. **Đặt queue quá lớn rồi mong policy điều tiết.** Task có thể tích hàng nghìn phần tử thay vì kích hoạt CallerRuns.
4. **Tưởng `maximumPoolSize` là trần tổng số task đang chạy.** Caller threads có thể làm việc đồng thời ngoài worker pool.
5. **Dùng trong request handler nhạy latency nhưng chỉ đo tải thấp.** p95/p99 có thể tăng khi queue đầy.
6. **Chạy task blocking trên reactive event-loop.** Task inline có thể chặn event-loop, làm ảnh hưởng nhiều request.
7. **Dùng `ThreadLocal`/transaction context mà không kiểm tra cả hai nhánh.** Worker và caller có môi trường thực thi khác nhau.
8. **Phát hành tín hiệu cần thiết sau `execute()` trong khi task có thể chờ tín hiệu đó.** Có nguy cơ tự deadlock khi caller-runs.
9. **Không dọn exception trong tác vụ.** `run()` có thể ném trực tiếp trên caller, khiến đường submit thất bại ngoài dự kiến.
10. **Chỉ dựa vào `getCompletedTaskCount()` để báo tổng công việc.** Tác vụ chạy trên caller không thuộc thống kê worker thông thường.
11. **Dùng `Future.get()` vô hạn sau khi submit vào executor đã shutdown.** Với CallerRuns, Future bị bỏ có thể không hoàn tất.
12. **Tưởng policy tạo backpressure cho toàn bộ hệ thống.** Nó giảm tốc từng submitter, nhưng nhiều submitter vẫn có thể làm việc song song.
13. **Gắn policy vào nhầm Spring executor.** Dùng qualifier và xác minh `@Async`/TaskExecutor chọn đúng bean.
14. **Retry trực tiếp tác vụ có side effect không idempotent.** Rủi ro lặp hành động khi caller hoặc client không biết kết quả cuối.
15. **Test bằng thời gian ngủ ngẫu nhiên.** Dùng latch để kiểm soát lúc worker bận và queue đầy.

## 18. Câu hỏi tự kiểm tra

1. Điều kiện nào khiến `ThreadPoolExecutor` gọi `RejectedExecutionHandler`, thay vì xếp việc vào queue?
2. Vì sao trong demo `onCaller=true` và `order=before>inCaller>after` cho thấy `execute()` đã bị đồng bộ hóa theo thời gian chạy task?
3. Với pool tối đa 4 worker và 20 request threads cùng submit lúc bão hòa, có thể có hơn 4 task đang chạy không? Vì sao?
4. Khi executor đã shutdown, `CallerRunsPolicy` xử lý task mới thế nào? Điều này ảnh hưởng `Future.get()` ra sao?
5. Vì sao p95/p99 của một API có thể tăng mạnh khi dùng CallerRuns dù p50 gần như không đổi?
6. Nếu một task cần transaction của request, sự khác nhau giữa đường worker và caller-runs dẫn tới rủi ro gì?
7. Làm sao kiểm thử cả nhánh worker lẫn caller mà không dùng `Thread.sleep()`?
8. Với một yêu cầu xuất báo cáo bắt buộc không mất, vì sao một queue in-memory cùng CallerRuns chưa đủ?
9. Vì sao `getActiveCount()` không phản ánh tất cả caller-runs task đang chạy?
10. Nếu cần vừa bounded concurrency vừa phản hồi quá tải rõ ràng, bạn sẽ chọn CallerRuns hay admission control + AbortPolicy? Giải thích theo deadline và SLA.

## 19. Tài liệu tham khảo chính thức

- [Java SE 17 — ThreadPoolExecutor.CallerRunsPolicy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.CallerRunsPolicy.html)
- [Java SE 17 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [Java SE 17 — RejectedExecutionHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RejectedExecutionHandler.html)
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Spring Framework — ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)

**Ghi nhớ:** `CallerRunsPolicy` chuyển chi phí thực thi một tác vụ bị từ chối sang **thread gửi việc**, qua đó làm producer chậm lại nhưng cũng có thể tăng mạnh thời gian phản hồi request và lan tải sang các caller khác. Cần xem **deadline, context, shutdown, observability và bảo đảm không mất việc** trước khi chọn chính sách này.