# Deduplication store

In a Spring Kafka system, a **deduplication store** provides durable tracking indicating whether a message or business event has already been processed within a defined scope. When the same event reappears due to consumer redelivery, producer retry, retry topics, DLT replay, or a client resending a command, the consumer can query the store to decide whether to execute the side effect again.

A deduplication store is typically implemented as a relational database table such as **processed_events/inbox**, a key-value store like Redis, or specialized storage. The most critical design choice is not raw lookup speed alone, but the **atomicity boundary**: recording that an event was processed must be properly coordinated with the business side effect. If the marker succeeds and the side effect fails, replayed messages may be skipped permanently. If the side effect succeeds but the dedup marker was not saved, redelivery may repeat the side effect.

This lesson belongs to the **Correctness and Idempotency** chapter in the **Spring Kafka Reliability Operations** module. It covers identity and key scope, inbox/processed-message stores, atomic transactions, concurrency and unique constraints, TTL/retention, Redis versus relational databases, retry/replay/DLT, partitioning, observability, migrations, failure modes, and runbooks.

## 1. What problem does a deduplication store solve?

Kafka consumers normally track progress via committed offsets. If a listener completes a business operation but the process crashes before the offset is committed, the record can be redelivered. Kafka does not automatically know whether a database transaction or external HTTP side effect has completed.

Example:

~~~text
Kafka record: eventId=evt-42, offset=100
       |
       v
Consumer receives record
       |
       v
Database decrements inventory successfully
       |
       v
Process crashes before Kafka offset commit
       |
       v
Consumer restarts and receives offset 100
       |
       v
Without dedup: inventory could be decremented a second time
~~~

A deduplication store helps identify events already applied and prevents repeating business effects:

~~~text
Consumer receives event evt-42
       |
       v
Check processed_events
       |
       +-- Absent -> process and mark atomically
       |
       +-- Present -> skip repeated side effect
~~~

The goal is **at-least-once delivery with idempotent business effects**. The store does not make Kafka delivery system-wide exactly-once; it enables the application to control duplicates within the protected business operation scope.

## 2. Distinguishing deduplication from related concepts

| Concept | Purpose | Example |
|---|---|---|
| Deduplication | Recognize that the same event/command was already processed | eventId already exists in inbox |
| Idempotency | Repeating the same operation produces no additional effect | Reserving stock twice still reserves only once |
| Inbox pattern | Persist message identity and processing state at the consumer | processed_events table |
| Outbox pattern | Persist events to publish in the same business transaction | outbox_events table |
| Kafka idempotent producer | Prevent duplicates from producer protocol retries within session/protocol scope | enable.idempotence |
| Kafka transactions | Atomically commit Kafka outputs and consumed offsets within a Kafka transaction | consume-transform-produce |
| Cache | Store data for fast reads | Product lookup cache |

A deduplication store is usually part of an inbox/idempotency design. A cache can assist lookups, but should not automatically serve as the durable source of truth if eviction, failover, or restarts can drop keys before the duplicate window ends.

Kafka producer idempotence also does not replace a consumer-side deduplication store. The two mechanisms protect different failure boundaries.

## 3. Choosing which identity to deduplicate on

This is a foundational decision. A Kafka record carries attributes:

- cluster;
- topic;
- partition;
- offset;
- key;
- headers;
- payload.

A business event may carry:

- eventId;
- eventType;
- aggregateId;
- tenantId;
- occurredAt;
- schemaVersion.

A command may carry:

- commandId;
- idempotencyKey;
- clientId;
- tenantId.

**Kafka topic-partition-offset** identifies a specific record within a Kafka log. It works well for identifying the exact same record being redelivered. However, when an event is republished to another topic or replayed, a new offset appears.

**Business event ID** is usually better suited for deduplicating the same event across producer retries, retry topics, DLT, and replays. This holds true only when the producer ensures eventId is stable and unique within the defined scope.

Do not use payload hash as the default identity. Two independent business events can have identical payloads, such as two orders for the same item and quantity. Conversely, the same event may serialize differently after schema evolution.

## 4. Defining the deduplication key scope

An event ID may be globally unique, unique per tenant, or unique only within one producer. The deduplication key must reflect the actual contract.

Example:

~~~text
eventId = evt-42
consumer = inventory-service
tenant = tenant-a
~~~

Key options:

~~~text
event_id
(consumer_name, event_id)
(tenant_id, event_id, consumer_name)
(event_source, event_id, processing_contract)
~~~

A table keyed solely by event_id can suffer collisions if two tenants or producers generate IDs in separate namespaces. A table using global event_id is safe only when the system enforces true global uniqueness.

Consumer name/processing contract also matters. The same event may need to be processed once by inventory-service and once by billing-service. Storing only a global eventId in a shared store could wrongly block the second service.

Define the key with a clear statement, such as: "Each OrderCreated event is applied at most once per tenant in inventory-service."

## 5. Designing the processed_events schema

A minimal relational table:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(120) NOT NULL,
    event_id VARCHAR(200) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

If eventId is unique only within a tenant:

~~~sql
CREATE TABLE processed_events (
    tenant_id VARCHAR(100) NOT NULL,
    consumer_name VARCHAR(120) NOT NULL,
    event_id VARCHAR(200) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, consumer_name, event_id)
);
~~~

The primary key/unique constraint is the most important element for resolving races across multiple consumer attempts. Checking then inserting in two separate operations without a unique constraint lets two threads both see "absent" and both run the side effect.

Optional additions:

- source topic/partition/offset;
- event type;
- payload/schema version;
- status;
- processed timestamp;
- correlation/trace ID;
- processing version;
- sanitized failure metadata.

You do not need to store the full payload in the dedup table if the goal is only to recognize processed events. Storing large payloads inflates index/storage size and can introduce privacy risks.

## 6. Inbox table with processing state

A simple insert-marker design fits when insertion and side effect share one transaction. For long workflows or when state inspection is needed, store state:

~~~sql
CREATE TABLE inbox_events (
    consumer_name VARCHAR(120) NOT NULL,
    event_id VARCHAR(200) NOT NULL,
    status VARCHAR(24) NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error_code VARCHAR(80),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Example states:

| State | Meaning |
|---|---|
| RECEIVED | Event has been recorded, not yet processed |
| PROCESSING | A worker is processing it, if workflow uses claim/lease |
| COMPLETED | Business operation completed |
| FAILED_RETRYABLE | Error eligible for retry per policy |
| FAILED_TERMINAL | Error requiring recovery/manual action |
| REPLAY_PENDING | Scheduled for replay per workflow |

The state machine must have explicit transition rules and concurrency controls. Never set COMPLETED before the business transaction actually commits.

For short listeners inside a single database transaction, a complex state machine is usually unnecessary: inserting the inbox marker, executing the side effect, and committing in the same transaction is sufficient.

## 7. Atomicity: writing dedup marker and side effect in the same transaction

This is the golden rule of a relational inbox.

~~~text
BEGIN DATABASE TRANSACTION
    |
    +-- INSERT processed_events(eventId)
    |
    +-- Apply business side effect
    |
COMMIT
~~~

If the marker insert fails due to the unique constraint, the event was already processed in that scope. If the business operation throws an exception, the transaction rolls back both the marker and the side effect.

Spring example:

~~~java
@Service
public class InventoryEventProcessor {

    private final JdbcTemplate jdbcTemplate;
    private final InventoryRepository inventoryRepository;

    public InventoryEventProcessor(
            JdbcTemplate jdbcTemplate,
            InventoryRepository inventoryRepository) {
        this.jdbcTemplate = jdbcTemplate;
        this.inventoryRepository = inventoryRepository;
    }

    @Transactional
    public boolean process(OrderCreated event) {
        int inserted = jdbcTemplate.update(
            """
            INSERT INTO processed_events(consumer_name, event_id)
            VALUES (?, ?)
            ON CONFLICT DO NOTHING
            """,
            "inventory-service",
            event.eventId()
        );

        if (inserted == 0) {
            return false; // Duplicate already applied previously.
        }

        inventoryRepository.reserve(
            event.orderId(),
            event.items()
        );

        return true;
    }
}
~~~

Listener:

~~~java
@KafkaListener(
    topics = "orders.events",
    groupId = "inventory-worker"
)
public void onOrderCreated(OrderCreated event) {
    inventoryEventProcessor.process(event);
}
~~~

In the PostgreSQL example, ON CONFLICT DO NOTHING relies on the unique constraint. Equivalent syntax in other databases differs. Ensure the Spring transaction manager and JDBC/JPA repositories participate in the same transaction manager/database transaction.

When the method returns false, the listener can finish normally; the container then commits the offset per AckMode/error-handling policy. Do not throw an exception just because a duplicate was properly suppressed, if your contract treats duplicate suppression as success.

## 8. Why not insert the marker first and commit separately?

Dangerous design:

~~~text
Transaction A:
  INSERT processed_events(eventId)
  COMMIT

Business operation:
  reserve stock
  FAIL

Kafka redelivers event
  |
  v
Dedup marker exists
  |
  v
Consumer skips event
  |
  v
Stock was never reserved
~~~

This is a **false dedup**: the store claims the event was processed even though the business effect never completed.

The reverse design is also dangerous:

~~~text
Business operation commits
       |
       v
Process crashes before dedup marker insert
       |
       v
Kafka redelivers
       |
       v
Business operation runs again
~~~

For side effects inside the same relational database, the safe pattern is placing marker and business write in the same transaction.

If the side effect is in a system outside the database, one SQL transaction cannot be atomic with an HTTP call or payment provider. In that case, you need an idempotency key at the target system, outbox/saga, or a stateful workflow with reconciliation.

## 9. Unique constraint resolves race conditions

Suppose two consumer attempts process the same event nearly simultaneously:

~~~text
Worker A: SELECT eventId -> not found
Worker B: SELECT eventId -> not found

Worker A: reserve stock
Worker B: reserve stock

Worker A: INSERT marker
Worker B: INSERT marker
~~~

If you only SELECT then INSERT without a proper unique constraint/locking, both can execute the side effect.

Insert-first design:

~~~text
Worker A: INSERT eventId -> success, owns processing
Worker B: INSERT eventId -> unique conflict/no-op

Worker A: apply side effect -> commit
Worker B: sees duplicate -> skip
~~~

The unique constraint is the database arbiter. It resolves contention even when two application instances have no knowledge of each other.

In PostgreSQL, INSERT ... ON CONFLICT DO NOTHING is a common approach. In other databases, use an equivalent atomic insert-if-absent/unique-key mechanism.

Do not rely on JVM synchronized blocks or a local HashSet to deduplicate across multiple pods.

## 10. Handling duplicates via exception or affected row count?

There are two approaches:

1. Execute INSERT and catch the unique-constraint exception.
2. Use insert-if-absent and check the number of inserted rows.

The second approach is usually cleaner to express:

~~~java
int inserted = jdbcTemplate.update(
    """
    INSERT INTO processed_events(consumer_name, event_id)
    VALUES (?, ?)
    ON CONFLICT DO NOTHING
    """,
    consumerName,
    eventId
);

if (inserted == 0) {
    return DuplicateDecision.ALREADY_PROCESSED;
}

return DuplicateDecision.NEW_EVENT;
~~~

Do not catch every DataIntegrityViolationException and treat it as a duplicate. Errors can stem from NOT NULL, foreign keys, length violations, or other constraints. If using the exception path, identify the exact constraint and handle only the corresponding duplicate error.

## 11. Database transaction and Kafka offset commit are two different transactions

With a relational inbox, the typical timeline is:

~~~text
Kafka delivers record
       |
       v
DB transaction:
  insert inbox marker
  apply business write
  commit
       |
       v
Listener returns successfully
       |
       v
Spring Kafka commits source offset
~~~

There is a window between DB commit and Kafka offset commit. If the process crashes there, Kafka redelivers. Since the inbox marker is already committed, the consumer skips repeating the business write next time.

This is why the inbox pattern works well for **database side effects** without needing a distributed transaction between Kafka and the database.

Never try to commit the Kafka offset before the database commit to reduce duplicates; that creates a risk of message loss if the DB transaction fails after the offset has already advanced.

## 12. Combining with AckMode

With Spring Kafka:

- AckMode.RECORD can commit offsets after a record listener completes per container semantics.
- AckMode.BATCH commits poll batch progress after processing the batch.
- MANUAL/MANUAL_IMMEDIATE require the application to acknowledge per contract.
- Transactional listeners have a path to commit offsets together with the Kafka transaction.

A dedup store does not alter AckMode. It protects the business side effect when a record is redelivered.

With manual ack:

~~~java
@KafkaListener(topics = "orders.events")
public void consume(
        OrderCreated event,
        Acknowledgment acknowledgment) {

    inventoryEventProcessor.process(event);
    acknowledgment.acknowledge();
}
~~~

The process method must complete the database transaction before acknowledging. If async processing is used, acknowledge only after the operation has truly finished and errors have been handled per policy.

## 13. Do Kafka transactions replace an inbox?

Kafka transactions can atomically commit:

- Kafka output records sent within the transaction.
- Input consumer offsets sent into the same transaction.
- Transaction commit or abort across all Kafka operations in that transaction.

This is useful for consume-transform-produce when all side effects reside inside Kafka.

However, a Kafka transaction does not automatically include a relational database, Redis, HTTP service, or payment provider. If a consumer updates a DB and then commits the Kafka offset, a failure window still exists between the two systems.

If all business state and dedup markers live in Kafka compacted topics/state stores with suitable transaction semantics, dedup can be designed differently. Still, never generalize Kafka EOS into exactly-once for the entire application.

## 14. Redis as a deduplication store

Redis supports atomic set-if-absent operations:

~~~text
SET dedup:inventory:evt-42 1 NX EX 604800
~~~

Meaning:

- SET key only if the key does not exist.
- NX guarantees the operation succeeds only when absent.
- EX sets a TTL of 604800 seconds, i.e., seven days.

If it returns OK, the request claimed the key. If the key exists, the event may already have been processed or is currently claimed by another worker.

In Spring Data Redis:

~~~java
Boolean claimed = stringRedisTemplate.opsForValue()
    .setIfAbsent(
        "dedup:inventory:" + event.eventId(),
        "PROCESSING",
        Duration.ofDays(7)
    );
~~~

This is only an atomic claim example. It does not fully solve PROCESSING state, failure recovery, lease expiry, and atomicity with database side effects.

If the Redis claim succeeds and then the database transaction fails, the key may remain and cause redeliveries to be skipped. Never use a Redis SET NX before a DB write as proof that the business operation completed.

## 15. Redis claims and leases

If Redis is needed to coordinate processing, states may include:

~~~text
ABSENT
  |
  v
PROCESSING (lease expires at T)
  |
  +-- Business operation success -> COMPLETED
  |
  +-- Failure -> FAILED_RETRYABLE or release claim
~~~

A lease requires:

- A unique owner token for the claiming worker.
- Expiration.
- Atomic compare-and-set when renewing or releasing.
- Preventing an old worker from releasing a new worker's claim.
- Recovery rules when a lease expires.
- Idempotent business side effects since an old worker may still be running after lease expiration.

Simply calling DEL key when a worker finishes can be dangerous: worker A's lease expires, worker B claims it, then worker A hits its finally block and runs DEL, deleting B's claim. Use an owner token and a Lua script or atomic conditional operation so a worker releases only its own claim.

Even a proper lease does not make HTTP/DB side effects atomic with Redis. Idempotency is still required where the side effect executes.

## 16. Redis persistence and eviction

Redis can restart, fail over, or evict keys depending on persistence, replication, and maxmemory policies.

If a dedup key is lost before a duplicate can appear, the event is treated as new and the side effect can repeat.

Evaluate:

- AOF/RDB persistence policy.
- Replication/failover guarantees.
- Eviction policy.
- Memory pressure.
- TTL distribution.
- Backup/restore behavior.
- Cluster hash slot/partitioning.
- Network timeouts and ambiguous write outcomes.

If dedup is a financial or inventory correctness requirement, do not use a volatile cache as the sole source of truth unless its durability/retention meets requirements and the business operation has additional protection.

## 17. Comparing relational databases and Redis

| Criterion | Relational inbox | Redis key-value |
|---|---|---|
| Atomic with business DB write in same database | Yes, same transaction | No if business write is in a separate SQL DB |
| Atomic insert-if-absent | Unique constraint | SET NX |
| Durability | Per database commit/replication policy | Depends on persistence/replication config |
| Query/audit history | Strong, SQL | Requires custom design |
| TTL | Cleanup job/partition retention | Native TTL |
| Concurrency | Unique constraint/transactions | Atomic commands/Lua |
| High throughput | Depends on DB/index/partitioning | Often fast for key lookups |
| Multi-service shared dedup | Possible, needs clear scope | Possible, needs namespace/ACL |
| Transaction with SQL business side effect | Good if same DB | Not automatically atomic |
| Failure under eviction | Normally not dropped before cleanup | Keys can be lost due to eviction |

A common choice for business effects in PostgreSQL is an inbox table in the same database transaction. Redis fits short-term duplicate suppression, rate limiting, or claims/leases when loss/expiry semantics are acceptable.

## 18. TTL: how long should dedup keys be retained?

A dedup store cannot delete keys arbitrarily. TTL/retention must exceed the window during which the system allows the same event to return.

Replay sources:

- Consumer retry/backoff.
- Retry topics with long delays.
- DLT retention and manual review.
- Operator replay after incidents.
- Producer/outbox retries.
- Backup restore or disaster recovery.
- Client retries.

If TTL is one day but an operator can replay the DLT after three weeks, old events can be reapplied after dedup keys expire.

Rule:

~~~text
dedup retention >= maximum allowed replay horizon
                   + operational safety margin
~~~

If the replay horizon cannot be bounded, a business-level uniqueness constraint or permanent event ledger is needed rather than a short TTL alone.

## 19. Retention and storage cost

Suppose a system receives 2 million unique events per day, with an average row/index footprint of 120 bytes:

~~~text
2,000,000 × 120 bytes = 240 MB/day
30 days ≈ 7.2 GB
90 days ≈ 21.6 GB
~~~

This is an illustrative calculation excluding replication, index overhead, vacuum/free space, page fragmentation, and backups.

Retention design must balance:

- Duplicate/replay horizon.
- Regulatory/audit retention.
- Database storage and index size.
- Cleanup workload.
- Partition pruning.
- Query latency.
- Recovery objectives.

Do not delete markers just because the table is growing without first establishing the maximum replay window. You can partition by processed_at and drop old partitions after retention expires, provided unique constraint/index semantics match the database's capabilities.

## 20. Cleanup jobs and races with event replay

A cleanup job:

~~~sql
DELETE FROM processed_events
WHERE processed_at < now() - INTERVAL '90 days';
~~~

This query is illustrative for PostgreSQL; deleting millions of rows at once can create long transactions, locks, WAL spikes, and vacuum pressure.

Operational practices:

- Delete in bounded batches.
- Run outside peak traffic.
- Monitor rows deleted, duration, locks, and database bloat.
- Use time partitioning when schema/unique keys allow.
- Define replay policy clearly before deleting.

A race can occur: cleanup deletes a key right before an old DLT replay is published. If the replay horizon exceeds retention, dedup no longer protects that event.

## 21. Partitioning the inbox table

A large dedup table can be partitioned by time:

~~~text
processed_events
  +-- p2026_01
  +-- p2026_02
  +-- p2026_03
~~~

Partitioning makes cleanup via dropping partitions faster than row-by-row deletes, yet many relational databases require the partition key to appear in the unique/primary key of a partitioned table. This can break global uniqueness of eventId if poorly designed.

Options:

- Include event timestamp/processing date in the unique key when the contract allows.
- Keep a compact global dedup index/table.
- Shard by hash of eventId.
- Separate hot inbox from archive/audit store.

Do not add partitioning before measuring index size, insert rate, vacuum, and query plans. Incorrect partitioning can prevent the unique constraint from enforcing global key uniqueness as intended.

## 22. Choosing a database for the dedup store

If business state resides in PostgreSQL, an inbox table in the same DB is usually the natural choice for atomic transactions.

If business state resides in MySQL, use unique keys and transactions in MySQL.

If business state spans multiple stores, choose a **source of truth** for idempotency and design a recoverable workflow. Do not write a marker in Redis and apply the side effect in SQL assuming the two writes are atomic.

If a service performs only an HTTP side effect, check whether the target API supports idempotency keys and operation outcome lookups. If not, a durable state machine is required to handle ambiguous timeouts and reconciliation.

## 23. External APIs and payment idempotency

A database inbox does not automatically prevent an external API from being called twice:

~~~text
Consumer receives PaymentRequested
       |
       v
Insert inbox marker
       |
       v
Call payment provider
       |
       v
Provider charge succeeds
       |
       v
Process crashes before storing result
       |
       v
Kafka redelivery
~~~

If the next attempt calls the provider as a brand-new request, it could charge twice.

Solutions:

- Use eventId/commandId as the provider idempotency key if supported by the API.
- Persist the provider operation ID and state.
- On an ambiguous timeout, query the provider by idempotency key/operation ID before calling again.
- Write the outcome and inbox state in a DB transaction after confirmation.
- Run a reconciliation job for operations in UNKNOWN status.

Do not mark COMPLETED without evidence that the provider executed the operation per contract. Never re-issue a charge just because the client timed out without knowing whether the first attempt succeeded.

## 24. State machine for external side effects

A workflow can use:

~~~text
RECEIVED
   |
   v
PENDING
   |
   v
CALLING_EXTERNAL
   |
   +-- Confirmed success -> COMPLETED
   |
   +-- Definitive failure -> FAILED_RETRYABLE / FAILED_TERMINAL
   |
   +-- Timeout unknown -> RECONCILIATION_REQUIRED
~~~

States must be durably persisted. Workers need claims/leases so the same operation does not run in parallel; each external request needs a stable idempotency key; reconciliation must be authorized to query provider status.

If the workflow can take a long time, do not hold a DB transaction open across the HTTP call. Use short, durable state transitions and an appropriate saga/workflow orchestration.

## 25. Using eventId and payload fingerprints

Event ID identifies the business event. A payload fingerprint detects whether a producer reused the same eventId for a different payload.

Example:

~~~text
eventId = evt-42
payloadHash = SHA-256(canonical payload)
~~~

If the store already has evt-42:

- Matching hash: likely a duplicate event.
- Different hash: producer violated uniqueness contract or reused an event ID.

Do not arbitrarily hash raw serialized bytes if serializer/schema evolution can change field order or encoding. Use a canonical representation or an immutable event identity contract.

If the hashed payload contains sensitive data, store a safely computed digest and never log the raw payload. Hashing does not replace eventId; it is an additional consistency check.

## 26. Consumer versions and dedup semantics

An event may be processed by a different code version after deployment. Decide whether the dedup key includes the processing version.

If the key is only (consumer,eventId), an event processed by version 1 will be skipped when version 2 replays. This is usually right when the goal is to avoid repeating business side effects.

If the workflow is a projection rebuild, a new scope may be needed:

~~~text
(projection_name, projection_generation, event_id)
~~~

For example, projection orders-v2 may need to re-read historical events independently of orders-v1. Do not share the same dedup namespace when you intentionally want one-time processing for a new projection.

Conversely, never add deployment version to the key for a payment side effect just to "allow re-running" after deploy. Doing so can double-charge payments.

## 27. DLT replay and the deduplication store

When replaying from a DLT, the business event ID should usually remain unchanged so the inbox recognizes whether the event was already processed.

However, there are two cases:

**Replay due to consumer crash after successful side effect:** the marker already committed; skipping the side effect is correct.

**Replay because initial business logic failed and no marker exists:** the event was never marked completed; the consumer needs to reprocess it.

If the inbox marker was written at the wrong time or FAILED_TERMINAL was treated like COMPLETED, a valid replay could be wrongly skipped.

Distinguish states:

- COMPLETED: business effect committed.
- FAILED: incomplete; eligible for replay per policy.
- SUPPRESSED_DUPLICATE: event duplicated a completed event.
- REPLAY_AUTHORIZED: explicit workflow permitting reprocessing.

An intentional replay to **fix/rebuild** may require a dedicated command and new processing scope. Never manually delete markers to force an event to re-run without understanding prior side effects.

## 28. Reprocessing and business compensation

If an event was processed incorrectly and must be re-run, the dedup store should not be wiped blindly.

Options:

- Emit a compensating event to undo the old business effect.
- Create a new correction command with its own idempotency key.
- Use a new projection generation for read model rebuilds.
- Use explicit audited replay authorization.
- Retain event history for before/after investigation.

For example, an OrderPaid event booked incorrectly may require a PaymentCorrection event rather than deleting the processed marker and re-running OrderPaid. Which approach is right depends on domain invariants.

## 29. Concurrent processing with multiple consumer instances

Within a consumer group, a partition is assigned to only one group member at a time under normal ownership. However, the same business event can still arrive via:

- Two partitions due to inconsistent producer keys.
- Two topics.
- Two consumer groups.
- A replay worker and a live worker.
- Two service instances via another command path.

Therefore, the dedup store must handle concurrency at the storage layer. A unique constraint or atomic SET NX is necessary if multiple workers can claim the same key.

Do not rely on partition ordering to protect global event uniqueness. If the same eventId is sent with two different keys, they can land on two partitions and be processed in parallel.

## 30. Locking and claim strategies

Some workflows need to claim rows:

~~~sql
SELECT *
FROM inbox_events
WHERE status = 'RECEIVED'
ORDER BY received_at
FOR UPDATE SKIP LOCKED
LIMIT 100;
~~~

This is a PostgreSQL pattern for worker queues. It helps when multiple workers claim distinct rows.

For a synchronous Kafka listener, extra queue/lease state is usually unnecessary if the DB transaction is short and a unique insert provides sufficient protection. Adding unnecessary locking can increase contention.

If using claim state:

- Include an owner ID.
- Include lease expiry.
- Use atomic state transitions.
- Provide recovery for expired leases.
- Use fencing/versions so old workers cannot overwrite newer state.
- Keep business side effects idempotent.

A lease does not guarantee an old worker stops immediately when the lease expires; network or GC pauses can let it continue. Thus, storage claims need fencing or downstream idempotency.

## 31. Dedup stores across multiple regions

Active-active multi-region topologies complicate identity and consistency:

~~~text
Region A consumer ----+
                     +---- Shared eventId
Region B consumer ----+
~~~

If two regions maintain independent dedup stores, both can simultaneously see the event as absent and execute the side effect.

Options:

- A single authoritative dedup store for the business key.
- Sharding by eventId/tenant so one region owns the key.
- Strongly consistent database/conditional writes.
- Domain partitioning so each aggregate is processed only in one home region.
- Downstream idempotency keys in the system executing the side effect.

Eventual replication in Redis or databases does not prevent two regions from claiming the same key within the replication lag window.

Make availability/latency/consistency trade-offs deliberately. Never claim global exactly-once dedup if the store is only eventually consistent.

## 32. Multi-tenant deduplication

In SaaS, the same eventId may be generated by two tenants if each tenant uses its own namespace.

Schema:

~~~sql
CREATE TABLE processed_events (
    tenant_id VARCHAR(100) NOT NULL,
    consumer_name VARCHAR(120) NOT NULL,
    event_id VARCHAR(200) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, consumer_name, event_id)
);
~~~

