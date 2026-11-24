# UNLIMITED_ATTEMPTS and Risks

In Spring Kafka, unlimited retries allow a record to keep being retried until it succeeds or until the system or an operator actively stops the flow. With Spring's backoff mechanism, the **UNLIMITED_ATTEMPTS** constant indicates that no finite retry count is configured. A common usage is combining **FixedBackOff** with **DefaultErrorHandler**.

Unlimited retries can be useful when an application is not allowed to skip a record and the error is strictly transient. However, it can also stall a partition on a single failing record, increase lag, tie up resources long-term, and delay subsequent data. If the actual error is permanent, unlimited retries simply repeat the exact same failure.

Therefore, `UNLIMITED_ATTEMPTS` is a recovery-policy choice, not a guarantee that the record will eventually succeed. To use it safely, clearly define which exception types are retried, backoff, timeouts, manual recovery capabilities, idempotency, and how stuck records are observed.

## 1. What does UNLIMITED_ATTEMPTS mean?

With finite retries, the error handler stops retrying after the configured attempt count. Once retries are exhausted, the handler can invoke a recoverer, send the record to a Dead Letter Topic (DLT), or perform another recovery action.

With unlimited retries, there is no retry-count threshold that automatically ends the retry loop. A record may be redelivered many times over a long period. If the dependency recovers and a subsequent attempt succeeds, the stream continues. If the underlying cause never changes, the record keeps failing.

It is important to distinguish:

- **Initial processing attempt:** the first time the listener receives the record.
- **Retry attempt:** a redelivery after a previous processing attempt failed.
- **Total listener invocations:** includes the initial attempt and all retries.
- **Recovery:** the action after the retry policy ends, such as sending to a DLT.

With unlimited retries, there is no automatic point where attempts run out to trigger recovery based on an attempt limit. To have an exit path, the application must rely on another condition, such as non-retryable exception classification, intentionally stopping the container, data intervention, or routing the record through a separate process.

## 2. Configuring with FixedBackOff and DefaultErrorHandler

Spring Kafka uses **DefaultErrorHandler** to handle exceptions from non-transactional listeners. The error handler takes a **BackOff** to determine the wait interval between retries.

Example configuring unlimited retries with a fixed wait interval:

~~~java
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Bean
DefaultErrorHandler kafkaErrorHandler() {
    FixedBackOff backOff =
        new FixedBackOff(2_000L, FixedBackOff.UNLIMITED_ATTEMPTS);

    return new DefaultErrorHandler(backOff);
}
~~~

In this example, the listener is retried after every 2-second wait and does not stop based on retry count. **FixedBackOff.UNLIMITED_ATTEMPTS** is Spring Framework's sentinel indicating unlimited retries; verify the package and API against your application's Spring Framework/Spring Kafka version.

If you want recovery for other errors, a recoverer can be passed in:

~~~java
@Bean
DefaultErrorHandler kafkaErrorHandler(
        DeadLetterPublishingRecoverer recoverer) {

    FixedBackOff backOff =
        new FixedBackOff(2_000L, FixedBackOff.UNLIMITED_ATTEMPTS);

    DefaultErrorHandler handler =
        new DefaultErrorHandler(recoverer, backOff);

    handler.addNotRetryableExceptions(
        InvalidOrderException.class,
        UnsupportedEventVersionException.class
    );

    return handler;
}
~~~

Here, exceptions marked as non-retryable can proceed to recovery without waiting through an infinite retry loop. Other errors still follow the error handler's classification and `BackOff`. Check the exceptions treated as fatal/non-retryable by default in the version you use.

### 2.1. Unlimited retries does not mean immediate retries

An unlimited retry count does not dictate the wait interval. Two parameters have separate responsibilities:

- **UNLIMITED_ATTEMPTS:** imposes no threshold on the number of retries.
- **BackOff interval:** determines the wait time before the next retry.

Examples:

