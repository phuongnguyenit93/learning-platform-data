# Concurrent Deduplication Across Multiple Consumers or Application Replicas

A Spring Boot application integrating HTTP APIs, databases, and message brokers is commonly deployed with multiple replicas to increase throughput. Yet when a broker redelivers a message, consumers rebalance, an HTTP client retries, or two pods receive the same command, **multiple processes can attempt to apply the same business effect simultaneously**.

For example: an `OrderStatusChanged` event with `eventId=E42` arrives at a consumer updating order status. Pod A commits the database update yet dies before sending its acknowledgment (ack). The broker redelivers the message to pod B. Without deduplication logic, B might update again, emit another event, or call a payment/invoicing API a second time.

Within Spring Boot system integration, you must coordinate **stable identifying keys, transactions, data constraints, acks/retries, idempotency, and observability**. This lesson explains the protection mechanisms when multiple consumers or replicas run concurrently, especially the limitations of Redis locks and broker delivery guarantees.

## 1. Distinguishing duplicate messages from duplicate effects

| Phenomenon | Typical cause | Risk |
| --- | --- | --- |
| Broker redelivery | Consumer commits DB yet loses ack, or broker rebalances | Processing the same event again |
| Parallel consumers | Multiple subscriptions/groups, deployments, or replays | Two workers applying one event simultaneously |
| HTTP retry | Client does not know whether the prior request finished | Duplicate order creation or double charge |
| Publisher retry | Broker received message, producer lost ack | Same business meaning emitted in multiple messages |
| Check-then-act race | Two pods both read "not processed yet" and both write | Both pass the guard |
| Backfill/replay | Re-reading historical events or publishing to a new topic | Older events overwriting newer state |

**Duplicate messages do not have to mean duplicate effects.** An event delivered three times whose handler writes once is safe deduplication. Conversely, two messages with different `eventId`s can still represent **the same payment command** and create duplicate effects if you deduplicate solely by event ID.

### 1.1. Understanding delivery semantics properly

- `At-most-once` can lose messages on errors; unsuitable as a processing guarantee for critical business flows.
- `At-least-once` permits message redelivery whenever completion is uncertain; consumers must be idempotent.
- `Exactly-once` is meaningful only within a defined scope. For example, a broker transaction can cover operations inside that broker, yet does not automatically cover PostgreSQL updates, REST API calls, emails, or external systems.

The practical target for many `HTTP → DB → broker → consumer` pipelines is **at-least-once delivery combined with idempotent effects**. Specify clearly which system, step, and source of truth each guarantee applies to.

## 2. Why is "check then write" unsafe?

An error-prone implementation:

~~~java
if (!processedEventRepository.existsByEventId(event.eventId())) {
    applyBusinessUpdate(event);
    processedEventRepository.save(new ProcessedEvent(event.eventId()));
}
~~~

If two transactions read `exists=false` concurrently, both can call `applyBusinessUpdate`. Wrapping the code in `@Transactional` does not automatically turn a `SELECT → UPDATE` sequence into an atomic operation under default isolation.

~~~mermaid
sequenceDiagram
    participant A as Consumer A
    participant B as Consumer B
    participant D as Database
    A->>D: SELECT marker(E42) → not found
    B->>D: SELECT marker(E42) → not found
    A->>D: Business UPDATE
    B->>D: Business UPDATE again
    A->>D: INSERT marker(E42)
    B->>D: INSERT marker(E42) → unique error?
    Note over A,B: Side effects may have occurred before duplicate detection
~~~

Even if the marker table has a unique constraint, it cannot undo **external HTTP side effects** executed outside the transaction. The solution must place execution rights and durable mutations inside the right **atomic boundary**, never stopping at an in-memory or check-then-act check.

## 3. Choosing business-aligned idempotency keys

A deduplication key should remain stable across all retries and encode the processing scope:

~~~text
Deduplication identity
  = security/tenant scope
  + logical handler or operation
  + stable event ID / command ID
~~~

| Component | Example | Role |
| --- | --- | --- |
| `tenant_id` | `shop-a` | Isolates identical IDs across two tenants |
| `handler_name` | `order-projection-v1` | Lets each independent handler process the same event |
| `event_id` | UUID generated once by producer | Detects duplicates across redeliveries/replays |
| Business operation ID | `payment-capture-123` | Blocks two distinct event IDs representing the same business action |
| Aggregate version | `order-42, version 10` | Enforces valid update ordering |

