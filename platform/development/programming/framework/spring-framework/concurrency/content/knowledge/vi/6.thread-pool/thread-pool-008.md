# Khởi động trước luồng cơ bản bằng prestartAllCoreThreads

Trong Java, một `ThreadPoolExecutor` thường **không tạo ngay toàn bộ core thread khi được khởi tạo**. Theo chính sách mặc định, pool tăng số worker theo nhu cầu khi nhận task đầu tiên. Nếu muốn các core thread được tạo trước để chờ công việc, có thể gọi `prestartAllCoreThreads()`. Với Spring Framework, `ThreadPoolTaskExecutor` cung cấp cấu hình tương ứng: `setPrestartAllCoreThreads(true)`.

Kỹ thuật này chủ yếu thay đổi **thời điểm tạo thread**: đưa một phần chi phí khởi tạo từ lần submit công việc đầu tiên sang giai đoạn chuẩn bị pool. Nó không tăng `corePoolSize`, không tự chạy nghiệp vụ, không đảm bảo task không phải đợi queue và không làm hệ thống có nhiều tài nguyên CPU hơn.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

- Giải thích khác biệt giữa `corePoolSize`, `maximumPoolSize`, số worker hiện có và số worker đang thực thi task.
- Mô tả `prestartAllCoreThreads()` làm gì, trả về gì và khi nào nên gọi.
- Phân biệt `prestartCoreThread()` (một worker) với `prestartAllCoreThreads()` (các core worker còn thiếu).
- Dùng API Java 17+ qua `ThreadPoolExecutor` và cấu hình đúng `ThreadPoolTaskExecutor` trong Spring.
- Phân tích tác động của `queueCapacity`, `allowCoreThreadTimeOut`, `ThreadFactory` và vòng đời ứng dụng.
- Đo lường chi phí khởi động và thời gian xử lý lượt task đầu tiên, nhận biết các trường hợp prestart không đem lại lợi ích.

## 2. Core thread là gì?

`ThreadPoolExecutor` quản lý một nhóm **worker thread** để thực thi `Runnable` hoặc `Callable`. Hai cấu hình quan trọng:

- `corePoolSize`: số worker cốt lõi mà pool hướng tới duy trì, trừ khi cho phép core timeout hoặc có thay đổi cấu hình/trạng thái.
- `maximumPoolSize`: trần worker mà pool có thể dùng khi lượng công việc tăng và chiến lược queue cho phép mở rộng.

Ngoài hai thông số cấu hình, trạng thái chạy thực tế còn có:

| Thuật ngữ / API | Ý nghĩa |
| --- | --- |
| `getCorePoolSize()` | Mức core được cấu hình; **không** phải số thread đã được tạo |
| `getMaximumPoolSize()` | Trần worker được cấu hình; không phải mục tiêu bắt buộc phải tạo ngay |
| `getPoolSize()` | Số worker hiện thuộc pool; có thể ít hơn core nếu chưa khởi động hoặc đã timeout |
| `getActiveCount()` | Ước lượng số worker đang thực thi task; thread đang chờ queue không được coi là active |
| `getLargestPoolSize()` | Số worker lớn nhất đã từng cùng tồn tại trong pool |
| `getQueue().size()` | Số task đang chờ trong queue ở thời điểm quan sát; đây là một giá trị có thể thay đổi ngay |

Ví dụ một pool có `corePoolSize=3` và `maximumPoolSize=8` có thể vừa mới khởi tạo với `getPoolSize()==0`. Điều đó bình thường: pool sẽ tạo worker khi task tới. Sau khi prestart, trong điều kiện khởi tạo thành công, ba core worker tồn tại và chờ công việc dù `getActiveCount()==0`.

**Worker đang tồn tại** khác với **worker đang chạy task**. Việc tạo sẵn ba worker không đồng nghĩa có ba task đã bắt đầu.

## 3. Vòng đời mặc định của một ThreadPoolExecutor

Với một pool thông thường có queue:

1. Khi tạo `ThreadPoolExecutor`, constructor thiết lập cấu hình nhưng không mặc định tạo toàn bộ core thread.
2. Khi gửi task và tổng worker chưa đạt `corePoolSize`, pool có thể tạo worker mới kèm task.
3. Khi đã có đủ core worker, pool ưu tiên đưa task tiếp theo vào queue.
4. Nếu queue không nhận thêm và còn khả năng tăng worker dưới `maximumPoolSize`, pool có thể tăng số worker.
5. Nếu vẫn không có cách nhận task, `RejectedExecutionHandler` xử lý trường hợp từ chối.
6. Worker lấy công việc từ queue, thực thi rồi tiếp tục chờ việc mới hoặc kết thúc theo chính sách vòng đời.

