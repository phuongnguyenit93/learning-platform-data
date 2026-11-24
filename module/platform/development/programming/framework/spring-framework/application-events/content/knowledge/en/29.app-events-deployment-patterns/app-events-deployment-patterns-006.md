# Running Asynchronous Post-Processing Tasks in Spring Framework Application Events

## 1. Problem Statement and Design Goals

In the **Deployment Patterns** group of **Spring Framework Application Events**, a "post-processing task" is work that **does not need to finish before a primary business operation returns its result**:

- Sending an email or notification after creating an order.
- Updating a search index, cache, or read model.
- Recording supplementary logs/audits.
- Syncing information with a CRM or webhook.
- Generating reports, thumbnails, or derived data.
- Triggering a downstream workflow after primary state is persisted.

If these tasks run synchronously inside the order-creation transaction, user latency increases and a transient failure in a secondary service can unnecessarily fail the primary business operation.

However, **"post-processing" has three distinct meanings**, so choose carefully:

1. **After the event is published:** an `@Async @EventListener` is submitted to an executor as soon as the publisher emits the event; the listener may start **before the source transaction commits**.
2. **After the transaction commits successfully:** a `@TransactionalEventListener(phase = AFTER_COMMIT)` triggers only when the event-emitting transaction completes with a commit. Combined with `@Async`, the work executes on a worker thread.
3. **After the HTTP response is returned:** a task may still be queued, running, or already finished before the response actually flushes; do not equate `@Async` with a callback that "runs strictly after the response is flushed."

A sound design must specify the **valid start milestone**, **task durability**, **error handling**, **executor bounds**, **idempotency**, and **testing strategy**.

This guide focuses on the common pattern: *an order commits successfully, and then a worker performs supplementary work asynchronously*, accompanied by a runnable Java 17+ example.

## 2. Choosing Listener Style by Business Timing

| Style | When It Can Run | Good Fit For | What to Watch Out For |
| --- | --- | --- | --- |
| Plain `@EventListener` | Immediately upon publish, synchronous by default | Fast internal logic needing immediate feedback | Extends transaction/request duration |
| `@Async @EventListener` | Submitted immediately upon publish | Independent work that need not wait for commit | Worker may read DB before commit or run despite rollback |
| `@TransactionalEventListener(AFTER_COMMIT)` | After successful commit, synchronous callback by default | Side effects depending on committed data | May block the thread completing the transaction |
| **`@Async @TransactionalEventListener(AFTER_COMMIT)`** | **Submits work only after commit**, runs on executor | Notifications, indexing, post-commit callbacks | Queue still lives in RAM; failures do not roll back DB; needs monitoring and recovery |
| Transactional outbox + worker | Worker reads durably committed work requests | Work that must not be lost on process crash | Must design relay, retries, states, and idempotency |
| Broker / durable queue | Dispatches work to external messaging system | Multiple services/consumers, independent recovery and scaling | Syncing DB with messages needs outbox/transaction strategy |

**Rule of thumb:** If a listener only performs small, synchronous work that does not depend on commit, do not add async needlessly. If it must read **committed** data, use a post-commit phase or a persisted work item; do not just slap `@Async` onto a listener emitted inside a transaction.

## 3. How `@Async` Works with Spring Application Events

When using the `@Async` infrastructure, Spring invokes the method via an async proxy and submits the invocation to a `TaskExecutor`. The handler can continue running on a background thread after the caller returns.

```java
@Component
public class NotificationListener {

    @Async("postExecutor")
    @EventListener
    public void onOrderCreated(OrderCreated event) {
        notificationClient.send(event.orderId());
    }
}
```

This is an **illustrative snippet**, not a standalone program. It requires a Spring-managed bean, `@EnableAsync`, an executor bean named `postExecutor`, the `OrderCreated` event type, and `notificationClient`.

This approach is asynchronous **from the moment the event is published**, without any commit condition. For example:

```text
Request thread                         Worker thread
  BEGIN transaction T1
      |
      +-- INSERT order
      +-- publishEvent(OrderCreated)
      |        |
      |        +-- submit async task -----> listener may execute
      |                                          |
      |                                          +-- SELECT order
      |                                               may not see T1 commit
      |
      +-- an error occurs
      +-- ROLLBACK T1
```

The worker may already have sent an "order created" email even though the transaction later rolled back. This is not a Spring bug: `@Async` only switches threads; it carries no commit contract.

### 3.1. Enable Async and Name the Executor Explicitly

```java
@Configuration
@EnableAsync
public class AsyncConfig {

    @Bean("postExecutor")
    public ThreadPoolTaskExecutor postExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(6);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("post-");
        return executor;
    }
}
```

