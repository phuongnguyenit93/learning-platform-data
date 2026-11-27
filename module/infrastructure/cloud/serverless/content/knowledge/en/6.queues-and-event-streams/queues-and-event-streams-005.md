# Batch Processing and Partial Batch Failure Reporting

In serverless systems, a queue or event stream often groups multiple messages into a batch and passes them to a Java function in a single invocation. This reduces invocation counts and can increase throughput, while raising an important question: if only one message in the batch fails, must the system resend the entire batch, or can it resend only the failed message?

**Partial batch failure** allows a function to report the exact items that failed to process successfully, when supported by the trigger and platform. When designed properly, completed items can be acknowledged while failed items are retried according to the source's policy. This lesson explains how batching, acknowledgment, retries, and partial failures work, and demonstrates how to implement safe Java handlers.

## Learning Objectives

After this lesson, you will be able to:

- Explain why queues and event streams group multiple records into batches.
- Distinguish whole-batch acknowledgment from per-item acknowledgment.
- Describe how partial batch responses affect retries and data replay.
- Write a Java handler that collects IDs of failed messages.
- Design idempotency, DLQs, and logging for batch processing.
- Recognize differences between queue messages and stream records when identifying items to retry.

## 1. What Is Batch Processing?

**Batch processing** is handling multiple messages or records within a single unit of work. The platform may wait until enough items arrive or wait until a batching window expires before invoking the function.

For example, instead of invoking a function 100 times for 100 messages, a queue trigger can place 10 messages into each batch and invoke the function 10 times. The handler receives a list of messages, processes each item, and returns results to the platform.

~~~mermaid
flowchart LR
    A["Producer"] --> B["Queue / Event Stream"]
    B --> C["Batch assembly"]
    C --> D["Java Function"]
    D --> E["Process each item"]
    E --> F["Result / Acknowledgment"]
    F --> B
~~~

Batching can help:

- Reduce invocation counts and function initialization overhead.
- Increase throughput when one invocation handles multiple items.
- Reuse shared connections or resources within a single execution.
- Reduce network and serialization overhead when there are many small messages.

However, large batches also increase the amount of data a single invocation holds in memory, total processing duration, and the blast radius if the function times out. If the platform only supports whole-batch acknowledgment, one failing item can cause already-succeeded items to be redelivered.

### Batch Size and Batch Window

Two common settings:

- **Batch size:** maximum number of items in a single batch.
- **Batch window:** maximum duration the platform waits to gather more items before sending the batch.

A large batch size can improve efficiency under high load, while increasing latency under low load and extending per-invocation duration. A long batch window helps fill batches in low-traffic systems, though callers wait longer before the function starts.

| Choice | Benefit | Trade-off |
|---|---|---|
| Small batch | Low latency, small failure scope, easier timeout handling | More invocations and overhead |
| Large batch | Higher throughput, fewer invocations | Higher memory use, longer processing time, costlier retries |
| Short batch window | Processing starts sooner | May frequently receive small batches |
| Long batch window | Opportunity to gather more items | Longer pre-processing wait time |

Choose batch size and window based on load distribution, function time limits, memory, payload sizes, and latency requirements. Do not simply maximize batch size while ignoring p95/p99 processing times or retry behavior.

## 2. Acknowledgment and Retries in Batch Processing

After the function receives a batch, the platform needs to know which items finished so it stops redelivering them, and which items need retrying.

**Acknowledgment (ack)** signals that a message or record has been processed according to the source's mechanism. **Negative acknowledgment (nack)** or a failure result signals that an item must be redelivered or routed to an error flow. Exact names and behaviors differ across queues, brokers, and stream services.

There are two general result modes:

### Whole-Batch Acknowledgment

If the function returns success, the platform treats the entire batch as succeeded. If the function throws an error or times out, the entire batch may be redelivered.

Example batch with A, B, C, D:

- A, B, and D persisted results successfully.
- C encountered a transient error.
- The function throws an exception.
- The platform redelivers A, B, C, and D.

A, B, and D may be reprocessed. Without idempotency, sending emails, charging payments, or creating records could happen multiple times.

### Partial Acknowledgment (Partial Batch Response)

The function returns a list of IDs for failed items. The platform acknowledges the remaining items and retries the reported failures, per the trigger's semantics.

~~~mermaid
flowchart TD
    A["Batch: A, B, C, D"] --> B["Function processes each item"]
    B --> C["A, B, D succeed"]
    B --> D["C fails"]
    C --> E["Ack A, B, D"]
    D --> F["Retry C"]
