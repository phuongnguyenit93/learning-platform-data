# Testing @TransactionalEventListener in Spring Framework

## 1. Goals and Problems to Solve

`@TransactionalEventListener` lets Spring execute a listener according to a **transaction phase** rather than necessarily running immediately when `publishEvent(...)` is called. For business workflows such as ordering, payments, status updates, or audit logging, this distinction decides whether a task executes **only after commit**, **after rollback**, or **before commit**.

A test containing only `verify(eventPublisher).publishEvent(...)` cannot prove the listener executed in the right phase. A test calling the listener method directly also cannot prove Spring registered transaction synchronization. To test properly, set up a **real Spring context, transaction manager, event publisher, and transaction resources**, then explicitly drive commit/rollback.

After this lesson, you will be able to:

- Distinguish a regular `@EventListener` from `@TransactionalEventListener`.
- Identify the `BEFORE_COMMIT`, `AFTER_COMMIT`, `AFTER_ROLLBACK`, and `AFTER_COMPLETION` phases.
- Write JUnit 5 tests for commit, exception-induced rollback, rollback-only, outside-transaction events, and failures before publishing.
- Verify both callbacks and database data after the transaction ends.
- Understand `fallbackExecution` and why fallback cannot be used as proof of commit.
- Avoid the `@Transactional` test-method trap that rolls back by default at the end of a test.
- Correctly interpret exceptions, async behavior, propagation, and completed transactions.
- Separate imperative JDBC tests from reactive transaction tests to avoid false PASS results.

The main section uses **Java 17+, Spring Framework 6.2.x, H2 JDBC, and TransactionTemplate**. Spring Boot is not required. When applied to a Boot application, the phase principles remain identical.

## 2. Under the Hood: Publishing Does Not Mean Immediate Handling

An event is typically emitted via `ApplicationEventPublisher`:

~~~java
publisher.publishEvent(new OrderCreated("order-101"));
~~~

It can be a small Java record:

~~~java
public record OrderCreated(String orderId) {}
~~~

And a listening bean:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderCreated(OrderCreated event) {
    notificationService.send(event.orderId());
}
~~~

These three snippets are **illustrative**, not a standalone program. They require `publisher` and `notificationService` beans and corresponding imports/classes. The full test suite appears in section 6.

When an active imperative transaction is present:

1. Business code starts a transaction via `PlatformTransactionManager`.
2. Code publishes an event inside the transaction.
3. Spring recognizes `@TransactionalEventListener` and registers a callback with the active transaction synchronization.
4. Once business logic finishes, the transaction manager begins commit or rollback.
5. The listener is triggered only in its declared phase.

Therefore, for an `AFTER_COMMIT` listener, `publishEvent(...)` returning normally **does not prove** the callback ran. Sometimes the callback will never run at all because the transaction rolls back.

With a regular synchronous `@EventListener`, the listener normally runs immediately on the publisher's call stack. Confusing the two annotations in test code yields completely different outcomes. Check class imports: `org.springframework.context.event.EventListener` versus `org.springframework.transaction.event.TransactionalEventListener`.

## 3. Contract of the Four TransactionPhases

| Phase | Execution Time | Normal Commit | Normal Rollback |
| --- | --- | --- | --- |
| `BEFORE_COMMIT` | Before transaction manager commits resources | Yes | No |
| `AFTER_COMMIT` | After successful commit | Yes | No |
| `AFTER_ROLLBACK` | After rollback | No | Yes |
| `AFTER_COMPLETION` | When transaction completes, commit or rollback | Yes | Yes |

The **default** for `@TransactionalEventListener` is `AFTER_COMMIT`.

Commit model:

~~~text
TransactionTemplate.execute(...)
       |
       +--> INSERT/UPDATE via JdbcTemplate
       +--> publishEvent(OrderCreated)
       |     |
       |     +--> register callbacks by phase
       |
       +--> business callback returns
       |
       +--> BEFORE_COMMIT
       +--> COMMIT data
       +--> AFTER_COMMIT
       +--> AFTER_COMPLETION
       |
       +--> TransactionTemplate returns
~~~

Rollback model:

~~~text
TransactionTemplate.execute(...)
       |
       +--> INSERT/UPDATE
       +--> publishEvent(OrderCreated)
       +--> throw RuntimeException
       |
       +--> ROLLBACK data
       +--> AFTER_ROLLBACK
       +--> AFTER_COMPLETION
       |
       +--> propagate exception to caller
~~~

Keep in mind:

- Observing `BEFORE_COMMIT` **does not prove commit succeeded**. A database error can still occur during commit after the callback.
- `AFTER_COMPLETION` runs in both outcomes. It is not synonymous with `AFTER_COMMIT`.
- In Spring's implementation, `@TransactionalEventListener`'s `AFTER_COMMIT` callback ties to the committed completion stage. Do not bind to an uncontracted order among multiple synchronization callbacks.
- If no transaction exists, the listener is not called by default.
- If an event was not published before an error, the transaction can still roll back, yet **there is no callback for an event that never existed**.

## 4. Test Matrix and Evidence to Collect

A good test proves **phase, transaction outcome, and data**. Do not check logs alone.

| Scenario | How Transaction Ends | Expected Default Listener | Database |
| --- | --- | --- | --- |
| Commit A | Callback succeeds, commits | `before:A`, `commit:A`, `complete:A` | A exists |
| Rollback B | Exception thrown after publish | `rollback:B`, `complete:B` | B does not exist |
| Rollback-only C | `status.setRollbackOnly()` | `rollback:C`, `complete:C` | C does not exist |
| Outside transaction N | Direct publish | No default callbacks | Unchanged |
| Error before publish D | Exception thrown before calling publisher | No callbacks at all | D does not exist |

To test fallback, add a separate bean with `@TransactionalEventListener(fallbackExecution = true)`. It still runs after commit when a transaction exists, yet is allowed to run immediately when no transaction exists. Thus test N must observe fallback, and **must not call that a commit**.

"Oracles" should be independent:

1. **Collector:** a callback trace list showing which event reached which phase.
2. **Database:** query outside the transaction after completion to confirm commit or rollback.
3. **Exception/result:** verify the expected error or return state.
4. **Timing:** place assertions after the commit/rollback boundary, not prematurely right after `publishEvent`.

A transaction can roll back without throwing an exception if code explicitly marks rollback-only; therefore, never treat "no exception thrown" as proof of commit.

## 5. Setting Up a Java 17+ and Gradle Project

Project structure:

~~~text
tx-listener-test/
├── settings.gradle
├── build.gradle
└── src/
    └── test/
        └── java/
            └── example/
                └── TransactionalEventListenerTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'tx-listener-test'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
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
    testImplementation 'org.springframework:spring-context:6.2.15'
    testImplementation 'org.springframework:spring-jdbc:6.2.15'
    testImplementation 'com.h2database:h2:2.3.232'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

test {
    useJUnitPlatform()
}
~~~

Explanation:

- `spring-context`: context, publisher, and listener adapter.
- `spring-jdbc`: `JdbcTemplate`, `DataSourceTransactionManager`, and JDBC transaction support; `spring-tx` is resolved transitively via the dependency graph.
- H2 JDBC: a real in-memory database to verify commit/rollback; not Mockito.
- JUnit Jupiter: test lifecycle, assertions, and JUnit execution platform.
- Java toolchain: selects JDK 17 to match Spring 6.2's baseline.

In a Spring Boot project, let the Spring Boot BOM manage Spring/H2/JUnit versions. Pinning versions in the example helps learners reproduce the configuration; it does not imply they are the latest versions at all times.

## 6. Complete Test Source Code

Save **all** of the following content into `src/test/java/example/TransactionalEventListenerTest.java`:

~~~java
package example;