This is an **illustrative configuration snippet**; appropriate Spring imports are required. The numbers are examples, not optimal production defaults. If `@EnableAsync` is missing or code calls `this.asyncMethod()` inside the same bean, async advice may not be applied. Use a Spring-managed bean and call through the proxy.

`@Async("postExecutor")` prevents accidentally running on another default executor when multiple executors exist in the system.

## 4. Key Pattern: `@Async` + `@TransactionalEventListener(AFTER_COMMIT)`

Primary pattern:

```java
@Transactional
public void createOrder(String orderId) {
    repository.insert(orderId);
    publisher.publishEvent(new OrderCreated(orderId));
}

@Async("postExecutor")
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT)
public void onOrderCommitted(OrderCreated event) {
    notificationService.send(event.orderId());
}
```

This is **illustrative code**, consisting of two methods on appropriate Spring-managed beans; it requires a transaction manager, repository, publisher, executor, and annotation configuration.

Lifecycle:

```text
Thread calling OrderService
  |
  +-- BEGIN T1
  +-- INSERT order
  +-- publishEvent(OrderCreated)
  |     |
  |     +-- AFTER_COMMIT listener registers to await transaction T1
  |
  +-- Exit service method body
  +-- COMMIT T1 succeeds
  |
  +-- AFTER_COMMIT callback
  |     |
  |     +-- async proxy SUBMITs task to postExecutor
  |
  +-- cleanup and return to caller
                           |
                           v
                    Executor worker
                           |
                           +-- receive event DTO
                           +-- read committed data
                           +-- run notification/indexing/audit
                           +-- persist status or handle errors separately
```

**Key point:** `AFTER_COMMIT` controls **when the event listener is triggered**, while `@Async` controls **where the method body runs**. They solve two different problems.

If T1 rolls back, `AFTER_COMMIT` is not triggered. If the event is published **outside a transaction**, the transaction-bound listener is **ignored by default** (`fallbackExecution=false`), because Spring has no transaction completion to wait on.

Do not set `fallbackExecution=true` just "to make it run." Without a transaction, it no longer provides an "after commit" guarantee.

### 4.1. Why Does the Listener Not Automatically Inherit Transaction T1?

In a Spring application using an imperative `PlatformTransactionManager`, the transaction context is typically thread-bound. The executor worker runs on **another thread**, so it does not automatically join transaction T1.

Moreover, T1 has already committed. If the worker needs to write to a status table, run it inside a **new transaction**:

```java
@Service
public class JobStatusWriter {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void markDone(String jobId) {
        // Update/insert task status in the DB.
    }
}
```

This is an illustrative snippet; `JobStatusWriter` should be a **separate** Spring-managed bean invoked via proxy. Do not use self-invocation `this.markDone(...)` if you expect `@Transactional` to be intercepted in default proxy mode.

On a worker thread with no active transaction, a `@Transactional` method with `REQUIRED` propagation can also open a new transaction. Using `REQUIRES_NEW` here expresses **the intent to create an independent transaction** and avoids depending on the caller's context; it is especially critical for writes from a synchronous post-commit callback on the publisher thread where T1 resources might still be bound before cleanup.

## 5. Complete Java 17+ Example: Successful Commit Triggers Async Post-Processing

This example requires no Spring Boot or web server, and uses:

- JDK 17+.
- Spring Framework **6.2.12** (`spring-context`, `spring-jdbc`, `spring-tx` via transitive dependencies).
- In-memory H2 to simulate DB transactions.
- `ThreadPoolTaskExecutor` with bounded queue and thread count.
- `@EnableAsync`, `@EnableTransactionManagement`.
- `@TransactionalEventListener(AFTER_COMMIT)` combined with `@Async`.
- A `@Transactional(REQUIRES_NEW)` writer bean to record post-processing results.
- `CountDownLatch` to prove **the service returns while the background task has not yet finished**, without arbitrary sleep timers.

### 5.1. Project Structure

```text
spring-async-post-processing-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/AfterCommitAsyncDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'spring-async-post-processing-demo'
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
    mainClass = 'demo.AfterCommitAsyncDemo'
}
```

This is a Gradle project using plain Spring Framework libraries. In-memory H2/`DriverManagerDataSource` is strictly for learning: production apps require a persistent DB, connection pooling, timeouts, and status observability.

### 5.2. `src/main/java/demo/AfterCommitAsyncDemo.java`

