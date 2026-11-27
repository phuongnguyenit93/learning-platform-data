# Testing Concurrency, Optimistic Locking, and Business Invariants in MongoDB

A sales system has **exactly one item** left in stock, yet two customers place orders simultaneously. A digital wallet holds 100,000 VND, and two concurrent requests try to deduct 80,000 VND. Two administrators edit the same order concurrently, and the second write silently overwrites the first admin's changes. A payment request is committed by MongoDB, yet the client loses connectivity before receiving the reply; the app resends the request, risking executing the transaction twice.

These are not merely bugs from “missing a lock” or “missing a transaction.” They are **race conditions** involving operation ordering, atomicity, consistency, request identity, and **business invariants**. A sequential functional test suite can be completely green while production still oversells stock, creates duplicate bookings, or overwrites user edits.

In MongoDB, a single write operation on **one document** is atomic. MongoDB provides conditional updates, unique indexes, transactions, and write conflict handling. In Spring Data MongoDB, the `@Version` annotation supports **optimistic locking** to detect when a document changed between read and save. Still, no single feature protects every business invariant: you must determine whether an invariant spans one document, multiple documents, multiple collections, or external systems.

This lesson belongs to the **Testing** chapter of the *MongoDB Document Database Engine* module. It focuses on how to **design and verify** correctness under concurrency, not merely how to write queries. Examples use Java, JUnit 5, MongoDB Java Sync Driver, Spring Data MongoDB, and `mongosh`; database names and URLs are illustrative. Any experiment that writes data must run against an **isolated test database** with appropriate privileges, never against production. APIs, exceptions, transactions, and Testcontainers setup may depend on driver, server, and framework versions.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish race conditions, lost updates, stale reads, check-then-act, write conflicts, write skew, and duplicate business requests.
2. Express invariants as **verifiable post-conditions across all interleavings**, rather than relying solely on HTTP responses.
3. Explain why reading and then writing in two separate statements is not automatically atomic.
4. Protect inventory and balances using conditional `updateOne` and `matchedCount` checks.
5. Apply compare-and-swap (CAS) with a `version` field to reject stale writes.
6. Understand Spring Data MongoDB `@Version` mechanics and optimistic locking exceptions.
7. Distinguish application-layer optimistic conflicts from MongoDB storage/transaction `WriteConflict`.
8. Design bounded retries, backoff, idempotency keys, and unknown commit outcome handling.
9. Use unique indexes to enforce uniqueness when multiple writers contend.
10. Use transactions for invariants spanning multiple documents or collections within MongoDB's supported scope.
11. Recognize write skew and why snapshot isolation does not replace all business invariants.
12. Use `CountDownLatch`/`CyclicBarrier` to reproduce interleavings deterministically instead of relying on random sleeps.
13. Build integration tests on appropriate MongoDB test deployments, including replica sets for transactions.
14. Distinguish functional tests, deterministic concurrency tests, stress/soak tests, and fault injection.
15. Assert outcomes directly on the database: non-negative inventory, bookings within quota, zero duplicate ledger entries, and zero lost updates.
16. Plan measurements for contention, conflicts, retries, transaction aborts, latency, and operational risks.

## 2. How Does Concurrency Testing Differ from Sequential Testing?

Sequential tests typically seed data, invoke one command, and compare with an expected result:

~~~text
Given stock=1
When reserve 1 unit
Then stock=0 and reservation succeeds
~~~

That does not test two requests executing together:

~~~text
Given stock=1
When request A and request B both reserve 1 unit concurrently
Then exactly one request succeeds
And stock=0, never negative
And only one confirmed reservation exists
~~~

The crux is that multiple execution schedules (interleavings) are possible.

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant DB as MongoDB
    participant B as Request B
    A->>DB: Read stock=1
    B->>DB: Read stock=1
    A->>DB: Write stock=0
    B->>DB: Write stock=0
    Note over A,B: Both A and B may believe their purchase succeeded
~~~

### 2.1. Ending with Zero Is Not Enough

If both requests report “Order placed” while the `stock` document sits at `0`, the invariant **items sold <= initial stock** has been violated. A test inspecting only the `stock` field misses this bug.

### 2.2. Assertions Are Needed at Two Layers

- **Response-level:** how many requests succeeded, were rejected, retried, or timed out?
- **State-level:** do inventory, reservations, ledgers, payments, and all final invariants hold?

A valid test inspects both. “No exception thrown” does not mean business correctness holds.

## 3. Concepts: Concurrency, Parallelism, and Atomicity

**Concurrency** means multiple operations make progress with overlapping lifetimes and interleaved step orderings. They can run on multiple threads/machines or be interleaved by a scheduler.

**Parallelism** means multiple operations physically execute at the exact same time on separate processing units.

**Atomicity** means an operation is observed as an indivisible unit of effect within the boundary guaranteed by the system. In MongoDB, a single-document write is atomic on that document, whereas two separate commands do not automatically form a transaction.

### 3.1. One Conditional Update Differs from Two Commands

~~~javascript
// Unsafe under concurrency: check on the client, then unconditional update.
const product = db.inventory.findOne({ _id: "SKU-1" });
if (product.available >= 1) {
  db.inventory.updateOne(
    { _id: "SKU-1" },
    { $inc: { available: -1 } }
  );
}
~~~

Both workers can read `available=1` and then both run `$inc(-1)`, resulting in `available=-1`.

A safer single-document invariant command:

~~~javascript
const result = db.inventory.updateOne(
  {
    _id: "SKU-1",
    available: { $gte: 1 }
  },
  { $inc: { available: -1 } }
);

if (result.matchedCount === 1) {
  print("RESERVATION_GRANTED");
} else {
  print("OUT_OF_STOCK_OR_NOT_FOUND");
}
~~~

Checking `available >= 1` and applying `$inc(-1)` execute as one atomic conditional update on the document. Once one worker completes the update, the second no longer matches the filter if stock dropped to `0`.

### 3.2. `matchedCount` Differs from `modifiedCount`

In a conditional update, `matchedCount=1` confirms a document matched the filter and the write was acknowledged per command semantics. `modifiedCount` can be `0` on a no-op update. When business logic relies on a CAS condition and an update that truly mutates state, define success by **matching the filter condition** and receiving acknowledgment rather than guessing generically from `modifiedCount`.

### 3.3. One Document vs Multiple Documents

A conditional update on `inventory(SKU-1)` does not automatically ensure a `reservations` document is also inserted. When an invariant requires **deducting stock and inserting a reservation together or neither**, either co-locate them in one document, wrap them in a transaction, or adopt an acceptable reconciliation mechanism.

## 4. Common Concurrency Failure Modes

| Phenomenon | Scenario | Symptom |
|---|---|---|
| **Lost update** | A and B read the same version, then overwrite the whole document | One edit vanishes |
| **Check-then-act / TOCTOU** | Check stock availability, then decrement in a separate command | Negative stock or overselling |
| **Double booking** | Two requests simultaneously confirm the same slot | Multiple bookings for one seat |
| **Duplicate request** | Client times out and resends | Business action applied twice |
| **Write conflict** | Transactions/writes contend on the same data | One transaction aborts/retries |
| **Write skew** | Two transactions read shared data and write disjoint documents | Cross-document invariant broken |
| **Stale read** | Reading lagging secondary or old snapshot | Decisions made on outdated state |
| **Phantom/range anomaly** | Record count in a range changes between reads | Count-based logic breaks |
| **Unique race** | Two workers insert the same business key | One operation hits DuplicateKey |
| **Unknown outcome** | Connection drops after server applies write/commit | Client unsure if write succeeded |

Never lump these failures together. The right safeguard depends on the invariant and the required atomicity boundary.

## 5. Start with Business Invariants, Not Framework Names

Before writing tests, list the rules the system **must never break** after any committed operation:

~~~text
INV-1: inventory.available >= 0
INV-2: confirmedReservations <= initialStock + replenishments
INV-3: wallet.balanceMinor >= 0
INV-4: one (tenantId, requestId) has at most one business outcome
INV-5: one seatId in an event has at most one active booking
INV-6: a PAID order must have a consistent payment ledger
INV-7: document revision is never overwritten by a stale client
~~~

### 5.1. Invariant Scope

| Scope | Example | Likely mechanism |
|---|---|---|
| Single field/document | `available >= 0` | Conditional atomic update |
| Single-namespace identity | Unique email per tenant | Compound unique index |
| Multiple docs in one collection | No two active bookings for a seat | Unique index / transaction / remodel |
| Multiple collections | Deduct stock + insert reservation | Transaction or single-document design |
| Outside MongoDB | Charge payment gateway + write ledger | Idempotency + outbox/reconciliation |

### 5.2. Business Invariants Are Not HTTP Status Codes

Two requests could both receive HTTP 200 if the app ignores `matchedCount` while the database only decremented stock once. Conversely, a request might time out even though the write committed. Tests must cross-check database state against API response contracts.

### 5.3. What Outcomes Are Acceptable?

Under concurrency, you usually **do not expect Request A to always win**. The proper expectation is a valid outcome set—such as “exactly one of A/B succeeds and the other receives OUT_OF_STOCK,” regardless of thread scheduling.

## 6. Linearization Points and Interleaving Schedules

An atomic operation can be viewed as taking effect at a single **linearization point** between invocation and response. In a single-document conditional `updateOne`, checking the predicate and applying the update happen together atomically.

~~~text
Time ->
A:  [ start ---------- update commit -------- response ]
B:      [ start ---------- failed match ------ response ]
                        ^
                 A claims the last unit
~~~

With separate read-then-write steps, no single point guarantees both “observed sufficient stock” and “decremented safely.” Fold the invariant into an atomic predicate or an appropriate transaction.

### 6.1. Tests Cannot Rely on Machine Speed

Threads launched on a fast laptop rarely collide at the exact critical instruction. Each thread might finish sequentially, keeping the test green even while a race condition lurks in production.

### 6.2. Controlling Interleavings

Use `CountDownLatch` or `CyclicBarrier` to pause two workers right after reading so both proceed with the same stale snapshot before writing. This builds a **reproducible bug-catching test**, instead of calling `Thread.sleep(50)` and hoping the scheduler gets lucky.

## 7. Lab Dataset: Inventory, Wallet, Booking, and Request Ledger

The following `mongosh` examples **use an isolated lab database only**:

~~~javascript
use mongo_concurrency_lab

db.inventory.insertMany([
  {
    _id: "SKU-A",
    available: 1,
    reserved: 0,
    version: NumberLong(0)
  },
  {
    _id: "SKU-B",
    available: 100,
    reserved: 0,
    version: NumberLong(0)
  }
])

db.wallets.insertOne({
  _id: "wallet-1",
  tenantId: "t-01",
  balanceMinor: NumberLong(100000),
  version: NumberLong(0)
})

