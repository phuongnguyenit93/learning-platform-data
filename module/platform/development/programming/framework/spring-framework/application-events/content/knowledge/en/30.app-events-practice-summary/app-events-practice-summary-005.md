# Configuring an Async Executor for Spring Framework Application Events

## 1. Objectives and Things to Understand First

In Spring Framework, `ApplicationEventPublisher.publishEvent(...)` helps a component notify listeners of an event. The default distribution in an `ApplicationContext` typically uses a **synchronous** `SimpleApplicationEventMulticaster`: regular listeners run on the thread that published the event and can prolong request response times.

When a listener sends emails, makes HTTP calls, generates reports, or performs work that does not belong on the publisher's response path, you can configure an **asynchronous executor** to offload processing from the event-publishing thread. However, this change affects timing, exception propagation, transaction context, processing order, retries, and shutdown. A system that "publishes faster" does not mean every task has already succeeded.

After this lesson, you will:

- Distinguish an **async multicaster** from `@Async` on individual `@EventListener` methods.
- Configure a `ThreadPoolTaskExecutor` with clear core/max pool sizes, queue capacity, thread prefix, and lifecycle.
- Know how Spring looks up the bean named `applicationEventMulticaster`.
- Understand the relationship between pool size, queue size, saturation, and rejection policy.
- Write a runnable Java 17+ example with Spring Framework, without needing Kafka or Spring Boot.
- Write JUnit 5 tests proving the publisher returns while the handler is still waiting, checking default sync behavior, and testing async errors.
- Properly handle exceptions, `@Order`, `@TransactionalEventListener`, ThreadLocal/MDC, graceful shutdown, and observability.
- Decide when an in-process executor suffices and when a durable outbox, job table, or broker is needed.

**First rule:** `publishEvent(...)` is a **handoff** step to the event-dispatch mechanism. It does not guarantee that listeners are processed synchronously or have finished when the method returns. Actual execution depends on the multicaster, listeners, proxies, executor, and transaction synchronizations.

## 2. Default Architecture: Why Can Publishing Block?

Given these beans:

~~~java
public record OrderPlaced(String orderId) {}

@EventListener
public void onOrderPlaced(OrderPlaced event) {
    notificationService.send(event.orderId());
}
~~~

This is **illustrative code** only, requiring Spring beans, `notificationService`, and appropriate imports.

Default flow:

~~~text
request thread
    |
    +--> publisher.publishEvent(OrderPlaced)
             |
             +--> SimpleApplicationEventMulticaster
                       |
                       +--> listener A -> return
                       +--> listener B -> return
                       +--> listener C -> return
             |
    <-------- publishEvent returns
    |
    +--> service returns
~~~

If A takes 40 ms, B takes 100 ms, and C takes 200 ms, the publish duration can be nearly 340 ms plus dispatch overhead. One slow listener can slow down the publisher. `@Order` can arrange invocation order, but does not automatically turn listeners into parallel workers.

In Spring, events are typically **in-process notifications**, not a message broker with storage, acknowledgments, delivery guarantees, or a dead-letter queue. Switching the multicaster to async only changes execution within the JVM; it does not add event durability.

## 3. Two Main Asynchronous Paths

| Criterion | Multicaster with `TaskExecutor` | `@Async` on listener |
| --- | --- | --- |
| Where enabled? | Bean `applicationEventMulticaster` | `@EnableAsync` and `@Async` on method/bean |
| Scope | Eligible listeners **supporting async multicasting** | Only methods annotated with `@Async` |
| Separate thread? | Multicaster submits task via executor | Spring async proxy submits method invocation |
| Needs `@EnableAsync`? | No, if using only the multicaster executor | Yes, to enable annotation proxy/interceptor |
| Needs `@EventListener`? | Yes, if using annotation listeners | Yes, plus `@Async` |
| Async exceptions | Multicaster's `ErrorHandler` can observe errors from callbacks it runs | `AsyncUncaughtExceptionHandler` for void methods; errors do not return to publisher |
| Transaction-bound listeners | May decline async at multicaster to register synchronization on the right thread | If target runs async, phase/context must be checked carefully |
| Impact on new listeners | Automatically dispatched via executor if eligible | Listeners without `@Async` keep existing invocation model |
| Best fit | Want a unified dispatch policy with listener compatibility checks | Want to selectively offload a few side-effect listeners |

**Do not enable both at once** to be "more async". Using an executor on the multicaster **and** `@Async` on the method can cause two layers of task submission, wasting scheduling/queuing and making error tracking, timing, and context propagation harder. Each event pipeline should have one clear decision on where threads split.

### 3.1. Distinguishing the Concepts

- `ApplicationEventPublisher` is the API for publishing events.
- `ApplicationEventMulticaster` is the engine that invokes listeners.
- `TaskExecutor` is the task execution abstraction.
- `ThreadPoolTaskExecutor` is a Spring implementation with a thread pool and queue.
- `@Async` is AOP/proxy-based method execution.
- `@TransactionalEventListener` binds a callback to a transaction phase.
- A broker/outbox is infrastructure for **storing and transporting work durably**; it does not appear automatically when enabling an executor.

When optimizing, measure `publisher latency`, `handler processing duration`, and the time until the side effect is actually confirmed separately. Measuring around `publishEvent` is no longer end-to-end latency once processing becomes async.

## 4. Configuring the Multicaster Bean with the Exact Name

Spring `ApplicationContext` picks up a custom multicaster via a bean named **`applicationEventMulticaster`**. If absent, the context creates a default multicaster.

Configuration template:

~~~java
@Configuration(proxyBeanMethods = false)
public class EventExecutionConfig {

    @Bean(name = "applicationEventMulticaster")
    ApplicationEventMulticaster applicationEventMulticaster(
            @Qualifier("eventTaskExecutor")
            ThreadPoolTaskExecutor executor) {

        SimpleApplicationEventMulticaster multicaster =
                new SimpleApplicationEventMulticaster();
        multicaster.setTaskExecutor(executor);
        return multicaster;
    }
}
~~~

This is an **illustrative configuration snippet**: it requires declaring the `eventTaskExecutor` bean and Spring imports. A complete runnable example is shown below.

Common misconceptions:

1. Naming the bean `asyncMulticaster` instead of the special name may **fail to replace** the context's multicaster.
2. `setTaskExecutor(...)` must receive a valid lifecycle-managed `Executor`/`TaskExecutor`; do not create a new executor on every event.
3. Not every listener gets moved to another thread. Spring 6.1+ provides `ApplicationListener.supportsAsyncExecution()`; transaction-synchronization listeners can require registration on the originating thread.
4. `SimpleApplicationEventMulticaster` does not turn events into records in a durable queue.
5. When the executor rejects a task at submission time, the publish call can throw an exception (such as `TaskRejectedException`); it does not guarantee every publish always returns normally.

