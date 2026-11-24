# Comprehensive Use-Case Exercise — Spring Framework Application Events

## 1. Objectives and Practice Scope

This is a **Practice and Summary** lesson of the **Spring Framework Application Events** module. Instead of merely writing an `@EventListener` that prints a log, learners implement a use case involving transactions, event payloads, multiple listener types, failure paths, background tasks, and integration tests. The goal is the ability to **choose the right event mechanism for business requirements** and prove it with tests.

After completing this exercise, you should be able to explain and implement:

1. Creating an **immutable event contract** using a Java record and publishing events with `ApplicationEventPublisher`.
2. Distinguishing a published event from **committed** data changes.
3. Registering a synchronous `@EventListener`, filtering events with a SpEL `condition`, and verifying payloads.
4. Choosing `@TransactionalEventListener(AFTER_COMMIT)` over a plain listener when side effects must wait for DB commit.
5. Using `@Async` and a bounded `ThreadPoolTaskExecutor` to offload post-processing from the business thread.
6. Understanding transaction/thread-context boundaries and why workers need a new transaction when writing data.
7. Writing `@RecordApplicationEvents` tests, assertions for commit/rollback/invalid data, and waiting for async completion with `CountDownLatch` rather than sleep.
8. Recognizing when in-memory Application Events are **not reliable enough** and require an outbox, retries, idempotency, or a broker.

The exercise uses Java 17+, Spring Framework 6.2.12, Spring JDBC, H2, Gradle, and JUnit Jupiter. No Spring Boot, HTTP server, or Kafka/RabbitMQ installation is required to run the core exercise. Advanced sections introduce real-system design.

## 2. Use Case: Checkout and Post-Event Reactions

An e-commerce application has a Checkout service. Upon receiving a request, it must validate inputs, create an order in the DB, publish `OrderPlaced`, and let other components react appropriately:

- **AuditProbe:** records published events in an in-memory list to observe the synchronous flow.
- **PremiumProbe:** observes only events with an order total of **10,000** or more via a SpEL condition.
- **PostCommitHandler:** starts post-processing **only after a successful commit**, running on an executor.
- **PostJobWriter:** writes the result to a DB table inside an independent transaction.
- **Spring Test recorder:** verifies the event was actually published, even when the transaction ultimately rolls back.

`AuditProbe` and `PremiumProbe` in the lab are technical observers, **not a business source of truth**. If a durable audit is required, design a DB audit table and proper transaction rather than an in-memory list.

### 2.1. Success Flow

```text
CheckoutService.checkout("O-1", "tenant-a", 2, 15000, false)
    |
    +-- Validate
    +-- BEGIN T1
    +-- INSERT purchase_orders
    +-- ApplicationEventPublisher.publishEvent(OrderPlaced)
    |      |
    |      +-- @EventListener audit (synchronous)
    |      +-- @EventListener(condition=...) premium (synchronous)
    |      +-- @TransactionalEventListener(AFTER_COMMIT)
    |                         registers callback with T1
    |
    +-- COMMIT T1 succeeds
    |      |
    |      +-- after-commit callback
    |               |
    |               +-- @Async submits to capstoneExecutor
    |
    +-- service may return
                           |
                           +-- worker reads committed order
                           +-- PostJobWriter.REQUIRES_NEW
                           +-- INSERT/UPSERT processed_post_jobs
                           +-- completes
```

### 2.2. Rollback Flow

```text
CheckoutService.checkout("O-2", ..., true)
    |
    +-- BEGIN T2
    +-- INSERT O-2
    +-- publish OrderPlaced(O-2)
    |      |
    |      +-- synchronous listener already ran
    |      +-- after-commit registered to wait
    |
    +-- throw IllegalStateException
    +-- ROLLBACK T2
           |
           +-- DB has no O-2
           +-- AFTER_COMMIT is not triggered
```

A common mistake is thinking **a transaction rollback makes the event as if it were never published**. That is false: synchronous `@EventListener` methods already executed when `publishEvent` was called. Only side effects participating in that transaction roll back accordingly. In-memory mutations or already-sent HTTP requests/emails do not automatically retract.

### 2.3. Invalid Path

`orderId` and `tenantId` must be non-null/non-blank, `quantity > 0`, and `totalCents >= 0`. The service validates before `INSERT` and publishing, so invalid inputs do not create `OrderPlaced` and trigger no listeners.

## 3. Exercises Before Viewing the Solution

You can implement each exercise and then compare with the reference solution in Section 5.

### Exercise 1 — Event Contract and Publisher

Create the record:

```java
public record OrderPlaced(
        String eventId,
        String orderId,
        String tenantId,
        int quantity,
        int totalCents) {}
```

Use constructor injection for `ApplicationEventPublisher` and `JdbcTemplate`. Put `@Transactional` on the public method `CheckoutService.checkout(...)`, validate before touching the DB, and publish the event **after `INSERT` yet before the transaction ends**.

