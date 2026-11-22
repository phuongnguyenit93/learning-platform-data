# Vai trò của bộ thực thi trong các thành phần Spring khác

## 1. Một TaskExecutor, nhiều điểm tích hợp

Trong Spring Framework, **TaskExecutor** là giao diện dùng để **giao một công việc cho cơ chế thực thi**. Nó mở rộng java.util.concurrent.Executor và cung cấp phương thức **execute(Runnable)**. Cùng một kiểu giao diện này có thể được dùng ở nhiều tầng: phương thức bất đồng bộ, xử lý HTTP, sự kiện nội bộ, message channel hay các tác vụ của Spring Batch.

Ý nghĩa của TaskExecutor trong từng thành phần **không hoàn toàn giống nhau**. Thành phần tích hợp quyết định **lúc nào** và **vì sao** gửi task, còn executor quyết định **tài nguyên thực thi, hàng đợi, cách cấp luồng và hành vi khi quá tải** theo cấu hình của nó.

~~~text
Nguồn phát sinh công việc                 Điểm giao cho TaskExecutor
────────────────────────                  ────────────────────────────
Lời gọi @Async qua Spring proxy   ──────> thực thi thân phương thức
Spring MVC controller -> Callable ──────> chạy Callable, trả kết quả qua async dispatch
@EventListener / multicaster      ──────> gọi listener trên worker thread
Spring Batch                       ──────> xử lý công việc của Step/Flow/partition
Spring Integration ExecutorChannel ──────> chuyển message đến handler trên worker
Mã nghiệp vụ gọi execute(...)     ──────> chạy Runnable trực tiếp

@Scheduled / TaskScheduler        ──────> quyết định thời điểm kích hoạt
                                         (có thể giao công việc tiếp cho TaskExecutor)
~~~

Mô hình này giúp phân biệt ba trách nhiệm: **bên tạo yêu cầu**, **bộ thực thi công việc** và **cơ chế quan sát kết quả/lỗi**. Nếu chỉ tăng số thread mà không hiểu bên nào gửi task và điều gì xảy ra khi task bị từ chối, ứng dụng có thể trễ, tốn bộ nhớ hoặc mất công việc.

## 2. Nền tảng API và lựa chọn triển khai

### TaskExecutor và AsyncTaskExecutor

- **TaskExecutor**: API lõi nhận Runnable bằng execute(Runnable), tương thích với Executor của JDK. Bản thân interface không hứa công việc chạy ở luồng khác. Ví dụ **SyncTaskExecutor** gọi công việc ngay trên luồng gửi.
- **AsyncTaskExecutor**: mở rộng TaskExecutor với các tiện ích gửi task và nhận Future (API cụ thể phụ thuộc phiên bản). Tích hợp **Spring MVC Callable** yêu cầu kiểu executor phù hợp với AsyncTaskExecutor.
- **ThreadPoolTaskExecutor**: triển khai thông dụng quản lý pool, queue, các ngưỡng core/max và vòng đời Spring; có thể dùng ở nhiều điểm tích hợp cần TaskExecutor/AsyncTaskExecutor.
- **SimpleAsyncTaskExecutor**: chạy tác vụ trên thread mới, không phải pool thread tái sử dụng; có thể dùng virtual threads khi chạy trên JDK hỗ trợ và cấu hình đúng.
- **ConcurrentTaskExecutor**: adapter cho một java.util.concurrent.Executor khác, hữu ích khi hệ thống đã có executor tự quản lý.

Ví dụ lời gọi trực tiếp, trong một Spring bean đã được inject TaskExecutor:

~~~java
public void submit(TaskExecutor executor) {
    executor.execute(() ->
            System.out.println("Running on " +
                    Thread.currentThread().getName()));
}
~~~

Đoạn code này là **minh họa phương thức**, chưa phải chương trình độc lập. Khi executor là pool bất đồng bộ, phương thức submit thường trả về trước khi Runnable hoàn tất. Nếu executor từ chối task vì đã shutdown hoặc hết capacity, bên gửi phải xử lý **TaskRejectedException/RejectedExecutionException** phù hợp; không mặc định task chắc chắn được nhận.

**Sự phân tách cần ghi nhớ:** API TaskExecutor không tự định nghĩa thứ tự xử lý, độ bền công việc, retry, giao dịch, truyền ngữ cảnh bảo mật hay lịch kích hoạt. Những bảo đảm ấy phải đến từ thiết kế thành phần sử dụng và cấu hình liên quan.

