# Extracting Asynchronous Methods to a Collaborating Bean

## 1. Goal and Problem

In the Spring Framework, `@Async` allows a method to be executed via a `TaskExecutor` without the caller manually creating a `Thread`. However, in the **default proxy mode**, the annotation takes effect when the call **goes through the Spring proxy**. If a method on a bean calls another `@Async` method using `this.method()`, that is an internal call on the target object and normally **is not intercepted by the proxy**. As a result, the code runs synchronously on the calling thread, contrary to expectations.

**Extracting the asynchronous method into a collaborating bean** is a simple, clear-responsibility, and generally recommended design: the first bean orchestrates the business flow; the second bean owns the `@Async` method and is injected into the orchestrating bean. Calls between the two beans go through a Spring-provided reference so the interceptor has the opportunity to hand the work off to the executor.

~~~text
Before — self-invocation:

Caller -> OrderService.start()
                   |
                   +--> this.sendEmailAsync()
                           ^ 
                           | Does not go through Spring proxy
                           v
                       Runs directly on current thread


After — extracted collaborating bean:

Caller -> OrderService.start()
                   |
                   +--> EmailWorker proxy.sendAsync()
                               |
                               +--> @Async interceptor
                                         |
                                         +--> TaskExecutor
                                                   |
                                                   +--> worker thread
                                                            |
                                                            +--> EmailWorker target
~~~

**Both conditions are required together:** the executing bean must be **managed by the Spring IoC container**, and the `@Async` method must be invoked through the appropriate interception mechanism (in proxy mode, **called through the proxy**). Splitting classes while still calling `new EmailWorker()` will not solve the problem.

## 2. Why Does Internal Invocation Disable @Async?

Spring supports `@Async` processing via `@EnableAsync` and the AOP infrastructure. In the default `AdviceMode.PROXY`, an object used by callers can be a proxy. The proxy inspects calls passing through it, dispatches `@Async` methods to an executor, and runs the real method on a worker.

However, inside a method of the **target bean**, the expression `this` refers to the target itself. The call `this.asyncMethod()` **does not go back through the proxy** to pass through the interceptor.

~~~java
@Service
public class OrderService {
    public void checkout(Order order) {
        saveOrder(order);
        this.sendEmailAsync(order.id()); // Does NOT trigger @Async through proxy
    }

    @Async
    public void sendEmailAsync(long orderId) {
        sendEmail(orderId);
    }
}
~~~

This is an **illustrative code snippet**, not a standalone application: the `Order` type, `saveOrder`, `sendEmail`, and imports are omitted. Even when `OrderService` is a container-created singleton and `@EnableAsync` is present, `this.sendEmailAsync(...)` is still an ordinary internal Java call. It runs on the current thread.

Common misconception: calling `checkout()` **through the proxy** does not automatically make **every internal call** inside `checkout()` continue to be intercepted by the proxy. At the target boundary, `this` is not the outer proxy in the way default Spring proxy AOP operates.

### 2.1. Non-Interchangeable Conditions

| Condition | Why Is It Needed? | What If Missing? |
| --- | --- | --- |
| `@EnableAsync` or matching async infrastructure | Allows Spring to register annotation processing | Annotation may not create an async interceptor |
| Worker is a container-managed bean | Bean goes through post-processing/proxying steps | Object created with `new` is not automatically proxied by Spring |
| Method can be intercepted | E.g., `public` non-`final` instance method with a matching proxy type | `private`/`final`/`static` methods cannot be intercepted by proxy as expected |
| Caller uses a Spring-injected reference | Call goes through the proxy | `this.method()` or `new Worker().method()` bypasses the proxy |
| Executor has the right name/type and capacity | Dispatcher has resources to submit tasks | May be rejected or run under a different policy |

A method returning `CompletableFuture` **does not prove** it is running asynchronously: even a synchronous Java call can return `CompletableFuture.completedFuture(value)`. You must observe the call boundary and the executor.

## 3. Before–After Design: Separating Coordinator and Worker

