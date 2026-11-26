# Đảm bảo executor được làm sạch sau test

> **Chương:** Async verification  
> **Chương trình:** `SPRING_MODULITH_VERIFICATION_TESTING`  
> **Mục tiêu:** Kiểm soát vòng đời executor khi kiểm thử ứng dụng Spring Modulith: biết khi nào task kết thúc, khi nào pool được phép đóng, cách chờ termination có giới hạn và cách giữ các kiểm chứng event, transaction, cơ sở dữ liệu, ranh giới module và CI đáng tin cậy.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **tác vụ hoàn tất**, **executor không còn việc**, **executor đã shutdown**, **executor đã terminated** và **Spring ApplicationContext đã đóng**.
2. Xác định quyền sở hữu của executor: do một test tạo, do test suite/context tạo, hay do Spring application quản lý.
3. Viết cleanup cho `ExecutorService` dùng `shutdown()`, `awaitTermination(...)`, `shutdownNow()` và đường xử lý interruption có deadline.
4. Phân biệt `Future.cancel(true)`, `CompletableFuture.cancel(...)` và sự thật underlying worker đã dừng.
5. Đặt logic lifecycle ở `@AfterEach`/`@AfterAll` hoặc `try/finally` phù hợp với scope; không đóng pool đang được các test khác dùng.
6. Chờ business side effect đã commit khi `@ApplicationModuleListener` xử lý sự kiện Spring Modulith bất đồng bộ, không dùng trạng thái executor thay cho business oracle.
7. Thiết kế test kiểm tra **rejection, queue drain, exception, timeout, callback đến muộn** và cách phục hồi khi worker không ngừng.
8. Cấu hình và quan sát `ThreadPoolTaskExecutor` của Spring ở test context riêng khi cần kiểm tra chính shutdown semantics.
9. Tránh xung đột với Spring TestContext caching, `@DirtiesContext`, JUnit parallelism, database Testcontainers và event publication registry.
10. Đưa kiến trúc `ApplicationModules.verify()`, `@ApplicationModuleTest` và integration/cleanup tests vào quality gate CI.

**Thông điệp:** **Không để test kết thúc với một executor do chính test tạo vẫn đang chạy**, nhưng cũng **không được shutdown executor toàn ứng dụng sau mỗi test method**. Cleanup đúng nghĩa là *đúng owner, đúng thứ tự, có deadline, có bằng chứng termination và không phá công việc nghiệp vụ đã commit*.

## 2. Executor leak là gì và vì sao làm test flaky?

`ExecutorService` giữ thread pool, hàng đợi và các task. Nếu một test tự tạo pool rồi không đóng:

~~~java
@Test
void leaks_threads() {
    ExecutorService executor = Executors.newFixedThreadPool(2);
    executor.submit(() -> doSomeWork());

    // Sai: method return mà không shutdown executor.
}
~~~

Những tác động có thể xảy ra:

- Non-daemon worker giữ JVM test fork chưa thể kết thúc.
- Task của test trước tiếp tục ghi vào database của test tiếp theo.
- Thread/queue tích tụ khi chạy nhiều lớp test.
- Context/DB container bị đóng khi worker vẫn sử dụng resource.
- `@AfterEach` xóa fixture trước khi task chậm hoàn tất.
- Exception ở thread nền không được JUnit quan sát trực tiếp.
- CI job timeout, nhưng lỗi thực chất là **lifecycle leak**, không phải business timeout.

### Đừng kết luận leak chỉ vì thấy thread còn sống

Spring-managed executors có thể **cố ý sống cùng ApplicationContext**. Khi một test method xong nhưng context vẫn cached, thread pool chưa shutdown không nhất thiết là leak. Cần hỏi: **pool có đang ở đúng lifecycle mà owner yêu cầu không?**

| Triệu chứng | Có thể là lỗi | Có thể là bình thường |
| --- | --- | --- |
| Test-owned executor còn active sau `@AfterEach` | Có, resource chưa cleanup | Không, nếu cleanup contract cố ý chuyển ownership |
| Spring executor idle sau một test method | Không nhất thiết | ApplicationContext còn sống để cache |
| Pool đã `shutdown()` nhưng chưa `isTerminated()` | Có task còn chạy | Graceful shutdown đang hoàn tất |
| Business READY nhưng active executor > 0 | Có nhánh/retry khác | Pool đang xử lý tác vụ hợp lệ khác |
| `isTerminated() == true` nhưng side effect sai | Business test không đủ | Executor lifecycle đúng, logic sai |

**Không dùng một phép đo thread count toàn JVM** làm assertion duy nhất. JUnit, Spring, database driver và Testcontainers cũng có thể tạo thread nền hợp lệ.

## 3. Mô hình trạng thái của ExecutorService

Java phân biệt việc **ngừng nhận task** và việc **mọi task đã kết thúc**.

~~~mermaid
stateDiagram-v2
    [*] --> RUNNING
    RUNNING --> SHUTDOWN: shutdown()
    RUNNING --> STOP_REQUESTED: shutdownNow()
    SHUTDOWN --> STOP_REQUESTED: shutdownNow() nếu quá hạn
    SHUTDOWN --> TERMINATED: Mọi task đã xử lý
    STOP_REQUESTED --> TERMINATED: Worker thực sự kết thúc
    TERMINATED --> [*]
~~~

- `shutdown()`: không nhận task mới, nhưng cho những task đã submit cơ hội hoàn tất.
- `shutdownNow()`: cố gắng ngắt task đang chạy và trả về các task chưa bắt đầu. **Không bảo đảm** worker đã ngừng.
- `isShutdown()`: đã yêu cầu shutdown, **không phải** đã kết thúc.
- `isTerminated()`: mọi task đã kết thúc sau shutdown.
- `awaitTermination(timeout, unit)`: đợi pool thực sự terminated trong thời hạn, trả boolean.
- `Future.isDone()`: future đã complete/cancel/exceptional, **không phải luôn là bằng chứng side effect cuối đã commit**.

### Quy trình graceful shutdown có fallback

~~~text
1. executor.shutdown()
2. awaitTermination(grace period)
3. Nếu chưa terminated:
       executor.shutdownNow()
       awaitTermination(force period)
4. Nếu vẫn chưa terminated:
       FAIL cleanup, giữ diagnostics, không giả vờ đã dọn
~~~

**Đường trên chỉ dùng khi test sở hữu pool.** Đừng áp dụng vào `@AfterEach` trên executor Spring global được chia sẻ giữa các module.

## 4. Quyền sở hữu và phạm vi vòng đời

| Executor/worker | Chủ sở hữu | Thời điểm cleanup thông thường |
| --- | --- | --- |
| `Executors.newSingleThreadExecutor()` trong method | Test method | `try/finally` trong chính method |
| Executor được tạo ở `@BeforeEach` | Test instance/method | `@AfterEach` |
| Executor được tạo ở `@BeforeAll` dùng chung class | Test class | `@AfterAll`, sau mọi test và task |
| Static/shared executor toàn suite | Suite/launcher | Sau toàn suite, không từ mỗi method |
| `ThreadPoolTaskExecutor` bean của Spring | ApplicationContext | Context lifecycle/shutdown hook |
| Executor bên trong Testcontainers/driver | Hạ tầng thư viện | Theo resource owner, không tự tắt thread thư viện |
| Background task từ `@ApplicationModuleListener` | Ứng dụng/event infrastructure | Chờ business completion hoặc shutdown theo lifecycle app |
| Async task thuộc fake test-only bean | Test fixture đã thiết kế | Theo fixture scope và controlled termination |

### Một quy tắc kiểm tra ownership

Trước khi gọi `shutdownNow()`, trả lời được:

1. Code nào tạo pool?
2. Có test hoặc bean khác đang submit vào pool đó không?
3. Nếu pool dừng ngay, task đang commit transaction có bị ảnh hưởng không?
4. Có cơ chế quiescence/biz outcome trước shutdown không?
5. Ai chịu trách nhiệm nếu pool không terminate?

Nếu không chắc pool thuộc test, **không tự ý tắt**.

## 5. Unit test: mẫu cleanup cơ bản với try/finally

Khi một test chỉ cần chạy một task Java ngoài Spring, có thể dùng:

~~~java
@Test
void computes_in_background() throws Exception {
    ExecutorService executor =
            Executors.newSingleThreadExecutor();

    try {
        Future<Integer> result =
                executor.submit(() -> 20 + 22);

        assertThat(result.get(2, TimeUnit.SECONDS))
                .isEqualTo(42);
    } finally {
        executor.shutdown();

        if (!executor.awaitTermination(
                2, TimeUnit.SECONDS)) {
            executor.shutdownNow();
            assertThat(executor.awaitTermination(
                    2, TimeUnit.SECONDS))
                    .as("Test-owned executor must terminate")
                    .isTrue();
        }
    }
}
~~~

Trong code thật, thêm imports JUnit, AssertJ, `ExecutorService`, `Executors`, `Future` và `TimeUnit`. Nếu thread bị interrupt trong cleanup, phải yêu cầu shutdown sớm, giữ interrupt status và bảo đảm failure được báo; xem helper mục 6.

**Vì sao `result.get(...)` chưa thay thế cleanup?** Future của một task thành công không tự kết thúc toàn executor. Pool vẫn có thread chờ các task kế tiếp cho tới khi owner shutdown.

