# Async Listener Running on a Different Thread

## 1. Symptom: Publish Succeeds Yet the Listener Runs on an Unexpected Thread

In Spring Framework Application Events, developers often start with a synchronous `@EventListener`:

~~~java
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    process(event);
}
~~~

With the default multicaster configuration, this listener normally runs **on the exact thread calling `ApplicationEventPublisher.publishEvent(...)`**. If the publisher is a Spring MVC request thread, the listener can also see thread-bound contexts valid at that moment.

When `@Async` is added and `@EnableAsync` is enabled, behavior changes:

~~~java
@Async("eventExecutor")
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    process(event);
}
~~~

Spring routes the method call through the async proxy mechanism to a `TaskExecutor`. The actual processing thread may be `event-worker-1`, **not** `http-nio-8080-exec-3` which published the event.

Example log:

~~~text
2026-11-11T07:00:01Z publisher [http-nio-8080-exec-3] eventId=evt-101
2026-11-11T07:00:01Z listener  [event-worker-1]       eventId=evt-101
~~~

Thread names are merely illustrative; every servlet container and executor has its own naming scheme. An event can preserve its ID across two threads, while thread-bound data such as MDC, request context, or transaction context **does not travel along automatically**.

Common symptoms:

- `RequestContextHolder.currentRequestAttributes()` throws `IllegalStateException`: no request context is bound on the worker.
- `SecurityContextHolder.getContext().getAuthentication()` lacks the expected value without an appropriate propagation mechanism.
- Listener logs lack `traceId`/`correlationId` even though controller logs have them.
- `TransactionSynchronizationManager.isActualTransactionActive()` returns `false` inside the async listener even though the publisher was inside `@Transactional`.
- An exception in the listener does not propagate back to the controller or service that called `publishEvent`.
- The service logs "published" before the listener logs "started processing".
- The listener occasionally runs on a different thread each time due to the executor pool; completion ordering can vary.

**The first diagnostic question** must be: *was the listener call actually handed off to an executor, and which thread is running the business code?* Do not deduce behavior merely from seeing `@Async` in source code.

## 2. Distinguishing Three Event Dispatch Modes

| Handling mode | Thread running handler | Does publisher wait for handler completion? | Notes |
| --- | --- | --- | --- |
| Regular `@EventListener`, default multicaster | Usually the publishing thread itself | Yes, for synchronous listeners | Handler exceptions can propagate to publisher |
| `@Async @EventListener` with active `@EnableAsync` | Thread belonging to the async proxy's executor | Does not wait for task completion | `void` method errors follow async exception policy |
| Custom `SimpleApplicationEventMulticaster` with `TaskExecutor` | Executor chosen by multicaster, if listener supports async execution | Not necessarily | Dispatch, context, and exception policies are configuration responsibilities |

### Two Distinct Async Layers

**Approach A — `@Async` on the listener method:**

~~~text
ApplicationEventPublisher
    -> default multicaster invokes @EventListener adapter
        -> bean async proxy schedules method onto TaskExecutor
            -> worker thread executes listener body
~~~

**Approach B — TaskExecutor directly on the multicaster:**

~~~text
ApplicationEventPublisher
    -> SimpleApplicationEventMulticaster
        -> TaskExecutor hands off listener invocation to worker
            -> listener method executes
~~~

Both can coexist in an application, even creating two layers of scheduling if configured unintentionally. When debugging, identify **which executor** received the task. Do not "fix" slow listeners by blindly attaching executors in both places.

In Spring 6.2, `SimpleApplicationEventMulticaster` invokes listeners synchronously by default. When an executor is configured on the multicaster, some listeners that **do not support async execution** still execute on the publishing thread; for example, transaction-synchronized listeners have their own mechanism. Thus "configured an async multicaster" does not prove *every* listener switches threads.

## 3. Conditions for @Async to Actually Work

`@Async` is processed by Spring through the async infrastructure, typically via an AOP proxy. Check these conditions:

