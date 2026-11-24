# Limits of Default Rollback for Behaviors Requiring Real Commit in Spring Data JPA

## 1. Why Does This Topic Matter?

In Spring Boot, a repository test can pass completely under `@DataJpaTest`: the entity is saved, flushed, queried back via the repository, and every assertion holds. However, the production flow can still fail **at transaction commit time**, or a critical behavior **only triggers after commit**. If tests always roll back, those behaviors may never actually execute.

Classic examples:

- `@TransactionalEventListener(phase = AFTER_COMMIT)` listeners run only when the transaction **commits successfully**.
- Some database constraints—especially **DEFERRABLE constraints** in PostgreSQL—are evaluated at commit time, not necessarily during an earlier `flush`.
- Other transactions, consumers, or connections **do not necessarily see** data that was flushed yet uncommitted.
- Outbox/CDC relays, external audits, notifications, or jobs depending on committed rows typically require a commit before another process observes them.
- A `@Transactional(propagation = REQUIRES_NEW)` method can commit its own transaction **even if** the test's outer transaction subsequently rolls back.
- An HTTP request hitting the real app in `@SpringBootTest(webEnvironment = RANDOM_PORT)` runs on a separate server thread/transaction; `@Transactional` on the test method **does not guarantee** rolling back server-side writes.

This lesson helps learners answer: **where does default rollback protect tests from leftover data, and what production behaviors requiring real commits can it hide?**

### Objectives

After this lesson, you will be able to:

1. Explain how Spring TestContext's **test-managed transaction** differs from service/application-managed transactions.
2. Identify when `@DataJpaTest` rolls back by default versus when `@SpringBootTest` does or does not have a test transaction.
3. Distinguish `save`, `flush`, `saveAndFlush`, `commit`, and `rollback`.
4. Verify that a row **truly committed and is visible outside the test transaction** using `@Commit`, `@Rollback(false)`, `TestTransaction`, and `@AfterTransaction`.
5. Test the difference between `@TransactionalEventListener(AFTER_COMMIT)` and `AFTER_ROLLBACK`/`BEFORE_COMMIT`.
6. Recognize cases rollback does not cover: `REQUIRES_NEW`, async threads, real HTTP server requests, and external side effects.
7. Design cleanup and idempotency so a committing test **does not pollute** subsequent tests.
8. Use H2 for standalone examples while knowing when to use **PostgreSQL/Testcontainers** to verify transaction isolation, deferred constraints, triggers, or real dialects.
9. Run a **Java 17+ / Spring Boot 3.5.16 / Spring Data JPA / JUnit Jupiter / Maven** project with multiple tests contrasting rollback and commit.

**Core message:** `flush` sends SQL to the current database connection; **only `commit` completes the transaction successfully, makes data visible to other transactions per isolation rules, and fires post-commit hooks**. Never treat `saveAndFlush` as a substitute for commit.

## 2. Three Transaction Layers to Distinguish

### 2.1. Test-Managed Transaction

Spring TestContext uses `TransactionalTestExecutionListener` to wrap a test method in a transaction **when the test is declared `@Transactional` and a suitable `PlatformTransactionManager` exists**.

`@DataJpaTest` in Spring Boot 3.5 enables test transactions by default: each test runs in a transaction, and afterward Spring **rolls back** that transaction. A test can add `@Commit` or `@Rollback(false)` to change how it ends.

```text
Spring TestContext
  |
  +-- begin TEST transaction (T1)
  |      |
  |      +-- @BeforeEach
  |      +-- @Test body
  |      |      +-- repository.save(...)
  |      |      +-- repository.flush()
  |      |      +-- repository.findBy...
  |      +-- @AfterEach
  | 
  +-- default: ROLLBACK T1
  +-- optional: COMMIT T1 with @Commit/@Rollback(false)
  |
  +-- @AfterTransaction (runs outside T1)
```

This timeline matters: JUnit Jupiter's `@BeforeEach` and `@AfterEach` inside a transactional test normally **execute inside** the test-managed transaction. To inspect database state before or after the transaction, use `@BeforeTransaction` and `@AfterTransaction`, or manage boundaries with `TestTransaction`.

### 2.2. Spring-Managed Transaction at the Service Layer

Suppose a service defines:

```java
@Service
public class PurchaseService {
    @Transactional
    public void create(...) {
        repository.save(...);
    }
}
```

When invoked through the **Spring proxy**, `@Transactional` defaults to `REQUIRED` propagation. If a test-managed transaction **already exists** on the same thread, the service normally **joins that transaction**; returning from the service method **does not commit a separate transaction**.

Therefore, the following test can mislead readers:

```java
@DataJpaTest
@Import(PurchaseService.class)
class PurchaseServiceTest {
    @Autowired PurchaseService service;

    @Test
    void create() {
        service.create(...);
        // No proof of commit here.
    }
}
```

This is an illustration; `create(...)` must be defined in a real project. Inside a test transaction, a `REQUIRED` service simply joins the active transaction. When the test ends, the outer test transaction rolls back even though the service method returned cleanly.

### 2.3. Application-Managed Transaction

Applications can also use `TransactionTemplate` or `PlatformTransactionManager` directly to open/commit/roll back transactions. Those transactions may join the test transaction or create separate boundaries depending on configuration and propagation.

**Never assume “every transaction gets rolled back by the test”.** Spring-managed/application-managed transactions join the test transaction only when propagation and thread/context match. `REQUIRES_NEW`, `NOT_SUPPORTED`, async/new threads, and HTTP server-side transactions can be completely independent.

### 2.4. Responsibility Matrix

| Type | Who Creates/Closes It? | Default When Test Has `@Transactional` | When Does It Commit? |
| --- | --- | --- | --- |
| Test-managed transaction | `TransactionalTestExecutionListener` | Rolled back after test | `@Commit`, `@Rollback(false)`, `TestTransaction.flagForCommit()` |
| Service `@Transactional(REQUIRED)` | Spring transaction interceptor | Joins T1 if same thread and compatible transaction | When T1 commits, not simply when method returns |
| Service `@Transactional(REQUIRES_NEW)` | Spring interceptor | Suspends T1, opens T2 | When the service method finishes and T2 commits |
| `TransactionTemplate` | Application code | Depends on propagation/config | When callback/transaction manager completes |
| HTTP request on real server thread | Server-side transaction manager | Does not inherit test ThreadLocal | When the server finishes its own transaction |
| External message/file/email | Systems outside database transaction | Usually does not roll back with T1 | Per external mechanism, often impossible to undo automatically |

## 3. Defaults of @DataJpaTest and @SpringBootTest

### 3.1. @DataJpaTest: Default Rollback

Spring Boot 3.5 Javadoc confirms `@DataJpaTest`:
- Loads only JPA entities, repositories, and required JPA/test infrastructure, not the full application.
- Wraps each test in a transaction and **rolls back by default**.
- Typically replaces the app datasource with an **embedded in-memory database**, unless configured otherwise.
- Accepts `@AutoConfigureTestDatabase` to adjust database replacement.

```java
@DataJpaTest
class PurchaseRepositoryTest {
    @Autowired PurchaseRepository repository;

    @Test
    void repositoryCanStoreAndQuery() {
        PurchaseRecord saved = repository.saveAndFlush(
                new PurchaseRecord("T-101", "NEW"));

        assertThat(repository.findByReferenceCode("T-101"))
                .isPresent();

        // When the test ends, Spring rolls back.
    }
}
```

This test verifies JPA mapping/queries **inside one transaction**; it does not prove the transaction committed.

### 3.2. @SpringBootTest Does Not Automatically Enable Rollback

`@SpringBootTest` only loads the application context for the test. It **does not by default** apply `@Transactional` to test methods. If a test writes:

```java
@SpringBootTest
class PurchaseIntegrationTest {
    @Autowired PurchaseService service;

    @Test
    void createsPurchase() {
        service.create("INT-101");
        // If service is @Transactional(REQUIRED) and there is no
        // test transaction, the service transaction may commit.
    }
}
```

This snippet follows section 9's API. Without an outer test-managed transaction, the service's `@Transactional` method creates and commits its own transaction. Data can remain afterward, requiring cleanup.

Only when the test/class carries `@Transactional` and appropriate test infrastructure exists does Spring TestContext open a test transaction. Never see `@SpringBootTest` and assume “all writes roll back”.

