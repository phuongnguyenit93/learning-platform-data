# @EventListener, @TransactionalEventListener, and Commit Timing

## 1. Why Does “Event Published” Not Mean “Committed”?

In **Spring Boot - testing**, under the **Events and Observability** group, a common bug-prone scenario occurs when an application persists a transaction and publishes an event to send an email, write an audit log, invalidate a cache, or publish a message to another system. Developers frequently place `ApplicationEventPublisher.publishEvent(...)` inside a `@Transactional` method and assume every listener only runs once data has committed.

That is **not true for a regular `@EventListener`**. Under default configuration, `@EventListener` runs **synchronously as soon as the event is published**, meaning *before* the enclosing transaction commits. If the transaction later rolls back, external side effects already executed by the listener outside the DB (sending an email, calling an API, publishing to Kafka) **do not automatically roll back**.

By contrast, `@TransactionalEventListener` binds listener execution to a **transaction phase**. The default phase is `AFTER_COMMIT`, ensuring it only runs when the transaction actually succeeds. The remaining phases are `BEFORE_COMMIT`, `AFTER_ROLLBACK`, and `AFTER_COMPLETION`.

This lesson focuses on answering through tests rather than descriptions alone:

1. Which listener ran immediately when `publishEvent` was called?
2. Which listener runs only **after commit**, and not on rollback?
3. Which listeners run before commit, after rollback, or after every completion state?
4. If an event is published **without a transaction**, what happens?
5. Why might an `AFTER_COMMIT` listener calling `repository.save(...)` fail to create a durable record without opening a **new transaction**?
6. How do you test the commit boundary accurately without letting `@Transactional` on a JUnit test roll everything back?
7. Why do Spring application events not by themselves replace a message broker, transactional outbox, or reliable event delivery?

The complete example uses **Java 17, Spring Boot 3.3.0, Spring JDBC, an H2 in-memory database, and JUnit Jupiter**. It includes `@EventListener`, all four `TransactionPhase` values, `fallbackExecution=true`, an `AuditWriter` using `Propagation.REQUIRES_NEW`, and **9 integration test methods** verifying real database + event observations. No Docker or HTTP server is required.

## 2. Learning Outcomes

After this lesson, you will be able to:

- Explain `ApplicationEventPublisher`, `@EventListener`, `@TransactionalEventListener`, and `ApplicationEventMulticaster`.
- Know that Java 17 POJOs/records can be published as event payloads without necessarily extending `ApplicationEvent`.
- Understand synchronous vs. asynchronous multicasting; default publication is typically synchronous on the publisher's thread.
- Distinguish method invocation time, publish time, and transaction commit time.
- Use `@TransactionalEventListener(phase=TransactionPhase.AFTER_COMMIT)` to process only after a successful commit.
- Verify `BEFORE_COMMIT`, `AFTER_ROLLBACK`, and `AFTER_COMPLETION`.
- Explain why `BEFORE_COMMIT` does not guarantee that the subsequent commit will succeed.
- Know that the default `fallbackExecution=false` makes transactional listeners ignore events published outside a transaction.
- Use `fallbackExecution=true` when non-transactional execution is desired, without implicitly calling it a commit.
- Know why `@Transactional` on a service must go through a Spring AOP proxy and requires a transaction manager.
- Understand the issue where `AFTER_COMMIT` transaction resources may remain bound while new DB writes are not committed.
- Extract a `@Transactional(propagation=REQUIRES_NEW)` Spring bean to persist durable audit rows after commit.
- Distinguish `REQUIRES_NEW` from `REQUIRED` and `NESTED`; do not assume `@Transactional` on a same-object self-invocation takes effect.
- Write tests for commit, rollback, no-tx, phase ordering, and multiple events within one transaction.
- Avoid Spring TestContext's default `@Transactional` rollback causing false negatives for AFTER_COMMIT.
- Use `TestTransaction.flagForCommit()`/`TestTransaction.end()` when a test-managed transaction is genuinely needed.
- Isolate DB and in-memory event observations across test methods without relying on execution order.
- Avoid inferring that a durable DB row or remote message exists merely because an event handler was invoked.
- Choose a transactional outbox when reliable delivery across processes/message brokers is required.
- Understand the differences between imperative `PlatformTransactionManager` and reactive `ReactiveTransactionManager`/Reactor Context.
- Use logs, traces, and metrics to observe the event lifecycle without putting sensitive information into tags.

## 3. Two Event Processing Paths

```text
External request / scheduled command
              |
              v
Spring @Service proxy
              |
              +-- begins JDBC transaction
              |
              v
INSERT purchases(...)  [not committed]
              |
              v
ApplicationEventPublisher.publishEvent(
    new PurchaseCreatedEvent(ref))
              |
              +--> @EventListener
              |       runs NOW, usually synchronously
              |       may see current uncommitted transaction
              |
              +--> @TransactionalEventListener
                      registers transaction synchronization
              |
              v
Service returns to transaction interceptor
              |
              +--> BEFORE_COMMIT listener callbacks
              |
              +--> Commit database transaction
                      |
                      +--> AFTER_COMMIT callbacks
                      |       audit writer with REQUIRES_NEW
                      |
                      +--> AFTER_COMPLETION callbacks
```

If code throws an unchecked exception before commit:

```text
publishEvent()
     |
     +--> @EventListener runs now
     |
     +--> transactional callbacks registered
     |
     v
throw RuntimeException
     |
     v
transaction rollback
     |
     +--> AFTER_ROLLBACK
     +--> AFTER_COMPLETION
     |
     -X-> AFTER_COMMIT not called
     -X-> BEFORE_COMMIT not normally called
```

**Ordering note:** `AFTER_COMPLETION` runs after the transaction finishes for both commit and rollback. Do not arbitrarily assert a specific order between two listeners in the same completion phase, as it can depend on registration/`@Order`. This lesson only asserts **IMMEDIATE < BEFORE_COMMIT < AFTER_COMMIT** for a normal commit.

## 4. @EventListener: Immediate Receipt, Unbound to Commit Outcome

A simple listener:

```java
@Component
public class PurchaseNoticeListener {
    @EventListener
    public void onPurchase(PurchaseCreatedEvent event) {
        System.out.println("Published: " + event.ref());
    }
}
```

This is an illustrative snippet; the runnable project uses `PurchaseEventListeners` with `EventProbe` instead of stdout. Spring detects listener methods on managed beans when initializing the ApplicationContext.

### 4.1. Synchronous by Default

With the default `SimpleApplicationEventMulticaster`, synchronous event listeners are usually called on the **publisher's thread**, and `publishEvent` does not return until they finish. If a listener throws an unchecked exception, it may propagate to the caller; when the caller is inside a `@Transactional` method, the transaction can roll back per rules.

**Do not generalize this to every configuration:** if the application replaces the ApplicationEventMulticaster executor, uses `@Async`, or configures a custom error handler, thread/exception/lifecycle behavior changes. Tests must match the application's actual configuration.

### 4.2. @EventListener Inside an Open Transaction

When `publishEvent` is called inside a method that truly has an active Spring transaction, a synchronous listener can participate in that thread's context. It can read data that was just flushed but not yet committed, or call a repository/JdbcTemplate participating in the current transaction.

That **does not prove the transaction committed**. An email/API call in the listener can still leave the system before commit and cannot be automatically undone if the transaction rolls back.

### 4.3. Observations Can Mislead If You Only Check Handler Invocation

Test:

```java
service.placeAndFail("ORDER-1");
assertEquals(1, eventProbe.count("IMMEDIATE", "ORDER-1"));
```

Without asserting database rollback and AFTER_COMMIT absence, it is easy to falsely conclude that processing succeeded. The listener being called only means **the event was published to the listener at that moment**.

## 5. @TransactionalEventListener and the Four Phases

Spring Framework provides `@TransactionalEventListener` to bind a listener to the transaction lifecycle. The default `phase` is `AFTER_COMMIT`.

| Phase | Timing | When Transaction Commits | When Transaction Rolls Back |
| --- | --- | --- | --- |
| `BEFORE_COMMIT` | Before commit; still inside transaction | Usually runs | Usually does not run on direct rollback |
| `AFTER_COMMIT` | After successful commit | Runs | Does not run |
| `AFTER_ROLLBACK` | After rollback | Does not run | Runs |
| `AFTER_COMPLETION` | After completion regardless of outcome | Runs | Runs |

