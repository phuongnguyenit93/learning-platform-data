# Ensuring Idempotency Across Restarts in Spring Integration Adapters

> **Chapter:** Production  
> **Lesson:** Ensuring idempotency across restarts  
> **Module:** Spring Integration Adapters  
> **Scope:** Inbound/outbound adapters, gateways, pollers, and `MessageChannel` connecting File, SFTP, HTTP, JMS, AMQP, Kafka, and JDBC; focusing on message contracts, error management, durable state, and connection lifecycles.

## 1. Learning Objectives and Real-World Problem

By the end of this lesson, you will be able to:

1. Explain why **restarts** can cause lost messages, re-delivered old messages, and duplicate side effects even when retries are configured.
2. Identify the **durable boundary**, **ack/offset/checkpoint point**, **business commit**, and **ambiguous-outcome point** in any `IntegrationFlow`.
3. Choose **stable idempotency keys** across restarts, multiple replicas, replays, and changing message headers.
4. Implement **transactional inbox/processed-event ledger**, **transactional outbox**, unique constraints, and proper concurrent duplicate handling.
5. Understand the scope of `AcceptOnceFileListFilter`, persistent metadata stores, and `IdempotentReceiverInterceptor`, and why they do not provide business exactly-once by themselves.
6. Analyze restart/redelivery characteristics across **File, SFTP, HTTP, JMS, AMQP, Kafka, and JDBC**.
7. Design **claim/lease/fencing**, graceful shutdown, recovery scans, retention, reconciliation, and safe replays.
8. Build a test matrix that actively kills processes at failure windows; monitor duplicates, pending age, outbox lag, and unknown-outcome states.

**Cross-cutting scenario:** A Spring Boot application uses Spring Integration to receive order files over SFTP, create orders in a JDBC database, call a partner HTTP API, and publish Kafka events. A pod is killed right after writing to the database but before marking the file processed or committing the Kafka offset. When a new pod starts, the same data may be reprocessed. Without a ledger/idempotency, the system creates duplicate orders or double payments; if marked received too early, it risks **dropping** orders.

**Realistic commitment:** Across independent systems, designs typically achieve **at-least-once delivery + idempotent business effects** rather than claiming "end-to-end exactly-once" spanning files, databases, brokers, and HTTP. Examples in this lesson illustrate verifiable behavior; verify APIs and configs against **your exact Spring Integration/client version**.

## 2. Idempotency Is a Property of Business Effects

An operation `f` is idempotent if repeating the operation with the same logical meaning produces no additional impact beyond the intended state:

\[
f(f(s,x),x)=f(s,x)
\]

Where `s` is the business state and `x` is the **same logical request**. In distributed systems, define the scope clearly: one database record, one order, one notification sent, or an entire workflow?

| Example | Can It Be Idempotent? | Condition |
|---|---|---|
| `PUT` setting order status to `CONFIRMED` | Yes | Same ID/version; does not spawn a new notification each time |
| `INSERT` new order with unique business key | Can be | Duplicates are detected and handled safely |
| Crediting wallet by 100,000 VND per request | Not by default | Must attach a transaction/request ID to block double credit |
| Sending confirmation email | Not by default | Requires delivery ledger/dedupe by template + business event |
| Creating payment transaction via HTTP POST | Not by default | Partner supports idempotency key / status lookup |
| Uploading the same SFTP file | Not by default | Versioned naming, checksum/manifest, and remote state |
| Publishing the same Kafka event | Delivery may duplicate | Consumer must dedupe and handle duplicates properly |
| Replaying a file after restart | Not automatically safe | Business key + durable state + recovery protocol |

**Distinguish three layers of idempotency:**

- **Ingress deduplication:** avoids re-ingesting the same file/record per filter/metadata rules. Useful for cutting redundant work, but does not prove business commits succeeded.
- **Business idempotency:** guarantees the same business key produces at most one valid business effect, even if two workers run concurrently.
- **Egress idempotency:** avoids re-sending or duplicating effects on partners; requires a ledger and/or receiver-supported idempotency.

If a problem requires all three, **a single accept-once filter is not enough**.

## 3. Why Restarts Cause Duplicates and Data Loss

Restarts are not limited to planned stops/starts. They can come from:

- Deployments/rolling updates, scale-ins, liveness restarts;
- JVM crashes, OOMs, host reboots, power loss;
- Broker/client reconnects triggering JMS/AMQP redeliveries or Kafka rebalances;
- Schedulers/pollers restarting and seeing the same file/row;
- Non-persistent metadata stores or in-memory queues;
- HTTP callers timing out and resending while the backend keeps processing;
- Worker leases expiring so a new pod claims an item while the old pod is still running.

### 3.1. Minimum Failure Windows

| Window | What Already Happened | What Restart Can Cause | Primary Protection |
|---|---|---|---|
| **W0** | Source still holds message; app hasn't received it | Source redelivers normally | Source retention/checkpoint |
| **W1** | Polled/received; no durable state saved yet | In-memory item lost if source already acked | Ack after durable handoff or rollback/redelivery |
| **W2** | Metadata/filter marked accepted; business not committed | File/record skipped after restart | Inflight recovery + never treat metadata as success |
| **W3** | Business transaction open, uncommitted | Rollback or ambiguous result depending on storage/network | Transaction boundaries and actual-state checks |
| **W4** | Business DB committed; source ack/offset uncommitted | Source redelivers → duplicate risk | Unique business key + processed-event ledger |
| **W5** | Outbound HTTP/Kafka/file executed; local success uncommitted | Repeats effect on external system | Stable idempotency key + remote reconciliation |
| **W6** | Source acked; downstream not yet durable | Message can be permanently lost | Durable inbox/outbox before ack |
| **W7** | Fully committed/acked per contract | Manual restart/replay can still reprocess | Ledger retention + idempotent result |

**Two opposing failure modes:**

1. **Premature ack:** source considers the item DONE before the business result is durably persisted → message loss.
2. **Late ack:** business commits before the source receives ack → redelivery → duplicate processing risk.

In most integrations, designs prioritize **ack after durable commit** to prevent data loss, then use idempotency to handle duplicates from redelivery.

### 3.2. Concrete Crash Timeline

~~~text
T0    Consumer receives orderId=O-123 from Kafka
T1    Validates schema and business key
T2    INSERTs order O-123 + processed event in DB transaction
T3    DB COMMIT succeeds
T4    Pod receives SIGKILL / JVM crashes
T5    Kafka offset is uncommitted
T6    New consumer receives the same record again
T7    Unique key/ledger returns "ALREADY_PROCESSED"
T8    Consumer commits offset per container policy
~~~

If `T2` only inserts into the database without a unique constraint, the record can be created twice. If `T2` writes "processed" to a separate cache **before** `T3`, and then the DB rolls back, subsequent deliveries could be wrongly discarded.

## 4. Define the Invariants to Protect

Before writing code, define explicit **invariants**:

- **I1 – No lost obligations:** Once inbound is acked, either the business result **or** a durable processing obligation already exists.
- **I2 – No duplicate effects:** The same business identity + version produces no extra business effects beyond contract.
- **I3 – Never mask conflicts:** Same key with a different payload must not be silently dropped; detect and handle it.
- **I4 – Recoverable:** Mid-flight interrupted items have status, deadlines, owners, and a retry/re-claim path.
- **I5 – No blind resends on unknown outcome:** Egress timeouts do not prove the remote didn't execute.
- **I6 – Safe under concurrency:** Two workers racing on the same key never create two effects regardless of execution order.
- **I7 – Adequate retention:** Dedupe ledgers never expire before replay/late-arrival windows close.
- **I8 – Observable and auditable:** You can answer "how many times was this order received, which attempt committed, and who replayed it?".

### 4.1. Reliability Claims Must Be Scoped

| Claim | Acceptable When |
|---|---|
| "No lost records after restart" | Crash-tested at ingress/commit/ack; source or inbox preserves data |
| "Orders created at most once" | DB uniqueness + transactions proven under concurrent duplicates |
| "Kafka publish exactly-once" | Exact Kafka client/transaction scope stated without extrapolating to external HTTP/DB |
| "No duplicate emails sent" | Delivery ledger or idempotent target exists; tested send-succeeded-but-ACK-lost |
| "SFTP files never skipped" | Ready protocol + persistent ingest state + recovery scans exist |
| "Safe replays" | Keys/versions, side-effect reconciliation, and retention meet requirements |

**Never use Spring Integration's generated message ID for business guarantees** when each ingress/replay can mint a new `Message`.

## 5. Choosing Idempotency Keys for Restarts and Replays

### 5.1. Keys Must Be Stable and Scoped

Commonly needed components:

- `sourceSystem` or `producerId`: prevents collisions across partners;
- `tenantId`: separates multi-tenant data spaces;
- `eventId` generated by the producer **once per logical event**;
- `businessId` and `revision`: when contracts allow multiple valid versions;
- `operationType`: avoids ambiguity among `CREATE`, `UPDATE`, `CANCEL`;
- `target` or `sideEffectKind`: when tracking egress separately.

Examples:

~~~text
ingress-key = (sourceSystem, tenantId, eventId)
order-transition-key = (tenantId, orderId, revision, transitionType)
http-payment-key = (tenantId, paymentRequestId)
file-key = (partnerId, logicalFileId, fileVersion)
outbox-key = (businessEventId, targetSystem)
~~~

**Values you should NOT use alone by default:**

| Value | Why It Easily Breaks |
|---|---|
| Spring Integration `MessageHeaders.ID` | Can be newly generated on re-parse/resend |
| Kafka offset | Tied to partition/topic and reprocessing; not a cross-system business identity |
| HTTP correlation ID | Meant for tracing; may change per request/retry |
| Filename `orders.csv` | Can be reused across days or versions |
| Current timestamp | Changes across retries; suffers clock skew and collisions |
| Whole-payload raw hash | JSON field order/formatting/metadata can vary for the same business event |
| Username or email | Mutable and not guaranteed unique long-term |

### 5.2. Duplicate Key with Different Payload

If a producer reuses an `eventId` with a different payload, `ON CONFLICT DO NOTHING` can silently drop a valid update or hide corrupt data. Dedupe ledgers should store a **payload fingerprint/schemaVersion/business version** to distinguish:

- **Same key, same semantic payload:** `ALREADY_PROCESSED`, returning prior result.
- **Same key, different semantic payload:** `CONFLICT` / quarantine + alert; never overwrite silently.
- **Different key, later revision:** Version/ordering rules decide whether to process.
- **Different key, same business operation:** If business rules forbid repeating the action, add an action-level key beyond `eventId`.

Hashing detects conflicts rather than replacing business identifiers; canonicalize semantic payloads deliberately and pick a sound hash algorithm so harmless formatting differences aren't mistaken for business changes.

### 5.3. Key Retention Must Match Replay Windows

Do not set a 24-hour TTL thinking "one day is plenty" when Kafka retains 7 days, JMS DLQs may replay after 30 days, or an SFTP partner resends files weeks later.

Dedupe retention must consider:

- Maximum automatic redelivery/retry duration;
- How long messages can remain in DLQ/DLT/quarantine;
- Source replay/reprocessing and disaster recovery;
- Business SLAs, audit/legal retention, and PII minimization;
- Whether producers reuse keys across versions/epochs after a **contractually defined** horizon.

When ledgers cannot be kept forever, define archive/compaction strategies or check authoritative business state before replaying old data.

## 6. Idempotency Architecture for an `IntegrationFlow`

~~~mermaid
flowchart LR
    SRC["File / SFTP / HTTP / JMS / AMQP / Kafka / JDBC"] --> IN["Inbound adapter / gateway"]
    IN --> VAL["Validate schema + stable key"]
    VAL --> INBOX["Transactional inbox / dedupe ledger"]
    INBOX --> DECIDE{"Key state?"}
    DECIDE -->|"New"| BIZ["Business DB transaction"]
    DECIDE -->|"Processed"| DUP["Replay prior outcome / no-op"]
    DECIDE -->|"Conflict"| Q["Quarantine + alert"]
    BIZ --> OUTBOX["Outbox event / target command"]
    BIZ --> ACK["Source checkpoint / ack after durable outcome"]
    OUTBOX --> PUBLISH["Independent outbound worker"]
    PUBLISH --> TARGET["Kafka / HTTP / SFTP / JMS / AMQP"]
    TARGET --> RECEIPT["Receipt / reconcile / retry"]
    RECEIPT --> OUTBOX
    DUP --> ACK
    Q --> OPS["Owner + runbook"]
    INBOX --> OPS
~~~

Within one database transaction, business state and the processed-event marker can commit **together**. When systems don't share one database/transaction manager, the design must define durable handoff points and saga/queue recovery.

### 6.1. State Worth Persisting

| Table / Store | Key Data | Reason |
|---|---|---|
| `integration_inbox` | Stable key, source, `receivedAt`, `payloadRef`/hash, schema, status, lease/attempt | Recover ingress after mid-flight interruptions |
| `processed_events` | Business key, payload hash, committed outcome/ref, `completedAt` | Deduplicate across restarts |
| `orders` / domain state | Business ID, version, invariants, unique constraint | Protect actual business outcomes |
| `integration_outbox` | Event ID, target, payload/ref, status, `nextAttemptAt`, attempt, last error | Deliver egress after DB commit |
| `external_operations` | Remote operation ID, idempotency key, unknown/success/failure, receipt | Reconcile HTTP/SFTP and off-DB side effects |
| `audit/replay_log` | Operator, reason, source offset/file, before/after state | Investigation and compliance |

Not every application needs all six tables. What matters is that **every state transition has a clear owner and transaction boundary**.

### 6.2. State Machine of an Inbound Event

~~~mermaid
stateDiagram-v2
    [*] --> RECEIVED
    RECEIVED --> CLAIMED: lease / claim
    CLAIMED --> PROCESSED: business commit + dedupe marker
    CLAIMED --> RETRYABLE: transient failure / lease release
    CLAIMED --> QUARANTINED: permanent payload failure
    RETRYABLE --> CLAIMED: backoff + re-claim
    CLAIMED --> UNKNOWN: ambiguous external effect
    UNKNOWN --> PROCESSED: reconcile confirms success
    UNKNOWN --> RETRYABLE: verified not executed
    PROCESSED --> [*]: source ack/checkpoint
    QUARANTINED --> [*]: durable handling per policy
~~~

**Note:** `RECEIVED`, `CLAIMED`, and `PROCESSED` represent an application-level ledger, not built-in Spring Integration states. Never transition `UNKNOWN` back to `RETRYABLE` without proof that the side effect did not happen or an idempotency contract protecting retries.

## 7. Transaction Pattern: Committing Business Effect and Dedupe Marker Together

### 7.1. Wrong Pattern: Non-Atomic Check-Then-Act

~~~text
if not alreadyProcessed(key):
    chargeCustomer()
    markProcessed(key)
~~~

Two workers can both observe "not processed" and both execute. Furthermore, if `chargeCustomer()` succeeds and the process dies before `markProcessed()`, restarts will re-charge.

### 7.2. Better Pattern When Side Effects Live in One Database

Assuming the same DB transaction can write `processed_events`, update `orders`, and insert `outbox`:

~~~text
handle(message):
    validate(message)
    key = stableBusinessKey(message)
    hash = semanticPayloadFingerprint(message)

    begin database transaction
        newlyClaimed = insertDedupeKeyIfAbsent(key, hash)

        if not newlyClaimed:
            saved = readCommittedOutcome(key)
            if saved.hash != hash:
                rollback
                return CONFLICT
            commit
            return ALREADY_PROCESSED(saved.result)

        updateBusinessStateWithInvariantChecks(message)
        insertOutboxEventsWithStableIds(message)
        markDedupeCommitted(key, resultingBusinessVersion)
    commit

    return PROCESSED
~~~

**Key points:**

- `insertDedupeKeyIfAbsent`, business mutations, outbox inserts, and completion markers all execute **in one local transaction**.
- Enforce a unique constraint on the stable key. Verify transaction isolation and concurrent-insert behavior on your database.
- If the transaction rolls back, the dedupe insert rolls back too, leaving the message eligible for valid retry after restart.
- If the transaction commits before source ack completes, redelivery sees the committed result and produces no new side effects.
- If the same key arrives with a different payload, never return success as a valid duplicate.
- If an HTTP gateway needs to echo the prior response, store the result/reference in the outcome to reply consistently.

**Never place remote HTTP/SFTP calls inside this transaction assuming DB rollback undoes remote effects.** Off-DB actions require commands/outboxes plus remote idempotency/reconciliation.

### 7.3. PostgreSQL Example: Unique Key as Concurrency Guard

~~~sql
CREATE TABLE processed_events (
    source_system     VARCHAR(80)  NOT NULL,
    tenant_id         VARCHAR(80)  NOT NULL,
    event_id          VARCHAR(160) NOT NULL,
    payload_sha256    VARCHAR(64)  NOT NULL,
    business_ref      VARCHAR(160),
    completed_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (source_system, tenant_id, event_id)
);

CREATE TABLE orders (
    tenant_id         VARCHAR(80)  NOT NULL,
    order_id          VARCHAR(160) NOT NULL,
    revision          BIGINT       NOT NULL,
    state             VARCHAR(40)  NOT NULL,
    PRIMARY KEY (tenant_id, order_id)
);

CREATE TABLE integration_outbox (
    event_id          VARCHAR(160) PRIMARY KEY,
    target            VARCHAR(60)  NOT NULL,
    payload_json      JSONB        NOT NULL,
    status            VARCHAR(20)  NOT NULL,
    attempt_count     INTEGER      NOT NULL DEFAULT 0,
    next_attempt_at   TIMESTAMPTZ,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now()
);
~~~

This schema is a **PostgreSQL example**, not a drop-in production migration. Design business versions, event ID generation, indexes, retention, consistency, and privacy for your actual domain.

Statement inserting the key in the same transaction:

~~~sql
INSERT INTO processed_events
    (source_system, tenant_id, event_id, payload_sha256, business_ref)
VALUES
    (:source, :tenant, :eventId, :fingerprint, :businessRef)
ON CONFLICT (source_system, tenant_id, event_id) DO NOTHING;
~~~

Check the update count: if `0`, read the committed record and compare fingerprint/outcome. If `1`, perform the business update and insert into the outbox **before committing that transaction**. If a subsequent update fails, the entire transaction must roll back. Exact `ON CONFLICT` behavior, isolation levels, and concurrent visibility depend on the DB—test concurrent duplicates and transaction failure windows.

### 7.4. Never Commit `PROCESSED` in a Separate Transaction Before Business Writes

If the `PROCESSED` ledger commits first and the business update fails, restarts will discard an unprocessed message. If an early claim in a separate transaction is needed for long work, set status to `CLAIMED/PROCESSING` with lease/recovery—**never** final success.

## 8. Transactional Inbox and Outbox Solve Both Risk Directions

### 8.1. Inbox: Before Acking Ingress

Sources like HTTP webhooks or async callbacks may want an early success response while internal work takes longer. Before returning `202 Accepted`, ensure the request sits in a **durable inbox/queue** with its key, payload/ref, and processing owner.

~~~text
HTTP ingress
    -> validate + stable event ID
    -> INSERT inbox row (dedupe + durable)
    -> COMMIT
    -> return 202 + tracking ID
    -> background worker claims inbox row
    -> business transaction
    -> mark processed + enqueue outbound
~~~

If the same request arrives twice, the first transaction prevents creating two inbox jobs for one key. If the same key arrives with a different payload, return conflict or route for review per API contract.

### 8.2. Outbox: After Business Commit, Before Publishing

Writing to DB and calling Kafka/HTTP directly risks crashes between the two steps—either the remote effect never happens, or it happens without local knowledge.

~~~text
Transaction A:
    update order
    insert processed-key
    insert outbox command/event
COMMIT

Worker B:
    claim outbox
    publish to target
    if success/receipt established:
        mark delivery outcome
    else:
        bounded retry or UNKNOWN_OUTCOME
~~~

The outbox prevents **losing the publish obligation** between DB commit and outbound send. However, if the broker accepts the message and the worker dies before marking it sent, the event may be republished. Therefore **consumers still need idempotency**. Outbox does not automatically deliver exactly-once to every target.

### 8.3. Transaction Isolation and Outbox Concurrency

- Outbox workers use row claims/leases or dialect-appropriate locking.
- A slow worker's claim can be reclaimed by another worker; receivers still need idempotency.
- Record `SENT` only after contractual confirmation; record `UNKNOWN` on ambiguous responses.
- Keep outbox event IDs stable across attempts—never mint new IDs per retry.
- Enforce bounded retry/backoff and alert on oldest pending/failed items and capacity.
- If outbox payloads contain PII, apply encryption, access controls, and retention.

## 9. Spring Integration Mechanisms: Dedupe at the Right Layer

Spring Integration provides several ways to detect previously seen messages, each with distinct **goals and scopes**. Understand how they interact with transactions, crashes, and restarts.

### 9.1. Accept-Once Filters Are Not Business Ledgers

| Mechanism | Typical Purpose | What It Does Not Guarantee |
|---|---|---|
| `AcceptOnceFileListFilter` | Limits picking the same file repeatedly within filter scope | In-memory cache surviving process restarts |
| Persistent file accept-once filter | Uses `MetadataStore` to remember files across restarts | That the business handler committed successfully |
| `SftpPersistentAcceptOnceFileListFilter` | Persists remote file intake state via an appropriate store | That download/parse/DB/HTTP completed |
| `FileSystemPersistentAcceptOnceFileListFilter` | Persists local file state via metadata | That remote source files finished business processing |
| `MetadataStore` | Stores key/value state for integration components | Automatic business idempotency or DB ACID coupling |
| `IdempotentReceiverInterceptor` | Intercepts handlers and classifies duplicates via selector | Rollback of downstream side effects on handler failure |
| Domain unique constraint / processed ledger | Guards business effects inside a DB transaction | Automatic idempotency of external HTTP/SMTP/SFTP effects |

Class names, constructors, and APIs vary across Spring Integration versions. This lesson describes **design roles**; verify against your actual adapter and factory versions.

