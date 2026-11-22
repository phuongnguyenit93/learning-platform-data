# Timeout, hủy tác vụ và dọn thread sau test trong Spring Boot

## 1. Bài toán: test PASS nhưng thread vẫn chạy

Trong Spring Boot, các chức năng `@Async`, `@Scheduled`, `TaskExecutor` và `TaskScheduler` giúp tách công việc khỏi thread gọi. Đây cũng là nguyên nhân thường gặp khiến integration tests bị treo, rò dữ liệu và phụ thuộc thứ tự chạy:

- Test gọi `Future.get(100, MILLISECONDS)` rồi nhận `TimeoutException` nhưng worker tiếp tục ghi database.
- Test gọi `Future.cancel(true)`, thấy `isCancelled()==true` rồi cho rằng task đã thoát.
- `CompletableFuture.cancel(true)` khiến completion stage bị hủy nhưng underlying worker không nhận interrupt.
- Scheduler chạy background trong lúc test khác thay fixture hoặc mock.
- Test tự tạo `ExecutorService`/`ThreadPoolTaskScheduler` mà không shutdown, khiến JVM không kết thúc.
- `@Async void` ném exception ở worker, test thread không thấy nên vẫn PASS.
- `@SpringBootTest @Transactional` bị hiểu lầm là sẽ rollback mọi side effect của async thread.
- `assertTimeoutPreemptively` chuyển body sang thread khác với thread mà Spring TestContext đã gắn transaction.

Cần phân biệt ba việc **không thể thay thế nhau**:

1. **Timeout:** giới hạn thời gian một caller chờ kết quả.
2. **Cancellation:** yêu cầu hủy một task, có thể là request ngắt worker đang chạy.
3. **Cleanup:** kiểm worker thật sự rời task body và các threads/resources thuộc sở hữu test được giải phóng.

**Không kết luận “timeout = cancel = task đã dừng”.**

### Sau bài này, bạn có thể

- Dùng `Future.get(timeout)`, `CompletableFuture.orTimeout` và JUnit `assertTimeout` có kiểm soát.
- Hiểu `cancel(false)`, `cancel(true)`, `isDone()`, `isCancelled()` và `InterruptedException`.
- Viết task phản hồi interruption, không rò resource khi test fail.
- Đồng bộ test bằng `CountDownLatch` thay `Thread.sleep`.
- Kiểm `@Async` qua Spring proxy và đúng thread pool.
- Ngăn `@Scheduled` chạy ngẫu nhiên trong test context, đồng thời vẫn kiểm nghiệp vụ.
- Hủy `ScheduledFuture` và shutdown scheduler test-owned.
- Dọn executor riêng của test bằng `shutdown`/`awaitTermination` và không phá Spring-managed executor bean.
- Phân biệt lifecycle, ThreadLocal transaction/security, HTTP/DB timeouts và virtual threads.
- Thiết kế suite lặp lại được, không phụ thuộc thời gian thật hoặc thứ tự test.

## 2. Bốn thực thể của một công việc bất đồng bộ

~~~text
JUnit test thread                      Worker thread
-----------------                     -------------------
submit(Callable) --------------------> ExecutorService
       |                                       |
       v                                       v
 Future<String>                          Callable.call()
       |                                       |
       +-- get(timeout) --> result?            +-- block / I/O / compute
       |          |                            |
       |          +--> TimeoutException        |
       |                    |                  |
       |                    +-- worker vẫn CÓ THỂ chạy
       |
       +-- cancel(true) ----------------> interrupt request
       |                                     |
       |                              task tự hợp tác để thoát
       |
       +-- latch.finished.await(timeout)
             |
             +-- xác minh worker đã qua finally
~~~

- `TaskExecutor`/`AsyncTaskExecutor` đại diện nơi chạy một task.
- `TaskScheduler` đăng ký thời điểm/chế độ chạy: one-shot, fixed rate, fixed delay, cron.
- `Future` là handle chờ kết quả/hủy; không phải bằng chứng thread đã chết.
- `ThreadPoolTaskExecutor` là Spring wrapper quanh worker pool và có Spring lifecycle.
- `ThreadPoolTaskScheduler` dùng scheduled executor, thường tự quản lý số threads và shutdown.
- `@Async`/`@Scheduled` cần annotation processing và context; gọi method trực tiếp không nhất thiết kích hoạt behavior framework.

### 2.1 Ma trận ngữ nghĩa

| Hành động | Tác dụng | Không được suy ra |
| --- | --- | --- |
| `Future.get(200, MILLISECONDS)` | Caller chờ tối đa 200ms | Task tự bị cancel sau 200ms |
| `Future.cancel(false)` | Cancel nếu được; không interrupt running task | Worker đang chạy đã thoát |
| `Future.cancel(true)` | Đề nghị interrupt worker đang chạy | Worker chắc chắn đã dừng |
| `CompletableFuture.cancel(true)` | Completion stage kết thúc với CancellationException | Physical computation bị interrupt |
| `ScheduledFuture.cancel(true)` | Cancel lịch, cố interrupt running task | Scheduler pool đã shutdown |
| `ExecutorService.shutdown()` | Không nhận task mới, thực thi các task đã submit | Đã chờ worker terminate |
| `ExecutorService.shutdownNow()` | Cố ngắt active tasks, trả tasks chưa chạy | Đã ép buộc mọi task thoát |
| `awaitTermination(timeout)` | Chờ sau khi đã shutdown | Tự gọi shutdown hộ |
| `@Async` return `CompletableFuture` | Caller nhận completion stage | Underlying future luôn interruptible |
| `@Scheduled` method invoked directly | Chạy method body | Cron trigger được kiểm |
| `assertTimeoutPreemptively` | Có giới hạn preemptive cho assertion | Không còn side effects ở thread khác |

## 3. Timeout: kết thúc chờ không có nghĩa kết thúc task

### 3.1 Future.get(timeout)

~~~java
Future<String> future = executor.submit(this::loadSlowly);

try {
    return future.get(300, TimeUnit.MILLISECONDS);
} catch (TimeoutException ex) {
    future.cancel(true);
    throw new IllegalStateException("Timed out", ex);
}
~~~

