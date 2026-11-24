# Creating a Transactional Event Listener in Spring Framework Application Events

## 1. What Problem Does This Practice Solve?

In a Spring use case, an application may save data to a database and publish a domain event for other modules to react to:

~~~text
POST /orders
      |
      v
OrderService.place()
      |
      +-- INSERT order
      |
      +-- publish(OrderPlaced)
                  |
                  +-- SendReceipt
                  +-- UpdateSearchIndex
                  +-- Audit
~~~

If you only write `@EventListener`, the listener method is typically invoked **immediately when the event is dispatched**. When `publishEvent(...)` is inside an open transaction, the listener can run **before the transaction commits**. If the transaction later rolls back, the listener may already have sent an email, called an API, or updated an external system about an order that was never committed.

`@TransactionalEventListener` solves **the problem of timing reactions according to transaction outcomes**. Instead of executing immediately, Spring registers a callback and triggers the listener at the chosen transaction phase:

- `BEFORE_COMMIT`: before the commit executes.
- `AFTER_COMMIT`: after the transaction has committed successfully (**default**).
- `AFTER_ROLLBACK`: after the transaction rolls back.
- `AFTER_COMPLETION`: after the transaction finishes, whether committed or rolled back.

This lesson belongs to the **Practice and Summary** group. Learners will build a real listener with Spring Framework 6.2.8 and Spring JDBC/H2, verify commit, rollback, and out-of-transaction publishing; then analyze fallback, new transactions, async execution, common pitfalls, and reliability.

**Limitation to remember upfront:** `AFTER_COMMIT` **is not equivalent to durable message delivery**. The transaction has committed, yet the process can still die before or during handler execution. If the event must reliably be delivered to another system, consider a transactional outbox.

## 2. Distinguishing `@EventListener` and `@TransactionalEventListener`

### 2.1. Plain `@EventListener`

~~~java
@Component
public class ImmediateOrderListener {
    @EventListener
    public void on(OrderPlaced event) {
        // Can run immediately during the publishEvent call.
    }
}
~~~

This is an illustrative snippet in an application with `OrderPlaced` and appropriate imports.

With the default `SimpleApplicationEventMulticaster` and no async executor, this handler typically runs **synchronously on the publisher thread**. If the service method has an active transaction, the listener is invoked **before the transaction is guaranteed to commit**.

This is suitable when the listener intentionally participates directly in the command flow, such as checking an invariant within the same transaction or a reaction that does not need to wait for commit. It is unsuitable if the listener must run only for **committed facts**.

### 2.2. `@TransactionalEventListener`

~~~java
@Component
public class CommittedOrderListener {
    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void on(OrderPlaced event) {
        // Invoked in the phase after a successful commit.
    }
}
~~~

The snippet above is also illustrative, requiring imports for `TransactionalEventListener`, `TransactionPhase`, and Spring types.

Spring registers this method as a transactional application listener. When the event is published inside an eligible transaction, the corresponding callback is bound to the transaction; it **does not execute the handler body immediately** at the `publishEvent` site.

### 2.3. Comparison Table

| Criterion | Plain `@EventListener` | `@TransactionalEventListener(AFTER_COMMIT)` |
| --- | --- | --- |
| When event is received in a transaction | Upon dispatch; may be before commit | Only after a successful commit |
| If transaction rolls back after publish | Handler may already have executed | `AFTER_COMMIT` handler does not run |
| When published outside a transaction | Runs normally | **Does not run** by default |
| Automatically runs async? | No | No |
| Automatically persists durable event/job? | No | No |
| Automatically opens a new transaction for DB writes? | No | No |
| Can run inside the same JVM? | Yes | Yes |
| Suitable for post-commit notifications | Only if early semantics are acceptable | Right **timing**, does not solve durability |

**Do not confuse them:** `@TransactionalEventListener` is not another name for `@Transactional`. One chooses **when the listener runs**; the other configures transactions for a Spring-proxied/intercepted method.

## 3. Timeline of a Transaction and Listeners

Suppose the service is:

~~~java
@Transactional
public void placeOrder(...) {
    repository.save(order);
    publisher.publishEvent(new OrderPlaced(order.getId()));
}
~~~

Conceptual timeline when the transaction succeeds:

~~~text
BEGIN TRANSACTION
    |
    +-- INSERT/UPDATE order
    +-- publishEvent(OrderPlaced)
    |      |
    |      +-- ordinary @EventListener: may run immediately
    |      +-- @TransactionalEventListener: registers synchronization
    |
    +-- BEFORE_COMMIT listeners
    |
    +-- DATABASE COMMIT
    |
    +-- AFTER_COMMIT listeners
    +-- AFTER_COMPLETION listeners
    |
TRANSACTION CLEANUP
    |
method proxy returns to caller
~~~

On rollback:

~~~text
BEGIN TRANSACTION
    |
    +-- INSERT/UPDATE order
    +-- publishEvent(OrderPlaced)
    |      |
    |      +-- ordinary listener may already have run
    |      +-- transactional listener awaits outcome
    |
    +-- exception / rollback-only
    |
    +-- DATABASE ROLLBACK
    |
    +-- AFTER_ROLLBACK listeners
    +-- AFTER_COMPLETION listeners
    |
TRANSACTION CLEANUP
~~~

The diagram explains relative milestones; Spring's transaction infrastructure, transaction manager, and synchronization callbacks have specific implementation details. `BEFORE_COMMIT` is not a guaranteed promise of commit: a transaction can still fail or roll back after that callback.

## 4. Choosing the Right `TransactionPhase`