Đây là **thứ tự quyết định nhận task**, không phải đảm bảo cứng về thứ tự task bắt đầu. Những worker đã tồn tại có thể lấy task ra khỏi queue ngay khi được đưa vào; scheduler và thời điểm giải phóng worker vẫn ảnh hưởng thời gian hoàn thành.

Ví dụ với `corePoolSize=3`, `maximumPoolSize=8`, `queueCapacity=100`: dù bạn bật prestart, pool cũng chỉ tạo trước **3 core worker**. Nếu queue còn rộng, tải tăng thường đi vào queue trước khi dùng khả năng mở rộng vượt core. Vì vậy prestart **không thay thế** việc chọn kích thước pool và queue phù hợp.

## 4. Chính xác prestartAllCoreThreads() làm gì?

`ThreadPoolExecutor.prestartAllCoreThreads()` có chữ ký:

~~~java
public int prestartAllCoreThreads()
~~~

Phương thức cố gắng khởi động tất cả **core worker còn thiếu**, để chúng chờ công việc trong queue. Giá trị trả về là **số worker mới thực sự được bắt đầu trong lần gọi**. Đó không phải số task đã chạy, tổng số thread sau cùng hay `maximumPoolSize`.

Giả sử pool mới có core là 4, chưa có worker và ThreadFactory hoạt động bình thường:

~~~text
Trước lời gọi: poolSize = 0
prestartAllCoreThreads() -> 4
Sau lời gọi:   poolSize = 4
Gọi lại:       prestartAllCoreThreads() -> 0
~~~

Nếu đã có hai core worker đang tồn tại, lời gọi có thể tạo thêm hai để đạt mức 4. Nếu pool đã đủ core, kết quả thường bằng 0. Nếu `corePoolSize=0`, không có core worker nào cần khởi động và kết quả là 0. Số thực sự tạo được còn phụ thuộc trạng thái pool, ThreadFactory và cạnh tranh đồng thời với thay đổi cấu hình hoặc vòng đời.

### Khác với prestartCoreThread()

`prestartCoreThread()` trả về `boolean` và cố gắng bắt đầu **một** core worker còn thiếu. Nếu đã đủ số core worker, nó trả `false`.

| Phương thức | Mục đích | Kiểu trả về |
| --- | --- | --- |
| `prestartCoreThread()` | Cố gắng khởi động thêm một core worker | `boolean`: có tạo được worker hay không |
| `prestartAllCoreThreads()` | Cố gắng khởi động tất cả core worker còn thiếu | `int`: số worker khởi động trong lần gọi |

Cả hai phương thức đều **không nhận `Runnable` làm đối số**, không gửi một task giả vào queue, không đợi một tác vụ nghiệp vụ và không tự động chạy initialization logic của ứng dụng. Worker được tạo ra chủ yếu để chờ nhận việc.

Nếu muốn tải cache, mở kết nối hoặc biên dịch JIT cho một đường code cụ thể, cần một quy trình warm-up riêng; prestart không thực hiện các việc đó.

## 5. Ví dụ Java 17+ chạy độc lập

Ví dụ dưới đây tạo một pool với `corePoolSize=3`, `maximumPoolSize=5`, queue chứa tối đa 8 task. Nó kiểm tra số worker trước và sau prestart, gọi prestart lần nữa và giao ba task nhỏ. `CountDownLatch` đảm bảo chỉ in số task đã xong khi cả ba hoàn tất.

