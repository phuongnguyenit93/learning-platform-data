# Role of the Executor Across Other Spring Components

## 1. One TaskExecutor, Many Integration Points

In Spring Framework, **TaskExecutor** is the interface used to **hand off a unit of work to an execution mechanism**. It extends java.util.concurrent.Executor and provides the **execute(Runnable)** method. This same interface can be used across multiple layers: asynchronous methods, HTTP request processing, internal application events, message channels, or Spring Batch jobs.

The role of TaskExecutor across components **is not entirely identical**. Each integrating component decides **when** and **why** to submit a task, while the executor decides **execution resources, queuing, thread allocation, and overload behavior** according to its configuration.

~~~text
Work Origin                               TaskExecutor Handoff
───────────                               ────────────────────
@Async call via Spring proxy      ──────> executes method body
Spring MVC controller -> Callable ──────> runs Callable, returns result via async dispatch
@EventListener / multicaster      ──────> invokes listener on worker thread
Spring Batch                      ──────> executes Step/Flow/partition work
Spring Integration ExecutorChannel──────> dispatches message to handler on worker
Business code calling execute(...)──────> runs Runnable directly

@Scheduled / TaskScheduler        ──────> decides when to trigger
                                          (may hand off further work to TaskExecutor)
~~~

This model separates three responsibilities: **the work producer**, **the task executor**, and **the result/error observer**. Simply increasing thread counts without understanding who submits tasks and what happens upon rejection can cause latency, memory pressure, or lost work.

## 2. API Foundation and Implementation Choices

### TaskExecutor and AsyncTaskExecutor

- **TaskExecutor**: core API accepting a Runnable via execute(Runnable), compatible with JDK Executor. The interface itself does not promise execution on another thread. For example, **SyncTaskExecutor** invokes the work directly on the calling thread.
- **AsyncTaskExecutor**: extends TaskExecutor with conveniences for submitting tasks and receiving a Future (exact APIs depend on Spring version). **Spring MVC Callable** integration requires an executor compatible with AsyncTaskExecutor.
- **ThreadPoolTaskExecutor**: common implementation managing a pool, queue, core/max bounds, and Spring lifecycle; usable across many integration points expecting TaskExecutor/AsyncTaskExecutor.
- **SimpleAsyncTaskExecutor**: runs tasks on a new thread rather than reusing pooled threads; can use virtual threads on supported JDKs when configured appropriately.
- **ConcurrentTaskExecutor**: adapter for another java.util.concurrent.Executor, useful when the system already owns a managed executor.

Example direct call inside a Spring bean injected with TaskExecutor:

~~~java
public void submit(TaskExecutor executor) {
    executor.execute(() ->
            System.out.println("Running on " +
                    Thread.currentThread().getName()));
}
~~~

This code snippet is a **method illustration**, not a standalone program. When the executor is an asynchronous pool, the submit method usually returns before the Runnable completes. If the executor rejects the task due to shutdown or exhausted capacity, the caller must handle **TaskRejectedException/RejectedExecutionException** appropriately; never assume tasks are guaranteed to be accepted.

**Separation to keep in mind:** the TaskExecutor API does not automatically define execution ordering, job durability, retries, transactions, security context propagation, or scheduling triggers. Those guarantees must come from the design of the consuming component and related configuration.

## 3. Mapping TaskExecutor Across Spring Components

| Component | When does it submit work? | Role of the executor | Things to control |
| --- | --- | --- | --- |
| **@Async** | Another bean invokes a method via the async proxy | Executes method body on a worker | Proxy/self-invocation, Future, exceptions, queue |
| **Spring MVC Callable/WebAsyncTask** | Controller returns a Callable | Runs blocking work on an AsyncTaskExecutor | Timeouts, async dispatch, pool, request context |
| **DeferredResult / CompletableFuture in MVC** | Result is completed by application code | Executor participates only if the app explicitly uses it; MVC does not auto-submit every DeferredResult | Who runs work, who completes it, timeouts/errors |
| **Application events** | ApplicationEventPublisher publishes an event | @Async on listener or event multicaster's TaskExecutor | Ordering, exceptions, transaction/context |
| **Spring Batch** | Step/Flow/partition needs parallel execution | Supplies workers for the chosen parallelism strategy | Reader/writer thread safety, transactions, restarts |
| **Spring Integration** | Message enters an ExecutorChannel | Shifts message dispatching onto a worker | Transaction boundaries, ordering, errors/rejection |
| **Spring WebSocket/message broker** | Messages arrive at inbound/outbound channels | Certain channels use an executor for dispatching | Queue size, ordering, backpressure |
| **TaskScheduler / @Scheduled** | Trigger time is reached | Primary role belongs to the scheduler; does not automatically use the @Async pool | Long tasks, overlap, scheduler threads |
| **Spring WebFlux** | Reactive stream subscribed/switched via Scheduler | Reactor Scheduler is a different abstraction; an executor can be adapted where appropriate | Never block the event loop; isolate blocking work |

