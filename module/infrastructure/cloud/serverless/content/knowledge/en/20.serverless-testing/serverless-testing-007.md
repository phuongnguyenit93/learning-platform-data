# Testing Partial Batch Failures, Retries, and Duplicate Messages

Serverless event sources typically group multiple records into a batch to reduce function invocations and increase throughput. A batch may hold many independent messages, yet a single failing message can cause the entire batch to be redelivered if the function only signals success or failure at the invocation level. When that happens, already-succeeded messages can be re-executed, creating duplicate side effects or increasing cost.

Partial batch failure lets a function report precisely which records did not succeed. The runtime can acknowledge the remaining records and redeliver only the failed ones according to the event source's semantics. This reduces duplicate work, but it does not turn the system into exactly-once delivery. Messages can still be delivered multiple times due to timeouts, crashes, network failures, visibility timeouts, or producer retries. Therefore, consumers must be idempotent, and tests must cover both batch responses and business outcomes.

Within the **CLOUD_SERVERLESS** module, learners build Java functions triggered by HTTP, messages, or events while handling retries, idempotency, state, scaling, and cost. This lesson focuses on batch processing, partial batch failures, retries, and duplicate messages, featuring AWS Lambda/SQS examples alongside comparisons with Kinesis/DynamoDB Streams.

## 1. Batch processing and partial batch failures

A batch is a group of records sent to a function in a single invocation by the event source mapping or runtime. For example, one invocation receives 10 messages from a queue. The function processes each message and returns a result to the runtime.

There are two common ways to report results:

- **Batch-level success/failure:** the invocation succeeds or fails as a single unit. If it fails, the whole batch may be redelivered.
- **Partial batch response:** the function returns a list of failed records. The event source retries only the specified records per the service's semantics.

Example 5-message batch:

~~~text
Batch:  [M1] [M2] [M3] [M4] [M5]
Result:  OK   OK   FAIL OK   FAIL

Batch-level failure:
         Retry M1 M2 M3 M4 M5

Partial batch response:
         Acknowledge M1 M2 M4
         Retry M3 M5
~~~

Partial batch responses help when records are independent and one failure should not force other records to re-run. However, if records depend on ordering or share a single transaction, per-record handling must be designed carefully.

The response contract depends on the platform and event source. The `ReportBatchItemFailures` structure in the AWS example is not a universal format for Azure Functions, Google Cloud Functions, or every other trigger; use the exact contract of the connector/runtime you deploy.

### Partial failure is not a standalone retry mechanism

The function is still invoked in batches. Partial responses only indicate which records remain incomplete for the event source to handle next. They do not by themselves establish retry policies, backoff, DLQs, idempotency, or transactions. Those mechanisms still require separate configuration and implementation.

## 2. Why are messages delivered multiple times?

Queue and stream systems prioritize not losing events. In exchange, a record may be redelivered in several situations:

- The function updates the database but crashes before acknowledging success.
- The function times out while some records in the batch have already completed.
- The event source fails to receive the response due to a network error.
- A message's visibility timeout expires before the previous attempt finishes.
- The producer resends the same business event.
- The consumer is throttled or the runtime restarts.
- A stream checkpoint has not yet advanced past already-processed records.
- A batch contains a failing record that forces earlier records to re-run per source semantics.

This is why you must design for **at-least-once delivery** when a service advertises those semantics. Never assume a message is invoked strictly once.

### Distinguishing three types of duplicates

| Duplicate type | Example | How to detect |
|---|---|---|
| Redelivery of the same message | Same queue message delivered again | Transport message ID, receive/dequeue count |
| Producer emits duplicate business event | Two messages with different IDs but the same OrderCreated event | Stable event ID or business idempotency key |
| Repeated side effect | Double charge or duplicate email for the same order | Idempotency ledger, unique constraint, provider idempotency key |

Transport message IDs help observe redeliveries. However, if a producer emits the same business event as two distinct queue messages, each message may have its own transport ID. Consumers need a stable event ID or business key to recognize the same business operation.

