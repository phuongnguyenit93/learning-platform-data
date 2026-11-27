# Strong Consistency, Eventual Consistency, and Business Requirements

In a distributed system, the same data may be stored across multiple nodes, database replicas, caches, or regions. When a user updates data, copies do not necessarily see the change at the same time. A read request immediately afterward may receive the new value, the old value, or a result assembled from multiple versions. This is the problem of **consistency**.

Choosing a consistency model is not simply choosing a fast database. It is a decision about **what the business allows users to observe, which invariants must always be protected, and how the system is allowed to react when the network is partitioned or a replica lags**. A booking application can accept a view count increasing with a few seconds of delay, but it cannot arbitrarily confirm two customers holding the same single slot.

In the **CLOUD_ARCHITECTURE** module, this lesson connects data design with reliability, performance, security, cost, and operations using a Well-Architected mindset. The focus is distinguishing **strong consistency** from **eventual consistency**, understanding intermediate guarantees, and mapping them to business requirements.

## 1. What does consistency mean?

At a high level, consistency describes which read/write results a system allows users to observe when data is updated, replicated, or accessed concurrently. However, the word "consistency" has multiple meanings:

| Context | Meaning |
| --- | --- |
| **Consistency in ACID** | A transaction moves a database from one valid state to another valid state according to defined constraints and rules |
| **Consistency model of a distributed system** | Defines the relationship between read/write operations across multiple replicas or nodes |
| **Eventual consistency** | If there are no new updates and propagation continues to succeed, replicas eventually converge to the same state |
| **Strong consistency / linearizability** | Every operation can be viewed as occurring at a single point in time between its start and completion, while respecting the real-time ordering of completed operations |
| **Causal consistency** | Causally related operations are observed in their corresponding order; operations without causal relation may be observed in different orders |

Do not equate ACID consistency with strong consistency across multiple regions. A single-node database with ACID transactions can still have a cache or read replica returning stale data. Conversely, a strongly replicated system can provide linearizable reads/writes for a single key without guaranteeing that a sequence of updates across multiple tables is an ACID transaction.

### Simple example

An account has a balance of 1,000,000 VND. The user transfers 200,000 VND:

1. The system writes the new balance of 800,000 VND.
2. A read replica in another region has not yet received the update and returns 1,000,000 VND.
3. The user sees the old balance even though the transaction already reported success.

For an application displaying reports a few seconds behind, that may be acceptable. For an operation authorizing spending, returning the old balance can lead to a wrong decision. The consistency model must be chosen based on **the meaning of the data and the actions taken based on that data**.

## 2. Strong consistency and eventual consistency

### Strong consistency

Strong consistency is often used to describe a strong guarantee such as linearizability: after a write operation succeeds, subsequent reads that start afterward see that write (or a newer value), following a global order consistent with real time.

For example, a reservation transaction is confirmed successfully. A lookup request that begins after the confirmation time needs to see that the slot is already reserved. This prevents clients from making decisions based on stale state for critical data.

Benefits:

- Easier to reason about read/write ordering and build business invariants.
- Reduces situations where a client reads immediately after a write and receives a stale result.
- Suitable for operations that must decide based on the latest state, such as allocating unique resources or recording ledger entries.

Trade-offs:

- May require coordination across replicas/quorums, increasing latency.
- During a network partition or when required replicas are insufficient, the system may reject or wait on some operations to preserve the guarantee.
- Strong consistency across multiple regions can be noticeably affected by network distance and round-trip time.
- Operational overhead, capacity, and failover design can be higher.

### Eventual consistency

Eventual consistency allows replicas to differ temporarily. The system propagates changes asynchronously, and replicas converge once synchronization completes and no competing new updates arrive.

For example, a user changes their profile picture. The API saves the new information to the data source, and then events update the cache and search index. During the first few seconds, some pages may still show the old picture. If the business accepts that delay, there is no need to wait for all projections to finish updating before returning success.

Benefits:

- Reduces synchronous waiting across components and regions.
- Maintains the ability to accept certain types of updates when connectivity to other replicas is unavailable.
- Suitable for projections, caches, analytics, feeds, search indexes, and reconstructible data.

Trade-offs:

- Clients may read stale values after a write.
- Multiple concurrent operations can create conflicts or different orderings.
- Requires handling duplicates, out-of-order events, retries, replay, and reconciliation.
- The application must represent syncing states or data freshness timestamps.

### Quick comparison

| Criterion | Strong consistency | Eventual consistency |
| --- | --- | --- |
| Read immediately after write | Under strong guarantees, sees the confirmed write | May see stale values during convergence |
| Replica coordination | Typically requires coordination/quorum per the model | Can propagate asynchronously |
| Latency | Can be higher, especially cross-region | Typically reduces waiting time on the write path |
| Write availability during partition | May be restricted in some models | Can accept local writes if conflict rules allow |
| Conflict handling | Can avoid some conflicts via serialization/locking | Requires merge, versioning, conflict policy, or accepting overwrites |
| Use case | Balances, reservations, uniqueness, critical access permissions | Feeds, search projections, analytics, caches, aggregated views |

Do not treat the two choices as a single switch for the entire system. A product typically needs **strong consistency where invariants are protected**, while using eventual consistency for projections and secondary features.

## 3. Intermediate guarantees: read-your-writes, monotonic reads, and causal consistency

Strong and eventual are not the entire space of consistency models. Many systems provide or require session-based and causal guarantees.

