# Simulating Partial Failures and Verifying Data Recovery Procedures

A Spring Boot system can accept an HTTP request, write to a database, emit an event through a broker, and update data in another service. Any step can fail at a different moment. When a pod crashes right after committing the DB but before sending a message, or the broker stores a message while the producer times out, **checking only HTTP status codes or message counts does not prove data recovered properly**.

This comprehensive practice builds **controlled fault-injection scenarios**, tracks state across every DB/HTTP/cache/broker boundary, and reconciles outcomes after recovery. The focus is simulating partial failures, identifying data-loss or duplication windows, protecting transactions and idempotency, verifying retries/DLQs, and measuring recovery with repeatable evidence.

Examples use Spring Boot with PostgreSQL, a message broker (Kafka, Pulsar, or RabbitMQ), a consumer, and an external HTTP service. Testing techniques also apply to Spring Integration adapters when flows use channels, gateways, or inbound/outbound adapters. SQL examples use PostgreSQL; broker APIs, acknowledgments, and retry policies must be tailored to your actual system.

## 1. Defining the System and What Counts as Correct

Assume an e-commerce platform with this flow:

1. Client sends `POST /orders` with `Idempotency-Key` and tenant ID.
2. `Order API` validates, persists `orders` and an `outbox` record in **the same transaction**.
3. `Outbox publisher` reads unsent records, publishes `OrderCreated` to the broker, and marks sent once the broker confirms.
4. `Order projection consumer` receives the event, deduplicates via `eventId` in `inbox`, updates a read database (read model), and acks **after commit**.
5. An integration component may call an HTTP shipping partner; a product cache speeds up reads without acting as the source of truth.

~~~mermaid
flowchart LR
    H[HTTP client] --> A[Order API]
    A --> T[(Order DB: orders + outbox)]
    T --> P[Outbox publisher]
    P --> B[(Message broker)]
    B --> C[Projection consumer]
    C --> R[(Read DB: inbox + projection)]
    C -. via workflow/outbox .-> X[HTTP partner]
    A -. reads data .-> K[(Cache)]
~~~

### 1.1. Defining Business Invariants

Before breaking the system, define what **successful recovery** looks like. Invariants to test:

| ID | Invariant to Preserve | How to Verify |
| --- | --- | --- |
| I1 | One `tenantId + clientOperationId` creates **one** logical order | Unique key in source DB, count `orders` |
| I2 | Every committed order has a durable event emission intent | Count `outbox` in same transaction, query by order ID |
| I3 | An event may be sent/received multiple times yet produces **one** projection effect per handler and tenant | Unique `inbox(tenant_id, handler_name, event_id)`, inspect committed effect counts |
| I4 | Older events never overwrite newer projection data | Compare `aggregateVersion` in target DB |
| I5 | When dependencies recover, backlog drains to 0 or within SLA | Measure outbox pending age, broker lag, retry queues |
| I6 | Poison messages never drop valid messages | DLQ/quarantine, controlled replay |
| I7 | Never create duplicate HTTP side effects for one business operation | Idempotency key and partner-side outcome logs |
| I8 | Cache failures never produce invalid transaction state | Compare results against authoritative DB |

"Once" in I1/I3/I7 must be understood **within the stated identities and boundaries**. Never claim system-wide exactly-once; brokers normally deliver at-least-once and handlers must tolerate duplicates.

### 1.2. Classifying Recovery Dimensions

- **Consistency:** data honors constraints and versions; never creates duplicate orders, charges, or invoices.
- **Durability:** committed changes survive pod/broker crashes; outbox retains send intent.
- **Availability:** whether APIs stay available or return `503` when the DB is down.
- **Convergence:** projections and external systems catch up to source state within acceptable time windows.
- **Recovery point objective (RPO):** tolerable data loss per system requirements; for API-confirmed committed orders, target RPO is typically **0** for source records.
- **Recovery time objective (RTO):** acceptable duration for functionality to recover after a fault. Must be measured under defined environments and loads, never merely guessed.

## 2. Designing Explicit Fault-Injection Points Instead of Random Kills

To trace root causes, place fault points at boundaries the application can observe:

~~~text
F1  Before committing orders + outbox
F2  After DB commit, before publisher reads outbox
F3  After broker accepts event, before producer gets ack/marks SENT
F4  After consumer commits inbox + projection, before broker ack
F5  Inside consumer transaction (before commit)
F6  During broker connectivity / reconnects or rebalances
F7  Calling HTTP partner; remote processed it yet response was lost
F8  Cache GET, PUT, or invalidation failure
F9  Malformed schema or business contract violation
F10 Two replicas/publishers competing for work when one worker dies
~~~

Attach test hooks at transaction/outbox boundaries in a **test profile**, use network proxies to sever connections, and use container stops/restarts to simulate crashes. Fault hooks must never accidentally run on production requests.

Simulated faults are only meaningful if you control **when they fire**. For example, "kill the broker for 30 seconds and watch the system recover" fails to test the case where the broker already persisted the message while the acknowledgment never reached the producer. Case F3 must force failure right around publish acknowledgment (or use stubs/fault hooks reproducing uncertain outcomes).

## 3. Setting Up a Repeatable Practice Environment

Build an **isolated integration test environment**:

| Component | Role | How Simulated |
| --- | --- | --- |
| Source PostgreSQL | Stores `orders` and `outbox` | Testcontainers PostgreSQL; stop/restart, locks, or rollbacks |
| Broker | Transports `OrderCreated` | Testcontainers Kafka/RabbitMQ/Pulsar matching project; network faults |
| Projection PostgreSQL | Stores `inbox` and read model | Can share DB instance using **separate schemas/transactions** to test boundaries |
| HTTP partner | Accepts shipment creation requests | WireMock/MockWebServer simulating `429`/`500`/timeouts and response loss |
| Network proxy | Cuts connections, adds latency, throttles bandwidth | Toxiproxy or network emulator |
| Application | Order API, publisher, consumer, scheduler | Run at least 2 replicas for contention cases |
| Observability | Logs, metrics, traces, DB queries | Stable correlation IDs and event IDs |

