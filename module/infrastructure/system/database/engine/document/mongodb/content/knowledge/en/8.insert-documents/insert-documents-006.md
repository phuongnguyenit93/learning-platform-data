# Designing Retryable Insert Operations Without Creating Duplicate Data in MongoDB

In real-world applications, a client may send the same data-creation request multiple times. A user clicks a button twice; a gateway retries after a timeout; a worker reprocesses a message after a restart; or the database succeeds in writing while the response is lost in transit. If every attempt runs `insertOne()` with a new random `_id`, the system can create two orders, two payment slips, or two identical jobs.

The goal of this lesson is to design **idempotent document insertion**: for the same business request, even when executed repeatedly, the system records **a single unique business outcome**. Achieving that requires designing request identity, MongoDB unique constraints, error classification, and recovery strategies when it is unknown whether the previous write succeeded.

This lesson uses MongoDB, **mongosh**, and the test database `insert_once_lab`. Examples use human-readable string IDs without assuming every application must replace ObjectId with strings. Only run write/delete commands in a lab environment you control.

## 1. Understanding the Problem: A Request Delivered Multiple Times

A typical document insert operation:

~~~javascript
db.orders.insertOne({
  _id: new ObjectId(),
  customerId: "customer-01",
  productId: "sku-001",
  qty: 2,
  createdAt: new Date()
})
~~~

Each execution generates a new `_id`, so even with identical business content, MongoDB treats them as **two distinct documents**. MongoDB does not automatically know this is a resent request.

### Lost Response Scenario

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as API
    participant M as MongoDB
    C->>A: POST /orders, request X
    A->>M: insertOne(order)
    M-->>A: Written successfully
    Note over A,C: Connection drops before client receives response
    C->>A: Resend request X
    A->>M: insertOne(order with new _id)
    M-->>A: Creates second document
    A-->>C: Success
~~~

In the diagram, the issue is not MongoDB "writing duplicate `_id`s," but the application **generating a new identity on every attempt**. When the client loses the response, it does not know whether the first attempt committed; resending is reasonable behavior. The API must take responsibility for recognizing the prior request.

### Sources of Retries

| Source | Scenario | Risk Without Deduplication |
|---|---|---|
| User | Clicking "Place Order" multiple times | Creates multiple orders |
| Client/mobile | Timeout, switching Wi-Fi/4G networks | Resends POST with unknown outcome |
| API Gateway | Retry policy on network errors | Same request hits backend multiple times |
| Worker/queue | Message redelivered after crash or missed ack | Processes same event multiple times |
| Driver | Retrying a supported write after transient errors | Must understand driver retry boundaries |
| Batch importer | Job reruns from checkpoint | Creates multiple records for the same source row |
| Webhook | Sender repeats notification | Writes multiple events/orders/payments per notice |

**The right requirement:** "The same creation intent" must not produce additional side effects when reprocessed. However, **two valid new intents** with identical payloads must still be able to create two documents. Hence, you cannot prevent duplicates simply by searching for documents where all fields match.

## 2. What Does Idempotency Mean for Document Inserts?

An operation `f` is idempotent if repeating the same input leaves the system outcome unchanged after the first successful execution:

\[
f(f(S, K), K) = f(S, K)
\]

Where `S` is the stored state and `K` is a request's identity. This models **business effect**, without necessarily claiming every invocation returns the same HTTP status code or writes only a single technical log entry.

Example with `Idempotency-Key: req-2026-0007`:

| Call | Key | Intent | Desired Behavior |
|---|---|---|---|
| 1 | `req-2026-0007` | Create order for 2 units of product A | Create exactly one order |
| 2 | `req-2026-0007` | Resend identically | Return result of the created order |
| 3 | `req-2026-0007` | Resend identically after timeout | Still do not create a second order |
| 4 | `req-2026-0007` | Change to 3 units of product A | Report **key already used with different payload** |
| 5 | `req-2026-0008` | Create a new order for 2 units of product A | Can validly create a second order |

Three necessary conditions:

1. **Stable identity:** each creation intent has an identifying key that stays constant across retries.
2. **Atomic constraint:** MongoDB prevents two concurrent executions from writing two outcomes for one identity, usually via a unique index or `_id`.
3. **Retrievable outcome:** upon receiving a repeat request, the backend reads the saved state or response and handles payload mismatches properly.

### Distinguishing "No Duplicates" from "Exact Same Response"

Preventing duplicates is the baseline guarantee. The API may also need to return **the same order code and confirmed business status** when the client retries. If you want to return the exact original response verbatim, store a response snapshot or enough stable fields to reconstruct it. Reading the current order might return a newer status (`SHIPPED` instead of `CREATED`), which is not identical to replaying the initial response even though data is not duplicated.

The API should publish a clear contract: whether replay returns the original response or the current resource state; both can make sense for different workflows.

## 3. Concepts to Distinguish

### 3.1. Retry Differs from Idempotency

**Retry** means resending upon error or uncertain outcome. **Idempotency** guarantees resending causes no unintended business mutations. Retrying without idempotency causes duplicates; idempotency makes retrying safe.

### 3.2. Unique Index Differs from Check-Before-Insert

The following snippet is **unsafe under concurrency**:

~~~javascript
if (!db.orders.findOne({ externalOrderId: "cart-123" })) {
  db.orders.insertOne({
    externalOrderId: "cart-123",
    total: 250000
  })
}
~~~

Two requests can both observe "does not exist" and both insert. Without a unique index on `externalOrderId`, both documents can be created.

A unique index enforces uniqueness directly in the database:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, externalOrderId: 1 },
  { unique: true, name: "uq_tenant_external_order" }
)
~~~

With proper data, MongoDB rejects the competing operation with a duplicate key error. **Pre-reading** can still be useful for fast responses or friendly messages, but does not replace database constraints.

### 3.3. MongoDB Retryable Writes Do Not Replace API Idempotency

MongoDB drivers support **retryable writes** in supported configurations/topologies and operation types. This mechanism lets the driver retry **the same write operation** after certain transient errors without applying that valid write twice within retryable write scope.

