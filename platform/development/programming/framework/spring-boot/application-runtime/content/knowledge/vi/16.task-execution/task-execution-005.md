# Phân biệt tác vụ đã được gửi với tác vụ đã hoàn thành

## 1. Bài toán: gọi submit thành công có nghĩa công việc đã xong?

Trong ứng dụng Spring Boot, có nhiều chỗ khởi chạy công việc ngoài luồng gọi hiện tại: `Executor.execute(...)`, `ExecutorService.submit(...)`, `CompletableFuture.supplyAsync(...)`, method `@Async`, scheduler hoặc một `ApplicationRunner` gửi tác vụ vào thread pool. Nếu lời gọi gửi tác vụ trả về bình thường, ta dễ viết log “đã xử lý xong” hoặc phát thông báo “ready”. **Đây là một lỗi suy luận thường gặp.**

Cần phân biệt tối thiểu năm mốc:

1. **Submitted / accepted:** lệnh thực thi được giao cho executor và không bị từ chối ngay tại thời điểm gọi. Tác vụ có thể nằm trong queue.
2. **Started / running:** một thread thực sự bắt đầu chạy body của tác vụ.
3. **Completed:** tác vụ đạt một trạng thái kết thúc theo contract của đối tượng theo dõi. Có thể là **thành công, thất bại hoặc bị hủy**.
4. **Succeeded:** body trả kết quả hợp lệ hoặc side effect mong muốn đã được xác nhận theo hợp đồng.
5. **Observed / acknowledged:** bên gọi đã nhận/kiểm tra kết quả, cập nhật trạng thái nghiệp vụ, hoặc bên đích xác nhận durable commit nếu công việc liên quan hệ thống ngoài.

**“Submitted” không đồng nghĩa “started”. “Completed” không đồng nghĩa “succeeded”. Và “Future đã xong” không tự chứng minh hệ thống ngoài đã commit dữ liệu.**

Bài đặt trong ngữ cảnh **Spring Boot 3.3.x, Spring Framework 6.1.x và Java 17+**. Ta sẽ dùng Java `Future`, `CompletableFuture`, Spring `TaskExecutor` và `@Async`, rồi kết nối với thứ tự `ApplicationStartedEvent` → runners → `ApplicationReadyEvent`.

## 2. Timeline của một tác vụ bất đồng bộ

Sơ đồ khái quát của một executor có hàng đợi:

```text
Thread A (caller)                           Executor / Thread B
-----------------                           -------------------
tạo Runnable/Callable/async invocation
       |
       +--> submit(task) ------------------> nhận hoặc từ chối task
       |                                        |
       |                                        +--> queue (có thể đợi)
       |                                        |
       |                                        +--> worker bắt đầu
       |                                               |
       |                                               +--> chạy body
       |                                               +--> hoàn thành / throw / cancel
       |                                               +--> cập nhật Future
       |
       +--> nhận Future <------------------- handle đại diện computation
       |
       +--> làm việc khác
       |
       +--> future.get() / join() ----------> chờ nếu chưa hoàn thành
                                                 |
                                                 +--> trả value hoặc báo failure
```

Một lời gọi `ExecutorService.submit(Callable<T>)` thường trả về rất nhanh nếu tác vụ được nhận. Tác vụ có thể **chưa có worker rảnh**, đang nằm trong queue, đang chạy hoặc đã hoàn tất cực nhanh. Vì thế **không thể suy ra trạng thái started/completed chỉ từ việc method submit đã return**.

Ngoại lệ đáng chú ý: `Executor` là abstraction. Một executor có thể thực thi ngay trên caller thread; một `RejectedExecutionHandler.CallerRunsPolicy` có thể chạy tác vụ ngay trong thread gọi khi pool bị quá tải. Vì vậy cũng **không thể khẳng định mọi lệnh `execute` đều bất đồng bộ**. Phải xem executor thực tế, queue, rejection policy và cách gọi.

Bên gọi nhận `Future` là nhận **tay cầm quan sát kết quả**, không phải giá trị tính toán ngay lập tức. Với `CompletableFuture`, tay cầm còn cho phép nối các stage xử lý tiếp và quản lý lỗi.

## 3. Bảng so sánh các API và điều chúng bảo đảm

| API / thao tác | Ngay sau khi return, biết điều gì? | Không tự bảo đảm điều gì? |
| --- | --- | --- |
| `Executor.execute(Runnable)` | Lệnh đã được executor xử lý theo policy nếu không throw | Task đã bắt đầu hoặc hoàn tất; không có result handle chuẩn |
| `ExecutorService.submit(Callable<T>)` | Trả về `Future<T>` nếu submission thành công | `Callable` đã chạy xong; kết quả thành công |
| `ExecutorService.submit(Runnable)` | Trả về `Future<?>` để theo dõi | Runnable không ném exception; side effect đã commit |
| `CompletableFuture.supplyAsync(supplier, executor)` | Trả về stage đại diện computation dùng executor chỉ định | Stage đã hoàn thành trước khi return |
| `CompletableFuture.completedFuture(value)` | Future **đã** hoàn thành bình thường với value | Có một tác vụ nền thật sự đã được submit |
| `@Async` method trả `CompletableFuture<T>` | Khi proxy async hoạt động, caller nhận Future về kết quả của invocation | Body đã hoàn tất; gọi cùng class (self-invocation) cũng được proxy intercept |
| `@Async void` | Caller không nhận Future từ method | Có thể `get/join` để nhận kết quả/lỗi; lỗi sẽ tự làm caller throw |
| `Future.isDone()` | Future ở trạng thái kết thúc theo định nghĩa API | Nó thành công; cancellation đã thực sự dừng mọi side effect |
| `Future.get()` | Khi return bình thường, có kết quả thành công theo Future | Tác động ở DB/API ngoài đã durable nếu body không xác nhận |
| `CompletableFuture.join()` | Khi return bình thường, lấy được giá trị của stage | Không block; không bao giờ ném exception |
| `ExecutorService.shutdown()` | Executor bắt đầu từ chối công việc mới, tiến tới shutdown theo contract | Những task đang chờ/đang chạy đã hoàn tất |

