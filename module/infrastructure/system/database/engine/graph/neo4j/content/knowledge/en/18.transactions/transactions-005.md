# Locking When Updating Nodes, Relationships, and Properties

## 1. Why Are Locks Needed in Neo4j Transactions?

In Neo4j, the **property graph** model consists of **nodes**, **relationships**, and **properties**. An application may concurrently receive requests to rename a customer, update an order's status, record a new follow relationship, or increment a counter. If two transactions write to the same piece of data without coordination, the result can be wrong or inconsistent.

**Locks** are one of the mechanisms Neo4j uses to coordinate concurrent access. When a transaction modifies a node or relationship, Neo4j automatically acquires the required locks to prevent conflicting writes from executing unsafely. Locks also affect wait times, latency, and deadlock risk.

Consider two transactions concurrently incrementing a view counter:

- Initially, the post node has `views = 100`.
- Transaction T1 wants to add 1, and T2 also wants to add 1.
- The desired business outcome after both increments succeed is **102**, not **101**.

In the **Transactions** chapter of the Neo4j module, it is important to distinguish **entity locks**, **transaction atomicity**, **isolation levels**, and **Cypher query patterns**. Neo4j manages locks automatically, yet the application must still choose the right query pattern to avoid reading a stale value and overwriting another transaction's update.

### 1.1. Three Distinct Goals

| Goal | Meaning | Related mechanism |
|---|---|---|
| Atomic transactions | Operations within one transaction commit or roll back together | Transaction |
| Coordinating updates to the same entity | Two conflicting write operations cannot concurrently modify the same object arbitrarily | Write lock |
| Enforcing data rules | For example, a `User` cannot have two nodes with the same `userId` | Uniqueness constraint and business validation |

Locks do not replace constraints. Conversely, constraints do not solve problems such as property overwrites, deadlocks, or updates based on previously read data.

## 2. What Objects Does Neo4j Lock?

In regular Cypher update operations, Neo4j manages locks automatically. You can think of the operation groups as follows:

| Operation | Directly affected object | What to understand |
|---|---|---|
| `SET n.name = ...` | Node `n` | Writing a node property requires synchronizing related write operations |
| `SET n:Verified`, `REMOVE n:Verified` | Node `n` | Changing labels is also a node update |
| `SET r.since = ...` | Relationship `r` | Writing a relationship property requires coordinating writes to that relationship |
| `CREATE (a)-[:KNOWS]->(b)` | Relationship structure and endpoint nodes | Neo4j may need additional locks/synchronization on connection data at endpoint nodes |
| `DELETE r` | Relationship `r` | Deletion must coordinate with transactions using/writing that relationship |
| `DETACH DELETE n` | Node `n` and its adjacent relationships | May affect many entities and widen lock contention |

**The unit of locking is not an individual property.** If two transactions update `name` and `status` on **the same node**, they may still contend for that node's write lock even though they modify different property names. Likewise, updating two different properties on the same relationship can also contend.

Neo4j uses internal lock types and optimization rules that vary by version, entity type, relationship density, and operation. Do not infer that a Cypher statement acquires exactly one lock matching the variable name in `SET`; creating or deleting relationships also updates the graph structure.

### 2.1. Write Locks Are Held for the Transaction Scope

A transaction can run multiple Cypher statements before committing:

~~~cypher
MATCH (u:User {userId: $userId})
SET u.status = 'ACTIVE';

MATCH (u:User {userId: $userId})
SET u.updatedAt = datetime();
~~~

If both statements above execute inside **the same transaction**, Neo4j holds the required locks during execution and releases them according to the transaction lifecycle upon commit or rollback. Therefore, a transaction held open while waiting on external HTTP/API calls can force other requests to wait longer for locks.

A read-only `MATCH ... RETURN ...` statement does not automatically act as an "exclusive lock for a later update." The default isolation level is typically described as **read committed**: applications never read uncommitted data from another transaction, yet separate reads may observe values committed by other transactions at different times.

