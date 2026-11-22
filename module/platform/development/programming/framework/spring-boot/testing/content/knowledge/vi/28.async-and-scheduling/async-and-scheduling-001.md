# Kiểm thử @Async qua proxy và executor được cấu hình trong Spring Boot

## 1. Bài toán: một phương thức có @Async chưa đủ chứng minh chạy bất đồng bộ

Trong Spring Boot, ứng dụng thường dùng `@Async` để gửi thông báo, xuất báo cáo, ghi audit, xử lý ảnh hoặc gọi một dịch vụ chậm mà không giữ luồng xử lý HTTP. Nhưng một bài test chỉ gọi phương thức rồi assert kết quả có thể **xanh dù @Async không hoạt động**.

Những rủi ro phổ biến:
- Test tạo đối tượng bằng `new EmailWorker()` thay vì lấy Spring bean, vì vậy **không có AOP proxy**.
- Một method trong cùng bean gọi `this.sendAsync()`, làm **self-invocation bỏ qua proxy**.
- `@Async` không có `@EnableAsync` trong test context, hoặc bean bị mock hoàn toàn.
- Không xác định rõ executor: tác vụ chạy trong một executor mặc định khác với thread pool mong muốn.
- Test dùng `Thread.sleep(100)` rồi assert dữ liệu; chạy trên CI chậm thì bị flaky.
- Method `void @Async` ném lỗi nhưng test không nhận được exception, tạo false positive.
- Kết quả kiểm thử dựa vào `future.isDone()` ngay lúc gọi, vốn có race condition nếu tác vụ quá ngắn.
- Test `@Transactional` ở thread chính nhưng lại kỳ vọng transaction tự đi theo worker thread.

**Mục tiêu bài học** là kiểm thử **đúng hai hợp đồng**:

1. **Proxy contract:** lời gọi phải đi qua bean Spring được `@EnableAsync` tạo proxy, nhờ đó phương thức chạy trên thread khác và caller có thể tiếp tục.
2. **Executor contract:** `@Async("tênExecutor")` chọn đúng bean `ThreadPoolTaskExecutor` (hoặc một `Executor` được cấu hình), với thread prefix, concurrency/queue/rejection và lifecycle theo chủ đích.

Bài dùng **Java 17+, Spring Boot 3.5.x, Spring Framework 6.x, JUnit Jupiter**. Ví dụ hoàn chỉnh gồm hai named executors, Spring service `@Async`, service gọi qua proxy, và các JUnit integration tests dùng `CountDownLatch`/`CompletableFuture` để **đồng bộ hóa deterministically thay vì ngủ một khoảng thời gian tùy ý**.

## 2. @Async chạy ra sao ở mức Spring AOP?

Khi bật `@EnableAsync`, Spring đăng ký hạ tầng nhận diện các phương thức `@Async` và áp dụng **async advice** trên bean theo chế độ mặc định `AdviceMode.PROXY`.

```text
JUnit test thread (T0)
      |
      | @Autowired BackgroundJobs  [Spring bean/proxy]
      |
      +--> proxy: intercept @Async("notificationExecutor")
                      |
                      +--> submit Callable/Runnable vào executor bean
                      |
                      +--> trả về CompletableFuture cho T0
                                 |
                       worker thread (T1)
                                 |
                         method body thực thi
                                 |
                    kết quả/exception hoàn tất future
                                 |
                    T0 get()/join() quan sát outcome
```

Điểm khác biệt cực kỳ quan trọng:

```java
// Đúng: jobs là Spring-managed bean; lời gọi đi qua proxy.
CompletableFuture<String> result = jobs.captureThreadName();

// Sai nếu muốn test proxy: tự tạo instance ngoài Spring.
BackgroundJobs plain = new BackgroundJobs();
CompletableFuture<String> result2 = plain.captureThreadName();
```

Hai dòng là **minh họa trong scope có biến jobs và class BackgroundJobs**. Với đối tượng được `new`, annotation không tự bật bất kỳ scheduler/executor nào. Method Java chạy đồng bộ như một lời gọi thông thường, cho dù vẫn có `@Async` trong mã nguồn.

### 2.1. @EnableAsync là điều kiện cần, không phải toàn bộ cấu hình

```java
@SpringBootApplication
@EnableAsync
public class AsyncDemoApplication {
}
```

Đây là đoạn cấu hình minh họa, cần imports Spring Boot/Scheduling. `@EnableAsync` bật asynchronous-method execution cho các bean thuộc context. Nó **không** tự khiến:
- Mọi method Java chạy nền.
- Một method `private` được proxy intercept.
- Một lời gọi `this.asyncMethod()` trở thành external proxy call.
- Code chạy trong một thread mới mang theo ThreadLocal transaction/security/request context.
- Một `@Scheduled` task tự xuất hiện nếu không bật `@EnableScheduling`.

**Chú ý:** `@Async` không hỗ trợ trên các method được khai báo trong chính `@Configuration` class theo Javadoc Spring. Đặt asynchronous business method trong `@Service`/component riêng.

### 2.2. Tại sao self-invocation mất bất đồng bộ?

```java
@Service
class NotificationService {
    public CompletableFuture<String> callInside() {
        return sendAsync(); // this.sendAsync(): không đi qua proxy
    }

    @Async("notificationExecutor")
    public CompletableFuture<String> sendAsync() {
        return CompletableFuture.completedFuture(
                Thread.currentThread().getName());
    }
}
```

Đoạn trên là ví dụ minh họa, cần `@EnableAsync`, bean executor và imports. Trong `callInside()`, lệnh `sendAsync()` gọi **trực tiếp trên target object**, không vòng qua proxy, vì thế trả về `completedFuture` chứa **tên thread của caller**.

Cách sửa được khuyến nghị: **tách method @Async sang một bean khác** rồi inject bean đó vào caller. Các kỹ thuật tự inject proxy hoặc `AopContext.currentProxy()` có thể thực hiện trong một số setup nhưng tăng coupling, khó test và không nên là thiết kế mặc định.

### 2.3. Interface-based proxy, class-based proxy và giới hạn method

Spring AOP mặc định dùng proxy. Nếu target có interface, JDK dynamic proxy có thể được sử dụng; trong cấu hình khác Spring có thể dùng class-based proxy. Do vậy:
- Ưu tiên phương thức `public` trên bean được gọi **từ bên ngoài bean**.
- `private` không thể được AOP proxy intercept.
- `final` methods không thể được subclass proxy override; `final` classes có thể cản class-based proxy.
- `@PostConstruct` không phải vị trí phù hợp để dựa vào `@Async` trên chính bean, vì proxy/lifecycle chưa bảo đảm.
- Nếu dùng `@EnableAsync(mode=AdviceMode.ASPECTJ)` với weaving thực, semantics self-invocation khác; **bài này chỉ kiểm thử proxy mode mặc định**.

**Kiểm thử proxy** không nên chỉ assert `@Async` annotation tồn tại bằng reflection. Cần lấy bean từ Spring context, gọi method thật và xác minh thread/executor behavior.

## 3. @Async cần trả kiểu nào, lỗi đi về đâu?

Spring Framework `@Async` hỗ trợ method trả **`void` hoặc `Future`**; khi cần quan sát kết quả, dùng `CompletableFuture<T>` rất thuận tiện.