Not all of these components automatically select **the exact same bean** named taskExecutor. Resolution rules depend on the framework/module, version, and configuration. You can share one pool for similar workloads; for HTTP, batch, and heavy background tasks with differing priorities, consider separating pools so they do not starve each other.

## 4. @Async: TaskExecutor Behind a Method Call

**@Async** is Spring's most convenient mechanism for dispatching work to an executor without requiring the caller to construct a Runnable manually. When enabled via **@EnableAsync**, valid method calls pass through a Spring proxy; the proxy delegates execution to the executor. You can specify a pool via qualifier:

~~~java
@Async("reportExecutor")
public CompletableFuture<String> buildReport(long reportId) {
    return CompletableFuture.completedFuture("report-" + reportId);
}
~~~

When the method above is invoked **from another bean via the proxy**, the caller receives a Future to await, check errors, or compose pipelines if needed. If the method only returns void, execution errors are not propagated synchronously back to the caller; logging or an **AsyncUncaughtExceptionHandler** is needed. With Future/CompletableFuture, handle completion and errors at the appropriate boundary.

Important points:

1. **@EnableAsync** must be active in the ApplicationContext; the annotation alone does not create an async proxy.
2. **Self-invocation** (this.buildReport(...)) normally bypasses the proxy in default proxy mode; the method runs like a regular Java call.
3. **@Async("reportExecutor")** explicitly selects the intended bean; avoid relying on automatic selection rules when multiple executors exist.
4. **@Async does not automatically ensure thread safety.** Multiple workers may concurrently call a singleton containing mutable fields.
5. **Avoid calling Future.get()/join() right after the call** if the goal is not blocking the caller; waiting is sometimes right, but must be a deliberate decision.
6. Async tasks normally **do not inherit the caller's transaction or ThreadLocal** automatically.

Calling executor.execute(...) directly fits when you only need a Runnable. Using @Async fits when you want to express async boundaries at the service-method level and leverage proxies, qualifiers, and Future return types. Avoid overusing @Async for very short CPU logic where dispatch overhead and thread switching outweigh the benefit.

## 5. Spring MVC: Freeing Request Threads While Waiting for Work

Spring MVC handles requests on the Servlet stack. A synchronous controller holds the request thread until processing finishes. With **Callable<T>**, MVC uses Servlet asynchronous processing:

1. Controller receives the request and returns a Callable.
2. MVC starts an async request and submits the Callable to the **AsyncTaskExecutor** configured for MVC.
3. The original Servlet request thread is released while the response stays open.
4. Worker runs the Callable and produces a result or exception.
5. Container performs an async dispatch so MVC processes the result and completes the response.

Controller example, **requiring spring-webmvc and a web runtime, so it is not part of the standalone program in Section 10**:

~~~java
@RestController
class ReportController {
    @GetMapping("/reports/current")
    public Callable<String> current() {
        return () -> {
            // Blocking backend access can run on the MVC async worker.
            return "ready: " + Thread.currentThread().getName();
        };
    }
}
~~~

MVC lets you configure AsyncTaskExecutor via **WebMvcConfigurer.configureAsyncSupport(AsyncSupportConfigurer)**, or use Spring Boot's auto-configuration. When customizing Spring Boot 3.3, a key detail is that the **applicationTaskExecutor** bean needs to be AsyncTaskExecutor-compatible for MVC's default selection mechanism to pick it up. An arbitrary custom Executor merely named taskExecutor might be picked by @Async yet **is not guaranteed to be selected by MVC**.