db.bookings.createIndex(
  { tenantId: 1, eventId: 1, seatId: 1 },
  { name: "uniq_tenant_event_seat", unique: true }
)

db.requestLedger.createIndex(
  { tenantId: 1, requestId: 1 },
  { name: "uniq_tenant_request", unique: true }
)
~~~

Assumes these collections have no pre-existing duplicate data. Re-running inserts with fixed `_id`s triggers duplicate key errors; never run these commands on production.

### 7.1. Business Keys

`_id` is unique per collection, yet emails, seats, or request IDs often require multi-field uniqueness such as `(tenantId, eventId, seatId)`. MongoDB enforces that constraint only if the corresponding unique index/constraint is created or the identity is modeled into `_id`.

### 7.2. Test Data Must Be Isolated

Never share a mutable collection across parallel tests that reset or delete each other's data. Give each test its own database/namespace or independent fixture IDs with controlled cleanup.

## 8. Testing the Lost Update Anti-Pattern

Two workers read concurrently:

~~~text
Counter = 0

Worker A: read 0
Worker B: read 0
Worker A: replace counter with 1
Worker B: replace counter with 1

Final counter = 1 (should have been 2 increments)
~~~

Each `replaceOne` is atomic on one document, yet the full **read → compute → replace** sequence is not atomic.

### 8.1. Mongosh Example Without Controlled Interleaving

~~~javascript
const old = db.counters.findOne({ _id: "views" });
const next = old.count + 1;

db.counters.replaceOne(
  { _id: "views" },
  { _id: "views", count: next }
);
~~~

Running sequentially in one session will not trigger the race; it illustrates a pattern **unprotected against stale state**. To reproduce the race, run two workers synchronized by a barrier after the read.

### 8.2. When Simply Incrementing a Counter

Fix with a single server-side atomic operation:

~~~javascript
db.counters.updateOne(
  { _id: "views" },
  { $inc: { count: 1 } }
);
~~~

Two concurrent `$inc` operations apply cleanly to yield `count = 2` via single-document atomicity. However, **resending the same business request after a timeout** will increment again; atomicity does not automatically grant idempotency.

## 9. What Is Optimistic Locking?

**Optimistic locking** assumes conflicts are infrequent, allowing multiple readers to read the same document while checking at write time that the document **is still at the version that was read**.

Document:

~~~javascript
{
  _id: "order-1001",
  status: "PENDING",
  version: NumberLong(4)
}
~~~

Two editors read version 4. Editor A writes with condition `version: 4` and increments it to 5; editor B's write filtering on `version: 4` fails to match. Instead of silently overwriting, B detects a conflict.

~~~mermaid
sequenceDiagram
    participant A as Editor A
    participant DB as MongoDB
    participant B as Editor B
    A->>DB: find order version=4
    B->>DB: find order version=4
    A->>DB: update where version=4; set status; inc version
    DB-->>A: matchedCount=1
    B->>DB: update where version=4; set status; inc version
    DB-->>B: matchedCount=0
    Note over B: OPTIMISTIC_CONFLICT; A's edit is preserved
~~~

### 9.1. Not a Database Lock Held While a User Edits a Form

No thread holds a mutex from page load until the user clicks Save. The check happens **at write time**. This suits forms and workflows with long think times between read and write.

### 9.2. A Conflict Is a Valid Business Outcome

When two editors edit the same record, one succeeds and the other receives HTTP 409 Conflict and is asked to reload or merge. Never blindly retry the stale payload until it wins, as that overrides the first editor's work.

### 9.3. Version Does Not Replace Authorization

Checking `version=4` does not verify the user is allowed to edit the order. Filters must still enforce tenant/owner/role constraints.

## 10. Compare-and-Swap (CAS) with MongoDB `updateOne`

Updating an order only if its version is still 4:

~~~javascript
const result = db.orders.updateOne(
  {
    _id: "order-1001",
    tenantId: "t-01",
    version: NumberLong(4)
  },
  {
    $set: { status: "APPROVED" },
    $inc: { version: NumberLong(1) }
  }
);

if (result.matchedCount === 0) {
  print("CONFLICT_OR_NOT_FOUND_OR_NOT_AUTHORIZED");
}
~~~

The filter and update execute atomically on the document. Incrementing `version` on success guarantees stale writes fail.

### 10.1. `matchedCount=0` Alone Does Not Classify the Cause

You cannot tell strictly from `0` whether:

- The document was deleted?
- The tenant filter failed to match?
- The version changed?
- The status/business predicate failed?

The application may return a generic response to avoid leaking record existence, or perform an authorized follow-up query to distinguish conflict vs not found per API policy.

### 10.2. `upsert` Can Break CAS If Misused

Never enable `upsert: true` on a version-constrained update meant only to modify an existing document, unless a dedicated create/insert protocol explicitly handles it. A stale attempt could turn into an unexpected insert, causing duplicate key errors or corrupt state.

### 10.3. Version Must Increment Atomically in the Same Update

Updating content in one command and incrementing version in a second command reintroduces a race window between them. Put `$set` and `$inc` in the **same atomic update**.

## 11. CAS for Order State Transitions

Suppose an order may transition only along:

~~~text
PENDING -> APPROVED -> FULFILLED
        \-> CANCELLED
~~~

A valid transition:

~~~javascript
const result = db.orders.updateOne(
  {
    _id: "order-1001",
    tenantId: "t-01",
    status: "PENDING",
    version: NumberLong(4)
  },
  {
    $set: {
      status: "APPROVED",
      approvedAt: new Date()
    },
    $inc: { version: NumberLong(1) }
  }
);
~~~

Combining **expected status** and **expected version**:

- Status protects the business state machine.
- Version protects against overwriting any other document edit made after the read.

### 11.1. Version Only vs Status Only?

Status alone may suffice for a simple transition if no other fields matter. Version alone detects stale writes yet cannot block illegal state transitions if buggy code invokes them. For critical workflows, test both guards.

### 11.2. Concurrent Approve vs Cancel

Two requests both read `PENDING`. One succeeds in moving to `APPROVED`; the `CANCELLED` update no longer matches status/version, making it impossible to end up both `APPROVED` and `CANCELLED` when both paths use proper conditional updates.

### 11.3. Retrying a Command Differs from Retrying a Decision

Never re-read the new version and retry `CANCELLED` if business rules forbid cancelling after approval. Retries must **re-evaluate business preconditions**, not blindly loop until the database accepts a write.

## 12. Conditional Updates for Balances and Inventory

Suppose a wallet holds 100,000 VND and two requests each attempt to deduct 80,000 VND:

~~~javascript
const amount = NumberLong(80000);
const result = db.wallets.updateOne(
  {
    _id: "wallet-1",
    tenantId: "t-01",
    balanceMinor: { $gte: amount }
  },
  {
    $inc: { balanceMinor: NumberLong(-80000) }
  }
);
~~~

Starting from 100,000, **at most one** of the two concurrent conditional updates can match. After success, `balanceMinor` equals 20,000, never negative.

### 12.1. Why No Pre-Read Is Required?

The sufficiency check lives inside the write filter, eliminating any gap between “check” and “act.” You can read beforehand for UI display, yet the final decision must rest on the atomic update.

### 12.2. Monetary Types

Examples use integer minor units; storing money as `double` risks floating-point comparison and subtraction errors. Use integer minor units or `Decimal128` per schema, defining numeric bounds, exchange rates, and rounding policies.

### 12.3. Not Idempotent on Resend

For two **distinct** requests competing for 80,000, at most one succeeds. Yet if the first request deducted 80,000, the client lost the response, and the client resends after a top-up occurs, the same business request could deduct again. Conditional updates do not replace idempotency keys.

## 13. Spring Data MongoDB `@Version`

Spring Data MongoDB provides `@Version` to manage optimistic locking on entities persisted via supported mapping operations:

~~~java
package example.concurrency;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("wallets")
public class Wallet {
    @Id
    private String id;
    private String tenantId;
    private long balanceMinor;

    @Version
    private Long version;

    public Wallet() {}

    public Wallet(String id, String tenantId, long balanceMinor) {
        this.id = id;
        this.tenantId = tenantId;
        this.balanceMinor = balanceMinor;
    }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public long getBalanceMinor() { return balanceMinor; }
    public Long getVersion() { return version; }

    public void setBalanceMinor(long amount) {
        this.balanceMinor = amount;
    }
}
~~~

### 13.1. What Does Spring Data Do?

On supported save and versioned update operations, the framework includes the **current version** in the write predicate and increments it upon success. If no document matches the old version, the framework throws `OptimisticLockingFailureException` instead of silently overwriting.

### 13.2. Never Hardcode Initial Version

When and what initial version is assigned to a new entity can vary between primitive vs wrapper types and Spring Data versions. In tests, **save the entity and read back its actual version** rather than assuming everything always starts at 0.

### 13.3. Write Concern Must Be Acknowledged

For Spring Data to detect when a versioned update matched nothing, the server must acknowledge the write result. Use an appropriate acknowledged write concern; unacknowledged write concerns prevent optimistic locking from detecting conflicts.

### 13.4. The Annotation Does Not Cover Raw Writes

If another module uses the MongoDB Java Driver directly with `updateOne({_id})` without checking and incrementing `version`, it **bypasses `@Version`**. Establish a codebase rule that every write path touching the entity honors the version protocol or an equivalent atomic predicate.

## 14. Testing Stale Entities with Spring Data MongoTemplate

A simple test **needing no second thread** suffices to prove stale versions are rejected:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.data.mongodb.core.MongoTemplate;

class WalletOptimisticLockIntegrationTest {
    @Autowired
    MongoTemplate mongoTemplate;

    @Test
    void staleEntityMustNotOverwriteFreshEntity() {
        Wallet created = mongoTemplate.save(
            new Wallet("wallet-stale-test", "t-01", 100000L)
        );

        Wallet editorA = mongoTemplate.findById(
            created.getId(), Wallet.class
        );
        Wallet editorB = mongoTemplate.findById(
            created.getId(), Wallet.class
        );

        assertNotNull(editorA);
        assertNotNull(editorB);
        assertEquals(editorA.getVersion(), editorB.getVersion());

        editorA.setBalanceMinor(90000L);
        mongoTemplate.save(editorA);

        editorB.setBalanceMinor(20000L);
        assertThrows(
            OptimisticLockingFailureException.class,
            () -> mongoTemplate.save(editorB)
        );

        Wallet persisted = mongoTemplate.findById(
            created.getId(), Wallet.class
        );
        assertNotNull(persisted);
        assertEquals(90000L, persisted.getBalanceMinor());
    }
}
~~~

### 14.1. This Is an Integration Skeleton for a Test Context

The example assumes `MongoTemplate` is injected by Spring Test configuration, runs on an **isolated database**, and the versioned entity is mapped properly. Use cleanup, unique IDs, or separate databases across tests to avoid leftover state.

### 14.2. Why Is a Sequential Test Still Valuable?

