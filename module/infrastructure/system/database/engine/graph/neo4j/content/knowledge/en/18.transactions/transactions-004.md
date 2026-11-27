# Default Isolation Level and Version-Specific Anomalies in Neo4j

## 1. Context: An ACID Transaction Does Not Mean an Immutable Snapshot

In Neo4j's **property graph** model, a transaction can read and modify nodes, relationships, properties, indexes, or constraints. Cypher executes these operations inside a **transaction** to guarantee atomicity and maintain system consistency. However, when multiple applications access the graph concurrently, they can still observe changes differently depending on timing and encounter write conflicts.

This lesson is part of the **Transactions** chapter of module `DATABASE_ENGINE_GRAPH_NEO4J`, focusing on the **default isolation level**, anomalies under concurrent execution, mitigation strategies, and details that must be **verified against the exact Neo4j/Driver version**. These scenarios arise in inventory systems, seat reservations, account relationships, dependency models, and applications using the **Java Driver** or **Spring Data Neo4j**.

After this lesson, you will be able to:

1. Explain the exact meaning of **read committed** and distinguish it from **repeatable read**, **snapshot isolation**, and **serializable**.
2. Recognize *dirty read*, *non-repeatable read*, *phantom*, *lost update*, *write skew*, *missing/double read*, and *deadlock*.
3. Understand when Cypher automatically acquires a write lock before reading a property to avoid lost updates.
4. Choose appropriate data models, queries, locks, constraints, and retries.
5. Cross-check documentation for your exact server version, Java Driver, and cluster setup rather than guessing from how other databases behave.

> **Version scope:** Documentation for Neo4j 4.4, the 5.x series, and the current Operations Manual all describe **read committed** as the default isolation level. Examples of execution operators, detailed locking behavior, error status codes, and Java APIs may differ by release. Therefore, conclusions about *isolation* should be kept separate from conclusions about *internal implementation*.

## 2. The Default Isolation Level: Read Committed

Official Neo4j documentation specifies the **read-committed isolation level** as the default. This has two key implications:

- A transaction **cannot read uncommitted changes made by another transaction**. Consequently, *dirty reads* from uncommitted updates are not permitted.
- Once another transaction commits, a subsequent read **may see** the new value, even if the first reading transaction has not finished. The default mode **does not promise that all reads in a transaction operate on an immutable snapshot of the graph**.

For example, if transaction A reads `account.balance = 100`, transaction B updates it to `80` and commits, A may re-read and observe `80`. A will still never observe `80` **before B commits**.

### 2.1. Distinguishing the Concepts

| Concept | Core guarantee | Is it Neo4j's default? |
| --- | --- | --- |
| **Read uncommitted** | May see uncommitted data from another transaction | No |
| **Read committed** | Never sees uncommitted data; repeated reads may differ | **Yes** |
| **Repeatable read** | Re-reading the same data within a transaction avoids changes by other transactions | Not guaranteed by default by Neo4j as a selectable SQL level |
| **Snapshot isolation** | Reads in a transaction typically see a consistent snapshot via MVCC | Should not be assumed from read committed |
| **Serializable** | Transactions produce effects equivalent to some serial execution order | Not the default level; requires properly synchronizing shared resources to achieve equivalent business guarantees |

The names in this table are **isolation concepts**. They do not imply that Neo4j provides a `SET TRANSACTION ISOLATION LEVEL` syntax to freely switch among all these levels like some relational database systems.

### 2.2. What Does ACID Protect?

**Atomicity** ensures a transaction either commits all of its changes or rolls back. **Durability** ensures committed data can be recovered. **Isolation** defines how transactions observe each other's data. Therefore, an **ACID** system can still allow *non-repeatable reads* under **read committed** without contradicting ACID.

Neo4j automatically acquires **write locks** when modifying entities, and locks are typically held until the transaction ends. Locks prevent two transactions from modifying the exact same resource simultaneously, but **do not automatically serialize every read–check–write workflow**.

## 3. Anomalies to Distinguish