**Acceptance criteria:** the event has the exact ID/tenant/quantity/total; one invocation publishes one event; invalid input publishes nothing. In this exercise, `eventId = "evt-" + orderId` gives tests fixed data; production needs a uniqueness strategy matching the event's lifecycle.

### Exercise 2 — Synchronous Listeners and `condition`

Create an `@EventListener` receiving every `OrderPlaced`; add another listener:

```java
@EventListener(condition = "#a0.totalCents() >= 10000")
public void premium(OrderPlaced event) {
    // Executes only when order total >= 10000.
}
```

`#a0` refers to the listener's first argument without depending on whether Java parameter names are preserved via `-parameters`. The listener must be a **Spring-managed bean**.

**Criteria:** a 15,000 event enters both listeners; a 5,000 event enters only the general listener. An event from a rolled-back transaction can also enter synchronous listeners before rollback.

### Exercise 3 — Transaction Phase

Add the listener:

```java
@Async("capstoneExecutor")
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void processAfterCommit(OrderPlaced event) {
    // Processes only after commit; method body runs on a worker.
}
```

**Criteria:** success -> post-processing starts after commit; rollback -> never called; publishing outside a transaction -> skipped by default since `fallbackExecution=false`. Do not enable `fallbackExecution=true` just to turn tests green if business rules require a committed state.

### Exercise 4 — Async Completion and DB Writer

Use a `CountDownLatch` to hold the worker before it finishes, proving `checkout` can return before post-processing completes. Add a separate bean with `@Transactional(propagation = REQUIRES_NEW)` to write to the DB from the worker.

**Criteria:** while the worker is held, the post-jobs table has no rows; after releasing and awaiting completion, there is exactly one row; the worker can query the committed order and the thread name carries the executor prefix.

### Exercise 5 — Testing All Four Paths

Use Spring Test `@RecordApplicationEvents` to verify published events, combined with JUnit and DB queries:

| Test | What to prove |
| --- | --- |
| Commit succeeds | Event has right type/payload; sync/premium listeners ran; post-job finishes after release |
| Rollback after publish | Recorder still sees event; sync ran; DB rolled back; after-commit did not run |
| Invalid input | No event, no DB row, no listener |
| Valid but below threshold | Event published and after-commit runs; premium listener skipped |

**Rule:** Testing that an event was published **differs** from testing transaction outcome and **differs** from testing async listener completion. Each needs its own evidence.

### Exercise 6 — Reliability Design

Code is not required in the main project for this part, yet you must be able to explain: full executor, `TaskRejectedException`, duplicate event retries, process crash after commit, transactional outbox, and idempotency keys. This is the advanced production-architecture step.

## 4. Creating the Gradle Project

Structure:

```text
spring-events-use-case-lab/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/EventUseCaseLab.java
    └── test/java/demo/EventUseCaseLabTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'spring-events-use-case-lab'
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

    testImplementation 'org.springframework:spring-test:6.2.12'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

application {
    mainClass = 'demo.EventUseCaseLab'
}

test {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
```

Spring Framework `spring-jdbc` brings in the required `spring-tx`; all Spring modules are pinned to the same 6.2.12 line. H2 is runtime-only because Java code uses `DataSource`/Spring JDBC without importing H2 classes directly. `spring-test` + JUnit Jupiter enable the TestContext Framework in integration tests.

This project omits the Gradle Wrapper; the machine needs Gradle 8+ and JDK 17+. In a real project, generate the wrapper and run `./gradlew` or `gradlew.bat`.

## 5. Java 17+ Reference Solution

### 5.1. `src/main/java/demo/EventUseCaseLab.java`

