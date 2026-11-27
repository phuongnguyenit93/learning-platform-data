# Atomicity, Consistency, Isolation, and Durability in Neo4j

## Learning Objectives

After this lesson, you will be able to:

- Explain the four **ACID** properties of a transaction when operating on a **property graph** in Neo4j.
- Identify transaction boundaries for a single Cypher statement, multiple statements, and transaction APIs in the Java Driver or Spring Data Neo4j.
- Analyze rollbacks, constraint enforcement, concurrent reads/writes, mid-execution failures, and durability after commit.
- Distinguish **ACID**, **idempotency**, and **causal consistency** when an application retries or runs on a cluster.
- Design and verify a business operation that safely updates multiple nodes and relationships.

The **Transactions** chapter of the **DATABASE_ENGINE_GRAPH_NEO4J** module places node creation, relationship linking, and property updates inside a single reliable boundary. Neo4j uses the property graph model and Cypher to represent and query relationships and paths, yet correct results from a graph query depend on more than syntax. When a business operation modifies **multiple related elements**, you must ensure those changes are accepted or discarded together.

## 1. What Is a Transaction and When Do You Need One?

A **transaction** is a unit of work executed and managed by the database as a consistent set of operations. A transaction may contain just one Cypher statement or multiple Cypher statements.

For example, an order placement workflow needs to:

1. Locate the `Customer` node.
2. Create the `Order` node.
3. Create the `PLACED` relationship from the customer to the order.
4. Update the order status.

If step 3 or 4 fails after the order has already been created, you should not leave an orphan order or an order in a half-completed state. Placing these steps inside the **same transaction** ensures all write operations succeed together or are rolled back.

~~~mermaid
flowchart TD
    A["Start transaction"] --> B["Create/update node"]
    B --> C["Create/update relationship"]
    C --> D{"All operations valid?"}
    D -->|Yes| E["COMMIT: publish all changes"]
    D -->|No| F["ROLLBACK: discard uncommitted changes"]
~~~

In Neo4j, **even a single regular Cypher statement runs inside a transaction**. When you want multiple statements to succeed or fail together, the application must place them within the **same transaction boundary**. If you send each statement separately using an *implicit/auto-commit* transaction and the first statement has already committed, an error in a subsequent statement cannot automatically undo the first one.

> **Note:** This lesson explains concepts and usage on modern Neo4j (specifically the Neo4j 5.x series). Depending on the version, APIs, batch import syntax, and query planner behavior may vary; in production, always verify against your actual database and driver versions.

## 2. ACID from a Property Graph Perspective

ACID stands for **Atomicity**, **Consistency**, **Isolation**, and **Durability**.

| Property | Practical meaning in Neo4j | What can happen if missing? |
| --- | --- | --- |
| **A — Atomicity** | Changes within a transaction are committed or rolled back as a single unit | An order node exists without its required relationship |
| **C — Consistency** | A transaction must obey rules enforced by the database, such as constraints; business rules must be further protected by the application | Two customers share the same code even though it must be unique; incorrect order total due to business logic bugs |
| **I — Isolation** | Concurrent transactions cannot see each other's **uncommitted** data; the default level is *read committed* | Reading incomplete data, or mistakenly assuming two reads will always return the same result |
| **D — Durability** | Committed transactions are persisted durably with recovery mechanisms upon database restart | A state reported as successful disappears after a process crash |

The four properties work together, yet each addresses **different risks**. ACID does not mean Neo4j automatically understands every business rule, nor that all concurrent transactions behave identically to serial execution.

## 3. Atomicity — All or Nothing

### 3.1. A Single Cypher Statement Updating Multiple Elements

Suppose the database already has customer `C-101`. Create a uniqueness constraint on the order ID to prevent two orders from sharing an identifier:

~~~cypher
CREATE CONSTRAINT order_id_unique IF NOT EXISTS
FOR (o:Order)
REQUIRE o.orderId IS UNIQUE;
~~~

Then execute the operation to create the node and relationship:

~~~cypher
MATCH (c:Customer {customerId: $customerId})
CREATE (o:Order {
  orderId: $orderId,
  status: 'CREATED',
  total: $total
})
CREATE (c)-[:PLACED]->(o)
RETURN o.orderId AS orderId;
~~~

In a regular Cypher statement, creating `Order` and the `PLACED` edge belong to the **same statement transaction**. If an error causes the transaction to fail, none of that statement's changes are partially committed.

However, a `MATCH` that finds no customer returns **0 rows** and does not automatically raise an error. In this case, the statement creates nothing; the application must check the returned row count and raise a business error if the customer is required to exist.