Testcontainers alone does not guarantee production parity. Document broker/driver versions, transaction isolation, retry settings, ack modes, retention, and replica counts. During load tests, fix payload sizes, partition counts, request rates, and fault-injection timings.

### 3.1. Test Data and Stable Keys

Use an isolated input set for each run:

~~~json
{
  "tenantId": "shop-a",
  "clientOperationId": "create-order-test-001",
  "orderId": "00000000-0000-4000-8000-000000000042",
  "eventId": "10000000-0000-4000-8000-000000000042",
  "aggregateVersion": 1,
  "amount": 125000
}
~~~

`clientOperationId` stays constant across client HTTP retries. `eventId` is minted once when writing the outbox and **never replaced by a new UUID on publish retries**. Re-running tests against the same DB without resetting fixtures or changing test namespaces can let old receipts produce false passes. Reset data only **inside isolated test environments**; never delete production data.

### 3.2. Controlling Time and Concurrency

Use barriers/`CountDownLatch` or test-point hooks to force races at exact boundaries; use controllable clocks when logic relies on leases/TTLs. Avoid long `Thread.sleep(...)` calls and arbitrary timings that pass on laptops yet flake in CI.

For async recovery tests, use `Awaitility` or deadline polling waiting for **business conditions**, such as "projection holds one version-1 row," instead of "wait 5 seconds and hope."

## 4. Data and Transactions Underlying Recovery

Abbreviated illustrative schema:

~~~sql
CREATE TABLE orders (
    order_id            uuid         PRIMARY KEY,
    tenant_id           varchar(80)  NOT NULL,
    client_operation_id varchar(100) NOT NULL,
    amount              bigint       NOT NULL,
    state               varchar(40)  NOT NULL,
    created_at          timestamptz  NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, client_operation_id)
);

CREATE TABLE order_outbox (
    event_id        uuid         PRIMARY KEY,
    tenant_id       varchar(80)  NOT NULL,
    aggregate_id    uuid         NOT NULL,
    aggregate_ver   bigint       NOT NULL,
    event_type      varchar(80)  NOT NULL,
    payload         jsonb        NOT NULL,
    status          varchar(20)  NOT NULL DEFAULT 'NEW',
    attempts        integer      NOT NULL DEFAULT 0,
    next_attempt_at timestamptz  NOT NULL DEFAULT now(),
    created_at      timestamptz  NOT NULL DEFAULT now(),
    sent_at         timestamptz
);

CREATE TABLE consumer_inbox (
    tenant_id    varchar(80)  NOT NULL,
    handler_name varchar(100) NOT NULL,
    event_id     uuid         NOT NULL,
    processed_at timestamptz  NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, handler_name, event_id)
);

CREATE TABLE order_read_model (
    tenant_id         varchar(80)  NOT NULL,
    order_id          uuid         NOT NULL,
    state             varchar(40)  NOT NULL,
    source_version    bigint       NOT NULL,
    PRIMARY KEY (tenant_id, order_id)
);
~~~

Source and target tables can live in **two separate databases**. Putting them in one DDL block illustrates column names; never assume a shared transaction across two databases. `consumer_inbox` commits **in the same transaction as the read model**, while `orders` and `order_outbox` commit **in the same source DB transaction**.

Each unique constraint plays a distinct role:

- `(tenant_id, client_operation_id)`: prevents duplicate orders from client retries of the same command.
- `order_outbox.event_id`: preserves one logical message identity across publish retries.
- `(tenant_id, handler_name, event_id)`: guarantees a handler applies an event's DB effect once per tenant.
- `(tenant_id, order_id)` and `source_version`: protect projection data from stale overwrites.

Real outbox tables also need claim/lease columns or row-locking support, last error, retry count, and poison-record isolation. A bare `status` column alone is **not enough** for safe concurrent claiming across multiple publishers.

### 4.1. Transaction at Order API

Inside one transaction on the source DB:

~~~text
BEGIN
  INSERT orders(tenant_id, client_operation_id, order_id, ...)
  INSERT order_outbox(event_id, aggregate_id, aggregate_ver, payload, ...)
COMMIT
HTTP response 201/200 matching idempotency contract
~~~

If inserting `orders` hits a conflict on the client operation ID, the API must read the existing outcome and verify **request payload/amount/tenant** to prevent returning results for a conflicting request accidentally reusing a key. Never create a second order with a new key after a client timeout. Never publish straight to the broker between two DB inserts assuming the broker shares PostgreSQL's transaction.

### 4.2. Transaction at Consumer

In the projection database, handle events in this order:

~~~text
BEGIN
  INSERT consumer_inbox(handler_name, event_id)
    ON CONFLICT DO NOTHING
  if receipt already existed:
      skip business write
  if newly claimed:
      INSERT/UPDATE order_read_model guarded by aggregateVersion
COMMIT
ACK broker
~~~

If the consumer crashes before commit, both receipt and read model roll back so the broker can redeliver. If it crashes after commit before ack, redeliveries hit the receipt and skip safely. If a message arrives with the same event ID yet a different payload, verify contract/hashes before treating it as a duplicate rather than silently ignoring differing semantics.

### 4.3. A Version-Checked SQL Statement

In PostgreSQL, a projection tracking latest state can use:

~~~sql
INSERT INTO order_read_model
    (tenant_id, order_id, state, source_version)
VALUES (:tenant_id, :order_id, :state, :version)
ON CONFLICT (tenant_id, order_id)
DO UPDATE SET
    state = EXCLUDED.state,
    source_version = EXCLUDED.source_version
WHERE order_read_model.source_version < EXCLUDED.source_version;
~~~