```java
package demo;

import java.util.List;
import java.util.UUID;
import java.util.concurrent.CopyOnWriteArrayList;
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
import org.springframework.context.event.EventListener;
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

public class EventUseCaseLab {

    // Value snapshot at event publication time.
    public record OrderPlaced(
            String eventId,
            String orderId,
            String tenantId,
            int quantity,
            int totalCents) {
    }

    // Test observer: strictly for demo, not persistent state.
    public static class Probe {
        final CopyOnWriteArrayList<String> syncIds =
                new CopyOnWriteArrayList<>();
        final AtomicInteger premiumCalls = new AtomicInteger();
        final AtomicInteger asyncStarts = new AtomicInteger();
        final AtomicBoolean sawCommittedOrder =
                new AtomicBoolean(false);
        final AtomicReference<String> workerThread =
                new AtomicReference<>("");
        final AtomicReference<Throwable> workerError =
                new AtomicReference<>();

        final CountDownLatch workerStarted = new CountDownLatch(1);
        final CountDownLatch releaseWorker = new CountDownLatch(1);
        final CountDownLatch workerFinished = new CountDownLatch(1);
    }

    public static class CheckoutService {
        private final JdbcTemplate jdbc;
        private final ApplicationEventPublisher publisher;

        public CheckoutService(
                JdbcTemplate jdbc,
                ApplicationEventPublisher publisher) {
            this.jdbc = jdbc;
            this.publisher = publisher;
        }

        @Transactional
        public void checkout(
                String orderId,
                String tenantId,
                int quantity,
                int totalCents,
                boolean rollback) {

            if (orderId == null || orderId.isBlank()
                    || tenantId == null || tenantId.isBlank()
                    || quantity <= 0 || totalCents < 0) {
                throw new IllegalArgumentException("invalid checkout");
            }

            jdbc.update(
                    "insert into purchase_orders "
                    + "(order_id, tenant_id, quantity, total_cents) "
                    + "values (?, ?, ?, ?)",
                    orderId, tenantId, quantity, totalCents);

            publisher.publishEvent(new OrderPlaced(
                    "evt-" + orderId,
                    orderId,
                    tenantId,
                    quantity,
                    totalCents));

            if (rollback) {
                throw new IllegalStateException("forced rollback");
            }
        }
    }

    public static class PostWorkWriter {
        private final JdbcTemplate jdbc;

        public PostWorkWriter(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional(propagation = Propagation.REQUIRES_NEW)
        public void save(OrderPlaced event) {
            // H2-specific UPSERT; event_id prevents DB duplicates.
            jdbc.update(
                    "merge into processed_jobs "
                    + "(event_id, order_id) key(event_id) "
                    + "values (?, ?)",
                    event.eventId(), event.orderId());
        }
    }

    public static class Handlers {
        private final JdbcTemplate jdbc;
        private final PostWorkWriter writer;
        private final Probe probe;

        public Handlers(JdbcTemplate jdbc,
                        PostWorkWriter writer,
                        Probe probe) {
            this.jdbc = jdbc;
            this.writer = writer;
            this.probe = probe;
        }

        // Synchronous; invoked even if the transaction later rolls back.
        @EventListener
        public void audit(OrderPlaced event) {
            probe.syncIds.add(event.orderId());
        }

        @EventListener(condition = "#a0.totalCents() >= 10000")
        public void highValue(OrderPlaced event) {
            probe.premiumCalls.incrementAndGet();
        }

        @Async("capstoneExecutor")
        @TransactionalEventListener(
                phase = TransactionPhase.AFTER_COMMIT)
        public void afterCommit(OrderPlaced event) {
            probe.asyncStarts.incrementAndGet();
            probe.workerThread.set(Thread.currentThread().getName());
            probe.workerStarted.countDown();

            try {
                if (!probe.releaseWorker.await(30, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "worker release timed out");
                }

                Integer found = jdbc.queryForObject(
                        "select count(*) from purchase_orders "
                        + "where order_id = ?",
                        Integer.class, event.orderId());
                probe.sawCommittedOrder.set(
                        found != null && found == 1);

                writer.save(event);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                probe.workerError.compareAndSet(null, ex);
            } catch (RuntimeException ex) {
                probe.workerError.compareAndSet(null, ex);
            } finally {
                probe.workerFinished.countDown();
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    @EnableTransactionManagement
    public static class Config {

        @Bean
        DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");

            // Each Spring context gets its own database to isolate tests.
            String name = "events_"
                    + UUID.randomUUID().toString().replace("-", "");
            ds.setUrl("jdbc:h2:mem:" + name
                    + ";DB_CLOSE_DELAY=-1");
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

        @Bean("capstoneExecutor")
        ThreadPoolTaskExecutor capstoneExecutor() {
            ThreadPoolTaskExecutor executor =
                    new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(2);
            executor.setQueueCapacity(4);
            executor.setThreadNamePrefix("capstone-");
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
        CheckoutService checkoutService(
                JdbcTemplate jdbc,
                ApplicationEventPublisher publisher) {
            return new CheckoutService(jdbc, publisher);
        }

        @Bean
        PostWorkWriter postWorkWriter(JdbcTemplate jdbc) {
            return new PostWorkWriter(jdbc);
        }

        @Bean
        Handlers handlers(
                JdbcTemplate jdbc, PostWorkWriter writer, Probe probe) {
            return new Handlers(jdbc, writer, probe);
        }
    }

    public static void createTables(JdbcTemplate jdbc) {
        jdbc.execute(
                "create table purchase_orders ("
                + "order_id varchar(50) primary key, "
                + "tenant_id varchar(50) not null, "
                + "quantity integer not null, "
                + "total_cents integer not null)");
        jdbc.execute(
                "create table processed_jobs ("
                + "event_id varchar(100) primary key, "
                + "order_id varchar(50) not null)");
    }

    public static int orders(JdbcTemplate jdbc) {
        return jdbc.queryForObject(
                "select count(*) from purchase_orders",
                Integer.class);
    }

    public static int completedJobs(JdbcTemplate jdbc) {
        return jdbc.queryForObject(
                "select count(*) from processed_jobs",
                Integer.class);
    }

    public static void main(String[] args)
            throws InterruptedException {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            CheckoutService checkout =
                    context.getBean(CheckoutService.class);
            Probe probe = context.getBean(Probe.class);
            createTables(jdbc);

            // A: transaction commits -> post-commit callback submits worker.
            checkout.checkout("O-1", "tenant-a", 2, 15000, false);
            try {
                if (!probe.workerStarted.await(30, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "async worker did not start");
                }

                // B: event published, then transaction rolls back.
                boolean rollbackCaught = false;
                try {
                    checkout.checkout(
                            "O-2", "tenant-a", 1, 20000, true);
                } catch (IllegalStateException ex) {
                    rollbackCaught = "forced rollback".equals(
                            ex.getMessage());
                }

                // C: validation fails before INSERT and publish.
                boolean invalidCaught = false;
                try {
                    checkout.checkout(
                            "O-3", "tenant-a", 0, 5000, false);
                } catch (IllegalArgumentException ex) {
                    invalidCaught = "invalid checkout".equals(
                            ex.getMessage());
                }

                System.out.println(
                        "sync event ids=" + List.copyOf(probe.syncIds));
                System.out.println(
                        "premium count=" + probe.premiumCalls.get());
                System.out.println(
                        "orders committed=" + orders(jdbc));
                System.out.println(
                        "rollback caught=" + rollbackCaught);
                System.out.println(
                        "invalid caught=" + invalidCaught);
                System.out.println(
                        "async starts=" + probe.asyncStarts.get());
                System.out.println(
                        "jobs before release=" + completedJobs(jdbc));
            } finally {
                // Do not leave worker blocked if main fails.
                probe.releaseWorker.countDown();
            }

            if (!probe.workerFinished.await(30, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "async worker did not finish");
            }
            if (probe.workerError.get() != null) {
                throw new IllegalStateException(
                        "async worker failed", probe.workerError.get());
            }

            System.out.println(
                    "jobs after release=" + completedJobs(jdbc));
            System.out.println(
                    "worker saw committed order="
                    + probe.sawCommittedOrder.get());
            System.out.println(
                    "worker used executor="
                    + probe.workerThread.get().startsWith("capstone-"));
        }
    }
}
```

