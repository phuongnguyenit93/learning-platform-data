# Stable Identifiers, Idempotency, and Duplicate Request Control

## 1. The Real-World Problem: A Request Can Be Sent Multiple Times

In an application using **Neo4j**, an operation rarely writes just a single property. For instance, an order creation API must create an **Order**, link it to a **Customer**, save processing status, and emit an event to the payment system. Neo4j stores these entities in a **property graph** consisting of nodes, relationships, and properties; the Java Driver or Spring Data Neo4j forms the connectivity layer, while Cypher executes writes.

Suppose the application receives a **POST /orders** request:

1. The client sends a request to create order **A**.
2. Neo4j executes and **commits successfully**.
3. The connection drops before the client receives the response.
4. The client or gateway retries the same request.

If every call runs **CREATE** on a new node, the system may create **two orders** or send two payment notifications. This is a classic distributed-network problem: **not receiving a response does not mean the transaction failed to commit**.

In the **Application Design** chapter of the **DATABASE_ENGINE_GRAPH_NEO4J** module, three mechanisms must work together:

1. **Stable identifiers:** the same business entity must be recognized by the same key across calls, imports, restarts, and deployments.
2. **Idempotency:** re-executing the same valid request produces no additional business side effects.
3. **Duplicate control:** use **constraints**, **transactions**, payload checks, and retry policies to guard against concurrent arrivals or retries after network failures.

The goal is not to force the network to deliver only once; the goal is to ensure **multiple deliveries yield a business outcome equivalent to one successful processing**.

## 2. Distinguishing Three Types of Identifiers

| Identifier Type | Example | Purpose | Lifecycle |
|---|---|---|---|
| **Business key** | **tenantId + orderId**, **customerCode** | Locate **the same entity** in the graph | Durable for the entity's lifecycle and domain rules |
| **Idempotency key** | **Idempotency-Key: 5b8...** | Identify **a single request intent** that may be retried | Retained for at least the committed retry window |
| **Correlation/trace ID** | **trace-8f1...** | Trace a single request across logs and multiple services | For observability; a retry may carry a new trace |

**A business key is not necessarily an idempotency key.** One customer can place many orders; **customerId** cannot serve as the key for every order-creation request. Conversely, a "create order" request may not yet know the **orderId** when the client starts; the server must persist the mapping from **idempotency key** to the created order.

### 2.1. Avoid Using Neo4j Internal IDs as Business Identifiers

Neo4j provides **elementId(n)** and internal identifiers to reference graph elements within a database context. They are **not a durable identifier contract** to expose in an API. A deleted, re-imported, or restored node can receive a different internal identifier; internal values also have lifecycle limits that applications must clearly understand.

Never use **id(n)** (the legacy internal ID function) as a customer code, order code, or cross-service exchange key. Instead:

~~~cypher
CREATE (:DemoAppCustomer {
  tenantId: 'shop-a',
  customerId: 'C-101',
  displayName: 'Nguyen An'
});
~~~

Here **tenantId + customerId** is the business-managed identifier. **C-101** retains its meaning when transferring data across systems or recreating the node with the same code. For keys not naturally supplied by the domain, the application can generate a **UUID/ULID** or equivalent code, store it as a property, and protect it with a constraint.

### 2.2. Requirements for a Good Business Key

- **Stable:** do not put mutable display names, statuses, or email addresses into the key unless the business guarantees immutability.
- **Clearly scoped:** two tenants can both have order **O-100**, so the unique key is usually **(tenantId, orderId)**.
- **Consistent normalization:** trimming, case folding, Unicode normalization, and code formatting rules must be uniform across writes, reads, imports, and index creation.
- **No arbitrary reuse:** if a code attached to a deleted entity is reassigned to another entity, old events may become wrongly linked.
- **Avoid sensitive data:** avoid using emails, phone numbers, or personal data as public identifiers when surrogate codes can be used.

For example, **shop-a / O-100** and **shop-b / O-100** are two distinct valid orders. Placing the constraint solely on **orderId** without **tenantId** would wrongly prevent two tenants from sharing the same code.

## 3. Uniqueness Constraints Are the Final Guard Against Duplicate Nodes

**MERGE** searches for a pattern first and creates it if not found. Neo4j recommends placing a **uniqueness constraint** on identifier properties because **MERGE alone only ensures the pattern exists, not node uniqueness under concurrent write load**.

### 3.1. Create Constraints Before Opening Write APIs

The following examples use a **test** database and labels **DemoAppOrder**, **DemoAppCustomer**, and **DemoAppRequest** to avoid affecting production data:

~~~cypher
CREATE CONSTRAINT demo_app_order_unique IF NOT EXISTS
FOR (o:DemoAppOrder)
REQUIRE (o.tenantId, o.orderId) IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT demo_app_customer_unique IF NOT EXISTS
FOR (c:DemoAppCustomer)
REQUIRE (c.tenantId, c.customerId) IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT demo_app_request_unique IF NOT EXISTS
FOR (r:DemoAppRequest)
REQUIRE (r.tenantId, r.operation, r.requestKey) IS UNIQUE;
~~~

Each constraint forbids **two nodes with the same label** from having the same combination of specified property values. Constraints back **MERGE** execution and come with an index to look up nodes by key.

**Important limitation:** a uniqueness constraint **does not require every node to have all properties**. A **DemoAppOrder** missing **tenantId** or **orderId** is not automatically rejected by this uniqueness constraint. The application must validate required values before writing. If you need combined **existence + uniqueness** at the database level, evaluate **node key constraints** in **Neo4j Enterprise Edition** and your running version's capabilities.

Creating a constraint on data that already has **duplicate keys** will fail. Before deploying onto an existing graph, audit and merge or resolve duplicates via business procedures. **IF NOT EXISTS** does not fix duplicate data and does not guarantee that another differently named constraint with wrong semantics is equivalent.

### 3.2. Inspecting Constraints

~~~cypher
SHOW CONSTRAINTS
YIELD name, type, entityType, labelsOrTypes, properties
WHERE name STARTS WITH 'demo_app_'
RETURN name, type, entityType, labelsOrTypes, properties
ORDER BY name;
~~~

The output should confirm all three constraints were created before testing concurrent transactions. In multi-tenant databases, verify specifically that composite keys include **tenantId**.

## 4. CREATE, MERGE, and ON CREATE/ON MATCH

### 4.1. CREATE Always Creates a New Node If Constraints Permit

~~~cypher
CREATE (:DemoAppOrder {
  tenantId: 'shop-a',
  orderId: 'O-100',
  status: 'CREATED'
});
~~~

Re-running this statement when a node with the same key already exists will **violate the constraint**; without a constraint, re-running creates duplicate nodes. **CREATE** fits when you are certain the entity is new and uniqueness protection is in place.

### 4.2. MERGE on a Stable Key

~~~cypher
MERGE (o:DemoAppOrder {
  tenantId: 'shop-a',
  orderId: 'O-101'
})
ON CREATE SET
  o.status = 'CREATED',
  o.createdAt = datetime()
RETURN o.orderId AS orderId, o.status AS status;
~~~

Re-running the statement above **matches the existing node**, without creating a new node or resetting **createdAt**. **ON CREATE SET** runs only upon creation. When intentional updates are needed, use **ON MATCH SET** for properties the business allows to be updated.

**Mistake to avoid:**

~~~cypher
// Do not include mutable state as part of the MERGE key.
MERGE (o:DemoAppOrder {
  tenantId: 'shop-a',
  orderId: 'O-101',
  status: 'CREATED'
});
~~~

If order **O-101** has already transitioned to **PAID**, the pattern with **status: 'CREATED'** no longer matches. Neo4j will try to create another node with the same **tenantId + orderId** and fail on the uniqueness constraint. The proper design is **MERGE by identifier**, then **SET state** according to business rules.

### 4.3. Do Not MERGE an Entire Complex Pattern Before Endpoints Are Resolved

To create a relationship between Customer and Order, resolve each node first:

~~~cypher
MERGE (c:DemoAppCustomer {
  tenantId: 'shop-a',
  customerId: 'C-101'
})
ON CREATE SET c.displayName = 'Nguyen An'
MERGE (o:DemoAppOrder {
  tenantId: 'shop-a',
  orderId: 'O-101'
})
ON CREATE SET o.status = 'CREATED'
MERGE (c)-[:DEMO_APP_PLACED]->(o);
~~~

**MERGE (c)-[:DEMO_APP_PLACED]->(o)** with both endpoints already bound finds or creates the relationship; Neo4j applies appropriate locking when concurrent transactions merge a relationship between those two nodes. However, no default constraint forbids multiple relationships of the same type between two nodes across the graph; independent **CREATE** operations or other patterns can still add extra relationships.

If a Customer can make **multiple purchases of the same Product**, do not model every event as a single **[:BOUGHT]** relationship when individual purchases must be preserved. Use an **Order/Purchase/Event node with its own business key**, or a relationship carrying a constrained event key as required.

