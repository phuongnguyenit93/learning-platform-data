# Relating @Async and @Scheduled to Execution Resources in Spring Boot

In Spring Boot, the `@Async` and `@Scheduled` annotations cause methods to execute in ways other than simply "caller invokes directly and runs immediately on the caller's thread". However, they **solve two different problems**:

- **`@Async`**: *where should the work run?* — delegates an eligible invocation to an `Executor` / `TaskExecutor`, typically a pool with worker threads and a queue.
- **`@Scheduled`**: *when should the work be triggered?* — registers a periodic trigger with a `TaskScheduler` / `ScheduledExecutorService`, using scheduler resources to invoke the method on schedule.

Therefore, "adding an annotation does not give free threads". Tasks still consume CPU, heap, threads, connections, queues, and time budgets of the **same Java process**. If scheduling uses one thread and a blocking task occupies it, other triggers may be delayed. If the async pool is too small or its queue is unbounded, work may slow down, get rejected, or grow memory dangerously.

This lesson belongs to the **Threads and Tasks** section of Spring Boot Application Runtime. Examples run on **Java 17+ and Spring Boot 3.3.x**, using platform threads by default; the final section also explains virtual threads on Java 21+.

## 1. Mechanism map: trigger and executor are two distinct roles

~~~text
HTTP request / runner / event / another method
               |
               | call @Async bean via Spring proxy
               v
       ThreadPoolTaskExecutor
          |    |    |
       worker threads + queue
               |
               v
          Business method
               |
               +---- may call DB / HTTP / broker


Spring TaskScheduler
       |
       | @Scheduled trigger fires (cron/fixedRate/fixedDelay)
       v
scheduled method
       |
       +--- run processing directly on scheduler thread
       |
       +--- or call @Async bean via proxy
                         |
                         v
                  Async TaskExecutor
                         |
                         v
                    Worker thread
~~~

A scheduled method is **not automatically** dispatched to an async executor. By default, with a standard scheduler pool, the method body executes on a **scheduler thread**. Only when you **explicitly** submit work to another executor, or invoke an `@Async` Spring bean through a valid proxy, does processing move to the corresponding pool.

This creates two separate budgets:

1. **Trigger budget:** scheduler threads, wait time until the next tick, and latency in invoking scheduled methods.
2. **Processing budget:** executor workers, queue capacity, number of concurrent tasks, and downstream dependency limits.

Conflating these two budgets can cause both missed scheduler ticks and uncontrolled backlogs.

## 2. How does @Async work?

Example service:

~~~java
@Service
public class ReportService {

    @Async("reportExecutor")
    public CompletableFuture<String> generate(String reportId) {
        // Perform work on the selected executor.
        return CompletableFuture.completedFuture("report-" + reportId);
    }
}
~~~

This is an **illustrative** snippet requiring imports for `Service`, `Async`, and `CompletableFuture`, enabling `@EnableAsync`, and defining an executor bean named `reportExecutor` to run as annotated.

Typical flow:

1. A caller invokes the method on the **bean's Spring proxy**.
2. The proxy recognizes `@Async("reportExecutor")`.
3. The proxy wraps the invocation as a task and submits it to the corresponding executor.
4. The caller returns early (for supported return types), rather than waiting for the method body to finish on the caller thread.
5. A worker thread pulls the task from the queue and executes the method.
6. Success, failure, task cancellation, and `Future`/`CompletableFuture` completion must all be handled according to the method contract.

**Key takeaway:** `@Async` has no effect when the method is called without going through an appropriate interceptor/proxy, such as self-invocation of a method within the same class in standard proxy mode.

### Enabling @Async

Spring does not automatically process every `@Async` simply because the annotation is on the classpath. Enable it:

~~~java
@Configuration
@EnableAsync
class AsyncConfiguration {
}
~~~

This is a configuration snippet, not a standalone class without imports. You can place `@EnableAsync` directly on the main `@SpringBootApplication` class as in the full example below.