Tệp **PrestartDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public final class PrestartDemo {
    public static void main(String[] args) throws InterruptedException {
        ThreadPoolExecutor executor = new ThreadPoolExecutor(
                3,
                5,
                30,
                TimeUnit.SECONDS,
                new ArrayBlockingQueue<>(8));

        CountDownLatch finished = new CountDownLatch(3);

        try {
            System.out.println("before=" + executor.getPoolSize());

            int started = executor.prestartAllCoreThreads();
            System.out.println("started=" + started);
            System.out.println("poolSize=" + executor.getPoolSize());

            int startedAgain = executor.prestartAllCoreThreads();
            System.out.println("startedAgain=" + startedAgain);

            for (int i = 0; i < 3; i++) {
                executor.execute(finished::countDown);
            }

            if (!finished.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Tasks did not finish");
            }

            System.out.println("completed=" + (3 - finished.getCount()));
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac PrestartDemo.java
java PrestartDemo
~~~

Kết quả của lần chạy thành công với `ThreadFactory` mặc định, không có tác vụ khác:

~~~text
before=0
started=3
poolSize=3
startedAgain=0
completed=3
~~~

Giải thích từng dòng:

- `before=0`: pool vừa được tạo, chưa nhận task và chưa có worker.
- `started=3`: lần prestart đầu đã tạo ba core worker, không tạo đủ năm worker theo `maximumPoolSize`.
- `poolSize=3`: có ba worker trong pool; các thread có thể đang chờ công việc, không có nghĩa là đang bận.
- `startedAgain=0`: đã có đủ core worker nên không tạo thêm.
- `completed=3`: chính **ba lần `execute` và chốt `CountDownLatch`** chứng minh ba task đã hoàn thành. `prestartAllCoreThreads` không tự làm tăng biến đếm tác vụ.

Code dùng hai ngưỡng timeout để tránh treo vô hạn nếu môi trường chạy gặp lỗi; việc kiểm tra trạng thái không phụ thuộc `Thread.sleep()` hoặc thời điểm scheduler đánh thức từng thread.

### Ví dụ gọi một thread trước rồi gọi tất cả

Đây là **đoạn minh họa**, đặt trong method có `ThreadPoolExecutor pool` đã được tạo với `corePoolSize=4`, chưa có worker, chưa có task và không bật core timeout:

~~~java
boolean first = pool.prestartCoreThread();  // true
int remaining = pool.prestartAllCoreThreads(); // 3
int repeat = pool.prestartAllCoreThreads();    // 0
~~~

Trong kịch bản nêu trên, ba biến lần lượt mang giá trị `true`, `3`, `0`. Nếu pool đã xử lý task từ trước hoặc được thay đổi cấu hình cùng lúc, số worker bổ sung sẽ khác. Tránh dùng `remaining == corePoolSize` như điều kiện thành công cứng trong môi trường có nhiều tác nhân thay đổi pool.

## 6. Tích hợp trong Spring ThreadPoolTaskExecutor

`org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor` là adapter Spring phổ biến trên nền `ThreadPoolExecutor`. Từ Spring Framework 5.3.14, nó hỗ trợ:

~~~java
public void setPrestartAllCoreThreads(boolean prestartAllCoreThreads)
~~~

Đây là **setter cấu hình**, không phải cùng phương thức JDK:

- `ThreadPoolExecutor.prestartAllCoreThreads()`: hành động ngay trên pool đã có, trả về `int`.
- `ThreadPoolTaskExecutor.setPrestartAllCoreThreads(true)`: yêu cầu Spring khởi động các core worker trong quá trình **initialize executor**; trả về `void`.
- Giá trị mặc định của setter Spring là `false`, tức tạo thread theo nhu cầu.

Với bean do Spring quản lý, container sẽ gọi các bước khởi tạo cần thiết trong lifecycle của bean. Nên thiết lập thuộc tính này **trước khi bean hoàn tất khởi tạo**.

### Cấu hình @Bean

Tệp **WorkerExecutorConfig.java** trong ứng dụng Spring có dependency `spring-context`:

~~~java
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class WorkerExecutorConfig {

    @Bean(name = "workerExecutor")
    public ThreadPoolTaskExecutor workerExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(3);
        executor.setMaxPoolSize(6);
        executor.setQueueCapacity(50);
        executor.setKeepAliveSeconds(60);
        executor.setThreadNamePrefix("worker-");

        executor.setPrestartAllCoreThreads(true);
        executor.setAllowCoreThreadTimeOut(false);
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());

        return executor;
    }
}
~~~

Đây là **lớp cấu hình Spring**, không có `main` riêng và không dùng `javac` độc lập nếu thiếu thư viện Spring. Container khởi tạo bean; trong điều kiện bình thường ba core worker được tạo từ giai đoạn khởi tạo pool. Nếu để `setPrestartAllCoreThreads(false)` (mặc định), số worker sẽ tăng theo công việc thực tế.

`setAllowCoreThreadTimeOut(false)` giữ nguyên hành vi cốt lõi: các core thread không bị loại bỏ chỉ vì idle. Điều này phù hợp khi muốn chúng tiếp tục sẵn sàng chờ task, nhưng phải tính chi phí tài nguyên của ba thread đó.

**`@Bean` không yêu cầu `@EnableAsync` chỉ để tạo pool.** `@EnableAsync` chỉ cần khi muốn kích hoạt hạ tầng `@Async` theo cách cấu hình tương ứng. Nếu dùng `@Async("workerExecutor")`, cần chỉ định đúng bean tên `workerExecutor` và gọi method qua proxy của Spring; lời gọi nội bộ trong cùng bean ở proxy mode mặc định không được intercept.

### Dùng TaskExecutor tại một service

Tệp **JobDispatcher.java** (mã tích hợp với Spring):

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.TaskExecutor;
import org.springframework.stereotype.Service;

@Service
public class JobDispatcher {
    private final TaskExecutor executor;

    public JobDispatcher(@Qualifier("workerExecutor") TaskExecutor executor) {
        this.executor = executor;
    }

    public void dispatch(String jobId) {
        executor.execute(() -> process(jobId));
    }

    private void process(String jobId) {
        System.out.println("Processing " + jobId);
    }
}
~~~

Mẫu minh họa cách submit task, **không hứa rằng công việc đã hoàn thành khi `dispatch()` trả về**. Đoạn `process` chỉ in ra log để học về luồng thực thi. Trong ứng dụng thật, cần xử lý exception, trạng thái job, idempotency, shutdown và bảo đảm bền vững nếu yêu cầu nghiệp vụ cần.

### Trường hợp tự tạo executor ngoài Spring

Nếu dùng `new ThreadPoolTaskExecutor()` bên ngoài container, bạn phải quản lý initialize và shutdown:

~~~java
ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
executor.setCorePoolSize(2);
executor.setMaxPoolSize(4);
executor.setQueueCapacity(10);
executor.setPrestartAllCoreThreads(true);

executor.initialize();
try {
    // executor đã được khởi tạo, có thể submit công việc.
} finally {
    executor.shutdown();
}
~~~

Đây là **mẫu lifecycle rút gọn** dùng trong method/test có thư viện Spring, không phải một chương trình độc lập. Không gọi `initialize()` lặp lại trên một bean đã được Spring quản lý chỉ vì muốn warm-up lần nữa.

## 7. Nếu pool đã khởi tạo rồi thì sao?

Với Spring, nên bật setter trước khi khởi tạo. Nếu cần chủ động prestart **sau** khi `ThreadPoolTaskExecutor` đã khởi tạo, có thể truy cập JDK executor nền:

~~~java
ThreadPoolExecutor nativePool = springExecutor.getThreadPoolExecutor();
int newlyStarted = nativePool.prestartAllCoreThreads();
~~~

Đây là **đoạn minh họa** trong method có biến `springExecutor` kiểu `ThreadPoolTaskExecutor` đã được initialize. Nếu chưa khởi tạo, `getThreadPoolExecutor()` không trả về pool đã sẵn sàng để gọi. Không nên bật setter sau khi khởi tạo rồi mặc nhiên kỳ vọng các thread mới xuất hiện ngay; setter chủ yếu điều khiển hành vi tại thời điểm khởi tạo. Gọi trực tiếp API JDK khi thật sự cần thực hiện ngay trên pool hiện tại.

Nếu muốn tăng `corePoolSize` ở runtime rồi tạo sẵn phần core mới, cần xác định bạn sở hữu cấu hình pool đó, đảm bảo lifecycle còn hợp lệ, và đo tác động lên bộ nhớ/số thread. Tùy trạng thái queue, một thay đổi `corePoolSize` có thể tự khiến pool tạo worker để xử lý việc chờ; không nên giả định chỉ có lời gọi prestart mới làm số thread tăng.

Việc trực tiếp lấy native pool khiến code gắn chặt hơn với `ThreadPoolTaskExecutor`, vì không phải mọi `TaskExecutor` đều dựa trên `ThreadPoolExecutor`. Ưu tiên cấu hình Spring khi yêu cầu chỉ là “core worker sẵn sàng từ startup”.

## 8. Tương tác với queueCapacity, maxPoolSize và core timeout

### queueCapacity quyết định hành vi mở rộng

Spring `ThreadPoolTaskExecutor` dùng queue có sức chứa khi `queueCapacity > 0` và dùng `SynchronousQueue` khi `queueCapacity <= 0`. Với queue dương, pool thường cho task vào queue sau khi đã đạt core; chỉ khi queue đầy mới xem xét tăng worker tới `maxPoolSize`.

Vì vậy:

- `core=3, max=6, queue=50, prestart=true`: lúc startup tạo khoảng ba core worker. Với tải đến dần và queue vẫn nhận được, có thể chưa bao giờ dùng tới sáu worker.
- `core=3, max=6, queue=0, prestart=true`: không có vùng buffer thông thường; khi các core worker đã bận và không thể giao trực tiếp việc mới, pool có thể tăng tới sáu worker rồi từ chối nếu hết chỗ.
- `core=0, max=6, queue=50, prestart=true`: không có core worker nào để prestart. Cấu hình này cần được hiểu rõ nếu muốn worker sẵn sàng trước.

Prestart không tự làm thay đổi queue hoặc `maximumPoolSize`. Nó chỉ dời thời điểm tạo **các core worker**.

### allowCoreThreadTimeOut(true) có thể làm core worker biến mất

Theo mặc định, core worker không tự chết chỉ do idle. Nếu bật `allowCoreThreadTimeOut(true)` và `keepAliveTime > 0`, core worker cũng có thể kết thúc sau một khoảng chờ không có việc. Kết quả:

1. Startup gọi prestart tạo worker.
2. Ứng dụng yên lặng đủ lâu, core worker có thể timeout và rời pool.
3. Đợt task tiếp theo lại cần tạo worker mới.

Đây không phải lỗi của prestart. Hai cấu hình phục vụ mục tiêu khác nhau: prestart muốn giảm chi phí ở đợt đầu; core timeout muốn giảm tài nguyên khi nhàn rỗi. Có thể kết hợp, nhưng lợi ích giảm latency cho những đợt về sau sẽ không ổn định nếu các worker đã bị thu hồi.

### Số thread thật phụ thuộc ThreadFactory và môi trường

`ThreadPoolExecutor` lấy worker từ `ThreadFactory`. ThreadFactory có thể đặt tên, mức ưu tiên, uncaught exception handler hoặc tạo các loại thread phù hợp; nếu không thể cấp thread, số tạo được có thể không đạt kỳ vọng. Cạn tài nguyên native thread/memory hoặc shutdown cũng ảnh hưởng việc khởi động. `prestartAllCoreThreads()` chỉ trả về số đã tạo trong lần gọi, không cam kết mọi lần đều bằng `corePoolSize`.

Việc chờ worker chuyển sang trạng thái thực sự sẵn sàng nhận task vẫn phụ thuộc scheduling. Không dùng `getPoolSize() == corePoolSize` như một hàng rào đồng bộ để xác nhận mọi dependency bên trong tác vụ đã sẵn sàng.

## 9. Prestart mang lại lợi ích gì và phải trả giá gì?

### Lợi ích có thể có

- Giảm một phần độ trễ submit/task đầu tiên do **tạo Thread object và native thread** khi đợt việc đến.
- Làm chi phí tạo core worker xuất hiện sớm và dễ quan sát hơn trong giai đoạn khởi động.
- Hữu ích cho pool cố định, service có đợt tải đầu tiên nhạy với latency hoặc pipeline bắt đầu nhận một loạt job ngay khi ứng dụng được đánh dấu ready.

Lợi ích thực tế phụ thuộc từng ứng dụng và có thể rất nhỏ. Thread creation thường chỉ là một phần tổng thời gian xử lý, bên cạnh I/O, TLS, database, GC, lock và logic nghiệp vụ.

### Chi phí và rủi ro

- Tăng thời gian/chi phí startup do phải tạo đủ core worker trước khi có công việc thực.
- Giữ tài nguyên của thread đang idle (stack, native handle, metadata và những cấu trúc liên quan); đáng kể nếu nhiều bean/replica cùng có core lớn.
- Làm concurrency xuất hiện sớm ở quá trình khởi động, gây tương tác với ThreadFactory, monitoring hoặc cấu hình lifecycle.
- Không giải quyết queue đầy, rejection, starvation, deadlock, lỗi tác vụ hoặc yêu cầu xử lý xuyên nhiều replica.
- Nếu bean chỉ được dùng rất hiếm, prestart có thể tạo tài nguyên mà ứng dụng gần như không sử dụng.

**Không dùng prestart để “tăng throughput” nếu không có số liệu.** Khi pool đã được warm theo tải thực tế, số core/max worker và thời gian xử lý task quyết định năng lực song song nhiều hơn việc worker được tạo sớm một vài mili giây.

## 10. Prestart không phải application warm-up

Có bốn thao tác thường bị nhầm:

| Thao tác | Tạo sẵn worker? | Chạy code nghiệp vụ? | Bảo đảm |
| --- | --- | --- | --- |
| `prestartAllCoreThreads()` | Có, với core worker còn thiếu | Không | Khởi động worker để chờ việc, trả số worker tạo mới |
| Gửi task warm-up qua `execute` | Có thể, theo nhu cầu pool | Có, chạy task đã gửi | Phụ thuộc completion, lỗi và cách chờ kết quả |
| Warm-up JIT/cache/connection pool | Phụ thuộc cách implement | Có thể | Chỉ những thành phần được warm thực tế |
| Tăng `corePoolSize` hoặc `maxPoolSize` | Có thể tạo thêm worker theo trạng thái | Không tự chạy task nghiệp vụ | Tăng mức cấu hình năng lực; không tự cải thiện latency |

Ví dụ, nếu task đầu phải kết nối tới database và tải một mô hình lớn, prestart chỉ loại bỏ chi phí tạo worker; việc kết nối database và tải dữ liệu vẫn diễn ra khi task chạy, trừ khi bạn chủ động warm-up chúng qua cơ chế khác.

Tương tự, `ThreadPoolTaskExecutor` mặc định dùng **platform thread** kiểu pool truyền thống. Virtual thread theo mô hình thread-per-task trong Java 21+ có cơ chế khác; không áp máy móc phương thức này lên một `TaskExecutor` không có core pool.

## 11. Phối hợp với vòng đời Spring và readiness

### Khởi tạo bean

Khi Spring khởi tạo bean `ThreadPoolTaskExecutor`, nó sử dụng cấu hình đã đặt và tiến hành khởi tạo executor. Bật `setPrestartAllCoreThreads(true)` thường khiến thread được tạo trong bước này. Nếu có nhiều bean pool khác nhau, mỗi pool có core riêng và tạo worker riêng; cần tính tổng số thread trước khi bật hàng loạt.

Trong ứng dụng có readiness probe, **bean được initialize không có nghĩa mọi dependency bên ngoài đã sẵn sàng**, và prestart cũng không chứng minh toàn bộ ứng dụng đã phục vụ được request. Phân biệt rõ:

- Executor được khởi tạo.
- Core worker tồn tại.
- Task đầu có thể được submit.
- Dependency, dữ liệu và hệ thống đã sẵn sàng cho thao tác nghiệp vụ.

Nếu ứng dụng cần bảo đảm dependency được kiểm tra trước khi ready, dùng health/readiness contract tương ứng. Không coi `getPoolSize() > 0` là health check duy nhất.

### Shutdown

Prestart không thay đổi hợp đồng shutdown: pool đã chuyển sang ngừng nhận việc không trở thành active trở lại chỉ bằng một lời gọi prestart. Khi đóng ApplicationContext, Spring quản lý vòng đời bean và cách xử lý task chờ/đang chạy theo cấu hình. Việc prestart các thread idle có thể khiến lúc shutdown cần dọn thêm worker, nhưng không phải lý do bỏ qua shutdown đúng cách.

Chỉ gọi `shutdown()`/`shutdownNow()` trên executor tự quản lý hoặc theo lifecycle được thiết kế. Không chủ động shutdown một bean được nhiều component chia sẻ ngay khi một request đã xong.

## 12. Cách quan sát và kiểm thử

### Theo dõi trạng thái

Sau khi Spring đã khởi tạo một `ThreadPoolTaskExecutor executor`, có thể đọc:

~~~java
int configuredCore = executor.getCorePoolSize();
int currentPool = executor.getPoolSize();
int activeTasks = executor.getActiveCount();
int queuedTasks = executor.getQueueSize();
~~~

Đây là **đoạn minh họa**, không phải source độc lập. Với một pool mới cấu hình `core=3`, prestart bật và chưa có task, trạng thái quan sát thường là `configuredCore=3`, `currentPool=3`, `activeTasks=0`, `queuedTasks=0`. Các giá trị runtime có thể đổi ngay khi có submit đồng thời; không dùng chúng để tự tạo một giao thức quyết định nghiệp vụ nhạy race.

Nếu cần metrics trong Spring Boot, có thể dùng Micrometer/Actuator tùy cấu hình thực tế. Theo dõi pool size, active count, queue size, số rejection và phân phối latency, nhưng tránh kết luận “warm-up tốt” chỉ từ một snapshot số worker.

### Kiểm tra tác động latency

Một thí nghiệm công bằng nên:

1. Tạo hai pool tương đương về core, max, queue, ThreadFactory và loại công việc; chỉ khác prestart.
2. Đo **startup time**, thời gian từ submit tới lúc task đầu bắt đầu, rồi đo cả thời gian hoàn tất.
3. Thử cả đợt đầu sau startup và đợt sau khi pool đã xử lý công việc.
4. Lặp nhiều lần, kiểm soát JIT/GC/hệ điều hành, đo p50/p95/p99, và so sánh chi phí bộ nhớ/số thread.
5. Lặp dưới tải thực tế với queue và tác vụ có độ dài tương tự sản xuất.

Không dùng `Thread.sleep(...)` để chứng minh thread đã sẵn sàng. Nếu cần phối hợp task và đo thời điểm, sử dụng `CountDownLatch`, `Phaser` hoặc các primitive đồng bộ phù hợp. Đo đạc không cần tự dàn dựng race bằng cách chờ một số mili giây tùy ý.

### Kiểm tra cơ chế trong unit test

Với `ThreadPoolExecutor` cấu hình core là 2, không submit task nào:

~~~java
ThreadPoolExecutor pool = new ThreadPoolExecutor(
        2, 4, 30, TimeUnit.SECONDS,
        new ArrayBlockingQueue<>(4));
try {
    if (pool.getPoolSize() != 0) {
        throw new AssertionError("Expected a fresh pool");
    }
    int newlyStarted = pool.prestartAllCoreThreads();
    if (newlyStarted != 2 || pool.getPoolSize() != 2) {
        throw new AssertionError("Core threads were not prestarted");
    }
} finally {
    pool.shutdownNow();
}
~~~

Đây là **mã minh họa đặt trong method**, cần import `java.util.concurrent.*`. Với factory mặc định và không có tác nhân đồng thời, assert này có thể xác định được. Test nên đóng executor trong `finally` để tránh giữ non-daemon worker thread làm quy trình test treo.

Với Spring bean, có thể inject đúng `ThreadPoolTaskExecutor`, kiểm tra cấu hình và pool size sau initialization. Không gọi `initialize()` lần nữa trên bean đang chạy chỉ để test số worker. Nếu muốn kiểm thử đường `@Async`, kiểm tra cả việc lời gọi đi qua proxy và cách task hoàn tất bằng `Future`/`CompletableFuture` hoặc latch.

## 13. Những nhầm lẫn và lỗi thường gặp

1. **Nhầm `corePoolSize=5` với “ngay lập tức có 5 thread”.** Mặc định worker khởi tạo theo nhu cầu; prestart mới yêu cầu tạo trước.
2. **Nhầm prestart với submit năm task.** Prestart chỉ làm worker chờ, không chạy `Runnable` do người dùng cung cấp.
3. **Dùng `maximumPoolSize` để suy ra số prestart.** Chỉ core worker còn thiếu được tạo trước; max không phải số cần tạo.
4. **Gọi prestart nhiều lần và nghĩ mỗi lần tạo thêm core mới.** Khi đã đủ core, lần gọi tiếp trả 0.
5. **Bật `setPrestartAllCoreThreads(true)` sau initialize rồi mặc định nghĩ có hiệu lực ngay.** Với pool đã hoạt động, dùng JDK method trên native pool nếu thực sự cần thực thi tức thì.
6. **Không gọi `initialize()` trên `ThreadPoolTaskExecutor` tự tạo ngoài container.** Setter chỉ cấu hình; chưa khởi tạo thì chưa có native executor để dùng.
7. **Tưởng bật prestart khiến max pool được dùng sớm hơn.** Queue vẫn quyết định đường mở rộng sau core.
8. **Dùng queue gần như vô hạn, max rất lớn rồi mong prestart giải quyết backlog.** Prestart không giải quyết tăng trưởng hàng đợi hoặc thiếu backpressure.
9. **Bật core timeout rồi kỳ vọng core worker luôn tồn tại.** Các worker có thể kết thúc sau thời gian idle.
10. **Tạo quá nhiều core worker trên mỗi replica.** Tài nguyên CPU, bộ nhớ và native thread đều bị chia sẻ; nhân số lượng pool với số lượng replica.
11. **Xem `getPoolSize()` như số thread active.** Chỉ số hoạt động có API riêng và đều có tính snapshot/ước lượng.
12. **Dùng thời gian lần chạy đầu làm bằng chứng tuyệt đối.** JIT, cache, disk, mạng, hệ điều hành và thread startup cùng ảnh hưởng latency.
13. **Cố dùng phương thức JDK trên mọi `TaskExecutor`.** Không phải mọi executor Spring đều chứa `ThreadPoolExecutor`; ví dụ executor dựa trên virtual thread có cơ chế khác.
14. **Bỏ quên cleanup trong demo hoặc test.** Core worker có thể tiếp tục sống và giữ JVM nếu không shutdown.
15. **Xem prestart là readiness của toàn hệ thống.** Worker sẵn sàng nhận task không chứng minh database hoặc service bên ngoài đã healthy.

## 14. Hướng dẫn ra quyết định

Chỉ bật prestart khi có nhu cầu rõ ràng. Một cách phân tích thực tế:

| Bối cảnh | Đề xuất | Lý do |
| --- | --- | --- |
| Dịch vụ nhận đợt tải quan trọng ngay sau startup, core nhỏ và cố định | Thử `prestartAllCoreThreads`, đo latency trước/sau | Có thể loại bớt chi phí tạo thread của đợt đầu |
| Batch worker dài hạn, luôn có task | Có thể không cần | Sau vài task, core worker thường đã được tạo |
| Dịch vụ hiếm khi chạy tác vụ, nhiều replica | Cân nhắc giữ lazy | Tránh tạo nhiều thread idle |
| Task đầu chậm vì kết nối DB/JIT/cache | Prestart đơn lẻ không giải quyết | Cần warm-up đúng dependency và work path |
| Queue đầy / từ chối do quá tải | Ưu tiên capacity planning và backpressure | Prestart không tăng giới hạn nhận việc |
| Muốn giảm tài nguyên khi idle và dùng `allowCoreThreadTimeOut(true)` | Đánh giá lại mục tiêu warm | Core worker tạo sớm có thể mất đi sau khi idle |
| Executor chạy theo kiểu virtual-thread-per-task | Không dùng trực tiếp công thức core pool | Cơ chế tạo thread khác với ThreadPoolExecutor |

Trong ứng dụng Spring, cấu hình ban đầu nên ngắn gọn và có chủ đích: định rõ core/max, queue hữu hạn khi phù hợp, thread name, chính sách rejection, vòng đời và monitoring. Sau đó thử prestart riêng biệt, đo độ trễ thật trước khi quyết định giữ.

## 15. Câu hỏi tự kiểm tra

1. Một `ThreadPoolExecutor(core=4,max=10)` vừa được tạo và chưa submit task. `getCorePoolSize()` và `getPoolSize()` có nhất thiết cùng bằng 4 không?
2. Vì sao `prestartAllCoreThreads()` trả về 0 ở lần thứ hai vẫn có thể là kết quả hoàn toàn đúng?
3. Một pool đã có hai worker, `corePoolSize=5`. Trong điều kiện bình thường, `prestartAllCoreThreads()` có thể trả về bao nhiêu?
4. `setPrestartAllCoreThreads(true)` của Spring khác gì `prestartAllCoreThreads()` của JDK về thời điểm áp dụng và giá trị trả về?
5. Vì sao prestart ba worker không khiến `maximumPoolSize=20` lập tức tạo 20 thread?
6. Nếu bật `allowCoreThreadTimeOut(true)` và service nhàn rỗi trong thời gian dài, lợi ích prestart có thể thay đổi thế nào?
7. Làm thế nào để kiểm tra prestart có thực sự giúp p99 của lượt request đầu tiên mà không nhầm với thời gian kết nối database?
8. Tại sao một pool có ba idle worker không chứng minh ứng dụng đã sẵn sàng phục vụ toàn bộ chức năng nghiệp vụ?

## 16. Tài liệu tham khảo chính thức

- [Java SE 17 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [Java SE 17 — ThreadFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadFactory.html)
- [Spring Framework 6.1 — ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/6.1.1/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)

**Ghi nhớ:** `prestartAllCoreThreads()` là công cụ **khởi tạo sẵn core worker**. Nó có thể đổi thời gian tạo thread để tối ưu độ trễ đợt đầu, nhưng không thay đổi cấu hình sức chứa, không thực thi warm-up nghiệp vụ và không thay thế thiết kế pool/queue/rejection/shutdown đúng đắn.