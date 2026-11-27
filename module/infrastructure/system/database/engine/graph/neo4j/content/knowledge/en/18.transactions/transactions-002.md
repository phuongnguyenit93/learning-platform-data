# Implicit and Explicit Transactions in Neo4j

## 1. What Is a Transaction and Why Distinguish Two Execution Modes?

In **Neo4j**, data is stored using the **property graph** model consisting of nodes, relationships, labels, and properties. When an application uses Cypher to create nodes, modify properties, or connect nodes with relationships, those operations take place inside a **transaction**. A transaction determines whether a group of operations is **committed** to save its results or **rolled back** to discard uncommitted changes.

Consider the workflow of adding a member to a project group. The application needs to:

1. Create or locate the `(:AppUser {id: 'u-101'})` node.
2. Create or locate the `(:Project {id: 'p-01'})` node.
3. Create the `(user)-[:MEMBER_OF]->(project)` relationship.

If these three steps form one business unit, creating the user without creating the relationship can leave an incomplete state. This can be solved with **a single Cypher statement** that executes all steps, or with **an explicit transaction** enclosing multiple Cypher statements.

Neo4j supports two common ways of organizing execution:

- **Implicit / auto-commit transaction**: the client submits one Cypher statement; the system automatically manages the transaction for that statement.
- **Explicit transaction**: the application/client explicitly defines the transaction boundary and executes one or more Cypher statements inside it. In the Java Driver, an explicit transaction can be managed automatically via a callback (*managed transaction*) or controlled directly by calling `commit()`/`rollback()` (*unmanaged transaction*).

**Key takeaway:** A single Cypher statement run in an implicit transaction is still atomic. The real difference lies in **who manages the transaction boundary** and **whether multiple Cypher statements can be grouped into a single commit**.

## 2. Placing Transactions in the Context of ACID

| Property | Meaning when operating on a Neo4j graph | Key points to remember |
| --- | --- | --- |
| **Atomicity** | All changes within the same transaction are committed together or rolled back | Two statements executed in two separate auto-commit transactions do **not** form an atomic unit |
| **Consistency** | Transactions must obey database constraints; business rules must be expressed by the application/queries | Unique constraints protect keys; Neo4j does not inherently know the maximum number of members allowed in a project |
| **Isolation** | Concurrent transactions use isolation and locking mechanisms to prevent reading uncommitted changes | Default is **read committed**; does not inherently prevent all non-repeatable reads or business conflicts |
| **Durability** | Successfully committed transactions are persisted by Neo4j according to the system's guarantees | Seeing data **inside an uncommitted transaction** does not prove the data is durable |

Within a transaction, a later query can read changes made by earlier queries in **that same transaction**. Other transactions cannot see uncommitted changes. When a transaction ends in rollback, updates made in that transaction never become committed state.

To reduce contention, keep transactions short, avoid external non-database work while holding a transaction open, and use appropriate constraints and business locks.

## 3. Implicit (Auto-Commit) Transactions

### 3.1. Mechanism

In auto-commit mode, each time a Cypher statement is sent through the appropriate API, Neo4j creates a transaction for that execution. For example, the Java Driver uses `session.run(...)` to execute in an **implicit transaction**.

```java
try (Session session = driver.session(
        SessionConfig.forDatabase("neo4j"))) {
    session.run(
        "MERGE (u:AppUser {id: $id})",
        Map.of("id", "u-101")
    ).consume();
}
```

Here:

- `session.run(...)` sends one Cypher statement in an implicit transaction.
- `consume()` drains any remaining results, completing the execution and returning a `ResultSummary` if needed.
- Only when the transaction finishes and commits successfully does the node created by the statement (if it did not already exist) become durable state.

The Java Driver returns `Result` in a streaming/lazy manner. **Do not treat the moment `session.run(...)` returns as proof that the commit has completed.** With implicit transactions, commit is guaranteed once the result has been fully consumed; use `consume()`, `list()`, or iterate to the end of the stream before relying on the write result in subsequent operations. If an error occurs while consuming the result, the application must handle it.

