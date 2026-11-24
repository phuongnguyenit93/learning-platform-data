# BackOffHandler and Long Wait Times in Spring Kafka

In Spring Kafka, DefaultErrorHandler uses a BackOff policy to decide **when** to retry a failed record and a BackOffHandler to decide **how** the container waits until the retry time. These two components serve different roles. BackOff generates the sequence of wait intervals; BackOffHandler executes those waits within the listener container lifecycle.

This distinction matters when wait intervals are long. If a consumer thread merely sleeps while waiting, it may go too long without calling poll and exceed max.poll.interval.ms. The consumer group can then evict the consumer and redistribute its partitions. ContainerPausingBackOffHandler addresses this by pausing the container during the wait while allowing the container to keep polling to preserve consumer liveness.

For very long waits or retries spanning many minutes or hours, retry topics or a durable retry-state store are usually more appropriate than holding a partition in blocking retry.

## 1. BackOff Policy and BackOffHandler Are Two Separate Things

A failed record processing attempt can pass through these steps:

~~~text
Kafka listener receives record
          |
          v
Listener throws exception
          |
          v
DefaultErrorHandler
          |
          +--> BackOff policy
          |       |
          |       +--> returns next wait interval
          |       |
          |       +--> returns STOP when retries exhausted
          |
          v
BackOffHandler
          |
          +--> executes the wait interval
          |
          v
Container retries / redelivers record
          |
          +--> succeeds
          |
          +--> fails again
          |
          +--> retries exhausted: recoverer / DLT
~~~

**BackOff policy** determines the sequence of wait times. For example:

- Wait 1 second between retries.
- Wait 1, 2, 4, 8 seconds under exponential backoff.
- Wait up to 30 seconds as intervals grow.
- Stop after a configured number of retries.

**BackOffHandler** receives the interval returned by the policy and performs the wait in a manner suited to the listener container. The handler itself does not decide which errors are retryable, how many retries occur, or which records go to the DLT.

**DefaultErrorHandler** coordinates both components alongside exception handling, seek/redelivery, and the recoverer. Consequently, changing only the BackOff policy does not necessarily solve the issue of a consumer thread being held in a long sleep. To change how the container waits, configure an appropriate BackOffHandler.

## 2. BackOff Policies Generate the Wait Sequence

Spring Kafka uses Spring Framework's BackOff abstraction. Each time a listener fails, BackOffExecution supplies the next wait interval via nextBackOff(). When no retries remain, execution returns BackOffExecution.STOP.

Example with FixedBackOff:

~~~java
BackOff backOff = new FixedBackOff(1_000L, 3L);
~~~

With a 1,000 ms interval and 3 retries, the listener is called immediately on the first attempt; if it fails, the error handler allows up to three retries after the initial attempt, spaced roughly one second apart. Once the retry chain finishes, the recoverer is invoked if configured.

Interpretation table:

| Listener Invocation | Outcome | Action |
|---:|---|---|
| 1 | Failed | Wait 1 second |
| 2 | Failed | Wait 1 second |
| 3 | Failed | Wait 1 second |
| 4 | Failed | Retries exhausted, invoke recoverer |

Counts in BackOff usually represent retries after the initial processing attempt. When designing policies, explicitly document total possible listener invocations to avoid confusing attempts with retries.

### FixedBackOff

FixedBackOff fits when dependencies usually recover within a relatively predictable timeframe.

~~~java
BackOff backOff = new FixedBackOff(2_000L, 4L);
~~~

This example waits 2 seconds between retries and allows up to four retries after the initial attempt. It is predictable, though if multiple consumers hit an outage together, they may retry simultaneously on the same schedule.

### Exponential Backoff

Exponential backoff increases the wait interval after each failure. This eases pressure on a dependency during extended outages.

~~~java
ExponentialBackOffWithMaxRetries backOff =
        new ExponentialBackOffWithMaxRetries(6);

backOff.setInitialInterval(1_000L);
backOff.setMultiplier(2.0);
backOff.setMaxInterval(30_000L);
~~~

With a 1-second initial interval, multiplier of 2, and max interval of 30 seconds, wait intervals grow until hitting the cap. The constructor in the example sets the maximum retry count; verify the API against your application's Spring Framework/Spring Kafka version.