~~~

In the same example, A, B, and D do not have to be reprocessed simply because C failed. That is the core benefit of partial batch failure.

However, partial response does not guarantee exactly-once processing. A function can execute a side effect and time out before returning a response; the platform does not know the item finished and may redeliver it. Consumers still need idempotency and safe result persistence.

## 3. Partial Batch Failure Behaves Differently by Data Source

Not all triggers share the same acknowledgment contract. Before writing a handler, read the event source's semantics.

| Source | Failed Item Identifier | Typical Retry Behavior |
|---|---|---|
| Message queue such as Amazon SQS | Message ID | Can retry individual messages listed in partial response when event source mapping is configured to support it |
| Ordered queue / FIFO | Message ID with ordering rules within message group | Must stop or hold messages after the failure point to avoid breaking order |
| Sharded/partitioned stream such as Kinesis or DynamoDB Streams | Sequence number or checkpoint identifier | Checkpointing may replay records from the failed position onward, not necessarily just one record |
| Pub/Sub or other brokers | Message ID, ack token, or delivery handle | Ack/nack and batch response mechanics depend on connector and runtime |

### Queue Messages

With a queue like Amazon SQS integrated with AWS Lambda, a single invocation can receive multiple SQS messages. If the `ReportBatchItemFailures` response type is enabled on the event source mapping, the handler returns the failed message IDs. Lambda can delete succeeded messages and retry only the failed ones.

If this setting is not enabled, returning a partial failure structure may be ignored by the platform. When the function throws an exception or times out, the entire batch may be retried per the queue integration's rules.

### FIFO Queues and Ordering

FIFO queues maintain ordering within a message group. If one message in a batch fails, continuing to process subsequent messages in the same ordered stream could advance business state past an incomplete step.

A safe policy is typically to stop processing after the first failed message and report failure for that message plus all remaining unprocessed messages in the batch. The platform will redeliver them per FIFO rules. This can lower throughput, while preserving required ordering.

### Event Streams and Checkpoints

With sharded or partitioned streams, record positions are represented by sequence numbers or offsets. When a record mid-batch fails, the platform may need to replay from the lowest incomplete checkpoint. Consequently, records after the failed one may be reprocessed even if they ran previously.

This is a critical distinction: **partial batch failure in a message queue does not imply independent single-record retry in every stream**. Handlers must return the exact identifier required by the stream integration, and processing logic must tolerate replay.

## 4. Java Handler for SQS: Reporting Failed Message IDs

The example below uses the AWS Lambda Java events library and illustrates a standard queue. The handler processes each message independently, records the ID on failure, and returns `SQSBatchResponse`.

This example targets Java 8 or later; event classes come from the `aws-lambda-java-events` library.

~~~java
import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestHandler;
import com.amazonaws.services.lambda.runtime.events.SQSEvent;
import com.amazonaws.services.lambda.runtime.events.SQSBatchResponse;

import java.util.ArrayList;
import java.util.List;

public class OrderBatchHandler
        implements RequestHandler<SQSEvent, SQSBatchResponse> {

    @Override
    public SQSBatchResponse handleRequest(
            SQSEvent event, Context context) {

        List<SQSBatchResponse.BatchItemFailure> failures =
                new ArrayList<>();

        for (SQSEvent.SQSMessage message : event.getRecords()) {
            try {
                processMessage(message);
            } catch (Exception ex) {
                context.getLogger().log(
                        "Failed messageId=" + message.getMessageId()
                                + ", reason=" + ex.getMessage());

                failures.add(
                        new SQSBatchResponse.BatchItemFailure(
                                message.getMessageId()));
            }
        }

        return new SQSBatchResponse(failures);
    }

    private void processMessage(SQSEvent.SQSMessage message) {
        // Parse payload, validate and perform an idempotent business operation.
        // Throw an exception when this message has not been processed safely.
    }
}
~~~

When no items fail, the `failures` list is empty. When one or more items fail, the response contains the exact message IDs of the items needing retry.

For the platform to use this response, the Lambda event source mapping must enable `ReportBatchItemFailures`. Condensed AWS SAM configuration example:

~~~yaml
Events:
  OrdersQueue:
    Type: SQS
    Properties:
      Queue: !GetAtt OrdersQueue.Arn
      BatchSize: 10
      FunctionResponseTypes:
        - ReportBatchItemFailures
~~~

Property names and configuration options depend on the deployment tool, but the principle remains: partial response mode must be enabled on the event source integration. Updating only the Java handler is not enough.