Never use pod names, receipt timestamps, Kafka offsets, or Pulsar message IDs as **universal business keys** when messages can be republished. Infrastructure IDs can change while business intent stays identical.

For example, a client retrying `capture-payment-123` causes the producer to emit two distinct event IDs `E1` and `E2`. Deduplicating by `eventId` alone lets both through. Payment systems need an extra constraint such as unique `(tenant_id, payment_command_id)` or a gateway-enforced `Idempotency-Key`.

If upstream lacks a stable event ID, establish identity at the producer boundary or derive a canonical business key such as `tenantId + orderId + transitionVersion`. Never blindly hash the entire payload as the key: timestamps, field ordering, and serialization formatting can differ between deliveries.

If the same `eventId` carries differing content, that is a **data contract conflict**. Where this risk exists, store a canonicalized `payload_hash` and alert when a duplicate's hash differs—never silently discard potentially corrupted payloads.

## 4. Foundational pattern: transactional inbox + unique constraint

When the deduplication receipt and business mutation live in **one transactional database**, follow this sequence:

1. Start a DB transaction.
2. `INSERT` into `consumer_inbox` with `PRIMARY KEY (tenant_id, handler_name, event_id)`.
3. **Only** if the insert succeeds, update business state and write any required outbox rows.
4. Commit everything in the **same DB transaction**.
5. **After commit**, acknowledge the message at the broker.

~~~mermaid
sequenceDiagram
    participant A as Consumer A
    participant B as Consumer B
    participant D as Shared database
    participant M as Broker
    M-->>A: Event E42
    M-->>B: Event E42 (duplicate)
    A->>D: BEGIN; INSERT inbox(E42)
    B->>D: BEGIN; INSERT inbox(E42)
    Note over D: Unique index arbitrates concurrency
    A->>D: UPDATE business; INSERT outbox
    A->>D: COMMIT
    D-->>B: Duplicate key → skip business logic
    B->>D: COMMIT or rollback no-op
    A->>M: Ack after commit
    B->>M: Ack verified duplicate
~~~

Two workers racing on the same unique key must be arbitrated by the database. If transaction A **commits**, B will not apply a second business effect; if A **rolls back**, its marker rolls back too, allowing B to claim and process. Never run `existsBy...` before inserting.

### 4.1. Illustrative PostgreSQL schema

~~~sql
CREATE TABLE consumer_inbox (
    tenant_id      varchar(80)  NOT NULL,
    handler_name   varchar(120) NOT NULL,
    event_id       uuid         NOT NULL,
    received_at    timestamptz  NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, handler_name, event_id)
);

CREATE TABLE order_projection (
    tenant_id      varchar(80)  NOT NULL,
    order_id       uuid         NOT NULL,
    state          varchar(40)  NOT NULL,
    source_version bigint       NOT NULL,
    updated_at     timestamptz  NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, order_id)
);

CREATE TABLE integration_outbox (
    outbox_id      uuid         PRIMARY KEY,
    tenant_id      varchar(80)  NOT NULL,
    event_id       uuid         NOT NULL,
    event_type     varchar(120) NOT NULL,
    payload        jsonb        NOT NULL,
    published_at   timestamptz,
    UNIQUE (tenant_id, event_id, event_type)
);
~~~

`consumer_inbox` is the receipt, and `order_projection` is the target data. `integration_outbox` is needed only when the handler must emit downstream commands or events. This schema targets PostgreSQL; other DBs differ in upsert syntax, locking, and unique-error handling. Processed markers may need retention long enough to cover redeliveries and replays.

### 4.2. Spring Boot: shared transaction and insert-first

Example using `JdbcTemplate` and `TransactionTemplate` on the same PostgreSQL datasource. Assume `OrderStatusEvent` is an application record containing `eventId`, `tenantId`, `orderId`, `version`, and `state`.

