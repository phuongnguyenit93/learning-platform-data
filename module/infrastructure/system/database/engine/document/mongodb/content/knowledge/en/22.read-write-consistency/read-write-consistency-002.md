# Distinguishing acknowledgment errors from unexecuted write operations in MongoDB

## 1. Why does "a write reported an error" not mean "no data was written"?

When building an application with MongoDB, developers often handle a write operation with two branches:

```text
Call insert/update/delete
        |
   +----+----+
   |         |
Success   Catch exception
   |         |
Return OK  Return failure?
```

The diagram above is **oversimplified** for distributed systems. Between the application and MongoDB lie networks, replica sets, server acknowledgments, data replication, journaling, timeouts, and potential primary elections. A write may have modified data on the server while the application **failed to receive a complete acknowledgment**.

This is the core distinction of this lesson:

> **"Not receiving a write acknowledgment" is not proof that "the write operation was never executed."**

For example, a user clicks "Place Order." The application sends `insertOne()` to MongoDB. The server creates the document, but the connection drops before the response reaches the application. If the application treats the exception as "order not created" and resends an order **with a new ID**, the customer may end up with **two orders**.

Conversely, not every error is ambiguous. MongoDB can explicitly report that an operation **was not applied**, such as a duplicate key error for a specific insert, though other writes in a bulk command may still succeed. Therefore, you must inspect the **error type and error scope**, rather than relying on a single Boolean `success`.

This lesson belongs to the **Read and Write Consistency** chapter and focuses on answering:

1. What has a "successful command" actually confirmed?
2. How does a `writeError` differ from a `writeConcernError`?
3. Does `wtimeout` mean the operation was canceled?
4. How does losing the connection after sending a command create an **unknown outcome** state?
5. When can you retry, when must you reconcile, and how do you avoid duplicate writes?
6. How can read concern and business keys be used to verify state?
7. What do transactions help with, and why can **a commit also have an uncertain acknowledgment outcome**?

## 2. Three distinct things in a single write

You should not use the same word "success" for every stage of the system.

### 2.1. Did the server execute the change?

Example:

```javascript
db.orders.insertOne({
  _id: "order-1001",
  customerId: "C01",
  total: 250000
});
```

This is the **data effect**: a new document is inserted into the collection if the operation is valid and not blocked by constraints.

### 2.2. Was the write acknowledgment level satisfied?

The client can request server acknowledgment via **write concern**:

```javascript
db.orders.insertOne(
  {
    _id: "order-1002",
    customerId: "C02",
    total: 180000
  },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 3000
    }
  }
);
```

With `w: "majority"`, the write is required to be acknowledged according to the deployment's majority criteria, not merely that the primary received the command. If the requirement is not met within `wtimeout`, MongoDB may report a **write concern error**, even though the write operation was already applied on the primary.

### 2.3. Did the application receive the response?

Even when the server has processed the command and sent a response, the network can drop **after server execution but before the client receives the result**.

```text
      Client                           MongoDB primary
        |                                    |
        | -------- insertOne -------------> |
        |                                    | Applies write
        |                                    | Sends response
        |           X                      |
        | <---- response lost ------------- |
        |
        +--> Timeout/connection error
             Cannot deduce "not written"
```

This is a **communication/acknowledgment failure from the client's perspective**; by itself, it does not prove whether the operation was or was not applied on the server.

### 2.4. State axes are not the same axis

| Question | Example evidence | What the evidence does not prove on its own |
|---|---|---|
| Did the command reach the server? | Command-received log | Does not confirm completion |
| Was the write applied? | Document appears on the primary | Does not confirm majority was reached |
| Did the write meet the write concern? | Requested acknowledged response | Does not prove the client received the response |
| Did the client receive the result? | Driver returns success | Does not mean all secondaries applied it if only `w: 1` was requested |
| Will the write survive failover? | Observing the record under an appropriate consistency policy | A single read does not replace write concern/backup decisions |

**The right mindset:** separate **data effect**, **acknowledgment level**, and **client certainty**.

## 3. Timeline of a write in a replica set

Suppose a replica set has three data-bearing members:

```text
              Client
                |
                v
             PRIMARY
                |
         Applies write locally
                |
        Writes to oplog / journal
                |
         +------+-------+
         |              |
         v              v
     SECONDARY A     SECONDARY B
         |              |
  Receives & applies  Receives & applies
         |              |
         +------+-------+
                |
    Write concern conditions met?
                |
         Responds to client
```

This diagram is a mental model, not a guarantee that MongoDB sequentially executes every step strictly as depicted. Writing, journaling, and replication have specific details depending on storage engine, version, and configuration.

### 3.1. `w: 1`

When requiring acknowledgment from only one member, the primary can return success **before secondaries catch up**. If the primary crashes immediately afterward, data that has not reached the required replication level may be rolled back during failover.

```javascript
db.orders.insertOne(
  { _id: "w1-demo", total: 100 },
  { writeConcern: { w: 1 } }
);
```

A success response in this case **does not equal** "the record already exists on a majority of members."

### 3.2. `w: "majority"`

```javascript
db.orders.insertOne(
  { _id: "majority-demo", total: 100 },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 5000
    }
  }
);
```

The server only acknowledges satisfying this request once the majority write concern condition is met. The goal is a stronger guarantee against certain primary-change scenarios.

**Note:** "majority of voting members" and "write durability" also involve data-bearing members, journaling settings, and version-specific guarantees. In topologies with an arbiter, do not simply count live nodes and assume every majority write will certainly be acknowledged.

### 3.3. `wtimeout` does not cancel an already-applied command

If secondaries are slow or not enough members acknowledge in time:

```text
Client requests: w="majority", wtimeout=3000ms

0ms      Primary receives and applies write
1ms      Primary begins waiting for acknowledgment conditions
3000ms   Write concern conditions not yet met
         => reports write concern timeout

Later:   Secondaries may catch up and the write reaches majority
         (or another crash/failover may occur)
```

`wtimeout` limits the time spent **waiting to satisfy the write concern**; it does not mean the server must undo an applied operation when the timer expires.

That is why **blindly retrying** immediately after `wtimeout` can be dangerous for non-idempotent operations.

## 4. Four outcome categories to distinguish

### 4.1. Category A — Success at the requested acknowledgment level

For example, the driver returns a successful result from `insertOne()` with the configured write concern and no errors.

Valid conclusions:

- The server processed the command and responded with success at the requested acknowledgment level.
- If `w: "majority"`, the corresponding majority requirement was met.
- If only `w: 1`, do not automatically assume secondaries have received the write.

### 4.2. Category B — Write execution error (write error)

Example:

```javascript
db.orders.insertOne({
  _id: "order-1001",
  customerId: "C99"
});
```

If document `_id: "order-1001"` already exists, MongoDB rejects **that insert command** due to the `_id` unique index. This is a data constraint execution error like **duplicate key**, not a report that "it was written but not yet replicated."

Other write errors can relate to validation, invalid update operators, `_id` immutability, or unique index constraints.

However, in a **bulk write** consisting of multiple operations, a `writeError` on the Nth operation **does not mean all preceding operations were not executed**. You must inspect the results and operation scope.

### 4.3. Category C — Write concern error after the operation was processed

For example, a command-level response may indicate the write portion was processed, while simultaneously containing a `writeConcernError` because the expected acknowledgment level was not achieved.

```javascript
// Illustrative shape, not a fixed response across all versions.
{
  ok: 1,
  n: 1,
  writeConcernError: {
    code: 64,
    errmsg: "waiting for replication timed out"
  }
}
```

Codes and messages may vary. The key point: **a write concern error is not equivalent to a write error**.

In this branch, you must think:

> "The operation may have been applied; what remains unconfirmed is the requested replication/durability level."

### 4.4. Category D — Lost response or network error, unknown outcome

```text
Client sends updateOne()
      |
      +--> Command never reached the server?
      |
      +--> Command arrived, not yet executed?
      |
      +--> Command executed, response lost?
      |
      +--> Command executed, but primary changed role?

Client only sees timeout/disconnect.
```

In many cases, the client **cannot determine from a network exception** which of these four possibilities occurred. You need to rely on supported retry mechanisms and business designs capable of reconciliation.

### 4.5. Summary matrix

| Signal | Allowed to conclude | Not allowed to conclude |
|---|---|---|
| Write succeeded with `w: 1` | Primary acknowledged at requested level | Already majority-committed |
| Write succeeded with `w: "majority"` | Majority level acknowledged per configuration | Every secondary has caught up |
| Duplicate key for an `insertOne` | That specific insert cannot create another record with the same key | A prior request definitely succeeded with the exact intended data |
| `writeConcernError` / `wtimeout` | Requested acknowledgment level was not met in time | The operation was never applied |
| Socket reset after sending command | Client did not receive the final result | Server definitely did not write |
| Document missing on a single read | Document was not seen at that read point | Prior command never arrived/was never processed |
| `NoWritesPerformed` in a supported retryable-write scenario | Server/driver has a specific signal that related attempts performed no writes | All other network errors carry the same guarantee |

## 5. Safe lab setup

The following examples use a dedicated database:

```javascript
use mongo_ack_lab
```

It is recommended to run these on a **test MongoDB replica set**, including a single-node replica set for basic exercises. To observe a majority write concern timeout due to slow replication, you need an actual topology with multiple data-bearing members in a controlled environment; never intentionally induce network failures in production.

### 5.1. Create collections and unique keys

```javascript
db.orderRequests.createIndex(
  { requestId: 1 },
  { unique: true }
);

db.accounts.createIndex(
  { accountId: 1 },
  { unique: true }
);
```

Example `orderRequests` document:

```javascript
{
  _id: "order:REQ-001",
  requestId: "REQ-001",
  customerId: "C01",
  total: 250000,
  status: "CREATED"
}
```

**`requestId` represents a unique business request.** If a user clicks again due to a timeout, a valid retry request must use the **same `requestId`**, rather than generating a new ID for the same business event.

### 5.2. Choose write concern explicitly

```javascript
db.orderRequests.insertOne(
  {
    _id: "order:REQ-001",
    requestId: "REQ-001",
    customerId: "C01",
    total: 250000,
    status: "CREATED"
  },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 5000
    }
  }
);
```

In a stable lab environment, the operation may be acknowledged successfully. Actual replication speed, latency, and real results **cannot be predicted in advance** for every deployment.

## 6. How do `writeError` and `writeConcernError` differ?

### 6.1. A write error relates to applying the operation

For example, create a record:

```javascript
db.orderRequests.insertOne({
  _id: "order:REQ-002",
  requestId: "REQ-002",
  customerId: "C02",
  total: 180000
});
```

Run another insert with a duplicate `requestId`:

```javascript
db.orderRequests.insertOne({
  _id: "order:REQ-002-DUPLICATE",
  requestId: "REQ-002",
  customerId: "C99",
  total: 999999
});
```

Because a unique index on `requestId` was created, the new insert is rejected. Document `order:REQ-002-DUPLICATE` **is not created by the failed insert** if the error is duplicate key.

This does not allow concluding that C99's request `REQ-002` was successfully processed: the existing record may belong to **a different payload**, or to an earlier processing run.

### 6.2. A write concern error relates to the acknowledgment level

For example, modifying a valid document may be applied on the primary, yet fail to reach `w: "majority"` within the deadline:

```javascript
db.orderRequests.updateOne(
  { requestId: "REQ-001" },
  {
    $set: {
      status: "CONFIRMED"
    }
  },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 1000
    }
  }
);
```

If a write concern timeout occurs:

- **Do not automatically revert status back to CREATED.**
- **Do not automatically conclude the update did not run.**
- **Do not immediately send a new business operation with a different ID.**
- **Verify and handle according to your retry/consistency policy.**

`$set` to a fixed value here is **idempotent with respect to final state**: re-applying the same `status: "CONFIRMED"` typically yields the same value for that field. However, if the update also modifies timestamps, increments counters, or triggers external side effects outside MongoDB, the overall workflow is not necessarily idempotent.

### 6.3. Note on `acknowledged` in drivers

Many drivers expose fields such as `acknowledged`, `matchedCount`, `modifiedCount`, and `insertedId` when an operation returns success:

```javascript
const result = db.orderRequests.updateOne(
  { requestId: "REQ-001" },
  { $set: { status: "CONFIRMED" } }
);

printjson(result);
```

Common shape:

```javascript
{
  acknowledged: true,
  matchedCount: 1,
  modifiedCount: 1,
  upsertedCount: 0
}
```

Actual numbers depend on the data and command. With `w: 0`, the API may return `acknowledged: false` **by configuration when no response is requested**, which does not mean the server proved the operation failed.

If the driver **throws an exception** before returning a normal result, do not synthesize `acknowledged: false` and treat it as proof of "not written."

## 7. Write concern: `w`, `j`, `wtimeout`

### 7.1. `w` determines the acknowledgment level

Common levels:

| Setting | General meaning | What to watch out for |
|---|---|---|
| `w: 0` | Does not ask the server to return write acknowledgment | Client has very little information to distinguish success/failure |
| `w: 1` | Requests acknowledgment from the primary or receiving member per applicable rules | Does not guarantee majority replication |
| `w: "majority"` | Requests acknowledgment from a majority per replica set rules | Can time out if required members fail to keep up |
| `w: N` | Requests acknowledgment from a configured valid number of members | Does not replace topology and durability analysis |

