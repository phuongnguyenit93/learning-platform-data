# Synchronous Execution Default and Impact of Long-Running Listeners in Spring Boot

## 1. Why Can a "Small" Listener Slow Down the Entire Application?

In Spring Boot, **application events** are a mechanism for publishing notifications to interested components through **ApplicationEventPublisher** and **ApplicationListener/@EventListener**. By default, Spring Framework uses **SimpleApplicationEventMulticaster** and invokes listeners **synchronously on the exact thread that published the event**.

This means a **publishEvent(...)** call normally does not return immediately: it waits for all matching synchronous listeners to finish executing. A slow listener can slow down HTTP requests, hold a transaction open longer, block listeners ordered after it, or delay stages inside **SpringApplication.run(...)**.

Conceptual example:

~~~text
Publisher's thread
    |
    | publishEvent(OrderCreated)
    |
    +--> Listener A: 20 ms
    |
    +--> Listener B: 3,000 ms (calls external API)
    |
    +--> Listener C: 10 ms
    |
    | publishEvent(...) returns
    v
Publisher continues processing
~~~

The total duration of publishEvent in this scenario can exceed **3,030 ms**, depending on overhead and scheduling. There is no separate worker thread per listener unless you have configured an asynchronous mechanism.

**Important distinction:** an "event" in Spring Framework is an **in-process application notification**—it is not automatically a Kafka message, durable queue, separate transaction, or background task.

## 2. Default Execution Mechanism

When a bean has a reference to **ApplicationEventPublisher**:

~~~java
publisher.publishEvent(new OrderCreated("O-42"));
~~~

Spring accepts the event, finds matching **ApplicationListener** beans or **@EventListener** methods, and dispatches through **ApplicationEventMulticaster**. With the default configuration, SimpleApplicationEventMulticaster has no asynchronous task executor assigned. Therefore:

1. The publisher calls **publishEvent(...)** on the current thread.
2. The multicaster finds listeners matching the event type; Spring also supports arbitrary user-defined event objects (payload events), which do not need to extend ApplicationEvent.
3. The first listener finishes before the publisher moves on to the second listener in the default synchronous model.
4. Only when all listeners finish normally does the publishEvent call return.
5. If a synchronous listener throws an unhandled exception, **by default the exception propagates back to the publisher**, which can stop the remaining listeners in the current multicast from being called.

**Same thread** brings important consequences you must understand:

- Listener execution time sits directly on the caller's execution path (request thread, runner thread, scheduler thread, or bootstrap thread).
- The publisher's ThreadLocal, logging MDC, and transaction context can remain present inside synchronous listeners, subject to their scope and configuration.
- Listeners have no implicit "run in background" contract: asynchronous handling must be explicitly configured.
- **@Order/Ordered** can control invocation order among listeners for the same event type, but it does not fix a blocking listener and does not make them run in parallel.

In Spring Framework 6.1+, **ApplicationListener.supportsAsyncExecution()** also allows certain listeners to declare **they must run on the original thread**. This is especially important when configuring a global multicaster with an executor: not every listener is eligible to be offloaded to another thread.

## 3. Where Do Long-Running Listeners Cause Impact?

| Event source | What does a slow listener do? | Practical consequence |
| --- | --- | --- |
| Controller/service handling an HTTP request | Holds the request-handling thread while publishEvent has not returned | Higher response latency, request timeouts, reduced throughput under high load |
| Service inside @Transactional | Extends the transaction flow if the event is published while the transaction is open | Holds connections/locks longer, increasing lock-wait risk |
| ApplicationStartedEvent | Holds the startup thread after refresh but before runners are invoked | Delays ApplicationRunner/CommandLineRunner and readiness |
| ApplicationReadyEvent | Delays completing event processing and subsequent startup steps | Increases time to ReadinessState.ACCEPTING_TRAFFIC |
| ContextRefreshedEvent | Can hold the context refresh thread | Slow startup, risk of hitting startup probe timeouts |
| Job scheduler or message consumer | Holds the scheduler/consumer thread | Increases delay before handling next events, causing backlog or polling stalls |
| Shutdown-related lifecycle event | Slows down the application shutdown path | Slow resource release, risk of exceeding shutdown grace periods |

**Explaining a common case:** a service publishes OrderCreatedEvent during an HTTP request and a listener sends an email via a synchronous HTTP client. If the email provider responds slowly, the thread handling the order must wait. Increasing server thread count only helps up to a point; if every request holds a thread for a long time, the system can still saturate.

