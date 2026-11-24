# Choosing Synchronous or Asynchronous Events in Spring Framework Application Events

## 1. The Decision That Truly Matters

In the **Deployment Patterns** group of **Spring Framework Application Events**, choosing a synchronous or asynchronous listener is not simply adding or removing `@Async`. That decision changes **completion timing**, **execution threads**, **how errors propagate**, **transaction context**, **side-effect ordering**, and **reliability under overload**.

Consider an order-processing application:

```text
POST /orders
   |
   +-- ValidateOrder
   +-- SaveOrder
   +-- SendEmail
   +-- RebuildSearchIndex
   +-- NotifyAnalytics
```

Do not put all of these steps into the same listener type by default. `ValidateOrder` is a precondition before accepting an order; `SendEmail` may be a post-commit auxiliary task; whereas a financial requirement that must guarantee eventual completion may need a **transactional outbox**, not just `@Async`.

**Quick decision rules:**

- **Need the result/error immediately to decide a transaction or response?** Prefer **synchronous** handling, often via a **direct service call** if it is a mandatory invariant.
- **Allowed to run later, independent of the response path, with an explicit error policy?** Consider `@Async @EventListener`.
- **Task is only valid after data commits?** Use `@TransactionalEventListener(AFTER_COMMIT)`, adding `@Async` if you want it executed on a background thread.
- **Task must never be lost on JVM crash, full executor, or deploy?** Persist a **durable outbox/job** inside the transaction, and have a worker process it according to capacity.

This guide explains each option and includes a runnable Java 17+ example comparing synchronous listeners, async listeners, and transaction-bound callbacks.

## 2. Spring's Default: Synchronous

Under Spring Framework's default mechanism, `ApplicationContext` uses `SimpleApplicationEventMulticaster` to process listeners **synchronously on the thread publishing the event**.

```java
public record OrderChecked(String orderId) {}

@Component
public class AuditListener {

    @EventListener
    public void onChecked(OrderChecked event) {
        auditService.record(event.orderId());
    }
}
```

This is **illustrative code**, requiring `auditService`, imports, and a registered Spring-managed bean.

When the caller invokes:

```java
publisher.publishEvent(new OrderChecked("O-42"));
```

with the default multicaster and plain listeners:

1. Spring finds listeners matching the event type.
2. Each listener runs on **the publisher's own thread**.
3. The caller waits for synchronous listeners to complete before `publishEvent(...)` returns.
4. If a listener throws an unchecked exception and no error handler or catch block handles it, the exception can propagate back to the publisher.
5. If publishing occurs inside an active imperative transaction, synchronous listeners typically run inside the **publisher thread's transaction context**.

**Do not equate "synchronous" with "committed."** A plain listener can run **before the transaction commits**; if it calls an external API and the DB transaction later rolls back, the external side effect does not roll back automatically with the DB.

### Pros of Synchronous

- Linear execution flow, easy to debug and test.
- The caller knows the listener finished before `publishEvent` returns, under the default synchronous multicaster configuration.
- Exceptions can be caught by the caller, translated into business errors, or trigger transaction rollback if rollback rules apply.
- Within a single thread, thread-bound transactions, request context, and logging context remain available.
- Zero overhead from task submission, executor queues, or thread switching for tiny tasks.

### Cons of Synchronous

- Increases caller latency and ties up the request/transaction thread longer.
- If a listener performs slow I/O, slow downstream systems can bottleneck the primary business flow.
- One failing listener can stop subsequent listeners from running or force the transaction to roll back.
- Handlers with external side effects may have executed **before commit**.
- High temporal coupling: auxiliary work lengthens order processing even when the user does not need to wait for it.

## 3. Asynchronous via `@Async @EventListener`

Spring supports `@Async` on listener methods:

```java
@Async("eventExecutor")
@EventListener
public void onOrderCreated(OrderCreated event) {
    searchIndexer.update(event.orderId());
}
```

This is **illustrative code**, not a standalone program. It requires `@EnableAsync`, an executor bean named `eventExecutor`, and the listener belonging to a Spring-managed bean intercepted by an async proxy.

In this mechanism:

```text
Publisher thread
   |
   +-- publishEvent(OrderCreated)
         |
         +-- Spring locates listener
         +-- async proxy submits task to executor
   |
   +-- publishEvent can return
                         |
                         v
                   Executor worker
                         |
                         +-- onOrderCreated(...)
                         +-- completes or fails
```

Spring can run the work on another thread, so the publisher **does not wait for the async method body to finish**. Never treat a normal return from `publishEvent()` as proof that a search index or email has already been updated.

### Pros of Async

- Frees the publisher thread sooner when auxiliary work can run independently.
- Allows dedicated executors for email, analytics, or indexing to isolate latency.
- Increases useful concurrency for I/O-bound workloads when CPU, DB, HTTP clients, and rate limits permit.
- Enables separate timeouts, queue capacities, metrics, and retry/error paths per workload.

### Cons of Async