| Guarantee | Meaning | Experience example |
| --- | --- | --- |
| **Read-your-writes** | After a successful write, a client sees its own writes on subsequent reads within the committed scope | A user updates their profile name, refreshes, and still sees the new name |
| **Monotonic reads** | A client does not observe data moving backward to an older version within the same session | After seeing an order status of "shipping", it does not revert to "confirmed" |
| **Monotonic writes** | Writes from the same client are applied in the order they were sent | Changing an address and then updating delivery instructions are not applied out of order |
| **Causal consistency** | If operation B depends on A, an observer does not see B before seeing A | A reply comment only appears after the original post |
| **Session consistency** | Combines several consistency guarantees within the scope of a user session | A session reads its own prior updates from that session |

Exact names and guarantee levels vary across databases/caches/frameworks. You must check the exact contract: whether the scope is a single key, a transaction, a session, a client, or the entire cluster.

### Read-your-writes example

A user edits their profile via an API in region A. The write succeeds on the primary, but the reload request is routed to a lagging read replica in region B. The user sees the old name and thinks the action was not saved.

Several ways to handle this:

- After a write, keep sticky routing to the primary for an appropriate time window.
- Return a version/commit token so subsequent reads require the replica to reach at least that version.
- Temporarily read from a stronger source for that specific client.
- Update the UI from the write response and show a syncing indicator if the projection is still lagging.

Each approach has different costs and limits. Sticky sessions can reduce load-balancing effectiveness; reading from the primary increases primary load; tokens must be supported throughout the query layer.

## 4. Do not confuse consistency with availability and durability

These three properties are related, but they answer different questions:

- **Consistency:** under what rules are read/write operations allowed to be observed?
- **Availability:** does the system respond to requests within a defined timeframe?
- **Durability:** is acknowledged data preserved after the specified types of failures?

A database can have strong consistency yet reject writes when quorum is not met. An eventually consistent store can accept writes in multiple places during a partition, but require reconciliation afterward. A write that returns success without proper durability can still be lost after a crash if commit/replication settings do not meet requirements.

Therefore, do not say "strong consistency means data is never lost" or "eventual consistency means the database is always available." Describe read/write semantics, target availability, and durability/backup separately.

## 5. CAP theorem: understanding it correctly under network partitions

CAP is a lens for viewing distributed systems when a **network partition** occurs:

- **Consistency (C)** in the CAP formulation is typically close to linearizability: every node behaves like a single copy of the data.
- **Availability (A)** means every request to a non-failing node receives a valid response (not necessarily the latest value).
- **Partition tolerance (P)** means the system continues to be evaluated under network conditions that split nodes so they cannot exchange messages.

When a partition occurs, a system cannot simultaneously guarantee both strong consistency in the linearizability sense and availability for every request on every side of the partition. It must choose to make some operations wait/fail to preserve consistency, or continue responding with the possibility that sides hold different states.

~~~mermaid
flowchart TD
    P["Network partition occurs"]
    P --> DEC{"Which priority for the operation?"}
    DEC -->|Preserve linearizability| C["Wait / reject some requests\nto avoid returning conflicting data"]
    DEC -->|Continue responding| A["May accept local data\nand reconcile later"]
~~~

CAP does **not** mean a system picks exactly two out of C, A, and P in all situations. Partition tolerance is a real-world condition that distributed systems must account for; the meaningful choice is how each operation behaves when a partition occurs. When the network is healthy, a design can still optimize both consistency and availability in different ways.

CAP also does not replace decisions about latency, durability, transaction isolation, backups, or data quality. Do not use a single CP/AP label to evaluate a database without specifying the operation, failure mode, and semantics.

## 6. PACELC: trade-offs even when the network is healthy

PACELC extends the CAP discussion by asking an additional question: **if there is no partition, what trade-off does the system still make between latency and consistency?**

- During a **P** (partition), the system typically must choose between **A** (availability) and **C** (consistency).
- **E** (else), when there is no partition, the system typically trades off **L** (latency) and **C** (consistency).

For example, a write that requires acknowledgment after multiple replicas receive the data can be more strongly consistent, but it must wait for a round trip. A write that waits only for the local replica can be faster, but other replicas see it later. PACELC is a mental framework, not a complete classification label for every service.

### Why multi-region makes the trade-off obvious

Geographic distance increases communication time. If every transaction must wait for a quorum spanning multiple regions, p95/p99 write latency can increase. If writes happen in one region and replicate asynchronously, users in other regions may read stale state. The design must answer:

- Does the user need to read the newly written data immediately?
- Can the user be routed to the region that owns the data?
- Can secondary regions serve read-only traffic when connectivity is lost?
- If a region is lost, how is unreplicated data handled?
- Are there requirements for data to reside within a specific jurisdiction/region?

There is no "multi-region is always better" option. For some workloads, regional single-writer plus read projections elsewhere is simpler and safer than active-active multi-writer.

## 7. Replication, quorum, and write acknowledgment semantics

Replication creates multiple copies to improve read capacity, reliability, or resilience. However, **the number of replicas alone does not specify how far a write is guaranteed**. You must understand which replicas acknowledge, whether replication is synchronous or asynchronous, and what happens when a node/region loses connectivity.

### Synchronous and asynchronous replication

| Replication mode | When is a write acknowledged? | Advantages | Trade-offs |
| --- | --- | --- | --- |
| **Synchronous** | Per contract, waits for one or more replicas to acknowledge before returning success | Reduces the chance of losing acknowledged writes under designed failure modes | Adds round trips, depends on replicas/quorum; may reject writes when components are insufficient |
| **Asynchronous** | Primary acknowledges before replicas receive the change | Reduces write latency and immediate dependency on distant replicas | Replica lag; failover may lose unreplicated writes |
| **Semi-synchronous / quorum-based** | Waits for a configured number of members or acknowledgment condition | Balances latency and data protection per configuration | Requires understanding exact quorum conditions, voting members, and node-loss scenarios |