```java
@Async("notificationExecutor")
public CompletableFuture<String> compute() {
    String value = Thread.currentThread().getName();
    return CompletableFuture.completedFuture(value);
}
```

Đây là một đoạn method minh họa. Spring async proxy trả một future đại diện execution thực. Còn **implementation** của method có thể trả `CompletableFuture.completedFuture(value)` sau khi đã tính kết quả trên worker thread; Spring sẽ chuyển/hoàn tất future được trả cho caller tương ứng.

| Method signature | Caller quan sát được gì? | Cách test |
|---|---|---|
| `@Async void send()` | Không có future nhận completion/error | Quan sát side effect/callback hoặc `AsyncUncaughtExceptionHandler` |
| `@Async Future<T> load()` | `Future.get()` | Assert result/cause, timeout |
| `@Async CompletableFuture<T> load()` | `get()`, `join()`, composition | Thường là lựa chọn tốt nhất |
| Method Java bình thường trả `CompletableFuture` | Không mặc nhiên chạy trong executor | Test xem ai thực sự thực thi |
| `@Async Mono<T>` tùy ý | **Không phải return type được hỗ trợ chung bởi @Async** | Reactive pipeline dùng Reactor scheduler/Context riêng |

**Ngoại lệ:**
- Với `CompletableFuture.get()`, lỗi task thường xuất hiện dưới `ExecutionException`, nguyên nhân thật ở `getCause()`.
- Với `CompletableFuture.join()`, lỗi thường được bọc trong `CompletionException`.
- Với `void @Async`, caller **không** thể bắt exception phát ra ở worker bằng `assertThrows(() -> service.voidAsync())` như lời gọi đồng bộ. Cần handler/probe hoặc đổi API sang future.
- Lỗi **ngay khi submit** (ví dụ pool từ chối task) có thể ném **đồng bộ** ở caller dưới dạng `TaskRejectedException`. Đây là lỗi khác với exception phát sinh trong worker task.

### 3.1. Đừng biến future thành phép đo tốc độ

```java
CompletableFuture<String> future = worker.compute();
assertFalse(future.isDone()); // KHÔNG ổn định nếu compute quá nhanh!
```

Task có thể đã hoàn tất trước khi `isDone()` được gọi; một implementation bất đồng bộ đúng vẫn làm assertion fail. Khi cần chứng minh caller không bị chặn, dùng **latch để giữ task đang chạy** rồi kiểm tra future chưa complete trong khi caller đang tự do thực thi. Bộ test mẫu phía dưới làm chính xác điều này.

## 4. Chọn đúng executor: default, bean name và explicit qualifier

`@Async("notificationExecutor")` dùng giá trị annotation để chọn `Executor`/`TaskExecutor` bean có tên hoặc qualifier tương ứng.

```java
@Async("notificationExecutor")
public CompletableFuture<String> sendNotification() { ... }

@Async("reportExecutor")
public CompletableFuture<String> buildReport() { ... }
```

Đây là hai method signatures minh họa, không phải mã Java file độc lập. Hai lời gọi sẽ chạy trên **hai executor beans khác nhau** khi cấu hình đúng.

**Tại sao nên có qualifier?** Khi ứng dụng có nhiều executors dùng cho web MVC, scheduling, batch jobs, async email, reporting và test infrastructure, **một @Async không có qualifier có thể dùng executor không như dự kiến**. Explicit `@Async("beanName")` giúp chủ đích rõ và có thể test bằng thread name prefix.

### 4.1. Boot 3.5 tự cấu hình executor trong trường hợp nào?

Theo tài liệu Spring Boot 3.5:
- Nếu **không có `Executor` bean tùy chỉnh**, Boot có thể tự cấu hình một `AsyncTaskExecutor` cho `@EnableAsync` và các tích hợp khác.
- Khi Java 17 và không bật virtual threads, auto-configured executor thông thường là `ThreadPoolTaskExecutor`.
- Nếu có custom `Executor` bean, auto-configuration thường **back off**; executor này có thể được chọn cho regular `@EnableAsync` theo quy tắc resolution của Spring.
- Với nhiều executors, tên `taskExecutor`, `@Primary`, `AsyncConfigurer`, các integration-specific types và `spring.task.execution.mode` có thể ảnh hưởng lựa chọn.
- `applicationTaskExecutor` là tên đặc biệt cho một số tích hợp như MVC/WebFlux async request handling, và với chúng bean cần là `AsyncTaskExecutor`. Nó **không đồng nghĩa** với mọi `@Async("notificationExecutor")` custom method.
- `spring.task.execution.mode=force` trong Boot 3.5 có tác dụng giữ auto-configured task executor ngay khi có custom executors; cần đọc đúng cách ưu tiên nếu dùng nhiều beans.
- Trên Java 21+ khi bật `spring.threads.virtual.enabled=true`, Boot có thể dùng virtual-thread executor, khác `ThreadPoolTaskExecutor`; ví dụ bài cố ý dùng Java 17 và pool được khai báo tường minh.

**Không dựa vào số thread mặc định hoặc bean name tình cờ** nếu đó là một yêu cầu hệ thống. Trong ví dụ dưới, mọi method `@Async` đều chỉ rõ executor, và test kiểm tra cả bean config lẫn thread chạy thật.

### 4.2. Vì sao core, max và queue quan trọng?

Với `ThreadPoolTaskExecutor`:

- `corePoolSize`: số worker threads cơ bản.
- `maxPoolSize`: giới hạn threads khi cần thêm worker.
- `queueCapacity`: số tác vụ chờ; khi queue chưa đầy, task thường được enqueue thay vì tự tăng thread đến max.
- `threadNamePrefix`: giúp chẩn đoán executor nào đang chạy.
- `RejectedExecutionHandler`: chính sách khi pool/queue đầy.
- `setWaitForTasksToCompleteOnShutdown`, `setAwaitTerminationSeconds`: kiểm soát shutdown của worker tasks.

Để test được cả **task rejection**, ví dụ sẽ dùng `notificationExecutor` có **1 core thread, 1 max thread và queue capacity = 1**. Khi task A đang giữ worker và task B đã chiếm queue, task C phải bị từ chối theo policy mặc định.

Đây là cấu hình **cố ý nhỏ cho test**, không phải cấu hình khuyến nghị sản xuất. Production cần đánh giá throughput, queue boundedness, memory, latency, backpressure và shutdown thời gian thích hợp.

## 5. Độ sâu kiểm thử: unit test khác integration test

| Kiểu test | Tạo bean thế nào? | Chứng minh được | Không chứng minh |
|---|---|---|---|
| Plain JUnit + `new BackgroundJobs()` | Không Spring context | Logic thân method | `@Async` proxy/executor |
| Mockito mock `BackgroundJobs` | Mock method return future | Consumer behavior | Execution thật/scheduling |
| `@SpringBootTest` + inject `BackgroundJobs` | Spring context/proxy thật | Proxy, executor selection, completion/error, bounded pool | Production external systems nếu không có integration |
| `@SpringJUnitConfig` với minimal config | Spring test context + imported beans | Proxy/executor với cấu hình tối thiểu | Toàn bộ Boot auto-configuration |
| `@SpringBootTest(RANDOM_PORT)` | HTTP server thật | HTTP → service → proxy nếu gọi thật | Không tự chứng minh background job đã hoàn tất |
| Manual executor `Runnable::run` trong test | Chạy đồng bộ có chủ đích | Logic deterministic | Asynchronous thread switch |