- Exceptions from `void @Async` methods do not propagate to the caller; they require `AsyncUncaughtExceptionHandler`/logging/error state tracking.
- Worker threads **do not automatically inherit** transactions, request attributes, MDC, security context, or arbitrary thread-locals.
- Task completion order may differ from submission order.
- In-memory queues can fill up or lose tasks on crash.
- Tests easily become flaky if they assert immediately after publishing without awaiting completion.
- `@Async` does not guarantee an event enters the executor if the executor is shutting down or rejects tasks.

**Beware of `@Async` before commit:** an event published inside transaction T1 can cause a worker to query the DB **before T1 commits**, or trigger side effects even though T1 later rolls back. To avoid this, use a transaction-bound listener or an outbox.

## 4. A Practical Decision Workflow

You can follow this decision flow:

```text
New task arises
    |
    +-- Need the result immediately to continue business logic?
    |      |
    |      +-- YES -> synchronous (prefer direct service call)
    |      |
    |      +-- NO
    |             |
    |             +-- Must DB commit succeed before executing?
    |             |      |
    |             |      +-- YES -> AFTER_COMMIT
    |             |      |            |
    |             |      |            +-- Tolerate loss on crash?
    |             |      |                  +-- YES -> @Async AFTER_COMMIT is viable
    |             |      |                  +-- NO  -> durable outbox/job
    |             |      |
    |             |      +-- NO -> @Async @EventListener is viable
    |             |
    |             +-- Are there dependencies between steps?
    |                     +-- YES -> orchestration/completion events
    |                     +-- NO  -> process independently, bound capacity
```

"Tolerate loss on crash?" must be evaluated under the **business contract**, not as if losing tasks were desirable. Best-effort telemetry may accept partial loss under an explicit policy; mandatory invoicing, payments, state transitions, or accounting sync do not.

| Scenario | Usually Appropriate Choice | Why |
| --- | --- | --- |
| Validate order before accepting | Synchronous service call | Caller needs pass/fail immediately |
| Compute totals in same transaction | Synchronous service | May need to roll back with business operation |
| Update fast internal read model | Synchronous listener or direct service | Async overhead may not be worthwhile |
| Emit best-effort telemetry | `@Async @EventListener` | Decouples from request, still needs bounded capacity |
| Send email after order commits | `@Async @TransactionalEventListener(AFTER_COMMIT)` | Avoids notifying for rolled-back orders |
| Mandatory invoice, must survive crashes | Transactional outbox + worker | In-RAM executor lacks sufficient durability guarantees |
| Update cache after DB commit | Sync/async `AFTER_COMMIT` per latency & guarantee | Avoids caching uncommitted data |
| Long image/upload processing | Persist file/job first, background worker | Request-scoped multipart data does not live forever |
| Strict sequence A then B | Service orchestration or `ACompleted` event | `@Order` does not guarantee async completion |
| Consumer in another service | Broker / durable messaging | `ApplicationEventPublisher` is not an inter-JVM bus |

## 5. When Should You Not Use Events?

Events decouple publishers from listeners, yet **not every service call should be converted into an event**.

Example of a business operation that must check a quota before creating a command:

```java
public Receipt submit(Command command) {
    limitService.ensureAllowed(command); // Need to know the result immediately.
    Receipt receipt = commandService.save(command);
    return receipt;
}
```

This is **illustrative code**; classes/services belong to the application. Replacing `ensureAllowed` with an `@Async @EventListener` and returning the receipt before validation finishes alters the business contract and risks accepting invalid commands.

Call a service directly when:

- The caller needs the result to decide the next step.
- Two steps must share the same transaction or critical section.
- Tight coupling is inherent and specific errors must be returned.
- There are neither multiple consumers nor genuine module decoupling needs.
- You need an API returning `Future`/`CompletableFuture` so the caller can wait and compose results.

Events fit when you are **announcing a business fact** and subscribers do not decide whether the main transaction proceeds.

## 6. Hybrid Pattern: `@Async @TransactionalEventListener(AFTER_COMMIT)`

When a task is valid only **after the transaction commits**, use:

```java
@Transactional
public String createOrder(CreateOrder command) {
    String id = repository.insert(command);
    publisher.publishEvent(new OrderCreated(id));
    return id;
}
```

and the listener:

```java
@Async("eventExecutor")
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT)
public void onCommitted(OrderCreated event) {
    notificationService.send(event.orderId());
}
```

These are **illustrative snippets**, requiring a Spring-managed service/listener, transaction manager, `@EnableAsync`, executor, and dependencies.

Key timeline:

```text
Publisher thread
  BEGIN T1
  INSERT Order
  publishEvent(OrderCreated)
       |
       +-- register transaction synchronization callback
  COMMIT T1
       |
       +-- AFTER_COMMIT callback
             |
             +-- submit to executor
                   |
                   +--> worker executes after commit
```

Key distinctions:

- `@TransactionalEventListener` controls the **transaction milestone**, defaulting to `AFTER_COMMIT`.
- `@Async` controls **the thread executing the method body**.
- `@TransactionalEventListener` defaults to `fallbackExecution=false`: publishing **outside a transaction** will **not invoke** that listener.
- T1 rolls back -> `AFTER_COMMIT` listener does not run.
- T1 commits successfully and then the executor rejects/crashes -> T1 is already committed and cannot be rolled back to rescue post-processing.
- With imperative transactions, the worker has its own thread and does not automatically continue the old transaction. For DB writes, open an appropriate transaction on a separate service bean.

**Do not treat `AFTER_COMMIT` as a durable queue.** The callback triggers based on an in-process transaction completion; it does not persist pending tasks across crashes.

## 7. Runnable Java 17+ Example: Synchronous, Async, and Transaction Phases

This example uses **Java 17+**, **Spring Framework 6.2.12**, Spring JDBC, in-memory H2, and Gradle 8+. No Spring Boot, HTTP server, or message broker is needed.

The program demonstrates three flows:

1. **Synchronous listener:** publishes `CheckOrder`, verifies the listener finishes on the publisher thread before `publishEvent` returns; if a listener rejects, the exception reaches the caller.
2. **Asynchronous listener:** publishes `RebuildView`, the worker starts and pauses on a `CountDownLatch`; the publisher continues while the side effect is not yet done.
3. **Transaction-bound listeners:** publishes `OrderStored` in one committing transaction and one rolling-back transaction; observes `AFTER_COMMIT` incrementing only on commit and `AFTER_ROLLBACK` only on rollback.

### 7.1. Structure

```text
spring-sync-or-async-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/SyncAsyncChoiceDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'spring-sync-or-async-demo'
```

`build.gradle`:

```groovy
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
    implementation 'org.springframework:spring-context:6.2.12'
    implementation 'org.springframework:spring-jdbc:6.2.12'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

application {
    mainClass = 'demo.SyncAsyncChoiceDemo'
}
```

H2 and `DriverManagerDataSource` are only suitable for short demos; production requires a persistent DB, connection pooling, and transaction/latency observability.

### 7.2. `src/main/java/demo/SyncAsyncChoiceDemo.java`

```java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

public class SyncAsyncChoiceDemo {

    public record CheckOrder(String id) {}
    public record RejectOrder(String reason) {}
    public record RebuildView(String id) {}
    public record OrderStored(String id) {}

    public static class Probe {
        final AtomicBoolean syncDone = new AtomicBoolean();
        final AtomicReference<String> syncThread =
                new AtomicReference<>("");
        final AtomicBoolean asyncDone = new AtomicBoolean();
        final AtomicReference<String> asyncThread =
                new AtomicReference<>("");
        final AtomicReference<Throwable> asyncError =
                new AtomicReference<>();

        final CountDownLatch asyncStarted = new CountDownLatch(1);
        final CountDownLatch releaseAsync = new CountDownLatch(1);
        final CountDownLatch asyncFinished = new CountDownLatch(1);

        final AtomicInteger afterCommit = new AtomicInteger();
        final AtomicInteger afterRollback = new AtomicInteger();
    }

    public static class DemoListeners {
        private final Probe probe;

        public DemoListeners(Probe probe) {
            this.probe = probe;
        }

        // Default synchronous listener.
        @EventListener
        public void check(CheckOrder event) {
            probe.syncThread.set(Thread.currentThread().getName());
            probe.syncDone.set(true);
        }

        // Synchronous exception propagates to publisher under default multicaster.
        @EventListener
        public void reject(RejectOrder event) {
            throw new IllegalArgumentException("rejected");
        }

        // Async listener: method body runs on an executor thread.
        @Async("eventExecutor")
        @EventListener
        public void rebuild(RebuildView event) {
            probe.asyncThread.set(Thread.currentThread().getName());
            probe.asyncStarted.countDown();

            try {
                if (!probe.releaseAsync.await(30, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "async release timed out");
                }

                // Simulate completing read model/indexing.
                probe.asyncDone.set(true);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                probe.asyncError.compareAndSet(null, ex);
            } catch (RuntimeException ex) {
                probe.asyncError.compareAndSet(null, ex);
            } finally {
                probe.asyncFinished.countDown();
            }
        }

        // Both phase listeners are invoked at transaction completion.
        @TransactionalEventListener(
                phase = TransactionPhase.AFTER_COMMIT)
        public void onCommitted(OrderStored event) {
            probe.afterCommit.incrementAndGet();
        }

        @TransactionalEventListener(
                phase = TransactionPhase.AFTER_ROLLBACK)
        public void onRolledBack(OrderStored event) {
            probe.afterRollback.incrementAndGet();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class AppConfig {

        @Bean
        DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:choice_demo;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource ds) {
            return new DataSourceTransactionManager(ds);
        }

        @Bean
        TransactionTemplate transactionTemplate(
                PlatformTransactionManager manager) {
            return new TransactionTemplate(manager);
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean("eventExecutor")
        ThreadPoolTaskExecutor eventExecutor() {
            ThreadPoolTaskExecutor executor =
                    new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(2);
            executor.setMaxPoolSize(4);
            executor.setQueueCapacity(20);
            executor.setThreadNamePrefix("event-");
            executor.setRejectedExecutionHandler(
                    new ThreadPoolExecutor.AbortPolicy());
            executor.setWaitForTasksToCompleteOnShutdown(true);
            executor.setAwaitTerminationSeconds(30);
            return executor;
        }

        @Bean
        Probe probe() {
            return new Probe();
        }

        @Bean
        DemoListeners demoListeners(Probe probe) {
            return new DemoListeners(probe);
        }
    }

    public static void main(String[] args)
            throws InterruptedException {

        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            Probe probe = context.getBean(Probe.class);
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            TransactionTemplate tx =
                    context.getBean(TransactionTemplate.class);
            String publisherThread = Thread.currentThread().getName();

            jdbc.execute(
                    "create table orders ("
                    + "order_id varchar(40) primary key)");

            // 1) Synchronous: listener finishes right inside publishEvent.
            context.publishEvent(new CheckOrder("O-1"));
            System.out.println("sync completed on return="
                    + probe.syncDone.get());
            System.out.println("sync on publisher thread="
                    + publisherThread.equals(probe.syncThread.get()));

            // Exception from synchronous listener reaches the caller.
            boolean propagated = false;
            try {
                context.publishEvent(new RejectOrder("bad"));
            } catch (IllegalArgumentException ex) {
                propagated = "rejected".equals(ex.getMessage());
            }
            System.out.println("sync exception propagated="
                    + propagated);

            // 2) Async: worker awaits latch while caller continues.
            try {
                context.publishEvent(new RebuildView("O-1"));

                if (!probe.asyncStarted.await(30, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "async listener did not start");
                }

                System.out.println("async completed before release="
                        + probe.asyncDone.get());
                System.out.println("async on publisher thread="
                        + publisherThread.equals(probe.asyncThread.get()));

                // 3) Transaction commit and rollback.
                tx.executeWithoutResult(status -> {
                    jdbc.update(
                            "insert into orders (order_id) values (?)",
                            "O-1");
                    context.publishEvent(new OrderStored("O-1"));
                });

                tx.executeWithoutResult(status -> {
                    jdbc.update(
                            "insert into orders (order_id) values (?)",
                            "O-2");
                    context.publishEvent(new OrderStored("O-2"));
                    status.setRollbackOnly();
                });

                Integer committedRows = jdbc.queryForObject(
                        "select count(*) from orders", Integer.class);

                System.out.println("orders committed=" + committedRows);
                System.out.println("AFTER_COMMIT callbacks="
                        + probe.afterCommit.get());
                System.out.println("AFTER_ROLLBACK callbacks="
                        + probe.afterRollback.get());
            } finally {
                // Even if main fails, release worker before shutdown.
                probe.releaseAsync.countDown();
            }

            if (!probe.asyncFinished.await(30, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "async listener did not finish");
            }
            if (probe.asyncError.get() != null) {
                throw new IllegalStateException(
                        "async worker failed", probe.asyncError.get());
            }

            System.out.println("async completed after release="
                    + probe.asyncDone.get());
        }
    }
}
```