### 3.2. Multiple Cypher Statements Must Share a Transaction

If the application splits order creation and status update into **two statements**, the boundary must enclose both:

~~~text
BEGIN TRANSACTION
  1. MATCH Customer; CREATE Order; CREATE relationship PLACED
  2. MATCH Order; SET auditState = 'PENDING'
  If an error occurs -> ROLLBACK both step 1 and step 2
  If all succeed -> COMMIT
~~~

The snippet above is **pseudocode illustrating the boundary**; `BEGIN TRANSACTION` is not a plain Cypher command to paste into every client. The concrete mechanism to open/commit/rollback is provided by the Java Driver, Spring Transaction Manager, or whichever client you use.

Once a transaction has committed, you cannot call rollback to undo the old transaction. To reverse a business operation, you need an appropriate **compensating transaction**.

### 3.3. Distinguishing Rollback from Creating No Data

Different scenarios produce different outcomes:

| Scenario | Outcome |
| --- | --- |
| First statement creates a node, second statement errors in the **same transaction** | The transaction fails and rolls back uncommitted writes |
| First statement **committed separately**, second statement errors | Data from the first statement remains persisted |
| `MATCH` returns no rows, no error occurs | The statement may complete normally without writing anything |
| A constraint error occurs, application catches it and still tries to commit | You must not assume a failed transaction can continue; roll back and open a new transaction |
| Driver retries after a transient error | The transaction callback may execute again; avoid external side effects |

**Important exception for batch data ingestion:** Cypher provides the `CALL { ... } IN TRANSACTIONS` syntax to split work into multiple smaller transactions. Earlier batches that have already committed may remain if a later batch fails. Therefore, do not treat a multi-batch import operation as a single atomic transaction.

## 4. Consistency — Protecting Graph Invariants

Consistency means the database maintains **verifiable rules** on data before and after a committed transaction. In Neo4j, part of these rules is expressed via **schema constraints**.

### 4.1. Constraints Are the Database-Level Line of Defense

~~~cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;

CREATE CONSTRAINT order_id_unique IF NOT EXISTS
FOR (o:Order)
REQUIRE o.orderId IS UNIQUE;
~~~

With a uniqueness constraint on `Order.orderId`, two `Order` nodes cannot both be committed with the same `orderId` value. A write transaction that violates the constraint will fail; that transaction's uncommitted changes are rolled back.

**Limitation to remember:** a uniqueness constraint on a property does not automatically require every node with that label to have the property. If an ID is mandatory, validate inputs, use a constraint type supported by your deployed edition/version, or organize an appropriate validation layer.

### 4.2. Constraints Do Not Replace Business Logic

Suppose a store has the rule "an order's total must equal the sum of its line items." Neo4j does not automatically infer this formula from the graph:

~~~text
Order.total == SUM(OrderLine.quantity * OrderLine.unitPrice)
~~~

The application must compute/validate this in business logic and ensure the related nodes, relationships, and properties are written within the **same transaction**. For concurrent updates, you must also apply an appropriate isolation/synchronization strategy so concurrent transactions do not read stale state and make conflicting decisions.

Similarly, a constraint on `Order.orderId` does not prevent the same order from appearing twice in external systems if the caller generates a new ID on every retry. **ACID, constraints, and idempotency** are three related concepts, not the same thing.

## 5. Isolation — What Happens When Multiple Transactions Run Concurrently?

Neo4j uses **read committed** as its default isolation level. This means:

- Other transactions **cannot see uncommitted changes**.
- A transaction normally **sees writes it made itself** in subsequent queries within the same transaction.
- Two reads of the same data within the same transaction **are not guaranteed to return the same result** if another transaction commits a change in between. This is known as a *non-repeatable read*.
- Conditional queries may also see changing result sets when another transaction creates or deletes matching elements, depending on read timing; do not assume *snapshot isolation* across all reads.

### 5.1. Example of Reads Changing Mid-Transaction

~~~text
Time         Transaction A                      Transaction B
T1           Read Customer C-101: status=NEW
T2                                              Update status=ACTIVE; COMMIT
T3           Re-read C-101: may see ACTIVE
T4           COMMIT
~~~

Transaction A does not see B's **uncommitted** state, but it can see B's **committed** state on a subsequent read. This does not violate read committed isolation.

### 5.2. Write Locks, Contention, and Lost Updates

Neo4j uses locking and conflict management to protect write integrity. Two transactions modifying the same node or relationship may have to wait for each other; one transaction may be aborted due to a deadlock or transient transaction error.