### 3.3. `@Transactional` on a Test Method Is Not Identical to `@Transactional` on a Service

In Spring Framework TestContext, several attributes of `@Transactional` **are not supported the same way** on test-managed transactions as on application methods:

| `@Transactional` Attribute on Test | Test-Managed Transactions |
| --- | --- |
| `value` / `transactionManager` | Supported to select the transaction manager |
| `propagation=NOT_SUPPORTED`, `NEVER` | Supported to run the test **without** a transaction |
| `propagation=REQUIRED` / `SUPPORTS` | Standard activation paths; do not infer every app propagation setting behaves identically |
| `isolation` | Not applied as you might expect to test-managed transactions |
| `timeout` | Not applied as you might expect |
| `readOnly` | Not applied as you might expect |
| `rollbackFor` / `noRollbackFor` | Does not govern test-managed commit/rollback; use `TestTransaction` or `@Commit`/`@Rollback` |

To test a real service method with `REQUIRES_NEW`, place the propagation attribute on the **service method**, rather than trying to put `@Transactional(propagation=REQUIRES_NEW)` on the test method expecting a second transaction.

## 4. How Do save(), flush(), saveAndFlush(), and commit() Differ?

### 4.1. save() — Managing the Entity in the Persistence Context

`repository.save(entity)` can call `EntityManager.persist` or `merge`. When SQL `INSERT`/`UPDATE` is emitted depends on ID generation, flush mode, persistence context state, and operations. With `GenerationType.IDENTITY`, the provider may INSERT early to get the generated ID.

**Never** treat “haven't called flush yet, so SQL definitely hasn't run” as an absolute rule.

### 4.2. flush() — Synchronizing Pending SQL

`repository.flush()` or `EntityManager.flush()` tells the JPA provider to synchronize pending changes to the database. It can trigger:
- SQL INSERT/UPDATE/DELETE.
- Immediate database constraint checks such as non-deferred unique/not-null/foreign-key constraints.
- JPA lifecycle callbacks firing during persistence/flush phases.
- SQL errors if invalid.

Yet the transaction remains **open**. Other connections likely still cannot see changes per isolation. Nor does an `AFTER_COMMIT` event fire merely because flush finished.

### 4.3. saveAndFlush()

`saveAndFlush(entity)` combines saving and flushing within the repository transaction. Helpful when you want the database to catch constraint errors early, it is still not equivalent to:
- `Connection.commit()`.
- Commit-only triggers or hooks.
- `@TransactionalEventListener(AFTER_COMMIT)`.
- Data becoming visible to other connections.
- Durable completion per database guarantees.

### 4.4. commit()

Commit:
1. Finalizes the transaction successfully when no errors or rollback-only flags exist.
2. Evaluates database rules deferred until commit (such as deferrable constraints where supported).
3. Makes changes visible per isolation levels and other transactions' snapshots.
4. Triggers Spring synchronizations and post-commit transactional event listeners.
5. Allows external observers like CDC/outbox processors to read committed rows (subject to system/lag behavior).

Commit **can also fail** due to constraints, connection loss, deadlocks, serialization failures, or DB shutdown. In those cases, a test stopping at `flush` fails to verify a successful commit flow.

### 4.5. Timeline Comparison

```text
Transaction T1:
  begin
   |
   +-- repository.save(entity)       -> entity becomes managed
   |
   +-- repository.flush()            -> SQL sent, T1 not yet committed
   |
   +-- repository.findById(id)       -> can see row inside T1
   |
   +-- publishEvent(PurchaseCreated) -> AFTER_COMMIT listener waits
   |
   +-- test assertion PASSES         -> still insufficient
   |
   +-- ROLLBACK (default @DataJpaTest)
          -> row vanishes; AFTER_COMMIT listener never runs
```

When verifying commit:

```text
Transaction T1:
  begin -> save -> flush -> event scheduled -> COMMIT
                                              |
                                              +-- row committed
                                              +-- AFTER_COMMIT listener runs
                                              +-- @AfterTransaction checks outside T1
```

## 5. Limits When Every Test Always Rolls Back

### 5.1. AFTER_COMMIT Listeners Never Execute

`@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` listens for transaction **commit**, running synchronously on the transaction thread by default unless `@Async` is configured.

```java
@Component
class PurchaseCreatedListener {
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    void onCreated(PurchaseCreated event) {
        // runs only after a successful commit
    }
}
```

If the test runs inside an outer test transaction that rolls back, the event may be published, yet the listener **is never invoked**.

Do not write a test that “publishes an event and immediately verifies the listener ran” when the listener uses `AFTER_COMMIT`. The test must close/commit the transaction before asserting the callback, e.g., via `@AfterTransaction` or `TestTransaction.end()`.

### 5.2. Data Is Visible Only Inside the Current Transaction

A query sharing the persistence context can read a just-saved/flushed entity. That **does not** prove another transaction sees the row. Under `READ_COMMITTED`, a fresh connection normally cannot read T1's uncommitted changes. Under snapshot-based isolation, the reading transaction's snapshot timing also matters.

To verify “another user can read after commit”, query **outside the test transaction** or in a new transaction started **after commit**, not solely `findById` inside T1.

### 5.3. Deferred Database Constraints Can Fail at Commit

PostgreSQL supports `DEFERRABLE INITIALLY DEFERRED` on constraints like unique and foreign keys. Even though `flush` sends SQL, validation can wait **until commit**, so a rolling-back test will not trigger the commit-time error.

PostgreSQL SQL example (not part of the H2 demo):

```sql
CREATE TABLE unique_codes (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    code text NOT NULL,
    CONSTRAINT uq_code UNIQUE (code)
        DEFERRABLE INITIALLY DEFERRED
);
```

Two INSERTs with the same `code` in one transaction may raise no error at flush, yet **commit fails** due to the unique constraint. Proving this requires **real PostgreSQL/Testcontainers**, rather than assuming H2 shares deferred semantics.

### 5.4. Triggers/Outbox/CDC and Out-of-Transaction Integration

Many architectures use the transactional outbox pattern:
- Business service writes `orders` and `outbox_events` in the **same transaction**.
- An outbox worker or CDC relay runs on **another connection/process**.
- The worker can consume rows only after the write transaction commits and rows become visible.
- A rolling-back test erases the outbox row; the relay never sees it.

You cannot claim the outbox flow is integrated merely because a repository test finds an outbox row before rollback. Add targeted real-commit tests with an isolated DB and an appropriate relay/test consumer.

### 5.5. Transaction Callbacks and Resource Lifecycle

Spring `TransactionSynchronization` offers `beforeCommit`, `afterCommit`, and `afterCompletion`. Post-commit/rollback steps handle cleanup, cache invalidation, auditing, or event dispatch. A rolling-back test exercises only the rollback path, leaving the commit path untested.

JPA `@PostPersist` or `@PostUpdate` are persistence-lifecycle callbacks, **not** proof of commit. They can run before the transaction finishes; a subsequent rollback still undoes the DB changes.

### 5.6. Non-DB Side Effects

Sending emails, HTTP calls, message broker publishes, file writes, or external service invocations can happen before commit. Database transaction rollback **cannot** recall an already-sent email or acked message. Architectures require **outbox, retries, idempotency, or compensation**.

A test using mocks can verify “the email adapter was called”, yet fail to prove the timing is transaction-safe. When sending is meant to happen after commit, test the callback/dispatcher at the actual post-commit phase.

## 6. Three Ways to Request an Intentional Commit

### 6.1. @Commit

`@Commit` on a transactional test class/method tells TestContext to commit instead of rolling back:

```java
@DataJpaTest
class RealCommitRepositoryTest {
    @Autowired PurchaseRepository repository;

    @Test
    @Commit
    void persistsAcrossTransactions() {
        repository.saveAndFlush(
                new PurchaseRecord("COMMIT-1", "NEW"));
        // Commit occurs AFTER the test method, before @AfterTransaction.
    }

    @AfterTransaction
    void verifyCommitted() {
        assertThat(repository.findByReferenceCode("COMMIT-1"))
                .isPresent();
        // Data cleanup in a separate transaction is required!
    }
}
```

This snippet shows usage; the complete project puts cleanup inside `finally` so no rows leak.