## 3. AWS Lambda with SQS: enabling partial batch responses

With AWS Lambda and Amazon SQS, by default, if a function returns an error or throws an exception, the whole batch is considered failed and messages may be redelivered. To report failed records individually, enable the response type:

~~~hcl
resource "aws_lambda_event_source_mapping" "orders" {
  event_source_arn = aws_sqs_queue.orders.arn
  function_name    = aws_lambda_function.orders.arn
  batch_size       = 10

  function_response_types = [
    "ReportBatchItemFailures"
  ]
}
~~~

This is an illustrative Terraform configuration. With CloudFormation/SAM or the CLI, enable the same `ReportBatchItemFailures` option on the event source mapping. Writing code that returns a failure list without enabling the matching response type will not produce the intended partial acknowledgement behavior.

Once enabled, the function returns a structure containing `BatchItemFailures`. Each entry identifies a message ID to retry. Messages omitted from the list are treated as successfully processed.

### Java handler for SQS

Example using the AWS Lambda Java Events library with a handler receiving the full batch:

~~~java
import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestHandler;
import com.amazonaws.services.lambda.runtime.events.SQSEvent;
import com.amazonaws.services.lambda.runtime.events.SQSBatchResponse;

import java.util.ArrayList;
import java.util.List;

public final class OrderBatchHandler
        implements RequestHandler<SQSEvent, SQSBatchResponse> {

    @Override
    public SQSBatchResponse handleRequest(
            SQSEvent event,
            Context context) {

        List<SQSBatchResponse.BatchItemFailure> failures =
                new ArrayList<>();

        for (SQSEvent.SQSMessage message : event.getRecords()) {
            try {
                processIdempotently(message);
            } catch (RetryableMessageException ex) {
                context.getLogger().warning(
                    "retryable message failure; messageId="
                    + safeId(message.getMessageId())
                );

                failures.add(
                    SQSBatchResponse.BatchItemFailure.builder()
                        .withItemIdentifier(message.getMessageId())
                        .build()
                );
            } catch (Exception ex) {
                context.getLogger().severe(
                    "unexpected message failure; messageId="
                    + safeId(message.getMessageId())
                );

                failures.add(
                    SQSBatchResponse.BatchItemFailure.builder()
                        .withItemIdentifier(message.getMessageId())
                        .build()
                );
            }
        }

        return SQSBatchResponse.builder()
                .withBatchItemFailures(failures)
                .build();
    }

    private void processIdempotently(SQSEvent.SQSMessage message) {
        // Validate, claim idempotency key, execute business operation.
    }

    private String safeId(String value) {
        if (value == null || !value.matches("[A-Za-z0-9_-]{1,128}")) {
            return "unavailable";
        }
        return value;
    }
}
~~~

Class names and builders must match the AWS Lambda Java Events dependency version in your project. The example illustrates batch orchestration; `processIdempotently` must implement actual business logic, transactions, and idempotency.

Key points:

- Use the message ID supplied by SQS as the item identifier in the response.
- Add a message to the failure list only when it has not finished processing and you want the event source to redeliver it.
- Never add a message whose business changes already committed to the failure list.
- If the handler throws an uncaught exception, an invocation-level failure may force the entire batch to retry.
- Never return an empty success response when a record was not processed, as that record may be deleted from the queue.
- Never log raw message bodies or unsanitized exception messages.

### Classifying errors before returning partial responses

The example above routes unhandled errors to retry. In production, distinguish:

- Transient errors: timeouts, throttling, network resets, dependency 503s. Usually retryable.
- Permanent data errors: invalid schema, missing required fields, unsupported event types. Quarantine or let DLQ capture after a bounded number of attempts.
- Configuration errors: missing permissions, wrong endpoints, expired secrets. Continuous retries usually cannot fix the cause; alert and fix configuration.
- Business errors: canceled orders or disallowed state transitions. May be valid outcomes to record, not necessarily retries.

If you decide to skip a permanently broken message, durably store audit-ready quarantine information before acknowledging the original message. If relying on SQS redrive policies, keep reporting the message as failed until it exceeds `maxReceiveCount` and moves to the DLQ.