Nếu pool đã đóng hoặc đầy theo chính sách từ chối, `submit`/`execute` có thể **ném `RejectedExecutionException`** (hoặc loại exception tương ứng của Spring). Khi bị từ chối thì **chưa có một tác vụ accepted** để chờ; ứng dụng phải xử lý backpressure/retry/fallback theo hợp đồng.

### 3.1. “Accepted” có tương đương “đã vào queue” không?

Không. Executor có thể tạo thread chạy ngay, đưa vào queue, dùng caller thread, hoặc có policy khác. “Accepted” chỉ có nghĩa lệnh được xử lý theo cơ chế executor mà không bị từ chối ngay. Không được ghi cứng `QUEUED` chỉ dựa vào `submit` thành công.

### 3.2. “Completed” có thể là failure

Java 17 `Future.isDone()` trả `true` khi computation kết thúc **bình thường, bị exception hoặc bị hủy**. Chẳng hạn:

```java
Future<String> result = executor.submit(() -> {
    throw new IllegalStateException("remote API failed");
});

// Khi result kết thúc, isDone() == true nhưng get() ném ExecutionException.
String value = result.get();
```

Đây là **đoạn minh họa trong context đã có `executor`**, không phải file chạy độc lập. `get()` không trả giá trị nếu callable throw; nó báo `ExecutionException` chứa nguyên nhân gốc. Lưu ý `get()` trước khi task kết thúc sẽ **block**, vì vậy code thực tế thường cần timeout.

## 4. Future: khi nào thật sự biết tác vụ đã kết thúc?

Interface `java.util.concurrent.Future<V>` có các API then chốt:

- `boolean isDone()`: không block; cho biết computation đã kết thúc theo Future. Không suy ra success.
- `boolean isCancelled()`: không block; cho biết Future bị hủy.
- `V get()`: block đến khi hoàn tất, rồi trả kết quả hoặc ném `ExecutionException`/`CancellationException`/`InterruptedException`.
- `V get(long timeout, TimeUnit unit)`: chờ tối đa khoảng thời gian đã chọn; có thể ném `TimeoutException`.
- `cancel(boolean mayInterruptIfRunning)`: **cố gắng** hủy; không bảo đảm thread hoặc mọi hành động ngoài đã dừng hoàn toàn.

Ví dụ mẫu trong phần code của một caller:

```java
Future<OrderSummary> future = executor.submit(this::buildSummary);
try {
    OrderSummary result = future.get(5, TimeUnit.SECONDS);
    publishResult(result);
} catch (TimeoutException ex) {
    future.cancel(true); // Yêu cầu hủy, không bảo đảm đã dừng mọi side effect.
    throw new IllegalStateException("Summary timed out", ex);
} catch (ExecutionException ex) {
    throw new IllegalStateException("Summary failed", ex.getCause());
}
```

Đây là **đoạn minh họa**, chưa biên dịch độc lập: cần `executor`, `OrderSummary`, `buildSummary`, `publishResult` và import classes liên quan. Vì `get(...)` còn có `InterruptedException`, caller phải khai báo throws hoặc bắt rồi **khôi phục interrupt flag** phù hợp; không nuốt interruption.

### 4.1. Timeout không tự hủy công việc

`get(5, SECONDS)` ném `TimeoutException` chỉ nói **caller đợi quá lâu**. Tác vụ có thể vẫn đang chạy. Nếu cần ngừng nó, phải quyết định chính sách cancel và thiết kế task cooperatively interruptible. Với I/O ngoài, **request timeout ở tầng HTTP/DB** có ý nghĩa hơn việc chỉ giới hạn thời gian `get`.

### 4.2. cancel(true) không bảo đảm dừng

Với `FutureTask`/`ExecutorService` thông thường, `cancel(true)` cố interrupt worker nếu nó đã chạy và worker được biết. Thread phải tự phản ứng đúng với interrupt; nhiều I/O hoặc side effect đã bắt đầu không thể “rollback” bằng interrupt.

Với `CompletableFuture`, `cancel(true)` hoạt động như exceptional completion và tham số `mayInterruptIfRunning` **không dùng để điều khiển interrupt** theo Javadoc Java 17. Đây là ví dụ rõ rằng “Future bị cancel” không đồng nghĩa “việc đang làm thực tế đã dừng ngay”.

### 4.3. Kết quả Future và tính nhất quán bộ nhớ

Theo Java Memory Model, các hành động trong asynchronous computation xảy ra-before những hành động sau khi `Future.get()` tương ứng ở thread khác. Vì vậy chờ `get` không chỉ chờ một cờ, mà còn là cơ chế đồng bộ hóa kết quả. Tuy nhiên đó **không phải transaction**: ghi file, commit database, publish message vẫn phải có quy ước xác nhận/durability riêng.

## 5. CompletableFuture: stage kết thúc không nhất thiết thành công

`CompletableFuture<T>` là một `Future` đồng thời hỗ trợ `CompletionStage`:

```java
CompletableFuture<Integer> stage =
        CompletableFuture.supplyAsync(() -> 40 + 2, executor);

int value = stage.join();
```

Đây là đoạn minh họa trong class đã có `executor`. `join()` block khi cần rồi trả `42` nếu thành công; nếu stage hoàn thành lỗi, `join()` có thể ném `CompletionException` unchecked, còn `get()` báo `ExecutionException` checked.

