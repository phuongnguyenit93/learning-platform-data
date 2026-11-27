# Error Events and Dead-Letter Handling in Debezium

## 1. The Problem: When a CDC Event Fails, Where Does the Data Go?

In the **SPRING_INTEGRATION_ADAPTERS** module, data from external systems enters Spring Integration through an inbound adapter or gateway, travels across `MessageChannel`s, gets processed by transformers, routers, filters, and service activators, and can then be sent to Kafka, JMS, AMQP, HTTP, SFTP, files, or databases via outbound adapters. For database synchronization, **Debezium** reads the source transaction log and produces *Change Data Capture* (CDC) events for a Spring Integration flow to process.

A CDC event can fail at many points:

- Debezium can no longer read the binlog/WAL or fails to decode changes from the source database.
- Kafka Connect fails to convert data into a message format, or an SMT (*Single Message Transform*) throws an exception.
- Spring Integration's Kafka consumer fails to deserialize a record.
- A transformer encounters a new schema, a missing required field, or an unrecognized `op`.
- A service activator writing to the target database hits a timeout, deadlock, or constraint violation.
- An outbound adapter sending to HTTP/JMS/AMQP or a sink encounters a connection error.

If every error is retried infinitely, **a permanently failing record** (*poison pill*) can stall an entire Kafka partition. If the application skips records too early, the projection may **lose a business change**. A **dead-letter** mechanism (DLQ/DLT) isolates unprocessable messages according to policy while preserving enough context to investigate and replay after fixing the root cause.

Key point upfront: **Debezium does not have a single universal `op="error"` row-change envelope for all failures**, and "dead-letter" is not one automatic pipeline spanning database → Debezium → Kafka → Spring Integration. Each layer has its own error reporting, retry, and checkpointing behavior.

### Learning Outcomes

After this lesson, you will be able to:

1. Distinguish CDC source errors, Kafka Connect sink errors, and Spring Integration consumer errors.
2. Explain the difference between **errors in logs/metrics**, Spring Integration **`ErrorMessage`s**, and **dead-letter records** on Kafka.
3. Choose between retry, fail-fast, alerting, or DLQ based on error classification and zero-data-loss requirements.
4. Configure a Kafka Connect sink DLQ and a Spring Kafka dead-letter recoverer for the right processing layer.
5. Design DLQ metadata, offset acknowledgment, redrive, idempotency, observability, and recovery procedures.

## 2. Locating Failures End-to-End

~~~mermaid
flowchart TD
    DB[(MySQL / PostgreSQL)] --> CDC[Debezium<br/>source connector]
    CDC -->|CDC records| TOPIC[(Kafka CDC topic)]
    TOPIC --> IN[Spring Integration<br/>Kafka inbound adapter]
    IN --> CH[MessageChannel]
    CH --> HANDLER[Transformer / service activator]
    HANDLER --> SINK[(Database / HTTP / JMS / AMQP)]
    DB -. missing log / permissions .-> SOURCEERR[Connector/task FAILED<br/>log + metrics + alert]
    CDC -. binlog decode error .-> SOURCEERR
    IN -. deserialize / process error .-> RETRY[Consumer retry / recoverer]
    HANDLER -. synchronous exception .-> RETRY
    RETRY -->|retries exhausted, publish ok| DLT[(Kafka DLT topic)]
    RETRY -. DLT publish failed .-> STOP[Keep failing / keep retrying<br/>per policy]
    TOPIC --> CONNECTSINK[Kafka Connect sink<br/>if any]
    CONNECTSINK -. Connect-supported error .-> CONNECTDLQ[(Connect sink DLQ)]
~~~

**This diagram is an architectural illustration.** A system does not necessarily run both a Spring Integration consumer and a Kafka Connect sink simultaneously. The Connect sink branch is shown separately to distinguish Connect's built-in DLQ feature from Spring Kafka's DLT mechanism.