## 5. Idempotency: "Retry" Differs from "New Business Operation"

An operation **f** is idempotent if in terms of observable state:

\[
f(f(x))=f(x)
\]

However, for **HTTP POST**, two requests with identical payloads **are not necessarily** the same intent. A customer may intentionally place two identical orders. Conversely, a retried order placement carrying the same **Idempotency-Key** must be recognized as **the same intent**.

Design the API contract, for example:

~~~http
POST /v1/orders
Idempotency-Key: 5b8f2f3f-3a4e-4d17-8b0c-72e2c4e02a21
Content-Type: application/json

{"customerId":"C-101","amountMinor":159900,"currency":"VND"}
~~~

Sound rules:

| Case | Expected Behavior |
|---|---|
| New key, valid payload | Create **one** order, save key → orderId mapping, return result |
| Same key, **semantically identical payload** | Return the result of the same order; create nothing new and emit no new side effects |
| Same key, **different payload** | Reject, e.g., **HTTP 409 Conflict**; never turn an old key into a new request |
| Different key, identical payload | May create another order because it is a **different intent**, unless domain has separate dedupe rules |
| Missing key on an endpoint requiring idempotency | Reject before writing, or apply published API policy |

**Idempotency keys** should be scoped to **tenant** and **operation/endpoint**, not just a global string. For example, key **K1** in **shop-a / CREATE_ORDER** differs from **K1** in **shop-b / CREATE_ORDER** or **shop-a / CANCEL_ORDER**.

### 5.1. Payload Fingerprint

Do not check the key alone. If a client accidentally reuses a key for two different requests, the application must detect the conflict.

The API layer computes a **fingerprint** from a canonical representation of **business-significant fields**: tenant, operation, customerId, amountMinor, currency, normalized item list, etc. **SHA-256** over a canonical representation can be used, or another controlled scheme.

- Do not hash raw arbitrary JSON if key ordering, whitespace, or number formatting causes equivalent payloads to hash differently.
- Do not include **traceId**, request arrival timestamp, or access token in the fingerprint if they change across retries.
- Do not trust a client-supplied fingerprint without validating the payload.
- Normalize currency units, currency codes, IDs, null representations, and collection order when the business considers order insignificant.

A fingerprint does not replace validation. Two requests with the same key but differing significant data must be rejected even if the client claims it is a retry.

## 6. One Atomic Transaction for Request Key and Order

### 6.1. Why Pre-Checking with Two Independent Queries Is Wrong

Risky pattern:

~~~text
T1: MATCH requestKey K -> not found
T2: MATCH requestKey K -> not found
T1: CREATE Order O1
T2: CREATE Order O2
~~~

Both threads can observe "key not found," because a read-only **MATCH** is not an exclusive reservation mechanism. Checking in a cache or separate **MATCH** query and then creating the node in another transaction creates a **race condition**. Even if the user clicks once, gateways and workers can deliver two copies.

The solution is to **MERGE the request node** under a **uniqueness constraint**, verify the fingerprint, and write the business result **in the same transaction**. While the first transaction creating the key is active, Neo4j's constraint and locking protect against committing two nodes with the constrained key.

### 6.2. Minimal Graph Model

~~~mermaid
flowchart LR
  R["DemoAppRequest<br/>tenantId, operation, requestKey<br/>fingerprint, orderId"] -.-> O["DemoAppOrder<br/>tenantId, orderId<br/>status, amountMinor"]
  C["DemoAppCustomer<br/>tenantId, customerId"] -->|"DEMO_APP_PLACED"| O
~~~

**DemoAppRequest** is the record tracking one **API intent**, while **DemoAppOrder** is the domain entity. A reference relationship can be stored if needed; this simple example just uses the **orderId** property to look up the written result.

For the write steps inside the same transaction:

1. **MERGE request guard** by key **(tenantId, operation, requestKey)**.
2. **ON CREATE SET** fingerprint and **candidateOrderId** on first creation.
3. Read the stored fingerprint; if it differs from the current request, **throw** and roll back.
4. **MERGE Order** by **(tenantId, orderId)** taken from the request guard.
5. **ON CREATE SET** initial status and data; do not re-trigger side effects on replay.
6. Commit **both the request guard and the Order** together.

If the transaction fails between step 2 and step 5, both roll back. If commit succeeds but the client loses the response, retrying with the same key finds the guard and the original **orderId**.

### 6.3. Java Driver Example: Retry-Safe Order Creation

The snippet below illustrates the modern Neo4j Java Driver. Assume the constraints from section 3 are already created; **the fingerprint must be computed server-side from the validated payload**. Set the database name to match your test environment.