### Không tạo pool chỉ để kiểm tra logic đồng bộ

Nếu phép tính là `20 + 22` và yêu cầu không có concurrency, unit test trực tiếp nhanh và chắc chắn hơn. Ví dụ trên chỉ nhằm minh họa lifecycle. Chỉ kiểm thử async thật khi scheduling/cancellation là hành vi cần chứng minh.

## 6. Helper đóng executor có deadline và xử lý interruption

Một helper tái sử dụng giúp hạn chế quên shutdown ở nhiều test:

~~~java
package com.example.shop.testing;

import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.TimeUnit;

public final class ExecutorCleanup {

    private ExecutorCleanup() {}

    public static void stopOwned(
            ExecutorService executor,
            Duration gracefulWait,
            Duration forcedWait) throws InterruptedException {

        Objects.requireNonNull(executor);
        Objects.requireNonNull(gracefulWait);
        Objects.requireNonNull(forcedWait);

        if (gracefulWait.isNegative() || forcedWait.isNegative()) {
            throw new IllegalArgumentException(
                    "Shutdown budgets must be non-negative");
        }

        executor.shutdown();

        try {
            if (!executor.awaitTermination(
                    gracefulWait.toNanos(), TimeUnit.NANOSECONDS)) {

                executor.shutdownNow();

                if (!executor.awaitTermination(
                        forcedWait.toNanos(), TimeUnit.NANOSECONDS)) {
                    throw new AssertionError(
                            "Owned executor did not terminate");
                }
            }
        } catch (InterruptedException interrupted) {
            executor.shutdownNow();
            Thread.currentThread().interrupt();
            throw interrupted;
        }
    }
}
~~~

### Giải thích từng quyết định

- `shutdown()` được ưu tiên để task đã submit có thể hoàn tất tự nhiên.
- Chỉ nếu quá grace period mới gọi `shutdownNow()`.
- Sau force request, tiếp tục kiểm tra `awaitTermination` — không coi return của `shutdownNow()` là proof.
- Khi cleanup thread bị interrupt, yêu cầu force shutdown và **khôi phục interrupt flag** trước khi truyền exception.
- Helper không tự đóng `ApplicationContext`, không xóa database và không dùng cho pool thuộc Spring.
- Nó báo `AssertionError` nếu không thể bảo đảm termination; không nuốt lỗi để CI xanh.

**Giới hạn:** Helper chờ task trong executor kết thúc. Nếu task đã enqueue công việc sang hệ thống khác, executor terminated không chứng minh remote/business work hoàn tất.

### Mốc ngân sách

`gracefulWait` và `forcedWait` là budget dọn tài nguyên **khác** Awaitility budget cho business outcome. Chọn qua số liệu test và failure policy, không sao chép vô điều kiện cùng một số cho mọi môi trường.

## 7. @BeforeEach và @AfterEach: scope của executor

Khi một lớp JUnit tạo executor trước mỗi method:

~~~java
package com.example.shop.testing;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class PerTestExecutorLifecycleTest {

    private ExecutorService executor;

    @BeforeEach
    void setUp() {
        executor = Executors.newFixedThreadPool(2);
    }

    @Test
    void produces_result() throws Exception {
        Future<String> future =
                executor.submit(() -> "READY");

        assertThat(future.get(2, TimeUnit.SECONDS))
                .isEqualTo("READY");
    }

    @AfterEach
    void tearDown() throws InterruptedException {
        if (executor != null) {
            ExecutorCleanup.stopOwned(
                    executor,
                    Duration.ofSeconds(2),
                    Duration.ofSeconds(2));
        }
    }
}
~~~

Nếu test body ném assertion error hoặc timeout, `@AfterEach` vẫn được JUnit gọi theo lifecycle thông thường. **Nếu JVM/process bị kill cưỡng bức**, không có bảo đảm cleanup Java vẫn chạy; CI cần job-level timeout và môi trường cô lập.

### Khi nào dùng @AfterAll?

Nếu pool được tạo ở `@BeforeAll` rồi chia sẻ giữa nhiều test methods, đóng trong `@AfterEach` sẽ làm method tiếp theo gặp `RejectedExecutionException`. Khi ấy:

~~~java
// Skeleton: dùng cùng test class lifecycle và access pattern.
@BeforeAll
static void startSuitePool() {
    suitePool = Executors.newFixedThreadPool(4);
}

@AfterAll
static void stopSuitePool() throws InterruptedException {
    ExecutorCleanup.stopOwned(
            suitePool,
            Duration.ofSeconds(5),
            Duration.ofSeconds(2));
}
~~~

Code trên là phần minh họa; cần field `static ExecutorService suitePool`. Phải xác định có test methods chạy song song và có còn task outstanding khi đến `@AfterAll` không.

### Lưu ý setup fail giữa chừng

`@BeforeEach` có thể ném lỗi sau khi tạo pool. Dùng null guards như trên và tránh tạo nhiều resource rồi chỉ dọn resource cuối. Với fixture phức tạp, có thể dùng một test resource owner/lifecycle extension được thiết kế riêng, nhưng không làm chuyện này thành global executor controller.

## 8. Future hoàn thành và executor sạch là hai điều khác nhau

Một test có thể chờ Future nhưng không shutdown pool:

~~~java
Future<Integer> result = executor.submit(() -> 42);
assertThat(result.get(2, TimeUnit.SECONDS))
        .isEqualTo(42);

// Nếu không shutdown, executor vẫn nhận task mới.
~~~

Một test khác có thể shutdown pool khi Future chưa xong:

~~~java
Future<?> job = executor.submit(() -> writeToDatabase());

executor.shutdown();
// Graceful: job đã submit có thể vẫn đang chạy.
~~~

| Phép kiểm | Chứng minh | Không chứng minh |
| --- | --- | --- |
| `Future.get` trả kết quả | Task đại diện bởi Future hoàn tất bình thường | Pool terminated |
| `Future.isDone` | Task Future đã ở trạng thái hoàn tất/cancel | Side effect theo business contract đã commit |
| `executor.isShutdown` | Pool không nhận task mới theo shutdown | Worker đã ngừng |
| `executor.isTerminated` | Pool đã kết thúc mọi task sau shutdown | Side effect ngoài executor đã hoàn tất |
| `executor.awaitTermination` true | Pool thực sự terminated trong deadline | Các async jobs đã delegate sang broker/remote đã xong |
| Public API đọc `READY` | Business side effect visible theo contract | Tất cả pool trong JVM idle |

**Test tốt có thể cần hai assertion riêng:** trước tiên business outcome đạt, sau đó owned executor không leak. Với Spring-managed listener, không lấy global executor `isTerminated` làm điều kiện của từng test method.

## 9. Cancellation, interruption và các điểm không thể dừng ngay

`Future.cancel(true)` từ `ExecutorService.submit` có thể yêu cầu interrupt; điều đó không bảo đảm task đã dừng:

~~~java
Future<?> task = executor.submit(() -> {
    while (!Thread.currentThread().isInterrupted()) {
        doOneSmallUnitOfWork();
    }
});

task.cancel(true); // Chỉ yêu cầu cancel.
~~~

Một worker hợp tác cần:

- Kiểm tra flag hoặc chặn ở `InterruptedException`-aware operation.
- Không nuốt `InterruptedException` rồi tiếp tục làm việc.
- Kết thúc/rollback một transaction dang dở theo chính sách.
- Trả tài nguyên trong `finally`.
- Không gọi external API tiếp sau khi biết cancellation được chấp nhận.
- Có deadline tổng để không giữ CI vô hạn.

### Phản mẫu

~~~java
while (true) {
    try {
        Thread.sleep(100);
    } catch (InterruptedException ignored) {
        // Sai: worker không dừng và nuốt signal.
    }
}
~~~

`shutdownNow()` có thể không terminate pool nếu task bỏ qua interruption. Báo lỗi leak, không dùng `Thread.stop()` hay kill toàn JVM trong một cleanup test bình thường.

### CompletableFuture khác FutureTask

`CompletableFuture.cancel(true)` chủ yếu thay đổi trạng thái completion; `mayInterruptIfRunning` không được dùng để interrupt underlying action theo semantics `CompletableFuture`. Đừng assert `isCancelled() == true` rồi kết luận thread đã ngừng. Nếu cần cancellation thật, thiết kế cancellation token/cooperative worker và một termination signal riêng.

## 10. Graceful drain, queued tasks và rejection

Khi gọi `shutdown()`, những task đã được chấp nhận trước đó có thể tiếp tục hoàn thành. Sau shutdown, lệnh `submit` mới thường bị từ chối qua `RejectedExecutionException`.

~~~java
ExecutorService executor =
        Executors.newSingleThreadExecutor();

try {
    Future<Integer> accepted =
            executor.submit(() -> 7);

    executor.shutdown();

    assertThat(accepted.get(2, TimeUnit.SECONDS))
            .isEqualTo(7);

    assertThatThrownBy(() -> executor.submit(() -> 8))
            .isInstanceOf(RejectedExecutionException.class);

    assertThat(executor.awaitTermination(
            2, TimeUnit.SECONDS))
            .isTrue();
} finally {
    executor.shutdownNow();
}
~~~