| Configuration | Behavior |
|---|---|
| FixedBackOff(0, UNLIMITED_ATTEMPTS) | Retries continuously with virtually no wait |
| FixedBackOff(1000, UNLIMITED_ATTEMPTS) | Retries indefinitely, waiting roughly 1 second between attempts |
| FixedBackOff(10000, UNLIMITED_ATTEMPTS) | Retries indefinitely, waiting roughly 10 seconds between attempts |

Unlimited retries with a delay of 0 are usually very dangerous: the consumer can enter a tight error loop, consuming CPU and placing heavy load on the dependency. Always choose a finite, deliberate backoff.

### 2.2. Registering the error handler with the listener container

Factory example:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory,
        DefaultErrorHandler kafkaErrorHandler) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(kafkaErrorHandler);
    return factory;
}
~~~

Declaring a `DefaultErrorHandler` bean alone is not enough if the actual listener container does not use that bean. Confirm that the factory is attached to `@KafkaListener` and that the container's error handler configuration is active.

## 3. How do unlimited retries differ from ExponentialBackOff?

Retry limits and backoff schedules are two independent dimensions. You can have a finite retry count with exponential backoff, or unlimited retries with a fixed delay. Do not confuse max interval with max attempts.

| Policy | Retry count | Wait interval |
|---|---:|---|
| Finite FixedBackOff | Bounded | Fixed |
| FixedBackOff with UNLIMITED_ATTEMPTS | Unlimited | Fixed |
| ExponentialBackOff with max elapsed time | Stops based on time budget | Increasing, capped |
| ExponentialBackOffWithMaxRetries | Bounded by attempt count | Increasing, capped |

Spring Framework's **ExponentialBackOff** has a `maxElapsedTime` limit. When used, the retry sequence stops once the time budget expires, even if the final delay has not reached a specific retry count. Spring Kafka's **ExponentialBackOffWithMaxRetries** is suitable when you want to specify an explicit retry count.

If the requirement is unlimited retries with increasing delays, you need a `BackOff` with matching semantics and must verify the implementation's elapsed-time limit. Do not assume that merely setting a large max interval makes the retry count unlimited.

## 4. Unlimited retries and blocking retry

With `DefaultErrorHandler`, blocking retry typically takes place within the listener container's processing flow. When a record fails, the container waits for `BackOff` and then retries that record before proceeding according to container semantics.

High-level flow:

~~~
poll() receives record
       |
       v
Listener processes record
       |
       v
Exception
       |
       v
DefaultErrorHandler
       |
       v
Wait BackOff
       |
       v
Invoke listener again
       |
       +---- Success -> continue and commit per AckMode
       |
       +---- Failure -> go back to wait and retry
~~~

With `UNLIMITED_ATTEMPTS`, the failure branch can loop indefinitely. This leads to several consequences:

- The failing record can block processing of subsequent records in the same partition.
- The consumer thread is held by retries and backoff.
- Consumer lag on the partition can keep climbing.
- If total time without polling exceeds `max.poll.interval.ms`, the group may rebalance.
- After a rebalance or restart, uncommitted records may be re-read and side effects may repeat.

Blocking retry can fit when partition ordering must be preserved and errors are expected to recover quickly. For prolonged errors or retries spanning many minutes/hours, blocking unlimited retries is rarely a good choice.

## 5. Unlimited retries and non-blocking retry topics

Spring Kafka supports non-blocking retry via **@RetryableTopic** and retry topics. Failed records are moved to retry topics on a backoff schedule; the main consumer can continue processing other records.

Some Spring Kafka versions provide an **UNLIMITED_ATTEMPTS** sentinel for retry topic configuration. The constant's location, data type, and how it is passed to annotations/builders depend on the version. Use the constant specified in your application version's documentation/Javadoc rather than substituting a very large number or guessing a string.

Configuration concept:

~~~java
@RetryableTopic(
    attempts = "5",
    backoff = @Backoff(
        delay = 1_000,
        multiplier = 2.0,
        maxDelay = 10_000
    )
)
@KafkaListener(topics = "orders", groupId = "billing")
public void handle(OrderEvent event) {
    billingService.process(event);
}
~~~

This is a finite retry-topic example illustrating how backoff is declared. When unlimited attempts are needed, replace the `attempts` value with the sentinel supported in your Spring Kafka version. Do not copy a constant from another version without verifying the API.

Retry topics have the benefit of not holding the main consumer during long backoffs, but carry their own risks:

- A record may be processed after newer records, altering ordering.
- Retry topics continue accumulating if the dependency does not recover.
- Retry topic consumer groups still consume resources.
- If retries are unlimited, there is no attempt threshold to automatically move records to the DLT once attempts are exhausted.
- Retry topic retention may expire records before they are reprocessed.

Retry topics do not make errors disappear. They shift where waiting happens and move backlog management to another stream.

## 6. Risk 1: Poison records stalling a partition indefinitely

A poison record is a record that always fails due to unprocessable payload, schema, or business state. With unlimited retries, such a record can be redelivered forever.

Example:

1. Consumer reads record at offset 100.
2. Listener fails deserialization or validation.
3. Error handler waits and retries offset 100.
4. The error recurs because the payload does not change.
5. Offsets 101, 102, and subsequent records in the partition are not processed in normal order.

The result is rising lag and blocked data. If the record raises a permanent exception, unlimited retries offer zero chance of recovery.

Solutions:

- Classify permanent exceptions as non-retryable.
- Route unprocessable records to a DLT or rejection workflow.
- Store topic, partition, offset, event ID, and root cause.
- Establish a process to fix payloads/schemas and perform controlled replay.
- Monitor partition lag and oldest record age.

## 7. Risk 2: Retry storms and overloading dependencies

If many consumers encounter failures simultaneously, unlimited retries can generate a continuous stream of requests against a database or HTTP service. When a dependency is already overloaded, retry requests make recovery harder.

For example, 40 consumers retrying every 100 ms can generate hundreds of requests per second. Without backoff, concurrency limits, or a circuit breaker, retry traffic can exceed original business traffic.

Mitigation measures:

- Use backoff with sufficiently large wait intervals.
- Consider exponential backoff with a max interval.
- Add jitter to spread retries across instances.
- Limit concurrency and simultaneous requests to the dependency.
- Use a circuit breaker or pause consumers when the dependency is unavailable.
- Set finite timeouts for every dependency call.
- Monitor retry rates and dependency error rates.

A circuit breaker does not replace a retry policy. When the circuit opens, the listener needs explicit behavior: wait, route to a retry topic, pause/stop the container cleanly, or let the error handler act per policy.

## 8. Risk 3: Consumer lag and max.poll.interval.ms

With blocking retry, backoff time and dependency call time count toward the time before the consumer returns to the next poll. With unlimited retries, a processing cycle can stretch indefinitely.

When a consumer exceeds **max.poll.interval.ms**, the group may deem the consumer stalled and revoke its partitions. Another consumer may take over the partition and read from the latest committed offset. An in-flight record may be redelivered while the old consumer still has side effects running.

This can cause:

- Repeated rebalances.
- Duplicate side effects.
- Rapidly growing lag.
- Multiple consumers reprocessing the same business action if prior work has not stopped.

Do not set `max.poll.interval.ms` to an enormous value just to legitimize unlimited retries. Bound each dependency call, compute a retry budget, and choose retry topics or pause/resume if long waits are necessary.

## 9. Risk 4: Duplicate side effects

Suppose a listener performs:

1. Successfully calls an invoice-creation API.
2. Then encounters an error updating state or committing the offset.
3. The record is retried.
4. The listener calls the invoice-creation API again.

If the API is not idempotent, two invoices may be created for the same order. Unlimited retries increase duplication probability as attempt counts grow.

