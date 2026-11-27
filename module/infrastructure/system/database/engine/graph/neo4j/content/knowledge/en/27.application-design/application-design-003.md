# Transaction Boundaries by Business Operation

## 1. Start from the Business Operation, Not from the Cypher Statement

Neo4j is a graph database following the **property graph** model: nodes represent entities, relationships represent links, and properties store data for each element. When a Java application uses Neo4j, a single business request often modifies **multiple nodes, relationships, and properties**.

For example, the operation **"place an order containing one product"** may need to:

1. Locate the customer and the product.
2. Create an `Order` node.
3. Create an `OrderLine` node to record quantity and unit price at the time of ordering.
4. Link `Customer-[:PLACED]->Order`.
5. Link `Order-[:HAS_LINE]->OrderLine-[:FOR_PRODUCT]->Product`.
6. Record an event to be published so other systems know a new order was created, if the application has integration requirements.

If only the Order is created while the OrderLine or customer link is missing, the graph can end up in a **business-invalid state**. The transaction boundary must reflect this requirement.

> **Core principle:** A transaction should encompass **the changes within the same Neo4j database that must succeed or fail together** so that a business operation produces a valid state.

Do not equate "one transaction = one Cypher statement," nor assume "one HTTP request = one single transaction." One operation may need multiple statements in the same transaction; conversely, a large workflow spanning multiple business steps and multiple external systems should not try to hold one Neo4j transaction open throughout the entire process.

## 2. Three Concepts to Distinguish

| Concept | Question | Example |
|---|---|---|
| **Business operation** | What is the user/system asking to execute? | Place an order, transfer ownership, remove membership |
| **Business invariant** | What must always remain true after commit? | Every Order has a customer and valid line items |
| **Transaction boundary** | Which changes must Neo4j commit or roll back together? | Creating the Order, OrderLine, and required relationships |

A business operation may involve multiple technical steps; the transaction is chosen based on **which invariants must be preserved**, not the number of statements.

### 2.1. Atomicity Does Not Mean Every Rule Automatically Holds

A transaction guarantees **atomicity**: the transaction's changes are committed as a single unit or none are committed when the transaction rolls back. However, a transaction does not automatically know that quantity must be greater than 0, a customer may join a group only once, or an account balance cannot go negative.

Those rules also require:

- Input validation and normalization.
- Constraints such as uniqueness on business keys.
- Cypher accurately expressing the conditions.
- Concurrency control or version checking when multiple requests modify data simultaneously.
- Concurrency testing and error/retry handling.

**Atomicity** solves "commit together or roll back together"; **concurrency correctness** solves "do two concurrent transactions preserve invariants?" These two goals are related but do not replace each other.

## 3. How to Determine the Boundary for a Use Case

Before writing a repository/service, answer five questions:

1. **What are the business start and end points?** For example, "order placed successfully" means the order exists together with its required line items, not necessarily that the email has already been sent.
2. **Which entities are modified?** Which nodes, relationships, properties? Are there resources outside Neo4j?
3. **If an intermediate step fails, is keeping partial work allowed?** If not, the write steps must be in the same transaction.
4. **Do other requests/workers concurrently mutate the same entities?** If so, business conditions must be protected alongside atomicity.
5. **When the client receives no response, how can we tell whether the request committed?** An idempotency key, tracking state, or an appropriate retry policy is needed.

The analysis should be documented as a **transaction contract**. For example:

| Case | Boundary to Consider | Reason |
|---|---|---|
| Create a single-product Order | Order + OrderLine + required relationships | Avoid incomplete orders |
| Rename a Product | Update that Product only | One node suffices if no other invariants apply |
| Accept a group invitation | Mark invitation and create membership in one transaction | Avoid an "accepted but not yet a member" state |
| Remove membership | Delete relationship, update related state if needed | Never accidentally delete User/Group nodes |
| Import one million Customers | Split into batches/transactions with checkpoints | One massive transaction causes high cost and rollback risk |
| Place order and send email | Neo4j transaction + outbox, external dispatcher | Email is not inside the Neo4j transaction |
| Payment via external provider | Local transactions and multi-step orchestration workflow | External payments cannot be directly rolled back by Neo4j |

## 4. Example Model: A Single-Line Order

Suppose the application uses this model:

~~~mermaid
flowchart LR
  C["Customer<br/>customerId"]
  O["Order<br/>orderId, status, totalInCents"]
  L["OrderLine<br/>lineId, quantity, unitPriceInCents"]
  P["Product<br/>productId, priceInCents"]
  C -->|PLACED| O
  O -->|HAS_LINE| L
  L -->|FOR_PRODUCT| P
~~~

**OrderLine** is modeled as a node because it carries a `lineId` key, quantity, and historical price. If the Product changes price the next day, old orders must still preserve the exact price at order time; never recalculate totals from `Product.priceInCents` when reading history.

### 4.1. Invariants of Placing an Order

For the single-line order example, when the transaction succeeds:

- Exactly one `Order` exists for the application-recognized `orderId`.
- One new `OrderLine` exists with a stable `lineId`.
- The Order belongs to an identified Customer.
- The OrderLine is linked to the right Order and Product.
- `quantity > 0` and `unitPriceInCents` is the price used to create the order.
- `totalInCents = quantity × unitPriceInCents` for the single-line example.