**Callable differs from DeferredResult.** With DeferredResult, the controller returns an uncompleted holder; the application itself, an I/O callback, or another message handler must call setResult/setErrorResult. MVC **does not automatically dispatch the computation of every DeferredResult to an executor**. With controllers returning CompletableFuture, whatever produces the future decides where the work runs. Thus, a controller "returning an async type" does not itself prove a particular TaskExecutor was used.

MVC asynchrony does not mean the application can handle infinite requests. Configure timeouts, monitor open requests, avoid unbounded pools, and manage downstream connections. Moving blocking I/O onto workers frees waiting Servlet threads, yet **does not turn blocking I/O into non-blocking I/O**.

## 6. Application Events: Listeners Run Synchronously or Offloaded to an Executor

With **ApplicationEventPublisher.publishEvent(...)**, Spring normally delivers events to listeners **synchronously on the publisher's thread** by default. Spring offers two primary ways to hand work to an executor.

### Approach A — Only One Listener Needs Async Execution

~~~java
@Component
class NotificationListener {
    @Async("notificationExecutor")
    @EventListener
    public void onOrderCreated(OrderCreated event) {
        // Runs on notificationExecutor.
    }
}
~~~

This is illustrative code, assuming **OrderCreated**, the notificationExecutor bean, @EnableAsync, and necessary imports are defined. If the application only needs asynchrony on this listener, the annotation expresses intent clearly. **publishEvent() does not wait for actual processing to finish** once the listener has been dispatched.

### Approach B — Configuring the Multicaster to Dispatch Listeners via TaskExecutor

A bean named **applicationEventMulticaster** can use SimpleApplicationEventMulticaster and call setTaskExecutor(...) to offload dispatching to an appropriate pool. Example inside a @Configuration class (requiring imports for the types used):

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

This is a separate illustrative configuration, **not included in the standalone demo**. With this approach, event dispatch can become asynchronous for listeners **that support async execution**. Do not infer every listener moves off-thread: for example, transactional listeners have constraints requiring synchronous alignment with the transaction. Do not stack both @Async and an async multicaster if doing so creates extra, hard-to-reason-about dispatch hops.

**Transaction boundary:** a listener running on another worker does not inherit an active transaction or the publisher's ThreadLocals. If you want post-commit handling, consider **@TransactionalEventListener(phase = AFTER_COMMIT)**, and then separately design background work boundaries and durability as needed. ApplicationContext events are an in-process mechanism, **not a durable message broker**; a process crash after replying to the publisher can lose tasks sitting only in memory.

**Error handling:** exceptions from async listeners are not automatically rethrown back to the publisher. Use logging, error handlers, bounded retries, or durable job storage if the event carries mandatory business obligations.

## 7. Spring Batch: Providing Workers for Parallel Processing

Spring Batch uses TaskExecutor as an **infrastructure component** when configuring a parallelism strategy. Common patterns:

- **Multi-threaded Step:** configure taskExecutor on a Step to execute processing concurrently where supported by the Spring Batch version. Readers/processors/writers and shared state must be evaluated for thread safety; exact chunk/transaction semantics depend on version.
- **Parallel Steps:** separate flows can run concurrently when configuring split flows with an executor.
- **Partitioning:** splits a workload into multiple StepExecutions; a local partition handler can use a TaskExecutor to run partitions. Choosing grid size, resources, and idempotency remains the application's responsibility.

Example **Spring Batch 5.x configuration sketch**, requiring spring-batch-core, JobRepository, transaction manager, and ItemReader/Processor/Writer, so not a standalone Java file:

~~~java
Step step = new StepBuilder("importStep", jobRepository)
        .<InputRow, OutputRow>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .taskExecutor(batchExecutor)
        .build();
~~~

**ThreadPoolTaskExecutor does not automatically make readers/writers safe for concurrent access.** When a framework/version runs components across multiple threads, verify compatibility, output ordering, commit boundaries, restart/retry behavior, and duplicate handling. In Batch, raising concurrency can bottleneck on the DataSource connection pool, I/O throughput, or database locks.

Distinguish an **in-JVM TaskExecutor** from distributing work across multiple processes/workers: remote distribution requires messaging, partitioning, or remote execution mechanisms. A plain ThreadPoolTaskExecutor does not create a distributed job queue.

## 8. Spring Integration and Messaging Systems

