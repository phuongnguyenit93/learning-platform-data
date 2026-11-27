# Idempotent Receiver Pattern in Spring Integration Adapters

## 1. Why Can a Message Arrive Twice?

Imagine a system receiving an `ORDER_CONFIRMED` event from Kafka, updating order status in a database, and sending a notification. The database updates successfully, yet right before the consumer commits the offset, the JVM stops. Kafka may redeliver the record when the consumer restarts; if the handler reruns the entire business logic, the user could receive two notifications or two recorded transactions.

This scenario is not unique to Kafka. **HTTP client retries after timeouts, JMS/AMQP redeliveries, SFTP re-scans, JDBC row re-polls, File watcher re-emissions, broker failovers, or operator DLQ replays** can all deliver the same *logical event* to the receiver multiple times.

**Idempotent Receiver** is an **Enterprise Integration Pattern** designed so the receiving side safely recognizes and handles repeated deliveries: **a business event that has already been processed successfully must not produce unintended extra side effects when it appears again**.

In the **SPRING_INTEGRATION_ADAPTERS** module, this pattern connects to inbound/outbound adapters, gateways, pollers, and `MessageChannel`, across File/SFTP/HTTP/JMS/AMQP/Kafka/database flows, as well as message contracts, retries, errors, and connection lifecycles. It belongs in the **Design patterns** chapter because it is a **receiver architectural decision**, not just an `if (seen) return` check.

### Learning objectives

After this lesson, you can:

1. Distinguish **duplicate delivery, duplicate processing, idempotent side effects**, and “exactly-once” at different boundaries.
2. Choose a stable **idempotency key** with appropriate scope and lifecycle.
3. Design **atomic check-and-record** using a metadata store or a database with unique constraints.
4. Use Spring Integration's **`IdempotentReceiverInterceptor`/`MetadataStoreSelector`** mechanisms where appropriate.
5. Handle crashes, concurrency, retries, DLQs, transactions, broker ACKs, and external side effects.
6. Apply the pattern to File, SFTP, HTTP, JMS, AMQP, Kafka, and JDBC, and test critical race conditions.

> **Guiding principle:** *An idempotent receiver does not turn every distributed flow into exactly-once*. You must define whether “once” means **one DB update**, **one API call**, **one broker publish**, or **one business completion**; each goal demands a different confirmation checkpoint.

## 2. Core Terminology

| Term | Meaning in this lesson | Example |
|---|---|---|
| **Logical event** | Business event/command to process | “Order A was paid” |
| **Delivery** | One transport delivery of a message | Kafka poll / JMS delivery |
| **Processing attempt** | One handler invocation | Retry #1, #2 |
| **Side effect** | Observable change outside the handler | DB write, funds transfer, file creation, publish |
| **Idempotency key** | Key identifying a processed logical operation | `tenant:order-confirmation:event-74` |
| **Duplicate** | Reappearance of a logical operation already/currently processed | Event 74 redelivered |
| **Claim/dedup reservation** | Step claiming processing rights by key | Unique insert / put-if-absent |
| **Completion marker** | Proof an operation completed within defined scope | Transactional `COMPLETED` record |
| **Redelivery** | Broker resends an already-delivered message | JMS rollback, AMQP NACK/requeue |
| **Replay** | Intentional reprocessing from DLQ/topic/file/log | Reprocessing events on request |
| **Idempotent effect** | Reapplying the same command leaves state unchanged after first run | `SET status=PAID` rather than `balance += amount` |

### 2.1. Redelivery is not always a bug

Many transports are designed for **at-least-once delivery** or retries to increase reliability. Keeping a message and redelivering on uncertain ACK is usually better than losing data. Receivers must therefore accept duplicates as **normal operating conditions**.

### 2.2. Duplicate delivery vs. duplicate business action

A receiver getting three deliveries of one event may log **three attempts** while producing only **one committed side effect** within the chosen business scope. Counting handler invocations to report processed orders would inflate metrics.

## 3. Common Sources of Duplicates

| Source | Why does it repeat? | What to verify |
|---|---|---|
| **HTTP inbound gateway** | Client retries on dropped connections or timeouts | Idempotency-Key, server state, response replay |
| **HTTP outbound gateway** | Receiver calls remote and misses response | Remote may have already committed |
| **File inbound** | Restarts, file filter/metadata store loses state | File identity, fingerprint, lifecycle |
| **SFTP inbound** | Interrupted transfer, remote file still present, restart | Remote identity, metadata store, rename/handoff |
| **JMS inbound** | Transaction rollback, incomplete ACK | Message ID, redelivery, DB transaction |
| **AMQP inbound** | NACK/requeue, unacked messages when consumer dies | Delivery count, DLQ, consumer ACK |
| **Kafka inbound** | Uncommitted offsets, rebalances, retries/replays | Topic-partition-offset and event ID |
| **JDBC inbound poller** | Row not yet marked processed on crash | Watermark/processed marker and transaction |
| **QueueChannel** | App proactively resubmits or job retries | Retry key and in-memory/durable state |
| **Batch splitter** | Entire batch reruns while some items already finished | Parent/child identity, per-item completion |
| **Operator replay** | Re-injects DLQ/file into the flow | Replay policy, idempotency window |

A re-transmitted message does not necessarily keep **the same Spring Message ID**, timestamp, trace ID, or broker delivery tag. Selecting a key solely from one of those fields can prevent the receiver from **recognizing the same business operation**.

## 4. Idempotent Receiver Model: Identify Before Causing Side Effects

~~~mermaid
flowchart TD
    A[Inbound adapter / gateway] --> B[Message and event contract]
    B --> C[Validate key, scope, operation]
    C --> D{Atomic claim / lookup}
    D -->|Completed duplicate| E[Skip effect or replay prior result]
    D -->|New claim| F[Apply business effect]
    F --> G{Effect committed?}
    G -->|Yes| H[Record COMPLETED / receipt]
    G -->|No, rollback| I[Release in same transaction / retry safely]
    D -->|In progress/unknown| J[Retry later, wait or reconcile]
    H --> K[ACK / reply per protocol]
    E --> K
    I --> L[Error / retry / DLQ policy]
    J --> L
~~~

Crucial decision point: **never mark “completed” before the protected side effect is actually confirmed**, unless marker and side effect are updated **in the same atomic transaction**. Conversely, never let two workers process concurrently after both read `seen=false` and then both write.

### 4.1. “Drop duplicate” is only one option

For one-way consumers, completed duplicates can be **skipped and ACKed**. For HTTP request/reply, duplicate calls may need to **replay the previous result** (status/body/reference) per contract instead of staying silent and timing out the client. For in-progress duplicates, return `202`/`409`/`Retry-After` depending on API design—there is no single mandatory response across all systems.

### 4.2. Three states to separate

- **NEW:** key has not been processed; workers can race to claim it.
- **IN_PROGRESS/UNKNOWN:** someone claimed it without confirming completion; do not treat as success.
- **COMPLETED:** side effect satisfied the completion definition with durable proof.

If persisting final errors/responses for replay, you can add `FAILED_TERMINAL` or `FAILED_RETRYABLE`, while explicitly defining whether a failed request may be retried under the same key.

## 5. The Hardest Step: Defining “The Same Operation”

### 5.1. Designing an idempotency key

A good key must be:

1. **Stable** across initial receipt and redeliveries/retries of the same logical operation.
2. **Unique within the scope** being protected: tenant, source, operation type, or business event ID.
3. **Invariant** under serialization, message conversion, consumer rebalances, or deployments.
4. **Discriminating** enough to separate genuinely different business tasks.
5. **Governed by allocation/trust policies** when supplied by external systems.
6. **Free of credentials/PII** in logs, public cache keys, or metric labels.
7. **Retained over a window** matching retry horizons, broker retention, and replay needs.

Conceptual example:

~~~text
idempotencyKey = namespace + ":" + tenantRef + ":" +
                 operationType + ":" + stableEventId
~~~

`tenantRef` is a valid internal ID or managed opaque reference, not raw customer emails/names. `stableEventId` must come from a trusted source or a durable mapping.

### 5.2. Commonly wrong keys