```java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import javax.sql.DataSource;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

public class AfterCommitAsyncDemo {

    public record OrderCreated(String orderId) {}

    public static class Probe {
        final CountDownLatch workerStarted = new CountDownLatch(1);
        final CountDownLatch releaseWork = new CountDownLatch(1);
        final CountDownLatch workerFinished = new CountDownLatch(1);

        final AtomicInteger listenerStarts = new AtomicInteger();
        final AtomicBoolean committedOrderVisible =
                new AtomicBoolean(false);
        final AtomicReference<String> workerName =
                new AtomicReference<>("");
        final AtomicReference<Throwable> error =
                new AtomicReference<>();
    }

    public static class OrderService {
        private final JdbcTemplate jdbc;
        private final ApplicationEventPublisher publisher;

        public OrderService(
                JdbcTemplate jdbc,
                ApplicationEventPublisher publisher) {
            this.jdbc = jdbc;
            this.publisher = publisher;
        }

        @Transactional
        public void create(String orderId, boolean forceRollback) {
            jdbc.update(
                    "insert into purchase_orders (order_id) values (?)",
                    orderId);
            publisher.publishEvent(new OrderCreated(orderId));

            if (forceRollback) {
                throw new IllegalStateException("rollback requested");
            }
        }
    }

    public static class PostWorkWriter {
        private final JdbcTemplate jdbc;

        public PostWorkWriter(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        // Write post-processing state in an independent transaction.
        @Transactional(propagation = Propagation.REQUIRES_NEW)
        public void recordCompleted(String orderId) {
            jdbc.update(
                    "insert into completed_post_work "
                    + "(order_id, result) values (?, ?)",
                    orderId, "DONE");
        }
    }

    public static class PostCommitListener {
        private final JdbcTemplate jdbc;
        private final PostWorkWriter writer;
        private final Probe probe;

        public PostCommitListener(
                JdbcTemplate jdbc,
                PostWorkWriter writer,
                Probe probe) {
            this.jdbc = jdbc;
            this.writer = writer;
            this.probe = probe;
        }

        @Async("postExecutor")
        @TransactionalEventListener(
                phase = TransactionPhase.AFTER_COMMIT)
        public void onCreated(OrderCreated event) {
            probe.listenerStarts.incrementAndGet();
            probe.workerName.set(Thread.currentThread().getName());
            probe.workerStarted.countDown();

            try {
                // Worker has started but actively waits for signal from main.
                if (!probe.releaseWork.await(10, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "worker release timed out");
                }

                Integer found = jdbc.queryForObject(
                        "select count(*) from purchase_orders "
                        + "where order_id = ?",
                        Integer.class, event.orderId());

                probe.committedOrderVisible.set(
                        found != null && found == 1);

                writer.recordCompleted(event.orderId());
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                probe.error.compareAndSet(null, ex);
            } catch (RuntimeException ex) {
                probe.error.compareAndSet(null, ex);
            } finally {
                probe.workerFinished.countDown();
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    @EnableAsync
    public static class AppConfig {

        @Bean
        DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl(
                    "jdbc:h2:mem:post_work;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource ds) {
            return new DataSourceTransactionManager(ds);
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean("postExecutor")
        ThreadPoolTaskExecutor postExecutor() {
            ThreadPoolTaskExecutor executor =
                    new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(2);
            executor.setMaxPoolSize(4);
            executor.setQueueCapacity(50);
            executor.setThreadNamePrefix("post-");
            executor.setRejectedExecutionHandler(
                    new ThreadPoolExecutor.AbortPolicy());
            executor.setWaitForTasksToCompleteOnShutdown(true);
            executor.setAwaitTerminationSeconds(10);
            return executor;
        }

        @Bean
        Probe probe() {
            return new Probe();
        }

        @Bean
        OrderService orderService(
                JdbcTemplate jdbc,
                ApplicationEventPublisher publisher) {
            return new OrderService(jdbc, publisher);
        }

        @Bean
        PostWorkWriter postWorkWriter(JdbcTemplate jdbc) {
            return new PostWorkWriter(jdbc);
        }

        @Bean
        PostCommitListener postCommitListener(
                JdbcTemplate jdbc,
                PostWorkWriter writer,
                Probe probe) {
            return new PostCommitListener(jdbc, writer, probe);
        }
    }

    private static int count(JdbcTemplate jdbc, String sql) {
        return jdbc.queryForObject(sql, Integer.class);
    }

    public static void main(String[] args)
            throws InterruptedException {

        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            OrderService orders = context.getBean(OrderService.class);
            Probe probe = context.getBean(Probe.class);

            jdbc.execute(
                    "create table purchase_orders ("
                    + "order_id varchar(40) primary key)");

            jdbc.execute(
                    "create table completed_post_work ("
                    + "order_id varchar(40) primary key, "
                    + "result varchar(20) not null)");

            String workCountSql =
                    "select count(*) from completed_post_work";
            String orderCountSql =
                    "select count(*) from purchase_orders";

            // T1 commits: post-commit callback submits async task.
            orders.create("A", false);

            if (!probe.workerStarted.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "async listener did not start");
            }

            // Worker A is waiting on releaseWork, has not written post-work yet.
            System.out.println("service A returned=true");
            System.out.println("post work before release="
                    + count(jdbc, workCountSql));

            try {
                // T2 rolls back: AFTER_COMMIT does not submit task B.
                boolean rollbackCaught = false;
                try {
                    orders.create("B", true);
                } catch (IllegalStateException ex) {
                    rollbackCaught = true;
                }

                System.out.println("rollback B caught="
                        + rollbackCaught);
                System.out.println("orders after rollback="
                        + count(jdbc, orderCountSql));
                System.out.println("listener starts before release="
                        + probe.listenerStarts.get());
            } finally {
                // Ensure worker A is released even if main fails.
                probe.releaseWork.countDown();
            }

            if (!probe.workerFinished.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "post-processing did not finish");
            }
            if (probe.error.get() != null) {
                throw new IllegalStateException(
                        "post-processing failed", probe.error.get());
            }

            int aCompleted = jdbc.queryForObject(
                    "select count(*) from completed_post_work "
                    + "where order_id = ?",
                    Integer.class, "A");

            System.out.println("post work after release="
                    + count(jdbc, workCountSql));
            System.out.println("only A completed=" + (aCompleted == 1));
            System.out.println("worker saw committed A="
                    + probe.committedOrderVisible.get());
            System.out.println("worker thread is postExecutor="
                    + probe.workerName.get().startsWith("post-"));
        }
    }
}
```

