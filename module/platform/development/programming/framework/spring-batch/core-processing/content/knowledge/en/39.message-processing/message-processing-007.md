# Retrying Message Processing

In Spring Batch, message processing can include reading messages from a broker, transforming/validating payloads, and sending messages to another destination. When a broker is temporarily unavailable, a network timeout occurs, acknowledgements are delayed, or a consumer hits an infrastructure dependency error, the job needs a controlled retry mechanism.

Retries help handle recoverable errors without failing the job immediately. However, message retries carry unique risks: a send attempt may have already been accepted by the broker while the client never received the acknowledgement; on retry, the same message may be sent a second time. Similarly, a consumer may finish applying a business update but fail before the acknowledgement is confirmed, causing the broker to redeliver the message.

Therefore, retry design must simultaneously answer four questions:

- Which errors are recoverable and allowed to be retried?
- At which layer should retries occur: broker client, Spring Batch step, or broker/consumer mechanism?
- When is an attempt considered successful for checkpointing or acknowledging?
- How do we ensure duplicates caused by retries do not create duplicate business effects?

In Spring Batch, retries are typically configured on a chunk-oriented step via fault-tolerant processing. For a message producer, the writer must propagate send failures up to the step after awaiting results according to policy. For a message consumer, batch checkpoints must be coordinated with broker acknowledgement/visibility timeouts so messages are not lost and can be safely reprocessed.

## What Is Retry in Message Processing?

Retry is re-executing a failed operation after determining the error may be transient. In a message pipeline, that operation can be:

- Reading a message or payload from a source.
- Calling a service to enrich/validate a message.
- Sending a message to Kafka, JMS, or RabbitMQ.
- Writing processing state or results to a database.
- Acknowledging a message to the broker after business processing completes.

For example, a batch step reads pending events from an outbox and publishes them to Kafka. If Kafka temporarily loses connectivity, the writer can throw an exception. Spring Batch rolls back the chunk per the transaction manager and retries according to the configured policy. If the producer actually wrote the record before the connection dropped, the retry may send a duplicate. Consumers must recognize the event ID so they do not apply the business action twice.

Retries do not fix permanent data or configuration errors. Invalid payload schemas, missing topics, bad credentials, or serialization errors generally require failing, rejecting, or quarantining rather than retrying indefinitely.

## Distinguishing Retry Layers

A messaging system can retry across multiple layers. These layers cover different failure windows and can multiply attempt counts if uncoordinated.

| Layer | Executing Component | Example |
| --- | --- | --- |
| Client retry | Kafka producer, JMS provider, or AMQP client | Resending a request on a transient network error |
| Step retry | Spring Batch fault-tolerant step | Re-invoking processing when the writer throws an exception |
| Broker redelivery | Broker/consumer container | Redelivering an unacknowledged message |
| Application retry | Service or `RetryTemplate` | Retrying an infrastructure-dependent API call |
| Recovery/DLQ | Broker or application | Moving unprocessable messages to quarantine |

For example, a single `KafkaTemplate.send()` call may be retried internally several times by the producer. If the future still fails and the writer throws an exception, Spring Batch may retry the writer/chunk. If the first send was written by the broker but the acknowledgement was lost, the batch retry may resend the event. The consumer can also retry when its handler fails, and the broker redelivers if the message remains unacked.

Calculate the overall retry budget. Do not configure 10 retries at the client, 5 at the step, and 10 at the consumer without a total time limit; a single operation can end up retried excessively, prolonging the job and causing a retry storm.

## Classifying Errors Before Retrying

The most critical requirement is distinguishing transient errors from permanent ones.