| Key | Why is it dangerous? | When can it be used? |
|---|---|---|
| `MessageHeaders.ID` | Newly created messages get different IDs | Only when deduplicating a specific local message instance |
| `traceId`/`spanId` | Traces change across retries and replays | Never use as a business idempotency key |
| Kafka topic-partition-offset | Identifies one physical record, fails if producer writes event twice | When requirement is strictly processing each Kafka record once |
| `JMSMessageID` | May differ if producer republishes the same logical event | When contract only requires identity per JMS delivery record |
| Filename | Same name with new content or renames; names may contain PII | When source guarantees non-reused trusted filenames |
| `lastModified` alone | Collisions, clock resolution, timestamp mutations | Secondary signal in file identity |
| Raw HTTP body hash | Body may contain PII; canonicalization/schema issues | Only with controlled hashing and explicit contract |
| Arbitrary client key | Spoofable / cross-tenant collisions | Only after auth, scope, length, ownership, and conflict checks |
| Current timestamp | Retries generate new keys | Almost never appropriate |

### 5.3. Same key, different payload

Suppose a second HTTP request reuses the same `Idempotency-Key` with a different amount/recipient. Simply returning the old result can hide bugs or invite abuse. Store a **canonicalized request fingerprint** or immutable required business attributes, then:

- Same key + same fingerprint + completed → return prior result.
- Same key + different fingerprint → **reject conflict**, never run another operation under the same key.
- Same key + IN_PROGRESS → respond “processing” or apply wait/retry policy.

Fingerprints must be stored/compared safely without logging raw sensitive content. Canonicalization must account for JSON field ordering, decimal formatting, locales, schema versions, and API semantics.

## 6. Atomicity: Why `containsKey` Followed by `put` Is Wrong

### 6.1. Classic race condition

~~~mermaid
sequenceDiagram
    participant A as Consumer A
    participant S as Dedup Store
    participant B as Consumer B
    participant DB as Business Database
    A->>S: contains(key) = false
    B->>S: contains(key) = false
    A->>DB: Apply side effect
    B->>DB: Apply side effect
    A->>S: put(key, completed)
    B->>S: put(key, completed)
    Note over A,B: Same logical event creates two side effects
~~~

Both consumers see “unprocessed” and both execute. Adding `synchronized` inside one JVM protects only that instance—**insufficient across multiple pods/processes**.

### 6.2. Appropriate primitives

- **Database unique constraint** on the idempotency key, with insert and side effect in an appropriate transaction.
- **Atomic `putIfAbsent`/compare-and-set** on a **shared `ConcurrentMetadataStore`**, when claiming before processing.
- **Conditional insert / optimistic version** with policies handling `IN_PROGRESS`.
- **Business unique key/constraint** on the target table when the side effect creates a resource.
- **Remote API idempotency contract** when the side effect lives in another service.

Atomic **claiming** alone is not enough; you must also understand **the side effect's commit point** and message ACK timing.

### 6.3. Limits of distributed locks

A distributed lock prevents concurrent execution, yet if the lease expires while a worker is still running or during a network partition, another worker can enter. For critical side effects, use **fencing tokens/versions, target-side uniqueness, or transactional design**—not just “holding a Redis lock.”

## 7. State Machine of an Idempotent Operation

~~~mermaid
stateDiagram-v2
    [*] --> ABSENT
    ABSENT --> IN_PROGRESS: Atomic claim
    IN_PROGRESS --> COMPLETED: Effect + durable commit
    IN_PROGRESS --> RETRYABLE: Transient error / recovery
    RETRYABLE --> IN_PROGRESS: Safe retry with ownership
    IN_PROGRESS --> UNKNOWN: Timeout after external call
    UNKNOWN --> COMPLETED: Reconciled positive
    UNKNOWN --> RETRYABLE: Reconciled negative
    IN_PROGRESS --> FAILED_TERMINAL: Permanent failure
    COMPLETED --> COMPLETED: Duplicate / replay result
    FAILED_TERMINAL --> FAILED_TERMINAL: Duplicate per policy
~~~

### 7.1. How long to retain completion markers?

Deleting markers too early turns an older replayed message into **NEW** and re-executes it. TTL must cover **maximum retry/redelivery duration, DLQ replay windows, batch re-imports, source retention, and business obligations**. For payments or resource creation, keys/receipts may need retention far longer than a cache TTL.

### 7.2. Stuck claims

A worker claims a key and crashes before completion → `IN_PROGRESS` stays forever without recovery. Use **conditional leases/timeouts**, owner tokens/versions, and mechanisms to check actual business effects before permitting retries. Never treat a stale marker as “definitely uncommitted”: if an external call already went out, state may be `UNKNOWN`.

### 7.3. Mark before vs. mark after

| Marking timing | Risk |
|---|---|
| **Mark completed before side effect** | Crash causes retries to skip unprocessed work |
| **Side effect before marking completed** | Crash causes retries to duplicate the side effect |
| **Marker and side effect in same DB transaction** | Solves mutations in the same database, does not cover external APIs |
| **Remote idempotency key + reconciliation** | Reduces duplicate external effects; requires remote contract support |

## 8. How Spring Integration Supports Idempotent Receiver

Spring Integration includes components supporting the **Idempotent Receiver pattern**, notably:

- **`IdempotentReceiverInterceptor`:** advice wrapping a message endpoint/handler to detect duplicates via a selector.
- **`MetadataStoreSelector`:** evaluates keys and stores/compares metadata to decide whether a message has been seen.
- **`MetadataStore`/`ConcurrentMetadataStore`:** stores key/value entries; implementation choice governs durability and atomicity.
- Version-compatible **endpoint advice** configurations or annotations.

**Exact classes and DSL APIs must be verified against your Spring Integration version.** The pattern works simply for flow-level duplicate tracking; when side effects require strong consistency, still verify **markers, transactions, ACKs, and remote outcomes**.

### 8.1. Where the interceptor attaches determines scope

~~~text
Inbound -> deserialize -> validate -> [IDEMPOTENT RECEIVER] -> business handler -> outbound
~~~

Attaching advice:

- **Too early**, before obtaining a trusted key or canonicalized payload, risks wrong deduplication.
- **Too late**, after a side effect already ran, fails to block upstream duplicates.
- **On the wrong channel**, messages may route elsewhere or be split prior to dedup.
- **On one handler in pub/sub**, only that branch is protected, not all subscribers.
- **Per item after a splitter**, the key must specify item identity rather than only batch ID.

### 8.2. Duplicate flag vs. “drop”

Depending on configuration/version, the advice may **mark a duplicate header** (often related to `IntegrationMessageHeaderAccessor.DUPLICATE_MESSAGE`), route to a discard channel, suppress handler invocation, or behave otherwise. **Never assume** adding the interceptor automatically drops all duplicates or rolls back markers when a handler fails. Check your exact version's API and behavior, then write integration tests.

### 8.3. Need a contract-backed key generator

Never let the selector fall back to raw `MessageHeaders.ID` if logic must deduplicate a business event redelivered under a new Spring Message ID. Supply the selector with **event ID + scope + operation**, validated and canonicalized before lookup.

## 9. MetadataStore: What to Store, Where, and Does It Survive Restarts?

| Option | Scope | Best fit | Risk |
|---|---|---|---|
| **In-memory metadata store** | Single JVM/process | Demos/tests or non-critical short caches | Lost on restart; unshared across replicas |
| **Persistent shared store (JDBC/Redis as suited)** | Multiple instances | Dedup surviving restarts/scale-out | Needs atomic ops, migrations, TTLs, and HA |
| **Business database unique constraint** | Transaction with domain state | Guaranteeing single DB effect | Does not directly cover external side effects |
| **Remote target idempotency** | Target service side | Outbound HTTP/payment/resource creation | Depends on provider TTL, scope, and semantics |
| **Object/file metadata store** | File/SFTP sources | Tracking polled/accepted files | Not equivalent to downstream business completion |

### 9.1. `ConcurrentMetadataStore` is an abstraction, not magic

Having `putIfAbsent` or `replace` on the interface does not mean every backend automatically:

- Shares state across replicas under your current config.
- Survives crashes, failovers, or TTLs.
- Joins an atomic transaction with business tables.
- Guarantees accurate duplicate markers after remote API timeouts.

Evaluate the concrete implementation, consistency model, network failures, capacity, and data recovery.

### 9.2. Metadata state in demos vs. production

A demo can use `SimpleMetadataStore` to watch the interceptor detect duplicates **within one JVM**. Production multi-replica setups and crash recovery typically require a **shared durable store** or transactional dedup in the business database.

### 9.3. Do not confuse `AcceptOnceFileListFilter` with business idempotence

File/SFTP inbound adapters can use accept-once filters and metadata stores to avoid re-picking already-seen files. That protects only **file detection/ingestion**, not whether transformers, databases, or outbound HTTP calls **completed business logic**. A file marked “seen” whose handler failed may still require controlled retries.

## 10. Interceptor Configuration: Design Blueprint (Version-Aware)

The pseudocode below conveys **integration intent**, not verified Java code compiling across every Spring Integration release:

~~~text
sharedStore = durable_concurrent_metadata_store()
selector = MetadataStoreSelector(
    key = message -> canonical(
        tenantRef, operationType, trustedBusinessEventId),
    store = sharedStore)

advice = IdempotentReceiverInterceptor(selector)

integrationFlow:
    inboundMessage
      -> validateIdentityAndSchema
      -> handler(with advice, id="receiveOrder")
      -> downstreamSideEffects

onDuplicate:
    if completed: skip effect, ACK or return prior result
    if inProgress/unknown: retry later or reconcile
~~~

In a real project:

1. Check packages/classes/constructors/DSL `advice` for **your exact version**.
2. Verify the interceptor attaches to the **intended endpoint**.
3. Read docs/tests for duplicate flags and discard behavior.
4. Verify when keys are written relative to handler success/exceptions.
5. Choose a store with matching durability/concurrency guarantees.
6. Separate duplicate detection from **completion semantics** for external side effects.
7. Test restarts, handler throws, two parallel consumers, broker redeliveries, and key changes.

When store and side effects cannot be made atomic together, consider **DB unique constraints/inbox/outbox** as shown next.

## 11. Simple Yet Strong: Unique Constraints and Business Effects in One Transaction

For mutations within **the same database**, place a **processed events** table with a unique key and execute the business update **in the same DB transaction**.

### 11.1. PostgreSQL SQL example

~~~sql
CREATE TABLE processed_event (
    tenant_ref   varchar(80)  NOT NULL,
    operation    varchar(80)  NOT NULL,
    event_id     varchar(160) NOT NULL,
    processed_at timestamptz  NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_ref, operation, event_id)
);

CREATE TABLE inventory_projection (
    tenant_ref varchar(80)  NOT NULL,
    sku_ref    varchar(160) NOT NULL,
    quantity   bigint       NOT NULL,
    PRIMARY KEY (tenant_ref, sku_ref)
);
~~~

**Illustrative schema only.** `processed_event` scopes `tenant + operation + eventId`. If source event IDs aren't sufficiently stable or keys can be reused across differing payloads, add a request fingerprint/semantic version and check for conflicts.

### 11.2. Receiver service with Spring JDBC

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

record InventoryEvent(
        String tenantRef,
        String eventId,
        String skuRef,
        long quantityDelta) {}

enum ApplyResult { APPLIED, ALREADY_APPLIED }

@Service
public class InventoryEventReceiver {
    private final JdbcTemplate jdbc;

