# Giới hạn của executor đồng bộ khi cần chứng minh hành vi đồng thời trong Spring Boot Test

## 1. Tình huống: test xanh nhưng ứng dụng vẫn hỏng khi hai tác vụ chạy cùng lúc

Một ứng dụng Spring Boot gửi email, tính toán tồn kho, cập nhật trạng thái đơn hàng hoặc thực hiện background job thông qua `TaskExecutor`, `@Async` và đôi khi cả `@Scheduled`. Để test chạy nhanh, dễ dự đoán, lập trình viên thường thay executor thật bằng **`SyncTaskExecutor`**. Executor này gọi `Runnable.run()` **ngay trên thread đã gọi `execute`** và chỉ trả quyền điều khiển khi tác vụ hoàn thành. Cách thay thế đó hữu ích để kiểm một số chức năng **tuần tự**, nhưng có một giới hạn nghiêm trọng: nó **không tạo ra hai tác vụ đang chạy đồng thời** nếu hai lệnh submit được thực hiện tuần tự từ một caller.

Vì vậy một test như sau có thể xanh dù ứng dụng thực tế có race condition:

~~~java
TaskExecutor executor = new SyncTaskExecutor();

executor.execute(() -> orderService.reserve("SKU-1"));
executor.execute(() -> orderService.reserve("SKU-1"));

assertEquals(2, processedCount.get());
~~~

Đây là **snippet ý tưởng**, chưa định nghĩa `orderService` và `processedCount`. Với `SyncTaskExecutor`, lệnh reserve thứ nhất **kết thúc hẳn** trước khi submit lần thứ hai, nên kết quả chỉ kiểm đúng *thực thi nối tiếp*. Nó **không chứng minh** rằng hai request cùng lúc không làm trùng đơn, không mất update hoặc không vi phạm giới hạn tồn kho.

**Chủ đề chính:** *“Giới hạn của executor đồng bộ khi cần chứng minh hành vi đồng thời”* trong nhóm **“Bất đồng bộ và lịch chạy”** của Spring Boot testing.

**Những kiến thức phải nắm:**

1. Hiểu `SyncTaskExecutor.execute(...)` là **synchronous execution**, không đồng nghĩa asynchronous/concurrent.
2. Phân biệt **synchronous**, **asynchronous**, **concurrent**, **parallel**, **overlapping/in-flight**, **deterministic** và **thread-safe**.
3. Biết tại sao việc dùng `SyncTaskExecutor` để test callback, exception và dữ liệu cuối cùng **có giá trị**, nhưng không chứng minh race freedom, pool rejection, lock contention hay scheduling overlap.
4. Phân biệt `@Async` annotation và **executor thực được chọn**; `@Async("syncProofExecutor")` vẫn có thể chạy ngay trên caller thread.
5. Biết cần đi **qua Spring proxy** để `@Async` có hiệu lực; self-invocation có thể bỏ qua async advice.
6. Chọn `ThreadPoolTaskExecutor` với ít nhất **hai workers** để chứng minh hai tác vụ **cùng đang hoạt động trước khi được giải phóng**.
7. Viết test dùng **`CountDownLatch`**, `CompletableFuture`, `AtomicInteger` và timeout hữu hạn, tránh `Thread.sleep(...)` như bằng chứng concurrency.
8. Test cả negative control **pool chỉ một thread** để thấy vì sao một gate đòi hai arrivals không thể hoàn thành.
9. Kiểm thread identity, trạng thái Future, exception propagation, queueing, rejection, cleanup và `@Async` qualification.
10. Hiểu tác động của `ThreadLocal`, Spring test transaction, security context/MDC, `@Scheduled`, thread pools và các cơ chế async khác.
11. Tạo project **Java 17 + Spring Boot 3.3.5 + Gradle** với **16 phương thức kiểm thử JUnit Jupiter** chia thành ba lớp.
12. Phân biệt điều gì test đã chứng minh và điều gì vẫn cần **stress testing, race detection, persistence tests** hoặc kiểm scheduling thực.

**Phiên bản bài học:** Java 17, Spring Boot **3.3.5**, Spring Framework **6.1.x**, Gradle và JUnit Jupiter. Ví dụ chạy hoàn toàn trong JVM, **không cần Docker hoặc external services**. Nếu ứng dụng dùng Java 21 virtual threads, Spring Boot 3.4/3.5/4.x hoặc một executor khác, phải đọc API tương ứng trước khi chuyển cấu hình.

## 2. Năm khái niệm rất hay bị gộp nhầm

| Khái niệm | Ý nghĩa chính | Có chứng minh hai job chạy chồng nhau? |
|---|---|---|
| **Synchronous call** | Caller chờ công việc xong rồi tiếp tục | Không |
| **Asynchronous call** | Gọi công việc mà caller có thể tiếp tục trước khi công việc kết thúc | Không tự động: có thể chỉ một worker hoặc hoàn tất quá nhanh |
| **Concurrency** | Nhiều công việc cùng có tiến độ trong khoảng thời gian quan sát, có thể xen kẽ | Có thể, nhưng phải kiểm thời điểm/overlap |
| **Parallelism** | Nhiều công việc thực thi đồng thời thật trên tài nguyên tính toán, thường ở nhiều cores | Cần bằng chứng mạnh hơn việc có hai threads |
| **Thread safety** | Kết quả/điều kiện đúng dưới các interleavings cho phép | Không thể suy ra chỉ từ một lần quan sát overlap |

Một `ThreadPoolTaskExecutor` có hai worker *cho phép* hai callbacks đang hoạt động tại cùng thời điểm, nhưng không tự đảm bảo mọi lần submit sẽ overlap. Ngược lại, `SyncTaskExecutor` chỉ thực thi một callback trên caller thread tại một thời điểm nếu caller gọi hai lệnh liên tiếp; nó không tạo thread mới, không tạo background queue và không xác nhận bất kỳ interleaving nào giữa hai task.

**Điểm tinh tế:** `SyncTaskExecutor` **không biến một ứng dụng nhiều threads thành toàn bộ single-threaded**. Nếu hai caller threads khác nhau cùng gọi **chính cùng một SyncTaskExecutor**, mỗi callback chạy trên thread của caller tương ứng và **vẫn có thể đồng thời**. Giới hạn cần phát biểu chính xác là: **nó không cung cấp concurrency qua một chuỗi submit tuần tự từ một caller**, chứ không bảo đảm không bao giờ tồn tại concurrency ở mọi hoàn cảnh.

Ví dụ:

~~~text
Trường hợp A — một test caller T0:
T0: execute(task A) ---> task A xong
T0: execute(task B) -----------------> task B xong
Không có overlap A/B do executor tạo ra.

Trường hợp B — hai caller khác nhau:
T1: execute(task A) ------------>
T2:     execute(task B) ------------->
Hai tasks có thể overlap, nhưng concurrency đến từ T1/T2,
không phải từ khả năng lập lịch của SyncTaskExecutor.

Trường hợp C — T0 submit vào thread pool hai workers:
T0: execute(A) -> trả về
T0: execute(B) -> trả về
W1: task A ====== chờ gate ====== tiếp tục
W2: task B ====== chờ gate ====== tiếp tục
Hai tasks in-flight cùng lúc; test có thể kiểm bằng latch.
~~~

**Không dùng số lượng lệnh `execute` làm số lượng threads.** Hai lần gọi `execute` của sync executor có thể chỉ dùng một thread, và hai calls của pool executor cũng có thể bị queue tuần tự nếu pool chỉ có một worker.

## 3. `SyncTaskExecutor` thật sự làm gì?

Trong Spring Framework 6.1, `org.springframework.core.task.SyncTaskExecutor` là một `TaskExecutor` triển khai `java.util.concurrent.Executor` và thực thi bằng cách **gọi trực tiếp `Runnable.run()` trên thread hiện tại**.

Bản rút gọn về mặt ý nghĩa:

~~~java
final class ConceptualInlineExecutor implements java.util.concurrent.Executor {
    @Override
    public void execute(Runnable command) {
        command.run(); // Không start Thread mới, không enqueue.
    }
}
~~~

**Đây là lớp khái niệm**, không phải source được sử dụng trong project ở mục 7. Thư viện Spring đã có `SyncTaskExecutor`; ta không cần tự chép một executor thay thế.

Hệ quả trực tiếp:

- **Thread identity:** Bên trong task, `Thread.currentThread()` là chính thread gọi `execute(...)`.
- **Đồng bộ thời điểm:** Sau khi `execute(...)` trả về bình thường, callback đã chạy xong; không phải chờ Future/latch để biết callback kết thúc.
- **Exception propagation:** Với lời gọi `execute` trực tiếp, unchecked exception từ callback có thể được ném ra **ngay tại lệnh execute của caller**. Điều này khác việc submit một `Callable` vào thread pool rồi kiểm `Future.get()`.
- **ThreadLocal:** Context gắn với calling thread như ThreadLocal tùy biến, MDC hoặc transaction association có thể **hiện diện** trong callback vì không hề đổi thread. Đây vừa là tiện lợi cho test tuần tự, vừa là **nguồn false confidence** khi production thực hiện task trên thread khác.
- **Không có background scheduling:** SyncTaskExecutor không có worker pool, queue capacity, thread pool starvation, task rejection do đầy queue, concurrency limit do worker count, hay race do bản thân nó tạo ra giữa hai sequential submits.
- **Blocking:** Nếu callback chờ một latch chỉ được một callback **đến sau** giải phóng, caller có thể bị kẹt trong callback đầu và không bao giờ submit được callback thứ hai. Đó là deadlock do thiết kế test, không phải cách chứng minh concurrency.

