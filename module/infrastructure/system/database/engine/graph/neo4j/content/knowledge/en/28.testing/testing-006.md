# Testing Commit, Rollback, Write Conflicts, and Retries in Neo4j

## 1. Why can't transaction testing stop at checking Cypher queries?

In a **Neo4j property graph**, nodes and relationships are created, modified, or deleted inside **transactions**. A Cypher query may work on a small dataset yet cause production failures when two requests write concurrently, a transaction rolls back, a connection drops right at commit time, or the Java Driver retries a callback after a transient error.

This lesson belongs to the **Testing** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module. The goal is to build repeatable tests that verify **data state after commit and rollback**, catch **lost updates, uniqueness conflicts, and deadlocks**, and evaluate **retry** behavior in the **Neo4j Java Driver** and services using **Spring Data Neo4j**.

After this lesson, you will be able to:

1. Verify that a write transaction commits completely and is observable from another Session.
2. Test both explicit rollbacks and rollbacks triggered when a callback/application throws an exception.
3. Schedule two concurrent transactions deterministically using barriers instead of relying on `Thread.sleep()`.
4. Distinguish **write conflict**, **constraint violation**, **deadlock**, and **indeterminate commit outcome** errors.
5. Verify that direct property increments avoid *lost updates* and recognize unsafe read–compute–write patterns.
6. Design **bounded, retry-safe operations** without external side effects inside the transaction.
7. Separate unit tests, repository integration tests, and concurrency/failure tests for Neo4j applications.

> **Version note:** Java examples use the `org.neo4j.driver` API style with `executeRead`/`executeWrite` in Java Driver 5.x/6.x and JUnit 5. Container examples pin Neo4j **5.26** for a stable illustration environment; in your project, align DBMS, Driver, Testcontainers, and Spring Data Neo4j versions. Error codes and locking details may vary by release.

## 2. Transaction contracts to verify

Transactions provide **ACID** properties, yet tests must state accurately what is guaranteed:

| Property / behavior | Appropriate test | What must NOT be inferred |
| --- | --- | --- |
| **Atomicity** | One transaction performs two writes and fails: neither commits | Does not mean individual statements can never fail |
| **Consistency** | Constraints and business invariants still hold after commit | The DB does not automatically enforce arbitrary multi-node app rules |
| **Isolation** | Two independent Sessions run concurrently and observe results per isolation level | Neo4j is not serializable by default |
| **Durability** | After commit, another Session reads the result; test recovery if operationally required | A post-commit read test alone does not prove full power-loss crash recovery |
| **Idempotency** | Repeating a request with the same key leaves a single entity/edge | Retrying a callback with external side effects is not automatically safe |

Neo4j uses **read committed** as its default isolation level: transactions cannot read **uncommitted** changes from other transactions, yet repeated reads within one transaction **can observe newly committed data** from other transactions. Therefore, tests must not silently assume an immutable snapshot like some MVCC configurations in other DBMSs.

**Decisive rule for transaction tests:** re-read state using **an independent transaction/Session after the operation under test completes**. Never treat a record returned via `RETURN` inside a `SET` statement as proof that commit succeeded.

## 3. Test scenario matrix

| ID | Scenario | Expectation to assert |
| --- | --- | --- |
| C01 | `SET` followed by explicit `commit()` | A new Session observes the change |
| C02 | Create node and relationship in one transaction, then commit | Both exist together |
| R01 | `SET` followed by explicit `rollback()` | Data retains the original value after rollback |
| R02 | `executeWrite` callback throws an exception after running `SET` | None of the callback's changes are committed |
| R03 | Write multiple nodes, then one step violates a constraint | The entire transaction rolls back when commit fails |
| I01 | Session A reads, B writes uncommitted, A reads again | A must not see B's uncommitted data |
| I02 | B commits between two reads by A | A may observe two different values |
| W01 | Two requests read the same old value and write a client-computed value | A **lost update** can occur |
| W02 | Two requests execute `SET x.count = x.count + 1` | Both increments are preserved when updating the same property |
| U01 | Two requests create a node with the same unique business key | Both cannot commit duplicate keys while the constraint is active |
| D01 | Two transactions acquire locks on two nodes in opposite orders | Deadlock may occur; aborted transaction leaves no partial commit |
| RT01 | Transient error inside a managed transaction | Driver may re-run the entire callback per retry policy |
| RT02 | Client does not know whether commit succeeded | Replaying the request with an idempotency key creates no second record |
| TO01 | Transaction exceeds configured timeout | Reports error/aborts appropriately; resources are released |