Cần static imports AssertJ và imports `Executors`, `ExecutorService`, `Future`, `TimeUnit`, `RejectedExecutionException`. Ví dụ trên dùng test-owned executor; `finally` vẫn cố stop nếu assert/await trước đó fail.

### Không dùng trạng thái queue làm oracle duy nhất

Một task vừa rời queue có thể đang **chạy**, nên `queue.size() == 0` không có nghĩa pool idle. `getActiveCount() == 0` tại một thời điểm cũng không phải bằng chứng mọi task đã được nhận, đã commit hoặc không còn task đến muộn.

Với test-owned pool, `awaitTermination` là oracle lifecycle mạnh hơn. Với event-based Spring work, nên dùng **business completion state/registry/quiescence policy** riêng.

## 11. Named threads và observability khi CI báo leak

Tên thread có ích khi chẩn đoán task nào thuộc fixture:

~~~java
AtomicInteger counter = new AtomicInteger();

ThreadFactory factory = runnable -> {
    Thread thread = new Thread(runnable);
    thread.setName("test-order-worker-" +
            counter.incrementAndGet());
    return thread;
};

ExecutorService executor =
        Executors.newFixedThreadPool(2, factory);
~~~

Cần imports `java.util.concurrent.ThreadFactory` và `java.util.concurrent.atomic.AtomicInteger`.

**Không ép `setDaemon(true)` chỉ để JVM có thể thoát.** Daemon thread có thể che leak và bị chấm dứt khi JVM kết thúc, dù công việc vẫn dang dở. Bảo đảm termination đúng mới là mục tiêu.

### Những số liệu nên ghi khi shutdown fail

| Tín hiệu | Công dụng |
| --- | --- |
| `executor.isShutdown()` | Đã yêu cầu dừng chưa |
| `executor.isTerminated()` | Dừng thật chưa |
| Worker thread names / stack traces | Tìm task bị block |
| Active count/queue size khi dùng `ThreadPoolExecutor` | Gợi ý congestion, không phải oracle hoàn chỉnh |
| Future completion/exception | Biết task cụ thể có lỗi không |
| Correlation ID | Tìm event của đúng test |
| Consumer DB state/registry state | Phân biệt executor leak với business failure |
| Deadline sử dụng | Biết timeout thuộc tầng nào |

Không tự khẳng định “zero extra JVM threads” vì JUnit/Spring/driver có thread nền hợp lệ không thuộc fixture.
## 12. Spring-managed executor không thuộc @AfterEach của từng method

Với Spring Boot, `@Async` và những thành phần bất đồng bộ có thể sử dụng executor do ApplicationContext quản lý. Đặc điểm vòng đời khác với pool tạo bằng `Executors.newFixedThreadPool(...)` trong unit test:

- Bean executor sống cùng context cho đến khi context được đóng/refresh theo policy.
- Spring TestContext **thường cache context** qua nhiều test classes tương thích.
- Một test method kết thúc **không** có nghĩa bean executor cần shutdown.
- Test khác có thể đang dùng cùng context và cùng executor.
- `@DirtiesContext` hoặc suite shutdown có thể làm container đóng executor và các bean phụ thuộc.

### Hai test có cùng context nhưng khác mục tiêu

| Test | Điều phải xác minh | Có shutdown executor sau method không? |
| --- | --- | --- |
| Unit test tạo ExecutorService riêng | Worker và pool owned được dọn | Có, tại `@AfterEach`/`finally` |
| `@ApplicationModuleTest` kiểm tra producer publication | Event đúng type/payload | Không tắt Spring executor toàn context |
| Consumer integration event | Side effect sau commit đúng | Không tắt Spring executor; await public business state |
| Spring executor shutdown contract test | Bean đóng đúng khi context close | Dùng context **riêng biệt** được test sở hữu |
| Testcontainers integration | Context, DB, registry có lifecycle phù hợp | Không stop pool/DB shared trước worker |

### Lỗi tiêu biểu

~~~java
// Anti-pattern: executor là bean dùng chung ApplicationContext.
@Autowired
ThreadPoolTaskExecutor taskExecutor;

@AfterEach
void tearDown() {
    taskExecutor.shutdown(); // Có thể phá test khác.
}
~~~

Kể cả khi code chạy qua `@SpringBootTest` và pool đang idle, hành động này vẫn làm các method khác không thể schedule `@Async` job. Đây không phải cleanup đúng ownership.

**Thay thế:** Chờ business state cần chứng minh trong test; để Spring quản lý shutdown của bean khi context đóng. Chỉ viết test shutdown riêng nếu chính lifecycle là feature muốn kiểm tra.

## 13. Cấu hình ThreadPoolTaskExecutor: giới hạn và shutdown policy

Một bean executor có thể được cấu hình rõ ràng:

~~~java
package com.example.shop.config;

import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
class AsyncExecutorConfiguration {

    @Bean(name = "taskExecutor")
    ThreadPoolTaskExecutor taskExecutor() {
        var executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(32);
        executor.setThreadNamePrefix("shop-async-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());

        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(10);
        return executor;
    }
}
~~~

Đây là **cấu hình minh họa**, không phải chuẩn mặc định. Nếu ứng dụng đã có `AsyncConfigurer` hoặc các `TaskExecutor` khác, **tên bean và resolution của `@Async` phải được xác minh** theo cấu hình thực tế; định nghĩa bean tên `taskExecutor` đơn độc không bảo đảm mọi async path dùng chính pool này.

### Ý nghĩa của cấu hình

| Thiết lập | Tác dụng | Không giải quyết |
| --- | --- | --- |
| `corePoolSize` / `maxPoolSize` | Khả năng đồng thời | Database pool và remote latency |
| `queueCapacity` | Số task có thể chờ trước khi reject/mở rộng | Lỗi handler |
| `threadNamePrefix` | Chẩn đoán thread pool | Correlation ID nghiệp vụ |
| Rejection handler | Chính sách khi executor quá tải | Đảm bảo event bền vững |
| `setWaitForTasksToCompleteOnShutdown(true)` | Cho các task chờ/đang chạy cơ hội hoàn tất khi shutdown theo cấu hình | Mọi task đều hoàn tất kịp |
| `setAwaitTerminationSeconds(10)` | Giới hạn phần chờ termination khi shutdown | Cancel không hợp tác hoặc DB treo vô hạn |

Đọc semantics Spring Framework version đang sử dụng, đặc biệt tương tác với context close và các cờ shutdown khác; không giả định tất cả Spring versions có lifecycle giống hệt.

### Cẩn trọng với event publication

Đôi khi handler event bị reject vì executor full. Khi publisher trong transaction, failure handling phụ thuộc lúc schedule, transaction phase, adapter registry và exception policy. **Không tự kết luận publication đã được lưu bền hoặc sẽ retry** chỉ vì bạn chọn một `ThreadPoolTaskExecutor` có queue.

Cần test rejection/failure path với registry nếu reliability là hợp đồng.

## 14. Test riêng cho Spring executor shutdown semantics

Muốn kiểm tra một Spring `ThreadPoolTaskExecutor` có giải phóng tài nguyên khi context đóng, hãy sở hữu **một context cô lập** thay vì đóng context mà các integration tests khác đang dùng.

Ví dụ dùng `AnnotationConfigApplicationContext`:

~~~java
package com.example.shop.testing;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

class IsolatedSpringExecutorShutdownTest {

    @Test
    void shuts_down_pool_on_context_close() throws Exception {
        var context = new AnnotationConfigApplicationContext(
                ExecutorConfig.class);

        ThreadPoolTaskExecutor executor = context.getBean(
                "isolatedExecutor", ThreadPoolTaskExecutor.class);

        try {
            var future = executor.submit(() -> "DONE");

            assertThat(future.get(2, TimeUnit.SECONDS))
                    .isEqualTo("DONE");
        } finally {
            context.close();
        }

        assertThat(executor.getThreadPoolExecutor().isTerminated())
                .as("Isolated Spring executor should terminate")
                .isTrue();
    }

    @Configuration(proxyBeanMethods = false)
    static class ExecutorConfig {