Exponential backoff generally fits network errors, rate limits, or recovering dependencies. If multiple instances share the same schedule, jitter may be needed at an appropriate retry layer to prevent all of them from calling again at the same instant.

### When BackOff Returns STOP

When BackOffExecution returns STOP, DefaultErrorHandler ends the retry sequence for the current record and transitions to recovery per configuration. If a ConsumerRecordRecoverer is configured, the record can be sent to a DLT or handled by a custom recoverer.

Do not use infinite retries for deterministic bad data. For an undeserializable record or a validation failure, waiting longer will not alter the payload. Classify such exceptions as non-retryable for early recovery.

## 3. How Does BackOffHandler Execute Wait Times?

Spring Kafka provides BackOffHandler to decouple how waiting occurs from the policy calculating intervals. Common handlers:

- **DefaultBackOffHandler:** waits in a blocking manner on the container's processing thread.
- **ContainerPausingBackOffHandler:** pauses the listener container during the wait interval, allowing the container to continue polling rather than keeping the consumer thread in one long sleep.

Choosing a handler does not alter the sequence of durations generated by the BackOff policy. It changes how those durations are executed.

### DefaultBackOffHandler

DefaultBackOffHandler is the simple choice for short wait intervals. During sleep, the consumer thread makes no new polls. If listeners run fast and backoffs are brief, this rarely causes trouble.

With long waits, the thread can go without polling longer than max.poll.interval.ms allows. The consumer may then be considered inactive in the group, triggering a rebalance and handing partitions to another consumer.

For example, if max.poll.interval.ms is 5 minutes yet the error handler sleeps 8 minutes, the consumer can breach the poll interval before resuming processing. Raising max.poll.interval.ms shifts this threshold, but does not solve every wait-duration issue or holding partitions for too long.

### ContainerPausingBackOffHandler

ContainerPausingBackOffHandler is designed for longer wait intervals. Rather than keeping the consumer thread asleep throughout, the handler pauses the listener container during backoff. The container continues polling in the paused state to maintain consumer group membership; new records are not dispatched to the listener while paused.

~~~text
Listener fails
      |
      v
DefaultErrorHandler
      |
      v
BackOff returns 8 minutes
      |
      v
ContainerPausingBackOffHandler
      |
      +--> pause container
      |
      +--> container keeps polling
      |       |
      |       +--> preserves consumer group membership
      |       +--> delivers no new records to listener
      |
      +--> pause interval ends
              |
              v
          resume container
              |
              v
       continue retrying failed record
~~~

This avoids leaving the consumer without polling across the entire long wait. Still, it remains a blocking retry at the partition/container level: the failing record is still pending, and subsequent records may have to wait. Pausing does not make the failed record disappear, nor does it create an independent retry queue.

## 4. Configuring ContainerPausingBackOffHandler with DefaultErrorHandler

Example configuring a record listener with a DLT recoverer and a long wait:

~~~java
@Configuration
public class KafkaErrorHandlerConfiguration {

    @Bean
    DefaultErrorHandler orderErrorHandler(
            KafkaTemplate<Object, Object> kafkaTemplate) {

        DeadLetterPublishingRecoverer recoverer =
                new DeadLetterPublishingRecoverer(kafkaTemplate);

        BackOff backOff = new FixedBackOff(
                60_000L, // 60-second wait interval
                3L       // up to 3 retries after initial attempt
        );

        BackOffHandler backOffHandler =
                new ContainerPausingBackOffHandler();

        DefaultErrorHandler handler =
                new DefaultErrorHandler(
                        recoverer,
                        backOff,
                        backOffHandler
                );

        handler.addNotRetryableExceptions(
                InvalidOrderException.class
        );

        return handler;
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
    orderListenerContainerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory,
            DefaultErrorHandler orderErrorHandler) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<
                        String, OrderCreated>();

        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(orderErrorHandler);

        return factory;
    }
}
~~~

In this example:

- The BackOff policy sets a 60-second wait and up to three retries.
- ContainerPausingBackOffHandler executes waits by pausing the container.
- DefaultErrorHandler orchestrates retries and recovery.
- InvalidOrderException is marked non-retryable so it does not wait through three retries.
- DeadLetterPublishingRecoverer routes unrecoverable records to the DLT per routing configuration.