However:

- A client can send **two separate HTTP requests**, generating two distinct MongoDB operations.
- The API may generate a new `_id` on each HTTP request even when the business payload is identical.
- Retryable writes do not guarantee "each order is placed only once" across the whole system.
- Not all write types, topologies, or errors are retried by the same mechanism.
- Driver retries do not manage side effects outside MongoDB such as payments or sending emails.

Therefore, **business-layer idempotency** is still required even when `retryWrites=true` is enabled in the connection string.

### 3.4. At-Least-Once Delivery vs. Exactly-Once Effect

In distributed systems, transport may deliver a message multiple times (**at least once**). Idempotent design achieves the goal of **a single business effect** for a request with a stable identity. Avoid claiming absolute "exactly once" across all databases, message brokers, and external APIs without clearly defining scope, acknowledgement protocols, and failure handling.

## 4. Designing the Insert Request's Identity

This is the first decision, before choosing `insertOne()` or `upsert`.

### 4.1. Stable Business Key

If the system already has a genuinely unique business key, leverage it:

- `externalOrderId` assigned to an order by the upstream system.
- `providerEventId` of a webhook.
- `invoiceNumber` unique within a company and applicable period.
- `importBatchId + sourceRowId` for an imported record.
- `tenantId + clientRequestId` for an API creation request.

For instance, the same SKU can appear in many orders, so **`productId` is not an idempotency key for order creation**. Likewise, the same person can place two identical orders at two different times.

### 4.2. Client-Generated Key

For a POST order-creation request lacking a business code yet, the client can generate a collision-resistant key **each time a user starts a new creation intent**, such as a UUID. The client must retain that key when retrying a pending or uncertain request.

~~~http
POST /orders HTTP/1.1
Authorization: Bearer <token>
Idempotency-Key: 8e821db3-4b86-4664-9f2d-6ed23e8df13c
Content-Type: application/json

{
  "items": [
    { "productId": "sku-001", "qty": 2 }
  ],
  "shippingAddressId": "address-03"
}
~~~

`Idempotency-Key` is a common API design pattern; the server must still define scope, lifetime, payload fingerprinting, and error responses. A client-supplied key **is not proof of access authorization**; the tenant/user must be authenticated independently.

### 4.3. Uniqueness Scope

Key `req-001` from tenant A is not necessarily the same request as `req-001` from tenant B. A contract can be:

~~~text
requestIdentity =
  tenantId
  + operationScope (e.g., "POST /orders")
  + idempotencyKey
~~~

Corresponding index:

~~~javascript
db.idempotency_requests.createIndex(
  { tenantId: 1, operation: 1, requestKey: 1 },
  {
    unique: true,
    name: "uq_idempotency_scope"
  }
)
~~~

The server must obtain `tenantId` from the authenticated principal, never trusting an arbitrary `tenantId` in the body for authorization. If the scope is user-based rather than tenant-based, or a provider webhook, adjust the scope key to match the exact business boundary.

### 4.4. Payload Fingerprint

A key must not be arbitrarily reused to create different content. After authenticating and normalizing the request, the server generates a fingerprint representing **the business-determining values**:

~~~text
Idempotency identity: tenant-01 / POST /orders / req-007

Normalized payload:
  item sku-001, qty 2
  shippingAddressId address-03
  currency VND

Fingerprint:
  SHA-256(canonical representation of operation + payload)
~~~

When a request repeats a key:

- Fingerprint matches: return the saved result or an in-progress status.
- Fingerprint differs: return a conflict; do not overwrite the existing document.

**Canonicalization matters:** JSON field order, whitespace, numeric types `2`/`2.0`, item ordering, letter casing, timezones, and default values can produce different fingerprints for logically equivalent payloads. Normalize per contract before hashing; do not hash raw JSON bytes directly if the API permits multiple equivalent representations. Never include dynamic server-side values like `createdAt: new Date()` in the fingerprint.

Do not store raw payloads containing sensitive data merely for deduplication if storing the fingerprint and metadata suffices. Fingerprints do not replace permission checks/access control.

## 5. Pattern 1 — Pinning `_id` to Business Identity

This is the simplest approach for operations that **only create a single document**.

### 5.1. Setting Up Lab Data

~~~javascript
use insert_once_lab

db.createCollection("simple_orders")
~~~

In MongoDB, every document has `_id`, and regular collections have a unique index on `_id`. Instead of generating a new ObjectId on every retry, use a stable ID derived server-side from the business key, or an already stably allocated order code:

~~~javascript
const orderId = "tenant-01:client-order-007"

db.simple_orders.insertOne({
  _id: orderId,
  tenantId: "tenant-01",
  clientOrderId: "client-order-007",
  productId: "sku-001",
  qty: 2,
  payloadFingerprint: "demo-fingerprint-v1",
  status: "CREATED",
  createdAt: new Date()
})
~~~

Re-running **the same command creating `_id`** triggers a duplicate key error instead of creating a second copy:

~~~text
MongoServerError: E11000 duplicate key error ...
~~~

That provides uniqueness protection, **not yet turning the second call into a success response**. The application must read the existing document, compare fingerprints, and return the right result.

### 5.2. Duplicate Key Handling Pattern

Service logic pseudocode:

~~~text
createOrder(request):
  identity = deriveStableIdentity(request)
  fingerprint = canonicalFingerprint(request)
  document = buildOrder(identity, request, fingerprint)

  try:
    insertOne(document)
    return CREATED(document)
  catch error:
    if error is not DuplicateKey:
      propagate error

    previous = findOneByIdentity(identity)
    if previous is missing:
      return RETRYABLE_AMBIGUOUS_RESULT
    if previous.fingerprint != fingerprint:
      return IDEMPOTENCY_KEY_CONFLICT

    return REPLAY(previous)
~~~

**Do not swallow every duplicate key as success.** The duplicate error might stem from a different unique field (such as invoice number) rather than the request `_id`; look up the document by its fixed identity and verify business content.