### 7.3. How to Run

In the project directory containing `build.gradle`:

```bash
gradle -q run
```

Lines printed by the program itself in the demo configuration:

```text
sync completed on return=true
sync on publisher thread=true
sync exception propagated=true
async completed before release=false
async on publisher thread=false
orders committed=1
AFTER_COMMIT callbacks=1
AFTER_ROLLBACK callbacks=1
async completed after release=true
```

Gradle or Spring logging may print extra messages. Those nine lines are the stdout produced by the program's `System.out.println` calls, not an absolute promise that the console has only nine lines.

### 7.4. Why Is the Output Deterministic?

**Synchronous listener:**

- The context publishes a `CheckOrder` record.
- `DemoListeners` has a matching `@EventListener` method. With the default multicaster, it executes on the publisher thread and sets `syncDone=true`.
- `publishEvent` returns **after** that handler completes, so the first two lines print `true`.
- Publishing `RejectOrder` makes the synchronous listener throw `IllegalArgumentException`. With no custom error handler configured, the exception propagates to the caller; line three prints `true`.

**Async listener:**

- `@EnableAsync` registers the async interceptor. `@Async("eventExecutor")` routes `rebuild` to a worker of `ThreadPoolTaskExecutor`.
- The worker records its thread name, opens `asyncStarted`, and waits on `releaseAsync`.
- `main` awaits `asyncStarted`, proving the worker truly started; `asyncDone` remains `false` because the worker has not yet been released.
- The worker name has prefix `event-`, different from the publisher thread. Hence "async on publisher thread" is `false`.
- After the transaction section, `main` opens `releaseAsync` inside `finally`. The worker sets `asyncDone=true` and opens `asyncFinished`; `main` awaits the latch before printing the final line.

**Transaction phase:**

- `TransactionTemplate.executeWithoutResult(...)` creates real JDBC transactions via `DataSourceTransactionManager`.
- In the first transaction, the code inserts `O-1` and publishes `OrderStored`. `AFTER_COMMIT` waits for T1 to commit, then increments its counter.
- In the second transaction, the code inserts `O-2` and publishes `OrderStored`, yet `status.setRollbackOnly()` rolls T2 back. `AFTER_ROLLBACK` increments its counter while `AFTER_COMMIT` does not.
- The DB holds only `O-1` after both transactions, so `orders committed=1`.

