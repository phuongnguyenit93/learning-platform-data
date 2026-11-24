# Do Not Rely on @Async on a Bean's Own @PostConstruct Callback

## 1. Core Lesson

In the Spring Framework, `@PostConstruct` is a **bean lifecycle callback**: the container invokes this method during bean initialization. `@Async` is an **interceptor mechanism**: in the default proxy-based mode, an external call must pass through the Spring proxy before the task is submitted to an executor.

The two mechanisms happen at **different times**. Therefore, **do not place `@Async` on the `@PostConstruct` method itself and expect it to run in the background automatically**. Nor should you expect calling `this.loadData()` inside `@PostConstruct` to trigger `@Async` on `loadData()` of the same bean.

The Spring Framework explicitly states: `@Async` is not supported in combination with lifecycle callbacks such as `@PostConstruct`; for asynchronous initialization, use a **separate initializer bean** calling the `@Async` method on the target bean. For heavy work, a simpler and safer approach in Spring Boot is triggering it after the context is initialized, such as via `ApplicationRunner` or the `ApplicationReadyEvent`, and then calling **another worker bean**.

Common scenario:

- The application starts up and needs to fetch reference data from an API.
- A developer writes `@PostConstruct @Async public void warmUp()` and assumes startup will return immediately.
- In reality, the callback may execute directly on the bean-initialization thread, prolonging startup; if the callback throws an error, startup may fail.
- The developer moves the logic into `@Async public void warmUp()` yet calls `this.warmUp()` directly from `@PostConstruct`. The call still does not pass through the proxy, so it still runs synchronously.
- The fix is having a **call path through another bean's proxy**, from an appropriate trigger point, with explicit executor, timeout, error handling, and readiness policy.

Scope: Java 17, Spring Framework 6.x, Spring Boot 3.3.x with `@EnableAsync` defaulting to `AdviceMode.PROXY`. With AspectJ weaving or custom lifecycles, some interceptor details differ, yet the principle of **not relying on `@Async` on initialization callbacks** remains useful.

## 2. Distinguishing Three Things: Target Bean, Proxy, and Callback

Spring typically builds a bean along a general sequence:

1. Instantiate the class (constructor).
2. Inject dependencies and set properties.
3. Run pre-initialization `BeanPostProcessor`s, including `@PostConstruct` handling by `CommonAnnotationBeanPostProcessor`.
4. Run initialization callbacks such as `InitializingBean.afterPropertiesSet()` or a declared init method.
5. Post-initialization post-processors may create an AOP proxy wrapping the bean.
6. Other beans are injected with an appropriate reference, which may be the proxy itself; only calling a public method through this reference has the chance to be intercepted by async advice.

This is a **conceptual** diagram, not a promise that every extension across every Spring version follows the exact same internal ordering:

~~~text
Spring container
   |
   +-- new TargetBean()
   +-- inject dependencies
   +-- @PostConstruct runs on bean during init phase
   +-- finish initialization / create proxy when applicable
   |
   +-- expose Spring proxy -----> caller in another bean
                                      |
                                      +-- proxy intercepts @Async
                                      +-- executor.execute(task)
                                      +-- worker thread runs target method

Inside TargetBean:
@PostConstruct init() -> this.asyncMethod()
                          |
                          +-- calls target directly, DOES NOT go through proxy
~~~

**There is no automatic "jump to a new thread" simply because the method's bytecode carries `@Async`.** The interceptor must receive the call through the right proxy. This is also why code manually created with `new MyService()` or self-invocation `this.method()` normally bypasses `@Async`.

**Exact note on `@PostConstruct`:** it executes at a stage when the bean has not yet finished initializing. Spring may create a proxy for *the exposed bean* afterward, yet the callback is not an external application call entering an already established proxy. Do not use the callback as an arbitrary background-work dispatch point, and certainly do not work around it by self-injecting to grab the proxy: self-references/circular dependencies make startup complex and fragile.

## 3. Two Common Anti-Patterns

### 3.1. Placing Both @PostConstruct and @Async on One Method

~~~java
import jakarta.annotation.PostConstruct;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;

@Component
public class CacheBootstrap {
    @PostConstruct
    @Async("bootstrapExecutor") // Does not make this callback run async.
    public void preload() {
        fetchAllRemoteRecords(); // Can hold the initialization thread for a long time.
    }

    private void fetchAllRemoteRecords() {
        // Represents slow I/O, not a standalone runnable example.
    }
}
~~~