## 4. SQS standard and FIFO have different semantics

### Standard queue

SQS Standard prioritizes throughput and scalability. Messages may be delivered at least once, and strict ordering is not guaranteed. Partial batch responses prevent one failing record from forcing independent records to re-run.

If a batch has M1 through M5 and M3 fails, the function can return M3 in the failure list. M1, M2, M4, and M5 are acknowledged; M3 is redelivered per queue policy.

### FIFO queue

SQS FIFO guarantees ordering within the same message group, so partial failure handling must preserve business ordering. When a record in a batch fails, do not keep processing later records in the same group as if the failing record succeeded.

The safest strategy is to stop processing the batch at the first failing record and include both that record and all remaining unprocessed records in the failure list. If you want to continue processing other message groups in the same batch, you must prove they are independent and preserve ordering within each group; never process messages behind a failed record in the same group.

~~~text
FIFO message group G1:
  M1 -> M2 -> M3(fail) -> M4 -> M5

Processing:
  M1, M2: success
  M3: failure
  M4, M5: unprocessed, must retry along with M3

Do not process M4/M5 past M3 if doing so breaks ordering.
~~~

With FIFO, continuing past an error can apply a later operation before an earlier one. Inspect message group IDs and in-batch ordering carefully; never apply standard-queue logic mechanically.

## 5. Kinesis and DynamoDB Streams: checkpoints instead of queue acknowledgements

Kinesis Data Streams and DynamoDB Streams are read by Lambda via an event source mapping. Each record has a sequence number, and stream shards are ordered. When partial batch responses are enabled, the function returns item identifiers corresponding to the sequence numbers of failed records.

Event source mapping configuration requires the `ReportBatchItemFailures` response type. General Terraform example:

~~~hcl
resource "aws_lambda_event_source_mapping" "orders_stream" {
  event_source_arn  = aws_kinesis_stream.orders.arn
  function_name     = aws_lambda_function.stream_consumer.arn
  starting_position = "LATEST"
  batch_size        = 100

  function_response_types = [
    "ReportBatchItemFailures"
  ]

  maximum_retry_attempts        = 5
  maximum_record_age_in_seconds = 3600
  bisect_batch_on_function_error = true
}
~~~

Retry and bisect attributes are supported depending on the event source mapping/stream type and provider version. Verify the Terraform schema and limits for your exact source type before applying. For DynamoDB Streams, ARNs and configurations may differ; do not copy Kinesis settings verbatim if the provider expects distinct attributes.

### Java response for streams

With AWS Lambda Java Events, Kinesis/DynamoDB partial responses use a similar structure where the item identifier is the sequence number:

~~~java
import com.amazonaws.services.lambda.runtime.events.KinesisEvent;
import com.amazonaws.services.lambda.runtime.events.StreamsEventResponse;

import java.util.ArrayList;
import java.util.List;

public StreamsEventResponse handle(KinesisEvent event) {
    List<StreamsEventResponse.BatchItemFailure> failures =
            new ArrayList<>();

    for (KinesisEvent.KinesisEventRecord record : event.getRecords()) {
        String sequenceNumber =
                record.getKinesis().getSequenceNumber();

        try {
            processStreamRecord(record);
        } catch (Exception ex) {
            failures.add(
                new StreamsEventResponse.BatchItemFailure(sequenceNumber)
            );
        }
    }

    return new StreamsEventResponse(failures);
}
~~~

This illustrates the response type; verify constructors/classes against your `aws-lambda-java-events` version. For DynamoDB Streams, the event record type and sequence-number extraction differ from `KinesisEvent`.

With streams, Lambda uses the lowest reported failed sequence number as the checkpoint for the retry. Records after that checkpoint may be re-read even if they succeeded in the previous attempt. Therefore, partial responses shrink the retry scope compared to the full batch, yet do not eliminate the need for idempotency on records following a failure point.

### Bisect batch