It creates two **independent object snapshots** holding the same version prior to writing. Once A saves, B becomes stale. You do not depend on thread scheduling to prove `@Version` semantics.

### 14.3. This Is Not Yet a Stress Test

A stale-save test does not prove behavior under thousands of contending requests, network partitions, or transaction retries. Additional concurrency and fault-injection layers are needed.

## 15. Spring Data Repositories and Exception Mapping

Repository:

~~~java
import org.springframework.data.mongodb.repository.MongoRepository;

public interface WalletRepository
        extends MongoRepository<Wallet, String> {
}
~~~

Saving a form edit:

~~~java
public Wallet saveUserEdit(Wallet edited) {
    return walletRepository.save(edited);
}
~~~

When the version is stale, Spring Data throws `OptimisticLockingFailureException`. The service or controller should map it to a **meaningful conflict**, such as HTTP 409, rather than returning a generic HTTP 500.

### 15.1. Never Silently Retry a Stale Form

If user A edits a shipping address and user B edits notes from the same version, offer UI merge or reload. Blindly retrying B's entire entity onto the new version would overwrite A's edit.

### 15.2. Retrying Commands in Batch Jobs

If the operation is “increment counter by 1” and business rules allow, a job may re-read, recompute, and retry CAS a bounded number of times. That differs fundamentally from overwriting a full user-edited form.

### 15.3. `@Version` Does Not Enforce Uniqueness

A document-level version never prevents **two distinct documents** from sharing the same email or seat. Use a unique index for cross-document identity constraints.

## 16. Spring Data `@Version` vs Raw Updates

Applications sometimes mix:

~~~java
// Path A: Spring Data save using @Version.
walletRepository.save(wallet);

// Path B: Raw MongoDB driver update matching only _id.
rawWalletCollection.updateOne(
    Filters.eq("_id", walletId),
    Updates.set("balanceMinor", 12345L)
);
~~~

Path B is **not automatically protected by the Java annotation**, because the database only sees the filter and update sent over the wire. One writer can modify `balanceMinor` without bumping `version`, leaving optimistic editors unaware the document changed.

### 16.1. Codebase Consistency Rule

For any shared aggregate:

- Either use Spring Data operations that honor `@Version`;
- Or use explicit atomic conditional updates checking and incrementing `version`;
- Or adopt another concurrency model and test every write path.

Never assume “the entity has `@Version`” guarantees background scripts, pipelines, or other services respect it.

### 16.2. Mixed-Path Integration Test

Create an entity via the repository, mutate it with a raw update that skips `version`, and verify whether a stale repository save overwrites it. If the test exposes a gap, fix the raw update path. This is a critical **compatibility/integration test** when multiple writers exist.

## 17. Optimistic Conflicts Differ from MongoDB `WriteConflict`

Two errors may sound alike yet stem from different layers:

| Type | Detected by | Example | Handling |
|---|---|---|---|
| **Application optimistic conflict** | Version predicate / Spring Data | `matchedCount=0`, `OptimisticLockingFailureException` | Return conflict; reload/merge/recompute per business rules |
| **MongoDB WriteConflict** | Storage / transaction concurrency control | WriteConflict code 112 inside a transaction | May retry transaction if transient and supported by driver |
| **DuplicateKey** | Unique index | E11000 / code 11000 | Inspect identity/request; do not retry blindly |
| **Network/timeout** | Client/transport/server selection | Reply never received | Outcome uncertain; reconcile/use idempotency |

### 17.1. Do Not Retry Every Exception

`OptimisticLockingFailureException` is not a transient transaction error. Blindly retrying a stale form causes business-level lost updates. DuplicateKey is usually an expected contention outcome of a uniqueness constraint.

### 17.2. Multiple Mechanisms Can Fire Together

A transaction performing an optimistic version update can abort with a write conflict. A request can also hit duplicate key on a ledger and a network timeout during commit. Error handling must separate **storage state** from **business outcome**.

## 18. Unique Indexes: Constraints Belong in the Database

Two users select the same seat. Dangerous pattern:

~~~javascript
const existing = db.bookings.findOne({
  tenantId: "t-01",
  eventId: "EV-1",
  seatId: "A-01"
});

if (!existing) {
  db.bookings.insertOne({
    tenantId: "t-01",
    eventId: "EV-1",
    seatId: "A-01",
    state: "ACTIVE"
  });
}
~~~

Both workers can observe no booking and insert two documents with distinct `_id`s.

Unique index:

~~~javascript
db.bookings.createIndex(
  {
    tenantId: 1,
    eventId: 1,
    seatId: 1
  },
  { unique: true, name: "uniq_tenant_event_seat" }
);
~~~

When both insert the same key, the index guarantees two valid documents with that key cannot coexist **per index semantics**; one writer receives E11000.

### 18.1. Align Unique Constraints with Business Semantics

If a seat may have multiple historical `CANCELLED` bookings yet at most one `ACTIVE` booking, a plain unique index on tenant/event/seat is too strict. Use a **partial unique index** where appropriate:

~~~javascript
db.bookings.createIndex(
  { tenantId: 1, eventId: 1, seatId: 1 },
  {
    unique: true,
    name: "uniq_active_seat",
    partialFilterExpression: { state: "ACTIVE" }
  }
);
~~~

The filter expression must match exact business semantics, including `HOLD`/`PENDING`/`EXPIRED` states if those also reserve seats.

### 18.2. Nulls, Collation, and Sharding

Unique indexes have rules for null/missing keys, collation, and sharded-collection limitations. Case-insensitive email uniqueness requires matching collation/normalization. On sharded clusters, global uniqueness depends on shard-key compatibility. Never assume adding `@Indexed(unique=true)` ensures every deployment enforces it.

### 18.3. Do Not Test Only for the Index Annotation

Tests must verify **the index actually exists on the MongoDB test instance**. Spring Data auto-index creation may be disabled by config or version; Java metadata does not prove the index exists.

## 19. Handling DuplicateKey as a Contention Outcome

The Java driver reports duplicate key errors as `MongoWriteException` with code 11000:

~~~java
import com.mongodb.MongoWriteException;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

public boolean tryBookSeat(
        MongoCollection<Document> bookings,
        String tenantId,
        String eventId,
        String seatId,
        String bookingId
) {
    try {
        bookings.insertOne(
            new Document("_id", bookingId)
                .append("tenantId", tenantId)
                .append("eventId", eventId)
                .append("seatId", seatId)
                .append("state", "ACTIVE")
        );
        return true;
    } catch (MongoWriteException error) {
        if (error.getError().getCode() == 11000) {
            return false;
        }
        throw error;
    }
}
~~~

### 19.1. “Booking Already Exists” Is Not Always HTTP 409

If a client **resends the same request ID**, a duplicate key can mean the same transaction already succeeded; read the ledger and return the prior result. If **another customer raced for the same seat**, returning “seat unavailable” / 409 is appropriate. Never conflate the two scenarios solely because they share an error code.

### 19.2. Never Retry Insert with a New ID

On a unique seat conflict, generating another random `_id` **does not free up the seat**. Retrying like that keeps failing or creates duplicates if an index is misconfigured.

## 20. Unique Indexes and Optimistic Locking Complement Each Other

| Need | Appropriate safeguard |
|---|---|
| No two records hold the same ACTIVE seat | Unique / partial unique index |
| No stale update overwrites an existing booking | Version CAS / `@Version` |
| One request does not create two bookings on retry | Idempotency key / unique ledger |
| Booking and payment record commit together | MongoDB transaction + external reconciliation |
| Seats stay within overall quota | Conditional quota document or transaction + guard |

An application often needs **all four**: unique constraints, optimistic locking, transactions, and idempotency. No single mechanism replaces all the others.

## 21. Test Infrastructure: Integration Databases Must Be Real

Mocks help unit test service branches, yet a mocked `MongoCollection` never proves the server enforces atomicity, unique indexes, transactions, or wire errors.

Testing tiers:

| Tier | Purpose | Limitation |
|---|---|---|
| Pure Java unit test | Business rules / DTO / result mapping | Does not test MongoDB concurrency semantics |
| Real MongoDB integration test | Atomic filters, unique indexes, mapping, `@Version` | Usually low load |
| Deterministic concurrency test | Reproduces a specific interleaving | Does not cover every schedule |
| Stress/soak test | Contention, p95/p99, resource leaks | May miss rare races |
| Fault injection | Network timeouts, rollbacks, commit uncertainty | Requires special infra and privileges |

### 21.1. Standalone vs Replica Set

Single-document atomic updates and unique indexes can be tested on a simple lab MongoDB server. **Multi-document transactions** require a supporting topology such as a replica set or sharded cluster. A plain standalone `mongod` is insufficient for transaction tests.

### 21.2. Testcontainers

Testcontainers can provision a MongoDB instance or replica set matching your module/version. Testcontainers changed packages and APIs across major versions, so align integration with your project's dependencies. Never hardcode a class or method from an old snippet without verifying it.

### 21.3. Test Isolation

Every test needs its own namespace/DB or unique IDs plus safe cleanup. Running a stress test concurrently with migrations or other tests on the same database causes flaky failures and invalid results.

## 22. Configuring Java Test Dependencies

With Gradle (illustrative; replace placeholders with pinned versions):

~~~kotlin
dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:REPLACE_WITH_PINNED_VERSION")
    testImplementation("org.mongodb:mongodb-driver-sync:REPLACE_WITH_PINNED_VERSION")

    // When using Spring Data tests:
    testImplementation("org.springframework.boot:spring-boot-starter-test")

    // If using Testcontainers, add the module and integration matching
    // your project's Testcontainers major version.
}

tasks.test {
    useJUnitPlatform()
}
~~~

This is a **dependency declaration template**, not a drop-in build file before replacing placeholders and configuring dependency management. You do not need redundant driver dependencies if Spring Data's starter already provides the MongoDB driver.

### 22.1. Separate Test URLs from Production

Examples below use `MONGODB_TEST_URI`. This variable must target a **dedicated test cluster** with restricted credentials. Never fall back to production `MONGODB_URI` when the test URI is missing.

### 22.2. Intentional Timeouts

Concurrency tests must never hang forever if one worker crashes before reaching the barrier. Use `await(timeout)`, `Future.get(timeout)`, and shut down thread pools and clients inside `finally`.

### 22.3. Never Use Sleep to “Simulate Concurrency”

`Thread.sleep` only introduces relative delays; it does not guarantee both readers read the stale snapshot. Use barriers/latches to reproduce interleavings and dedicated load generators for stress.

## 23. Atomic Test: Two Workers Racing for One Product

The JUnit 5 test below creates a randomly named database on a **test deployment**, inserts `stock = 1`, launches two threads executing a conditional update simultaneously, and verifies:

- **Exactly one** worker succeeds.
- Final `available` equals `0`.
- Stock never turns negative.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.UUID;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.result.UpdateResult;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import org.bson.Document;
import org.junit.jupiter.api.Test;