KafkaTemplate, serializer, and factory types must match actual payloads. If the DLT can receive both deserialized objects and raw `byte[]` from deserialization errors, configure serializers capable of handling both or use a dedicated template.

The constructor accepting BackOffHandler is available in Spring Kafka versions supporting this API. Verify your dependency version before applying; if an older version lacks that constructor, upgrade or use the equivalent mechanism provided by that version.

## 5. Relationship to max.poll.interval.ms

max.poll.interval.ms is the maximum interval allowed between consecutive poll() calls for a consumer in group management. If a consumer fails to poll within this window, the coordinator may deem it dead and start a rebalance.

Distinguish three timing parameters:

| Setting | What It Controls |
|---|---|
| max.poll.interval.ms | Maximum time allowed between poll calls |
| session.timeout.ms | Time to detect consumer heartbeat loss under group mechanics |
| pollTimeout | Time the container waits inside a single poll before the loop continues |

When using DefaultBackOffHandler, sleep time plus listener execution time can push the consumer past max.poll.interval.ms if no poll occurs during the wait.

Example:

~~~text
max.poll.interval.ms = 300000 (5 minutes)
listener fails
DefaultBackOffHandler sleep = 8 minutes
consumer does not poll during sleep
      |
      v
exceeds max.poll.interval.ms
      |
      v
consumer may leave group / rebalance
~~~

ContainerPausingBackOffHandler solves this by pausing the container and letting the container loop keep polling while paused. Thus, the consumer preserves group membership while the record has not yet been redelivered to the listener.

Raising max.poll.interval.ms can be appropriate if normal listener processing genuinely takes a long time. However, never raise this value solely to hide an overly long retry wait. A consumer sitting in a long retry state still holds partitions and slows down consumer group progress.

## 6. Pausing the Container Is Not Stopping the Consumer

This is an important operational distinction.

**Pause** temporarily suspends dispatching new records to the listener while the consumer continues polling to retain group membership. Upon resume, the container resumes delivering records to the listener.

**Stop** halts the container and closes the consumer per lifecycle. The consumer leaves the group; partitions can be reassigned to other consumers.

~~~text
RUNNING
   |
   | pause()
   v
PAUSED
   |
   | polling continues, listener receives no new records
   |
   | resume()
   v
RUNNING

RUNNING
   |
   | stop()
   v
STOPPING
   |
   | consumer closes
   v
STOPPED
~~~

ContainerPausingBackOffHandler uses pause/resume to implement wait intervals. It does not stop the consumer and restart it after every retry.

Pausing at the container level can also affect multiple partitions managed by the same child consumer. Therefore, when a failing record pauses a consumer, other partitions assigned to that same consumer may slow down as well. Factor partition assignment and concurrency into blocking retry decisions.

## 7. Pause Duration May Not Be Millisecond-Exact

ContainerPausingBackOffHandler relies on the listener container's poll loop and pause/resume mechanics. Actual wait duration can drift from the number in the BackOff policy due to pollTimeout and container scheduling.

For example, if you request a 10-second pause while the container polls on a 2-second cycle, the actual resume time can shift with the poll cycle and when the container processes pause/resume commands. This is not a precision timer for business tasks requiring millisecond accuracy.

Therefore:

- Use this handler for retry delays needing long waits without requiring exact millisecond timing.
- Set pollTimeout to match latency needs and container operation.
- Observe actual pause durations under realistic load.
- Do not rely on pause duration to enforce an exact business deadline.
- If you need long retry schedules that survive restarts or require independent redelivery timing, use retry topics or persist retry schedules durably.

## 8. Blocking Retries Can Hold a Partition for a Long Time

ContainerPausingBackOffHandler keeps the consumer group alive, yet does not eliminate blocking retry's impact on partitions.

Suppose partition 0 has these records:

~~~text
P0:
  offset 100 --> event A (error, retry in 10 minutes)
  offset 101 --> event B
  offset 102 --> event C
~~~

If blocking retry holds record 100 in a waiting state, records 101 and 102 may not be processed until record 100 succeeds or is recovered. This preserves order, but increases latency for subsequent records.

In a consumer managing multiple partitions, pausing the container can affect delivery from other partitions on that same consumer. Increasing concurrency spreads partitions across more child consumers, yet does not solve a single partition being blocked by a poison pill.