Đây là **fragment minh họa**, không phải file độc lập; cần `executor` và `loadSlowly`. `get(timeout)` chỉ ném khi kết quả chưa có sau thời hạn, **không tự cancel**. Việc gọi cancel là **chính sách riêng**, và `cancel(true)` chỉ đề nghị interrupt.

Không nên viết:

~~~java
assertThrows(TimeoutException.class,
        () -> future.get(100, TimeUnit.MILLISECONDS));
// Kết luận “worker đã dừng” là sai.
~~~

### 3.2 CompletableFuture.orTimeout và completeOnTimeout

Java 17:

~~~java
stage.orTimeout(200, TimeUnit.MILLISECONDS);
stage.completeOnTimeout("fallback", 200, TimeUnit.MILLISECONDS);
~~~

Hai thao tác có thể hoàn tất stage ở deadline (exception hoặc fallback). Nhưng một physical HTTP/DB/background computation bên dưới **có thể tiếp tục**. Nếu cần hủy physical task, phải giữ đúng cancellation handle ở layer thực thi và chọn I/O timeout/resource close riêng.

### 3.3 HTTP timeout, task timeout và deadline tổng

~~~text
Logical request deadline: 2s
    |
    +-- worker queue waiting
    +-- HTTP connect timeout: 1s
    +-- HTTP read timeout: 1s
    +-- retry backoff
    +-- DB commit or rollback
    +-- cleanup / compensation
~~~

Các durations cộng dồn có thể vượt deadline request. Spring `@Async` không tự set timeout HTTP, database statement hoặc transaction. Cần giới hạn từng resource đúng API, rồi theo dõi tổng latency.

### 3.4 JUnit assertTimeout và assertTimeoutPreemptively

~~~java
assertTimeout(Duration.ofSeconds(2),
        () -> service.compute());

assertTimeoutPreemptively(Duration.ofSeconds(2),
        () -> service.compute());
~~~

Đây là hai **mẫu minh họa**. `assertTimeout` thường chạy ở **caller thread**, đo thời gian nhưng không ép dừng một method block mãi. `assertTimeoutPreemptively` có thể chạy body ở **thread khác**. Spring TestContext cảnh báo điều này có thể phá test-managed transaction vốn bind theo test thread; database writes trong body có thể commit riêng rồi không rollback cùng test. SecurityContext/MDC/tenant ThreadLocal cũng có thể mất.

Đừng dùng preemptive test timeout thay cho deadline thực của HTTP/DB/worker.

## 4. Future.cancel(false), cancel(true) và cooperative interruption

JDK `Future.cancel(boolean mayInterruptIfRunning)`:

- Nếu task chưa chạy, cancellation có thể ngăn nó chạy.
- Nếu đang chạy, `cancel(false)` thường không interrupt worker; task có thể chạy đến kết thúc dù Future có trạng thái cancelled.
- `cancel(true)` đề nghị interrupt thread đang xử lý task nếu implementation biết worker.
- Worker có thể không phản hồi interrupt, ví dụ CPU loop không kiểm flag hoặc I/O driver không hỗ trợ ngắt.
- `Future.isDone()` có thể true vì completed, failed hoặc cancelled.
- `Future.get()` sau cancellation thường ném `CancellationException`, không trả về giá trị thực mà task có thể đã tính sau đó.

### 4.1 Task cần hợp tác

~~~java
try {
    releaseLatch.await();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return;
} finally {
    closeResources();
}
~~~

Đây là fragment cần `releaseLatch` và `closeResources` thật. Trong task CPU-bound, kiểm `Thread.currentThread().isInterrupted()` định kỳ. Với task chờ `CountDownLatch.await()`, interrupt gây `InterruptedException`, rất thuận lợi để test.

**Không dùng Thread.stop().** Hủy tác vụ phải được thiết kế sao cho task thoát an toàn, dọn lock/connection/streams trong finally và không để dữ liệu dang dở.

### 4.2 Tại sao chỉ kiểm isCancelled không đủ?

~~~text
Future.cancel(true) returned true
Future.isCancelled() == true
Future.isDone() == true

Nhưng task có thể còn:
- ghi database,
- gọi HTTP,
- giữ file lock,
- chờ I/O,
- chạy vòng lặp không kiểm interrupt.
~~~

Test cần một tín hiệu độc lập từ **cuối task body**, ví dụ `finished.countDown()` trong `finally`. Khi test sở hữu cả executor, xác minh thêm `awaitTermination`.

## 5. CompletableFuture cancellation khác FutureTask

Theo Java 17 Javadoc, `CompletableFuture.cancel(boolean)` tương đương exceptional completion; tham số `mayInterruptIfRunning` **không interrupt worker** trong implementation này.

~~~java
CompletableFuture<String> visible = new CompletableFuture<>();

Future<?> physical = executor.submit(() -> {
    String result = doBlockingWork();
    visible.complete(result);
});

visible.cancel(true);      // Không tự interrupt physical worker.
physical.cancel(true);     // Đây mới là cancellation attempt của task.
~~~

Đây là fragment. Đừng đánh đồng `CompletableFuture.cancel(true)` với `FutureTask.cancel(true)`. Với Spring `@Async`, proxy/executor wrapping có thể ảnh hưởng chi tiết cancellation; nên kiểm đúng version và API mà application đang sử dụng.

### 5.1 Cancelled result và running computation có thể cùng tồn tại

Ngay cả khi stage đã cancelled, worker có thể đi tới `visible.complete(value)`; lời gọi complete sẽ không thay đổi stage đã cancelled, nhưng **side effects** do worker thực hiện vẫn có thể xảy ra. Vì vậy:
- API trả fallback do timeout không bảo đảm database không còn commit.
- “Task canceled” không tương đương “task body đã vào finally”.
- Cần cancellation token/physical Future nếu muốn ngừng computation thật.

## 6. @Async trong Spring Boot

Cần `@EnableAsync`, Spring-managed bean và phương thức được gọi **qua proxy**. Annotation `@Async("workExecutor")` chỉ rõ pool.