~~~java
import java.util.Objects;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class OrderProjectionHandler {
    private static final String HANDLER = "order-projection-v1";

    private final JdbcTemplate jdbc;
    private final TransactionTemplate transactions;

    public OrderProjectionHandler(JdbcTemplate jdbc,
                                  TransactionTemplate transactions) {
        this.jdbc = jdbc;
        this.transactions = transactions;
    }

    public Result handle(OrderStatusEvent event) {
        validate(event); // Validate schema, tenant, ID, version, state.

        return Objects.requireNonNull(transactions.execute(tx -> {
            int claimed = jdbc.update("""
                INSERT INTO consumer_inbox
                    (tenant_id, handler_name, event_id)
                VALUES (?, ?, ?)
                ON CONFLICT (tenant_id, handler_name, event_id)
                DO NOTHING
                """,
                event.tenantId(), HANDLER, event.eventId());

            if (claimed == 0) {
                return Result.DUPLICATE;
            }

            jdbc.update("""
                INSERT INTO order_projection
                    (tenant_id, order_id, state, source_version)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (tenant_id, order_id)
                DO UPDATE SET
                    state = EXCLUDED.state,
                    source_version = EXCLUDED.source_version,
                    updated_at = now()
                WHERE order_projection.source_version
                      < EXCLUDED.source_version
                """,
                event.tenantId(), event.orderId(),
                event.state(), event.version());

            // If events must be sent to another system,
            // INSERT integration_outbox here, in the same transaction.
            return Result.PROCESSED;
        }));
    }

    private void validate(OrderStatusEvent event) {
        Objects.requireNonNull(event);
        Objects.requireNonNull(event.eventId());
        Objects.requireNonNull(event.tenantId());
        Objects.requireNonNull(event.orderId());
        Objects.requireNonNull(event.state());
        if (event.version() < 1) {
            throw new IllegalArgumentException("version must be positive");
        }
    }

    public enum Result { PROCESSED, DUPLICATE }
}
~~~

This snippet intentionally avoids calling HTTP or publishing to a broker inside the DB transaction. Java text blocks require Java 15+. `validate` must be fleshed out per application contract, especially verifying tenant authenticity from a trusted source, data validity, and authorization.

**Why it prevents races:** PostgreSQL resolves contention when two transactions `INSERT` the same unique key. B waits for A to commit or roll back; if A commits, `ON CONFLICT DO NOTHING` returns 0 rows inserted, while if A rolls back, another worker can claim it. Bound transaction duration to avoid long-held locks and handle deadlocks/timeouts.

**Why include version:** two events with **different IDs** can arrive out of order. `source_version < EXCLUDED.source_version` prevents older states from overwriting newer states in latest-state projections. However, if you must process **every transition** in strict order, check `expectedVersion = currentVersion + 1` and buffer early arrivals instead of merely ignoring older versions.

**Never treat every error as a duplicate:** database timeouts, deadlocks, lost connections, foreign-key errors, or payload mismatches must roll back and retry/quarantine by root cause. Only `claimed == 0` on the specific inbox unique key means the event already has a receipt. On MySQL, do not copy `ON CONFLICT`; use matching syntax and catch only the exact duplicate-key error instead of assuming `INSERT IGNORE` is safe for all failures.

### 4.3. Transaction boundaries and limits

- With multiple datasources, `TransactionTemplate` must bind to the exact `PlatformTransactionManager` managing `JdbcTemplate`; never assume two databases share a transaction.
- Inbox and business updates commit atomically **only inside the database**. HTTP calls, broker publishes, or emails do not roll back with that transaction.
- If the business operation fails, the marker must roll back too; committing the marker first and failing the business update later causes retries to skip work wrongly.
- Never store raw payloads or credentials in the inbox table without explicit justification and data controls.

## 5. Acking the broker after the transaction commits

Across all brokers, distinguish **message received** from **durable effect completed**:

~~~text
Right:
receive → begin DB tx → claim → business update → commit → ack

Wrong:
receive → ack → begin DB tx → crash
           └─ broker has no obligation to redeliver

Without inbox:
receive → update DB → commit → crash before ack
          └─ redelivery → updates DB again
~~~

Example Spring Kafka listener using manual acknowledgment, assuming the listener container is actually configured with `AckMode.MANUAL` or `MANUAL_IMMEDIATE` and a matching converter for `OrderStatusEvent`:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.stereotype.Component;

@Component
class OrderProjectionListener {
    private final OrderProjectionHandler handler;

    OrderProjectionListener(OrderProjectionHandler handler) {
        this.handler = handler;
    }

    @KafkaListener(
        topics = "orders.status.changed",
        groupId = "order-projection")
    void onMessage(OrderStatusEvent event, Acknowledgment ack) {
        // handle() commits the database before returning.
        // If handler throws, do not ack on this path.
        handler.handle(event);
        ack.acknowledge();
    }
}
~~~

