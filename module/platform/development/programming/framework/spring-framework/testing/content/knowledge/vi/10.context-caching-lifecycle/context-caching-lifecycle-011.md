# Đóng context, tác vụ nền và tài nguyên đang sử dụng

Một `ApplicationContext` không chỉ chứa các bean để inject. Trong một ứng dụng Spring đang chạy, bean còn có thể sở hữu connection pool, HTTP client, message consumer, thread pool, scheduler, file handle hoặc socket. Khi context đóng, những thành phần này cần được dừng theo thứ tự phù hợp để ứng dụng không còn nhận công việc mới, tác vụ đang chạy có cơ hội hoàn tất và tài nguyên được giải phóng an toàn.

Điều này đặc biệt quan trọng trong kiểm thử tích hợp. TestContext Framework có thể cache và tái sử dụng context giữa nhiều test class. Khi một test đánh dấu context dirty hoặc một test tự đóng context, Spring phải hủy bean và các tài nguyên do chúng quản lý. Nếu tác vụ nền vẫn đang chạy hoặc bean tự tạo thread không được quản lý, test sau có thể gặp lỗi ngẫu nhiên, giữ cổng mạng, ghi dữ liệu sau khi test đã kết thúc hoặc làm tiến trình test không thoát.

## 1. Vòng đời của `ApplicationContext`

`ApplicationContext` thường được tạo khi ứng dụng khởi động và tồn tại cho đến khi ứng dụng dừng hoặc test framework loại context khỏi cache. Các bước khái quát khi đóng context gồm:

1. Context chuyển sang trạng thái đóng và phát `ContextClosedEvent`.
2. Spring yêu cầu các bean tham gia cơ chế lifecycle dừng hoạt động.
3. Spring gọi destruction callback của các singleton bean được quản lý.
4. Bean factory được đóng và context giải phóng các cấu trúc nội bộ.

Trong quá trình shutdown, Spring phối hợp `LifecycleProcessor` để dừng các bean `Lifecycle`/`SmartLifecycle`, rồi thực hiện hủy singleton bean. Nhờ vậy, thành phần đang nhận công việc có thể dừng trước khi dependency mà nó sử dụng bị đóng.

Một context có thể được đóng trực tiếp qua `ConfigurableApplicationContext.close()`:

```java
ConfigurableApplicationContext context =
        new AnnotationConfigApplicationContext(AppConfiguration.class);

try {
    MyService service = context.getBean(MyService.class);
    service.performWork();
} finally {
    context.close();
}
```

Với context được tạo trong ứng dụng độc lập, có thể đăng ký shutdown hook để JVM yêu cầu Spring đóng context khi tiến trình kết thúc:

```java
ConfigurableApplicationContext context =
        new AnnotationConfigApplicationContext(AppConfiguration.class);
context.registerShutdownHook();
```

Shutdown hook giúp xử lý việc đóng context khi JVM shutdown bình thường. Nó không thay thế việc quản lý vòng đời trong ứng dụng chạy lâu dài, và không bảo đảm cleanup khi tiến trình bị kill cưỡng bức hoặc máy bị tắt đột ngột.

## 2. Các cơ chế hủy bean

Spring cung cấp nhiều cách để bean giải phóng tài nguyên khi context đóng. Có thể dùng annotation, interface hoặc khai báo destroy method trong bean definition.

### 2.1. `@PreDestroy`

`@PreDestroy` đánh dấu phương thức được gọi trong giai đoạn hủy bean:

```java
@Component
class LocalCache {
    private final Map<String, String> entries = new ConcurrentHashMap<>();

    @PreDestroy
    void clear() {
        entries.clear();
    }
}
```

Đây là cách phổ biến để đóng client, xóa tài nguyên nội bộ hoặc ghi nhận trạng thái kết thúc. Với Spring Framework hiện đại, annotation nằm trong namespace Jakarta (`jakarta.annotation.PreDestroy`), nên dự án cần dependency annotation phù hợp nếu runtime không cung cấp sẵn.

Phương thức cleanup nên ngắn, có thể gọi an toàn và không phụ thuộc vào một test method cụ thể. Tránh để exception trong cleanup che mất lỗi gốc của test; nếu giải phóng nhiều tài nguyên, hãy cố gắng đóng tất cả và ghi nhận lỗi theo cách phù hợp.

