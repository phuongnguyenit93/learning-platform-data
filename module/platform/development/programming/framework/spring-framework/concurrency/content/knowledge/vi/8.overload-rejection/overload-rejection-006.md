# Không để Future chờ vô hạn do chính sách loại bỏ không hoàn tất tác vụ

## 1. Bài toán: executor bỏ việc, Future vẫn đang đợi

Giả sử một API Spring nhận yêu cầu tạo báo cáo, đưa tác vụ vào `ThreadPoolTaskExecutor` và trả một `Future`/`CompletableFuture` để các thành phần khác chờ kết quả. Khi hệ thống quá tải, một cấu hình như `DiscardPolicy` có thể **âm thầm bỏ tác vụ**. Caller vẫn nhận được đối tượng `Future` từ `submit` nhưng tác vụ chưa từng chạy, không có ai gọi logic hoàn tất và cũng không có exception/cancellation được ghi trên Future.

Khi đó:

- `future.isDone() == false` có thể kéo dài mãi nếu không có tác nhân khác hoàn tất hoặc hủy Future.
- `future.get()` **không có timeout** có thể chặn vô hạn.
- `future.get(2, TimeUnit.SECONDS)` giúp người gọi dừng chờ sau khoảng thời gian giới hạn bằng `TimeoutException`, nhưng **không tự biến Future thành DONE/CANCELLED**.
- `CompletableFuture.join()` và các stage phụ thuộc cũng có thể chờ vô hạn; nếu task dùng để hoàn thành Future bị loại bỏ, lời gọi `thenApply`/`allOf` có thể không bao giờ chạy xong.

Lỗi thường khó thấy trong môi trường phát triển vì queue hiếm khi đầy. Trên production, chỉ cần một worker chậm, hàng đợi hữu hạn và nhiều tác vụ đến cùng lúc là chính sách từ chối được kích hoạt.

**Nguyên tắc thiết kế:** nếu bên ngoài đang đợi một kết quả, **mọi nhánh kết thúc** phải được quan sát: thành công, lỗi nghiệp vụ, từ chối nhận việc, hủy, timeout và dừng ứng dụng. Tránh chính sách bỏ việc không thông báo khi đầu ra là `Future` mà người khác sẽ đợi.

## 2. Phân biệt task, Future và việc “đã submit”

### 2.1. `execute` khác `submit`

Với Java `ThreadPoolExecutor`:

- `execute(Runnable)` đề nghị executor chạy một `Runnable` và có kiểu trả về `void`.
- `submit(Callable<T>)`/`submit(Runnable)` tạo một đối tượng kiểu `RunnableFuture` (thường là `FutureTask`), gửi wrapper đó qua `execute` và trả `Future` cho caller.
- Khi wrapper thực sự chạy, nó đánh dấu thành công hoặc lỗi. Khi bị `Future.cancel(...)`, nó chuyển sang trạng thái canceled. Nếu wrapper **chưa từng chạy và không ai cancel**, Future thường vẫn ở trạng thái ban đầu.
- `submit` trả về được **không bảo đảm** executor đã thật sự nhận việc: một `RejectedExecutionHandler` được cấu hình để im lặng có thể khiến `execute` trả về bình thường dù tác vụ vừa bị bỏ.

Vì vậy, “đã có `Future`” không đồng nghĩa “job sẽ hoàn tất”. Khi tác vụ được tạo bởi `CompletableFuture.supplyAsync(supplier, executor)`, một wrapper cũng phải được chạy để hoàn thành stage; executor im lặng loại wrapper thì CompletableFuture có thể tiếp tục `isDone() == false`.

### 2.2. Các trạng thái cần phân biệt