**Do not cram everything into one giant test.** Each test must verify one clear contract with deterministic setup and teardown; concurrency tests must control timing to minimize *flaky tests*.

## 4. Practice environment: real Neo4j in Testcontainers

### 4.1. Why mocking the Driver is not enough

Mocks are useful for unit-testing how a service calls a repository, but they cannot prove:

- Cypher syntax validity and accurate property type mapping.
- Real transaction commit and rollback behavior.
- Real enforcement of unique constraints.
- How two concurrent writes to the same node wait on locks or fail.
- Deadlocks, timeouts, routing, or Driver behavior over Bolt.

Therefore, transaction tests must run against **real Neo4j**, ideally in a dedicated container. Never run this lesson's cleanup statements against a production database.

### 4.2. Test dataset

Use two small node types:

```text
(:TxAccount {id: 'A', balance: 100, version: 0})
(:TxAccount {id: 'B', balance: 200, version: 0})

(:TxRequest {requestId, amount, state})
```

- `TxAccount` supports testing same-node updates, lock ordering, and rollbacks.
- `TxRequest` supports uniqueness and idempotency testing.
- `id` and `requestId` are **business keys**; never use internal node IDs for assertions.

Create appropriate constraints:

```cypher
CREATE CONSTRAINT tx_account_id_unique IF NOT EXISTS
FOR (a:TxAccount)
REQUIRE a.id IS UNIQUE;

CREATE CONSTRAINT tx_request_id_unique IF NOT EXISTS
FOR (r:TxRequest)
REQUIRE r.requestId IS UNIQUE;
```

Constraints are a mandatory part of the test environment; relying solely on `MERGE` and expecting two concurrent writers never to create duplicates is insufficient to prove data integrity.

### 4.3. JUnit 5 + Testcontainers fixture

The code below shows an integration test class. Your project needs compatible test dependencies: **JUnit Jupiter**, `org.testcontainers:neo4j`, `org.testcontainers:junit-jupiter`, and `org.neo4j.driver:neo4j-java-driver`. Lock versions in your build or project BOM; do not mix versions casually just because examples share similar APIs.

```java
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.Neo4jContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

import java.util.Map;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.*;

@Testcontainers
class Neo4jTransactionIT {

    @Container
    static final Neo4jContainer<?> NEO4J =
        new Neo4jContainer<>("neo4j:5.26")
            .withAdminPassword("test-password");

    private static Driver driver;

    @BeforeAll
    static void initDriverAndSchema() {
        driver = GraphDatabase.driver(
            NEO4J.getBoltUrl(),
            AuthTokens.basic("neo4j", "test-password"));
        driver.verifyConnectivity();

        try (Session session = newSession()) {
            // Each constraint creation runs in its own transaction.
            session.run("""
                CREATE CONSTRAINT tx_account_id_unique IF NOT EXISTS
                FOR (a:TxAccount) REQUIRE a.id IS UNIQUE
                """).consume();
            session.run("""
                CREATE CONSTRAINT tx_request_id_unique IF NOT EXISTS
                FOR (r:TxRequest) REQUIRE r.requestId IS UNIQUE
                """).consume();
        }
    }

    @BeforeEach
    void resetFixture() {
        try (Session session = newSession()) {
            session.executeWrite(tx -> {
                // Only delete dedicated test labels on the test database.
                tx.run("MATCH (a:TxAccount) DETACH DELETE a").consume();
                tx.run("MATCH (r:TxRequest) DETACH DELETE r").consume();
                tx.run("""
                    CREATE (:TxAccount {
                      id: 'A', balance: 100, version: 0
                    })
                    """).consume();
                tx.run("""
                    CREATE (:TxAccount {
                      id: 'B', balance: 200, version: 0
                    })
                    """).consume();
                return null;
            });
        }
    }

    private static Session newSession() {
        return driver.session(SessionConfig.forDatabase("neo4j"));
    }

    private long balance(String id) {
        try (Session session = newSession()) {
            return session.executeRead(tx ->
                tx.run("""
                    MATCH (a:TxAccount {id: $id})
                    RETURN a.balance AS balance
                    """, Map.of("id", id))
                .single()
                .get("balance").asLong());
        }
    }

    @AfterAll
    static void closeDriver() {
        if (driver != null) driver.close();
    }

    // Place the @Test methods from the following sections inside this class.
}
```

**Fixture notes:**

