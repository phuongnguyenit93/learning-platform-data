# Duplicate-Processing Prevention Keys via Business Request IDs in MongoDB

In real-world systems, **a single business request can arrive at the server multiple times** even though the user intended only one action. For example, a customer clicks "Place Order," the application creates the order successfully, yet the HTTP response is lost; the browser, API gateway, or worker resends the request. If the backend creates a new order upon every receipt, the system produces **duplicate orders**, potentially triggering repeated inventory holds, double charges, or duplicate notifications.

MongoDB provides building blocks to prevent this situation: **unique indexes**, **single-document atomic writes**, **upserts**, **conditional updates**, **transactions** when multiple documents must change together, and coordination patterns with queues/events. However, MongoDB does not automatically know when two HTTP requests represent "the same business intent." The application must supply a **stable request identifier** and design an explicit replay contract.

This lesson moves from concurrency hazards to concrete implementation patterns:

- Attaching a **requestId/idempotency key** to a business intent and reusing that key across retries.
- Using a **unique compound index** so two records for the same request cannot be created within the same scope.
- Handling **two concurrent requests** without relying on "find first, insert later."
- Distinguishing requests that are **COMPLETED**, **PROCESSING**, failed, and **same key with a different payload**.
- Combining **transactions, outboxes, leases, and downstream deduplication** when business logic is complex.
- Understanding the limits of **retryable writes**, **TTL**, and "exactly once" claims.

Examples use **mongosh**, followed by **MongoDB Java Sync Driver** and **Spring Data MongoDB**. All write operations target a test database only; do not run them on production collections without a proper data and index management plan.

## 1. Why are retried requests normal?

A processing sequence can unfold as follows:

~~~text
User                    Backend                  MongoDB
  |                        |                       |
  | POST /orders           |                       |
  | requestId=R-100        |                       |
  |----------------------->| insert order          |
  |                        |---------------------->|
  |                        |<--- write succeeded --|
  |                X-------|                       |
  | Network response lost  |                       |
  |                        |                       |
  | POST /orders again     |                       |
  | requestId=R-100        |                       |
  |----------------------->|                       |
  |                        |                       |
~~~

At retry time, the client **does not know** whether the backend's first write succeeded. If the server simply generates a new order ID and inserts again, two orders can end up representing the same placement intent.

Common sources of duplicate requests:

1. Client retries on timeout, connection drop, or 5xx responses.
2. Users clicking multiple times because they have not seen a result yet.
3. API gateways/proxies retrying according to retry policies.
4. Message brokers redelivering an unacknowledged message.
5. Worker crashes after writing successfully but before recording completion.
6. Sync systems replaying older events after reconnecting.

Retries should not be treated as an abnormal error to eliminate entirely. In distributed systems, **designing for safe retries** is usually far more practical than trying to guarantee a request arrives only once.

## 2. What is idempotency, and what does "no duplicate processing" mean?

An operation is **idempotent** when executing the same request again produces no additional business effects beyond the expected outcome of the first valid execution.

For example, for a request with requestId **R-100**:

- First call: creates **one** order O-100.
- Second call with the same requestId and same contents: **does not create a second order**.
- Third call: still refers to **the exact same order O-100**.

This **does not mean every HTTP response must return the exact same status code**. An API may return **201 Created** on the first call and **200 OK** on retry, or replay the recorded response verbatim. What matters is a clear API contract and **never duplicating business effects**.

### 2.1. Distinguishing three concepts

| Concept | Meaning | Example |
|---|---|---|
| **At-most-once effect** | A business effect must not occur more than once | One request ID creates at most one order |
| **At-least-once delivery** | System may deliver a request/message multiple times to improve completion | Broker redelivers a message until acked |
| **Exactly-once business outcome** | Business outcome is neither duplicated nor lost on failure | A payment is genuinely recorded exactly once |

Unique indexes limit **the number of records sharing a key in a collection**, yet do not automatically guarantee that an email, external payment gateway charge, or change in another system happens only once. Achieving end-to-end guarantees requires coordinating all participating components.

### 2.2. Which key identifies "one request"?

Common candidates:

- **Idempotency-Key** generated by the client for an action and kept constant across retries.
- **clientRequestId** generated in mobile/frontend when the user initiates an action.
- **orderReference** or **paymentInstructionId** as a business identifier issued by the source system.
- **eventId** of a message/event emitted once and potentially redelivered.
- **externalTransactionId** returned by a payment partner.

What matters is not the field name, but **uniqueness within the defined scope** and **stability across retries of the same action**.

A fresh random UUID generated by the backend **on every incoming retry** does not distinguish duplicate requests: each retry gets a different key, so the unique index cannot stop new records from being created.

## 3. Designing the requestId contract

Before writing code, lock down the rules:

1. **Who issues the key?** Frontend, source system, gateway, or backend on initial receipt?
2. **When is it generated?** Once per **single business intent**, prior to operations that may retry.
3. **Uniqueness scope?** System-wide, per tenant, per merchant, or per operation type?
4. **Can the key be reused for a different payload?** Normally **no**.
5. **How long is the key retained?** Depends on retry window, legal terms, and business requirements.
6. **How is an in-progress state returned?** 202, 409, or per API specification.
7. **How is the completed result retrieved?** Response snapshot, businessId, or GET by requestId.

HTTP header example:

~~~http
POST /v1/orders HTTP/1.1
Content-Type: application/json
Idempotency-Key: 018f0d9a-bafd-7f32-a6e1-dc1234567890

{
  "customerId": "C-201",
  "amountCents": 250000,
  "currency": "VND"
}
~~~

When the client retries **the same order-creation intent**, it sends **the same Idempotency-Key**. When the user intentionally places **a new distinct order**, even for identical products, the client must use a new key.

### 3.1. Tenant and operation-type scope

If different tenants can independently generate the same requestId, a global key consisting only of requestId would cause tenant A to block tenant B.

You can define:

~~~text
(tenantId, requestId)
~~~

If one requestId is permitted to repeat across operation types, use:

~~~text
(tenantId, operationType, requestId)
~~~

Be deliberate: if requestId must be unique across **all endpoints of a tenant**, do not include operationType in the key, because doing so would allow key reuse across endpoints.

**Uniqueness scope is part of the business contract**, not an accidental choice when creating an index.

### 3.2. Keys must be bounded and validated

Never accept an arbitrary multi-megabyte string as requestId. Validate format, length, encoding, allowed characters, and relationship to the authenticated user. In multi-tenant systems, **tenantId must come from a trusted authentication/authorization context**, not solely from a client-supplied body field.

Do not log full sensitive tokens, card numbers, or secret payloads merely to support deduplication. RequestId can be logged if security policy allows, but never use it as a substitute for authentication.

## 4. Why does "find first, insert later" suffer from race conditions?

Error-prone approach:

~~~javascript
const existed = db.orders.findOne({
  tenantId: "T-A",
  clientRequestId: "R-100"
});

if (!existed) {
  db.orders.insertOne({
    tenantId: "T-A",
    clientRequestId: "R-100",
    amountCents: 250000
  });
}
~~~

In a single-threaded environment, this looks reasonable. However, two processes can interleave:

~~~text
Worker A                         Worker B
   |                                |
   | findOne() -> not found         |
   |                                | findOne() -> not found
   | insertOne(R-100)               |
   |                                | insertOne(R-100)
   |                                |
     Both believe they are allowed to create the order
~~~

MongoDB guarantees **single-document** write atomicity, but **does not turn a findOne followed by insertOne pair into a critical section**. Without a unique constraint, two inserts can create two documents with the same tenantId and clientRequestId.

**Rule:** enforce uniqueness via a MongoDB **unique index**, rather than relying on application-level existence checks as a concurrency barrier.

## 5. Simplest approach: a unique compound index on the business record

If a request only creates **a single order document** and has no other changes requiring atomic commit together, you can place the request key directly on the order.

Select the practice database:

~~~javascript
use idempotency_lab
~~~

Create the unique index before processing data:

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    clientRequestId: 1
  },
  {
    unique: true,
    name: "uq_orders_tenant_request"
  }
);
~~~

Meaning: **two orders documents cannot share the same (tenantId, clientRequestId) pair**. Identical requestIds across two different tenants can still coexist.

Example first order write:

~~~javascript
db.orders.insertOne({
  _id: "ORDER-100",
  tenantId: "T-A",
  clientRequestId: "R-100",
  customerId: "C-201",
  amountCents: 250000,
  currency: "VND",
  status: "CREATED",
  createdAt: new Date()
});
~~~

Resending the same request while attempting to create another document:

~~~javascript
db.orders.insertOne({
  _id: "ORDER-100-RETRY",
  tenantId: "T-A",
  clientRequestId: "R-100",
  customerId: "C-201",
  amountCents: 250000,
  currency: "VND",
  status: "CREATED",
  createdAt: new Date()
});
~~~

The second insert is rejected due to **duplicate key**, typically reported as **E11000** with code **11000**. The underlying collection still contains only **one document** for that key pair:

~~~javascript
db.orders.find({
  tenantId: "T-A",
  clientRequestId: "R-100"
});
~~~

Do not interpret E11000 as a system fault requiring endless insert retries. In idempotent design, a duplicate key usually signals that **the key was already recorded or another racing request just won**. The application must read the existing state/record, verify the payload, and return the appropriate response.

### 5.1. The unique index is the final arbiter

When two inserts race, both requests might see no record before writing. Yet the unique index ensures only **one** record with that key is accepted. Thus the application does not need an in-memory mutex to guarantee document uniqueness in MongoDB.

### 5.2. Creating a unique index on an existing collection

If a collection already holds two orders sharing `(tenantId, clientRequestId)`, creating the unique index will fail. Do not blindly delete duplicate records just to let the index build without first analyzing order statuses, payments, and related data.

When rolling out on legacy data, typically:

1. Audit duplicates using an appropriate aggregation.
2. Define rules for merging/retiring old records.
3. Stop write sources from producing new duplicates during migration.
4. Create the unique index and verify success.
5. Only afterward enable request handling under the new contract.

If you cannot build the unique index, **never claim duplicate protection is guaranteed** merely because code calls findOne().

## 6. Atomic upsert with $setOnInsert

Another way to create a record if absent is **updateOne + upsert + $setOnInsert**:

~~~javascript
db.orders.updateOne(
  {
    tenantId: "T-A",
    clientRequestId: "R-101"
  },
  {
    $setOnInsert: {
      _id: "ORDER-101",
      customerId: "C-201",
      amountCents: 250000,
      currency: "VND",
      status: "CREATED",
      createdAt: new Date()
    }
  },
  { upsert: true }
);
~~~

If no order exists with that key pair, MongoDB inserts a new document. If one already exists, the update matches the existing record and **$setOnInsert makes no changes** to it.

Operation results typically show:

- **upsertedCount = 1** when a new insert occurred.
- **matchedCount = 1** when an existing document matched.
- **modifiedCount = 0** for an update using only $setOnInsert on an already matching document.

For hands-on practice, re-run the same command with requestId R-101: observe **matchedCount** instead of the order count increasing. Even so, never treat every matched result as a "valid retry": verify that the request payload matches the original request.

### 6.1. A unique index is still needed even with upsert

**Upsert does not mean all racing upserts automatically merge when a unique index is missing**. If two concurrent requests both observe no existing record, both can create documents with the same business key if no unique constraint exists.

Therefore, the core remains:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, clientRequestId: 1 },
  { unique: true }
);
~~~

Under specific conditions, MongoDB can convert a racing upsert into an update on the document just inserted by another request. Still, never design around an expectation that **every** upsert race completes without a duplicate-key error. The application needs a branch handling the case where another process won the race.

### 6.2. Why not use $set to overwrite payload on every retry?

Unsafe example:

~~~javascript
db.orders.updateOne(
  {
    tenantId: "T-A",
    clientRequestId: "R-101"
  },
  {
    $set: {
      amountCents: 999999,
      status: "CREATED"
    }
  },
  { upsert: true }
);
~~~

If the record already exists, this operation **overwrites amount and status**. A client reusing a requestId with a changed payload could accidentally or maliciously alter a previously accepted request.

Better rules:

- Use **$setOnInsert** for immutable fields of the initial request.
- If requestId already exists, **read and compare the original data**.
- Modify business state only via dedicated operations with authorization, state checks, and atomic conditional updates.

### 6.3. Insert or upsert?

| Write approach | Advantages | Points to handle |
|---|---|---|
| insertOne + unique index | Clear semantics: first call creates, repeat hits duplicate | Catch E11000 and look up outcome |
| updateOne + $setOnInsert + upsert | Expresses "create if absent" concisely | Distinguish inserted/matched, handle races and payload check |
| findOneAndUpdate + upsert | Can return the resulting document | Pay attention to ReturnDocument and unique index |
| findOne then insertOne without unique index | Simple to write initially | **Does not prevent races** |

For simple apps creating a single document, **insertOne + unique index** is usually clearest. For flows wanting to return an existing record or create a new one, upsert can be convenient, yet all states must still be handled completely.

## 7. Never let the same requestId represent two different payloads

Suppose the first call is:

~~~json
{
  "requestId": "R-200",
  "customerId": "C-201",
  "amountCents": 250000,
  "currency": "VND"
}
~~~

A subsequent request uses **the same R-200** but amountCents = 900000:

~~~json
{
  "requestId": "R-200",
  "customerId": "C-201",
  "amountCents": 900000,
  "currency": "VND"
}
~~~

The unique index only detects **a duplicate key**, not whether the new payload matches the old payload. If the application blindly treats duplicates as success, the second caller receives a result unrelated to the amount it requested.

Therefore, add **payload consistency verification**.

### 7.1. Storing primary fields or a payload fingerprint

An idempotency record may look like:

~~~javascript
{
  tenantId: "T-A",
  operationType: "CREATE_ORDER",
  requestId: "R-200",
  requestFingerprint: "sha256:<digest-of-canonical-business-payload>",
  status: "COMPLETED",
  resourceId: "ORDER-200",
  createdAt: ISODate("2026-11-14T08:00:00Z")
}
~~~

In the example, **"sha256:<digest-of-canonical-business-payload>" is only an illustrative placeholder**, not a literal hash digest.

Another approach is storing the **business fields requiring comparison** directly—customerId, currency, amountCents, normalized line items—and comparing them when requestId appears again.

### 7.2. What is a canonical payload?

Hashing identical business content must yield the same digest regardless of JSON key ordering or formatting. For example:

~~~json
{"currency":"VND","amountCents":250000}
~~~

and:

~~~json
{"amountCents":250000,"currency":"VND"}
~~~

represent identical business data, yet their raw JSON strings differ. Hashing raw bytes without canonicalization rules can raise false "payload conflict" errors.

Define explicitly:

1. Which fields genuinely determine business intent.
2. How to normalize key ordering and arrays (with or without order semantics).
3. How to represent money: **integers in smallest currency units** or normalized decimals, avoiding arbitrary floats.
4. How to represent timestamps, timezones, nulls, and missing fields.
5. Canonicalization format versioning when schemas evolve.

A fingerprint typically includes **operationType** and critical fields. In sensitive systems, avoid putting secrets into logs; hashing does not turn sensitive payloads into safe public strings.

### 7.3. Handling matrix when requestId already exists

| Key | Fingerprint | Prior state | Reasonable response |
|---|---|---|---|
| Not present | N/A | N/A | Attempt to claim processing for the first time |
| Exists | Matches | COMPLETED | Return stored result without re-executing |
| Exists | Matches | PROCESSING | Report in-progress/pending or let client poll later |
| Exists | Differs | Any | **409 Conflict** or equivalent contract error |
| Exists | Matches | FAILED | Follow retry policy; never create a new effect if state is uncertain |

Example API response:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/json

{
  "code": "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD",
  "message": "Request ID was already used with different payload."
}
~~~

Choose HTTP status codes per your API contract; the example above illustrates a common convention, not a rule enforced by MongoDB.

### 7.4. What if payload matches but the user differs?

In multi-user systems, check permission **to access the original outcome**. Never allow a caller to read someone else's order details merely by guessing a requestId. Retrieved status and responses must be scoped by tenant, principal, or appropriate authorization boundary.

**An idempotency key is not an authorization token.**

## 8. Separating the request registry from business records

When a request involves multiple steps, use a dedicated collection to record accepted keys:

~~~javascript
db.requestResults.createIndex(
  {
    tenantId: 1,
    operationType: 1,
    requestId: 1
  },
  {
    unique: true,
    name: "uq_request_results"
  }
);
~~~

Sample document:

~~~javascript
{
  tenantId: "T-A",
  operationType: "CREATE_ORDER",
  requestId: "R-300",
  fingerprint: "sha256:<fingerprint-placeholder>",
  state: "PROCESSING",
  resourceId: null,
  createdAt: ISODate("2026-11-14T08:00:00Z"),
  updatedAt: ISODate("2026-11-14T08:00:00Z")
}
~~~

A request registry decouples **request processing state** from the business state of orders/payments:

| Registry state | Meaning |
|---|---|
| PROCESSING | Request accepted; final business outcome not yet concluded |
| COMPLETED | Outcome recorded for replay on retries |
| FAILED_RETRYABLE | Error occurred that may be retried safely under policy and guards |
| FAILED_FINAL | Request failed permanently; replay recorded failure or API error |
| UNKNOWN | External effect status unverified; reconciliation required |

**These states are an application design, not built-in MongoDB enums.** Different names may be used, provided meanings and state transitions are well defined.

### 8.1. Claiming processing rights via atomic insert

Suppose workers attempt to process the same request R-300:

~~~javascript
db.requestResults.insertOne({
  tenantId: "T-A",
  operationType: "CREATE_ORDER",
  requestId: "R-300",
  fingerprint: "fp-v1-R300",
  state: "PROCESSING",
  createdAt: new Date(),
  updatedAt: new Date()
});
~~~

