# Write Contention, Deadlocks, and Contention-Reduction Strategies

In **Neo4j**, multiple transactions can concurrently read and modify a **property graph** of nodes, relationships, and properties. For instance, an order request updates an order's status and links a customer to a product while other tasks record payment history or synchronize data. When these transactions need to modify the same resources, they can end up waiting on locks, hitting deadlocks, or producing business discrepancies if the program reads and writes improperly.

This lesson belongs to the **Transactions** chapter of module **DATABASE_ENGINE_GRAPH_NEO4J**. The goal is to clearly recognize **write contention**, **deadlocks**, and **lost updates**, then select the right strategy across **Cypher**, the **Neo4j Java Driver**, and **Spring Data Neo4j** applications. Examples use nodes, relationships, and locks for illustration; no external libraries beyond Neo4j are required unless explicitly noted.

## 1. Distinguishing Three Easily Confused Phenomena

| Phenomenon | What happens? | Primary consequence | Direction to address |
|---|---|---|---|
| **Write contention / lock contention** | Transaction B needs a resource whose lock is held by transaction A | B **waits** for A to finish, increasing latency; not necessarily an error | Shorten transactions, reduce operations touching the same resource |
| **Deadlock** | A holds lock X, waits for Y; B holds lock Y, waits for X (or a longer cycle) | Neither can make progress; Neo4j detects and aborts one transaction | Standardize lock acquisition order, narrow the contested resource set, retry transient errors |
| **Lost update** | Multiple transactions read the same stale value, then update based on it | One update is overwritten even without any deadlock | Express value-dependent updates properly in Cypher; use locks/synchronization strategies when needed |

**Not every slow transaction is deadlocked.** If only B waits for A, A can still finish and release the lock. A **deadlock** requires a **wait cycle**. On the other hand, a transaction that succeeds while writing the wrong total due to a *lost update* is still a bug, even though no exception was returned.

## 2. How Does Neo4j Manage Transactions and Locks?

### 2.1. A Transaction Is an ACID Unit

A transaction encompasses changes that are **committed together** or **rolled back together**. Neo4j provides ACID properties; when a transaction encounters a fatal error, uncommitted changes are not partially retained. Operations on the graph, indexes, and schema all run inside transactions.

Neo4j's default isolation level is **read committed**:

- Uncommitted changes from other transactions are never read as committed data.
- Simply **reading** a node or relationship normally does **not** hold a write lock blocking other transactions from modifying it. Thus *non-repeatable reads* can occur—reading the same property twice inside one transaction and observing two different committed values.
- **Write** operations require locks to protect data consistency. Locks are generally held until the transaction **commits** or **rolls back**.
- Read committed does **not** automatically protect every "read condition → compute → write result" business rule against concurrent updates.

When stricter isolation is needed for a read–write sequence, the design must proactively acquire a shared lock or use appropriate concurrency control. Never assume that placing multiple queries inside one transaction gives **serializable** isolation.

### 2.2. Write Operations and Associated Locks

| Operation | Notable lock |
|---|---|
| Modifying node properties or labels | **NODE** write lock |
| Modifying relationship properties | **RELATIONSHIP** write lock |
| Deleting a node | **NODE** lock and related integrity checks |
| Creating or deleting a relationship | May require locks/synchronization on both endpoint nodes and relationship structures |
| Creating/modifying indexed or constrained data | May incur additional locks to maintain internal structures |

**Do not assume every relationship creation/deletion acquires identical exclusive node locks.** Neo4j uses different strategies for *sparse* and *dense* nodes; for dense nodes, relationship updates may be synchronized at finer granularity. Internal lock details can change across versions and store formats. This lesson focuses on **shared resources and consistent update ordering** rather than depending on a fixed internal lock list.

### 2.3. Why Longer Transactions Bottleneck More Easily

Suppose transaction T1 locks node A and then makes an external HTTP call before committing. While waiting on the network, other transactions wanting to modify A may be blocked. Locks are released when the transaction ends, not immediately after each **`SET`** statement.

Common causes of overly long transactions include: calling external APIs while holding a transaction open; processing huge lists in a single write; scanning too many nodes before updating; waiting for user input; or failing to close sessions/transactions properly.

In Java applications, design transactions to contain only the database operations requiring atomicity plus concise computation. Run HTTP calls, email sending, large file processing, and steps that do not need locks **outside** the transaction callback.

## 3. Illustrating Routine Write Contention

