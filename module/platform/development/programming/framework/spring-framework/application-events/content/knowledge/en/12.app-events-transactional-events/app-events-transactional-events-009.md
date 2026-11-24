# Post-Commit Listeners Cannot Roll Back a Completed Transaction

In Spring Framework, a listener annotated with `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` is processed **after the event-publishing transaction has committed successfully**. Because the original transaction's data has already been confirmed at the database layer, an error occurring in the listener at this point **cannot revert and roll back the original transaction**.

This is the core distinction between two questions:

- **Did the original transaction succeed?** Decided at the transaction's commit step.
- **Did the post-commit follow-up work succeed?** That is the separate outcome of the listener, such as sending an email, calling a webhook, updating a search index, or saving a tracking record.

For example: the order creation transaction has committed, and then the email-sending listener encounters a network error. The order **still exists**; the failed email needs its own handling or retry mechanism. You cannot "throw an exception to roll back the order" once the commit has already completed.

## 1. Position of `AFTER_COMMIT` in the Transaction Lifecycle

Consider the order creation flow:

```text
Service starts transaction T1
  |
  +-- INSERT orders (uncommitted)
  |
  +-- publishEvent(OrderCreated)
  |     +-- Spring registers AFTER_COMMIT listener with T1
  |         (listener does not execute at publish time)
  |
  +-- Business method ends normally
  |
  +-- Transaction manager COMMITS T1 successfully
  |     +-- orders becomes committed data
  |
  +-- Execute AFTER_COMMIT listener
        +-- Send email / call API / update auxiliary data
        +-- If an error occurs, T1 is still committed
```

`@TransactionalEventListener` binds a listener to a transaction phase. The default phase is `AFTER_COMMIT`, so the following two declarations have the same meaning:

```java
@TransactionalEventListener
public void onOrderCreated(OrderCreated event) {
    // After the source transaction commits successfully.
}

@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderCreated(OrderCreated event) {
    // Same phase as the default declaration.
}
```

*These are two alternative declarations; do not register both methods at the same time if you only want to process once.*

Distinguishing the phases:

| Phase | Timing | Can an error roll back the source transaction? |
| --- | --- | --- |
| `BEFORE_COMMIT` | Before commit, while the transaction has not ended | Can cause the commit to fail and lead to rollback; also depends on flow and transaction manager |
| `AFTER_COMMIT` (default) | After successful commit | **No**: the source transaction has already committed |
| `AFTER_ROLLBACK` | After the transaction has rolled back | **No**: the rollback has already occurred |
| `AFTER_COMPLETION` | After completion, regardless of commit or rollback | **No**: the source transaction outcome has already been decided |

Note: Spring implements `AFTER_COMMIT` listeners via the transaction completion synchronization mechanism; do not infer that the listener is called from `TransactionSynchronization.afterCommit()` solely because the phase name is similar. What to rely on is the contract of `@TransactionalEventListener`: the callback executes after the source transaction has committed successfully.

## 2. Why Do Exceptions in the Listener Not Undo the Commit?

Rollback can only affect a transaction that is still in a revertible state. Once the database has confirmed the `COMMIT` of T1, T1's changes belong to the database's durable state. An exception occurring **after** that point has no authority to reverse the just-completed commit decision.

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void sendNotification(OrderCreated event) {
    throw new IllegalStateException("Email provider unavailable");
}
```

The snippet above illustrates a failing callback. Depending on the callback path and how Spring/the application handles exceptions, the error may be logged or surfaced to the calling layer; **no path turns a post-commit error into a rollback of T1**. Do not interpret an HTTP 500 returned at the end as proof that the database rolled back: the client may receive an error while the data has actually committed.

A practical consequence is that **request status and transaction status can diverge**. If a client receives an error and retries, there must be a mechanism to prevent duplicate order creation (an idempotency key, unique constraint, or request ID check) rather than assuming "failed request means not saved."

## 3. Runnable Java 17+ Example: Email Fails Yet the Order Remains Committed

The example uses Spring Framework, Spring JDBC, and an in-memory H2 database. `TransactionTemplate` creates real transactions, `JdbcTemplate` writes data, and `@TransactionalEventListener` receives events at the post-commit phase. No Spring Boot required.

Directory structure:

```text
after-commit-demo/
├── pom.xml
└── src/main/java/AfterCommitDemo.java
```

Create `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>after-commit-demo</artifactId>
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
                    <mainClass>AfterCommitDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Create `src/main/java/AfterCommitDemo.java`:

```java
import org.h2.jdbcx.JdbcDataSource;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

public class AfterCommitDemo {

    public record OrderCreated(long orderId) {}

    public static class NotificationListener {

        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
        public void onOrderCreated(OrderCreated event) {
            // Simulate a failing notification service.
            try {
                sendEmail(event.orderId());
            } catch (IllegalStateException ex) {
                System.out.println("AFTER_COMMIT: email failed for " + event.orderId());
            }
        }

        private void sendEmail(long orderId) {
            throw new IllegalStateException("Mail server unavailable");
        }
    }

    public static void main(String[] args) {
        var dataSource = new JdbcDataSource();
        dataSource.setURL("jdbc:h2:mem:ordersdb;DB_CLOSE_DELAY=-1");
        dataSource.setUser("sa");

        var jdbc = new JdbcTemplate(dataSource);
        jdbc.execute("CREATE TABLE orders (id BIGINT PRIMARY KEY)");

        var manager = new DataSourceTransactionManager(dataSource);
        var tx = new TransactionTemplate(manager);

        try (var context = new AnnotationConfigApplicationContext()) {
            context.registerBean(NotificationListener.class);
            context.refresh();

            // T1: order saved successfully; post-commit email sending fails.
            tx.executeWithoutResult(status -> {
                jdbc.update("INSERT INTO orders (id) VALUES (?)", 42L);
                context.publishEvent(new OrderCreated(42L));
                System.out.println("T1: inserted and published order 42");
            });

            Long count42 = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM orders WHERE id = 42",
                    Long.class
            );
            System.out.println("T1: committed orders with id 42 = " + count42);

            // T2: error BEFORE commit; AFTER_COMMIT listener does not run.
            try {
                tx.executeWithoutResult(status -> {
                    jdbc.update("INSERT INTO orders (id) VALUES (?)", 43L);
                    context.publishEvent(new OrderCreated(43L));
                    System.out.println("T2: inserted and published order 43");
                    throw new IllegalStateException("Business rule rejected");
                });
            } catch (IllegalStateException ex) {
                System.out.println("T2: rolled back");
            }

            Long count43 = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM orders WHERE id = 43",
                    Long.class
            );
            System.out.println("T2: committed orders with id 43 = " + count43);
        }
    }
}
```

From the project directory, run (requires JDK 17+, Maven, and initial dependency download capability):

```bash
mvn -q compile exec:java
```

Key lines printed by the program, in order:

```text
T1: inserted and published order 42
AFTER_COMMIT: email failed for 42
T1: committed orders with id 42 = 1
T2: inserted and published order 43
T2: rolled back
T2: committed orders with id 43 = 0
```

Result explanation:

1. For **T1**, the order record `42` is committed. The listener runs after commit, simulates a failed email send and catches the error; the post-transaction query still sees **one** order with ID `42`.
2. For **T2**, the error is thrown right inside the **pre-commit** work. `TransactionTemplate` performs a rollback; the `AFTER_COMMIT` listener for order `43` does not run; the query finds **no** order `43`.
3. The example catches the exception inside the listener to keep stdout clean and easy to reproduce. Even if the exception were allowed to escape, it still **could not roll back T1** because the commit already finished; how errors are reported to the caller/logged can differ depending on the transaction synchronization path.

The example uses the `OrderCreated` record as a plain event payload; `@TransactionalEventListener` can receive this object type. `NotificationListener` is registered as a Spring bean so Spring discovers the annotation. `JdbcTemplate` and `DataSourceTransactionManager` share the **same** `DataSource` so the INSERT statement participates in the proper transaction.

## 4. Pitfall: Transaction Resources Are Still Accessible After Commit