| Phase | When is it called? | Suitable scenarios | What to avoid |
| --- | --- | --- | --- |
| `BEFORE_COMMIT` | Before commit | Validation/flushing or preparing data that must participate in the transaction | Triggering un-rollbackable external side effects assuming commit already happened |
| `AFTER_COMMIT` | After successful commit | Cache invalidation, best-effort notifications, recoverable internal projections | Treating as a durable queue or writing to DB without opening a new transaction |
| `AFTER_ROLLBACK` | After rollback | Appropriate metrics/cleanup, controlled deletion of temporary resources | Assuming uncommitted data still exists |
| `AFTER_COMPLETION` | After commit or rollback | Outcome-independent release/cleanup, completion metrics | Using as a success-only signal |

### 4.1. Default Phase Is `AFTER_COMMIT`

The following two examples have the same default phase:

~~~java
@TransactionalEventListener
public void onOrder(OrderPlaced event) { }
~~~

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT
)
public void onOrder(OrderPlaced event) { }
~~~

Write `phase = AFTER_COMMIT` explicitly in documentation and critical business code so readers do not have to remember the default.

### 4.2. `AFTER_COMPLETION` Does Not Automatically Indicate Success or Failure via a Parameter

`@TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)` triggers after a transaction finishes for both commits and rollbacks. If business logic needs two different behaviors, it is usually clearer to use **two separate listeners** for `AFTER_COMMIT` and `AFTER_ROLLBACK`, or lower-level transaction synchronization with status. Do not assume an `OrderPlaced` parameter in `AFTER_COMPLETION` carries a "committed" flag.

### 4.3. `@Order` Only Controls Relative Ordering

Spring supports `@Order` to prioritize listeners within the same phase. However, that **does not create cross-process ordering** and does not guarantee side effects on async executors finish in order. When per-aggregate ordering is required, use versioning, sequences, and idempotency.

## 5. Prerequisites for a Transactional Listener to Work Correctly

For **imperative, thread-bound transactions**, you need:

1. A Spring-managed `ApplicationContext` with the listener bean properly registered.
2. An appropriate `PlatformTransactionManager` (for example `DataSourceTransactionManager` or a JPA transaction manager).
3. The publisher is called while a transaction is currently **active** in the corresponding thread/transaction context.
4. If the transaction comes from `@Transactional`, the method must be called **through the Spring proxy**, not via `this.method()` inside the same object in default proxy mode.
5. The event type matches the listener parameter; the listener is not excluded by a condition.
6. Publishing does not occur before listener infrastructure is registered during startup.

Without an active transaction, `@TransactionalEventListener` **skips the event by default** and does not start a new transaction to process it.

### 5.1. `TransactionSynchronizationManager` Is Not a Switch to Fake Transactions

You can use `TransactionSynchronizationManager.isActualTransactionActive()` for diagnostic logging of imperative transactions. However, do not manually manipulate `TransactionSynchronizationManager`'s `ThreadLocal` to "trick" listeners. A real transaction manager is needed to verify commit/rollback phases.

### 5.2. Event Payloads Are Facts, Not Live JPA Entities

Prefer immutable records, for example:

~~~java
public record OrderPlaced(
    long orderId,
    long totalCents
) { }
~~~

Do not pass an entire mutable JPA entity/lazy proxy through an event and expect all lazy associations to remain accessible after commit. For post-commit listeners, keep only IDs and necessary data; if state must be read, query explicitly within an appropriate transaction boundary.

## 6. Java 17+ Practice with Spring JDBC and H2

This **standalone, compilable/runnable** example uses:

- Java 17+.
- Spring Framework 6.2.8: `spring-context`, `spring-tx`, and `spring-jdbc`.
- H2 database 2.3.232 (in-memory) to observe commit and rollback.
- Maven to compile and run `main`.
- `@EnableTransactionManagement` and `DataSourceTransactionManager` to activate Spring transaction proxies.
- `@EventListener` (immediate upon publish), `@TransactionalEventListener(AFTER_COMMIT)`, and `@TransactionalEventListener(AFTER_ROLLBACK)`.
- An out-of-transaction publish call to verify default transactional listener behavior.

No Spring Boot, REST server, or message broker is needed.

### 6.1. Directory Structure

~~~text
transactional-event-listener-demo/
├── pom.xml
└── src
    └── main
        └── java
            └── TransactionalEventDemo.java
~~~

### 6.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>transactional-event-listener-demo</artifactId>
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
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-tx</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
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
                    <mainClass>TransactionalEventDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 6.3. src/main/java/TransactionalEventDemo.java

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import javax.sql.DataSource;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

public final class TransactionalEventDemo {

    // Domain fact: immutable and minimal payload.
    public record OrderPlaced(long orderId, long totalCents) { }

    // Not final: Spring creates a class-based proxy to intercept
    // @Transactional when obtaining the bean from ApplicationContext.
    public static class OrderService {
        private final JdbcTemplate jdbc;
        private final ApplicationEventPublisher publisher;

        public OrderService(
                JdbcTemplate jdbc,
                ApplicationEventPublisher publisher
        ) {
            this.jdbc = jdbc;
            this.publisher = publisher;
        }

        @Transactional
        public void place(
                long orderId,
                long totalCents,
                boolean failAfterPublish
        ) {
            if (orderId <= 0 || totalCents <= 0) {
                throw new IllegalArgumentException("Invalid order");
            }

            jdbc.update(
                "INSERT INTO orders(id, total_cents) VALUES (?, ?)",
                orderId, totalCents
            );

            publisher.publishEvent(
                new OrderPlaced(orderId, totalCents)
            );

            System.out.println(
                "METHOD_BODY_END order=" + orderId
            );

            if (failAfterPublish) {
                throw new IllegalStateException(
                    "Forced rollback after event publish"
                );
            }
        }
    }