This is a **latest-state projection** pattern, intentionally ignoring older events. When business rules require processing every transition sequentially or accumulating deltas, enforce `expectedVersion = currentVersion + 1` and buffer out-of-order events for ordered replay. Never use `max(version)` to swallow mandatory intermediate events.

## 5. Baseline: Run the Happy Path Before Injecting Faults

Do not inject faults immediately. First execute a clean request to establish a baseline:

1. Send `POST /orders` once with `Idempotency-Key: create-order-test-001`.
2. Verify `orders` has one row and `order_outbox` has one row matching the aggregate/event keys.
3. Wait for the publisher to emit the event and the broker to accept it; outbox transitions to `SENT` **after acknowledgment**.
4. Wait for the consumer to commit `consumer_inbox` and `order_read_model`, then ack.
5. If an HTTP partner is involved, verify exactly one operation in the stubbed system using a durably persisted idempotency key.
6. Record baseline metrics: p95/p99 publish latency, projection convergence time, retries, outbox pending age, broker lag, and memory.

A baseline missing unique constraints, idempotency, and event counts is **unfit** as a recovery test benchmark. Fix those gaps before injecting faults.

## 6. Partial Failure Matrix and Recovery Expectations

| Fault | Injection Point | Expected State Right After Fault | Recovery Criterion |
| --- | --- | --- | --- |
| F1 | Order API before DB commit | Neither order nor outbox committed | Retrying same key creates one order + outbox |
| F2 | After commit, before publish | Order + `NEW` outbox remain | Restarted publisher sends event, projection converges |
| F3 | Broker accepted, producer lost ack | Outbox may not be `SENT` | Retry may duplicate send, yet consumer applies one effect |
| F4 | Consumer commits, ack lost | Inbox + projection committed | Redelivery skipped and re-acked; no duplicate write |
| F5 | Consumer DB unavailable mid-transaction | Transaction rolls back, message unacked | After DB recovery, retry commits once |
| F6 | Broker unavailable/rebalance | Outbox stays pending, backlog grows | Reconnects, backlog drains within bounds, zero lost events |
| F7 | HTTP partner processed yet response lost | Outbound status stays uncertain | Retry with same operation ID creates no second effect |
| F8 | Cache GET/evict fails | Degraded or bounded stale cache | Source of truth stays valid, cache refreshes/invalidates |
| F9 | Bad schema or poison message | Retried/quarantined per policy | DLQ holds diagnostic metadata, valid messages progress |
| F10 | Two publishers/consumers contend; one pod dies | Physical duplicate receives/sends possible | DB uniqueness, claims/leases, and idempotency preserve exact effect counts |

**Not every scenario expects zero duplicate messages.** In F3 and F4, duplicate physical publishes or deliveries are normal under at-least-once; what you must prove is **zero duplicate business outcomes** and eventual convergence.

## 7. Case F1: Failure Before Source DB Commit

**Objective:** prove "order committed yet outbox missing" never occurs when both tables must update atomically.

**Setup:** create an order via a `@Transactional` service method. In the test profile, throw an exception **after inserting `orders` and `order_outbox`, right before commit**. Use a test hook inside the transaction rather than killing processes randomly.

~~~java
// Pseudocode of test hook, enabled only in test profile.
// Real business method still uses one DB transaction.
@Transactional
public UUID createOrder(CreateOrderCommand command) {
    UUID orderId = saveOrderWithUniqueOperationKey(command);
    saveOutboxEvent(orderId, command);
    faultHook.failIfEnabled("BEFORE_ORDER_COMMIT");
    return orderId;
}
~~~

`saveOrderWithUniqueOperationKey`, `saveOutboxEvent`, and `faultHook` are illustrative abstractions, not built-in Spring Boot APIs. The error must be thrown before commit and trigger rollback via the transaction manager; if the hook catches the exception and continues, the test no longer tests the failure window.

**Verification:**

- HTTP returns a controlled error; database holds **zero rows** in `orders` and `outbox` for the failed command.
- Re-sending the same `Idempotency-Key` with the hook disabled creates both rows once.
- If two HTTP requests with the same key arrive concurrently, the unique constraint picks one order; the other receives an idempotent response per contract or a handleable conflict error.
- Zero `OrderCreated` events were emitted from the failed transaction.

If tests reveal `orders` exists without `outbox`, verify both inserts share the same datasource/transaction manager and that no `REQUIRES_NEW` or in-transaction HTTP altered behavior.

## 8. Case F2: DB Committed Yet Publisher Crashed Before Sending

**Objective:** prove an independent pod/worker crash after DB commit never loses the event to publish.

**Setup:**

1. Call the create-order API and confirm `orders` and `order_outbox` committed.
2. Pause the outbox publisher or kill only the worker **before it reads the record**; leave DB running.
3. Verify `outbox.status=NEW`, `sent_at IS NULL`, and projection lacks the event.
4. Restart the publisher and watch it pick up the row, send to the broker, and mark `SENT` after ack.
5. Wait for the consumer to commit inbox and projection.

~~~mermaid
sequenceDiagram
    participant A as Order API
    participant D as Order DB
    participant P as Publisher
    participant B as Broker
    participant C as Consumer
    A->>D: COMMIT order + outbox(E42)
    Note over P: Publisher pod dies before reading E42
    D-->>A: Transaction committed
    Note over P: Restart
    P->>D: Poll outbox NEW
    P->>B: Publish E42
    B-->>P: ACK
    P->>D: Mark outbox SENT
    B-->>C: Deliver E42
    C->>C: Inbox + projection COMMIT
~~~

**Passing criteria:** one logical order, one outbox record for that event ID, converged projection, and no row permanently stuck in `NEW`. Physical sends may exceed one if additional faults occur; never assert "strictly one network send" as an invariant.