~~~java
@Service
public class AsyncService {
    @Async("workExecutor")
    public CompletableFuture<String> compute() {
        return CompletableFuture.completedFuture(
                Thread.currentThread().getName());
    }
}
~~~

Đây là snippet; demo đầy đủ ở phần 11.

**Self-invocation:**

~~~java
public String outer() {
    return this.compute().join(); // Bypass proxy thông thường.
}
~~~

Nếu cùng bean tự gọi method `@Async`, proxy-based interception có thể bị bỏ qua; task chạy ở caller thread. Tách worker ra bean khác hoặc dùng programmatic executor.

### 6.1 @Async void exception

Một method:

~~~java
@Async("workExecutor")
public void send() {
    throw new IllegalStateException("send failed");
}
~~~

không có Future để caller `get()` exception. Spring có thể log exception hoặc gửi tới `AsyncUncaughtExceptionHandler`. Nếu bài test chỉ gọi `send()` rồi return, nó có thể PASS dù worker fail; hãy inject exception handler/test probe hoặc đổi contract sang Future/CompletableFuture để caller quan sát kết quả.

### 6.2 Boot auto-configured executor

Spring Boot 3.5 có thể auto-configure `AsyncTaskExecutor` hoặc dùng custom Executor beans. `@Async("workExecutor")` giúp chọn đúng pool khi có nhiều beans, tránh nhầm giữa executor của MVC async/GraphQL/WebFlux và jobs của ứng dụng. Không đoán bean default chỉ dựa vào tên method.

## 7. @Scheduled, fixedRate, fixedDelay và cron trong test

`@EnableScheduling` làm Spring đăng ký methods `@Scheduled` khi context khởi tạo. Nếu test không cô lập, job có thể chạy giữa assertions và sửa dữ liệu fixture.

| Kiểu | Ý nghĩa | Test nên làm |
| --- | --- | --- |
| `fixedRate` | Khoảng giữa các mốc bắt đầu, tùy scheduler | Test trigger riêng, không sleep tùy ý |
| `fixedDelay` | Khoảng sau khi lần trước hoàn thành | Tách business body ra service |
| `cron` | Theo biểu thức và timezone | Kiểm CronExpression/Trigger bằng clock |
| `schedule(task, Instant)` | Một lần ở thời điểm xác định | Hủy handle trước start khi cần |
| `scheduleAtFixedRate` | Gọi lặp, trả ScheduledFuture | Cancel và shutdown rõ |
| Quartz/distributed scheduling | Persistence/multi-node | Test lock/misfire/idempotency riêng |

### 7.1 Tắt cron một cách chủ đích trong ordinary tests

Spring `@Scheduled` nhận dấu `"-"` (`CRON_DISABLED`) để tắt cron:

~~~java
@Scheduled(cron = "${demo.maintenance.cron:-}")
public void runOnce() {
    // business logic
}
~~~

Với test property:

~~~properties
demo.maintenance.cron=-
~~~

Test không có trigger tự chạy. Production có thể set cron thực:

~~~properties
demo.maintenance.cron=0 0 3 * * *
~~~

Ở Spring property placeholder, default value của `demo.maintenance.cron` ở trên là dấu `-`. Không biến fixed-rate thành 1ms chỉ để kiểm bằng `Thread.sleep`.

### 7.2 Test body khác test scheduling wiring

- Gọi service method trực tiếp để kiểm logic.
- Kiểm cron/trigger bằng `CronExpression` và controlled `Clock`/`Instant` khi có business SLA về thời điểm.
- Test một scheduled handle bằng `TaskScheduler` local trong JUnit và hủy nó sau test.
- Nếu hệ thống có multiple app replicas, một `@Scheduled` được kích hoạt **trên mỗi instance**; cần distributed lock hoặc idempotency để tránh chạy cùng một job nhiều lần.

## 8. ThreadPoolTaskExecutor và lifecycle ownership

### 8.1 Spring-managed bean

~~~java
@Autowired
@Qualifier("workExecutor")
ThreadPoolTaskExecutor workExecutor;
~~~

Pool này có thể nằm trong **cached ApplicationContext** của Spring TestContext. Không gọi `workExecutor.shutdown()` trong `@AfterEach` để “dọn thread”: các class khác có thể dùng lại bean đã bị đóng và nhận `TaskRejectedException`.

**Cách đúng:** dọn/cancel/release **tasks của test**, đợi `finished`; để Spring đóng executor khi context thật sự kết thúc. Nếu cần kiểm shutdown lifecycle, tạo một executor **riêng do test sở hữu**.

### 8.2 Test-owned ExecutorService

~~~java
ExecutorService owned = Executors.newSingleThreadExecutor();
try {
    // tests and assertions
} finally {
    owned.shutdownNow();
    if (!owned.awaitTermination(3, TimeUnit.SECONDS)) {
        throw new AssertionError("Owned threads not terminated");
    }
}
~~~

Đây là fragment; có thể ném `InterruptedException` và cần handle phù hợp. `shutdownNow()` chỉ là best effort; kết quả `awaitTermination==false` là tín hiệu cleanup chưa hoàn tất.

### 8.3 Spring shutdown flags

| Option | Tác dụng |
| --- | --- |
| `setWaitForTasksToCompleteOnShutdown(false)` | Shutdown sớm, có thể interrupt active và bỏ queued tasks |
| `setWaitForTasksToCompleteOnShutdown(true)` | Cho existing/queued tasks chạy tới hoàn tất |
| `setAwaitTerminationSeconds(n)` | Đợi tối đa n giây khi Spring executor shutdown |
| `setStrictEarlyShutdown(true)` | Phát tín hiệu shutdown sớm khi context đóng |
| `setThreadNamePrefix(...)` | Dễ tìm threads trong logs/thread dump |
| `setCorePoolSize/setMaxPoolSize` | Điều chỉnh concurrency |
| `setQueueCapacity` | Giới hạn queue, tránh tài nguyên vô hạn |

Nếu set wait-for-completion=true mà có hung task, shutdown có thể kéo dài hoặc không kết thúc dù đã có timeout chờ. Cần cancellation/deadline ở tác vụ trước khi đóng.