| Tình huống | `isDone()` | `get()` | Ý nghĩa |
| --- | --- | --- | --- |
| Chưa bắt đầu nhưng **đang nằm hợp lệ trong queue** | `false` | Chờ | Có thể được thực thi sau |
| Đang thực thi | `false` | Chờ | Tiến độ phụ thuộc task |
| Thành công | `true` | Trả kết quả | Terminal |
| Task ném exception qua `FutureTask` | `true` | `ExecutionException` | Terminal lỗi |
| Được cancel thành công | `true` và `isCancelled() == true` | `CancellationException` | Terminal hủy |
| Bị `DiscardPolicy` bỏ im lặng | Thường `false` mãi | Chờ mãi nếu không timeout | **Mất tín hiệu hoàn tất** |
| Bị `DiscardOldestPolicy` đẩy khỏi queue mà không cancel | Thường `false` mãi | Chờ mãi nếu không timeout | **Future cũ bị mồ côi** |

Một Future chưa hoàn tất không tự cho biết “đang xếp hàng”, “đang chạy” hay “đã thất lạc”. Cần kết hợp metric của pool, nhật ký rejection, trạng thái job và thời điểm gửi việc.

### 2.3. Vì sao executor từ chối?

`ThreadPoolExecutor` gọi `RejectedExecutionHandler` khi không thể nhận thêm việc (thường vì đã đạt giới hạn số worker và queue đầy) hoặc executor đã shutdown. Với Spring `ThreadPoolTaskExecutor`, `corePoolSize`, `maxPoolSize`, `queueCapacity` và handler quyết định hành vi thực tế.

Ví dụ pool có `core=1`, `max=1`, queue chứa tối đa một tác vụ: tác vụ đầu đang chạy; tác vụ thứ hai xếp hàng; tác vụ thứ ba bị từ chối. Nếu queue không giới hạn, tác vụ mới có thể xếp hàng rất lâu trước khi có rejection; không nên lấy việc “chưa từng rejected” làm bằng chứng là hệ thống có đủ năng lực.

## 3. Bốn chính sách từ chối của ThreadPoolExecutor

| Chính sách JDK | Khi pool bão hòa | Nguy cơ với Future |
| --- | --- | --- |
| `AbortPolicy` (mặc định của `ThreadPoolExecutor`) | Ném `RejectedExecutionException` ngay tại chỗ gửi | Caller nhận biết được việc từ chối, có thể trả lỗi/hoàn tất Future ngoại lệ |
| `CallerRunsPolicy` | Chạy tác vụ trên **luồng gửi** nếu executor chưa shutdown | Không mất tác vụ do bão hòa, nhưng có thể chặn HTTP caller; **khi đã shutdown thì bỏ im lặng** |
| `DiscardPolicy` | Bỏ tác vụ đang bị từ chối, **không ném lỗi** | `Future` của tác vụ vừa gửi có thể không bao giờ completed |
| `DiscardOldestPolicy` | Bỏ tác vụ **đầu queue** rồi thử gửi lại tác vụ mới nếu chưa shutdown | Future **của task cũ** có thể chờ vô hạn; khi shutdown, tác vụ mới cũng bị bỏ |

`DiscardOldestPolicy` không phải “đổi thứ tự ưu tiên” theo nghĩa an toàn. Nó thường lấy `Runnable` đầu queue ra bằng `poll()` mà **không hủy Future tương ứng**. Nếu queue có `FutureTask`, Future của người đã gửi task cũ có thể không bao giờ chuyển trạng thái terminal. Ngay cả khi tác vụ mới được chấp nhận, hệ thống đã làm mất một lời hứa kết quả của caller khác.

**Chú ý shutdown:** `CallerRunsPolicy` và `DiscardOldestPolicy` trong JDK cũng có nhánh bỏ tác vụ khi executor đã shutdown. Vì thế `CallerRunsPolicy` không phải bằng chứng rằng *mọi task submit sẽ luôn hoàn thành*. Với yêu cầu kết quả chắc chắn, ưu tiên cơ chế **từ chối minh bạch** và ghi nhận trạng thái terminal.

## 4. Java 17: tái hiện lỗi một cách xác định

Ví dụ độc lập dưới đây dùng `CountDownLatch` để giữ worker duy nhất đang bận, đặt task thứ hai vào queue một phần tử, rồi gửi task thứ ba. Không dựa vào `Thread.sleep` để “hy vọng” pool bão hòa. Hai chính sách được kiểm thử lần lượt:

1. `DiscardPolicy` bỏ task **mới**, Future của task mới không hoàn tất.
2. `DiscardOldestPolicy` loại task **cũ đang đợi**, Future cũ không hoàn tất, task mới chạy.

Lưu thành file **`DroppedFutureDemo.java`**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionHandler;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public final class DroppedFutureDemo {
    public static void main(String[] args) throws Exception {
        demonstrate("DiscardPolicy",
                new ThreadPoolExecutor.DiscardPolicy(), false);
        demonstrate("DiscardOldestPolicy",
                new ThreadPoolExecutor.DiscardOldestPolicy(), true);
    }

    private static void demonstrate(
            String name, RejectedExecutionHandler handler,
            boolean dropsQueuedTask) throws Exception {

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0, TimeUnit.SECONDS,
                new ArrayBlockingQueue<>(1),
                handler);

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<String> running = pool.submit(() -> {
                started.countDown();
                release.await();
                return "running";
            });

            // Chắc chắn worker đã nhận task đầu và đang chờ release.
            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker did not start");
            }

            // Queue capacity = 1: queued nằm trong hàng đợi.
            Future<String> queued = pool.submit(() -> "queued");

            // Worker bận và queue đầy: chính sách rejection chạy.
            Future<String> newest = pool.submit(() -> "newest");

            release.countDown();

            System.out.println(name + ": running="
                    + running.get(5, TimeUnit.SECONDS));

            Future<String> kept = dropsQueuedTask ? newest : queued;
            Future<String> dropped = dropsQueuedTask ? queued : newest;

            System.out.println(name + ": kept="
                    + kept.get(5, TimeUnit.SECONDS));

            // Không dùng dropped.get() vô hạn. Đây là hạn chờ của caller.
            try {
                dropped.get(100, TimeUnit.MILLISECONDS);
                System.out.println(name + ": UNEXPECTED COMPLETION");
            } catch (TimeoutException expected) {
                System.out.println(name + ": dropped TIMEOUT, done="
                        + dropped.isDone());
            }

            // Chủ động chuyển Future thất lạc sang trạng thái canceled.
            dropped.cancel(false);
            System.out.println(name + ": canceled="
                    + dropped.isCancelled());
        } finally {
            release.countDown();
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Pool did not stop");
            }
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac -encoding UTF-8 DroppedFutureDemo.java
java DroppedFutureDemo
~~~

Stdout của chương trình (không gồm dòng từ môi trường chạy):

~~~text
DiscardPolicy: running=running
DiscardPolicy: kept=queued
DiscardPolicy: dropped TIMEOUT, done=false
DiscardPolicy: canceled=true
DiscardOldestPolicy: running=running
DiscardOldestPolicy: kept=newest
DiscardOldestPolicy: dropped TIMEOUT, done=false
DiscardOldestPolicy: canceled=true
~~~

**Giải thích vì sao output xác định:** latch `started` bảo đảm worker đã vào `running` trước khi gửi `queued`. Latch `release` giữ worker không lấy task khác trước khi tác vụ thứ ba bị từ chối. Vì pool chỉ có một worker và một ô queue, điều kiện rejection là xác định. Chính sách giữ/bỏ task theo luật đã nêu; hai `get(5, SECONDS)` là hạn bảo vệ phép thử, còn `get(100, MILLISECONDS)` chứng minh Future bị bỏ vẫn `isDone() == false`. Cuối cùng `cancel(false)` làm Future chuyển trạng thái canceled; nó không “khôi phục” công việc đã bị thất lạc.

Sau `cancel(false)` thành công, nếu gọi `dropped.get()` thì sẽ có `CancellationException` thay cho chờ mãi. Phương thức `cancel` trả boolean phản ánh nỗ lực hủy; muốn biết trạng thái cuối thì đọc `isCancelled()`. Ví dụ không cần network, DB hoặc Spring Boot để tái hiện nguyên nhân gốc; Spring executor bọc JDK pool có cùng loại rủi ro nếu dùng các rejection handler này.

## 5. Cách sửa ưu tiên: từ chối có tín hiệu

### 5.1. Dùng AbortPolicy khi caller cần biết việc có được nhận hay không