    public InventoryEventReceiver(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public ApplyResult applyOnce(InventoryEvent event) {
        // Validate trusted IDs/schema/tenant ownership before this step.
        int claimed = jdbc.update(
            """
            INSERT INTO processed_event(tenant_ref, operation, event_id)
            VALUES (?, 'INVENTORY_ADJUST', ?)
            ON CONFLICT DO NOTHING
            """,
            event.tenantRef(), event.eventId());

        if (claimed == 0) {
            return ApplyResult.ALREADY_APPLIED;
        }

        int updated = jdbc.update(
            """
            UPDATE inventory_projection
               SET quantity = quantity + ?
             WHERE tenant_ref = ? AND sku_ref = ?
            """,
            event.quantityDelta(),
            event.tenantRef(),
            event.skuRef());

        if (updated != 1) {
            throw new IllegalStateException("INVENTORY_ROW_NOT_FOUND");
        }
        return ApplyResult.APPLIED;
    }
}
~~~

### 11.3. Explaining correctness and limits

- `@Transactional` must genuinely be active via Spring proxies/an appropriate transaction manager.
- **Inserting the marker + updating the business row** inside **the same PostgreSQL transaction** rolls back both if the update fails.
- The unique constraint blocks two concurrent consumers with the same key.
- If the first transaction rolls back, a later transaction can claim and process.
- If commit succeeds yet broker ACK fails, redelivery sees the existing key and skips the duplicate update.
- This example does not check payload fingerprints; production must handle **same key, different command**.
- This example protects only **one DB side effect**. Adding an HTTP call or Kafka publish inside the transaction does not extend atomicity remotely.
- Inputs must be validated (tenant, ID, quantity, domain rules); duplicate detection does not replace authentication/authorization.
- `UPDATE ... quantity + delta` is **not inherently idempotent**; the transactional unique marker prevents a second execution.

### 11.4. Spring Integration handler calling the service

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
public class InventoryInboundFlow {
    @Bean
    IntegrationFlow inventoryEvents(InventoryEventReceiver receiver) {
        return IntegrationFlow.from("inventoryEventsInput")
                .handle(message -> {
                    InventoryEvent event =
                            (InventoryEvent) message.getPayload();
                    receiver.applyOnce(event);
                }, endpoint -> endpoint.id("applyInventoryOnce"))
                .get();
    }
}
~~~

This is an illustrative **one-way** flow without a specific adapter/broker. When consuming from Kafka/JMS/AMQP, configure matching ACK/transaction/error handling: the service returning `ALREADY_APPLIED` should be treated as a **safe success** for a redelivered already-completed delivery.

## 12. When Business Logic Calls External Systems: There Is No Free Atomic Transaction

Suppose a receiver inserts `processed_event` into the DB and then calls an HTTP payment service. Four scenarios:

| Crash point | DB marker | Remote payment | Consequence on naive retry |
|---|---|---|---|
| Before marker commit | Absent | Absent | Can reprocess |
| After marker commit, before HTTP call | Present | Absent | Duplicate skipped, **lost side effect** |
| After remote commit, before marker | Absent | Present | Retry may **double-charge** |
| After marker and remote effect, before broker ACK | Present | Present | Redelivery must safely skip |

**A single `processed_event` table cannot fix all four scenarios** if the remote system does not join the same transaction.

### 12.1. Design approaches

- **Remote idempotency key:** repeated commands are deduplicated by the target itself with response replay/reconciliation.
- **Transactional Outbox:** one DB transaction commits domain changes and the **intent to publish/call**; a separate worker dispatches from the outbox with safe retries.
- **Inbox + Outbox:** consumer records input, updates domain state, and inserts outbound intent in one transaction.
- **Saga/compensation:** when multiple services hold independent side effects, maintain step state and compensating actions.
- **Reconciliation:** timeouts with unknown outcomes query target state before repeating risky operations.

### 12.2. “Exactly once” must be scoped

Kafka transactions support certain consume–process–produce flows contained within the broker; when involving **external databases, HTTP payment APIs, email/SFTP/filesystems**, those side effects do not join Kafka transactions automatically. Verify per-system semantics before promising “exactly once.”

## 13. Inbox + Transactional Outbox: Durably Pairing Inbound and Outbound

~~~mermaid
flowchart LR
    BROKER[JMS / AMQP / Kafka / HTTP ingress] --> IN[Inbox Receiver]
    IN --> TX[One Local DB Transaction]
    TX --> DEDUP[Unique Inbox Key]
    TX --> DOMAIN[Business State]
    TX --> OUTBOX[Outbound Intent / Outbox Row]
    OUTBOX --> DISPATCH[Outbox Dispatcher + Retry]
    DISPATCH --> TARGET[HTTP / Broker / SFTP]
    TARGET --> CONFIRM[ACK / Receipt / Reconciliation]
    CONFIRM --> STATUS[Outbox Outcome]
~~~

### 13.1. Processing flow

1. Inbound arrives with a valid **event key** and verified payload.
2. In **one local DB transaction**, insert the unique inbox marker, update domain state, and insert the outbox row (with `outbound_command_id`).
3. If the transaction rolls back, neither marker, domain state, nor outbox row commits.
4. If commit succeeds yet inbound ACK fails, redelivery sees the inbox key and skips mutating domain state again.
5. The outbox dispatcher sends the command, retrying as needed and relying on **target-side idempotency** or readbacks.
6. Confirm target completion and update outbox status; on timeout, mark `UNKNOWN` and reconcile.

### 13.2. Why outboxes can still send duplicates

The dispatcher can finish sending and crash before marking the outbox row `SENT`. On restart, it sends again. Outbox guarantees **outbound intent is not lost**, not that targets execute once if targets lack idempotency/reconciliation. Outbound command IDs must stay stable across attempts.

### 13.3. Be careful with `COMPLETED` status

An inbox event marked `COMPLETED` may only mean **domain state and outbox intent committed**. If business rules require “partner processed,” maintain a separate completion status on **outbox/remote outcome**. Never overload one flag for both meanings.

## 14. File Inbound/Outbound: File Identity Is Not Business Identity

### 14.1. A file can reappear

File scanners/pollers may see a file again after restarts, lost metadata store state, renames/copies, or re-uploads. Using only filenames risks skipping a new document with the same name; using full content hashes risks wrongly merging **two distinct business events** that happen to share identical content.

### 14.2. Suggested keys and scopes

| Unit | Candidate key | Warning |
|---|---|---|
| An identified file drop | Producer file ID/manifest ID | Requires source contract guaranteeing uniqueness |
| A specific file version | Source ID + stable version/generation | Never rely on `lastModified` alone |
| A record inside a file | Batch ID + record ID/sequence | Sequence is meaningful only within its batch |
| A business command in a file | Stable business event ID | Great if genuinely guaranteed by source |
| A poll cycle | Poll ref | Observability only, **never** an idempotency key |

### 14.3. Accept-once and business receiver

A useful combination:

1. **File accept-once filter** avoids re-polling already-ingested files.
2. **Idempotent receiver** ensures already-committed records/commands do not re-run if a file is reprocessed.
3. **Transaction/Outbox** preserves domain outcomes and downstream emission intent.
4. **Checkpoints and retries** protect against stream-read, parsing, or upload failures.

Never mark a file “business completed” simply because the inbound adapter emitted a message. For a file holding 10,000 records, track completion at appropriate **record/batch** granularity.

## 15. SFTP: Metadata Stores, File Transfers, and Duplicate Delivery

SFTP inbound typically involves remote directory listing, filtering, local transfer, and downstream processing. Notable failures:

- Connection timeouts leaving partial file downloads.
- File downloaded before updating the remote metadata store.
- Remote filenames reused for new content.
- Two replicas polling the same remote file without shared locks/filters.
- Source retrying an upload causing the same business event to appear twice.

### 15.1. Safe design

1. Establish **remote file identity** per source contract rather than filename alone.
2. Use a persistent/shared metadata store or distributed coordination across multiple replicas.
3. Avoid reading partially uploaded files; use producer manifests/renames/ready markers.
4. Separate **download completed** from **business processing completed**.
5. For multi-record files, deduplicate at the record/business command level where needed.
6. For SFTP outbound, consider atomic handoffs/renames and duplicate remote writes.
7. On timeouts, check remote state before retrying; never treat `send()` as committed.

### 15.2. Never handle duplicates by deleting source files prematurely

Deleting SFTP files without authorization or before handlers finish destroys retry/audit trails. Archive/move/delete strictly per **source contracts, retention, and verified completion**—never as a crude dedup shortcut.

## 16. HTTP Inbound Gateway: `Idempotency-Key` and Response Replay

HTTP clients may retry `POST /payments` or `POST /orders` after network timeouts. To behave safely, APIs can support a caller-supplied **`Idempotency-Key`** per contract.

### 16.1. Server workflow

1. Authenticate client and determine tenant/consumer scope.
2. Validate key: length/charset/entropy and scope; never treat keys as credentials.
3. Canonicalize comparable payload fields; compute a protected fingerprint.
4. Atomically claim by `tenant + operation + key`.
5. If **new**, process and store the **response/receipt** matching the committed outcome.
6. If **completed duplicate + same fingerprint**, replay prior response or expose resource status per contract.
7. If **same key + different fingerprint**, return a conflict error without executing another command.
8. If **in progress**, apply wait/`202`/`409`/retry-later policy.
9. If **unknown outcome**, reconcile; never blindly create a new payment.

### 16.2. Sample state table

| Key state | Payload | Suggested response | Meaning |
|---|---|---|---|
| Absent | Valid | Execute workflow | New claim |
| Completed | Same fingerprint | Prior status/body or resource ref | Do not repeat side effects |
| Completed | Different fingerprint | Conflict, usually `409` | Never reuse key for another command |
| In progress | Same fingerprint | `202`/`409`/retry-later per contract | Do not run concurrently |
| Unknown | Same fingerprint | Pending status + reconciliation | Do not assume it failed |

No single HTTP status code is mandatory for all APIs; what matters is a **published, consistent** contract. When stored responses contain PII/secrets, enforce ACLs, encryption, and retention on the response store.

## 17. HTTP Outbound Gateway: Where Does the Real Receiver Live?

When Spring Integration calls a **remote HTTP API**, the actual idempotent receiver often lives at the **remote service**. The client must preserve **the same remote idempotency key** across attempts of the same command.

~~~text
Spring Integration Receiver (local) -- OUTBOUND_ATTEMPT #1 --> Remote API
                                              |
                                              +-- timeout, result UNKNOWN
                 retry with SAME remote key --> Remote API
                                              |
                                              +-- returns previous result safely
~~~

If the remote service lacks idempotency keys, consider **readback/status APIs, local outboxes, reconciliation, target-side business dedup, or business compensation**. A local interceptor cannot guarantee an external API ran only once when a timeout occurs after remote commit.

### 17.1. Do not confuse HTTP GET with POST

HTTP methods have protocol-defined semantics; GET/PUT are intended to be idempotent at the resource level, whereas resource-creating POSTs usually need idempotency contracts on retry. **Never assume every GET/PUT endpoint is side-effect-free** or that every POST is unsafe; inspect the actual API contract and implementation.

## 18. JMS: Redelivery and Transactional Receive

In JMS, consumers may re-receive messages due to rollbacks, process crashes, or incomplete ACKs. `JMSRedelivered`, `JMSMessageID`, and `JMSCorrelationID` aid observability yet have limits:

- `JMSRedelivered` is a transport hint, not a final idempotency verdict.
- `JMSMessageID` identifies a broker message, unstable if a producer republishes the same logical event as a new message.
- `JMSCorrelationID` serves request/reply or app mapping, not necessarily unique event identity.
- Handlers still need an appropriate **business idempotency key** if the same command can arrive in distinct JMS messages.

### 18.1. Receive and commit model

1. Consumer receives message, parses, and validates event identity.
2. Idempotent receiver checks the key via store/DB.
3. If marker and business mutation share the **same DB transaction**, commit or roll back cleanly at that boundary.
4. ACK JMS per session/transaction configuration **after required state is durable**.
5. If the broker redelivers due to ACK failure, the committed key causes the receiver to skip side effects and complete ACK safely.

**Warning:** A JMS transaction and a database transaction are not automatically one unified transaction. For stricter coordination, design explicit transactions/outboxes/idempotency; never assume `@Transactional` on a Java service automatically wraps JMS ACK.

## 19. AMQP/RabbitMQ: ACK, NACK, and Poison Messages

AMQP consumers can re-receive messages via NACK/requeue, dropped connections, or consumer restarts. Receivers must:

- Separate **delivery attempt** from **logical event**.
- Derive keys from validated producer contracts rather than delivery tags alone.
- Commit side effects/dedup state before ACKing per designed semantics.
- When seeing a **completed duplicate**, ACK safely without incrementing business completion counts.
- For transient errors, use bounded retry/backoff and DLQs.
- For poison messages, prevent infinite requeue loops.
- For external API timeouts, keep `UNKNOWN` and reconcile before replaying.

### 19.1. Publisher confirm is not consumer completion

An AMQP producer may receive a publisher confirm before any consumer has processed the message. Never use a `publisher_confirmed` log to mark an event as processed by the business receiver. Outbound targets also need idempotency if the broker delivers multiple times.

## 20. Kafka: Offsets, Event IDs, and Idempotent Receivers

Kafka is commonly consumed under models that **redeliver records** on uncommitted offsets, rebalances, or retries. Receivers can choose scope:

1. **Per physical record:** deduplicate by `topic + partition + offset`.
2. **Per logical event:** deduplicate by `producer/event ID + operation/tenant`, even if the producer published the same event to two offsets.
3. **Per business command:** deduplicate by business command ID, even across multiple topics/bridges.

Choose scope by requirement. For payments or balance adjustments, **business-level keys** are usually far more valuable than record offsets.

### 20.1. Reprocessing scenarios

| Scenario | Offset-based key | Business-event-based key |
|---|---|---|
| Same Kafka record redelivered | Detected | Detected |
| Producer republishes same event at new offset | **Not** detected | Detected if event ID is stable |
| Two valid business events with identical payloads | Treated distinct if offsets differ | Treated distinct if event IDs differ |
| Replay from retry topic | Offset differs | Detectable via logical event key |
| Reprocess intentionally as a new command | New offset | Needs new operation/event version per policy |

### 20.2. Committing offsets after side effects

If a handler commits a DB transaction and crashes before committing the Kafka offset, the record may be redelivered. A DB unique marker prevents re-applying the side effect; the consumer can then safely commit the offset per container config.

### 20.3. Kafka transactions do not cover all external effects

Kafka producer idempotence/transactions provide guarantees scoped inside Kafka. A handler updating an **external database or calling HTTP** crosses a separate transaction boundary. Never claim end-to-end exactly-once without handling cross-system side effects, retries, and failure modes.

## 21. JDBC Inbound Poller: One Row Can Be Selected Multiple Times

A database polling flow often queries `PENDING` rows, emits messages, processes them, and marks `PROCESSED`. If the process dies after calling HTTP yet before updating the status, the next poll selects the same row again.

### 21.1. Non-equivalent milestones

| Milestone | Meaning | Is it finished? |
|---|---|---|
| `ROW_SELECTED` | Poller found the row | Not yet |
| `MESSAGE_EMITTED` | JDBC adapter created Spring Message | Not yet |
| `CLAIMED` | A worker holds processing rights | Not yet |
| `BUSINESS_COMMITTED` | DB mutation committed | Yes, **for local DB effects** |
| `OUTBOUND_SENT` | Outbound attempt made | Uncertain whether remote committed |
| `OUTBOUND_CONFIRMED` | Remote confirmed per contract | Yes within confirmed scope |
| `SOURCE_MARKED_PROCESSED` | Source row/watermark updated | Checkpoint progress only |

### 21.2. Design choices

- **Single database:** update business state, marker, and source row in the same transaction when appropriate.
- **Separate source and business DBs:** no default atomic transaction; use consumer inbox/dedup, outbox, and reconciliation.
- **DB poll → HTTP API:** use stable remote idempotency keys and readbacks after timeouts.
- **Batch queries:** never use `poll timestamp` as the key for every row in a batch.
- **Concurrent pollers:** require row claims/leases, locking strategies, immutable event IDs, and preventing workers from reading the same row and making duplicate remote calls.

### 21.3. Watermarks do not replace idempotency

Watermarks like `last_processed_id` or `updated_at` tell the poller where to resume reading. Yet transaction rollbacks, source reordering, colliding timestamps, or late-arriving events can cause watermarks to skip or re-select rows. **Idempotency keys and receiver markers** guard against duplicates; watermarks are just part of polling mechanics.

## 22. Splitter, Aggregator, and Batch Replay

When a splitter turns one batch into many messages, using **only the batch ID** as the key on item handlers wrongly blocks the second, third, and subsequent valid items. Conversely, using only `sequenceNumber` without batch scope collides across batches.

### 22.1. Rules for child keys

~~~text
parentKey = source + ":" + batchId
itemKey   = source + ":" + batchId + ":" + stableItemId
operation = "VALIDATE_AND_APPLY"

idempotencyKey = tenantRef + ":" + operation + ":" + itemKey
~~~

`stableItemId` must be defined by the source, or use positional index **only when batches are strictly immutable**. If batch ordering/membership can shift between downloads, sequence indices may stop identifying the same logical item.

### 22.2. Aggregator and partial failures

Some items may have processed before the aggregator timed out waiting for the rest. When the batch replays:

1. Already-committed items → skip item-level side effects.
2. Uncommitted items → allowed to process.
3. The aggregator must honor **completion/expiry semantics** and avoid mis-merging groups.
4. Aggregated output must carry a **group/version key** to avoid duplicate emissions when regenerated.

**Never** assume an aggregate result's history/header proves every item succeeded. Maintain an item-level completion ledger or per-contract event statuses.

### 22.3. Publish-subscribe

If one message travels over `PublishSubscribeChannel` to three subscribers, each branch produces a distinct side effect. Key by **business event + subscriber/operation**, for example:

~~~text
tenant:t1:event:e100:op:update-ledger
tenant:t1:event:e100:op:send-email
tenant:t1:event:e100:op:notify-warehouse
~~~

Using a global `event:e100` lets the first branch mark it completed and falsely cause remaining branches to skip as duplicates. **Key scope must match the specific side effect being protected**.

## 23. Retries and Backoff: Safe Duplicates Do Not Mean Infinite Retries

Retries occur on transient network/broker/database faults. Idempotency makes retries safer, yet does not eliminate the need for **bounded retries, exponential backoff, jitter, circuit breakers, or DLQs**.

### 23.1. Error classification

| Error type | Example | Handling direction |
|---|---|---|
| **Transient** | Rate limits, 503, network reset before request left | Retry with backoff/budget |
| **Permanent** | Invalid schema, genuine missing permissions | Reject/DLQ; never infinitely retry unchanged |
| **Unknown outcome** | Timeout after remote may have committed | Reconcile/readback; preserve idempotency key |
| **In-progress conflict** | Another worker holds claim on same key | Wait/retry later; avoid parallel side effects |
| **Same key different payload** | Request key wrongly reused | Conflict; investigate |
| **Store unavailable** | Cannot check dedup state | Fail-closed or defer per risk; never bypass blindly |

### 23.2. Danger zone: retries from lost ACKs

A handler completes its DB effect, yet broker ACK/offset commit fails. On redelivery, **returning “duplicate completed” is not a processing failure**. Allow transport ACKs/cursors to advance; otherwise the message loops forever even though the marker exists.

### 23.3. Error channels and duplicate state

Spring Integration error paths depend on endpoints, transactions, and pollers. When a handler throws:

- Check whether markers are written **before or after** the handler.
- If the marker sits in a rolled-back transaction, retries can reclaim cleanly.
- If a selector/store marks independently before the handler, the marker may linger despite failed effects; design recovery.
- Never set `COMPLETED` merely because an exception routed to `errorChannel`.
- In `ErrorMessage`, log safe correlation and reason codes without printing raw failed payloads.

## 24. DLQ Replay and Intentional Reprocessing

A DLQ message may be reprocessed after fixing a code/schema bug. Replay time may far exceed dedup cache TTLs.

### 24.1. Two cases to distinguish

**Case A — Replay to ensure the same operation finishes:** keep the exact business idempotency key. If already completed, skip; if not, process per policy.

**Case B — A new business operation derived from old data:** intentionally mint a **new operation/version/event ID**, rather than “deleting dedup markers” to force re-execution.

For example, recomputing this month's report can be a new command `RECOMPUTE_REPORT:v2`, whereas replaying `PAY_INVOICE:event-77` must never create a second payment.

### 24.2. Safe replay procedure

1. Verify source, event identity, prior status, and DLQ reason.
2. Inspect `COMPLETED/FAILED/UNKNOWN` markers and actual target-side effects.
3. Decide between **resuming the same operation** vs. issuing a **new compensating operation**.
4. Keep the source event ID and attach a new `replay_ref`/`attempt_ref` for observability.
5. Never bypass idempotency to “push it through” without understanding current state.
6. Require owner/approval and batch limits for replays affecting finances or sensitive data.
7. Monitor completed, skipped, conflict, failure, and reconciliation counts.

### 24.3. Never delete markers just to retry

Deleting `COMPLETED` markers erases proof that an event already ran. When business needs to correct an outcome, emit a dedicated **compensation/correction event** with its own ID and audit trail instead of blindly re-executing the original command.

## 25. TTL, Retention, and Garbage Collection of Dedup Stores

### 25.1. Minimum TTL depends on the whole system

Factors:

- Client HTTP retry windows and `Idempotency-Key` lifetimes.
- Broker retention/redelivery/DLQ replay horizons.
- Potential for SFTP files to be re-uploaded days later.
- Database polling/reconciliation and batch schedules.
- Compliance, audits, and the period over which business transactions require duplicate protection.
- Key volume, storage cost, privacy, and data-deletion rules.

No single TTL fits every domain. For some operations, keep **long-lived business unique constraints** and purge only transient attempts/leases.

### 25.2. Separating stored info by lifecycle

| Data | Purpose | Sample retention |
|---|---|---|
| Completed business key | Protects prior side effects on replay | Per business replay horizon |
| In-progress claim | Prevents concurrent execution | Short lease with owner/fencing |
| Attempt logs | Diagnosing retries/latency | Per logging policy |
| Outbox intent | Ensures downstream delivery | Until confirmed + retention window |
| Audit events | Accountable change trail | Per applicable policy/law |
| Reconciliation evidence | Resolves unknown outcomes | Until investigation/obligations close |

**Never store raw payloads/PII in dedup keys or logs** just to keep history longer. Use opaque references and ACL-protected stores.

### 25.3. Cleanup must be safe under concurrent processing

If TTL deletes `IN_PROGRESS` while an old worker is still running, a new worker can claim the same key. Use conditional updates/versions/fencing or target-side uniqueness. Never purge every record “older than 5 minutes” without checking state.

## 26. Multiple JVMs, Multiple Pods: Stores Must Be Shared and Consistent

~~~mermaid
flowchart TD
    SRC[Shared Broker / Source] --> A[Receiver Pod A]
    SRC --> B[Receiver Pod B]
    SRC --> C[Receiver Pod C]
    A --> S[(Shared Dedup Store)]
    B --> S
    C --> S
    S --> DB[(Business Database)]
    A --> OUT[Outbound Side Effect]
    B --> OUT
    C --> OUT
~~~

### 26.1. Common cluster bugs

1. Using per-pod `SimpleMetadataStore` → both A and B treat messages as new.
2. Redis key TTL expires too early → same event claimed twice.
3. Cross-region failover before metadata replication catches up → duplicates processed.
4. Network partition → client unsure whether claim write succeeded.
5. Old worker retains stale work past lease expiry → duplicate side effects.
6. Rolling deployment changes key format → old records stop matching.
7. Two source adapters share a namespace → cross-tenant key collisions.
8. Consumer crashes before broker ACK → redelivery lands on another pod.

### 26.2. Safeguards

- A **shared durable store** with proper atomic claims/unique keys.
- Stable **key namespaces and schema versions**, with migration plans for changes.
- **Local DB transactions** with unique constraints for in-DB side effects.
- **Remote idempotency/reconciliation** for external side effects.
- Recovery paths for `UNKNOWN/IN_PROGRESS` instead of ignoring or blindly retrying.
- Monitoring collisions, store latency, cleanup, capacity, and error rates.

## 27. Message Ordering, Versions, and Handling Late Events

Idempotency does not solve **out-of-order delivery**. Two distinct events `STATUS_CHANGED:version=7` and `STATUS_CHANGED:version=8` each have their own key; processing version 8 then version 7 can revert the record to an older state even though each event ran only once.

### 27.1. Combining idempotency with a version guard

~~~sql
-- Illustrative guard: update only if incoming event version is newer.
UPDATE order_projection
   SET status = :new_status,
       source_version = :incoming_version
 WHERE order_id = :order_id
   AND source_version < :incoming_version;
~~~

**This is pseudo-SQL with named parameters**, not raw JDBC syntax. When `UPDATE` returns 0 rows, distinguish **stale events, duplicate versions, missing orders, or conflicts** per business rules—never label every case “duplicate completed.”

### 27.2. When sequential processing is needed

With Kafka, key partitioning preserves order within a partition, yet retry topics, concurrency, and separate processes can still alter execution order. With JMS/AMQP/file batches, enforce explicit ordering/sequence contracts when required by business logic. **Idempotent receiver + ordering/versioning** solve two separate problems.

## 28. Idempotent Receiver vs. Related Patterns

| Pattern/mechanism | Core question | Relationship to Idempotent Receiver |
|---|---|---|
| **Idempotent Receiver** | Should this logical operation run again? | Primary topic |
| **Idempotent Producer** | Do producer publish retries duplicate records? | Cuts duplicates at source; doesn't replace receiver |
| **HTTP Idempotency-Key** | Is repeating the same command safe at a remote API? | Receiver on the HTTP service side |
| **Message Filter** | Is the message valid/right type? | Can precede dedup to validate identity |
| **Message Store/Metadata Store** | Where is recognition state stored? | One implementation building block |
| **Transactional Inbox** | How to durably record inbound receipt and domain effect? | Strengthens atomicity |
| **Transactional Outbox** | How not to lose outbound intent after DB commit? | Complementary; targets still need idempotency |
| **Retry/DLQ** | What happens when processing fails? | Creates the repeat deliveries requiring this pattern |
| **Resequencer** | Did messages arrive out of order? | Distinct from deduplication |
| **Aggregator** | When have enough messages arrived for a result? | Needs per-item and per-result idempotency |
| **Compensating Transaction/Saga** | What if distributed side effects already ran? | Used when atomic rollback isn't possible |
| **Exactly-once semantics** | Within what scope does the guarantee hold? | Not automatically achieved via one interceptor |

## 29. Observability: Measuring Duplicates Without Miscounting Success

### 29.1. Suggested event taxonomy

~~~text
INGRESS_ACCEPTED
IDEMPOTENCY_KEY_VALIDATED
CLAIM_ATTEMPTED
CLAIM_ACQUIRED
DUPLICATE_COMPLETED_SKIPPED
IN_PROGRESS_CONFLICT
PAYLOAD_KEY_CONFLICT
BUSINESS_EFFECT_COMMITTED
OUTBOUND_INTENT_CREATED
OUTBOUND_ATTEMPTED
REMOTE_OUTCOME_UNKNOWN
REMOTE_CONFIRMED
RECONCILIATION_COMPLETED
REPLAY_STARTED
TERMINAL_FAILURE
~~~

Never log raw payloads, secrets, or full business IDs. Log **opaque correlation references**, operation, key scope category, attempt index, bounded reason codes, and outcomes.

### 29.2. Useful metrics

| Logical metric | Meaning | What NOT to infer |
|---|---|---|
| Inbound deliveries | Messages delivered by source | Not unique business events |
| Unique keys claimed | New logical keys accepted | Not guaranteed completed |
| Completed duplicate skips | Repeat deliveries safely skipped | Not a business error |
| In-progress conflicts | Concurrent workers racing on same key | Does not prove duplicate side effect |
| Payload-key conflicts | Same key, different operation payload | Possible client bug or attack |
| Business effects committed | Durable domain outcomes | Scoped to specific DB/target |
| Outbound attempts | Calls to target system | Includes retries/redeliveries |
| Remote confirmed | Transport/remote confirmations | Not always business completion |
| Unknown outcomes | Potentially executed, unverified | Never count as definitely failed |
| Dedup store latency/errors | Health of atomic primitive | Can create backlogs/incompletes |
| Key retention expirations | Cleanup rate | Watch risk of replays outside TTL |

**Never use idempotency keys, event IDs, dynamic tenant IDs, or filenames as metric tags.** Keep them in access-controlled structured logs if needed, while metrics use bounded `flow`, `source_type`, `operation`, and `outcome`.

### 29.3. SLIs centered on unique events

For example: 100 logical events, 120 deliveries, 110 processing attempts, 97 completed events, 3 pending reconciliation. **Logical-event success rate** is not 110/120. Define eligible events, completion checkpoints, and treatment of unknown/pending items to calculate accurate SLIs.

## 30. Security and Risks of Idempotency Key Abuse

### 30.1. Key poisoning and cross-tenant collisions

An unauthenticated or malicious caller might submit someone else's key to trick the server into thinking that person's request already succeeded. Therefore:

- Verify authentication and tenant/actor scope **before looking up keys**.
- Namespace keys by operation and verified principal/tenant context.
- On same key with different payload, return a conflict; never replay sensitive results from another request.
- Do not leak the existence of another tenant's resources/responses through status codes.
- Rate-limit and cap keys per caller to prevent memory/store exhaustion.

### 30.2. Avoid storing excessive data in metadata stores

Dedup keys should be minimal references, free of passwords, OAuth tokens, card numbers, emails, or sensitive full file paths. If storing request fingerprints, use reviewed canonicalization and hashing inside ACL-protected stores; **plain hashes of low-entropy PII are not automatically anonymous**.

### 30.3. Access control and auditing

Stores and response caches may contain business-sensitive data. Enforce encryption, access controls, credential rotation, retention, and operation audits. Never allow operators to arbitrarily delete completed keys as a “quick fix”; doing so can cause duplicate payouts or resource provisioning.

## 31. Mandatory Test Scenarios

### 31.1. Test table

| Case | Input/condition | Expected |
|---|---|---|
| **First delivery** | New key, valid payload | One business effect, marker completed |
| **Identical redelivery** | Same key, payload | Effect does not run twice |
| **Concurrent same key** | Two consumers simultaneously | Only one claim/effect commits |
| **Different keys** | Two valid events with identical content | Both processed if business permits |
| **Same key different payload** | Key wrongly reused | Conflict; no new side effect |
| **Handler fails before commit** | Exception inside DB transaction | Marker/effect roll back; retry succeeds |
| **Crash after DB commit before ACK** | Broker redelivers | Skips effect, ACKs safely |
| **Crash after outbox send before status** | Dispatcher retries | Remote idempotency/reconciliation prevents duplicates |
| **Store unavailable** | DB/Redis unreachable | Does not bypass dedup against policy |
| **Stale IN_PROGRESS** | Worker died or lease expired | Verified recovery avoiding concurrent duplicates |
| **TTL expired replay** | Old event returns | Clear policy; no surprise side effects |
| **Out-of-order versions** | Version 8 before 7 | Version guard blocks state rollback |
| **Batch replay** | 100 items, 90 completed | Only the 10 incomplete items execute |
| **DLQ reprocess** | Replay same command | Preserves key or creates intentional correction event |
| **Multi-pod** | 3 replicas sharing broker | Shared store/unique constraint prevents double effects |
| **Broker timeout** | Outcome unknown | Reconciles instead of marking definitely failed |
| **Restart** | JVM/Pod restart | Dedup state persists per retention |

### 31.2. Unit tests vs. integration tests?

**Unit tests** cover key canonicalization, operation scoping, and conflict rules. However, **atomic uniqueness, JDBC transaction rollbacks, broker ACKs/offsets, multi-process races, and restarts** require integration/failure tests against representative infrastructure. A `ConcurrentHashMap` test inside one JVM never proves cluster safety.

### 31.3. Testing apply and marker ordering

Specifically test **throwing an exception between marker insertion and business update**. With the PostgreSQL design in section 11, if `@Transactional` works properly, the transaction rolls back so a retry can re-insert. If markers are written by an out-of-transaction metadata store, behavior differs; tests must expose this.

## 32. JUnit Test Example for Key Canonicalization

To keep keys stable and separate operations, you can define a simple helper:

~~~java
import java.util.Objects;
import java.util.regex.Pattern;

public final class EventKeys {
    private static final Pattern PART =
            Pattern.compile("[A-Za-z0-9_-]{1,120}");