        @Bean(name = "isolatedExecutor")
        ThreadPoolTaskExecutor isolatedExecutor() {
            var executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(2);
            executor.setThreadNamePrefix("isolated-");
            executor.setWaitForTasksToCompleteOnShutdown(true);
            executor.setAwaitTerminationSeconds(3);
            return executor;
        }
    }
}
~~~

**Phạm vi:** Test này chỉ kiểm tra Spring lifecycle của **bean executor được tạo trong context riêng**. Nó không chứng minh consumer event Spring Modulith đã commit hoặc production executor đã dùng đúng routing.

### Một tinh chỉnh để test shutdown khi có task đang chạy

- Dùng latch `started` để xác nhận job đang chạy.
- Trong một thread test-owned khác, gọi `context.close()`.
- Chờ một khoảng có giới hạn, xác minh close chưa hoàn tất nếu policy yêu cầu chờ task.
- Release latch trong `finally`.
- Xác minh close và pool termination.
- Không chặn listener global của context chia sẻ.

Lưu ý thay đổi concurrency làm test phức tạp hơn; dùng **hai latch và deadline**, không dựa vào `Thread.sleep` để đoán task đã bắt đầu. Nếu bài này chỉ cần xác nhận normal close, ví dụ phía trên đã đủ.

## 15. Context caching: executor không bị đóng theo từng test method

Spring TestContext dùng cache dựa trên cấu hình context, profiles, overrides và customizers. Nếu nhiều classes dùng cùng context, chỉ một bean executor tồn tại xuyên các methods.

~~~mermaid
flowchart LR
    T1["JUnit Test A"] --> C["Cached ApplicationContext"]
    T2["JUnit Test B"] --> C
    C --> EX["Shared Spring executor"]
    EX --> L["Async listener"]
    L --> DB["Shared test database"]
~~~

Hệ quả:

- `@AfterEach` của Test A không được shutdown EX nếu Test B có thể còn sử dụng.
- Test A cũng không được xóa dữ liệu của B vì “A đã xong”.
- `@DirtiesContext` làm context không còn tái sử dụng được và có thể gây shutdown trong khi worker đang chạy.
- TestContext cache hit/miss và Testcontainers class-scoped container lifecycle có thể lệch nhau.
- Đóng context để sửa flaky test có thể chỉ làm lỗi trở nên hiếm, không giải quyết race.

### Cách tổ chức scope

| Bài test | Scope khuyến nghị | Cleanup |
| --- | --- | --- |
| Unit task algorithm | Không Spring | Owned executor sau method |
| Module publication | `@ApplicationModuleTest` | Không shutdown shared Spring executor |
| Async consumer integration | Full context hoặc module context đủ dependencies | Chờ business state, cô lập data |
| Executor lifecycle | Isolated ApplicationContext | Context close + assert pool termination |
| Broker/registry recovery | Context và persistent storage theo scenario | Recovery/quiescence trước dispose |

**Không tự tạo `@DirtiesContext` hàng loạt** vì chi phí cold context cao và có thể phát sinh lỗi do những worker bị ngắt giữa chừng.

## 16. Spring Modulith: từ event publisher tới consumer executor

Ví dụ ứng dụng `orders` và `fulfillment`:

~~~text
com.example.shop
├── ShopApplication.java
├── orders/
│   ├── OrderCommands.java
│   ├── OrderPlaced.java
│   └── internal/
│       ├── OrderApplicationService.java
│       └── persistence/
│           ├── OrderEntity.java
│           └── OrderRepository.java
└── fulfillment/
    ├── FulfillmentQueries.java
    ├── PreparationState.java
    └── internal/
        ├── OrderPlacedListener.java
        ├── FulfillmentQueryService.java
        └── persistence/
            ├── FulfillmentTask.java
            └── FulfillmentTaskRepository.java
~~~

Theo cơ chế nhận diện mặc định, `orders` và `fulfillment` là các application modules. Event `OrderPlaced` nằm ở API package của `orders`; consumer không cần import repository/entity nội bộ.

~~~mermaid
sequenceDiagram
    participant T as JUnit
    participant O as orders
    participant E as Spring event infrastructure
    participant X as Async executor
    participant F as fulfillment listener
    participant DB as DB

    T->>O: place(customerId)
    O->>DB: INSERT order trong T1
    O->>E: publish OrderPlaced
    O->>DB: COMMIT T1
    O-->>T: orderId
    E->>X: Schedule listener
    X->>F: Call on(OrderPlaced)
    F->>DB: INSERT task trong T2
    F->>DB: COMMIT T2
    T->>DB: Query task theo orderId
    DB-->>T: READY
    Note over T,X: Test await READY, không shutdown X sau method
~~~

### Mốc cần phân biệt

| Mốc | Có thể được quan sát bằng | Ý nghĩa |
| --- | --- | --- |
| Event được publish | `PublishedEvents` | Producer công bố event |
| Worker được schedule | Executor/test instrumentation | Task đã được nhận vào executor |
| Listener bắt đầu | Log/latch/test port | Callback bắt đầu, **chưa** commit |
| Consumer commit | Public read API thấy task | Side effect được ghi và đọc được |
| Executor terminated | `awaitTermination` sau shutdown | Lifecycle pool kết thúc |
| Business terminal outcome | Workflow status/receipt | Các bước nghiệp vụ theo contract đã xong |

Nếu test chỉ bảo vệ **task được tạo**, nó phải chờ consumer commit, không cần shutdown application executor. Nếu test bảo vệ **Spring executor lifecycle**, nó phải tạo một context cô lập để đóng.

## 17. Producer module: API công khai và transaction T1

**`src/main/java/com/example/shop/ShopApplication.java`**

~~~java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableAsync;

@SpringBootApplication
@EnableAsync
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

`@EnableAsync` hỗ trợ các đường gọi async, nhưng không tự bảo đảm durable event storage, retry hoặc event handler idempotent.

**`src/main/java/com/example/shop/orders/OrderCommands.java`**

~~~java
package com.example.shop.orders;

import java.util.UUID;

public interface OrderCommands {
    UUID place(String customerId);
}
~~~

**`src/main/java/com/example/shop/orders/OrderPlaced.java`**

~~~java
package com.example.shop.orders;

import java.util.UUID;

public record OrderPlaced(UUID orderId) {}
~~~

### JPA entity và repository

**`src/main/java/com/example/shop/orders/internal/persistence/OrderEntity.java`**

~~~java
package com.example.shop.orders.internal.persistence;

import java.util.UUID;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customer_orders")
public class OrderEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(nullable = false)
    private String customerId;

    protected OrderEntity() {}

    public OrderEntity(String customerId) {
        this.customerId = customerId;
    }

    public UUID getId() {
        return id;
    }
}
~~~

**`src/main/java/com/example/shop/orders/internal/persistence/OrderRepository.java`**

~~~java
package com.example.shop.orders.internal.persistence;

import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository
        extends JpaRepository<OrderEntity, UUID> {}
~~~

### Service phát event trong transaction

**`src/main/java/com/example/shop/orders/internal/OrderApplicationService.java`**

~~~java
package com.example.shop.orders.internal;

import java.util.UUID;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.example.shop.orders.OrderCommands;
import com.example.shop.orders.OrderPlaced;
import com.example.shop.orders.internal.persistence.OrderEntity;
import com.example.shop.orders.internal.persistence.OrderRepository;

@Service
class OrderApplicationService implements OrderCommands {

    private final OrderRepository orders;
    private final ApplicationEventPublisher publisher;

    OrderApplicationService(
            OrderRepository orders,
            ApplicationEventPublisher publisher) {
        this.orders = orders;
        this.publisher = publisher;
    }

    @Override
    @Transactional
    public UUID place(String customerId) {
        if (customerId == null || customerId.isBlank()) {
            throw new IllegalArgumentException(
                    "customerId must not be blank");
        }

        var order = orders.save(new OrderEntity(customerId));
        UUID id = order.getId();

        publisher.publishEvent(new OrderPlaced(id));
        return id;
    }
}
~~~

`publishEvent(...)` được gọi **trong T1**. Khi service được gọi qua Spring transaction proxy và không có outer transaction, commit của T1 được xử lý trước khi lời gọi hoàn tất thành công, nhưng listener async có thể vẫn đang chạy. Không shutdown executor để “bảo đảm publisher event đã hoàn tất”.

## 18. Consumer: public state là oracle sau commit

**`src/main/java/com/example/shop/fulfillment/PreparationState.java`**

~~~java
package com.example.shop.fulfillment;

public enum PreparationState {
    NOT_OBSERVED,
    READY
}
~~~

**`src/main/java/com/example/shop/fulfillment/FulfillmentQueries.java`**

~~~java
package com.example.shop.fulfillment;

import java.util.UUID;

public interface FulfillmentQueries {
    PreparationState statusFor(UUID orderId);
}
~~~

### JPA persistence

**`src/main/java/com/example/shop/fulfillment/internal/persistence/FulfillmentTask.java`**

~~~java
package com.example.shop.fulfillment.internal.persistence;

import java.util.UUID;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "fulfillment_tasks")
public class FulfillmentTask {

    @Id
    private UUID orderId;

    protected FulfillmentTask() {}

    public FulfillmentTask(UUID orderId) {
        this.orderId = orderId;
    }
}
~~~

**`src/main/java/com/example/shop/fulfillment/internal/persistence/FulfillmentTaskRepository.java`**

~~~java
package com.example.shop.fulfillment.internal.persistence;

import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;

public interface FulfillmentTaskRepository
        extends JpaRepository<FulfillmentTask, UUID> {}
~~~

### @ApplicationModuleListener

**`src/main/java/com/example/shop/fulfillment/internal/OrderPlacedListener.java`**

~~~java
package com.example.shop.fulfillment.internal;

import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

import com.example.shop.orders.OrderPlaced;
import com.example.shop.fulfillment.internal.persistence.FulfillmentTask;
import com.example.shop.fulfillment.internal.persistence.FulfillmentTaskRepository;

@Component
class OrderPlacedListener {

    private final FulfillmentTaskRepository tasks;

    OrderPlacedListener(FulfillmentTaskRepository tasks) {
        this.tasks = tasks;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        if (!tasks.existsById(event.orderId())) {
            tasks.save(new FulfillmentTask(event.orderId()));
        }
    }
}
~~~

`@ApplicationModuleListener` thông thường là listener hậu commit, bất đồng bộ và có transaction mới. Đây là code happy path; `existsById` + `save` không đủ tránh race khi duplicate events cùng xử lý. Trong reliability test cần xử lý database conflict/idempotency theo hợp đồng.