import java.util.List;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.CopyOnWriteArrayList;
import javax.sql.DataSource;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class TransactionalEventListenerTest {

    public record OrderCreated(String id) {}

    public static final class PhaseRecorder {
        private final CopyOnWriteArrayList<String> events =
                new CopyOnWriteArrayList<>();

        @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
        public void before(OrderCreated event) {
            events.add("before:" + event.id());
        }

        // No phase specified => AFTER_COMMIT.
        @TransactionalEventListener
        public void committed(OrderCreated event) {
            events.add("commit:" + event.id());
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
        public void rolledBack(OrderCreated event) {
            events.add("rollback:" + event.id());
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)
        public void completed(OrderCreated event) {
            events.add("complete:" + event.id());
        }

        public List<String> snapshot() {
            return List.copyOf(events);
        }
    }

    // Separate fallback from main collector for easy comparison.
    public static final class FallbackRecorder {
        private final CopyOnWriteArrayList<String> events =
                new CopyOnWriteArrayList<>();

        @TransactionalEventListener(fallbackExecution = true)
        public void accept(OrderCreated event) {
            events.add("fallback:" + event.id());
        }

        public List<String> snapshot() {
            return List.copyOf(events);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class Config {

        @Bean
        public DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");

            // Each test gets its own DB to avoid test order dependence.
            String dbName = "txevent_"
                    + UUID.randomUUID().toString().replace("-", "");
            ds.setUrl("jdbc:h2:mem:" + dbName + ";DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        public PlatformTransactionManager transactionManager(
                DataSource dataSource) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        public TransactionTemplate transactionTemplate(
                PlatformTransactionManager manager) {
            return new TransactionTemplate(manager);
        }

        @Bean
        public PhaseRecorder phaseRecorder() {
            return new PhaseRecorder();
        }

        @Bean
        public FallbackRecorder fallbackRecorder() {
            return new FallbackRecorder();
        }
    }

    private AnnotationConfigApplicationContext context;
    private ApplicationEventPublisher publisher;
    private JdbcTemplate jdbc;
    private TransactionTemplate tx;
    private PhaseRecorder phases;
    private FallbackRecorder fallback;

    @BeforeEach
    void setUp() {
        context = new AnnotationConfigApplicationContext(Config.class);
        publisher = context;
        jdbc = context.getBean(JdbcTemplate.class);
        tx = context.getBean(TransactionTemplate.class);
        phases = context.getBean(PhaseRecorder.class);
        fallback = context.getBean(FallbackRecorder.class);

        jdbc.execute(
                "CREATE TABLE tx_items (id VARCHAR(64) PRIMARY KEY)");
    }

    @AfterEach
    void tearDown() {
        if (context != null) {
            context.close();
        }
    }

    private int countRows(String id) {
        Integer result = jdbc.queryForObject(
                "SELECT COUNT(*) FROM tx_items WHERE id = ?",
                Integer.class,
                id);
        return result.intValue();
    }

    private void assertPhases(String... expected) {
        List<String> actual = phases.snapshot();
        assertEquals(expected.length, actual.size());
        assertEquals(Set.of(expected), Set.copyOf(actual));
    }

    @Test
    void commitCallsCommitPhasesAndPersistsData() {
        tx.executeWithoutResult(status -> {
            jdbc.update("INSERT INTO tx_items(id) VALUES (?)", "A");
            publisher.publishEvent(new OrderCreated("A"));

            // Callback has not run yet because transaction has not committed.
            assertTrue(phases.snapshot().isEmpty());
            assertTrue(fallback.snapshot().isEmpty());
        });

        assertPhases("before:A", "commit:A", "complete:A");
        assertEquals(List.of("fallback:A"), fallback.snapshot());
        assertEquals(1, countRows("A"));
    }

    @Test
    void exceptionAfterPublishRollsBack() {
        IllegalStateException error = assertThrows(
                IllegalStateException.class,
                () -> tx.executeWithoutResult(status -> {
                    jdbc.update(
                            "INSERT INTO tx_items(id) VALUES (?)", "B");
                    publisher.publishEvent(new OrderCreated("B"));
                    throw new IllegalStateException("rollback requested");
                }));

        assertEquals("rollback requested", error.getMessage());
        assertPhases("rollback:B", "complete:B");
        assertTrue(fallback.snapshot().isEmpty());
        assertEquals(0, countRows("B"));
    }

    @Test
    void rollbackOnlyAlsoTriggersRollbackPhase() {
        tx.executeWithoutResult(status -> {
            jdbc.update("INSERT INTO tx_items(id) VALUES (?)", "C");
            publisher.publishEvent(new OrderCreated("C"));
            status.setRollbackOnly();
        });

        assertPhases("rollback:C", "complete:C");
        assertTrue(fallback.snapshot().isEmpty());
        assertEquals(0, countRows("C"));
    }

    @Test
    void outsideTransactionOnlyFallbackRuns() {
        publisher.publishEvent(new OrderCreated("N"));

        assertTrue(phases.snapshot().isEmpty());
        assertEquals(List.of("fallback:N"), fallback.snapshot());
        assertEquals(0, countRows("N"));
    }

    @Test
    void errorBeforePublishHasNoEventCallbacks() {
        assertThrows(IllegalArgumentException.class,
                () -> tx.executeWithoutResult(status -> {
                    jdbc.update(
                            "INSERT INTO tx_items(id) VALUES (?)", "D");
                    throw new IllegalArgumentException(
                            "validation failed before event");
                }));

        assertTrue(phases.snapshot().isEmpty());
        assertTrue(fallback.snapshot().isEmpty());
        assertEquals(0, countRows("D"));
    }
}
~~~

This is a **complete JUnit 5 file**, not pseudo-code. `@BeforeEach` builds the Spring context and database table; `@AfterEach` closes the context. Each test method has an explicit transaction boundary. There is no outer `@Transactional` wrapping the test method, so `TransactionTemplate` opens/closes the transaction right before the assertions.

### Why Use @EnableTransactionManagement?

In a plain Spring Framework context, `@EnableTransactionManagement` registers transaction annotation infrastructure. Transactional listeners are detected via the event listener adapter mechanism, while `DataSourceTransactionManager` provides the real transaction for registering callbacks. Tests should not rely on beans Spring Boot might auto-create when explicitly constructing a minimal `AnnotationConfigApplicationContext`.

### Why Share One DataSource Between JdbcTemplate and the Manager?

`JdbcTemplate` must run SQL using the **connection participating in the managed transaction**. Both it and `DataSourceTransactionManager` receive the same `DataSource` bean. If a test writes data to a different datasource than the one managed by the transaction manager, the database may auto-commit even when the test believes it rolled back.

### Why Use a UUID-Named Database?

Each test gets its own in-memory H2 database, preventing leftover data when tests run in parallel or in varying order. `DB_CLOSE_DELAY=-1` keeps the database alive across fresh connections in the same JVM. This is an easy-to-follow isolation technique, though not the only optimal choice for large test suites.

### Why Use CopyOnWriteArrayList?

This collection keeps the collector safe when another thread reads/writes; `snapshot()` creates a separate list so assertions never iterate while the collection mutates. However, **thread safety does not turn an async test into one with completion synchronization**. The current test suite intentionally uses the default synchronous multicaster and deterministic transaction boundaries.

### Why Compare Set and Size?

`assertPhases` confirms the right number of callbacks and right labels without coupling to an incidental order among same-stage transaction synchronizations. If duplicate callbacks occur, comparing size and the label set catches them. To test `@Order`, write a dedicated ordering test with an explicit contract.

## 7. Running Tests and Expected Outcomes

In the project directory, with JDK 17+ and Gradle:

~~~bash
gradle test
~~~

If using the Gradle Wrapper, run `./gradlew test` on Linux/macOS or `gradlew.bat test` on Windows. Gradle's JUnit report is typically located at `build/reports/tests/test/index.html`.

There are **5 `@Test` methods** in the file above. Once dependencies resolve and the context/transaction manager operate properly, all five tests will pass.

Outcome comparison table:

| Test | Transaction Phase Labels | Fallback | Rows in H2 |
| --- | --- | --- | --- |
| Commit A | `before:A`, `commit:A`, `complete:A` | `fallback:A` | A = 1 |
| Exception rollback B | `rollback:B`, `complete:B` | None | B = 0 |
| Rollback-only C | `rollback:C`, `complete:C` | None | C = 0 |
| Outside transaction N | None | `fallback:N` | N = 0 |
| Error before publish D | None | None | D = 0 |

These are **expectations by code and contract**, not a test log captured in the current environment. The test file does not intentionally print labels to stdout; they are checked via JUnit assertions. If the build fails, inspect the actual compile/dependency/runtime error rather than modifying assertions to make tests "green."

## 8. Deep Dive into the Commit Case

In the test:

~~~java
tx.executeWithoutResult(status -> {
    jdbc.update("INSERT INTO tx_items(id) VALUES (?)", "A");
    publisher.publishEvent(new OrderCreated("A"));
    assertTrue(phases.snapshot().isEmpty());
});
~~~

At the moment of `publishEvent`, Spring knows about the event and a transaction exists, yet **phase callbacks have not run yet**. Once the callback inside the template returns:

1. The transaction manager starts the commit process.
2. `BEFORE_COMMIT` listeners execute.
3. The database commits the insert operation.
4. `AFTER_COMMIT` and `AFTER_COMPLETION` listeners are invoked for the success outcome.
5. `TransactionTemplate` returns to the test.
6. The test asserts the labels and `COUNT(*)`.

Therefore, `assertTrue(phases.snapshot().isEmpty())` **inside** the callback is intentional: it checks that listeners are not called prematurely. Assertions for the three labels and `A = 1` are placed **outside** the callback to avoid timing errors.

A `@TransactionalEventListener(fallbackExecution=true)` listener still binds to the transaction when one is active. It **does not run immediately** merely because fallback is enabled; that attribute applies only when no transaction exists. Thus in case A, `fallback:A` appears after commit according to the default phase.

**Exercise caution:** if a `BEFORE_COMMIT` callback fails or the database commit fails, `BEFORE_COMMIT` may have run while `AFTER_COMMIT` never takes place. That is why the DB assertion is a vital part of the test.

## 9. Deep Dive into Exception-Induced Rollback

In test B:

~~~java
assertThrows(IllegalStateException.class,
    () -> tx.executeWithoutResult(status -> {
        jdbc.update("INSERT INTO tx_items(id) VALUES (?)", "B");
        publisher.publishEvent(new OrderCreated("B"));
        throw new IllegalStateException("rollback requested");
    }));
~~~

The transaction manager rolls back after the business callback throws an exception. Because the event was already published, the corresponding synchronization exists. Therefore, the test expects `AFTER_ROLLBACK` and `AFTER_COMPLETION`, and must not see `AFTER_COMMIT`.

Three things must be proven together:

- The exception has the expected type and message, not some unrelated setup error.
- The collector contains exactly `rollback:B` and `complete:B`, and does not contain `commit:B`.
- After the transaction, the database does not contain row B.

If an exception occurs **before** `publishEvent(...)`, the event does not exist yet, so rollback listeners cannot be expected to receive event B. Test D in the file cleanly isolates this case: the database rolls back, while the collector stays empty.

Merely mocking a `RuntimeException` in a service without a real transaction manager is insufficient to prove event phases work.

## 10. Rollback-Only: Rolling Back Without an Exception

In test C:

~~~java
tx.executeWithoutResult(status -> {
    jdbc.update("INSERT INTO tx_items(id) VALUES (?)", "C");
    publisher.publishEvent(new OrderCreated("C"));
    status.setRollbackOnly();
});
~~~

`status.setRollbackOnly()` instructs the transaction manager to roll back when the transaction ends. In a fresh transaction opened by `TransactionTemplate` as in the example, the method can return normally, yet the database has no row C and rollback listeners still fire.

This is a necessary check because a test asserting only "does not throw" could wrongly conclude a commit happened.

If code joins an existing transaction with `REQUIRED` propagation, an inner scope marking rollback-only can cause the outer commit to throw `UnexpectedRollbackException`. The outcome and where the exception surfaces depend on propagation, not always matching an isolated new transaction.

**Testing rule:** inspect transaction status and final data effects, not exception flow alone.

## 11. No Transaction and `fallbackExecution`

When calling:

~~~java
publisher.publishEvent(new OrderCreated("N"));
~~~

outside any transaction, default `@TransactionalEventListener` listeners ignore event N. Spring cannot attach callbacks to a non-existent commit/rollback.

If a listener enables:

~~~java
@TransactionalEventListener(fallbackExecution = true)
public void accept(OrderCreated event) {
    // Receives the event even when there is no transaction.
}
~~~

it can execute immediately when published outside a transaction. This is **illustrative**; the method must reside in a Spring bean.

Do not call that "AFTER_COMMIT ran" in a business sense. In the fallback branch, **no commit occurred at all**. This is dangerous if a listener sends an order confirmation email while the publisher never created a transaction.

Also distinguish **publishing after a transaction closed** from **publishing inside a transaction**. If a service commits first and then calls `publishEvent` outside the transaction, default listeners are skipped; to get post-commit callbacks, publish inside the transaction so the listener registers while the transaction is still active.

### Also Test Fallback Inside a Transaction

When a transaction is active, a listener with fallback enabled **does not bypass the phase** and still waits for the matching phase. In the full code, `FallbackRecorder` only appends `fallback:A` after commit A; it appends nothing for rollbacks B/C. This test ensures fallback configuration does not accidentally cause every outcome to be processed.

## 12. Trap When Placing `@Transactional` on Test Methods

With `Spring TestContext Framework`, an `@Transactional` test typically runs in a **test-managed transaction**, which rolls back by default when the test method ends. That differs completely from `TransactionTemplate` committing right before assertions.

Example:

~~~java
@SpringJUnitConfig(TestConfig.class)
@Transactional
class OrderEventIntegrationTest {
    @Autowired
    ApplicationEventPublisher publisher;

    // Illustrative method, omitting all required beans/imports.
    public void aTestBody() {
        publisher.publishEvent(new OrderCreated("A"));
        // AFTER_COMMIT has not run yet: test transaction is still open.
    }
}
~~~

This illustrative snippet requires `spring-test` and test configuration. There are two parts to the problem:

1. Assertions inside the test body run **before** the test-managed transaction ends.
2. By default, Spring TestContext rolls back at test end, so `AFTER_COMMIT` may **never be called**.

Do not solve this with `Thread.sleep(500)`, because the callback is waiting for a **transaction phase**, not missing a few milliseconds.

### Solution 1: Do Not Wrap the Test in `@Transactional`

Section 6's example omits `@Transactional` on the test class/methods. Each test uses `TransactionTemplate` and asserts outside it. This is the clearest approach when you need to verify commit or rollback explicitly.

**Note:** if you put `@Transactional` on a test method **and** call `TransactionTemplate` with `REQUIRED` propagation, the template can join the TestContext-opened transaction. Then `executeWithoutResult` returning does not mean the outer test transaction has ended.

### Solution 2: Spring Test's `TestTransaction`

Spring Test provides `TestTransaction.flagForCommit()` and `TestTransaction.end()` to conclude a test-managed transaction in a controlled way.

~~~java
// Illustrative snippet inside a test-managed transaction:
publisher.publishEvent(new OrderCreated("A"));

TestTransaction.flagForCommit();
TestTransaction.end();

// Only now assert AFTER_COMMIT.
~~~

This is not a standalone file; it requires Spring TestContext, a transaction manager bean, and `import org.springframework.test.context.transaction.TestTransaction`. If using `@Commit` or `@Rollback(false)`, commit can happen after the test method body, so assertions must still sit at the right place, such as an `@AfterTransaction` callback.

## 13. `BEFORE_COMMIT` Exceptions and Post-Commit Failures

### `BEFORE_COMMIT` Can Fail the Transaction

A validation listener:

~~~java
@TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
public void validate(OrderCreated event) {
    if ("REJECT".equals(event.id())) {
        throw new IllegalStateException("event rejected");
    }
}
~~~

If a `BEFORE_COMMIT` callback throws an unchecked exception, the transaction manager can roll back; this is a **pre-commit** failure. A dedicated test should verify the exception/rollback, absence of `AFTER_COMMIT`, and zero rows in the database.

Place a deliberately throwing listener in a dedicated configuration for that test; do not attach it to section 6's shared collector or it would break unrelated commit cases.

### `AFTER_COMMIT` Cannot Turn Back Time

When an `AFTER_COMMIT` listener runs, the database has already committed. If sending an HTTP call or email fails here, the error does not roll back already committed data. Thus, tests should never expect "AFTER_COMMIT throwing rolls back the order placement transaction."

To safeguard critical post-commit side effects:

- Use bounded retries and idempotency.
- Track actual handler errors and outcomes.
- Use a transactional outbox or message broker when work must survive restarts.
- Never treat Spring in-process events as a durable queue or exactly-once delivery.

### Writing to the Database in a Post-Commit Listener

Javadoc warns that after commit/rollback/completion, transaction resources may still be accessible, yet additional writes may "participate" in old resources without **receiving a fresh commit**. If you need to write an audit record after commit, use a **new** transaction with a real boundary, such as another bean annotated with `@Transactional(propagation = REQUIRES_NEW)` invoked through a Spring proxy.

Do not call `this.saveAudit()` assuming a transaction proxy applies to self-invocation. Tests should verify the audit row exists in the database **after the new transaction**, not merely that `jdbc.update` returned a row count.

## 14. Async, `@Order`, and Callback Timing

In imperative transactions, context is usually bound to **the thread executing the transaction**. If you offload `publishEvent` to another thread before transaction synchronization is registered, the new thread may lack the transaction context.

Do not simply configure an executor on `SimpleApplicationEventMulticaster` and assume every transactional listener will run asynchronously. Spring 6.1+ supports `ApplicationListener.supportsAsyncExecution()`; transaction-bound listeners may need to register callbacks on the original thread.

With `@Async`, additional risks apply:

- Actual work runs after the publisher returns.
- Worker exceptions do not necessarily return to the publisher.
- A callback that merely constructs a `Mono`/`CompletableFuture` without awaiting it can exit before the side effect.
- The caller's ThreadLocal transaction context does not automatically propagate to workers.
- `Thread.sleep` in tests only hopes for timing rather than guaranteeing handler completion.

To test async, use `CountDownLatch`, `Future`, or a controlled completion signal with a timeout, then assert real outcomes. Do not mix async tests into synchronous phase tests without clearly defining transaction boundaries.

### `@Order`

`@Order` can prioritize listeners under applicable conditions. It does not change **transaction phase** ordering. An `AFTER_COMMIT` callback cannot be moved ahead of `BEFORE_COMMIT` merely via `@Order(-100)`.

If business rules require ordering between two listeners in the same phase, write a dedicated test using explicit `@Order` and ordered traces; general phase tests should compare counts/label sets so they do not depend on uncontracted details.

## 15. Testing Reactive Transactions: A Different Case

Since Spring Framework 6.1, `@TransactionalEventListener` supports both mechanisms:

| Mechanism | Transaction Manager | Context | Appropriate Event Publishing |
| --- | --- | --- | --- |
| Imperative JDBC/JPA | `PlatformTransactionManager` | ThreadLocal | `ApplicationEventPublisher` inside transaction |
| Reactive R2DBC | `ReactiveTransactionManager` | Reactor Context | `TransactionalEventPublisher`, event source carries `TransactionContext` |

The main test suite uses `DataSourceTransactionManager` and `JdbcTemplate`, so it **does not prove** reactive behavior. Reactive transactions do not rely on a ThreadLocal transaction context.

Reactive testing concept:

~~~java
Mono<Void> work = reactiveRepository.save(order)
        .then(transactionalEventPublisher.publishEvent(
                new OrderCreated("A")));

StepVerifier.create(transactionalOperator.transactional(work))
        .verifyComplete();
~~~

This is an **illustrative** snippet requiring Spring reactive transactions, an R2DBC repository, `TransactionalOperator`, `TransactionalEventPublisher`, Reactor Test, and matching beans. Merely constructing a `Mono` without subscribing does not execute save/publish; `StepVerifier` actually subscribes and awaits completion of the transaction operator.

To test reactive rollback, publish the event successfully inside the transaction before chaining `Mono.error(...)`, then assert `AFTER_ROLLBACK`, `AFTER_COMPLETION`, and R2DBC database state. Do not use `DataSourceTransactionManager` for R2DBC, and do not use a plain publisher assuming the source already carries a reactive `TransactionContext`.

## 16. Troubleshooting: Why Is the Test Red?

| Symptom | Common Cause | How to Check |
| --- | --- | --- |
| `AFTER_COMMIT` does not run | Not committed yet, test defaults to rollback, no transaction | Verify transaction boundary before assertions |
| `AFTER_ROLLBACK` does not run | Event was not published before the error | Publish inside the transaction prior to throwing |
| Listener is never called | Not a Spring bean, wrong annotation import | Build a real context and inspect bean registration |
| Listener runs outside transaction | `fallbackExecution=true` | Test the fallback branch separately |
| Database still has row after rollback | `JdbcTemplate` uses a different datasource, wrong transaction | Verify manager and actual resource |
| Test only mocks publisher | No transaction synchronization | Use a real publisher/context/manager |
| Test calls listener directly | Only tests body logic | Add integration test publishing via Spring |
| Outcome depends on suite execution order | Database/collector shares state | Isolate context and DB per test |
| `BEFORE_COMMIT` ran yet no data exists | Commit failed after callback | Check exceptions and final DB state |
| `AFTER_COMMIT` listener writes DB yet nothing saved | No new transaction opened | Use `REQUIRES_NEW` via a proper proxy |
| Test has `@Transactional` and calls `TransactionTemplate` | Joins the existing test transaction | Remove annotation or use `TestTransaction` |
| Async test intermittently PASSES/FAILS | Assertions run before worker | Await completion with a timeout |
| Reactive listener does not run | Event source lacks reactive `TransactionContext` | Use `TransactionalEventPublisher` |
| Rollback-only yields unexpected outcome | Propagation/nested transactions | Check inner/outer status and `UnexpectedRollbackException` |
| Listener runs twice | Duplicate bean/listener registrations or parent-child contexts | Inspect beans and event sources |
| Testing error cases yields no rollback callbacks | Error occurred prior to publish | Verify publish order and error timing |

## 17. Checklist and Practice Exercises

Checklist:

- [ ] Listener is registered by Spring from a real bean.
- [ ] Event is published **inside an active transaction** when testing phases.
- [ ] Commit/rollback happens **before** corresponding assertions.
- [ ] `AFTER_COMMIT` and `AFTER_ROLLBACK` are not confused.
- [ ] `AFTER_COMPLETION` is verified in both outcomes.
- [ ] Database is queried outside the transaction and shows matching results.
- [ ] Exception is raised after publish when testing rollback callbacks.
- [ ] No-transaction and fallback scenarios are tested independently.
- [ ] No outer `@Transactional` on the test class shifts transaction timing.
- [ ] Async listeners use a timeout-bounded completion signal, never sleep.
- [ ] Reactive and imperative managers are not cross-used.
- [ ] No assumption that internal events guarantee delivery across crashes/restarts.

Extended exercises:

1. Create a `BEFORE_COMMIT` listener that throws an exception for event ID `"REJECT"`, then verify the database does not commit and `AFTER_COMMIT` callbacks do not run.
2. Try `@SpringJUnitConfig` + `@Transactional` to observe default rollback; then use `TestTransaction.flagForCommit()` and `end()`.
3. Add an `@TransactionalEventListener(fallbackExecution=true)` listener in phase `AFTER_ROLLBACK`. Distinguish immediate fallback execution outside a transaction from a real rollback.
4. Publish two different events in one transaction, asserting callback counts per phase and ordering only when explicit `@Order` is present.
5. Add an `AFTER_COMMIT` listener writing an audit row in a new transaction. Confirm the audit exists only when the business transaction commits and persists after the callback.
6. Switch to R2DBC + `StepVerifier` and test commit/rollback with a real reactive transaction context.
7. Use Testcontainers PostgreSQL to test constraint/commit failures that H2 cannot simulate accurately.
8. Add an external side effect that fails after commit, verifying the business transaction does not roll back and designing an outbox/retry properly.

## 18. References

- Spring Framework Reference 6.2 — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
- Spring Framework Javadoc 6.2 — `TransactionalEventListener`: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html
- Spring Framework Javadoc 6.2 — `TransactionPhase`: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/transaction/event/TransactionPhase.html
- Spring Framework Javadoc 6.2 — `TransactionTemplate`: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html
- Spring Framework Javadoc 6.2 — `DataSourceTransactionManager`: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html
- Spring Framework Reference 6.2 — Programmatic Transaction Management: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/programmatic.html
- Spring Framework Reference 6.2 — Test-managed Transactions: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html
- Spring Framework Javadoc — `TestTransaction`: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/test/context/transaction/TestTransaction.html
- Spring Framework Reference — Embedded Database Support: https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/embedded-database-support.html
- Spring Framework Javadoc — `TransactionalEventPublisher`: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/transaction/reactive/TransactionalEventPublisher.html
- JUnit 5 User Guide: https://junit.org/junit5/docs/current/user-guide/