1. **`@EnableAsync` is present** in the appropriate context (or equivalent infrastructure is enabled), not just importing the annotation.
2. The listener is a **Spring-managed bean**, not an object created via `new` and called directly.
3. The handler method is eligible for proxy interception: avoid `private`, `final`, or a `final` target class in subclass-based proxy setups; understand interface- vs. class-based proxy constraints.
4. A **valid `TaskExecutor`** exists. For `@Async("eventExecutor")`, the qualifier must point to the right executor bean.
5. The call to the handler goes **through the proxy**, not internal self-invocation like `this.onOrderPlaced(event)`.
6. Do not confuse this with a publisher invoking a synchronous listener that manually spawns a task inside the method; that is a different architecture and must be measured at task creation.

If code annotated with `@Async` still runs on the request thread, check registration/proxy/configuration before blaming Spring event routing.

### @Order and Execution Order

`@Order` governs the priority of **invocation or scheduling** among matching listeners; it does not force a higher-priority async listener to **complete** before a lower-priority listener. With thread pools, completion order also depends on task duration, queues, and the scheduler.

~~~text
@Order(-10) async A: scheduled
@Order(10)  sync B : finishes processing
async A             : may finish later than B
~~~

Therefore, if B **needs data committed by A**, build explicit orchestration/transactions instead of relying on `@Order`.

## 4. Java 17+ Program Proving Thread and Event Payload Behavior

Complete demo using **Spring Framework 6.2.19**, **Java 17+**, and `ThreadPoolTaskExecutor`. Requires no Spring Boot, web server, or database.

Design:

- `main` acts as the publishing thread;
- `SyncOrderListener` uses regular `@EventListener`, running on the publishing thread;
- `AsyncOrderListener` uses `@Async("eventExecutor")`, running on a thread prefixed `event-worker-`;
- both push an `Observation` into a `BlockingQueue`;
- `main` pulls **two observations** via `poll(timeout)`, classifies by listener name, and prints results in fixed order regardless of which thread finished first;
- the event carries `correlationId` to prove **payload data is still delivered intact** even though thread-local contexts do not travel automatically.

### Directory Structure

~~~text
async-event-thread-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/AsyncEventThreadDemo.java
    └── test/java/demo/AsyncEventThreadDemoTest.java
~~~

### settings.gradle

~~~groovy
rootProject.name = 'async-event-thread-demo'
~~~

### build.gradle

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.12.2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.12.2'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.AsyncEventThreadDemo'
}

test {
    useJUnitPlatform()
}
~~~

### src/main/java/demo/AsyncEventThreadDemo.java

~~~java
package demo;