## 3. Updating Node Properties: Node-Level Contention

Suppose two requests update the same customer:

~~~cypher
MATCH (u:User {userId: $userId})
SET u.displayName = $newName
RETURN u.userId AS userId, u.displayName AS displayName;
~~~

This is a write operation on **node `u`**. If T1 and T2 both modify that node, each transaction must abide by Neo4j's write-lock mechanism. One transaction may have to wait until the other finishes.

However, locks only coordinate writes; **they do not decide which request should win according to business rules**. If T1 writes `"An"` and T2 writes `"An Nguyen"`, the final value depends on execution/commit order and update logic. When you need to accept only the latest version, the application should design explicit versioning, conditional updates, or conflict handling.

### 3.1. Modifying Two Different Properties on the Same Node

~~~cypher
// Transaction T1
MATCH (u:User {userId: 'u-1'})
SET u.displayName = 'An';
~~~

~~~cypher
// Transaction T2
MATCH (u:User {userId: 'u-1'})
SET u.lastSeenAt = datetime();
~~~

Both statements write to the same `User` node. Different property names do not mean the two writes are completely independent with respect to locks. When a node is updated frequently, it can become a **hot node**, especially if many workers increment counters or update timestamps on that node.

> **Example convention:** Separate Cypher blocks in this lesson represent statements executed in different transactions/sessions when labeled T1 or T2; do not combine independent example snippets into a single one-shot script.

## 4. Incrementing Values Properly: Avoiding Lost Updates

A common scenario is reading the current property and adding to it. There are two ways to write this with different safety levels.

### 4.1. Updating Directly Based on the Property Inside `SET`

~~~cypher
MATCH (p:Post {postId: $postId})
SET p.views = coalesce(p.views, 0) + 1
RETURN p.views AS views;
~~~

With a direct update pattern referencing the node's own property, Cypher can recognize that the new value depends on that property's old value and protect the read–modify–write cycle with the appropriate lock. Two concurrent increments that **both succeed** will preserve the total increment count.

This is the fundamental pattern for updating a counter. Still, a very frequently updated node creates lock contention; data correctness does not automatically mean optimal throughput.

### 4.2. Anti-Pattern: Pre-Computing the Value Before Writing

~~~cypher
MATCH (p:Post {postId: $postId})
WITH p, coalesce(p.views, 0) AS oldViews
SET p.views = oldViews + 1
RETURN p.views AS views;
~~~

The snippet above **risks a lost update** when two transactions read `oldViews` before acquiring the write lock. A possible interleaved schedule is:

| Time | T1 | T2 |
|---|---|---|
| 1 | Reads `oldViews = 100` | |
| 2 | | Reads `oldViews = 100` |
| 3 | Writes `views = 101` and commits | |
| 4 | | Writes pre-computed `101` and commits |
| Result | | **`101` instead of `102`** |

Data read before acquiring a write lock may already be stale. Distinguish queries that **SET a property based directly on its current value** from queries that **pre-compute via `WITH` and then SET a fixed value**. If the problem is more complex than a simple increment expression, review the locking/transaction model and application-level consistency rules.

### 4.3. Do Not Confuse Atomicity with Lost-Update Prevention

Two transactions can both **commit atomically and successfully**, yet business-level read–write logic still causes a lost update. Neither operation "half-committed"; the issue is that the later transaction **wrote a value computed from stale data**.

If you need operations such as:

- Deducting inventory **only when sufficient stock remains**;
- Transferring points/assets between two accounts;
- Changing status **only if the current status is still PENDING**;

then you must protect the entire read condition and write action, not just rely on `SET` taking a lock at write time. In particular, evaluating `WHERE` before acquiring a lock can evaluate the business condition against outdated state. In critical flows, design transactions with conflict control and run real concurrency tests.

## 5. Locking When Updating Relationships and Relationship Properties

In Neo4j, a relationship is also an entity with its own identity, type, and properties. For example, a customer is a member of an organization:

~~~cypher
MATCH (u:User {userId: $userId})-[m:MEMBER_OF]->(o:Organization {orgId: $orgId})
SET m.role = $newRole,
    m.updatedAt = datetime()
RETURN m.role AS role;
~~~

Here `m` represents the **MEMBER_OF relationship**. `SET m.role` updates a **property on the relationship**, not a property on the User or Organization node.

Two transactions concurrently modifying `role` and `joinedAt` on **the same relationship `m`** may contend for the relationship's write lock. Conversely, modifying a different relationship does not always conflict directly; actual behavior depends on the operations and other involved locks.

### 5.1. Deleting a Relationship

~~~cypher
MATCH (u:User {userId: $userId})-[m:MEMBER_OF]->(o:Organization {orgId: $orgId})
DELETE m;
~~~

This deletes the relationship while keeping both endpoint nodes. A concurrent transaction modifying a property on `m` may wait on the lock or error if its data assumptions change mid-execution. The application should handle the case where the relationship no longer exists as a valid business outcome.

### 5.2. Creating Relationships Also Modifies Graph Structure

~~~cypher
MATCH (u:User {userId: $userId})
MATCH (o:Organization {orgId: $orgId})
MERGE (u)-[m:MEMBER_OF]->(o)
ON CREATE SET m.joinedAt = datetime()
RETURN m.joinedAt AS joinedAt;
~~~

Although `MERGE` may end up creating just **one relationship**, the operation touches the endpoints and adjacency structures of both nodes. Neo4j uses appropriate synchronization for relationship creation; thus contention can arise on nodes with very high degree or when many transactions create/delete edges to the same target.

**`MERGE` is not equivalent to a uniqueness constraint for relationships across all concurrent schedules.** When business rules enforce a unique membership per User–Organization pair, verify the identifier model, constraints supported by your Neo4j version, and how the application handles concurrent transactions. Uniqueness constraints on `User.userId` and `Organization.orgId` only directly protect **node** uniqueness by those two keys.

## 6. Deleting Nodes and Relationships: Lock Scope Can Be Wider

For a node that still has relationships, a plain `DELETE n` will fail. To delete a node and all relationships directly attached to it, use `DETACH DELETE`:

~~~cypher
MATCH (u:User {userId: $userId})
DETACH DELETE u;
~~~

This statement can affect **many relationships**, including both incoming and outgoing edges. For a heavily connected node, the number of modified entities and lock hold duration can be substantial.

If you only need to remove a membership edge:

~~~cypher
MATCH (:User {userId: $userId})-[m:MEMBER_OF]->(:Organization {orgId: $orgId})
DELETE m;
~~~

Targeting the exact **object to delete** narrows the blast radius and better matches business intent. Do not use `DETACH DELETE u` as a substitute for removing a single relationship.

## 7. When Two Transactions Need to Lock Multiple Objects

Transactions often must update multiple nodes or relationships. For example, transferring points between two wallets:

~~~cypher
MATCH (src:Wallet {walletId: $sourceId})
MATCH (dst:Wallet {walletId: $targetId})
SET src.points = src.points - $amount,
    dst.points = dst.points + $amount
RETURN src.points AS sourcePoints, dst.points AS targetPoints;
~~~

These writes execute in the same Cypher statement and same transaction. If the transaction commits, the updates belong to one atomic unit; if it rolls back, there is no committed state where points were deducted without being credited.

**This is only an illustration of atomicity and lock scope, not a complete point-transfer algorithm.** A real system must validate `sourceId != targetId`, sufficient balance, valid `amount`, and protect that condition against concurrent transfers. A naive `MATCH ... WHERE src.points >= $amount ... SET ...` may be insufficient if condition evaluation is separated from acquiring the appropriate locks.

### 7.1. Deadlock: Two Transactions Waiting on Each Other

Imagine T1 acquires the write lock on wallet A and needs wallet B; T2 acquires the write lock on wallet B and needs wallet A:

~~~text
T1: holds lock A  ---> waits for lock B
T2: holds lock B  ---> waits for lock A
                    ^ wait cycle ^