| Error Group | Example | Handling Approach |
| --- | --- | --- |
| Transient infrastructure | Broker temporarily unavailable, network reset, brief timeout, leader election | Bounded retry with backoff |
| Throttling/quota | Broker returns rate limit or temporary overload | Backoff, reduce concurrency, or throttle throughput |
| Authentication/configuration | Invalid credentials, missing ACL, non-existent destination | Fail fast and fix configuration |
| Serialization/schema | Unserializable payload, incompatible schema | Reject/quarantine or fail; retrying usually does not help |
| Business validation | Missing business key, invalid state | Reject/skip per business rules |
| Duplicate/conflict | Event ID already processed, unique constraint conflict | Handle idempotently; do not retry blindly |
| Permanent resource failure | Queue/topic deleted, payload exceeds limit | Fail or route to appropriate recovery workflow |

Do not classify errors solely by the outermost exception class when a framework wraps exceptions. Inspect the cause chain and specific broker/client exceptions. For example, `MessagingException` may wrap either a transient timeout or a permanent serialization error.

### Retryable and Non-Retryable Exceptions

With Spring Batch, you can declare which exceptions are retried and which are not:

```java
return new StepBuilder("publishEventsStep", jobRepository)
        .<OutboxEvent, OutboxEvent>chunk(100, transactionManager)
        .reader(outboxReader)
        .writer(messageWriter)
        .faultTolerant()
        .retry(TransientBrokerException.class)
        .retryLimit(3)
        .noRetry(MessageSerializationException.class)
        .build();
```

`TransientBrokerException` and `MessageSerializationException` are application-defined exceptions in this example. In production, map Kafka/JMS/AMQP client exceptions to meaningful exception groups rather than retrying all `Exception`s.

Some exceptions may be infrastructure errors yet should not be retried immediately—for instance, authentication failures or topic authorization errors. Retrying continuously only generates log noise and delays failure detection.

### Do Not Retry Every Exception

The following example is overly broad:

```java
.faultTolerant()
.retry(Exception.class)
.retryLimit(20)
```

It can end up retrying programming bugs, validation failures, schema issues, and misconfigurations. Specify transient error types and cap attempts. If certain exceptions need different handling, use `noRetry`, skip policies, or an exception classifier per your Spring Batch version's API.

## Configuring Retry in Spring Batch

Chunk steps support fault tolerance via `faultTolerant()`. The retry policy specifies which exceptions are retried and the maximum retry count.

Basic example:

```java
@Bean
Step publishEventsStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OutboxEvent> eventReader,
        ItemWriter<OutboxEvent> messageWriter) {

    return new StepBuilder("publishEventsStep", jobRepository)
            .<OutboxEvent, OutboxEvent>chunk(100, transactionManager)
            .reader(eventReader)
            .writer(messageWriter)
            .faultTolerant()
            .retry(TransientBrokerException.class)
            .retryLimit(3)
            .build();
}
```

In the Spring Batch 5 API, `retryLimit(3)` expresses the configured retry limit for the specified exceptions; check how initial attempts and retry counts are counted in your specific version's documentation. Do not treat this number as the total broker request count if the client also performs internal retries.

If errors exceed the retry limit and no matching skip policy applies, the step fails. For events that must be published, this is usually the right choice: fail so operations can investigate and restart/replay rather than silently dropping messages.

### Combining Retry with Skip

Retry and skip serve different purposes:

- Retry: re-attempt the same operation because the error may be recoverable.
- Skip: accept bypassing a failing item per policy and record it.

Example skipping only invalid data errors while retrying transient broker errors:

```java
.faultTolerant()
.retry(TransientBrokerException.class)
.retryLimit(3)
.skip(InvalidEventException.class)
.skipLimit(50)
```

Do not configure skip on broker errors merely to let the job finish. If events are skipped without outbox/reject persistence, the system can lose events permanently.

## Backoff Between Retries

Tight retries with no pause can overload an already struggling broker even further. Backoff introduces waiting intervals between attempts.

Common strategies:

- **Fixed backoff:** a constant pause between attempts.
- **Exponential backoff:** wait time grows after each failure.
- **Exponential backoff with jitter:** adds randomness so many workers do not retry at the exact same instant.
- **Capped backoff:** caps the maximum wait duration.