Terminology is not guaranteed to be identical across products. Some systems' "synchronous" waits for log flush to disk; others wait for a replica to receive or commit. Always verify what point is acknowledged: received, written, flushed, or committed.

### Read/write quorums

In some replicated key-value stores, quorums are modeled using:

- \(N\): number of replicas storing a key.
- \(W\): number of replicas required to acknowledge a write.
- \(R\): number of replicas queried during a read.

If \(R+W>N\), the read replica set and write acknowledgment set overlap in the simple model. If \(W>N/2\), two write quorum sets also overlap. However, **overlap alone does not prove linearizability**: it also depends on versioning, write ordering, read repair, hinted handoff, sloppy quorums, concurrent writes, and consensus algorithms.

For example, \(N=3, W=2, R=2\) shows the minimum participating replicas. Yet if replicas are out of sync, the client reads two copies with different versions, and the system picks a value using an unreliable timestamp, the result can still violate business invariants. Inspect the engine's consistency semantics rather than reasoning from three numbers alone.

### Read repair and anti-entropy

Some systems detect when replicas return different data during a read and update the older copy (read repair). An anti-entropy process compares data in batches to detect and fix divergence without waiting for a client to read that specific key. These mechanisms aid convergence, but they do not replace backups and do not necessarily resolve all logical conflicts.

## 8. Transaction isolation is not the same as replica consistency

A system can replicate strongly across replicas and still allow transaction anomalies if the isolation level is lower than required. Conversely, serializable transactions on a primary database do not automatically guarantee that a read replica in another region returns the latest data.

Common isolation levels:

| Isolation level | General meaning | Risks/anomalies to know |
| --- | --- | --- |
| **Read uncommitted** | Can read uncommitted data in systems supporting this level | Dirty reads and other anomalies |
| **Read committed** | Reads only committed data; each statement may see a different snapshot | Non-repeatable reads, phantoms depending on the DBMS |
| **Repeatable read** | Reads of the same data within a transaction have stronger stability guarantees | Phantoms or anomalies depending on the database implementation |
| **Serializable** | Result is equivalent to a valid serial execution order | May require transaction retries, reduce concurrency, or increase cost |

Isolation level names are standardized conceptually, but actual implementations differ across engines. Read the database documentation and test relevant anomalies. For example, "check that one slot remains, then decrement by one" is unsafe if two transactions both read the old value and then update without an atomic conditional update, lock, or appropriate constraint.

### Atomic conditional update example

Suppose an `inventory` table has a row with an `available` column. You can perform a conditional update in a single statement:

~~~sql
UPDATE inventory
SET available = available - 1
WHERE item_id = :item_id
  AND available > 0;
~~~

The application checks the number of affected rows. If it is one, the reservation successfully decremented the count under the database's concurrency control; otherwise, there is no stock/slot left or the item does not exist. A real booking needs proper transactions and constraints for the entire booking flow; this example illustrates moving the invariant into an atomic operation instead of an unsafe read-then-write split.

### Lost update and write skew

- **Lost update:** two transactions read the same value, each computes a result from the old value, and the later write overwrites the earlier write.
- **Write skew:** two transactions read a valid snapshot and then update different rows, yet the combined result violates a business constraint.

Write skew example: an on-call scheduling system requires at least one staff member on duty at all times. Two transactions both read that two people are on duty; each transaction removes a different person from the schedule. Without appropriate constraints or serializable coordination, after both commit, no one is on duty.

## 9. Mapping consistency to business requirements

Do not choose strong consistency for all data just because it is easy to describe, nor eventual consistency just to increase throughput. Start from **business invariants** and the actions users or systems take on the data.

| Data / journey | Invariant or expectation | Model typically considered |
| --- | --- | --- |
| Account balance | Cannot spend beyond balance; ledger must not be duplicated | Transactions and strong write control at the source of truth |
| Final slot booking | At most one booking confirmed per slot | Atomic transaction/constraint/serialization |
| Inventory | Must not oversell beyond business-allowed quantity | Atomic conditional update or transaction |
| Access permissions and revocation | Must not continue allowing sensitive access based on a long-lived stale cache | Strong read or cache invalidation/short TTL depending on risk |
| Order status | Must not regress to an earlier business state | Transition validation, versioning, causal/order guarantee |
| Product catalog | Description updates can lag by a few seconds | Eventual consistency/cache |
| Search index | Can lag behind the transactional source | Projection/eventual consistency, surface freshness when needed |
| Analytics dashboard | Can aggregate in batches or streams | Eventual consistency |
| View counts / feeds | Can accept approximate counts or delayed updates | Eventual/approximate aggregation |

### Ask impact-based questions instead of technical labels

For each piece of data, ask:

1. What happens if a user reads a stale version for 100 ms, 5 seconds, or 5 minutes?
2. Does any action cause financial, legal, security, or resource-allocation harm if the data is stale?
3. Can two users update the same entity at the same time?
4. Can two updates be merged, or must one side be rejected?
5. Does the client need read-your-writes or monotonic reads?
6. When a region loses connectivity, can certain writes pause or must all updates continue to be accepted?
7. Who and which system is responsible for reconciling discrepancies?

Do not use "this data is unimportant" as a reason for choosing eventual consistency. State clearly **the maximum acceptable lag, UI behavior, discrepancy detection process, and recovery path**.

## 10. Conflict handling in eventually consistent systems