In a Spring Boot application, you can still declare this bean in `@Configuration`. If Boot or another library also declares a multicaster under that name, coordinate ownership explicitly; do not define two beans with the same name and rely on bean definition overriding.

## 5. Choosing `ThreadPoolTaskExecutor` and Initial Sizing

Example bounded configuration:

~~~java
@Bean("eventTaskExecutor")
ThreadPoolTaskExecutor eventTaskExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(16);
    executor.setKeepAliveSeconds(30);
    executor.setThreadNamePrefix("spring-events-");
    executor.setRejectedExecutionHandler(
            new ThreadPoolExecutor.AbortPolicy());
    executor.setWaitForTasksToCompleteOnShutdown(true);
    executor.setAwaitTerminationSeconds(10);
    return executor;
}
~~~

This is a **configuration snippet** requiring imports for `org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor` and `java.util.concurrent.ThreadPoolExecutor`. When a method returns the bean inside a Spring context, the container manages initialization and shutdown; do not mix container management with arbitrary manual creation/shutdown of the executor.

Meaning of each parameter:

| Parameter | Role |
| --- | --- |
| `corePoolSize=2` | Core worker count, typically created on demand as tasks arrive |
| `maxPoolSize=4` | Maximum worker limit when the queue is full and scaling is needed |
| `queueCapacity=16` | Maximum tasks waiting in the executor's queue |
| `keepAliveSeconds=30` | Idle timeout for non-core threads before shrinking |
| `threadNamePrefix` | Makes worker threads easy to identify in thread dumps/logs |
| `AbortPolicy` | Rejects tasks on saturation rather than silently dropping them |
| `waitForTasksToCompleteOnShutdown` | Attempts to finish already-accepted tasks on shutdown |
| `awaitTerminationSeconds` | Allows shutdown to wait a bounded time before the container proceeds |

**Important behavior of `ThreadPoolExecutor`:** it generally uses **core workers first, then the queue, and only expands toward `maxPoolSize`** once the queue is full. With core=2, max=4, queue=16, do not expect 4 threads to be used immediately when 4 tasks arrive. With a huge or unbounded queue, thread count may almost never exceed core, leading to growing backlogs.

### 5.1. Queue Capacity 0 vs. Large Queues

`queueCapacity=0` in `ThreadPoolTaskExecutor` uses direct handoff (`SynchronousQueue`), buffering no waiting tasks like a regular queue. This readily spawns non-core threads up to max during bursts, yet also rejects readily once max workers are all busy.

A positive `queueCapacity` typically creates a bounded queue. An overly large queue absorbs short bursts but increases wait times, memory retention, and completion latency. An unbounded queue risks memory exhaustion and renders `maxPoolSize` largely ineffective.

Values "2/4/16" are purely an **illustrative configuration**, not a universal standard. Size based on arrival rate, processing duration, downstream concurrency/rate limits, and the backlog your business can tolerate.

### 5.2. Little's Law for Viewing Backlog

If the average arrival rate is `λ` events/second and each event spends `W` seconds in the system, the average work-in-progress can be modeled by `L ≈ λ × W` under appropriate steady-state conditions.

For example: 100 tasks/second with 0.2 seconds total time from enqueue to completion yields roughly 20 concurrent/in-flight tasks on average. This is a **model**; when workers fall behind, the queue grows and the system is no longer in steady state. Sizing must also account for duration distributions, bursts, retries, and shared resources.

## 6. Complete Java 17+ Example: Async Multicaster and Selective `@Async`

This example uses plain Spring Framework to demonstrate two distinct strategies:

1. `MulticasterConfig`: a `SimpleApplicationEventMulticaster` using `ThreadPoolTaskExecutor`.
2. `AnnotationAsyncConfig`: default multicaster, where only the listener annotated with `@Async("notificationExecutor")` runs on an executor.

A `ProcessingProbe` holds `CountDownLatch` instances to wait for the listener to **start**, hold it before completion, and then release it. This lets both `main` and tests prove async handoff without depending on fragile few-millisecond timings on CI machines.

The example has no broker, database, or transactions; that is intentional to make thread boundaries clear. When durable delivery is required, later sections show the extended design.

### 6.1. Project Structure

~~~text
spring-event-executor-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   └── java/
    │       └── demo/
    │           └── AsyncEventExecutorDemo.java
    └── test/
        └── java/
            └── demo/
                └── AsyncEventExecutorDemoTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'spring-event-executor-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
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
    implementation 'org.springframework:spring-context:6.2.15'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

application {
    mainClass = 'demo.AsyncEventExecutorDemo'
}

test {
    useJUnitPlatform()
}
~~~

`spring-context` supplies `AnnotationConfigApplicationContext`, `@EventListener`, and `@EnableAsync` support through Spring dependencies. The example pins Spring 6.2.15 for a concrete baseline; when using Spring Boot, prefer Boot's dependency management/BOM rather than manually pinning mixed Spring versions.

### 6.2. Complete Java File

Save **`src/main/java/demo/AsyncEventExecutorDemo.java`**:

~~~java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.ApplicationEventMulticaster;
import org.springframework.context.event.EventListener;
import org.springframework.context.event.SimpleApplicationEventMulticaster;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public final class AsyncEventExecutorDemo {

    private AsyncEventExecutorDemo() {}

    public record OrderPlaced(String orderId) {}
    public record FailingSignal() {}

    public static final class ProcessingProbe {
        private final CountDownLatch started = new CountDownLatch(1);
        private final CountDownLatch release = new CountDownLatch(1);
        private final CountDownLatch finished = new CountDownLatch(1);
        private final AtomicInteger processed = new AtomicInteger();
        private final AtomicReference<String> workerThread =
                new AtomicReference<>("");

        public void handle(OrderPlaced event) {
            workerThread.set(Thread.currentThread().getName());
            started.countDown();

            try {
                if (!release.await(8, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "Probe was not released");
                }
                processed.incrementAndGet();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(
                        "Probe interrupted", ex);
            } finally {
                finished.countDown();
            }
        }

        public boolean awaitStarted(long seconds)
                throws InterruptedException {
            return started.await(seconds, TimeUnit.SECONDS);
        }

        public boolean awaitFinished(long seconds)
                throws InterruptedException {
            return finished.await(seconds, TimeUnit.SECONDS);
        }

        public void release() {
            release.countDown();
        }

        public int processedCount() {
            return processed.get();
        }

        public String workerThread() {
            return workerThread.get();
        }
    }

    // Used in MulticasterConfig and SynchronousConfig.
    public static final class OrdinaryListener {
        private final ProcessingProbe probe;

        public OrdinaryListener(ProcessingProbe probe) {
            this.probe = probe;
        }

        @EventListener
        public void onOrderPlaced(OrderPlaced event) {
            probe.handle(event);
        }
    }

    // Only used in AnnotationAsyncConfig.
    public static class AnnotatedAsyncListener {
        private final ProcessingProbe probe;

        public AnnotatedAsyncListener(ProcessingProbe probe) {
            this.probe = probe;
        }

        @EventListener
        @Async("notificationExecutor")
        public void onOrderPlaced(OrderPlaced event) {
            probe.handle(event);
        }
    }

    public static final class ErrorProbe {
        private final CountDownLatch observed = new CountDownLatch(1);
        private final AtomicInteger count = new AtomicInteger();

        public void record(Throwable error) {
            count.incrementAndGet();
            observed.countDown();
        }

        public boolean awaitError(long seconds)
                throws InterruptedException {
            return observed.await(seconds, TimeUnit.SECONDS);
        }

        public int errorCount() {
            return count.get();
        }
    }

    public static final class FailingListener {
        @EventListener
        public void fail(FailingSignal event) {
            throw new IllegalStateException("simulated listener failure");
        }
    }

    private static ThreadPoolTaskExecutor boundedExecutor(String prefix) {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setKeepAliveSeconds(30);
        executor.setThreadNamePrefix(prefix);
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(10);
        return executor;
    }

    @Configuration(proxyBeanMethods = false)
    public static class MulticasterConfig {
        @Bean
        public ProcessingProbe processingProbe() {
            return new ProcessingProbe();
        }

        @Bean("eventTaskExecutor")
        public ThreadPoolTaskExecutor eventTaskExecutor() {
            return boundedExecutor("spring-events-");
        }

        // Special bean name looked up by ApplicationContext.
        @Bean(name = "applicationEventMulticaster")
        public ApplicationEventMulticaster applicationEventMulticaster(
                @Qualifier("eventTaskExecutor")
                ThreadPoolTaskExecutor executor) {
            SimpleApplicationEventMulticaster multicaster =
                    new SimpleApplicationEventMulticaster();
            multicaster.setTaskExecutor(executor);
            return multicaster;
        }

        @Bean
        public OrdinaryListener ordinaryListener(ProcessingProbe probe) {
            return new OrdinaryListener(probe);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class SynchronousConfig {
        @Bean
        public ProcessingProbe processingProbe() {
            return new ProcessingProbe();
        }

        // No custom multicaster declared: synchronous by default.
        @Bean
        public OrdinaryListener ordinaryListener(ProcessingProbe probe) {
            return new OrdinaryListener(probe);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync(proxyTargetClass = true)
    public static class AnnotationAsyncConfig {
        @Bean
        public ProcessingProbe processingProbe() {
            return new ProcessingProbe();
        }

        @Bean("notificationExecutor")
        public ThreadPoolTaskExecutor notificationExecutor() {
            return boundedExecutor("notify-");
        }

        @Bean
        public AnnotatedAsyncListener annotatedAsyncListener(
                ProcessingProbe probe) {
            return new AnnotatedAsyncListener(probe);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class ErrorConfig {
        @Bean
        public ErrorProbe errorProbe() {
            return new ErrorProbe();
        }

        @Bean("errorExecutor")
        public ThreadPoolTaskExecutor errorExecutor() {
            return boundedExecutor("error-");
        }

        @Bean(name = "applicationEventMulticaster")
        public ApplicationEventMulticaster applicationEventMulticaster(
                @Qualifier("errorExecutor")
                ThreadPoolTaskExecutor executor,
                ErrorProbe errors) {
            SimpleApplicationEventMulticaster multicaster =
                    new SimpleApplicationEventMulticaster();
            multicaster.setTaskExecutor(executor);
            multicaster.setErrorHandler(errors::record);
            return multicaster;
        }

        @Bean
        public FailingListener failingListener() {
            return new FailingListener();
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             MulticasterConfig.class)) {

            ProcessingProbe probe =
                    context.getBean(ProcessingProbe.class);

            context.publishEvent(new OrderPlaced("ORD-42"));

            try {
                if (!probe.awaitStarted(5)) {
                    throw new IllegalStateException(
                            "Listener did not start");
                }

                // publishEvent already returned; handler is still awaiting release.
                System.out.println("publisher.returned=true");
                System.out.println(
                        "listener.uses.executor="
                        + probe.workerThread().startsWith("spring-events-"));
                System.out.println(
                        "processed.before.release=" + probe.processedCount());
            } finally {
                probe.release();
            }

            if (!probe.awaitFinished(5)) {
                throw new IllegalStateException(
                        "Listener did not finish");
            }

            System.out.println(
                    "processed.after.release=" + probe.processedCount());
        }
    }
}
~~~

### 6.3. Code Analysis and Correctness

`ProcessingProbe` intentionally holds the listener on a `CountDownLatch`. It signals that it has started and waits for `release`. Since `main` only calls `awaitStarted` **after `publishEvent` returns**, if `main` reaches this point while the listener is still waiting for release, we know the publisher did not wait for the handler to finish.

- `MulticasterConfig` attaches the executor to `SimpleApplicationEventMulticaster`. `OrdinaryListener` **does not have** `@Async`, yet still runs on a worker.
- `SynchronousConfig` omits the custom multicaster; the same `OrdinaryListener` runs synchronously on the publisher thread.
- `AnnotationAsyncConfig` keeps the default multicaster but marks the method with `@Async("notificationExecutor")`; `@EnableAsync` is needed to create proxies. `proxyTargetClass=true` enables CGLIB proxying for a class without an interface.
- `ErrorConfig` uses an `ErrorHandler` to capture exceptions thrown by handlers executed on workers by the multicaster, so errors are not lost in the demo's error path.
- `boundedExecutor(...)` returns the executor for Spring container management; each context gets its own executor and shuts it down when the context closes.
- `finally` in `main` ensures release even if an assertion/timing check fails in the demo.

To keep the illustrative code concise, `ProcessingProbe` does not inspect the order ID and does not connect to real business logic. In a real application, listeners process event data with an error policy; latches belong only in tests, never to block production workers en masse.

### 6.4. Running and Expected stdout

Inside `spring-event-executor-demo`, with JDK 17+ and Gradle:

~~~bash
gradle -q run
~~~

If using the Gradle Wrapper, you can run `./gradlew -q run` (Linux/macOS) or `gradlew.bat -q run` (Windows).

Lines explicitly printed by `main` if the listener starts and completes successfully:

~~~text
publisher.returned=true
listener.uses.executor=true
processed.before.release=0
processed.after.release=1
~~~

This is **expected logical output**, not stdout captured from an executed build in the lesson's environment. Task pickup timing depends on scheduling and system load; therefore the example uses a 5-second timeout instead of asserting the event starts in exactly 10 ms.

If tasks are starved, the machine is overloaded, or setup fails, the program may throw an exception and fail to print all four lines. Tests must never treat any timeout error as success.

## 7. JUnit 5: Four Controlled Tests

Create **`src/test/java/demo/AsyncEventExecutorDemoTest.java`**:

~~~java
package demo;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AsyncEventExecutorDemoTest {

    @Test
    @Timeout(15)
    void multicasterAsyncHandoffCompletesAfterRelease()
            throws InterruptedException {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             AsyncEventExecutorDemo.MulticasterConfig.class)) {

            var probe = context.getBean(
                    AsyncEventExecutorDemo.ProcessingProbe.class);

            context.publishEvent(
                    new AsyncEventExecutorDemo.OrderPlaced("A"));

            try {
                assertTrue(probe.awaitStarted(5));
                assertEquals(0, probe.processedCount());
                assertTrue(probe.workerThread()
                        .startsWith("spring-events-"));
            } finally {
                probe.release();
            }

            assertTrue(probe.awaitFinished(5));
            assertEquals(1, probe.processedCount());
        }
    }

    @Test
    @Timeout(15)
    void defaultMulticasterWaitsForListenerToFinish() throws Exception {
        ExecutorService publisherThread =
                Executors.newSingleThreadExecutor();

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             AsyncEventExecutorDemo.SynchronousConfig.class)) {

            var probe = context.getBean(
                    AsyncEventExecutorDemo.ProcessingProbe.class);

            Future<?> publication = publisherThread.submit(() ->
                    context.publishEvent(
                            new AsyncEventExecutorDemo.OrderPlaced("B")));

            try {
                assertTrue(probe.awaitStarted(5));

                // The publish call on the separate thread is still waiting.
                assertFalse(publication.isDone());
            } finally {
                probe.release();
            }

            publication.get(5, TimeUnit.SECONDS);
            assertEquals(1, probe.processedCount());
        } finally {
            publisherThread.shutdownNow();
        }
    }

    @Test
    @Timeout(15)
    void annotationAsyncUsesNamedExecutor() throws InterruptedException {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             AsyncEventExecutorDemo.AnnotationAsyncConfig.class)) {

            var probe = context.getBean(
                    AsyncEventExecutorDemo.ProcessingProbe.class);

            // Default multicaster; only this listener has @Async.
            context.publishEvent(
                    new AsyncEventExecutorDemo.OrderPlaced("C"));

            try {
                assertTrue(probe.awaitStarted(5));
                assertTrue(probe.workerThread().startsWith("notify-"));
                assertEquals(0, probe.processedCount());
            } finally {
                probe.release();
            }

            assertTrue(probe.awaitFinished(5));
            assertEquals(1, probe.processedCount());
        }
    }

    @Test
    @Timeout(15)
    void asyncListenerFailureGoesToMulticasterErrorHandler()
            throws InterruptedException {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             AsyncEventExecutorDemo.ErrorConfig.class)) {

            var errors = context.getBean(
                    AsyncEventExecutorDemo.ErrorProbe.class);

            // Do not expect the worker exception to propagate back to the caller.
            context.publishEvent(
                    new AsyncEventExecutorDemo.FailingSignal());

            assertTrue(errors.awaitError(5));
            assertEquals(1, errors.errorCount());
        }
    }
}
~~~