**Limitations:** The program intentionally uses `Probe`/latches and performs no real HTTP side effects. It demonstrates thread, exception, and transaction-phase semantics; it **does not prove** queue durability across JVM death or real executor throughput under load.

## 8. Understanding the Four Meanings of "Success"

One of the most common mistakes is saying "finished processing" for four distinct milestones:

```text
Business code emits event
   |
   +-- publishEvent(...) called
         |
         +-- Listener task accepted by executor (accepted)
               |
               +-- Listener begins execution (started)
                     |
                     +-- Side effect finishes (completed)
                           |
                           +-- Outcome durably persisted (committed/acked)
```

- `publishEvent(...)` returns `void`, not the number of successful listeners.
- With the default synchronous listener, `publishEvent` waits for that handler to finish; yet external side effects enqueued by the handler may still be unfinished.
- With `@Async`, the publisher does not automatically know the handler's final outcome.
- Executor acceptance does not mean the task has started.
- Task completion does not mean the outcome is committed if the handler fails to manage transactions/ACKs properly.
- A message broker ACK does not prove every downstream consumer finished its business work.

When the caller **genuinely needs to wait for the result**, use an API returning a service-controlled `CompletableFuture`/`Future`, or a durable job ID/status. Never try to extract a future from `ApplicationEventPublisher.publishEvent(...)`, because the API returns `void`.

## 9. Exceptions and Rollbacks: Key Differences

| Aspect | Default Sync Listener | `@Async @EventListener` | `@Async @TransactionalEventListener(AFTER_COMMIT)` |
| --- | --- | --- | --- |
| Caller waits for method body? | Yes | No | Does not wait for body after submission |
| Method body exception reaches caller? | Usually yes if uncaught / no error handler | Does not propagate automatically | Does not propagate automatically from async worker |
| Shares publisher transaction? | Yes if published on a transactional thread | Does not inherit transaction automatically | Runs only after transaction commits; body runs on worker |
| Can roll back T1? | Yes if exception propagates inside T1 pre-commit and rollback rules match | Usually not, runs on another worker | No, T1 already committed |
| Can run before commit? | Yes | Yes | No, for events registered inside T1 |
| Queue survives crash? | Not a queue | No | No |
| Thread context / MDC | Usually publisher thread | Does not propagate automatically | Does not propagate automatically |

### 9.1. A Failing Sync Listener Does Not Guarantee Rolling Everything Back

If a synchronous `@EventListener` throws an exception, the transaction interceptor may roll back the DB if the exception escapes and matches rollback rules. However:

- If the publisher catches and swallows the exception, the transaction may continue or already be marked rollback-only by another component.
- If the listener already sent an email or HTTP call before failing, external side effects do not roll back automatically.
- If the multicaster has a custom `ErrorHandler`, exception handling differs from the default.
- If the listener runs outside a transaction, there is no DB transaction to roll back.

**For critical pre-commit invariants, an explicit synchronous service call is usually clearer than an event.**

### 9.2. Errors in `void @Async` Methods

```java
@Async("eventExecutor")
@EventListener
public void onEmailRequested(EmailRequested event) {
    mailClient.send(event.messageId());
}
```

This is **illustrative code**. If `mailClient.send(...)` throws inside the worker, the caller of `publishEvent(...)` will not receive that exception along the normal call path.

Spring supports `AsyncUncaughtExceptionHandler`:

```java
@Configuration
@EnableAsync
public class AsyncErrorConfig implements AsyncConfigurer {

    @Override
    public AsyncUncaughtExceptionHandler
            getAsyncUncaughtExceptionHandler() {
        return (ex, method, args) -> {
            System.err.println("async method failed: "
                    + method.getName() + ": " + ex.getMessage());
        };
    }
}
```

This is illustrative code requiring imports for `AsyncConfigurer`, `AsyncUncaughtExceptionHandler`, and annotations. In production, use structured logging, trace/event IDs, metrics, retry states, and alerts; printing to `System.err` is insufficient when a job is mandatory.

An `@Async @EventListener` **does not support auto-publishing a follow-up event via its return value**. If the worker needs to emit `EmailSent`, inject the publisher and call `publishEvent(new EmailSent(...))` after completion, or write the resulting event to an outbox if durability is required.

## 10. `@Order` and Completion Order

For synchronous listeners on the same multicaster, you can use `@Order` to prioritize **invocation** order:

```java
@Order(0)
@EventListener
public void before(OrderChanged event) {
    // Listener prioritized earlier.
}

@Order(10)
@EventListener
public void after(OrderChanged event) {
    // Listener prioritized later.
}
```

This is illustrative code.

However, if the `@Order(0)` listener uses `@Async`, the dispatcher may **submit** its task and immediately invoke the `@Order(10)` listener **before the async task finishes**. Never use `@Order` as a mechanism to guarantee side effect B happens after side effect A.

