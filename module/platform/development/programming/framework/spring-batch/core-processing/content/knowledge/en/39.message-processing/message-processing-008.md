# Dead-Letter Messages

In a message-processing system, some messages fail repeatedly even after the consumer retries—for example, syntactically invalid JSON payloads, unsupported schema versions, business data missing required fields, or a message that always causes the processor to throw an exception. If the broker continues redelivering that message, it can block processing progress and create unnecessary load. A **dead-letter message** is a message routed to a separate storage location (a dead-letter queue, dead-letter topic, or quarantine store) after it cannot be processed under the defined policy.

In Spring Batch, you must distinguish dead-letter handling at the broker layer from skip handling at the step layer. A broker may move a message to a DLQ when delivery/acknowledgement fails more than the allowed number of times. Spring Batch can identify an invalid item and skip it within a chunk. The two mechanisms do not automatically replace each other. If a step reads a message and then detects a business error, the application must explicitly decide how to store the failing message, acknowledge the source, and ensure data is neither lost nor processed twice.

## 1. What Is a Dead-Letter Message?

A dead-letter message is a message that cannot continue through normal processing and is routed to an isolated stream for investigation, data repair, or later replay. The destination is commonly called:

- Dead-letter queue (DLQ) for queue-based brokers.
- Dead-letter topic (DLT) for Kafka or topic-based systems.
- Quarantine queue/store when an organization wants to separate quarantined data from a broker-managed DLQ.

Example processing flow:

```text
Input queue / topic
        |
        v
Consumer / Spring Batch reader
        |
        v
Validate + process
        |
        +---- Success ---------> Business writer ----> Commit
        |
        +---- Transient error -> Bounded retry
        |                         |
        |                         +--> Success: continue
        |                         |
        |                         +--> Limit exceeded
        |                                  |
        +---- Permanent error -------------+
                                           |
                                           v
                                   Dead-letter route
                                           |
                                           v
                                   DLQ / DLT / quarantine
```

Messages routed to the dead-letter path must retain enough information to tell where they came from, why they failed, and whether they can be replayed safely. A DLQ is an intentional error store, not a trash bin to discard inconvenient messages.

## 2. Poison Messages and Reasons for Dead-Lettering

A *poison message* is a message that causes an error every time it is processed, typically due to fixed content or state. Some examples:

- Malformed JSON/XML that cannot be parsed.
- Payload missing a required field or containing a wrong type.
- Schema version unsupported by the current application.
- Enum or discriminator value outside the allowlist.
- Non-existent business key or business rule violation.
- Message containing unresolvable references even after source data is confirmed.
- Message exceeding allowed size or nesting depth limits.

Not every failure is a poison message. A temporarily unavailable database, broker timeout, network reset, or deadlock can self-heal. Sending transient errors straight to a DLQ can quarantine valid data merely because infrastructure suffered a brief outage.

## 3. Classifying Errors Before Choosing Retry or Dead-Letter

The handling policy should distinguish at least three groups:

| Error Group | Example | Typically Appropriate Action |
|---|---|---|
| Transient infrastructure error | Timeout, broker unavailable, deadlock, connection reset | Bounded retry with backoff and jitter |
| Permanent data/contract error | Invalid JSON, unsupported schema, missing required field | Dead-letter or quarantine |
| Business rejection | Order cancelled, amount over limit, invalid state | May record a business rejection result; DLQ only if investigation/replay is needed |

A business rejection can be a valid business outcome rather than a technical failure. For instance, a customer with insufficient credit might be recorded with status `REJECTED` without necessarily routing the message to a DLQ. Conversely, a payload missing `customerId` may be a contract violation that needs isolation.

Error classifiers should rely on exception types, business error codes, and message context. Avoid relying solely on exception message text, as wording can change across libraries/versions.

## 4. Retrying Before Moving to a DLQ

A common policy is retrying transient errors before dead-lettering:

```text
Attempt 1 -> transient error -> wait backoff
Attempt 2 -> transient error -> wait backoff
Attempt 3 -> transient error -> wait backoff
Attempt 4 -> limit exceeded -> DLQ
```

Retries should define:

- Maximum attempt count.
- Increasing backoff or suitable fixed delay.
- Jitter so many consumers do not retry in lockstep.
- Overall timeout and maximum message retention duration.
- Classification of retryable vs. non-retryable exceptions.
- Metrics for retry count, delivery count, and final outcome.

Do not retry infinitely. One permanently failing message will occupy workers, increase broker load, and delay valid messages behind it.

## 5. Spring Batch Retry vs. Broker Redelivery

Spring Batch fault tolerance can retry an item or chunk per step configuration. Meanwhile, the broker has its own redelivery mechanism when a message is not acknowledged or an offset is not committed.

Both layers can operate together:

```text
Broker delivery attempt
        |
        v
Spring Batch chunk attempt
        |
        +--> Step-level retry
        |       |
        |       +--> succeeds: chunk commits
        |       +--> retries exhausted: step handles skip/fail
        |
        +--> transaction rollback / no acknowledgement
                |
                v
           Broker redelivery
```

If both Spring Retry and the broker retry, actual processing attempts can exceed each layer's individual limit. Designate one primary retry owner for each error category, or explicitly compute total attempt counts.

## 6. Spring Batch Skip Is Not Automatically Dead-Lettering

In a fault-tolerant step, Spring Batch can skip an item when the exception is skippable and `skipLimit` has not been reached. Skipping means the item does not proceed through the step's normal processing path. It does not automatically send the message to a DLQ.

Example:

```java
return new StepBuilder("processMessagesStep", jobRepository)
        .<InboundMessage, ProcessedMessage>chunk(100, transactionManager)
        .reader(messageReader)
        .processor(messageProcessor)
        .writer(messageWriter)
        .faultTolerant()
        .skip(InvalidPayloadException.class)
        .skipLimit(50)
        .build();
```

This configuration only allows the step to skip a number of `InvalidPayloadException` errors. It does not yet persist failing messages to a DLQ. To dead-letter them, add a persistence/quarantine mechanism such as a `SkipListener`, a broker error handler, or an outbox writer.

Do not configure a broad `skip(Exception.class)` just to keep the job going. Doing so can hide database failures, programming bugs, or infrastructure outages that ought to fail the step.

## 7. Using SkipListener to Record Skipped Items

`SkipListener` provides callbacks when items are skipped during read, process, or write. For process/write errors, the callback receives the corresponding item and can persist details into a quarantine/outbox store.

```java
public class MessageSkipListener
        implements SkipListener<InboundMessage, ProcessedMessage> {

    private final DeadLetterOutboxRepository outboxRepository;

    public MessageSkipListener(DeadLetterOutboxRepository outboxRepository) {
        this.outboxRepository = outboxRepository;
    }

    @Override
    public void onSkipInProcess(InboundMessage item, Throwable error) {
        outboxRepository.save(DeadLetterRecord.from(
                item.messageId(), item.payload(), "PROCESS", error));
    }

    @Override
    public void onSkipInWrite(ProcessedMessage item, Throwable error) {
        outboxRepository.save(DeadLetterRecord.from(
                item.messageId(), item.originalPayload(), "WRITE", error));
    }

    @Override
    public void onSkipInRead(Throwable error) {
        // No item is passed to this callback.
        // The reader must retain raw message/metadata to quarantine read failures.
    }
}
```

Example registering the listener:

```java
.faultTolerant()
.skip(InvalidPayloadException.class)
.skipLimit(50)
.listener(messageSkipListener)
```

This is an illustrative example; `InboundMessage`, `ProcessedMessage`, and the repository are application models. In `onSkipInRead`, Spring Batch supplies only the exception, not an item, because the reader failed to return a valid item. If raw payloads must be saved on parse failures, the reader must retain the envelope/raw bytes and error metadata, or delegate handling to a broker-level error handler.