**Relationship to transactions:** if publishEvent sits inside an active transactional method and the listener runs synchronously upon publish, both share the same thread. Publishing an event **does not automatically start a new transaction** or commit data; a listener running at that point may observe uncommitted state of the current transaction, depending on how data is accessed.

Do not equate **@TransactionalEventListener** with **@EventListener**: TransactionalEventListener binds to a transaction phase such as AFTER_COMMIT; that is a different contract from a regular listener invoked immediately upon publication.

## 4. Long-Running Listeners Directly Impact the Startup Sequence

Spring Boot publishes lifecycle events during **SpringApplication.run(...)**. Key milestones:

~~~text
... refresh ApplicationContext
          |
          v
ApplicationStartedEvent
          |
LivenessState.CORRECT
          |
ApplicationRunner / CommandLineRunner
          |
ApplicationReadyEvent
          |
ReadinessState.ACCEPTING_TRAFFIC
          |
SpringApplication.run(...) returns
~~~

Default listeners for these events are invoked **synchronously**. Consequently:

- An **ApplicationStartedEvent** listener waiting on a slow remote API prevents runners from being invoked yet, even though ApplicationContext has refreshed.
- A slow **ApplicationReadyEvent** listener delays completing publication of the ready event and transitioning readiness on the normal startup path.
- Spring Boot **recommends not placing long-running tasks inside startup event listeners**. If a task is a precondition for the application to be ready, **ApplicationRunner/CommandLineRunner** is usually a better extension point: its intent is clear, it can be ordered, and throwing an exception can fail startup rather than falsely announcing ready.
- A web server binding its port or logging "Started ..." does not prove that runners have completed or that the instance is ready.

Note: runners are also invoked synchronously during startup by design and **can lengthen startup** if they perform slow work. Moving work from a listener to a runner does not make the task inherently faster; the benefit is **proper placement of responsibility and coordination before ready**, with clear timeout, monitoring, and fail-fast semantics.

## 5. Runnable Example: A Slow Listener Blocking the Publisher on the Same Thread

This example uses **Java 17+** and **Spring Boot 3.x**, simulating a runner that publishes an InventoryChecked event; a "slow" synchronous listener runs before an audit listener. All source code resides in **a single Java file** for easy inspection.

### 5.1. Project Structure

~~~text
sync-listener-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        example/
          SynchronousEventDemo.java
~~~

File **settings.gradle**:

~~~groovy
rootProject.name = 'sync-listener-demo'
~~~

File **build.gradle**:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
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
~~~

Spring Boot 3.3.x requires Java 17+. The project requires Gradle and compatible plugins, plus access to download dependencies from Maven Central or a local cache. The lesson focuses on event behavior, so no HTTP server is needed.

### 5.2. Java Source

File **src/main/java/example/SynchronousEventDemo.java**:

~~~java
package example;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class SynchronousEventDemo {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(
                SynchronousEventDemo.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println("MAIN_AFTER_RUN");
        }
    }
}

record InventoryChecked(String sku, boolean failListener) {
}

@Component
class EventProducer implements ApplicationRunner {
    private final ApplicationEventPublisher publisher;

    EventProducer(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("PUBLISH_BEFORE");
        publisher.publishEvent(new InventoryChecked(
                "SKU-42", args.containsOption("fail-listener")));
        System.out.println("PUBLISH_AFTER");
    }
}

@Component
class SlowInventoryListener {

    @EventListener
    @Order(10)
    public void onInventoryChecked(InventoryChecked event) {
        System.out.println("SLOW_START");

        if (event.failListener()) {
            throw new IllegalStateException("Listener failed");
        }

        try {
            Thread.sleep(400);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted", e);
        }

        System.out.println("SLOW_END");
    }
}

@Component
class AuditInventoryListener {

    @EventListener
    @Order(20)
    public void audit(InventoryChecked event) {
        System.out.println("AUDIT");
    }
}

@Component
class ReadySignal {

    @EventListener(ApplicationReadyEvent.class)
    public void onReady() {
        System.out.println("APPLICATION_READY");
    }
}
~~~

**Key points to understand in the code:**