**Chọn @SpringBootTest(webEnvironment=NONE)** cho bài thực nghiệm này. Ta cần Spring AOP và executor configuration thật, nhưng không cần HTTP server/database để chứng minh `@Async`.

## 6. Dự án Java 17+ hoàn chỉnh có thể chạy

Cấu trúc:

```text
build.gradle
src/main/java/com/example/asynclab/
    AsyncLabApplication.java
    AsyncExecutorsConfig.java
    JobReceipt.java
    BackgroundJobs.java
    JobFacade.java
src/test/java/com/example/asynclab/
    AsyncProxyIntegrationTest.java
```

### 6.1. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter` mang Spring Framework/Scheduling infrastructure cần thiết; `spring-boot-starter-test` cung cấp JUnit Jupiter, Spring Test, AssertJ và Mockito. Không cần web starter, Redis, JDBC hoặc Docker cho bài này.

Project cần một Gradle wrapper hợp lệ để chạy `./gradlew`; file build ở trên tự nó **không tạo wrapper**. Nếu dùng Maven, tạo `pom.xml` tương đương với Spring Boot parent/BOM, starter, starter-test và Surefire/JUnit Platform phù hợp.

### 6.2. Bật @EnableAsync

Tệp `src/main/java/com/example/asynclab/AsyncLabApplication.java`:

```java
package com.example.asynclab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableAsync;

@SpringBootApplication
@EnableAsync
public class AsyncLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(AsyncLabApplication.class, args);
    }
}
```

`@EnableAsync` là điểm kích hoạt annotation processing. Trong ví dụ, mọi method `@Async` đều thuộc bean `@Service` riêng, không được gọi trong lifecycle `@PostConstruct`.

### 6.3. Khai báo hai executors với tên rõ ràng

Tệp `src/main/java/com/example/asynclab/AsyncExecutorsConfig.java`:

```java
package com.example.asynclab;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class AsyncExecutorsConfig {

    @Bean("notificationExecutor")
    public ThreadPoolTaskExecutor notificationExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setQueueCapacity(1);
        executor.setThreadNamePrefix("notify-worker-");

        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(5);

        return executor;
    }

    @Bean("reportExecutor")
    public ThreadPoolTaskExecutor reportExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setQueueCapacity(4);
        executor.setThreadNamePrefix("report-worker-");

        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(5);

        return executor;
    }
}
```

`ThreadPoolTaskExecutor` là Spring bean hỗ trợ initialization/shutdown lifecycle; khi Spring context tạo bean, nó được init trước khi `@Async` submit task. Thread names có dạng `notify-worker-1` hoặc `report-worker-1` **theo quan sát điển hình**; test chỉ assert **prefix**, không hard-code suffix hoặc tên thread cố định.

**Không nhầm cấu hình:** `@Bean("notificationExecutor")` là **bean name được @Async chọn**, trong khi `setThreadNamePrefix("notify-worker-")` là **hậu tố log/định danh worker thread**. Bean name và thread name không có cơ chế tự đồng bộ; test cần kiểm tra cả hai khi đây là yêu cầu.

### 6.4. Mô hình kết quả ghi nhận thread thực thi

Tệp `src/main/java/com/example/asynclab/JobReceipt.java`:

```java
package com.example.asynclab;

public record JobReceipt(
        String jobId,
        String workerThreadName) {
}
```

Record chỉ chứa dữ liệu cần quan sát, không chứa `Thread` object hoặc mutable global state. Khi chạy đồng thời, nó giúp mỗi future mang kết quả độc lập theo job ID.

### 6.5. Spring service có @Async thật

Tệp `src/main/java/com/example/asynclab/BackgroundJobs.java`:

```java
package com.example.asynclab;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class BackgroundJobs {

    @Async("notificationExecutor")
    public CompletableFuture<JobReceipt> sendNotification(
            String jobId,
            CountDownLatch entered,
            CountDownLatch release) {

        // Đánh dấu worker đã bước vào method body.
        entered.countDown();

        try {
            // Test điều khiển chính xác thời điểm được hoàn tất.
            if (!release.await(15, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Worker release gate timed out");
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                    "Worker thread interrupted", ex);
        }

        JobReceipt receipt = new JobReceipt(
                jobId, Thread.currentThread().getName());

        // Spring async proxy sẽ cung cấp future thực cho caller.
        return CompletableFuture.completedFuture(receipt);
    }

    @Async("reportExecutor")
    public CompletableFuture<JobReceipt> generateReport(
            String jobId) {
        return CompletableFuture.completedFuture(
                new JobReceipt(
                        jobId, Thread.currentThread().getName()));
    }

    @Async("notificationExecutor")
    public CompletableFuture<String> captureAsyncThreadName() {
        return CompletableFuture.completedFuture(
                Thread.currentThread().getName());
    }

    @Async("notificationExecutor")
    public CompletableFuture<String> failNotification(
            String jobId) {
        throw new IllegalArgumentException(
                "Invalid job: " + jobId);
    }

    public CompletableFuture<String> callOwnAsyncMethod() {
        // Gọi trực tiếp target method trong cùng bean.
        // KHÔNG đi qua Spring proxy.
        return captureAsyncThreadName();
    }
}
```

**Cách code được thực thi:**
- Caller gọi **proxy** `BackgroundJobs.sendNotification`.
- Proxy submit task vào bean `notificationExecutor`.
- Thread của executor thực hiện method body, đếm `entered` và chờ `release`.
- Caller vẫn nhận `CompletableFuture<JobReceipt>` để quan sát kết quả.
- Khi test mở `release`, worker trả `completedFuture(receipt)`; proxy hoàn tất future của caller.
- `generateReport` sử dụng **reportExecutor** khác.
- `failNotification` ném lỗi trong worker, được biểu diễn bằng future exceptional.
- `callOwnAsyncMethod` không có `@Async`, và lời gọi từ target vào `captureAsyncThreadName` không đi qua proxy; đó là một **negative example có chủ ý**.

Sử dụng `CountDownLatch` trực tiếp trong public API của một service production không phải thiết kế phổ biến. Ở đây nó làm **test seam** rõ ràng để chứng minh scheduling. Production có thể tách một `Gate`/client dependency và inject fake dependency trong test, nhưng **nguyên tắc không dựa vào sleep** vẫn như nhau.

### 6.6. Service khác bean gọi đúng qua Spring proxy

Tệp `src/main/java/com/example/asynclab/JobFacade.java`:

```java
package com.example.asynclab;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;

import org.springframework.stereotype.Service;

@Service
public class JobFacade {

    private final BackgroundJobs jobs;

    public JobFacade(BackgroundJobs jobs) {
        this.jobs = jobs;
    }

    public CompletableFuture<JobReceipt> dispatch(
            String jobId,
            CountDownLatch entered,
            CountDownLatch release) {
        // Dependency jobs là Spring proxy, không phải "this".
        return jobs.sendNotification(
                jobId, entered, release);
    }
}
```

Đây là cách khắc phục self-invocation được khuyến nghị: thiết kế ranh giới async ở một service bean, caller inject bean ấy. Test sẽ chứng minh `JobFacade.dispatch` đưa task sang executor.

## 7. JUnit integration tests dùng Spring proxy và executor thật