### 9.2. Metadata Stores Need Proper Durability and Sharing

An in-memory key-value store avoids duplicates within one JVM, yet restarts wipe its state. To survive restarts and multi-replica setups, use a **persistent `MetadataStore`** backed by DB, Redis, or another framework-supported durable store.

Verify:

- **Durability:** Do keys survive JVM/pod restarts?
- **Atomic claim/update:** When two replicas write the same key, is there an atomic `putIfAbsent` / compare-and-set operation?
- **Transaction coupling:** When does metadata commit, and does it share the business DB transaction?
- **Key prefix/namespace:** Could two inbound flows collide on keys and falsely filter files?
- **Expiry/cleanup:** Could metadata TTL eviction cause already-processed files to be re-polled?
- **Recovery:** When the filter accepts a file but the handler fails, how is it re-driven?
- **Cross-region/multi-process:** Does the store offer consistency strong enough against duplicate races?

**Critical mistake:** Merely swapping an in-memory metadata store for a persistent one stops re-polling after crashes—yet if files are marked accepted **before** business commits, they can be skipped **forever**. Add stage-appropriate recovery states and workflows.

### 9.3. `IdempotentReceiverInterceptor` Has Specific Semantics

`IdempotentReceiverInterceptor` uses a message selector to classify duplicates at the handler boundary; `MetadataStoreSelector` is one option backed by a key/value store. How duplicates are handled (header marking, discard/reject, or letting the handler inspect) depends on interceptor and flow configuration.

Mandatory checks:

1. Derive keys from **business identity**, not default `MessageHeaders.ID`.
2. If the selector marks "seen" before the handler runs and the handler fails, know how the marker is rolled back or reclaimed.
3. Never write a "processed" marker before business state commits if they do not share a transaction.
4. If duplicates still pass to the handler with a duplicate header, the handler must act safely.
5. If using a discard channel, ensure unprocessed business work isn't silently dropped.
6. Filters/interceptors act at the **ingress layer**, while domain unique constraints guard races at the final persistence boundary.
7. Verify behavior across exceptions, retry advice, async channels, and transaction boundaries.

### 9.4. `MessageChannel` and Durable Handoffs

- `DirectChannel`: handlers run synchronously on the sender thread; exceptions can propagate back to pollers/listeners, subject to adapter transaction/ack configs.
- `ExecutorChannel`: switches threads; upstream transaction contexts do not propagate to handlers; successful dispatch **does not mean** business processing completed.
- `QueueChannel`: in-memory queues do not survive restarts by default; use a persistent `MessageStore` or broker when durability is required.
- Messaging gateways: `sendTimeout` and `replyTimeout` apply only to specific stages; caller timeouts do not prove handlers were canceled.
- Error channels: `ErrorMessage` allows custom error flows; **log-and-swallow** can cause sources to treat failures as success under some setups.

**Review question:** If the process is killed **right after `.channel("workQueue")` returns** but before the handler runs, does the source still retain the message or was it already acked? If acked into an in-memory queue, fix the design.

## 10. File Inbound/Outbound: Restarts After Ingest and After Archiving

File adapters scan directories, filter files, and feed file references into `IntegrationFlow`. Unlike broker queues, filesystems offer no unified consumer acknowledgement for business workflows.

### 10.1. File-Ready Convention and Business State

A clean workflow:

~~~text
producer:
    write orders_20261123.csv.tmp
    close/flush per contract
    rename to orders_20261123.csv.ready

consumer:
    discover READY file
    verify source identity + version + checksum/manifest
    claim business file ID
    parse/validate
    transactionally process rows with stable keys
    record complete outcome
    archive or mark DONE
~~~

A file may be touched multiple times at the filesystem layer while still producing **at most one business effect per row/order** if deduplication is designed properly.

### 10.2. File Crash Windows

| Failure | Visible After Restart | Recovery |
|---|---|---|
| Crash before filter accepts | File still in ready | Normal re-poll |
| Filter accepted, not yet parsed | Persistent filter may skip file | Recovery scan by business status; repair/reset metadata **per runbook** |
| Parsed, rows uncommitted | No business records exist | Re-run rows with stable keys |
| Some rows committed, some not | File in partial state | Per-row ledger/transaction + file completion marker |
| All rows committed, archive incomplete | File still in ready/processing | Reconcile then archive without re-inserting |
| Archived, durable completion unrecorded | File gone from ready | Rely on receipt/manifest and business reconciliation |

### 10.3. Large Files: Idempotency at Which Granularity?

- **File-level dedupe:** Same logical file/version is fully ingested at most once.
- **Record-level dedupe:** Each row carries a source record key; file retries create no duplicate rows.
- **Business-level dedupe:** Two distinct files may still carry the same order ID/revision and must be deduplicated.
- **Output-level dedupe:** Outbound file creation uses deterministic paths/versions or manifests.

If a 50,000-row file commits in 500-row batches, crashing after batch 20 requires knowing **which rows already committed**; a single `fileProcessed=true` flag cannot resume mid-file cleanly.

### 10.4. File Outbound

When writing files for partners:

- Write a temporary name, complete writes, verify checksum/record count, then rename/place marker.
- Assign deterministic output identities/versions per logical batch/event.
- On timeout or crash after rename but before ledger commit, inspect the target file rather than inventing a new random filename.
- Never overwrite files sharing a name but differing in payload/version without policy.
- Never delete original sources or outbox commands before target delivery satisfies contract.

### 10.5. Post-Restart File Checklist

- [ ] Ready protocol agreed upon by both sides.
- [ ] Persistent filter has a re-drive path for accepted-but-unprocessed files.
- [ ] File, record, and business dedupe keys are distinct.
- [ ] Archive/move/delete occurs only after durable completion.
- [ ] Partial batches maintain per-row checkpoints and recovery.
- [ ] Schema-invalid files go to quarantine rather than looping forever.
- [ ] Multiple replicas use distributed claims/partitioning, not just in-memory filters.
- [ ] Crash-tested every step from discovery through archiving.

## 11. SFTP Inbound/Outbound: Dual Remote and Local Footprints

SFTP inbound often involves a **remote file synchronizer**, **local file cache**, and **downstream business handler**. You can end up in a state where "remote file downloaded" is recorded with zero business commits.

### 11.1. SFTP-Specific Failure Windows

~~~text
Remote SFTP file READY
   -> remote accept-once metadata
   -> local download (temporary -> final)
   -> local accept-once metadata
   -> parse / validate
   -> DB transaction
   -> business COMPLETE
   -> remote/local archive policy
~~~

Verify at every step:

- Where do remote/local metadata stores live, and do they survive restarts?
- If download succeeds but parsing fails, is the file kept in local cache or deleted?
- If a remote file is replaced under the same filename, do timestamp/size/version filters notice?
- If two pods download the same file, are metadata stores/claims shared and atomic?
- If remote deletes early, is there a durable copy for replay?
- Is business completion decoupled from the remote accept-once marker?

### 11.2. Safe Strategy

1. Producer uploads a temporary name then renames or writes a marker when done.
2. Consumer verifies SSH host keys and enforces bounded timeouts/retries.
3. Record logical file ID/version, checksum, and source metadata.
4. Download to a local temporary path, exposing the final path only on completion; verify filesystem semantics.
5. Keep the file durably (or ensure re-fetchability) until business completion.
6. Parse/commit using stable business keys with per-row or per-batch checkpoints.
7. Mark complete and archive only after data is durable and reconciled.
8. On crash, recovery scans items accepted/downloaded but incomplete.
9. Never delete remote files arbitrarily; follow partner retention and ownership.
10. With multiple replicas, enforce distributed claims or explicit path partitioning.

### 11.3. SFTP Outbound and Ambiguous Outcomes

If SFTP `rename` succeeds on the server while the client loses the response:

- Do not assume the upload failed.
- Inspect remote final/temporary paths, size/hash/manifest, and target receipts.
- Keep the **same output identity** for the same business command—never create a second file under a new name.
- If the remote already received and processed the file, avoid re-uploading outside contract.
- Record `UNKNOWN_OUTCOME` when proof is lacking, with an owner and reconciliation workflow.

### 11.4. SFTP Checklist

- [ ] Remote/local metadata and business ledgers have separate responsibilities.
- [ ] Recovery handles files downloaded before handler commit.
- [ ] Never rely solely on accept-once filters to prevent business duplicates.
- [ ] Checksums/versions handle remote files modified under the same name.
- [ ] Distributed claims protect shared remote paths across replicas.
- [ ] Session reconnect/backoff, host-key verification, and secret rotation are active.
- [ ] Reconciliation covers lost upload/rename responses.
- [ ] Tested restarts after metadata accept, after download, and after business commit.

## 12. HTTP Inbound/Outbound: Caller Retries and Ambiguous Side Effects

### 12.1. HTTP Inbound Gateways/Webhooks

For side-effecting requests, clients commonly retry on:

- Dropped connections;
- HTTP 502/503/504;
- Gateway timeouts;
- Lost responses even though the backend committed;
- Client restarts or load balancers failing over backends.

Mitigations:

1. Require a **client-generated idempotency key** or contract-recognized business request ID.
2. Validate authentication/authorization and request integrity.
3. Guard keys with a unique constraint in a durable inbox/processed ledger.
4. For same key + same semantic payload, return a consistent **prior result/tracking ID**.
5. For same key + different payload, return conflict or handle per API contract.
6. Return `200/201/202` only after contractual state is durably persisted.
7. For long-running work, return `202 Accepted + tracking ID` after durable inbox commit.
8. When clients disconnect, backends don't automatically cancel; workers still require idempotency.

**Note:** Returning `202` after enqueuing only into an in-memory `ExecutorChannel` or non-persistent `QueueChannel` risks losing requests on pod restarts.

### 12.2. HTTP Outbound Gateways

| Scenario | Common Mistake | Preferred Behavior |
|---|---|---|
| POST sent, response timed out | Retry with a new request ID | Query remote state or retry with remote-supported idempotency key |
| 409 because key already processed | Treat as permanent error and resend under another key | Check contract: may safely echo prior result |
| 503 before remote commit | Retry infinitely | Bounded attempts, per-attempt timeout, jitter, deadline |
| 401 expired token | Tight-loop retries | Controlled refresh keeping business identity intact |
| Remote API lacks idempotency | Blindly retry POST | Use command ledger/`UNKNOWN_OUTCOME`, require reconciliation |
| Caller timed out | Assume downstream didn't run | Query outcome by business key/tracking ID |

### 12.3. Outbound Command Ledger

~~~text
external_operations(
    operation_id,
    target,
    idempotency_key,
    payload_fingerprint,
    status = PENDING | IN_FLIGHT | SUCCEEDED | FAILED | UNKNOWN,
    remote_reference,
    last_attempt_at,
    next_attempt_at
)
~~~

- Persist command records in the same transaction as the business decision whenever possible.
- Workers send the stable idempotency key across attempts.
- Upon valid remote confirmation, store the remote receipt/result.
- If connectivity drops after the request may have reached the remote, keep `UNKNOWN`; query state or retry only if the remote idempotency contract permits.
- On restart, never blindly reset all `IN_FLIGHT` records to `PENDING` and resend.