### 5.1. AFTER_COMMIT (Default)

```java
@TransactionalEventListener
public void afterCommit(PurchaseCreatedEvent event) {
    // Work only after successful commit.
}
```

Equivalent to `phase=TransactionPhase.AFTER_COMMIT`. If the transactional method rolls back, the callback does not execute.

**Not synonymous with reliable remote delivery:** once commit finishes, the process can crash right before the callback; or a callback sending to Kafka/email can fail. The original transaction has already committed and cannot roll back to synchronize the external side effect.

### 5.2. BEFORE_COMMIT

```java
@TransactionalEventListener(
        phase = TransactionPhase.BEFORE_COMMIT)
public void beforeCommit(PurchaseCreatedEvent event) {
    // Validation or in-transaction work, if appropriate.
}
```

Can be used for work that needs to happen inside the transaction before commit. However, **BEFORE_COMMIT does not guarantee commit will succeed**: database flush, constraints, deadlocks, or commit failures can still happen after the callback. Never dispatch irreversible side effects here and label them confirmed-committed.

### 5.3. AFTER_ROLLBACK

```java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_ROLLBACK)
public void afterRollback(PurchaseCreatedEvent event) {
    // Record a rollback observation or compensate when safe.
}
```

Used to observe, fall back, or compensate when a transaction fails to commit. If you need to persist an audit record to the database after rollback, **a separate transaction** such as `REQUIRES_NEW` is needed because the original transaction has rolled back. Do not treat `AFTER_ROLLBACK` as a magic way to undo arbitrary remote side effects.

### 5.4. AFTER_COMPLETION

```java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMPLETION)
public void afterCompletion(PurchaseCreatedEvent event) {
    // Cleanup/observe after either commit or rollback.
}
```

The callback runs after the transaction finishes, whether committed or rolled back. Annotating with this phase alone does not mean the business outcome was successful. When you need to distinguish outcomes, use separate `AFTER_COMMIT`/`AFTER_ROLLBACK` callbacks or dedicated TransactionSynchronization status checks.

### 5.5. One Event Can Trigger Multiple Callbacks

In the runnable lab, a single `PurchaseCreatedEvent` is listened to by multiple methods. For example, a commit produces IMMEDIATE, BEFORE_COMMIT, AFTER_COMMIT, and AFTER_COMPLETION. Do not assume “one event invokes only one listener” or “each phase corresponds to a unique business event”.

## 6. Without a Transaction: fallbackExecution

By default:

```java
@TransactionalEventListener
public void afterCommit(PurchaseCreatedEvent event) {
    // Not invoked if event published without a transaction.
}
```

Calling `publisher.publishEvent(new PurchaseCreatedEvent("A"))` outside a transaction means this callback **does not run**, because there is no commit phase to wait for. Meanwhile, a regular `@EventListener` still receives the event immediately.

If you want to handle non-transactional events as well:

```java
@TransactionalEventListener(fallbackExecution = true)
public void onPing(NoTxPingEvent event) {
    // Runs after commit in a transaction;
    // runs immediately if no transaction is active.
}
```

This is a **business choice**, not something to enable indiscriminately to mask a missing service transaction. When no transaction exists, the fallback callback runs immediately; it **does not fabricate a fake commit**.

**Important:** One listener with fallback enabled can process an event outside a transaction while another listener for the same event type with fallback=false does nothing. Tests must cover the exact branches.

## 7. The Difference Between Publish and Commit Boundaries

A method:

```java
@Transactional
public void create(String ref) {
    jdbc.update(
            "insert into purchases(ref) values (?)",
            ref);
    events.publishEvent(new PurchaseCreatedEvent(ref));
}
```

actually executes in a transaction when invoked **through the Spring proxy**. Conceptual order:

1. Spring transaction interceptor opens a transaction.
2. `jdbc.update` sends an INSERT inside the transaction.
3. `publishEvent` invokes synchronous `@EventListener` methods and registers transactional callbacks.
4. Target method returns.
5. Transaction interceptor completes commit or rollback.
6. Only after a successful commit do `AFTER_COMMIT` callbacks run.

### 7.1. Self-Invocation Prevents @Transactional from Applying

If a bean calls `this.create(...)` from another internal method in the same object, the call can bypass the Spring AOP proxy. In that case, there may be no outer transaction as expected. An individual JPA repository/JdbcTemplate operation might still run under auto-commit/its own transaction, leaving the event without the same commit boundary. This is a bug source hard to catch with unit tests calling `new Service()`.

In the lab, tests inject the Spring-managed `PurchaseService` and invoke public transactional methods from outside the bean.

### 7.2. Proxy Method Visibility

Prefer public service methods and invoke them through an injected Spring bean. Do not assume annotations on private methods or methods called directly from a constructor always produce transactional advice. When multiple PlatformTransactionManager beans exist, select the right manager/qualifier.

### 7.3. Default Rollback Rules

With standard Spring declarative transactions, unchecked `RuntimeException`/`Error` triggers rollback; checked exceptions by default may not roll back unless `rollbackFor` is configured. Rollback tests in the lab use `IllegalStateException` to avoid ambiguity. Do not claim every exception always rolls back.

## 8. Tricky Case: AFTER_COMMIT Can Still See Bound Resources

The `@TransactionalEventListener` Javadoc warns: during `AFTER_COMMIT`, `AFTER_ROLLBACK`, and `AFTER_COMPLETION`, the transaction has finished, yet its resources **may still be active/bound** to the thread during cleanup. Data-access code executing then may appear to join the old transaction, while **new changes are not committed**.

An error-prone example:

```java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT)
public void onPurchase(PurchaseCreatedEvent event) {
    auditRepository.save(new AuditRecord(event.ref()));
}
```

This is a cautionary snippet, not part of the runnable project. If a repository method with `REQUIRED` propagation joins the already-committed resource context, an INSERT issued after commit may have no subsequent commit as you expected. A test only verifying that Java method `save()` was called **does not prove a durable record exists**.

### 8.1. Intentional Solution: A New Transaction

Extract a separate Spring-managed bean:

```java
@Service
public class AuditWriter {
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void write(PurchaseCreatedEvent event) {
        jdbc.update(
                "insert into audit_entries(ref, phase) values (?, ?)",
                event.ref(), "AFTER_COMMIT");
    }
}
```

The snippet above is abbreviated; the full class with constructor injection is in the lab section. `REQUIRES_NEW` instructs Spring to suspend the outer resource context (if still bound) and open a new physical transaction, committing independently before the callback returns.

**Do not** place `@Transactional(REQUIRES_NEW)` on a private method and call `this.write(...)`; self-invocation bypasses the proxy. The lab makes `AuditWriter` a separate bean and injects it into the event listener.

### 8.2. AFTER_COMMIT Exceptions Do Not Undo the Original Transaction

If `AuditWriter.write(...)` fails, **the purchase transaction has already committed**. Depending on synchronization callback/exception handling, the exception might still reach the caller, but it cannot turn the purchase into uncommitted. Do not write naive retry code solely based on a service exception and end up creating duplicate purchases.

If the domain needs *exactly-once-looking* processing, use idempotency keys, deduplication, or a transactional outbox—an in-process callback is not a distributed transaction.

### 8.3. Connection Pool

`REQUIRES_NEW` can require an additional DB connection while the outer connection is still bound. An undersized pool or high concurrency can cause deadlocks or pool exhaustion. H2/Hikari in tests suffices for a single thread, while production needs proper sizing and monitoring under load.

## 9. Not Every Spring Event Has a Transaction

Spring application events do not require a transaction. A publisher can run from:

- A `@Scheduled` job without `@Transactional`.
- A REST controller calling `ApplicationEventPublisher` directly.
- A startup listener/runner.
- A message listener processing outside a transaction.
- An async/background callback detached from any thread-bound transaction.
- A test method calling `publishEvent` outside a Spring transactional service.

When there is no active transaction:

| Listener | Does It Run? |
| --- | --- |
| `@EventListener` (default synchronous) | Yes |
| `@TransactionalEventListener(AFTER_COMMIT)`, fallback=false | No |
| `@TransactionalEventListener(BEFORE_COMMIT)`, fallback=false | No |
| `@TransactionalEventListener(AFTER_ROLLBACK)`, fallback=false | No |
| `@TransactionalEventListener(AFTER_COMPLETION)`, fallback=false | No |
| `@TransactionalEventListener(..., fallbackExecution=true)` | Yes; runs immediately as fallback |