### 5.3. Running and Output

In the project directory:

```bash
gradle -q run
```

Eight lines **explicitly printed by the program**, in order:

```text
service A returned=true
post work before release=0
rollback B caught=true
orders after rollback=1
listener starts before release=1
post work after release=1
only A completed=true
worker saw committed A=true
worker thread is postExecutor=true
```

**Note:** The block above actually has **nine** `System.out.println` lines; all nine lines are the expected output. Gradle or Spring logging may print extra messages. Do not assert against an absolute total console line count when logging configurations change.

### 5.4. Step-by-Step Analysis

**Step A — commit first, then submit:**

1. `context.getBean(OrderService.class)` returns the Spring-managed service; calling `create("A", false)` goes through transaction advice.
2. T1 starts. `JdbcTemplate` inserts order A; the service publishes `OrderCreated("A")` **inside T1**.
3. `@TransactionalEventListener(AFTER_COMMIT)` does not invoke the handler immediately; it registers processing against the transaction outcome.
4. T1 commits successfully. When the post-commit callback fires, the async proxy submits the handler to `postExecutor`.
5. Worker thread `post-*` starts, increments `listenerStarts`, and opens `workerStarted`, but has **not yet** written to the post-work table because it is awaiting `releaseWork`.
6. The service has returned to `main`, yet `completed_post_work` still has **0 rows**. This proves post-processing may not be finished when the caller returns.

**Step B — rollback does not trigger post-commit:**

1. `orders.create("B", true)` inserts B and publishes event B inside T2.
2. The service intentionally throws an unchecked exception. The transaction interceptor rolls back T2.
3. The `AFTER_COMMIT` listener does not process event B. While worker A is still paused, `listenerStarts` remains 1, and `purchase_orders` contains only A.

**Step C — independent worker writes to DB:**

1. `main` opens the `releaseWork` latch, and the worker proceeds.
2. The worker queries committed order A and finds one row.
3. The worker calls the separate bean `PostWorkWriter.recordCompleted("A")`. `@Transactional(REQUIRES_NEW)` opens an independent transaction T3 to insert into `completed_post_work`, then commits.
4. `workerFinished` is signaled after the writer returns. `main` awaits the latch, checks for exceptions, and only then prints the results.
5. `completed_post_work` has exactly one row for A and none for B. The thread name starts with `post-`, proving the handler ran on the named executor.

`CountDownLatch`, `AtomicBoolean`, `AtomicInteger`, and `AtomicReference` provide proper cross-thread visibility instead of polling a plain variable with `Thread.sleep(...)`.

### 5.5. Limitations of the Sample Program

- The example **proves the commit milestone and the async mechanism**, not that an email or external API call succeeded.
- In-memory `H2 mem:` disappears when the JVM stops; these records do not represent a durable job system.
- `Probe` is in-RAM test instrumentation, not a job state store.
- The handler uses a latch to simulate delay, not how real production work is handled.
- The example has only one valid post-job, so it does not demonstrate throughput, fairness, or ordering under heavy load.
- `recordCompleted` inserts one row with no retries; on DB errors, the sample simply stores the error in `AtomicReference` for `main` to detect.
- Outside a demo, do not hold a DB transaction open across a slow HTTP API call unnecessarily; keep state-writing boundaries brief and separate from I/O.