## 9. ThreadPoolTaskScheduler lifecycle

`ThreadPoolTaskScheduler` có `schedule`, `scheduleAtFixedRate`, `scheduleWithFixedDelay` và `ScheduledFuture<?>` để cancel.

~~~java
ThreadPoolTaskScheduler scheduler =
        new ThreadPoolTaskScheduler();
scheduler.setPoolSize(1);
scheduler.setRemoveOnCancelPolicy(true);
scheduler.initialize();

try {
    ScheduledFuture<?> handle = scheduler.schedule(
            () -> perform(),
            Instant.now().plus(Duration.ofHours(1)));
    handle.cancel(false);
} finally {
    scheduler.shutdown();
    scheduler.getScheduledThreadPoolExecutor()
            .awaitTermination(3, TimeUnit.SECONDS);
}
~~~

Đây là fragment (cần `perform`). `setRemoveOnCancelPolicy(true)` giúp loại canceled delayed tasks khỏi queue nhanh hơn; **không** đồng nghĩa nó ngắt worker đang chạy. Hủy một `ScheduledFuture` chỉ hủy **lịch/tác vụ tương ứng**, không đóng scheduler.

Với `ThreadPoolTaskScheduler` Spring-managed bean, cũng không shutdown trong ordinary @AfterEach vì context có thể còn dùng nó.

## 10. Dự án Java 17+ / Spring Boot 3.5.x

Bộ thực hành không cần database, external API, Docker hoặc đồng hồ chờ cron. Có **12 phương thức JUnit Jupiter** ở ba test classes:

1. `AsyncIntegrationTest`: Spring @Async, Future timeout/cancel, CompletableFuture cancel, cron disabled.
2. `TaskSchedulerCancellationTest`: cancel delayed/periodic jobs, xác minh scheduler terminated.
3. `OwnedExecutorLifecycleTest`: graceful shutdown và interrupting shutdown.

Cấu trúc:

~~~text
async-test-demo/
  settings.gradle
  build.gradle
  src/main/java/example/async/
    AsyncDemoApplication.java
    ExecutorConfig.java
    AsyncWorker.java
    ScheduledMaintenance.java
  src/test/java/example/async/
    BlockingJob.java
    AsyncIntegrationTest.java
    TaskSchedulerCancellationTest.java
    OwnedExecutorLifecycleTest.java
  src/test/resources/
    application.properties
~~~

### 10.1 settings.gradle

~~~groovy
rootProject.name = 'async-test-demo'
~~~

### 10.2 build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Đây là Gradle config cho ví dụ, không tuyên bố các version trên là mới nhất. Test framework dựa trên Java 17+, Boot 3.5.x. Nếu máy chưa có Gradle wrapper, cần tạo wrapper hoặc dùng Gradle tương thích.

### 10.3 src/test/resources/application.properties

~~~properties
demo.maintenance.cron=-
logging.level.org.springframework.scheduling=INFO
~~~

## 11. Production: AsyncDemoApplication.java

~~~java
package example.async;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableAsync
@EnableScheduling
public class AsyncDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AsyncDemoApplication.class, args);
    }
}
~~~

`@EnableAsync` cho async proxy; `@EnableScheduling` đăng ký lịch khi có @Scheduled. Test đặt cron '-' nên không có background cron.

## 12. Production: ExecutorConfig.java

~~~java
package example.async;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

@Configuration
public class ExecutorConfig {

    @Bean("workExecutor")
    ThreadPoolTaskExecutor workExecutor() {
        ThreadPoolTaskExecutor pool =
                new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(2);
        pool.setQueueCapacity(8);
        pool.setThreadNamePrefix("demo-work-");
        pool.setWaitForTasksToCompleteOnShutdown(false);
        pool.setAwaitTerminationSeconds(3);
        pool.setStrictEarlyShutdown(true);
        return pool;
    }

    @Bean("taskScheduler")
    ThreadPoolTaskScheduler taskScheduler() {
        ThreadPoolTaskScheduler scheduler =
                new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(1);
        scheduler.setThreadNamePrefix("demo-sched-");
        scheduler.setRemoveOnCancelPolicy(true);
        scheduler.setWaitForTasksToCompleteOnShutdown(false);
        scheduler.setAwaitTerminationSeconds(3);
        return scheduler;
    }
}
~~~

Spring tự initialize và destroy các bean executors/scheduler. Test không gọi `initialize()` thủ công trên những Spring beans này. Pool sizes là giá trị demo; production cần bounded concurrency và rejection/queue policy phù hợp.

## 13. Production: AsyncWorker.java

~~~java
package example.async;

import java.util.Locale;
import java.util.concurrent.CompletableFuture;

import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class AsyncWorker {

    @Async("workExecutor")
    public CompletableFuture<String> upper(String input) {
        String value = Thread.currentThread().getName()
                + ":" + input.toUpperCase(Locale.ROOT);
        return CompletableFuture.completedFuture(value);
    }

    @Async("workExecutor")
    public CompletableFuture<String> fail() {
        throw new IllegalStateException("worker failed");
    }
}
~~~

Method được gọi qua Spring-injected bean để @Async advice thật sự chạy. `fail()` ném exception trong worker; caller nhận qua completion stage.

## 14. Production: ScheduledMaintenance.java

~~~java
package example.async;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class ScheduledMaintenance {

    private final AtomicInteger runs = new AtomicInteger();

    @Scheduled(cron = "${demo.maintenance.cron:-}")
    public void runOnce() {
        runs.incrementAndGet();
    }

    public int count() {
        return runs.get();
    }
}
~~~

Property placeholder của Spring trong annotation trên có default dấu '-' (cron disabled). Counter chỉ giúp test quan sát; production nên tách business logic sang service có idempotency nếu nhiều app instances có thể chạy schedule.

## 15. Test support: BlockingJob.java

~~~java
package example.async;

import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;

final class BlockingJob implements Callable<String> {

    final CountDownLatch started = new CountDownLatch(1);
    final CountDownLatch release = new CountDownLatch(1);
    final CountDownLatch finished = new CountDownLatch(1);
    final AtomicBoolean interrupted = new AtomicBoolean(false);