class StockConcurrencyTest {

    @Test
    void exactlyOneOfTwoRequestsMayReserveLastUnit()
            throws Exception {

        String uri = System.getenv("MONGODB_TEST_URI");
        assertNotNull(uri, "MONGODB_TEST_URI must point to isolated test DB");

        try (MongoClient client = MongoClients.create(uri)) {
            String dbName = "concurrency_lab_" +
                UUID.randomUUID().toString().replace("-", "");

            MongoDatabase db = client.getDatabase(dbName);
            MongoCollection<Document> inventory =
                db.getCollection("inventory");

            ExecutorService pool = Executors.newFixedThreadPool(2);
            CountDownLatch ready = new CountDownLatch(2);
            CountDownLatch start = new CountDownLatch(1);

            try {
                inventory.insertOne(
                    new Document("_id", "SKU-A")
                        .append("available", 1)
                );

                Callable<Boolean> reserve = () -> {
                    ready.countDown();
                    if (!start.await(5, TimeUnit.SECONDS)) {
                        throw new IllegalStateException("Start gate timeout");
                    }

                    UpdateResult result = inventory.updateOne(
                        Filters.and(
                            Filters.eq("_id", "SKU-A"),
                            Filters.gte("available", 1)
                        ),
                        Updates.inc("available", -1)
                    );
                    return result.getMatchedCount() == 1;
                };

                Future<Boolean> a = pool.submit(reserve);
                Future<Boolean> b = pool.submit(reserve);

                assertTrue(ready.await(5, TimeUnit.SECONDS));
                start.countDown();

                int wins =
                    (a.get(10, TimeUnit.SECONDS) ? 1 : 0) +
                    (b.get(10, TimeUnit.SECONDS) ? 1 : 0);

                Document finalDoc = inventory.find(
                    Filters.eq("_id", "SKU-A")
                ).first();

                assertNotNull(finalDoc);
                assertEquals(1, wins);
                assertEquals(0, finalDoc.getInteger("available"));
            } finally {
                start.countDown();
                pool.shutdownNow();
                db.drop(); // Only the random DB created for this test.
            }
        }
    }
}
~~~

### 23.1. Why `Filters.gte` Matters

Omitting that filter and matching only `Filters.eq("_id", "SKU-A")` lets both workers run `$inc(-1)`, yielding `available = -1`.

### 23.2. Does the Latch Guarantee Both Updates Hit the Same Nanosecond?

No. `start` releases both threads close together to heighten contention, though the OS scheduler may still serialize them. Regardless, the **exactly-one-winner invariant** is upheld by the atomic filter across every valid execution order, whether simultaneous or sequential.

### 23.3. This Test Does Not Verify Reservation Documents Yet

It proves the single-document stock invariant, not multi-collection transactions. If production also creates `reservations`, add transaction or reconciliation tests.

## 24. Controlled Lost-Update Test Using CyclicBarrier

To prove the read-then-replace pattern is unsafe, **both workers must read the old value before either writes**.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.*;

import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import org.bson.Document;

// Assumes "counter" belongs to an isolated test database;
// client and cleanup are managed by the test fixture.
void demonstratesLostUpdate(
        MongoCollection<Document> counter
) throws Exception {
    counter.insertOne(
        new Document("_id", "hits").append("count", 0)
    );

    CyclicBarrier bothHaveRead = new CyclicBarrier(2);
    ExecutorService pool = Executors.newFixedThreadPool(2);

    Callable<Void> wrongIncrement = () -> {
        Document snapshot = counter.find(
            Filters.eq("_id", "hits")
        ).first();

        assertNotNull(snapshot);
        int next = snapshot.getInteger("count") + 1;

        // Guarantees both A and B read before either replaces.
        bothHaveRead.await(5, TimeUnit.SECONDS);

        counter.replaceOne(
            Filters.eq("_id", "hits"),
            new Document("_id", "hits").append("count", next)
        );
        return null;
    };

    try {
        Future<Void> a = pool.submit(wrongIncrement);
        Future<Void> b = pool.submit(wrongIncrement);
        a.get(10, TimeUnit.SECONDS);
        b.get(10, TimeUnit.SECONDS);

        Document finalDoc = counter.find(
            Filters.eq("_id", "hits")
        ).first();
        assertNotNull(finalDoc);
        assertEquals(1, finalDoc.getInteger("count"));
    } finally {
        pool.shutdownNow();
    }
}
~~~

### 24.1. This Test Intentionally Demonstrates a Bug

It proves **two logical increments yield only one persisted increment**—never use that pattern in production. Once fixed with atomic `$inc` or CAS, the expected result becomes `2`.

### 24.2. Why Place the Barrier After the Read?

If the barrier came before the read, A could read and write before B even read, causing the test to pass by accident sequentially. Placing the barrier **after the read** forces both workers onto the stale snapshot.

### 24.3. Timeouts Prevent Hanging Tests

`CyclicBarrier.await(timeout)` fails cleanly if a thread dies before reaching the barrier, letting the test report an error and tear down the thread pool.

## 25. Testing CAS: One Winner, One Conflict

Given:

~~~javascript
{ _id: "counter", count: 0, version: NumberLong(0) }
~~~

Two workers read `version=0`, synchronize at a barrier, and both send:

~~~javascript
db.counters.updateOne(
  { _id: "counter", version: NumberLong(0) },
  {
    $inc: {
      count: 1,
      version: NumberLong(1)
    }
  }
);
~~~

Expected:

~~~text
Worker A matchedCount=1, B matchedCount=0
or:
Worker A matchedCount=0, B matchedCount=1

Final count=1, version=1
~~~

This is an **expected optimistic conflict**: exactly one change from version 0 is accepted. For both **valid business increments** to take effect eventually, the losing worker must re-read the new version/state, recompute, and try again.

### 25.1. Necessary Checks

1. Zero updates succeed with a stale version.
2. `version` increments once per accepted change.
3. Zero lost updates from full-document overwrites.
4. With retries enabled, final state reflects accepted operations rather than raw attempt counts.

### 25.2. Never Treat Conflict as Automatic Success

`matchedCount=0` does not mean “my update already succeeded earlier.” Another writer modified the record. For requests carrying an identity/idempotency key, consult the ledger or verify the exact operation.

## 26. Bounded CAS Retries

For an operation **safe to recompute on fresh state**, use a bounded retry loop:

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

public boolean incrementWithCas(
        MongoCollection<Document> counters,
        String id,
        int maxAttempts
) {
    if (maxAttempts < 1) {
        throw new IllegalArgumentException("maxAttempts");
    }

    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
        Document current = counters.find(
            Filters.eq("_id", id)
        ).first();
        if (current == null) {
            return false;
        }

        Long version = current.getLong("version");
        if (version == null) {
            throw new IllegalStateException("version required");
        }

        UpdateResult result = counters.updateOne(
            Filters.and(
                Filters.eq("_id", id),
                Filters.eq("version", version)
            ),
            Updates.combine(
                Updates.inc("count", 1),
                Updates.inc("version", 1L)
            )
        );

        if (result.getMatchedCount() == 1) {
            return true;
        }
        // Conflict: re-read on the next iteration.
        // Production: add bounded backoff/jitter/deadline.
    }
    return false;
}
~~~

### 26.1. Why Not Retry Forever?

When many workers contend on one document, tight immediate retries trigger contention storms. Use bounded attempts, backoff with jitter, deadlines, and observability, returning an error when the budget expires.

### 26.2. Crucial Distinction: Operation Type

This snippet handles “increment counter by 1” where each **independent call** is meant to increment. For a request that could be resent after a network timeout, you still need an **idempotency key** for exactly-once business effects; a CAS loop alone does not provide that.

### 26.3. Re-Reading Is Not Always Valid

If two users edit a form with conflicting intents, you cannot blindly recompute by re-reading and saving old fields. Either apply a domain merge policy or return a conflict to the user.

## 27. State Machines and Business Invariants

Valid order transitions:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> APPROVED
    PENDING --> CANCELLED
    APPROVED --> FULFILLED
    APPROVED --> CANCELLED: if policy allows
    FULFILLED --> [*]
    CANCELLED --> [*]
~~~

Concurrency tests should cover:

- APPROVE vs CANCEL at the same version.
- APPROVE sent twice with the same request ID.
- FULFILL vs CANCEL while `APPROVED`.
- Updating notes concurrently with a state transition.
- Retries after a lost response.

### 27.1. Atomic Predicate for Transitions

~~~javascript
db.orders.updateOne(
  {
    _id: "order-1",
    tenantId: "t-01",
    status: "PENDING"
  },
  {
    $set: { status: "APPROVED" },
    $inc: { version: NumberLong(1) }
  }
);
~~~

At most one competing transition can move `PENDING` to another state if **all write paths** enforce expected status properly.

### 27.2. Testing Negative / Malformed Inputs

If an API allows `quantity=-1`, `available >= quantity` can match and `$inc(-quantity)` unintentionally increases stock. Business validation must verify `quantity > 0`, numeric bounds, and types before issuing MongoDB writes.

### 27.3. Boundary Testing

Test stock `0, 1, N` with request quantities `0, 1, N, N+1` and concurrent demand exceeding quota. Boundary inputs catch bugs that average random tests miss.

## 28. Transactions When One Business Operation Touches Multiple Documents

Suppose a reservation must:

1. Decrement `inventory.available`.
2. Insert a `reservations` record.
3. Save a `requestLedger` entry to block resends.

If executed as separate steps:

~~~text
Update inventory succeeded
Process crashed
Reservation document was not inserted
~~~

Stock decreased without a matching reservation. A **MongoDB multi-document transaction** groups these changes into one atomic commit when supported by the deployment.

~~~mermaid
flowchart TD
    Request["Reserve request tenant + requestId"] --> Tx["Start MongoDB transaction"]
    Tx --> Ledger["Insert unique request ledger"]
    Ledger --> Stock["Atomic conditional inventory update"]
    Stock --> Decision{"Stock matched?"}
    Decision -->|"No"| Abort["Abort transaction; reject"]
    Decision -->|"Yes"| Reservation["Insert reservation record"]
    Reservation --> Commit["Commit transaction"]
    Commit --> Return["Return committed result"]
~~~

### 28.1. Transactions Do Not Automatically Prevent Negative Stock

Even inside a transaction, reading stock and deducting without a protective predicate requires understanding concurrency interactions. MongoDB raises write conflicts on overlapping writes, yet sound design still uses **invariant-protecting conditional updates** and proper transaction retry handling.

### 28.2. Never Place External Side Effects Inside a Transaction Callback

Calling a payment gateway, sending emails, or publishing to Kafka directly inside a transaction callback can emit duplicate side effects if the transaction body retries. External systems do not roll back when MongoDB aborts. Use a transactional outbox, idempotent consumers, or proper orchestration/reconciliation.