### 5.2. Running and Checking Output

From the directory containing `build.gradle`:

```bash
gradle -q run
```

Lines explicitly printed by the program:

```text
sync event ids=[O-1, O-2]
premium count=2
orders committed=1
rollback caught=true
invalid caught=true
async starts=1
jobs before release=0
jobs after release=1
worker saw committed order=true
worker used executor=true
```

These are the **10 expected output lines** of the demo logic. Gradle/Spring may print additional logs depending on environment; do not rely on verbatim full stdout to draw conclusions.

### 5.3. Analyzing Run A — Successful Commit

1. `CheckoutService` is a Spring-managed bean. The caller retrieves the bean from the context and invokes public `checkout(...)` through the transaction proxy.
2. T1 starts and `INSERT`s O-1 into `purchase_orders`.
3. `publishEvent(new OrderPlaced(...))` is called inside T1; with the default multicaster, the `@EventListener` audit and high-value listeners run immediately on the publisher thread.
4. The high-value listener matches because `totalCents=15000 >= 10000`.
5. The transactional listener does not run post-work immediately; it registers a callback waiting for T1 to commit.
6. When T1 commits, the `AFTER_COMMIT` callback triggers the `@Async` invocation, submitting the method to `capstoneExecutor`.
7. The worker records its thread name, increments the counter, opens `workerStarted`, and waits on `releaseWorker`. At this moment, the post-jobs table still has **0 rows**.
8. After `main` releases, the worker queries and sees O-1 committed, then invokes the separate bean `PostWorkWriter.save(event)`. A new transaction opens, runs H2 `MERGE` by `event_id`, and commits one row.
9. `main` prints the final results only after `workerFinished` completes, avoiding races in assertions.

### 5.4. Analyzing Run B — Publish Before Rollback

1. T2 `INSERT`s O-2 and publishes `OrderPlaced` with `totalCents=20000`.
2. The audit listener appends O-2 and the high-value listener increments its counter immediately inside T2.
3. The service intentionally throws an unchecked exception. The transaction interceptor rolls back T2.
4. The DB no longer contains O-2; `AFTER_COMMIT` for event B does not run.
5. The in-memory audit list remains `[O-1, O-2]`, which **does not** mean the DB committed two orders.

If the synchronous listener had updated **the same DB transaction T2** instead of an in-memory list, that update would roll back with T2. External side effects or RAM updates do not roll back automatically.

### 5.5. Analyzing Run C — Invalid Input

Because quantity is 0, the service throws `IllegalArgumentException` before `INSERT` and publishing. No record is created for O-3, no synchronous event runs, and no background task is created.