| Phenomenon | Example in a property graph | Default read committed |
| --- | --- | --- |
| **Dirty read** | A reads a value B just `SET`, before B commits | **Not allowed** |
| **Non-repeatable read** | A reads the same property twice and gets 2 values because B committed in between | **Can occur** |
| **Phantom** | A re-runs a `MATCH` pattern and sees added/removed nodes or relationships due to B committing | **Can occur under read committed semantics** |
| **Lost update** | A and B both read an old value and overwrite with results computed from that stale value | **Can occur** if no lock is taken before the dependent read |
| **Write skew** | Two transactions both check a condition spanning multiple nodes, then modify **two different nodes**, breaking a shared invariant | **Risk requiring preventative design** |
| **Missing/double read** | An index scan skips or reads an entity twice when another transaction changes the indexed key | **Can occur** with certain index scan operators |
| **Deadlock** | A holds lock on node X, waits for Y; B holds lock on Y, waits for X | **Can occur** under lock contention; this is a concurrency error, not a *read anomaly* |

Rows marked "can occur" describe **possibilities**, not that every query run will reproduce them. Actual outcomes depend on execution schedule, operator types, lock order, indexes, and Neo4j version.

## 4. Setting Up the Practice Environment

The examples use a dedicated label `IsolationCounter` so other business data is unaffected. Run them on a **test database**, opening **two independent sessions**, labeled **A** and **B**. One window executing multiple auto-commit queries in sequence is **not equivalent** to keeping a transaction open.

Create a shared entity for both sessions to read/write:

```cypher
CREATE CONSTRAINT isolation_counter_id IF NOT EXISTS
FOR (c:IsolationCounter)
REQUIRE c.id IS UNIQUE;
```

```cypher
MERGE (c:IsolationCounter {id: 'shared'})
SET c.value = 0, c.version = 0
RETURN c.id, c.value, c.version;
```

To inspect state after each experiment:

```cypher
MATCH (c:IsolationCounter {id: 'shared'})
RETURN c.value AS value, c.version AS version;
```

**Tooling note:** Lines like `:begin`, `:commit`, and `:rollback` in interactive examples are **transaction management commands of certain interactive clients**, such as Cypher Shell. They are **not Cypher clauses** and cannot be sent verbatim via the Java Driver. With the Java Driver, use `session.beginTransaction()` to explicitly keep a transaction open. Session A and Session B must each use an independent transaction.

## 5. Two Fundamental Schedules: No Dirty Reads, Yet Non-Repeatable Reads Are Possible

### 5.1. Dirty Reads Are Prevented

Suppose the counter starts at `0`.

| Time | Transaction A | Transaction B |
| --- | --- | --- |
| T1 | Begin transaction | Begin transaction |
| T2 | Read `value`, sees `0` | |
| T3 | | Set `value = 99`, **uncommitted** |
| T4 | Re-read; **must not see uncommitted value `99`** | |
| T5 | | Rollback |
| T6 | Re-read; final value remains `0` | |

At T4, a specific query may wait on a lock or see the previously committed value depending on resources and execution plan; the essential guarantee is that **B's uncommitted update is never returned**.

### 5.2. Non-Repeatable Read

Test with two sessions when the counter starts at `0`:

**Session A**, inside an uncommitted transaction:

```cypher
MATCH (c:IsolationCounter {id: 'shared'})
RETURN c.value AS firstRead;
```

**Session B**, after A finishes reading, executes and **commits**:

```cypher
MATCH (c:IsolationCounter {id: 'shared'})
SET c.value = 10
RETURN c.value AS writtenValue;
```

**Session A** re-reads within **the same original transaction**:

```cypher
MATCH (c:IsolationCounter {id: 'shared'})
RETURN c.value AS secondRead;
```

Under the right timing, `firstRead = 0` and `secondRead = 10`. Same transaction, same node, yet two reads yield different results. This is a **non-repeatable read**.

Even within a single Cypher statement, reading the same property at different stages of the execution plan can observe different values. Illustrative example:

```cypher
MATCH (c:IsolationCounter {id: 'shared'})
WITH c, c.value AS firstRead
// Another transaction may commit in the interval between the two reads.
WITH c, firstRead, c.value AS secondRead
RETURN firstRead, secondRead;
```

There is no guarantee the two columns will always differ; the query will usually run very fast. The key takeaway is: **do not assume two accesses to a property fix the same value**. If a read-only calculation needs a consistent value, read it once and carry the computed variable forward with `WITH`.

