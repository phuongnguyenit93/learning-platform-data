# Shutting Down Executors Properly in the Spring Application Events Lifecycle

## 1. Why Does Executor Lifecycle Matter?

In a Spring application, `@Async` or a `TaskExecutor` offloads work from the publisher thread to a worker thread. With Spring Application Events, this is often used to send emails, update projections, write auxiliary audit logs, or process notifications after a domain event.

However, **an executor is a lifecycle-managed resource**: it creates/holds threads, accepts tasks, queues tasks, lets workers execute them, and eventually must stop accepting work and reclaim resources. If shutdown is neglected, the application may:

- Shut down the HTTP server while the thread pool stays alive, preventing the JVM from exiting.
- Lose tasks sitting in the queue when the process stops.
- Interrupt a task mid-write, leaving state indeterminate.
- Keep running listeners after `DataSource`, HTTP clients, or dependent beans have already been destroyed.
- Reject tasks submitted during shutdown without appropriate logs or metrics.
- Extend a rolling deployment past the platform's graceful shutdown deadline.
- Accidentally create multiple executors via `Executors.newFixedThreadPool(...)` with nobody responsible for shutting them down.

**Goal:** the executor runs only while the application permits accepting work; when `ApplicationContext` closes, the executor handles in-flight and queued tasks according to **an explicit policy**, with timeouts, observability, and without assuming work succeeded merely because `close()` was called.

This lesson belongs to the **Threads and Context** group in Spring Framework Application Events. The focus is managing executors for listeners, not creating Java threads in general.

### A Typical Processing Path

~~~text
HTTP / Scheduler / Consumer
             |
             v
     Publisher.publishEvent(event)
             |
             v
       @Async @EventListener
             |
             v
      Spring-managed TaskExecutor
             |
        +----+-----+
        |          |
       RUNNING     QUEUED
        |          |
        +----+-----+
             |
     ApplicationContext.close()
             |
     shutdown policy:
     - accept new tasks?
     - wait for running tasks?
     - drain queue or discard?
     - how long to wait at most?
             |
             v
       Executor stopped
~~~

## 2. Who Owns the Executor and Who Is Responsible for Closing It?

A useful rule: **the component that creates and owns an executor is responsible for managing its lifecycle**.

| How the executor is created | Owner | Typical appropriate shutdown |
| --- | --- | --- |
| `@Bean ThreadPoolTaskExecutor` | Spring `ApplicationContext` | Let Spring initialize it and invoke its destruction callback |
| `@Bean(destroyMethod = "shutdown") ExecutorService` | Spring manages the bean; JDK provides the pool | Spring invokes `shutdown()`; add a wait policy if needed |
| `new ThreadPoolExecutor(...)` inside a service | Self-managed by the service | Service must close it in a lifecycle hook, or convert it to a Spring bean |
| Executor provided by an application server / Jakarta EE | External container | Follow container contract; do not arbitrarily shut down a resource you do not own |
| `SimpleAsyncTaskExecutor` | Depends on bean/config | Not a reusable thread pool; requires separate concurrency/shutdown awareness |
| Executor from Spring Boot auto-config | Spring Boot / Spring | Configure via appropriate properties/beans; verify which executor is actually used |

Recommended approach for this scenario: **declare `ThreadPoolTaskExecutor` as a Spring bean with a clear name, and let the context manage init/destroy**. Never create a new pool on every event handling invocation.

### Bean Configuration Example

~~~java
@Configuration
@EnableAsync
public class EventExecutorConfiguration {

    @Bean("eventsExecutor")
    public ThreadPoolTaskExecutor eventsExecutor() {
        ThreadPoolTaskExecutor executor =
            new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("events-");

        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);
        return executor;
    }
}
~~~

This is **illustrative code inside a Spring application**; it requires importing `Configuration`, `EnableAsync`, `Bean`, `ThreadPoolTaskExecutor`. When the bean belongs to `ApplicationContext`, Spring manages the initialization/destruction callbacks of `ThreadPoolTaskExecutor`. Therefore, **do not call `executor.initialize()` manually inside the `@Bean` method, and do not call `shutdown()` from a business listener**.

The pool sizes, queue capacity, and wait time are illustrative numbers, not default settings to apply blindly to every workload.

## 3. Understanding ApplicationContext and Executor Lifecycles

With `ConfigurableApplicationContext.close()`, Spring executes the context shutdown process, including publishing `ContextClosedEvent`, coordinating the lifecycle processor, and destroying eligible singletons. `ThreadPoolTaskExecutor` is a bean supporting lifecycle/shutdown management, so it can participate in this process.

Conceptual flow:

~~~text
Active ApplicationContext
      |
      | ContextClosedEvent starts shutdown process
      v
Lifecycle stop / early shutdown signaling
      |
      | beans stopped according to phase/policy
      v
Destroy singleton beans
      |
      | ThreadPoolTaskExecutor.destroy() / shutdown()
      v