### Query service

**`src/main/java/com/example/shop/fulfillment/internal/FulfillmentQueryService.java`**

~~~java
package com.example.shop.fulfillment.internal;

import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.example.shop.fulfillment.FulfillmentQueries;
import com.example.shop.fulfillment.PreparationState;
import com.example.shop.fulfillment.internal.persistence.FulfillmentTaskRepository;

@Service
class FulfillmentQueryService implements FulfillmentQueries {

    private final FulfillmentTaskRepository tasks;

    FulfillmentQueryService(FulfillmentTaskRepository tasks) {
        this.tasks = tasks;
    }

    @Override
    @Transactional(readOnly = true)
    public PreparationState statusFor(UUID orderId) {
        return tasks.existsById(orderId)
                ? PreparationState.READY
                : PreparationState.NOT_OBSERVED;
    }
}
~~~

Test chỉ gọi public `FulfillmentQueries`; không import `FulfillmentTaskRepository` từ module khác. Mỗi poll qua transaction đọc mới có thể thấy commit từ listener nếu isolation/cache được thiết kế đúng.

## 19. @ApplicationModuleTest: producer publication không phải executor lifecycle

Đặt test trong package `com.example.shop.orders`:

**`src/test/java/com/example/shop/orders/OrderPublicationTest.java`**

~~~java
package com.example.shop.orders;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;
import org.springframework.test.context.TestPropertySource;

@ApplicationModuleTest
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:orders-pub;DB_CLOSE_DELAY=-1",
        "spring.datasource.driver-class-name=org.h2.Driver",
        "spring.jpa.hibernate.ddl-auto=create-drop"
})
class OrderPublicationTest {

    @Autowired
    OrderCommands orders;

    @Test
    void publishes_event_for_created_order(PublishedEvents events) {
        UUID id = orders.place("CUS-PUBLISH");

        assertThat(events.ofType(OrderPlaced.class))
                .anySatisfy(event ->
                        assertThat(event.orderId()).isEqualTo(id));
    }

    @Test
    void invalid_customer_has_no_event(PublishedEvents events) {
        assertThatThrownBy(() -> orders.place(" "))
                .isInstanceOf(IllegalArgumentException.class);

        assertThat(events.ofType(OrderPlaced.class)).isEmpty();
    }
}
~~~

**Bằng chứng:** Producer publish event type/payload theo case; không publish khi input bị reject trong ví dụ.

**Chưa có bằng chứng:** Listener consumer đã được nạp, task đã commit, executor đã drain, registry bền hay event chỉ được gửi đúng một lần. `anySatisfy` chỉ đòi có **ít nhất một** event khớp.

### Lưu ý module test bootstrap

`@ApplicationModuleTest` giới hạn phạm vi module; consumer không tự có mặt trong producer-only test. Chiều dependency tĩnh từ `fulfillment` tới `orders.OrderPlaced` thường không làm `fulfillment` trở thành dependency trực tiếp **của orders**. Không cố chờ consumer trong module test thiếu consumer; dùng cross-module integration test.

### Không shutdown executor trong producer test

Khi test hoàn tất, Spring context có thể vẫn cached. Nếu nó tạo executor, đó là resource của context, **không** phải pool của riêng test method. Không thêm `@AfterEach taskExecutor.shutdown()` chỉ vì producer test đã thấy event.

## 20. Consumer integration: chờ READY, không shutdown pool

**`src/test/java/com/example/shop/OrderFulfillmentIntegrationTest.java`**

~~~java
package com.example.shop;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

import java.time.Duration;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;

import com.example.shop.orders.OrderCommands;
import com.example.shop.fulfillment.FulfillmentQueries;
import com.example.shop.fulfillment.PreparationState;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:fulfillment-it;DB_CLOSE_DELAY=-1",
        "spring.datasource.driver-class-name=org.h2.Driver",
        "spring.jpa.hibernate.ddl-auto=create-drop"
})
class OrderFulfillmentIntegrationTest {

    @Autowired
    OrderCommands orders;

    @Autowired
    FulfillmentQueries fulfillment;

    @Test
    void awaits_consumer_side_effect_after_commit() {
        UUID id = orders.place(
                "CUS-" + UUID.randomUUID());

        await()
                .atMost(Duration.ofSeconds(10))
                .pollInterval(Duration.ofMillis(100))
                .untilAsserted(() ->
                        assertThat(fulfillment.statusFor(id))
                                .isEqualTo(PreparationState.READY));
    }
}
~~~

### Bài này chứng minh gì?

- Spring context nạp cả publisher và listener.
- Producer T1 commit qua service khi không có outer transaction.
- Listener có cơ hội chạy trên executor phù hợp.
- Consumer T2 ghi task; phép đọc bên ngoài T2 thấy state READY.
- Test không return trước khi outcome bắt buộc được quan sát.

### Bài này chưa chứng minh gì?

- Pool Spring đã shutdown hay không còn task khác.
- Registry publication completed cho mọi duplicate/retry.
- Event xử lý exactly once.
- External shipping API đã hoàn tất.
- Production p99 latency dưới một ngưỡng.

**Vì vậy không kết thúc test bằng `taskExecutor.shutdown()`**; nó phá lifecycle chung mà không bổ sung bằng chứng về task đã commit.

## 21. @Transactional trên test có thể làm listener không chạy

Sai khi kiểm chứng `AFTER_COMMIT`:

~~~java
@Transactional
@Test
void waits_inside_outer_test_transaction() {
    UUID id = orders.place("CUS-TX");

    await()
            .atMost(Duration.ofSeconds(5))
            .untilAsserted(() ->
                    assertThat(fulfillment.statusFor(id))
                            .isEqualTo(PreparationState.READY));
}
~~~

Spring Test có thể mở transaction và rollback cuối test; `orders.place(...)` propagation mặc định có thể tham gia transaction ấy. Không có commit T1 → listener AFTER_COMMIT không chạy → Awaitility timeout.

**Không tăng timeout hoặc shutdown executor để giải quyết điều này.** Phải điều chỉnh boundary: service producer commit thật, hoặc dùng `TransactionTemplate`/Spring Test transaction control khi bài test chủ ý kiểm thử rollback.

### Test rollback là claim khác

~~~java
@Autowired
TransactionTemplate transactions;

@Test
void source_rollback_does_not_commit_order() {
    UUID id = transactions.execute(status -> {
        UUID created = orders.place("CUS-ROLLBACK");
        status.setRollbackOnly();
        return created;
    });

    assertThat(id).isNotNull();

    // Cần public source query/test fixture để xác nhận rollback.
    // Không assert NOT_OBSERVED một lần rồi kết luận
    // listener không bao giờ được chạy.
}
~~~

Trích đoạn trên minh họa transaction rollback, chưa phải test âm hoàn chỉnh. Một assertion absence tức thời có thể pass trước listener cấu hình sai chạy muộn.

## 22. Cleanup Spring executor không được lấn át cleanup fixture

Khi consumer đã tạo task, `@AfterEach` có thể cần dọn dữ liệu test. Nhưng **dọn dữ liệu** và **đóng executor** là hai việc khác nhau.

~~~text
Business integration:
   1. place orderId
   2. await READY
   3. ghi assertion hoàn thành
   4. cleanup fixture theo scope an toàn
   5. KHÔNG shutdown Spring executor

Isolated executor lifecycle:
   1. tạo isolated context/executor
   2. submit controlled jobs
   3. close context
   4. assert executor termination
   5. không đụng tới DB/business event nếu không cần
~~~

### Sai lầm trong @AfterEach

~~~java
@Autowired
ThreadPoolTaskExecutor sharedExecutor;

@AfterEach
void cleanup() {
    sharedExecutor.shutdown();
    repository.deleteAll();
}
~~~

Hai vấn đề: shutdown sai owner và xóa toàn bảng có thể cạnh tranh với listener/test khác.

### Hướng an toàn

- Mỗi test dùng `UUID` riêng.
- Chờ side effect cần chứng minh trước return.
- Không xóa dữ liệu khi listener vẫn có thể retry hoặc replay.
- Không xóa pending publication khi đang test recovery.
- Với test-owned executor, cleanup trong `finally`/`@AfterEach` và assert terminated.
- Nếu không thể chắc chắn worker quiescent, dùng isolated DB/schema hoặc disposable context để tránh làm hỏng test khác.

## 23. Khi shutdownNow trả task chưa thực thi

Một executor một thread đang chạy công việc A và đã nhận công việc B vào queue. Nếu yêu cầu `shutdownNow()`, implementation sẽ cố interrupt A và trả các `Runnable` chưa được xử lý. B có thể **chưa chạy và chưa được future đánh dấu done**.

### Ví dụ deterministic với latch

~~~java
package com.example.shop.testing;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.jupiter.api.Test;

class QueuedTaskShutdownTest {