import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class AsyncEventThreadDemo {

    // Business snapshot: do not hold references to Thread, HttpServletRequest,
    // or transaction/session objects in events.
    public record OrderPlaced(long orderId, String correlationId) {}

    public record Observation(
        String listener,
        String threadName,
        String correlationId
    ) {}

    @Bean
    BlockingQueue<Observation> observations() {
        return new LinkedBlockingQueue<>();
    }

    @Bean(name = "eventExecutor")
    ThreadPoolTaskExecutor eventExecutor() {
        var executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setQueueCapacity(8);
        executor.setThreadNamePrefix("event-worker-");
        return executor;
    }

    @Bean
    SyncOrderListener syncOrderListener(
            BlockingQueue<Observation> observations) {
        return new SyncOrderListener(observations);
    }

    @Bean
    AsyncOrderListener asyncOrderListener(
            BlockingQueue<Observation> observations) {
        return new AsyncOrderListener(observations);
    }

    public static class SyncOrderListener {
        private final BlockingQueue<Observation> queue;

        public SyncOrderListener(BlockingQueue<Observation> queue) {
            this.queue = queue;
        }

        @EventListener
        public void onOrderPlaced(OrderPlaced event) {
            queue.add(new Observation(
                "sync",
                Thread.currentThread().getName(),
                event.correlationId()
            ));
        }
    }

    // Non-final: @Async uses proxying, so the method must be interceptable.
    public static class AsyncOrderListener {
        private final BlockingQueue<Observation> queue;

        public AsyncOrderListener(BlockingQueue<Observation> queue) {
            this.queue = queue;
        }

        @Async("eventExecutor")
        @EventListener
        public void onOrderPlaced(OrderPlaced event) {
            queue.add(new Observation(
                "async",
                Thread.currentThread().getName(),
                event.correlationId()
            ));
        }
    }

    // Helper receiving both observations without assuming arrival order.
    public static Map<String, Observation> collectTwo(
            BlockingQueue<Observation> queue)
            throws InterruptedException {
        Observation first = queue.poll(10, TimeUnit.SECONDS);
        Observation second = queue.poll(10, TimeUnit.SECONDS);

        if (first == null || second == null) {
            throw new IllegalStateException(
                "Expected both sync and async listener observations"
            );
        }

        Map<String, Observation> results = new HashMap<>();
        results.put(first.listener(), first);
        results.put(second.listener(), second);

        if (results.size() != 2 ||
            !results.containsKey("sync") ||
            !results.containsKey("async")) {
            throw new IllegalStateException(
                "Missing or duplicated listener observation"
            );
        }
        return results;
    }

    public static void main(String[] args)
            throws InterruptedException {
        try (var context = new AnnotationConfigApplicationContext(
                AsyncEventThreadDemo.class)) {

            String publisherThread = Thread.currentThread().getName();

            @SuppressWarnings("unchecked")
            BlockingQueue<Observation> queue =
                (BlockingQueue<Observation>) context.getBean(
                    "observations");

            context.publishEvent(new OrderPlaced(101L, "REQ-101"));

            Map<String, Observation> result = collectTwo(queue);
            Observation sync = result.get("sync");
            Observation async = result.get("async");

            System.out.println(
                "sync same thread="
                    + publisherThread.equals(sync.threadName()));
            System.out.println(
                "async on event executor="
                    + async.threadName().startsWith("event-worker-"));
            System.out.println(
                "async different thread="
                    + !publisherThread.equals(async.threadName()));
            System.out.println(
                "correlation preserved="
                    + (Objects.equals(sync.correlationId(), "REQ-101")
                    && Objects.equals(async.correlationId(), "REQ-101"))
            );
        }
    }
}
~~~

### Running the Program

Use JDK 17+ with Gradle or a compatible Gradle Wrapper:

~~~bash
gradle run --quiet
# With wrapper: ./gradlew run --quiet
# On Windows: gradlew.bat run --quiet
~~~

Lines intentionally printed by `main`:

~~~text
sync same thread=true
async on event executor=true
async different thread=true
correlation preserved=true
~~~

Line-by-line explanation:

1. **`sync same thread=true`**: regular listener runs on the exact thread calling `publishEvent` with the default multicaster.
2. **`async on event executor=true`**: `@Async("eventExecutor")` method executes on a thread prefixed `event-worker-` by `ThreadPoolTaskExecutor`.
3. **`async different thread=true`**: the async processing thread differs from the publishing thread.
4. **`correlation preserved=true`**: the event payload retains `correlationId` when delivered to both listeners.

`poll(10, TimeUnit.SECONDS)` here is strictly for **console demo/test** result collection. Never make a real HTTP request thread block indefinitely pretending async work is synchronous; establish separate response/job contracts.

An important condition: the program prints results by **observation type**, rather than printing directly from listeners. Hence the order of the four lines is deterministic regardless of which listener the scheduler invokes first. The code also checks for missing or duplicate observations.

## 5. Testing with JUnit: Do Not Use Thread.sleep()

Create `src/test/java/demo/AsyncEventThreadDemoTest.java`:

~~~java
package demo;