In Neo4j Browser or cypher-shell, each ordinary Cypher statement can also be executed with a client-managed transaction; specific transaction commands/modes depend on the tool.

### 3.2. Each Auto-Commit Is Its Own Boundary

Suppose the application runs sequentially:

```cypher
MERGE (u:AppUser {id: 'u-101'});
```

```cypher
MERGE (p:Project {id: 'p-01'});
```

```cypher
MATCH (u:AppUser {id: 'u-101'})
MATCH (p:Project {id: 'p-01'})
MERGE (u)-[:MEMBER_OF]->(p);
```

If the client executes **these three statements as three implicit transactions**, statements 1 and 2 may already commit before statement 3 fails. In that case, the nodes may exist while the relationship was never created. Placing three statements next to each other in documentation or sending them from the same session **does not automatically combine them into one transaction**.

Conversely, they can be combined into **a single Cypher statement**:

```cypher
MERGE (u:AppUser {id: 'u-101'})
MERGE (p:Project {id: 'p-01'})
MERGE (u)-[:MEMBER_OF]->(p)
RETURN u.id AS userId, p.id AS projectId;
```

When executed normally inside a single implicit transaction, all three operations belong to **the same statement** and the same transaction: if the statement fails, its uncommitted changes are rolled back. However, for complex business workflows, splitting logic into multiple clear statements inside an explicit transaction can be easier to manage.

### 3.3. Advantages and Limitations

| Advantages | Limitations to account for |
| --- | --- |
| Simple API, well suited for standalone queries | Cannot use multiple auto-commit `session.run(...)` calls to guarantee all-or-nothing commit |
| Minimal commit/rollback boilerplate | Must consume the result to confirm query completion |
| Suitable for read queries, single-step writes, or standalone admin commands | Java Driver does not auto-retry implicit transactions like managed transactions |
| Required mode for certain batch operations, such as `CALL { ... } IN TRANSACTIONS` | Batch writes commit per batch and do not provide whole-operation atomicity |

## 4. Explicit Transactions

### 4.1. Mechanism and Lifecycle

An explicit transaction has a clear boundary:

```text
BEGIN transaction
    Query A: create or find user
    Query B: create or find project
    Query C: create MEMBER_OF relationship
    (can re-read results within the transaction)
COMMIT  -> save all successful changes together
    or
ROLLBACK -> discard uncommitted changes of A, B, C
```

If the third statement throws an exception and the transaction is rolled back, uncommitted changes from statements 1 and 2 are also discarded. A single transaction can contain multiple Cypher statements, including read queries to check preconditions and write queries.

Important distinction:

- **Managed transaction:** the application passes a callback to the Driver via `session.executeRead(...)` or `session.executeWrite(...)`; the Driver manages commit/rollback and can retry on transient errors.
- **Unmanaged transaction:** the application calls `session.beginTransaction()`, followed by `tx.commit()` or `tx.rollback()`. The application controls the lifecycle directly and must implement retry logic itself if needed.

Both allow multiple Cypher statements to share one transaction, unlike separate implicit transactions.

### 4.2. Managed Transaction Example with the Java Driver

The following example uses the synchronous Driver API of the current Neo4j Java Driver:

```java
import java.util.Map;
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public class ManagedTransactionExample {
    public static void main(String[] args) {
        try (
            Driver driver = GraphDatabase.driver(
                "neo4j://localhost:7687",
                AuthTokens.basic("neo4j", "change-me")
            );
            Session session = driver.session(
                SessionConfig.forDatabase("neo4j")
            )
        ) {
            Map<String, Object> params = Map.of(
                "userId", "u-101",
                "projectId", "p-01"
            );

            session.executeWrite(tx -> {
                tx.run("""
                    MERGE (u:AppUser {id: $userId})
                    """, params).consume();

                tx.run("""
                    MERGE (p:Project {id: $projectId})
                    """, params).consume();

                tx.run("""
                    MATCH (u:AppUser {id: $userId})
                    MATCH (p:Project {id: $projectId})
                    MERGE (u)-[:MEMBER_OF]->(p)
                    """, params).consume();

                return null;
            });

            // By this point, executeWrite has returned after a successful commit.
            long membershipCount = session.executeRead(tx ->
                tx.run("""
                    MATCH (u:AppUser {id: $userId})
                          -[r:MEMBER_OF]->
                          (p:Project {id: $projectId})
                    RETURN count(r) AS total
                    """, params)
                  .single()
                  .get("total")
                  .asLong()
            );

            if (membershipCount != 1L) {
                throw new IllegalStateException(
                    "MEMBER_OF relationship does not match expectations"
                );
            }
            System.out.println("Committed and verified MEMBER_OF");
        }
    }
}
```

In this example:

1. All three `tx.run(...)` calls execute inside **one managed write transaction**.
2. If any statement fails or the callback throws an exception, the active transaction is not committed and will roll back.
3. After `executeWrite(...)` finishes successfully, the example uses a **new read transaction** via `executeRead(...)` to verify that the relationship was committed.
4. `MERGE` allows node/relationship creation statements to be rerun without producing duplicates when the data model and identifier keys are properly managed.

In a real system, you should have uniqueness constraints on `AppUser.id` and `Project.id`, for example:

```cypher
CREATE CONSTRAINT app_user_id_unique IF NOT EXISTS
FOR (u:AppUser)
REQUIRE u.id IS UNIQUE;

CREATE CONSTRAINT project_id_unique IF NOT EXISTS
FOR (p:Project)
REQUIRE p.id IS UNIQUE;
```

These two constraint creation statements are independent schema management steps and should be run ahead of business workflows. Avoid mixing schema migrations inside frequent data-write callbacks.

**Crucial for retries:** The Driver may re-run the entire `executeWrite` callback upon encountering a transient error. Therefore, the callback must be safe to re-execute. Never send emails, call external payment APIs, increment shared counters, or perform non-rollbackable side effects inside the callback. For record creation, rely on business keys and idempotent design.

### 4.3. Unmanaged Transaction and Explicit Rollback Example

When you need direct control over commit timing or want to roll back based on business conditions, use `beginTransaction()`:

```java
import java.util.Map;
import org.neo4j.driver.Session;
import org.neo4j.driver.Transaction;

try (Session session = driver.session()) {
    try (Transaction tx = session.beginTransaction()) {
        tx.run("""
            MERGE (u:AppUser {id: $id})
            ON CREATE SET u.name = $name
            """, Map.of("id", "u-102", "name", "Binh")
        ).consume();

        long matching = tx.run("""
            MATCH (u:AppUser {id: $id})
            RETURN count(u) AS total
            """, Map.of("id", "u-102")
        ).single().get("total").asLong();

        if (matching != 1L) {
            tx.rollback();
            throw new IllegalStateException(
                "Unable to uniquely identify AppUser"
            );
        }

        tx.commit();
    }
}
```

In the example above, `tx.commit()` is the point where the result is confirmed. If execution leaves the `try` block without committing or rolling back, closing the transaction rolls back all uncommitted changes. Never treat a `tx.run(...)` call returning normally as meaning the transaction has committed. Unlike managed transactions, `beginTransaction()` **does not automatically retry the unit of work** on transient errors.

Some environments use explicit transactions directly in CLI tools. For example, in interactive **cypher-shell**, there are client commands:

```text
:begin
MERGE (u:AppUser {id: 'u-103'});
MERGE (p:Project {id: 'p-02'});
:commit
```