    public static class OrderObservers {
        private final AtomicInteger immediate = new AtomicInteger();
        private final AtomicInteger committed = new AtomicInteger();
        private final AtomicInteger rolledBack = new AtomicInteger();

        // Does not wait for the transaction to end.
        @EventListener
        public void onImmediate(OrderPlaced event) {
            immediate.incrementAndGet();
            System.out.println(
                "IMMEDIATE order=" + event.orderId()
            );
        }

        // Waits for the transaction to commit successfully.
        @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT
        )
        public void onCommit(OrderPlaced event) {
            committed.incrementAndGet();
            System.out.println(
                "AFTER_COMMIT order=" + event.orderId()
            );
        }

        // Receives only when the transaction bound to the event rolls back.
        @TransactionalEventListener(
            phase = TransactionPhase.AFTER_ROLLBACK
        )
        public void onRollback(OrderPlaced event) {
            rolledBack.incrementAndGet();
            System.out.println(
                "AFTER_ROLLBACK order=" + event.orderId()
            );
        }

        public int immediateCount() {
            return immediate.get();
        }

        public int committedCount() {
            return committed.get();
        }

        public int rollbackCount() {
            return rolledBack.get();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement(proxyTargetClass = true)
    public static class Config {

        @Bean
        DataSource dataSource() {
            DriverManagerDataSource ds =
                new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl(
                "jdbc:h2:mem:transactional_events;DB_CLOSE_DELAY=-1"
            );
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        PlatformTransactionManager transactionManager(
                DataSource dataSource
        ) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        OrderService orderService(
                JdbcTemplate jdbc,
                ApplicationEventPublisher publisher
        ) {
            return new OrderService(jdbc, publisher);
        }

        @Bean
        OrderObservers orderObservers() {
            return new OrderObservers();
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(Config.class)) {

            JdbcTemplate jdbc = context.getBean(
                JdbcTemplate.class
            );

            jdbc.execute(
                "CREATE TABLE orders (" +
                "id BIGINT PRIMARY KEY, " +
                "total_cents BIGINT NOT NULL)"
            );

            // IMPORTANT: retrieve the proxied Spring bean;
            // do not call new OrderService(...) and invoke @Transactional.
            OrderService service = context.getBean(
                OrderService.class
            );

            OrderObservers observers = context.getBean(
                OrderObservers.class
            );

            System.out.println("CASE=COMMIT");
            service.place(101L, 8500L, false);
            System.out.println(
                "ROWS_AFTER_COMMIT=" +
                jdbc.queryForObject(
                    "SELECT COUNT(*) FROM orders",
                    Integer.class
                )
            );

            System.out.println("CASE=ROLLBACK");
            try {
                service.place(102L, 9900L, true);
            } catch (IllegalStateException ex) {
                System.out.println("CAUGHT_ROLLBACK");
            }

            System.out.println(
                "ROWS_AFTER_ROLLBACK=" +
                jdbc.queryForObject(
                    "SELECT COUNT(*) FROM orders",
                    Integer.class
                )
            );

            // Not bound to any transaction.
            System.out.println("CASE=NO_TX");
            context.publishEvent(new OrderPlaced(103L, 7000L));

            System.out.println(
                "COUNTS immediate=" + observers.immediateCount()
                + " commit=" + observers.committedCount()
                + " rollback=" + observers.rollbackCount()
            );
        }
    }
}
~~~

### 6.4. Run Command

Inside `transactional-event-listener-demo` with JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java
~~~

Expected output **for the `System.out.println` lines printed by the program** (excluding framework/Maven logs), on normal execution:

~~~text
CASE=COMMIT
IMMEDIATE order=101
METHOD_BODY_END order=101
AFTER_COMMIT order=101
ROWS_AFTER_COMMIT=1
CASE=ROLLBACK
IMMEDIATE order=102
METHOD_BODY_END order=102
AFTER_ROLLBACK order=102
CAUGHT_ROLLBACK
ROWS_AFTER_ROLLBACK=1
CASE=NO_TX
IMMEDIATE order=103
COUNTS immediate=3 commit=1 rollback=1
~~~

### 6.5. Explaining the Output

**CASE=COMMIT:** `OrderService.place(101, ..., false)` inserts the row and publishes the event. The plain `@EventListener` prints `IMMEDIATE` while still inside the method. The service prints `METHOD_BODY_END` and returns to the transaction interceptor. The transaction manager commits, and only then does the `AFTER_COMMIT` transactional listener print its line. Querying outside the transaction shows `ROWS_AFTER_COMMIT=1`.

**CASE=ROLLBACK:** The service tentatively inserts order 102 and publishes event 102. The immediate listener **did run**. Then the service throws `IllegalStateException`, the transaction interceptor marks rollback / rolls back, so the `AFTER_COMMIT` callback is skipped; instead `AFTER_ROLLBACK` prints event 102. The exception propagates to the caller and is caught, printing `CAUGHT_ROLLBACK`. Querying the DB still finds **only one row**, proving order 102 did not commit.

**CASE=NO_TX:** `context.publishEvent(...)` is called directly outside any active transaction; the plain `@EventListener` still receives the event. Both transactional listeners have the default `fallbackExecution=false`, so they **do not run**. Totals: immediate received 3 events (commit, rollback, no transaction), after-commit received 1, after-rollback received 1.

**Scope limits of the example:** In-memory H2 does not survive process restarts; counters are also in RAM. The demo verifies **phases and rollback**, not durable delivery, brokers, retries, or crash survivability. Code and output are designed to run, not a captured build/test transcript in this document.

## 7. `fallbackExecution`: How Are Events Outside a Transaction Handled?

By default:

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT
)
public void on(OrderPlaced event) { }
~~~

Without an active transaction at publish time, the handler is not invoked. This is intentional: Spring cannot fulfill an "after commit" promise when there is no transaction to commit.

When processing without a transaction is genuinely acceptable, you can choose:

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT,
    fallbackExecution = true
)
public void on(OrderPlaced event) {
    // Runs when published in a committed transaction,
    // or via fallback when no transaction is present.
}
~~~

