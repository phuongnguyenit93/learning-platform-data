# Acknowledgment, Visibility Timeout, and Message Retention

In a serverless architecture, a queue or event stream typically connects a producer with one or more consumers. The producer sends a message and can continue its work; the consumer receives the message at a suitable time and processes it independently. This decoupling helps absorb traffic spikes, regulate processing rates, and recover when a component is temporarily unavailable.

However, sending a message successfully does not mean the message has finished being processed. The system needs to know when the consumer has completed, when a message should be redelivered, and how long a message is stored before expiring. Three concepts that must be clearly understood are **acknowledgment (ack)**, **visibility timeout or acknowledgment deadline**, and **message retention**.

Ack confirms that the consumer has processed the message according to the broker's rules. Visibility timeout or deadline defines how long a consumer can hold a message for processing before it can be redelivered. Retention defines how long the broker stores a message or record. Misconfiguration can cause message loss, duplicate processing, premature retries, growing backlogs, or messages expiring before they are processed.

## 1. Message Lifecycle in a Queue

A message typically goes through the following conceptual states:

~~~mermaid
stateDiagram-v2
    [*] --> Available: Producer publishes
    Available --> InFlight: Consumer receives
    InFlight --> Completed: Ack / Complete
    InFlight --> Available: Nack / Release / Visibility expires
    InFlight --> InFlight: Extend visibility or lock
    Available --> Expired: Retention expires
    InFlight --> Expired: Retention expires per broker policy
    Available --> DeadLetter: Exceeds delivery limit
    InFlight --> DeadLetter: Unrecoverable error / redrive policy
    Completed --> [*]
    Expired --> [*]
    DeadLetter --> [*]
~~~

This is a general model. Each broker has its own state names, confirmation mechanisms, and storage rules. For example, some queues delete messages after ack; an event stream may retain records until retention expires even after consumers have committed offsets.

Basic steps:

1. The producer publishes a message and the broker confirms receipt.
2. The message enters a state eligible for delivery to a consumer.
3. The consumer receives the message; the broker marks the message as in-flight or tracks the read position.
4. The consumer executes business logic and persists results durably.
5. The consumer sends ack, complete, or commits an offset per the broker's model.
6. If the consumer fails or does not confirm in time, the broker can redeliver or continue serving records from the committed position.
7. If the message is not processed within the retention period or exceeds delivery limits, the broker may drop it or move it to a dead-letter queue.

Distinguish **publish acknowledgment** from **consumer acknowledgment**. Publish acknowledgment confirms that the broker received the message from the producer. Consumer acknowledgment confirms a processing step on the receiving side. These two events occur at different times and carry different meanings.

## 2. Acknowledgment: Confirming Successful Processing

Acknowledgment is the signal a consumer sends to the broker indicating that a message has been processed to the point where it can be considered complete under the contract. Depending on the service, this operation may be named ack, delete, complete, or commit offset.

Typically, a consumer should only ack after business results are durably persisted. If it acks before writing data, the function could be terminated after the ack but before the business commit; the broker believes the message is complete and will not redeliver it, leading to lost work.

Example of an unsafe sequence:

~~~text
Receive message
    |
    v
Ack message
    |
    v
Write database
    |
    X  Function terminates
~~~

The broker treats the message as completed, yet the database has no result.

Safer sequence:

~~~text
Receive message
    |
    v
Validate + process
    |
    v
Commit durable result
    |
    v
Ack message
~~~

If the function stops after committing to the database but before acking, the message can be redelivered. Thus, this ordering reduces the risk of losing work, though it can still cause duplicate processing. The consumer needs idempotency so that delivering a message multiple times does not produce duplicate side effects.

### Ack, Nack, and Handling Options

Queue systems commonly offer several equivalent actions:

| Action | Meaning | Typical Outcome |
|---|---|---|
| Ack / Complete | Confirm processing finished | Broker removes the message from the pending queue or marks it read |
| Nack / Reject | Reject the message | May return the message to the queue, dead-letter it, or drop it depending on config |
| Release / Abandon | Release an unfinished message | Message may be redelivered immediately or after a delay |
| Extend / Renew | Extend message hold duration | Consumer gets more time before the message can be redelivered |
| No ack | Send no confirmation | Broker handles it when visibility/lock/deadline expires |