`groupId` does not automatically enable manual acks. Container factories, deserializers, error handlers, retries, and DLTs must be configured appropriately for your Spring Kafka version and business needs. Never catch all exceptions and call `ack.acknowledge()` in `finally`.

With Pulsar, RabbitMQ, or Spring Integration inbound adapters, use matching ack/nack, requeue, or transaction mechanisms. APIs differ, while the rule stays identical: **acknowledge only after processed state is durably saved**, or after a follow-up processing intent is durably persisted per contract.

A duplicate with a confirmed receipt may be acked as handled. If the database is unavailable, never guess it is a duplicate from a local cache.

## 6. Contention across pods: cases to distinguish

| Scenario | Pod A | Pod B | Outcome |
| --- | --- | --- | --- |
| Two transactions, same key | Inserts marker, not yet committed | Inserts marker, may wait on unique lock | DB picks one valid commit |
| A commits | Commits marker + business | `claimed=0` | B performs no business effect |
| A rolls back | Rolls back marker + business | Can insert and process | Event is not lost |
| A commits then loses ack | Side effect committed | Broker redelivers to B | B detects duplicate and acks |
| A updates external system then dies | Remote HTTP already ran | B retries with same key | Requires target-side idempotency |

Unique constraints are the **durable arbiter** for event IDs. Yet they do not prevent two distinct event IDs from mutating the same aggregate, nor do they resolve external HTTP side effects outside the DB.

In PostgreSQL, `READ COMMITTED` plus unique keys suffices for standard insert-first patterns. You do not need `SERIALIZABLE` on every transaction just to deduplicate identical event IDs. When domain invariants span multiple rows or tables, add row locks, optimistic locking, unique business constraints, or stricter isolation as needed.

## 7. Event deduplication alone does not preserve state order

Consider two events with distinct IDs:

~~~text
E1: order-42, version=10, state=PAID
E2: order-42, version=11, state=SHIPPED
~~~

If E2 arrives before E1, merely marking both event IDs "seen" does not stop E1 from regressing state back to `PAID`. Therefore separate **deduplication** from **per-aggregate ordering/concurrency**:

- `Optimistic versioning`: update only if incoming version is newer (latest-state projection) or equals `currentVersion + 1` (step-by-step workflow).
- `SELECT ... FOR UPDATE` or `UPDATE ... WHERE version=?` to guard read–check–write inside the DB transaction.
- Keyed broker partitioning on `tenant + aggregateId` to reduce reordering per broker guarantees.
- Business state machines and DB constraints to block invalid transitions.
- Concurrency/rate limits at downstream targets when multiple aggregates touch shared resources.

One Kafka partition is owned by one consumer in the **same group** at a time, yet rebalances, replays, and other consumer groups can still reprocess events. Pulsar `Shared` and `Key_Shared` have distinct routing/ordering properties; `Key_Shared` also depends on proper producer batching. RabbitMQ prefetch/acks can redeliver. Broker settings help distribute load—**they do not replace durable business state checks**.

## 8. External side effects: an inbox alone is insufficient

Suppose a consumer receives `PaymentCaptured` and must call an HTTP invoicing service:

~~~text
DB INSERT inbox(E1) + COMMIT
HTTP POST /invoices
~~~

If the pod dies after committing the inbox yet before the HTTP call, the broker redelivers E1, the handler sees a duplicate, and **the invoice is never created**. Conversely, calling HTTP before writing the marker means a crash after remote success yet before committing the marker creates **two invoices** on retry.

Three common patterns:

| Pattern | When it fits | Key condition |
| --- | --- | --- |
| **Inbox + transactional outbox** | Need to emit async events/commands after DB commit | Receipt and outbound intent commit in the same transaction |
| **Target API idempotency key** | HTTP target enforces deduplication | Every retry sends the exact same key and valid payload |
| **Durable Saga/workflow** | Multiple services and compensatable steps | State machine, timeouts, retries, reconciliation, and compensation |

### 8.1. Transactional outbox

~~~mermaid
flowchart LR
    A[Receive event E1] --> B[DB transaction]
    B --> C[Insert inbox E1]
    C --> D[Update business]
    D --> E[Insert outbox operationId]
    E --> F[Commit]
    F --> G[Ack input broker]
    F --> H[Outbox publisher]
    H --> I[HTTP or output broker]
    I --> J[Mark outbox sent]