`@Async` applies to methods returning `void`, `Future<T>`, or `CompletableFuture<T>` under Spring's contract. If a `void` method throws an exception, the caller receives no exception via a return value; configure logging and `AsyncUncaughtExceptionHandler` as appropriate. With `CompletableFuture`, the caller should observe outcomes via `whenComplete(...)`, `handle(...)`, or equivalent APIs. Never fire a task and completely ignore success/failure.

## 3. How does @Scheduled work?

Enable scheduling with:

~~~java
@Configuration
@EnableScheduling
class SchedulingConfiguration {
}
~~~

A bean can declare:

~~~java
@Scheduled(fixedDelay = 5000)
public void pollInbox() {
    // Task is called again after the previous run finishes and waits 5 seconds.
}
~~~

For standard synchronous methods:

- **`fixedDelay`**: wait interval measured from the **end of the previous call** to the **start of the next one**.
- **`fixedRate`**: attempts to trigger on a steady cadence relative to start times; if the scheduler lacks threads or work runs long, runs can slip with no strict millisecond guarantee.
- **`cron`**: triggers according to a schedule expression, potentially requiring timezone, DST, and multi-instance duplication considerations.
- **`initialDelay`**: waits an initial interval before the first execution, useful to reduce startup noise.

Syntax example:

~~~java
@Scheduled(initialDelay = 1000, fixedRate = 10000)
public void refreshMetadata() {
    // Consider the method's duration and concurrency.
}
~~~

With a **single-threaded** `ThreadPoolTaskScheduler` as Spring Boot's default non-virtual-thread configuration, multiple scheduled methods contend for the same thread. One method sleeping for 30 seconds or waiting on a slow HTTP timeout can noticeably delay other ticks.

**Do not mistake `@Scheduled` for a durable job queue system.** If the process dies, an in-memory tick schedule does not magically become a stateful distributed job with retries and exactly-once semantics. In Kubernetes with three replicas, each replica can register and run the same `@Scheduled` method. To ensure "only one instance runs", you need leader election, a distributed lock, an external scheduler, or an idempotent design.

## 4. Which executor and scheduler does Spring Boot auto-configure?

In **Spring Boot 3.3** on Java 17 / platform threads with no custom beans altering auto-configuration conditions:

| Need | Type typically auto-configured by Boot | Defaults to remember |
|---|---|---|
| Task execution, e.g. `@EnableAsync` | `ThreadPoolTaskExecutor` | Pool starts with **8 core threads**; properties under `spring.task.execution.*` tune execution/queue. |
| Scheduling, e.g. `@EnableScheduling` | `ThreadPoolTaskScheduler` | **Default pool size is 1 thread**; properties under `spring.task.scheduling.*` can adjust it. |

The condition "no custom bean" is crucial. When an application registers its own `Executor`, Boot may **back off** creating the default async executor; when an application registers a `TaskScheduler`, Boot may likewise skip creating a default scheduler. Never assume all `spring.task.execution.*` properties automatically apply to an executor you manually construct with `new ThreadPoolTaskExecutor()`.

Example when **using Boot auto-configuration**, configured in `application.properties`:

~~~properties
spring.task.execution.thread-name-prefix=app-async-
spring.task.execution.pool.core-size=8
spring.task.execution.pool.max-size=16
spring.task.execution.pool.queue-capacity=100
spring.task.execution.pool.keep-alive=10s

spring.task.scheduling.thread-name-prefix=app-schedule-
spring.task.scheduling.pool.size=2
~~~

Here:

- The async pool has 8 core threads, max 16, queue capacity 100.
- When all core threads are busy, tasks are usually queued first; once the queue is full, the pool can grow up to max size; when both pool and queue are full, new tasks can be **rejected**.
- The scheduler has 2 threads, allowing more concurrent schedules than a single scheduler thread.
- **An unbounded queue** can cause `max-size` to almost never take effect as expected; understand `ThreadPoolExecutor` queuing rules.

Setting a finite queue capacity is a way to enforce **backpressure**: the system must decide how to handle saturation instead of accepting infinite work.

## 5. Choosing an Executor for @Async and TaskScheduler for @Scheduled

The two bean types should have clear names and responsibilities:

~~~java
@Bean("businessExecutor")
ThreadPoolTaskExecutor businessExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("business-");
    return executor;
}