Do not enable `fallbackExecution=true` merely because a test lacks a transaction; define the business policy for when no transaction is present.

## 10. Choosing the Test Architecture

| Goal | Appropriate Test | What It Does Not Prove |
| --- | --- | --- |
| Listener handles event payload properly | Unit test listener method directly | Spring registration/phase |
| `@EventListener` is discovered by Spring | `@SpringBootTest` and publisher | DB commit |
| Transactional listener phase | Spring transaction + event publisher + real DB | Remote broker delivery |
| AFTER_COMMIT audit row is durable | DB query outside transaction after callback | Exactly-once external effects |
| Rollback writes no audit | Service throws + DB zero rows + phase probe | Ability to undo already-sent email |
| Event outside transaction | Publisher in non-transactional test | Transactions of real requests |
| Test-managed `@Transactional` | `TestTransaction.flagForCommit()/end()` | External systems if uncalled |
| Reliable Kafka/email dispatch | Outbox + broker/emulator/Testcontainers | Production availability across all failures |
| Reactive transaction phases | Reactor TransactionalEventPublisher integration | Imperative thread-bound semantics |

**This lesson tests transaction timing and does not need a web server.** We use `@SpringBootTest(webEnvironment=NONE)`, H2/JdbcTemplate, and a real transaction manager instead of Mockito faking commits.

## 11. Runnable Project: Spring Boot 3.3 + H2 + JDBC

### 11.1. Directory Tree

```text
transaction-events-lab/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/example/events/
    │   │   ├── EventLabApplication.java
    │   │   ├── PurchaseCreatedEvent.java
    │   │   ├── NoTxPingEvent.java
    │   │   ├── PurchaseService.java
    │   │   ├── AuditWriter.java
    │   │   ├── EventProbe.java
    │   │   └── PurchaseEventListeners.java
    │   └── resources/
    │       └── schema.sql
    └── test/java/example/events/
        └── PurchaseEventIntegrationTest.java
```

### 11.2. settings.gradle

```groovy
rootProject.name = 'transaction-events-lab'
```

### 11.3. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Because the JDBC starter includes `spring-tx`/JDBC, Spring Boot auto-configures an embedded H2 datasource, JdbcTemplate, and PlatformTransactionManager when eligible. In the main class, the lab enables `@EnableTransactionManagement` explicitly to highlight the proxy boundary.

**JPA is unnecessary** for this lesson: JDBC/H2 makes commit/rollback and connection independence explicit. If an application uses JPA, substitute repositories while keeping the corresponding transaction phase logic; when testing flush/constraints, invoke `EntityManager.flush()` explicitly.

### 11.4. schema.sql

**src/main/resources/schema.sql**

```sql
create table if not exists purchases (
    id bigint generated by default as identity primary key,
    ref varchar(120) not null
);

create table if not exists audit_entries (
    id bigint generated by default as identity primary key,
    ref varchar(120) not null,
    phase varchar(40) not null
);
```

Spring Boot SQL initialization with embedded H2 applies schema.sql when creating the application. Foreign keys are omitted to keep test cleanup straightforward.

In a production app with Flyway/Liquibase, **do not** use schema.sql to reinitialize a real DB as in this lab; use migrations and environment-appropriate schema initialization settings.

## 12. Main Application + Event Payload Records

### 12.1. EventLabApplication.java

**src/main/java/example/events/EventLabApplication.java**

```java
package example.events;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@SpringBootApplication
@EnableTransactionManagement
public class EventLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(
                EventLabApplication.class, args);
    }
}
```

### 12.2. PurchaseCreatedEvent.java

**src/main/java/example/events/PurchaseCreatedEvent.java**

```java
package example.events;

public record PurchaseCreatedEvent(String ref) {}
```

### 12.3. NoTxPingEvent.java

**src/main/java/example/events/NoTxPingEvent.java**

```java
package example.events;

public record NoTxPingEvent(String id) {}
```

Spring's `ApplicationEventPublisher.publishEvent(Object)` accepts any Java object as an event payload, including records. You do not need to extend `ApplicationEvent` for every domain event. Choosing immutable records prevents mutation between publication and callback, especially if event processing is deferred.

**Do not pass a JPA entity with lazy-loaded mutable state into an event and read it after the transaction** without good reason; records holding business IDs/references/immutable data are easier to test and avoid detached entity issues.

## 13. PurchaseService.java — Creating Transactions and Publishing Events

**src/main/java/example/events/PurchaseService.java**

```java
package example.events;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PurchaseService {

    private final JdbcTemplate jdbc;
    private final ApplicationEventPublisher events;

    public PurchaseService(
            JdbcTemplate jdbc,
            ApplicationEventPublisher events) {
        this.jdbc = jdbc;
        this.events = events;
    }

    @Transactional
    public void place(String ref) {
        insertAndPublish(ref);
    }

    @Transactional
    public void placeAndFail(String ref) {
        insertAndPublish(ref);
        throw new IllegalStateException(
                "forced rollback");
    }

    @Transactional
    public void placePair(String first, String second) {
        insertAndPublish(first);
        insertAndPublish(second);
    }

    @Transactional
    public void placePairAndFail(
            String first, String second) {
        insertAndPublish(first);
        insertAndPublish(second);
        throw new IllegalStateException(
                "forced rollback");
    }

    private void insertAndPublish(String ref) {
        jdbc.update(
                "insert into purchases(ref) values (?)",
                ref);
        events.publishEvent(
                new PurchaseCreatedEvent(ref));
    }
}
```

**Why is @Transactional placed on public methods?** JUnit injects the `PurchaseService` bean and calls public methods through the Spring proxy; the transaction interceptor opens a transaction before `insertAndPublish`. The private method is merely a helper **running inside the already-opened active transaction**, needing no annotation of its own. There is no self-invocation of an annotated public method here.

**Why use an unchecked exception?** `IllegalStateException` is a RuntimeException, which Spring rolls back by default. If a test uses a checked exception and forgets `rollbackFor`, behavior can differ.

**Why insert before the event?** The event carries the reference of data just written in the transaction, though not necessarily committed yet. Immediate listeners can observe the event before database commit. The AFTER_COMMIT transactional listener runs only once commit finishes successfully.

## 14. EventProbe.java — Observing Phases and Transaction Status

**src/main/java/example/events/EventProbe.java**

```java
package example.events;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Component
public class EventProbe {

    public record Mark(
            String phase,
            String ref,
            boolean transactionActive,
            long threadId) {}

    private final List<Mark> marks =
            new CopyOnWriteArrayList<>();

    public void mark(String phase, String ref) {
        marks.add(new Mark(
                phase,
                ref,
                TransactionSynchronizationManager
                        .isActualTransactionActive(),
                Thread.currentThread().getId()));
    }

    public long count(String phase, String ref) {
        return marks.stream()
                .filter(mark -> mark.phase().equals(phase))
                .filter(mark -> mark.ref().equals(ref))
                .count();
    }

    public List<String> phases(String ref) {
        return marks.stream()
                .filter(mark -> mark.ref().equals(ref))
                .map(Mark::phase)
                .toList();
    }

    public boolean transactionActiveAt(
            String phase, String ref) {
        return marks.stream()
                .filter(mark -> mark.phase().equals(phase))
                .filter(mark -> mark.ref().equals(ref))
                .findFirst()
                .orElseThrow()
                .transactionActive();
    }

    public long threadIdAt(
            String phase, String ref) {
        return marks.stream()
                .filter(mark -> mark.phase().equals(phase))
                .filter(mark -> mark.ref().equals(ref))
                .findFirst()
                .orElseThrow()
                .threadId();
    }

    public void clear() {
        marks.clear();
    }
}
```

`EventProbe` is strictly an observation tool for the demo, performing no DB or HTTP calls. `CopyOnWriteArrayList` prevents data races when reading observations across threads, though the lab uses synchronous event handlers.

### 14.1. Caution with transactionActiveAt in AFTER_COMMIT