Create the data once on a **test database**:

~~~cypher
CREATE CONSTRAINT demo_txn_account_id IF NOT EXISTS
FOR (a:DemoTxnAccount)
REQUIRE a.id IS UNIQUE;
~~~

~~~cypher
CREATE
  (:DemoTxnAccount {id: 'A', counter: 0}),
  (:DemoTxnAccount {id: 'B', counter: 0});
~~~

Two sessions concurrently update account A:

~~~cypher
MATCH (a:DemoTxnAccount {id: 'A'})
SET a.counter = a.counter + 1
RETURN a.counter;
~~~

If T1 has not finished and T2 needs to update A, T2 may wait for the lock held by T1. Once T1 commits or rolls back, T2 proceeds. This is **lock contention**; it is **not** a deadlock because T1 does not need any lock held by T2.

When a transaction increments a counter using **`SET a.counter = a.counter + 1`**, Cypher recognizes the direct dependency between the read value and the written value on the same node; Neo4j automatically acquires the write lock **before reading the value used for the update**. This protects simple increments from *lost updates*. Verify correctness for complex expressions or cases where values are extracted earlier elsewhere.

## 4. Deadlock: A Wait Graph Forming a Cycle

A deadlock can form in four steps:

1. T1 modifies **A**, holding lock A.
2. T2 modifies **B**, holding lock B.
3. T1 then needs B, which is held by T2.
4. T2 then needs A, which is held by T1.

~~~mermaid
flowchart LR
  T1["Transaction T1 holds lock A"] -->|"waits for lock B"| T2["Transaction T2 holds lock B"]
  T2 -->|"waits for lock A"| T1
~~~

Neo4j performs **deadlock detection**. When a wait cycle is detected, the system terminates one of the involved transactions to break the cycle; that transaction is rolled back. A deadlock error has the legacy code:

~~~text
Neo.TransientError.Transaction.DeadlockDetected
~~~

In Neo4j releases from **5.25** onward, the error may also include **GQLSTATUS 50N05**. This is a **transient retryable error**, yet retrying does not fix the root cause if every attempt keeps competing for the same resources in opposite orders.

### 4.1. Reproducing a Deadlock in Two Cypher Shell Sessions

**Run only in the test database** where A and B were created in Section 3. Open two separate **cypher-shell** terminals; **`:begin`**, **`:commit`**, and **`:rollback`** are client control commands, not pure Cypher syntax.

**Session 1 — T1:**

~~~text
:begin
~~~

~~~cypher
MATCH (a:DemoTxnAccount {id: 'A'})
SET a.counter = a.counter + 1;
~~~

**Session 2 — T2:**

~~~text
:begin
~~~

~~~cypher
MATCH (b:DemoTxnAccount {id: 'B'})
SET b.counter = b.counter + 1;
~~~

**Back in T1**, request an update to B:

~~~cypher
MATCH (b:DemoTxnAccount {id: 'B'})
SET b.counter = b.counter + 1;
~~~

This command will wait because T2 still holds lock B. **Then in T2**, request an update to A:

~~~cypher
MATCH (a:DemoTxnAccount {id: 'A'})
SET a.counter = a.counter + 1;
~~~

While both locks are held and both commands wait on each other, one transaction will be rejected due to deadlock. The aborted side should finish/roll back the transaction per client state; the surviving side can proceed and commit. Clean up any open transactions with **`:commit`** or **`:rollback`** as appropriate. Exact timing and which side gets aborted depend on scheduling, so this is a conditional demonstration rather than a deterministic test yielding the exact same message every time.

**How to prevent wait cycles:** have every business flow that updates both A and B update A **before** B. Then one transaction waits on A right at the start; it has not acquired B to form a reverse wait cycle. However, internal locks taken by Neo4j (especially via **`MERGE`** and index/relationship updates) can be subtler, so consistent ordering **greatly reduces risk** rather than guaranteeing zero deadlocks forever.

## 5. Lost Update: Corrupt Data Even Without Deadlocks

### 5.1. Mistake: Moving the Old Value Outside the Locked Update Path

A common trap:

~~~cypher
MATCH (a:DemoTxnAccount {id: 'A'})
WITH a, a.counter AS oldCounter
// Other calculation steps could happen here.
SET a.counter = oldCounter + 1
RETURN a.counter;
~~~