import java.util.Map;
import java.util.concurrent.BlockingQueue;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AsyncEventThreadDemoTest {

    @Test
    void asyncListenerUsesDifferentThreadAndKeepsEventData()
            throws InterruptedException {
        try (var context = new AnnotationConfigApplicationContext(
                AsyncEventThreadDemo.class)) {

            String publisherThread = Thread.currentThread().getName();

            @SuppressWarnings("unchecked")
            BlockingQueue<AsyncEventThreadDemo.Observation> queue =
                (BlockingQueue<AsyncEventThreadDemo.Observation>)
                    context.getBean("observations");

            context.publishEvent(
                new AsyncEventThreadDemo.OrderPlaced(101L, "C-101"));

            Map<String, AsyncEventThreadDemo.Observation> values =
                AsyncEventThreadDemo.collectTwo(queue);

            var sync = values.get("sync");
            var async = values.get("async");

            assertEquals(publisherThread, sync.threadName());
            assertFalse(publisherThread.equals(async.threadName()));
            assertTrue(async.threadName().startsWith("event-worker-"));
            assertEquals("C-101", sync.correlationId());
            assertEquals("C-101", async.correlationId());
        }
    }
}
~~~

Run:

~~~bash
gradle test
# Or: ./gradlew test
# Windows: gradlew.bat test
~~~

When executor configuration works properly, **one JUnit test passes**. The test uses a timeout when collecting observations so it does not hang forever if the async listener fails to run. It relies on no fixed sleep interval and does not assume the `sync` observation always enters the queue before `async`.

**A failing test is a diagnostic signal**. For instance, removing `@EnableAsync` in this configuration can cause the `@Async`-annotated method to be invoked synchronously, turning `async different thread` into `false`. If `eventExecutor` is misnamed or the task is rejected, the test will miss the async observation and throw after the timeout.

Do not generalize the test result into a claim that "every event listener always runs on a different thread": the example itself has **one sync listener** and **one async listener** receiving the same event type.

## 6. Where Do Errors in Async Listeners Go?

With a synchronous listener and default multicaster, a `RuntimeException` can propagate back to the publisher:

~~~text
publishEvent()
    -> sync listener throws
    -> caller of publishEvent receives exception
~~~

With `@Async @EventListener`:

~~~text
publishEvent()
    -> async proxy submits task
    -> publisher may return normally
                           |
                           v
                   worker listener throws
                           |
                           +-- does not automatically rethrow to publisher
~~~

Spring documentation emphasizes that exceptions from asynchronous event listeners **are not propagated to the caller**. For `void` `@Async` methods, exceptions can go to `AsyncUncaughtExceptionHandler`. If the async method returns a Future/CompletableFuture where supported by the API, errors are usually observed through that async result instead of the original caller; note that `@EventListener` methods annotated with `@Async` should not rely on return values to automatically publish follow-up events.

Application illustration snippet (not standalone):

~~~java
@Configuration
@EnableAsync
class AsyncErrorConfiguration implements AsyncConfigurer {

    private static final Logger log =
        LoggerFactory.getLogger(AsyncErrorConfiguration.class);

    @Override
    public AsyncUncaughtExceptionHandler
            getAsyncUncaughtExceptionHandler() {

        return (ex, method, params) -> {
            log.error(
                "Async listener failed: method={}",
                method.getName(),
                ex
            );
            // Can increment metrics, raise alerts, or enqueue a retry.
        };
    }
}
~~~

Requires SLF4J dependency and appropriate imports for `AsyncConfigurer`, `AsyncUncaughtExceptionHandler`, `Logger`, and `LoggerFactory`. This is a **partial configuration pattern**, not a standalone runnable class. Logging only gives error visibility; **it does not automatically retry or guarantee task completion**.

Several related yet distinct failure modes:

- **Error when scheduling the task:** executor overloaded, already shut down, or misconfigured; submission may be rejected right on the publisher or async proxy path, e.g., `TaskRejectedException`.
- **Error after the task is accepted:** callback runs on the worker and throws; the publisher may have already returned, so do not rely on a `try/catch` around `publishEvent` to catch this error.
- **Exception caught and ignored inside the listener:** the method does not rethrow; monitoring may miss errors if the handler fails to report them.
- **Executor queue backlog:** the listener does not necessarily run immediately after publish. "Event exists" does not mean "already processed".
- **Process crash before the worker runs:** a local async executor is not a durable queue; tasks can be lost.