### 3.1. Before: One Service Doing Both Orchestration and Background Work

~~~java
@Service
public class ReportService {

    public void requestReport(long reportId) {
        markRequested(reportId);
        generateAsync(reportId); // internal call
    }

    @Async("reportExecutor")
    public CompletableFuture<String> generateAsync(long id) {
        return CompletableFuture.completedFuture(renderReport(id));
    }
}
~~~

The snippet above illustrates the anti-pattern; `markRequested`, `renderReport`, imports, and the executor still need to be defined. `generateAsync(reportId)` **does not** pass through the Spring proxy, so `renderReport` still runs on the caller thread. If `renderReport` blocks on I/O, the HTTP request or coordinating thread stays blocked waiting.

Even changing it to `this.generateAsync(reportId)` or adding `@Async` onto `requestReport` itself does not properly address boundaries, lifetimes, and business contracts. Marking the coordinator async might just move the whole workflow to another thread without creating a clean boundary between saving state and rendering the report.

### 3.2. After: Coordinator Only Orchestrates, Worker Executes Async

~~~java
@Service
public class ReportWorker {

    @Async("reportExecutor")
    public CompletableFuture<String> generateAsync(long reportId) {
        String output = renderReport(reportId);
        return CompletableFuture.completedFuture(output);
    }

    private String renderReport(long id) {
        return "report-" + id;
    }
}

@Service
public class ReportCoordinator {
    private final ReportWorker worker;

    public ReportCoordinator(ReportWorker worker) {
        this.worker = worker;
    }

    public CompletableFuture<String> requestReport(long id) {
        return worker.generateAsync(id); // goes through the injected bean
    }
}
~~~

These are illustrative classes in a Spring project with component scanning, imports, `@EnableAsync`, and a `reportExecutor` bean. **Splitting properly** is not about naming a class `Worker`, but about `ReportCoordinator` receiving a **Spring-managed reference** to `ReportWorker`. When `generateAsync` is called from the coordinator, the Spring proxy can dispatch the method to the executor.

Responsibility table:

| Component | Responsibility | Where Does It Typically Run? |
| --- | --- | --- |
| Controller / consumer | Receives requests, validates input, chooses response protocol | HTTP/request/message thread |
| `ReportCoordinator` | Orchestrates use case, generates job ID, checks authorization, stores request state | Caller thread (unless configured otherwise) |
| `ReportWorker` | Executes heavy I/O or CPU work per contract | Executor thread when called through `@Async` proxy |
| `TaskExecutor` | Provides workers, queue, concurrency limits, and overload handling | Execution infrastructure |
| Job store / outbox if needed | Persists work and status durably, supports restart/retry | External storage system outside process |

A two-bean structure generally enables independent testing, separate pool selection, and a clear spot where code hands off to background processing.

## 4. Proper Implementation Steps in a Spring Application

### Step 1 — Enable the @Async Mechanism in the ApplicationContext

~~~java
@Configuration
@EnableAsync
public class AsyncConfiguration {
    @Bean("reportExecutor")
    public ThreadPoolTaskExecutor reportExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(50);
        executor.setThreadNamePrefix("report-worker-");
        return executor;
    }
}
~~~

This is a **configuration fragment** (requires Spring imports). `@EnableAsync` activates asynchronous method execution in the corresponding context. `ThreadPoolTaskExecutor` is a Spring-managed bean; Spring initializes and shuts it down according to the appropriate lifecycle.

Do not create `new ThreadPoolTaskExecutor()` per request: besides making resource management difficult, you would have to initialize/shut it down manually, and `@Async` methods will not automatically pick that new executor merely because it exists.

### Step 2 — Worker Is a Spring Bean

The worker can be created via `@Service`/`@Component` and component scanning, or via a `@Bean` factory method:

~~~java
@Bean
public ReportWorker reportWorker() {
    return new ReportWorker();
}
~~~