    private EventKeys() {}

    public static String key(String tenantRef,
                             String operation,
                             String eventId) {
        validate(tenantRef);
        validate(operation);
        validate(eventId);
        return tenantRef + ":" + operation + ":" + eventId;
    }

    private static void validate(String value) {
        Objects.requireNonNull(value, "key segment");
        if (!PART.matcher(value).matches()) {
            throw new IllegalArgumentException("INVALID_EVENT_KEY");
        }
    }
}
~~~

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class EventKeysTest {
    @Test
    void sameEventUsesStableKey() {
        String first = EventKeys.key("tenantA", "CONFIRM", "ev-100");
        String replay = EventKeys.key("tenantA", "CONFIRM", "ev-100");
        assertEquals(first, replay);
    }

    @Test
    void operationsCannotCollide() {
        assertNotEquals(
                EventKeys.key("tenantA", "CONFIRM", "ev-100"),
                EventKeys.key("tenantA", "REFUND", "ev-100"));
    }

    @Test
    void unsafeUserInputIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> EventKeys.key("tenantA", "CONFIRM",
                        "ev-100\nFAKE-LOG"));
    }
}
~~~

**Example limits:** this tests **key formatting** without verifying source trust, business uniqueness, payload fingerprints, or DB atomicity. `tenantRef` must also be verified against the real actor/session rather than relying on regex alone.