## 8. Writing Dead-Letters via Transactional Outbox

If a step both writes to a database and needs to send messages to a broker DLQ, do not assume the database transaction and broker send are atomic. A safer approach is writing a dead-letter record into an outbox table in the same chunk database transaction, and having a separate publisher forward that record to the broker.

Example table:

```sql
CREATE TABLE dead_letter_outbox (
    dead_letter_id  VARCHAR(100) PRIMARY KEY,
    original_id     VARCHAR(100) NOT NULL,
    source_name     VARCHAR(300) NOT NULL,
    payload         TEXT NOT NULL,
    error_code      VARCHAR(100) NOT NULL,
    error_message   VARCHAR(1000),
    failed_at       TIMESTAMP NOT NULL,
    published_at    TIMESTAMP NULL
);
```

Inside `SkipListener`, write the outbox record using a repository participating in the step's database transaction when configuration permits. Spring Batch invokes skip listeners right before the chunk transaction commits; thus, an outbox repository sharing the same transaction manager/`DataSource` can commit the dead-letter record alongside checkpoints and business data.

A separate publisher reads unpublished outbox rows, sends them to the DLQ, and updates their status. If the broker accepts the message and the publisher crashes before setting `published_at`, the publisher may resend. Therefore, dead-letter records need stable IDs and consumer/operator tooling must deduplicate.

Outbox provides durable retry capability for DLQ publishing; it does not turn the database and broker into a single distributed transaction.

## 9. Broker-Managed DLQ vs. Application-Managed Quarantine

Two places can decide to dead-letter:

**Broker-managed DLQ:** the broker moves a message to a DLQ after delivery/acknowledgement fails per its redelivery policy or consumer error handler. This is a broker/integration-container mechanism.

**Application-managed quarantine:** the application received and read the message, then determined the payload or business data is invalid. The application persists the message to quarantine/DLT according to its own policy.

| Criterion | Broker-Managed DLQ | Application Quarantine |
|---|---|---|
| Timing | When broker/consumer infrastructure determines delivery failed | After the application parses/validates/processes |
| Typical cause | Consumer fails to ack, listener keeps throwing, delivery limit exceeded | Invalid schema, business validation failure, unsupported payload type |
| Error details | Delivery count, broker headers, listener exception per integration | Can attach error code, stage, validation details, and `JobExecution` ID |
| Configuration | Broker redelivery policy, listener container error handler | `SkipListener`, outbox, custom writer/reader, or application service |
| Scope | Broker/provider-dependent | Application-managed |

Avoid letting both the broker and the application dead-letter the same failure without clear rules. That can create duplicate DLQ entries or route messages multiple times.

## 10. JMS Dead-Letter Queues

With JMS, brokers typically provide redelivery policies and dead-letter destination configurations. When a message rolls back or goes unacknowledged, the broker can redeliver it. After the maximum delivery count, the broker moves the message to the DLQ per provider configuration.

Useful JMS metadata:

- `JMSMessageID`: provider-generated message identifier.
- `JMSCorrelationID`: links the message to another request/flow.
- `JMSRedelivered`: indicates whether the message was previously delivered per JMS semantics.
- `JMSXDeliveryCount`: delivery count when the provider supports this standard property.
- Application properties: event ID, source system, schema version, or batch ID.

DLQ names, redelivery limits, delays, poison-message handling, and exception storage are usually configured per broker such as ActiveMQ Classic, Artemis, or other providers. The JMS API does not mandate a single destination named `DLQ` across all brokers.

When using a Spring JMS listener container, error handling and transaction settings determine when sessions roll back and whether the broker redelivers. With a custom Spring Batch `ItemReader`, ensure messages are not acknowledged before the chunk completes if rollbacks are expected to return messages to the source.

## 11. Kafka Dead-Letter Topics