Ví dụ thấy rõ thứ tự:

~~~java
List<String> events = new ArrayList<>();
TaskExecutor sync = new SyncTaskExecutor();

events.add("before");
sync.execute(() -> events.add("inside"));
events.add("after");

assertEquals(
        List.of("before", "inside", "after"),
        events);
~~~

Đây là **snippet trong một JUnit test** với imports `java.util.List`, `java.util.ArrayList`, `TaskExecutor`, `SyncTaskExecutor` và assertions; bản hoàn chỉnh nằm ở mục 8.

**Vì sao Spring dùng nó cho test?** Một test chỉ muốn chắc listener/callback được gọi, exception được ném, hoặc state cuối cùng đúng có thể cần **tính xác định** hơn là thread hopping. Dùng sync executor là cách giảm biến thiên môi trường cho **mục tiêu tuần tự**. Không phải công cụ này “sai”; sai khi kết luận từ test tuần tự rằng code xử lý đúng khi nhiều worker cùng lúc.

## 4. `@Async` không đồng nghĩa luôn có thread khác

Spring hỗ trợ `@Async` qua `@EnableAsync` và interceptor/proxy. `@Async` có thể chỉ định tên executor:

~~~java
@Async("syncProofExecutor")
public CompletableFuture<String> runWithSyncExecutor() {
    return CompletableFuture.completedFuture(
            Thread.currentThread().getName());
}
~~~

Snippet này là một method trong Spring-managed bean, không phải file độc lập. Nếu `syncProofExecutor` là `SyncTaskExecutor`, method body vẫn được executor thực thi **trên caller thread**, cho dù annotation tên là “Async”. Spring có thể bọc kết quả bằng Future/CompletableFuture nhưng việc đó không tự tạo concurrency.

Với:

~~~java
@Async("parallelProofExecutor")
public CompletableFuture<String> runWithPool() {
    return CompletableFuture.completedFuture(
            Thread.currentThread().getName());
}
~~~

nếu `parallelProofExecutor` là `ThreadPoolTaskExecutor` có worker, Spring gửi invocation sang pool thread. Nhưng **Future có thể đã hoàn tất khi test đọc nó** nếu công việc nhanh. Do đó `future.isDone()` là **quan sát trạng thái hoàn thành tại một thời điểm**, không phải bài kiểm tra chắc chắn rằng executor có hoặc không có concurrency.

### 4.1. Qua proxy hay self-invocation?

**Có proxy:** test gọi `asyncService.runWithPool()` trên **bean do Spring inject**, nơi `@EnableAsync` đã bật và bean không bị bypass proxy. Spring async interceptor chọn executor đã nêu trong `@Async`.

**Không qua proxy:** một method trong cùng class gọi `this.runWithPool()`. Với proxy-based async của Spring, đây là **self-invocation**, interceptor không xử lý; method body có thể chạy ngay trên caller. Một test chỉ gọi self-invocation rồi kết luận `@Async` không hoạt động là kiểm sai đường thực thi.

### 4.2. `@Async` trả kiểu gì?

`@Async` method thường trả `void`, `Future<T>` hoặc `CompletableFuture<T>`. Khi muốn test completion và exception, **ưu tiên `CompletableFuture`** để có signal có thể quan sát. Với `void` async method, exception không được truyền trực tiếp tới caller; Spring dùng `AsyncUncaughtExceptionHandler` hoặc logging theo cấu hình.

Trong method thực thi, việc trả `CompletableFuture.completedFuture(value)` là hợp lệ: Spring interceptor có thể dùng kết quả đó để hoàn tất Future trả cho caller. **Chính executor, không phải từ khóa completedFuture, quyết định method body chạy ở thread nào**.

### 4.3. Spring Boot 3.3 chọn executor mặc định như thế nào?

Spring Framework `@EnableAsync` tìm một TaskExecutor phù hợp, hoặc `Executor` bean tên `taskExecutor` nếu cần; nếu không tìm được thì có fallback theo Framework. Spring Boot **3.3** còn auto-configure `AsyncTaskExecutor` khi không có custom executor, thường là `ThreadPoolTaskExecutor` ở Java 17. Nếu app định nghĩa custom `Executor` bean, auto-configuration có thể back off. Nếu có nhiều executor, lựa chọn mặc định cần được xác định theo bean type/names/`AsyncConfigurer`.

**Đừng đoán executor thật theo annotation `@Async` đơn lẻ.** Trong ví dụ, ta luôn ghi **`@Async("syncProofExecutor")`** hoặc **`@Async("parallelProofExecutor")`** để chọn đích rõ, không phụ thuộc default hoặc các beans khác. Không đặt tên một synchronous executor là `taskExecutor` trong application production rồi vô tình bắt mọi async task chạy inline.

## 5. Có thể chứng minh điều gì bằng một test executor đồng bộ?

| Mục tiêu kiểm thử | SyncTaskExecutor có phù hợp? | Giới hạn của bằng chứng |
|---|---|---|
| Callback được gọi và sửa state tuần tự | **Có** | Không chứng minh behavior với hai callbacks overlap |
| Thứ tự các callbacks từ cùng một caller | **Có**, nếu yêu cầu thực sự tuần tự | Không chứng minh scheduler/worker pool bảo toàn thứ tự đó |
| Chuyển đổi DTO, validation, domain logic thuần | **Có** | Đây không phải test concurrency |
| Exception khi `execute` trực tiếp | **Có** | Pool submit thường chuyển lỗi sang Future/callback |
| Code dựa vào ThreadLocal của caller | Có thể thấy giá trị | **Có nguy cơ che lỗi** khi production dùng worker |
| Queue capacity, backpressure, rejection | **Không** | Executor sync không có worker queue |
| Race condition/lost update giữa hai tasks | **Không** với sequential submits | Cần interleaving/concurrency thật |
| Lock contention hoặc deadlock giữa workers | **Không** với sequential submits | Cần ít nhất hai tasks thực sự in-flight |
| `@Async` có chạy trên thread khác không | **Không** nếu executor được thay sync | Cần real executor/proxy assertions |
| Throughput/latency của pool production | **Không** | Cần benchmark/load test theo workload |
| Hai `@Scheduled` invocations overlap | **Không** chỉ bằng thay task executor | Scheduler và trigger semantics phải kiểm riêng |
| Thread safety trên mọi interleaving | **Không** | Một test overlap chỉ chứng minh một kịch bản |

**Phải nêu phạm vi kết luận.** Test `assertEquals(2, processedCount)` sau hai lần chạy sync chứng minh callback logic cuối cùng tạo đúng 2 theo thứ tự đó. Nó **không** chứng minh atomic increment hoặc DB transaction isolation trong cạnh tranh.

**Một đối chứng rất hữu ích:** chạy cùng functional assertion với sync executor để đảm bảo logic cơ bản, rồi chạy **một test riêng** bằng pool thật có gate để ép overlap và kiểm invariant concurrency. Không thay tất cả tests bằng pool vì làm test logic thuần bị flaky không cần thiết; cũng không thay mọi test bằng sync vì vô tình bỏ trống một loại rủi ro quan trọng.

## 6. Phương pháp kiểm chứng overlap đúng

### 6.1. Dùng latch để xác lập điểm gặp nhau

Hai tasks phải:
1. Được submit vào executor thật có đủ workers.
2. Báo đã **đi vào vùng đang hoạt động** bằng `entered.countDown()`.
3. Chờ cùng một `release` latch để **cả hai vẫn in-flight** khi test thread kiểm trạng thái.
4. Test thread chờ `entered.await(timeout)`, xác nhận **đủ hai tasks đã bắt đầu và chưa kết thúc**.
5. Kiểm `maxInFlight == 2`, `!future1.isDone()` và `!future2.isDone()` khi gate chưa mở.
6. Trong `finally`, mở gate để **không kẹt worker** nếu assertion thất bại; dùng timeout cho Future.get.
7. Sau khi giải phóng, kiểm kết quả và mọi side effects.

~~~text
JUnit test thread T0           pool worker W1          pool worker W2
        |                            |                       |
        | submit task1  ---------->  | enter; active=1        |
        | submit task2  ----------------------------------->  | enter; active=2
        |                            | wait release           | wait release
        | await entered(2) ----------+-----------------------+
        | assert maxInFlight==2      |                       |
        | assert futures not done    |                       |
        | release.countDown() ------>+---------------------->+
        |                            | finish                | finish
        | get both futures ----------+-----------------------+
~~~

**Chứng minh được gì?** Hai tasks đã **đồng thời ở trạng thái in-flight trước khi hoàn tất**, có ít nhất một khoảng mà cả hai còn đang chờ. Nó là bằng chứng về **overlap** của hai task invocations trong setup này, **không chứng minh hai CPU cores đã cùng chạy instruction tại đúng một nanosecond** hoặc rằng code an toàn với mọi lịch chạy khả dĩ.

