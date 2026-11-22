# Kiểm soát executor và tác vụ nền trong kiểm thử

Khi ứng dụng Spring chuyển công việc sang executor hoặc thread pool, lời gọi khởi chạy tác vụ và thời điểm tác vụ hoàn tất là hai thời điểm khác nhau. Test chỉ gọi phương thức rồi kiểm tra ngay kết quả thường tạo ra lỗi chập chờn: có lần tác vụ đã chạy xong, có lần nó vẫn đang chờ trong queue hoặc đang thực thi trên thread khác.

Kiểm thử bất đồng bộ cần một cơ chế đồng bộ rõ ràng. Hãy chờ tín hiệu hoàn tất bằng Future, CompletableFuture, CountDownLatch hoặc công cụ như Awaitility; đặt giới hạn thời gian hữu hạn; và kiểm tra lỗi cũng như kết quả của tác vụ. Khi cần kiểm thử logic độc lập với concurrency, có thể thay executor bằng executor chạy đồng bộ. Khi cần xác nhận tính song song thật sự, dùng thread pool có giới hạn và đồng bộ các tác vụ bằng latch hoặc barrier.

## 1. Phân biệt executor, thread pool và tác vụ nền

Spring cung cấp abstraction TaskExecutor để ứng dụng giao một Runnable cho cơ chế thực thi. Một số interface và implementation thường gặp:

| Thành phần | Vai trò |
|---|---|
| Executor | Abstraction chuẩn Java với phương thức execute(Runnable) |
| TaskExecutor | Abstraction executor của Spring, mở rộng cách giao tác vụ của Java |
| AsyncTaskExecutor | Hỗ trợ gửi tác vụ và nhận Future để theo dõi kết quả |
| ThreadPoolTaskExecutor | Executor Spring dựa trên thread pool, có cấu hình số thread, queue và chính sách từ chối |
| SyncTaskExecutor | Chạy tác vụ ngay trên thread gọi; hữu ích khi muốn kiểm thử luồng xử lý một cách xác định |
| SimpleAsyncTaskExecutor | Tạo thread cho tác vụ theo cấu hình; không phải thread pool tái sử dụng thread theo cùng cách ThreadPoolTaskExecutor |

Một thread pool thường có ba thành phần cần quan tâm:

- **Worker threads:** số tác vụ có thể chạy đồng thời.
- **Queue:** tác vụ chờ khi các worker đang bận.
- **Rejection policy:** hành vi khi không còn thread/slot queue để nhận tác vụ.

Luồng cơ bản:

~~~text
Thread gọi service
       |
       | submit / execute
       v
Executor
       |
       +---- worker rảnh? ---- Có ----> chạy tác vụ
       |                         |
       |                         +----> hoàn tất / phát tín hiệu
       |
       +---- Không ----> đưa vào queue
                            |
                            v
                       worker lấy tác vụ
                            |
                            v
                       chạy và hoàn tất
~~~

Test cần xác định mình đang kiểm tra điều gì: tác vụ có được gửi đi hay không, nó có chạy trên thread khác hay không, nhiều tác vụ có thể chạy đồng thời hay không, kết quả cuối cùng là gì, hoặc executor xử lý queue đầy ra sao. Một assertion duy nhất sau lời gọi thường không đủ để chứng minh các hành vi này.

## 2. Cấu hình executor cho @Async

@Async yêu cầu Spring bật async method execution bằng @EnableAsync. Lời gọi cần đi qua Spring proxy để interceptor chuyển phần thân phương thức sang executor.

Ví dụ cấu hình:

~~~java
@Configuration
@EnableAsync
public class AsyncConfiguration {

    @Bean("applicationTaskExecutor")
    public ThreadPoolTaskExecutor applicationTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("background-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(10);
        return executor;
    }
}
~~~

Service:

~~~java
@Service
public class ReportService {