### 2.2. `DisposableBean`

Bean có thể triển khai `DisposableBean` và định nghĩa `destroy()`:

```java
class LegacySocketClient implements DisposableBean {
    private final Socket socket;

    LegacySocketClient(Socket socket) {
        this.socket = socket;
    }

    @Override
    public void destroy() throws IOException {
        socket.close();
    }
}
```

Spring gọi `destroy()` khi hủy bean singleton được quản lý. Cách này gắn class trực tiếp với Spring API, vì vậy `@PreDestroy` hoặc destroy method trên bean definition thường giúp domain class ít phụ thuộc Spring hơn.

### 2.3. Khai báo `destroyMethod` trên `@Bean`

Với thư viện bên thứ ba mà ta không thể sửa class, có thể khai báo phương thức đóng trong `@Bean`:

```java
@Configuration
class ClientConfiguration {
    @Bean(destroyMethod = "close")
    ExternalClient externalClient() {
        return new ExternalClient();
    }
}
```

Khi context đóng, Spring gọi `close()` trên bean. Có thể chỉ định `shutdown` hoặc một phương thức cleanup phù hợp với API của thư viện:

```java
@Bean(destroyMethod = "shutdown")
MessageProducer messageProducer() {
    return new MessageProducer();
}
```

Spring có cơ chế suy luận một số destroy method phổ biến như `close` hoặc `shutdown` cho bean được khai báo qua `@Bean`, nhưng khai báo tường minh giúp người đọc thấy rõ trách nhiệm quản lý tài nguyên. Khi thư viện không có phương thức cleanup, có thể dùng `destroyMethod = ""` để tắt suy luận tự động nếu cần.

### 2.4. So sánh các cách cleanup

| Cơ chế | Cách khai báo | Phù hợp khi |
|---|---|---|
| `@PreDestroy` | Annotation trên phương thức bean | Có thể chỉnh sửa class và muốn dùng callback chuẩn Jakarta |
| `DisposableBean` | Implement `destroy()` | Bean tích hợp trực tiếp với Spring lifecycle |
| `@Bean(destroyMethod = ...)` | Khai báo trên bean factory method | Quản lý thư viện bên thứ ba hoặc chọn phương thức cleanup |
| `Lifecycle` / `SmartLifecycle` | Implement `stop()` hoặc `stop(Runnable)` | Bean cần quy trình start/stop và phối hợp với thành phần khác |
| `ContextClosedEvent` | Listener nhận sự kiện đóng context | Phản ứng với sự kiện toàn context hoặc ghi nhận trạng thái shutdown |

Không cần triển khai nhiều cơ chế cleanup cho cùng một tài nguyên nếu chúng có thể đóng nó hai lần. Hãy xác định một nơi sở hữu việc đóng và làm cho thao tác cleanup an toàn khi được gọi theo vòng đời thực tế.

## 3. Thứ tự hủy bean và quan hệ dependency

Nếu bean A phụ thuộc bean B, Spring cần hủy A trước B để A còn có thể dùng B trong quá trình cleanup. Ví dụ, một message consumer phụ thuộc vào connection factory; consumer cần dừng và đóng subscription trước khi connection factory bị đóng.

```java
@Configuration
class MessagingConfiguration {
    @Bean(destroyMethod = "close")
    BrokerConnection brokerConnection() {
        return new BrokerConnection();
    }

    @Bean(destroyMethod = "close")
    MessageConsumer messageConsumer(BrokerConnection connection) {
        return connection.createConsumer();
    }
}
```

Spring biết quan hệ dependency qua tham số của `@Bean` và quá trình tạo bean. Khi hủy singleton, các bean phụ thuộc được giải phóng trước dependency mà chúng cần. Hãy khai báo dependency qua constructor hoặc tham số `@Bean` thay vì tự tìm bean bằng static registry; quan hệ rõ ràng giúp Spring quản lý thứ tự lifecycle chính xác hơn.

Nếu một bean khởi chạy công việc nền nhưng không khai báo dependency đến tài nguyên mà công việc đó sử dụng, Spring có thể không biết thứ tự cần thiết. Hãy thiết kế bean graph thể hiện rõ mối quan hệ hoặc dùng `SmartLifecycle` để điều phối start/stop.