Do not use nack for every exception. A permanent data error like an invalid schema may loop endlessly if simply returned to the queue. Conversely, a transient error like a database timeout may need retrying after a backoff delay. Classify errors and configure appropriate redrive or dead-letter handling.

### Ack Does Not Create Exactly-Once Side Effects

An ack is usually not part of the same transaction as a database or external API. A consumer might write to the database successfully while the ack fails; the broker then redelivers the message. Or a consumer might ack successfully while the business write was not truly durable due to improper transaction handling.

Therefore, never assume that because a broker supports ack, business logic is automatically processed strictly once. Design consumers to tolerate duplicate delivery and use idempotency keys or deduplication wherever business state is stored.

## 3. Visibility Timeout and Acknowledgment Deadline

With pull-based queues, when a consumer receives a message, the broker typically hides it temporarily from other consumers. That duration is called **visibility timeout**, **acknowledgment deadline**, or lock duration, depending on the platform.

If the consumer acks before the deadline expires, the message is considered complete. If the consumer neither acks nor extends, the message can become eligible for delivery again so another consumer can process it.

Example:

~~~text
t = 0s       Consumer A receives message
             Message moves to InFlight

t = 10s      Consumer A is still processing
             Other consumers cannot see the message yet

t = 30s      Visibility timeout expires
             No ack or extension received

t = 31s      Message can be delivered to Consumer B
             Consumer A may still be running if not stopped
~~~

The last point is crucial: visibility timeout expiration does not necessarily cancel the old invocation. If Consumer A keeps running after the message is redelivered to B, two consumers can execute side effects concurrently. Idempotency and conditional writes remain necessary even when visibility timeouts are configured.

### Choosing a Visibility Timeout

The visibility timeout must be long enough for the consumer to finish normal work, including processing time and reasonable dependency jitter. If too short, messages are redelivered while the original consumer is still running, increasing concurrency and duplicate processing. If too long, failed messages wait a long time before getting retried.

Consider these factors:

- p95/p99 processing time, not just the average.
- Maximum duration of an invocation or batch handler.
- Time to call databases, partner APIs, and persist results.
- In-invocation internal retry duration.
- Function shutdown or timeout duration.
- Retry policy and delay before the next delivery attempt.

There is no single number suitable for every queue. For example, if a consumer normally finishes in a few seconds but occasionally takes tens of seconds to call a partner service, the visibility timeout must be chosen based on the latency distribution and platform limits. For highly variable task durations, extending visibility may be better than setting a very long timeout for every message.

### Extending Visibility or Locks

If processing may exceed the initial deadline, the consumer can extend the message hold duration before it expires. Some platforms support changing visibility timeout, modifying ack deadlines, or renewing locks.

Design extension as a controlled mechanism:

1. Define the maximum processing duration permitted by the business logic.
2. Renew before the current deadline expires, leaving sufficient buffer for network latency.
3. Stop renewing once processing completes or a decision is made to abandon the message.
4. Cap total message hold duration based on policy and maximum execution time.
5. If renewal fails, assume the message may be delivered to another consumer; protect side effects with idempotency.
6. Monitor extension counts and unusually long-held messages.

Do not extend indefinitely to mask a hung consumer. If work exceeds reasonable limits, break it into smaller steps, persist checkpoints, or move to workflow orchestration.

## 4. Message Retention: How Long Does the Broker Keep Messages?

**Message retention** is how long the broker keeps a message or record before it expires under the storage policy. Retention differs from visibility timeout:

- Visibility timeout controls how long an in-flight message is held for processing before it can be redelivered.
- Retention controls how long a message exists in the broker's storage system.

A message can be invisible to consumers during its visibility timeout while still stored in the broker. When visibility expires, the message can be redelivered if retention has not expired. If retention expires before a consumer processes it, the message may be deleted or become unavailable, depending on service semantics.

Example:

~~~text
Publish
  |
  +---- Message stored by broker -----------------------------+
  |                                                           |
  |  Consumer receives                                        |
  |      |                                                    |
  |      +-- Visibility timeout: message temporarily hidden   |
  |      |       |                                            |
  |      |       +-- Expires: eligible for redelivery         |
  |      |                                                    |
  |      +-- Ack: completed under queue model                 |
  |                                                           |
  +---- Retention expires: broker drops expired message ------+
~~~

### Choosing a Retention Period

Retention must align with recovery capabilities and the outage duration the system needs to tolerate. Consider:

- How long can consumers be down while the business still wants catch-up processing?
- Are there extended maintenance or deployment windows?
- What is the expected peak backlog during traffic spikes?
- Is post-recovery processing throughput fast enough to catch up with the producer?
- Do messages contain sensitive data or data subject to deletion deadlines?
- Do events need to be kept for replay, audit, or projection rebuilds?
- How do storage volume and costs grow with longer retention?

Retention that is too short can cause messages to expire during consumer outages or large backlogs. Retention that is too long increases costs, extends how long sensitive data lingers, and can cause consumers to re-read stale events if replay processes are poorly controlled.

Do not pick retention based only on normal processing time. Factor in outage duration, detection time, remediation, and backlog draining. If long-term storage is needed for auditing, consider a dedicated archive rather than using a queue as a long-term data store.

### Retention Differs Between Queues and Event Streams

Queues and event streams both use the word "retention," but their semantics differ:

- **Queue:** messages are typically removed from the pending set after a consumer acks successfully; retention limits how long incomplete messages can stay. Some services have separate retention for dead-letter queues.
- **Event stream/log:** records are typically kept by time or size even after consumers have read them. Consumers record offsets to remember read positions; committing an offset does not delete the record from the log.
- **Compacted log:** some streams retain the latest value per key and discard older records under a compaction policy, rather than deleting immediately on consumer confirmation.

Therefore, do not apply queue visibility timeout mental models directly to Kafka or a partitioned log stream. Use the corresponding broker concepts instead.

## 5. Comparing Semantics Across Platforms

Exact API names and rules vary across providers. The table below maps concepts across platforms and does not replace the configuration documentation for your specific service.

| System | Processing Confirmation | Redelivery / Hold Mechanism | Retention |
|---|---|---|---|
| Amazon SQS | Consumer deletes message using receipt handle after processing | Visibility timeout; can change or extend visibility | Messages kept up to configured retention if not deleted |
| Google Cloud Pub/Sub | Consumer acks message | Ack deadline; can modify deadline or let it expire | Message retention per subscription/topic policy |
| Azure Service Bus | Consumer completes message | Message lock; abandon or let lock expire for redelivery, lock can be renewed | Message TTL and entity policy |
| Apache Kafka | Consumer commits offset for partition | Records re-read if offset is uncommitted or reset; no queue-style per-message visibility timeout | Time/size-based retention; records are not deleted merely because a consumer commits |

Notes:

- SQS standard queues can deliver messages multiple times and do not guarantee strict ordering. FIFO queues have dedicated ordering and deduplication semantics, though deduplication scope still needs to be understood.
- Pub/Sub has ack deadlines and delivery attempts; if exactly-once delivery is configured, understand its scope, limits, and how it differs from database side effects.
- Azure Service Bus has lock tokens and complete, abandon, defer, and dead-letter actions; lock duration and renewal have limits.
- Kafka tracks consumer progress via per-partition offsets. Committing an offset before processing completes can skip records after a crash; committing after processing can cause duplicate processing. Coordinating offsets with external side effects requires an explicit strategy.

Before deploying, verify the exact broker in use, queue/subscription/stream type, delivery mode, timeouts, and actual retention settings.

## 6. Relationship Between Ack, Visibility, Retries, and Dead-Letter Queues

Ack and visibility determine whether a message continues to be redelivered. Retry policies determine how long the system waits, how many times it retries, and when it stops. A dead-letter queue (DLQ) isolates messages that cannot be processed within policy limits.

A typical retry flow:

~~~mermaid
flowchart TD
    A["Message available"] --> B["Consumer receives"]
    B --> C["Execute business logic"]
    C --> D{"Success?"}
    D -->|"Yes"| E["Commit durable result"]
    E --> F["Ack / Complete"]
    D -->|"Transient error"| G["Nack / Release or let timeout expire"]
    G --> H["Backoff / Delay"]
    H --> A
    D -->|"Permanent error"| I["Reject / Dead-letter"]
    D -->|"Exceeds max delivery"| I
    I --> J["DLQ: investigate and handle safely"]
~~~

Classify errors before retrying:

| Error Type | Examples | Typical Appropriate Action |
|---|---|---|
| Transient error | Database timeout, throttling, dependency 503 | Bounded retry with backoff and jitter |
| Data error | Malformed JSON, missing required field, unsupported schema | Dead-letter or quarantine for investigation |
| Business error | Order already canceled, state disallows operation | Record business rejection outcome; do not retry endlessly |
| Config/permission error | Wrong credentials, missing IAM permission | Alert and fail fast if fix requires config change |
| Unknown error | Crash, process killed, connection dropped | Broker may redeliver; consumer must be idempotent |

A DLQ needs an operational process:

- Monitor message count and age in the DLQ.
- Record error details and necessary delivery metadata without logging sensitive payloads.
- Identify root cause before redriving.
- Fix code, schemas, or data before replaying.
- Preserve event IDs or business keys during replay so idempotency continues working.
- Throttle redrive rates to avoid bursts that overload consumers or databases.
- Define who is authorized to read, edit, and replay messages.

A DLQ does not fix errors automatically. Without alerts and remediation workflows, it simply becomes a place where messages are forgotten.

## 7. Idempotency and Duplicate Delivery

At-least-once delivery means the broker can deliver a message more than once. This happens when a consumer finishes processing but the ack is lost, an invocation crashes, visibility expires, or a consumer loses partition ownership before committing offsets.

Consumers should rely on a stable event identifier, such as a producer-generated `eventId`. Before executing side effects, the consumer checks whether the event has already been applied.

Example deduplication table model:

| Field | Role |
|---|---|
| `consumerName` | Distinguishes progress across logical consumers |
| `eventId` | Unique event identifier |
| `status` | `PROCESSING` or `COMPLETED` |
| `processedAt` | Completion timestamp |
| `resultRef` | Result reference if needed |
| `expiresAt` | Expiration timestamp of the deduplication record |

The unique key can be `(consumerName, eventId)`. Claiming and recording the outcome require a transaction or atomic conditional write. If two invocations receive the same event concurrently, only one is allowed to claim it; the other checks the status and skips repeating side effects.

When the database and side effects live in separate systems, a single transaction cannot automatically guarantee both complete together. For example, a consumer writes to the database and then calls a payment provider. If the function crashes between those two steps, the state can be ambiguous. Use provider idempotency keys if supported, persist payment attempt state, and build reconciliation processes. For events emitted from a database transaction, a transactional outbox bridges the gap between data commit and event publish.

Deduplication record retention must be long enough to cover the window during which messages may be redelivered or replayed. If message retention is 7 days while dedup records expire after 1 day, a message replayed on day 3 could re-execute side effects. For financial operations or irreversible side effects, retain business operation IDs longer than the broker keeps messages.

## 8. Batch Processing and Partial Acknowledgment

Some triggers pass multiple messages into a single invocation to reduce overhead. When processing batches, clarify ack semantics per message versus per batch.

If a consumer processes 10 messages and the 8th fails, there are two common handling modes:

- **Ack the whole batch after all succeed:** if the batch is retried, messages 1–7 may be reprocessed.
- **Partial batch response:** confirm successfully processed messages and request redelivery only for failed ones, if supported by the broker and event source mapping.

Conceptual logic example:

~~~java
List<String> failedMessageIds = new ArrayList<>();

for (Message message : batch) {
    try {
        processor.processIdempotently(message);
    } catch (RetryableException ex) {
        failedMessageIds.add(message.id());
    } catch (PermanentMessageException ex) {
        deadLetterPublisher.publish(message, ex);
        // Only mark complete after quarantine is durable.
    }
}

return BatchResult.withFailures(failedMessageIds);
~~~