@Bean("taskScheduler")
ThreadPoolTaskScheduler taskScheduler() {
    ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
    scheduler.setPoolSize(2);
    scheduler.setThreadNamePrefix("schedule-");
    return scheduler;
}
~~~

These are **illustrative factory methods** belonging inside a configuration class with Spring imports. When declared as beans, Spring manages their initialization and destruction; do not manually call `initialize()` on the bean instance inside the factory method and let the container initialize it twice.

To route an async method to the pool above:

~~~java
@Async("businessExecutor")
public CompletableFuture<Result> calculate(...) {
    // ...
}
~~~

This snippet is illustrative, requiring a `Result` class and method body. `@Async`'s value can specify the executor bean/qualifier explicitly, avoiding "adding a new Executor bean accidentally shifts existing @Async methods to a different pool".

For `@Scheduled`, a suitable `TaskScheduler` bean can be picked up by the processor. When only one scheduler bean exists with the standard name `taskScheduler`, selection is usually unambiguous. If multiple schedulers coexist, specify the intended scheduler via appropriate configuration APIs or the scheduler attribute on the annotation when supported by your Spring version, rather than guessing which one the container picks.

**Do not reuse one pool for everything just because you can.** Long blocking work, schedulers, and async HTTP processing have different load profiles. Separate pools let you apply distinct timeouts, queues, metrics, and shutdown policies.

## 6. Complete example: a scheduled trigger dispatches tasks to an async executor

The program below explicitly creates:

- A scheduler named `taskScheduler` with thread prefix `timer-`.
- An executor named `bizExecutor` with thread prefix `jobs-`.
- A `@Scheduled` bean using the scheduler to trigger.
- A **separate** `@Async("bizExecutor")` bean to process work on the executor.
- An `ApplicationRunner` that waits for the task to finish, prints thread comparison results, and then closes the context.

Structure:

~~~text
thread-resources-demo/
├── build.gradle
└── src/main/java/com/example/threads/ThreadResourcesApplication.java
~~~

### build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

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

springBoot {
    mainClass = 'com.example.threads.ThreadResourcesApplication'
}
~~~

### ThreadResourcesApplication.java

Create `src/main/java/com/example/threads/ThreadResourcesApplication.java`:

~~~java
package com.example.threads;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

@SpringBootApplication
@EnableAsync
@EnableScheduling
public class ThreadResourcesApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ThreadResourcesApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);

        try (ConfigurableApplicationContext ignored = application.run(args)) {
            // ApplicationRunner already waited for the task to finish.
        }
    }

    @Bean("bizExecutor")
    ThreadPoolTaskExecutor bizExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(8);
        executor.setThreadNamePrefix("jobs-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(5);
        return executor;
    }

    @Bean("taskScheduler")
    ThreadPoolTaskScheduler taskScheduler() {
        ThreadPoolTaskScheduler scheduler =
                new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(1);
        scheduler.setThreadNamePrefix("timer-");
        scheduler.setWaitForTasksToCompleteOnShutdown(true);
        scheduler.setAwaitTerminationSeconds(5);
        return scheduler;
    }

    @Bean
    Signals signals() {
        return new Signals();
    }

    @Bean
    AsyncWorker asyncWorker(Signals signals) {
        return new AsyncWorker(signals);
    }

    @Bean
    ScheduledTrigger scheduledTrigger(
            AsyncWorker worker, Signals signals) {
        return new ScheduledTrigger(worker, signals);
    }

    @Bean
    ApplicationRunner reportThreadOwnership(Signals signals) {
        return args -> {
            boolean finished = signals.done.await(10, TimeUnit.SECONDS);
            if (!finished) {
                throw new IllegalStateException(
                        "Timed out waiting for the scheduled async task");
            }

            String triggerThread = signals.triggerThread.get();
            String workerThread = signals.workerThread.get();

            System.out.println("task completed = true");
            System.out.println(
                    "trigger uses scheduler = "
                            + triggerThread.startsWith("timer-"));
            System.out.println(
                    "worker uses executor = "
                            + workerThread.startsWith("jobs-"));
            System.out.println(
                    "different threads = "
                            + !triggerThread.equals(workerThread));
        };
    }

    public static final class Signals {
        final CountDownLatch done = new CountDownLatch(1);
        final AtomicReference<String> triggerThread =
                new AtomicReference<>();
        final AtomicReference<String> workerThread =
                new AtomicReference<>();
    }

    public static class ScheduledTrigger {
        private final AsyncWorker worker;
        private final Signals signals;

        ScheduledTrigger(AsyncWorker worker, Signals signals) {
            this.worker = worker;
            this.signals = signals;
        }

        @Scheduled(initialDelay = 200, fixedDelay = 60000)
        public void tick() {
            signals.triggerThread.set(Thread.currentThread().getName());
            // Call via another bean, wrapped by Spring @Async proxy.
            worker.process();
        }
    }

    public static class AsyncWorker {
        private final Signals signals;

        AsyncWorker(Signals signals) {
            this.signals = signals;
        }

        @Async("bizExecutor")
        public void process() {
            signals.workerThread.set(Thread.currentThread().getName());
            signals.done.countDown();
        }
    }
}
~~~