The worker whose insert succeeds **wins the right to initiate** the request record. Another worker with the same key hits a duplicate key error. It must not run business logic before reading the record's state and checking ownership.

### 8.2. Re-reading upon duplicate

~~~javascript
db.requestResults.findOne({
  tenantId: "T-A",
  operationType: "CREATE_ORDER",
  requestId: "R-300"
});
~~~

If state = PROCESSING, the API can return **202 Accepted** with a tracking resource; if COMPLETED, return resourceId or stored response; if fingerprint differs, return a conflict error.

In replicated deployments, note that **write concern, read concern, and read preference** affect when freshly written records become visible. When re-reading after duplicates or ambiguous writes, choose appropriate consistency levels; do not assume a lagging secondary immediately reflects a write just accepted on the primary.

### 8.3. A registry alone does not complete business work

A worker might insert state PROCESSING and then terminate before creating the order. If the API always sees PROCESSING and has no continuation mechanism, the request gets stuck forever. Conversely, if every request seeing PROCESSING immediately re-runs, multiple workers execute duplicates.

That is why production systems need **retry/recovery, leases, or job schedulers**, not just a unique index and a state field.

## 9. Atomic conditional updates on a single document

MongoDB guarantees that **an update on a single document is atomic**. You can include the current state in the filter to perform conditional state transitions.

For example, the worker that claimed R-300 finishes successfully:

~~~javascript
db.requestResults.updateOne(
  {
    tenantId: "T-A",
    operationType: "CREATE_ORDER",
    requestId: "R-300",
    state: "PROCESSING"
  },
  {
    $set: {
      state: "COMPLETED",
      resourceId: "ORDER-300",
      updatedAt: new Date(),
      completedAt: new Date()
    }
  }
);
~~~

The filter **state: "PROCESSING"** requires the record to still be in a state eligible for completion. If another process already transitioned it to another state, **matchedCount = 0**, and the worker must reconcile instead of overwriting.

### 9.1. Do not overwrite state unconditionally

Risky operation:

~~~javascript
db.requestResults.updateOne(
  { requestId: "R-300" },
  { $set: { state: "COMPLETED" } }
);
~~~

Because the filter omits tenant/operation and does not check current state, it can update the wrong request or overwrite another worker's transition.

When designing a state machine, include **the full identifying key** and **required state/version preconditions** for the transition in the filter.

### 9.2. Checking the update result

~~~javascript
const result = db.requestResults.updateOne(
  {
    tenantId: "T-A",
    operationType: "CREATE_ORDER",
    requestId: "R-300",
    state: "PROCESSING"
  },
  {
    $set: {
      state: "COMPLETED",
      resourceId: "ORDER-300",
      updatedAt: new Date()
    }
  }
);

printjson({
  matchedCount: result.matchedCount,
  modifiedCount: result.modifiedCount
});
~~~

If **matchedCount = 0**, you cannot assume the document was updated. Another request, a recovery worker, or a prior transition may have changed state.

When multiple competing owners exist, checking state alone may be insufficient. Compare **ownerToken/leaseVersion** as well so an old worker cannot complete work after a new worker took over the lease; see the lease and fencing token section below.

## 10. One request writing multiple documents: a unique index is not enough

Suppose creating an order requires:

1. Writing a **requestResults** record.
2. Creating an **orders** document.
3. Writing an **inventoryReservations** document to hold stock.

If the three operations execute independently:

~~~text
insert requestResults  -> succeeds
insert orders          -> succeeds
insert reservations    -> network or validation failure
~~~

MongoDB does not roll back the first two documents simply because the third write failed. Single-document write atomicity **does not extend to a multi-collection transaction**.

When all three writes must either succeed together or remain invisible together, use a **multi-document transaction** if your deployment supports it and data design requires that guarantee.

### 10.1. Grouping related writes in a transaction

mongosh example on a MongoDB deployment supporting transactions (typically an appropriate replica set or sharded cluster):

~~~javascript
// Prepare unique indexes before testing transactions.
db.requestResults.createIndex(
  { tenantId: 1, operationType: 1, requestId: 1 },
  { unique: true }
);

db.orders.createIndex(
  { tenantId: 1, clientRequestId: 1 },
  { unique: true }
);
~~~

Suppose neither collection contains request R-400. In mongosh:

~~~javascript
const session = db.getMongo().startSession();
const sessionDb = session.getDatabase("idempotency_lab");

try {
  await session.withTransaction(async () => {
    const requestId = "R-400";
    const tenantId = "T-A";

    sessionDb.requestResults.insertOne({
      tenantId,
      operationType: "CREATE_ORDER",
      requestId,
      fingerprint: "fp-v1-R400",
      state: "COMPLETED",
      resourceId: "ORDER-400",
      createdAt: new Date()
    });

    sessionDb.orders.insertOne({
      _id: "ORDER-400",
      tenantId,
      clientRequestId: requestId,
      customerId: "C-201",
      amountCents: 100000,
      currency: "VND",
      status: "CREATED",
      createdAt: new Date()
    });
  });
} finally {
  await session.endSession();
}
~~~

This illustrates **writing the request record and order in the same transaction**. Callback/transaction execution may be retried by the driver based on error labels and API policy. **Never place email sending, payment gateway calls, or external tasks inside a retryable callback**: the callback can re-run, duplicating external side effects.

Environment notes:

- Multi-document transactions require a compatible MongoDB deployment and version/features; they do not apply as cross-collection transactions on an ordinary standalone mongod.
- Define write concern, transaction lifetime, resources, and operational bounds.
- A unique index blocks duplicate requests; a transaction groups related writes atomically. **The two mechanisms solve two different problems**.

### 10.2. Two transactions competing on the same requestId

Suppose A and B both try inserting request R-400 inside transactions. MongoDB's unique constraints and concurrency control will never allow both transactions to commit two documents with the same unique key. One transaction will hit **duplicate key**, **write conflict**, or a label-handled transaction error depending on timing.

The application must never treat **every transaction error as "the request never ran."** In particular, a network error during commit can leave the commit outcome uncertain, requiring a lookup by requestId to verify.

### 10.3. Storing the business response in the same transaction

If the client needs to retrieve the initial result, the idempotency document can store:

~~~javascript
{
  tenantId: "T-A",
  operationType: "CREATE_ORDER",
  requestId: "R-400",
  fingerprint: "fp-v1-R400",
  state: "COMPLETED",
  response: {
    orderId: "ORDER-400",
    status: "CREATED"
  },
  completedAt: ISODate("2026-11-14T09:00:00Z")
}
~~~

If the response holds sensitive data or is too large, store only what is needed to **reconstruct the response under current access permissions**. Storing an initial response snapshot versus returning the order's current state is an API contract choice that must be explicitly defined.

### 10.4. Transactions do not cover external side effects

MongoDB transactions cover only data operations within MongoDB's supported transaction scope. For example:

~~~text
MongoDB Transaction
  insert order
  insert requestResult
  commit

Then call Payment Provider
~~~

If the application commits and crashes before calling the Payment Provider, the order exists without payment. If it calls the Payment Provider first and the MongoDB commit fails, funds may have been charged without MongoDB recording it.

You cannot make an external payment API atomic with MongoDB by placing an HTTP call between two statements inside a transaction.

## 11. Handling ambiguous outcomes when the network drops

A tricky situation arises when **a write command reaches the server and may succeed, yet the client receives no response**:

~~~text
Client                         MongoDB
  |                               |
  |--- insert request R-500 ----->|
  |                               | Writes data
  |<---------- X -----------------|
  |      Response lost            |
  |                               |
  |  Client does not know         |
  |  whether write succeeded      |
~~~

Never conclude **"timeout means the database wrote nothing."** This is a primary motivation for designing idempotency.

### 11.1. Safe retry scenario

Suppose the request insert has a unique key. When the client/backend retries with the same key:

- If the prior record already committed and is visible, the unique index prevents a second record; the application finds the original record and responds.
- If the prior attempt did not write, the retry creates the first record.
- If the prior attempt is still running or commit is uncertain, the new operation may hit a contention error; the application performs bounded retries and state lookups.

The application must treat **durable persisted data keyed by the business key** as the source of reconciliation, not the memory of a timed-out process.

### 11.2. Retryable writes do not replace idempotency keys

MongoDB Drivers support **retryable writes** on eligible deployments. This uses driver session/transaction numbers to retry certain write commands under supported conditions without repeating the effect of the recognized command itself.

Yet the two mechanisms differ:

| Driver retryable writes | Business idempotency |
|---|---|
| Scoped to one write command and driver retry/session context | Scoped to a **business intent** spanning HTTP, workers, processes, or systems |
| Helpful for transient network errors on supported commands | Helpful for user double-clicks, gateway retries, message redelivery |
| Does not know two separate app requests represent the same order | Uses shared requestId to recognize duplicate requests |
| Does not protect external service calls after the write | Requires combining downstream idempotency/outbox |

For instance, two separate HTTP requests can create two distinct MongoDB sessions and two distinct insert commands. Even with retryable writes enabled, MongoDB cannot tell they share the same intent unless **the application supplies a stable business key**.