Blocking retry is appropriate when:

- Wait intervals are short or moderate.
- Preserving per-partition order is required.
- Errors are likely to recover within the expected window.
- Retry counts are bounded.
- Temporarily pausing the partition during retries is acceptable.

If a record must wait many minutes or hours, evaluate retry topics instead of holding the partition idle.

## 9. Retry Topics for Long Wait Times

Spring Kafka supports non-blocking retries through @RetryableTopic. When a listener fails, the framework forwards the record to a corresponding retry topic with a configured delay. Consumers on the main topic can keep processing other records while the failing record waits for its next attempt.

Example:

~~~java
@RetryableTopic(
        attempts = "5",
        backoff = @Backoff(
                delay = 60_000,
                multiplier = 2.0,
                maxDelay = 900_000
        ),
        dltTopicSuffix = "-dlt"
)
@KafkaListener(
        topics = "orders",
        groupId = "order-service"
)
public void onOrder(OrderCreated event) {
    orderService.process(event);
}
~~~

In this example, the retry topic uses an increasing delay starting at 60 seconds, doubling, and capped at 15 minutes. Attributes like attempts and how retry topics are created must be verified against your Spring Kafka version; this configuration illustrates a non-blocking retry policy.

Comparison:

| Criterion | Blocking Retry + ContainerPausingBackOffHandler | Non-Blocking Retry Topic |
|---|---|---|
| Main consumer group | Container pauses yet keeps polling | Can continue processing other records |
| Failing partition | May be held at the retrying record | Failed record is moved to a retry topic |
| Ordering | Easier to preserve source partition order | Observed order may change |
| Wait durations | Fits moderately long delays | Fits longer delays |
| Infrastructure | Uses source topic and container | Requires retry topics and forwarding flows |
| Recovery after restart | Relies on offsets and container lifecycle | Retrying records are persisted in Kafka topics |
| Complexity | Lower | Higher; requires managing retry/DLT topology |

Non-blocking retries have limitations depending on version and listener type; in particular, check compatibility with batch listeners and container transactions. Never assume every blocking-retry configuration translates verbatim to @RetryableTopic.

Retry topics can also alter ordering. For example, event B on the main topic may be processed before event A waiting in a retry topic. If business ordering is mandatory, keep blocking retries or design sequencing/ordering at the business layer.

## 10. Choosing Backoff by Error Type

Do not apply one wait sequence to every exception.

| Error Type | Recommended Policy |
|---|---|
| Intermittent database/network glitch | Short exponential backoff, capped total time |
| HTTP 429 or rate limit | Honor Retry-After if present, backoff with jitter |
| HTTP 503 or temporarily unavailable dependency | Increasing backoff, circuit breaker if needed |
| Service maintenance for a few minutes | Container pause or retry topic depending on ordering needs |
| Dependency outage lasting hours | Retry topic or durable retry-state storage |
| Invalid payload | Do not retry the same payload; recover/DLT |
| Authorization denied | Do not retry indefinitely; alert and quarantine if needed |
| Deterministic code bug | Cap retries, preserve record for investigation |

Retryable errors must have a meaningful recovery condition. For instance, a brief database disconnect can recover, whereas an event missing orderId will not fix itself after 10 minutes.

### Exponential Backoff and Jitter

If multiple consumers retry on the same fixed schedule, they can hammer the dependency simultaneously. Jitter adds a random offset to spread retry timestamps apart.

Illustrative schedule:

~~~text
baseDelay = 1 second
multiplier = 2
maxDelay = 30 seconds

retry 1: ~1 second + jitter
retry 2: ~2 seconds + jitter
retry 3: ~4 seconds + jitter
retry 4: ~8 seconds + jitter
retry 5: ~16 seconds + jitter
retry 6+: ~30 seconds + jitter
~~~

If the BackOff implementation does not supply jitter, use a custom BackOff or pick a retry mechanism with appropriate jitter support. Avoid calling random sleeps inside the listener itself because that does not coordinate with the container pause/poll lifecycle.

## 11. Combining DefaultErrorHandler with Recovery and DLT

DefaultErrorHandler orchestrates retries and invokes the recoverer once retries are exhausted. With a DLT, DeadLetterPublishingRecoverer can send failed records to a separate topic for investigation or replay after fixing the root cause.