Kafka has no built-in broker-level DLQ like a fixed queue destination. A common convention is creating a separate topic, such as:

```text
orders.input
orders.input.DLT
```

Consumers or listener error handlers send failing records to the DLT after retries are exhausted. The DLT typically preserves the original payload and adds headers for the original topic/partition/offset along with exception details.

In a Spring Kafka listener container, you can use `DefaultErrorHandler` with `DeadLetterPublishingRecoverer` to retry and then publish failed records to a DLT. Conceptual example:

```java
@Bean
DefaultErrorHandler kafkaErrorHandler(
        KafkaTemplate<Object, Object> template) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(template);

    return new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 2L)
    );
}
```

Then attach the common error handler to the listener container factory according to your Spring Kafka version. Constructors, generic types, destination resolvers, and header behaviors can differ across versions; verify against your application dependencies.

**Note:** `DefaultErrorHandler` is a mechanism of the Spring Kafka listener container. It is not invoked automatically when Spring Batch uses a custom Kafka `ItemReader` or the consumer API directly. With readers managing polls/offsets manually, the application must implement dead-letter routing and commit offsets appropriately.

## 12. Kafka DLT Headers and Preserving Record Origin

When moving a record to a DLT, retain metadata so the original record can be traced accurately:

- Original topic.
- Original partition.
- Original offset.
- Original timestamp.
- Original key.
- Consumer group or application identity if needed.
- Exception class and sanitized error description.
- Delivery/retry attempt.
- Correlation ID, event ID, and schema version.

Spring Kafka's `DeadLetterPublishingRecoverer` can attach origin headers following framework conventions. Check header names in your version and avoid adding duplicate headers with conflicting names.

If the DLT needs to preserve the same partition number, the target topic must have enough partitions or the destination resolver must pick a valid partition. Otherwise, publishing can fail. Never assume a DLT topic automatically has matching partition counts.

## 13. Dead-Lettering in a Message-Reading Spring Batch Step

When Spring Batch reads messages with a custom reader, errors can occur at different stages:

1. Error receiving the message from the broker.
2. Error deserializing the payload in the reader.
3. Error validating or processing in the processor.
4. Error writing results in the writer.

Each stage has different available context and transaction behavior.

| Stage | Is a Valid Item Passed to Callbacks? | Common Handling |
|---|---|---|
| Broker receive/poll | Often only raw record/metadata exists | Broker error handling or reader retains envelope |
| Deserialization in `read()` | Usually no typed item exists yet | Save raw payload/headers before parsing; custom exception/quarantine |
| `process()` | Input item available | `SkipListener.onSkipInProcess` can write dead-letter record |
| `write()` | Output item available; original payload may be needed | `SkipListener.onSkipInWrite` or custom error handling |

`SkipListener.onSkipInRead(Throwable)` receives no item. If the reader parses payloads and throws an exception before returning an item, the reader must keep raw bytes, source partition/offset, or message ID so a dead-letter record can be created.

If the message is still held by a broker transaction, decide how DLQ publishing and input acknowledgement coordinate. Writing raw payloads to a database outbox and committing the transaction is one option, provided the input message is acknowledged only after the outbox record is durable.

## 14. Never Acknowledge Before the Dead-Letter Is Durable

Suppose an application receives a failing message and sends it to a DLQ. If the application acknowledges the source message first and then publishing to the DLQ fails, the original message can be lost with no dead-letter copy.

Unsafe order:

```text
Receive source message
       |
       v
ACK source message
       |
       v
Publish to DLQ fails
       |
       v
Message lost
```

A safer order in a local-transaction model:

```text
Receive source message
       |
       v
Persist dead-letter intent (e.g. DB outbox)
       |
       v
Commit durable record
       |
       v
ACK source message
       |
       v
Publisher retries delivery to DLQ
```

Exact details depend on the broker and how consumer transactions operate. The goal is always having at least one durable copy of the failing message before confirming the source. If both database and broker support XA, transactions can be coordinated; otherwise, outbox/inbox with idempotency is the common choice.