If B must run **only after A succeeds**, you can:

1. Call service A then service B directly in sequence if the workflow is linear.
2. Have worker A publish **`ACompleted`** after succeeding; B listens to that outcome event.
3. Use a state machine/workflow engine with persistent state when retries, compensation, multiple prerequisites, or multiple services are involved.
4. With DB transactions, publish the outcome event inside the right transaction and handle post-commit per contract.

Never rely on `Thread.sleep(...)`, a static boolean flag, or increasing worker counts to "guarantee" ordering.

## 11. Thread Context and Payloads: What Does Not Automatically Flow to Workers?

In Spring MVC/security applications, many contexts are thread-bound:

- `RequestContextHolder` and request-scoped beans;
- `SecurityContextHolder` under its default strategy;
- MDC/tracing context unless propagation is configured;
- imperative `PlatformTransactionManager` transaction resources;
- `EntityManager`/Hibernate persistence context tied to the transaction.

A bad event:

```java
public record OrderChanged(
        String orderId,
        HttpServletRequest request) {}
```

This is a **counter-example**, not a recommendation. `HttpServletRequest` belongs to the HTTP request lifecycle and can be mutable. Workers running after the response must not retain requests, sessions, `MultipartFile`, or input streams.

Capture an **immutable snapshot** from validated, authorized data:

```java
public record OrderChanged(
        String orderId,
        String eventId,
        String verifiedActorId,
        String verifiedTenantId) {}
```

This DTO does not depend on Servlet requests. For collections, perform defensive copies and make nested elements immutable where needed. Never take raw tenant/user IDs from untrusted headers as access permissions.

If you only need log/tracing context, consider `TaskDecorator` or Micrometer Context Propagation with proper accessor and cleanup setup. **Context propagation neither makes request objects durable nor turns T1 into a transaction on the worker thread.**

## 12. `@Async` on Listeners vs. a Multicaster Executor

There are two independent places to configure async behavior:

### 12.1. `@Async` Per Method

```java
@Async("mailExecutor")
@EventListener
public void sendMail(MailRequested event) {
    // Only this listener is routed to mailExecutor.
}
```

Pros: isolates executors by workload and simplifies capacity control. Requires `@EnableAsync` and a Spring-managed bean proxy. Self-invocation `this.sendMail(...)` bypasses the default async proxy.

### 12.2. Context-Wide Executor on `SimpleApplicationEventMulticaster`

```java
@Bean(name = "applicationEventMulticaster")
ApplicationEventMulticaster applicationEventMulticaster(
        @Qualifier("eventExecutor") TaskExecutor executor) {

    SimpleApplicationEventMulticaster multicaster =
            new SimpleApplicationEventMulticaster();
    multicaster.setTaskExecutor(executor);
    return multicaster;
}
```

This is an **illustrative snippet**, requiring imports for `ApplicationEventMulticaster`, `SimpleApplicationEventMulticaster`, `TaskExecutor`, `Qualifier`, and `Bean`.

This affects **many listeners** at once; not every listener is safe to run asynchronously on the multicaster. Spring Framework provides `ApplicationListener.supportsAsyncExecution()`, and transaction-synchronized listeners require an appropriate thread to register synchronizations.

**Do not enable both `@Async` and a multicaster executor on the same listener without understanding double scheduling.** Two queuing layers can increase latency, complicate queue metrics, scatter error/rejection handling, and muddle thread context management.

Spring's synchronous default is an intentional feature to avoid silently changing transaction/context semantics when an application only wants internal events.

## 13. Capacity and Overload: Async Is Not Infinite Throughput

An executor must have bounds:

```java
executor.setCorePoolSize(4);
executor.setMaxPoolSize(12);
executor.setQueueCapacity(200);
executor.setRejectedExecutionHandler(
        new ThreadPoolExecutor.AbortPolicy());
```

This is an illustrative snippet, not optimal tuning for every machine. Use `ThreadPoolTaskExecutor`; imports follow Spring/Java concurrency.

### 13.1. Understanding Core, Max, and Queue

With standard `ThreadPoolExecutor` mechanics:

1. While workers are below `corePoolSize`, the executor creates core workers.
2. Once core workers are full, the executor normally **queues tasks** first.
3. Once the queue is full, the executor spawns additional workers up to `maxPoolSize`.
4. Once both max threads and queue are full, the rejection policy governs behavior.

`ThreadPoolTaskExecutor` has a very large/unbounded default queue capacity. Without configuring a bounded queue, `maxPoolSize` rarely takes effect; backlog, memory, and queue wait grow without visible rejections.

### 13.2. Rejection Is Not Trivial

| Rejection Policy | Behavior When Full | Consequence |
| --- | --- | --- |
| `AbortPolicy` | Throws rejection exception | Caller/bridge must handle; makes overload visible |
| `CallerRunsPolicy` | Caller may run task itself if not shut down | Creates backpressure but increases request latency / alters thread semantics |
| `DiscardPolicy` | Drops task | May silently lose work |
| `DiscardOldestPolicy` | Drops oldest queued task | Can break ordering/reliability requirements |