## 4. `Lifecycle` và `SmartLifecycle`

`Lifecycle` cung cấp các phương thức `start()`, `stop()` và `isRunning()`. Bean triển khai interface này có thể tham gia vào lifecycle của context:

```java
class MessageListenerContainer implements Lifecycle {
    private boolean running;

    @Override
    public void start() {
        running = true;
        // Bắt đầu nhận message.
    }

    @Override
    public void stop() {
        // Dừng nhận message và giải phóng tài nguyên.
        running = false;
    }

    @Override
    public boolean isRunning() {
        return running;
    }
}
```

`SmartLifecycle` mở rộng `Lifecycle`, bổ sung khả năng tự khởi động, thứ tự theo phase và callback để báo hoàn tất việc dừng bất đồng bộ:

```java
class BackgroundConsumer implements SmartLifecycle {
    private volatile boolean running;

    @Override
    public void start() {
        running = true;
        // Khởi động worker hoặc đăng ký consumer.
    }

    @Override
    public void stop(Runnable callback) {
        running = false;
        // Dừng nhận công việc mới, chờ công việc đang chạy kết thúc.
        callback.run();
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }

    @Override
    public int getPhase() {
        return 100;
    }
}
```

Trong ví dụ, `callback.run()` chỉ được gọi sau khi bean đã dừng xong. Nếu việc dừng cần chờ worker, callback phải được gọi từ đường hoàn tất thực tế sau khi worker kết thúc; gọi callback ngay sau khi gửi lệnh stop sẽ khiến Spring nghĩ bean đã dừng dù tài nguyên vẫn đang được sử dụng.

### 4.1. Phase điều khiển thứ tự start/stop

`SmartLifecycle` dùng phase để sắp xếp các bean. Khi khởi động, phase thấp hơn được start trước; khi dừng, thứ tự đảo ngược, nên phase cao hơn được stop trước.

Điều này hữu ích khi một consumer cần connection factory:

1. Khi khởi động, connection factory phải sẵn sàng trước consumer.
2. Khi đóng, consumer phải dừng trước khi connection factory đóng.

Có thể gán phase cao hơn cho consumer và phase thấp hơn cho connection factory. Hãy dùng dependency injection để thể hiện quan hệ bean, và dùng phase khi cần phối hợp giữa những thành phần lifecycle mà thứ tự không thể suy ra đầy đủ từ dependency graph.

Các bean cùng phase có thể được xử lý theo nhóm bởi lifecycle processor. Không nên dựa vào thứ tự khai báo class hoặc thứ tự scan component để điều khiển shutdown.

### 4.2. `stop(Runnable)` và dừng bất đồng bộ

Một worker có thể cần thời gian để hoàn thành message đang xử lý. `SmartLifecycle.stop(Runnable callback)` cho phép bean dừng bất đồng bộ và báo lại khi đã hoàn tất:

```java
@Override
public void stop(Runnable callback) {
    acceptingMessages = false;
    workerExecutor.shutdown();

    Thread waiter = new Thread(() -> {
        try {
            if (!workerExecutor.awaitTermination(10, TimeUnit.SECONDS)) {
                workerExecutor.shutdownNow();
            }
        } catch (InterruptedException exception) {
            workerExecutor.shutdownNow();
            Thread.currentThread().interrupt();
        } finally {
            callback.run();
        }
    }, "consumer-shutdown-waiter");
    waiter.start();
}
```

Đây là minh họa về callback hoàn tất; trong ứng dụng thật, nên dùng executor hoặc cơ chế lifecycle có quản lý để thực hiện việc chờ thay vì tạo một thread tùy tiện. Đảm bảo mọi đường kết thúc đều gọi callback đúng một lần, kể cả khi worker gặp lỗi hoặc bị timeout.

## 5. Quản lý thread pool với `TaskExecutor`

Spring cung cấp `TaskExecutor` để ứng dụng gửi tác vụ vào executor do container quản lý. `ThreadPoolTaskExecutor` là implementation phổ biến:

```java
@Configuration
@EnableAsync
class AsyncConfiguration {
    @Bean
    ThreadPoolTaskExecutor applicationTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("app-worker-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(10);
        return executor;
    }
}
```