Having the `new` keyword **inside a `@Bean` factory method is not an error**: the returned object will be registered and post-processed by the container. The error is a caller keeping a different object instantiated outside the container, such as `new ReportWorker().generateAsync(...)`.

### Step 3 — Inject the Worker via Constructor, Do Not Instantiate Manually

~~~java
public ReportCoordinator(ReportWorker worker) {
    this.worker = worker;
}
~~~

With constructor injection, the dependency is resolved from the Spring context. In proxy mode, Spring can inject the corresponding proxy rather than the raw target directly. This keeps the AOP boundary much more transparent than fetching beans manually from `ApplicationContext` inside business code.

### Step 4 — Call the Public @Async Method via the Collaborating Reference

~~~java
return worker.generateAsync(reportId);
~~~

The method should be invoked from **another** bean, not `this.generateAsync(...)`. Use `@Async("reportExecutor")` to explicitly specify the pool when multiple executors exist. Do not assume declaring a bean named `reportExecutor` makes every `@Async` pick it automatically without appropriate qualifiers/resolution rules.

### Step 5 — Decide Return Contract and Error Handling

For business flows needing a result, use an appropriate `CompletableFuture<T>`/`Future<T>`. For fire-and-forget `void`, the caller has no `Future` to observe errors; an `AsyncUncaughtExceptionHandler`, logging, and proper monitoring are required. `@Async` does not provide a durable queue or an exactly-once guarantee.

Do not call `future.join()` or `future.get()` immediately after dispatch if the goal is freeing the calling thread. When waiting for a result is truly required, blocking is valid, provided timeouts/cancellation and appropriate UX are handled.

## 5. Complete Runnable Example Using Java 17 and Spring Framework

This demo shows **the same Spring context** containing both the self-invocation anti-pattern and the proper bean-extraction pattern. Instead of relying on `Thread.sleep()` or random scheduling order to draw conclusions, we inspect thread names and proxy status after each `Future` completes.

Uses **JDK 17+, Gradle 8.5+, and Spring Framework 6.1.14**. The demo is a command-line application requiring no Spring Boot or HTTP server.

### 5.1. Project Structure

~~~text
async-collaborator-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/AsyncCollaboratorDemo.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'async-collaborator-demo'
~~~

**build.gradle**

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
    mainClass = 'demo.AsyncCollaboratorDemo'
}
~~~

**src/main/java/demo/AsyncCollaboratorDemo.java**

~~~java
package demo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public final class AsyncCollaboratorDemo {

    public static void main(String[] args) throws Exception {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            String callerThread = Thread.currentThread().getName();

            ReportWorker worker = context.getBean(ReportWorker.class);
            ReportCoordinator coordinator =
                    context.getBean(ReportCoordinator.class);
            LegacyReportService legacy =
                    context.getBean(LegacyReportService.class);

            System.out.println("worker is Spring proxy: " +
                    AopUtils.isAopProxy(worker));

            // Anti-pattern: managed bean calling its own @Async method.
            String selfName = legacy.startBySelfCall()
                    .get(5, TimeUnit.SECONDS);
            System.out.println("self-call runs on caller: " +
                    selfName.equals(callerThread));

            // Proper way: coordinator calls method on injected worker.
            WorkResult result = coordinator.start("R-42")
                    .get(5, TimeUnit.SECONDS);
            System.out.println("collaborator uses executor: " +
                    result.threadName().startsWith("report-worker-"));
            System.out.println("report ID preserved: " +
                    result.reportId().equals("R-42"));

            // Manually instantiated object is not registered/proxied by Spring.
            String manualThread = new ReportWorker()
                    .generateAsync("R-43")
                    .get(5, TimeUnit.SECONDS).threadName();
            System.out.println("manual new runs on caller: " +
                    manualThread.equals(callerThread));
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class Config {

        @Bean("reportExecutor")
        public ThreadPoolTaskExecutor reportExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(8);
            executor.setThreadNamePrefix("report-worker-");
            return executor;
        }

        @Bean
        public LegacyReportService legacyReportService() {
            return new LegacyReportService();
        }

        @Bean
        public ReportWorker reportWorker() {
            return new ReportWorker();
        }

        @Bean
        public ReportCoordinator reportCoordinator(ReportWorker worker) {
            return new ReportCoordinator(worker);
        }
    }

    public record WorkResult(String reportId, String threadName) { }

    public static class LegacyReportService {

        public CompletableFuture<String> startBySelfCall() {
            return this.buildAsync();
        }

        @Async("reportExecutor")
        public CompletableFuture<String> buildAsync() {
            return CompletableFuture.completedFuture(
                    Thread.currentThread().getName());
        }
    }

    public static class ReportWorker {

        @Async("reportExecutor")
        public CompletableFuture<WorkResult> generateAsync(
                String reportId) {

            WorkResult result = new WorkResult(
                    reportId, Thread.currentThread().getName());
            return CompletableFuture.completedFuture(result);
        }
    }

    public static class ReportCoordinator {
        private final ReportWorker worker;

        public ReportCoordinator(ReportWorker worker) {
            this.worker = worker;
        }

        public CompletableFuture<WorkResult> start(String reportId) {
            return worker.generateAsync(reportId);
        }
    }
}
~~~