    @Async("applicationTaskExecutor")
    public CompletableFuture<String> generate(String reportId) {
        String result = doGenerate(reportId);
        return CompletableFuture.completedFuture(result);
    }

    private String doGenerate(String reportId) {
        return "report-" + reportId + "-ready";
    }
}
~~~

Khi gọi generate(...) qua bean Spring được inject, caller nhận một CompletableFuture. Phần thân phương thức được chạy bởi executor có qualifier applicationTaskExecutor. Tên executor trong @Async("...") giúp chọn rõ pool cần sử dụng khi ứng dụng có nhiều executor.

### 2.1. Vì sao self-invocation làm test async sai?

Trong chế độ proxy mặc định, gọi một phương thức @Async từ phương thức khác trong cùng object không đi qua proxy:

~~~java
public void start() {
    generate("monthly"); // lời gọi nội bộ, không qua async proxy
}
~~~

Đây là lời gọi trực tiếp trên this, nên interceptor của @Async không được kích hoạt. Khi kiểm thử, hãy gọi phương thức async qua bean được Spring inject hoặc tách tác vụ sang bean riêng. Không tự tạo instance bằng new nếu mục tiêu là xác nhận proxy async của Spring hoạt động.

## 3. Kiểm tra tác vụ hoàn tất bằng CompletableFuture

Với tác vụ có kết quả, CompletableFuture là cách trực tiếp để đồng bộ test với kết quả thực thi:

~~~java
@SpringJUnitConfig({AsyncTestConfiguration.class, ReportService.class})
class ReportServiceTest {

    @Autowired
    ReportService reportService;

    @Test
    void completesReportOnBackgroundThread() throws Exception {
        CompletableFuture<String> future =
                reportService.generate("monthly");

        String result = future.get(2, TimeUnit.SECONDS);

        assertThat(result).isEqualTo("report-monthly-ready");
    }
}
~~~

get(timeout, unit) chờ hoàn tất tối đa một khoảng thời gian. Nếu tác vụ không hoàn tất, test thất bại bằng TimeoutException thay vì treo vô hạn. Nếu tác vụ hoàn tất lỗi, get(...) ném ExecutionException; có thể kiểm tra nguyên nhân gốc qua getCause().

Để kiểm tra thread thực thi, trả tên thread trong kết quả hoặc ghi lại bằng một probe an toàn cho thread:

~~~java
@Async("testExecutor")
public CompletableFuture<String> runAndReportThread() {
    return CompletableFuture.completedFuture(
            Thread.currentThread().getName());
}
~~~

Test:

~~~java
String callerThread = Thread.currentThread().getName();
String workerThread =
        worker.runAndReportThread().get(2, TimeUnit.SECONDS);

assertThat(workerThread).startsWith("test-async-");
assertThat(workerThread).isNotEqualTo(callerThread);
~~~

Tên thread prefix nên được cấu hình riêng cho executor test để assertion không phụ thuộc tên thread mặc định của JVM hoặc môi trường CI.

## 4. Kiểm tra tác vụ void bằng CountDownLatch

Phương thức @Async trả về void không có future để caller lấy kết quả. Test có thể dùng CountDownLatch để nhận tín hiệu tác vụ đã đi đến điểm cần xác minh:

~~~java
@Component
public class NotificationWorker {

    @Async("testExecutor")
    public void send(
            String recipient,
            CountDownLatch completed,
            AtomicReference<String> executedThread) {

        try {
            executedThread.set(Thread.currentThread().getName());
            // Thực hiện công việc gửi thông báo giả lập.
        }
        finally {
            completed.countDown();
        }
    }
}
~~~

Test:

~~~java
CountDownLatch completed = new CountDownLatch(1);
AtomicReference<String> executedThread = new AtomicReference<>();

notificationWorker.send("test@example.invalid",
        completed, executedThread);

assertThat(completed.await(2, TimeUnit.SECONDS)).isTrue();
assertThat(executedThread.get()).startsWith("test-async-");
~~~