Thay `DiscardPolicy` bằng `AbortPolicy`, `ThreadPoolExecutor` sẽ ném `RejectedExecutionException` khi pool đã bão hòa. Với `submit`, exception có thể ném **ngay khi gửi**, trước khi có Future trả về:

~~~java
// Trích đoạn minh họa khi pool đang bão hòa; không phải class đầy đủ.
try {
    Future<String> future = pool.submit(() -> "report");
    // Chỉ lưu future sau khi submit trả về bình thường.
} catch (java.util.concurrent.RejectedExecutionException ex) {
    // Báo quá tải và đánh dấu request/job bị từ chối.
}
~~~

Không dùng `try { future.get() }` để phát hiện rejection sau khi đã bật `DiscardPolicy`: Future có thể không bao giờ có kết quả hay lỗi. Cần đổi **chính sách acceptance** chứ không chỉ đặt một `catch` sau `get()`.

Trong Spring Framework, `ThreadPoolTaskExecutor` có thể ném `org.springframework.core.task.TaskRejectedException` khi từ chối bằng chính sách mặc định kiểu abort. Ở lớp API, trả HTTP `503 Service Unavailable` hoặc `429 Too Many Requests` tùy semantics và chính sách rate limit; không trả `202 Accepted` như thể hệ thống đã tiếp nhận công việc bền vững.

### 5.2. Không bỏ quên Future khi chủ động loại bỏ task

Nếu nghiệp vụ cho phép **thả bớt công việc ít quan trọng**, phải có cơ chế để người đã gửi biết task không còn được chạy:

- Với `FutureTask` bị loại, gọi `cancel(false)` hoặc hoàn tất bằng một exception thông qua một wrapper/gateway quản lý kết quả.
- Với `CompletableFuture` do ứng dụng sở hữu, dùng `completeExceptionally(new RejectedExecutionException(...))` hoặc một trạng thái lỗi/hủy rõ ràng; không phải mọi `Runnable` do `CompletableFuture` tạo đều là `Future<?>` có thể cast để hủy.
- Ghi nguyên nhân `REJECTED`, `DROPPED` hoặc `CANCELLED` vào trạng thái job, metric và log để upstream có thể retry hoặc thông báo cho người dùng.
- Với `DiscardOldestPolicy`, cần xử lý **task vừa bị đẩy khỏi queue**, không chỉ task mới bị từ chối. Do nhiều race (shutdown, polling của worker, nhiều submitters), custom handler cần được kiểm thử kỹ; nếu không cần ưu tiên task mới, nên dùng `AbortPolicy` đơn giản hơn.

Javadoc JDK 17 của `DiscardOldestPolicy` cũng minh họa handler tự lấy task cũ khỏi queue và hủy nó nếu là `Future<?>`. Tuy nhiên chỉ cast/cancel `Runnable` lấy từ queue có thể **chưa đủ** cho wrapper của `CompletableFuture`, callback hoặc một hệ thống job có trạng thái riêng. Phải chọn thiết kế gắn được identity tác vụ với Future/status cần hoàn tất.

## 6. Lớp phòng vệ thứ hai: hạn chờ và terminal state

### 6.1. Future.get(timeout) chỉ giới hạn thời gian chờ

~~~java
// Trích đoạn minh họa bên trong phương thức có thể throws InterruptedException.
try {
    String result = future.get(3, TimeUnit.SECONDS);
    consume(result);
} catch (TimeoutException ex) {
    boolean canceled = future.cancel(true);
    recordTimeout(canceled);
} catch (java.util.concurrent.ExecutionException ex) {
    recordFailure(ex.getCause());
} catch (java.util.concurrent.CancellationException ex) {
    recordCancellation();
}
~~~

`consume`/`recordTimeout`/`recordFailure`/`recordCancellation` là phương thức nghiệp vụ giả định: snippet này **không độc lập**. Hạn `3 giây` chỉ có nghĩa caller chờ tối đa khoảng đó cho `get`. `cancel(true)` gửi yêu cầu hủy và có thể interrupt worker, **không bảo đảm** task đang chạy dừng được, rollback DB hoặc không tiếp tục ghi file. `Future.get(timeout)` tự nó không hủy task.