Close complete
~~~

**Do not interpret this diagram as a rigid sequence applying identically to every bean.** Different policies (notably `waitForTasksToCompleteOnShutdown`, `acceptTasksAfterContextClose`, and `strictEarlyShutdown`) can alter whether an executor stops early, accepts late tasks, and participates in coordinated lifecycle stop.

### 3.1. Close Does Not Mean All Work Has Finished

When `context.close()` is called:

- Spring invokes bean stop/destroy hooks according to policy.
- The executor may wait for running tasks, process queued tasks, or interrupt/cancel tasks depending on configuration.
- `awaitTerminationSeconds` is only **a maximum wait time**, not a promise that all tasks will succeed.
- If a task ignores interrupts or hangs on I/O, shutdown may not finish cleanly within the limit.
- Even if a task completed inside the JVM, delivery to another system may still not be durable without an appropriate confirmation mechanism.

The term "graceful shutdown" must be defined concretely: **stop accepting new work, let in-flight work finish, wait for a bounded duration, and then enforce a policy for unfinished work**.

### 3.2. ContextClosedEvent Is Not a License to Shut Down Shared Pools Arbitrarily

A listener receiving `ContextClosedEvent` can log or update state, but should not call `shutdown()` itself on a Spring-managed shared executor while other beans still depend on that pool. Spring already manages the executor bean's lifecycle.

In particular, avoid designing "on context close, publish an async cleanup event and assume the listener will always run": the executor may already be receiving stop signals; the task may be rejected, canceled, or lack enough time before the process exits.

## 4. Three Key Configurations in Spring Framework 6.2

Spring provides explicit properties on `ExecutorConfigurationSupport`, the base class of `ThreadPoolTaskExecutor`.

### 4.1. `setWaitForTasksToCompleteOnShutdown(true)`

~~~java
executor.setWaitForTasksToCompleteOnShutdown(true);
~~~

This policy instructs the executor to perform an orderly shutdown, letting **currently running tasks continue** and **queued tasks have a chance to execute**, instead of simply attempting to interrupt running tasks and drop the queue at the destroy step.

Important details in Spring Framework 6.2:

- This property defaults to `false`.
- When `true`, the executor favors soft shutdown during **the destruction step** and **bypasses normal coordinated lifecycle stop**.
- That can allow tasks to continue being submitted during part of the context closing phase, rather than being rejected immediately when `ContextClosedEvent` fires.
- When `false`, Spring has its own coordinated lifecycle stop and default shutdown policy. Do not assert that every task is cut off immediately upon `ContextClosedEvent`, because the executor may finish active tasks during the coordinated stop phase.

**Choosing `true` involves a trade-off:** suitable if you want to drain the queue during destruction, but **not** a strict mode that stops accepting tasks right at the start of shutdown. Keep this in mind when multiple producers are still active.

### 4.2. `setAwaitTerminationSeconds(n)`

~~~java
executor.setAwaitTerminationSeconds(30);
~~~

Sets the **maximum** time shutdown will block waiting for the executor to terminate before the container moves on to close remaining resources. For instance, 30 seconds is only a waiting budget, not a guarantee that every task finishes or succeeds.

If you set `waitForTasksToCompleteOnShutdown(true)` **without** setting await-termination, tasks may keep running while Spring destroys other beans they use. Hence the pair is usually configured together:

~~~java
executor.setWaitForTasksToCompleteOnShutdown(true);
executor.setAwaitTerminationSeconds(30);
~~~

Example risk: a worker needs `DataSource` to commit while the pool has already begun shutting down; if the container closes `DataSource` before the worker finishes, the task may fail. Await-termination reduces this risk by waiting during the destruction step, though **it still depends on lifecycle ordering, timeouts, and whether tasks can actually terminate**.

If the budget expires before tasks finish, the system still needs logs/metrics and a recovery strategy. Avoid describing `awaitTerminationSeconds(30)` as a "zero-task-loss guarantee".

### 4.3. `setStrictEarlyShutdown(true)`

~~~java
executor.setStrictEarlyShutdown(true);
~~~

In Spring Framework 6.2, this property instructs `ThreadPoolTaskExecutor` to signal shutdown **early when context closing begins**, refusing new tasks after that point per its policy. The default on `ThreadPoolTaskExecutor` in 6.2 is `false`, allowing lenient late task submission alongside coordinated lifecycle stop.

Easy-to-miss detail: `setWaitForTasksToCompleteOnShutdown(true)` and `setAcceptTasksAfterContextClose(true)` can **override** strict early shutdown behavior. Therefore, do not set all three flags and assume strict early stop is still in effect.

### 4.4. `setAcceptTasksAfterContextClose(true)`

~~~java
executor.setAcceptTasksAfterContextClose(true);
~~~

When `true`, the executor is permitted to accept late tasks during the context-close phase, though it may bypass coordinated stop. This is a conditional option, not general advice. It fits only when beans inside shutdown callbacks genuinely must submit additional tasks and you have a sufficiently safe wait/destroy policy.