Tệp `src/test/java/com/example/asynclab/AsyncProxyIntegrationTest.java`:

```java
package com.example.asynclab;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;

import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.task.TaskRejectedException;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class AsyncProxyIntegrationTest {

    @Autowired
    BackgroundJobs jobs;

    @Autowired
    JobFacade facade;

    @Autowired
    @Qualifier("notificationExecutor")
    ThreadPoolTaskExecutor notificationExecutor;

    @Autowired
    @Qualifier("reportExecutor")
    ThreadPoolTaskExecutor reportExecutor;

    @Test
    void springBeanIsProxiedAndPoolHasExpectedLimits() {
        assertTrue(AopUtils.isAopProxy(jobs));

        assertEquals(1, notificationExecutor.getCorePoolSize());
        assertEquals(1, notificationExecutor.getMaxPoolSize());
        assertEquals(1, notificationExecutor.getQueueCapacity());

        assertEquals(1, reportExecutor.getCorePoolSize());
        assertEquals(1, reportExecutor.getMaxPoolSize());
        assertEquals(4, reportExecutor.getQueueCapacity());
    }

    @Test
    void callerReturnsWhileWorkerIsBlocked()
            throws Exception {
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        String caller = Thread.currentThread().getName();

        CompletableFuture<JobReceipt> future =
                jobs.sendNotification(
                        "notice-1", entered, release);

        try {
            assertTrue(entered.await(5, TimeUnit.SECONDS));
            assertFalse(future.isDone());
        } finally {
            // Release worker kể cả khi assertion thất bại.
            release.countDown();
        }

        JobReceipt receipt =
                future.get(5, TimeUnit.SECONDS);

        assertEquals("notice-1", receipt.jobId());
        assertTrue(receipt.workerThreadName()
                .startsWith("notify-worker-"));
        assertFalse(receipt.workerThreadName().equals(caller));
    }

    @Test
    void namedExecutorsRunOnDifferentThreadPools()
            throws Exception {
        String notificationThread =
                jobs.captureAsyncThreadName()
                        .get(5, TimeUnit.SECONDS);

        JobReceipt report =
                jobs.generateReport("report-1")
                        .get(5, TimeUnit.SECONDS);

        assertTrue(notificationThread
                .startsWith("notify-worker-"));
        assertEquals("report-1", report.jobId());
        assertTrue(report.workerThreadName()
                .startsWith("report-worker-"));
    }

    @Test
    void externalBeanCallCrossesAsyncProxy()
            throws Exception {
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        CompletableFuture<JobReceipt> future =
                facade.dispatch("facade-1", entered, release);

        try {
            assertTrue(entered.await(5, TimeUnit.SECONDS));
            assertFalse(future.isDone());
        } finally {
            release.countDown();
        }

        JobReceipt receipt =
                future.get(5, TimeUnit.SECONDS);

        assertEquals("facade-1", receipt.jobId());
        assertTrue(receipt.workerThreadName()
                .startsWith("notify-worker-"));
    }

    @Test
    void selfInvocationRunsOnCallerThread()
            throws Exception {
        String caller = Thread.currentThread().getName();

        // callOwnAsyncMethod() là lời gọi vào target bean;
        // this.captureAsyncThreadName() không đi qua proxy.
        String selfCallResult =
                jobs.callOwnAsyncMethod()
                        .get(5, TimeUnit.SECONDS);

        assertEquals(caller, selfCallResult);

        // External call vẫn đi qua proxy và chọn executor.
        String externalResult =
                jobs.captureAsyncThreadName()
                        .get(5, TimeUnit.SECONDS);

        assertTrue(externalResult
                .startsWith("notify-worker-"));
        assertFalse(externalResult.equals(caller));
    }

    @Test
    void workerExceptionIsExposedThroughFuture()
            throws Exception {
        CompletableFuture<String> future =
                jobs.failNotification("invalid-7");

        ExecutionException error = assertThrows(
                ExecutionException.class,
                () -> future.get(5, TimeUnit.SECONDS));

        IllegalArgumentException cause =
                assertInstanceOf(
                        IllegalArgumentException.class,
                        error.getCause());

        assertEquals(
                "Invalid job: invalid-7",
                cause.getMessage());
    }

    @Test
    void poolRejectsThirdTaskWhileOneRunsAndOneQueues()
            throws Exception {
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        CompletableFuture<JobReceipt> first =
                jobs.sendNotification(
                        "first", entered, release);

        CompletableFuture<JobReceipt> second = null;

        try {
            // Phải chắc chắn worker đầu đã chiếm core thread.
            assertTrue(entered.await(5, TimeUnit.SECONDS));

            // Task thứ hai nằm trong queueCapacity = 1.
            second = jobs.sendNotification(
                    "second",
                    new CountDownLatch(1),
                    new CountDownLatch(0));

            // Worker đang chờ + queue đã đầy:
            // Spring ThreadPoolTaskExecutor phải từ chối.
            assertThrows(
                    TaskRejectedException.class,
                    () -> jobs.sendNotification(
                            "third",
                            new CountDownLatch(1),
                            new CountDownLatch(0)));

        } finally {
            // Trả worker về trạng thái sạch cả khi test fail.
            release.countDown();
        }

        assertEquals(
                "first",
                first.get(5, TimeUnit.SECONDS).jobId());

        assertTrue(second != null);
        assertEquals(
                "second",
                second.get(5, TimeUnit.SECONDS).jobId());
    }

    @Test
    void newObjectDoesNotTestSpringAsyncProxy()
            throws Exception {
        BackgroundJobs plain = new BackgroundJobs();

        String caller = Thread.currentThread().getName();

        String result =
                plain.captureAsyncThreadName()
                        .get(5, TimeUnit.SECONDS);

        assertEquals(caller, result);
        assertFalse(AopUtils.isAopProxy(plain));
    }
}
```

Bộ mẫu trên có **8 ca JUnit `@Test`**, mỗi ca nhắm một contract khác nhau. Từng test sử dụng `future.get(timeout)` để **giới hạn thời gian chờ** nếu worker gặp lỗi cấu hình hoặc deadlock; không có `Thread.sleep`. Với `CountDownLatch`, `entered.await` chỉ hoàn tất sau khi worker **thực sự vào method**, nên `future.isDone()==false` trong lúc `release` đang đóng là một assertion có ý nghĩa.

### 7.1. Vì sao latch giúp test bớt flaky?

Nếu task ngắn:

```java
CompletableFuture<String> future =
        jobs.captureAsyncThreadName();

assertFalse(future.isDone()); // Có thể fail do race.
```

Dòng `assertFalse` là **anti-pattern** vì worker có thể đã hoàn tất hợp lệ. Trong test `callerReturnsWhileWorkerIsBlocked`, worker báo `entered` rồi chờ `release` từ test. Khi `entered.await` trả true và `release` chưa đếm về 0, future phải **chưa hoàn tất thành công**. Test xác minh caller vẫn có thể chạy assertions trong lúc worker đang bận, chứ không dựa vào tốc độ CPU.

### 7.2. Sử dụng finally bảo đảm worker không kẹt

Nếu assertion trong test fail mà không `release.countDown()`, executor thread có thể chờ đến timeout, khiến suite fail dây chuyền hoặc context shutdown kéo dài. Đặt `release.countDown()` trong `finally` là một quy tắc quan trọng khi test concurrency.

