# Testing @Async Through Proxy and Configured Executor in Spring Boot

## 1. The problem: a method annotated with @Async is not enough to prove asynchronous execution

In Spring Boot, applications commonly use `@Async` to send notifications, export reports, write audit logs, process images, or call a slow service without blocking the HTTP request thread. However, a test that merely calls the method and asserts the result can **pass even when @Async is not working**.

Common risks:
- The test creates the object with `new EmailWorker()` instead of retrieving the Spring bean, so **there is no AOP proxy**.
- A method within the same bean calls `this.sendAsync()`, causing **self-invocation to bypass the proxy**.
- `@Async` lacks `@EnableAsync` in the test context, or the bean is completely mocked.
- No explicit executor is specified: the task runs on a default executor different from the intended thread pool.
- The test uses `Thread.sleep(100)` and then asserts the data; on a slow CI runner it becomes flaky.
- A `void @Async` method throws an error, yet the test does not receive the exception, creating a false positive.
- Test assertions rely on `future.isDone()` right after calling the method, which has a race condition if the task is too short.
- The test uses `@Transactional` on the main thread while expecting the transaction to propagate automatically to the worker thread.

**The lesson's goal** is to test **the exact two contracts**:

1. **Proxy contract:** the call must go through the Spring bean proxied by `@EnableAsync`, so that the method executes on a different thread and the caller can proceed.
2. **Executor contract:** `@Async("executorName")` selects the right `ThreadPoolTaskExecutor` bean (or a configured `Executor`), with the intended thread prefix, concurrency/queue/rejection, and lifecycle.

This lesson uses **Java 17+, Spring Boot 3.5.x, Spring Framework 6.x, JUnit Jupiter**. The complete example includes two named executors, an `@Async` Spring service, a service calling through the proxy, and JUnit integration tests using `CountDownLatch`/`CompletableFuture` to **synchronize deterministically instead of sleeping for an arbitrary duration**.

## 2. How does @Async work at the Spring AOP level?

When `@EnableAsync` is enabled, Spring registers the infrastructure that detects `@Async` methods and applies **async advice** to the bean using the default `AdviceMode.PROXY`.

```text
JUnit test thread (T0)
      |
      | @Autowired BackgroundJobs  [Spring bean/proxy]
      |
      +--> proxy: intercept @Async("notificationExecutor")
                      |
                      +--> submit Callable/Runnable to executor bean
                      |
                      +--> return CompletableFuture to T0
                                 |
                       worker thread (T1)
                                 |
                         method body executes
                                 |
                    result/exception completes future
                                 |
                    T0 get()/join() observes outcome
```

A crucial distinction:

```java
// Correct: jobs is a Spring-managed bean; the call goes through the proxy.
CompletableFuture<String> result = jobs.captureThreadName();

// Wrong if you want to test the proxy: instantiating outside Spring.
BackgroundJobs plain = new BackgroundJobs();
CompletableFuture<String> result2 = plain.captureThreadName();
```

These two lines are **illustrative snippets within a scope that has the `jobs` variable and `BackgroundJobs` class**. With an object created via `new`, the annotation does not automatically activate any scheduler/executor. The Java method runs synchronously like a normal call, even though `@Async` is still in the source code.

### 2.1. @EnableAsync is a necessary condition, not the entire configuration

```java
@SpringBootApplication
@EnableAsync
public class AsyncDemoApplication {
}
```

This is an illustrative configuration snippet; it requires Spring Boot/Scheduling imports. `@EnableAsync` enables asynchronous method execution for beans in the context. It does **not** automatically make:
- Every Java method run in the background.
- A `private` method get intercepted by the proxy.
- A `this.asyncMethod()` call become an external proxy call.
- Code running on a new thread carry along ThreadLocal transaction/security/request context.
- A `@Scheduled` task start running automatically if `@EnableScheduling` is not enabled.

**Note:** `@Async` is not supported on methods declared in the `@Configuration` class itself according to the Spring Javadoc. Place asynchronous business methods in a separate `@Service`/component.

### 2.2. Why does self-invocation lose asynchronicity?

```java
@Service
class NotificationService {
    public CompletableFuture<String> callInside() {
        return sendAsync(); // this.sendAsync(): does not go through the proxy
    }

    @Async("notificationExecutor")
    public CompletableFuture<String> sendAsync() {
        return CompletableFuture.completedFuture(
                Thread.currentThread().getName());
    }
}
```

The snippet above is an illustrative example; it requires `@EnableAsync`, an executor bean, and imports. In `callInside()`, `sendAsync()` calls **directly on the target object**, bypassing the proxy, so it returns a `completedFuture` containing the **caller's thread name**.

The recommended fix: **extract the @Async method into another bean** and inject that bean into the caller. Techniques such as self-injecting the proxy or using `AopContext.currentProxy()` can work in some setups, but they increase coupling, are harder to test, and should not be the default design.

### 2.3. Interface-based proxy, class-based proxy, and method limitations

Spring AOP uses proxies by default. If the target has an interface, a JDK dynamic proxy may be used; in other configurations, Spring may use a class-based proxy. Therefore:
- Prefer `public` methods on a bean called **from outside the bean**.
- `private` methods cannot be intercepted by an AOP proxy.
- `final` methods cannot be overridden by a subclass proxy; `final` classes can prevent class-based proxies.
- `@PostConstruct` is not a suitable place to rely on `@Async` on the bean itself, because the proxy/lifecycle is not guaranteed yet.
- If using `@EnableAsync(mode=AdviceMode.ASPECTJ)` with actual weaving, self-invocation semantics differ; **this lesson only tests the default proxy mode**.