When multiple nodes can accept writes before synchronizing, the same entity can be modified in multiple places. When changes meet, the system must have rules to resolve them.

### Common strategies

| Strategy | How it works | Suitable when | Limitations |
| --- | --- | --- | --- |
| **Last-write-wins (LWW)** | Picks the version with the timestamp/version considered latest | Simple state where overwrites are acceptable | Clock skew can pick the wrong version; concurrent updates are lost |
| **Version/vector clock** | Tracks version or causal relationships to detect concurrent updates | Need to identify true conflicts | Complex metadata and merge logic |
| **Application-level merge** | Merges according to business rules | Profiles, documents, configs with clear merge rules | Must handle each data type explicitly |
| **CRDT** | Uses data structures with operations designed to converge when merged | Counters, sets, distributed state with matching semantics | Not all business invariants can be expressed this way |
| **Single-writer/leader** | Only one node has write authority for a key/partition at a time | Data needing clear write ordering | Depends on leader, failover, and routing |
| **Reject-and-retry** | Detects stale version/conflict and asks the caller to reload or retry | Sensitive updates where the user can choose how to resolve | User experience may need to handle conflicts |

### Last-write-wins and the clock problem

If two regions write two values at the same time, the system may choose the larger timestamp. However, machine clocks are not necessarily synchronized to absolute accuracy; clock skew can cause an older write to be treated as newer. For critical data, you need timestamps/versions from a source with clear semantics or another ordering mechanism. LWW is only valid when **overwrite semantics** fit the business.

### CRDTs are not magic

A Conflict-free Replicated Data Type (CRDT) is a structure with update and merge operations designed to converge without coordinating every operation. For example, a grow-only counter can merge counts from multiple nodes by summing separate per-node components; a grow-only set can merge elements using set union.

However, CRDTs do not solve every problem on their own. For instance, "do not sell more than 10 tickets" cannot be solved simply by independent increment-only counters across regions without quota allocation or coordination; regions could collectively oversell the total. CRDTs must be chosen based on data structure and invariants that merge operations can preserve.

### Conflict resolution must be audited

When the system automatically merges or discards a version, record:

- The entity/key in conflict and the versions involved.
- The source/region or actor that created each version.
- The merge algorithm/rule version applied.
- Pre-merge and post-merge values and the reason.
- Whether an operator or user needs to intervene manually.

For financial data, access permissions, or regulated data, do not silently overwrite without an audit trail and reconciliation process.

## 11. Eventual consistency in event-driven architectures

A common way to build an eventually consistent read model is to write data to the source of truth and emit events for consumers to update projections, caches, or search indexes.

~~~mermaid
flowchart LR
    API["Booking API"] --> DB["Booking database"]
    DB --> OUTBOX["Transactional outbox"]
    OUTBOX --> BROKER["Message broker"]
    BROKER --> SEARCH["Search indexer"]
    BROKER --> CACHE["Cache updater"]
    BROKER --> ANALYTICS["Analytics consumer"]
~~~

This flow reduces synchronous coupling between booking and read models. Booking can return success once the transaction and outbox commit; search/cache/analytics update afterward. You must ensure the publisher does not drop events and consumers safely handle duplicate or out-of-order events.

### Transactional outbox

If an application commits a booking in the database and then publishes a message independently, there are two failure windows:

1. The database commit succeeds, but the process crashes before publishing: the data exists, but the event is lost.
2. Publishing succeeds, but the process crashes before recording that it published: the event may be sent multiple times.

The transactional outbox solves the lost-event window by writing the booking and the outbox record in **the same database transaction**. A relay reads unsent records and publishes them to the broker; the relay can send duplicates, so consumers must still be idempotent.

### Idempotent consumers and event ordering

A consumer can store the processed event ID alongside the projection update in a single transaction. If the same event ID arrives again, it skips the second side effect. For events belonging to the same entity, an aggregate version/sequence can detect stale or missing order:

- If the received version is less than or equal to the already-applied version, consider ignoring the duplicate/stale event per the contract.
- If the version jumps with a gap, you may need to wait, replay, or fetch a snapshot from the source.
- If two events are truly concurrent, apply the defined conflict rule.

Ordering solely by timestamp can be unsafe if clocks are unsynchronized; a monotonically increasing version at the entity's owning source is easier to reason about. Partitioning the broker by entity key can preserve ordering within a partition, but does not automatically guarantee global ordering across partitions.

### Convergence lag

Set targets for the lag from write commit to projection update:

- p50/p95/p99 event lag.
- Time from outbox creation to publish.
- Queue wait time and consumer processing time.
- Number of retried/dead-lettered events.
- Projection age and version compared to the source.

An eventual consistency contract must state **under what conditions it converges**: for example, 99% of search index updates appear within 5 seconds under normal load; overdue events trigger alerts and replay. Do not claim "it will eventually be consistent" without mechanisms guaranteeing event delivery, consumer health, and error detection.

## 12. Cache consistency and invalidation

Caching reduces latency and database load, but it introduces another copy of data that can become stale. When a write updates the source, the cache must be updated, deleted, or expired according to policy.

### Strategies

| Strategy | Flow | Risks |
| --- | --- | --- |
| **Cache-aside** | Read cache; on miss, read database and populate cache. On write, update DB then invalidate cache | Race between stale read and cache fill; cache can become stale |
| **Write-through** | Write through the cache layer and update the source per the system's mechanism | Adds latency; semantics depend on cache implementation |
| **Write-behind / write-back** | Cache accepts writes first and flushes to the store later | Cache holds unpersisted data; risk of loss on crash |
| **TTL-based** | Data expires after a predefined duration | Maximum staleness can approach TTL plus propagation time |
| **Event-driven invalidation** | Events from the source trigger cache eviction/update | Events can be delayed, duplicated, or lost without outbox/replay |