| Failure Point | Example | Appropriate Observability / Policy | Auto-Creates a Kafka DLQ? |
|---|---|---|---|
| Source database | Missing replication slot, purged binlog, missing read privileges | Database logs, Debezium task status, source offset, alerts, and recovery runbook | **No**; no CDC record may even be produced |
| Debezium source connector | Cannot decode log event, broken schema history | Debezium logs, connector config, task status, metrics | Not by default; must be resolved at source/connector |
| Kafka Connect converter/SMT | Data type cannot be converted | Connect error handling; depends on source/sink and version | **Built-in DLQ** is primarily designed for **sink connectors** |
| Kafka Connect sink | Cannot process a read record | Connect tolerance/retry/log/DLQ for supported error types | Can use Connect sink DLQ |
| Spring Kafka consumer | Deserialization/conversion error | `ErrorHandlingDeserializer`, listener container error handler, recoverer | Yes, **if** a DLT-publishing recoverer is configured |
| Spring Integration flow | Validator fails, service activator throws exception | `errorChannel`, retry advice, propagating errors to Kafka listener container | `errorChannel` alone is **not** a Kafka DLT |
| Target system | DB timeout, HTTP 503, JMS broker outage | Bounded retries, idempotency verification, circuit breaker | Depends on flow/recoverer design |

A source connector halted due to missing WAL segments cannot "push the bad record to a DLT and move on" when no processable record exists yet. Recovery requires checking remaining logs, offsets, snapshots, and source schema state.

## 3. "Error Event" Can Mean Three Different Things

### 3.1. Connector Exception or Failed Task State

A Debezium source may record a stack trace, failing log position, or `FAILED` status on a Kafka Connect task. This is an **operational signal**, not necessarily a CDC message on a business topic. For instance, if a MySQL source fails reading a corrupted binlog event, the Kafka topic may **contain no corresponding record at all**, leaving downstream consumers with nothing to receive or route to a DLT.

Debezium's heartbeat, transaction metadata, or schema change notification streams also follow distinct contracts; never treat them as "error events" simply because they differ from the `before/after/op` row CDC structure.

### 3.2. Spring Integration `ErrorMessage`

In Spring Integration, when certain components or endpoints throw exceptions, the framework can send an `ErrorMessage` wrapping the exception to an `errorChannel` (global or explicitly configured). This is a **Spring message representing a flow failure**, not a Kafka record by default.

Example:

~~~text
cdcRawChannel
    -> transform envelope
    -> orderProjectionHandler
               |
               +-- exception --> orderErrorChannel
                                     |
                                     +-- audit / alert / recovery decision
~~~

If errors are merely sent to a logging handler that returns normally, the listener container **may treat the message as successfully processed**, depending on how the adapter connects to the flow. Explicitly decide which exceptions propagate back to the Kafka listener for retry, which enter a durably confirmed recovery branch, and when the consumer offset may be committed.

### 3.3. Kafka Dead-Letter Record

**DLQ** (*Dead Letter Queue*) is the general term for holding unprocessable messages; **DLT** (*Dead Letter Topic*) typically refers to a Kafka topic serving that role. Both terms are often used interchangeably in Kafka architectures.

A record sent to a DLT can:

- Preserve the **original key and value** alongside headers describing the exception, topic, partition, and offset.
- Or use an **application-defined error envelope** referencing the original payload.

Never assume a DLT payload automatically contains fields like `error`, `reason`, `originalEvent`, or `retryCount`: those fields exist only if the framework or your application explicitly adds them. Specifically, Spring Kafka's `DeadLetterPublishingRecoverer` typically forwards the original key/value with error metadata in headers, whereas a Kafka Connect sink DLQ attaches error context per its own configuration.

## 4. Classifying Errors to Choose Retry vs. Dead-Letter

Handling decisions must be driven by recoverability and data semantics:

| Error Group | Example | Typical Suitable Handling |
|---|---|---|
| **Transient** | Target DB timeout, HTTP 503, brief broker disconnect | Bounded retry with backoff and time/count limits; preserve idempotency |
| **Corrupt or incompatible record** | Unparseable JSON, changed field type, unsupported schema/version | Limit blind retries; quarantine/DLT, deploy fix, then redrive |
| **Business contract violation** | `amount < 0` rejected by receiving policy | Route to audited error flow; intervene and fix source or drop deliberately |
| **Source/CDC failure** | Missing binlog/WAL, invalid schema history, unreadable logs | Fail-fast/alert; restore connector or run controlled snapshot/reconciliation |
| **Configuration or infra error** | Invalid credentials, missing topic, ACL denial | Fix config/infra; avoid flooding DLT with healthy records |
| **Programming bug** | `NullPointerException` in transformer, mapper reading wrong field | Fix code, test with real event; preserve record for replay |
| **Valid but special message** | `op="r"`, Debezium tombstone, heartbeat | Route per contract; **do not** treat as an error just because `after` is missing |