## 3. Bảng ánh xạ TaskExecutor vào các thành phần Spring

| Thành phần | Khi nào gửi việc? | Vai trò của executor | Điểm cần kiểm soát |
| --- | --- | --- | --- |
| **@Async** | Bean khác gọi method qua async proxy | Thực thi thân method trên worker | Proxy/self-invocation, Future, exceptions, queue |
| **Spring MVC Callable/WebAsyncTask** | Controller trả về một Callable | Chạy tác vụ blocking trên AsyncTaskExecutor | Timeout, async dispatch, pool, request context |
| **DeferredResult / CompletableFuture trong MVC** | Kết quả được hoàn thành bởi phía ứng dụng | Executor chỉ tham gia khi ứng dụng thực sự dùng nó; MVC không tự submit mọi DeferredResult | Ai làm việc, ai hoàn thành, timeout/lỗi |
| **Application events** | ApplicationEventPublisher phát sự kiện | @Async trên listener hoặc TaskExecutor của event multicaster | Thứ tự, exception, transaction/context |
| **Spring Batch** | Step/Flow/partition cần thực thi song song | Cấp worker cho chiến lược parallelism đã chọn | Reader/writer thread safety, transaction, restart |
| **Spring Integration** | Message đi vào ExecutorChannel | Chuyển việc dispatch message sang worker | Ranh giới transaction, ordering, lỗi/rejection |
| **Spring WebSocket/message broker** | Message tới các channel inbound/outbound | Một số channel sử dụng executor để dispatch | Kích thước queue, ordering, backpressure |
| **TaskScheduler / @Scheduled** | Đến thời điểm trigger | Vai trò chính thuộc scheduler, không tự động dùng pool @Async | Tác vụ dài, chồng lấp, thread scheduler |
| **Spring WebFlux** | Dòng reactive được subscribe/chuyển Scheduler | Reactor Scheduler là abstraction khác; executor có thể được điều chỉnh để dùng ở chỗ phù hợp | Không chặn event-loop, tách blocking work |

Không phải tất cả các thành phần này tự động chọn **cùng một bean** có tên taskExecutor. Quy tắc lựa chọn phụ thuộc framework/module, phiên bản và cấu hình. Có thể dùng một pool chung cho những workload tương đồng; với HTTP, batch và tác vụ nặng có độ ưu tiên khác nhau, nên cân nhắc phân chia để tránh chúng làm nghẽn lẫn nhau.

## 4. @Async: TaskExecutor ở phía sau một lời gọi method

**@Async** là cơ chế Spring tiện lợi nhất để gửi công việc sang executor mà người gọi không phải tự tạo Runnable. Khi được bật bằng **@EnableAsync**, lời gọi method hợp lệ đi qua Spring proxy; proxy giao phần thực thi cho executor. Có thể chỉ định pool bằng qualifier:

~~~java
@Async("reportExecutor")
public CompletableFuture<String> buildReport(long reportId) {
    return CompletableFuture.completedFuture("report-" + reportId);
}
~~~

Khi method trên được gọi **từ bean khác qua proxy**, caller nhận Future để chờ, kiểm tra lỗi hoặc ghép pipeline nếu cần. Nếu method chỉ trả về void, lỗi trong quá trình thực thi không được truyền đồng bộ lại cho caller; cần logging hoặc **AsyncUncaughtExceptionHandler**. Với Future/CompletableFuture, xử lý completion và lỗi ở ranh giới phù hợp.

Quan trọng:

1. **@EnableAsync** phải có hiệu lực trong ApplicationContext; annotation một mình chưa tạo ra async proxy.
2. **Self-invocation** (this.buildReport(...)) thường không đi qua proxy trong chế độ proxy mặc định; method chạy như lời gọi Java thông thường.
3. **@Async("reportExecutor")** chọn rõ bean tương ứng; tránh phụ thuộc quy tắc tự chọn khi ứng dụng có nhiều executor.
4. **@Async không tự làm an toàn luồng.** Nhiều worker có thể cùng gọi một singleton có mutable fields.
5. **Không dùng Future.get()/join() ngay sau lời gọi** nếu mục tiêu là không chặn luồng gọi; đôi khi chờ là đúng nhưng phải là quyết định có chủ đích.
6. Async task thường **không kế thừa transaction hay ThreadLocal** của caller một cách tự động.