Khi cần SLA thật, phải có cả **queue-wait budget**, **execution timeout**, timeout I/O/DB và idempotency để tránh một job bị retry khi bản gốc vẫn tiếp tục chạy sau khi caller hết hạn chờ.

### 6.2. CompletableFuture.orTimeout() chuyển Future sang trạng thái terminal

~~~java
// Trích đoạn minh họa: future được ứng dụng tạo và sở hữu.
CompletableFuture<String> future = new CompletableFuture<>();
future.orTimeout(3, TimeUnit.SECONDS);
~~~

Nếu sau 3 giây chưa hoàn tất, chính `CompletableFuture` đó sẽ hoàn tất **exceptionally** với `TimeoutException`; `join()` có thể ném `CompletionException` bọc nguyên nhân. `orTimeout` trả về **chính future đang được cấu hình**, không tạo một bản sao độc lập. Đây là cơ chế tránh một `CompletableFuture` trong bộ nhớ ở trạng thái pending mãi.

Nhưng `orTimeout` **không dừng task thực sự**, không gỡ queued task khỏi executor, không tự cancel `FutureTask` khác và không hoàn tất một job đã lưu DB. Task có thể vẫn tiếp tục side effects sau khi future timeout; một lời gọi `complete(...)` đến muộn sẽ không ghi đè kết quả terminal đã có.

`completeOnTimeout(value, timeout, unit)` hoàn tất bình thường bằng giá trị thay thế, thích hợp cho một số cache/fallback **chỉ khi nghiệp vụ cho phép**. Không nên biến báo cáo tài chính bị mất thành một kết quả thành công giả để che giấu quá tải.

### 6.3. Hạn chờ không thay thế rejection handling

Một phương án vững hơn gồm ba bước:

1. **Submission:** dùng handler ném lỗi và ghi nhận từ chối ngay khi `execute/submit` không nhận việc.
2. **Execution:** task hoàn tất kết quả hoặc exception bằng `try/catch/finally`, không để đường lỗi bị bỏ quên.
3. **Deadline:** đặt hạn chờ ở client và/hoặc timeout trên CompletableFuture, ghi lại trạng thái timeout; quản lý task đang chạy/đang xếp hàng khi hết hạn.

Nếu chỉ triển khai bước 3, hệ thống sẽ **thoát tình trạng chờ vô hạn cho caller** nhưng vẫn âm thầm làm mất tác vụ và có thể để rò rỉ trạng thái nghiệp vụ.

## 7. Kết hợp đúng với Spring ThreadPoolTaskExecutor

### 7.1. Bean executor có giới hạn và AbortPolicy

Ví dụ Spring Framework 6.x chạy trên Java 17, đặt trong một class `@Configuration` (đây là snippet cấu hình, không phải chương trình khởi động độc lập):

~~~java
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class ReportPoolConfig {
    @Bean("reportExecutor")
    public ThreadPoolTaskExecutor reportExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(4);
        pool.setQueueCapacity(20);
        pool.setThreadNamePrefix("report-");
        pool.setRejectedExecutionHandler(new ThreadPoolExecutor.AbortPolicy());
        pool.setWaitForTasksToCompleteOnShutdown(true);
        pool.setAwaitTerminationSeconds(15);
        return pool;
    }
}
~~~

Với một `@Bean` Spring quản lý, container xử lý lifecycle/initialization của `ThreadPoolTaskExecutor`. Nếu tự khởi tạo ngoài Spring thì phải `initialize()` trước khi chạy. Pool này sẽ dùng tối đa bốn worker và queue 20 theo logic của `ThreadPoolExecutor`; khi queue đầy và toàn bộ worker ở giới hạn, việc nhận task mới thất bại theo `AbortPolicy`.

**Không đánh đồng `maxPoolSize=4` với việc luôn có bốn luồng:** pool ban đầu tăng tới core=2; sau đó ưu tiên queue, và chỉ cân nhắc thêm worker khi queue đã đầy. Khi quá tải phải xử lý exception tại nơi submit, vì nếu không API có thể trả 500 không kiểm soát hoặc đánh dấu sai một job là đã được chấp nhận.