`TransactionSynchronizationManager.isActualTransactionActive()` reflects the transaction status **bound to the thread at the moment of the call**, not “did commit succeed?” at the business level. After commit, resources may remain bound until cleanup; do not assert it must be false in AFTER_COMMIT.

The lesson only asserts `IMMEDIATE` is called with an active transaction in `place(...)` and inactive when published directly outside a transaction. Durable DB evidence in AFTER_COMMIT is verified via a JDBC query from outside the method.

### 14.2. Why Is threadId Recorded?

To verify the default synchronous path: an `@EventListener` receives the event while `publishEvent` is executing on the test/publisher thread. The test does not assert thread **name** (which can change); it compares `Thread.currentThread().getId()` with the mark recorded by the handler. If you enable `@Async` or a custom executor, this assertion no longer holds as a contract.

## 15. AuditWriter.java — REQUIRES_NEW After Commit

**src/main/java/example/events/AuditWriter.java**

```java
package example.events;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuditWriter {

    private final JdbcTemplate jdbc;

    public AuditWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void write(PurchaseCreatedEvent event) {
        jdbc.update(
                "insert into audit_entries(ref, phase) " +
                "values (?, ?)",
                event.ref(),
                "AFTER_COMMIT");
    }
}
```

The Spring AOP proxy can apply `REQUIRES_NEW` because `PurchaseEventListeners` injects **a separate Spring bean** and calls `auditWriter.write(event)`. Placing a private method on the listener and calling `this.write` directly would skip the new transaction annotation.

In the lab, the after-commit event is handled once the original transaction has finished. `REQUIRES_NEW` opens/commits a new physical transaction for the audit row. The test can query `audit_entries` after `service.place(...)` returns and observe the durable row.

**What it does not prove:** The new transaction can still fail, the connection pool can exhaust; the lab does not solve reliable remote event delivery or idempotency.

## 16. PurchaseEventListeners.java — All Four Phases

**src/main/java/example/events/PurchaseEventListeners.java**

```java
package example.events;

import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class PurchaseEventListeners {

    private final EventProbe probe;
    private final AuditWriter auditWriter;

    public PurchaseEventListeners(
            EventProbe probe,
            AuditWriter auditWriter) {
        this.probe = probe;
        this.auditWriter = auditWriter;
    }

    @EventListener
    public void immediate(PurchaseCreatedEvent event) {
        probe.mark("IMMEDIATE", event.ref());
    }

    @TransactionalEventListener(
            phase = TransactionPhase.BEFORE_COMMIT)
    public void beforeCommit(PurchaseCreatedEvent event) {
        probe.mark("BEFORE_COMMIT", event.ref());
    }

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(PurchaseCreatedEvent event) {
        auditWriter.write(event);
        probe.mark("AFTER_COMMIT", event.ref());
    }

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_ROLLBACK)
    public void afterRollback(PurchaseCreatedEvent event) {
        probe.mark("AFTER_ROLLBACK", event.ref());
    }

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMPLETION)
    public void afterCompletion(PurchaseCreatedEvent event) {
        probe.mark("AFTER_COMPLETION", event.ref());
    }

    @TransactionalEventListener(fallbackExecution = true)
    public void ping(NoTxPingEvent event) {
        probe.mark("FALLBACK_PING", event.id());
    }
}
```

The lab does not enable `@EnableAsync`, replace the ApplicationEventMulticaster, or configure an asynchronous executor. Therefore, the immediate listener runs synchronously, while the transactional listeners are invoked according to JDBC transaction phases.

**Do not assert a single fixed order between AFTER_COMMIT and AFTER_COMPLETION**: both relate to completion, and detailed ordering between listeners in the same phase can depend on registration/order. If the business requires handler ordering, use `@Order`/explicit orchestration rather than relying on incidental order on a dev machine as a contract.

### 16.1. Why Does ping Use a Separate Event Type?

A listener with `fallbackExecution=true` receives events both on transaction commit and directly when no transaction exists. To let unit/integration tests clearly observe “runs even without a transaction”, the lab uses a dedicated `NoTxPingEvent`, avoiding confusion with callback counts from `PurchaseCreatedEvent`.

### 16.2. Keep Remote Side Effects Out of Immediate Listeners

In this sample, the immediate listener only writes to the in-memory `EventProbe`. Putting email/webhook/Kafka sends there means a DB rollback **cannot undo** a message that already left the process. Use after-commit for best-effort notifications, or the outbox pattern when reliable delivery is required.

## 17. PurchaseEventIntegrationTest.java — Nine Scenarios

**src/test/java/example/events/PurchaseEventIntegrationTest.java**

```java
package example.events;

import java.util.List;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = "spring.sql.init.mode=always"
)
class PurchaseEventIntegrationTest {

    @Autowired
    PurchaseService service;

    @Autowired
    EventProbe probe;

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    ApplicationEventPublisher events;

    @BeforeEach
    void reset() {
        jdbc.update("delete from audit_entries");
        jdbc.update("delete from purchases");
        probe.clear();
    }

    @AfterEach
    void cleanUp() {
        jdbc.update("delete from audit_entries");
        jdbc.update("delete from purchases");
        probe.clear();
    }

    private long purchaseCount(String ref) {
        Long value = jdbc.queryForObject(
                "select count(*) from purchases where ref = ?",
                Long.class, ref);
        return value == null ? 0 : value;
    }

    private long auditCount(String ref) {
        Long value = jdbc.queryForObject(
                "select count(*) from audit_entries where ref = ?",
                Long.class, ref);
        return value == null ? 0 : value;
    }

    @Test
    void commitRunsCorrectPhasesAndPersistsAudit() {
        service.place("COMMIT-A");

        assertEquals(1L, purchaseCount("COMMIT-A"));
        assertEquals(1L, auditCount("COMMIT-A"));

        assertEquals(1L,
                probe.count("IMMEDIATE", "COMMIT-A"));
        assertEquals(1L,
                probe.count("BEFORE_COMMIT", "COMMIT-A"));
        assertEquals(1L,
                probe.count("AFTER_COMMIT", "COMMIT-A"));
        assertEquals(1L,
                probe.count("AFTER_COMPLETION", "COMMIT-A"));
        assertEquals(0L,
                probe.count("AFTER_ROLLBACK", "COMMIT-A"));

        assertTrue(probe.transactionActiveAt(
                "IMMEDIATE", "COMMIT-A"));
    }

    @Test
    void rollbackRunsRollbackNotCommitCallbacks() {
        IllegalStateException error = assertThrows(
                IllegalStateException.class,
                () -> service.placeAndFail("ROLLBACK-A"));

        assertEquals("forced rollback",
                error.getMessage());
        assertEquals(0L, purchaseCount("ROLLBACK-A"));
        assertEquals(0L, auditCount("ROLLBACK-A"));

        assertEquals(1L,
                probe.count("IMMEDIATE", "ROLLBACK-A"));
        assertEquals(0L,
                probe.count("BEFORE_COMMIT", "ROLLBACK-A"));
        assertEquals(0L,
                probe.count("AFTER_COMMIT", "ROLLBACK-A"));
        assertEquals(1L,
                probe.count("AFTER_ROLLBACK", "ROLLBACK-A"));
        assertEquals(1L,
                probe.count("AFTER_COMPLETION", "ROLLBACK-A"));
    }

    @Test
    void immediateRunsBeforeBeforeCommitAndAfterCommit() {
        service.place("ORDERING-A");

        List<String> phases = probe.phases("ORDERING-A");

        int immediate = phases.indexOf("IMMEDIATE");
        int beforeCommit = phases.indexOf("BEFORE_COMMIT");
        int afterCommit = phases.indexOf("AFTER_COMMIT");

        assertTrue(immediate >= 0);
        assertTrue(beforeCommit > immediate);
        assertTrue(afterCommit > beforeCommit);

        // Do not assume a fixed relative order for
        // AFTER_COMMIT versus AFTER_COMPLETION.
    }

    @Test
    void outsideTransactionOnlyImmediateListenerRuns() {
        events.publishEvent(
                new PurchaseCreatedEvent("NO-TX-A"));

        assertEquals(1L,
                probe.count("IMMEDIATE", "NO-TX-A"));
        assertFalse(probe.transactionActiveAt(
                "IMMEDIATE", "NO-TX-A"));

        assertEquals(0L,
                probe.count("BEFORE_COMMIT", "NO-TX-A"));
        assertEquals(0L,
                probe.count("AFTER_COMMIT", "NO-TX-A"));
        assertEquals(0L,
                probe.count("AFTER_ROLLBACK", "NO-TX-A"));
        assertEquals(0L,
                probe.count("AFTER_COMPLETION", "NO-TX-A"));
        assertEquals(0L, auditCount("NO-TX-A"));
    }

    @Test
    void fallbackExecutionHandlesEventWithoutTx() {
        events.publishEvent(
                new NoTxPingEvent("PING-A"));

        assertEquals(1L,
                probe.count("FALLBACK_PING", "PING-A"));
        assertFalse(probe.transactionActiveAt(
                "FALLBACK_PING", "PING-A"));
    }

    @Test
    void afterCommitAuditIsDurableInNewTransaction() {
        service.place("AUDIT-A");

        assertEquals(1L, purchaseCount("AUDIT-A"));
        assertEquals(1L, auditCount("AUDIT-A"));

        Integer rows = jdbc.queryForObject(
                "select count(*) from audit_entries " +
                "where ref = ? and phase = ?",
                Integer.class,
                "AUDIT-A", "AFTER_COMMIT");

        assertEquals(Integer.valueOf(1), rows);
        assertEquals(1L,
                probe.count("AFTER_COMMIT", "AUDIT-A"));
    }

    @Test
    void twoEventsInOneCommitProduceTwoAudits() {
        service.placePair("PAIR-A", "PAIR-B");

        assertEquals(1L, purchaseCount("PAIR-A"));
        assertEquals(1L, purchaseCount("PAIR-B"));

        assertEquals(1L, auditCount("PAIR-A"));
        assertEquals(1L, auditCount("PAIR-B"));

        assertEquals(1L,
                probe.count("AFTER_COMMIT", "PAIR-A"));
        assertEquals(1L,
                probe.count("AFTER_COMMIT", "PAIR-B"));
    }

    @Test
    void rolledBackPairDoesNotWriteAudit() {
        assertThrows(
                IllegalStateException.class,
                () -> service.placePairAndFail(
                        "PAIR-X", "PAIR-Y"));

        assertEquals(0L, purchaseCount("PAIR-X"));
        assertEquals(0L, purchaseCount("PAIR-Y"));

        assertEquals(0L, auditCount("PAIR-X"));
        assertEquals(0L, auditCount("PAIR-Y"));

        assertEquals(1L,
                probe.count("IMMEDIATE", "PAIR-X"));
        assertEquals(1L,
                probe.count("IMMEDIATE", "PAIR-Y"));
        assertEquals(1L,
                probe.count("AFTER_ROLLBACK", "PAIR-X"));
        assertEquals(1L,
                probe.count("AFTER_ROLLBACK", "PAIR-Y"));
        assertEquals(0L,
                probe.count("AFTER_COMMIT", "PAIR-X"));
        assertEquals(0L,
                probe.count("AFTER_COMMIT", "PAIR-Y"));
    }

    @Test
    void ordinaryListenerIsSynchronousByDefault() {
        long callerThreadId =
                Thread.currentThread().getId();

        events.publishEvent(
                new PurchaseCreatedEvent("SYNC-A"));

        assertEquals(1L,
                probe.count("IMMEDIATE", "SYNC-A"));
        assertEquals(callerThreadId,
                probe.threadIdAt("IMMEDIATE", "SYNC-A"));
        assertEquals(0L, auditCount("SYNC-A"));
    }
}
```