~~~java
import java.util.Map;
import java.util.UUID;
import org.neo4j.driver.Driver;
import org.neo4j.driver.SessionConfig;

public final class DemoOrderWriter {

    public static String createOrder(
            Driver driver,
            String dbName,
            String tenantId,
            String requestKey,
            String fingerprint,
            String customerId,
            long amountMinor) {

        if (tenantId == null || tenantId.isBlank()
                || requestKey == null || requestKey.isBlank()
                || fingerprint == null || fingerprint.isBlank()
                || customerId == null || customerId.isBlank()
                || amountMinor < 0) {
            throw new IllegalArgumentException("Invalid order request");
        }

        // Generated once per Java invocation, outside the retryable callback.
        String candidateOrderId = UUID.randomUUID().toString();

        try (var session = driver.session(
                SessionConfig.forDatabase(dbName))) {

            return session.executeWrite(tx -> {
                var gate = tx.run("""
                    MERGE (r:DemoAppRequest {
                      tenantId: $tenantId,
                      operation: 'CREATE_ORDER',
                      requestKey: $requestKey
                    })
                    ON CREATE SET
                      r.fingerprint = $fingerprint,
                      r.orderId = $candidateOrderId,
                      r.createdAt = datetime()
                    RETURN r.fingerprint AS storedFingerprint,
                           r.orderId AS storedOrderId
                    """, Map.of(
                        "tenantId", tenantId,
                        "requestKey", requestKey,
                        "fingerprint", fingerprint,
                        "candidateOrderId", candidateOrderId
                    )).single();

                if (!fingerprint.equals(
                        gate.get("storedFingerprint").asString())) {
                    // API layer should map this to HTTP 409 Conflict.
                    throw new IllegalArgumentException(
                        "Idempotency key reused with different payload");
                }

                // Important: use the stored ID, never the retry's new ID
                // if this key already existed.
                String orderId = gate.get("storedOrderId").asString();

                var order = tx.run("""
                    MERGE (o:DemoAppOrder {
                      tenantId: $tenantId,
                      orderId: $orderId
                    })
                    ON CREATE SET
                      o.customerId = $customerId,
                      o.amountMinor = $amountMinor,
                      o.status = 'CREATED',
                      o.createdAt = datetime()
                    RETURN o.orderId AS orderId
                    """, Map.of(
                        "tenantId", tenantId,
                        "orderId", orderId,
                        "customerId", customerId,
                        "amountMinor", amountMinor
                    )).single();

                return order.get("orderId").asString();
            });
        }
    }
}
~~~

**Idempotency explanation:**

- **requestKey** is uniquely constrained by tenant and operation. Two concurrent requests with the same key cannot commit two different request guards.
- **fingerprint** allows replaying the result for equivalent payloads and rejecting modified payloads.
- **r.orderId** is set in **ON CREATE**, so an HTTP retry after commit still uses the original ID even though Java generated a new **candidateOrderId**.
- **MERGE Order** under its constraint guarantees the same **orderId** will not create two nodes. **ON CREATE SET** avoids resetting **status = CREATED** if the order has moved to another state.
- Both Cypher statements run inside **a single executeWrite transaction**, preventing a "key saved but order not committed" state on failure between statements.

**Scope of example:** the method returns **orderId** and omits the HTTP controller, tenant auth, canonical fingerprinting, outbox, cart logic, or storing the full HTTP response. Production services may need to store **responseStatus**, **responseBody/responseReference**, and timestamps to replay the exact API contract.

If order creation must link to an existing Customer, the **same transaction** must also **MATCH customer** and verify existence; **do not** auto-create junk customers when not found. When multiple line items, prices, taxes, relationships, or constraints are involved, all changes that must stay consistent belong in the same transaction.

### 6.4. Why Can a Constraint-Backed Statement Still Throw Errors?

A uniqueness constraint prevents **committing duplicate data**, yet it does not promise **every client succeeds on the first try** under write contention. A transaction may wait on a lock, deadlock, or hit a transient error; if data collides with another business key, the constraint raises a deterministic error. The driver can retry transient errors, while **constraint violations caused by real data conflicts** must be resolved by business rules.

Therefore, the API must distinguish:

- **Same key, same fingerprint:** replay the stored result.
- **Same key, different fingerprint:** conflict.
- **Business orderId colliding with another order:** handle business-key conflict; never silently overwrite the existing order.
- **Transient error:** bounded retry.
- **Validation error:** return input error; never blindly retry.

## 7. Retries, Ambiguous Commits, and Side-Effect Boundaries