### 5.3. When Does This Pattern Fit?

- One request creates only one document and does not need to mutate other documents.
- There is a unique, stable business key that is never wrongly reallocated.
- Results can be reconstructed from the created document.
- The document is retained long enough to recognize retries within the desired window.

If the document's `_id` is an ObjectId yet the app still needs an external key, place a unique compound index on `tenantId + externalOrderId` instead of forcing `_id` to be a string.

## 6. Pattern 2 — `upsert` with `$setOnInsert`

MongoDB supports `updateOne(filter, update, { upsert: true })`. When no matching document exists, the operation creates one; when one already exists, it can update it. To **write fields only upon creation**, use `$setOnInsert`.

### 6.1. Create Once, Send Many Times

~~~javascript
use insert_once_lab

db.createCollection("upsert_orders")
db.upsert_orders.createIndex(
  { tenantId: 1, clientOrderId: 1 },
  { unique: true, name: "uq_client_order_per_tenant" }
)

const identity = {
  tenantId: "tenant-01",
  clientOrderId: "cart-checkout-008"
}

const requestFingerprint = "demo-payload-v1-sku-001-qty-2"

const result = db.upsert_orders.updateOne(
  identity,
  {
    $setOnInsert: {
      productId: "sku-001",
      qty: 2,
      payloadFingerprint: requestFingerprint,
      status: "CREATED",
      createdAt: new Date()
    }
  },
  { upsert: true }
)

printjson(result)
printjson(db.upsert_orders.findOne(identity))
~~~

The first run can return `upsertedCount: 1`. On subsequent runs, the filter matches the document; `$setOnInsert` does not touch fields of the existing document. `matchedCount` can be 1, while `modifiedCount` is typically 0 since no effective modification occurred.

**Fingerprint verification after upsert is mandatory**: the same `clientOrderId` with a different `qty` must never silently return success as if the new request had been processed.

~~~javascript
const saved = db.upsert_orders.findOne(identity)

if (!saved) {
  throw new Error("RESULT_NOT_VISIBLE_OR_OPERATION_FAILED")
}

if (saved.payloadFingerprint !== requestFingerprint) {
  throw new Error("IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD")
}

printjson({
  orderId: saved._id,
  status: saved.status
})
~~~

In this lab, the fingerprint is an illustrative string. A real application must compute the fingerprint from the normalized payload, never accepting an arbitrary client-supplied string as proof of matching content.

### 6.2. Why Not Use `$set` During Request Replay?

~~~javascript
// NOT suitable for replaying "create once" semantics.
db.upsert_orders.updateOne(
  identity,
  {
    $set: {
      status: "CREATED",
      createdAt: new Date()
    }
  },
  { upsert: true }
)
~~~

When the document exists, `$set` still modifies its fields. A retry could overwrite a `PAID` or `SHIPPED` status back to `CREATED` and alter the creation timestamp. `$setOnInsert` avoids this bug for creation-only fields.

Similarly, `$inc: { balance: -100 }` or `$push: { events: ... }` produces **additional effects on every execution**. They do not become idempotent merely because the filter includes a key; a claim/guard mechanism is required to guarantee single business execution.

### 6.3. Race Condition Between Two Concurrent Upserts

~~~text
Request A searches by (tenantId, clientOrderId) -> not found
Request B searches by (tenantId, clientOrderId) -> not found
A attempts to create document
B attempts to create document
~~~

If there is **no unique index** on the key pair, two concurrent upserts can create two documents. With a proper unique index, two documents with the same key cannot both commit. Under certain conditions, MongoDB may resolve upsert contention by updating the document that appeared; under other conditions one request may receive **E11000**. Therefore:

1. Create the unique index before accepting traffic.
2. Filter upserts by an explicit, unique identity.
3. Use `$setOnInsert` for creation-only fields.
4. Catch duplicate keys, read back the document by identity, and verify the fingerprint.
5. Never retry infinitely; enforce bounds and handle uncertain results.

**A unique index is the ultimate necessary safeguard.** Logic that "finds first then inserts" or "upserts on non-unique fields" is insufficient.

### 6.4. `findOneAndUpdate` When Returning the Document After Upsert

~~~javascript
const doc = db.upsert_orders.findOneAndUpdate(
  {
    tenantId: "tenant-01",
    clientOrderId: "cart-checkout-009"
  },
  {
    $setOnInsert: {
      productId: "sku-002",
      qty: 1,
      payloadFingerprint: "demo-payload-v1-sku-002-qty-1",
      status: "CREATED",
      createdAt: new Date()
    }
  },
  {
    upsert: true,
    returnDocument: "after"
  }
)

printjson(doc)
~~~

This method is convenient when you want to return the newly created or existing document in one API-level call. Even so, the fingerprint must still be checked, and races/duplicate keys/timeouts must be handled similarly. In other drivers, the returned document or wrapper API may differ.

## 7. Pattern 3 — Request Ledger for Multi-Step Workflows

A "create order" action typically does more than insert into `orders`:

1. Check inventory.
2. Deduct inventory.
3. Create the order.
4. Record the request as completed.
5. Possibly emit an event to send email or process payment.

If you only enforce uniqueness on `orders._id` while each retry still runs `$inc: {stock: -2}`, you could end up with one order **but stock deducted twice**. Idempotency must cover **all business effects**, not merely the document count in the primary collection.

### 7.1. Designing the Request Ledger Collection

A request ledger entry might contain:

~~~javascript
{
  tenantId: "tenant-01",
  operation: "POST /orders",
  requestKey: "req-010",
  fingerprint: "sha256-of-canonical-order-request",
  status: "COMPLETED",
  result: {
    orderId: "order-010",
    status: "CREATED"
  },
  createdAt: ISODate("2026-05-10T08:00:00Z"),
  completedAt: ISODate("2026-05-10T08:00:01Z")
}
~~~

The fingerprint field is an illustrative string. A system may use `PENDING`, `COMPLETED`, `FAILED` across its processing lifecycle; each status must have defined semantics and a recovery mechanism if a worker dies. When a workflow commits entirely within one transaction, you can store just the `COMPLETED` record alongside the business changes.