`w: 0` is discouraged for commands creating payments, orders, or balance updates because the application does not receive sufficient feedback to make safe decisions.

### 7.2. `j` and journaling

`j: true` requests acknowledgment related to the journal under supported mechanisms. It is part of **storage durability**, distinct from replicating across multiple members.

```javascript
db.orderRequests.insertOne(
  {
    _id: "order:REQ-003",
    requestId: "REQ-003",
    total: 50000
  },
  {
    writeConcern: {
      w: 1,
      j: true,
      wtimeout: 5000
    }
  }
);
```

Do not assume `w: 1, j: true` equals `w: "majority"`. One ties to acknowledgment on the write-receiving node and its journal; the other ties to replication/majority requirements per configuration.

In modern deployments, the interaction between majority and journaling also depends on settings such as `writeConcernMajorityJournalDefault` and the storage engine; do not treat the terms "journal" and "majority" as synonyms.

### 7.3. `wtimeout` is not the same as client communication timeouts

`wtimeout` limits how long to wait for the write concern requirement. Other timeouts can limit server selection, connection establishment, socket reads/writes, or total API execution time depending on the driver.

| Timeout type | Scope | Does it prove no write occurred? |
|---|---|---|
| `wtimeout` | Waiting to satisfy write concern | **No** |
| Network/socket timeout | Communication between client and server | **No**, if the command may have been sent |
| Server selection timeout | Waiting to select a server matching topology | If confirmed the command was never sent, no write came from that call; must rely on driver/logs |
| Client-side deadline | Limits total client-side request duration | Does not independently determine whether the server stopped processing |

A client-side timeout occurring **before the command is sent** differs from a timeout occurring **after the command reached the primary**. From a generic "timeout" exception name alone, you cannot safely distinguish every case.

### 7.4. Timeout is not an undo button

```text
Client: "I will only wait up to 3 seconds."
Server: "I wrote it, but didn't satisfy enough acknowledgments as requested."

Client timed out != Server reverted all changes.
```

The application must explicitly define an **UNKNOWN/UNCERTAIN** state, rather than forcing every timeout into either `SUCCESS` or `FAILED`.

## 8. Network loss after sending: the indeterminate outcome problem

### 8.1. Three scenarios difficult for the client to distinguish

Suppose:

```javascript
db.accounts.updateOne(
  { accountId: "A01" },
  { $inc: { balance: -100 } }
);
```

While invoking the command, the client loses connection.

**Scenario 1 — command was never sent to the server:**

```text
Client --X--> Server
No write effect from this transmission.
```

**Scenario 2 — server received the command but did not finish:**

```text
Client -----> Server (processing)
Client <---X  Lost response
Outcome is still in flight or unknown.
```

**Scenario 3 — server wrote, but the response was lost:**

```text
Client -----> Server
              balance -= 100
Client <---X  Lost response
Application does not know balance decreased.
```

If the application independently resends `$inc: -100` as a **new command**, the balance may drop by another 100, totaling -200.

### 8.2. Do not retry by creating a new request

Here is an incorrect example:

```javascript
// Pseudocode illustrating an anti-pattern; DO NOT use for real balances.
try {
  debitAccount(accountId, 100, createNewRequestId());
} catch (e) {
  debitAccount(accountId, 100, createNewRequestId());
}
```

The two calls use **different business IDs**, so even unique indexes or request-ID-based deduplication cannot recognize that they belong to the same request.

### 8.3. Does re-reading help?

If the client re-reads the balance and sees it decreased by 100, there may have been **an effect from the prior command**. However, if other transactions are concurrently modifying the balance, merely inspecting the total value is insufficient to determine **which transaction** caused the change.

Similarly, if the change is not immediately visible:

- The read may have gone to a lagging secondary.
- The prior command may not have completed yet.
- State may change during a failover.
- Another operation may have offset the total value.

**For reliable reconciliation, you must track a unique transaction/request identifier**, not merely compare a changing numeric field.

## 9. Retryable writes: the MongoDB driver's retry mechanism

MongoDB supports **retryable writes** for eligible operations and deployments. The driver can resend an eligible write operation after a communication error or failover without treating it as an entirely new request.

### 9.1. Connection configuration

Example URI:

```text
mongodb://mongo-a.example:27017,mongo-b.example:27017,mongo-c.example:27017/?replicaSet=rsApp&retryWrites=true
```

The hostnames and replica set name above are examples. Production configurations require credentials/TLS and real addresses. Modern drivers typically enable retryable writes by default when supported by the deployment; declaring it explicitly communicates intent to readers, though it does not replace checking actual driver settings.

### 9.2. Mechanism for identifying retries

Conceptually, the mechanism uses session information and appropriate statement/transaction number identifiers so the server recognizes a retransmission of the **same retryable operation**, rather than treating it as a completely separate write operation.

```text
Driver sends write W with session/statement identity
       |
       +--> Response lost
       |
Driver retries write W with matching identity
       |
Server identifies retry via supported mechanism
       |
Reduces risk of applying the same statement twice
```

This differs from application code calling an arbitrary API again with a **new session or request**. You should not claim that "because the driver has retryable writes, the entire business workflow is exactly-once."

### 9.3. Operations generally eligible

In supported replica sets/sharded clusters, single-document write operations can generally be retryable, for example:

- `insertOne()`.
- `updateOne()`.
- `replaceOne()`.
- `deleteOne()`.
- Certain find-and-modify operations such as `findOneAndUpdate()`.
- Certain bulk writes composed of eligible operations, subject to driver/server specifications and limits.

**Do not assume** `updateMany()` or `deleteMany()` are automatically retried under the same idempotent mechanism as retryable single-document writes. Multi-document commands can be partially applied before encountering an error and require separate recovery procedures.

### 9.4. Retryable writes have limits

Not all errors are retried. Common factors that affect behavior include:

- MongoDB server/driver version.
- Whether the deployment supports logical sessions and retryable writes.
- Whether the operation falls into the retryable category.
- Whether the error is eligible for retry.
- Whether the driver has exhausted its retry attempts or deadline.
- Whether the operation is inside a transaction.
- Whether data has been modified by another request or business constraint.

**Duplicate key errors are not treated as transient errors to be retried endlessly.**

### 9.5. `NoWritesPerformed` is a special signal, not the default

MongoDB 6.1 added the **`NoWritesPerformed` error label** in retryable write scenarios where both the initial attempt and the retry failed **without any write having been performed**.

If you actually receive that label under supported conditions, the application has a **stronger signal** that the associated attempts performed no writes.