## 33. Testing Transactional Receiver Behavior

An integration test should run against a real database or PostgreSQL-compatible environment with the unique constraint from section 11.

### 33.1. Basic scenario

~~~text
Given:
  inventory_projection(tenantA, sku01, quantity=100)
  processed_event does not yet contain eventId=ev-77

When:
  receiver.applyOnce(tenantA, ev-77, sku01, delta=-2)
  receiver.applyOnce(tenantA, ev-77, sku01, delta=-2)

Then:
  first result = APPLIED
  second result = ALREADY_APPLIED
  inventory quantity = 98
  processed_event has exactly 1 row for (tenantA, INVENTORY_ADJUST, ev-77)
~~~

### 33.2. Failure scenario

~~~text
Given:
  a new event with a nonexistent SKU

When:
  receiver.applyOnce(...) throws IllegalStateException

Then:
  transaction rolls back
  processed_event has NO completed marker for that event

When:
  create valid SKU and retry event

Then:
  receiver applies successfully exactly once
~~~

### 33.3. Race condition test

Have two workers invoke `applyOnce` concurrently with the same key using a barrier to force contention. Verify quantity changes only once, neither request creates duplicate records, and store transaction behavior is sound. Avoid `Thread.sleep` as concurrency proof since tests may fail to trigger actual contention.