### 5.2. Running the Program

In the project root directory, with Java 17+ and Gradle installed:

~~~bash
gradle run
~~~

If the project includes the Gradle Wrapper, use `./gradlew run` (Linux/macOS) or `gradlew.bat run` (Windows).

With the executor operating normally and tasks completing within `get(5, TimeUnit.SECONDS)`, **the exact stdout printed by the program itself is**:

~~~text
worker is Spring proxy: true
self-call runs on caller: true
collaborator uses executor: true
report ID preserved: true
manual new runs on caller: true
~~~

Gradle/Spring may emit additional startup logs or build messages beyond those five lines. The actual thread name may be `report-worker-1`, yet the example checks the **prefix** so it does not depend on worker numbering or worker count.

### 5.3. Why Is the Output Correct?

1. `@EnableAsync` is processed in the same `AnnotationConfigApplicationContext` containing the beans.
2. `ReportWorker` is created via `@Bean` and passes through Spring bean post-processing; `AopUtils.isAopProxy(worker)` returns `true` in this default configuration (the class declares no interface and the method is eligible for proxying).
3. `LegacyReportService` is also a managed bean, yet `startBySelfCall()` invokes `this.buildAsync()` **inside the target**. The `@Async`-annotated method is not intercepted by the proxy; the thread name equals the caller's.
4. `ReportCoordinator` receives `ReportWorker` via a `@Bean` parameter. Spring injects the post-processed reference; `worker.generateAsync(...)` **passes through the proxy**, and then `TaskExecutor` runs the code on a worker prefixed with `report-worker-`.
5. `new ReportWorker()` creates an object outside the context; the call returns an already completed `CompletableFuture` yet **still executes synchronously** on the caller.
6. The context is closed via `try-with-resources` after the futures complete, preventing the thread pool from outliving the demo.

This is a **complete program**; the standalone snippets in earlier sections must be placed inside a Spring project with appropriate imports and configuration.

## 6. Designing the Two Beans' APIs Without Hiding Errors

### 6.1. Keeping the Asynchronous Boundary in the Worker API

A practical approach is having the worker return `CompletableFuture<ReportResult>` and having the coordinator return that future or transform it:

~~~java
public CompletableFuture<ReportResult> requestReport(ReportRequest request) {
    validate(request);
    return worker.generateAsync(request)
            .thenApply(this::toResponseModel);
}
~~~

This is an **illustrative code snippet**: `ReportResult`, `ReportRequest`, `validate`, and `toResponseModel` are not defined here. In `CompletableFuture`, `thenApply` without the `Async` suffix may run on the thread completing the preceding stage or on the caller thread if the stage is already complete. If the transformation is heavy, consider `thenApplyAsync(..., chosenExecutor)` with an explicitly chosen executor.