If both transactions read **`oldCounter = 0`** and then wait until the write step, both may end up writing **`1`** instead of the desired **`2`**. The reason is that the **`SET`** expression no longer directly depends on reading **`a.counter`** at update time: the old value was captured into a variable earlier. The same issue occurs when Java reads a value, computes in application code, and sends **`SET a.counter = $newValue`**.

For simple increments, prefer:

~~~cypher
MATCH (a:DemoTxnAccount {id: 'A'})
SET a.counter = a.counter + 1
RETURN a.counter AS counter;
~~~

Neo4j recognizes the direct read dependency inside **`SET`** and locks the node before reading to update. For data where the property might be missing, define a clear initial value and test the expression on your active version, such as **`coalesce(a.counter, 0) + 1`**.

### 5.2. When Multi-Step Read–Compute–Write Is Necessary

If a rule must read a property, run multiple computations, and then update, do not assume placing everything inside one **`MATCH`** suffices. Options include:

- Rewrite as a direct update on the property being read so Neo4j detects the dependency and locks at the right moment.
- When you truly need to protect a read–write sequence, proactively acquire a write lock **before reading**. Neo4j documentation describes writing a temporary property and immediately deleting it in the same transaction, though this is a special technique with write overhead that requires testing; do not overuse it.
- Design **optimistic concurrency control** with a version column and application-side conflict handling, alongside a mechanism ensuring the condition is properly checked within a locked region. Merely comparing a version in an unlocked read and writing later is **not enough** to prevent lost updates.

Example of the **temporary lock marker** technique per Neo4j documentation, to be used only if the model genuinely requires holding a lock before reading values:

~~~cypher
MATCH (a:DemoTxnAccount {id: 'A'})
SET a._lockMarker = true
REMOVE a._lockMarker
WITH a, a.counter AS oldCounter
// Keep calculations brief inside the current transaction.
SET a.counter = oldCounter + 1
RETURN a.counter;
~~~

Removing the temporary property **does not release the lock early**: the write lock is held until the transaction ends. When updating multiple resources, consistent lock ordering is still required. Do not use this pattern for a simple addition already served by **`SET a.counter = a.counter + 1`**.

## 6. `MERGE`, Constraints, and Contention When Writing Linked Data

**`MERGE`** finds or creates a graph pattern. Under concurrent writes, distinguish **node identification** from **relationship creation**:

~~~cypher
CREATE CONSTRAINT demo_txn_customer_id IF NOT EXISTS
FOR (c:DemoTxnCustomer)
REQUIRE c.id IS UNIQUE;
~~~

~~~cypher
MERGE (c:DemoTxnCustomer {id: $customerId})
ON CREATE SET c.createdAt = datetime()
RETURN c;
~~~

A **uniqueness constraint** protects node identity when multiple transactions concurrently create customers. **`MERGE`** by itself does not replace a uniqueness constraint on an identifier property; without a constraint, duplicate nodes with the same business key can appear under concurrent load.

When **both endpoint nodes are already identified**, the pattern:

~~~cypher
MATCH (c:DemoTxnCustomer {id: $customerId})
MATCH (p:DemoTxnProduct {sku: $sku})
MERGE (c)-[:DEMO_FOLLOWS]->(p);
~~~

uses locking mechanisms to prevent two transactions from concurrently creating duplicate **relationships matching that pattern** between the two located nodes. However, because `MERGE` must search, potentially acquire additional locks, and re-verify, **complex `MERGE` patterns can increase contention or deadlocks** in heavy write workloads.

**Do not mechanically replace `MERGE` with `CREATE`**: `CREATE` unconditionally creates new elements and is suitable only when input data is guaranteed to require new creation or external deduplication exists. A practical strategy:

1. **`MERGE` nodes** by a business key backed by a uniqueness constraint to avoid duplicate nodes.
2. **`MATCH`** existing source and target nodes using indexes/constraints.
3. **`MERGE` relationships** when idempotent behavior is needed; use **`CREATE`** when the requirement is to record a new relationship and business rules permit multiple relationships.
4. For large lists, batch writes and process endpoints in a consistent order to reduce transactions competing on the same nodes.

**A node with many relationships is not automatically an "unoptimizable hotspot."** Neo4j employs locking strategies for dense nodes and relationships based on store format. What you need to measure is whether transactions actually touch the same node/relationship, the same internal structures, or the same identifier data.

## 7. Effective Contention-Reduction Strategies