Tự gọi executor.execute(...) phù hợp khi chỉ cần một Runnable. Dùng @Async phù hợp khi muốn thể hiện ranh giới async ở mức service method và tận dụng proxy, qualifier, các kiểu Future. Không nên lạm dụng @Async cho logic CPU rất ngắn nếu overhead và tác động lên luồng xử lý lớn hơn lợi ích.

## 5. Spring MVC: giải phóng request thread trong lúc chờ việc

Spring MVC xử lý request trên Servlet stack. Một controller đồng bộ giữ request thread cho đến khi xử lý xong. Với **Callable<T>**, MVC có cơ chế Servlet asynchronous processing:

1. Controller nhận request rồi trả về Callable.
2. MVC bắt đầu async request, gửi Callable vào **AsyncTaskExecutor** được cấu hình cho MVC.
3. Servlet request thread ban đầu được giải phóng trong khi response còn mở.
4. Worker chạy Callable và trả kết quả/exception.
5. Container thực hiện async dispatch để MVC xử lý kết quả và hoàn tất response.

Ví dụ controller, **cần spring-webmvc và web runtime nên không thuộc chương trình độc lập ở mục 10**:

~~~java
@RestController
class ReportController {
    @GetMapping("/reports/current")
    public Callable<String> current() {
        return () -> {
            // Có thể truy cập backend blocking từ MVC async worker.
            return "ready: " + Thread.currentThread().getName();
        };
    }
}
~~~

MVC cho phép cấu hình AsyncTaskExecutor qua **WebMvcConfigurer.configureAsyncSupport(AsyncSupportConfigurer)**, hoặc dùng tích hợp auto-configuration của Spring Boot. Khi tự cấu hình Spring Boot 3.3, một điểm đặc biệt là bean **applicationTaskExecutor** cần tương thích AsyncTaskExecutor để MVC dùng trong cơ chế chọn mặc định. Một custom Executor bất kỳ chỉ tên taskExecutor có thể được @Async chọn nhưng **không bảo đảm MVC chọn cùng bean đó**.

**Callable khác DeferredResult.** Với DeferredResult, controller trả về một holder chưa có kết quả; chính ứng dụng, một callback I/O hoặc message handler khác phải gọi setResult/setErrorResult. MVC **không tự động gửi phần tính toán của mọi DeferredResult sang executor**. Với controller trả về CompletableFuture, nơi sản xuất future quyết định phần công việc chạy ở đâu. Vì thế việc controller "trả về kiểu async" không tự chứng minh một TaskExecutor cụ thể đã được dùng.

Bất đồng bộ MVC không có nghĩa ứng dụng xử lý vô hạn request. Cần đặt timeout, quan sát số request đang mở, không dùng pool vô hạn và quản lý kết nối/downstream. Việc chuyển blocking I/O sang worker giúp giải phóng Servlet thread chờ nhưng **không làm blocking I/O trở thành non-blocking**.

## 6. Application Events: listener chạy đồng bộ hoặc được đẩy sang executor

Với **ApplicationEventPublisher.publishEvent(...)**, Spring thường chuyển sự kiện tới listener **đồng bộ trên thread của publisher** theo mặc định. Spring có hai con đường chủ yếu để giao việc cho executor.

### Cách A — chỉ một listener cần chạy bất đồng bộ

~~~java
@Component
class NotificationListener {
    @Async("notificationExecutor")
    @EventListener
    public void onOrderCreated(OrderCreated event) {
        // Xử lý trên notificationExecutor.
    }
}
~~~

Đây là mã minh họa, giả định đã định nghĩa **OrderCreated**, bean notificationExecutor, @EnableAsync và các import cần thiết. Ứng dụng chỉ cần async ở listener này thì annotation thể hiện ý định khá rõ. **publishEvent() không chờ việc xử lý thực tế kết thúc** khi listener đã được dispatch thành công.

### Cách B — cấu hình multicaster để điều phối listener bằng TaskExecutor

Một bean tên **applicationEventMulticaster** có thể dùng SimpleApplicationEventMulticaster và gọi setTaskExecutor(...) để chuyển việc dispatch sang pool phù hợp. Ví dụ nằm trong class @Configuration (cần import các kiểu được dùng):

~~~java
@Bean(name = "applicationEventMulticaster")
ApplicationEventMulticaster eventMulticaster(
        @Qualifier("eventExecutor") TaskExecutor eventExecutor) {
    SimpleApplicationEventMulticaster multicaster =
            new SimpleApplicationEventMulticaster();
    multicaster.setTaskExecutor(eventExecutor);
    return multicaster;
}
~~~