- `@Container` starts Neo4j for the test class; requires Docker or a compatible container runtime.
- Pin the image tag so results do not shift unexpectedly when a `latest` tag moves.
- Every `Session` is closed; `Driver` is shared across the class.
- `@BeforeEach` resets baseline data to a deterministic state. **Do not run tests sharing this fixture in parallel** if they can delete or mutate each other's data; use a separate database/container per test or disable parallel execution on the class.
- `DETACH DELETE` targets only test labels inside a **dedicated container**. Never adapt this fixture into a cleanup script on production data.

## 5. Testing commit: observing state from another Session

### 5.1. Explicit transaction commit

Add this method to `Neo4jTransactionIT`:

```java
@Test
void commitMakesUpdateVisibleToAnotherSession() {
    try (Session writer = newSession()) {
        try (var tx = writer.beginTransaction()) {
            tx.run("""
                MATCH (a:TxAccount {id: 'A'})
                SET a.balance = 120
                """).consume();

            tx.commit();
        }
    }

    // balance() opens a new Session after commit has completed.
    assertEquals(120L, balance("A"));
}
```

**Why call `consume()` before `commit()`?** Write statements must be transmitted and consumed cleanly within the transaction lifecycle. Checking `RETURN a.balance` inside the writing transaction only proves that transaction sees its own changes—**it does not prove commit occurred**.

### 5.2. Atomicity across multiple operations

A simulated transfer must update both accounts in the **same transaction**:

```java
@Test
void transferCommitsBothChangesTogether() {
    try (Session session = newSession()) {
        session.executeWrite(tx -> {
            tx.run("""
                MATCH (a:TxAccount {id: 'A'})
                SET a.balance = a.balance - 30
                """).consume();
            tx.run("""
                MATCH (b:TxAccount {id: 'B'})
                SET b.balance = b.balance + 30
                """).consume();
            return null;
        });
    }

    assertAll(
        () -> assertEquals(70L, balance("A")),
        () -> assertEquals(230L, balance("B"))
    );
}
```

This tests **two updates committing together**. The example does not solve full financial domain requirements: in production, you also need sufficient-funds checks, protection against *write skew*, exact monetary arithmetic, and retry/idempotency handling.

## 6. Testing rollback: changes must vanish after failure

### 6.1. Explicit rollback

```java
@Test
void explicitRollbackRestoresOriginalValue() {
    try (Session session = newSession()) {
        try (var tx = session.beginTransaction()) {
            tx.run("""
                MATCH (a:TxAccount {id: 'A'})
                SET a.balance = 1
                """).consume();

            tx.rollback();
        }
    }

    assertEquals(100L, balance("A"));
}
```

After rollback, a new Session observes the original value. Reading the value from **inside the active transaction before rollback** would give a misleading test result.

### 6.2. Exception inside a managed transaction

```java
@Test
void uncheckedExceptionRollsBackManagedTransaction() {
    assertThrows(IllegalStateException.class, () -> {
        try (Session session = newSession()) {
            session.executeWrite(tx -> {
                tx.run("""
                    MATCH (a:TxAccount {id: 'A'})
                    SET a.balance = 0
                    """).consume();
                throw new IllegalStateException("Reject this operation");
            });
        }
    });

    assertEquals(100L, balance("A"));
}
```

Because the callback does not finish normally, the managed transaction **does not commit** the change. When testing Spring applications, also distinguish `@Transactional` rollback rules; see Section 14.

### 6.3. Rollback must cover the entire transaction, not just the last statement

Suppose a transaction writes:

```cypher
MATCH (a:TxAccount {id: 'A'})
SET a.balance = 10;
```

Then it attempts to create another `TxAccount` node with `id = 'A'`, violating the unique constraint:

```cypher
CREATE (:TxAccount {id: 'A', balance: 999});
```

When the transaction fails and rolls back, **the earlier `balance = 10` update must not commit**. The test must open another Session and confirm `balance = 100`. Note: constraint errors belong to the class of errors you **should not blindly retry**; they typically indicate invalid data or logic bugs, unlike transient deadlocks.

## 7. Read committed: what can be read between two transactions?

Not every concurrency test tests *write conflicts*. A foundational step is distinguishing **uncommitted** from **committed** writes.

| Step | Transaction A | Transaction B |
| --- | --- | --- |
| T1 | Starts, reads `balance = 100` | |
| T2 | | Starts, `SET balance = 80`, **not yet committed** |
| T3 | A reads again | B still uncommitted |
| T4 | | B commits |
| T5 | A reads again | |

At T3, A **must not read B's uncommitted value 80**. Depending on locking, a query may wait or observe the previously committed value. After T4, A **can** read `80` on a fresh read—an example of a **non-repeatable read** under read committed.