`ThreadPoolTaskExecutor` được Spring quản lý như bean và có lifecycle cleanup. Hai thiết lập đáng chú ý:

- `setWaitForTasksToCompleteOnShutdown(true)` yêu cầu executor chờ các tác vụ đã nhận hoàn tất trong quá trình shutdown theo chính sách của executor.
- `setAwaitTerminationSeconds(10)` đặt khoảng thời gian chờ kết thúc trước khi shutdown tiếp tục.

Thời gian chờ cần phù hợp với công việc và giới hạn shutdown của ứng dụng. Nếu task có thể treo vô hạn, chờ vô hạn sẽ khiến context không đóng xong; nếu timeout quá ngắn, task có thể bị ngắt khi đang ghi dữ liệu hoặc giải phóng tài nguyên.

### 5.1. `@Async` và tác vụ đang chạy

`@Async` gửi lời gọi đến executor thay vì chạy trên thread gọi ban đầu:

```java
@Service
class ReportService {
    @Async("applicationTaskExecutor")
    public CompletableFuture<Report> generateAsync(ReportCommand command) {
        Report report = generate(command);
        return CompletableFuture.completedFuture(report);
    }
}
```

Khi context đóng, executor cần ngừng nhận task mới và xử lý task đang chạy theo chính sách shutdown. Không nên giả định việc gọi `close()` trên context sẽ tự hoàn tất mọi công việc nền trong mọi cấu hình. Hãy cấu hình executor và viết test xác nhận chính sách chờ hoặc hủy phù hợp.

Một điểm quan trọng: `@Async` hoạt động qua proxy Spring. Lời gọi một phương thức async từ phương thức khác trong cùng instance (self-invocation) thường không đi qua proxy, nên có thể chạy đồng bộ. Nếu test không thấy tác vụ được gửi vào executor, hãy kiểm tra cách gọi bean và cấu hình `@EnableAsync`.

### 5.2. Tác vụ bị từ chối khi shutdown

Sau khi executor bắt đầu shutdown, việc gửi task mới có thể bị từ chối. Ứng dụng nên có cách xử lý `TaskRejectedException` hoặc exception tương ứng, tùy executor và abstraction sử dụng.

Không gửi công việc mới từ `@PreDestroy` vào chính executor đang bị đóng nếu không có chính sách cho phép. Việc đó có thể tạo vòng lặp shutdown hoặc task bị từ chối. Nếu cần hoàn tất một bước cuối, hãy thực hiện trong lifecycle stop có thứ tự rõ ràng và bảo đảm dependency còn hoạt động.

## 6. Quản lý scheduler và tác vụ định kỳ

`@Scheduled` đăng ký phương thức chạy theo lịch. Scheduler có thể tiếp tục đánh thức tác vụ trong khi context đang shutdown nếu vòng đời không được quản lý đúng.

```java
@Configuration
@EnableScheduling
class SchedulingConfiguration {
    @Bean
    ThreadPoolTaskScheduler taskScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(2);
        scheduler.setThreadNamePrefix("scheduled-");
        scheduler.setWaitForTasksToCompleteOnShutdown(true);
        scheduler.setAwaitTerminationSeconds(10);
        return scheduler;
    }
}
```

Scheduler do Spring quản lý có thể được đóng theo lifecycle bean. Khi shutdown, ứng dụng cần ngừng lập lịch lần chạy mới, xử lý hoặc hủy các lần chạy đã được lên lịch theo chính sách đã chọn, rồi chờ tác vụ đang thực hiện kết thúc.

Với scheduler tùy biến, hãy kiểm tra các chính sách của implementation như tiếp tục periodic task sau shutdown hay thực thi delayed task đã lên lịch. Đừng giả định mọi `ScheduledExecutorService` có hành vi giống nhau.

### 6.1. Không dùng `Thread.sleep` để kiểm thử scheduler

Test scheduler bằng sleep cố định thường chậm và flaky. Ưu tiên:

- Dùng scheduler test có thể điều khiển thời gian nếu framework cung cấp.
- Dùng latch/future để chờ tác vụ thực sự được thực thi với timeout.
- Tách logic nghiệp vụ khỏi phương thức `@Scheduled` để unit test logic trực tiếp.
- Kiểm tra việc scheduler bị dừng qua lifecycle hoặc trạng thái tài nguyên thay vì chờ một khoảng dài để hy vọng không có lần chạy tiếp theo.