Run:

~~~bash
gradle test
~~~

### 7.1. What Is Verified

| Test | What is verified | What must not be inferred |
| --- | --- | --- |
| `multicasterAsyncHandoffCompletesAfterRelease` | Multicaster submits and worker is still waiting when publish returns | Task committed external side effects |
| `defaultMulticasterWaitsForListenerToFinish` | Without executor, publisher thread waits for listener release | The entire system only has one publisher thread |
| `annotationAsyncUsesNamedExecutor` | `@Async` runs on executor named `notificationExecutor` | Every other listener automatically runs async |
| `asyncListenerFailureGoesToMulticasterErrorHandler` | Error from callback run via async multicaster is recorded by `ErrorHandler` | `@Async` errors thrown later by proxies also pass through the same handler |

The sync test intentionally runs the publisher on a test-owned thread so the test method can still control the latch. It is **not** how sync events are configured in production. Latches and timeouts avoid absolute-time assertions, yet still require enough CI resources for workers to be scheduled.

### 7.2. Why Not Assert Milliseconds?

A test asserting `publishEvent` takes less than 5 ms can fail on slow CI even when async semantics are correct. Conversely, a low 200 ms sleep does not guarantee the handler ran. A latch verifies **relative ordering in time**: the handler started but had not finished when the caller continued.

To evaluate real performance, use appropriate load tests/JFR/JMH collecting p50/p95/p99, queue wait, and completion latency under representative load.

## 8. Sizing the Executor for the Workload

### 8.1. Distinguishing CPU-Bound and I/O-Bound

**CPU-bound** work such as cryptography or large data transformations generally does not benefit from scaling workers far beyond available CPUs. **I/O-bound** work such as waiting on HTTP/DB may need higher concurrency, but must account for connection pool limits, remote API rate limits, and memory.

Initial configuration is not a rigid formula. Measure:

- Arrival rate: how many events/sec enter the pipeline?
- Average, p95/p99 handler time.
- Number of destinations and length of each dependent step.
- Available DB connections / HTTP connections.
- Queue capacity and maximum acceptable backlog.
- Retry, timeout, and rejected task rates.
- End-to-end SLA, not just publish duration.

### 8.2. How the Queue Acts Before Max Threads

With pool core=2/max=4/queue=16:

~~~text
1..2 concurrent tasks:
    core threads can take them

core busy, queue has room:
    new task queues up, does not necessarily create a 3rd worker

queue full:
    executor can scale up to 3rd, 4th worker

pool=4 busy, queue=16 full:
    new task is rejected per policy
~~~

This explains why `core=2,max=32,queue=100000` may use only 2 workers most of the time and build up a very long waiting queue. Do not treat `maxPoolSize` as always-available concurrency.

### 8.3. Multiple Listeners: One Pool or Multiple Pools?

One event can trigger inventory, billing, email, and analytics. If all share a single executor, one stalled listener group can starve the others of workers.

Options:

- **One shared pool** when workloads are similar, share priority, and share failure domains.
- **Separate pools** by critical side-effect type when isolation is needed (for example, email I/O vs. analytics CPU).
- **Explicit pipeline/workflow** when one handler must wait for another handler's output.
- **Broker/job table/outbox** when durable queues, retries, and cross-process scheduling are required.