Example exponential backoff:

```java
ExponentialBackOffPolicy backOff = new ExponentialBackOffPolicy();
backOff.setInitialInterval(500L);
backOff.setMultiplier(2.0);
backOff.setMaxInterval(10_000L);

return new StepBuilder("publishEventsStep", jobRepository)
        .<OutboxEvent, OutboxEvent>chunk(100, transactionManager)
        .reader(eventReader)
        .writer(messageWriter)
        .faultTolerant()
        .retry(TransientBrokerException.class)
        .retryLimit(4)
        .backOffPolicy(backOff)
        .build();
```

This example uses Spring Retry's `ExponentialBackOffPolicy`. Imports/packages and configuration APIs must match your project's Spring Batch/Spring Retry version. Some versions offer different builders or retry configuration styles; the principle remains bounded backoff.

With an initial interval of 500 ms and a multiplier of 2, intervals grow roughly to 0.5 s, 1 s, 2 s, 4 s, then cap at max interval. Total wait time must stay within SLAs and broker delivery timeouts.

### Jitter to Prevent Synchronized Retry Spikes

If 100 workers hit a broker outage together and all retry after exactly 1 second, they can create a simultaneous load spike. Jitter spreads out retry timestamps to reduce synchronization.

You can use a jitter-enabled backoff policy if supported by your library version, or a custom policy. Never add unbounded random delays; you still need a max interval and an overall deadline.

## Producer Client Retry vs. Spring Batch Retry

Producer clients can retry a send internally before returning a final outcome to the application. For example, a Kafka producer uses `retries` and `delivery.timeout.ms`; AMQP/JMS clients also have their own reconnect/recovery mechanisms.

Step retry starts after the writer receives the final error and throws an exception. Thus, total duration and attempt count are the combination of both layers:

```text
Spring Batch retry attempt 1
    |
    +--> Producer client send
    |       +--> internal retry
    |       +--> internal retry
    |       +--> final failure
    |
    +--> writer throws TransientBrokerException
    |
    +--> step backoff
    |
Spring Batch retry attempt 2
    |
    +--> Producer client sends again
            ...
```

Set timeouts and retry budgets according to total duration. For instance, if the producer can spend up to 30 seconds on one record, 3 step retries could keep a chunk waiting more than 90 seconds plus backoff. The chunk transaction may hold locks throughout that window.

For prolonged broker outages, a separate outbox publisher step usually keeps the initial business transaction from staying open while waiting for the broker to recover.

## Retries in a Message-Sending Writer

The writer must report failures at the right time so Spring Batch can decide on retries. If sending asynchronously, never return before knowing the outcome required by policy.

Example Kafka writer awaiting results:

```java
public class KafkaEventWriter implements ItemWriter<OutboxEvent> {

    private final KafkaTemplate<String, EventPayload> kafkaTemplate;

    @Override
    public void write(Chunk<? extends OutboxEvent> chunk) throws Exception {
        List<CompletableFuture<SendResult<String, EventPayload>>> futures =
                new ArrayList<>();

        for (OutboxEvent event : chunk) {
            EventPayload payload = toPayload(event);
            futures.add(kafkaTemplate.send(
                    "domain-events",
                    event.aggregateId(),
                    payload));
        }

        for (CompletableFuture<SendResult<String, EventPayload>> future : futures) {
            future.get(30, TimeUnit.SECONDS);
        }
    }
}
```

This example uses Spring Kafka 3.x. Older versions may use a different future type. In real code, translate future exceptions into appropriate transient/permanent exceptions and keep event IDs stable.

If one future fails after other futures succeeded, the writer throwing an exception can roll back the chunk, yet messages already accepted by the broker remain. When Spring Batch retries the chunk, they may be sent again. This is why consumers must be idempotent and event IDs must stay stable across retries.

### Never Swallow Send Errors

Do not write:

```java
try {
    kafkaTemplate.send(topic, key, payload);
} catch (Exception ex) {
    log.warn("Could not send", ex);
    // continue and return as if successful
}
```

