# Transaction Phase BEFORE_COMMIT in Spring Framework Application Events

## 1. Lesson Objectives

`TransactionPhase.BEFORE_COMMIT` allows a listener to handle an event **right before Spring commits the current transaction**. It is a specific phase of the transaction lifecycle, commonly used for final condition checks, preparing or supplementing data that must belong to **the same transaction**, and tasks appropriate when the commit can still take place.

After this lesson, you will be able to:

- Identify exactly when a `BEFORE_COMMIT` listener runs relative to `publishEvent(...)`, the end of the business method, and the database commit operation.
- Declare `@TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)`.
- Explain the differences between `BEFORE_COMMIT`, `AFTER_COMMIT`, `AFTER_ROLLBACK`, and `AFTER_COMPLETION`.
- Analyze the impact when the listener throws an exception, the transaction rolls back, or the event is published outside a transaction.
- Write and run a Java 17+ example using Spring Framework, JDBC transactions, and H2, verifying both successful commit and rollback.
- Choose the appropriate processing phase, avoiding non-rollbackable side effects before the database commits.

**Key point:** "Has run `BEFORE_COMMIT`" means **Spring has reached the commit preparation step**, **not that the transaction has committed successfully**.

## 2. `@TransactionalEventListener` and the Four Transaction Phases

Spring supports regular event-listening methods with `@EventListener` and transaction-bound listeners with `@TransactionalEventListener`.

~~~java
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
public void beforeCommit(OrderCreated event) {
    // Invoked before the commit of the transaction active when the event was published.
}
~~~

This is **an illustrative snippet**, not a standalone Java program: `OrderCreated` needs to be defined, the method must reside in a Spring bean, and a compatible active transaction must exist when the event is published.

The `phase` attribute is a value of the `TransactionPhase` enum:

| Phase | Callback timing | Use when |
| --- | --- | --- |
| `BEFORE_COMMIT` | Before the commit operation, while the transaction and related resources are not yet finished | Final validation, supplementing/flushing data in the same transaction |
| `AFTER_COMMIT` | After a successful commit | Reacting to the committed result; note that additional database writes require a suitable new transaction |
| `AFTER_ROLLBACK` | After a rollback | Tracking or reacting to a failed transaction |
| `AFTER_COMPLETION` | After the transaction finishes, commit or rollback | Cleanup or recording the general outcome |

If **`phase` is not specified**, `@TransactionalEventListener` defaults to **`AFTER_COMMIT`**. To execute logic before commit, you must explicitly declare `BEFORE_COMMIT`.

These phases describe **when the callback is invoked**, not an arbitrary order determined by `@Order`. For example, an `AFTER_COMMIT @Order(-100)` listener cannot run before a `BEFORE_COMMIT @Order(100)` listener solely due to having a smaller order value.

## 3. Event Lifecycle When a Transaction Commits

Suppose a service calls `publishEvent(...)` inside an active transaction and Spring uses a `PlatformTransactionManager` managing thread-bound transactions.

~~~text
Transaction starts
       |
       v
Service modifies data via repository/JdbcTemplate
       |
       v
publishEvent(new OrderCreated(...))
       |
       +--> Spring detects @TransactionalEventListener
       |    and registers transaction synchronization
       |
       +--> publishEvent(...) returns
       |
       v
Service finishes method body
       |
       v
Transaction manager begins commit process
       |
       +--> BEFORE_COMMIT listener runs
       |    (can still access transaction resources)
       |
       +--> beforeCompletion callbacks
       |
       +--> Perform actual resource commit
       |
       +--> AFTER_COMMIT if commit succeeded
       |         or AFTER_ROLLBACK if rolled back
       |
       +--> AFTER_COMPLETION
       |
       v
Transaction finishes
~~~

Two timestamps are often confused:

1. **At event publish time:** `publishEvent(event)` typically passes the event to the transactional listener registration mechanism; the body of `BEFORE_COMMIT` is not invoked right here.
2. **When the transaction prepares to commit:** the `BEFORE_COMMIT` callback is invoked by the synchronization mechanism when the transaction manager proceeds to commit, after the business processing inside the transaction has finished.

