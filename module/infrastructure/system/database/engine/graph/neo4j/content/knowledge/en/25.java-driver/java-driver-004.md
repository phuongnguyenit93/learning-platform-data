# Driver-Managed Transactions for Reads and Writes in Neo4j Java Driver

## Learning Objectives

After this lesson, you will be able to:

- Explain what a **managed transaction** is and distinguish it from an **implicit transaction** or **explicit transaction** in Neo4j Java Driver.
- Use `Session.executeRead(...)` and `Session.executeWrite(...)` to execute one or more Cypher statements within proper transaction boundaries.
- Manage the lifecycles of `Driver`, `Session`, callbacks, and query results; choose READ/WRITE modes for proper routing.
- Understand commit/rollback conditions, transient errors, and the **automatic retry** mechanism of managed transactions.
- Design callbacks free of external side effects outside Neo4j, handle duplicate requests, and protect data with stable keys/constraints.
- Write tests verifying atomicity, error handling, thread safety, and correctness of read/write operations.

This lesson is in the **Java Driver** chapter of the **DATABASE_ENGINE_GRAPH_NEO4J** module. Java applications use Neo4j to model a **property graph** and query nodes, relationships, and paths with **Cypher**. When a business operation modifies multiple graph elements, a **transaction** ensures changes commit or roll back together. Managed transactions are how the Java Driver orchestrates those boundaries and handles retries for eligible transient errors.

> Examples in this lesson use the `executeRead` / `executeWrite` APIs from Neo4j Java Driver 5.x and newer versions with corresponding APIs. Legacy docs or codebases may use `readTransaction` / `writeTransaction`; do not mix APIs across versions. Check your driver version, Neo4j DBMS, and active official guides before adopting examples into a project.

## 1. Why Do We Need a Managed Transaction?

Suppose a sales system has the following graph:

~~~mermaid
flowchart LR
    C["Customer<br/>customerId"] -->|PLACED| O["Order<br/>orderId, totalCents"]
    O -->|CONTAINS| P["Product<br/>sku"]
~~~

An order placement request might involve:

1. Verifying that the `Customer` exists.
2. Creating or identifying the `Order` keyed by `orderId`.
3. Attaching the `PLACED` relationship from the customer to the order.
4. Returning the order ID after **all write operations** complete.

If the order creation statement commits on its own while creating the relationship fails, the graph may contain an order not linked to any customer. Managed transactions allow **multiple Cypher statements to share a single commit/rollback unit**; if the callback fails, uncommitted changes from that transaction are discarded.

There are three common transaction forms in the Java Driver:

| Call style | Who decides commit/rollback? | Characteristics |
| --- | --- | --- |
| `session.run(cypher, params)` | Driver runs an **implicit transaction** for the statement | Concise for a single statement; multiple `session.run` calls do not share one transaction |
| `session.executeRead(tx -> ...)` / `executeWrite(tx -> ...)` | **Driver manages** the transaction around the callback | Selects read/write routing, commits on success, rolls back on error, can retry eligible errors |
| `session.beginTransaction()` | **Application explicitly manages** `commit()` / `rollback()` | Flexible, but must handle lifecycle and retry policies itself |

**Managed** does not mean Neo4j automatically fixes all business errors. The Driver manages the transaction and certain technical faults; the application still decides **identity keys, correctness, duplicate request handling, and update ordering**.

## 2. Lifecycle of a Managed Transaction

The methods follow the general form:

~~~java
T result = session.executeRead(tx -> {
    // One or more read-only Cypher statements.
    return ...;
});

T result = session.executeWrite(tx -> {
    // One or more write Cypher statements.
    return ...;
});
~~~

`tx` is the **driver-provided transaction context**. The application runs `tx.run(...)` inside the callback, extracts the needed results, and returns a Java value. Do not call `commit()` or `rollback()` directly on this context.

