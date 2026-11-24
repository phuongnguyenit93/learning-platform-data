# Testing Reactive Transaction Events in Spring Framework

## 1. Objectives

A reactive transaction event is a Spring event bound to the lifecycle of a **reactive transaction** managed by `ReactiveTransactionManager`. When testing, what needs to be proven is not merely whether a listener receives an event, but also **which phase the listener runs in, whether the transaction commits or rolls back, and whether data is actually persisted or reverted**.

After this lesson, you can:

- Distinguish reactive transactional events from events running in imperative transactions managed by `PlatformTransactionManager`.
- Create reactive transactions with `TransactionalOperator`, publish events with `TransactionalEventPublisher`, and register callbacks with `@TransactionalEventListener`.
- Test `BEFORE_COMMIT`, `AFTER_COMMIT`, `AFTER_ROLLBACK`, and `AFTER_COMPLETION` using JUnit 5 and `StepVerifier`.
- Combine callback verification with R2DBC data queries after the transaction finishes.
- Test publishing events outside a transaction, lost transaction context, unsubscribed `Mono`, and incorrect composition.
- Avoid false-positive tests caused by mocking the wrong transaction manager, using a plain publisher, ignoring terminal signals, or relying on `Thread.sleep`.

This lesson focuses on Spring Framework 6.1+ and Java 17+ examples using Spring 6.2.x with R2DBC H2. It covers **testing reactive transaction events**, not messaging architectures or durable queuing systems.

## 2. How do reactive transactional events work?

Spring supported `@TransactionalEventListener` even before reactive transactions. Since Spring Framework 6.1, this annotation also supports transactions managed by `ReactiveTransactionManager`. The main difference lies in **where the transaction context is stored**:

| Mechanism | Transaction manager | Transaction context | How events are published |
| --- | --- | --- | --- |
| Imperative JDBC/JPA | `PlatformTransactionManager` | ThreadLocal bound to the running thread | `ApplicationEventPublisher.publishEvent(...)` inside the transaction |
| Reactive R2DBC | `ReactiveTransactionManager` | `Reactor Context` of the reactive flow | `TransactionalEventPublisher` to place `TransactionContext` into the event's source |

In reactive programming, a processing flow can execute across multiple threads. You must not infer that a reactive transaction exists simply because a method is running on a thread that previously opened a transaction. `ReactiveTransactionManager` and reactive resources use context propagated through the **subscription**.

`TransactionalEventPublisher.publishEvent(payload)` returns a `Mono<Void>`. When this Mono is **subscribed to inside a reactive transaction**, the wrapper retrieves the current `org.springframework.transaction.reactive.TransactionContext`, creates a `PayloadApplicationEvent` whose source is TransactionContext, and publishes it via `ApplicationEventPublisher`. On the receiving side, `@TransactionalEventListener` recognizes the transaction and registers a callback for the corresponding phase.

~~~text
StepVerifier.subscribe()
       |
       v
TransactionalOperator opens reactive transaction
       |
       v
R2DBC operates on data inside transaction
       |
       v
TransactionalEventPublisher.publishEvent(payload)
       |
       +--> reads TransactionContext from Reactor Context
       +--> creates PayloadApplicationEvent(source=TransactionContext)
       +--> Spring dispatches event and registers synchronization
       |
       v
Pipeline completes
       |
       +--> onComplete -> commit:
       |    BEFORE_COMMIT -> commit -> AFTER_COMMIT -> AFTER_COMPLETION
       |
       +--> onError -> rollback:
            AFTER_ROLLBACK -> AFTER_COMPLETION
~~~

The diagram shows the **normal path**; there are still cases where commit fails or the transaction is already rollback-only, causing an outcome different from the business logic's success signal.

## 3. Understanding the four transaction phases accurately

`@TransactionalEventListener` uses `TransactionPhase`. If `phase` is omitted, the default is `AFTER_COMMIT`.