If there is an enclosing outer transaction—such as a `@Transactional(propagation = REQUIRED)` method joining an existing transaction—the listener binds to **the actual transaction active at event publish time** and is invoked when that transaction proceeds to commit. It does not necessarily run immediately when the inner method returns.

In the thread-bound transaction model, this process relies on `TransactionSynchronizationManager` and the `TransactionSynchronization.beforeCommit(boolean readOnly)` callback. `BEFORE_COMMIT` occurs **before** `beforeCompletion()` and before the actual resource commit operation. Note: interaction ordering with other synchronizations can also be affected by `Ordered` and transaction infrastructure.

### What Does "Before Commit" Mean?

- The transaction is still in the process of finishing; standard JDBC changes using the same transaction/resource can become part of the commit if everything succeeds.
- The listener can throw an exception before commit, causing the commit process to abort and the transaction to roll back.
- After the listener runs, the transaction **can still fail** due to flush errors, constraints, database connectivity, deadlocks, or another rollback decision.
- Therefore, `BEFORE_COMMIT` must not be treated as proof that data has been durably persisted.

## 4. Proper Configuration for `BEFORE_COMMIT`

A basic listener:

~~~java
import org.springframework.core.annotation.Order;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

public class OrderListeners {

    @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
    @Order(-10)
    public void verify(OrderCreated event) {
        // Check conditions before commit.
    }

    @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
    @Order(10)
    public void prepareAudit(OrderCreated event) {
        // Add a record to be committed together if the check succeeds.
    }
}
~~~

This is an **illustrative snippet**: Spring bean declarations, the `OrderCreated` definition, and actual transaction infrastructure are required. `@Order(-10)` has higher priority than `@Order(10)` among listeners of the same phase; smaller numbers are ordered before larger numbers. However, do not design a complex chain of business dependencies relying entirely on order. In addition, if an earlier listener throws an exception, subsequent listeners may not get a chance to run in that commit attempt.

For `BEFORE_COMMIT` to work in the imperative model, you typically need:

- `@TransactionalEventListener` placed on **a Spring bean method** discovered by the event listener mechanism.
- `publishEvent(...)` occurring when an active transaction and synchronization exist; for example, a transaction created by `@Transactional` via a Spring proxy or `TransactionTemplate`.
- A `PlatformTransactionManager` compatible with the resource (JDBC, JPA...) and a consistent transaction manager used for business operations.
- Not losing the transaction context by arbitrarily offloading the event registration step to another thread.

**`@EnableAsync` is not required** just to activate transactional event listeners. `@EnableTransactionManagement` is needed for examples using `@Transactional` through a proxy; in the complete program in section 6, we use `TransactionTemplate`, so transaction proxy configuration is not needed.

## 5. When Should BEFORE_COMMIT Be Used?

Suitable cases usually relate to **the contents of the current transaction**:

1. **Final condition checks:** verifying consistency based on data updated by the service, right before finalizing the commit. This check can cause the transaction to roll back by throwing an appropriate exception.
2. **Supplementing data in the same transaction:** writing an internal audit or an outbox record using the same database and the same transaction manager, so these changes commit together or roll back together.
3. **Flushing/preparing data:** part of the infrastructure can synchronize or flush state before commit. When using an ORM, understand flush modes, synchronization order, and the transaction manager; do not assume every query in a listener sees unflushed state.
4. **Reviewing the validity of a step:** used when the unit of change is inside the transaction and an error must be able to block the commit.

Cases where **before-commit should not be used**:

- Sending emails/SMS or calling external APIs that **cannot be rolled back** under a "send only if the DB commit succeeds" requirement.
- Publishing a message as processed as if the commit were already guaranteed to succeed.
- Performing long-running tasks that block the thread/transaction for too long, increasing connection and lock hold times.
- Using listeners to replace a multi-step business workflow with explicit dependencies: core steps should be expressed transparently in the service.

For example, if an email is sent in `BEFORE_COMMIT` and then the database commit fails, the recipient may still receive an email about a transaction that does not exist. When post-commit side effects are needed, consider `AFTER_COMMIT`; when high durability and retry capability are needed, write a **transactional outbox** record inside the transaction and use a worker/broker to deliver externally afterward.