**Most important:** read the Javadoc for **the exact Spring version you are using**. Early-shutdown behavior on `ThreadPoolTaskExecutor` was refined in Spring 6.1+ releases, so older guides may describe different defaults.

## 5. Choosing a Shutdown Policy by Workload Type

No single set of flags fits every listener:

| Requirement | Direction to choose | What to check |
| --- | --- | --- |
| Auxiliary task, safe to drop on stop | Default coordinated lifecycle or proactive stop | Logs/metrics exist for canceled work |
| Want to block new tasks immediately on close | Consider `strictEarlyShutdown(true)` (when not overridden by other flags) | Do producers still submit late? How are rejected tasks handled? |
| Want queued tasks to execute on destroy | `waitForTasksToCompleteOnShutdown(true)` | Does the queue have a large backlog? Are late tasks acceptable? |
| Want to wait for tasks before destroying other dependencies | `awaitTerminationSeconds(...)` with an appropriate policy | Is the budget sufficient and can tasks ever hang? |
| Final shutdown task submitted by another component | Consider lifecycle ordering/phases and `acceptTasksAfterContextClose` if truly needed | Does it bypass coordinated lifecycle stop? |
| Work must execute even if the process crashes | Durable job/outbox + dispatcher | In-memory shutdown alone is insufficient |
| Multiple services needing separate graceful stops | `SmartLifecycle`/orchestrator or job framework | Stop order, completion callbacks, timeouts |

**Another architectural problem distinct from closing the pool:** stop **producers** from generating new tasks first, drain/complete consumers, and only then close dependencies. Merely configuring an executor timeout while controllers, queue consumers, or schedulers keep pushing work into the pool makes shutdown fail to converge.

### 5.1. Capacity and Bounded Queues

~~~java
executor.setCorePoolSize(4);
executor.setMaxPoolSize(8);
executor.setQueueCapacity(200);
~~~

Capacity is part of the shutdown policy. With a huge backlog, draining the queue can take longer than the pod's termination grace period. An unbounded queue is dangerous because it hides overload and stretches out draining; a queue that is too small rejects tasks prematurely during bursts. Measure throughput, task duration, acceptable shutdown time, and peak traffic.

### 5.2. Rejection Is a Separate Failure Path

When the pool cannot accept more tasks, the executor may throw `TaskRejectedException`/`RejectedExecutionException` or apply another configured rejection policy. Do not assume exceptions in the **task body** and errors during **task submission** share the same error handler.

If a listener handles events via `@Async`, a task can be rejected **right at scheduling time**, whereas task exceptions occur after a worker has already begun executing it. Track these two error paths separately.

## 6. Complete Java 17+ Example: Closing the Context and Waiting for an @Async Listener to Finish

This is a runnable Spring Framework **6.2.8** program using Java 17+ and Maven, **without Spring Boot**. It demonstrates:

- `ThreadPoolTaskExecutor` is a **Spring bean** and is not manually shut down.
- `@EnableAsync` activates `@Async("eventsExecutor")` on the listener.
- The listener receives `WorkRequested` via `@EventListener` and runs on the executor.
- Two `CountDownLatch` instances establish deterministic log ordering without `Thread.sleep(...)`.
- Upon exiting `try-with-resources`, `AnnotationConfigApplicationContext.close()` closes the context; the configured policy makes the executor wait for the task before close completes.
- No extra tasks are submitted during shutdown, avoiding assumptions about dispatch ordering among context-closing listeners.

### 6.1. Directory Structure

~~~text
executor-lifecycle-demo/
├── pom.xml
└── src/main/java/ExecutorLifecycleDemo.java
~~~

