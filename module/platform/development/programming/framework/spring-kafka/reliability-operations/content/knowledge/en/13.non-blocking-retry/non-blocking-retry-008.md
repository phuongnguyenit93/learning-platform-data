# Combining Blocking and Non-Blocking Retry

In Spring Kafka, **blocking retry** and **non-blocking retry** handle failures on two different cadences. Blocking retry re-attempts a record right inside the listener container's processing flow, typically with a few short wait intervals. Non-blocking retry forwards failed records to retry topics so the main topic's consumer can keep processing while failed records are retried after a longer delay.

Combining both mechanisms forms a multi-tier retry policy: **retry fast a few times for brief transient errors; if the error persists, forward to retry topics for longer waits; if it still fails or the error is non-retryable, perform recovery such as sending to a Dead Letter Topic (DLT)**. This design can reduce latency for short blips, avoid stalling the main partition during dependency disruptions, and help control backlogs. In return, it increases business execution counts, operational complexity, and the risk of altering processing order.

This lesson focuses on Spring Kafka listeners in a reliability model—specifically criteria for choosing each retry tier, configuration, impact on offsets, idempotency, record ordering, and observability.

## 1. Where Do the Two Retry Mechanisms Differ?

### 1.1. Blocking Retry

With blocking retry, the listener processes a record and throws an exception. The error handler waits according to a BackOff and redelivers the record to the listener, typically before moving on to subsequent records in the container's processing sequence.

~~~text
orders (partition 1)
    |
    v
Listener processes record A
    |
    +-- error --> short wait --> attempt A #2
                                      |
                                      +-- error --> short wait --> attempt A #3
                                                                        |
                                                                        +-- success
~~~

This is an appropriate choice when an error can resolve within hundreds of milliseconds or a few seconds: a database connection just reset, a dependency is changing leader, or an API call hit a brief timeout.

The upside is not having to publish records to another topic for every minor hiccup, and it is easier to preserve per-partition ordering. The downside is that the consumer thread and partition are affected during retries. If processing or backoff takes too long, throughput drops, lag can climb, and poll cycles must be managed carefully.

### 1.2. Non-Blocking Retry

With non-blocking retry, when processing at one tier fails, the framework can publish the record to a retry topic. A separate retry-topic consumer processes the record after the configured delay. The main consumer keeps reading other records.

~~~text
orders ----> main listener
                 |
                 +-- error --> orders-retry-2000
                                  |
                                wait 2s
                                  |
                                  v
                              retry listener
                                  |
                                  +-- error --> orders-retry-8000
                                                    |
                                                  wait 8s
                                                    |
                                                    v
                                                retry listener
                                                    |
                                                    +-- retries exhausted --> orders-dlt
~~~

Non-blocking retry fits when a dependency typically needs several seconds or minutes to recover. It prevents a single failed record from holding the main topic consumer for the entire wait duration. However, a record forwarded to a retry topic may finish **after** newer records sharing the same key. Therefore, never assume this mechanism preserves the original partition's ordering.

### 1.3. Comparison Table

| Criterion | Blocking retry | Non-blocking retry |
|---|---|---|
| Where waiting occurs | Processing flow/container per BackOff | Retry topic and retry-tier consumer |
| Suitable delay | Typically short | Can be longer |
| Impact on main consumer | May delay processing of subsequent records | Main consumer can continue |
| Additional topics | Not required | Requires retry topics, usually DLT |
| Original partition ordering | Easier to control | Can change |
| Operational cost | Fewer topics | Extra topics, groups, lag, ACLs, and retention |
| Recovery | Error handler/recoverer | Retry topics, DLT, and recovery policy |
| Duplicate risk | Exists when listener is re-invoked | Exists across both retries and cross-tier publish/commit |

## 2. Why Combine Both?

A system using **only blocking retry** can stall the consumer for a very long time if a downstream outage drags on. Conversely, if every error goes straight to a retry topic, even a 100 ms connection blip incurs extra publishing, logging, polling, retry-topic overhead, and unnecessary latency.

Combining two tiers aligns with real-world recovery-time distributions:

1. Initial error: listener attempts processing.
2. Brief transient error: retry a few times locally with short backoff.
3. Still failing: publish record to a retry topic with a longer delay.
4. On each retry topic, the framework can reapply configured blocking retries for selected exceptions.
5. After exhausting non-blocking retries or hitting a fatal error, send to DLT/recoverer per configuration.

This pattern is often called **hybrid retry**. Blocking retry handles brief blips; non-blocking retry absorbs prolonged outages and gives dependencies time to recover.

Do not adopt hybrid retry merely because both APIs exist. If the business requires strict ordering, uses listener container transactions, or cannot tolerate multi-tier latency, evaluate those limits before choosing it.

## 3. Overall Flow

Suppose a consumer processes OrderCreated events and calls an Inventory API. The application allows two blocking retries with a 300 ms delay and has two retry-topic stages with longer delays.

~~~text
orders
  |
  v
Listener A (initial)
  |
  +-- transient error --> wait 300ms --> local retry 1
                                             |
                                             +-- error --> wait 300ms --> local retry 2
                                                                       |
                                                                       +-- still failing
                                                                               |
                                                                               v
                                                                       Publish retry topic
                                                                               |
                                                                               v
                                                                    orders-retry (long delay)
                                                                               |
                                                                               v
                                                                    Listener retry stage
                                                                               |
                                                             local retries if configured
                                                                               |
                                                                               +-- success
                                                                               |
                                                                               +-- still failing
                                                                                       |
                                                                                       v
                                                                              Next retry stage
                                                                                       |
                                                                               attempts exhausted
                                                                                       |
                                                                                       v
                                                                                   orders-dlt
~~~

Exact milestones depend on retry topic count, how the framework reuses topics, classification, attempt counts, BackOff, and Spring Kafka version. The diagram illustrates decision flow; it does not promise there will be exactly two retry topics or that each topic always receives only one delivery.

**Key point:** transitioning from blocking to non-blocking is a step that publishes a new record to a retry topic. Afterward, the retry topic's consumer processes it on its own consumption flow. This is not a long sleep on the main consumer thread.

## 4. Configuring Spring Kafka in the Hybrid Model

Spring Kafka provides retry-topic integration and supports configuring blocking retries alongside non-blocking retries. A typical implementation in supported versions extends **RetryTopicConfigurationSupport** to declare which exceptions receive blocking retries, then uses **@RetryableTopic** on the listener to define non-blocking retry tiers.

Illustrative example:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.annotation.EnableKafka;
import org.springframework.kafka.retrytopic.RetryTopicConfigurationSupport;
import org.springframework.kafka.retrytopic.RetryTopicConfigurationSupport.BlockingRetriesConfigurer;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
@EnableKafka
public class KafkaRetryConfiguration extends RetryTopicConfigurationSupport {

    @Override
    protected void configureBlockingRetries(
            BlockingRetriesConfigurer blockingRetries) {

        blockingRetries
            .retryOn(InventoryTemporarilyUnavailableException.class)
            .backOff(new FixedBackOff(300L, 2L));
    }
}
~~~

The example specifies that **InventoryTemporarilyUnavailableException** is retried at the blocking tier with two additional retries, each waiting 300 ms. Other exceptions are handled according to their classifier and policy.

Next, declare non-blocking retry on the listener:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.annotation.RetryableTopic;
import org.springframework.retry.annotation.Backoff;

@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(
        delay = 2_000,
        multiplier = 2.0,
        maxDelay = 10_000
    ),
    exclude = {
        InvalidOrderEventException.class,
        UnsupportedEventVersionException.class
    }
)
@KafkaListener(
    topics = "orders.events",
    groupId = "inventory-service"
)
public void onOrderEvent(OrderEvent event) {
    inventoryService.reserve(event);
}
~~~

Here, the annotation describes deliveries at the non-blocking tier. In many Spring Kafka versions, @RetryableTopic's **attempts** counts total non-blocking deliveries, including the initial processing attempt; verify exact semantics for your running version. Blocking retries occur inside each of those deliveries and can make total listener invocations exceed attempts.