All helper classes in the example are nested classes. `ScheduledTrigger` and `AsyncWorker` are **separate instances**, and `worker.process()` invokes a Spring-managed bean rather than `this.process()` within the same object.

Why use `CountDownLatch`? Because scheduling runs in the background. If `main` merely called `run()` and closed the context immediately, the console app could exit before the first scheduled tick occurs. The runner awaits completion of the first task so it can inspect it. The **10-second** wait is a test-example limit, not a recommended production timeout.

### Run and observe

In the project directory with the Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

This is a Spring Boot program with corresponding dependencies; you cannot run the Java file standalone with a bare `javac` command without Spring Framework/Spring Boot on the classpath.

Under normal execution, ignoring Spring Boot and Gradle log lines, the **stdout explicitly printed by the demo code** is:

~~~text
task completed = true
trigger uses scheduler = true
worker uses executor = true
different threads = true
~~~

Those four lines are printed inside `ApplicationRunner` **after** `CountDownLatch` signals task completion, so their order is deterministic. `triggerThread` has prefix `timer-`; `workerThread` has prefix `jobs-`. Actual thread names can include varying numeric suffixes, so the program checks prefixes and prints booleans rather than asserting one fixed thread name.

**Technical walkthrough:**

1. `@EnableScheduling` makes Spring register `ScheduledTrigger.tick()` on a schedule.
2. `ThreadPoolTaskScheduler` uses thread `timer-...` to invoke `tick()`.
3. `tick()` records its thread name and calls `AsyncWorker.process()` **through a Spring-managed bean**.
4. `@Async("bizExecutor")` dispatches `process()` execution onto `ThreadPoolTaskExecutor`, thread `jobs-...`.
5. The worker records its thread name and signals completion; the runner reads both names to verify they differ.
6. When exiting the `try` block, the context closes, stopping the scheduler and executor according to Spring's lifecycle.

No HTTP server is needed in this example. `WebApplicationType.NONE` keeps focus on background resources rather than Tomcat threads or other web components.

## 7. What happens when @Scheduled runs blocking work directly?

Without offloading to an async executor, a scheduled method like the following runs on the scheduler thread:

~~~java
@Scheduled(fixedDelay = 1000)
public void slowPoll() throws InterruptedException {
    Thread.sleep(5000);  // Simulate five seconds of blocking I/O.
}
~~~

This is an illustrative method inside a bean with scheduling enabled; **do not** add it directly to the section 6 program if you want to preserve the described stdout.

With `fixedDelay = 1000`:

- One execution takes about 5 seconds.
- Spring waits about 1 second **after the execution finishes** before scheduling the next one.
- The effective period of this method alone is about 6 seconds, excluding scheduling latency.
- If the scheduler pool has only one thread, during that blocking wait it is also unavailable to run other scheduled tasks.

Increasing `spring.task.scheduling.pool.size` can keep **different jobs** from competing for one thread, yet does not replace timeouts, controlled retries, or an architecture that offloads heavy processing from the scheduler.