Đây là cấu hình minh họa riêng, **không có trong bản demo độc lập**. Khi chọn hướng này, event dispatch có thể async cho các listener **hỗ trợ async execution**. Không suy ra mọi listener đều bị chuyển thread: ví dụ transactional listener có những ràng buộc phải giữ đồng bộ khi gắn với transaction. Không cần gắn cả @Async lẫn multicaster async nếu chúng tạo thêm tầng dispatch khó kiểm soát.

**Ranh giới transaction:** một listener chạy ở worker khác không có sẵn transaction đang mở hay các ThreadLocal của publisher. Nếu muốn xử lý sau commit, hãy cân nhắc **@TransactionalEventListener(phase = AFTER_COMMIT)**, sau đó thiết kế riêng ranh giới công việc nền và tính bền vững cần thiết. Event trong ApplicationContext là cơ chế nội bộ, **không phải message broker bền vững**; process crash sau khi trả lời publisher có thể làm mất task chỉ đang nằm trong memory.

**Xử lý lỗi:** exception của async listener không tự ném ngược về publisher. Cần logging, error handler, retry có kiểm soát hoặc cơ chế lưu trữ công việc nếu sự kiện có giá trị nghiệp vụ bắt buộc.

## 7. Spring Batch: cung cấp worker cho xử lý song song

Spring Batch sử dụng TaskExecutor như một **thành phần hạ tầng** khi cấu hình một chiến lược parallelism. Những kịch bản phổ biến:

- **Multi-threaded Step:** cấu hình taskExecutor trên Step để thực hiện đồng thời phần xử lý mà phiên bản Spring Batch hỗ trợ. Các reader/processor/writer và trạng thái chia sẻ phải được đánh giá thread-safety; hành vi chunk/transaction chi tiết phụ thuộc phiên bản.
- **Parallel Steps:** mỗi flow có thể chạy đồng thời khi cấu hình split flow với executor.
- **Partitioning:** chia workload thành nhiều StepExecution; một partition handler cục bộ có thể dùng TaskExecutor để thực thi các partition. Việc chọn grid size, tài nguyên và idempotency vẫn thuộc ứng dụng.

Ví dụ **phác thảo cấu hình Spring Batch 5.x**, cần thêm spring-batch-core, JobRepository, transaction manager, ItemReader/Processor/Writer nên không phải file Java độc lập:

~~~java
Step step = new StepBuilder("importStep", jobRepository)
        .<InputRow, OutputRow>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .taskExecutor(batchExecutor)
        .build();
~~~

**ThreadPoolTaskExecutor không làm cho reader/writer tự an toàn khi được truy cập đồng thời.** Nếu framework/version cho các thành phần chạy trên nhiều thread, cần xác nhận compatibility, kiểm tra thứ tự đầu ra, commit boundaries, restart/retry và vấn đề duplicate. Trong Batch, tăng concurrency có thể bị chặn bởi DataSource connection pool, I/O throughput hoặc lock ở database.

Phân biệt **TaskExecutor trong một JVM** với phân phối công việc qua nhiều process/worker: muốn phân phối từ xa phải dùng cơ chế messaging, partitioning hoặc remote execution tương ứng. Một ThreadPoolTaskExecutor đơn thuần không tạo được distributed job queue.

## 8. Spring Integration và các hệ thống messaging

Spring Integration cung cấp **ExecutorChannel** để điều phối message sang subscriber/handler bằng TaskExecutor. Ví dụ sử dụng spring-integration-core, là đoạn minh họa cần khai báo MessageChannel và các dependency:

~~~java
@Bean
MessageChannel processingChannel(
        @Qualifier("integrationExecutor") TaskExecutor executor) {
    return new ExecutorChannel(executor);
}
~~~

Khi message được gửi vào channel, việc gọi handler thường chuyển sang worker. So với **DirectChannel**, ExecutorChannel làm **đứt ranh giới thread của sender**, do đó không thể giả định handler dùng chung transaction/ThreadLocal với sender. Thao tác send thường có thể return trước khi handler chạy; tuy nhiên nếu executor dùng **CallerRunsPolicy** hay một chính sách backpressure đặc biệt, sender **có thể bị block hoặc tự chạy task**, nên không coi "channel async" là một bảo đảm tuyệt đối.

Khi nhiều message được xử lý đồng thời, **thứ tự hoàn tất** có thể khác thứ tự gửi. Nếu cần bảo đảm ordering theo key, idempotency hoặc retry, phải chọn message pattern và cơ chế tương ứng.