If `fetchAllRemoteRecords()` takes 20 seconds, bean initialization time can increase accordingly. `@Async` does not turn the callback into a background job. In Spring Boot 3 use `jakarta.annotation.PostConstruct`, **not** `javax.annotation.PostConstruct` from older Spring projects if dependencies are incompatible.

### 3.2. @PostConstruct Calling @Async on the Same Bean

~~~java
import jakarta.annotation.PostConstruct;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class InventoryBootstrap {
    @PostConstruct
    public void init() {
        this.refreshAsync(); // Bypasses proxy: calls directly on the same object.
    }

    @Async("bootstrapExecutor")
    public void refreshAsync() {
        // Here it can still run on the init() callback thread.
    }
}
~~~

This is a case of **self-invocation**. Even after the bean has been proxied and is called from another method of the target itself post-startup, `this.refreshAsync()` is not intercepted in proxy mode; inside `@PostConstruct` there is the additional lifecycle-timing issue.

Contrast this with a valid call:

~~~java
// Illustrative snippet in ANOTHER bean, with a Spring proxy injected:
private final InventoryWorker worker;

public StartupTrigger(InventoryWorker worker) {
    this.worker = worker;
}

public void trigger() {
    worker.refreshAsync(); // Call to another bean through the proxy.
}
~~~

The snippet above is not a complete class; `InventoryWorker` must be a Spring-managed bean and `refreshAsync()` must be eligible for async execution.

## 4. Complete Runnable Example on Java 17 and Spring Boot 3.3

This example demonstrates **both the mistake and the right approach in a single run**. It does not rely on `Thread.sleep` to prove thread switching. A dedicated executor uses the `init-worker-` prefix; code records the thread name **directly inside the real method**, then prints deterministic boolean results.

### 4.1. Project Structure

~~~text
lifecycle-async-demo/
├── pom.xml
└── src/main/java/com/example/lifecycle/
    ├── LifecycleAsyncApplication.java
    ├── WrongLifecycleBean.java
    └── WarmupWorker.java
~~~

### 4.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>lifecycle-async-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-boot-starter` provides Boot and core dependencies; `spring-boot-starter-aop` ensures explicit AOP proxy infrastructure. `jakarta.annotation.PostConstruct` is used per Spring Boot 3. No web server or database is needed to run the demo.

### 4.3. LifecycleAsyncApplication.java

~~~java
package com.example.lifecycle;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@SpringBootApplication
@EnableAsync
public class LifecycleAsyncApplication {
    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(
                             LifecycleAsyncApplication.class, args)) {
            // Close context after ApplicationRunner completes.
        }
    }

    @Bean("initExecutor")
    ThreadPoolTaskExecutor initExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(1);
        pool.setMaxPoolSize(1);
        pool.setQueueCapacity(8);
        pool.setThreadNamePrefix("init-worker-");
        pool.setWaitForTasksToCompleteOnShutdown(true);
        return pool;
    }

    @Bean
    ApplicationRunner afterStartup(WarmupWorker worker) {
        return args -> {
            System.out.println("RUNNER_ON_POOL="
                    + isWorkerThread());

            // This is a call FROM another bean/runner into the Spring proxy.
            CompletableFuture<String> result = worker.prepare();

            // Runner waits intentionally so the demo produces deterministic output.
            String actualThread = result.get(5, TimeUnit.SECONDS);
            System.out.println("SEPARATE_BEAN_ON_POOL="
                    + actualThread.startsWith("init-worker-"));
        };
    }

    private static boolean isWorkerThread() {
        return Thread.currentThread().getName().startsWith("init-worker-");
    }
}
~~~

Key point: `afterStartup` is an `ApplicationRunner`. Spring Boot invokes runners **after the `ApplicationContext` has refreshed** and required singletons have been created. `worker.prepare()` is a call to **another Spring-managed worker**, through the `@Async("initExecutor")` proxy.

The runner deliberately uses `get(5, TimeUnit.SECONDS)` only to keep demo stdout ordered, bounded, and allow clean context shutdown. If the real requirement is "start a background job and let the web server accept requests immediately," **do not wait on the `Future` on the startup thread**; maintain job/readiness state and a dedicated tracking mechanism instead.

### 4.4. WrongLifecycleBean.java

~~~java
package com.example.lifecycle;

import jakarta.annotation.PostConstruct;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;

@Component
public class WrongLifecycleBean {
    @PostConstruct
    @Async("initExecutor")
    public void initialize() {
        System.out.println("POST_CONSTRUCT_ON_POOL="
                + isWorkerThread());

        // Same bean, calling this; @Async on the method below is bypassed.
        this.selfInvokedAsync();
    }