`BisectBatchOnFunctionError` lets Lambda split a failing batch into smaller halves to isolate a bad record. It helps when you do not yet know which record in a batch is crashing the handler. Combining it with partial batch responses can improve handling, but understand how checkpoints, retry attempts, and record age interact so you do not prolong poison-record processing.

## 6. Retry policies and dead-letter handling

Retries must be bounded and matched to the event source type. No single retry configuration fits all queues and streams.

| Component | Role | What to check |
|---|---|---|
| Visibility timeout (SQS) | Duration a message stays hidden after receipt | Long enough for function timeout, batch window, and retry behavior |
| maxReceiveCount | Number of receives before redrive | Finite limit so poison messages do not loop forever |
| Dead-letter queue | Stores unprocessable messages | Read permissions, retention, alerts, and redrive |
| MaximumRetryAttempts (stream) | Retry cap for records/batches per event source mapping | Tuned for zero data loss and acceptable backlog |
| MaximumRecordAgeInSeconds | Max age of retried records | Avoids holding stale records indefinitely |
| On-failure destination | Target storing metadata when stream events fail per config | Enables investigation and recovery |
| BisectBatchOnFunctionError | Splits batches on function errors | Weigh invocation cost and retry latency |

With an SQS Lambda event source mapping, the queue visibility timeout must be set sufficiently longer than the function timeout. AWS recommends at least six times the function timeout; if a batching window is used, account for that time as well. If the timeout is too short, messages can reappear while the previous invocation is still running, causing concurrency spikes and duplicates.

SQS redrive policies use `maxReceiveCount` to move messages to a DLQ after repeated failed receives. DLQs need alarms on message count and message age. Never create a DLQ and forget to monitor it.

### Backoff and retry storms

When a dependency suffers an outage, many functions may retry simultaneously and trigger a retry storm. Use exponential backoff, jitter, and bounded retry counts at the application layer when appropriate. For event-source-managed retries, understand the provider's visibility, polling, and scaling mechanics so you do not stack an unbounded retry loop inside the handler.

Never retry permanent errors such as bad schemas or permission denials forever. Classify errors and route poison messages to quarantine/DLQ for investigation.

## 7. Idempotency: a mandatory safeguard for consumers

Idempotency means processing the same business operation multiple times while producing only one accepted business effect. It is the core defense when duplicate deliveries occur.

### Choosing an idempotency key

Prefer a stable key generated by the producer, such as an event ID or operation ID. If none exists, construct one from business keys and the operation type, ensuring two distinct valid events cannot accidentally collide.

Example:

~~~text
idempotency_key = tenant_id + ":" + event_type + ":" + event_id
~~~

Do not hash arbitrary payloads if field ordering, timestamps, or metadata can vary. Nor should you rely solely on the SQS message ID when a producer can re-emit the same event as a new message with a different transport ID.

### Inbox/idempotency table

A table recording processed events may contain:

| Field | Purpose |
|---|---|
| idempotency_key | Unique key of the business operation |
| status | PROCESSING, COMPLETED, or FAILED |
| result_ref | Reference to the created outcome |
| first_seen_at | Timestamp of first receipt |
| completed_at | Timestamp of completion |
| attempt_count | Number of attempts observed by the app |
| expires_at | Expiration timestamp for the deduplication record |

Create a unique constraint on `idempotency_key`. When a message is redelivered, the consumer checks the key:

- Already COMPLETED: return success without repeating side effects.
- Currently PROCESSING: follow a lease/lock policy; prevent two invocations from doing the same work concurrently.
- Not yet present: claim the key and execute business logic.
- FAILED: determine whether the error is retryable or requires intervention.

Idempotency record retention must exceed the window during which messages can be redriven or replayed. Deleting keys too early allows replayed older messages to repeat side effects.

### Transactions for database side effects

If business updates and idempotency records live in the same database, perform them in the same transaction:

~~~java
@Transactional
public void handle(OrderCreated event) {
    boolean firstDelivery =
            inboxRepository.insertIfAbsent(event.eventId());

    if (!firstDelivery) {
        // Acknowledge only if an invariant guarantees an existing row means COMPLETED.
        // If rows can be PROCESSING/FAILED, read status and decide whether to retry.
        return;
    }

    orderRepository.markCreated(event.orderId());
    inboxRepository.markCompleted(event.eventId());
}
~~~