**Design red flags:** publishing directly inside the HTTP controller so post-commit crashes lose intent; storing outbox in a separate non-transactional database; running the scanner once at startup only; or pending queries missing rows stuck in stale leases.

## 9. Case F3: Broker Accepted Yet Producer Does Not Know

**Objective:** test **uncertain publish outcomes**. The broker may already have persisted the message even when the producer throws a timeout from a lost ack.

Distinguish two test levels:

- **Deterministic recovery test:** broker send succeeds and acks, then a hook kills the publisher **after ack, before updating outbox `SENT`**. Restarting guarantees re-sending the exact same event ID, proving downstream handles duplicates.
- **Network fault test:** place Toxiproxy/a network emulator between publisher and broker to drop or delay traffic during publish; observe timeouts/reconnects. A timeout alone **cannot prove** whether the broker persisted the message. Use supported logs, metrics, or broker queries to inspect broker state when needed.

~~~text
Outbox E42 = NEW/SENDING
  -> producer sends E42
  -> broker may have persisted E42
  -> ack never reaches publisher or pod dies
  -> outbox not yet marked SENT
  -> recovery resends E42
  -> consumer receives E42 1st and/or 2nd time
  -> unique inbox(eventId, handler) allows one DB effect
~~~

**Passing criteria:** outbox eventually clears, inbox records `E42`, projection shows one effect, and the retried event's `eventId` **did not change**. If the publisher generates a fresh UUID on retries, event-ID inbox deduplication breaks; fix that immediately at outbox creation.

**What to avoid:** assuming every `sendAsync()` failure means "broker definitely didn't store it"; marking `SENT` before ack; deduplicating by dropping messages based on pod name or offset; or tracking "already sent" solely in RAM.

## 10. Cases F4 and F5: Consumer Loses Ack or DB Fails Mid-Transaction

### 10.1. F4 — Projection Commits Yet Ack Is Lost

1. Consumer receives event `E42`.
2. Target DB transaction inserts `consumer_inbox(E42)`, updates `order_read_model`, and commits.
3. Hook severs connection or kills consumer **before ack**.
4. Broker redelivers `E42` to another consumer.
5. New worker attempts inbox insert with the same key, detects committed duplicate, skips updating projection again, and acks after verification.

~~~mermaid
sequenceDiagram
    participant M as Broker
    participant A as Consumer A
    participant D as Projection DB
    participant B as Consumer B
    M-->>A: Event E42
    A->>D: BEGIN; INSERT inbox; UPDATE read model
    A->>D: COMMIT
    Note over A: Dies before ACK
    M-->>B: Redeliver E42
    B->>D: INSERT inbox E42 → conflict
    B-->>M: ACK recorded duplicate
~~~

**Passing criteria:** one `(tenant,handler,E42)` receipt and one properly versioned projection; broker does not loop redeliveries forever; listener callback count may be ≥ 2 while business side effect count equals one.

### 10.2. F5 — Target DB Unavailable Before Commit

Simulate target database unavailability or throw an exception **before commit**. The transaction must roll back both inbox and business updates. The consumer must not ack as success; error handlers/backoff/retry topics or DLQs must enforce configured policy.

**Passing criteria:** while the DB is failing, no fake "processed" marker appears; once the DB recovers, redelivery commits inbox and projection once. Also test connection failures **at commit time**, where the client does not know if commit succeeded. Retries must rely on the unique inbox and real DB state rather than guessing from the exception.

### 10.3. Transaction and Ack Rules by Framework

| Consumer Framework | Boundaries to Inspect | Common Mistakes |
|---|---|---|
| Spring Kafka | Container ack/offset commit, DB transaction, error handler | Committing offsets before DB commit; inconsistent retry and DLT setup |
| Spring for Apache Pulsar | Ack/nack and redelivery, listener DB transaction | Assuming broker ack shares a JDBC transaction |
| Spring AMQP/RabbitMQ | Manual/auto ack, requeue/DLX, consumer concurrency | Early ack; infinitely requeuing poison messages |
| Spring Integration | Inbound adapter, error channel, advice/retries, transaction boundaries | Thinking error channels automatically roll back both DB and broker |
| Spring Batch message chunking | Job checkpoint and reader/ack modes per implementation | Restarting jobs with new identities causing duplicate processing |

Never slap a generic `@Transactional` on a handler and assume you have a distributed transaction. Verify which transaction manager governs each step; when DB and broker do not share an atomic transaction, design retries and idempotency to survive mid-step failures.

## 11. Case F6: Slow Broker, Network Partitions, and Bounded Recovery

When the broker goes down, committed source data remains safely in the outbox. Recovery aims to **lose zero events and avoid crashing DB/HTTP when the broker returns**.

Plan:

1. Create N orders with unique `eventId`s—large enough to observe backlog yet safe for test resources.
2. Block broker traffic via proxy or stop the broker container. Verify HTTP APIs and publishers meet their SLAs: never hang indefinitely, never drop outbox rows.
3. Observe outbox growing while publisher timeouts/retries use `backoff + jitter` and bounded concurrency.
4. Restore the broker and measure backlog drain rate, connection pools, pending send queues, and error rates.
5. Wait until backlog drops below threshold and verify every order has its matching projection.

**Required bounds:** connect/operation timeouts, max in-flight, bulkheads, retry caps or deadlines, circuit breakers (where fitting), outbox claims/leases, and worker concurrency. Never let one pod fire unbounded `sendAsync()` calls or let an HTTP request hold a DB transaction waiting on the broker.

With multiple publishers:

- Claim records via atomic row locks or conditional updates in DB; `SELECT ... FOR UPDATE SKIP LOCKED` supports short work distribution in PostgreSQL.
- When sends take time, persist `SENDING` with `ownerToken`/`leaseUntil` instead of holding a DB transaction open across network sends.
- When leases expire, another publisher can resend the same event. **Never rely on leases for exactly-once**; downstream must stay idempotent.
- In test reports, count unique `eventId`s at the source vs. committed business effects at the target, rather than raw `sendAsync()` counts.