With `ThreadPoolTaskExecutor`, rejection typically surfaces as `TaskRejectedException` on the submission path. **Especially with `AFTER_COMMIT`:** when a task is rejected, the source transaction has already committed; you cannot roll back the order just because sending an email was rejected.

### 13.3. Sizing Based on Load

A rough estimate for busy concurrency:

\[
C_{\text{busy}} \approx \lambda S
\]

where \(\lambda\) is incoming events/second and \(S\) is average service time in seconds/event.

Example: 120 events/s, handler takes 0.05s on average -> roughly 6 busy workers **under an ideal model**. If you run exactly 6 workers near 100% utilization, any burst quickly builds a queue. Leave headroom and measure p95/p99 latency, CPU, HTTP client/DB pools, and rate limits; do not just plug numbers into a formula and assume sufficient throughput.

For CPU-bound jobs, adding threads beyond CPU resources may only increase context switching. For I/O-bound jobs, useful thread count can be higher, yet remains capped by connection pools and downstream concurrency.

## 14. Reliability: When Is Async Not Enough and When Do You Need an Outbox?

`@Async @TransactionalEventListener(AFTER_COMMIT)` is a clean pattern for **best-effort post-processing**, yet still has task-loss windows:

```text
T1 COMMIT
   |
   +-- JVM crashes before callback submits task
   |
   +-- executor queue full and rejects
   |
   +-- task accepted, then JVM crashes before execution
   |
   +-- worker calls external API successfully, crashes before writing DONE
```

If a task **must be executed**, write the processing intent to the **DB in the same transaction as the primary business work**:

```text
BEGIN T1
  +-- INSERT order
  +-- INSERT outbox(eventId, aggregateId, type, payload, status=NEW)
COMMIT T1
   |
   +-- relay worker reads outbox in batches/leases
         |
         +-- execute task with idempotency key
         +-- success -> mark DONE
         +-- transient failure -> RETRY/backoff
         +-- permanent failure -> FAILED/DLQ/alert
```

A committed outbox row survives restarts. However, the relay may redeliver after a crash occurring between side-effect success and marking `DONE`, so consumers/operations must be **idempotent**. An outbox guarantees **not losing intent** on commit; it does not automatically create exactly-once external side effects.

Real `post_jobs`/outbox tables should include `eventId/jobId`, `aggregateId`, `status`, `attempts`, `nextAttemptAt`, `lastError`, timestamps/lease fields, and appropriate unique indexes. Do not call `Thread.sleep(...)` inside an executor worker to wait out long retries; a scheduler/persistent queue is far more effective.

If work must be delivered to another service, a broker such as Kafka/RabbitMQ/JMS may fit, yet **synchronizing DB commits with broker publishing still requires its own solution**, such as outbox + relay.

## 15. Monitoring: Measure Completion Instead of Just Publishing

To choose and sustain the right design, observe:

| Metric | Question |
| --- | --- |
| Publish rate | How many events are being created? |
| Accepted/submitted rate | How many tasks does the executor accept? |
| Active threads | How busy is the pool? |
| Queue depth/capacity | What is the current backlog and remaining headroom? |
| Queue wait p95/p99 | How long do events wait before starting? |
| Handler latency p95/p99 | How long does actual execution take? |
| Completed/s | How many tasks finish successfully? |
| Rejected/s | How many tasks are turned away by the pool? |
| Failure/retry count | How many tasks fail or must be retried? |
| Oldest pending job age | Is any job stuck for too long? |
| DB/HTTP downstream utilization | Is the bottleneck in the executor or another dependency? |

**A fast 200 API response does not prove email/indexing succeeded.** If the business needs to know status, provide a job ID and explicit processing status. Even for best-effort work, minimal error/queue metrics are needed to avoid silent task loss.

## 16. Testing Sync/Async Choices Properly

### 16.1. Testing Synchronous Behavior

- Mock `ApplicationEventPublisher` to verify the service emits the right type/payload/count.
- With a real context, call `publishEvent` and assert the synchronous handler updated state by the time the call returns.
- Emit an exception-triggering event and confirm the caller receives the error under default settings.
- If the listener participates in a transaction, test rollback to verify DB state directly; do not infer rollback from the presence or absence of logs.

### 16.2. Testing Asynchronous Behavior

Do not write:

```java
publisher.publishEvent(new RebuildView("O-1"));
Thread.sleep(100);
assertTrue(indexUpdated);
```

This is a **counter-example**, because scheduler jitter, CI load, or downstream delays make the test flaky.

Use `CountDownLatch`, `CompletableFuture`, Awaitility, or a controlled test executor:

1. Hold the worker on a latch to prove the caller can continue.
2. Observe callback start with a dedicated latch.
3. Release the latch after asserting pre-completion state.
4. Await the completion latch and assert the final side effect.
5. Test timeout, failure, and rejection paths.

The Section 7 example uses three latches (`asyncStarted`, `releaseAsync`, `asyncFinished`) to avoid guessing with `Thread.sleep`.