Do not create unbounded executors per listener; every pool consumes threads, memory, and connections. Split pools based on isolation and monitoring needs, not merely class names.

## 9. Rejection Policies and Backpressure

When an executor saturates, choose an explicit contract:

| Policy / handling approach | Behavior | Risk |
| --- | --- | --- |
| `AbortPolicy` | Rejects task; Spring may wrap in `TaskRejectedException` | Caller must handle the error; ignoring it can lose work |
| `CallerRunsPolicy` | Submitting thread may execute the task | Publisher unexpectedly waits on handler, spiking p99 |
| `DiscardPolicy` | Silently drops task | Silent event loss without signal; usually unsuitable |
| `DiscardOldestPolicy` | Drops oldest queued task | Breaks ordering and completeness of work |
| Producer rate limiting | Throttles traffic upstream of executor | Needs clear reject/backpressure APIs |
| Persisted work/outbox | Persists first, then workers process at capacity | Higher complexity; requires retries/idempotency |

**Specific note on errors:** `SimpleApplicationEventMulticaster#setErrorHandler` handles exceptions from listeners invoked by the multicaster, whereas **task submission rejection** happens when calling `executor.execute(...)` and is not necessarily covered by a listener error handler. Test the queue-saturation path explicitly to see how errors return to the publisher.

An application must never switch to `DiscardPolicy` just so dashboards stop showing rejections. That hides lost work rather than improving reliability.

### 9.1. Retries Must Not Be Unbounded

When a dependency fails, retrying immediately on the same executor increases load and holds workers longer. If retries are needed:

- Choose which errors are retryable.
- Use exponential backoff with jitter and a maximum attempt limit.
- Set a timeout on every attempt.
- Use an idempotency key when side effects could run repeatedly.
- Monitor retry backlog, age, and eventual outcomes.
- Route unrecoverable work to a dead-letter/quarantine path per policy.

With an in-process async executor, if the process crashes before a retry, the task can still be lost. Do not assume a retry loop creates durability.

## 10. Multicaster `ErrorHandler` vs. `AsyncUncaughtExceptionHandler`

Two distinct error paths:

### 10.1. Async Multicaster

An ordinary listener:

~~~java
@EventListener
public void handle(OrderPlaced event) {
    if (shouldFail(event)) {
        throw new IllegalStateException("business listener failed");
    }
}
~~~

When the multicaster submits this method call to a worker, exceptions thrown by the method can be handled by `SimpleApplicationEventMulticaster#setErrorHandler(...)`:

~~~java
multicaster.setErrorHandler(error -> {
    errorMetrics.increment();
    safeLogger.error("Event listener failed", error);
});
~~~

These snippets are **illustrative**, requiring beans and metrics/logger implementations. If the handler swallows exceptions, the publisher may remain unaware of failures; critical tasks need dedicated retry/ack semantics.

In the `ErrorConfig` demo, `ErrorProbe` records the error without printing event payloads and the test waits for the callback. `ErrorHandler` does not replace a retry/dead-letter system.

### 10.2. `@Async` on a Listener

When Spring's async proxy executes an `@Async` method returning `void` on a worker, exceptions do not propagate directly back to the caller. Spring provides `AsyncUncaughtExceptionHandler` for this case.

Standalone configuration example:

~~~java
@Configuration
@EnableAsync
public class AsyncErrorConfig implements AsyncConfigurer {

    @Override
    public AsyncUncaughtExceptionHandler
            getAsyncUncaughtExceptionHandler() {
        return (ex, method, params) -> {
            // Record metric/safe log; do not print raw params containing PII.
            auditError(ex.getClass().getSimpleName());
        };
    }
}
~~~

This is an **illustrative snippet** requiring imports for `AsyncConfigurer`, `AsyncUncaughtExceptionHandler`, and an `auditError` implementation; it is not part of the Section 6 runnable files. With `Future`/`CompletableFuture`, errors can be observed via the resulting future rather than the uncaught handler.

**Do not assume a multicaster `ErrorHandler` catches every exception thrown later inside an `@Async` proxy.** Test the exact error path you use.

### 10.3. Publisher Outcome Differs from Handler Outcome

~~~text
publishEvent returned normally
      |
      +--> task queued
             |
             +--> worker runs
                    |
                    +--> handler throws
~~~

`publishEvent` returning without error in this situation does not mean the handler succeeded. If business logic requires a response based on the side-effect outcome, change the contract explicitly: await completion/future or use a stateful workflow rather than returning "email sent" right after handoff.

## 11. `@Order`, Dependent Listeners, and Concurrency

`@Order` can determine **dispatch/invocation** order within the same phase. With a multi-worker executor, it **does not guarantee completion order**.

Example:

~~~text
@Order(10) Inventory    |---- 120 ms ----|
@Order(20) Billing      |--  40 ms --|
@Order(30) Notification |------ 200 ms ------|

Billing may finish before Inventory.
~~~

If Billing needs Inventory's result, do not just add `@Order` and enable async. Instead:

- Combine steps with mandatory dependencies into explicit service orchestration.
- Use `CompletableFuture`/structured completion with timeouts if within the same process.
- Use a state machine/outbox/broker with sequence/versioning when workflows are long-lived or must be durable.
- When ordering per aggregate is needed, use appropriate serialization or partition keys rather than relying on thread-pool scheduling.

One event having three listeners does not mean three threads are guaranteed. The pool may have only one worker or two busy workers; completion time depends on queuing, concurrency, and shared resources.

## 12. `@TransactionalEventListener`: An Important Exception

Spring Framework 6.1+ includes `ApplicationListener.supportsAsyncExecution()`. `TransactionalApplicationListener` instances must register transaction synchronization **on the thread associated with the transaction**, so they do not support async dispatch at the multicaster for that registration step. Their target processing can still have its own async mechanism, without bypassing the lifecycle phase.

Example:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderPlaced event) {
    emailService.send(event.orderId());
}
~~~

This snippet is illustrative, requiring beans, a transaction manager, and an event class.

With imperative JDBC/JPA transactions:

- The transaction context is typically bound to the thread via `TransactionSynchronizationManager`.
- When `publishEvent` runs inside a transaction, transaction-bound listeners must register callbacks in the right place.
- `AFTER_COMMIT` fires only after a successful commit; on rollback, this callback does not run.
- A normal `AFTER_COMMIT` callback can still run on the thread completing the transaction and **still block the request**.
- Without an active transaction and with `fallbackExecution=false`, transaction-bound listeners are not invoked.
- Accessing the database or performing side effects inside `AFTER_COMMIT` requires its own transaction semantics; for new writes, `REQUIRES_NEW` via a proper proxy is usually needed.