However, a rule such as "only deduct funds if the balance is sufficient" is not protected merely by placing a `WHERE` clause before a `SET` and assuming zero contention. Dangerous example:

~~~text
Transaction A reads balance = 100
Transaction B reads balance = 100
Transaction A computes new balance = 20
Transaction B computes new balance = 30
Both writes attempt to update based on the stale value
~~~

If the application **computes the new value outside the transaction, or reads first and writes later without concurrency control**, there is a risk of a *lost update* or breaking the balance invariant.

Some Cypher operations that directly update properties on the node itself are protected by appropriate write locks in Neo4j, but you should not generalize that to mean every multi-node or multi-step rule is automatically safe. For high-contention workflows, consider:

1. **Placing all related reads, checks, and writes inside a single transaction**; avoid making decisions based on values read in an earlier transaction.
2. **Locking the entities that need protection before checking conditions**, using mechanisms and APIs compatible with your Neo4j version; standardize lock acquisition order to reduce deadlocks.
3. **Optimistic locking** using a version field or `@Version` in Spring Data Neo4j; detect conflicts and retry the entire business operation with a bounded limit.
4. **Constraints** to protect identity, while testing two or more concurrent write transactions.

If a deadlock or transient error occurs, a transaction may roll back and be retried according to application policy. Retries should be bounded, use appropriate backoff, and avoid repeating actions outside the database.

## 6. Durability — How Does Data Persist After COMMIT?

When Neo4j confirms that a transaction has committed successfully, the changes become **accepted state**. Neo4j uses storage mechanisms, transaction logs, and crash recovery to preserve committed changes across process restarts.

Distinguish the following stages:

~~~mermaid
sequenceDiagram
    participant App as Application
    participant DB as Neo4j
    App->>DB: Send write operations in transaction
    DB-->>App: Execute; data uncommitted
    App->>DB: Request COMMIT
    DB-->>App: Confirm commit succeeded
    Note over DB: Changes are committed data
~~~

- **Before commit:** Even if statements have executed inside the transaction, an error or rollback can still discard the writes.
- **After successful commit:** Neo4j is responsible for durability according to its storage engine and deployment configuration.
- **Connection drop right at commit time:** The client may not know whether the transaction committed or not. Never assume "timeout means rollback"; query to verify, use a **stable business ID**, or implement deduplication.
- **Catastrophic loss of the entire storage device:** Durability does not replace backups, restore testing, or redundancy architecture.

In a **cluster**, reading from another member may require a **bookmark** to ensure causally dependent transactions are observed in the right order. Bookmarks provide **causal consistency** across sessions/transactions; they do not upgrade read committed isolation to serializable and are not a substitute for transactions.

## 7. Transaction Boundaries in Cypher and the Java Driver

### 7.1. Common Execution Patterns

| Execution pattern | Boundary | When to use |
| --- | --- | --- |
| A single regular Cypher statement | One transaction per statement | Simple queries/writes with no follow-up step that must commit together |
| Multiple independent `session.run(...)` calls | Each implicit call has its own transaction | Operations that do not need to be atomic together |
| `session.beginTransaction()` | Explicit transaction; application calls `commit()` | Fine-grained control over when commit/rollback happens |
| `session.executeWrite(...)` / `executeRead(...)` | Managed transaction handled by the driver | Most application read/write flows, with built-in retry support for eligible errors |
| `@Transactional` in Spring | Transaction per method invocation via Spring proxy and transaction manager | Spring Data Neo4j services coordinating multiple queries/repositories |

Note: With implicit transactions, you must **consume** the result or close the session properly before considering the operation finished. Do not leave a result stream unread and assume the commit has happened.

### 7.2. Java Driver: Two Statements in One Managed Transaction

Here is an example using the **Neo4j Java Driver**, assuming `Customer` already exists and the database has a uniqueness constraint on `Order.orderId`:

~~~java
import java.util.Map;
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public class OrderTransactionExample {
    static String placeOrder(
            Driver driver, String customerId, String orderId, long total) {
        try (Session session =
                     driver.session(SessionConfig.forDatabase("neo4j"))) {

            return session.executeWrite(tx -> {
                var params = Map.of(
                        "customerId", customerId,
                        "orderId", orderId,
                        "total", total);

                String createdId = tx.run("""
                        MATCH (c:Customer {customerId: $customerId})
                        CREATE (o:Order {
                            orderId: $orderId,
                            total: $total,
                            status: 'CREATED'
                        })
                        CREATE (c)-[:PLACED]->(o)
                        RETURN o.orderId AS id
                        """, params).single().get("id").asString();

                tx.run("""
                        MATCH (o:Order {orderId: $orderId})
                        SET o.auditState = 'PENDING'
                        """, params).consume();

                return createdId;
            });
        }
    }

    public static void main(String[] args) {
        // Actual URI and credentials should be retrieved from secure configuration.
        try (Driver driver = GraphDatabase.driver(
                "bolt://localhost:7687",
                AuthTokens.basic("neo4j", "password-from-config"))) {
            System.out.println(
                    placeOrder(driver, "C-101", "O-901", 150000L));
        }
    }
}
~~~