## 6. Why Separate Business Events from Job Execution Requests?

A domain event:

```java
public record OrderCreated(
        String orderId,
        long aggregateVersion,
        String correlationId) {}
```

should state **what happened** in the domain. A post-processing task can be represented by a `PostProcessingJob`/outbox row with its own lifecycle:

```text
OrderCreated(orderId=O-42, version=7)
    |
    +-- NotifyCustomerJob(orderId=O-42, status=NEW)
    +-- IndexOrderJob(orderId=O-42, status=NEW)
```

This is helpful when you need to:

- Trigger multiple tasks from one event with different retry policies.
- Distinguish an already-created order from an email waiting to be sent.
- Rate-limit capacity separately for the email API and the indexing service.
- Observe task states: `NEW`, `RUNNING`, `RETRY`, `DONE`, `FAILED`.
- Retry individual post-processing steps **without recreating the order**.

Do not cram every side effect into one giant listener when each needs different timeouts, failure policies, and SLOs. Conversely, do not split a tiny synchronous operation into a dozen events if there is no architectural value.

## 7. Errors in Async Listeners: The Publisher Receives No Outcome

A common mistake:

```java
@Async("postExecutor")
@EventListener
public void sendEmail(OrderCreated event) {
    throw new IllegalStateException("mail server unavailable");
}
```

This is an **illustrative snippet**, not a standalone program. With `void @Async`, the exception is thrown on the **worker thread**. It does not automatically propagate back to the request thread for the caller to catch like a synchronous exception.

Spring allows configuring `AsyncUncaughtExceptionHandler`:

```java
@Configuration
@EnableAsync
public class AsyncErrorsConfig implements AsyncConfigurer {

    @Override
    public AsyncUncaughtExceptionHandler
            getAsyncUncaughtExceptionHandler() {
        return (ex, method, args) -> {
            System.err.println(
                    "async handler failed: " + method.getName()
                    + ": " + ex.getMessage());
        };
    }
}
```

This is **illustrative code**, requiring imports for `AsyncConfigurer`, `AsyncUncaughtExceptionHandler`, `Configuration`, and `EnableAsync`; production systems should use structured logs, tracing, metrics, and durable failure states instead of just `System.err`.

### 7.1. Should Exceptions Be Swallowed in the Listener?

Only catch an error when you know **what to do** with it:

```java
@Async("postExecutor")
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onCreated(OrderCreated event) {
    try {
        mailClient.send(event.orderId());
    } catch (TransientMailException ex) {
        retryWriter.schedule(
                event.orderId(), ex.getMessage());
    }
}
```

This is illustrative code; `TransientMailException`, `mailClient`, and `retryWriter` are application-defined. `retryWriter` should persist a **retry request record** inside its own properly managed transaction.

If `retryWriter` also fails, the task can still be lost. Catching `Exception` and merely logging does not provide recovery across process crashes.

**Specifically:** `@TransactionalEventListener(AFTER_COMMIT)` in imperative Spring Framework triggers through a completion callback. If **submitting to the executor is rejected** during the post-commit callback, T1 has already committed and cannot be rolled back. Depending on the handling path, Spring may log the callback exception without propagating it to the caller. Never look at a 200 response alone and assert the worker was definitely accepted into the pool.

### 7.2. Can `CompletableFuture` Be Used?

With an async service **invoked explicitly** through a Spring proxy, you can write:

```java
@Async("postExecutor")
public CompletableFuture<SendResult> send(String orderId) {
    SendResult result = mailClient.send(orderId);
    return CompletableFuture.completedFuture(result);
}
```

This is an illustrative snippet requiring `SendResult`, `mailClient`, and `CompletableFuture`. The caller holds the `CompletableFuture` and composes `whenComplete`, `handle`, `allOf`, or `join` as needed.

However, `ApplicationEventPublisher.publishEvent(...)` **does not return futures for listeners**, so there is no simple way to write:

```java
CompletableFuture<?> done = publisher.publishEvent(event);
```

This is a **non-compiling counter-example** because `publishEvent` returns `void`. If the caller truly needs to await the job, use an async service API returning a future, or a persisted job ID/status. Do not fake a future around an Application Event that lacks a completion contract.

### 7.3. Async Listeners Do Not Publish Follow-Up Events via Return Value

For synchronous `@EventListener`, Spring supports certain return types to publish subsequent events. **The return-as-event mechanism is not supported for async listeners**. If worker success needs to emit `NotificationSent`, call:

```java
publisher.publishEvent(
        new NotificationSent(event.orderId()));
```

This is illustrative code; `NotificationSent` is an application-defined event class. If the resulting event must survive crashes, persist it via DB/outbox rather than merely publishing in RAM.

