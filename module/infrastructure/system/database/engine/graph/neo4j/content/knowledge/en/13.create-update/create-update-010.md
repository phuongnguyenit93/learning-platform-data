# Checking Update Statistics and Verifying Post-Write State in Neo4j

## 1. Why Does a Successful Write Query Still Need Verification?

Neo4j organizes data as a **property graph**: nodes carry labels and properties; relationships have a direction, type, and their own properties. Cypher clauses such as `CREATE`, `MERGE`, `SET`, `REMOVE`, and `DELETE` mutate the graph. However, an application should not conclude "the data is right" merely because the query threw no errors.

For example, a user management system sends a request to transition account `u-101` to `ACTIVE`. Several different scenarios can happen:

- The `MATCH` query found no node, so it updated nothing even though it succeeded.
- `MERGE` matched an existing node and did not create a new one; this may be the intended outcome of an idempotent operation.
- `SET` executed, yet the final value violated business rules.
- The application received query statistics, but the enclosing transaction was subsequently rolled back.
- The transaction committed, yet a read in another session across a cluster was not coordinated with bookmarks, or another transaction updated the data immediately afterward.

Therefore, you need to verify **three distinct layers of information**:

| Verification Layer | Tool | Answers the Question | Does Not Guarantee by Itself |
| --- | --- | --- | --- |
| Execution outcome | Query results, exceptions, transaction status | Did Cypher finish executing and did the transaction commit successfully? | Right node, right relationship, right business value |
| Update statistics | Query counters in Neo4j Browser or Java Driver's `ResultSummary.counters()` | How many create, delete, property-set, or label-add operations did the query perform? | Unique business record count, actual post-write values, durability if uncommitted |
| Post-write state | `MATCH ... RETURN` query after commit, within a consistent read context | Do the current node, relationship, properties, and version match expectations? | That data will not be altered later by another transaction |

**Principle:** counters report *the write activity of a query*; a follow-up read query reports *the observed graph state*; the transaction determines *whether the changes were committed*.

## 2. Reading Update Metrics Correctly

In Neo4j Browser, after running a write statement, you can view notifications showing how many nodes/relationships were created or deleted, properties set, or labels added. When using a driver, these metrics appear in the **query execution summary**.

| Java Driver Counter | Meaning | Common Misinterpretation |
| --- | --- | --- |
| `nodesCreated()` | Number of nodes created | Not the number of nodes found by `MATCH` |
| `nodesDeleted()` | Number of nodes deleted | `DETACH DELETE` may also delete relationships simultaneously |
| `relationshipsCreated()` | Number of relationships created | Not the number of paths returned by the query |
| `relationshipsDeleted()` | Number of relationships deleted | Not necessarily equal to nodes deleted |
| `propertiesSet()` | Number of property-set operations recorded by Neo4j | Not the number of modified nodes or values that *actually differed from before* |
| `labelsAdded()` / `labelsRemoved()` | Number of labels added/removed | Distinct from creating/deleting nodes |
| `indexesAdded()` / `indexesRemoved()` | Schema index changes | Does not reflect user data updates |
| `constraintsAdded()` / `constraintsRemoved()` | Schema constraint changes | Does not reflect how many records are subject to constraints |
| `containsUpdates()` | Whether at least one data/schema update was recorded for the query | Does not prove the outer transaction has committed |
| `containsSystemUpdates()` / `systemUpdates()` | Statistics for changes on the `system` database | Does not replace data graph counters |

Interpretation notes:

1. `CREATE (u:AppUser {id: 'u-101', name: 'Mai'})` creates **one node**, while also recording adding a label and setting multiple properties.
2. A `MERGE` matching an existing node normally yields `nodesCreated() == 0`. With `ON MATCH SET`, the query can still report property updates.
3. `SET u.status = 'ACTIVE'` can be counted as a property-set operation even when the value was already `ACTIVE`. Do not rely on a counter to infer whether a "business value actually changed."
4. `RETURN count(u)` counts rows/nodes flowing through the query under Cypher semantics; it is **not** an update counter. If a node appears across multiple rows due to relationship expansion, consider `DISTINCT`.
5. Counters are **per-query statistics**, not a change-history table stored in the graph and not a long-term auditing mechanism.

## 3. Verification Workflow in Cypher

The running example uses the `AppUser` label and business key `id`. Run the statements in order on a **test database** and observe both the results and the summary statistics. If your environment already has an equivalent constraint, you do not need to recreate it.

### Step 1: Guarantee Unique Identity

```cypher
CREATE CONSTRAINT app_user_id_unique IF NOT EXISTS
FOR (u:AppUser)
REQUIRE u.id IS UNIQUE;
```