If a **permanently bad** record blocks progress, a DLT lets the stream advance once the record is safely isolated. However, skipping one update in a dependent sequence can cause subsequent updates to apply wrongly. For order-sensitive domains, you may need to **halt processing for that key/partition**, fix the issue, and replay in order before letting newer events proceed.

## 5. Debezium Source Errors: Do Not Confuse with Kafka Connect Sink DLQ

### 5.1. Handling Errors While Reading the Transaction Log

Some Debezium connectors (e.g., MySQL, depending on version) expose an option such as:

~~~properties
# Example Debezium source connector property, not Spring Integration.
event.processing.failure.handling.mode=fail
~~~

On supporting MySQL connector versions, modes may include:

| Value | Practical Meaning | Risk |
|---|---|---|
| `fail` | Reports an error and stops the connector/task when a source event cannot be processed | CDC stream pauses; operator intervention required |
| `warn` | Logs a warning with event/position details and skips the event | **Can lose a change**; projection becomes incomplete |
| `ignore` | Skips the failing event without logging corresponding warnings | Silent divergence that is hard to detect |

**Exact property names and allowed values must be verified against your Debezium connector/version.** For instance, MySQL docs use `warn` and `ignore` for `event.processing.failure.handling.mode`, whereas some schema-inconsistency properties use `skip`; never mix these settings up.

When data correctness matters, prefer **`fail` with clear alerting** whenever a connector cannot decode an important event. Choose `warn`/`ignore` only when record loss is acceptable and backed by reconciliation and recovery procedures. No DLT record is guaranteed to be produced for an event skipped right at the source layer.

### 5.2. Source Offsets and Conditions for Re-Reading

Suppose the durable offset is at `mysql-bin.000021:1000`, and Debezium hits a failing event later and stops:

1. Investigate the **root cause**: schema history, DDL change, corrupted data, permissions, config, or purged logs.
2. Record the source, connector/task, timestamp, and reported log/offset coordinates.
3. Verify the required binlog/WAL segment still exists.
4. Fix the root cause and resume via supported connector mechanics.
5. If re-reading is impossible, plan a snapshot/reconciliation from a consistent boundary; never arbitrarily "jump" the offset to skip the error.

Even if a Kafka Connect sink DLQ exists downstream, it **cannot recover** an event the Debezium source never emitted.

### 5.3. Connect Error Tolerance Does Not Cover Every Failure

Kafka Connect provides `errors.tolerance`, `errors.retry.timeout`, `errors.log.enable`, and error-reporting properties. They do not guarantee that every binlog read error, permission error, missing log, or schema history failure in a **Debezium source connector** will be routed to a DLQ and skipped cleanly.

Likewise, when embedding the Debezium Engine in a Java application, examine the **Engine's own exception and offset-commit handling** rather than blindly applying Kafka Connect worker or Spring Kafka consumer settings.

## 6. Kafka Connect Sink DLQ: Configuring in the Right Context

Kafka Connect supports writing failing records to a dead-letter topic inside a **sink connector** (e.g., a sink reading Kafka and writing to a target system) for errors occurring within Connect's supported stages such as converters, SMTs, and sink processing.

**Example properties for a Kafka Connect *sink connector***:

~~~properties
# Allow skipping failed records after error reporting/recovery.
errors.tolerance=all

# Retry Connect-handled errors for up to 60 seconds.
errors.retry.timeout=60000
errors.retry.delay.max.ms=5000

# Log errors; do not dump raw message payloads into application logs.
errors.log.enable=true
errors.log.include.messages=false

# DLQ for the sink connector:
errors.deadletterqueue.topic.name=orders-connect-sink-dlq
errors.deadletterqueue.context.headers.enable=true
~~~