If the coordinator only needs to acknowledge that the request was accepted without waiting for the result, design a separate **job ID and job status** instead of returning a vague promise that the job will definitely complete.

### 6.2. Errors in an Async Worker Differ from Synchronous Errors

With `@Async` returning `CompletableFuture<T>`, execution errors should be observed through the future:

~~~java
CompletableFuture<ReportResult> future = worker.generateAsync(request);

return future.whenComplete((value, error) -> {
    if (error != null) {
        // Record failure and update job status appropriately.
    }
});
~~~

This snippet is illustrative. Do not treat calling `whenComplete` as handling or recovering from the error: unless a callback transforms the outcome, the future still completes exceptionally. You can use `handle`, `exceptionally`, or bounded retries when the business contract permits.

With `@Async void`, the caller has no `Future` to wait on. Errors are not automatically thrown back onto the caller thread, which has already returned; you need `AsyncUncaughtExceptionHandler`, logging, and error monitoring.

`@Async` uses an in-memory executor and can hit **task rejection** when the pool is overloaded or shut down. Do not treat a normal return as a durability guarantee if you chose a rejection handler that silently drops work. For mandatory work, prefer explicit rejection responses or a durable queue/outbox.

## 7. Transactions: Why Extracting a Bean Also Clarifies Boundaries

In an application using `@Transactional`, a common misconception is:

~~~java
@Transactional
public void placeOrder(Order order) {
    repository.save(order);
    emailWorker.sendAsync(order.id());
}
~~~

This is an illustrative snippet (requiring declarations for `Order`, repository, and worker). If calling `sendAsync` through the proxy triggers a worker on another thread, **the transaction bound to the caller's thread does not automatically follow the worker**. The worker may run **before the caller's transaction commits**. If the worker reads the database, it may fail to see the newly written record or observe unexpected state.

Extracting the worker forces the architecture to answer:

- Which parameters/DTO does the worker need, and does it need to re-read committed data from the DB?
- When is the email or event allowed to fire — immediately upon submission or only after commit?
- If the caller's transaction rolls back, how must the dispatched background work be handled?
- If the worker fails, who retries/updates status? Is idempotency required?

If the background action must happen only **after commit**, you can use `@TransactionalEventListener(phase = AFTER_COMMIT)` where appropriate, or a **transactional outbox** when durability across crashes/restarts is required. Do not simply put `@Async` or `@Transactional` on the same method and expect the work to wait for the caller's transaction automatically.

Inside the worker, if a separate transaction is needed, configure the transaction boundary on the executing method using an appropriate Spring mechanism and pay attention to how multiple proxies interact. A transaction in the worker is not an automatic continuation of the caller's transaction.

## 8. Data, Context, and Thread Safety

Extracting a bean solves **proxy interception**, not all concurrency problems automatically.

**Do not casually pass shared mutable objects.** If a controller receives a request and passes the same mutable object into `@Async`, the worker may read values modified mid-flight. Prefer immutable DTOs/records or data snapshots at the dispatch point; non-immutable data needs a clear ownership policy.

**Do not store per-request state in singleton worker fields.** A `@Service` is a singleton by default. Multiple thread pools can invoke the same worker instance concurrently. For example, `private String currentOrderId` on a singleton risks races and mixing data across tasks. Keep IDs in method parameters, local variables, or appropriately scoped storage.

**ThreadLocals do not automatically carry over to executor threads.** MDC/tracing, `SecurityContext`, request attributes, and transaction contexts usually require explicit propagation or data passing. Spring Security provides appropriate wrappers, while a `TaskDecorator` can decorate a `Runnable` to capture/restore context. Clean up afterward so context does not leak when the pool reuses threads.

**Cancellation is cooperative.** `Future.cancel(true)` can send an interrupt when configuration/implementation supports it, yet it cannot force all external I/O to stop immediately. Design timeouts and job states at the business layer.