## 7. Tài nguyên do bean sở hữu

Một bean có thể sở hữu tài nguyên mà nếu không đóng sẽ làm rò rỉ socket, file descriptor, thread hoặc connection. Các ví dụ thường gặp:

| Tài nguyên | Việc cần làm khi shutdown |
|---|---|
| JDBC connection pool / datasource | Ngừng cấp connection mới và đóng pool |
| HTTP client có connection pool | Đóng client/pool và giải phóng event loop nếu client sở hữu |
| Kafka/JMS producer hoặc consumer | Ngừng nhận message, flush nếu cần, đóng client |
| File hoặc stream | Flush dữ liệu cần giữ rồi đóng stream |
| Socket/server | Ngừng nhận kết nối mới và đóng socket |
| Executor/scheduler | Ngừng nhận task, chờ hoặc hủy task theo chính sách rồi giải phóng thread |
| Cache hoặc registry | Ngừng truy cập và giải phóng tài nguyên nội bộ nếu có |

Tài nguyên nên có một bean chịu trách nhiệm sở hữu và đóng. Những bean khác dùng nó qua dependency injection. Tránh để nhiều bean cùng gọi close trên một đối tượng dùng chung mà không có quy tắc ownership rõ ràng.

### 7.1. `AutoCloseable` và try-with-resources

Với tài nguyên cục bộ trong một test hoặc một thao tác, `try-with-resources` thường đơn giản nhất:

```java
@Test
void readsFileAndClosesStream() throws IOException {
    try (InputStream input = Files.newInputStream(testFile)) {
        assertThat(input.read()).isNotEqualTo(-1);
    }
}
```

Với tài nguyên có vòng đời bằng context, đăng ký nó thành bean và khai báo destroy method:

```java
@Configuration
class FileClientConfiguration {
    @Bean(destroyMethod = "close")
    FileClient fileClient() {
        return new FileClient();
    }
}
```

Chọn phạm vi sở hữu theo thời gian sống thực tế: tài nguyên chỉ dùng trong một test nên được đóng trong test; tài nguyên chia sẻ trong context nên được Spring quản lý đến khi context đóng.

## 8. `ContextClosedEvent` và phản ứng với shutdown

Spring phát `ContextClosedEvent` khi context bắt đầu đóng. Bean có thể lắng nghe sự kiện này:

```java
@Component
class ShutdownAuditListener {
    @EventListener
    void onContextClosed(ContextClosedEvent event) {
        // Ghi nhận context bắt đầu đóng.
    }
}
```

Sự kiện phù hợp cho hành vi phản ứng ở phạm vi ứng dụng, chẳng hạn ghi nhận shutdown hoặc phát tín hiệu đến một thành phần quản lý. Với việc quản lý lifecycle của worker, executor hoặc resource, `SmartLifecycle`, destroy callback hoặc bean ownership thường diễn đạt trách nhiệm trực tiếp hơn.

Không giả định một listener bất đồng bộ sẽ hoàn thành trước khi context đóng. Nếu listener dùng `@Async`, nó lại phụ thuộc vào executor đang shutdown. Một bước cleanup quan trọng nên được thực hiện đồng bộ hoặc được quản lý bằng lifecycle callback có cơ chế chờ hoàn tất.

## 9. Đóng context trong kiểm thử tích hợp

Spring TestContext Framework cache `ApplicationContext` để tránh khởi động lại cùng cấu hình cho từng test class. Vì vậy, vòng đời context thường dài hơn một test method và có thể dài hơn một test class.

### 9.1. Không tự đóng context được cache trong test method

Nếu test inject `ApplicationContext` rồi gọi `close()` trực tiếp, Spring TestContext cache có thể vẫn giữ tham chiếu đến context đã đóng. Test class tiếp theo có cùng cache key có thể lấy lại context không còn hoạt động.

Khi test làm bẩn context và cần Spring loại nó khỏi cache, dùng `@DirtiesContext`:

```java
@SpringBootTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class ContextShutdownIntegrationTest {
    // Test thay đổi trạng thái cấp context và yêu cầu đóng sau class.
}
```