~~~text
orders topic
    |
    v
listener
    |
    +--> retryable exception
    |       |
    |       v
    |    BackOff policy
    |       |
    |       v
    |    BackOffHandler waits
    |       |
    |       v
    |    retry listener
    |
    +--> retries exhausted
            |
            v
      DeadLetterPublishingRecoverer
            |
            v
        orders.DLT
~~~

Define:

- Retry count and total retry duration.
- Which exceptions skip retries.
- DLT topic and partition routing.
- Serializers for original records and raw bytes.
- Behavior if DLT publishing fails.
- DLT retention and access controls.
- Data-repair and replay workflows.
- Consumer idempotency when records are replayed.

If DLT publishing fails, do not treat the source record as successfully recovered. Monitor exceptions from the recoverer and ensure the source offset does not advance as if the data were safely stored.

## 12. Using BackOffHandler with Multi-Partition Consumers and Concurrency

ConcurrentMessageListenerContainer spawns child containers, each with its own consumer. When one child consumer pauses for backoff, all partitions assigned to that child can be affected together.

Example:

~~~text
Topic orders: 6 partitions
Concurrency: 3

Child 1: P0, P1
Child 2: P2, P3
Child 3: P4, P5

P0 has a failing record and Child 1 pauses:
  P0: failing record awaiting retry
  P1: may slow down due to sharing the child container
  P2-P5: continue processing on other children
~~~

This is why concurrency and partition assignment shape the blast radius of blocking retries. If a workload uses key ordering, distribute keys and partitions thoughtfully. Never raise concurrency above partition count expecting it to solve every retry scenario.

While the container is paused, the consumer keeps polling to preserve membership without dispatching new records to the listener. Track consumer lag per partition to see which partitions are stalled and how far the impact spreads.

## 13. BackOffHandler and Shutdown/Rebalance

A long pause interval can overlap with application shutdown or a consumer group rebalance.

On shutdown:

- The container must stop accepting new work.
- A retrying record may not have finished reprocessing.
- Uncommitted offsets can cause the record to be redelivered once another instance takes over.
- DLT/recovery must have clear state if already started.
- Do not wait on retries longer than the allotted shutdown grace period.

On rebalance:

- Partitions may be revoked from the current consumer.
- The container must stop processing per lifecycle and assignment state.
- Uncommitted records may be redelivered to the new consumer.
- Idempotency must protect side effects executed prior to the commit.

ContainerPausingBackOffHandler does not guarantee a record will finish before every shutdown or rebalance. Design listeners to be recoverable and never rely on a single consumer instance holding retry state in memory.

## 14. Do Not Use Sleep Inside the Listener Instead of BackOffHandler

A common yet unsuitable pattern is calling Thread.sleep inside the listener:

~~~java
@KafkaListener(topics = "orders")
public void onOrder(OrderCreated event) throws InterruptedException {
    try {
        orderService.process(event);
    }
    catch (TemporaryDependencyException ex) {
        Thread.sleep(300_000L);
        throw ex;
    }
}
~~~

This holds the consumer thread in sleep, delays polling, and can breach max.poll.interval.ms. It also mixes retry scheduling with business logic, making testing, shutdowns, and observability hard to control.

Let the listener throw the exception and configure DefaultErrorHandler with a BackOffHandler. When long delays are needed, choose ContainerPausingBackOffHandler or retry topics as required.

## 15. Choosing Wait Times and Retry Limits

Backoff should not be chosen purely by feel. Determine:

1. How long does the dependency typically take to recover?
2. How many retries are reasonable before recovery?
3. Does total record processing time exceed business deadlines?
4. Can the partition remain stalled for that duration?
5. Does the consumer group need to keep processing subsequent records?
6. Must per-partition order be preserved?
7. Can retries recover after a restart?
8. Can the DLT safely store the record if retries expire?

Example policy for an external service error typically recovering within tens of seconds:

~~~java
ExponentialBackOffWithMaxRetries backOff =
        new ExponentialBackOffWithMaxRetries(5);

backOff.setInitialInterval(1_000L);
backOff.setMultiplier(2.0);
backOff.setMaxInterval(15_000L);

DefaultErrorHandler handler =
        new DefaultErrorHandler(
                recoverer,
                backOff,
                new ContainerPausingBackOffHandler()
        );