**Important:** assertions inside `@Test` still run **before commit**. To prove “committed”, assert inside `@AfterTransaction`, or end the test transaction manually via `TestTransaction.end()` and assert afterward.

### 6.2. @Rollback(false)

`@Rollback(false)` has the same effect (committing the test transaction at completion), using an explicit boolean flag:

```java
@Test
@Rollback(false)
void persistenceRequiresCommit() {
    // ...
}
```

`@Commit` is essentially a readable alias for “do not roll back”. Either can go on a class or method; method-level overrides class-level. Never stack both `@Commit` and `@Rollback(false)` on the same method.

`@Rollback(true)` restores rollback for a single method inside a `@Commit`-annotated class, though keep scopes clear so other methods do not accidentally persist test data.

### 6.3. TestTransaction.flagForCommit() and end()

When you need to inspect commit **mid-test**:

```java
@Test
void canInspectDatabaseAfterCommit() {
    repository.saveAndFlush(
            new PurchaseRecord("MANUAL-1", "NEW"));

    TestTransaction.flagForCommit();
    TestTransaction.end(); // commit the test-managed transaction right here

    assertThat(TestTransaction.isActive()).isFalse();
    assertThat(repository.findByReferenceCode("MANUAL-1"))
            .isPresent();

    // Clean up using another repository transaction (in finally).
}
```

`TestTransaction` is meaningful only when `TransactionalTestExecutionListener` opened a **test-managed transaction** (such as in `@DataJpaTest`). `end()` terminates the current transaction per its commit/rollback flag. Never call it in plain JUnit tests without a transaction or in `NOT_SUPPORTED` tests expecting it to start one automatically.

### 6.4. TestTransaction.start() and flagForRollback()

After ending T1, you can start T2 to inspect committed data from a new transaction boundary:

```java
TestTransaction.flagForCommit();
TestTransaction.end();

TestTransaction.start();
try {
    assertThat(repository.findByReferenceCode("MANUAL-1"))
            .isPresent();
}
finally {
    TestTransaction.flagForRollback();
    TestTransaction.end();
}
```

This snippet runs inside a test method of a `@DataJpaTest` class. **T2** reads a fresh snapshot and explicitly rolls back afterward. Because **T1's committed row remains**, you still must delete it in a separate transaction after T2.

### 6.5. @BeforeTransaction and @AfterTransaction

`@BeforeTransaction` runs before the test transaction opens; `@AfterTransaction` runs after the test transaction closes. They run only for test methods configured with a test-managed transaction.

```java
@BeforeTransaction
void checkCleanStart() {
    assertThat(repository.findByReferenceCode("COMMIT-1"))
            .isEmpty();
}

@Test
@Commit
void save() {
    repository.saveAndFlush(
            new PurchaseRecord("COMMIT-1", "NEW"));
}

@AfterTransaction
void checkCommittedAndClean() {
    try {
        assertThat(repository.findByReferenceCode("COMMIT-1"))
                .isPresent();
    }
    finally {
        repository.findByReferenceCode("COMMIT-1")
                .ifPresent(repository::delete);
    }
}
```

These hooks run outside T1. Repository methods need their own transactions when writing/deleting; Spring Data JPA `SimpleJpaRepository.delete` is transactional. For complex cleanup, use a `@Transactional` bean/service or scoped `TransactionTemplate`.

## 7. Cleaning Up After Real-Commit Tests: A Mandatory Responsibility

### 7.1. Why Is Careless `@Commit` Dangerous?

A test that commits rows without deleting them can:
- Break the next test via unique constraint violations.
- Make count/list assertions depend on execution order.
- Cause flaky CI across parallel test runs.
- Pollute a shared test database, sandbox, or others' data.
- Trigger real outbox events/jobs if app infrastructure is not isolated.

`@Commit` is not a shortcut to “fix a red test”. Enable commits only for tests **genuinely testing commit-dependent behavior**, paired with cleanup and DB isolation.

### 7.2. Use Namespaced Test Data

Assign unique `referenceCode` values per test or run. With deterministic fixtures like `COMMIT-1`, guarantee a fresh/isolated test database and clean teardown.

For parallel tests, include a UUID suffix or correlation ID logged in reports; never share a hardcoded key across tests that may execute concurrently against the same database.

### 7.3. Cleanup in finally

```java
@AfterTransaction
void afterCommit() {
    try {
        assertThat(repository.findByReferenceCode("COMMIT-1"))
                .isPresent();
    }
    finally {
        repository.findByReferenceCode("COMMIT-1")
                .ifPresent(repository::delete);
    }
}
```

If an assertion fails because the row never committed, `finally` still attempts cleanup. Still, `finally` cannot run on JVM crashes, kills, or terminated CI runners—which is why an **isolated test database** is essential rather than sharing important environments.

### 7.4. Cleanup When Tests Are Non-Transactional

In `@SpringBootTest` without a test-managed tx or `@Transactional(propagation=NOT_SUPPORTED)`, services commit inside their methods. Cleanup must run inside an **independent transaction**; `repository.delete(...)` or a transactional cleanup service can handle it.

When deletion spans multiple tables with foreign keys or outbox rows, delete in valid FK order and ensure cleanup commits. Never call `EntityManager.remove` outside a transaction expecting rows to be deleted.

### 7.5. @DirtiesContext Is Not Database Cleanup

`@DirtiesContext` tells Spring TestContext to discard and rebuild the cached context; it **does not guarantee deleting data** in an external database. With in-memory H2, data might vanish when the context/DB closes, yet never rely on that as a cleanup contract—especially once moving to a PostgreSQL container or shared DB.

### 7.6. @Sql and Isolated Transactions

Spring `@Sql` sets up or tears down fixtures; `@SqlConfig(transactionMode = ISOLATED)` runs SQL scripts in a **separate committed transaction**, outside the test's rollback scope.

```java
@Sql(
    scripts = "/sql/seed-purchase.sql",
    config = @SqlConfig(transactionMode =
            SqlConfig.TransactionMode.ISOLATED))
class DatabaseFixtureTest {
    // ...
}
```

This is an illustrative snippet requiring real SQL scripts and imports. It helps create committed fixtures yet leaves data behind after the test; add cleanup, typically via `@Sql` at `AFTER_TEST_METHOD` or a transactional cleanup callback. Never assume `@Sql` always runs outside the test transaction — semantics depend on config and test transaction state.

### 7.7. Testcontainers for Deterministically Scoped DBs

For PostgreSQL integration tests:
- Dedicate an isolated database/schema/container per suite or test group.
- Never point at production, even read-only.
- Set `@AutoConfigureTestDatabase(replace = NONE)` if `@DataJpaTest` must **preserve the container datasource** instead of replacing it with an embedded DB.
- When using Spring Boot `@ServiceConnection` with Testcontainers, ensure container lifecycles and connection details stay test-scoped.
- Test deferred constraints, real dialects, locks/isolation on the real database, not H2 emulation.
- Clean up by truncating/deleting in the isolated DB or destroying the container after the suite.

## 8. Transaction Boundaries Not Covered by Test Rollback

### 8.1. REQUIRES_NEW: Inner Transaction Can Commit Independently

```java
@Service
class IndependentWriter {
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void record() {
        // repository.save(...)
    }
}
```

While outer test T1 is active, calling this method through the Spring proxy suspends T1 and opens T2. If T2 commits cleanly, T1 rolling back afterward **does not undo T2**. T2's writes stay in the database.

This is a dangerous failure mode when teams assume “it's `@DataJpaTest`, so every write rolls back”. Tests must understand transaction boundaries and clean up rows committed by T2.

**Pitfall:** self-invocation (`this.record()` from within the same class) bypasses the Spring AOP proxy, preventing `REQUIRES_NEW` from starting a fresh transaction as expected. Tests must call through a separate bean/proxy or refactor the service structure.

### 8.2. NOT_SUPPORTED: Running a Test Without a Test Transaction

```java
@DataJpaTest
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class NonTransactionalJpaTest {
    // ...
}
```

This configures TestContext **not to run the test method in a transaction**. Repository and service methods manage their own transactions (or fail if an operation requires one). Use this when testing that a service commits upon return. Explicit cleanup is mandatory since no outer rollback exists.

### 8.3. Async/New Threads