Use an event ID or idempotency key that stays stable across all retries. A consumer can store processed event IDs in the same database transaction as business state changes:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

If the event ID already exists, skip the duplicate side effect. Recording the event ID and updating business data must occur within the same transaction to avoid race conditions.

For HTTP APIs or external services, pass an idempotency key if supported. If no idempotency mechanism exists, query the operation's status before resending a command whose outcome is uncertain.

## 10. Risk 5: No termination point and DLT never receives the record

In finite retries, once attempts are exhausted, the error handler can invoke a recoverer to send the record to the DLT. With unlimited retries, attempts never run out, so there is no "attempts exhausted" event to automatically trigger threshold-based recovery.

This means:

- The DLT does not automatically become the destination for all failed records under unlimited retries.
- Records can remain trapped in retry loops or retry topics forever.
- Operators need a separate diversion condition if they want to stop retries.
- Permanent exceptions must be classified as non-retryable or have an independent recovery path.

If the requirement is "retry transient errors indefinitely, but invalid data must go to the DLT", configure explicit exception classification. Unlimited attempts should apply only to the retryable exception group; permanent errors must go to recovery immediately or after a finite number of attempts.

## 11. Risk 6: Retention and losing the chance to replay

A retry topic is a normal Kafka topic and is subject to retention policies. If a record waits too long and retention expires before the retry consumer reads it, the record can be deleted per log retention policy.

With unlimited retries, a record's lifetime is unbounded by retry count. Therefore, retention must be long enough relative to the maximum outage duration the business wants to tolerate. If failed records must be retained longer, a DLT or a separate durable store may be more appropriate.

Do not assume unlimited attempts implies permanent storage. Unlimited retry counts and retention are two independent mechanisms.

## 12. Risk 7: Altered ordering

Blocking retry typically keeps the failed record at the head of the partition's processing stream, so subsequent records must wait. This maintains per-partition processing order but reduces progress.

Non-blocking retry topics let the main consumer continue, but the failed record may return after newer records. Example:

~~~text
Main topic:   A1 -> A2 -> A3
                  |
                  +-- A2 fails, moved to retry topic

Main consumer continues: A1 -> A3
Retry topic processes later: A2
~~~

The processing outcome can become A1, A3, A2. If A2 and A3 mutate the same aggregate in a mandatory sequence, business results can be wrong.

Before using unlimited non-blocking retries, define ordering requirements by key/partition. If ordering must be preserved, consider bounded blocking retries, isolating error streams, or designing a versioned/sequenced state machine to reject out-of-order updates.

## 13. Risk 8: Rising resource and operational costs

Unlimited retries can increase:

- Dependency call volume and API costs.
- Consumer thread hold time and memory usage.
- Retry topic backlog size.
- Metric/log volume and storage costs.
- Investigation and replay toil for operations teams.
- Duration records spend outside SLOs.

If a record cannot be processed for hours, decide whether to keep it in a retry loop or move it into a workflow with explicit state. A record waiting forever without an owner or alert becomes forgotten data.

## 14. When should unlimited retries be used?

Unlimited retries are only suitable when all of the following critical conditions are met:

- Errors belong to the transient group or can self-recover without payload fixes.
- The business forbids skipping the record.
- Holding the record waiting does not violate SLOs, or a process accepts very long delays.
- Finite backoff and finite timeouts exist for every dependency call.
- Idempotency mechanisms protect side effects.
- Dashboards/alerts exist to detect prolonged retrying records.
- There is a way to stop, fix, or reroute records when conditions change.
- Retry topic retention matches the outage window to be tolerated.

An example worth considering: an internal consumer processing durable commands, depending on a service with a clear recovery SLA, where processing even after several minutes/hours remains valuable. Even then, control load and have operational mechanisms to detect backlogs.

## 15. When should it NOT be used?

Avoid unlimited retries when:

- Exceptions are commonly permanent, such as invalid schemas or business validation failures.
- A failing record can block an entire critical partition.
- The dependency lacks timeouts or cannot have concurrency limited.
- Side effects are non-idempotent and results cannot be queried before retrying.
- Retries violate `max.poll.interval.ms` or cause continuous rebalances.
- Retry topics have shorter retention than potential wait durations.
- There are no alerts, owners, or procedures for stuck records.
- The business requires a final failure notification within a specific deadline.

In these cases, finite retries with a DLT, bounded retry topics, or workflows persisting pending state are easier to operate.

## 16. Combining unlimited attempts with exception classification

A safe design rarely applies unlimited retries to every exception. Only a specific set of transient exceptions is retried indefinitely; permanent exceptions go straight to recovery or the DLT.

Example:

~~~java
@Bean
DefaultErrorHandler errorHandler(
        DeadLetterPublishingRecoverer recoverer) {

    FixedBackOff backOff =
        new FixedBackOff(5_000L, FixedBackOff.UNLIMITED_ATTEMPTS);

    DefaultErrorHandler handler =
        new DefaultErrorHandler(recoverer, backOff);

    handler.addNotRetryableExceptions(
        InvalidOrderException.class,
        UnsupportedEventVersionException.class,
        InvalidCustomerStateException.class
    );

    return handler;
}
~~~

This example excludes validation errors from unlimited retries. Other exceptions remain subject to default classification, so review your Spring Kafka version's retryable/non-retryable exception lists and declare rules explicitly per business logic.

If using custom exception wrappers, ensure the error handler sees the exception type you classified. A generic `RuntimeException` wrapping a validation error can prevent the policy from behaving as expected if classification does not inspect causes.

## 17. Alternative strategy: finite retries followed by DLT

For many production systems, finite retries are easier to control:

1. Retry several times with exponential backoff.
2. Once retries are exhausted, publish the record to a DLT.
3. Record metadata on root cause, offset, and event ID.
4. Trigger alerts for operators or automated workflows to handle.
5. After fixing the root cause, replay records in a controlled manner.

This creates a clear termination point. It prevents a single failing record from occupying a consumer forever and lets operations triage backlogs.

Example:

~~~java
ExponentialBackOffWithMaxRetries backOff =
    new ExponentialBackOffWithMaxRetries(5);

backOff.setInitialInterval(1_000L);
backOff.setMultiplier(2.0);
backOff.setMaxInterval(30_000L);

DefaultErrorHandler handler =
    new DefaultErrorHandler(recoverer, backOff);
~~~

Finite retries do not automatically guarantee zero record loss. The recoverer must publish successfully and the original offset must advance only per the chosen policy. Monitor both DLT publish errors and the replay process.

## 18. Observing and alerting on unlimited retries

If unlimited retries are enabled, dashboards must show how long records have been retrying and whether dependencies are recovering.

Signals to monitor:

| Signal | What to detect |
|---|---|
| Retry attempts by exception and topic | Which errors are repeating heavily |
| Age of the first retry | How long a record has been held |
| Retry rate by consumer/member | Which instances generate heavy retry load |
| Backoff duration | How long consumers are waiting |
| Consumer lag by partition | Which partitions are not progressing |
| Oldest record age | Actual business delay |
| Dependency availability/latency | Whether transient causes have recovered |
| Rebalance count | Whether blocking retries cause consumers to miss poll cadence |
| Retry topic lag | Where retry backlogs are accumulating |
| DLT publish/recovery failures | Whether records are stuck in the recovery step |

Logs should include topic, partition, offset, event ID, exception class, root cause, retry count or retry timestamp, and correlation ID. Do not log full sensitive payloads.

Alert on record age and retry duration, not solely on attempt counts. With unlimited retries, counts can be large while a record waiting 30 seconds may be acceptable; conversely, a record waiting many hours may already breach SLOs even if retry counts are low.