~~~

The two transactions form a **wait cycle**. This is a deadlock. Neo4j detects deadlocks and can abort/roll back one transaction so the other can proceed. The application receives a transient transaction error in this situation instead of hanging forever.

Having locks does not mean deadlocks cannot occur. Deadlocks usually stem from **acquiring multiple locks in inconsistent orders** under concurrent load.

### 7.2. Reducing Deadlocks with Consistent Update Ordering

If multiple services need to update a set of wallets, sort the **wallet IDs** first and update sequentially in the same order inside one transaction:

~~~java
List<String> orderedWalletIds = walletIds.stream()
    .distinct()
    .sorted()
    .toList();

session.executeWrite(tx -> {
    for (String walletId : orderedWalletIds) {
        tx.run("""
            MATCH (w:Wallet {walletId: $walletId})
            SET w.updatedAt = datetime()
            """, Values.parameters("walletId", walletId)).consume();
    }
    return null;
});
~~~

This illustrates an **application-level lock-ordering strategy**: multiple workflows using the same sorting rule reduce opposing wait cycles caused by themselves. It **does not guarantee eliminating all deadlocks**, because a query may lock additional internal resources, another service may write in a different order, or the query plan may behave differently than assumed.

The Java example assumes `session`, `walletIds`, and the corresponding type imports already exist. This is not a complete money-transfer function.

## 8. Locks, Isolation, and Constraints: Boundaries of Responsibility

A Neo4j transaction is atomic, yet the default **read committed** isolation level does not promise that all data read at the start and end of a transaction comes from an immutable snapshot. In a read-then-decide-then-write flow, another transaction can commit in between.

| Scenario | What automatic locking helps with | What the application must still handle |
|---|---|---|
| T1 and T2 both run `SET u.name` | Coordinates two writes on the same node | Choose the rule for accepting the latest version |
| Two direct `counter` increments inside `SET` | Protects read–modify–write when Cypher detects dependency | Avoid pre-computing values that might be stale |
| Concurrently creating `User` by `userId` | Coordinates write operations and related locks | Define uniqueness constraints, use key-based `MERGE` |
| Two transactions updating two nodes in reverse order | Manages locks, detects wait cycles | Retry appropriately and standardize write order |
| One worker deletes a relationship while another edits it | Synchronizes entity modifications | Handle missing data or contention errors |
| Conditional balance updates | Locks during write execution | Protect check conditions and non-negativity rules with consistent design |

### 8.1. `MERGE` and Uniqueness Constraints

When multiple requests concurrently try to create a node by a key, `MERGE` is convenient for find-or-create:

~~~cypher
MERGE (u:User {userId: $userId})
ON CREATE SET u.createdAt = datetime()
SET u.displayName = $displayName
RETURN u.userId AS userId;
~~~

However, to **forbid duplicate keys at the database level**, you need the corresponding constraint:

~~~cypher
CREATE CONSTRAINT user_id_unique IF NOT EXISTS
FOR (u:User)
REQUIRE u.userId IS UNIQUE;
~~~

Constraints must be deployed before allowing large-scale concurrent writes. If duplicate nodes already exist, constraint creation may fail. Constraints do not replace classifying transient errors or controlling transaction boundaries.

### 8.2. Optimistic Concurrency: Update Only If the Version Matches

When multiple actors edit the same record and you want to avoid silent overwrites, you can use a version property to express the business requirement:

~~~cypher
MATCH (d:Document {documentId: $documentId})
WHERE d.version = $expectedVersion
SET d.title = $newTitle,
    d.version = d.version + 1
RETURN d.documentId AS documentId,
       d.version AS version;
~~~

If the query returns **0 rows**, either the record does not exist or the version mismatched. However, checking the version in `WHERE` and writing in `SET` must **be verified under concurrency**: evaluating conditions before acquiring locks and re-evaluating predicates depend on execution semantics. Never assume this is a guaranteed atomic compare-and-swap across all versions and query plans.