However:

- Not all versions/deployments provide the label.
- Not all operation types fall under this mechanism.
- **Absence of `NoWritesPerformed` does not mean a write occurred**; it may simply mean insufficient information is available.
- An ordinary network exception does not inherently imply `NoWritesPerformed`.

Java example:

```java
if (exception.hasErrorLabel("NoWritesPerformed")) {
    // Specialized evidence from the retryable write mechanism.
    // Still must enforce business rules before deciding to proceed.
}
```

Do not manually attach this label to an exception and treat it as a server guarantee that no write occurred.

## 10. Idempotency: designing repeatable operations without duplicating effects

### 10.1. Concept

An operation is **idempotent** if applying it multiple times **for the same request** yields the same final business state as applying it once, within the defined scope.

Examples:

```javascript
// Usually idempotent for the status field alone:
{ $set: { status: "CONFIRMED" } }

// NOT idempotent if executed as two new statements:
{ $inc: { balance: -100 } }

// NOT idempotent when each insert generates a new _id:
insertOne({ _id: new ObjectId(), requestId: newUUID() })
```

Idempotency of a field update **does not automatically equal** idempotency of the entire workflow. For example, updating status once but sending an email twice is still a workflow with duplicate side effects.

### 10.2. Using a stable request ID

For order creation, the client generates a unique `requestId` **once for the checkout action**, and reuses it across all retries of that exact action.

```javascript
const requestId = "REQ-ORDER-2026-0001";

const order = {
  _id: "order:" + requestId,
  requestId: requestId,
  customerId: "C01",
  total: 250000,
  currency: "VND",
  status: "CREATED"
};

db.orderRequests.insertOne(
  order,
  { writeConcern: { w: "majority", wtimeout: 5000 } }
);
```

When retrying in business logic, **do not generate a different `requestId` and `_id`** for the same order. A unique index on `requestId` blocks two documents with the same key; a deterministic `_id` also helps prevent creating a second record.

### 10.3. What does a duplicate key after retry mean?

Suppose the client retries inserting the same document and receives a duplicate key error. Possibilities include:

1. The prior command succeeded and the same document already exists.
2. Another request wrote a document with the same key.
3. The target record exists, but with a different payload, e.g., mismatched `total`.
4. Another actor modified the document between attempts.

Therefore, **do not automatically treat every duplicate key as success**. Read the document by the stable key and verify that it **belongs to the same request, matches the accepted payload, and is in a valid business state**.

### 10.4. Using an "unknown" status for the API

A solid API contract typically needs at least three states:

```text
SUCCESS
  Write has been properly acknowledged.

REJECTED
  Evidence exists that the operation was rejected by business rules.

UNKNOWN / PENDING_CONFIRMATION
  Outcome is not fully confirmed; must reconcile or retry safely.
```

Do not return "Order failed, please place the order again as a new request" on every timeout if retrying with a new ID will cause duplicate orders.

### 10.5. Distinguishing deduplication from correctness

A unique key prevents **creating multiple documents with the same `requestId`**, but does not by itself solve:

- A request ID being reused with a different payload.
- Transferring balances between two accounts requiring multiple operations.
- Sending emails/notifications to external systems.
- Issuing refunds after funds were captured.
- Writing audit logs and business records across two collections where only one side succeeds.

This is why systems need appropriate **business states, data constraints, transactions, or recovery workflows**, rather than just creating a unique index and considering the problem solved.

## 11. Reconciling after acknowledgment errors

### 11.1. Safe business-level workflow

Suppose creating `order:REQ-001` reports a timeout.

```text
Timeout after write
        |
        v
Keep the same requestId / business key
        |
        v
Classify the error:
  - writeError?
  - writeConcernError?
  - network / unknown?
  - special error label?
        |
        v
Read/reconcile state from an authoritative source
        |
    +---+--------------------+
    |                        |
Matching record found     Still uncertain
    |                        |
Verify payload,          Do not create new request
status, write            Retry safely with same key
concern/majority         or continue reconciliation
    |                        |
    +------------+-----------+
                 |
         Return business status
```

### 11.2. Querying by request ID

```javascript
db.orderRequests.findOne({
  requestId: "REQ-001"
});
```

Use **a stable ID with a unique index** and compare at least:

- `requestId`.
- `customerId`.
- `total` and `currency`.
- Business status.
- Version/processing trail if the workflow has multiple steps.

If a document exists with the same `requestId` but a different `total`, that is a **data conflict**, not a valid "retry success."

### 11.3. Choosing read preference and read concern when reconciling

If you read from a lagging secondary immediately after writing to the primary, not seeing the document can happen even if the primary applied the write.

A common reconciliation approach when you want to observe only **majority-committed** data is to read from the primary with read concern `majority`:

```javascript
db.orderRequests
  .withReadConcern("majority")
  .findOne({ requestId: "REQ-001" });
```

Across environments, `mongosh` helper syntax may vary. An explicit MongoDB command form illustrating read concern:

```javascript
db.runCommand({
  find: "orderRequests",
  filter: { requestId: "REQ-001" },
  limit: 1,
  readConcern: { level: "majority" }
});
```

**Important to understand:** a majority read that does not find the document **does not prove the old operation was never applied on the primary**. It only indicates that at the read point with the selected guarantee, the client did not observe the document. A prior write concern timeout may later reach majority, or may be rolled back in certain crashes.

If the business needs to determine when it can **make a new decision**, combine deduplication mechanisms with the request lifecycle and a suitable retry policy, rather than relying on a single isolated `findOne()`.

### 11.4. Does reading the document mean sufficient guarantees?

Not always. A local read on the primary can observe a document **that has not yet met majority write concern**. If the primary steps down before the write is majority-committed, the state may differ after failover.

For critical data, the system must define the required acknowledgment and consistency levels before returning "final success" to the user.

## 12. Scenarios: errors when writing orders, accounts, and counters

### 12.1. Inserting with a fixed `_id`

```javascript
db.orderRequests.insertOne(
  {
    _id: "order:REQ-100",
    requestId: "REQ-100",
    total: 100000
  },
  { writeConcern: { w: "majority", wtimeout: 3000 } }
);
```

If the response is ambiguous:

1. Keep `REQ-100`.
2. Reconcile the document by `requestId`.
3. If retrying, use the **same business key**, without generating a new ID.
4. On duplicate key, **inspect document contents** before reporting success.

This model is much easier to make idempotent than inserting a new `_id` every time.

### 12.2. `$set` to a fixed value

```javascript
db.orderRequests.updateOne(
  {
    requestId: "REQ-100",
    status: "CREATED"
  },
  {
    $set: {
      status: "CONFIRMED"
    }
  }
);
```