### 11.3. Choosing data durability levels

For critical operations like payments or orders, consider **write concern** and failover behavior. A write acknowledged below majority durability can be rolled back upon primary election in certain failover scenarios.

Example applying majority write concern on a collection when needed:

~~~javascript
db.getCollection("orders").insertOne(
  {
    _id: "ORDER-501",
    tenantId: "T-A",
    clientRequestId: "R-501",
    status: "CREATED"
  },
  { writeConcern: { w: "majority" } }
);
~~~

Choose write concern levels based on deployment topology, majority settings, latency, and durability requirements. **Majority does not give multi-service workflows exactly-once semantics**, yet builds a firmer foundation for confirming a write in MongoDB.

When re-reading after timeouts or failovers, consider read preference/read concern and required consistency. A lagging secondary may not immediately show a write just acknowledged on the primary.

## 12. When payments, emails, or messages are involved: use outbox and downstream idempotency

Suppose placing an order must trigger a payment:

~~~text
Order-creation API
    |
    v
MongoDB: order + requestResult
    |
    v
Payment Provider: charge(amount)
~~~

If the backend calls the payment gateway directly during the request and times out, it may not know whether the card was charged. Retrying the charge without a key can charge the customer twice even though MongoDB holds only one order.

### 12.1. Transactional outbox

A common pattern:

1. Within one MongoDB transaction, write **order**, **requestResult**, and the **outbox event** to be published.
2. Commit the transaction so all three records appear consistently.
3. A worker reads the outbox and dispatches the command/event to the external system.
4. The worker records dispatch status or outcome; on crash, it can resend.
5. The receiving system deduplicates by **eventId/operationId** or its own idempotency mechanism.

~~~text
                 MongoDB transaction
          +--------------------------------+
Request ->| Order + RequestResult + Outbox |
          +--------------------------------+
                          |
                        commit
                          |
                          v
                     Outbox worker
                          |
                send with operationId
                          |
                          v
                  Payment / Email / Broker
                    (dedupe same ID)
~~~

An outbox prevents "order committed yet event never created to send," provided order and outbox are written in the same transaction. It **does not make event delivery once-only by itself**: workers can resend after errors, so downstream systems need deduplication/idempotency.

### 12.2. Carrying the same key across layers

Identifier example:

~~~text
Request:      (tenantId=T-A, requestId=R-600)
Order:        ORDER-600
Outbox event: EVENT-600-CHARGE
Payment op:   CHARGE-ORDER-600
~~~

**Payment op** must stay stable when the worker retries the same charge action. If the gateway supports idempotency keys, send the same **CHARGE-ORDER-600** key across retries of that exact payment command.

Never reuse a single key blindly across **different actions** such as charge, refund, capture, or send-email if the provider scopes or retains keys differently. Each side effect needs a properly scoped unique identifier.

### 12.3. When downstream lacks idempotency support

If an external service neither allows querying by operationId nor supports duplicate-prevention keys, the system can struggle to guarantee a single effect under every lost-response scenario. You may need:

- A **reconciliation** workflow against the external system.
- An **UNKNOWN/NEEDS_REVIEW** state instead of blind infinite retries.
- An inbox/outbox layer on the downstream side if architecture permits.
- **Compensating actions** for certain business workflows.

Never claim a MongoDB unique index "solved duplicate payments" if the payment gateway can still receive duplicate requests from workers.

### 12.4. MongoDB transactions are only part of the flow

Example outbox document:

~~~javascript
{
  _id: "EVT-ORDER-600-CHARGE",
  tenantId: "T-A",
  requestId: "R-600",
  resourceId: "ORDER-600",
  eventType: "PAYMENT_CHARGE_REQUESTED",
  operationId: "CHARGE-ORDER-600",
  state: "PENDING",
  createdAt: ISODate("2026-11-14T10:00:00Z")
}
~~~

Ensure eventId/operationId uniqueness via an index or suitable `_id` convention. When a worker reprocesses an event, it must send **the exact stored operationId**, never generating a new charge key that makes downstream treat it as a separate operation.

## 13. Long-running workers: leases and fencing tokens

A request or event may take minutes to process. If worker A dies, the system wants worker B to take over. Yet if A only paused and later resumes, **both A and B could run simultaneously**, risking duplicate writes.

A common pattern is a **lease** — temporary, time-bounded processing ownership:

~~~javascript
{
  tenantId: "T-A",
  requestId: "R-700",
  state: "PROCESSING",
  ownerId: "worker-A",
  leaseUntil: ISODate("2026-11-14T10:05:00Z"),
  leaseVersion: 3
}
~~~

Fields:

- **ownerId**: worker currently granted ownership.
- **leaseUntil**: temporary processing expiration timestamp.
- **leaseVersion**: ownership version incremented whenever another worker takes over.

### 13.1. Acquiring a lease with a conditional operation

Once the deadline expires, another worker can try claiming ownership via **findOneAndUpdate**:

~~~javascript
const now = new Date();
const leaseUntil = new Date(now.getTime() + 60_000);

const claimed = db.requestResults.findOneAndUpdate(
  {
    tenantId: "T-A",
    operationType: "CREATE_ORDER",
    requestId: "R-700",
    state: "PROCESSING",
    leaseUntil: { $lte: now }
  },
  {
    $set: {
      ownerId: "worker-B",
      leaseUntil,
      updatedAt: now
    },
    $inc: { leaseVersion: 1 }
  },
  { returnDocument: "after" }
);
~~~

Because updating a single document is atomic, if multiple workers race to claim an expired lease, only the worker whose conditional update succeeds at that instant holds ownership.

**Never treat merely reading an expired leaseUntil as owning the job**; always check the result of the conditional update. Additionally, account for server/client clock considerations, processing authorization, and business TTL limits.

### 13.2. Fencing tokens stop stale workers from overwriting

After worker B receives leaseVersion = 4, worker A may wake up still holding leaseVersion = 3. Upon completion, every worker must include its **ownership version** in the filter:

~~~javascript
db.requestResults.updateOne(
  {
    tenantId: "T-A",
    operationType: "CREATE_ORDER",
    requestId: "R-700",
    state: "PROCESSING",
    ownerId: "worker-B",
    leaseVersion: 4
  },
  {
    $set: {
      state: "COMPLETED",
      resourceId: "ORDER-700",
      updatedAt: new Date()
    }
  }
);
~~~

When worker A attempts to complete with leaseVersion 3, it no longer matches the document taken over by B. This applies **compare-and-set** using state and version.

### 13.3. A crucial limit of leases

Leases and fencing tokens in MongoDB **only protect updates that check the token in systems you control**. If worker A calls an external payment API after losing its lease without fencing-token/idempotency verification, it can still trigger external side effects.

For end-to-end protection:

- Downstream must support idempotency or reject stale fencing tokens where architecture permits.
- Workers should verify current ownership before and after sensitive steps, though standalone checks cannot eliminate every external side-effect race.
- Maintain reconciliation workflows whenever external state is uncertain.

For tasks modifying only a single MongoDB document, it is much simpler: use one conditional atomic update instead of building complex leases.

### 13.4. Never resurrect FAILED arbitrarily

Suppose request R-700 is in state FAILED_FINAL because a card was declined. If a worker resets it to PROCESSING simply because a retry arrived, the system could re-execute an action the contract declared permanently failed.

A sound state machine distinguishes:

~~~text
NEW -> PROCESSING -> COMPLETED
            |
            +------> FAILED_RETRYABLE -> PROCESSING (when eligible)
            |
            +------> FAILED_FINAL
            |
            +------> UNKNOWN -> RECONCILIATION -> ...
~~~

Allowed transitions must be defined by business rules and enforced with conditional updates. **Not every 5xx, timeout, or worker crash can transition directly to FAILED_RETRYABLE** if an external side effect might already have occurred.

## 14. TTL and retention duration of deduplication keys

The requestResults collection grows with request volume. MongoDB supports **TTL indexes** to automatically delete documents once a specified expiration time passes.

For example, each request includes an **expiresAt** field:

~~~javascript
db.requestResults.createIndex(
  { expiresAt: 1 },
  {
    expireAfterSeconds: 0,
    name: "ttl_request_expiration"
  }
);
~~~

Document:

~~~javascript
{
  tenantId: "T-A",
  operationType: "CREATE_ORDER",
  requestId: "R-800",
  state: "COMPLETED",
  resourceId: "ORDER-800",
  createdAt: ISODate("2026-11-14T10:00:00Z"),
  expiresAt: ISODate("2026-12-14T10:00:00Z")
}
~~~

TTL indexes manage document storage lifecycles by timestamp, yet carry very important limitations:

1. **TTL deletion is not millisecond-accurate.** A server background thread removes eligible documents, so records can remain past expiresAt.
2. **Once the document is deleted, the unique index no longer holds that key.** An old requestId could be accepted again.
3. **TTL does not stop a worker** currently using a document as lock state.
4. TTL indexes are a data-deletion mechanism, **not a guarantee of sufficient retention for audit/legal compliance**.
5. A multi-field unique index and a TTL index on expiresAt are **two separate indexes**; TTL is not a uniqueness constraint.