1. **InventoryChecked** is a plain Java record and does not need to extend ApplicationEvent. Spring Framework can wrap the event payload to dispatch to **@EventListener** methods with matching parameters.
2. **EventProducer** is an **ApplicationRunner**, invoked by Spring Boot after context refresh and before ApplicationReadyEvent.
3. **@Order(10)** on SlowInventoryListener causes this method to be called before **@Order(20)** on AuditInventoryListener for the same event in the default synchronous configuration.
4. **Thread.sleep(400)** merely simulates a slow external call. Production code must use controlled timeouts/real I/O; never use sleep as an event-handling strategy.
5. **PUBLISH_AFTER** can print only after **publishEvent(...) returns**, meaning after synchronous listeners have finished.
6. Main closes the ApplicationContext after run(...) returns successfully. In a long-running web service, **never close the context after every request**.

### 5.3. Running and Observing

If the project has a Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

The lines **printed by the example code itself** appear in this order:

~~~text
PUBLISH_BEFORE
SLOW_START
SLOW_END
AUDIT
PUBLISH_AFTER
APPLICATION_READY
MAIN_AFTER_RUN
~~~

Spring Boot/Gradle logs may appear in between; the block above does not describe the entire console output. **There is no fixed millisecond figure in stdout** because Thread.sleep and real OS scheduling vary.

Key point: even though the event was "published," **PUBLISH_AFTER does not appear immediately after PUBLISH_BEFORE**. The publisher waited for the slow listener and audit listener to finish. If a slow listener performs 10 seconds of network I/O during a real request, the entire request may have to wait nearly 10 seconds plus the remaining steps.

### 5.4. Failure Branch of a Synchronous Listener

Try triggering an exception inside the listener:

~~~bash
./gradlew bootRun --args="--fail-listener"
~~~

The lines printed by the source before the exception are:

~~~text
PUBLISH_BEFORE
SLOW_START
~~~

Then SlowInventoryListener throws **IllegalStateException("Listener failed")**. With the default configuration **without an ErrorHandler swallowing errors**, the exception propagates back to publishEvent(...), causing ApplicationRunner to fail; Spring Boot handles the startup failure. Because the listener failed before the multicaster moved on to audit, **AUDIT**, **PUBLISH_AFTER**, **APPLICATION_READY**, and **MAIN_AFTER_RUN** do not appear along the success path. The framework/Gradle may print a stack trace and build failure status.

**Implication:** a synchronous listener error is not just a log from an isolated component; it can fail the caller. When an event is published in an HTTP service, an exception can fail the request; when published from a startup runner, it can prevent the application from reaching the ready state.

## 6. How to Identify Slow Listeners and Measure Latency

### Measuring from the Publisher Side

Wrap timing around publishEvent(...):

~~~java
long startedAt = System.nanoTime();
publisher.publishEvent(new InventoryChecked("SKU-42", false));
long elapsedMillis =
        java.util.concurrent.TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - startedAt);
System.out.println("publishEvent took " + elapsedMillis + " ms");
~~~

This is an **illustrative snippet** placed inside a method with an injected **ApplicationEventPublisher publisher**. The measured value is the total duration of the publishEvent call, including finding and invoking synchronous listeners and related overhead; it **does not** automatically tell you which listener is slow.

### Measuring Per Listener

For important events, you can:

- Record a **timer metric** for each handler and for total publishEvent duration, avoiding customer/order IDs that create excessive label cardinality.
- Capture traces/spans with sufficient context; for events running synchronously on the same thread, MDC/ThreadLocal is typically preserved within the matching scope.
- Log start/end timestamps for listeners doing external I/O, keeping log volume bounded.
- Configure timeouts on HTTP clients, JDBC, file/network calls, and external systems to avoid holding threads indefinitely.
- Inspect thread dumps when the app "hangs" at startup or API latency spikes: is the thread inside **ApplicationEventMulticaster**, and which handler is blocking?
- Distinguish **slowness caused by listeners** from **slowness in publisher code before/after publishEvent**.

Do not use an "event published" log as proof that the event was processed successfully if the system has async listeners; measure completion status at the consumer itself.

## 7. Solution 1: Keep Listeners Synchronous but Short and Bounded

Synchronicity **is not inherently bad**. It is useful when you need:

- The caller to see exceptions immediately and fail the transaction/request cleanly.
- Short operations to finish before the main flow continues.
- Fast, consistent invariant checks within the same transaction, if carefully designed.
- Easy-to-follow ordering, straightforward debugging, and low scheduling overhead.

How to improve it:

1. Keep only **lightweight validation or brief processing** inside listeners; avoid long external I/O.
2. Set **explicit timeouts**, bounded retry counts, and fallbacks for non-critical dependencies.
3. Never re-publish events infinitely or create recursive event loops.
4. If a task is a mandatory startup condition, **move it to a runner** to express responsibility clearly, still with timeouts and fail-fast behavior.
5. For post-transaction notifications such as emails or non-mandatory audits, consider the **transactional outbox + worker/queue** pattern instead of making requests wait on external systems.

For example: for an order, checking business policy before commit may belong as a synchronous service step, rather than sending an email notification on the same thread/transaction.

## 8. Solution 2: Moving a Specific Listener to @Async

If a handler **does not need to complete before the publisher proceeds**, Spring supports **@Async** on **@EventListener** methods. Enable **@EnableAsync** and configure a suitable executor. The method can then run on another thread.

### 8.1. Configuring a Bounded Executor

The following example is an **alternative configuration to illustrate async**, not part of the synchronous project in Section 5. To try it, add the classes to a project with the InventoryChecked record and **remove/adjust existing synchronous listeners** to avoid duplicate event handling.

~~~java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
class AsyncEventConfiguration {

    @Bean("eventExecutor")
    ThreadPoolTaskExecutor eventExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("event-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(10);
        return executor;
    }
}
~~~

A bounded executor controls thread count and queue depth. **CorePoolSize=2, MaxPoolSize=4, and QueueCapacity=100** are illustrative values; measure real traffic. When the queue fills up and the executor rejects additional tasks, the publisher may see a task rejection error right at submission time; async does not eliminate all forms of blocking or failure.

Corresponding async listener:

~~~java
package example;

import org.springframework.scheduling.annotation.Async;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class AsyncInventoryListener {

    @Async("eventExecutor")
    @EventListener
    public void onInventoryChecked(InventoryChecked event) {
        System.out.println("ASYNC_START");
        // Perform independent work, with timeout and dedicated error handling.
        System.out.println("ASYNC_DONE");
    }
}
~~~

In a real deployment, the handler must perform concrete work with logging/metrics. This sample class uses the same **InventoryChecked** record from Section 5. If both synchronous and async listeners remain active, **both will receive the event**, so do not use Section 5's output to predict the new completion order.

### 8.2. What Changes When Using @Async?

| Aspect | Default @EventListener | @Async + @EventListener |
| --- | --- | --- |
| Executing thread | Publisher thread | Thread from async executor if submission succeeds |
| Does publisher wait for handler to finish? | Yes | No, waits only until the task is scheduled |
| Completion order across multiple handlers | Can follow synchronous invocation order | No completion order guarantee |
| Exceptions from handler | Typically propagate to publisher | Do not propagate back to publisher once task is running |
| Transaction/thread-local context | Can share publisher thread/context | Not automatically transferred to another thread |
| Startup completion barrier | Can hold startup until handling finishes | Does not guarantee work finishes before ApplicationReadyEvent |
| Shutdown | Follows current thread | Must configure appropriate executor/task lifecycle |

**@EnableAsync is mandatory** to use standard async method infrastructure. A non-Spring-managed bean or a self-invocation **this.method()** can bypass the AOP proxy, preventing @Async from taking effect as expected.

**Async exceptions:** with an @Async method returning void, exceptions occurring inside the task **are not propagated back to the publishEvent(...) caller**. Spring uses AsyncUncaughtExceptionHandler/appropriate logging; if errors matter, you need a dedicated handler, retries, dead-letter handling, or job status tracking. Never treat "the publisher saw no error" as proof that the email/job succeeded.

**ThreadLocal/MDC/transactions:** worker threads do not automatically carry the publisher's full security context, transaction, and MDC. If related data is required, pass needed values in the event, use an appropriate TaskDecorator/context propagation mechanism, and define dedicated transaction boundaries for the task.

**Ordering:** @Order controls **registration/invocation or scheduling order** in applicable situations, yet with async it cannot be used to promise **listener A completes before listener B**. If tasks have dependencies, coordinate explicitly via services/workflows or controlled sequential processing.

## 9. Solution 3: Configuring ApplicationEventMulticaster with an Executor

Another option is configuring a **global ApplicationEventMulticaster** with an executor. This affects **many listeners across the entire context**, so weigh it much more carefully than placing @Async on a single method.