### 7.1. Managed Transactions May Run Callbacks Multiple Times

The Java Driver's **Session.executeWrite(...)** automatically retries transactions on certain **transient** errors. Because the callback may be re-invoked, everything inside the callback must be safe to re-run.

**Never place side effects outside Neo4j** inside the callback:

~~~java
// Do not apply this pattern in production:
session.executeWrite(tx -> {
    tx.run("CREATE (:DemoAppOrder {orderId: $id})", params)
      .consume();
    paymentGateway.charge(card, amount); // Does not roll back with Neo4j.
    return "ok";
});
~~~

If Neo4j rolls back and the driver retries, **charge** may have already executed in the payment system. If Neo4j commits yet the response is lost, the client may resend the API call and invoke **charge** again. A Neo4j transaction only provides ACID over changes inside that database.

### 7.2. Business-Level "Exactly Once" Requires Additional Design

You cannot rely solely on a promise of "each callback runs once" over an unreliable network. A common implementation:

1. Within the order-creation transaction, simultaneously write an **outbox event** with a **unique eventId**.
2. After commit, a worker reads pending events and dispatches them to the external system.
3. The worker may resend after a timeout, so the receiver **must also support idempotency keys/eventIds**.
4. The worker updates delivery status, logs, and bounds retries, moving to dead-letter if needed.

Example of an event derived from a resolved order ID (executed in the **same transaction** that creates the order):

~~~cypher
CREATE CONSTRAINT demo_app_outbox_event_unique IF NOT EXISTS
FOR (e:DemoAppOutboxEvent)
REQUIRE e.eventId IS UNIQUE;
~~~

~~~cypher
// Runs inside the transaction where $orderId is already resolved,
// not in a detached transaction disconnected from Order creation.
MERGE (e:DemoAppOutboxEvent {
  eventId: 'ORDER_CREATED:' + $tenantId + ':' + $orderId
})
ON CREATE SET
  e.tenantId = $tenantId,
  e.orderId = $orderId,
  e.eventType = 'ORDER_CREATED',
  e.deliveryState = 'PENDING',
  e.createdAt = datetime()
RETURN e.eventId AS eventId;
~~~

**Important:** the two snippets above serve different roles: **CREATE CONSTRAINT** is a **schema setup** step, whereas **MERGE event** must be placed inside the application's order-write transaction. Never run constraint creation inside a business transaction callback.

Even with an outbox, the worker may deliver an event and lose connection before marking it **SENT**. Thus, **duplicate delivery can still happen**; the payment/notification consumer must use **eventId** to prevent executing side effects twice. Never describe an outbox alone as guaranteeing "exactly once" across two independent systems.

### 7.3. Use Events Instead of Repeatedly Incrementing Counters

This update:

~~~cypher
MATCH (s:DemoAppStatistics {key: 'orders'})
SET s.total = s.total + 1;
~~~

may be **atomic** within one transaction, yet **not idempotent** if the same business request executes again in another transaction: the total increments twice. **Safety under concurrent writes** and **safety under replay** are two distinct requirements.

One option is treating **Order** or a uniquely keyed **OrderCreated event** as the source of truth and aggregating; another option is updating the counter **only when a new event is created**, inside the same transaction using a mechanism that detects the creation branch. Never run **MERGE Event** followed unconditionally by **SET counter = counter + 1**, because the increment still runs even when MERGE matches an existing event.

## 8. Relationship-Level Idempotency: Avoiding Duplicate Links

In a graph, duplication can occur on **nodes**, **relationships**, or both.

### 8.1. One Logical Relationship Between Two Identified Nodes

~~~cypher
MATCH (c:DemoAppCustomer {
  tenantId: $tenantId,
  customerId: $customerId
})
MATCH (o:DemoAppOrder {
  tenantId: $tenantId,
  orderId: $orderId
})
MERGE (c)-[:DEMO_APP_PLACED]->(o);
~~~

When **Customer** and **Order** are already bound by their own keys, **MERGE relationship** fits the requirement "a Customer **PLACED** an Order." Neo4j applies locking and re-checking on both endpoints when concurrent relationship `MERGE` operations do not yet see the pattern. Even so, still account for version behavior, pre-existing duplicate data, and other write paths using **CREATE**.

### 8.2. Multiple Distinct Events Between the Same Pair of Nodes

For a **VIEWED** relationship between Customer and Product, the same person can view the same product many times. If the business wants to record **each view**, do not use a single **[:VIEWED]** relationship to represent every view. A clearer model:

~~~cypher
CREATE CONSTRAINT demo_app_view_event_unique IF NOT EXISTS
FOR (v:DemoAppViewEvent)
REQUIRE (v.tenantId, v.eventId) IS UNIQUE;
~~~

~~~cypher
MERGE (v:DemoAppViewEvent {
  tenantId: $tenantId,
  eventId: $eventId
})
ON CREATE SET
  v.customerId = $customerId,
  v.productId = $productId,
  v.viewedAt = datetime();
~~~

Each **eventId** represents one view, so re-delivering the same event creates no new event node. A **different eventId** can still represent a genuinely distinct view even when Customer and Product are unchanged.

Relationships can also carry properties and certain **relationship uniqueness/key constraints** in supported Neo4j versions; choose based on semantics and edition. Do not assume "only one edge of a type is allowed between two nodes" is a default Neo4j rule.

## 9. Distinguishing Technical Duplicates from Business Duplicates

| Duplication | Example | Primary Mechanism |
|---|---|---|
| **Same request retried** | HTTP timeout followed by POST retry with same key | Idempotency key + fingerprint + stored result |
| **Two workers process same event** | Broker delivers event E10 twice | Unique eventId, consumption control |
| **Import re-run** | Re-importing customer list | Business key + constraint + MERGE |
| **True business duplicate data** | Two customer records with different IDs for the same person | Business matching/deduplication rules; cannot be inferred solely from request key |
| **Two valid operations, identical payload** | Customer intentionally places two identical orders | Must be permitted as two distinct intents with separate keys |
| **Two services create same entity** | ERP sync and API both create customer code C-101 | Normalized business key, uniqueness constraint, conflict resolution |

For example, an **identical email** does not automatically prove two customer profiles are the same entity. People may share an email or change emails over time. If records must be merged, define explicit **identity resolution rules**, edit permissions, and audit trails; never merge nodes just because one field matches.

**Technical duplicates** can usually be blocked with keys and transactions. **Business duplicates** require domain definitions and may involve probabilistic matching, manual review, or data-merge workflows.

## 10. Spring Data Neo4j: Where to Place the Transaction?

With **Spring Data Neo4j**, a service method annotated with **@Transactional** can wrap multiple repository and `Neo4jClient` operations into a single transaction when the transaction manager is configured properly:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final OrderGraphRepository orders;
    private final RequestGraphRepository requests;

    public OrderApplicationService(OrderGraphRepository orders,
                                   RequestGraphRepository requests) {
        this.orders = orders;
        this.requests = requests;
    }

    @Transactional
    public String createOrder(CreateOrderCommand command) {
        // Illustrates the transaction boundary.
        // 1. Use a uniqueness constraint for request idempotency.
        // 2. Verify the fingerprint of any existing request.
        // 3. Write Order + request result + outbox in the same transaction.
        // 4. Return the durable Order ID.
        throw new UnsupportedOperationException(
            "Implement using the domain's repositories");
    }
}
~~~

This is a **transaction boundary skeleton**, not runnable order-creation code; it requires your project's models, repositories, mappers, and retry policy. For workflows with request-key contention, **Neo4jClient** or explicit Cypher can express the **MERGE** and creation branch clearly instead of assuming **repository.save(...)** handles all idempotency automatically.

**Points to keep distinct:**

- **@Transactional** groups operations into one transaction; it **does not create uniqueness constraints**.
- **@Transactional** **does not automatically retry** deadlocks or transient errors like **Java Driver executeWrite**. Spring-level retries must be explicitly designed so **each attempt uses a fresh transaction** with bounded attempts.
- Framework-managed entity IDs must be configured properly. Never confuse a **node's internal ID** with a **business key** or **request key**.
- Self-invocation within **the same bean** may bypass the Spring transaction proxy depending on configuration.
- Never execute external side effects inside a retryable callback or service transaction without proper idempotency protection.

When using the Java Driver directly **inside an SDN-managed Spring transaction**, understand whether it participates in the same transaction or opens a separate session/transaction. Never open a second transaction and assume the whole workflow remains atomic.

## 11. Idempotency Key Retention Windows and Result Lifecycle

Storing idempotency keys **forever** inflates storage; deleting them too early causes late retries to be treated as new requests. You must define a clear **retention window**:

- How long may HTTP clients/gateways retry?
- How late can the broker redeliver an event?
- How long after payment can a customer dispute or replay a charge?
- After expiration, can old keys be reused, or must the domain still prevent duplicate effects?