Do not assume Neo4j knows "an Order must have exactly one Customer" simply because a `PLACED` relationship exists. Relationship multiplicity invariants are modeling/application rules that must be designed and tested. A unique constraint on `Order.orderId` does not prevent relationships from different Customers pointing to the same Order.

### 4.2. Proposed Transaction Boundary

~~~text
API placeOrder
    |
    +-- validate request before transaction
    |
    +-- BEGIN Neo4j transaction
           |
           +-- MATCH Customer, Product
           +-- CREATE Order + OrderLine
           +-- CREATE relationships
           +-- RETURN orderId, totalInCents
           |
           +-- COMMIT or ROLLBACK everything
    |
    +-- return result / handle conflict / trigger post-commit tasks
~~~

**Pure validation** steps can run before opening the transaction. Conditions depending on mutable graph data must be designed so they do not unsafely rely on stale reads.

## 5. Identifiers and Constraints Before Opening Write Traffic

Use stable business keys instead of Neo4j internal IDs to identify entities across retries and across services.

~~~cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT product_id_unique IF NOT EXISTS
FOR (p:Product)
REQUIRE p.productId IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT order_id_unique IF NOT EXISTS
FOR (o:Order)
REQUIRE o.orderId IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT order_line_id_unique IF NOT EXISTS
FOR (l:OrderLine)
REQUIRE l.lineId IS UNIQUE;
~~~

Constraints must be deployed via migrations before multiple workers write concurrently. If the database already contains duplicate nodes, creating the corresponding uniqueness constraint can fail. Uniqueness on a property does not make that property mandatory, so the application must validate input keys.

**Do not run constraint creation statements in every place-order request.** Schema setup is environment preparation, not a normal business step.

## 6. Cypher Example: Creating the Entire Order Graph in One Transaction

A single Cypher statement can encompass all required changes for the single-line order use case:

~~~cypher
MATCH (c:Customer {customerId: $customerId})
MATCH (p:Product {productId: $productId})
WHERE p.priceInCents IS NOT NULL

CREATE (o:Order {
  orderId: $orderId,
  status: 'CREATED',
  createdAt: datetime(),
  totalInCents: p.priceInCents * $quantity
})
CREATE (l:OrderLine {
  lineId: $lineId,
  quantity: $quantity,
  unitPriceInCents: p.priceInCents
})
CREATE (c)-[:PLACED]->(o)
CREATE (o)-[:HAS_LINE]->(l)
CREATE (l)-[:FOR_PRODUCT]->(p)

RETURN o.orderId AS orderId,
       o.totalInCents AS totalInCents;
~~~

**Preconditions:** the request has already been validated: `orderId`, `lineId`, `customerId`, and `productId` are valid; `quantity` is a positive integer; `priceInCents` is a valid system-managed price. The statement does not perform inventory reservation or payment; those are separate business invariants that must be designed separately.

In Neo4j, a write query runs within a transaction scope. If the caller uses a managed transaction, it can be part of that transaction. If the query fails to find the Customer or Product, `MATCH` yields **0 rows** and the subsequent `CREATE` clauses do not execute. The application must **check for empty results** and return an appropriate error; never equate "no exception thrown" with "order created."

If `CREATE OrderLine` succeeds during intermediate execution but a subsequent write operation fails and rolls back the transaction, neither the OrderLine nor the transaction's relationships are committed.

### 6.1. Why Not Split into Separate Auto-Commit Calls?

Counter-example:

~~~cypher
// Call 1: create Order in a separate transaction.
CREATE (:Order {
  orderId: $orderId,
  status: 'CREATED'
});
~~~

~~~cypher
// Call 2: create line item in another transaction.
CREATE (:OrderLine {
  lineId: $lineId,
  quantity: $quantity
});
~~~

~~~cypher
// Call 3: connect Order and OrderLine.
MATCH (o:Order {orderId: $orderId})
MATCH (l:OrderLine {lineId: $lineId})
CREATE (o)-[:HAS_LINE]->(l);
~~~

If Call 1 commits but Call 2 or 3 fails, the database may persist an incomplete order. Running these statements within **the same HTTP request** does not automatically place them in the same transaction.

You can split work into multiple Cypher statements for clarity or error checking, **as long as they run within the same transaction** when atomicity is required.

### 6.2. Relationships Are Also Part of the Invariant

Having all nodes present with wrong relationships still produces a corrupt business graph. For example, an OrderLine connected to a different Product than the one selected leads to inaccurate reporting. Therefore, when designing a transaction, do not only list the nodes to create; list **all relationships and properties** that must be valid at commit time.

## 7. Java Driver: Use-Case-Scoped Managed Transactions

Below is a Java Driver example running the Cypher statement from section 6 inside `Session.executeWrite(...)`. A real system must configure `Driver`, authentication, URI, and the target database appropriately.

~~~java
import org.neo4j.driver.Driver;
import org.neo4j.driver.Result;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.Values;

public final class OrderApplicationService {
    public record CreatedOrder(String orderId, long totalInCents) {}

    private final Driver driver;

    public OrderApplicationService(Driver driver) {
        this.driver = driver;
    }