When configuring retry topics by extending RetryTopicConfigurationSupport, avoid simultaneously enabling another retry-topic configuration mechanism that creates duplicate infrastructure—for example, using **@EnableKafkaRetryTopic** alongside a subclassed config class when your version's docs require choosing one. Inspect your application's actual retry-topic bean configuration.

Specific API names, packages, and combinability depend on the Spring Kafka version. The example shows the required structure; application code still needs domain exceptions, services, KafkaTemplate, and appropriate topic/serializer configs.

## 5. Actual Attempts Can Exceed Expectations

A common configuration mistake is treating @RetryableTopic's attempts as the total number of times the listener can be invoked. When combined with blocking retry, each record delivery from the main topic or a retry topic can trigger additional local attempts.

Hypothetical example:

- Non-blocking policy has 4 deliveries: 1 on the main topic and subsequent ones on retry topics.
- Each delivery allows up to 2 extra blocking retries for exceptions in the configured group.
- Every attempt fails and the same exception keeps being classified as retryable.

Total listener invocations in this ideal model can reach:

~~~text
total_listener_calls
    = number_of_non_blocking_deliveries
      × (1 + blocking_retries_per_delivery)

    = 4 × (1 + 2)
    = 12 times
~~~

This is a **configuration-based estimate**, not a hard ceiling for all situations. Consumer restarts, rebalances, commit failures, retry-topic publish failures, or other redelivery mechanisms can cause a record to be seen even more times. Classification can also restrict blocking retries to certain attempts or exception types.

If the listener calls HTTP APIs or updates a database on each attempt, side effects may execute far more times than expected. Calculate your retry budget using **total actual executions**, across all tiers.

## 6. Classification: Which Errors Retry Locally vs. Move Tiers?

Hybrid retry works well when error classification mirrors recovery times and root causes.

| Case | Short blocking retry | Non-blocking retry | Recovery |
|---|---|---|---|
| Database just reset connection | Suitable | Can escalate tiers if still failing | DLT or alert after policy exhaustion |
| HTTP 503 during deploy | Can try a few times | Suitable if outage persists | DLT/workflow after deadline |
| HTTP 429 with large Retry-After | Little or unnecessary | Suitable if delayed per server | Review quota when overdue |
| JSON fails deserialization | Usually no | No if payload is permanently invalid | Early DLT and fix schema/payload |
| Business rule rejects data | Usually no | Only if state can change | DLT or rejection workflow |
| Wrong ACL/credentials | Pointless when conditions do not change | Should not loop endlessly | Fix security/configuration |
| HTTP request with unknown outcome | Must check idempotency | Retry only when safe | Reconcile state |

Exceptions can be grouped into three buckets:

**Group A — fleeting errors:** a few blocking retries usually suffice. Example: database blip lasting hundreds of milliseconds.

**Group B — slow-recovery errors:** retry locally very few times or skip blocking and route to retry topics. Example: service under maintenance or throttled.

**Group C — non-retryable errors:** route straight to DLT/recoverer or handle separately. Example: invalid payload that cannot self-heal.

Do not classify solely by exception message text. Use exception classes, root causes, status codes, and dependency contracts. A TimeoutException can be transient, or it can stem from a misconfigured endpoint that will never recover on its own.

## 7. How Does Blocking Retry Use DefaultErrorHandler?

For non-transactional listeners, **DefaultErrorHandler** is the core mechanism for blocking retries and recovery. In a system with retry-topic support enabled, the framework creates/configures the components needed to transition records from blocking retries to non-blocking destinations.

When configuring hybrid mode via **RetryTopicConfigurationSupport.configureBlockingRetries**, the framework knows which exceptions to retry immediately and which BackOff to use. Once blocking retries exhaust or an exception falls outside the blocking set, the retry-topic flow can publish according to the non-blocking policy.

Do not assume that merely defining a global DefaultErrorHandler bean with FixedBackOff will automatically forward records to retry topics. Publishing to retry topics requires the recoverer/destination routing configured by retry-topic infrastructure. Overriding the handler improperly can leave the app only retrying locally and logging, stopping, or recovering to the wrong destination.