For instance, if the API contract only guarantees deduplication for **24 hours**, document that policy in the API docs; for payments or critical side effects, consider **durable business keys** and longer reconciliation trails. Never drop the key → result link while supported retries can still arrive.

Separate the two lifecycles:

| Data | Role | How to Manage |
|---|---|---|
| **DemoAppOrder** | Business record | Retain per data and audit policy |
| **DemoAppRequest** | Request processing state / replay | Retain per idempotency SLA; never delete while valid retries remain possible |
| **DemoAppOutboxEvent** | Outbound event delivery | Retain until delivery/reconciliation completes and retention expires |
| **Traces/logs** | Diagnostics for one network call | May have a different retention period than idempotency records |

If request guards must be purged, ensure clients cannot reuse expired keys outside policy; for high-risk systems, keep **tombstones** or long-term business-key constraints to prevent unintended repeated effects.

## 12. Observability, Diagnostics, and Adversarial Testing

### 12.1. Verify Entity Counts After Multiple Calls

After invoking the API multiple times with the same key in a test environment:

~~~cypher
MATCH (r:DemoAppRequest {
  tenantId: $tenantId,
  operation: 'CREATE_ORDER',
  requestKey: $requestKey
})
RETURN r.fingerprint AS fingerprint, r.orderId AS orderId;
~~~

~~~cypher
MATCH (o:DemoAppOrder {
  tenantId: $tenantId,
  orderId: $orderId
})
RETURN count(o) AS orderCount;
~~~

Expect **orderCount = 1**. With the uniqueness constraint in place, there cannot be two nodes sharing **tenantId + orderId**. To detect nodes missing IDs, also check:

~~~cypher
MATCH (o:DemoAppOrder)
WHERE o.tenantId IS NULL OR o.orderId IS NULL
RETURN count(o) AS missingBusinessIds;
~~~

Expect **0** if every node-creation path enforces validation. A uniqueness constraint alone does not guarantee this.

### 12.2. Meaningful Test Cases

| Test Case | Expected Result |
|---|---|
| First call with key K, payload P | Creates exactly one order, returns stable ID |
| Resend K + P after commit | Returns **same orderId**, creates no extra order or outbox event |
| Resend K + different payload Q | Conflict; leaves original order untouched |
| Two **concurrent** requests with K + P | Ultimately only one order commits; transient errors may validly retry |
| Two requests with different keys, same payload | Two valid intents processed per domain rules |
| Response lost right after commit | Retry finds request guard and returns stored result |
| Failure between guard write and order write | Both roll back since they share one transaction |
| Broker delivers an event twice | Only one business effect, keyed by eventId |
| API receives null/blank business ID | Rejected before MERGE; no ID-less node created |

For concurrency tests, run two or more clients with the same key against a **test database**, using a synchronization barrier so requests genuinely contend. After all transactions finish, inspect **request guard**, **Order**, and **outbox event**. Never rely solely on one HTTP response to conclude no duplicates exist.

### 12.3. Metrics to Monitor

- Rate of **new / replay / conflict / invalid** requests per endpoint and tenant.
- Retry counts from transient errors, deadlocks, timeouts, or connection drops.
- Number of request guards stuck in anomalous states in the execution flow (if using a state model).
- Pending outbox events, retry counts, and external acknowledgment rates.
- Uniqueness constraint violations on business keys, distinguishing concurrency contention from real duplicate data.
- Write transaction p95/p99 latency and contention on hot nodes or keys.

Never log full payloads, payment details, or idempotency keys unnecessarily. Prefer correlation IDs and normalized fingerprints, enforcing log access controls per security policy.

## 13. Common Mistakes

1. **Using `elementId(node)` as a public `orderId`.** Internal identifiers do not replace domain identities.
2. **Using `CREATE` without constraints** for data that may be re-imported or retried. Easily creates duplicate nodes.
3. **`MERGE` across mutable properties** like status, name, or `lastSeenAt`. Once a property changes, `MERGE` stops matching the original entity.
4. **Assuming `MERGE` alone prevents duplicates under concurrent load.** Nodes need appropriate uniqueness/key constraints.
5. **Checking `requestKey` in one transaction and writing Order in another.** Creates a race window and risks half-written state.
6. **Using a payload hash as the sole request ID.** Two intentionally identical orders are still two separate intents.
7. **Letting the same key with a different payload proceed.** Can return wrong results or mutate the original order.
8. **Unconditionally resetting status inside `ON MATCH`.** An order-creation retry must never reset a paid order back to `CREATED`.
9. **Placing external side effects inside a retryable callback.** Payments/emails/webhooks may execute multiple times.
10. **Assuming an atomic counter increment is idempotent.** Business retries can still increment it twice.
11. **Using one global request key across all tenants and operations.** Causes false blocks or mislinked requests.
12. **Purging idempotency records before the retry window expires.** Old requests get processed as brand new.
13. **Assuming uniqueness also guarantees property existence.** Neo4j distinguishes uniqueness from key/existence constraints.
14. **Failing to check for existing duplicates before adding constraints.** Schema creation can fail on legacy data.