await(...) vừa chờ tác vụ vừa có giới hạn thời gian. Dùng finally để giảm latch bảo đảm test không chờ vô hạn nếu phần thân tác vụ kết thúc sớm do exception. Trong test thực tế, nên truyền một collaborator giả hoặc ghi nhận trạng thái qua một probe thread-safe thay vì đưa quá nhiều đối tượng kiểm thử vào API nghiệp vụ.

Không nên dùng Thread.sleep(...) để đợi tác vụ. Sleep chỉ đoán rằng tác vụ đã có đủ thời gian chạy; nó không chứng minh tác vụ đã hoàn tất và có thể thất bại khi CI tải cao.

## 5. Cấu hình executor riêng cho test

Test nên kiểm soát số thread, queue và thread name để hành vi có thể lặp lại. Có thể cung cấp executor riêng trong test configuration:

~~~java
@TestConfiguration
@EnableAsync
public class AsyncTestConfiguration {

    @Bean("testExecutor")
    public ThreadPoolTaskExecutor testExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(10);
        executor.setThreadNamePrefix("test-async-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(5);
        return executor;
    }
}
~~~

Service test dùng qualifier:

~~~java
@Component
public class BackgroundWorker {

    @Async("testExecutor")
    public CompletableFuture<String> execute(String value) {
        return CompletableFuture.completedFuture(
                value + "@" + Thread.currentThread().getName());
    }
}
~~~

Test có thể dùng @SpringJUnitConfig hoặc @Import(AsyncTestConfiguration.class) trong test context để nạp cấu hình. Spring quản lý vòng đời bean executor và gọi lifecycle callback khi context khởi tạo/đóng.

Nếu dự án đã có executor production với cấu hình phức tạp, không nhất thiết phải dùng cấu hình production cho mọi test đơn vị. Executor test có thể nhỏ hơn, có queue hữu hạn và tên thread dễ nhận biết. Với test tích hợp cấu hình production, hãy nạp đúng bean production và kiểm tra các đặc tính cần xác nhận.

## 6. Dùng SyncTaskExecutor để kiểm thử logic không phụ thuộc concurrency

Không phải test nào gọi code có @Async cũng cần tạo thread thật. Khi muốn kiểm tra mapping, validation hoặc logic của phần thân tác vụ mà không quan tâm concurrency, có thể cung cấp executor chạy đồng bộ:

~~~java
@TestConfiguration
@EnableAsync
public class SynchronousAsyncTestConfiguration {

    @Bean("testExecutor")
    public TaskExecutor testExecutor() {
        return new SyncTaskExecutor();
    }
}
~~~

Khi đó proxy @Async vẫn được gọi, nhưng executor chạy Runnable ngay trên thread gọi. Test có thể quan sát kết quả ngay mà không cần chờ thread pool.

Cách này phù hợp cho test logic đơn giản và deterministic. Nó không chứng minh tác vụ chạy trên thread khác, không kiểm tra queue, rejection, race condition hoặc khả năng chạy song song. Giữ ít nhất một nhóm test riêng dùng executor thật cho các hành vi concurrency mà ứng dụng dựa vào.

Không thay executor production bằng SyncTaskExecutor trong mọi test nếu yêu cầu quan trọng của hệ thống là cô lập request khỏi công việc nền. Khi đó test sẽ bỏ qua chính hành vi bất đồng bộ cần bảo vệ.

## 7. Kiểm tra nhiều tác vụ thực sự chạy song song

Để xác nhận thread pool có thể chạy nhiều tác vụ đồng thời, dùng latch làm hàng rào đồng bộ. Mỗi tác vụ báo rằng nó đã bắt đầu, rồi chờ test cho phép tiếp tục:

~~~java
@Async("testExecutor")
public CompletableFuture<Void> waitAtBarrier(
        CountDownLatch started,
        CountDownLatch release) {

    started.countDown();
    try {
        if (!release.await(2, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Test did not release workers");
        }
        return CompletableFuture.completedFuture(null);
    }
    catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        throw new IllegalStateException("Worker interrupted", ex);
    }
}
~~~

Test với pool có hai worker:

~~~java
CountDownLatch started = new CountDownLatch(2);
CountDownLatch release = new CountDownLatch(1);

try {
    CompletableFuture<Void> first =
            worker.waitAtBarrier(started, release);
    CompletableFuture<Void> second =
            worker.waitAtBarrier(started, release);

    assertThat(started.await(2, TimeUnit.SECONDS)).isTrue();

    release.countDown();
    first.get(2, TimeUnit.SECONDS);
    second.get(2, TimeUnit.SECONDS);
}
finally {
    release.countDown();
}
~~~

Nếu pool chỉ có một worker và tác vụ đầu tiên đang chờ release, tác vụ thứ hai không thể báo đã bắt đầu trước khi test mở latch. Với pool hai worker, cả hai có thể tới barrier. finally luôn mở latch để tránh để lại thread test đang chờ nếu assertion thất bại.

Đừng kiểm tra song song bằng cách so sánh thứ tự log hoặc giả định task A luôn kết thúc trước task B. Scheduler có thể thay đổi thứ tự. Hãy kiểm tra thuộc tính cần thiết, chẳng hạn số tác vụ đã cùng bắt đầu, giới hạn số worker đang chạy hoặc kết quả cuối cùng của tất cả tác vụ.

## 8. Kiểm tra queue và tác vụ bị từ chối

Thread pool có queue hữu hạn cần một chính sách khi không thể nhận thêm công việc. Nếu queue và số worker đều đầy, executor có thể từ chối tác vụ. Test có thể tạo một pool nhỏ để kiểm tra hành vi này một cách có kiểm soát:

~~~java
ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
executor.setCorePoolSize(1);
executor.setMaxPoolSize(1);
executor.setQueueCapacity(0);
executor.setRejectedExecutionHandler(
        new ThreadPoolExecutor.AbortPolicy());
executor.initialize();

CountDownLatch started = new CountDownLatch(1);
CountDownLatch release = new CountDownLatch(1);

try {
    executor.execute(() -> {
        started.countDown();
        try {
            release.await();
        }
        catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
        }
    });

    assertThat(started.await(2, TimeUnit.SECONDS)).isTrue();

    assertThatThrownBy(() -> executor.execute(() -> {}))
            .isInstanceOf(TaskRejectedException.class);
}
finally {
    release.countDown();
    executor.shutdown();
}
~~~

Ở đây pool chỉ có một worker và queue không có chỗ chờ. Tác vụ đầu tiên giữ worker bận; tác vụ thứ hai bị từ chối. AbortPolicy ném lỗi khi không thể nhận tác vụ, còn Spring ThreadPoolTaskExecutor biểu diễn việc từ chối qua TaskRejectedException.

Chính sách khác có thể chạy tác vụ trên thread gọi hoặc loại bỏ tác vụ. Hãy kiểm tra đúng chính sách mà ứng dụng cấu hình. Đặc biệt, CallerRunsPolicy có thể khiến request thread phải chạy tác vụ nền khi pool quá tải; điều đó làm thay đổi độ trễ và có thể khiến hành vi trông như đồng bộ.

Test queue/rejection nên dùng pool nhỏ được tạo riêng trong test và luôn giải phóng latch, đóng executor trong finally. Không làm cạn pool dùng chung của application context để kiểm tra rejection vì có thể ảnh hưởng các test khác.

## 9. Kiểm tra exception từ tác vụ nền

Cách quan sát lỗi phụ thuộc kiểu trả về của phương thức async.

### 9.1. Phương thức trả về Future hoặc CompletableFuture

Nếu phương thức trả về CompletableFuture, exception có thể được quan sát qua future:

~~~java
@Async("testExecutor")
public CompletableFuture<String> executeAndFail() {
    throw new IllegalStateException("background failure");
}
~~~

Test:

~~~java
CompletableFuture<String> future = worker.executeAndFail();

assertThatThrownBy(() -> future.get(2, TimeUnit.SECONDS))
        .isInstanceOf(ExecutionException.class)
        .hasCauseInstanceOf(IllegalStateException.class);
~~~

Có thể dùng join() và kiểm tra CompletionException, nhưng get(timeout, unit) hữu ích khi test cần giới hạn thời gian chờ.

### 9.2. Phương thức trả về void

Với @Async void, caller không nhận được future để quan sát exception. Spring chuyển exception sang AsyncUncaughtExceptionHandler. Có thể cấu hình handler trong AsyncConfigurer hoặc cấu hình async tương ứng:

~~~java
@Configuration
@EnableAsync
public class AsyncConfiguration implements AsyncConfigurer {

    @Override
    public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return (exception, method, params) -> {
            // Ghi log, phát metric hoặc chuyển tới cơ chế xử lý lỗi.
        };
    }
}
~~~

Trong test, có thể cung cấp handler giả ghi nhận exception vào BlockingQueue hoặc CountDownLatch, rồi chờ và assert exception. Tránh chỉ kiểm tra log console vì log không phải kênh giao tiếp ổn định giữa tác vụ và test.

## 10. Không dùng sleep để đồng bộ test

Thread.sleep(...) thường tạo ra test chập chờn:

~~~java
worker.execute();
Thread.sleep(500);
assertThat(repository.findResult()).isNotNull();
~~~

Test trên chỉ giả định 500 ms đủ để tác vụ hoàn tất. Khi CI bận, task có thể chưa chạy; khi máy nhanh, test lại lãng phí thời gian chờ. Sleep cũng không cho biết task thất bại hay chưa được schedule.

Thay bằng tín hiệu hoàn tất:

~~~java
CompletableFuture<Result> future = worker.execute();
Result result = future.get(2, TimeUnit.SECONDS);
assertThat(result).isNotNull();
~~~

Hoặc dùng latch cho phương thức void:

~~~java
assertThat(completed.await(2, TimeUnit.SECONDS)).isTrue();
assertThat(resultReference.get()).isEqualTo(expected);
~~~

Awaitility cũng hữu ích khi test chờ một điều kiện được cập nhật qua nhiều thành phần:

~~~java
await()
        .atMost(Duration.ofSeconds(2))
        .untilAsserted(() ->
                assertThat(repository.findById(id)).isPresent());
~~~

Awaitility phù hợp khi test không có future hoặc latch trực tiếp và cần chờ một trạng thái quan sát được. Đặt timeout hữu hạn và polling interval hợp lý; không dùng forever() trong test.

## 11. Thread safety và dữ liệu dùng chung trong test

Khi nhiều tác vụ chạy song song, các biến mutable dùng chung cần được bảo vệ. ArrayList, HashMap và biến primitive thông thường không tự an toàn khi nhiều thread cùng ghi.

Các lựa chọn thường gặp:

- AtomicInteger, AtomicReference cho một giá trị cần cập nhật nguyên tử.
- ConcurrentHashMap cho map được truy cập đồng thời.
- BlockingQueue để chuyển kết quả từ worker về test thread.
- CountDownLatch, CyclicBarrier hoặc Phaser để phối hợp thời điểm thực thi.
- Các collection concurrent phù hợp với thao tác thực tế.

Ví dụ thu kết quả từ nhiều worker:

~~~java
BlockingQueue<String> results = new LinkedBlockingQueue<>();
CountDownLatch completed = new CountDownLatch(3);

for (String id : List.of("A", "B", "C")) {
    executor.execute(() -> {
        try {
            results.add(process(id));
        }
        finally {
            completed.countDown();
        }
    });
}