### 14.1. Replay risk after key expiration

~~~text
Day 1:  requestId=R-800 -> charge succeeds
Day 2:  client timeout/retry -> deduped, not charged again
Day 31: TTL deletes requestResult
Day 40: requestId=R-800 arrives again
~~~

If relying solely on requestResult with no other business record, the backend can treat day 40 as a brand-new request and trigger a duplicate side effect.

To use TTL safely, establish an **explicit retention window contract** and supplementary safeguards if old requests can reappear, such as:

- Permanent or long-term business keys on order/paymentInstruction.
- Separate deduplication at downstream systems.
- Minimal ledger or history retained per policy.
- Rejecting overly stale requests based on timestamped tokens/events.

**Never delete critical deduplication records just to shrink collection size** if business rules must block replays longer than the TTL.

### 14.2. Choosing retention by operation type

| Scenario | Retention guidance |
|---|---|
| Preview API with no side effects | Short expiration per contract is fine |
| Creating orders | Usually requires a long-lived unique business reference or attachment to the order |
| Payments, refunds | Coordinate retention with ledgers, partners, and regulatory rules |
| Sync events replayable weeks later | Retain eventId for at least the practical replay window, with reprocessing rules |
| Request registry caching responses temporarily | Can TTL the response cache if effect uniqueness is enforced elsewhere |

There is no single optimal TTL for all domains. Distinguish **how long to cache responses for clients** from **how long a business effect must be protected against duplicate execution**.

## 15. Null, missing fields, and why unique indexes do not replace schema validation

A document missing requestId should never count as a "valid empty requestId." MongoDB indexes apply specific rules to null values and missing fields in keys. Inside a unique compound index, combinations involving missing/null entries can still collide unexpectedly.

For instance, the index:

~~~javascript
{ tenantId: 1, clientRequestId: 1 }
~~~

**does not automatically require** every order to contain tenantId and clientRequestId. If the app can insert documents lacking requestId, the system ends up with untraceable records and unexpected index collisions.

### 15.1. Enforcing required fields with $jsonSchema

For a new collection:

~~~javascript
db.createCollection("strictRequests", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "tenantId",
        "operationType",
        "requestId",
        "fingerprint",
        "state"
      ],
      properties: {
        tenantId: {
          bsonType: "string",
          minLength: 1
        },
        operationType: {
          bsonType: "string",
          minLength: 1
        },
        requestId: {
          bsonType: "string",
          minLength: 1
        },
        fingerprint: {
          bsonType: "string",
          minLength: 1
        },
        state: {
          enum: [
            "PROCESSING",
            "COMPLETED",
            "FAILED_RETRYABLE",
            "FAILED_FINAL",
            "UNKNOWN"
          ]
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});

db.strictRequests.createIndex(
  { tenantId: 1, operationType: 1, requestId: 1 },
  { unique: true }
);
~~~

Schema validation blocks missing or mistyped fields, while the unique index blocks duplicate **key values**. Both are needed when the contract requires non-null, non-empty String keys.

### 15.2. Partial unique indexes can open deduplication gaps

Suppose you create a unique index only for state = PROCESSING:

~~~javascript
db.requestResults.createIndex(
  { tenantId: 1, requestId: 1 },
  {
    unique: true,
    partialFilterExpression: {
      state: "PROCESSING"
    }
  }
);
~~~

Once a request transitions to **COMPLETED**, the document leaves the partial index subset. That allows inserting a new PROCESSING document with the exact same key, risking re-execution of an already completed request.

**If the goal is blocking the same key across its entire lifecycle**, the unique index must cover **every relevant state**, not only in-flight states. Use partial indexes only when explicit business rules define which documents participate in uniqueness.

### 15.3. Never include state in the unique key for single-use keys

This index is usually **unsuitable** for per-request idempotency:

~~~javascript
db.requestResults.createIndex(
  {
    tenantId: 1,
    requestId: 1,
    state: 1
  },
  { unique: true }
);
~~~

It permits **the same tenantId/requestId** to exist across different states—such as one PROCESSING record and one COMPLETED record. If there must be **at most one record per key**, state must not distinguish records in the unique key.

A better index for that contract is:

~~~javascript
{ tenantId: 1, requestId: 1 }
~~~

or adding operationType if the scope definition permits.

## 16. Sharded architectures and uniqueness scope

When a collection is **sharded**, uniqueness enforcement depends on the shard key configuration and MongoDB's unique index rules. On sharded collections, ordinary unique indexes must satisfy **shard key prefix** constraints in supported configurations.

For example, if idempotency is scoped by:

~~~text
(tenantId, operationType, requestId)
~~~

then the shard key and unique index must be designed together. Never assume any arbitrary compound unique index enforces global uniqueness across shards the way an unsharded collection does.

### 16.1. Questions when sharding

1. Does the **shard key** consist of fields identifying the request?
2. Does the proposed unique index include the **shard key prefix** per your server version and sharding type?
3. Do request lookup filters include enough of the shard key to **target a single shard** rather than scatter-gather?
4. Is tenant distribution skewed enough to create a hot shard?
5. Where is requestId generated, and can different producers collide?

If global deduplication is required yet the shard key cannot enforce that constraint, adjust the model or use a registry whose uniqueness MongoDB can guarantee, rather than trusting per-shard application checks.

### 16.2. Do not use default ObjectId instead of business keys

MongoDB generates a separate `_id` per document; two different inserts normally get two distinct `_id`s. That **does not stop** two orders from sharing the same requestId if requestId is not uniquely constrained.

Some designs derive a deterministic `_id` from requestId and scope, but you must ensure unambiguous encoding, zero collisions, and shard-key compatibility. A unique compound index is usually clearer for tenant/operation scoping.

## 17. Duplicate business intent with different requestIds: a key limitation

Suppose a customer sends:

~~~text
Request A: requestId=R-901, orderRef=SHOP-10001
Request B: requestId=R-902, orderRef=SHOP-10001
~~~

With a unique index only on requestId, MongoDB views these as **two distinct requests**. Yet business rules may stipulate **orderRef=SHOP-10001 may be created only once**.

Therefore, you may need an **independent unique business constraint**:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, orderRef: 1 },
  {
    unique: true,
    name: "uq_tenant_order_reference"
  }
);
~~~

Distinguish:

- **requestId** protects retries of the same client-submitted action.
- **orderRef/invoiceNumber/paymentInstructionId** protects business invariants even when a client sends a fresh request ID.

Reliable systems often need **both** when both kinds of duplication pose risks.

### 17.1. Never treat all identical payloads as business duplicates

A customer might intentionally buy the same item twice on two different days, or transfer the same amount twice. Two requests with identical payloads yet **different requestIds** are not automatically duplicates.

Do not hash payloads alone and forbid every repeated hash, as that blocks legitimate repeat transactions. Business keys must reflect **a specific intent**, not merely matching content.

## 18. Single-document atomic model for recording side effects

In some cases, all protected state fits in **a single document**. You can then check conditions and update data in one command instead of a multi-collection transaction.

For example, an inventory document:

~~~javascript
db.inventory.insertOne({
  _id: "SKU-100",
  available: 10,
  appliedRequestIds: []
});
~~~

One command reserves one unit while preventing double execution for the same requestId:

~~~javascript
db.inventory.updateOne(
  {
    _id: "SKU-100",
    available: { $gte: 1 },
    appliedRequestIds: { $ne: "R-1000" }
  },
  {
    $inc: { available: -1 },
    $addToSet: { appliedRequestIds: "R-1000" }
  }
);
~~~

The filter and update are evaluated atomically on **one document**. When two workers both reserve SKU-100 for request R-1000, only one update decrements available and appends the key, because the second no longer satisfies **appliedRequestIds: {$ne: "R-1000"}**.

### 18.1. Interpreting matchedCount

If matchedCount = 1, a valid update occurred. If matchedCount = 0, there are at least three possibilities:

- Insufficient inventory.
- Request ID already applied.
- SKU does not exist.

Never assume matchedCount = 0 always means "out of stock." Read the current state and distinguish causes when building the API response.

### 18.2. Why not store requestIds unboundedly in an array?

The **appliedRequestIds** example works only when each document handles a small, known maximum number of operations. If a SKU receives millions of requests, the array grows without bound, straining memory and document size (MongoDB enforces a BSON document size limit).

For large systems, it is usually better to store each reservation as **its own document with a unique business key** and use a transaction to update stock + reservation when cross-document atomicity is required. The single-document array example illustrates **atomicity**, not a complete inventory architecture for every workload.

### 18.3. Checking permissions and state transitions

When a reservation is cancelled, the application must know how to restore stock exactly once. Simply removing requestId from the array without state history makes cancel-then-retry-reserve flows ambiguous.

Real systems need explicit modeling for CREATE/CONFIRM/CANCEL with consistent operation or reservationIds and appropriate unique constraints; one requestId field cannot replace an entire state machine.

## 19. MongoDB Java Sync Driver: idempotent insert via unique index

