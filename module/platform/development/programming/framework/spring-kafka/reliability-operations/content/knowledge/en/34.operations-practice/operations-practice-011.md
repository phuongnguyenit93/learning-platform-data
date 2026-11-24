# Writing a DLT Replay Runbook in Spring Kafka Reliability Operations

## 1. Objective: Returning Failed Records to Processing Under Control

In a Spring Kafka application, a consumer can encounter messages that still fail after exhausting allowed retries. Rather than blocking a partition indefinitely, the application typically routes those messages to a **Dead Letter Topic (DLT)** to preserve failure evidence and allow later recovery. A DLT may accumulate thousands of records from many different causes, yet **not every record should be replayed right away**.

Example:

~~~text
orders.events
     |
     v
@KafkaListener
     |
     +-- Processing succeeds --> Database / downstream events
     |
     +-- Transient error --> Bounded retry
                               |
                               +-- Recovers --> Continue processing
                               |
                               +-- Retries exhausted --> orders.events.DLT
                                                             |
                                                             v
                                                      Triage + fix root cause
                                                             |
                                                             v
                                                      Controlled replay
                                                             |
                                                             v
                                                  Consumer reprocesses + reconcile
~~~

**DLT replay** means reading a selected set of records from a DLT and republishing them to an approved processing destination (typically the original topic or a dedicated recovery topic). Done carelessly, this operation can create duplicate messages, invert business ordering, reintroduce poison pills, send schema-incompatible payloads, or overload consumers.

A runbook is an **actionable operator guide**: it specifies preconditions, approvals, exact actions, stop thresholds, verification evidence, and recovery steps if the replay itself fails. It is far more than a snippet showing how to run a single CLI command.

Practice objectives:

1. Classify why records entered the DLT and select only replay-eligible records.
2. Scope selections precisely by **topic, partition, and offset**, never replaying indiscriminately.
3. Verify **payloads, schemas, keys, headers, retention, and ordering** before republishing.
4. Enforce **idempotency**, rate limits, stop switches, and auditing.
5. Execute **dry-run → canary → bounded batch replay → reconciliation**.
6. Understand what Kafka guarantees vs. what must still be verified in databases and external side effects.
7. Design tests and incident responses around observable criteria.

Examples follow **Spring Kafka 3.x** conventions, Kafka Java clients, and Java 17. Version-dependent APIs, DLT settings, and CLI flags must be verified against your live release before operating in production.

## 2. Distinguishing DLT, Retry Topic, Quarantine, and Source Topic

Different systems use similar acronyms with different meanings. Confirm the actual topology before selecting a replay target.

| Component | Role | Should You Replay Directly Into It? |
|---|---|---|
| **Source topic** | Main business event stream | Possible, after evaluating consumer contracts |
| **Retry topic** | Temporarily holds events for scheduled/backoff retries | Usually framework-managed; do not inject manually unless topology is clear |
| **Dead Letter Topic** | Stores events unrecoverable under retry/recovery policy | Source for triage and controlled replay |
| **Recovery topic** | Dedicated topic for reprocessing via a tested pipeline | Often safer when traffic isolation is needed |
| **Quarantine store** | Access-controlled store holding failing payloads with audit & retention | Usually needs a dedicated recovery tool; not a Kafka topic by default |
| **Audit / replay ledger** | Records which items were selected, sent, and verified | Not a business event source |

In Spring Kafka, DLTs can be wired via **`DeadLetterPublishingRecoverer`**, **`DefaultErrorHandler`**, **`@RetryableTopic`**, or custom resolvers. Naming and partition routing do not automatically follow `<source>.DLT` in every project.

For example:

~~~text
orders.events
orders.events-retry-1000
orders.events-retry-10000
orders.events-dlt
~~~

The names above illustrate a retry-topic topology. Another project may use:

~~~text
orders.events
orders.events.DLT
~~~

**Never guess topic or partition names from habit.** Inspect the actual recoverer config, destination resolver, listener container, topic provisioning, and ACLs of the deployed service.

### What Does Being in the DLT Mean?

Usually it means **the consumer chose to route the message to an error stream** after failing to process it under policy. It **does not prove**:

- The payload was preserved verbatim across every error path.
- Whether the message partially succeeded earlier.
- That the DLT producer committed safely if a crash hit mid-recovery.
- That the source consumer offset committed in every scenario.
- That the underlying bug has been fixed.
- That replaying it will execute strictly once.

Inspect DLT records, consumer group offsets, actual DB/downstream state, and the recoverer configuration together.

## 3. A Sample Incident to Anchor the Runbook

Suppose the **orders-worker** service consumes **orders.events** and updates order state in a database:

~~~text
Source topic:      orders.events
Dead letter topic: orders.events.DLT
Consumer group:    orders-worker-v1
Recovery target:   orders.events
Business key:      orderId
Event ID:          eventId
~~~

During a prolonged database outage, the listener retried a few times and routed unprocessable messages to the DLT. Once the database recovered, failed records remained in the DLT.

Operational goal:

~~~text
Incident: INC-KAFKA-2026-015 (example)
Scope:    15 verified records in DLT
Cause:    transient database unavailability
Fix:      DB connections restored, health checks and integration tests passing
Action:   bounded replay to approved recovery target
Exit:     all 15 events processed or each exception documented
~~~

Names, counts, and the incident ID are **illustrative data**. Real runbooks must be populated from live environment evidence—never run production commands with placeholder offsets or keys.

### Technical Goal vs. Business Goal

**Technical goal:** replay producer sent records, broker ACKed them, recovery consumer received them.

**Business goal:** the right orders updated accurately; zero duplicate payments, inventory reservations, emails, or DB rows; zero valid events dropped; final state passes reconciliation contracts.

Close a runbook only when the business goal passes or approved exceptions are logged.

## 4. Mandatory Safety Principles

Before taking action, agree on these invariants:

1. **Never auto-replay the entire DLT** the moment an error appears.
2. **Never replay before proving the root cause is fixed** or a compatible new handling path exists.
3. **Never assume a DLT record caused zero side effects.** The handler may have written to a DB/API before failing.
4. **Never trust message headers as authority to pick destination topics.** Target topics require an operator allowlist.
5. **Never mutate business keys, `eventId`, or schemas recklessly** during replay.
6. **Never dump sensitive payloads to tickets, logs, or consoles**; use secure references and access-controlled storage.
7. **Never equate producer ACK with downstream processing success.**
8. **Never promise exactly-once purely from a replay tool.** Account for idempotency and ambiguous commit outcomes.
9. **Never reset source consumer group offsets** as a substitute for DLT replay.
10. **Require approval, count caps, rate limits, stop thresholds, and a recovery plan.**
11. **Maintain an immutable audit trail** recording source, target, scope, operator, timestamps, and outcomes.
12. **Touch production only under an approved change or incident procedure.**

DLT replay can trigger **new business side effects**. Execution permissions should be separated from read-only lag/metadata access where environments require least privilege.

## 5. Mandatory Fields in a Runbook Execution Record

Each replay run should carry a unique **Replay Operation ID** and explicit approval record:

| Field | What to Record |
|---|---|
| `incidentId` | Incident or change ticket |
| `replayOperationId` | Unique ID for this replay run; kept stable if the command retries |
| `service / owner` | Owning service and accountable engineer |
| `environment / cluster` | Production/staging and Kafka cluster alias |
| `sourceDLT` | Actual topic holding failed records |
| `targetTopic` | Approved destination topic |
| `partitions / offsets` | Exact tuple list or snapshotted range |
| `inputWindow` | Incident time window to aid triage |
| `rootCause` | Identified root cause and evidence |
| `fixEvidence` | PR, release, config, DB health, and tests confirming the fix |
| `schemaVersion` | Payload format and compatibility status |
| `idempotencyPlan` | Business key, `eventId`, dedup store, and ambiguous-commit handling |
| `expectedCount` | Approved record count and reasons for exclusions |
| `maxRate` | Caps on messages/s, bytes/s, or in-flight requests |
| `canaryScope` | Small initial record set, explicitly chosen |
| `stopConditions` | Automatic or operator-triggered abort criteria |
| `approval` | Approver identity and timestamp |
| `reconciliation` | Final data verification check |
| `auditLocation` | Secure storage location for evidence |