## 8. Executor Capacity, Backpressure, and Shutdown

An executor needs load-appropriate bounds:

```java
executor.setCorePoolSize(2);
executor.setMaxPoolSize(6);
executor.setQueueCapacity(100);
executor.setRejectedExecutionHandler(
        new ThreadPoolExecutor.AbortPolicy());
```

This is an illustrative snippet; configure these on the `ThreadPoolTaskExecutor` bean. In a `ThreadPoolExecutor`-style pool, once core workers are busy, tasks usually enter the queue; the pool expands toward `maxPoolSize` only when the queue fills. An **unbounded queue** typically renders `maxPoolSize` ineffective, allowing backlog to grow unchecked.

### 8.1. When the Executor Is Full

- `AbortPolicy` rejects submissions; Spring `ThreadPoolTaskExecutor` typically surfaces this as `TaskRejectedException`.
- `CallerRunsPolicy` may execute the task on the **publisher thread** under overload, changing latency/thread context and potentially affecting transactions. With transaction-bound listeners, understand the exact callback timing.
- `DiscardPolicy` and `DiscardOldestPolicy` **drop tasks**, making them unsuitable for critical work without a recovery mechanism.
- In-memory queues do not survive process crashes.

If a job must be processed, **persist the intent first**, and let workers pull according to capacity. Do not treat increasing queue size infinitely as backpressure.

### 8.2. Which Metrics Should Be Monitored?

| Metric | Meaning |
| --- | --- |
| Events published/s | Inbound event rate, **not** completed jobs |
| Tasks submitted/accepted/s | Work accepted by the executor |
| Active threads | Busy workers |
| Queue depth/capacity | Backlog and proximity to rejection |
| Queue wait p95/p99 | Latency from enqueue to handler start |
| Handler duration p95/p99 | Execution time of the task |
| Completed/s | Actual throughput |
| Rejected/s | Rate of rejected tasks |
| Failed/retried/s | Downstream health and retry pressure |
| Oldest pending job age | Longest-stuck work, especially with an outbox |
| DB/HTTP connection pool utilization | Bottlenecks outside the executor |

Measure **the time from when the event is received to when the side effect completes**, not merely how fast `publishEvent` returns.

### 8.3. Graceful Shutdown Is Not Durable Recovery

`setWaitForTasksToCompleteOnShutdown(true)` and `setAwaitTerminationSeconds(...)` enable orderly shutdown under supported conditions. However, the JVM can still die from `SIGKILL`, OOM, or power loss; tasks sitting only in the RAM queue will be lost.

In deployments/Kubernetes, review termination grace periods, readiness/draining, external API timeouts, and recovery from a persisted job store. **If the work is mandatory, never make an in-memory async executor the sole source of truth.**

## 9. Transactional Outbox for Post-Processing That Must Not Be Lost

`@Async @TransactionalEventListener(AFTER_COMMIT)` is straightforward, yet has **failure windows**:

```text
T1 COMMIT
   |
   +-- process crashes before callback/submit
   |
   +-- executor queue full, rejection
   |
   +-- task accepted, then JVM crashes before execution
   |
   +-- worker finishes external API call, crashes before writing DONE
```

For critical work, record the post-processing intent **inside T1 itself**:

```text
BEGIN T1
  +-- INSERT order
  +-- INSERT outbox(
          eventId, orderId, type=SEND_CONFIRMATION,
          status=NEW, attempt=0
      )
COMMIT T1
      |
      +-- worker polls/claims outbox by capacity
            |
            +-- call email/HTTP/broker with idempotency key
            +-- success -> mark DONE
            +-- transient failure -> RETRY with backoff
            +-- permanent failure -> FAILED/DLQ + alert
```

If T1 rolls back, order and outbox roll back together. If the process dies after commit, the outbox row remains for reprocessing.

### 9.1. Useful Job/Outbox Attributes

A schema might look like:

```sql
CREATE TABLE post_jobs (
    job_id VARCHAR(80) PRIMARY KEY,
    order_id VARCHAR(40) NOT NULL,
    job_type VARCHAR(80) NOT NULL,
    status VARCHAR(20) NOT NULL,
    attempts INT NOT NULL,
    next_attempt_at TIMESTAMP,
    last_error VARCHAR(1000)
);
```

This is **illustrative DDL**; adapt it to your actual database and timestamp types. With multiple workers, you need claiming/leasing/locking/unique constraints so two workers do not unintentionally process the same job concurrently.

Idempotency keys should be based on a **stable job ID or operation ID**, never generating a fresh UUID on every retry. If the external system already sent the email or recorded payment while the client timed out, retries can duplicate effects without deduplication/idempotency.

### 9.2. Avoid Retrying the Entire Committed Command