### 6.2. Vì sao không dùng `Thread.sleep(100)`?

~~~java
executor.execute(() -> {
    Thread.sleep(100); // Giả sử task B sẽ chen vào...
});
~~~

Đây là **snippet phản mẫu** và chưa xử lý checked exception. Scheduler/CPU/CI load có thể làm task B không chạy kịp trong khoảng ngủ; test có thể “thường xanh” nhưng không có ràng buộc quan hệ thứ tự. Latch/barrier tạo **điều kiện đồng bộ rõ ràng**; timeout trong `await(5, SECONDS)` chỉ là giới hạn chờ, không phải cơ chế tạo concurrency.

### 6.3. Vì sao không áp gate hai parties vào SyncTaskExecutor?

Nếu T0 gọi:

~~~java
sync.execute(() -> {
    entered.countDown();
    release.await(); // T0 bị chặn ở đây.
});
sync.execute(() -> {
    entered.countDown(); // Không bao giờ được submit từ T0.
});
~~~

Đây là **snippet cảnh báo**; chưa có imports và có `InterruptedException` cần xử lý. Callback đầu giữ caller T0 tại `await`; câu submit thứ hai không thể chạy. Một `CountDownLatch(2)` đang chờ đủ hai arrivals từ các tasks sẽ không đạt nếu T0 bị kẹt trước khi submit task thứ hai. Nếu không có timeout/cleanup, test có thể treo vô hạn.

**Không xem “latch không đếm đủ” là bằng chứng race/deadlock của ứng dụng.** Trong trường hợp này, deadlock do chính test dùng một executor inline cho một giao thức vốn đòi nhiều threads.

### 6.4. Dùng AtomicInteger để đếm in-flight

~~~java
int now = active.incrementAndGet();
maxActive.accumulateAndGet(now, Math::max);

try {
    // Chờ gate; giữ active > 0.
} finally {
    active.decrementAndGet();
}
~~~

`AtomicInteger` dùng trong **instrumentation của test** để không tự phát sinh data race khi đếm. `maxActive=2` cùng latch đã chứng minh overlap trong vùng được đánh dấu. **Không dùng chính atomic counter để giả vờ rằng business code không có race**: counter an toàn chỉ bảo vệ biến đo, không tự bảo vệ đơn hàng, inventory, cache hoặc transaction.

## 7. Project Spring Boot 3.3.5 / Java 17 có thể chạy

Ví dụ dựng:
- Một Spring Boot app nhỏ không có HTTP server.
- Hai executors có **bean names tường minh**: `syncProofExecutor` và `parallelProofExecutor`.
- Một **`OverlapGate`** an toàn cho tests; bảo đảm release kể cả khi assert fail.
- Một Spring-managed `AsyncProbeService` với cả hai kiểu `@Async` và một self-invocation.
- Ba lớp JUnit Jupiter với **16 tests**: 6 sync, 6 pool và 4 Spring async proxy.
- `junit-platform.properties` để không vô tình chạy các test classes song song và tranh pool 2 workers.

### 7.1. Cây tệp

~~~text
settings.gradle
build.gradle
src/main/java/demo/async/ExecutorProofApplication.java
src/main/java/demo/async/ProofExecutorConfiguration.java
src/main/java/demo/async/OverlapGate.java
src/main/java/demo/async/AsyncProbeService.java
src/test/resources/junit-platform.properties
src/test/java/demo/async/SyncTaskExecutorTest.java
src/test/java/demo/async/ThreadPoolTaskExecutorTest.java
src/test/java/demo/async/AsyncProxyIntegrationTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'spring-sync-executor-concurrency-proof'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-aop'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

Spring Boot starter cung cấp application context và logging; starter-aop bảo đảm Spring AOP proxy infrastructure cho các tests method interception; starter-test có JUnit Jupiter, Spring Boot Test và assertions. Bài không cần `spring-boot-starter-web`, DataSource hoặc RabbitMQ. Java 17 hỗ trợ records, lambdas và `CompletableFuture`. Spring Boot BOM giữ versions Spring Framework tương thích.

**src/test/resources/junit-platform.properties**

~~~properties
junit.jupiter.execution.parallel.enabled=false
~~~

Tệp này chỉ điều chỉnh JUnit Jupiter parallel execution của **tests**, không làm `ThreadPoolTaskExecutor` dừng chạy đồng thời bên trong một test. Thực tế production scheduler/worker threads vẫn chạy khi được submit; test ở mục 9 chủ động tạo overlap.

### 7.2. Main application

**src/main/java/demo/async/ExecutorProofApplication.java**

~~~java
package demo.async;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ExecutorProofApplication {

    public static void main(String[] args) {
        SpringApplication.run(ExecutorProofApplication.class, args);
    }
}
~~~

Không khởi động HTTP server vì không khai báo web starter. Trong `@SpringBootTest`, Spring tìm main application qua package hierarchy.

### 7.3. Cấu hình hai executors tách biệt

**src/main/java/demo/async/ProofExecutorConfiguration.java**

~~~java
package demo.async;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.SyncTaskExecutor;
import org.springframework.core.task.TaskExecutor;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class ProofExecutorConfiguration {

    @Bean("syncProofExecutor")
    public TaskExecutor syncProofExecutor() {
        // Runnable chạy ngay trong calling thread.
        return new SyncTaskExecutor();
    }

    @Bean("parallelProofExecutor")
    public ThreadPoolTaskExecutor parallelProofExecutor() {
        ThreadPoolTaskExecutor pool =
                new ThreadPoolTaskExecutor();

        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(2);
        pool.setQueueCapacity(0);
        pool.setThreadNamePrefix("parallel-proof-");

        pool.setWaitForTasksToCompleteOnShutdown(true);
        pool.setAwaitTerminationSeconds(10);

        // Spring khởi tạo/đóng bean theo lifecycle;
        // không cần gọi initialize() thủ công tại @Bean.
        return pool;
    }
}
~~~

**Vì sao pool có hai workers và `queueCapacity=0`?**
- Hai workers là điều kiện thực dụng để hai tasks có thể cùng chờ `OverlapGate`.
- `queueCapacity=0` tạo **SynchronousQueue** cho ThreadPoolTaskExecutor, tức không có hàng đợi lưu sẵn thêm tasks khi cả hai workers đều bận. Nếu submit task thứ ba trong lúc hai workers đang bị gate giữ, Spring sẽ từ chối bằng **`TaskRejectedException`** theo rejection policy mặc định. Điều đó hữu ích để học capacity/backpressure và ngăn tình trạng test vô tình có task thứ ba chờ không rõ.
- `corePoolSize=maxPoolSize=2` giới hạn kích thước pool trong ví dụ. **Không** chép cấu hình này vào production khi chưa phân tích I/O/CPU/backpressure.
- `ThreadPoolTaskExecutor` triển khai Spring lifecycle; trong @Bean thực tế Spring gọi initialization/destruction phù hợp. Các tasks của tests được release và `Future.get` trước khi context đóng.

**Không thay thế toàn bộ application executor bằng SyncTaskExecutor trong production.** Ví dụ tạo hai beans để so sánh trong cùng một project; mọi method `@Async` trong bài **chọn executor theo tên**, không dựa vào Boot default. Với ứng dụng thực có Spring MVC async, GraphQL hoặc WebFlux blocking support, Spring Boot còn có những yêu cầu riêng đối với bean `applicationTaskExecutor`; đừng đổi global bean sang SyncTaskExecutor chỉ để giảm độ flaky của test.

### 7.4. OverlapGate để xác minh đồng thời mà không dùng sleep

**src/main/java/demo/async/OverlapGate.java**

~~~java
package demo.async;

import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class OverlapGate {

    private final CountDownLatch entered;
    private final CountDownLatch release = new CountDownLatch(1);

    private final AtomicInteger active = new AtomicInteger();
    private final AtomicInteger peakActive = new AtomicInteger();

    public OverlapGate(int expectedArrivals) {
        if (expectedArrivals <= 0) {
            throw new IllegalArgumentException(
                    "expectedArrivals must be positive");
        }
        this.entered = new CountDownLatch(expectedArrivals);
    }

    public String enterAndAwaitRelease() {
        int currentlyActive = active.incrementAndGet();
        peakActive.accumulateAndGet(currentlyActive, Math::max);
        entered.countDown();

        try {
            // Timeout là safety net, không tạo concurrency.
            if (!release.await(15, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Gate was not released in time");
            }
            return Thread.currentThread().getName();
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                    "Interrupted while waiting for gate", ex);
        } finally {
            active.decrementAndGet();
        }
    }

    public boolean awaitAllEntered(Duration timeout)
            throws InterruptedException {
        return entered.await(
                timeout.toMillis(), TimeUnit.MILLISECONDS);
    }

    public int peakActive() {
        return peakActive.get();
    }

    public int active() {
        return active.get();
    }

    public void open() {
        release.countDown();
    }
}
~~~