    @Override
    public String call() {
        started.countDown();

        try {
            release.await();
            return "released";
        } catch (InterruptedException ex) {
            interrupted.set(true);
            Thread.currentThread().interrupt();
            return "interrupted";
        } finally {
            finished.countDown();
        }
    }
}
~~~

Ba latches có nhiệm vụ tách biệt:

- `started` xác nhận task thực sự chạy trước khi test cancel.
- `release` cho phép test chủ động kết thúc chờ.
- `finished` xác nhận task body đi qua `finally`.

Không dùng sleep để đoán thời điểm worker start. `AtomicBoolean interrupted` cho phép test chứng minh interrupt đã được quan sát, thay vì chỉ kiểm Future state.

## 16. AsyncIntegrationTest.java: 7 tests

File `src/test/java/example/async/AsyncIntegrationTest.java`:

~~~java
package example.async;

import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(properties = "demo.maintenance.cron=-")
class AsyncIntegrationTest {

    @Autowired AsyncWorker asyncWorker;
    @Autowired ScheduledMaintenance maintenance;

    @Autowired
    @Qualifier("workExecutor")
    ThreadPoolTaskExecutor executor;

    @Test
    void asyncUsesConfiguredWorker() throws Exception {
        String result = asyncWorker.upper("hello")
                .get(2, TimeUnit.SECONDS);

        assertTrue(result.startsWith("demo-work-"));
        assertTrue(result.endsWith(":HELLO"));
    }

    @Test
    void asyncErrorReachesFuture() throws Exception {
        CompletableFuture<String> future = asyncWorker.fail();

        ExecutionException error = assertThrows(
                ExecutionException.class,
                () -> future.get(2, TimeUnit.SECONDS));

        assertInstanceOf(IllegalStateException.class,
                error.getCause());
        assertEquals("worker failed",
                error.getCause().getMessage());
    }

    @Test
    void timedOutGetDoesNotCancelTask() throws Exception {
        BlockingJob job = new BlockingJob();
        Future<String> future = executor.submit(job);

        try {
            assertTrue(job.started.await(2, TimeUnit.SECONDS));
            assertThrows(TimeoutException.class,
                    () -> future.get(100, TimeUnit.MILLISECONDS));
            assertFalse(future.isDone());
            assertFalse(job.interrupted.get());
        } finally {
            job.release.countDown();
        }

        assertTrue(job.finished.await(2, TimeUnit.SECONDS));
        assertEquals("released", future.get(2, TimeUnit.SECONDS));
    }

    @Test
    void cancelTrueInterruptsResponsiveJob() throws Exception {
        BlockingJob job = new BlockingJob();
        Future<String> future = executor.submit(job);

        try {
            assertTrue(job.started.await(2, TimeUnit.SECONDS));
            assertTrue(future.cancel(true));
            assertTrue(future.isCancelled());
            assertTrue(job.finished.await(2, TimeUnit.SECONDS));
            assertTrue(job.interrupted.get());
            assertThrows(CancellationException.class, future::get);
        } finally {
            job.release.countDown();
            future.cancel(true);
        }
    }

    @Test
    void cancelFalseDoesNotInterruptRunningJob()
            throws Exception {

        BlockingJob job = new BlockingJob();
        Future<String> future = executor.submit(job);

        try {
            assertTrue(job.started.await(2, TimeUnit.SECONDS));
            assertTrue(future.cancel(false));
            assertTrue(future.isCancelled());
            assertFalse(job.interrupted.get());
            assertEquals(1L, job.finished.getCount());
        } finally {
            job.release.countDown();
        }

        assertTrue(job.finished.await(2, TimeUnit.SECONDS));
        assertFalse(job.interrupted.get());
        assertThrows(CancellationException.class, future::get);
    }

    @Test
    void completableFutureCancelDoesNotInterruptWorker()
            throws Exception {

        BlockingJob job = new BlockingJob();
        CompletableFuture<String> visible =
                new CompletableFuture<>();

        Future<?> physical = executor.submit(
                () -> visible.complete(job.call()));

        try {
            assertTrue(job.started.await(2, TimeUnit.SECONDS));
            assertTrue(visible.cancel(true));
            assertTrue(visible.isCancelled());
            assertFalse(job.interrupted.get());
            assertEquals(1L, job.finished.getCount());
        } finally {
            job.release.countDown();
        }

        assertTrue(job.finished.await(2, TimeUnit.SECONDS));
        physical.get(2, TimeUnit.SECONDS);
        assertFalse(job.interrupted.get());
        assertTrue(visible.isCancelled());
    }

    @Test
    void cronDisabledInTestContext() {
        assertEquals(0, maintenance.count());
        maintenance.runOnce();
        assertEquals(1, maintenance.count());
    }
}
~~~

**7 @Test methods**. Không có test nào shutdown Spring-managed `executor`. Mỗi test tự release/cancel tasks do chính nó tạo ra.

**Timeout test:** `get(100ms)` ném TimeoutException nhưng task vẫn chờ. Sau release, worker hoàn thành và Future trả `released`.

**Cancel true:** sau started signal, cancel(true) làm worker chờ latch nhận interrupt; test đợi finished và kiểm interrupted=true.

**Cancel false:** Future canceled, nhưng job vẫn chờ latch và không bị interrupt; sau release body kết thúc bình thường, còn Future đã canceled không trả value.

**CompletableFuture:** cancel visible stage không interrupt physical worker; test vẫn phải release và đợi physical Future.

## 17. TaskSchedulerCancellationTest.java: 3 tests

File `src/test/java/example/async/TaskSchedulerCancellationTest.java`:

~~~java
package example.async;