Filtering with `status: "CREATED"` expresses a controlled state transition. If `status` is already `CONFIRMED` because the previous attempt succeeded, retrying as a new operation may return `matchedCount: 0`.

**`matchedCount: 0` does not automatically mean an error.** It may reflect that the previous operation already transitioned the status, the record was deleted, a conflicting state exists, or the request does not exist. You must read and classify the actual state.

### 12.3. `$inc` is not idempotent when re-run as a new command

```javascript
db.accounts.updateOne(
  { accountId: "A01" },
  { $inc: { balance: -100 } }
);
```

If the application independently resends `$inc`, the operation can execute a second time. Do not use this pattern for "retry to be sure" when the client does not know the previous outcome.

Safer options depending on the business logic:

- Use retryable writes properly without regenerating unrelated statements.
- Design a ledger with a unique `operationId`.
- Record a processed marker and adjust the balance within appropriate atomicity/transaction boundaries.
- Use event sourcing or compute balances from confirmed events where suitable.

### 12.4. `updateMany()` can have partial success

```javascript
db.accounts.updateMany(
  { archived: false },
  { $set: { reviewed: true } }
);
```

If the command encounters an error mid-execution, do not assume "no accounts were modified." Multi-document operations do not automatically become transactional just because they are written in a single `updateMany()` command.

Because `$set: { reviewed: true }` is a fixed-state update, you can design an idempotent/re-scan process, though you must still account for errors, newly appearing documents matching the filter, and concurrent modification effects.

## 13. Bulk write: one error does not represent every operation

### 13.1. Ordered bulk

Example:

```javascript
db.bulkAckDemo.bulkWrite(
  [
    {
      insertOne: {
        document: { _id: "A", value: 1 }
      }
    },
    {
      insertOne: {
        document: { _id: "A", value: 2 }
      }
    },
    {
      insertOne: {
        document: { _id: "B", value: 3 }
      }
    }
  ],
  { ordered: true }
);
```

On an empty collection:

1. The first insert of A can succeed.
2. The second insert of A fails with duplicate key.
3. With `ordered: true`, subsequent operations after the error are generally not executed in that batch under ordered bulk rules.

Therefore, **the bulk command reports an error**, yet document A can still exist because the first operation succeeded. Never conclude "the entire bulk rolled back."

### 13.2. Unordered bulk

```javascript
db.bulkAckDemo.bulkWrite(
  [
    { insertOne: { document: { _id: "C", value: 1 } } },
    { insertOne: { document: { _id: "C", value: 2 } } },
    { insertOne: { document: { _id: "D", value: 3 } } }
  ],
  { ordered: false }
);
```

With unordered bulk, the server can continue processing other operations despite an error on one element. **Do not assume execution order or result ordering matches the source array order.**

A bulk response may contain:

- Counts of successful insert/update/delete operations.
- A list of `writeErrors` with associated operation indices.
- `writeConcernError` if acknowledgment requirements were not met.
- Upserted IDs or matched/modified counts within what the driver exposes.

### 13.3. Rules for safe bulk handling

Never translate:

```text
bulkWrite() threw exception
```

into:

```text
0 operations were executed
```

unless you have exact evidence supporting that conclusion.

If a bulk batch spans distinct business actions, each element should carry a **unique key/`operationId`** and its own reconciliation mechanism. For massive bulks, you can split batches to bound recovery scope, though batching does not automatically provide multi-document atomicity.

## 14. Multi-document transactions and uncertain commit acknowledgment

MongoDB supports transactions on eligible replica set/sharded deployments. Transactions help group multiple read/write operations into **one atomic commit unit**.

For example, transferring funds between two accounts may require:

1. Debiting account A.
2. Crediting account B.
3. Writing a ledger entry.

If the operation commits successfully under the transaction, both updates belong to the same transactional unit under MongoDB guarantees.

### 14.1. Transactions do not eliminate network ambiguity completely

```text
Client                 MongoDB
  |                      |
  | --- commitTransaction --> |
  |                      | Transaction committed
  |     X                | Server sends response
  | <-- response lost --- |
  |
  +--> Client does not know if commit succeeded
```

This is the **uncertain commit outcome** problem. Do not immediately re-run the entire transfer business logic as a new transaction just because the client timed out during commit.

### 14.2. Common transaction error labels

MongoDB drivers may provide error labels such as:

- **`TransientTransactionError`**: may require retrying the entire transaction via supported mechanisms when appropriate.
- **`UnknownTransactionCommitResult`**: the outcome of the **commit** is unknown; the usual handling is to retry the **commit** per protocol rather than immediately re-executing the entire business body.

Drivers offering transaction callback helpers such as `withTransaction()` implement specific retry logic. Use them according to your driver version's guidance and avoid layering uncontrolled retry loops on top.

### 14.3. Difference between retrying the body and retrying the commit

```text
Error before commit, transaction clearly aborted:
  -> may retry the entire body if business logic and driver allow.

Commit error with unknown outcome:
  -> must verify/retry commit per protocol,
     DO NOT arbitrarily start a new business operation.
```

Transactions support MongoDB atomicity, but do not automatically provide exactly-once semantics for **external payments, sending emails, or calling external APIs** inside a transaction body. External side effects require separate architecture, such as transactional outbox, idempotency keys on the receiver, and reconciliation workflows.

## 15. Java Sync Driver example: classifying exceptions

Suppose a Java application uses the MongoDB Sync Driver. The goal of this example is **not to turn every `MongoException` into "not written."**

### 15.1. Creating a collection handle with write concern

```java
import com.mongodb.MongoException;
import com.mongodb.MongoWriteConcernException;
import com.mongodb.MongoWriteException;
import com.mongodb.WriteConcern;
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import java.util.concurrent.TimeUnit;

public class WriteAcknowledgementExample {
    public static void main(String[] args) {
        String uri =
            "mongodb://localhost:27017/?replicaSet=rsLab&retryWrites=true";

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> base = client
                .getDatabase("mongo_ack_lab")
                .getCollection("orderRequests");

            MongoCollection<Document> writes = base.withWriteConcern(
                WriteConcern.MAJORITY.withWTimeout(5, TimeUnit.SECONDS)
            );

            String requestId = "REQ-JAVA-001";
            Document order = new Document("_id", "order:" + requestId)
                .append("requestId", requestId)
                .append("customerId", "C01")
                .append("total", 250000)
                .append("status", "CREATED");

            try {
                writes.insertOne(order);
                System.out.println("ACKNOWLEDGED");
            } catch (MongoWriteException e) {
                System.out.println("WRITE_ERROR: " + e.getMessage());
                // e.g. duplicate key: check the record with the same requestId.
            } catch (MongoWriteConcernException e) {
                System.out.println("WRITE_CONCERN_UNMET: " + e.getMessage());
                // Do not conclude that the insert did not happen.
            } catch (MongoException e) {
                System.out.println("OUTCOME_POSSIBLY_UNKNOWN: " + e.getMessage());
                if (e.hasErrorLabel("NoWritesPerformed")) {
                    System.out.println("Server reports no writes performed");
                }
                // Classify the error and reconcile by business key.
            }

            // For the reconciliation step; DO NOT treat a single read as
            // absolute proof that the earlier write never ran.
            MongoCollection<Document> majorityRead =
                base.withReadConcern(ReadConcern.MAJORITY)
                    .withReadPreference(ReadPreference.primary());

            Document observed = majorityRead.find(
                new Document("requestId", requestId)
            ).first();

            System.out.println("Observed at majority read: " + observed);
        }
    }
}
```