This snippet does not even await the future, and if an error is reported asynchronously, the `catch` block misses it completely. The step can commit its checkpoint even though messages were never sent.

Await results, classify exceptions, and propagate errors when required operations fail.

## Retries When Reading Messages from a Broker

A batch step can read messages from a broker or from a staging/inbox table. With a message broker, you must coordinate fetching messages, processing chunks, and acknowledging.

General model:

```text
Broker / queue
    |
    v
Message reader / adapter
    |
    v
Processor
    |
    v
Writer (database or next broker)
    |
    v
Commit business result
    |
    v
Broker acknowledgement
```

The critical decision is whether acknowledgement happens before or after the business result commits. If you ack first and the database rolls back, messages can be lost. If the database commits first and the ack fails, the broker may redeliver and messages get reprocessed.

With JMS, consumer acknowledgement/session transaction semantics depend on the listener/container and transaction manager. With Kafka, consumer offset commit marks progress; committing offsets before the business transaction can lose messages, while committing after can lead to duplicates on a mid-step crash. With RabbitMQ, post-processing consumer ack is standard so the broker redelivers if a worker dies before acking.

Spring Batch does not automatically know how to acknowledge every broker. The adapter/reader or an integration layer must manage acknowledgement per the broker's contract. If complex retry/redelivery is required, use supported integration mechanisms and test against a real broker.

### Message Visibility Timeout and Leases

Some queue services use visibility timeouts or leases. If processing a message exceeds the timeout, the broker may hand the message to another worker while the first worker is still running. Extend visibility/leases or choose a long enough timeout; consumers still need idempotency because timeouts and crashes can create concurrent duplicates.

### Never Acknowledge Messages Before Commit

If a message is acked before the database commits, a subsequent failure can remove the message from the queue even though business work was not saved. Generally, ack after business processing succeeds according to the integration layer's transaction semantics. However, exact transaction coordination depends on the broker and framework; do not apply one generic rule blindly across all adapters.

## Retrying Processors and Supporting Services

Not all message errors occur in the writer. A processor might call an external service for fraud checks, exchange rates, or metadata enrichment. If that service is temporarily unavailable, retries can be appropriate.

```java
return new StepBuilder("enrichEventsStep", jobRepository)
        .<RawEvent, EnrichedEvent>chunk(100, transactionManager)
        .reader(eventReader)
        .processor(enrichmentProcessor)
        .writer(eventWriter)
        .faultTolerant()
        .retry(TransientServiceException.class)
        .retryLimit(3)
        .build();
```

If a processor calls an API with side effects, retries can execute that action multiple times. For non-idempotent operations, use an idempotency key or design the API call as query/read-only. Ideally, processors compute deterministic outputs from inputs and dependencies that are safe to retry.

## Stateful vs. Stateless Retry

Retries can occur within the same call flow (stateless) or persist retry state across calls (stateful), depending on the framework/policy.

- **Stateless retry:** the operation is retried immediately within the same execution context until it succeeds or hits the limit.
- **Stateful retry:** maintains retry state tied to a key/item across invocations, useful when failures require rolling back and retrying in a new transaction.

In a chunk step, Spring Batch manages retry context and item identity per fault-tolerant step mechanics. Never store retry counters in a singleton field on the writer, because multiple items/executions can share the writer and restarts lose that state.

If retries must survive job restarts or span scheduled runs, persist attempt/deadline state in a database/outbox or use the broker's redelivery policy. In-memory step retries are not an infinite durable retry queue.

## Retries and Chunk Transactions

A chunk transaction can roll back when the writer throws an exception. Spring Batch can then retry per policy. However, rolling back the database cannot revoke messages already accepted by the broker unless the broker participates in a shared transaction.

Example:

```text
Chunk attempt 1
    |
    +--> publish event A -> broker confirms
    +--> publish event B -> timeout (unknown outcome)
    +--> writer throws
    +--> database transaction rolls back
    |
Chunk retry
    |
    +--> publish event A again
    +--> publish event B again
```