Example operational manifest:

~~~yaml
incidentId: INC-KAFKA-2026-015
replayOperationId: REPLAY-2026-015-A
environment: production
clusterAlias: prod-kafka-a
service: orders-worker
sourceTopic: orders.events.DLT
targetTopic: orders.events

selection:
  - partition: 0
    offsets: [3811, 3812]
  - partition: 2
    offsets: [9024]

expectedSelectedCount: 3
dryRunRequired: true
canaryCount: 1
maxMessagesPerSecond: 2
maxInFlight: 1

rootCause: DB_CONNECTION_TIMEOUT
fixEvidence: CHG-2026-092
idempotencyPolicy: orders-event-id-v2
schemaCompatibility: VERIFIED
approvalStatus: APPROVED
~~~

This is a **workflow specification manifest**, not a native format executed directly by Spring Kafka or the Kafka CLI. Any replay tool needs its own schema/validator and must never treat the mere string `APPROVED` in a user-supplied file as authorization.

### When Selecting by Range

If selecting partition 0, offsets 3811 to 3850: specify whether bounds are **inclusive** or **exclusive**, snapshot the high watermark / last stable offset at selection time, and record the actual readable count. Kafka offsets are not a contiguous sequence of business records because aborted transactions, retention, and control markers leave gaps.

For high-assurance runs, an approved **explicit list of `(topic, partition, offset)` tuples** is safer than a broad uninspected range.

## 6. Phase 0 — Activation, Ownership, and Stop Conditions

Before launching any replay tool:

1. Have an incident/change ID and an assigned operator.
2. Confirm exact Kafka cluster, namespace, consumer group, and environment.
3. Verify read access on the DLT, write access on the target, metric visibility, and business output lookup access.
4. Confirm **no other replayer is running against the same scope**; use a lock, lease, or coordination guard.
5. Pause any auto-replayer targeting that scope if it would collide with manual replay.
6. Capture baseline system state and identify who signs off on final verification.
7. Prepare an instant stop/suspend switch if consumers or downstreams throw errors.

Sample **stop conditions**:

- Processing error rate or new DLT rate exceeds approved threshold.
- Duplicate business side effect detected.
- Producer timeouts or ambiguous transaction commit outcomes exceed threshold.
- Consumer lag climbs steadily without matching throughput.
- Schema/deserialization errors recur.
- Database latency or connection pool nears saturation.
- Sent count exceeds `selectedCount` or hits an unapproved topic/partition.
- Audit ledger or metrics pipeline stops recording, blinding progress checks.

Tune thresholds to service SLAs and production traffic. Never apply one static `maxRate` across every topic.

## 7. Phase 1 — Triaging Why Records Entered the DLT

**Replaying before fixing the root cause** typically sends records straight back into the DLT.

| Failure Category | Example | Action Before Replay |
|---|---|---|
| **TRANSIENT_DEPENDENCY** | DB/API temporarily down, timeout | Confirm dependency stabilized and rate fits capacity |
| **RATE_LIMIT** | HTTP 429 from downstream | Respect `Retry-After`, quotas/backoff; lower replay rate |
| **DESERIALIZATION** | Unparseable payload, schema mismatch | Fix serializer/schema or apply approved conversion/quarantine |
| **VALIDATION** | Missing fields, invalid business data | Fix data under an audited workflow; never blindly replay |
| **APPLICATION_BUG** | `NullPointerException` or logic defect | Deploy fix and run regression test on matching payload |
| **AUTHORIZATION** | Invalid ACL, token, or cert | Fix permissions/certs and verify scopes |
| **POISON_MESSAGE** | Record always throws | Quarantine, patch, or skip/reject per contract |
| **OUT_OF_ORDER** | Stale event arrives after newer state | Evaluate version/sequence; may be ineligible for replay |
| **DUPLICATE** | Event already applied before DLT routing | Reconcile and deduplicate; do not trigger a second side effect |
| **UNKNOWN** | Insufficient exception/broker evidence | Halt; never replay by guessing |

**Never assume a single DLT holds only one error type.** Multiple incidents can overlap inside the retention window. A topic-wide blind replay can mix transient failures with schema breaks and permanent business errors.

### Triage Data Sources

- Consumer logs/traces carrying **exception category**, `eventId`, or source offset.
- Headers written by Spring Kafka's recovery mechanism.
- Metrics for exhausted retries, DLT publish rate, and rebalances.
- Consumer group committed offsets and deployment/version history.
- Schema registry and migration history.
- Database or downstream receipts keyed by `eventId`.
- Replay audit logs from prior runs.

Never paste raw exceptions or full payloads into widely readable tickets. Reference protected storage and grant access only when needed.

## 8. Understanding Spring Kafka DLT Metadata Accurately

**`DeadLetterPublishingRecoverer`** can attach headers describing the original record and failure:

- Original topic.
- Original partition and offset.
- Original consumer group (in supported versions/configurations).
- Original record timestamp.
- Exception class, message, stack trace, or failure metadata.

In code, Spring Kafka defines constants such as **`KafkaHeaders.DLT_ORIGINAL_TOPIC`**, **`DLT_ORIGINAL_PARTITION`**, **`DLT_ORIGINAL_OFFSET`**, and exception headers; **exact names and encodings depend on version and recoverer config**.

Example observed structure:

~~~text
DLT topic:        orders.events.DLT
DLT partition:    2
DLT offset:       9024
Kafka key:        O101
Original topic:   orders.events
Original partition: 2
Original offset:  6201
Failure category: DB_CONNECTION_TIMEOUT
~~~

This is a conceptual metadata view, not a raw header dump. Several headers such as original partition and offset are **binary-encoded per framework representation**—never convert them blindly to UTF-8 strings and parse integers.

**DLT tuple** and **original tuple** are two distinct coordinates:

~~~text
Source record:
  orders.events / partition=2 / offset=6201

Failed copy:
  orders.events.DLT / partition=2 / offset=9024
~~~

To fetch a DLT record, **use the DLT's own tuple**. Original topic/partition/offset trace back to the initial event, not the DLT copy's location.

### Headers May Be Missing or Contain Sensitive Data

Not every DLT record carries all headers. Custom recoverers that omit original offsets, or records passing through multiple retry topics, can alter header sets.

Exception headers may contain raw input, tokens, PII, or SQL details. Never copy them back to the source topic by default. Retain only application headers needed by deserializers and business logic; handle DLT/recovery-specific headers per policy.

**Never treat the `original-topic` header value as an arbitrary routing destination.** Message headers are untrusted data, not authoritative operational commands.

## 9. Phase 2 — Inventorying the DLT and Freezing Scope

Inventory using internal tools, `AdminClient`, and metadata consumers. Record:

- Topic/partition/offset of each DLT record.
- Key usable for reconciliation, per security policy.
- `eventId`, schema ID/version, or type headers if present.
- Original topic/partition/offset where trustworthy.
- Exception category and prior replay attempt count.
- Record timestamp and remaining retention window.
- Current downstream state: already applied or not.

### Kafka CLI Commands for Topics and Groups

Read-only examples:

~~~bash
# Inspect DLT partitions, replicas, and ISR.
kafka-topics.sh \
  --bootstrap-server kafka-prod-a:9092 \
  --describe \
  --topic orders.events.DLT