With `fixedRate=1000`, the scheduler tries to maintain a one-second cadence, though without enough CPU/threads triggers still lag. **Fixed rate is not a promise that every invocation always runs concurrently or fires on the exact mark**; for a single task registered on a standard scheduler, direct invocations do not spontaneously spawn overlapping runs on the same schedule.

With `cron`, you must also account for timezones, DST, application downtime, and each replica running its own schedule.

## 8. Why can combining @Scheduled with @Async be dangerous without bounds?

Suppose the scheduler triggers every 1 second while each async task takes 30 seconds to process. When `@Scheduled` merely **submits** a task to the executor and returns right away, it can keep triggering subsequent runs without waiting for previous work to complete.

~~~text
Scheduler: tick1 tick2 tick3 tick4 tick5 ...
                |     |     |     |
                v     v     v     v
Executor:     queue / worker 1 / worker 2 ...
                |
           backlog grows if arrival rate > processing rate
~~~

In that situation:

- **`fixedDelay` measures completion of the submitting scheduled method**, not automatically waiting for the async worker to finish processing.
- Executions **can overlap** if the executor has multiple threads.
- The queue can grow steadily, causing latency and heap consumption.
- If the queue is bounded, the executor may reject new tasks upon saturation.
- Non-idempotent tasks can execute duplicate work across multiple triggers, retries, or Pods.
- The scheduler may still look "on time" while the actual processing backlog has grown huge.

If only one job may run at a time, enforce an explicit policy:

1. **Do not offload to async** if the job is short, safe, and fits the scheduler's capacity.
2. Use a `Semaphore` or state flag to **skip a tick while the previous job is still running**, if skipping is acceptable.
3. Use a **bounded durable queue** when every piece of work must be stored and processed later; never rely on a thread pool's internal queue for durability.
4. Use a **distributed lock/leader election** when multiple instances might trigger the same job.
5. Design **idempotency keys** and retry/backoff so duplicate side effects do not occur.

**Warning:** Placing both `@Scheduled` and `@Async` on **the same method** can yield hard-to-follow semantics depending on bean/proxy mechanics and completion handling. For learning and operations, the **scheduled trigger bean → async worker bean** pattern shown in section 6 is usually clearer.

## 9. Queues, pool size, and task rejection errors

Consider an executor configured with:

~~~properties
spring.task.execution.pool.core-size=2
spring.task.execution.pool.max-size=4
spring.task.execution.pool.queue-capacity=10
~~~

When this configuration applies to the **Boot auto-configured executor** (not the custom bean in section 6), the core `ThreadPoolExecutor` mechanics are:

1. Create/use core workers to handle tasks.
2. When all core workers are busy, place new tasks into the queue if space remains.
3. When the queue is full, create additional workers up to max size.
4. When both worker slots and queue are saturated, new tasks can be **rejected** per the rejection policy.

In Spring, rejection can surface as `TaskRejectedException` at task submission; for `@Async` calls, the caller may receive an exception when the proxy fails to submit the task.

**There is no "infinite yet safe" configuration**: too many threads increase context-switching and downstream load, too large a queue causes latency and heap pressure, and too small a queue triggers frequent rejections. Size based on processing duration and arrival rate.

Sizing thought experiment:

~~~text
Arrival rate:  20 jobs/second
Average processing time: 0.5 seconds
Estimated minimum concurrency: ~10 in-flight jobs
~~~