## 6. Lost Update: Automatic Write Locks vs. Pre-Read Values

*Lost updates* are often the most severe issue in applications counting views, awarding loyalty points, adjusting inventory, or updating node metrics.

### 6.1. Lost Update Schedule

The counter starts at `0`. Both A and B read that value, compute outside the query, and then write the computed value sequentially.

| Step | Transaction A | Transaction B |
| --- | --- | --- |
| 1 | Read `value = 0` | |
| 2 | | Read `value = 0` |
| 3 | Compute `newValue = 1` then write/commit | |
| 4 | | Compute `newValue = 1` from stale data then write/commit |
| Outcome | | **`value = 1`**, despite two increment requests |

The application write might look like:

```cypher
MATCH (c:IsolationCounter {id: $id})
SET c.value = $newValue
RETURN c.value;
```

If both clients read `0` and send `$newValue = 1`, **write locking does not fix the business bug**: the second transaction still overwrites with a value computed from stale data.

Similarly, within one Cypher query, capturing the read value into a variable before updating can break the direct dependency the execution engine relies on to acquire locks early:

```cypher
MATCH (c:IsolationCounter {id: 'shared'})
WITH c, c.value AS oldValue
SET c.value = oldValue + 1
RETURN c.value;
```

Per Neo4j documentation on *lost updates*, be very cautious with separating property reads from the `SET` expression like this when concurrent transactions exist.

### 6.2. Direct Increment Pattern: Cypher Can Lock Before Reading

When the right-hand side of `SET` depends **directly** on the property being updated:

```cypher
MATCH (c:IsolationCounter {id: 'shared'})
SET c.value = c.value + 1
RETURN c.value AS updatedValue;
```

Neo4j documents that Cypher **automatically acquires a write lock before reading the dependent value** in this case. When two transactions increment the same counter concurrently, the lock protects the read–update operation, avoiding the *lost update* pattern above.

This also applies to certain direct map expressions such as `SET c += {value: c.value + 1}`, but **do not generalize** this into "every `SET` always protects every previously read value."

### 6.3. When You Need to Hold a Lock Before Complex Read–Compute Logic

Neo4j documentation describes a way to explicitly acquire a write lock by setting and removing a temporary property on a node **before reading** the value to compute from:

```cypher
MATCH (c:IsolationCounter {id: 'shared'})
SET c._writeLock = true
REMOVE c._writeLock
WITH c, c.value AS oldValue
// Perform calculations from oldValue after acquiring the lock.
SET c.value = oldValue + 1
RETURN c.value AS updatedValue;
```

`REMOVE`-ing the temporary property **does not release the held lock**; the lock is retained until the transaction ends. This is a documented technique for cases requiring read–compute logic after locking. Verify it against your active Neo4j version and weigh lock contention costs; do not overuse temporary properties when a direct increment suffices.

**Important:** Locking **one node** only serializes transactions that also acquire that node's lock. It does not automatically enforce rules spanning **multiple nodes** unless transactions lock a shared resource.

## 7. Phantoms, Write Skew, and Graph-Specific Risks

### 7.1. Phantom: Graph Pattern Result Sets Change

Suppose A counts pending reservation requests:

```cypher
MATCH (r:IsolationReservation {eventId: 'ev-1', state: 'PENDING'})
RETURN count(r) AS pendingCount;
```

Between two executions of this query by A inside **the same transaction**, B creates and commits a node:

```cypher
CREATE (:IsolationReservation {
  reservationId: 'res-new',
  eventId: 'ev-1',
  state: 'PENDING'
});
```

After B commits, A may re-read and see **an increased count or node set**. That is a *phantom* example in the sense of matching entity sets changing between queries inside the same transaction. Similarly, if B creates/deletes relationships, the result of `MATCH (a)-[:CONNECTED_TO]->(b)` can also change.

Do not use a single `count(*)` result as a "reservation lock" for subsequent write transactions. If you must guarantee a seat cannot be double-booked, model a seat lock or business identifier key with an appropriate **unique constraint** alongside transactions.

### 7.2. Write Skew: Each Transaction Modifies a Different Node, Breaking a Global Rule

Consider the rule: **each shift must always have at least one staff member on duty**. Initially there are two `(:IsolationStaff {onDuty: true})` nodes: An and Binh.