Do not take tenantId directly from an untrusted payload and use it to bypass dedup scope. Verify tenant identity against the authentication/authorization contract of the event source.

Never allow one tenant to occupy another tenant's event ID namespace by sending forged messages. If event sources are untrusted, enforce signatures, ACLs, and validation.

## 33. Dedup stores and schema evolution

Event schemas evolve over time, while event identity should remain stable.

Example:

~~~text
OrderCreated v1:
  eventId=evt-42
  payload: orderId, items

OrderCreated v2:
  eventId=evt-42
  payload: orderId, items, currency
~~~

If event v2 is the same event re-serialized, dedup must preserve the same identity. If event v2 is a new business event, it must receive a new eventId even if aggregateId is identical.

Do not include schemaVersion in the dedup key unless the contract intentionally treats each schema version as an independent operation. Normally, schema version describes format, not a new business event.

## 34. Dedup stores and event ordering

Deduplication prevents the same event from running multiple times, but does not guarantee event order.

Example:

~~~text
OrderCreated -> eventId=E1, aggregateId=O1
OrderPaid    -> eventId=E2, aggregateId=O1
~~~

If E2 arrives before E1 due to incorrect producer/key/partition topology, the dedup store still views both as new events. Business logic must validate aggregate version/sequence or partition by aggregate key.