**How to design the test:** coordinate read/write ordering with `CountDownLatch` or explicit synchronization, always apply timeouts, and close every transaction in `finally`/`try-with-resources`. Never write tests like "spawn 100 threads and guess who runs first"; that is a stress test, not a deterministic semantic test.

## 8. Lost updates: two requests reading stale state and overwriting each other

### 8.1. Updating from a previously read value

Suppose two transactions both try to increment `A.balance` from 100 to 101. Each reads `100`, computes `old + 1` in Java, and writes the computed value:

```cypher
MATCH (a:TxAccount {id: $id})
RETURN a.balance AS oldValue;
```

Then:

```cypher
MATCH (a:TxAccount {id: $id})
SET a.balance = $computedNewValue;
```

If both read `100` and send `computedNewValue = 101`, the final value is **101** even though two requests asked to increment. Write locks only serialize the two writes; they **cannot fix** the stale `101` already computed by the application.

### 8.2. Test enforcing the "both read before either writes" schedule

```java
@Test
void staleClientSideComputationCanLoseAnUpdate()
        throws Exception {
    CountDownLatch bothRead = new CountDownLatch(2);
    ExecutorService pool = Executors.newFixedThreadPool(2);

    Callable<Long> update = () -> {
        try (Session session = newSession();
             var tx = session.beginTransaction()) {
            long old = tx.run("""
                MATCH (a:TxAccount {id: 'A'})
                RETURN a.balance AS balance
                """).single().get("balance").asLong();

            bothRead.countDown();
            if (!bothRead.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                    "Both readers did not reach the barrier");
            }

            // Pass an externally computed value instead of directly
            // referencing the property on the right-hand side of SET.
            tx.run("""
                MATCH (a:TxAccount {id: 'A'})
                SET a.balance = $newValue
                """, Map.of("newValue", old + 1))
                .consume();
            tx.commit();
            return old;
        }
    };

    try {
        Future<Long> first = pool.submit(update);
        Future<Long> second = pool.submit(update);
        assertEquals(100L, first.get(15, TimeUnit.SECONDS).longValue());
        assertEquals(100L, second.get(15, TimeUnit.SECONDS).longValue());
    } finally {
        pool.shutdownNow();
    }

    // Both computed 100+1: one increment was lost.
    assertEquals(101L, balance("A"));
}
```

The barrier ensures **both transactions have read** the old value before either starts its write. Under unusual lock contention or timeouts, the test can still fail due to infrastructure conditions; inspect logs before concluding isolation behavior changed. Never use this test's algorithm to increment counters in production.

## 9. Direct property-dependent increments

Neo4j documents that Cypher can acquire a **write lock before reading** when updating a property with a **direct dependency**:

```cypher
MATCH (a:TxAccount {id: 'A'})
SET a.balance = a.balance + 1;
```

Because of that dependency, two concurrent increment operations on the same node are synchronized appropriately so neither increment is lost as described above.

### Testing two Sessions incrementing concurrently

```java
@Test
void directPropertyIncrementPreservesBothUpdates()
        throws Exception {
    ExecutorService pool = Executors.newFixedThreadPool(2);
    CountDownLatch start = new CountDownLatch(1);

    Callable<Void> increment = () -> {
        if (!start.await(10, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Start was not released");
        }
        try (Session session = newSession()) {
            session.executeWrite(tx -> {
                tx.run("""
                    MATCH (a:TxAccount {id: 'A'})
                    SET a.balance = a.balance + 1
                    """).consume();
                return null;
            });
        }
        return null;
    };

    try {
        Future<Void> first = pool.submit(increment);
        Future<Void> second = pool.submit(increment);
        start.countDown();
        first.get(15, TimeUnit.SECONDS);
        second.get(15, TimeUnit.SECONDS);
    } finally {
        pool.shutdownNow();
    }

    assertEquals(102L, balance("A"));
}
```

The result `102` confirms that **both property increment requests** are reflected in this scenario. It **does not prove** serializability for arbitrary multi-node invariants. When updates depend on earlier reads or span multiple nodes without locking a shared resource, design explicit synchronization.

### 9.1. Caution with `WITH`

The following query separates reading from updating:

```cypher
MATCH (a:TxAccount {id: 'A'})
WITH a, a.balance AS oldBalance
SET a.balance = oldBalance + 1;
```

Do not assume this carries the same lost-update protection as `SET a.balance = a.balance + 1`. For complex read–compute updates, verify locking behavior or use optimistic locking/version checks and test under concurrency.

