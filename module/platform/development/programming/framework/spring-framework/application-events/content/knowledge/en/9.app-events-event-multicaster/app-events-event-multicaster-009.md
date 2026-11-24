# Impact of Event Multicaster on Transactions in Spring Framework

## 1. Problem: What Does Publishing an Event Inside a Transaction Mean?

Suppose the application is creating an invoice inside a method managed by Spring with `@Transactional`. Immediately after the write statement, the method calls `ApplicationEventPublisher.publishEvent(new InvoiceCreated(...))`. There are two independent questions:

1. **Where and when does the listener run?** This depends on `ApplicationEventMulticaster` and annotations such as `@Async`.
2. **In which transaction context does the listener run?** This depends on which thread the transaction is bound to, what kind of listener it is, and whether the listener is bound to a transaction phase.

`ApplicationEventMulticaster` is responsible for selecting and dispatching events to appropriate listeners; it is **not a transaction manager**, and does not automatically open, commit, or roll back a transaction per listener. Changing the multicaster configuration can move a listener from being invoked inside the publisher's transaction to running on another thread **without that transaction**. This difference directly affects data consistency, error handling, and when notifications are sent to external systems.

This lesson focuses on Spring Framework 6.1+ with **imperative transactions** via `PlatformTransactionManager` (for example, JDBC/JPA), while also pointing out differences when using reactive transactions.

## 2. Default: `SimpleApplicationEventMulticaster` Invokes Synchronously

If the application does not define a special bean named `applicationEventMulticaster`, `ApplicationContext` typically uses `SimpleApplicationEventMulticaster` in synchronous mode. For a regular `@EventListener`:

- The publisher calls `publishEvent(event)` directly on the current thread.
- The multicaster finds matching listeners and invokes them directly on that thread.
- `publishEvent(...)` usually returns only after synchronous listeners finish running.
- If the publisher's thread is currently bound by Spring to a transaction, synchronous listeners usually see **the same thread-bound transaction** and the same resources managed under that transaction.
- The listener does not get a new transaction automatically: it is running inside the publisher's already existing transaction scope, unless a different propagation configuration is applied via a transactional proxy.

Illustrative example in a service invoked **through a Spring proxy**:

```java
@Service
public class InvoiceService {
    private final JdbcTemplate jdbc;
    private final ApplicationEventPublisher publisher;

    public InvoiceService(JdbcTemplate jdbc, ApplicationEventPublisher publisher) {
        this.jdbc = jdbc;
        this.publisher = publisher;
    }

    @Transactional
    public void issueInvoice(long invoiceId) {
        jdbc.update("INSERT INTO invoices (id) VALUES (?)", invoiceId);
        publisher.publishEvent(new InvoiceCreated(invoiceId));
        // The transaction normally commits only after the method completes successfully.
    }
}
```

This is an **integration snippet**, assuming an `invoices` table, `InvoiceCreated` record, `JdbcTemplate` bean, and an appropriate transaction manager. If a synchronous listener updates another table using the same JDBC transaction, changes from both publisher and listener can commit or roll back together. However, sending HTTP requests, emails, or publishing to a broker inside a synchronous listener is **not automatically undone by the database transaction**. If the DB transaction rolls back after an email has been sent, the email can still exist.

### Exceptions and Rollback in Synchronous Mode

With the default multicaster configuration and no custom `ErrorHandler`, an exception from a synchronous listener can propagate back through `publishEvent(...)` to the publisher. If it is an unchecked exception escaping the `@Transactional` method, Spring marks rollback by default for `RuntimeException` and `Error`. This is an effect of the **transaction boundary**, not the multicaster rolling back on its own.

If the publisher catches and swallows the exception, if the multicaster is configured with an `ErrorHandler` to handle the error, or if the transaction has custom rollback rules, the outcome can differ. Do not write business logic assuming that every listener error always causes the database to roll back.

## 3. Switching the Multicaster to Asynchronous: Transactions Do Not Automatically Follow Threads

You can register an `applicationEventMulticaster` bean and attach a `TaskExecutor`:

```java
@Configuration
class EventDispatchConfig {
    @Bean(name = "applicationEventMulticaster")
    ApplicationEventMulticaster applicationEventMulticaster(
            @Qualifier("eventExecutor") TaskExecutor eventExecutor) {

        SimpleApplicationEventMulticaster multicaster =
                new SimpleApplicationEventMulticaster();
        multicaster.setTaskExecutor(eventExecutor);
        return multicaster;
    }
}
```