You can store:

- aggregateId;
- aggregateVersion;
- event sequence;
- eventId.

A unique constraint on (aggregateId, aggregateVersion) can detect two events claiming the same version or abnormal replays, though it does not replace eventId deduplication.

## 35. Combining outbox and inbox

A service may both consume events and publish new events:

~~~text
Input Kafka event
       |
       v
Database transaction
  +-- Insert inbox marker
  +-- Update business state
  +-- Insert outbox event
       |
       v
Commit DB transaction
       |
       v
Outbox publisher sends Kafka event
~~~

The inbox prevents the input event from repeating side effects. The outbox guarantees the output event intent is persisted alongside business state. The outbox publisher can still publish duplicates if send ACK and mark-sent are not atomic; downstream consumers still need deduplication by eventId.

The two patterns complement each other:

- **Inbox:** prevents repeats on receipt.
- **Outbox:** prevents losing events on emit.

This does not make the entire pipeline exactly-once; it creates durable, recoverable boundaries.

## 36. Dedup during batch processing

A batch listener can receive many records at once. Each record needs its own dedup key; do not use a single shared marker for the whole batch unless batch identity is the business contract.

One transaction:

~~~text
BEGIN
  for each record:
    insert inbox marker
    if new:
      apply side effect
    else:
      count duplicate