**Passing criteria:** broker recovers, no outbox rows stay pending past the deadline, projections converge, side effects never scale with publish attempts, and resources (heap, threads, DB pools, queues) stay within test budgets.

## 12. Case F7: HTTP Partner Processed Request Yet Response Was Lost

An integration service may call shipping, payment, or invoicing APIs. This is where "timeout means operation failed" causes major bugs.

Example shipment creation workflow:

~~~http
POST /shipments HTTP/1.1
Idempotency-Key: shop-a:shipment:create:order-42
Content-Type: application/json

{"orderId":"00000000-0000-4000-8000-000000000042"}
~~~

Using WireMock or a custom stateful fake partner in tests, simulate:

1. Target **accepts and commits** the operation under key `shop-a:shipment:create:order-42`.
2. Target intentionally closes the socket or delays the response past the caller's read timeout.
3. Worker records **`UNKNOWN`/RETRYABLE** rather than assuming the request never executed.
4. After backoff, worker queries status if supported by the API or retries with **the exact same idempotency key**.
5. Target returns the original outcome without creating a second shipment.

**Passing criteria:** fake partner records one logical shipment despite two client attempts. Every retry carries the same operation ID and compatible payload. If the target supports neither idempotency nor lookup, use reconciliation/compensation; an application-side distributed lock cannot enforce exactly-once on a partner API.

Never execute a durable-retry HTTP call inside the inbox transaction and treat DB commit as proof the HTTP call succeeded. Persist a workflow/outbox record, drive workers post-commit, and record remote outcomes in recoverable states.

## 13. Case F8: Cache Failures and Post-Update Invalidation

Cache is a latency-reducing copy, never the source of truth confirming "order created" or "payment settled."

Separate at least three failures:

| Fault | What to Verify | Business Policy |
| --- | --- | --- |
| Cache GET timeout | Can HTTP query authoritative DB within budget? | Bounded fail-open fallback if data allows |
| Cache PUT failure | Is newly committed data still returned accurately? | Return source data; increment alerts/miss metrics |
| Cache eviction failure after DB update | Could stale entries violate freshness bounds? | TTLs/versioned keys, invalidation retries, or direct DB reads for sensitive decisions |

When an order update commits to DB and Redis disconnects before `evict`, **never pretend the DB transaction rolled back** because of the cache exception. Maintain invalidation recovery: durable events, outboxes, bounded TTLs, versioned keys, or direct source reads. For authorization, inventory, credit limits, or payment states, never rely on stale cache hits.

**Passing criteria:** source DB remains accurate; once cache recovers, entries invalidate/refresh; mass cache misses do not overwhelm the DB due to bounded fallbacks.

## 14. Case F9: Bad Schema, Poison Messages, and DLQ

Inject a malformed JSON or contract-violating event amid valid events:

~~~json
{
  "eventId": "20000000-0000-4000-8000-000000000042",
  "eventType": "OrderCreated",
  "schemaVersion": 999,
  "payload": {"orderId": null}
}
~~~

**Objective:** permanent errors must not spin in endless retries, drop valid events, or masquerade as processed successes.

- Validate envelopes before business handlers; separate deserialization errors, schema mismatches, invalid business data, and transient source errors.
- Retry transient faults within budget; route unrecoverable failures to DLQ/quarantine with controlled error reasons and correlation IDs.
- Never log full sensitive payloads. DLQs require access controls, retention, and dedicated redrive procedures.
- After fixing schemas/data, redrive **with the same business key/event ID** if still the same event; if issuing a new revision, define explicit rules.
- Never auto-ack poison messages as success without a business discard/quarantine decision. Also test ack behavior when DLQ publishing itself fails.

**Passing criteria:** subsequent valid events process per ordering guarantees, invalid events appear observably in quarantine/DLQ, and redrives cause zero duplicate business effects. For strictly sequential versioned workflows, newer versions must not leapfrog a failed version without reconciliation.

## 15. Case F10: Multiple Replicas Competing or Reprocessing

Run two publisher or consumer instances sharing a queue/DB, then kill one instance at critical moments.

### 15.1. Two Publishers on One Outbox Record

If two publishers run `SELECT status=NEW` before updating, both can send `E42`. Use atomic row-locking claims or conditional updates to minimize races. Even with claims/leases, **duplicates can still be emitted** on lease expiry, long GC pauses, or lost producer acks. Always verify both publish counts and downstream idempotency.

### 15.2. Two Consumers on One Event

Run two independent transactions with the same `eventId`. Worker A inserts `consumer_inbox(tenant,handler,E42)` and holds the transaction open; Worker B tries inserting the same unique key. The database lets one commit; if A rolls back, B can proceed. Final state must show **one inbox receipt and one business effect** despite concurrent callbacks.

### 15.3. Lease Expires While Old Worker Is Still Alive

Use a short lease so A pauses, B takes over, and A later resumes. `ownerToken` stops A from overwriting claim state, yet **does not stop** A from firing an HTTP call. Enforce monotonic fencing tokens verified by targets, or target-supported idempotency keys. Lacking those, tests must document guarantee limits and verify reconciliation rather than labeling the case "exactly-once."

### 15.4. Recovery After Restarts or Deployments

Repeat the scenarios above during:

- Rolling restarts of publisher pods mid-publish.
- Consumer assignment/rebalance mid-processing before ack.
- Outbox worker killed leaving records `SENDING` until lease expiry.
- Retry/backoff settings changing between deployments.

Verify new workers resume purely from **durable state**, never relying on in-RAM queues, maps, or caches on the dead pod.

## 16. Automating the Practice with Integration Tests

Layer tests to balance feedback speed with real technical evidence:

| Test Level | Focus | Reference Tools |
| --- | --- | --- |
| Unit | Exception classification, backoff math, dedup keys, versioning rules | JUnit 5, Mockito |
| DB Integration | Unique constraints, transaction rollbacks, outbox/inbox, concurrency | `@SpringBootTest`, Testcontainers PostgreSQL |
| Broker Integration | Publish/consume, redelivery, ack modes, retries/DLQ | Testcontainers broker |
| Fault Injection | Network cuts, timeouts, pod/worker restarts | Toxiproxy, WireMock, test hooks |
| End-to-End Recovery | Reconcile source DB and target DB post-fault | Awaitility, SQL probes, metrics/logs/traces |
| Staging Chaos | Scale-out, rolling restarts, production-like infra | Container/Kubernetes orchestration, observability |

### 16.1. Separating Observation Points from Fault-Injection Points

Enable only **one fault at a defined boundary** per case. Test hooks might expose:

~~~text
BEFORE_ORDER_COMMIT
AFTER_ORDER_COMMIT_BEFORE_PUBLISH
AFTER_BROKER_ACK_BEFORE_MARK_SENT
AFTER_CONSUMER_DB_COMMIT_BEFORE_ACK
BEFORE_CONSUMER_DB_COMMIT
BEFORE_PARTNER_RESPONSE
AFTER_LEASE_EXPIRED_BEFORE_WORKER_RESUMES
~~~

These names are **practice-designed fault hook interfaces**, not built-in Spring Boot APIs. A hook for `AFTER_ORDER_COMMIT_BEFORE_PUBLISH` sits in the post-commit worker/publisher or orchestration layer—**never** simulate it by throwing an exception *inside* the transaction and pretending it committed.

Hooks can be implemented via latches, spies, `@Primary` test beans, fault proxies, or test-harness control channels. When testing network faults, observe real connections and assert the fault actually fired rather than assuming `container.stop()` hit the exact microsecond desired.

### 16.2. Skeleton Test for a Lost-Ack Window

The Java snippet below illustrates **orchestration intent**. `IntegrationScenario` is a custom test-harness facade you build, not a Spring library class.

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;
import java.time.Duration;
import org.junit.jupiter.api.Test;

class OutboxRecoveryIT {
    private IntegrationScenario scenario; // @Autowired or test fixture.

    @Test
    void publisherCrashAfterBrokerAckMustNotDuplicateProjection() {
        var input = scenario.uniqueOrderCommand();

        // Simulate broker received event while outbox wasn't marked SENT.
        scenario.failOnceAt("AFTER_BROKER_ACK_BEFORE_MARK_SENT");
        var result = scenario.createOrder(input);

        // Wait for publisher recovery and projection convergence.
        scenario.restartFailedPublisher();
        await().atMost(Duration.ofSeconds(60)).untilAsserted(() -> {
            assertThat(scenario.outboxSent(result.eventId())).isTrue();
            assertThat(scenario.inboxReceiptCount(result.eventId()))
                    .isEqualTo(1);
            assertThat(scenario.projectedOrderCount(result.orderId()))
                    .isEqualTo(1);
            assertThat(scenario.projectedVersion(result.orderId()))
                    .isEqualTo(1);
        });

        assertThat(scenario.orderCount(input.operationId())).isEqualTo(1);
    }
}
~~~

`Duration.ofSeconds(60)` is an **illustrative test deadline**, not a guaranteed RTO. Size thresholds for your SLAs and CI runners. Assert that `failOnceAt` actually triggered (e.g., fault-hit counter equals 1) so tests never pass simply because execution bypassed the fault window.

### 16.3. Race Testing with Two Transactions

To verify cross-replica deduplication, run **two independent connections and transactions** synchronized by `CountDownLatch`/barriers. Have Worker A insert `consumer_inbox(E42)` and hold its transaction open while Worker B attempts inserting the same key.

Run both branches:

- **A commits:** B must not commit a second business effect; exactly one marker and read model exist.
- **A rolls back:** B acquires and proceeds; final result still holds one business effect.

Test against a real database like PostgreSQL; in-memory H2 does not reliably match production locking, isolation, or unique-constraint behavior. Count **committed rows** and outbound outbox events in addition to handler callback counts.

### 16.4. Distinguishing Infrastructure Tests from Business Tests

A test passing because a proxy severed a connection does not prove data recovered. Every test should assert two things:

1. **Fault assertions:** the fault fired at the intended point, and the request/worker experienced the expected timeout, crash, or rebalance.
2. **Data assertions:** invariants I1–I8 hold, zero data stays pending past SLA, and projection versions match the source.

Never treat "no exception at the end of the test" as sufficient proof of recovery.

## 17. Reconciling Data Using SQL and Business Keys

The core work after a fault is **comparing the source of truth against replicas and external side effects**, not merely counting messages.

### 17.1. Finding Committed Orders Missing Outbox Events

On the **source database**:

~~~sql
SELECT o.tenant_id, o.order_id, o.client_operation_id
FROM orders o
LEFT JOIN order_outbox b
    ON b.tenant_id = o.tenant_id
   AND b.aggregate_id = o.order_id
   AND b.event_type = 'OrderCreated'
WHERE b.event_id IS NULL;
~~~

If the design mandates "one `OrderCreated` per order in the same transaction," this query must return empty. Only run this when outbox retention covers the inspected window; if older rows are purged, check archives/audits before concluding an event is missing.

To detect **logically duplicate outbox events** with distinct `event_id`s:

~~~sql
SELECT tenant_id, aggregate_id, aggregate_ver, event_type,
       COUNT(*) AS n
FROM order_outbox
GROUP BY tenant_id, aggregate_id, aggregate_ver, event_type
HAVING COUNT(*) > 1;
~~~

This applies when the contract allows **one event type per aggregate version**. If business rules intentionally emit multiple events of the same type on one version, add an operation ID or sequence column to the grouping.