`@DirtiesContext` đánh dấu context dirty để TestContext Framework loại nó khỏi cache và đóng nó ở thời điểm phù hợp. Các chế độ method/class cho phép chọn thời điểm trước hoặc sau method/class.

Không dùng `@DirtiesContext` chỉ để xóa record trong database hoặc message trong broker. Hãy dùng rollback, dữ liệu có định danh riêng hoặc cleanup tài nguyên tương ứng.

### 9.2. Kiểm tra destroy callback

Có thể dùng một bean test ghi nhận việc đóng để xác nhận Spring gọi cleanup khi context bị đóng:

```java
class CloseTracker {
    private boolean closed;

    void close() {
        closed = true;
    }

    boolean isClosed() {
        return closed;
    }
}

@Configuration
class CloseTrackerConfiguration {
    @Bean(destroyMethod = "close")
    CloseTracker closeTracker() {
        return new CloseTracker();
    }
}

@Test
void invokesBeanDestroyMethodWhenContextCloses() {
    AnnotationConfigApplicationContext context =
            new AnnotationConfigApplicationContext(CloseTrackerConfiguration.class);
    CloseTracker tracker = context.getBean(CloseTracker.class);

    context.close();

    assertThat(tracker.isClosed()).isTrue();
}
```

Test dùng context tự tạo, không phải context đang được TestContext Framework cache. Điều đó cho phép đóng trực tiếp và kiểm tra destroy callback mà không làm hỏng context dùng chung của suite.

### 9.3. Kiểm tra tác vụ nền trước khi đóng

Nếu test gửi task bất đồng bộ, hãy chờ task hoàn tất trước khi assertion hoặc cleanup tài nguyên:

```java
@Test
void waitsForAsyncWorkToComplete() throws Exception {
    CompletableFuture<Result> result = service.processAsync(command);

    Result completed = result.get(2, TimeUnit.SECONDS);

    assertThat(completed.status()).isEqualTo(Status.COMPLETED);
}
```

`get(timeout, unit)` giúp test kết thúc có giới hạn nếu worker bị treo. Sau khi future hoàn tất, test có thể xác nhận tác dụng phụ hoặc trạng thái đã được cập nhật.

Nếu API chỉ trả về khi task được xếp hàng chứ không có future, dùng `CountDownLatch` hoặc test observer. Tránh `Thread.sleep` để đoán worker đã chạy xong.

## 10. Tác vụ đang sử dụng tài nguyên khi context đóng

Một vấn đề khó là worker vẫn đang dùng datasource, HTTP client hoặc file stream trong khi context bắt đầu hủy bean. Nếu tài nguyên bị đóng trước, worker có thể ném lỗi giữa chừng hoặc ghi dữ liệu không đầy đủ.

Hãy tổ chức shutdown theo thứ tự:

1. Ngừng nhận yêu cầu hoặc message mới.
2. Ngừng lên lịch công việc mới.
3. Chờ các tác vụ đang chạy hoàn tất trong một khoảng thời gian hữu hạn.
4. Nếu hết thời gian, yêu cầu hủy hoặc interrupt theo chính sách của tác vụ.
5. Đóng các client, connection pool và tài nguyên mà worker sử dụng.

Để Spring thực hiện thứ tự này, dùng dependency graph và `SmartLifecycle` phase. Bean xử lý công việc cần dừng trước bean cung cấp tài nguyên cho nó. Với executor, cấu hình wait/await termination phù hợp và bảo đảm task có thể phản ứng với interruption hoặc cancellation.

Không phải tác vụ nào cũng có thể dừng ngay. Một giao dịch đang ghi dữ liệu có thể cần hoàn tất hoặc rollback; một message consumer có thể cần ack/nack rõ ràng; một file writer có thể cần flush. Chính sách shutdown cần phù hợp với loại công việc và yêu cầu nhất quán của ứng dụng.

### 10.1. Task cần hỗ trợ cancellation

Task dài nên kiểm tra trạng thái interrupt hoặc cancellation ở những điểm an toàn:

```java
void processLargeBatch(List<Item> items) throws InterruptedException {
    for (Item item : items) {
        if (Thread.currentThread().isInterrupted()) {
            throw new InterruptedException("Batch processing interrupted");
        }

        process(item);
    }
}
```