This is pseudocode: `insertIfAbsent` must rely on a unique constraint and proper transaction isolation. In a single-transaction model, commit the inbox row alongside the business update and COMPLETED status; on rollback, both the inbox insert and business update roll back together. If events are claimed in a separate transaction with status PROCESSING, duplicates must not be acknowledged automatically: inspect status, leases/timeouts, and recovery for abandoned claims.

Never check with a SELECT followed by an INSERT. Two concurrent invocations can both observe the key as absent and both execute the business operation. Use a unique constraint, atomic insert, or conditional write.

## 8. External side effects and the transactional outbox

A database transaction cannot automatically span payment provider APIs, email services, or external systems. If calling a provider succeeds and the function crashes before marking COMPLETED, a retry may call the provider again.

Options:

- Pass a stable idempotency key to the provider if the API supports it.
- Use a transactional outbox to commit business state and outbound events in the same database transaction.
- Have a dispatcher read the outbox and send events; the dispatcher must also be idempotent.
- Store the provider operation reference for reconciliation when responses are lost.
- Use workflows/durable orchestration when multi-step processes require durable state.

Outbox flow:

~~~mermaid
sequenceDiagram
    participant C as Queue consumer
    participant DB as Database
    participant O as Outbox dispatcher
    participant P as External provider

    C->>DB: Transaction: inbox + business update + outbox
    DB-->>C: Commit
    C-->>C: Acknowledge message
    O->>DB: Read pending outbox event
    O->>P: Call with stable idempotency key
    P-->>O: Result / provider reference
    O->>DB: Mark outbox delivered
~~~

If the dispatcher crashes after the provider processed the request but before marking it delivered, it will resend. Provider-side idempotency keys or reconciliation via provider references prevent repeated side effects.

## 9. Handling batches with interdependent records

Partial batch responses fit best when each record can be processed independently. If record B depends on the outcome of record A, parallel execution or acknowledging A while B fails can violate business ordering.

Determine:

- Do records belong to the same aggregate/order/customer?
- Is ordering required by message group or partition key?
- Can each record commit independently?
- Does a single transaction span the whole batch?
- If one record fails, are subsequent records allowed to run?
- On retry, can earlier succeeded records be re-executed?

If the whole batch is one logical transaction, process everything in one transaction and acknowledge the full batch only upon commit. If records are independent, process and commit each record individually so partial responses are meaningful.

For SQS FIFO, preserve ordering by message group. For streams, respect shard/partition ordering and checkpoints. Never crank up concurrency solely to maximize throughput if it breaks ordering or aggregate consistency.

## 10. Timeouts, batch size, and concurrency

Larger batch sizes reduce invocations but increase batch processing duration, memory usage, and error blast radius. Smaller batch sizes add overhead while limiting how many records are affected per invocation.

| Parameter | Increasing it can bring | Risks to check |
|---|---|---|
| Batch size | Fewer invocations, higher throughput | Memory, duration, partial failure complexity |
| Maximum batching window | More records grouped together | Higher pre-processing latency |
| Function timeout | Allows batches more time to finish | Longer message lock duration and cost |
| Event source concurrency | More parallel batches | Downstream overload, ordering, and duplicates |
| Visibility timeout | Reduces premature message reappearance | Longer wait before retrying after a function crash |
| Max receive count | More chances to succeed | Poison messages linger longer |

Choose batch sizes from benchmarks and downstream limits. A batch of 10 records where each record calls the database multiple times can create higher load than expected. Measure p95/p99 duration, memory, connection counts, error rates, and backlog.

## 11. Observing partial failures and duplicates

An invocation may be counted as successful at the Lambda level because the handler returned a valid partial response, even when several records were marked failed. Relying solely on Lambda `Errors` metrics can miss record-level failures.

Emit structured metrics and logs for each outcome:

- Batch records received.
- Records succeeded.
- Records failed retryable.
- Records quarantined/permanent.
- Duplicates detected.
- Idempotency conflicts or operations already completed.
- Retry attempt counts.
- DLQ ingress and backlog.
- Age of oldest message/record.
- Processing duration by event type.

For SQS, monitor `ApproximateAgeOfOldestMessage`, `ApproximateNumberOfMessagesVisible`, DLQ depth, Lambda `Duration`, `Throttles`, and custom record failure metrics. For Kinesis/DynamoDB Streams, monitor `IteratorAge`, retries, throughput, and shard-level lag.

Never put raw payloads, emails, or tokens into metric dimensions. Use bounded-cardinality dimensions such as event type, error code, queue name, function name, and status class.

## 12. Testing partial batch responses

Tests must verify both technical responses and business effects. A handler can return the exact failed message IDs while still committing wrong or duplicate side effects.

### Unit tests for the handler

Use simulated batches containing:

- All records succeeding.
- One transient-error record at the beginning, middle, and end of a batch.
- Multiple failing records.
- Invalid messages.
- Duplicate event IDs within the same batch.
- Records already completed in a prior invocation.
- Unexpected exceptions.

Verify the response contains only the exact message IDs/sequence numbers needing retry. Also verify the business service is invoked the exact number of times allowed by idempotency.

### Integration tests with the event source

Test in an environment with realistic semantics:

1. Create a test queue/stream and event source mapping with partial responses enabled.
2. Send a multi-message batch.
3. Intentionally fail one record.
4. Verify succeeded records are not unexpectedly redelivered.
5. Verify the failed record is redelivered.
6. Send the same business event twice with different transport IDs.
7. Verify idempotency blocks duplicate side effects.
8. Trigger function timeouts/crashes before and after commit.
9. Verify DLQ/quarantine behavior after max retry attempts.
10. Measure backlog and downstream concurrency under bursts.

Local emulators help during development loops, but do not assume they perfectly emulate a cloud provider's visibility timeouts, scaling, ordering, retries, and checkpoints. Run integration tests in a test account/stack before release.

## 13. Test matrix for batches, retries, and duplicates

| Scenario | Condition | Expected outcome |
|---|---|---|
| Successful batch | All records valid | Zero record failures; single side effect |
| One transient failure | One message times out, others succeed | Only failed message retries when partial response is configured |
| Multiple failures | Two independent records fail | Response lists both |
| Function throws uncaught exception | Invocation-level exception | Whole batch may retry; idempotency guards side effects |
| Crash after DB commit | Message unacknowledged | Redelivery does not repeat DB update |
| Duplicate in same batch | Two messages share business event ID | Only one business operation commits |
| Duplicate across batches | Same event arrives again later | Inbox/unique key recognizes event is already completed |
| Dependency throttling | Downstream returns 429/503 | Bounded retries, backoff, no retry storm |
| Poison message | Unprocessable data | Quarantined or moved to DLQ after finite policy |
| FIFO failing record | One record in message group fails | Stops later records in order; retries failed and unprocessed records |
| Stream checkpoint | Mid-batch record fails | Retries from lowest checkpoint; subsequent records may re-run |
| Visibility timeout too short | Invocation exceeds visibility | Test catches redelivery/concurrent duplicates |
| DLQ redrive | Replay previously processed message | Idempotency prevents duplicate side effects |
| Large batch | Many records and slow dependency | Memory/duration/concurrency stay within limits |

## 14. Idempotency test examples

Example test for the same event delivered twice:

~~~java
@Test
void duplicateEventDoesNotCreateSecondOrder() {
    OrderCreated event = new OrderCreated("evt-1001", "order-42");

    handler.process(event);
    handler.process(event);

    assertEquals(1, orderRepository.countByOrderId("order-42"));
    assertEquals(1, inboxRepository.countByEventId("evt-1001"));
}
~~~

This test requires a database or repository test double with appropriate unique constraint semantics. A mock counting method calls does not prove atomicity under two concurrent invocations.