**Testing the proxy** should not merely assert via reflection that the `@Async` annotation exists. You must obtain the bean from the Spring context, invoke the real method, and verify thread/executor behavior.

## 3. What return types should @Async use, and where do errors go?

Spring Framework `@Async` supports methods returning **`void` or `Future`**; when you need to observe the result, using `CompletableFuture<T>` is very convenient.

```java
@Async("notificationExecutor")
public CompletableFuture<String> compute() {
    String value = Thread.currentThread().getName();
    return CompletableFuture.completedFuture(value);
}
```

This is an illustrative method snippet. The Spring async proxy returns a future representing the actual execution. Meanwhile, the method **implementation** can return `CompletableFuture.completedFuture(value)` after computing the result on the worker thread; Spring will propagate/complete the future returned to the caller accordingly.

| Method signature | What can the caller observe? | How to test |
|---|---|---|
| `@Async void send()` | No future to receive completion/error | Observe side effect/callback or `AsyncUncaughtExceptionHandler` |
| `@Async Future<T> load()` | `Future.get()` | Assert result/cause, timeout |
| `@Async CompletableFuture<T> load()` | `get()`, `join()`, composition | Usually the best choice |
| Regular Java method returning `CompletableFuture` | Does not run in an executor by default | Test where it actually executes |
| Arbitrary `@Async Mono<T>` | **Not a generally supported return type for @Async** | Reactive pipelines use their own Reactor scheduler/Context |

**Exceptions:**
- With `CompletableFuture.get()`, task errors typically surface as an `ExecutionException`, with the actual cause in `getCause()`.
- With `CompletableFuture.join()`, errors are typically wrapped in a `CompletionException`.
- With `void @Async`, the caller **cannot** catch an exception thrown on the worker using `assertThrows(() -> service.voidAsync())` like a synchronous call. You need a handler/probe or change the API to return a future.
- An error **immediately upon submission** (e.g., the pool rejects the task) can be thrown **synchronously** to the caller as a `TaskRejectedException`. This is a different error from an exception thrown inside the worker task.

### 3.1. Do not turn a future into a speed measurement

```java
CompletableFuture<String> future = worker.compute();
assertFalse(future.isDone()); // UNSTABLE if compute is too fast!
```

The task may have already completed before `isDone()` is called; a valid asynchronous implementation can still fail this assertion. When you need to prove the caller is not blocked, use a **latch to hold the task running** and check that the future is not yet complete while the caller is free to execute. The sample test suite below does exactly this.

## 4. Selecting the right executor: default, bean name, and explicit qualifier

`@Async("notificationExecutor")` uses the annotation value to select the `Executor`/`TaskExecutor` bean with the matching name or qualifier.

```java
@Async("notificationExecutor")
public CompletableFuture<String> sendNotification() { ... }

@Async("reportExecutor")
public CompletableFuture<String> buildReport() { ... }
```

These are two illustrative method signatures, not a standalone Java file. The two calls will run on **two different executor beans** when configured properly.

**Why use a qualifier?** When an application has multiple executors for web MVC, scheduling, batch jobs, async email, reporting, and test infrastructure, **an @Async without a qualifier may use an unintended executor**. Explicit `@Async("beanName")` makes intent clear and allows testing via thread name prefix.

### 4.1. When does Boot 3.5 auto-configure an executor?

According to the Spring Boot 3.5 documentation:
- If there is **no custom `Executor` bean**, Boot can auto-configure an `AsyncTaskExecutor` for `@EnableAsync` and other integrations.
- On Java 17 without virtual threads enabled, the auto-configured executor is typically a `ThreadPoolTaskExecutor`.
- If a custom `Executor` bean exists, auto-configuration normally **backs off**; this executor may be selected for regular `@EnableAsync` according to Spring's resolution rules.
- With multiple executors, the name `taskExecutor`, `@Primary`, `AsyncConfigurer`, integration-specific types, and `spring.task.execution.mode` can affect selection.
- `applicationTaskExecutor` is a special name for certain integrations such as MVC/WebFlux async request handling, and for them the bean must be an `AsyncTaskExecutor`. It is **not synonymous** with every custom `@Async("notificationExecutor")` method.
- `spring.task.execution.mode=force` in Boot 3.5 keeps the auto-configured task executor even when custom executors exist; read the precedence rules carefully if using multiple beans.
- On Java 21+ when `spring.threads.virtual.enabled=true` is enabled, Boot may use a virtual-thread executor, which differs from `ThreadPoolTaskExecutor`; this lesson intentionally uses Java 17 and explicitly declared pools.

**Do not rely on default thread counts or an accidental bean name** if it is a system requirement. In the example below, every `@Async` method explicitly specifies its executor, and the tests verify both bean configuration and actual execution thread.

### 4.2. Why do core, max, and queue matter?

For `ThreadPoolTaskExecutor`:

- `corePoolSize`: baseline number of worker threads.
- `maxPoolSize`: limit of threads when additional workers are needed.
- `queueCapacity`: number of waiting tasks; when the queue is not full, tasks are typically enqueued instead of scaling threads up to max.
- `threadNamePrefix`: helps diagnose which executor is running.
- `RejectedExecutionHandler`: policy when the pool/queue is full.
- `setWaitForTasksToCompleteOnShutdown`, `setAwaitTerminationSeconds`: controls shutdown of worker tasks.

To also test **task rejection**, the example uses `notificationExecutor` with **1 core thread, 1 max thread, and queue capacity = 1**. When task A holds the worker and task B occupies the queue, task C must be rejected under the default policy.

This is an **intentionally small configuration for testing**, not a recommended production configuration. Production requires evaluating throughput, queue boundedness, memory, latency, backpressure, and an appropriate shutdown duration.

## 5. Testing depth: unit tests vs integration tests

| Test type | How is the bean created? | What does it prove? | What does it NOT prove? |
|---|---|---|---|
| Plain JUnit + `new BackgroundJobs()` | No Spring context | Method body logic | `@Async` proxy/executor |
| Mockito mock `BackgroundJobs` | Mock method returning future | Consumer behavior | Real execution/scheduling |
| `@SpringBootTest` + inject `BackgroundJobs` | Real Spring context/proxy | Proxy, executor selection, completion/error, bounded pool | Production external systems without integration |
| `@SpringJUnitConfig` with minimal config | Spring test context + imported beans | Proxy/executor with minimal config | Full Boot auto-configuration |
| `@SpringBootTest(RANDOM_PORT)` | Real HTTP server | HTTP → service → proxy if really called | Does not automatically prove background job finished |
| Manual `Runnable::run` executor in test | Intentionally synchronous | Deterministic logic | Asynchronous thread switch |

**Choose @SpringBootTest(webEnvironment=NONE)** for this lab. We need real Spring AOP and executor configuration, without needing an HTTP server or database to prove `@Async`.

## 6. Complete runnable Java 17+ project

Structure:

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

`spring-boot-starter` provides the required Spring Framework/Scheduling infrastructure; `spring-boot-starter-test` provides JUnit Jupiter, Spring Test, AssertJ, and Mockito. No web starter, Redis, JDBC, or Docker is needed for this lesson.

The project needs a valid Gradle wrapper to run `./gradlew`; the build file above by itself **does not generate the wrapper**. If using Maven, create an equivalent `pom.xml` with the appropriate Spring Boot parent/BOM, starter, starter-test, and Surefire/JUnit Platform.

### 6.2. Enabling @EnableAsync

File `src/main/java/com/example/asynclab/AsyncLabApplication.java`:

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

`@EnableAsync` is the activation point for annotation processing. In the example, all `@Async` methods belong to separate `@Service` beans and are not called during `@PostConstruct` lifecycle.

### 6.3. Declaring two executors with explicit names

File `src/main/java/com/example/asynclab/AsyncExecutorsConfig.java`:

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

`ThreadPoolTaskExecutor` is a Spring bean supporting initialization/shutdown lifecycle; when the Spring context creates the bean, it is initialized before `@Async` submits tasks. Thread names typically look like `notify-worker-1` or `report-worker-1` **by typical observation**; tests only assert the **prefix**, not a hard-coded suffix or fixed thread name.

**Do not confuse configuration settings:** `@Bean("notificationExecutor")` is the **bean name selected by @Async**, while `setThreadNamePrefix("notify-worker-")` is the **log/identification prefix for worker threads**. Bean name and thread name have no automatic synchronization mechanism; tests must check both when this is a requirement.

### 6.4. Result model recording the execution thread

File `src/main/java/com/example/asynclab/JobReceipt.java`:

```java
package com.example.asynclab;

public record JobReceipt(
        String jobId,
        String workerThreadName) {
}
```

The record holds only observable data, without a `Thread` object or mutable global state. When running concurrently, it helps each future carry an independent result per job ID.

### 6.5. Spring service with real @Async

File `src/main/java/com/example/asynclab/BackgroundJobs.java`:

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

        // Signal that the worker has entered the method body.
        entered.countDown();

        try {
            // The test controls the exact moment completion is allowed.
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

        // The Spring async proxy will provide the real future to the caller.
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
        // Direct call to target method within the same bean.
        // Does NOT go through the Spring proxy.
        return captureAsyncThreadName();
    }
}
```

**How the code executes:**
- The caller invokes the `BackgroundJobs.sendNotification` **proxy**.
- The proxy submits the task to the `notificationExecutor` bean.
- The executor thread runs the method body, counts down `entered`, and waits for `release`.
- Meanwhile, the caller receives a `CompletableFuture<JobReceipt>` to observe the result.
- When the test opens `release`, the worker returns `completedFuture(receipt)`; the proxy completes the caller's future.
- `generateReport` uses a different **reportExecutor**.
- `failNotification` throws an error inside the worker, represented as an exceptional future.
- `callOwnAsyncMethod` has no `@Async`, and the call from the target to `captureAsyncThreadName` does not go through the proxy; it is an **intentional negative example**.

Using `CountDownLatch` directly in the public API of a production service is not a common design. Here it serves as an explicit **test seam** to prove scheduling. Production code can extract a `Gate`/client dependency and inject a fake dependency in tests, while keeping the same **principle of not relying on sleep**.

### 6.6. Another service bean calling properly through the Spring proxy

File `src/main/java/com/example/asynclab/JobFacade.java`:

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
        // The jobs dependency is a Spring proxy, not "this".
        return jobs.sendNotification(
                jobId, entered, release);
    }
}
```