**Example assumptions:** a local replica set named `rsLab` is running on the declared port, the `orderRequests` collection has a unique index on `requestId`, and the lab environment requires no credentials. The URI and port must be adjusted to match your actual lab; if the lab has three seed nodes, use the corresponding seed list.

### 15.2. What matters more than catch syntax?

Not every exception class name holds the final business conclusion. The application must:

- Record `requestId` **before sending the operation**.
- Log exception type, error labels, write concern, and relevant metadata.
- Distinguish data constraint errors from acknowledgment-level errors.
- Reconcile documents by request ID if the response is unclear.
- Handle cases where the record exists with a **different payload**.
- Never issue a new debit/payment simply because a `MongoException` was caught.

Additionally, the reconciliation read **can also experience network errors**. Do not write code assuming every write exception is immediately resolved by a single `find()` right afterward.

### 15.3. With Java transactions

When using `ClientSession` and transactions, prefer driver-provided helpers for retrying transactions/commits according to error labels. If implementing custom retries, accurately understand `TransientTransactionError` and `UnknownTransactionCommitResult`; do not lump them together with ordinary insert/update cases.

## 16. `mongosh` example: inspecting error types

A simple lab snippet to distinguish duplicate key errors from acknowledgment errors:

```javascript
const collection = db.getSiblingDB("mongo_ack_lab").orderRequests;

const doc = {
  _id: "order:REQ-MONGOSH-001",
  requestId: "REQ-MONGOSH-001",
  total: 90000
};

try {
  const result = collection.insertOne(
    doc,
    {
      writeConcern: {
        w: "majority",
        wtimeout: 5000
      }
    }
  );

  print("Write acknowledged:");
  printjson(result);
} catch (e) {
  print("Write did not return a normal success result:");
  print(e.message);
  printjson({
    name: e.name,
    code: e.code,
    errorLabels: e.errorLabels
  });
}
```

If re-run with the same document when `_id`/`requestId` already exists, it will typically produce a duplicate key error. This is a way to **produce a predictable constraint error** to observe how it differs from success.

**You cannot use duplicate inserts to simulate a write concern timeout.** The two error types stem from different conditions.

### 16.1. Inspecting the record after an error

```javascript
collection.findOne({
  requestId: "REQ-MONGOSH-001"
});
```

If a record exists, check its payload and status. In a lab without concurrent writes, the outcome is straightforward to explain; in a real system, you must also consider who else could use the same key and modify the document.

### 16.2. Direct error observation is not mandatory for learning

You do not need to intentionally kill a primary, cut network links, lag secondaries, or force write concern timeouts to understand the rules:

- `wtimeout` **does not undo**.
- A network error after sending a command can leave an unknown outcome.
- Duplicate key is a write error for the specific operation.
- Bulk operations can partially succeed.
- Reconciling via business key/idempotency enables recovery.

Practicing simulations with scenario tables is usually safer and more effective than inducing real failovers on a cluster serving users.

## 17. A decision table when exceptions occur

| Scenario type | Is write effect state knowable? | Handling approach |
|---|---|---|
| Client-side validation rejects before sending | Can know it was not sent if logic guarantees no dispatch | Fix request; do not uselessly retry identical payload |
| Duplicate key on `insertOne` | That insert was rejected | Read by business key, inspect payload, return conflict or already processed |
| Validation/write error on an operation | That operation did not complete due to constraint | Fix data/command; for bulk, inspect per element |
| `writeConcernError`/`wtimeout` | Effect may have occurred; acknowledgment insufficient | Keep ID, reconcile, and safely retry per design |
| Network reset after sending | Uncertain whether command executed | Rely on retryable writes, idempotency, reconciliation |
| Driver reports valid `NoWritesPerformed` | Specific evidence that related retryable attempts performed no writes | Can decide to retry per business rules |
| Bulk write fails at element N | Other elements may have been applied | Inspect `writeErrors`, upserts, counts, and reconcile |
| `UnknownTransactionCommitResult` | Commit not definitively acknowledged | Retry commit/reconcile per protocol; do not immediately run a new body |
| Primary failover after `w: 1` success | Write may not have been majority-committed | Determine durability requirements and post-failover state |
| Record not found when reading secondary | May be due to replication lag | Read with an appropriate policy; do not jump to conclusions |

### 17.1. Do not return HTTP 500 with messages that invite duplicate writes

If an order API receives an unknown outcome, responding with:

> "Unable to confirm request status. Please check your order using the request code."

is safer than:

> "Order failed. Click Place Order again to create a new request."

Real-world design also requires specifying HTTP status codes, idempotency keys, lookup windows, and pending states, but the goal is **never encouraging users to create another business operation while the system does not know the previous state**.

### 17.2. Do not treat HTTP error codes alone as data truth

An API Gateway can time out after a service has already written to MongoDB. HTTP 504 means the gateway **did not receive a response in time**, not that MongoDB confirmed the insert never occurred.

Similarly, a client may drop its HTTP connection while the backend continues working. Business state must be bound by an ID flowing end-to-end from the frontend through the service to the database and downstream systems.

## 18. Logging and reconciliation in production

### 18.1. Metadata to store

When encountering an ambiguous write error, technical logs might include:

```javascript
{
  requestId: "REQ-ORDER-2026-0001",
  operation: "createOrder",
  collection: "orderRequests",
  database: "app",
  writeConcern: { w: "majority", wtimeout: 5000 },
  errorCategory: "WRITE_CONCERN_TIMEOUT",
  errorLabels: [],
  attempt: 1,
  observedState: "UNKNOWN",
  timestamp: ISODate("2026-11-14T10:00:00Z")
}
```

This is an **application-designed log example**, not a schema automatically generated by MongoDB.