Event A may be sent twice. Event B may have already been accepted by the broker despite the client timeout. You cannot distinguish the outcome with certainty from a timeout alone. Consumers must deduplicate by event ID, or the publisher needs a durable protocol such as outbox plus idempotent consumers.

### Do Not Hold Transactions Open Long During Backoff

If retries occur inside a chunk transaction, the transaction/connection may remain held during the wait depending on retry placement and transaction boundaries. That can hold locks, exhaust connection pools, and reduce throughput.

Set appropriate timeouts/backoff and avoid long in-transaction retries for broker outages. When brokers suffer frequent disruptions or require minutes/hours of retries, splitting publishing into an outbox publisher job/step with short transactions is usually much easier to operate.

## Transactional Outbox for Durable Retries

A transactional outbox stores the intent to emit messages in the same database transaction as business changes. A separate publisher reads pending outbox rows and sends them to the broker.

```text
Business chunk transaction
    |
    +--> update business row
    +--> insert outbox row (PENDING)
    +--> COMMIT
             |
             v
       Outbox publisher step
             |
             +--> claim pending row
             +--> publish message
             +--> wait for acknowledgement
             +--> mark published
```

If the broker is unavailable, the outbox row remains for the publisher to retry in a subsequent run. The business transaction does not need to stay open while waiting for the broker to recover.

### Retrying the Outbox Publisher

The publisher can use Spring Batch retries for transient errors within an execution and outbox status to retry in later executions. Example:

```java
.faultTolerant()
.retry(TransientBrokerException.class)
.retryLimit(5)
.backOffPolicy(backOffPolicy)
```

Once retries are exhausted, do not delete the outbox row. You can leave it `PENDING`, move it to `RETRY` with `next_attempt_at`, or transition it to `FAILED`/`DEAD` after operational thresholds for operator handling. Exact statuses should reflect whether the publisher knows for sure the broker did not receive the message or the outcome is unknown.

### Claims and Leases

Multiple publishers must not send the same outbox row concurrently if you want to minimize duplicates. You can claim rows via status/lease:

```sql
UPDATE outbox_event
SET status = 'PROCESSING',
    lease_owner = :workerId,
    lease_until = :leaseUntil
WHERE event_id = :eventId
  AND (status = 'PENDING' OR lease_until < :now)
```

This is a conceptual example; use database-appropriate locking/conditional updates and check the updated row count. Leases must be long enough or renewed during slow publishes. If a worker dies after the broker accepts the message but before marking published, the lease expires and the event may be resent. Event IDs and consumer idempotency remain necessary.

## Idempotency: The Essential Condition for Message Retries

Idempotency means executing the same operation multiple times yields a final business outcome equivalent to executing it once. For messages, consumers should recognize already-processed messages via a stable ID.

Example inbox table:

```sql
CREATE TABLE processed_message (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

The consumer processes inside a single transaction:

1. Insert `(consumer_name, event_id)` into the inbox.
2. If the insert succeeds, apply the business update.
3. Commit the business update and inbox record together.
4. If the unique key already exists, treat the message as an already-processed duplicate and acknowledge per policy.

If the business update fails, the transaction rolls back the inbox insert as well; the broker can redeliver and the consumer retries. If the inbox commits separately from the business update, a message can be marked processed even though the business operation failed.

### Event IDs Must Stay Stable Across Retries

Never generate a new UUID each time the writer resends the same logical event. Generate the event ID beforehand, store it with the outbox/item, and reuse it across every retry/restart. If each retry carries a different ID, consumers cannot deduplicate.

Kafka producer idempotence reduces duplicates from producer session retries, but does not solve the case where Spring Batch restarts and resends the same event via a new producer operation. Event IDs and consumer inboxes still serve their own distinct role.

## Retries, Dead-Lettering, and Recovery

Once retries are exhausted, the message needs a clear recovery state. Depending on the error type, you can:

- Fail the step so operators fix the broker/configuration and restart.
- Keep the outbox row in a retryable state for the publisher to handle later.
- Route invalid payloads to a reject store/DLQ.
- Mark a permanent failure and raise an alert/incident.
- Replay from a durable source after fixing the error.

Do not automatically route every retry-exhausted error to a DLQ. A broker outage may not be a message defect; pushing all events to a DLQ breaks ordering and increases replay overhead. Conversely, poison messages that can never be processed in the main queue may require dead-lettering.

### Poison Messages

A poison message is a message that always fails due to a permanent payload defect or fixed condition—such as an invalid schema, missing required field, or event version unsupported by consumer code. Retries cannot fix that error and can block subsequent messages if the broker enforces ordering.

For poison messages:

1. Identify permanent errors via validation/schema checks.
2. Record payload/reference, event ID, and root cause into a safe reject store/DLQ.
3. Acknowledge or move the message per policy once the reject is durably persisted.
4. Alert operators and monitor reject rates.
5. Replay only after the payload or consumer has been fixed.

Do not log secrets or full sensitive data in DLQ metadata. Proper retention and access controls are required.

## Circuit Breakers and Retry Limits

When a broker or dependency is down for an extended period, continuous retries stop being helpful. A circuit breaker can stop calling the dependency for a window after crossing an error threshold, then allow probes to test recovery.

Retry and circuit breaker differ:

- Retry re-attempts an operation after a failure.
- Circuit breaker temporarily stops calling a dependency with a high failure rate.
- Rate limiter caps request rate.
- Bulkhead limits resources/concurrency dedicated to a dependency.

You can use Spring Retry/Resilience4j or appropriate broker client mechanisms, but avoid stacking multiple retries/circuit breakers without a unified budget. When the circuit is open, the writer should throw a classified exception so the step fails or defers execution as planned; never pretend success.

## Ordering and Retries

Retries can affect message order. For instance, event A times out on send, event B succeeds, and then A is retried. Consumers may receive B before A.

To manage ordering:

- Use stable partition/aggregate keys.
- Avoid letting a later message overtake an earlier one when business invariants require sequence.
- Use sequence numbers/versions on aggregates.
- Have consumers check versions and handle out-of-order events per policy.
- If strict ordering is mandatory, serialize publishing per key and design controlled retry/parking-lot queues.

Kafka ordering is scoped to a partition; RabbitMQ/JMS ordering also depends on queues, consumer concurrency, redelivery, and broker configuration. Never assume retries preserve original ordering automatically.

## Observability for Retries

Retries should be observed as an operational signal, not merely exception logs.

Recommended metrics:

- Retry counts by step, exception type, and destination.
- Send success/failure counts.
- Acknowledgement and backoff latencies.
- Pending/retry/failed message counts in the outbox.
- Redelivered or deduplicated message counts.
- Messages routed to DLQ/reject store.
- Chunk rollbacks and step restarts.
- Age of oldest pending message/outbox row.
- Broker availability, producer errors, and consumer lag.

Logs should include `eventId`, `correlationId`, `JobExecutionId`, `StepExecutionId`, destination, and attempt number. Avoid logging full sensitive payloads.

A useful alert monitors pending outbox age or retry rates exceeding thresholds, rather than alerting on every single retried request. That distinguishes brief transient blips from prolonged outages.

## Complete Retry Configuration Example

Example combining an outbox reader, message-sending writer, transient exception retries, backoff, and invalid-data skips:

```java
@Bean
Step publishOutboxStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OutboxEvent> outboxReader,
        ItemProcessor<OutboxEvent, OutboxEvent> eventValidator,
        ItemWriter<OutboxEvent> kafkaWriter) {

    ExponentialBackOffPolicy backOff = new ExponentialBackOffPolicy();
    backOff.setInitialInterval(500L);
    backOff.setMultiplier(2.0);
    backOff.setMaxInterval(8_000L);

    return new StepBuilder("publishOutboxStep", jobRepository)
            .<OutboxEvent, OutboxEvent>chunk(50, transactionManager)
            .reader(outboxReader)
            .processor(eventValidator)
            .writer(kafkaWriter)
            .faultTolerant()
            .retry(TransientBrokerException.class)
            .retryLimit(4)
            .noRetry(MessageSerializationException.class)
            .skip(InvalidEventException.class)
            .skipLimit(20)
            .backOffPolicy(backOff)
            .build();
}
```

This example shows configuration structure, not a complete production setup for every broker. You must establish whether the writer awaits acknowledgements, which transaction claims/marks outbox rows, and whether event IDs are stable. When skipping `InvalidEventException`, include durable reject/audit persistence; otherwise items can disappear from the pipeline without a trace.

## Testing Message-Processing Retries

Test retries at multiple levels: writer unit tests, step integration tests, and broker integration tests. Mocks only prove code calls the right APIs; broker tests prove acknowledgement/redelivery/transaction semantics.

### Unit Testing Retryable Exceptions

Create a writer test double that fails twice and then succeeds. Run the step and verify invocation counts match the retry policy, the job completes, and output is accurate.

```java
AtomicInteger attempts = new AtomicInteger();