**Tại sao code này ổn cho test?** `active` và `peakActive` là `AtomicInteger`, `entered` và `release` là `CountDownLatch` — mọi trạng thái đo được phối hợp bằng cơ chế thread-safe. Mỗi task báo arrived **trước** khi chờ release; test chờ cả hai arrived rồi assert chúng chưa kết thúc. Sau khi có signal, `CountDownLatch` cung cấp quan hệ **happens-before** giữa hành động trước countDown và hành động sau await thành công. `finally` trong method giảm active kể cả timeout/interrupt; `finally` ở test phải mở gate để tránh bỏ lại worker đang đợi.

**Giới hạn:** Nếu test cấu hình pool sai chỉ có một worker, gate đòi hai arrivals sẽ không hoàn tất; main test timeout hữu hạn và mở gate để task một tiếp tục. Đó là **test thất bại có thông tin**, không phải treo vô hạn.

### 7.5. Spring-managed service cho @Async / proxy tests

**src/main/java/demo/async/AsyncProbeService.java**

~~~java
package demo.async;

import java.util.concurrent.CompletableFuture;

import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class AsyncProbeService {

    @Async("syncProofExecutor")
    public CompletableFuture<String> threadFromSyncExecutor() {
        return CompletableFuture.completedFuture(
                Thread.currentThread().getName());
    }

    @Async("parallelProofExecutor")
    public CompletableFuture<String> threadFromPoolExecutor() {
        return CompletableFuture.completedFuture(
                Thread.currentThread().getName());
    }

    @Async("parallelProofExecutor")
    public CompletableFuture<String> waitAtGate(OverlapGate gate) {
        return CompletableFuture.completedFuture(
                gate.enterAndAwaitRelease());
    }

    public CompletableFuture<String> selfInvokePoolMethod() {
        // Self-invocation: không qua proxy @Async.
        return this.threadFromPoolExecutor();
    }
}
~~~

**Điểm đáng chú ý:**
- Ba methods đầu là public; khi được gọi qua **Spring bean/proxy**, `@Async` áp dụng đúng executor theo qualifier.
- Với `syncProofExecutor`, Future có thể được trả về đã hoàn thành vì task được chạy inline.
- Với `parallelProofExecutor`, method body chạy trên pool thread. Nó có thể hoàn thành rất nhanh; chỉ nhìn `isDone` không đủ để xác minh overlapping behavior.
- `waitAtGate` cung cấp một điểm synchronization rõ để test chứng minh **hai lời gọi @Async đang cùng in-flight**.
- `selfInvokePoolMethod()` dùng `this.threadFromPoolExecutor()` để minh họa **bypass proxy**; body chạy trên caller dù annotation của method được gọi là @Async.
- Các method trả `CompletableFuture` để test có thể chờ completion và kiểm exception; không dùng async `void` nếu test cần biết task đã hoàn thành.

## 8. JUnit class 1: executor đồng bộ chạy tuần tự

**src/test/java/demo/async/SyncTaskExecutorTest.java**

~~~java
package demo.async;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.task.TaskExecutor;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
@Execution(ExecutionMode.SAME_THREAD)
class SyncTaskExecutorTest {

    @Autowired
    @Qualifier("syncProofExecutor")
    TaskExecutor sync;

    @Test
    void syncExecuteUsesCallerThread() {
        Thread caller = Thread.currentThread();
        AtomicReference<Thread> observed =
                new AtomicReference<>();

        sync.execute(() ->
                observed.set(Thread.currentThread()));

        assertSame(caller, observed.get());
    }

    @Test
    void syncExecuteFinishesBeforeReturn() {
        AtomicBoolean completed = new AtomicBoolean(false);

        sync.execute(() -> completed.set(true));

        // Sau execute, Runnable đã hoàn thành.
        assertTrue(completed.get());
    }

    @Test
    void twoSynchronousTasksNeverOverlapForOneCaller() {
        AtomicInteger active = new AtomicInteger();
        AtomicInteger maximum = new AtomicInteger();

        Runnable task = () -> {
            int now = active.incrementAndGet();
            maximum.accumulateAndGet(now, Math::max);
            active.decrementAndGet();
        };

        sync.execute(task);
        sync.execute(task);

        assertEquals(1, maximum.get());
        assertEquals(0, active.get());
    }

    @Test
    void exceptionsAreThrownAtExecuteCall() {
        IllegalArgumentException failure = assertThrows(
                IllegalArgumentException.class,
                () -> sync.execute(() -> {
                    throw new IllegalArgumentException("bad job");
                }));

        assertEquals("bad job", failure.getMessage());
    }

    @Test
    void nestedExecuteIsReentrantOnSameCallStack() {
        List<String> order = new ArrayList<>();

        sync.execute(() -> {
            order.add("outer-start");
            sync.execute(() -> order.add("inner"));
            order.add("outer-end");
        });

        assertEquals(
                List.of("outer-start", "inner", "outer-end"),
                order);
    }

    @Test
    void threadLocalRemainsVisibleToInlineTask() {
        ThreadLocal<String> trace = new ThreadLocal<>();
        trace.set("request-A");

        try {
            AtomicReference<String> observed =
                    new AtomicReference<>();

            sync.execute(() -> observed.set(trace.get()));

            assertEquals("request-A", observed.get());
        } finally {
            trace.remove();
        }
    }
}
~~~

**Đúng 6 phương thức `@Test`.** Các test này chứng minh:
- `syncExecuteUsesCallerThread`: thread không thay đổi.
- `syncExecuteFinishesBeforeReturn`: callback hoàn tất trước khi execute trả về.
- `twoSynchronousTasksNeverOverlapForOneCaller`: với **hai sequential submissions từ một caller**, peak active chỉ 1. **Không suy rộng** rằng hai callers riêng biệt cũng không thể overlap.
- `exceptionsAreThrownAtExecuteCall`: unchecked exception của direct inline `execute` tới caller ngay.
- `nestedExecuteIsReentrantOnSameCallStack`: inner callback chạy lồng vào outer callback, không được xếp hàng chờ worker rảnh.
- `threadLocalRemainsVisibleToInlineTask`: ThreadLocal của caller có mặt trong inline callback; test sẽ có khả năng **che giấu** một lỗi context propagation ở production pool.

**Không một test nào ở đây chứng minh thread safety của business service.** Sáu test xác minh đúng semantics của sync executor, cung cấp một **negative control** cho phần pool.

## 9. JUnit class 2: pool hai threads, latch, Future và rejection

**src/test/java/demo/async/ThreadPoolTaskExecutorTest.java**

~~~java
package demo.async;

import java.time.Duration;
import java.util.concurrent.Callable;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.task.TaskRejectedException;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
@Execution(ExecutionMode.SAME_THREAD)
class ThreadPoolTaskExecutorTest {

    @Autowired
    @Qualifier("parallelProofExecutor")
    ThreadPoolTaskExecutor pool;

    @Test
    void workerThreadDiffersFromCaller() throws Exception {
        String caller = Thread.currentThread().getName();

        Future<String> future = pool.submit(
                () -> Thread.currentThread().getName());

        String actual = future.get(5, TimeUnit.SECONDS);

        assertNotEquals(caller, actual);
        assertTrue(actual.startsWith("parallel-proof-"));
    }

    @Test
    void twoTasksAreInFlightBeforeRelease() throws Exception {
        OverlapGate gate = new OverlapGate(2);

        CompletableFuture<String> first =
                CompletableFuture.supplyAsync(
                        gate::enterAndAwaitRelease, pool);

        CompletableFuture<String> second =
                CompletableFuture.supplyAsync(
                        gate::enterAndAwaitRelease, pool);

        try {
            assertTrue(
                    gate.awaitAllEntered(Duration.ofSeconds(5)),
                    "Both tasks must reach gate before release");
            assertEquals(2, gate.peakActive());
            assertEquals(2, gate.active());

            // Cả hai vẫn chờ release; không Future nào xong.
            assertFalse(first.isDone());
            assertFalse(second.isDone());
        } finally {
            gate.open(); // Không để worker bị treo nếu assert fail.
        }

        assertTrue(
                first.get(5, TimeUnit.SECONDS)
                        .startsWith("parallel-proof-"));
        assertTrue(
                second.get(5, TimeUnit.SECONDS)
                        .startsWith("parallel-proof-"));

        assertEquals(0, gate.active());
    }

    @Test
    void singleWorkerQueuesSecondTask() throws Exception {
        ThreadPoolTaskExecutor oneWorker =
                new ThreadPoolTaskExecutor();
        oneWorker.setCorePoolSize(1);
        oneWorker.setMaxPoolSize(1);
        oneWorker.setQueueCapacity(1);
        oneWorker.setWaitForTasksToCompleteOnShutdown(true);
        oneWorker.setAwaitTerminationSeconds(10);
        oneWorker.initialize();

        CountDownLatch firstStarted = new CountDownLatch(1);
        CountDownLatch releaseFirst = new CountDownLatch(1);
        AtomicBoolean secondRan = new AtomicBoolean(false);

        try {
            Future<?> first = oneWorker.submit(() -> {
                firstStarted.countDown();
                try {
                    if (!releaseFirst.await(
                            15, TimeUnit.SECONDS)) {
                        throw new IllegalStateException(
                                "First task was not released");
                    }
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(ex);
                }
            });

            assertTrue(firstStarted.await(5, TimeUnit.SECONDS));

            Future<?> second = oneWorker.submit(
                    () -> secondRan.set(true));

            // Task 1 giữ worker, task 2 đang xếp hàng.
            assertFalse(secondRan.get());
            assertFalse(second.isDone());

            releaseFirst.countDown();

            first.get(5, TimeUnit.SECONDS);
            second.get(5, TimeUnit.SECONDS);
            assertTrue(secondRan.get());
        } finally {
            releaseFirst.countDown();
            oneWorker.shutdown();
        }
    }