Do not log passwords, tokens, card numbers, sensitive personal data, or unnecessary full payload contents. You can store a normalized payload hash/checksum to help detect duplicate requests, while protecting and controlling collisions/encoding according to system requirements.

### 18.2. Create a dedicated state for inconclusive requests

A workflow might use:

```text
RECEIVED
   |
   v
PROCESSING
   |           \
   v            v
COMPLETED     UNKNOWN_OUTCOME
   |              |
   |              v
   |        RECONCILING
   |         /        \
   v        v          v
DONE      COMPLETED   REJECTED/NEEDS_REVIEW
```

Not every application needs this many states. However, when operations have **financial impact or cannot be easily undone**, an "unknown" state is often more critical than forcing all errors into "failed."

### 18.3. Automated reconciliation

A reconciliation job can:

1. Find requests in the `UNKNOWN_OUTCOME` state.
2. Read by `requestId` from an authoritative source.
3. Verify payload and state machine.
4. If completed, mark as `COMPLETED`.
5. If definitively rejected, mark as `REJECTED`.
6. If evidence is insufficient, keep pending/continue safe retries according to deadlines and policies.

Do not treat "record not seen on the first read" as sufficient reason to re-issue a credit/debit operation with a **new ID**.

### 18.4. Operational metrics to monitor

| Metric/signal | Question |
|---|---|
| `writeConcernError` frequency | Is write acknowledgment capacity falling short of targets? |
| `wtimeout` count | Secondary lag, majority unavailable, or threshold too tight for infrastructure? |
| Network timeouts | Issues with network, connection pool, server selection, or server load? |
| Retryable write errors | Are failovers or connection errors occurring frequently? |
| Replication lag | Are secondaries keeping up with the primary? |
| `UNKNOWN_OUTCOME` request count | Are many business operations awaiting reconciliation? |
| Duplicate business key rate | Are clients retrying with stable IDs or sending duplicates? |
| Transaction commit retries | Are many commits lacking clear acknowledgment? |
| Replica set elections | Is the primary changing roles too frequently? |

Metrics must be correlated with timestamps and topology. A timeout spike during a primary election differs from rising timeouts caused by a long-running query or disk I/O saturation.

## 19. Four critical rules on read/write consistency

### 19.1. Write acknowledgment does not mean all replicas are updated

`w: 1` success does not guarantee all secondaries have the data. Even with `w: "majority"`, not every secondary needs to be in sync at the exact same millisecond.

### 19.2. Reading from a secondary may miss a new write

A secondary read missing a document **does not invalidate** a write acknowledgment received from the primary. To guarantee "read-your-writes" in a workflow, choose read preference, read concern, and sessions/causal consistency matching the requirements.

### 19.3. `wtimeout` is a failure to meet acknowledgment requirements, not a rollback command

The server may apply a write at the primary without yet satisfying `w: "majority"`. After timeout, the write may continue replicating or be affected by failover. State must be assessed using additional information.

### 19.4. "Unknown outcome" is a valid state in distributed systems

If a response is lost after sending a command, the system cannot always state with certainty "written" or "not written" from a single exception. **Retryable writes, stable identifier keys, reconciliation, and state machines** are the tools applications use to reach reliable business outcomes.

## 20. Misconceptions to avoid

| Misconception | Correct understanding |
|---|---|
| Insert timed out means not inserted | Timeout can happen after the server already processed it |
| `wtimeout` is the duration to cancel a write operation | It limits waiting for the write concern level |
| `writeConcernError` is a `writeError` | One is an acknowledgment requirement error, the other is an operation application error |
| Every driver exception means no side effect occurred | Network and commit errors can leave ambiguous outcomes |
| `w: 1` success means it will never roll back | Non-majority-committed data faces risk during failover |
| `w: "majority"` success means all secondaries have the data | Only requires the deployment's majority condition |
| `acknowledged: false` proves the write failed | With `w: 0`, the client intentionally declines acknowledgment |
| Catching duplicate key means you can just report success | Must verify business key, payload, and state |
| `$inc` can be retried as a new command as many times as needed | Can double the effect if the earlier operation was already applied |
| Enabling driver retries makes the whole workflow exactly-once | Only applies to eligible operations; does not automatically protect other side effects |
| `NoWritesPerformed` appears on all unapplied write errors | It is a specialized error label with conditions and version limits |
| Absence of `NoWritesPerformed` guarantees a write occurred | Missing label yields no affirmative conclusion |
| Secondary read missing record means prior insert failed | Secondary may have replication lag |
| Majority read missing record proves the command never ran | Only reflects what is observed at that read concern level |
| Bulk error means nothing in the batch was written | Bulk operations can partially succeed |
| Transactions always tell the client clearly whether commit succeeded | Commit responses can be lost |
| Unknown commit means re-run the whole new business operation | Must retry commit/reconcile per protocol |
| HTTP 504 means backend/MongoDB did not execute the request | Gateway may time out after backend already wrote |
| Every `$set` operation is completely idempotent | Side effects, timestamps, or other workflows may be non-idempotent |

## 21. Practice exercises

### Exercise 1 — Classifying error signals

Given five scenarios:

1. `insertOne()` returns success with `w: 1`.
2. `insertOne()` returns success with `w: "majority"`.
3. `insertOne()` hits duplicate key.
4. `updateOne()` ran on the primary but encountered `writeConcernError` due to `wtimeout`.
5. Client hits socket reset right after sending `updateOne()`.

Write down clearly:

- What is known?
- What **cannot** yet be concluded?
- Is it permissible to automatically re-issue the same business operation with a new ID?

### Exercise 2 — Predicting a retried `$inc` command

An account has `balance: 1000`. The application sends:

```javascript
db.accounts.updateOne(
  { accountId: "A01" },
  { $inc: { balance: -100 } }
);
```

The client times out after sending. A piece of code creates an identical new command and resends it. List the possible observable balance values across scenarios **with no other operations** and their specific underlying assumptions.

Why can you not deduce the final balance from a single network exception? Propose how to use `operationId`, a ledger, and atomicity boundaries to make the workflow reliable.

### Exercise 3 — Duplicate key after timeout

Client creates:

```javascript
{
  _id: "order:REQ-10",
  requestId: "REQ-10",
  customerId: "C01",
  total: 200000
}
```

The first attempt times out. The second insert with the same key receives duplicate key.

1. Can you assert the first attempt wrote the exact payload?
2. Which key should you read the document by?
3. What if the document exists but has `total: 500000`?
4. What if the document exists with the right payload, and `status` is `PROCESSING`—how should the API respond?

### Exercise 4 — `wtimeout` and replica sets

Suppose a replica set has three data-bearing members, and the primary receives a write command requiring majority. Secondaries temporarily lag, causing acknowledgment conditions not to be met before `wtimeout`.