### 17.1. Evidence of Each Test

| Test | Observable Asserted | Bug It Can Catch |
| --- | --- | --- |
| `commitRunsCorrectPhasesAndPersistsAudit` | Purchase + audit rows, 4 commit phases | Wrong listener phase or missing proxy |
| `rollbackRunsRollbackNotCommitCallbacks` | Database rollback, immediate/rollback/completion accurate | Treating event as committed despite rollback |
| `immediateRunsBeforeBeforeCommitAndAfterCommit` | Order IMMEDIATE < BEFORE_COMMIT < AFTER_COMMIT | Event handled too early or too late |
| `outsideTransactionOnlyImmediateListenerRuns` | No-tx event does not trigger default transactional listeners | Assuming afterCommit runs without a tx |
| `fallbackExecutionHandlesEventWithoutTx` | No-tx ping handled when fallback=true | Misunderstanding fallback semantics |
| `afterCommitAuditIsDurableInNewTransaction` | Audit row readable via JDBC after method returns | Missing REQUIRES_NEW, non-durable data |
| `twoEventsInOneCommitProduceTwoAudits` | Two events in same tx, two callbacks after one commit | Processing only one event / lost event |
| `rolledBackPairDoesNotWriteAudit` | Two events roll back, no audits | Pre-commit side effects |
| `ordinaryListenerIsSynchronousByDefault` | Same caller thread, immediate callback before publishEvent returns | Unintended switch to async multicaster |

### 17.2. Why Does the Test Class Not Have @Transactional?

This is **the most important point of the lesson**. Do not place `@Transactional` on the test class or method. `PurchaseService.place(...)` opens and commits the **service proxy's** transaction before the test method resumes. Thus, after `service.place` returns, the test can query the DB and assert that AFTER_COMMIT callbacks ran.

If you put `@Transactional` on the JUnit test, Spring TestContext opens a **test-managed transaction** by default and rolls it back after the test. A service with REQUIRED propagation joins that transaction; `AFTER_COMMIT` is not invoked before the test's assertions, and may never run when the test framework rolls back. “AFTER_COMMIT did not run” failures like this are **false negatives from test setup**, not production code bugs.

### 17.3. Why Query the DB Outside the Service Transaction?

Once `service.place` returns, the outer transaction interceptor has finished. A `JdbcTemplate` query executed in a test without `@Transactional` reads committed data, avoiding reading “uncommitted data of the open transaction itself” and mistaking it for durable.

### 17.4. Why Include Both Rollback and Commit?

If tests only verify `@EventListener` is called, a rollback scenario still passes because the listener runs immediately. If tests only verify the `@TransactionalEventListener` commit path, a listener accidentally firing on rollback might slip past. The lesson checks both directions.

### 17.5. Why Include an Outside-Transaction Test?

Many entry points do not open a transaction. With default transactional listeners, publishing directly outside a transaction produces no callback. That is the intended contract behavior, not a broken event publisher.

## 18. Commands to Run the Project

Requires JDK 17 and a Gradle Wrapper compatible with Spring Boot 3.3 (e.g., Gradle 8.7). If the wrapper is missing, generate it with an appropriate Gradle version and commit wrapper artifacts; do not assume `./gradlew` appears automatically when copying source only.

Linux/macOS:

```bash
./gradlew test
./gradlew test --tests example.events.PurchaseEventIntegrationTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat test --tests example.events.PurchaseEventIntegrationTest
```

**Expected result:** 9 JUnit tests pass when sources are placed in the proper packages and Spring Boot 3.3 dependencies and embedded H2 work. No Docker or external broker is needed. The sample prints no fixed stdout; never fabricate a “BUILD SUCCESSFUL” log as if it ran. Read the real Gradle test report to report executed/pass/fail/skipped counts.

Note that H2 uses an in-memory database and schema.sql to teach the JDBC commit boundary. It does not verify PostgreSQL isolation levels, MySQL replication, SQL Server triggers, or broker ack semantics. If the real application uses a different DB, add provider-specific integration tests (Testcontainers when appropriate).

## 19. What If You Must Use @Transactional on a JUnit Test?

Spring TestContext rolls back test-managed transactions by default. If you need to control commit directly inside a test, Spring provides `TestTransaction`.

Instructional example (not part of the runnable class):

```java
@Transactional
@Test
void commitExplicitlyDuringTest() {
    service.place("CONTROLLED-A");

    // AFTER_COMMIT is not expected to run yet
    // while the test-managed transaction is active.

    TestTransaction.flagForCommit();
    TestTransaction.end();

    // Now the test transaction has ended with commit.
    // AFTER_COMMIT may be asserted here.
    assertEquals(1L, auditCount("CONTROLLED-A"));
}
```