### 16.3. Testing Transaction Phases

Spring Test supports `@RecordApplicationEvents` with `ApplicationEvents.stream(EventType.class)` to verify events **were published** in the context. However, the recorder proves neither that async listeners finished nor that transactions committed.

For `@TransactionalEventListener`:

- Real commit -> `AFTER_COMMIT` runs properly.
- Rollback -> `AFTER_COMMIT` does not run; `AFTER_ROLLBACK` may run.
- Publish outside transaction -> listener skips by default when `fallbackExecution=false`.
- Spring Test methods annotated with `@Transactional` typically roll back at test end. When you need a commit inside a test, use `TestTransaction.flagForCommit(); TestTransaction.end();` inside an active test-managed transaction.
- Even after commit, await async completion separately; `TestTransaction.end()` does not wait for async workers.

### 16.4. Load Testing and Crash Testing

For production, also test sustained load, bursts, executor queue saturation, downstream timeouts, retry storms, deploy/shutdown, JVM restarts, and duplicates. If a critical job exists only in RAM, crash testing will expose architectural gaps that unit tests can never patch over with `@Order` or higher `maxPoolSize`.

## 17. Common Troubleshooting Table

| Symptom | Likely Cause | How to Fix |
| --- | --- | --- |
| Request slows down when publishing event | Sync listener performs slow I/O | Move auxiliary work to async/outbox if domain allows |
| Async event runs on publisher thread | Missing `@EnableAsync`, self-invocation, proxy not applied | Check bean/proxy/executor and thread name |
| Worker reads order but DB lacks record | Async listener ran before commit | Switch to `AFTER_COMMIT` or outbox |
| `AFTER_COMMIT` listener does not run | Published outside transaction or T1 rolled back | Check active transaction at publish time and phase |
| Email sent despite DB rollback | Used `@Async @EventListener` unbound to commit | Switch to post-commit if required |
| Caller misses errors inside worker | `void @Async` exception occurred on another thread | `AsyncUncaughtExceptionHandler`, failure state/metrics |
| Raising `maxPoolSize` leaves queue piling up | Unbounded queue keeps pool near core size | Bounded queue and load-tested sizing |
| Queue full, order saved but notification lost | Rejection occurred after commit | Outbox / durable recovery path |
| Event has `@Order` yet side effects run out of order | Async completion differs from invocation order | Use completion events / orchestration |
| Listener lacks MDC/`RequestContext` | `ThreadLocal` does not propagate automatically | Immutable payload and context propagation for observability |
| Worker fails on lazy JPA entity | Persistence context closed or on wrong thread | Snapshot DTO/ID; open dedicated transaction to query |
| App restart loses pending work | Tasks lived only in executor memory | Durable job store / outbox |
| Flaky async test | Asserting too early or using `Thread.sleep` | Latch/future with timeout |
| Async handler returns event yet no new event fires | Async listeners do not support return-value auto-publish | Call `ApplicationEventPublisher` explicitly |

## 18. Checklist for Choosing Sync vs. Async

- [ ] Does the caller need the result **before returning a response or committing**?
- [ ] Is the task a mandatory invariant or an independent notification?
- [ ] If synchronous, could a slow/failing listener break the primary business flow?
- [ ] If asynchronous, could the event execute **before commit**? Is that safe?
- [ ] If post-commit is needed, is the event published **inside the right transaction**?
- [ ] Does the event contain immutable DTOs/IDs rather than mutable requests/sessions/JPA entities?
- [ ] Are `@EnableAsync`, a dedicated executor bean, and clear queue/rejection policies configured?
- [ ] Are error handling, retries, idempotency, and success/failure states implemented?
- [ ] If tasks must survive JVM crashes, is a durable outbox/queue used?
- [ ] If ordering/dependencies exist, are completion events/orchestration used instead of `@Order` alone?
- [ ] Are queue wait, completed, failed, rejected, and p95/p99 latency metrics tracked?
- [ ] Do tests separate **publishing**, **transaction commit**, and **async completion**?

**Conclusion:** Choose **synchronous** when the caller must know the result/error immediately and processing latency is acceptable; if it is a mandatory invariant, a direct service call is usually clearer than an event. Choose **`@Async @EventListener`** for auxiliary work that can run later and does not depend on commit. Choose **`@Async @TransactionalEventListener(AFTER_COMMIT)`** when the task is valid only after DB commit. If the task must survive crashes, an in-RAM executor is insufficient: use a **durable transactional outbox/job**, retries/idempotency, and state observability.

## References

- [Spring Framework 6.2 — ApplicationContext Events, Default Synchronous Dispatch, Async Listeners, and `@Order`](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework 6.2 — Task Execution and Scheduling, `@Async`](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [Spring Framework 6.2 — `SimpleApplicationEventMulticaster`](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework 6.2 — `ThreadPoolTaskExecutor`](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework 6.2 — Transaction Propagation and `REQUIRES_NEW`](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework 6.2 — Testing Application Events](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/application-events.html)
- [Java SE 17 — `ThreadPoolExecutor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