If a project has multiple listener container factories, clearly identify which factory applies retry-topic configuration and blocking policy. Check which container factory each listener uses, because an error handler set on factory A does not necessarily affect a listener using factory B.

## 8. BackOffs of the Two Tiers Should Differ

The blocking tier usually has short waits; the non-blocking tier usually waits longer. Example:

| Tier | Example | Goal |
|---|---|---|
| Blocking retry 1 | 200 ms | Recover from ultra-brief blips |
| Blocking retry 2 | 400 ms | Avoid immediately switching topics |
| Retry topic 1 | 3 seconds | Wait for dependency stabilization |
| Retry topic 2 | 15 seconds | Reduce pressure during longer outages |
| Retry topic 3 | 60 seconds | Allow recovery before final recovery |
| DLT | After policy exhaustion | Store failure for separate handling |

This is an illustrative schedule, not a framework default. Actual backoffs also depend on retry count, multiplier, interval caps, poll latency, and retry consumer load.

A bad configuration would wait 30 seconds per blocking attempt and then only 1 second in non-blocking retry: it stalls the main consumer for a long time only to issue tightly spaced topic hops. Design from a single unified time budget.

### 8.1. Estimating Time to Recovery

A simple estimate:

~~~text
T_total
  ≈ Σ(processing time of each listener invocation)
    + Σ(blocking_backoff per delivery)
    + Σ(non_blocking_delay between retry topics)
    + T_publish_and_poll_overhead
~~~

Suppose there are 3 deliveries, each allowing up to 3 listener calls, each potentially waiting on a 2-second HTTP timeout; blocking waits 200 ms and 400 ms per delivery; non-blocking delays are 5 seconds and 20 seconds.

~~~text
T_processing_max  = 3 deliveries × 3 calls × 2s = 18s
T_blocking_wait   = 3 deliveries × (0.2s + 0.4s) = 1.8s
T_retry_topics    = 5s + 20s = 25s
T_total_estimated ≈ 44.8s + overhead
~~~

That is the duration of a continuous retry chain when every attempt times out. With rebalances, outages, or retry-topic backlogs, actual time can be significantly longer.

## 9. max.poll.interval.ms and Blocking Wait Duration

A Kafka consumer must keep polling within **max.poll.interval.ms**. Blocking retries and listener execution time affect the ability to maintain poll cadence. If a single call or backoff sequence keeps the consumer from polling long enough, the group can rebalance and reassign partitions.

Spring Kafka provides backoff-handling mechanisms, including ways for the container to keep polling during waits in certain configurations. For instance, **ContainerPausingBackOffHandler** can support longer waits by pausing the container instead of blocking the thread in a way that exceeds the poll interval. Exact behavior depends on version and error handler setup.

Operational rules:

- Set bounded timeouts on database/HTTP dependencies.
- Keep blocking retries short and bounded.
- Measure total poll-processing duration, including retries and commits.
- Offload long-wait failures to retry topics.
- Monitor rebalances, poll intervals, and commit latency.
- Do not raise max.poll.interval.ms unboundedly to mask a hung task.

Non-blocking retry frees the main consumer sooner, yet retry consumers also have their own max.poll.interval.ms. If blocking policies are reapplied on each retry topic, each retry consumer must still maintain its poll cadence.

## 10. Offset Commit When Forwarding Records to Retry Topics

This is the most critical part of reliability. When the main listener fails and the framework moves a record to a retry topic, two outcomes must be coordinated:

1. The record must be published to the retry topic for later processing.
2. The offset on the original topic must be acknowledged per recovery policy so the main consumer advances.

~~~text
Original topic: orders partition 0 offset 100
                  |
                  v
               Listener
                  |
                  +-- error, blocking retries exhausted
                              |
                              v
                     Publish orders-retry
                              |
                         succeeded?
                         /       \
                       Yes       No
                       |          |
                       v          v
                Recovery       Handle publish error,
                succeeds;      avoid skipping record
                source offset  before retry copy
                advances       is safely persisted
~~~

Spring Kafka's retry-topic infrastructure coordinates publishing to retry topics and recovering the source record. However, **a Kafka publish and a regular consumer offset commit are not automatically a single atomic transaction**.