This configuration snippet requires Spring imports and a `TaskExecutor` bean named `eventExecutor`, such as a `ThreadPoolTaskExecutor`. It changes the dispatch mechanism for listeners that **allow** asynchronous execution.

When a regular `@EventListener` runs via the executor on another thread:

1. The event-publishing thread can continue and finish the transaction before the listener starts or finishes.
2. With imperative JDBC/JPA transactions, Spring's transaction context is managed by default using `ThreadLocal`, so it does not automatically appear on the executor thread.
3. `TransactionSynchronizationManager.isActualTransactionActive()` usually returns `false` on an asynchronous listener thread, even though the publisher is inside a transaction.
4. If the listener itself calls a `@Transactional` service, that service may start **its own transaction** according to its propagation; this is not the publisher's original transaction.
5. Reading rows the publisher just wrote but has not yet committed may not see the data, depending on isolation/DB. If the publisher rolls back afterward, the listener may still have run and caused external side effects.
6. Exceptions in an asynchronous task do not automatically propagate back to roll back the transaction handled on the publisher thread.

**Do not** attempt to move an open JDBC transaction to another thread by copying `ThreadLocal`. Transactions are tied to specific resources/connections and lifecycles. Context propagation for tracing, MDC, or security does not equate to safely transferring an active transaction.

`@Async` placed on an `@EventListener` can also cause the listener body to execute asynchronously when `@EnableAsync` and a proxy/executor are configured. You must evaluate both **the multicaster's executor** and **`@Async` on the method**; checking only one of the two can miss a thread switch.

## 4. Important Exception: `@TransactionalEventListener`

`@TransactionalEventListener` is designed to register a callback with the transaction lifecycle at the time the event is published. By default, the listener is invoked in the `AFTER_COMMIT` phase, meaning after the transaction commits successfully; if it rolls back, the `AFTER_COMMIT` callback does not run.

In Spring Framework 6.1+, `TransactionalApplicationListener` (including the adapter for `@TransactionalEventListener`) declares that it **does not support asynchronous dispatch at the multicaster level** via `supportsAsyncExecution()`. Therefore, with `SimpleApplicationEventMulticaster.setTaskExecutor(...)`:

- Regular `@EventListener` listeners can be run by the executor on another thread.
- The `@TransactionalEventListener` adapter is still **invoked by the multicaster on the event-publishing thread to register transaction synchronization**. The processing declared by the annotation will then be invoked in the corresponding transaction phase later.
- Do not assume, just because an executor is configured on the multicaster, that transactional listeners lose transaction registration or run immediately on a worker thread.

**Distinction:** synchronous adapter registration does not mean the *method body* always runs synchronously if you explicitly add `@Async` to the `@TransactionalEventListener` method. In that case, the transaction-phase callback can trigger an asynchronous task and the actual processing runs on another thread after the phase occurs. Separate transaction management is required for any DB operations performed on that thread.

### Transaction Phases

| `@TransactionalEventListener` Phase | Timing | Practical Meaning |
| --- | --- | --- |
| `BEFORE_COMMIT` | Before commit, while the transaction can still roll back | Suitable for checks/preparation tied to commit, while still needing to handle a possible commit failure afterward |
| `AFTER_COMMIT` *(default)* | After a successful commit | Suitable for triggering actions that should happen only after DB data has committed |
| `AFTER_ROLLBACK` | After the transaction rolls back | Used for logging, compensation, or appropriate cleanup |
| `AFTER_COMPLETION` | After the transaction finishes, whether committed or rolled back | Used for behavior that needs to know a transaction has completed |

Example:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(InvoiceCreated event) {
    notificationService.enqueueNotification(event.id());
}

@TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
public void afterRollback(InvoiceCreated event) {
    auditLogger.noteCanceledInvoice(event.id());
}
```

This is an **illustrative snippet**, requiring the corresponding services. Phase configuration belongs to the transactional listener; `@Order` or the multicaster's invocation order cannot turn an `AFTER_COMMIT` callback into *before-commit* processing.

If an event is published when **no transaction is active**, `@TransactionalEventListener` by default **does not run** because there is no transaction phase to bind to. You can specify `fallbackExecution = true` if you still want the listener to execute when there is no transaction:

```java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT,
        fallbackExecution = true
)
public void handle(InvoiceCreated event) {
    // With transaction: runs according to phase; without: allowed to run fallback.
}
```

Do not enable fallback just to "fix" an event that lost its transaction due to misconfigured asynchrony: in that case, the "process only after commit" guarantee no longer holds for the fallback branch.

### Very Common Pitfall When Writing to the DB in `AFTER_COMMIT`

In the `AFTER_COMMIT`/`AFTER_ROLLBACK`/`AFTER_COMPLETION` phases, the transaction has already finished, yet resources (connections, sessions) can sometimes still remain bound during the callback stage. Spring documentation warns that data-access calls at this point **may still participate in the old transaction's resources without committing new changes**.

If you need to write another DB record after commit, open a genuinely new transaction, typically with `PROPAGATION_REQUIRES_NEW` on a public method of **another Spring bean**, invoked through a proxy:

```java
@Service
public class DeliveryAuditService {
    private final JdbcTemplate jdbc;

    public DeliveryAuditService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordDeliveryRequest(long invoiceId) {
        jdbc.update(
            "INSERT INTO delivery_audit (invoice_id) VALUES (?)",
            invoiceId
        );
    }
}
```

The `AFTER_COMMIT` listener can call `deliveryAuditService.recordDeliveryRequest(event.id())`. The example assumes the `delivery_audit` table and appropriate imports already exist. Internal self-invocation `this.recordDeliveryRequest(...)` within the same bean usually bypasses the transaction proxy and therefore does not guarantee opening a new transaction. A separate post-commit transaction **does not make non-DB operations atomic with the original transaction**.

## 5. Runnable Example: Same Event, Two Multicasters, Different Transaction Contexts

The following example runs with Java 17+, Spring Framework 6.2.x, and in-memory H2. It uses `TransactionTemplate` to clearly show two transactions: invoice 1 is committed, invoice 2 is rolled back. With the same listener code, running in synchronous mode and asynchronous executor mode will show different transaction contexts for `@EventListener`, while `@TransactionalEventListener` still observes the exact phase.

Directory structure:

```text
multicaster-transaction-demo/
├── pom.xml
└── src/main/java/MulticasterTransactionDemo.java
```

### `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>multicaster-transaction-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.9</version>
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
                <version>3.5.1</version>
                <configuration>
                    <mainClass>MulticasterTransactionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### `src/main/java/MulticasterTransactionDemo.java`

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import javax.sql.DataSource;

import org.springframework.context.event.ApplicationEventMulticaster;
import org.springframework.context.event.EventListener;
import org.springframework.context.event.SimpleApplicationEventMulticaster;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.transaction.support.TransactionTemplate;

public class MulticasterTransactionDemo {

    public record InvoiceCreated(int id) {}

    @Configuration
    public static class DbConfig {

        @Bean
        public DataSource dataSource() {
            var ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:events;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public PlatformTransactionManager transactionManager(DataSource ds) {
            return new DataSourceTransactionManager(ds);
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }
    }

    public static class Handlers {
        private final Queue<String> lines;
        private final CountDownLatch done;

        public Handlers(Queue<String> lines, CountDownLatch done) {
            this.lines = lines;
            this.done = done;
        }