## 10. Unique constraints: two transactions competing for the same business key

### 10.1. Contention schedule

Two clients concurrently attempt to create:

```cypher
CREATE (:TxRequest {requestId: 'req-01', amount: 50});
```

If `TxRequest.requestId` has an active unique constraint, **two nodes with the same key cannot both commit**. Typically one transaction succeeds while the other receives a constraint error (or waits and errors per the execution schedule).

Never assert in advance that "thread 1 always wins"; scheduling is governed by the OS, driver, locks, and DBMS.

### 10.2. `MERGE` + constraint for idempotency

```cypher
MERGE (r:TxRequest {requestId: $requestId})
ON CREATE SET
    r.amount = $amount,
    r.state = 'NEW'
RETURN r.requestId AS requestId,
       r.amount AS storedAmount;
```

Repeating the same `requestId` matches the existing record instead of creating a duplicate. However, if a second request reuses the same ID with a different `amount`, the query keeps the old value; **the application must detect same-ID payload conflicts** and return a conflict error rather than silently treating it as success.

### 10.3. Repeatable idempotency test

```java
@Test
void repeatedRequestIdDoesNotCreateDuplicateNode() {
    for (int i = 0; i < 2; i++) {
        try (Session session = newSession()) {
            session.executeWrite(tx -> {
                tx.run("""
                    MERGE (r:TxRequest {requestId: $requestId})
                    ON CREATE SET r.amount = $amount, r.state = 'NEW'
                    """, Map.of(
                        "requestId", "req-01",
                        "amount", 50
                    )).consume();
                return null;
            });
        }
    }

    try (Session session = newSession()) {
        long count = session.executeRead(tx ->
            tx.run("""
                MATCH (r:TxRequest {requestId: 'req-01'})
                RETURN count(r) AS count
                """).single().get("count").asLong());
        assertEquals(1L, count);
    }
}
```

This tests **sequential replays**. To test concurrent inserts, open two Sessions and submit the same key behind a barrier, then assert **no two nodes committed**; handle the case where one request fails with a constraint error rather than requiring both callbacks to succeed.

## 11. Deadlocks: testing lock-order conflicts

A deadlock occurs when transactions form a wait cycle:

```text
Transaction A                         Transaction B
SET account A (holds lock on A)       SET account B (holds lock on B)
          |                                     |
          +---- waits for lock B    waits for lock A ----+
```

A schedule to trigger a deadlock in tests:

1. Transaction A starts and updates node `A`, ensuring the query result is consumed.
2. Transaction B starts and updates node `B`.
3. Use a barrier to confirm **each holds its own write lock**.
4. Have A attempt to update `B` and B attempt to update `A`.
5. Neo4j detects the wait cycle and aborts one transaction to break the deadlock.

In modern Java Drivers, this raises an error with code `Neo.TransientError.Transaction.DeadlockDetected`; newer Neo4j generations also expose **GQLSTATUS** and diagnostic metadata. **Never assert exact error message text**, as wording may vary between versions.

What to assert:

- No **uncommitted** changes from the aborted transaction remain in the database.
- The transaction can be safely retried under the allowed policy.
- No thread hangs indefinitely; every `Future.get`/barrier uses a timeout.
- The final state violates no invariants or constraints, regardless of which transaction won.

**Note:** Deadlock tests are sensitive to timing, runtime, and locking internals. Isolate them in an integration/failure test suite, pin versions, capture diagnostic logs, and never use `sleep(100)` to "guarantee" one thread arrives first. When using managed transactions, the driver may retry and mask the original deadlock error; to observe the error directly, use an **explicit transaction** or count callback invocations.

## 12. Retries: what exactly needs testing?

### 12.1. Managed vs. explicit transactions

| Mode | Common Java Driver API | Retry rule |
| --- | --- | --- |
| Managed read | `session.executeRead(callback)` | Driver may automatically retry callback on eligible errors |
| Managed write | `session.executeWrite(callback)` | Driver may automatically retry the entire callback |
| Explicit | `session.beginTransaction()`, `commit()`/`rollback()` | Application must handle retries if needed |
| Auto-commit query | `session.run(...)` | Do not assume managed-transaction retry semantics |

The Driver only retries **errors classified as eligible**, bounded by `maxTransactionRetryTime` and actual API behavior. Unique constraint violations, Cypher syntax errors, invalid input, or authorization failures **must not** be treated as transient just to keep retrying.

### 12.2. Callbacks can execute multiple times