This is a snippet requiring appropriate classes/imports, **not part of the runnable demo**.

**Warning:** `fallbackExecution=true` **does not create a transaction**, nor does it turn an out-of-transaction event into a "committed" event. It only allows the handler to run when there is no transaction for phase synchronization. That may make sense for cache invalidation or metrics, but is dangerous if logic is only allowed to react after business state has transactionally committed.

### 7.1. The "No Transaction When the Author Thought There Was One" Problem

Common causes:

- The service object was created with `new` instead of obtained from the Spring context.
- A `@Transactional` method was called via `this.method()` inside the same bean, bypassing the Spring proxy.
- The method was not proxied/intercepted due to architecture or proxy configuration.
- The publisher was called before or after the intended transaction boundary.
- An async code path ran on another thread without carrying the publisher's imperative transaction.
- Calling the publisher in a test that did not configure a transaction manager or open a transaction.
- Multiple `PlatformTransactionManager` beans exist and the annotation/scope picked the wrong manager.

**Do not fix those bugs by blindly enabling fallback.** Diagnose the exact transaction boundary first, then decide the phase or fallback policy.

### 7.2. Diagnosing with `TransactionSynchronizationManager`

In an imperative application, you can log at the producer:

~~~java
boolean active =
    TransactionSynchronizationManager.isActualTransactionActive();
System.out.println("TX_ACTIVE=" + active);
~~~

This is a snippet requiring import `org.springframework.transaction.support.TransactionSynchronizationManager`. `isActualTransactionActive()` indicates whether a real transaction is active on **the current thread**; it does not replace checking the transaction manager, rollback rules, event type, or listener registration. With reactive transactions, thread-locals do not represent Reactor context.

## 8. Important Note: Writing to the Database in `AFTER_COMMIT` Requires a New Transaction

This is a very easy mistake to make even when the code looks reasonable:

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT
)
public void on(OrderPlaced event) {
    auditRepository.save(new AuditRecord(event.orderId()));
}
~~~

The snippet above is illustrative. The problem is: per **Spring's Javadoc**, during `AFTER_COMMIT`, `AFTER_ROLLBACK`, or `AFTER_COMPLETION`, **the database transaction has already completed, yet transaction resources may still be bound to the thread and accessible** during cleanup. A DB operation that appears to join the old transaction may **have no subsequent commit**.

Do not infer from `save(...)` returning that the audit row was committed.

### 8.1. The Right Way When Writing to the DB After Commit Is Truly Needed

Move the write into a **different** Spring service with a `@Transactional(propagation = Propagation.REQUIRES_NEW)` method:

~~~java
@Service
public class CommittedAuditService {
    private final JdbcTemplate jdbc;

    public CommittedAuditService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void writeCommittedAudit(long orderId) {
        jdbc.update(
            "INSERT INTO committed_audit(order_id) VALUES (?)",
            orderId
        );
    }
}
~~~

And the listener:

~~~java
@Component
public class CommitAuditListener {
    private final CommittedAuditService audit;

    public CommitAuditListener(CommittedAuditService audit) {
        this.audit = audit;
    }

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void on(OrderPlaced event) {
        audit.writeCommittedAudit(event.orderId());
    }
}
~~~

Both snippets are **extended illustrative code**, requiring imports for `Service`, `Component`, `JdbcTemplate`, `Transactional`, `Propagation`, `TransactionalEventListener`, and a `committed_audit` table. They are not part of `TransactionalEventDemo.java` in Section 6.

Calling from the listener into **another proxied Spring bean** ensures `REQUIRES_NEW` is actually intercepted, opening an independent new transaction to commit the audit record. **Do not call `this.writeCommittedAudit(...)` on the same object** and expect the method annotation to be intercepted under default proxying.

**Cost:** `REQUIRES_NEW` requires a new transaction and connection, which can increase connection pool pressure. Do not treat it as a cure-all. If work must be delivered reliably to an external service, an **outbox written in the source transaction** is usually better than a post-commit listener writing intent.

### 8.2. Why Not Use `REQUIRES_NEW` Instead of an Outbox?

An `AFTER_COMMIT` listener can still **never be called if the process dies after the source commit**, even if the target method opens a new transaction. `REQUIRES_NEW` solves **committing a DB operation that actually ran**; it does not eliminate the loss window between source commit and listener invocation.

A proper outbox writes the `OrderPlaced` intent **inside the same source transaction** as the Order before commit, rather than waiting for a post-commit callback to insert it.

## 9. `BEFORE_COMMIT`, `AFTER_ROLLBACK`, and `AFTER_COMPLETION` in Practice

### 9.1. `BEFORE_COMMIT` Does Not Guarantee Commit

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.BEFORE_COMMIT
)
public void beforeCommit(OrderPlaced event) {
    // Example: a local step still needing the source transaction.
}
~~~

The handler runs before the transaction manager completes the commit, yet a rollback can still happen afterward. Do not call an irreversible payment API simply because the phase name sounds committed.

An exception from `BEFORE_COMMIT` can abort the commit or roll back the transaction, depending on the transaction manager and error handling. If validation directly governs the use case, an explicit service call inside the transaction is usually clearer than an event listener hiding workflow control.