**Tenant data note:** the lab only validates that `tenantId` is non-blank to focus on event mechanics. Real applications must derive tenant identity from verified authentication/authorization and check permissions—never trust raw headers or client-supplied parameters.

## 6. JUnit 5 Solution with Spring Test

### 6.1. `src/test/java/demo/EventUseCaseLabTest.java`

```java
package demo;

import java.util.List;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringJUnitConfig(EventUseCaseLab.Config.class)
@RecordApplicationEvents
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class EventUseCaseLabTest {

    @Autowired
    EventUseCaseLab.CheckoutService checkout;

    @Autowired
    EventUseCaseLab.Probe probe;

    @Autowired
    JdbcTemplate jdbc;

    @BeforeEach
    void createSchema() {
        EventUseCaseLab.createTables(jdbc);
    }

    @Test
    void commitPublishesCorrectPayloadAndCompletesPostJob(
            ApplicationEvents events) throws InterruptedException {
        try {
            checkout.checkout(
                    "T-1", "tenant-test", 1, 12000, false);

            assertTrue(probe.workerStarted.await(30, TimeUnit.SECONDS));
            assertEquals(List.of(
                    new EventUseCaseLab.OrderPlaced(
                            "evt-T-1", "T-1", "tenant-test", 1, 12000)),
                    events.stream(EventUseCaseLab.OrderPlaced.class)
                            .toList());

            assertEquals(List.of("T-1"),
                    List.copyOf(probe.syncIds));
            assertEquals(1, probe.premiumCalls.get());
            assertEquals(1, EventUseCaseLab.orders(jdbc));
            assertEquals(0, EventUseCaseLab.completedJobs(jdbc));
        } finally {
            probe.releaseWorker.countDown();
        }

        assertTrue(probe.workerFinished.await(30, TimeUnit.SECONDS));
        assertNull(probe.workerError.get());
        assertTrue(probe.sawCommittedOrder.get());
        assertEquals(1, EventUseCaseLab.completedJobs(jdbc));
    }

    @Test
    void rollbackStillPublishesButSkipsAfterCommit(
            ApplicationEvents events) {
        assertThrows(IllegalStateException.class, () ->
                checkout.checkout(
                        "T-2", "tenant-test", 1, 15000, true));

        assertEquals(1L,
                events.stream(EventUseCaseLab.OrderPlaced.class)
                        .count());
        assertEquals(List.of("T-2"),
                List.copyOf(probe.syncIds));
        assertEquals(1, probe.premiumCalls.get());
        assertEquals(0, EventUseCaseLab.orders(jdbc));
        assertEquals(0, EventUseCaseLab.completedJobs(jdbc));
        assertEquals(0, probe.asyncStarts.get());
        assertEquals(1L, probe.workerStarted.getCount());
    }

    @Test
    void invalidCheckoutPublishesNoEvent(
            ApplicationEvents events) {
        assertThrows(IllegalArgumentException.class, () ->
                checkout.checkout(
                        "T-3", "tenant-test", 0, 5000, false));

        assertEquals(0L,
                events.stream(EventUseCaseLab.OrderPlaced.class)
                        .count());
        assertTrue(probe.syncIds.isEmpty());
        assertEquals(0, probe.premiumCalls.get());
        assertEquals(0, EventUseCaseLab.orders(jdbc));
    }

    @Test
    void belowThresholdSkipsPremiumButRunsPostCommit(
            ApplicationEvents events) throws InterruptedException {
        try {
            checkout.checkout(
                    "T-4", "tenant-test", 1, 5000, false);

            assertTrue(probe.workerStarted.await(30, TimeUnit.SECONDS));
            assertEquals(1L,
                    events.stream(EventUseCaseLab.OrderPlaced.class)
                            .count());
            assertEquals(0, probe.premiumCalls.get());
            assertEquals(List.of("T-4"),
                    List.copyOf(probe.syncIds));
        } finally {
            probe.releaseWorker.countDown();
        }

        assertTrue(probe.workerFinished.await(30, TimeUnit.SECONDS));
        assertNull(probe.workerError.get());
        assertEquals(1, EventUseCaseLab.completedJobs(jdbc));
    }
}
```

### 6.2. Running Tests

```bash
gradle clean test
```

If the project already has a Gradle Wrapper:

```bash
./gradlew clean test
```

On Windows:

```bat
gradlew.bat clean test
```

**Expected:** JUnit Jupiter discovers and runs **4 test methods**, with all assertions passing. Gradle generates an HTML report at `build/reports/tests/test/index.html`. Timing, test order, and log line counts depend on the environment; the build/assertion results themselves are the proof.

This is a **source example and expected result**, not an actual run report from the learner's environment.

### 6.3. Meaning of the Four Tests