    @Async("initExecutor")
    public void selfInvokedAsync() {
        System.out.println("SELF_CALL_ON_POOL="
                + isWorkerThread());
    }

    private boolean isWorkerThread() {
        return Thread.currentThread().getName().startsWith("init-worker-");
    }
}
~~~

Both values are printed inside the callback itself and the self-called method, rather than checking a mocked variable. Spring creates `WrongLifecycleBean` during context initialization, so these two lines appear before the lines from `ApplicationRunner`.

Even though `initialize()` is annotated with both `@PostConstruct` and `@Async`, the callback still does not run through async advice. Likewise, `selfInvokedAsync()` is not submitted to the executor because the call is `this.selfInvokedAsync()`.

### 4.5. WarmupWorker.java

~~~java
package com.example.lifecycle;

import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class WarmupWorker {
    @Async("initExecutor")
    public CompletableFuture<String> prepare() {
        // Read the thread name RIGHT inside the worker's actual code.
        String name = Thread.currentThread().getName();
        return CompletableFuture.completedFuture(name);
    }
}
~~~

Returning `CompletableFuture<String>` matches `@Async`. The method implementation returns a completed future so the Spring async proxy can capture the result of the task run by the executor; the caller receives a `Future` representing the dispatched work. That does **not** mean the implementation ran on the caller: the thread name is read inside the method and the result will have the `init-worker-` prefix.

### 4.6. Running and Expected Output

Requires JDK 17+ and Maven. In the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Ignoring Spring and Maven logs, **the four lines printed by the program** in order are:

~~~text
POST_CONSTRUCT_ON_POOL=false
SELF_CALL_ON_POOL=false
RUNNER_ON_POOL=false
SEPARATE_BEAN_ON_POOL=true
~~~

Why is this result reliable?

1. `WrongLifecycleBean.initialize()` is invoked by the container during bean initialization, on the startup thread rather than an `initExecutor` thread. Thus the first line is `false`.
2. `this.selfInvokedAsync()` is a direct call without going through a proxy, so the second line is also `false`.
3. `ApplicationRunner` runs on the normal application startup thread, so the third line is `false`.
4. `WarmupWorker.prepare()` is called on another bean's proxy after startup and uses `initExecutor` properly; the real method executes on a thread with prefix `init-worker-`, yielding `true` on the fourth line.

The demo does not require multiple concurrent workers to prove the proxy path. With `ThreadPoolTaskExecutor`, `corePoolSize=1`, `queueCapacity=8` only describes this **demo's** configuration, not Spring's defaults. Besides the three files and `pom.xml` listed, no hidden code files are needed. This is an example to **understand the mechanism**, not a design for executing heavy batch workloads in production.

## 5. Fixes in Real-World Environments

### 5.1. Prefer Triggering with ApplicationRunner

Spring Boot provides `ApplicationRunner` and `CommandLineRunner` to run code once the context is prepared and started. Split into two beans:

~~~java
// Snippet inside the trigger bean, not a standalone program.
@Component
public class WarmupTrigger implements ApplicationRunner {
    private final CatalogWorker worker;

    public WarmupTrigger(CatalogWorker worker) {
        this.worker = worker;
    }

    @Override
    public void run(ApplicationArguments args) {
        worker.refreshCatalog(); // Caller goes through ANOTHER bean's proxy.
    }
}
~~~

Requires importing `org.springframework.stereotype.Component`, `org.springframework.boot.ApplicationRunner`, and `org.springframework.boot.ApplicationArguments`. `CatalogWorker` is a separate service bean with a public `@Async("catalogExecutor")` method. The snippet above does not await the result; production usage requires error handling, retry/timeout, and completion status tracking.

When multiple runners are needed, use `@Order` or `Ordered` to control ordering among runners, yet **do not** assume async tasks finish in that order. If runner A submits a job and returns immediately, runner B can execute while job A is still running.

### 5.2. Use @EventListener(ApplicationReadyEvent.class) When Starting After Runners

In Spring Boot, `ApplicationReadyEvent` is published **after `ApplicationRunner`/`CommandLineRunner` beans have been called**. A listener can invoke another worker:

~~~java
// Illustrative snippet in a separate Spring-managed bean.
@Component
public class ReadyTrigger {
    private final CatalogWorker worker;