assertThat(completed.await(2, TimeUnit.SECONDS)).isTrue();
assertThat(results).containsExactlyInAnyOrder(
        "done-A", "done-B", "done-C");
~~~

Nếu thứ tự hoàn tất không phải một phần hợp đồng, dùng assertion không phụ thuộc thứ tự như containsExactlyInAnyOrder. Chỉ kiểm tra thứ tự khi hệ thống thật sự phải bảo đảm thứ tự đó.

## 12. Kiểm soát context và executor dùng chung giữa các test

Spring TestContext có thể cache ApplicationContext và tái sử dụng context giữa nhiều test. Executor là singleton bean trong context có thể được nhiều test cùng dùng. Điều này ảnh hưởng khi:

- Một test chủ động shutdown executor.
- Một test thay đổi cấu hình hoặc state của executor.
- Các test đồng thời gửi tác vụ vào cùng queue.
- Một test giữ latch hoặc barrier khiến worker bị chiếm dụng.
- Một test dùng mock hoặc probe mutable được chia sẻ giữa nhiều method.

Không nên gọi shutdown() trên executor được inject từ Spring context trong từng test method; Spring quản lý vòng đời bean đó. Nếu cần kiểm tra shutdown hoặc rejection, tạo executor riêng trong test và tự đóng nó.

Với test chạy song song bằng JUnit Jupiter, có thể dùng @Execution(ExecutionMode.CONCURRENT) khi các test độc lập và thread-safe. Nếu nhiều test phải dùng chung một tài nguyên có trạng thái, dùng @ResourceLock để tuần tự hóa phần truy cập tài nguyên đó:

~~~java
@Execution(ExecutionMode.CONCURRENT)
class IndependentAsyncTests {
    // Mỗi test dùng dữ liệu riêng và không sửa shared state.
}

@ResourceLock("shared-system-property")
class TestsUsingSharedSystemProperty {
    // Các test dùng chung property này được phối hợp theo resource lock.
}
~~~

Parallel execution của JUnit phải được bật trong cấu hình test engine. Chỉ thêm annotation @Execution không có nghĩa toàn bộ dự án đã bật chạy song song.

Không dùng @DirtiesContext như cách mặc định để sửa mọi vấn đề cạnh tranh. Chỉ đánh dấu context dirty khi test thực sự thay đổi cấu hình hoặc state khiến context không thể tái sử dụng an toàn. Với executor, cách tốt hơn thường là tách resource riêng, làm test độc lập và để Spring quản lý lifecycle.

## 13. Truyền context qua thread bằng TaskDecorator

Thông tin gắn với thread như MDC logging context hoặc một số ThreadLocal không tự động chuyển sang worker thread. Nếu tác vụ nền cần context đó, ứng dụng có thể cấu hình TaskDecorator để chụp context lúc submit và khôi phục nó trong worker:

~~~java
executor.setTaskDecorator(task -> {
    Map<String, String> contextMap = MDC.getCopyOfContextMap();

    return () -> {
        Map<String, String> previous = MDC.getCopyOfContextMap();
        try {
            if (contextMap == null) {
                MDC.clear();
            }
            else {
                MDC.setContextMap(contextMap);
            }
            task.run();
        }
        finally {
            if (previous == null) {
                MDC.clear();
            }
            else {
                MDC.setContextMap(previous);
            }
        }
    };
});
~~~

Nếu ứng dụng có TaskDecorator, nên kiểm tra context được truyền sang worker và được dọn sau khi task kết thúc để không rò rỉ dữ liệu giữa các tác vụ dùng chung thread. Test nên tạo context khác nhau cho các task và xác nhận worker đọc đúng giá trị của từng task.

Không giả định mọi context đều có thể copy bằng TaskDecorator. Security context, transaction context và request context có quy tắc riêng. Transaction gắn với thread không tự động được chuyển sang worker; nếu tác vụ cần transaction, hãy mở transaction phù hợp trong tác vụ. Với request-scoped object, tránh giữ tham chiếu sau khi request kết thúc.