This estimate comes from `concurrency ≈ throughput × latency` (Little's Law under steady state), **not an automatically recommended pool configuration**. You must also factor in tail latency percentiles, blocking I/O, retries, CPU cores, downstream rate limits, and traffic spikes.

### Two distinct kinds of "on time"

- **Scheduler lag**: a tick arrives late because the scheduler lacks threads or a callback is blocking.
- **Executor queue wait**: the tick submitted on time, yet a worker started processing late due to queuing.

A dashboard showing only when `@Scheduled` was invoked will **not reflect** when the job actually completed. Measure schedule-to-submit, submit-to-start, processing duration, active workers, queue depth, task rejections, and outcomes separately.

## 10. @Async is proxy-based — calling within the same bean does not switch threads

This is a common mistake:

~~~java
@Service
public class InvoiceService {

    public void prepare() {
        sendInBackground(); // self-invocation, bypasses proxy
    }

    @Async("bizExecutor")
    public void sendInBackground() {
        // May still run directly on the caller thread!
    }
}
~~~

The snippet above is illustrative, requiring imports and beans. With `@EnableAsync` in **default proxy mode**, calling `this.sendInBackground()` or `sendInBackground()` inside the same class bypasses the Spring async interceptor.

Consequences:

- Code appears to have `@Async` yet actually executes synchronously.
- The configured thread pool is not used.
- The request/scheduler thread may block for a long time.
- Why does checking thread names matter? Because it verifies whether the proxy actually offloaded work to the executor.

Reliable fix: extract the async part into **another Spring bean** and inject it, just like `ScheduledTrigger` and `AsyncWorker` in section 6. Do not manually call `new AsyncWorker(...)` and expect annotations to work. Also, overly restrictive classes/methods for proxies (such as `final` methods under certain proxy mechanisms) may fail interception; design proxyable service APIs.

## 11. Same JVM does not mean same thread or same transaction

When a method switches to an async worker thread, examine everything normally bound to the thread:

| Data or mechanism | What to watch out for |
|---|---|
| Custom `ThreadLocal` | Does not automatically copy to the worker thread. |
| Logging MDC / trace context | Can lose correlation unless context propagation is configured. |
| Spring SecurityContext | Cannot be assumed present on every thread; use appropriate executor wrappers/context propagation. |
| Transaction bound to caller thread | Does not automatically transfer the transaction context to the worker. |
| Request attributes | May not exist or the request may have finished when the task runs. |
| EntityManager / Hibernate session | Not inherently thread-safe or kept open on the worker. |
| Cancellation / interruption | Must be designed explicitly; do not assume everything stops instantly. |

For example, a `@Transactional` controller calling `@Async`. Do not assume work inside the worker shares **the exact transaction open on the request thread**. If the job needs a transaction, define an appropriate transaction boundary on the service invoked by the worker and verify it passes through a valid transaction-managing proxy.

**Exception scope:** if an async method returns `CompletableFuture<T>`, failure resides in the future. If `void`, there is no return value for the caller to observe; configure handlers, logging, metrics, and alerts. When a synchronous `@Scheduled` method throws an exception, scheduler/error-handler behavior differs from an error inside an already-submitted async task; do not assume the scheduler always sees exceptions occurring on worker threads.

## 12. Shutdown: both executor and scheduler hold resources to release

At runtime, the scheduler holds timer tasks while the executor holds queues and worker threads. Both must be handled properly when the context closes or a Pod receives SIGTERM.

Questions you must answer:

- Do you **stop accepting new tasks** before closing pools?
- Will running tasks finish or be requested to cancel?
- Should queued waiting tasks drain completely, cancel, or persist to a durable queue?
- What is the maximum shutdown wait time?
- When interrupted, does task code clean up resources and restore the interrupt flag properly?
- Are any tasks waiting on I/O without timeouts, prolonging shutdown?

Section 6's example includes:

~~~java
executor.setWaitForTasksToCompleteOnShutdown(true);
executor.setAwaitTerminationSeconds(5);

scheduler.setWaitForTasksToCompleteOnShutdown(true);
scheduler.setAwaitTerminationSeconds(5);
~~~

These calls express a **waiting policy** on shutdown; understand that tasks can outlast the timeout and critical systems require more durable policies. With Kubernetes graceful shutdown, align total cleanup time with `terminationGracePeriodSeconds`, readiness transitions, and ingress/load-balancer timeouts.

For high-frequency `@Scheduled` tasks, shutdown should prevent new ticks and avoid creating further backlog while executors stop. Cancellation/interruption behavior for scheduled futures depends on `TaskScheduler` configuration and Spring version; do not naively assume "closing context = every running task finishes immediately".

If a job must run **reliably without data loss** across pod restarts, never treat an in-memory executor queue as durable storage. Use a message broker, database job table, or durable scheduler with required ack/retry/idempotency.

## 13. Measuring resources and detecting bottlenecks

A production system should track:

| Signal | What it reflects |
|---|---|
| Active async worker count | How many workers are actively processing. |
| Async executor queue size | Backlog and potential wait time. |
| Task rejection count | Pool/queue cannot accept more tasks. |
| Scheduler trigger delay | How late schedules fire compared to due time. |
| Work duration p50/p95/p99 | Whether task latency is rising. |
| Error/timeout/retry counts | Failing work or retries adding extra load. |
| Thread dump / blocked threads | Deadlocks or prolonged blocking. |
| Heap, GC, CPU, connection pool | Actual resource pressure inside the JVM. |

Micrometer/Actuator can integrate with properly instrumented executors, yet **do not assume every custom bean automatically exports all metrics**. Check which signals your dashboards collect, and register metrics by executor/scheduler name plus correlation IDs where needed.

For schedulers, tracking **actual start time** versus scheduled due time can matter more than just method invocation timestamps. For async, tracking **queue wait** helps separate CPU-bound issues from slow downstream dependencies.

### Separating workloads by profile

- **CPU-bound work**: generally avoid using far more workers than CPU cores without good reason.
- **Blocking I/O work**: may warrant higher concurrency, but must enforce timeouts and downstream connection limits.
- **Low-priority work**: give it its own pool/queue so it does not starve critical requests.
- **Periodic triggers**: keep trigger methods fast; avoid long network calls on scheduler threads if important schedules share the pool.
- **Cluster-wide single execution**: requires distributed coordination, not just tuning scheduler thread counts per Pod.

## 14. What do Java 21 virtual threads change?

Spring Boot 3.3 supports `spring.threads.virtual.enabled=true` when running on **Java 21+**. When enabled:

- Boot may auto-configure `SimpleAsyncTaskExecutor` using **virtual threads** instead of the usual `ThreadPoolTaskExecutor`.
- Scheduling may use `SimpleAsyncTaskScheduler` instead of `ThreadPoolTaskScheduler`.
- Previous pool-size properties may **no longer apply** the same way as with platform-thread pools.
- With `SimpleAsyncTaskScheduler`, fixed-delay tasks have specific behavior: fixed-delay tasks execute on a scheduler thread, so consider fixed-rate/cron and exact semantics.
- Virtual threads help blocking I/O models scale in many scenarios, yet **do not** make CPU, database connection pools, API rate limits, or memory infinite.

Sample configuration (only when running Java 21+):

~~~properties
spring.threads.virtual.enabled=true
spring.main.keep-alive=true
~~~

`spring.main.keep-alive=true` should be considered for console apps using only virtual threads, because virtual threads are **daemon threads** and do not keep the JVM alive once non-daemon threads end. Do not copy this property pair into the Java 17 example in section 6; that example explicitly creates platform-thread pools specifically to verify traditional scheduler/executor separation.

**Specifically:** when manually declaring `ThreadPoolTaskExecutor` and `ThreadPoolTaskScheduler` as in section 6, merely enabling the virtual threads property **does not automatically turn those custom beans into virtual-thread implementations**. To switch, choose the appropriate executor/scheduler types and re-test behavior.

## 15. Testing and hands-on exercises

Keeping the section 6 example program, try each change individually:

1. **Print actual thread names** inside `ScheduledTrigger.tick()` and `AsyncWorker.process()`. Observe one thread prefixed `timer-` and the other prefixed `jobs-`.
2. **Remove `@Async` from `AsyncWorker.process()`**: the method runs directly on the scheduler thread. Both "worker uses executor" and "different threads" become `false`.
3. **Remove `@EnableAsync`** while keeping `@Async`: observe that the call is no longer handled by the normal async proxy.
4. **Remove `@EnableScheduling`**: the tick is never registered, and the runner waits past 10 seconds before throwing a timeout. This is a verifiable failure test, not an expectation that startup still succeeds.
5. **Have a scheduled method sleep 3 seconds** and add another scheduled method: observe the delay when scheduler pool size is 1.
6. **Shrink executor queue capacity** and submit controlled blocking tasks: observe wait times and task rejection behavior. Do not run unbounded stress tests in shared environments.
7. **Call an `@Async` method via self-invocation** in the same class and compare thread names with calling via another bean.
8. **Simulate shutdown** while a job is running: verify timeouts, interrupts, resource cleanup, and reporting of unfinished work.

When testing production behavior, do not look only at log line counts. Verify three independent questions: **did the tick fire on schedule? was the task submitted to the executor successfully? did the task complete or fail per contract?**

## 16. Common design mistakes

**Mistake 1 — "@Scheduled runs on the @Async pool by default".**

False. Scheduler and executor are two distinct concepts with separate configurations and resources. To offload, invoke an `@Async`-managed worker bean or submit the task to an appropriate executor.

**Mistake 2 — "Adding @Async means the task uses no JVM resources".**

False. It still consumes threads, CPU, heap, connections, and queues; it only switches the execution context.

**Mistake 3 — "A single-threaded scheduler pool still runs every job on time".**

No. One blocking method can delay all other ticks. Measure workload and tune the scheduler pool or offload design.

**Mistake 4 — "@Scheduled fixedDelay guarantees waiting for the async worker to finish".**

Not automatically. If the scheduled method only submits an async task and returns, fixedDelay measures from when the submitting method finishes, not when the worker finishes processing.

**Mistake 5 — "I configured spring.task.execution.pool.* so every @Async uses that pool".**

Not guaranteed. A custom `Executor` bean, `AsyncConfigurer`, qualifiers, or another context can override executor selection. If custom executors exist, auto-config properties may not apply.

**Mistake 6 — "@Async self-invocation in the same class still runs on another thread".**

Not in default proxy mode. Extract the worker to another bean and call through the Spring proxy.

**Mistake 7 — "The bigger the queue, the safer it is".**

An oversized queue increases latency, retains objects on the heap, and masks overload. Size properly and apply backpressure, timeouts, and rejection policies.

**Mistake 8 — "Cron runs only once across the entire Kubernetes deployment".**

False. Every replica typically has its own scheduler. Distributed coordination is required for jobs that must run once cluster-wide.

**Mistake 9 — "Transaction/request context automatically transfers to the async thread".**

Not by default. Thread-bound state needs explicit context propagation; transaction boundaries must be explicit.

**Mistake 10 — "Closing the context means all queued tasks are durably saved".**

No. In-memory executor queues can be lost on process death. Critical work needs proper persistence, acks, and retries.

## 17. Pre-deployment checklist

- Correctly enable `@EnableAsync` and `@EnableScheduling` where needed.
- Know which bean executes each `@Async` (name/qualifier/AsyncConfigurer) and which bean drives `@Scheduled`.
- Log/observe thread names to verify the async proxy works; check for self-invocation.
- Size scheduler pools appropriately and avoid direct blocking on ticks.
- Configure executor core/max/queue/rejection based on load and downstream limits.
- Separate job triggers from job processing when processing can run long; also prevent backlog overflow and bad overlaps.
- Distinguish fixedRate, fixedDelay, cron, and initialDelay with tests involving realistic durations.
- Never assume distributed single execution when running multiple replicas.
- Handle exceptions for `void @Async` and `CompletableFuture`; emit metrics on failed/rejected tasks.
- Account for MDC, tracing, security, transactions, and request context across thread boundaries.
- Ensure graceful shutdown, timeouts, thread/queue draining, and durability policies for critical work.
- When using Java 21 virtual threads, re-verify executor/scheduler types and which properties actually take effect.

### Official documentation

- Spring Boot 3.3 — *Task Execution and Scheduling*: https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html
- Spring Framework 6.1 — *Task Execution and Scheduling*: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Framework 6.1 — `@Async` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/annotation/Async.html
- Spring Framework 6.1 — `@Scheduled` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/annotation/Scheduled.html

**Remember:** `@Scheduled` decides **when to trigger**, while `@Async` decides **where to process**. A scheduler thread does not automatically turn into an async worker thread. In Spring Boot, both depend on **finite execution resources** managed inside the JVM. Sound design specifies which scheduler generates ticks, which executor processes work, how many tasks the queue may hold, what to do on overload, and how to stop on shutdown.