This is the recommended fix for self-invocation: design the async boundary on a service bean, and have the caller inject that bean. The test will prove `JobFacade.dispatch` dispatches the task to the executor.

## 7. JUnit integration tests using real Spring proxy and executors

File `src/test/java/com/example/asynclab/AsyncProxyIntegrationTest.java`:

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
            // Release the worker even if an assertion fails.
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

        // callOwnAsyncMethod() calls into the target bean;
        // this.captureAsyncThreadName() does not go through the proxy.
        String selfCallResult =
                jobs.callOwnAsyncMethod()
                        .get(5, TimeUnit.SECONDS);

        assertEquals(caller, selfCallResult);

        // External call still goes through the proxy and selects the executor.
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
            // Must ensure the first worker already occupies the core thread.
            assertTrue(entered.await(5, TimeUnit.SECONDS));

            // Second task sits in queueCapacity = 1.
            second = jobs.sendNotification(
                    "second",
                    new CountDownLatch(1),
                    new CountDownLatch(0));

            // Worker waiting + queue full:
            // Spring ThreadPoolTaskExecutor must reject.
            assertThrows(
                    TaskRejectedException.class,
                    () -> jobs.sendNotification(
                            "third",
                            new CountDownLatch(1),
                            new CountDownLatch(0)));

        } finally {
            // Return the worker to a clean state even if the test fails.
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

The sample suite above has **8 JUnit `@Test` cases**, each targeting a different contract. Every test uses `future.get(timeout)` to **bound wait time** if the worker encounters a configuration error or deadlock; there is no `Thread.sleep`. With `CountDownLatch`, `entered.await` only completes after the worker **actually enters the method**, so `future.isDone()==false` while `release` is closed is a meaningful assertion.

### 7.1. Why do latches make tests less flaky?

If a task is short:

```java
CompletableFuture<String> future =
        jobs.captureAsyncThreadName();

assertFalse(future.isDone()); // Can fail due to race.
```

That `assertFalse` line is an **anti-pattern** because the worker may legitimately finish early. In the `callerReturnsWhileWorkerIsBlocked` test, the worker signals `entered` and then waits for `release` from the test. When `entered.await` returns true and `release` has not counted down to 0, the future must **not have completed normally yet**. The test verifies that the caller can still run assertions while the worker is busy, rather than relying on CPU speed.

### 7.2. Using finally ensures the worker does not get stuck

If an assertion in the test fails without calling `release.countDown()`, the executor thread may wait until its timeout, causing cascading suite failures or prolonged context shutdown. Putting `release.countDown()` in `finally` is an important rule when testing concurrency.

**Limitation:** if the worker code has a bug and never calls `entered.countDown()`, `await(5s)` fails instead of waiting forever, yet the test still needs to release the gate. `get(5s)` is the test's timeout, and does not by itself guarantee the pool has handled every cancellation/interrupt path.

### 7.3. Rejection tests can be affected by parallel test execution

`poolRejectsThirdTaskWhileOneRunsAndOneQueues` assumes that the `notificationExecutor` has no other tasks interfering **concurrently**. With default JUnit Jupiter settings, test methods usually run sequentially; however, if a project enables suite-wide parallel execution, or other beans share the pool, this test needs:
- A dedicated executor/context for the class or an appropriate `@ResourceLock`.
- Not running tests that depend on queue capacity in parallel on the same bean.
- Collecting and awaiting the results of submitted tasks.
- Not changing `queueCapacity` on a production executor just to force a test to pass.

**`TaskRejectedException` occurs at submission**, unlike a worker exception propagated through the future. Do not catch generic `Exception` and claim both are the same type of error.

### 7.4. How to prove the executor was actually used?

Simply `@Autowired ThreadPoolTaskExecutor` and asserting core/max/queue values is not enough. That proves the bean is configured properly, **not that `@Async` selected it**. You also need:
- A call through the Spring proxy.
- `Thread.currentThread().getName()` recorded **inside the worker**.
- Asserting the prefix of `notificationExecutor` or `reportExecutor`.
- A test for self-invocation within the bean returning the caller thread, establishing a negative control.

That is why the lesson includes `springBeanIsProxiedAndPoolHasExpectedLimits`, `namedExecutorsRunOnDifferentThreadPools`, and `selfInvocationRunsOnCallerThread`, rather than just one test checking "future returns the right string".

## 8. Default configuration choices that can mislead tests

### 8.1. @Async without an executor name

```java
@Async
public CompletableFuture<String> doWork() {
    return CompletableFuture.completedFuture(
            Thread.currentThread().getName());
}
```

This is an illustrative method. If the context has multiple executors, executor selection depends on the configuration of Spring async infrastructure and Boot auto-configuration. Do not write `assertTrue(name.startsWith("task-"))` based on an incidental thread name and treat it as a production contract.

When multiple pools are needed:
- Use `@Async("notificationExecutor")`.
- Or define an `AsyncConfigurer` for the default executor used by `@EnableAsync`.
- Or define an explicitly configured `taskExecutor`/primary executor bean according to Spring/Boot rules.

**Special note:** an `applicationTaskExecutor` serving Spring MVC async requests may differ from the named `notificationExecutor` for business jobs. Do not modify the MVC bean just to "fix" an unqualified `@Async` test without understanding all consequences.

### 8.2. AsyncConfigurer when a default executor or uncaught handler is needed

An application can provide:

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
            // Log redacted error, metrics, or send to observability system.
            // Do not log credentials or sensitive data from arguments.
        };
    }
}
```

This is an **illustrative configuration snippet**, not a complete Java file: it requires imports for `Executor`, `@Configuration`, `@EnableAsync`, `AsyncConfigurer`, `@Qualifier`, `AsyncUncaughtExceptionHandler`, and an appropriate executor bean. Do **not** drop this second class directly into the example project without reviewing `@EnableAsync`/beans to avoid duplicate or conflicting configuration precedence.

`getAsyncUncaughtExceptionHandler()` is used to observe errors from `void @Async` methods; future-returning methods should **let the caller handle errors via the future**.

### 8.3. Testing with an intentionally synchronous executor

A unit test can inject an executor like `Runnable::run` to run tasks **immediately on the caller thread**:

```java
Executor sameThread = Runnable::run;
sameThread.execute(
        () -> checkDomainRule());