    public ReadyTrigger(CatalogWorker worker) {
        this.worker = worker;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onReady() {
        worker.refreshCatalog();
    }
}
~~~

Requires importing `org.springframework.context.event.EventListener`, `org.springframework.boot.context.event.ApplicationReadyEvent`, and `org.springframework.stereotype.Component`. With a standard event listener, the handler initially runs on the thread publishing the event; above, **calling `worker.refreshCatalog()` through the proxy** is what moves the heavy work to the executor.

**Do not confuse "ready event published" with "warm-up data is ready."** If the listener just submits a background job and returns right away, Spring Boot can still transition readiness to accept traffic before the work finishes. If APIs only work properly after warm-up completes, use a readiness gate, initialization state control, or bounded synchronous startup. Do not use a non-synchronized boolean flag and forget memory visibility.

If the context refreshes again or the application has a multi-context hierarchy, watch out for duplicate events and initialization idempotency. With multiple pods, each pod may receive the event, so cluster-wide shared jobs need a coordination mechanism.

### 5.3. Using a Separate Initializer Bean with @PostConstruct — Conditionally

Spring documentation also describes a pattern where an independent initializer bean injects the target bean and invokes an async method inside `@PostConstruct`:

~~~java
// Minimal pattern per documentation; not a standalone Java program.
@Component
public class CatalogInitializer {
    private final CatalogWorker worker;

    public CatalogInitializer(CatalogWorker worker) {
        this.worker = worker;
    }