### 17.2. Finding Pending or Overdue Outbox Retries

~~~sql
SELECT status,
       COUNT(*) AS event_count,
       MIN(created_at) AS oldest_created_at,
       MAX(attempts) AS max_attempts
FROM order_outbox
GROUP BY status
ORDER BY status;
~~~

When the outbox tracks `next_attempt_at`, inspect due uncompleted rows:

~~~sql
SELECT event_id, aggregate_id, attempts, next_attempt_at
FROM order_outbox
WHERE status IN ('NEW', 'RETRYABLE')
  AND next_attempt_at <= now()
ORDER BY next_attempt_at, created_at
LIMIT 100;
~~~

The illustrative schema in section 4 uses `NEW` and `SENT`; `RETRYABLE` is an **optional state-machine status** for detailed failure tracking. Adjust queries to match your actual states. Rows stuck `SENDING` with no recovery after worker death indicate missing leases/reapers—never bulk-flip them to `SENT` via raw SQL.

### 17.3. Checking Receipts in the Target DB

On the **projection database**:

~~~sql
SELECT tenant_id, handler_name, event_id, COUNT(*) AS n
FROM consumer_inbox
GROUP BY tenant_id, handler_name, event_id
HAVING COUNT(*) > 1;
~~~

With `consumer_inbox`'s primary key, this query must always be empty; it verifies receipt integrity, though **not** that external effects weren't repeated. Inspect business records and remote systems too, especially when handlers trigger HTTP calls.

Check one order's version and state:

~~~sql
SELECT tenant_id, order_id, state, source_version
FROM order_read_model
WHERE tenant_id = 'shop-a'
  AND order_id = '00000000-0000-4000-8000-000000000042';
~~~

### 17.4. Reconciling Across Two Databases

When source and projection live in **two separate databases**, never write cross-DB SQL `JOIN`s pretending they share one transaction or datasource. Build a reconciliation worker/job:

1. Read target `order_id`s and versions from the source DB within an explicit watermark/snapshot.
2. Read projection data for matching tenant/order IDs.
3. Compare versions, states, and business-significant contract fields.
4. Bucket into `MISSING`, `STALE`, `CONFLICT`, and `OK`.
5. For `MISSING/STALE` beyond normal propagation windows, schedule replay from the outbox/source using **stable event IDs or business operation IDs**.
6. Never auto-overwrite `CONFLICT` or re-run payment side effects; route to investigation.

A `Spring Batch` job fits periodic large-scale reconciliation: checkpointed readers, time/tenant identifying parameters, persisted results, and bounded retries. On job restart after failure, preserve reconciliation run identity and keep repair actions idempotent. With Spring Integration, route mismatches to durable recovery flows or error channels—never turn an in-RAM error channel into an unbounded retry loop.

**Final criterion:** for any given business key, prove the source committed, the event was persisted/emitted, the consumer processed or quarantined it with a reason, and target/projection state aligns with data policy.

## 18. Measuring RPO, RTO, and Post-Fault Convergence

Anchor measurements consistently:

~~~text
T0 = fault begins
T1 = dependency or worker becomes healthy again
T2 = backlog begins draining steadily
T3 = data invariants verified and backlog within SLA

Functional recovery time ≈ T1 - T0
Post-recovery convergence time ≈ T3 - T1
Total time to consistent data state ≈ T3 - T0
~~~

These are analytical milestones; your service's **official RTO** may be defined per critical capability differently from `T3`, so align definitions with SLOs/SLAs. Never report "5-second RTO" just because the broker accepted connections at T1 while projections lagged for minutes.

Signals to collect:

| Signal | Purpose |
| --- | --- |
| `outbox_pending_total`, oldest pending age | Tracks unsent intent and backlog age |
| Publish success/error/timeout, queue depth | Distinguishes slow broker from blocked publisher |
| Broker lag/backlog, redeliveries, DLQ | Shows undelivered or looping messages |
| Consumer DB transaction latency, unique conflicts | Tracks processing delay and active deduplication |
| Projection version gap, reconciliation mismatches | Quantifies data correctness/staleness |
| Downstream HTTP idempotency hits/timeouts | Verifies external side effects |
| Retry attempts, circuit/bulkhead state, connection pools | Prevents recovery storms from causing cascading overload |
| Correlation ID, `eventId`, `orderId` in logs/traces | Controlled tracing across HTTP, DB, and broker |

Use bounded-cardinality metric tags like service, component, outcome, fault scenario, and broker topic (when topic count is bounded). Never attach raw `eventId`, `orderId`, tokens, or sensitive payloads as metric tags; keep event IDs in access-controlled logs/traces with appropriate retention.

### 18.1. Sample Practice Outcome Report

| Field | Example Filled from Real Measurements |
| --- | --- |
| Scenario | `F4: consumer commits then loses ack` |
| Version/config | Spring Boot, DB, broker, ack mode, isolation, replica count |
| Input | `tenant, operationId, orderId, eventId, aggregateVersion` |
| Fault activated | Injection timestamp, logs/hook hit/trace proof |
| State right after fault | Source DB, outbox, inbox, projection, broker lag |
| Recovery action | Consumer restart, reconnect, retry, or redrive |
| State post-recovery | Counts, version, idempotency result, pending age |
| RPO/RTO/convergence | Measured values and pass/fail criteria |
| Finding | Any invariant breached, root cause, and required fix |

**Never fabricate passing numbers:** results must come from real test runs and environment measurements. Having a well-designed test matrix does not mean the tests have actually been executed.

## 19. Real-Incident Data Recovery Runbook

During production incidents, never react by deleting metadata, changing event IDs, or replaying everything immediately. Follow a controlled workflow:

1. **Scope impact:** identify affected services, tenants, time windows, topics/subscriptions, and order/event IDs; gather alerts and traces.
2. **Stabilize root cause:** restore DB/broker/network/credentials and ensure connection pools/retries aren't causing storms; pause publishers or consumers in a controlled manner if needed.
3. **Capture evidence:** record source/outbox/inbox/projection row counts, watermarks, backlogs, DLQ contents, and latest errors before touching data.
4. **Classify actual states:** uncommitted orders, pending outbox, uncertain publish outcomes, committed-but-unacked inbox, stale projections, or uncertain remote HTTP calls.
5. **Recover in safe order:** let publishers drain durable outbox; let idempotent consumers handle redeliveries; replay DLQ only after fixing schemas/configs; rebuild projections from source snapshots/aggregate versions if needed.
6. **Reconcile source and targets:** run per-tenant/time-window reconciliation, verify I1–I8, and reconcile external HTTP systems via operation IDs.
7. **Restore traffic:** ramp concurrency safely while watching DB pools, broker lag, retries, DLQs, and cache invalidation.
8. **Close incident:** document fault timestamps, convergence time, retried event counts, blocked duplicates, and any remaining mismatches.

**Actions never to automate unconditionally:** bulk-setting `outbox.status='SENT'` without acks; deleting `consumer_inbox` rows to force re-runs; minting new event IDs for the same business operation; acking poison messages without quarantine; or cranking concurrency indefinitely to drain backlogs. Such actions mask or multiply bad data.

### 19.1. When Is Manual Intervention Required?

- Same idempotency key with differing payloads: must determine which request is valid.
- Two systems committed conflicting states with no automated resolution rule.
- Remote payment/invoice API lacks lookup or idempotency; needs evidence-based reconciliation.
- DLQ holds messages with incompatible schemas/versions that cannot auto-transform.
- Old events are replayed past dedup retention windows, risking duplicate side effects.
- Business logic changes require reprocessing rather than retrying a transient fault.

These cases require an explicit decision record and business owner sign-off; "the worker finished running" does not mean the data is right.

## 20. Common Mistakes That Produce False Test Passes

- **Killing containers at random:** you don't know if the crash landed before or after commit/ack; results lack diagnostic rigor.
- **Equating sent/received message counts with once-only execution:** at-least-once brokers repeat deliveries; count committed business effects.
- **Using Redis locks instead of DB transactions/unique constraints:** expired leases or crashed workers still race and duplicate.
- **Marking outbox `SENT` before broker ack:** opens an event-loss window on publish failures.
- **Acking before DB commit:** loses work when consumers crash.
- **Treating HTTP timeouts as guaranteed failures:** ignores uncertain remote execution.
- **Minting new `eventId` or idempotency keys on retries:** blinds deduplication to repeated business operations.
- **Editing metadata with SQL to force reruns:** breaks audit history and state machines; follow state-machine runbooks.
- **Using H2 instead of PostgreSQL for race tests:** locking, upserts, and isolation behavior differ.
- **Asserting only final state without proving fault activation:** tests pass even when the fault hook never ran.
- **Treating cache as source of truth:** stale entries serve wrong state after DB updates.
- **Skipping post-recovery backlog and data checks:** brokers may reconnect while target data remains missing.

## 21. Practice Completion Checklist

- [ ] Identified sources of truth, HTTP/DB/broker/cache steps, and transaction boundaries.
- [ ] Defined concrete data invariants covering business IDs, event IDs, versions, and remote side effects.
- [ ] Test profile can inject faults before/after commits, publishes, acks, and HTTP responses.
- [ ] Fault-free baseline confirms accurate source/outbox/inbox/projection data.
- [ ] F1–F10 each have at least one repeatable test/scenario explicitly verifying the fault fired.
- [ ] Transactional inbox/outbox and unique constraints are verified on a production-compatible DB.
- [ ] Consumer acks post-commit with bounded retries/DLQ; publisher uses bounded queues/leases/recovery.
- [ ] Remote HTTP uses durable idempotency keys or reconciliation/compensation workflows.
- [ ] Cache failures never mutate authoritative sources, and invalidation bounds staleness.
- [ ] SQL probes and cross-database reconciliation exist using business keys/versions.
- [ ] Reports capture fault points, post-fault state, recovery actions, post-recovery counts, and measured RPO/RTO.
- [ ] Runbooks exist for non-recoverable states; never blindly replay or wipe receipts.

**Core principle:** partial-failure simulation is valuable only when you verify **the exact failure point**, **surviving state immediately after the fault**, and **durable outcomes post-recovery**. In Spring Boot, transactions and unique constraints preserve atomicity per database; outbox/inbox, properly timed acks, idempotency, and reconciliation bridge HTTP, cache, and broker boundaries. A system is recovered when business invariants are verified—not simply when service health reports `UP`.

### References

- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transaction boundaries, rollbacks, propagation, and transaction managers.
- [Spring Boot — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html): `@SpringBootTest`, test slices, and integration testing.
- [Spring Integration — Testing Support](https://docs.spring.io/spring-integration/reference/testing.html): testing flows, channels, and integration endpoints.
- [Spring for Apache Kafka — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html): broker transaction scope and limits with external systems.
- [Testcontainers for Java — PostgreSQL](https://java.testcontainers.org/modules/databases/postgres/): PostgreSQL test container.
- [Testcontainers for Java — Toxiproxy](https://java.testcontainers.org/modules/toxiproxy/): network-layer fault injection.
- [WireMock Documentation](https://wiremock.org/docs/): HTTP stubbing, fault simulation, and request verification.
- [PostgreSQL — INSERT and ON CONFLICT](https://www.postgresql.org/docs/current/sql-insert.html): upserts and unique constraints.

These examples use illustrative APIs/DSLs to explain the practice; `faultHook` and `IntegrationScenario` must be implemented in your application's test harness. Align with your exact Spring Boot, broker, testing library versions, and data contracts before implementation. Writing this lesson completes STEP 4; empirical verification and academic QA review will be performed in separate steps.