For rules **requiring that at most one request succeeds for a given version**, use a transaction/locking pattern verified for your Neo4j version, or an appropriate application-layer concurrency mechanism. Combine row-count checks with retry/conflict handling; avoid assuming a single Cypher statement automatically provides serializable isolation.

## 9. Transaction Choices in the Java Driver

The Neo4j Java Driver supports managed transactions via `Session.executeWrite(...)`. This is the right place to group write statements that require atomicity:

~~~java
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class UserService {
    private final Driver driver;

    public UserService(Driver driver) {
        this.driver = driver;
    }

    public String changeDisplayName(String userId, String newName) {
        if (userId == null || userId.isBlank()) {
            throw new IllegalArgumentException("userId is required");
        }

        try (Session session =
                 driver.session(SessionConfig.forDatabase("neo4j"))) {

            return session.executeWrite(tx ->
                tx.run("""
                    MATCH (u:User {userId: $userId})
                    SET u.displayName = $newName,
                        u.updatedAt = datetime()
                    RETURN u.userId AS userId
                    """, Map.of("userId", userId, "newName", newName))
                  .single()
                  .get("userId")
                  .asString()
            );
        }
    }
}
~~~

Implementation notes:

- **`Driver`** is typically reused at the application level; **`Session`** is short-lived and should not be arbitrarily shared across threads.
- The callback in `executeWrite` may be re-executed by the driver when encountering eligible transient errors. Actions inside the callback should be **safe to re-run**.
- Do not call email, payment, or external APIs inside a retryable callback unless those operations have proper idempotency mechanisms.
- `single()` assumes exactly one node is found. If zero nodes or multiple invalid rows match, it throws an error; the application should define how to return "not found."
- Database name, retry timeout, and driver version must be configured for your actual system.

With **Spring Data Neo4j**, a transactional service still relies on Neo4j's locking mechanisms and query choices. Transaction management annotations do not automatically make read–check–write logic immune to lost updates or deadlocks.

## 10. Handling Contention Errors, Timeouts, and Retries

Competing transactions can encounter several categories of outcomes:

| Outcome category | Example | Appropriate response |
|---|---|---|
| Successful commit | Both counter increments finish | Return result; verify business values |
| Lock wait | T1 is modifying a node T2 also needs | Keep transactions short; monitor latency and load |
| Deadlock/transient failure | Two transactions form a wait cycle | Retry **the entire transaction** when the error is classified as retryable |
| Constraint violation | Two requests try to create a duplicate unique key; or conflicting data | Re-read by key, distinguish concurrent write from business error |
| Invalid input | Null key, negative amount, missing identifier | Reject the request; do not retry |
| Transaction timeout | Write/lock wait exceeds the timeout limit | Identify hot nodes, slow queries, and lock hold times before tuning |

Avoid **infinite retries**. Retries should be bounded by attempt count or duration, use reasonable backoff, and apply only to error types that can genuinely succeed on retry. Java Driver managed transactions already retry certain transient errors automatically; do not blindly wrap them in an outer retry loop that multiplies execution attempts.

### 10.1. Retries Must Cover the Entire Unit of Work

If T1 acquired lock A and needed B, but a deadlock rolled back the transaction, the retry must re-run **all work belonging to that transaction**, including necessary reads and related writes.

Do not resume from the middle of a workflow as if earlier parts had already committed. Data state may have changed between the error and the retry.

### 10.2. Protecting Operations with Side Effects

Suppose a transaction awards points and then sends a notification. If it sends the notification inside the callback before committing, the callback could run multiple times on retry, sending duplicate notifications. For critical tasks, use a pattern like **outbox** or an idempotency key so post-commit event publishing is controlled.

## 11. Reducing Lock Contention Through Query Design

### 11.1. Start from the Target Node and Avoid Unnecessary Graph Expansion

If you only need to update an order's status, keep the query concise:

~~~cypher
MATCH (o:Order {orderId: $orderId})
SET o.status = $status,
    o.updatedAt = datetime()