    public CreatedOrder placeSingleItemOrder(
            String orderId,
            String lineId,
            String customerId,
            String productId,
            long quantity) {

        if (orderId == null || orderId.isBlank()
                || lineId == null || lineId.isBlank()
                || customerId == null || customerId.isBlank()
                || productId == null || productId.isBlank()
                || quantity <= 0) {
            throw new IllegalArgumentException("Invalid order input");
        }

        String cypher = """
            MATCH (c:Customer {customerId: $customerId})
            MATCH (p:Product {productId: $productId})
            WHERE p.priceInCents IS NOT NULL
            CREATE (o:Order {
                orderId: $orderId,
                status: 'CREATED',
                createdAt: datetime(),
                totalInCents: p.priceInCents * $quantity
            })
            CREATE (l:OrderLine {
                lineId: $lineId,
                quantity: $quantity,
                unitPriceInCents: p.priceInCents
            })
            CREATE (c)-[:PLACED]->(o)
            CREATE (o)-[:HAS_LINE]->(l)
            CREATE (l)-[:FOR_PRODUCT]->(p)
            RETURN o.orderId AS orderId,
                   o.totalInCents AS totalInCents
            """;

        try (Session session =
                 driver.session(SessionConfig.forDatabase("neo4j"))) {
            return session.executeWrite(tx -> {
                Result result = tx.run(cypher, Values.parameters(
                    "orderId", orderId,
                    "lineId", lineId,
                    "customerId", customerId,
                    "productId", productId,
                    "quantity", quantity
                ));
                if (!result.hasNext()) {
                    throw new IllegalStateException(
                        "Customer or Product not found or invalid price"
                    );
                }
                var record = result.single();
                return new CreatedOrder(
                    record.get("orderId").asString(),
                    record.get("totalInCents").asLong()
                );
            });
        }
    }
}
~~~

The example creates the Order and OrderLine with IDs **already chosen at the request boundary**, rather than generating new IDs every time the callback retries. `executeWrite` may retry the transaction on eligible transient errors, so the callback must not send emails or invoke external services with side effects outside Neo4j.

Consider the case where **commit succeeded, yet the client never received the response**. When the caller retries with the same `orderId`, `CREATE` can hit a uniqueness violation. In that case, the service should look up the existing Order and verify matching inputs before returning an "already processed" result, rather than generating a new `orderId` or treating every uniqueness error as success.

### 7.1. `executeWrite` Can Contain Multiple Cypher Statements

A transaction is not forced to contain only one statement:

~~~java
session.executeWrite(tx -> {
    tx.run("""
        MATCH (o:Order {orderId: $orderId})
        SET o.internalNote = $note
        """, Values.parameters(
            "orderId", orderId,
            "note", note
        )).consume();

    tx.run("""
        MATCH (o:Order {orderId: $orderId})
        SET o.lastReviewedAt = datetime()
        """, Values.parameters("orderId", orderId)).consume();

    return null;
});
~~~

The two write statements above run **inside the same managed transaction** as long as both use the provided `tx` handle. In this example, both updates could be merged into a single `SET`; it illustrates transaction boundaries rather than encouraging unnecessary statement splitting.

If a Cypher statement matches **0 rows**, the transaction can still commit with no corresponding changes. Use `RETURN` or check row counts/summary counters when business logic requires the target entity to exist. Relying solely on "no exception" is not enough.

### 7.2. Lifecycle Scopes of Driver, Session, and Transaction

| Object | Reference Lifecycle | Responsibility |
|---|---|---|
| `Driver` | Reused for application lifetime | Connections, configuration, routing/pooling |
| `Session` | Short-lived, typically per application call unit | Context for executing queries |
| Managed transaction callback | One business operation that may be retried | Reading/writing data that must commit together |
| `Result` / `Record` | Consumed within proper scope | Mapping returned data to DTOs |

Never share a `Session` arbitrarily across threads, or pass an unconsumed `Result` outside the callback expecting it to work after the transaction closes.

## 8. Choosing Between Read and Write Transactions

Use `executeRead` for read-only queries:

~~~java
try (Session session = driver.session(
        SessionConfig.forDatabase("neo4j"))) {
    var orders = session.executeRead(tx ->
        tx.run("""
            MATCH (:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
            RETURN o.orderId AS orderId,
                   o.status AS status
            ORDER BY o.createdAt DESC, o.orderId DESC
            LIMIT $limit
            """, Values.parameters(
                "customerId", customerId,
                "limit", 20
            )).list(row -> new OrderSummary(
                row.get("orderId").asString(),
                row.get("status").asString()
            ))
    );
}
~~~

This example assumes `OrderSummary` is an application-defined DTO/record and `customerId` is a valid input variable. Put filters, pagination, and projections in Cypher so unneeded nodes/relationships are not transferred.

**Do not use `executeRead` just because the query has a `MATCH` clause**: if the transaction executes `CREATE`/`SET`/`DELETE`, it is a write operation and must use `executeWrite`.

### 8.1. Do Multiple Reads Need the Same Transaction?

If the application computes a result from multiple related read queries, placing them inside one read transaction ensures they are managed as a single transaction unit. However, Neo4j's default isolation level is typically described as **read committed**; do not implicitly assume multiple reads in one transaction always observe an immutable database-wide snapshot.

If a report requires a strict snapshot across multiple queries, design a consistency mechanism suited to your Neo4j version, workload, and data sources, rather than assuming a read transaction provides serializable isolation.