**Adding an executor to the multicaster is no guarantee every transactional listener will run async.** This is one reason to test transaction behavior after changing configuration.

### 12.1. Combining `@Async` with a Transactional Listener

Some designs place `@Async` on a `@TransactionalEventListener` method so the target listener runs on a worker after synchronization triggers. However:

- Phase registration must be confirmed on the transaction thread.
- Async execution may no longer have the original transaction `ThreadLocal`.
- A worker exception does not roll back the already-committed transaction.
- If DB writes are needed, open a new transaction and test it.
- Do not make transaction success/failure decisions depend on an unfinished async task.

When strict correctness is required, an outbox or persisted job is usually more reliable than combining annotations without testing crash/retry scenarios.

### 12.2. Reactive Transactions

Reactive transactions use Reactor Context rather than thread-local JDBC context. Spring provides `TransactionalEventPublisher` so events carry the appropriate transaction context. Do not use a JDBC `TransactionTemplate` example and claim it verifies an R2DBC reactive path.

When handling events reactively, distinguish a `Mono` being **created** from a `Mono` being **subscribed/completed**. A listener returning a `Mono` that Spring does not subscribe to produces no real side effect. Use reactive transaction operators/`StepVerifier` in appropriate tests.

## 13. `@EnableAsync`, AOP Proxies, and Self-Invocation Pitfalls

A selective configuration:

~~~java
@Configuration
@EnableAsync
class AsyncSupport {

    @Bean("notificationExecutor")
    ThreadPoolTaskExecutor notificationExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(50);
        executor.setThreadNamePrefix("notification-");
        return executor;
    }
}
~~~

Listener:

~~~java
@Component
class NotificationListener {

    @Async("notificationExecutor")
    @EventListener
    public void onOrderPlaced(OrderPlaced event) {
        sendNotification(event);
    }
}
~~~

Both snippets are **illustrative**, requiring imports/beans and a `sendNotification` method. `@EnableAsync` turns on async annotation support. For a method to execute through a proxy, use a public method on a Spring-managed bean invoked externally through the proxy; if the same bean calls `this.asyncMethod(...)` directly, self-invocation bypasses standard Spring AOP proxies.

When multiple executors exist, always specify `@Async("notificationExecutor")` (bean name/qualifier) rather than relying on an arbitrary pool selection. If no matching executor exists or the bean is not Spring-managed, the application may fall back unexpectedly or not run async as you thought.

An `@Async @EventListener` callback cannot emit a new event via its **return value** the way a synchronous `@EventListener` can; to publish a follow-up event, inject `ApplicationEventPublisher` and call `publishEvent` explicitly. Handle errors and completion for that step separately.

## 14. Context Propagation: Trace, MDC, Security, and Transactions

In a synchronous listener, the publisher's thread-local MDC and current trace context usually remain on the same thread. When handing off to a worker:

~~~text
request thread:
   MDC["requestId"] = req-123
   publish event
   return

event executor worker:
   MDC["requestId"] = ?  (usually not present automatically)
~~~

Do not pass an entire `ThreadLocal` or `SecurityContext` manually via a global mutable map, because worker threads are reused and can leak context across users.

Spring provides `TaskDecorator` to wrap runnables on an executor. With `ContextPropagatingTaskDecorator` and properly configured Micrometer Context Propagation, supported contexts can be snapshotted and restored:

~~~java
@Bean("eventTaskExecutor")
ThreadPoolTaskExecutor eventTaskExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(32);
    executor.setTaskDecorator(
            new ContextPropagatingTaskDecorator());
    return executor;
}
~~~

This is an **illustrative variant**, not to be added directly to the Gradle demo; it requires `org.springframework.core.task.support.ContextPropagatingTaskDecorator` and a matching `io.micrometer:context-propagation` dependency. Context propagation helps supported scopes/logs/traces, **grants no new permissions**, does not guarantee valid authentication/authorization for every downstream call, and **does not carry an open JDBC transaction across to a worker thread**.

If an event needs a business correlation ID to survive restarts/queues/brokers, put that ID into an immutable event context or outbox record, not only MDC. After the worker finishes, context must be cleaned up/restored so data does not leak into the next task.

## 15. Graceful Shutdown and Safe Deployments

A subtle bug: the application receives an event, submits a task, and shuts down before the task finishes. If the in-process executor has not drained its queue, work is lost.

`ThreadPoolTaskExecutor` has lifecycle settings:

- `setWaitForTasksToCompleteOnShutdown(true)`: attempts to let accepted tasks finish instead of canceling immediately.
- `setAwaitTerminationSeconds(n)`: bounded wait time during container shutdown.
- Thread name prefixes help inspect still-running tasks in logs and thread dumps.
- Spring 6.2's context lifecycle/phases affect when stop/close occur; test with your application's exact configuration.

**Do not equate a shutdown hook with durable processing.** A process can be `kill -9`'d, crash, OOM, or lose power with no chance to drain the queue. If the business cannot tolerate losing events, persist the work before returning success.

### 15.1. Rolling Restart Deployments

When running on Kubernetes or another orchestrator:

1. Stop accepting new work according to readiness/traffic policy.
2. Allow workers to drain already-accepted queue items within the grace period.
3. Track metrics for active, queued, and rejected tasks.
4. For tasks exceeding the grace period, rely on a durable work store to recover.
5. Avoid infinite stop timeouts that can stall deployments.
6. Account for messages sent before ACK/mark-done; idempotency is needed so side effects do not execute twice.

With only an in-memory executor, zero-loss cannot be promised on forced container termination.

## 16. Observing Async Executors and Listener Latency

### 16.1. Metrics to Separate

| Metric | Question answered |
| --- | --- |
| `app.event.publish.duration` | How long did the `publishEvent` call take? |
| `app.event.handler.duration` | How long did each handler take? |
| `app.event.handler.outcome` | How many times did the handler succeed/fail? |
| `app.event.start.delay` | Time from event creation until the handler started? |
| `app.event.executor.queue.depth` | How many tasks are waiting? |
| `app.event.executor.active` | How many workers are busy? |
| `app.event.executor.rejected` | How many tasks were rejected? |
| `app.event.business.complete` | How long until the side effect is confirmed? |

These are **suggested application metric names**, not all emitted automatically by Spring Framework. `ThreadPoolTaskExecutor` exposes indicators such as `getActiveCount()`, `getPoolSize()`, and `getThreadPoolExecutor().getQueue().size()` for observation when accessing the bean with compatible APIs.

Micrometer `Timer` fits durations, while `Counter` fits occurrences. Example:

~~~java
Timer.Sample sample = Timer.start(registry);
String outcome = "success";