## 6. Runnable Java 17+ Example: BEFORE_COMMIT with H2 and Rollback

This example intentionally uses **plain Spring Framework** and an in-memory H2 database to have real transactions whose SQL results can be verified. There are two account creation events:

- **Mai:** the validation listener succeeds, the audit listener inserts into the `audit_log` table; both tables are committed.
- **Lan:** the validation listener throws `IllegalStateException` before commit; the transaction rolls back, so Lan's account does not exist in the database.

By using `TransactionTemplate`, the example does not depend on calling `@Transactional` methods through a proxy or web framework.

### 6.1. Project Structure

~~~text
before-commit-demo/
├── build.gradle
└── src/
    └── main/
        └── java/
            └── example/
                └── BeforeCommitDemo.java
~~~

Contents of `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.15'
    implementation 'org.springframework:spring-jdbc:6.2.15'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

application {
    mainClass = 'example.BeforeCommitDemo'
}
~~~

`spring-jdbc` pulls in the required transaction infrastructure (`spring-tx`); H2 provides the JDBC database for the example. Both Spring dependencies use **the same version** to avoid API mismatch. Real-world applications using Spring Boot should usually let Boot manage compatible versions.

### 6.2. Complete Source Code

Create `src/main/java/example/BeforeCommitDemo.java`:

~~~java
package example;

import javax.sql.DataSource;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

public class BeforeCommitDemo {

    public record SignupRequested(String username, boolean reject) {}

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        public DataSource dataSource() {
            return new DriverManagerDataSource(
                    "jdbc:h2:mem:before_commit_demo;DB_CLOSE_DELAY=-1",
                    "sa", "");
        }

        @Bean
        public PlatformTransactionManager transactionManager(DataSource dataSource) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        public TransactionTemplate transactionTemplate(
                PlatformTransactionManager transactionManager) {
            return new TransactionTemplate(transactionManager);
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        public BeforeCommitHandlers beforeCommitHandlers(JdbcTemplate jdbc) {
            return new BeforeCommitHandlers(jdbc);
        }
    }

    public static class BeforeCommitHandlers {

        private final JdbcTemplate jdbc;

        public BeforeCommitHandlers(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
        @Order(-10)
        public void validate(SignupRequested event) {
            System.out.println("BEFORE_COMMIT validate " + event.username());

            if (event.reject()) {
                throw new IllegalStateException("blocked " + event.username());
            }
        }

        @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
        @Order(10)
        public void audit(SignupRequested event) {
            jdbc.update(
                    "INSERT INTO audit_log (username) VALUES (?)",
                    event.username());
            System.out.println("BEFORE_COMMIT audit " + event.username());
        }
    }

    private static void register(
            TransactionTemplate transaction,
            JdbcTemplate jdbc,
            ApplicationEventPublisher publisher,
            String username,
            boolean reject) {

        transaction.executeWithoutResult(status -> {
            jdbc.update(
                    "INSERT INTO user_accounts (username) VALUES (?)",
                    username);

            publisher.publishEvent(new SignupRequested(username, reject));
            System.out.println("published " + username);
        });
    }

    private static int count(JdbcTemplate jdbc, String table) {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM " + table,
                Integer.class);
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            TransactionTemplate transaction =
                    context.getBean(TransactionTemplate.class);

            jdbc.execute(
                    "CREATE TABLE user_accounts (username VARCHAR(80) PRIMARY KEY)");
            jdbc.execute(
                    "CREATE TABLE audit_log (username VARCHAR(80) PRIMARY KEY)");

            System.out.println(
                    "initial users=" + count(jdbc, "user_accounts")
                    + ", audits=" + count(jdbc, "audit_log"));

            register(transaction, jdbc, context, "Mai", false);

            System.out.println(
                    "after Mai users=" + count(jdbc, "user_accounts")
                    + ", audits=" + count(jdbc, "audit_log"));

            try {
                register(transaction, jdbc, context, "Lan", true);
            } catch (IllegalStateException ex) {
                System.out.println("rollback Lan: " + ex.getMessage());
            }

            System.out.println(
                    "after Lan users=" + count(jdbc, "user_accounts")
                    + ", audits=" + count(jdbc, "audit_log"));
        }
    }
}
~~~

**Configuration explanation:**

- `DriverManagerDataSource` creates connections to H2; `DataSourceTransactionManager` manages JDBC transactions on that `DataSource`.
- `JdbcTemplate` participates in the current transaction through Spring's connection management mechanism. Therefore, updates to `user_accounts` and `audit_log` can share a single transaction.
- `TransactionTemplate.executeWithoutResult(...)` opens a transaction and commits after the business callback returns. If the commit step throws an error, the transaction manager handles rollback when possible.
- `publishEvent(...)` registers the two `BEFORE_COMMIT` listeners. At publish time, `validate` and `audit` do not print anything yet because they wait for the transaction to reach the commit stage.
- `@Order(-10)` prioritizes `validate` to run before `audit`; if validation fails, the subsequent callback is not executed in the normal commit flow.
- The `reject` flag is only to simulate a controlled failure case; real production code requires appropriate business conditions.

### 6.3. Running and Expected Stdout

In the `before-commit-demo` directory, with JDK 17+ and Gradle installed:

~~~bash
gradle -q run
~~~

Or use the provided Gradle Wrapper: `./gradlew -q run` (Linux/macOS) or `gradlew.bat -q run` (Windows).

Lines printed by the program:

~~~text
initial users=0, audits=0
published Mai
BEFORE_COMMIT validate Mai
BEFORE_COMMIT audit Mai
after Mai users=1, audits=1
published Lan
BEFORE_COMMIT validate Lan
rollback Lan: blocked Lan
after Lan users=1, audits=1
~~~

**Result analysis:**

1. Initially there are 0 accounts and 0 audit records.
2. `register(..., "Mai", false)` inserts the account and publishes the event inside the transaction. The `published Mai` line appears **before** the two listener lines.
3. When `TransactionTemplate` prepares to commit, `BEFORE_COMMIT validate Mai` runs; then `audit` inserts the audit record using the same JDBC transaction.
4. Commit succeeds: post-transaction queries see 1 account and 1 audit.
5. For Lan, the `validate` listener throws `IllegalStateException("blocked Lan")` at the before-commit stage. The transaction manager rolls back, so inserting Lan's account is also canceled. `audit` does not run for Lan.
6. The final query still shows `users=1, audits=1`: Mai's transaction committed earlier and is unaffected by Lan's rollback.

Thus, a validation condition can reject the commit, while internal audit writes are grouped into the same transaction. This example uses real transactions; merely calling three methods sequentially in a `main` method cannot accurately demonstrate the effect of `BEFORE_COMMIT`.

## 7. Errors in BEFORE_COMMIT and Rollback

### 7.1. Runtime Exceptions from a Listener

`BEFORE_COMMIT` corresponds to the `TransactionSynchronization.beforeCommit(...)` callback. Per Spring's contract, a `RuntimeException` thrown here is propagated to the commit caller and **causes the transaction to roll back** during normal processing. The example in section 6 shows the exception from `validate` propagating out of `TransactionTemplate`, while H2 does not save Lan's row.

Points to distinguish:

- An error in the business method **before** finishing the transaction can cause Spring to decide to roll back **before reaching the `BEFORE_COMMIT` stage**; in that case, the `BEFORE_COMMIT` listener is not invoked.
- An error thrown **inside** `BEFORE_COMMIT` can cause the transaction to roll back.
- Even if **all** `BEFORE_COMMIT` listeners have run successfully, the resource commit step can still fail. Success in the callback does not guarantee final success.
- If you catch and swallow an exception inside the listener, it will not automatically force a rollback; when you need to abort the commit, throw an appropriate error or mark rollback-only via the transaction mechanism.

When you need a policy of "do not commit if the final condition is invalid," use a clearly meaningful exception (usually a runtime exception) and ensure the error is not swallowed by another layer. Do not use arbitrary checked exceptions or expect every exception to have the same rollback rules; callback semantics differ from `@Transactional` interceptor rules for exceptions escaping a service method.

### 7.2. When the Transaction Is Already Rollback-Only

If the transaction has already been marked rollback-only or the execution flow actively rolls back, there is no normal commit operation to invoke `BEFORE_COMMIT`. In that case, use `AFTER_ROLLBACK` to handle post-rollback reactions; do not expect `BEFORE_COMMIT` to always run merely because an event was published.

### 7.3. When the Database Commit Fails After the Callback

Suppose `BEFORE_COMMIT` calls an external system successfully, but the JDBC/JPA commit step afterward encounters an error. You may have created an irreversible side effect while the database data was not committed. This is why it is necessary to classify tasks into "internal to the same transaction" and "external systems" before choosing a phase.

## 8. Publishing Events Without a Transaction

By default, `@TransactionalEventListener` has `fallbackExecution = false`. If `publishEvent(...)` happens outside a Spring-managed transaction, the listener **is skipped** because Spring cannot satisfy the BEFORE_COMMIT timing.

~~~java
publisher.publishEvent(new SignupRequested("An", false));
// Outside a transaction: BEFORE_COMMIT listener does not run by default.
~~~

This is an illustrative snippet with `publisher` and `SignupRequested` already defined. It does not insert data, does not create a transaction, and does not run the listener in the program from section 6.

You can write:

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.BEFORE_COMMIT,
    fallbackExecution = true)
public void onEvent(SignupRequested event) {
    // Runs immediately when there is no transaction to bind the callback to.
}
~~~

However, with `fallbackExecution = true`, the **no-transaction** case is only fallback execution, **not executing a before-commit callback** because there is no pending commit. Enable this option only when business logic permits both semantics. For checks that must strictly occur inside a transaction, keep the default `false` to avoid misunderstanding consistency.

## 9. Timing with @Transactional, TransactionTemplate, and Propagation

In real applications, events are often published from a service:

~~~java
@Service
public class RegistrationService {
    private final UserRepository repository;
    private final ApplicationEventPublisher publisher;

    public RegistrationService(UserRepository repository,
                               ApplicationEventPublisher publisher) {
        this.repository = repository;
        this.publisher = publisher;
    }

    @Transactional
    public void register(String username) {
        repository.insert(username);
        publisher.publishEvent(new SignupRequested(username, false));
    }
}
~~~

This is an **illustrative snippet**, not part of the complete program in section 6: `UserRepository` must be defined, Spring imports added, `@EnableTransactionManagement` or equivalent transaction infrastructure configured, and the method invoked through a Spring proxy.

When calling `RegistrationService.register(...)` through the `@Transactional` proxy, the transaction interceptor starts/coordinates the transaction. The event registers the callback in that transaction, and `BEFORE_COMMIT` is invoked when the transaction actually proceeds to commit.

Notes on propagation:

| Case | Transaction the event binds to |
| --- | --- |
| `@Transactional(REQUIRED)` creates a new transaction | The newly created transaction |
| `REQUIRED` joins an existing transaction | The existing transaction; the listener waits for the outer transaction's commit |
| `REQUIRES_NEW` creates an independent transaction | The new transaction is suspended/resumed separately; the listener binds to the new transaction |
| `TransactionTemplate` creates a transaction | The transaction managed by the template and `PlatformTransactionManager` |
| Calling a service method from within the same instance (self-invocation) with `@Transactional` proxy | The call may bypass the interceptor; if no other transaction exists, the listener is skipped by default |
| `@Async` publishes an event on another thread | Only binds to an actually active transaction in the event-publishing thread, if any |

Do not infer "the method has `@Transactional`" means a transaction is definitely active; the transaction manager, proxy invocation, propagation, transaction system type, and actual thread all matter.

## 10. BEFORE_COMMIT, Listener Ordering, and Async

### 10.1. `@Order` Helps Order Callbacks in the Same Phase

If two `BEFORE_COMMIT` listeners have `@Order(-10)` and `@Order(10)`, Spring can order the callbacks according to synchronization priority. Smaller numbers take precedence; the example in section 6 leverages this to validate first and then write the audit.

However, order is not a tool for designing a long business chain with multiple resources and complex conditional dependencies. A core "A succeeds before B can run" step should be expressed directly in the service when strict consistency is required.

### 10.2. Do Not Use Async Expecting to Preserve the Original Transaction

Spring manages imperative transactions primarily via **thread-bound context**. If a callback is offloaded to another executor/thread, the code can no longer see the transaction the publisher is using. With `@TransactionalEventListener`, Spring handles synchronization registration on the transactional thread; the multicaster mechanism does not arbitrarily move transactional listeners to a thread pool.

Putting `@Async` on a transactional listener method is also a choice with different semantics: the delegated code can run asynchronously, no longer able to abort the original transaction's commit via an exception thrown later. Therefore, when **the goal is to validate and decide commit or rollback**, keep `BEFORE_COMMIT` synchronous and avoid `@Async` at that step.

### 10.3. Reactive Transactions Have a Different Mechanism

Since Spring Framework 6.1, transactional event listeners also support reactive transactions, but the reactive transaction context is stored in the **Reactor Context**, not equivalent to `PlatformTransactionManager`'s ThreadLocal. With `ReactiveTransactionManager`, the appropriate transaction context must be passed via the event source using the `TransactionalEventPublisher` API. The JDBC/`TransactionTemplate` example in this lesson is an **imperative transaction**; do not use it to extrapolate directly to reactive transactions.

### 10.4. Events Published Inside Another BEFORE_COMMIT Listener

Do not assume that an event published **while** a `BEFORE_COMMIT` callback is already running will register another `BEFORE_COMMIT` callback in time to execute in that same callback cycle. Transaction synchronizations are typically already snapshotted/ordered for the current invocation pass; registering an additional callback too late may not be processed in the expected pass. If you have a multi-step task chain, coordinate it before commit time or use an explicit listener instead of creating a new event chain inside the callback.

## 11. Reading/Writing Data in BEFORE_COMMIT: Practical Limitations

A `BEFORE_COMMIT` listener has access to transaction resources, but that does not mean all changes will always behave identically:

- **JDBC with a single DataSource/transaction manager:** operations via `JdbcTemplate` using the same transactional connection normally participate in the original transaction, as shown in section 6.
- **JPA/Hibernate:** has a persistence context, dirty checking, and flush timings. If a listener reads via direct SQL before entities are flushed, results may differ from the object state in the persistence context. Verify with the specific ORM and transaction manager rather than assuming automatic flushing happens before an arbitrary listener.
- **Read-only transactions:** the `beforeCommit(boolean readOnly)` callback also passes the read-only flag; do not abuse the listener to write data if the transaction is designed as read-only. Whether the database blocks writes depends on configuration.
- **Long transactions:** a listener running before commit can keep locks/connections held longer; slow network operations or blind retries are generally inappropriate here.
- **Sensitive data and side effects:** do not stuff passwords/tokens into events; pass only necessary, minimal, clearly semantic data and avoid leaking information in logs.
- **Idempotency:** when a transaction/service is retried, events may be published multiple times. Listeners that write records should consider unique keys or an idempotent mechanism appropriate for the business logic.

Although `BEFORE_COMMIT` can write an outbox row in the same transaction, **the actual sending of the message to a broker** should be handled by an independent task processing committed outbox rows; publishing to an external system before commit does not provide atomicity between the two systems.

## 12. Common Misconceptions

| Misconception | Correct Understanding |
| --- | --- |
| `BEFORE_COMMIT` means the database has saved successfully | Not yet. The callback occurs before commit and the commit can still fail |
| `publishEvent` invokes the `BEFORE_COMMIT` listener immediately | Normally publish only registers synchronization; the listener runs when the transaction proceeds to commit |
| Publishing an event always makes `BEFORE_COMMIT` run | Requires a matching transaction/synchronization; without a transaction it is skipped by default |
| A rolled-back transaction also runs `BEFORE_COMMIT` | If rollback was already decided before the commit process, this listener does not run |
| Exceptions in the listener do not affect the transaction | A runtime exception in `beforeCommit` can propagate out and cause a rollback |
| `@TransactionalEventListener` defaults to `BEFORE_COMMIT` | It defaults to `AFTER_COMMIT`; `phase` must be set explicitly |
| `@Order(-10)` higher than `@Order(10)` means the transaction commits earlier | Order only sorts callbacks within the same phase; it does not change phases or commit timing |
| Sending email in `BEFORE_COMMIT` is safe because commit is about to happen | The database can still roll back; email cannot roll back with the database |
| `fallbackExecution=true` creates a transaction when none exists | No. The fallback listener runs without any actual commit |
| Adding `@Async` still lets exceptions abort the original transaction | Async work runs in a different context; it cannot be relied on to intervene in the publisher's commit |

## 13. Guide to Choosing a Phase by Scenario

| Requirement | Recommendation | Reason |
| --- | --- | --- |
| Final condition check; roll back if invalid | Synchronous `BEFORE_COMMIT` or check directly in the service | Has the opportunity to block the commit before completion |
| Need to write audit/outbox in the same JDBC transaction | Write directly in the service or in `BEFORE_COMMIT` with the same resource/transaction manager | Succeeds with commit; fails with rollback |
| Only send notification if the transaction committed | `AFTER_COMMIT` for suitable tasks, or outbox when delivery must be guaranteed | Avoids sending notifications before the commit outcome |
| Handle consequences after rollback | `AFTER_ROLLBACK` | Reacts properly to an unsuccessful transaction |
| Reclaim resources/record status when the transaction ends regardless of outcome | `AFTER_COMPLETION` | Covers both commit and rollback |
| Require messages not to be lost even if the app crashes right after commit | Transactional outbox and worker/message broker | Internal Spring events are not a durable queue |

Not every "prepare before commit" operation needs a listener. If a check is **a core condition to accept a request**, writing it directly in the service is usually easier to maintain, test, and observe errors. `BEFORE_COMMIT` is useful when you want to decouple a transaction-bound concern from the event-publishing code, with well-understood execution semantics.

## 14. Self-Check Knowledge

**Question 1.** A service publishes an event inside `TransactionTemplate`, then prints `"service done"` and finishes the lambda. A `BEFORE_COMMIT` listener prints `"listener"`. Which line appears first?

**Answer:** `"service done"` first; the listener waits for the transaction manager to proceed to commit, after the business lambda returns.

**Question 2.** A `BEFORE_COMMIT` listener finished sending an email, but the JDBC commit fails. Can the email be implicitly canceled along with the rollback?

**Answer:** No. Email is an external system side effect and does not roll back with the JDBC transaction.

**Question 3.** A `BEFORE_COMMIT` listener throws `IllegalStateException`. What is the outcome in a normal Spring-managed JDBC transaction?

**Answer:** The exception propagates out of the callback, the transaction manager rolls back if possible, and the commit caller receives the error. Do not catch and swallow the error if you intend to prevent the commit.

**Question 4.** An event is published outside a transaction; the `@TransactionalEventListener(BEFORE_COMMIT)` listener has no `fallbackExecution`. Does it run?

**Answer:** No, by default without a transaction the listener is skipped.

**Question 5.** Two handlers in the same phase have orders `20` and `-5`, respectively. Which one has higher priority?

**Answer:** `-5`, because smaller numbers have higher priority in the ordering mechanism.

**Question 6.** Does a `BEFORE_COMMIT` listener of a `REQUIRED` method joining an existing transaction run when the child method returns or when the enclosing transaction commits?

**Answer:** When the actual enclosing transaction proceeds to the commit process.

## 15. References

- Spring Framework Reference 6.2 — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
- Javadoc `TransactionPhase` — meaning of `BEFORE_COMMIT` and other phases: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/transaction/event/TransactionPhase.html
- Javadoc `TransactionalEventListener` — `phase`, `fallbackExecution`, transaction context: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html
- Javadoc `TransactionSynchronization` — `beforeCommit(...)`, exceptions and rollback: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html
- Spring Framework Reference 6.2 — Declarative transaction management: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html
- Spring Framework Javadoc `TransactionTemplate`: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html
- Spring Framework issue #35081 — registering an additional `BEFORE_COMMIT` event inside a `BEFORE_COMMIT` callback itself: https://github.com/spring-projects/spring-framework/issues/35081