## 15. DLQs and Chunk Rollbacks

A chunk can contain multiple messages. If one item fails in the processor and is skipped, Spring Batch may roll back/replay the chunk per its fault-tolerance algorithm before finalizing the skip. `SkipListener` is invoked according to the skip lifecycle, and callbacks are designed to avoid duplicate invocations for the same skip during internal chunk rollbacks.

However, sending directly to a broker DLQ from a callback or processor is a side effect outside the database transaction if no transaction coordinator exists. If the chunk rolls back after a successful DLQ publish, the item may be reprocessed and publish a duplicate.

To control this:

- Use a stable dead-letter ID, typically derived from the source message ID or topic/partition/offset.
- Write outbox records inside the chunk's database transaction.
- Have the publisher send outbox records at-least-once and let DLQ consumers deduplicate.
- Never delete/ack source messages before the durable intent commits.
- Test crash points between persistence, publishing, and acknowledgement.

## 16. Structuring the Dead-Letter Envelope

Do not send a bare exception string to a DLQ. Define a structured envelope so operators and replay tools can interpret it:

```json
{
  "deadLetterId": "dlq-8b5f...",
  "originalMessageId": "event-12345",
  "source": {
    "system": "orders-service",
    "destination": "orders.input",
    "partition": 2,
    "offset": 9812
  },
  "payloadType": "ORDER_CREATED",
  "schemaVersion": 3,
  "failedStage": "PROCESS",
  "errorCode": "CUSTOMER_NOT_FOUND",
  "errorType": "InvalidOrderException",
  "failedAt": "2026-11-15T10:30:00Z",
  "attempts": 3,
  "correlationId": "corr-456",
  "payload": {
    "orderId": 1001,
    "customerId": 9999
  }
}
```

This is an illustrative schema. A real envelope should specify:

- Whether the original payload is preserved byte-for-byte or deserialized/reserialized.
- Which headers are copied and which are normalized.
- Whether error messages may contain sensitive data.
- Payload size limits and how large attachments are stored.
- Timestamps in UTC with a consistent format.
- Schema version of the dead-letter envelope itself.
- TTL/retention and access permissions.

When possible, retain the original raw payload so replays are not altered by current serializers. At the same time, store parsed snippets or an error summary to simplify investigation.

## 17. Never Expose Sensitive Data in DLQs

DLQs are often accessible to operations teams or replay tooling with broader access than the business application itself. Therefore, payloads in a DLQ must be protected like source data.

Measures to consider:

- Encrypt data in transit and at rest.
- Dedicated ACLs/authorization for DLQs, granting only necessary access.
- Never put passwords, tokens, session keys, or secrets in headers/logs.
- Mask or strip personal data from error summaries when unnecessary.
- Bound retention and enforce deletion policies per legal requirements.
- Audit read, export, replay, and purge actions.
- Enforce message size limits so oversized payloads cannot exhaust storage.

Do not log entire raw payloads on parse errors. Log `deadLetterId`, `messageId`, `source`, `errorCode`, and `correlationId` so authorized users can look up the record.

## 18. Redriving and Replaying from a DLQ

**Redrive** means sending a message from the DLQ back into the processing flow, typically after the underlying error is fixed. **Replay** means re-running stored messages, either into the original input destination or a dedicated replay pipeline.

A redrive procedure should include:

1. Identify the root cause and fix code, configuration, or reference data.
2. Select the exact messages by batch ID, event ID, timestamp, or error code.
3. Verify messages are still valid under the current schema.
4. Check whether prior side effects already occurred.
5. Replay a small batch first and observe results.
6. Ramp up replay speed gradually to avoid load spikes.
7. Record replay attempts, operator/job ID, and outcomes.
8. Retain the original DLQ record per retention/audit policy.