import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class TaskSchedulerCancellationTest {

    private ThreadPoolTaskScheduler scheduler;

    @BeforeEach
    void openOwnedScheduler() {
        scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(1);
        scheduler.setThreadNamePrefix("test-scheduler-");
        scheduler.setRemoveOnCancelPolicy(true);
        scheduler.initialize();
    }

    @AfterEach
    void closeOwnedScheduler() throws Exception {
        scheduler.shutdown();
        assertTrue(scheduler.getScheduledThreadPoolExecutor()
                .awaitTermination(3, TimeUnit.SECONDS));
    }

    @Test
    void cancelDelayedTaskBeforeStart() {
        AtomicInteger calls = new AtomicInteger();

        ScheduledFuture<?> handle = scheduler.schedule(
                () -> calls.incrementAndGet(),
                Instant.now().plus(Duration.ofDays(1)));

        assertNotNull(handle);
        assertTrue(handle.cancel(false));
        assertTrue(handle.isCancelled());
        assertEquals(0, calls.get());
    }

    @Test
    void interruptRunningPeriodicTask() throws Exception {
        BlockingJob job = new BlockingJob();
        AtomicInteger runs = new AtomicInteger();

        ScheduledFuture<?> handle =
                scheduler.scheduleAtFixedRate(
                    () -> {
                        runs.incrementAndGet();
                        job.call();
                    },
                    Duration.ofMillis(20));

        try {
            assertTrue(job.started.await(2, TimeUnit.SECONDS));
            assertTrue(handle.cancel(true));
            assertTrue(job.finished.await(2, TimeUnit.SECONDS));
            assertTrue(job.interrupted.get());
            assertEquals(1, runs.get());
        } finally {
            job.release.countDown();
            handle.cancel(true);
        }
    }

    @Test
    void cancelHandleDoesNotDestroyScheduler()
            throws Exception {

        ScheduledFuture<?> first = scheduler.schedule(
                () -> {},
                Instant.now().plus(Duration.ofDays(1)));

        assertNotNull(first);
        assertTrue(first.cancel(false));

        CountDownLatch ran = new CountDownLatch(1);
        ScheduledFuture<?> second = scheduler.schedule(
                ran::countDown, Instant.now());

        assertNotNull(second);
        assertTrue(ran.await(2, TimeUnit.SECONDS));
        second.get(2, TimeUnit.SECONDS);
    }
}
~~~

**3 tests**. Mỗi method tạo một scheduler mới. `@AfterEach` đóng và kiểm `awaitTermination` để không rò threads sang test khác. Task periodic bị chặn trong lần chạy thứ nhất nên test có thể cancel mà không cần ngủ nhiều chu kỳ.

`ScheduledFuture.cancel` hủy một registration, **không** đóng pool; test thứ ba chứng minh scheduler có thể tiếp tục nhận task khác.

## 18. OwnedExecutorLifecycleTest.java: 2 tests

File `src/test/java/example/async/OwnedExecutorLifecycleTest.java`:

~~~java
package example.async;

import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class OwnedExecutorLifecycleTest {

    private static ThreadPoolTaskExecutor owned(
            boolean graceful) {

        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setQueueCapacity(2);
        executor.setThreadNamePrefix("owned-test-");
        executor.setWaitForTasksToCompleteOnShutdown(graceful);
        executor.setAwaitTerminationSeconds(3);
        executor.initialize();
        return executor;
    }

    @Test
    void gracefulShutdownDrainsQueue() throws Exception {
        ThreadPoolTaskExecutor executor = owned(true);
        BlockingJob job = new BlockingJob();
        AtomicInteger queuedRuns = new AtomicInteger();

        try {
            Future<String> first = executor.submit(job);
            assertTrue(job.started.await(2, TimeUnit.SECONDS));

            Future<Integer> second =
                    executor.submit(queuedRuns::incrementAndGet);

            job.release.countDown();
            executor.shutdown();

            assertEquals("released",
                    first.get(2, TimeUnit.SECONDS));
            assertEquals(1,
                    second.get(2, TimeUnit.SECONDS));
            assertEquals(1, queuedRuns.get());
            assertTrue(executor.getThreadPoolExecutor()
                    .awaitTermination(3, TimeUnit.SECONDS));
        } finally {
            job.release.countDown();
            executor.shutdown();
        }
    }

    @Test
    void interruptingShutdownEndsResponsiveJob()
            throws Exception {

        ThreadPoolTaskExecutor executor = owned(false);
        BlockingJob job = new BlockingJob();

        try {
            executor.submit(job);
            assertTrue(job.started.await(2, TimeUnit.SECONDS));
            executor.shutdown();

            assertTrue(job.finished.await(2, TimeUnit.SECONDS));
            assertTrue(job.interrupted.get());
            assertTrue(executor.getThreadPoolExecutor()
                    .awaitTermination(3, TimeUnit.SECONDS));
        } finally {
            job.release.countDown();
            executor.shutdown();
        }
    }
}
~~~

**2 tests**. Graceful shutdown với `waitForTasksToCompleteOnShutdown=true` cho phép task đang chạy và task queued hoàn tất. Interrupting shutdown với false yêu cầu ngắt job đang đợi latch; test kiểm interruption và underlying pool terminated.

Đây là pool **do từng test tạo** chứ không phải Spring-managed shared bean, nên `shutdown()` là đúng ownership.

## 19. Tổng hợp 12 JUnit Jupiter tests

| Test class | Số methods | Tình huống |
| --- | ---: | --- |
| `AsyncIntegrationTest` | 7 | @Async proxy, Future timeout, cancel true/false, CompletableFuture, cron disable |
| `TaskSchedulerCancellationTest` | 3 | Hủy delayed/periodic schedule, shutdown scheduler |
| `OwnedExecutorLifecycleTest` | 2 | Graceful vs interrupting executor shutdown |
| **Tổng** | **12** | Không sleep, không external resources |

Trong project có Gradle wrapper:

~~~bash
./gradlew test --tests example.async.AsyncIntegrationTest --tests example.async.TaskSchedulerCancellationTest --tests example.async.OwnedExecutorLifecycleTest
~~~

Windows:

~~~powershell
.\gradlew.bat test --tests example.async.AsyncIntegrationTest --tests example.async.TaskSchedulerCancellationTest --tests example.async.OwnedExecutorLifecycleTest
~~~

**Kết quả dự kiến theo thiết kế:** 12 tests PASS trên Java 17+/Spring Boot 3.5.x với code/dependencies/file paths trên. Đây **không** phải stdout ghi từ một lần Gradle build thực tế. Thời gian chờ 2–3 giây trong tests là upper bound khi lỗi, không phải lời hứa về thời lượng suite.