### 12.4. HTTP Checklist

- [ ] Side-effecting endpoints enforce contract-backed idempotency keys.
- [ ] Duplicate responses match prior outcomes consistently.
- [ ] Same-key/different-payload requests are explicitly handled.
- [ ] Durable handoff completes before returning `202`.
- [ ] Unknown outcomes and late responses are handled.
- [ ] Timeouts/retries never duplicate payments or shipments.
- [ ] Never log tokens, cookies, or sensitive payloads.
- [ ] Tested successful HTTP POST with lost response and post-restart caller retry.

## 13. JMS: Redelivery After Listener Restart

JMS acknowledgements and session transactions depend on the provider and container. When a listener crashes before acknowledging a message, the broker can redeliver it.

### 13.1. Typical Window

~~~text
Broker queue -> JMS listener -> DB transaction commit
                                   |
                            Process crash
                                   |
                         JMS ack incomplete
                                   |
                            Broker redelivers
                                   |
                      Business ledger sees duplicate
                                   |
                      No-op / prior outcome + ack
~~~

JMS acknowledgement alone cannot create exactly-once effects in a DB outside the broker transaction. Even with transacted listeners, verify **whether the transaction spans the DB**. Local JMS session transactions do not automatically include JDBC or HTTP.

### 13.2. JMS Checklist

- [ ] Listener container, transacted session / ack mode, and ack timing are documented.
- [ ] Handler exceptions propagate or recover per policy; never swallow unpersisted failures.
- [ ] On container redelivery, business keys and processed ledgers protect side effects.
- [ ] When using local transactions, explicitly document separate DB boundaries.
- [ ] Poison messages have bounded retries/redeliveries into a DLQ.
- [ ] Reply destinations / request-reply gateways handle late replies and timeouts.
- [ ] Consumer concurrency/prefetch does not break ordering or transactions.
- [ ] DLQ replays preserve business keys instead of minting new keys to "force reprocessing".
- [ ] Tested crashes before/after DB commit, before/after JMS ack, and broker restarts.

### 13.3. Never Ack Before Durable Recovery Completes

If a handler fails and swallows the exception, some containers/ack modes may acknowledge the message. You must either:

- Rethrow to trigger rollback/redelivery per source semantics, **or**
- Persist the message and error to durable quarantine/inbox, confirm persistence succeeded, and then ack per policy.

Never treat `errorChannel` as a durable DLQ by default. Inspect the real error flow in your `IntegrationFlow`/adapter and version.

## 14. AMQP/RabbitMQ: Ack, Requeue, and Publisher Confirms

### 14.1. Consumer Redelivery

For AMQP listeners, key decisions include:

- Do broker queue durability and message persistence meet requirements?
- Which acknowledgement mode does the container use?
- Does ack happen before or after DB commit?
- If the process dies before ack, how does the broker redeliver?
- Are requeues/rejects/DLX/DLQ bounded with retention?
- Does consumer idempotency hold when two deliveries arrive back-to-back?

**Manual ack** clarifies control over when confirmation happens, yet **does not create exactly-once**. DB committing before broker ack arrives is a normal redelivery window you must handle.

### 14.2. Publisher Confirms Also Have an Ambiguous Window

~~~text
Outbox worker -> broker publish -> broker accepts
                                    |
                            confirm response lost
                                    |
                               worker crash
                                    |
                         outbox still PENDING
                                    |
                           retry same event
~~~

Duplicate publishes can happen. Use stable message/event IDs and consumer dedupe; never rely on a timed-out publisher confirm to conclude the broker didn't receive the message.

### 14.3. AMQP Checklist

- [ ] Publisher confirms/returns and lost-confirm handling are defined.
- [ ] Outbox event IDs remain unchanged across retries and restarts.
- [ ] Both queue durability and message persistence match SLAs.
- [ ] Consumer ack/requeue/reject behavior is crash-tested.
- [ ] Poison messages are never infinitely requeued.
- [ ] DLQ exists with durable replay, retention, and auditing.
- [ ] Consumers are idempotent on broker redelivery.
- [ ] Tested two consumers receiving the same logical business event at different times.
- [ ] Prefetch/unacked counts and queue age are monitored during scaling/restarts.

## 15. Kafka: Offset Commits and DB Transactions Are Two Separate Worlds

### 15.1. Offsets Are Not Business Processed Keys

Kafka records are identified by topic/partition/offset, yet:

- Replays in the same consumer group can re-read uncommitted offsets.
- Changing consumer groups or resetting offsets replays large ranges.
- Producers can emit the same business event at a new offset.
- Copying events to another topic or retry/DLT creates new records/offsets.
- The same order can emit multiple events across revisions.

**Never store only offsets to prevent business duplicates.** Deduplicate on `eventId` or `(source, orderId, revision)`, storing topic/partition/offset purely as audit/checkpoint metadata.

### 15.2. Crash After DB Commit, Before Offset Commit

~~~text
Kafka record O-123
    -> listener
    -> DB transaction: order update + processed key + outbox
    -> COMMIT
    -> process crashes
    -> offset not committed
    -> Kafka delivers record again
    -> processed key exists + matching fingerprint
    -> no-op, then commit offset according to container policy
~~~

Verify the actual ack/commit settings of the **Spring Kafka listener container** backing Spring Integration's Kafka inbound adapter; never assume all error handlers share identical semantics. If an error flow recovers a handler exception, verify whether the offset gets committed and where the message is durably saved.

### 15.3. Transactional Producers Do Not Replace Idempotent DB Consumers

Kafka provides producer idempotence and transaction semantics **within its configured Kafka scope**. Those guarantees do not automatically span external PostgreSQL/HTTP/SFTP systems.

With DB + Kafka, a common pattern is:

- Database transaction saves business state + outbox;
- Worker publishes Kafka events at-least-once;
- Downstream consumers maintain processed-event ledgers;
- Never claim end-to-end exactly-once outside proven boundaries.

### 15.4. Ordering During Replays

If order revision 2 fails while revision 3 processes first, business state corrupts even though both events have distinct keys and "no duplicates". Therefore:

- Partition Kafka keys to match business ordering requirements;
- When routing failed records to retry topics/DLTs, define how subsequent revisions are blocked or handled;
- Use DB version checks/optimistic locking to catch stale events;
- Include revisions in dedupe keys when each revision is a distinct valid event;
- Never treat "different event key" as an excuse to skip ordering checks.

### 15.5. Kafka Checklist

- [ ] Stable event IDs independent of offsets.
- [ ] Container ack/commit timing aligns with durable business completion.
- [ ] DB updates + processed ledger commit atomically.
- [ ] Producer/outbox retries preserve event IDs.
- [ ] Replays after offset resets or group migrations cause no duplicate side effects.
- [ ] Error recovery/DLT persists durably before marking records handled per policy.
- [ ] Ordering/version guards protect retry-topic workflows.
- [ ] Tested crashes before DB commit, after DB commit/before offset commit, and after ack.
- [ ] Monitored consumer lag, rebalances, duplicate counts, and pending outbox items.

## 16. JDBC Polling: Row Claims Are Not Idempotency

JDBC inbound adapters/pollers query eligible rows. If two replicas run `SELECT WHERE status='NEW'`, both can read the same row before either marks it `PROCESSING`.

### 16.1. Claim/Lease/Complete Model

~~~text
NEW -> CLAIMED(owner, lease_until, fencing_version)
     -> BUSINESS_COMMITTED
     -> COMPLETE

CLAIMED -> lease_expired -> re-claim by new worker
CLAIMED -> recoverable_error -> RETRYABLE
CLAIMED -> invalid_payload -> QUARANTINED
~~~

A sound design requires:

- Dialect-appropriate atomic claim/locking—never plain SELECT followed by unconditional UPDATE;
- Owner/token/version per claim;
- Lease expiration to reclaim jobs from dead pods;
- Unique business keys to block duplicates if an old worker keeps running;
- Bounded retries/backoff and attempt caps;
- Query/connection/pool timeouts;
- Monitoring rows stuck in `CLAIMED` too long;
- Durable business commits and completion markers on clean transaction boundaries.

### 16.2. PostgreSQL Pseudo-SQL for Claiming a Batch

~~~sql
-- Directional example; verify schema, isolation, and indexes.
BEGIN;

SELECT id
FROM integration_inbox
WHERE status = 'NEW'
ORDER BY created_at, id
FOR UPDATE SKIP LOCKED;

-- Within the same transaction, limit batch size and transition selected IDs
-- to CLAIMED with lease_owner, lease_until, and incrementing fencing_version.

COMMIT;
~~~

`SKIP LOCKED` and row-limiting syntax vary by database. In real PostgreSQL, a CTE + `UPDATE ... RETURNING` can claim atomically in one statement. After claiming, business logic must still prevent stale workers from writing after lease expiration.

### 16.3. Why Is Fencing Needed?

Worker A claims job `O-123` with a 60-second lease, then pauses for a long GC. The lease expires; worker B reclaims and completes it. Later A wakes up and sends an HTTP POST under its old lease. With only an "expired lock" and no guard on the side effect, A can still corrupt state or double-send.

A **fencing token/version** lets supporting targets reject mutations from older tokens. When targets do not support fencing, combine idempotency keys, authoritative state checks, and reconciliation—merely raising lease timeouts never eliminates the risk.

### 16.4. JDBC Checklist

- [ ] Rows are claimed atomically with owners and lease recovery.
- [ ] Fencing/versions guard against stale workers continuing writes.
- [ ] Business unique keys are independent of claim state.
- [ ] `PROCESSED` commits in the same transaction as domain mutations when sharing a DB.
- [ ] Lost connections during DB commit are reconciled before retrying.
- [ ] Query/pool timeouts, indexes, and batch limits are tested.
- [ ] Avoid holding transactions across long HTTP/SFTP calls when splittable.
- [ ] Expired `CLAIMED` rows are scanned/recovered with auditing.
- [ ] Multi-replica tests cover same-key races, kill/restart, and lease expiry.

## 17. Hands-On: Transactional Idempotent JDBC Handler

Suppose the business database, `processed_events`, `orders`, and `integration_outbox` all reside in PostgreSQL. Producers provide a stable `eventId`, while consumers compute a fingerprint after validating payloads. The goal is **atomic commit of DB mutation + dedupe marker + outbound obligation**, leaving outbound delivery to a separate worker.

### 17.1. Input Contract

- `(sourceSystem, tenantId, eventId)` uniquely identifies a logical event.
- `(tenantId, orderId, revision)` represents business version; never blindly apply older revisions.
- When producers retry the **same event**, `eventId` and semantic payload stay identical.
- Same `eventId` with a different payload is a conflict—never silently drop.
- Kafka/HTTP publishes never execute directly inside this DB transaction.

~~~java
// Java 17+. Fingerprint must be computed server-side from canonical payload.
record OrderEvent(
    String sourceSystem,
    String tenantId,
    String eventId,
    String orderId,
    long revision,
    String state,
    String fingerprint,
    String outboundJson
) {}
~~~