Also test race conditions:

~~~java
@Test
void concurrentDuplicateDeliveryCommitsOnce() {
    // Run two consumers concurrently with the same event ID.
    // Assert unique constraint/conditional write lets only one consumer claim it.
    // Assert business side effect commits only once.
}
~~~

Concurrency tests should use a real database or suitable test container to verify transaction isolation, unique constraints, and conditional writes.

## 15. Common implementation pitfalls

| Pitfall | Consequence | Prevention |
|---|---|---|
| Forgetting to enable ReportBatchItemFailures | Runtime treats response as standard batch success/failure | Verify event source mapping alongside code |
| Returning empty response when records remain unprocessed | Messages may be acknowledged and lose retry opportunity | Acknowledge records only after durable completion/quarantine |
| Throwing exception after processing some records | Whole batch may retry | Catch errors per record and return partial response when appropriate |
| Using SQS message ID as sole business idempotency key | Producer emits duplicate event with a new message ID | Use stable event IDs/business keys |
| Missing unique constraint | Two concurrent invocations process the same event | Atomic inserts/conditional writes |
| Calling external API before recording idempotency | Retries can repeat side effects | Provider idempotency keys or outbox/reconciliation |
| FIFO continues processing past failed record | Breaks business ordering | Stop at first failure in group and report unprocessed tail |
| Ignoring stream checkpoints | Records after checkpoint re-run | Idempotent consumers and sequence-number tests |
| Visibility timeout too short | Message reappears while prior invocation is still running | Size timeout for function duration and batch window |
| No DLQ/quarantine | Poison messages retry endlessly or get dropped | Redrive policies, alerts, and runbooks |
| Retrying all errors identically | Wastes invocations and prolongs outages | Classify transient/permanent/configuration errors |
| Watching only Lambda Errors | Misses partial record failures | Emit custom per-record metrics |
| Logging raw bodies on retry | Duplicates sensitive data | Log event references and error codes |
| Oversized batches | Increases memory, timeouts, and blast radius | Benchmark and cap batch size/concurrency |

## 16. Design and operations workflow

When implementing a batch consumer:

1. **Choose the event source:** determine queue vs. stream, ordering, and delivery semantics.
2. **Define batch boundaries:** are records independent or sharing a transaction?
3. **Enable partial responses:** configure the event source mapping and provider-specific response schema.
4. **Classify errors:** transient, permanent, configuration, and business outcomes.
5. **Design idempotency:** stable event IDs, unique constraints, and transactions.
6. **Protect external side effects:** provider idempotency keys, outbox, or reconciliation.
7. **Configure retries:** visibility timeouts, max receive/retry attempts, DLQs, and record age.
8. **Bound load:** batch size, batching window, concurrency, and downstream capacity.
9. **Test:** partial failures, duplicates, crashes, timeouts, FIFO ordering, and stream checkpoints.
10. **Observe:** custom record failure metrics, backlog, oldest age, iterator lag, and duplicate rates.
11. **Prepare recovery:** runbooks for DLQ inspection, redrive, poison messages, and replays.
12. **Review post-deploy:** monitor throughput, latency, cost, and retry rates to tune settings.

## 17. Conclusion

Partial batch failure lets a function request retries only for records that did not succeed, cutting duplicate work when a batch carries independent items. Yet semantics depend on the event source: SQS uses message IDs and acknowledgements/visibility; FIFO must preserve ordering; Kinesis and DynamoDB Streams use sequence numbers and checkpoints, meaning records after a failure point can re-run.

Retries and duplicates are normal behavior in distributed systems. Consumers need stable idempotency keys, unique constraints or conditional writes, transactions for database side effects, and provider idempotency/outbox patterns for external side effects. Testing must cover partial responses, crashes after commit, concurrent duplicates, poison messages, DLQ redrives, ordering, and checkpoints. Monitor record-level failures alongside invocation metrics to understand how batches actually behave in production.

When partial acknowledgements, retry policies, idempotency, and observability are designed together, Java functions can process batches efficiently without compromising business correctness on message redelivery.