To discard uncommitted changes, use `:rollback` instead of `:commit`. The colon-prefixed commands above are **client tool commands**, not Cypher syntax to pass directly into `session.run(":begin")`. Transaction capabilities and controls in Neo4j Browser, cypher-shell, or admin tools may differ; check the documentation for the exact client/version you are using.

## 5. Direct Comparison

| Criterion | Implicit Transaction | Explicit Transaction |
| --- | --- | --- |
| Boundary | Typically a single statement sent via client/API | Defined by the client/application; can span multiple statements |
| Commit | Automatic after execution/result consumption finishes | Managed: Driver commits when callback succeeds; unmanaged: call `commit()` |
| Rollback | If the statement fails, that statement's transaction is aborted | An error or rollback can discard all uncommitted steps in the transaction |
| Java Driver | `session.run(cypher)` | `session.executeWrite/read(...)` or `session.beginTransaction()` |
| Retry | No automatic retry mechanism equivalent to managed transactions | Managed transactions can retry transient errors; unmanaged requires custom handling |
| Best-fit scenarios | Independent queries, single-step writes, certain batch import operations | Multiple statements that must succeed together; conditional updates coordinating multiple nodes/relationships |
| Common risks | Assuming multiple `session.run` calls form one transaction; forgetting to consume results | Forgetting to commit, holding transactions open too long, side effects inside retried callbacks |

### Is a Single Cypher Statement with Multiple `CREATE` Clauses an Explicit Transaction?

**Not necessarily.** If that Cypher statement runs via `session.run(...)`, it is an **implicit transaction** containing multiple graph operations. Classification depends on **how the client opens/manages the transaction**, not on how many nodes or relationships a single statement modifies.

### Is a Transaction Containing Only One Cypher Statement Implicit?

**Not necessarily.** If the application calls `beginTransaction()`, runs a single Cypher statement, and calls `commit()`, it is still an **explicit transaction**.

## 6. Notable Exception: `CALL { ... } IN TRANSACTIONS`

When ingesting large datasets, you may need to split writes into multiple batches to avoid an overly large transaction:

```cypher
UNWIND range(1, 1000) AS userNumber
CALL {
    WITH userNumber
    MERGE (:SampleUser {id: userNumber})
} IN TRANSACTIONS OF 100 ROWS;
```

Here, Cypher creates multiple batches and each batch is executed and committed in its own transaction according to the `IN TRANSACTIONS` clause. This example deliberately uses a small dataset; in production systems, choose the batch size based on workload, constraints, and recovery requirements.

**Two ways this differs completely from a regular transaction:**

1. The `CALL { ... } IN TRANSACTIONS` clause must be executed in an **implicit transaction** on the client side; do not place this entire statement inside `executeWrite(...)` or `beginTransaction()`. This is a case where you must match the transaction mode to the Cypher feature.
2. If a later batch fails, **earlier committed batches may still persist**. You cannot assume all 1,000 rows will roll back together. Therefore, batch ingestion designs should be idempotent, with unique keys/constraints, checkpoints, and safe rerunnability.

Java Driver example executing the batch statement in an implicit transaction:

```java
try (Session session = driver.session(
        SessionConfig.forDatabase("neo4j"))) {
    session.run("""
        UNWIND range(1, 1000) AS userNumber
        CALL {
            WITH userNumber
            MERGE (:SampleUser {id: userNumber})
        } IN TRANSACTIONS OF 100 ROWS
        """).consume();
}
```

Note that subquery variable import syntax varies across Cypher versions; the `CALL { WITH userNumber ... }` pattern is common in Neo4j 5, while newer releases also add scoped variable syntax `CALL (userNumber) { ... }`. Check your server version if your application needs to support multiple Neo4j versions.

## 7. Spring Data Neo4j Integration