### Nếu test bị treo

1. Xem `Thread.dump` hoặc `jstack` xem worker đang chờ gì.
2. Kiểm tất cả latches có release ở finally.
3. Kiểm task có bắt InterruptedException rồi tiếp tục loop hay không.
4. Kiểm executor bean có bị shutdown bởi test class trước không.
5. Kiểm task còn ở queue vì pool saturation.
6. Kiểm cron schedule không vô tình bật ở test context.
7. Kiểm `@Async` chạy qua Spring proxy, không self-invocation.
8. Kiểm HTTP/DB driver có timeout thực, không chỉ Future timeout.
9. Kiểm test-created executor/scheduler đã shutdown và await termination.
10. Kiểm thread name prefix để xác định đúng owner thay vì JVM-wide Thread.activeCount.

## 20. Thread pool saturation và rejection

`ThreadPoolTaskExecutor` thông thường:

~~~text
corePoolSize=2
maxPoolSize=4
queueCapacity=3

tasks 1-2       -> 2 worker threads
tasks 3-5       -> queued
tasks 6-7       -> có thể mở rộng tới 4 worker threads
task tiếp theo  -> bị reject nếu cả threads và queue đều đầy
~~~

Đây là sơ đồ khái niệm khi tasks đang block và queue chưa drain. Nếu queue unbounded, pool có thể **không bao giờ** tăng lên max size do queue luôn nhận task trước.

Để test rejection, submit một task chờ latch cho worker bận, rồi lấp queue, assert `TaskRejectedException`/configured handler. **Đừng** để task đầu chờ vô hạn sau assertion failure; cleanup trong finally.

`CallerRunsPolicy` có thể khiến task chạy trên **caller thread** khi pool quá tải, vì vậy các assumptions “đây là async” cần kiểm đúng rejection handler.

## 21. Transaction, SecurityContext và MDC trong async threads

### 21.1 Spring TestContext transaction không theo @Async

Spring TestContext thường bind transaction vào **JUnit test thread**. `@Async`/`@Scheduled` chạy thread khác nên JDBC transaction của test không tự đi theo. Nếu worker mở transaction riêng/auto-commit, dữ liệu có thể tồn tại **sau khi test rollback**.

Cần committed cleanup hoặc isolated test database, không trông cậy `@Rollback` để dọn mọi background writes.

### 21.2 SecurityContext không tự theo worker

`SecurityContextHolder` mặc định gắn với thread. Worker mới không tự có security identity của JUnit, và MDC/tenant ThreadLocal cũng không tự truyền. Khi business cần, dùng `DelegatingSecurityContextAsyncTaskExecutor`, `TaskDecorator` hoặc context propagation phù hợp, có **finally clear** để tránh rò identity giữa tasks của pool.

### 21.3 EntityManager không thread-safe

Không chia sẻ cùng persistence context/EntityManager/JDBC Connection sang worker. Service ở worker thread nên mở transaction đúng của nó qua Spring proxy khi cần. Không dùng shared mutable DB session để “giữ transaction test” qua thread khác.

## 22. Cron, fixed delay và cluster consistency

- `fixedRate`: kiểm schedule semantics riêng nếu cần cadence chính xác.
- `fixedDelay`: khoảng chờ sau completion; phù hợp tránh overlap của một scheduled registration.
- `cron`: cần timezone khi lịch gắn với giờ địa phương/DST.
- Nhiều `@Scheduled` trên cùng method có thể đăng ký nhiều triggers.
- Chạy Spring Boot trên nhiều replicas thường làm **mỗi instance** có scheduler riêng.
- Các job có side effects cần idempotency, distributed locking hoặc persistent scheduler nếu yêu cầu một lần toàn cluster.

Không dùng một JUnit test chạy một ApplicationContext để kết luận “job chỉ chạy một lần trên toàn hệ thống phân tán”.

## 23. Cleanup matrix

| Resource | Owner | Cleanup |
| --- | --- | --- |
| Future từ task test submit | Test | cancel/release, đợi finished latch |
| CompletableFuture completion stage | Caller | cancel stage; physical task xử lý riêng |
| ExecutorService tạo trong test | Test | shutdown/shutdownNow + awaitTermination |
| ThreadPoolTaskExecutor Spring bean | ApplicationContext | test dọn riêng tasks; Spring đóng khi context close |
| ThreadPoolTaskScheduler test-owned | Test | cancel ScheduledFuture, shutdown, await |
| @Scheduled registration | Spring context | cron disabled trong ordinary tests, close context khi sở hữu |
| DB writes từ worker | Database/application transaction | Dedicated test DB, cleanup committed rows |
| HTTP call | HTTP client | timeout per resource, cancel/close response |
| Message consumer | Container/broker | stop listener, unsubscribe/offset cleanup |
| File temp | Test | @TempDir/try-finally |
| Reactive subscription | Subscriber | dispose/cancel và verify terminal state |
| Quartz/distributed job | Scheduler persistence | unschedule và cleanup locks/fixtures |

**Không dùng `@DirtiesContext` như lựa chọn mặc định để dọn mọi executor**: context rebuild tốn thời gian và không tự xóa database committed side effects. Chỉ dùng khi test thật sự cần phá/khởi động lại Spring context và lifecycle.

## 24. Lỗi phổ biến

**1. TimeoutException nghĩa task đã bị cancel.**  
Sai: `get(timeout)` không tự cancel.

**2. Future.isDone() nghĩa worker đã thoát.**  
Sai: canceled future cũng done.

**3. CompletableFuture.cancel(true) interrupt worker.**  
Sai với Java 17 implementation; cần physical task handle.

**4. Future.cancel(false) dừng task đang chạy.**  
Không yêu cầu interrupt; task có thể tiếp tục.

**5. Future.cancel(true) chắc chắn ngắt mọi I/O.**  
Interrupt là best effort; resource-specific cancellation cần thiết.

**6. Catch InterruptedException rồi nuốt và tiếp tục loop.**  
Làm pool khó shutdown; exit hoặc propagate appropriately.