Failure window example: publishing to the retry topic succeeds, yet the app stops before committing the source topic offset. After restart, the original record may be redelivered and published to the retry topic a second time. Thus, even when the framework handles errors properly, the application must tolerate duplicates under actual delivery semantics.

If publishing to the retry topic fails, let error handling follow the framework's recovery failure behavior; never force-commit the source offset just to make lag drop. Know your configured send verification and publish-failure handling mechanics.

## 11. Idempotency Is a Mandatory Business Requirement

Hybrid retry can invoke the listener multiple times on the same or different topics. One attempt may have written to the database or called HTTP successfully before an exception happened prior to offset commit or result recording. On retry, side effects can repeat.

Example of a listener receiving PaymentRequested:

~~~text
Receive PaymentRequested(eventId=evt-417)
      |
      v
Call Payment API: succeeds
      |
      v
App times out while saving status
      |
      v
Record retried locally or via retry topic
      |
      v
Calls Payment API a second time without idempotency
~~~

Design direction:

- Every event has a stable **event ID** preserved across all retry tiers.
- For databases, use a unique constraint/inbox table to record processed events.
- Write the processed status and business changes in the **same database transaction**.
- For HTTP APIs supporting idempotency keys, send the same key on every retry.
- For operations with ambiguous outcomes, reconcile state before re-issuing.

Simple table example:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(128) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Within one database transaction, the app inserts the event ID under the unique constraint and updates business state. If the ID already exists, the handler skips repeating side effects. A separate SELECT followed by INSERT is insufficient to prevent race conditions.

Kafka's idempotent producer protects certain protocol-level producer retries; it does not treat two independent business publishes as one event. Therefore, idempotency is required at the business boundary.

## 12. Record Ordering Can Change

Kafka guarantees per-partition order in the original log, but moving records to retry topics changes the consumption stream. Example:

~~~text
orders (same key order-7):
    Created(v1) ---> Paid(v2) ---> Cancelled(v3)
          |
          +-- failed, moved to orders-retry

orders listener continues:
    Paid(v2) ---> Cancelled(v3)

orders-retry listener processes Created(v1) later
~~~

If business logic requires Created to be applied before Paid, state can become corrupted. Blocking retry holds records in the main stream longer and thus preserves processing order better; non-blocking retry prioritizes main-topic progress and accepts potential out-of-order execution.

Risk mitigation strategies:

- Use aggregate versions or sequence numbers and reject out-of-order updates.
- Design handlers to be idempotent and capable of handling late-arriving events when business rules permit.
- Keep bounded blocking retries for strictly ordered flows, escalating prolonged errors to intervention workflows rather than letting newer records overtake.
- Separate event types with different ordering requirements.
- For strict workflows, consider a state machine/saga or dedicated per-key sequential processing service.

Never promote non-blocking retry as simultaneously preserving both throughput and ordering for every business flow; those two properties can conflict when records fail.

## 13. DLT and the End of the Retry Process

When non-blocking attempts exhaust, the framework can route the record to the DLT. For permanent errors, you can skip retry tiers and send straight to the DLT via classification.

A DLT record should carry enough info for later handling:

- Original topic, partition, and offset.
- Event ID/business key, schema version.
- Exception class, root cause, and sanitized message.
- Failure timestamp, delivery count, and retry metadata if present.
- Source group/correlation ID for trace lookup.

Spring Kafka supports **@DltHandler** to handle the DLT in the retry-topic pattern:

~~~java
@DltHandler
public void handleDlt(OrderEvent event) {
    log.error("Event routed to DLT: id={}", event.eventId());
    // Persist investigation state, alert, or forward to error-handling system.
}
~~~

The DLT handler method must reside in the bean/listener inspected by retry-topic infrastructure and have matching serializers/deserializers. Merely logging DLT entries without dashboards and a reprocessing workflow will cause failures to pile up.

Distinguish between:

- **Recovery succeeded:** record was moved to the DLT or handled per policy.
- **Business succeeded:** side effects completed.

A record in the DLT is typically considered complete with respect to retry routing, but not yet complete with respect to business logic. Operations must have a way to fix and replay it if the data still has value.