```java
try (Session session = newSession()) {
    session.executeWrite(tx -> {
        tx.run("""
            MATCH (a:TxAccount {id: 'A'})
            SET a.balance = a.balance + 1
            """).consume();
        return null;
    });
}
```

On eligible errors, the driver discards the failed transaction attempt and re-invokes the callback in a new transaction. **Changes from the rolled-back attempt do not accumulate**, but side effects **outside Neo4j** are not rolled back by the driver:

```java
// Unsafe:
session.executeWrite(tx -> {
    // paymentGateway.charge(...); // may be called multiple times!
    tx.run("CREATE (:TxEvent {kind: 'CHARGED'})").consume();
    return null;
});
```

Prerequisites for safe retries:

- The callback produces no external side effects, or external side effects enforce their own **idempotency**.
- Check/increment/write logic keyed by business ID is safe under concurrent writers.
- Never share a `Session` or `Transaction` across threads.
- Never retry deterministic errors infinitely (syntax, constraint, or data validation).
- Set timeouts/budgets for requests, transactions, and retries; monitor retry rates.

### 12.3. Two-layer retry testing

**Unit tests** for an application-owned retry policy can use a fake port that emits deterministic transient errors before succeeding; assert invocation counts, backoff, and budget exhaustion. Unit tests do not prove the Java Driver retries a real Bolt error.

**Integration tests** use real Neo4j and controlled transient failures (such as a barrier-induced deadlock or test-infrastructure fault injection). Assert:

1. No changes remain from rolled-back attempts.
2. Final post-retry state matches exact business expectations.
3. Re-running the callback does not duplicate external side effects.
4. Once the retry budget is exhausted, the error propagates and resources close cleanly.

**Do not simulate transient errors by throwing arbitrary `RuntimeException`s** and expecting the Driver to retry: not every exception is retryable. To test driver retry decisions, verify the exception contract for your exact driver version.

### 12.4. Errors at commit time can create uncertainty

If a client loses its connection **right around commit**, it may not know whether the server committed or aborted. A failing callback alone does not guarantee the record was not created.

This is why **idempotency keys** are mandatory for critical entity/edge creation commands. For example, creating an order with a stable `requestId`:

```cypher
MERGE (r:TxRequest {requestId: $requestId})
ON CREATE SET r.amount = $amount, r.state = 'NEW'
RETURN r.requestId, r.amount, r.state;
```

When retrying the same business request, look up by `requestId`, verify the stored payload matches, and only then return success. Never run a fresh `CREATE` with a new random ID on each retry.

## 13. Optimistic locking, versions, and multi-node invariants

### 13.1. Comparing version to catch stale writes

One strategy reads `balance` and `version`, runs business calculations, and updates only if the version still equals the read value:

```cypher
MATCH (a:TxAccount {id: $id})
WHERE a.version = $expectedVersion
SET a.balance = $newBalance,
    a.version = a.version + 1
RETURN a.id AS id, a.version AS version;
```

The application inspects the **returned row count**:

- One row: the version matched and the update executed inside the transaction.
- Zero rows: the node does not exist **or** the version mismatched; distinguish these if business rules require.

**Concurrency warning:** Adding `WHERE a.version = ...` does not automatically turn every read–write pattern into a safe *compare-and-swap* under all schedules. Verify locking/contention behavior on **your target Neo4j version**, or acquire an appropriate write lock **before reading/checking version**, and run concurrency tests confirming only one writer with the same version succeeds. Never treat this snippet as automatic proof of serializable isolation.

### 13.2. Multi-node invariants

Business rule example: "an on-call team must always have at least one member on duty". Two transactions both read two staff members and each updates **a different node** to off-duty. Each sees the invariant satisfied at check time, yet the combined result leaves zero people on duty. This is **write skew**.

Tests should:

1. Seed exactly two nodes with `onDuty = true`.
2. Let A and B both read state before either writes.
3. Have each write to a different node.
4. Check whether the final state violates the invariant.
5. Add a shared guard-node locking protocol to both write flows; re-run to prove the invariant holds.

A unique constraint on a single key cannot replace locking/coordination protocols governing **multi-node** invariants.

## 14. Spring Data Neo4j: testing `@Transactional` boundaries

In Spring applications, `@Transactional` manages transactions when methods are invoked through a **Spring proxy** backed by an appropriate transaction manager. Test real use cases instead of inferring behavior from annotations:

```java
@Service
public class AccountService {
    private final AccountRepository repository;

    public AccountService(AccountRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void changeThenReject(String id) {
        repository.setBalance(id, 1L);
        throw new IllegalStateException("Business rejection");
    }
}
```