    @Test
    void futureCarriesWorkerException() throws Exception {
        Future<?> future = pool.submit(() -> {
            throw new IllegalArgumentException("worker failure");
        });

        ExecutionException ex = assertThrows(
                ExecutionException.class,
                () -> future.get(5, TimeUnit.SECONDS));

        assertInstanceOf(
                IllegalArgumentException.class, ex.getCause());
        assertEquals(
                "worker failure", ex.getCause().getMessage());
    }

    @Test
    void threadLocalIsNotAutomaticallyPropagated()
            throws Exception {
        ThreadLocal<String> marker = new ThreadLocal<>();
        marker.set("caller-context");

        try {
            assertEquals("caller-context", marker.get());

            Future<String> workerRead = pool.submit(
                    (Callable<String>) marker::get);

            assertNull(workerRead.get(5, TimeUnit.SECONDS));
        } finally {
            marker.remove();
        }
    }

    @Test
    void poolRejectsThirdTaskWhileBothWorkersBlocked()
            throws Exception {
        OverlapGate gate = new OverlapGate(2);

        CompletableFuture<String> first =
                CompletableFuture.supplyAsync(
                        gate::enterAndAwaitRelease, pool);

        CompletableFuture<String> second =
                CompletableFuture.supplyAsync(
                        gate::enterAndAwaitRelease, pool);

        try {
            assertTrue(
                    gate.awaitAllEntered(Duration.ofSeconds(5)));
            assertEquals(2, gate.peakActive());

            // Pool có 2 workers, không có queue capacity.
            assertThrows(
                    TaskRejectedException.class,
                    () -> pool.execute(() -> {
                        throw new IllegalStateException(
                                "Third task must be rejected");
                    }));
        } finally {
            gate.open();
        }

        first.get(5, TimeUnit.SECONDS);
        second.get(5, TimeUnit.SECONDS);
        assertEquals(0, gate.active());
    }
}
~~~

**Đúng 6 JUnit `@Test` ở lớp pool.**

1. **workerThreadDiffersFromCaller**: xác minh task chạy trên một thread pool khác; so sánh thread names vì pool có prefix rõ. Đây là test thread identity, chưa phải overlap.
2. **twoTasksAreInFlightBeforeRelease**: hai futures đang ở trong gate, mỗi task đã tăng active; test thread quan sát active=2, peak=2 và futures chưa done. Đây là bằng chứng **overlap** đáng tin hơn việc sleep hoặc thấy hai log lines.
3. **singleWorkerQueuesSecondTask**: một pool chỉ 1 worker đang bị first task giữ; second task được xếp hàng (`queueCapacity=1`) và **chưa chạy** trước khi release. Đây là negative control cho giới hạn worker count. `finally` mở latch và gọi shutdown.
4. **futureCarriesWorkerException**: khác sync `execute`, lỗi từ worker ở `Future.get()` dưới dạng `ExecutionException` với cause phù hợp. Vì vậy chỉ quan sát lời gọi `submit` không đủ biết task thất bại.
5. **threadLocalIsNotAutomaticallyPropagated**: ThreadLocal object do test thread set không tự hiện trong pool thread. Nó không có InheritableThreadLocal hoặc custom TaskDecorator, nên kết quả trong ví dụ là null.
6. **poolRejectsThirdTaskWhileBothWorkersBlocked**: hai workers đầy, queue capacity=0, task thứ ba bị từ chối với `TaskRejectedException`. Đây là rủi ro/backpressure mà SyncTaskExecutor không mô phỏng được.

**Đừng coi rejection là lỗi ngẫu nhiên của framework.** `ThreadPoolTaskExecutor` có cấu hình capacity; nếu production có queue lớn, task thứ ba có thể được enqueue thay vì bị reject. Test phải match đúng cấu hình production/test target. Bài cố ý chọn capacity nhỏ để làm rõ behavior.

**Về độ ổn định:** Các assertions phụ thuộc signal (`CountDownLatch`, Future với deadline), không phụ thuộc “ngủ 100 ms thì chắc thread khác chạy”. Trong CI quá tải, deadline 5 giây vẫn có thể quá ngắn; hãy chọn thời gian phù hợp môi trường, nhưng **không dùng timeout để tạo concurrency**. Nếu timeout, test fail và release gate thay vì treo vô hạn.

## 10. JUnit class 3: xác minh Spring @Async và self-invocation

**src/test/java/demo/async/AsyncProxyIntegrationTest.java**

~~~java
package demo.async;

import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
@Execution(ExecutionMode.SAME_THREAD)
class AsyncProxyIntegrationTest {

    @Autowired
    AsyncProbeService service;

    @Test
    void qualifiedSyncAsyncActuallyRunsOnCallerThread()
            throws Exception {
        String caller = Thread.currentThread().getName();

        CompletableFuture<String> result =
                service.threadFromSyncExecutor();

        assertTrue(result.isDone());
        assertEquals(
                caller, result.get(5, TimeUnit.SECONDS));
    }

    @Test
    void qualifiedParallelAsyncRunsOnPoolThread()
            throws Exception {
        String caller = Thread.currentThread().getName();

        CompletableFuture<String> result =
                service.threadFromPoolExecutor();

        String worker = result.get(5, TimeUnit.SECONDS);

        assertNotEquals(caller, worker);
        assertTrue(worker.startsWith("parallel-proof-"));
    }

    @Test
    void twoProxiedAsyncCallsOverlap()
            throws Exception {
        OverlapGate gate = new OverlapGate(2);

        CompletableFuture<String> first =
                service.waitAtGate(gate);

        CompletableFuture<String> second =
                service.waitAtGate(gate);

        try {
            assertTrue(
                    gate.awaitAllEntered(Duration.ofSeconds(5)));
            assertEquals(2, gate.peakActive());

            assertFalse(first.isDone());
            assertFalse(second.isDone());
        } finally {
            gate.open();
        }

        String worker1 = first.get(5, TimeUnit.SECONDS);
        String worker2 = second.get(5, TimeUnit.SECONDS);

        assertTrue(worker1.startsWith("parallel-proof-"));
        assertTrue(worker2.startsWith("parallel-proof-"));
        assertNotEquals(worker1, worker2);

        assertEquals(0, gate.active());
    }

    @Test
    void selfInvocationBypassesAsyncProxy() throws Exception {
        String caller = Thread.currentThread().getName();

        CompletableFuture<String> result =
                service.selfInvokePoolMethod();

        // Inside selfInvokePoolMethod: this.threadFromPoolExecutor().
        assertTrue(result.isDone());
        assertEquals(
                caller, result.get(5, TimeUnit.SECONDS));
    }
}
~~~

**Đúng 4 `@Test` ở lớp tích hợp @Async.**

- Test thứ nhất dùng `@Async("syncProofExecutor")` và chứng minh **annotation không buộc chuyển thread** nếu executor được chọn là inline. `CompletableFuture` đã hoàn thành là một hệ quả kỳ vọng.
- Test thứ hai dùng `@Async("parallelProofExecutor")` và chứng minh invocation **qua Spring proxy** chạy ở worker thread.
- Test thứ ba tạo **hai lời gọi `@Async`** đi qua Spring proxy, dùng gate buộc cả hai worker đang in-flight trước khi test giải phóng. Đây là bằng chứng quan trọng nhất về **real concurrency ở @Async boundary** trong project.
- Test thứ tư chứng minh **self-invocation** không đi qua Spring proxy và chạy đồng bộ. Nếu chỉ nhìn annotation trên `threadFromPoolExecutor`, ta dễ hiểu sai behavior của `this.threadFromPoolExecutor()`.

**Lưu ý về test async nhanh:** Không nên assert `assertFalse(result.isDone())` ngay sau một lời gọi `threadFromPoolExecutor()` trả kết quả cực nhanh; nó có thể hoàn thành trước khi caller kịp kiểm. Chỉ assert chưa done ở test `waitAtGate`, khi work **có điểm chờ rõ ràng**.

## 11. Tổng hợp test và cách chạy

| Test class | Số `@Test` | Bằng chứng |
|---|---:|---|
| `SyncTaskExecutorTest` | **6** | Caller thread, inline completion, sequential peak=1, exception, nested execute, ThreadLocal |
| `ThreadPoolTaskExecutorTest` | **6** | Worker identity, **2 tasks overlap**, 1-worker queue, Future exception, ThreadLocal separation, rejection |
| `AsyncProxyIntegrationTest` | **4** | `@Async` sync vs pool, 2 proxied @Async tasks overlap, self-invocation bypass |
| **Tổng** | **16** | Bốn nhóm bằng chứng bổ trợ; không có @Disabled |