- **Commit:** verifies the full payload via `record.equals`, event count, synchronous listener, premium condition, DB commit, and worker completion.
- **Rollback:** the recorder sees the event **was published**, yet the DB has no order and the post-commit listener was never triggered; prevents the misconception "event published means committed".
- **Invalid:** validation fails before publishing, with no event and no side effects.
- **Below threshold:** a valid event passes through audit and post-commit, yet **does not** pass the high-value filter.

`@DirtiesContext(AFTER_EACH_TEST_METHOD)` gives each test a fresh context, singleton `Probe`, and H2 database. `ApplicationEvents` is also scoped by Spring Test to each test method, not shared as a singleton event store.

### 6.4. Why Not Add `@Transactional` to the Test Method?

Spring Test normally rolls back test-managed transactions by default when a test method has `@Transactional`. In that case `@TransactionalEventListener(AFTER_COMMIT)` may not run because the test transaction has not committed or ultimately rolls back. Here, test methods **do not** open an outer transaction; the transaction lives on the service and commits or rolls back right inside the proxied call.

If a real test-managed transaction is needed, use `TestTransaction.flagForCommit()` and `TestTransaction.end()` when an active transaction exists, then still wait for async completion with a latch/future. Never use `@RecordApplicationEvents` output to infer that callbacks finished.

## 7. Revisiting Mechanics: Events, Transactions, and Threads

### 7.1. `publishEvent()` Is Not a Durable Queue

`ApplicationEventPublisher.publishEvent(...)` returns `void`. In the default context, synchronous listeners run on the publisher thread. With a multicaster executor or `@Async` method, the body may execute on another thread.

It does **not** automatically:

- Persist messages for replay across restarts.
- Provide ACKs for all async listeners.
- Move a DB transaction from the publisher thread to a worker thread.
- Guarantee email/HTTP side effects succeed.
- Retry when an executor is full.
- Distribute events to another JVM or microservice.

For cross-service communication, use an appropriate broker/queue; when a DB write and durable message emission must commit together, use an outbox or a verified transactional mechanism.

### 7.2. `@TransactionalEventListener` Is Not an Ordinary Synchronous `@EventListener`

`@TransactionalEventListener(phase=AFTER_COMMIT)` binds the callback to the transaction outcome. When published outside a transaction, the listener **does not run** by default because `fallbackExecution=false`. On rollback, `AFTER_COMMIT` callbacks do not run.

Meanwhile, a plain `@EventListener` runs at publish time, even inside a transaction that later rolls back. Never change `AFTER_COMMIT` to `@EventListener` to "fix" a rolling-back test without understanding the semantics.

### 7.3. `@Async` Does Not Automatically Run After Commit

An `@Async @EventListener` can begin **before the transaction commits**. To act only on committed data, use `@TransactionalEventListener(AFTER_COMMIT)` or an outbox.

Exceptions in `void @Async` methods do not automatically propagate to the caller; configure an `AsyncUncaughtExceptionHandler`, logging/metrics, and failure/retry paths. In the demo, `Probe.workerError` is solely a test observer, not a replacement for durable error handling.

### 7.4. Return-as-Event Does Not Apply to Async Listeners

Spring lets synchronous listeners return another event for Spring to publish in supported cases. However, **asynchronous event listeners do not support publishing follow-up events via return values**. To emit `PostJobDone`, inject `ApplicationEventPublisher` and call it explicitly after completion, or write to an outbox when durability is required.

### 7.5. `@Order` Only Resolves Call Order Within Eligible Scope

`@Order` can affect listener dispatch order, yet does not guarantee async task A **finishes** before async task B. When dependencies exist, use completion events, sequential service calls, or a workflow/state machine with durable state.

## 8. Advanced Exercise A — Designing Inventory Then Payment

**Use case:** an order can only be paid after inventory is successfully reserved.

Counter-example:

```java
@Async("capstoneExecutor")
@Order(0)
@EventListener
public void reserve(OrderPlaced e) {
    inventory.reserve(e.orderId());
}

@Order(10)
@EventListener
public void pay(OrderPlaced e) {
    payment.authorize(e.orderId());
}
```

This is **broken illustrative code if payment depends on reservation**. `@Order` only orders invocation/submission; it does not wait for async work to complete.

A sounder design:

```text
OrderPlaced
    |
    +-- ReserveInventory
          |
          +-- SUCCESS -> InventoryReserved(orderId, reservationId)
                           |
                           +-- PaymentService.authorize(...)
                                  |
                                  +-- SUCCESS -> PaymentAuthorized
                                  +-- FAILED  -> PaymentFailed
          |
          +-- FAILURE -> InventoryReservationFailed
```

**Acceptance test:** hold the inventory worker with a latch and assert payment has not run; only after reservation succeeds and publishes `InventoryReserved` can payment run. When reservation fails, do not publish the success event. If the whole workflow must survive crashes, use persisted state/sagas/outboxes rather than in-memory events alone.

## 9. Advanced Exercise B — From Best-Effort Async to Transactional Outbox