try {
    handler.process(event);
} catch (RuntimeException ex) {
    outcome = "error";
    throw ex;
} finally {
    sample.stop(Timer.builder("app.event.handler.duration")
            .tag("handler", "notification")
            .tag("outcome", outcome)
            .register(registry));
}
~~~

This is an **illustrative snippet** requiring the Micrometer dependency, a `MeterRegistry`, and a real handler; it is not in the Section 6 Gradle demo. Instrument inside the handler body, not only around `publishEvent`.

### 16.2. Queue Wait Differs from Start Delay

If a timestamp is captured when the event is created, `handlerStart - eventCreated` includes several components: payload creation, dispatch, enqueueing, queue wait, and possibly transaction waiting. It is **not pure queue wait**.

For accurate queue wait, instrument the executor from when the task is enqueued (at a well-defined measurement point) until just when a worker begins executing it. Across process boundaries, never pass `System.nanoTime()` between JVMs to compute durations because monotonic clocks are not synchronized.

### 16.3. Tags and Cardinality

Do not put `eventId`, `orderId`, `userId`, `email`, trace ID, or payloads into metric tags. Use `event_type`, `handler`, `outcome`, and `error_kind` with bounded value sets. IDs belong in structured logs/traces subject to data, redaction, access-control, and retention policies.

### 16.4. Dashboards and Alerts

Monitor together:

- Publisher p95/p99 and request p95/p99.
- Handler p95/p99 by listener name.
- Queue depth and rejection rate.
- End-to-end completion latency.
- Counts of succeeded, failed, and retried tasks.
- DB pool/HTTP connections and downstream error rates.

If publishing is fast while queue depth grows steadily, processing cannot keep up. If the queue is empty while handler p99 spikes, check slow dependencies or locks. If rejections rise, handle overload rather than endlessly growing the pool.

## 17. Data Security in Asynchronous Queues

An async executor can hold event objects in memory longer than a synchronous listener. Therefore:

- Do not pass raw `HttpServletRequest`, large JPA entities, or mutable object graphs.
- Do not pass passwords, access tokens, session cookies, or raw PII if the listener does not truly need them.
- Prefer immutable event records containing permitted business IDs and minimal attributes.
- If a listener needs a real ID to call a service, enforce authorization and data classification, and never log the full event.
- Do not put sensitive identifiers into thread names or metric tags.
- Do not send a request's `SecurityContext` to workers in ways that expose privileges after the request ends.
- Bound queue capacity to prevent memory retention and GC pressure from large payloads.
- When using a broker/DLQ/outbox, metadata and payloads can persist for days; design encryption, retention, and ACLs accordingly.

An `@Async` method with a `void` return does not automatically create an error channel or audit record. For critical work, build an explicit outcome-recording path instead of merely logging exceptions.

## 18. Async Executor vs. Outbox: Choosing by Reliability

| Requirement | In-memory async executor | Durable outbox/queue |
| --- | --- | --- |
| Offload thread for fast publisher | Yes | Possible, via post-commit worker |
| Work survives JVM crash | Not guaranteed | Yes, if persisted and designed properly |
| Retries after restart | Not built-in | Can be built from storage |
| DLQ/replay | Not built-in | Possible |
| Long-term backlog tracking | In-memory only | Backed by durable data |
| Transactional with domain DB | No atomicity with task enqueue | Outbox row commits with domain row |
| At-least-once delivery | Not guaranteed | Can be designed; needs idempotency |
| Exactly-once side effect | No | Not automatic either; requires domain idempotency |
| Complexity | Lower | Higher |

An outbox workflow:

~~~text
Domain transaction:
   INSERT business row
   INSERT outbox work item (same transaction)
   COMMIT
       |
       v
Outbox worker:
   claim pending item
   execute side effect
   record outcome / retry
   ACK / mark done
~~~

Even though an outbox prevents losing work between commit and send, a worker can still crash **after the side effect but before ACK**. Consumers/side effects must therefore be idempotent or support reconciliation. Never treat an outbox as automatic "exactly once".

An in-process async executor still fits lightweight cache refreshes, prefetching, or best-effort analytics when losing a task on crash is acceptable. State that reliability level explicitly in the design.

## 19. Common Configuration Mistakes

| Symptom | Likely cause | How to check/fix |
| --- | --- | --- |
| Listener still runs on request thread | Wrong multicaster bean name, missing executor, or listener does not support async | Check bean name and `supportsAsyncExecution()` |
| `@Async` has no effect | Missing `@EnableAsync`, non-Spring bean, self-invocation | Enable annotation support, invoke via proxy |
| Spring picks wrong executor | Multiple pools without qualifier | Use `@Async("notificationExecutor")` |
| Only 2 workers active despite max=32 | Queue still has room or is unbounded | Review core/queue/max semantics |
| Publishing suddenly slows under high load | `CallerRunsPolicy` makes caller execute tasks | Check rejection policy and saturation |
| Events disappear when queue fills | Discard policy or swallowed exceptions | Reject explicitly / persist work |
| Listener completions out of order | Multi-worker scheduling gives no completion order | Use workflow/ordering contract |
| Listener fails but publisher throws nothing | Exception on async worker | Configure `ErrorHandler`/`AsyncUncaughtExceptionHandler` and outcome metrics |
| `@TransactionalEventListener` skipped | Published outside transaction, wrong phase, or incompatible thread/context | Test transaction synchronization and commit/rollback |
| Same listener enqueued twice | Async configured on both multicaster and proxy, or duplicate publish | Count invocations, clarify ownership, idempotency |
| MDC/trace lost after async | Context not propagated | `TaskDecorator`/context propagation |
| Traces full of PII | Unfiltered baggage or logged event payloads | Data minimization/redaction |
| Tasks lost on shutdown | Missing grace period or blocked tasks | Test lifecycle and recovery |
| Oversized pool overloads DB | Concurrency exceeds connection/rate limits | Shrink pool, apply backpressure, optimize |
| JUnit flaky after waiting 20 ms | Using sleep instead of completion signals | Latch/future with timeout |
| Publish timer low yet request still slow | Transaction commit or other synchronous work | Trace the full critical path |
| Publish timer low yet emails arrive late | Queue backlog or downstream latency | Measure start delay, handler duration, E2E |
| `TaskExecutor` bean closed early | Manual creation/shutdown or wrong scope | Let Spring manage lifecycle |
| Async event has multiple subscribers and count expected to equal publishes | One event can trigger multiple handlers | Count by event type + handler + outcome |
| Works locally but loses events on restart | In-memory queue is not durable | Outbox/job table/broker |

## 20. Implementation Checklist and Practice Exercises

### Pre-Merge Checklist