Create the scoped unique index:

~~~javascript
use insert_once_lab

db.createCollection("request_ledger")

db.request_ledger.createIndex(
  { tenantId: 1, operation: 1, requestKey: 1 },
  {
    unique: true,
    name: "uq_request_ledger_identity"
  }
)
~~~

### 7.2. Transactions Guarantee Multiple Documents Commit Together

On a replica set or sharded cluster supporting transactions, you can group the request record, stock deduction, and order into **one transaction**. In the lab example, the product must exist first:

~~~javascript
use insert_once_lab

db.products.updateOne(
  { _id: "sku-001" },
  {
    $setOnInsert: {
      name: "Demo Product",
      stock: 10
    }
  },
  { upsert: true }
)

db.createCollection("transaction_orders")
~~~

Transaction example (run once in a replica set/sharded cluster lab):

~~~javascript
const session = db.getMongo().startSession()

const tenantId = "tenant-01"
const operation = "POST /orders"
const requestKey = "req-010"
const fingerprint = "demo-payload-sku-001-qty-2"
const orderId = "order-010"
const qty = 2

try {
  const response = await session.withTransaction(async () => {
    const txDb = session.getDatabase("insert_once_lab")

    const previous = await txDb.request_ledger.findOne({
      tenantId,
      operation,
      requestKey
    })

    if (previous) {
      if (previous.fingerprint !== fingerprint) {
        throw new Error("IDEMPOTENCY_KEY_CONFLICT")
      }
      return previous.result
    }

    const now = new Date()

    // Claim the unique identity inside the same transaction.
    await txDb.request_ledger.insertOne({
      tenantId,
      operation,
      requestKey,
      fingerprint,
      status: "COMPLETED",
      result: { orderId, status: "CREATED" },
      createdAt: now,
      completedAt: now
    })

    // Only deduct stock if sufficient, right inside the update condition.
    const stockUpdate = await txDb.products.updateOne(
      { _id: "sku-001", stock: { $gte: qty } },
      { $inc: { stock: -qty } }
    )

    if (stockUpdate.modifiedCount !== 1) {
      throw new Error("INSUFFICIENT_STOCK")
    }

    await txDb.transaction_orders.insertOne({
      _id: orderId,
      tenantId,
      productId: "sku-001",
      qty,
      status: "CREATED",
      createdAt: now
    })

    return { orderId, status: "CREATED" }
  }, {
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" }
  })

  printjson(response)
} finally {
  await session.endSession()
}
~~~

The transaction ensures the ledger entry, stock reduction, and order insert **commit together or abort together**. If stock is insufficient, the exception aborts the transaction; the `COMPLETED` ledger entry is not committed either. If a completed request is called again, the ledger lookup branch returns the prior result without deducting stock a second time.

Notes:

- **Do not run on a regular standalone node** assuming multi-document transactions are supported; an appropriate topology is required.
- When two transactions contend for the same key, neither can see the other's uncommitted record. The unique index will cause one transaction to fail with a conflict/duplicate; the service layer must handle that error by re-reading the outcome after the other transaction commits or performing bounded retries.
- `withTransaction` may retry the transaction callback on certain errors per driver/shell behavior; never call payment APIs, send emails, or trigger external side effects inside the callback.
- An unknown commit result error must be handled per the transaction API and by **looking up the ledger by key**; do not immediately create a new order.
- `writeConcern: {w: "majority"}` strengthens write acknowledgement guarantees in many deployments, but does not replace backups or business logic.
- The example uses constant keys and fingerprints for easy observation; real APIs must extract keys from authenticated requests and compute fingerprints from normalized payloads.

### 7.3. If You Want to Record Failed Outcomes Too

For example, insufficient stock: the transaction above aborts and leaves no `COMPLETED` ledger entry. Under one contract, retrying the same key after restocking **can succeed**. Under another contract, terminal business failures must be remembered so retries return the exact initial failure.

If you want to replay terminal errors as well, design how `FAILED` states and responses are recorded via transactions or a separate claim mechanism. Never record `FAILED` for transient network errors, as doing so could permanently mark an uncertain operation as failed.

## 8. When Processing Asynchronously or with External Side Effects

A MongoDB transaction **cannot commit atomically** with external systems: message brokers, payment gateways, email/SMS, or shipping services. If the DB commits and the external API call fails, or the external call succeeds before the API records status, retries can cause duplicates.

### 8.1. Transactional Outbox

The **transactional outbox** pattern writes an `outbox` document in the same transaction as the business data:

~~~javascript
{
  _id: "order-010:OrderCreated:v1",
  aggregateId: "order-010",
  eventType: "OrderCreated",
  payload: {
    orderId: "order-010"
  },
  status: "PENDING",
  createdAt: ISODate("2026-05-10T08:00:00Z")
}
~~~

~~~mermaid
flowchart LR
    API["API / command handler"] --> TX["MongoDB transaction"]
    TX --> Order["Order + request ledger"]
    TX --> Outbox["Outbox event"]
    Outbox --> Worker["Publisher/worker"]
    Worker --> Broker["Message broker / external service"]
    Broker --> Consumer["Consumer with dedupe by eventId"]
~~~

Because both are written in the same transaction, whenever the order commits, the corresponding outbox event exists too. The worker might publish an event multiple times if it crashes after sending but before marking it sent; **consumers must still be idempotent by event ID**, and the outbox must have appropriate status/retry/reconciliation handling.

### 8.2. Payment APIs Need Their Own Keys

When calling a payment gateway, the backend should use the idempotency mechanism supported by the provider, or persist a stable payment request identifier and reconcile. Deduplication inside MongoDB **does not automatically stop a provider from charging twice** if each retry calls the payment gateway with a new request code.

### 8.3. Message Queues Can Redeliver

Example message:

~~~javascript
{
  messageId: "evt-order-010",
  eventType: "OrderCreated",
  orderId: "order-010"
}
~~~