COMMIT
~~~

If one record errors and the transaction rolls back, all markers and side effects in that transaction roll back as well. The error handler can redeliver the batch/record per batch error semantics.

For large batches:

- Use batch insert/upsert if the DB supports it.
- Keep the unique constraint.
- Distinguish new records from duplicates.
- Consider transaction duration/lock contention.
- Do not acknowledge the entire batch before all side effects qualify.

If each record can commit independently, design batch error handling and dedup transaction boundaries accordingly.

## 37. Logging for dedup decisions

When the store identifies a duplicate, emit a structured event log:

~~~json
{
  "event": "dedup_duplicate_suppressed",
  "service": "inventory-service",
  "consumer": "inventory-worker",
  "event_id": "evt-42",
  "tenant_id": "tenant-a",
  "topic": "orders.events",
  "partition": 2,
  "offset": 18421,
  "dedup_scope": "tenant-consumer-event",
  "decision": "skip_business_effect"
}
~~~

This log distinguishes a new record at offset 18421 from an already-processed business event. Do not log full payloads or secrets.

Log duplicates at DEBUG/INFO with appropriate sampling/baselining; occasional duplicate suppression is normal in at-least-once processing. Alert when the rate spikes abruptly or duplicate suppression appears in an unexpected workflow.

## 38. Metrics for deduplication stores