        @EventListener
        public void ordinary(InvoiceCreated event) {
            boolean active =
                    TransactionSynchronizationManager.isActualTransactionActive();
            lines.add("PLAIN " + event.id() + " txActive=" + active);
            done.countDown();
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
        public void onCommit(InvoiceCreated event) {
            lines.add("AFTER_COMMIT " + event.id());
            done.countDown();
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
        public void onRollback(InvoiceCreated event) {
            lines.add("AFTER_ROLLBACK " + event.id());
            done.countDown();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        boolean async = args.length > 0 && args[0].equals("async");
        Queue<String> lines = new ConcurrentLinkedQueue<>();
        CountDownLatch done = new CountDownLatch(4);
        ExecutorService executor =
                async ? Executors.newSingleThreadExecutor() : null;

        try (var context = new AnnotationConfigApplicationContext()) {
            context.register(DbConfig.class);
            context.registerBean(
                    Handlers.class,
                    () -> new Handlers(lines, done)
            );

            if (async) {
                context.registerBean(
                        "applicationEventMulticaster",
                        ApplicationEventMulticaster.class,
                        () -> {
                            var multicaster =
                                    new SimpleApplicationEventMulticaster();
                            multicaster.setTaskExecutor(executor);
                            return multicaster;
                        }
                );
            }

            context.refresh();

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute("CREATE TABLE invoices (id INT PRIMARY KEY)");

            TransactionTemplate tx = new TransactionTemplate(
                    context.getBean(PlatformTransactionManager.class)
            );

            // First transaction: commit.
            tx.executeWithoutResult(status -> {
                jdbc.update("INSERT INTO invoices (id) VALUES (?)", 1);
                context.publishEvent(new InvoiceCreated(1));
            });

            // Second transaction: explicit rollback.
            tx.executeWithoutResult(status -> {
                jdbc.update("INSERT INTO invoices (id) VALUES (?)", 2);
                context.publishEvent(new InvoiceCreated(2));
                status.setRollbackOnly();
            });

            if (!done.await(15, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Missing listener callbacks");
            }

            var output = new ArrayList<>(lines);
            Collections.sort(output); // Stabilizes stdout without assuming execution timing.
            output.forEach(System.out::println);
            System.out.println(
                    "Persisted IDs: " +
                    jdbc.queryForList(
                            "SELECT id FROM invoices ORDER BY id",
                            Integer.class
                    )
            );
        } finally {
            if (executor != null) {
                executor.shutdown();
            }
        }
    }
}
```

The two transactional listeners only count down when the corresponding phase actually occurs: `AFTER_COMMIT` receives invoice 1, whereas `AFTER_ROLLBACK` receives invoice 2. The two regular `@EventListener` calls are always dispatched regardless of whether the transaction later commits or rolls back. `CountDownLatch` waits for asynchronous listeners and `Collections.sort` displays results in a fixed order; **the order of stdout lines does not represent actual execution order**.

### Running in Default Synchronous Mode

```bash
mvn -q compile exec:java
```

Output from the program's `System.out.println` statements:

```text
AFTER_COMMIT 1
AFTER_ROLLBACK 2
PLAIN 1 txActive=true
PLAIN 2 txActive=true
Persisted IDs: [1]
```

`@EventListener` ran on the event-publishing thread while the transaction was active, so `txActive=true`. Even though listener `PLAIN 2` was invoked, the database row with `id=2` rolled back. The `AFTER_COMMIT` listener did not process invoice 2.

### Running with a Multicaster Using an Executor

```bash
mvn -q compile exec:java -Dexec.args=async
```

Output from the program's `System.out.println` statements:

```text
AFTER_COMMIT 1
AFTER_ROLLBACK 2
PLAIN 1 txActive=false
PLAIN 2 txActive=false
Persisted IDs: [1]
```

The regular `@EventListener` moved to the executor thread and no longer saw the transaction of the thread calling `publishEvent`. Meanwhile, the transactional listeners were still registered on the original thread and received callbacks according to commit/rollback. Even though the async listener prints `PLAIN 1` at the end of the sorted list, do not infer that it **executed** after commit: the code intentionally sorted the log strings for comparison.

If you replace the logging in `ordinary(...)` with a DB query, the query could occur before or after commit, so query results under async mode can differ from synchronous mode. This is precisely the hazard of turning a listener that depends on transaction state into an asynchronous task.

## 6. Comparison Table for Choosing the Right Configuration

| Mechanism | Typical thread/timing of execution | Uses publisher's original transaction? | If publisher rolls back |
| --- | --- | --- | --- |
| `@EventListener` + default synchronous multicaster | Immediately when `publishEvent` invokes listener, same thread | Can use the same active thread-bound transaction | Listener already ran; DB writes in same transaction roll back, but non-DB side effects may already have happened |
| `@EventListener` + executor multicaster | Executor thread, timing not fixed relative to commit | Does **not** automatically inherit publisher's transaction | Listener can still run and produce effects outside the original transaction |
| `@TransactionalEventListener(AFTER_COMMIT)` | Callback after successful commit | No longer an active transaction to keep writing as before commit; old resources may linger temporarily | `AFTER_COMMIT` callback does not run on rollback |
| `@TransactionalEventListener(AFTER_ROLLBACK)` | Callback after rollback | Transaction has already ended | `AFTER_ROLLBACK` callback runs |
| `@TransactionalEventListener(BEFORE_COMMIT)` | Callback before commit while transaction is finalizing | Still in transaction context before commit | No guarantee this callback ran if transaction rolls back before reaching commit phase |

Avoid interpreting the table as a delivery guarantee: `@TransactionalEventListener(AFTER_COMMIT)` runs the callback **after commit**, yet it is not a durable queue. The process can crash between database commit and sending the message/email. If reliable delivery to another system is required, one option is the **transactional outbox**: write the event to an outbox table in the same transaction as business data, then have a separate worker read, send, and retry with an idempotency key.

## 7. Execution Order, Errors, and Consistency

- **`@Order` does not define commit timing.** It only adjusts the invocation priority of matching listeners. With an executor, dispatch order does not guarantee completion order. With transactional listeners, the `BEFORE_COMMIT`/`AFTER_COMMIT` phase still determines callback timing.
- **Do not conflate "listener invoked" with "DB write succeeded".** A regular listener can be invoked before rollback. A notification receiver might observe "invoice created" while the DB has no such invoice.
- **Do not treat the event multicaster as a durable event broker.** Spring's in-process mechanism does not automatically guarantee replay, retries, exactly-once delivery, or distributed transactions.
- **Configuring `ErrorHandler` changes how errors propagate.** If the handler processes or swallows exceptions, the publisher may not know a listener failed. With an executor, exceptions belong to the task running on the worker thread.
- **Do not rely on transaction context on another thread.** With JDBC/JPA, async events should carry stable data or identifiers so the listener can re-read inside its own post-commit transaction.
- **Watch HTTP responses.** With an async multicaster, an API can return success after DB commit while event tasks are still running; you need an error-recording and retry strategy if side effects are mandatory.
- **Do not rely on `@Transactional` when calling the same bean via `this.method()`.** Proxy-based transactions generally do not apply to self-invocation; call through an appropriate bean/proxy.
- **Do not expect DB rollback inside an `AFTER_COMMIT` callback.** By that point the transaction has already committed; a failed callback does not automatically undo a completed transaction.

### If the Application Uses Reactive Transactions

Since Spring 6.1, `@TransactionalEventListener` also supports transactions managed by `ReactiveTransactionManager`. However, reactive transactions are bound to the **Reactor Context**, not JDBC/JPA-style `ThreadLocal` rules. When publishing events inside a reactive transaction, you must propagate the transaction context properly (for example, via `TransactionalEventPublisher` and including context in the event source) so the listener binds to the transaction phase. You cannot take conclusions about `isActualTransactionActive()` or JDBC threads and apply them verbatim to a reactive pipeline.

## 8. How to Test Before Changing the Multicaster in a Project

For an event published inside a real business transaction, test the following cases:

1. **Successful commit:** `@EventListener` receives the event; `@TransactionalEventListener(AFTER_COMMIT)` runs right after commit; DB data is persisted.
2. **Rollback:** `@EventListener` may have run; `AFTER_COMMIT` does not run; `AFTER_ROLLBACK` runs; DB data written by the publisher is rolled back.
3. **No transaction:** `@TransactionalEventListener` does not run by default; only enable fallback execution when explicitly intended.
4. **With executor:** verify regular listeners do not rely on the publisher's transaction; verify transactional listeners still receive the right callbacks; use `CountDownLatch`/barriers instead of `Thread.sleep` to control asynchrony.
5. **Listener failure:** verify how exceptions affect rollback, API responses, logs, and retry mechanisms; test both synchronous and async modes.
6. **Work needing DB writes after commit:** use a service opening a new transaction and verify the record is actually persisted; for outbound messages, test idempotency and retry/crash scenarios.

## 9. Design Takeaways

A business flow that requires **sharing the same transaction and rolling back together** should usually be coordinated explicitly within the same service/transaction, or use a synchronous listener when the dependency is intentional and tested. An action that must execute **only after DB commit succeeds** fits `@TransactionalEventListener(AFTER_COMMIT)`. An **asynchronous task requiring guaranteed delivery and retries** should have a durable persistence mechanism such as an outbox, rather than relying solely on the multicaster's executor.

The first checkpoints when seeing a listener "not seeing data", "not rolling back with the publisher", or "running despite transaction failure" are: does the current multicaster have a `TaskExecutor`, is the listener `@EventListener` or `@TransactionalEventListener`, is `@Async` present, and what phase is the original transaction in when the event is published?

## References

- [Spring Reference – Application events and SimpleApplicationEventMulticaster](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Reference – Transaction-bound events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Javadoc – SimpleApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Javadoc – TransactionalEventListener](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [Javadoc – TransactionalApplicationListener](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/transaction/event/TransactionalApplicationListener.html)