## 14. Practice Exercises

### Exercise 1 — Choosing a Stable Key

A multi-tenant SaaS allows each tenant to issue its own order code **O-100**. Design an appropriate unique key for **Order**; explain why using only **orderId** or **customer email** can fail.

### Exercise 2 — Evaluating MERGE

Explain the behavior when order **O-100** already has **status = PAID** and the program runs:

~~~cypher
MERGE (o:DemoAppOrder {
  tenantId: 'shop-a',
  orderId: 'O-100',
  status: 'CREATED'
});
~~~

Rewrite it using **MERGE on a stable key** and **ON CREATE SET**. Re-test after changing the status; identify which scenario can violate the uniqueness constraint.

### Exercise 3 — Self-Testing Idempotency-Key

In a test database, create the three constraints from section 3 and execute an API flow equivalent to the Java example in section 6:

- Send key K and payload P for the first time.
- Resend key K + payload P after the first call commits.
- Send key K + different payload Q.
- Send payload P with a new key K2.

Inspect **requestKey**, **fingerprint**, **orderId**, and the final node count. Explain why sending K + P twice represents one intent, while K2 + P can represent a new intent.

### Exercise 4 — Designing for Lost Commit Responses

The client times out right after Neo4j commits Order O-501, without receiving the HTTP body. Describe how the client resends the same key, how the server checks the request guard, detects differing payloads, and returns the stored ID. Do not use timestamps to guess the created order.

### Exercise 5 — External Side Effects

A transaction callback both creates an Order and calls **paymentGateway.charge(...)**. Identify two scenarios that can cause duplicate charges, then propose **outbox + eventId**, payment-gateway idempotency requirements, and a reconciliation mechanism.

### Exercise 6 — Event Relationships

The same Customer C-1 views Product P-1 three separate times. Why can **MERGE (c)-[:VIEWED]->(p)** lose information? Design a **ViewEvent** with a stable key that permits three distinct views while preventing duplicate delivery of a single view by a broker.

### Exercise 7 — Evaluating Latency and Contention

Twenty workers concurrently receive the same key K. Explain the roles of the uniqueness constraint, transaction locks, retries, and post-commit checks. Which metrics help pinpoint bottlenecks if p95 increases?

## 15. Takeaways

Stable identifiers are the foundation for Neo4j to know **what constitutes the same entity**; idempotency keys and fingerprints identify **what constitutes the same request**; uniqueness constraints, **MERGE**, and transactions enforce those rules safely when multiple clients write concurrently.

For write APIs, a verifiable design typically follows this chain:

**Normalize business key → validate payload → establish scoped request key → MERGE guard under constraint → compare fingerprint → write graph and outbox in one transaction → commit → return or replay stored result.**

The Neo4j Java Driver supports transactions and transient-error retries, but cannot itself guarantee that side effects outside the database occur only once. For Spring Data Neo4j, define transaction boundaries and retry policies explicitly. Ultimately, concurrency testing and **lost-response-after-commit** tests prove application-level idempotency.

### Official Neo4j Documentation

- [Cypher Manual – MERGE, uniqueness constraints, and concurrent relationship merges](https://neo4j.com/docs/cypher-manual/current/clauses/merge/)
- [Cypher Manual – CREATE and comparing CREATE with MERGE](https://neo4j.com/docs/cypher-manual/current/clauses/create/)
- [Cypher Manual – Constraints](https://neo4j.com/docs/cypher-manual/current/schema/constraints/)
- [Cypher Manual – Create constraints](https://neo4j.com/docs/cypher-manual/current/schema/constraints/create-constraints/)
- [Neo4j Java Driver Manual – Run your own transactions](https://neo4j.com/docs/java-manual/current/transactions/)
- [Neo4j Java Driver Manual – Performance recommendations](https://neo4j.com/docs/java-manual/current/performance/)
- [Spring Data Neo4j Reference – Neo4jClient](https://docs.spring.io/spring-data/neo4j/reference/appendix/neo4j-client.html)
- [Spring Data Neo4j API – Neo4jTransactionManager](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/transaction/Neo4jTransactionManager.html)