| Trạng thái | `isDone()` | `isCompletedExceptionally()` | Kết quả `join()` |
| --- | --- | --- | --- |
| Chưa hoàn thành | `false` | `false` | Chờ nếu gọi |
| Thành công | `true` | `false` | Trả giá trị |
| Thất bại với exception | `true` | `true` | Ném `CompletionException` thường bao root cause |
| Bị cancel | `true` | `true` | Ném `CancellationException` hoặc exception phù hợp |

Phân biệt thêm:

- `thenApply(fn)` nối một stage xử lý kết quả khi stage trước thành công.
- `thenCompose(fn)` ghép công việc bất đồng bộ tiếp theo mà `fn` trả về (flatten future).
- `whenComplete((value,error) -> ...)` chủ yếu quan sát sự hoàn tất; nếu không có xử lý recovery, lỗi của stage trước vẫn có thể lan tiếp.
- `exceptionally(ex -> fallback)` **có thể biến một stage lỗi thành stage thành công với fallback**. Muốn có báo cáo failure, phải theo dõi trạng thái stage gốc hoặc log lỗi, không chỉ xem stage sau `exceptionally`.
- `handle((value,error) -> ...)` có thể biến cả đường thành công và lỗi thành kết quả mới.
- `allOf(a,b,c)` đại diện cho việc **tất cả futures đầu vào đã hoàn thành**; nếu một input thất bại, allOf có thể hoàn thành lỗi. Nó không tự tạo ra danh sách kết quả và không tự làm rollback/cancel các task khác.
- `anyOf(a,b,c)` hoàn thành khi có **một** input hoàn tất, không đồng nghĩa toàn bộ batch xong.

Một ví dụ dùng `allOf` đúng:

```java
CompletableFuture<Void> all =
        CompletableFuture.allOf(customerStage, productStage, stockStage);
all.join(); // Chờ cả ba hoàn tất, propagate failure nếu có.
```

Đây là đoạn minh họa giả định ba futures đã được tạo. Nếu `all.join()` return bình thường thì chúng đã hoàn tất bình thường theo stage; nếu một stage thất bại, cần xem root cause và những side effect của các stage khác.

### 5.1. SupplyAsync không tự dùng Spring TaskExecutor

`CompletableFuture.supplyAsync(supplier)` không nhận executor; mặc định nó dùng cơ chế asynchronous execution của `CompletableFuture` (thường là `ForkJoinPool.commonPool()` theo JDK). Đừng nhầm nó luôn chạy qua bean `ThreadPoolTaskExecutor` mà Spring Boot cấu hình.

Nếu cần giới hạn threads/queue, bảo đảm tracing hoặc shutdown, **truyền một executor được quản lý**:

```java
CompletableFuture<Report> report =
        CompletableFuture.supplyAsync(this::loadReport, managedExecutor);
```

Đây là đoạn minh họa. `managedExecutor` là một `Executor` được chọn rõ, `loadReport` có kết quả kiểu `Report`.

### 5.2. orTimeout và completeOnTimeout có “giết” thread không?

`future.orTimeout(3, SECONDS)` khiến stage hoàn thành lỗi khi quá hạn, còn `completeOnTimeout(fallback, 3, SECONDS)` có thể hoàn thành bình thường bằng fallback. Những API đó **thay đổi trạng thái completion**, không bảo đảm interrupt hoặc hủy công việc nền đang tác động tới hệ thống ngoài.

Không xem một future đã timeout/complete fallback là bằng chứng remote job hoặc transaction ngoài đã dừng. Nếu task vẫn có side effect sau timeout, cần cơ chế cancellation/lease/idempotency riêng.

## 6. Spring @Async: lời gọi proxy đã trả về khác việc method đã chạy xong

Spring Framework cung cấp `@Async` để chuyển việc thực thi method sang `TaskExecutor`. Cách dùng chuẩn:

- Bật xử lý bất đồng bộ với `@EnableAsync` hoặc cấu hình tương đương.
- Đặt `@Async` trên method của **bean Spring**.
- **Gọi method qua Spring proxy**, thường từ một bean khác; self-invocation trong cùng instance mặc định **không** qua proxy nên annotation có thể không tác dụng.
- Với công việc có kết quả hoặc lỗi cần quan sát, method nên trả `Future<T>` hoặc `CompletableFuture<T>`. Với `void`, caller không có future để chờ; exception được xử lý qua cơ chế `AsyncUncaughtExceptionHandler`/logging phù hợp.
- Khi cần executor cụ thể, dùng `@Async("executorBeanName")` và đăng ký executor bean đúng tên.

Trong chế độ proxy mặc định, call từ một bean khác:

```java
CompletableFuture<String> handle = asyncService.loadData();
log.info("async invocation has returned"); // Không chứng minh task xong.
String data = handle.join();                 // Chờ kết quả hoặc nhận failure.
```

Đây là **đoạn minh họa**, cần `asyncService` là bean được inject và method `loadData` trả future. Không dùng `@Async` trực tiếp trên lifecycle callback như `@PostConstruct` với kỳ vọng cơ chế proxy sẽ giúp initialization bất đồng bộ; Spring khuyến cáo tách một bean làm nhiệm vụ gọi async method trên bean đích.

### 6.1. Exception từ @Async không tự thành exception của caller

Nếu `@Async CompletableFuture<T>` ném lỗi ở worker thread, lời gọi proxy có thể đã trả về từ lâu. Lỗi sẽ phản ánh qua future; caller chỉ biết nếu `get/join` hoặc gắn completion handler theo dõi failure.

Nếu method trả `void`, caller không có future và exception không thể được chuyển về caller theo cùng cách; cần `AsyncUncaughtExceptionHandler` hoặc logging/monitoring. Một runner gọi một method `@Async void` rồi return **không tự fail startup** khi công việc nền throw sau đó.