**Lệnh chạy với Gradle Wrapper** (nếu project đã tạo wrapper scripts/JAR):

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Nếu mới tạo các tệp trong bài nhưng **chưa có Gradle Wrapper**, lệnh `./gradlew` chưa tồn tại. Dùng Gradle tương thích để tạo wrapper hoặc tạm chạy:

~~~bash
gradle test
~~~

Chạy riêng lớp:

~~~bash
./gradlew test --tests demo.async.SyncTaskExecutorTest
./gradlew test --tests demo.async.ThreadPoolTaskExecutorTest
./gradlew test --tests demo.async.AsyncProxyIntegrationTest
~~~

Báo cáo test thường tại:

~~~text
build/reports/tests/test/index.html
~~~

**Kết quả kỳ vọng khi code/dependencies/lifecycle đúng:** 16 JUnit Jupiter tests được phát hiện và được thiết kế PASS. Lớp sync dùng một thread calling; lớp pool buộc hai workers cùng in-flight tại gate; lớp @Async qua proxy chứng minh executor được chọn có ảnh hưởng trực tiếp. Đây là **kết quả mong đợi theo API và assertions**, không phải lời khẳng định Gradle đã được thực thi trong môi trường người đọc.

**Quan trọng:** Test chứng minh **hai tasks in-flight** nhưng vẫn **không chứng minh** business algorithm đã xử lý đúng mọi possible interleavings. Khi ứng dụng có race trên shared state, cần đưa domain operation vào vùng gate và kiểm invariant/DB state sau cả hai tasks. Pool có hai workers là **điều kiện tạo concurrency**, không tự xác lập đúng sai của nghiệp vụ.

### 11.1. Nếu test đúng về synchronization nhưng application vẫn sai

Lấy bài toán tồn kho chỉ còn 1 đơn vị. Test tuần tự:

~~~text
Task A đọc stock=1 -> ghi stock=0 -> success.
Task B đọc stock=0 -> reject.
``Không có lỗi oversell`` nếu thực thi nối tiếp.
~~~

Ở execution thật có thể có interleaving:

~~~text
Task A đọc stock=1 --------------------- cập nhật stock=0
Task B -------- đọc stock=1 ----------- cập nhật stock=0
Cả hai đều cho "success" nhưng chỉ có một đơn vị.
~~~

**Mục tiêu cần assert khi kiểm đồng thời:** tổng số reservation thành công phải <= stock ban đầu; không có negative stock; không tạo duplicate order IDs; không mất audit event. Với JDBC/JPA, kiểm sau khi cả hai `Future`s hoàn thành và transaction commit, bằng query độc lập ở database test.

**Không biến bài học này thành cách tạo exploit.** Đây là kiểm thử tính đúng đắn của business invariant; production cần transaction isolation, optimistic/pessimistic locking hoặc atomic SQL update, tùy workload.

## 12. Bẫy ThreadLocal và test-managed transaction

`SyncTaskExecutor` thường giúp callback **nhìn thấy ThreadLocal của caller**, như test thứ sáu. Nhưng đó là **khác biệt kiến trúc** khi production `ThreadPoolTaskExecutor` chuyển task sang worker:

| Context | SyncTaskExecutor từ test thread | Pool worker |
|---|---|---|
| `ThreadLocal` tự tạo | Có thể thấy giá trị caller | Không tự có |
| Spring `SecurityContextHolder` mặc định | Thường cùng thread/context | Không tự được truyền |
| MDC log context | Có thể hiện diện | Cần propagation rõ ràng |
| Spring test-managed transaction | Có thể cùng transaction đã bind ở caller | Không tự tham gia transaction caller |
| Locale/request context | Có thể còn trên thread caller | Có thể null hoặc sai nếu không thiết kế |
| Error stack/exception | Direct execute có thể ném tại caller | Thường quan sát qua Future/handler |

Một bài test có `@Transactional` của Spring TestContext rồi thay mọi async work bằng `SyncTaskExecutor` có thể làm database writes **tham gia transaction của test** và được rollback. Nhưng HTTP server thread/async pool production lại không mang test transaction của caller. Do đó cùng test có thể “xanh, sạch DB” với sync executor nhưng tạo dữ liệu committed độc lập khi chạy async thật.

**Phân biệt quan trọng:** Worker thread **có thể** có transaction **riêng** nếu code của nó đi qua Spring `@Transactional` proxy hoặc `TransactionTemplate`. Phát biểu đúng là: nó **không tự thừa hưởng test transaction của caller**, không phải “mọi worker đều không có transaction”.

Nếu code async cần SecurityContext, có thể dùng `DelegatingSecurityContextAsyncTaskExecutor` của Spring Security hoặc `TaskDecorator` phù hợp, **nhưng không mặc nhiên truyền JDBC Connection/TransactionStatus giữa threads**. Transaction resource có lifecycle gắn thread và có thể không thread-safe. Khi kiểm propagation, test cả **khả năng hiện diện**, **đúng user/tenant** và **cleanup** để tránh context của request trước rò vào request sau.

### 12.1. Phản mẫu: fake async làm false-positive về transaction

~~~java
@Test
@Transactional
void wrongProofOfAsyncRollback() {
    // Đoạn code dưới đây chỉ minh họa sai lầm.
    // Nếu async executor bị đổi thành SyncTaskExecutor:
    service.performAsyncWrite();

    // Rollback cuối test có thể dọn được write do callback
    // chạy ngay trên thread test.
    // Điều đó KHÔNG chứng minh rollback khi worker thật xử lý.
}
~~~

Đây là **snippet phản mẫu**, không thuộc source runnable của phần 7–10; project chính không có DataSource. Với test cần xác minh DB async work, dùng **database disposable**, async executor thật, chờ Future hoàn thành và query trạng thái sau commit/rollback. Đừng dùng `@Transactional` trên test client rồi giả định side effects ở thread khác được tự động rollback.

## 13. `@Scheduled` là một bài toán lịch chạy riêng

`@Async` **submit công việc** sang executor; `@Scheduled` **kích hoạt** method theo fixed rate, fixed delay hoặc cron. Scheduler thường được điều khiển bởi **`TaskScheduler`**, ví dụ `ThreadPoolTaskScheduler`, không phải `TaskExecutor` được chọn cho một @Async method.

Vì vậy thay `TaskExecutor` bằng `SyncTaskExecutor` trong test **không tự chứng minh**:
- Cron expression thực sự kích hoạt vào thời điểm mong muốn.
- `fixedRate` có các lần kích hoạt chồng nhau hay không.
- `fixedDelay` chờ lần trước hoàn tất theo cách dự kiến.
- Scheduler có đủ pool threads để hai scheduled jobs overlap.
- Một job bị treo có làm job khác bị starvation không.
- Misfire, clock skew, DST và scheduling jitter có được xử lý không.

Ví dụ cấu hình scheduler (snippet riêng, không thuộc project runnable):

~~~java
@Bean
ThreadPoolTaskScheduler taskScheduler() {
    ThreadPoolTaskScheduler scheduler =
            new ThreadPoolTaskScheduler();
    scheduler.setPoolSize(2);
    scheduler.setThreadNamePrefix("schedule-test-");
    return scheduler;
}
~~~

Để **chứng minh overlap của lịch chạy**, cần thật sự kích hoạt hai scheduled executions (hoặc cùng một business handler được kích hoạt qua scheduler) và quan sát chúng bằng gate ở vùng công việc. Một test trực tiếp gọi method có `@Scheduled` không đi qua scheduling trigger và không chứng minh cron/fixedRate semantics.

**Một nuance nữa:** Nếu một method mang cả `@Scheduled` và `@Async`, scheduler có thể gọi proxy method, còn phần work do async executor được chọn quyết định. Việc job overlap lúc đó phụ thuộc **cả scheduler triggers lẫn async executor capacity**. Dùng sync executor cho @Async sẽ làm scheduler calling thread chờ method xong, có thể che mất overlap thật của cấu hình production.

### 13.1. Test scheduling theo hai tầng

**Tầng 1 — logic của job:** Tách nghiệp vụ khỏi annotation/trigger, test method logic tuần tự hoặc với fake Clock khi cần. Không cần chờ đồng hồ thật chạy tới cron.

**Tầng 2 — trigger/concurrency:** Dùng scheduler thật nhưng thời gian test kiểm soát được, chờ CountDownLatch/observer events, kiểm số lần trigger, không có unexpected overlaps hoặc có overlaps theo contract, và dọn task schedules sau test. Với hệ phân tán nhiều replicas, chỉ một local scheduler pool test **không chứng minh cluster-wide singleton job**; cần distributed lock/lease/idempotency và integration tests phù hợp.

**Clock/virtual time:** `Clock` inject/fake giúp test logic dựa vào thời gian, nhưng không tự làm Spring scheduler thật tiến thời gian giả. Nếu test cron, DST hoặc timers, chọn abstraction hỗ trợ virtual time hoặc kiểm schedule calculation thuần riêng.

## 14. TaskExecutor, ExecutorService và CompletableFuture: khác nhau ở điểm nào?