    @PostConstruct
    public void initialize() {
        worker.refreshCatalog(); // Different bean, reference can be a proxy.
    }
}
~~~

Compared to `this.refreshCatalog()` on the same bean, the call above **can pass through `CatalogWorker`'s proxy** if the target bean was already constructed and injected properly. However, the initializer bean's `@PostConstruct` still runs during the singleton creation phase. It does not guarantee all dependencies in the context are ready, and can introduce circular dependencies, deadlocks, or races if the worker immediately accesses beans/resources still being initialized. For heavy work, multi-dependency flows, or explicit startup requirements, prefer a post-refresh runner/event rather than dispatching inside a lifecycle callback.

If you do use this variant, keep the initializer **strictly responsible for dispatching**, avoid waiting on `future.get()` inside `@PostConstruct`, and test startup for timeouts/circular dependencies.

### 5.4. What About SmartInitializingSingleton or ContextRefreshedEvent?

`SmartInitializingSingleton.afterSingletonsInstantiated()` runs after regular non-lazy singletons are instantiated, which helps if work needs singletons ready without waiting until `ApplicationReadyEvent`. `ContextRefreshedEvent` fires after context refresh; a listener can dispatch to another bean.

Neither hook replaces full startup semantics: consider lazy beans, multiple contexts, refresh cycles, server/readiness state, and asynchronously dispatched tasks. Choose a hook based on **what preconditions must hold before running** and tolerance for background jobs, rather than simply picking based on the word "after".

## 6. If the Work Is Required Before the Application Is Ready

Two designs must be kept distinct:

| Goal | Trigger Point | Readiness Condition | Error Handling |
| --- | --- | --- | --- |
| Lightweight, mandatory, fast initialization | `@PostConstruct` or init method | Bean initialization completes only after the work | Fail startup explicitly if invalid |
| Load mandatory data before serving | `ApplicationRunner`, invoke business logic (synchronously or await `Future` **with timeout**) | Runner succeeds only when mandatory work succeeds | Fail startup or set readiness `REFUSING_TRAFFIC` |
| Optional warm-up that can finish later | `ApplicationReadyEvent` / runner async dispatch | Allows the application to serve in a fallback state | Logging, metrics, retry/backoff, appropriate health status |
| Batch job that must run only once across the cluster | Job scheduler/queue/leader election, DB lease | Depends on shared contract | Idempotency, locks/claims, and durable state |

**Do not treat an `@Async` method as proof of readiness.** Creating a `Future` proves a task submission was attempted (and rejections must still be handled); it does not mean the task finished.

If a runner awaits a `Future` to gate startup, it must have a deadline:

~~~java
// Illustrative snippet inside ApplicationRunner, not standalone.
CompletableFuture<Void> job = worker.initializeRequiredData();

try {
    job.get(20, TimeUnit.SECONDS);
} catch (TimeoutException ex) {
    job.cancel(true); // Only a cancellation request, does not guarantee worker stopped.
    throw new IllegalStateException("Required data initialization timed out", ex);
}
~~~

Requires importing types from `java.util.concurrent`; `initializeRequiredData()` is an application-defined method. Also handle `ExecutionException` and `InterruptedException`: record the root cause, restore the interrupt flag when catching `InterruptedException`, and decide whether to fail startup or enter degraded readiness. `cancel(true)` does not automatically roll back DB transactions and does not stop tasks that ignore interrupts.

Spring Boot publishes `ApplicationReadyEvent` after runners, and enters a readiness state accepting traffic unless customized. If a runner waits for completion before returning, you ensure startup does not report ready prematurely, though waiting also lengthens deployment time and can trip health-probe timeouts. Choose bounds fitting your operational platform.

## 7. Distinguishing Initialization Errors from Async Task Errors

### 7.1. Exceptions Thrown in @PostConstruct Can Fail Bean Creation

~~~java
// Illustrative snippet inside a @Component.
@PostConstruct
public void checkConfiguration() {
    if (requiredEndpoint == null) {
        throw new IllegalStateException("Missing endpoint");
    }
}
~~~

You do not need `@Async` to check a simple condition like the one above. If an error occurs inside the callback, Spring can halt bean creation and fail context startup. That makes sense for **mandatory configuration checks** and is why `@PostConstruct` should remain short, clear, and deterministic.

### 7.2. Exceptions Thrown in @Async void Do Not Return to Caller via Future

~~~java
// Illustrative snippet inside a worker bean.
@Async("initExecutor")
public void refreshCatalog() {
    throw new IllegalStateException("remote service unavailable");
}
~~~

When invoked through the proxy and executed asynchronously by an executor, the exception occurs on the worker. With a `void` return type, the caller has no `Future` to receive the error; Spring uses `AsyncUncaughtExceptionHandler` (which mainly logs errors by default). With `CompletableFuture<T>`/`Future<T>`, the caller can observe errors via `get()/join()` or completion callbacks.

Therefore, if warm-up matters, **return a `Future` to monitor status** instead of unmonitored fire-and-forget. When the executor is saturated and rejects right at submission, `TaskRejectedException` can also occur on the caller. Do not use a silently-discarding rejection policy for tasks whose results readiness or a `Future` depends on, because the job may be dropped while the `Future` never completes.

### 7.3. Do Not Hide Errors Behind Startup Callbacks

If you dispatch from `ApplicationReadyEvent` without awaiting it, startup can still report ready even if warm-up fails. For optional jobs, log with a job ID and emit metrics; for mandatory jobs, use a readiness gate and fallback matching business requirements. A startup hook being invoked successfully does not prove remote data, caches, or DB snapshots are ready.

## 8. ThreadLocal, Transactions, Proxies, and True Asynchrony

Once fixed so calls go through the proxy, behavioral differences may surface that earlier tests missed when the callback ran synchronously:

- **Transactions:** transaction association belongs to the thread; `@Transactional` on the callback/caller does not automatically move to the worker. The worker needs its own transaction boundary, typically via a Spring-proxied service bean. Do not pass JDBC connections/`EntityManager`s across threads.
- **MDC/trace/security:** `ThreadLocal` values do not automatically transfer to the worker; capture needed IDs and pass them as parameters, or configure context propagation such as a `TaskDecorator`. The worker must clean up context when the pool reuses threads.
- **Request scope:** during application startup there is normally no HTTP request. Do not inject/use request-scoped beans inside startup callbacks as if a request context existed.
- **Mutable objects:** sending a task to another thread can race if the callback continues mutating an object the worker reads. Use immutable snapshots or proper synchronization.
- **Bean dependencies:** the injected worker is a Spring-managed bean, yet it might call another service that is lazy or relies on an external resource that is not ready yet; guard preconditions and retries.
- **ThreadPoolTaskExecutor:** configure core/max/queue sizes, rejection policy, thread naming, and graceful shutdown appropriately; Framework or Boot defaults do not guarantee a fixed thread count across all environments.

Likewise, `@Async` on `private`/`final` methods or `final` classes has proxy limitations in common proxy modes; use **`public`, non-`final`** methods on a Spring bean called by another bean. Enabling `@EnableAsync` in the right `ApplicationContext` and invoking through the proxy are essential conditions. If `SyncTaskExecutor` is used, calls through the proxy may be intercepted yet still run on the **caller thread**, because the executor itself is synchronous. Thus, when diagnosing, verify both the **proxy path** and the **executor implementation**, not just the thread name.

## 9. Diagnosing: @Async Does Not Run After @PostConstruct

| Symptom | Common Cause | How to Check / Fix |
| --- | --- | --- |
| `@PostConstruct @Async` still runs on the main thread | Callback is invoked during bean initialization, not through the async proxy | Remove `@Async` from the callback; dispatch from a runner/event to another worker bean |
| `this.asyncWork()` still runs synchronously | Self-invocation bypasses the proxy | Extract worker into another bean, inject proxy |
| Background work slows down startup | Callback does heavy I/O before bean initialization finishes | Move to a post-refresh hook with explicit timeout |
| `@Async` is present, yet no worker thread appears | Missing `@EnableAsync`, self-call, calling `new` object, or using `SyncTaskExecutor` | Check bean, interceptor, executor, and thread prefix |
| Startup shows ready, yet data is not loaded | Async task runs after runner/listener returns | Use a readiness gate or await `Future` with a deadline |
| Warm-up exception does not fail startup | `void @Async` runs detached, errors go to uncaught handler | Return `CompletableFuture`, handle failure, and evaluate readiness |
| Occasional deadlock at startup | Cross-bean waiting/triggering from `@PostConstruct` under singleton creation lock | Move to a post-refresh runner, reduce circular dependencies |
| Extracted to worker bean, yet `@Transactional` misbehaves | Caller's transaction context does not follow the worker | Define transaction on a proxied call inside the worker |
| Synchronous test passes, production races | Real worker runs concurrently, sharing mutable state | Use latches, immutable data, proper locks/transactions |
| Multiple pods all run warm-up | Startup hook runs on every instance | Use idempotency or coordination if cluster-wide single execution is needed |

### Pre-Merge Checklist

1. `@PostConstruct` only validates config or initializes lightweight state—no heavy I/O and no reliance on `@Async`.
2. The method meant for background execution lives on **another Spring-managed bean**, invoked from an appropriate trigger after proxies are ready.
3. `@EnableAsync` is enabled in the right context, and code does not go through `this.method()` or an object created with `new`.
4. The executor is explicitly specified (name/qualifier) with a thread prefix for observability; queue/rejection/shutdown are reviewed.
5. The async method has a valid return type: `void`, `Future<T>`, or `CompletableFuture<T>`. If startup depends on the outcome, do not use `void` without an error-reporting path.
6. Timeouts, error handlers, logging, and failure state exist for warm-up. Do not assume `Future.get(timeout)` cancels the task automatically.
7. Explicit readiness policy: must the work finish before traffic? Does the event/runner return before the work completes?
8. Context/security/transactions and mutable state are redesigned for the worker thread; do not assume callback thread context persists.
9. Tests verify **inline callback**, **inline self-call**, and **true cross-bean async**; also test overload and shutdown if the job is critical.
10. With multiple instances, the job may trigger multiple times; use idempotency, a job ledger, or cluster coordination when needed.

## 10. Thought Exercises

1. Why does `@PostConstruct @Async public void init()` not guarantee background execution even when `@EnableAsync` is enabled?
2. A `load()` method is annotated with `@Async`, yet `@PostConstruct` in the same bean calls `this.load()`. How must the bean structure change for the interceptor to apply?
3. How does calling another bean from `ApplicationRunner` differ from self-invocation? When should the runner await the result, and when should it return immediately?
4. `ApplicationReadyEvent` is published after runners. If a listener submits a job and returns immediately, has the job finished when readiness begins accepting traffic?
5. Why can `@Async void` log an error without failing startup? If warm-up is mandatory, which return type should be chosen?
6. A test running with `SyncTaskExecutor` sees the callback and worker on the same thread. How do you distinguish "proxy did not trigger" from "proxy triggered, but executor is synchronous"?
7. If a warm-up job takes 30 seconds and queries a slow DB, how should you weigh timeouts, retries, transactions, and readiness?
8. If an application runs three pods, does switching from `@PostConstruct` to `ApplicationRunner` automatically stop all three pods from running a global job simultaneously?

**Conclusion:** `@PostConstruct` is a **container callback during the bean-creation phase**, not an application call entering through a Spring proxy. `@Async` in proxy mode only takes effect when the call passes through the proxy and an appropriate executor. Do not place `@Async` on the lifecycle callback itself or rely on `this.asyncMethod()`. Use a separate trigger after beans are ready to invoke another worker bean, while specifying clear timeout, error, and readiness rules.

## Official References

- [Spring Framework — Task Execution and Scheduling, @Async](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — @PostConstruct / @PreDestroy](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/postconstruct-and-predestroy-annotations.html)
- [Spring Framework — Bean lifecycle and initialization](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Spring Boot 3.3 — SpringApplication and Application Events](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Spring Framework — @EnableAsync Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html)