Spring JPA transactions normally bind to the current thread via `ThreadLocal`. When code uses `@Async`, `CompletableFuture`, manual threads, executors, or cross-thread callbacks, the test thread's transaction **does not propagate**.

A `@Transactional` test calling an async service can commit rows outside the test transaction. To test async effects:
- Wait deterministically for future/queue completion.
- Use an isolated real test DB.
- Clean up external side effects.
- Never rely on `Thread.sleep(1000)` to guess commit completed.
- Test idempotency and error handling independently.

### 8.4. JUnit assertTimeoutPreemptively Can Break Boundaries

`assertTimeoutPreemptively(...)` runs the executable on a separate thread to allow interruption on timeout. Spring TestContext docs warn that ThreadLocal transaction state **is not propagated** to that thread; DB writes inside can commit instead of rolling back with the outer test transaction.

```java
// DO NOT use this pattern expecting test rollback:
assertTimeoutPreemptively(Duration.ofSeconds(2), () -> {
    service.create("PREEMPTIVE-1");
});
```

In transactional tests, prefer `assertTimeout(...)` (non-preemptive) or same-thread timeout handling while bounding the underlying operation's timeout. JUnit `@Timeout` thread mode depends on configuration; always verify which thread actually runs the code.

### 8.5. `@SpringBootTest(RANDOM_PORT)`: Server Transactions on Separate Threads

```java
@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
@Transactional
class RealHttpPurchaseTest {
    // HTTP client sends POST to the real server.
}
```

This is an illustrative snippet. The test method's transaction on the JUnit thread **does not cover** the transaction handling the request on the web server thread. When the controller/service saves and commits, rows survive after the test transaction rolls back.

By contrast, `@SpringBootTest(webEnvironment=MOCK)` with `MockMvc` normally executes MVC requests **on the same test thread**, so a `REQUIRED` service can join the outer test transaction. These two setups **are not equivalent** regarding visibility and commit, even with identical request paths and assertions.

### 8.6. Multiple Transaction Managers and Chained Resources

If an application defines multiple transaction managers, `@Transactional("ordersTxManager")` and `@Transactional("billingTxManager")` can manage separate resources. A test transaction bound to `@Transactional(transactionManager="...")` does not automatically roll back resources owned by another transaction manager.

With Kafka transactions, JMS, files, emails, remote DBs, or multiple datasources, transaction coordination has strict limits; never claim a rollback undoes all side effects without explicit coordination/compensation mechanisms.

## 9. Runnable Practice Project: Spring Boot 3.5.16, Java 17

The project is intentionally compact, needs no Docker, and uses an **embedded H2 database** and JPA to demonstrate rollback vs. commit. Tests cover:
1. `saveAndFlush` in `@DataJpaTest` then rollback; `@AfterTransaction` confirms the row does not exist.
2. `@Commit` then `@AfterTransaction` confirms the row exists and cleans up.
3. `TestTransaction.flagForCommit()`, `end()` to commit mid-method.
4. `AFTER_COMMIT` listener **does not** run on default rollback.
5. `AFTER_COMMIT` listener runs **after** `@Commit`.
6. `@Transactional(propagation=NOT_SUPPORTED)` letting the service commit on its own.
7. `REQUIRES_NEW` writing committed rows surviving an outer rollback.

### 9.1. Directory Tree

```text
jpa-commit-boundary-lab/
├── pom.xml
├── src/main/resources/application.properties
├── src/main/java/com/example/commitlab/
│   ├── CommitLabApplication.java
│   ├── PurchaseRecord.java
│   ├── PurchaseRepository.java
│   ├── PurchaseCreated.java
│   ├── PurchaseService.java
│   ├── PurchaseCreatedListener.java
│   └── IndependentWriter.java
└── src/test/java/com/example/commitlab/
    ├── DefaultRollbackTest.java
    ├── ExplicitCommitTest.java
    ├── ManualTestTransactionTest.java
    ├── RollbackDoesNotFireEventTest.java
    ├── CommitFiresEventTest.java
    ├── NoTestTransactionTest.java
    └── RequiresNewSurvivesRollbackTest.java
```

All Java classes live in package `com.example.commitlab`. For clarity, tests use **distinct reference codes**, clean up their committed data, and avoid sharing state intentionally. No network or external systems are used.

### 9.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>jpa-commit-boundary-lab</artifactId>
  <version>1.0.0</version>

  <properties>
    <java.version>17</java.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>
    <dependency>
      <groupId>com.h2database</groupId>
      <artifactId>h2</artifactId>
      <scope>runtime</scope>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
```

H2 lets the project run locally without an external DB; Spring Boot parent manages dependency versions. Spring Web starter is omitted because the demo tests only JPA transactions without an HTTP server. When switching to PostgreSQL to test deferred constraints/locking, configure a real DB/Testcontainers separately and drop any assumption that H2 mirrors the production dialect.

### 9.3. application.properties

`src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:commitlab;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.jpa.show-sql=false
```

Because the project has only H2 and no external database, `@DataJpaTest` uses an embedded datasource. `ddl-auto=create-drop` is convenient **strictly for this practice demo**, never as a production migration strategy. In real apps using Flyway/Liquibase, test migrations against the chosen database.

### 9.4. CommitLabApplication.java

`src/main/java/com/example/commitlab/CommitLabApplication.java`:

```java
package com.example.commitlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CommitLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(CommitLabApplication.class, args);
    }
}
```

### 9.5. PurchaseRecord.java

`src/main/java/com/example/commitlab/PurchaseRecord.java`:

```java
package com.example.commitlab;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "purchase_records")
public class PurchaseRecord {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "reference_code", nullable = false,
            unique = true, length = 80)
    private String referenceCode;

    @Column(nullable = false, length = 32)
    private String state;

    protected PurchaseRecord() {
        // JPA constructor
    }

    public PurchaseRecord(String referenceCode, String state) {
        this.referenceCode = referenceCode;
        this.state = state;
    }

    public Long getId() {
        return id;
    }

    public String getReferenceCode() {
        return referenceCode;
    }

    public String getState() {
        return state;
    }
}
```

`GenerationType.IDENTITY` lets the provider INSERT to obtain the ID when needed; that **is not commit**. The entity has a no-arg constructor as required by JPA. The unique index is an ordinary immediate constraint in the H2 demo, **not DEFERRABLE**.

### 9.6. PurchaseRepository.java

`src/main/java/com/example/commitlab/PurchaseRepository.java`:

```java
package com.example.commitlab;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseRepository
        extends JpaRepository<PurchaseRecord, Long> {

    Optional<PurchaseRecord> findByReferenceCode(String referenceCode);
}
```

Spring Data JPA provides the repository bean in `@DataJpaTest`. Query `findByReferenceCode` uses the Java property `referenceCode` (not the SQL column name `reference_code`). `JpaRepository`'s `delete` method executes inside a transaction per `SimpleJpaRepository`, so it can clean up from `@AfterTransaction`.

### 9.7. PurchaseCreated.java

`src/main/java/com/example/commitlab/PurchaseCreated.java`:

```java
package com.example.commitlab;

public record PurchaseCreated(
        Long id,
        String referenceCode) {}