**Spring Data Neo4j (SDN)** is commonly used in Spring Boot applications with repositories, entities, and object relationships. When multiple graph operations must succeed together, place the transaction boundary at the **service layer**:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class RegistrationService {
    private final AppUserRepository userRepository;
    private final ProjectRepository projectRepository;

    public RegistrationService(
            AppUserRepository userRepository,
            ProjectRepository projectRepository) {
        this.userRepository = userRepository;
        this.projectRepository = projectRepository;
    }

    @Transactional
    public void register(AppUser user, Project project) {
        userRepository.save(user);
        projectRepository.save(project);
        // If there are relationship changes between entities,
        // perform them within this same transaction.
    }
}
```

This illustrative code assumes the application has already defined `AppUser`, `Project`, and their corresponding repositories. How relationships are attached and persisted also depends on the project's entity mappings. The main point is that both `save` calls participate in the same Spring-managed transaction when the method is invoked through the Spring proxy and transaction management is properly configured.

Several important notes:

- `@Transactional` rolls back by default on unchecked exceptions (`RuntimeException`/`Error`); for checked exceptions, you may need to configure `rollbackFor` per application policy.
- If a `@Transactional` method **calls another annotated method on itself** within the same instance, standard Spring proxying will not apply a new transaction boundary to that internal call.
- Avoid mixing Spring-managed transactions with `session.run(...)` on an independent Driver/session if you want statements to belong to the **same** transaction.
- If business logic needs to verify data **after commit**, schedule the read in a subsequent transaction or use an appropriate after-commit hook. Reading inside the same `@Transactional` method only verifies state visible within the ongoing transaction.
- In multithreaded code, never share a mutable Java Driver `Session` or `Transaction` across threads; each unit of work should obtain its own appropriate session/transaction.

## 8. What Happens on Errors, Timeouts, or Concurrent Conflicts?

| Situation | Outcome to understand | How to handle |
| --- | --- | --- |
| First implicit statement committed; later implicit statement fails | The earlier statement does **not** roll back with the later one | Combine into a single explicit transaction when all-or-nothing is required |
| Statement inside explicit transaction fails | The transaction may need to roll back; uncommitted changes must not be retained | Handle the exception, roll back / let the managed transaction roll back |
| `executeWrite` callback is retried | All logic inside the callback may re-execute | Keep logic idempotent; avoid external non-DB side effects |
| `beginTransaction` without calling `commit()` | Transaction rolls back when closed uncommitted | Call commit explicitly only after required checks pass |
| Long-held transactions / lock contention | Increased lock waits, deadlocks, timeouts, or degraded throughput | Shorten transactions, update in a consistent order, retry transient errors |
| Multiple writers updating the same property | Data conflicts or lost updates if read-then-write is poorly designed | Use locking, version conditions, and appropriate update patterns |
| Connection drops during commit | Client cannot be sure whether the commit reached the server | Check state by business key / idempotency key before retrying |
| Reading from another session in a cluster | Without a bookmark, the read may not have causal consistency with the write | Use bookmarks / bookmark manager when passing across sessions |
| `CALL { ... } IN TRANSACTIONS` fails mid-way | Already-committed batches may persist | Track progress and rerun safely using unique keys |

### Isolation Does Not Replace Concurrency Control

Under default read committed isolation, a transaction cannot read uncommitted data from another transaction. However, when a transaction reads a value at one moment and writes based on that value, the application must still guard against **race conditions**, locking issues, and stale data versions.

Example of a version-conditioned update:

```cypher
MATCH (p:Project {
  id: $projectId,
  version: $expectedVersion
})
SET p.status = $newStatus,
    p.version = p.version + 1