Spring `TaskExecutor` mở rộng `java.util.concurrent.Executor`. `SyncTaskExecutor` chỉ có `execute(Runnable)` nên **không phải một thread pool** và không cung cấp `submit(Callable)` trực tiếp như `ExecutorService`. Spring `ThreadPoolTaskExecutor` triển khai `AsyncTaskExecutor`, hỗ trợ submit và Future.

`CompletableFuture` có một số cách dùng dễ bị hiểu nhầm:

~~~java
CompletableFuture<String> ready =
        CompletableFuture.completedFuture("ok");
// Đã hoàn tất, không hề tạo thêm concurrency.

CompletableFuture<String> inPool =
        CompletableFuture.supplyAsync(
                () -> Thread.currentThread().getName(),
                parallelExecutor);
// Work được submit vào executor đã nêu.
~~~

Đây là snippet với biến `parallelExecutor` đại diện cho một `Executor` đã cấu hình. Chỉ dùng `completedFuture` không tạo worker; `supplyAsync` có một executor cụ thể sẽ submit callback qua executor ấy. Nếu dùng `supplyAsync(supplier)` không nêu executor, Java thường dùng ForkJoin common pool, không nhất thiết liên quan Spring Boot `TaskExecutor` đang kiểm.

**`thenApply` vs `thenApplyAsync`:** Một callback `thenApply` có thể chạy trên thread hoàn tất stage trước (hoặc thread gắn callback khi đã completed), không bảo đảm thread hop. `thenApplyAsync` gửi callback qua executor bất đồng bộ (common pool hoặc executor explicit). Khi test context propagation hoặc concurrency, phải xác định **chính xác callback được thực thi ở thread nào**, không suy ra từ cái tên Future.

**Exception:** Direct `SyncTaskExecutor.execute` có thể ném exception ngay, trong khi `ThreadPoolTaskExecutor.submit` trả Future và exception xuất hiện ở `Future.get()`. Với `CompletableFuture`, failure được quan sát qua `get`, `join`, `handle`, `whenComplete` hoặc `exceptionally`; chỉ submit rồi assert state có thể bỏ sót một task đã fail.

**Cancellation:** `future.cancel(true)` thường là yêu cầu interruption, không phải một bảo đảm side effects đã dừng/rollback. Tác vụ không tôn trọng interrupt có thể tiếp tục; dùng timeout hữu hạn và cleanup trong finally. Đừng sử dụng `assertTimeoutPreemptively` một cách vô tư trong transactional integration test: callback có thể chạy khác thread và thoát rollback của test.

## 15. Thiết kế một concurrency test thật cho business invariant

Sử dụng ba giai đoạn:

**Giai đoạn A — Arrange:**
- Seed trạng thái business ban đầu cố định (ví dụ `inventory=1`).
- Tạo **2 requests/tasks riêng** cùng tác động lên một object key.
- Tạo executor đủ workers và gate.
- Tách instrumentation khỏi business code sao cho việc ghi `AtomicInteger peakActive` **không vô tình khóa/serialize business path** cần test.

**Giai đoạn B — Force concurrent interleaving:**
- Cho cả hai workers vào **vùng tranh chấp**, ví dụ ngay sau khi đọc cùng version/tồn kho hoặc trước update.
- Chờ đủ hai arrivals; release cùng gate.
- Khi thật sự cần test “cả hai đều đọc cùng giá trị cũ”, đặt barrier **sau read, trước write** bằng test-only hook hoặc dependency điều khiển được; barrier ngay ở đầu method chỉ chứng minh hai tasks bắt đầu gần nhau, **không ép** đúng interleaving nguy hiểm.
- Không dùng sleeps hoặc đặt thread priorities để hy vọng race xảy ra.

**Giai đoạn C — Assert invariants after completion:**
- `Future.get(timeout)` cả hai; phân loại success/conflict theo contract.
- Query DB sau khi các transactions đã kết thúc bằng một connection/transaction mới nếu cần.
- Assert **không oversell**, **không duplicate**, **không lost update**, **số lượng side effects khớp với số operations được accept**.
- Kiểm failure paths và cleanup, bao gồm khi một Future ném exception.
- Lặp nhiều seeds hoặc workload scenarios để tăng coverage; **một interleaving thành công không chứng minh mọi interleaving đều an toàn**.

Ví dụ pseudocode về điều kiện **sau khi hoàn tất**:

~~~java
// Snippet: repository và business operations thuộc hệ thống thật.
Result first = future1.get(5, TimeUnit.SECONDS);
Result second = future2.get(5, TimeUnit.SECONDS);

long accepted = Stream.of(first, second)
        .filter(Result::accepted)
        .count();

assertEquals(1L, accepted);
assertEquals(0, inventoryRepository.available("SKU-1"));
assertEquals(1L, reservationRepository.countBySku("SKU-1"));
~~~

Đây là **snippet không độc lập**, các types `Result`, `inventoryRepository` và `reservationRepository` chưa được định nghĩa. Nó minh họa cần assert **đúng business invariant**, không chỉ in-flight peak. Nếu policy cho phép hai tác vụ cùng lấy hàng từ một stock 2 units, expected accepted count phải thay tương ứng.

### 15.1. Atomic increment trong instrumentation không chữa lost update

~~~java
AtomicInteger tracked = new AtomicInteger();
tracked.incrementAndGet();
~~~

Biến tracked an toàn vì atomic operations, nhưng nếu code production đang làm:

~~~java
int balance = account.getBalance();
account.setBalance(balance - amount);
~~~

thì hai threads vẫn có thể đọc cùng balance cũ và ghi đè nhau. Đừng dùng test counter atomic để thay thế transaction/locking thật trong business code. Với DB, xem optimistic version field (`@Version`), atomic conditional UPDATE, serializable transactions hoặc pessimistic row lock tùy mục tiêu.

### 15.2. Test overlap không phải stress test

Một latch-gated test kiểm một schedule cụ thể có thể deterministic và hữu ích cho regression. Để tăng độ tin cậy đối với races phức tạp, có thể cần:
- Nhiều interleavings khác nhau, random-yield/delay injection có kiểm soát hoặc property-based scenarios.
- Stress/integration tests trong môi trường tương đương production (DB, pool, CPU quotas, thread counts).
- **jcstress** cho các vấn đề Java Memory Model/visibility/linearizability của code thuần JVM.
- Load test/benchmark cho throughput và queueing latency (không dùng unit test elapsed time làm KPI production).
- Fault-injection ở transaction commit, message delivery, interruption và shutdown.
- Observability về active threads, queue depth, rejected tasks và downstream failures.

Không có một assert đơn lẻ có thể “chứng minh không có race” trong mọi thực thi cho một hệ thống bất kỳ. Hãy xác định loại hành vi cần chứng minh, rồi chọn kỹ thuật phù hợp.

## 16. Sai lầm và troubleshooting

| Triệu chứng | Nguyên nhân | Cách sửa |
|---|---|---|
| `@Async` test trả về ngay nhưng luôn cùng thread | Executor được chọn là SyncTaskExecutor hoặc self-invocation | Kiểm qualifier, proxy và thread identity |
| Có 2 `execute` calls nhưng peakActive=1 | Sync executor chạy tuần tự hoặc pool chỉ có 1 worker | Pool >=2 workers và gate |
| Test treo tại latch đầu | Caller bị chặn trong SyncTaskExecutor trước submit lần hai | Không dùng gate hai parties với sequential inline submits |
| Test dùng `Thread.sleep(50)` đôi lúc fail | Scheduling/CI không xác định | CountDownLatch/CyclicBarrier và bounded wait |
| `@Async` test lúc `isDone=true`, lúc false | Task chạy quá nhanh | Dùng gate nếu thực sự cần chứng minh pending |
| Test xanh với sync executor nhưng DB bị rò khi deploy | Thread-local transaction trong test không được truyền sang worker | Dùng async executor thật và DB isolation test |
| Principal/MDC có ở test nhưng null trên worker | Test dùng SyncTaskExecutor che thiếu context propagation | Test worker thật, propagator đúng; cleanup |
| `@PreAuthorize`/`@Async` không chạy ở call nội bộ | Self-invocation không qua proxy | Tách bean/đi qua proxy đúng |
| Thay SyncTaskExecutor thành pool làm test fail vì exception | Exception bây giờ đi qua Future thay vì caller | `get()/join()` và assert cause |
| `TaskRejectedException` khi submit task thứ ba | Pool 2 workers, queue capacity=0 | Policy backpressure; test retry/reject/handling |
| Pool vẫn giữ task sau test | Gate không release hoặc Future không chờ | `finally gate.open()` và bounded get/shutdown |
| Pool luôn chạy chỉ 1 thread | Core size 1 + queue lớn, task bị queue | Tăng core/cấu hình queue phù hợp với test |
| `.setMaxPoolSize(8)` vẫn chỉ thấy 1 | Core=1, queue còn dung lượng nên chưa scale lên max | Kiểm core/queue interactions |
| Test pass nhưng business lost update | Chỉ kiểm peak=2, không kiểm invariant sau interleaving | Barrier gần shared state, asserts DB |
| Test check ThreadLocal bằng InheritableThreadLocal | Truyền context có thể xảy ra khác biệt | Test đúng loại ThreadLocal thực dùng |
| Lỗi `NoUniqueBeanDefinitionException` cho Executor | Nhiều Executor beans không qualifier/default rõ | @Async("beanName") hoặc AsyncConfigurer |
| `@Scheduled` chạy đúng trong direct call nhưng không theo cron | Direct call bypass scheduler | Integration test TaskScheduler/trigger riêng |
| Scheduler pool 1 bị job dài chiếm | Không đủ scheduler threads; không liên quan SyncTaskExecutor trực tiếp | Cấu hình scheduler pool, bounded tasks |
| Không chạy được Gradle test | Chưa có wrapper, Java 17 sai version | Tạo wrapper/chọn toolchain phù hợp |
| Test bị timeout khi CI quá tải | Deadline quá ngắn hoặc pool chưa khởi tạo/đang bị dùng | Kiểm JUnit parallelism, pool bean, tăng hợp lý timeout |
| App có nhiều virtual threads nhưng test Java17 | Virtual threads yêu cầu Java 21+ | Tách version/scenario, không suy từ Java17 |
| `.get()` đứng mãi | Task deadlock/future không hoàn thành | Bounded get và release/cancellation |
| `@Transactional` trên worker “không có effect” | Lời gọi không qua transaction proxy hoặc transaction context khác | Test boundary/propagation, không copy JDBC context |