1. A reads and sees **2** staff on duty.
2. B reads and also sees **2**.
3. A sets An off duty (`onDuty = false`) and commits.
4. B sets Binh off duty (`onDuty = false`) and commits.
5. Zero staff remain on duty, even though **each transaction** checked "two staff were on duty before editing."

The two transactions wrote to **two different nodes**, so each node's individual write lock may not produce a conflict. This is a *write skew* risk: a constraint over a **set of entities** is not protected simply by reading that set.

One approach is to create a **shared guard node** for the shift; every transaction modifying that shift must acquire a write lock on the guard node **before re-reading and checking conditions**. Only transactions that **consistently follow the same locking protocol** are protected by it. For rules expressible via unique identifiers, schema-level constraints should also be used.

### 7.3. Missing/Double Reads During Index Scans

Current Neo4j documentation notes that **an index scan can miss or read an entity twice** if another transaction concurrently updates the indexed key value, moving the entity into a position already scanned or yet to be scanned.

Example query shape to evaluate:

```cypher
MATCH (i:IsolationItem)
WHERE i.score IS NOT NULL
RETURN i.itemId, i.score;
```

If the plan uses an index scan operator and another transaction is modifying `i.score`, you cannot assume a single scan sees every entity exactly once. **Having an index does not automatically give a consistent snapshot.** Not every plan or every run of the query above will trigger this anomaly; use `EXPLAIN` or `PROFILE` to inspect the actual operators.

### 7.4. Path Queries Are Not Shielded from Concurrent Modifications

With a query like:

```cypher
MATCH p = (a:IsolationNode {id: 'start'})-[:NEXT*1..3]->(b:IsolationNode)
RETURN b.id, length(p);
```

another transaction can add/remove relationships or modify properties while the read executes. Because Neo4j defaults to read committed, **do not treat the result of a long graph traversal as a consistent snapshot of all relationships at transaction start time**. If business correctness requires a pinned state, design appropriate synchronization on the relevant nodes/relationships, taking transaction scope and concurrent write load into account.

## 8. Deadlocks, Locks, and Retries: Application-Side Handling

### 8.1. A Deadlock Does Not Mean Corrupt Writes

Two transactions updating the same two nodes in opposite order can get stuck:

```text
Transaction A: locks node X ---> waits for lock on node Y
                                   ^
                                   |
Transaction B: locks node Y ---> waits for lock on node X
```

Neo4j detects deadlocks and terminates one of the involved transactions with a retryable error. Changes from the rolled-back transaction are never partially committed.

Common countermeasures:

- Acquire locks on nodes to update in **one consistent order** across all execution paths.
- Keep transactions short; do not wait on network calls or UI interactions while holding locks.
- Reduce contention on "hot" nodes; redesign data partitioning or batch updates where appropriate.
- Implement a **bounded retry policy** for transient errors with reasonable backoff; verify retry safety.

In current documentation, deadlock errors carry the Neo4j code `Neo.TransientError.Transaction.DeadlockDetected`. Starting in **Neo4j 5.25**, error details also include GQLSTATUS `50N05`. Do not write application logic that depends solely on a specific message string, as error representations can vary across versions.

### 8.2. Java Driver: Managed Transactions Have Built-In Retries

Example with a **Neo4j Java Driver version supporting `executeWrite`**:

```java
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.SessionConfig;

public final class CounterRepository {
    private final Driver driver;

    public CounterRepository(Driver driver) {
        this.driver = driver;
    }

    public long increment(String id) {
        try (var session = driver.session(SessionConfig.forDatabase("neo4j"))) {
            return session.executeWrite(tx ->
                tx.run(
                    """
                    MATCH (c:IsolationCounter {id: $id})
                    SET c.value = c.value + 1
                    RETURN c.value AS value
                    """,
                    Map.of("id", id)
                ).single().get("value").asLong()
            );
        }
    }
}
```

Here:

- `executeWrite` runs the callback inside a **managed transaction**; the driver can **retry the entire callback** on eligible transient errors up to the configured retry timeout.
- `SET c.value = c.value + 1` preserves the direct dependency needed for Neo4j to acquire a write lock before reading.
- `Driver` instances can be shared, but **Session is not thread-safe**; each concurrent transaction flow should use its own session.
- The callback may be invoked multiple times. **Never send emails, charge external payment systems, or trigger irreversible side effects inside the callback** without an appropriate idempotency mechanism.