In Spring Framework, define a bean with the special name **applicationEventMulticaster** (constant **AbstractApplicationContext.APPLICATION_EVENT_MULTICASTER_BEAN_NAME**) so the context uses it.

Illustrative configuration example:

~~~java
@Configuration
class MulticasterConfiguration {

    @Bean(name = AbstractApplicationContext.APPLICATION_EVENT_MULTICASTER_BEAN_NAME)
    SimpleApplicationEventMulticaster applicationEventMulticaster(
            @Qualifier("eventExecutor") ThreadPoolTaskExecutor executor) {
        SimpleApplicationEventMulticaster multicaster =
                new SimpleApplicationEventMulticaster();
        multicaster.setTaskExecutor(executor);
        multicaster.setErrorHandler(error ->
                System.err.println("Event handler error: " + error));
        return multicaster;
    }
}
~~~

This snippet **is not a standalone Java file**; it requires imports from **org.springframework.context.annotation**, **org.springframework.context.support.AbstractApplicationContext**, **org.springframework.context.event.SimpleApplicationEventMulticaster**, **org.springframework.beans.factory.annotation.Qualifier**, and **ThreadPoolTaskExecutor**. It can reuse an executor like the one configured in Section 8. **Do not enable both a global async multicaster and @Async on individual methods unless you understand double-scheduling and executor management**.

Limitations to understand:

- **Global change:** listeners capable of async execution will change threads, execution timing, error propagation, and observability. Startup event listeners may also be affected, so never rely on an async listener finishing before startup runners.
- **supportsAsyncExecution():** in Spring Framework 6.1+, some ApplicationListeners require running on the publisher thread, such as transaction-bound listeners. A global multicaster **does not mean every listener becomes async**.
- **ErrorHandler:** the configuration above **logs and does not rethrow**, a deliberate choice to stop synchronous errors from propagating to the caller. Use this only with an appropriate error-handling policy; if a critical callback fails, swallowing errors can leave inconsistent state.
- **Task rejection:** an executor can reject scheduling depending on multicaster configuration and framework behavior; do not assume an unbounded queue or automatic fallback to the caller thread.
- **No durability:** offloading listeners to an in-RAM executor still does not create a durable queue. If the JVM dies before processing, tasks can be lost.

For one or two independent notification handlers, **per-listener @Async** or a queue/outbox is usually easier to control. A global multicaster makes sense only when you fully understand the requirements of all listeners and framework events across the application.

## 10. Error Handling in Synchronous and Asynchronous Listeners

### Synchronous Listeners

By default, **SimpleApplicationEventMulticaster** has no ErrorHandler, so an unhandled exception from one listener halts the current multicast and propagates to the publisher. Example:

~~~java
@EventListener
void onInventoryChecked(InventoryChecked event) {
    throw new IllegalStateException("Audit unavailable");
}
~~~

This is an illustrative method inside a Spring bean. If the caller is inside **@Transactional**, a runtime exception can roll back the transaction per configured transaction rules, **if** the exception crosses the transaction boundary. However, side effects outside the transaction (APIs already called, emails already sent) are not automatically undone.

You can catch exceptions locally inside a listener when errors are safe to ignore, provided you emit enough logs and metrics to investigate. Do not catch all Throwables and return "success" if the handler enforces a mandatory precondition for request/startup correctness.

### Asynchronous Listeners

Once a task is submitted and starts running on another thread, the caller does not receive the handler's exception directly. Therefore you need to:

- Monitor **async handler failures**, backlog, queue saturation, retry counts, and task age.
- Choose idempotent retries, timeouts, and appropriate give-up thresholds.
- Account for ordering and duplicate possibilities when multiple tasks touch the same entity.
- Never rely on the publisher's transaction extending automatically onto the task thread.
- Define shutdown behavior: wait for critical tasks up to a deadline, or use a durable queue if data loss is unacceptable.

**Note especially:** pairing ApplicationReadyEvent with an @Async listener does not make the async work a readiness precondition. The event may have finished publishing and readiness may be announced before the task completes.

## 11. How Does TransactionalEventListener Differ from Regular @EventListener?

**@TransactionalEventListener** lets you react according to a **transaction phase** (BEFORE_COMMIT, AFTER_COMMIT, AFTER_ROLLBACK, AFTER_COMPLETION). The default phase is **AFTER_COMMIT**. It is a tool for synchronizing reaction timing with a transaction, not simply a variant of async events.