RETURN count(p) AS updatedProjects;
```

If `updatedProjects = 0`, either the project does not exist **or** its version has already changed. Do not treat every zero result as a network error or retry infinitely. To avoid subtle race conditions, verify the locking/optimistic-locking mechanism of your stack, especially for workflows with financial invariants or contested resources.

## 9. Verifying That a Transaction Was Truly Persisted

For graph update workflows, apply three layers of verification:

1. **Query completed:** the API fully consumed the result; exceptions and transaction errors were handled. For explicit transactions, wait for `commit()` or the managed transaction to return successfully.
2. **Expected updates occurred:** use `ResultSummary.counters()` if you need counts of nodes/relationships created, deleted, or properties set. Remember that counters describe what the query executed, and **do not by themselves prove an outer transaction has committed**.
3. **Correct post-commit state:** run a new read transaction querying the expected node keys and relationships; check both property values and record counts.

Example verification query after creating a membership:

```cypher
OPTIONAL MATCH (u:AppUser {id: 'u-101'})
OPTIONAL MATCH (p:Project {id: 'p-01'})
OPTIONAL MATCH (u)-[m:MEMBER_OF]->(p)
RETURN count(DISTINCT u) AS users,
       count(DISTINCT p) AS projects,
       count(m) AS memberships;
```

On a test database with uniqueness constraints and no duplicate data, the expected state is `users = 1`, `projects = 1`, `memberships = 1`. Reading the data inside an **uncommitted** transaction does not prove the changes are durably saved.

When verifying from another session/instance on a Neo4j cluster, ensure **causal consistency** via properly propagated bookmarks or driver-managed read-your-writes within the same session.

## 10. Hands-On: Choosing the Right Transaction Mode

On a test database, run the following scenarios and note where each transaction begins and ends:

1. **One standalone statement:** use an implicit transaction to `MERGE` an `AppUser`; ensure the result is consumed and read the node back afterward.
2. **Three auto-commit statements:** sequentially create a user, create a project, and create a membership using three separate statements. Simulate the third statement failing or not running; check whether the nodes from earlier statements still exist.
3. **One managed transaction:** move all three statements into an `executeWrite` callback; intentionally throw an exception before the callback succeeds, then read back to verify the new changes in the transaction rolled back. Next, run the success case and verify the membership.
4. **One unmanaged transaction:** open `beginTransaction()`, update a node, then call `rollback()`; verify the value did not change. Repeat with `commit()`.
5. **Batch writes:** run `CALL { ... } IN TRANSACTIONS` in an implicit transaction; explain why it must not be placed inside `executeWrite(...)` and why committed batches can still exist when a later batch fails.
6. **Spring Data Neo4j:** identify the `@Transactional` boundary in a service, state the rollback conditions, and show how to place post-commit verification.

Answer these three questions for yourself:

- Why do three consecutive `session.run(...)` calls not guarantee rolling back together?
- When should you choose `executeWrite(...)`, when should you choose `beginTransaction()`, and why must a managed transaction callback be safe to retry?
- Why does a `MATCH ... RETURN` inside the same transaction not replace post-`commit` verification?

**Completion criteria:** distinguish implicit and explicit transactions by execution boundary; pick the right API to build an atomic group of updates; know when commit/rollback takes place; understand the batch import exception, retries, and post-commit verification.

## Official References

- [Neo4j Java Driver Manual — Run your own transactions](https://neo4j.com/docs/java-manual/current/transactions/): implicit, managed, and unmanaged transactions; commit, rollback, and retry.
- [Neo4j Java Driver Manual — Query the database](https://neo4j.com/docs/java-manual/current/query-simple/): query execution, API selection, and result consumption.
- [Neo4j Cypher Manual — Transactions](https://neo4j.com/docs/cypher-manual/current/transactions/): transaction boundaries, atomicity, and transaction handling in Cypher.
- [Neo4j Cypher Manual — CALL subqueries in transactions](https://neo4j.com/docs/cypher-manual/current/subqueries/subqueries-in-transactions/): executing statements across multiple batch transactions.
- [Neo4j Java Driver Manual — Bookmarks](https://neo4j.com/docs/java-manual/current/bookmarks/): ensuring update visibility order across sessions in a cluster.
- [Spring Data Neo4j Reference — Transactions](https://docs.spring.io/spring-data/neo4j/reference/transactions.html): managing transactions when using Spring Data Neo4j.