| Phase | When it is invoked | Required test case |
| --- | --- | --- |
| `BEFORE_COMMIT` | Before actual resource commit, while the transaction is completing along the commit branch | Present on commit branch; usually does not run if the pipeline already errored and the transaction rolled back |
| `AFTER_COMMIT` | After the transaction commits successfully | Present on commit; absent on rollback |
| `AFTER_ROLLBACK` | After rollback | Present on rollback; absent on commit |
| `AFTER_COMPLETION` | When the transaction finishes, whether commit or rollback | Present in both cases |

Events in post-completion phases may still see old resources in certain cases, but **you must not assume new data writes in `AFTER_COMMIT` will be committed**. If new data operations are needed after commit, initiate an appropriate new transaction.

Easy-to-miss point: **having run `BEFORE_COMMIT` does not prove the commit succeeded**. A database error occurring during the commit step can still lead to failure. Therefore, tests must verify the transaction outcome and data state after commit, rather than only verifying that the `BEFORE_COMMIT` listener was called.

If an event is published outside a transaction, `@TransactionalEventListener` by default **does not process it** because there is no phase to bind the callback to. The `fallbackExecution = true` option is a separate fallback mechanism; tests should keep it separate from real transaction tests.

## 4. Designing the test matrix

Before writing code, identify inputs, terminal signals, and expected evidence:

| Test case | Event publication | Pipeline signal | Expected callbacks | DB state |
| --- | --- | --- | --- | --- |
| Successful commit | Inside `TransactionalOperator`, reactive wrapper | `onComplete` | BEFORE, AFTER_COMMIT, AFTER_COMPLETION | Insert persisted |
| Rollback on error | After insert, inside transaction, then `onError` | `onError` with clear cause | AFTER_ROLLBACK, AFTER_COMPLETION | Insert rolled back |
| Outside transaction | Regular `ApplicationEventPublisher` | Synchronous call returns | No transaction listener runs | Unchanged |
| Wrapper outside transaction | `TransactionalEventPublisher` but missing context | Mono emits error on subscribe | No callbacks | Unchanged |
| Not subscribed | Only building the `Mono` | No terminal signal | No callbacks | Unchanged |
| Plain publisher inside reactive transaction | Transaction exists, but event lacks transaction source | Transaction may commit | No reactive transaction callbacks | If data exists, verify separately |

Each commit/rollback case needs **two kinds of oracles**:

1. **Callback oracle:** traces in a thread-safe collector showing which methods were called.
2. **Database oracle:** a query from an **out-of-transaction** subscription after the publisher finishes to verify whether changes truly committed or rolled back.

Merely mocking `EventPublisher` and checking `publishEvent(...)` was called cannot verify phases. Calling listener methods directly also does not verify Spring's synchronization registration mechanism.

## 5. Environment, dependencies, and structure

The example runs with **JDK 17+, Gradle, Spring Framework 6.2.x, JUnit 5, Reactor Test, and R2DBC H2**. No Spring Boot or HTTP server is needed. The in-memory H2 database provides real transactions to verify commit/rollback.

Structure:

~~~text
reactive-event-test/
├── settings.gradle
├── build.gradle
└── src/
    └── test/
        └── java/
            └── example/
                └── ReactiveTransactionEventTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'reactive-event-test'
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
    testImplementation 'org.springframework:spring-r2dbc:6.2.15'
    testImplementation 'io.r2dbc:r2dbc-h2:1.0.0.RELEASE'
    testImplementation 'io.projectreactor:reactor-test:3.7.12'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

test {
    useJUnitPlatform()
}
~~~

Key dependencies:

- `spring-context` provides the Spring context, event publisher, and listeners.
- `spring-r2dbc` provides `DatabaseClient` and `R2dbcTransactionManager`, while pulling in the necessary transaction infrastructure.
- `r2dbc-h2` provides the **R2DBC ConnectionFactory**; do not substitute the JDBC driver `com.h2database:h2` with `DataSourceTransactionManager`.
- `reactor-test` contains `StepVerifier` to subscribe to pipelines, verify signals, and attach test timeouts.
- `junit-jupiter` together with JUnit Platform runs the tests.

Version `1.0.0.RELEASE` of R2DBC H2 belongs to the line compatible with H2 2.1–2.3. In Spring Boot, prefer Boot's dependency management/BOM instead of pinning multiple Spring and Reactor versions independently.

## 6. Complete Java 17+ test suite