In Java applications using **mongodb-driver-sync**, a clean pattern is:

1. The orders collection has unique index **{tenantId:1, clientRequestId:1}**.
2. Attempt **insertOne** for the new document.
3. On success, return the newly created document.
4. On **duplicate key 11000**, look up the order by the exact key.
5. Compare immutable business fields; if identical, return the original order; if different, throw a conflict error.
6. Never repeat order creation or downstream calls in the duplicate branch.

### 19.1. Complete Java example

~~~java
import com.mongodb.MongoWriteException;
import com.mongodb.WriteConcern;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.Date;
import java.util.Objects;

public class IdempotentOrderInsert {
    static Document createOrGet(
            MongoCollection<Document> orders,
            String tenantId,
            String requestId,
            String customerId,
            long amountCents,
            String currency) {

        Bson requestKey = Filters.and(
                Filters.eq("tenantId", tenantId),
                Filters.eq("clientRequestId", requestId)
        );

        Document candidate = new Document("tenantId", tenantId)
                .append("clientRequestId", requestId)
                .append("customerId", customerId)
                .append("amountCents", amountCents)
                .append("currency", currency)
                .append("status", "CREATED")
                .append("createdAt", new Date());

        try {
            orders.insertOne(candidate);
            return candidate;
        } catch (MongoWriteException ex) {
            if (ex.getError().getCode() != 11000) {
                throw ex;
            }

            // Treat duplicate as a retry only when finding the exact business key.
            Document existing = orders.find(requestKey).first();
            if (existing == null) {
                // Duplicate may stem from another constraint or
                // the target record is not yet visible.
                throw ex;
            }

            boolean samePayload =
                    Objects.equals(existing.getString("customerId"), customerId)
                    && Objects.equals(
                            existing.getLong("amountCents"), amountCents)
                    && Objects.equals(existing.getString("currency"), currency);

            if (!samePayload) {
                throw new IllegalStateException(
                        "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD");
            }

            return existing;
        }
    }

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI is required");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> orders = client
                    .getDatabase("idempotency_lab")
                    .getCollection("orders")
                    .withWriteConcern(WriteConcern.MAJORITY);

            Document first = createOrGet(
                    orders, "T-JAVA", "R-JAVA-001",
                    "C-301", 250000L, "VND");

            Document retry = createOrGet(
                    orders, "T-JAVA", "R-JAVA-001",
                    "C-301", 250000L, "VND");

            System.out.println(first.toJson());
            System.out.println(retry.toJson());
        }
    }
}
~~~

With **the unique index successfully built**, two calls with the same key and payload resolve to **one order**. The example stores amountCents as **Long**; never use double for money when currency units and rounding require precision.

**Important:** this code illustrates a successful insert and the **duplicate key** case. A network exception after insert can represent an **ambiguous write outcome** rather than a MongoWriteException 11000. In real APIs/jobs, add retry/re-read policies by requestId, bounded timeouts, and suitable write/read concerns as discussed in section 11.

### 19.2. Why compare payload in the duplicate branch?

If requestId R-JAVA-001 is resent with amountCents = 999999L, the unique index blocks a new insert. Yet simply returning the old order without raising a conflict can mislead the caller into thinking the new amount was accepted.

The samePayload check ensures the caller resent **the same intent for fields treated as immutable**. In production, the field list must cover all business content: line items, product options, customerId, currency, amounts, and shipping address if those determine the outcome.

### 19.3. Creating the index in Java

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.IndexOptions;
import com.mongodb.client.model.Indexes;
import org.bson.Document;

public class OrderIndexes {
    public static void ensureUniqueRequestIndex(
            MongoCollection<Document> orders) {

        orders.createIndex(
                Indexes.compoundIndex(
                        Indexes.ascending("tenantId"),
                        Indexes.ascending("clientRequestId")
                ),
                new IndexOptions()
                        .unique(true)
                        .name("uq_orders_tenant_request")
        );
    }
}
~~~

This snippet only demonstrates the index creation API. Do not call it inside **every request**; manage indexes via approved bootstrap/migrations. Creating a unique index on a collection with existing duplicates will fail and requires cleaning up historical data.

### 19.4. Handling duplicate errors by exact type

Not every **MongoException** is a duplicate key error:

- Authentication/authorization errors: cannot assume the request already exists.
- Timeout/network errors: outcome may be ambiguous, requires reconciliation.
- Validation errors: payload or schema is invalid.
- Duplicate key 11000: a unique constraint was violated; still verify **which key** collided.

When multiple unique indexes exist in practice, never catch every 11000 error and blindly return a result for the current requestId. Locating the record by exact key and verifying payload are prerequisites for treating it as a valid retry.

## 20. Spring Data MongoDB: catching DuplicateKeyException

In Spring Boot / Spring Data MongoDB projects, **MongoTemplate** inserts documents and raises **DuplicateKeyException** when a unique index is violated.

### 20.1. Entity with compound index

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.index.CompoundIndex;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("orders")
@CompoundIndex(
        name = "uq_orders_tenant_request",
        def = "{'tenantId': 1, 'clientRequestId': 1}",
        unique = true
)
public class OrderRecord {
    @Id
    private String id;
    private String tenantId;
    private String clientRequestId;
    private String customerId;
    private long amountCents;
    private String currency;
    private String status;

    // Constructor, getters, and setters added per project conventions.
}
~~~

The annotation declares the desired index. **MongoDB must actually have the index built before handling concurrent requests**. Whether Spring Data auto-creates indexes from annotations at startup depends on configuration and version; in production, explicit index migrations are standard.

### 20.2. Service handling insert and duplicate

Illustrative example assuming entity getters/setters:

~~~java
import java.util.Objects;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public class OrderCreationService {
    private final MongoTemplate mongoTemplate;

    public OrderCreationService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public OrderRecord createOrRead(OrderRecord candidate) {
        try {
            return mongoTemplate.insert(candidate);
        } catch (DuplicateKeyException duplicate) {
            Query query = Query.query(
                    Criteria.where("tenantId")
                            .is(candidate.getTenantId())
                            .and("clientRequestId")
                            .is(candidate.getClientRequestId())
            );

            OrderRecord existing = mongoTemplate.findOne(
                    query, OrderRecord.class);

            if (existing == null) {
                throw duplicate;
            }

            boolean samePayload =
                    Objects.equals(
                            existing.getCustomerId(),
                            candidate.getCustomerId())
                    && existing.getAmountCents() == candidate.getAmountCents()
                    && Objects.equals(
                            existing.getCurrency(),
                            candidate.getCurrency());

            if (!samePayload) {
                throw new IllegalStateException(
                        "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD");
            }

            return existing;
        }
    }
}
~~~

In the HTTP controller, differing payload errors can map to **409 Conflict**. When a completed request is found, the response must carry the exact existing resourceId/orderId; never generate a new ID in the response.

This snippet assumes the operation only creates one order document. If it must also reserve inventory, record payment, and emit events, apply transaction/outbox or an appropriate pattern rather than treating a single insert as sufficient.

### 20.3. Beware of overly broad catch blocks

Incorrect approach:

~~~java
try {
    mongoTemplate.insert(candidate);
} catch (Exception ex) {
    return mongoTemplate.findOne(
            Query.query(Criteria.where("clientRequestId")
                    .is(candidate.getClientRequestId())),
            OrderRecord.class);
}
~~~

This catches network errors, permission errors, mapping failures, and validation errors and treats all of them as duplicates—while **omitting tenantId scope**. It hides real failures and risks leaking another tenant's data.

Classify exceptions, check the full scoped key, enforce authorization, and return the prior result only after idempotency conditions are verified.

## 21. Managing HTTP/API states for retries

Idempotency is a contract between client and server. Illustrative convention:

| Scenario | Server action | Candidate HTTP status |
|---|---|---|
| First requestId, synchronous processing succeeds | Record result, return orderId | 201 Created |
| Retry with same requestId/payload, result exists | Return result per contract | 200 OK or stored response |
| Retry while request is still PROCESSING | Do not run business logic twice; report in-progress | 202 Accepted with tracking resource |
| Retry with same key but different payload | Reject | 409 Conflict |
| Malformed or missing required requestId | Reject before writing | 400 Bad Request |
| Deterministic non-retryable business error | Return recorded failure outcome | Appropriate business error code |
| Payment state UNKNOWN | Do not auto-recharge; require reconciliation | 202/409/5xx per contract, with lookup ID |

**MongoDB does not dictate HTTP status codes**. The table offers API design guidance; your API documentation should specify TTL, key reuse handling, in-progress behavior, and result retrieval.

### 21.1. Example response while processing

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json
Retry-After: 3

{
  "requestId": "R-300",
  "state": "PROCESSING",
  "statusUrl": "/v1/requests/R-300"
}
~~~

If a status lookup URL is provided, that endpoint must authenticate and authorize the tenant/user so knowing a requestId alone does not expose results. The `Retry-After` header hints when to poll again, not a guarantee that the worker finishes in exactly three seconds.

### 21.2. Return the original response or current state?

Suppose an order was initially CREATED and later shipped as SHIPPED. When the old order-creation request is retried:

- **Replay original response:** returns orderId and the stored CREATED status.
- **Return current state:** returns the same orderId with status SHIPPED.

Both can be idempotent regarding **order creation**, yet represent two distinct API contracts. Choose and document one clearly, especially if clients compare responses or retry based on status.

## 22. Observing and operating deduplication mechanisms

A good idempotency mechanism does not only prevent duplicates under normal load—it also reveals **which requests are stuck, which completed, and what causes repeated retries**.

Useful metrics:

| Metric | Purpose |
|---|---|
| `requests_first_seen` | Count of new request keys accepted |
| `requests_replayed_completed` | Count of retries returning completed results |
| `requests_in_progress_conflict` | Count of retries hitting in-progress requests |
| `requests_payload_conflict` | Count of same key with differing payload |
| `duplicate_key_count` | Unique index collisions related to requests |
| `requests_unknown_state` | Requests whose effect status is unverified |
| `stale_processing_count` | PROCESSING records exceeding lease or SLA |
| `reconciliation_duration` | Time spent reconciling ambiguous requests |
| `outbox_redelivery_count` | Events resent after failures |
| `downstream_duplicate_suppressed` | Duplicate commands rejected/deduped downstream |

These metric names are application instrumentation suggestions, **not built-in MongoDB metric fields**.

### 22.1. Finding stuck PROCESSING requests

Example:

~~~javascript
const threshold = new Date(Date.now() - 15 * 60 * 1000);

db.requestResults.find({
  state: "PROCESSING",
  updatedAt: { $lt: threshold }
}).sort({ updatedAt: 1 });
~~~

This identifies **candidates for investigation**, not blanket permission for workers to blindly re-run. Some requests may be awaiting an external partner and require reconciliation before retrying.

On large datasets, consider an index:

~~~javascript
db.requestResults.createIndex({
  state: 1,
  updatedAt: 1
});
~~~

This index serves status/staleness queries and **does not replace** the unique compound index protecting requestId.

### 22.2. Structured logging by request ID

Example structured log:

~~~text
traceId=tr-501
tenantId=T-A
operation=CREATE_ORDER
requestId=R-500
idempotencyOutcome=REPLAY_COMPLETED
orderId=ORDER-500
statusCode=200
~~~

Never log card numbers, tokens, full payloads, or unnecessary personal data. A single trace may span retries, or different retries may carry different traceIds: traceId usually differs across independent HTTP requests, so it is not an idempotency key.

### 22.3. Monitoring unique indexes and schema changes

When a new deployment begins requiring requestId, ensure:

- The unique index exists before opening traffic.
- Validators/write logic no longer permit documents missing the key.
- Other write paths (admin scripts, importers, batch jobs) obey the constraint.
- Legacy data migration does not break the index build.
- Conflict rates and stuck states are monitored post-rollout.

The unique index is the **final database guardrail**; application layers must still validate inputs and give callers clear feedback.

## 23. Contention scenarios to distinguish

### 23.1. Two requests with same key, same payload arriving simultaneously

~~~text
              request R-100
                 /     \
              A           B
              |           |
          insertOne    insertOne
              |           |
           SUCCESS       E11000
              |           |
          order A       read order A
              |           |
            return      return original
~~~

**Correct outcome:** at most one order is created. The request hitting E11000 returns the original result only after verifying key and payload.

### 23.2. Same key, different payload

~~~text
Request A: key=R-100, amount=100000
Request B: key=R-100, amount=900000
~~~

**Correct outcome:** the first valid request is recorded; the other must receive a conflict, **never treating both as succeeded**.

### 23.3. Different keys, same business order reference

~~~text
Request A: requestId=R-100, orderRef=SHOP-1
Request B: requestId=R-101, orderRef=SHOP-1
~~~

If orderRef is a unique business identifier, add a separate unique index on **(tenantId, orderRef)**. Otherwise, two distinct valid requestIds can still create two orders with the same source reference.

### 23.4. Request wrote successfully, response lost

When a client times out, the retry must **look up and reuse the recorded result**, never minting a new requestId for the same action. A write timeout does not prove the first attempt failed to commit.

### 23.5. Worker A loses lease, worker B takes over

To stop worker A from overwriting B's outcome, the final update must include **leaseVersion** or a fencing token in its filter. External side effects still need their own idempotency mechanism.

### 23.6. Registry purged by TTL before an old replay

Absence of a requestResult record does not prove the action never ran. Align retention windows with durable business records/ledgers or downstream operationIds.

## 24. Lab exercise: creating two competing requests with mongosh

Setup:

~~~javascript
use idempotency_lab

db.demoRequests.createIndex(
  { tenantId: 1, requestId: 1 },
  { unique: true, name: "uq_demo_request" }
);
~~~

Open **two mongosh sessions** connected to the test database. In both windows, run nearly simultaneously:

~~~javascript
db.demoRequests.insertOne({
  tenantId: "T-DEMO",
  requestId: "R-RACE-1",
  state: "COMPLETED",
  createdAt: new Date()
});
~~~

One insert succeeds while the other receives **E11000 duplicate key**, depending on server execution order. If data remains from a prior run, both may hit duplicate key; use a different requestId to test a fresh intent.

Verify document count:

~~~javascript
db.demoRequests.countDocuments({
  tenantId: "T-DEMO",
  requestId: "R-RACE-1"
});
~~~

The expected count is **1** once at least one insert succeeded. This directly observes uniqueness enforcement—not proof that every side effect in a payment system is deduplicated.

### 24.1. What happens without the index?

On a **separate** test collection without a unique index on requestId, two inserts with different auto-generated `_id`s coexist even with identical tenantId/requestId. Never **drop an index on a production collection** to test this hypothesis.

### 24.2. Testing upsert and inspecting results

~~~javascript
db.demoRequests.updateOne(
  {
    tenantId: "T-DEMO",
    requestId: "R-UPSERT-1"
  },
  {
    $setOnInsert: {
      state: "COMPLETED",
      resourceId: "RESOURCE-1",
      createdAt: new Date()
    }
  },
  { upsert: true }
);
~~~

Re-run the exact command, then inspect the document:

~~~javascript
db.demoRequests.findOne({
  tenantId: "T-DEMO",
  requestId: "R-UPSERT-1"
});
~~~

`$setOnInsert` does not overwrite the existing resourceId on retry. If the real application must return resourceId, it must **read the stored value**; never generate RESOURCE-2 and return it on retry.

### 24.3. Avoid confusing request IDs with resource IDs

A requestId represents the **creation intent**, while orderId/resourceId represents the **created outcome**. They can match in some designs, though it is not mandatory. Keeping the two concepts distinct helps APIs respond idempotently:

~~~text
RequestId:  R-UPSERT-1
ResourceId: RESOURCE-1
~~~

When the same requestId arrives again, the server returns **RESOURCE-1**—without starting a new resource-creation workflow.

## 25. Applied exercises

The exercises below focus on **concurrency thinking, atomicity, and business identifiers**, without requiring a live payment gateway. Practice on the test collections created above or trace expected outcomes.

### Exercise 1. Two workers inserting concurrently

Given the collection:

~~~javascript
db.payments.createIndex(
  { merchantId: 1, paymentInstructionId: 1 },
  { unique: true }
);
~~~

Workers A and B both insert `paymentInstructionId = "P-101"` for merchant `"M-1"`, each using a different `_id`. Answer:

1. Can two documents with that key pair coexist?
2. If one insert receives error 11000, what must happen next?
3. Should it retry the insert with a different requestId to "fix the error"?

**Guided answer:** The unique index prevents two documents with the same key pair. The duplicate caller must read and inspect the existing outcome, compare payload/state, and return the proper result. Minting a new requestId to retry the same intent breaks deduplication.

### Exercise 2. Same key, different amount

Suppose the first request is:

~~~json
{
  "requestId": "R-2000",
  "amountCents": 120000,
  "currency": "VND"
}
~~~

Subsequent request:

~~~json
{
  "requestId": "R-2000",
  "amountCents": 900000,
  "currency": "VND"
}
~~~

Choose a proper response and explain why you cannot simply return the old result while ignoring differing payloads.

**Answer:** A standard design returns **409 Conflict** with an error code indicating the key was reused with a different payload. A matching key does not prove identical intent when immutable fields differ.

### Exercise 3. Does upsert guarantee uniqueness without an index?

Two workers concurrently invoke:

~~~javascript
db.orders.updateOne(
  { tenantId: "T-1", clientRequestId: "R-3000" },
  { $setOnInsert: { status: "CREATED" } },
  { upsert: true }
);
~~~

The collection has no unique index on tenantId/clientRequestId. Explain why a race can still produce two inserts.

**Guidance:** Both workers can observe no existing document before deciding to upsert. You need a MongoDB-enforced unique index; upsert alone does not replace uniqueness constraints.

### Exercise 4. Choosing the right key scope

A multi-tenant system allows each tenant to issue `"REQ-1"`. Choose between:

~~~javascript
{ requestId: 1 }

{ tenantId: 1, requestId: 1 }
~~~