## 19. Runbook for handling indefinitely retrying records

When a record is detected retrying over an extended period:

### Step 1: Identify the record and blast radius

- What are the topic, partition, offset, and event ID?
- Which consumer group is processing it?
- Is the record stuck in blocking retry or sitting in a retry topic?
- How are partition lag and record age growing?

### Step 2: Identify the root cause

- Is the error transient or permanent?
- Is the dependency recovering?
- Is there an invalid schema, ACL, configuration, or business state?
- Is a single record failing or are all consumers failing?

### Step 3: Protect the dependency

- Check retry rate and request rate.
- Reduce concurrency or use a circuit breaker/pause if the dependency is overloaded.
- Set appropriate timeouts and backoff.
- Avoid mass-restarting consumers before the root cause is addressed.

### Step 4: Choose a recovery path

- If transient: restore the dependency and let retries proceed.
- If permanent: stop retrying that exception type, route to DLT, or fix the data.
- If side effect outcome is unclear: query by event ID/idempotency key before replaying.
- If ordering matters: evaluate the impact of skipping or moving the record to a retry topic.

### Step 5: Verify progress

Confirm the record succeeds, committed offsets advance, lag drops, retry rate falls, and the dependency stabilizes. Document the root cause and refine classification so the same error is not retried indefinitely again.

## 20. Common design mistakes

| Practice | Consequence | Adjustment |
|---|---|---|
| Unlimited retries for every exception | Permanent exceptions stall partitions indefinitely | Classify exceptions and exclude permanent errors from retries |
| Using zero delay | Retry storms, CPU and dependency overload | Use non-zero backoff and rate/load limits |
| Assuming UNLIMITED_ATTEMPTS guarantees eventual success | Records can fail forever if cause does not change | Monitor, classify, and establish intervention procedures |
| Omitting timeouts on dependencies | A single retry can hang indefinitely | Set finite timeouts on every call |
| Ignoring max.poll.interval.ms | Blocking retries can trigger rebalances | Calculate poll budget or use retry topics |
| Assuming unlimited retries auto-route to DLT | No attempt threshold exists to trigger count-based recovery | Route permanent exceptions separately and define recovery conditions |
| Using retry topics with overly short retention | Records may expire before retrying | Set retention based on outage windows and SLOs |
| Non-idempotent side effects | Replays duplicate business actions | Use event IDs/idempotency keys and inbox patterns |
| No alerts on aging records | Backlogs go unnoticed | Alert on oldest record age and retry duration |
| Restarting consumers repeatedly | Increases rebalances and duplicates | Fix root cause before restarting |

## 21. Checklist before enabling UNLIMITED_ATTEMPTS

Before deploying, answer:

1. Which exception types does unlimited retry apply to?
2. Are permanent exceptions excluded from retries and routed to recovery?
3. Does `BackOff` have finite, reasonable wait intervals that avoid retry storms?
4. Does every database/HTTP call have a timeout?
5. Can blocking retries exceed `max.poll.interval.ms`?
6. If using retry topics, is retention long enough for outage windows?
7. Will partition ordering be altered if switching to non-blocking retry?
8. Are side effects idempotent when the same record is processed multiple times?
9. Are dashboards in place for retry rate, oldest record age, lag, rebalances, and dependency health?
10. Who receives alerts and what is the procedure to stop, fix, or replay records?
11. Is there a way to check whether a record already succeeded before replaying an operation with an uncertain outcome?
12. Can unlimited retries be replaced with finite retries and a DLT while still meeting business requirements?

`UNLIMITED_ATTEMPTS` fits certain transient errors that the business cannot afford to skip, but it removes the attempt-based termination point. When using it, bound load with backoff, classify permanent exceptions, protect side effects with idempotency, and monitor record age. Without those safeguards, unlimited retries can turn an isolated failure into a stalled partition, prolonged consumer lag, and cascading failures across other dependencies.