Spring Integration provides **ExecutorChannel** to dispatch messages to subscribers/handlers using a TaskExecutor. Example using spring-integration-core, an illustrative snippet requiring MessageChannel declarations and dependencies:

~~~java
@Bean
MessageChannel processingChannel(
        @Qualifier("integrationExecutor") TaskExecutor executor) {
    return new ExecutorChannel(executor);
}
~~~

When a message is sent to the channel, handler invocation normally shifts to a worker. Compared to **DirectChannel**, ExecutorChannel **breaks the sender's thread boundary**, so you cannot assume the handler shares a transaction or ThreadLocal with the sender. Send operations can normally return before the handler runs; however, if the executor uses **CallerRunsPolicy** or a special backpressure policy, the sender **may block or execute the task itself**, so never treat "async channel" as an absolute guarantee.

When multiple messages process concurrently, **completion order** can differ from send order. If per-key ordering, idempotency, or retries are required, select the corresponding messaging pattern and mechanism.

Components such as Spring WebSocket message channels, JMS listener containers, or AMQP listener containers may use executors for thread management or dispatching depending on implementation. Yet many listener containers also have **their own concurrency settings** and independent lifecycles; **do not assume that merely defining a TaskExecutor bean in the context makes all listeners switch to that pool**.

For systems that must preserve messages across application restarts, scale across multiple nodes, or guarantee delivery, an in-process executor **does not replace** a durable queue/broker (Kafka, RabbitMQ, JMS broker, etc.).

## 9. Relationship With TaskScheduler, @Scheduled, and Reactor Scheduler

**TaskScheduler** addresses **when to trigger**, whereas TaskExecutor addresses **how submitted work is executed**. Although some Spring classes implement multiple interfaces and can use thread pools in both roles, the two abstractions remain distinct.

~~~text
@Scheduled every 30 seconds
       |
       v
TaskScheduler triggers short method
       |
       v
method calls @Async on another Spring bean
       |
       v
TaskExecutor accepts heavy work with its own queue/capacity
~~~

A @Scheduled method runs directly on a scheduler thread if it does not offload work elsewhere. If the method merely submits async work and returns, **fixedDelay** measures from when the scheduler-invoked method returns, **not from when the async task finishes**. Thus, multiple background jobs can overlap even though the schedule appears sequential. Add overlap/deduplication rules if business logic demands it.

**Reactor Scheduler in WebFlux** is also not a TaskExecutor. Reactor uses Scheduler to determine the execution context of reactive signals/operators. You can adapt an appropriate executor into a reactive chain in specific cases, yet adding @Async to a service should not be treated as a general cure for blocking code inside reactive pipelines. Move blocking work off the event loop, use a proper scheduler, and bound concurrency.

## 10. Standalone Demo: One Executor Serving execute(), @Async, and @EventListener

This demo uses **Java 17+, Spring Framework 6.1.14, and Gradle 8.5+**. It demonstrates in a command-line application that three different entry points can submit work to **the same ThreadPoolTaskExecutor**. No Spring Boot, web server, Spring Batch, or Spring Integration is needed to run it.

Structure:

~~~text
executor-integrations-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/ExecutorIntegrationsDemo.java
~~~

File **settings.gradle**:

~~~groovy
rootProject.name = 'executor-integrations-demo'
~~~

File **build.gradle**:

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

File **src/main/java/demo/ExecutorIntegrationsDemo.java**:

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

            // Path 1: submit Runnable directly via TaskExecutor.
            var directDone = new CountDownLatch(1);
            executor.execute(directDone::countDown);
            System.out.println("execute completed: " +
                    directDone.await(5, TimeUnit.SECONDS));

            // Path 2: @Async through a Spring proxy of another bean.
            var service = context.getBean(ReportService.class);
            var report = service.createReport(7)
                    .get(5, TimeUnit.SECONDS);
            System.out.println("async result: " + report.name());
            System.out.println("async pool: " +
                    report.threadName().startsWith("worker-"));

            // Path 3: ApplicationEventPublisher + @Async listener.
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

Run from the **executor-integrations-demo** directory with Gradle and an installed JDK:

~~~bash
gradle run
~~~

If the project has a wrapper, use **./gradlew run** (Linux/macOS) or **gradlew.bat run** (Windows). Under normal conditions, when all three tasks finish before the 5-second timeout, the program prints **exactly five lines**:

~~~text
execute completed: true
async result: report-7
async pool: true
event completed: true
event pool: true
~~~

Startup logs from Spring/Gradle may also appear; actual thread names carry varying suffixes (worker-1, worker-2, ...), so the example prints booleans checking the prefix rather than relying on a fixed thread name or order. If the environment is overloaded or times out, values/exceptions may differ; those are operational conditions to handle rather than proof that an executor always guarantees task completion.

Analysis:

1. **execute(...)** runs the Runnable directly on a worker managed by ThreadPoolTaskExecutor.
2. **@Async("workerExecutor")** dispatches ReportService.createReport() via the proxy to the same pool; the Future allows observing the result.
3. **@EventListener + @Async("workerExecutor")** shifts event handling onto the same pool while the default multicaster still delivers the call to the listener via Spring's publishing mechanism.
4. CountDownLatch lets the main thread wait to verify completion and establishes the necessary happens-before relationship for data updated by the worker. In production applications, add appropriate timeout/rejection/error handling.
5. The demo **does not** prove MVC, Spring Batch, or Spring Integration automatically use this bean. Those components require their own dependencies and configuration, as explained above.

## 11. Configuring and Splitting Executors in Spring Boot

In **Spring Boot 3.3**, when auto-configuration conditions match and no custom Executor changes selection, Boot typically creates an AsyncTaskExecutor for integrations—normally a **ThreadPoolTaskExecutor** unless virtual threads are enabled. Some integrations such as Spring MVC/WebFlux follow the **applicationTaskExecutor** bean name convention and require an **AsyncTaskExecutor** type. Selection rules for @EnableAsync and other components can vary when multiple beans of the same type exist.

**Rule of thumb:** when an application has multiple pools, specify the pool **explicitly** at each integration point. Do not assume the first bean with "executor" in its name will be picked by every component.

For an auto-configured ThreadPoolTaskExecutor/TaskScheduler, you can configure via application.yml:

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

This is a **Spring Boot configuration sample** and has no effect on the plain Spring Framework project in Section 10. These properties also **do not automatically override** settings on a ThreadPoolTaskExecutor you construct with `new` and configure manually; to share Boot's construction conventions, look into the builders Boot provides.

One way to define a custom pool (for example, inside a @Configuration class):

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

This configuration snippet is illustrative; it requires importing ThreadPoolTaskExecutor and @Bean and registering it in the ApplicationContext. This pool does not automatically replace the executor for MVC, Batch, Integration, or the event multicaster unless those components are explicitly configured to use it.

**Consider splitting pools by workload:** for instance, a small pool for application coordination, a bounded pool for heavy I/O, another executor for CPU processing, and a separate scheduler for schedules. Splitting into too many pools also wastes resources; base decisions on arrival rates, task durations, priority needs, and actual CPU/connection counts.

## 12. Cross-Integration Risks and Operations

### 12.1. Queues, Capacity, and Rejection

With ThreadPoolTaskExecutor, understand the interaction among **corePoolSize, maxPoolSize, queueCapacity**. In a bounded-queue model, the pool normally grows to core threads, then enqueues, and only grows beyond core when the queue is full. Thus a high maxPoolSize does not mean the application immediately creates that many threads.

When task arrival exceeds processing throughput, queues grow, latency climbs, and eventually the executor rejects work. Policies such as CallerRunsPolicy can force the caller to run the task, slowing the producer while changing the call's asynchronous nature. For HTTP requests, message channels, or event publication, define the exact rejection reaction: return an error code, perform bounded retries, apply backpressure, or persist work into a durable queue.

### 12.2. Context and Transactions

**ThreadLocals** normally do not transfer automatically to workers. For example, logging MDC, SecurityContext, and request attributes may be missing or wrong on the new thread. Spring provides **TaskDecorator** to wrap Runnables and propagate appropriate contexts; Spring Security also offers wrappers such as **DelegatingSecurityContextAsyncTaskExecutor**. Context propagation must capture, restore, and clean up at the right moments to prevent context leaks across tasks on reused pool threads.