### 9.2. `AFTER_ROLLBACK` Is Only for Reactions That Tolerate Rollback

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_ROLLBACK
)
public void afterRollback(OrderPlaced event) {
    // Example: record failure metric / policy-governed external cleanup.
}
~~~

On rollback, the just-inserted Order row may already have been reverted. The listener must not assume it can query that row or treat it as a committed fact. The event payload may still exist in RAM, so distinguish "command attempted" from "OrderPlaced durably exists".

In domain terms, consider another event name like `OrderPlacementFailed` or an explicit failure signal if recipients need to know the transaction failed. A rollback listener observes an **attempted fact** created in an uncommitted transaction and must not emit it as a successful fact to external systems.

### 9.3. `AFTER_COMPLETION` for General Cleanup

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMPLETION
)
public void cleanup(OrderPlaced event) {
    // Cleanup/metrics applying to both commit and rollback.
}
~~~

Do not rely on this method to conclude commit succeeded. When distinct outcomes must be tracked separately, use the dedicated phases or an appropriate transaction synchronization API.

## 10. `@Async` and Transactional Event Listeners: Understanding Two Boundaries

They can be combined:

~~~java
@Component
public class AsyncNotificationListener {
    @Async("notificationsExecutor")
    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void on(OrderPlaced event) {
        // Send notification on executor after commit.
    }
}
~~~

This is a snippet without `@EnableAsync`, `notificationsExecutor`, or real dependencies; it is not part of the runnable demo.

Separate **two things**:

1. The transactional event infrastructure receives the event inside the publisher's transaction and registers the callback for the corresponding phase.
2. When that phase arrives, the handler can be dispatched through the Spring async proxy/executor if configured properly.

Therefore, `@Async` **does not carry the source transaction to the worker thread**. Spring imperative transactions are usually thread-bound and do not automatically transfer to executors. Listeners should receive an **immutable event DTO** holding only needed IDs/payload and open a new transaction when writing to the DB.

### 10.1. Risks of Async

- In-memory queues can be lost if the process dies.
- The executor can fill up and reject tasks (`TaskRejectedException`).
- Errors in `@Async void` typically need an `AsyncUncaughtExceptionHandler` or dedicated instrumentation; they do not propagate back to the request.
- Completion order across multiple events can be reversed.
- An async listener may execute after request/transaction-scoped dependencies have closed.
- A misconfigured proxy can run synchronously without developers noticing.
- `AFTER_COMMIT` does not turn a background task into durable delivery.

When zero job loss is required, do not just add `@Async`; write a job/outbox in the source transaction with explicit worker retries and acknowledgments.

### 10.2. Global Async Multicaster Differs from Selective `@Async`

`SimpleApplicationEventMulticaster.setTaskExecutor(...)` affects how the multicaster dispatches listeners in general. Spring provides `ApplicationListener.supportsAsyncExecution()` so certain transaction-bound listeners still trigger on the publisher thread to register synchronization in the right context; do not assume all listeners are moved to the executor identically.

Configuring an executor on the multicaster is therefore a **context-wide change** requiring evaluation of transactions, lifecycle, and non-async listeners. Selective `@Async` or a dedicated job system can be easier to control.

## 11. Post-Commit Events Do Not Equal Durable Delivery

Failure timeline:

~~~text
T1 BEGIN
  INSERT order
  publishEvent(OrderPlaced)       [AFTER_COMMIT listener registered]
T1 COMMIT                         [order durable in DB]
  |
  +-- process crash
  |
  X  @TransactionalEventListener never sent the notification
~~~

The application may never know it missed the work. `AFTER_COMMIT` guarantees **callback timing while the process is alive and the callback executes**, not retries after restart.

### 11.1. When Is `AFTER_COMMIT` Sufficient?

Typically suitable for **best-effort or self-healing** side effects:

- Invalidating a cache that already has TTL/refresh.
- Recording supplementary metrics/tracing that are not the source of truth.
- Triggering projection updates that can be rebuilt from the database.
- Sending notifications if the business accepts occasional loss or reconciliation jobs.

Set expectations accurately: "email sent after commit" does not mean "email guaranteed to be delivered".

### 11.2. When Is a Transactional Outbox Needed?

If `OrderPlaced` must reliably reach billing or fulfillment, use a single source transaction:

~~~text
OrderService @Transactional:
    INSERT orders
    INSERT outbox(eventId, type, payload, status=PENDING)
    COMMIT
         |
         v
Outbox relay process
    |
    +-- poll/claim or CDC
    +-- broker publish + ack
    +-- retry/backoff
         |
         v
Consumer
    +-- deduplicate stable eventId
    +-- process idempotently
~~~

Writing the outbox in the same transaction as the Order ensures **business state and publishing intent commit or roll back atomically**. A relay can retry after an app restart. If the broker received the message but the relay died before marking SENT, the event may be redelivered, so consumers must be idempotent.

### 11.3. `AFTER_COMMIT` and Outbox Can Coexist

An application can:

- Write an `OrderPlaced` outbox row for cross-process integration.
- Trigger `@TransactionalEventListener(AFTER_COMMIT)` for internal caches/metrics where **strict delivery is not mandatory**.

There is no need to turn every listener into a broker consumer. What matters is classifying the **durability requirement** and **business criticality** of each consumer.

## 12. Testing the Real Transaction Boundary

Do not simply mock `ApplicationEventPublisher` and conclude listener phases work. Mockito `verify` proves the service **called `publishEvent`**, but does not execute transaction synchronization or Spring listeners.

### 12.1. Mandatory Test Matrix