### 17.2. Service Pattern with Unique Constraint

~~~java
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderEventProcessor {

    private final NamedParameterJdbcTemplate jdbc;

    OrderEventProcessor(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public ProcessingOutcome process(OrderEvent event) {
        MapSqlParameterSource p = new MapSqlParameterSource()
            .addValue("source", event.sourceSystem())
            .addValue("tenant", event.tenantId())
            .addValue("eventId", event.eventId())
            .addValue("fingerprint", event.fingerprint())
            .addValue("orderId", event.orderId())
            .addValue("revision", event.revision())
            .addValue("state", event.state())
            .addValue("outboundJson", event.outboundJson());

        int claimed = jdbc.update("""
            INSERT INTO processed_events
              (source_system, tenant_id, event_id, payload_sha256, business_ref)
            VALUES
              (:source, :tenant, :eventId, :fingerprint, :orderId)
            ON CONFLICT (source_system, tenant_id, event_id) DO NOTHING
            """, p);

        if (claimed == 0) {
            String knownHash = jdbc.queryForObject("""
                SELECT payload_sha256 FROM processed_events
                 WHERE source_system = :source
                   AND tenant_id = :tenant
                   AND event_id = :eventId
                """, p, String.class);

            if (!event.fingerprint().equals(knownHash)) {
                throw new IllegalArgumentException(
                    "Same event key with different business payload");
            }
            return ProcessingOutcome.ALREADY_PROCESSED;
        }

        int changed = jdbc.update("""
            INSERT INTO orders (tenant_id, order_id, revision, state)
            VALUES (:tenant, :orderId, :revision, :state)
            ON CONFLICT (tenant_id, order_id)
            DO UPDATE SET revision = EXCLUDED.revision,
                          state = EXCLUDED.state
            WHERE orders.revision < EXCLUDED.revision
            """, p);

        if (changed != 1) {
            // Example policy: reject stale revisions. Real domains need explicit rules.
            throw new IllegalStateException("Stale order revision");
        }

        jdbc.update("""
            INSERT INTO integration_outbox
                (event_id, target, payload_json, status)
            VALUES (:eventId, 'kafka-orders', CAST(:outboundJson AS jsonb), 'PENDING')
            ON CONFLICT (event_id) DO NOTHING
            """, p);

        // Do not call remote HTTP or Kafka directly here.
        return ProcessingOutcome.APPLIED;
    }

    enum ProcessingOutcome { APPLIED, ALREADY_PROCESSED }
}
~~~

**Technical notes:**

1. This is a skeleton for **PostgreSQL + Spring JDBC**, not complete production code. Verify imports, Java version, migrations, validation, logging, exception mapping, canonical hashing, transaction manager, payload schema, and concurrent-insert edge cases.
2. `@Transactional` takes effect when invoked through the proper proxy/transaction infrastructure; never assume self-invocation is transactional.
3. Dedupe insert, domain mutation, and outbox insert commit/roll back **atomically** in one DB transaction.
4. On post-commit duplicate delivery, `claimed=0`; fingerprints are compared and no new side effects occur.
5. If the business update fails, the exception rolls back the inserted marker, enabling valid retries later.
6. For multiple targets, use a composite outbox identity like `(eventId, target)` or target-specific event IDs; the example schema in Section 7 uses a single `event_id` primary key and thus fits one event/target.
7. If an HTTP gateway needs to return the prior response, persist the outcome/response or query authoritative domain state.
8. Unique constraints block concurrent duplicate workers more reliably than a separate SELECT before INSERT; still test isolation and exception semantics.

### 17.3. Wiring the Handler into an `IntegrationFlow`

~~~java
// Illustrative structure; verify DSL against your Spring Integration version.
@Bean
IntegrationFlow orderEventFlow(OrderEventProcessor processor) {
    return IntegrationFlow.from("orderEvents")
        .handle(OrderEvent.class, (event, headers) ->
            processor.process(event))
        .get();
}
~~~

This snippet omits sources/channels/acks and full error handling. Configure Kafka/JMS/AMQP/File inputs so sources ack/checkpoint per contract only after durable completion. Returning `APPLIED` from the handler does not yet mean the Kafka outbox event has been published.

### 17.4. Verification via SQL and Business Outcomes

- New event: `orders` has 1 row, `processed_events` has 1 key, `integration_outbox` has 1 event.
- Resend same event: `orders`/`outbox` counts stay unchanged; returns `ALREADY_PROCESSED`.
- Two threads send same event concurrently: only one transaction applies the business effect.
- Same `eventId` with altered payload: conflict detected.
- Exception thrown between business update and outbox: entire transaction rolls back.
- Process killed after commit before ack: redelivery returns duplicate no-op.
- Stale revision sent: stale-revision policy triggers cleanly without silent overwrites.
- Outbox worker publishes successfully then dies before marking sent: downstream consumers stay idempotent.

## 18. Claims/Leases, Fencing, and Multiple Replicas

### 18.1. Three Contention Scenarios

**Concurrent duplicates:** Two Kafka consumers or file pollers pick up the same logical event. Atomic business keys/unique constraints protect effects regardless of whether ingress markers are shared.

**Lease expiration:** Worker A claims a job with a 60-second lease, then hits a long GC pause. Worker B reclaims and completes it; A wakes up and calls HTTP. Without side-effect guards, duplicates still happen.

**Split brain:** A network partition leaves two nodes believing they own the work. Never rely solely on leader election or distributed locks to protect high-risk operations like payments.

### 18.2. Fencing Tokens

Each valid claim issues a monotonically increasing `fencingVersion`. Supporting targets must reject mutations carrying tokens older than the latest accepted version. When targets lack fencing support:

- Use target-supported stable idempotency keys.
- Check authoritative domain state before acting.
- Maintain durable command ledgers, owners, and reconciliation workflows.
- Re-check leases and enforce timeouts before side effects without treating them as absolute guarantees.
- Enforce versions/unique constraints on DB state.
- Never claim "exactly-once" solely because locks/leases exist.

### 18.3. Scheduled Retries After Restart

- [ ] One primary retry owner per operation; avoid stacking client/advice/container/broker retries.
- [ ] `nextAttemptAt`, `maxAttempts`, and `lastError` are durably persisted.
- [ ] Pending/leased jobs recover when pods are killed.
- [ ] Re-dispatches preserve business keys and target operation IDs.
- [ ] On unknown outcomes, verify remote state or idempotency contracts before resending.
- [ ] Throttle recovery with backoff/jitter so thousands of pods do not retry simultaneously.
- [ ] Retry queues enforce TTLs, retention, and oldest-pending alerts.
- [ ] Every replay is audited with an owner.

## 19. Startup, Graceful Shutdown, and Rolling Deployments

### 19.1. Graceful Shutdown Helps, But Cannot Replace Crash Recovery

An orderly shutdown sequence:

1. Stop accepting new messages in pollers/listeners per adapter lifecycle.
2. Stop claiming new inbox/outbox jobs.
3. Finish active business transactions within the grace period.
4. Acknowledge only messages with contractually durable completion.
5. For unfinished I/O, ensure retry/recovery state persists.
6. Close session/connection pools, flush telemetry, report remaining inflight work.
7. On force kills, never assume cleanup ran; sources and ledgers must self-recover.

**Always test `SIGKILL`/JVM crashes**, since OOMs and power losses skip graceful hooks.

### 19.2. Ordered Startup Recovery

- [ ] Verify schemas/migrations, secrets, TLS/SSH host keys, and dependency readiness.
- [ ] Read durable inbox/outbox tables to assess post-crash state.
- [ ] `RECEIVED`: eligible for claiming within capacity.
- [ ] `CLAIMED` with active lease: do not double-claim.
- [ ] `CLAIMED` with expired lease: reconcile/fence, then reclaim if safe.
- [ ] `PROCESSED` but unacked: on redelivery, no-op and ack per policy.
- [ ] `OUTBOX PENDING`: worker resumes publishing with stable event ID.
- [ ] `UNKNOWN_OUTCOME`: verify remote receipt before retrying.
- [ ] Files accepted but business-incomplete: recovery scan handles selective filter re-drives.
- [ ] Poison/invalid messages: quarantine; never tight-loop retry.
- [ ] Re-open pollers/listeners gradually with rate limits and watch backlogs drain.

### 19.3. Two App Versions Running During Rolling Deploys

- Key formats, canonical payload hashing, and ledger schemas stay compatible.
- Never alter event IDs based on application version.
- Migrations support both old and new versions during the rolling window.
- Old pods may hold leases as new pods boot; fencing and idempotency protect state.
- HPA/rolling surges raise total claims/connections; budget cluster-wide quotas.
- On rollback, never wipe the new version's metadata/offsets/ledgers to "start fresh".
- Test manual replays on records produced by both versions.

## 20. Retention, Schema Evolution, and Disaster Recovery

### 20.1. Dedupe Keys Must Outlive Replay Windows

Base retention on real replay horizons:

| Source | Windows to Consider |
|---|---|
| Kafka | Topic retention, offset resets, consumer group migrations, manual replays |
| JMS/AMQP | DLQ/DLT retention, redelivery/requeues, operator replays |
| SFTP/File | Partner file resends, archive recovery, disaster replays |
| HTTP | Client retry windows, remote idempotency key TTLs, business reconciliation |
| JDBC | Inbox/outbox retention, lease recovery, row/archive migrations |
| DR/backup | Restoring older snapshots and re-receiving newer events |

If a remote HTTP target retains idempotency keys for only 24 hours while your app replays a payment after 7 days, **resending the same key can still duplicate**. Check remote contracts, query status, or get business approval before resending.

### 20.2. Canonical Fingerprints and Format Versions

A serializer upgrade can reorder JSON fields without changing business semantics. Hashing raw bytes causes false conflicts on restart. Instead:

1. Parse according to supported schema/version.
2. Canonicalize business-significant fields.
3. Compute canonical fingerprints on the consumer side.
4. Store `fingerprintVersion` alongside the hash.
5. Support dual-reads/compatible migrations when upgrading schemas or hash algorithms.
6. Never use hashes instead of authentication/authorization or business keys.

### 20.3. Ledger Cleanup and Privacy

- Never delete dedupe keys before all contractual replay sources expire.
- For long-term archives, consider non-sensitive tombstones/summaries.
- Govern PII-bearing payloads/raw files via retention and access controls.
- When scrubbing PII, preserve duplicate detection via properly pseudonymized keys.
- Never bulk-purge metadata stores just to reset application state.
- Audit all DLQ/quarantine purges and manual replays.

### 20.4. Disaster Recovery Is Harder Than Pod Restarts

An older DB backup may lack processed keys for recent events. After restoring, Kafka/SFTP may redeliver events whose side effects already hit targets. DR runbooks must:

1. Identify the recovery point and the gap window missing from ledgers.
2. Reconcile business state/remote receipts instead of blindly restarting consumers.
3. Rebuild or merge processed ledgers with verification.
4. Scope replays by stable business IDs, versions, and source windows.
5. Never replay non-idempotent actions with ambiguous outcomes.
6. Verify DB, file, broker, and HTTP state post-DR using test fixtures.
7. Record evidence and obtain owner signoff concluding recovery.

## 21. Observability: Measuring Duplicates and Recovery Accountability

A dashboard showing only ingress counts or rising Kafka offsets does not prove correctness. Track **logical event → business effect → source acknowledgement → downstream delivery**.

### 21.1. Structured Logs and Tracing

| Field | Purpose |
|---|---|
| `sourceSystem`, `tenantId`, `eventId` | Logical identity of the event |
| `businessId`, `revision`, `operation` | Identifies the side effect |
| `fingerprintVersion`, `payloadHash` | Detects same-key/different-payload conflicts |
| `integrationFlowId`, endpoint/adapter ID | Identifies which handler processed the message |
| `podId`, `workerId`, `leaseVersion` | Investigates concurrent duplicates |
| `fileId`, `sourceOffset`, `sourceMessageId` (if any) | Traces source provenance; never replaces business keys |
| `inboxStatus`, `processedStatus`, `outboxStatus` | Distinguishes durable milestones |
| `ack/commitState` | Separates business commits from source acknowledgements |
| `attempt`, `errorCategory`, `retryDelayMs` | Spots retry storms |
| `remoteOperationId`, `remoteReceipt` | Reconciles external side effects |
| `correlationId`, `traceId`, `incidentId` | End-to-end tracing and incident tracking |
| `replayOwner`, `replayReason` | Audits manual recovery actions |

Never log passwords, raw API tokens, SFTP private keys, Authorization headers, session cookies, or PII payloads. Ledgers and quarantines also require strict ACLs, encryption, and retention.

### 21.2. Metrics to Emit

| Conceptual Metric | Alert Condition |
|---|---|
| Ingress received vs. business committed | Received items sitting without completion |
| Duplicate detection rate | Abnormal spikes after restarts/replays |
| Dedupe conflict count | Same key/different payload; producer or migration bug |
| Inbox oldest pending/claimed age | Stalled workers or expired leases |
| Stale leases and recovery count | Hung workers or poorly tuned timeouts |
| Outbox pending count / oldest age | Business committed while outbound lags |
| Outbox retries / exhausted | Prolonged target failures |
| Unknown-outcome count / age | Unverified side effects |
| Kafka lag / rebalances / offset commit errors | Message backlogs or redeliveries |
| JMS/AMQP ready / unacked / redelivery / DLQ age | Unhandled redeliveries or poison messages |
| SFTP/File oldest ready/processing age | Files stuck after restarts |
| JDBC lock / transaction / pool waits | DB contention triggering lease timeouts |
| Business effect count per unique event | Catches true duplicate mutations |
| Recovery backlog drain rate | Post-outage recovery speed |
| End-to-end business completion latency | Whether SLOs are met |

Metric names are **conceptual**; not all exist out of the box in Spring Integration/Micrometer. Business metrics usually require custom instrumentation from code/ledgers. Avoid putting `eventId` into high-cardinality metric labels; keep `eventId` in access-controlled logs and traces.

### 21.3. Interpreting Metrics Properly

- Rising duplicate counts after a Kafka replay **may be normal**; rising business side-effect counts for the same key indicates a bug.
- Low queue depth does not prove zero backlog; JMS/AMQP can hold many unacked messages.
- Rising Kafka committed offsets without matching processed-ledger growth may indicate premature acks or swallowed exceptions.
- Growing outbox pending counts alongside steady DB commits indicate egress bottlenecks.
- Rising `CLAIMED` lease expiries point to GC pauses, overloaded workers, remote timeouts, or pool saturation.
- Rising conflicts post-deploy can come from canonical hash/schema-version changes rather than bad producer data alone.

**Daily operational question:** Does every received event sit in one of three clear states: **processed**, **pending with guaranteed recovery**, or **failed with an assigned owner**?

## 22. Security, Replay Attacks, and Operational Access Control

Idempotency does not replace authentication/authorization. A client must never retrieve a prior result simply by knowing or guessing an idempotency key.

Checklist:

- [ ] Authenticate and authorize senders before querying ledgers or returning cached responses.
- [ ] Namespace keys by source/tenant so tenants cannot collide.
- [ ] For webhooks, verify signatures and timestamps/nonces per protocol to block replay attacks.
- [ ] Never confuse security nonces with business keys for legitimate redeliveries.
- [ ] Encrypt/secure ledgers, inboxes, and outboxes with least-privilege read/write access.
- [ ] Protect DLQ/quarantine stores like primary data; never grant org-wide open access.
- [ ] Require approvers, reasons, scopes, and audits for operator replays.
- [ ] Block replays of canceled/expired data unless domain state permits.
- [ ] Never return another tenant's prior response on key collisions.
- [ ] Never bypass TLS/SSH host-key verification during recovery.
- [ ] Rate-limit replay batches and retries to avoid self-inflicted DoS.
- [ ] For commands triggering payments, refunds, cancellations, or access grants, verify authorization and current policies before any new side effect.

**Special note:** Partner API idempotency keys may have TTLs or merchant/account scoping. Sending the same key under different credentials may not be recognized as a duplicate—check the actual contract.

## 23. Restart and Replay Test Matrix: 65 Scenarios

### 23.1. Designing Evidence-Backed Tests

1. Build test fixtures with stable `eventId`, `businessId`, source/tenant, schema version, and fingerprint.
2. Record pre-fault state: ingress markers, DB transactions, outbox rows, acks/offsets.
3. Inject faults at **deliberate failure windows**, not merely restarting after idle completion.
4. Kill processes hard or drop network/commit confirmations right inside target windows.
5. Restart or fail over to another replica and allow source redelivery/replay.
6. Inspect actual business state in target DBs, partners, brokers, and files—not just logs.
7. Record attempts, completed effects, duplicate no-ops, and DLQ/`UNKNOWN` outcomes.
8. Test two workers racing on the same key and a stale worker acting after lease expiry.
9. Test key retention, schema migrations, and backup restores.
10. Mark PASS only when invariants I1–I8 are proven.

### 23.2. Acceptance Matrix

| ID | Scenario | Expected Outcome |
|---|---|---|
| **T01** | Same `eventId` received twice in one JVM | One business effect, duplicate no-op |
| **T02** | Same `eventId` received again after restart | Persistent ledger blocks duplicates |
| **T03** | Same key with different semantic payload | Conflict/quarantine; no silent drops |
| **T04** | Two threads insert dedupe key concurrently | Unique constraint prevents double effect |
| **T05** | Two pods receive same business event | One business effect |
| **T06** | Crash before dedupe transaction | Source/inbox replay processes cleanly |
| **T07** | Crash after inserting marker, before commit | Both marker and mutation roll back |
| **T08** | Crash mid-order-update | No partial committed state violating invariants |
| **T09** | Crash immediately after DB commit | Redelivery returns already-processed |
| **T10** | Crash after DB commit, before source ack | Zero loss and zero duplicates |
| **T11** | Source acks before durable inbox | Test catches data-loss risk; blocks GO |
| **T12** | `ExecutorChannel` accepts task then pod dies | Durable recovery exists; enqueue ≠ processed |
| **T13** | In-memory `QueueChannel` restarted | Not assumed durable unless persistent store used |
| **T14** | Metadata/business store unavailable | Never acks success without durability |
| **T15** | `IdempotentReceiverInterceptor` detects duplicate | Configured duplicate handling; skips side effects |
| **T16** | In-memory `MetadataStore` reset | Business ledger still protects side effects |
| **T17** | Persistent file filter accepted, handler failed | Recovery scan finds incomplete file |
| **T18** | Two flows share metadata prefix | Namespacing prevents cross-flow filtering |
| **T19** | Metadata TTL expires before replay window | Test flags risk or falls back to authoritative state |
| **T20** | File mid-upload | Ignored until ready marker/rename |
| **T21** | File crashes after 500/1,000 rows | Per-row/transaction checkpoints resume cleanly |
| **T22** | All rows commit, file archive fails | No re-inserts; reconciles and archives |
| **T23** | Same filename, newer revision | Version contract handles accurately |
| **T24** | Two differently named files share order revision | Business dedupe blocks duplicate |
| **T25** | Outbound file written, ledger unrecorded | Reconciles target path/checksum before retry |
| **T26** | SFTP remote accepted, local download partial | Safe re-fetch/resume |
| **T27** | SFTP local ready, business uncommitted | Recovers from local/remote |
| **T28** | SFTP remote metadata persisted, DB rolled back | Accepted is not treated as completed |
| **T29** | Two pods download same SFTP file | Claims/idempotency yield one effect |
| **T30** | SFTP upload/rename succeeds, response lost | Inspects remote state; no second file |
| **T31** | HTTP webhook repeats same idempotency key | Same result/tracking ID, one command |
| **T32** | HTTP same key / different payload | Conflict; never echoes wrong prior result |
| **T33** | HTTP returns 202 before durable inbox | Test flags design flaw; blocks GO |
| **T34** | HTTP client disconnects after backend commit | Retries cause no double effect |
| **T35** | HTTP POST commits remotely, response times out | Reconciles or retries same key if supported |
| **T36** | Remote idempotency TTL expires before replay | Blocks blind resend; routes to owner review |
| **T37** | JMS listener crashes before DB commit | Redelivery processes cleanly |
| **T38** | JMS listener crashes after DB commit, before ack | Redelivery is a no-op |
| **T39** | JMS handler swallows unpersisted exception | Test catches false ack and fixes propagation |
| **T40** | JMS poison message redelivered repeatedly | Bounded DLQ; no infinite retries |
| **T41** | AMQP consumer commits DB, ack lost | Idempotent redelivery |
| **T42** | AMQP broker receives publish, confirm lost | Outbox retries + consumer dedupes |
| **T43** | AMQP target DLQ does not exist | No silent recovery or drops |
| **T44** | AMQP poison requeue storm | Bounded retries and quarantine |
| **T45** | Kafka DB commits, offset uncommitted | Redelivery is a no-op |
| **T46** | Kafka consumer group changed, topic replayed | Business effects do not duplicate |
| **T47** | Kafka producer resends event at new offset | Consumer deduplicates via business key |
| **T48** | Kafka retry topic mints new offset/topic | Event identity remains stable |
| **T49** | Order revision 3 arrives before revision 2 | Version/ordering guard handles cleanly |
| **T50** | Kafka error flow swallows exception then commits offset | Test catches lost processing obligation |
| **T51** | Two JDBC pollers claim same row | Atomic claim / unique guard |
| **T52** | JDBC worker crashes while `CLAIMED` | Lease/recovery allows reprocessing |
| **T53** | Lease expires, stale worker wakes up | Fencing/idempotency blocks stale side effects |
| **T54** | DB connection lost right at `COMMIT` | Reconciles actual state before retrying |
| **T55** | Key/fingerprint changes after schema migration | Versioned migration / dual-read active |
| **T56** | Business DB commits, publisher hasn't run | Outbox remains `PENDING` and emits after restart |
| **T57** | Publish succeeds, worker hasn't marked `SENT` | Stable event ID + consumer dedupe |
| **T58** | One event fans out to two targets | Per-target delivery ledger prevents drops |
| **T59** | Outbox holds 10,000 pending events after outage | Bounded retries/throttling drain backlog |
| **T60** | Old DB backup restored and source replayed | DR reconciliation prevents double effects |
| **T61** | Dedupe ledger purged prematurely | Retention policy gap detected/fixed |
| **T62** | Operator replays DLQ after schema fix | Zero duplicates, full audit trail |
| **T63** | Replay of expired/canceled payment/order | Business validity check rejects invalid effect |
| **T64** | Rolling deploy runs two versions concurrently | Keys/schemas/claims remain compatible |
| **T65** | Graceful stop and `SIGKILL` while inflight | Recovery meets I1–I8; zero lost/duplicate effects |

**Evidence per test:** environment and version, input/business ID, payload fingerprint, source offset/path, expected vs. actual, DB/remote side-effect count, ack status, inbox/outbox result, attempt count, logs/traces, and verifier.

### 23.3. Testing Priorities

- **P0 before go-live:** T04, T09–T12, T17, T31–T35, T38, T41–T42, T45, T51–T57, and T65. These represent classic loss/duplication windows.
- **P1 before scaling:** multi-replica claims, retry/DLQ, ordering, rolling deploys, quotas, and backlogs.
- **P2 periodic:** backup restores, retention expiry, key/fingerprint migrations, manual replay audits.

Priorities are educational guidelines; payment, access-grant, or irreversible workflows may demand stricter risk assessments.

## 24. Post-Restart or Post-Outage Recovery Runbook

### 24.1. Start with One Question: Where Does the Obligation Live?

During an incident, verify:

1. **Does the source still hold the data?** Ready file, remote SFTP file, JMS/AMQP queue, uncommitted Kafka offset, or `NEW` JDBC row?
2. **Did the app persist it durably?** Inbox row, processed key, business record, outbox event?
3. **Did an external side effect already occur?** HTTP payment/shipment, outbound SFTP file, Kafka publish, broker message?
4. **Is there a receipt/confirmation?** Response, publisher confirm, remote file checksum, partner transaction ID?
5. **Is resending safe?** Remote idempotency contract, fencing/versioning, reconciliation, or operator signoff?

**Never** reset metadata, purge files/queues, or seek Kafka offsets before answering these five questions.

### 24.2. 12-Step Procedure

1. **Contain the blast radius:** Identify affected deployment, pods, source ranges, timeframe, targets, and business IDs.
2. **Throttle ingress if needed:** Pause pollers/listeners/HTTP command intake if sources buffer durably.
3. **Snapshot state:** Inbox/outbox/processed ledgers, file metadata, offsets, queue ready/unacked counts, connection states.
4. **Confirm business side effects:** Inspect authoritative DBs and remote targets via operation IDs or receipts.
5. **Classify items:** `NEW`, `CLAIMED`, `PROCESSED`, `PENDING_OUTBOX`, `SENT`, `UNKNOWN_OUTCOME`, `QUARANTINED`.
6. **Find root cause:** Schema error, transaction rollback, lost ack, network timeout, worker OOM, lease expiry, or code bug.
7. **Check idempotency scope:** Keys, tenants, `eventId`, revisions, remote TTLs, canonical hash versions.
8. **Fix root cause:** Code/config patch, credentials, capacity, partner outage, or malformed data.
9. **Reconcile unknown outcomes:** Never blindly resend financial or hard-to-reverse side effects.
10. **Bounded replay:** Use small batches, keep original business keys, watch attempts/ordering, verify actual results.
11. **Drain backlog:** Ramp concurrency cautiously within quotas while monitoring outbox lag and duplicate counts.
12. **Close incident:** Reconcile logical event counts against business effects, archive audit trails, and update tests/runbooks.

### 24.3. Quick Decision Table

| State | Do Not Do | Appropriate Action |
|---|---|---|
| File accepted, no DB order | Skip assuming filter handled it | Run recovery scan and re-drive via key/ledger |
| DB committed, Kafka offset uncommitted | Reset DB to "match offset" | Allow redelivery; business idempotency no-ops |
| DB committed, outbox `PENDING` | Re-submit inbound from scratch with new `eventId` | Let outbox worker publish the original event |
| HTTP outcome `UNKNOWN` | Retry with a new request ID | Query partner or retry with supported key |
| AMQP publisher confirm lost | Assume broker never got it | Reconcile / rely on consumer dedupe on republish |
| JMS poison message | Tight-loop requeue forever | Route to DLQ and fix root cause |
| Kafka DLT record needs replay | Dump straight back to main topic blindly | Check ordering/version and duplicate state |
| JDBC lease expired while old worker runs | Only raise TTL | Enforce fencing/idempotency; check remote state |
| Metadata store wiped | Delete business state to "sync up" | Rebuild/reconcile from authoritative records |
| Old DB backup restored | Immediately resume all consumers | Run DR reconciliation for missing ledger window |

### 24.4. Replay Checklist

- [ ] Incident/replay ticket, owner, and explicit scope exist.
- [ ] Root cause is resolved or an approved mitigation is in place.
- [ ] Original business idempotency keys are preserved.
- [ ] Same-key/different-payload conflicts are checked.
- [ ] Respects business versions, expirations, and cancellation states.
- [ ] Unknown remote effects are verified or guarded by idempotency contracts.
- [ ] Batch/concurrency/rate limits and a stop switch exist.
- [ ] Alerts watch duplicate conflicts, DLQ, target errors, and backlogs.
- [ ] Expected logical success counts are reconciled against actual effects.
- [ ] Full pre/post replay audit exists; purge DLQs strictly per retention policy.

## 25. Case Study: SFTP → JDBC/Inbox-Outbox → Kafka and Logistics HTTP

A partner order platform drops CSV files onto SFTP every 10 minutes, each containing 1,000–10,000 rows. After validation, the app persists orders in PostgreSQL, emits `OrderAccepted` to Kafka, and books shipments via a logistics HTTP partner.

### 25.1. Faulty Initial Design

- Producer uploads directly as `orders.csv`, getting polled mid-write.
- SFTP accept-once filter uses memory only; restarts re-read files.
- DB lacks `(tenant, orderId, revision)` uniqueness.
- Handler commits order then publishes directly to Kafka without an outbox.
- Shipment HTTP POST uses no idempotency key.
- On pod restarts, orders exist yet files haven't moved to `done`, causing reprocessing.
- On HTTP timeout after shipment creation, workers retry with a fresh request ID.
- On Kafka consumer redelivery, a downstream service books a second shipment.
- No durable record tracks how many rows in a file have finished.

### 25.2. Target Design

**SFTP source:**

- Producer writes temp file then renames to `.ready` or sends a manifest.
- Every file carries a logical file ID, version, and checksum.
- Remote/local metadata stores use distinct namespaces; app tracks ingest state separately.
- Multi-replica uses distributed claims or partitioned remote paths.

**Business inbox/ledger:**

- Each row carries stable key `(partnerId, tenantId, orderId, revision)`.
- DB transactions combine unique guard, domain update, and outbox insert.
- File completion marks only after all valid rows process or errors follow policy.
- Partial batches record per-row status or committed checkpoints for resumption.

**Kafka egress:**

- Outbox events carry stable `eventId` and explicit payload versions.
- Publisher retries at-least-once without minting new event IDs across restarts.
- Consumers maintain processed-event ledgers or unique business effect keys.
- Offset commits depend on durable processing, not mere record receipt.

**Logistics HTTP:**

- Outbound command ledger stores stable `shipmentRequestId`.
- When partner supports idempotency keys, reuse the exact key across retries.
- If unsupported, use status lookups, receipts, and reconciliation.
- Timeouts after possible remote commit classify as `UNKNOWN_OUTCOME`—never automatically create a second shipment.

**Observability:**

- Received/processed file counts, oldest pending file, partial file progress.
- Duplicate no-ops per source/business event.
- Stale inbox leases, pending outbox age, Kafka lag/commit errors.
- HTTP unknown outcomes and verified shipment receipts.
- Correlation across file ID → order ID → outbox event ID → Kafka/HTTP receipts.

### 25.3. Mid-Flight Kill Timeline

~~~text
09:00:00  File F-001 renamed to READY
09:00:01  Pod A claims F-001; parses 2,000 orders
09:00:05  First 1,000 orders committed along with outbox events
09:00:06  Pod A killed; file not yet DONE
09:00:20  Pod B recovers file F-001
09:00:22  Rows 1..1000 -> ALREADY_PROCESSED
09:00:30  Rows 1001..2000 -> processed/committed
09:00:31  File completion marker committed
09:00:35  File archived per contract
09:00:40  Outbox workers emit pending Kafka events
09:00:45  One publisher killed after publish but before marking SENT
09:01:00  Republishes same event ID; downstream consumer no-ops
~~~

The same file may be re-ingested, yet **each order version commits validly at most once**. Do not try to prevent every duplicate delivery at every layer; instead guard the final invariant with durable state.

### 25.4. Failure Drills

**Drill A — Crash after filter accept, before DB commit.** Recovery scan catches the incomplete file even though the metadata store marked it accepted.

**Drill B — Crash mid-batch.** Only uncommitted rows apply business effects; already-completed rows no-op.

**Drill C — DB committed, Kafka publisher hasn't run.** Pending outbox emits after restart without creating duplicate orders.

**Drill D — Broker accepts Kafka publish, confirm/callback lost.** Republish may occur, yet consumer ledger prevents duplicate business effects.

**Drill E — Logistics HTTP books shipment, response times out.** Query partner via business shipment ID or retry with same idempotency key; zero second shipment.

**Drill F — Pod A lease expires while calling HTTP.** Pod B reclaims; fencing/remote idempotency/reconciliation protect side effects.

**Drill G — Restoring backup missing recent ledger entries.** Recovery reconciles orders/shipments and outbox instead of blindly replaying payments/shipments.

### 25.5. Acceptance Criteria

- Total valid logical orders match business records per domain contract.
- Zero duplicate orders or shipments from restarts/redeliveries.
- Can pinpoint which rows committed, failed, or haven't started.
- Post-outage Kafka/outbox backlogs drain within SLA.
- Accepted-but-incomplete files are never skipped.
- Unknown HTTP outcomes have owners and are reconciled.
- Multi-replica, rolling deploys, and manual replays introduce no business discrepancies.
- Dashboards/runbooks support investigation via business IDs without exposing raw sensitive payloads.

## 26. Pre-Production Idempotency Review Form Template

This is **illustrative YAML for technical/business review**, not config understood by Spring Integration or Spring Boot:

~~~yaml
flow: supplier-orders-sftp-to-kafka-and-http
owner:
  business: order-operations
  technical: integration-platform
  onCall: platform-operations

ingress:
  type: sftp-file
  remoteReadyProtocol: temporary-then-rename
  sourceId: partner-id
  fileIdentity: partner-file-id-version
  distributedClaim: required
  acceptedFileRecovery: required

messageIdentity:
  key: source-tenant-orderId-revision
  fingerprint: canonical-business-payload-sha256
  fingerprintVersion: 1
  sameKeyDifferentPayload: QUARANTINE_AND_ALERT
  retention: REVIEW_WITH_BUSINESS_OWNER

durability:
  sourceAckAfterDurableCommit: required
  inbox: relational-database
  businessEffect: unique-constraint-and-transaction
  outbox: same-transaction-as-domain
  archiveAfterCompletion: required

outbound:
  kafka:
    stableEventId: required
    consumerIdempotency: required
    commitPolicy: REVIEW_CONTAINER_CONFIGURATION
  logisticsHttp:
    stableIdempotencyKey: shipment-request-id
    partnerKeyTtl: REVIEW_WITH_PARTNER
    ambiguousOutcome: RECONCILE_BEFORE_RESEND

restartRecovery:
  lease: required
  fencingOrTargetIdempotency: required
  staleClaimScan: required
  unknownOutcomeQueue: required
  replayAudit: required
  rateLimitAfterOutage: required

observability:
  duplicateNoopRate: required
  sameKeyPayloadConflictRate: required
  inboxStaleAge: required
  outboxPendingAge: required
  unknownOutcomeAge: required
  businessCompletionLatency: required

testing:
  crashWindowTestsPassed: PENDING
  twoReplicaDuplicateTestsPassed: PENDING
  remoteSideEffectTestsPassed: PENDING
  replayAndRollbackTestsPassed: PENDING

approval:
  technicalOwner: PENDING
  businessOwner: PENDING
  securityOwner: PENDING
  operationsOwner: PENDING
~~~

All `REVIEW_...` and `PENDING` items must be resolved; the form does not replace implementing these mechanisms in code or broker/adapter configurations.

### 26.1. Go/No-Go Gate

| Status | Criteria |
|---|---|
| **GO** | Crash windows, concurrent duplicates, durable acks, and outbound reconciliation tested with evidence |
| **GO WITH EXCEPTION** | Exception has approved owner, expiration, impact bounds, and mitigations |
| **HOLD / RETEST** | Missing restart/rollback tests, unverified retention, or unclear container ack semantics |
| **NO-GO** | Message loss post-ack, uncontrolled duplicate side effects, unknown remote outcomes, or bypassed security |

### 26.2. Final Pre-Go-Live Checklist

- [ ] Diagram documents durable boundaries, source acks/offsets, and business/outbox transactions.
- [ ] Stable keys + payload fingerprints and same-key/different-payload policy are clear.
- [ ] Domain unique constraints block concurrent worker races.
- [ ] Dedupe markers and business updates commit in one transaction when sharing a DB.
- [ ] Metadata filters never equate "accepted" with "processed".
- [ ] In-memory `QueueChannel`/`ExecutorChannel` are never treated as durable.
- [ ] Recovery scans catch File/SFTP items accepted yet incomplete.
- [ ] HTTP inbound returns Accepted only after durable handoff.
- [ ] JMS/AMQP/Kafka redeliveries tested after business commit before ack.
- [ ] Outbox event IDs are stable; publisher/consumer idempotency covers proper scopes.
- [ ] Unknown outcomes follow reconciliation/approval rather than blind retries.
- [ ] Claims/leases/fencing/recovery fit multi-replica deployments.
- [ ] Dedupe retention outlives replay windows or falls back to authoritative state.
- [ ] Rolling deploys and DR backup restores are accounted for.
- [ ] Logs/metrics/alerts, replay runbooks, incident owners, and security controls exist.
- [ ] P0 test cases pass with zero business loss/duplication blockers.

## 27. Anti-Patterns to Avoid

**"Accept-once filter means processed once."** Filters typically only know a file/message was seen; they do not prove DB/HTTP side effects committed.

**"Write processed key first, then process."** If the marker commits early and the worker crashes, unprocessed messages can be skipped forever. Tie markers to business transactions or recoverable state-machine leases.

**"SELECT to check if key exists, then INSERT is enough."** Two workers can both SELECT false; enforce unique constraints/atomic claims with proper transaction isolation.

**"Use `MessageHeaders.ID` as the business key."** Recreated messages after restarts carry different IDs. Use stable business/event IDs.

**"HTTP timeout means request didn't execute."** The partner may have committed; enforce remote idempotency/lookups/reconciliation.

**"Kafka exactly-once automatically protects the database."** Kafka transactions/idempotent producers are scoped to Kafka and do not encompass external DB/HTTP/SFTP.

**"JMS/AMQP ack modes prevent duplicates."** Crashes after DB commit before ack still trigger redelivery; consumers must be idempotent.

**"Swap `eventId` on replay to force reprocessing."** Breaks deduplication and risks duplicate effects; when a business adjustment is needed, issue a **new versioned, approved business action** instead of disguising an old duplicate as a new event.

**"Leases grant absolute exclusivity."** Stale workers can keep running after lease expiry; pair with fencing or target-side idempotency.

**"Outbox guarantees publishing exactly once."** Succeeding at publish before dying prior to marking `SENT` can trigger a resend; receivers must dedupe.

**"Wiping metadata stores after deploy gives a clean start."** Triggers mass replays and duplicates; store changes require migrations and reconciliation.

**"Short retention saves DB space."** Risks expiring dedupe windows before Kafka replays or manual DLQ handling; size retention to business contracts.

**"Test only graceful shutdown."** OOMs, `SIGKILL`, and power loss skip cleanup hooks; test hard crashes.

**"One `PROCESSED` flag for an entire file is enough."** Batched file processing needs per-row/checkpoint tracking and partial-success recovery across mid-file restarts.

**"Track only idempotency keys without checking payloads."** Same-key/different-payload hides mutated data or producer bugs.

**"Restore backup then restart consumers immediately."** Backups can lack processed keys for events that already hit external targets; DR requires reconciliation before replay.

**"Duplicate count must be 0."** Under at-least-once delivery, duplicate deliveries can be normal; the goal is **duplicate business effect = 0** within contract scope.

## 28. Review Questions and Reference Material

### 28.1. Self-Check Questions

1. Why do restarts cause duplicates even when a broker stores only one record?
2. How do "file polled" and "business processed" differ?
3. Which crash window loses messages if upstream acks prematurely?
4. Which crash window triggers redelivery if the DB commits before source ack?
5. Why is `MessageHeaders.ID` not a default business idempotency key?
6. When the same key arrives with a different payload, should you return `ALREADY_PROCESSED`?
7. Which race condition does a unique constraint solve that SELECT-before-INSERT cannot?
8. Why should dedupe markers commit alongside business mutations when sharing a database?
9. How do inbox and outbox differ in purpose and flow position?
10. Does an outbox completely eliminate duplicate Kafka publishes?
11. Why can a persistent file filter still cause missed business processing after a restart?
12. Does `IdempotentReceiverInterceptor` automatically roll back HTTP side effects on handler errors?
13. When an SFTP remote file has been downloaded but DB hasn't committed, what does recovery do?
14. For a succeeded HTTP POST with a lost response, why might retrying the same ID still fail if remote TTL expired?
15. How does JMS/AMQP redelivery occur after DB commit before ack?
16. Should Kafka offsets serve as business dedupe keys for an event crossing multiple topics?
17. When a Kafka retry topic breaks revision order, how should business logic handle it?
18. When a JDBC lease expires while an old worker keeps running, what role does fencing play?
19. Why isn't an in-memory `QueueChannel` a durable handoff?
20. If HTTP returns 202 before durable inbox persistence, what can a restart do?
21. Which metrics prove multiple deliveries yielded only one business effect?
22. When ledger retention expires before the source replay window, what risk arises?
23. When upgrading canonicalization, why can false conflicts appear?
24. When restoring an older backup, why must you reconcile before resuming Kafka/file pollers?
25. What must a safe replay runbook verify regarding side effects, business versions, and authorization?

**Hint:** For each question, trace **source identity → durable ingest → transaction commit → ack/checkpoint → outbound delivery → recovery** and ask: "if the pod dies right here, where will this event reappear and how will it be handled?".

### 28.2. Glossary

| Term | Meaning |
|---|---|
| **Idempotency** | Repeating the same request without creating duplicate business effects beyond contract |
| **Stable business key** | Key remaining invariant across retries, restarts, and replays |
| **Payload fingerprint** | Semantic content digest used to detect conflicts |
| **Deduplication ledger** | Durable record of processed logical events/operations |
| **Durable boundary** | Point where data/obligations are persisted safely enough to recover |
| **Inbox** | Durable intake record enabling recoverable processing |
| **Outbox** | Publish/command obligation written in the same transaction as business changes |
| **At-least-once delivery** | Messages may redeliver prior to source acknowledgement |
| **Ack / offset commit** | Confirmation to source or processed-position marker |
| **`MetadataStore`** | Store backing integration component state |
| **Accept-once filter** | Mechanism limiting re-intake of items per filter criteria |
| **`IdempotentReceiverInterceptor`** | Interceptor identifying duplicates via a message selector |
| **Lease / fencing token** | Time-bounded claim / guard rejecting stale workers |
| **Unknown outcome** | Uncertain whether a remote operation succeeded |
| **DLQ / DLT / quarantine** | Isolation store for messages unprocessable on the normal path |
| **Reconciliation** | Verifying actual state across sources, DBs, brokers, and partners |
| **Replay** | Re-driving existing data for processing/recovery |
| **Graceful shutdown** | Halting new intake and draining inflight work cleanly |
| **Disaster recovery** | Recovery after data/infrastructure loss, potentially requiring ledger rebuilds |

### 28.3. Version-Specific Reference Documentation

- **Spring Integration Reference Guide:** Idempotent Receiver, `IdempotentReceiverInterceptor`, `MetadataStoreSelector`, File/SFTP persistent filters, Message Channels, Polling Consumer, Error Handling, Message Stores, and Endpoint Lifecycle.
- **Spring Framework / Spring Boot Reference:** Transaction Management, JDBC, declarative `@Transactional`, lifecycle, Actuator/Micrometer, graceful shutdown.
- **Spring for Apache Kafka Reference and Apache Kafka docs:** Consumer offsets/ack modes, error handling, DLT/retry topics, producer idempotence, and Kafka-scoped transactional semantics.
- **Spring AMQP / RabbitMQ Reference:** Acknowledgement, redelivery, DLX/DLQ, publisher confirms, and listener recovery.
- **Jakarta Messaging / JMS specification and broker provider docs:** Sessions, acknowledgement, transactions, durable queues, redelivery, and DLQ.
- **PostgreSQL docs or database vendor docs:** Transactions, unique constraints, `ON CONFLICT`, isolation, row locking, `SKIP LOCKED`, and concurrency.
- **Partner HTTP API contracts:** Idempotency key TTLs, status lookups, response semantics, retries, and side-effect receipts.
- **SFTP/SSH client and server docs:** Accept-once metadata, host-key verification, rename/ready protocols, transfer integrity, and file retention.

**Conclusion:** "Idempotent across restarts" does not mean a message is sent or received only once. It means the system can **re-receive, check durable state, and finish any remaining obligations without repeating business effects**. In Spring Integration Adapters, place idempotency at the right layer, commit business state and ledgers inside proper transactions, use inboxes/outboxes at system boundaries, treat acks/offsets/filters purely as source-side progress, and prove everything with crash tests, reconciliation, and runbooks before production.