### Race condition in cache-aside

1. Request A gets a cache miss and reads an old value from the DB.
2. Request B updates the DB to a new value, then deletes the cache entry.
3. Request A finishes slowly and writes the old value into the cache.
4. Subsequent requests keep reading the old value until TTL expires or the cache is invalidated.

You can reduce this risk with version/fencing tokens on cache fills, conditional cache updates, short TTLs aligned with staleness tolerance, or reading directly from a strong source for critical paths. No invalidation approach is immune to races; you must understand write/read concurrency.

### Caches should not decide critical invariants

A cache of available slot counts can serve list displays, but final booking confirmation must use an atomic operation/transaction at the owning data source. Access-permission caches may need short TTLs or strong invalidation to revoke access promptly. Acceptable staleness depends on the harm of making decisions from stale data.

## 13. CQRS and read models with different consistency levels

Command Query Responsibility Segregation (CQRS) separates the write model (commands) from the read model (queries). The write model protects invariants and transactions; events/projections update read models optimized for search or dashboards.

For example:

- The booking write model stores reservations, enforces uniqueness, and tracks transaction state.
- The search read model stores data tailored for filtering/searching and can update with a slight delay.
- The dashboard read model aggregates booking counts and revenue by minute.

CQRS can reduce load on the write source and allow query models to be optimized independently. However, it introduces **multiple data copies and multiple synchronization states**; you need outbox, replay, versioning, reconciliation, lag observability, and UX handling when the read model has not yet caught up.

Not every application needs CQRS. If a single table and a few simple queries work well, adding an event broker and projections only adds complexity.

### Read-your-writes in CQRS

A user who just created a booking can receive a response containing the booking ID and status from the write model. If they immediately open the search list before the projection updates, the booking may appear to have vanished. You can:

- Display the newly created result in the UI from the write response.
- Provide an endpoint to read details directly from the write model by ID right after creation.
- Return a projection version/consistency token and wait for the read model to reach that version.
- Keep newly created items in the client session until the search index converges.

Do not block every write command until all search/analytics projections finish updating unless the business requires it.

## 14. Sagas and multi-step workflows

When a business workflow spans multiple services/databases, a global ACID transaction may be infeasible or inappropriate. A saga splits the workflow into local transactions, where each step can have a compensating action if a later step fails.

Booking example:

1. The Booking service reserves a slot.
2. The Payment service requests payment collection.
3. When payment succeeds, Booking transitions the state to confirmed.
4. If payment fails, Booking releases the slot via a compensating action.

~~~mermaid
sequenceDiagram
    participant B as Booking
    participant I as Inventory
    participant P as Payment
    B->>I: Reserve slot
    I-->>B: Reserved
    B->>P: Charge payment
    alt Payment success
        P-->>B: Paid
        B->>I: Confirm reservation
    else Payment failure
        P-->>B: Failed
        B->>I: Release reservation (compensation)
    end
~~~

Compensating actions are not instant rollbacks like single-database transactions. Payment may have already charged the user while the callback arrives late; refunds can take time; releasing a reservation can also fail and require retries. A saga requires a durable state machine, idempotent commands, timeouts, deadlines, retry policies, compensation, and manual reconciliation.

If two changes must always commit together under a tight invariant and live in one database, keeping them in a single transaction can be simpler and more accurate. Only split into a saga when business boundaries and operational benefits are clear enough.

## 15. Case study: booking platform and limited inventory

A booking platform sells 100 slots for a time window. During a campaign, thousands of users may send requests within a few seconds. The system has three requirements:

- No more than 100 bookings may be confirmed.
- A booker must see their booking immediately after the API reports success.
- Search, popular lists, and dashboards can update a few seconds later.

This is a good example of choosing a consistency model **per capability**, rather than forcing the entire platform onto one model.

### Step 1 — Define the invariant

Let \(A\) be the number of available slots and \(B\) be the number of confirmed bookings. The invariant to preserve is:

\[
A\geq0,\qquad A+B=100
\]

In practice, there are also temporary holds, expirations, cancellations, and indeterminate payments. Include those states in the domain model and define when a slot counts as sold.

### Step 2 — Keep transactional writes at the owning source

Booking/Inventory uses transactions and atomic conditional updates to decrement available slots if any remain. Appropriate constraints or locks protect the invariant under concurrent requests. Requests carry an idempotency key so client retries do not create duplicate bookings.

The search index and dashboard receive events after the write transaction succeeds. They may lag, but they must never be used as the final decision source for selling the last slot.

### Step 3 — Update projections asynchronously

~~~mermaid
flowchart TB
    CLIENT["Client"]
    API["Booking API"]
    DB["Booking / Inventory database"]
    OUTBOX["Outbox event"]
    BROKER["Message broker"]
    SEARCH["Search projection"]
    DASH["Dashboard aggregate"]
    CLIENT --> API
    API --> DB
    DB -->|Commit booking + outbox| OUTBOX
    OUTBOX --> BROKER
    BROKER --> SEARCH
    BROKER --> DASH
~~~

After commit, the Booking API returns the result and ID. The search projection updates from events; the dashboard can aggregate in batches. If a message is duplicated, consumers use the event ID/version so they do not double-count revenue or booking totals.

### Step 4 — Handle user experience

Right after creating a booking, the client displays the status from the write-model response. If the user opens the search list and the result has not updated yet, the UI can:

- Show the newly created booking in a "Recent" section from the response.
- Mark the list as updating or display the sync timestamp.
- When the user opens details by booking ID, read from the write model or an endpoint with read-your-writes.

Do not delay booking confirmation until analytics/dashboards update, as that is not a required business condition.

### Step 5 — When replicas or events lag

If a read replica lags, the system can route requests requiring read-your-writes back to the primary or use a consistency token if the database supports it. If search events lag, measure queue lag and display the projection's freshness state; if events fail, retry/DLQ and replay after fixing.

### Step 6 — When two users book the last slot simultaneously

Two requests reading one remaining slot simultaneously can happen if the application separates reads and writes. Therefore, never use a prior read result to decide on your own. Both send a conditional update:

~~~sql
UPDATE inventory
SET available = available - 1
WHERE slot_id = :slot_id
  AND available > 0;
~~~

Only the transaction whose update succeeds proceeds to create the reservation within the same transaction or under a protocol guaranteeing atomicity. The other request receives a sold-out response. Verify unique constraints, idempotency, transaction boundaries, and behavior when the commit succeeds but the response is lost.

### Architectural outcome

| Component | Required consistency level | Reason |
| --- | --- | --- |
| Inventory/booking write | Strong/transactional per invariant | Prevents overselling and duplicate bookings |
| User's own booking detail | Read-your-writes or read from strong source | Avoids a user who just booked seeing nothing |
| Search index | Eventual | A few seconds of delay is acceptable |
| Dashboard | Eventual/batch | Aggregate metrics do not decide transactions |
| Available-slots list cache | Bounded staleness allowed | Used only for display, not confirming reservations |

## 16. Case study: multi-region profile updates

A global application allows users to edit their display name and profile picture across multiple regions. If two devices edit the same profile while offline and then sync, the system must resolve conflicts.

### Distinguish fields

- **Display name:** can use optimistic concurrency with a version; if a conflict is detected, ask the user to choose or apply a published merge rule.
- **Profile picture:** store new files as objects keyed by key/version; update the metadata pointer using version checks. On concurrent writes, pick a version using a business rule rather than relying solely on timestamps from two arbitrary clocks.
- **Email / login identifier:** typically requires uniqueness and verification; do not let two regions independently accept the same email and merge later without coordination.
- **Change history:** store audits/events so users or support can inspect changes.

### Optimistic concurrency control

A client reads profile version 12, then sends an update referencing the current version:

~~~http
PUT /profiles/123
If-Match: "12"
Content-Type: application/json

{"displayName":"Linh"}
~~~

The server applies the update only if the version is still 12; if another device already updated to version 13, the server returns a conflict (such as HTTP 412 per the contract). The client reloads, displays the diff, or resubmits according to defined rules.

This pattern prevents silent overwrites when two users edit concurrently. It does not by itself resolve all multi-region conflicts; you still need an authoritative version owner or an ordered sync/merge mechanism.

## 17. API design when data may not have converged yet

APIs must make clear **what has been committed** and **what is still synchronizing**.

### Return version and update timestamp

The response may include:

~~~json
{
  "bookingId": "bkg_123",
  "status": "CONFIRMED",
  "version": 42,
  "committedAt": "2026-11-18T10:20:30Z"
}
~~~

This example is an illustrative schema. Version can be used to reconcile projections; the timestamp helps display time, though it is not necessarily a global causal order. Do not expose internal database LSNs or sensitive tokens unless the API contract requires them.

### Projection sync state

A read/search API can return metadata:

~~~json
{
  "items": [],
  "projectionVersion": 40,
  "sourceVersion": 42,
  "asOf": "2026-11-18T10:20:28Z",
  "consistency": "EVENTUAL"
}
~~~

This lets clients see that the projection is two versions behind in the example. In practice, source/projection versions are only comparable when they share the same scope and semantics. If the data spans multiple aggregates, use watermarks or per-partition checkpoints instead of a single version number.

### Commands and queries should have distinct contracts

- Commands answer whether the operation was accepted/committed at the write source.
- Queries state the read source, freshness, or consistency level the caller receives.
- If read-your-writes is required, the client passes a consistency token/version per the contract.
- If an operation is asynchronous, return a job/operation ID and a status-tracking endpoint.
- On conflict, return a handleable error instead of silently overwriting.

Do not label every API response `EVENTUAL` if consumers do not know the maximum lag, and do not return `CONFIRMED` before the transaction has actually committed.

## 18. Observing and operating consistency

Eventual consistency is only operable when the team knows how far replicas/projections are lagging and has a way to recover. Strong consistency also requires monitoring latency/quorums to detect when coordination becomes a bottleneck.

| Signal | Meaning | Alert when |
| --- | --- | --- |
| Replication lag | Delay of replica behind source | Exceeds read-your-writes threshold or RPO |
| Quorum failure / unavailable writes | Insufficient members satisfy the write policy | Critical transactions cannot commit |
| Conflict rate | Number of concurrent versions needing resolution | Spikes abnormally or merges repeatedly fail |
| Event delivery lag | Outbox/broker/consumer is slow | Projection exceeds stale budget |
| Dead-letter count | Unprocessable events | Increases or persists past threshold |
| Projection version lag | How far behind the source the read model is | Consumers observe stale state beyond SLA |
| Cache stale rate | Cache serves old versions or invalidation is delayed | Sensitive journeys exceed stale tolerance |
| Reconciliation mismatch | Discrepancy between source and projection/aggregates | Persistent mismatch or financial data does not balance |
| Read-your-writes fallback rate | Frequency of forcing reads from the strong source | Abnormally high, increasing primary load |

### Dashboards and traces