**Thread scheduling does not guarantee ordering.** If the coordinator submits task A and then task B to a multi-worker pool, B may finish before A. If ordering/idempotency is required, design for it independently.

## 9. Cases Where Extracting a Bean Is Still Not Enough

| Case | Cause | Fix |
| --- | --- | --- |
| Split into two classes, yet used `new ReportWorker()` | Worker does not go through container/proxy | Register bean and inject from Spring |
| Worker bean has `@Service`, yet sits outside scan path | Bean is not registered | Check `@ComponentScan`, app config, and profiles |
| `@Async` is present, yet `@EnableAsync` is missing | Infrastructure not enabled | Enable async in the `ApplicationContext` holding the worker |
| Coordinator calls an `@Async` method on itself | Self-invocation | Move the method to another collaborating bean |
| Calling a `private`/`final`/`static` method through a proxy | Not eligible for interception | Public, non-final instance method on a suitable bean |
| Bean has an interface, yet concrete class is injected with JDK proxy | Proxy may only implement the interface | Inject via interface or configure class proxies appropriately |
| Using `@Async` on a `@Configuration` method | Not supported like a service method | Keep `@Configuration` for bean declarations and logic in services |
| Calling worker from the worker's own `@PostConstruct` | Lifecycle/self-call does not go through proxy | Orchestrate from another bean after startup |
| Beans are split, yet caller immediately invokes `future.get()` | Caller still blocks waiting for result | Return future or separate job lifecycle |
| Worker runs, yet lacks caller's transaction context | ThreadLocal/transaction is not inherited automatically | Define transaction boundary inside worker or after commit |
| Worker uses mutable shared fields on a singleton | `@Async` does not provide synchronization | Make stateless/immutable or use proper locking/atomic operations |
| Task must survive restarts, yet uses only an in-memory executor | Tasks are not durable | Job store/outbox/message broker |

### 9.1. Why Should Self-Injection Not Be the Default?

A commonly mentioned workaround is injecting the bean into a field of itself and calling `selfProxy.asyncMethod()` to pass through the proxy. This approach can require circular-dependency handling/lazy injection, making code harder to read and test. It hides business intent behind an AOP trick instead of expressing a real dependency.

Likewise, `AopContext.currentProxy()` depends on `exposeProxy` configuration and couples business logic to Spring AOP infrastructure. When async work is genuinely a distinct responsibility, **extracting a collaborating bean is usually clearer and less restrictive**.

### 9.2. Are There Alternatives Without a Second Bean?

Yes. For instance, submitting a `Runnable`/`Callable` directly to a `TaskExecutor`, or using `CompletableFuture.supplyAsync(..., executor)` with an injected executor. These approaches **do not depend on `@Async` interception**, though the caller must manage submission, error handling, and result coordination itself.

You can use `@EnableAsync(mode = AdviceMode.ASPECTJ)` with properly configured weaving to intercept self-invocation as well. However, that is a different deployment mode requiring separate dependencies/configuration; it is not the default choice for an application that only needs to separate coordinator and worker.

Do not split into countless tiny classes merely to avoid a single `this`: the architecture should reflect meaningful responsibility boundaries. For small services, choosing direct executor submission where appropriate is also a valid design.

## 10. Properly Testing the Proxy Boundary

A unit test calling `new ReportWorker()` **cannot verify** that `@Async` works. It only tests the Java method body. To test interception, the test needs an **`ApplicationContext`** with `@EnableAsync`, an executor, and real beans.

Suggested test scenario:

1. Obtain the worker from the context, using `AopUtils.isAopProxy` as a supporting signal.
2. Call the `@Async` method from **another bean**, receive the `Future`, and wait for the result with a timeout.
3. Verify the worker observes a thread name with the configured prefix; do not depend on a specific thread sequence number.
4. Verify `this.method()` in the anti-pattern version still runs on the caller to prove the test has discriminative power.
5. Test exceptions and rejections; a timeout must never be treated as a passing result.
6. Test data passed to the worker and idempotency under retries.