If `orders.create("A")` already committed while notification failed, **do not** automatically re-invoke `create("A")` just to resend the email. Retry the exact target: `sendConfirmation(jobId, orderId)`, without creating another order.

Separate states:

```text
Order: CREATED
Post-job: RETRY_PENDING
```

The API response can state "order created; confirmation is being processed" instead of equating email delivery success with order creation.

## 10. Do Not Hold Request/Thread-Bound Objects in Async Events

Avoid:

```java
public record OrderCreated(
        String orderId,
        HttpServletRequest request) {}
```

This is **code you should not adopt**. `HttpServletRequest` has a lifecycle tied to the HTTP request, mutable attributes, stream/session context, and no safe contract to outlive the request.

Workers do not automatically inherit:

- `RequestContextHolder`;
- default Spring Security context;
- MDC/logging/tracing context unless propagation is configured;
- the request thread's JDBC transaction;
- JPA `EntityManager` / lazy-loaded entities.

Instead, capture an **immutable payload**:

```java
public record OrderCreated(
        String orderId,
        String eventId,
        String verifiedTenantId,
        String actorId) {}
```

This is a separate illustrative definition, not a replacement for the single-field `OrderCreated` in the runnable project. `verifiedTenantId` and `actorId` must come from proper authentication/authorization mechanisms, never trusting client headers directly. When using `List`/`Map`, make defensive copies with immutable nested objects.

To preserve trace/MDC context, consider a configured `TaskDecorator` or Micrometer Context Propagation with proper cleanup. Remember that context propagation **does not extend the Servlet request's lifetime** and does not replace a clean business payload.

## 11. Ordering When Multiple Post-Processing Tasks Have Dependencies

Suppose there are three steps:

```text
OrderCreated
  |
  +-- reserve inventory
  |
  +-- authorize payment
  |
  +-- send invoice
```

If the invoice must only be sent after inventory reservation and payment succeed, having three `@Async` listeners subscribe to `OrderCreated` is insufficient. `@Order` orders **dispatch/invocation**, not ensuring one async worker **finishes** before the next begins.

A better approach:

```text
OrderCreated
    |
    +-- InventoryReserved (published only after stock is reserved)
            |
            +-- PaymentAuthorized
                    |
                    +-- InvoiceRequested
```

Or use an orchestrator with durable state (saga/workflow) when there are multiple prerequisites and failure recovery requirements. For events on the same aggregate, enforce `eventId`/sequence, idempotency, and per-aggregate ordering across multiple workers/brokers.

Never use `Thread.sleep(100)` to "wait" for the first task. If the caller needs a definite result within the same request, consider calling services directly with `CompletableFuture` composition, or execute synchronously when the contract truly requires it.

## 12. Testing Publish, Commit, and Completion Boundaries Properly

A solid test suite separates three concerns:

1. **Did the publisher invoke the right event?** Mockito `ArgumentCaptor<OrderCreated>` on `ApplicationEventPublisher` to check type/payload/count.
2. **Did Spring publish the event?** Spring Test `@RecordApplicationEvents` with `ApplicationEvents.stream(OrderCreated.class)` to verify the event was published in context.
3. **Did the async post-commit listener complete properly?** Latch/future/DB state with a timeout; assert **after a real commit** and after worker completion.

### 12.1. Tests to Include

| Scenario | Assertion |
| --- | --- |
| T1 commits | `AFTER_COMMIT` listener triggers and worker persists post-work |
| T1 rolls back | `AFTER_COMMIT` listener does not run for that event |
| Event published outside transaction | Listener skips by default if `fallbackExecution=false` |
| Async listener waits on I/O | Caller can return before the side effect completes |
| Worker throws exception | Error log/metric/failure state recorded; original TX remains committed |
| Executor queue full | Rejection is observed; critical jobs have a recovery path |
| Process crash/restart | Persisted job/outbox is recovered |
| Two workers + one job | Locking/claiming or idempotency prevents duplicate side effects |
| Duplicate event | Job/result is not duplicated |
| Event held mutable DTO | Worker's snapshot does not change if source mutates |

### 12.2. Pitfall in Spring Test `@Transactional`

A test method wrapped by Spring Test's `@Transactional` normally **rolls back by default** when the test ends. Publishing an event inside the test transaction and asserting `AFTER_COMMIT` **before commit** fails because the listener hasn't run yet. If the test ends in rollback, the listener never runs at all.

When you need a real commit inside a Spring-managed test transaction, you can use:

```java
TestTransaction.flagForCommit();
TestTransaction.end();

// Only then await async completion and assert DB state.
```

This is an illustrative snippet requiring Spring Test and an active test-managed transaction. Note that `TestTransaction.end()` only finishes the test-managed transaction; it does not wait for async workers to complete. Therefore, combine it with a latch or observable state.