## 14. When Forwarding to DLT Fails

The DLT is also a Kafka topic and can encounter authorization errors, serialization errors, broker outages, or timeouts. If publishing to the DLT fails while the app still commits the source offset, the record risks slipping out of the recovery workflow.

Policy must specify:

1. Does the recoverer verify publish success as required?
2. If publishing fails, is the record redelivered or recovery retried?
3. Can the source offset be committed before safe recovery occurs?
4. Is there a dedicated alert for DLT publish failures?
5. Can original records be located and replayed from Kafka if needed?

Defaults for checking send results, committing recovered offsets, and error-handler recovery behavior vary by version and configuration. Rely on the actual Spring Kafka contract rather than assuming merely configuring a DLT guarantees zero loss.

## 15. Limitations: Batch Listeners and Kafka Transactions

Non-blocking retry topics have important limitations in Spring Kafka. By design and in common versions, **non-blocking retries do not support batch listeners and are not combined with container transactions** under standard retry-topic infrastructure usage.

With batch listeners, splitting individual failed records out to retry topics has different semantics than record listeners. If an app uses batch listeners, check your Spring Kafka version's limits or switch to a record listener model to use @RetryableTopic.

With Kafka transactions managed by the listener container, input offsets and Kafka outputs can be committed/aborted together in one transaction. Non-blocking retry via forwarding records to retry topics is a different recovery path and cannot be blindly paired with container transactions to achieve the same atomic guarantees.

If transactional consume-transform-produce is required:

- Use a transaction manager and matching rollback/retry mechanisms, such as DefaultAfterRollbackProcessor depending on version.
- Distinguish retrying records inside a transaction from publishing to a retry topic outside a transaction.
- If coordinating a database and Kafka, consider transactional outbox/inbox or a dedicated workflow.
- Do not attach @RetryableTopic to a transactional listener assuming EOS remains intact.

Verify limits and APIs against your exact library version, as utilities and supported modes can evolve over time.

## 16. Parameters to Configure Together

| Parameter/mechanism | Meaning | Notes when combining |
|---|---|---|
| Blocking retry count | Immediate retries inside listener/container | Multiplied by retry-topic deliveries, can make total executions large |
| Blocking BackOff | Wait between local retries | Keep short, counts against poll budget |
| @RetryableTopic attempts | Attempt threshold at non-blocking tier | Verify whether initial attempt is included per version |
| Non-blocking delay/backoff | Wait between retry deliveries | Does not guarantee millisecond-exact execution timing |
| Exception classification | Decides retry vs. recovery | Separate transient vs. permanent; may differ per tier |
| max.poll.interval.ms | Maximum interval between polls | Affected by processing and blocking retries |
| AckMode | When container records offsets | Must align with recovery policy |
| Retry topic retention | How long Kafka retains retry records | Must exceed expected wait/outage duration |
| DLT retention | How long failed records stay for investigation | Needs a replay procedure |
| Concurrency | Parallel consumers/containers | Can increase load on dependencies when retrying en masse |
| Idempotency key | Identifies one business action across all runs | Must stay unchanged across tiers |

Choose settings based on SLOs: maximum time before business completion or recovery, transient error rates, and dependency load capacity.

## 17. Retry Topics, Partitions, and Consumer Groups

Spring Kafka's retry-topic infrastructure typically creates dedicated containers for retry topics and DLT, deriving topic/group names from configuration. Retry topics must be created properly with matching partitions, serializers, ACLs, replication factors, and retention.

Checks to perform:

- Main consumers and retry consumers may use related group IDs, yet must not be confused as sharing the same offset commits.
- Each retry topic has its own offset log; committed offsets on the main topic are not offsets on retry topics.
- A record copy forwarded to a retry topic gets a new topic/partition/offset, even while the business event ID stays the same.
- Original partition and per-key ordering are not automatically guaranteed across retry topics.
- When deploying multiple app versions, changing naming/attempt rules can leave old and new retry topics active; check backlogs before deleting topics.

Even if the framework auto-creates retry topics in dev, production often requires IaC provisioning to control partitions, retention, replication, and ACLs. Avoid relying on auto-create when production clusters restrict topic creation permissions.