Suggested metrics:

| Metric | Meaning |
|---|---|
| dedup_lookup_total | Total key checks/claims |
| dedup_new_event_total | New keys claimed |
| dedup_duplicate_total | Keys already present |
| dedup_store_error_total | Lookup/insert errors |
| dedup_lookup_latency | Read/claim latency |
| dedup_db_conflict_total | Unique conflicts/duplicate inserts |
| dedup_expired_key_total | Keys cleaned up/expired if measurable |
| dedup_inflight_total | Active processing claims |
| dedup_stale_processing_total | PROCESSING claims past lease |
| business_effect_applied_total | Business effects actually applied |
| duplicate_suppressed_total | Side effects prevented due to duplicates |

Metric names are custom. Use bounded-cardinality labels like consumer, service, topic, outcome, and store type. Never put eventId, unbounded tenant IDs, or Kafka offsets into Prometheus labels.

### 38.1. Dedup ratio

A simple ratio:

~~~text
duplicate_ratio =
    duplicate_suppressed
    / all_dedup_decisions
~~~

The denominator must be clearly defined. A high ratio can signal producer duplicates, replays, or retry behavior; it is not necessarily an error during intentional replays.

## 39. Illustrative Prometheus queries

Assuming the app exports counters:

~~~promql
sum by (consumer, topic) (
  rate(app_dedup_duplicate_total[5m])
)
~~~

Duplicate ratio:

~~~promql
sum(rate(app_dedup_duplicate_total[10m]))
/
clamp_min(
  sum(rate(app_dedup_lookup_total[10m])),
  0.000001
)
~~~

Store errors:

~~~promql
sum by (store_type, error_group) (
  rate(app_dedup_store_error_total[5m])
)
~~~

Lookup latency p95 if a Timer is exported as a histogram:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, consumer) (
    rate(app_dedup_lookup_latency_seconds_bucket[5m])
  )
)
~~~

Actual metric names depend on the Micrometer registry and naming conventions. Do not deploy these queries before confirming the exporter emits the corresponding metrics.

## 40. Alerts for dedup stores

### Store unavailable

If the dedup store is unreachable, the consumer cannot reliably decide whether an event is new or a duplicate.

The usually safe policy is **fail closed** for business side effects requiring idempotency: do not execute the side effect when the key cannot be checked/claimed. The error handler can retry with backoff or pause per policy.

Fail open (bypassing dedup and processing anyway) can cause repeated side effects. Use it only if the domain tolerates duplicates or downstream has independent idempotency.

### Duplicate spike

Alert when the duplicate ratio exceeds baseline and correlate with:

- producer send retries/ambiguous acknowledgements;
- consumer rebalances/commit failures;
- outbox publisher retries;
- DLT replay volume;
- idempotency suppression rate.

### Stale processing claims

With state machines/leases, alert when PROCESSING rows exceed expiry. Check whether the worker is alive, lease renewal is failing, or the side effect is hung.

### Storage pressure

Monitor table size, index size, Redis memory, evictions, cleanup lag, and lookup latency. A slow dedup store can drag down consumer throughput and increase Kafka lag.

## 41. Dedup store failure: fail open or fail closed?

Two policies:

| Policy | Behavior when store unavailable | Risk |
|---|---|---|
| Fail open | Process message as unseen | Duplicate side effects |
| Fail closed | Do not run side effect, retry/pause | Reduced throughput, rising lag |

For payments, inventory, account balances, or operations unsafe to repeat, **fail closed** is usually appropriate when downstream lacks idempotency.

For an analytics counter that can tolerate bounded over-counting, fail open may be a business choice. The decision must be approved by the domain owner and documented in the runbook.

Never catch all exceptions from the dedup store and return success; doing so can commit the offset and cost the event its chance to be processed properly.

## 42. DB outages and transaction behavior

If the inbox DB and business state share the same database:

~~~text
Kafka record
   |
   v
DB unavailable
   |
   v
Inbox insert fails
   |
   v
Transaction rollback / listener exception
   |
   v
Kafka offset not committed per error policy
   |
   v
Record retried after DB recovers
~~~

This matches fail-closed behavior. However, you need:

- Explicit DB timeouts.
- Bounded retries/backoff.
- Never block consumer threads indefinitely.
- Monitor lag and DB health.
- Avoid retry storms during prolonged database outages.

If the DB connection pool exhausts, dedup store latency and consumer lag may climb before database errors become obvious.

## 43. Store timeouts and unknown outcomes

A dedup write can time out at the client even though the database committed:

~~~text
INSERT marker + side effect
       |
       v
DB commit succeeds
       |
       v
Response lost
       |
       v
Client receives timeout
       |
       v
Kafka redelivery
~~~

The retry attempts INSERT with the same unique key. If the row exists, the application sees a duplicate and does not repeat the side effect. This is the payoff of unique constraints and transactions.

Never assume a timeout means the transaction rolled back. On an unknown outcome, re-read durable state or let the unique constraint decide on retry.

## 44. Redis timeouts and ambiguous claims

With Redis SET NX:

~~~text
Client sends SET key NX
       |
       v
Redis stores key
       |
       v
Response lost
       |
       v
Client timeout
~~~