**Giới hạn:** nếu code worker gặp bug không bao giờ gọi `entered.countDown()`, `await(5s)` fail thay vì chờ vô hạn, nhưng test vẫn cần giải phóng gate. `get(5s)` là timeout của test, không tự bảo đảm pool đã xử lý mọi cancellation/interrupt path.

### 7.3. Test rejection có thể chịu ảnh hưởng chạy test song song

`poolRejectsThirdTaskWhileOneRunsAndOneQueues` giả định riêng executor `notificationExecutor` không có các tác vụ khác **đồng thời** can thiệp. Với JUnit Jupiter mặc định, test methods thường chạy tuần tự; nhưng nếu project bật parallel execution toàn suite, hoặc các bean khác cùng dùng pool, test này cần:
- Dùng một executor/context riêng cho class hoặc `@ResourceLock` phù hợp.
- Không chạy các test phụ thuộc queue capacity song song trên cùng bean.
- Thu thập và chờ kết quả của các tasks đã submit.
- Không thay queueCapacity trên production executor chỉ để ép test pass.

**TaskRejectedException xảy ra tại submit**, khác exception của worker được truyền qua future. Không bắt `Exception` chung rồi tuyên bố cả hai là một loại lỗi.

### 7.4. Làm sao chứng minh executor được dùng thật?

Chỉ `@Autowired ThreadPoolTaskExecutor` và assert các giá trị core/max/queue vẫn chưa đủ. Điều đó chứng minh bean cấu hình đúng, **chưa chứng minh `@Async` chọn nó**. Cần thêm:
- Lời gọi qua Spring proxy.
- `Thread.currentThread().getName()` được ghi **bên trong worker**.
- Assert prefix của `notificationExecutor` hoặc `reportExecutor`.
- Test tự gọi trong bean phải trở về thread caller, tạo negative control.

Đó là lý do bài có cả `springBeanIsProxiedAndPoolHasExpectedLimits`, `namedExecutorsRunOnDifferentThreadPools` và `selfInvocationRunsOnCallerThread`, không chỉ một test “future trả đúng string”.

## 8. Những lựa chọn cấu hình mặc định có thể làm test sai

### 8.1. @Async không có tên executor

```java
@Async
public CompletableFuture<String> doWork() {
    return CompletableFuture.completedFuture(
            Thread.currentThread().getName());
}
```

Đây là method minh họa. Nếu context có nhiều executor, lựa chọn executor phụ thuộc cấu hình của Spring async infrastructure và Boot auto-configuration. Không nên viết `assertTrue(name.startsWith("task-"))` dựa vào một tên thread tình cờ và coi nó là contract production.

Khi cần nhiều pools:
- Dùng `@Async("notificationExecutor")`.
- Hoặc định nghĩa `AsyncConfigurer` cho executor mặc định dùng bởi `@EnableAsync`.
- Hoặc một bean `taskExecutor`/primary executor theo quy tắc Spring/Boot được cấu hình tường minh.

**Điểm đặc biệt:** một `applicationTaskExecutor` phục vụ Spring MVC async request có thể khác named `notificationExecutor` cho business jobs. Không nên đổi bean MVC để “sửa” một bài test `@Async` không qualifier mà chưa hiểu toàn bộ hệ quả.

### 8.2. AsyncConfigurer dùng khi cần default executor hoặc uncaught handler

Một application có thể cung cấp:

```java
@Configuration
@EnableAsync
class AsyncPolicyConfig implements AsyncConfigurer {

    private final Executor defaultExecutor;

    AsyncPolicyConfig(
            @Qualifier("notificationExecutor")
            Executor defaultExecutor) {
        this.defaultExecutor = defaultExecutor;
    }

    @Override
    public Executor getAsyncExecutor() {
        return defaultExecutor;
    }

    @Override
    public AsyncUncaughtExceptionHandler
            getAsyncUncaughtExceptionHandler() {
        return (throwable, method, arguments) -> {
            // Ghi lỗi đã redacted, metrics hoặc gửi đến hệ thống quan sát.
            // Không log credentials hay dữ liệu nhạy cảm từ arguments.
        };
    }
}
```

Đây là **đoạn minh họa về cấu hình**, chưa phải Java file đầy đủ: cần imports `Executor`, `@Configuration`, `@EnableAsync`, `AsyncConfigurer`, `@Qualifier`, `AsyncUncaughtExceptionHandler`, và executor bean phù hợp. **Không** thêm class thứ hai này trực tiếp vào dự án ví dụ mà không xem lại `@EnableAsync`/beans để tránh cấu hình trùng/khác ưu tiên.

`getAsyncUncaughtExceptionHandler()` được dùng để quan sát lỗi từ method `void @Async`; future-returning methods nên **để caller xử lý lỗi qua future**.

### 8.3. Test với executor đồng bộ có chủ đích

Một unit test có thể inject một executor kiểu `Runnable::run` để thực hiện các task **ngay trong thread caller**:

```java
Executor sameThread = Runnable::run;
sameThread.execute(
        () -> checkDomainRule());
```

Đây là đoạn minh họa trong test có `checkDomainRule()`. Cách này rất tốt khi mục tiêu là **logic của job** không phụ thuộc concurrency. Nhưng nếu dùng nó làm executor trong Spring context rồi test `@Async` bằng `assertEquals(expected, future.get())`, test **không chứng minh async thread switch**.

**Phân loại test theo mục tiêu:**
- Logic unit test: executor đồng bộ/fake service hợp lệ.
- Async integration test: executor thật có thread khác, proxy thật, latch và timeout.
- Performance/load test: benchmark/workload riêng, không sử dụng một `Thread.sleep` tùy ý để đánh giá throughput.

## 9. Exception handling: CompletableFuture vs void @Async

### 9.1. Future-returning method

`failNotification` trong ví dụ ném `IllegalArgumentException` trên worker. Caller nhận `CompletableFuture` được complete exceptionally:

```java
CompletableFuture<String> future =
        jobs.failNotification("invalid-7");

ExecutionException failure =
        assertThrows(
                ExecutionException.class,
                () -> future.get(5, TimeUnit.SECONDS));

assertInstanceOf(
        IllegalArgumentException.class,
        failure.getCause());
```

Đây là đoạn minh họa trong JUnit test đã inject `jobs`; nó không đòi log inspection. Điều quan trọng là assert **cause** thật, tránh bắt một `ExecutionException` bất kỳ mà bên trong là `NullPointerException` do test setup lỗi.

Nếu dùng `join()`, exception wrapper thường là `CompletionException`. Nếu future đã bị cancel, `CancellationException` có thể xuất hiện; cancellation không nhất thiết dừng một task đang chạy nếu nó không quan sát interrupt/cancellation state.

### 9.2. void-returning method

```java
@Async("notificationExecutor")
public void fireAndForget(String id) {
    throw new IllegalStateException(
            "Cannot deliver " + id);
}
```

Đây là method minh họa. Với `void`, caller không nhận `Future` để `get()` và không thể expect lỗi đồng bộ bằng `assertThrows(() -> service.fireAndForget("x"))` — trừ khi lỗi xảy ra ngay khi submit hoặc có behavior khác ngoài body method.