Both `tx.run` calls reside inside the same `executeWrite` callback, meaning the **same transaction**. If the second step errors, both creating `Order` and creating the `PLACED` relationship from the first step are rolled back. If `MATCH` finds no customer, `single()` finds no row and throws an exception inside the callback; the application can catch and map it to a business error outside the transaction.

`executeWrite` may **re-execute the callback** on transient errors that the driver considers retryable. Therefore:

- Do not send emails, call external payment gateways, publish Kafka messages, or generate a new ID on each retry **inside the callback**.
- Generate a stable `orderId` before entering the transaction; if the request can be resent after a successful commit, add an **idempotent upsert/deduplication design**. A constraint prevents duplicate IDs, yet may cause the resent request to receive a duplicate error rather than returning success.
- Do not assume the driver retries every error; constraint violations and normal business errors typically require the application to decide how to handle them.

### 7.3. Java Driver: Explicit Transactions

When you need explicit control over when to commit, use `beginTransaction()`:

~~~java
try (Session session = driver.session();
     var tx = session.beginTransaction()) {

    tx.run("""
        MATCH (c:Customer {customerId: $customerId})
        SET c.lastOrderId = $orderId
        """, Map.of(
            "customerId", "C-101",
            "orderId", "O-901")).consume();

    // Additional conditions can be checked and other statements run here.
    tx.commit();
}
~~~

If an exception occurs before `commit()` or the transaction is closed without committing, uncommitted changes are rolled back. Unlike managed transactions, the application must manage retries itself when using explicit transactions.

### 7.4. Spring Data Neo4j and `@Transactional`

In a Spring Data Neo4j application using synchronous APIs, you can place the boundary on a **service method**:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {
    private final OrderRepository orderRepository;
    private final CustomerRepository customerRepository;

    public OrderService(OrderRepository orderRepository,
                        CustomerRepository customerRepository) {
        this.orderRepository = orderRepository;
        this.customerRepository = customerRepository;
    }

    @Transactional
    public void changeOrderOwner(String orderId, String customerId) {
        var order = orderRepository.findById(orderId).orElseThrow();
        var customer = customerRepository.findById(customerId).orElseThrow();

        // Illustration: the Order entity must declare the owner relationship mapping.
        order.setOwner(customer);
        orderRepository.save(order);
    }
}
~~~

This example is an **illustrative service skeleton**: `OrderRepository`, `CustomerRepository`, and the entity with `setOwner` must be declared according to your project's domain model. In a real deployment, `@Transactional` works when the call passes through Spring's transaction management mechanism and is configured with the appropriate **Neo4j transaction manager**; calling a method internally within the same bean may bypass the transaction proxy. Combining Neo4j with another database, HTTP calls, or a message broker **does not automatically create** a distributed ACID transaction.

## 8. ACID vs. Idempotency and Causal Consistency

Three concepts frequently appear together in distributed systems:

| Concept | Question addressed | Example |
| --- | --- | --- |
| **ACID transaction** | Does a set of changes commit/roll back properly and stay isolated at the promised level? | Creating `Order` and `PLACED` succeed together |
| **Idempotency** | Does reprocessing the same request cause unintended extra effects? | Receiving `orderId=O-901` again still results in only one order |
| **Causal consistency** | Does a later operation observe writes confirmed by an earlier operation in a dependency chain? | Reading a newly created order from another session in a cluster using a bookmark |

**Example:** A transaction can be completely ACID when creating order `O-901`. Yet if the client loses its connection right after the server commits and resends the request with a new `orderId`, the system can still create **two business orders** in two separate ACID transactions. Preventing this requires stable identifiers, constraints, or an appropriate deduplication mechanism.

Conversely, calling `MERGE` repeatedly while splitting critical updates into separate transactions can still leave a **half-completed state** if a later step fails. Idempotency is not a substitute for atomicity.

## 9. Common Pitfalls and How to Avoid Them

### Pitfall 1: Running Multiple Separate Statements and Expecting Full Rollback

~~~text
session.run("CREATE ...")       # implicit transaction #1
session.run("CREATE ...")       # implicit transaction #2
~~~