**Avoid speed-only tests** like "if the method returns in under 100ms, it is async." Scheduling variations can make such tests flaky. Checking the actual executor/proxy and concrete results is much more reliable.

In production, add metrics for active threads, queue depth, rejected tasks, task wait time, and execution time. Dedicated pool names (`report-worker-`) help when reading logs/thread dumps, though they do not replace trace IDs or correlation IDs.

## 11. Checklist When Refactoring a Self-Calling @Async Method

- [ ] Identify precisely which method calls `this.asyncMethod()` and currently expects async execution.
- [ ] Extract only meaningful background work into a separate `@Service`/`@Component` or `@Bean` bean.
- [ ] Enable `@EnableAsync` in the context containing the worker.
- [ ] Inject the worker into the coordinator via constructor; **do not manually `new`** the worker inside the coordinator.
- [ ] Place `@Async("executorName")` on a `public` non-`final` method of the worker when using proxy mode.
- [ ] Provide an executor with the right name, capacity, and rejection policy; avoid unbounded queues.
- [ ] Design the return type (`void`/`Future`/`CompletableFuture`) and how callers observe errors.
- [ ] Do not call `get()`/`join()` right after dispatch when a non-blocking caller is needed.
- [ ] Evaluate transactions and commit timing; use after-commit/outbox if needed.
- [ ] Pass immutable request data or DTOs; do not write request state into singleton fields.
- [ ] Verify with an integration test using a Spring context, proxy, and proper worker thread.
- [ ] Include logging/metrics and shutdown, timeout, retry, and idempotency strategies as business needs dictate.

## 12. Self-Check Questions

1. **Why does `this.generateAsync()` not run in the background even though the bean has `@Service`?** In proxy mode, self-invocation calls the target directly, bypassing the async interceptor.
2. **Does moving the method into a new class and calling `new` on that class fix it?** No; the worker must be managed by Spring and called through the proxy.
3. **Does a `@Bean` method returning `new ReportWorker()` leave the worker unmanaged?** No. The returned object is registered as a bean and goes through appropriate bean post-processing.
4. **What are the different roles of coordinator and worker?** The coordinator receives/orchestrates the use case; the worker executes tasks meant to run on an executor.
5. **Why does `CompletableFuture.completedFuture(...)` not prove async execution?** It can also be created and completed immediately on the caller thread.
6. **What happens if a controller calls the worker and immediately calls `future.get()`?** The caller still blocks waiting; the goal of reducing request-thread hold time is not achieved.
7. **Does splitting beans automatically carry the caller's transaction to the worker?** No; transactions are typically thread-bound, requiring separate boundaries and post-commit policies.
8. **Why should shared mutable fields be avoided in a singleton worker?** Multiple worker threads can access them concurrently and cause race conditions.
9. **Are there ways to avoid splitting beans?** Yes: submitting work directly to an executor or using proper AspectJ weaving, though contracts and complexity differ.
10. **How do you reliably test that `@Async` works?** Invoke via a Spring-managed collaborator in an async-enabled context and verify the execution thread/result with a timeout.
11. **What if a proxied worker bean calls an `@Async` method from its own constructor/`@PostConstruct`?** Do not expect proxy interception for internal calls during lifecycle initialization; orchestrate post-initialization via another bean.
12. **If a job must survive restarts, are splitting beans and adding `@Async` enough?** No. Durable job storage such as an outbox or job store, plus retries and idempotency, are required.

**Conclusion:** Extracting asynchronous methods into a **Spring-managed and injected collaborating bean** turns **self-invocation** into **cross-bean proxy invocation**. This is the clean way for `@Async` to take effect in proxy mode; thread safety, transactions, job durability, error handling, and overload control still require dedicated design.

### Official References

- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — @Async](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/annotation/Async.html)
- [Spring Framework — @EnableAsync](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html)
- [Spring Framework — Proxying Mechanisms and Self-Invocation](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework — Bean Definitions](https://docs.spring.io/spring-framework/reference/core/beans/definition.html)