A caller's **transaction** is usually bound to the current thread; handing work to an executor does not keep it inside the same transaction. Across Batch, Integration, Application Events, and MVC Callable, decide explicitly which transaction surrounds which unit of work. Never use synchronized as a substitute for database transactions, and never assume @Transactional on a caller covers async threads.

### 12.3. Thread Safety, Cancellation, and Shutdown

A singleton Spring service can be invoked concurrently by MVC, @Async, scheduled callbacks, and message handlers. **TaskExecutor does not automatically make singleton fields thread-safe**. Prefer stateless services; when shared mutable state is required, use immutable snapshots, atomic operations, concurrent collections, or proper locking.

On application shutdown, handle pending tasks, running tasks, interrupts, retries, and recoverable data. Cancelling a Future is a cooperative signal/mechanism, not a guarantee that all I/O stops immediately. The lifecycle of a Spring-managed pool depends on how the bean is created and its shutdown configuration; never instantiate raw pools inside methods and forget to close them.

### 12.4. Observability

Measure at least: **active threads, pool size, queue depth, submitted/completed/rejected tasks, queue wait time, processing duration, timeouts, and errors**. Measure each executor separately when multiple pools exist so you can distinguish bottlenecks in MVC, events, or batch jobs. High thread counts without higher throughput often point to I/O, connection pools, locks, or downstream limits rather than simply max-thread tuning.

## 13. Common Misconceptions

| Symptom | Wrong assumption | How to check and fix |
| --- | --- | --- |
| A TaskExecutor bean exists, yet MVC Callable does not run on the expected pool | Every component automatically picks this bean | Check AsyncTaskExecutor, applicationTaskExecutor, and WebMvcConfigurer |
| @Async does not spawn another thread | Simply adding the annotation runs in background | Check @EnableAsync and whether calls pass through the Spring proxy |
| Slow @Scheduled blocks multiple schedules | The @Async TaskExecutor always runs scheduled methods | Check TaskScheduler, scheduler thread count, and callback duration |
| Listener receives event, yet handler still runs on publisher thread | @EventListener is async by default | Need @Async on listener or appropriate multicaster configuration |
| Sending to ExecutorChannel loses the prior transaction | Messaging keeps the same thread boundary | Design transactions inside the handler/worker and handle errors independently |
| Batch duplicates/fails under parallel execution | Executor makes readers/writers safe automatically | Check idempotency, state, thread safety, restarts, and database |
| Increased maxPoolSize, yet latency keeps rising | Executor always spawns max threads immediately | Check core, queue, task duration, and saturation |
| Bean works single-threaded but breaks under high load | Singletons have built-in synchronization | Check shared mutable state, races, atomicity, and contention |

## 14. Self-Check Questions

1. Which executor does a service annotated with @Async run on? **According to async configuration, the qualifier on @Async, and bean selection rules for your version; specify @Async("beanName") when explicit control is needed.**
2. Does an MVC controller returning Callable automatically use the ThreadPoolTaskExecutor of an arbitrary @Async method? **Not guaranteed.** MVC uses an AsyncTaskExecutor per MVC/Boot's own configuration.
3. Does an MVC controller returning DeferredResult have its business work automatically submitted to a worker by MVC? **No**; the application is responsible for completing the DeferredResult.
4. Is an event listener async by default? **No**; listeners normally run synchronously by default. Use @Async or configure a multicaster.
5. Does increasing Spring Batch concurrency guarantee faster and more accurate processing? **No**; it still depends on thread safety, I/O, database, transactions, and restartability.
6. Does ExecutorChannel automatically preserve the sender's transaction into the handler? **No**, because the handler can run on another worker.
7. @Scheduled invokes an @Async worker taking 30 seconds and returns right away: does the next fixedDelay wait for the worker to finish? **No**; fixedDelay is tied to when the scheduler-triggered method finishes.
8. Is TaskExecutor a durable queue surviving restarts for critical work? **No**; a dedicated persistence and recovery mechanism is needed.

**Key takeaway:** TaskExecutor is a shared mechanism for **supplying execution resources**, while each Spring component defines when tasks are submitted, how results are awaited, and where error/transaction boundaries lie. Understanding those boundaries helps you pick the right pools, avoid confusing async with scheduling, and keep systems under control under load.

### Official Documentation

- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — Async Requests in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html)
- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Boot 3.3 — Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html)
- [Spring Batch — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html)
- [Spring Integration — Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html)