Never automatically requeue the entire DLQ immediately after a new deployment finishes. Some messages may still be invalid or may have been partially processed before failing.

## 19. Preserving Original Message IDs on Replay

When replaying, preserve the original message ID/event ID so deduplication recognizes it as the same business event. You can attach separate replay metadata:

```json
{
  "originalMessageId": "event-12345",
  "replayId": "replay-20261115-0042",
  "replayAttempt": 2,
  "replayedAt": "2026-11-15T11:00:00Z",
  "replayRequestedBy": "batch-operations"
}
```

Never replace the original ID with a brand-new UUID and expect the inbox/unique constraint to prevent duplicates. If the system requires a new transport ID, retain both `originalMessageId` and `replayMessageId` to distinguish transport attempts from business event identity.

## 20. Replay and Message Ordering

Replaying old messages can break business ordering. For example, `OrderCreated` was dead-lettered, while `OrderPaid` and `OrderShipped` were already processed. Replaying `OrderCreated` afterward can leave an invalid state.

Before replaying, determine:

- Does the message depend on earlier or later events?
- What is the ordering key or Kafka partition key?
- Have subsequent events already been applied?
- Can you replay by aggregate ID or sequence number?
- Do you need to rebuild the projection from an event log rather than replaying a single message?
- Can idempotency and version checks reject stale events?

For ordered data, replay grouped by aggregate or in defined sequence order. Do not sort solely by dead-letter timestamp, because failure time is not necessarily original business order.

## 21. Kafka Retry Topics and DLTs

In Kafka, you can use retry topics for transient errors needing a delay before retrying, then route to a DLT after exhausting attempts. Example:

```text
orders.input
     |
     +--> processed successfully
     |
     +--> transient error --> orders.retry.1
     |                         |
     |                         +--> retry succeeded
     |                         |
     |                         +--> still failing --> orders.retry.2
     |                                                |
     |                                                +--> orders.DLT
     |
     +--> permanent error -----------------------------> orders.DLT
```

Retry topics decouple retry waiting from the main consumer, though they can alter ordering across records. A record being retried may be processed after a later record on the main topic. If per-key/aggregate ordering is mandatory, design an appropriate retry strategy and understand your framework's semantics.

Spring Kafka provides retry-topic mechanisms such as `@RetryableTopic` for listener-based processing. Those belong to Spring Kafka listener infrastructure; they do not apply automatically to a custom Spring Batch reader. With Batch, retry/DLT can be built using custom readers/writers, outbox tables, and orchestrating steps.

## 22. JMS Redelivery and DLQs

With JMS, messages are typically redelivered when a transacted session rolls back or a message goes unacknowledged per configured mode. The broker tracks delivery counts and applies its redelivery policy. When thresholds are exceeded, the broker moves the message to a dead-letter destination.

Provider settings to verify:

- Maximum redelivery attempts.
- Redelivery delay and exponential backoff.
- Default or per-queue dead-letter destination.
- How original destination and exception metadata are preserved.
- Behavior when the DLQ destination does not exist or is full.
- Message expiration/TTL and DLQ retention.
- Policy for non-persistent messages.

Do not hard-code DLQ names using one broker's convention if the application must run across multiple providers. Externalize destinations into configuration and test against real brokers.

## 23. Spring Kafka DefaultErrorHandler and DeadLetterPublishingRecoverer

With a Spring Kafka listener container, `DefaultErrorHandler` can retry exceptions with backoff and invoke a recoverer once retries are exhausted. `DeadLetterPublishingRecoverer` is a common recoverer for publishing failed records to a DLT.

Conceptual configuration example:

```java
@Bean
DefaultErrorHandler errorHandler(KafkaTemplate<Object, Object> template) {
    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(template);

    FixedBackOff backOff = new FixedBackOff(1_000L, 2L);
    return new DefaultErrorHandler(recoverer, backOff);
}
```