### 6.2. Self-invocation: dễ bị tưởng có submit

Ví dụ phản ví dụ:

```java
@Service
class JobService {
    void dispatch() {
        loadAsync(); // Gọi qua this, bỏ qua proxy trong chế độ Spring AOP mặc định.
    }

    @Async
    public CompletableFuture<String> loadAsync() {
        return CompletableFuture.completedFuture("OK");
    }
}
```

Đây là **class minh họa**, cần import `@Service`, `@Async`, `CompletableFuture` và bật `@EnableAsync`. Lời gọi trong cùng bean không đi qua async proxy nên body có thể thực thi **đồng bộ trên caller thread**. Khi review một vấn đề “submit đã trả về hay chưa”, hãy kiểm tra việc có thật sự sử dụng async proxy hay không.

## 7. Ví dụ chạy được: Spring Boot 3.3 kiểm chứng submit != completed

Ví dụ thiết kế có kiểm soát bằng `CountDownLatch` thay vì dùng `Thread.sleep(...)` để suy ra thứ tự race-dependent. Tác vụ nền **không thể hoàn thành** trước khi runner chủ động mở latch. Nhờ vậy stdout ổn định, thể hiện rõ:

- Sau lời gọi `@Async`, caller nhận future và `isDone() == false`.
- Runner mở latch rồi `future.get(...)` chờ cho tới khi computation hoàn thành thành công.
- Chỉ sau runner trả về, Boot phát `ApplicationReadyEvent`.

### 7.1. Cấu trúc project và Gradle

Dùng Java 17+, Gradle Wrapper và Spring Boot 3.3.13.

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
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
}
```

File `settings.gradle`:

```groovy
rootProject.name = 'submit-vs-complete-lab'
```

File `src/main/resources/application.properties`:

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.main.log-startup-info=false
logging.level.root=ERROR
```

Không cần starter web; bài kiểm tra timing của thread, future và mốc startup, không cần port HTTP.

### 7.2. File Java hoàn chỉnh

Tạo file **`src/main/java/com/example/tasks/SubmitVsCompleteApplication.java`**:

```java
package com.example.tasks;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableAsync
public class SubmitVsCompleteApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                SpringApplication.run(SubmitVsCompleteApplication.class, args)) {
            System.out.println("05 main: run returned");
        }
    }

    @Bean("learningExecutor")
    ThreadPoolTaskExecutor learningExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setQueueCapacity(4);
        executor.setThreadNamePrefix("learning-");
        return executor;
    }

    @Bean
    ApplicationRunner verifyAsyncCompletion(AsyncWorker worker) {
        return args -> {
            CountDownLatch release = new CountDownLatch(1);

            // Invocation qua Spring proxy: gửi việc và nhận handle.
            CompletableFuture<String> handle = worker.prepare(release);

            // Worker có thể đã được schedule nhưng đang chờ latch.
            System.out.println("02 submitted: done=" + handle.isDone());

            // Từ đây worker được phép hoàn tất.
            release.countDown();

            // Bắt buộc đợi kết quả trước khi cho runner kết thúc.
            String value = handle.get(10, TimeUnit.SECONDS);
            System.out.println("03 completed: " + value);
        };
    }

    @EventListener
    public void onStarted(ApplicationStartedEvent event) {
        System.out.println("01 ApplicationStartedEvent");
    }

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println("04 ApplicationReadyEvent");
    }

    @Component
    public static class AsyncWorker {

        @Async("learningExecutor")
        public CompletableFuture<String> prepare(CountDownLatch release) {
            try {
                release.await();
                return CompletableFuture.completedFuture("data prepared");
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return CompletableFuture.failedFuture(ex);
            }
        }
    }
}
```

**Tại sao mã này có tính kiểm chứng?**

1. `@EnableAsync` bật cơ chế AOP async; `AsyncWorker` là bean Spring được inject vào runner, nên lời gọi `worker.prepare(release)` đi qua proxy.
2. `@Async("learningExecutor")` chọn đúng bean `ThreadPoolTaskExecutor` được quản lý. Bean được Spring initialize và shutdown theo lifecycle container; ví dụ không tự tạo thread pool rò rỉ.
3. `CountDownLatch(1)` có count bằng 1; ngay khi caller vừa nhận Future, body async **không thể hoàn thành** vì nó phải đợi `release.await()`.
4. Vì caller chưa gọi `release.countDown()`, dòng `02` **luôn** nhìn thấy `handle.isDone() == false` nếu việc gửi được chấp nhận và code chạy theo cấu hình này.
5. Runner mở latch rồi gọi `get(10, SECONDS)`. Nếu worker trả kết quả bình thường, `get` return với value. Nếu worker throw hoặc bị interrupt, runner nhận failure; nếu quá thời hạn, runner nhận `TimeoutException`. Các lỗi ấy **được phép thoát ra khỏi runner**, nên Boot có thể xử lý startup failure thay vì báo ready giả.
6. `ApplicationStartedEvent` đến sau refresh, trước runner. `ApplicationReadyEvent` chỉ được phát sau khi runner return bình thường. Vì thế dòng `04` đến **sau** dòng `03`.
7. `try-with-resources` đóng context sau khi `SpringApplication.run(...)` return. Do đã chờ task hoàn thành, việc đóng executor không cắt ngang task ví dụ.

### 7.3. Lệnh chạy và stdout

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

macOS/Linux:

```bash
./gradlew bootRun
```

Với project đúng như trên, không truyền tham số và task được thực thi thành công, **những dòng do mã Java chủ động in** theo thứ tự:

```text
01 ApplicationStartedEvent
02 submitted: done=false
03 completed: data prepared
04 ApplicationReadyEvent
05 main: run returned
```