| Strategy | How to apply | Trade-offs / limitations |
|---|---|---|
| **Fixed write ordering** | When modifying multiple accounts, sort by ID and update in the same order across all flows | Reduces wait cycles; cannot control every internal lock Neo4j takes |
| **Short transactions** | Keep only writes and computations needing atomicity; close transactions immediately | Must move non-database logic outside the transaction region |
| **Reduce transactions hitting "hot nodes"** | Partition work by business key; single queue per ID | May add queuing latency, but lowers lock contention and retries |
| **Narrow, indexed write steps** | Use uniqueness constraints/range indexes to locate nodes quickly before writing | Indexes also carry write and storage overhead |
| **Appropriately sized batches** | Split multi-million-row loads into moderate transactions | Too large holds locks too long; too small increases commit overhead |
| **Record events instead of updating one central counter** | Create separate events and aggregate periodically, or shard counters | Computing totals is more complex; requires accepting eventual consistency |
| **Bounded retries** | Retry deadlocks/transient errors with backoff and jitter | Smooths transient failures, though aggressive retries can worsen overload |
| **Throttle parallelism** | Limit workers per partition/key; tune concurrent write transactions | Total throughput may rise even with fewer workers; measure empirically |

### 7.1. Ordering Resources Before Updating

When a transaction updates multiple nodes, use a **stable** business key (e.g., `accountId`) to bring operations into a consistent order:

~~~cypher
UNWIND $accountIds AS accountId
WITH DISTINCT accountId
ORDER BY accountId
MATCH (a:DemoTxnAccount {id: accountId})
SET a.counter = a.counter + 1
RETURN a.id AS id, a.counter AS counter;
~~~

Note: **`ORDER BY`** sorts rows entering the next clause by ID; internal lock acquisition, statistics, and the query planner must still be verified at runtime. If strict lock ordering is critical, a clearer approach is for the application to sort IDs and execute updates sequentially within **the same transaction**, enforcing that rule across **all** related write flows. Never use Neo4j's internal ID order as a long-term business key.

### 7.2. Shortening Lock Hold Times

Choose transaction boundaries around a **business invariant**: for example, "deducting points and recording the point-change log must commit together." Do not drag payment API calls, email sending, or waiting for user responses inside the transaction. For very large data batches, split into sensible chunks; batches must be safely rerunnable.

### 7.3. Mitigating Hotspots Instead of Just Increasing Retries

If every request updates **`(:Statistics {id: 'global'})`**, all transactions converge on one hotspot even if the graph has millions of other nodes. Consider sharded counters, event logs, or periodic aggregation; each involves trade-offs in read speed, consistency, and complexity.

**Increasing threads indefinitely** usually increases wait times and deadlocks rather than boosting throughput. Benchmark different concurrency levels and measure throughput, p95/p99 latency, retry rates, and lock wait times before settling on a configuration.

## 8. Retrying Properly in the Neo4j Java Driver

### 8.1. Managed Transactions with `executeWrite`

The Java Driver provides **`Session.executeWrite()`** to run transactions with **automatic retry on transient errors**; after the configured maximum retry window, the driver throws an exception if still unsuccessful. Illustrative example for modern Neo4j Java Driver releases:

~~~java
import java.time.Duration;
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.TransactionConfig;

// Driver is created once and can be shared across threads.
long increment(Driver driver, String accountId) {
    var txConfig = TransactionConfig.builder()
        .withTimeout(Duration.ofSeconds(5))
        .withMetadata(Map.of("operation", "increment-account-counter"))
        .build();

    try (var session = driver.session(
            SessionConfig.forDatabase("neo4j"))) {
        return session.executeWrite(tx -> {
            var result = tx.run("""
                MATCH (a:DemoTxnAccount {id: $id})
                SET a.counter = a.counter + 1
                RETURN a.counter AS counter
                """, Map.of("id", accountId));
            return result.single().get("counter").asLong();
        }, txConfig);
    }
}
~~~

Points to note:

- **`Driver`** can be shared across threads, whereas **`Session` is not thread-safe**; create a separate session per thread/request and close it with **try-with-resources**.
- Inside the callback, execute **Cypher**, consume the **`Result`**, and return a plain value. Never return an unconsumed **`Result`** outside the transaction.
- The driver may **re-run the callback**. Therefore, do not send emails, call payment gateways, or mutate external in-memory state inside the callback; avoid non-rollbackable side effects.
- A deadlocked transaction is **rolled back**, so on a successful retry the direct increment applies cleanly to the fresh transaction. Still, for business operations that must not execute twice when commit status is ambiguous, use an **idempotency key** and data-level deduplication.
- The **transaction timeout** in the example caps transaction duration; it does not eliminate deadlocks or replace proper update ordering.