**Use case:** a committed order must send an invoice, even if the JVM dies right after commit.

`@Async @TransactionalEventListener(AFTER_COMMIT)` **is not a sufficient guarantee**: the process can crash before the callback/submission, the executor can reject the task, or jobs can be lost on shutdown.

**Transactional outbox design:**

```text
BEGIN T1
  +-- INSERT purchase_orders
  +-- INSERT post_jobs(
          jobId, orderId, type=SEND_INVOICE,
          status=NEW, attempts=0
      )
COMMIT T1
    |
    +-- Worker polls/claims batches with leases
           |
           +-- send invoice with stable idempotency key
           +-- success -> DONE
           +-- transient failure -> RETRY/backoff
           +-- permanent failure -> FAILED/alert/DLQ
```

Illustrative schema:

```sql
CREATE TABLE post_jobs (
    job_id VARCHAR(80) PRIMARY KEY,
    order_id VARCHAR(50) NOT NULL,
    job_type VARCHAR(80) NOT NULL,
    status VARCHAR(20) NOT NULL,
    attempts INT NOT NULL,
    next_attempt_at TIMESTAMP,
    last_error VARCHAR(1000)
);
```

**Acceptance criteria:** transaction rollback leaves neither order nor job; commit leaves both; workers recover pending jobs after restarts; re-sending a message does not duplicate invoices or side effects.

**Why is idempotency needed?** If the external API succeeded yet the worker crashed before marking `DONE`, retries will call it again. An outbox prevents losing **the intent to send**, without automatically guaranteeing exactly-once side effects. Consumers and remote APIs need idempotency keys and deduplication.

In explanations, use the exact terms **transactional outbox** and **idempotency** to distinguish durability from execution speed.

## 10. Advanced Exercise C — Executor Capacity and Backpressure

A bounded configuration:

```java
ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
executor.setCorePoolSize(4);
executor.setMaxPoolSize(8);
executor.setQueueCapacity(100);
executor.setRejectedExecutionHandler(
        new ThreadPoolExecutor.AbortPolicy());
```

This is illustrative code; if created outside a Spring-managed bean, initialize and shut down the executor with proper lifecycle management. Numbers 4/8/100 are **not a universal optimal configuration**.

**Questions:**

1. When core threads are busy, does the next task enter the queue or does the pool immediately grow to max?
2. When both the queue and max threads are full, is the event processed?
3. If rejection happens after commit, can the already-committed order roll back?
4. How does `CallerRunsPolicy` change latency or transaction/thread context?
5. With an unbounded `queueCapacity`, how large can the backlog grow?
6. Which metrics must be measured to know business work actually finished?

**Answer guide:** With a standard `ThreadPoolExecutor`, once core threads are busy, tasks queue first; only when the queue fills do workers grow toward max. Once both max and queue are full, `AbortPolicy` rejects; Spring may throw `TaskRejectedException` on the submit path. Once post-commit has arrived, T1 cannot roll back. `CallerRunsPolicy` can run the task on the caller thread and spike latency. An unbounded queue masks overload and grows memory and latency. Track published, submitted, accepted, completed, failed, rejected, queue wait, and oldest pending age.

**Test:** hold workers with a latch, fill the queue, and assert rejection. Never use `Thread.sleep(50)` to guess that the scheduler queued the task.

## 11. Advanced Exercise D — Protecting Tenants and Sensitive Data

In the demo, `tenantId` is an illustrative field. In production:

- Derive tenant/user identity from verified authentication/authorization.
- For multi-tenant data, scope queries/updates by tenant or enforce proper checks. Never rely solely on `orderId` if it is not globally unique.
- Never place `HttpServletRequest`, `HttpSession`, cookies, bearer tokens, database connections, or lazy JPA entities inside async events.
- Never log full payloads containing PII or secrets.
- For nested collections inside Java records, defensively copy mutable elements too when a deeply immutable snapshot is required.
- Workers run on separate threads and do not automatically inherit `RequestContextHolder`, security context, MDC/tracing, or imperative transactions.
- `TaskDecorator`/context propagation helps observability, yet does not extend request lifecycles or turn worker threads into the source transaction thread.

Advanced test: simulate two tenants with the same local order ID and verify tenant A's worker cannot query or write tenant B's data.

## 12. Mechanism Selection Matrix

| Need | Mechanism | Warning |
| --- | --- | --- |
| Validate mandatory invariant before commit | Synchronous service | Do not use async events to decide validity |
| Non-critical internal notification | `@EventListener` or `@Async` depending on latency | Check transaction/timing |
| Process only after DB commit | `@TransactionalEventListener(AFTER_COMMIT)` | Does not itself guarantee durable jobs |
| Post-commit without blocking business thread | Add `@Async` and executor | Queue can reject or lose work on crash |
| Event for another process | Broker / external adapter | `ApplicationEventPublisher` stays inside context/JVM |
| Work must never be lost | Outbox/persistent job + retrying worker | Still requires idempotency |
| B only after A succeeds | Completion event / orchestrator | `@Order` does not guarantee async completion |
| Test publisher type/payload | Mockito `ArgumentCaptor` or Spring Test recorder | Mocks do not prove actual dispatch |
| Test real publish inside context | `@RecordApplicationEvents` | Recorder does not prove commit/completion |
| Test async listener completion | Latch/future + DB effect | Never use sleep |
| Event schema evolution | Versioning / compatibility tests | Never serialize raw entities |