A consumer can store `messageId` in a uniquely indexed collection within the same transaction as its MongoDB mutations. If the message is redelivered, the consumer sees the processed marker and skips re-applying side effects. Never rely on in-memory "message received" state across process restarts.

### 8.4. Long-Running Jobs with `PROCESSING` Status

For workflows that cannot fit inside a short transaction, the request ledger can use:

~~~text
NEW -> PROCESSING -> COMPLETED
                  \-> FAILED / RETRYABLE
~~~

The `PROCESSING` status needs **leases/timeouts, worker ownership, attempt IDs**, and recovery mechanisms. If a worker dies, the key must not remain stuck in PROCESSING forever; yet another worker must not pick up the job via blind updates and run concurrently with the old worker. Use conditional updates on status and lease tokens (fencing) to transfer ownership. This workflow is more complex than single-document creation and must be tailored per job type.

## 9. Handling Uncertain Outcomes After Timeouts

This is the hardest part of idempotency: **a client losing the response does not mean the database did not write**.

### 9.1. Four Possibilities After a Client Timeout

| Real Situation | What Does the Client Know? | Safe Action |
|---|---|---|
| Request never reached server | Only knows timeout | Resend **same key** |
| Server received but has not written | Only knows timeout | Resend same key; server executes once |
| MongoDB committed, response lost | Only knows timeout | Read ledger/resource by key; replay result |
| Two retries running concurrently | May both wait | Unique index + conflict/in-progress handling |

You cannot infer from a timeout exception whether the operation failed or succeeded. Query by the stable identity and follow the retry contract.

### 9.2. An Illustrative API State Machine

~~~mermaid
flowchart TD
    R["POST with request key"] --> Lookup["Lookup by tenant + operation + key"]
    Lookup --> Found{"Ledger exists?"}
    Found -->|"Yes"| Compare{"Fingerprint matches?"}
    Compare -->|"No"| Conflict["409 Conflict"]
    Compare -->|"Yes, completed"| Replay["Return saved result"]
    Compare -->|"Yes, processing"| Pending["202 / 409 / Retry-After per API contract"]
    Found -->|"No"| Claim["Create/claim identity via unique index"]
    Claim --> Tx["Execute business logic"]
    Tx --> Commit["Commit + save result"]
    Commit --> Created["Return newly created result"]
    Claim -->|"Unique contention"| Lookup
~~~

In real systems, the loop-back branch needs **bounded retries, backoff, and deadlines** to avoid infinite loops when a request is actively processing or persistently failing. A dedicated endpoint like `GET /requests/{key}` lets clients poll status without repeating side effects.

### 9.3. HTTP Status Codes Are Part of the Contract

An illustrative convention:

| State | Reference Response | Meaning |
|---|---|---|
| Initial creation completed | `201 Created` | Returns the new resource's ID |
| Replay same key + payload | `200 OK` or replay original saved `201` | No new resource created |
| Old key with different payload | `409 Conflict` | Client must not reuse a key for a different intent |
| Request with same key still running | `202 Accepted` with status lookup info; or `409` with retry guidance | Do not start a second execution |
| Temporarily uncertain commit | `503`/`504` or retryable response per contract | Client retries with same key or checks status |
| Invalid input | `400`/`422` | Do not retry indefinitely with unchanged input |

These are API design choices, not HTTP statuses returned directly by MongoDB. The contract should specify key retention duration, replayable results, conflict handling, and client error handling.

## 10. TTL and Idempotency Key Retention

The ledger can grow large with traffic. Some systems retain idempotency keys only for a published window, such as 24 hours or 7 days. However, deleting a key means **the server may no longer recognize old requests afterward**.

### 10.1. Retention Based on the Retry Horizon

Ask:

- How long might a mobile app stay offline before resending?
- How long do gateways/queues retain and replay requests?
- Could business processes replay months later during imports/reconciliation?
- Does the created resource hold a business key that outlives the ledger?
- If a key expires and the request is resent, how will the system respond?

For workflows like invoices or payments, a durable unique business identity may need to last longer than a short-lived ledger window. TTL is merely a storage retention policy, not a guarantee of eternal deduplication.

### 10.2. Example TTL for a Short-Lived Ledger

~~~javascript
db.idempotency_requests.createIndex(
  { expiresAt: 1 },
  {
    expireAfterSeconds: 0,
    name: "ttl_idempotency_expiry"
  }
)
~~~

Documents with a BSON Date `expiresAt` become eligible for deletion by the TTL monitor from that timestamp onward. **TTL deletion runs asynchronously** and does not guarantee removal at the exact boundary. Do not build business assumptions like "the key exists up to exact millisecond T."

If the request is purged from the ledger while the order still retains a unique key, the unique business index continues protecting the order's existence. If both traces disappear, the same request could be treated as new after expiry. The contract must disclose this limit.

### 10.3. Do Not Auto-Delete `COMPLETED` Records Needed for Reconciliation

Before enabling TTL, check whether `orderId`, fingerprints, audit IDs, or financial transactions must be kept longer. You can archive the ledger or separate:

- **Request replay cache** with TTL.
- **Business identity** persisting for the order/transaction lifecycle.
- **Audit/reconciliation records** retained per business compliance rules.

Never place TTL on a core business collection just to "clean up keys" if it risks deleting required records.

## 11. Common Errors and How to Distinguish Them

### 11.1. Duplicate Key — `E11000`

Cause: the operation attempted to insert/modify a value violating a unique index, either `_id` or another business key.

**Handling:**

1. Identify which unique constraint was violated.
2. Look up the document by **request identity**.
3. Compare fingerprints.
4. If matched, return the saved result; if mismatched, return a conflict.
5. If no matching document exists, do not guess it was a successful replay; treat it as a data error or contended state.

### 11.2. Write Concern Timeout

The operation may have been applied, yet the desired write acknowledgement level was not received within the timeout. Do not immediately recreate the document with a new ID. Look up by key or retry with the same key per policy.

### 11.3. Network Timeout After Commit