With **explicit transactions** via **`session.beginTransaction()`**, the Java Driver **does not automatically retry callbacks like `executeWrite`**. If you build custom retries, you must start a **new transaction** per attempt, catch only eligible errors (such as **`RetryableException`**), enforce bounded attempts and **backoff + jitter**, and never retry infinitely or retry syntax errors and non-transient constraint violations.

### 8.2. Retryable Transactions and Side Effects Outside the Database

Suppose a transaction callback writes an order and calls a payment gateway. When a deadlock rolls back the transaction, the driver retries the callback and calls the payment gateway again: the payment system may receive two requests while Neo4j commits only one order. Therefore:

1. The Neo4j transaction writes only the data requiring atomicity, such as the order and processing status.
2. Use a **unique request code** or **idempotency key** backed by a constraint to recognize already-processed requests.
3. Coordinate external side effects via post-commit processing or a **transactional outbox** paired with retryable, idempotent delivery on the receiver.

If business-level "exactly-once" guarantees are required, **automatic retries are not enough**: you must design duplicate detection and handle ambiguous commit outcomes caused by dropped connections.

### 8.3. Spring Data Neo4j and Spring Transactions

In **Spring Data Neo4j**, related changes can be placed inside a service method managed by **`@Transactional`**:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class AccountService {
    private final AccountRepository repository;

    AccountService(AccountRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void updateBoth(String firstId, String secondId) {
        // Repository or Neo4jClient executes write operations
        // inside Spring's transaction.
        // All flows must agree on lock ordering by ID.
    }
}
~~~

**`@Transactional`** defines the Spring transaction commit/rollback boundary; it **does not automatically provide deadlock retries** like the Java Driver's **`executeWrite()`** callback. If you add Spring-layer retries (e.g., Spring Retry), configure them so **each attempt gets a fresh transaction**, catch the proper translated transient exception types from the data layer, and avoid uncontrolled nested retries. Also remember that internal calls within the same bean instance may bypass the **`@Transactional`** proxy depending on Spring configuration.

## 9. Observing and Diagnosing Waiting Transactions

### 9.1. Viewing Running Transactions

~~~cypher
SHOW TRANSACTIONS
YIELD transactionId, username, status, currentQueryId,
      currentQuery, elapsedTime, waitTime, activeLockCount
RETURN transactionId, username, status, currentQueryId,
       currentQuery, elapsedTime, waitTime, activeLockCount
ORDER BY waitTime DESC;
~~~

Signs to look for:

- **`status = Blocked`** or rising **`waitTime`**: the transaction may be waiting on a resource.
- High **`elapsedTime`** with low **`waitTime`**: likely spending CPU, I/O, data processing, or waiting elsewhere; do not jump to assuming a deadlock.
- High **`activeLockCount`**: the transaction holds many locks, though lock count alone **does not** prove a problem.
- **`currentQueryId`** identifies the query for inspecting active locks in environments with appropriate privileges.

To view active locks held by a query:

~~~cypher
CALL dbms.listActiveLocks($queryId)
YIELD mode, resourceType, resourceId
RETURN mode, resourceType, resourceId;
~~~

The **`$queryId`** parameter comes from **`currentQueryId`** in **`SHOW TRANSACTIONS`**. This procedure requires appropriate admin privileges and can vary slightly across Neo4j releases. Do not assume every application role can inspect other users' transactions; visibility depends on **`SHOW TRANSACTION`** permissions. Only use **`TERMINATE TRANSACTIONS`** after assessing impact on running work and with valid operational authority.

### 9.2. Distinguishing Errors and Timeout Settings

| Symptom | Meaning | Action to take |
|---|---|---|
| **`DeadlockDetected`** | Neo4j detected a wait cycle and aborted one transaction to unblock progress | Apply bounded retries; locate reverse-ordered update chains |
| **Lock acquisition timeout** | Transaction waited on a lock past the limit | Find transactions holding locks too long; narrow write regions |
| **Transaction timeout** | Transaction exceeded execution time limit | Optimize queries, batch work, and verify sensible limits |
| **Constraint violation** | Write violated uniqueness/existence/type rule | Fix data or logic; do not blindly retry like a transient error |
| **High wait time, no error** | Transactions complete after waiting | Measure latency and throughput; identify hotspots |

In Neo4j server configuration, **`db.transaction.timeout`** caps transaction duration (`0` typically means no default limit enabled); **`db.lock.acquisition.timeout`** caps the wait time for acquiring each lock (`0` disables lock timeouts by default). These two settings are distinct, and a driver-specified transaction timeout can override the server default. Tune settings based on your version and operational procedures, and **never raise timeouts as the primary fix for deadlocks**.

### 9.3. Establishing Before/After Observability

Record metrics across representative load windows:

- Transaction success/failure rates; deadlock counts and transient-error retry counts.
- **p50/p95/p99** write transaction latency and commit throughput per second.
- **`waitTime`**, count of blocked transactions, longest-running transactions, and contended lock groups.
- Top write queries, nodes/relationships per transaction, and batch sizes.
- Scan times, **DB Hits**, index usage via **`EXPLAIN`/`PROFILE`**, and frequency of touching the same entity.

Track transaction metadata and request IDs to correlate application logs with database logs. Log only necessary fields and avoid leaking sensitive parameters into monitoring logs.

## 10. Contention-Handling Practice Exercises

### Exercise 1 — Reading a Wait Graph

Suppose T1 holds lock A and waits for B, T2 holds B and waits for C, and T3 holds C and waits for A.

**Question:** Is there a deadlock? What if T3 stops waiting for A and commits?

*Hint:* Draw edges **T1 → T2**, **T2 → T3**, **T3 → T1** to identify the cycle. Once a wait edge disappears, re-evaluate whether the remaining transactions can advance.

### Exercise 2 — Fixing a Lost-Update Increment

Find the bug in this pattern:

~~~cypher
MATCH (n:DemoTxnAccount {id: 'A'})
WITH n, n.counter AS oldValue
SET n.counter = oldValue + 1;
~~~

Rewrite it as a direct increment and explain why **capturing the old value in a variable** can lose updates under concurrent writes.

### Exercise 3 — Designing Write Ordering

A group of services concurrently transitions statuses on two `Account` nodes with IDs **`A`** and **`B`**: service S1 updates A before B, while service S2 updates B before A.

**Task:** Propose a shared update order, commit placement, retry policy, and concurrent-load test plan. Explain why merely raising the transaction timeout is insufficient.

### Exercise 4 — Deciding on `MERGE` and Constraints

An ingestion job runs **`MERGE (c:Customer {id: $id})`** concurrently across multiple workers without a uniqueness constraint. Identify the duplicate-data risk and draft the appropriate constraint creation command before running the import, accounting for any pre-existing duplicates.

### Exercise 5 — Incident Triage Workflow

In production, **`Blocked`** transactions rise, **`waitTime`** rises, and write p95 increases, yet no **`DeadlockDetected`** error appears. List three observations to pinpoint the cause and two low-risk changes to try before altering the graph structure.

## Summary

When multiple transactions write to the same graph, **lock contention** can slow down the system, **deadlocks** require a wait cycle and typically roll back one transaction, and **lost updates** can corrupt data without any deadlock. In Neo4j, the effective approach is to:

1. Identify exactly where operations touch the same nodes/relationships and lock paths.
2. Write value-dependent updates in a form Cypher can protect; place constraints on business identifiers.
3. Keep transactions short, standardize write ordering, and distribute work around hotspots.
4. Use Java Driver managed transactions for bounded transient-error retries with retry-safe callbacks; manage retries explicitly if using Spring Data Neo4j.
5. Measure **`waitTime`**, errors, throughput, and p95 before concluding that schema or timeout changes are needed.

### Official References

- [Neo4j Operations Manual – Concurrent data access: locking, deadlocks, and lost updates](https://neo4j.com/docs/operations-manual/current/database-internals/concurrent-data-access/)
- [Neo4j Operations Manual – Database transactions](https://neo4j.com/docs/operations-manual/current/database-internals/transaction-management/)
- [Neo4j Operations Manual – Show and terminate transactions](https://neo4j.com/docs/operations-manual/current/database-internals/show-and-terminate-transactions/)
- [Neo4j Java Driver Manual – Run your own transactions](https://neo4j.com/docs/java-manual/current/transactions/)
- [Neo4j Cypher Manual – MERGE and concurrent relationship merges](https://neo4j.com/docs/cypher-manual/current/clauses/merge/)