~~~

This example produces increasing wait intervals capped at 15 seconds with up to five retries. Actual elapsed time depends on the backoff sequence, listener duration, polling intervals, and recovery.

If total retry time can reach many minutes or hours, consider retry topics. If retries must follow a specific business schedule or coordinate with database state, persist next_attempt_at and attempt count in a durable store.

## 16. Observing Retry Duration and Container State

In production, measure both retry counts and how long containers actually spend paused.

| Signal | What to Monitor |
|---|---|
| Listener error count | Frequency of listener failures |
| Retry attempt count | Number of times records are retried |
| Backoff duration | Requested wait duration |
| Container paused duration | Actual paused duration |
| Consumer lag by partition | Partitions stalled during retries |
| Rebalance count | Rebalances occurring during retries |
| DLT publish count | Number of recovered records |
| Recovery failure count | Errors publishing to or handling the DLT |
| Listener processing latency | Processing duration before failure |
| Dependency error rate | Determines whether errors are genuinely transient |

Exact metric names depend on Spring Kafka, the Kafka client, Micrometer, and exporters. You can listen for container events such as ConsumerPausedEvent and ConsumerResumedEvent to record pause/resume state, alongside consumer lag metrics to measure partition impact.

Logs should include topic, partition, offset, key or event ID, exception class, attempt number, and next retry timestamp. Never log raw payloads if they might contain sensitive data.

## 17. Common Operational Scenarios

### Retry Delay Longer Than max.poll.interval.ms

With blocking sleep, the consumer can go too long without polling and drop out of the group. Use ContainerPausingBackOffHandler to pause the container while continuing to poll, or switch to retry topics if the source partition should not be held.

### Container Still Polls Yet Partition Does Not Advance

ContainerPausingBackOffHandler preserves polling while paused, but the failing record is still waiting to retry. If later records must keep flowing, use non-blocking retry topics and accept the ordering impact.

### Synchronized Retries Cause Load Spikes

Use exponential backoff, jitter, and circuit breakers at the dependency layer. Reduce concurrency or processing rate if the dependency is overloaded. Do not let every consumer retry right after the same fixed interval.

### Retrying an Invalid Payload Forever

Classify exceptions as non-retryable and route to DLT/quarantine. Do not use long backoffs to hide deterministic data errors.

### DLT Publish Fails

Check broker, ACLs, serializers, topic, and partition routing. Recovery is incomplete until the record is safely persisted; alert and never commit the source offset as if recovery succeeded.

### Shutdown Occurs While Container Is Paused

The container stops per lifecycle. Uncommitted records may be redelivered when another consumer takes the partition. Listeners and side effects must be idempotent to reprocess safely.

## 18. BackOffHandler Configuration Checklist

- BackOff policy has finite retries and reasonable total duration.
- FixedBackOff or exponential backoff matches the error type.
- Deterministic data exceptions are classified as non-retryable.
- BackOffHandler is chosen based on wait-interval length.
- Use DefaultBackOffHandler for short waits where blocking sleep is appropriate.
- Use ContainerPausingBackOffHandler when you need to pause the container and keep polling during waits.
- Do not call Thread.sleep directly inside listeners to roll your own retries.
- Relationship between max.poll.interval.ms, session timeout, and pollTimeout is understood.
- Impact on other partitions sharing the same child consumer when paused is accounted for.
- Retry delays do not hold partitions longer than throughput requirements allow.
- Retry topics are evaluated for long waits or when later records must proceed.
- Business ordering is evaluated when considering non-blocking retries.
- DLT recoverer and serializers support failed payloads.
- Recovery publish failures are observed and handled properly.
- Shutdowns/rebalances can occur between retries without losing side effects.
- Consumers are idempotent to tolerate redeliveries.
- Metrics/logs cover retry counts, pause durations, lag, rebalances, and DLTs.

BackOff policy answers “how long to wait and how many times to retry”; BackOffHandler answers “how does the container wait”. For long waits, ContainerPausingBackOffHandler lets the consumer keep polling while the container is paused, avoiding holding the consumer thread in a sleep exceeding the poll interval. When delays are long enough that partitions should not be held, switch to retry topics or a durable retry mechanism with its own schedule.