This is illustrative pseudocode; the actual batch response format depends on the provider's adapter. On platforms that require throwing an exception to retry the entire batch, consumers must be idempotent per message. With partial acknowledgment, verify the exact IDs to return and how the broker handles unlisted items.

Large batches can boost throughput, but also increase invocation duration, memory usage, and retry blast radius. Size batches based on processing time, payloads, concurrency, and dependency limits. Avoid grouping too many messages if one slow message can stall the entire batch.

## 9. Designing Java Consumers for Serverless

Java consumers should separate broker adapters from business logic. The adapter translates messages and context into internal types; the application service validates schemas, permissions, and state; the repository persists outcomes; the adapter acks per the trigger contract.

Conceptual structure example:

~~~java
public final class OrderEventHandler {
    private final OrderProcessor processor;

    public OrderEventHandler(OrderProcessor processor) {
        this.processor = processor;
    }

    public void handle(Message message, MessageContext context) {
        try {
            OrderEvent event = eventMapper.validateAndMap(message.body());

            // Must be idempotent and persist results durably.
            processor.process(event);

            // Adapter only acks after processing completes.
            context.ack();
        } catch (RetryableException ex) {
            context.retryLater(ex);
        } catch (PermanentMessageException ex) {
            context.deadLetter(ex);
        }
    }
}
~~~

`Message`, `MessageContext`, `OrderEvent`, and the ack/retry/DLQ methods are abstractions, not a universal API across all Java serverless runtimes. Some platforms manage acknowledgment automatically via invocation return values or event source mappings; in those cases, the adapter must follow the specific contract rather than calling a hypothetical ack function.

Implementation principles:

- Parse and validate the envelope before executing business logic.
- Use stable event IDs to deduplicate.
- Persist business results durably before confirming.
- Do not swallow exceptions if the runtime relies on exceptions to trigger retries.
- Distinguish retryable errors from permanent errors.
- Set dependency timeouts shorter than the remaining invocation time.
- Keep message bodies small; for large payloads, store objects and pass access-controlled references.
- Never store deduplication state in static fields.
- Log event IDs, correlation IDs, and processing outcomes without logging secrets or full payloads.

When using a framework with a listener container, understand its ack modes: auto acknowledgment, manual acknowledgment, batch acknowledgment, or offset commit. Misconfiguration can cause the framework to ack before a transaction finishes or commit offsets prematurely.

## 10. Configuring Timeouts and Retention for Real Load

Visibility timeout, invocation timeout, dependency timeout, and retention are related yet serve distinct purposes.

| Parameter | Question to Answer |
|---|---|
| Function timeout | How long is a single invocation allowed to run? |
| Visibility/lock/ack deadline | How long does the broker wait for confirmation or renewal before redelivering? |
| Dependency timeout | How long should a database or external API call wait at most? |
| Retry delay/backoff | On a transient error, how long does the consumer wait before retrying? |
| Max delivery/receive count | How many times is a message tried before dead-lettering? |
| Message retention | How long does the broker retain uncompleted messages at most? |
| DLQ retention | How long are quarantined messages kept for investigation or replay? |
| Deduplication retention | How long does the system remember that an event was already applied? |

One configuration rule is that visibility/lock must be long enough for valid processing plus buffer, or be renewed properly. Function timeout should bound invocation duration; dependency timeout must be smaller than the remaining time so the function can save state or handle errors. Retention needs to be long enough to survive expected outages and backlogs.

As an illustrative example, suppose p99 message processing is 18 seconds, total dependency timeout is capped at 8 seconds, and saving results/acking takes around 2 seconds. A team might choose a visibility timeout significantly larger than typical processing time, say 30–45 seconds, and validate under load against the actual invocation timeout. This is merely a starting point for testing, not a universal default across platforms.

### Backlog and Drain Time

Retention should be compared against the time needed to drain a backlog. If producers send 100 messages/second while consumers only handle 80 messages/second, the backlog grows by 20 messages/second. Once producers stop or slow down, consumers need spare capacity to clear the backlog before messages hit retention expiration.

Drain time can be roughly estimated as:

\[
T_{drain} \approx \frac{N_{backlog}}{R_{consumer} - R_{producer}}
\]