For critical tasks like transaction notifications, external system updates, or payment calls, design **retries, idempotency, an outbox/message broker, or persistent jobs** rather than assuming `@Async` supplies reliability.

## 7. Different Thread: Which Contexts Are Lost?

Threads do not automatically share all state held by the request/publisher. Each context type follows its own rules:

| Context/value | Where is it stored? | What to remember in async workers |
| --- | --- | --- |
| `RequestContextHolder` / `RequestAttributes` | Thread-bound in Spring MVC/Servlet | Usually absent; never use raw `HttpServletRequest` after request ends |
| `SecurityContextHolder` | Typically ThreadLocal under default strategy | Does not automatically carry request authentication; needs security propagation or independent auth |
| `LocaleContextHolder` | Thread-local locale context | Does not automatically transfer locale/timezone |
| MDC/logging context | Thread-local per logging implementation | Worker logs may miss trace/correlation |
| Imperative transaction context | `TransactionSynchronizationManager` binds resources to thread | Does not automatically join publisher's transaction |
| Reactor Context | Context attached to reactive subscriber | Not a servlet ThreadLocal; keep inside reactive chain and use proper propagation |
| Event payload | Object passed to listener | Values in payload remain readable if designed immutable and thread-safe |

This explains a typical failure:

~~~java
@Async("eventExecutor")
@EventListener
public void onPlaced(OrderPlaced event) {
    // Can throw because the worker has no request attributes.
    RequestAttributes attrs =
        RequestContextHolder.currentRequestAttributes();
}
~~~

This is an illustrative snippet; requires bean, imports, and `@EnableAsync` config. Replace with the exact data needed in the payload:

~~~java
public record OrderPlaced(
    long orderId,
    String correlationId,
    String tenantId
) {}

@Async("eventExecutor")
@EventListener
public void onPlaced(OrderPlaced event) {
    processOrder(
        event.orderId(),
        event.correlationId(),
        event.tenantId()
    );
}
~~~

This snippet is also illustrative, requiring `processOrder` and the corresponding bean. **A `tenantId` value in the event does not replace authentication/authorization** when the worker accesses sensitive resources.

### Why Not Enable InheritableThreadLocal for Everything?

`InheritableThreadLocal` can pass values when **a new child thread is created**, yet thread pools reuse workers and may spawn a thread while handling request A. Context from request A can be retained and leaked to a task from request B. For request contexts, that is a dangerous mistake.

Do not enable `RequestContextHolder.setRequestAttributes(attributes, true)` or similar mechanisms as a blanket executor workaround. When propagation is truly needed, account for context lifetime, exact capture/restore, and cleanup on pooled threads.

## 8. Controlled Propagation of Logging/Observation Context

If the sole goal is logging with a `correlationId`, it is usually **simpler and safer** to place the ID inside an immutable event payload. Listeners can log the ID from the event into structured log fields during processing.

When **well-defined execution contexts** must be propagated, Spring supports `TaskDecorator`, such as `ContextPropagatingTaskDecorator` working with Micrometer Context Propagation and corresponding accessors:

~~~java
// Illustration added to ThreadPoolTaskExecutor configuration.
executor.setTaskDecorator(
    new ContextPropagatingTaskDecorator()
);
~~~

Requires a supporting Spring version, the Micrometer Context Propagation dependency, and matching `ThreadLocalAccessor` implementations. **Not every context is copied automatically** merely by adding the decorator; verify which accessors are registered.

Rules:

- Propagate only contexts with **appropriate lifetimes**, such as tracing/logging metadata; never retain raw servlet requests/sessions in background threads by default.
- If writing a custom decorator, snapshot context before submission; restore/clear **in `finally`** to prevent data leaks when workers are reused.
- Never copy transaction ThreadLocals to share a JDBC transaction across threads. Imperative transactions are not designed for cross-thread sharing.
- For security contexts, use appropriate Spring Security mechanisms—such as executor wrappers that guarantee contract-compliant context clearing—rather than copying tokens ad hoc.
- Capture/restore adds overhead; benchmark throughput and latency if the app emits many events.
- Tracing/observability context propagation does not guarantee the listener runs after commit or finishes successfully.