This is the classic reason idempotency is needed. The client cannot tell whether the server never processed it or finished processing and lost the response. Check the ledger/resource by identity.

### 11.4. Validation Error

A schema-invalid document (e.g., missing required field) will not become valid on retry. Fix the input or contract; do not infinitely retry malformed requests.

### 11.5. Transaction Conflict / Unknown Commit Result

Under concurrent workloads, transactions can hit write conflicts, transient errors, or unknown commit results. Use driver-supported transaction/commit retry mechanisms with deadlines and check the idempotency ledger. Never write custom retry logic that triggers new external side effects outside the transaction.

### 11.6. Unique Index Creation Did Not Succeed

`createIndex({tenantId:1,externalOrderId:1},{unique:true})` can fail if the collection already contains duplicate data. Clean up legacy data per plan before enabling new traffic. **Never deploy code assuming a unique index exists** simply because a migration attempted to run the create command.

## 12. Anti-Patterns: Approaches That Seem Right Yet Still Create Duplicates

| Anti-pattern | Why It Fails | Alternative |
|---|---|---|
| Generating `new ObjectId()` on every HTTP retry | Two requests get different IDs | Stable business ID or unique request key |
| `findOne()` then `insertOne()`, no unique index | Two requests can both see missing | Unique index + conflict handling |
| Upserting on non-unique fields | Concurrent upserts can create two documents | Unique index covering filter keys |
| `$set` on every replay | Overwrites fields updated after creation | `$setOnInsert`, compare fingerprints |
| `$inc` stock on every retry | One order deducts inventory multiple times | Transaction + ledger or operation guard |
| Catching **every** `E11000` and returning success | Could be a collision on a different unique field | Look up exact identity and compare payloads |
| Retrying after timeout with a new key | Treats the same intent as a different order | Reuse key and look up outcome |
| Deduplicating by `hash(payload)` instead of request key | Two valid orders with identical items get merged | One request key per intent, fingerprint to validate reuse |
| Storing keys only in RAM | Restart wipes processed request history | Durable ledger / unique index in MongoDB |
| Deleting keys immediately after HTTP response | Client loses response, retries as a brand-new request | Retention matching the retry horizon |
| Trusting client-sent key as authorization | User could guess another tenant's key | Authenticate/authorize and scope identity server-side |
| Sending email/payment inside transaction callback | Callback can retry and repeat side effects | Outbox/idempotent consumer, provider keys |
| Returning "failed" immediately on network timeout | Actual commit state is unknown | Check state, bounded retry with same key |
| Preventing duplicates with single-process locks | Multiple instances/workers do not share locks | Durable database constraints |

### Bad Example: Using Payload Hash as the Sole Identity

~~~javascript
// Wrong if two customers or one customer is allowed to buy the same cart twice.
const orderId = hash(customerId + JSON.stringify(items))
~~~

A valid new ordering intent can have the exact same cart. Fingerprints check whether **the same key was reused with different content**; identity distinguishes separate **intents**.

### Bad Example: Checking Stock Separately Before Inserting

~~~javascript
// Illustrates a logic bug; do not use for real order creation.
const p = db.products.findOne({ _id: "sku-001" })
if (p.stock >= 2) {
  db.products.updateOne(
    { _id: "sku-001" },
    { $inc: { stock: -2 } }
  )
  db.orders.insertOne({ productId: "sku-001", qty: 2 })
}
~~~

Two requests can both read `stock: 2` and both deduct; a retry can deduct twice. At minimum, updates need a condition like `stock: {$gte: 2}` and checking `modifiedCount`; if creating an order simultaneously is required, use a transaction/ledger or an equivalent consistent workflow.

## 13. End-to-End Service API Design

Suppose endpoint `POST /orders` has the contract:

~~~text
Input:
  Authorization token
  Idempotency-Key
  items, shippingAddressId

Identity:
  tenantId from auth
  operation = "POST /orders"
  requestKey from header

Fingerprint:
  canonical payload with defined schema/fields

Output:
  orderId, creation status
  replay per policy
  conflict if same key with different payload
~~~

Recommended flow:

~~~text
1. Authenticate user/tenant, verify order creation permission.
2. Validate header key and business payload.
3. Normalize payload and compute fingerprint.
4. Look up result for (tenant, operation, key).
5. If already COMPLETED:
      - fingerprint differs -> 409
      - fingerprint matches -> replay result
6. If currently PROCESSING:
      - return status/retry guidance per contract
7. If not found:
      - claim identity with unique index
      - execute business write exactly once
      - record result/metadata inside transaction (if multi-doc)
8. On unique race/timeout/unknown commit:
      - re-read ledger by key, bounded retry/backoff
9. Return stable response and metrics/correlation ID.
~~~

### 13.1. Driver-Independent Handler Pseudocode

~~~text
function createOrder(authContext, key, request):
    tenant = authContext.tenantId
    operation = "POST /orders"
    validateKey(key)
    normalized = normalizeOrderRequest(request)
    fingerprint = sha256(operation + canonical(normalized))

    result = findRequest(tenant, operation, key)
    if result exists:
        if result.fingerprint != fingerprint:
            return HTTP 409
        if result.state == COMPLETED:
            return replay(result.savedResponse)
        return inProgressResult()

    try:
        return performOneBusinessTransaction(
            tenant, operation, key, fingerprint, normalized
        )
    catch DuplicateKey or RetryableConflict:
        return resolveByReadingSameRequestIdentity()
    catch UnknownCommitResult:
        return resolveByReadingSameRequestIdentityOrRetrySafely()
~~~

Note: checking the ledger first is only a **fast path**. Correctness comes from the unique constraint and transaction/claim at execution time. Two requests can both miss the ledger before either creates it.

### 13.2. Preventing Duplicates Across Multiple Instances

If the API runs 10 replicas behind a load balancer, a retried request may hit a different instance. In-memory `Map<key,result>`, `synchronized`, or per-process mutexes are insufficient. Constraints inside MongoDB serve as the shared coordination point across all instances. Redis locks or other distributed systems can assist, but do not eliminate the need for unique database state and crash recovery.