Example:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderCommitted(OrderCreated event) {
    // React only when the transaction reaches the matching commit outcome.
}
~~~

The snippet above is **illustrative code**, not a standalone class; it requires imports from **org.springframework.transaction.event** and an application-defined OrderCreated business event type. When no transaction is active, this kind of listener **is not invoked by default**, unless **fallbackExecution=true** is configured.

In Spring Framework 6.1+, listeners requiring transaction binding can declare that they do not support async execution by the multicaster, because they must synchronize with the transactional thread/context. **Do not use a global executor assuming it will "push every TransactionalEventListener into the background."**

Even in AFTER_COMMIT, performing a slow email/network call in a synchronous callback still holds the thread completing the transaction. For critical integrations, an outbox pattern that stores a durable event in the same transaction for a separate worker to send is usually a more reliable choice.

## 12. Choosing a Solution by Scenario

| Scenario | Design approach | Reason |
| --- | --- | --- |
| Lightweight validation right when business logic publishes an event | Synchronous, brief, and fail clearly | Caller needs to know the outcome |
| Recording simple metrics or logs | Synchronous and minimal; or an appropriate collector | Tiny task does not warrant another thread |
| Sending email notifications after an order commits | Outbox/queue, or async listener if loss on process crash is acceptable | Avoid holding requests for email; control retries |
| Mandatory cache warm-up before service is ready | ApplicationRunner/CommandLineRunner with timeout | Work belongs to an explicit startup barrier |
| Event inside HTTP request calling a multi-second third-party API | Decouple execution with timeouts/queues | Avoid tying up request threads |
| Need to react after transaction commit | @TransactionalEventListener(AFTER_COMMIT), consider outbox | Bind timing to commit |
| Mandatory audit listener that must not be lost | Outbox + durable messaging + idempotent consumer | In-RAM @Async is not durable |
| Heavy background CPU task | Bounded executor or suitable job system | Avoid starving request/thread pools |
| Wanting every listener to run in the background automatically | Do not rush to change global multicaster; evaluate each listener | Lifecycle/transaction/error semantics may change |
| Consumer needing continuous execution with start/stop lifecycle | SmartLifecycle/consumer container | Runners/event listeners do not manage this lifecycle themselves |

**Minimum parameters to design for async:** max concurrency, queue capacity, queue-full policy, task timeout, retry/backoff, idempotency, error reporting, shutdown deadline, trace correlation, and event data security.

## 13. Very Common Mistakes

**1. Assuming publishEvent is always asynchronous.** False. By default, listeners run **synchronously** on the publisher's thread.

**2. Using a listener to call an external API without a timeout.** The HTTP/runner thread can hang indefinitely, easily causing request timeouts and thread starvation.

**3. Putting heavy warm-up in ApplicationStartedEvent.** Started occurs before runners; a slow listener delays the startup chain. Move to a runner if warm-up must finish before ready.

**4. Putting long tasks in ApplicationReadyEvent.** Synchronous event listeners can delay readiness; use events for lightweight notifications, not as a job infrastructure replacement.

**5. Adding @Async while forgetting @EnableAsync.** The annotation alone does not run methods on another thread when async processing is not enabled.

**6. Calling this.someAsyncMethod() from the same bean.** Self-invocation can bypass the proxy, keeping @Async from taking effect.

**7. Treating @Order as a completion-order guarantee under async.** @Order can affect invocation/scheduling order, yet async tasks have no guaranteed completion order.

**8. Thinking an async exception automatically rolls back the publisher's transaction.** The task runs on a different thread and errors generally do not propagate back; design separate transaction boundaries and reporting.

**9. Configuring a global async multicaster without auditing sensitive listeners.** This can affect startup events, transactions, security/logging contexts, and synchronous assumptions.

**10. Using an unbounded executor queue.** Under load spikes, backlog consumes memory and latency, risking JVM OOM; use bounded queues, metrics, and saturation policies.

**11. Swallowing exceptions from mandatory listeners.** The publisher continues even though invariants were not met; distinguish critical vs. best-effort errors.

**12. Believing @Async guarantees email/message delivery during JVM shutdown.** An in-RAM async executor has no durability; use an outbox/broker when tasks must not be lost.

**13. Forgetting idempotency during retries.** Events may be reprocessed, sending duplicate emails or double-updating state; include appropriate keys/idempotency keys.