Meaning:

- `errors.tolerance=none` is the default, failing immediately on intolerable errors; `all` allows skipping failed records within Connect's tolerance scope after configured reporting. **Never enable `all` casually** if every change must be preserved.
- `errors.retry.timeout`/`errors.retry.delay.max.ms` govern Connect-managed retries; they do not replace business retries in Spring Integration.
- `errors.deadletterqueue.topic.name` specifies the Kafka DLQ for the **sink connector**; the topic needs appropriate retention, partitions, replication, and read/write ACLs.
- `errors.deadletterqueue.context.headers.enable=true` adds error context headers prefixed with `__connect.errors.`. Do not assume error details live inside the JSON value.
- `errors.log.include.messages=false` keeps raw keys/values out of application logs, especially when CDC contains PII; DLQ read access must still be restricted.

A Kafka Connect source such as Debezium is typically configured to **emit** CDC records. If you want error handling on the Spring Integration consumer, configure **Spring Kafka / Spring Integration error handling** on that consumer rather than expecting `errors.deadletterqueue.topic.name` on the Debezium source to produce the desired DLT flow.

## 7. Spring Integration: `errorChannel`, Retries, and Kafka DLT

### 7.1. Distinguishing `errorChannel` from a DLT

In Spring Integration, `errorChannel` is a **`MessageChannel`** used to carry exception info, usually wrapped in an `ErrorMessage`. It can connect to a service activator that writes audits, fires alerts, or calls an outbound adapter to publish the record to a Kafka DLT.

Example:

~~~text
KafkaMessageDrivenChannelAdapter
    -> cdcInboundChannel
        -> parse + validate
        -> orderProjectionHandler
            |
            +-- exception --> errorChannel
                                  -> errorAuditHandler
                                  -> (by design) Kafka DLT outbound adapter
~~~

Distinguish two execution modes:

- **Synchronous processing:** exceptions from a service activator/transformer propagate back to the listener container so Spring Kafka's `DefaultErrorHandler` can retry or invoke recovery.
- **Asynchronous handoff:** if messages pass into an `ExecutorChannel` or in-memory queue and the listener considers delivery successful before the worker finishes, downstream errors may only reach `errorChannel` and **never trigger listener retries on the original record**. In that case, the application must build explicit durable handoff confirmation, recovery, and DLQ routing.

Do not treat sending an `ErrorMessage` as proof that the CDC record was safely stored in a DLT.

### 7.2. Spring Kafka `DefaultErrorHandler` with a DLT

When Spring Integration uses a **Kafka message-driven channel adapter**, a common setup configures the Spring Kafka listener container with `DefaultErrorHandler` and `DeadLetterPublishingRecoverer`.

The Java snippet below shows an **error handler bean**; the application must attach it to the listener container used by the Kafka inbound adapter:

~~~java
import org.apache.kafka.common.TopicPartition;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
public class CdcKafkaErrorHandling {

    @Bean
    DefaultErrorHandler cdcErrorHandler(
            KafkaTemplate<Object, Object> kafkaTemplate) {

        var recoverer = new DeadLetterPublishingRecoverer(
                kafkaTemplate,
                (record, error) -> new TopicPartition(
                        record.topic() + "-dlt",
                        record.partition()));

        // 1-second backoff, 2 retries after the initial attempt:
        // up to 3 total attempts before routing to the recoverer.
        return new DefaultErrorHandler(
                recoverer,
                new FixedBackOff(1_000L, 2L));
    }
}
~~~

**Integration notes:**

1. This bean **is not automatically wired** into every Kafka listener container; configure your container/adapter to use this handler.
2. `KafkaTemplate` needs serializers and producer permissions compatible with failed record keys/values, including raw `byte[]` when deserialization fails.
3. This example preserves the original partition when routing to `-dlt`, so the DLT must have at least as many partitions. Use a different partition-selection policy if needed.
4. Once the recoverer and container complete successfully, the record may be treated as *recovered* so the consumer advances. Exact offset commit behavior depends on ack mode, transaction mode, container configuration, and Spring Kafka version.
5. Verify behavior when **DLT publishing fails**. Never mark a record as skipped merely because an asynchronous send was invoked; configure send-result checking and proper failure handling.
6. This snippet uses Spring Kafka APIs from versions providing `DefaultErrorHandler`. Check the exact Spring Boot/Spring Kafka/Spring Integration APIs in your project before adopting it.