### 6.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>executor-lifecycle-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
                <configuration>
                    <mainClass>ExecutorLifecycleDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 6.3. `ExecutorLifecycleDemo.java`

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public final class ExecutorLifecycleDemo {

    private static final CountDownLatch WORKER_STARTED =
        new CountDownLatch(1);
    private static final CountDownLatch ALLOW_COMPLETION =
        new CountDownLatch(1);

    public record WorkRequested(String jobId) { }

    // Non-final listener class so Spring can create a proxy when needed.
    public static class WorkListener {

        @Async("eventsExecutor")
        @EventListener
        public void onWorkRequested(WorkRequested event) {
            System.out.println(
                "WORK_STARTED " + event.jobId()
            );
            WORKER_STARTED.countDown();

            try {
                if (!ALLOW_COMPLETION.await(10, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("worker gate timeout");
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("worker interrupted", ex);
            }

            System.out.println(
                "WORK_DONE " + event.jobId()
            );
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class Config {

        @Bean("eventsExecutor")
        public ThreadPoolTaskExecutor eventsExecutor() {
            ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(10);
            executor.setThreadNamePrefix("events-");

            // Drain running and queued tasks on shutdown.
            executor.setWaitForTasksToCompleteOnShutdown(true);

            // Up to 10 seconds to wait during the destruction step.
            executor.setAwaitTerminationSeconds(10);
            return executor; // Spring manages init/destroy automatically.
        }

        @Bean
        public WorkListener workListener() {
            return new WorkListener();
        }
    }

    public static void main(String[] args)
            throws InterruptedException {

        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(Config.class)) {

            System.out.println("PUBLISH");
            context.publishEvent(new WorkRequested("job-1"));

            if (!WORKER_STARTED.await(10, TimeUnit.SECONDS)) {
                ALLOW_COMPLETION.countDown();
                throw new IllegalStateException("worker did not start");
            }

            // Worker has started but is waiting on the second latch.
            System.out.println("PUBLISH_RETURNED");
            ALLOW_COMPLETION.countDown();
        }

        // try-with-resources has called context.close().
        System.out.println("CONTEXT_CLOSED");
    }
}
~~~

Run from the `executor-lifecycle-demo` directory using JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java
~~~

Lines **printed by the program itself** when no timeout occurs, excluding Maven output:

~~~text
PUBLISH
WORK_STARTED job-1
PUBLISH_RETURNED
WORK_DONE job-1
CONTEXT_CLOSED
~~~

### 6.4. Analyzing the Ordering

1. `main` prints `PUBLISH` and publishes the event. `@EventListener` is registered by Spring, and `@Async("eventsExecutor")` routes execution of the listener method to the executor bean.
2. The worker prints `WORK_STARTED` and counts down `WORKER_STARTED`. Because `main` waits on that latch, `PUBLISH_RETURNED` is printed **only after** the worker has printed `WORK_STARTED`.
3. The worker is held at `ALLOW_COMPLETION.await(...)`, so it **cannot print `WORK_DONE` before `PUBLISH_RETURNED`**.
4. `main` prints `PUBLISH_RETURNED`, releases the worker's latch, and exits `try-with-resources`. This invokes `context.close()`.
5. The executor is configured to drain work and await up to 10 seconds. For this short example task, the worker prints `WORK_DONE` before `context.close()` finishes, so `CONTEXT_CLOSED` appears last.

Note: the program uses latches to **prove a separate worker exists and enforce deterministic ordering**. It does not prove that every production task finishes within the timeout; real tasks may hang on the network, run for hours, or ignore interrupts. In the example, `awaitTerminationSeconds(10)` and the latch timeouts are chosen to suffice for near-instantaneous work under normal execution conditions.

### 6.5. Why Not Call `executor.shutdown()` in `main`?

`ThreadPoolTaskExecutor` is a Spring-managed lifecycle bean. Calling `shutdown()` manually while the context is still open can cause other listeners to be rejected while the context still believes the bean is serving other components. When closing the context, Spring already has an official destruction path. If you want to stop accepting new work, coordinate **producer stop → consumer drain → resource destroy** via lifecycle policies rather than arbitrarily shutting down a shared bean.

### 6.6. Why Not Call `initialize()` Inside `@Bean`?

When returning `ThreadPoolTaskExecutor` as a Spring bean, the container applies `InitializingBean.afterPropertiesSet()` and the appropriate initialization callbacks. Calling `initialize()` manually and then letting the container initialize it again is redundant and can cause unwanted behavior. Conversely, if you instantiate an executor with `new` **outside** Spring, you must initialize/shut it down explicitly via its API.

## 7. What If the Spring Context Closes While Tasks Are Still in the Queue?

In the demo there is only one task. In a real application, an executor may have running tasks plus many queued tasks:

~~~text
                RUNNING: [A] [B]
                QUEUED : [C] [D] [E] [F]

Context.close()
    |
    +-- strict/early shutdown: limits accepting new tasks
    |
    +-- coordinated lifecycle stop or destruction policy
    |
    +-- processes A/B/C/D/E/F or interrupts/drops per config
    |
    +-- waits up to awaitTerminationSeconds
    |
    +-- closes remaining beans
~~~

You cannot tell whether C/D/E/F will execute just by looking at `@Async`. You must inspect the executor type, `waitForTasksToCompleteOnShutdown`, `strictEarlyShutdown`, timeouts, and rejection policies. With `waitForTasksToCompleteOnShutdown(true)`, the queue is given a chance to run during shutdown; however, **completing tasks** still requires time and cooperative task behavior.

### 7.1. Distinguishing Scheduled Tasks from Succeeded Tasks

A `publishEvent` that throws no error and an accepted `executor.execute(...)` only prove **submission** succeeded per API; they do not prove the task executed or that side effects persisted.

For critical tasks, track explicit status:

~~~text
PENDING -> RUNNING -> SUCCEEDED
                  \-> RETRYABLE_FAILED -> PENDING
                  \-> PERMANENT_FAILED
~~~

These statuses belong to an application-defined job system or store, not built-in fields of every Spring `TaskExecutor`.

### 7.2. Rejections During Shutdown

If a producer keeps emitting events after the pool stops accepting tasks, `@Async` may encounter `TaskRejectedException` or `RejectedExecutionException` depending on the implementation. This is a **submission** failure, distinct from an exception thrown by the listener body after accepting a task.

Define a clear policy: stop producers first, record rejected-task metrics, and retry at the appropriate layer if work must be redelivered. Never treat a submission error as "email sent" or silently swallow errors when delivery is mandatory.

## 8. When to Use `ContextClosedEvent`, `@PreDestroy`, and `SmartLifecycle`?

These three mechanisms serve different purposes.

### 8.1. `ContextClosedEvent`: Observing the Closing Phase

`ContextClosedEvent` is published while `ApplicationContext` is closing. Listeners can update a status flag, log, and coordinate shutdown according to contract. However, you should not use an async listener on this event to submit work that "must finish before JVM exit" by default, because the executor may already be stopping in the same phase.

### 8.2. `@PreDestroy`: Cleaning Up a Bean's Resources

If a bean **genuinely owns** external resources outside the container, `@PreDestroy` or `DisposableBean.destroy()` can close them. For an executor that is already a Spring-managed `ThreadPoolTaskExecutor`, **do not add `@PreDestroy` just to call shutdown on that same bean**, avoiding duplicate lifecycle management.

If a bean owns connections/files/other resources, cleanup is that bean's responsibility—do not try to turn mandatory cleanup into an async event.

### 8.3. `SmartLifecycle`: Coordinating Start/Stop by Phase

A component consuming from Kafka, WebSockets, polling, or a scheduler can implement `SmartLifecycle` to:

- Start accepting work once the context reaches the right state.
- Stop producers and cease creating new tasks on shutdown.
- Track in-flight work and invoke the `stop(Runnable)` callback.
- Choose `getPhase()` to define stop ordering per Spring's policy.

Normally, the lifecycle processor processes **stop in reverse phase order** relative to start: higher phases stop before lower phases. However, final ordering is also influenced by bean dependencies and lifecycle configuration. Do not reason from phase alone when explicit dependency relationships exist.

Pseudo-code illustrating intent:

~~~text
SmartLifecycle producer:
  start():  allowNewMessages = true
  stop(callback):
     allowNewMessages = false
     stopPollingNewMessages()
     waitUntilInFlightIsSafeOrTimedOut()
     callback.run()

Executor:
  drainAcceptedTasksAccordingToPolicy()
  shutdown()
~~~

This is pseudo-code, **not a directly compilable Java class**. When implementing `SmartLifecycle.stop(Runnable)` in practice, always invoke the callback when stopping completes so the container does not hang waiting (and handle failures/timeouts). If stopping is asynchronous, configure an appropriate phase timeout.

### 8.4. There Is No Single "Universal Order" for Every Bean

For example, a bean's `@PreDestroy` callback may run after an executor has already stopped accepting tasks. A design that relies on "during destroy I will submit an async job and wait for it" risks deadlock or rejection. In particular, never block-wait inside the same low-worker-count pool if the awaited task also requires a worker from that pool.

## 9. JDK `ExecutorService` When Manual Management Is Needed

Sometimes a library does not use `ThreadPoolTaskExecutor` and constructs an `ExecutorService` directly. If it is a Spring bean you manage, you can declare a destruction callback:

~~~java
@Bean(destroyMethod = "shutdown")
ExecutorService reportingPool() {
    return Executors.newFixedThreadPool(2);
}
~~~

This is an illustrative snippet requiring imports for `Bean`, `ExecutorService`, and `Executors` inside a configuration class. When the context destroys the bean, Spring calls `shutdown()`. However, JDK `shutdown()` **only stops accepting new tasks and lets submitted tasks run**; it does not block waiting for completion—if waiting is required, combine it with `awaitTermination(...)` per policy.

For a fully self-owned executor, the JDK shutdown pattern:

~~~java
pool.shutdown();
try {
    if (!pool.awaitTermination(30, TimeUnit.SECONDS)) {
        pool.shutdownNow();
        if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
            System.err.println("Executor did not terminate");
        }
    }
} catch (InterruptedException ex) {
    pool.shutdownNow();
    Thread.currentThread().interrupt();
}
~~~

This snippet is **placed inside the owner's lifecycle hook**, requiring a `pool` variable of type `ExecutorService` and imports for `TimeUnit`/`InterruptedException`. `shutdownNow()` is a best-effort interrupt/cancel request; it does not guarantee every task stops immediately. After a timeout, observability and recovery mechanisms are still required if the work is important.

**Never have two owners simultaneously:** if Spring manages destroying `ThreadPoolTaskExecutor` and you also manually call shutdown from several listeners, it becomes unpredictable when the pool starts rejecting tasks.

## 10. Thread Context, Transactions, and Tasks Still Running at Shutdown

Because async tasks run on worker threads, they typically **do not inherit the imperative transaction** bound to the publisher thread:

~~~text
Publisher thread                        events-1 worker
----------------------                  -----------------------
@Transactional T1
 save Order
 publish(OrderPlaced)  -----------+---> @Async listener
 COMMIT T1                          |     update projection
 return                             |     own transaction if configured
                                    +---> shutdown may begin meanwhile
~~~

A failing `@Async` listener **does not automatically roll back the source transaction**. A listener needing consistent DB operations should call a `@Transactional` service on the worker via a Spring proxy, creating a transaction with its own proper scope.

If you only want to process after the source transaction commits, consider `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)`, optionally combined with `@Async`. However:

- `AFTER_COMMIT` only coordinates **timing** relative to the transaction; it does not guarantee the task is delivered and completed.
- When published outside a transaction, the handler does not run by default unless `fallbackExecution=true` is enabled.
- Executor errors/timeouts/shutdown can occur after the transaction has already committed.
- If a post-commit listener writes to the DB, open an appropriate new transaction rather than relying on the old transaction.
- A shutdown mechanism that waits for tasks in RAM is not **durable delivery**.

### Do Not Dump Raw `ThreadLocal` Values onto Workers

MDC, security context, locale, request context, or tracing context may need propagation via `TaskDecorator` or a context propagation library when the contract permits. However, **never copy a JDBC/JPA transaction** or `EntityManager` from publisher to worker. Attempting to share the same session/entity across threads easily triggers errors and violates transaction boundaries.

During shutdown, dependencies such as HTTP clients, connection pools, and loggers also have their own lifecycles. Ensure an appropriate shutdown order; waiting for executor tasks while the dependencies those tasks need have already been destroyed will still fail.

## 11. Exceptions in Async Tasks and Exceptions During Shutdown

Distinguish at least four failure paths:

| Error type | Example | Where observed |
| --- | --- | --- |
| **Scheduling rejection** | Full queue, executor shutting down | Submitting thread, executor-path error handling |
| **Exception in `@Async void`** | HTTP 503, serialization error | `AsyncUncaughtExceptionHandler` if uncaught |
| **Interrupted task** | Shutdown/cancel/timeout | Inside the task via `InterruptedException` or interrupt flag |
| **Termination timeout** | Worker does not stop within budget | Shutdown path, operational metrics/logs |

A `try/catch` around `publishEvent(...)` is not enough to catch exceptions thrown inside an async worker. `SimpleApplicationEventMulticaster.setErrorHandler(...)` and `AsyncUncaughtExceptionHandler` are also **two distinct layers**—do not assume one handler covers every kind of error.

### 11.1. Interrupts Must Be Handled Properly

A task should:

- Respect `InterruptedException` at blocking points.
- Restore the interrupt flag when translating to another exception: `Thread.currentThread().interrupt()`.
- Not continue looping indefinitely after being asked to stop.
- Not assume an interrupt automatically rolls back an external email or API call that already completed.

Example handling pattern:

~~~java
try {
    blockingQueue.take();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return;
}
~~~

This is illustrative code inside a method with a `blockingQueue`. Silently swallowing interrupts can prevent the container from stopping tasks within the graceful shutdown window.

### 11.2. Do Not Swallow Errors Inside Error Handlers

An exception handler can emit structured logs, metrics, failure states, or schedule retries. However, "logged" does not mean "handled to completion". If the task must succeed, persist outcomes and retry durably.

## 12. Shutdown in Deployment Environments: Stop Producers, Drain, Destroy

When running in Kubernetes, VMs, service managers, or application servers, processes typically have **a finite window** to terminate. Executor timeouts must therefore coordinate with the platform's grace period and other components.

An operational shutdown sequence should specify:

1. **Stop accepting new input:** drop readiness, stop pollers/consumers/schedulers in a designed order.
2. **Stabilize in-flight work status:** accepted tasks finish within budget or are recorded for retry.
3. **Drain the executor:** wait for running and queued work per policy.
4. **Close dependencies:** connection pools, HTTP clients, and other resources close after tasks using them have stopped.
5. **Terminate the process:** before the orchestrator/service manager deadline.

Do not configure `awaitTerminationSeconds(120)` if the platform kills the container after 30 seconds and assume you have two minutes of graceful shutdown. Conversely, a 1-second timeout for thousands of queued tasks leaves many tasks unfinished.

### Designing the Budget

~~~text
Assume platform deadline: 45 seconds
  - stop producer / readiness: up to 5 seconds
  - drain accepted work      : up to 25 seconds
  - close dependencies       : up to 10 seconds
  - safety margin            : 5 seconds
~~~

Numbers are **planning examples**, not benchmarks. In production deployments, measure p95/p99 task latency, backlog depth, consumption rate, downstream timeouts, and interruptibility. Monitor shutdown duration and unfinished task counts.

### Suggested Metrics

Names below are **application-defined** metrics, not all built automatically by Spring:

~~~text
app_event_executor_active_threads
app_event_executor_queue_depth
app_event_executor_rejected_total
app_event_executor_shutdown_duration_seconds
app_event_executor_inflight_on_close
app_event_executor_unfinished_total
app_event_listener_failures_total{listener="notification"}
~~~

Never put `eventId`/`orderId` into metric labels to avoid high cardinality; keep those IDs in structured logs and traces.

## 13. Why Even Proper Lifecycle Waiting Does Not Guarantee Delivery

Even when tasks are allowed to run until `context.close()` returns, systems must still handle:

- Process killed without running JVM shutdown hooks.
- Node power loss, kernel panic, or hard container kill.
- Email sent successfully but HTTP client timed out, risking duplicate sends on retry.
- Thread pool stopping after the source transaction committed before the task was persisted durably.
- A consumer receiving an event and crashing before recording completion state.

**`TaskExecutor` is not a message broker or event store.** For work requiring reliability, persist work intent **in the same transaction** as business state via a **transactional outbox**, and have a dispatcher deliver tasks with retries and idempotency.

~~~text
T1 BEGIN
  save order
  insert outbox(id, eventType, payload, status=PENDING)
T1 COMMIT
            |
            v
Outbox worker / broker
  -> deliver idempotently
  -> retry transient failure
  -> record success / dead-letter
~~~

If T1 rolls back, no outbox event commits. If T1 commits and the process dies, pending records can still be recovered and redelivered. Systems usually provide **at-least-once delivery** with deduplication; do not promise end-to-end exactly-once automatically.

This is a **reliability** solution, not a replacement for shutting down thread pools cleanly in the lifecycle. Both concerns must be addressed, at their respective layers.

## 14. Testing Shutdown Properly

A quality test does more than assert `context.close()` throws no exception—it verifies which tasks were accepted, executed, completed, or rejected.

| Scenario | Expectation to verify |
| --- | --- |
| Context has executor bean and no tasks | Context closes cleanly; no leaked thread pools |
| An async listener is running | Close respects wait timeout/policy without unintended interruption |
| Tasks are in the queue | `waitForTasksToCompleteOnShutdown(true)` drains the queue per contract |
| Timeout shorter than task duration | Unfinished tasks and recovery plan are observed; do not report all succeeded |
| Strict early shutdown | After close signal, new submissions are rejected per policy |
| Producer keeps submitting during shutdown | No infinite task-creation loop; rejections handled |
| Executor depends on `DataSource` | DB-dependent tasks do not run after DB destruction if safety requires it |
| Async listener throws an exception | Error handler/metrics capture the error and shutdown does not report false success |
| Thread is interrupted | Task restores interrupt flag or stops cleanly |
| Multiple services share a pool | No service manually shuts down a shared bean while context is active |
| Container killed before await timeout | Durable jobs can retry after restart |
| Parent–child or multiple `ApplicationContext`s | Each executor has a clear owner/lifetime; never use a closed bean |

### 14.1. Use Latches Instead of `Thread.sleep`

The section 6 example uses `CountDownLatch` and a 10-second timeout to establish deterministic ordering. Tests relying on `Thread.sleep(100)` are flaky because scheduling and CI load vary.

For timeout tests, deliberately hold a worker with a latch, initiate `close` on a separate test thread, and observe completion timing. Such tests must release the task in a `finally` block so the suite never hangs even if an assertion fails.

### 14.2. Tracking Progress

In addition to data assertions, monitor:

- Tasks submitted / running / queued.
- Tasks succeeded and failed.
- Tasks rejected during close.
- Actual shutdown duration.
- Tasks still unfinished when the budget expires.
- Jobs recovered from the outbox after restart.

You can write restart-simulation tests to verify **job delivery** separately from executor graceful-close tests.

## 15. Common Mistakes

1. **Creating a pool with `new` inside every listener** without keeping a reference to shut down.
2. **Declaring `ThreadPoolTaskExecutor` as a bean and manually calling `initialize()` again** unnecessarily.
3. **Calling `shutdown()` from a business method**, causing other listeners to be rejected while the context is still active.
4. **Assuming `context.close()` automatically drains the entire queue** regardless of flags/timeouts.
5. **Setting `waitForTasksToCompleteOnShutdown(true)` and thinking the pool rejects tasks as soon as `ContextClosedEvent` fires**; this flag uses a late soft shutdown during destruction.
6. **Enabling `strictEarlyShutdown(true)` alongside `waitForTasksToCompleteOnShutdown(true)` and assuming strict mode still applies intact**; check flag interactions.
7. **Enabling `waitForTasksToCompleteOnShutdown` without `awaitTerminationSeconds`** while tasks depend on other beans being destroyed.
8. **Treating `awaitTerminationSeconds` as a guarantee tasks will finish**; it is only a maximum blocking budget.
9. **Letting producers keep publishing tasks during shutdown**, causing continuous rejections or non-converging backlogs.
10. **Calling `@Async` cleanup from `@PreDestroy` and waiting on the already-shut-down pool**, risking rejections or deadlocks.
11. **Ignoring `InterruptedException`** and continuing to loop, preventing the JVM from stopping.
12. **Catching and swallowing all exceptions**, making failed tasks look successful.
13. **Using an unbounded queue for critical tasks**, hiding overload and making drains uncontrollable.
14. **Not coordinating timeouts with Kubernetes/service-manager deadlines**, causing the process to be killed before draining.
15. **Believing graceful shutdown equals durable delivery**, when hard kills and crashes remain unaddressed.
16. **Putting external email/payment actions inside an imaginary async-worker transaction**, confusing rollback with eventual consistency.
17. **Failing to measure task rejections during context close**, silently losing events.
18. **Not separating producer and executor responsibilities**, lacking an owner for the stop sequence.
19. **Using `ContextClosedEvent` to emit mandatory async tasks** even though the executor may have already stopped accepting work.
20. **Not testing timeouts and shutdown with stuck tasks**, testing only under zero load.

## 16. Self-Check Exercises

1. When `ThreadPoolTaskExecutor` is declared as a `@Bean`, who is responsible for initializing and destroying the pool?
2. How does `waitForTasksToCompleteOnShutdown(true)` differ from `awaitTerminationSeconds(30)`?
3. Why might `setStrictEarlyShutdown(true)` no longer govern behavior when `setWaitForTasksToCompleteOnShutdown(true)` is set?
4. If the Spring context closes with 10 queued tasks, can you conclude all 10 ran successfully just because `context.close()` threw no error?
5. In the demo, what ensures `WORK_DONE` is never printed before `PUBLISH_RETURNED`?
6. If the pool rejects new tasks during shutdown, does that error belong to submission or the worker body?
7. If an `@Async` listener fails to send an email after the publisher commits an order, can it roll back the order by throwing an exception?
8. Why should `@PreDestroy` not be used to emit a mandatory `@Async` task on the same executor?
9. When an executor depends on a DB and an HTTP client, why must wait times coordinate with dependency destruction order?
10. In an environment with a 30-second termination grace period, what happens if you configure `awaitTerminationSeconds(120)`?
11. Why does `ExecutorService.shutdown()` differ from `awaitTermination(...)`?
12. For work that must not be lost after a crash, what mechanism is needed in addition to the Spring event executor?
13. How should `SmartLifecycle.stop(Runnable)` signal completion?
14. Does a listener running in a thread pool automatically inherit the publisher's `@Transactional`?

**Answer hints:** (1) Spring context; (2) task-handling policy vs. blocking wait duration; (3) the wait-for-completion flag performs late shutdown and overrides the early signal; (4) no, it depends on policy/time/exceptions; (5) the latch blocks the worker until after the log; (6) scheduling error; (7) no, the source transaction already committed; (8) the pool may have stopped accepting tasks and shutdown can deadlock; (9) workers need live resources; (10) the platform may kill the process early; (11) stop accepting new tasks vs. wait for termination; (12) durable outbox/jobs + retries/idempotency; (13) invoke the callback once stopping finishes; (14) not automatically for imperative thread-bound transactions.

## 17. Summary

**Shutting down an executor properly in its lifecycle** means having a clear owner, understanding how the Spring context coordinates stop/destroy, choosing policies for accepting new tasks and draining work, waiting a reasonable maximum duration, ensuring required dependencies stay alive, and observing errors and unfinished work. For a Spring-managed `ThreadPoolTaskExecutor`, prefer letting the container manage its lifecycle rather than shutting it down manually from listeners.

Three commonly confused settings are:

- `setWaitForTasksToCompleteOnShutdown(true)`: favors completing running and queued tasks on shutdown, with trade-offs around late submission and coordinated stop.
- `setAwaitTerminationSeconds(n)`: waits up to `n` seconds for the executor to terminate before continuing destruction, without guaranteeing completion by itself.
- `setStrictEarlyShutdown(true)`: signals early stop of accepting new tasks per policy, but can be overridden by other flags.

Finally, an executor is only an **in-memory execution mechanism**. Good graceful shutdown does not eliminate crashes or hard kills. For business work that must be delivered and processed reliably, use durable mechanisms such as a **transactional outbox**, idempotent consumers, and monitored retries.

## References

- Spring Framework 6.2.8 API — *ExecutorConfigurationSupport*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/scheduling/concurrent/ExecutorConfigurationSupport.html
- Spring Framework 6.2.8 API — *ThreadPoolTaskExecutor*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Spring Framework 6.2 Reference — *Task Execution and Scheduling*: https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html
- Spring Framework Reference — *Application Events and Async Listeners*: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework 6.2.8 API — *AbstractApplicationContext*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html
- Spring Framework 6.2.8 API — *SmartLifecycle*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/SmartLifecycle.html