If the app uses Spring WebFlux/Reactor, reason about reactive context in terms of **subscriber context**, rather than forcing everything into servlet-style ThreadLocals.

## 9. Different Threads and Transactions: An Easily Missed Bug

Suppose:

~~~java
@Transactional
public void placeOrder(PlaceOrder command) {
    repository.save(toOrder(command));
    eventPublisher.publishEvent(new OrderPlaced(...));
}
~~~

This code is a non-standalone example. When an event is published **before commit** and an `@Async @EventListener` receives it, the worker may run **before transaction T1 commits**.

Possible consequences:

- The listener queries a repository on its own transaction/connection and **cannot see the uncommitted record**.
- T1 rolls back, yet the listener already called an external API or sent an email; side effects do not roll back automatically.
- The listener reads T1's thread-local state and finds no active transaction.
- Exceptions from the async listener do not automatically roll back T1.

To bind execution after commit, consider:

~~~java
@Async("eventExecutor")
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT)
public void afterOrderCommit(OrderPlaced event) {
    // Callback registered in T1; upon successful commit,
    // the method is dispatched to the executor for independent processing.
}
~~~

This is an illustrative pattern requiring imports/beans; not a standalone program. In imperative Spring:

1. The event is published while T1 is active.
2. `@TransactionalEventListener` infrastructure registers a synchronization callback; the callback itself is triggered by the transaction manager at the proper phase.
3. When T1 commits, the async proxy submits the handler method to the executor.
4. **The executor thread does not inherit T1's transaction**. If the worker needs DB writes, design a dedicated transaction, such as an `@Transactional` method on another bean invoked via Spring proxy (which normally opens a new transaction since the worker has none).

Also remember: `@TransactionalEventListener` **skips events outside a transaction** by default when `fallbackExecution=false`. For Spring reactive transactions, use `TransactionalEventPublisher`/Reactor Context per contract rather than treating servlet ThreadLocals as the transaction source.

If the requirement is that events **must not be lost if the process crashes between commit and processing**, `AFTER_COMMIT + @Async` remains an in-memory solution. Use a transactional outbox or durable messaging with retries/idempotency when high reliability is required.

## 10. Diagnosing by Symptom

### Case A: Added @Async Yet Still Observing the Same Thread

Ask:

1. Is `@EnableAsync` present? Is it in the right `ApplicationContext` managing the listener?
2. Is the listener a Spring bean?
3. Is the method `private`/`final` or invoked directly on the same object (self-invocation)?
4. Was `SyncTaskExecutor` or a custom inline-executing executor used by mistake?
5. Does `@Async("executorName")` reference the right bean?
6. Was the log placed **inside the listener method**, not only around `publishEvent`?

If all listeners run on the same thread with no configured executor, that may be **intended synchronous behavior**. Spring does not enable `@Async` automatically just because a listener sits in the application context.

### Case B: Published, Yet Handler Logs Appear Late

Check executor queue depth, active workers, task duration, saturation, rejection policy, and process shutdown. Do not diagnose "lost event" solely from the order of two log lines. An async listener may simply be waiting for a free worker.

### Case C: Publisher Sees No Exception Yet Task Failed

For `void @Async`, add `AsyncUncaughtExceptionHandler` or explicit try/catch + logging/metrics. Measure **publish attempts**, **listener invocations**, **listener success/error**, **latency**, and pending tasks with distinct metrics. Do not treat `publishEvent` returning as proof of handler success.

### Case D: Handler Logs Lose correlationId/traceId

Use event payloads or controlled context propagation; distinguish business IDs from infrastructure trace contexts. Do not attach high-cardinality IDs (`eventId`, `correlationId`) as metric tags; they belong in logs and traces.

### Case E: Listener Cannot See Newly Saved Entity