## 29. Java Driver: Transaction Skeleton

Example for a transaction-capable replica set/sharded topology with collections and permissions configured:

~~~java
import com.mongodb.ReadConcern;
import com.mongodb.WriteConcern;
import com.mongodb.TransactionOptions;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import org.bson.Document;

import static com.mongodb.client.model.Filters.*;

public String reserveInTransaction(
        MongoClient client,
        MongoCollection<Document> inventory,
        MongoCollection<Document> reservations,
        MongoCollection<Document> requestLedger,
        String tenantId,
        String requestId,
        String sku
) {
    TransactionOptions txOptions = TransactionOptions.builder()
        .readConcern(ReadConcern.SNAPSHOT)
        .writeConcern(WriteConcern.MAJORITY)
        .build();

    try (ClientSession session = client.startSession()) {
        return session.withTransaction(() -> {
            requestLedger.insertOne(
                session,
                new Document("tenantId", tenantId)
                    .append("requestId", requestId)
                    .append("state", "COMMITTED")
                    .append("sku", sku)
            );

            long matched = inventory.updateOne(
                session,
                and(eq("_id", sku),
                    gte("available", 1)),
                Updates.inc("available", -1)
            ).getMatchedCount();

            if (matched != 1) {
                throw new IllegalStateException("OUT_OF_STOCK");
            }

            reservations.insertOne(
                session,
                new Document("tenantId", tenantId)
                    .append("requestId", requestId)
                    .append("sku", sku)
                    .append("state", "CONFIRMED")
            );

            return "CONFIRMED";
        }, txOptions);
    }
}
~~~

### 29.1. This Is a Skeleton, Not Production Checkout Code

Production still needs a unique index on `(tenantId, requestId)`, quantity handling, tenant/product ownership checks, duplicate ledger handling, normalized errors, retry deadlines, and returning success only after confirmed commit. Here `state: "COMMITTED"` is written **inside the transaction**, so it is never visible if the transaction aborts.

### 29.2. `withTransaction` Has Built-In Retry Behavior

The driver convenience API can retry the transaction body or commit according to error labels. The callback must have zero external side effects and remain safe to re-execute per driver semantics. Check your driver version and error-handling contract.

### 29.3. Never Swallow Exceptions and Continue the Transaction

When stock is exhausted, the entire operation must abort; throwing a domain error out of the callback prevents committing without stock. Catching it and returning normally could commit the ledger without a reservation.

### 29.4. Unique Index on the Ledger

~~~javascript
db.requestLedger.createIndex(
  { tenantId: 1, requestId: 1 },
  { unique: true, name: "uniq_tenant_request" }
);
~~~

If the same request ID runs twice, one attempt hits duplicate key. The caller must **reconcile the existing outcome** when payloads match, rather than declaring failure or deducting stock again under a new request ID.

## 30. Transaction Isolation Does Not Replace Business Invariants

MongoDB transactions provide snapshot isolation and atomic commits within supported scope. However, applications must not assume “adding a transaction automatically preserves every cross-document invariant.”

### 30.1. Write Skew Example

Two doctors A and B are on call; the invariant is **at least one doctor must remain on call**. Each doctor is a separate document:

~~~text
doctors:
{ _id: "A", onCall: true }
{ _id: "B", onCall: true }
~~~

Two concurrent transactions:

~~~text
Tx1 reads both A and B on call, lets A leave, writes A.onCall=false
Tx2 reads both A and B on call, lets B leave, writes B.onCall=false
~~~

Because each transaction updates a **different document**, without a shared write conflict or guard, snapshot isolation allows both decisions on the same snapshot, leaving zero doctors on call. This is **write skew** in isolation theory; exact behavior and safeguards must be verified on your MongoDB topology and version.

### 30.2. Protecting with a Shared Guard

Possible solutions:

1. Model all on-call staff in **one document** and update conditionally with `countOnCall > 1`.
2. Use a **guard/sentinel document** updated by both transactions to force a write conflict when both adjust the shift.
3. Use an application-layer/queue serialization protocol with proper guarantees.

The key is routing every invariant-affecting transition through a **shared point of contention**, rather than reading a shared count and mutating disjoint documents.

### 30.3. Testing Write Skew

Have two transaction workers read the same snapshot, synchronize after reading, and write to two distinct documents. Assert the invariant after both finish; if violated, add a guard and retest. Never judge solely by “both transactions committed.”

## 31. MongoDB WriteConflict and Transaction Retries

When two transactions contend on the same document or resource, MongoDB may abort one with a write conflict. The error may carry the `TransientTransactionError` label, signaling that retrying the **entire transaction body** per driver policy is appropriate in supported cases.

### 31.1. Retry from the Start, Not Just One Statement

If a transaction read stock, inserted a ledger entry, and updated status, retrying only the final update against the stale snapshot is unsafe. On transient transaction failures, **restart the transaction** to obtain a fresh snapshot and re-evaluate decisions.

### 31.2. UnknownTransactionCommitResult

If the connection drops after sending commit, the client cannot tell whether the server committed. Errors carrying `UnknownTransactionCommitResult` require **commit retries per driver semantics or reconciliation**, rather than blindly re-running the whole business body from scratch.

### 31.3. Conceptual Handling Table

| Situation | Retry appropriate? | Watch out for |
|---|---|---|
| `TransientTransactionError` | May retry whole transaction body | Bounded retries, side-effect-free callback |
| `UnknownTransactionCommitResult` | Retry commit / reconcile | Never duplicate business effects |
| `OptimisticLockingFailureException` | Only if business allows re-read/recompute | Never overwrite user intent |
| E11000 unique ledger | Reconcile request ID / payload | Request may have already completed |
| Stock predicate mismatch | Usually a business rejection | Never retry blindly to “win” |
| Validation error | Fix input/schema | Never retry identical bad request forever |
| Network timeout | Outcome may be unknown | Stable request identity, query ledger |

### 31.4. Retry Budgets

Enforce max attempts/deadlines, exponential backoff with jitter, conflict metrics, and clear separation between transient and permanent failures. High-load tests must confirm the system avoids retry storms that drive latency unboundedly upward.

## 32. Idempotency Is a Distinct Requirement

Suppose a client sends request `PAY-123`:

~~~text
T1 Client sends PAY-123
T2 MongoDB commits payment
T3 Network drops before response
T4 Client resends PAY-123
~~~

Without a stable request identity, the server cannot distinguish a **new** action from a **retry of the same action**.

### 32.1. Idempotency Key

A ledger with a unique key:

~~~javascript
{
  tenantId: "t-01",
  requestId: "PAY-123",
  payloadHash: "sha256-of-canonical-payload",
  status: "COMMITTED",
  result: { paymentId: "payment-789" }
}
~~~

Unique index:

~~~javascript
db.requestLedger.createIndex(
  { tenantId: 1, requestId: 1 },
  { unique: true }
);
~~~

### 32.2. Same Key, Same Payload

If a second request arrives with the same key and payload hash, return the **persisted result** instead of creating a new payment. While the first request is still executing, use a `PENDING/COMMITTED/FAILED` protocol or appropriate transaction/lease.

### 32.3. Same Key, Different Payload

This indicates misuse or a client conflict; never silently return the old result for a different payload or execute a second payment. Reject with an appropriate conflict error and audit it.

### 32.4. Unique Ledger Must Share the Atomic Boundary When Needed

Writing the ledger in one command and deducting funds in a second command without a transaction or compensation still leaves inconsistent state on a mid-flight crash. Use an atomic transaction or a fully designed state/reconciliation protocol.

## 33. Do Not Confuse Retryable Writes with Exactly-Once Business Operations

MongoDB drivers support retryable writes for supported operations and topologies, preventing duplicate application of a single command when the driver retries within a logical session.

However:

- An HTTP retry routed to another service instance is a **brand-new logical operation** to the driver.
- Application code may generate a fresh `_id` on each attempt.
- A business operation often spans multiple commands, collections, and external service calls.
- Operations like `$inc` are non-idempotent if re-executed as a fresh business request.

### 33.1. Test Both Retry Layers

1. Driver-level retry after a transient network fault within one invocation.
2. Application-level retry of the **entire HTTP request** from the client after a timeout.

Only the second test directly proves the business API's idempotency contract.

### 33.2. Exactly-Once Effects Need Clear Scope

Never promise “system-wide exactly once” when MongoDB and a payment gateway share no atomic transaction. The realistic goal is **effectively once** within a defined boundary: stable operation IDs, deduplication, reconciliation, outbox/inbox, idempotent consumers, and auditing.

## 34. Testing Identical Request IDs Running Concurrently

A proper idempotency test spawns multiple concurrent callers with:

~~~text
tenantId = t-01
requestId = CHECKOUT-123
payload = sku-A, quantity 1, price 120000
~~~

Expected:

1. Callers may observe different intermediate states (COMMITTED/IN_PROGRESS/retry), yet all resolve to **one business result**.
2. The ledger holds **one** entry for `(tenantId, requestId)`.
3. Inventory decreases **once**.
4. Reservation/payment for this request appears **once**.
5. If a caller drops the response and retries, the final outcome matches the original request.

### 34.1. Never Assert Solely on E11000

If a writer hits duplicate key on the ledger *after* already decrementing stock outside the transaction, the unique constraint failed to protect the invariant. Assert on both the ledger **and** inventory.

### 34.2. Avoid Arbitrary Loser Assumptions

Do not assert that exactly one thread gets HTTP 200 and all others get HTTP 409 if the contract specifies duplicate requests return the same success response. HTTP outcomes must follow your **idempotency policy**, not accidental thread scheduling.

## 35. Testing Multiple Distinct Request IDs Competing for Stock

Unlike duplicate retries, these are **independent business requests**:

~~~text
Initial stock = 5
Request IDs = R-1, R-2, ..., R-20
Each quantity = 1
20 concurrent callers
~~~

Invariants:

~~~text
successfulDistinctRequests <= 5
finalStock = 5 - successfulDistinctRequests
finalStock >= 0
confirmedReservations = successfulDistinctRequests
~~~

When all successful reservations are transaction-protected and no validation or network errors occur, **5 successful requests** are expected; under fault injection, classify uncertain outcomes and reconcile before asserting exact counts.

### 35.1. Stress Testing Across Stock Levels

Test with `stock = 0, 1, 5, 100` and `concurrency = 1, 2, 10, 100`. Measure conflicts, retries, p95/p99 latency, and final invariants. Never benchmark on a database shared with unrelated workloads.

### 35.2. More Requests Than CPU Cores

High client concurrency stresses thread schedulers and connection pools, though it does not guarantee every write executes in the exact same nanosecond. The objective is proving invariants hold across diverse interleavings, not literal simultaneous execution.

## 36. Testing Unique Seat Booking Under Concurrency