The application does not know whether the key was claimed. You can read the key back and check owner/state, though a separate read does not resolve every race if workflow state shifts between operations.

Claim design needs owner tokens, state, TTL, and appropriate atomic scripts. For financial side effects, never let a Redis claim be the sole protection when business writes go to a separate database.

## 45. Backup, restore, and disaster recovery

Losing dedup store data after a restore can cause historical events to be reprocessed:

~~~text
Database backup at T1
       |
       v
Process events through T2
       |
       v
Disaster recovery restores DB to T1
       |
       v
Kafka group/offset restored at T2 or T1?
       |
       v
Potential mismatch and duplicate effects
~~~

You must coordinate recovery points of:

- business database;
- inbox/dedup store;
- Kafka committed offsets;
- outbox rows;
- external side effect state.

If the database restores to a point before markers while Kafka offsets remain at a later point, events may not be redelivered even though business state rolled back. If Kafka offsets restore earlier than DB state, events may replay and the dedup store must still retain the corresponding markers.

Disaster recovery runbooks require reconciliation, not merely restoring each system independently.

## 46. Dedup store migration

When changing schemas or stores:

- Preserve key semantics.
- Avoid any window where two stores both receive traffic without sharing uniqueness.
- Backfill markers from the source of truth.
- Verify retention/horizons.
- Run dual-read/dual-write only when semantics and failure handling are clear.
- Maintain a rollback plan that does not lose markers.

Example migrating from Redis to PostgreSQL:

1. Choose retention and key scope.
2. Export active Redis keys with state/expiry.
3. Backfill into the DB with unique constraints.
4. Compare counts and sample keys.
5. Switch consumers to the DB transaction.
6. Monitor duplicate hits, store errors, and lag.
7. Retire Redis only after the protected replay horizon passes.

Dropping Redis immediately after backfill while uncopied keys or active TTLs remain can let duplicates slip through.

## 47. Versioning and backward compatibility

An event ID contract may be shared across multiple producer versions. When changing ID formats:

- Maintain parsers compatible with legacy IDs.
- Avoid changing namespaces in ways that make old events look "new" in the dedup store.
- Backfill or alias keys if necessary.
- Record event source/version clearly.
- Do not include schema version in the key without a business reason.

If a consumer changes consumer_name in the inbox key after a deployment, all old events can appear new. Treat consumer_name as part of a stable processing contract, not necessarily a bean/listener ID that changes during refactoring.

## 48. Security and privacy of the dedup store

A dedup table may store event IDs, tenant IDs, source offsets, and timestamps. Even without payloads, metadata can still be sensitive.

Apply:

- Least-privilege database credentials.
- Allow each consumer to insert/select only within its own namespace.
- Encrypt transport and storage per policy.
- Align retention/cleanup with privacy policies.
- Audit access as needed.
- Never expose a public endpoint to query eventId existence.
- Avoid logging full keys/tenant IDs unless policy permits.
- Avoid storing payloads or tokens in failure metadata.

An endpoint to "check if event exists" could be abused to probe another tenant's activity. Enforce authentication, authorization, and rate limiting if exposed via API.

## 49. Runbook: duplicate side effect occurred

**Step 1 — Identify the business event and effect**

Collect eventId/commandId, consumer, tenant, operation ID, and timestamp. Verify whether the effect truly duplicated in the database/provider.

**Step 2 — Classify the duplicate**

Same Kafka offset redelivery, same eventId at a different offset, producer republish, DLT replay, or client command duplicate?

**Step 3 — Inspect the dedup store**

Does the marker exist? Is the key scope right? Did TTL expire, did a cleanup race occur, did Redis evict, or did a restore roll back?

**Step 4 — Check atomicity**

Do the marker and business state share the same transaction? Did a marker commit before the effect? Does the external API have an idempotency key?

**Step 5 — Check concurrency**

Is there a unique constraint? Did two workers claim the event simultaneously? Was local in-memory dedup used instead of a shared store?

**Step 6 — Mitigate impact**

Depending on the domain, pause the consumer/operation causing further duplicates if safe. Do not rush to reset offsets or delete markers.

**Step 7 — Reconcile**

Reconcile payment/inventory/order state and execute compensation per business procedures.

**Step 8 — Fix and verify**

Add an atomic inbox/unique key or downstream idempotency. Test crashing after the side effect before offset commit and verify the side effect occurs only once.

## 50. Runbook: dedup store unavailable

1. Identify the affected relational DB/Redis instance and endpoint.
2. Check connection pools, timeouts, latency, failover, and network.
3. Confirm whether the consumer fails closed or fails open.
4. For side effects unsafe to repeat, keep fail closed.
5. Inspect consumer lag, retry rate, and partition assignment.
6. Restore the store or fail over per procedure.
7. Verify unique constraint/Redis availability and consistency.
8. Resume consumers under controlled rollout/throughput.
9. Monitor duplicate suppression and business effects.

Do not bypass dedup to reduce lag during a store outage unless downstream has equivalent idempotency.

## 51. Runbook: duplicate event wrongly skipped

Symptom: consumer logs a duplicate yet the business effect never completed.

1. Look up the inbox row by composite key.
2. Inspect status and processed_at.
3. Check whether a code path writes and commits the marker separately before the side effect.
4. Check transaction boundaries/transaction manager propagation.
5. Verify business state and external provider state.
6. If the marker is wrong, adjust it only through an audited reconciliation process.
7. Fix atomicity and test side-effect failure after marker insert.

Do not delete markers based solely on duplicate logs. The business side effect may have completed while the success log was lost.

## 52. Runbook: duplicate slipped past the dedup store

Possible causes:

- Key scope omitted tenant/consumer appropriately.
- Producer regenerated event ID on each retry.
- Missing or incorrect unique constraint.
- Store eviction/TTL expiration.
- Two regions using eventually consistent stores.
- Consumer using local cache instead of shared store.
- Marker and side effect executed in two separate transactions.

Checks:

1. Compare actual keys across both processing attempts.
2. Inspect the unique constraint/index.
3. Check DB/Redis durability and cleanup.
4. Inspect concurrency/region/partition topology.
5. Verify the eventId contract at the producer.
6. Reproduce the race in an integration test.

## 53. Testing the deduplication store