## 14. Shutdown và tác vụ còn đang chạy

Executor là tài nguyên có vòng đời. Khi application context đóng, Spring hủy executor bean và ThreadPoolTaskExecutor có các tùy chọn như:

- setWaitForTasksToCompleteOnShutdown(true): chờ các tác vụ đã nhận hoàn tất trong quá trình shutdown.
- setAwaitTerminationSeconds(...): giới hạn thời gian chờ trước khi kết thúc shutdown.
- setWaitForTasksToCompleteOnShutdown(false): không chờ tác vụ hoàn tất theo cách cấu hình chờ graceful shutdown.

Test tích hợp có thể kiểm tra hành vi shutdown với executor riêng, một task đang giữ latch và thời gian chờ được cấu hình. Hãy luôn giải phóng latch trong finally để không để lại worker treo khi test assertion thất bại.

Không nên cho rằng graceful shutdown bảo đảm task sống sót qua sự cố process hoặc máy. Thread pool giữ task trong bộ nhớ; nếu công việc bắt buộc phải được giao nhận lại sau restart, cần hàng đợi bền vững hoặc cơ chế lưu trạng thái nghiệp vụ.

## 15. Chọn chiến lược test theo mục tiêu

| Mục tiêu cần xác nhận | Chiến lược phù hợp |
|---|---|
| Kiểm tra logic phần thân tác vụ, không cần thread thật | Dùng SyncTaskExecutor trong test |
| Chờ kết quả của tác vụ async | Trả về CompletableFuture và dùng get(timeout) |
| Chờ tác vụ void hoàn tất | CountDownLatch hoặc một completion signal thread-safe |
| Xác nhận task chạy trên executor cụ thể | Thread name prefix hoặc probe ghi nhận thread |
| Xác nhận nhiều task chạy đồng thời | Pool có nhiều worker kết hợp latch/barrier |
| Kiểm tra queue đầy hoặc từ chối task | Executor test riêng với pool và queue nhỏ |
| Kiểm tra exception từ async method có kết quả | Assert future hoàn tất exceptional |
| Kiểm tra exception từ async method void | Ghi nhận qua AsyncUncaughtExceptionHandler |
| Chờ trạng thái cập nhật qua nhiều thành phần | Awaitility với timeout hữu hạn |
| Kiểm tra ứng dụng dọn executor | Integration test lifecycle với executor riêng hoặc context được đóng có kiểm soát |

## 16. Quy trình kiểm thử một executor

Trước khi hoàn tất test, xác định rõ:

1. Test đang kiểm tra logic tác vụ, việc dispatch hay khả năng chạy song song?
2. Executor được tạo riêng cho test hay được Spring quản lý trong context?
3. Có cơ chế xác nhận task bắt đầu và hoàn tất không?
4. Mọi thao tác chờ có timeout hữu hạn không?
5. Exception có đường đi để test quan sát không?
6. Các biến dùng chung có thread-safe không?
7. Test có phụ thuộc thứ tự thực thi không cần thiết không?
8. Latch, barrier và executor riêng có được giải phóng/đóng trong finally không?
9. Test có vô tình shutdown hoặc làm cạn executor singleton dùng chung không?
10. Nếu kiểm tra @Async, lời gọi có đi qua Spring proxy không?

Kiểm soát executor trong test không có nghĩa là ép mọi tác vụ chạy đồng bộ. Hãy dùng executor đồng bộ khi chỉ cần kiểm tra logic; dùng thread pool có cấu hình rõ khi cần kiểm tra dispatch, concurrency, queue hoặc rejection. Kết hợp completion signal, timeout hữu hạn và dữ liệu thread-safe sẽ giúp test nền chạy ổn định và thể hiện đúng hành vi mà ứng dụng cần bảo đảm.