The unique constraint prevents `MERGE (u:AppUser {id: ...})` from creating two nodes with the same `id` under competing transactions. DDL has its own counters: do not conflate constraint-creation metrics with business-data write metrics.

### Step 2: Create If Absent and Inspect Counters

```cypher
MERGE (u:AppUser {id: 'u-101'})
ON CREATE SET
  u.name = 'Mai',
  u.status = 'PENDING',
  u.version = 0
RETURN u.id AS id, u.name AS name,
       u.status AS status, u.version AS version;
```

**First run** on a dataset without `u-101`: expect `nodesCreated = 1`, along with the added label and properties. **Second run**: `MERGE` matches the existing node and skips the `ON CREATE` branch, so zero updates are expected. This is intentional idempotency, not a bug.

If `RETURN` outputs one row while `nodesCreated = 0`, that only tells you the node **was not created during this run**. It does not rule out that the node already existed.

### Step 3: Conditional Update to Avoid Redundant Writes

```cypher
MATCH (u:AppUser {id: 'u-101'})
WHERE u.status IS NULL OR u.status <> 'ACTIVE'
SET u.status = 'ACTIVE',
    u.version = coalesce(u.version, 0) + 1
RETURN u.id AS id, u.status AS status,
       u.version AS version;
```

If `u-101` is `PENDING`, the query updates `status` and `version`; the `RETURN` output shows values *after `SET` within the current transaction*. Re-running once already `ACTIVE`, `WHERE` filters out the node, the query returns zero rows, and update counters are 0.

If node `u-101` does not exist, the query likewise makes no changes. Thus **zero counters have multiple causes**: node not found, data already in desired state, or update condition not met. You must inspect existence and current values to tell them apart.

### Step 4: Read Back After Transaction Commit

```cypher
OPTIONAL MATCH (u:AppUser {id: 'u-101'})
RETURN count(u) AS matchingNodes,
       head(collect(u.status)) AS actualStatus,
       head(collect(u.version)) AS actualVersion;
```

Given the unique key and expected outcome from Step 3:

- `matchingNodes = 1`: there is exactly one account for the business key.
- `actualStatus = 'ACTIVE'`: the current status matches expectations.
- `actualVersion = 1`: on freshly initialized sample data, the version incremented once.

If `matchingNodes = 0`, no node exists; if `actualStatus` is wrong, the update did not achieve the requirement. The `version` value is purely an **application-maintained** business mechanism—Neo4j does not automatically increment it on every write.

**Where you read back matters:** reading within the same transaction sees uncommitted changes. To verify persisted results, let the write transaction commit first and perform the read afterward. A single Java Driver session automatically preserves causal ordering across sequential transactions; when reading from another session or in a multi-node cluster, pass bookmarks or use an appropriate bookmark manager.

### Step 5: Verify Both Relationships and Deletions

Create another target entity and a relationship:

```cypher
MERGE (u:AppUser {id: 'u-102'})
ON CREATE SET u.name = 'Nam';

MATCH (a:AppUser {id: 'u-101'})
MATCH (b:AppUser {id: 'u-102'})
MERGE (a)-[r:FOLLOWS]->(b)
ON CREATE SET r.createdAt = datetime()
RETURN type(r) AS relationshipType;
```

On initial creation of the relationship, observe `relationshipsCreated`. Verify the actual structure:

```cypher
MATCH (a:AppUser {id: 'u-101'})-[r:FOLLOWS]->
      (b:AppUser {id: 'u-102'})
RETURN a.id AS follower, type(r) AS relation,
       b.id AS followed, r.createdAt AS createdAt;
```

The read-back result must show an edge with the **right direction, right type, and right two endpoints**, not just `relationshipsCreated = 1`.

When deleting a node that has relationships, you can use:

```cypher
MATCH (u:AppUser {id: 'u-102'})
DETACH DELETE u;
```

After this operation, statistics can include **both** `nodesDeleted` and `relationshipsDeleted`. Read back to confirm neither the node nor the attached relationship remains:

```cypher
OPTIONAL MATCH (u:AppUser {id: 'u-102'})
RETURN count(u) AS remainingUsers;

MATCH (a:AppUser {id: 'u-101'})-[r:FOLLOWS]->()
RETURN count(r) AS remainingOutgoingFollows;
```

On the sample data containing only the newly created relationship, both results are expected to be 0. In a real database, `remainingOutgoingFollows` may be greater than 0 because `u-101` still follows other accounts; in that case, check for **the specific target relationship** rather than expecting all `FOLLOWS` relationships to vanish.

## 4. Retrieving Statistics and Verifying via the Java Driver