If using an **explicit transaction** via `session.beginTransaction()`, the application controls `commit`/`rollback` and its own retry strategy. Driver-managed callback retries do not automatically apply as they do with managed transactions.

With **Spring Data Neo4j**, `@Transactional` groups repository operations into a transaction according to Spring's transaction manager configuration. However, this annotation **does not change the server's default isolation level**, nor does it automatically make every read–modify–write safe. Pay attention to Cypher design, transaction limits, retry strategies, and whether Spring actually applies its transaction proxy to that invocation.

### 8.3. Do Not Confuse Bookmarks and Causal Consistency with Isolation

In a cluster, Neo4j Driver **bookmarks** preserve causal ordering across transactions—for example, ensuring a subsequent read sees data written by an earlier transaction. This addresses **causal consistency across transactions and replicas**, which is a different question from "must two reads inside the same transaction return the same value?".

Do not conclude that using bookmarks makes a transaction **repeatable read** or **serializable**. When deploying multiple databases, clusters, and read routing, verify actual session and bookmark settings against your Driver/DBMS version.

## 9. Understanding "Version-Specific": What Is Stable vs. What Must Be Verified?

### 9.1. Verification Matrix

| Aspect | Neo4j 4.4 | 5.x series, including 5.26 LTS | Current documentation (latest release series) |
| --- | --- | --- | --- |
| Default transaction isolation level | **Read committed** | **Read committed** | **Read committed**, per current Operations Manual |
| Can non-repeatable reads occur | Yes, under read committed | Yes | Explicitly documented under *Concurrent data access* |
| Lost updates when separating read value from write | Must be guarded; depends on acquiring locks before reading | Must be guarded | Documentation explicitly contrasts `SET` with vs. without direct dependency |
| Lock details for dense/sparse nodes and store formats | Consult matching version guide | Consult matching version guide | Mechanisms may depend on store format; do not copy lock-structure assumptions from older releases |
| Deadlock error codes / structure | Check matching API docs | From 5.25 onward, adds GQLSTATUS `50N05` | Check both error code/GQLSTATUS and retry mechanism |
| Java Driver API | Older examples may use `writeTransaction` | `executeWrite` is standard in newer Drivers | Match the exact major version of the Driver in use |

**Do not infer the Neo4j server version from the Java Driver version**, and do not infer the DBMS version from the use of Spring Data Neo4j. Server, driver, Spring Data, and store formats each have independent lifecycles. The table above primarily highlights **what to verify**, rather than promising every internal difference across releases.

### 9.2. Determining the Running Version

On systems where the account has permission to call procedures, you can check:

```cypher
CALL dbms.components()
YIELD name, versions, edition
RETURN name, versions, edition;
```

In restricted environments or certain cloud services, procedure execution permissions and version reporting may vary; if the command is not permitted, check release info via your admin console or provider. Then open the **matching documentation for that exact version**, prioritizing:

1. **Operations Manual → Database internals → Concurrent data access** for default isolation and anomaly types.
2. **Operations Manual → Database transactions / Locks** for transactions, lock contention, deadlocks, and timeouts.
3. **Java Driver Manual → Run your own transactions** for `executeRead`, `executeWrite`, explicit transactions, retries, and sessions.
4. **Release notes** during upgrades, especially for changes to runtime, store format, error codes, or locking behavior.

### 9.3. Never Promise Serializable Just Because "Locks Exist"

Neo4j allows explicit locking to **emulate stronger isolation semantics** in controlled scenarios. Yet having one transaction modify node X and another modify node Y is insufficient to protect a rule **involving both X and Y simultaneously**. To achieve serializability for a business invariant, you must identify the exact set of resources to protect and ensure **all write paths obey the same locking protocol or constraint**.

## 10. Safe Transaction Design Process

When an API updates the graph, follow this process:

1. **Write down the business invariants clearly.** Examples: non-negative balance, each seat sold at most once, at least one staff member always on duty, or unique account identifiers.
2. **Identify nodes and relationships that may be updated together.** Locate true contention points, not just the final `SET` clause.
3. **Use indexes and constraints for rules expressible in the schema.** Unique constraints protect identifier uniqueness when concurrent requests create entities.
4. **Prefer direct property-dependent updates**, such as `SET n.counter = n.counter + 1`, when incrementing a value.
5. **If check-then-write spans multiple entities, define an explicit synchronization protocol.** Consider shared locks, guard nodes, data model redesign, or serializing requests per business key.
6. **Keep transactions short, use parameters, and apply bounded retries** for transient errors. Separate managed transaction callbacks from external non-Neo4j side effects.
7. **Test with at least two concurrent sessions** on the target Neo4j version; use `EXPLAIN`/`PROFILE` and transaction/lock logs where needed, because concurrency schedules rarely surface in single-query tests.

## 11. Practice Exercises

### Exercise 1. Identifying the Isolation Level

Transaction A reads `value = 5` and stays open. Transaction B updates `value = 8` and commits. A re-reads and sees `8`.

**Question:** What anomaly is this? Does this outcome violate read committed?

**Suggested Answer:** This is a **non-repeatable read**. This outcome can occur under **read committed** because B committed before the second read; it is not a dirty read.

### Exercise 2. Choosing a Counter-Increment Query

How do the following two snippets differ under concurrent load?

```cypher
// Pattern A: the old value is passed via a variable.
MATCH (c:IsolationCounter {id: 'shared'})
WITH c, c.value AS oldValue
SET c.value = oldValue + 1;
```

```cypher
// Pattern B: the write directly depends on the property.
MATCH (c:IsolationCounter {id: 'shared'})
SET c.value = c.value + 1;
```

**Suggested Answer:** Pattern B has a direct dependency, so Neo4j acquires a write lock before reading the property. Pattern A risks *lost updates* under concurrent execution schedules; if complex read–compute logic is required, the initial read step must be protected.

### Exercise 3. Diagnosing the "At Least One Staff On Duty" Rule

A and B both read two staff members on duty, then each sets a different person off duty. Is writing to **two different nodes** enough to guarantee the rule cannot be violated?

**Suggested Answer:** No. This is a *write skew* risk. You need a shared synchronization point, locking over the right entity set, or a model change so all transactions contend on the same resource protecting the rule.

### Exercise 4. Distinguishing Phenomenon from Mechanism

A transaction is terminated by Neo4j with `Neo.TransientError.Transaction.DeadlockDetected`. Can you conclude that a dirty read happened or that partial data was wrongly committed?

**Suggested Answer:** No. This is a **deadlock** caused by conflicting lock acquisition orders, not evidence of a dirty read. The transaction was rolled back; the application may retry the entire transaction within appropriate bounds.

### Exercise 5. Verifying Your Actual Version

In your test environment, identify the **Neo4j server version**, **Java Driver version**, and matching documentation. Check: (a) default isolation level, (b) examples of direct property dependency in `SET`, (c) managed transaction retries, (d) deadlock error encoding. Note any differences compared to the examples in this lesson if your project uses an older release.

## 12. Summary

Neo4j defaults to **read committed**: transactions never see **uncommitted** changes from other transactions, but can observe **non-repeatable reads**, changing result sets, *lost updates* in unsafe read–write patterns, and contention risks when multiple transactions update the graph concurrently. **Automatic write locks do not mean all multi-step business checks are serialized.** You must understand property dependencies in `SET`, enforce invariants with constraints or shared locks, and retry properly on deadlocks. When learning or upgrading Neo4j, always verify against **your exact DBMS version, driver, and documentation** before relying on detailed lock or runtime behavior.

### Official References

- [Neo4j Operations Manual – Database internals and transactional behavior](https://neo4j.com/docs/operations-manual/current/database-internals/)
- [Neo4j Operations Manual – Concurrent data access](https://neo4j.com/docs/operations-manual/current/database-internals/concurrent-data-access/)
- [Neo4j Operations Manual – Database transactions](https://neo4j.com/docs/operations-manual/current/database-internals/transaction-management/)
- [Neo4j Java Driver Manual – Run your own transactions](https://neo4j.com/docs/java-manual/current/transactions/)
- [Neo4j Documentation Archive – choose documentation by version](https://neo4j.com/docs/reference/docs-archive/)