### 8.2. Do Not Wrap Every Screen Read Query in a Write Transaction

A dashboard page may invoke multiple independent endpoints: order list, counts by status, and top-selling products. You do not have to bundle them all into one write transaction. If the business accepts metrics refreshing at different cadences, they can be read independently using appropriate projections/materialized summaries.

Require stronger cross-query consistency only when the screen contract genuinely demands it, such as a financial reconciliation document.

## 9. Read–Check–Write and the Limits of Atomicity Under Concurrent Writes

Suppose we must deduct 3 items from inventory, but only if stock has at least 3. A naive design might do:

~~~text
T1: read stock = 4
T2: read stock = 4
T1: decide to allow order of 3
T2: decide to allow order of 3
T1/T2: write updated stock
~~~

If one transaction reads stock and a separate transaction deducts it, the earlier check is no longer trustworthy. Yet **even placing `MATCH`/`WHERE`/`SET` inside one transaction does not automatically prove** that the condition is evaluated after acquiring the necessary write lock under every query syntax or execution plan.

### 9.1. Lost Updates When Precomputing Values

Example vulnerable to lost updates:

~~~cypher
MATCH (p:Product {productId: $productId})
WITH p, p.stock AS oldStock
SET p.stock = oldStock - $quantity
RETURN p.stock AS stock;
~~~

Two transactions can both compute `oldStock` before a write lock is acquired for `SET`, and then write back values derived from stale data.

For simple increments/decrements, expressing the new value directly in terms of the existing property inside `SET` lets Neo4j apply appropriate locking:

~~~cypher
MATCH (p:Product {productId: $productId})
SET p.stock = p.stock - $quantity
RETURN p.stock AS stock;
~~~

Even so, the second example **does not yet protect the non-negative stock invariant**. To implement inventory reservation safely under concurrency, you need a concurrency-safe check workflow: coordinating write locks, re-reading state after holding the lock, or using version control verified for your running Neo4j version. Without protecting the check timing, two parallel orders can still oversell.

### 9.2. Multi-Node Writes Risk Deadlocks

Transferring points from wallet A to wallet B may require writing two nodes. Two transactions transferring A→B and B→A in opposite lock acquisition orders risk deadlocking. Neo4j can detect this and roll back one transaction; the application must handle transient errors with appropriate retries.

Consider establishing a **consistent lock ordering** convention by ID in workflows that update multiple entities. This helps reduce certain deadlock patterns, though it does not guarantee eliminating all of them because Neo4j can also acquire locks related to relationship structures and other operators.

Never keep a transaction open during an external HTTP call just to wait for business completion; held locks can block many other requests.

## 10. Idempotency for Resubmitted Business Requests

An API can encounter this scenario:

~~~text
Client                   API / Neo4j
   |--- placeOrder ------->|
   |                       |--- transaction commits successfully
   |                       |
   X--- lost response -----|
   |
   |--- retry placeOrder ->|   (same logical operation)
~~~

When the client receives no response, **it cannot be sure** the database did not commit. An idempotency key such as `orderId` or `commandId` that remains stable across attempts is needed.

In the place-order example:

- `orderId` and `lineId` are chosen upfront, **never generating a new UUID on each retry**.
- Uniqueness constraints prevent creating two Orders with the same `orderId`.
- If a subsequent attempt hits a uniqueness violation, the service fetches the existing Order and compares Customer/Product/quantity/price or request hash per the contract.
- If the data matches: treat the request as already processed; if different: return a conflict, never silently overwrite.

**Do not treat every uniqueness error as a safe duplicate**: a different key might have collided, or the data may have been created by a different request.

### 10.1. `MERGE` on a Node Is Not Enough for Every Operation

~~~cypher
MERGE (a:Account {accountId: $accountId})
SET a.rewardPoints = coalesce(a.rewardPoints, 0) + 100;
~~~

`MERGE` protects finding/creating the Account by key, **it does not know whether the "add 100 points" command was already applied**. If the request runs again and commits a second time, points increase by 200.

For additive/incremental operations, a stable `commandId`/`eventId` and a receipt/ledger written in the same transaction as the business change are required, backed by a uniqueness constraint on the command identifier. That is a **different invariant** from uniqueness of the Account node.

### 10.2. Transaction Boundaries Must Include the Receipt When Needed

~~~cypher
MATCH (a:Account {accountId: $accountId})
CREATE (cmd:AppliedCommand {
    commandId: $commandId,
    accountId: $accountId,
    delta: $delta,
    appliedAt: datetime()
})
SET a.rewardPoints = coalesce(a.rewardPoints, 0) + $delta
SET cmd.resultPoints = a.rewardPoints
CREATE (cmd)-[:APPLIED_TO]->(a)
RETURN cmd.resultPoints AS resultPoints;
~~~

Required constraint:

~~~cypher
CREATE CONSTRAINT applied_command_unique IF NOT EXISTS
FOR (cmd:AppliedCommand)
REQUIRE cmd.commandId IS UNIQUE;
~~~

If `commandId` already exists, `CREATE` violates the constraint and the transaction fails; the additive update in that transaction does not commit either. After the error, the application reads the receipt and compares request details before confirming it was already processed.

**These are two separate scopes to distinguish:**