**14. Ignoring backpressure.** A producer faster than the consumer over time fills the queue; async only moves the bottleneck rather than removing capacity limits.

**15. Measuring only controller duration without breaking down listeners.** It becomes hard to tell whether bottlenecks come from HTTP clients, event handlers, or core logic; add per-stage metrics.

## 14. Testing Checklist

1. **Synchronous test:** publish an event from one thread and verify the publisher returns only after listeners finish. Section 5 demonstrates this via the sequence PUBLISH_BEFORE → SLOW_* → AUDIT → PUBLISH_AFTER.
2. **Exception test:** make a listener throw an exception and verify publisher and subsequent listener behavior; do not assume audit ran if an earlier exception interrupted the multicast.
3. **Startup test:** create a controlled Started/Ready listener and confirm long work delays the corresponding milestone; avoid long sleeps in real CI.
4. **Async test:** use CountDownLatch or CompletableFuture to await conditional task completion; **never** assert stdout order across threads.
5. **Load test:** test high event rates and slow external I/O, checking queue depth, memory, thread pool utilization, and task rejections.
6. **Shutdown test:** stop the service while tasks remain and verify wait/delegation policies avoid losing critical work.
7. **Transaction test:** test commit, rollback, AFTER_COMMIT, and async contexts; do not confuse a published event with a committed transaction.
8. **Operational observability:** log appropriate correlation IDs, per-listener timers, error/retry counts, and age of pending tasks.

When testing with **Spring Boot 3.x/Java 17+**, make sure a single test run does not accidentally keep both synchronous and asynchronous implementations of the same business handler active and mistake that for default ordering.

## 15. Self-Check Questions

**Question 1.** A controller calls publishEvent and a listener takes 2 seconds. Can the controller return its response immediately?  
**Answer:** Not by default; the caller waits for synchronous listener execution to finish, unless the code explicitly offloads work asynchronously.

**Question 2.** There are two listeners @Order(10) and @Order(20). Listener 10 blocks for 5 seconds. Is Listener 20 invoked immediately?  
**Answer:** With the default synchronous multicaster, Listener 20 normally waits for Listener 10 to finish before being invoked.

**Question 3.** A synchronous listener throws RuntimeException. Does the publisher know?  
**Answer:** Yes, the exception can propagate back to the publisher under the default configuration without an ErrorHandler swallowing errors.

**Question 4.** How does a slow ApplicationStartedEvent listener affect startup?  
**Answer:** It can block the startup thread after refresh and delay runners as well as readiness.

**Question 5.** Is placing @Async on a listener enough for async execution?  
**Answer:** You must enable @EnableAsync and ensure the listener is an AOP-managed bean with an available executor.

**Question 6.** If an @Async listener fails after the publisher has returned, does the exception automatically propagate to the publisher?  
**Answer:** No. You need AsyncUncaughtExceptionHandler/logging/monitoring and a dedicated failure-handling policy.

**Question 7.** Does an async task executor automatically create a transaction and copy MDC from the request?  
**Answer:** Not automatically; you need explicit transaction configuration, context propagation, and proper design.

**Question 8.** Does a global multicaster with an executor make every listener run asynchronously?  
**Answer:** Not necessarily; in Spring 6.1+ listeners that do not support async execution may still have to run on the original thread.

**Question 9.** Can internal events with @Async replace Kafka or a transactional outbox for non-losable audits?  
**Answer:** No. In-memory async does not guarantee durable storage or redelivery if the JVM crashes.

**Question 10.** What should be used for mandatory warm-up work before ready?  
**Answer:** A runner with appropriate timeouts/fail-fast behavior, rather than running async and announcing ready prematurely.

**Key takeaway:** **Spring listeners run synchronously on the event-publishing thread by default.** Slow listeners slow down the publisher and can impact requests, transactions, or startup sequences. Keep synchronous listeners short with timeouts; use **runners** for mandatory startup work; use **@Async/executors** only when accounting for changes in transactions, exceptions, ordering, and shutdown; and use **durable queues/outboxes** when events must never be lost.

### References

- [Spring Boot — Application Events and Listeners](https://docs.spring.io/spring-boot/reference/features/spring-application.html)
- [Spring Framework 6.1 — SimpleApplicationEventMulticaster API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework — Application Events and @EventListener](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework — Observability Support for Application Events](https://docs.spring.io/spring-framework/reference/integration/observability.html)