### 7.2. Gateway trả CompletableFuture có đường kết thúc đầy đủ

Ví dụ này là **một class Spring service hoàn chỉnh** để ghép với `ReportPoolConfig` trong cùng ứng dụng Spring đã cấu hình component scanning:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.TaskRejectedException;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Service;

@Service
public class ReportGateway {
    private final ThreadPoolTaskExecutor executor;

    public ReportGateway(
            @Qualifier("reportExecutor") ThreadPoolTaskExecutor executor) {
        this.executor = executor;
    }

    public CompletableFuture<String> submit(String reportId) {
        CompletableFuture<String> outcome = new CompletableFuture<>();

        try {
            executor.execute(() -> {
                try {
                    // Thay bằng nghiệp vụ thật, có timeout DB/HTTP riêng.
                    String location = "reports/" + reportId + ".csv";
                    outcome.complete(location);
                } catch (Throwable ex) {
                    // Đảm bảo nhánh lỗi có kết quả quan sát được.
                    outcome.completeExceptionally(ex);
                }
            });
        } catch (TaskRejectedException ex) {
            // AbortPolicy: lỗi phát sinh ngay lúc gửi task.
            outcome.completeExceptionally(ex);
        }

        // Phòng vệ cuối: Future không pending quá 30s trong bộ nhớ.
        return outcome.orTimeout(30, TimeUnit.SECONDS);
    }
}
~~~

`execute` có thể ném `TaskRejectedException` lúc pool bão hòa; trong nhánh ấy `outcome` được hoàn tất exceptionally, cho phép client kiểm tra và trả 503. Nếu xử lý nghiệp vụ trong worker bị lỗi, `completeExceptionally` giữ lỗi để downstream quan sát. `orTimeout` bảo vệ lời gọi đợi nếu bị kẹt vì lỗi ngoài ý muốn hoặc ai đó đổi handler thành kiểu bỏ im lặng.

**Giới hạn của gateway:** đoạn worker minh họa tạo chuỗi nhanh, chưa lưu job bền vững, chưa thể bảo đảm exactly-once. Nếu future timeout sau khi worker đã bắt đầu, worker vẫn có thể tiếp tục thao tác và ghi side effect. Trong hệ thống có nhiều bước hoặc ghi DB, cần trạng thái job ở kho bền vững, quản lý deadline và tránh job thành công muộn bị client retry gây trùng.

### 7.3. Nếu dùng @Async

~~~java
// Trích đoạn trong Spring-managed service, gọi qua proxy từ bean khác.
@Async("reportExecutor")
public CompletableFuture<String> build(String id) {
    String result = createReport(id);
    return CompletableFuture.completedFuture(result);
}
~~~

Đoạn trên là snippet; `createReport` do ứng dụng định nghĩa. `@EnableAsync` phải được bật, method phải được gọi qua Spring proxy để áp dụng `@Async` trong proxy mode. Executor được chỉ định bằng tên bean, nên chính sách reject/queue của bean đó có ý nghĩa trực tiếp.

Nếu executor ném `TaskRejectedException` khi submit, exception có thể xuất hiện **ngay ở lời gọi qua proxy**; lỗi phát sinh trong worker được truyền theo semantics của `Future/CompletableFuture`. Không giả định rằng mọi lỗi đều được phát sinh khi `future.join()` hoặc mọi lỗi luôn được ném đồng bộ. Với handler bỏ im lặng, lời gọi qua proxy có thể trả một Future không có ai hoàn tất.

## 8. Chọn kiểu kết quả theo yêu cầu thực tế

### 8.1. Không cần kết quả thì có thể bỏ việc, nhưng phải công khai

Một tác vụ telemetry không quan trọng có thể được phép rơi khi quá tải. Khi đó `execute(Runnable)` kiểu fire-and-forget và metric `dropped_total` có thể là lựa chọn chính sách. Nhưng nếu caller cần xác nhận “đã lưu audit log”, “đã gửi email”, “đã tạo báo cáo”, **không được** coi silently dropped như thành công.