1. **Business transaction:** updating the Account and writing the receipt commit together.
2. **API retry policy:** on an ambiguous outcome, inspect the receipt and decide whether to retry.

## 11. When Operations Must Call Systems Outside Neo4j

A use case often spans beyond a single database:

- Place an order and call a payment gateway.
- Place an order and send a confirmation email.
- Add a friend and publish a message to a notification system.
- Approve an order and dispatch a shipping request to an external warehouse service.

A Neo4j transaction guarantees atomicity only for changes **within the Neo4j database**. Email, Kafka, REST APIs, another SQL server, or a payment system **do not automatically participate in the same transaction**.

### 11.1. Why Not Call External APIs Inside `executeWrite`?

~~~java
session.executeWrite(tx -> {
    tx.run("""
        MATCH (o:Order {orderId: $orderId})
        SET o.status = 'CONFIRMED'
        """, Values.parameters("orderId", orderId)).consume();

    mailer.sendOrderConfirmation(orderId);
    return null;
});
~~~

If the callback is retried by the driver, the email may be sent multiple times. If the transaction rolls back, an already sent email cannot be unsent.

Calling an external API while holding a transaction also increases lock duration, latency, and contention with other workers.

**Principle:** a managed transaction callback should focus on Neo4j operations that can be safely retried; never execute external side effects unless proper idempotency mechanisms are in place.

## 12. Transactional Outbox: Writing the "Intent to Publish" Alongside Data

One way to bridge local transactions with a message broker is the **transactional outbox**.

~~~mermaid
flowchart TD
    A["API: Confirm Order"] --> B["Neo4j transaction"]
    B --> C["SET Order.status = CONFIRMED"]
    B --> D["CREATE OutboxEvent PENDING"]
    C --> E["COMMIT"]
    D --> E
    E --> F["Dispatcher reads OutboxEvent"]
    F --> G["Publish broker / call external service"]
    G --> H["Mark progress"]
~~~

Benefit: if Neo4j commits, both **Order status** and **proof that an event must be emitted** are present; if it rolls back, neither commits.

Create a constraint on the event key:

~~~cypher
CREATE CONSTRAINT outbox_event_key_unique IF NOT EXISTS
FOR (e:OutboxEvent)
REQUIRE e.eventKey IS UNIQUE;
~~~

Example in a single transaction:

~~~cypher
MATCH (o:Order {orderId: $orderId})
SET o.status = 'CONFIRMED',
    o.confirmedAt = datetime()
CREATE (e:OutboxEvent {
    eventKey: $eventKey,
    eventType: 'OrderConfirmed',
    orderId: $orderId,
    status: 'PENDING',
    createdAt: datetime()
})
CREATE (o)-[:EMITS]->(e)
RETURN o.orderId AS orderId, e.eventKey AS eventKey;
~~~

`eventKey` must stay stable across retries of the same confirmation action. If confirmation can be invoked repeatedly, you must also ensure **confirmation semantics are not duplicated** or guard properties conditionally before emitting an event. The outbox constraint prevents two events with the same key; it does not automatically enforce valid Order state transitions when different command types run concurrently.

**Outbox does not mean exactly-once delivery.** If the dispatcher publishes successfully and crashes before updating the status to `SENT`, it may publish the same `eventKey` again. Consumers must deduplicate or target APIs must accept an idempotency key.

### 12.1. Do Not Treat Reading `PENDING` Events as an Exclusive Claim

~~~cypher
MATCH (e:OutboxEvent {status: 'PENDING'})
RETURN e.eventKey AS eventKey
LIMIT 10;
~~~

This is a **read** query; it does not exclusively claim those ten events. Two dispatchers can read the exact same result set. In production, you need a claim/lease/timeout mechanism, worker coordination, and a dedicated retry policy.

### 12.2. Outbox Messages Should Contain Stable Data

Do not let the dispatcher re-read the Order later and assume it reflects the "exact state when the event occurred" if the Order has continued changing. Store the necessary data/version snapshot directly in `OutboxEvent` within the same transaction so messages can be reconstructed deterministically.

## 13. Multi-System Workflows: Local Transactions and Sagas

Suppose placing an order in Neo4j is followed by paying through an external system:

~~~text
Step 1. Neo4j: create Order = PENDING_PAYMENT
Step 2. Payment API: confirm transaction
Step 3. Neo4j: update Order = PAID
Step 4. Shipping service: create shipment request
~~~

Do not hold **one Neo4j transaction open** across Steps 1–4, because:

- The Payment API may take seconds or minutes.
- Neo4j cannot roll back a completed payment.
- Long transactions hold locks, increase overhead, and cause timeouts.
- Any failure at a later step requires a business decision, not just a database rollback.

One approach is a **saga**: multiple step-by-step local transactions with events, intermediate states, and **compensating actions** when a downstream step fails.

For instance, if payment succeeded yet shipping failed, the system may need to issue a **refund** according to business rules, not roll back an already committed Neo4j transaction. A compensating action is a **new business operation**, not an automatic undo feature in Neo4j.

### 13.1. Distinguishing Strong Consistency and Eventual Consistency

| Need | Viable Option |
|---|---|
| Order and OrderLine must exist together | Single Neo4j transaction |
| Receipt write and points increment must commit together | Single Neo4j transaction with constraint |
| Committed Order must eventually emit an event | Neo4j transaction + outbox + dispatcher |
| External payment must stay coordinated with Order | Workflow/saga and idempotency on payment API |
| Dashboard reading aggregated data across services | Often accepts eventual consistency if contract allows |