Gradle có thể in thêm các dòng task/build. Trong ví dụ, **worker thread không in log**, nên thứ tự dòng đánh số không bị tranh chấp giữa hai thread. Latch quyết định thời điểm task được phép hoàn tất, không phụ thuộc vào một khoảng `sleep` ước lượng.

**Điểm cần hiểu:** khi dòng `02` được in, một lời gọi `@Async` đã trả về và caller đã có handle, nhưng task **chưa completed**. Sau `get(...)` return bình thường mới in `03`. Vì runner chờ, `ApplicationReadyEvent` ở dòng `04` chỉ xuất hiện **sau thành công của công việc bắt buộc**.

### 7.4. Thử biến thể: chỉ submit rồi return

Thay body runner bằng logic sau (**đoạn minh họa thay thế**, không phải file độc lập):

```java
return args -> {
    CountDownLatch release = new CountDownLatch(1);
    CompletableFuture<String> handle = worker.prepare(release);
    System.out.println("submitted; done=" + handle.isDone());

    // Runner return mà không release latch, không đợi handle!
    // Điều này khiến startup có thể báo ready trước khi task hoàn tất.
};
```

**Không chạy nguyên biến thể này trong production:** latch không được mở nên task có thể bị kẹt, khiến shutdown kéo dài. Mục đích là cho thấy contract: Boot thấy runner đã return, không tự biết một Future vẫn đang đợi. Nếu thay bằng task có I/O hoặc đợi tài nguyên thực, tình trạng tương tự có thể xảy ra mà không có latch.

Trong code thực tế, hãy **lưu/giám sát handle** hoặc chỉ trả về ngay khi công việc thật sự tùy chọn, và xử lý teardown khi dừng ứng dụng. Nếu công việc phải hoàn thành trước readiness, giữ mô hình `get(timeout)`/`join` có deadline hoặc cung cấp readiness gate đáng tin.

### 7.5. Thử biến thể: worker hoàn thành lỗi

Thay thân method `prepare` để sau `release.await()` trả:

```java
return CompletableFuture.failedFuture(
        new IllegalStateException("required initialization failed"));
```

Đây là **đoạn thay thế trong method `@Async`**, không độc lập. `handle.get(...)` trong runner sẽ ném `ExecutionException` chứa root cause; runner không return bình thường, Boot sẽ xử lý startup failure. Không có `ApplicationReadyEvent` theo đường startup thành công.

Nếu **bỏ `get(...)`** và chỉ submit, lỗi worker đến sau đó có thể chỉ nằm trong Future; Boot có thể vẫn phát ready, nên cần quan sát failure độc lập và quyết định chính sách fallback/retry.

### 7.6. Thử biến thể: self-invocation

Đặt method `@Async` và lời gọi trực tiếp `this.prepare(release)` trong cùng bean `AsyncWorker`. Với proxy mode mặc định, lời gọi nội bộ **không qua proxy**, có thể chạy đồng bộ. Khi body đang chờ `release.await()` mà release chỉ được gọi sau khi method return, bạn tạo deadlock. Vì vậy thí nghiệm dùng **hai bean** và inject proxy từ container.


## 8. Startup Spring Boot: runner gửi việc nền có làm app ready chưa?

Trong luồng Boot 3.3.x:

```text
ApplicationContext refreshed
   |
   +--> ApplicationStartedEvent
   +--> LivenessState.CORRECT
   |
   +--> gọi ApplicationRunner / CommandLineRunner
   |      +--> executor.submit(job)
   |      |      +--> queued/running/pending
   |      +--> runner return
   |
   +--> ApplicationReadyEvent
   +--> ReadinessState.ACCEPTING_TRAFFIC
```

**Spring Boot chờ lời gọi runner, không tự chờ mọi async job mà runner đã gửi.** Nếu runner `run(...)` kết thúc ngay sau `submit`, Boot vẫn có thể đi đến mốc ready trong khi job còn pending.

Đây là vấn đề thực tế nếu job là điều kiện bắt buộc: nạp catalog, warm cache thiết yếu, đồng bộ quyền truy cập hoặc kiểm tra an toàn dữ liệu trước khi nhận request. Một trạng thái ready giả có thể khiến load balancer gửi traffic vào instance chưa có dữ liệu.

Phân loại công việc:

| Loại công việc | Có cần đợi trước ready? | Cách tiếp cận |
| --- | --- | --- |
| Bước khởi tạo bắt buộc cho mọi request | **Có**, theo hợp đồng | Runner đợi Future thành công có timeout, hoặc readiness gate rõ |
| Cập nhật cache tùy chọn, có fallback đúng | Có thể không | Submit, đo trạng thái degraded, retry có giới hạn |
| Background maintenance không chặn phục vụ | Không nhất thiết | Quản lý bằng executor/scheduler lifecycle và monitoring |
| Task phục vụ một request HTTP | Caller/request-specific | Trả trạng thái 202 + job ID hoặc đợi theo SLA; không dùng startup readiness để mô tả kết quả của từng request |
| Stream/consumer dài hạn | Không thể “hoàn thành” theo kiểu batch | SmartLifecycle với start/stop, kiểm tra “đã subscribe và sẵn sàng” riêng |

### 8.1. ApplicationStartedEvent và ApplicationReadyEvent không tự quan sát mọi task

`ApplicationStartedEvent` được phát khi context đã refresh, trước runner. `ApplicationReadyEvent` được phát sau khi các runner hoàn tất **lời gọi đồng bộ**. Liveness/readiness của Boot có nghĩa cấp ứng dụng nhưng không suy đoán mọi thread tự tạo đã kết thúc.

Một `SmartLifecycle.start()` chỉ submit task rồi return cũng có thể bị nhầm tương tự: component đã được yêu cầu start, nhưng worker chưa thật sự sẵn sàng.