Required imports: `org.springframework.test.context.transaction.TestTransaction`, `org.springframework.transaction.annotation.Transactional`, and JUnit Test. The snippet assumes service/probe/query helpers are injected from the Spring context and test-managed transactions are enabled. If you need to continue work in a new test transaction, call `TestTransaction.start()` per contract.

### 19.1. @Commit and @Rollback(false)

`@Commit` or `@Rollback(false)` makes the test transaction commit **when the test method ends**; if you assert AFTER_COMMIT **inside** the method before it finishes, the callback has not run yet. You can use `@AfterTransaction` to assert after the test transaction ends, or control it with `TestTransaction.end()`.

### 19.2. @BeforeEach and @AfterEach in Transactional Tests

If a test method has a test-managed transaction, JUnit `@BeforeEach`/`@AfterEach` typically run **inside** the test transaction. Do not use them assuming you are observing committed DB data outside the transaction. Use `@BeforeTransaction`/`@AfterTransaction` when you need boundaries outside the test transaction.

### 19.3. @DataJpaTest Is Not the Full Application

`@DataJpaTest` normally uses test-managed rollback and loads only the JPA slice. It may not scan service/event listener beans like a full `@SpringBootTest`. If testing `@TransactionalEventListener` AFTER_COMMIT in a JPA slice, import appropriate beans and manage the commit boundary explicitly. This lab chose JDBC + full context to avoid setup confusion.

## 20. Listener Ordering: Phase Order Differs from Listener Order

In a normal commit:

1. Synchronous `@EventListener` receives the event immediately at publish time.
2. `BEFORE_COMMIT` runs before commit.
3. Transaction manager commits the database.
4. `AFTER_COMMIT` is invoked.
5. `AFTER_COMPLETION` runs upon completion.

However, ordering **between two listeners in the same phase** can be affected by Spring listener ordering. When a specific order is needed, consider `@Order`, processing policy, and dependencies. `@Order` does not turn two transaction synchronizations into a distributed atomic workflow.

### 20.1. Listener A Republishes Event B

`@EventListener` can return an event object for Spring to publish onward (with certain limits; async listeners have caveats). That creates an event chain. In complex systems, nested event publication can increase event counts or make listener order hard to follow; tests should assert the expected event graph, not just the number of business calls.

### 20.2. Listener Exceptions

- A synchronous `@EventListener` throwing an unchecked exception before commit can fail the publisher method and roll back.
- A `BEFORE_COMMIT` callback throwing can abort commit and trigger rollback.
- An `AFTER_COMMIT` failure happens **after commit**; the original DB transaction cannot be undone.
- `AFTER_COMPLETION` errors may be logged instead of propagated depending on the transaction synchronization implementation; do not assume every callback exception surfaces to the caller.
- Async `@EventListener` exceptions normally do not propagate to the publisher like synchronous listeners.

Do not design tests solely around matching an exception message string while ignoring the final database state.

## 21. @Async Changes Testing Determinism

By default, Spring's event multicaster is synchronous. If you use:

```java
@Async
@EventListener
public void asyncHandle(PurchaseCreatedEvent event) {
    // Executes on an executor thread when @Async is enabled.
}
```

this is an illustrative snippet requiring corresponding `@EnableAsync`/executor configuration. It is **not** runnable lab code, and introduces key differences:

- Tests must not assert the callback completed **immediately after** `publishEvent` when async.
- The publisher's ThreadLocal transaction context **does not automatically propagate** to the executor thread.
- Exceptions do not propagate back to the publisher like synchronous callbacks.
- Use synchronization primitives/Awaitility with finite timeouts and thread-safe event observations.
- Do not use `Thread.sleep(2000)` as proof the callback ran; CI can be slow.
- Do not confuse async in-process execution with reliable durable message processing.

With `@TransactionalEventListener`, understand Spring's transaction-bound listener registration/execution and executor compatibility; do not casually add `@Async` to “avoid blocking the commit thread” without testing thread and transaction boundaries.

## 22. TransactionalEventListener in Reactive Transactions

This lab uses **imperative JDBC**, `PlatformTransactionManager`, and thread-bound transaction synchronizations.

Since Spring Framework 6.1, transactional event listeners also support **reactive transactions** using `ReactiveTransactionManager`, but Reactor's transaction context is unlike ThreadLocal. When publishing inside a reactive pipeline, use the appropriate mechanism (e.g., `TransactionalEventPublisher`) to carry the transaction context in the event source when needed.

**Do not copy this JDBC test to R2DBC/WebFlux and assume transaction callbacks behave identically.**

### 22.1. Reactor Context Is Not Servlet ThreadLocal

Reactive transaction state flows through the Reactor Context, not a fixed Java thread. Calling `publishEvent` directly inside a callback running on an arbitrary scheduler may fail to carry the transaction context. Design context propagation, publish within the reactive chain, and test with Reactor `StepVerifier` alongside a reactive transaction manager.

### 22.2. What Does a Complete R2DBC Test Need?

- An R2DBC connection factory/database with transaction support.
- `R2dbcTransactionManager` or an appropriate reactive transaction manager.
- Reactive repository/DatabaseClient operations.
- `TransactionalEventPublisher`/publisher logic matching the version.
- Assertions on events after reactive publisher commit/rollback, not merely after constructing a Mono.
- Multi-subscription isolation and virtual/real scheduler considerations.
- Negative tests for missing transaction context.

Do not claim `@TransactionalEventListener` is limited to JDBC since Spring Framework 6.1; the distinction is **how the transaction context is carried**.

## 23. Events and Observability

Because the parent group is **Events and Observability**, observe the lifecycle via metrics/logs/traces rather than testing business rows alone.

Example metric contract:

| Metric | Type | Bounded Tags | Meaning |
| --- | --- | --- | --- |
| `purchase.events.published` | Counter | `event=created` | Number of publishes in-process |
| `purchase.events.committed` | Counter | `event=created` | Number of AFTER_COMMIT callbacks |
| `purchase.events.rollback` | Counter | `event=created` | Number of AFTER_ROLLBACK callbacks |
| `purchase.events.handler.duration` | Timer | `phase=after_commit|rollback` | Listener processing latency |
| `purchase.events.failures` | Counter | `phase,exception_type` from a finite set | Callback failures |

**Do not equate published count with committed count.** Published increments right before commit; the transaction can still roll back. Do not put `ref`, `orderId`, email, or requestId into metric tags due to very high cardinality; use structured logs/traces when correlating a specific event.

### 23.1. Do Not Log Sensitive Payloads

Log only event IDs, references masked per policy, phases, and safe correlation IDs. Do not log tokens, PII, or full payment/customer payloads. When diagnosing an AFTER_COMMIT failure, log the event ID + exception type + correlation trace, avoiding messages containing secrets.

### 23.2. Metrics Do Not Prove Durable Event Delivery

A post-commit counter is an **in-process observation** and does not prove downstream Kafka/email received and acknowledged the event. Add broker producer/consumer integration tests or outbox relay tests as appropriate.

### 23.3. Trace Boundaries

A synchronous listener usually executes within the publisher's execution/correlation context. Across an async executor or broker, explicit trace/context propagation is required; never assume ThreadLocal trace MDC automatically crosses every thread/queue. Test correlation at boundaries according to your actual observability stack.

## 24. Transactional Outbox: When afterCommit Is Still Not Enough

Scenario:

1. Purchase transaction commits.
2. `AFTER_COMMIT` callback prepares to send to Kafka.
3. JVM crashes before sending.
4. Database has the purchase, but no Kafka event exists.

`@TransactionalEventListener(AFTER_COMMIT)` prevents **sending before commit**, yet cannot close the window between **committed and not yet sent**.

Transactional outbox replaces it with:

```text
Begin database transaction
    |
    +-- INSERT purchases(...)
    +-- INSERT outbox_event(
            id, type, payload, state='NEW')
    |
Commit both rows atomically
    |
    v
Outbox relay reads NEW events
    |
    +-- sends to broker with retry
    +-- marks processed/delivered
    |
    v
Idempotent consumer de-duplicates event id
```

This is a design sketch; there is no outbox code in the runnable lab. It requires an extra repository/schema, relay worker, backoff/retries, duplicate handling, dead-letter policy, and monitoring. Never say “outbox is exactly-once by default”: a relay can send duplicates if it crashes after the broker send but before the DB ack; consumers must be idempotent or use appropriate delivery mechanisms.

### 24.1. When Is afterCommit Enough?