ItemWriter<OutboxEvent> flakyWriter = chunk -> {
    if (attempts.incrementAndGet() < 3) {
        throw new TransientBrokerException("temporary failure");
    }
};
```

With an appropriate retry limit configured, the test verifies the step retries and then succeeds. Use a real transaction manager/test repository for step integration rather than calling `write()` directly.

### Unit Testing Permanent Exceptions

Have the writer throw `MessageSerializationException`. Verify the exception is not retried per policy and the step fails or skips as configured. Count attempts to prove permanent errors do not trigger useless retries.

### Testing Backoff

Do not wait long durations in unit tests. Inject a policy/clock or use short backoff intervals in tests; verify attempt counts, ordering, and total duration stay within bounds. Do not make tests flaky with long sleeps.

### Testing Future Failures

With a Kafka writer, create a future that completes exceptionally and verify `write()` waits and throws an exception. Test future timeouts and failures occurring after some earlier futures succeeded. Verify the writer never returns success before required sends complete.

### Testing the Duplicate Window

Simulate the broker accepting an event while the client times out before receiving the acknowledgement. The step retries and resends the same event ID. Consumer tests must apply the business effect only once thanks to inbox/idempotency. This is a critical test to verify at-least-once behavior.

### Testing Transaction Rollbacks

Have a chunk send several messages and then fail. Verify the database transaction rolls back properly; inspect which messages exist on the broker. The test must demonstrate that side effects outside the transaction do not automatically roll back.

### Testing Consumer Acknowledgement/Redelivery

With a test broker, let the consumer process a business update and then simulate a crash before ack. The broker can redeliver. Verify the consumer inbox prevents duplicates and the message is eventually acknowledged after business results commit.

### Testing Outbox Recovery

Simulate these scenarios:

1. Business transaction rolls back: no outbox row exists.
2. Business transaction commits, broker unavailable: outbox remains pending.
3. Broker accepts event, publisher dies before marking published: publisher resends after lease expiry.
4. Consumer receives duplicate: business effect occurs only once.
5. Permanent payload error: row moves to reject/dead per policy with an audit trail.

### Testing Retry Storms and Circuit Breakers

Simulate prolonged broker unavailability and verify retries are bounded, backoff/jitter work, and circuit breakers/rate limiters prevent unbounded load growth. Monitor connection/thread counts and transaction durations.

## Common Mistakes

### Retrying Every Exception Type

Schema, validation, or authorization errors do not heal with retries. Classify transient vs. permanent errors.

### Failing to Bound Retries

Jobs can hold transactions/connections indefinitely and cause retry storms. Set retry limits, deadlines, and backoff caps.

### Stacking Multi-Layer Retries Without a Budget

Client, step, and broker redelivery can multiply attempt counts. Calculate total duration and request count.

### Sending Async Without Awaiting Acknowledgement

The writer can return success before send failures surface. Await/flush per contract and propagate errors to the step.

### Assuming Rollback Revokes Already-Published Messages

Database and broker are two independent resources without transaction coordination. Use outbox or idempotency.

### Changing the Event ID on Each Retry

Consumers cannot recognize duplicates. Keep event IDs stable across retries/restarts.

### Handling Broker Outages with Skip

Skip can lose events. Retry/fail or keep outbox rows pending.

### Acking Messages Before Business Commit

A crash after ack can lose messages even though business updates never committed. Coordinate ack after commit per broker semantics.

### Non-Idempotent Consumers

Redeliveries or publisher retries can create duplicate business effects. Use inboxes/unique event IDs and transactions.

### Neglecting Poison Messages

Permanently failing messages can loop infinitely and block queues. Reject/DLQ with audits and a replay procedure.

### Missing Backoff/Jitter

Many workers retrying simultaneously overload the broker further. Use capped backoff and jitter.

### Holding Chunk Transactions Too Long

Long backoff can hold locks and connections. Separate an outbox publisher or tighten in-transaction retry budgets.

### Not Observing Attempts and Event IDs

Makes it hard to tell which messages were sent, how many times they retried, and what needs replay. Attach correlation/event IDs and metrics.

## Design Principles

When designing retries for message processing, establish:

1. Is the retried operation a read, process, publish, or acknowledge?
2. Does retry live in the client, Spring Batch, broker, or application service?
3. Which exceptions are transient and which are permanent?
4. What are the retry limit, backoff, jitter, and overall deadline?
5. Are internal producer retries included in the shared retry budget?
6. Does the writer await acknowledgement before returning?
7. Are the database chunk and broker transaction genuinely coordinated?
8. If a send outcome is unknown, does the event ID stay stable for deduplication?
9. Does the consumer have an inbox/idempotency and ack after business commit?
10. Is an outbox needed to persist publishing intent durably?
11. How are poison messages rejected/DLQ'd and replayed?
12. Can ordering change during retries or redeliveries?
13. Does monitoring expose attempts, latency, pending age, duplicates, and DLQ metrics?
14. Do integration tests simulate broker outages, ack timeouts, duplicates, rollbacks, restarts, and recovery?

Message-processing retries should be designed as a bounded recovery mechanism. Use Spring Batch retries for transient step exceptions, backoff to ease broker pressure, and classify permanent failures to fail/reject properly. Writers must await send outcomes per policy; consumers must acknowledge per transaction semantics and remain idempotent on redelivery. When database updates and publishing must stay consistent, a transactional outbox paired with a consumer inbox usually offers cleaner recovery than direct publishing. Always keep event IDs stable, budget retries across all layers, and test failure windows across broker acknowledgements, database commits, and restarts.

## Key Takeaways

Retrying message processing means re-attempting read, process, publish, or acknowledge operations on recoverable errors. Distinguish client retries, Spring Batch step retries, broker redeliveries, and application retries; bound total attempts and duration to prevent retry storms. Use `.faultTolerant().retry(...).retryLimit(...)` for transient exceptions, `noRetry` for permanent failures, skip only when items are durably rejected/audited, and capped backoff with jitter. Message writers must await acknowledgements per policy before returning; send timeouts can leave outcomes unknown, so retries may produce duplicates. Database rollbacks do not revoke broker messages unless both resources share a transaction. Keep event IDs stable, ensure consumer idempotency/inbox, and ack after business commits. Transactional outbox persists publishing intent alongside business updates; publishers can still resend, so consumers must deduplicate. Track attempts, event IDs, pending age, redeliveries, and DLQs; test broker outages, ack timeouts, duplicates, rollbacks, restarts, and recovery against a production-equivalent broker.