### 8.2. Khi công việc không chặn ready, đừng giấu lỗi

Với background task tùy chọn, cho Boot sẵn sàng không phải sai, miễn **fallback thực sự hợp lệ**. Cần:

- Metrics riêng: `submitted`, `running`, `succeeded`, `failed`, `cancelled`, `rejected`.
- Retry bounded + backoff/jitter cho lỗi có thể phục hồi, không retry vô hạn.
- Trạng thái degraded/health tùy thuộc tính bắt buộc.
- Đường đóng task khi shutdown và khả năng phục hồi nếu process chết.
- Tracing/correlation ID từ request tới background work.

Không dùng việc “đã submit” để ghi record nghiệp vụ ở trạng thái **DONE**. Nếu API trả ngay, status nên là `ACCEPTED`/`PENDING`, rồi update thành `SUCCEEDED`/`FAILED` sau khi hoàn tất và có bằng chứng đúng.

## 9. HTTP 202 Accepted không phải kết quả thành công cuối cùng

Khi client gửi một job dài và server trả `HTTP 202 Accepted`, ngữ nghĩa chuẩn là request đã được chấp nhận để xử lý, nhưng xử lý có thể **chưa hoàn tất** và có thể thất bại về sau. Đây là ví dụ rất gần với `ExecutorService.submit`.

Một thiết kế API phù hợp:

```text
POST /reports
-> 202 Accepted
-> {"jobId":"rpt-123","status":"PENDING","statusUrl":"/reports/rpt-123"}

GET /reports/rpt-123
-> {"jobId":"rpt-123","status":"RUNNING"}

GET /reports/rpt-123
-> {"jobId":"rpt-123","status":"SUCCEEDED","downloadUrl":"/reports/rpt-123/file"}
```

Đây là **HTTP transcript minh họa**, không phải một Spring Controller được triển khai trong ví dụ chạy. Nếu task thất bại, trạng thái cuối cần báo rõ `FAILED` và lý do không nhạy cảm.

**Đặc biệt:** HTTP 202 chỉ nói request được server chấp nhận theo contract HTTP. Nó **không tự tạo một queue durable**, không bảo đảm job sống qua JVM restart, không tự cung cấp idempotency hoặc trạng thái tracking. Nếu server chỉ dùng in-memory executor, process crash có thể làm mất công việc đã “accepted” nhưng chưa xử lý. Với công việc quan trọng, cân nhắc database-backed job table, message broker durable, outbox pattern và recovery worker.

### 9.1. Mối liên hệ với transaction

Nếu một method đang trong transaction rồi submit background task, thread async **không tự kế thừa transaction context** của caller. Task có thể chạy trước khi caller commit và đọc dữ liệu chưa thấy; hoặc transaction caller rollback sau khi task đã gửi message ra ngoài.

Với tác vụ chỉ nên chạy sau commit, dùng cơ chế transaction synchronization/`@TransactionalEventListener(phase = AFTER_COMMIT)`, outbox hoặc queue phù hợp. Không coi “gọi submit sau một lệnh save” là bảo đảm transaction đã commit.

## 10. Task queue, thread pool và backpressure

Một `ThreadPoolTaskExecutor` có thể có:

- `corePoolSize` và `maxPoolSize`: số worker được duy trì/mở rộng tùy cấu hình.
- `queueCapacity`: sức chứa queue khi thread đang bận.
- `RejectedExecutionHandler`: quyết định điều gì xảy ra khi executor không thể nhận công việc.
- Tên thread, metrics và timeout/shutdown policies cần cấu hình phù hợp.

Ba trạng thái có tính vận hành khác:

```text
ACCEPTED but QUEUED   -> chưa được thread thực thi
RUNNING               -> worker đang thực thi
COMPLETED             -> worker đã kết thúc (success/failure/cancel)
```

Một queue sâu có thể khiến “submit latency” thấp nhưng “time-to-start” và “time-to-complete” cao. Nếu chỉ đo `submit` return nhanh, dashboard có thể báo thành công trong khi người dùng đợi hàng phút.

Đối với server nhận nhiều job, cần thiết kế **backpressure**:

- Giới hạn concurrency và queue theo tài nguyên thật; tránh queue vô hạn làm tăng bộ nhớ.
- Khi overload, từ chối có chủ đích (ví dụ HTTP 429/503 tùy API contract) hoặc đẩy vào hệ thống job durable có capacity rõ ràng.
- Đo thời gian `queue wait` riêng với `execution duration` và `end-to-end completion latency`.
- Không retry immediate vô hạn trên `RejectedExecutionException`.
- Không để `CallerRunsPolicy` vô tình block event loop/HTTP request thread quá lâu khi pool bận.
- Khi queue full, monitor cả số task bị reject, task active, queue depth, timeout và failure rate.

**Chú ý:** `ThreadPoolTaskExecutor` là Spring bean được quản lý vòng đời. Tự tạo một `new ThreadPoolExecutor(...)` không đóng có thể giữ thread, làm leak và khiến ứng dụng không shutdown sạch. Cần quy định owner executor và phương thức shutdown rõ.

## 11. Shutdown: “đã gọi shutdown” vẫn chưa chắc mọi task hoàn thành

`ExecutorService.shutdown()` bắt đầu quy trình shutdown và ngừng nhận task mới; nó **không chờ đến khi mọi task đã thực hiện xong**. Có thể dùng `awaitTermination(timeout, unit)` để đợi executor chấm dứt, nhưng kiểm tra boolean return và xử lý trường hợp timeout.

Minh họa:

```java
executor.shutdown();
boolean finished = executor.awaitTermination(10, TimeUnit.SECONDS);
if (!finished) {
    // Hệ thống cần chính sách riêng cho task còn pending/in-flight.
}
```