# Inspect source consumer group lag and offsets.
kafka-consumer-groups.sh \
  --bootstrap-server kafka-prod-a:9092 \
  --describe \
  --group orders-worker-v1

# Inspect topic retention / cleanup policies.
kafka-configs.sh \
  --bootstrap-server kafka-prod-a:9092 \
  --entity-type topics \
  --entity-name orders.events.DLT \
  --describe
~~~

These commands apply to compatible Kafka CLI releases. On SASL/TLS clusters, supply approved client configuration files per organizational guidelines; never hardcode passwords into shell history.

**`kafka-configs.sh --describe`** does not always display every effective cluster default. To confirm effective retention/cleanup when not overridden, query effective configs via `AdminClient` or authorized governance tooling.

### Never Dump the Entire DLT to a Shared Terminal with Console Consumer

Anti-pattern:

~~~bash
# Do not run blindly in production:
kafka-console-consumer.sh \
  --bootstrap-server kafka-prod-a:9092 \
  --topic orders.events.DLT \
  --from-beginning
~~~

This can print **sensitive payloads**, flood terminals, and mix unrelated incidents. Nor does it produce a verified tuple manifest or preserve headers/schemas if piped into a producer.

Use read-only tools supporting **exact offset seeking, byte limits, redaction, and allowlisted metadata export**.

### Snapshotting Scope

A DLT is a live, changing log. When choosing "all currently present records," capture **end offsets / last stable offsets** per partition and bound reads accordingly. New DLT records arriving mid-replay **do not automatically belong to the active replay batch**.

On compacted or short-retention topics, a selected record can expire before execution. If an approved offset is unreadable, report **`SOURCE_NOT_AVAILABLE`** rather than silently substituting the next record to hit a target count.

## 10. Choosing Replay Target and Handling Strategy

Four common strategies:

| Strategy | When Appropriate | Risks to Manage |
|---|---|---|
| **Replay to source topic** | Root cause fixed, source consumer handles it, ordering allows | Arrives after newer events, duplicate side effects, DLT loop |
| **Replay to recovery topic** | Dedicated consumer group, load isolation, or testing a new version | Different routing/schemas; clear ownership required |
| **Transform then replay** | Older payload needs approved migration | Changes semantics; retain original and transformation audit |
| **Quarantine / do not replay** | Poison data, obsolete events, already applied, lacking evidence | Requires business/audit sign-off to prevent silent data loss |

### Replaying to the Source Topic Does Not "Turn Back Time"

Kafka appends replayed records at **brand-new offsets**. A replayed event can land after newer events for the same order.

~~~text
Original:
  order O101 v1 (failed -> DLT)
  order O101 v2 (processed)

Replay v1 later:
  order O101 v1 (new Kafka offset)
~~~

If consumers overwrite state in arrival order without version checks, `v1` can **overwrite newer state**. In event-sourced systems or state machines, evaluate **event sequence/version, current business state, and stale-event policy**.

### When Preserving Partitions Matters

Kafka producers can target an explicit partition or let the partitioner hash by key. Hardcoding **original partition** is dangerous if:

- The source topic changed partition counts or the target is a different topic.
- Key serializers or partitioners changed.
- The DLT partition layout differs from the source topic.
- Replay traffic needs redistribution across a recovery pipeline.

Runbooks must state the **partition routing policy**. With stable keys and an unchanged source topic, letting the producer hash keys with a tested partitioner preserves key routing—yet never assume historical log ordering is restored.

## 11. Schemas, Serializers, and Raw Bytes

Kafka records do not inherently carry Java class names. Payloads may be JSON, Avro, Protobuf, String, or custom binary formats. With **`ErrorHandlingDeserializer`**, deserialization error details and raw payloads enter recovery according to your Spring Kafka version and recoverer configuration.

Crucially, **a DLT copy does not always carry a deserialized domain object**. Often you should handle raw **`byte[]`** so another serializer does not mutate payload bytes during replay.

### Checklist to Verify

1. Key and value serializers used by the source producer.
2. Record format **inside the DLT**: bytes, String, JSON, Avro, etc.
3. Schema IDs or type headers required by target consumers to deserialize.
4. Schema Registry subject naming strategy: it may depend on topic name.
5. Whether current consumers still support older record schemas.
6. Which custom headers are business contract vs. recoverer metadata.
7. Whether transformation/migration is required and who approves it.

For Avro payloads with Schema Registry, copying `byte[]` preserves the embedded schema ID, yet target consumers still need registry access and compatible schemas. Changing **target topics** can interact with subject naming strategies; never assume raw `byte[]` copying is universally safe without confirming the wire format.

### Tombstones (`null` Values) Are Not Ordinary Failed Records

In compacted topics, records with **`value=null`** signify logical key deletion. Replaying an old tombstone onto a topic holding newer state can make downstream delete live data.

Runbooks must separate tombstones, confirm validity against business sequences, and require explicit approval before replaying.

### Allowlisting Headers

You may need to preserve **`eventId`**, **`schemaVersion`**, **`content-type`**, or consumer-required type headers. Never resend full DLT exception stack-trace headers. Also avoid injecting custom replay headers that break consumers enforcing strict header allowlists.

## 12. Idempotency: The Prerequisite for Safe Replay

A Kafka producer may receive an ACK when appending a replayed record, or lose network connectivity right as the ACK returns, leaving the operator unsure whether the send succeeded. Rerunning the command can emit the event twice.

~~~text
DLT replayer sends event E101
              |
              v
Kafka broker appended event
              |
              v
ACK lost / process crashes
              |
              v
Operator retries same replay request
              |
              v
Duplicate event E101 possible
~~~

Kafka producer idempotence handles certain producer-internal retries within the same session and partition per Kafka semantics; **it does not prevent duplicates when an operator re-runs a fresh replay invocation**.

### Business Idempotency Keys

Prefer a stable identifier from the original event:

~~~text
eventId = E101
orderId = O101
operation = APPLY_ORDER_STATUS
~~~

Example deduplication table:

~~~sql
CREATE TABLE processed_event (
    consumer_name VARCHAR(100) NOT NULL,
    event_id      VARCHAR(100) NOT NULL,
    processed_at  TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Inside the handler's database transaction, insert the dedup key and apply business changes atomically so a rollback reverts both. Unique keys prevent applying the same `eventId` repeatedly per contract, alongside explicit rules when `eventId` is missing or identical IDs carry conflicting payloads.

Never use the **DLT offset** as a business idempotency key because replaying creates a new record with a new offset. Never mint a new `eventId` for the same business event during replay if downstream deduplication depends on it.

### When Side Effects Leave the Database

If the handler calls:

- A payment API.
- An inventory reservation API.
- An email/SMS gateway.
- An external REST service.

then a database dedup marker alone cannot prevent duplicating an already-committed remote call whose response was lost. Use remote service idempotency keys, receipt lookups, outboxes, or compensation/reconciliation.

**Never replay in production if duplicate-side-effect risks lack approved controls.**

## 13. Replay Ledger: Tracking Every Record

Auditing should distinguish **selected**, **sending**, **Kafka ACKed**, and **downstream business verified**.

Illustrative schema:

~~~sql
CREATE TABLE dlt_replay_ledger (
    operation_id       VARCHAR(100) NOT NULL,
    source_topic       VARCHAR(250) NOT NULL,
    source_partition   INTEGER NOT NULL,
    source_offset      BIGINT NOT NULL,
    target_topic       VARCHAR(250) NOT NULL,
    event_ref          VARCHAR(150),
    state              VARCHAR(40) NOT NULL,
    attempt_count      INTEGER NOT NULL,
    target_partition   INTEGER,
    target_offset      BIGINT,
    updated_at         TIMESTAMP NOT NULL,
    PRIMARY KEY (
        operation_id, source_topic, source_partition, source_offset
    )
);
~~~

Suggested state transitions:

~~~text
SELECTED
    |
    v
VALIDATED
    |
    v
READY
    |
    v
SENDING
    |
    +--> SEND_FAILED / COMMIT_UNCONFIRMED
    |
    v
SENT_ACKED
    |
    v
DOWNSTREAM_VERIFIED
    |
    v
CLOSED
~~~

This is an audit model, not a built-in Spring Kafka state machine. When ledger updates and Kafka sends span **two different transactional resources**, a gap remains:

~~~text
Kafka append succeeds
       |
       v
Process crashes before ledger updates to SENT_ACKED
~~~

Thus a ledger does not automatically make replay exactly-once. For ambiguous states, use **`eventId`/business reconciliation** to decide whether to retry; handle **`COMMIT_UNCONFIRMED`** states transparently.

### Keep `replayOperationId` Stable

If an operator reruns **the same replay batch** after a failure, never mint a new `replayOperationId` just to bypass the ledger or lock. Operation IDs track the audit run; **business `eventId`s** prevent double application downstream.

## 14. Phase 3 — Preflight Checks Before Sending a Single Record

Preflight must verify both system health and data eligibility.

### 14.1. Verify the Root Cause Is Resolved

- Code or config fixes deployed to the target environment.
- Database/API dependencies stable over a meaningful observation window.
- Auth/ACL/schema issues fixed.
- Regression test for **that exact failure category** passing.
- Current retry/DLT handler will not trigger a new loop.

### 14.2. Verify Scope and Data

- Approved list of source DLT topic/partition/offsets exists.
- Records still exist within retention/compaction bounds.
- Event IDs, keys, schemas, and headers fit the target contract.
- Tombstones, stale events, and conflicts separated from the list.
- Downstream state checked for duplicate-execution risk.
- Expected count and reconciliation query defined (not just offset counts).

### 14.3. Verify Resources

- Broker and target topic have healthy ISR and status.
- Consumer lag, error rates, throughput, and DB connection pools have headroom.
- Replay producer has `WRITE` ACL on target; reader has `READ` ACL on DLT.
- Backpressure, rate limits, and stop switches active.
- Audit ledger and monitoring operational.
- No concurrent auto-replayer running on the same scope.

If any critical check cannot be verified, mark **`BLOCKED/UNKNOWN`** rather than assuming preflight passed.

## 15. Phase 4 — Dry-Run Without Publishing to Kafka

A replay tool's dry-run must **never call `producer.send`**. Instead:

1. Read each record by approved tuple.
2. Confirm exact offsets exist.
3. Check key/value lengths, payload type, and schema compatibility.
4. Validate routing policy and approved target.
5. Run header filtering in memory to inspect retained headers.
6. Tally eligible, blocked, and unknown records.
7. Emit a **safe manifest/preview** without raw payloads.

Example report:

~~~json
{
  "operationId": "REPLAY-2026-015-A",
  "mode": "DRY_RUN",
  "selected": 15,
  "eligible": 12,
  "blocked": 2,
  "unknown": 1,
  "willSend": false,
  "targetTopic": "orders.events",
  "reasonSummary": {
    "TRANSIENT_DEPENDENCY": 12,
    "OUTDATED_EVENT": 2,
    "SCHEMA_NOT_VERIFIED": 1
  }
}
~~~

**Never force all 15 records into replay just to match `expectedCount=15`.** The two stale records and one unverified-schema record require separate handling.

Dry-runs should assert technically that **`producer invocation count = 0`**, not merely log a "dry run" string.

## 16. Phase 5 — Canary Replay with Selected Records

After dry-run approval:

1. Select one or a few representative records—preferring easily reconcilable, low-risk cases.
2. Record DLT tuples, business `eventId`s, and expected target behavior.
3. Replay with **`maxInFlight=1`** and a low rate.
4. Await Kafka send ACK or transaction commit per tool design.
5. Watch the consumer receive and process the record.
6. Query the database or downstream receipt to reconcile by business key.
7. Confirm new DLT arrivals do not spike from the canary itself.
8. Confirm no duplicates or stale-state overwrites occurred.
9. Proceed only after the accountable owner signs off on evidence.

If the canary fails, **STOP**. Never raise rates or expand scope to "see if it settles with more data."

### Canary Success Does Not Equal "Kafka ACKed the Message"

For example:

~~~text
Replay producer:
  sent + broker ACK

Target consumer:
  deserialization FAILED
  retry exhausted
  DLT again
~~~

A send ACK proves only that Kafka accepted the republished record per ACK config; it **does not prove the handler succeeded**. A canary passes only once business reconciliation or downstream receipts confirm success.

## 17. Phase 6 — Bounded Batch Replay

After canary sign-off, split eligible records into **small, deterministic batches**:

~~~text
Eligible manifest: 12 records
    |
    +-- Batch 1: 3 records -> verify
    |
    +-- Batch 2: 3 records -> verify
    |
    +-- Batch 3: 3 records -> verify
    |
    +-- Batch 4: 3 records -> verify
~~~

Guidelines:

- Enforce max rate, max in-flight, and total record caps.
- Pause between batches if errors, DLT arrivals, lag, or DB latency climb.
- Update the ledger by source tuple and `operationId`.
- Never pull in new DLT records arriving **after the snapshot**.
- Where per-business-key ordering applies, define grouping, sequencing, and routing rules.
- Never delete records from the DLT after sending; retention and compaction handle lifecycle separately.

### Backpressure Matters More Than High Replay Speed

A system recovering from an outage may still carry backlog on the source topic. Blasting 100,000 records/s during replay can trigger a second outage on consumers, databases, or external APIs.

Cap both **records/s and bytes/s** when payload sizes vary widely. For rate-limited downstream APIs, pace replay to real capacity to avoid throwing DLT traffic back into the same retry storm.

### Kafka Ordering

Even when replaying source offsets in ascending order, records append at **new offsets** on the target topic. If live producers are writing concurrently, relative order between replayed and live traffic is not preserved historically.

For versioned/sequenced events, consumers should reject or quarantine older events rather than blindly applying replays over newer state.

## 18. Example Single-Record Replay Helper in Spring Kafka

This section shows a **tightly scoped helper for runbook support**: read one exact DLT record by `(partition, offset)`, support dry-run, and publish to an allowlisted target. It illustrates core mechanics, **not a full production CLI**.

Design choices:

- Dedicated **`ConsumerFactory<byte[], byte[]>`** for DLT reading with `ByteArrayDeserializer`.
- Dedicated **`KafkaTemplate<byte[], byte[]>`** for replay with `ByteArraySerializer`.
- Consumer **`enable.auto.commit=false`**, **`isolation.level=read_committed`**.
- **`assign + seek`** to the exact source partition and offset.
- **Never commit DLT consumer group offsets** during manual tuple-based reads.
- **Never take destination topic from `original-topic` headers**.
- **Never copy all exception headers** to the target topic.
- **Never mutate event ID or key bytes**.

### 18.1. Replay Request

~~~java
package com.example.kafka.operations;

public record ReplayRequest(
        String incidentId,
        String operationId,
        String sourceTopic,
        int sourcePartition,
        long sourceOffset,
        String targetTopic,
        boolean dryRun) {
}
~~~

In production, requests must pass through **approval/authorization**, input schema validation, rate limiting, locking, and ledger persistence. Never let callers pass arbitrary target topics via HTTP query parameters.

### 18.2. Service Scoped to a Single DLT Tuple

~~~java
package com.example.kafka.operations;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Arrays;
import java.util.List;
import java.util.Set;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.TopicPartition;
import org.apache.kafka.common.header.Headers;
import org.apache.kafka.common.header.internals.RecordHeaders;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
public class SingleRecordDltReplayer {

    private static final Set<String> ALLOWED_HEADERS =
            Set.of("eventId", "schemaVersion", "content-type",
                   "__TypeId__");

    private final ConsumerFactory<byte[], byte[]> consumerFactory;
    private final KafkaTemplate<byte[], byte[]> replayTemplate;

    public SingleRecordDltReplayer(
            ConsumerFactory<byte[], byte[]> consumerFactory,
            KafkaTemplate<byte[], byte[]> replayTemplate) {
        this.consumerFactory = consumerFactory;
        this.replayTemplate = replayTemplate;
    }

    public String replayOne(ReplayRequest request) throws Exception {
        validateRequest(request);

        TopicPartition source = new TopicPartition(
                request.sourceTopic(), request.sourcePartition());

        try (Consumer<byte[], byte[]> consumer =
                consumerFactory.createConsumer()) {

            // Manual assignment: does not join group rebalancing.
            consumer.assign(List.of(source));
            consumer.seek(source, request.sourceOffset());

            var records = consumer.poll(Duration.ofSeconds(5));
            ConsumerRecord<byte[], byte[]> selected = null;

            for (var record : records.records(source)) {
                if (record.offset() == request.sourceOffset()) {
                    selected = record;
                    break;
                }
            }

            if (selected == null) {
                throw new IllegalStateException(
                        "SOURCE_OFFSET_NOT_AVAILABLE");
            }

            // Never log key/value or raw exception headers.
            if (request.dryRun()) {
                return "DRY_RUN_RECORD_VALIDATED";
            }

            Headers outgoingHeaders =
                    filterHeaders(selected.headers());
            outgoingHeaders.add(
                    "x-replay-operation-id",
                    request.operationId()
                            .getBytes(StandardCharsets.UTF_8));

            // partition=null: route by key/partitioner.
            // timestamp=null: let producer/broker assign timestamp.
            ProducerRecord<byte[], byte[]> outgoing =
                    new ProducerRecord<>(
                            request.targetTopic(),
                            null,
                            null,
                            selected.key(),
                            selected.value(),
                            outgoingHeaders);

            var sendResult =
                    replayTemplate.send(outgoing)
                            .get(15, TimeUnit.SECONDS);

            // Return ACK metadata to the audit layer.
            // NEVER treat this as downstream business success.
            return "SENT_ACKED:"
                    + sendResult.getRecordMetadata().partition()
                    + ":"
                    + sendResult.getRecordMetadata().offset();
        }
    }

    private void validateRequest(ReplayRequest request) {
        if (request == null
                || request.operationId() == null
                || request.operationId().isBlank()) {
            throw new IllegalArgumentException(
                    "INVALID_REPLAY_OPERATION");
        }

        if (request.sourcePartition() < 0
                || request.sourceOffset() < 0) {
            throw new IllegalArgumentException(
                    "INVALID_SOURCE_POSITION");
        }

        // Example strict allowlist for a single pipeline.
        if (!"orders.events.DLT".equals(request.sourceTopic())
                || !"orders.events".equals(request.targetTopic())) {
            throw new IllegalArgumentException(
                    "UNAPPROVED_TOPIC_MAPPING");
        }
    }

    private Headers filterHeaders(Headers sourceHeaders) {
        RecordHeaders result = new RecordHeaders();

        sourceHeaders.forEach(header -> {
            if (ALLOWED_HEADERS.contains(header.key())) {
                byte[] sourceValue = header.value();
                byte[] copy = sourceValue == null
                        ? null
                        : Arrays.copyOf(
                                sourceValue, sourceValue.length);
                result.add(header.key(), copy);
            }
        });

        return result;
    }
}
~~~

**Intentional limitations of this example:**

1. Each call selects **one offset**, never scanning an entire topic or range.
2. If the offset is absent from readable data, the helper **fails** rather than substituting the next record.
3. Source and target are restricted by a literal allowlist. Production tools should read approved mappings from governed policies.
4. The header allowlist is **illustrative only** and must match your application's serializer/header contract. Some stacks do not use `__TypeId__`; others need additional headers.
5. The injected producer must be a **dedicated byte-array `KafkaTemplate`** with proper security, bootstrap servers, and ACK settings—never reuse a business template serializing DTOs.
6. If `replayTemplate` is configured as transactional, the send must run inside an appropriate transaction scope; this example assumes a **non-transactional** template to focus on bounded replay.
7. Dry-run here checks only offset readability; a complete runbook also validates schemas, idempotency, downstream state, and approvals.
8. This snippet **omits an audit ledger, distributed lock, rate limiter, overall batch timeout, and CLI parser**. Never expose this raw service on a public endpoint for production operations.
9. Calling send and awaiting ACK does not form an atomic transaction with the replay ledger or downstream processing.

### 18.3. Dedicated Byte-Array Client Configuration

Illustrative Kafka client properties:

~~~properties
# DLT reader
key.deserializer=org.apache.kafka.common.serialization.ByteArrayDeserializer
value.deserializer=org.apache.kafka.common.serialization.ByteArrayDeserializer
enable.auto.commit=false
isolation.level=read_committed

# Replay producer
key.serializer=org.apache.kafka.common.serialization.ByteArraySerializer
value.serializer=org.apache.kafka.common.serialization.ByteArraySerializer
acks=all
enable.idempotence=true
~~~

Build `ConsumerFactory` and `ProducerFactory` from **securely injected bootstrap servers and security settings**. Never embed SASL passwords or tokens in source files. With transactional DLTs or source records, `read_committed` prevents replaying records from aborted transactions.

**Byte-array replay does not automatically prove schema compatibility.** It merely avoids unnecessary deserialization/reserialization; verify business compatibility separately.

## 19. Why Not Use a `@KafkaListener` That Auto-Replays Every DLT Record?

A dangerous pattern:

~~~java
@KafkaListener(topics = "orders.events.DLT",
        groupId = "dlt-auto-replay")
public void replay(String payload) {
    kafkaTemplate.send("orders.events", payload);
}
~~~

Problems:

- Consumes **every new DLT record** even before the underlying bug is fixed.
- No incident or offset selection.
- Strips keys, headers, and original serialization.
- Zero approvals, dry-runs, canaries, or business state checks.
- Easily forms an infinite **`original → DLT → original → DLT`** loop.
- If the replay listener commits its offset while send outcomes are unclear, recovery becomes hard to reconcile.

If an automated DLT listener is intentionally built, it requires tested **routing policies, retry budgets, idempotency, rate limits, monitoring, and stop/quarantine gates**. For **manual incident replays**, a one-shot tool operating on an approved manifest is far safer than an always-on listener.

## 20. DLT Replay Differs from Consumer Group Offset Resets

Some operators reach for consumer group offset resets to "reread original messages." That is a completely different operation:

| Action | Scope | Risk |
|---|---|---|
| Replay one DLT tuple | One specifically chosen record | Duplicates at target if re-run |
| Replay a list of DLT tuples | Approved failure subset | Requires auditing and per-record reconciliation |
| Reset group offsets | Affects every record from the new offset onward in the partition/group | Huge volumes of already-valid messages get reprocessed |
| Create a new consumer group | Reads per new group's `auto.offset.reset` policy | May read from start or miss records |
| Republish from backup | Depends on source snapshots | May lose headers, keys, and ordering history |

**Never use `kafka-consumer-groups --reset-offsets` as a direct substitute for DLT replay.** When a reset is genuinely required, follow its own runbook: stop/coordinate the group, snapshot offsets, estimate record scope, and verify deduplication.

## 21. Interaction Between Replay and Spring Kafka Retry/DLT Handlers

Once replayed to the target topic, a record flows through the live consumer and error handler. If the root cause was not resolved:

~~~text
DLT replay
    |
    v
Original topic
    |
    v
Listener fails
    |
    +-- Retry 1
    +-- Retry 2
    +-- Recovery
    |
    v
DLT again
~~~

If an automated replayer kept consuming newly arriving DLT records, the system would loop forever. Prevent this by:

- Replaying only snapshotted selections.
- Monitoring **new DLT inflow** during and after replay.
- Capping total recovery attempts by `eventId`/operation, not just Kafka offset.
- Attaching safe replay metadata if consumers accept it without breaking schemas.
- Quarantining records that fail replay alongside `replayOperationId` for investigation.
- Halting whenever new failures exceed thresholds.

### `@RetryableTopic` and Non-Blocking Retries

Some applications use retry topics generated by `@RetryableTopic`. They run on their own schedules, backoffs, and listener containers. Replaying directly into an intermediate retry topic can bypass tested pipelines or skew attempt tracking.

**Prefer targets designed explicitly for recovery** (source topic or recovery topic) rather than guessing framework-managed retry topic names. Inspect the active configuration and test one record first.

## 22. Kafka Delivery Guarantees and Ambiguous Commits

With a non-transactional producer, `send` is ACKed by the broker per `acks` policy. If connectivity drops mid-flight, the app may not know whether the record was appended.

With a transactional producer, sends can ACK **before the transaction commits**. `read_committed` consumers see only committed data, hiding records from aborted transactions.

~~~text
Transactional replay producer
    |
    +-- send A, send B
    |
    +-- send ACKs received
    |
    +-- commitTransaction
             |
             +-- committed -> visible to read_committed
             +-- aborted   -> not visible
             +-- ACK lost  -> outcome uncertain to client
~~~

**A database replay ledger does not commit atomically with a Kafka transaction.** Crashing between the two resources leaves a gap. Rely on `eventId`/business deduplication and reconciliation.

To send a small group of records inside one Kafka transaction, use `KafkaTemplate.executeInTransaction` with a transactional `ProducerFactory` and tight batch caps. Remember:

- Keep transactions short; never hold them open awaiting approvals or slow DB checks.
- Handle producer fencing and transaction timeouts.
- Kafka transactions do not cover external non-Kafka side effects.
- Commit ACK ambiguity still requires a reconciliation policy.

Never turn on transactions just to claim "exactly once" without matching requirements and tests.

## 23. Phase 7 — Post-Replay Reconciliation

After every canary and batch, reconcile **expected, sent, received, and applied**:

~~~text
Selected for replay:        12
Blocked before replay:       3
Sent / broker ACK:          12
Downstream received:        12
Business applied:           10
Already processed (dedup):   2
Unexpected DLT re-entry:     0
Unresolved:                  0
~~~

This shows **10 business applications is not automatically an error** if two events had already been processed and were legitimately deduplicated. What matters is that every event reached a **valid business outcome**.

### Reconciliation by Business Key

Suppose a business table `order_event_application` enforces unique `event_id`:

~~~sql
SELECT
    event_id,
    COUNT(*) AS applied_count
FROM order_event_application
WHERE batch_id = :batchId
GROUP BY event_id
HAVING COUNT(*) <> 1;
~~~

Where some events were deduplicated because they ran earlier, compare against **expected logical state** instead of demanding physical application counts equal one.

An anti-join check in a dedicated reconciliation store:

~~~sql
SELECT e.event_id
FROM approved_replay_expected e
LEFT JOIN order_event_application a
       ON a.event_id = e.event_id
WHERE a.event_id IS NULL;
~~~

These tables are illustrative. In production, query verified schemas and datasets. When events have no DB writes (e.g., forwarding to Kafka or sending notifications), inspect downstream receipts, output topics, or audit logs.

### Checking by Source Tuple

A report should account for every item:

| Source DLT Tuple | Decision | Kafka Send | Downstream Outcome | Final |
|---|---|---|---|---|
| `p0/o3811` | Replay | ACK | Applied | `VERIFIED` |
| `p0/o3812` | Replay | ACK | Deduplicated legitimately | `VERIFIED` |
| `p2/o9024` | Block | Not sent | Schema unknown | `BLOCKED` |

Never strip `BLOCKED` rows from reports to make completion rates look artificially high.

## 24. Handling Errors During Replay

### 24.1. Producer Send Fails Before ACK

Actions:

1. Stop the active batch.
2. Log source tuple and failure category—**never raw payloads**.
3. Check broker, ACLs, network, and timeouts.
4. Determine whether the ACK outcome is truly known or ambiguous.
5. Reconcile against the target using `eventId` when ambiguous.
6. Retry only under an approved idempotency policy.

### 24.2. Record Sent Yet Downstream Routes It Back to the DLT

Actions:

1. Stop sending further records of that category.
2. Capture the new DLT tuple and link it to `eventId` and `operationId`.
3. Classify the new error; never assume it is the same root cause.
4. If caused by a regression in the fix, roll back or halt canary per deployment runbook.
5. Quarantine the record, add regression tests, and resume replay only after a verified fix.

### 24.3. Audit Ledger Fails

If the Kafka send succeeded yet updating the ledger failed, mark **`UNCONFIRMED`** in the incident log or recovery store. Never rerun the send "just so the ledger gets an ACK" without checking whether the event already exists and was processed downstream.

### 24.4. Consumer Lag Spikes Sharply

Slow down or halt replay rates; inspect consumer concurrency, poll intervals, retries, DB latency, and bottlenecked partitions. Never raise concurrency unboundedly if partition counts, DB pools, or ordering constraints prohibit it.

### 24.5. Wrong Target Topic or Wrong Schema

Stop immediately, record sent target partitions/offsets, and assess which consumers read them and which side effects fired. Kafka log appends have no simple "roll back all published records" button. Coordinate downstream cleanup/compensation with topic owners.

## 25. There Is No Undo Button for Committed Kafka Replays

Once a replayed record is in the target topic, **deleting rows in a replay ledger does not delete the Kafka record**. Undoing effects depends on domain contracts:

- Emit a domain-defined compensating event.
- Mark the event superseded/invalidated if schemas support it.
- Revert DB state via an approved business transaction.
- Inspect receipts and compensate external side effects.
- Pause consumers to contain blast radius while assessing impact.

Never emit tombstones or reset offsets impulsively as an "undo"; tombstones have specific compacted-topic semantics, and offset resets can replay unrelated events.

### Recovering After an Early Stop

Suppose an operator halts a 10-record replay after five records:

~~~text
Approved: 10
SENT_ACKED: 5
DOWNSTREAM_VERIFIED: 4
UNCONFIRMED: 1
NOT_SENT: 5
~~~

Before resuming:

1. Reconcile the one `UNCONFIRMED` record.
2. Confirm the four `VERIFIED` records still match expected business state.
3. Send only confirmed `NOT_SENT` records, or use idempotent replay for records needing retry.
4. Keep the same `operationId` and selection; never expand scope casually.
5. Re-run preflight checks and a canary if the environment changed.

## 26. DLT Retention and Preserving Evidence

Kafka topics enforce **`retention.ms`**, **`retention.bytes`**, or **`cleanup.policy`**. A DLT is not infinite storage.

Risks:

- Records expire past retention while awaiting a fix.
- Compacted topics drop older DLT entries sharing keys.
- Partition/broker changes alter readability of old offsets.
- Events carrying PII require strict retention and deletion policies.

Procedure:

1. From incident start, check **time remaining before retention expiry**.
2. If fixes cannot land before expiry, export a **controlled backup** to an encrypted, access-controlled quarantine object store.
3. Retain checksums and source metadata for verification, keeping secrets/PII out of tickets.
4. Never extend production DLT retention casually without evaluating disk capacity, security, and approvals.
5. Once source records expire, report **`SOURCE_EXPIRED`**; never fabricate payloads or substitute another offset.

**A Kafka log offset is not a permanent identifier.** Under retention or compaction, that offset may no longer hold a readable business record; never discard business event references and evidence in favor of storing offsets alone.

## 27. Security and Permissions for Replay Tooling

DLTs can hold bad data, raw payloads, exception stack traces, and security-sensitive headers. Operational tools must:

- Authenticate operators and authorize by cluster, source, and target.
- Restrict targets via a **mapping allowlist**, never accepting arbitrary topic names from payloads.
- Use a least-privilege Kafka principal: `READ` on DLT and `WRITE` on approved targets.
- Never print raw payloads or exception headers to consoles, Slack, or tickets.
- Encrypt secrets and keep credentials out of shell history.
- Protect manifests, audit ledgers, replay snapshots, and quarantine stores.
- Require two-person approval where domain policies demand it.
- Never expose replay tools as unauthenticated public APIs.
- Enforce timeouts, batch caps, max bytes, and rate limits.
- Define retention and access controls for replay artifacts.

**Never rely on plain hashes of emails or phone numbers as strong anonymization.** Where correlation by user or business entity is needed, use approved surrogate IDs and proper pseudonymization.

### What Should Be Logged?

~~~text
event=dlt.replay.started
incidentId=INC-KAFKA-2026-015
operationId=REPLAY-2026-015-A
sourceTopic=orders.events.DLT
targetTopic=orders.events
selectedCount=12
rateLimit=2

event=dlt.replay.record.acked
operationId=REPLAY-2026-015-A
sourcePartition=0
sourceOffset=3811
targetPartition=1
targetOffset=92010

event=dlt.replay.stopped
operationId=REPLAY-2026-015-A
reasonCode=DOWNSTREAM_ERROR_RATE_EXCEEDED
~~~

Values are illustrative only. Never log raw keys, values, access tokens, `Authorization` headers, or unsanitized exception messages.

## 28. Metrics and Dashboards for Monitoring Replay Runs

Track **replay metrics** alongside **consumer and downstream metrics**:

| Metric / Signal | Purpose |
|---|---|
| Selected / eligible / blocked counts | Tracks actual scope and ineligible items |
| Replay send attempts | Tracks rate and send volume |
| Replay ACK success/failure | Flags producer or broker errors |
| Unconfirmed send outcomes | Flags items needing reconciliation before retry |
| Downstream applied / deduplicated | Verifies business outcomes |
| New DLT inflow | Catches loops or incomplete fixes |
| Consumer lag | Tracks backpressure and catch-up |
| Retry / exception rate | Flags new target consumer failures |
| DB/API latency and connection pools | Monitors downstream headroom |
| Producer request latency/timeouts | Reflects Kafka health and publish overhead |
| Replay age / time-to-recovery | Measures operational SLA compliance |

In Prometheus, custom application metric names might look like:

~~~text
dlt_replay_selected_total
dlt_replay_sent_total
dlt_replay_unconfirmed_total
dlt_replay_downstream_verified_total
dlt_replay_reentry_total
~~~

These are suggested names, **not built-in Spring Kafka metrics**. Avoid putting `eventId`, `orderId`, or arbitrary `operationId` values into high-cardinality labels; keep those IDs in access-controlled audits and logs.

### Signals That Trigger Stop

Some metrics naturally rise briefly during replay (e.g., short-lived consumer lag while publishing). Runbooks must set **thresholds and observation windows** to avoid both premature aborts and ignoring real failures. For sensitive side effects like payments, even one confirmed duplicate may warrant an immediate halt.

## 29. Testing the Runbook Before Production Use

Test replays in test/staging using **`EmbeddedKafka` or Testcontainers** and a representative test database schema.

### Test Model

~~~text
Test producer -> orders.events
                      |
                      v
               Listener fails
                      |
                      v
                DLT publisher
                      |
                      v
              orders.events.DLT
                      |
                      v
              Dry-run / replay tool
                      |
                      v
              orders.events / recovery
                      |
                      v
              Fixed listener + test DB
~~~

Include tests where the DLT record is produced by the real **Spring Kafka recoverer**, alongside tests for tuple-based DLT reading. Hand-crafting a dummy DLT record with clean key/value can miss header differences produced by real deserialization failures.

### Minimum Test Matrix

| ID | Scenario | What to Prove |
|---|---|---|
| RP-01 | Transient DB error, now fixed | Single-record replay → downstream succeeds cleanly |
| RP-02 | Dry-run | Zero producer sends; accurate preview |
| RP-03 | Exact offset selection | Records outside selection are untouched |
| RP-04 | Offset no longer exists | Fails with `SOURCE_OFFSET_NOT_AVAILABLE` |
| RP-05 | Disallowed target mapping | Rejected before send |
| RP-06 | Deserialization failure | Preserves required bytes/headers or blocks |
| RP-07 | Null key | Partition routing and ordering evaluated |
| RP-08 | Tombstone | Blocked without explicit authorization |
| RP-09 | Already-processed record | Business deduplication blocks duplicate side effect |
| RP-10 | Kafka ACK lost | Outcome reconciled; no blind resend |
| RP-11 | Replayed record re-enters DLT | Stops on threshold and traces operation |
| RP-12 | Sender crashes after ACK before ledger update | Resume does not duplicate business effect |
| RP-13 | Source/target have different partition counts | Explicit routing policy; never trusts original partition |
| RP-14 | Stale event after newer event | Version/sequence guard prevents overwriting newer state |
| RP-15 | Legacy payload/schema | Target consumer handles or quarantines |
| RP-16 | Concurrent operators | Lock blocks overlapping selection |
| RP-17 | Rate limit / backpressure | Tool stays within thresholds |
| RP-18 | DLT retention expired | Reports source expired; never picks wrong record |
| RP-19 | Aborted transaction at source | `read_committed` never replays aborted data |
| RP-20 | Invalid credentials / ACLs | Never logs secrets or misroutes |
| RP-21 | Partial replay then resume | Ledger/audit and final outcomes stay consistent |
| RP-22 | Target event triggers external API side effect | Idempotency key prevents duplicate side effect |

### Integration Test with Spring Kafka

A test can look like:

~~~java
@EmbeddedKafka(
    partitions = 1,
    topics = {"orders.events", "orders.events.DLT"},
    brokerProperties = {
        "offsets.topic.replication.factor=1",
        "transaction.state.log.replication.factor=1",
        "transaction.state.log.min.isr=1"
    }
)
class DltReplayIntegrationTest {

    // Test context with KafkaTemplate, consumer factories,
    // DLT recoverer, listener, and test database.
    //
    // 1. Send input E101.
    // 2. Force listener failure until DLT receives the record.
    // 3. Verify DLT tuple/key/headers per contract.
    // 4. Execute dry-run: zero new outputs.
    // 5. Fix mock dependency.
    // 6. Replay exact approved tuple.
    // 7. Await downstream receipt with timeout.
    // 8. Query DB: E101 applied exactly once.
    // 9. Zero unexpected DLT re-entries.
}
~~~

This is an integration test **skeleton**; add the Spring test context, dependencies, imports, setup, consumer assignments, and version-specific assertions. It defines required evidence rather than standalone runnable code.

### Never Use `sleep` to Assert Replay Success

Anti-pattern:

~~~java
replayTool.replayOne(request);
Thread.sleep(500);
assertEquals(1, outputCount);
~~~

Such tests flake across broker scheduling, consumer assignment, retries, and DB latency. Use bounded polling or Awaitility against concrete conditions:

~~~java
await()
    .atMost(Duration.ofSeconds(15))
    .untilAsserted(() ->
        assertEquals(1, countAppliedEvent("E101")));
~~~

This assumes **Awaitility** and helper assertions are in test dependencies. Assert that the **exact target event** was applied, not merely that a generic counter incremented.

## 30. Two Contrasting Practice Scenarios

### Scenario A — Transient Database Failure

**Symptom:** order event `E101` landed in the DLT due to a DB connection timeout.

**Analysis:** payload/schema valid; consumer exhausted retries; DB recovered; no output persisted yet for `eventId`; dedup logic ready.

**Procedure:**

1. Open an incident and approved manifest for the exact DLT tuple.
2. Verify DB health and test a representative fixture.
3. Run dry-run confirming key, value, schema, and target.
4. Canary-replay `E101` at low rate.
5. Wait for Kafka ACK and observe consumer processing.
6. Query the DB by `eventId`; confirm exactly one logical application.
7. Monitor DLT inflow, lag, and DB health.
8. Update ledger to `DOWNSTREAM_VERIFIED` and close after reconciliation.

**Lesson:** replay is viable once **the root cause is fixed**, backed by clear idempotency and reconciliation.

### Scenario B — Schema-Incompatible Payload

**Symptom:** DLT record `E202` carries a legacy serializer payload that newer consumers fail to parse.

**Analysis:** replaying raw bytes to the source topic will fail identically. Schema version, migration path, and compatibility must be determined.

**Procedure:**

1. Halt replay; mark `E202` `BLOCKED_SCHEMA`.
2. Retrieve original payload and metadata using authorized tools.
3. Identify old parser/schema version and permitted transformation rules.
4. Build a migration function with unit/integration tests on synthetic payloads.
5. Decide whether the migrated payload keeps the **same business event identity** or emits a new event version per policy.
6. Obtain approval before publishing to a recovery topic or compatible target.
7. Reconcile final outputs and preserve audit links from source tuple → transformed record.

**Lesson:** not every DLT record is a transient failure; some require a **data repair workflow**, not a resend.

## 31. Copy-Ready Operations Runbook Template

Fill out this template for each concrete replay operation.

### Details

~~~text
Runbook: Spring Kafka DLT Replay
Incident/Change ID: __________________
Environment/Cluster: _________________
Service/Consumer Group: ______________
Source DLT: __________________________
Target Topic: ________________________
Replay Operation ID: _________________
Selected Tuple Manifest: _____________
Expected Eligible Count: _____________
Root Cause Category: _________________
Fix Evidence: _______________________
Schema Compatibility Evidence: _______
Idempotency / Receipt Strategy: ______
Approval / Owner: ___________________
Rate Limit / Max In Flight: __________
Stop Conditions: ____________________
Audit Location: _____________________
~~~

### Execution Phases

| Phase | Action | Completion Gate |
|---|---|---|
| 0. Authorization | Confirm owner, scope, approval, and lock | `APPROVED` |
| 1. Root-cause triage | Classify errors and verify fix | `FIX_VERIFIED` |
| 2. Inventory | Snapshot DLT tuples, schemas, business status | `SCOPE_FROZEN` |
| 3. Preflight | Check routing, ACLs, retention, capacity, dedup | `PREFLIGHT_PASS` |
| 4. Dry-run | Read selection without sending to Kafka | `NO_SEND` / `ELIGIBLE_CONFIRMED` |
| 5. Canary | Replay tiny sample and reconcile | `CANARY_VERIFIED` |
| 6. Bounded replay | Replay small batches at capped rate; watch stop conditions | `SEND_COMPLETE_OR_STOPPED` |
| 7. Reconciliation | Compare expected, ACKed, applied, deduped, DLT re-entries | `DOWNSTREAM_VERIFIED` |
| 8. Closure | Archive evidence, blocked items, follow-ups, lessons | `CLOSED` |

If any critical gate is `FAIL` or `UNKNOWN`, **never skip ahead to the next phase**. Once Kafka records are emitted, recovery relies on durable state and idempotency—changing a ticket status never rolls back Kafka.

### Final Reporting Format

~~~text
STATUS: COMPLETED / PARTIAL / BLOCKED / FAILED
OPERATION_ID:
SOURCE_DLT:
TARGET_TOPIC:
SELECTED_COUNT:
ELIGIBLE_COUNT:
BLOCKED_COUNT:
SENT_ACKED_COUNT:
DOWNSTREAM_VERIFIED_COUNT:
DEDUPLICATED_COUNT:
DLT_REENTRY_COUNT:
UNCONFIRMED_COUNT:
UNRESOLVED_TUPLES:
APPROVER:
EVIDENCE_LINKS:
FOLLOW_UP:
~~~

Report **`COMPLETED`** only when eligible records have **verified downstream outcomes** and blocked records are explicitly documented—not merely when Kafka sends equal `selectedCount`.

## 32. Common Mistakes

**Replaying the whole DLT to "clean it up."** One topic can hold multiple error types and incidents; replaying everything can trigger a second outage.

**Skipping root-cause fixes before replay.** Messages bounce right back to the DLT in a loop.

**Confusing DLT offsets with original offsets.** Both topics have independent offset sequences.

**Trusting `original-topic` headers as routing commands.** Headers are data, never substitutes for an approved target allowlist.

**Piping console consumer into console producer.** Strips keys, headers, schema metadata, and audit trails while risking payload leaks.

**Treating send ACKs as business processing success.** Consumers can still fail validation or deserialization.

**Minting a fresh `eventId` per attempt.** Breaks business deduplication.

**Believing Kafka's idempotent producer prevents all replay duplicates.** Running the tool twice emits two separate records; downstream must be idempotent.

**Copying all DLT exception headers.** Can re-inject stack traces, PII, or unwanted metadata into main consumers.

**Ignoring schemas and serializers.** Copying raw bytes fails if target consumers cannot read that format.

**Ignoring tombstones and out-of-order events.** Replaying stale events can delete or overwrite newer state.

**Forcing original partitions without checking target partition counts.** Can route wrongly or break ordering if topic layouts changed.

**Resetting consumer group offsets instead of replaying.** Broad-blast operation risking duplicates and skipped records.

**Replaying at full speed right after recovery.** Easily re-overloads recovering databases and APIs.

**Running an ungated always-on DLT replay listener.** Keeps looping poison pills endlessly.

**Marking the ledger `SENT` before broker confirmation.** Corrupts state and complicates recovery.

**Resending immediately when an ACK is lost.** The record may already have succeeded; reconcile first.

**Hiding blocked records from reports.** Falsely marks incidents complete while data remains missing.

**Letting DLT retention expire without saving evidence.** Destroys investigation and recovery capability.

**Lacking stop switches or compensation plans.** Committed Kafka appends have no simple undo.

**Logging raw payloads and exceptions into runbook logs.** Leaks PII and secrets.

## 33. Core Operational Principles

Reliable DLT replay is never "read and send back to Kafka." It is a scoped workflow with explicit gates:

1. **Triage**: prove why each record failed and confirm the root cause is resolved.
2. **Select**: freeze a manifest of DLT tuples without pulling in post-snapshot arrivals.
3. **Validate**: verify business state, schemas, keys, headers, targets, and authorization.
4. **Dry-run**: verify readability and routing **without publishing**.
5. **Canary**: send a tiny sample and verify real downstream outcomes.
6. **Bounded replay**: enforce rate limits, batch caps, audit logging, and stop switches.
7. **Reconcile**: verify business state, deduplication, DLT re-entries, and unresolved items.
8. **Close**: archive evidence and follow-ups; never equate ACK with `COMPLETED`.

When a runbook states **exactly who may act, on which records, under what preconditions, and what evidence proves success**, operations teams can recover DLT messages without inadvertently causing data loss, duplicate side effects, or fresh retry storms. That is the standard for a **Spring Kafka Reliability Operations** procedure that can be tested and executed safely during real incidents.