- [ ] Identified which listeners are genuinely allowed to run async.
- [ ] Chosen **one place** to split threads: multicaster or deliberate `@Async`.
- [ ] Custom multicaster has exact bean name `applicationEventMulticaster`.
- [ ] `@EnableAsync` is enabled when using `@Async`.
- [ ] `@Async` methods are Spring-managed, public/proxy-invocable, and use the right executor qualifier.
- [ ] Core/max/queue capacity and rejection policy sized for workload.
- [ ] Queue is bounded and does not silently discard critical tasks.
- [ ] Dedicated exception handling configured for multicaster and annotation async paths.
- [ ] Never expect async exceptions to return to the publisher for rollback.
- [ ] Checked `@TransactionalEventListener`, phases, thread context, and `REQUIRES_NEW` if writing DB after commit.
- [ ] Do not rely on `@Order` to guarantee async completion order.
- [ ] ThreadLocal/MDC/security/trace contexts propagated per policy.
- [ ] Graceful shutdown has a timeout; durable storage used when work cannot be lost.
- [ ] Metrics cover queue depth, active workers, rejections, handler duration/outcome, and E2E.
- [ ] Event payloads exclude secrets and unnecessary PII.
- [ ] JUnit uses latches/futures to test behavior rather than absolute timing.
- [ ] Load tested before/after with representative workloads and verified business correctness.

### Exercise 1 — Full Queue

Try core=1, max=1, queue=1 with three blocked tasks. Use latches to hold the worker and queued task, and verify a new submission is rejected. Distinguish submission-time exceptions from exceptions thrown by listener logic.

### Exercise 2 — `CallerRunsPolicy`

Change `AbortPolicy` to `CallerRunsPolicy` in a separate test. When the pool and queue saturate, confirm the new task can run on the publisher thread and block `publishEvent`. Explain why publish p99 can spike sharply under overload.

### Exercise 3 — Transaction-Bound Listener

Create a real JDBC transaction, publish `OrderPlaced` inside `TransactionTemplate`, and use an `AFTER_COMMIT` listener. Verify the listener does not run before commit and does not run after rollback. Compare behavior when the custom multicaster has an executor.

### Exercise 4 — Async Failure

Write an `AsyncUncaughtExceptionHandler` for `@Async @EventListener void` and test capturing errors via a latch. Compare with `SimpleApplicationEventMulticaster#setErrorHandler` in the main example.

### Exercise 5 — Context Propagation

Use `ContextPropagatingTaskDecorator` with Micrometer Context Propagation to transfer a supported trace/log context to workers. Verify the context does not linger on the next task. Do not try to propagate a JDBC transaction `ThreadLocal` as a way to span transactions across threads.

### Exercise 6 — Outbox

Create a job table in H2 or PostgreSQL, insert both the job and order in the same transaction, intentionally kill the worker, and restart. Confirm pending jobs remain, with retries and idempotency. Compare reliability with an in-memory queue.

### Exercise 7 — Performance

Run 1,000 events at varying concurrency levels; measure p95/p99 publish and listener completion times, queue length, and DB pool wait. Base pool/queue sizing on data rather than single-event duration.

## 21. Self-Check Questions

**Q1.** Does calling `setTaskExecutor` on `SimpleApplicationEventMulticaster` require `@EnableAsync`?

**Answer:** No. `@EnableAsync` serves annotation-driven `@Async`; the multicaster can submit directly to the executor.

**Q2.** Does `@Async("notificationExecutor")` make every listener run in the background automatically?

**Answer:** No. It applies to the annotated method when invoked via proxy; other listeners keep their own execution model.

**Q3.** Core=2, max=20, queueCapacity=10000. Why does the application rarely use more than 2 workers?

**Answer:** `ThreadPoolExecutor` prioritizes enqueueing once core threads are busy; it spawns non-core threads only when the queue is full, so max does not mean immediate concurrency.

**Q4.** When the pool/queue are full and `CallerRunsPolicy` is used, is `publishEvent` guaranteed to return quickly?

**Answer:** No. The task may run directly on the caller thread, forcing the publisher to wait for the handler.

**Q5.** Why doesn't a `@TransactionalEventListener(AFTER_COMMIT)` automatically run async just because the multicaster has an executor?

**Answer:** Transaction-synchronized listeners must register synchronization in the transaction context and may decline async dispatch; phase registration and target processing are two distinct parts.

**Q6.** An `@Async` void handler throws an exception. Does the publishing caller necessarily receive that exception?

**Answer:** No. The failure occurs on the worker; handle it via an async error handler or an explicit outcome/ack mechanism.

**Q7.** Should you raise the pool to 500 workers if the database only has 20 connections?

**Answer:** Usually no; excessive concurrency increases contention, DB pool queuing, timeouts, and tail latency. Size according to dependencies.

**Q8.** When an event must reliably send an email even if the JVM crashes, is an executor enough?

**Answer:** No. Use a durable job/outbox/broker with retries, idempotency, and recovery mechanisms.

**Q9.** Is a test that sleeps 100 ms and then asserts the listener finished reliable?

**Answer:** No. Scheduling is non-deterministic; use `CountDownLatch`/`Future` or a completion signal with a timeout.

**Q10.** Async is enabled, publish duration drops to 2 ms, yet the backlog grows continuously. Can you claim the whole workflow is faster?

**Answer:** No. The producer only hands off faster; handler completion may be getting slower. Measure end-to-end latency, saturation, and error rates.

## 22. References

- Spring Framework 6.2 — Standard and Custom Events, asynchronous event listeners and `@Order`: https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html
- Spring Framework 6.2 — `SimpleApplicationEventMulticaster` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html
- Spring Framework 6.2 — `ApplicationEventPublisher` Javadoc (handoff semantics): https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Framework 6.2 — `ApplicationListener.supportsAsyncExecution()` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/context/ApplicationListener.html
- Spring Framework 6.2 — `TransactionalApplicationListener` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/transaction/event/TransactionalApplicationListener.html
- Spring Framework 6.2 — Task Execution and Scheduling, `ThreadPoolTaskExecutor` sizing and `@Async`: https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html
- Spring Framework 6.2 — `ThreadPoolTaskExecutor` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Spring Framework 6.2 — `ContextPropagatingTaskDecorator` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html
- Spring Framework — Observability and `@EventListener`: https://docs.spring.io/spring-framework/reference/integration/observability.html
- Spring Framework — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
- Micrometer — Timers: https://docs.micrometer.io/micrometer/reference/concepts/timers.html
- Micrometer — Context Propagation: https://docs.micrometer.io/context-propagation/reference/
- Java 17 — `ThreadPoolExecutor`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
- JUnit 5 — Testing framework user guide: https://junit.org/junit5/docs/current/user-guide/