In Java applications, the key API is `ResultSummary.counters()`, which returns `SummaryCounters`. The snippet below uses the Java Driver with managed transactions; replace the URI, password, and database with your environment configuration:

```java
import java.util.Map;
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.summary.ResultSummary;
import org.neo4j.driver.summary.SummaryCounters;

public class VerifyNeo4jWrite {
    public static void main(String[] args) {
        try (
            Driver driver = GraphDatabase.driver(
                "neo4j://localhost:7687",
                AuthTokens.basic("neo4j", "change-me")
            );
            Session session = driver.session(SessionConfig.forDatabase("neo4j"))
        ) {
            Map<String, Object> params = Map.of(
                "id", "u-101",
                "name", "Mai",
                "status", "ACTIVE"
            );

            // executeWrite returns only after the write transaction commits successfully.
            ResultSummary summary = session.executeWrite(tx ->
                tx.run("""
                    MERGE (u:AppUser {id: $id})
                    ON CREATE SET u.name = $name, u.status = $status
                    ON MATCH SET u.status = $status
                    """, params).consume()
            );

            SummaryCounters counters = summary.counters();
            System.out.printf(
                "created=%d, propertiesSet=%d, updated=%s%n",
                counters.nodesCreated(),
                counters.propertiesSet(),
                counters.containsUpdates()
            );

            // Read using a new transaction in the same session.
            String actualStatus = session.executeRead(tx ->
                tx.run("""
                    MATCH (u:AppUser {id: $id})
                    RETURN u.status AS status
                    """, Map.of("id", "u-101"))
                  .single()
                  .get("status")
                  .asString()
            );

            if (!"ACTIVE".equals(actualStatus)) {
                throw new IllegalStateException(
                    "Post-write status mismatch: " + actualStatus
                );
            }

            System.out.println("Verified: status = " + actualStatus);
        }
    }
}
```

Details to understand clearly:

- `consume()` returns `ResultSummary` **and consumes the remainder of the result stream**. If you need both records from `RETURN` and summary statistics, read the required records **before** calling `consume()`, or use `Driver.executableQuery(...).execute()` and obtain `records()` and `summary()` from the result.
- `executeWrite(...)` runs a managed transaction and may retry the callback on transient errors. Therefore, logic inside the callback should be **idempotent**—do not send external notifications, increment global variables, or cause irreversible side effects on each attempt.
- `containsUpdates() == false` does not mean failure: a `MERGE` matching existing data or a query whose filter excludes every candidate can produce zero updates.
- `single()` throws an exception if zero records or more than one record is returned; this is a useful assertion when an identifying key must pinpoint exactly one node. Unique constraints should still be set up beforehand.
- Within the same session, sequential transactions are coordinated by the Neo4j Driver using bookmarks so a subsequent read sees the committed results of the preceding write, even in a clustered deployment.

In Spring Data Neo4j, `repository.save(...)` operates via entities and `@Transactional` manages service-layer transaction boundaries. However, the object returned from `save` **does not replace post-commit database verification** and does not directly expose Cypher counters like `ResultSummary`. When a task needs exact Cypher operation counts, use the Java Driver to obtain the summary; when business verification is needed, read back by unique key via the repository or `Neo4jClient` inside a read transaction **after the write transaction finishes**. Watch out for Spring's proxy-based `@Transactional` limitation: a method calling another `@Transactional` method on the same object normally does not start a new transaction boundary.

## 5. When You Need to Check How Many Records Were Updated

Query counters have no universal metric for "number of business entities genuinely updated" across all Cypher statements. When you need to know how many nodes met the write condition, express it directly in the query.

Example updating status on overdue orders:

```cypher
MATCH (o:Order)
WHERE o.status = 'PENDING'
  AND o.expiredAt < datetime()
WITH DISTINCT o
SET o.status = 'EXPIRED'
RETURN count(o) AS affectedOrders;
```

`affectedOrders` is the number of distinct `Order` nodes passing through the update step in **this query**. `propertiesSet` instead represents the number of property assignments, so never equate the two numbers. `affectedOrders = 0` can be completely normal if no orders needed expiring.

When updating a record based on its current version (optimistic locking), include a `version` condition:

```cypher
MATCH (o:Order {id: $orderId, version: $expectedVersion})
SET o.status = $newStatus,
    o.version = o.version + 1
RETURN count(o) AS updatedOrders;
```

If `Order.id` is unique and `updatedOrders = 1`, the query matched the expected version and executed the write branch. If it is 0, **do not immediately conclude the order does not exist**: the version may have changed due to another request. The application should read back `id` and `version` (or return a conflict error), and report success only after the transaction commits.