Khi thật sự cần kiểm tra lỗi của `void @Async`, cung cấp `AsyncUncaughtExceptionHandler` có thể **ghi nhận exception vào một thread-safe probe** và dùng `CountDownLatch` để test chờ handler được gọi. Với lỗi production, nên có logging/metrics/DLQ/retry policy minh bạch. Nếu caller cần biết trạng thái công việc, ưu tiên **`CompletableFuture<T>`** thay vì chỉ `void`.

### 9.3. Phân biệt rejection, failure trong body và timeout của test

| Loại lỗi | Xảy ra lúc nào? | Cách test phù hợp |
|---|---|---|
| Executor rejection | Khi gọi proxy/submit task | `assertThrows(TaskRejectedException.class, ...)` |
| Task body ném exception | Trên worker thread | `future.get(timeout)`, assert `ExecutionException.getCause()` |
| Future chờ quá lâu | Khi caller đợi kết quả | `assertThrows(TimeoutException.class, () -> future.get(...))` nếu đó là mục tiêu |
| `void @Async` ném exception | Trên worker thread, không có future cho caller | `AsyncUncaughtExceptionHandler`/probe |
| Caller bị interrupt khi `get()` | Trong thread caller | Giữ interrupt policy rõ, xử lý `InterruptedException` |
| Worker bị interrupt | Trong worker thread | Restore interrupt flag và dừng task theo policy |
| Transaction/session state thiếu trên worker | Khi worker truy cập ThreadLocal-bound resource | Phân tích context propagation, không bắt chung `Exception` |

## 10. @Async và ThreadLocal: transaction, security, MDC

`@Async` thực thi body method trên **thread của executor**, không phải thread gọi vào. Vì vậy **ThreadLocal của caller không tự động xuất hiện trên worker**, đặc biệt khi dùng thread pool tái sử dụng threads.

### 10.1. @Transactional trong test không tự lan sang worker

Nếu test có:

```java
@SpringBootTest
@Transactional
class NotificationIntegrationTest {
    // Test-managed transaction nằm trên JUnit test thread.
}
```

thì worker method `@Async` chạy ở thread khác, không tham gia tự động vào **test-managed JDBC/JPA transaction** của test. Việc rollback cuối test **không bảo đảm** các thay đổi worker đã commit bị đảo ngược. Điều này đặc biệt nguy hiểm khi test dùng database thực nhưng tin rằng `@Transactional` làm mọi side effect biến mất.

**Thiết kế đúng:** nếu worker cần transaction, để nó gọi một Spring-managed transactional service ở thread worker, hoặc mở transaction rõ ràng trong phạm vi worker. Cần test với database cô lập, định danh dữ liệu riêng và cleanup cho commit độc lập. Khi kết hợp `@Async` và `@Transactional` trên cùng method, thứ tự AOP advice/transaction boundary phải được kiểm chứng; đừng dựa vào suy đoán rằng transaction của caller được chuyển sang background.

### 10.2. Spring SecurityContext không tự đi theo executor

Một controller authenticated có `SecurityContextHolder` trong request thread. Nếu background worker cố lấy principal bằng `SecurityContextHolder.getContext()`, nhiều khả năng không có đúng user của request.

Các lựa chọn:
- Truyền **userId/tenantId đã được kiểm tra quyền** dưới dạng tham số bất biến khi submit job.
- Dùng `DelegatingSecurityContextAsyncTaskExecutor` nếu business requirement thật sự cần SecurityContext propagation.
- Dùng TaskDecorator/context propagation được thiết kế và kiểm tra đúng, tránh giữ credentials trong long-lived worker.
- Không bật `MODE_INHERITABLETHREADLOCAL` cho thread pool tái sử dụng và xem đó là giải pháp bảo mật mặc định.

Khi test propagation, assert principal ở **worker thread**, đồng thời verify không bị rò principal giữa tasks của user khác. Một unit test mock `SecurityContextHolder` trên caller thread không chứng minh điều này.

### 10.3. MDC, trace ID và request context

`MDC` của SLF4J/Logback và nhiều request contexts là thread-bound. TaskExecutor có thể hỗ trợ `setTaskDecorator(...) ` để capture/restore một số context, nhưng phải **clear/restore state trong finally** để tránh leak khi pool tái sử dụng worker threads. Không gửi password/token thô vào MDC.

Ví dụ minh họa (không phải file Java hoàn chỉnh):

```java
executor.setTaskDecorator(runnable -> {
    Map<String, String> captured = MDC.getCopyOfContextMap();
    return () -> {
        Map<String, String> original = MDC.getCopyOfContextMap();
        try {
            if (captured == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(captured);
            }
            runnable.run();
        } finally {
            if (original == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(original);
            }
        }
    };
});
```

Đoạn này cần imports `java.util.Map`, `org.slf4j.MDC` và một `ThreadPoolTaskExecutor executor`. Nó minh họa nguyên tắc restore context cũ, không thay thế cơ chế telemetry/Context Propagation chuẩn của hệ thống nếu đang có OpenTelemetry/Micrometer Tracing.

**Không nhầm ngữ cảnh:** `ThreadLocal` của @Async/imperative transaction khác với **Reactor Context** của WebFlux/R2DBC. Dùng `@Async` không tự tạo/reactively-propagate Reactor Context.

## 11. Độ ổn định của kiểm thử async trên CI

### 11.1. Không dùng Thread.sleep để đoán

```java
jobs.sendNotification(...);
Thread.sleep(100);
assertEquals(1, auditRepository.count());
```

Đây là anti-pattern minh họa, không phải mã độc lập: `...` biểu diễn inputs và repository chưa khai báo. 100 ms không bảo đảm task đã chạy; CI có thể chậm hoặc được JVM scheduling khác. Kết quả là test flaky, nhất là khi chạy parallel.

Thay thế bằng một synchronization contract:
- `CompletableFuture.get(timeout)` khi method trả future.
- `CountDownLatch.await(timeout)` khi cần xác nhận worker đã bước vào một giai đoạn.
- `Awaitility`/polling có deadline khi chỉ quan sát external side effect và không thể lấy future.
- `StepVerifier` với Reactor publishers; khác với Java `@Async` future.
- Acknowledgement/event test probe được reset riêng cho mỗi test.

**Không dùng `assertTimeoutPreemptively` để “chặn task” khi code phụ thuộc test-managed transaction/ThreadLocal**: preemptive timeout có thể chạy code ở thread khác, làm test thay đổi transaction semantics. Với Future, `get(timeout)` thường là cách rõ hơn để giới hạn thời gian chờ.

### 11.2. Chạy nhiều tests dùng chung executor

Nếu test suite sử dụng Spring context cache, nhiều test classes có thể chia sẻ **cùng executor bean**. Một test không đợi xong jobs sẽ ảnh hưởng test sau:
- Queue vẫn có tasks khi test mới bắt đầu.
- Thread prefix vẫn giống nên race khó phát hiện.
- Shared static `AtomicInteger`/lists thay đổi do tasks cũ.
- Test rejection do pool đầy không còn deterministic.
- Context shutdown chờ tasks kéo dài ngoài mong muốn.

Giải pháp: đợi mọi futures hoàn tất trong test, cancel/cleanup theo policy, dùng executor riêng cho test cần saturation, và tránh test methods parallel trên cùng pool khi có assertions về queue capacity. `@DirtiesContext` có thể giúp cô lập context ở những test đặc biệt nhưng có chi phí bootstrap; không lạm dụng nó như giải pháp mặc định.