### 16.1. Checklist khi một test async bị nghi ngờ “xanh giả”

1. **Đọc tên thực của executor bean** đã được inject/chọn bởi @Async. Có đang dùng SyncTaskExecutor không?
2. Nếu SyncTaskExecutor, xác định test chỉ chứng minh **sequential behavior** hay lỡ tuyên bố concurrency?
3. Test có đi qua **Spring proxy** không? Có self-invocation hay `new Service()` thủ công không?
4. Test có hai worker threads thật hoặc hai independent calling threads không?
5. Có một **gate/barrier** đảm bảo hai tasks cùng in-flight trước khi release không?
6. Gate có bounded await và `finally` release không?
7. Test có kiểm cả Future completion và exception (get/join) không?
8. `peakActive` có thực sự đếm vùng critical section cần quan sát, hay chỉ đếm đầu method?
9. Test có assert business invariants/DB outcome sau cả hai tasks không?
10. Có ThreadLocal/SecurityContext/transaction context được giả định tự truyền không?
11. Có đủ pool capacity, queue/rejection policy và no-parallel-test interference không?
12. Nếu là @Scheduled, đã test **scheduler triggers** chứ không chỉ gọi method thủ công chưa?
13. Khi chuyển test từ sync sang async, fixture/database có được cô lập và cleanup đúng không?
14. Có thread/connection/resource leak khi timeout/failure không?
15. Kết luận trong code review có giới hạn rõ: “đã quan sát overlap trong test này”, không phải “đã chứng minh thread-safe tuyệt đối”?

## 17. Câu hỏi thực hành

**Bài 1 — Thread identity.** Với SyncTaskExecutor, dùng `Thread.currentThread()` trước và trong `execute`. Vì sao cùng thread? Nếu hai caller threads độc lập gọi chung executor, có thể xảy ra overlap không?

**Bài 2 — Thứ tự.** Chạy hai tasks bằng sync executor; ghi `[A-start,A-end,B-start,B-end]`. Đổi sang pool hai workers có gate. Thứ tự logs có còn chắc chắn không? Assertions nào nên tránh?

**Bài 3 — Exception.** Cho callback ném `IllegalArgumentException`. Với direct SyncTaskExecutor.execute, exception xuất hiện ở đâu? Với ThreadPoolTaskExecutor.submit, test phải gọi gì để nhìn được lỗi?

**Bài 4 — Latch.** Thêm `CountDownLatch(2)` vào hai tasks nhưng lại submit qua sync executor một thread. Tại sao test treo/timeout? Là bug business hay bug test synchronization?

**Bài 5 — Pool capacity.** Đổi `corePoolSize=2` thành 1, `queueCapacity=1`. Vì sao task thứ hai không overlap được dù `maxPoolSize=2`? Sự khác nhau giữa core, max và queue là gì?

**Bài 6 — No sleep.** Viết concurrency test mà không dùng Thread.sleep, chỉ dùng `CountDownLatch`, `AtomicInteger peakActive` và bounded `Future.get`.

**Bài 7 — @Async qualifier.** Đổi `@Async("parallelProofExecutor")` sang `@Async("syncProofExecutor")`. Test nào fail? Vì sao `@Async` không tự tạo thread khi executor đã là inline?

**Bài 8 — Self-invocation.** Bỏ test `selfInvocationBypassesAsyncProxy` rồi thêm một call nội bộ trong service. Khi production thật, @Async có được áp dụng? Làm sao sửa kiến trúc?

**Bài 9 — ThreadLocal.** Set một ThreadLocal trong test caller, đọc nó trong sync task và pool task. Khi nào cần propagate context, khi nào phải fail closed? Không copy JDBC transaction resource qua thread.

**Bài 10 — Timeout.** Cho task bỏ qua interrupt, gọi Future.cancel(true). Điều gì có thể xảy ra? Làm sao cleanup và không coi timeout là rollback?

**Bài 11 — Lost update.** Hai clients cùng reserve SKU-1 còn 1 unit. Dùng gate đặt **sau read, trước write** để ép race. Thiết kế atomic UPDATE/optimistic lock rồi test lại.

**Bài 12 — CompletableFuture.** So sánh `completedFuture`, `supplyAsync` với executor được chỉ định, `thenApply` và `thenApplyAsync`. Method nào chứng minh có thread hop?

**Bài 13 — @Scheduled.** Viết fixed-rate job và một scheduled job khác. Dùng TaskScheduler thật có pool phù hợp; xác minh overlap/no overlap theo hợp đồng. Vì sao thay TaskExecutor sync không đủ?

**Bài 14 — Scheduler drift.** Thêm công việc dài hơn period, quan sát lịch với scheduler một thread/hai threads. Kiểm đúng semantics của fixedRate/fixedDelay thay vì giả định từ logs.

**Bài 15 — DB transaction.** Một @Transactional test gọi @Async service với SyncTaskExecutor rồi với ThreadPoolTaskExecutor. Chỉ ra vì sao rollback và ThreadLocal khác nhau; test với disposable DB để không pollute data.

**Bài 16 — Stress.** Tạo test 1000 tasks và so sánh throughput, rejected tasks, queue length. Vì sao kết quả này không nên được dùng như benchmark chính thức nếu chạy trong test runner quá biến động?

**Bài 17 — Virtual threads.** Nếu chuyển sang JDK 21 và SimpleAsyncTaskExecutor virtual-thread mode, task vẫn có thể overlap nhưng resource constraints khác. Những asserts nào vẫn hợp lệ? Những giả định về thread name/pool reuse nào cần sửa?

**Bài 18 — Review.** Tìm các test dùng `SyncTaskExecutor`, `Runnable::run`, `MoreExecutors.directExecutor` hoặc executor giả synchronous; phân loại những test chỉ cần deterministic logic và những test đang tuyên bố “thread-safe”.

## 18. Tham khảo chính thức

- [Spring Framework 6.1 — SyncTaskExecutor API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/task/SyncTaskExecutor.html): chạy mỗi task đồng bộ trên calling thread, chủ yếu hữu ích cho testing.
- [Spring Framework 6.1 — ThreadPoolTaskExecutor API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html): core/max pool, queueCapacity, Future, lifecycle và rejection.
- [Spring Framework 6.1 — TaskExecutorAdapter API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/task/support/TaskExecutorAdapter.html): adapter từ Executor sang AsyncTaskExecutor.
- [Spring Framework 6.1 — @EnableAsync API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html): async proxy, executor selection và AsyncConfigurer.
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@Async`, executor qualifier, scheduler và exceptions.
- [Spring Boot 3.3 — Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html): applicationTaskExecutor, auto-configuration và scheduler settings.
- [Java 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): awaited signals và happens-before guarantee.
- [Java 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): completion, executor selection, errors và cancellation.
- [Java 17 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html): core/max threads, work queues và rejection.
- [Java 17 — AtomicInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): atomic counters an toàn cho test instrumentation.
- [Spring Framework — TestContext Transaction Management](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): transaction ThreadLocal và rủi ro khi test chạy khác thread.
- [OpenJDK jcstress](https://openjdk.org/projects/code-tools/jcstress/): stress tests chuyên dụng cho Java Memory Model/concurrency semantics.

**Ghi nhớ cuối bài:** `SyncTaskExecutor` **không sai**: nó tốt khi ta muốn kiểm logic/callback theo thứ tự xác định và không đổi thread. Nhưng hai lần submit tuần tự qua executor này **không chứng minh** hai tác vụ có thể overlap, không phát hiện được nhiều race conditions và có thể che lỗi ThreadLocal/transaction context của async execution thật. Khi yêu cầu là “**chứng minh hành vi đồng thời**”, hãy chọn executor thật có đủ workers, **dùng latch/barrier để buộc cùng in-flight, release trong finally, chờ Futures hữu hạn và assert business invariants sau completion**. Tách test scheduling khỏi test work logic; phân biệt @Async proxy với self-invocation; không suy từ một test overlap rằng hệ thống an toàn cho mọi interleaving.