Track metrics by database/region/keyspace/consumer, but avoid putting high-cardinality user IDs or entity IDs into metric labels. Use access-controlled traces/logs to investigate individual events or operations. Correlation IDs, aggregate IDs, event IDs, and versions connect writes to projections.

### Reconciliation process

1. Identify the authoritative data source for each type of information.
2. Select the time range/partition with lag or mismatch.
3. Compare versions/checksums/counts in a way that does not overload the source.
4. Replay events or rebuild projections from the source when needed.
5. Verify no duplicate side effects are produced.
6. Record an audit entry, update metrics, and notify business owners.

For financial data, reconciliation must use the authoritative ledger; never fix total revenue simply by re-summing a dashboard without identifying which transactions are missing or duplicated.

## 19. Process for selecting a consistency model

A consistency decision can be executed in the following steps:

### Step 1 — List data and owners

Document entities, sources of truth, replicas, caches, read models, regions, consumers, and external systems. Each data type needs an owner responsible for defining invariants and handling reconciliation.

### Step 2 — Write business invariants

For example:

- Inventory counts are non-negative.
- A slot does not have two confirmed bookings.
- A payment operation is recorded at most once.
- Order status does not move backward from `DELIVERED` to `PROCESSING`.
- Only authorized users can read profile data.

Write invariants as testable conditions, not vague descriptions like "data is always right."

### Step 3 — Define acceptable staleness

For each read path, specify how stale it can be: zero staleness allowed, up to 100 ms, 5 seconds, a few minutes, or only needing convergence before end-of-day reporting. Staleness must be tied to the action users perform on that result.

### Step 4 — Choose consistency boundaries

Place strong/transactional consistency where invariants are protected; choose read-your-writes or causal consistency for session experiences; choose eventual consistency for projections/caches/analytics if the business accepts it. Avoid distributed transactions when invariants can be kept within a single data boundary.

### Step 5 — Select data and replication mechanisms

Determine primary/single-writer vs. multi-writer, sync/async replication, quorums, transaction isolation, conditional updates, unique constraints, versioning, and conflict resolution. Verify the database's actual contract.

### Step 6 — Design events and recovery

If projections exist, use outbox/CDC or a reliable event-publishing pattern; idempotent consumers, versioning/ordering, retries, DLQs, replay, reconciliation, and backups.

### Step 7 — Design APIs and experience

Return operation IDs, versions, pending states, or freshness metadata when needed. Define behavior on stale reads, conflicts, timeouts, or region disconnects.

### Step 8 — Measure, test, and review

Measure latency, replication lag, event lag, conflict rate, duplicates, mismatches, and cost. Run drills for partitions, node loss, out-of-order events, retries, replay, and restores. Set thresholds for when to change the model or add capacity.

~~~mermaid
flowchart TD
    DATA["Data + owner"] --> INV["Business invariants"]
    INV --> STALE["Acceptable staleness"]
    STALE --> BOUNDARY["Consistency boundary"]
    BOUNDARY --> MECH["Replication / transaction / events"]
    MECH --> API["API contract + UX"]
    API --> TEST["Test + observe + reconcile"]
    TEST --> REVIEW["Review SLO / cost / risk"]
    REVIEW --> STALE
~~~

## 20. Testing consistency

Happy-path testing with a single client is not enough. You must create contention and network-fault scenarios to verify semantics.

| Test case | Simulation | What must be proven |
| --- | --- | --- |
| Concurrent write | Multiple clients updating one entity simultaneously | Invariants are not violated; conflicts are detected |
| Read-after-write | Read immediately after a successful write on another replica | Read-your-writes holds per contract |
| Partition | Block communication between replicas/regions | CP/AP or per-operation policy matches commitments |
| Replica lag | Intentionally slow down replication | Stale reads are detected or bounded properly |
| Out-of-order event | Send event version N+1 before N | Projection does not regress or corrupt state |
| Duplicate delivery | Deliver the same event multiple times | Consumer produces no duplicate side effects |
| Missing event | Disrupt publisher/consumer | Outbox/replay/DLQ recovers |
| Cache race | Interleave stale reads, new writes, and cache invalidation | Stale values stay within staleness tolerance |
| Region failover | Lose the primary region | Actual RPO and post-failover writer source are clear |
| Restore/rebuild | Restore database/projection from backup/events | Data and invariants are verified |

### Invariant-based testing

Instead of checking only HTTP responses, continuously assert business conditions:

- Total confirmed bookings never exceed capacity.
- Ledger balance never decreases erroneously relative to confirmed transactions.
- Each idempotency key produces at most one business outcome.
- Projection version never exceeds an uncommitted source version.
- Entity states only follow allowed transitions.
- Sensitive data never appears in unauthorized read models.

You can use property-based tests, concurrency tests, or fault injection to generate varied operation orders. After each run, read from the authoritative source and verify invariants.

### Consistency tests must test recovery

A system might handle a partition properly yet fail to converge after the network recovers due to lost events or unmerged conflicts. Therefore, tests must run across all three phases:

1. **Before fault:** establish baseline data and state.
2. **During fault:** generate competing updates or split the network; observe what nodes return.
3. **After fault:** restore connectivity, wait for replication/replay, compare final state, and verify invariants.

## 21. Common mistakes