### 11.3. Timeout không phải benchmark

Một `future.get(5, TimeUnit.SECONDS)` chỉ là **deadline để fail có kiểm soát**. Nó không chứng minh job luôn nhanh hơn 5 giây dưới tải production; cần performance/load tests riêng, trên workloads thực tế và executor pool sizing phù hợp.

## 12. Rejection, bounded queue và thiết kế backpressure

Khi pool/queue đều đầy, `ThreadPoolTaskExecutor` có thể ném `TaskRejectedException` lúc submit. Điều này rất có giá trị để kiểm thử vì hệ thống phải quyết định **làm gì khi không còn năng lực nhận thêm việc**:
- Báo lỗi cho caller (HTTP 503/429 hoặc status miền phù hợp).
- Persist job vào hàng đợi bền (nếu architecture cho phép) để retry ngoài request.
- Dùng circuit breaker hoặc rate limiting ở đầu vào.
- Tránh mất job im lặng.
- Không dùng unbounded queue để che quá tải cho đến khi hết bộ nhớ.

**Đừng giả lập rejection bằng cách Mockito mock `CompletableFuture.failedFuture` rồi gọi đó là saturation test.** Đó là một task **đã được nhận** nhưng hoàn tất với lỗi; rejection xảy ra **trước khi** executor nhận task. Test `poolRejectsThirdTaskWhileOneRunsAndOneQueues` tạo tình huống saturation thực với pool 1 + queue 1.

### 12.1. Vì sao maxPoolSize không luôn tăng lên ngay?

Ví dụ `corePoolSize=2`, `maxPoolSize=8`, `queueCapacity=100`: sau khi hai core threads bận, executor có thể **enqueue** các tasks tiếp theo tới khi queue đầy rồi mới tạo thêm threads (tùy executor implementation). Vì vậy tăng `maxPoolSize` không nhất thiết cải thiện latency nếu queue rất lớn.

Trong bài, queue capacity = 1 cho phép ép rejection một cách dễ đoán sau khi một task đã chiếm worker và task thứ hai xếp hàng. Đây là **contract test cho cấu hình cụ thể**, không phải quy tắc chung cho mọi executor hoặc handler.

### 12.2. CallerRunsPolicy có thể làm mất đặc tính async

Một số hệ thống cố ý đặt `CallerRunsPolicy`: khi quá tải, task có thể chạy ngay trên **caller thread** thay vì bị từ chối. Đây là cơ chế backpressure có chủ ý nhưng sẽ thay đổi latency và thread-affinity. Nếu production bật chính sách này, test phải xác nhận đúng behavior — không luôn assert `TaskRejectedException`.

Ví dụ code sử dụng default rejection policy, nên test kỳ vọng `TaskRejectedException` khi pool/queue đã đầy. Không tự sửa thành CallerRunsPolicy để làm test xanh nếu yêu cầu là thông báo quá tải cho HTTP client.

## 13. Phân biệt @Async với @Scheduled

`@Async` và `@Scheduled` đều dùng scheduling infrastructure nhưng trả lời hai câu hỏi khác nhau:

| Annotation | Điều kích hoạt | Executor/Scheduler | Kiểu test chính |
|---|---|---|---|
| `@Async` | Có caller gọi Spring proxy method | `TaskExecutor`/`Executor` | Proxy/executor selection, future/error |
| `@Scheduled(fixedRate=...)` | Scheduler trigger định kỳ | `TaskScheduler`/`ScheduledExecutorService` | Thời điểm trigger, số lần chạy, idempotency |
| `@Scheduled(cron=...)` | Cron expression + timezone | Scheduler | Clock/timezone/cadence, misfire behavior |
| `@Async @Scheduled` kết hợp | Scheduler kích hoạt method, async advice có thể submit work | Phải hiểu cả scheduler và async executor | Không cho phép overlapping work ngoài chủ ý |

Không bật `@EnableScheduling` chỉ để kiểm thử `@Async`; trong demo chỉ bật `@EnableAsync`. Với scheduled jobs, bạn thường tách **trigger** và **business worker method** để có thể unit test domain logic và integration test lịch chạy độc lập.

**Lưu ý phiên bản:** Boot 3.5 cũng có tự cấu hình `ThreadPoolTaskScheduler` khi cần; `spring.task.scheduling.*` và `spring.task.execution.*` là hai nhóm properties khác nhau. Không dùng `spring.task.scheduling.pool.size` để mong `@Async` notification pool thay đổi.

## 14. Những lỗi thực tế và cách điều tra

| Triệu chứng | Nguyên nhân | Hướng sửa |
|---|---|---|
| `@Async` không đổi thread | Chưa `@EnableAsync`, gọi `new`, tự gọi `this.method`, thiếu AOP proxy | Inject bean qua Spring, test proxy và thread prefix |
| `AopUtils.isAopProxy(bean)==false` | Async post-processor không kích hoạt hoặc method không đủ điều kiện | Kiểm tra context/annotation/visibility |
| Test trả kết quả đúng nhưng không chứng minh async | Method trả `completedFuture` ngay trên caller | Latch giữ worker, assert caller vẫn chạy |
| Self-invocation trả tên thread JUnit | Gọi trong cùng target bean | Tách bean và gọi qua proxy |
| Method `private`/`final` không được intercept | Proxy không thể override/advise method | Public non-final external method |
| `@Async("missingExecutor")` fail | Bean không tồn tại hoặc tên/qualifier sai | Kiểm tra bean name/qualifier và context |
| Thread prefix không đúng | `@Async` chọn executor khác | Explicit qualifier; assert tên thread ở worker |
| Context có nhiều executors, default bất ngờ | `taskExecutor`/`@Primary`/`AsyncConfigurer`/Boot rules | Chọn explicit bean hoặc cấu hình default rõ |
| MVC async request hoạt động khác business @Async | `applicationTaskExecutor` không phải named business executor | Phân biệt integration-specific executor |
| Test chập chờn khi assert `future.isDone()==false` | Task quá nhanh, race | CountDownLatch/blocked worker gate |
| `Thread.sleep(100)` tạo test flaky | Scheduler/CI load không cố định | Await có deadline, Future.get(timeout) |
| Không thấy exception khi `void @Async` ném | Exception xảy ra ở worker, caller không có future | AsyncUncaughtExceptionHandler hoặc trả future |
| `CompletableFuture.get()` ném ExecutionException | Worker task lỗi | Inspect `getCause()`, đừng nuốt lỗi |
| TaskRejectedException ngay khi gọi method | Pool/queue đầy hoặc executor shutdown | Sizing/backpressure/retry/queue policy |
| Thread pool không tăng lên `maxPoolSize` | Queue còn capacity, growth policy | Hiểu core/max/queue và test dưới tải có kiểm soát |
| Async method tạo DB row dù test rollback | Test transaction ThreadLocal không đi sang worker | Worker transaction riêng, isolated DB/cleanup |
| SecurityContext null trong worker | ThreadLocal không tự propagate | Truyền user ID hoặc SecurityContext-aware executor |
| MDC trace ID biến mất | MDC không tự propagate qua pooled thread | TaskDecorator/context propagation và finally restore |
| Job còn chạy sau JUnit test | Chưa đợi future/cancel | Await result, bounded shutdown |
| Test saturation fail khi suite chạy song song | Có tasks khác dùng chung executor | Executor riêng/ResourceLock và tách test isolation |
| @Async method gọi ở @PostConstruct không async | Bean proxy chưa sẵn sàng | Gọi từ bean riêng sau initialization |
| Java 21 virtual threads khác kỳ vọng prefix | Boot auto-config virtual executor | Phân biệt version/runtime; explicit pool nếu cần |
| @Async method trả Mono/Flux không hoạt động như Future | Async return type không đúng hợp đồng | Dùng Reactor scheduler/Reactive API |
| Build xanh nhưng test không chạy | `NO-SOURCE`, skipped, wrong JUnit runner | Kiểm tra reports/tests executed |