Không nuốt `InterruptedException`. Nếu bắt exception để cleanup hoặc chuyển đổi lỗi, hãy khôi phục interrupt status khi phù hợp bằng `Thread.currentThread().interrupt()`. Điều này cho phép executor và shutdown logic nhận biết task đã được yêu cầu dừng.

### 10.2. Timeout và công việc không thể dừng

Chọn thời gian chờ dựa trên SLA shutdown và thời lượng công việc thực tế. Nếu task không thể bị interrupt an toàn, có thể cần để nó hoàn tất hoặc chuyển công việc sang cơ chế durable queue để tiến trình khác tiếp tục. Không chờ vô hạn trong shutdown hook, vì JVM có thể bị giữ lại không kết thúc.

## 11. Context hierarchy và tài nguyên chia sẻ

Một ứng dụng có thể có parent context và child context. Khi child đóng, Spring hủy bean thuộc child context. Parent context có vòng đời riêng và có thể được chia sẻ bởi child khác.

Điều này quan trọng trong test hierarchy: đóng child context không có nghĩa mọi tài nguyên của parent đã được đóng. Nếu parent sở hữu datasource dùng chung, hãy để thành phần sở hữu parent quản lý việc đóng datasource. Tránh để child đóng một tài nguyên mà parent hoặc sibling context vẫn đang sử dụng.

Nếu nhiều context cùng tham chiếu một tài nguyên ngoài Spring, cần xác định một owner duy nhất và quản lý reference/lifecycle rõ ràng. Không để mỗi context tự đóng cùng một client dùng chung trừ khi client hỗ trợ việc đó.

## 12. Những lỗi thường gặp khi đóng context

### Thread vẫn chạy sau khi test kết thúc

Nguyên nhân thường là thread được tạo thủ công, executor không được quản lý hoặc shutdown không chờ task. Đăng ký executor thành bean, cấu hình shutdown và bảo đảm task có điểm kết thúc/cancellation.

### Context đóng nhưng socket vẫn mở

Bean sở hữu client/socket chưa có destroy callback hoặc tài nguyên được tạo ngoài container. Đăng ký bean với `destroyMethod = "close"`, `@PreDestroy` hoặc một lifecycle owner rõ ràng.

### Test sau nhận context đã đóng

Test tự gọi `close()` trên context đang được TestContext Framework cache. Dùng `@DirtiesContext` để framework loại và đóng context đúng cách, hoặc dùng context tự tạo riêng khi cần kiểm tra shutdown.

### Worker dùng datasource đã bị đóng

Thứ tự shutdown chưa đúng hoặc task chưa hoàn tất trước khi datasource bị hủy. Dừng worker trước, chờ task và chỉ sau đó đóng dependency.

### Callback `SmartLifecycle` được gọi quá sớm

Bean gọi callback ngay khi mới gửi lệnh stop. Spring tiếp tục hủy dependency trong khi worker còn chạy. Chỉ gọi callback sau khi quá trình dừng thực sự hoàn tất.

### `@PreDestroy` gửi thêm task vào executor đang shutdown

Task có thể bị từ chối hoặc không được chờ. Đưa bước dừng vào lifecycle có thứ tự phù hợp hoặc thực hiện cleanup đồng bộ trước khi executor đóng.

### Dùng `@DirtiesContext` để dọn mọi thứ

Đóng context không xóa database, file hoặc message bên ngoài. Dọn từng tài nguyên theo đúng cơ chế sở hữu.

## 13. Ví dụ tổng hợp: worker phụ thuộc vào client

Giả sử một ứng dụng có worker xử lý message bằng một client. Khi context đóng, worker phải dừng trước client. Có thể thể hiện quan hệ qua bean dependency và dùng `SmartLifecycle` cho worker:

```java
@Configuration
class WorkerConfiguration {
    @Bean(destroyMethod = "close")
    RemoteClient remoteClient() {
        return new RemoteClient();
    }

    @Bean
    MessageWorker messageWorker(RemoteClient remoteClient) {
        return new MessageWorker(remoteClient);
    }
}

class MessageWorker implements SmartLifecycle {
    private final RemoteClient client;
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private volatile boolean running;

    MessageWorker(RemoteClient client) {
        this.client = client;
    }

    @Override
    public void start() {
        running = true;
        // Bắt đầu nhận và gửi công việc vào executor.
    }

    @Override
    public void stop(Runnable callback) {
        running = false;
        executor.shutdown();
        Thread waiter = new Thread(() -> {
            try {
                if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
                    executor.shutdownNow();
                }
            } catch (InterruptedException exception) {
                executor.shutdownNow();
                Thread.currentThread().interrupt();
            } finally {
                callback.run();
            }
        }, "message-worker-stop");
        waiter.start();
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public int getPhase() {
        return 100;
    }
}
```

Ví dụ minh họa thứ tự lifecycle; trong production, nên để executor thành bean do Spring quản lý hoặc dùng `ThreadPoolTaskExecutor` để tránh tự tạo waiter thread và quản lý shutdown thủ công. Nếu worker sử dụng executor riêng, worker phải sở hữu và đóng executor đó một cách rõ ràng. Dependency `RemoteClient` được inject qua constructor để Spring biết worker cần client và có thể hủy worker trước dependency.

Test có thể dùng một client fake ghi nhận `close()` và một worker có tín hiệu hoàn tất để xác nhận worker dừng trước khi client đóng. Khi kiểm tra thứ tự cleanup, hãy quan sát callback/lifecycle thực tế thay vì chỉ kiểm tra thứ tự gọi constructor.

## 14. Quy trình thiết kế shutdown cho integration test

Khi test hoặc ứng dụng tạo tài nguyên nền, hãy xác định:

1. Bean nào sở hữu tài nguyên và bean nào chỉ sử dụng nó?
2. Tài nguyên được tạo trong test method, test class hay `ApplicationContext`?
3. Có thread pool, scheduler hoặc consumer nào tiếp tục nhận công việc khi context đóng không?
4. Tác vụ đang chạy cần hoàn tất, rollback hay có thể bị hủy?
5. Destroy callback nào đóng từng tài nguyên và callback có an toàn khi lỗi xảy ra giữa chừng không?
6. Thứ tự shutdown có bảo đảm worker dừng trước dependency của nó không?
7. Test có dùng context cache không, và việc đóng context có cần thông qua `@DirtiesContext` không?
8. Có tài nguyên ngoài context như database, broker hoặc file cần cleanup riêng không?
9. Có timeout hữu hạn để suite không bị treo khi worker không dừng không?

Một test nên kết thúc khi các công việc nó khởi tạo đã hoàn tất hoặc được hủy theo chính sách. Không để task của test này tiếp tục ghi dữ liệu sau khi test khác đã bắt đầu.

## 15. Nguyên tắc cần nhớ

- Đóng `ApplicationContext` kích hoạt sự kiện đóng, dừng bean lifecycle và gọi destruction callback cho các bean được quản lý.
- Dùng `@PreDestroy`, `DisposableBean` hoặc `@Bean(destroyMethod = ...)` để giải phóng tài nguyên.
- Dùng `Lifecycle`/`SmartLifecycle` khi bean cần start/stop có thứ tự hoặc cần chờ dừng bất đồng bộ.
- Bean xử lý công việc nên dừng trước dependency mà nó đang sử dụng.
- Đăng ký executor và scheduler thành bean; cấu hình việc chờ hoặc hủy tác vụ đang chạy.
- Task dài cần có cơ chế timeout/cancellation và xử lý interruption đúng cách.
- Context cache có thể giữ context qua nhiều test; không tự đóng context đang được TestContext Framework quản lý.
- Dùng `@DirtiesContext` khi cần loại context khỏi cache; cleanup database, broker, file và tài nguyên ngoài bằng cơ chế riêng.
- Supplier, event listener hoặc `@PreDestroy` không nên âm thầm tạo thêm công việc trên executor đang shutdown.

Quản lý shutdown tốt giúp Spring đóng các bean theo đúng thứ tự, cho tác vụ nền cơ hội kết thúc và giải phóng tài nguyên mà không để lại thread hoặc kết nối tồn tại sau test. Trong integration test, việc xác định rõ owner, lifecycle và cách chờ hoàn tất là điều kiện để context cache hoạt động ổn định và suite có thể kết thúc sạch sẽ.