Some environments use Kafka transactions; in those setups, error/recovery flows may go through `DefaultAfterRollbackProcessor` or another transactional mechanism. Never mix transactional and non-transactional configurations without verifying commit/rollback behavior.

### 7.3. Deserialization Failures and `ErrorHandlingDeserializer`

A message containing undecodable bytes can fail the consumer **before the record ever reaches a Spring Integration `MessageChannel`**. Putting a `try/catch` inside a service activator will not catch such failures.

Spring Kafka provides `ErrorHandlingDeserializer` to surface deserialization errors via headers/metadata so the listener container handles them with its recoverer policy; on supporting versions, the DLT recoverer can recover the **raw bytes** of the failing value (or key) for storage. Configure the delegate deserializer, `KafkaTemplate` serializers, and error policy for both **key** and **value**.

If messages use Avro/Protobuf with Schema Registry, classify schema compatibility failures separately from Registry connectivity outages. Routing transient Registry outages straight to a DLT can quarantine floods of valid records during an infrastructure blip.

## 8. Designing Dead-Letter Records for Investigation and Redrive

Before routing a CDC message into a DLT, decide **what you will read back**, **where fixes happen**, and **how redrive runs**.

A practical observability contract:

| Group | Data to Retain | Why? |
|---|---|---|
| Kafka origin | Topic, partition, offset, timestamp | Locate the exact record for investigation or replay |
| Key | Kafka record key and schema/encoding if present | Identify the business entity and maintain per-key ordering |
| Original content | Raw key/value bytes or durable storage reference | Re-parse the exact original bytes after fixing the converter |
| Error type | Error code, exception class, processing step | Distinguish deserialization, validation, and sink failures |
| Retry state | Attempt count, first/last failure time, next retry | Spot poison pills and enforce recovery policies |
| Debezium metadata | `op`, `source`, log position, transaction ID **if readable** | Reconcile CDC state and distinguish replays |
| Tracing | Correlation ID, consumer/configuration version | Link logs, metrics, and offending deployments |
| DLQ governance | Status `OPEN`/`REPLAYED`/`RESOLVED`, reviewer, reason | Prevent repeated replays or forgotten records |

**Not every field is always extractable.** If deserialization failed before reading the envelope, only raw bytes and Kafka metadata may exist; never fabricate `op` or source log positions. If the failure happened in the Debezium source, there may be **no Kafka topic/partition/offset yet**.

### 8.1. Example Application-Defined Error Envelope

Instead of duplicating sensitive payloads in multiple places, an application can store raw bytes in a secured store and emit a metadata record to a governance topic:

~~~json
{
  "errorId": "err-orders-000042",
  "stage": "spring-integration-projection",
  "classification": "NON_RETRYABLE_SCHEMA",
  "reason": "Missing required order status mapping",
  "original": {
    "topic": "shop-cdc.sales.orders",
    "partition": 1,
    "offset": 2058,
    "keyRef": "secure://cdc-errors/000042/key",
    "valueRef": "secure://cdc-errors/000042/value"
  },
  "attempts": 3,
  "state": "OPEN"
}
~~~

**This is a custom-designed contract, not a default payload** from Debezium, Kafka Connect, or Spring Kafka. `secure://...` is merely an illustrative URI for an application-managed store, not a real protocol URL.

By default, `DeadLetterPublishingRecoverer` sends the original key/value and places error details in **Kafka headers**. If your DLT consumer expects JSON shaped like the example above, add an explicit transformation step before publishing.

### 8.2. Protecting Sensitive Data

CDC can carry customer names, addresses, identifiers, or payment details. When routing to a DLT:

- Never dump full payloads or exceptions containing sensitive data into broad application logs.
- Enforce least-privilege ACLs on DLQs/DLTs and raw payload stores.
- Apply encryption, retention, data erasure, and access auditing as required.
- Prevent DLTs from being accidentally consumed as primary CDC topics by using distinct names and consumer groups.
- Define behavior if the DLQ topic is full, deleted, or unreachable.