To classify permanent errors that need no retries, configure those exceptions as non-retryable using `DefaultErrorHandler`'s API in your version. Only after the recoverer successfully publishes to the DLT can the container commit/ack the input per error-handler semantics.

This is listener container configuration, not a generic setting for every `ItemReader`. With Spring Batch polling Kafka directly, explicitly integrate producer transactions/offset commits or use an outbox to avoid acking input before the DLT record is durably persisted.

## 24. Full DLQs or Failed DLQ Publishes

A dead-letter destination is itself a resource that can fail:

- DLQ exceeds quota or retention storage.
- Kafka DLT lacks matching partitions.
- Producer lacks publish permissions.
- Broker is unavailable.
- Payload exceeds message size limits.
- Dead-letter envelope serialization fails.

Never acknowledge the source message if the dead-letter record has not been durably persisted per policy. If DLT publishing fails, retain the source message for retry, roll back the transaction, or write to an outbox/database quarantine. Avoid infinite loops of failing DLQ publishes followed by silent redelivery with no alerts.

DLQs also require monitoring for depth, oldest message age, publish failures, and storage utilization. If a DLQ fills up unattended, the system merely shifts backlog from the main queue to an error queue.

## 25. Poison Messages Can Block Partitions or Queues

In FIFO queues or certain ordering models, a poison message at the head can block subsequent messages if the broker enforces ordering and keeps redelivering. In Kafka, a failing record can stop the consumer from committing offsets past that position, stalling the partition.

Dead-lettering after finite attempts lets the consumer move forward, at the cost of ordering. Skipping past the failing offset/message means later records may process before the older record is repaired and replayed.

If ordering is a hard requirement, decide whether the partition/queue should pause, quarantine the entire aggregate, or proceed in a degraded state. That is a business decision, not just a retry setting.

## 26. Dead-Letter Records and Source Lineage

For investigation and replay, preserve source identity:

- Broker type and cluster/environment.
- Original queue/topic.
- Kafka partition/offset or JMS message ID/correlation ID.
- Consumer group/subscription if applicable.
- Event/business ID.
- Batch ID, `JobExecution` ID, and `StepExecution` ID if processed by Spring Batch.
- Payload type/schema version.
- Receive timestamp and failure timestamp.
- Processing stage and error code.
- Delivery count/retry attempt.

If only exception text is stored, it becomes hard later to locate the source message or tell whether it was already processed. Standardize metadata into a versioned envelope and avoid coupling your domain model to a single provider's custom header names.

## 27. Dead-Letter Retention and Operations

DLQs need clear retention policies. Keeping every message forever increases cost and security exposure; deleting too early loses data needed for investigation or replay.

Policies should define:

- Retention period by error type and data classification.
- Who may read, export, replay, and purge.
- Encryption, masking, and access auditing.
- Alert thresholds for message count and oldest message age.
- Triage workflows and accountable owners.
- SLAs for resolving DLQ entries.
- Archival procedures before purging.
- How dead-letter records link to incidents/tickets.

A steadily growing DLQ signals a system defect or upstream contract break, not a normal steady state to ignore.

## 28. Observing Dead-Letters in Spring Batch

Track metrics both per job/step and per broker:

- Total items read, processed, written, filtered, and skipped.
- Dead-letter counts by error code and payload type.
- Retry counts inside Spring Batch.
- Broker delivery/redelivery counts.
- Successful/failed DLQ publishes.
- DLQ depth and oldest message age.
- Redriven message counts and replay outcomes.
- Duplicates detected by inbox/idempotency.
- Batch ID, `JobExecution` ID, `StepExecution` ID, and correlation ID.

Do not write full payloads to logs. Log `deadLetterId`, `originalMessageId`, `source`, `errorCode`, and `correlationId`; store payloads in access-controlled storage.

## 29. Testing Dead-Letter Flows

Unit tests mocking the writer only prove code invokes the right collaborators. Integration tests with a broker and database are needed to verify transactions, acknowledgements, redeliveries, and DLT publishing.