This formula only makes sense when consumer rate exceeds producer rate during the drain phase and throughput is relatively steady. If the two rates are equal or consumer rate is lower, the backlog does not shrink. In practice, factor in retries, batching, throttling, partitions, dependencies, and processing time distributions.

Monitor oldest message age or lag, not just queue depth. A queue with few messages yet very old items can indicate a stuck consumer or a stalled partition.

## 11. Message Ordering and Parallel Processing

Visibility timeouts and acks can affect processing order. With queues allowing parallelism, a later message may finish before an earlier one. If business logic requires ordering, choose appropriate broker ordering features, partition keys, or message groups.

For example, events updating the same account may need ordering by account ID. You can use account ID as the partition key or group key so the broker routes related messages into the same ordered stream. This typically reduces parallelism within a single partition/group while preserving order.

Even when a broker guarantees delivery order, parallel processing or retries can cause completion order to differ from receive order. Consumers should check aggregate sequence/version numbers and reject stale events if they would regress state.

With Kafka, ordering is guaranteed within a single partition. Consumer groups divide partitions among consumers; during rebalances, partition ownership can change. Consumers must handle offset commits carefully and prevent an old worker from committing stale progress after losing ownership.

## 12. Observing and Alerting on the Message Lifecycle

Observe the entire lifecycle from publish to completion, not just function invocation counts.

Metrics to monitor:

- Published message count and successfully processed message count.
- Ack rate, nack/release rate, and delivery attempt counts.
- Approximate age of oldest message or consumer lag.
- Queue depth or per-partition backlog.
- Visibility expirations, lock losses, or ack deadline extensions.
- Retry counts, max deliveries reached, and DLQ depth.
- p50/p95/p99 processing durations.
- Duplicate rate blocked by idempotency.
- Messages expired by retention or dropped.
- Database errors, throttling, timeouts, and dependency failures.
- Backlog drain duration following an outage.

Use event IDs, correlation IDs, or trace IDs to link producer, broker, consumer, and downstream service logs. Avoid logging sensitive payloads; log schema versions, event types, access-controlled tenant references, and processing outcomes instead.

Alerts should reflect meaningful symptoms:

- Oldest message age exceeds SLA threshold.
- New messages appear in the DLQ or DLQ grows rapidly.
- Ack rate drops while publish rate stays steady.
- Retries or visibility expirations spike abnormally.
- Consumer lag rises continuously.
- Messages are nearing retention expiration before being processed.
- A partition or message group stops making progress.

## 13. Acknowledgment and Retention Design Checklist

Before promoting a consumer to production, verify:

1. Is the broker a queue, subscription, or event stream? What are the exact ack/offset semantics?
2. Does ack happen only after business results are durably persisted?
3. If the business commit succeeds but ack fails, can the consumer tolerate duplicates?
4. Are visibility timeout, lock duration, or ack deadline sufficient for p95/p99 processing?
5. Does the consumer extend message hold times when needed, with a cap on total duration?
6. Are function timeouts and dependency timeouts coordinated properly?
7. Can retention survive expected outages, backlogs, and drain times?
8. Do the DLQ and retry policy distinguish transient errors from permanent errors?
9. Are deduplication records retained longer than the required retry/replay window?
10. Does batch acknowledgment support partial failures?
11. Is event ordering required by entity or partition key?
12. Are metrics and alerts in place for oldest message age, lag, retries, acks, and DLQ?
13. Does the redrive procedure verify root causes and throttle replay rates?
14. Do payloads, secrets, retention, and access controls meet data protection requirements?

## Conclusion

Acknowledgment tells the broker a consumer has finished processing per contract; visibility timeout or lock deadline determines when unconfirmed messages can be redelivered; retention determines how long the broker retains messages or records. Together with retry policies, DLQs, and function timeouts, these three parameters govern data flow resilience.

In serverless Java, persist business results durably before acking, design idempotency to tolerate duplicate deliveries, extend visibility when work needs extra time, and set retention large enough to cover expected outages and backlogs. By understanding broker semantics accurately and monitoring oldest message age, delivery counts, lag, retries, and DLQs, teams can operate reliable consumers while keeping concurrency, latency, and costs under control.