A DLT retention period shorter than the time operations needs to fix bugs destroys redrive capability. Conversely, retaining sensitive data indefinitely creates cost and compliance risks. Pick an appropriate retention policy.

## 9. Retries, DLT, and Offset Commits: Data-Safety Boundaries

Consider a Kafka consumer reading offset `2058` and a service activator updating a projection:

~~~mermaid
sequenceDiagram
    participant K as Kafka CDC topic
    participant C as Spring Kafka / Integration
    participant DB as Projection DB
    participant D as DLT
    K->>C: Record offset 2058
    C->>DB: Write projection
    DB-->>C: Timeout
    C->>DB: Retry with backoff
    DB-->>C: Timeout again
    C->>D: Send original record + error context
    alt DLT publish confirmed successful
        D-->>C: Stored
        C->>C: Recover / advance offset per config
    else DLT publish failed
        D-->>C: Error
        C->>C: Keep error state, retry/stop per policy
    end
~~~

Under **at-least-once** delivery, watch three boundaries:

1. **Target written, Kafka offset uncommitted:** a restart can replay the record; upserts/deletes and side effects must be idempotent.
2. **Sent to DLT, offset uncommitted:** the record may appear in the DLT again or be re-attempted; ensure deduplication and idempotent redrive.
3. **Offset committed before safe target write or DLT publish:** the consumer group may skip a change permanently without a copy left to reprocess.

Therefore, simply "logging the error and returning normally" is not equivalent to safely handling the record. If business rules allow quarantining a record and moving on, confirm it was durably persisted in the DLT/governance queue before allowing the consumer to advance per framework configuration.

### Per-Key Ordering Warning

Suppose event `E1` updating `orders.id=42` from `NEW` to `PAID` is routed to the DLT, and subsequent event `E2` updating `PAID` to `SHIPPED` succeeds. When redriving `E1`, an unconditional upsert would **regress the projection from `SHIPPED` back to `PAID`**.

Business-appropriate mitigations:

- Pause further processing for the failing key/partition until the older record is fixed.
- Maintain reliable version/ordering checks to reject stale updates, or reconcile from current source state.
- During redrive, check key history to decide whether the record still needs applying or has already been superseded.

**A DLT does not solve ordering on its own**, and Kafka does not guarantee uniform processing order across two different topics or partitions.

## 10. Safe Redrive Workflow

Reintroducing a record from a DLT back into processing is called *redrive* or *replay*. It requires explicit state tracking, especially after deploying CDC handler fixes.

1. **Identify root cause:** group failures by connector, topic, partition, exception, schema version, time, and deployment.
2. **Fix the root cause:** update converters, DTOs, transformers, database mappings, or infrastructure; test against the exact failing raw record.
3. **Assess data and ordering:** check whether newer events arrived for that key, check current projection state, and check which side effects already fired.
4. **Plan the replay:** use a dedicated redrive consumer group/worker, preserve record keys and required metadata, and rate-limit replays; decide whether to republish to the main topic or invoke a specialized handler.
5. **Enforce idempotency:** a record may have partially written to the target before timing out, so avoid double-counting, duplicate emails, or double charges.
6. **Monitor and verify:** mark recovered records, reconcile target data against the source, and confirm the DLQ backlog drains as expected.
7. **Restore monitoring:** verify alerts and metrics return to baseline; capture lessons learned in contract tests and docs.

Never delete from a DLT simply because a replay "didn't throw an exception": verify the actual target state. And never delete **Debezium source offsets** just to redrive a consumer message; that can replay massive CDC ranges and cause wider drift.

### Suggested State Model

~~~text
OPEN -> TRIAGED -> FIXED -> REPLAYING -> RESOLVED
                    |           |
                    |           +-> FAILED_REDRIVE -> TRIAGED
                    +-> CANCELLED_WITH_REASON (requires business approval)
~~~

These states are an application-level operational convention, not a built-in enum in Kafka Connect or Debezium.

## 11. Monitoring and Alerting So the DLQ Does Not Become a "Message Graveyard"