Create the unique index **before** launching insert workers:

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Indexes;
import com.mongodb.client.model.IndexOptions;
import org.bson.Document;

bookings.createIndex(
    Indexes.ascending("tenantId", "eventId", "seatId"),
    new IndexOptions().unique(true)
);
~~~

Launch 10 concurrent workers inserting:

~~~text
tenantId=t-01, eventId=EV-1, seatId=A-01
each has different booking _id
~~~

Expected:

- Exactly one document exists for that key.
- One insert succeeds; all other attempts leave zero duplicates.
- Duplicate key errors map to business conflicts.
- If the index exists only as an annotation and was never created on the test DB, the test must fail rather than pass silently.

### 36.1. Testing Partial Uniqueness

If policy allows many `CANCELLED` records yet only one `ACTIVE`, test:

~~~text
ACTIVE + ACTIVE => conflict
CANCELLED + CANCELLED => allowed
CANCELLED + ACTIVE => allowed
ACTIVE -> CANCELLED then insert new ACTIVE => allowed
~~~

Test state transitions under contention too, since updating status from `CANCELLED` to `ACTIVE` also triggers unique index enforcement.

## 37. Testing Timeouts and Unknown Outcomes via Fault Injection

Not every concurrency bug involves two threads writing together. Another critical failure mode:

~~~text
Server committed write
Connection closed before client received reply
Client sees timeout
Client retries business request
~~~

MongoDB test deployments can use supported failpoint mechanisms such as `configureFailPoint`/`failCommand` on permitted topologies. Enabling failpoints requires elevated privileges and is **unsuitable for production**; managed Atlas tiers may also restrict them.

### 37.1. Understanding Fault Placement Without Relying on One Failpoint

Tests can place a controlled proxy or network fault between the driver and MongoDB in an isolated environment and observe retry behavior. Note that **dropping the connection before the server processes the command** differs fundamentally from **dropping it after commit yet before the reply arrives**; distinguish both so you test the intended failure mode.

### 37.2. Post-Fault Assertions

After network recovery:

1. Query the ledger by stable request ID.
2. Verify payment/reservation produced only one business effect.
3. Verify stock/balances.
4. For unknown commit outcomes, reconcile before issuing non-idempotent retries.
5. Ensure requests are never stranded indefinitely in `PENDING`.

### 37.3. Fault Injection Is Not Load Testing

Controlled faults prove handling of specific failure modes. Stress/load tests remain necessary to uncover contention, latency, and resource issues.

## 38. Testing Transaction Rollbacks

A multi-collection transaction test:

~~~text
Given stock=0
When transaction inserts ledger then tries to reserve one item
Then stock predicate fails
And transaction aborts
And no ledger/reservation persists
~~~

The key assertion is that **zero partial effects** survive after abort.

### 38.1. Forcing Failure

Trigger an `OUT_OF_STOCK` business rejection, validation error, or controlled exception after an earlier write inside the transaction to verify rollback. You do not need to kill processes or corrupt disks to test atomic rollback.

### 38.2. Verify from an Independent Session Afterward

Read from a separate session/client after abort/commit to verify persisted state rather than inspecting in-memory objects inside the transaction callback.

### 38.3. Transactions Do Not Cover External HTTP Side Effects

If a callback calls a payment gateway before MongoDB aborts, the gateway may still charge the customer. Integration tests should use an idempotent fake/mock external gateway to expose and verify those boundaries.

## 39. Testing Snapshot Reads and Stale Secondaries

Replica sets can serve reads from the primary or secondaries per read preference and read concern. Secondaries can lag:

~~~text
T1 primary commits: stock=0
T2 secondary has not applied oplog yet: stock=1
T3 client reads secondary and renders stock=1
~~~

A UI showing stale stock does not violate the stock invariant as long as the **deduction itself** executes an atomic conditional update on the primary checking `matchedCount`.

### 39.1. Testing Consistency Contracts

- If the API promises only “stock may lag slightly,” stale reads are acceptable.
- If the API promises “once paid, the status is immediately readable,” enforce read-your-writes, causal sessions, or primary reads.
- When balance correctness decides safety, never base final approval on a client-side stale read.

### 39.2. Read Concerns Do Not Replace Write Predicates

`majority` and `snapshot` define read semantics, not conditional write guards. Test read/write ordering across failovers whenever requirements are timing-sensitive.

## 40. Never Use `Thread.sleep()` to Prove Safety

A test like:

~~~java
Thread workerA = new Thread(() -> reserve());
Thread workerB = new Thread(() -> reserve());
workerA.start();
Thread.sleep(10);
workerB.start();
~~~

guarantees no specific interleaving and varies wildly with CI CPU load. `Thread.sleep` can simulate processing delays, yet it **is not a synchronization primitive** for proving concurrency safety.

### 40.1. Tools to Use Instead

| Tool | Role |
|---|---|
| `CountDownLatch` | Wait for N workers to become ready or open a start gate |
| `CyclicBarrier` | Align N workers at a rendezvous point after reading |
| `ExecutorService` | Manage thread pools and task submissions |
| `Future.get(timeout)` | Collect results/exceptions with bounded waits |
| `AtomicInteger` | Tally outcomes in JVM tests (never replaces DB invariants) |
| `CompletableFuture` | Compose async tasks; handle exceptions explicitly |
| `Testcontainers` | Provision isolated test databases per environment |

### 40.2. Place Barriers at the Right Point

To reproduce lost updates, place the barrier **after read, before write**. To test conditional stock updates, a start gate **before the atomic update** suffices to boost contention because correctness does not rely on forcing a race window.

### 40.3. Never Use Test Barriers in Production Transactions

Barriers coordinate threads inside a test process, not distributed service instances. Production must rely on database constraints, transaction protocols, and idempotency.

## 41. Managing Test Isolation

A concurrency test can fail simply because another test ran `deleteMany({})` on a shared collection—not because concurrency logic is broken.

### 41.1. Random Database per Test

~~~java
String dbName = "concurrency_test_" +
    UUID.randomUUID().toString().replace("-", "");
MongoDatabase db = client.getDatabase(dbName);
~~~

After the test:

~~~java
db.drop();
~~~

**Only drop test-created random databases on a test cluster.** Never grant test suites permission to drop production databases. With ephemeral Testcontainers instances, container teardown can replace manual drops.

### 41.2. Transaction Tests Need the Right Topology

A standalone Testcontainers MongoDB setup will fail transaction tests. Use a replica-set-enabled setup and proper readiness checks matching your Testcontainers MongoDB module version. Never assume “Docker container started” means replica set election finished.

### 41.3. Never Parallelize Tests Sharing Fixture IDs

If JUnit runs tests in parallel and two tests both insert `_id="wallet-1"` into the same DB, they will collide. Use namespaced IDs or per-test databases.

## 42. Assertions Must Bind to Invariants

For each concurrent scenario, maintain an expected outcomes table:

| Test | Inputs | Expected persisted state |
|---|---|---|
| Two requests compete for stock=1 | A/B each request 1 | 1 accepted, stock=0 |
| Two requests compete for balance=100k | A/B deduct 80k | <=1 accepted, balance>=0 |
| Two stale editors | Same version | 1 save wins, 1 conflict |
| Two bookings for same seat | Distinct booking IDs, same seat key | 1 active booking |
| Two retries with same request ID | Same payload | 1 ledger + 1 effect |
| Transaction lacking stock | Stock=0 | Zero ledger/reservation commits |
| Transaction abort after write | Controlled failure | Zero partial state |
| Distinct request IDs competing for quota=5 | 20 x qty 1 | <=5 confirmed, non-negative stock |

### 42.1. Never Assert Only Result Counts

Reporting 1 success while stock sits at -1 is still broken. Ending at stock=0 with 2 confirmed bookings is equally broken. Always read persisted database state.

### 42.2. Never Assert Only DB State While Ignoring Responses

If both clients received success while the DB recorded only one booking, the API lied to one customer. Verify both business success counts and result identities.

### 42.3. Check for Orphaned Records

Look for `CONFIRMED` reservations without a matching inventory decrement or payment ledger. Use reconciliation aggregations or queries after retries and injected faults.

## 43. Checking Invariants via Aggregation

Checking active booking counts per seat:

~~~javascript
db.bookings.aggregate([
  { $match: { state: "ACTIVE" } },
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        eventId: "$eventId",
        seatId: "$seatId"
      },
      count: { $sum: 1 }
    }
  },
  { $match: { count: { $gt: 1 } } }
])
~~~

Expected: **zero documents returned**. This verifies the business post-condition while the unique index prevents violations in the database. Both matter because an index might be missing or a partial index filter misconfigured.

### 43.1. Non-Negative Inventory

~~~javascript
db.inventory.find({
  available: { $lt: 0 }
})
~~~

Expected: zero documents.

### 43.2. Duplicate Request Ledger Entries

~~~javascript
db.requestLedger.aggregate([
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        requestId: "$requestId"
      },
      count: { $sum: 1 }
    }
  },
  { $match: { count: { $gt: 1 } } }
])
~~~

Expected: zero documents. Even with a unique index, this cross-checks test setup and legacy data.

### 43.3. Reading Consistent Snapshots for Verification

In transaction tests, read after commit/abort completes using an appropriate connection and read concern so you never assert on unacknowledged state. Across multiple collections, ensure consistent reads when background writers might still be active.

## 44. Property-Based / Randomized Concurrent Testing

Beyond fixed interleavings, generate seeded random operation sequences:

~~~text
Initial stock: 20
Operations:
  reserve(qty=1..5)
  replenish(qty=1..5)
  cancelReservation(...)
  retryExistingRequest(...)
  queryStatus(...)
Concurrent workers: 2..50
Seed: 184726
~~~

At the end, compute expected stock from **confirmed operations and idempotency identities**, not raw HTTP request counts.

### 44.1. Save Random Seeds and Schedule Context

On failure, log the seed, operation IDs, payloads, outcomes, retry counts, and timestamps. Without reproducible inputs, rare races are nearly impossible to debug.

### 44.2. Randomness Does Not Replace Determinism

Randomized stress tests excel at finding unexpected interactions yet cannot guarantee hitting critical interleavings. Keep core barrier-driven tests to block regressions reliably.

### 44.3. Model-Based Testing

Build a **sequential reference model** enforcing business rules on small inputs. Compare final states and histories of the concurrent MongoDB implementation against outcomes permitted by the model.

## 45. Linearizability Checks and Their Limits

For a simple object like a counter or stock item, record a history:

~~~text
operationId, invokedAt, returnedAt, args, result
~~~

Check whether there exists a sequential ordering of operations respecting **real-time precedence** that yields valid outcomes. This is the basis of **linearizability testing**.

### 45.1. Do Not Confuse with Serializable Transactions

Linearizability of a single counter or atomic document update does not mean arbitrary multi-document MongoDB transactions automatically achieve full serializable isolation for every cross-document invariant.