An alternative is leaving `@Transactional` off the test method itself so the service call commits through its transaction proxy before post-processing assertions run.

### 12.3. Why Not Test with `Thread.sleep`?

```java
service.create("A", false);
Thread.sleep(100);
assertEquals(1, countCompletedJobs());
```

This is a **counter-example**. CI machines can run slowly or executors can be busy, making tests flaky. The Section 5 example uses `workerStarted`, `releaseWork`, and `workerFinished` to **control ordering deterministically** and verify completion with real signals.

## 13. Troubleshooting Table

| Symptom | Possible Cause | Fix |
| --- | --- | --- |
| `@Async` listener still runs on request thread | Missing `@EnableAsync`, wrong bean/proxy, self-invocation | Check executor bean, proxy, and thread name |
| `AFTER_COMMIT` listener does not run | Event published outside TX, T1 rolled back, listener not registered | Publish inside real transactional service, verify phase |
| Worker cannot see newly created order | Used `@Async @EventListener` so worker ran before commit | Switch to `@TransactionalEventListener(AFTER_COMMIT)` or outbox |
| Worker lacks `RequestContextHolder`/MDC | `ThreadLocal` does not propagate automatically | Capture immutable payload; use `TaskDecorator` for observability |
| `REQUIRES_NEW` method does not open transaction | `this.method()` bypassed transaction proxy | Invoke a separate Spring bean through proxy |
| Caller gets success while notification fails | Async exception on worker does not propagate | Async error handler, metrics, persisted failure/retry |
| Post-commit task rejected even though order was created | Executor full **after** T1 committed | Outbox/persisted queue, capacity sizing, and admission control |
| Increased max threads yet queue keeps growing | Queue not yet full so pool stays at core size | Bounded queue, sized for throughput/latency |
| Retry creates extra orders | Retrying entire business command instead of post-job | Stable job ID, retry side effect separately |
| Email sent twice | Ambiguous timeout, duplicate delivery, missing idempotency | Idempotency key or deduplication |
| Unstarted tasks lost after deploy | Executor queue lived in RAM | Durable outbox/queue and worker recovery |
| Flaky test (passes sometimes, fails others) | Asserting immediately after publish or using `Thread.sleep` | Latch/Awaitility/future with timeout |
| DB insert in post-commit callback not persisted | Old transaction resources may remain bound | Call new transaction via proper proxy, verify commit |
| `@Order` fails to keep job B after A | Async completion order differs from dispatch order | `ACompleted` event / workflow orchestration |

## 14. Pre-Production Checklist for Async Post-Processing

- [ ] Does the task truly **not need to finish** before the response/business method returns?
- [ ] Is the requirement "after publish" or "only after successful commit"?
- [ ] Is the event published **inside the appropriate transaction** when using `AFTER_COMMIT`?
- [ ] Is the listener a Spring-managed bean with `@EnableAsync` and an explicit executor name?
- [ ] Is the payload an immutable snapshot/ID without holding requests/entities/lazy proxies?
- [ ] Does the worker open its own DB transaction for writes when needed?
- [ ] Are exception handling, retry/backoff, and idempotency implemented for external side effects?
- [ ] Are executor core/max/queue/rejection/shutdown settings properly sized and monitored?
- [ ] Do mandatory tasks use a persisted outbox or durable queue instead of RAM-only queues?
- [ ] Have you tested commit, rollback, async completion, executor saturation, and crash/restart?
- [ ] Are there metrics for `submitted/accepted/completed/failed/rejected`, queue age, retry age, and SLA/SLO?
- [ ] When steps depend on each other, are completion events/state machines used instead of `@Order`?

**Conclusion:** For *best-effort* post-processing in Spring applications, `@Async("postExecutor")` combined with `@TransactionalEventListener(phase = AFTER_COMMIT)` is a clean pattern to **start only after DB commit without tying up the business thread while the worker runs**. It does not guarantee executor acceptance, automatic retries on failure, or task survival across JVM crashes. For critical tasks, persist the intent via **transactional outbox + idempotent worker**, using the executor strictly to bound and run persisted jobs.

## Official References

- [Spring Framework 6.2 — ApplicationContext Events, Asynchronous Listeners, and `@Order`](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework 6.2 — Task Execution and Scheduling, `@Async`](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [Spring Framework 6.2 — `ThreadPoolTaskExecutor` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework 6.2 — `@TransactionalEventListener` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [Spring Framework 6.2 — `TransactionSynchronization` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html)
- [Spring Framework 6.2 — Transaction Propagation (`REQUIRES_NEW`)](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework 6.2 — Testing Application Events](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/application-events.html)