RETURN o.orderId AS orderId;
~~~

There is no need to traverse all customers, products, or relationships before reaching the `Order` node if `orderId` already uniquely identifies the order.

Creating an appropriate uniqueness constraint/index on `Order.orderId` makes finding the starting point efficient. Indexes **do not eliminate write locks**, but they can reduce node lookup time and the amount of work done before and after acquiring locks.

### 11.2. Avoid Overly Long Transactions

A long transaction can:

- Hold locks longer, forcing many other requests to wait.
- Increase the chance of colliding with workflows updating the same entities.
- Consume extra memory and processing resources.
- Require redoing a large amount of work if rolled back.

Prefer completing calculations independent of changing data before opening the transaction, pass required parameters, write concisely, and commit. However, **do not** move reads that require consistency out of the transaction solely to shorten lock duration; balance correctness and performance.

### 11.3. Mitigating "Hot Nodes"

If one `Post` node receives thousands of `views` increments per second, all direct writes to that same node may queue behind one another. Consider:

- Batching multiple view events into periodic updates with deduplication.
- Using sharded counters or separate aggregation tables if business rules tolerate delayed synchronization.
- Separating frequent writes from unrelated updates when the data model allows.

Changing the model has trade-offs: you must decide how totals are computed, acceptable staleness, and duplicate event handling. Optimize only after measuring contention and throughput targets.

### 11.4. Batch Writes with Controlled Parallelism

During data ingestion, huge transactions can hold many locks for a long time; tiny transactions can add overhead. Find a reasonable batch size based on data shape, relationship density, and contention.

Multiple workers concurrently ingesting records sharing business keys must coordinate constraints, `MERGE`, and retries. Batching **does not** by itself eliminate conflicts across workers.

## 12. Observing Transactions and Verification

### 12.1. Viewing Running Transactions

Where environment and permissions allow, you can inspect transaction status:

~~~cypher
SHOW TRANSACTIONS;
~~~

Columns and visibility into other users' transactions depend on Neo4j version, edition, and admin privileges. Look for long-running transactions, currently executing statements, and wait states when your version/monitoring tools expose them.

### 12.2. `EXPLAIN` and `PROFILE` Serve Different Purposes

~~~cypher
EXPLAIN
MATCH (u:User {userId: $userId})
SET u.status = 'ACTIVE'
RETURN u.userId;
~~~

`EXPLAIN` analyzes the query plan **without executing the write**, making it useful to inspect starting points and how nodes are located. `PROFILE` **executes** the statement, so never run `PROFILE` on a write query against production data just to "take a look."

A query plan alone does not guarantee zero contention or zero deadlocks. To evaluate locking, also examine latency, transient errors, timeouts, concurrency levels, and relevant metrics from Neo4j and the application.

### 12.3. Minimal Concurrency Test Scenario

In a dedicated test database, create a node with a unique key and an initial counter:

~~~cypher
CREATE CONSTRAINT lock_lab_counter_id IF NOT EXISTS
FOR (n:LockLabCounter)
REQUIRE n.counterId IS UNIQUE;
~~~

~~~cypher
MERGE (n:LockLabCounter {counterId: 'demo'})
SET n.value = 0;
~~~

From **two or more sessions**, have each session run the following statement multiple times in separate transactions:

~~~cypher
MATCH (n:LockLabCounter {counterId: 'demo'})
SET n.value = n.value + 1
RETURN n.value AS value;
~~~

Read it back:

~~~cypher
MATCH (n:LockLabCounter {counterId: 'demo'})
RETURN n.value AS actual;
~~~

With `W` workers, each completing `K` increment transactions once, the expected value is **W × K**, provided all transactions succeed and no other process modifies `value`. Record error counts, retry counts, and latency separately; a correct final value accompanied by heavy retries still indicates contention.

Repeat in the **test environment** using the pre-computed `WITH` pattern to observe lost-update risk. Whether an error manifests can depend on how the two sessions interleave; seeing no error in a single test run is not proof of safety across all execution schedules.