Check whether transaction T1 has committed yet. `@Async @EventListener` does not wait for transaction commit. Check isolation levels, how the listener acquires connections, and its queries. If business rules require after-commit execution, use transaction-bound events or an outbox—**do not** try to fix it with `Thread.sleep(...)`.

### Case F: Tests Sometimes Pass, Sometimes Fail

Tests are reading async listener results **right after publish**, or relying on lucky sleeps/timing. Use `BlockingQueue.poll(timeout)`, `CountDownLatch`, `CompletableFuture`, or Awaitility to await a concrete signal. Assert different threads and correct event data; avoid asserting completion order without a contract.

## 11. Symptom-and-Action Matrix

| Observation | Cause to check first | Action |
| --- | --- | --- |
| Same-thread logs despite `@Async` | Async proxy inactive, synchronous executor | Check `@EnableAsync`, bean/proxy, executor |
| Logs show `event-worker-*` thread | Async executing properly | Review lifecycle, errors, and independent contexts |
| `RequestContextHolder` returns `null` | Worker lacks servlet request binding | Snapshot required data into payload |
| MDC missing `correlationId` | No propagation | Payload/structured logging or decorator |
| `isActualTransactionActive() = false` | T1 bound to publisher thread | Open new transaction in worker if needed |
| DB does not show new row yet | Listener ran before commit or different isolation | `AFTER_COMMIT`/outbox per requirements |
| Exception never reaches publisher | Handler failed on worker | `AsyncUncaughtExceptionHandler`, metrics, retries |
| Handler never runs after publish | Wrong type/annotation, executor rejected, backlog, tx phase | Log event type, bean registration, executor, phase |
| A/B log order flips | Independent scheduling and duration | Test via signals; do not rely on `@Order` for completion |
| Tasks lost after restart | Local executor is non-durable | Durable queue/job/outbox |

## 12. Pre-Closure Incident Checklist

- [ ] Verify **event type, event ID/correlation ID, and thread name** at publish time and inside the listener.
- [ ] Distinguish sync `@EventListener`, `@Async @EventListener`, and a multicaster with its own `TaskExecutor`.
- [ ] Verify `@EnableAsync`, proxy, and executor qualifier.
- [ ] Do not assume `@Order` guarantees **completion order** of async tasks.
- [ ] Know whether errors are reported via direct exception, Future, or async error handler.
- [ ] Check required contexts: request, security, locale, MDC, and transaction.
- [ ] Pass needed metadata via immutable event payloads; never carry raw `HttpServletRequest`/JPA entities into background tasks.
- [ ] If propagating context with a decorator, ensure proper restore/clear on pooled threads.
- [ ] Test executor timeouts, rejections, and errors—not just the happy path.
- [ ] If **post-commit** execution is required, use the right phase; if task loss is unacceptable, use an outbox/durable queue.
- [ ] Test async behavior using latches/queues with timeouts; avoid `Thread.sleep`.
- [ ] Review metrics for queue depth, task rejections, listener latency, failures, and backlog.

### Key Takeaway

~~~text
publishEvent(...) on thread A
    |
    +-- synchronous @EventListener
    |     -> usually runs on thread A
    |
    +-- @Async @EventListener
          -> proxy submits to TaskExecutor
          -> runs listener body on thread B
          -> does not inherit A's request/transaction/MDC context
          -> exceptions in B do not propagate back to A

How to debug:
    Log thread + eventId + correlationId on both sides.
    Check @EnableAsync + proxy + TaskExecutor.
    Use immutable payloads for required metadata.
    Separate after-commit/durability from threading concerns.
~~~

## References

- [Spring Framework 6.2 — ApplicationContext Events, Asynchronous Listeners](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework — Task Execution and Scheduling / @Async](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [Spring Framework 6.2 — SimpleApplicationEventMulticaster Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework — Observability Support for Application Events](https://docs.spring.io/spring-framework/reference/integration/observability.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework — RequestContextHolder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/context/request/RequestContextHolder.html)