- Best-effort in-process cache invalidation.
- Optional notifications that business policy allows losing.
- Noncritical local observations.
- Side effects backed by a repair path or periodic reconciliation.

### 24.2. When Should You Prefer an Outbox?

- Creating external invoice/payment/shipping commands that require delivery.
- Syncing critical business data to a message broker.
- Legal/audit guarantees around event processing.
- Retry across process restarts and reconciliation capability.

Do not merely swap `@EventListener` for `@TransactionalEventListener` and consider all consistency/distributed delivery problems solved.

## 25. Pitfalls That Cause False-Positive Tests

### 25.1. @Transactional on a Test Method Rolls Back by Default

`@SpringBootTest @Transactional @Test` creates a test-managed transaction. A `@Transactional(REQUIRED)` service joins the test's transaction. `AFTER_COMMIT` does not run until commit; the test framework rolls back by default. Hence asserting afterCommit right after the service call inside the method usually fails.

**Fix:** remove `@Transactional` from commit integration tests, or use `TestTransaction.flagForCommit()/end()`, or `@Commit` + `@AfterTransaction`.

### 25.2. Mocking ApplicationEventPublisher

Mockito `verify(events).publishEvent(...)` only proves the service called the publisher method; it does not prove Spring registered listeners, transaction phases, JDBC commit, or callback order. Use a real ApplicationContext and transaction manager when testing transaction-bound behavior.

### 25.3. Calling the Listener Method Directly in Tests

`listeners.afterCommit(event)` executes the Java method directly, bypassing Spring transactional synchronization. This unit test only verifies handler business logic; it does **not** prove `@TransactionalEventListener` is applied.

### 25.4. Asserting Only Callback Count

An incremented `afterCommit` count does not prove the audit row is durable if code writes to the DB in a post-commit resource context without `REQUIRES_NEW`. Read the audit row **after the service transaction finishes**, using JDBC outside the transaction.

### 25.5. Testing Only Commit Without Testing Rollback

If `@EventListener` is used for external sends, the commit test still passes. A rollback test reveals that the side effect can fire before DB rollback. Cover both positive and negative paths.

### 25.6. Forgetting fallbackExecution

Publishing outside a tx with a default transactional listener skips invocation. A test waiting forever for a callback because there is no transaction is a misconfigured test setup. If business allows no-tx events, enable `fallbackExecution=true` intentionally and test it separately.

### 25.7. @Transactional Self-Invocation

Calling a public annotated method from within the same class without going through the proxy can fail to open an outer tx. Put transaction boundaries on a Spring bean and test through the injected service.

### 25.8. Confusing BEFORE_COMMIT with Guaranteed Commit

`BEFORE_COMMIT` can run right before a DB commit failure. Do not dispatch irreversible external effects in this phase and label them “after commit only”.

### 25.9. Assuming Every Event Is Asynchronous

`@EventListener` is synchronous by default. If a test expects async callbacks, check whether the app actually uses a custom executor/`@Async`. Do not add arbitrary sleeps to synchronous tests.

### 25.10. Forgetting Method Rollback Rules

Checked exceptions by default may not roll back. Throw `IllegalStateException` or specify `rollbackFor` explicitly per contract in tests. Do not blame the listener if the transaction actually committed due to another rollback rule.

### 25.11. Writing to the DB from AFTER_COMMIT with REQUIRED

The callback can see resources still bound even though the original tx committed; new writes may not commit. Extract a separate `REQUIRES_NEW` bean and verify via DB rows, not just a Java mock call.

### 25.12. EventProbe State Leaking Across Tests

Spring ApplicationContext is cached; singleton `EventProbe` keeps marks from earlier tests. Clear it in `@BeforeEach`/`@AfterEach` and clean up the DB. Do not rely on test execution order.

### 25.13. Parallel Tests Sharing Database/Probe

One test can delete another test's observations/rows inside `@AfterEach`. The lab runs test methods sequentially by default. If enabling JUnit parallel execution, use per-test isolation (DB schema/container, probe scope) or `@Execution(SAME_THREAD)`, rather than “fixing” with sleep.

### 25.14. @Async Loses ThreadLocal Transactions

When using an executor, the publisher's thread-bound tx does not follow the listener, and errors may not return to the publisher. Do not casually combine `@Async` with transactional callbacks without testing propagation and side effects.

### 25.15. Treating In-Process Events as a Distributed Queue

Spring application events only communicate between beans in the same ApplicationContext/process. There are no durable broker offsets, delivery acks, retries, or persisted queues by default.

## 26. Debugging Mismatched Test Results

| Symptom | Likely Cause | How to Check |
| --- | --- | --- |
| IMMEDIATE does not run | Listener is not a Spring bean, wrong event type | `@Component`, package scan, `publishEvent` |
| IMMEDIATE runs despite DB rollback | Expected synchronous semantics | Use AFTER_COMMIT for commit-dependent work |
| AFTER_COMMIT does not run | No active tx, rollback, `@Transactional` test auto-rollback | Tx boundary, rollback rules, `TestTransaction` |
| AFTER_COMMIT runs when rollback was expected | Checked exception didn't roll back, exception caught | Spring rollback rules / tx status |
| BEFORE_COMMIT does not run | Early rollback or no active transaction | Service proxy / transaction manager |
| AFTER_ROLLBACK does not run | Transaction committed or event outside tx | Check actual outcome |
| AFTER_COMPLETION runs on rollback too | Expected semantics | Do not treat completion as success |
| Fallback listener runs without tx | `fallbackExecution=true` | Expected contract |
| AuditWriter writes row but DB doesn't show it | No new tx from AFTER_COMMIT | `REQUIRES_NEW` on separate Spring bean |
| Audit row appears twice | Event published twice, retries/duplicates | Event IDs, idempotency |
| Context test logs committed yet DB is empty | Test-managed transaction hasn't committed | `@Transactional` test, `TestTransaction` |
| Service `@Transactional` doesn't activate | Self-invocation/private method/new object | Spring AOP proxy |
| Event doesn't switch threads | `@EventListener` is synchronous | Default behavior; add `@Async` if needed |
| Async listener doesn't see transaction | ThreadLocal doesn't propagate | Context propagation/design |
| AFTER_COMMIT errors then retry creates duplicates | Purchase already committed before callback failed | Idempotency/outbox |
| Random test failures in parallel | Shared DB/Probe cleanup races | Disable parallel / isolate |
| H2 schema missing | `schema.sql`/SQL init misconfigured | `spring.sql.init.mode`/Boot logs |
| Duplicate application contexts | TestContext cache, multiple beans | Component scan/configuration |
| Event value mutated before callback | Mutable shared event payload | Immutable record/IDs |
| Kafka misses event even though AFTER_COMMIT ran | Remote send failure / process crash | Outbox, broker integration test |

### 26.1. Transaction Debugging Logs

In a test profile (not production), you can enable:

```properties
logging.level.org.springframework.transaction=TRACE
logging.level.org.springframework.jdbc=DEBUG
logging.level.org.springframework.context.event=DEBUG
```

Logs reveal commit/rollback and event multicaster flow. Do not enable overly broad logging in production if it exposes SQL params, event payloads, PII, or secrets. Pair logs with DB final-state assertions rather than using logs as a replacement.

### 26.2. Why Not Assert Fixed Elapsed Time?

In synchronous tests, listeners run immediately, yet commit/callback durations depend on DB/JVM/CI scheduling. Tests measure **observable phase counts and persisted data**, rather than calling `Thread.sleep(100)` and assuming callbacks must have completed.

## 27. Testing with Multiple Transaction Managers

The lab only has one H2 DataSource/transaction manager. Larger applications may have:

- A PostgreSQL database and a Redis cache.
- Two DataSources with two PlatformTransactionManagers.
- JPA + a Kafka transaction manager.
- A separate reactive transaction manager.

`@Transactional` must select the right manager, e.g. `@Transactional(transactionManager="ordersTransactionManager")`; transactional event phases bind to the **current transaction context**, which does not mean all external resources commit atomically together.

If a service has a nested method using `REQUIRES_NEW` on a different transaction manager, callbacks can bind to the inner or outer transaction depending on where `publishEvent` is called. Tests must identify **which transaction the event is bound to** and never assume every database/broker commits simultaneously.