Clean up example data after finishing on the test database:

~~~cypher
MATCH (n:LockLabCounter {counterId: 'demo'})
DETACH DELETE n;
~~~

## 13. Common Misconceptions

**"Neo4j locks each property independently."** Do not assume this. Updating properties on the same node can contend on the node-level write lock, even for different property names.

**"With locks, lost updates can never happen."** False. If an application computes a value from data read before write time, it can overwrite another transaction's result with stale data.

**"A transaction guarantees all reads and writes are serializable."** False under default isolation assumptions. Check read patterns, lock timing, and how business conditions are protected.

**"Write locks are locks I must declare manually in every Cypher query."** No. Neo4j acquires required locks automatically for write operations. However, complex read–check–write workflows may still need additional synchronization design.

**"Creating a `UNIQUE` constraint also prevents deadlocks."** No. Constraints enforce data uniqueness by key; deadlocks arise when transactions contend on multiple resources in conflicting orders.

**"A deadlock means the database is corrupted."** No. It is a concurrency condition that can arise in multi-transaction systems. Neo4j can detect it and roll back one transaction; the application should handle transient errors.

**"Putting everything into one Cypher query eliminates contention."** No. A single Cypher statement can still modify multiple nodes/relationships, hold locks, and conflict with other transactions.

**"`PROFILE` only shows the plan."** No. `PROFILE` executes the query; use `EXPLAIN` if you only want to inspect the execution plan of a write statement.

## 14. Self-Check Exercises

### Exercise 1 — Two Fields on the Same Node

T1 runs `SET u.name = 'Binh'`, while T2 runs `SET u.status = 'ACTIVE'` on the same node `u`. Since they modify different fields, can you guarantee there is no lock contention?

**Hint:** No. Write operations on the same node may still require the same node write lock.

### Exercise 2 — A Counter Missing One Increment

Two workers read the same `oldCount = 7` into a Java variable, and then each runs `SET p.count = $oldCount + 1`. Both requests succeed, and the final value is 8. Why?

**Hint:** Both requests sent a value computed from stale state, so one increment was overwritten. Moving the addition into `SET p.count = p.count + 1` instead of passing a pre-computed value avoids this lost-update pattern.

### Exercise 3 — Updating a Membership

The application needs to change `role` on the `MEMBER_OF` relationship between `User` and `Organization`. Should it run `SET u.role` or `SET m.role`?

**Hint:** If `role` belongs to the **membership relationship**, update `m.role` on the relationship. Targeting the exact object being modified ensures proper modeling and clarifies contention scope.

### Exercise 4 — Two-Wallet Deadlock

T1 updates wallet A then B; T2 updates B then A. Both transactions hold one lock and wait for the other. What should happen?

**Hint:** Deadlock detection can roll back one transaction. The application retries the entire unit of work when the error is classified as retryable; standardizing update order reduces the risk.

### Exercise 5 — A Transaction Making an HTTP Call

An `executeWrite` callback updates an order and then directly calls an SMS API. Why should you avoid doing this?

**Hint:** The callback may re-run if the transaction hits a transient error. If the SMS was already sent and the transaction rolls back/retries, the notification may be sent multiple times. Use post-commit event publishing or proper idempotency.

## 15. Key Takeaways

In Neo4j, **writing properties to nodes** and **writing properties to relationships** are coordinated via transaction locking; **creating and deleting relationships** also affects graph connectivity structures. Two operations modifying the same entity may wait on each other, and a transaction updating multiple entities can encounter a **deadlock**. Neo4j manages locks automatically and guarantees atomicity, but Cypher authors must still avoid **reading stale values and overwriting**, properly guard business conditions, and handle retries sensibly.

For stable operations, **write concisely using clear identifier keys**, update target properties directly, enforce consistent operation ordering across multiple entities, monitor hot nodes, and test concurrency with realistic workloads. Combining these practices with **constraints**, **Java Driver managed transactions**, and observability keeps graph applications both data-correct and scalable under load.