A DLT only helps if someone owns resolving it. A pipeline can report `RUNNING` while quietly dumping events into a DLQ and drifting further from the source database.

| Metric / Signal | Interpretation | Operational Question |
|---|---|---|
| Debezium connector/task status | `RUNNING`, `FAILED`, crash loops | Can it still read source logs? |
| Source lag / log position / replication slot lag | Debezium falling behind or logs held open | Is binlog/WAL retention nearing exhaustion? |
| CDC topic throughput | Rate of emitted changes | Did traffic suddenly drop to zero or spike unusually? |
| Kafka consumer lag | Unread records for Spring Integration consumer | Is a handler or adapter stalled? |
| Retry attempts / failures | Error counts and duration by type | Transient issue or poison pill? |
| DLT record count & oldest record age | Unresolved messages and backlog staleness | Is someone triaging and resolving within SLA? |
| DLT producer failures | Failures publishing to the DLT | Is a flawed policy dropping records? |
| Projection consistency | Row counts, keys, business state reconciliation | CDC is running, but is target data accurate? |
| Error-channel backlog | Internal Spring Integration flow errors | Are errors being logged without real recovery? |

Tie alerts to **business impact**, not just raw error counts. One quarantined payment update may be far more urgent than hundreds of rebuildable analytics records. Alert immediately when a DLT goes unmonitored or a new error cluster appears right after a deployment.

## 12. Real-World Scenario: New Schema Halts the Consumer

An order system has:

~~~text
MySQL sales.orders
  -> Debezium MySQL source
  -> Kafka topic shop-cdc.sales.orders
  -> Spring Integration Kafka inbound adapter
  -> orderChangesChannel
  -> orderProjectionHandler
  -> PostgreSQL reporting.orders
~~~

### What Happens

1. The data team adds column `coupon_code` to `sales.orders`.
2. Debezium reads the binlog normally and emits row events containing the new field.
3. The Spring Integration consumer uses an old schema/DTO and fails to parse a record.
4. Without proper error handling, the record retries endlessly and stalls a Kafka partition.

### How to Handle It

**At the Debezium layer:** confirm the task is `RUNNING`, new records hit the topic, and source offsets continue advancing. If so, do not reset the source connector to fix a consumer mapper.

**At the Spring Kafka layer:** configure an error handler classifying permanent converter/schema failures so they do not retry excessively; quarantine the raw record to the DLT with topic/partition/offset and exception details. For deserialization failures, use `ErrorHandlingDeserializer` or an equivalent mechanism so the container can route bad bytes cleanly.

**At the Spring Integration layer:** update the DTO/transformer to accept both pre-DDL and post-DDL events. If messages cross async channels, verify exceptions reach a reliable recovery mechanism.

**During redrive:** check whether newer events exist for each key, apply idempotency/versioning as needed, verify the projection, and close the incident only after target data matches.

### Counterexample: Missing Binlogs at Source

If Debezium stops for several days and MySQL purges the required binlogs, a Spring consumer DLT is **completely unable** to recover events that never reached Kafka. That is a source-layer failure requiring recovery/resnapshot and database-level reconciliation based on actual offset state.

## 13. Practice Exercises

### Exercise 1 — Error Classification

Choose the primary handling strategy for each incident:

| Incident | Fail-fast, Retry, or DLT/Quarantine? |
|---|---|
| A. Debezium MySQL cannot find the binlog for its saved offset | ? |
| B. Spring Integration outbound HTTP adapter hits HTTP 503 for 30 seconds | ? |
| C. A Kafka record has malformed JSON syntax that fails identically on every retry | ? |
| D. A Kafka Connect sink fails to convert a record's data type | ? |
| E. A Kafka tombstone with null value arrives after a valid delete event | ? |

### Exercise 2 — Choosing the Right Tool

A team sets these properties on a **Debezium source connector**:

~~~properties
errors.tolerance=all
errors.deadletterqueue.topic.name=debezium-source-errors
~~~

They expect that if the PostgreSQL replication slot is lost, Debezium will write an "error record" to that Kafka topic and automatically continue. Explain why this expectation is wrong and what mechanism is needed at the source layer.

### Exercise 3 — Can Redrive Regress State?