Nếu dùng `DiscardOldestPolicy` cho hoạt động như refresh cache (chỉ cần bản mới nhất), vẫn phải giải quyết callback/awaiters của bản cũ nếu chúng tồn tại. Có thể thay đổi kiến trúc để chỉ giữ một trạng thái “latest” với cơ chế coalescing và một CompletableFuture được hoàn tất có kiểm soát thay vì dùng chính sách queue eviction mù.

### 8.2. Muốn bảo đảm xử lý sau restart cần hàng đợi bền vững

`ThreadPoolTaskExecutor` và `Future` là cấu trúc bộ nhớ của **một tiến trình**. Khi pod chết, mọi Future trong JVM đó cũng biến mất. Nếu nghiệp vụ cần không mất job, ghi yêu cầu vào DB/message broker có transaction/ack và cơ chế retry + idempotency.

Một trình tự thường gặp:

1. HTTP POST kiểm tra idempotency key rồi lưu job `PENDING` vào DB.
2. Transaction commit xong mới dispatch qua broker/outbox hoặc worker đáng tin cậy.
3. Worker chuyển job sang `RUNNING` bằng claim có điều kiện, ghi kết quả `DONE` hoặc `FAILED`, có retry/backoff.
4. API GET tra trạng thái job; khi quá hạn có reconciliation để tìm việc bị treo và chuyển sang trạng thái cần retry/failed theo chính sách.

Tương tác với broker/DB không tự cho exactly-once; cần thiết kế idempotent ở side effects và trạng thái chuyển có điều kiện. Dù dùng queue nào, vẫn phải theo dõi việc quá hạn chờ.

## 9. Shutdown và những Future bị bỏ lại

`shutdown()` cho executor có cơ hội xử lý task đã nhận và đang chờ; `shutdownNow()` cố interrupt task đang chạy và trả về danh sách `Runnable` chưa bắt đầu. JDK không tự cam kết hủy tất cả Future ứng với những Runnable bị trả về. Nếu ứng dụng sở hữu một `ThreadPoolExecutor` và chỉ submit `FutureTask`, có thể hủy những Future nằm trong danh sách này:

~~~java
// Trích đoạn minh họa trong code quản lý ThreadPoolExecutor.
for (Runnable queued : pool.shutdownNow()) {
    if (queued instanceof java.util.concurrent.Future<?> future) {
        future.cancel(false);
    }
}
~~~

Việc này giúp `get()` trên các `FutureTask` vừa bị drain thấy `CancellationException`, nhưng **không hủy được task đã bị discard từ trước** và không áp dụng phổ quát cho mọi wrapper của Spring, `CompletableFuture` hoặc broker. Nếu dùng `ThreadPoolTaskExecutor` do Spring quản lý, cấu hình lifecycle/shutdown thích hợp và ghi nhận job chưa hoàn tất ở tầng ứng dụng; đừng tự gọi `shutdownNow()` lên tài nguyên do framework sở hữu mà không có chiến lược.

Một số chính sách xử lý rejection có thể vứt task khi executor đã shutdown. Vì thế kiểm thử đường dừng/deploy lại là quan trọng tương đương thử đầy queue.

## 10. Kiểm thử để bảo đảm không còn Future “mồ côi”

Một test có ích phải **ép pool bão hòa một cách xác định** bằng latch thay vì chỉ submit nhiều task rồi hy vọng race. Với pool core=max=1 và queue=1:

1. Cho task A vào worker và chặn bằng `CountDownLatch`.
2. Gửi task B vào queue, xác minh queue có một phần tử nếu cần.
3. Gửi task C khiến handler rejection chạy.
4. Với `AbortPolicy`, assert caller nhận `RejectedExecutionException` (JDK) hoặc `TaskRejectedException` (Spring) và đã ghi nhận job `REJECTED`.
5. Với chính sách chủ động drop, xác nhận đúng Future bị loại được `cancel` hoặc `completeExceptionally` trong hạn định; không dùng `get()` vô hạn trong test.
6. Nhả latch rồi xác minh task được nhận hoàn tất, task bị loại mang trạng thái terminal, và không có ID nào mắc ở `PENDING` mãi.