Never use "eventual consistency" as an excuse for invalid state inside **a single internal transaction**. Conversely, never force a multi-system workflow into a single database transaction just because "everything must be right."

## 14. Designing Transactions for Relationship Updates

Some business operations center on the **relationship**, not the node.

For example, "customer follows an author":

~~~cypher
MATCH (u:User {userId: $userId})
MATCH (a:Author {authorId: $authorId})
MERGE (u)-[r:FOLLOWS]->(a)
ON CREATE SET r.followedAt = datetime()
RETURN u.userId AS userId, a.authorId AS authorId;
~~~

If the entire business rule is "ensure a follow relationship exists," one transaction for this pattern may suffice. However, if it must also update invitation status, remove a pending request, and create the relationship, **all changes that must hold together** belong in the same transaction.

**Concurrency warning:** `MERGE` on a relationship between two identified nodes expresses the intent to find or create, yet uniqueness constraints on `User` and `Author` IDs **do not automatically guarantee relationship uniqueness for the same pair** under all concurrent write schedules. If business rules forbid duplicate `FOLLOWS` relationships, design concurrency controls/relationship identification appropriate to your Neo4j version and test it.

### 14.1. Never Delete Nodes Just to Remove a Relationship

~~~cypher
MATCH (u:User {userId: $userId})-[r:FOLLOWS]->
      (a:Author {authorId: $authorId})
DELETE r;
~~~

Unfollowing means deleting the `FOLLOWS` relationship, not running `DETACH DELETE u` or deleting the Author. The transaction scope must match the **intended business effect**, avoiding impact on unrelated entities.

## 15. Batching Without Breaking an Invariant

For CSV imports or processing millions of events, do not wrap the entire dataset in one giant transaction. Large transactions hold many locks for a long time, consume heavy memory, and make rollbacks very expensive.

A sound design:

1. Identify the **smallest invariant unit**: one Customer, one complete Order, one applied event with its receipt.
2. Never split a unit that must commit together across two separate transactions.
3. Group multiple independent units into appropriately sized batches.
4. Use stable keys, checkpoints, and replay/deduplication rules to resume after failures.
5. Limit parallelism when multiple batches update hot nodes.

For example, if an Order has three line items, do not split `CREATE Order` into today's batch and `CREATE OrderLine` into tomorrow's batch **if the business exposes an Order as complete as soon as it commits**. You can use a staging status `IMPORTING` and a publishing step `READY` once all data is verified, but that is a **different business contract** and must be modeled explicitly.

Neo4j supports version-appropriate batching mechanisms, such as managing transactions in the Java Driver or Cypher transaction-splitting patterns. `CALL ... IN TRANSACTIONS` syntax and restrictions must be checked against your Neo4j version; do not mix it inside another managed transaction when disallowed.

## 16. Operations: Keep Transactions Short Without Cutting Across the Wrong Boundary

Principles to reduce transaction duration:

- Validate format, types, and authorization in the application layer before starting when they do not depend on changing data.
- Use business keys and matching indexes/constraints to locate nodes fast.
- `MATCH` only the nodes/relationships that need updating.
- Do not return huge graphs/paths when the API only needs IDs and a few properties.
- Never perform I/O outside Neo4j inside a transaction callback.
- Cap the number of records processed per transaction; tune against real workloads.
- Avoid holding transactions while waiting for users, HTTP calls, or sleep/backoff.
- Retry the **entire transaction** on eligible error classes, never resuming midway through a rolled-back transaction.

Yet **never slice a valid transaction into smaller ones** just to reduce lock hold time if doing so breaks business atomicity.

### 16.1. Inspecting Query Plans and Transactions

~~~cypher
EXPLAIN
MATCH (c:Customer {customerId: $customerId})
MATCH (p:Product {productId: $productId})
RETURN c.customerId AS customerId,
       p.productId AS productId;
~~~

`EXPLAIN` shows the plan without executing the query; use it to check node lookups, indexes, and estimated row counts. For write queries, `PROFILE` **actually executes the write operation**, so never run it against production data merely to inspect a plan.

Depending on permissions and Neo4j version, inspect running transactions with:

~~~cypher
SHOW TRANSACTIONS;
~~~

Monitor long-running transactions, lock waits, deadlocks, timeouts, batch sizes, and application retries. Low average query time does not prove that no requests are stalling on lock contention.

## 17. Service Blueprint for Layered Applications

A common architecture:

~~~mermaid
flowchart TD
    A["HTTP Controller"] --> B["Application Service / Use Case"]
    B --> C["Neo4j transaction / Repository"]
    C --> D["Node + Relationship + Property"]
    C --> E["OutboxEvent if needed"]
    E --> F["Dispatcher"]
    F --> G["Broker / external service"]
~~~

### 17.1. The Application Service Defines the Boundary

The controller receives input and calls `placeOrder`; the application service defines invariants, executes the transaction, and classifies errors; the repository or `Neo4jClient` owns the specific Cypher statements.

Do not let a controller sequentially call four write repositories using four default transactions and assume the operations are atomic simply because they sit inside one HTTP request.