### 14.1. Chuỗi debug 10 bước

1. Xác định lời gọi `@Async` xuất phát từ bean nào và có đi qua Spring proxy không.
2. Kiểm tra `@EnableAsync` đã được import trong test context.
3. Kiểm tra method public/non-final; `@Async` không đặt ở `@Configuration` method.
4. Kiểm tra `@Async("beanName")` khớp đúng executor bean.
5. Assert proxy bằng `AopUtils.isAopProxy` — nhưng **kết hợp** kiểm tra thread thực thi.
6. Ghi tên thread từ **bên trong method**, không chỉ tên caller.
7. Dùng CountDownLatch để đồng bộ phase worker entered/release, không đoán bằng sleep.
8. Đọc lỗi `future.get().getCause()` hoặc task rejection tại submit.
9. Kiểm tra executor có bị shutdown, queue đã đầy hoặc context cache đang chia sẻ jobs.
10. Xem thread-local context, @Transactional, security và MDC nếu kết quả khác giữa JUnit thread và worker thread.

## 15. Chạy test và kiểm tra báo cáo đúng

Linux/macOS nếu project có Gradle wrapper:

```bash
./gradlew test --tests "com.example.asynclab.AsyncProxyIntegrationTest"
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.asynclab.AsyncProxyIntegrationTest"
```

Với Maven wrapper khi đã chuyển dependencies/config sang `pom.xml` tương đương:

```bash
./mvnw -Dtest=AsyncProxyIntegrationTest test
```

Windows PowerShell:

```powershell
.\mvnw.cmd -Dtest=AsyncProxyIntegrationTest test
```

Kết quả **dự kiến** khi environment phù hợp: 8 test methods được discovery và thực thi; assertions về proxy, two executors, self invocation, future exception và saturation đạt. Tuy nhiên **bài viết không tuyên bố đã thực thi 8 tests**. Cần xem `build/reports/tests/test/index.html` hoặc `target/surefire-reports/` của module và trạng thái task thực tế, không kết luận chỉ từ `BUILD SUCCESSFUL` nếu test bị skip hoặc `NO-SOURCE`.

**Không có stdout nghiệp vụ cố định**: thread IDs và suffix có thể thay đổi theo JVM và thời điểm test, vì vậy code assert prefix thay vì in ra một dòng cố định không đáng tin.

### 15.1. Vì sao không dùng javac đơn lẻ?

Code sử dụng Spring Boot, scheduling/AOP và JUnit Jupiter, nên `javac` cần một classpath đầy đủ. Trong dự án mẫu, chạy qua Gradle/Maven với dependencies đã khai báo là workflow được kiểm chứng phù hợp. Nếu muốn cô lập logic Java không phụ thuộc Spring, có thể tách nó thành class thuần và test với `javac`/JUnit runner tương ứng, nhưng đó **không phải bài kiểm thử @Async qua proxy**.

## 16. Checklist QA cho @Async và configured executor

- [ ] `@EnableAsync` có trong Spring test context thực tế.
- [ ] Test lấy `@Autowired` bean, không `new` nếu mục tiêu là proxy execution.
- [ ] Method `@Async` được gọi **từ bean khác** hoặc bên ngoài qua Spring proxy.
- [ ] Method public/non-final và return type là `void`/`Future`/`CompletableFuture` theo API hỗ trợ.
- [ ] Đã test negative case self-invocation nếu codebase có rủi ro đó.
- [ ] `@Async("notificationExecutor")` trỏ đúng bean name/qualifier.
- [ ] Test xác minh executor **được chọn thực sự** qua thread name trong worker, không chỉ config bean.
- [ ] Test khác biệt hai named executors khi project dùng nhiều pools.
- [ ] Dùng `CountDownLatch`/future synchronization, tránh `Thread.sleep` đoán lịch.
- [ ] `future.get(timeout)` có deadline, không chờ vô hạn.
- [ ] Latch được release trong `finally` để không làm kẹt worker/context.
- [ ] Với exceptions, assert nguyên nhân bên trong `ExecutionException`; với void dùng handler/probe.
- [ ] Khi saturation là contract, test queue bounded + rejection có isolation khỏi parallel tasks.
- [ ] Production sizing/backpressure là quyết định riêng, không copy pool size 1 của demo.
- [ ] Test-managed JDBC/JPA transaction không bị giả định lan sang worker thread.
- [ ] SecurityContext/MDC/request scope được propagate có chủ đích và clear đúng lifecycle.
- [ ] Phân biệt `applicationTaskExecutor` của MVC async với named business executors.
- [ ] Nếu Java 21 virtual threads hoặc Boot khác version, xác minh executor type đúng.
- [ ] Dọn/đợi mọi future đã submit, tránh test rò tasks sang method sau.
- [ ] Đọc reports JUnit thực tế để xác nhận các tests đã chạy trước khi báo runtime PASS.

## 17. Nguồn chính thức

- [Spring Framework 6.2 — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@EnableAsync`, `@Async`, executor qualification, proxy mode và `AsyncUncaughtExceptionHandler`.
- [Spring Framework 6.2 — @Async Javadoc](https://docs.spring.io/spring-framework/docs/6.2.2/javadoc-api/org/springframework/scheduling/annotation/Async.html): return types `void`/`Future`, `CompletableFuture`, `value` executor qualifier, giới hạn `@Configuration` methods.
- [Spring Framework — @EnableAsync Javadoc](https://docs.spring.io/spring-framework/docs/6.2.11/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html): default proxy mode, executor selection và `AsyncConfigurer`.
- [Spring Boot 3.5 — Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html): auto-configured `applicationTaskExecutor`, `taskExecutor`, nhiều Executor beans, Boot `spring.task.execution.*`, Java 21 virtual threads.
- [Spring Framework — ThreadPoolTaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.5/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html): core/max/queue/thread prefix, rejection, shutdown.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): self-invocation và AOP proxy limits.
- [JUnit Jupiter — User Guide](https://docs.junit.org/current/user-guide/): method lifecycle, JUnit Platform và parallel execution.

**Kết luận:** Kiểm thử `@Async` đúng nghĩa phải đi qua **Spring proxy**, xác minh **executor được chọn thực** và quan sát worker thread bằng synchronization có deadline. `@WithMockUser` hoặc `@Transactional` ở JUnit thread không tự di chuyển state sang worker, còn `this.asyncMethod()` không kích hoạt proxy. Dùng `@SpringBootTest` với named `ThreadPoolTaskExecutor`, `CountDownLatch` và `CompletableFuture` để kiểm chứng thread switching, self-invocation, exception và task rejection; đừng tuyên bố async hoạt động chỉ vì method có annotation hoặc test chờ một khoảng `Thread.sleep` rồi thấy dữ liệu.