Các thành phần như Spring WebSocket message channels, JMS listener containers hay AMQP listener containers có thể dùng executor để quản lý thread hoặc dispatch tùy implementation. Nhưng nhiều listener container cũng có cấu hình **concurrency riêng** và lifecycle độc lập; **không được suy ra cứ định nghĩa một TaskExecutor trong context là tất cả listener tự chuyển sang pool ấy**.

Với hệ thống cần lưu message khi application restart, phân phối nhiều node hoặc bảo đảm delivery, một executor chạy trong process **không thay thế** queue/broker bền vững (Kafka, RabbitMQ, JMS broker, v.v.).

## 9. Quan hệ với TaskScheduler, @Scheduled và Reactor Scheduler

**TaskScheduler** giải quyết **thời điểm kích hoạt**, còn TaskExecutor giải quyết **cách thực thi công việc được giao**. Dù có class Spring thực thi nhiều interface và có thể dùng thread pool ở cả hai vai trò, hai abstraction vẫn tách biệt.

~~~text
@Scheduled mỗi 30 giây
       |
       v
TaskScheduler kích hoạt method ngắn
       |
       v
method gọi @Async qua một Spring bean khác
       |
       v
TaskExecutor nhận công việc nặng, có queue/capacity riêng
~~~

Method @Scheduled có thể chạy trực tiếp trên thread scheduler nếu nó không gửi việc sang nơi khác. Nếu method chỉ submit việc async rồi return, **fixedDelay** đo từ lúc method được scheduler gọi kết thúc, **không phải từ lúc async task hoàn tất**. Vì thế có thể có nhiều việc nền chồng lấp dù lịch trông giống chạy tuần tự. Cần thêm quy tắc chống trùng/chồng lấp nếu nghiệp vụ yêu cầu.

**Reactor Scheduler trong WebFlux** cũng không phải TaskExecutor. Reactor dùng Scheduler để quyết định execution context của reactive signal/operators. Có thể điều chỉnh để một reactive chain dùng executor thích hợp trong những trường hợp cụ thể, nhưng không nên coi việc thêm @Async vào service là giải pháp chung cho blocking code trong reactive pipeline. Cần đưa blocking work ra khỏi event-loop, dùng scheduler phù hợp và quản lý giới hạn concurrency.

## 10. Demo độc lập: một executor phục vụ execute(), @Async và @EventListener

Demo này dùng **Java 17+, Spring Framework 6.1.14, Gradle 8.5+**. Nó chứng minh bằng một ứng dụng command-line rằng ba đường vào khác nhau có thể gửi việc tới **cùng một ThreadPoolTaskExecutor**. Không cần Spring Boot, web server, Spring Batch hay Spring Integration để chạy.

Cấu trúc:

~~~text
executor-integrations-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/ExecutorIntegrationsDemo.java
~~~

Tệp **settings.gradle**:

~~~groovy
rootProject.name = 'executor-integrations-demo'
~~~

Tệp **build.gradle**:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.14'
}

application {
    mainClass = 'demo.ExecutorIntegrationsDemo'
}
~~~

Tệp **src/main/java/demo/ExecutorIntegrationsDemo.java**:

~~~java
package demo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class ExecutorIntegrationsDemo {

    public static void main(String[] args) throws Exception {
        try (var context =
                     new AnnotationConfigApplicationContext(DemoConfig.class)) {

            var executor = context.getBean(
                    "workerExecutor", ThreadPoolTaskExecutor.class);

            // Đường 1: submit Runnable trực tiếp qua TaskExecutor.
            var directDone = new CountDownLatch(1);
            executor.execute(directDone::countDown);
            System.out.println("execute completed: " +
                    directDone.await(5, TimeUnit.SECONDS));

            // Đường 2: @Async qua Spring proxy của một bean khác.
            var service = context.getBean(ReportService.class);
            var report = service.createReport(7)
                    .get(5, TimeUnit.SECONDS);
            System.out.println("async result: " + report.name());
            System.out.println("async pool: " +
                    report.threadName().startsWith("worker-"));

            // Đường 3: ApplicationEventPublisher + @Async listener.
            var listener = context.getBean(ReportListener.class);
            context.publishEvent(new ReportRequested(8));
            System.out.println("event completed: " +
                    listener.await(5, TimeUnit.SECONDS));
            System.out.println("event pool: " +
                    listener.wasOnWorkerThread());
        }
    }

    @Configuration
    @EnableAsync
    public static class DemoConfig {
        @Bean(name = "workerExecutor")
        public ThreadPoolTaskExecutor workerExecutor() {
            var executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(2);
            executor.setMaxPoolSize(2);
            executor.setQueueCapacity(10);
            executor.setThreadNamePrefix("worker-");
            return executor;
        }

        @Bean
        public ReportService reportService() {
            return new ReportService();
        }

        @Bean
        public ReportListener reportListener() {
            return new ReportListener();
        }
    }

    public record ReportRequested(int id) { }

    public record ReportResult(String name, String threadName) { }

    public static class ReportService {
        @Async("workerExecutor")
        public CompletableFuture<ReportResult> createReport(int id) {
            var result = new ReportResult(
                    "report-" + id,
                    Thread.currentThread().getName());
            return CompletableFuture.completedFuture(result);
        }
    }

    public static class ReportListener {
        private final CountDownLatch completed = new CountDownLatch(1);
        private volatile boolean onWorkerThread;

        @EventListener
        @Async("workerExecutor")
        public void handle(ReportRequested event) {
            onWorkerThread =
                    Thread.currentThread().getName().startsWith("worker-");
            completed.countDown();
        }

        public boolean await(long timeout, TimeUnit unit)
                throws InterruptedException {
            return completed.await(timeout, unit);
        }

        public boolean wasOnWorkerThread() {
            return onWorkerThread;
        }
    }
}
~~~

Chạy từ thư mục **executor-integrations-demo** bằng Gradle và JDK đã cài:

~~~bash
gradle run
~~~

Nếu dự án có wrapper, dùng **./gradlew run** (Linux/macOS) hoặc **gradlew.bat run** (Windows). Dưới điều kiện bình thường, khi cả ba task hoàn tất trước timeout 5 giây, phần output do chương trình in **đúng năm dòng**:

~~~text
execute completed: true
async result: report-7
async pool: true
event completed: true
event pool: true
~~~

Các log khởi động của Spring/Gradle có thể xuất hiện thêm; tên thread thật có hậu tố biến đổi (worker-1, worker-2, ...), vì vậy ví dụ in boolean kiểm tra prefix, không dựa vào thứ tự/tên thread bất biến. Nếu môi trường quá tải hoặc timeout, các giá trị/ngoại lệ có thể khác; đây là điều kiện vận hành cần xử lý chứ không phải chứng cứ executor luôn bảo đảm task chạy thành công.

Phân tích:

1. **execute(...)** gọi trực tiếp Runnable trên worker được ThreadPoolTaskExecutor quản lý.
2. **@Async("workerExecutor")** khiến lời gọi ReportService.createReport() qua proxy được gửi tới cùng pool; Future cho phép quan sát kết quả.
3. **@EventListener + @Async("workerExecutor")** chuyển phần xử lý sự kiện sang cùng pool trong khi multicaster mặc định vẫn giao lời gọi cho listener theo cơ chế publish của Spring.
4. CountDownLatch giúp main thread chờ kiểm tra kết quả đã hoàn thành và tạo quan hệ happens-before thích hợp cho dữ liệu được worker cập nhật. Trong ứng dụng production, cần thêm cơ chế timeout/rejection/error handling phù hợp.
5. Demo **không** chứng minh MVC, Spring Batch, Spring Integration tự dùng bean này. Những thành phần đó cần dependency và cấu hình riêng, như các mục trên đã giải thích.

## 11. Cấu hình và phân chia executor trong Spring Boot

Với **Spring Boot 3.3**, khi phù hợp điều kiện auto-configuration và chưa có custom Executor làm thay đổi lựa chọn, Boot thường tạo AsyncTaskExecutor cho các tích hợp, thông thường là **ThreadPoolTaskExecutor** nếu không bật virtual threads. Một số tích hợp như Spring MVC/WebFlux có quy ước tên bean **applicationTaskExecutor** và yêu cầu kiểu **AsyncTaskExecutor**. Quy tắc chọn với @EnableAsync và các thành phần khác có thể thay đổi khi có nhiều bean cùng kiểu.

**Nguyên tắc:** khi ứng dụng có nhiều pool, chọn pool **tường minh** ở mỗi điểm cần thiết. Không dựa vào việc bean đầu tiên có chữ "executor" trong tên sẽ được mọi thành phần dùng.