### 45.2. Cross-Machine Clocks

Timestamps across multiple hosts suffer clock skew; distributed linearizability checks require proper instrumentation and clock models. Even within one process, measure invocation/response boundaries carefully.

### 45.3. Histories with Timeouts

A timed-out operation may have committed. In a history checker, never treat an “unknown” outcome as “failed” without reconciling database state—which is why storing operation identities and reading ledgers post-fault matters.

## 46. Testing Performance Under Contention

A design that is functionally correct yet routes every request to a single document creates a **hotspot**:

~~~text
1000 workers
  -> same inventory document SKU-POPULAR
  -> high optimistic conflicts / transaction retries
  -> p99 latency spikes
~~~

### 46.1. Metrics to Collect

| Metric | Question |
|---|---|
| Successful operations/s | Real committed throughput? |
| Business rejections/s | Are OUT_OF_STOCK or conflicts within expectations? |
| Optimistic conflict count | How many `matchedCount=0` / stale saves? |
| Transaction abort/retry count | Is contention high? |
| Duplicate key count | How many requests collided on identity? |
| p50/p95/p99 latency | Are users waiting too long? |
| Retry attempts distribution | Is there a retry storm? |
| Connection pool wait | Is the app starved of connections? |
| MongoDB CPU/I/O/lock metrics | Is the bottleneck server-side or app-side? |
| Ledger reconciliation backlog | Are unknown-outcome requests piling up? |

### 46.2. Rethink the Data Model

If every write must mutate one global quota document, that document becomes an unavoidable serialization point. Expanding the thread pool will not scale throughput endlessly. Consider sharding/partitioning quotas per business semantics, pre-allocating ownership, or queuing—while proving the global quota invariant still holds.

### 46.3. Failing Fast Beats Endless Retries

When `stock=0`, `OUT_OF_STOCK` is a normal business rejection, not a transient infrastructure error to retry 100 times.

## 47. Outbox and Testing External Side Effects

A confirmed order may need to emit external effects:

~~~text
MongoDB order CONFIRMED
Kafka message OrderConfirmed
Email confirmation
Payment gateway capture
~~~

MongoDB transactions do not span Kafka, email providers, or payment gateways. Sending events directly inside a transaction callback risks emitting duplicates if the callback retries even though the DB commits once.

### 47.1. Transactional Outbox

Within the same MongoDB transaction, write both `order` and an `outboxEvent` carrying a stable event ID. A separate publisher dispatches events, while consumers deduplicate by event ID to handle at-least-once delivery.

### 47.2. Testing Duplicate Events

Simulate a publisher dispatching an event successfully and crashing before marking it sent; on restart it publishes again. Verify consumers never deduct inventory or charge twice for the same event ID.

### 47.3. External Payments

Pass idempotency keys to payment providers where supported, and reconcile charge state before retrying. Never claim a MongoDB transaction rolls back an external charge that already succeeded.

## 48. HTTP Contract for Optimistic Conflicts

An API might specify:

~~~text
PUT /orders/O-1001
If-Match: "revision-4"

Body: { "status": "APPROVED" }
~~~

The service maps the revision to expected version and business guards. If stale:

~~~json
{
  "code": "OPTIMISTIC_CONFLICT",
  "message": "Order was modified; reload before saving",
  "currentRevision": "revision-5"
}
~~~

This is an **illustrative API contract**. Standard HTTP `If-Match`/ETag semantics carry specific strong/weak validator rules; implement them accurately if adopting ETags.

### 48.1. Conflicts Are Rarely HTTP 500

Normal stale edits should return `409 Conflict` or `412 Precondition Failed` per API contract. Never alert on ordinary optimistic conflicts as severe server crashes.

### 48.2. Never Leak Unauthorized State

If a caller lacks permission to view an order, a conflict response must not leak `currentRevision` or sensitive details revealing the record exists.

### 48.3. Transparent Retry Semantics

The API should clearly distinguish:

- `OUT_OF_STOCK`: business rejection.
- `OPTIMISTIC_CONFLICT`: stale version; reload required.
- `DUPLICATE_REQUEST`: idempotency key reused with a different payload.
- `IN_PROGRESS`: same key currently executing.
- `TEMPORARY_UNAVAILABLE`: eligible for bounded retry.

## 49. Multi-Step Scenarios to Test

| Scenario | Easy-to-miss bug |
|---|---|
| User double-clicks Pay button | Two distinct HTTP requests with identical intent |
| Client times out and mobile app retries | Duplicate effect due to fresh client identity |
| Worker restarts after stock update | Missing reservation or ledger entry |
| Concurrent approval and cancellation | Unenforced state machine |
| Secondary lag while viewing stock | Stale UI display, yet write decision must stay atomic |
| Two admins edit full document | Lost update from unversioned replace/save |
| Bulk updates via migration script | Bypasses Spring Data `@Version` protocol |
| Payment provider returns unknown | Blind retry charges twice |
| Unique index not built yet | Double booking slips through |
| Transaction callback retries | External event emitted twice |
| TTL deletes ledger too early | Late client retry looks like a brand-new request |
| Shard migration/failover | Network errors and unknown outcomes unhandled |

### 49.1. Idempotency Ledger Retention

If the ledger expires entries after 24 hours while clients can retry after 7 days, retention is too short. Tie TTL/retention to the **maximum replay horizon, audit needs, and business contract**, not just disk savings.

### 49.2. Clocks and Timing

Tests using timestamps must account for timezone, clock skew, and millisecond precision. For expiration boundaries, never rely on `Thread.sleep` to prove exact boundary expiry; inject a `Clock` into business logic wherever possible.

## 50. Practice A — Classifying Anomalies

Given:

1. Two editors read version 3; the second replaces the full document and wipes out a field edited by the first.
2. Two checkout requests both read `stock=1` and each deducts 1.
3. Two transactions each take one doctor off call based on a snapshot showing two doctors on call.
4. A client loses the reply after commit and resends the identical payment.

Name each anomaly, identify the broken invariant, and propose the safeguard for each case.

## 51. Practice B — Conditional Stock Update

Write an `updateOne` guarding `available >= quantity`, with `quantity > 0` validated in the service. Two independent requests compete for `stock=1`. Write assertions for success count, final stock, and booking count.

## 52. Practice C — Lost Update

Use `CyclicBarrier(2)` so both workers read `count=0` before replacing. Explain why final `count` ends at 1. Then replace with atomic `$inc` and update the expected final count to 2.

## 53. Practice D — CAS

Create `{_id:"x", count:0, version:0}`. Two workers both filter on `version=0`. How many `matchedCount=1` results are expected? Write a bounded retry loop so both valid business increments eventually apply.

## 54. Practice E — Spring Data `@Version`

Create a `Wallet` entity with `@Version Long version`. Read two copies at the same version. Save A, then save B. Verify B's exception and the persisted balance. Why do unacknowledged writes make conflict detection unreliable?

## 55. Practice F — Order Status

Order is `PENDING`, version 7. Two workers race `APPROVED` vs `CANCELLED`. Design a filter enforcing expected status and version. List the allowed business states once both finish and what the losing writer receives.

## 56. Practice G — Unique Seat

Create unique index `(tenantId, eventId, seatId)`. Launch 20 workers inserting the same seat with distinct `_id`s. Check booking count. If the domain forbids two `ACTIVE` bookings yet allows multiple `CANCELLED` records, how should the index change?

## 57. Practice H — Idempotency

Send 10 concurrent HTTP requests with the same `requestId="PAY-123"` and identical payload. Design the unique ledger index, transaction/atomic boundary, and retry response logic. State invariants for payment charges and ledger rows. What if the payload differs under the same key?

## 58. Practice I — Transaction Rollback

A transaction inserts a ledger entry, then tries to reserve stock when `available=0`. Business code throws `OUT_OF_STOCK`. After abort, do the ledger entry or reservation exist? Which assertions prove rollback?

## 59. Practice J — Transient vs Unknown Commit

Distinguish handling `TransientTransactionError` from `UnknownTransactionCommitResult`. Why does retrying the **entire business body** immediately after an unknown commit risk duplicating effects?

## 60. Practice K — Write Skew

Doctors A and B both have `onCall=true`. Each transaction reads both and updates a separate document. Why can 0 doctors end up on call? Propose a shared guard document or single-document model to protect the invariant.

## 61. Practice L — Raw Update Bypassing Version

One service uses Spring Data `@Version`, while a scheduled job runs raw `updateOne({_id}, {$set:{...}})`. Design a test showing how the job's write path causes a version-based editor to miss edits, and propose a codebase rule to fix it.

## 62. Practice M — Fault Injection

Simulate network loss after a business write commits yet before the client receives the reply. Why does a client timeout not prove the write failed? How do request IDs, ledger reconciliation, and retry policies achieve a single business effect?

## 63. Practice N — Concurrency Matrix

Starting with `stock=5`, test request counts `1, 2, 5, 10, 100` and quantities `1, 2, 5, 6`. Identify invariants to assert across every scenario, including requests exceeding stock and retries sharing a request ID.

## 64. Practice O — Monitoring Contention

Measure p95/p99 latency, optimistic conflict counts, transaction aborts, duplicate keys, retry attempts, and throughput when 100 workers contend on one SKU. Why can increasing a thread pool from 100 to 1000 actually **reduce** throughput?

## 65. Practice Answer Hints

**A:** 1 lost update → CAS/`@Version`; 2 check-then-act/oversell → conditional update; 3 write skew → shared guard/single-document invariant; 4 duplicate business request → idempotency key/ledger/reconciliation.

**B:** Filter `{_id: sku, available: {$gte: qty}}` with `$inc: {available: -qty}` in one command, validating `qty > 0`. With `stock=1` and two `qty=1` requests: at most one succeeds, final `stock >= 0`; if creating a reservation, create exactly one via transaction/protocol.

**C:** The post-read barrier forces both workers to compute `0+1`; the last replace writes `count=1`. Atomic `$inc` produces `count=2` across two accepted operations.

**D:** At most one `matchedCount=1` at `version=0`; the loser re-reads `version=1`, performs a bounded retry, and final count/version reflect two accepted increments.

**E:** Stale B must fail with `OptimisticLockingFailureException` using version-aware save and acknowledged writes, leaving A's balance persisted.

**F:** Either `APPROVED` or `CANCELLED` wins; both cannot succeed from `PENDING` with expected status/version; the loser receives a conflict/rejection.

**G:** A single unique key allows only one booking; for multiple `CANCELLED` histories and one `ACTIVE`, use a partial unique index on `state: "ACTIVE"` and test transitions.

**H:** Unique ledger on `tenant + requestId`, payload hash, persisted result, and atomic boundary with payment effect. Same key/same payload returns stored result; same key/different payload returns conflict.

**I:** Transaction abort discards all inner writes: zero ledger/reservation rows remain and stock stays 0; assert from an independent session.