Ngoài unit test, theo dõi runtime: số worker active, `getQueueSize()`, rejection rate, queue wait time, task execution latency, số `PENDING` quá hạn, `Future timeout`, tỷ lệ retry, việc thất lạc callback và số job chuyển trạng thái terminal. Đừng chỉ đếm số task hoàn thành vì những task bị bỏ **không đi tới đường hoàn thành** để được tính.

### Ma trận nguyên nhân thường gặp

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng khắc phục |
| --- | --- | --- |
| `submit` trả Future nhưng `get()` mãi không về | `DiscardPolicy` loại tác vụ mới | Dùng AbortPolicy; timeout và terminalize kết quả |
| Task mới chạy nhưng Future task cũ pending | `DiscardOldestPolicy` đẩy task cũ khỏi queue | Tránh policy này hoặc cancel/complete job bị đẩy |
| `CompletableFuture.allOf(...)` không hoàn tất | Một future con không bao giờ terminal | Bound timeout và xử lý từng future; tìm upstream task thất lạc |
| Không thấy `RejectedExecutionException` | Rejection handler im lặng | Audit `setRejectedExecutionHandler` và bean runtime |
| `get(timeout)` đã timeout nhưng `isDone()==false` | Timeout chỉ giới hạn thời gian đợi | Quy định việc cancel/terminal state và xử lý retry |
| `orTimeout` đã bắn nhưng DB vẫn được ghi | Timeout của Future không ngừng worker | Cơ chế cancellation, transaction, idempotency |
| Sau shutdown vẫn có waiter treo | Queued task bị drain/drop mà không cancel Future | Ghi nhận/hủy outstanding tasks, xử lý shutdown |
| Spring trả 202 dù job bị từ chối | Không chuyển rejection thành HTTP/job state | Catch `TaskRejectedException` tại gateway, trả 429/503 |
| Queue liên tục đầy và nhiều task bị loại | Mất cân đối tốc độ đến và năng lực xử lý | Bounded queue, backpressure, rate limit, tối ưu tác vụ |

## 11. Câu hỏi tự kiểm tra

1. Vì sao `ExecutorService.submit(...)` trả về bình thường không bảo đảm task sẽ được chạy khi có `DiscardPolicy`?
2. Trong pool một worker và queue một chỗ, task A đang chạy, B xếp hàng, C mới đến: Future nào có thể bị “mồ côi” với `DiscardPolicy` và với `DiscardOldestPolicy`?
3. Sự khác biệt giữa `future.get(3, SECONDS)` bị `TimeoutException` và `CompletableFuture.orTimeout(3, SECONDS)` là gì?
4. `Future.cancel(true)` có bảo đảm giao dịch DB rollback hoặc tác vụ ngừng ngay không?
5. Tại sao `CallerRunsPolicy` cũng không phải cam kết hoàn tất Future trong trường hợp executor đã shutdown?
6. Spring `ThreadPoolTaskExecutor` dùng `AbortPolicy`: rejection nên được bắt ở vị trí nào và phản hồi HTTP/job status ra sao?
7. Nếu ứng dụng bị kill khi job mới ở queue, một `Future` trong RAM có thay thế được kho lưu job bền vững không?
8. Tại sao metric “completed tasks” không đủ để phát hiện task bị discard?

**Quy tắc thực hành:** khi một API hứa trả kết quả bằng `Future`, hãy coi **silent discard** là một lỗi thiết kế cho tới khi đã có đường thông báo terminal tương ứng. Dùng rejection có tín hiệu, bounded wait, completion/cancellation rõ ràng, và theo dõi trạng thái job qua mọi nhánh để không có người gọi nào bị chặn vô hạn.

## Tài liệu tham khảo

- [Java SE 17 — ThreadPoolExecutor và các rejection policy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [Java SE 17 — DiscardOldestPolicy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.DiscardOldestPolicy.html)
- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Spring Framework 6.2 — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)