### Do Not Swallow Errors and Return Success

If you catch an exception without adding the message ID to the `failures` list, the function reports that message as succeeded. The platform may delete or acknowledge the message, dropping data from the retry flow.

Conversely, adding the ID of an already-succeeded message causes unnecessary redelivery. Only add an ID when the handler has not safely completed the item's side effects.

## 5. Handling FIFO: Stopping at the First Failure

With FIFO queues, if ordering within a message group matters to business logic, the handler must avoid processing messages after a failed item. The simple pattern below illustrates this rule; in real systems, consider message groups and exact source semantics.

~~~java
List<SQSBatchResponse.BatchItemFailure> failures =
        new ArrayList<>();

boolean stopAfterFailure = false;

for (SQSEvent.SQSMessage message : event.getRecords()) {
    if (stopAfterFailure) {
        failures.add(new SQSBatchResponse.BatchItemFailure(
                message.getMessageId()));
        continue;
    }

    try {
        processMessage(message);
    } catch (Exception ex) {
        failures.add(new SQSBatchResponse.BatchItemFailure(
                message.getMessageId()));
        stopAfterFailure = true;
    }
}

return new SQSBatchResponse(failures);
~~~

This code preserves whole-batch ordering by skipping messages after the failure point. It may hold back messages from other groups in the same batch if the source mixes multiple groups; this is a conservative choice to weigh against throughput and how the platform distributes groups. For systems requiring per-group optimization, implement according to exact broker semantics.

## 6. Rules for Determining Item Success

An item should only be considered succeeded once the application has completed all required work and can tolerate the platform never resending that item.

Example of a function handling `OrderPlaced`:

1. Read and validate the event schema.
2. Check whether the `eventId` or business key has already been processed.
3. Execute the business operation.
4. Persist the result and idempotency marker safely.
5. Only then treat the item as succeeded in the batch response.

If the function calls a payment service successfully but fails to save state, a retry may call the payment service again. Using a stable idempotency key with the payment service and persisting transaction state reduces this risk.

Do not mark an item succeeded merely because the function started processing or wrote a log entry. Success must be defined by committed business results.

### Avoid One Large Transaction for the Whole Batch Unless Required

If each item is an independent business transaction, process and commit each item separately. Wrapping an entire batch in one transaction can negate the benefits of partial failure: one failure rolls back all items, or the transaction holds locks for too long.

If business rules require the entire batch to succeed atomically together, that is an explicit atomic-batch design decision. In that case, partial acknowledgment cannot on its own turn operations into an atomic distributed transaction.

## 7. Retries, Visibility Timeout, and Dead-Letter Queues

Partial responses only identify which items failed; retry policies are still governed by the data source and integration settings.

For queues, understand:

- **Visibility timeout / message lock:** duration during which an in-flight message is temporarily withheld from other consumers.
- **Retry policy:** when a message is redelivered, whether backoff applies, and maximum attempt count.
- **Receive count / delivery attempt:** number of times a message has been delivered.
- **Dead-letter queue (DLQ):** destination for messages exceeding retry thresholds or classified unprocessable by policy.
- **Redrive:** process for moving messages from the DLQ back to the queue for reprocessing after fixing root causes.

Visibility timeout or lock duration must cover expected processing time, including the batch and downstream service calls. If the lock expires before the handler finishes, messages can be delivered concurrently to another consumer. Monitor message age, delivery counts, and queue depth.

### Poison Messages

A **poison message** is a message that fails repeatedly due to bad data, unsupported schemas, missing required fields, or an unrecoverable error.

If retried indefinitely, a poison message consumes processing capacity, inflates costs, and delays healthy messages. Classify failures:

- Transient errors such as timeouts or throttling: retry with backoff.
- Permanent data errors such as invalid schemas: record, quarantine, or route to a DLQ per policy.
- Application bug errors: cap retries, alert, and fix the handler before redriving.

A DLQ is not a place to forget data. Assign ownership for review, dashboards, retention limits, payload remediation procedures, and controlled replay.

## 8. Idempotency and Side Effects in Batches

Queues and event streams commonly provide at-least-once delivery semantics in many configurations. Thus, the same item can be processed more than once, even when partial responses are enabled.

Common safeguards:

- Use a stable `eventId` as the deduplication key.
- Enforce unique constraints or conditional writes in the database.
- Write business outcomes and processed markers in the same transaction when possible.
- Pass idempotency keys to external services if their APIs support them.
- Use a transactional outbox when emitting events after committing data.
- Keep side effects separate from message parsing and validation.