Với auto-configured ThreadPoolTaskExecutor/TaskScheduler, có thể cấu hình từ application.yml:

~~~yaml
spring:
  task:
    execution:
      thread-name-prefix: "app-work-"
      pool:
        core-size: 4
        max-size: 8
        queue-capacity: 100
    scheduling:
      thread-name-prefix: "scheduled-"
      pool:
        size: 2
~~~

Đây là mẫu cấu hình **của Spring Boot**, không có tác dụng lên project thuần Spring Framework ở mục 10. Những property này cũng **không tự ghi đè** thông số của một ThreadPoolTaskExecutor do bạn tự new và cấu hình thủ công; muốn dùng chung cách dựng, xem các builder mà Boot cung cấp.

Một cách tự tạo pool (ví dụ trong class @Configuration):

~~~java
@Bean("ioExecutor")
ThreadPoolTaskExecutor ioExecutor() {
    ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
    pool.setCorePoolSize(4);
    pool.setMaxPoolSize(8);
    pool.setQueueCapacity(100);
    pool.setThreadNamePrefix("io-");
    return pool;
}
~~~

Đoạn cấu hình chỉ minh họa; cần import ThreadPoolTaskExecutor, @Bean và áp dụng trong ApplicationContext. Pool này không tự thay thế executor cho MVC, Batch, Integration hoặc event multicaster nếu những thành phần ấy chưa được cấu hình dùng nó.

**Cân nhắc tách pool theo workload:** ví dụ pool nhỏ dành cho điều phối ứng dụng, pool hạn chế cho I/O nặng, executor khác cho xử lý CPU và scheduler riêng cho lịch. Chia quá nhiều pool cũng tốn tài nguyên; quyết định dựa trên lượng task đến, thời gian chạy, yêu cầu ưu tiên và số CPU/connection thực có.

## 12. Rủi ro xuyên suốt các tích hợp và cách vận hành

### 12.1. Queue, capacity và rejection

Với ThreadPoolTaskExecutor, cần hiểu tương tác giữa **corePoolSize, maxPoolSize, queueCapacity**. Trong mô hình queue có dung lượng, pool thường tăng đến core threads, sau đó enqueue và chỉ tăng trên core khi queue đầy. Vì vậy maxPoolSize cao không có nghĩa ứng dụng sẽ lập tức tạo tương ứng số thread.

Khi tốc độ sinh task lớn hơn throughput xử lý, queue có thể tăng, độ trễ lớn dần và cuối cùng executor từ chối công việc. Chính sách như CallerRunsPolicy có thể buộc caller xử lý task, giúp làm chậm phía gửi nhưng làm thay đổi tính chất bất đồng bộ của lời gọi. Với request HTTP, message channel hay event publication, cần xác định cụ thể phản ứng khi bị từ chối: trả mã lỗi, retry có giới hạn, backpressure hoặc đưa công việc vào durable queue.

### 12.2. Context và transaction

**ThreadLocal** thông thường không tự chuyển sang worker. Ví dụ MDC cho logging, SecurityContext và request attributes có thể thiếu hoặc không đúng ở thread mới. Spring có **TaskDecorator** giúp bao bọc Runnable để truyền các context phù hợp; Spring Security còn có các wrapper như **DelegatingSecurityContextAsyncTaskExecutor**. Truyền context cần đặt đúng thời điểm capture/restore/cleanup, tránh rò rỉ ngữ cảnh giữa task trên pool tái sử dụng.

**Transaction** của caller thường gắn với thread hiện tại; chuyển việc sang executor không có nghĩa nó tiếp tục dùng cùng transaction. Với Batch, Integration, Application Events và MVC Callable, phải quyết định rõ transaction bao quanh đơn vị công việc nào. Không dùng synchronized để thay transaction database, cũng không mặc định @Transactional trên caller phủ sang thread async.

### 12.3. An toàn luồng, hủy và shutdown

Một singleton Spring service có thể được gọi đồng thời bởi MVC, @Async, scheduled callback và message handlers. **TaskExecutor không làm các field của singleton tự an toàn luồng**. Ưu tiên stateless service; khi cần shared mutable state thì dùng immutable snapshots, atomic operations, concurrent collection hoặc locking thích hợp.

Khi ứng dụng shutdown, cần xử lý task đang chờ, task đang chạy, interrupt, retry và dữ liệu cần khôi phục. Hủy Future là một tín hiệu/cơ chế phối hợp, không bảo đảm mọi I/O dừng ngay. Vòng đời của pool quản lý bởi Spring phụ thuộc cách bean được tạo và cấu hình shutdown; không nên tự new pool trong method rồi quên đóng.