### 13.3. Protecting Data and Resources

Idempotency keys and ledgers also require:

- Bounding key length/size, key creation rate, and concurrent in-flight requests.
- Defining retry deadlines and ledger cleanup mechanisms.
- Never using keys as unauthenticated routing paths/authorization indices.
- Avoiding storing sensitive raw payloads in the ledger when hashes and metadata suffice.
- Rate-limiting against flooding with many distinct keys per user/tenant.
- Controlling what information is returned if a key is guessed or tested across accounts.

Idempotency does not replace anti-spam, quotas, or resource authorization checks.

## 14. Lab: Observing a Creation Request That Writes Only One Document

This lab focuses on a single document to clearly contrast regular inserts, unique IDs, and upserts.

### Step 1 — Create Collection and Unique Index

~~~javascript
use insert_once_lab

db.createCollection("lab_orders")

db.lab_orders.createIndex(
  { tenantId: 1, requestKey: 1 },
  { unique: true, name: "uq_lab_order_request" }
)
~~~

If the collection already exists from an earlier session, `createCollection` may report namespace exists. Use a fresh lab name when restarting, and never drop collections outside test data.

### Step 2 — Initial Creation

~~~javascript
const filter = {
  tenantId: "lab-tenant-1",
  requestKey: "create-order-001"
}

const fingerprint = "product-A|qty=2|currency=VND"

const first = db.lab_orders.updateOne(
  filter,
  {
    $setOnInsert: {
      productId: "product-A",
      qty: 2,
      currency: "VND",
      payloadFingerprint: fingerprint,
      createdAt: new Date()
    }
  },
  { upsert: true }
)

printjson(first)
~~~

### Step 3 — Resending the Same Request

Run the `updateOne` operation again with **the same filter and same fingerprint**:

~~~javascript
const again = db.lab_orders.updateOne(
  filter,
  {
    $setOnInsert: {
      productId: "product-A",
      qty: 2,
      currency: "VND",
      payloadFingerprint: fingerprint,
      createdAt: new Date()
    }
  },
  { upsert: true }
)

printjson(again)
printjson(db.lab_orders.findOne(filter))
print(db.lab_orders.countDocuments(filter))
~~~

The document count for this identity stays **1**; the existing document's `createdAt` is not overwritten by `$setOnInsert`.

### Step 4 — Testing the Same Key with Different Content

Suppose a new request tries to change `qty` to 3 while reusing the old key:

~~~javascript
const requestedFingerprint = "product-A|qty=3|currency=VND"
const saved = db.lab_orders.findOne(filter)

if (saved.payloadFingerprint !== requestedFingerprint) {
  print("IDEMPOTENCY_KEY_CONFLICT: do not create another order")
}
~~~

In a service, return `409 Conflict` (or equivalent error contract). Do not insert a new document or modify `qty` on the existing document.

### Step 5 — Same Payload, New Creation Intent

~~~javascript
const another = db.lab_orders.updateOne(
  {
    tenantId: "lab-tenant-1",
    requestKey: "create-order-002"
  },
  {
    $setOnInsert: {
      productId: "product-A",
      qty: 2,
      currency: "VND",
      payloadFingerprint: fingerprint,
      createdAt: new Date()
    }
  },
  { upsert: true }
)

printjson(another)
~~~

This time a **valid new order** can be created: the changed key expresses a different intent despite the identical payload.

### Step 6 — Inspecting Indexes and Queries

~~~javascript
db.lab_orders.getIndexes()

db.lab_orders.find({
  tenantId: "lab-tenant-1",
  requestKey: "create-order-001"
}).explain("executionStats")
~~~

With just a few documents, the query planner may choose a simple scan. As data grows, the appropriate index makes key lookups efficient and enforces the uniqueness constraint. Most importantly in this lab, verify that **no two documents share the same unique key**.

## 15. Advanced Practice: Simulating Timeouts and Concurrency

Design an order-creation API or event-ingestion job, and test the following scenarios in an **isolated environment**:

| Scenario | How to Simulate | Expected Outcome |
|---|---|---|
| Sequential retries | Send POST with same key 5 times | One order, stable replay responses |
| Concurrent retries | Send 20 requests with same key simultaneously | One business effect; remaining requests cleanly receive replay/wait/handled conflict |
| Key reuse with mismatched payload | Send `qty=2` then `qty=3` with same key | Conflict; original order unmodified |
| Two valid intents with identical content | Use two distinct new keys, identical payload | Two orders if business rules allow |
| Lost response after commit | Simulate network drop after DB commit | Client retries with same key, no new order created |
| Primary failover | Test only in a lab replica set | Driver/handler retries and checks status accurately |
| Transaction with low stock | Two orders competing for 1 item with low stock | No negative stock, no duplicate stock deductions |
| Worker crash mid-processing | Kill lab worker at controlled checkpoint | Job recovers without double effects |
| Consumer receives event twice | Publish same eventId twice | Consumer applies effect only once |
| Expired ledger | Set up expiry scenario in lab | Post-expiry behavior follows contract without promising infinite dedupe |

### Observations to Record

- Document count per unique request identity.
- Order count and stock before/after retry rounds.
- Frequency of `DuplicateKey`, transaction conflicts, retries, and request replays.
- p95/p99 latency when 20 requests share one key or span many keys.
- Ledger state after errors/timeouts.
- Correlation IDs, redacted/masked request keys if sensitive, and order IDs in logs.

Crucially, **verify all downstream effects**. Seeing `countDocuments({requestKey}) === 1` is not enough if inventory was deducted twice or email was sent three times.

## 16. Estimating Storage Footprint of a Request Ledger

A system handles 100 order-creation requests/second, retaining keys for 24 hours:

~~~text
Request ledger entries per day:
100 x 60 x 60 x 24 = 8,640,000

Assuming each record + index uses 1 KiB on average:
8,640,000 KiB ≈ 8.24 GiB/day
~~~