**J:** Transient transaction errors can retry the whole body per driver support; unknown commit requires retrying commit or reconciling, never blindly re-running non-idempotent operations.

**K:** Both transactions read the same snapshot yet update disjoint documents with no write conflict; use a shared guard document, single quota document, or serialization policy.

**L:** Raw updates lacking version predicates/increments bypass detection. Require all writers to honor the same protocol and add cross-path integration tests.

**M:** Timeout means unknown outcome, not confirmed rollback; read the ledger by stable request ID and use idempotent retries to prevent duplicate effects.

**N:** Assert `stock >= 0`, `confirmedUnits <= initial + replenished`, one effect per request ID, zero orphan reservations; `quantity > stock` rejected.

**O:** One hot document drives conflicts/retries, spiking CPU and connection waits; contention makes extra threads slower, requiring rate limits, backoff, or data-model redesign.

## 66. Common Implementation Mistakes

| Mistake | Risk | Fix |
|---|---|---|
| Read stock then update by `_id` | Oversell / negative stock | Atomic predicate `available >= qty` |
| Replace full document without version | Lost update | `@Version` or CAS |
| Split data and version updates into two commands | Race between data/version | One atomic update |
| Catch optimistic conflict and return success | Masks stale writes | Domain conflict / reload |
| Retry stale form infinitely | Overwrites user intent | Business merge policy |
| Use `modifiedCount` for every business result | Misinterprets no-ops | Clear contract on matched/acknowledged |
| Declare unique index annotation without building index | Double bookings | Assert index exists in integration tests |
| Retry duplicate insert with new ID | Fails to resolve seat conflict | Check business key / ledger |
| Write ledger outside stock transaction | Partial state on crash | Atomic boundary / reconciliation |
| Call payment gateway inside transaction callback | Duplicate charge on retry | Outbox / idempotent external protocol |
| Retry whole body after unknown commit | Double business effect | Commit retry / reconcile |
| Blur transient vs business errors | Retry storms | Error taxonomy |
| Use `Thread.sleep` to manufacture races | Flaky tests | Barriers / latches |
| Share test DB and run `deleteMany({})` | Cross-test interference | Database / fixture isolation |
| Test transactions on unsupported standalone | Invalid test environment | Replica-set-enabled tests |
| Assert only HTTP 200 | Misses DB invariant bugs | Validate persisted state |
| Assert only `stock=0` | Misses double-successes | Validate result counts and reservations |
| Reuse request ID with a different payload | Identity confusion | Payload fingerprint + conflict |
| Short ledger TTL | Late retries cause double effects | Retention >= replay horizon |
| Test only one interleaving | Misses other races | Deterministic + stress + fault tests |
| No timeout on Futures/barriers | Hung CI | Bounded waits / cleanup |

## 67. Review Questions

**1. What does single-document atomicity protect?** — A single document update executes atomically within MongoDB's guarantees; it does not combine multiple separate commands into a transaction.

**2. Why can read-then-write fail?** — Two writers read the same stale state and decide before either writes.

**3. What is a lost update?** — One writer silently overwrites another writer's committed edit.

**4. How to safely increment a counter?** — Atomic `$inc` or versioned CAS depending on semantics.

**5. How to decrement stock without going negative?** — `updateOne` with `available >= qty` and `$inc: -qty` in one atomic operation.

**6. Why must `quantity` be validated?** — Zero, negative, or mistyped quantities invert or break update predicates.

**7. What does CAS filter on?** — ID/owner/business predicate and expected version.

**8. When must `version` increment?** — Inside the same successful write command.

**9. Does `matchedCount=0` prove a stale version?** — No; the document could be missing, belong to another tenant, or fail a business predicate.

**10. What does Spring Data `@Version` help with?** — Detecting stale saves/versioned updates via version predicates.

**11. Can unacknowledged writes reliably test optimistic locking?** — No, because confirmed match counts are missing.

**12. Does a raw MongoDB update automatically respect POJO `@Version`?** — No; the raw query must send the version predicate and increment.

**13. Is an optimistic conflict the same as MongoDB `WriteConflict`?** — No; they originate at different layers with different retry semantics.

**14. When should a unique index be used?** — To enforce business key uniqueness under concurrent inserts and updates.

**15. Does a unique index protect total stock quotas?** — No; a separate invariant design is needed.

**16. What are transactions used for?** — Atomic commit or abort across multiple operations within MongoDB's supported scope.

**17. Can a MongoDB transaction protect an external payment gateway directly?** — Not directly; idempotency, outbox, and reconciliation are needed.

**18. Does snapshot isolation prevent all write skew?** — Never assume so; use shared guards or single-document models.

**19. How is `TransientTransactionError` handled?** — Retry the full transaction body per driver semantics and retry budget.

**20. What does `UnknownTransactionCommitResult` mean?** — The client is unsure if commit succeeded; retry commit or reconcile.

**21. Is DuplicateKey always an error requiring retry?** — No; it may signal a business conflict or an idempotent retry.

**22. What is an idempotency key for?** — Identifying retries of the same logical business request.

**23. How to handle the same key with a different payload?** — Reject as a conflict; never silently reuse the old outcome.

**24. Do atomic updates automatically make HTTP retries idempotent?** — No.

**25. Why place `CyclicBarrier` after the read?** — Forces both workers onto the stale snapshot to reproduce lost updates.

**26. Is `Thread.sleep` sufficient for concurrency tests?** — No; thread scheduling is non-deterministic.

**27. Does a mocked repository test MongoDB atomicity?** — No; integration tests against real MongoDB are required.

**28. Which topology do multi-document transaction tests require?** — A supported replica set or sharded cluster, not plain standalone.

**29. Why isolate test databases?** — Prevents tests from wiping each other's fixtures and protects production.

**30. Why assert DB state in addition to API responses?** — Responses can lie or get lost even while writes committed.

**31. Can a stale secondary alone cause overselling?** — It can show stale UI data, while a proper atomic write predicate on primary still protects stock invariants.

**32. What is the impact of a hot document?** — Higher contention, retries, and tail latency.

**33. Should `OUT_OF_STOCK` be retried hundreds of times to “win”?** — No; it is a normal business rejection.

**34. When is optimistic locking suitable?** — Low-to-moderate contention where stale edits must be detected and reloaded/merged.

**35. When is a concurrency test complete?** — Both responses and persisted invariants hold, errors/timeouts are classified, and teardown cleans up.

## 68. Quick Reference Table

| Problem | Solution / Test |
|---|---|
| Lost update on replace | `@Version` or expected-version CAS |
| Counter increment | Atomic `$inc` |
| Non-negative stock | `updateOne({_id, available: {$gte: qty}}, {$inc: {available: -qty}})` |
| Stale Spring Data entity | `OptimisticLockingFailureException` |
| Unique seat/email | Unique / partial unique index |
| Deduct stock + insert reservation | Transaction or single-document atomic model |
| Resent request | Stable idempotency key + ledger + payload hash |
| Unknown commit | Commit retry / reconcile per driver semantics |
| Transient transaction failure | Bounded full-transaction retry |
| Write skew | Shared guard / single-document invariant |
| Reproduce lost update | `CyclicBarrier` after read |
| Competing start | `CountDownLatch` start gate |
| Threads/tasks | `ExecutorService`, `Future.get(timeout)` |
| Test MongoDB semantics | Real MongoDB integration test |
| Test transactions | Replica-set-enabled test topology |
| Validate post-conditions | Database queries/aggregations + response counts |
| Retrying external effects | Outbox / idempotent consumer / reconciliation |
| Production contention | Conflict/retry metrics, p95/p99, backoff |

## 69. Pre-Release Testing Checklist

- [ ] Are business invariants expressed as explicit assertions?
- [ ] Is every invariant scoped clearly to one document vs multiple documents/services?
- [ ] Do all stock/balance deductions enforce atomic predicates at write time?
- [ ] Are input quantities, money values, and ownership validated?
- [ ] Do all optimistic writes check expected version and increment it atomically?
- [ ] Do all write paths (repositories, raw driver, scripts) honor `@Version`?
- [ ] Is write concern strong enough to detect stale versions?
- [ ] Are response contracts defined for optimistic conflict, not found, and business rejections?
- [ ] Do unique indexes actually exist on the database, not merely as annotations?
- [ ] Do partial unique indexes, filters, and collations match business states?
- [ ] Do MongoDB transactions wrap writes that must commit atomically together?
- [ ] Are abort/rollback, transient retries, and unknown commit tested?
- [ ] Are transaction callbacks free of non-idempotent external side effects?
- [ ] Are idempotency keys stable per tenant/operation with payload fingerprints?
- [ ] Do concurrent/retried calls with the same request ID yield exactly one business effect?
- [ ] Is ledger TTL/retention longer than the maximum replay window?
- [ ] Are distinct request IDs tested competing for shared stock/quotas?
- [ ] Is lost update tested deterministically with a post-read barrier?
- [ ] Are barriers/futures bounded by timeouts with thread pool cleanup?
- [ ] Do tests run against real MongoDB in isolated databases?
- [ ] Do transaction tests use an appropriate replica-set/sharded topology?
- [ ] Do tests refuse to fall back to production URIs when test config is missing?
- [ ] Do assertions verify both API responses and persisted invariants?
- [ ] Are checks run for duplicate bookings, negative stock, and orphan ledger/reservation records?
- [ ] Are concurrent business state machine transitions tested?
- [ ] Are stale secondaries and read-consistency contracts tested where required?
- [ ] Are stress tests run across multiple concurrency levels with reproducible seeds?
- [ ] Is fault injection tested for timeouts/unknown outcomes where supported?
- [ ] Are conflict/retry/abort/latency/throughput metrics and retry budgets tracked?
- [ ] Do rollback and reconciliation plans exist for data discrepancies?

## 70. Conclusion

Concurrency testing in MongoDB must start with the question: **“Which business states must never exist?”** A single-document update is atomic, yet read-then-write logic still races. `@Version` protects stale saves, yet never replaces a unique index. A transaction commits multiple writes together, yet does not automatically cover external payment side effects or every cross-document invariant.

For inventory and balances, prefer **atomic conditional updates** guarding conditions at write time. For multi-editor or read-modify-write workflows, apply **optimistic locking/CAS** to detect stale versions and return conflicts or recompute per business rules. For identities like seats, emails, or request IDs, enforce **unique indexes and idempotency ledgers**. When an operation spans multiple documents, use transactions within MongoDB's supported scope alongside controlled retries, unknown-commit handling, and reconciliation.

Finally, never trust a sequential test or two threads launched “close together.” Use **barriers and latches to reproduce interleavings**, real MongoDB to verify semantics, stress and fault tests to widen coverage, and assertions on **persisted state**: zero negative stock, zero double bookings, zero lost updates, zero double charges, and zero orphan records. A system is truly reliable only when **every permissible concurrent outcome** still preserves its business invariants.