| Case | Expectation |
| --- | --- |
| Event published in transaction, commit succeeds | `AFTER_COMMIT` runs once |
| Event published in transaction, then rolls back | `AFTER_COMMIT` does not run; `AFTER_ROLLBACK` may run |
| Event published outside transaction, default fallback | Transactional listener does not run |
| Event published outside transaction, `fallbackExecution=true` | Listener executes via fallback |
| Exception after publish before commit | No after-commit success side effect |
| Ordinary sync listener | May run before commit and on rollback paths too |
| `BEFORE_COMMIT` handler fails | Verify commit is affected per policy |
| `AFTER_COMMIT` writes DB with `REQUIRES_NEW` via bean proxy | New write commits independently |
| `AFTER_COMMIT` writes DB in wrong transaction | Test must expose missing commit / non-durable change |
| `@Async` `AFTER_COMMIT` | Wait for worker outcome with timeout |
| Wrong transaction manager or self-invocation | Test must expose missing active transaction |
| Process crash after commit before listener | Proves no durable retry with in-memory event bus alone |
| Outbox written in source transaction | Atomic commit/rollback between business data and intent |
| Context without listener registered | Does not automatically replay old events |

### 12.2. `@Transactional` Tests Defaulting to Rollback Are a Trap

In Spring TestContext, a test method annotated with `@Transactional` typically **rolls back at the end of the test**. If the test expects `AFTER_COMMIT` to fire right after `publisher.publishEvent(...)`, assertions may fail because the transaction has not committed and later rolls back.

Example of a misleading test:

~~~java
// Illustrates a commonly misunderstood test.
@Test
@Transactional
void afterCommitShouldRun() {
    publisher.publishEvent(new OrderPlaced(1L, 100L));
    assertEquals(1, listener.committedCount());
}
~~~

At the assertion line, the test's transaction is usually **still active**; the after-commit listener has not run yet. Structure tests to perform a **real commit** before asserting.

### 12.3. How to Test with Explicit Commits

Several options:

- Call a `@Transactional` Spring service from a test method that is **not** wrapped in a test transaction; once the proxied service method returns, the commit has completed.
- Use `TransactionTemplate` to close the transaction before asserting.
- In Spring TestContext with test-managed transactions, use `TestTransaction.flagForCommit()` followed by `TestTransaction.end()` where appropriate.

Example using `TransactionTemplate` (snippet requiring manager/publisher beans):

~~~java
TransactionTemplate transaction = new TransactionTemplate(txManager);
transaction.executeWithoutResult(status -> {
    repository.save(order);
    publisher.publishEvent(new OrderPlaced(1L, 100L));
});

// By here executeWithoutResult has finished the transaction.
// Assert state recorded by the AFTER_COMMIT listener.
assertEquals(1, listener.committedCount());
~~~

This is an **illustrative snippet**, not a complete test file and not part of the Section 6 Maven demo. It demonstrates a clearer commit boundary than asserting inside an unfinished transactional test method.

### 12.4. `@RecordApplicationEvents` Only Proves Publication

Spring TestContext provides `@RecordApplicationEvents` and `ApplicationEvents` to record events published within a test. However:

- An event being recorded **does not prove** every transactional listener succeeded.
- When an event is published and the transaction rolls back, the recorder can still record the publication.
- With async listeners, publishing/recording does not prove the worker finished.

When testing transaction phases, observe **the actual handler's outcome** after commit/rollback, not only published event counts.

### 12.5. Deterministic Feedback in Tests

Use in-memory counters/lists (as in the demo) for synchronous phase tests; for async, use `CountDownLatch` or result futures with timeouts. Avoid `Thread.sleep(100)` and guessing that the worker ran, as it flakes under CI load.

## 13. Common Errors and Diagnostic Steps

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| No `AFTER_COMMIT` despite producer calling publish | No active transaction | Log `TransactionSynchronizationManager.isActualTransactionActive()` |
| `@EventListener` runs while transactional listener stays silent | Published outside transaction or rolled back | Compare transaction boundaries and phase |
| No transaction despite `@Transactional` | Self-invocation / proxy not intercepting | Invoke bean from context through proxy |
| `AFTER_COMMIT` never runs in tests | Test transaction uncommitted or auto-rolling back | Use `TransactionTemplate`/`TestTransaction` |
| Data written in `AFTER_COMMIT` is missing | No new transaction while old resources remain bound | Use another service with `REQUIRES_NEW` |
| Rollback event not received | Published outside transaction or missing phase listener | Check phase and registration |
| Async listener has no immediate result | Task not yet finished or rejected | Check queue/rejections and await outcome |
| Wrong event type | Listener parameter/condition mismatch | Log runtime event type, check wiring |
| Listener registered too late | Event published during context startup | Defer publish or register earlier |
| Using reactive transaction but listener never runs | Reactor transaction context not propagated | Use appropriate `TransactionalEventPublisher` |
| Post-commit network failure loses notification | No durable intent/retry | Transactional outbox/worker |
| Listener runs twice or duplicates side effects | Duplicate publish/retry or multiple listeners/contexts | Event ID, idempotency, check bean registrations |
| `BEFORE_COMMIT` handler throws exception | Can abort commit | Check business rules and error propagation |
| Multiple transaction managers | Wrong manager selected | Specify qualifier/`transactionManager` name explicitly |
| Cache updated before commit | Using plain `@EventListener` | Move to `AFTER_COMMIT` if needed |

### 13.1. Step-by-Step Transaction Debugging