Đây là đoạn minh họa trong nơi có `executor`, chưa độc lập. `shutdownNow()` cũng chỉ **cố gắng** dừng task đang chạy và trả danh sách những task chưa bắt đầu trong một số executor; nó không bảo đảm mọi side effect đã dừng.

Trong Spring Boot, lifecycle của `TaskExecutor` bean có thể được tích hợp với shutdown context, nhưng hành vi chờ task và thời hạn phụ thuộc loại executor/cấu hình. Nếu cần không mất job, không nên dựa chỉ vào JVM shutdown hook. Dùng durable queue/checkpoint/idempotent jobs khi nhiệm vụ phải sống qua crash.

### 11.1. Khác biệt giữa Future completed và business committed

Một `Future` thành công chỉ có nghĩa method/task đã return bình thường. Nếu task:

1. Gửi HTTP request nhưng không kiểm response,
2. Ghi database nhưng transaction chưa commit,
3. Đưa message vào buffer nhưng chưa được broker ack,
4. Khởi tạo background thread thứ hai rồi return,

thì `Future` đầu tiên hoàn tất **không đủ** để khẳng định outcome cuối cùng theo nghiệp vụ. API của task phải định nghĩa “thành công” bằng checkpoint thích hợp; nếu cần ack ở broker, chờ acknowledgement trước khi trả success.

## 12. Viết test không phụ thuộc thời gian ngủ

Dùng `Thread.sleep(100)` rồi `assertFalse(future.isDone())` có thể pass/fail theo tốc độ máy, CPU contention và CI. Nên dùng primitive đồng bộ hóa:

- `CountDownLatch`: tạo một rào chắn để điều khiển thời điểm task được phép chạy/hoàn tất.
- `CyclicBarrier` hoặc `Phaser`: phối hợp nhiều thread ở những pha đã định nghĩa.
- `Future.get(timeout)`: giới hạn thời gian chờ, nhận failure có cấu trúc.
- `CompletableFuture`: tạo stage có thể complete thủ công trong unit test và kiểm tra dependent callbacks.
- `Awaitility` hoặc cơ chế polling bounded nếu cần quan sát event bất đồng bộ và eventual consistency.

Với test tích hợp, kiểm tra **cả hai đường**:

1. Sau khi gửi việc nhưng trước khi mở latch: `future.isDone() == false`, status nghiệp vụ là `PENDING/RUNNING` chứ không phải `DONE`.
2. Sau khi mở latch, Future hoàn thành thành công và caller quan sát kết quả: status chuyển `SUCCEEDED`.
3. Task ném exception: Future hoàn thành lỗi, status phải là `FAILED`, không phải `SUCCEEDED`.
4. Executor từ chối: handle có thể không được trả; request cần phản ánh rejection.
5. Task bị cancel/timeout: phải báo trạng thái đúng và xác định side effects có thể tiếp tục hay không.
6. Runner đợi task bắt buộc: ready chỉ đến khi task đã thành công.
7. Runner chỉ gửi task tùy chọn: readiness chính xác theo contract fallback và monitoring.

Đừng viết assertion phụ thuộc vào thứ tự log từ hai thread nếu không có đồng bộ hóa; dùng latch/future để kiểm chứng các quan hệ happens-before.

## 13. Các sai lầm phổ biến

| Nhận định hoặc dấu hiệu | Vì sao sai? | Hướng sửa |
| --- | --- | --- |
| “`submit` return là job đã hoàn thành” | Có thể còn queue hoặc running | Theo dõi Future/ACK và status riêng |
| “`isDone() == true` là thành công” | Failure/cancellation cũng tạo done | `get/join`, `isCompletedExceptionally` và contract kết quả |
| “Có future nghĩa việc chắc đã bắt đầu” | Có thể chưa được thread lấy khỏi queue | Phân biệt accepted/queued/running |
| “`cancel(true)` chắc cắt mọi I/O” | Interrupt/cancellation best effort; CompletableFuture không tự interrupt | Timeout I/O, cooperative cancellation, idempotency |
| “`get(timeout)` tự hủy task” | Chỉ timeout caller đang chờ | Thiết kế cancel, downstream deadline |
| “`@Async` trong cùng class luôn chạy thread khác” | Self-invocation bỏ qua proxy | Gọi qua bean khác/proxy hợp lệ |
| “`@Async void` exception làm caller throw” | Caller không có Future | Handler/logging/metrics, dùng Future khi cần result |
| “`CompletableFuture.supplyAsync` luôn dùng Spring executor” | Không truyền executor thì thường dùng common pool | Chỉ định executor bean có capacity rõ |
| “Runner submit rồi return thì Boot đợi hết background jobs” | Boot chỉ chờ lời gọi runner | Await Future bắt buộc hoặc readiness gate |
| “HTTP 202 nghĩa đã xử lý xong” | 202 là accepted, có thể pending | Job ID, status endpoint, durability |
| “Future thành công thì DB chắc commit” | Chưa chắc task await commit/ack | Định nghĩa success ở boundary nghiệp vụ |
| “Task cuối cùng xong thì mọi task đều xong” | Có thể những task trước/sau khác | Dùng `allOf` hoặc tracking batch đúng |
| “`shutdown` return nghĩa executor hết task” | Shutdown chỉ khởi động quá trình dừng | `awaitTermination` và timeout |
| “Queue càng dài càng tốt, không mất job” | In-memory queue có thể mất khi process crash | Bounded queue/durable broker phù hợp |
| “Dùng `Thread.sleep` là test async ổn định” | Race phụ thuộc scheduling | Latch, barrier, futures có timeout |

### 13.1. Checklist debug một job “đã gửi nhưng chưa có kết quả”