    @Test
    void forced_shutdown_discards_queued_work() throws Exception {
        var pool = Executors.newSingleThreadExecutor();
        var started = new CountDownLatch(1);
        var release = new CountDownLatch(1);
        var queuedRan = new AtomicBoolean(false);

        Future<?> active = null;
        Future<?> queued = null;

        try {
            active = pool.submit(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });

            assertThat(started.await(2, TimeUnit.SECONDS))
                    .isTrue();

            queued = pool.submit(() ->
                    queuedRan.set(true));

            var notStarted = pool.shutdownNow();

            assertThat(notStarted).hasSize(1);
            queued.cancel(false);

            assertThat(pool.awaitTermination(
                    2, TimeUnit.SECONDS))
                    .isTrue();

            assertThat(queuedRan.get()).isFalse();
            assertThat(queued.isCancelled()).isTrue();
        } finally {
            release.countDown();

            if (active != null) {
                active.cancel(true);
            }
            if (queued != null) {
                queued.cancel(false);
            }

            pool.shutdownNow();

            assertThat(pool.awaitTermination(
                    2, TimeUnit.SECONDS))
                    .isTrue();
        }
    }
}
~~~

### Những mốc cần phân biệt

- `shutdownNow()` có thể trả danh sách task queued, không chứng minh task active đã kết thúc.
- Future của task đã bị lấy khỏi queue có thể cần **cancel rõ** để `get()` không tiếp tục chờ.
- Queue length bằng 0 sau shutdown không chứng minh listener/broker ở hệ thống khác đã xong.
- Dùng `started.await(...)` để chắc chắn A chiếm worker trước khi submit B; không dùng `Thread.sleep` để đoán.
- Đoạn này dùng **test-owned executor**; không force shutdown executor của Spring Modulith và làm rơi event nghiệp vụ.

Nếu test dùng một scheduling implementation khác hoặc có nhiều worker, kết quả danh sách queued có thể khác; hãy kiểm thử đúng contract của executor được dùng và không suy diễn một thứ tự không được đảm bảo.

## 24. Future exception khác lifecycle termination

Pool có thể terminate hoàn toàn dù một task đã fail:

~~~java
ExecutorService pool =
        Executors.newSingleThreadExecutor();

try {
    Future<?> failed = pool.submit(() -> {
        throw new IllegalStateException("Simulated failure");
    });

    assertThatThrownBy(() ->
            failed.get(2, TimeUnit.SECONDS))
            .isInstanceOf(ExecutionException.class)
            .hasCauseInstanceOf(IllegalStateException.class);
} finally {
    ExecutorCleanup.stopOwned(
            pool,
            Duration.ofSeconds(1),
            Duration.ofSeconds(2));
}
~~~

Cần imports `ExecutionException` và static AssertJ `assertThatThrownBy`. `submit(...)` có thể giữ exception trong Future; nếu test không gọi `get` hoặc có failure observation khác, exception không tự biến thành assertion failure.

| Assertion | Chứng minh | Không chứng minh |
| --- | --- | --- |
| `future.get` trả kết quả đúng | Task được Future đại diện đã xong bình thường | Executor terminated |
| `future.get` ném `ExecutionException` | Task fail và lỗi được quan sát | Cleanup đã chạy |
| `pool.awaitTermination` true | Không còn task chạy trong pool đã shutdown | Business side effect hợp lệ |
| Public consumer query `READY` | Side effect phía consumer đã commit/visible | Pool global đã shutdown |
| Publication registry completed | Handler được ghi nhận xử lý theo registry | External provider đã hoàn thành job |

Một bài test hoàn chỉnh có thể cần **hai gate tách biệt**: functional outcome và lifecycle của pool do test sở hữu.

### Khi dùng execute thay vì submit

Exception của `Runnable` gửi bằng `execute(...)` có thể được báo bằng uncaught exception handler hoặc cơ chế của `TaskExecutor`. Với `@Async void`, Spring có async exception handling riêng theo cấu hình. Không giả định mọi exception sẽ quay lại producer thread; cần public outcome/error state, test-owned Future hoặc instrumentation thích hợp.

## 25. Failure protocol và việc giữ nguyên lỗi gốc

Một test timeout vì consumer chậm và teardown cũng thất bại vì owned executor không terminate:

~~~text
PRIMARY FAILURE:
  Fulfillment READY not observed after 10 s, orderId=...

CLEANUP FAILURE:
  Owned executor termination not observed after 2+2 s
  Worker: test-order-worker-1
~~~

**Cả hai đều quan trọng.** Đừng dùng `catch (Throwable ignored)` để bỏ qua một trong hai; không gọi `System.exit`/`Thread.stop` để che leak.

### Mẫu xử lý

- Business assertion ở test method.
- Owned executor cleanup ở `finally`/`@AfterEach`.
- Throw rõ tên pool, thread, deadline khi cleanup không đạt.
- Lưu ID, last known business state, task exception, registry pending trước destructive cleanup.
- Nếu tự catch lỗi rồi rethrow, giữ exception gốc; có thể gắn cleanup failure bằng `addSuppressed`.
- Không chờ vô hạn trong `@AfterEach`, ngay cả khi test chính fail.

### JUnit @Timeout chỉ là outer guard

~~~java
@Test
@Timeout(value = 20, unit = TimeUnit.SECONDS)
void must_finish_before_test_deadline() {
    // Awaitility có thể atMost(10s).
    // Cleanup của owned executor cần deadline riêng.
}
~~~

`@Timeout` không tự hủy tất cả work đang chạy trong Spring executor hoặc DB. Cấu hình per-call HTTP/JDBC timeout khi có blocking I/O; đừng kỳ vọng interrupt JUnit sẽ làm một network request ngừng tức thời.

### Interruption giữa cleanup

Khi thread cleanup bị `InterruptedException`, hãy gửi force shutdown cho owned pool và khôi phục interrupt flag. Nếu chưa xác minh termination, giữ failure/diagnostic; không ghi "cleanup complete" chỉ vì đã gọi `shutdownNow()`.

## 26. Parallel tests và pool dùng chung

Giả sử Test A và Test B cùng dùng Spring cached context:

~~~mermaid
flowchart TD
    A["Test A publish OrderPlaced(A)"] --> E["Shared Spring executor"]
    B["Test B publish OrderPlaced(B)"] --> E
    E --> LA["Listener for A"]
    E --> LB["Listener for B"]
    A --> X["Test A @AfterEach shutdown()"]
    X -. "Có thể làm B bị reject" .-> E
~~~

**Không đóng shared Spring executor sau Test A**: đó là resource có vòng đời context. Nếu Test A sử dụng `@DirtiesContext` không phù hợp, context có thể đóng khi Test B đang dựa vào nó hoặc khi worker còn chạy.

| Resource | Scope cleanup |
| --- | --- |
| Executor tạo trong mỗi method | Method-scoped `@AfterEach` hoặc `finally` |
| Executor tạo trong `@BeforeAll` | `@AfterAll`, sau toàn class |
| Spring executor cached context | ApplicationContext lifecycle |
| Latch/gate test-specific | Release theo correlation ID trong `finally` |
| Shared H2/PostgreSQL fixture | Không `deleteAll()` khi workers/tests khác còn dùng |
| Persistent event publication registry | Theo recovery/retention policy, không xóa bừa |
| External sandbox resource | Tenant/run ID và business compensation nếu được hỗ trợ |

### Tránh các trường static mutable

Nếu một test dùng `static Future<?> currentFuture` rồi các methods chạy song song, một cleanup có thể cancel future của test khác. Dùng field per-instance, fixture-scoped registry hoặc khóa/serialization cho resource dùng chung.

Một môi trường không có isolation đủ tốt nên giảm parallelism cho các reliability tests, thay vì shutdown executor toàn context để “bảo đảm không ai còn chạy”.

## 27. Testcontainers: container và executor phải cùng đúng lifecycle

Khi consumer T2 ghi PostgreSQL, lỗi teardown có thể xảy ra:

~~~mermaid
sequenceDiagram
    participant T as JUnit
    participant W as Fulfillment listener
    participant DB as PostgreSQL container
    participant CL as Teardown

    T->>W: Trigger OrderPlaced
    T-->>T: Await timeout
    T->>CL: End class/context
    CL->>DB: Stop DB
    W->>DB: INSERT/COMMIT
    DB-->>W: Connection closed
~~~

Khung cấu hình production-like:

~~~java
package com.example.shop;

import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class FulfillmentPostgresIntegrationTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    // Inject OrderCommands + FulfillmentQueries;
    // chờ outcome READY từ T2.
}
~~~

Cần Spring Boot Testcontainers, Testcontainers Jupiter/PostgreSQL, driver và container runtime. `@ServiceConnection` được hỗ trợ từ Spring Boot 3.1+, nên dùng stack tương thích.

### Những timeout khác nhau

- Container image pull/start/readiness budget.
- Spring context/bootstrap và migration.
- Awaitility chờ business side effect sau T1 commit.
- JUnit method timeout.
- Context/executor/container shutdown budget.
- CI job wall-clock timeout.

**Không sửa container lifecycle bằng cách tăng Awaitility**, cũng không sửa listener transaction bằng cách gọi `shutdownNow()`.

Spring TestContext cache có thể tái sử dụng context khi Testcontainers class-scoped container đã dừng. Phải chọn scope nhất quán; recovery test cần storage tồn tại qua restart để kiểm chứng durable publication.

## 28. Event Publication Registry khác executor idle

Spring Modulith hỗ trợ Event Publication Registry cùng các persistence adapters để theo dõi xử lý sự kiện. Khi listener gặp lỗi:

~~~text
OrderPlaced recorded
  -> executor schedules listener
  -> handler T2 fails
  -> publication may remain pending
  -> executor pool becomes idle
  -> resubmit/recovery may be needed later