**Answer:** If requestId is unique only per tenant, use the **compound unique index (tenantId, requestId)**. Obtain tenantId from a trusted auth context. If business rules require globally unique requestIds, another key design may fit.

### Exercise 5. Why omit state from the unique key?

Given index:

~~~javascript
{ tenantId: 1, requestId: 1, state: 1 }
~~~

with unique = true. Can two documents be inserted with the same tenantId/requestId where one is PROCESSING and one is COMPLETED?

**Answer:** Yes, because the three-field keys differ. If only one document may exist for a requestId across all states, do not include state in the unique key.

### Exercise 6. Lost response after write

An insert returns a timeout, yet a subsequent lookup by requestId finds the order already in state CREATED. The client retries with the same key and payload. What must the backend do?

**Guidance:** Do not create a new order. Verify scope, payload, and access permissions, then return the original order or stored state per contract. A timeout does not prove the first call failed.

### Exercise 7. Transactions and payment gateways

Inside a transaction, the backend inserts an order, calls HTTP charge, then inserts requestResult and commits. What happens if the commit fails after the HTTP charge succeeded?

**Guidance:** MongoDB cannot roll back charges in external systems. Propose an outbox, payment-provider operationId/idempotency key, and reconciliation. Never place external side effects inside a retryable transaction callback.

### Exercise 8. LeaseVersion and stale workers

Worker A holds leaseVersion = 7. After timing out, B takes over and increments leaseVersion to 8. A wakes up and tries to write COMPLETED.

Write an update filter ensuring A **cannot** succeed if the document is now at version 8.

~~~javascript
db.requestResults.updateOne(
  {
    tenantId: "T-A",
    operationType: "CREATE_ORDER",
    requestId: "R-7000",
    state: "PROCESSING",
    ownerId: "worker-A",
    leaseVersion: 7
  },
  {
    $set: {
      state: "COMPLETED",
      updatedAt: new Date()
    }
  }
);
~~~

Once B updates ownerId/leaseVersion, A's filter fails to match and matchedCount equals 0. This only blocks MongoDB updates that check the token; it does not stop an external HTTP call lacking fencing/idempotency.

### Exercise 9. TTL and replay after a month

A payment registry purges deduplication documents after seven days, yet a message broker can redeliver old events after thirty days. What can happen?

**Guidance:** An event redelivered after TTL deletion can be treated as brand new. Match retention to the replay window or rely on durable business records (paymentInstructionId/ledger) and downstream idempotency. TTL does not guarantee "processed once forever."

### Exercise 10. Duplicate business reference across different requestIds

Two requests:

~~~text
R-1 -> orderRef=INV-2026-100
R-2 -> orderRef=INV-2026-100
~~~

If the two requestIds differ and the system only has a unique index on requestId, what happens? Design an additional unique business index.

**Answer:** Both requests with distinct keys could be accepted. If orderRef must be unique per tenant, add unique index **{tenantId:1, orderRef:1}**, check existing state, and define business conflict handling.

### Exercise 11. Guarding stock with a single-document update

Given:

~~~javascript
{
  _id: "SKU-1",
  available: 5,
  appliedRequestIds: ["REQ-A"]
}
~~~

Write an update reserving one unit for requestId REQ-A. The filter includes **available >= 1** and **appliedRequestIds != REQ-A**. Predict matchedCount and available.

**Answer:** matchedCount = 0, available stays 5 because REQ-A is already in appliedRequestIds. Changing to REQ-B decrements available to 4 and adds REQ-B, assuming no competing requests or unmet conditions.

### Exercise 12. Designing a retryable endpoint

An order-creation API must tolerate network drops, concurrent duplicate requests, conflicting payloads, and external notifications. Outline:

1. Rules for issuing requestId and uniqueness scope.
2. Unique index on the request registry or order.
3. How to verify fingerprint/payload when the key already exists.
4. Handling COMPLETED/PROCESSING/FAILED/UNKNOWN.
5. Writing order + outbox consistently.
6. OperationId for downstream deduplication.
7. Retention and recovery plan.

A complete answer must distinguish **protecting MongoDB data** from **protecting external side effects**, rather than merely saying "add a unique index."

## 26. Choosing a model by business complexity

| Requirement | Suggested pattern to evaluate | Limitations to keep in mind |
|---|---|---|
| One request inserts one document | Unique business key + insertOne; handle duplicate | Does not protect external side effects alone |
| "Create if absent" semantics | Unique index + upsert $setOnInsert | Re-read/compare payload if present, handle races |
| One request modifies one document | Conditional atomic update with requestId/state in filter | Needs space to record applied keys and size bounds |
| One request writes multiple collections atomically | Multi-document transaction + unique index | Does not include external HTTP calls |
| Emit events after data commits | Transactional outbox + downstream dedupe | Events can be redelivered; needs stable operationId |
| Long job, worker takeover possible | Registry + lease + leaseVersion/fencing | Does not block side effects in external systems |
| Cache idempotency responses for a bounded window | TTL index + retention window contract | Past TTL, replays can recur without durable business markers |
| Block different keys using same order reference | Separate unique business reference | Never blindly treat identical payloads as duplicates |
| Multi-tenant / sharded | Scoped compound key designed with shard key | Must obey unique index rules on sharded collections |

### 26.1. Simple decision flow

~~~text
Have a business intent requiring deduplication?
                    |
                    v
       Define requestId + scope
                    |
                    v
      Create unique constraint in MongoDB
                    |
                    v
       Task writes only one document?
              /             \
            Yes              No
            |                 |
     insert/upsert       Need atomicity
     + payload check     across documents?
                         /             \
                       Yes              No
                       |                 |
                  Transaction      Workflow/state machine
                       |                 |
                       +---------+-------+
                                 |
                                 v
                     External side effects?
                          /       \
                        Yes        No
                        |           |
                 Outbox/operationId  Done
                 + downstream dedupe
                        |
                        v
               Retry/recovery/reconciliation
~~~

This flowchart guides design selection and does not replace analyzing consistency, latency, data regulations, and system capabilities.

## 27. Design mistakes to avoid

1. **Generating a new requestId on every retry.** The system loses the ability to recognize the same intent.
2. **Using only findOne followed by insertOne.** Concurrent workers can still insert duplicates without a unique index.
3. **Including state in the unique key** when each requestId should have at most one record across all states.
4. **Using $set in upserts to overwrite payload on retries.** Can overwrite the original order with new data.
5. **Treating every E11000 as a valid retry.** Duplicate may stem from another constraint or payload conflict.
6. **Treating a timeout as "nothing was written."** A successful write can still lose its response.
7. **Treating driver retryable writes as business deduplication.** Two HTTP requests remain two independent operations unless the app passes a shared key.
8. **Calling a payment gateway inside a transaction assuming MongoDB rollback refunds it.** External side effects sit outside MongoDB commit/rollback.
9. **Leaving PROCESSING requests stuck forever after worker crashes.** Recovery, leases, and reconciliation are needed.
10. **Allowing an old worker to finish after losing its lease.** Check owner/leaseVersion in the final update.
11. **Letting TTL delete deduplication records too early.** Old replays can trigger fresh effects.
12. **Skipping authorization checks when replaying responses.** Knowing requestId does not grant permission to view results.
13. **Using only unique requestId when business rules also require unique orderRef.** Two different requestIds can still violate order invariants.
14. **Failing to monitor UNKNOWN / stale PROCESSING requests.** Deduplication might stop duplicates yet leave requests silently stuck.
15. **Ignoring index/transaction costs.** A logically sound deduplication design must still balance performance and operability.

## 28. Conclusion

**A business request ID** links repeated deliveries of **the same intent** into one controllable action. MongoDB enforces this constraint via **unique indexes** and **single-document atomicity**. Upserts, conditional updates, and transactions add varying consistency levels as requirements grow more complex.

To truly prevent duplicate processing, you cannot just create an index and stop there:

~~~text
Same business intent
       |
       v
Stable requestId + correct scope
       |
       v
Unique index (MongoDB-enforced)
       |
       v
Same payload? ---- No ----> Conflict
       |
      Yes
       |
       v
State: new / processing / completed / unknown
       |
       v
Atomic write or transaction as needed
       |
       v
Outbox + downstream operationId when needed
       |
       v
Durable result + safe retry + reconciliation
~~~

**Five principles to remember:**

- One business intent must use **the same requestId across all retries**; a new intent must use a new key.
- **A unique compound index** is a critical race barrier; check-then-write alone is insufficient.
- **Same key with different payload is a conflict**, not a valid retry.
- **A successful MongoDB write does not make external side effects safe**; use outbox, downstream idempotency, or reconciliation.
- **Key retention and recovery** must cover real retry/replay horizons; never assume TTL, leases, or driver retries automatically deliver end-to-end exactly-once semantics.

Applying these principles lets a MongoDB-backed system absorb duplicate requests, concurrent operations, and network faults while preserving its business invariant: **one valid intent produces at most one corresponding effect within the defined scope**, and uncertain cases are recorded and reconciled safely rather than silently creating extra data.