~~~mermaid
flowchart TD
    A["session.executeRead / executeWrite"] --> B["Driver opens appropriate transaction"]
    B --> C["Invoke callback with tx"]
    C --> D{"Callback completes?"}
    D -->|Returns result| E["Driver COMMIT"]
    D -->|Throws error| F["Driver ROLLBACK"]
    E --> G{"Commit succeeds?"}
    G -->|Yes| H["Return result to application"]
    G -->|Retryable error| R["Rollback / evaluate retry"]
    F --> R
    R --> S{"Driver allowed to retry?"}
    S -->|Yes| B
    S -->|No| X["Throw exception to application"]
    G -->|Non-retryable error| X
~~~

This is a conceptual diagram. **Not every error is retried**; authentication failures, constraint violations, Cypher errors, or business-thrown exceptions typically require application handling. The Driver only retries errors classified by its policy as retryable within the configured retry window.

### What Happens to the Callback Result?

- Callback succeeds and commit completes: `executeRead` / `executeWrite` returns the callback's return value to the caller.
- Callback throws an exception or the transaction fails to commit: the caller receives the error; the uncommitted transaction is rolled back by the driver/server mechanism.
- On a retryable error, **the entire callback may execute multiple times**, each in a fresh transaction.
- A Cypher statement succeeding **inside the callback** does not mean the transaction has committed. Report business success only after the managed transaction call itself returns cleanly.

## 3. Preparing Driver and Session with the Right Lifecycle

### 3.1. Adding the Java Driver Library

With Maven, declare the dependency (replace the placeholder with your chosen compatible version, or manage the version via a BOM/build config):

~~~xml
<dependency>
    <groupId>org.neo4j.driver</groupId>
    <artifactId>neo4j-java-driver</artifactId>
    <version>COMPATIBLE_DRIVER_VERSION</version>
</dependency>
~~~

`COMPATIBLE_DRIVER_VERSION` is a **placeholder**, not a real version string Maven can download. In Spring Data Neo4j or Spring Boot projects, rely on the framework's dependency management instead of forcing an incompatible driver version.

### 3.2. Create the Driver Once, a Session per Unit of Work

~~~java
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class DriverLifecycle {
    public static void main(String[] args) {
        String uri = System.getenv("NEO4J_URI");
        String user = System.getenv("NEO4J_USERNAME");
        String password = System.getenv("NEO4J_PASSWORD");

        try (Driver driver = GraphDatabase.driver(
                uri, AuthTokens.basic(user, password))) {
            driver.verifyConnectivity();

            try (Session session =
                    driver.session(SessionConfig.forDatabase("neo4j"))) {
                String greeting = session.executeRead(tx ->
                        tx.run("RETURN 'Neo4j ready' AS message")
                          .single()
                          .get("message")
                          .asString());
                System.out.println(greeting);
            }
        }
    }
}
~~~

The application requires those three environment variables configured before running. In real environments, use appropriate URIs, authentication, and connection security; never hardcode passwords into a repository.

**Lifecycles to remember:**

- **`Driver`:** create once and **share** across the application; the Driver manages a connection pool and is thread-safe. Close it on application shutdown.
- **`Session`:** lightweight and created per request/unit of work; **never share one Session across concurrent threads**. Close with `try-with-resources`.
- **`TransactionContext` (`tx`):** use only inside the callback; do not store it or pass it to another thread.
- **`Result`:** a result stream tied to the open transaction; read/`consume()` needed results **before the callback returns**.

When using multiple databases, specify the database explicitly via `SessionConfig.forDatabase(...)` to avoid default-database resolution round trips and targeting mistakes. In a cluster, `neo4j://` URIs enable routing via the routing driver; `bolt://` targets a single server address directly. Pick the URI according to your topology and operational requirements.

## 4. Reading Data with executeRead

### 4.1. Example: Reading an Order List

Read orders from a known `Customer` without mutating properties:

~~~cypher
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
RETURN o.orderId AS orderId,
       o.totalCents AS totalCents,
       o.status AS status
ORDER BY o.orderId
LIMIT 20;
~~~

Java Driver:

~~~java
import java.util.List;
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class OrderQueries {
    public record OrderSummary(
            String orderId, long totalCents, String status) {}

    public static List<OrderSummary> recentOrders(
            Driver driver, String customerId) {
        try (Session session =
                driver.session(SessionConfig.forDatabase("neo4j"))) {
            return session.executeRead(tx ->
                    tx.run("""
                        MATCH (c:Customer {customerId: $customerId})
                              -[:PLACED]->(o:Order)
                        RETURN o.orderId AS orderId,
                               o.totalCents AS totalCents,
                               o.status AS status
                        ORDER BY o.orderId
                        LIMIT 20
                        """, Map.of("customerId", customerId))
                      .list(row -> new OrderSummary(
                              row.get("orderId").asString(),
                              row.get("totalCents").asLong(),
                              row.get("status").asString())));
        }
    }
}
~~~

In this example:

1. Each call opens its own `Session` for the `neo4j` database.
2. `executeRead` starts a **managed read transaction** and provides `tx`.
3. `tx.run(query, parameters)` binds parameters safely, avoiding string concatenation of user input into Cypher.
4. `.list(mapper)` reads all results and maps them into Java records **while the transaction is alive**.
5. Once the callback and commit finish, the Java list no longer depends on `Result` or the Session.

**Why use `list(...)`?** Returning a `Result` directly out of the callback leaves it inaccessible once the transaction closes. For very large result sets, avoid loading all rows into a `List` in the Java heap; design pagination or bounded processing suited to your API.

### 4.2. Two Read Statements in the Same Transaction

If you need to confirm the customer exists and then read orders:

~~~java
return session.executeRead(tx -> {
    var customer = tx.run("""
            MATCH (c:Customer {customerId: $customerId})
            RETURN c.customerId AS id
            """, Map.of("customerId", customerId)).single();

    var orders = tx.run("""
            MATCH (:Customer {customerId: $customerId})
                  -[:PLACED]->(o:Order)
            RETURN o.orderId AS id
            ORDER BY id
            """, Map.of("customerId", customerId))
            .list(row -> row.get("id").asString());

    return Map.of(
            "customerId", customer.get("id").asString(),
            "orderIds", orders);
});
~~~