In queries with multiple `MATCH` clauses or path expansions, row counts can multiply. Use `WITH DISTINCT target` before `SET` when business logic intends each target node to be processed once. When checking relationships, verify both direction and relationship type.

## 6. Transaction Boundaries and Situations Prone to Misinterpretation

| Observed Symptom | Correct Explanation | Next Verification Step |
| --- | --- | --- |
| Query finishes, all counters are 0 | No update operations recorded; possibly empty `MATCH` or no modification needed | Read by key and compare against desired state |
| `nodesCreated = 0` after `MERGE` | No new node was created in this run | Check whether the node already existed and its properties are right |
| `propertiesSet > 0` | Property assignment operations occurred | Read back values; do not infer node count or whether values changed from before |
| `RETURN count(*)` returns `1` | One input row was counted by `count(*)` (depending on the query) | Check what `count` is counting; inspect counters and a verification query |
| Counters present, yet transaction later rolled back | Metrics describe query execution, not proof of commit | Confirm commit succeeded, then read back |
| Reading in the same transaction sees new data | A transaction sees its own uncommitted changes | Read again in a new transaction after commit |
| Reading from another session in a cluster sees stale data | Causal consistency between transactions/sessions may not be ensured | Pass bookmarks or use a bookmark manager; confirm target database |
| Single `DETACH DELETE` deletes many relationships | Deletes the node along with all relationships attached to it | Compare `nodesDeleted`, `relationshipsDeleted`, and target graph |
| Running batched `CALL { ... } IN TRANSACTIONS` encounters an error | Earlier committed batches may remain persisted | Inspect each batch and summarize actual data; never assume the whole import is one transaction |

**Commits and re-reads are point-in-time:** a successful verification at read time does not lock that state forever. If multiple requests can concurrently modify the same node, use constraints, proper transactions, and version/concurrency checks. If you need to trace *who* changed *what* and *when*, design an audit log or business events; query counters only describe a single execution.

### `EXPLAIN` and `PROFILE` Do Not Replace Data Verification

- `EXPLAIN <query>` builds the execution plan **without running the statement**; never use its output to claim a write occurred.
- `PROFILE <query>` **actually executes the statement** to gather row counts, DbHits, and plan details. For write queries, `PROFILE` mutates data too; use it only when you genuinely intend to execute.
- Rows, DbHits, and timing in execution plans primarily serve **query tuning**, not verifying counters or post-commit values. When an update query is slow, check indexes/constraints on lookup keys and how many nodes/relationships are touched.

## 7. Practice Lab and Completion Criteria

On a test database, perform the following steps:

1. Create a unique constraint on `AppUser.id`, then run `MERGE` for account `u-101` twice. Note the difference in `nodesCreated` between the two runs.
2. Run the command to transition status to `ACTIVE` and increment `version` twice. Explain why the second run updates nothing.
3. Read back the node and check `id`, `status`, and `version`; try changing `id` to a nonexistent value to observe an empty result.
4. Create a `FOLLOWS` relationship, inspect statistics, and query back the exact relationship direction. Delete the target node with `DETACH DELETE`, then verify both the target node and attached edge are gone.
5. In a Java application, collect `SummaryCounters` and read back data **after** `executeWrite` completes; test both a valid request and one whose target is not found.

A write operation is considered **verified against business requirements** when all of the following hold simultaneously:

- The write transaction finishes and commits successfully; exceptions are not swallowed.
- The query targets the right database, labels/types, and identifying keys; required identity constraints are in place.
- Counters are consistent with the operation type (create, modify, delete, idempotent) and are not misused as business values.
- A post-commit read query confirms the expected entity count, properties, relationship direction, and version.
- Explicit handling exists for missing targets, already-up-to-date data, update conflicts, and reads lacking causal ordering.

## Official References

- [Neo4j Java Driver — Explore the query execution summary](https://neo4j.com/docs/java-manual/current/result-summary/): obtaining `ResultSummary`, reading counters, and understanding `consume()`.
- [Neo4j Java Driver — Run your own transactions](https://neo4j.com/docs/java-manual/current/transactions/): managed transactions, commit/rollback, and retryable callbacks.
- [Neo4j Java Driver — Coordinate parallel transactions](https://neo4j.com/docs/java-manual/current/bookmarks/): sessions, bookmarks, and causal consistency across writes/reads.
- [Neo4j Cypher Manual — MERGE](https://neo4j.com/docs/cypher-manual/current/clauses/merge/): `MERGE`, `ON CREATE`, `ON MATCH`, and unique constraints semantics.
- [Neo4j Query API — Retrieve query counters](https://neo4j.com/docs/query-api/current/query-counters/): names and meanings of statistics fields in Query API responses.