~~~

**Idle không đồng nghĩa event đã được xử lý xong.** Một pool có thể rỗng queue nhưng publication vẫn pending.

| Tín hiệu | Có thể khẳng định | Không được khẳng định |
| --- | --- | --- |
| `PublishedEvents` chứa event | Producer đã publish | Consumer T2 đã commit |
| `executor.isTerminated()` | Pool đã shutdown và kết thúc | Event registry empty |
| Active count 0 | Tại thời điểm đo ít active workers | Không có retry/scheduled work về sau |
| Registry pending | Publication chưa completed theo adapter | Business terminal FAILED |
| Registry completed | Xử lý xong theo semantics registry | External async job đã DONE |
| Fulfillment READY | Task đúng ID visible | Mọi replay/duplicate đều đã quiescent |

### Reliability test độc lập

1. Cấu hình registry persistence đúng dependency/version.
2. Commit producer và inject listener failure.
3. Quan sát pending publication.
4. Giữ storage khi restart/resubmit.
5. Gỡ failure, kích hoạt recovery bằng cơ chế được hỗ trợ.
6. Await business state terminal đúng ID.
7. Xác nhận idempotency và registry trạng thái cuối.

Đừng xóa pending publication để test suite “sạch”; đó có thể chính là dữ liệu cần kiểm chứng recovery. Không tự giả định retry vô hạn hay exactly-once semantics chỉ vì dùng `@ApplicationModuleListener`.

## 29. Shutdown ordering và quyền sở hữu business state

Một ứng dụng có thể cần graceful shutdown khi triển khai, nhưng lifecycle của Spring context không tự tạo bằng chứng mọi external job đã xong.

### Hai bài test khác nhau

**Business completion test:**

~~~text
Producer T1 commit
  -> @ApplicationModuleListener chạy trong T2
  -> Public query fulfillment trả READY
  -> Test pass; Spring executor có thể vẫn alive/cached
~~~

**Executor shutdown contract test:**

~~~text
Isolated context tạo ThreadPoolTaskExecutor
  -> Submit controlled task
  -> Context close/shutdown
  -> Await pool terminated
  -> Test pass; không cần giả vờ đã kiểm tra delivery nghiệp vụ
~~~

Không thể thay kiểm tra thứ nhất bằng thứ hai. Một pool terminated có thể từng chạy handler ném exception và rollback. Cũng không thể thay kiểm tra thứ hai bằng thứ nhất: task READY không tự làm pool stop.

### Các giai đoạn graceful shutdown điển hình

1. Không nhận request/command mới hoặc chuyển readiness theo deployment policy.
2. Ngừng tạo thêm công việc có thể bị mất theo hợp đồng.
3. Đợi in-flight listeners xử lý tới commit/rollback an toàn với deadline.
4. Giữ pending event publications để recovery nếu có registry persistent.
5. Đóng executor/application context theo chính sách.
6. Đóng DataSource/container sau khi không còn writer thuộc lifecycle cần xử lý.
7. Kiểm tra tài nguyên thật sự terminated; nếu không, báo lỗi/diagnostic.

Đây là **khung thiết kế**, không phải trình tự Spring Boot/Modulith tự bảo đảm trong mọi phiên bản. Với một test method bình thường, chỉ thực hiện phần liên quan đến **outcome của chính test**, không shutdown cả ứng dụng.

### Quiescence khác termination

- **Quiescence** có thể nghĩa không còn task nghiệp vụ của *một workflow* đang xử lý hoặc chờ retry, tùy contract.
- **Termination** nghĩa executor sau shutdown không còn worker đang chạy.
- Một Spring executor có thể quiescent nhưng vẫn alive để nhận event mới.
- Một executor terminated vẫn có thể để lại publication pending hoặc external job chưa xong.

Một cleanup muốn xóa fixture phải xem **quiescence theo workflow** nếu sự kiện có replay, không chỉ kiểm tra active count của pool tại một thời điểm.

## 30. Architectural verification bảo vệ ranh giới khác với cleanup

Spring Modulith kiểm chứng kiến trúc thông qua `ApplicationModules`. Dù executor được shutdown đúng, module consumer vẫn có thể vi phạm encapsulation bằng cách truy cập repository `internal` của producer.

Đúng:

~~~java
import com.example.shop.orders.OrderPlaced;
~~~

Sai trong thiết kế public API mặc định:

~~~java
import com.example.shop.orders.internal.persistence.OrderRepository;
~~~

Bài test kiến trúc:

**`src/test/java/com/example/shop/ModuleArchitectureTest.java`**

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTest {

    @Test
    void verifies_module_boundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

`verify()` kiểm tra các quy tắc như vòng phụ thuộc, truy cập ngoài API module và whitelist allowed dependencies khi khai báo. Nó **không** chạy listener để xác minh T2 commit, cũng không khởi động rồi shutdown executor.

Khi `fulfillment` chỉ được phụ thuộc `orders`, có thể khai báo có chủ đích trong `fulfillment/package-info.java`:

~~~java
@ApplicationModule(allowedDependencies = "orders")
package com.example.shop.fulfillment;

import org.springframework.modulith.ApplicationModule;
~~~

Không mở whitelist cho mọi module chỉ để test architecture xanh. Chiều import Java `fulfillment → orders.OrderPlaced` và chiều nghiệp vụ event `orders → fulfillment` cần được phân biệt.

## 31. Quality gate CI: functional, lifecycle và architecture

~~~mermaid
flowchart LR
    PR["Pull request"] --> U["Unit + owned executor cleanup"]
    U --> A["ApplicationModules.verify()"]
    A --> PUB["Producer module tests"]
    PUB --> CON["Consumer after-commit tests"]
    CON --> LIFE["Isolated Spring executor lifecycle"]
    LIFE --> REL["Retry / registry / Testcontainers"]
    REL --> HTTP["Critical HTTP E2E"]
    HTTP --> G{"Mọi gate bắt buộc đạt?"}
    G -- "Có" --> OK["Merge / release"]
    G -- "Không" --> ERR["Điều tra và sửa"]
~~~

| Gate | Mệnh đề bảo vệ | Oracle |
| --- | --- | --- |
| Unit executor | Owned pool sạch trên success/failure | `awaitTermination(...) == true` |
| Graceful/forced shutdown | Queue, active worker và rejection theo policy | Future state + pool termination |
| Spring executor lifecycle | Bean cleanup khi isolated context close | `isTerminated()` |
| `ApplicationModules.verify()` | Dependency/public API hợp lệ | Architecture verification pass |
| `@ApplicationModuleTest` + `PublishedEvents` | Producer phát đúng event | Event type, payload, correlation |
| Consumer integration | Listener T2 tạo business effect | Public query READY theo ID |
| Retry/idempotency/registry | Event không mất/không double effect theo policy | State + publication registry |
| Testcontainers | Isolation/constraint/transaction production-like | DB assertions, không lifecycle race |
| HTTP E2E | Client nhận kết quả terminal | Poll status theo API contract |

### Theo dõi trong CI

- Test fork bị treo vì non-daemon executor leak.
- Tỷ lệ `awaitTermination` timeout.
- Thread names và stack traces khi shutdown không kết thúc.
- Listener exceptions và rejected task count.
- Pending publication/retry attempts.
- Time-to-READY và business timeout rate.
- Context cache hit/miss; số lần `@DirtiesContext` gây cold startup.
- Container startup/readiness time và DB pool wait time.

**Đừng lấy tổng thời gian CI job làm độ trễ riêng của consumer.** Cũng đừng tăng deadline vô hạn để che leak.

### Negative controls

Trong nhánh thực hành có kiểm soát:

1. Bỏ cleanup owned executor → lifecycle test phải phát hiện leak/thiếu termination.
2. Cho worker nuốt interruption → forced shutdown test phải báo failure có deadline.
3. Bỏ `@ApplicationModuleListener` → producer có thể xanh, consumer integration phải đỏ.
4. Bỏ `publishEvent(...)` → producer module test phải đỏ.
5. Thêm import `orders.internal` trong consumer → architecture test phải đỏ.
6. Cố ý gây lỗi DB constraint → integration/Testcontainers test phải đỏ.
7. Đóng shared Spring executor ở `@AfterEach` → test khác có thể gặp rejection; hoàn nguyên ngay vì đây là phản mẫu.

Không giữ negative controls làm suite đỏ vĩnh viễn. Dùng chúng để xác nhận rằng mỗi gate thực sự chặn lỗi đúng loại.

## 32. Troubleshooting executor cleanup theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Điều tra/khắc phục |
| --- | --- | --- |
| JVM test fork không thoát | Pool test-owned chưa shutdown | Truy nguồn `Executors.new*`, thread names |
| `isShutdown() == true` nhưng thread còn | Task graceful drain | Await termination với deadline |
| `shutdownNow()` vẫn không dừng | Worker ignore interrupt hoặc block I/O | Interrupt points, per-call timeout |
| `Future.isCancelled()` true nhưng worker còn log | Future state không đại diện quiescence | Worker exit signal, pool termination |
| `CompletableFuture.cancel(true)` không ngắt | Cancellation semantics khác FutureTask | Cooperative token + termination |
| Queue size 0 nhưng active còn | Task đã dequeue và đang chạy | In-flight count, await termination |
| Test B bị `RejectedExecutionException` | Test A shutdown shared Spring executor | Sửa owner, không shutdown per-method |
| Spring context cached nhưng container stop | Cache/container lifecycle lệch | Align test fixture lifecycle |
| Producer test xanh, consumer không có task | `PublishedEvents` không chờ listener | Chạy consumer integration |
| Business task READY, registry vẫn pending | Duplicate/retry hoặc registry state lỗi | Reliability test, idempotency |
| Consumer test luôn timeout | Outer `@Transactional` rollback T1 | Cho producer commit thật |
| Test sau thấy row của test trước | Cleanup khi worker còn retry | Correlation ID, isolation/quiescence |
| Teardown failure che assertion gốc | Xử lý exception không giữ cause | JUnit reporting/suppressed |
| `@DirtiesContext` làm listener lỗi | Context close khi task còn dùng resource | Chờ completion, review shutdown policy |
| Architecture verification fail dù E2E xanh | Import implementation ngoài API | Sửa phụ thuộc, giữ `verify()` |

### Thứ tự điều tra

1. Executor này do ai tạo và ai có quyền shutdown?
2. Task thuộc test hay application event infrastructure?
3. Pool mới `shutdown` hay đã `terminated`?
4. Có task queued, active hoặc rejection không?
5. Future đã complete normally, exceptionally hay cancelled?
6. Worker có hợp tác interruption?
7. Context được cache hay đã đóng?
8. DataSource/container còn sống tới khi T2 commit không?
9. Có pending publication/retry chưa được xử lý?
10. Root failure và cleanup failure có được báo đầy đủ?
11. Mệnh đề business test và architecture test có được kiểm tra độc lập?

Không sửa bằng `Thread.sleep(30_000)` hoặc `Thread.stop()`.

## 33. Bài thực hành

### Bài A — Executor per-method

Tạo `ExecutorService` ở `@BeforeEach`, submit task trả `42` và dọn trong `@AfterEach` bằng `ExecutorCleanup.stopOwned`. Cho test assertion thất bại; cleanup vẫn phải chạy.

### Bài B — Graceful shutdown

Dùng latch cho worker đang chạy. Gọi `shutdown()`, kiểm tra `isShutdown()` true nhưng `isTerminated()` có thể false. Release latch và `awaitTermination`. Giải thích tại sao không cần force khi task hợp tác.

### Bài C — Forced shutdown

Cho worker đang chờ interruptible latch, gọi `shutdownNow()` sau grace deadline. Kiểm tra nó dừng và `finally` chạy, không chỉ dựa vào return value `shutdownNow()`.

### Bài D — Task bị bỏ trong queue

Chạy `QueuedTaskShutdownTest`, quan sát danh sách queued chưa start. Giải thích vì sao Future của queued task cần được reconcile/cancel. Không dùng `sleep` thay `started` latch.

### Bài E — Future kết thúc nhưng executor còn sống

Dùng `Future.get` thành công rồi kiểm tra `isShutdown()` false trước cleanup. Tách assertion correctness khỏi resource lifecycle.

### Bài F — CompletableFuture cancellation

Tạo `CompletableFuture.runAsync` trên pool do test sở hữu. Yêu cầu cancel rồi dùng worker-exit signal riêng. Giải thích vì sao `isCancelled()` không tự chứng minh underlying action dừng.

### Bài G — Isolated Spring context

Chạy `IsolatedSpringExecutorShutdownTest`, thay đổi grace/termination settings và đo behavior. Không dùng `@AfterEach` để shutdown bean executor của một `@SpringBootTest` dùng chung.

### Bài H — Spring Modulith producer/consumer

Chạy `@ApplicationModuleTest` với `PublishedEvents` và full integration Awaitility theo `orderId`. Tạm bỏ listener: producer test có thể xanh nhưng consumer test phải đỏ.

### Bài I — Transaction rollback

Đặt outer `@Transactional` trong consumer integration rồi nhận diện vì sao `AFTER_COMMIT` không được kích hoạt. Khôi phục service commit thật.

### Bài J — Testcontainers và context cache

Dùng PostgreSQL Testcontainers kiểm tra constraint/isolation. Bảo đảm container lifecycle không dừng trước context/worker. Chạy riêng test recovery giữ registry storage qua restart.

### Bài K — Parallel test ownership

Chạy nhiều methods đồng thời, mỗi method có owned executor và UUID riêng. Xác nhận không có shutdown shared Spring executor hay cleanup dữ liệu test khác.

### Bài L — Quality gate CI

Đưa owned executor unit test, isolated Spring shutdown, producer module, consumer integration, architecture và reliability test vào CI. Ghi deadline riêng cho startup, business wait, shutdown và job.

### Câu hỏi tự đánh giá

1. `shutdown()` và `isTerminated()` khác nhau ra sao?
2. Vì sao `Future.get` thành công chưa dọn pool?
3. Khi nào dùng `shutdownNow()`?
4. Lệnh `shutdownNow()` có bảo đảm mọi thread dừng ngay không?
5. Vì sao queued Future có thể cần cancel sau khi bị loại khỏi queue?
6. `CompletableFuture.cancel(true)` có giống `FutureTask.cancel(true)` không?
7. Vì sao không shutdown Spring executor từ `@AfterEach`?
8. Khi nào cần `@AfterAll` thay vì `@AfterEach`?
9. Spring TestContext caching ảnh hưởng ownership thế nào?
10. `@DirtiesContext` có tự bảo đảm worker quiescent không?
11. `PublishedEvents` chứng minh điều gì?
12. Khi nào task READY nhưng registry vẫn pending?
13. Vì sao `getQueue().size() == 0` chưa chứng minh business completed?
14. DB Testcontainers và Spring context cache có thể lệch lifecycle ra sao?
15. `ApplicationModules.verify()` kiểm chứng điều gì khác consumer integration?
16. CI phải làm gì nếu cleanup failure xảy ra cùng assertion failure?

## 34. Checklist bảo đảm executor được dọn đúng

- [ ] Đã xác định pool là method-, class-, suite- hay Spring-context-owned.
- [ ] Chỉ shutdown executor mà test thật sự sở hữu.
- [ ] Per-method owned pool được cleanup ở `finally` hoặc `@AfterEach`.
- [ ] Per-class owned pool được cleanup sau toàn class, không từ mỗi method.
- [ ] Graceful `shutdown()` được ưu tiên khi còn task cần xử lý.
- [ ] Có `awaitTermination` với deadline hữu hạn.
- [ ] Khi quá grace period, có `shutdownNow()` và await tiếp có giới hạn.
- [ ] Không coi return từ `shutdownNow()` là chứng cứ termination.
- [ ] Có failure khi pool không terminate, không swallow exception.
- [ ] Worker có cancellation/interruption point hợp tác.
- [ ] `CompletableFuture.isCancelled()` không bị nhầm với worker exited.
- [ ] Future task exceptions được quan sát khi cần.
- [ ] Queued tasks bị trả ra khi force shutdown được reconcile.
- [ ] Không dùng queue/active count snapshot làm oracle duy nhất.
- [ ] Thread names/correlation IDs đủ để chẩn đoán leak.
- [ ] Không tắt Spring-managed executor trong per-method teardown.
- [ ] Spring executor shutdown policy và context lifecycle được review.
- [ ] `@DirtiesContext` không được dùng thay completion barrier.
- [ ] `@ApplicationModuleTest` chỉ kiểm tra producer publication.
- [ ] Consumer integration chờ side effect đã commit đúng ID.
- [ ] Outer test transaction không rollback flow AFTER_COMMIT ngoài ý muốn.
- [ ] Fixture cleanup không xóa dữ liệu khi worker còn retry.
- [ ] Testcontainers lifecycle tương thích cached Spring context.
- [ ] Pending publications được giữ cho recovery khi cần.
- [ ] Parallel tests không chia sẻ mutable executor handles không an toàn.
- [ ] Architecture gate `ApplicationModules.verify()` vẫn chạy.
- [ ] CI có báo cáo cả business failures và executor cleanup failures.

## 35. Ghi nhớ

**Đảm bảo executor được làm sạch sau test** là kiểm chứng một **vòng đời tài nguyên có chủ sở hữu**, không phải việc shutdown mọi thread nhìn thấy trong JVM. Với pool do test tạo, cần `shutdown()`, `awaitTermination`, escalation `shutdownNow()` khi phù hợp và báo failure nếu worker vẫn không ngừng. `Future.get` thành công không tự shutdown pool; `isShutdown` không đồng nghĩa `isTerminated`; `CompletableFuture.cancel` không tự chứng minh underlying action đã dừng.

Với Spring Modulith, executor của `@ApplicationModuleListener` thông thường thuộc Spring ApplicationContext và có thể phục vụ nhiều test qua context cache. **Không đóng nó trong `@AfterEach` của một method.** Hãy chờ business side effect sau commit qua public module API bằng Awaitility; nếu cần kiểm tra shutdown semantics, dùng Spring context cô lập. Kết hợp `@ApplicationModuleTest` + `PublishedEvents`, consumer integration/reliability, Testcontainers và `ApplicationModules.verify()` trong quality gate CI để ngăn **thread leak, cleanup race, event bị bỏ dở và phụ thuộc module sai**.