## 13. Diagnosing Common Errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Listener never called | Bean missing from context/scan, `@Lazy`, wrong type | Check bean registrations; avoid lazy listeners |
| Synchronous listener received rolled-back order event | Event published before rollback | Use `AFTER_COMMIT` for side effects requiring committed facts |
| Premium listener skipped | `condition` false or wrong SpEL | Check `totalCents` and `#a0` |
| `@Async` runs synchronously | Missing `@EnableAsync`, wrong executor, self-invocation | Invoke through Spring proxy; check thread name |
| Post-commit never runs | Published outside transaction or rolled back | Check active transaction and phase |
| `@Transactional` test skips post-commit | Test rolls back by default | Commit via `TestTransaction` or omit test transaction |
| Worker misses just-inserted row | Worker ran before commit | Use `AFTER_COMMIT` or outbox |
| Worker lacks request/security context | `ThreadLocal` does not auto-propagate | Put immutable validated snapshot in event |
| `REQUIRES_NEW` does not start new transaction | Method called on same bean, bypassing proxy | Call a separate Spring writer bean |
| `void @Async` fails while caller gets success | Exception on worker | `AsyncUncaughtExceptionHandler` + failure state |
| App deploy drops pending jobs | In-memory queue | Persistent outbox + recovery |
| Event processed twice | Retries, broker redelivery, crash after effect | Stable `eventId`, idempotent consumer |
| Flaky test | Race condition, asserting before worker finishes | Latch/future with timeout |
| `@Order` used yet two async tasks invert | Ordering applies only to dispatch | Completion events / orchestration |
| Async queue full | Producer faster than consumer | Backpressure, bounded capacity, measured scaling |

## 14. Self-Assessment Checklist

- [ ] Event defined as an immutable record with only needed payload?
- [ ] Service validates before publishing and runs through a Spring transaction proxy?
- [ ] Understood synchronous listeners can run inside T1 before commit?
- [ ] SpEL `condition` uses exact field names and event type?
- [ ] Rollback test proves event was published yet DB did not commit?
- [ ] `AFTER_COMMIT` triggers only when transaction commits?
- [ ] `@Async` uses the right executor bean with a bounded queue?
- [ ] Worker opens its own transaction for DB writes?
- [ ] Tests await async completion strictly with latches/futures and timeouts?
- [ ] `@RecordApplicationEvents` asserts payload contents, not only counts?
- [ ] Never treat `publishEvent` as a durable delivery receipt?
- [ ] Outbox designed if jobs must survive crashes?
- [ ] Idempotency key included if retries can redeliver?
- [ ] Metrics exist for completed/rejected/failed counts and queue backlogs?
- [ ] Payload excludes requests/sessions or mutable entities causing cross-thread bugs?
- [ ] Know when to use direct service calls instead of event choreography?

## 15. Summary

An Application Events capstone does not stop at creating `OrderPlaced` and seeing a listener run. You must prove **exact type/payload**, **exact timing**, **exact transaction phase**, **exact execution count**, and **proper recovery mechanisms** when work is critical.

In the solution:

- Synchronous `@EventListener` sees O-1 and O-2 because both events were published, even though T2 later rolls back.
- `condition` routes only events with `totalCents >= 10000` to the high-value handler.
- `@TransactionalEventListener(AFTER_COMMIT)` skips O-2 because the DB rolled back.
- `@Async` runs O-1 post-processing on an executor, allowing the caller to continue before completion.
- `@RecordApplicationEvents` verifies published events; DB queries and `CountDownLatch` verify commits and completion.
- **Transactional outbox** + **idempotency** are the next step whenever work must survive JVM crashes, broker outages, or executor rejections.

From here, the same methodology applies to sending emails, CRM sync, search indexing, cache updates, inventory reservations, microservice messaging, or auditing; the common thread is defining **the business contract and failure boundaries** accurately before picking annotations.

## 16. References

- [Spring Framework 6.2 — ApplicationContext Events and `@EventListener`](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework 6.2 — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [Spring Framework 6.2 — `ThreadPoolTaskExecutor` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework 6.2 — Testing Application Events](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/application-events.html)
- [Spring Framework 6.2 — `@RecordApplicationEvents`](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-recordapplicationevents.html)
- [Spring Framework 6.2 — Transaction Propagation](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/tx-propagation.html)