Cases to test:

1. Valid messages process normally and do not enter the DLQ.
2. Transient errors are retried and then succeed.
3. Transient errors exceeding the retry limit are dead-lettered.
4. Permanent errors go straight to quarantine/DLT per policy.
5. Malformed payloads still retain raw payloads and source metadata.
6. Errors in `process()` are captured via `onSkipInProcess`.
7. Errors in `write()` follow configured skip/dead-letter policies.
8. Errors in `read()` do not lose raw messages even though the callback lacks an item.
9. Chunk rollbacks do not lose dead-letter intents or create uncontrolled duplicates.
10. Failed DLQ publishes do not cause source messages to be acked and lost.
11. Message redeliveries are deduplicated by original message ID.
12. Replays preserve original IDs and include replay metadata.
13. Replays grouped by aggregate/partition do not break business ordering.
14. Full DLQs, permission denials, or unavailable brokers trigger alerts and leave recoverable state.
15. Job restarts do not drop messages between Batch checkpoints and broker offsets.

With Kafka, test topics/partitions/offsets and `read_committed` when using producer transactions. With JMS, test session rollbacks, redelivery counts, and provider DLQ behavior. Do not merely check that a message appeared in the DLQ; verify the source message was acked/committed at the right moment.

## 30. Common Misconceptions

**Assuming Spring Batch automatically creates a DLQ when skipping items.** Skip merely removes items from the step flow; you need a listener, outbox, or broker error handler to persist dead-letters.

**Sending every exception straight to a DLQ.** Transient infrastructure errors need retries; permanent data failures typically belong in quarantine.

**Assuming a broker DLQ and application quarantine are the same mechanism.** They operate at different layers and require coordination rules.

**Acknowledging source messages before the DLQ write is persisted.** If DLQ publishing fails, messages can be lost.

**Publishing directly to a DLQ from SkipListener and assuming atomicity with the database.** Broker and database are usually separate local transactions; use outbox or XA when atomicity is needed.

**Assuming `onSkipInRead` provides the failing item.** That callback receives only the exception. The reader must retain raw payloads/metadata or let broker error handling process it.

**Assuming Kafka has a built-in broker-created DLQ.** A DLT is typically an application/platform-created topic published to by an error handler.

**Replaying with a new message ID.** That can break deduplication. Keep original business/event IDs and attach a separate replay ID.

**Replaying the entire DLQ at once.** Can trigger load spikes and break ordering. Filter selectively, replay in batches/by aggregate, and throttle rates.

**Failing to monitor the DLQ.** Quarantined messages without an owner or SLA become a chronic error backlog.

## 31. Designing a Dead-Letter Flow

First, establish which errors are transient, which are permanent, and which business rejections are valid business outcomes. Set clear retry limits, backoff, and timeouts. Dead-letter only when errors are unrecoverable under policy or broker deliveries exceed thresholds.

If the broker manages redeliveries, configure DLQs on the broker/listener container and verify acknowledgement semantics. If Spring Batch has already read an item and the processor detects an error, combine a skip policy with `SkipListener` or a quarantine writer. For parse failures in `read()`, capture raw payloads and source metadata prior to deserialization because `onSkipInRead` has no item to save.

When the database and broker are separate local transactions, write dead-letter intents to an outbox in the database transaction and have a publisher forward them to the DLQ. Retain original message IDs, source topic/queue/partition/offset, payload type, schema version, error code, and retry metadata. Acknowledge source messages only after the dead-letter record is durable under the chosen model.

Build a controlled redrive process: fix root causes, select messages, inspect prior side effects, preserve original IDs, add replay metadata, and replay at a safe rate and order. Protect DLQs with ACLs, encryption, retention, and audits. Test crashes across persistence, publishing, acks, rollbacks, and restarts. A solid dead-letter flow prevents failing messages from stalling pipelines while preserving investigability and replayability without losing or duplicating business effects.