An idempotency table might include:

| Field | Purpose |
|---|---|
| `event_id` | Stable event identifier |
| `status` | `RECEIVED`, `PROCESSING`, `SUCCEEDED`, or `FAILED` |
| `result_reference` | Reference ID for the business outcome |
| `first_seen_at` | Timestamp when the consumer first received it |
| `completed_at` | Timestamp when processing finished |
| `attempt_count` | Recorded attempt count |

Using a `PROCESSING` status requires a lease or recovery mechanism in case the function dies mid-way. Marking an event as processed before side effects finish can cause subsequent retries to skip the item even though business logic failed.

## 9. Batch Size, Timeout, and Concurrency

Batch size, processing duration, and concurrency are directly coupled:

- Large batches reduce invocations, but a single batch can take longer.
- Function timeouts can cause the whole batch or unacknowledged portion to be redelivered.
- High concurrency speeds up consumption, but can overload downstream databases or APIs.
- A batch containing multiple heavy items can skew execution times across invocations.
- Partial failure avoids re-running succeeded items, but does not eliminate retry and verification costs.

Measure at minimum:

- Actual batch sizes and full-batch ratio.
- Per-item and full-batch processing duration.
- Batch error rate and failed items per batch.
- Delivery/retry counts and DLQ message counts.
- Queue depth, oldest message age, and wait time.
- Throttling, concurrency, and downstream dependency errors.
- Cost per successfully processed item.

You can start with small batches, measure load, and scale up gradually. When increasing batch size, test with large payloads, slow items, interleaved failures, and timeouts to find safe limits.

## 10. Testing Partial Batch Failure

A thorough test suite verifies both the returned failure list and actual side effects.

| Scenario | Expected Result |
|---|---|
| All items succeed | Response contains an empty failure list |
| One item hits a transient error | Only that item's ID is returned in the partial response |
| Multiple items fail | All IDs that did not safely complete are returned |
| Failure after side effect but before state commit | Retry produces no duplicate side effects thanks to idempotency |
| Function timeout | Redelivery behavior matches source semantics; committed items tolerate replay |
| Poison message | Retry cap and DLQ/quarantine path work as expected |
| FIFO failure | Does not process past the failure point per ordering rules |
| Stream record failure | Returns proper sequence number/checkpoint and verifies subsequent records tolerate replay |
| Partial response disabled | Configuration test confirms platform may fall back to whole-batch retry |

Unit tests can mock business services to verify which message IDs appear in the response. Integration tests should run against the actual event source mapping or corresponding broker/test environment to verify acks, retries, lock timeouts, ordering, and DLQs.

## 11. Pre-Deployment Batch Handler Checklist

- [ ] Identified whether the event source is a standard queue, FIFO queue, or ordered stream.
- [ ] Reviewed trigger acknowledgment, retry, ordering, and checkpoint semantics.
- [ ] Enabled partial batch response configuration if required by the platform.
- [ ] Handler only reports failure for items that did not complete safely.
- [ ] Message IDs or sequence numbers are returned in the exact format required by the platform.
- [ ] FIFO handler stops or holds items after the failure point per ordering rules.
- [ ] Side effects are idempotent to tolerate redelivery and replay.
- [ ] Batch size, batch window, timeouts, and concurrency have been measured and tested.
- [ ] Visibility timeout or message lock covers processing duration.
- [ ] Retry limits, DLQ, alerts, and redrive procedures are configured.
- [ ] Logs include event ID, message ID, attempt count, and outcome without exposing sensitive data.
- [ ] Tested single-item failure, multi-item failure, timeouts, duplicates, poison messages, and stream checkpoints.

## Self-Check

1. If a batch has 10 messages and only the 4th fails, what can whole-batch acknowledgment cause?
2. Besides the Java code, where must partial batch response be enabled?
3. Why does partial batch failure not guarantee exactly-once processing?
4. With a FIFO queue, why should processing stop for messages after a failed message?
5. Why might a stream with sequence numbers retry from the failed checkpoint onward instead of retrying only a single record?
6. How does a large batch size affect latency, timeouts, and retry blast radius?
7. When should a message be routed to a DLQ instead of continuing retries?

Batch processing lets functions handle multiple messages efficiently in a single invocation. Partial batch failure narrows retries to incomplete items under the trigger's contract. To make this mechanism safe, development teams must return accurate failure identifiers, enable the proper integration settings, preserve ordering when needed, design idempotency, and monitor retries alongside DLQs. Once these rules are validated against the real event source, batching boosts throughput while preserving business correctness.