This is an **illustrative estimate**, not exact WiredTiger storage footprint. BSON size, indexes, compression, storage pre-allocation, replication, journal, and backups all change the real number. If retained for seven days, document volume grows much larger before TTL removes entries.

Therefore, you should:

1. Estimate the retry horizon based on clients/queues.
2. Decide between storing minimal responses or full verbatim snapshots.
3. Measure footprint and growth rate in a realistic environment.
4. Track metrics on TTL backlog, archiving, and replay rates.
5. Consider durable unique business identities to protect critical workflows after short-lived ledger entries expire.

Do not delete keys immediately after responding just to save disk space; lost-response incidents happen at that exact moment.

## 17. Design Decisions by Workflow Type

| Insert Workflow | Suitable Identity | Typical Pattern | Notes |
|---|---|---|---|
| Creating records from an import source | `sourceSystem + sourceRecordId` | Unique compound index + `$setOnInsert` upsert | Rerunning the full batch generates no duplicates |
| Receiving provider webhooks | `provider + eventId` | Unique event inbox, idempotent consumer | Verify provider signature before processing |
| Creating orders from checkout button | `tenant/user + requestKey` | Request ledger + unique order + stock transaction | Replay results, handle timeouts and conflicts |
| Creating invoice from an order | `tenant + orderId + invoiceType` | Unique business key | Prevent creating multiple invoices for one obligation |
| Registering accounts | Normalized email or external identity per contract | Unique index + validation | Email is not always an immutable identity |
| Creating file-processing jobs | `tenant + fileUploadId + processingType` | Unique job identity + status/lease | Worker restarts do not spawn a second job |
| Recording financial transactions | Durable business transaction ID | Ledger, transaction/outbox, reconciliation | Never purge dedupe traces prematurely |

Each row must define what qualifies as "a new intent." For instance, a file may intentionally be reprocessed with a newer algorithm version; in that case `processingType` or `generation` must be part of the identity if business rules permit generating new results.

## 18. Pre-Production Checklist for Creation Features

- [ ] Clearly defined **one creation intent** versus **one retry**.
- [ ] Request key stays stable across all retries, yet changes when the user starts a new intent.
- [ ] Identity is scoped by authenticated tenant/user/operation.
- [ ] Unique index or `_id` enforces uniqueness in the database.
- [ ] Verified unique index creation migration actually succeeded with no pre-existing duplicates.
- [ ] Canonical fingerprint detects key reuse with differing payloads.
- [ ] Initial creation data uses `$setOnInsert` or stable-key insert, never overwriting on replay.
- [ ] Duplicate keys are classified by index, never unconditionally swallowed as success.
- [ ] Timeouts/unknown commits are handled via key lookup or bounded safe retries.
- [ ] Multi-document MongoDB mutations within one workflow use transactions/guards to guarantee consistency.
- [ ] External side effects use outbox/idempotent consumers or provider keys.
- [ ] Clear HTTP contract exists for created, replay, processing, key conflict, and retryable errors.
- [ ] Key retention matches the retry horizon; post-TTL behavior is understood.
- [ ] Tested under concurrent requests, network faults, crashes, and message replays.
- [ ] Metrics track replays, duplicate keys, transaction retries, and actual business effects.
- [ ] Request ledger avoids storing or logging excessive sensitive data.

## 19. Review Questions

**1. Is `insertOne()` with a new ObjectId on every retry idempotent?**

No. Each call creates a document with a different `_id`. You must use a stable request identity or a unique constraint on a business key.

**2. Can running `findOne()` before inserting prevent duplicates?**

Not under concurrency. Two requests can both observe "not found." You need a unique index and contention error handling.

**3. Why is `$setOnInsert` better than `$set` when replaying creation operations?**

Because `$setOnInsert` only sets fields when an upsert actually inserts a new document, leaving existing documents untouched. `$set` can overwrite status or `createdAt` during retries.

**4. Is a unique index alone enough for deducting inventory and creating an order?**

No. A unique index can prevent two orders with the same key, but cannot stop code outside a transaction from deducting stock multiple times. You need a transaction or synchronized business-effect mechanism.

**5. Why must fingerprints be compared?**

To avoid silently treating the same key with different content as a valid replay. One key represents one defined intent.

**6. If MongoDB returns E11000, should you always return success?**

No. E11000 might come from another unique field or an old key reused with a wrong payload. Look up the exact identity and verify saved content.

**7. Do retryable writes solve two HTTP POST requests with identical content?**

No. The driver retries a single write operation per its protocol rules; two HTTP POSTs can issue two separate business operations. API-level idempotency is required.

**8. Does a client timeout prove the database did not write?**

No. The write may have committed while the response was lost. Clients must keep the key and backends must retrieve the outcome.

**9. Why are different keys needed when the same customer intentionally places two identical orders?**

Because two orders represent two distinct intents. Using payload hashes as identities would wrongly merge them; each intent needs its own request key.

**10. Does an expiring ledger TTL still guarantee eternal deduplication?**

No. The system must document its deduplication time window and may retain permanent unique business identities longer.

**11. Does a MongoDB transaction guarantee an email is sent only once?**

No. Email is an external side effect. Use an outbox and worker/consumer idempotency mechanisms.

**12. How do you handle two requests with the same key hitting two different API instances?**

Both access the shared unique index/request ledger in MongoDB. One request succeeds while the other reads back the result or handles conflict/in-progress status; per-instance in-memory locks are insufficient.

## 20. Conclusion

Designing retryable insert operations requires identifying **business intent** through a stable key, enforcing **unique constraints** as a database safeguard, and **retrieving outcomes** on repeated requests or timeouts. For a single document, pinning `_id` or upserting with `$setOnInsert` is often enough. For workflows spanning multiple documents, inventory, events, or external services, you need a request ledger, transactions, an outbox, and participant idempotency.

The golden rule: **retrying with the same key may only repeat looking up or completing the outcome of one intent; it must never create a new intent or trigger extra unintended side effects**. Every data-creation feature should be tested under resent requests, concurrent execution, and lost responses after commit before being considered production-safe.