### 27.1. REQUIRED, REQUIRES_NEW, and NESTED Propagation

| Propagation | General Meaning | Effect on Events |
| --- | --- | --- |
| `REQUIRED` | Join existing tx or create a new one | Listener binds to the enclosing transaction |
| `REQUIRES_NEW` | Suspend existing tx and open an independent one | Inner tx commit/rollback phases differ from outer |
| `NESTED` | Savepoint-based nested transaction if manager supports | Savepoint rollback doesn't always match outer completion events |
| `SUPPORTS` | Join if tx exists, otherwise run no-tx | Event may be skipped by transactional listeners |
| `NOT_SUPPORTED` | Suspend transaction, run outside tx | Default transactional listeners skipped |

These are Spring transaction propagation concepts; exact support depends on the transaction manager. Do not tweak propagation solely to make an event test pass; design commit boundaries around the business contract.

## 28. Practical Exercises

1. **Change AFTER_COMMIT to `@EventListener`:** run the rollback test and observe that the audit can still be written despite purchase rollback if the audit writer opens `REQUIRES_NEW`. Explain why pre-commit side effects are dangerous.
2. **Remove REQUIRES_NEW:** switch `AuditWriter.write` to `REQUIRED` propagation, run the audit durability test; verify the actual row after commit, not just that the handler was invoked.
3. **Add `@Transactional` to the test class:** the commit test may miss AFTER_COMMIT before assertions. Revert it or use `TestTransaction`.
4. **Use `TestTransaction`:** open a test-managed tx, call the service, invoke `flagForCommit()/end()`, and assert callbacks after `end()`.
5. **Switch exception to a checked exception:** observe default rollback rules, then add `rollbackFor` if the business requires rollback.
6. **Remove `@Transactional` on `PurchaseService.place`:** publish events without an enclosing transaction; immediate still runs, default transactional listeners skip.
7. **Enable `fallbackExecution` on a `PurchaseCreatedEvent` listener:** publish a no-tx event and observe the callback runs immediately; assess business risk.
8. **Throw inside the immediate listener:** experiment in a sandbox and watch the transaction roll back from an unchecked exception; never do this in production.
9. **Throw inside the AFTER_COMMIT listener:** verify the purchase is already committed even though the caller may see an exception; add a retry/idempotency strategy.
10. **Convert the event record into a mutable class:** mutate fields after publish before commit, observe callbacks seeing altered payloads; restore the immutable record.
11. **Two events in one transaction:** verify both produce audits only on commit and produce none on rollback.
12. **Add `@Order` to two listeners in the same phase:** assert ordering only when it is truly a business contract; do not rely on random registration order.
13. **Enable `@Async` on a listener:** write tests using `CountDownLatch`/timeout, and check propagation and exception policies.
14. **Use JPA instead of JDBC:** add Spring Data JPA/H2, handle flush/transaction boundaries; do not rely solely on `@DataJpaTest` auto-rollback.
15. **Add Micrometer counters:** distinguish `events.published` from `events.committed` and `events.rollback` with bounded tags.
16. **Add an outbox:** persist purchase and outbox rows in the same SQL transaction, write an idempotent relay and crash/retry integration tests.
17. **Multi-data-source:** identify which transaction manager an event binds to, simulating commit A/rollback B.
18. **Reactive R2DBC:** use `TransactionalEventPublisher` with Reactor context and `StepVerifier`.
19. **Publish after transaction in the service caller:** distinguish “code placed after `service.place` returns” from callbacks scheduled by transaction synchronization.
20. **Test a real DB provider:** run PostgreSQL Testcontainers to verify production-provider transaction isolation and constraints.

## 29. QA Checklist

- [ ] Know whether the event is published inside or outside a transaction.
- [ ] Verified `@EventListener` immediate behavior under synchronous config.
- [ ] Default `@TransactionalEventListener` understood as AFTER_COMMIT.
- [ ] Tested both commit and rollback, not only success.
- [ ] BEFORE_COMMIT is not treated as commit guaranteed.
- [ ] AFTER_ROLLBACK runs only on actual rollback.
- [ ] AFTER_COMPLETION runs on both commit and rollback.
- [ ] No-tx events with fallback=false trigger no transactional callbacks.
- [ ] `fallbackExecution=true` is enabled intentionally when no-tx is permitted.
- [ ] Service `@Transactional` is invoked via a Spring-managed bean proxy.
- [ ] No self-invocation or private transactional methods used to open a tx.
- [ ] Checked/unchecked exception rollback rules are well understood.
- [ ] Post-commit audit writes use a separate `REQUIRES_NEW` bean and are verified as DB-durable.
- [ ] Do not call `repository.save` inside AFTER_COMMIT assuming it commits automatically.
- [ ] Do not assume an AFTER_COMMIT failure rolls back the original purchase.
- [ ] Tests lack `@Transactional` auto-rollback when asserting real commits.
- [ ] If using test-managed transactions, use `TestTransaction` or `@AfterTransaction` properly.
- [ ] DB rows and event probes are reset between tests.
- [ ] Tests do not depend on method execution order.
- [ ] Parallel tests do not wipe shared DB/probe state unintentionally.
- [ ] Tests distinguish in-process events from durable broker delivery.
- [ ] Do not use `Thread.sleep` as an oracle for synchronous callbacks.
- [ ] `@Async`/custom multicasters are tested separately when used.
- [ ] Transaction-bound listeners in reactive flows have proper Reactor context.
- [ ] Do not attach unbounded user/order IDs directly as metric tags.
- [ ] Production event processing includes idempotency/retry/outbox when needed.
- [ ] Test reports state actual executed/passed/failed/skipped counts, never claiming expected as executed.
- [ ] Do not treat H2 tests as proof that every database/broker transaction behaves identically.

## 30. Listener Selection and Testing Guide

```text
When should the event be reacted to?
      |
      +-- Right when the method publishes?
      |      -> @EventListener.
      |         Test synchronous invocation + rollback case.
      |
      +-- Only if the transaction commits?
      |      -> @TransactionalEventListener(AFTER_COMMIT).
      |         Test commit/rollback and durability.
      |
      +-- Before commit?
      |      -> BEFORE_COMMIT.
      |         Test no guarantee commit succeeds afterward.
      |
      +-- Only on rollback?
      |      -> AFTER_ROLLBACK.
      |
      +-- After any completion?
      |      -> AFTER_COMPLETION.
      |
      +-- Might the event be published outside a tx?
      |      -> fallbackExecution=true if business approves,
      |         otherwise require transaction and test missing-tx.
      |
      +-- Need to write DB from completion callback?
      |      -> Separate @Transactional(REQUIRES_NEW) bean.
      |
      +-- Need messages delivered across crashes?
             -> Transactional outbox + relay + idempotency.
```

**Conclusion:** `@EventListener` verifies **an event was published**, not that the database committed. `@TransactionalEventListener` binds execution to transaction phases, defaulting to `AFTER_COMMIT`. To test accurately, use **real transactions**, cover commit/rollback/no-tx paths, read **committed database state**, and avoid test-managed auto-rollback hiding commit callbacks. When writing data after commit, use `REQUIRES_NEW` on a separate Spring bean. For critical cross-process messages, pair with an outbox/idempotency rather than relying solely on internal listeners.

## 31. Official Documentation

- Spring Framework — Transaction-bound Events and the four phases: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Framework 6.1 Javadoc — `@TransactionalEventListener`, fallback, after-commit resource caveat: https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html
- Spring Framework — Annotation-based Event Listeners, sync/async behavior: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework — Declarative Transactions and propagation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — Transaction Propagation REQUIRED, REQUIRES_NEW, NESTED: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework — TestContext transaction management, `@Commit`, `@Rollback`, `TestTransaction`: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html
- Spring Framework — TransactionSynchronizationManager API: https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html
- Spring Framework — TransactionSynchronization API: https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html
- Spring Framework — ApplicationEventPublisher API: https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Framework — Reactive TransactionalEventPublisher: https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/transaction/reactive/TransactionalEventPublisher.html
- Spring Boot 3.3 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot 3.3 — SQL database initialization: https://docs.spring.io/spring-boot/3.3/reference/how-to/data-initialization.html
- JUnit Jupiter — Lifecycle and integration testing: https://docs.junit.org/current/user-guide/