1. **Equating ACID consistency with strong consistency across replicas:** the two guarantees operate at different layers.
2. **Using eventual consistency for financial/booking invariants without coordination:** can cause overselling, double spending, or invalid states.
3. **Using strong consistency for every read model:** increases latency and coordination even when reports/search tolerate delay.
4. **Saying "eventual" will converge on its own without event delivery/replay:** dropped messages or failing consumers can leave projections permanently out of sync.
5. **Treating CAP as a static "pick two of three":** ignores partition conditions and per-operation semantics.
6. **Assuming overlapping quorums alone guarantee linearizability:** it still depends on versioning, ordering, leadership, and algorithms.
7. **Using LWW timestamps when clocks are unreliable:** can discard valid updates.
8. **Splitting data sources and doing non-atomic dual-writes:** one service updates while the other fails.
9. **Failing to handle duplicate/out-of-order events:** corrupts projections, double-counts metrics, or regresses state.
10. **Invalidating cache after commit without considering races:** an old request can repopulate stale cache after deletion.
11. **Using search/cache as the confirmation source for transactions:** lagging read models can make wrong decisions.
12. **Not exposing staleness to clients:** users see stale data without understanding sync state.
13. **Lacking reconciliation:** small discrepancies accumulate into major bugs unnoticed.
14. **Not testing partitions and recovery:** a model works on a stable network but fails when replicas lag or disconnect.
15. **Splitting every transaction into a saga:** adds intermediate states and compensations when a local transaction would suffice.

## 22. Practice exercise and reference answers

An e-commerce platform has the following requirements:

- Inventory for a product has only 1 unit left.
- Two customers in two regions click buy almost simultaneously.
- The product listing screen may lag by up to 10 seconds.
- After a customer receives order confirmation, the detail page must show the newly created order.
- The revenue dashboard accepts per-minute updates.
- When the cross-region network partitions, the system must prioritize not overselling.

### Question 1 — Choose consistency for inventory

**Reference answer:** Strong/transactional consistency at the inventory write source, using conditional updates/locking/unique invariants. During a partition, reject or hold purchase requests in regions that do not own the writer instead of continuing to sell from a stale replica.

### Question 2 — Choose consistency for the product listing

**Reference answer:** Eventual consistency can fit because the business allows up to 10 seconds of lag. Track projection/cache lag metrics, alert when exceeding the stale budget, and ensure the final purchase operation re-checks the inventory source.

### Question 3 — Why not use the dashboard to confirm orders?

**Reference answer:** The dashboard is a per-minute aggregated projection; it may not have updated right after commit or may round/group data. The order detail page should read from the write model or support read-your-writes using a version/token.

### Question 4 — What can happen if both regions write inventory during a partition?

**Reference answer:** Each region may see one unit remaining and both confirm an order, causing overselling. If the business prioritizes preventing overselling, use single-writer/ownership or coordination/quorum; regions unable to meet write conditions must wait, reject, or accept requests in a controlled pending state.

### Question 5 — If the OrderCreated event is delivered twice, will the dashboard double-count revenue?

**Reference answer:** No, if the consumer is idempotent. Store the event ID / processed marker and update the projection within the same transaction or an equivalent guarantee. If events carry versions, discard duplicates/stale events per the contract.

### Question 6 — After the region recovers, how do you know projections have converged?

**Reference answer:** Compare source versions/watermarks, event lag, checksums/counts, or reconcile by partition. Replay missing events, resolve conflicts, and verify invariants; do not simply wait a fixed period and assume everything is synced.

### Question 7 — Give an example where strong consistency is unnecessary

**Reference answer:** The revenue dashboard or product listing can use projections/eventual consistency if maximum staleness is acceptable to the business and freshness is communicated. There is no need to block purchase transactions waiting for the dashboard to update.

## 23. Architecture review checklist

- Does every piece of data have a clear source of truth and owner?
- Are business invariants written as testable conditions?
- Have read paths been classified as needing strong, read-your-writes, causal, or eventual consistency?
- Is maximum acceptable staleness specified per journey?
- Are transaction isolation and replica consistency evaluated separately?
- Are sync/async replication, commit acknowledgments, quorums, and failure modes well understood?
- During a partition, which operations wait, reject, read stale data, or continue accepting writes?
- How are conflicts detected/merged/rejected? Is there an audit trail?
- Do events have outbox/replay, idempotent consumers, versioning/ordering, and DLQs?
- What race conditions and stale windows exist in cache invalidation?
- Do APIs support versions, conflicts, operation status, or read-your-writes when needed?
- Are metrics tracked for replication lag, projection lag, conflicts, duplicates, and reconciliation mismatches?
- Have concurrent writes, partitions, failovers, replay, and restores been tested?
- Do latency, network, replica, broker, and operational costs fit SLOs and budget?

## 24. Well-Architected assessment

| Pillar | Key question | Evidence |
| --- | --- | --- |
| **Reliability** | When partitions, replica lag, or duplicate events occur, do invariants hold and can the system recover? | Quorum policy, RPO/RTO, outbox, idempotency, fault tests |
| **Security** | Can read models/caches expose data or retain revoked permissions for too long? | IAM, authorization, cache invalidation, audit |
| **Performance Efficiency** | Does strong consistency push latency past SLOs? Do eventual projections lag too long? | p95/p99, replication lag, queue lag, read/write throughput |
| **Cost Optimization** | Are replicas, coordination, events, storage, and reconciliation justified by business value? | Cost per operation, network transfer, broker/storage bill |
| **Operational Excellence** | Can the team detect mismatches, replay, and reconcile? | Dashboards, alerts, runbooks, ownership, restore/reconcile drills |
| **Sustainability** | Do we avoid keeping unnecessary replicas/copies and expire data properly? | Retention, right-sizing, data lifecycle |

A good consistency decision clearly states **what must be right immediately, what can be right later, what users see during the transition, and how the system proves convergence**. That is the foundation for choosing databases, replication, and event-driven architectures based on business requirements rather than technology labels.