1. Tìm **đúng nơi submit**: `execute`, `submit`, `@Async`, `supplyAsync` hay queue ngoài?
2. Kiểm tra submission có throw/reject không; nếu có, request chưa được accepted.
3. Xác định executor thật và thread name; có dùng đúng Spring proxy và `@EnableAsync` không?
4. Đọc metrics queue size, active threads, completed/failed counts và task wait time.
5. Kiểm tra Future: `isDone`, `isCancelled`, `isCompletedExceptionally`, `get` hoặc callback completion.
6. Kiểm tra exception của worker; đặc biệt `@Async void` và các Future không ai observe.
7. Xác định business ACK: DB commit, file fsync khi cần, broker ack, downstream response hợp lệ.
8. Kiểm tra caller có timeout và cancellation policy không; thread có bị stuck ở I/O không?
9. Nếu xảy ra trong startup, kiểm tra runner đã return và `ApplicationReadyEvent` đã phát chưa.
10. Nếu có transaction, kiểm tra async thread có đang chạy trước commit không.
11. Nếu JVM restart, hệ thống có thể phục hồi job pending không? In-memory queue có phù hợp?
12. Ghi log ID tác vụ, phase, duration, outcome và correlation ID; không ghi secret/payload nhạy cảm.

## 14. Bài tập và câu hỏi tự kiểm tra

**Câu 1.** Một `ExecutorService.submit` trả về Future ngay. Công việc đã hoàn tất chưa?

**Đáp:** Chưa đủ bằng chứng. Future có thể còn queued/running. Cần kiểm tra completion và quan sát kết quả.

**Câu 2.** `future.isDone()` true và `get()` ném `ExecutionException`. Tác vụ thành công không?

**Đáp:** Không. Nó đã kết thúc **thất bại**.

**Câu 3.** `@Async` method bị gọi trực tiếp trong cùng bean. Có chắc nó chạy trên worker thread?

**Đáp:** Không, trong proxy mode mặc định self-invocation không được intercept.

**Câu 4.** Một runner submit job bắt buộc rồi return; Boot phát Ready event. Điều này có chứng minh job hoàn tất?

**Đáp:** Không. Boot chỉ biết runner return. Phải đợi Future thành công hoặc điều khiển readiness đúng.

**Câu 5.** Gọi `CompletableFuture.cancel(true)` có đảm bảo interrupt công việc nền không?

**Đáp:** Không. Với CompletableFuture, cancel là exceptional completion; flag `mayInterruptIfRunning` không điều khiển interrupt theo API.

**Câu 6.** `future.get(5, SECONDS)` ném TimeoutException. Tác vụ đã bị hủy chưa?

**Đáp:** Chưa. Chỉ thời gian chờ của caller hết. Tác vụ có thể tiếp tục chạy.

**Câu 7.** `@Async void` throw exception. Caller có tự nhận `ExecutionException` không?

**Đáp:** Không vì caller không có Future. Phải có handler/monitoring khác hoặc đổi API để trả Future.

**Câu 8.** Một API `POST /reports` trả 202. Dữ liệu báo cáo đã sẵn sàng tải chưa?

**Đáp:** Chưa chắc. Cần status endpoint và trạng thái `SUCCEEDED`/download link thực.

**Câu 9.** `ExecutorService.shutdown()` return có chứng minh mọi task hoàn tất?

**Đáp:** Không. Đó mới là tín hiệu bắt đầu shutdown; có thể dùng `awaitTermination`/theo dõi Future.

**Câu 10.** Khi nào một Future completed cũng có thể chưa mang business success?

**Đáp:** Khi task return trước database commit, broker acknowledgement, remote operation hoặc một task nền cấp hai.

## 15. Ghi nhớ và tài liệu chính thức

- **Submitted/accepted** là đã giao việc theo contract executor, chưa chắc started hay completed.
- **Completed** gồm cả success, failure và cancellation; `isDone` một mình **không** xác nhận thành công.
- **Future.get / CompletableFuture.join** cho phép đợi/quan sát kết quả, nhưng phải tính timeout, exception, interruption và tính đúng của business ACK.
- **Spring @Async** cần `@EnableAsync` và gọi qua proxy; dùng Future nếu caller cần quan sát outcome, tránh `void` cho công việc bắt buộc.
- **Spring Boot runner** mà chỉ submit rồi return có thể khiến `ApplicationReadyEvent` xảy ra **trước khi task thực sự xong**.
- **Queue/executor** cần capacity, rejection handling, monitoring và shutdown lifecycle; accepted vào memory queue không đồng nghĩa durable.
- **HTTP 202 Accepted** và trạng thái job `PENDING` không phải `SUCCEEDED`; cần job ID và endpoint theo dõi.
- **Đối với startup task bắt buộc**, chờ kết quả xác nhận có timeout hoặc readiness gate rõ ràng; không dùng sleep đoán thời điểm.

Tài liệu tham khảo:

- [Java SE 17 — Future API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html), `isDone`, `get`, `cancel` và memory consistency.
- [Java SE 17 — CompletableFuture API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html), exceptional completion, `join`, `allOf`, cancellation.
- [Spring Framework 6.1 — @Async API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/annotation/Async.html), supported return types và proxy.
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html), `@EnableAsync`, `@Async`, async exception handling.
- [Spring Boot 3.3 — SpringApplication](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html), lifecycle event, runner và readiness.
- [Spring Framework 6.1 — ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html), pool/queue semantics và lifecycle.

Muốn trả lời “job xong chưa?”, hãy xác định rõ **đã gửi**, **đã được worker chạy**, **Future đã hoàn tất theo cách nào**, **caller đã kiểm tra kết quả** và **side effect nghiệp vụ đã được xác nhận chưa**. Đây là những ranh giới độc lập cần được đo, không thể thay nhau bằng một log “submitted”.