Two events share the same Kafka key `{"id":42}`:

- `E1`: `op="u"`, `after.status="PAID"`, quarantined to DLT.
- `E2`: `op="u"`, `after.status="SHIPPED"`, processed successfully afterward.

If `E1` is sent back to the main topic and the handler runs an unversioned UPSERT, what happens to the projection? Propose safeguards.

<details>
<summary>Solution Hints</summary>

1. A: stop/alert, inspect source offsets and log recovery options; B: bounded retry with backoff plus idempotency; C: DLT/quarantine until data/consumer is fixed; D: Connect sink DLQ if within supported scope, retaining failing record and metadata; E: process as a valid tombstone per contract rather than defaulting to DLT.
2. Connect sink DLQ settings cannot fabricate records never emitted by the source connector, and losing a replication slot is a source-read/offset failure. Inspect slot/WAL, source offsets, logs, and resumption or reconciled resnapshot options.
3. `E1` can overwrite `SHIPPED` back to `PAID`. Enforce version/order guards, per-key processing locks, or latest-state reconciliation before redrive; never blindly replay an older event.

</details>

## 14. CDC Error-Handling Implementation Checklist

- [ ] Identify whether errors originate in the Debezium source, Kafka Connect sink, Kafka consumer, or Spring Integration flow.
- [ ] Explicitly define handling for special events: `r/c/u/d`, tombstones, heartbeats, schema notifications, and transaction metadata.
- [ ] Choose **fail-fast** for source errors risking data loss; never assume skipped source events are saved to a DLT.
- [ ] If using a Kafka Connect sink DLQ, configure error tolerance, retries, logging, topic, and context headers per connector.
- [ ] If using a Spring Integration Kafka inbound adapter, configure an appropriate listener container error handler and recoverer.
- [ ] Catch deserialization failures before entering channels, preserving raw key/value bytes when needed.
- [ ] Distinguish Spring Integration's `errorChannel` from a physical Kafka DLT.
- [ ] Use bounded retries with backoff for transient errors; define poison-pill isolation rules.
- [ ] Advance consumer offsets only per verified policy after target persistence or confirmed DLT publishing succeeds.
- [ ] Preserve Kafka topic/partition/offset, key/value, and exception context in the DLT; protect sensitive data.
- [ ] Evaluate per-key ordering and idempotency before running redrives.
- [ ] Monitor connector status, source lag, consumer lag, DLQ volume/age, and DLT publish errors.
- [ ] Test crashes during target writes, before offset commits, during DLT publishes, and during replays.
- [ ] Maintain a runbook assigning triage, remediation, reconciliation, and DLQ record closure.

## 15. Technical References

- [Debezium MySQL connector — source error handling configuration](https://debezium.io/documentation/reference/stable/connectors/mysql.html): see `event.processing.failure.handling.mode`, log capabilities, and recovery requirements.
- [Apache Kafka Connect User Guide — Error Reporting](https://kafka.apache.org/44/kafka-connect/user-guide/): scope of tolerance, retries, logging, and dead-letter queues for sink connectors.
- [Apache Kafka Connect Configs](https://kafka.apache.org/44/configuration/kafka-connect-configs/): `errors.*` configuration properties.
- [Spring Kafka — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html): `DefaultErrorHandler`, `DeadLetterPublishingRecoverer`, `ErrorHandlingDeserializer`, and recovery/offset handling.
- [Spring Integration Reference — Kafka Support](https://docs.spring.io/spring-integration/reference/kafka.html): inbound adapters and connecting Kafka to `MessageChannel`s.

The configuration examples in this lesson illustrate mechanics; always cross-check **your exact Debezium, Kafka Connect, Spring Kafka, and Spring Integration versions** before applying.

**Key Takeaway:** Debezium source failures, Kafka Connect sink failures, and downstream Spring Integration failures have **different recovery boundaries**. Dead-lettering preserves existing records that failed processing per policy; it cannot restore purged transaction logs, enforce business ordering on its own, or guarantee exactly-once delivery. A trustworthy CDC pipeline handles failures at the proper layer, protects valid checkpoints, bounds retries, uses durable DLTs, reconciles redrives, and enforces idempotency.