1. Confirm the producer genuinely called `publishEvent(...)`.
2. Confirm the `@Transactional` method was invoked through the Spring-managed proxy.
3. Verify the right `PlatformTransactionManager` and DataSource/EntityManager.
4. Log `TX_ACTIVE` at the moment of publishing.
5. Verify event type/parameter/condition and listener bean registration.
6. Determine whether the transaction actually committed, rolled back, or was marked rollback-only.
7. Check the expected listener phase and `fallbackExecution`.
8. If async, inspect the executor, rejections, error handler, and completion.
9. If the side effect writes to a database, verify the new transaction and affected rows.
10. If delivery must survive crashes, adopt an outbox instead of tweaking annotations alone.

### 13.2. `@TransactionalEventListener` Cannot Fix a Broken Transaction

If a service publishes an event before business invariants are confirmed, or opens the wrong transaction, changing a listener from `@EventListener` to `AFTER_COMMIT` will not fix validation, optimistic locking, transaction ownership, or duplicate commands.

First establish **which fact the event represents** and **which transaction commits that fact**.

## 14. Reactive Transactions (Spring 6.1+) vs. Thread-Bound Transactions

Starting with Spring Framework 6.1, transactional event listeners support both:

- Imperative transactions managed by `PlatformTransactionManager`, typically bound via `ThreadLocal`.
- Reactive transactions managed by `ReactiveTransactionManager`, with context stored in the Reactor context rather than a `ThreadLocal`.

With reactive transactions, simply calling an imperative publisher and expecting listeners to detect the transaction via `ThreadLocal` can fail. Spring provides `org.springframework.transaction.reactive.TransactionalEventPublisher` to attach the proper transaction context to the event source so transactional listeners receive the required context.

This is an **extended topic**, not included in the runnable demo using imperative Spring JDBC. Do not copy `@TransactionalEventListener` code from a JDBC demo into WebFlux/R2DBC and assume identical behavior; follow the reference guide for reactive APIs and test against a real `ReactiveTransactionManager`.

## 15. Security, Data, and Reliability

### 15.1. Do Not Abuse Mutable Payloads

A post-commit listener can retain an event object longer than the method that created it. If the payload references mutable entities or request objects, contents can change before the handler runs (especially under async). Use immutable records/value objects with `eventId`, `aggregateId`, `aggregateVersion`, and minimal data.

### 15.2. Do Not Log Sensitive Data

Avoid publishing or logging full `Authentication` objects, tokens, session cookies, full customer profiles, or large JPA entity graphs. `record.toString()` can print all components. Event IDs and correlation IDs should have proper access controls, and should not be used as high-cardinality metric labels.

### 15.3. Idempotency Still Matters

Even with `AFTER_COMMIT`, events can be published multiple times due to command retries or multiple listeners/contexts. When consumers trigger external side effects, pass an idempotency key if the API supports it and check for duplicates; when using durable queues/brokers, duplicate delivery must be designed for from day one.

### 15.4. Monitoring by Phase and Outcome

You can define custom metrics:

~~~text
app_event_published_total{type="OrderPlaced"}
app_event_after_commit_started_total{listener="SearchListener"}
app_event_after_commit_failed_total{listener="SearchListener"}
app_event_after_rollback_total{listener="CleanupListener"}
app_event_async_rejected_total{pool="notification"}
app_outbox_oldest_pending_age_seconds
~~~

These are **suggested application-instrumented metrics**, not built-in Spring metric names. Distinguish event publication from handler start/completion and durably persisted side effects.

## 16. Common Pitfalls

1. **Using `@EventListener` and assuming it only runs after commit:** plain listeners can run immediately.
2. **Forgetting `AFTER_COMMIT` is the default phase:** the annotation without a phase still waits for commit.
3. **Enabling `fallbackExecution=true` to mask all failures:** can cause out-of-transaction events to be treated like committed facts.
4. **Self-invocation calling `@Transactional`:** bypasses proxies by default, so no new transaction starts as expected.
5. **Instantiating `OrderService` with `new` and expecting `@Transactional` to work:** Spring proxy/interception is required.
6. **Mocking only `ApplicationEventPublisher` to test phases:** mocks do not run transaction synchronization.
7. **Asserting immediately inside a `@Transactional` test:** the transaction has not committed yet or rolls back by default.
8. **Writing to the DB inside `AFTER_COMMIT` without `REQUIRES_NEW`:** old resources remain bound and updates may never commit.
9. **Calling `@Transactional(REQUIRES_NEW)` via `this`:** self-invocation bypasses the proxy.
10. **Using `AFTER_COMMIT` as an outbox:** process crashes can still lose events.
11. **Using `@Async` and assuming jobs are durable:** in-memory queues do not survive crashes.
12. **Ignoring executor rejections and `@Async void` errors:** side effects fail silently.
13. **Believing `@Order` guarantees async completion order:** dispatch order differs from completion order.
14. **Publishing outside a transaction and wondering why the listener skipped:** that is the intended default.
15. **Using `AFTER_COMPLETION` as a success signal:** it runs for both commit and rollback.
16. **Putting full JPA entities into events:** risks lazy-loading failures or data leaks.
17. **Using a rollback listener as proof a domain fact exists:** the transaction may have reverted.
18. **Correct annotation but wrong event type/condition:** listener is not matched.
19. **Publishing events too early in constructors/`@PostConstruct`:** listener infrastructure may not be registered yet.
20. **Mixing transaction managers across different resources:** the phase will not protect the intended business write.
21. **Failing to distinguish reactive and imperative contexts:** transaction binding differs.
22. **Omitting retries/idempotency for critical side effects:** failures/retries can cause duplicates.
23. **Assuming a post-commit error can roll back committed business state:** `AFTER_COMMIT` cannot turn back time.
24. **Not verifying real transaction commits in integration tests:** tests may stay green without verifying phase semantics.
25. **Ignoring shutdown/restart behavior:** in-process listeners can be lost during deployment shutdowns.