A dangerous misconception is: "Once in `AFTER_COMMIT`, every repository operation automatically opens a new transaction."

In thread-bound transactions (e.g., `DataSourceTransactionManager` or `JpaTransactionManager`), **the original transaction's resource is sometimes still bound to the thread and accessible** during the post-commit callback. Thus, database access code may look like it is participating in the old transaction, but **there is no subsequent commit pass** for that transaction. Consequently, writes inside the listener may not be persisted as the developer expects.

The following snippet **only illustrates the problem**, assuming `auditRepository` is a configured repository:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderCreated(OrderCreated event) {
    auditRepository.save(new AuditLog(event.orderId(), "CREATED"));
    // Do not assume this write operation will definitely be COMMITTED.
}
```

If you need to persist database changes **after commit**, perform that work in **a new transaction with a clear boundary**, such as a separate Spring service with `@Transactional(propagation = Propagation.REQUIRES_NEW)`:

```java
@Service
public class AuditService {
    private final AuditRepository auditRepository;

    public AuditService(AuditRepository auditRepository) {
        this.auditRepository = auditRepository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void saveAudit(long orderId) {
        auditRepository.save(new AuditLog(orderId, "CREATED"));
    }
}

@Component
public class OrderAuditListener {
    private final AuditService auditService;

    public OrderAuditListener(AuditService auditService) {
        this.auditService = auditService;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(OrderCreated event) {
        auditService.saveAudit(event.orderId());
    }
}
```

This is an **illustrative integration snippet for a Spring Data application**, not an addition to the standalone Maven example in section 3. The `AuditRepository` and `AuditLog` classes must exist in a real application; annotations and types like `@Service`, `@Component`, `@Transactional`, and `Propagation` require the corresponding imports.

`REQUIRES_NEW` creates an **independent physical transaction** for `saveAudit`, so the audit record can be committed separately. If the audit transaction fails, only the audit transaction rolls back; **T1's order remains committed**. Placing the service in another Spring bean also ensures the call goes through Spring's transaction proxy; calling `this.saveAudit(...)` within the same bean under default proxy mode bypasses interception and does not achieve the desired effect.

Consider connection pool configuration when using `REQUIRES_NEW`: a new transaction requires its own resource; a nested call inside a transaction still holding a connection can increase connection demand. For post-commit callbacks, resources from the original transaction may also not yet be completely cleaned up.

## 5. Proper Design When Post-Commit Work Fails

`@TransactionalEventListener(AFTER_COMMIT)` is suitable for tasks reacting after the primary data has been saved. It **does not by itself provide** durable retries, deduplication, queuing, or an atomic transaction across the database and external email/APIs.

### 5.1. Auxiliary Work Not Requiring Strict Guarantees

For example: recording best-effort metrics or sending non-critical notifications. The listener can catch errors, log with context (event ID, order ID), collect metrics, and leave the main transaction's result intact. Swallowing errors must be intentional; if the client must know the email failed, represent **a separate notification delivery status** rather than returning an error that misleads the client into thinking the order was not saved.

### 5.2. Ensuring Work Will Be Retried: Transactional Outbox

For critical business logic (emitting events to other systems, payment synchronization, sending data to a message broker), there is a failure window: the database has committed, but the application shuts down before the callback completes. Relying solely on an in-memory listener means that work can be lost.

The **Transactional Outbox** pattern closes this window:

1. **Within the same transaction T1**, write the business data (e.g., `orders`) and an `outbox` record with a stable ID, event type, necessary payload, and status `PENDING`.
2. Only when **T1 commits successfully** do both the order and the outbox message durably exist. If T1 rolls back, both disappear together.
3. An independent worker reads the outbox, sends to the service/broker, and updates `SENT` in a separate transaction.
4. If sending fails or the process stops, the worker can retry with backoff. Consumers must handle **idempotency** because duplicate sends can happen when the worker sends successfully before marking `SENT`.

```text
T1: INSERT orders + INSERT outbox -> COMMIT
                                   |
                                   v
                       Outbox worker reads PENDING
                                   |
                      send / retry / deduplicate
                                   |
                       separate transaction: SENT
```

`AFTER_COMMIT` can be used to wake up the outbox worker faster, but **the durably persisted outbox is the source guaranteeing recovery**; the callback is only an optimization signal.

### 5.3. Requiring "All Succeed or None Succeed"

If multiple steps **are all operations on the same database** and must be atomic, execute them **before commit in the same transaction** (usually via a coordinating service), and commit once. Atomicity between committing an order and sending an email afterward cannot be achieved merely through `@Order`, `@Transactional`, or `@TransactionalEventListener`.

If external services are involved and a multi-step recoverable flow is needed, design business states and compensating actions (compensation/Saga) where appropriate. Compensation is a **new business operation**, not a technical rollback of an already-committed transaction.

## 6. Commonly Confused Situations

**A regular `@EventListener` differs from a transaction-bound listener.** A synchronous `@EventListener` can be invoked immediately when `publishEvent(...)` executes, while the source transaction is still open. Exceptions from a regular listener can propagate and cause the pre-commit business flow to fail. `@TransactionalEventListener(AFTER_COMMIT)` actively waits for a successful commit before processing.

**Without a transaction, the listener may not run.** With the default `fallbackExecution = false`, if an event is published when no suitable transaction exists, a transaction-bound listener will **not be invoked**. Configuring `fallbackExecution = true` allows execution without a transaction, but then there is no longer a guarantee of "running only after an actual commit." If the problem strictly requires post-commit execution, ensure the publisher actually runs inside a transaction.

**`@Async` does not make post-commit work part of T1.** If executed asynchronously, the callback may run on a different thread. Exceptions, retries, and completion order must be managed separately; thread-local transaction context does not automatically follow every offloaded task.

**`@Order` does not fix the issue.** Even though listeners have a specified invocation order, a listener running at `AFTER_COMMIT` still cannot roll back an already-committed transaction. Do not use listener ordering as a substitute for transaction boundaries and business dependencies.

**Do not treat HTTP 500 as a rollback.** A request can report an error due to post-processing while the INSERT has already committed. When the client retries, use a request ID/idempotency key and appropriate unique constraints to avoid duplicating data.

**Do not write to the database after commit and assume there is a second commit.** Transaction resources may still be accessible; use an explicit new transaction (`REQUIRES_NEW` via Spring proxy) for changes that must be saved independently, or move that write into the original transaction if atomicity is mandatory.

## 7. How to Test and Self-Check Questions

In an integration test with a real database and transaction manager, verify three scenarios:

| Scenario | Source transaction status | Expectation |
| --- | --- | --- |
| Commit succeeds, post-commit listener fails sending email | Committed | Business data still exists; email error is recorded separately |
| Error in service before commit | Rolled back | Business data does not exist; `AFTER_COMMIT` listener does not run |
| Commit succeeds, listener writes audit in `REQUIRES_NEW` transaction but audit rolls back | Source transaction committed | Business data still exists; audit failure/retry is handled separately |

When testing, re-query the database using an independent connection/transaction after the processing flow ends to avoid confusing data remaining in a persistence context with actually committed data. Do not rely solely on logs printed by the listener as proof of rollback/commit.

Self-check:

1. **If `@TransactionalEventListener(AFTER_COMMIT)` throws an exception, does the preceding order automatically roll back?** No, because the commit has already completed.
2. **If an audit record needs to be written from the listener, how should it be done?** Use an independent transaction (e.g., a `REQUIRES_NEW` service) or write the audit inside T1 if it must be atomic with the order.
3. **What if the application crashes right after commit and before sending an event to the broker?** In-memory listeners do not guarantee recovery; consider an outbox in the same transaction and a worker with retries/idempotency.
4. **What if the event is published outside a transaction?** Transaction-bound listeners do not run by default; `fallbackExecution = true` changes that behavior but does not create a fake commit.

## Official Documentation

- [Spring Framework Reference — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Javadoc — `@TransactionalEventListener`, warning on resources still active after completion](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [Javadoc — `TransactionSynchronization`](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html)
- [Spring Framework Reference — Transaction Propagation (`REQUIRES_NEW`)](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/tx-propagation.html)