```

The event is an immutable Java record. **Publishing** an event differs from the event listener **running**; an `AFTER_COMMIT` listener waits until the transaction commits before handling it.

### 9.8. PurchaseService.java

`src/main/java/com/example/commitlab/PurchaseService.java`:

```java
package com.example.commitlab;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PurchaseService {

    private final PurchaseRepository repository;
    private final ApplicationEventPublisher events;

    public PurchaseService(
            PurchaseRepository repository,
            ApplicationEventPublisher events) {
        this.repository = repository;
        this.events = events;
    }

    @Transactional
    public Long create(String referenceCode) {
        PurchaseRecord saved = repository.saveAndFlush(
                new PurchaseRecord(referenceCode, "NEW"));

        events.publishEvent(new PurchaseCreated(
                saved.getId(), saved.getReferenceCode()));

        return saved.getId();
    }
}
```

Because the service uses default `@Transactional(REQUIRED)`:
- Inside a transactional `@DataJpaTest`, the method normally joins the outer test transaction.
- Inside a `NOT_SUPPORTED` test (no outer test transaction), the Spring proxy opens a new transaction and commits when the method returns cleanly.
- `saveAndFlush` sends SQL, yet the `AFTER_COMMIT` listener **does not** run until the transaction actually commits.

### 9.9. PurchaseCreatedListener.java

`src/main/java/com/example/commitlab/PurchaseCreatedListener.java`:

```java
package com.example.commitlab;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class PurchaseCreatedListener {

    private final CopyOnWriteArrayList<PurchaseCreated> observed =
            new CopyOnWriteArrayList<>();

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(PurchaseCreated event) {
        observed.add(event);
    }

    public List<PurchaseCreated> observed() {
        return List.copyOf(observed);
    }

    public void clear() {
        observed.clear();
    }
}
```

The listener stores events in an in-memory list so synchronous tests do not need an email server or broker. This **is not production audit storage**. If a real listener must write additional DB rows after commit, note that resources from the old transaction may still be bound to the thread; normally use a **new transaction** for that write (see section 11). With `@Async` event listeners, assertions must wait for async work to finish rather than assuming synchronous execution.

### 9.10. IndependentWriter.java

`src/main/java/com/example/commitlab/IndependentWriter.java`:

```java
package com.example.commitlab;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class IndependentWriter {
    private final PurchaseRepository repository;

    public IndependentWriter(PurchaseRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void write(String referenceCode) {
        repository.saveAndFlush(
                new PurchaseRecord(referenceCode, "NEW"));
    }
}
```

This is a separate bean invoked via the Spring proxy, avoiding self-invocation. `REQUIRES_NEW` suspends the outer transaction and commits its own transaction when the method returns. The test will use `@AfterTransaction` to verify the row persists even though the outer test transaction rolled back.

### 9.11. DefaultRollbackTest.java

`src/test/java/com/example/commitlab/DefaultRollbackTest.java`:

```java
package com.example.commitlab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.BeforeTransaction;
import org.springframework.test.context.transaction.TestTransaction;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
class DefaultRollbackTest {

    private static final String REF = "ROLLBACK-1";

    @Autowired
    PurchaseRepository repository;

    @BeforeTransaction
    void beforeTransaction() {
        assertThat(repository.findByReferenceCode(REF)).isEmpty();
    }

    @Test
    void saveAndFlushIsNotCommit() {
        assertThat(TestTransaction.isActive()).isTrue();

        repository.saveAndFlush(
                new PurchaseRecord(REF, "NEW"));

        assertThat(repository.findByReferenceCode(REF))
                .isPresent();

        // This check inside T1 does not prove commit.
    }

    @AfterTransaction
    void afterTransaction() {
        // TestContext rolls back T1 by default.
        assertThat(repository.findByReferenceCode(REF)).isEmpty();
    }
}
```

**Expected:** Inside the method, the row is found; after the method and rollback, `@AfterTransaction` confirms the row is gone. This is a direct test breaking the misconception that `saveAndFlush == commit`.

### 9.12. ExplicitCommitTest.java

`src/test/java/com/example/commitlab/ExplicitCommitTest.java`:

```java
package com.example.commitlab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.test.annotation.Commit;
import org.springframework.test.context.transaction.AfterTransaction;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
class ExplicitCommitTest {

    private static final String REF = "COMMIT-1";

    @Autowired
    PurchaseRepository repository;

    @Test
    @Commit
    void commitsAtEndOfTestMethod() {
        repository.saveAndFlush(
                new PurchaseRecord(REF, "NEW"));

        // Still in T1: only know the row was flushed.
        assertThat(repository.findByReferenceCode(REF))
                .isPresent();
    }

    @AfterTransaction
    void provesCommitAndCleansUp() {
        try {
            // @AfterTransaction: T1 has finished COMMITting.
            assertThat(repository.findByReferenceCode(REF))
                    .isPresent();
        }
        finally {
            repository.findByReferenceCode(REF)
                    .ifPresent(repository::delete);
        }
    }
}
```

`@Commit` on the method commits **only this test**. `@AfterTransaction` checks data visibility after commit and cleans up. Without cleanup, this test would leave `COMMIT-1` behind in the DB.

### 9.13. ManualTestTransactionTest.java

`src/test/java/com/example/commitlab/ManualTestTransactionTest.java`:

```java
package com.example.commitlab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.test.context.transaction.TestTransaction;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
class ManualTestTransactionTest {

    private static final String REF = "MANUAL-1";

    @Autowired
    PurchaseRepository repository;

    @Test
    void endsTestTransactionAndSeesCommittedRow() {
        assertThat(TestTransaction.isActive()).isTrue();

        repository.saveAndFlush(
                new PurchaseRecord(REF, "NEW"));

        TestTransaction.flagForCommit();
        TestTransaction.end();

        assertThat(TestTransaction.isActive()).isFalse();

        try {
            // Query outside T1 after commit.
            assertThat(repository.findByReferenceCode(REF))
                    .isPresent();
        }
        finally {
            repository.findByReferenceCode(REF)
                    .ifPresent(repository::delete);
        }
    }
}
```

This differs from `@Commit`: commit happens **inside the test method**, so the assertion after `TestTransaction.end()` is a post-commit assertion right in place. This is useful for workflows needing T1 to commit before reading in T2. There is no need to convert all repository tests to manual transaction boundaries.

### 9.14. RollbackDoesNotFireEventTest.java

`src/test/java/com/example/commitlab/RollbackDoesNotFireEventTest.java`:

```java
package com.example.commitlab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.BeforeTransaction;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
@Import({PurchaseService.class, PurchaseCreatedListener.class})
class RollbackDoesNotFireEventTest {

    private static final String REF = "EVENT-ROLLBACK-1";

    @Autowired PurchaseService service;
    @Autowired PurchaseRepository repository;
    @Autowired PurchaseCreatedListener listener;

    @BeforeTransaction
    void clearObserved() {
        listener.clear();
    }

    @Test
    void eventWaitsForCommitButTestWillRollback() {
        service.create(REF);

        assertThat(repository.findByReferenceCode(REF))
                .isPresent();
        assertThat(listener.observed()).isEmpty();
    }

    @AfterTransaction
    void verifiesNoAfterCommitEvent() {
        assertThat(repository.findByReferenceCode(REF))
                .isEmpty();
        assertThat(listener.observed()).isEmpty();
    }
}
```

This test proves “the service called `publishEvent`” does not mean the `AFTER_COMMIT` listener ran. Because the outer test transaction rolls back, the listener is never invoked. `@Import` imports only the specific service and listener; `@DataJpaTest` does not automatically scan `@Service`/`@Component` beans.

### 9.15. CommitFiresEventTest.java

`src/test/java/com/example/commitlab/CommitFiresEventTest.java`:

```java
package com.example.commitlab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.annotation.Commit;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.BeforeTransaction;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
@Import({PurchaseService.class, PurchaseCreatedListener.class})
class CommitFiresEventTest {

    private static final String REF = "EVENT-COMMIT-1";

    @Autowired PurchaseService service;
    @Autowired PurchaseRepository repository;
    @Autowired PurchaseCreatedListener listener;

    @BeforeTransaction
    void clearObserved() {
        listener.clear();
    }

    @Test
    @Commit
    void publishesEventButListenerWaitsUntilCommit() {
        Long id = service.create(REF);

        assertThat(id).isNotNull();
        assertThat(repository.findByReferenceCode(REF))
                .isPresent();

        // Transaction T1 has not ended yet.
        assertThat(listener.observed()).isEmpty();
    }

    @AfterTransaction
    void verifiesAfterCommitAndCleans() {
        try {
            assertThat(repository.findByReferenceCode(REF))
                    .isPresent();

            assertThat(listener.observed())
                    .extracting(PurchaseCreated::referenceCode)
                    .containsExactly(REF);
        }
        finally {
            repository.findByReferenceCode(REF)
                    .ifPresent(repository::delete);
            listener.clear();
        }
    }
}
```

This test traces the entire timeline: the event is published inside T1; the listener has not yet fired during the test method's assertions; Spring TestContext commits T1 thanks to `@Commit`; the `AFTER_COMMIT` callback adds the event to the list; `@AfterTransaction` verifies and cleans up.

**Limitation:** the demo listener runs synchronously in memory; production listeners may use `@Async`, brokers, or external APIs. In those cases `@AfterTransaction` can run before the async job finishes; await the outcome with explicit timeouts and verify side effects independently.

### 9.16. NoTestTransactionTest.java

`src/test/java/com/example/commitlab/NoTestTransactionTest.java`:

```java
package com.example.commitlab;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
@Import({PurchaseService.class, PurchaseCreatedListener.class})
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class NoTestTransactionTest {

    private static final String REF = "NO-TEST-TX-1";

    @Autowired PurchaseService service;
    @Autowired PurchaseRepository repository;
    @Autowired PurchaseCreatedListener listener;

    @BeforeEach
    void clearObserved() {
        listener.clear();
    }

    @Test
    void serviceOpensAndCommitsOwnTransaction() {
        assertThat(TestTransaction.isActive()).isFalse();

        try {
            Long id = service.create(REF);

            // Service @Transactional already completed commit
            // before returning, with no outer T1.
            assertThat(id).isNotNull();
            assertThat(repository.findByReferenceCode(REF))
                    .isPresent();
            assertThat(listener.observed())
                    .extracting(PurchaseCreated::referenceCode)
                    .containsExactly(REF);
        }
        finally {
            repository.findByReferenceCode(REF)
                    .ifPresent(repository::delete);
            listener.clear();
        }
    }
}
```

The key difference: `@Transactional(propagation=NOT_SUPPORTED)` on the test disables the **test-managed transaction**. Hence `PurchaseService.create` runs through the Spring proxy, opens its own transaction, and commits before returning. Cleanup is needed directly in the test because there is no outer rollback.

### 9.17. RequiresNewSurvivesRollbackTest.java

`src/test/java/com/example/commitlab/RequiresNewSurvivesRollbackTest.java`:

```java
package com.example.commitlab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.TestTransaction;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
@Import(IndependentWriter.class)
class RequiresNewSurvivesRollbackTest {

    private static final String REF = "REQUIRES-NEW-1";

    @Autowired IndependentWriter writer;
    @Autowired PurchaseRepository repository;

    @Test
    void commitsSeparateTransactionWhileTestTransactionIsOpen() {
        assertThat(TestTransaction.isActive()).isTrue();

        // TestContext's T1 is open (rolls back by default).
        // Method runs through Spring proxy opening T2 REQUIRES_NEW.
        writer.write(REF);

        // Do not assert visibility in T1:
        // depending on isolation/snapshot, this may vary.
    }

    @AfterTransaction
    void seesInnerCommitAfterOuterRollbackAndCleans() {
        try {
            // T2 committed independently; T1 rolled back.
            assertThat(repository.findByReferenceCode(REF))
                    .isPresent();
        }
        finally {
            repository.findByReferenceCode(REF)
                    .ifPresent(repository::delete);
        }
    }
}
```

This example proves outer rollback does not cover every transaction. The test intentionally avoids asserting row visibility inside T1 after T2: different databases and isolation levels behave differently. `@AfterTransaction` runs after the outer rollback, querying T2's committed row via a fresh transaction/connection.

### 9.18. Running Maven

In the `jpa-commit-boundary-lab` directory with JDK 17+ and Maven:

```bash
mvn -q clean test

mvn -q -Dtest=DefaultRollbackTest test
mvn -q -Dtest=ExplicitCommitTest test
mvn -q -Dtest=ManualTestTransactionTest test
mvn -q -Dtest=RollbackDoesNotFireEventTest test
mvn -q -Dtest=CommitFiresEventTest test
mvn -q -Dtest=NoTestTransactionTest test
mvn -q -Dtest=RequiresNewSurvivesRollbackTest test
```

When all assertions pass, Maven reports build/test success with exit code `0`. No exact stdout is assumed: Hibernate/JDBC/Maven logging and cached context counts can differ. Detailed results appear in `target/surefire-reports`.

**Environment scope:** This project teaches semantics using H2, not verifying PostgreSQL deferred constraints or HTTP server transactions. The classes and configs are structured to run directly once created at the proper file paths; before production adoption, run real builds against your team's artifact repository and JDK.

## 10. Expected Outcomes of the Seven Tests

| Test Class | Has Test Transaction? | Notable Ending | Observation After Boundary |
| --- | --- | --- | --- |
| `DefaultRollbackTest` | Has T1 | Default rollback | Row does not exist |
| `ExplicitCommitTest` | Has T1 | `@Commit` at test end | Row exists, then cleaned up |
| `ManualTestTransactionTest` | Has T1 initially | `TestTransaction.end()` commits immediately | Query outside T1 sees row |
| `RollbackDoesNotFireEventTest` | Has T1 | Default rollback | `AFTER_COMMIT` listener never runs |
| `CommitFiresEventTest` | Has T1 | `@Commit` | `AFTER_COMMIT` listener runs after commit |
| `NoTestTransactionTest` | No test T1 | Service opens/commits its own transaction | Row and event observed |
| `RequiresNewSurvivesRollbackTest` | Has outer T1 | Inner T2 commits; outer T1 rolls back | T2's row survives |

Note “row exists” holds **prior to cleanup**. Tests clean up after verification so no state leaks across runs. For parallel tests sharing H2/a database, use unique fixtures and context isolation; these tests are designed for Maven Surefire's default sequential execution.

## 11. Advanced Notes on AFTER_COMMIT

### 11.1. An AFTER_COMMIT Listener Is Not Automatically Safe for DB Writes

Spring Framework's Javadoc for `@TransactionalEventListener` warns: at `AFTER_COMMIT`/`AFTER_ROLLBACK`/`AFTER_COMPLETION`, the transaction has finished, yet some resources may remain bound to the thread. Data access operations performed then may **still bind to the old transaction's resources**, which will **never commit again**.

Therefore, when a listener must write an audit row or database record, it generally must open a **new** transaction:

```java
@Service
class AuditWriter {
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void writeAudit(PurchaseCreated event) {
        // auditRepository.save(...)
    }
}

@Component
class PurchaseAuditListener {
    private final AuditWriter auditWriter;

    PurchaseAuditListener(AuditWriter auditWriter) {
        this.auditWriter = auditWriter;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(PurchaseCreated event) {
        auditWriter.writeAudit(event);
    }
}
```

This is an **illustrative pattern**, excluded from the runnable project since `auditRepository`/entity are omitted. `AuditWriter` must be a separate Spring bean so `REQUIRES_NEW` runs through the proxy; self-invocation inside the same class bypasses AOP.

### 11.2. Does an AFTER_COMMIT Listener Run When Published Outside a Transaction?

By default `@TransactionalEventListener` has `fallbackExecution = false`. If an event is published **with no active transaction**, the listener will ignore it. You can set `fallbackExecution=true` if business rules call for fallback, though behavior then differs depending on whether a transaction is active; test both cases.

Real-world example: a non-`@Transactional` method publishes an event and an `AFTER_COMMIT` listener never runs. Do not assume that is a Spring bug; check which transaction boundary published the event.

### 11.3. BEFORE_COMMIT and AFTER_ROLLBACK

`TransactionPhase.BEFORE_COMMIT` runs prior to commit; exceptions from the callback can prevent commit depending on handling. `AFTER_ROLLBACK` runs when the transaction rolls back. `AFTER_COMPLETION` runs after completion regardless of outcome.

When an action must run **only on successful commit**, pick `AFTER_COMMIT` instead of `AFTER_COMPLETION`. When cleanup must happen on both rollback and commit, pick the matching hook while avoiding “succeeded” business work before commit finishes.

### 11.4. `@Async` Combined with AFTER_COMMIT

If a listener is both `@Async` and `@TransactionalEventListener(AFTER_COMMIT)`, callback dispatch runs asynchronously. Tests must not write:

```java
service.create("ASYNC-1");
assertThat(emailGateway.sent()).isTrue(); // race
```

This snippet illustrates the race risk and is not in the runnable project. To test it:
- Commit a real transaction.
- Await event processing completion with `CountDownLatch`/`CompletableFuture`/message receipt and a timeout.
- Assert outcomes within the bounded window.
- Use a fake external adapter so no real emails are sent.
- Never rely on fixed `Thread.sleep` delays that cause flakiness.

### 11.5. AFTER_COMMIT Does Not Guarantee “Exactly Once”

In-JVM `@TransactionalEventListener(AFTER_COMMIT)` does not provide durable messaging or exactly-once guarantees between the database and a broker. The JVM can crash after DB commit yet before the listener finishes its external side effect. When events cannot be lost, a transactional outbox + relay with retries and idempotency is usually better. Real-commit tests cover only one part of that verification.

## 12. Testing Constraints and Transaction Isolation on a Real Database

### 12.1. H2 and PostgreSQL Can Behave Differently

H2 works well for JPA repository smoke tests and small lessons. However, when production uses PostgreSQL/MySQL/Oracle, test the following on the exact engine/version:
- Deferred constraints and transaction commit timing.
- Locking (`SELECT FOR UPDATE`), deadlocks, serialization failures.
- Isolation levels, MVCC snapshots, and phantom/non-repeatable reads.
- JSONB, native queries, stored procedures, database triggers.
- SQL dialects, identity/sequence generation, timezones/collations.
- Batch flush ordering, auto-generated IDs, transaction propagation effects.

Never assume from `@DataJpaTest` with embedded H2 that the application has been verified on the production engine.

### 12.2. Testcontainers with `@DataJpaTest`

With Testcontainers PostgreSQL, an **illustrative** annotation setup:

```java
@DataJpaTest
@AutoConfigureTestDatabase(replace =
        AutoConfigureTestDatabase.Replace.NONE)
@Testcontainers
class PostgresCommitContractTest {
    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16");
}
```

Requires `org.testcontainers:postgresql`, `org.testcontainers:junit-jupiter`, and `spring-boot-testcontainers` in test scope, plus a container runtime. This is not section 9's H2 project. When `@ServiceConnection` is active, Spring Boot obtains connection details from the container; `replace=NONE` prevents the test slice from swapping in H2.

The PostgreSQL image version here is an example; real projects should match production versions and follow security/supply-chain policies.

### 12.3. Testing Commit Failure from Deferred Constraints

On PostgreSQL, set up a table with a deferred constraint, insert violating data inside a transaction, and force commit via `TestTransaction.flagForCommit()` and `TestTransaction.end()`. **The exception assertion must wrap commit**, not only `repository.flush()`. This is a case where rolling-back tests asserting only in-transaction state miss the bug.

```java
TestTransaction.flagForCommit();

assertThatThrownBy(TestTransaction::end)
        .isInstanceOf(RuntimeException.class);
```

This snippet **illustrates only where the exception emerges**; exact exception types depend on the Spring transaction manager/JDBC driver, and the test requires a schema/data violating a deferred constraint. Once commit fails, the transaction is marked/closed; never reuse it as active. Design cleanup for any external/out-of-transaction test state.

### 12.4. Verifying Visibility with Another Connection/Transaction

When the requirement is “another consumer sees the row only after commit”, run:
1. T1 saves and flushes, keeping its transaction uncommitted.
2. T2 on **another connection** attempts to read and asserts it is absent (per configured isolation).
3. Commit T1.
4. T3 (a fresh reading transaction) reads again and asserts the row is visible.

This integration scenario requires two connections and bounded coordination. Never build T2 on the same `EntityManager` and treat it as an independent transaction. Under `READ_COMMITTED`, behavior differs from other isolation levels and snapshot semantics; define the contract upfront.

## 13. Web Layer and Transactional Tests: A Major Pitfall

### 13.1. MockMvc with a Test Transaction

A `@SpringBootTest` or `@WebMvcTest` using `MockMvc` normally runs request handling on the same test thread. If the controller invokes a `@Transactional(REQUIRED)` service, it can join the test transaction; rollback at test end can undo writes. While convenient for simulated HTTP integration tests, this can **suppress `AFTER_COMMIT` events**.

### 13.2. RANDOM_PORT with Real HTTP

With `@SpringBootTest(webEnvironment=RANDOM_PORT)`:
- The JUnit test method runs on the test thread.
- The HTTP client sends a request over loopback networking.
- The server handles it on a separate worker thread.
- Server transactions commit or roll back per application code, not the test-managed transaction.
- `@Transactional` on the test thread does not enclose server-side transactions.

If a POST test creates a row without cleanup, the row persists after the test. Never use test-level `@Transactional` as a cleanup strategy for real HTTP integration tests.

### 13.3. `@Transactional` on Controllers/Services Must Be Understood

An HTTP request might hit a non-`@Transactional` service, causing each repository method to open and commit its own transaction. Know the actual transaction boundaries invoked through Spring proxies. Never inspect `@Transactional` on a test class alone and assume you understand server-side service transactions.

### 13.4. JPA and Reactive Pipelines

Spring Data JPA uses imperative transaction managers and a ThreadLocal model; reactive R2DBC uses Reactor Context and `ReactiveTransactionManager`. This article covers JPA. Never blindly apply `TestTransaction`/thread-bound JPA rollback rules to R2DBC publishers assuming identical mechanics. If a WebFlux app still calls blocking JPA (discouraged on event loops), account carefully for thread scheduling and transaction boundaries.

## 14. Common Mistakes and Fixes

### 14.1. “Called saveAndFlush, So It Definitely Committed”

**False:** `flush` sends SQL before commit. Verify with `@AfterTransaction` after rollback/commit or `TestTransaction.end()`. If an error triggers only at commit, run a real commit in an appropriate test.

### 14.2. `@TransactionalEventListener` Does Not Fire in `@DataJpaTest`

**Common cause:** the outer test transaction rolled back. **Fix:** commit intentionally with `@Commit` or `TestTransaction.flagForCommit()`, and assert the listener in `@AfterTransaction`/after `end()`. Never downgrade a production listener to `@EventListener` just to make a test green if `AFTER_COMMIT` is required.

### 14.3. `@Commit` Applied, Yet Assertions Inside `@Test` Still See an Empty Listener

**Expected behavior:** `@Commit` changes how the transaction finishes **after** the test method exits. The `AFTER_COMMIT` listener has not run during the method body. Place assertions in `@AfterTransaction` or call `TestTransaction.end()` before asserting.

### 14.4. `@Commit` Causes Subsequent Tests to Fail on Unique Constraints

**Cause:** committed rows remain in the DB. **Fix:** clean up in `@AfterTransaction`/finally, or use isolated databases/schemas and unique fixtures. Never rely on test execution order.

### 14.5. `REQUIRES_NEW` Persists Even Though the Outer Test Rolls Back

**Cause:** T2 commits independently. **Fix:** if testing those semantics, assert post-boundary and clean up T2's row; if unintended, adjust propagation deliberately rather than blaming the framework.

### 14.6. `@SpringBootTest` Does Not Roll Back Like `@DataJpaTest`

**Cause:** `@SpringBootTest` does not enable test transactions by default. **Fix:** add test-level `@Transactional` only when appropriate; for post-commit tests, keep explicit real transactions + cleanup. Never put `@Transactional` on full HTTP tests expecting server writes to roll back.

### 14.7. `assertTimeoutPreemptively` Leaves Dirty Database State

**Cause:** code executes on a new thread without TestContext's ThreadLocal transaction. **Fix:** avoid preemptive timeouts inside transactional tests or isolate DB/cleanup; prefer bounded operations and same-thread timeouts where suitable.

### 14.8. JPA Constraint Fails in Production While H2 Tests PASS

**Cause:** different engine/dialect/constraint timing. **Fix:** Testcontainers matching production DB/version with real schema migrations, especially when testing deferred constraints, isolation, or triggers.

### 14.9. `@BeforeEach` Cleanup Does Not Help Post-Commit Tests

**Cause:** `@BeforeEach` inside a transactional test runs **inside T1**, so its cleanup can also roll back without removing previously committed data. **Fix:** use `@BeforeTransaction` or a cleanup service in its own transaction—or ideally an isolated test DB.

### 14.10. `@DirtiesContext` Does Not Wipe PostgreSQL Data

**Cause:** it only evicts the Spring context cache. **Fix:** use SQL/repository cleanup in a committing transaction or drop the schema/container. Avoid overusing context resets, which slow suites down.

### 14.11. `AFTER_COMMIT` Listener Writes an Audit Row, Yet the Row Vanishes

**Cause:** the post-commit callback may still share old thread-bound resources with no further commit. **Fix:** delegate audit writes to a `@Transactional(REQUIRES_NEW)` bean or a `TransactionTemplate` with new propagation, and verify in a separate transaction afterward.

### 14.12. Parallel Tests Produce Flaky Results

**Cause:** shared database rows, shared in-memory listener state, identical reference codes, and context caching. **Fix:** unique fixtures, cleanup, container isolation, avoiding shared mutable listener state, and disabling parallelism until concurrency isolation is ready.

### 14.13. Outer Transaction Query Sees Row While Another Connection Does Not

**Cause:** uncommitted data and isolation/MVCC. **Fix:** test with two independent transactions—commit T1, then open a new reading transaction. Never call `EntityManager.clear()` and think you created a new transaction.

### 14.14. Async Listener Makes Event Tests Flaky

**Cause:** asynchronous post-commit dispatch. **Fix:** await completion/event receipt with bounded timeouts, never `Thread.sleep`. With this project's synchronous in-memory listener, dispatch is deterministic and simple to test.

### 14.15. Transaction Ends in Error Yet Test Still Expects Commit

**Cause:** transaction marked rollback-only, commit-time constraint, or connection failure. **Fix:** assert failure around the commit boundary, not just around `save`; inspect root causes and clean up state.

## 15. Rollback vs. Commit Decision Matrix

| Test Goal | Default Rollback? | Real Commit Needed? | Reason |
| --- | --- | --- | --- |
| Basic entity mappings, repository queries | Suitable | Not necessarily | Checking inside a transaction suffices |
| Immediate constraints checked on flush | Usually suitable | Not necessarily | `flush` triggers the error early |
| Deferred constraints in production DB | Insufficient | Yes | Error may surface only at commit |
| `@TransactionalEventListener(AFTER_COMMIT)` | Insufficient | Yes | Callback runs only after commit |
| `@TransactionalEventListener(AFTER_ROLLBACK)` | Suitable | No | Must exercise the rollback path |
| Unique ID generation via IDENTITY | Usually suitable | Not necessarily | IDs may allocate before commit |
| Visibility across two connections | Insufficient | Yes | Must close T1 and read from T2/T3 |
| Outbox/CDC relay | Insufficient | Yes, in an isolated DB | Relay reads committed rows |
| Does `REQUIRES_NEW` survive outer rollback? | Not covered | Inner transaction commits | Must verify propagation semantics |
| Real HTTP POST with `RANDOM_PORT` | No test rollback wraps server | App commits itself | Clean up outside the test |
| Unit tests for business math | No Spring context needed | No | Use pure JUnit/Mockito |
| Email/message side effects | DB rollback insufficient | Not strictly needed to unit-test adapter | Use fake external services + idempotency |

A healthy test suite combines **many cheap/isolated rollback tests** with **a focused set of real-commit integration tests**. Neither switch the entire suite to `@Commit`, nor spin up a full database for pure Java logic.

## 16. Review Exercises

1. Explain why `repository.saveAndFlush(...)` can succeed in `@DataJpaTest` while `@AfterTransaction` finds no row.
2. Write a `@Commit` test that asserts committed data in `@AfterTransaction` and cleans up even if the assertion fails.
3. Rewrite that test using `@Rollback(false)`; state commit timing and annotation scope.
4. Use `TestTransaction.flagForCommit()`/`end()` to commit mid-test, then start a fresh reading transaction via `TestTransaction.start()`.
5. A `@Transactional(REQUIRED)` service returns after `saveAndFlush` inside test T1. Has the service committed? What does it depend on?
6. Write an `AFTER_COMMIT` event listener. Why doesn't it run when the test rolls back?
7. Explain why an `AFTER_COMMIT` listener writing DB audit records should call a `REQUIRES_NEW` service.
8. Use `REQUIRES_NEW` in a writer and test outer rollback. Verify the row survives outer rollback and delete it.
9. Run a `@SpringBootTest(RANDOM_PORT)` POST creating an entity and inspect transaction boundaries; why doesn't test-level `@Transactional` delete the server-created row?
10. State the difference between H2 immediate constraints and PostgreSQL `DEFERRABLE` constraints; where can exceptions occur?
11. Design a T1/T2 scenario checking uncommitted/committed data visibility on a real database with defined isolation.
12. Write an outbox relay test observing events only after commit without publishing to a production broker.
13. Explain why `@DirtiesContext` is not a cleanup strategy for a shared PostgreSQL database.
14. If JUnit uses `assertTimeoutPreemptively` inside a `@Transactional` test, what data can escape rollback?
15. List ways to prevent a real-commit test from breaking subsequent or parallel tests.

Success means being able to identify **which transaction is open, who manages it, when it ends, which beans join it, and which data/side effects survive rollback** before writing an assertion.

## 17. Review Checklist for Transactional Tests

- [ ] Does the test truly require a commit to verify the behavior?
- [ ] Aware that `@DataJpaTest` rolls back by default while `@SpringBootTest` does not enable `@Transactional` automatically?
- [ ] Distinguished `save`/`flush`/`saveAndFlush`/`commit`/`rollback`?
- [ ] Avoided inferring from a same-persistence-context query that a row committed?
- [ ] Used `@Commit`/`@Rollback(false)` only with an active test-managed transaction?
- [ ] Placed commit-dependent assertions inside `@AfterTransaction` or after `TestTransaction.end()`?
- [ ] For `@TransactionalEventListener(AFTER_COMMIT)`, waited for an actual commit?
- [ ] Does any listener writing DB rows post-commit need `REQUIRES_NEW`?
- [ ] For `REQUIRES_NEW`, accounted for independent transactions and cleanup?
- [ ] For `NOT_SUPPORTED`, understood services/repositories commit their own transactions?
- [ ] For async or HTTP server threads, avoided relying on test ThreadLocal rollback?
- [ ] Avoided `assertTimeoutPreemptively` inside transactional tests?
- [ ] Guaranteed committed test data is cleaned up even when assertions fail?
- [ ] Isolated databases/schemas/fixtures so tests never write to production?
- [ ] Used unique IDs and avoided shared mutable event state for parallel tests?
- [ ] Verified whether H2 fits the risk or Postgres/Testcontainers is required?
- [ ] Tested deferred constraints/triggers/CDC integration with real commit boundaries?
- [ ] Configured `@Sql` transaction mode and cleanup explicitly?
- [ ] Avoided mistaking `@DirtiesContext` for database cleanup?
- [ ] Executed a clean Maven/JUnit suite and examined root causes of commit failures?

**Conclusion:** Default rollback in `@DataJpaTest` is an **invaluable test-isolation tool**, yet it does not test commits by itself and can hide behaviors occurring **after commit**. `saveAndFlush` verifies SQL and immediate constraints without closing the transaction. When targeting `AFTER_COMMIT` events, deferred constraints, cross-transaction visibility, or outbox/CDC, explicitly test commits with `@Commit`/`TestTransaction`/`@AfterTransaction` alongside proper databases and cleanup. Simultaneously account for transactions outside outer rollback such as `REQUIRES_NEW`, HTTP server threads, async tasks, and external side effects.

## 18. Official References

- Spring Framework 6.2 — TestContext Transaction Management (test-managed vs. Spring-managed transactions; rollback/commit; TestTransaction; lifecycle; preemptive timeouts): https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html
- Spring Boot 3.5 Javadoc — `@DataJpaTest` (transactional + default rollback): https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/orm/jpa/DataJpaTest.html
- Spring Boot 3.5 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Framework 6.2 — `@Commit`: https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-commit.html
- Spring Framework 6.2 — `@Rollback`: https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-rollback.html
- Spring Framework 6.2 — `@BeforeTransaction` / `@AfterTransaction`: https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-beforetransaction.html
- Spring Framework 6.2 — TestTransaction API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/test/context/transaction/TestTransaction.html
- Spring Framework 6.2 — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
- Spring Framework 6.2 — `@TransactionalEventListener` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html
- Spring Data JPA — Transactionality and Repository methods: https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html
- Spring Data JPA — `JpaRepository.saveAndFlush` API: https://docs.spring.io/spring-data/jpa/docs/current/api/org/springframework/data/jpa/repository/JpaRepository.html
- PostgreSQL — Constraint Types / DEFERRABLE: https://www.postgresql.org/docs/current/ddl-constraints.html
- Spring Boot Testcontainers — Service Connections: https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html