## 17. Pre-Production Checklist

- [ ] Event represents a true business **fact**, published after validation?
- [ ] Source transaction is Spring-managed with the right `PlatformTransactionManager`?
- [ ] Producer is invoked through the appropriate Spring bean proxy/transaction context?
- [ ] Listener has the exact event class/condition and is registered before publish time?
- [ ] Phase chosen explicitly for the goal: before, after commit, rollback, or completion?
- [ ] Tested commit and rollback against a real database/transaction manager?
- [ ] Tested out-of-transaction publishing and `fallbackExecution` policy?
- [ ] If `AFTER_COMMIT` writes to the DB, does it use a new proxied transaction?
- [ ] If the listener calls external APIs, are timeouts, retries/idempotency, and error monitoring in place?
- [ ] If `@Async`, does the executor have a bounded queue, rejection policy, and shutdown handling?
- [ ] If jobs must survive crashes, is there an outbox or durable job store?
- [ ] Event DTO is immutable with data minimization, proper versioning/schema, and correlation?
- [ ] Metrics track published/started/succeeded/failed counts and end-to-end lag?
- [ ] `@Transactional` tests do not inadvertently roll back before asserting after-commit behavior?
- [ ] Transaction manager/configuration tested when upgrading Spring or library versions?

## 18. Practice Exercises

1. Run the demo, then change `failAfterPublish` for order 102 from `true` to `false`. How do `AFTER_COMMIT`, `AFTER_ROLLBACK`, and `ROWS_AFTER_ROLLBACK` change?
2. Remove `@EnableTransactionManagement` and observe what happens to listener timing. Explain why missing a transaction causes `AFTER_COMMIT` to skip events by default.
3. Change `onCommit` to `@TransactionalEventListener` without `phase`; does the result change?
4. Set `fallbackExecution=true` on `onCommit`, then publish event 103 outside a transaction. How does the commit counter change? Does that mean event 103 was committed to the DB?
5. Change `onImmediate`'s `@EventListener` to `@TransactionalEventListener(AFTER_COMMIT)`. How does the behavior for rolled-back event 102 differ?
6. Add a `BEFORE_COMMIT` listener that logs; check where its log appears relative to `METHOD_BODY_END` and `AFTER_COMMIT`.
7. Change a listener to `AFTER_COMPLETION` and verify it runs for both commit and rollback cases.
8. Add an audit table with a separate `REQUIRES_NEW` Spring service; prove the audit row commits after the source commit.
9. Place a `@Transactional` method in the same bean and call it via `this.place(...)`. Use `TransactionSynchronizationManager` to explain how it differs from a proxied call.
10. Use `TransactionTemplate` in a JUnit integration test; assert after the execution callback finishes.
11. Try `@Async` and use `CountDownLatch` to wait for listener completion instead of `Thread.sleep`.
12. Given a requirement to deliver `OrderPlaced` to billing even if the app crashes, design an outbox schema and relay; explain why `AFTER_COMMIT` alone is insufficient.

**Answer guide:** (1) order 102 commits, commit listener runs instead of rollback, DB has two rows; (2) Spring transaction proxy is lost so publisher has no active transaction; (3) no, because `AFTER_COMMIT` is the default; (4) listener handles event 103 via fallback, yet no DB commit occurred for event 103; (5) no longer prints immediate on rollback; (6) runs before database commit; (7) both outcomes; (8) invoke through another Spring service proxy; (9) self-invocation bypasses proxy; (10) assert after real commit; (11) await outcome with timeout; (12) write Order + outbox in the same transaction, relay retries, consumer is idempotent.

## 19. Summary

**Creating a transactional event listener** is more than adding an annotation. You must understand real transaction boundaries and verify behavior with a real transaction manager.

- `@EventListener` normally runs immediately at dispatch, potentially before commit.
- `@TransactionalEventListener` binds a handler to a `TransactionPhase`.
- The default phase is `AFTER_COMMIT`; `AFTER_ROLLBACK` runs only on rollback; `AFTER_COMPLETION` runs for both outcomes.
- When published outside a transaction, transactional listeners skip by default; `fallbackExecution=true` changes that contract without creating a transaction.
- `@Transactional` must be activated via a Spring proxy with the right manager/resource.
- In after-completion phases, transaction resources may still be bound without further commits; new DB writes need their own transaction such as `REQUIRES_NEW` via a proxied Spring bean.
- `@Async` does not carry the publisher's imperative transaction to workers and does not guarantee durability.
- `AFTER_COMMIT` guarantees **timing**, not **delivery after a crash**; for mandatory events, use a transactional outbox and idempotent consumers.
- Integration tests must verify real commits and rollbacks, not just Mockito `verify` or `@RecordApplicationEvents`.

Once phase, proxying, transaction boundaries, and failure windows are clearly understood, you can implement post-commit listeners with clear semantics, thorough tests, and without making promises beyond what Spring Application Events provide.

## References

- Spring Framework 6.2 — *Transaction-bound Events*: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
- Spring Framework 6.2.8 Javadoc — *TransactionalEventListener*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html
- Spring Framework 6.2.8 Javadoc — *TransactionPhase*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/transaction/event/TransactionPhase.html
- Spring Framework — *Using @Transactional*: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — *TransactionSynchronization / afterCompletion*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html
- Spring Framework — *Application Events*: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework — *Reactive TransactionalEventPublisher*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/transaction/reactive/TransactionalEventPublisher.html
- Spring Framework — *Test-managed Transactions*: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html