## 34. Runbook IDEMP-01 — Sudden Spike in Duplicates

**Trigger:** `duplicate_skips`, broker redeliveries, or outbound attempts spike while business completions do not rise proportionally.

1. Identify flow, source, operation, timeframe, and **logical key scope**.
2. Separate **duplicate deliveries** from **two valid events sharing similar payloads**.
3. Check transport telemetry: Kafka lag/rebalances/offsets, JMS rollbacks, AMQP NACK/requeues, HTTP retries, SFTP repolls.
4. Inspect recent changes in ACK modes, transactions, retry policies, metadata stores, and key generators.
5. Check dedup store latency/errors/capacity, TTLs, and stuck `IN_PROGRESS` states.
6. Compare **unique business completions** rather than handler invocation counts.
7. For external APIs, inspect timeouts and `UNKNOWN_OUTCOME` before replaying.
8. Across multiple nodes, verify all instances share **the same store/key namespace/schema version**.
9. Fix root causes of retries/rebalances/poison messages per adapter runbooks.
10. Preserve evidence, strengthen test coverage, and monitor return to baseline.

### 34.1. What NOT to do

- Never bulk-delete completed keys to “unclog the queue.”
- Never disable dedup when stores slow down for financial or critical side-effect commands.
- Never ACK an event as success with an unknown business outcome.
- Never infinitely increase retries/concurrency when targets are rate-limiting.
- Never log raw PII-containing payloads/keys to compare duplicates.