```

This is an illustrative snippet in a test that has `checkDomainRule()`. This approach is great when the goal is **job logic** independent of concurrency. However, if you use it as the executor in a Spring context and test `@Async` with `assertEquals(expected, future.get())`, the test **does not prove an async thread switch**.

**Categorize tests by goal:**
- Logic unit test: synchronous executor / fake service is valid.
- Async integration test: real executor with another thread, real proxy, latch, and timeout.
- Performance/load test: dedicated benchmark/workload, not using an arbitrary `Thread.sleep` to evaluate throughput.

## 9. Exception handling: CompletableFuture vs void @Async

### 9.1. Future-returning method

`failNotification` in the example throws `IllegalArgumentException` on the worker. The caller receives a `CompletableFuture` completed exceptionally:

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

This is an illustrative snippet in a JUnit test with `jobs` injected; it does not require log inspection. What matters is asserting the real **cause**, avoiding catching any `ExecutionException` whose inner cause is a `NullPointerException` from broken test setup.

If using `join()`, the wrapper exception is typically `CompletionException`. If the future was cancelled, `CancellationException` can appear; cancellation does not necessarily stop a running task if it does not observe interrupt/cancellation state.

### 9.2. void-returning method

```java
@Async("notificationExecutor")
public void fireAndForget(String id) {
    throw new IllegalStateException(
            "Cannot deliver " + id);
}
```

This is an illustrative method. With `void`, the caller receives no `Future` to call `get()` on and cannot expect a synchronous error with `assertThrows(() -> service.fireAndForget("x"))` — unless an error occurs immediately at submission or another behavior occurs outside the method body.

When you genuinely need to test errors of `void @Async`, provide an `AsyncUncaughtExceptionHandler` that can **record the exception into a thread-safe probe** and use `CountDownLatch` for the test to wait for the handler to be invoked. For production errors, have transparent logging/metrics/DLQ/retry policies. If the caller needs to know job status, prefer **`CompletableFuture<T>`** instead of just `void`.

### 9.3. Distinguishing rejection, failure in body, and test timeout

| Error type | When does it occur? | Appropriate way to test |
|---|---|---|
| Executor rejection | When calling proxy / submitting task | `assertThrows(TaskRejectedException.class, ...)` |
| Task body throws exception | On worker thread | `future.get(timeout)`, assert `ExecutionException.getCause()` |
| Future waits too long | When caller awaits result | `assertThrows(TimeoutException.class, () -> future.get(...))` if that is the goal |
| `void @Async` throws exception | On worker thread, no future for caller | `AsyncUncaughtExceptionHandler`/probe |
| Caller interrupted during `get()` | On caller thread | Keep interrupt policy clear, handle `InterruptedException` |
| Worker interrupted | On worker thread | Restore interrupt flag and stop task per policy |
| Missing transaction/session state on worker | When worker accesses ThreadLocal-bound resource | Analyze context propagation, do not catch generic `Exception` |

## 10. @Async and ThreadLocal: transaction, security, MDC

`@Async` executes the method body on the **executor's thread**, not the calling thread. Therefore, the **caller's ThreadLocal does not automatically appear on the worker**, especially when using a thread pool that reuses threads.

### 10.1. @Transactional in a test does not automatically propagate to the worker

If a test has:

```java
@SpringBootTest
@Transactional
class NotificationIntegrationTest {
    // Test-managed transaction resides on the JUnit test thread.
}
```

then the `@Async` worker method runs on a different thread and does not automatically join the test's **test-managed JDBC/JPA transaction**. Rollback at the end of the test **does not guarantee** that changes committed by the worker are reverted. This is especially dangerous when a test uses a real database while assuming `@Transactional` makes all side effects disappear.

**Proper design:** if the worker needs a transaction, have it call a Spring-managed transactional service on the worker thread, or open a transaction explicitly within the worker's scope. Test with an isolated database, distinct data identifiers, and cleanup for independent commits. When combining `@Async` and `@Transactional` on the same method, AOP advice ordering/transaction boundaries must be verified; do not rely on guessing that the caller's transaction moves to the background.

### 10.2. Spring SecurityContext does not automatically follow the executor

An authenticated controller has `SecurityContextHolder` on the request thread. If a background worker tries to get the principal via `SecurityContextHolder.getContext()`, it will likely not have the request's user.

Options:
- Pass the **already-authorized userId/tenantId** as an immutable parameter when submitting the job.
- Use `DelegatingSecurityContextAsyncTaskExecutor` if business requirements genuinely need SecurityContext propagation.
- Use a properly designed and tested TaskDecorator/context propagation, avoiding keeping credentials in long-lived workers.
- Do not enable `MODE_INHERITABLETHREADLOCAL` for reusable thread pools and treat it as a default security solution.

When testing propagation, assert the principal on the **worker thread**, and verify that principals do not leak between tasks of different users. A unit test mocking `SecurityContextHolder` on the caller thread does not prove this.

### 10.3. MDC, trace ID, and request context

SLF4J/Logback `MDC` and many request contexts are thread-bound. TaskExecutor can support `setTaskDecorator(...)` to capture/restore certain contexts, but you must **clear/restore state in finally** to avoid leaks when the pool reuses worker threads. Do not put raw passwords/tokens into MDC.

Illustrative example (not a complete Java file):

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

This snippet requires imports for `java.util.Map`, `org.slf4j.MDC`, and a `ThreadPoolTaskExecutor executor`. It illustrates the principle of restoring the previous context, not replacing standard telemetry/Context Propagation mechanisms if OpenTelemetry/Micrometer Tracing is already in place.

**Do not confuse contexts:** `ThreadLocal` of `@Async`/imperative transactions is different from **Reactor Context** in WebFlux/R2DBC. Using `@Async` does not automatically create or reactively propagate a Reactor Context.

## 11. Stability of async tests on CI

### 11.1. Do not use Thread.sleep to guess

```java
jobs.sendNotification(...);
Thread.sleep(100);
assertEquals(1, auditRepository.count());
```

This is an illustrative anti-pattern, not standalone code: `...` represents undeclared inputs and repository. 100 ms does not guarantee the task has run; CI may be slow or have different JVM scheduling. The result is flaky tests, especially under parallel execution.

Replace with a synchronization contract:
- `CompletableFuture.get(timeout)` when the method returns a future.
- `CountDownLatch.await(timeout)` when you need to confirm the worker entered a phase.
- `Awaitility`/polling with a deadline when only observing external side effects and a future cannot be obtained.
- `StepVerifier` for Reactor publishers; different from Java `@Async` futures.
- An acknowledgement/event test probe reset individually for each test.

**Do not use `assertTimeoutPreemptively` to "cut off a task" when code depends on a test-managed transaction/ThreadLocal**: preemptive timeouts may run code on a different thread, altering test transaction semantics. With Futures, `get(timeout)` is usually the clearer way to bound wait time.

### 11.2. Running multiple tests sharing an executor

If the test suite uses Spring context caching, multiple test classes may share the **same executor bean**. One test that fails to await its jobs will affect subsequent tests:
- The queue still contains tasks when a new test starts.
- The thread prefix remains the same, making races hard to detect.
- Shared static `AtomicInteger`/lists get mutated by old tasks.
- Rejection tests based on a full pool become non-deterministic.
- Context shutdown waits unexpectedly long for lingering tasks.

Solutions: wait for all futures to finish in the test, cancel/clean up per policy, use a dedicated executor for tests needing saturation, and avoid parallel test methods on the same pool when asserting queue capacity. `@DirtiesContext` can help isolate contexts in special tests but carries bootstrap overhead; do not overuse it as a default solution.

### 11.3. Timeout is not a benchmark

A `future.get(5, TimeUnit.SECONDS)` is merely a **deadline to fail in a controlled manner**. It does not prove the job always completes faster than 5 seconds under production load; dedicated performance/load tests on realistic workloads and proper executor pool sizing are needed.

## 12. Rejection, bounded queue, and backpressure design

When both the pool and queue are full, `ThreadPoolTaskExecutor` can throw `TaskRejectedException` at submission. This is valuable to test because the system must decide **what to do when it has no capacity for more work**:
- Return an error to the caller (HTTP 503/429 or appropriate domain status).
- Persist the job into a durable queue (if architecture permits) to retry outside the request.
- Use a circuit breaker or rate limiting at ingress.
- Avoid silently dropping jobs.
- Do not use an unbounded queue to hide overload until running out of memory.

**Do not simulate rejection by having Mockito mock `CompletableFuture.failedFuture` and calling that a saturation test.** That is a task that **was accepted** and completed with an error; rejection happens **before** the executor accepts the task. The `poolRejectsThirdTaskWhileOneRunsAndOneQueues` test creates a real saturation scenario with pool 1 + queue 1.

### 12.1. Why does maxPoolSize not always scale up immediately?

For example, `corePoolSize=2`, `maxPoolSize=8`, `queueCapacity=100`: after the two core threads are busy, the executor may **enqueue** subsequent tasks until the queue is full before creating additional threads (depending on executor implementation). Thus increasing `maxPoolSize` does not necessarily improve latency if the queue is very large.

In this lesson, queue capacity = 1 lets us force rejection predictably after one task occupies the worker and a second queues. This is a **contract test for a specific configuration**, not a universal rule for every executor or handler.

### 12.2. CallerRunsPolicy can lose async characteristics

Some systems intentionally configure `CallerRunsPolicy`: under overload, a task may run immediately on the **caller thread** instead of being rejected. This is an intentional backpressure mechanism, but it changes latency and thread-affinity. If production enables this policy, tests must verify that exact behavior — not always assert `TaskRejectedException`.

The example code uses the default rejection policy, so the test expects `TaskRejectedException` when the pool/queue is full. Do not switch to `CallerRunsPolicy` just to make a test pass if the requirement is to report overload to HTTP clients.

## 13. Distinguishing @Async from @Scheduled

`@Async` and `@Scheduled` both use scheduling infrastructure but answer two different questions:

| Annotation | What triggers it | Executor/Scheduler | Primary test type |
|---|---|---|---|
| `@Async` | A caller invokes a Spring proxy method | `TaskExecutor`/`Executor` | Proxy/executor selection, future/error |
| `@Scheduled(fixedRate=...)` | Periodic scheduler trigger | `TaskScheduler`/`ScheduledExecutorService` | Trigger timing, execution count, idempotency |
| `@Scheduled(cron=...)` | Cron expression + timezone | Scheduler | Clock/timezone/cadence, misfire behavior |
| `@Async @Scheduled` combined | Scheduler triggers method, async advice may submit work | Must understand both scheduler and async executor | Prevent unintended overlapping work |

Do not enable `@EnableScheduling` just to test `@Async`; the demo only enables `@EnableAsync`. With scheduled jobs, you typically separate the **trigger** and the **business worker method** so you can unit test domain logic and integration test scheduling independently.

**Version note:** Boot 3.5 also auto-configures `ThreadPoolTaskScheduler` when needed; `spring.task.scheduling.*` and `spring.task.execution.*` are two different property groups. Do not use `spring.task.scheduling.pool.size` expecting the `@Async` notification pool to change.

## 14. Real-world failures and how to investigate

| Symptom | Cause | Fix direction |
|---|---|---|
| `@Async` does not switch threads | Missing `@EnableAsync`, calling `new`, self-invocation `this.method()`, missing AOP proxy | Inject bean via Spring, test proxy and thread prefix |
| `AopUtils.isAopProxy(bean)==false` | Async post-processor not active or method not eligible | Check context/annotation/visibility |
| Test returns right result without proving async | Method returns `completedFuture` directly on caller | Latch holds worker, assert caller keeps running |
| Self-invocation returns JUnit thread name | Call inside the same target bean | Split bean and call through proxy |
| `private`/`final` method not intercepted | Proxy cannot override/advise method | Public non-final external method |
| `@Async("missingExecutor")` fails | Bean does not exist or wrong name/qualifier | Check bean name/qualifier and context |
| Wrong thread prefix | `@Async` picked another executor | Explicit qualifier; assert thread name inside worker |
| Context has multiple executors, unexpected default | `taskExecutor`/`@Primary`/`AsyncConfigurer`/Boot rules | Choose explicit bean or configure clear default |
| MVC async request behaves differently from business @Async | `applicationTaskExecutor` is not named business executor | Distinguish integration-specific executors |
| Flaky test when asserting `future.isDone()==false` | Task too fast, race | CountDownLatch/blocked worker gate |
| `Thread.sleep(100)` makes test flaky | Scheduler/CI load is non-deterministic | Await with deadline, `Future.get(timeout)` |
| Exception unseen when `void @Async` throws | Exception occurred on worker, caller has no future | `AsyncUncaughtExceptionHandler` or return future |
| `CompletableFuture.get()` throws `ExecutionException` | Worker task failed | Inspect `getCause()`, do not swallow error |
| `TaskRejectedException` immediately on method call | Pool/queue full or executor shut down | Sizing/backpressure/retry/queue policy |
| Thread pool does not grow to `maxPoolSize` | Queue still has capacity, growth policy | Understand core/max/queue and test under controlled load |
| Async method creates DB row despite test rollback | Test transaction ThreadLocal does not move to worker | Worker's own transaction, isolated DB/cleanup |
| SecurityContext is null in worker | ThreadLocal does not propagate automatically | Pass user ID or SecurityContext-aware executor |
| MDC trace ID disappears | MDC does not propagate automatically across pooled threads | TaskDecorator/context propagation and finally restore |
| Job still runs after JUnit test | Did not await future/cancel | Await result, bounded shutdown |
| Saturation test fails under parallel suite execution | Other tasks share the same executor | Dedicated executor/ResourceLock and test isolation |
| `@Async` method called in `@PostConstruct` is not async | Bean proxy not ready yet | Call from separate bean after initialization |
| Java 21 virtual threads differ from expected prefix | Boot auto-configures virtual executor | Distinguish version/runtime; explicit pool if needed |
| `@Async` method returning `Mono`/`Flux` does not behave like `Future` | Async return type breaks contract | Use Reactor scheduler/Reactive API |
| Build green but tests did not run | `NO-SOURCE`, skipped, wrong JUnit runner | Check reports/tests executed |

### 14.1. 10-step debugging sequence

1. Identify which bean the `@Async` call originates from and whether it goes through a Spring proxy.
2. Verify `@EnableAsync` is imported in the test context.
3. Verify the method is public/non-final; `@Async` is not placed on a `@Configuration` method.
4. Verify `@Async("beanName")` matches the exact executor bean.
5. Assert proxy with `AopUtils.isAopProxy` — **combined with** checking the execution thread.
6. Record the thread name from **inside the method**, not just the caller name.
7. Use `CountDownLatch` to synchronize worker entered/release phases, not guessing with sleep.
8. Inspect `future.get().getCause()` errors or task rejection at submission.
9. Check whether the executor was shut down, the queue is full, or context caching is sharing jobs.
10. Check thread-local context, `@Transactional`, security, and MDC if results differ between the JUnit thread and worker thread.

## 15. Running tests and checking reports properly

Linux/macOS if the project has a Gradle wrapper:

```bash
./gradlew test --tests "com.example.asynclab.AsyncProxyIntegrationTest"
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.asynclab.AsyncProxyIntegrationTest"
```

With Maven wrapper once dependencies/config are converted to an equivalent `pom.xml`:

```bash
./mvnw -Dtest=AsyncProxyIntegrationTest test
```

Windows PowerShell:

```powershell
.\mvnw.cmd -Dtest=AsyncProxyIntegrationTest test
```

**Expected outcome** in a suitable environment: 8 test methods are discovered and executed; assertions for proxy, two executors, self invocation, future exception, and saturation pass. However, **this article does not claim to have executed the 8 tests**. You must inspect `build/reports/tests/test/index.html` or `target/surefire-reports/` for the module and the actual task status, rather than concluding solely from `BUILD SUCCESSFUL` if tests were skipped or `NO-SOURCE`.

**There is no fixed business stdout**: thread IDs and suffixes can vary by JVM and test timing, so the code asserts prefixes instead of printing a fixed unreliable line.

### 15.1. Why not use standalone javac?

The code uses Spring Boot, scheduling/AOP, and JUnit Jupiter, so `javac` needs a full classpath. In the sample project, running through Gradle/Maven with declared dependencies is the verified workflow. If you want to isolate Java logic without Spring, you can extract it into a plain class and test with `javac`/the corresponding JUnit runner, but that **is not testing @Async through a proxy**.

## 16. QA checklist for @Async and configured executor

- [ ] `@EnableAsync` is present in the actual Spring test context.
- [ ] Test retrieves the `@Autowired` bean, not `new`, when targeting proxy execution.
- [ ] `@Async` method is called **from another bean** or externally through the Spring proxy.
- [ ] Method is public/non-final and return type is `void`/`Future`/`CompletableFuture` per supported API.
- [ ] Negative case for self-invocation is tested if the codebase carries that risk.
- [ ] `@Async("notificationExecutor")` points to the right bean name/qualifier.
- [ ] Test verifies the executor **was actually selected** via thread name inside the worker, not just bean config.
- [ ] Test differentiates two named executors when the project uses multiple pools.
- [ ] Uses `CountDownLatch`/future synchronization, avoiding `Thread.sleep` schedule guessing.
- [ ] `future.get(timeout)` has a deadline, not waiting indefinitely.
- [ ] Latch is released in `finally` so workers/context do not get stuck.
- [ ] For exceptions, assert the cause inside `ExecutionException`; for void use a handler/probe.
- [ ] When saturation is a contract, test bounded queue + rejection isolated from parallel tasks.
- [ ] Production sizing/backpressure is a separate decision, not copying the demo's pool size 1.
- [ ] Test-managed JDBC/JPA transactions are not assumed to propagate to worker threads.
- [ ] SecurityContext/MDC/request scope are propagated intentionally and cleared per lifecycle.
- [ ] Distinguish MVC async `applicationTaskExecutor` from named business executors.
- [ ] If using Java 21 virtual threads or a different Boot version, verify the right executor type.
- [ ] Clean up/await all submitted futures, preventing tests from leaking tasks into subsequent methods.
- [ ] Read actual JUnit reports to confirm tests ran before reporting a runtime PASS.

## 17. Official sources

- [Spring Framework 6.2 — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@EnableAsync`, `@Async`, executor qualification, proxy mode, and `AsyncUncaughtExceptionHandler`.
- [Spring Framework 6.2 — @Async Javadoc](https://docs.spring.io/spring-framework/docs/6.2.2/javadoc-api/org/springframework/scheduling/annotation/Async.html): return types `void`/`Future`, `CompletableFuture`, `value` executor qualifier, `@Configuration` methods limitation.
- [Spring Framework — @EnableAsync Javadoc](https://docs.spring.io/spring-framework/docs/6.2.11/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html): default proxy mode, executor selection, and `AsyncConfigurer`.
- [Spring Boot 3.5 — Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html): auto-configured `applicationTaskExecutor`, `taskExecutor`, multiple Executor beans, Boot `spring.task.execution.*`, Java 21 virtual threads.
- [Spring Framework — ThreadPoolTaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.5/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html): core/max/queue/thread prefix, rejection, shutdown.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): self-invocation and AOP proxy limits.
- [JUnit Jupiter — User Guide](https://docs.junit.org/current/user-guide/): method lifecycle, JUnit Platform, and parallel execution.

**Conclusion:** Proper `@Async` testing must go through the **Spring proxy**, verify the **actually selected executor**, and observe the worker thread using synchronization with a deadline. `@WithMockUser` or `@Transactional` on the JUnit thread does not automatically move state to the worker, and `this.asyncMethod()` does not trigger the proxy. Use `@SpringBootTest` with named `ThreadPoolTaskExecutor` beans, `CountDownLatch`, and `CompletableFuture` to verify thread switching, self-invocation, exceptions, and task rejection; do not claim async works just because a method has the annotation or a test sleeps with `Thread.sleep` and sees data.