Both statements belong to the **same transaction**, yet **read committed** (Neo4j's default isolation level) **does not guarantee a fixed snapshot** across reads. Another transaction can commit new data between the two queries. If business logic requires stricter multi-object consistency, evaluate concurrency rules and locking/versioning strategies accordingly.

## 5. Writing Data with executeWrite

### 5.1. Creating Constraints for Business Keys

To prevent two nodes with the same identifier from committing, add a **uniqueness constraint** before concurrent writes occur:

~~~cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;

CREATE CONSTRAINT order_id_unique IF NOT EXISTS
FOR (o:Order)
REQUIRE o.orderId IS UNIQUE;
~~~

The constraint on `Order.orderId` helps identify the same order during retries. Even so, it **does not automatically enforce all business invariants** such as order ownership or total amount.

### 5.2. Example: Multiple Write Statements in One Callback

Goal: create an `Order` with a stable ID, validate data if the ID already exists, and link the node to `Customer`. If the customer does not exist, the entire transaction must roll back.

~~~java
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class OrderCommands {
    public static String placeOrder(
            Driver driver, String customerId,
            String orderId, long totalCents) {
        if (customerId == null || customerId.isBlank()
                || orderId == null || orderId.isBlank()
                || totalCents < 0) {
            throw new IllegalArgumentException("Invalid order input");
        }

        Map<String, Object> params = Map.of(
                "customerId", customerId,
                "orderId", orderId,
                "totalCents", totalCents);

        try (Session session =
                driver.session(SessionConfig.forDatabase("neo4j"))) {
            return session.executeWrite(tx -> {
                // Statement 1: identify or create a unique Order.
                var order = tx.run("""
                    MERGE (o:Order {orderId: $orderId})
                    ON CREATE SET
                        o.customerId = $customerId,
                        o.totalCents = $totalCents,
                        o.status = 'CREATED',
                        o.createdAt = datetime()
                    RETURN o.customerId AS ownerId,
                           o.totalCents AS storedTotal
                    """, params).single();

                // Same ID with different data must be a business error.
                if (!customerId.equals(
                        order.get("ownerId").asString())
                        || totalCents !=
                        order.get("storedTotal").asLong()) {
                    throw new IllegalStateException(
                            "Order ID reused with different data");
                }

                // Statement 2: require Customer to exist, create relationship.
                return tx.run("""
                    MATCH (c:Customer {customerId: $customerId})
                    MATCH (o:Order {orderId: $orderId})
                    MERGE (c)-[:PLACED]->(o)
                    RETURN o.orderId AS id
                    """, params).single().get("id").asString();
            });
        }
    }
}
~~~

Result behavior explained:

- If `Customer` exists and `Order` does not: creates the node + relationship in the **same transaction**, then commits.
- If the same request is retried after committing: `MERGE` finds the existing order, validates owner/total, and matches the relationship. This achieves **idempotency by business ID**.
- If `Customer` does not exist: the second statement returns 0 rows, `single()` throws an exception, and the driver rolls back the newly created `Order` node in that transaction.
- If `orderId` already exists with different data: the callback throws an exception; no new changes commit.
- If the database reports a constraint conflict or technical error: the managed transaction handles rollback/retry depending on error category; the application still classifies the resulting exception.

**Concurrent write limitation:** `MERGE` on a relationship between two nodes is not a database-level **uniqueness constraint** on the endpoint pair. If multiple transactions race and business rules strictly require at most one relationship, add protection via a stable relationship identifier/constraint, locking, or serialization on the business key. Specifically, **do not assume `MERGE` always prevents duplicate edges under all race conditions**.

### 5.3. Why Does the Example Use Two Statements?

We intentionally separated upserting the node and creating the relationship into **two `tx.run` calls** to demonstrate callback atomicity. If two independent `session.run` calls were used, the node creation could commit before the relationship creation fails. With `executeWrite`, the driver only commits everything when the callback succeeds.

A transaction **does not replace validation**: validate identifiers, order data, user permissions, limits, and business invariants before or inside the transaction as needed.

## 6. Commit, Rollback, and Exceptions: Understanding Precisely

| Scenario | Neo4j/Driver handling | Application responsibility |
| --- | --- | --- |
| Callback returns normally and commit succeeds | Transaction commits; value returned to caller | Safe to return success response |
| Callback throws a business error | Uncommitted transaction rolls back | Map error to appropriate response |
| Cypher syntax error or invalid data | Transaction fails; typically not auto-retried | Fix query or reject input |
| Uniqueness constraint violation | Write rejected; transaction does not commit | Check duplicate IDs, business conflicts |
| Deadlock or transient error recognized by driver | Driver may retry **the entire callback** | Callback must be safe to re-execute |
| Connection drops near commit time | Client may not know commit outcome | Re-read by business ID, avoid duplicate creation |

**Never assume:** "The callback passed the last statement = commit definitely succeeded." A transaction can still fail during commit, so act on success only after `executeWrite` itself completes.

When an exception leaves the callback, **do not catch it and return a normal value just to let the driver commit**, unless the application intentionally accepts the preceding successful operations. If business logic requires full rollback, **let the exception propagate out of the callback**.

### Example Condition Causing Transaction Rollback

~~~java
session.executeWrite(tx -> {
    tx.run("""
        CREATE (a:AuditMarker {markerId: $id})
        """, Map.of("id", "MARK-001")).consume();

    // When an invalid business condition is detected:
    throw new IllegalStateException("Business validation failed");
});
~~~

After the exception, the `AuditMarker` created in this transaction **is not committed**. If a node with the same ID already existed from an earlier committed transaction, rolling back the new transaction **does not** delete that pre-existing data.

## 7. Automatic Retry: Benefits and the Biggest Pitfall

In real systems, transactions can encounter deadlocks, brief server restarts, or transient faults. Managed transactions allow the driver to **re-run the callback** for errors it identifies as retryable within the configured policy/time limit.

~~~mermaid
sequenceDiagram
    participant App as Java application
    participant Driver as Neo4j Java Driver
    participant DB as Neo4j
    App->>Driver: executeWrite(callback)
    Driver->>DB: Start transaction #1
    DB-->>Driver: Retryable transient error
    Driver->>DB: Start transaction #2
    Driver->>DB: Re-invoke entire callback
    DB-->>Driver: COMMIT succeeded
    Driver-->>App: Return result
~~~

### 7.1. The Callback Can Be Re-Invoked

Common mistake:

~~~java
session.executeWrite(tx -> {
    String orderId = java.util.UUID.randomUUID().toString();
    tx.run(
        "CREATE (o:Order {orderId: $id})",
        Map.of("id", orderId)
    ).consume();
    paymentGateway.charge(orderId); // Side effect outside Neo4j!
    return orderId;
});
~~~

When the callback re-runs, `orderId` may **change**, while the payment gateway charge **cannot roll back with Neo4j**. Calling a payment gateway inside the transaction increases the risk of double charging or state divergence between systems.

A safer design:

1. Receive or generate a **stable `requestId`/`orderId` before entering the callback** so retries reuse it.
2. Inside the callback, only access Neo4j and validate data to be written, backed by proper constraints and upserts.
3. Write an **event/outbox record** with a unique ID **in the same transaction** if post-commit processing is needed.
4. Have an independent worker read the outbox, call external services with an idempotency key, confirm status, and handle its own retries.

For sending emails, publishing to Kafka, or calling external systems after commit, use a reliable mechanism like the **transactional outbox** or business compensation; merely placing external calls **after** `executeWrite` still risks lost delivery if the process crashes between commit and send.

### 7.2. Driver Retries Differ from Request Retries

Two retry layers can occur simultaneously:

- **Driver retry:** a single `executeWrite` call re-runs the callback due to a recognized transient error.
- **Application/HTTP retry:** a client resends **the entire request** after a timeout, possibly after the earlier transaction **already committed**.

Therefore, even a callback with no external side effects needs **business-level idempotency** if clients can resend requests. Constraints and `MERGE` on business IDs help, but you must validate payload consistency on duplicate IDs rather than blindly treating every duplicate request as valid.

### 7.3. Retry Duration

The driver has a configurable retry timeout (e.g., via the driver's transaction retry configuration). This limit should align with **HTTP timeouts**, external call budgets, and SLO requirements. Increasing retries indefinitely will not fix broken schemas, bad queries, or prolonged outages.

Log error codes and retry counts using metrics/observability hooks available from the driver/stack, avoiding placing customer IDs or sensitive parameters directly into metric labels. When an error is not retried by the driver, let it surface to the application and perform deliberate backoff or re-reads.

## 8. executeRead and executeWrite: Choosing by Intent

| Need | Recommended API | Notes |
| --- | --- | --- |
| Read node by `customerId` | `executeRead` | Can be routed to a read member |
| Traverse relationships or read-only path queries | `executeRead` | Use indexes/depth bounds to control cost |
| `CREATE`, `MERGE`, `SET`, `DELETE` | `executeWrite` | Uses a write transaction |
| Run multiple dependent write statements | `executeWrite` | Wraps all invariants needing atomic commit |
| Read, verify, then write | `executeWrite` | Read and write inside the same write transaction; account for concurrency |
| Export large datasets in separate batches | Design multiple controlled transactions | Do not assume all batches form one atomic transaction |

**`executeRead` is not for writing.** It declares a READ context and lets the driver pick suitable routing; issuing write statements in a read transaction can be rejected by the server. **`executeWrite`** can perform both reads and writes.

### Routing in a Cluster

When connecting via a `neo4j://` routing URI, the driver uses its routing table to send READ/WRITE transactions to appropriate cluster members. However:

- `executeRead` **does not strictly mean** it must execute on a specific follower.
- Sessions/transactions **must not be arbitrarily shared across threads** concurrently.
- After a write, a subsequent read in a new session needs **causal consistency** if business logic expects to see the just-committed data. Neo4j Java Driver supports **bookmarks** and `BookmarkManager` to chain dependent transactions.
- **Bookmarks** enforce causal ordering; they do not upgrade read committed isolation to global snapshot isolation/serializability.

In simple applications using an appropriate session, the driver tracks bookmarks within the session; across sessions/instances, design bookmark sharing or `BookmarkManager` usage according to your API and version.

## 9. Result Handling, Timeouts, and Resources

### 9.1. Consume Results Inside the Callback

Lifecycle bug:

~~~java
var result = session.executeRead(tx ->
        tx.run("MATCH (c:Customer) RETURN c"));

// Result may have lost its source transaction here.
~~~

Correct for small results:

~~~java
var customerIds = session.executeRead(tx ->
        tx.run("""
            MATCH (c:Customer)
            WHERE c.customerId IS NOT NULL
            RETURN c.customerId AS id
            LIMIT 100
            """).list(row -> row.get("id").asString()));
~~~

For write queries that do not need to return a list, call `consume()` inside the callback to finish processing the result:

~~~java
session.executeWrite(tx -> {
    tx.run("""
        MATCH (c:Customer {customerId: $id})
        SET c.lastSeenByJob = $jobName
        """, Map.of("id", "C-101", "jobName", "sync-01"))
      .consume();
    return null;
});
~~~

**Note:** `consume()` finishes consuming the query's result stream; it **does not commit the transaction**. The driver still commits only after the callback completes cleanly.

### 9.2. Large Results and Memory

`.list(...)` is convenient, but loads the entire result into the Java heap. For large results:

- Filter with `WHERE` and apply `LIMIT`/pagination using a stable key.
- Return only the required properties rather than full nodes/relationships when IDs suffice.
- Process rows while the transaction is open, yet **do not hold transactions open** waiting on network calls, message brokers, or external work.
- For batch writes, use `UNWIND $rows AS row ...` split into bounded transactions; give each batch its own retry/deduplication strategy.

Long-running transactions hold resources/locks and increase contention with other workloads. Size row counts, durations, and timeouts based on realistic data and load, not small sample fixtures.

### 9.3. Transaction Timeouts and Metadata

Neo4j Java Driver supports configuring **transaction timeouts** and metadata for observability, depending on the API version:

~~~java
import java.time.Duration;
import java.util.Map;
import org.neo4j.driver.TransactionConfig;

var config = TransactionConfig.builder()
        .withTimeout(Duration.ofSeconds(5))
        .withMetadata(Map.of("operation", "read-customer-orders"))
        .build();

var orders = session.executeRead(tx ->
        tx.run("""
            MATCH (c:Customer {customerId: $customerId})
                  -[:PLACED]->(o:Order)
            RETURN o.orderId AS id
            LIMIT 20
            """, Map.of("customerId", customerId))
          .list(row -> row.get("id").asString()), config);
~~~

This snippet assumes `session` and `customerId` are already declared. **Transaction timeouts**, connection acquisition timeouts, network timeouts, and HTTP endpoint timeouts are distinct layers; align them so the server does not keep executing long after the HTTP request has timed out. Metadata should hold stable business labels, never secrets or unnecessary personal data.

## 10. Managed, Explicit, and Implicit Transactions in One Scenario

Suppose business logic updates a customer's tier and records an audit entry:

~~~cypher
MATCH (c:Customer {customerId: $customerId})
SET c.tier = $tier
CREATE (a:TierAudit {auditId: $auditId, tier: $tier})
CREATE (c)-[:HAS_TIER_AUDIT]->(a)
RETURN c.customerId AS id;
~~~

A single statement like this is already atomic within **its own** transaction. However, when business logic grows more complex and needs multiple `tx.run` calls with Java-side decisions, your choice matters.

| Transaction style | Advantages | Limitations / cautions |
| --- | --- | --- |
| **Implicit `session.run`** | Concise for one standalone Cypher query | Separate `session.run` calls do not share a commit; completion depends on consuming the result |
| **Managed `executeWrite`** | Clear boundaries, orchestrates commit/rollback and retries | Callback may re-run; be careful with side effects and result lifecycle |
| **Explicit `beginTransaction`** | Full manual control over `commit` and `rollback` | Must manage errors, resources, and retries manually; easy to forget rollback/close |

Explicit example for comparison:

~~~java
try (Session session = driver.session();
     var tx = session.beginTransaction()) {
    tx.run("""
        MATCH (c:Customer {customerId: $id})
        SET c.tier = $tier
        """, Map.of("id", "C-101", "tier", "GOLD"))
      .consume();

    // Application checks other conditions.
    tx.commit();
}
~~~

When an explicit transaction is closed without committing, uncommitted writes are rolled back. Explicit transactions do not automatically provide the callback retry mechanism of `executeWrite`. Unless business logic requires custom orchestration, managed transactions are usually the preferred choice.

## 11. Relationship with Spring Data Neo4j

In Spring Data Neo4j applications, the service layer typically uses **`@Transactional`** paired with a properly configured `Neo4jTransactionManager` to wrap repository operations:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerService {
    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public CustomerView findCustomer(String id) {
        var customer = repository.findById(id).orElseThrow();
        return new CustomerView(customer.getCustomerId(),
                                customer.getDisplayName());
    }
}
~~~

The snippet above is an **illustrative skeleton**: `CustomerRepository`, `CustomerView`, and the entity must be defined in your project. `@Transactional` only applies when calls pass through Spring's transaction proxy; self-invocation within the same bean may bypass the proxy unexpectedly.

**Do not conflate them:**

- `@Transactional` is **Spring's application-layer transaction management**.
- `executeRead` / `executeWrite` is the **Java Driver's managed transaction mechanism**.

Within the same flow, avoid creating independent Sessions/managed transactions in the middle of a sequence of repository calls expected to share **a single Spring transaction**. Keep your transaction manager and data access entry points consistent. If you must invoke GDS, CDC, or specialized Cypher procedures directly, verify how `Neo4jClient`/Driver participates in the active transaction boundary.

## 12. Testing Behavior Instead of Just Syntax

Prepare a test database with `Customer` nodes and the constraints from Section 5. The tests below can run as integration tests against a real Neo4j instance or a compatible Neo4j Testcontainers environment.

| Scenario | Expected outcome |
| --- | --- |
| `executeRead` reads an existing customer | Returns accurate data; creates/modifies no nodes |
| `executeRead` callback has 2 queries | Both run in one read transaction; results materialized before callback returns |
| `executeWrite` creates Order + relationship | Both appear after commit |
| Failure after creating Order, before creating relationship | No uncommitted Order remains after the failed transaction |
| Customer missing, `single()` fails | Transaction rolls back; no orphan Order left behind |
| Same `orderId` resent with identical data | No duplicate Order created for that key; check relationship is not duplicated |
| Same `orderId` with different total | Application detects conflict and rejects |
| Constraint violation under concurrent writes | Database rejects duplicate node; application handles error properly |
| Driver callback retried due to retryable transient error | All IDs stay stable; no external side effects outside the database |
| HTTP timeout after a possible commit | Re-check by business ID before creating another request |
| Session accessed from multiple threads | Refactor to **one Session per thread/request** |
| Very large result set | Measure memory; paginate/limit instead of unbounded `list` |

### Minimal Atomicity Test

In a practice environment, create a customer or run an operation that intentionally throws an exception:

~~~java
try (Session session =
        driver.session(SessionConfig.forDatabase("neo4j"))) {
    try {
        session.executeWrite(tx -> {
            tx.run("""
                CREATE (:Order {orderId: 'ROLLBACK-TEST-01'})
                """).consume();
            throw new IllegalStateException("Force rollback");
        });
    } catch (IllegalStateException expected) {
        // Expected business error to test rollback.
    }

    long count = session.executeRead(tx ->
            tx.run("""
                MATCH (o:Order {orderId: 'ROLLBACK-TEST-01'})
                RETURN count(o) AS n
                """).single().get("n").asLong());

    if (count != 0) {
        throw new AssertionError("Rollback did not work");
    }
}
~~~

Run tests only against an isolated database. Data with the same `orderId` from a **previously committed transaction** will not be rolled back by the current attempt, so choose a fresh test ID or ensure test isolation.

### Observing Latency and Errors

In operations, monitor:

- p50/p95/p99 latency of the **entire** `executeRead` / `executeWrite` call.
- Error and timeout rates; connection acquisition time, network latency, and full result consumption time.
- Count of failed/transient/deadlock transactions and retry counts where supported by telemetry.
- Active transaction count, lock hold times, rows processed, and Neo4j server resources.

Do not measure only `tx.run`: that call may not have consumed the entire result yet, and a managed transaction only finishes after commit. `EXPLAIN` and `PROFILE` help analyze Cypher plans, but do not replace end-to-end application measurements.

## 13. Self-Practice Exercises

**Exercise 1 — Safe reading:** Write an `executeRead` returning up to 50 customers with `tier = 'GOLD'`. Verify parameter binding, `list(mapper)` usage, and session closure.

**Exercise 2 — Atomic write:** Write an `executeWrite` running two statements: (1) upsert an `Order` node, (2) create `PLACED` to the matching `Customer`. Intentionally throw an exception after the first statement and verify the new Order is not committed.

**Exercise 3 — Retries:** Suppose a callback occasionally runs twice. Explain why `UUID.randomUUID()` and calling a payment gateway inside the callback are dangerous. Fix the design using a stable `requestId` and an outbox event with a unique ID.

**Exercise 4 — Read-your-writes:** One thread writes successfully, and another thread reads from a cluster immediately after without seeing the update. Explore bookmarks/causal consistency instead of adding arbitrary `Thread.sleep(...)` calls.

**Exercise 5 — Large datasets:** A query returns millions of nodes. Evaluate why `.list()` can put pressure on the Java heap and propose strategies using limits, pagination, or batched processing.

### Quick Check Questions

**1. Can you call `tx.commit()` inside `executeWrite`?** No. The Driver manages commit/rollback; the callback only executes work on `tx` and returns a result.

**2. Does `executeRead` guarantee a fixed snapshot across all reads by default?** No. Neo4j's read committed isolation is not general snapshot isolation/serializable.

**3. If a callback succeeds but the commit fails, may the application return HTTP 200?** No; you must handle the outcome/exception of `executeWrite`, rather than treating reaching the end of the callback as proof of commit.

**4. Does the Driver retry every exception?** No. Only errors recognized as retryable according to its policy and configured timeout.

**5. Should one Session be shared across multiple concurrent requests?** No. Share the Driver, and create a separate Session per unit of work.

**6. Do `MERGE` and uniqueness constraints eliminate the need to handle retried requests?** No. You still need stable request keys and business payload conflict checks; relationships and external systems also have separate requirements.

## 14. Adoption Checklist

- [ ] Choose `executeRead` for read-only work and `executeWrite` for writes or read-then-write operations.
- [ ] Use a **shared Driver**, **per-request Sessions**, and explicitly specify the database.
- [ ] Place all Cypher statements belonging to one business operation inside **one callback** when atomic commit/rollback is required.
- [ ] Read/`consume()` results inside the callback; never return a Result still tied to the transaction.
- [ ] Use **Cypher parameters**, stable business IDs, uniqueness constraints, and input validation.
- [ ] Remember callbacks can re-run: never send emails, charge payments, or generate changing IDs inside them.
- [ ] Distinguish technical Driver retries from **full HTTP/request retries** and enforce idempotency.
- [ ] Never catch errors and return "success" if business logic requires rollback.
- [ ] Configure pool/timeouts, routing, and bookmarks according to topology and consistency requirements.
- [ ] With Spring Data Neo4j, let Spring's transaction manager coordinate related repository calls.
- [ ] Test rollbacks, constraints, write contention, timeouts, and large reads on an isolated database.

## References

- [Neo4j Java Driver Manual — Transactions](https://neo4j.com/docs/java-manual/current/transactions/)
- [Neo4j Java Driver Manual — Query the database](https://neo4j.com/docs/java-manual/current/query-simple/)
- [Neo4j Java Driver Manual](https://neo4j.com/docs/java-manual/current/)
- [Neo4j Cypher Manual — Transactions](https://neo4j.com/docs/cypher-manual/current/transactions/)
- [Neo4j Java Driver API](https://neo4j.com/docs/api/java-driver/current/)

**Conclusion:** `executeRead` and `executeWrite` are the core mechanism when Java needs Neo4j to manage read/write transactions. They give a Cypher callback **clear commit/rollback boundaries, proper routing, and transient error retries**. For truly correct business behavior, the application still needs proper Driver/Session lifecycles, timely result consumption, stable identifiers, concurrency control, and no external database-outside side effects inside retryable callbacks.