### 12.4. Đo đạc

Nên quan sát ít nhất: **active threads, pool size, queue depth, submitted/completed/rejected tasks, thời gian chờ trong queue, thời gian xử lý, timeout và lỗi**. Đo riêng từng executor khi có nhiều pool để phân biệt bottleneck từ MVC, event hay batch. Thread count lớn nhưng throughput không tăng có thể do I/O, pool kết nối, lock hoặc downstream, không phải lỗi cấu hình max thread đơn thuần.

## 13. Các sai lầm thường gặp

| Hiện tượng | Suy luận sai | Cách kiểm tra và sửa |
| --- | --- | --- |
| Có một bean TaskExecutor nhưng MVC Callable không chạy ở pool mong muốn | Mọi thành phần tự lấy bean này | Kiểm tra AsyncTaskExecutor, applicationTaskExecutor và WebMvcConfigurer |
| @Async không tạo luồng khác | Cứ gắn annotation là chạy nền | Kiểm tra @EnableAsync và lời gọi có qua Spring proxy |
| @Scheduled chậm làm nghẽn nhiều lịch | TaskExecutor cho @Async luôn xử lý scheduled method | Kiểm tra TaskScheduler, số scheduler threads và thời gian callback |
| Listener nhận event rồi handler vẫn chạy trên thread publish | @EventListener mặc định luôn async | Cần @Async trên listener hoặc cấu hình multicaster thích hợp |
| Gửi vào ExecutorChannel nhưng mất transaction cũ | Chuyển message không đổi ranh giới thread | Thiết kế transaction ở handler/worker và xử lý lỗi độc lập |
| Batch xử lý trùng/lỗi khi chạy song song | Executor tự làm reader/writer an toàn | Kiểm tra idempotency, state, thread-safety, restart, database |
| Thêm maxPoolSize nhưng latency vẫn tăng | Executor luôn dùng max thread ngay | Kiểm tra core, queue, thời gian task, saturation |
| Cùng một bean chạy tốt khi đơn luồng nhưng lỗi lúc tải cao | Singleton tự có synchronization | Kiểm tra shared mutable state, race, atomicity và contention |

## 14. Câu hỏi tự kiểm tra

1. Một service gắn @Async chạy bằng executor nào? **Theo cấu hình async, qualifier trên @Async và quy tắc chọn bean của phiên bản đang dùng; đặt @Async("tênBean") nếu cần kiểm soát rõ.**
2. MVC controller trả về Callable có tự dùng ThreadPoolTaskExecutor của một method @Async bất kỳ không? **Không chắc.** MVC dùng AsyncTaskExecutor theo cấu hình MVC/Boot riêng.
3. MVC controller trả về DeferredResult có tự được MVC submit phần nghiệp vụ sang worker không? **Không**; ứng dụng chịu trách nhiệm hoàn thành DeferredResult.
4. Một event listener mặc định có async không? **Không**; mặc định listener thường chạy đồng bộ. Có thể dùng @Async hoặc cấu hình multicaster.
5. Tăng concurrency của Spring Batch có bảo đảm xử lý nhanh và đúng hơn không? **Không**; còn phụ thuộc thread-safety, I/O, database, transaction và khả năng restart.
6. ExecutorChannel có tự duy trì transaction của sender sang handler không? **Không**, vì handler có thể chạy ở worker khác.
7. @Scheduled gọi worker @Async mất 30 giây rồi return ngay: lần fixedDelay sau chờ worker xong chứ? **Không**; fixedDelay gắn với thời điểm kết thúc method được scheduler kích hoạt.
8. TaskExecutor có phải durable queue cho công việc quan trọng qua restart không? **Không**; cần cơ chế lưu và khôi phục công việc riêng.

**Điểm cần nhớ:** TaskExecutor là cơ chế dùng chung để **cấp tài nguyên thực thi**, nhưng mỗi Spring component xác định thời điểm gửi task, cách chờ kết quả và ranh giới lỗi/transaction khác nhau. Nắm rõ ranh giới đó giúp chọn đúng pool, không nhầm async với scheduling, và tránh mất kiểm soát khi ứng dụng chịu tải.

### Tài liệu chính thức

- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — Async Requests in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html)
- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Boot 3.3 — Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html)
- [Spring Batch — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html)
- [Spring Integration — Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html)