Create `src/test/java/example/ReactiveTransactionEventTest.java` with the following full source code:

~~~java
package example;

import java.time.Duration;
import java.util.List;
import java.util.Set;
import java.util.concurrent.CopyOnWriteArrayList;

import io.r2dbc.spi.ConnectionFactories;
import io.r2dbc.spi.ConnectionFactory;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.r2dbc.connection.R2dbcTransactionManager;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.transaction.ReactiveTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.reactive.TransactionalEventPublisher;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Timeout(15)
class ReactiveTransactionEventTest {

    // Payload is a Java record, not extending ApplicationEvent.
    record OrderRecorded(String id) {}

    public static class EventLog {
        private final CopyOnWriteArrayList<String> entries =
                new CopyOnWriteArrayList<>();

        @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
        public void before(OrderRecorded event) {
            entries.add("before:" + event.id());
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
        public void committed(OrderRecorded event) {
            entries.add("commit:" + event.id());
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
        public void rolledBack(OrderRecorded event) {
            entries.add("rollback:" + event.id());
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)
        public void completed(OrderRecorded event) {
            entries.add("complete:" + event.id());
        }

        List<String> snapshot() {
            return List.copyOf(entries);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class Config {

        @Bean
        ConnectionFactory connectionFactory() {
            return ConnectionFactories.get(
                    "r2dbc:h2:mem:///reactive_event_test"
                    + "?options=DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE");
        }

        @Bean
        DatabaseClient databaseClient(ConnectionFactory connectionFactory) {
            return DatabaseClient.create(connectionFactory);
        }

        @Bean
        ReactiveTransactionManager transactionManager(
                ConnectionFactory connectionFactory) {
            return new R2dbcTransactionManager(connectionFactory);
        }

        @Bean
        TransactionalOperator transactionalOperator(
                ReactiveTransactionManager transactionManager) {
            return TransactionalOperator.create(transactionManager);
        }

        @Bean
        TransactionalEventPublisher transactionalEventPublisher(
                ApplicationEventPublisher publisher) {
            return new TransactionalEventPublisher(publisher);
        }

        @Bean
        EventLog eventLog() {
            return new EventLog();
        }
    }

    private AnnotationConfigApplicationContext context;
    private DatabaseClient db;
    private TransactionalOperator tx;
    private TransactionalEventPublisher publisher;
    private EventLog log;

    @BeforeEach
    void setUp() {
        context = new AnnotationConfigApplicationContext(Config.class);
        db = context.getBean(DatabaseClient.class);
        tx = context.getBean(TransactionalOperator.class);
        publisher = context.getBean(TransactionalEventPublisher.class);
        log = context.getBean(EventLog.class);

        // Create schema and clear data before each test.
        StepVerifier.create(db.sql(
                "CREATE TABLE IF NOT EXISTS tx_orders "
                + "(id VARCHAR(40) PRIMARY KEY)")
                .fetch().rowsUpdated().then())
                .expectComplete()
                .verify(Duration.ofSeconds(10));

        StepVerifier.create(db.sql("DELETE FROM tx_orders")
                .fetch().rowsUpdated().then())
                .expectComplete()
                .verify(Duration.ofSeconds(10));
    }

    @AfterEach
    void tearDown() {
        if (context != null) {
            context.close();
        }
    }

    private Mono<Long> countRows(String id) {
        return db.sql("SELECT COUNT(*) FROM tx_orders WHERE id = :id")
                .bind("id", id)
                .map((row, metadata) ->
                        ((Number) row.get(0)).longValue())
                .one();
    }

    private void assertPhases(String... expected) {
        List<String> actual = log.snapshot();

        // Match exact count and labels; do not constrain unnecessary
        // internal ordering among callbacks.
        assertEquals(expected.length, actual.size());
        assertEquals(Set.of(expected), Set.copyOf(actual));
    }

    @Test
    void commitInvokesCommitPhasesAndPersistsRow() {
        Mono<Void> operation = db.sql(
                "INSERT INTO tx_orders (id) VALUES (:id)")
                .bind("id", "A")
                .fetch().rowsUpdated()
                .then(publisher.publishEvent(new OrderRecorded("A")));

        StepVerifier.create(tx.transactional(operation))
                .expectComplete()
                .verify(Duration.ofSeconds(10));

        assertPhases("before:A", "commit:A", "complete:A");

        StepVerifier.create(countRows("A"))
                .expectNext(1L)
                .verifyComplete();
    }

    @Test
    void errorRollsBackAndInvokesRollbackPhases() {
        Mono<Void> operation = db.sql(
                "INSERT INTO tx_orders (id) VALUES (:id)")
                .bind("id", "B")
                .fetch().rowsUpdated()
                .then(publisher.publishEvent(new OrderRecorded("B")))
                .then(Mono.<Void>error(
                        new IllegalStateException("force rollback")));

        StepVerifier.create(tx.transactional(operation))
                .expectErrorMatches(error ->
                        error instanceof IllegalStateException
                        && "force rollback".equals(error.getMessage()))
                .verify(Duration.ofSeconds(10));

        assertPhases("rollback:B", "complete:B");

        StepVerifier.create(countRows("B"))
                .expectNext(0L)
                .verifyComplete();
    }

    @Test
    void eventOutsideTransactionIsIgnoredByDefault() {
        // Regular publisher can publish payload outside transaction,
        // but transactional listeners skip it by default.
        context.publishEvent(new OrderRecorded("outside"));
        assertTrue(log.snapshot().isEmpty());

        // Reactive wrapper cannot find TransactionContext.
        StepVerifier.create(
                publisher.publishEvent(new OrderRecorded("outside")))
                .expectError()
                .verify(Duration.ofSeconds(10));

        assertTrue(log.snapshot().isEmpty());
    }

    @Test
    void nothingHappensUntilSubscription() {
        Mono<Void> cold = tx.transactional(
                publisher.publishEvent(new OrderRecorded("cold")));

        assertTrue(log.snapshot().isEmpty());

        StepVerifier.create(cold)
                .expectComplete()
                .verify(Duration.ofSeconds(10));

        assertPhases("before:cold", "commit:cold", "complete:cold");
    }

    @Test
    void plainPublisherDoesNotCarryReactiveTransactionSource() {
        // Has reactive transaction, yet event source is still wrong.
        Mono<Void> operation = tx.transactional(
                Mono.fromRunnable(() ->
                        context.publishEvent(new OrderRecorded("plain"))));

        StepVerifier.create(operation)
                .expectComplete()
                .verify(Duration.ofSeconds(10));

        assertTrue(log.snapshot().isEmpty());
    }
}
~~~

**Main parts of the example:**

1. `Config` creates the Spring context, R2DBC `ConnectionFactory`, `R2dbcTransactionManager`, and `TransactionalOperator`. `@EnableTransactionManagement` activates the transaction annotation infrastructure required for `@TransactionalEventListener` in a plain context.
2. `TransactionalEventPublisher` is declared as a bean using `ApplicationEventPublisher`. This wrapper ensures events carry `TransactionContext` in their source when used properly.
3. `EventLog` is a bean containing four listeners for the four phases; a thread-safe list records labeled entries with IDs to distinguish emissions.
4. `@BeforeEach` creates the context and resets the `tx_orders` table; `@AfterEach` closes the context. H2 is kept alive across connections via `DB_CLOSE_DELAY=-1`.
5. `StepVerifier` subscribes to the `Mono` and checks the terminal signal. Afterwards, the test queries the database **outside the transaction** to cross-check the outcome.
6. `assertPhases` checks the exact callback count and label set; it does not turn internal traversal ordering of same-stage callbacks into a business assumption.

`@Timeout(15)` keeps hung tests under control. Timeouts in `verify` limit test waiting time; they do not replace business guarantees.

## 7. How to run and expected results

From the `reactive-event-test` directory, using JDK 17+ and Gradle:

~~~bash
gradle test
~~~

If Gradle Wrapper is present, use `./gradlew test` on Linux/macOS or `gradlew.bat test` on Windows. Gradle generates an HTML report at `build/reports/tests/test/index.html`.

The test suite has **five `@Test` methods**. If dependencies download properly and the environment supports R2DBC H2 and Spring infrastructure as configured, all five tests are expected to complete successfully.

Do not publish a specific Gradle stdout excerpt as proof without actually running it: timings, dependency logs, and test ordering may vary. The meaning of each assertion is right in the code:

- `commitInvokesCommitPhasesAndPersistsRow`: has `before:A`, `commit:A`, `complete:A`; table has one row A.
- `errorRollsBackAndInvokesRollbackPhases`: has `rollback:B`, `complete:B`; no `commit:B`; table has no row B.
- `eventOutsideTransactionIsIgnoredByDefault`: transaction listeners do not receive the event; reactive wrapper errors when there is no transaction context.
- `nothingHappensUntilSubscription`: list is empty before subscribe; transaction commit callbacks appear only after subscribing.
- `plainPublisherDoesNotCarryReactiveTransactionSource`: using the regular publisher inside a reactive transaction does not produce the required event source, so there are no reactive phase callbacks.

**Practical note:** the results above are test expectations derived from the code, not a report executed by tooling in the current environment. When bringing this into a project, run `gradle test` to verify both compilation and runtime behavior.

## 8. Analyzing the successful commit test

Core snippet:

~~~java
Mono<Void> operation = db.sql(
        "INSERT INTO tx_orders (id) VALUES (:id)")
        .bind("id", "A")
        .fetch().rowsUpdated()
        .then(publisher.publishEvent(new OrderRecorded("A")));

StepVerifier.create(tx.transactional(operation))
        .expectComplete()
        .verify(Duration.ofSeconds(10));
~~~

What happens when `StepVerifier` subscribes:

1. `TransactionalOperator` opens a transaction managed by `R2dbcTransactionManager`; context is propagated through Reactor Context.
2. `DatabaseClient` executes the insert using a connection participating in the current transaction.
3. `then(...)` waits for the insert operation to finish before subscribing to `publisher.publishEvent(...)`.
4. `TransactionalEventPublisher` retrieves `TransactionContext` from the reactive chain and constructs an event with the right source.
5. `EventLog`'s `@TransactionalEventListener` registers phase callbacks; publishing does not mean the callbacks have already run.
6. The business part emits `onComplete`; the transaction manager proceeds to commit, invoking `BEFORE_COMMIT`, then post-commit/completion callbacks.
7. The outer `tx.transactional(...)` publisher completes after transaction processing; only then does the test assert the snapshot and query table A.

Therefore, a test that only calls `publisher.publishEvent(event)` without using `StepVerifier` or subscribing proves nothing. Reactive publishers are **lazy** structures; building a pipeline is not equivalent to executing it.

### Why verify the table after commit?

Suppose a listener logs `AFTER_COMMIT`, yet no real transaction existed, it rolled back, or a driver was incompletely mocked. An assertion on a log list cannot detect all of those issues. Querying outside the transaction confirms H2 actually saved row A. When testing data, query the same database after the transaction publisher has finished to avoid reading uncommitted state by mistake.

## 9. Analyzing the rollback test

In the rollback test, inserting the row and publishing the event **occurred inside the transaction** before the pipeline emitted an error:

~~~java
Mono<Void> operation = db.sql(
        "INSERT INTO tx_orders (id) VALUES (:id)")
    .bind("id", "B")
    .fetch().rowsUpdated()
    .then(publisher.publishEvent(new OrderRecorded("B")))
    .then(Mono.<Void>error(
            new IllegalStateException("force rollback")));
~~~

`TransactionalOperator` receives `onError` and triggers rollback. `StepVerifier.expectErrorMatches(...)` verifies the exact business exception, not just any arbitrary error. After the transaction finishes handling it, the checks include:

- An `AFTER_ROLLBACK` callback for B.
- An `AFTER_COMPLETION` callback for B.
- No `AFTER_COMMIT` and no `BEFORE_COMMIT` for B.
- Row B does not exist in the table.

All three conditions together are necessary. Row B missing without the rollback callback running may indicate an event-registration bug. Rollback callback running while row B still exists may indicate the R2DBC operation did not participate in the transaction the test meant to verify.

**Note on error timing:** if the pipeline throws an error **before** `publisher.publishEvent(...)`, the event has not been published/registered yet, so you cannot expect an `AFTER_ROLLBACK` listener for that event. Similarly, when the transaction has already been marked rollback-only prior to the commit stage, `BEFORE_COMMIT` is not necessarily invoked.

## 10. Why isn't a plain publisher enough inside a reactive transaction?

The snippet:

~~~java
Mono<Void> operation = tx.transactional(
    Mono.fromRunnable(() ->
        context.publishEvent(new OrderRecorded("plain"))));
~~~

is still subscribed inside the reactive transaction. However, `context.publishEvent(payload)` is a plain publisher; the event is wrapped with the publisher object as its source, **not the reactive `TransactionContext`**. With reactive transactions, `@TransactionalEventListener` cannot rely on ThreadLocal to fetch context like in imperative transactions. Thus, `plainPublisherDoesNotCarryReactiveTransactionSource` tests for a common wiring bug.

The right path:

~~~java
Mono<Void> operation = tx.transactional(
    transactionalPublisher.publishEvent(new OrderRecorded("ok")));
~~~

In this illustrative code, `transactionalPublisher` is a `TransactionalEventPublisher` bean and `tx` is `TransactionalOperator`. The wrapper automatically retrieves TransactionContext at subscription time.

### If a custom ApplicationEvent is needed

The `TransactionalEventPublisher.publishEvent(Object payload)` overload is for a **plain payload**; it does not accept a pre-created `ApplicationEvent`. For a custom `ApplicationEvent`, use the overload taking a factory function from source:

~~~java
class AuditEvent extends org.springframework.context.ApplicationEvent {
    private final String id;

    AuditEvent(Object source, String id) {
        super(source);
        this.id = id;
    }

    String id() {
        return id;
    }
}

// Illustrative inside a reactive transaction:
Mono<Void> send = transactionalPublisher.publishEvent(
    source -> new AuditEvent(source, "A"));
~~~

This is an **illustrative snippet** needing the matching variables and Spring beans, not a standalone program. The `source` received by the function is the `TransactionContext` supplied by the wrapper; do not replace it with `this`, a request, or an entity if you want the listener bound to the reactive transaction.

## 11. Signs of lost subscription or Reactor Context

A common mistake is creating a Mono inside a side callback and ignoring it:

~~~java
// Wrong: publisher.publishEvent(...) creates a Mono but it is never subscribed to.
Mono.just("A")
    .doOnNext(id -> transactionalPublisher.publishEvent(
        new OrderRecorded(id)));
~~~

`doOnNext` is suited for **synchronous, immediate** side effects; here the side effect is a reactive publisher that needs subscribing. Creating a Mono without composing it only constructs a work description.

The right way is to use `flatMap` or `then`:

~~~java
Mono.just("A")
    .flatMap(id -> transactionalPublisher.publishEvent(
        new OrderRecorded(id)))
    .as(tx::transactional);
~~~

These snippets illustrate with `transactionalPublisher` and `tx` already declared. When accurate testing is needed, wrap the result in `StepVerifier.create(...)`.

Other sources of lost context include calling `subscribe()` individually inside a service, splitting work into an independent pipeline without propagating context, or calling the publisher outside a transactional subscription. Design seamless reactive chains and avoid relying on "same thread" or static/thread-local variables for transaction handling.

`publishEvent(...)` from `TransactionalEventPublisher` returns `Mono<Void>`: it emits no `onNext` value to await, so `flatMap`, `then`, and `StepVerifier.expectComplete()` are more appropriate than trying to `expectNext(...)` an event.

## 12. Fallback, @Transactional test methods, and special cases

### 12.1. No transaction and fallbackExecution

By default `@TransactionalEventListener` has `fallbackExecution = false`. If an event is published outside a transaction, the listener is skipped; that is proper behavior rather than a Spring bug.

If the application wants the callback to run even without a transaction:

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT,
    fallbackExecution = true)
public void handleWithFallback(OrderRecorded event) {
    // Also accepts handling when there is no transaction.
}
~~~

This snippet is an **illustrative method** that must live inside a Spring bean. Tests must clearly separate the two branches: the branch with a real commit and the fallback branch **with no commit at all**. Do not use a `listener ran` assertion to infer that data was committed.

### 12.2. Avoid slapping @Transactional onto an entire test mechanically

A test method wrapped by the framework in a test-managed transaction may be **rolled back at the end of the test**. If you place an `AFTER_COMMIT` assertion inside the method body before the test transaction finishes, the callback may not have run yet; or the test runner's rollback prevents the `AFTER_COMMIT` callback from running. With reactive transactions, putting test method annotations without knowing which manager is selected causes even more confusion.

The test suite in section 6 **does not put `@Transactional` on `@Test`**. Each method creates a concrete reactive transaction via `TransactionalOperator` and awaits its completion with `StepVerifier`, making the verification boundary explicit.

### 12.3. BEFORE_COMMIT can affect commit

You can add a `BEFORE_COMMIT` listener that intentionally throws `IllegalStateException` upon receiving a specific event, then test transaction rollback. However, keep it in a dedicated test/config so it does not break commit cases. An exception in a pre-commit callback can cause the transaction manager to roll back; tests should verify the actual database state and error signal.

### 12.4. Handling async work after commit

If a listener merely constructs a `Mono` or schedules an independent task without tying completion back into the transaction pipeline, `StepVerifier` waiting for transaction commit does not guarantee the side task finished. You need a separate completion signal with a timeout or final verification in the DB/messaging system. Do not use `Thread.sleep(100)` to time an asynchronous task that has no timing contract.

## 13. When is real R2DBC needed, and when can you mock?

There are three testing levels:

1. **Handler unit test:** invoke the listener method directly, mock services/repositories, and check business decisions. Cheap and fast, but has no transaction synchronization.
2. **Spring + R2DBC H2 integration test:** initializes context, event listener factory, `ReactiveTransactionManager`, publisher, database, subscription, and both real phases. Fits this lesson.
3. **Production-database integration test via Testcontainers:** helps verify specific semantics around isolation, constraints, locking, commit failures, and the real driver.

Mocking `ReactiveTransactionManager` to simply return `Mono.empty()` from `commit(...)` or `rollback(...)` usually **fails to create proper Reactor transaction contexts/synchronizations**. Then you can get false-positive tests: the application event appears while the transaction listener does not run, or the callback runs while the database does not roll back because there is no real resource at all.

An in-memory H2 database is only suitable for proving general mechanics; if production uses PostgreSQL, you need at least one group of integration tests with PostgreSQL R2DBC. Do not infer rollback capability of an external system (email, Kafka, REST API) from the rollback of an H2 table.

## 14. Subscription cancellation, timeouts, and errors on transaction close

Reactive publishers have `onComplete`, `onError`, and **cancel** signals. They are not fully equivalent:

- `onComplete` from business logic usually leads the transaction to commit unless rollback-only or another error occurs.
- `onError` causes the transaction manager to perform rollback and propagate the error to the downstream subscriber.
- `cancel` is a distinct signal that can lead to rollback/resource cancellation depending on operator semantics. Spring advises caution when using cancellation with transactional publishers.

If a business flow involves `take(...)`, `timeout(...)`, client disconnects, or special backpressure, write a **dedicated cancellation test**. Do not assume `thenCancel()` on StepVerifier behaves identically to emitting `Mono.error(...)`; outcomes and cleanup timing can differ.

Also distinguish two kinds of timeouts:

- `verify(Duration.ofSeconds(10))` in StepVerifier limits the **test's wait time**; it does not intentionally inject a `timeout` error into the business pipeline.
- `somePublisher.timeout(Duration...)` inside the transaction is an operator that can alter the terminal signal and cause transaction rollback.

When testing commit, choose a timeout generous enough to detect unreasonable hangs without tying to arbitrary sleep durations. When testing errors, `expectErrorMatches` should specify the expected cause. When testing rollback, read the DB only after the transaction-handling publisher has terminated.

## 15. Common errors and how to diagnose them

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| No listener runs | Event lacks reactive TransactionContext in source | Use `TransactionalEventPublisher`, keep Mono in transaction pipeline |
| Neither insert nor callback observed | `Mono` was never subscribed to | `StepVerifier.create(...).verify...` |
| Listener receives event despite no transaction | Missing transaction-aware listener factory or fallback enabled | Check `@EnableTransactionManagement` and `fallbackExecution` |
| `AFTER_COMMIT` does not run | Pipeline rolled back, not finished yet, or callback not registered | Assert signal, log phase and transaction outcome |
| `AFTER_ROLLBACK` does not run | Exception occurred **before publish**, or no transaction | Ensure event was published inside transaction before causing error |
| `BEFORE_COMMIT` ran yet row does not exist | Commit failed after callback or transaction rolled back | Check terminal signal and query DB |
| Using JDBC DataSource manager with R2DBC | Wrong transaction manager model | Use `R2dbcTransactionManager` and `ConnectionFactory` |
| `@EventListener` runs immediately, transaction listener ignores phase | Misconfigured annotation wiring | Check factory/`@EnableTransactionManagement` and annotation type |
| Test only PASSES when run alone | Shared database/table/collector across tests | Clear data per test, isolated context, distinct DB names |
| `@Order` present yet log order differs | Same-phase callbacks or async tasks do not guarantee completion order | Assert ordering only when contract requires and mechanism guarantees it |
| Tests using `Thread.sleep` are flaky | Varying schedulers, machine load, and threads | Wait for completion signal/latch with timeout |
| Test puts `@Transactional` on method yet expects immediate commit | Test-managed transaction stays open until end of test | Use `TransactionalOperator` directly in test |
| `AFTER_COMMIT` listener writes data yet DB misses it | Tried reusing resources of completed transaction | Open a new transaction if doing post-commit writes |
| Reactive wrapper outside transaction throws error | Missing TransactionContext | Put publication inside a chain wrapped by the operator |

When a test fails, check in order: **subscription -> transaction manager -> event source -> listener annotation/factory -> terminal signal -> database outcome**. This workflow isolates bugs without guessing from runtime timings or thread names.

## 16. Extended exercises

**Exercise 1 — Error in BEFORE_COMMIT.** Add a listener that checks if id equals `"reject"` and throws `IllegalStateException` in `BEFORE_COMMIT`. Write a test publishing an event after insert, then verify rollback, no `AFTER_COMMIT` callback, and no row in the DB. Compare with `onError` originating directly from the pipeline.

**Exercise 2 — Fallback.** Add a listener with `fallbackExecution = true`. Write a test publishing an event outside a transaction and assert the fallback listener is called. Explain why a fallback callback does not prove commit.

**Exercise 3 — Wrong context.** Change a `TransactionalEventPublisher` call to plain `ApplicationEventPublisher` inside a reactive transaction. Write an assertion detecting that the listener does not receive the phase properly, then fix it using the wrapper with a transaction source.

**Exercise 4 — Forgetting to compose.** Write a chain using `doOnNext` while ignoring the `Mono<Void>` returned by the publisher. Make the test fail intentionally, then fix it with `flatMap` or `then`. State the difference between "creating a publisher" and "subscribing to a publisher".

**Exercise 5 — Production database.** Replace H2 with Testcontainers PostgreSQL using R2DBC. Re-run commit/rollback cases and inspect differences in connections, isolation, constraints, and real transactions.

**Exercise 6 — Cancellation.** Design a subscription cancellation test with `StepVerifier.thenCancel()` and determine the outcome for your Spring/database version. Distinguish cancel from `onError`, avoiding treating them as identical.

## 17. References

- Spring Framework 6.2 Reference — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
- Javadoc `TransactionalEventPublisher`: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/transaction/reactive/TransactionalEventPublisher.html
- Javadoc `TransactionalEventListener`: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html
- Javadoc `TransactionalOperator`: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/transaction/reactive/TransactionalOperator.html
- Javadoc `TransactionPhase`: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/transaction/event/TransactionPhase.html
- Spring Framework — Programmatic Reactive Transactions: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/programmatic.html
- Spring Framework — @EnableTransactionManagement: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/transaction/annotation/EnableTransactionManagement.html
- Project Reactor — Testing with StepVerifier: https://projectreactor.io/docs/core/release/reference/testing.html
- R2DBC H2 README — driver and in-memory database URL: https://github.com/r2dbc/r2dbc-h2