## 18. Backpressure During Widespread Failures

Suppose the Inventory API is down for 10 minutes while the orders topic keeps receiving thousands of records per second. Short blocking retries fail and every record moves to retry topics. Now the main consumer can keep advancing, yet retry topics accumulate backlog rapidly.

This is load shifting: the main consumer escapes waiting, while the retry system must store and process those records once the dependency recovers.

Protective strategies:

- Monitor publish rate into retry topics vs. drain rate out.
- Cap concurrency of retry consumers to prevent a retry storm when the API returns.
- Use exponential backoff and consider jitter at the appropriate tier.
- Use a circuit breaker or temporarily throttle ingress if the dependency cannot absorb more load.
- Size retry topic retention for the outage window.
- Alert on record age, not just total lag.
- Plan backlog catch-up once the dependency recovers.

If retry consumers process 1,000 records/second while backlog grows at 2,000 records/second during an outage, backlog keeps climbing. After recovery, processing rate must exceed ingress rate to drain backlog; raising concurrency only helps if downstream still has capacity.

## 19. Observing Both Retry Tiers

Looking only at main-topic consumer lag can make the system look healthy even while many records have been shunted to retry topics. Dashboards must therefore separate main-topic progress from the entire business processing pipeline.

| Signal | Question to answer |
|---|---|
| Blocking retry attempts by exception | Are short errors self-healing? |
| Blocking retry success rate | How many records succeed before switching topics? |
| Retry topic publish rate | How many records are leaving the main topic to wait? |
| Retry topic lag | Which tier holds retry backlog? |
| Oldest retry record age | How long have records been delayed? |
| Non-blocking attempts/exhausted | How many records are heading to the DLT? |
| DLT publish rate and lag | How many business items remain uncompleted? |
| Consumer rebalances | Are blocking retries breaking poll cadence? |
| Dependency latency/error rate | Has the root cause recovered yet? |
| Publish/recovery failures | Are retry-topic or DLT forwards failing? |

Logs and traces should carry the business event ID across every tier. Spring Kafka's retry headers may contain attempt info and original topic/exception details; header names depend on version. Never use only the new topic offset to identify a business item because each publish to another topic gets a new offset.

Avoid high cardinality by keeping event IDs out of metric labels; put event IDs in logs/traces and keep metrics aggregated by topic, exception, and stage.

## 20. Common Investigation Scenarios

### 20.1. Blocking Retry Succeeds but Latency Climbs

If most records recover after 1–2 local retries, the system may not need many retry topics. However, if large blocking backoffs raise p99 processing latency and lag, reduce blocking attempts or optimize the dependency.

Inspect record processing times, retry attempts, and per-partition lag. Tune initial intervals and attempt counts using the actual recovery-time distribution.

### 20.2. Main Topic Has No Lag Yet Business Processing Is Slow

Records may have been forwarded to retry topics with source offsets committed. Dashboards watching only the main group miss backlogs on retry topics.

Aggregate processing state by event ID, track retry topic lag, and watch oldest event age. Business KPIs should measure when events finish business processing, not merely when they leave the main topic.

### 20.3. Same Event Appears Twice in a Retry Topic

Publishing the retry may have succeeded while committing the source offset failed, or a consumer rebalance caused the original record to be re-read. Do not assume the framework deduplicates across topics and offset commits.

Trace the event ID, original offset, publishes, and side-effect state. Verify idempotency and how publish results/commit failures are handled.

### 20.4. Some Records Never Reach the DLT

Check attempts, classification, whether the retry policy is still running, retry topic retention, publish errors, and the DLT handler. An unbounded retry policy or an exception continuously classified as retryable can prevent records from ever reaching the limit for DLT routing.

### 20.5. Errors Surge After a Schema Change

If all retries fail due to deserialization or validation, this is usually a data/contract error that backoff cannot fix. Use ErrorHandlingDeserializer when poll-time deserialization errors must pass to the container, classify exceptions as non-retryable, and send records to the DLT with proper metadata.

## 21. Runbook for Rolling Out Hybrid Retry

A practical rollout sequence:

1. **Classify errors:** identify short transient, long transient, and permanent errors.
2. **Design retry budget:** set blocking retry count, delays, and non-blocking attempt limits; compute worst-case total duration.
3. **Evaluate ordering:** identify which event types/keys cannot tolerate out-of-order processing.
4. **Check transactions:** verify listeners use non-transactional record containers if using the standard retry-topic pattern.
5. **Configure framework:** declare blocking retries in RetryTopicConfigurationSupport and non-blocking policy via @RetryableTopic or matching builder.
6. **Prepare topics:** create retry topics/DLT with appropriate partitions, retention, replication, ACLs, and serializers.
7. **Protect side effects:** use stable event IDs and database/API idempotency.
8. **Set up observability:** measure attempts, lag, oldest age, publish failures, and DLT backlog.
9. **Test failure paths:** recovery via local retry; escalation to retry topics; exhausted attempts; DLT publish failure; restarts/rebalances.
10. **Gradual rollout:** monitor retry topic volume, throughput, and p95/p99 end-to-end latency.

Not every topic needs one shared retry policy. Flows needing strict ordering can use bounded blocking retry, while flows tolerating reordering can leverage non-blocking retry.

## 22. Common Design Mistakes

| Practice | Consequence | Adjustment |
|---|---|---|
| Treating @RetryableTopic attempts as total listener calls | Underestimates side effects and retries | Include blocking retries per delivery |
| Blocking retry too long before switching topics | Main topic remains blocked, long poll cycles | Keep blocking retries short, use retry topics for long errors |
| Passing every exception through both tiers | Permanent errors inflate cost and delay recovery | Classify non-retryable and route to DLT early |
| Overriding DefaultErrorHandler outside retry-topic infrastructure | Records fail to route to retry topics properly | Use official extensions/APIs for your version |
| Assuming retry publish + offset commit is atomic | Duplicates on failure between the two steps | Design idempotency and verify recovery |
| Ignoring per-key ordering | Newer events finish before older events | Use versions/state machines or pick another policy |
| Using retry topics on unsupported transactional/batch listeners | Missing desired semantics or broken config | Check limits, pick suitable processor/container |
| Not monitoring retry topic lag | Main topic KPIs look green while business lags | Monitor full pipeline and oldest event age |
| Retry topic retention too short | Records expire before reprocessing | Size retention from outage duration and backoff |
| Retrying en masse after an outage | Newly recovered dependency gets overloaded again | Limit concurrency, backoff, and jitter |
| Logging DLT entries and forgetting them | Permanent errors pile up | Assign owners, alerts, and fix/replay workflows |

## 23. Pre-Production Checklist

Before enabling hybrid retry, answer:

1. Which errors get blocking retry and which go straight to retry topics?
2. Are permanent exceptions excluded from both retry tiers?
3. How many blocking attempts are allowed per non-blocking delivery?
4. What are the configured maximum listener calls and maximum total duration?
5. Is blocking backoff safe with max.poll.interval.ms?
6. Does the listener require per-key/per-partition ordering?
7. Is the retry-topic pattern supported with the current record listener and transaction setup?
8. When publishing to a retry topic succeeds but source offset commit fails, how are duplicates handled?
9. If publishing to a retry topic or DLT fails, is redelivery capability preserved?
10. Are event IDs and idempotency keys kept intact across all tiers?
11. Do retry topics have proper retention, ACLs, partitions, and replication?
12. Do dashboards monitor retry topic lag, oldest age, and DLT backlog?
13. Is there a DLT handling and replay workflow that prevents duplicate side effects?
14. During prolonged dependency outages, does the system have capacity to hold backlogs and catch up after recovery?
15. Do tests cover restarts, rebalances, and publish/commit failures at topic-handoff boundaries?

Combining blocking and non-blocking retry helps a system react fast to brief glitches without stalling the main consumer during prolonged failures. The design's value lies in choosing the right exceptions, wait times, and tier handoff points; real-world stability still depends on idempotency, offset management, ordering, transaction limits, and observability. Once those boundaries are clear, two-tier retry boosts resilience while keeping failed records investigable and recoverable.