Integration tests should invoke **the `AccountService` bean from the Spring container**, catch the exception, and re-read using **a fresh transaction**:

```java
assertThrows(IllegalStateException.class,
    () -> accountService.changeThenReject("A"));

assertEquals(100L, accountQueryRepository.getBalance("A"));
```

`AccountRepository` and `AccountQueryRepository` are application-defined interfaces. This snippet illustrates the test structure, not a fully wired Spring project.

Key pitfalls:

- **Self-invocation:** calling a `@Transactional` method on the same object via `this.method()` can bypass the proxy.
- **Checked exceptions:** Spring's default rollback rules differ from unchecked exceptions; configure `rollbackFor` or explicit policies.
- **`@Transactional` on test methods:** many test frameworks auto-roll back test transactions on completion, which can hide missing commits in production code. To **test real commits**, let the test manage boundaries explicitly and re-read from another Session/transaction.
- **Mixing Java Driver and SDN:** opening an independent Driver transaction inside a Spring-managed service does not guarantee participation in the same transaction without proper integration setup.
- **Relationship mapping:** verify via real Cypher and constraints that edges were actually written or rolled back, rather than comparing objects inside a persistence context.

## 15. Writing less flaky concurrency tests

### 15.1. Use barriers instead of guessed sleep durations

| Scheduling approach | Reliability | Notes |
| --- | --- | --- |
| `Thread.sleep(200)` hoping the other thread wrote | Low | Sensitive to CI hardware, OS scheduler, and DB latency |
| `CountDownLatch` confirming each thread passed a step | Better | Supports timeouts and cleanup paths if a thread errors |
| `CyclicBarrier` synchronizing multiple schedule points | Good if designed carefully | Avoid barrier deadlocks when one thread throws |
| Controlled fault injection (network/DB) | Fits failure testing | Requires dedicated infrastructure and test isolation |
| Repeated stress runs | Surfaces probabilistic bugs | Does not replace tests with explicit expected states |

Never stop at "no exception thrown"; always verify **node counts, edge counts, properties, and invariants** after all transactions complete.

### 15.2. Timeouts and cleanup

Concurrency tests should include:

- `Future.get(timeout, TimeUnit.SECONDS)` instead of unbounded waits.
- `CountDownLatch.await(timeout, unit)`.
- `try-with-resources` for every Session and Transaction.
- `ExecutorService.shutdownNow()` in `finally` when tests fail.
- An isolated Neo4j test instance so other tests cannot mutate contested nodes.
- Logging error codes and root causes without logging passwords or sensitive data.

Tests may be **non-deterministic regarding which thread wins**. Assert "one request succeeded and invariants still hold" rather than asserting a specific winning thread name, unless the test deliberately enforces deterministic ordering.

## 16. Investigation checklist for failures

When a commit/rollback/retry test fails, check in order:

1. **Right database?** Is the test targeting `neo4j` or another database, and pointing at the container's URI?
2. **Constraints present and ONLINE?** Did `CREATE CONSTRAINT` finish before the race test began?
3. **Right transaction boundary?** Did a statement accidentally run via auto-commit `session.run()` instead of the shared transaction?
4. **Asserting after commit?** Does the verification query read from a separate Session after the writer finished, rather than pre-commit results?
5. **Swallowed exceptions?** Did code inside a managed callback catch an exception and return success anyway?
6. **Separate Sessions and threads?** Sharing one Session across threads does not represent two independent transactions.
7. **Real concurrent schedule?** Did barriers confirm both transactions actually read before writing?
8. **Which error category?** Deadlock/transient, constraint violation, connection timeout, transaction timeout, or Java callback bug?
9. **Did retry mask the failure?** Did `executeWrite` silently retry, leaving the test seeing only final success?
10. **Miscounted results?** `count(*)` after `OPTIONAL MATCH` differs from `count(node)`; cross-check against real data.
11. **Do server and driver versions match test assumptions?** Locking, error codes, syntax, and defaults can change.
12. **Is test data isolated?** Did another test reset fixtures or clean up while the concurrency test was running?

During development, `SHOW TRANSACTIONS` (with sufficient privileges) helps inspect active/waiting transactions. For slow queries, `EXPLAIN`/`PROFILE` reveals cardinality, index usage, and relationship expansion cost, though good query plans never replace concurrency tests.

## 17. Practice exercises with suggested solutions

### Exercise 1 — Committed or only visible inside the transaction?

A test runs `SET a.balance = 200 RETURN a.balance`, receives `200`, and concludes the transaction committed. Is that conclusion valid?