~~~

If the pod dies **before commit**, neither receipt nor outbox exists. If it dies **after commit yet before publish**, another publisher can still send. If the publisher sends successfully and dies **before marking sent**, it can send again. An outbox ensures **recoverability of send intent**, not target-side exactly-once.

Pass a stable `operationId`/`eventId` to the downstream target and enforce idempotency there. If multiple publishers read the outbox concurrently, claim rows via transactions/leases or row locks, handling dead publishers and expired leases.

### 8.2. HTTP Idempotency-Key

An external API supporting idempotency may accept:

~~~http
POST /invoices HTTP/1.1
Idempotency-Key: tenant-a:invoice:create:order-42
Content-Type: application/json

{"orderId":"order-42","amount":125000}
~~~

Header names and syntax above are illustrative; each provider defines its own contract for header names, key TTLs, payload hashing, and replay responses. The `Idempotency-Key` value must stay constant across all retries of the **same business operation** and be persisted in the outbox/workflow. Never generate a random UUID per retry. An HTTP timeout does not prove the target API failed to complete, as the response may drop after the target committed.

If the target API lacks idempotency support, look for status-query endpoints, target-side business unique keys, reconciliation, or compensation. No local lock can guarantee exactly-once side effects on another service.

## 9. Leases, PROCESSING state, and fencing for long-running tasks

For tasks taking seconds/minutes or calling external HTTP APIs, holding a DB transaction open to lock an event is harmful. Design a **processing-state table** instead:

~~~text
NEW
  └─ claim → PROCESSING(ownerToken, leaseUntil, attempt)
                 ├─ success → COMPLETED
                 ├─ transient failure → RETRYABLE
                 └─ permanent failure → FAILED / DEAD_LETTER
~~~

Workers claim atomically, recording `owner_token` and `lease_until`. Another worker takes over only when lease rules allow, incrementing `attempt` within retry limits. Upon completion, a conditional update like `UPDATE ... WHERE owner_token=? AND status='PROCESSING'` stops a dispossessed worker from overwriting local state.

**Lease pitfall:** lease expiration does **not** prove the old worker stopped executing. Pod A might pause for GC, its lease expires, and pod B claims and calls HTTP. Pod A wakes up and calls HTTP too. Comparing owner tokens on completion protects only the **local coordination table**, not side effects on the HTTP server.

When protecting target resources from stale workers, use a **monotonic fencing token** (higher epoch/version wins) checked by **the target system itself**, or require target-side idempotency keys. A random owner token only identifies a lease holder—it **is not a fencing token**. If the target supports neither fencing nor idempotency, state the guarantee boundaries explicitly and pair with reconciliation/compensation.

### 9.1. Can a Redis lock replace a unique constraint?

A `SET lock:key token NX PX leaseMs` lock helps reduce how many workers concurrently hit a resource. However:

- The lease can expire while the worker is still running, letting two workers execute the effect.
- Network partitions, Redis failovers, timeouts, and misconfigurations require careful analysis.
- Crashing after an external side effect yet before durable state causes retries and possible duplicates.
- Releasing a lock must compare the token and delete **atomically**; separate `GET` and `DEL` calls are unsafe.

Redis locks help shed load or prevent stampedes, yet should never serve as **final proof** that a charge ran once, an invoice issued once, or a business operation completed. When state lives in a relational database, unique constraints and transactions provide a much stronger foundation.

## 10. How long to keep markers and handling intentional replays

`consumer_inbox` grows with event volume. Deleting markers too early allows old messages to re-enter as brand-new events.

~~~text
Dedup retention must cover the entire duplicate window:
  broker retention/replay
  + retries, DLQs, outbox resends
  + supported backfill and recovery windows
~~~

This guides analyzing **replay sources**, not a rigid arithmetic sum: practical protection must exceed the **maximum age** at which old events can return, including manual operations. If the system can replay six months back, keeping markers for seven days will not stop duplicates during that replay.

Options to consider: partition and archive inbox tables; retain minimal-key tombstones; keep unique business operation IDs longer; exclude raw PII from markers. Deletion policies must align with data compliance and real event lifecycles.

Distinguish four cases:

1. **Retry of the same request:** keep the same event/operation ID; block if already succeeded.
2. **Replay to rebuild a projection:** may use a new handler version or fresh projection table, without re-triggering unintended external side effects.
3. **Reprocess with changed inputs:** create a new revision deliberately, under controls, with explicit rules for superseding old results.
4. **Historical backfill:** ensure tenant/aggregate versions, order, and newer live state are never overwritten by old events.

Renaming `handler_name` on every deployment invalidates all prior receipts for the new name. Change a handler's namespace only when intentionally planning a reprocess and understanding its impact.

## 11. Error classification, retries, and poison messages

Not every error should be retried; nor does every exception mean "already processed."

| Situation | Appropriate handling |
| --- | --- |
| Already-committed duplicate with same key | Skip business effect, ack success, increment duplicate metric |
| Another transaction currently claiming | Wait boundedly; on lock timeout, retry with backoff |
| DB deadlock or lost connection | Roll back, do not ack success; bounded retry with jitter |
| Permanently invalid payload/schema | Reject/DLQ/quarantine per contract; never infinite-loop |
| Missing prerequisite that may arrive later | Delayed retry or buffer waiting on version/dependency |
| HTTP 429/503 | Retry with backoff, concurrency caps, and same idempotency key |
| HTTP timeout, uncertain outcome | Query status if supported, then retry with same operation ID |
| Same event ID, differing payload | Report contract conflict; never silently skip |
| Cannot check inbox due to DB error | Never treat as duplicate; route through error handling |

Designate **one primary retry owner** per stage: Spring Kafka error handler/DLT, Pulsar retry/DLQ, RabbitMQ requeue/DLX, Spring Integration error channel, or DB workflow. If adapters, brokers, and app code all retry independently, you get multiplicative retry storms that overwhelm data stores.

Set max attempts or deadlines, jittered backoff, controlled DLQs, and redrive rules. Poison messages must not wedge an entire subscription, yet skipping them must respect ordering invariants: event version 11 may be invalid if version 10 was never applied.

## 12. Observing duplicate rates and business impact

Measuring only received and acked messages is not enough. Cross-check durable storage and downstream targets to confirm deduplication actually works.

| Group | Metric or signal | Meaning |
| --- | --- | --- |
| Inbox | Claim successes, duplicate skips, payload conflicts | Reveals retry rates and upstream bugs |
| DB concurrency | Unique conflicts, lock wait times, deadlocks, tx timeouts | Spots multiple replicas racing on the same keys |
| Broker | Redeliveries, consumer lag/backlog, nacks, DLQ, rebalances | Correlates duplicates with messaging events |
| Outbox | Pending age, resends, publish timeouts, failure rates | Detects stalled progress or excessive retries |
| Downstream HTTP | Idempotency hits, timeouts, uncertain external responses | Verifies target-side deduplication |
| Business | Business operation counts, invariant violations, double-charge checks | Measures **correctness**, not just throughput |

Micrometer/Actuator and tracing can link receive → claim inbox → DB commit → ack → publish outbox → target processing. Never use high-cardinality raw `eventId`, `orderId`, `userId`, or `tenantId` as metric tags; keep correlation IDs in access-controlled, sanitized logs and traces. Avoid logging tokens, credentials, and unnecessary raw payloads.

Alert on deviations from baseline: sharp duplicate spikes after rebalances, contention scaling up with pod count, outbox pending past SLA, expired leases while workers still call downstreams, or processed counts exceeding valid business commands.

## 13. Testing race conditions and crash windows

Unit tests calling a handler twice sequentially test only the trivial duplicate branch. You need **concurrency tests against a real production-like database**—such as PostgreSQL via Testcontainers—paired with fault injection at critical boundaries.

| Scenario | How to reproduce | Expectation |
| --- | --- | --- |
| Two workers, same event ID | Two separate transactions launched at a barrier | One receipt, one business effect committed |
| Winner rolls back | A inserts then rolls back, B waits on same key | B processes cleanly; no lost event |
| Commit then lost ack | DB commits, kill process before broker ack | Redelivery detects duplicate, no second effect |
| Crash before commit | Kill worker while transaction is open | Marker and business roll back; retry succeeds |
| Same ID across topics | Replay/republish same event ID to same logical handler | Still deduplicated when business identity is unchanged |
| Same event ID, different payload | Mutate one field with the same key | Detected as a contract conflict |
| Two events, different versions | Deliver 11 before 10 | Old event never overwrites newer state |
| Outbox sent, unmarked | Kill publisher right after send succeeds | Downstream deduplicates via operation ID |
| HTTP target succeeds, times out | Mock remote commit then drop response | Retry with same Idempotency-Key creates no second effect |
| Lease expires while worker A runs | A pauses, B takes over, A resumes | Target fencing/idempotency blocks stale effect |
| DB unavailable | Connection timeout/deadlock | Does not ack success; bounded retries |
| Burst retries/DLQ | Rebalance/replay under load | Pool stays healthy, zero duplicate side effects |