### 17.2. Spring Data Neo4j and `@Transactional`

With Spring Data Neo4j, a service can declare:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderWorkflowService {
    private final OrderWorkflowRepository repository;

    public OrderWorkflowService(OrderWorkflowRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void attachExistingLine(
            String orderId, String lineId, String productId) {
        repository.assertOrderAndProductExist(orderId, productId);
        repository.createLineAndRelationships(orderId, lineId, productId);
    }
}
~~~

This is a **layering example**, assuming `OrderWorkflowRepository` provides the matching methods; it is not standalone compilable code without implementing the repository. When the Spring transaction manager is properly configured for Neo4j, repository calls run within the service's transaction scope according to transaction management rules.

Notes:

- A Spring `@Transactional` does not automatically commit atomically across Neo4j, SQL, and Kafka.
- Spring-layer retries, if used, must be designed explicitly; do not treat `@Transactional` as equivalent to `executeWrite`'s retry policy.
- Self-invocation and proxy configuration affect how annotations apply; verify transaction behavior on real services.
- If an exception is caught and swallowed before exiting the service, rollback may not occur as intended unless explicitly marked for rollback.
- Never mix Java Driver managed transactions arbitrarily with an active Spring transaction without understanding how they manage sessions and commit scopes.

**Design rule:** transaction boundaries should be declared at the **use-case/application service**, which knows which steps must succeed together, rather than scattered across individual repository calls without a shared contract.

## 18. Error Handling by Business Boundary

| Outcome / Error | Impact on Transaction | Application Response |
|---|---|---|
| Commit succeeds | All changes in transaction committed | Return business result |
| A Cypher statement throws and transaction rolls back | Uncommitted changes in transaction discarded | Return error or retry by error class |
| `MATCH` finds no nodes and throws no error | Potentially zero changes made | Check result and report missing data |
| Uniqueness violation | Write transaction may fail | Distinguish idempotent duplicate from conflict |
| Deadlock / transient error | A transaction may roll back | Bounded retry of the entire use case |
| Connection lost after commit | Client outcome is ambiguous | Re-read using stable key / receipt |
| Email API fails after Neo4j commit | Neo4j does not roll back for email | Outbox / retry / compensation |
| Payment API succeeds but Order update fails | Two systems' states diverge | Reconcile state via saga / reconciliation |
| Resource limit exceeded due to huge batch | Transaction may fail or hang | Reduce batch size, add checkpoints, monitor |

### 18.1. Do Not Confuse Technical Errors and Business Errors

If the Customer does not exist, return `NOT_FOUND` rather than retrying. If the same `orderId` already exists with a different payload, return `CONFLICT`. If a transient cluster/lock error occurs, bounded retry may make sense.

When retrying, rerun **the entire callback or transaction**—never resume from "step three" as if earlier steps had committed. Once a transaction rolls back, all Neo4j operations inside it must be treated as undone.

### 18.2. Idempotency Is Part of the API Contract

Documentation for the place-order endpoint should state clearly:

- Which key identifies one logical request: `orderId` or `requestId`.
- How same key / same payload is handled.
- Whether same key / different payload returns a conflict.
- On timeout, whether the client should resend the same key or poll status.
- Which intermediate states may be exposed.

Safe retries cannot be built if the client generates a fresh key for every attempt of the same operation.

## 19. Testing Transaction Boundaries

### 19.1. Testing Atomicity

In a test database, create a valid Customer and Product, then invoke `placeOrder` with a new `orderId`.

**Expected on success:**

- One new Order and one new OrderLine exist.
- `PLACED`, `HAS_LINE`, and `FOR_PRODUCT` are all present.
- Order stores the exact price at order time.

**Expected on mid-flight failure:** intentionally trigger a constraint error on `lineId`, and verify no new Order or relationships from the failed attempt were committed.

Example verification query for one Order's key:

~~~cypher
MATCH (o:Order {orderId: $orderId})
OPTIONAL MATCH (c:Customer)-[placed:PLACED]->(o)
OPTIONAL MATCH (o)-[hasLine:HAS_LINE]->(l:OrderLine)
OPTIONAL MATCH (l)-[forProduct:FOR_PRODUCT]->(p:Product)
RETURN o.orderId AS orderId,
       count(DISTINCT c) AS customers,
       count(DISTINCT l) AS lines,
       count(DISTINCT p) AS products;
~~~

This query checks **a single Order** and assumes the single-line model. Multiple `OPTIONAL MATCH` clauses can multiply rows if duplicate relationships exist; `DISTINCT` counts distinct nodes, but if you need to detect duplicate relationships, count each relationship separately.

### 19.2. Testing Retries and Idempotency

| Scenario | Expected Outcome |
|---|---|
| One request creates a new Order | One complete Order exists |
| Same `orderId` and payload resent | No duplicate Order/OrderLine |
| Same `orderId` but different payload | Return conflict, do not overwrite |
| Two threads concurrently place same `orderId` | Constraint prevents two duplicate committed Orders |
| Error injected between write statements in one transaction | No partial updates committed |
| Transient error injected before commit | Callback can retry; no external side effects duplicated |
| Lost response after commit | Client uses same key to query status |
| Outbox dispatcher crashes after publish | May republish; downstream deduplicates |
| Placing order concurrently with stock changes | Verify stock invariant via concurrency tests |

### 19.3. Testing Multiple Transactions and External Systems

Do not merely unit-test the service with a mocked repository and conclude the transaction boundary is sound. Write integration tests against a real Neo4j instance with constraints and multiple threads, especially for:

- Concurrent writes targeting the same business key.
- Operations modifying multiple relationships.
- Failures between the first write statement and the second write statement.
- Retries after timeouts and ambiguous commit outcomes.
- Outbox dispatcher redelivery.
- Saga workflows requiring compensation.

In test environments, never use production data or send real emails/payments to simulate failures.

## 20. Common Design Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| One repository call equals its own transaction despite sharing one business operation | Graph left in partial state | Place boundary at use-case service |
| Assuming one HTTP request is automatically atomic | DB calls can commit independently | Use explicit/managed transactions |
| Wrapping external HTTP calls inside a transaction | Long lock holds, non-rollbackable side effects | Outbox and separate workflows |
| Generating new IDs inside a retryable callback | Same request creates multiple Orders | Stabilize IDs before callback |
| Only running `MERGE Account` before adding points | Retries add points again | Receipt/`commandId` in same transaction |
| Checking only "no exception" after `MATCH` | Zero rows matched means no data created | Check `RETURN`/row counts |
| Believing transactions automatically prevent all lost updates | Stale reads overwritten | Concurrency design and verification |
| Assuming node constraints prevent duplicate relationships | Duplicate edges can still violate rules | Relationship model and write coordination |
| One transaction for importing millions of rows | Long locks, costly rollbacks | Batch by invariant unit |
| Splitting a "complete" order across two transactions | Missing lines/relationships state | Group changes that must hold together |
| Running `PROFILE` on write queries in production | Writes actually execute | Use `EXPLAIN` or a test DB |
| Ignoring ambiguous commits | Requests applied multiple times | Track by ID/receipt and safe retry |

## 21. Practice Exercises

### Exercise 1 — Defining a Transaction for an Order

Requirement: create an Order with two OrderLines and all required relationships. If one line item fails, the order must not appear.

**Question:** Should you create the Order and each OrderLine in three auto-commit calls or one transaction?

**Answer:** One transaction covering the mandatory nodes, relationships, and properties of the Order. On error, roll back every part of the business operation.

### Exercise 2 — Renaming a Product

The sole requirement is updating `Product.name`, with no relationship changes or external systems involved.

**Question:** Should you keep the transaction open while waiting for an email service to finish sending?

**Answer:** No. Limit the transaction to updating the Product; if notifications are needed, use an appropriate post-commit/outbox workflow.

### Exercise 3 — Adding Reward Points

An API receives a command to add 100 points. If the client retries after a timeout, the command must not add points a second time.

**Question:** Is `MERGE (Account)` sufficient?

**Answer:** No. You need a stable command identifier, a receipt/constraint, and the points update inside the same transaction; inspect the receipt when commit status is ambiguous.

### Exercise 4 — Inventory

Two users concurrently order three units when stock is four.

**Question:** Is wrapping the `stock >= 3` check and stock deduction in one transaction guaranteed to be safe?

**Answer:** Not guaranteed without understanding read/lock timing and how the condition is expressed. You must design a concurrency-safe reservation operation and run concurrency tests against Neo4j.

### Exercise 5 — External Payment

The Neo4j transaction created the Order successfully, the payment API succeeded, yet the shipping service failed.

**Question:** Can you roll back Neo4j to automatically undo the payment?

**Answer:** No. You must orchestrate a saga/compensating action according to business rules, such as issuing a refund or transitioning to an error-handling state.

### Exercise 6 — Outbox Events

The dispatcher sent the message successfully but crashed before marking it `SENT`.

**Question:** Does an outbox guarantee the consumer receives the message exactly once?

**Answer:** No. The dispatcher may resend it. Use a stable `eventKey` and consumer-side idempotency.

### Exercise 7 — Multiple Read Queries

A service opens one read transaction, reads `Order.status`, and then reads `Order.totalInCents` afterward.

**Question:** Can you guarantee both reads see an immutable snapshot?

**Answer:** Not solely from sharing a transaction. You must understand isolation semantics and the consistency level the business requires.

### Exercise 8 — Transaction Swallowing Exceptions

A Spring service catches an exception from the repository and returns success without rethrowing or marking for rollback.

**Question:** What is the risk?

**Answer:** The transaction may commit changes made before the error if not properly marked for rollback. Define exception-handling rules consistent with use-case semantics.

## 22. Takeaways

**Transaction boundaries in Neo4j must be designed around business operations and invariants that must hold together**, not by the number of Cypher statements, repositories, or HTTP requests. A complete Order requires its nodes, relationships, and related properties to commit together; a simple rename does not need a transaction spanning unrelated work.

In the Java Driver, use `executeWrite` for write steps that must be atomic, handle `MATCH` yielding zero rows, prepare stable business keys, and design callbacks safe for retries. **Atomicity alone does not solve write contention**, so conditions like inventory, versioning, and relationship uniqueness require dedicated protection and testing. When workflows involve brokers, email, or payments, use **local transactions, outboxes, and sagas** as needed instead of assuming Neo4j can roll back external systems. A well-chosen boundary both protects graph integrity and keeps transactions short enough for stable production operations.