**Answer:** No. A transaction always sees its own writes. You must wait for `commit()` to succeed and re-read from a separate Session/transaction to verify.

### Exercise 2 — Transaction with two updates followed by failure

A and B start with `balance = 100` and `200` respectively. A transaction sets A to `70` and B to `230`, then throws an exception before committing. What values must be observed after rollback?

**Answer:** A remains `100` and B remains `200`. Tests must assert **both** values, not just one side.

### Exercise 3 — Two callbacks incrementing balance

Two transactions both read `100` and execute `SET a.balance = $value` with `value = 101`. Why can the result still end up `101`? Rewrite the Cypher statement to perform a direct increment.

**Answer:**

```cypher
MATCH (a:TxAccount {id: 'A'})
SET a.balance = a.balance + 1;
```

Values pre-read and computed externally are no longer linked to the property at write time. Direct increments allow Neo4j to protect updates using its documented locking mechanism.

### Exercise 4 — Two requests with the same ID

Two requests share `requestId = 'req-01'` with amounts `50` and `80` respectively. Are a unique constraint and `MERGE` enough to treat both as valid?

**Answer:** No. They prevent two nodes with the same ID, but the second request must be treated as a **payload conflict** rather than silently overwriting or ignoring the mismatch.

### Exercise 5 — Deadlock testing

Why can a test with two threads updating A and B in opposite orders using `Thread.sleep(100)` pass intermittently and fail intermittently?

**Answer:** Thread scheduling, networking, and Neo4j timing are never guaranteed by a fixed sleep interval. Use barriers to confirm each transaction acquired its first lock before attempting the second, with explicit timeouts and cleanup.

### Exercise 6 — Retry callback sending emails

`executeWrite` creates a node successfully, calls an email API, and then the server/driver reports a transient error. The driver retries the callback. What is the risk?

**Answer:** The email may be sent multiple times even though the failed transaction attempt rolled back. Move external side effects outside the callback, or use an outbox/idempotency pattern with business constraints.

### Exercise 7 — Spring test auto-rollback

A `@SpringBootTest` puts `@Transactional` on the test method. The test calls a service to create a node, queries it successfully, and then the test framework rolls everything back. Has the test proved the real commit use case?

**Answer:** No. It only proved the node was visible inside the test's transaction. Write an integration test that actually commits and reads from a new transaction, or structure transaction tests with the appropriate Spring testing tools.

### Exercise 8 — Designing a relationship test matrix

An application models `(:User)-[:MEMBER_OF]->(:Team)`. Design three tests for an idempotent, atomic add-member operation.

**Hint:** (1) Commit creates exactly one relationship and reads it back from another Session; (2) throwing an exception after creating the relationship rolls it back; (3) two concurrent writers using the same business key cannot commit duplicate equivalent relationships when protected by appropriate constraints/deduplication. Verify **endpoint nodes**, edge direction, and relationship key properties.

## 18. Summary

Testing Neo4j transactions does not stop at verifying a query returns expected records. **Commits** must be confirmed from another transaction; **rollbacks** must erase **all uncommitted changes of the failed transaction**; **concurrent writes** must be tested with controlled schedules and real constraints.

In particular, **read committed does not mean serializable**. Computing from stale read values can cause *lost updates*, whereas `SET n.value = n.value + 1` follows specialized locking rules. The Java Driver's **managed transactions** may retry callbacks, so write logic must be retry-safe, and idempotency keys are essential when commit outcomes are uncertain. With Spring Data Neo4j, validate real transaction boundaries, proxies, and rollbacks via integration tests rather than relying on annotations alone.

A dependable test suite combines **JUnit + Neo4j Testcontainers**, isolated fixtures, timed barriers, post-commit/post-rollback verification reads, invariant checks, and version-aware error tracking. This provides a solid foundation for keeping Java applications on Neo4j safe under concurrent load and real-world failures.

### References

- [Neo4j Java Driver Manual – Transactions](https://neo4j.com/docs/java-manual/current/transactions/)
- [Neo4j Java Driver Manual – Query advanced topics](https://neo4j.com/docs/java-manual/current/query-advanced/)
- [Neo4j Operations Manual – Concurrent data access](https://neo4j.com/docs/operations-manual/current/database-internals/concurrent-data-access/)
- [Neo4j Cypher Manual – Constraints](https://neo4j.com/docs/cypher-manual/current/constraints/)
- [Testcontainers – Neo4j module](https://java.testcontainers.org/modules/databases/neo4j/)
- [Spring Data Neo4j Reference](https://docs.spring.io/spring-data/neo4j/reference/)