Explain:

- Might the primary have already applied the write?
- Must the server undo the write when the timer expires?
- Can the write reach majority after the client already received the error?
- What happens if the primary fails before reaching majority?
- What information is needed before concluding the order is confirmed?

### Exercise 5 — `w: 0` and observability

An application sends a critical operation with `w: 0`, then the API returns success because no exception occurred.

Why is this handling problematic? Does `acknowledged: false` mean the server confirmed the command did not execute? For payment workflows, what acknowledgment design should be chosen?

### Exercise 6 — Ordered bulk with an error midway

On an empty collection:

```javascript
db.bulkAckDemo.bulkWrite(
  [
    { insertOne: { document: { _id: "X" } } },
    { insertOne: { document: { _id: "X" } } },
    { insertOne: { document: { _id: "Y" } } }
  ],
  { ordered: true }
);
```

Predict:

- Which operation succeeds?
- Which operation fails?
- Which operation is typically not attempted in an ordered bulk?
- Why does an exception for the whole bulk not mean the collection is still empty?

Then analyze the differences when `ordered: false`.

### Exercise 7 — Read after write

An application receives a successful insert result with `w: 1` from the primary, but an immediate read afterward from a secondary does not find the document.

1. Is this necessarily a write error?
2. How does replication lag affect this?
3. How does reading from the primary differ from reading from a secondary?
4. When should read concern majority, write concern majority, and causal consistency be considered?
5. Is a majority read missing the document proof that the earlier operation never ran?

### Exercise 8 — Two types of timeouts

Distinguish:

- Server selection timeout **before a server is chosen and before the command is sent**.
- Socket timeout **after sending the command**.
- Write concern `wtimeout` **after the server processed the write but before meeting acknowledgment requirements**.

In each case, indicate the client's level of certainty regarding the data effect and what additional evidence is needed.

### Exercise 9 — Transaction commit outcome

A transaction debits A, credits B, and writes a ledger entry. The server receives `commitTransaction` and commits successfully, but the response drops.

- Can the client assert the transaction failed?
- Should it create a new transaction and re-run the entire funds transfer?
- What handling does `UnknownTransactionCommitResult` point toward?
- Why do notification emails or external payment gateway calls still require idempotency/outbox?

### Exercise 10 — Designing an idempotent API

A `POST /orders` endpoint lets clients pass an `Idempotency-Key` header.

Design:

1. How to generate and store the key for an order-placement action.
2. Unique indexes and data fields to validate.
3. Outcome when the first attempt succeeds but the response is lost.
4. Outcome when the client retries with the same key and same payload.
5. Outcome when the client retries with the same key and a **different payload**.
6. API status when write concern is not yet acknowledged.
7. Reconciliation workflow when data cannot be read immediately.

Explain why simply catching duplicate key and returning HTTP 200 in all cases is not a proper design.

### Exercise 11 — Evaluating a Java snippet

Code snippet:

```java
try {
    collection.insertOne(order);
    return "SUCCESS";
} catch (MongoException e) {
    return "NOT_WRITTEN";
}
```

Point out:

- Which types of exceptions make the name `NOT_WRITTEN` potentially wrong?
- Where do business keys/idempotency need to be added?
- When can an error be classified as `REJECTED`?
- When should `UNKNOWN_OUTCOME` be returned?
- Why should you not blindly loop retries indefinitely on every `MongoException`?

### Exercise 12 — Incident scenario walkthrough

Given the timeline:

```text
10:00:00 Client sends create order REQ-77
10:00:01 Primary executes insert
10:00:02 Write concern majority not yet satisfied
10:00:03 Client receives write concern timeout
10:00:04 Secondary catches up
10:00:05 Client creates REQ-78 to "retry"
10:00:06 Primary executes REQ-78
```

Identify which step creates the risk of two orders, and rewrite a safer timeline using the **same `requestId`** and a reconciliation step. Then consider a primary failover right before 10:00:04 and describe why the outcome cannot be deduced solely from the timeout at 10:00:03.

## 22. Practical decision workflow after a write error

To avoid mistakes in real applications, walk through these questions in order:

1. **What operation was it?** `insertOne`, `updateOne`, `$inc`, bulk write, or transaction?
2. **Is there a stable business ID?** If not, design one so retries do not create duplicates.
3. **Which category does the error belong to?** Write application error, write concern, network, server selection, or uncertain commit?
4. **Did the driver already retry automatically?** Are there error labels, or a reliable `NoWritesPerformed`?
5. **What was the requested write concern?** `w: 1`, majority, journaling, timeout?
6. **If re-reading is needed, where and at what consistency level?** Do not pick a lagging secondary and jump to conclusions.
7. **Does the existing record match the request and payload?** Duplicate key is not automatically success.
8. **Could retrying duplicate side effects?** Especially for `$inc`, event emission, payment calls, or emails.
9. **If information is insufficient, is there an UNKNOWN state?** The system needs a scheduled check/reconciliation path.
10. **Are logging and recovery workflows in place?** To handle prolonged client-server disconnections.

This is a triage and operational workflow, **not a rigid formula forcing every case to retry or every case to re-read exactly once**. Final design also depends on data criticality, fault tolerance, SLAs, topology, and driver/server versions.

## 23. Summary

**Acknowledgment errors and write execution errors are two distinct concepts.** A `writeError` can indicate that a specific operation was rejected; a `writeConcernError` or `wtimeout` indicates that the acknowledgment requirement was not met, **not that the operation was reverted**. Network errors after sending a command can leave the client **uncertain** of the actual outcome.

**Write concern is part of the durability contract.** `w: 1` does not equal `w: "majority"`; `j` does not replace replication; client-side timeouts are not a server undo button. An operation acknowledged by the primary but not yet majority-committed remains at risk during failover.

**Retries require stable identifiers and clear boundaries.** Driver retryable writes help reduce the risk of re-executing eligible operations, but do not automatically make the whole business process exactly-once. `$inc`, bulk writes, transaction commits, and side effects outside MongoDB require separate policies.

**Reconciliation beats guesswork.** Use unique `requestId`/`operationId` values, verify payloads and states, read with appropriate read concern/read preference, log errors, and support an `UNKNOWN_OUTCOME` state when needed. If evidence is insufficient to say "written" or "not written," keep the outcome **unknown** rather than issuing a new business operation that could cause duplicates.

The core mindset of the **Read and Write Consistency** chapter is: **whether the operation occurred**, **what acknowledgment level was reached**, and **what the client knows for certain** are three separate questions. Distinguishing them is the foundation for building MongoDB systems resilient to timeouts, failovers, and retries.