How to write effective race tests:

1. Use two service instances or independent transactions/connections against the same PostgreSQL instance; align start times with `CountDownLatch` or a barrier.
2. Hold transaction A open before commit so B genuinely hits the unique index. Test both A-commit and A-rollback branches.
3. Assert **committed row counts** in inbox, business tables, and outbox; counting method invocations is insufficient.
4. Simulate crashes right **before/after commit** and **before/after ack**. Those are the windows where work gets lost or duplicated.
5. For HTTP, use a mock server tracking `Idempotency-Key` history and dropping responses post-commit.
6. Test concurrent job/consumer limits, timeouts, lock contention, and multi-replica redeliveries.
7. Never assert that worker A always wins; correctness must hold regardless of which worker wins.

In-memory unit tests alone cannot prove database unique indexes, transaction isolation, network faults, or real message-container behavior.

## 14. Choosing mechanisms by consistency boundary

| Source and target | Reliable atomic point | Mechanism to use |
| --- | --- | --- |
| Broker consumer → **one relational DB** | Transaction + unique index | Inbox receipt + business update + ack after commit |
| HTTP retry → **one relational DB** | Unique business key + transaction | Stable idempotency key, persist response for replay |
| Broker/HTTP → DB → another broker | No automatic cross-system transaction | Inbox + transactional outbox + idempotent target consumers |
| Consumer → external payment/invoice API | Target API owns the side effect | Stable Idempotency-Key, durable workflow, and reconciliation |
| Long multi-worker tasks | Coordination leases are only temporary | Durable state + leases + target fencing/idempotency |
| Multiple distinct event IDs on same aggregate | Unique event ID does not solve order | Version checks, row locks, keyed partitioning, domain invariants |
| Long-term replays/backfills | Marker TTL may be shorter than replay window | Retention policies or long-lived business invariants |

Before implementing, answer seven questions:

1. **What counts as "the same effect"?** One message, one command, one charge, or one state transition?
2. **What is the retry-stable key?** Who issues event ID, command ID, tenant, handler, and version?
3. **Where is the source of truth?** One DB, multiple DBs, or external APIs? What does each transaction cover?
4. **Who can run concurrently?** Consumer groups, subscriptions, HTTP retries, schedulers, replicas, publisher replays?
5. **What if a crash hits before/after commit and ack?** Is work lost or duplicated?
6. **How is old data handled?** Ordering, revisions, replay retention, and DLQ redrives?
7. **How is it verified?** Which unique conflicts, duplicate skips, outbox ages, reconciliations, and race tests?

**Core principle:** concurrent deduplication cannot rely solely on `existsById()`, a local cache, or a lease-based distributed lock. Use **stable business identities**, **atomic and durable arbitration** (typically DB unique constraints inside transactions), **acks after commit**, and **idempotency/fencing at systems holding external side effects**. That way, scaling out, retries, rebalances, and crashes never turn one valid request into multiple business mutations.

### References

- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transaction boundaries, rollbacks, propagation, and transaction managers.
- [Spring for Apache Kafka — Message Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html): acknowledgments, containers, and message listeners.
- [Spring for Apache Kafka — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html): guarantee boundaries of Kafka transactions and effects outside Kafka.
- [PostgreSQL — INSERT / ON CONFLICT](https://www.postgresql.org/docs/current/sql-insert.html): resolving unique key contention and `DO NOTHING`.
- [PostgreSQL — Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html): lock waits and deadlocks in PostgreSQL.
- [Apache Kafka — Documentation](https://kafka.apache.org/documentation/): consumer groups, delivery semantics, and producer/consumer behavior.

Illustrative examples use PostgreSQL, Spring JdbcTemplate/TransactionTemplate, Spring Kafka, and Java text blocks. When applying them, verify your exact Spring Boot, broker, driver, isolation level, and target API idempotency contracts; only mutations inside the **same DB transaction** commit or roll back atomically under the pattern above.