## 35. Runbook IDEMP-02 — Claim Exists Yet Business Work Is Incomplete

**Trigger:** messages are skipped because keys are `IN_PROGRESS`/`COMPLETED`, yet targets lack expected results.

1. Read key status, owner/lease/version, timestamps, store consistency, and actual business records.
2. Distinguish **marker committed while effect never ran** from **effect ran while confirmation/logs were lost**.
3. Check transaction boundaries: did marker and business update share the same DB transaction?
4. For remote APIs, use status/readback by idempotency key or business reference before retrying.
5. If `IN_PROGRESS` is stale, check whether the old worker is still alive; take over only per lease/fencing policy.
6. If `COMPLETED` was written prematurely, open a design incident and execute approved remediation; never delete markers blindly.
7. Update states (`UNKNOWN/RETRYABLE/COMPLETED`) based on evidence and preserve audits.
8. Add crash tests at the exact failing checkpoint to prevent recurrence.

## 36. Twelve Practical Scenarios

### Scenario A — Kafka redelivery after DB commit

Consumer finishes DB write, crashes before offset commit. Broker redelivers the record with the same event ID.

**Handling:** use unique keys and business updates inside the DB transaction; retry sees completed, skips writing again, and safely ACKs/commits offsets per container settings. Do not treat two handler log lines as two business events.

### Scenario B — Producer republishes same event at new Kafka offset

Producer times out and publishes a copy with the same event ID to a different offset.

**Handling:** deduplicate by **stable event ID** rather than solely `topic-partition-offset` when scope requires one business completion. Cross-check producer retries, idempotent producer settings, and consumer metrics.

### Scenario C — JMS consumer rolls back after sending email

Handler sends an external email, then DB update throws and JMS rolls back.

**Handling:** next delivery may resend the email. Split email into an outbox command with a stable ID; use sender/reconciliation and email-provider idempotency if supported, or accept/monitor duplicates per contract.

### Scenario D — AMQP poison message looping endlessly

RabbitMQ requeues a schema-invalid message; consumer keeps rejecting.

**Handling:** classify permanent errors, enforce bounded retries and DLQs; never “just add an idempotency marker” to mask invalid payloads. Mark completed only upon business completion or defined terminal rejection.

### Scenario E — SFTP same filename, new content

Partner re-uploads `report.csv` for a new day; filename-based accept-once filter/selector treats it as duplicate.

**Handling:** agree on file generation IDs/manifests or trusted versions; records need individual event IDs. Never rely on filenames alone and never log raw remote paths.

### Scenario F — JDBC re-polls row after remote timeout

Poller reads `PENDING` row, calls HTTP API and times out; row not yet marked processed.

**Handling:** external effect state is `UNKNOWN`; query remote/idempotency status before calling again; use durable outboxes/markers and retry budgets.

### Scenario G — HTTP duplicate Idempotency-Key with changed amount

Two POST requests share the same key; the second has a different amount.

**Handling:** scope keys by actor/tenant/operation and compare canonicalized fingerprints. Return conflict; never replay another request's sensitive response or create a new charge.

### Scenario H — Two pods process the same event

Two replicas use local `SimpleMetadataStore` and both receive the event during failover.

**Handling:** use a shared durable/atomic store or DB unique constraints; test concurrency and restarts. Never fix with per-JVM `synchronized`.

### Scenario I — Metadata TTL shorter than DLQ replay

Completed key expires after 1 hour; DLQ is replayed after 2 days.

**Handling:** align retention with replay horizons and business obligations, keep markers/receipts longer, or check business state before replay. Never blindly rerun financial commands.

### Scenario J — Splitter blocks 99/100 items

Every item uses the same `batchId` as its idempotency key.

**Handling:** use `batch + stable item ID + operation` keys; track group completion independently. Never treat distinct items as duplicates for sharing a batch.

### Scenario K — Events arrive out of order

Version 8 processes before version 7; both keys are new.

**Handling:** add version/order guards/expected-state CAS; idempotency alone never prevents stale events from rolling back business state.

### Scenario L — An outbound call committed yet ACK was lost

Remote payment succeeded; receiver lost the response and prepares to retry.

**Handling:** keep the same remote idempotency key, read back status, and record `UNKNOWN_OUTCOME` until verified. If remote lacks idempotency, apply business-approved reconciliation/compensation.

## 37. Idempotent Receiver Implementation Checklist

### 37.1. Key design

- [ ] Identified logical operations and side effects requiring protection?
- [ ] Key remains stable across redeliveries/retries/restarts/process boundaries?
- [ ] Key scoped by tenant/source/operation to avoid collisions?
- [ ] Policy defined for same key with different payload?
- [ ] Raw filenames/emails/tokens/PII excluded from keys/logs?
- [ ] Contract and trust validation defined for client-supplied `Idempotency-Key`?

### 37.2. Storage and atomicity

- [ ] Store provides appropriate **atomic claims/unique constraints**?
- [ ] State is shared and durable across multiple JVMs/pods?
- [ ] For local DB effects, do markers and business updates share **one transaction**?
- [ ] Rollback tested between marker and effect?
- [ ] For external side effects, do remote idempotency/outbox/reconciliation exist?
- [ ] Stale `IN_PROGRESS` states have owners/leases/fencing/recovery?
- [ ] TTL/retention covers retry/DLQ/replay horizons?

### 37.3. Spring Integration and adapters

- [ ] Interceptor/selector attached **before** protected side effects?
- [ ] Duplicate flag/discard behavior verified for your framework version?
- [ ] File/SFTP accept-once is not mistaken for business completion?
- [ ] HTTP inbound duplicates have response replay/conflict policies?
- [ ] HTTP outbound retries reuse the same remote idempotency key?
- [ ] JMS/AMQP ACKs, rollbacks, and redeliveries sit on proper boundaries?
- [ ] Kafka offset commits, record IDs, and business event IDs are distinguished?
- [ ] JDBC poller watermarks and durable markers have clear strategies?
- [ ] Splitters/aggregators use per-item and per-result keys?
- [ ] DLQ replays preserve lineage and never accidentally bypass dedup?

### 37.4. Testing, monitoring, and operations

- [ ] Tests cover duplicates, concurrency, crashes, and timeouts after remote commit?
- [ ] Tests cover store unavailability, process restarts, and multiple replicas?
- [ ] Metrics distinguish attempts, duplicate skips, unique completions, and unknown outcomes?
- [ ] Logs use correlation/attempt refs free of secrets/PII?
- [ ] Metrics never attach keys/message IDs as tags?
- [ ] Runbooks exist for duplicate spikes and stuck claims?
- [ ] Completed markers are never deleted as a “fix” without approval/evidence?
- [ ] Business owners understand the exact guarantee scope and remaining limits?

## 38. Summary

The **Idempotent Receiver Pattern** enables Spring Integration flows to withstand **at-least-once delivery**, retries, redeliveries, and replays without executing single-occurrence side effects multiple times. Applying it properly requires distinguishing **logical events** from **transport deliveries**, choosing **scoped stable keys**, enforcing **atomic claims/unique constraints**, handling **NEW/IN_PROGRESS/COMPLETED/UNKNOWN** states, and placing **transactions/ACKs** on the right boundaries.

Across **File, SFTP, HTTP, JMS, AMQP, Kafka, and JDBC**, duplicate sources and completion confirmations vary. Spring Integration tools such as **`IdempotentReceiverInterceptor` and `MetadataStoreSelector`** handle endpoint-level duplicate detection; **business database unique constraints, Inbox/Outbox, target idempotency, and reconciliation** solve the harder problem of avoiding lost or repeated side effects during crashes and timeouts. Combining **concurrency/failure tests, unique-event metrics, safe structured logs, and runbooks** yields reliable integrations without falsely claiming that a single interceptor gives end-to-end exactly-once.