**7. Không release latch trong finally.**  
Assertion fail làm worker kẹt vĩnh viễn.

**8. Dùng Thread.sleep để chờ @Async.**  
Flaky trên CI; dùng CountDownLatch và bounded get.

**9. @Async void exception khiến test vẫn PASS.**  
Có handler hoặc Future-based contract để quan sát.

**10. Self-invocation @Async không qua proxy.**  
Tách bean hoặc gọi qua Spring-managed proxy.

**11. Test shutdown @Autowired executor dùng chung.**  
Cached context hỏng, test sau bị rejected.

**12. Scheduler không bị hủy sau test.**  
Periodic job tiếp tục chạy, data race/leak.

**13. @Scheduled chạy lúc SpringBootTest startup.**  
Disable cron hoặc cô lập scheduling configuration.

**14. Test cron bằng sleep tới đúng mốc thời gian.**  
Chậm/flaky; dùng CronExpression/Clock hoặc fake scheduler.

**15. waitForTasksToCompleteOnShutdown=true với hung task.**  
Shutdown có thể chờ quá lâu; cần deadlines và interrupt responsiveness.

**16. awaitTermination trả false bị bỏ qua.**  
Resource leak không được báo; test nên FAIL.

**17. assertTimeoutPreemptively trong @Transactional test.**  
Thread boundary có thể làm DB writes không rollback với test.

**18. Truyền EntityManager/SecurityContext ThreadLocal sang executor mà không có cơ chế propagation.**  
Có thể sai thread context hoặc leak identity.

**19. HTTP Future timeout nhưng request vẫn chạy.**  
Cần HTTP client transport timeout/cancel thực.

**20. Queue unbounded nên maxPoolSize không tăng.**  
Cấu hình queue bounded theo nhu cầu và test rejection.

**21. Test activeCount==0 ngay sau Future completion.**  
Snapshot pool không phải synchronization barrier; dùng latches và awaitTermination.

**22. Multi-instance scheduler bị coi là một lần toàn cluster.**  
Cần distributed coordination/idempotency.

## 25. Checklist trước khi chốt bài kiểm thử

1. Nêu rõ caller timeout, worker cancellation và pool cleanup là ba concerns.
2. Mọi `Future.get`/`await` trong test cần bounded timeout.
3. Có `finally` release resources ngay cả khi assertions fail.
4. Có tín hiệu worker finished, không chỉ isDone/isCancelled.
5. Task có hợp tác với interrupt và dọn connection/file/lock.
6. CompletableFuture cancellation được kiểm theo implementation thực.
7. @Async được gọi qua bean/proxy và đúng executor qualifier.
8. Tránh @Async void không có error observer.
9. @Scheduled không chạy ngẫu nhiên trong ordinary SpringBootTest.
10. Test business logic tách khỏi trigger registration tests.
11. Test-owned pool/scheduler luôn shutdown và await termination.
12. Không shutdown Spring-managed executors trong cached test context.
13. Có timeout riêng ở HTTP/DB và overall deadline.
14. Async/scheduled DB writes có cleanup committed state.
15. Test bảo mật/transaction không dựa vào ThreadLocal tự truyền sang worker.
16. Có idempotency/distributed lock nếu scheduled job chạy ở nhiều instances.
17. Test queue saturation/rejection nếu đây là yêu cầu quan trọng.
18. Chạy lại suite, quan sát thread dumps khi nghi leak.

### Checklist cuối

- [ ] Không nhầm timeout với cancellation.
- [ ] Future.cancel(true) chỉ là interrupt request.
- [ ] CompletableFuture.cancel(true) không mặc định interrupt.
- [ ] Test dùng latch, không sleep tùy ý.
- [ ] Có bằng chứng worker body đã kết thúc.
- [ ] Task tạo trong test có finally cleanup.
- [ ] Scheduler registrations được cancel.
- [ ] Owned executors có shutdown + awaitTermination.
- [ ] Spring-managed executor không bị đóng sớm.
- [ ] @Scheduled được disable/cô lập khi không kiểm trigger.
- [ ] @Async exception được quan sát.
- [ ] Thread-bound transaction/security context được hiểu đúng.

## 26. Kết luận

**Timeout chỉ giới hạn thời gian chờ; cancellation yêu cầu dừng; cleanup chứng minh task và tài nguyên đã chấm dứt.** Trong Spring Boot tests, ba việc này phải được thiết kế và xác minh riêng.

- `@Async` hoạt động qua Spring proxy/executor; dùng Future/CompletableFuture đúng semantics và luôn đợi có giới hạn.
- `@Scheduled` có lifecycle của ApplicationContext; đừng để cron tự chạy ngẫu nhiên giữa tests.
- `Future.cancel(true)` có thể interrupt worker; `CompletableFuture.cancel(true)` không tự interrupt physical computation trong Java 17.
- Test-owned `ThreadPoolTaskExecutor`/`ThreadPoolTaskScheduler` phải shutdown và await termination, còn Spring-managed beans để container quản lý.
- `CountDownLatch`, `finally`, bounded waits và latches ở cuối worker đáng tin cậy hơn `Thread.sleep`.

### Tài liệu tham khảo chính thức

- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): @Async, @Scheduled, executor/scheduler abstractions và lifecycle.
- [Spring Boot 3.5 — Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html): executor auto-config, queue/thread-pool và scheduling.
- [Spring Boot 3.5 — Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): spring.task.execution/scheduling shutdown settings.
- [Spring Framework 6.2 — ThreadPoolTaskExecutor API](https://docs.spring.io/spring-framework/docs/6.2.5/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html): lifecycle, submit và metrics.
- [Spring Framework 6.2 — ThreadPoolTaskScheduler API](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskScheduler.html): schedule, ScheduledFuture và shutdown.
- [Java SE 17 — Future API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): get timeout, cancel, isDone/isCancelled.
- [Java SE 17 — CompletableFuture API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): cancel và completion/timeout behavior.
- [Java SE 17 — ExecutorService API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): shutdown, shutdownNow và awaitTermination.
- [Spring TestContext — Transaction Management](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): preemptive timeout/thread-bound transaction warning.