An essential test suite:

### 53.1. New event

- Inbox insert succeeds.
- Business effect executes once.
- Transaction commits.
- Kafka listener returns success.

### 53.2. Same event redelivered

- Inbox insert hits conflict/no-op.
- Business effect does not run again.
- Listener finishes per duplicate policy.

### 53.3. Business operation fails

- Inbox marker inserts.
- Side effect throws an exception.
- DB transaction rolls back.
- Marker does not exist after rollback.
- Retry can reprocess the event.

### 53.4. Two competing workers

- Two threads/instances process the same eventId simultaneously.
- Only one unique insert succeeds.
- Business effect occurs only once.

### 53.5. DB commit response timeout

- Transaction may have committed despite client timeout.
- Redelivery attempts insert again.
- Unique constraint prevents repeated effects.

### 53.6. Redis claim timeout

- Simulate ambiguous SET NX response.
- Verify owner/state recovery.
- Prevent an old worker from deleting a new claim.

### 53.7. TTL expiry and DLT replay

- Replay before TTL must be deduplicated.
- Replay after TTL must follow business retention policy.
- Prevent cleanup races from dropping protection prematurely.

### 53.8. Database restore

- Restore business DB/inbox and Kafka offsets per DR scenario.
- Confirm no lost business effects or unintended duplicates.

## 54. Testing with Spring Kafka and Testcontainers

An integration test can use Kafka Testcontainers and a database Testcontainer:

1. Start Kafka broker and PostgreSQL test instance.
2. Create a dedicated topic and consumer group.
3. Send a fixed eventId.
4. Let the listener call the transactional inbox service.
5. Resend the same eventId in a new Kafka record or force same-offset redelivery in an appropriate test.
6. Assert business rows/stock changes incremented only once.
7. Assert the inbox contains exactly one composite key.
8. Assert the consumer group offset eventually advances.
9. Verify duplicate metrics/logs are emitted properly.

Two test cases to keep separate:

- **Same-record redelivery:** the same topic-partition-offset is delivered again.
- **Duplicate publication:** two different offsets with the same eventId.

Do not collapse them into one "send same message twice" test because that only tests duplicate publication, not offset redelivery.

## 55. Common design mistakes

| Mistake | Consequence | Remedy |
|---|---|---|
| Using local HashSet as dedup store | Lost on restart, not shared across pods | Shared durable store |
| SELECT then INSERT without unique constraint | Race allows two side effects | Atomic insert-if-absent/unique key |
| Writing and committing marker before business effect | Event may be skipped even though effect failed | Same DB transaction |
| Committing business effect then writing marker separately | Redelivery repeats effect | Atomic inbox marker and effect |
| Using Redis SET NX as proof DB write completed | Two systems are not atomic | Durable workflow/downstream idempotency |
| TTL shorter than DLT replay horizon | Old events get reapplied | Retention aligned with replay policy |
| Eviction drops dedup keys | Duplicates slip through | Persistence/no-eviction or durable DB |
| Key only on eventId when ID not globally unique | Collisions across tenants/producers | Composite key per contract |
| Key includes consumer bean name or deployment version | Refactor makes old events look new | Stable processing contract |
| Using topic-partition-offset for business dedup | Replay/republish gets a new offset | Business event ID |
| Using payload hash as sole identity | Two valid events have identical payloads | Stable event/command ID |
| Using Kafka EOS to protect a database | DB is not inside Kafka transaction | Inbox/outbox/idempotency |
| Fail open when store errors | Side effects may repeat | Fail closed per domain |
| Manually deleting markers to replay | Can re-charge/reapply effects | Audited compensation/replay |
| Not coordinating DB restore and Kafka offsets | Duplicates or skipped events | DR reconciliation |
| Not measuring store latency/errors | DB/Redis degradation causes hard-to-trace lag | Metrics and alerts |

## 56. Production checklist

Before deploying a deduplication store to production:

1. Is the identity of the business event/command defined?
2. Is the key scoped properly by tenant, consumer, and processing contract?
3. Does the producer keep eventId stable across retries/replays?
4. Is there a unique constraint or atomic set-if-absent at the storage layer?
5. Are the marker and business side effect in the same DB transaction?
6. If the side effect is HTTP/payment, does downstream support idempotency keys?
7. Are RECEIVED/PROCESSING/COMPLETED/FAILED distinguished if the workflow needs state?
8. Do claims/leases have owner tokens, expiry, and fencing/conditional release?
9. Is TTL longer than all retry/DLT/manual replay horizons?
10. Does cleanup use a batch/partition strategy without racing against replays?
11. Do Redis persistence, replication, and eviction policies satisfy correctness?
12. Does multi-region consistency prevent two regions from claiming the same key?
13. Are database backups/restores coordinated with Kafka offsets and outboxes?
14. Are metrics present for lookup latency, duplicate hits, store errors, and stale claims?
15. Are alerts configured for store unavailability and duplicate spikes?
16. Do logs include eventId, current/original Kafka metadata, and decision outcomes?
17. Are high-cardinality labels containing event IDs avoided?
18. Are integration tests separated for same-offset redelivery and different-offset duplicate publication?
19. Has crashing after business commit before offset commit been tested?
20. Do audited runbooks exist for reconciliation/compensation and replays?

## 57. Conclusion

A **deduplication store** provides a durable source of state to recognize events already processed within a defined scope. For business side effects residing in the same relational database, an inbox table with a unique constraint writing both marker and side effect in one transaction is a clear and verifiable design. Redis SET NX can fit claims or short-term duplicate suppression, but does not automatically create atomicity with databases or external APIs.

The design must accurately define event identity, consumer/tenant scope, retention, and replay horizons; resolve races via unique constraints or atomic operations; and define clear policies for store timeouts, failovers, or restores. Kafka retries, rebalances, and DLT replays can still cause redeliveries; the dedup store ensures reprocessing creates no unintended side effects when boundaries are properly engineered.

A good deduplication store does more than answer "does this key already exist?". It must prove **whether the business operation actually completed**, handle concurrency and failure windows, retain sufficient history for the required duration, and enable operations teams to investigate/reconcile without accidentally skipping or duplicating critical business operations.