If the first transaction has already committed, an error in the second does not undo the first change. Use `executeWrite` or an explicit transaction when two operations belong to a single business unit.

### Pitfall 2: Treating a Zero-Row Result as a Transaction Error

A `MATCH` with no match can return 0 rows without erroring. Check the result, and if a missing node is a failure condition, throw an exception **inside the same transaction** to roll back related writes.

### Pitfall 3: Performing External Side Effects Inside a Retryable Callback

Sending an email or charging a payment gateway does not roll back with Neo4j. Use a pattern such as a **transactional outbox** (recording an outbox event within the same database transaction and processing it asynchronously with deduplication) or saga/compensation when integrating multiple systems.

### Pitfall 4: Mistaking Read Committed for Serializable

Having no dirty reads does not mean reads stay fixed or that every multi-node business invariant is automatically protected. Design locking/versioning and write concurrency tests where needed.

### Pitfall 5: Treating `CALL { ... } IN TRANSACTIONS` as One Shared Commit

During batch ingestion, each batch has its own transaction, so already-committed batches will not automatically roll back when another batch fails. You need batch identification, checkpoints, deduplication, and rerunnability.

### Pitfall 6: Assuming a Successful Commit Replaces Backups

Transaction logs and crash recovery protect committed changes within the storage system's scope, yet accidental deletions, hardware loss, or operational mistakes still require **backups, restores, and recovery drills**.

## 10. Hands-On Exercise and Verification

**Scenario:** When creating an order, the application must create the `Order` node properly, create the edge from `Customer`, and record the processing state. Run the following scenarios in your practice environment:

1. Prepare a `Customer`, add a uniqueness constraint on `Order.orderId`, and run the `executeWrite` flow from Section 7. Verify both the order and the relationship are created completely.
2. Force the second step to throw an exception **before commit**. Verify the newly created `Order` and `PLACED` edge do not exist after rollback; use a fresh `orderId` for each test run.
3. Resend the same `orderId` after a successful commit. Observe the constraint error or application behavior; discuss why ACID does not mean idempotency.
4. Open two transactions reading the same property, then have another transaction commit an update between the two reads. Observe how read committed allows seeing the updated value.
5. Run a data import split across multiple batch transactions and intentionally trigger an error in a later batch. Verify that data from earlier committed batches can remain.

Query to verify the order and relationship:

~~~cypher
MATCH (c:Customer {customerId: 'C-101'})
OPTIONAL MATCH (c)-[r:PLACED]->(o:Order {orderId: 'O-901'})
RETURN
  c.customerId AS customerId,
  count(r) AS placedRelationships,
  count(o) AS matchedOrders;
~~~

If you need to distinguish an order that **does not exist** from an order that **exists without the edge**, run an additional independent query:

~~~cypher
MATCH (o:Order {orderId: 'O-901'})
RETURN count(o) AS orderCount;
~~~

| Test case | Expected result |
| --- | --- |
| Single transaction writes completely | Node, relationship, and properties appear together |
| Error occurs before commit | No partial changes from the failed transaction |
| Statement violates constraint | Write transaction fails; invalid data is not committed |
| Read uncommitted data from another transaction | Dirty data is not visible |
| Re-read after another transaction commits | New data may be visible under read committed |
| Client times out near commit time | Must verify state before retrying; do not guess rollback |
| Ingestion using multiple batch transactions | Already-committed batches may remain intact when a later batch fails |

## 11. Neo4j Transaction Design Checklist

- Identify the **business unit that must commit together**, including nodes, relationships, and properties.
- Explicitly choose **managed** or **explicit transactions**; do not rely on multiple implicit transactions when atomicity is required.
- Check `MATCH` results, validate inputs, and create appropriate constraints to protect data at the database level.
- Analyze **read committed**, write contention, lost updates, and deadlocks for invariants spanning multiple elements.
- Design **stable IDs and retry handling** for requests that may arrive multiple times; avoid external DB side effects inside retryable callbacks.
- Use **bookmarks** when you need to preserve causal ordering across transactions/sessions in a cluster.
- Distinguish batch transactions from a single atomic transaction; plan for rerunnability when ingesting large datasets.
- Test rollbacks, concurrency, ambiguous commit outcomes, and backup/restore in a staging environment.

**Conclusion:** ACID is the foundation for Neo4j to update a property graph reliably. **Atomicity** protects the commit/rollback boundary; **Consistency** enforces declared constraints; **Isolation** governs how concurrent transactions interact; and **Durability** safeguards data after commit. Correct business outcomes also require designing locking, invariants, retries, and system integrations that align with real transaction boundaries.
